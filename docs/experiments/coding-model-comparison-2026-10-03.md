# Coding-model comparison

Date: 2026-10-03. Base: `82e3f59`. Candidate: Ollama `qwen3-coder:30b`.

## Method

Three small tasks use current Forge source: change the model idle-unload request
from five minutes to two, write an async HTTP-503 adapter regression test, and
repair a boolean-validation defect seeded only in a temporary configuration copy.
These are evaluation fixtures, not requested production behavior changes.

Both models receive the same explicit source-read instructions and use the actual
authenticated controller API, read-only file grants, 4096-token context,
1024-token output allowance, temperature zero, thinking disabled, eight tool calls
and a 180-second deadline. Reviewed-example retrieval is disabled. The output
allowance is larger than earlier 512-token experiments to accommodate complete
tests. No dependency or controller implementation change is needed.

The initial 8B run used less explicit repository/tool wording and failed all three
tasks with `sources_not_read`. Its evidence is preserved separately. The wording
was clarified before the paired comparison; this is not a claim that the initial
and clarified runs used identical prompts.

The runner at [evals/coding/run.py](../../evals/coding/run.py) only generates and
records proposals. Senior review checks exact applicability and semantics before
any candidate is executed in an isolated copy. No model receives write or command
tools. See [review procedure](../../evals/coding/README.md).

## Baseline review

The clarified Qwen3 8B run read the required sources but produced **0/3 accepted
uncorrected proposals**:

- Patch, 2.45 s: requested behavior is correct, but before-text has 24 leading
  spaces instead of the source's 23. Exact application fails. One whitespace
  correction would suffice; no silent correction receives a passing score.
- Test, 4.90 s: `await` appears outside an async function, required Settings
  arguments and imports are missing, and MockTransport uses a nonexistent
  `side_effect` argument. Reject without execution.
- Bug, 1.53 s: the proposed `isinstance(value, (int, bool))` still accepts `True`.
  Reject without correction.

The seeded copy independently produces one failure and 31 passing model-limit
tests; the failure specifically shows `True` accepted for `context_length`.
The untouched checkout passes all 84 existing tests.

## Coding candidate and verified outcome

Qwen3-Coder 30B produced **2/3 accepted uncorrected proposals**. Raw responses,
model digests, source hashes, prompts, read audits and review findings are in
[comparison evidence](coding-model-comparison-2026-10-03.json).

| Case | Qwen3 8B | Qwen3-Coder 30B | Candidate time |
| --- | --- | --- | --- |
| Exact idle-unload patch | Reject: indentation mismatch | Accept: exact scoped edit | 6.21 s |
| HTTP-503 regression test | Reject: invalid Python and APIs | Reject: incorrect mocking | 4.07 s |
| Seeded boolean-validation bug | Reject: still accepts bool | Accept: exact type check | 4.29 s |

The coding candidate's patch and bug fix each passed **all 84 existing tests**
against their isolated source copies. The idle-unload fixture's existing request
test expectation was changed to two minutes for this evaluation; the generated
patch itself required no corrections. The bug candidate restored the strict
validation and resolved the independently demonstrated failure. Main-checkout
source hashes remained unchanged. Neither evaluation patch was applied to the
live controller.

The candidate test ignored the requested `httpx.MockTransport` and used
`AsyncMock` for a streaming context manager. Its `stream()` returns a coroutine,
the raw HTTP response has no associated request, and the original real client
is not closed. Senior review rejected it without execution. No generated test
was accepted, so no generated-test mutation pass is claimed.

Ollama reported Q4_K_M, 30.5B total parameters, an installed size of
18,556,700,761 bytes and 18,864,070,982 bytes (17.57 GiB) loaded entirely in GPU
memory, with context 4096. One model was loaded at a time; the candidate was
unloaded afterward. Baseline memory was not resampled in this run; the earlier
8B comparison recorded about 5.51 GiB. The first candidate task includes loading,
and its other tasks are warm; these times are not a controlled throughput ranking.

## Recommendation

Prefer Qwen3-Coder for the next **reviewed, bounded patch-proposal** experiments;
it handled exact source edits and the boolean bug better in this small sample.
Keep senior review and independent tests mandatory. Test writing remains a
failure for both models and needs a narrower template or more evidence before
it becomes a dependable delegated task. Do not infer broad reliability or add
autonomous command/write access from two successes. The shared controller's
default model remains unchanged pending a separate role-routing decision.

## Limitations

Three repository-informed single attempts do not establish general coding
reliability. Timing includes any model loading and cache effects, with no
controlled repeated speed benchmark. A transport-level succeeded status does
not mean an accepted patch. Correction effort is described qualitatively rather
than treated as a calibrated time measurement. Neither model is trained by this
experiment, and evaluation results do not authorize automatic execution.
