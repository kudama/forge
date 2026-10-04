# Forge

Forge builds and maintains shared software for the personal AI platform. Domain behavior stays in the Jarvis, Thoth, Hermes, and Bear repositories.

## Controller prototype

A small Python execution service coordinates local inference and explicitly permitted tools. It supports authenticated task submission, owner-scoped results, cancellation, deadlines, and persistent task records. Implemented tools provide synthetic read-only service status and explicitly granted source-file listing/reading for a local repository analyst. See the [first analyst experiment](docs/experiments/repository-analyst-2026-10-03.md).

[Setup and operation](docs/controller.md) · [Architecture decision](docs/controller-architecture.md) · [Validation](docs/controller-validation.md)

The controller and model runtime can run on different hosts. Development currently uses the Mac Studio; deployment to Ubuntu is supported by the design but has not yet been tested there. This service is not connected to ChatGPT and does not implement the domain agents or real household connectors.
