# Forge v2 worker execution and validation

Status: new draft for review. Recorded 2026-11-18.
Owns worker contracts; see [service](service.md) for durable orchestration.

## Objective

Make bounded local delegation reliable enough to reduce senior correction work.
Separate transport/protocol success from proposal quality. Reproduce the known
v1 failure modes in isolated tests rather than repeatedly retrying production work.

Initial roles: source-grounded analyst, implementation-proposal worker, and
test-proposal worker. Initial outputs are proposals only.

## WRK-01 — Prepare usable assignments

As senior controller, I can give a worker a complete bounded assignment.

- Compile a versioned template with objective, criteria, role, permitted source,
  exact output contract, available tools, prohibited actions, and effective limits.
- Pin source revision and file hashes before dispatch; retain the packet hash.
- Include required context directly when it fits. Additional reads use a defined,
  authorized interface only when necessary.
- Context budgeting includes instructions, source, tool schemas/messages, and
  reserved output. Oversize fails preflight or produces an explicitly reviewed
  partition; never silently truncate source or criteria.
- Separate trusted policy from untrusted repository text and task material.
- A worker cannot change its role, model, source scope, tools, or release authority.

## WRK-02 — Source access

As worker, I can read allowed source without guessing hidden constraints.

- Supply exact available paths and read limits, or stable source-chunk handles.
- Validate grants and supported source types before replacing active manifests.
- Support approved Python, documentation, configuration, and frontend sources;
  define encodings, binary handling, path normalization, symlink and size policies.
- Reject path traversal, symlink escapes, unapproved paths, and stale revisions.
- Reads always resolve to captured source, not a mutable working tree.
- Provide source-complete/source-partial metadata and accurate line ranges.
- Tool denials identify safe failure category and effective bounds without
  leaking unrelated paths or widening grants.
- Track delivered/read evidence independently of model assertions.
- Detect unavailable required source before inference where determinable.

## WRK-03 — Worker adapter protocol

As operator, I can identify whether a model or adapter violated the contract.

- Version normalized tool schemas and translate backend formats in one adapter.
- Validate tool name, arguments, role grant, selected source, call budget, and
  deadline before executing any worker request.
- Treat unknown tool names, malformed calls, excessive reads, and source denials
  as distinct diagnostic categories.
- Bound inference rounds, total tool calls, request/output sizes, and deadlines.
- A tool call is not a final result; empty, truncated, or unfinished output is
  explicitly classified.
- Retain normalized attempt events and private raw response with correlation IDs.
- No user tokens, repository credentials, shell tools, or write tools reach models.
- Retries follow SRV-04. Deterministic permission/configuration failures are not
  retried with identical input; no fallback expands authority or incurs cloud cost.

## WRK-04 — Result contract

As reviewer, I can inspect a faithful proposal against its pinned source.

Required: assignment/attempt identity; result kind (proposal or blocked); summary;
source references; findings/changes appropriate to role; checks claimed/not run;
uncertainties; criteria coverage; and known limitations.

- Analysts return findings and no edits.
- Implementation proposals use one documented patch representation with exact
  applicability checks and unambiguous file identity.
- Test proposals state target behavior, fixtures, and what failure they detect.
- New-file proposals, if supported, explicitly name authorized target paths and
  are distinguished from edits; until specified they are rejected, not inferred.
- Blocked results state the missing prerequisite and do not claim implementation.
- Strict parsing rejects duplicate keys, nonstandard constants, wrong identities,
  unexpected fields, and invalid schema versions.
- Scope/citation/applicability validation uses captured source, including overlap,
  ambiguous anchors, changed hashes, and out-of-range references.
- Do not silently strip fences or repair malformed output into accepted raw work.
  Any bounded repair pass is a separately attributed attempt with retained original
  output and full revalidation. Whether to enable repair is open.

## WRK-05 — Independent correctness checks

As senior reviewer, I can distinguish a syntactically valid proposal from useful work.

- Report protocol completion, result admission, correctness, criteria coverage,
  and review outcome separately.
- Initially, senior Forge applies proposals in isolated checkouts and records
  independent checks. The model cannot certify its own correctness.
- Use compilation/static checks when applicable and behavior tests relevant to
  the change. Do not add tests merely mirroring implementation.
- Test proposals must exercise the actual interface and fail against a suitable
  seeded defect or equivalent meaningful negative control.
- Verify resource cleanup, input/output aliasing, validation boundaries, and
  error paths when material to the change.
- Record raw acceptance versus acceptance after format or semantic corrections.
- Validation failure remains visible even if the task executed successfully.

## WRK-06 — Future isolated validation runner

If separately authorized, the runner must have disposable workspaces, no production
mounts or credentials, default-denied network, approved dependency acquisition,
resource/time/process limits, and authenticated result reporting. Allowlisted
validation recipes are selected by trusted code, not arbitrary model commands.
Destroy/quarantine workspaces after collecting bounded evidence. Runner failure
must not become proposal approval. This is not an initial worker privilege.

## WRK-07 — Model qualification

As operator, I can promote models using representative evidence.

- Compare candidates with the same pinned sources and effective assignments.
- Include small analysis, exact edit, meaningful test writing, and a real
  multi-file/frontend example appropriate to launch scope.
- Record every attempt, protocol/source failures, raw correctness, correction
  effort, queue/load/execution time, and resource use.
- Separate cold-load latency from execution; avoid general rankings from tiny trials.
- Larger contexts or newer names do not imply better results.
- Keep production default unchanged until the release review accepts evidence.
- Maintain a reproducible regression set for prior tool_denied, sources_not_read,
  invalid_worker_result, oversized reads, malformed edits, duplicate keys,
  timeout, and technically valid but incorrect proposals.

## Open decisions and acceptance

Choose task sizes/limits, patch representation, frontend type policy, blocked-result
mapping, repair policy, backend versions, benchmark cases, and quantitative quality/
correction thresholds before coding these contracts.

The [acceptance plan](acceptance-migration.md) must prove that source delivery and
recognized-tool execution work, result admission rejects bad contracts, and
independent review catches incorrect admitted proposals. No worker receives new
commands or writes under this document.
