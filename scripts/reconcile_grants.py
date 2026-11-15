"""Restore selected snapshot grants at new roots; preserve current credentials."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import backup
from forge_controller.config import Settings
from forge_controller.tools import execute, ToolDenied


def private_json(path):
    backup.private_file(path)
    return json.loads(path.read_text())


def write_private(path, data):
    with open(path, 'xb', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
        output.write(data)


def replace_private(path, data):
    fd, name = tempfile.mkstemp(prefix='.grant-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def reconcile(snapshot, root, mappings, apply=False):
    snapshot = snapshot.expanduser().resolve()
    root = root.expanduser().resolve()
    backup.verify(snapshot)
    profile = private_json(root/'.secrets/local-controller.json')
    def configured(key):
        value = Path(profile[key]).expanduser()
        path = value if value.is_absolute() else root/value
        if path.resolve() != path:
            raise ValueError('Private configuration paths must be canonical, without symlinks')
        return path
    principals_path = configured('FORGE_PRINCIPALS_FILE')
    repositories_path = configured('FORGE_REPOSITORIES_FILE')
    current_principals = private_json(principals_path)
    current_repositories = private_json(repositories_path)
    before_principals = principals_path.read_bytes()
    before_repositories = repositories_path.read_bytes()
    source_principals = private_json(snapshot/'principals.json')
    source_repositories = private_json(snapshot/'repositories.json')
    if not mappings or set(mappings)-set(source_repositories):
        raise ValueError('Map only explicitly approved snapshot repository IDs')
    principals = copy.deepcopy(current_principals)
    repositories = copy.deepcopy(current_repositories)
    for name, path in mappings.items():
        path = path.expanduser().absolute()
        if path.resolve() != path or not path.is_dir():
            raise ValueError('Mapped repository must be an existing canonical directory')
        proposed = {**source_repositories[name], 'root': str(path)}
        if name in repositories and repositories[name] != proposed:
            raise ValueError('Existing repository differs; preserving it: '+name)
        repositories[name] = proposed
    restored = {}
    for owner, current in principals.items():
        original = source_principals.get(owner)
        if original is None:
            continue  # Never create a principal or change a new identity.
        additions = [name for name in original.get('repositories', [])
                     if name in mappings and name not in current.get('repositories', [])]
        if not additions:
            continue
        if {k:v for k,v in current.items() if k != 'repositories'} != {
                k:v for k,v in original.items() if k != 'repositories'}:
            raise ValueError('Principal settings changed since snapshot; review before restoring grants')
        if any(name in current_repositories for name in additions):
            raise ValueError('Repository already exists with a removed principal grant; preserving revocation')
        current['repositories'] = current.get('repositories', [])+additions
        restored[owner] = additions
    database = configured('FORGE_DATABASE')
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
        active = db.execute("SELECT count(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0]
    if active:
        raise ValueError('Wait for active tasks before reconciling grants')
    previous_env = os.environ.copy()
    reads = 0
    with tempfile.TemporaryDirectory(prefix='.grant-check-', dir=root/'.secrets') as temporary:
        temporary = Path(temporary)
        staged_principals = temporary/'principals.json'
        staged_repositories = temporary/'repositories.json'
        write_private(staged_principals, (json.dumps(principals, indent=2)+'\n').encode())
        write_private(staged_repositories, (json.dumps(repositories, indent=2)+'\n').encode())
        try:
            os.environ.update(profile)
            os.environ.update(FORGE_PRINCIPALS_FILE=str(staged_principals),
                              FORGE_REPOSITORIES_FILE=str(staged_repositories))
            settings = Settings.from_environment()
        finally:
            os.environ.clear()
            os.environ.update(previous_env)
        for name in mappings:
            owners = [(owner, agent) for owner, grants in principals.items()
                      if name in grants.get('repositories', [])
                      for agent in ('repository_analyst', 'implementer') if agent in grants['agents']]
            if not owners:
                raise ValueError('No existing source-reading principal for '+name)
            owner, agent = owners[0]
            for path in repositories[name]['files']:
                # Use the real read policy: size, UTF-8, hidden paths, links and grants.
                try:
                    execute(settings, owner, agent, 'read_repository_file',
                            {'repository':name,'path':path,'start_line':1,'end_line':1})
                except ToolDenied:
                    raise ValueError('Approved source cannot be read under current policy: '+name+':'+path) from None
                reads += 1
        changed = principals != current_principals or repositories != current_repositories
        result = {'validated':True,'applied':False,'changed':changed,
                  'repositories':{name:repositories[name]['root'] for name in mappings},
                  'source_files_checked':reads,'restored_grants':restored,
                  'credentials_changed':False}
        if apply and changed:
            if (principals_path.read_bytes() != before_principals or
                    repositories_path.read_bytes() != before_repositories):
                raise ValueError('Configuration changed during validation; retry')
            saved = Path(tempfile.mkdtemp(prefix='grants-before-', dir=root/'.secrets'))
            write_private(saved/'principals.json', before_principals)
            write_private(saved/'repositories.json', before_repositories)
            write_private(saved/'rollback.json', json.dumps({
                'principals_target':str(principals_path),'repositories_target':str(repositories_path),
                'new_principals_sha256':hashlib.sha256(staged_principals.read_bytes()).hexdigest(),
                'new_repositories_sha256':hashlib.sha256(staged_repositories.read_bytes()).hexdigest()}).encode())
            # Publish the manifest first. Old cached grants remain safe until restart.
            replace_private(repositories_path, staged_repositories.read_bytes())
            try:
                replace_private(principals_path, staged_principals.read_bytes())
            except BaseException:
                replace_private(repositories_path, before_repositories)
                raise
            result.update(applied=True, backup_directory=str(saved))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--checkout', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repository', action='append', required=True, metavar='ID=PATH')
    parser.add_argument('--apply', action='store_true', help='write validated changes; default is dry run')
    args = parser.parse_args()
    mappings = {}
    for item in args.repository:
        name, separator, path = item.partition('=')
        if not separator or not name or not path or name in mappings:
            parser.error('Expected a unique ID=PATH for each repository')
        mappings[name] = Path(path)
    os.umask(0o077)
    print(json.dumps(reconcile(args.snapshot, args.checkout, mappings, args.apply)))


if __name__ == '__main__':
    main()
