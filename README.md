# AI Forge

AI Forge is an engineering workspace and execution platform for Forge, a master
agent that coordinates specialist subagents on behalf of its operator. Forge
owns planning, architecture, delegation, and final review; subagents carry out
explicitly scoped tasks.

This repository currently implements a prototype controller for local language
models, giving Forge a bounded way to delegate repository analysis and
implementation proposals. Tool permissions and review remain explicit. The
controller is one component of the agent system; it does not independently
provide the master agent's reasoning or a complete autonomous subagent framework.

## What it does

- Coordinates local inference through Ollama, with configurable models per role.
- Accepts authenticated tasks and keeps results isolated by caller.
- Enforces explicit repository file manifests and read-only tool grants.
- Provides deadlines, cancellation, execution limits, and persistent SQLite state.
- Offers an optional local MCP bridge for desktop AI clients.
- Supports reviewed reference examples and repeatable model evaluations.

Repository analysts produce source-grounded proposals. Implementers propose
patches. The controller has no file-write, shell-command, or patch-application
tool; an operator reviews changes and runs independent checks before applying
them. A completed task is not a guarantee that its output is correct.

## Getting started

The prototype uses Python 3.12 or newer and an existing Ollama installation.
Follow [setup and operation](docs/controller.md) to install the Python environment,
configure private credentials and source grants, select installed models, and
start the controller. Credentials and task state stay outside version control.

For desktop integration, see the [local MCP bridge](docs/mcp.md).
For startup and recovery on macOS, see [service management](docs/mac-services.md).

## Architecture and validation

The planned [UX Designer model evaluation](docs/ux-designer-evaluation.md) compares local and hosted design helpers alongside engineering workers. Its requirements and handoff are captured; no evaluation result or deployed designer is claimed.

The [work-order contracts and native enforcement](docs/work-orders.md) define explicit assignment and
result contracts, tested through the current controller compatibility path.

The controller and inference runtime are separate components and can run on
separate hosts. The current validated environment is macOS; deployment to Ubuntu
has not yet been validated. The default services bind to loopback. Remote access
requires a separately reviewed authentication and transport setup.

[Architecture](docs/controller-architecture.md) ·
[Validation](docs/controller-validation.md) ·
[Reviewed examples and evaluation](docs/feedback-loop.md)

Model outputs and repository content are untrusted. Runtime grants remain the
source of authority; prompts cannot expand them. Do not expose raw model or
controller listeners directly to the public internet.

The [AI Forge backlog workflow](docs/backlog.md) uses GitHub Issues for scoped tasks,
local-worker delegation, Forge review and verification.

## License and support

AI Forge is available under the [MIT License](LICENSE), including for commercial
use. This prototype is provided as-is, with no guaranteed support, maintenance
schedule, response time, or service availability. Third-party dependencies and
model weights retain their own licenses.
