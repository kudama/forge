import json
import os
from pathlib import Path
import shlex
import socket
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace

import httpx
import pytest

from scripts import controller


@pytest.fixture
def certificate(tmp_path):
    cert, key = tmp_path/'cert.pem', tmp_path/'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-days', '1', '-subj', '/CN=localhost', '-addext',
                    'subjectAltName=DNS:localhost,IP:127.0.0.1',
                    '-keyout', str(key), '-out', str(cert)],
                   check=True, capture_output=True)
    key.chmod(0o600)
    return {'FORGE_TLS_CERTFILE': str(cert), 'FORGE_TLS_KEYFILE': str(key)}


def test_default_listener_unchanged():
    assert controller.server_command({}) == controller.COMMAND


@pytest.mark.parametrize('host', ['0.0.0.0', '::', '8.8.8.8', '224.0.0.1', 'foundry.local'])
def test_no_wildcard_public_multicast_or_hostname_binding(host):
    with pytest.raises(ValueError):
        controller.server_command({'FORGE_LISTEN_HOST': host})


@pytest.mark.parametrize('host', ['10.0.0.106', '192.168.1.20', 'fd00::1'])
def test_network_requires_tls(host, certificate):
    with pytest.raises(ValueError, match='requires both TLS'):
        controller.server_command({'FORGE_LISTEN_HOST': host})
    command = controller.server_command({'FORGE_LISTEN_HOST': host, **certificate})
    assert command[3] == host
    assert '--ssl-certfile' in command and '--ssl-keyfile' in command


@pytest.mark.parametrize('mutation', ['partial', 'relative', 'permissive', 'symlink', 'mismatch'])
def test_invalid_tls_fails_before_launch(certificate, tmp_path, mutation):
    config = dict(certificate)
    key = Path(config['FORGE_TLS_KEYFILE'])
    if mutation == 'partial':
        config.pop('FORGE_TLS_KEYFILE')
    elif mutation == 'relative':
        config['FORGE_TLS_KEYFILE'] = 'key.pem'
    elif mutation == 'permissive':
        key.chmod(0o644)
    elif mutation == 'symlink':
        other = tmp_path/'other'; key.rename(other); key.symlink_to(other)
    else:
        key.write_text('invalid key')
    with pytest.raises((ValueError, ssl.SSLError)):
        controller.server_command(config)


def test_running_checks_exact_network_command_and_legacy_record(tmp_path, monkeypatch, certificate):
    record = tmp_path/'process.json'
    monkeypatch.setattr(controller, 'RECORD', record)
    listener = {'FORGE_LISTEN_HOST': '10.0.0.106', **certificate}
    command = controller.server_command(listener)
    record.write_text(json.dumps({'pid': 12345, 'listener': listener}))
    monkeypatch.setattr(controller.subprocess, 'run', lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout=shlex.join(command)))
    assert controller.running() == 12345
    command[1] = 'another.app:app'
    assert controller.running() is None
    command[:] = controller.COMMAND
    record.write_text(json.dumps({'pid': 12345}))
    assert controller.running() == 12345


def test_real_https_server_validates_certificate_and_authentication(tmp_path, certificate):
    principals = tmp_path/'principals.json'
    principals.write_text(json.dumps({'operator': {'token': 't'*40,
        'agents': ['forge'], 'services': ['prototype']}}))
    principals.chmod(0o600)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    command = controller.server_command(certificate)
    command[5] = str(port)
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]/'src'),
           'FORGE_PRINCIPALS_FILE': str(principals), 'FORGE_DATABASE': str(tmp_path/'tasks.db')}
    for name in ('FORGE_REPOSITORIES_FILE', 'FORGE_EXAMPLES_FILE'):
        env.pop(name, None)
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', *command[1:]],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        context = ssl.create_default_context(cafile=certificate['FORGE_TLS_CERTFILE'])
        with httpx.Client(base_url=f'https://127.0.0.1:{port}', verify=context,
                          trust_env=False, timeout=1) as client:
            for _ in range(100):
                try:
                    response = client.get('/health/live')
                    break
                except httpx.ConnectError:
                    if process.poll() is not None:
                        pytest.fail('HTTPS server exited before becoming live')
                    time.sleep(.05)
            else:
                pytest.fail('HTTPS server did not become live')
            assert response.status_code == 200
            assert client.get('/v1/tasks/'+'a'*32).status_code == 401
            assert client.get('/v1/tasks/'+'a'*32,
                              headers={'Authorization': 'Bearer '+'t'*40}).status_code == 404
        with httpx.Client(trust_env=False) as untrusted:
            with pytest.raises(httpx.ConnectError):
                untrusted.get(f'https://127.0.0.1:{port}/health/live')
    finally:
        process.terminate()
        process.wait(timeout=10)
