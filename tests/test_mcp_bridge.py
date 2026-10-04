import asyncio
import json

import httpx
import pytest

pytest.importorskip('mcp')
from mcp import Client

from forge_controller.app import create_app
from forge_controller.config import Settings
from forge_controller.mcp_bridge import BridgeSettings, create_bridge
from test_controller import FakeModel


def credential(tmp_path, token='t'*40):
    path=tmp_path/'mcp-token.json'
    path.write_text(json.dumps({'token':token}))
    path.chmod(0o600)
    return path


@pytest.mark.parametrize('url', ['https://example.com','http://example.com','http://127.0.0.1/x',
    'http://user:secret@localhost','http://localhost?token=secret','http://localhost/#x'])
def test_reject_remote_and_credential_urls(tmp_path,url):
    with pytest.raises(ValueError):
        BridgeSettings(credential(tmp_path),url)


def test_private_single_credential(tmp_path):
    path=credential(tmp_path)
    assert BridgeSettings(path).token()=='t'*40
    path.chmod(0o644)
    with pytest.raises(ValueError):BridgeSettings(path).token()
    path.chmod(0o600)
    link=tmp_path/'link';link.symlink_to(path)
    with pytest.raises(ValueError):BridgeSettings(link).token()
    path.write_text(json.dumps({'token':'t'*40,'another_principal':'secret'}))
    with pytest.raises(ValueError):BridgeSettings(path).token()
    path.write_text(json.dumps({'token':'t'*40+'\n'}))
    with pytest.raises(ValueError):BridgeSettings(path).token()
    path.write_bytes(b'x'*4097)
    with pytest.raises(ValueError):BridgeSettings(path).token()


async def test_catalog_validation_and_sanitized_failures(tmp_path):
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(401,text='secret upstream detail')
    async with Client(create_bridge(BridgeSettings(credential(tmp_path)),httpx.MockTransport(respond))) as client:
        tools={t.name:t for t in (await client.list_tools()).tools}
        assert set(tools)=={'forge_health','forge_submit_task','forge_get_task','forge_cancel_task'}
        assert all(t.input_schema['additionalProperties'] is False for t in tools.values())
        assert tools['forge_health'].annotations.read_only_hint is True
        assert tools['forge_submit_task'].annotations.read_only_hint is False
        assert tools['forge_submit_task'].annotations.idempotent_hint is False
        for args in [{'task_id':'../health/ready'},{'task_id':123}]:
            assert (await client.call_tool('forge_get_task',args)).is_error
        for args in [{'prompt':'','agent':'forge'},{'prompt':'x'*8001},
                     {'prompt':'x','agent':'unrestricted'}, {'prompt':'x','tools':['shell']},
                     {'prompt':'x','model':'arbitrary'}]:
            assert (await client.call_tool('forge_submit_task',args)).is_error
        assert not requests
        result=await client.call_tool('forge_health')
        assert result.is_error and 'unauthorized' in str(result.content)
        assert 'secret upstream detail' not in str(result.content)
        assert requests[0].headers['Authorization']=='Bearer '+'t'*40


@pytest.mark.parametrize('status,error', [(403,'permission_denied'),(404,'task_not_found'),
    (409,'task_conflict'),(503,'controller_unavailable'),(302,'controller_request_failed')])
async def test_status_mapping_no_response_leak(tmp_path,status,error):
    transport=httpx.MockTransport(lambda request:httpx.Response(status,text='private detail',headers={'Location':'https://example.com'}))
    async with Client(create_bridge(BridgeSettings(credential(tmp_path)),transport)) as client:
        result=await client.call_tool('forge_get_task',{'task_id':'a'*32})
        assert result.is_error and error in str(result.content)
        assert 'private detail' not in str(result.content)


@pytest.mark.parametrize('kind,error',[('large','controller_response_too_large'),
    ('json','invalid_controller_response'),('timeout','controller_unavailable')])
async def test_bounded_upstream_failures(tmp_path,kind,error):
    def respond(request):
        if kind=='timeout':raise httpx.ReadTimeout('private connection detail')
        return httpx.Response(200,content=b'x'*131073 if kind=='large' else b'not JSON')
    async with Client(create_bridge(BridgeSettings(credential(tmp_path)),httpx.MockTransport(respond))) as client:
        result=await client.call_tool('forge_health')
        assert result.is_error and error in str(result.content)
        assert 'private connection detail' not in str(result.content)


async def test_protocol_to_real_controller_authorization_lifecycle_and_disconnect(tmp_path):
    config=Settings(database=tmp_path/'tasks.sqlite3',principals={
        'bridge':{'token':'t'*40,'agents':['forge'],'services':[]},
        'other':{'token':'o'*40,'agents':['forge'],'services':[]}})
    fake=FakeModel('wait');app=create_app(config,fake)
    async with app.router.lifespan_context(app):
        bridge=create_bridge(BridgeSettings(credential(tmp_path)),httpx.ASGITransport(app=app))
        async with Client(bridge) as client:
            assert not (await client.call_tool('forge_health')).is_error
            denied=await client.call_tool('forge_submit_task',{'prompt':'x','agent':'implementer','tools':['read_repository_file']})
            assert denied.is_error and 'permission_denied' in str(denied.content)
            foreign=app.state.store.create('other','forge')
            assert (await client.call_tool('forge_get_task',{'task_id':foreign})).is_error
            assert (await client.call_tool('forge_cancel_task',{'task_id':foreign})).is_error
            app.state.store.update(foreign,'cancelled')
            submitted=await client.call_tool('forge_submit_task',{'prompt':'wait'})
            task_id=submitted.structured_content['id']
            await fake.started.wait()
        # Closing the MCP session must not silently cancel accepted durable work.
        assert app.state.store.get(task_id)['status']=='running'
        async with Client(bridge) as client:
            task=await client.call_tool('forge_get_task',{'task_id':task_id})
            assert task.structured_content['status']=='running'
            cancelled=await client.call_tool('forge_cancel_task',{'task_id':task_id})
            assert cancelled.structured_content['status']=='cancelled'
            again=await client.call_tool('forge_cancel_task',{'task_id':task_id})
            assert again.structured_content['status']=='cancelled'
            fake.release.set()
            next_task=await client.call_tool('forge_submit_task',{'prompt':'next'})
            next_id=next_task.structured_content['id']
            for _ in range(100):
                row=await client.call_tool('forge_get_task',{'task_id':next_id})
                if row.structured_content['status']=='succeeded':break
                await asyncio.sleep(.01)
            assert row.structured_content['status']=='succeeded'
