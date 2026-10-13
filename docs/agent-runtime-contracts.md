# Common agent runtime, action and audit contracts

Design proposal for [Forge #43](https://github.com/kudama/forge/issues/43),
October 13, 2026. Builds on the shared core/secret principles in PR #41. These
contracts are not runtime enforcement, authentication, scheduling or deployment.
The [health implementation task](https://github.com/kudama/forge/issues/42)
is a separate PR; domain semantics remain in the six agents.

## Versioned service profiles

Every deployed service/specialist needs a validated, operator-owned profile:

| Field group | Minimum contract |
| --- | --- |
| Identity | Schema version, agent ID, stable deployment instance ID, owning peer/service, authenticated workload identity reference |
| Software | Package/build revision, supported request/result contract versions, reproducible deployment source and rollback compatibility |
| Capabilities | Registered names/versions, read/draft/mutation effect, input/result schemas, subject/resource scope and ownership |
| Permissions | Trusted policy reference/revision, grant refresh/revocation behavior; no inherited household/parent access |
| Adapters | Allowed provider/service references and required versus optional dependencies; credential references under OpenBao principles |
| Limits | Admission capacity, request/input/output bounds, caller deadline, provider timeouts, retry policy and safe cancellation behavior |
| Operations | Health observation cadence/freshness, state/audit references, retention, process owner, startup/drain/recovery and alert owner |

Profiles contain no credentials or private records. Unknown fields/schema versions
fail validation; capabilities are implemented by fixed handlers, not arbitrary
model-supplied imports, URLs or commands. Models can choose among authorized
capabilities but cannot rewrite profiles or grants. Validate actual effective
permissions before publishing capabilities. A static profile is not proof of
current authorization or provider availability.

Expose only the capability metadata the authenticated caller may see. Publish
schema/version/lifecycle metadata separately from personal context. Contract
changes require explicit compatibility rules; do not add unsupported fields to
the current strict core request. Transport/deadline/action metadata needs a
reviewed outer adapter contract or a versioned request extension.

## Startup, readiness and shutdown

Lifecycle: starting → serving → draining → stopped; failure may enter a bounded
recovery path. Starting loads/validates profile, identity, current policy and
state compatibility before accepting work. Cheap dependency checks establish
readiness for registered capabilities. Expensive model or provider checks are
bounded and cached only with explicit freshness; idle model unloading does not
necessarily make a deterministic capability unavailable.

Draining rejects new work and allows admitted work only within its configured
deadline. Persist any required action disposition before shutdown. A timeout,
disconnect or cancellation response is not proof a provider-side mutation stopped.
Restart reopens known operation records, identifies interrupted work and resumes
observation/reconciliation rather than repeating uncertain effects. A process
supervisor handles process restart; model reasoning is not the supervisor.

Health separates liveness from accepting work and dependency readiness. Configure
Checkmk host/process checks plus the metadata health services. Planned changes
use real maintenance windows. Health/alerts never silently authorize repair.
Profiles specify software/state rollback compatibility; failed migrations or
restores do not trigger automatic downgrade against incompatible state.

## Peer handoffs and bounded execution

Authenticate both originating person and calling service. A receiving peer
rechecks its own target/capability/subject/resource grants; a forwarded request,
parent relationship or copied identity string grants nothing. Specialists use
their own explicit permission boundaries. Handoff records correlate parent and
child request IDs without exposing prompts or private records in shared logs.

Propagate a trusted deadline and remaining work budget. Queue wait consumes the
budget. Each service chooses a shorter provider timeout and bounds admission,
output and concurrency. Reject overload explicitly instead of allowing unbounded
queues. Slow/failed dependencies cannot block all unrelated capabilities.
Read retries are bounded by freshness/deadline and transient error classification;
authentication/validation/permission errors are not retryable. Duplicate reads
may execute again; the current core request ID is correlation, not idempotency.

Models remain replaceable adapters. Credential-consuming domain clients remain
trusted code with restricted credentials; read/draft labels are contracts, not
an OS sandbox. Any cross-domain query must preserve person/resource scope and
source timestamps. Do not expose a generic database, HTTP or shell endpoint to
make every integration look uniform.

## Actions, approvals and durable receipts

Writes require a separate action adapter. The current shared core rejects them.
Define action ID, actor/workload, target, operation/capability version, permitted
arguments, preconditions, expected changes, affected-resource locks, acceptance
checks and recovery plan. Bind approval to the exact normalized plan/version,
person, resource, policy revision and expiry; a changed plan or scope invalidates
approval. Standing permissions must be explicit trusted policy, not a description
field saying automatic. OpenBao retrieval follows authorization/plan validation.

Persist action acceptance/ownership and step intent before mutation. Use scoped
idempotency keys plus a canonical argument/plan digest; a reused key with different
work is rejected. Provider-native idempotency is preferred where supported, but
is not a blanket exactly-once guarantee. Record execution, verification and
recovery states separately. Exit code or HTTP success without postconditions is
not completed work. Request cancellation records disposition honestly.

If a response is lost or a process restarts mid-mutation, mark the operation
needs-reconciliation, retain target locks/uncertainty guards as appropriate, and
inspect actual state before retrying. Never create a new ID to bypass an unknown
outcome. Secret refresh or model retry does not justify action replay. Long-running
workers use durable ownership/leases and bounded recovery; asynchronous delivery
is duplicate-safe and acknowledged only after the required disposition persists.

Reuse [Mechanic's operation foundation](https://github.com/kudama/mechanic/blob/main/docs/runtime-foundation.md)
for host/action semantics and [Forge work orders](work-orders.md) for proposal
workers. Reuse the platform's selected Postgres/RabbitMQ/OpenBao maintenance
architecture for scheduled jobs. Synchronous reads do not need a new job broker;
do not replace existing domain state with a generic framework or controller DB.

## Correlation and safe audit

Use distinct request, parent-request, job, action and attempt IDs with clear
ownership. Record schema/build/policy revision, authenticated workload, capability,
target alias, admission/outcome/verification state, timestamps/duration and safe
provider/evidence references. Audit subject identifiers are private metadata,
not metrics labels. Default metrics expose aggregate latency, capacity/error
counts, dependency state and version—no personal values or high-cardinality IDs.

Separate operational metadata from private evidence and application records.
Allowlist log fields; do not log prompts, credentials, arguments/results, raw
provider responses or exception content by default. Capture authorized diagnostic
evidence only in protected domain storage with retention. Bind trace propagation
to authenticated callers, validate length/format and never interpret trace IDs as
authority. Audit sink failure uses a defined policy: reads may report reduced
observability, but consequential actions requiring durable audit must fail closed
before mutation. Preserve safe failure evidence without inventing completed work.

## Applicability and conformance

| Peer | Contract emphasis |
| --- | --- |
| Jarvis | Per-person calendars/lists, consented household sharing; peer handoffs preserve the requesting person's scope |
| Citadel / Steward / Mechanic | Device/host locks, maintenance windows, scheduled jobs and uncertain operation reconciliation |
| Forge | Source-pinned proposals, independent validation and separately authorized publication/deployment |
| Thoth | Per-person reading/watch history, catalog schema compatibility and reviewed media mutations |
| Hermes | Capture/draft/publish separation, exact reviewed publication plans, duplicate delivery prevention |
| Bear | Health-data freshness and per-person scope; coaching reads do not imply source-record mutation |

Future implementation must demonstrate invalid profile/version rejection,
per-person/peer denial, revoked grants, overload/deadline behavior, graceful drain,
safe cancellation/interrupt recovery, same-key argument conflicts, approval invalidation,
postcondition failure and secret-free audit error paths. Test actual provider
idempotency/reconciliation and process restart on approved targets. Do not mark
these accepted because a design document or synthetic read example exists.

This PR defines the common contracts and retains existing owners. No lifecycle
engine, action executor, audit backend, authentication provider, queue, grants or
deployed state is installed. Adapter implementations should be separate bounded
issues linked to platform requirements and actual domain acceptance.
