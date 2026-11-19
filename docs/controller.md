# Controller setup and operation

## Install

For a fresh environment, start with the [preflight and resumable installer](installation.md).
It handles explicit interpreter selection, packaging upgrades, the MCP/test lock
and checks in one fail-fast command. The manual sequence below remains available
for reviewed development environments and troubleshooting.

Use the commands below from the Forge checkout, one block at a time. Stop on
any failed command. Blocks omit shell comments: interactive zsh may interpret a
pasted `#` line as a command and report `zsh: command not found: #`.

### Python and Homebrew on a fresh Mac

The package declares `requires-python = ">=3.12"`; Python 3.9 is unsupported.
The [CI workflow](../.github/workflows/tests.yml) targets Python 3.12, and the
[historical Mac validation](controller-validation.md) records Python 3.14.8.
There is no multi-version support matrix: the minimum declaration does not prove
that every newer interpreter works with the pinned dependencies. Prefer a
versioned Homebrew Python 3.12 for a new Mac environment to match CI.

Check the host and available tooling first:

```sh
hostname
command -v brew
command -v python3
python3 --version
```

A fresh Mac may have no Homebrew. If `brew` is missing, check whether
`/opt/homebrew/bin/brew` already exists before installing another copy. If absent,
follow the [official Homebrew installation instructions](https://docs.brew.sh/Installation),
including the installer's shell setup steps, then repeat the checks.
Homebrew's default Apple Silicon prefix is `/opt/homebrew`; use the actual
prefix on other installations.

Install [versioned Python 3.12](https://formulae.brew.sh/formula/python@3.12)
if it is not already available:

```sh
brew list --versions python@3.12
```

If absent:

```sh
brew install python@3.12
```

Select its interpreter explicitly; do not rely on an unversioned `python3`:

```sh
FORGE_PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
"$FORGE_PYTHON" --version
```

Before creating a virtual environment, check for an existing one:

```sh
test ! -e .venv && test ! -L .venv
```

If this check fails, preserve the environment and inspect
`.venv/bin/python --version` and `.venv/pyvenv.cfg`. Do not delete or rebuild an
environment used by a running service. A working supported environment can be
reused; a failed or unsupported one needs a deliberate replacement after stopping
its users and preserving its version details. Do not copy a virtual environment
from another Mac.

For a new environment only:

```sh
"$FORGE_PYTHON" -m venv .venv
```

### Install and verify dependencies

Upgrade packaging tools before the editable pyproject installation, then install
the full test/MCP dependency set, matching CI:

```sh
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements-mcp.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
```

`requirements-mcp.lock` includes `requirements.lock` and pins the optional
MCP SDK. The core lock includes pytest but omits MCP; a controller-only runtime
can use it, but the current full test suite imports MCP in
`test_native_mcp_submission`. Install the MCP lock before running that suite or
using the [MCP bridge](mcp.md). Do not change pins merely to bypass an installation
error. Record the interpreter, pip version, failing command and final test summary:

```sh
.venv/bin/python --version
.venv/bin/python -m pip --version
git rev-parse HEAD
```

No global Python packages are required. Keep local secrets and task state outside
Git; `.secrets/` and `state/` are ignored.

### Foundry setup evidence — 2026-11-13

Operator-provided output in the “Install Forge Dependencies” chat and follow-up
request reported:

- The fresh Mac initially had no `brew`.
- Unversioned `python3` resolved to `/usr/bin/python3`, Python 3.9.6;
  `/opt/homebrew/bin/python3` reported Python 3.15.2.
- pip 21.2.4 rejected editable installation of the pyproject-only project.
  Dependency installation also failed to resolve `annotated-types==0.8.0`,
  and pytest was then unavailable. The cause of that resolution failure was not
  independently established; old pip alone is not a confirmed explanation.
- A later installation reported `forge-controller-0.1.0` installed and
  **334 passed, 1 failed, 1 skipped**. The failure was
  `ModuleNotFoundError: No module named 'mcp'` in
  `tests/test_native_work_orders.py::test_native_mcp_submission`.
- Pasted shell comments produced `zsh: command not found: #`.

Source inspection confirms the Python minimum, CI's Python 3.12/MCP-lock install,
the MCP pin and that test's SDK import. Installing the MCP lock is the prescribed
next step; no successful Foundry rerun, complete Python 3.15.2 validation, model
installation, private-config migration, service startup or reboot acceptance has
been observed here. Test counts can change with the checkout revision.

### Existing installation or host migration

Before creating credentials or starting a replacement controller, inspect existing
private configuration, source grants, database, MCP token and handoff journal on
both hosts. Preserve the Macbox identities and task history. Use the
[backup/recovery workflow](backup-recovery.md) to verify a private snapshot and
stage recovery separately; do not overwrite Foundry state or copy an active raw
SQLite file. Reconcile host-specific source paths and the journal's endpoint
identity before cutover. Keep uncertain submissions and receipts; do not replay
them. Reuse or deliberately migrate approved credentials rather than generating
a fresh production principal set. Do not publish private files or token values.

After dependencies/tests pass, inspect `ollama list` and download only missing
configured models. Validate the staged private profile before
[service installation](mac-services.md). Foundry does not become authoritative
until migration and authenticated runtime checks succeed.

For development, create a credential without printing it:

```sh
.venv/bin/python - <<'PY'
import json, secrets
from pathlib import Path
folder = Path('.secrets')
folder.mkdir(mode=0o700, exist_ok=True)
path = folder / 'principals.json'
if path.exists():
    raise SystemExit('Credential file already exists; preserving it.')
path.write_text(json.dumps({'operator': {'token': secrets.token_urlsafe(32),
                                   'agents': ['forge'], 'services': ['prototype']}}, indent=2))
path.chmod(0o600)
PY
```

Each principal needs a unique random bearer token of at least 32 characters, an `agents` list containing `forge`, `repository_analyst`, and/or `implementer`, and `services: ["prototype"]` or `[]`. An optional `repositories` list grants explicit repository IDs. Unknown fields are rejected. The file must have owner-only permissions. Never paste tokens into Git, commands, URLs, logs, or PRs. Rotate/revoke by editing the private file and restarting the controller; in-flight tasks should be stopped during revocation.

For a verified snapshot restore or direct private-network HTTPS, follow
[the migration procedure](private-network-migration.md). The launcher defaults
to loopback; non-loopback binding requires TLS and existing authentication.

## Start locally

If Ollama is not already running, start it in another terminal using the installed binary:

```sh
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_CONTEXT_LENGTH=4096 ollama serve
```

Download `qwen3:8b` and `qwen3-coder:30b` if missing. Do not run a second Ollama
instance on the same port. Copy the reviewed local profile once, preserving any
existing operator configuration:

```sh
test -e .secrets/local-controller.json || cp config/local-controller.example.json .secrets/local-controller.json
chmod 600 .secrets/local-controller.json
.venv/bin/python scripts/controller.py start
```

The launcher validates the private configuration, starts one foreground controller
on loopback, and records its process under ignored `state/`. The profile preserves
8B analysis, the coding-model implementer, explicit source grants and reviewed
examples. Paths are relative to the checkout, independent of the invoking directory.
Credentials remain in the separate private principal file; the profile contains
only settings and file paths. Remove optional manifest/example settings if you
have not configured those features. The launcher starts no Ollama process and
installs no login/background service. Stop an older manually launched controller
before first adopting it. Logs remain in the start terminal.

From another terminal, use:

```sh
.venv/bin/python scripts/controller.py status
.venv/bin/python scripts/controller.py stop
```

Ctrl+C in the start terminal also stops the controller cleanly. Duplicate managed
starts are rejected. Stop verifies the recorded process command before signaling
it and never stops an unrelated Ollama instance. Ollama remains available; unload
models with `ollama stop qwen3:8b` and `ollama stop qwen3-coder:30b` when finished.

In another terminal from this checkout:

```sh
export FORGE_PRINCIPALS_FILE="$PWD/.secrets/principals.json"
export FORGE_CLIENT_PRINCIPAL=operator
.venv/bin/python -m forge_controller.client --status-tool \
  'Check the prototype service with the status tool and identify whether the result is synthetic.'
```

The convenience client reads the development principal file and prints a task ID and result. It is not a credential-distribution mechanism: remote clients should receive only their own token. Ctrl+C in the client requests task cancellation. A client wait timeout leaves the task addressable by its ID.

## Read-only repository analyst

Set `FORGE_REPOSITORIES_FILE` to an operator-owned JSON manifest outside Git:

```json
{
  "forge": {
    "root": "/absolute/canonical/path/to/forge",
    "files": ["src/forge_controller/model.py", "src/forge_controller/config.py", "pyproject.toml"]
  }
}
```

Grant the intended principal `agents: ["forge", "repository_analyst"]` and `repositories: ["forge"]` in its private credential record. Submit an analyst task with `agent: "repository_analyst"` and `tools: ["list_repository_files", "read_repository_file"]`. The convenience CLI currently submits only the original `forge` tasks; use the HTTP API for analyst tasks. Configure an adequate tool budget (`FORGE_TOOL_ROUNDS=8` was used for the first experiment).

The analyst can list only manifest entries and read up to 80 numbered lines per call (at most 12 KiB returned). A line is LF-terminated, exactly as git and editors number it; other Unicode line separators (form feed, U+2028 and similar) do not start a new line. Work orders reject sources containing carriage returns (`unsupported_line_endings`) because exact-replacement admission cannot rely on them. Approved files must be non-hidden `.py`, `.md`, or `.toml` sources. File reads are limited to 64 KiB, reject symlinks at every component, and reject non-regular/multiply-linked files and invalid UTF-8. Neither listing nor reading uses a command-execution tool. Selecting a source for the manifest is an operator responsibility: even source files may contain secrets and must be reviewed before granting access. Keep the manifest restricted to selected source files, not an entire home directory.

Every read rechecks principal repository permission, requested task capability, path membership, argument shape, and limits. Approved file/range metadata is audited without source content. A task cannot finish as an analyst without at least one successful source read (`sources_not_read`); this does not prove its conclusions are correct. Source content remains untrusted. Reports require senior review; see the [first experiment](experiments/repository-analyst-2026-10-03.md).

## Patch-only implementer

The `implementer` role uses the same explicit source manifest and read tools, with separate instructions to return proposed patch text. Grant it only when intended by adding `implementer` to the principal's `agents` list. Submit with `agent: "implementer"` and `tools: ["read_repository_file"]` (listing is optional). It must successfully read a source before completing.

This role cannot apply patches, edit files, or execute commands. Returned patch text is untrusted: senior Forge reviews source applicability, syntax, scope, and behavior before applying it to an isolated checkout and running tests. Task status `succeeded` means a model response was returned, not that a patch was accepted or verified. See the [first implementation experiment](experiments/implementer-model-limits.md).

## Configuration

Optional role routing uses operator-owned configuration:

```sh
export FORGE_ROLE_MODELS='{"implementer":"qwen3-coder:30b"}'
```

Install each selected model first. `forge` and `repository_analyst` then retain
`FORGE_MODEL` (8B by default), while implementer tasks use the coding model.
Unspecified roles use `FORGE_MODEL`; an empty mapping preserves previous behavior.
Only the three existing roles and nonempty model-name strings are accepted.
Clients cannot supply a model in task input. All inference rounds for a task use
its role's model, and a `model_selection` audit entry records that selection
without consuming the tool budget. Missing models fail; there is no runtime
fallback to another model. Readiness requires every effective role model installed
and checks tags without loading them. Evaluation reports record actual role models.

Keep the single controller worker and Ollama `OLLAMA_NUM_PARALLEL=1` /
`OLLAMA_MAX_LOADED_MODELS=1` settings shown above. The controller serializes its
tasks; Ollama manages loading and eviction. Those runtime limits are deployment
settings, not enforced against unrelated clients by the controller. Switching
roles can add model-loading latency. The larger model occupied about 17.6 GiB
with context 4096 in the prototype comparison.

| Setting | Default / requirement |
| --- | --- |
| `FORGE_PRINCIPALS_FILE` | Required path to private principal grants |
| `FORGE_REPOSITORIES_FILE` | Optional private path to explicit source manifest |
| `FORGE_DATABASE` | `state/tasks.sqlite3`; local disk owned by service account |
| `FORGE_MODEL_URL` | `http://127.0.0.1:11434`; trusted operator configuration |
| `FORGE_MODEL` | `qwen3:8b` |
| `FORGE_ROLE_MODELS` | JSON role-to-model mapping, default `{}` |
| `FORGE_EXAMPLES_FILE` | Optional reviewed example collection; see [feedback loop](feedback-loop.md) |
| `FORGE_CONTEXT_LENGTH` | Positive integer; default 4096 context tokens |
| `FORGE_MAX_OUTPUT_TOKENS` | Positive integer; default 512 output tokens |
| `FORGE_TASK_TIMEOUT` | 60 seconds of execution, measured from dispatch (queue wait is not counted) |
| `FORGE_QUEUE_TIMEOUT` | 600 seconds a task may wait before dispatch; positive number |
| `FORGE_CAPACITY` | 8 admitted tasks, including running work |
| `FORGE_TOOL_ROUNDS` | Maximum 3 total tool calls |
| `FORGE_CONTROLLER_URL` | Client URL, default `http://127.0.0.1:8787` |
| `FORGE_CLIENT_PRINCIPAL` | Configured principal name; set explicitly (for example, `operator`) |

Model calls default to 4096-token context and at most 512 output tokens; both limits can be overridden at startup. Thinking is disabled, temperature is 0, and models unload after five idle minutes. Model responses are limited to 64 KiB; HTTP request bodies to 32 KiB; prompts to 8000 characters. One task runs at a time. There is no automatic external-model fallback. New limits must be actual positive integers; booleans/fractional/string programmatic values and malformed environment values are rejected. Operator overrides can increase memory use, output length, latency, and deadline risk; practical upper bounds need workload measurements.

## API

All routes except liveness require `Authorization: Bearer <token>`. There is no public interactive documentation route.

| Route | Behavior |
| --- | --- |
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database write probe and configured model availability; no inference load |
| `POST /v1/tasks` | Accept `{ "agent": "forge", "prompt": "...", "tools": ["get_service_status"] }`; tools default to none; return 202 and ID |
| `POST /v1/work-orders` | Submit a source-pinned order; immutable selected-file snapshot and structured result enforcement; see [work orders](work-orders.md) |
| `GET /v1/tasks/{id}` | Owner-scoped task status, result, error, and tool audit |
| `POST /v1/tasks/{id}/cancel` | Cancel queued/running task; completed records remain terminal |
| `DELETE /v1/tasks/{id}` | Delete settled terminal record; 409 while active |

Statuses: `queued`, `running`, `succeeded`, `failed`, `cancelled`. Errors include `model_unavailable`, `invalid_model_response`, `tool_denied`, `tool_limit_exceeded`, `deadline_exceeded` (execution exceeded its limit), `queue_expired` (waited too long before dispatch; no inference ran), and `interrupted`. Unknown or another owner's ID returns 404. Invalid credentials return 401; forbidden capability requests 403; invalid input 422; large bodies 413; full admission capacity 503. Cancellation prevents result publication but cannot undo a remote action; only synthetic read-only actions exist here.

## Operation and portability

Stop with Ctrl+C in the server terminal. Active tasks become interrupted; startup also reconciles records left by abrupt termination. No automatic replay. Do not run `--reload`, multiple workers, or concurrent replicas against this database. Keep the database directory private; task results may contain sensitive content. Logs are JSON lifecycle metadata with task IDs, without prompts, responses, credentials, or raw tool arguments. Configure rotation/retention in the chosen launcher before prolonged operation.

The Mac prototype uses the [user-login service manager](mac-services.md) for
Ollama and the controller. To run on Ubuntu, install the same Python environment
and checkout under a dedicated non-admin service account. Place private grants
outside the checkout, set absolute database/config paths, and use a single
`systemd` service process with explicit working directory/environment and restart
throttling. Ubuntu service installation and VM deployment remain later steps.

For a controller on another host, keep raw Ollama on loopback and use a restricted SSH tunnel or an authenticated TLS gateway. Update `FORGE_MODEL_URL` accordingly. Do not expose raw Ollama, publish controller ports to the Internet, or use unencrypted bearer tokens across an untrusted network. Reuse existing private networking. Verify the deployment host firewall and access restrictions before enabling network access.

## Backup, deletion, and recovery

Use the [private backup and recovery workflow](backup-recovery.md) for consistent
live SQLite snapshots and private configuration. Stop the managed services before
any manual raw database copy. Validate restores in a separate private directory
and instance before production replacement. Preserve runtime/model manifests and
dependency versions; exclude reproducible model caches from routine source backups.

There is no automatic retention scheduler in this release. Delete terminal task records through the owner-scoped endpoint and establish retention before ingesting personal data. Deletion is logical; it does not erase existing backup copies or guarantee forensic removal. Full disk/database failure may prevent durable status writes; recover disk/storage first, then restart and reconcile. Do not claim acceptance until backup/restore and failure scenarios are validated in the target deployment.

Native work orders migrate the database to version 2. Back up before upgrade; an
older controller requires a pre-upgrade restore. Generic tasks remain compatible.
See [native scope, retention and rollback](work-orders.md#controller-enforced-work-orders).
