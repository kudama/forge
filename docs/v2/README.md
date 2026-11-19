# Forge v2 specification set

Status: draft requirements for review. Recorded 2026-11-18 (America/Los_Angeles).

This set captures the Forge v2 discussion. It authorizes documentation only.
No implementation, infrastructure provisioning, identity-provider configuration,
paid service, public exposure, migration, or production cutover is authorized.

## Documents

| Document | Owns |
| --- | --- |
| [Architecture overview](architecture.md) | Boundaries, data flow, ownership, and design decisions |
| [SSO workflows](sso.md) | User identity, authorization lifecycle, recovery, and account access |
| [MCP interface](mcp.md) | Client transport, tools, submissions, errors, and task retrieval |
| [Forge service](service.md) | Admission, durable orchestration, scheduling, state, and review |
| [Worker execution and validation](workers.md) | Source delivery, worker protocol, results, and correctness evidence |
| [Deployment, operations, and recovery](operations.md) | Hosting, ingress, secrets, monitoring, backup, and rollback |
| [Acceptance testing and v1 migration](acceptance-migration.md) | Release gates, client matrix, reliability evidence, and cutover |

Cross-cutting requirements have an owning document. Other documents reference that
owner rather than defining a second policy. Requirement IDs are stable within this set.

## Accepted direction versus pending choices

Confirmed user direction:
- Build toward a shared Forge service for Mike and his husband across devices.
- Launch requirements include desktop clients and native iPhone clients.
  A browser fallback is not an accepted replacement.
- Prefer ZITADEL Cloud as identity provider; confirm free-plan suitability and
  actual client compatibility before implementation commitments.
- Do not pursue a manual Synology upgrade for this integration.
- Preserve ChatGPT as senior engineering/architecture/review and local workers
  for bounded work.
- Work is in specification drafting; implementation has not started.

Proposed, not settled:
- Public HTTPS MCP gateway with private execution services.
- Always-on Proxmox hosting for gateway/controller and Foundry for inference.
- Task sharing, scheduling, limits, storage products, retention, recovery targets,
  and quantitative reliability thresholds.

Native iPhone MCP access, token renewal, provider configuration, and client
packaging are unknown until tested. Nothing in these documents claims universal
ChatGPT client support or a currently deployed v2 service.

## Evidence and continuity

The branch was created from main at ea5af8a3a1ba64a69baa6ffeac6ddffe1de49a32.
Existing [controller architecture](../controller-architecture.md),
[MCP bridge](../mcp.md), and [work orders](../work-orders.md) describe v1;
they are not replaced by these future requirements.

Known motivation:
- [Forge #76](https://github.com/kudama/forge/issues/76): denied/unrecognized worker
  tools, source restrictions, rejected results, and misleading readiness signals.
- [Evaluation #110](https://github.com/kudama/forge/issues/110) and
  [handoff audit #111](https://github.com/kudama/forge/issues/111): model trials
  did not establish dependable implementation proposals.
- [Fix #112](https://github.com/kudama/forge/issues/112) /
  [PR #113](https://github.com/kudama/forge/pull/113): duplicate-key rejection;
  a focused fix, not proof of overall handoff reliability.

These links are dated evidence, not execution authority. GitHub issues and
[the backlog workflow](../backlog.md) remain authoritative for implementation
tracking. No board item is marked Building or Done by this documentation commit.

## Next review

Review the four newly drafted documents and resolve the open decisions, especially
the exact client matrix, validation scope, reliability targets, and recovery
policy. Then shape bounded implementation issues if explicitly requested.
