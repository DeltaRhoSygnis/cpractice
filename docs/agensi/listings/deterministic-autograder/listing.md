# Listing — deterministic-autograder

Every field of the Agensi.io upload form, copy-paste ready.

---

## Skill Name

Deterministic Autograder — Verdict Model and Test Strength

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

- **Seven verdict categories** — passed, wrong answer, runtime error, timeout,
  output limit exceeded, compilation error, internal error — with per-test
  results and a partial-credit rule. A single boolean cannot tell a student
  "your loop was correct, your off-by-one was not".
- **Test discrimination through mutation** — ten C-specific mutation
  operators, and the rule that a surviving mutant is a finding: the suite does
  not catch an obviously wrong program.
- **An edge-case checklist** for student programs: empty and single-element
  inputs, boundaries, sign of zero, overflow, signed/unsigned comparison,
  output shape.
- **The problem-package contract** — an exercise is declarative data (input,
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
| `internal_error` | The grader failed — never the student's fault | Retry, then report |

Per-test result: `test_id`, `test_name`, `visibility`, `category`,
`duration_ms`, `exit_code`, `detail`. Aggregate to an attempt verdict: all
passed → `passed`; any infrastructure failure → `internal_error`; otherwise
the first failing category wins.

Two rules that matter: partial credit is computed from the per-test counts,
never from a single overall boolean; and `internal_error` is never counted
against a student. A grader failure is a missing score, not a low score.

### 2. Making the tests discriminate

A reference passing its own tests proves consistency, not correctness. Derive
wrong-but-plausible mutants of the reference and check that your suite kills
them.

| Operator | Mutation | Bug it represents |
|---|---|---|
| `add-to-sub` | `+` → `-` | Sign error in an accumulation |
| `mul-to-add` | `*` → `+` | Multiplication written as addition |
| `lt-to-le` | `<=` → `<` | Off-by-one at the boundary |
| `eq-to-ne` | `==` → `!=` | Equality inverted |
| `inc-to-dec` | `++` → `--` | Loop runs the wrong way |
| `drop-increment` | loop increment deleted | Infinite loop or early exit |

A mutant that **fails** a test is killed — your suite detects that bug. A
mutant that **passes every test** survived: the suite is too weak to notice an
obviously wrong program. Three or more survivors on an arithmetic problem
means the suite is not ready.

Worked example: for `sum two integers`, a mutant turning `a + b` into `a - b`
is killed by the negative-input test. If that test is missing, the mutant
survives and the grader will happily accept `a - b` for every student who
forgets to negate. That single failure mode is why the instrument exists.

Two rules keep the signal honest: mutate only the first occurrence of each
pattern, and never remove `return 0;` from `main` — since C99 an implicit
`return 0;` is added, so that mutant is semantically equivalent to the
reference and would survive every time, flagging correct tests as weak.

### 3. Edge cases to cover before you trust the suite

Empty and single-element inputs; `n = 1` and `n = n_max`; the value exactly on
the threshold; negative values and the sign of zero; an accumulator that can
overflow its type; signed versus unsigned comparison when the value can go
negative; whether the program consumed exactly the declared number of inputs;
one trailing newline or none — decide the comparison mode once and apply it
everywhere.

### 4. Package the exercise as data

An exercise is a directory of declarative files, not a script: a manifest, a
statement, a reference, and a starter. Each test is `stdin`,
`expected_stdout`, `visibility`, `comparison` — nothing else. Limits come from
configuration; a package may narrow them, never widen them. Hidden test data
never reaches the client before grading, and the distribution code must not
already pass the hidden tests.

Write the expected output **by hand** from the specification, then confirm it
against the reference — if they disagree, the specification is wrong, and
regenerating the expectation from the reference hides that.

### 5. Hint ladder

Five levels: pointer at the kind of mistake; the concept to revisit; the shape
of the approach; a worked fragment; and an explicit reveal of the reference
solution at level 5. One level per request. If the package already carries a
hint for that failure mode, use the stored one — the author knows the
learners' misconceptions.

### Next steps

1. Write the verdict model for your course first — it constrains everything else.
2. Pick one reference solution and apply the mutation operators; list the survivors.
3. Close each survivor with one targeted hidden test.

## Compatibility note

Works with any agent that supports the SKILL.md format — Claude Code, Codex
CLI, Cursor, VS Code Copilot, Gemini CLI, Windsurf, Aider, Cline, Zed and
others. No runtime, no packages, no network access, no credentials, no file
access beyond the files you ask it to read. Contains no scripts: it is
instructions and reference material only.

## Pricing

One-time purchase — $9.

## Tags / categories / use cases

Tags: `education`, `coding-education`, `autograder`, `code-grader`, `testing`,
`c-programming`, `assignment-grading`, `assessment`, `test-design`,
`specification`.

Use cases: design a programming-assignment autograder; define per-test
verdicts and partial credit for a course; write hidden tests that actually
reject wrong student programs; specify an exercise package that any runner can
execute; design a progressive hint ladder for a struggling student.

## Permissions

**Tools used:** none required. The skill is advisory — it produces
specifications, not side effects.

**Environment variables:** none.

**File scopes:** read-only, and only the files the user asks about
(`**/*.c`, `**/*.h`, `**/problem.json`, `**/*.md`).

**Note:** this skill describes how to *design* a grader. It never compiles or
runs a submission itself, never invokes a shell, never writes files and never
reaches the network. It has no bundled scripts.

## FAQ

**Does this run my students' code?**
No. It specifies the sandbox (time limit, memory limit, output cap, cleanup) as
configuration your grader enforces, and it never emits a command that compiles
or executes a submission.

**Is the AI allowed to grade?**
No. That is the point of the skill. The invariant is that no model, heuristic
or opinion decides a verdict. A model may write the statement and draft hints.

**Will this work for a language other than C?**
Yes for the verdict model, the package contract and the hint ladder. The
mutation operators and the edge-case checklist are C-specific by design,
because they target the mistakes C students actually make.

**What do I get for $9?**
A specification package: one router skill plus five reference documents — the
verdict taxonomy and result schema, the mutation operator table, the
edge-case checklist, the problem-package schema, and the hint ladder. The
same material as a working implementation is open source.

**Is there a free version?**
Not yet. This is the only listing at the moment, and it is the complete
specification — the verdict taxonomy, the mutation operator table, the
edge-case checklist, the package schema and the hint ladder. The same material
is open source and linked at the bottom of this page if you would rather read
it than pay for it.

## Documentation link

https://jessiejamesportfolio.vercel.app/projects/cpractice/
