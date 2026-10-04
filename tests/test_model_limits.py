import json

import httpx
import pytest

from forge_controller.config import Settings
from forge_controller.model import Ollama


def make_settings(tmp_path, **overrides):
    return Settings(database=tmp_path/'tasks.sqlite3', principals={
        'tester': {'token': 't'*40, 'agents': ['forge'], 'services': []}}, **overrides)


@pytest.mark.parametrize('models', [None, 'unexpected', [None], [123], [{'name':[]}], [{'name':None}], [{}],
    [{'name':'qwen3:8b'},None], [{'name':'qwen3:8b'},{'name':[]}], []])
async def test_readiness_rejects_malformed_models(tmp_path, models):
    adapter=Ollama(make_settings(tmp_path))
    await adapter.client.aclose()
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'models':models})))
    try:
        assert await adapter.ready() is False
    finally:
        await adapter.close()


@pytest.mark.parametrize('installed,ready', [(['qwen3:8b'],False),(['qwen3:8b','qwen3-coder:30b'],True)])
async def test_readiness_requires_all_role_models(tmp_path,installed,ready):
    adapter=Ollama(make_settings(tmp_path,role_models={'implementer':'qwen3-coder:30b'}))
    await adapter.client.aclose()
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'models':[{'name':name} for name in installed]})))
    try:
        assert await adapter.ready() is ready
    finally:
        await adapter.close()


@pytest.mark.parametrize('overrides,context,output', [
    ({},4096,512),
    ({'context_length':8192,'max_output_tokens':1024},8192,1024),
    ({'context_length':2048},2048,512),
    ({'max_output_tokens':128},4096,128),
])
async def test_outgoing_payload_limits(tmp_path, overrides, context, output):
    adapter=Ollama(make_settings(tmp_path,**overrides))
    await adapter.client.aclose()
    captured=[]
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':'ok'}})
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(respond))
    try:
        assert (await adapter.chat([{'role':'user','content':'test'}],[]))['content']=='ok'
    finally:
        await adapter.close()
    assert captured[0]['options']=={'num_ctx':context,'num_predict':output,'temperature':0}
    assert captured[0]['think'] is False
    assert captured[0]['stream'] is False
    assert captured[0]['model']=='qwen3:8b'
    assert captured[0]['keep_alive']=='5m'


@pytest.mark.parametrize('field',['context_length','max_output_tokens'])
@pytest.mark.parametrize('value',[0,-1,1.5,True,False,'4096',None])
def test_rejects_invalid_programmatic_limits(tmp_path,field,value):
    with pytest.raises(ValueError):
        make_settings(tmp_path,**{field:value})


@pytest.fixture
def private_environment(tmp_path,monkeypatch):
    config=tmp_path/'principals.json'
    config.write_text(json.dumps({'tester':{'token':'t'*40,'agents':['forge'],'services':[]}}))
    config.chmod(0o600)
    monkeypatch.setenv('FORGE_PRINCIPALS_FILE',str(config))
    monkeypatch.delenv('FORGE_REPOSITORIES_FILE',raising=False)
    monkeypatch.delenv('FORGE_CONTEXT_LENGTH',raising=False)
    monkeypatch.delenv('FORGE_MAX_OUTPUT_TOKENS',raising=False)
    return monkeypatch


@pytest.mark.parametrize('overridden',[False,True])
def test_environment_defaults_and_overrides(private_environment,overridden):
    if overridden:
        private_environment.setenv('FORGE_CONTEXT_LENGTH','8192')
        private_environment.setenv('FORGE_MAX_OUTPUT_TOKENS','1024')
    settings=Settings.from_environment()
    assert settings.context_length==(8192 if overridden else 4096)
    assert settings.max_output_tokens==(1024 if overridden else 512)


@pytest.mark.parametrize('variable',['FORGE_CONTEXT_LENGTH','FORGE_MAX_OUTPUT_TOKENS'])
@pytest.mark.parametrize('value',['0','-1','1.5','true','abc',''])
def test_environment_rejects_invalid_limits(private_environment,variable,value):
    private_environment.setenv(variable,value)
    with pytest.raises(ValueError):
        Settings.from_environment()


@pytest.mark.parametrize('message', [{}, {'content':''}, {'content':' \n\t'},
    {'content':'','tool_calls':[]}, {'content':None}, {'content':123},
    {'content':'','tool_calls':'invented'}, {'content':'','tool_calls':{}},
    {'content':'','tool_calls':None}, {'content':'','tool_calls':1},
    {'content':'valid','tool_calls':'invalid'}, []])
async def test_reject_empty_or_invalid_final_response(tmp_path,message):
    from forge_controller.model import ModelError
    adapter=Ollama(make_settings(tmp_path))
    await adapter.client.aclose()
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'message':message})))
    try:
        with pytest.raises(ModelError,match='^invalid_model_response$'):
            await adapter.chat([{'role':'user','content':'test'}],[])
    finally:
        await adapter.close()


@pytest.mark.parametrize('message', [{'content':'valid'}, {'content':' valid\n'},
    {'content':'','tool_calls':[{'function':{'name':'read_repository_file','arguments':{}}}]},
    {'tool_calls':[{'function':{'name':'read_repository_file','arguments':{}}}]}])
async def test_preserve_valid_final_and_tool_only_response(tmp_path,message):
    adapter=Ollama(make_settings(tmp_path))
    await adapter.client.aclose()
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'message':message})))
    try:
        assert await adapter.chat([{'role':'user','content':'test'}],[])==message
    finally:
        await adapter.close()


@pytest.mark.parametrize('message',[{}, {'content':' \n'}])
async def test_empty_response_fails_controller_task(tmp_path,message):
    from forge_controller.app import create_app
    from test_controller import terminal
    settings=make_settings(tmp_path)
    adapter=Ollama(settings)
    await adapter.client.aclose()
    adapter.client=httpx.AsyncClient(base_url='http://model',transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'message':message})))
    app=create_app(settings,adapter)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://controller',
            headers={'Authorization':'Bearer '+'t'*40}) as client:
            submitted=await client.post('/v1/tasks',json={'prompt':'test'})
            assert submitted.status_code==202
            row=await terminal(client,submitted.json()['id'])
            assert row['status']=='failed' and row['error']=='invalid_model_response'
            assert row['result'] is None
