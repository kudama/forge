import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from forge_controller.app import create_app
from forge_controller.config import Settings
from forge_controller.store import Store

TOKEN = 'a' * 40
OTHER = 'b' * 40


class FakeModel:
    def __init__(self, mode='success'):
        self.mode = mode
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def ready(self):
        return self.mode != 'unavailable'

    async def close(self):
        pass

    async def chat(self, messages, tools):
        self.calls += 1
        self.started.set()
        if self.mode == 'wait':
            await self.release.wait()
        if self.mode in {'tool', 'bad_tool', 'loop'} and (messages[-1]['role'] != 'tool' or self.mode == 'loop'):
            return {'content': '', 'tool_calls': [{'function': {'name': 'get_service_status', 'arguments': {'service': 'private'} if self.mode == 'bad_tool' else {'service': 'prototype'}}}]}
        return {'content': 'synthetic healthy' if messages[-1]['role'] == 'tool' else 'done'}


@asynccontextmanager
async def client(tmp_path, fake=None, **limits):
    grants = {'mike': {'token': TOKEN, 'agents': ['forge'], 'services': ['prototype']},
              'other': {'token': OTHER, 'agents': ['forge'], 'services': []}}
    settings = Settings(database=tmp_path/'tasks.sqlite3', principals=grants, **limits)
    app = create_app(settings, fake or FakeModel())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'Authorization': 'Bearer ' + TOKEN}) as c:
            yield c, app


async def submit(c, **extra):
    response = await c.post('/v1/tasks', json={'prompt': 'test', **extra})
    assert response.status_code == 202, response.text
    return response.json()['id']


async def terminal(c, task_id):
    for _ in range(200):
        row = (await c.get('/v1/tasks/' + task_id)).json()
        if row['status'] in {'succeeded', 'failed', 'cancelled'}:
            return row
        await asyncio.sleep(.005)
    raise AssertionError('task did not finish')


async def test_auth_and_owner_isolation(tmp_path):
    async with client(tmp_path) as (c, app):
        assert (await c.get('/health/live', headers={'Authorization': ''})).status_code == 200
        assert (await c.post('/v1/tasks', json={'prompt': 'x'}, headers={'Authorization': ''})).status_code == 401
        task_id = await submit(c)
        assert (await terminal(c, task_id))['status'] == 'succeeded'
        for path in ['/v1/tasks/' + task_id, '/v1/tasks/' + task_id + '/cancel']:
            response = await (c.post(path, headers={'Authorization': 'Bearer ' + OTHER}) if path.endswith('cancel') else c.get(path, headers={'Authorization': 'Bearer ' + OTHER}))
            assert response.status_code == 404


async def test_input_and_submission_grants(tmp_path):
    async with client(tmp_path) as (c, app):
        for payload in [{'prompt': ''}, {'prompt': 'x', 'owner': 'other'}, {'prompt': 'x'*8001}]:
            assert (await c.post('/v1/tasks', json=payload)).status_code == 422
        assert (await c.post('/v1/tasks', json={'prompt': 'x', 'agent': 'jarvis'})).status_code == 403
        assert (await c.post('/v1/tasks', json={'prompt': 'x', 'tools': ['shell']})).status_code == 403
        assert (await c.post('/v1/tasks', json={'prompt': 'x', 'tools': ['get_service_status']}, headers={'Authorization': 'Bearer ' + OTHER})).status_code == 403


async def test_scoped_tool_and_audit(tmp_path):
    async with client(tmp_path, FakeModel('tool')) as (c, app):
        row = await terminal(c, await submit(c, tools=['get_service_status']))
        assert row['status'] == 'succeeded'
        assert row['audit'] == [{'tool': 'get_service_status', 'status': 'allowed'}]


@pytest.mark.parametrize('mode,tools', [('bad_tool', ['get_service_status']), ('tool', [])])
async def test_model_cannot_expand_permissions(tmp_path, mode, tools):
    async with client(tmp_path, FakeModel(mode)) as (c, app):
        row = await terminal(c, await submit(c, tools=tools))
        assert row['status'] == 'failed'
        assert row['error'] == 'tool_denied'
        assert row['audit'][0]['status'] == 'denied'


async def test_loop_bound(tmp_path):
    async with client(tmp_path, FakeModel('loop'), tool_rounds=2) as (c, app):
        row = await terminal(c, await submit(c, tools=['get_service_status']))
        assert row['error'] == 'tool_limit_exceeded'
        assert len(row['audit']) == 2


async def test_cancel_does_not_kill_worker(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake) as (c, app):
        task_id = await submit(c)
        await fake.started.wait()
        assert (await c.post('/v1/tasks/' + task_id + '/cancel')).json()['status'] == 'cancelled'
        fake.release.set()
        assert (await terminal(c, await submit(c)))['status'] == 'succeeded'
        assert (await c.get('/v1/tasks/' + task_id)).json()['status'] == 'cancelled'


async def test_capacity_timeout_and_queue_deadline(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake, capacity=2, timeout=.05) as (c, app):
        first = await submit(c)
        await fake.started.wait()
        second = await submit(c)
        assert (await c.post('/v1/tasks', json={'prompt': 'x'})).status_code == 503
        assert (await terminal(c, first))['error'] == 'deadline_exceeded'
        assert (await terminal(c, second))['error'] == 'deadline_exceeded'


async def test_readiness(tmp_path):
    async with client(tmp_path, FakeModel('unavailable')) as (c, app):
        assert (await c.get('/health/ready')).status_code == 503
        assert (await c.get('/health/live')).status_code == 200


def test_recovery_and_exclusive_database(tmp_path):
    path = tmp_path/'tasks.sqlite3'
    store = Store(path)
    pending = store.create('mike', 'forge')
    complete = store.create('mike', 'forge')
    store.update(complete, 'succeeded', result='retained')
    with pytest.raises(RuntimeError):
        Store(path)
    store.close()
    recovered = Store(path)
    assert recovered.get(pending)['error'] == 'interrupted'
    assert recovered.get(complete)['result'] == 'retained'
    recovered.close()


async def test_shutdown_marks_interrupted(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake) as (c, app):
        task_id = await submit(c)
        await fake.started.wait()
    store = Store(tmp_path/'tasks.sqlite3')
    assert store.get(task_id)['error'] == 'interrupted'
    store.close()


def test_secret_permissions_and_invalid_config(tmp_path, monkeypatch):
    path = tmp_path/'principals.json'
    path.write_text('{"mike":{"token":"' + TOKEN + '","agents":["forge"],"services":[]}}')
    path.chmod(0o644)
    monkeypatch.setenv('FORGE_PRINCIPALS_FILE', str(path))
    with pytest.raises(ValueError):
        Settings.from_environment()
    path.chmod(0o600)
    assert Settings.from_environment().principals['mike']['services'] == []


async def test_body_limit_and_delete(tmp_path):
    async with client(tmp_path) as (c, app):
        assert (await c.post('/v1/tasks', content=b'x'*32769)).status_code == 413
        task_id = await submit(c)
        await terminal(c, task_id)
        assert (await c.delete('/v1/tasks/' + task_id, headers={'Authorization': 'Bearer ' + OTHER})).status_code == 404
        assert (await c.delete('/v1/tasks/' + task_id)).status_code == 204
        assert (await c.get('/v1/tasks/' + task_id)).status_code == 404


async def test_queued_cancellation_and_delete_guard(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake) as (c, app):
        first = await submit(c)
        await fake.started.wait()
        second = await submit(c)
        assert (await c.delete('/v1/tasks/' + first)).status_code == 409
        await c.post('/v1/tasks/' + second + '/cancel')
        assert (await c.delete('/v1/tasks/' + second)).status_code == 409
        fake.release.set()
        await terminal(c, first)
        await asyncio.sleep(.01)
        assert fake.calls == 1
        assert (await c.get('/v1/tasks/' + second)).json()['status'] == 'cancelled'


async def test_adapter_errors_and_limits(tmp_path):
    from forge_controller.model import Ollama, ModelError
    settings = Settings(database=tmp_path/'x', principals={'mike': {'token': TOKEN, 'agents': ['forge'], 'services': []}})
    adapter = Ollama(settings)
    await adapter.client.aclose()
    for response, expected in [(httpx.Response(503), 'model_unavailable'),
                               (httpx.Response(200, content='not json'), 'model_unavailable'),
                               (httpx.Response(200, content='x'*65537), 'model_response_too_large')]:
        adapter.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response), base_url='http://model')
        with pytest.raises(ModelError, match=expected):
            await adapter.chat([], [])
        await adapter.close()


async def test_worker_survives_model_error(tmp_path):
    from forge_controller.model import ModelError
    class Flaky(FakeModel):
        async def chat(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                raise ModelError('model_unavailable')
            return {'content': 'recovered'}
    async with client(tmp_path, Flaky()) as (c, app):
        assert (await terminal(c, await submit(c)))['error'] == 'model_unavailable'
        assert (await terminal(c, await submit(c)))['result'] == 'recovered'


def test_consistent_backup_restore_and_future_schema(tmp_path):
    import sqlite3
    path = tmp_path/'source.sqlite3'
    store = Store(path)
    task_id = store.create('mike', 'forge')
    store.update(task_id, 'succeeded', result='backup result')
    target = tmp_path/'restore.sqlite3'
    with sqlite3.connect(target) as backup:
        store.db.backup(backup)
    restored = Store(target)
    assert restored.get(task_id)['result'] == 'backup result'
    restored.db.execute('PRAGMA user_version=2')
    restored.close()
    with pytest.raises(RuntimeError, match='Unsupported database schema'):
        Store(target)
    store.close()
