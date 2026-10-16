"""Namespaced metadata and separate-unit graphs, including rolling counts."""
from cmk.graphing.v1 import Title
from cmk.graphing.v1.graphs import Graph
from cmk.graphing.v1.metrics import Color, DecimalNotation, Metric, Unit

from cmk_addons.plugins.forge_agents.lib.telemetry import METRICS

UNITS = dict(METRICS, heartbeat_age='seconds', execution_failure_percent='percent', verification_failure_percent='percent')
for _key, _unit in UNITS.items():
    globals()['metric_forge_' + _key] = Metric(
        name='forge_' + _key, title=Title(_key.replace('_', ' ').capitalize()),
        unit=Unit(DecimalNotation({'seconds': 's', 'percent': '%', 'usd': 'USD', 'count': ''}[_unit])), color=Color.BLUE,
    )
    globals()['graph_forge_' + _key] = Graph(
        name='forge_' + _key, title=Title(_key.replace('_', ' ').capitalize()), simple_lines=['forge_' + _key],
    )
