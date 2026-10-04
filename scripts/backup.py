"""Create and verify private, consistent backups of a local controller deployment."""
import argparse
import fcntl
import re
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {'controller.json', 'principals.json', 'repositories.json', 'mcp-token.json',
         'reviewed.json', 'tasks.sqlite3', 'requirements.lock', 'requirements-mcp.lock', 'pyproject.toml'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_file(path):
    info = path.lstat()
    mode = info.st_mode
    if not stat.S_ISREG(mode) or mode & 0o077 or info.st_nlink != 1:
        raise ValueError('Expected a private regular file')


def check_database(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Database integrity check failed')
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('Unsupported database version')
        return db.execute('SELECT count(*) FROM tasks').fetchone()[0]


def check_handoffs(payload):
    if not isinstance(payload, dict) or set(payload) != {'version', 'records'} or payload['version'] != 1 or not isinstance(payload['records'], dict):
        raise ValueError('Invalid handoff archive')
    for order_id, record in payload['records'].items():
        if (not re.fullmatch('[0-9a-f]{32}', order_id) or not isinstance(record, dict)
            or record.get('version') != 1 or not isinstance(record.get('order'), dict)
            or record['order'].get('work_order_id') != order_id
            or record.get('submission') not in {'submitting', 'submission_unknown', 'accepted'}
            or not isinstance(record.get('owner'), str) or not isinstance(record.get('controller'), str)
            or (record['submission'] == 'accepted' and not re.fullmatch('[0-9a-f]{32}', str(record.get('task_id', ''))))):
            raise ValueError('Invalid handoff record')
    return len(payload['records'])


def snapshot_handoffs(root):
    root = root.absolute()
    if root.resolve() != root:
        raise ValueError('Journal must be canonical')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = root.lstat().st_mode
    if not stat.S_ISDIR(mode) or mode & 0o077:
        raise ValueError('Expected private journal directory')
    fd = os.open(root/'.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_nlink != 1:
            raise ValueError('Invalid journal lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Handoff active; retry backup later') from None
        records = {}
        for path in root.iterdir():
            if path.name == '.lock':
                continue
            if not re.fullmatch(r'[0-9a-f]{32}\.json', path.name):
                raise ValueError('Unexpected journal entry')
            private_file(path)
            if path.stat().st_nlink != 1 or path.stat().st_size > 262144:
                raise ValueError('Invalid journal input')
            records[path.stem] = json.loads(path.read_bytes())
        archive = {'version':1, 'records':records}
        check_handoffs(archive)
        return archive
    finally:
        os.close(fd)


def create(destination, journal=None):
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Backup destination must not exist')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    config_path = ROOT/'.secrets/local-controller.json'
    private_file(config_path)
    config = json.loads(config_path.read_text())
    def configured(name):
        path = Path(config[name]).expanduser()
        return path if path.is_absolute() else ROOT/path
    sources = {'controller.json': config_path,
               'principals.json': configured('FORGE_PRINCIPALS_FILE'),
               'repositories.json': configured('FORGE_REPOSITORIES_FILE'),
               'mcp-token.json': ROOT/'.secrets/mcp-token.json',
               'reviewed.json': configured('FORGE_EXAMPLES_FILE'),
               **{name:ROOT/name for name in ('requirements.lock','requirements-mcp.lock','pyproject.toml')}}
    for name in ('principals.json','repositories.json','mcp-token.json'):
        private_file(sources[name])
    for path in sources.values():
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Expected a regular backup input')
    hashes = {name:digest(path) for name,path in sources.items()}
    temporary = Path(tempfile.mkdtemp(prefix='.forge-backup-', dir=destination.parent))
    try:
        for name, path in sources.items():
            shutil.copyfile(path, temporary/name)
            (temporary/name).chmod(0o600)
        database = configured('FORGE_DATABASE')
        private_file(database)
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as source:
            with sqlite3.connect(temporary/'tasks.sqlite3') as target:
                source.backup(target)
        (temporary/'tasks.sqlite3').chmod(0o600)
        count = check_database(temporary/'tasks.sqlite3')
        if any(digest(path)!=hashes[name] or digest(temporary/name)!=hashes[name] for name,path in sources.items()):
            raise ValueError('Configuration changed during backup; retry')
        archive = snapshot_handoffs(journal if journal is not None else ROOT/'state/handoffs')
        (temporary/'handoffs.json').write_text(json.dumps(archive, allow_nan=False)+'\n')
        (temporary/'handoffs.json').chmod(0o600)
        commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        manifest = {'version':2,'git_commit':commit,'task_count':count,'handoff_count':len(archive['records']),
                    'sha256':{name:digest(temporary/name) for name in sorted(FILES | {'handoffs.json'})}}
        (temporary/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (temporary/'manifest.json').chmod(0o600)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return verify(destination)


def verify(directory):
    mode = directory.lstat().st_mode
    if not stat.S_ISDIR(mode) or mode & 0o077:
        raise ValueError('Expected a private backup directory')
    private_file(directory/'manifest.json')
    manifest = json.loads((directory/'manifest.json').read_text())
    expected_files = FILES if manifest['version']==1 else FILES | {'handoffs.json'}
    if manifest['version'] not in {1,2} or set(manifest['sha256'])!=expected_files:
        raise ValueError('Invalid backup manifest')
    for name, expected in manifest['sha256'].items():
        private_file(directory/name)
        if digest(directory/name)!=expected:
            raise ValueError('Backup checksum mismatch')
    count=check_database(directory/'tasks.sqlite3')
    if count != manifest['task_count']:
        raise ValueError('Backup row count mismatch')
    handoffs = None
    if manifest['version']==2:
        handoffs = check_handoffs(json.loads((directory/'handoffs.json').read_bytes()))
        if handoffs != manifest['handoff_count']:
            raise ValueError('Backup handoff count mismatch')
    return {'verified':True,'task_count':count,'git_commit':manifest['git_commit'],
            'manifest_version':manifest['version'],'handoff_count':handoffs}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create','verify'])
    parser.add_argument('directory',type=Path)
    parser.add_argument('--journal',type=Path,help='Override journal source for create (default state/handoffs)')
    args=parser.parse_args()
    if args.action=='verify' and args.journal is not None:
        parser.error('--journal is only valid for create')
    os.umask(0o077)
    print(json.dumps(create(args.directory,args.journal) if args.action=='create' else verify(args.directory)))


if __name__=='__main__':
    main()
