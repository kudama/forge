# Installation: inspect first, then build the environment

Use this entry point for a new checkout. It runs on Python 3.9+ so Apple's older
system interpreter can diagnose the host; the installed Forge environment must
meet the minimum in `pyproject.toml` (currently Python 3.12). The bootstrap uses
only the standard library and does not require Forge or pytest to be installed.

## 1. Inspect the target

From the checkout:

```sh
python3 scripts/setup.py check
```

The report includes the actual interpreter/pip version, platform, free disk,
existing environment/private state, Homebrew location, default local Ollama
catalog, known login-service definitions and port occupancy. It never prints
credentials or private file contents. A missing runtime is a reported next action,
not an instruction to start another server. A client-only desktop installation
does not need local Ollama; runtime/model observations are informational.

If the selected Python is too old, the report exits nonzero and explains what
to select. The check itself creates no environment or private state. A declared
minimum is not a tested-version matrix: Python 3.12 matches CI; other versions
need their own dependency/test evidence. See the dated [setup evidence](controller.md).

On a fresh Apple Silicon Mac, inspect whether `/opt/homebrew/bin/brew` already
exists if `brew` is absent from PATH. Follow the [official Homebrew installer](https://docs.brew.sh/Installation)
and its shell setup directions when Homebrew is absent. Do not install a second
copy or silently edit shell startup files. Install versioned Python if missing:

```sh
brew install python@3.12
```

## 2. Install with an explicit interpreter

On a Homebrew Mac:

```sh
python3 scripts/setup.py install --python "$(brew --prefix python@3.12)/bin/python3.12"
```

On another host, pass an absolute path to its supported Python. The bootstrap
does not infer that an unversioned `python3` is appropriate for creating a venv.
It upgrades packaging tools before installing the full MCP/test lock, installs
the project editable without a second dependency resolution, checks dependencies
and runs the regression suite. Any failed step stops the workflow.

The installer records its input hashes and Python version in
`.venv/.forge-install.json`. A successful repeat returns `already-installed`
without modifying the environment. If a dependency/test step fails, the incomplete
tool-owned environment remains available; repeat the same command with unchanged
inputs to resume. The installer never deletes a venv. A foreign environment,
symlinked environment, changed inputs or existing private state require a reviewed
upgrade/migration rather than automatic replacement. An environment created by
the earlier manual commands is deliberately considered foreign.

This command installs Python dependencies and runs tests. It does not install
Homebrew/Ollama, download model weights, create/rotate identities, change GitHub
credentials, restore databases, install login services or change existing service
ownership. A completed environment is not a running-controller acceptance result.

## 3. Choose the remaining workflow

- **New controller identity:** follow [private configuration and models](controller.md)
  and [service ownership](mac-services.md). Existing credentials/state are not a
  clean install. Keep model selection and source grants explicit. Identity/service
  setup still uses the current documented commands; further consolidation is
  tracked in [#64](https://github.com/kudama/forge/issues/64).
- **Existing host migration:** use [verified snapshot restore and grant reconciliation](private-network-migration.md),
  then test authenticated readiness/inference and selected-source access. Project
  working copies/history, GitHub credentials and controller state are separate
  acceptance checks. The Foundry project-export/import artifact is not yet a
  supported general-purpose Forge command; #64 retains that work.
- **Desktop MCP client only:** after environment installation, follow
  [MCP registration](mcp.md), using the remote HTTPS controller and explicit
  certificate trust. A dedicated client checkout/environment avoids keeping a
  retired controller environment solely for its Python dependencies.

## Validation boundary

On 2026-11-15, the stock Mac Python 3.9.6/pip 21.2.4 combination produced an
actionable read-only report and was rejected for installation. Tests cover invalid
interpreter probes, foreign/symlinked environments, private state, changed locks,
interrupted setup and idempotent resume. A fresh-environment CI job exercises the
full bootstrap on Linux and macOS with Python 3.12. CI validates environment setup,
not a fresh Mac's Homebrew provisioning, FileVault/login lifecycle, actual model
installation, or network service acceptance. Preserve those separate checks.
