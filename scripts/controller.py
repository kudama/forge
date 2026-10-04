"""Manual foreground launcher; never starts Ollama or installs autostart."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import signal
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT/'state'
RECORD = STATE/'controller-process.json'
COMMAND = [str(ROOT/'.venv/bin/uvicorn'), 'forge_controller.app:app',
           '--host', '127.0.0.1', '--port', '8787', '--workers', '1', '--no-access-log']


def running():
    if not RECORD.exists():
        return None
    record = json.loads(RECORD.read_text())
    pid = record['pid']
    if type(pid) is not int or pid <= 1:
        raise ValueError('Invalid process record')
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError('Cannot verify controller process; refusing to signal it')
    args = shlex.split(result.stdout.strip())
    # Python script processes include the interpreter before the script path.
    return pid if args == COMMAND or args[1:] == COMMAND else None


def start(config_path):
    STATE.mkdir(mode=0o700, exist_ok=True)
    with (STATE/'controller-launch.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A managed controller is already running')
        if running():
            raise SystemExit('A managed controller is already running')
        mode = config_path.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise SystemExit('Local configuration must be an owner-only regular file (mode 600)')
        config = json.loads(config_path.read_text())
        allowed = {'FORGE_PRINCIPALS_FILE', 'FORGE_REPOSITORIES_FILE', 'FORGE_EXAMPLES_FILE',
                   'FORGE_DATABASE', 'FORGE_MODEL', 'FORGE_ROLE_MODELS', 'FORGE_TOOL_ROUNDS',
                   'FORGE_CONTEXT_LENGTH', 'FORGE_MAX_OUTPUT_TOKENS', 'FORGE_TASK_TIMEOUT',
                   'FORGE_CAPACITY', 'FORGE_MODEL_URL'}
        if not isinstance(config, dict) or set(config)-allowed or any(not isinstance(v,str) for v in config.values()):
            raise SystemExit('Invalid local configuration')
        os.chdir(ROOT)
        os.environ.update(config)
        from forge_controller.config import Settings
        Settings.from_environment()  # Validate before starting a process.
        child = subprocess.Popen(COMMAND, cwd=ROOT, env=os.environ.copy())
        RECORD.write_text(json.dumps({'pid':child.pid})+'\n')
        RECORD.chmod(0o600)
        def stop_child(signum, frame):
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, stop_child)
        signal.signal(signal.SIGINT, stop_child)
        try:
            raise SystemExit(child.wait())
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait()
            RECORD.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('--config', type=Path, default=ROOT/'.secrets/local-controller.json')
    args = parser.parse_args()
    if args.action == 'start':
        start(args.config.resolve())
    else:
        pid = running()
        if args.action == 'status':
            print('running' if pid else 'stopped')
        elif pid:
            os.kill(pid, signal.SIGTERM)
            for _ in range(100):
                if not running():
                    print('stopped')
                    return
                time.sleep(.1)
            raise SystemExit('Controller is still stopping; inspect its terminal')
        else:
            print('stopped')


if __name__ == '__main__':
    main()
