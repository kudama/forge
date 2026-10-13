# Shared agent foundation

First implementation for [Forge #40](https://github.com/kudama/forge/issues/40),
authorized October 12, 2026. Parent:
[shared platform #5](https://github.com/kudama/personal-ai-platform/issues/5).
The package is separately installable at `packages/agent-core` with no runtime
dependencies. It establishes contracts for scoped reads and peer handoffs while
preserving the six-agent architecture and existing implementation.

## Common responsibilities, distinct domains

| Consumer | What the shared base supports | What stays in its domain or adapter |
| --- | --- | --- |
| Jarvis / Treasurer | Per-person identity, household versus private resources, authorized peer reads, cited results | Calendar/list workflows, preferences, briefings; Treasurer's read-only finance sources and reconciliation |
| Citadel / Steward / Mechanic | Registered capabilities, home/host resource scope, consistent request and evidence correlation | Device/scene policy; Steward schedules and dispatch; Mechanic host execution, locks, verified receipts and recovery |
| Forge / Engineer / UX Designer | Explicit worker/service identity and task scope, repeatable handoffs | Existing controller/model routing, source snapshots/work orders, code review, PR publication and deployment gates |
| Thoth / Librarian / Curator | Scoped catalog/collection reads and source/freshness references | Book/edition ownership, reading/watch history, metadata, recognition and reviewed media management |
| Hermes / Paparazzi / Publicist | Separate capture/draft resources and per-person data access, source references | Consent/retention, iOS feasibility, voice/style/media selection, draft approval and explicitly authorized publishing |
| Bear | Per-person fitness-service access and source timestamps | Training Atlas health/workout data, analysis, coaching, recovery/goal semantics; no medical or cross-person authority inferred |

All peers need replaceable model and provider adapters, authenticated clients,
grants, provenance, structured errors and handoffs. Some need schedules,
notifications, persistent context and actions. Those requirements do not make
every peer a copy of the same prompts, memory database or tool set. Named
specialists receive their own explicit identities/grants; parentage supplies none
automatically. Shared context is accessed through services owned by the domain.

## First vertical

The synthetic example represents Jarvis requesting Bear's fitness summary for
Mike. The authenticated context distinguishes Mike from Kyle and Jarvis from
Hermes. Bear accepts only the exact grant for its registered summary capability,
Mike's subject and the named resource. No record values appear in the scope.
Other users/peers/resources are denied before handler or validator access. A
successful response carries a source/reference/timestamp. It does not imply
actual Training Atlas access or a deployed Bear.

The core lives in Forge because it is shared engineering infrastructure.
`personal-ai-platform` remains architecture/requirements, not a new operational
memory store. Domain repositories consume an independently versioned package
after its interface is reviewed. No extra agent framework or runtime dependency
was selected. Existing Forge and Mechanic packages are not migrated in this PR.

## Adapter contracts and next steps

| Boundary | Required integration | Current implementation |
| --- | --- | --- |
| Authentication/identity | Verify client and calling service, bind person/service claims; reject untrusted forwarded identity; revocation checked at issuance/use | `Principal` is the typed trusted context; no identity provider selected or installed |
| Model/provider | Bounded model proposes capability/arguments; service policy validates; model cannot supply grants/handlers/credentials | Existing Forge Ollama layer remains separate; no new LLM loop |
| Domain read service | Fixed handler validates arguments and scopes queries from trusted context; sources are fresh or explicitly reported stale/uncertain | Generic read dispatcher plus synthetic example/tests; actual providers pending |
| Peer handoff | Authenticate both peers; preserve person and purpose, issue a narrower explicit target grant | Exact caller/target/person scope; in-process demonstration only |
| Persistent context | Domain API stores structured data/provenance and supports correction, deletion, per-person grants and retention | No base-memory database; Postgres/NAS placement remains separate |
| Scheduling/notifications | Deterministic service owns jobs/delivery, retries and notification rules; source/action grants rechecked at execution | No scheduler here; preserve selected maintenance Postgres/RabbitMQ/OpenBao design |
| Actions/approval | Exact validated plan, durable authorization, idempotency/reconciliation, locks and postchecks under scoped credentials | Write tools fail closed; Mechanic's existing operational foundation stays separate |
| API/MCP clients | Versioned envelopes plus authenticated transport, bounded deadlines/cancellation, lifecycle/health and secret-free audit | Strict request/result JSON and static errors; no listener or daemon installed |

The current call is synchronous. A domain adapter must bound its own remote
calls; transport timeout/cancellation does not prove a handler stopped. Do not
run arbitrary untrusted plugins inside a privileged process. Policy objects and
tool registration are trusted application configuration. Registering something
as read-only is not enforcement of its filesystem/network effects.

Grant snapshots narrow a call but do not replace runtime authorization: construct
or refresh service instances from current trusted grants. Do not retain stale
grants indefinitely or let an LLM create them. Request IDs correlate calls;
read requests may repeat. Consequential retries require a separate durable
operation contract, never a silent extension of this read dispatcher.

Next reusable integration should implement one authenticated real read workflow,
with per-person denial and source freshness tested at the actual domain API.
Agree transport identity and domain provider first. Actions, job reliability and
shared-context storage should reuse existing boundaries rather than turning the
core into a monolithic platform. GitHub holds source/design/acceptance evidence;
domain services hold their operational state.

## Validation and limits

The regression suite tests all six identities, exact peer/person/resource denial,
malformed/oversized JSON, source timestamps, immutable input/grant snapshots,
unavailable capabilities, write refusal and sanitized handler failures. Forge
identified and reproduced an iterator-consumption bug in grant validation, then
fixed it by snapshotting the iterable before validation. Independent package
installation and example execution are part of review validation.

Two no-tool local `qwen3-coder:30b` packets reviewed source and proposed tests:
`local-agent-core-review-20261012-01` and `local-agent-core-tests-20261012-01`.
These are packet IDs, not controller work orders. The review's depth/duplicate-key/
argument-validation bug claims were rejected against the actual guards/tests.
Useful denial/error test themes were considered; claims that this library can
sandbox a dishonest read handler were rejected. Forge owns the final tests,
security boundary and correctness verdict. No runtime grants or credentials changed.

This is implemented foundation code, not a completed top-level bot, whole-platform
security audit, persistent-memory service or deployed domain workflow. Sources:
[requirements](https://github.com/kudama/personal-ai-platform/blob/main/docs/requirements.md),
[six-peer architecture](https://github.com/kudama/personal-ai-platform/blob/main/docs/agent-architecture.md),
[Forge work orders](work-orders.md) and
[Mechanic contracts](https://github.com/kudama/mechanic/blob/main/docs/contracts.md).
