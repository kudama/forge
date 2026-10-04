# Repository analyst comparison: Qwen3 8B vs 14B

Verified 2026-10-03 on the M5 Max Studio with 48 GB memory. Outcome: **no clear overall quality improvement on this assignment; do not promote 14B as the default on this evidence.**

## Controlled comparison

The identical original analyst assignment was run against both models through authenticated controller HTTP APIs. The 8B baseline was rerun on the same current implementation rather than compared only with an older run. Both had the same role instructions, explicit source manifest, 4096-token context, 512-token output limit, thinking disabled, temperature zero, eight-call budget, and 60-second task deadline. Each model was warmed immediately before its task; warm-up/load time is recorded separately. Tasks ran sequentially, with one loaded model at a time.

The source files were unchanged between runs and verified by SHA-256 after evaluation. Models chose their own read ranges: both read all model.py and config.py; 8B read all pyproject.toml while 14B read its first ten lines. That difference is part of agent behavior, not an operator-supplied context change. Exact prompt, hashes, model manifests/digests, audit paths/ranges, task timing, raw answers, and loaded memory are saved in [comparison evidence](repository-analyst-8b-vs-14b.json).

| Criterion | Qwen3 8B | Qwen3 14B |
| --- | --- | --- |
| Warm task wall time, including polling | 7.51 s | 9.30 s |
| Separate initial model-load measurement | 2.03 s | 1.08 s |
| GPU-resident model memory reported by runtime | 5.51 GiB | 9.38 GiB |
| Correct values and source location | Values correct; contradictory wrong line 14 plus correct line 24 | Values correct; cited lines 24–25, encompassing actual line 24 |
| Proposed settings and defaults | Both settings and unchanged defaults; concrete environment names | Both settings and unchanged defaults; no concrete new environment names |
| Validation proposal | Positive integers only; invalid cases not specified | Positive integers only; invalid cases not specified |
| Meaningful tests | Omitted | Omitted; generic request to test behavior only |
| Behavior/resource implications | Generic uncertainty; overbroad claim about unchanged behavior | Generic uncertainty; no resource analysis |
| Read-only access and audit | Four permitted calls, selected source reads only | Four permitted calls, selected source reads only |

These are senior qualitative assessments, not an automated score or broad benchmark. This is one assignment and one controlled run per model. The 8B response reproduced its earlier first answer verbatim, including the citation error. 14B gave a shorter, cleaner answer but remained incomplete.

For 14B, runtime log telemetry showed a final prompt of 2738 tokens, 211 final generated tokens, and no context truncation. The missing tests in that answer cannot be attributed simply to hitting the configured 512-token output cap or overflowing this context. This does not isolate why instructions were missed or establish general model capability.

## Recommendation

Keep the existing controller default at 8B for now. Retain 14B as an installed comparison candidate. Before granting writes, evaluate a short structured response contract with explicit required sections, and compare both models again under that same contract. Treat prompt/contract changes as a separate experiment. Expand to several representative repository tasks and judge correctness, completeness, source references, and actionable test plans. Consider another coding-focused model only after these measurements.

No source edits were delegated; the model-limit configuration proposal remains unimplemented. The temporary 14B comparison service was stopped after testing and the model was unloaded to release memory. Main controller settings remain unchanged. The downloaded model remains available locally.

## Raw Qwen3 8B response

### Observations

**Hardcoded Values:**
- In `src/forge_controller/model.py` (line 14), the `num_ctx` and `num_predict` parameters are hardcoded to 4096 and 512 respectively.
- These values are used in the `options` dictionary in the `chat` method (line 24).

**Configuration Pattern:**
- `src/forge_controller/config.py` (lines 13-14) defines `model_url` and `model` as default values.
- Environment variables are used to override these defaults (lines 71-73).
- The `Settings` class validates input and enforces constraints (lines 20-45).

### Proposal

**Names and Defaults:**
- Add `context_length` and `max_output_tokens` to the `Settings` class in `config.py` with defaults of 4096 and 512 respectively.

**Validation:**
- Ensure `context_length` and `max_output_tokens` are positive integers.
- Allow these values to be overridden via environment variables (`FORGE_CONTEXT_LENGTH`, `FORGE_MAX_OUTPUT_TOKENS`).

**Usage:**
- Update `model.py` to use these new settings in the `options` dictionary.

**Uncertainty:**
- The exact impact of changing `num_ctx` and `num_predict` on model behavior is unclear without testing.
- The environment variable names and defaults should be consistent with existing patterns.

### Conclusion

The smallest change would be to add `context_length` and `max_output_tokens` to the `Settings` class in `config.py` with appropriate validation and environment variable support. This aligns with the existing configuration pattern and allows for flexibility without altering the model's behavior.

## Raw Qwen3 14B response

The hardcoded values for model context length (`num_ctx=4096`) and maximum output tokens (`num_predict=512`) are found in `src/forge_controller/model.py` at lines 24-25. The existing configuration pattern in `src/forge_controller/config.py` uses environment variables and defaults for settings like `model_url`, `model`, `timeout`, etc.

**Proposal**: Introduce two new configuration parameters, `model_context_length` and `model_max_output_tokens`, in `Settings` class of `config.py` with defaults of 4096 and 512, respectively. These parameters should be validated to ensure they are positive integers. In `model.py`, replace the hardcoded values with references to these new configuration parameters.

**Uncertainty**: The current code does not include validation for these parameters, so adding it would be necessary to ensure robustness. Additionally, the impact of these changes on the model's behavior should be tested, though no tests are claimed to be run here.

The subsequent [required-section comparison](repository-analyst-structured-comparison.md) improved assignment completeness for both models without changing model limits.
