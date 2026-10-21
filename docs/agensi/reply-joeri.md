# Draft reply to Joeri Brons (Agensi.io)

Subject: Re: CPractice skills on Agensi

Hi Joeri,

Thanks for reaching out — and for the note on the name: the project is
CPractice (a C programming practice platform with deterministic grading).

I'd be interested in listing. A bit of context on what I have, so we can work
out whether it's a fit:

I have two categories of material.

**Tutor skills** — four standalone, single-file skills I wrote for AI coding
partners: code review that teaches the reasoning behind findings, debugging
that tests the learner's hypotheses with evidence, examination through
prediction/explanation/transfer, and spaced retrieval practice. They're
already installable as-is, which makes them a clean fit for a standalone
SKILL.md listing.

**Engineering skills distilled from CPractice** — the parts that took the
longest to get right and that other people building a judge or an autograder
would otherwise get wrong:

- *Deterministic code grading* — the rule that AI must never decide pass/fail,
  separating learner failure from infrastructure failure, declarative test
  data instead of executable test scripts, sandboxing and limits from
  configuration, and the test cases that keep a grader honest.
- *Exercise authoring* — blueprint-first problem design, declarative hidden
  tests, boundary and edge-case coverage, reference-solution validation,
  mutation checks (a deliberately broken solution must fail), difficulty
  calibration, misconception mapping, and progressive hints.

Both are written to be self-contained and vendor-neutral, so they'd work for
someone building this in a stack that has nothing to do with mine.

I'm going ahead and submitting rather than waiting — the tutor skills as a
set, and the two engineering ones alongside them. If you have two minutes
when it reaches you, two things would be genuinely useful to know: whether
formal bundle pricing is available to a new creator (your site shows bundles
at $39, but the pricing guide I read said it isn't formally supported yet),
and whether there's a category or tag placement you'd point me at for a
deterministic-grading skill, since the closest listings on the marketplace
are all about LLM evaluation rather than code.

No rush on either — I'll take whatever you have.

Best,
Jessie

---

## Listing copy — frontmatter, summaries, prices

The `description` is the field that decides whether the skill ever activates,
so these are written trigger-based per the format spec: what it does first,
then when to load it, with multiple phrasings.

### Tutor skills — bundle + individual

**Bundle: "AI Tutor Companion — code review, debugging, examination, retrieval"**
Price: **$39** (matches the live "Coding Teacher — Bundle" and "Code Explainer
— Bundle" precedent). Individual listings alongside it: **$5–$9 each**.

```yaml
name: code-review
description: Reviews learner code for correctness and security risks while
  teaching the reasoning behind each finding. Use when the user asks to review
  code, check a submission, find bugs, or give feedback on someone's program.
```

```yaml
name: debugging
description: Diagnoses a failure by testing the learner's hypotheses with
  observable evidence instead of guessing. Use when the user asks to debug,
  diagnose a bug, work out why something fails, or is stuck on an error.
```

```yaml
name: examination
description: Tests understanding through prediction, explanation, application
  and transfer, one question at a time. Use when the user asks to quiz me, check
  if I understand something, test my knowledge, or assess a learner.
```

```yaml
name: retrieval
description: Turns learning-log material into short, varied recall practice.
  Use when the user asks to review what we covered, practise for a test, run a
  spaced review, or revise an earlier topic.
```

### Flagships

**deterministic-code-grader** — **$14**. (Sits just under "AI Eval & Test
Suite Quality Gate" at $14, and above the $5 low end, on the argument that it
is a full system design rather than a single check.)

```yaml
name: deterministic-code-grader
description: Designs a reproducible autograder for source-code exercises where
  the model writes problems but never decides pass or fail. Use when the user
  asks to build a code judge, autograder, CI checker, test harness, or
  submission grader, or asks how to run and compare submitted code safely.
```

**exercise-authoring** — **$9**. (Below the $14 judge price: it is authoring
guidance, one step removed from implementation, and the teacher audience is
more price-sensitive than the developer one.)

```yaml
name: exercise-authoring
description: Writes programming exercises reliable enough to grade
  automatically, with declarative hidden tests, reference-solution validation
  and mutation checks. Use when the user asks to write a programming problem,
  create practice exercises or test cases, or design hidden tests for a judge.
```

### Listing summaries (the marketing card)

- **code-review** — Review learner code for risk while teaching the reasoning
  behind findings. Prioritises correctness and security, labels severity,
  distinguishes objective defects from preference, and requires verification
  with evidence.
- **debugging** — Diagnose failures by testing learner hypotheses with
  observable evidence. Separates expected from actual behaviour, asks for a
  hypothesis before suggesting causes, and captures a prevention habit only
  when the lesson is durable.
- **examination** — Test understanding through prediction, explanation,
  application and transfer. One question at a time, answers withheld until
  commitment, smallest misconception corrected first, recognition never
  mistaken for understanding.
- **retrieval** — Revisit learning-log material with short, varied recall
  practice. Prediction, debugging, comparison and transfer over definitions;
  difficulty adjusted to performance; ends with one targeted practice action.
- **deterministic-code-grader** — Design a reproducible autograder for
  source-code exercises. The model writes problems and hints; tests and a
  deterministic evaluator decide pass/fail. Covers the result taxonomy
  (learner failure vs infrastructure failure), declarative test data,
  sandboxing, configurable limits, comparison modes, hidden-test secrecy, and
  the test suite that keeps the grader itself honest.
- **exercise-authoring** — Write programming exercises reliable enough to grade
  automatically. Blueprint first, then statement, declarative hidden tests
  with deliberate edge-case coverage, reference-solution validation, mutation
  checks, difficulty calibration, misconception mapping, and three-level
  progressive hints.
