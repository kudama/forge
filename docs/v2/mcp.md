# Forge v2 MCP service specification

Status: draft requirements for review. Recorded 2026-11-18.
See [architecture](architecture.md) and [SSO workflows](sso.md).

## Objective

Expose one authenticated bounded engineering interface to supported desktop and
native iPhone clients. Tasks survive changes of chat and device. The interface
does not grant models new execution or release authority.

## MCP-01 — Connection

- Stable HTTPS endpoint using standard MCP Streamable HTTP and publicly trusted TLS.
- OAuth discovery and authorization follow the SSO contract.
- No client-side scripts, local credential files, or direct Foundry access required.
- Publish tested protocol/client versions and accurate tool annotations.
- Keep internal controller, database, model, and administrative endpoints private.
- Native iPhone access is required at launch and remains unverified; a browser
  substitution requires explicit acceptance.

## MCP-02 — Public tools

Names are proposed contracts; exact schemas are a later design artifact.

| Tool | Purpose |
| --- | --- |
| forge_identity | Authenticated identity and effective access summary |
| forge_capabilities | Permitted task types, repositories, source revisions, effective limits |
| forge_health | Service, queue, worker availability, observation times |
| forge_submit_work_order | Submit a bounded assignment and return a durable receipt |
| forge_get_task | Authorized task status, result, provenance, verification |
| forge_list_tasks | Find authorized tasks across chats/devices |
| forge_cancel_task | Request authorized cancellation |

Use one clear work-order submission contract. Legacy tools, if retained, require
equivalent permissions and a separately documented compatibility contract.
Read-only versus mutating annotations guide clients, not authorization.

No arbitrary shell, file writes, unrestricted URL fetching, credentials, patch
application, merge, or deployment tools are added in this scope.

## MCP-03 — Work order and receipt

As a user, I can submit precise work without understanding model internals.

Inputs: idempotency key; objective; acceptance criteria; supported task type;
authorized repository/source selection; permitted analysis/change scope; supported
result format; requested limits within caller bounds.

The service resolves source references to an immutable revision, preflights
permissions/source/limits, and records a durable task before acknowledgement.
Invalid preflight must not start inference. Callers cannot introduce arbitrary
paths, grants, or execution resources.

Receipt: task ID, acceptance timestamp, initial state, resolved revision, effective
limits, and correlation ID. Task identifiers and receipts contain no bearer secrets.

## MCP-04 — Continuity, duplicate handling, and cancellation

As a user, I can continue tracking work from another authorized client.

- Accepted work survives disconnection, chat closure, and service restart.
- The idempotency key is scoped to authenticated owner and service environment.
- Same key and semantically identical assignment return the original receipt;
  conflicting reuse is rejected.
- Define canonical assignment comparison, retention, and expiry/tombstone behavior
  before implementation. Expiry must never silently allow replay of uncertain work.
- Reconcile lost responses before retrying. Do not promise exactly-once model execution.
- Cancellation is idempotent; requested and completed cancellation are distinct.
- Preserve terminal outcomes and cancellation races.
- Listing, retrieval, pagination, and artifacts obey ownership/sharing permissions.

## MCP-05 — State and review

| Execution state | Meaning |
| --- | --- |
| queued | Accepted, waiting |
| running | Execution started |
| succeeded | Execution finished and output passed admission |
| failed | Execution or admission failed |
| cancelled | Cancellation completed |

Correctness and review are separate fields: unreviewed, verified, rejected, or
partially verified with attributed evidence. Succeeded does not mean approved,
applied, merged, or deployed. Detailed lifecycle rules belong to [service](service.md).

## MCP-06 — Source and results

As a reviewer, I can inspect evidence against the assignment's exact source.

- Deliver source deterministically; do not depend on guessed paths/tool limits.
- Record actual revision, worker/model, effective limits, and relevant audit.
- Return summary, source references, findings/changes, checks reported by the worker,
  independent evidence if available, limitations, remaining work, and review state.
- Reject malformed output, duplicate keys, out-of-scope changes, and unsupported shapes.
- Large results use authorized bounded pagination/artifact retrieval; no silent truncation.
- Result content remains untrusted and cannot instruct clients to expand permissions.
- Artifact identifiers are not public bearer links.

[Workers](workers.md) owns detailed source/result admission and validation rules.

## MCP-07 — Errors and limits

Stable machine-readable errors include a safe message, correlation ID, retryability,
and next action. Distinguish authentication, authorization, invalid assignment,
idempotency conflict, missing/stale source, queue/rate limit, unavailable worker,
deadline, denied/unrecognized tool, invalid result, internal error, and uncertain
submission outcome.

Report effective request/context/output/tool/execution/queue limits. Queue wait is
separate from execution time. Retries are bounded and duplication-safe; permission
failures do not trigger broader grants. Never disclose credentials or unauthorized
resource existence through errors.

## MCP-08 — Health

As operator, I can tell whether the endpoint is reachable and whether work can run.

- Ordinary health does not load a model.
- Separate gateway, controller/storage, queue capacity, and worker availability.
- Include component version and observation time.
- Report latest real capability probe, age, outcome, and tested scope separately.
- A probe exercises allowed source delivery and output admission; it is not proof
  of arbitrary proposal correctness.
- Preserve correlation IDs across the gateway/service/worker boundary.

## Acceptance and open choices

See [acceptance and migration](acceptance-migration.md).
Required: both users on desktop/native iPhone, cross-device retrieval, third-user
denial, ownership/source isolation, safe duplicate handling, restart/reconnect/
cancel/timeout behavior, representative verified proposals, v1 regression cases,
and visible component identity.

Open: initial task/repository catalog; sharing; concurrency and queue policy;
limits; artifact retention; legacy clients; polling guidance/progress notifications;
deployment arrangement. No implementation is authorized by this document.
