---
name: deterministic-autograder
description: Use when the user asks to design an autograder, grade programming assignments, define per-test verdicts and partial credit, write hidden test cases, prove their tests are not vacuous, or structure a problem package for an automated judge. Also use when the user asks why a student's submission was graded wrong, or wants a hint ladder for a struggling learner.
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
categories the grader can actually distinguish - a grader that cannot detect a
timeout must not offer a `timeout` verdict.

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
