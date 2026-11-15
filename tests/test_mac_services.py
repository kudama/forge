from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import mac_services


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    calls = []
    home = tmp_path / 'home'
    root = tmp_path / 'forge'
    (root / '.venv/bin').mkdir(parents=True)
    (root / '.venv/bin/python').touch()
    ollama = tmp_path / 'ollama'
    ollama.touch()
    monkeypatch.setattr(mac_services, 'ROOT', root)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setattr(mac_services.sys, 'platform', 'darwin')
    monkeypatch.setattr(mac_services.os, 'getuid', lambda: 501)
    monkeypatch.setattr(mac_services.os, 'umask', lambda mask: None)

    def launchctl(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='state = running\npid = 123\n')

    monkeypatch.setattr(mac_services.subprocess, 'run', launchctl)

    def invoke(action, role=None):
        arguments = ['mac_services.py', action, '--ollama', str(ollama)]
        if role:
            arguments += ['--role', role]
        monkeypatch.setattr(mac_services.sys, 'argv', arguments)
        mac_services.main()
        return calls

    return invoke, home


@pytest.mark.parametrize('action', ['start', 'stop'])
@pytest.mark.parametrize('role', ['controller', 'ollama'])
def test_explicit_role_only_operates_selected_service(launcher, action, role):
    invoke, home = launcher
    label = mac_services.LABELS[role]
    if action == 'start':
        expected = [['launchctl', 'bootstrap', 'gui/501',
                     str(home / 'Library/LaunchAgents' / (label + '.plist'))]]
    else:
        expected = [['launchctl', 'print', 'gui/501/' + label],
                    ['launchctl', 'bootout', 'gui/501/' + label]]
    assert invoke(action, role) == expected


@pytest.mark.parametrize('action', ['start', 'stop'])
def test_default_operates_both_in_existing_order(launcher, action):
    invoke, _ = launcher
    calls = invoke(action)
    operated = [call for call in calls if call[1] in {'bootstrap', 'bootout'}]
    assert len(operated) == 2
    for call, label in zip(operated, mac_services.LABELS.values()):
        assert label in call[-1]


@pytest.mark.parametrize('role', [None, 'controller', 'ollama'])
def test_status_selects_requested_service(launcher, role, capsys):
    invoke, _ = launcher
    calls = invoke('status', role)
    labels = [mac_services.LABELS[role]] if role else list(mac_services.LABELS.values())
    assert calls == [['launchctl', 'print', 'gui/501/' + label] for label in labels]
    output = capsys.readouterr().out
    assert all(label + ' loaded' in output for label in labels)


@pytest.mark.parametrize('role', [None, 'controller', 'ollama'])
def test_install_and_remove_select_requested_definitions(launcher, role):
    invoke, home = launcher
    assert invoke('install', role) == []
    labels = [mac_services.LABELS[role]] if role else list(mac_services.LABELS.values())
    paths = [home / 'Library/LaunchAgents' / (label + '.plist') for label in labels]
    assert all(path.is_file() and path.stat().st_mode & 0o777 == 0o600 for path in paths)
    calls = invoke('remove', role)
    assert [call for call in calls if call[1] == 'bootout'] == [
        ['launchctl', 'bootout', 'gui/501/' + label] for label in labels]
    assert all(not path.exists() for path in paths)
    if role:
        other = next(name for name in mac_services.LABELS if name != role)
        assert not (home/'Library/LaunchAgents'/(mac_services.LABELS[other]+'.plist')).exists()


@pytest.mark.parametrize('role', [None, 'controller', 'ollama'])
def test_run_defaults_to_controller_and_preserves_explicit_role(launcher, monkeypatch, role):
    invoke, _ = launcher
    executed = []
    monkeypatch.setattr(mac_services, 'run', lambda selected, ollama: executed.append(selected) or 0)
    with pytest.raises(SystemExit) as error:
        invoke('run', role)
    assert error.value.code == 0
    assert executed == [role or 'controller']


def test_stop_unloaded_service_does_not_bootout(launcher, monkeypatch):
    invoke, _ = launcher
    calls = []

    def unloaded(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(mac_services.subprocess, 'run', unloaded)
    invoke('stop', 'controller')
    assert calls == [['launchctl', 'print', 'gui/501/org.forge.local.controller']]


def test_start_propagates_launchctl_failure(launcher, monkeypatch):
    invoke, _ = launcher

    def failed(command, **kwargs):
        raise mac_services.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(mac_services.subprocess, 'run', failed)
    with pytest.raises(mac_services.subprocess.CalledProcessError):
        invoke('start', 'controller')
