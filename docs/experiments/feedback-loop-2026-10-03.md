# Initial feedback-loop evaluation

Date: 2026-10-03. Runtime: local Qwen3 8B / Ollama 0.35.1. Context 4096, output limit 512, thinking disabled, temperature zero, eight-call budget. No candidate patches were executed or applied.

## What was built

A manually reviewed example collection; permission- and source-version-aware lexical retrieval; example-use audit records; three versioned cases; a repeatable on/off runner using the real controller; and tests for scope, stale examples, approval status, startup cleanup, reference budgeting, source citations, known false claims, and exact patch applicability. No model-weight update or automatic promotion exists.

## Calibration and review

The initial checker reported 0/3 mechanical passes without examples and 2/3 with them. Senior review found a false float-rejection claim in a nominally passing answer. Add a known-error check and a reviewed correction to the example, then rerun with the same model/source settings. This new answer instead made a false boolean-rejection claim that the checker still missed. Tighten the check and transparently regrade the saved answers, retaining the previous checks and generation/checker hashes.

The final reviewed result is:

| Case | References off | References on |
| --- | --- | --- |
| Current defaults and exact citations | Correct values, but fails requested citation format | Accepted after source verification |
| Strict integer reasoning | Incorrect float claim; rejected | Incorrect boolean claim; rejected |
| Exact candidate patch | Inapplicable; rejected | Inapplicable; rejected |

Final mechanical passes: **0/3 off, 1/3 on**. Both modes successfully read the required sources. The examples-on audits identify the relevant reviewed example. All source hashes remained stable during the second suite. This does not mean all baseline facts were wrong: the default case primarily measures citation-format compliance.

The feedback loop caught its own score limitations through senior review. The collection helped citation completeness on this fixture, but did not establish reliable logic or patch generation. Adding one lesson also changed which reasoning error appeared; this is a regression risk, not a reason to assume retrieved examples always help.

**84 software tests pass.** Those verify controller/retrieval/checker behavior; they do not certify model answers. The initial suite has only three known, non-held-out cases and one fixed-order run per mode, so do not infer broad capability, a reliable improvement rate, or throughput gains.

[First raw report](feedback-loop-first.json) preserves the initial weaker checks. [Second report and senior review](feedback-loop-reviewed.json) preserves the tightened/regraded checks, model answers, example IDs, hashes, and explicit human-readable verdicts. Review attribution is senior engineering assessment, not a model self-grade.

Next: add independent repository tasks and reviewed ground truth, test prompt/model variants against them, and measure accepted results plus review effort. Keep both specialists without write/command access until patch correctness improves consistently.
