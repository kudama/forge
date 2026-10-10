# UX Designer model evaluation — execution plan (issue #32)

Status: in progress. Claimed 2026-10-09; this file records the bounded plan before any
results are collected. Results will be appended in a separate results file with the
same date convention as other experiments.

## Host under test

- Apple Mac Studio, M5 Max, 48 GB unified memory (operator-confirmed).
- Ollama 0.35.1, loopback only, one parallel request / one loaded model.
- Candidate (stage 1): `qwen3-vl:30b` (~19 GB download). Operator directed 30b first;
  staged comparison against `qwen3-vl:8b` is optional and only if 30b leaves
  actionable doubt on specific dimensions.

## Representative cases

Live screens of Training Atlas (`http://sd01web01:8765/`) captured headlessly at
1440x1000 with a local reverse proxy injecting `showPage(<page>)`; captured pages:
overview, fitness, nutrition, sleep, events. These captures contain the operator's
real health data and remain local-only (`atlas_shots/`, not committed). Sanitized
repo fixtures use the synthetic screenshots already published in the Training Atlas
README (`docs/screenshots/*.png`, synthetic sample data).

## Common rubric

Seven dimensions from the issue brief: user-flow reasoning, screenshot
interpretation, navigation, interaction design, visual consistency, accessibility,
actionable feedback. Structured JSON output per run: findings with dimension,
severity, screenshot-grounded evidence, and an engineer-implementable
recommendation, plus a single top priority and open questions. Prompts and runner
are fixed before any candidate runs (`atlas_shots/evaluate_ux.py`, local tooling,
not committed until reviewed).

## Measurements per run

Wall time, prompt tokens, output tokens, tokens/second, plus the structured
response. Model name, Ollama version, and quantization recorded from
`ollama show`. No numerical quality threshold is set in advance (per brief).

## Planned sequence

1. Verify `qwen3-vl:30b` loads within memory budget alongside system overhead.
2. Run the three primary screens (overview, fitness, nutrition), natural theme,
   fixed temperature 0.2, identical prompts.
3. Optional: sleep/events screens, theme variants, and an 8b comparison stage.
4. Operator (Mike) reviews outputs for correctness of screen interpretation;
   model self-scores are not treated as validation.
5. Record results, sanitized samples, and tradeoffs; define the Designer review
   and Engineer handoff contract in a separate reviewed document.

## Out of scope for this evaluation

Hosted model comparison (separate authorization required for any real data),
automation of the review loop, and any controller integration.
