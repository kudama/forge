# Controller setup and operation

## Install

From the Forge checkout, use Python 3.12 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest -q
```

The lock includes test dependencies. No global Python packages are required. Keep local secrets and task state outside Git; `.secrets/` and `state/` are ignored. For development, create a credential without printing it:

```sh
.venv/bin/python - <<'PY'
import json, secrets
from pathlib import Path
folder = Path('.secrets')
folder.mkdir(mode=0o700, exist_ok=True)
path = folder / 'principals.json'
if path.exists():
    raise SystemExit('Credential file already exists; preserving it.')
path.write_text(json.dumps({'mike': {'token': secrets.token_urlsafe(32),
                                   'agents': ['forge'], 'services': ['prototype']}}, indent=2))
path.chmod(0o600)
PY
```

Each principal needs a unique random bearer token of at least 32 characters, `agents: ["forge"]`, and `services: ["prototype"]` or `[]`. Token records require exactly those three fields. The file must have owner-only permissions. Never paste tokens into Git, commands, URLs, logs, or PRs. Rotate/revoke by editing the private file and restarting the controller; in-flight tasks should be stopped during revocation.

## Start locally

If Ollama is not already running, start it in another terminal using the installed binary:

```sh
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_CONTEXT_LENGTH=4096 ollama serve
```

Download `qwen3:8b` if missing (`ollama pull qwen3:8b`). Do not run a second Ollama instance on the same port. Then start the controller:

```sh
export FORGE_PRINCIPALS_FILE="$PWD/.secrets/principals.json"
export FORGE_DATABASE="$PWD/state/tasks.sqlite3"
.venv/bin/uvicorn forge_controller.app:app --host 127.0.0.1 --port 8787 \
  --workers 1 --no-access-log
```

In another terminal from this checkout:

```sh
export FORGE_PRINCIPALS_FILE="$PWD/.secrets/principals.json"
.venv/bin/python -m forge_controller.client --status-tool \
  'Check the prototype service with the status tool and identify whether the result is synthetic.'
```

The convenience client reads the development principal file and prints a task ID and result. It is not a credential-distribution mechanism: remote clients should receive only their own token. Ctrl+C in the client requests task cancellation. A client wait timeout leaves the task addressable by its ID.

## Configuration

| Setting | Default / requirement |
| --- | --- |
| `FORGE_PRINCIPALS_FILE` | Required path to private principal grants |
| `FORGE_DATABASE` | `state/tasks.sqlite3`; local disk owned by service account |
| `FORGE_MODEL_URL` | `http://127.0.0.1:11434`; trusted operator configuration |
| `FORGE_MODEL` | `qwen3:8b` |
| `FORGE_TASK_TIMEOUT` | 60 seconds including queue wait |
| `FORGE_CAPACITY` | 8 admitted tasks, including running work |
| `FORGE_TOOL_ROUNDS` | Maximum 3 total tool calls |
| `FORGE_CONTROLLER_URL` | Client URL, default `http://127.0.0.1:8787` |
| `FORGE_CLIENT_PRINCIPAL` | Development client principal, default `mike` |

Model calls use 4096-token context, at most 512 output tokens, thinking disabled, temperature 0, and five-minute idle unload. Model responses are limited to 64 KiB; HTTP request bodies to 32 KiB; prompts to 8000 characters. One task runs at a time. There is no automatic external-model fallback.

## API

All routes except liveness require `Authorization: Bearer <token>`. There is no public interactive documentation route.

| Route | Behavior |
| --- | --- |
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database write probe and configured model availability; no inference load |
| `POST /v1/tasks` | Accept `{ "agent": "forge", "prompt": "...", "tools": ["get_service_status"] }`; tools default to none; return 202 and ID |
| `GET /v1/tasks/{id}` | Owner-scoped task status, result, error, and tool audit |
| `POST /v1/tasks/{id}/cancel` | Cancel queued/running task; completed records remain terminal |
| `DELETE /v1/tasks/{id}` | Delete settled terminal record; 409 while active |

Statuses: `queued`, `running`, `succeeded`, `failed`, `cancelled`. Errors include `model_unavailable`, `invalid_model_response`, `tool_denied`, `tool_limit_exceeded`, `deadline_exceeded`, and `interrupted`. Unknown or another owner's ID returns 404. Invalid credentials return 401; forbidden capability requests 403; invalid input 422; large bodies 413; full admission capacity 503. Cancellation prevents result publication but cannot undo a remote action; only synthetic read-only actions exist here.

## Operation and portability

Stop with Ctrl+C in the server terminal. Active tasks become interrupted; startup also reconciles records left by abrupt termination. No automatic replay. Do not run `--reload`, multiple workers, or concurrent replicas against this database. Keep the database directory private; task results may contain sensitive content. Logs are JSON lifecycle metadata with task IDs, without prompts, responses, credentials, or raw tool arguments. Configure rotation/retention in the chosen launcher before prolonged operation.

The first deployment is manually started on the Mac. To run on Ubuntu, install the same Python environment and checkout under a dedicated non-admin service account. Place private grants outside the checkout, set absolute database/config paths, and use a single `systemd` service process with explicit working directory/environment and restart throttling. A service-unit installation is a later deployment step; no autostart or VM has been configured by this prototype.

For a controller on another host, keep raw Ollama on loopback and use a restricted SSH tunnel or an authenticated TLS gateway. Update `FORGE_MODEL_URL` accordingly. Do not expose raw Ollama, publish controller ports to the Internet, or use unencrypted bearer tokens across an untrusted network. Reuse existing private networking. The current firewall was observed disabled; network deployment requires verifying firewall and access restrictions first.

## Backup, deletion, and recovery

Stop the controller before copying its database; back up credentials separately through secure recovery storage. Restore to a separate private directory and start one controller against that copy to validate status/results. Use consistent SQLite backups if adding live backups. Preserve runtime/model manifests and dependency versions; exclude reproducible model caches from routine source backups.

There is no automatic retention scheduler in this release. Delete terminal task records through the owner-scoped endpoint and establish retention before ingesting personal data. Deletion is logical; it does not erase existing backup copies or guarantee forensic removal. Full disk/database failure may prevent durable status writes; recover disk/storage first, then restart and reconcile. Do not claim acceptance until backup/restore and failure scenarios are validated in the target deployment.
