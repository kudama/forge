"""Queue wait and execution time are separate budgets (v2 SRV-04, MCP-07)."""
import asyncio
import json

import pytest

from forge_controller.config import Settings
from tests.test_controller import FakeModel, client, submit, terminal


class SlowModel(FakeModel):
    def __init__(self, delay):
        super().__init__()
        self.delay = delay

    async def chat(self, messages, tools, *, agent='forge'):
        await asyncio.sleep(self.delay)
        return await super().chat(messages, tools, agent=agent)


async def test_queue_wait_is_not_charged_to_execution_deadline(tmp_path):
    # Three 0.15s tasks run serially under a 0.3s execution limit. The third task
    # waits ~0.3s in the queue; with a queue-inclusive deadline it would have failed.
    async with client(tmp_path, SlowModel(.15), timeout=.3, queue_timeout=30) as (c, app):
        ids = [await submit(c) for _ in range(3)]
        rows = [await terminal(c, task_id) for task_id in ids]
        assert [row['status'] for row in rows] == ['succeeded'] * 3, rows


async def test_queue_expiry_is_distinct_and_never_runs_inference(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake, timeout=5, queue_timeout=.05, capacity=4) as (c, app):
        first = await submit(c)
        await fake.started.wait()
        second = await submit(c)
        await asyncio.sleep(.1)              # second outlives its queue budget
        fake.release.set()
        assert (await terminal(c, first))['status'] == 'succeeded'
        row = await terminal(c, second)
        assert row['status'] == 'failed' and row['error'] == 'queue_expired'
        assert row['audit'] == []            # never reached the running state
        assert fake.calls == 1               # only the first task consumed inference


async def test_execution_deadline_still_enforced_after_dispatch(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake, timeout=.05, queue_timeout=30) as (c, app):
        row = await terminal(c, await submit(c))
        assert row['status'] == 'failed' and row['error'] == 'deadline_exceeded'


async def test_expiry_releases_capacity_while_inference_is_blocked(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake, timeout=5, queue_timeout=.05, capacity=2) as (c, app):
        first = await submit(c)
        await fake.started.wait()
        # Repeat without releasing inference: expired queue entries must not
        # accumulate and fill the physical queue after admission slots are freed.
        for _ in range(4):
            queued = await submit(c)
            row = await terminal(c, queued)
            assert row['error'] == 'queue_expired' and row['audit'] == []
            assert (await c.get('/v1/tasks/' + first)).json()['status'] == 'running'
            assert fake.calls == 1
            assert (await c.delete('/v1/tasks/' + queued)).status_code == 204
        last = await submit(c)
        fake.release.set()
        assert (await terminal(c, first))['status'] == 'succeeded'
        assert (await terminal(c, last))['status'] == 'succeeded'
        assert fake.calls == 2
        await asyncio.wait_for(app.state.engine.queue.join(), timeout=.5)


async def test_expiry_preserves_other_tasks_fifo_order(tmp_path):
    class RecordingModel(FakeModel):
        def __init__(self):
            super().__init__('wait')
            self.prompts = []

        async def chat(self, messages, tools, *, agent='forge'):
            self.prompts.append(messages[-1]['content'])
            return await super().chat(messages, tools, agent=agent)

    fake = RecordingModel()
    async with client(tmp_path, fake, timeout=5, queue_timeout=.3) as (c, app):
        first = await submit(c, prompt='first')
        await fake.started.wait()
        expired = await submit(c, prompt='expired')
        await asyncio.sleep(.2)
        third = await submit(c, prompt='third')
        fourth = await submit(c, prompt='fourth')
        assert (await terminal(c, expired))['error'] == 'queue_expired'
        fake.release.set()
        for task_id in [first, third, fourth]:
            assert (await terminal(c, task_id))['status'] == 'succeeded'
        assert fake.prompts == ['first', 'third', 'fourth']
        await asyncio.wait_for(app.state.engine.queue.join(), timeout=.5)


async def test_dispatched_task_does_not_expire_at_its_old_queue_deadline(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake, timeout=5, queue_timeout=.05) as (c, app):
        task_id = await submit(c)
        await fake.started.wait()
        await asyncio.sleep(.1)
        assert (await c.get('/v1/tasks/' + task_id)).json()['status'] == 'running'
        fake.release.set()
        assert (await terminal(c, task_id))['status'] == 'succeeded'


async def test_expiry_timer_preserves_cancellation_and_stops_on_shutdown(tmp_path):
    fake = FakeModel('wait')
    async with client(tmp_path, fake, timeout=5, queue_timeout=.05) as (c, app):
        await submit(c)
        await fake.started.wait()
        queued = await submit(c)
        await c.post('/v1/tasks/' + queued + '/cancel')
        await asyncio.sleep(.1)
        row = (await c.get('/v1/tasks/' + queued)).json()
        assert row['status'] == 'cancelled' and row['error'] == 'cancelled_by_user'
        pending = await submit(c)
    # Timer callbacks must not access the closed store or overwrite interrupted.
    await asyncio.sleep(.1)
    assert app.state.engine.queue_timers == {}


@pytest.mark.parametrize('value', [0, -1, True, '5', None, float('nan'), float('inf'), -float('inf')])
def test_queue_timeout_must_be_a_positive_number(tmp_path, value):
    principals = {'mike': {'token': 'a' * 40, 'agents': ['forge'], 'services': []}}
    with pytest.raises(ValueError):
        Settings(database=tmp_path / 't.sqlite3', principals=principals, queue_timeout=value)


@pytest.mark.parametrize('env,expected', [(None, 600), ('12.5', 12.5)])
def test_queue_timeout_environment(tmp_path, monkeypatch, env, expected):
    path = tmp_path / 'principals.json'
    path.write_text(json.dumps({'mike': {'token': 'a' * 40, 'agents': ['forge'], 'services': []}}))
    path.chmod(0o600)
    monkeypatch.setenv('FORGE_PRINCIPALS_FILE', str(path))
    monkeypatch.setenv('FORGE_DATABASE', str(tmp_path / 't.sqlite3'))
    if env is None:
        monkeypatch.delenv('FORGE_QUEUE_TIMEOUT', raising=False)
    else:
        monkeypatch.setenv('FORGE_QUEUE_TIMEOUT', env)
    assert Settings.from_environment().queue_timeout == expected


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf'])
def test_nonfinite_environment_queue_timeout_is_rejected(tmp_path, monkeypatch, value):
    path = tmp_path / 'principals.json'
    path.write_text(json.dumps({'mike': {'token': 'a' * 40, 'agents': ['forge'], 'services': []}}))
    path.chmod(0o600)
    monkeypatch.setenv('FORGE_PRINCIPALS_FILE', str(path))
    monkeypatch.setenv('FORGE_QUEUE_TIMEOUT', value)
    with pytest.raises(ValueError, match='queue_timeout'):
        Settings.from_environment()
