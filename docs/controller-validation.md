# Initial controller validation

Final standalone prototype check, **2026-10-04**: all 99 automated tests pass.
The saved local profile and foreground launcher were verified for start, status,
duplicate-start rejection, clean stop and restart. Final live authentication,
both role routes, queued cancellation, readiness and explicit model unloading
are recorded in [wrap-up evidence](experiments/prototype-wrap-up-2026-10-04.json).
The controller remains manually started; MCP/ChatGPT integration, remote access,
domain connectors and deployment acceptance are later milestones. Earlier
validation counts below describe their respective implementation stages.

Verified 2026-10-03 on the Mac Studio, Python 3.14.8. Ubuntu deployment remains untested.

- 17 automated tests pass: authentication and task ownership; strict input and capability grants; permitted synthetic tool execution; denied model proposals; tool-loop limits; queued/running cancellation; capacity and deadlines; readiness; exclusive database ownership; persisted results and interrupted-task recovery; private credential permissions; body limits and deletion; model response size/HTTP/JSON errors; worker recovery after a model failure; transaction-consistent SQLite backup/restore and rejection of a future schema version.
- A real HTTP request to the running localhost controller completed through Ollama 0.35.1 / Qwen3 8B, using the synthetic status tool. Readiness returned 200; invalid credentials returned 401. The model described the service as healthy and explicitly synthetic; audit recorded one allowed tool call. Initial end-to-end task time was approximately 1.63 seconds.
- The model is `qwen3:8b`, GGUF Q4_K_M, digest `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`. The earlier direct-runtime smoke checks showed 100% GPU residency, approximately 5.5 GiB model memory, and 93–100 generation tokens/second for short warm requests. These are basic checks, not realistic coding-quality or sustained-load benchmarks.

No personal connectors, MCP transport, ChatGPT connection, remote access, VM deployment, or autostart were installed. A restart of the real controller and the documented client were also verified successfully. Deployment backup storage/recovery, real-world permissions, prolonged workload, hard-kill recovery, log rotation, and target-host operation still need deployment validation. The current queue does not replay unfinished tasks after restart.

Repository analyst extension: 35 total automated tests pass, including explicit repository grants, traversal/hidden-file rejection, symlink and hardlink restrictions, file size/type/encoding limits, numbered ranges, cross-role denial, and refusal to complete without a source read. Two real local analyst runs demonstrated source access but only partially satisfactory analysis; see the [experiment and senior review](experiments/repository-analyst-2026-10-03.md).

Model-limit/implementer extension: 70 total tests pass in the isolated and main checkouts. New coverage checks real outgoing default/overridden payloads, strict programmatic/environment limit validation, and both source-reading roles. A real 2048-context/64-output-limit controller request succeeded with runtime-reported context 2048. Local patch outputs needed senior fixes, and generated tests were rejected; see [implementation review](experiments/implementer-model-limits.md).

Feedback extension: 84 software tests pass. Real Qwen3 on/off runs exercised reviewed-example retrieval, citation/source checks, and non-executing patch validation. Senior review rejected nominal passes missed by the initial checks; the regraded suite passes 0/3 off and 1/3 on. See the [feedback evaluation](experiments/feedback-loop-2026-10-03.md); these are narrow fixture results, not a general capability claim.
