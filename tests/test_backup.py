import json
import sqlite3
from pathlib import Path

import pytest

from scripts import backup
from forge_controller.store import Store


@pytest.fixture
def prototype(tmp_path,monkeypatch):
    root=tmp_path/'prototype';root.mkdir()
    (root/'.secrets').mkdir(mode=0o700)
    (root/'examples').mkdir()
    config={'FORGE_DATABASE':'state/tasks.sqlite3','FORGE_PRINCIPALS_FILE':'.secrets/principals.json',
            'FORGE_REPOSITORIES_FILE':'.secrets/repositories.json','FORGE_EXAMPLES_FILE':'examples/reviewed.json'}
    for name,content in [('local-controller.json',config),('principals.json',{}),('repositories.json',{}),('mcp-token.json',{'token':'t'*40})]:
        p=root/'.secrets'/name;p.write_text(json.dumps(content));p.chmod(0o600)
    (root/'examples/reviewed.json').write_text('[]')
    for name in ('requirements.lock','requirements-mcp.lock','pyproject.toml'):
        (root/name).write_text('versioned configuration')
    monkeypatch.setattr(backup,'ROOT',root)
    monkeypatch.setattr(backup.subprocess,'check_output',lambda *a,**k:'a'*40+'\n')
    return root


def test_live_snapshot_preserves_rows_without_taking_controller_lock(prototype,tmp_path):
    store=Store(prototype/'state/tasks.sqlite3')
    try:
        task=store.create('owner','forge')
        store.update(task,'succeeded',result='preserved',audit=[{'tool':'read','status':'allowed'}])
        target=tmp_path/'snapshot'
        result=backup.create(target)
        assert result['task_count']==1 and result['verified']
        with sqlite3.connect(target/'tasks.sqlite3') as db:
            assert db.execute('SELECT result FROM tasks WHERE id=?',(task,)).fetchone()==('preserved',)
        store.create('owner','forge')
        assert backup.verify(target)['task_count']==1
        with pytest.raises(ValueError):backup.create(target)
    finally:
        store.close()


@pytest.mark.parametrize('mutation',['checksum','permission','symlink'])
def test_restore_verification_rejects_tampering(prototype,tmp_path,mutation):
    store=Store(prototype/'state/tasks.sqlite3');store.close()
    target=tmp_path/'snapshot';backup.create(target)
    p=target/'principals.json'
    if mutation=='checksum':p.write_text('changed')
    elif mutation=='permission':p.chmod(0o644)
    else:
        outside=tmp_path/'outside';outside.write_bytes(p.read_bytes());outside.chmod(0o600)
        p.unlink();p.symlink_to(outside)
    with pytest.raises(ValueError):backup.verify(target)
