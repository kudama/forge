# Mac startup and recovery

Ollama and the Forge controller run as the logged-in user using launchd. They
start after login and recover after process exit, with a 30-second restart
throttle. They require no new Python dependency or administrator service.
FileVault requires unlocking the Mac after reboot. Login startup is configured;
an actual logout/reboot validation remains for the operator. Sleep settings are
independent of this setup and are unchanged.

## Install and operate

From the Forge checkout, after following the existing controller setup:

```sh
.venv/bin/python scripts/mac_services.py install
# Stop the manual controller and verified manual Ollama instance first.
.venv/bin/python scripts/mac_services.py start
.venv/bin/python scripts/mac_services.py status
```

Definitions live in `~/Library/LaunchAgents/org.forge.local.ollama.plist` and
`org.forge.local.controller.plist`. Installation refuses to overwrite differing
definitions. Paths are absolute: moving the checkout requires unloading/removing
these definitions and reinstalling from the new checkout. Do not also use
Homebrew services or another Ollama launcher on port 11434. The controller keeps
its existing single-instance guard and SQLite locking.

```sh
# Stop both services for backups or maintenance; they resume at next login.
.venv/bin/python scripts/mac_services.py stop
# Start both again in the current login session.
.venv/bin/python scripts/mac_services.py start
# Stop and remove definitions to disable future login startup.
.venv/bin/python scripts/mac_services.py remove
```

While launchd manages them, use this manager rather than the manual controller
stop command: KeepAlive would restart a manually stopped child. Updating source
does not automatically reload processes; stop/start both services after review.
The MCP bridge is still started on demand by Codex, using its private token file.

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
