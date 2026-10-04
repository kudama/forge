# Reviewed examples and evaluations

Forge now has an explicit feedback loop for its local engineering specialists. Model weights do not change. Improvement comes from reviewed reference material and repeatable task evaluation.

## Reference collection

`examples/reviewed.json` contains short, senior-reviewed engineering lessons, not raw conversation history or model memory. Each example specifies its role, repository, review attribution/date, matching terms, lesson, and exact source SHA-256 hashes. Only records with status `approved` are accepted. Review attribution is metadata, not cryptographic proof of approval: control this file through normal Git review and trusted operator access.

Set `FORGE_EXAMPLES_FILE` to the collection's absolute path when starting the controller. Leave it unset to disable retrieval. The collection must be a regular file not writable by group/others. Invalid/unapproved records fail startup. No API/tool lets a specialist edit the collection, approve its own answer, or automatically add task results.

Retrieval uses simple lexical matching, with no embeddings, vector database, or new dependencies. It filters by agent, current principal repository grants, approved source manifests, and matching source hashes before ranking. It selects at most two examples with a combined 2200-character JSON budget. Examples whose sources change become ineligible until reviewed again; do not blindly refresh hashes. Review their lessons for continued applicability first.

The model receives selected examples as reference data alongside its task; tool permissions and required source reads remain independently enforced. Retrieval is not a substitute for reading current code. Task audit records show selected example IDs. Examples do not consume the model tool-call budget. The initial collection is shared engineering guidance only: keep credentials, personal data, and domain memory out of it.

## Evaluation

From the checkout, configure the same private principal/source-manifest paths used for the controller:

```sh
export FORGE_PRINCIPALS_FILE="$PWD/.secrets/principals.json"
export FORGE_REPOSITORIES_FILE="$PWD/.secrets/repositories.json"
export FORGE_EXAMPLES_FILE="$PWD/examples/reviewed.json"
export FORGE_TOOL_ROUNDS=8
.venv/bin/python -m forge_controller.evaluate --references both \
  --cases evals/cases.json --output state/evaluation.json
```

The selected principal needs `repository_analyst` and `implementer` grants, plus the `forge` repository containing approved config.py/model.py paths. The default model is Qwen3 8B; select another installed candidate with `FORGE_MODEL`. Other controller limits retain their existing environment settings.

The runner uses the same controller implementation in a separate temporary database, through its authenticated ASGI API, and makes real HTTP model requests. It does not require or modify the running service. Cases execute sequentially. Reports record case/checker/corpus/source hashes, model manifest/digest, relevant limits, responses, audits, durations, and pass/fail details; principal tokens are excluded. Report bodies may contain source/user content, so default output stays in ignored `state/`. Source drift is checked before/after the suite.

Current cases cover current limit defaults/citations, strict integer reasoning, and an exact candidate patch. Patch checks parse Python and compare an exact expected edit; they never execute or apply generated code. These are narrow fixture checks, not a general patch verifier. The temperature-change candidate is an evaluation fixture, not an authorized application change.

An exit status of 1 means a mechanical check failed; the JSON report is still saved. It is an expected evaluation outcome, not necessarily a runner crash. Exit status 0 means the listed checks passed, **not** that the answer is correct or safe. Every case is marked `manual_review_required`. Some checks measure explicit response-format compliance; others catch known errors. Neither regex nor syntax parsing can establish general engineering correctness.

## Review and promotion workflow

1. Record raw outputs in ignored state. Inspect their factual accuracy, references, patch applicability, and review effort independently of the score.
2. Distill a verified correction or successful pattern into a short candidate lesson. Include exact source provenance and scope; do not copy an unreviewed model answer as the lesson.
3. Senior Forge reviews the lesson, sets attribution/date/approved status, and updates the collection through Git. The model cannot perform this step itself. Keep the original failed answer separately as evaluation evidence.
4. Run the same cases with references off/on, preserving all other settings. If checks change, record checker versions and regrade stored answers transparently; do not silently replace earlier scores.
5. Review every nominal pass and known failure. Accept a prompt/model/tool change only after enough representative tasks show a useful result without unacceptable regressions or review burden.

The initial on/off suite is fixed-order, one run per case. Cache/loading effects bias wall-time comparisons; reference-enabled results also see distilled lessons relevant to these cases. This is a regression fixture, not a held-out generalization benchmark. Add independent tasks, repeated/counterbalanced runs, and reviewed ground truth before making wider claims. No automatic model promotion, fine-tuning, schedule, or background evaluation was configured.

See the [initial feedback evaluation](experiments/feedback-loop-2026-10-03.md).
