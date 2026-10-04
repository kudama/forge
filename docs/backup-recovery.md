# Prototype backup and recovery

Run from the Forge checkout:

```sh
.venv/bin/python scripts/backup.py create state/backups/UNIQUE-SNAPSHOT-NAME
.venv/bin/python scripts/backup.py verify state/backups/UNIQUE-SNAPSHOT-NAME
```

Creation uses SQLite's online backup API and can run while the controller is
active. It creates a new private directory; existing snapshots are not replaced.
The snapshot includes task state, controller settings, principal grants, the MCP
credential, repository manifest, reviewed examples, dependency locks and package
metadata. The manifest records file checksums, row count, schema version and Git
revision. Configuration changes during copying cause creation to fail.

Snapshots contain credentials and potentially sensitive task results. Files are
mode 600 and the snapshot directory is mode 700; symlinks and permissive private
inputs are rejected. Keep snapshots out of Git. Checksums detect accidental
damage but are not signatures and cannot protect against someone who can rewrite
both the snapshot and its manifest. FileVault protects the disk while locked;
this script adds no separate backup encryption.

## Restore without touching the live instance

1. Verify the snapshot before copying it. Retrieve the recorded source revision
   from GitHub and rebuild the Python environment using the captured lock files.
   Reinstall the configured model versions independently; model weights, the
   virtual environment, logs and process lock/PID files are not copied.
2. Copy the snapshot into a separate private recovery directory. Keep the
   original snapshot unchanged. Rewrite the copied controller settings so
   `FORGE_DATABASE`, `FORGE_PRINCIPALS_FILE`, `FORGE_REPOSITORIES_FILE` and
   `FORGE_EXAMPLES_FILE` point to the recovery copies. Repository source paths
   must point to a reviewed checkout; do not expand the source manifest.
3. Load those settings into an isolated controller with its own database and
   loopback port. Never start it against the production database. Check
   authenticated readiness, known task status/results/audits, and denial of
   unauthenticated and cross-owner requests. Startup changes queued/running
   records to interrupted failures, without automatic task replay.
4. For a production replacement, first unload the managed services with
   `scripts/mac_services.py stop`. Preserve the existing state, install only the
   verified recovery copies into the configured locations, retain private file
   permissions, and restart with `scripts/mac_services.py start`. Verify MCP
   readiness and known owner-scoped records again. Revoked credentials must not
   be resurrected from an old snapshot; review grants and rotate them as needed.

## Validation and remaining protection

On 2026-10-04, a private snapshot under
`state/backups/2026-10-04-validation` passed SQLite integrity and file checksums.
A temporary restored application loaded the copied configuration, verified real
Ollama readiness, compared all 29 task records including results and audits, and
rejected unauthenticated and cross-owner requests. Production state was not
replaced and the original snapshot stayed unchanged. See
[validation evidence](experiments/backup-recovery-2026-10-04.json).

The test used an isolated ASGI instance, not a reboot or production cutover.
The backup script is covered by regression checks for live snapshots, overwrite
refusal, checksum damage, permissive files and symlink substitution.

This snapshot is on the same disk. Include `state/backups/` in the user's secure
off-host backup and verify restoration from that destination before relying on
it for disk-loss recovery. Off-host copying and existing backup coverage were
not verified here. Retain only the snapshots needed for recovery, respecting task
data retention and credential revocation. No recurring backup job is installed.
