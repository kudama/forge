# Forge v2 deployment, operations, and recovery

Status: new draft for review. Recorded 2026-11-18.
Owns operational requirements, not permission to provision or expose services.

## Objective and deployment proposal

Run a small maintainable shared service with recoverable state and a narrow public
entrance. Proposed topology: gateway/controller on an always-on Proxmox guest,
Foundry for local model execution, ZITADEL Cloud for identity. Co-locate gateway
and controller if safe; do not add a broker, cluster, or new database by default.

Actual host, storage, ingress, domain, firewall rules, and installation tooling
remain open. The absence of a public IP does not prevent local contract tests;
external testing requires a separately authorized reachable test endpoint.

## OPS-01 — Reproducible installation

As operator, I can install and rebuild without private knowledge trapped in a chat.

- Document supported OS/runtime, pinned dependencies, configuration schema,
  service identity, storage paths, and required network flows.
- Version non-secret deployment configuration in Git; resolve credentials locally.
- Preflight host resources, paths, source grants, certificates, identity metadata,
  database compatibility, and worker connection before activation.
- Service startup does not require an interactive login or an open terminal.
- Failed preflight leaves existing working configuration and service intact.
- Record build/commit, configuration revision, schema version, and adapter versions.
- Avoid undocumented live-checkout edits; record any required deployment differences.

## OPS-02 — Ingress and network boundaries

As owner, I can reach Forge publicly without exposing internal infrastructure.

- Public HTTPS serves only approved MCP/discovery and required identity-flow routes.
- Validate routing and authentication independently; a public URL grants no access.
- Use publicly trusted certificates with monitored renewal and expiry.
- Keep management access private and independently authenticated.
- Define explicit gateway-to-service, controller-to-worker, source acquisition,
  monitoring, and backup flows; restrict all other access.
- Authenticate/encrypt traffic crossing hosts; a private address alone is not identity.
- Authenticate and integrity-protect forwarded user identity if gateway and service
  are separate. Reject direct forged identity headers.
- Set request/body/connection/rate bounds compatible with supported MCP transport.
- Validate streaming, timeout, reconnect, DNS, and proxy behavior end to end.
- Neither raw Ollama nor controller administrative endpoints are publicly exposed.

## OPS-03 — Identity and secrets operations

As owner, I can rotate or recover credentials without leaking them.

- Use the [SSO contract](sso.md); do not implement a homegrown identity provider.
- Keep provider admin credentials, internal service credentials, signing keys,
  repository tokens, and backup secrets separate and least-privileged.
- Store secrets outside Git, images, argv, task prompts, artifacts, and routine logs.
- Document rotation, revocation, emergency disablement, and recovery access.
- Validate issuer/audience changes and key rotation without accepting unknown issuers
  or disabling signature/TLS checks.
- Define key-cache refresh behavior and fail safely for invalid/unknown keys.
- Identity-provider outage produces explicit failures; no anonymous fallback.
- Verify free-plan limits and recovery/admin capabilities before depending on them.

## OPS-04 — Health and monitoring

As operator, I can locate faults and avoid unnecessary restarts.

- Monitor gateway/controller/storage, worker reachability, queue age/capacity,
  stale attempts, timeouts, admission failures, disk growth, certificates, and backups.
- Publish version identity and time-stamped component observations.
- Keep readiness and capability-probe results separate.
- Integrate with existing Checkmk/Homebase where useful; do not invent a second
  monitoring platform as a prerequisite.
- Idle/unloaded models are not failures by themselves.
- Alert on actionable failures or freshness thresholds; define thresholds before launch.
- Record outage/recovery evidence without secrets or full task content.

## OPS-05 — Backups and restoration

As owner, I can recover consistent accepted tasks and evidence.

- Define and approve recovery point/time targets, retention, and off-host placement.
- Back up task/receipt/attempt state, identity/grant mappings, snapshots/artifacts,
  configuration references, and required key material through appropriate secure paths.
- Protect backups with encryption and restricted restore access.
- Capture database and artifact consistency; enumerate missing/orphaned objects.
- Include idempotency records/tombstones so restoration cannot silently replay work.
- Treat external ZITADEL identity state separately: document supported exports,
  recovery dependencies, and limits of what a Forge backup can restore.
- Test restore in an isolated environment with dispatch/public access disabled.
- Reconcile tasks accepted after the recovery point before enabling dispatch.
- Deletion from live state does not imply removal from retained backups; document expiry.

## OPS-06 — Upgrade and rollback

As operator, I can make focused changes with a verified recovery path.

- Validate candidate code/configuration against representative tests before rollout.
- Drain or explicitly settle active attempts; do not restart over unknown work.
- Capture rollback artifacts and a consistent backup before schema/config changes.
- Test schema compatibility; rollback may require restoring a matching database,
  artifacts, and idempotency state rather than merely downgrading code.
- Define reconciliation for tasks accepted after the rollback snapshot.
- After startup, verify configured endpoint, authenticated identity, version, source
  capability probe, ownership, and queue state.
- Preserve grants/routing unless the change explicitly includes them.
- Record observed results, remaining work, and next action in GitHub.

## OPS-07 — Failure procedures

Runbooks must cover worker loss, database/storage failure, full disk, stale attempts,
identity-provider outage, certificate expiry, token/key rotation failure, duplicate/
uncertain submission, compromised account, failed upgrade, and backup restore.
For each: symptoms, safe read-only diagnostics, containment, reconciliation,
recovery action, and proof of recovery. Do not prescribe blind restart/retry loops.

## Acceptance and open decisions

Demonstrate clean installation, unattended startup, monitored components, a worker
outage, credential rotation, consistent off-host restore, upgrade/rollback rehearsal,
and external boundary tests in non-production first.

Open: final topology/OS, ingress, domain, secret storage, backup destination,
retention, recovery targets, operational admin access, alert thresholds, and
maintenance windows. Public exposure and production changes need separate authorization.
