# deterministic-code-grader

Design and build a **reproducible autograder** for source-code exercises — a
code judge, a CI-based checker, a submission grader, or a practice platform's
evaluation harness.

The core rule: **the model writes problems and hints; deterministic software
decides pass or fail.** A verdict that a model produced is not reproducible,
cannot be defended to a learner, and cannot be tested.

## What is in this package

```
deterministic-code-grader/
├── SKILL.md                          # the instructions
├── README.md                         # what it does, how to use it
└── references/
    └── result-taxonomy.md            # outcome model + report schema
```

Read `references/result-taxonomy.md` when you need the exact category list,
the report fields, or the rule for what a learner's diagnostic message may
contain.

## Who it is for

- Someone building a judge, an autograder, or a CI checker for programming
  exercises.
- Someone whose current grader lets a language model decide whether a
  submission is correct.
- Someone reviewing a grader for correctness, safety, and reproducibility.

## Works with

Any language and any agent. The skill is written as engineering guidance, not
as code to run: the agent produces a design, a data model, a sequence, a risk
list, and a test plan that you then implement in your own stack. Nothing in
this package executes anything, needs credentials, or touches the network.

## Suggested entry points

- "Help me build a code autograder for my exercise platform."
- "How should I structure the results of a submitted solution?"
- "Review my grader — can a student game it or break it?"
- "Where should the pass/fail decision live if I use an LLM to write problems?"
