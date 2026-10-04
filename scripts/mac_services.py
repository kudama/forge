"""User-login launchd services for the local Forge prototype (macOS only)."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'ollama': 'org.forge.local.ollama', 'controller': 'org.forge.local.controller'}
LOGS = ROOT/'state'/'logs'


def definition(role, ollama):
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'PYTHONUNBUFFERED': '1'}
    if role == 'ollama':
        env.update(OLLAMA_HOST='127.0.0.1:11434', OLLAMA_NO_CLOUD='1',
                   OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1',
                   OLLAMA_CONTEXT_LENGTH='4096', OLLAMA_DEBUG='0')
    return {'Label': LABELS[role],
            'ProgramArguments': [str(ROOT/'.venv/bin/python'), str(Path(__file__).resolve()),
                                 'run', '--role', role, '--ollama', str(ollama)],
            'WorkingDirectory': str(ROOT), 'EnvironmentVariables': env,
            'KeepAlive': True, 'ThrottleInterval': 30, 'ExitTimeOut': 20,
            'AbandonProcessGroup': False, 'Umask': 0o077,
            'StandardOutPath': '/dev/null', 'StandardErrorPath': '/dev/null'}


def run(role, ollama):
    LOGS.mkdir(mode=0o700, parents=True, exist_ok=True)
    LOGS.chmod(0o700)
    logger = logging.getLogger('service')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(LOGS/(role+'.log'), maxBytes=1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(handler)
    command = [str(ollama), 'serve'] if role == 'ollama' else [
        str(ROOT/'.venv/bin/python'), str(ROOT/'scripts/controller.py'), 'start']
    child = None
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if stopping:
            child.terminate()
        logger.info('started role=%s pid=%s', role, child.pid)
        while True:
            chunk = child.stdout.readline(4096)
            if not chunk:
                break
            logger.info('%s', chunk.decode('utf-8', errors='replace').rstrip())
        code = child.wait()
        logger.info('exited role=%s code=%s', role, code)
        return code if code >= 0 else 128-code
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=20)
        handler.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'start', 'stop', 'status', 'remove', 'run'])
    parser.add_argument('--role', choices=LABELS, default='controller')
    parser.add_argument('--ollama', type=Path, default=Path('/opt/homebrew/bin/ollama'))
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('This launcher requires macOS')
    os.umask(0o077)
    if args.action == 'run':
        raise SystemExit(run(args.role, args.ollama))
    directory = Path.home()/'Library/LaunchAgents'
    domain = 'gui/'+str(os.getuid())
    for role, label in LABELS.items():
        path = directory/(label+'.plist')
        target = domain+'/'+label
        if args.action == 'install':
            if not args.ollama.is_file() or not (ROOT/'.venv/bin/python').is_file():
                raise SystemExit('Install the local Python environment and Ollama first')
            directory.mkdir(parents=True, exist_ok=True)
            content = plistlib.dumps(definition(role, args.ollama.resolve()))
            if path.exists() and path.read_bytes() != content:
                raise SystemExit('Existing service definition differs; inspect it before replacing')
            path.write_bytes(content)
            path.chmod(0o600)
            print('installed', label)
        elif args.action == 'start':
            subprocess.run(['launchctl', 'bootstrap', domain, str(path)], check=True)
            print('started', label)
        elif args.action in {'stop', 'remove'}:
            exists = subprocess.run(['launchctl', 'print', target], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL).returncode == 0
            if exists:
                subprocess.run(['launchctl', 'bootout', target], check=True)
            if args.action == 'remove':
                path.unlink(missing_ok=True)
            print(args.action, label)
        else:
            result = subprocess.run(['launchctl', 'print', target], capture_output=True, text=True)
            print(label, 'loaded' if result.returncode == 0 else 'not loaded')
            for line in result.stdout.splitlines():
                if line.strip().startswith(('state =', 'pid =', 'last exit code =')):
                    print(' ', line.strip())


if __name__ == '__main__':
    main()
