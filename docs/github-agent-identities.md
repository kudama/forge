# GitHub agent identities and credential boundary

Design proposal for [Forge #37](https://github.com/kudama/forge/issues/37),
reviewed against current source and GitHub documentation on 2026-10-12.
Related requirements: PLAT-04, PLAT-05 and SEC-01 in the
[platform register](https://github.com/kudama/personal-ai-platform/blob/main/docs/requirements.md).
This specifies a future integration. No App, credential service or GitHub-enabled
worker is installed by this document.

## Identity and ownership

Start with Mike's human identity and one dedicated Forge GitHub App installed on
explicitly selected repositories. Independent persistent domain agents receive
separate Apps only when their responsibilities justify a separate revocation or
permission boundary. Temporary coding workers remain identified by work-order
and task IDs under Forge; they do not need accounts or GitHub credentials.

An installation-authenticated request is attributed to the App. Git commit
author/committer metadata is separately configurable and is not proof of the
authenticated actor. Keep reviewed authorship and worker contribution in the PR
description, with source revision, task IDs, model and reviewer corrections.
Several keys for Mike's account would still act as Mike, so they do not meet this
identity requirement. Current operator-connected tooling may still act as Mike
until a reviewed App integration exists; do not label those requests as bot work.

The trusted Forge execution path publishes only after Forge has reviewed a
proposal and independently validated the resulting branch. Local workers retain
the read-only scope in [work orders](work-orders.md); a succeeded worker task is
neither permission to publish nor acceptance of its output.

## Repository and action matrix

These are proposed executor policies, not current grants. Allowlist numeric
repository IDs plus canonical owner/name; review renames/transfers before use.
Install first on a disposable test repository, then approve repositories one at
a time. Installation on every repository is not the default.

| Actor/path | Repositories | GitHub permissions | Permitted action and approval |
| --- | --- | --- | --- |
| Mike | Repositories Mike already controls | Existing human access | Approve App installation/scopes, review changes, and authorize merges/releases/deployment |
| Forge read path | Selected repository for a reviewed task | Metadata read, Contents read; Issues/PRs read only when needed | Inspect source and task state under the task's data scope |
| Forge branch/PR publisher | One explicitly authorized repository per action | Metadata read, Contents write, Pull requests write | Create task-prefixed branch, commit reviewed files, open/update a draft PR under the user's work request |
| Forge queue recorder | Same issue/PR repository; an explicitly selected user board if separately authorized | Issues write for issue status/comments; PR write for PR operations; user Projects permission only after compatibility verification | Record dated evidence and synchronize the corresponding issue/board; no general board administration |
| Persistent domain agent | Only its reviewed domain repositories | Separate read/write scope derived from actual responsibilities | Disabled until its own interface, grants and verification are reviewed |
| Temporary analyst/implementer | Captured files in a Forge work order | None | Return proposals; no GitHub network action or secret access |

No initial grant for Actions/Workflows, Administration, Secrets, Environments,
Deployments, Members or Checks. Repository write requests that touch workflow
files are rejected; labels/status updates cannot expand scope. App registration,
installation approval and repository security settings stay with Mike.

**GitHub permission scopes do not express the complete action boundary.**
Contents write used for branch publication can also authorize PR merging when
combined with appropriate repository access. There is no token permission that
means only "write feature branches, never merge." The executor must reject
protected/default-branch writes, force pushes, deletes, merge and auto-merge
endpoints, unsolicited review requests, release and deployment actions. Protect
the default branch with reviewed rules requiring checks/review and keep the App
off bypass lists where supported. Confirm those rules on the actual account
plan; do not assume all controls are available. Treat the publisher as a trusted
service with powerful repository access. A later merge path needs a distinct
operation policy and explicit user authorization; it is not part of this design's
initial implementation.

## Credential and execution lifecycle

Prefer the selected OpenBao service for private-key storage and controlled
retrieval/signing. Availability, authentication, recovery and signing support are
deployment prerequisites, not claims that OpenBao is working. Do not introduce a
new credential service or export the App private key to workers as a shortcut.
Only the trusted issuer can use that key. Keep signing inside the trusted
boundary; a sign-only integration is desirable if supported and verified.

1. Authenticate the Forge execution caller. Resolve a preconfigured policy by
   principal, repository ID, work-order/task ID and operation. Request text cannot
   supply its own permissions, installation ID, secret reference or API URL.
2. Require a reviewed source revision, permitted file diff, independent validation
   and authorization for the proposed action. A credential grant does not replace
   the user's authorization. For engineering publication, use a separate action
   record referencing the worker order; do not add publication tools to the
   proposal worker's order or repurpose its result contract.
3. The issuer signs a short-lived RS256 App JWT (GitHub permits at most ten minutes
   into the future), then requests an installation token with explicit
   `repository_ids` and `permissions`. GitHub cannot exceed installation grants;
   omitting either restriction broadens to installed defaults and is rejected by
   Forge's policy. Confirm returned repositories, permissions and expiry before
   accepting a token. GitHub installation tokens expire after one hour; stop
   action use earlier if the work request is no longer authorized.
4. Keep the token in the trusted process's memory for the action. Never return it
   to a model, work order, subprocess command line, PR, logs or Git remote URL.
   The future executor should make fixed API calls and structured payloads;
   arbitrary model-selected commands/URLs are not an execution interface. Reuse
   established GitHub libraries if they meet scope and redaction checks. Avoid
   assumptions about token length or format.
5. Recheck action policy immediately before mutation and enforce expected branch
   SHA. Record GitHub's object ID/URL and observed postcondition. On a lost response,
   inspect the known branch/PR and action journal before any retry. Do not create
   duplicate PRs or replay uncertain mutations merely because a worker succeeded.
6. Revoke the action token after use through GitHub's token-revocation endpoint.
   Track a failed revocation as actionable and prevent reuse; expiry remains a
   separate bound. Remove cached token references. Caller/grant revocation blocks
   new issuance and future executor actions immediately; reconcile/revoke already
   issued tokens separately. Removing an installation or suspending it is an
   operator incident response step, with actual denial verified.

Memory-only tokens can be lost when the executor crashes before revocation.
Audit metadata cannot revoke a bearer token by itself. Treat such a token as
potentially usable until its recorded expiry; use operator-controlled installation
suspension/removal for urgent containment and verify the resulting denial. Test
this crash window explicitly rather than claiming immediate revocation on every
failure.

App private keys do not expire automatically. Rotate on a documented schedule and
after suspected compromise: create the replacement, store/verify its fingerprint,
test issuance on the sandbox, switch the issuer, then delete the old key. Track
and revoke existing installation tokens separately; key rotation is not evidence
that an already-issued bearer token stopped working. Retain no private key copies
in repository backups; credential-service recovery belongs to its own approved
backup policy. Fail closed if signing, source validation, policy or audit storage
is unavailable. No fallback to Mike's broad human token.

## Audit contract

Keep private durable action records separate from the controller's proposal
execution records. Record timestamp, authenticated caller, App/installation ID,
repository ID/name, work-order ID, worker task ID/model, reviewer, source revision,
validated diff digest, operation, intended branch/base SHA, approved policy
revision, authorization reference, granted permission names, token expiry,
outcome and GitHub request/object IDs. Link publication back to the reviewed order
without exposing captured source or raw prompts. Record denial and uncertain
outcome distinctly from verified success.

Never record the bearer token, JWT, key material, secret value, credential-bearing
URL or raw HTTP headers/body. Allowlist log fields and test errors as well as
success paths. Retention/deletion and who can read these private records must be
agreed before deployment; GitHub issues receive only concise sanitized evidence.

## Bounded implementation plan and acceptance

| Phase | Deliverable | Prerequisite and independent checks |
| --- | --- | --- |
| 1: policy contract | Fixed read, branch-publication, draft-PR and queue-record operations; explicit identity/action records | Review repository IDs, branch/path restrictions, caller identity, user authorization and allowed API methods; reject forged IDs, workflow files and protected-branch actions offline |
| 2: sandbox issuer | Trusted App JWT/token issuance and redacted lifecycle | Mike authorizes sandbox App/installation; confirmed credential service and private recovery; demonstrate narrowed repository/permission requests, expiry and explicit revocation, key rotation and failure-closed behavior |
| 3: reviewed publication | Source/diff gates, branch lease, draft PR and action journal | Distinct bot attribution observed; deny unauthorized repository/action, stale SHA/source and unreviewed worker result; recover lost responses without replay; scan all logs/outputs for injected test credentials |
| 4: queue integration | Dated evidence and matching issue/board state | Verify user-owned Project authentication/permission support separately; repository-only operation remains usable if board access is unavailable; tests deny unrelated boards/items and permission expansion |

Before enabling a real repository, record actual App/installation IDs, selected
repositories and permissions, credential-service identity and availability,
branch protections/bypass configuration, audit access/retention and approval
owner without credentials. Demonstrate Contents-write merge risk and executor
denial in the disposable repository. Verify token expiry/revocation through real
authenticated requests, not mocks alone. Document incident shutdown and recovery.
Creating an App, installing it, provisioning credentials and enabling publication
need explicit approval of this concrete scope. No implementation/deployment is
claimed by a design PR; #37 remains in Review until its design is accepted.

## Source verification

GitHub behavior checked on 2026-10-12 against primary documentation:

- [Installation authentication and attribution](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation).
- [Installation-token scope and expiry](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app).
- [App JWT claims](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app).
- [Private-key storage and rotation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps).
- [Installation-token revocation](https://docs.github.com/en/rest/apps/installations#revoke-an-installation-access-token).
- [Merge endpoint permission](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request).
- [Choosing App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).

Bounded local consistency check: controller task
`9d12d30f9c9f4e22a7f7eb271030285c`, selected model `qwen3:8b`, no tools, succeeded
with the response "None." to a supplied policy excerpt. It reported no findings;
it is not a security verdict or implementation verification. Forge independently
checked the cited authentication/permission behavior, merge capability and the
crash-before-revocation limitation. Live acceptance remains future work.
