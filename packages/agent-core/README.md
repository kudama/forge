# Forge agent core

Small dependency-free Python 3.12+ package for six peer agents and their
specialists. Version 0.1 establishes a shared in-process read boundary and result
contract; domain agents, model loops and deployment remain separate.

The optional standard-library [health/Checkmk adapter](../../docs/agent-health.md)
reads metadata snapshots without network, model or secret access. Services must
still implement their own bounded health producer and domain readiness checks.

Install independently of the Forge controller:

```sh
python -m pip install ./packages/agent-core
python packages/agent-core/examples/peer_handoff.py
```

See [the six-agent design and integration limits](../../docs/agent-core.md).
The example uses synthetic data and locally constructed identities. It is not a
network authentication or deployed Bear/Training Atlas integration example.

## Contract

`Principal` is supplied by a trusted authentication adapter. `Request` is parsed
from bounded strict JSON and has `schema_version`, `request_id`, `target_agent_id`,
`capability`, `subject_id`, `resource_id` and `arguments`. The envelope has no
principal, grant, tool implementation or secret-lookup fields. Domain argument
validators must reject credential/provider overrides inside their own argument
schemas; the generic JSON parser does not know those domain fields.

`Agent.invoke(principal, raw)` requires an exact `Grant` matching the person,
calling peer (or `None` for a human adapter), target agent, capability, subject and
resource. There are no wildcard or implicit household/parent grants. Its fixed
tool registry supplies domain argument validation and handlers. Validators return
`None` for accepted arguments or raise to reject; Boolean returns fail closed.
Authorization
runs before the domain validator or handler. Input dictionaries and grants are
snapshotted so later caller mutations do not change the issued scope/data.

Handlers use `Context.subject_id` and `Context.resource_id` to scope backend
queries. Each read returns a `Reply` with JSON data and at least one `Source`
record containing an opaque source/reference ID and timezone-aware timestamp.
The core checks shape and bounds, not factual truth, freshness or confidence;
those interpretations stay with the owning agent.

Results contain schema version, correlation ID, agent ID, status and static code.
Success includes authorized data and source records. Handler/validator exception
details are not returned. There is no automatic logging of request/result content.
Duplicate JSON keys, non-finite numbers, unknown request fields and invalid types
are rejected. JSON has a 64 KiB bound and maximum nesting depth of 32; result
envelopes as well as data are bounded. This does not bound a handler's execution
time, memory usage or network calls.

Tools marked `write` fail with `action_adapter_required`, including when a grant
matches. Read-only is a trusted handler contract, not an OS sandbox: a Python
handler can perform arbitrary actions if its process credentials permit them.
Use restricted adapters/credentials; do not give models registry objects or
generic shell/database tools. This package cannot enforce a dishonest handler's
declared effect or prevent it from querying the wrong backend scope. Test domain
adapter conformance separately.

The caller adapter authenticates the person AND service before constructing
`Principal`. The constructor itself provides no authentication proof. In a peer
handoff, copying someone's principal ID from text does not establish their grant.
No transport, credential issuer, database, queue, durable memory or automatic
retry is installed here. `request_id` is correlation, not deduplication. Existing
Mechanic mutation receipts/locks and Forge work-order grants remain authoritative
until reviewed integrations adopt this package.

[OpenBao secrets principles](../../docs/agent-secrets.md) define the future
credential-adapter boundary. No secrets client or migration is installed here.

Structured [agent telemetry](../../docs/agent-telemetry.md) adds atomic publication,
a bounded Checkmk exporter, optional measured work/verification/latency/freshness/
usage data, and a separately packaged Checkmk server plugin. The existing local
health-check adapter remains available. No timers, probes or remediation run on
import or during collection.
