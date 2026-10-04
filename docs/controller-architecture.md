# Controller prototype architecture

Status: initial prototype. Decision date: 2026-10-03.

Use Python 3.12+, FastAPI/Pydantic for strict API inputs, HTTPX for asynchronous model requests, Uvicorn for serving, and standard-library SQLite for task state. These are the first application dependencies in this previously README-only repository. Exact tested application/test versions are recorded in `requirements.lock`; it is a version lock, not a hash-verified supply-chain lock.

The controller owns task lifecycle, identity, tool authorization, deadlines, and audit metadata. The model proposes actions; code checks the tool name, declared task capabilities, argument shape, and authenticated principal's resource grant before executing. The current tool returns a constant synthetic result. Future real tools must provide independent domain-side authorization and explicit person/resource/action scopes.

A single bounded worker consumes an in-memory queue. SQLite persists task IDs, owner, agent, status, times, results, errors, and redacted tool audit metadata. Prompts and intermediate messages stay in memory. Accepted unfinished tasks fail as `interrupted` after shutdown/restart; they are never replayed silently. SQLite task records are authoritative for lifecycle, not domain memory. Admission has a global capacity; queue wait counts toward the task deadline.

One controller process owns one database, enforced with a Unix file lock. Do not use multiple Uvicorn workers or replicas. There is no broker, workflow framework, container requirement, vector database, or distributed scheduler. Fair scheduling, durable resumable execution, and multiple replicas are future requirements, not promises of this prototype.

The adapter talks to the configured Ollama URL; no Mac-specific inference assumption exists in orchestration code. Moving the controller to an Ubuntu VM changes configuration and the launcher. Network separation requires authenticated encrypted connectivity, restricted network access, and tested availability/error behavior. Model inference remains on the GPU host; the controller VM needs no GPU. Host sleep/power policy is an operational choice.

Agent identifiers are `forge` and the read-only `repository_analyst` specialist. The analyst has a separate prompt, explicit repository grants, and source-reading capabilities; both roles share the configured local model. Enabling further agents requires intentional capability definitions and tests. Keep domain-specific connectors and knowledge with their domain repositories. API/MCP adapters should implement this permission boundary when added; this release contains no MCP transport/server.

ChatGPT remains the senior engineering interface. Connecting it to the controller requires a separate API/MCP integration and an explicit trust/permission design; running this service does not grant this chat access automatically.
