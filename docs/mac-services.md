# Mac startup and recovery

Ollama and the Forge controller run as the logged-in user using launchd. They
start after login and recover after process exit, with a 30-second restart
throttle. They require no new Python dependency or administrator service.
FileVault requires unlocking the Mac after reboot. Login startup was configured on the prototype host;
installation on a replacement host and actual logout/reboot validation must be
verified separately. Sleep settings are
independent of this setup and are unchanged.

## Install and operate

From the Forge checkout, first complete [controller setup](controller.md), including
tests, installed role models and private configuration. On a replacement host,
stage and reconcile existing credentials/state before starting production services.

Inspect current ownership without changing it:

```sh
.venv/bin/python scripts/mac_services.py status
.venv/bin/python scripts/controller.py status
lsof -nP -iTCP:11434 -sTCP:LISTEN
lsof -nP -iTCP:8787 -sTCP:LISTEN
```

Also check existing LaunchAgent definitions, Ollama app login items and Homebrew
services. A `not loaded` result alone does not prove a port is free. Preserve
differing definitions and investigate their checkout paths; do not remove them
just to bypass the install guard.

Once migration/configuration is ready and the service owner is chosen, install:

```sh
.venv/bin/python scripts/mac_services.py install
```

Stop only the identified conflicting manual processes or previous launcher before
starting. If these launchd services are already loaded, do not bootstrap them again.

```sh
.venv/bin/python scripts/mac_services.py start
.venv/bin/python scripts/mac_services.py status
```

Confirm authenticated readiness and an inference request using the private client
workflow in [controller setup](controller.md), then MCP readiness if configured.
A loaded service is not proof that its child is healthy. Record versions, checkout
revision and checks without tokens. Test next-login startup separately; do not
claim reboot acceptance from installation alone.

Interactive zsh may reject pasted `#` comment lines; command blocks below contain
only commands, with their purpose in the surrounding text.

Definitions live in `~/Library/LaunchAgents/org.forge.local.ollama.plist` and
`org.forge.local.controller.plist`. Installation refuses to overwrite differing
definitions. Paths are absolute: moving the checkout requires unloading/removing
these definitions and reinstalling from the new checkout. Do not also use
Homebrew services or another Ollama launcher on port 11434. The controller keeps
its existing single-instance guard and SQLite locking.

Stop both services for maintenance (they resume at next login):

```sh
.venv/bin/python scripts/mac_services.py stop
```

Start both again in the current login session:

```sh
.venv/bin/python scripts/mac_services.py start
```

To deliberately disable future login startup, stop and remove definitions:

```sh
.venv/bin/python scripts/mac_services.py remove
```

While launchd manages them, use this manager rather than the manual controller
stop command: KeepAlive would restart a manually stopped child. Updating source
does not automatically reload processes; stop/start the affected service after review.
The MCP bridge is still started on demand by Codex, using its private token file.

`start` and `stop` without `--role` operate both services, Ollama first and then
the controller. Supply `--role controller` for controller-only maintenance that
keeps the existing Ollama process and loaded models running:

```sh
.venv/bin/python scripts/mac_services.py stop --role controller
.venv/bin/python scripts/mac_services.py start --role controller
```

Use `--role ollama` to select only Ollama. `install`, `remove` and `status`
retain their existing behavior: they operate on both services even if a role is
supplied. The internal `run` action defaults to the controller when no role is
supplied. These selection changes do not reload the running services themselves.

## Settings and logs

Ollama binds only `127.0.0.1:11434`, disables cloud, uses one parallel request and
one loaded model, with a 4096-token default context. Forge binds only
`127.0.0.1:8787` with one worker and reads `.secrets/local-controller.json`.
Credentials remain in private files, outside the launchd definitions. Neither
service exposes a public listener. Models still unload after five idle minutes.

The standard-library runner captures subprocess output into `state/logs/` with
private permissions. Each service log rotates at 1 MiB, retaining three backups
(approximately 4 MiB per service). It forwards termination signals and preserves
the child exit status; launchd cleans up the process group. Controller access
logging stays disabled. Keep Ollama debug logging off and do not add prompt or
credential logging. Runner initialization failures appear as exits in launchd
status; run the runner manually if no log was created.

## Validation

Verified service installation, valid property lists, MCP readiness, loopback
listeners, and automatic controller recovery after killing the verified server
process. Existing regression tests pass. Live evidence is in
[the service experiment](experiments/mac-services-2026-10-04.json).
Startup reconciliation marks interrupted tasks; it does not replay them.
An operator should verify readiness after the next real reboot/login, and test
backup restoration separately before trusting the host with irreplaceable data.
