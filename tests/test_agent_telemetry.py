from datetime import datetime, timezone
import json
import os

import pytest

from forge_agent_core.health import Snapshot, read_snapshot
from forge_agent_core.telemetry import Report, Target, collect, export, main, parse_row, publish

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def report(metrics=(), **updates):
    health = dict(agent_id='jarvis', instance_id='primary', version='0.1.0', observed_at=NOW,
                  alive=True, accepting_work=True, dependencies=(('data', 'ok'),))
    health.update(updates)
    return Report(Snapshot(**health), 300, metrics)


def test_publish_collect_wire_round_trip_and_private_permissions(tmp_path):
    path = tmp_path.resolve() / 'telemetry.json'
    value = report((('queue_depth', 0), ('response_p95_seconds', 0.2)))
    publish(path, value)
    assert path.stat().st_mode & 0o007 == 0
    assert read_snapshot(path, parser=Report.parse) == value
    text = export([Target('jarvis', 'primary', str(path))])
    assert text.splitlines()[0] == '<<<forge_agents:sep(0)>>>'
    item, (status, parsed) = parse_row(text.splitlines()[1])
    assert item == 'jarvis/primary' and status == 'ok' and parsed == value
    publish(path, report((('queue_depth', 1),)))
    assert dict(read_snapshot(path, parser=Report.parse).metrics) == {'queue_depth': 1}
    assert list(path.parent.iterdir()) == [path]


def test_missing_and_invalid_producer_always_export_expected_identity(tmp_path):
    path = tmp_path.resolve() / 'missing'
    target = Target('hermes', 'primary', str(path))
    assert collect(target) == dict(agent_id='hermes', instance_id='primary', status='unavailable', report=None)
    path.write_text('password=PRIVATE'); path.chmod(0o600)
    assert collect(target)['status'] == 'invalid'
    assert 'PRIVATE' not in export([target])
    publish(path, report())
    assert collect(target)['status'] == 'invalid'  # wrong identity


@pytest.mark.parametrize('metric,value', [
    ('queue_depth', True), ('queue_depth', 1.5), ('queue_depth', -1),
    ('input_tokens', 10**15+1), ('capacity_used_percent', 101),
    ('hosted_cost_usd', float('nan')), ('inference_seconds', float('inf')),
    ('private_prompt', 1), ('response_p95_seconds', 'SECRET'),
])
def test_metrics_are_finite_bounded_typed_and_allowlisted(metric, value):
    with pytest.raises((ValueError, TypeError)):
        report(((metric, value),))


def test_no_duplicate_metric_or_inverted_percentiles():
    with pytest.raises(ValueError): report((('queue_depth', 0), ('queue_depth', 1)))
    with pytest.raises(ValueError): report((('response_median_seconds', 10), ('response_p95_seconds', 1)))


@pytest.mark.parametrize('mutation', ['extra', 'schema', 'duplicate', 'oversize', 'metrics', 'nested'])
def test_report_rejects_bad_wire(mutation):
    value = report().as_dict()
    if mutation == 'extra': value['secret'] = 'PRIVATE'
    if mutation == 'schema': value['schema_version'] = True
    if mutation == 'metrics': value['metrics'] = []
    if mutation == 'nested': value['health']['observed_at'] = 'invalid'
    raw = json.dumps(value)
    if mutation == 'duplicate': raw = '{"schema_version":1,"schema_version":1}'
    if mutation == 'oversize': raw = ' '*8193
    with pytest.raises((ValueError, TypeError)): Report.parse(raw)


def test_missing_is_distinct_from_zero_and_inputs_are_immutable():
    values = [['queue_depth', 0]]
    parsed = report(values)
    values[0][1] = 42
    assert parsed.metrics == (('queue_depth', 0),)
    assert dict(report().metrics) == {}
    assert dict(parsed.metrics) == {'queue_depth': 0}


def test_publish_does_not_follow_directory_or_leaf_links(tmp_path):
    root = tmp_path.resolve()
    directory = root/'alias'; directory.symlink_to(root, target_is_directory=True)
    with pytest.raises(OSError): publish(directory/'snapshot', report())
    destination = root/'original'; destination.write_text('keep')
    leaf = root/'snapshot'; leaf.symlink_to(destination)
    publish(leaf, report())  # replace the link itself; never write its target
    assert destination.read_text() == 'keep' and not leaf.is_symlink()
    with pytest.raises(ValueError): publish(root/'..'/'snapshot', report())


def test_failure_before_rename_retains_previous_complete_report(tmp_path, monkeypatch):
    path = tmp_path.resolve()/'snapshot'
    publish(path, report())
    original = path.read_bytes()
    def fail(*args, **kwargs): raise OSError('simulated')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError): publish(path, report((('queue_depth', 1),)))
    assert path.read_bytes() == original and list(path.parent.iterdir()) == [path]


def test_target_validation_and_duplicate_configuration(tmp_path, capsys):
    with pytest.raises(ValueError): Target('bad\n<<<section>>>', 'primary', '/unused')
    with pytest.raises(ValueError): Target('bear', 'primary', 'relative')
    target = Target('bear', 'primary', str(tmp_path.resolve()/'missing'))
    with pytest.raises(ValueError): export([target, target])
    with pytest.raises(ValueError): export([Target('bear', f'i{n}', '/missing') for n in range(65)])
    main(['--target', 'private\nSECRET', 'primary', '/unused'])
    output = capsys.readouterr().out
    assert 'SECRET' not in output and parse_row(output.splitlines()[1])[1] == ('invalid', None)


def test_export_does_not_rejuvenate_old_reports(tmp_path):
    path = tmp_path.resolve()/'snapshot'
    value = report(); publish(path, value)
    target = Target('jarvis', 'primary', str(path))
    for _ in range(3):
        assert parse_row(export([target]).splitlines()[1])[1][1].health.observed_at == NOW


def test_configuration_revision_is_safe_optional_metadata():
    value = Report(report().health, 300, (), 'deployment-abc123')
    assert Report.parse(value.to_json()).configuration_revision == 'deployment-abc123'
    for revision in ('private value', 'bad\n<<<section>>>', '', True):
        with pytest.raises(ValueError): Report(report().health, 300, (), revision)
    assert Report.parse(report().to_json()).configuration_revision is None


def test_transport_rejects_extra_fields_bad_status_and_identity_changes(tmp_path):
    target = Target('jarvis', 'primary', str(tmp_path.resolve()/'missing'))
    original = collect(target)
    for updates in ({'secret': 'PRIVATE'}, {'status': 'healthy'}, {'agent_id': 'bad\nsection'},
                    {'report': {}}, {'status': 'ok', 'report': report(agent_id='bear').as_dict()}):
        with pytest.raises((ValueError, TypeError)):
            parse_row(json.dumps(dict(original, **updates)))
