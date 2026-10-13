# Shared context, retention and notification contracts

Design proposal for [Forge #44](https://github.com/kudama/forge/issues/44),
October 13, 2026. Applies to all six peers and their specialists. Parent platform
#5 covers CTX-01 and PLAT-03/04. No context store, vector database, ingestion,
notification provider or permission is installed by this document.

## Domain records, explicit sharing

Domain services/APIs remain authoritative. Postgres is the selected structured
record store and NAS/file storage holds larger assets where approved; actual
placement, schemas and recovery remain separate work. The base is not an
unrestricted common memory database, nor is conversation history operational
truth. Agents request permitted context through the owning service rather than
copying whole domain databases into prompts or another agent's storage.

The common context record/reference contract includes:

| Field group | Minimum semantics |
| --- | --- |
| Version/identity | Schema version, opaque record ID, record version and owning domain/service; stable references do not imply public access |
| Scope | Subject/person or explicitly defined household resource, classification, audience/sharing policy reference and current grant revision |
| Provenance | Source/service and source-record/version references, observed/event time, retrieval time, transformation lineage and correction relationships |
| Meaning | Observed versus inferred/derived, optional confidence with its defined semantics, validity/freshness rule and explicit missing/uncertain state |
| Lifecycle | Creation/update time, retention policy/expiry, correction/deletion state, permitted replicas/caches and recovery owner |
| Content | Domain-specific typed value or asset reference under that domain's access/size rules; credentials are excluded |

References and metadata can themselves be private. Authenticate person and
calling peer and authorize subject/resource/audience before returning them.
Household membership, proximity, voice confidence or parentage does not grant
access to another person's calendar, health, finances or message history. Shared
records require an explicit scope with consent/authority and a revocable policy.
Combine only records the receiver is permitted to access for that purpose.

These proposed fields are not accepted by the current strict core Request or
fully enforced by its Source record. Domain/context adapters need reviewed
schemas and API contracts; extend versions deliberately. The current core passes
exact scope and basic source/time references, not a complete memory system.

## Freshness and retrieval

Preserve actual event/observation times; fetching old data now does not make it
fresh. A domain defines its own acceptable age and missing-source behavior.
Calendar events, fitness ingestion, media catalogs and device state have different
freshness requirements. Do not hardcode one global TTL for every peer.

Return source age/uncertainty and partial availability explicitly. An inference
cannot be promoted to an observation by a peer handoff; retain transformations
and confidence semantics. Contradictory sources remain visible with their owners
and timestamps rather than being silently merged into a confident memory.
Model-generated summaries are derived artifacts, not replacement source records.
Bound query/prompt sizes, avoid unnecessary private values and distinguish an
authorized empty result from unavailable/denied context.

Adapters scope backend queries from authenticated Context fields, not a model's
subject override. Cache keys include domain/record version, person/resource,
audience and relevant grant revision. Before use, refresh authorization and
validate expiry/source version; a cache hit does not preserve revoked access.
Do not create embeddings until a demonstrated retrieval workload justifies them.
Any later index is another scoped replica with deletion/recovery obligations.

## Correction, deletion and recovery

Corrections create an explicit version/relationship so consumers can invalidate
old summaries and references. Deletion/tombstones propagate to registered caches,
derived artifacts, queued notifications and any approved indexes. Do not silently
continue recommending from deleted or corrected personal data. Audit metadata
may retain the minimal permitted disposition under a separate retention policy,
not the deleted private payload.

The owning service records downstream propagation acknowledgments and remaining
exceptions. It cannot promise removal from unsupported external systems, already
delivered messages, published posts or historical backups. Report those limits
and use separately authorized provider deletion/retraction where available.
Retention and backup expiry must be agreed before collecting data; no infinite
retention default. Restores reapply tombstones/corrections and current grants
before making old records queryable, so recovery does not resurrect withdrawn
sharing or deleted records without the user's informed decision.

Context reads can use domain-service caching; consequential source-record
changes use that domain's approval/action contract. Do not create a second shared
write authority in Forge merely because several agents consume the same source.

## Notification contract

Each notification request carries a version, stable event/incident ID and
idempotency/delivery key, owning service, authorized recipient/audience,
classification/purpose, safe content/template reference, source/action references,
creation/eligibility/expiry times, urgency, channel/preference policy and delivery
disposition. Store credential references only in trusted provider configuration,
not the job or message body. The provider/channel is undecided until selected.

Resolve current recipient and sharing grants at dispatch and every retry. A
queued message does not freeze permission forever. On private channels and lock
screens, default to a minimal notification with authenticated detail retrieval;
never expose health, finance or private message values through a broad household
or public destination. Clicking a reference rechecks access, rather than trusting
an old link. Template variables and attachments have the same disclosure scope
as the notification itself.

Respect explicit cadence/quiet hours, time zone, channel choices and expiration.
Routine unchanged health/success states stay quiet unless requested. Notify on
meaningful change, requested completion, failure/recovery or required user action.
Group/deduplicate related events by incident and audience. Checkmk owns host/service
alerting; domain notifications should reference the same incident and avoid
generating a parallel alarm stream. A warning can request diagnosis, not grant
remediation or permission to message arbitrary people.

Distinguish queued, attempting, submitted, delivered/acknowledged where supported,
blocked, expired, failed and outcome-unknown. Provider acceptance is not proof
someone received or read the message. Bound retries by expiry and classification;
permission/recipient/template failures are not transient. Reconcile a lost
provider response before replay. Use provider-native idempotency when available,
but do not promise exactly-once delivery. A durable outbox links domain event and
pending notification atomically if that workflow needs reliable asynchronous
delivery. Reuse the chosen service architecture; no new universal queue is implied.

Publishing/communications authority remains with its owner. A notification
transport for approved system alerts does not confer Hermes publication or
private-message authority. Publicist drafts still require Mike's review. Jarvis's
reminders, Steward's maintenance messages and other peer notifications each need
their explicitly authorized workflow and audience.

## Six-peer emphasis and acceptance

| Peer | Context and notification concerns |
| --- | --- |
| Jarvis / Treasurer | Separate personal calendars/finance from shared household lists; source-backed briefings and approved reminders |
| Citadel / Steward / Mechanic | Device/host observations versus inferred state, durable job/incident references, quiet routine operations and actionable alerts |
| Forge | Source revisions, task/review evidence and sanitized build results; code/job records do not become personal memory |
| Thoth / Librarian / Curator | Collection ownership and private reading/watch history, corrected metadata and authorized discovery summaries |
| Hermes / Paparazzi / Publicist | Capture consent/retention, observed versus inferred activity, drafts versus publication, correction/deletion of derived content |
| Bear | Health-source freshness and per-person retention; private coaching results do not become household alert payloads |

Future conformance checks include denied person/peer/audience access, stale and
contradictory sources, observations/inferences, revoked cached grants, corrected
derived records, deletion propagation and recovery without resurrecting data.
Notification tests cover changed/revoked audiences after queueing, quiet-hour and
expiry rules, duplicate/lost responses, provider failure and secret-free error
paths. Verify actual receipt/retraction/deletion capabilities on the selected
provider before claiming them. These are future implementation checks, not
completed integration tests or authorization to collect/send personal data.
