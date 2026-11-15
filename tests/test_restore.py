import json
from pathlib import Path
import sqlite3

import pytest

from forge_controller.store import Store
from scripts import backup
from scripts.restore import restore


@pytest.fixture
def migration(tmp_path, monkeypatch):
    source = tmp_path/'source'; source.mkdir()
    private = source/'.secrets'; private.mkdir(mode=0o700)
    config = {'FORGE_DATABASE': 'state/tasks.sqlite3',
              'FORGE_PRINCIPALS_FILE': '.secrets/principals.json',
              'FORGE_REPOSITORIES_FILE': '.secrets/repositories.json',
              'FORGE_EXAMPLES_FILE': 'reviewed.json'}
    principals = {'operator': {'token': 't'*40, 'agents': ['forge'],
                              'services': ['prototype'], 'repositories': ['forge', 'missing']}}
    repositories = {name: {'root': str(source), 'files': ['README.md']}
                    for name in ('forge', 'missing')}
    for name, value in [('local-controller.json', config), ('principals.json', principals),
                        ('repositories.json', repositories), ('mcp-token.json', {'token': 't'*40})]:
        path = private/name; path.write_text(json.dumps(value)); path.chmod(0o600)
    (source/'reviewed.json').write_text('[]')
    for name in ('requirements.lock', 'requirements-mcp.lock', 'pyproject.toml'):
        (source/name).write_text('fixture')
    monkeypatch.setattr(backup, 'ROOT', source)
    monkeypatch.setattr(backup.subprocess, 'check_output', lambda *a, **k: 'a'*40)
    store = Store(source/'state/tasks.sqlite3')
    task = store.create('operator', 'forge'); store.update(task, 'succeeded', result='history')
    store.close()
    journal = source/'state/handoffs'; journal.mkdir(mode=0o700)
    for index, status in enumerate(('accepted', 'submission_unknown', 'submitting')):
        order_id = str(index)*32
        record = {'version': 1, 'order': {'work_order_id': order_id}, 'owner': 'operator',
                  'controller': 'http://127.0.0.1:8787', 'submission': status}
        if status == 'accepted':
            record['task_id'] = task
        path = journal/(order_id+'.json'); path.write_text(json.dumps(record)); path.chmod(0o600)
    snapshot = tmp_path/'snapshot'; backup.create(snapshot)
    target = tmp_path/'target'; target.mkdir(); (target/'README.md').write_text('source')
    return snapshot, target


def test_restore_preserves_tokens_database_receipts_and_original_snapshot(migration):
    snapshot, target = migration
    before = {p.name: p.read_bytes() for p in snapshot.iterdir()}
    result = restore(snapshot, target, {'forge': target})
    assert result['task_count'] == 1 and result['handoff_count'] == 3
    assert result['disabled_repositories'] == ['missing']
    assert not result['services_started']
    private = target/'.secrets'
    principals = json.loads((private/'principals.json').read_text())
    assert principals['operator']['token'] == 't'*40
    assert principals['operator']['repositories'] == ['forge']
    assert (private/'mcp-token.json').read_bytes() == (snapshot/'mcp-token.json').read_bytes()
    manifest = json.loads((private/'repositories.json').read_text())
    assert manifest == {'forge': {'root': str(target), 'files': ['README.md']}}
    config = json.loads((private/'local-controller.json').read_text())
    assert config['FORGE_DATABASE'] == str(target/'state/tasks.sqlite3')
    with sqlite3.connect(target/'state/tasks.sqlite3') as db:
        assert db.execute('SELECT result FROM tasks').fetchone() == ('history',)
    archive = json.loads((snapshot/'handoffs.json').read_text())
    for order_id, record in archive['records'].items():
        assert json.loads((target/'state/handoffs'/(order_id+'.json')).read_text()) == record
    assert all(p.stat().st_mode & 0o077 == 0 for p in private.iterdir())
    assert before == {p.name: p.read_bytes() for p in snapshot.iterdir()}
    with pytest.raises(ValueError, match='preserving'):
        restore(snapshot, target, {'forge': target})


@pytest.mark.parametrize('existing', ['.secrets', 'state', 'symlink'])
def test_existing_state_is_never_merged(migration, existing):
    snapshot, target = migration
    if existing == 'symlink':
        (target/'.secrets').symlink_to(target/'nonexistent')
    else:
        (target/existing).mkdir()
    with pytest.raises(ValueError, match='preserving'):
        restore(snapshot, target, {'forge': target})


@pytest.mark.parametrize('failure', ['checksum', 'new_grant', 'missing_root', 'invalid_principal', 'tls'])
def test_invalid_restore_never_publishes_partial_state(migration, failure):
    snapshot, target = migration
    mapping = {'forge': target}; listener = None
    if failure == 'checksum':
        (snapshot/'principals.json').write_text('{}')
    elif failure == 'new_grant':
        mapping['unknown'] = target
    elif failure == 'missing_root':
        mapping['forge'] = target/'absent'
    elif failure == 'invalid_principal':
        path = snapshot/'principals.json'; path.write_text('{}')
        manifest = json.loads((snapshot/'manifest.json').read_text())
        manifest['sha256']['principals.json'] = backup.digest(path)
        (snapshot/'manifest.json').write_text(json.dumps(manifest))
    else:
        listener = {'FORGE_LISTEN_HOST': '10.0.0.106'}
    with pytest.raises(ValueError):
        restore(snapshot, target, mapping, listener)
    assert not (target/'.secrets').exists() and not (target/'state').exists()
    assert not list(target.glob('.forge-restore-*'))
