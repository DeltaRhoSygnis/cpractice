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
   reference. If the two disagree, the specification is wrong - fix it, do not
   regenerate the expectation from the reference.
3. **Limits come from configuration.** A package may narrow them; it may not
   widen them beyond the configured maximum.
4. **Identifiers are validated before they touch the filesystem.** A package id
   becomes a directory name and a compiler argument.
5. **The learner never sees hidden test data.** The runner receives it; the
   client does not.
6. **The starter must fail.** A distribution file that already passes the
   hidden tests gives the answer away and makes the problem meaningless.

## Concept legality

A problem set is legal only when every concept it requires is one the learner
is declared to know, plus exactly one concept that is new:

```
required_concepts(package)  ⊆  known_concepts ∪ {new_concept}
```

Check this deterministically against the learner's checklist, not by asking a
model to judge it. A package that assumes an undeclared concept is a bug in
the curriculum, not a question of style.

## The quality gate

A package is validated before it is ever shown to a learner. The gate is
evidence-producing, not score-producing:

| Check | What it proves |
|---|---|
| Structure | The manifest is complete and the files are present |
| Reference compilation | The reference solution builds under the configured flags |
| Reference execution | The reference passes every test it ships with |
| Test discrimination | The tests kill the wrong-but-plausible mutants |
| Concept legality | The package assumes nothing the learner has not declared |
| Distribution weakness | The starter does not already pass the hidden tests |

Every finding carries a severity and a reason. **Never award a numeric
"quality score"** - the specification is the source of truth, and the gate
reports evidence against it.
