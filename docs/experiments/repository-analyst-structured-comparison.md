# Repository analyst: required-section comparison

Date: 2026-10-03. Outcome: **both models produced usable reviewed proposals when given explicit required sections; retain 8B as the initial default.** This is a narrow task-completion result, not evidence of unsupervised engineering reliability.

## Method

Repeat the prior context/output-configuration assignment with the same controller code, approved source manifest, model digests, 4096-token context, 512-token output budget, thinking disabled, temperature zero, eight-call limit, and 60-second deadline. Change only the task prompt to explicitly require findings, proposal, validation, tests, and behavior/uncertainty. The prompt specifies positive-integer validation cases and test categories; this therefore assesses grounded completion of an explicit contract, not independent discovery of all requirements.

This is a text-format instruction, not JSON-schema enforcement or automatic quality validation. Each model was warmed immediately before its sequential task. Source hashes match the earlier comparison. Raw prompt, answers, manifests, timings, audit ranges, and hashes are in [structured comparison evidence](repository-analyst-structured-comparison.json).

| Reviewed criterion | Qwen3 8B | Qwen3 14B |
| --- | --- | --- |
| All five required sections | Yes | Yes |
| Hardcoded values/location | Correct values and line 24; uses abbreviated model.py/config.py paths | Correct values and line 24; full repository-relative paths |
| Settings, environment names, unchanged defaults | Concrete and consistent proposal | Concrete and consistent proposal; different context-setting name |
| New-setting validation | Covers zero, negative, non-integer, bool and malformed environment values | Covers the same cases |
| Concrete tests | Default payload, environment overrides, invalid values | Same categories, with bool rejection explicitly included in test examples |
| Behavior and uncertainty | Defaults unchanged; overrides affect resources; measurement needed | Defaults unchanged; overrides may increase resource use; measurement needed |
| Warm task wall time, including polling | 6.11 s | 12.53 s |
| GPU model memory | 5.51 GiB | 9.38 GiB |
| Approved tool calls | 3 | 4 |

The 14B model optionally read pyproject.toml; 8B did not. That extra work contributes to the wall-time comparison; it is not a pure model throughput benchmark. Both read the full approved model.py/config.py ranges. Neither edited source, executed commands, or claimed to have run the proposed tests.

## Senior review and next decision

Both proposals are suitable inputs for a small implementation task after senior review. Prefer the 8B naming from the earlier reviewed proposal (`context_length`, `max_output_tokens`, `FORGE_CONTEXT_LENGTH`, `FORGE_MAX_OUTPUT_TOKENS`) for consistency if implementing it. The 8B answer should spell out full file paths; tests should exercise actual serialized override values, fractional and boolean programmatic inputs, and malformed environment input. The 14B proposal is slightly more explicit, but this single example does not justify doubling task time and greater memory usage as the default.

The first free-form runs omitted tests; these structured runs supplied them. The evidence supports explicit task/output contracts as the next improvement on this assignment. It does not prove the models will reliably comply on unrelated tasks, that the specialist role prompt should be changed universally, or that 8B is broadly superior. Collect several more representative tasks before choosing a general engineering model.

No application settings were changed and no local-model patch was applied. The main controller remains on 8B. The temporary 14B service was stopped and GPU memory released after the comparison; both downloaded models remain available.

## Raw Qwen3 8B response

1. Findings: Hardcoded values are `num_ctx=4096` (model.py:24) and `num_predict=512` (model.py:24). The environment-loading pattern in config.py:71-77 uses `os.environ.get()` with defaults for `FORGE_MODEL_URL`, `FORGE_MODEL`, `FORGE_TASK_TIMEOUT`, `FORGE_CAPACITY`, and `FORGE_TOOL_ROUNDS`.

2. Proposal: Add `context_length` and `max_output_tokens` to Settings. Defaults: `context_length=4096`, `max_output_tokens=512`. Corresponding environment variables: `FORGE_CONTEXT_LENGTH`, `FORGE_MAX_OUTPUT_TOKENS`. Update the `Ollama` class to use these values in the payload.

3. Validation: Reject zero, negative, non-integer, and boolean values for the new settings. Malformed environment values should raise `ValueError`.

4. Tests: Default payload should include `num_ctx=4096` and `num_predict=512`. Override test should use `FORGE_CONTEXT_LENGTH=8192` and `FORGE_MAX_OUTPUT_TOKENS=1024`. Invalid test should use `FORGE_CONTEXT_LENGTH=0` or `FORGE_MAX_OUTPUT_TOKENS=abc`.

5. Impact and uncertainty: Default requests remain unchanged. Overrides affect memory usage, output length, and latency. Measurement is needed for performance and resource usage.

## Raw Qwen3 14B response

1. **Findings**: Hardcoded values for model context length (`num_ctx=4096`) and maximum output tokens (`num_predict=512`) are found in `src/forge_controller/model.py` lines 24. The existing environment-loading pattern is in `src/forge_controller/config.py` lines 72-75, where settings are loaded from environment variables.

2. **Proposal**: Introduce two new `Settings` fields: `model_context_length` and `max_output_tokens`, with defaults of 4096 and 512, respectively. Corresponding environment variables: `FORGE_MODEL_CONTEXT_LENGTH` and `FORGE_MAX_OUTPUT_TOKENS`. Modify the `Ollama` class in `model.py` to use these settings in the `chat` method.

3. **Validation**: Reject zero, negative, non-integer, and boolean values for `model_context_length` and `max_output_tokens`. Reject malformed environment values (e.g., non-numeric strings) for the new settings.

4. **Tests**: 
   - Test 1: Verify default outgoing model payload with `num_ctx=4096` and `num_predict=512`.
   - Test 2: Override the outgoing payload with `num_ctx=8192` and `num_predict=1024` using environment variables.
   - Test 3: Attempt to set `model_context_length` and `max_output_tokens` to invalid values (e.g., 0, "abc", True) and ensure they are rejected.

5. **Impact and uncertainty**: Default requests remain unchanged, but overriding these settings may increase memory usage, output length, and latency. Measurement is needed to quantify the impact of these changes on performance.

Approximate whitespace word counts: 8B 119, 14B 178. The 250-word instruction is evaluated separately from the 512-token generation cap.
