# Per-role model routing

Date: 2026-10-03. Base: `ef25593`. Implemented and enabled locally with
`FORGE_ROLE_MODELS='{"implementer":"qwen3-coder:30b"}'`. Other roles retain
`FORGE_MODEL=qwen3:8b`. No new dependencies, write/command tools, VM or autostart.

## Local-model contribution and senior review

Qwen3-Coder received a bounded configuration-only assignment through an isolated
controller and explicit source manifest. The combined task failed with
`invalid_model_response`. After splitting it, one task supplied an exact usable
field declaration but omitted validation; the other failed `tool_denied`.
Senior Forge accepted only the declaration and implemented the remaining
validation, resolver, environment loading, adapter/engine routing, auditing,
readiness, evaluation metadata and tests. This is not an autonomous successful
implementation. [Raw evidence and live checks](role-model-routing-2026-10-03.json)
preserve all three proposal outcomes.

## Behavior and verification

- Operator-only role mapping accepts the three existing roles. Omitted roles
  retain the previous default model. Invalid mappings fail startup; unknown task
  model fields are rejected by the existing strict API input.
- Every inference round uses the authenticated task's role. Selection is recorded
  in task audit metadata and does not consume the tool budget. Readiness checks
  all effective models installed without loading them. Missing selections fail
  explicitly; they never retry on the fallback model.
- **99 tests pass**, covering defaults/overrides, invalid configuration and JSON,
  serialized requests through the real adapter, authenticated role routing,
  sequential task processing, missing-model failure, readiness, audit and tool
  budgets. Evaluation records each actual role model and corresponding manifests.
- Live requests switched **8B → Qwen3-Coder → 8B**, and Ollama reported exactly one
  loaded model at each check. The coder completed the source-read smoke task.
  Both 8B attempts on an artificial one-word prompt repeated source reads until
  `tool_limit_exceeded`; routing itself was correct. A separate realistic analyst
  question succeeded with correct defaults and verified config.py:16/:17 citations.
- All three reviewed reference lessons were re-reviewed against the changed
  source and remain accurate; their source hashes were renewed. The live analyst
  follow-up retrieved the current defaults lesson.
- The idle controller was restarted after verifying no active tasks. The Ollama
  process retains loopback binding, cloud disabled, parallelism one and maximum
  loaded models one. Models were unloaded after verification to release memory.

## Operational boundaries

The controller serializes its own work; Ollama enforces runtime loading limits.
Those deployment settings must also be retained when restarting Ollama.
Model switching adds loading latency. The role map is an environment setting;
retain the export in the documented local startup procedure on future restarts.
The controller remains manually started, with shared 4096/512 request limits and
existing deadlines. Task completion still requires review for factual/code quality.

See [operation and routing configuration](../controller.md).
