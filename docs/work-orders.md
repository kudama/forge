# Forge-issued work orders

Status: v1 contracts with a Forge-side validator/compiler and real compatibility-path trials. This document defines the
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

## Validator and compiler

`scripts/work_orders.py` provides two explicit operations. It uses JSON Schema
validation already included in `requirements-mcp.lock`; no additional dependency
is introduced. Run from the checkout with the same operator-managed `FORGE_*`
environment as the active controller. There is no automatic discovery of the
running controller's configuration; the operator must ensure those settings match.

```sh
.venv/bin/python scripts/work_orders.py compile /private/path/order.json \
  --principal forge_mcp > /private/path/task-input.json
.venv/bin/python scripts/work_orders.py validate-result /private/path/order.json \
  --principal forge_mcp --result /private/path/result.json \
  --execution /private/path/execution.json
```

Use private directories and mode 600 for order, prompt, execution and result
files; they may contain sensitive task data. The compiler emits only the existing
task API arguments and never submits, applies, merges or changes GitHub state.
Forge submits them through MCP and saves the returned task ID. Historical examples
are not ready-to-run orders: create a new ID and pin the current revision/hashes.

Preflight enforces schemas, current grants, exact configured limits, HEAD revision,
approved file access and hashes matching both Git source and current source.
Result validation repeats preflight, checks the matching worker result against a
successful owner/role-scoped execution record, rejects undeclared reads/tools,
checks tool budget and citation ranges against the audit, and validates exact,
non-overlapping source replacements. Supply an execution record retrieved through
the authenticated controller by Forge; worker-supplied records are not provenance.
Local JSON inputs are size-bounded and reject duplicate keys and nonstandard constants.

The returned `review_required: true` is deliberate. Structural validity and source
correspondence do not prove a claim, patch behavior or acceptance criteria. Forge
must independently review and test. The validator does not authenticate a saved
JSON execution record or capture immutable source snapshots; its caller and
operator settings are trusted parts of this Forge-side boundary.

The [compiled handoff trial](experiments/work-order-handoff-2026-10-04.json)
passed through the real MCP controller, persisted private attempt metadata, and
returned independently reviewed source-line evidence. The full optional-tooling
suite passes 188 tests, including 34 handoff regression cases.

## Next implementation boundary

The Forge-side validator/compiler has no GitHub polling or scheduler. Trial order
and attempt/review links stay in private state; automatic durable handoff storage
and recovery are not implemented. Preserve existing submission and ownership
behavior. Controller-native work orders and idempotent submission
need separate designs and migrations rather than prompt-only claims of enforcement.

The compatibility trial uses [issue #15](https://github.com/kudama/forge/issues/15)
and [review evidence](experiments/work-order-contract-2026-10-04.json).
