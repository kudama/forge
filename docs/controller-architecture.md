# Controller prototype architecture

Status: initial prototype. Decision date: 2026-10-03.

Use Python 3.12+, FastAPI/Pydantic for strict API inputs, HTTPX for asynchronous model requests, Uvicorn for serving, and standard-library SQLite for task state. These are the first application dependencies in this previously README-only repository. Exact tested application/test versions are recorded in `requirements.lock`; it is a version lock, not a hash-verified supply-chain lock.

The controller owns task lifecycle, identity, tool authorization, deadlines, and audit metadata. The model proposes actions; code checks the tool name, declared task capabilities, argument shape, and authenticated principal's resource grant before executing. The current tool returns a constant synthetic result. Future real tools must provide independent domain-side authorization and explicit person/resource/action scopes.

A single bounded worker consumes an in-memory queue. SQLite persists task IDs, owner, agent, status, times, results, errors, and redacted tool audit metadata. Prompts and intermediate messages stay in memory. Accepted unfinished tasks fail as `interrupted` after shutdown/restart; they are never replayed silently. SQLite task records are authoritative for lifecycle, not domain memory. Admission has a global capacity; queue wait counts toward the task deadline.

One controller process owns one database, enforced with a Unix file lock. Do not use multiple Uvicorn workers or replicas. There is no broker, workflow framework, container requirement, vector database, or distributed scheduler. Fair scheduling, durable resumable execution, and multiple replicas are future requirements, not promises of this prototype.

The adapter talks to the configured Ollama URL; no Mac-specific inference assumption exists in orchestration code. Moving the controller to an Ubuntu VM changes configuration and the launcher. Network separation requires authenticated encrypted connectivity, restricted network access, and tested availability/error behavior. Model inference remains on the GPU host; the controller VM needs no GPU. Host sleep/power policy is an operational choice.

Agent identifiers are `forge`, the read-only `repository_analyst`, and the patch-proposing `implementer`. The implementer can read approved sources and return a candidate patch, with no file-write or command capability; senior Forge reviews/applies it and verifies behavior. The analyst has a separate prompt, explicit repository grants, and source-reading capabilities; roles use the operator-configured model mapping with a shared fallback. Enabling further agents requires intentional capability definitions and tests. Keep domain-specific connectors and knowledge with their domain repositories. API/MCP adapters should implement this permission boundary when added; the optional local stdio facade now implements that boundary through the authenticated task API.

ChatGPT remains the senior engineering interface. The optional
[local stdio MCP facade](mcp.md) now forwards bounded task lifecycle calls through
a dedicated controller principal. It opens no network listener and accesses no
database or source directly. The core controller remains independent of the MCP
SDK. Role-specific models are operator-configured. Client registration and a
successful protocol test do not automatically refresh an already open chat's
tool catalog. Remote ChatGPT/phone access needs a later authenticated transport.
