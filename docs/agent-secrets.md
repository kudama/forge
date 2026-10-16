# OpenBao principles for the shared agent foundation

Design requirements added at Mike's request on October 13, 2026. Applies to
Jarvis, Citadel, Forge, Thoth, Hermes, Bear and their specialists. Implements the
design part of SEC-01 alongside PLAT-04; it does not install OpenBao, configure
policies, move credentials or implement a credential client. Actual deployment,
auth method, secrets engines and recovery remain to be verified.

## Credentials belong to trusted adapters

OpenBao is the selected credential store. Models and temporary engineering
workers receive no credential values, OpenBao tokens, unseal/recovery material
or general secret-read tool. A domain service's trusted adapter may use the
credential required for an already-authorized operation. Possessing that
credential does not authorize additional actions or cross-person access.

Agent requests, jobs and configuration retain opaque references when needed,
not secret values. A reference is not authority and is not a caller-selectable
OpenBao path. The adapter maps its registered capability, authenticated identity,
subject and resource to a preconfigured reference. Clients/models cannot override
the secret, provider, endpoint, auth role or policy. Domain argument validators
must reject these override fields, including nested forms allowed by their
schemas. Keep reference names free of personal data or sensitive details.

The shared core currently authorizes before the validator/handler. A future
credential-consuming handler follows this order:

1. Authenticate the person and calling service, then check current exact grants.
2. Validate domain arguments and any required action approval; resolve registered
   target/provider configuration. Reads do not confer write approval.
3. Select the trusted secret reference and authenticate the workload to OpenBao.
4. Retrieve the minimum required credential, validate its usable lifetime and
   use it only inside the domain adapter for the authorized operation.
5. Return sanitized domain data/provenance and static failures; record safe audit
   metadata, then discard cached credential material within its allowed lifetime.

Never put credentials into a `Reply`, source reference, prompt, handoff, journal,
database job arguments, Git remote URL or command-line argument. The core checks
JSON shape and scope; it cannot identify and redact arbitrary secret values in
handler output. Adapter tests must demonstrate this boundary. Do not describe
the current package as enforcing secret isolation by itself.

## Distinct identities and least privilege

Use a separately authenticated workload identity for each service/permission
boundary. Do not share one broad OpenBao token across all bots. Parentage does
not imply a specialist inherits its parent's secrets. The chosen auth method
must match the actual VM/service environment and support identity verification,
bootstrap, expiry and revocation. Reuse an appropriate OpenBao Agent/standard
client where it meets these requirements; do not create a parallel vault or
custom credential broker without a demonstrated need.

OpenBao policies control paths/operations and deny access by default. Prefer
exact, engine-specific paths and minimal capabilities. Avoid wildcard read/list
access, policy/auth administration and token creation for ordinary adapters.
KV engine versions have different API paths; validate the configured engine
rather than copying a generic policy example. OpenBao access controls do not
replace upstream API permissions or the agent's per-person action policy.
[Policy documentation](https://openbao.org/docs/concepts/policies/).

| Agent boundary | Credential principle |
| --- | --- |
| Jarvis / Treasurer | Separate residents' personal accounts from explicitly shared household resources. Treasurer uses upstream read-only finance access; secret retrieval never grants trading/payment authority. |
| Citadel / Steward / Mechanic | Device and host credentials belong to their registered executors. Steward passes job/secret references, not host credentials. Mechanic's operational identity remains separate from software workers. |
| Forge / Engineer / UX Designer | Temporary workers have no secrets. GitHub App signing/publication credentials stay with the trusted Forge publication path described in the identity design. |
| Thoth / Librarian / Curator | Scope catalog/media adapters to the required provider and permitted user's history. Catalog access does not grant host/NAS administration. |
| Hermes / Paparazzi / Publicist | Capture, draft and publication are different grants. Draft generation does not expose publishing credentials; approved publication is performed by its trusted adapter. |
| Bear | Fitness-service credentials stay with its adapter, with per-person data isolation. Bear does not inherit database administrator credentials or other agents' personal accounts. |

No shared runtime root token. Bootstrap/recovery administration is a separate
operator workflow with protected access; ordinary adapters cannot obtain its
materials. Service grants must account for the entire effective policy set,
not just one narrowly named policy. Existing private credential files remain
the current runtime configuration until an explicit migration is tested.

## Lifetimes, rotation and failure

Prefer short-lived workload tokens and dynamic upstream credentials where the
provider supports them. Choose token type deliberately: OpenBao service tokens
support renewal/manual revocation; batch-token behavior differs. Set explicit
lifetime/renewal bounds for the workload and operation; do not silently renew
indefinitely. [Token documentation](https://openbao.org/docs/concepts/tokens/).

Distinguish OpenBao authentication lifetime from upstream credential lifetime.
Dynamic secrets have leases; arbitrary KV secrets do not gain upstream expiry or
revocation merely by being stored in OpenBao. Revoking a vault token or deleting a
KV entry must not be reported as rotating/revoking an external API key. Verify
the actual provider denial and update all authorized consumers after rotation.
[Lease documentation](https://openbao.org/docs/concepts/lease/).

Keep cached material only in the trusted workload for a bounded useful lifetime;
no persisted shared cache by default. Discard on expiry, grant withdrawal,
identity change or rotation. Do not claim Python can reliably erase every copy
from process memory. If a service needs a rendered credential file, separately
review ownership, mode, lifetime, process access and backup exclusion; never
render into Git or general application logs.

Fail closed when authorization, credential lookup, valid lifetime or trusted
transport is unavailable. No fallback to a root token, Mike's broad account,
another bot's credential or an indefinitely stale cached value. A credential
failure is not permission to blindly retry a side-effecting provider request;
use its existing operation receipt and reconciliation contract.

Use private, certificate-verified TLS to OpenBao and supported authenticated
transport to the provider. Bootstrap credentials are provisioned through a
reviewed protected channel, never embedded in application code or prompts.
OpenBao authentication is separate from the core's typed `Principal` object;
constructing the latter is not proof of workload authentication.
[Authentication documentation](https://openbao.org/docs/concepts/auth/).

## Audit, backup and implementation acceptance

Configure OpenBao audit devices and protected application audit storage before
enabling production credential consumption. Application audit records should
contain request/job ID, authenticated workload/person, capability/resource,
opaque reference/version, time and sanitized outcome. Exclude values, bearer
headers, raw provider responses and exception content. Do not assume OpenBao
audit handling protects application logs or every upstream diagnostic. Limit
audit access and retention; confirm failures do not trigger secret disclosure.

Protect and restore OpenBao using the procedure for its actual storage/seal
configuration. Recovery access and required key material must not depend solely
on the vault being restored. Keep operator recovery materials separately
protected and test an isolated restore and authorized access/denial. Synology
may hold approved backups; this does not assume a particular snapshot covers
OpenBao, nor does it change the agreed application-backup policy in Mechanic.

Before claiming an integrated secrets boundary, demonstrate:

- Actual installed version, TLS, auth method, workload identities, engines and
  effective policies; no adapter uses a root/broad shared token.
- Denied cross-agent, cross-person, unknown-reference and forbidden-path reads;
  denied agent calls never reach the credential provider.
- Expiry/renewal limits, token revocation, dynamic lease handling and separately
  verified upstream rotation for static keys.
- Sealed/unavailable-vault and provider failures produce safe outcomes; no
  fallback credentials or uncertain mutation replay.
- Injected test secrets never reach model input, replies, logs, traces, jobs,
  command lines or repository artifacts, including error paths.
- Isolated recovery, rotation propagation and the agreed incident shutdown
  procedure, with evidence excluding credentials.

These are future adapter/deployment acceptance checks, not tests already run by
the current read-only package. Existing Forge work orders, Mechanic operational
grants and [GitHub App identity design](github-agent-identities.md) retain their
authority. Official documentation above was checked October 13, 2026; verify the
actual installed version before translating these principles into policies.
