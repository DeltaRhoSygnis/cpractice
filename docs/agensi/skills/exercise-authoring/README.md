# exercise-authoring

Write **programming exercises that are reliable enough to grade automatically** —
problems for a judge, a course, a practice platform, or a tutoring assistant.

The premise: an exercise's quality is the quality of its tests. A problem with
vague tests produces learners who fail for reasons they cannot see. A problem
with no hidden tests produces learners who pass by pattern-matching the public
example. A model can draft the wording; only a deterministic validation pass
decides whether the exercise ships.

## What is in this package

```
exercise-authoring/
├── SKILL.md                      # the instructions
├── README.md                     # what it does, how to use it
└── references/
    └── edge-case-catalogue.md    # which test cases to write, and why
```

Read `references/edge-case-catalogue.md` when choosing test cases or auditing
an existing test set for gaps. It contains the category catalogue, a coverage
table format, and a mutation cross-check.

## Who it is for

- Teachers and course authors writing practice problems.
- Anyone building a practice platform, an autograder, or a tutoring assistant
  that needs exercises to grade against.
- Anyone whose current problem set has known-bad tests: exercises that
  reference solutions fail, or where every submission passes.

## Works with

Any language and any agent. The skill produces an exercise package — a
statement, metadata, a reference solution, a test set, a misconception map, and
a hint ladder — that you then validate with your own tooling. Nothing here
executes code, needs credentials, or touches the network.

## Suggested entry points

- "Write a programming problem about recursion with hidden tests."
- "Here are my test cases — what am I missing?"
- "Why do students pass this exercise when they clearly don't understand it?"
- "How do I write exercises that a judge can grade fairly?"
