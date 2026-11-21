# Forge AI agent Checkmk package

October 15, 2026. The shared core, exporter and server extension were merged in
Forge #41, #45 and #49. Mike then reported **Checkmk 2.5.0p14 Community**; the open
server UI independently confirms that version and edition. Package 0.1.1 tests
Agent Based API v2, Rulesets API v1, Graphing API v1 and native MKP interfaces
against exact official 2.5.0p14 sources as well as the prior 2.4.0 baseline. The
manifest supports 2.4/2.5 and stops at 2.6.0 pending validation. No commercial-only
check feature is used; package installation through the web UI is commercial-only.
Offline compatibility is separate from installation and live polling acceptance.

## Build and install

From the repository root:

```sh
python3 integrations/checkmk/build_mkp.py --output /tmp/forge_agents-0.1.1.mkp
```

The standard-library builder creates a deterministic MKP with `info`,
`info.json` and `cmk_addons_plugins.tar`. It bundles private copies of the core
JSON codec, health and telemetry modules from their single source in
`packages/agent-core`; there is no second maintained protocol implementation.
The Checkmk server requires no Forge controller, model, external Python package,
OpenBao access or network permission for these checks.

Mike authorized server-plugin installation on October 15, 2026. Community
requires a site shell: its Setup menu has no package manager, and a setup search
for Extension packages returned no results. The official MKP guide confirms web
package management exists only in commercial editions. Use an existing approved
SSH/server-shell connection, transfer the reviewed artifact, then run as the
Checkmk site user:

```sh
mkp add /APPROVED/PATH/forge_agents-0.1.1.mkp
mkp enable forge_agents 0.1.1
```

The package installs only under
`~/local/lib/python3/cmk_addons/plugins/forge_agents/`, with `agent_based`,
`rulesets`, `graphing`, `checkman` and private `lib` modules. Do not manually install
those libraries globally. Verify the named files belong to this package before
upgrading or removing it. To roll back, disable this package using the site's
normal MKP management and restore the prior exporter/local-check configuration.
Do not run two alerting paths for one instance unintentionally.

Install the administrator-owned host exporter wrapper separately as described in
[agent-telemetry.md](../../docs/agent-telemetry.md), with a fixed list of expected
identities. Agent-core requires Python 3.12+ on the monitored host; the stock
Checkmk agent's interpreter is not assumed to meet that requirement. The file
publisher/reader uses POSIX filesystem APIs; Windows publication is not supported.
The collector opens no ports and uses the existing authenticated Checkmk agent
connection. Retain the site's certificate and network controls.

## Discovery and policy

Discover services on the approved test host. Each configured identity creates
`AI agent AGENT/INSTANCE`, including missing/invalid producers. Empty or malformed
transport creates `AI agent collector/transport` in UNKNOWN. A previously
discovered identity missing from a section remains UNKNOWN; removal of a service
requires explicit inventory/configuration review. A completely absent section is
handled by Checkmk's native missing-data handling. Keep ordinary host, process,
agent availability and inventory checks enabled so loss of the whole collector
is visible.

In **AI agent health and telemetry**, match the service's agent/instance item and
configure required dependency aliases, required measurements, heartbeat age,
maximum metric window, minimum rate sample size, and optional upper thresholds.
Required dependency policy comes from the server, never from producer claims.
The default heartbeat expiry is 180 seconds and maximum metric window is 3600
seconds; all business thresholds are unset until a workload baseline is agreed.
All configured threshold metrics become required. Missing required data or
insufficient rate samples produce UNKNOWN. See the numeric contract for idle
semantics and execution/verification denominators. Metrics have `forge_` prefixes
and distinct graphs/units. Rolling-window counts are gauges, not counter rates.

Use native Checkmk notification rules, acknowledgement and downtime to decide
who receives which incident; this package creates no notification channels or
automated restarts. Reconciliation pending is a diagnostic count, not permission
to retry an uncertain mutation. OpenBao/model/database aliases must describe
actual bounded observations without secret values, provider URLs or user data.

## Offline verification

The integration suite runs against official Checkmk source, not mocked APIs.
`api-source.lock.json` pins the 2.4.0 baseline; `api-source-2.5.0p14.lock.json`
pins release tag v2.5.0p14, commit 80e512e3e3132129161881598e1f71f1ea282263,
and each source file's SHA-256. The 2.5 release consolidates its plugin APIs in
`packages/cmk-plugin-apis`; test paths include that package. Fetch each lock into
a separate scratch directory, since shared paths have different hashes across
versions. Source files are test inputs and are not included in the MKP. Test dependencies are the repository's existing
pytest/pydantic versions; no application runtime dependency was added.

```sh
python3 integrations/checkmk/fetch_test_api.py /tmp/forge-checkmk-25-api \
  --lock integrations/checkmk/api-source-2.5.0p14.lock.json
export PYTHONPATH=/tmp/forge-checkmk-25-api/packages/cmk-plugin-apis:/tmp/forge-checkmk-25-api/packages/cmk-mkp-tool
python3 -m pytest integrations/checkmk/tests -q
```

Tests build and extract the actual MKP, import its bundled modules with the real
Agent Based/Rulesets/Graphing APIs, validate its manifest with the native MKP
reader, exercise the native MKP builder when GNU tar is present (Linux CI), and
verify report → file → exporter → parse → discovery → server evaluation. No API
stubs are substituted. macOS's BSD tar does not support the native builder's GNU
flags; manifest parsing, extraction, actual API imports and the standard-library
builder still run there. The dedicated Linux CI job exercises the native builder.
This does not substitute for installing, activating changes and polling a real
site. Linux CI and site acceptance are recorded separately from local tests.

## Site acceptance still required

1. Version/edition is confirmed as 2.5.0p14 Community. Obtain the approved site
   shell; confirm agent host registration, real service identity, paths,
   filesystem owner/group/umask and publication cadence.
2. Wire each owning service's measured observations and metrics; the package
   does not claim all six agents already have probes or instrumentation.
3. Install on an approved test site, fetch raw agent data, inspect the structured
   section, discover services, configure policy, activate changes and inspect
   graph units/levels and native missing-data handling.
4. Exercise normal operation, idle, stopped producer, stale data, draining,
   required/optional dependency loss, malformed report, clock skew, an overdue
   work item and recovery. Verify missing metrics stay UNKNOWN when required.
5. Confirm native notifications/downtime and one incident path. Inspect raw agent
   output for personal/secret data before approving broader rollout.

Sources: [official agent plugin guide](https://docs.checkmk.com/2.4.0/en/devel_check_plugins.html),
[MKP management](https://docs.checkmk.com/2.4.0/en/mkps.html),
[Agent Based API source](https://github.com/Checkmk/checkmk/tree/7ccf810373e6a835947377302eba090c3a8d682d/packages/cmk-agent-based),
[Rulesets API source](https://github.com/Checkmk/checkmk/tree/7ccf810373e6a835947377302eba090c3a8d682d/packages/cmk-rulesets),
[Graphing API source](https://github.com/Checkmk/checkmk/tree/7ccf810373e6a835947377302eba090c3a8d682d/packages/cmk-graphing),
[native MKP reader/builder](https://github.com/Checkmk/checkmk/blob/7ccf810373e6a835947377302eba090c3a8d682d/packages/cmk-mkp-tool/cmk/mkp_tool/_mkp.py).

2.5 references: [exact release source](https://github.com/Checkmk/checkmk/tree/80e512e3e3132129161881598e1f71f1ea282263/packages/cmk-plugin-apis),
[current MKP edition/CLI guide](https://docs.checkmk.com/latest/en/mkps.html).
