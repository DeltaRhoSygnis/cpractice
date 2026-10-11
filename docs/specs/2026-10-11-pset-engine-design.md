# CPractice — Problem-Set Engine Design

**Document type:** Design specification
**Date:** 2026-10-11
**Status:** Approved for planning
**Builds on:** `docs/PLAN.md` (milestones M1–M9), `docs/CS50_STYLE_ENGINE_PLAN.md`

---

## [S1] Problem

CPractice today generates *exercises*: a short statement, a reference solution,
and a declarative stdin/stdout test list. That machinery works and is
well-tested. It does not, however, produce what the learner actually wants to
practise against.

The requested shape is a **CS50-style problem set**:

- a real-world scenario (a shop's sales log, a class reading level, a voting
  tally) that forces several concepts to work together;
- **distribution code** — a starter the learner completes — and/or hint code,
  rather than a blank editor;
- a **checker** in the spirit of `check50`: an ordered, named list of checks
  (`exists`, `compiles`, then one behavioural check per requirement) that was
  defined **at generation time from the pset specification**, so the learner
  runs the same checker that the author designed;
- a deliberate link between concepts the learner **already knows** and **one new
  concept**, so each pset connects known and unknown rather than drilling an
  isolated topic label.

And, additionally requested: the whole pset — statement, reference solution,
starter, checker, requirements, hints — should be **prepared before it is
presented**. Nothing is decided while the learner waits at the editor.

**Diagnosis.** The missing pieces are not correctness — the deterministic engine
already grades reliably. The missing pieces are (a) a *concept-legality rule*
that ties generation to what the learner actually knows, (b) *distribution code*
as a first-class part of the package, (c) *checker metadata* (names, ordering,
dependencies, descriptions) layered over the existing tests, and (d) a
*preparation model* that builds and validates the entire pset up front.

---

## [S2] Solution overview

Add a **problem-set layer** above the existing package without changing the
grading core. Five components:

1. **Concept map and known-concepts checklist.** The learner ticks which concept
   tags (from `app/services/curriculum.py` `STAGES`) they already know. Every
   generated pset must use **exactly one** new concept and must not require any
   concept outside `known ∪ {new}`.
2. **Distribution code contract.** `starter_code` becomes a compilable but
   incomplete program with labelled `TODO` regions; optional `hint_code` gives a
   partial scaffold. The gate verifies the starter does **not** already pass the
   hidden tests.
3. **Generation-time checker.** A declarative, ordered list of named checks.
   `exists` and `compiles` are synthesised deterministically; behavioural checks
   map one-to-one onto existing `TestCase`s. Checks carry a human-readable
   description and an `after` dependency, so a failed `compiles` blocks
   dependent checks exactly as `check50` does.
4. **Realistic-scenario generation.** Prompts instruct the generator to frame
   the task as a real-world program and to require the intended reasoning moves,
   while remaining original (no copied course text).
5. **Prepared psets via AI batch generation.** A pset is generated, validated,
   and stored **before** it is offered. A batch job (Gemini Batch API or the
   existing provider) can prepare a whole shelf of psets in one run; the learner
   then opens a ready pset and works offline from the provider.

**Invariant preserved:** AI designs and explains; the deterministic evaluator
decides pass/fail. The checker is data interpreted by trusted code, never an
AI-generated script.

---

## [S3] Concept ladder and the known-concepts checklist

### Checklist

- A stored preference: the set of **known concept tags** (`for_loops`,
  `arrays`, `strings`, ...). The tags are exactly the `concepts` tuples already
  declared in `app/services/curriculum.py` `STAGES`, so no new vocabulary is
  invented.
- The checklist is the source of truth for the "known" side. It is explicit and
  user-controlled; CPractice does not guess.

### Pairing rule (deterministic)

For a requested pset:

- `new_concept`: exactly one tag, chosen as the lowest-index concept not in the
  checklist (the frontier). The learner may override it.
- `assumed_known`: a non-empty subset of the checklist. At least one known
  concept must be **combined** with the new one — this is the "connect known and
  unknown" requirement, and it is enforced, not merely prompted.
- `forbidden`: every concept above the frontier is forbidden.

**Legality check (gate, not AI):**

```
required_concepts(reference_solution) ⊆ assumed_known ∪ {new_concept}
new_concept ∉ checklist
assumed_known ⊆ checklist
```

`required_concepts` is derived from the pset's declared `topics` +
`target_skills` plus a static scan of the reference for concept markers
(loop constructs → loop stages; array declaration/indexing → arrays; `struct` →
structs; self-call → recursion; pointer syntax → pointers). A pset whose
reference reaches past the frontier is **rejected by the gate**, never shipped
with a warning.

### Why this is checkable

`curriculum.STAGES` already orders concepts 0–11. The frontier is the first
stage index with any unchecked concept. Everything above is forbidden, so
"connect known and unknown" becomes a rule with a pass/fail, not an adjective.

---

## [S4] Distribution-code contract

`starter_code` becomes a required, meaningful artifact:

| Aspect | Requirement |
|---|---|
| Compiles | The started code **must compile** as C11 (learner can run the checker immediately). |
| Incomplete | It must **not** pass all hidden tests. |
| Labelled | It contains at least one `TODO` region identifying what the learner must implement. |
| Bounded | It does not contain the answer; TODOs mark missing decisions, not formatting. |

Optional `hint_code`: a scaffold showing structure (e.g. a loop header and a
comment naming the missing update) without the final logic. Distinct from the
hint ladder — hint code is a starting scaffold, hints are progressive text.

**Gate rules:**

- `starter-compiles`: ERROR if the starter fails to compile.
- `starter-passes-all-tests`: ERROR if the starter already passes every test
  ("distribution code solves the pset").
- `starter-missing-todos`: WARNING when no `TODO` marker is present.
- `starter-not-incomplete`: ERROR when the starter is byte-identical to the
  reference.

Backwards compatibility: packages where `starter_code` is empty load unchanged;
these rules apply only to psets that declare themselves as problem sets (see
[S10]).

---

## [S5] Checker: ordered, named, dependent checks

The checker is metadata **over existing tests**, not a new execution path.

### Synthesised prefix checks (never AI-authored)

| id | description | after |
|---|---|---|
| `exists` | `<entrypoint> exists.` | — |
| `compiles` | `<entrypoint> compiles.` | `exists` |

These are derived from the problem's `entrypoint` and `comparison`; the model
does not supply them.

Because the learner submits source text rather than a filename, `exists` always
passes in the local submission path: a submission with non-empty source
satisfies it. It is kept in the checker list for parity with `check50` and so
the same report shape carries over if a future file-based submission path is
added. It never fails spuriously on an empty-but-valid program, because an empty
submission is rejected earlier as a validation error rather than reaching the
checker.

### Behavioural checks

Each `TestCase` contributes one check:

```json
{
  "id": "encrypts_a_as_b",
  "description": "encrypts \"a\" as \"b\" using 1 as key",
  "after": "compiles",
  "visibility": "public",
  "test_id": "test-1"
}
```

- `description` reuses the test's `name`; the pipeline derives it from the test
  when absent, so a checker is always presentable.
- `visibility: hidden` checks appear by **name only**; their stdin and expected
  stdout never leave the server (existing hidden-data rule).
- `after` defaults to `compiles`. A check whose dependency failed reports
  **blocked** (`can't check until a frown turns upside down`), not failed.

### Ordering

Deterministic: `exists`, `compiles`, then behavioural checks in test-declaration
order. No AI ordering, no randomness.

### Report shape

The submission report gains a `checks` array mirroring `check50`'s JSON:

```json
{ "name": "compiles", "description": "caesar.c compiles.", "passed": false,
  "blocked": false, "cause": "compilation failed", "data": {} }
```

Existing fields (`verdict`, counts, failure categories) are retained; the check
list is additive.

---

## [S6] The hypothesis mechanic (predict-then-verify)

Optional, per-pset, and **never a pass/fail criterion**.

- Before submitting, the learner may be shown one public sample and asked:
  *"What do you expect this to print?"*.
- The prediction is stored on the attempt as `predicted_stdout` and is **not**
  scored. It does not affect `verdict`, pass counts, or recommendation evidence.
- After the checker runs, the report includes a prediction diff: expected vs
  predicted vs actual, and — when a mismatch maps to a declared misconception
  the learner's code also triggered — a short factual note tying them (e.g.
  "you predicted 4 and got 5; your code counts ties as new records, which
  `MIS-EQUAL-TIES` describes").
- If no prediction is supplied, the check runs normally and the diff section is
  omitted.

This isolates the AI-out-of-grading invariant: prediction comparison is pure
string comparison of the three known values; the explanatory note cites the
pset's declared misconceptions, not a fresh AI judgement.

---

## [S7] Prepared psets and AI usage (batch-first)

### Preparation model

Every artifact is built and validated **before** the pset is presented:

```
checklist + frontier
  └─ pick new_concept, assumed_known, role
      └─ blueprint (scenario, reasoning moves, misconceptions)
          └─ specification (statement, I/O contract, examples)
              └─ distribution code + hint code
                  └─ tests (public + hidden, requirement/misconception tagged)
                      └─ reference solution
                          └─ checker (exists, compiles, behavioural)
                              └─ gate: concept legality, starter rules,
                                 compile+run reference, calibration, mutation
                                  └─ STORED as a ready pset (status validated)
```

Nothing in this chain runs when the learner opens the pset. Opening, editing,
submitting, hinting, and checking are all provider-free.

### Why batch

The entire pset is known at request time, so it is a **batch workload**, not an
interactive one. Using a batch API:

- **cost:** batch pricing is materially cheaper than interactive calls;
- **quota:** a shelf of psets is prepared in one budgeted run;
- **latency tolerance:** the learner is not waiting — preparation happens ahead
  of the session, and the shelf is consumed offline.

### Provider strategy

- Add a `BatchProvider` capability alongside the existing `AIProvider`
  interface (adapters, not a rewrite — design decision #10).
- **Gemini Batch API** is the first batch adapter (Google already has an adapter
  module: `app/ai/google.py`). Kenari's OpenAI-compatible endpoint remains the
  interactive/repair path and a fallback.
- Batch flow: submit `N` pset requests as one job → poll/receive → run each
  response through the **same** pipeline and gate as interactive generation.
- Failure handling mirrors the existing taxonomy; a batch item that fails the
  gate is recorded as rejected, not silently dropped, and does not block the
  rest of the shelf.

### Requirements for batch readiness (documented, not all in first cut)

| Requirement | Reason |
|---|---|
| Idempotent job submission | A re-run must not duplicate psets (content-addressed cache key already exists). |
| Per-item provenance | Each stored pset records provider, model, prompt version, job id. |
| Bounded shelf size | Batch size derived from `AI_DAILY_REQUEST_BUDGET`. |
| Offline consumption guaranteed | Stored validated psets practice with no provider configured (already true). |
| Repair inside the job | A failing item may be repaired within the batch; repairs never lower the gate. |

### Interaction with existing pipeline

The batch path calls the **same** `GenerationPipeline.generate` per item, with
the same `QualityGate`. Batching changes *when and how many* calls are made, not
*what is accepted*. This keeps the "AI never decides pass/fail" guarantee intact
and means the existing mock-provider tests cover the batch path by construction.

---

## [S8] Data model additions

Additive and backwards-compatible.

### Problem metadata (new fields, all optional)

```json
{
  "kind": "problem_set",              // "exercise" (default) | "problem_set"
  "concept": {
    "new_concept": "arrays",
    "assumed_known": ["for_loops", "input_output"]
  },
  "distribution": {
    "has_starter": true,
    "todo_count": 2,
    "hint_code": "..."
  },
  "checker": {
    "prefix": ["exists", "compiles"],
    "checks": [
      { "id": "record_count", "description": "counts record days",
        "after": "compiles", "visibility": "public", "test_id": "test-1" }
    ]
  },
  "prediction": { "enabled": true, "sample_test_id": "test-1" }
}
```

### Attempt additions

- `predicted_stdout` (nullable text) — stored, never scored.
- `checker_results` — the per-check outcome list (derivable from existing
  `test_results`; stored denormalised for the report).

### No new execution machinery

The runner, compiler, comparator, and evaluator are unchanged. The checker is a
presentation and ordering layer over their output.

---

## [S9] Data flow (end to end)

```
[prepare, provider-online, batched]
checklist + frontier
  └─> concept selection (deterministic)
       └─> blueprint ──> specification ──> distribution code
            └─> tests (tagged) ──> reference ──> checker (synthesised + mapped)
                 └─> GATE: concept legality | starter rules | compile+run ref
                          | calibration | mutation | schema
                      └─> store validated pset

[practise, provider-offline]
open pset ──> read statement + distribution code
  └─> optional: write prediction for a public sample
       └─> complete TODOs in editor
            └─> submit
                 └─> deterministic evaluator (unchanged)
                      └─> checker report (exists/compiles/behaviour, blocked deps)
                           └─> prediction diff (when a prediction was given)
                                └─> hint ladder (stored, provider-free)
                                     └─> retry
```

---

## [S10] Error handling

| Condition | Response |
|---|---|
| Reference requires a concept above the frontier | Gate **error**; pset rejected. |
| `new_concept` already in the checklist | Gate error; concept selection recomputed. |
| Starter fails to compile | Gate error; pset rejected. |
| Starter already passes all hidden tests | Gate error ("distribution code solves the pset"). |
| `exists` fails | `compiles` and all behavioural checks report **blocked**. |
| `compiles` fails | Behavioural checks report **blocked**; report carries the diagnostic. |
| Prediction absent | Checker runs normally; diff section omitted. |
| Batch item fails the gate | Recorded as rejected with findings; job continues. |
| Provider auth/quota/unavailable | Existing taxonomy: 502 / 429 / 503, unchanged. |
| Old package without new fields | Loads unchanged; treated as `kind: exercise`. |

---

## [S11] Testing

All tests use mocked provider responses (existing rule); no live calls in the
suite.

- **Concept legality:** accepts a legal pairing; rejects a reference that reaches
  past the frontier; rejects `new_concept ∈ checklist`; rejects empty
  `assumed_known`.
- **Starter rules:** rejects a starter that fails to compile; rejects a starter
  that passes all tests; warns on a missing `TODO`; rejects a starter identical
  to the reference.
- **Checker:** synthesises `exists`/`compiles`; orders deterministically; maps
  each test to one check; marks dependents blocked when `compiles` fails;
  never exposes hidden stdin/stdout.
- **Prediction:** stores without affecting `verdict`; diff computed for
  match/mismatch/absent; misconception note only when a declared id applies.
- **Batch:** mocked batch provider yields N outcomes; a failing item is recorded
  and does not fail the job; idempotent re-submission does not duplicate psets;
  each stored pset records job provenance.
- **Backwards compatibility:** every existing package still loads and grades.
- **Live check:** one real batch-prepared pset passes the gate end to end and is
  praxisable with the provider disabled.

---

## [S12] Scope / YAGNI

**In this spec:**

- known-concepts checklist and the deterministic pairing rule;
- concept-legality gate check;
- distribution-code contract and its gate rules;
- checker metadata (names, ordering, dependencies, report shape);
- prediction capture and diff;
- realistic-scenario prompt guidance;
- batch-first preparation (Gemini Batch adapter + shelf workflow).

**Deferred (explicitly out):**

- function-level / `check50.c`-style harnesses — the runner stays stdin/stdout
  (design decision #7);
- multi-file psets and build systems;
- arbitrary AI-authored check scripts (forbidden by design decision #5);
- a public checker-output JSON format beyond the internal report;
- hosted execution hardening (separate, later concern);
- adaptive frontier inference from attempt history — the checklist is manual by
  decision for now.

---

## [S13] Acceptance criteria

A pset is ready when **all** hold:

1. It declares exactly one `new_concept` not in the checklist and a non-empty
   `assumed_known` ⊆ checklist.
2. Its reference requires no concept outside `assumed_known ∪ {new_concept}`
   (gate-verified).
3. Its distribution code compiles and does not already pass the hidden tests.
4. Its reference compiles and passes every test, and survives mutation testing
   under the existing thresholds.
5. Its checker lists `exists`, `compiles`, and one check per test, ordered, with
   dependencies, and exposes no hidden data.
6. It was generated and stored before being presented; it practises with no
   provider configured.
7. If generated via batch, it records job provenance and a re-run does not
   duplicate it.

The spec's central guarantee: **the AI prepares the pset; the deterministic
checker grades it; the learner never waits on a model.**
