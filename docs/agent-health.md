# Shared health reporting and Checkmk

Implementation proposal for [Forge #42](https://github.com/kudama/forge/issues/42),
October 13, 2026. Depends on shared-core PR #41. All six peers and separately
deployed specialists use the same metadata contract. No running agent, Checkmk
server, producer schedule, system service or firewall was changed.

## What healthy means

Each deployed instance publishes a bounded JSON snapshot with schema version,
agent/stable instance alias, software version, timezone-aware observation time,
reported liveness, whether it accepts work, and up to 32 named dependency states.
Only fixed metadata is permitted; no prompts, personal record values, credentials,
raw exceptions, provider URLs or request arguments. Names/versions are constrained
to safe characters; unknown fields and malformed values are rejected.

The collector's trusted profile declares required dependencies and maximum report
age. A producer cannot make an outage disappear by dropping a required dependency
from its report. Optional failures degrade readiness; required failures prevent
it. Unloaded/idle models are not failures if their service can perform the
required capability; do not require a model backend for a deterministic worker.

| Situation | Liveness | Readiness |
| --- | --- | --- |
| Fresh report: alive, accepting work, required dependencies OK | OK | OK |
| Required dependency failed | Reported liveness | CRIT |
| Required dependency missing/unknown | Reported liveness | UNKNOWN |
| Optional dependency unavailable or any dependency degraded | Reported liveness | WARN |
| Alive but deliberately not accepting work (startup/draining) | OK | WARN |
| Reports not alive | CRIT | CRIT |
| Report older than configured maximum | CRIT | UNKNOWN |
| Missing, malformed, future-dated beyond 30-second skew, or wrong identity | UNKNOWN | UNKNOWN |

Default maximum age is 180 seconds, explicitly configurable; it is not an agreed
production cadence. The collector refuses non-regular, linked, oversized and
world-readable snapshot files. Parent directories are traversed without following
symlinks. Failure messages are fixed codes and never echo file contents/errors.

Liveness is a recent report from the producer, not proof of process identity or
actual provider functionality. Also monitor the real process/service/host through
Checkmk's normal checks. A functioning reporter cannot substitute for readiness:
the owning service must derive dependency states from bounded real checks,
invalidate expired probe caches, and leave unverified dependencies unknown.
Snapshot age does not prove each provider's data is fresh. Domain source freshness
is a separate requirement. Never perform a paid/full LLM generation, retrieve a
secret, query personal records or retry a mutation merely to satisfy a poll.

## Collection path

Use a Checkmk local check on the application host that reads the service-owned
snapshot and renders two stable services. The installed Python package exposes:

```sh
/APPROVED/VENV/bin/python -m forge_agent_core.health \
  --agent jarvis --instance primary \
  --snapshot /APPROVED/STATE/health.json \
  --require data --max-age 180
```

The paths and `data` dependency are illustrative; configure each actual deployed
profile. Install a small administrator-owned wrapper in the host's verified
Checkmk local-check directory, using the correct venv path. Keep service identity
stable across restarts to avoid service discovery churn. The package emits local
check lines, not an entire agent section, and opens no listener or provider
connection. Its CLI produces UNKNOWN for unreadable/bad/missing snapshots.

Checkmk local checks use a numeric state, quoted service name, performance data
or `-`, and summary. This collector supplies two lines with explicit states and
heartbeat-age performance data. Source:
[official local-check documentation](https://docs.checkmk.com/latest/en/localchecks.html).

Prefer this lightweight local reader over granting applications write access to
Checkmk's shared spool directory. A raw spool file can inject agent sections;
age-prefixed files are omitted when stale, which then relies on Checkmk handling
missing service data. Reading structured JSON locally keeps stale state explicit
and never passes raw application output into agent sections. Source:
[official spool documentation](https://docs.checkmk.com/latest/en/spool_directory.html).

## Producer and deployment ownership

The application/service owner supplies the producer, cheap probe definitions,
poll cadence and expected dependencies. The producer writes atomically in its
registered state directory; retain the prior complete file until replacement.
Health observation time is when the producer actually assessed the service,
not when a collector reread old data. Do not put a timer in this core package.

Mechanic operates the approved service/wrapper permissions and process startup.
The service can write only its own snapshot; Checkmk can read it through an
approved group (for example mode 640), without access to domain credentials or
other application state. Verify actual filesystem ownership and parent paths.
The wrapper/configuration is administrator-owned and not model-editable.
Checkmk registration, certificate verification, allowed network path and service
discovery follow the separately reviewed VM baseline; this PR does not enable
unauthenticated monitoring or automatic remediation.

Checkmk owns infrastructure alerting and scheduled downtime. Planned maintenance
must have an explicit window; do not hide it by writing a permanent OK report.
Agent/domain notifications should link to the same incident instead of generating
duplicate alarms. A health failure may request diagnosis; it does not grant
restart/deployment/credential changes.

## Six-peer profiles and acceptance

| Peer | Example readiness dependencies to confirm, not universal defaults |
| --- | --- |
| Jarvis | Authorized calendar/list adapters; model only for conversational tasks |
| Citadel | Permitted device service; Steward schedule delivery and Mechanic executors monitored separately |
| Forge | Controller task store and required inference roles; engineering/proposal-only mode distinct from deployment |
| Thoth | Catalog/collection API and selected metadata adapters; no host-admin requirement |
| Hermes | Draft source/store; publishing service separately authorized and monitored |
| Bear | Fitness-service API and verified source freshness; no direct health database admin access |

Tests cover state mapping, required-dependency omission, age/future boundaries,
identity mismatch, wire/output injection, bounded safe file reads and CLI failures.
The bounded no-tool local `qwen3-coder:30b` review
`local-health-review-20261013-01` proposed three concerns already covered by
permission, future-time and configuration guards; Forge verified and rejected
them as defects. Model completion did not establish correctness. Forge owns
the implementation, independent tests and deployment acceptance.
No current agent publishes this snapshot yet. Before deployment acceptance,
confirm the installed Checkmk version/paths, actual producer/permissions/cadence,
cheap readiness checks, monitored host registration and service discovery. Observe
normal state, stopped producer, required/optional outage, draining and recovery
on an approved test instance. Verify no personal or secret data in agent output.
This verifies integration separately from the offline code checks.
