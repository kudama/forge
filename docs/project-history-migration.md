# Project history migration: verify before importing

Project working copies/history and controller private state are separate payloads.
Use [controller migration](private-network-migration.md) for identities, task
history and handoff receipts. This document covers the first supported project
package step: transport verification. General export/import remains tracked in
[#64](https://github.com/kudama/forge/issues/64); the original Foundry scripts are
private task artifacts, not a supported general importer.

## Verify an extracted package

`scripts/project_package.py` reads an already extracted version-1 project-history
package with `manifest.json`, `checksums.json` and `checkouts/`. The original
Foundry export uses that format. It never extracts an archive, invokes Git, runs
packaged scripts, downloads objects, writes a report or changes runtime grants.

Before transfer, obtain the SHA-256 of `checksums.json` on the trusted source:

```sh
shasum -a 256 /absolute/path/to/package/checksums.json
```

Retain that digest through an authenticated channel or a private migration record.
Do not calculate the expected value from an untrusted destination copy. A hash
included beside its payload does not authenticate itself. If transferring an
archive, independently verify its trusted archive digest before extraction with
your reviewed transfer/extraction procedure; this command does not secure archive
extraction. Keep the original export immutable and private.

On the destination, replace the package path and `TRUSTED_SOURCE_DIGEST` with the
actual source value:

```sh
.venv/bin/python scripts/project_package.py /absolute/path/to/package \
  --checksums-sha256 TRUSTED_SOURCE_DIGEST
```

The package root must be an existing canonical owner-only directory. Verification
requires exact agreement between the regular-file/symlink inventory and checksum
manifest, canonical relative names, matching bytes/sizes/executable flags and
consistent working-file records. It rejects hard-linked/special files, duplicate
JSON keys and duplicate/escaping checkout IDs. It does not follow directory
symlinks; a packaged symlink is checked as a link, without opening its target.
An extra import report or other new file makes the immutable export fail the
inventory check. Keep reports outside the exported payload rather than deleting
unrecognized files to make verification pass.

The summary prints counts and the trusted digest, without project contents or
credentials. `git_history_checked: false` and `imported: false` are explicit:
matching transport bytes do not establish complete Git objects, refs/reflogs,
index/stash/working-tree equivalence, safe Git configuration or target readiness.
Do not run Git or scripts from a package merely because this check passed.

Use a quiescent, trusted private package. This verifier is not a filesystem lock
against concurrent writers, an importer, a Git configuration sanitizer or a
replacement for an authenticated transfer. Limits are 16 MiB per JSON manifest
and 100,000 file/link entries. Names are canonical POSIX paths; checkout IDs use
ASCII letters, digits, underscores, hyphens and dots. A package outside these
boundaries needs review rather than automatic conversion.

## Validation and remaining work

2026-11-15: synthetic tests cover read-only verification, unchanged bytes/modes,
legitimate dotfiles/Unicode paths/trailing-dot names, transport tampering, extra
and missing files, executable flags, hard links, directory symlinks, malformed
manifests and a changed checksum file rejected against its original trust anchor.
No live Foundry package or original private migration archive was modified.

Still required for supported end-to-end migration: explicit source inventory and
ignored-file classification, export of independent linked-worktree histories,
full object/ref/index/reflog/stash verification, authenticated account inventory,
canonical project cloning, resumable conflict-safe import, missing-object/cloud
placeholder handling and separate runtime grant reconciliation. Preserve the
existing Foundry evidence without claiming this verifier implements those steps.
