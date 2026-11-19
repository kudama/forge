# Forge v2 acceptance testing and v1 migration

Status: new draft for review. Recorded 2026-11-18.
Owns release evidence and transition gates. No tests below are claimed executed.

## Objective

Prove a useful, secure workflow on the actual intended clients before replacing
v1. Preserve existing records, grants, and availability while v2 is evaluated.
A passing health call or merged code is insufficient release evidence.

## ACC-01 — Launch client matrix

As either approved user, I can use Forge from desktop and native iPhone ChatGPT.

| Environment | Required people | Required workflow | Current evidence |
| --- | --- | --- | --- |
| Desktop ChatGPT client(s), exact product/OS/version to select | Mike and husband | Connect/sign in, identity, submit, list, retrieve, cancel, reconnect | Unverified |
| Native ChatGPT iPhone client, iOS/app version to select | Mike and husband | Same workflow, including return from sign-in | Unverified |
| Desktop to iPhone and iPhone to desktop | Both, within own identity | Retrieve the same accepted task/result without resubmission | Unverified |

Specify account/workspace entitlement and local/cloud execution mode for each row.
Browser tests can supplement but cannot replace the required native iPhone row.
If that row is unsupported, record a launch blocker and request a requirement
decision; do not claim universal device support or silently substitute a browser.

## ACC-02 — Identity and authorization

- Both approved identities complete first connection, renewal, sign-out/reconnect,
  and recovery with selected authentication factors.
- A third authenticated identity is denied.
- Invalid signature, issuer, audience, expiry, and insufficient scope are rejected.
- Guessed task/artifact IDs and pagination cannot disclose another user's data.
- Repository/tool boundaries hold despite prompts requesting broader access.
- User disablement blocks new operations; test the chosen policy for accepted work.
- Measure revocation behavior and residual token lifetime rather than assuming
  immediate provider-token invalidation.
- Record the effective identity for each test without publishing token contents.

## ACC-03 — Submission and lifecycle

- Same owner/key/assignment yields one logical accepted task and its original receipt.
- Changed assignment under the same key is rejected; different users are isolated.
- Simulate loss of the submission response, client reconnect, and service restart.
- Accepted queue records survive; uncertain running work is reconciled explicitly.
- Test concurrent submissions and stale/late attempt completion.
- Verify queue/execution deadline distinction and configured scheduling fairness.
- Cancel queued/running/terminal work and test completion/cancellation races.
- A closed chat or expired client token does not silently cancel or duplicate work.
- Task/review/delivery states retain the meanings defined in [MCP](mcp.md).

## ACC-04 — Worker and correctness evaluation

Use the same pinned source fixtures and acceptance criteria across candidate models.
Include analysis, a bounded edit, a meaningful test proposal, and a frontend/
multi-file task representative of intended launch usage.

Reproduce prior v1 failures: unrecognized/denied tools, excessive source reads,
sources_not_read, invalid_worker_result, duplicate keys, malformed/ambiguous edits,
empty/truncated output, timeout, incorrect tests, and valid-looking incorrect code.

Test source/context preflight, snapshot immutability, allowed file types, source
drift, path/symlink escapes, and denied tool attempts. Independent checks must catch
a deliberately defective admitted proposal or an equivalent negative control.
Do not expose production credentials or data merely to make a benchmark realistic.

## ACC-05 — Reliability measurements and gate

Report denominators and all attempts, not selected successes:

| Measure | Meaning |
| --- | --- |
| Admission correctness | Valid jobs accepted and invalid jobs rejected as expected |
| Source delivery | Required permitted context reaches the worker |
| Protocol/result validity | Raw responses admitted without format repair |
| Independent correctness | Raw proposals satisfy criteria and independent checks |
| Reviewer correction effort | Time and nature of corrections, including format-only fixes |
| Latency | Queue, model load, execution, and review measured separately |
| Recovery integrity | Restarts/reconnects preserve records without unsafe duplication |

Before implementation qualification, agree numerical targets, sample sizes,
representative cases, allowed retries, latency/resource budgets, and correction
effort. These remain open release gates, not implied 100% model correctness.
Deterministic security/isolation cases must all pass. Model trials must not be
averaged together with configuration failures to hide either failure class.

## ACC-06 — Operations and privacy

Test unattended startup, configured HTTPS endpoint and streaming/proxy behavior,
certificate/key rotation, provider/worker outages, storage full/failure, and
consistent backup restore. Confirm no public access to model/database/admin
services and no secrets in logs or returned errors. Verify private task/artifact
retention and deletion behavior, including retained backups.

## MIG-01 — Inventory and coexistence

As operator, I can evaluate v2 without changing v1 production behavior.

- Inventory actual v1 code/config versions, grants, identities, tasks, journals,
  source snapshots, artifacts, model routes, and known deployment differences.
- Keep v2 test endpoint, credentials, storage, and source fixtures separate.
- No dual writer against the same v1 database and no automatic dual submission.
- Pin the baseline and use sanitized fixtures or explicitly approved data copies.
- Existing v1 clients continue until the migration plan is separately accepted.
- Do not silently upgrade old task semantics or claim historical success was verified.

## MIG-02 — Identity and record migration

- Explicitly map v1 principals to approved v2 owners; do not infer ownership from
  a shared v1 credential, email similarity, or repository name.
- Ambiguous legacy ownership requires operator reconciliation or private archival.
- Prefer read-only archive over complex import when it satisfies continuity.
- If importing, preserve original IDs through namespace/mapping, source provenance,
  execution/review status, timestamps, artifacts, receipts, and tombstones.
- Do not copy v1 bearer credentials into OAuth identities.
- Reconcile unfinished/uncertain work before starting equivalent v2 assignments.
- Verify counts, integrity, access controls, and lookup behavior after migration.

## MIG-03 — Cutover and rollback

- Produce a review packet with exact versions, client matrix, test evidence,
  unresolved blockers, recovery procedure, and proposed cutover window.
- Obtain separate authorization for production exposure/cutover.
- Drain or explicitly settle v1 work; take a consistent verified backup.
- Switch clients deliberately; preserve rollback materials and detect old-endpoint use.
- Avoid silent fallback between services and automatic task replay.
- Test rollback before cutover; reconcile any work accepted after the backup point.
- Retire v1 only after agreed acceptance, record-retention, and recovery checks.
- No cloud fallback, new paid service, or new worker permissions are implied.

## Evidence packet and decision

For each test: case/requirement ID, environment/build/config/source versions,
identity role, timestamps, input fixture, expected/observed behavior, task/attempt
IDs, independent verdict, corrections, and sanitized evidence location.

Release verdict: accepted, rejected, or conditionally accepted with explicitly
approved exclusions. Required native iPhone support and missing security controls
cannot be waived by an implementation summary.

## Sequence

1. Review specs and resolve client/quality/recovery gates.
2. After implementation authorization, prove isolated identity and MCP contracts.
3. Prove one bounded source-grounded workflow, including failure/recovery.
4. Run client matrix, worker qualification, isolation, and operations tests.
5. Rehearse record migration and rollback.
6. Review evidence and request production cutover authorization.

No infrastructure change or execution milestone is authorized by drafting this plan.
