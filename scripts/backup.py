"""Create and verify private, consistent backups of this Mac prototype."""
import argparse
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
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError('Expected a private regular file')


def check_database(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Database integrity check failed')
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('Unsupported database version')
        return db.execute('SELECT count(*) FROM tasks').fetchone()[0]


def create(destination):
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
        commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        manifest = {'version':1,'git_commit':commit,'task_count':count,
                    'sha256':{name:digest(temporary/name) for name in sorted(FILES)}}
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
    if manifest['version']!=1 or set(manifest['sha256'])!=FILES:
        raise ValueError('Invalid backup manifest')
    for name, expected in manifest['sha256'].items():
        private_file(directory/name)
        if digest(directory/name)!=expected:
            raise ValueError('Backup checksum mismatch')
    count=check_database(directory/'tasks.sqlite3')
    if count != manifest['task_count']:
        raise ValueError('Backup row count mismatch')
    return {'verified':True,'task_count':count,'git_commit':manifest['git_commit']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create','verify'])
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    os.umask(0o077)
    print(json.dumps(create(args.directory) if args.action=='create' else verify(args.directory)))


if __name__=='__main__':
    main()
