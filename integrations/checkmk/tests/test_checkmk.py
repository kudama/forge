from datetime import datetime, timedelta, timezone
import inspect
import io
import json
import subprocess
import tarfile

import pytest
from cmk.agent_based.v2 import Metric, Result, State, entry_point_prefixes
from cmk.graphing.v1 import entry_point_prefixes as graph_prefixes
from cmk.mkp_tool._mkp import Manifest, PackagePart, create_mkp, extract_manifest
from cmk.rulesets.v1 import entry_point_prefixes as rule_prefixes
from cmk_addons.plugins.forge_agents.agent_based import forge_agents as plugin
from cmk_addons.plugins.forge_agents.graphing import forge_agents as graphs
from cmk_addons.plugins.forge_agents.rulesets import forge_agents as rules
from forge_agent_core.health import Snapshot
from forge_agent_core.telemetry import METRICS, Report, Target, export, publish

from conftest import builder, stage

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
DEFAULTS = plugin.check_plugin_forge_agents.check_default_parameters


def report(metrics=(), **updates):
    values = dict(agent_id='jarvis', instance_id='primary', version='0.1.0', observed_at=NOW,
                  alive=True, accepting_work=True, dependencies=(('data', 'ok'),))
    values.update(updates)
    return Report(Snapshot(**values), 300, metrics)


def run(value=None, **params):
    section = {'jarvis/primary': ('ok', value or report())}
    return list(plugin.evaluate('jarvis/primary', dict(DEFAULTS, **params), section, now=NOW))


def states(results):
    return [r.state for r in results if isinstance(r, Result)]


def measurements(results):
    return {r.name: r.value for r in results if isinstance(r, Metric)}


def test_real_api_entry_points_and_callback_signatures():
    for module, prefixes in [(plugin, entry_point_prefixes()), (rules, rule_prefixes()), (graphs, graph_prefixes())]:
        registered = [key for key, value in vars(module).items() if any(isinstance(value, kind) and key.startswith(prefix) for kind, prefix in prefixes.items())]
        assert registered
    assert str(inspect.signature(plugin.check_forge_agents)) == '(item, params, section)'
    form = rules.rule_spec_forge_agents.parameter_form()
    assert set(form.elements) == set(DEFAULTS)
    for name, element in form.elements['levels'].parameter_form.elements.items():
        assert name in graphs.UNITS
    assert set(rules.ALL_METRICS) == set(METRICS) | {'execution_failure_percent', 'verification_failure_percent'}


def test_native_mkp_reader_and_builder_accept_package(tmp_path):
    package = builder.package()
    assert package == builder.package()  # deterministic sources, file modes and mtime
    manifest = extract_manifest(package)
    assert isinstance(manifest, Manifest)
    assert manifest.version_min_required == '2.4.0'
    assert manifest.version_usable_until == '2.6.0'
    assert manifest.version_packaged == '2.5.0p14'
    assert str(manifest.version) == '0.1.1'
    assert set(manifest.files) == {PackagePart.CMK_ADDONS_PLUGINS}
    # The upstream builder requires GNU tar; its reader runs on macOS too.
    if 'GNU tar' in subprocess.check_output(['tar', '--version'], text=True):
        official = create_mkp(manifest, lambda part: stage/'cmk_addons/plugins', manifest.version_packaged)
        assert extract_manifest(official) == manifest
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as tar:
        with tarfile.open(fileobj=io.BytesIO(tar.extractfile('cmk_addons_plugins.tar').read())) as inner:
            assert sorted(inner.getnames()) == sorted(str(p) for p in manifest.files[PackagePart.CMK_ADDONS_PLUGINS])
            assert all(m.isfile() and m.mode == 0o644 for m in inner.getmembers())


def test_full_producer_file_export_parse_discover_check_path(tmp_path):
    path = tmp_path.resolve()/'telemetry.json'
    publish(path, report((('queue_depth', 4), ('reconciliation_pending', 1))))
    text = export([Target('jarvis', 'primary', str(path)), Target('bear', 'primary', str(path.parent/'missing'))])
    section = plugin.parse_forge_agents([[line] for line in text.splitlines()[1:]])
    assert [s.item for s in plugin.discover_forge_agents(section)] == ['bear/primary', 'jarvis/primary']
    results = list(plugin.evaluate('jarvis/primary', dict(DEFAULTS, levels={'reconciliation_pending': ('fixed', (1, 2))}), section, now=NOW))
    assert State.WARN in states(results)
    assert measurements(results)['forge_queue_depth'] == 4
    assert states(list(plugin.evaluate('bear/primary', DEFAULTS, section, now=NOW))) == [State.UNKNOWN]


@pytest.mark.parametrize('updates,expected', [
    ({}, [State.OK, State.OK]),
    ({'alive': False}, [State.CRIT, State.CRIT]),
    ({'accepting_work': False}, [State.OK, State.WARN]),
    ({'dependencies': ()}, [State.OK, State.UNKNOWN]),
    ({'dependencies': (('data', 'failed'),)}, [State.OK, State.CRIT]),
    ({'dependencies': (('optional', 'failed'), ('data', 'ok'))}, [State.OK, State.WARN]),
    ({'observed_at': NOW-timedelta(seconds=181)}, [State.CRIT, State.UNKNOWN]),
    ({'observed_at': NOW+timedelta(seconds=31)}, [State.UNKNOWN, State.UNKNOWN]),
])
def test_server_liveness_readiness_states(updates, expected):
    assert states(run(report(**updates), required_dependencies=['data']))[:2] == expected


def test_server_owns_age_policy_and_stale_values_do_not_refresh_metrics():
    old = report((('queue_depth', 5),), observed_at=NOW-timedelta(seconds=181))
    assert 'forge_queue_depth' not in measurements(run(old))
    assert 'forge_queue_depth' in measurements(run(old, max_age_seconds=300))
    assert not measurements(run(report(observed_at=NOW+timedelta(seconds=31))))


def test_missing_and_duplicate_sections_do_not_pass_as_healthy():
    assert states(list(plugin.evaluate('jarvis/primary', DEFAULTS, {}, now=NOW))) == [State.UNKNOWN]
    assert plugin.parse_forge_agents([]) == {'collector/transport': ('invalid', None)}
    assert plugin.parse_forge_agents([['SECRET']]) == {'collector/transport': ('invalid', None)}
    row = json.dumps(dict(agent_id='bear', instance_id='primary', status='unavailable', report=None))
    assert plugin.parse_forge_agents([[row], [row]])['bear/primary'] == ('invalid', None)
    assert plugin.parse_forge_agents([[row]]*65) == {'collector/transport': ('invalid', None)}
    assert plugin.parse_forge_agents([[row, row]]) == {'collector/transport': ('invalid', None)}


def test_missing_required_metric_is_unknown_zero_is_a_measurement():
    assert State.UNKNOWN in states(run(required_metrics=['queue_depth']))
    assert State.UNKNOWN not in states(run(report((('queue_depth', 0),)), required_metrics=['queue_depth']))
    assert measurements(run()) == {'forge_heartbeat_age': 0}
    assert State.UNKNOWN in states(run(levels={'queue_depth': ('fixed', (3, 5))}))


def test_execution_and_verification_are_separate_with_low_sample_and_idle_semantics():
    metrics = (('execution_successes', 8), ('execution_failures', 1), ('execution_timeouts', 1),
               ('verified_successes', 1), ('verification_failures', 9))
    output = run(report(metrics), levels={'execution_failure_percent': ('fixed', (25, 50)), 'verification_failure_percent': ('fixed', (25, 50))})
    measured = measurements(output)
    assert measured['forge_execution_failure_percent'] == 20
    assert measured['forge_verification_failure_percent'] == 90
    assert State.CRIT in states(output)
    assert 'forge_execution_failure_percent' not in measurements(run(report(metrics), minimum_rate_samples=11))
    idle = report((('execution_successes', 0), ('execution_failures', 0), ('execution_timeouts', 0)))
    assert all(state == State.OK for state in states(run(idle)))
    assert State.UNKNOWN in states(run(idle, required_metrics=['execution_failure_percent']))


def test_all_metrics_have_graph_definitions_and_window_guard():
    output = run(report(tuple((key, 1) for key in METRICS)))
    for key in measurements(output):
        assert hasattr(graphs, 'metric_' + key) and hasattr(graphs, 'graph_' + key)
    limited = run(report((('queue_depth', 4),)), max_window_seconds=60)
    assert State.UNKNOWN in states(limited) and 'forge_queue_depth' not in measurements(limited)
