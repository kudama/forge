# Local Forge MCP connection

The stdio bridge lets a desktop MCP client delegate bounded work to the existing
authenticated controller. It starts on demand with the client and needs no
separate VM, new listening port or login service. Ollama and the controller must
already be running. The bridge does not start them or access SQLite/source files
directly. The controller remains authoritative for identity, role/tool grants,
source scope, deadlines, ownership and model routing.

## Install and credential

The official Python MCP SDK is an **optional** extra; controller-only installations
retain their original dependencies. The separate lock pins the tested SDK and
transitive packages without changing the core lock:

```sh
.venv/bin/python -m pip install -r requirements-mcp.lock
.venv/bin/python -m pip install --no-deps -e .
```

Create a separate controller principal and a credential file containing only its
token. Do not share the full principal database with the bridge. For this local
prototype, from the checkout:

```sh
.venv/bin/python - <<'PY'
import json, secrets
from pathlib import Path
principals = Path('.secrets/principals.json')
credential = Path('.secrets/mcp-token.json')
rows = json.loads(principals.read_text())
if 'forge_mcp' in rows or credential.exists():
    raise SystemExit('Existing configuration preserved; review it before changing.')
token = secrets.token_urlsafe(32)
rows['forge_mcp'] = {'token': token,
    'agents': ['forge', 'repository_analyst', 'implementer'],
    'services': ['prototype'], 'repositories': ['forge']}
principals.write_text(json.dumps(rows, indent=2) + '\n')
principals.chmod(0o600)
credential.write_text(json.dumps({'token': token}) + '\n')
credential.chmod(0o600)
PY
```

Use only an already reviewed `forge` source manifest. Restart the idle controller
with the configured service manager or manual launcher to load grants. Tasks
owned by other principals are inaccessible to `forge_mcp`, and vice versa.
Principal permissions are loaded at controller startup. Rotation/revocation requires changing both private records
as appropriate, restarting the controller and reconnecting the bridge. Never
commit credentials or include bearer values in client settings, argv or logs.

## Register locally

From the checkout, add a unique client server entry:

```sh
codex mcp add forge_local \
  --env "FORGE_MCP_TOKEN_FILE=$PWD/.secrets/mcp-token.json" \
  --env FORGE_CONTROLLER_URL=http://127.0.0.1:8787 \
  -- "$PWD/.venv/bin/python" -m forge_controller.mcp_bridge
```

Settings contain the credential **path**, not the token. Absolute paths permit
launching from any client working directory. `FORGE_MCP_TOKEN_FILE` is required;
`FORGE_CONTROLLER_URL` defaults to `http://127.0.0.1:8787` and this first bridge
accepts only loopback HTTP URLs without embedded credentials/query/path suffixes.
The token file must be a regular owner-only file, not a symlink, with at most
4 KiB and exactly `{"token":"..."}`. SDK stdio uses stdout for protocol messages;
diagnostics go to stderr, with warning-level logging and sanitized upstream errors.

Check `codex mcp get forge_local --json` or the client's MCP settings. Reconnect
or refresh the client session if its tool catalog predates registration. An
SDK stdio test proves the bridge protocol works; it does not prove an already
open chat has refreshed its tool catalog. To remove registration, use
`codex mcp remove forge_local`; revoke the controller principal separately.

## Tools and workflow

| Tool | Meaning |
| --- | --- |
| `forge_health` | Authenticated readiness; no model load |
| `forge_submit_task` | Prompt, existing agent ID, declared read/status tools; returns ID immediately |
| `forge_submit_work_order` | Validated order; controller captures selected source and enforces result scope; returns ID |
| `forge_get_task` | Owner-scoped status, untrusted result and audit |
| `forge_cancel_task` | Explicit queued/running cancellation; terminal records remain terminal |

Submit analyst/implementer tasks with `read_repository_file` in their declared
tools and specific source paths/ranges. Poll using the returned ID until
`succeeded`, `failed` or `cancelled`. Avoid busy polling; queue wait counts toward
the controller deadline. Every inference round uses the configured role model.
The bridge performs no implicit retries: a lost submission response may correspond
to an accepted task. Do not blindly resubmit. Retain known task IDs across client
reconnections; disconnecting does not cancel work. Use explicit cancellation.

Readiness/get are marked read-only; submit/cancel are marked mutating.
Annotations guide the client and do not replace controller authorization. No
delete, direct filesystem, shell, arbitrary model, URL override or patch-application
tool is exposed. Results are returned as structured JSON plus text for clients
that only consume text. Model completion is not a correctness verdict: senior
Forge must review patch applicability, scope and behavior and run relevant tests.
Bridge HTTP calls have a ten-second timeout and responses are capped at 128 KiB.

## Verification and remote access

Verified on 2026-10-04: **116 tests pass**, including 17 bridge tests for MCP
discovery/schema validation, private credentials, role denial/owner isolation,
sanitized/bounded upstream failures, lifecycle/cancellation, and disconnect/reconnect
behavior. A real stdio subprocess performed readiness, both model roles, polling,
cancellation and explicit model unloading. See
[live evidence](experiments/mcp-bridge-2026-10-04.json).
The legacy initialize handshake was also verified with protocol `2025-11-25`,
tool discovery and readiness, alongside the SDK's current default handshake.

Remote clients require a separate supported connection. As checked on
2026-10-04, [OpenAI documents custom MCP apps as web-only](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt).
A tunnel does not enable this workflow in the native ChatGPT mobile app. Verify
the intended ChatGPT surface and account permissions before provisioning remote
access; phone-browser compatibility has not been tested. Supported ChatGPT web
connections can use [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
with an outbound connection from the Mac and no public origin listener.

Cloudflare Tunnel is a candidate for remote access to future platform web apps.
For private apps, pair it with [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/setup/secure-private-apps/private-web-app/)
and a narrow allow policy. Publish only the intended application, keep Ollama and
the controller private, and retain controller authorization and task ownership
behind the application. Browser login alone is not an established ChatGPT MCP
authentication integration; validate that separately if this route is chosen.
An authenticated mobile web task screen is a possible alternative for phone
submission, status and cancellation, using the existing bounded controller.

No remote endpoint, tunnel, OAuth setup or phone connection is installed by this
local milestone. Reuse controller scopes and define remote identity, revocation,
availability and audit behavior before enabling one. A separate VM is not a prerequisite
for the working desktop connection.

Primary references: [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
and [official OpenAI MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
