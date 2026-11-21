# Implementation review — October 15, 2026

Scope: Forge #48, stacked on #45 (producer/exporter) and #41 (shared core).
The user authorized building the complete path, not installing or merging it.

Confirmed locally: 353 repository regression tests; 16 separate real-API/package
integration cases. Clean scratch-venv installation of the standalone package;
installed local and structured CLI missing-report smoke checks. The actual MKP
was built deterministically, parsed by Checkmk's native manifest reader,
extracted and imported with official Checkmk 2.4 API source pinned to commit
7ccf810373e6a835947377302eba090c3a8d682d. No mocks replace these APIs. The upstream
MKP builder requires GNU tar; Linux CI covers that additional step. macOS testing
does not claim that native-builder execution or any real site installation.

Two bounded no-tool local qwen3-coder:30b review tasks assisted:

- `local-telemetry-review-20261015-01`: proposed path traversal, missing directory
  fsync and missing-versus-zero defects. Rejected after inspecting explicit `..`
  rejection/no-follow traversal, directory fsync after replacement, and tests
  distinguishing absent dictionaries from measured zero. Rename stays within
  one directory/filesystem and replaces a leaf link rather than following it.
- `local-checkmk-review-20261015-01`: proposed stale false-OK, zero-denominator rate
  and required-metric defects. Rejected: the stale path yields CRIT/UNKNOWN before
  returning, zero-denominator rates are intentionally absent, and a zero-valued
  required metric is accepted while an absent one is UNKNOWN. Tests cover each.

Forge performed the architecture, security decisions, implementation and final
review. Local-model completion is not proof of correctness. Raw local-review
packets and hashes remain in the controller workspace's output/shared-pieces;
no credentials or private records were provided to the workers.

Remaining deployment acceptance: actual Checkmk version/edition and endpoint,
application instrumentation/probes, publication schedule, file ownership/group,
wrapper paths, test-site install/discovery, graphs, notification/downtime rules,
stopped producer and recovery. No runtime, server, firewall, notification channel
or permission grant changed. Native host/process availability checks remain
necessary. GitHub CI status is separate evidence recorded in the PR checks.

## 2.5 compatibility follow-up — October 15, 2026

Mike supplied 2.5.0p14 Community; the open Checkmk UI independently confirmed it.
He explicitly authorized installing the server package. The Community Setup menu
and its search have no extension package manager, matching Checkmk's official
commercial-only GUI documentation. The configured SSH login was rejected, so no
package was installed and no server state was changed. Installation awaits an
existing authenticated site shell, not additional authorization.

Package 0.1.1 expands the compatibility boundary through 2.5 (stops at 2.6.0),
with exact release v2.5.0p14 pinned to commit
80e512e3e3132129161881598e1f71f1ea282263 and 129 source hashes. The same 16
integration cases pass against that release and against the 2.4 baseline locally.
CI now runs separate 2.4/Python 3.12 and 2.5.0p14/Python 3.13 jobs, each with the
native Linux package builder. No plugin business logic or protocol changed.
