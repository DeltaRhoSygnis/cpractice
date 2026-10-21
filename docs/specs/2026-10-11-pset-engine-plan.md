# CPractice — Problem-Set Engine Implementation Plan

**Spec:** [`docs/specs/2026-10-11-pset-engine-design.md`](../specs/2026-10-11-pset-engine-design.md)
**Date:** 2026-10-11
**Method:** strict sequencing — each phase ends with green tests before the next.

Every task cites the spec section it serves. No phase touches the deterministic
execution core (`grading/runner.py`, `compiler.py`, `comparator.py`,
`evaluator.py`) except by reading its output.

---

## Phase 0 — Baseline (no production changes)

**Goal:** a recorded baseline so regressions are attributable.

| # | Task | Covers | Verify |
|---|---|---|---|
| 0.1 | Run `pytest -q` and record the pass count. | — | all green, count saved in the PR description |
| 0.2 | Load every package in `problems/` through `ProblemRepository.load_all()` and assert no exceptions. | S8 | a script or test proves the baseline loads |
| 0.3 | Confirm the provider-free path: submit + hint against a saved problem with no provider configured. | S7 | manual/HTTP check passes |

**Exit:** baseline recorded; no code changed.

---

## Phase 1 — Concept ladder and checklist

**Spec:** [S3]

| # | Task | File(s) | Verify |
|---|---|---|---|
| 1.1 | Add `concept` fields to `ProblemMetadata`: `kind` (`exercise`/`problem_set`), `concept.new_concept`, `concept.assumed_known`. Optional; defaults preserve old packages. | `app/schemas/problem.py` | schema test: old payload loads unchanged |
| 1.2 | Add `ConceptPair` model with validation: exactly one `new_concept`; non-empty `assumed_known`; no duplicates. | `app/schemas/pedagogy.py` (or new `concept.py`) | unit tests for each rejection |
| 1.3 | Add checklist + frontier helpers to `curriculum.py`: `concept_tags()`, `frontier(checklist)`, `known_set()`, `forbidden_set()`. | `app/services/curriculum.py` | unit tests: frontier with empty/partial/full checklist |
| 1.4 | Add `required_concepts(problem)` — static scan of the reference + declared topics/skills mapping to stage concepts (loops, arrays, strings, structs, recursion, pointers). | new `app/services/concepts.py` | unit tests against prepared reference snippets |
| 1.5 | Add `ConceptLegalityChecker` producing findings: `concept-above-frontier` (error), `new-concept-known` (error), `empty-assumed-known` (error), `concept-not-declared` (warning). | new `app/services/concepts.py` | tests: legal pair accepted; each illegal case rejected |
| 1.6 | Add `GET/PUT /api/preferences/known-concepts` (or fold into existing settings) to persist the checklist. | `app/api/` | API test: round-trip |
| 1.7 | Backfill: packages with no `concept` block are treated as `kind: exercise` and skip legality checks. | `app/services/problem_service.py` | old packages still list/load |

**Exit:** legality is deterministic and testable; nothing generated yet.

---

## Phase 2 — Distribution-code contract

**Spec:** [S4]

| # | Task | File(s) | Verify |
|---|---|---|---|
| 2.1 | Add `distribution` fields: `has_starter`, `todo_count`, `hint_code` (metadata; optional). | `app/schemas/problem.py` | schema test |
| 2.2 | Add `DistributionChecker`: starter compiles (error), starter passes all tests (error), starter == reference (error), no `TODO` (warning). | new `app/services/distribution.py` | compile+run through existing evaluator with mocked/real gcc |
| 2.3 | Wire `DistributionChecker` into `QualityGate` for `kind: problem_set` only. | `app/generation/quality_gate.py` | gate test: bad starter → invalid; good starter → valid |
| 2.4 | Add a distribution-code requirement to the generation prompt (starter must compile, must not pass, must carry `TODO`s). | `app/generation/prompts.py` + prompt assets | prompt-content assertion test |
| 2.5 | Author one manual `problem_set` package under `problems/` as a fixture. | `problems/<new-pset>/` | repository loads it; reference passes; starter does not |

**Exit:** a pset cannot ship with a solved or non-compiling starter.

---

## Phase 3 — Generator emits a full pset

**Spec:** [S7], [S4], [S3]

| # | Task | File(s) | Verify |
|---|---|---|---|
| 3.1 | Extend `GenerationRequest`/pipeline with `new_concept`, `assumed_known`, `kind`. | `app/generation/prompts.py`, `pipeline.py` | pipeline test with mock provider |
| 3.2 | Blueprint prompt: require a realistic scenario and explicitly combine one known concept with the new one. | `app/ai/prompts/build_blueprint.md` | prompt assertion |
| 3.3 | Route `kind: problem_set` through legality + distribution checks in `pipeline.generate`. | `pipeline.py` | reject/accept tests |
| 3.4 | Persist `distribution/` starter + `hint_code` to disk in `save()`. | `pipeline.py` | file-layout test |
| 3.5 | Mock provider fixtures for a full pset (statement, starter-with-TODOs, tests, reference). | `tests/` | no live calls |
| 3.6 | Prompt/version bump; record version on generated psets. | `prompts_loader.py` | provenance test |

**Exit:** a mocked request yields a validated `problem_set` package on disk.

---

## Phase 4 — Checker metadata and report

**Spec:** [S5]

| # | Task | File(s) | Verify |
|---|---|---|---|
| 4.1 | Add `checker` schema: `prefix` + ordered `checks` (`id`, `description`, `after`, `visibility`, `test_id`). | `app/schemas/problem.py` (or `checker.py`) | schema + ordering tests |
| 4.2 | Build the checker deterministically: synthesise `exists`/`compiles`, map each test to one check, default `after: compiles`, preserve test order. | new `app/services/checker.py` | unit tests incl. determinism |
| 4.3 | Compute check outcomes from `GradingReport`; mark dependents **blocked** when `compiles` fails. | `app/feedback/reporter.py` | tests: compile-fail → dependents blocked, not failed |
| 4.4 | Add `checks` array to the submission response; retain existing verdict fields. | `app/api/submissions.py` | API-shape test |
| 4.5 | Assert hidden checks expose name only — never stdin/expected stdout. | `app/services/problem_service.py` | reuse hidden-data test pattern |
| 4.6 | Render the checker in the workspace UI (icon + text + colour, no colour-only signalling). | `web/app.js`, `web/styles.css` | UI-contract test; a11y check |

**Exit:** every pset presents an ordered, dependency-aware checker.

---

## Phase 5 — Prediction (hypothesis) capture and diff

**Spec:** [S6]

| # | Task | File(s) | Verify |
|---|---|---|---|
| 5.1 | Add `prediction` metadata (`enabled`, `sample_test_id`). | `app/schemas/problem.py` | schema test |
| 5.2 | Add optional `predicted_stdout` to the submit payload; store on the attempt. | `app/api/submissions.py`, `attempt_repository.py` | persistence test |
| 5.3 | Compute the diff (expected vs predicted vs actual); attach to the report; omit when absent. | `app/feedback/reporter.py` | match/mismatch/absent tests |
| 5.4 | Add the misconception note **only** when a declared id applies to the failed check. | `app/feedback/reporter.py` | test: no id → no note |
| 5.5 | Prove prediction never affects `verdict`, counts, or evidence. | tests | verdict identical with and without prediction |
| 5.6 | UI: prediction input + diff display. | `web/app.js` | UI-contract test |

**Exit:** prediction is a learning signal, provably not a grade.

---

## Phase 6 — Batch preparation

**Spec:** [S7]

| # | Task | File(s) | Verify |
|---|---|---|---|
| 6.1 | Define a `BatchProvider` capability (adapter, not a rewrite). | `app/ai/base.py` | interface test |
| 6.2 | Implement the Gemini Batch adapter (submits N requests, returns N responses). | `app/ai/google_batch.py` | mocked HTTP tests |
| 6.3 | Add a shelf runner: N requests → same `GenerationPipeline.generate` per item → store validated. | new `app/generation/batch.py` | mocked batch → N outcomes |
| 6.4 | Idempotency: reuse the content-addressed cache key; a re-run does not duplicate psets. | `app/ai/cache.py`, `batch.py` | re-run test |
| 6.5 | Per-item provenance: store provider, model, prompt version, job id, outcome. | `app/storage/usage_ledger.py` | ledger test |
| 6.6 | Bounded shelf size from `AI_DAILY_REQUEST_BUDGET`; record refusals. | `batch.py`, `rate_limits.py` | budget test |
| 6.7 | A failing item is recorded (rejected + findings) and does not fail the job. | `batch.py` | partial-failure test |
| 6.8 | CLI/endpoint to trigger a batch and report the shelf. | `app/api/generation.py` | API test |

**Exit:** a shelf of psets can be prepared in one provider run.

---

## Phase 7 — Verification and live proof

**Spec:** [S13]

| # | Task | Verify |
|---|---|---|
| 7.1 | Full `pytest -q`; all prior + new tests green. | counts recorded |
| 7.2 | Regression: every original package still loads and grades. | test suite |
| 7.3 | One live batch-prepared pset passes the gate end to end. | manual, documented |
| 7.4 | That pset is praxisable with **no provider configured** (open, predict, edit, submit, check, hint). | manual, documented |
| 7.5 | Adversarial check: try to make the gate accept an above-frontier reference and a solved starter. | both rejected |
| 7.6 | Update `docs/PLAN.md` progress + `README.md` if the workflow changed. | review |

**Exit:** the spec's central guarantee holds — AI prepares, checker grades, the
learner never waits on a model.

---

## Build-order summary

```
P0 baseline
 └─ P1 concept ladder + checklist        (schema + deterministic legality)
     └─ P2 distribution-code contract     (gate rules + fixture)
         └─ P3 generator emits a full pset
             └─ P4 checker metadata + report + UI
                 └─ P5 prediction capture + diff
                     └─ P6 batch preparation
                         └─ P7 verification + live proof
```

## Risk / ordering notes

- **P1 and P2 are independent of AI.** They can land and be tested before any
  generation change, which keeps the gate trustworthy.
- **Batch (P6) is last on purpose.** Batching changes *when* calls happen, not
  *what* is accepted, so it is only meaningful once the single-pset path (P3–P5)
  is proven.
- **No phase lowers the gate.** A package that fails a hard check is rejected;
  repair is bounded and must fully pass (existing rule).
- **Provider-free practice is a hard invariant** tested at P0.3 and P7.4.

---

## Phase 7 verification record (2026-10-21)

Recorded on `master` at `99259cb` (PR #1 merged). Reproducible with the three
scripts in `tools/`.

| # | Task | Result | Evidence |
|---|---|---|---|
| 7.1 | Full `pytest -q` green | **753 passed, 3 skipped, 0 failed** | exit 0 on the merged tree; 3 skips are the expected live-provider skips |
| 7.2 | Every original package still loads and grades | **pass** | covered by the suite; `problems/` fixtures unchanged |
| 7.3 | A batch-prepared pset passes the gate end to end | **pass** (model mocked) | `tools/phase7_batch_proof.py` |
| 7.4 | The pset is praxisable with **no provider configured** | **pass** | `tools/phase7_proof.py` — 19/19 steps |
| 7.5 | The gate rejects an above-frontier reference and a solved starter | **pass** | `tools/phase7_adversarial.py` — both rejected over HTTP, control accepted |
| 7.6 | `docs/PLAN.md` + `README.md` updated | **pass** | problem-set section, `/api/problems/batch` row, progress tracker |

### 7.1 — suite

`753 passed, 3 skipped, 0 failed` on the merged tree. The 3 skips exercise
live provider paths and need explicit configuration.

### 7.3 — batch proof, and what is substituted

The proof drives the real `POST /api/problems/batch` endpoint and asserts:

* the shelf goes out as **one** provider submission carrying all items;
* every item is accepted only after the **same** `GenerationPipeline` and the
  **same** `QualityGate` as an interactive generation;
* each accepted package is on disk and reloads with `kind=problem_set`, a
  concept pair, distribution code carrying `TODO`s, a stored checker
  (`prefix = ["exists", "compiles"]`), and stored hints;
* a malformed item is **rejected** with a finding — the batch path cannot
  lower the bar.

**Substitution, stated plainly:** the *model* is mocked. The live variant is
blocked because the configured provider returns **HTTP 402 — "insufficient
balance: available Rp 0"**. Everything else in the proof is the production
path: the HTTP boundary, the shelf runner, the pipeline, the gate, the
compiler, the runner, the comparator, the writer. Re-run the live variant once
the provider has credit.

### 7.4 — provider-free praxisability

Started with `KENARI_API_KEY=` (empty) so the app runs with no AI at all
(`/api/health` reports `key_configured: false`; the log says *"no
KENARI_API_KEY configured; AI generation is disabled"*). The full learner loop
then succeeds: **open → predict → edit → submit → check → hint → reveal**.

Observed: verdict `passed` (7/7), a 9-check `check50`-style report ordered
`exists → compiles → test-1..7`, **no test data in any check** (`data: {}`),
a prediction diff that does not alter the verdict, a hint served from the
*stored* ladder (`source: "stored"` — a stored hint always wins over a
generated one), and a solution reveal that correctly **refuses** without
`confirm: true`.

### 7.5 — adversarial probe

Attempted over the real HTTP boundary against a provider-free server, so the
gate is provably deciding on its own:

| Attack | Result | Finding |
|---|---|---|
| Starter replaced by the reference solution | rejected | `starter-identical-to-reference`, `starter-passes-all-tests` |
| Concept pair above the declared frontier (`new_concept: recursion`, `assumed_known: [pointers, structs]`, neither declared known) | rejected | `concept-above-frontier` |
| Control: the genuine pset | accepted | — |

Neither rejected package was written to disk, and the probe removes the
control package so it leaves the problems directory exactly as it found it.

Note the schema layer rejects a malformed pair even earlier:
`new_concept` appearing in `assumed_known` is a validation error, so it never
reaches the gate.
