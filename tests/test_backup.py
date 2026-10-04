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


@pytest.mark.parametrize('relative', ['examples/reviewed.json', 'requirements.lock'])
def test_creation_rejects_symlinked_public_inputs(prototype, tmp_path, relative):
    store = Store(prototype/'state/tasks.sqlite3')
    store.close()
    source = prototype/relative
    outside = tmp_path/'outside'
    outside.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(ValueError, match='regular backup input'):
        backup.create(tmp_path/'snapshot')
    assert not (tmp_path/'snapshot').exists()


def journal_record(order_id, status):
    value={'version':1,'order':{'work_order_id':order_id},'owner':'operator',
           'controller':'http://127.0.0.1:8787','submission':status}
    if status=='accepted':value['task_id']='c'*32
    return value


def test_journal_snapshot_restore_prevents_replay(prototype,tmp_path):
    pytest.importorskip('jsonschema')
    from scripts.handoff import Journal, submit
    from scripts.work_orders import HandoffError
    import httpx
    store=Store(prototype/'state/tasks.sqlite3');store.close()
    source=Journal(prototype/'state/handoffs')
    for order_id,status in [('a'*32,'accepted'),('b'*32,'submission_unknown'),('d'*32,'submitting')]:
        source.write(journal_record(order_id,status))
    snapshot=tmp_path/'snapshot'
    assert backup.create(snapshot)['handoff_count']==3
    archive=json.loads((snapshot/'handoffs.json').read_text())
    restored=Journal(tmp_path/'recovered')
    for record in archive['records'].values():restored.write(record)
    with httpx.Client(transport=httpx.MockTransport(lambda request:pytest.fail('must not replay'))) as client:
        for order_id in archive['records']:
            record=restored.read(order_id)
            if record['submission']=='accepted':
                assert submit(record['order'],None,'operator',restored,client,record['controller'])['task_id']=='c'*32
            else:
                with pytest.raises(HandoffError):submit(record['order'],None,'operator',restored,client,record['controller'])
    assert restored.read('d'*32)['submission']=='submission_unknown'


def test_busy_journal_refuses_snapshot(prototype,tmp_path):
    import fcntl
    store=Store(prototype/'state/tasks.sqlite3');store.close()
    root=prototype/'state/handoffs';root.mkdir(mode=0o700)
    with (root/'.lock').open('w') as lock:
        (root/'.lock').chmod(0o600)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(ValueError,match='active'):backup.create(tmp_path/'snapshot')
    assert not (tmp_path/'snapshot').exists()


@pytest.mark.parametrize('mutation',['symlink','permission','hardlink','unexpected','oversized'])
def test_unsafe_journal_rejected(prototype,tmp_path,mutation):
    store=Store(prototype/'state/tasks.sqlite3');store.close()
    root=prototype/'state/handoffs';root.mkdir(mode=0o700)
    path=root/('a'*32+'.json');path.write_text(json.dumps(journal_record('a'*32,'accepted')));path.chmod(0o600)
    if mutation=='symlink':
        outside=tmp_path/'outside';path.rename(outside);path.symlink_to(outside)
    elif mutation=='hardlink':
        import os
        os.link(path,tmp_path/'outside')
    elif mutation=='permission':path.chmod(0o644)
    elif mutation=='oversized':path.write_bytes(b'x'*262145)
    else:(root/'unknown').write_text('unexpected')
    with pytest.raises(ValueError):backup.create(tmp_path/'snapshot')
    assert not (tmp_path/'snapshot').exists()


def test_legacy_snapshot_remains_verifiable(prototype,tmp_path):
    store=Store(prototype/'state/tasks.sqlite3');store.close()
    target=tmp_path/'snapshot';backup.create(target)
    path=target/'manifest.json';manifest=json.loads(path.read_text())
    manifest['version']=1;manifest.pop('handoff_count');manifest['sha256'].pop('handoffs.json')
    (target/'handoffs.json').unlink();path.write_text(json.dumps(manifest))
    assert backup.verify(target)['handoff_count'] is None


def test_journal_checksum_and_count_verification(prototype,tmp_path):
    store=Store(prototype/'state/tasks.sqlite3');store.close()
    target=tmp_path/'snapshot';backup.create(target)
    path=target/'handoffs.json';path.write_text('{}')
    with pytest.raises(ValueError,match='checksum'):backup.verify(target)
    path.write_text(json.dumps({'version':1,'records':{}}))
    manifest_path=target/'manifest.json';manifest=json.loads(manifest_path.read_text())
    manifest['sha256']['handoffs.json']=backup.digest(path);manifest['handoff_count']=1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='count'):backup.verify(target)


def test_bundle_preserves_controller_native_snapshots(prototype,tmp_path):
    store=Store(prototype/'state/tasks.sqlite3')
    order={'work_order_id':'a'*32,'source':{'repository_id':'forge','revision':'b'*40,'files':[]}}
    task=store.create('operator','repository_analyst',(order,{'source.py':'captured\n'}))
    store.update(task,'succeeded',result='preserved')
    target=tmp_path/'snapshot'
    try:assert backup.create(target)['task_count']==1
    finally:store.close()
    import shutil
    recovered=tmp_path/'recovered.sqlite3'
    shutil.copyfile(target/'tasks.sqlite3',recovered)
    restored=Store(recovered)
    try:
        assert restored.get(task)['work_order_id']==order['work_order_id']
        assert restored.has_order('operator',order['work_order_id'])
        assert json.loads(restored.db.execute('SELECT sources_json FROM work_orders').fetchone()[0])=={'source.py':'captured\n'}
    finally:restored.close()
