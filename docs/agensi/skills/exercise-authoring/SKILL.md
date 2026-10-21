---
name: exercise-authoring
description: Writes programming exercises reliable enough to grade automatically, with declarative hidden tests, reference-solution validation and mutation checks. Use when the user asks to write a programming problem, create practice exercises or test cases, design hidden tests for a judge, or audit an existing test set for gaps.
---

# Exercise Authoring

An exercise is only as good as its tests. A problem with vague tests produces
students who fail for reasons they cannot see, and a problem with no hidden
tests produces students who pass by pattern-matching the public examples.

## Start with a blueprint, not a prompt

Never write the problem statement first. Define the pedagogical skeleton
before any wording exists:

- **Concept(s)**: the one or two ideas the exercise exercises. More than three
  and it is not an exercise, it is a project.
- **Objective**: what the learner can do afterwards, stated as a capability
  ("choose the right loop and bound the search", not "practice loops").
- **Prerequisites**: what must already be understood. If the prerequisite
  isn't in the curriculum, the exercise is misplaced.
- **Difficulty**: an ordinal level, anchored to a stated rubric — for example
  *single concept, one application* → *single concept, non-obvious edge cases*
  → *two concepts combined* → *open-ended with ambiguity to resolve*. The
  rubric is what makes difficulty comparable across exercises.
- **Target duration**: an expected solve time. It is a sanity check, and it
  catches exercises that are secretly two exercises.

Then derive the statement from the blueprint. The blueprint also becomes the
metadata you tag the exercise with, so it can be sequenced into a curriculum
and so a learner's progress is measurable.

## The statement must be self-sufficient

A learner must be able to solve the exercise from the statement alone, with no
external references and no guessing about the input format. Every statement
states:

1. The task, in one or two sentences, in terms of the learner's goal — not
   "implement function `foo`" but "compute the number of days until the next
   Friday".
2. The exact input format: how many lines, what each line contains, the type
   and range of each value, and what a valid input never contains.
3. The exact output format: what to print, in what order, and with what
   precision or units.
4. The constraints, stated as numbers. A constraint that is not stated cannot
   be relied on.
5. At least one worked example, with its input and its expected output.
6. Any constraint on the solution: required complexity, forbidden libraries,
   no floating point, "do not use recursion", and so on. These are common
   teaching goals; state them or they will not be taught.

Say "print the number of days" and not "the result". Every ambiguity you leave
is a fairness complaint later.

## Hidden tests are the product

Public tests teach; hidden tests measure. Aim for a public set that is a small
subset of the hidden set, so a learner who has genuinely understood the
problem passes the hidden set, and a learner who pattern-matched the examples
does not.

For each exercise, cover these categories deliberately:

- **Nominal** — a typical input straight from the description.
- **Minimal** — the smallest legal input: zero, one element, empty string.
- **Maximal** — the largest legal value in every dimension at once.
- **Boundary** — the value immediately before and immediately after each
  threshold in the constraints. Off-by-one is the single most common
  correctness bug; the boundary is the test that catches it.
- **Degenerate / shape** — all elements equal, already sorted, strictly
  decreasing, duplicates, alternating pattern.
- **Negative / special** — negative numbers where allowed, zero, very large
  magnitudes, values that would overflow a naive 32-bit intermediate.
- **Input-format stress** — extra whitespace, trailing newline present or
  absent, multiple spaces between tokens, values split across lines if the
  format allows it.
- **Idempotence / repetition** — for exercises with accumulation or state, the
  same input processed twice.

For each test, record the *reason* it exists as a tag or comment. A test with
no reason is usually a test of the same thing as another one, or a test of
nothing.

## Tests are data, and data is lintable

A test case is a value — id, name, visibility, input, expected output,
comparison mode, and a rationale tag — never an executable script. Data can be
validated before use; scripts cannot.

Two comparison modes cover nearly everything:

- **exact_normalized** (default): compare after normalizing line endings and
  trailing whitespace per line, and stripping trailing newlines.
- **whitespace_tolerant**: compare after collapsing whitespace runs to single
  spaces. Only for problems where spacing carries no meaning.

If a test needs "approximately equal", the problem needs a declared tolerance
and the comparator needs to apply it explicitly. Never let the tolerance live
in the test data and never approximate.

## Validate the exercise before it ships

Run this pass on every exercise, every time. It is mechanical, so make it
automatic:

1. **The reference solution passes every test.** A failing reference solution
   is the number one cause of a broken exercise set. If it fails, the test is
   wrong until proven otherwise.
2. **Mutants fail.** Write several deliberately wrong variants — flip `<` to
   `<=`, off-by-one on a bound, forget to handle the empty case, print in the
   wrong order, drop the last element. Each must fail at least one test. A
   mutant that passes means the test that should have caught it is either
   missing or too weak. This check is what makes your test suite meaningful
   rather than merely present.
3. **Statement/test agreement**: every constraint stated in the text has a
   corresponding boundary test, and every test's input respects the stated
   format. Mismatch in either direction is a bug.
4. **Coverage**: the hidden set covers every category listed above for this
   exercise's shape. If some category does not apply, say why in the exercise
   metadata.
5. **Determinism**: the reference solution produces identical output across
   repeated runs. If it does not (uninitialized memory, hash iteration order,
   time dependence), the exercise is not gradable.
6. **Time and space fit the stated constraints**, and the stated constraints
   are the ones the difficulty level assumes.

## Difficulty is a claim you can check

An exercise is "medium" if a learner who has the prerequisites and has solved
the easy exercises in the same family solves it in roughly the target time
without hints. Calibrate empirically:

- Solve the exercise yourself, timed, cold. If it takes you much longer than
  the target, it is harder than labeled.
- Have a learner at the intended level attempt it. Observe *where* they stall.
  A stall point is a statement defect: the information needed at that point
  was missing or buried.
- Count the distinct insights required. Each additional insight is a level.
- Check the error profile: if a common wrong approach is *not* caught by any
  test, the exercise is too easy to be labelled as testing that concept.

Recalibrate when the exercise or its family changes, and whenever a cohort
tells you it disagrees with the label.

## Map misconceptions explicitly

For each exercise, name the two or three wrong beliefs a learner is likely to
carry into it, and the error each produces. Typical ones: off-by-one on
inclusive ranges; using `<` for a maximum when the constraints say "at most";
assuming sorted input; forgetting to handle the empty case; printing
debug output alongside the answer; ignoring the output format while getting
the value right.

Then check two things: the *statement* should make the correct behaviour clear
enough that the misconception is avoidable, and the *tests* should catch the
error. An exercise where a common misconception leads to a passing submission
is teaching the misconception.

This mapping is also what lets a feedback layer give a targeted hint: the
failing test tells you which misconception is in play, without you having to
re-read the student's code.

## Progressive hints

Three levels, each one step further than the last:

1. **Direction** — name the concept and where to look ("think about what the
   loop bound should be at the edges").
2. **Approach** — the shape of the solution without the code ("scan once,
   tracking the largest value seen so far, and update after the comparison").
3. **Near-solution** — the critical line or the key expression, with the rest
   left to the learner.

Rules: hints are requested, never pushed. The number of levels already shown
is per-learner, per-exercise state. A level is never shown twice. A full
solution is a separate, explicit action. And no hint may contain the expected
output of a hidden test — check this mechanically, not by eye.

## Keep the exercise package portable

An exercise is a self-contained package: statement, metadata (concepts,
difficulty, duration, blueprint), reference solution, public tests, hidden
tests, comparator settings, misconception map, and hint set. Two consequences
that pay off immediately:

- **It must be importable and exportable** without loss. If a teacher cannot
  move an exercise between courses, you have a platform, not a course.
- **The package schema is provider-independent.** Nothing inside it may assume
  which model, API, or vendor produced it. Models generate candidate content;
  the validator and the grader decide what ships. An exercise that only
  exists as an API response is not an exercise.

## Output format

When producing an exercise, emit these sections in this order. Keep the
section headings exactly as written so the package can be parsed or checked
mechanically.

1. **Blueprint** — concept, objective, prerequisites, difficulty (against the
   stated rubric), target solve time.
2. **Statement** — the full learner-facing text: task, input format, output
   format, constraints, one worked example, and any solution constraints.
3. **Metadata** — concepts, difficulty, duration, visibility split, the
   comparison mode per test.
4. **Reference solution** — the correct program.
5. **Test set** — each case with: id, name, visibility, category, input,
   expected output, comparison mode, and a one-line rationale for why it
   exists. Public cases first, then hidden.
6. **Coverage table** — which stated constraint each test covers, and the bug
   it would catch.
7. **Misconception map** — the likely wrong beliefs, the error each produces,
   and the test that catches it.
8. **Hint ladder** — three levels, each one step further than the last, with
   no hidden expected output anywhere in it.
9. **Validation report** — the results of the validation pass: does the
   reference solution pass every test (yes/no, per test), which mutants were
   written and which were caught, whether the reference is deterministic
   across repeated runs, and any category from the coverage catalogue that was
   considered and skipped, with the reason.

For an audit of an existing test set, lead with the gaps: each missing
category, the constraint it leaves untested, and the mutant that would
currently survive.

## Checklist before publishing

- [ ] Blueprint defined; concept, objective, prerequisites, difficulty, duration
- [ ] Statement complete: task, input format, output format, constraints, example
- [ ] Public tests are a subset of hidden tests
- [ ] Edge categories covered: minimal, maximal, boundary, degenerate, negative
- [ ] Every test has a rationale tag
- [ ] Reference solution passes all tests
- [ ] Mutants all fail
- [ ] Statement/test agreement verified
- [ ] Reference solution deterministic across runs
- [ ] Difficulty matches the observed solve profile
- [ ] Misconceptions named, and caught by tests
- [ ] Hints written at three levels, no hidden outputs leaked
- [ ] Package contains no provider-specific or environment-specific data
