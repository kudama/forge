# Coding-model comparison

Run from the Forge checkout:

```sh
.venv/bin/python evals/coding/run.py qwen3:8b
.venv/bin/python evals/coding/run.py qwen3-coder:30b
```

Requires the selected model installed in the existing loopback Ollama runtime.
No additional dependencies, private credentials, live controller changes, or
write/command tools are required. Results go to ignored `state/coding-MODEL.json`.

Each task uses its own temporary source copy and database through the real
authenticated controller API. The seeded boolean-validation defect exists only
in the bug fixture. Reference retrieval is disabled. Both models receive the same
explicit read instructions, 4096 context, 1024 output tokens, eight allowed tool
calls and a 180-second task deadline. Source reads and model manifests are recorded.
Models are unloaded after their three cases. Run sequentially on the desktop.

The runner **does not apply or execute generated code**. Senior review should:

1. Parse the proposed JSON and check the requested path and edit count.
2. Require exact, unique before-text matches; do not silently repair indentation.
3. Inspect the complete candidate for correct behavior and unrelated changes.
4. For reviewed candidates only, apply to a separate temporary source copy.
5. Run relevant tests against that copy, ensuring its `src` is imported.
6. For generated tests, prove they pass the real implementation and fail a
   narrowly seeded mutation of the behavior under test.
7. Record rejection reasons, correction effort and test results alongside raw
   answers. Commit reviewed evidence under `docs/experiments/`.

These are three small repository-informed cases, not a held-out benchmark or an
autonomy assessment. Single runs, load state and caching prevent reliable speed
rankings. A pass does not grant the model execution or write permissions.
