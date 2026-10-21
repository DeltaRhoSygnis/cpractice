# Agensi.io Single-Listing Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish one $9 Agensi.io listing (`deterministic-autograder`) that funnels instructors into the CPractice repository, with a landing page that can be understood and installed by a non-developer.

**Architecture:** Two tracks. Track A makes CPractice honestly installable by an instructor with zero API keys (the promise the landing page makes). Track B builds the marketplace artifact: a router-style `SKILL.md` plus five reference documents, packaged as one ZIP, with one listing copy and one demo. Track C is the landing page on the portfolio site plus the measurement instrumentation the funnel is judged by. Manual work (video recording, submission, KYC) is sequenced last because everything else must exist before it is worth doing.

**Tech Stack:** Markdown (SKILL.md + references), Bash (`build-zips.sh`), Python 3.12 / pytest / FastAPI TestClient (offline-mode test), static HTML + CSS (portfolio case study), Vercel Analytics.

**Design spec:** `docs/specs/2026-10-22-agensi-single-listing-design.md`

**Repos:**
- CPractice: `/data/data/com.termux/files/home/cpractice` (git repo, branch `main`)
- Portfolio: `/data/data/com.termux/files/home/portfolio` (git repo, branch `master`)

---

## Global Constraints

These bind every task below. Implementers and reviewers inherit them without being told individually.

- **One SKU only.** Exactly one listing is published. The four tutor skills (`code-review`, `debugging`, `examination`, `retrieval`) are **not** listed and stay in the repository only.
- **Price is $9, one-time.** Not free, not a subscription, not a bundle.
- **Skill folder name is `deterministic-autograder`.** The frontmatter `name` must equal the folder name exactly, lowercase and hyphenated — a mismatch means the skill silently never loads.
- **The ZIP contains exactly one top-level folder** with `SKILL.md` at that folder's root. Text files only: no binaries, no symlinks, no `.DS_Store`, no `Thumbs.db`.
- **No `scripts/` directory in the package.** References and prose only.
- **No repo paths, internal URLs, provider names, or secrets inside the ZIP.** The call-to-action link lives in the *listing description*, outside the archive.
- **The skill body is design guidance only.** It must never emit a literal shell invocation of user source, never contain `rm -rf`, and never read as a prompt override.
- **The `SKILL.md` is a router, not an encyclopedia.** Short procedure per competency; depth lives in `references/`. Target ≤ 900 words in `SKILL.md`.
- **The listing demo (Step 3) is the single biggest conversion driver** and must be one realistic request prompt plus one complete, untruncated result of 700+ characters.
- **The CTA destination is the portfolio CPractice case study**, canonical `https://jessiejamesportfolio.vercel.app/projects/cpractice/`. `bryllim.com` is a reference site, not ours — it must never appear as a link.
- **Never promise the no-API-key path before it exists.** Track A lands before the landing page is edited.
- **AGENTS.md rules for the CPractice repo still apply:** PEP 8, type hints on public functions, Pydantic v2 at boundaries, `pytest` before commit, conventional commit messages, no secrets, no unrelated refactors.

---

## File Structure

| Path | Repo | Responsibility |
|---|---|---|
| `tests/test_offline_mode.py` | CPractice | Characterizes the zero-credential path: boot, list problems, grade a submission, no AI provider |
| `README.md` | CPractice | Quick start states that no API key is required |
| `start.sh` | CPractice | Prints the offline-mode notice when no provider key is configured |
| `docs/agensi/skills/deterministic-autograder/SKILL.md` | CPractice | Router body + frontmatter |
| `docs/agensi/skills/deterministic-autograder/README.md` | CPractice | Buyer-facing README inside the ZIP |
| `docs/agensi/skills/deterministic-autograder/references/result-taxonomy.md` | CPractice | Verdict model + result schema |
| `docs/agensi/skills/deterministic-autograder/references/mutation-operators.md` | CPractice | C mutation operators, killed/survived table |
| `docs/agensi/skills/deterministic-autograder/references/c-edge-cases.md` | CPractice | Edge-case checklist for student programs |
| `docs/agensi/skills/deterministic-autograder/references/problem-package-schema.md` | CPractice | The problem-package contract |
| `docs/agensi/skills/deterministic-autograder/references/hint-ladder.md` | CPractice | Progressive hints, level-5 reveal |
| `docs/agensi/skills/deterministic-autograder/verify-package.py` | CPractice | Structural verification of the built ZIP (not shipped) |
| `docs/agensi/listings/deterministic-autograder/listing.md` | CPractice | Every upload-form field, copy-ready |
| `docs/agensi/logos/deterministic-autograder.png` | CPractice | 512×512 marketplace logo |
| `docs/agensi/LAUNCH.md` | CPractice | Submission + KYC + distribution + 90-day decision runbook |
| `projects/cpractice/index.html` | Portfolio | Instructor path section (section 08) + verdict demo block |
| `index.html` | Portfolio | Vercel Analytics enabled |

---

### Task 1: Make the zero-credential path a tested, documented guarantee

**Covers:** S5, S7

**Files:**
- Create: `tests/test_offline_mode.py`
- Modify: `README.md:51-63`
- Modify: `start.sh:44-56`

**Interfaces:**
- Consumes: `app.main.create_app(settings) -> FastAPI`; `app.config.Settings`; `POST /api/problems/{problem_id}/submit` with body `{"source": str}`; `GET /api/health`.
- Produces: no new public API. The guarantee asserted is: with `kenari_api_key=None` and `google_api_key=None`, `GET /api/health` reports `capabilities.ai.key_configured is False`, `GET /api/problems` returns at least one problem, and a correct submission returns `"verdict" == "passed"`.

- [ ] **Step 1: Write the characterization test**

Create `tests/test_offline_mode.py`:

```python
"""The zero-credential path: CPractice must be fully usable without an AI key.

An instructor is not a developer. If CPractice cannot boot, list problems and
grade a submission with no provider credentials, nobody outside the project can
use it - and the landing page must not promise otherwise.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

REPO_PROBLEMS = Path(__file__).resolve().parent.parent / "problems"
EXAMPLE_ID = "c-sum-two-integers"

REFERENCE = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""


def _offline_client(tmp_path: Path) -> TestClient:
    """An app with no provider credentials and no .env file."""
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=REPO_PROBLEMS,
        workspaces_dir=tmp_path / "workspaces",
        kenari_api_key=None,
        google_api_key=None,
    )
    return TestClient(create_app(settings))


def test_app_boots_without_any_provider_key(tmp_path: Path) -> None:
    with _offline_client(tmp_path) as client:
        body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["capabilities"]["ai"]["key_configured"] is False


def test_problems_are_listable_without_any_provider_key(tmp_path: Path) -> None:
    with _offline_client(tmp_path) as client:
        response = client.get("/api/problems")

    assert response.status_code == 200
    assert response.json()


def test_submission_is_graded_without_any_provider_key(tmp_path: Path) -> None:
    with _offline_client(tmp_path) as client:
        response = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit", json={"source": REFERENCE}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "passed"
    assert body["summary"]["all_passed"] is True


def test_generation_endpoint_reports_that_ai_is_unavailable(tmp_path: Path) -> None:
    """The failure must be explicit, not a 500 and not a silent empty response."""
    with _offline_client(tmp_path) as client:
        response = client.post("/api/problems/generate", json={"topic": "loops"})

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
```

The generation endpoint already raises `HTTPException(status_code=503, ...)`
when `request.app.state.generation_pipeline` is `None`, so this test should pass
as written. If it returns `500` instead, the guard in
`app/api/generation.py:78-85` has been changed - restore it.

- [ ] **Step 2: Run the new test**

Run: `pytest tests/test_offline_mode.py -v`

Expected: 4 tests PASS.

- [ ] **Step 3: Run the full suite to confirm nothing regressed**

Run: `pytest -q`

Expected: all tests pass, no new warnings about unset credentials.

- [ ] **Step 4: Update the README quick start**

In `README.md`, replace lines 55–63:

```markdown
```bash
git clone https://github.com/DeltaRhoSygnis/cpractice.git
cd cpractice
pip install -r requirements.txt
./start.sh                # http://127.0.0.1:8000 - no API key needed
```

or without the helper: `uvicorn app.main:app --host 127.0.0.1 --port 8000`.

> **No API key required.** CPractice boots, serves the saved problem packages
> and grades submissions with **no AI provider configured**. An AI key is only
> needed to *generate* new exercises and to draft hints on the fly
> (`cp .env.example .env` to add one). Everything that decides a verdict is
> deterministic software.
```

- [ ] **Step 5: Make `start.sh` say so out loud**

In `start.sh`, immediately after the line `echo "Starting CPractice at ${URL} ..."`, insert:

```bash
# Report offline mode honestly: no key means no generation, but grading works.
if [ -z "${KENARI_API_KEY:-}" ] && [ -z "${GOOGLE_API_KEY:-}" ] \
   && ! grep -qsE '^[[:space:]]*(KENARI|GOOGLE)_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]]' .env 2>/dev/null; then
  echo "No AI provider key found - AI generation and live hints are disabled."
  echo "Saved problem packages still load and every submission is still graded."
fi
```

- [ ] **Step 6: Verify the notice by running the script briefly**

Run: `./start.sh` then `Ctrl-C` after the banner prints.

Expected output includes both `No AI provider key found` and `Saved problem packages still load and every submission is still graded.`

- [ ] **Step 7: Re-run the suite and commit**

Run: `pytest -q`

Expected: all pass.

```bash
git add tests/test_offline_mode.py README.md start.sh app/api/generation.py
git commit -m "feat: guarantee the zero-credential path and document it"
```

---

### Task 2: Write the five reference documents

**Covers:** S3

**Files:**
- Create: `docs/agensi/skills/deterministic-autograder/references/result-taxonomy.md`
- Create: `docs/agensi/skills/deterministic-autograder/references/mutation-operators.md`
- Create: `docs/agensi/skills/deterministic-autograder/references/c-edge-cases.md`
- Create: `docs/agensi/skills/deterministic-autograder/references/problem-package-schema.md`
- Create: `docs/agensi/skills/deterministic-autograder/references/hint-ladder.md`

**Interfaces:**
- Consumes: nothing executable. The facts are transcribed from the CPractice source (`app/schemas/grading.py`, `app/generation/mutation.py`, `app/generation/blueprint.py`, `app/generation/calibration.py`, `app/schemas/problem.py`, `app/schemas/test_case.py`, `app/feedback/hint_service.py`, `app/generation/misconceptions.py`).
- Produces: five markdown files, each with the exact headings given below. Task 3 links to them by filename; Task 5 quotes from them in the listing demo.

Every reference file starts with a one-line purpose statement, then uses the
headings given here, in this order. **No file may contain a path into the
CPractice repository, a provider name, or an internal URL.**

- [ ] **Step 1: Write `result-taxonomy.md`**

Headings and content:

```markdown
# Verdict taxonomy and result schema

A grader must be able to say *why* a submission failed, and must never let a
language model decide the verdict. This is the outcome model.

## The seven outcome categories

| Category | Meaning | Learner-facing action |
|---|---|---|
| `passed` | The output matched the expected output for this test. | Continue. |
| `wrong_answer` | The program ran and produced a different answer. | Fix the logic. |
| `runtime_error` | The program crashed (signal, abort, or non-zero exit that is not a verdict). | Fix the crash. |
| `timeout` | The program exceeded the wall-clock limit for this test. | Improve the complexity. |
| `output_limit_exceeded` | The program produced more output than the limit allows. | Print less. |
| `compilation_error` | The source did not compile. (Attempt-level only - it blocks every test.) | Fix the compile error. |
| `internal_error` | The grader itself failed - missing compiler, broken workspace. **Never the learner's fault.** | Retry, then report. |

## Two rules that make the taxonomy worth having

1. **Partial credit needs per-test verdicts.** A single boolean cannot award
   partial credit, and cannot tell a learner "your loop was correct, your
   off-by-one on the last case was not". Grade per test; aggregate afterwards.
2. **Infrastructure failure is a separate category.** If the compiler is
   missing, that is *your* problem, not the learner's. Never map an internal
   error onto `wrong_answer`.

## Result schema

```json
{
  "problem_id": "c-sum-two-integers",
  "verdict": "wrong_answer",
  "compilation": { "success": true, "diagnostics": "", "duration_ms": 41 },
  "tests": [
    {
      "test_id": "t1",
      "test_name": "two positive integers",
      "visibility": "public",
      "category": "passed",
      "duration_ms": 12,
      "exit_code": 0,
      "detail": ""
    }
  ],
  "summary": { "total": 5, "passed": 4, "failed": 1, "all_passed": false }
}
```

`visibility` is `public` or `hidden`. Report hidden test names and expected
outputs only after the attempt is graded - never before, or the hidden tests
become the answer key.

## Aggregating an attempt

- All tests `passed` -> attempt verdict `passed`.
- Any test `compilation_error` is impossible per test; a compile failure is
  attempt-level and short-circuits the run.
- Any test `timeout`, `runtime_error` or `output_limit_exceeded` -> attempt
  verdict is the *first* such category, in the order above. Report which test
  produced it.
- Otherwise -> `wrong_answer`.
- An `internal_error` anywhere -> the attempt is `internal_error`, and it is
  never counted against the learner.

## What a model may and may not do

**May:** write the statement, draft hints, propose candidate test inputs,
explain a verdict.
**May not:** decide `passed` or `wrong_answer`, author an expected output,
change a category, or score a submission. If a model is down, wrong or cheap,
the verdict is unchanged.
```

- [ ] **Step 2: Write `mutation-operators.md`**

```markdown
# Proving your hidden tests are not vacuous

A reference solution passing its own tests proves **consistency**, not
**correctness**. A wrong reference with matching wrong tests passes cleanly.
Mutation testing supplies the missing instrument.

## The method

1. Derive deliberately-wrong variants ("mutants") of the reference solution.
2. Run each mutant against the problem's test suite.
3. A mutant that **fails** a test is **killed** - the tests detect that bug.
   A mutant that **passes every test** **survived** - the tests are too weak to
   notice an obviously wrong program.

A high survival rate means the suite does not discriminate. Fix the suite;
never quietly accept the survivors.

## C-specific operators worth having

| Operator | Mutation | The beginner bug it represents |
|---|---|---|
| `add-to-sub` | `+` becomes `-` | Sign error in an accumulation |
| `sub-to-add` | `-` becomes `+` | Sign error in a subtraction |
| `mul-to-add` | `*` becomes `+` | Multiplication written as addition |
| `lt-to-le` | `<=` becomes `<` | Off-by-one at the boundary |
| `le-to-lt` | `<` becomes `<=` | Off-by-one at the boundary |
| `gt-to-ge` | `>=` becomes `>` | Boundary, wrong side |
| `eq-to-ne` | `==` becomes `!=` | Equality inverted |
| `inc-to-dec` | `++` becomes `--` | Loop runs the wrong way |
| `drop-newline` | trailing `\n` removed | Output formatting differs |
| `drop-increment` | loop increment deleted | Infinite loop / early exit |

## Rules that keep the signal honest

- **Mutate only the first occurrence** of each pattern, so each mutant is
  small and still compiles most of the time.
- **Do not remove `return 0;` from `main`.** Since C99 an implicit
  `return 0;` is added, so that mutant is semantically equivalent to the
  reference and would survive every time - pure noise that would wrongly flag
  correct tests as weak.
- **Treat `drop-newline` as an expected survivor** when the comparison mode
  ignores a single trailing newline. Reporting it would flag every problem
  that legitimately uses that mode.
- **Collapse duplicate mutants.** Two operators that produce the same source
  are one mutant, not two.

## Reading the result

| Surviving mutants | What it means | What to do |
|---|---|---|
| 0 | The suite discriminates. | Ship it. |
| 1-2 | Usually a formatting-only survivor. | Confirm it is expected; add a test if it is not. |
| 3+ on arithmetic problems | The suite is too weak. | Add the missing boundary and interior cases. |

## The rule that matters most

Survivors are a **finding**, not a score. Report the operator, the mutant and
the reason. Never present a mutation score as a quality number to be
optimised - the goal is a suite that catches the mistakes students actually
make.
```

- [ ] **Step 3: Write `c-edge-cases.md`**

```markdown
# Edge cases to walk before writing hidden tests

For each student program, walk this checklist before you write a single hidden
test. Each row is a bug that has actually been graded as "correct" because the
suite never asked the right question.

## Reading and formatting

- Does the program read **exactly** the declared number of values? A program
  that stops early and still prints an answer passes a suite that never checks
  the input was consumed.
- Trailing newline present or absent? Decide the comparison mode once
  (exact, or exact-ignoring-one-trailing-newline) and apply it to every test.
- Extra whitespace inside the line? Leading zeros? Fix one canonical output
  format and test against that.
- What if the input has **more** values than declared? Fewer?

## Empty and single-element inputs

- Zero-length array, zero-length string, single element.
- A count of `0` where a division or a modulo appears - division by zero.
- The minimum and maximum representable value for the declared type.

## Boundaries

- `n = 1` and `n = n_max` for every loop.
- A value exactly on the threshold (`<=` versus `<`).
- Negative values, and the sign of zero.

## Accumulation and overflow

- An accumulator that overflows its type. In C this is undefined behaviour,
  so the test either uses a range that cannot overflow or the language
  standard guarantees a wider type.
- Off-by-one in the loop bound: does the last element get processed?

## Types and conversions

- Signed versus unsigned comparison when the value can go negative.
- Implicit truncation from a wider to a narrower type.
- Floating point compared with a tolerance, and when it must be exact.

## Output shape

- One number per line, or one line? Declare it, then test it.
- Trailing spaces. Extra blank lines. Both are wrong if the format says
  otherwise.

## The rule

Write the **expected output by hand**, from the specification, not by running
the reference. If you cannot, you do not yet know what the problem is asking.
```

- [ ] **Step 4: Write `problem-package-schema.md`**

```markdown
# The problem-package contract

An exercise is **data**, not a script. If the test suite is a program, it
becomes an arbitrary script and the grader stops being deterministic. A package
is a directory of declarative files that any runner can execute.

## Layout

```
<problem-id>/
├── problem.json      # the manifest: metadata, concept tags, limits
├── statement.md      # what the learner is asked to do
├── reference/        # the reference solution (source files)
└── starter/          # the distribution code the learner completes
```

## The manifest

| Field | Type | Rule |
|---|---|---|
| `id` | string | Lowercase, hyphenated, unique. Used as a path - validate it before use. |
| `title` | string | One line. Shown in the editor. |
| `kind` | enum | `exercise` or `problem_set`. |
| `concept_ids` | string[] | The concepts this problem exercises. Must be a subset of what the learner is declared to know, plus exactly one new concept. |
| `starter_code` | string | Compilable but incomplete. It must **not** already pass the hidden tests. |
| `limits` | object | `time_ms`, `memory_mb`, `max_output_bytes`. Bounds are configuration, never hard-coded per problem. |
| `tests` | test case[] | Each test is declarative data. |

## A test case

| Field | Type | Rule |
|---|---|---|
| `id` | string | Stable, unique inside the package. |
| `name` | string | Human readable; shown to the learner only for public tests. |
| `visibility` | enum | `public` or `hidden`. Hidden test data and expected outputs never reach the client before grading. |
| `stdin` | string | The input, verbatim. |
| `expected_stdout` | string | The expected output. Written by hand from the specification. |
| `comparison` | enum | `exact` or `exact_normalized` (ignores one trailing newline). |
| `time_ms` / `memory_mb` | int | Per-test overrides; fall back to the package limits. |

## The rules that keep it deterministic

1. **No test may be a script.** A test is input, expected output and a
   comparison mode. Nothing else.
2. **Expected outputs are written by hand**, then confirmed against the
   reference. If the two disagree, the specification is wrong - fix it, do
   not regenerate the expectation from the reference.
3. **Limits come from configuration.** A package may narrow them; it may not
   widen them beyond the configured maximum.
4. **Identifiers are validated before they touch the filesystem.** A package
   id becomes a directory name and a compiler argument.
5. **The learner never sees hidden test data.** The runner receives it; the
   client does not.
```

- [ ] **Step 5: Write `hint-ladder.md`**

```markdown
# Progressive hints, and when to stop giving them

Hints are optional and progressive. Each level gives away more, so the learner
can stop at the level that unblocks them without having taken the whole
answer.

## The five levels

| Level | Gives | Does not give |
|---|---|---|
| 1 | A pointer at the kind of mistake, without naming the line | The line, the fix, or the code |
| 2 | The specific concept to revisit | The fix |
| 3 | The shape of the approach, or the boundary that is being missed | The code |
| 4 | A worked fragment of the approach | The complete solution |
| 5 | The full reference solution, explicitly | - |

Level 5 is a **reveal**, and it is labelled as one. It is never the default
answer to a request for a hint.

## Rules

1. **One level per request.** Asking again moves up the ladder; it never
   returns several levels at once.
2. **The reveal is explicit.** Level 5 says plainly that it is the reference
   solution and that the learner can go back and try again.
3. **Hints target the misconception, not the syntax.** A hint that restates
   the question is wasted.
4. **A stored hint beats a generated one.** If the package already carries a
   hint for this failure mode, use it - it was written by the author, who
   knows the learner's misconceptions.
5. **Track how many hints were consumed.** The count changes what comes next:
   after several hints, the learner usually needs a *different* problem, not a
   bigger hint.

## What a hint must never do

- Never hand over a working solution when the request was for level 1-3.
- Never guess which mistake the learner made. Point at the observable failure
  and the concept, and let them decide.
- Never claim understanding on the learner's behalf. Correct the smallest
  misconception first, then ask them to restate the repaired idea.
```

- [ ] **Step 6: Verify the five files exist and contain no forbidden strings**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice
ls docs/agensi/skills/deterministic-autograder/references/
grep -rniE "cpractice|app/|kenari|gemini|google_api|bryllim|/data/data" docs/agensi/skills/deterministic-autograder/references/ && echo "LEAK FOUND" || echo "clean"
```

Expected: five filenames listed; `clean`.

- [ ] **Step 7: Commit**

```bash
git add docs/agensi/skills/deterministic-autograder/references/
git commit -m "docs(agensi): add the five reference documents for the autograder skill"
```

---

### Task 3: Write the router SKILL.md and the package README

**Covers:** S3

**Files:**
- Create: `docs/agensi/skills/deterministic-autograder/SKILL.md`
- Create: `docs/agensi/skills/deterministic-autograder/README.md`

**Interfaces:**
- Consumes: the five reference files from Task 2.
- Produces: a `SKILL.md` whose frontmatter `name` is `deterministic-autograder` and whose `description` contains the trigger phrases; a `README.md` for buyers.

- [ ] **Step 1: Write `SKILL.md`**

```markdown
---
name: deterministic-autograder
description: Use when the user asks to design an autograder, grade programming assignments, define per-test verdicts and partial credit, write hidden test cases, prove their tests are not vacuous, or structure a problem package for an automated judge. Also use when the user asks why students' submissions are graded wrong, or wants a hint ladder for a struggling learner.
---

# Deterministic autograder design

## The invariant

**No model, heuristic or human opinion decides a verdict.** Software compares
output to expected output; the verdict is a function of the bytes, the exit
code and the clock. A model may write the statement, draft a hint, or propose
candidate inputs. A model may not decide that a submission is correct.

If the model is down, wrong, or cheap, the verdict does not change.

## Output format

Always answer in this shape:

1. **Verdict model** - the outcome categories, what each means, and how an
   attempt-level verdict is derived from per-test verdicts.
2. **Partial-credit rule** - how per-test results aggregate into a grade.
3. **Test-discrimination plan** - which wrong-but-plausible variants of the
   reference must be rejected, and how to check that they are.
4. **Edge-case checklist** - the inputs the suite must cover before it is
   trusted.
5. **Hint ladder** - the levels, what each reveals, and where the reveal stops.
6. **Next steps** - the two or three concrete actions to take next.

If the user asked for only one of these, answer that one and state which
others apply. Do not pad.

## Procedure

### 1. Specify the verdicts before writing a single test

Read `references/result-taxonomy.md`. Produce the outcome categories, the
per-test result schema, and the aggregation rule. Then decide which
categories the grader can actually distinguish - a grader that cannot detect
a timeout must not offer a `timeout` verdict.

### 2. Make the tests discriminate

Read `references/mutation-operators.md`. For the reference solution, list the
wrong-but-plausible variants a student actually writes, and state which test
kills each one. A variant that no test rejects is a hole in the suite - say so
explicitly rather than shipping a suite that passes a wrong program.

### 3. Walk the edge cases

Read `references/c-edge-cases.md`. Turn the checklist into concrete inputs for
this problem. Write the expected output **by hand from the specification**,
then confirm it against the reference. If they disagree, the specification is
wrong - fix the specification, do not regenerate the expectation.

### 4. Package the problem as data

Read `references/problem-package-schema.md`. Emit the package layout, the
manifest fields, and the test case fields. Tests are declarative data; a test
is never a script.

### 5. Design the hint ladder

Read `references/hint-ladder.md`. Give the five levels, what each reveals,
and the explicit reveal at level 5.

## Boundaries

- Do not write code that compiles and runs a learner's submission. Describe
  the sandbox - time limit, memory limit, output cap, cleanup - as
  configuration the grader enforces.
- Do not emit shell commands, process-killing incantations or file-deletion
  commands as part of a design.
- Do not propose that a language model grade, score, or sanity-check a
  submission.
- Do not invent an expected output by running the reference and recording
  whatever it printed.
- Do not return a single quality score in place of evidence. Report findings
  with the reason attached.

## Example

**Request:** "I want to autograde my students' C submissions. They should get
partial credit, and I need to be sure my hidden tests actually catch wrong
answers."

**Answer:** follow the output format above - the seven verdict categories and
the per-test schema; the aggregation rule that yields partial credit; the
mutation operators to apply to a reference solution and what a survivor means;
the edge-case checklist; the five hint levels; and the next steps.
```

- [ ] **Step 2: Verify the frontmatter and the word count**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice
head -5 docs/agensi/skills/deterministic-autograder/SKILL.md
wc -w docs/agensi/skills/deterministic-autograder/SKILL.md
```

Expected: the `name:` line reads exactly `name: deterministic-autograder`, and the word count is between 700 and 1000.

- [ ] **Step 3: Write the package `README.md`**

```markdown
# deterministic-autograder

A specification you can hand to an agent when you are building a code grader:
verdict categories and partial credit, test discrimination through mutation,
edge-case coverage, the problem-package contract, and the hint ladder.

**Install:** copy this folder into your agent's skills directory
(`~/.claude/skills/`, `.cursor/rules/`, `.codex/skills/`, or the equivalent for
your agent). It contains no scripts and runs no commands - it is instructions
and reference material only.

## What is inside

| File | What it gives you |
|---|---|
| `SKILL.md` | The router: the invariant, the output format, the five-step procedure. |
| `references/result-taxonomy.md` | The seven verdict categories, the result schema, the partial-credit rule. |
| `references/mutation-operators.md` | Ten C-specific mutation operators and how to read survivors. |
| `references/c-edge-cases.md` | The edge-case checklist for student programs. |
| `references/problem-package-schema.md` | The package layout, manifest fields and test case fields. |
| `references/hint-ladder.md` | Five progressive hint levels and the explicit reveal. |

## The one rule everything else serves

**No model decides a verdict.** Output is compared to expected output by
software. A model may write the statement and draft hints; it may not decide
that a submission is correct. The grading engine is provider-independent, so a
model outage, a bad model, or a cheap model cannot change a grade.

## Requirements

None. No runtime, no packages, no network, no credentials, no file access
beyond the files you ask it to read. Works in any agent that supports the
`SKILL.md` format.

## License

MIT.
```

- [ ] **Step 4: Scan the whole package for leaks and prompt-override patterns**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice
grep -rniE "cpractice|app/|kenari|gemini|google_api|bryllim|/data/data|ignore previous|disregard the" docs/agensi/skills/deterministic-autograder/ && echo "LEAK FOUND" || echo "clean"
```

Expected: `clean`.

- [ ] **Step 5: Commit**

```bash
git add docs/agensi/skills/deterministic-autograder/SKILL.md docs/agensi/skills/deterministic-autograder/README.md
git commit -m "docs(agensi): add the router SKILL.md and buyer README"
```

---

### Task 4: Package the skill and verify the archive structurally

**Covers:** S3, S7

**Files:**
- Create: `docs/agensi/skills/deterministic-autograder/verify-package.py`
- Modify: `docs/agensi/build-zips.sh` (restrict the default target set to the one listing)
- Output: `docs/agensi/dist/deterministic-autograder.zip`

**Interfaces:**
- Consumes: the package from Tasks 2–3.
- Produces: `docs/agensi/dist/deterministic-autograder.zip`, and `verify-package.py <zip>` which exits `0` when the archive satisfies every marketplace rule and non-zero with a named failure otherwise.

- [ ] **Step 1: Write the verifier**

Create `docs/agensi/skills/deterministic-autograder/verify-package.py`:

```python
#!/usr/bin/env python3
"""Verify a built skill ZIP against the marketplace's structural rules.

Usage:  python3 verify-package.py ../dist/deterministic-autograder.zip
Exit:   0 = every check passed, 1 = at least one check failed.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

FORBIDDEN_TEXT = re.compile(
    r"cpractice|app/|kenari|gemini|google_api|bryllim|/data/data|ignore previous",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify-package.py <zip>", file=sys.stderr)
        return 1

    zip_path = Path(sys.argv[1])
    problems: list[str] = []

    if not zip_path.is_file():
        print(f"FAIL: {zip_path} does not exist")
        return 1

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()

        roots = {name.split("/")[0] for name in names if name.strip()}
        if len(roots) != 1:
            fail(problems, f"expected exactly one top-level folder, found {sorted(roots)}")
        else:
            root = roots.pop()
            if root != "deterministic-autograder":
                fail(problems, f"top-level folder is {root!r}, expected 'deterministic-autograder'")
            if f"{root}/SKILL.md" not in names:
                fail(problems, f"{root}/SKILL.md is missing")

        for name in names:
            if name.startswith("__MACOSX/") or name.endswith((".DS_Store", "Thumbs.db")):
                fail(problems, f"OS cruft in archive: {name}")
            suffix = Path(name).suffix.lower()
            if suffix and suffix not in TEXT_SUFFIXES:
                fail(problems, f"non-text file in archive: {name}")

        skill_text = ""
        for name in names:
            if name.endswith("SKILL.md"):
                skill_text = archive.read(name).decode("utf-8")
                match = re.search(r"^name:\s*(.+)$", skill_text, re.MULTILINE)
                if match is None:
                    fail(problems, "SKILL.md has no 'name:' frontmatter field")
                elif match.group(1).strip() != "deterministic-autograder":
                    fail(problems, f"frontmatter name is {match.group(1).strip()!r}")
                if "description:" not in skill_text:
                    fail(problems, "SKILL.md has no 'description:' frontmatter field")

        for name in names:
            body = archive.read(name).decode("utf-8", errors="replace")
            hit = FORBIDDEN_TEXT.search(body)
            if hit:
                fail(problems, f"forbidden content {hit.group(0)!r} in {name}")

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1

    print(f"OK: {zip_path} satisfies every structural check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Restrict the build script to the single listing**

In `docs/agensi/build-zips.sh`, change the default-target discovery block so that only the published skill is built when no argument is given. Replace:

```bash
  for d in "$SKILLS_DIR"/*/; do
    [ -f "$d/SKILL.md" ] && targets+=("$(basename "$d")")
  done
```

with:

```bash
  # Only the published listing is built by default. The other folders are
  # drafts kept for reference and must never reach the marketplace.
  if [ -f "$SKILLS_DIR/deterministic-autograder/SKILL.md" ]; then
    targets+=("deterministic-autograder")
  fi
```

- [ ] **Step 3: Build the archive**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice/docs/agensi
./build-zips.sh
```

Expected: `built dist/deterministic-autograder.zip`.

- [ ] **Step 4: Run the verifier**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice/docs/agensi
python3 skills/deterministic-autograder/verify-package.py dist/deterministic-autograder.zip
```

Expected: `OK: dist/deterministic-autograder.zip satisfies every structural check`.

- [ ] **Step 5: Prove the verifier actually catches a broken package**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice/docs/agensi
cp dist/deterministic-autograder.zip /tmp/broken.zip 2>/dev/null || cp dist/deterministic-autograder.zip "$TMPDIR/broken.zip"
python3 - <<'PY'
import zipfile, shutil, os, tempfile
src = "dist/deterministic-autograder.zip"
dst = os.path.join(tempfile.gettempdir(), "broken.zip")
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith("SKILL.md"):
            data = data.replace(b"name: deterministic-autograder", b"name: wrong-name")
        zout.writestr(item, data)
print(dst)
PY
python3 skills/deterministic-autograder/verify-package.py "$TMPDIR/broken.zip"; echo "exit=$?"
```

Expected: the verifier prints `FAIL: frontmatter name is 'wrong-name'` and `exit=1`.

- [ ] **Step 6: Clean up and commit**

```bash
rm -f "$TMPDIR/broken.zip"
cd /data/data/com.termux/files/home/cpractice
git add docs/agensi/build-zips.sh docs/agensi/skills/deterministic-autograder/verify-package.py
git commit -m "build(agensi): verify the autograder archive structure"
```

Do **not** commit `docs/agensi/dist/` — it is a build artifact and stays ignored.

---

### Task 5: Write the listing copy, including the one demo that sells it

**Covers:** S4

**Files:**
- Create: `docs/agensi/listings/deterministic-autograder/listing.md`

**Interfaces:**
- Consumes: the package from Tasks 2–3; the form field list from `skill_upload.txt`.
- Produces: one markdown file with a heading per upload-form field, so it can be pasted into the form field by field.

- [ ] **Step 1: Write the listing file**

Create `docs/agensi/listings/deterministic-autograder/listing.md` with these headings, in this order, each containing exactly the field content:

`## Skill Name`, `## Summary`, `## Full Description`, `## The request`, `## The result`, `## Compatibility note`, `## Pricing`, `## Tags / categories / use cases`, `## Permissions`, `## FAQ`, `## Documentation link`.

Field content:

```markdown
## Skill Name

Deterministic Autograder — verdicts, partial credit, tested test cases

## Summary

Design an autograder where software decides pass/fail, not the model, and where partial credit and test strength are specified up front.

## Full Description

Most "AI graders" fail in one of two ways: the model guesses whether a
submission is right, or the suite is so weak that a wrong program passes. This
skill specifies both away.

**The invariant: no model decides a verdict.** Output is compared to expected
output by software. A model may write the statement, draft a hint, or propose
candidate inputs. It may not decide that a submission is correct. The grading
engine stays provider-independent, so a model outage or a cheap model cannot
change a grade.

**What you get:**

- **Seven verdict categories** - passed, wrong answer, runtime error, timeout,
  output limit exceeded, compilation error, internal error - with per-test
  results and a partial-credit rule. A single boolean cannot tell a student
  "your loop was correct, your off-by-one was not".
- **Test discrimination through mutation** - ten C-specific mutation
  operators, and the rule that a surviving mutant is a finding: the suite does
  not catch an obviously wrong program.
- **An edge-case checklist** for student programs: empty and single-element
  inputs, boundaries, sign of zero, overflow, signed/unsigned comparison,
  output shape.
- **The problem-package contract** - an exercise is declarative data (input,
  expected output, comparison mode), never an arbitrary script, so any runner
  can execute it and every run is reproducible.
- **A five-level hint ladder** with an explicit reveal at level 5, so a learner
  can unblock themselves without being handed the answer.

The skill is a router: `SKILL.md` carries the invariant, the output format and
the five-step procedure; five reference documents carry the depth. Your agent
reads the reference it needs at the moment it needs it.

## The request

I'm setting up an autograder for my introductory C course. Students submit
source, I need per-test verdicts and partial credit, and I need to be sure my
hidden tests actually catch wrong answers. How should I specify this?

## The result

## Compatibility note

Works with any agent that supports the SKILL.md format - Claude Code, Codex
CLI, Cursor, VS Code Copilot, Gemini CLI, Windsurf, Aider, Cline, Zed and
others. No runtime, no packages, no network access, no credentials, no file
access beyond the files you ask it to read. Contains no scripts: it is
instructions and reference material only.

## Pricing

One-time purchase - $9.

## Tags / categories / use cases

Tags: `education`, `coding-education`, `autograder`, `code-grader`, `testing`,
`c-programming`, `assignment-grading`, `assessment`, `test-design`,
`specification`.

Use cases: design a programming-assignment autograder; define per-test
verdicts and partial credit for a course; write hidden tests that actually
reject wrong student programs; specify an exercise package that any runner can
execute; design a progressive hint ladder for a struggling student.

## Permissions

**Tools used:** none required. The skill is advisory - it produces
specifications, not side effects.

**Environment variables:** none.

**File scopes:** read-only, and only the files the user asks about
(`**/*.c`, `**/*.h`, `**/problem.json`, `**/*.md`).

**Note:** this skill describes how to *design* a grader. It never compiles or
runs a submission itself, never invokes a shell, never writes files and never
reaches the network. It has no bundled scripts.

## FAQ

**Does this run my students' code?**
No. It specifies the sandbox - time limit, memory limit, output cap, cleanup -
as configuration your grader enforces, and it never emits a command that
compiles or executes a submission.

**Is the AI allowed to grade?**
No. That is the point of the skill. The invariant is that no model, heuristic
or opinion decides a verdict. A model may write the statement and draft hints.

**Will this work for a language other than C?**
Yes for the verdict model, the package contract and the hint ladder. The
mutation operators and the edge-case checklist are C-specific by design,
because they target the mistakes C students actually make.

**What do I get for $9?**
A specification package: one router skill plus five reference documents -
the verdict taxonomy and result schema, the mutation operator table, the
edge-case checklist, the problem-package schema, and the hint ladder. The
same material as a working implementation is open source.

**Is there a free version?**
The verdict taxonomy and result schema alone are published as a free companion
skill. This package is the complete specification.

## Documentation link

https://jessiejamesportfolio.vercel.app/projects/cpractice/
```

- [ ] **Step 2: Write the demo result (the `## The result` section)**

Replace the placeholder under `## The result` with a complete, untruncated
deliverable of at least 700 characters:

```markdown
### Summary

You need two independent guarantees: a verdict model that supports partial
credit, and a test suite that provably rejects wrong programs. Here is both,
in the order to build them.

### 1. Verdict model and partial credit

Grade **per test**, then aggregate. A single boolean cannot award partial
credit, and cannot tell a student "your loop was correct, your off-by-one was
not".

| Category | Meaning | Action for the student |
|---|---|---|
| `passed` | Output matched expected output | Continue |
| `wrong_answer` | Program ran, output differs | Fix the logic |
| `runtime_error` | Program crashed | Fix the crash |
| `timeout` | Exceeded the wall-clock limit | Improve complexity |
| `output_limit_exceeded` | Produced more output than allowed | Print less |
| `compilation_error` | Did not compile (attempt-level) | Fix the compile error |
| `internal_error` | The grader failed - never the student's fault | Retry, then report |

Per-test result: `test_id`, `test_name`, `visibility`, `category`,
`duration_ms`, `exit_code`, `detail`. Aggregate to an attempt verdict:
all passed -> `passed`; any infrastructure failure -> `internal_error`;
otherwise the first failing category wins.

Two rules that matter: partial credit is computed from the per-test counts,
never from a single overall boolean; and `internal_error` is never counted
against a student.

### 2. Making the tests discriminate

A reference passing its own tests proves consistency, not correctness. Derive
wrong-but-plausible mutants of the reference and check that your suite kills
them.

| Operator | Mutation | Bug it represents |
|---|---|---|
| `add-to-sub` | `+` -> `-` | Sign error in an accumulation |
| `mul-to-add` | `*` -> `+` | Multiplication written as addition |
| `lt-to-le` | `<=` -> `<` | Off-by-one at the boundary |
| `eq-to-ne` | `==` -> `!=` | Equality inverted |
| `inc-to-dec` | `++` -> `--` | Loop runs the wrong way |
| `drop-increment` | loop increment deleted | Infinite loop or early exit |

A mutant that **fails** a test is killed - your suite detects that bug. A
mutant that **passes every test** survived: the suite is too weak to notice
an obviously wrong program. Three or more survivors on an arithmetic problem
means the suite is not ready. Write the expected output **by hand** from the
specification, then confirm it against the reference - if they disagree, the
specification is wrong, and regenerating the expectation from the reference
hides that.

### 3. Edge cases to cover before you trust the suite

Empty and single-element inputs; `n = 1` and `n = n_max`; the value exactly
on the threshold; negative values and the sign of zero; an accumulator that
can overflow its type; signed versus unsigned comparison when the value can go
negative; whether the program consumed exactly the declared number of inputs;
one trailing newline or none - decide the comparison mode once and apply it
everywhere.

### 4. Package the exercise as data

An exercise is a directory of declarative files, not a script: a manifest, a
statement, a reference, and a starter. Each test is `stdin`,
`expected_stdout`, `visibility`, `comparison` - nothing else. Limits come from
configuration; a package may narrow them, never widen them. Hidden test data
never reaches the client before grading.

### 5. Hint ladder

Five levels: pointer at the kind of mistake; the concept to revisit; the shape
of the approach; a worked fragment; and an explicit reveal of the reference
solution at level 5. One level per request. If the package already carries a
hint for that failure mode, use the stored one - the author knows the
learner's misconceptions.

### Next steps

1. Write the verdict model for your course first - it constrains everything else.
2. Pick one reference solution and apply the mutation operators; list the survivors.
3. Close each survivor with one targeted hidden test.
```

- [ ] **Step 3: Check the demo length and completeness**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice
python3 - <<'PY'
import re
text = open("docs/agensi/listings/deterministic-autograder/listing.md").read()
demo = text.split("## The result", 1)[1].split("## Compatibility note", 1)[0]
print("demo characters:", len(demo))
print("truncation markers:", re.findall(r"\.\.\.|truncated|\[more\]", demo))
PY
```

Expected: `demo characters:` above 3000 and `truncation markers: []`.

- [ ] **Step 4: Check every required form field is present**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice
for f in "Skill Name" "Summary" "Full Description" "The request" "The result" "Compatibility note" "Pricing" "Tags / categories / use cases" "Permissions" "FAQ"; do
  grep -q "^## $f$" docs/agensi/listings/deterministic-autograder/listing.md && echo "ok  $f" || echo "MISSING $f"
done
```

Expected: `ok` on all ten lines.

- [ ] **Step 5: Commit**

```bash
git add docs/agensi/listings/deterministic-autograder/listing.md
git commit -m "docs(agensi): listing copy and demo for the autograder skill"
```

---

### Task 6: Produce the logo and the screenshots

**Covers:** S4

**Files:**
- Modify: `docs/agensi/make-logos.py` (add the `deterministic-autograder` mark)
- Output: `docs/agensi/logos/deterministic-autograder.png`
- Output: `docs/agensi/screenshots/` (produced in Task 9 from the recording; Task 6 prepares the folder and the capture list)

**Interfaces:**
- Consumes: nothing.
- Produces: `docs/agensi/logos/deterministic-autograder.png`, a 512x512 square PNG with no text.

- [ ] **Step 1: Add the mark to `make-logos.py`**

Open `docs/agensi/make-logos.py`, find the function that draws each existing
mark (they are drawn in one function per skill), and add:

```python
def deterministic_autograder() -> Image.Image:
    """A verdict scale: one bar accepted, one bar rejected, on a dark ground."""
    img, draw = base()
    draw.rectangle((0, 0, SIZE, SIZE), fill=BG)
    # Accepted bar.
    draw.rounded_rectangle((96, 168, 416, 232), radius=32, fill=ACCENT)
    # Rejected bar, broken into two segments with a gap between them.
    draw.rounded_rectangle((96, 288, 240, 352), radius=32, fill=WARM)
    draw.rounded_rectangle((272, 288, 416, 352), radius=32, fill=MUTED)
    # The invariant: a vertical rule between the two.
    draw.rectangle((248, 120, 264, 400), fill=LIGHT)
    return img
```

Then add it to the script's write-out list next to the other skills, writing
`logos/deterministic-autograder.png`.

- [ ] **Step 2: Generate and check the logo**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice/docs/agensi
python3 make-logos.py
python3 -c "from PIL import Image; im=Image.open('logos/deterministic-autograder.png'); print(im.size, im.mode)"
```

Expected: `(512, 512) RGB`.

- [ ] **Step 3: Confirm it reads at card size**

Run:

```bash
cd /data/data/com.termux/files/home/cpractice/docs/agensi
python3 -c "from PIL import Image; im=Image.open('logos/deterministic-autograder.png'); im.resize((64,64)).save('/tmp/logo-small.png')"
```

Then open `/tmp/logo-small.png` and confirm the two-bar mark is still legible and contains no text.

- [ ] **Step 4: Write the screenshot capture list**

Create `docs/agensi/screenshots/README.md`:

```markdown
# Screenshots for the deterministic-autograder listing

Up to 6 images are accepted. They are cut from the 30-45 second screen
recording (Task 9), not screenshotted separately, so the listing shows one
consistent session.

| # | Frame | Shows | Why it is on the listing |
|---|---|---|---|
| 1 | The request | The prompt as a buyer types it | The activation trigger, in the buyer's words |
| 2 | The verdict table | The seven categories and the partial-credit rule | The core deliverable |
| 3 | The mutation table | Operators and the survivor rule | The part no other skill has |
| 4 | The edge-case checklist | Concrete inputs to cover | Immediately actionable |
| 5 | The hint ladder | Five levels, explicit reveal | The pedagogy half |
| 6 | The CTA | The link to the working implementation | Where the buyer goes next |

Cut at 1280x720, PNG, no text overlays that the recording does not already
contain.
```

- [ ] **Step 5: Commit**

```bash
git add docs/agensi/make-logos.py docs/agensi/logos/deterministic-autograder.png docs/agensi/screenshots/README.md
git commit -m "docs(agensi): logo and screenshot plan for the autograder listing"
```

---

### Task 7: Add the instructor path to the portfolio case study

**Covers:** S5

**Files:**
- Modify: `/data/data/com.termux/files/home/portfolio/projects/cpractice/index.html`

**Interfaces:**
- Consumes: the case study's existing sections `01` - `07` and its CSS classes (`.section`, `.section-head`, `.section-num`, `.section-note`, `.hero`, `.page-hero`, `.reveal`); the `copy-email` affordance already present on the portfolio.
- Produces: a new section `08` with id `instructors`, and a verdict demo block inside it.

- [ ] **Step 1: Read the existing page structure**

Run:

```bash
cd /data/data/com.termux/files/home/portfolio
sed -n '395,454p' projects/cpractice/index.html
```

Expected: the closing `07 - status` section and the closing tags. Note the exact indentation and the closing `</main>` / footer structure so the new section matches.

- [ ] **Step 2: Insert section 08 before the closing of `<main>`**

Insert this block immediately after the end of the `07 - status` section and before the closing `</main>`:

```html
        <section class="section" id="instructors" aria-labelledby="instructors-title">
          <div class="section-head">
            <h2 id="instructors-title"><span class="section-num">08</span> — for instructors</h2>
            <span class="section-note">a course, not a demo</span>
          </div>

          <div class="reveal">
            <p class="lead">
              You teach C. Your students submit source. You want per-test
              verdicts, partial credit, and a hint ladder that unblocks them
              without handing over the answer — and you want the same verdict
              every time, whether the network is up or down.
            </p>

            <h3>What a student's submission returns</h3>
            <table class="table">
              <thead>
                <tr><th>Category</th><th>What happened</th><th>What the student is told</th></tr>
              </thead>
              <tbody>
                <tr><td><code>passed</code></td><td>Output matched expected output</td><td>Continue</td></tr>
                <tr><td><code>wrong_answer</code></td><td>Program ran, output differs</td><td>Fix the logic</td></tr>
                <tr><td><code>runtime_error</code></td><td>Program crashed</td><td>Fix the crash</td></tr>
                <tr><td><code>timeout</code></td><td>Exceeded the time limit</td><td>Improve the complexity</td></tr>
                <tr><td><code>output_limit_exceeded</code></td><td>Printed more than allowed</td><td>Print less</td></tr>
                <tr><td><code>compilation_error</code></td><td>Did not compile</td><td>Fix the compile error</td></tr>
                <tr><td><code>internal_error</code></td><td>The grader itself failed</td><td>Retry — never the student's fault</td></tr>
              </tbody>
            </table>

            <h3>How a class uses it</h3>
            <ol>
              <li><strong>Generate or author a problem set.</strong> Every package is
                validated deterministically before a student sees it: the reference
                must compile and pass its own tests, the tests must discriminate
                wrong-but-plausible student programs, and the concept must be one the
                student is actually ready for.</li>
              <li><strong>Students submit source.</strong> They get a verdict per
                test, not a single boolean — which is what makes partial credit
                possible.</li>
              <li><strong>Stuck students get a hint, one level at a time.</strong>
                Level 1 points at the kind of mistake. Level 5 is an explicit reveal.
                The student chooses how far to be helped.</li>
              <li><strong>You keep the history.</strong> Attempt history plus the
                evidence supports the next practice decision, not a guess.</li>
            </ol>

            <h3>Install it</h3>
            <pre><code>git clone https://github.com/DeltaRhoSygnis/cpractice.git
cd cpractice
pip install -r requirements.txt
./start.sh            # http://127.0.0.1:8000</code></pre>
            <p>
              <strong>No API key is required.</strong> The saved problem packages load
              and every submission is graded with no AI provider configured. A key is
              only needed to <em>generate</em> new exercises and to draft hints on the
              fly. Everything that decides a verdict is deterministic software.
            </p>

            <h3>Using this with your class?</h3>
            <p>
              <!-- COPY THE EXACT EXISTING MAILTO MARKUP FROM THE CONTACT SECTION
                   OF THIS SITE HERE. Do not invent a new address and do not add a
                   second email mechanism. The site already renders one copy-email
                   affordance; this section links to it. -->
              <a class="copy-email" href="#">Email me</a>
              and say which course you teach — I will help you get the first problem
              set running, and I will tell you plainly if it does not fit your setup.
            </p>
          </div>
        </section>
```

Use the **existing** mailto address and the **existing** copy-email markup
that already exists on the site — do not invent a second address or a second
email mechanism. If the page already has a contact section, link to it instead
of adding a duplicate.

- [ ] **Step 3: Verify the page still validates and renders**

Run:

```bash
cd /data/data/com.termux/files/home/portfolio
python3 - <<'PY'
import re
html = open("projects/cpractice/index.html").read()
for needle in ('id="instructors"', 'section-num">08', 'No API key is required', 'copy-email'):
    print(("ok  " if needle in html else "MISS "), needle)
print("sections:", len(re.findall(r'<section class="section"', html)))
print("open/close section balance:", html.count("<section") - html.count("</section>"))
PY
```

Expected: four `ok` lines, a section count of 8, and a balance of 0.

- [ ] **Step 4: Check the copy-email markup is not duplicated**

Run:

```bash
cd /data/data/com.termux/files/home/portfolio
grep -c 'copy-email' projects/cpractice/index.html
```

Expected: `1`. The instructor section reuses the existing affordance; if the
count is `2` or more, remove the duplicate introduced in Step 2.

- [ ] **Step 5: Preview locally**

Run:

```bash
cd /data/data/com.termux/files/home/portfolio
python3 -m http.server 8123
```

Open `http://127.0.0.1:8123/projects/cpractice/` and confirm: the section renders with the site's typography, the table is readable on a narrow viewport, the install block scrolls horizontally, and the email link is clickable.

- [ ] **Step 6: Commit**

```bash
cd /data/data/com.termux/files/home/portfolio
git add projects/cpractice/index.html
git commit -m "feat: add the instructor path to the cpractice case study"
```

---

### Task 8: Turn on referrer measurement

**Covers:** S6

**Files:**
- Modify: `/data/data/com.termux/files/home/portfolio/index.html` (uncomment the analytics tag)
- Modify: `/data/data/com.termux/files/home/portfolio/projects/cpractice/index.html` (same tag, if the case study page does not inherit it)

**Interfaces:**
- Consumes: the Vercel Analytics script tag already present but commented out.
- Produces: page views and referrers for the case study, which is how "did Agensi send anyone?" gets answered.

- [ ] **Step 1: Find the commented analytics tags**

Run:

```bash
cd /data/data/com.termux/files/home/portfolio
grep -rn "_vercel/insights" index.html projects/cpractice/index.html
```

Expected: one or two commented lines of the form
`<!-- <script defer src="/_vercel/insights/script.js"></script> -->`.

- [ ] **Step 2: Enable it on both pages**

Replace the commented line with:

```html
    <script defer src="/_vercel/insights/script.js"></script>
```

- [ ] **Step 3: Verify no other page references bryllim**

Run:

```bash
cd /data/data/com.termux/files/home/portfolio
grep -rni "bryllim" . --exclude-dir=.git && echo "REFERENCE FOUND" || echo "clean"
```

Expected: `clean`. If it appears, remove it — that domain is a design reference, not a link target.

- [ ] **Step 4: Commit**

```bash
cd /data/data/com.termux/files/home/portfolio
git add index.html projects/cpractice/index.html
git commit -m "chore: enable vercel analytics on the portfolio and case study"
```

---

### Task 9: Record the demo video and cut the screenshots

**Covers:** S4, S6

**Files:**
- Output: `docs/agensi/dist/deterministic-autograder-demo.mp4` (upload to the listing, not committed)
- Output: `docs/agensi/screenshots/01-verdict-table.png` … `06-cta.png`

**Interfaces:**
- Consumes: the request and result text from Task 5; the capture list from Task 6; the installed skill package.
- Produces: one 30-45 second recording and six PNG frames.

- [ ] **Step 1: Install the package into the agent used for the recording**

Run:

```bash
mkdir -p ~/.claude/skills
cp -r /data/data/com.termux/files/home/cpractice/docs/agensi/skills/deterministic-autograder ~/.claude/skills/
ls ~/.claude/skills/deterministic-autograder
```

Expected: `SKILL.md`, `README.md`, `references/`.

- [ ] **Step 2: Rehearse the demo against the exact request from the listing**

Paste the `## The request` text into the agent and confirm the answer
contains: the verdict table, the partial-credit rule, the mutation operator
table, the edge-case checklist, the hint ladder and the next steps.

Expected: all six blocks appear. If any is missing, the skill's procedure in
`SKILL.md` is not directing the agent strongly enough — tighten it, and
re-run Task 3 Step 2 (word count) afterwards.

- [ ] **Step 3: Record**

Record the screen while the agent answers the request, scrolling at a readable
pace, ending on the section that shows where the buyer goes next. Target
30-45 seconds; cut dead air at the start and end.

Expected: one MP4, H.264, 1280x720 or larger, under 60 seconds.

- [ ] **Step 4: Cut the six frames**

Cut the frames listed in `docs/agensi/screenshots/README.md`, in order, at
1280x720 PNG.

Expected: `01-verdict-table.png` through `06-cta.png` exist in
`docs/agensi/screenshots/`.

- [ ] **Step 5: Verify the video is usable**

Check: it plays in a browser, the text in the frames is legible at 50% zoom,
and the audio (if any) is unnecessary to understand it.

- [ ] **Step 6: Commit the frames, not the video**

```bash
cd /data/data/com.termux/files/home/cpractice
git add docs/agensi/screenshots/
git commit -m "docs(agensi): listing screenshots"
```

The MP4 stays out of git (`docs/agensi/dist/` is ignored) and is uploaded to the
listing form.

---

### Task 10: Write the launch runbook and submit

**Covers:** S1, S2, S6, S7, S8, S9, S10

**Files:**
- Create: `docs/agensi/LAUNCH.md`
- Output: the published listing on agensi.io

**Interfaces:**
- Consumes: the ZIP from Task 4, the listing copy from Task 5, the logo from Task 6, the frames and video from Task 9, the landing page from Task 7.
- Produces: a published listing, a KYC-completed payout rail, and a written 90-day decision rule.

- [ ] **Step 1: Write the runbook**

Create `docs/agensi/LAUNCH.md`:

```markdown
# Launch runbook — deterministic-autograder on Agensi.io

**Price:** $9, one-time. **One listing. No bundle.** **KYC required** before a
paid listing goes live (a connected payment method is not the same as
completed KYC - verify in the dashboard).

## Pre-submission checklist

- [ ] `name` == folder name == `deterministic-autograder` (lowercase, hyphens)
- [ ] `description` written as "Use when the user asks to..." with 3-5 trigger phrases
- [ ] `SKILL.md` under ~1000 words; depth in `references/`
- [ ] At least one supporting file (five present)
- [ ] `README.md` in the folder
- [ ] ZIP = one top-level folder, `SKILL.md` at its root
- [ ] Text files only; no binaries, no symlinks, no OS cruft
- [ ] No repo paths, no provider names, no internal URLs, no secrets
- [ ] Nothing in the body that reads as a dangerous command or a prompt override
- [ ] `python3 skills/deterministic-autograder/verify-package.py dist/deterministic-autograder.zip` prints OK
- [ ] Tested in two agents (Claude Code and one other)
- [ ] Logo uploaded (512x512 square)
- [ ] Demo section pasted in full, untruncated
- [ ] Demo video URL uploaded
- [ ] Screenshots uploaded (up to 6)
- [ ] Permissions declared: no terminal, no writes, no network, no env vars; read-only globs
- [ ] Documentation link: https://jessiejamesportfolio.vercel.app/projects/cpractice/
- [ ] KYC completed

## Order of operations

1. Submit the listing (paid). Review takes 24-48h and may come back with a
   named failing check on the 8-point security scan - fix the named cause and
   resubmit; there is no penalty for failing.
2. While it is in review, complete KYC and confirm the payout rail.
3. Publish the build-in-public post (Task "Distribution" below).
4. Start the outreach wave: the free install of this same package plus the
   case-study link is the leave-behind.

## Distribution

One post per surface, showing the workflow rather than the pitch: the messy
manual task, then the agent doing it, then the link.

- [ ] Build-in-public post (blog or dev.to): "Your hidden tests pass a wrong
      program. Here is how I found out." The post links the listing and the repo.
- [ ] One X/LinkedIn post with the demo clip.
- [ ] One Reddit post in the relevant teaching or C communities, following that
      community's self-promotion rules.
- [ ] Outreach list of ~30 instructors, bootcamp leads and course-tool Discord
      admins. The leave-behind is the free skill install; the CTA is the case study.

## Measurement

| Signal | Where | Why it matters |
|---|---|---|
| Views -> installs -> reviews | Agensi Creator Studio | Discovery quality |
| Case-study visits and referrers | Vercel Analytics | Did the listing send anyone |
| Repo clones and cloners | GitHub traffic API | Did they act on it |
| Instructor emails | Inbox | The only real conversion event |

## The 90-day decision rule

| Outcome at day 90 | Action |
|---|---|
| >= 50 installs and >= 10 case-study visits, or >= 3 instructor emails | Channel works. Add the second listing, keep investing. |
| Installs but no instructor interest | The skill lands, the audience does not. Keep the listing as a portfolio artifact, stop investing, redirect to direct outreach. |
| Neither | Dead traffic channel. Leave the listing live, spend nothing more on it. |

## Not doing

- The four tutor skills are **not** listed.
- No second listing, no bundle, no free companion (unless KYC blocks payment -
  in which case split `result-taxonomy.md` into a free `deterministic-grading-contract`).
- No hosted CPractice instance.
```

- [ ] **Step 2: Verify the checklist against reality**

Run, for each item that can be checked mechanically:

```bash
cd /data/data/com.termux/files/home/cpractice/docs/agensi
python3 skills/deterministic-autograder/verify-package.py dist/deterministic-autograder.zip
python3 -c "from PIL import Image; print(Image.open('logos/deterministic-autograder.png').size)"
ls screenshots/
```

Expected: `OK: ...`, `(512, 512)`, and the six frames listed.

- [ ] **Step 3: Commit the runbook**

```bash
cd /data/data/com.termux/files/home/cpractice
git add docs/agensi/LAUNCH.md
git commit -m "docs(agensi): launch runbook and 90-day decision rule"
```

- [ ] **Step 4: Submit the listing**

Upload `docs/agensi/dist/deterministic-autograder.zip`, paste every field from
`docs/agensi/listings/deterministic-autograder/listing.md` in order, upload the
logo, the demo video URL and the screenshots, set the price to **$9 one-time**,
and submit.

Expected: a submission id and a review state of "pending" within minutes.

- [ ] **Step 5: Record the outcome**

Add the submission id and date to the top of `docs/agensi/LAUNCH.md` and commit:

```bash
git add docs/agensi/LAUNCH.md
git commit -m "docs(agensi): record the listing submission"
```

---

## Verification

Before declaring the plan complete, run:

```bash
cd /data/data/com.termux/files/home/cpractice
pytest -q
cd docs/agensi && ./build-zips.sh && python3 skills/deterministic-autograder/verify-package.py dist/deterministic-autograder.zip
cd /data/data/com.termux/files/home/portfolio && grep -c 'id="instructors"' projects/cpractice/index.html
```

Expected: the full suite passes, the archive verifies, and the instructor
section exists exactly once.

---

## Out of Scope for This Plan

- Publishing anything other than the one listing (spec S9).
- The free companion skill, unless KYC blocks payment (Task 10, Step 4 note).
- A hosted CPractice instance and instructor onboarding beyond the case study.
- The outreach list, its cadence, and its templates (referenced in Task 10,
  to be designed separately).
