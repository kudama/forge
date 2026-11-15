"""Restore a verified snapshot into an unused checkout; never starts services."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import backup
from scripts.controller import server_command
from forge_controller.config import Settings


def restore(snapshot, root, repositories, listener=None, *, apply=True):
    snapshot = snapshot.expanduser().absolute()
    root = root.expanduser().absolute()
    if root.resolve() != root or not root.is_dir():
        raise ValueError('Target checkout must be an existing canonical directory')
    if snapshot.resolve() != snapshot:
        raise ValueError('Snapshot path must be canonical')
    for name in ('.secrets', 'state'):
        if (root/name).exists() or (root/name).is_symlink():
            raise ValueError('Target already has private configuration or state; preserving it')
    evidence = backup.verify(snapshot)
    if evidence['manifest_version'] != 2:
        raise ValueError('Migration requires a version-2 snapshot with handoff history')
    config = json.loads((snapshot/'controller.json').read_text())
    principals = json.loads((snapshot/'principals.json').read_text())
    original = json.loads((snapshot/'repositories.json').read_text())
    if not repositories or set(repositories)-set(original):
        raise ValueError('Map at least one existing repository ID; new grants are not allowed')
    mapped = {}
    for name, path in repositories.items():
        path = path.expanduser().absolute()
        if not path.is_dir() or path.resolve() != path:
            raise ValueError('Mapped repository must be an existing canonical directory')
        mapped[name] = {**original[name], 'root': str(path)}
    disabled = sorted(set(original)-set(mapped))
    for principal in principals.values():
        if 'repositories' in principal:
            principal['repositories'] = [r for r in principal['repositories'] if r in mapped]
    # Source TLS paths belong to the old host. Require explicit destination inputs.
    for key in ('FORGE_LISTEN_HOST', 'FORGE_TLS_CERTFILE', 'FORGE_TLS_KEYFILE'):
        config.pop(key, None)
    config.update(listener or {})
    server_command(config)
    archive = json.loads((snapshot/'handoffs.json').read_text())
    targets = {'FORGE_PRINCIPALS_FILE': '.secrets/principals.json',
               'FORGE_REPOSITORIES_FILE': '.secrets/repositories.json',
               'FORGE_EXAMPLES_FILE': '.secrets/reviewed.json',
               'FORGE_DATABASE': 'state/tasks.sqlite3'}
    config.update({key: str(root/path) for key, path in targets.items()})
    prior_env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix='.forge-restore-', dir=root) as directory:
        stage = Path(directory)
        private = stage/'.secrets'; private.mkdir(mode=0o700)
        state = stage/'state'; state.mkdir(mode=0o700)
        journal = state/'handoffs'; journal.mkdir(mode=0o700)

        def write(path, value):
            with open(path, 'x', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
                json.dump(value, output, indent=2)
                output.write('\n')

        def copy(source, target):
            with open(target, 'xb', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
                output.write(source.read_bytes())

        write(private/'local-controller.json', config)
        write(private/'principals.json', principals)
        write(private/'repositories.json', mapped)
        copy(snapshot/'mcp-token.json', private/'mcp-token.json')
        copy(snapshot/'reviewed.json', private/'reviewed.json')
        copy(snapshot/'tasks.sqlite3', state/'tasks.sqlite3')
        for order_id, record in archive['records'].items():
            write(journal/(order_id+'.json'), record)
        # Validate using staged private files without starting or opening the Store.
        try:
            os.environ.update(config)
            os.environ.update({key: str(stage/path) for key, path in targets.items()})
            Settings.from_environment()
        finally:
            os.environ.clear()
            os.environ.update(prior_env)
        if backup.check_database(state/'tasks.sqlite3') != evidence['task_count']:
            raise ValueError('Restored task count mismatch')
        # Recheck the unchanged source before publishing any destination files.
        backup.verify(snapshot)
        if not apply:
            return {**evidence, 'restored': False, 'validation_only': True,
                    'mapped_repositories': {name: repo['root'] for name, repo in mapped.items()},
                    'disabled_repositories': disabled, 'services_started': False,
                    'handoff_endpoints_unchanged': True}
        created = []
        try:
            for name in ('.secrets', 'state'):
                target = root/name
                target.mkdir(mode=0o700)  # Exclusive; never merge existing directories.
                created.append(target)
                for path in (stage/name).iterdir():
                    shutil.move(str(path), target/path.name)
        except BaseException:
            # Only directories exclusively created by this invocation are removed.
            for target in reversed(created):
                shutil.rmtree(target)
            raise
    return {**evidence, 'restored': True, 'disabled_repositories': disabled,
            'services_started': False, 'handoff_endpoints_unchanged': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--checkout', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repository', action='append', required=True, metavar='ID=PATH')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--certfile')
    parser.add_argument('--keyfile')
    parser.add_argument('--plan', action='store_true',
                        help='validate using temporary private staging; do not publish restored state')
    args = parser.parse_args()
    repositories = {}
    for item in args.repository:
        name, separator, path = item.partition('=')
        if not separator or not name or not path or name in repositories:
            parser.error('Each repository mapping must be a unique ID=PATH')
        repositories[name] = Path(path)
    listener = {'FORGE_LISTEN_HOST': args.host}
    if args.certfile:
        listener['FORGE_TLS_CERTFILE'] = args.certfile
    if args.keyfile:
        listener['FORGE_TLS_KEYFILE'] = args.keyfile
    os.umask(0o077)
    print(json.dumps(restore(args.snapshot, args.checkout, repositories, listener, apply=not args.plan)))


if __name__ == '__main__':
    main()
