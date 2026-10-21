---
name: deterministic-code-grader
description: Designs a reproducible autograder for source-code exercises, where the model writes problems and hints but never decides pass or fail. Use when the user asks to build a code judge, autograder, CI checker, test harness, or submission grader, to review an existing grader, or to decide where the pass/fail boundary should sit.
---

# Deterministic Code Grader

Build a grader whose verdict is reproducible: the same submission and the same
tests always produce the same category, and the verdict is decided by software,
not by a model.

## The one rule that governs everything

**A model may write exercises, write hints, and explain failures. A model may
never decide pass/fail.** If an LLM is on the grading path, the output is not
reproducible, cannot be defended to a student, and cannot be tested. Keep the
model out of the evaluator entirely — it should not even be importable from
grading code.

Corollary: when you add an LLM feature, check that it cannot influence the
verdict. If the model generates the *test data*, the model has influence. Either
don't, or validate the generated data with deterministic checks before use.

## Separate the two kinds of failure

Most graders conflate "the student is wrong" with "the grader is broken." Use a
closed taxonomy with two families:

**Learner failure** (the submission is at fault)
- `passed`
- `wrong_answer` — output did not match expected
- `compilation_error` — the source did not build
- `runtime_error` — the program crashed or exited non-zero
- `timeout` — exceeded the time limit
- `output_limit_exceeded` — produced more output than allowed

**Infrastructure failure** (the grader is at fault — never blame the learner)
- `internal_error` — the checker itself failed (missing compiler, unwritable
  temp dir, bug in the comparator)

The distinction is not cosmetic. A missing compiler reported as "wrong answer"
teaches a student a false lesson and generates an unanswerable support ticket.
Infrastructure failures must be retried or surfaced as a system error, and
must be logged separately from learner results.

## The test model

Tests are **declarative data**, never scripts. A test case is a value with
fields, something like:

```
id, name, visibility (public|hidden), stdin, expected_stdout,
comparison_mode, time_limit_ms?, tags?, concept?
```

Why data and not scripts:
- Data is serializable, diffable, reviewable, and storable.
- A script per test is an arbitrary-code-execution surface in your data store.
- Data tests can be validated by a linter before use (see validation below).

### Comparison modes

Implement at least these two, and make the mode explicit per test:

- `exact_normalized` — compare after normalizing line endings and trailing
  whitespace on each line, and stripping trailing newlines. This is the
  default; it accepts the formatting differences that are not mistakes.
- `whitespace_tolerant` — compare after collapsing all whitespace runs to a
  single space. Use only for numeric or token-stream problems where spacing
  carries no meaning.

Do not implement a "fuzzy" mode that uses a model, a similarity score, or a
threshold. If a case cannot be expressed exactly, redesign the test or the
problem.

Never compare floats with a tolerance unless the problem statement declares
the tolerance, and then apply the declared tolerance in the comparator, not in
the test data.

### Visibility

Every test is `public` or `hidden`. Public tests may be shown with their
expected output; hidden tests must never reach the client — not the input, not
the expected output, not a hint of them. Serialize student-facing test data
through a separate, explicit projection that drops hidden fields, rather than
filtering on the client or "just not including it" by convention.

## The grading sequence

Follow this order, and report each stage distinctly:

1. **Prepare** — create a fresh temporary workspace per submission. Never
   reuse a directory between runs; stale artifacts cause phantom passes.
2. **Compile** — one compile for the whole submission. Record success,
   diagnostics, and duration. If compilation fails, stop: report
   `compilation_error` with the compiler's diagnostics, and do not run tests.
3. **Run** — for each test: feed `stdin`, capture stdout, enforce limits,
   record duration and exit code.
4. **Compare** — apply the test's comparison mode. Record a category, never a
   raw diff of hidden expected output.
5. **Report** — return a structured report: overall category, per-test results
   (id, name, visibility, category, duration, exit code, safe detail), and
   compile diagnostics if any.
6. **Clean up** — remove the workspace in a `finally` block, even on
   exception or timeout. Leaked workspaces accumulate until the disk fills.

## Limits come from configuration, never from constants

Time limit, memory limit, output size cap, compiler binary, and language
standard are all configuration. Hard-coding them means every deployment is
wrong somewhere, and a user cannot tune them.

- **Time limit**: enforce it on the process, not by measuring duration after
  the fact. A program that hangs must be killed, not waited on.
- **Memory limit**: apply at the process level where the platform supports it.
- **Output size cap**: truncate *while* reading, not after. A program that
  prints 4 GB will exhaust memory before you get to check its length.
- Kill the process group, not just the child, or orphans survive and hold the
  workspace open.

## Running untrusted code safely

Submitted code is hostile input. The rules:

- **Never invoke the submitted source as a shell command.** Write it to a file
  with a fixed name inside the workspace, and run the compiler/binary by path.
  Never build a shell command string that interpolates user content.
- **Never accept a compiler path, a command, a test script, or a working
  directory from the client.** These are configuration, configured server-side.
  A browser must never be able to choose what gets executed.
- **Compile and run with the fewest privileges you can**: a dedicated
  unprivileged user where available, no network, a fresh process group, a
  wall-clock timeout, and a filesystem scoped to the workspace.
- **Use argument arrays, not shell strings**, when invoking the compiler.
- **Treat the compiler as part of the trust boundary.** It parses untrusted
  input; keep it patched and run it with the same limits you give the program.
- **Clean up after every run**, including the failure paths.

For local development this may be "a temp directory and a timeout." For a hosted
deployment, treat the sandbox as a separate security problem with its own
review: container/VM isolation, seccomp, resource cgroups, and a fresh
environment per run. Say so honestly in your docs rather than implying a
`tempfile` call is a sandbox.

## Validate exercises before publishing them

An exercise whose reference solution fails, or whose tests all pass, is worse
than no exercise. Before an exercise goes live, run a deterministic validation
pass:

1. The **reference solution must pass every test.** Non-negotiable.
2. **Deliberately broken variants (mutants) must fail.** Flip a comparison
   operator, drop an edge case, use `<` where `<=` belongs. If a mutant passes,
   the test that should have caught it is not doing its job. This is the
   highest-value check and the one most often skipped.
3. **Structural lint**: a test needs an id, a name, a visibility, an input
   format, and an expected output; inputs must match what the problem
   statement promises; expected outputs must be well-formed for the mode.
4. **Coverage check**: the public tests should be a subset of the hidden ones,
   and the hidden set should cover the edge cases the statement calls out
   (empty input, single element, maximum values, duplicates, negative values).
5. **Pedagogy check**: the statement states the input format, the output
   format, the constraints, and at least one worked example; the difficulty
   matches the concepts it claims to teach.
6. **Concept tagging**: tag the exercise with the concepts it exercises, so it
   can be sequenced and so a learner's progress is measurable.

Keep the mutation step even if you drop everything else. It is what converts
"tests exist" into "tests are meaningful."

## Report failures in a way a learner can act on

- Show the compiler's diagnostics verbatim on a compilation error. The student
  needs the actual line and column.
- For a wrong answer, say which test failed and what the program produced —
  but only for public tests. For hidden tests, report the category and
  nothing about the expected value.
- For a timeout, say the time limit and what it was given.
- Do not editorialize inside the deterministic report. Explanation is a separate
  layer: the deterministic report says *what happened*; a model-powered feedback
  layer may say *what to do about it*, and it must never contradict the
  report. If the two disagree, the deterministic one wins.

## Progressive hints, if you add them

Hints are a separate concern from grading, and they must not leak the answer
by accident.

- Fixed number of levels (for example three: direction, approach, near-solution).
- Each level is revealed only on request, and the count of revealed levels is
  per-learner, per-exercise state.
- Never repeat a level that was already shown.
- A solution reveal is a separate, explicit action with its own state.
- Hint text may not contain the expected output of a hidden test.

## Output format

When this skill is used to design or review a grader, produce the following
sections, in this order. Omit a section only if it genuinely does not apply,
and say why.

1. **Verdict boundary** — one paragraph naming exactly which component
   decides pass/fail, and an explicit statement of what the model is allowed
   to do (write problems, write hints, explain a failure) and forbidden to do
   (choose a verdict, generate test data that becomes the verdict, soften a
   failure into a pass).
2. **Outcome model** — the category list, split into learner failure and
   infrastructure failure, and the rule that derives the attempt-level verdict
   from the per-test results.
3. **Data model** — the test case fields, the visibility field, and the
   comparison modes, as concrete field names with types.
4. **Grading sequence** — the ordered stages, with what each stage records and
   what it aborts on.
5. **Limits and configuration** — every limit named, where it comes from, and
   how it is enforced (process-level, not measured after the fact).
6. **Trust boundary** — what runs untrusted code, what a client may and may
   not choose, and what cleanup is guaranteed on every path including
   exceptions and timeouts.
7. **Secret-handling** — a statement that no hidden test data reaches the
   client, and the mechanism that guarantees it (a projection step, not
   client-side filtering).
8. **Test plan** — the categories to cover, and the properties to assert
   (reproducibility, isolation, no leakage, cleanup, determinism).
9. **Risks and open decisions** — the things that are wrong or missing in the
   current design, ordered by severity, each with a concrete fix.

For a review of an existing grader, lead with the risk list rather than the
architecture, and for each finding state: what is wrong, the concrete failure
it causes, and the smallest change that fixes it.

## Test your grader

The grader is the product; test it like the product. At minimum, one test per
category in the taxonomy: compilation error, passed, wrong answer, runtime
error, timeout, output limit exceeded, and internal error.

Also test the properties that are easy to break:

- **Reproducibility**: the same submission graded twice yields the same category.
- **Isolation**: a submission that tries to read a hidden test file, write
  outside the workspace, or fork-bomb must fail cleanly and leave no residue.
- **No leakage**: the student-facing payload contains no hidden test data —
  assert this directly in a test, not by inspection.
- **Cleanup**: no workspace survives a run, including a crashed one.
- **Determinism**: run the suite twice; identical results.

Use mocked model responses in the grader's own test suite. A grading test that
calls a live API is not a test of the grader.
