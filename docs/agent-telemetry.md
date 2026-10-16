# Structured agent telemetry

October 15, 2026 implementation for Forge #42. Extends the shared health
snapshot without changing the existing local-check CLI. The application owns
instrumentation; the collector reads files; the Checkmk server owns thresholds,
service discovery, graphing and notification policy. Neither path runs an LLM,
fetches secrets, opens a listener or performs remediation.

## Producer API

Install `packages/agent-core` in the application's approved Python 3.12+ venv.
The application builds a `Snapshot` from current, bounded observations, wraps it
in `telemetry.Report(health, window_seconds, metrics, configuration_revision=None)`
and calls `telemetry.publish(path, report)`. Metrics are immutable `(name, value)`
pairs. Configuration revision is an optional safe deployment alias or digest of
nonsecret configuration; never hash credentials into this field. The schema
accepts only defined metadata and numeric metrics, rejects duplicate/unknown
fields and bounds the encoded report to 8192 bytes.

`publish` atomically replaces a file in an existing service-owned directory,
refuses symlinked parent paths, creates private temporary files, flushes the
file, renames within that directory and flushes the directory. Failure before
replacement retains the prior complete report. A failure after rename may leave
the new complete report present even if the directory flush failed; report the
publication error rather than rewriting timestamps. Leaf links are replaced,
never followed. Directory ownership is a deployment prerequisite, not inferred
from a path string. Mode 640 is reduced by the caller's umask; arrange an approved
reader group and umask when group reading is needed. Do not widen permissions on
other application state. The file reader rejects world-accessible files, hard
links, symlinks at every component, special files and oversized reports.

Run publication from the owning service's normal lifecycle, after actual
observations. A separate timer must not assert liveness for a dead application.
A callback demonstrating API usage is in `packages/agent-core/examples/telemetry.py`;
it does not create probes or invent operational metrics. Cache expiry and
readiness deadlines belong to the service. An idle agent can be healthy; do not
use time since last request or an unloaded model as universal outage signals.
The old `health.Snapshot` file and the richer `telemetry.Report` file have
different schemas. If both adapters are needed, publish separate files from the
same observation; do not point the old CLI at a report envelope.

## Numeric contract

Every value is finite and nonnegative, at most 10^15; counts must be integers and
percentages at most 100. No dynamic labels, personal IDs, source URLs, prompts,
errors, tool arguments or secret-derived values are accepted. Alias vocabulary
is configured by administrators. Omission means **not measured**, distinct from
an explicitly measured zero. Do not silently carry a prior value forward as a
new sample.

`window_seconds` is 1–86400. Counts, costs, inference duration and latency
statistics cover this rolling window ending at `health.observed_at`; they are
not cumulative counters and Checkmk must not differentiate them as counters.
Queue, freshness, capacity and reconciliation are gauges at that same time.
Use the same window across samples for comparable trends. Aggregations describe
the entire configured instance, with no per-person dimensions.

| Metric | Meaning |
| --- | --- |
| `queue_depth` | Eligible queued work; exclude deliberately scheduled future work |
| `oldest_eligible_seconds` | Age of oldest eligible queued item; measured zero for an empty eligible queue |
| `running_overdue` | Running work past its explicit execution deadline; never infer a universal task timeout |
| `reconciliation_pending` | Actions with uncertain outcome requiring reconciliation |
| `execution_successes`, `execution_failures`, `execution_timeouts` | Mutually exclusive completed execution outcomes in the window; exclude cancellation and in-flight work |
| `verified_successes`, `verification_failures` | Independent verification outcomes in the window; exclude unverified execution and pending verification |
| `peer_failures` | Failed peer handoffs in the window; no peer/person labels |
| `authorization_denials` | Aggregate policy denials in the window |
| `response_median_seconds`, `response_p95_seconds` | End-to-end response latency; omit when no observations; median cannot exceed p95 |
| `handoff_p95_seconds`, `queue_wait_p95_seconds` | Peer handoff and eligible queue wait latency; omit when no observations |
| `source_age_seconds` | Oldest required source age based on verified source timestamps; omit if any required source freshness is unknown, then require this metric centrally |
| `capacity_used_percent` | Occupancy of the service's configured capacity, 0–100 |
| `inference_seconds`, `input_tokens`, `output_tokens` | Measured inference use in the window, not estimates; omit unavailable provider counts |
| `hosted_cost_usd` | Verified hosted inference cost in USD in the window; omit unknown or differently denominated cost |

The server derives execution failure percentage from `(failures + timeouts) /
(successes + failures + timeouts)` and verification failure percentage from
`verification_failures / (verified_successes + verification_failures)`. Each
requires all component counts and at least the centrally configured minimum
sample size (default five). With no samples the rate is absent, never a fabricated
0% or 100%. Requiring a rate or setting its threshold makes an unavailable rate
UNKNOWN, including idle periods; use count-based policies if idle should remain
OK. Execution success does not establish verification success.

## Exporter

Use an administrator-owned Checkmk agent plugin wrapper with an absolute approved
venv path and fixed expected identities/paths:

```sh
#!/bin/sh
exec /APPROVED/VENV/bin/python -m forge_agent_core.telemetry \
  --target jarvis primary /APPROVED/STATE/jarvis/telemetry.json \
  --target bear primary /APPROVED/STATE/bear/telemetry.json
```

Place this in the host's verified Checkmk **plugins** directory, not the local
checks directory. The CLI emits a complete `<<<forge_agents:sep(0)>>>` section,
with one ASCII-escaped JSON line per configured identity, at most 64. It neither
refreshes observation times nor applies health thresholds. Missing, invalid or
wrong-identity files still emit the expected identity with a fixed unavailable
or invalid state and no content/error/path echo. Invalid configuration emits a
stable collector configuration identity in UNKNOWN. Protect the wrapper/config
from application and model writes. No filesystem path is sent to the server.

The server independently computes heartbeat age using its own clock (30-second
future tolerance). It suppresses all telemetry from stale or future-invalid
reports; repeated collection cannot refresh old graphs. Required dependencies,
required measurements, maximum heartbeat age, maximum metric window, minimum
rate sample count and upper warning/critical thresholds are configured centrally.
Optional measurements without thresholds remain graph-only. Thresholds imply
the measurement is required; missing values produce UNKNOWN. There are no global
latency, cost, failure-rate or queue thresholds without an agreed workload
baseline. Default heartbeat expiry is 180 seconds and default maximum metric
window 3600 seconds; confirm both per deployment.

See [Checkmk package and acceptance](../integrations/checkmk/README.md) for server
installation, compatibility and offline validation. The local-check fallback is
in [agent-health.md](agent-health.md). Enable one alerting path per instance to
avoid duplicate incidents. Native host/process checks remain necessary.

## Delivery boundaries

The reusable producer/publisher, transport and server plugin are implemented and
tested offline. This does not assert application-specific probes/instrumentation
exist in Jarvis, Citadel, Forge, Thoth, Hermes or Bear. Each service owner must wire
its real metrics and callbacks before production acceptance. There is no verified
Checkmk endpoint/version in the current inventory, and no service, certificate,
notification channel or running agent was changed. Secrets and OpenBao are
represented only by safe dependency aliases and aggregate state; health polling
must not retrieve secrets to prove access.
