# Local implementer: configurable model limits

Date: 2026-10-03. Base: `4d3ed16`. Outcome: implemented and verified, with substantial senior review/corrections. This was **not an autonomous successful patch**.

## Scope and boundaries

Add Settings fields `context_length=4096` and `max_output_tokens=512`, environment overrides `FORGE_CONTEXT_LENGTH` and `FORGE_MAX_OUTPUT_TOKENS`, strict positive-integer validation, and outgoing request wiring. Preserve defaults and other request fields. Approved by the user after the analyst experiment.

Senior Forge added a distinct `implementer` role using the same explicitly granted file-reading tools. The model can return patch text but cannot write files or execute commands. It must read source before completing. Seven bounded tasks used the same local runtime with 4096-token context, 512-token output limit, thinking disabled, and temperature zero. No remote model fallback occurred.

Source reads targeted an isolated detached checkout. Proposed replacements were parsed and inspected by senior Forge; only reviewed edits were applied there. The final tested changes were copied into the main checkout. There is no automatic patch-application endpoint or command tool.

## Review findings

- First 8B task was rejected by the controller as `sources_not_read`; no patch was accepted.
- A retry supplied usable field declarations but a broken validation edit. Accept declarations only; reject the validation edit.
- A smaller 8B validation task still failed the type requirements. Reject it.
- The 14B validation task produced a usable structure but used `isinstance(value, int)`, which accepts booleans. Senior Forge corrected it to `type(value) is int` checks and repaired excess code quote escaping.
- The 14B environment-loading patch required quote-escaping cleanup before exact-source application.
- The 14B request-options patch preserved the intended behavior but its old-line indentation did not exactly match. Senior Forge verified the stripped before/after lines against the expected substitutions and retained original source indentation.
- The 14B proposed test code referenced nonexistent Adapter/helper imports and nonexistent MockTransport behavior. Reject it entirely. Senior Forge wrote the actual transport/configuration tests.

Raw results and audited read paths/ranges are preserved in [implementer evidence](implementer-model-limits.json). Proposal generation succeeded at the transport level for most tasks; that status does not mean code correctness or acceptance.

## Verified implementation

- New limits default to 4096 and 512; environment overrides are parsed at startup.
- Programmatic booleans, strings, floats, None, zero, and negatives are rejected for both fields. Malformed/zero/negative environment overrides also fail startup.
- Mock HTTP transport tests verify default, independent, and combined override values in the actual outgoing request, preserving temperature, thinking, streaming, model, and idle-unload settings.
- Both source-reading roles remain limited by authenticated agent grants, repository grants, explicit file manifests, and source-read completion requirements.
- **70 tests passed** in the isolated checkout and main checkout. Diff whitespace checks passed.
- A real temporary controller with context 2048/output limit 64 returned `LOCAL_LIMITS_OK`; Ollama reported an effective 2048-token context. The output-limit value was verified in transport tests; this tiny live output does not prove long-output truncation behavior.

The temporary services were stopped, model memory released, and the main controller restarted with unchanged defaults. No VM deployment or autostart was configured. Source manifest returned to the main checkout.

## Assessment

The local models supplied some useful boilerplate, but senior correction and independent tests were necessary. This experiment does not justify direct write/command access or promotion of either model as a reliable implementer. Further coding-model evaluation should judge patch applicability, semantic correctness, and review effort, separately from read-only analysis completeness.
