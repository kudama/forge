from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

from forge_agent_core.health import Policy, Snapshot, main, read_snapshot, render

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
POLICY = Policy('jarvis', 'primary', frozenset({'data'}), 180)


def snapshot(**updates):
    values = dict(agent_id='jarvis', instance_id='primary', version='0.1.0', observed_at=NOW,
                  alive=True, accepting_work=True, dependencies=(('data', 'ok'),))
    values.update(updates)
    return Snapshot(**values)


def states(output):
    return [int(line.split()[0]) for line in output.splitlines()]


def test_fresh_alive_ready_and_version_without_personal_data():
    output = render(POLICY, snapshot(), now=NOW)
    assert states(output) == [0, 0]
    assert 'heartbeat_age=0' in output and 'version=0.1.0' in output
    assert output.count('\n') == 2 and '<<<' not in output


@pytest.mark.parametrize('dependencies,expected', [
    ((), 3), ((('data', 'unknown'),), 3), ((('data', 'failed'),), 2),
    ((('data', 'degraded'),), 1), ((('data', 'ok'), ('optional', 'failed')), 1),
])
def test_dependency_readiness_never_equals_process_liveness(dependencies, expected):
    output = render(POLICY, snapshot(dependencies=dependencies), now=NOW)
    assert states(output) == [0, expected]


def test_required_dependency_cannot_be_dropped_from_report():
    assert states(render(POLICY, snapshot(dependencies=(('other', 'ok'),)), now=NOW)) == [0, 3]


def test_unavailable_invalid_stale_and_future_never_ok():
    assert states(render(POLICY, now=NOW)) == [3, 3]
    assert states(render(POLICY, now=NOW, unavailable='password=PRIVATE')) == [3, 3]
    assert 'PRIVATE' not in render(POLICY, now=NOW, unavailable='password=PRIVATE')
    assert states(render(POLICY, snapshot(observed_at=NOW-timedelta(seconds=181)), now=NOW)) == [2, 3]
    assert states(render(POLICY, snapshot(observed_at=NOW+timedelta(seconds=31)), now=NOW)) == [3, 3]


def test_age_boundary_and_clock_skew_tolerance():
    assert states(render(POLICY, snapshot(observed_at=NOW-timedelta(seconds=180)), now=NOW)) == [0, 0]
    assert states(render(POLICY, snapshot(observed_at=NOW+timedelta(seconds=30)), now=NOW)) == [0, 0]


def test_wrong_agent_or_instance_is_unknown():
    assert states(render(POLICY, snapshot(agent_id='hermes'), now=NOW)) == [3, 3]
    assert states(render(POLICY, snapshot(instance_id='other'), now=NOW)) == [3, 3]


def test_draining_and_dead_are_distinct():
    assert states(render(POLICY, snapshot(accepting_work=False), now=NOW)) == [0, 1]
    assert states(render(POLICY, snapshot(alive=False), now=NOW)) == [2, 2]


@pytest.mark.parametrize('field,value', [
    ('agent_id', 'jarvis"\n<<<secrets>>>'), ('instance_id', 'private user'),
    ('version', 'version\n0 "Injected" - OK'), ('alive', 1), ('accepting_work', 'yes'),
    ('observed_at', NOW.replace(tzinfo=None)),
    ('dependencies', (('data', 'password=PRIVATE'),)),
    ('dependencies', (('data', 'ok'), ('data', 'failed'))),
])
def test_snapshot_rejects_injection_types_and_duplicate_dependencies(field, value):
    with pytest.raises((ValueError, TypeError)):
        snapshot(**{field: value})


def test_round_trip_and_immutable_dependency_snapshot():
    dependencies = [['data', 'ok']]
    report = snapshot(dependencies=dependencies)
    dependencies[0][1] = 'failed'
    assert report.dependencies == (('data', 'ok'),)
    assert Snapshot.parse(report.to_json()) == report


@pytest.mark.parametrize('mutation', ['secret_field', 'schema_bool', 'duplicate', 'oversize', 'bad_time'])
def test_strict_health_wire_schema(mutation):
    value = snapshot().as_dict()
    if mutation == 'secret_field': value['password'] = 'PRIVATE'
    if mutation == 'schema_bool': value['schema_version'] = True
    if mutation == 'bad_time': value['observed_at'] = 'not-time'
    raw = json.dumps(value)
    if mutation == 'duplicate': raw = '{"schema_version":1,"schema_version":1}'
    if mutation == 'oversize': raw = ' ' * 8193
    with pytest.raises((ValueError, TypeError)):
        Snapshot.parse(raw)


def test_safe_file_reader_and_link_special_file_rejection(tmp_path):
    root = tmp_path.resolve()
    path = root / 'snapshot.json'
    path.write_text(snapshot().to_json()); path.chmod(0o640)
    assert read_snapshot(path) == snapshot()
    alias = root / 'alias'; alias.symlink_to(path)
    with pytest.raises((OSError, ValueError)): read_snapshot(alias)
    directory_alias = root / 'directory'; directory_alias.symlink_to(root, target_is_directory=True)
    with pytest.raises((OSError, ValueError)): read_snapshot(directory_alias / path.name)
    path.chmod(0o644)
    with pytest.raises(ValueError): read_snapshot(path)


def test_cli_invalid_snapshot_outputs_fixed_unknown_without_content(tmp_path, capsys):
    path = tmp_path.resolve() / 'snapshot.json'
    path.write_text('password=PRIVATE'); path.chmod(0o600)
    main(['--agent', 'jarvis', '--instance', 'primary', '--snapshot', str(path), '--require', 'data'])
    output = capsys.readouterr().out
    assert states(output) == [3, 3]
    assert 'PRIVATE' not in output and str(path) not in output


@pytest.mark.parametrize('kind', ['hardlink', 'directory', 'fifo'])
def test_non_regular_or_multiply_linked_snapshot_is_refused(tmp_path, kind):
    path = tmp_path.resolve() / 'snapshot'
    if kind == 'directory':
        path.mkdir()
    elif kind == 'fifo':
        os.mkfifo(path, 0o600)
    else:
        path.write_text(snapshot().to_json()); path.chmod(0o600)
        os.link(path, tmp_path.resolve() / 'second')
    with pytest.raises((OSError, ValueError)):
        read_snapshot(path)


def test_cli_missing_snapshot_never_ok(tmp_path, capsys):
    main(['--agent', 'bear', '--instance', 'primary', '--snapshot', str(tmp_path.resolve() / 'missing')])
    assert states(capsys.readouterr().out) == [3, 3]


def test_cli_bad_configuration_is_sanitized_unknown(capsys):
    main(['--agent', 'secret\n<<<injection>>>', '--instance', 'primary', '--snapshot', '/unused', '--max-age', '0'])
    output = capsys.readouterr().out
    assert states(output) == [3] and 'injection' not in output


def test_policy_is_snapshot_and_limits_are_positive():
    values = ['data']; policy = Policy('jarvis', 'primary', values)
    values.clear()
    assert policy.required_dependencies == frozenset({'data'})
    with pytest.raises(ValueError): Policy('jarvis', 'primary', max_age_seconds=0)
    with pytest.raises(ValueError): Policy('jarvis', 'primary', max_age_seconds=True)


def test_all_six_peers_use_same_collector_without_model_dependency():
    for agent in ('jarvis', 'citadel', 'forge', 'thoth', 'hermes', 'bear'):
        policy = Policy(agent, 'primary')
        assert states(render(policy, snapshot(agent_id=agent, dependencies=()), now=NOW)) == [0, 0]
