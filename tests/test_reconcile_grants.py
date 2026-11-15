import hashlib
import json
from pathlib import Path

import httpx
import pytest

from scripts import backup
from scripts.restore import restore
from scripts.reconcile_grants import reconcile
from scripts.check_source_access import check, ready
from forge_controller.store import Store
from forge_controller.tools import ToolDenied


@pytest.fixture
def deployment(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir()
    private=source/'.secrets';private.mkdir(mode=0o700)
    config={'FORGE_DATABASE':'state/tasks.sqlite3','FORGE_PRINCIPALS_FILE':'.secrets/principals.json',
            'FORGE_REPOSITORIES_FILE':'.secrets/repositories.json','FORGE_EXAMPLES_FILE':'reviewed.json'}
    grants={'operator':{'token':'t'*40,'agents':['forge','repository_analyst'],
                        'services':['prototype'],'repositories':['forge','app']}}
    repos={name:{'root':str(source),'files':['README.md']} for name in ('forge','app')}
    for name,value in [('local-controller.json',config),('principals.json',grants),
                       ('repositories.json',repos),('mcp-token.json',{'token':'t'*40})]:
        p=private/name;p.write_text(json.dumps(value));p.chmod(0o600)
    for name in ('requirements.lock','requirements-mcp.lock','pyproject.toml'):
        (source/name).write_text('fixture')
    (source/'reviewed.json').write_text('[]')
    store=Store(source/'state/tasks.sqlite3');store.close()
    monkeypatch.setattr(backup,'ROOT',source)
    monkeypatch.setattr(backup.subprocess,'check_output',lambda *a,**k:'a'*40)
    snapshot=tmp_path/'snapshot';backup.create(snapshot)
    target=tmp_path/'target';target.mkdir();(target/'README.md').write_text('forge\n')
    restore(snapshot,target,{'forge':target})
    app=tmp_path/'app';app.mkdir();(app/'README.md').write_text('application\n')
    return snapshot,target,app


def test_dry_run_apply_backup_idempotence_and_credential_preservation(deployment):
    snapshot,target,app=deployment
    p=target/'.secrets/principals.json';r=target/'.secrets/repositories.json'
    before_p=p.read_bytes();before_r=r.read_bytes()
    plan=reconcile(snapshot,target,{'app':app})
    assert plan['validated'] and not plan['applied'] and plan['source_files_checked']==1
    assert (p.read_bytes(),r.read_bytes())==(before_p,before_r)
    applied=reconcile(snapshot,target,{'app':app},True)
    assert applied['applied'] and not applied['credentials_changed']
    saved=Path(applied['backup_directory'])
    assert (saved/'principals.json').read_bytes()==before_p
    assert (saved/'repositories.json').read_bytes()==before_r
    principal=json.loads(p.read_text())['operator']
    assert principal['token']=='t'*40 and principal['repositories']==['forge','app']
    assert p.stat().st_mode&0o077==0 and r.stat().st_mode&0o077==0
    assert not reconcile(snapshot,target,{'app':app},True)['changed']


@pytest.mark.parametrize('failure',['unknown','rotated','symlink','missing','oversized','revocation'])
def test_refuses_unsafe_or_changed_state_without_writing(deployment,failure):
    snapshot,target,app=deployment
    principal=target/'.secrets/principals.json';repository=target/'.secrets/repositories.json'
    mappings={'app':app}
    if failure=='unknown':mappings={'unapproved':app}
    elif failure=='rotated':
        value=json.loads(principal.read_text());value['operator']['token']='x'*40
        principal.write_text(json.dumps(value))
    elif failure=='missing':(app/'README.md').unlink()
    elif failure=='symlink':
        (app/'README.md').unlink();(app/'README.md').symlink_to(target/'README.md')
    elif failure=='oversized':(app/'README.md').write_text('x'*65537)
    else:
        value=json.loads(repository.read_text());value['app']={'root':str(app),'files':['README.md']}
        repository.write_text(json.dumps(value))
    before=(principal.read_bytes(),repository.read_bytes())
    with pytest.raises((ValueError,ToolDenied)):
        reconcile(snapshot,target,mappings,True)
    assert before==(principal.read_bytes(),repository.read_bytes())
    assert not list((target/'.secrets').glob('grants-before-*'))


def test_source_probe_requires_matching_allowed_read_audit(capsys):
    def transport(request):
        if request.method=='POST':return httpx.Response(202,json={'id':'a'*32})
        return httpx.Response(200,json={'status':'succeeded','audit':[{
            'tool':'read_repository_file','status':'allowed','repository':'app','path':'README.md'}]})
    with httpx.Client(base_url='https://test',transport=httpx.MockTransport(transport)) as client:
        assert check(client,'app','README.md')['source_read_verified']
    assert 'content' not in capsys.readouterr().out
    with httpx.Client(base_url='https://test',transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ValueError):check(client,'another','README.md')


def test_restart_wait_retries_readiness_without_submitting(monkeypatch):
    calls=[]
    monkeypatch.setattr('scripts.check_source_access.time.sleep',lambda delay:None)
    def handle(request):
        assert request.method=='GET'
        calls.append(request)
        if not request.headers.get('Authorization'):return httpx.Response(401)
        return httpx.Response(503 if len(calls)==2 else 200)
    with httpx.Client(base_url='https://test',headers={'Authorization':'Bearer private'},
                      transport=httpx.MockTransport(handle)) as client:
        ready(client)
    assert len(calls)==4
