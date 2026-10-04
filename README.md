# Forge

Forge builds and maintains shared software for the personal AI platform. Domain behavior stays in the Jarvis, Thoth, Hermes, and Bear repositories.

## Controller prototype

A small Python execution service coordinates local inference and explicitly permitted tools. It supports authenticated task submission, owner-scoped results, cancellation, deadlines, and persistent task records. Implemented tools provide synthetic read-only service status and explicitly granted source-file listing/reading for a local repository analyst and patch-only implementer. See the [first analyst experiment](docs/experiments/repository-analyst-2026-10-03.md).

[Setup and operation](docs/controller.md) · [Architecture decision](docs/controller-architecture.md) · [Validation](docs/controller-validation.md)

The controller and model runtime can run on different hosts. Development currently uses the Mac Studio; deployment to Ubuntu is supported by the design but has not yet been tested there. This service is not connected to ChatGPT and does not implement the domain agents or real household connectors.

The optional [local MCP bridge](docs/mcp.md) connects desktop clients to the
controller's authenticated task API using a dedicated scoped principal. Remote
ChatGPT/phone access and domain connectors remain later milestones.

Model context/output limits are configurable at startup. See the [reviewed implementation experiment](docs/experiments/implementer-model-limits.md) for local-model contributions, corrections, and verification.

[Reviewed examples and evaluation loop](docs/feedback-loop.md) provides scoped reference retrieval and repeatable checks with required senior review. It does not automatically train or promote models.

The [coding-model comparison](docs/experiments/coding-model-comparison-2026-10-03.md) records reviewed patch, test-writing and seeded-bug results for Qwen3 8B and Qwen3-Coder 30B, with a repeatable isolated evaluation runner.

[Per-role routing](docs/experiments/role-model-routing-2026-10-03.md) lets operator configuration select a coding model for implementer proposals while retaining the lightweight model for other roles. Tasks record the selected model; missing models fail explicitly.
