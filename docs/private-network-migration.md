# Restore a controller and enable private-network HTTPS

This procedure restores an existing prototype into an unused checkout. It does
not migrate repository working copies, GitHub credentials or model weights.
Use [clean installation](controller.md) first; keep project migration and GitHub
access as separate acceptance checks. No new runtime dependency is introduced.

## Before restoring

- Verify the snapshot using `scripts/backup.py verify`. Keep its original files
  unchanged. Use a current snapshot and pause submissions on the source during
  cutover; otherwise reconcile every task and journal change after the snapshot.
- Install dependencies and selected models on the destination. Compare source
  and destination code revisions; a snapshot does not prove arbitrary versions
  are compatible. The current restorer accepts version-2 snapshots and validates
  database integrity and the destination configuration before publishing files.
- Confirm the target checkout is clean, `.secrets/` and `state/` do not exist,
  and port 8787 is free. The restorer refuses existing private configuration or
  state, including dangling symlinks. It never starts services or changes source
  snapshots, tracked files, model processes or GitHub credentials.
- Choose a stable, specific private IP. Do not use wildcard/public bindings or
  router port forwarding. Use the host firewall/private network controls to
  restrict reachability to intended clients. Authentication remains required.

## TLS and restore

The launcher still defaults to `127.0.0.1:8787`. Private-network binding requires
both `FORGE_TLS_CERTFILE` and `FORGE_TLS_KEYFILE` in the private controller profile.
`FORGE_LISTEN_HOST` accepts a loopback IP or a specific RFC1918 IPv4/ULA IPv6
address. TLS paths must be absolute; key permissions must be owner-only. Invalid
certificate/key pairs fail before the server starts. The port remains 8787.

Use your existing certificate issuer if available. A self-signed certificate is
also suitable when each client explicitly trusts the transferred public
certificate. Include every connection hostname/IP in its subject alternative
names. Do not use `curl -k`, `verify=False` or disable certificate validation.
Keep the private key on the server; distribute only the public certificate over
an already authenticated channel, such as SSH. Arrange certificate renewal and
retain its key in your private recovery system; the controller snapshot does not
currently include TLS keys/certificates. A regenerated certificate needs renewed
client trust.

Example certificate creation (replace example address/name before running):

```sh
mkdir -m 700 "$HOME/forge-tls"
```

Continue only if creation succeeds; do not overwrite an existing TLS directory.

```sh
(umask 077; openssl req -x509 -newkey rsa:3072 -nodes -days 365 \
  -subj '/CN=forge.example.internal' \
  -addext 'subjectAltName=DNS:forge.example.internal,IP:192.168.1.20' \
  -keyout "$HOME/forge-tls/server-key.pem" \
  -out "$HOME/forge-tls/server-cert.pem")
```

Restore from the checkout, mapping only repository IDs whose approved working
copies exist on the destination:

```sh
.venv/bin/python scripts/restore.py /private/path/to/snapshot \
  --repository "forge=$PWD" \
  --host 192.168.1.20 \
  --certfile "$HOME/forge-tls/server-cert.pem" \
  --keyfile "$HOME/forge-tls/server-key.pem"
```

The restore keeps principal identities/tokens, the MCP token, database history,
reviewed examples and all handoff records. Repository mappings retain their
existing selected-file manifests; omitted repositories and their principal
grants are disabled in the destination copy. Original grants remain in the
unchanged snapshot. Add repositories later only after verifying their working
copies and history. The new profile uses absolute destination paths. Failures
before publication leave no installed configuration; an interrupted restore may
leave private directories, which require inspection rather than a blind retry.

## Start only the controller

### Restore grants after the project files arrive

The project importer does not change runtime permissions. For repositories omitted
during controller restore, map their existing approved IDs to destination working
copies using the original verified snapshot. Check the selected source paths:
a canonical GitHub clone can contain design documents while an archived working
copy contains the implementation that was originally approved.

```sh
.venv/bin/python scripts/reconcile_grants.py /private/path/to/snapshot \
  --repository "approved-id=/absolute/path/to/approved/working-copy"
```

This is a dry run. It validates every originally selected file through the actual
source-read policy, preserving the file list and existing credentials. It refuses
changed principal settings, existing conflicting mappings, a previously removed
grant on an already configured repository, unsafe files and active tasks. It
cannot create principals, grant new repository IDs or add source paths.

Repeat with `--apply` to write the validated changes. The command prints a private
`backup_directory` containing the previous principal/manifest files and target
metadata. Keep it private. It writes the manifest before principal grants; the
running controller retains its cached old permissions until restart. Restart only
the controller after a successful apply, with submissions paused:

```sh
.venv/bin/python scripts/mac_services.py stop --role controller
.venv/bin/python scripts/mac_services.py start --role controller
.venv/bin/python scripts/check_source_access.py --repository approved-id
```

The checker reads the existing private profile and MCP token, verifies HTTPS
authentication and waits briefly for startup, then submits one read-only analyst
task per selected repository. A successful result requires both a completed task
and a matching allowed source-read audit record; model prose alone is insufficient.
Receipts print before polling, without credentials or source contents. A timeout
does not imply the task was rejected; inspect its printed ID before retrying.

For rollback, stop only the controller, preserve the changed files separately,
and restore the saved `principals.json` first, then `repositories.json`, to the
targets recorded in `rollback.json`. Do not replace newer configuration changes
without reconciling them. Restart and recheck authenticated readiness. The
database, handoff records, tokens and Ollama are unchanged by reconciliation.

### Service startup

If Ollama already runs on loopback, retain its current owner. Install and start
only the controller, without installing or touching an Ollama LaunchAgent:

```sh
.venv/bin/python scripts/mac_services.py install --role controller
.venv/bin/python scripts/mac_services.py start --role controller
.venv/bin/python scripts/mac_services.py status --role controller
```

`--role` now selects the service for every manager action, including install,
remove and status. Omit it only when you intend to manage both services. Existing
differing service definitions remain protected by the installation guard.

Confirm the listener and certificate locally, then repeat from another host:

```sh
curl --cacert "$HOME/forge-tls/server-cert.pem" \
  https://192.168.1.20:8787/health/live
curl --cacert "$HOME/forge-tls/server-cert.pem" \
  -o /dev/null -s -w '%{http_code}\n' https://192.168.1.20:8787/health/ready
```

Liveness should succeed; readiness without credentials should return 401. Read
a client's private token file in the client process and send its bearer header
only over validated HTTPS. Authenticated readiness must return 200; then submit
one synthetic inference request and verify its terminal result. Do not place
tokens in argv, shell history or shared output. A loaded LaunchAgent or a 200
liveness response alone is not acceptance.

The included checker reads a private token-only credential file and trusts the
specified public certificate. It first checks unauthenticated rejection and
then authenticated readiness. `--inference` deliberately creates one synthetic
task; omit it for a read-only connectivity check. It prints the receipt before
polling so a timeout does not require another submission.

```sh
.venv/bin/python scripts/check_api.py \
  --url https://192.168.1.20:8787 \
  --ca-file "$HOME/forge-tls/server-cert.pem" \
  --token-file "$PWD/.secrets/mcp-token.json" --inference
```

To repeat from another host, transfer the public certificate and checker through
SSH and use that client's existing scoped token-only file. Never transfer the
server private key or share the full principals database with another client.

The existing convenience client, MCP bridge and handoff CLI currently target
local HTTP. This server change does not make those clients HTTPS/network-capable.
Use an HTTPS API client with explicit certificate trust for network acceptance.
Saved handoff records retain their old endpoints: do not rewrite their endpoint
strings or resubmit their work to bypass reconciliation. Verify known task IDs
against the recovered database using authenticated GET requests. Retire source
submissions and reconcile controller identity before moving handoff clients.

To roll back, stop only the destination controller with the service manager;
retain its new state and journal for reconciliation. The source snapshot and old
host are unchanged by restore. Do not restart both hosts as independent writers
and assume their journals will synchronize.

## Evidence and remaining work

2026-11-15: operator reported Foundry's 353 tests pass and both role models are
installed. Its checkout was clean; port 8787 was free, Ollama listened only on
127.0.0.1:11434 and neither Forge LaunchAgent was loaded. The transferred
version-2 snapshot verified with 62 tasks and 5 accepted handoffs. Macbox's task
rows, handoffs, principal grants, repository manifest and reviewed examples still
matched that snapshot at implementation time, with zero active tasks.

Automated validation covers real local HTTPS, certificate trust, authentication,
restore integrity/overwrite refusal, preserved receipts and service selection.
Foundry restore/startup, remote authenticated inference, firewall reachability,
login recovery, GitHub connectivity and complete project/history migration still
require target-host evidence. Do not mark those complete from CI alone.
