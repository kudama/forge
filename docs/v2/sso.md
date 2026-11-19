# Forge v2 SSO workflows and user stories

Status: draft; initial SSO direction accepted in discussion, open choices remain.
Recorded 2026-11-18. See [index](README.md).

## Objective and responsibilities

Mike and his husband connect individual ChatGPT accounts to the same Forge
service using separate identities. ZITADEL Cloud is the preferred OAuth/OIDC
provider; free-plan suitability and exact client compatibility remain unverified.
Manual Synology upgrades are excluded from this approach.

ZITADEL authenticates; the gateway validates tokens; Forge authorizes every
operation. ChatGPT acts on behalf of the signed-in person. Workers never receive
user tokens or login credentials.

## SSO-01 — First connection

As an approved user, I can connect using my own identity so requests are attributed
to me.

- Connect opens provider sign-in and consent with the configured MFA or passkey.
- Requested access is understandable; cancellation or failure grants no access.
- Successful authorization binds a verified issuer/subject to an approved Forge
  identity. Email/display name alone is not the access-control key.
- Secrets are never pasted into chat.
- An authenticated identity/status tool confirms the effective Forge user.

## SSO-02 — Desktop and iPhone access

As a user, I can connect from desktop and native iPhone clients without copying
local scripts or credentials.

- Launch supports both people on the agreed desktop and native iPhone matrix.
- Each client uses the same Forge service and the same effective identity/grants.
- Submission, status/result retrieval, and authorized cancellation work on both.
- Work submitted on one platform is retrievable on the other.
- Missing connection, expired authorization, and service failure are distinguishable.
- Project membership alone grants nothing.
- Native iPhone support must be demonstrated; a browser fallback requires explicit
  user acceptance and cannot silently replace this requirement.

## SSO-03 — Approved users only

As owner, I can limit Forge to explicitly approved people.

- Initial access is limited to Mike and his husband.
- A valid provider login alone does not grant access.
- A third identity is denied without task or repository disclosure.
- Adding users is an explicit administrative action; public self-enrollment in
  Forge is disabled.
- The gateway/service validate signature, issuer, audience, expiry, and scopes
  and check the local disable/grant state on every operation.

## SSO-04 — Permissions and ownership

As a user, I have scoped access and control over who sees my work.

- Enforce authorized repositories, tools, and actions for every request.
- Bind task ownership to the authenticated creator.
- Guessing an ID cannot expose or cancel someone else's task.
- Sharing requires an explicit policy and grant; the launch sharing policy is open.
- Prompts and model output cannot expand authority.
- Submit access does not imply permission to apply, merge, or deploy.

## SSO-05 — Reconnection

As a user, I can retrieve accepted work after a closed chat or expired connection.

- Closing a chat or losing connectivity does not cancel accepted work.
- After sign-in, the authorized owner can retrieve the durable task ID and result.
- Reconnection does not resubmit work; uncertain submissions are reconciled using
  the [MCP idempotency contract](mcp.md).

## SSO-06 — Expiry and renewal

As a user, I receive understandable renewal and reconnection behavior.

- Use supported token renewal; reject expired/invalid/incorrectly scoped tokens.
- Failed renewal produces a clear reconnect requirement.
- Never fall back to anonymous access or another user's credentials.
- New operations require valid authorization; accepted work follows the recorded
  task policy.

## SSO-07 — Revocation and recovery

As owner, I can remove access without disabling the other person.

- A Forge user-disable control blocks new operations immediately.
- Provider session/token revocation and residual token lifetime are documented and
  tested; provider logout is not assumed to invalidate every issued token instantly.
- Recovery works independently of the affected ChatGPT session.
- Recovery credentials stay outside chat and Git.
- Revocation does not silently transfer or delete records.
- Policy for queued/running tasks after disablement must be chosen before launch.

## SSO-08 — Audit and diagnostics

As owner, I can distinguish sign-in, authorization, and execution failures.

- Log caller, operation, request/task ID, time, and authorization outcome.
- Separate invalid authentication, denied access, service outage, worker failure,
  and rejected output.
- Exclude credentials and full prompts from routine logs.
- Configure audit access and retention explicitly.
- Report component readiness separately from worker capability.

## Acceptance and open choices

The [acceptance plan](acceptance-migration.md) owns the client matrix and evidence.
Both users, a denied third account, renewal, revocation, recovery, isolation,
and a real source-grounded task must be demonstrated.

Open: exact client products/versions; sharing; per-user grants; authentication and
recovery methods; treatment of accepted work after disablement; audit retention;
free-plan entitlements and supported OAuth client-registration mode.

References for later verification:
- [OpenAI MCP authentication](https://developers.openai.com/plugins/build/auth)
- [ZITADEL pricing](https://zitadel.com/pricing)
- [ZITADEL client registration](https://zitadel.com/docs/guides/integrate/dynamic-client-registration)

These references identify verification sources, not evidence of deployed support.
