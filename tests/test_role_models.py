import asyncio
import json

import httpx
import pytest

from forge_controller.app import create_app
from forge_controller.config import Settings
from forge_controller.model import Ollama, ModelError


def config(tmp_path, **overrides):
    return Settings(database=tmp_path/'tasks.sqlite3', principals={
        'tester': {'token':'t'*40, 'agents':['forge','repository_analyst','implementer'],
                   'services':[], 'repositories':['forge']}},
        repositories={'forge':{'root':str(tmp_path.resolve()), 'files':['source.py']}}, **overrides)


@pytest.mark.parametrize('mapping', [None, [], 'coder', {'unknown':'coder'},
    {'implementer':None}, {'implementer':1}, {'implementer':True},
    {'implementer':''}, {'implementer':' coder'}, {'implementer':'coder\n'}])
def test_invalid_mappings_fail_startup(tmp_path, mapping):
    with pytest.raises(ValueError, match='role model'):
        config(tmp_path, role_models=mapping)


def test_role_defaults_and_overrides(tmp_path):
    settings=config(tmp_path, model='base', role_models={'implementer':'coder'})
    assert settings.model_for('forge')=='base'
    assert settings.model_for('repository_analyst')=='base'
    assert settings.model_for('implementer')=='coder'
    with pytest.raises(ValueError, match='Unknown agent'):
        settings.model_for('arbitrary')


def test_environment_mapping(tmp_path, monkeypatch):
    path=tmp_path/'principals.json'
    path.write_text(json.dumps({'tester':{'token':'t'*40,'agents':['forge'],'services':[]}}))
    path.chmod(0o600)
    monkeypatch.setenv('FORGE_PRINCIPALS_FILE',str(path))
    monkeypatch.delenv('FORGE_REPOSITORIES_FILE',raising=False)
    monkeypatch.delenv('FORGE_ROLE_MODELS',raising=False)
    assert Settings.from_environment().role_models=={}
    monkeypatch.setenv('FORGE_ROLE_MODELS','{"implementer":"coder"}')
    assert Settings.from_environment().model_for('implementer')=='coder'
    monkeypatch.setenv('FORGE_ROLE_MODELS','not json')
    with pytest.raises(ValueError):
        Settings.from_environment()


async def test_readiness_requires_effective_models_and_never_loads(tmp_path):
    settings=config(tmp_path, role_models={'implementer':'coder'})
    adapter=Ollama(settings)
    await adapter.client.aclose()
    names=['qwen3:8b']
    requests=[]
    def respond(request):
        requests.append((request.method,request.url.path))
        return httpx.Response(200,json={'models':[{'name':n} for n in names]})
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(respond))
    try:
        assert not await adapter.ready()
        names.append('coder')
        assert await adapter.ready()
    finally:
        await adapter.close()
    assert requests==[('GET','/api/tags')]*2


async def test_missing_selected_model_has_no_fallback(tmp_path):
    adapter=Ollama(config(tmp_path,role_models={'implementer':'missing'}))
    await adapter.client.aclose()
    requests=[]
    def respond(request):
        requests.append(json.loads(request.content)['model'])
        return httpx.Response(404,json={'error':'missing model'})
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(ModelError,match='model_unavailable'):
            await adapter.chat([],[],agent='implementer')
    finally:
        await adapter.close()
    assert requests==['missing']


async def test_authenticated_roles_route_serially_and_audit_without_using_tool_budget(tmp_path):
    (tmp_path/'source.py').write_text('VALUE = 1\n')
    settings=config(tmp_path,role_models={'implementer':'coder'}, tool_rounds=1)
    adapter=Ollama(settings)
    await adapter.client.aclose()
    requests=[]
    active=peak=0
    async def respond(request):
        nonlocal active, peak
        active+=1
        peak=max(peak,active)
        payload=json.loads(request.content)
        requests.append(payload)
        await asyncio.sleep(.01)
        active-=1
        if payload['tools'] and payload['messages'][-1]['role']!='tool':
            return httpx.Response(200,json={'message':{'content':'','tool_calls':[{'function':{
                'name':'read_repository_file','arguments':{'repository':'forge','path':'source.py','start_line':1,'end_line':1}}}]}})
        return httpx.Response(200,json={'message':{'content':'reviewed source'}})
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(respond))
    app=create_app(settings,adapter)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer '+'t'*40}) as client:
            rejected=await client.post('/v1/tasks',json={'prompt':'x','model':'untrusted'})
            assert rejected.status_code==422
            ids=[]
            for role in ['repository_analyst','implementer','repository_analyst']:
                r=await client.post('/v1/tasks',json={'agent':role,'prompt':'read source','tools':['read_repository_file']})
                assert r.status_code==202
                ids.append(r.json()['id'])
            for task_id, expected in zip(ids,['qwen3:8b','coder','qwen3:8b']):
                for _ in range(200):
                    row=(await client.get('/v1/tasks/'+task_id)).json()
                    if row['status'] in {'succeeded','failed'}:
                        break
                    await asyncio.sleep(.005)
                assert row['status']=='succeeded',row
                selected=[a for a in row['audit'] if a['tool']=='model_selection']
                assert len(selected)==1 and selected[0]['model']==expected
    assert peak==1
    assert [r['model'] for r in requests]==['qwen3:8b']*2+['coder']*2+['qwen3:8b']*2
    assert all(r['options']=={'num_ctx':4096,'num_predict':512,'temperature':0} for r in requests)
