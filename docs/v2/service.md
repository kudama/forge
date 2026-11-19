# Forge v2 service specification

Status: draft requirements for review. Recorded 2026-11-18.

## Objective and ownership

Turn authorized engineering assignments into durable, traceable work with reliable
source delivery, bounded execution, and reviewable results. Reduce supervision
needed for local delegation; measure it rather than assuming a newer model solves it.

The service owns assignment admission, Forge authorization, source preparation,
durable queue/attempt state, worker routing, result admission, artifacts, review
records, and recovery. See [architecture](architecture.md) for boundaries.
ChatGPT retains senior architecture, engineering, security, and final review.

## SRV-01 — Admit work durably

As a user, I can learn whether work is executable before worker time is consumed.

- Validate the [MCP work order](mcp.md), caller grants, source availability,
  supported output/criteria, and limits.
- Resolve/capture immutable source and record effective limits.
- Commit task and receipt durably before acknowledgement.
- Known preflight failures do not queue inference.
- Acceptance is not a guarantee of a correct solution.

## SRV-02 — Plan bounded tasks

As senior controller, I can issue assignments appropriate for local workers.

- Distinguish analysis, implementation proposals, and test proposals.
- Use maintained templates specifying inputs, outputs, and limits.
- Prefer one bounded task. Record explicit partitioning when needed.
- Preserve parent objective, dependencies, criteria, and source revision.
- Parent completion requires accounting for all required child work.
- Bound delegation depth, count, and resource use; no unrestricted recursion.
- Model-driven planning beyond templates is a separately evaluated capability.

## SRV-03 — Authorize and capture source

As a worker, I receive the exact allowed context.

- Explicit repository/path grants support approved relevant types, including
  frontend sources, without blanket filesystem access.
- Validate manifests before activation; report unsupported/missing sources.
- Prepare deterministic bounded source packets with revision/path/line provenance.
- Exclude credentials and unrelated private files from model context.
- Retain snapshots for reproducibility and detect source drift before application.
- Repository instructions are data, not permission grants.

[Workers](workers.md) owns detailed source-delivery rules.

## SRV-04 — Schedule and dispatch

As a user, I can understand waiting work without destabilizing Foundry.

- Persist queued work independently of clients.
- Enforce configured global/per-user concurrency and worker/model capacity.
- Define fairness and prevent indefinite starvation.
- Show queue/wait reason where feasible; separate queue wait and execution time.
- Claim work atomically with attempt identity, ownership, deadlines, and
  liveness/lease or equivalent single-executor protection.
- Detect stale attempts; reconcile before redispatch and reject late/stale
  attempt results as authoritative completions.
- Record bounded retries and their reasons. Never imply exactly-once inference.
- Do not silently switch to paid cloud models.
- Worker/provider outages yield explicit degraded/unavailable outcomes.

## SRV-05 — Replace worker backends independently

As operator, I can change a backend without changing task identity or policy.

- Stable adapter interface for execute, progress, cancel, and result.
- Model-specific protocol/formatting belongs inside adapters.
- Server-controlled routing records actual model, adapter version, and settings.
- Keep credentials outside model context.
- Diagnose unsupported calls/malformed responses explicitly.
- Require representative evaluations before promoting default models.
- Initial workers remain read-only proposal generators.

## SRV-06 — Admit and review results

As reviewer, I receive evidence, not an unsupported success label.

- Strict schema/scope/source checks before admission.
- Retain rejected raw output and reasons under private retention controls.
- Separate model claims from independently run checks.
- Record reviewer changes and partial/rejected outcomes explicitly.
- Preserve original model output; corrected artifacts carry their own attribution.
- Compilation, tests, behavior, and acceptance criteria remain independent checks.
- Execution, admission, correctness review, application, merge, and deployment
  are distinct records.

## SRV-07 — Independent validation and release

Initially support evidence from senior-run independent checks. Any automated
validation runner requires its own isolated design, allowed commands/resources/
network, and authorization; do not run generated code inside the controller.

Reports record source revision, proposed/applied artifact, checks, outcomes,
limitations, and reviewer. Failure history cannot be erased by a later summary.

Initial service exposes proposals/artifacts only. Apply, PR publication, merge,
and deployment remain separately authorized workflows. Models cannot grant
themselves release authority.

## SRV-08 — Persistence and recovery

As a user, accepted work and evidence survive interruption.

- Transactional task/receipt/attempt state; artifact integrity references.
- Separate credentials from tasks and versioned source.
- Explicit state transitions and append-preserving attempt/review history.
- Restart preserves queued work and detects interrupted running work.
- Interrupted execution is reconciled or terminally failed with an explicit reason;
  never report success or silently replay uncertain work.
- Protect stale completion and cancellation races.
- Restore task records and artifacts consistently.
- Retention/deletion rules cover snapshots, results, logs, backups, and tombstones.

Database/storage products are open decisions; no database migration is assumed.

## SRV-09 — Operate and configure

As operator, I can diagnose failure without reconstructing several chats.

- Expose service/config/adapter/model-route versions.
- Measure queue age, active work, timeout/cancellation, source/protocol/admission
  failures, independently accepted proposals, and correction effort.
- Correlate gateway, service, worker, and review records.
- Routine logs/metrics exclude credentials and full private prompts.
- Integrate with existing monitoring through a documented interface.
- Validate configuration/grants/manifests before activation.
- Version non-secret templates in Git and identify restart requirements.
- Keep known-working configuration and tested rollback; no silent grant expansion.

[Operations](operations.md) owns operational requirements;
[acceptance and migration](acceptance-migration.md) owns release evidence.

## Acceptance and open choices

Demonstrate automatic source preparation, representative verified proposals,
multi-user isolation/scheduling, precise worker failures, safe duplicate handling,
cancel/restart/outage recovery, consistent restoration, and honest result states.

Open: initial templates/repositories/models/limits; hosting; scheduling; storage;
retention and recovery targets; revoke-during-work policy; quantitative reliability
and correction-effort targets; v1 coexistence; launch scope of automated validation.
No implementation or deployment is authorized by this draft.
