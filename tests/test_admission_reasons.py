"""Work-order admission failures say why (MCP-07) without echoing arbitrary text."""
import hashlib

import httpx
import pytest

pytest.importorskip('mcp')
from mcp import Client

import forge_controller.app as controller_app
from forge_controller.mcp_bridge import BridgeSettings, create_bridge
from forge_controller.work_orders import HandoffError
from tests.test_mcp_bridge import credential
from tests.test_native_work_orders import Worker, assignment, instance  # noqa: F401
from tests.test_line_model import commit
from tests.test_work_orders import assignment as source_assignment  # noqa: F401  (fixture dependency)


def mutate(case, root, settings, order):
    if case == 'unknown_field':
        order['extra'] = True
    elif case == 'hash':
        order['source']['files'][0]['sha256'] = '0' * 64
    elif case == 'revision':
        order['source']['revision'] = '0' * 40
    elif case == 'limits':
        order['runtime_limits']['output_tokens'] += 1
    elif case == 'scope':
        settings.principals['operator']['repositories'] = []
    elif case == 'tools':
        order['tools'] = ['execute_commands']
    elif case == 'crlf':
        data = b'a\r\nb\r\n'
        order['source']['revision'] = commit(root, data)
        order['source']['files'][0]['sha256'] = hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize('case,reason', [
    ('unknown_field', 'invalid_work-order'), ('tools', 'invalid_work-order'),
    ('hash', 'source_hash_mismatch'), ('revision', 'stale_revision'),
    ('limits', 'runtime_limits_mismatch'), ('scope', 'scope_denied'),
    ('crlf', 'unsupported_line_endings')])
async def test_admission_failure_reports_its_reason(assignment, case, reason):  # noqa: F811
    root, settings, order, result, _ = assignment
    mutate(case, root, settings, order)
    model = Worker(result)
    async with instance(settings, model) as (client, app):
        response = await client.post('/v1/work-orders', json=order)
        assert response.status_code == 422
        assert response.json() == {'detail': 'invalid_work_order', 'reason': reason}
        assert not model.started.is_set()
        assert app.state.store.db.execute('SELECT count(*) FROM tasks').fetchone()[0] == 0


@pytest.mark.parametrize('error', [KeyError('private-key'), ValueError('private detail'),
                                    HandoffError('free text with spaces & private detail'),
                                    HandoffError('x' * 65), HandoffError('UPPER_CASE')])
async def test_only_well_formed_codes_are_echoed(assignment, monkeypatch, error):  # noqa: F811
    _, settings, order, result, _ = assignment

    def boom(*args, **kwargs):
        raise error
    monkeypatch.setattr(controller_app, 'preflight', boom)
    async with instance(settings, Worker(result)) as (client, app):
        response = await client.post('/v1/work-orders', json=order)
        assert response.status_code == 422
        assert response.json() == {'detail': 'invalid_work_order'}
        assert 'private' not in response.text


def bridge_for(tmp_path, status, content):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, content=content))
    return Client(create_bridge(BridgeSettings(credential(tmp_path)), transport))


async def submit(client):
    return await client.call_tool('forge_submit_work_order', {'order': {'any': 'thing'}})


async def test_bridge_passes_a_well_formed_reason_through(tmp_path):
    body = b'{"detail":"invalid_work_order","reason":"stale_revision"}'
    async with bridge_for(tmp_path, 422, body) as client:
        result = await submit(client)
        assert result.is_error and 'invalid_request: stale_revision' in str(result.content)


@pytest.mark.parametrize('body', [
    b'{"detail":"invalid_work_order","reason":"has spaces and private detail"}',
    b'{"detail":"invalid_work_order","reason":["stale_revision"]}',
    b'{"detail":"something_else","reason":"stale_revision"}',
    b'{"detail":"invalid_work_order","reason":"' + b'x' * 2000 + b'"}',
    b'not json', b'[1,2]', b'private detail'])
async def test_bridge_never_leaks_unbounded_upstream_text(tmp_path, body):
    async with bridge_for(tmp_path, 422, body) as client:
        result = await submit(client)
        text = str(result.content)
        assert result.is_error and 'invalid_request' in text
        assert 'private' not in text and 'spaces' not in text and 'stale_revision' not in text
        assert 'xxxx' not in text


async def test_bridge_403_source_reads_required_is_unchanged(tmp_path):
    async with bridge_for(tmp_path, 403, b'{"detail":"source_reads_required"}') as client:
        result = await client.call_tool('forge_submit_task', {'prompt': 'x', 'agent': 'implementer'})
        assert result.is_error and 'source_reads_required' in str(result.content)
