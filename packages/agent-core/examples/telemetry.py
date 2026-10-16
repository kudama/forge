"""Service callback template: pass actual observations, never invent metrics."""
from forge_agent_core.telemetry import Report, publish


def on_health_observation(path, health, window_seconds, metrics, configuration_revision=None):
    """Call from the owning service after assessing health and expiring old probes.

    health is a Snapshot whose observed_at is the assessment time. metrics is an
    iterable of measured name/value pairs; pass () if no metrics are instrumented.
    The approved state directory must already exist. No scheduler/probes are added.
    """
    publish(path, Report(health, window_seconds, tuple(metrics), configuration_revision))
