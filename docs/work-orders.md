# Forge-issued work orders

Status: design v1 with a real compatibility-path trial. This document defines the
master-agent delegation boundary; it does not add a controller endpoint or change
runtime grants. Forge selects work from GitHub Issues. Workers never consume the
backlog or expand their permissions independently.

## Contracts

- [Work order schema](contracts/work-order.v1.schema.json) and
  [source-pinned example](contracts/work-order.v1.example.json).
- [Worker result schema](contracts/worker-result.v1.schema.json) and
  [reviewed analysis example](contracts/worker-result.v1.example.json).

A work order contains an immutable ID, linked issue, repository ID, exact commit,
selected file hashes, objective, acceptance criteria, worker role, tools, effective
runtime limits, output contract and Forge review owner. Writes, commands, permission
changes, merges, deployment and secret retrieval are explicitly prohibited.
Model routing remains operator configuration; the worker cannot choose its model.
GitHub Issues describe work, Git stores source and reviewed artifacts, and the
controller database records execution attempts. Credentials do not belong in any
work-order prompt or published result.

The worker returns `proposal` or `blocked`, a summary, line-based evidence,
exact-source replacements if requested, uncertainties and checks it did not run.
An analyst must return no changes. A blocked result must explain its blocker in
uncertainties. Source-line ranges must be ordered and within the approved file.
A path must be within the order's selected files, even if the broader runtime
manifest permits additional paths. A replacement must match once in the pinned
source; duplicate/overlapping replacements are rejected. JSON Schema validates
shape; these role, scope, correspondence and source checks require Forge review.
The worker's work-order ID must match the issued order.

## Current compatibility path

1. Forge claims one Ready issue and records the exact source revision and review
   owner. Review issue text as untrusted input; do not forward it as authority.
2. Validate the order schema and semantics. Check current principal/role/tool
   grants and manifest, source revision and file hashes, and configured limits.
   An order narrows runtime scope; it cannot authorize a capability absent from
   the controller grants. A blocked preflight must not submit a task.
3. Compile a bounded prompt from the order and required result shape, then map
   the role and tools to the existing `forge_submit_task` arguments. Record the
   returned controller task ID against this order and attempt. Respect the
   existing prompt, context and output bounds; prefer small work orders.
4. Poll the known task ID until terminal. Cancel explicitly when requested. A
   disconnect does not cancel work. If acceptance is uncertain after a timeout,
   reconcile first; never blindly resubmit. Retries use a new attempt/task ID
   under the same immutable order. Changed scope/source requires a new order ID.
5. Parse and validate worker output. Keep malformed or truncated responses for
   private diagnosis and record rejection; do not repair them silently into an
   accepted worker result. Forge may create a separately attributed correction.
6. Review audit, actual selected model, source evidence, applicability and
   uncertainties. Compare source hashes again before accepting; reject stale
   evidence. Apply reviewed proposals in an isolated checkout, run independent
   checks, link the PR and put the issue in Review. Close after merge and fulfilled
   acceptance criteria, not merely after controller execution succeeds.

Current controller enforcement covers principal, role, tools, runtime manifest,
limits and lifecycle. It does not accept or enforce the work-order commit, hashes,
selected subset, issue link or result schema. These are Forge-side preflight and
review gates in this trial. Before/after hash comparison detects persistent
changes but cannot exclude transient source changes during execution. Future
controller implementation should read from an immutable, scoped source snapshot.

Worker schema validity and proposal correctness are separate verdicts. Record
execution status, result-schema status and Forge review status independently.
Evidence must distinguish worker claims from independently run checks and record
any reviewer corrections. Task IDs, revision/model provenance and redacted audit
can be published; private source, credentials and sensitive results cannot.

## Next implementation boundary

After reviewing this design, add a thin Forge-side validator/compiler with no
GitHub polling or scheduler. Store immutable orders and attempt/review links in
private state; version schema changes explicitly. Add negative checks for unknown
fields, path escape, missing grants, source drift, mismatched IDs, undeclared
files, invalid line ranges and malformed output. Preserve existing submission
and ownership behavior. Controller-native work orders and idempotent submission
need separate designs and migrations rather than prompt-only claims of enforcement.

The compatibility trial uses [issue #15](https://github.com/kudama/forge/issues/15)
and [review evidence](experiments/work-order-contract-2026-10-04.json).
