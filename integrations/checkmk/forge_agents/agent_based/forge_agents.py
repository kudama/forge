"""Checkmk 2.4 API v2 adapter. No network calls or application imports."""
from datetime import datetime, timezone

from cmk.agent_based.v2 import AgentSection, CheckPlugin, Metric, Result, Service, State, check_levels

from cmk_addons.plugins.forge_agents.lib.health import Policy, assess
from cmk_addons.plugins.forge_agents.lib.telemetry import METRICS, parse_row


def parse_forge_agents(string_table):
    section = {}
    malformed = False
    # Bounded to 64 configured instances. Never silently truncate a larger table.
    if len(string_table) > 64:
        return {'collector/transport': ('invalid', None)}
    for row in string_table:
        try:
            if len(row) != 1:
                raise ValueError('invalid_columns')
            item, report = parse_row(row[0])
            if item in section:
                section[item] = ('invalid', None)
            else:
                section[item] = report
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            malformed = True
    if malformed or not string_table:
        section['collector/transport'] = ('invalid', None)
    return section


def discover_forge_agents(section):
    for item in sorted(section):
        yield Service(item=item)


def evaluate(item, params, section, *, now=None):
    status, report = section.get(item, ('unavailable', None))
    if status != 'ok' or report is None:
        yield Result(state=State.UNKNOWN, summary='Telemetry ' + status)
        return
    now = now or datetime.now(timezone.utc)
    policy = Policy(report.health.agent_id, report.health.instance_id,
                    frozenset(params.get('required_dependencies', [])), params.get('max_age_seconds', 180))
    live, ready, live_text, ready_text, age = assess(policy, report.health, now=now)
    yield Result(state=State(live), summary='Liveness: ' + live_text)
    yield Result(state=State(ready), summary='Readiness: ' + ready_text)
    if age is not None:
        yield Metric('forge_heartbeat_age', age, boundaries=(0, None))
    if age is None or age > policy.max_age_seconds:
        return  # Old values are not new measurements.
    if report.window_seconds > params.get('max_window_seconds', 3600):
        yield Result(state=State.UNKNOWN, summary='Telemetry window exceeds configured maximum')
        return
    values = dict(report.metrics)
    units = dict(METRICS, execution_failure_percent='percent', verification_failure_percent='percent')
    minimum = params.get('minimum_rate_samples', 5)
    rates = {
        'execution_failure_percent': (('execution_successes', 'execution_failures', 'execution_timeouts'), ('execution_failures', 'execution_timeouts')),
        'verification_failure_percent': (('verified_successes', 'verification_failures'), ('verification_failures',)),
    }
    for key, (denominator_keys, numerator_keys) in rates.items():
        if all(k in values for k in denominator_keys):
            denominator = sum(values[k] for k in denominator_keys)
            if denominator >= minimum and denominator > 0:
                values[key] = 100 * sum(values[k] for k in numerator_keys) / denominator
    thresholds = params.get('levels', {})
    required = set(params.get('required_metrics', [])) | {
        key for key, levels in thresholds.items() if levels[0] != 'no_levels'
    }
    for key in sorted(required - values.keys()):
        reason = 'insufficient samples or unavailable' if key in rates else 'unavailable'
        yield Result(state=State.UNKNOWN, summary=key + ': ' + reason)
    for key, value in sorted(values.items()):
        yield from check_levels(value, levels_upper=thresholds.get(key, ('no_levels', None)),
                                metric_name='forge_' + key, label=key,
                                boundaries=(0, 100 if units[key] == 'percent' else None), notice_only=True)
    yield Result(state=State.OK, notice=f'Telemetry window: {report.window_seconds}s; {len(report.metrics)} measurements')
    if report.configuration_revision is not None:
        yield Result(state=State.OK, notice='Configuration revision: ' + report.configuration_revision)


def check_forge_agents(item, params, section):
    yield from evaluate(item, params, section)


agent_section_forge_agents = AgentSection(name='forge_agents', parse_function=parse_forge_agents)
check_plugin_forge_agents = CheckPlugin(
    name='forge_agents', sections=['forge_agents'], service_name='AI agent %s',
    discovery_function=discover_forge_agents, check_function=check_forge_agents,
    check_ruleset_name='forge_agents',
    check_default_parameters={'max_age_seconds': 180, 'max_window_seconds': 3600,
                              'minimum_rate_samples': 5, 'required_dependencies': [],
                              'required_metrics': [], 'levels': {}},
)
