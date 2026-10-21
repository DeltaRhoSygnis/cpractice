# Result Taxonomy and Report Schema

Reference for the `deterministic-code-grader` skill. Read this when defining
the outcome model, the report structure, or the boundary between learner
failure and infrastructure failure.

## The two families

Every outcome belongs to exactly one family. Never report an infrastructure
problem as a learner problem.

### Learner failure — the submission is at fault

| Category | Meaning | What the learner sees |
|---|---|---|
| `passed` | Output matched the expected output for this test | Pass |
| `wrong_answer` | Program ran to completion, output did not match | Which test failed and what it printed (public tests only) |
| `compilation_error` | Source did not build | The compiler's diagnostics, verbatim |
| `runtime_error` | Program crashed, or exited non-zero | The exit code and the signal, if any |
| `timeout` | Wall-clock limit exceeded | The limit that was applied |
| `output_limit_exceeded` | Program wrote more than the cap | The cap that was applied |

### Infrastructure failure — the grader is at fault

| Category | Meaning | Handling |
|---|---|---|
| `internal_error` | Missing compiler, unwritable workspace, comparator bug, resource exhaustion on the host | Retry once, then surface as a system error. Log separately. Never blame the learner. Never present it as a failed test. |

A `internal_error` on the first test aborts the attempt. Partial results from
an aborted attempt are not a verdict.

## Attempt-level versus test-level

Test-level: `passed`, `wrong_answer`, `runtime_error`, `timeout`,
`output_limit_exceeded`.

Attempt-level: `compilation_error` (the whole submission failed to build, so
no test ran) and `internal_error`.

An attempt's overall verdict is derived, never stored separately:

- Any test fails → the attempt is not a pass, and the reported category is the
  category of the **first** failing test in execution order. Keep the full
  per-test list so the learner can see the pattern.
- All tests pass and compilation succeeded → `passed`.
- Compilation failed → `compilation_error`, and there are no test results.

## Report shape

A structured, machine-readable report. Field names vary by stack; the content
does not.

```
GradingReport
├── category: passed | wrong_answer | compilation_error | runtime_error
│              | timeout | output_limit_exceeded | internal_error
├── compilation:
│   ├── success: bool
│   ├── diagnostics: str        # compiler output, verbatim, may be empty
│   └── duration_ms: int
├── tests: [TestResult]
│   ├── test_id: str
│   ├── test_name: str
│   ├── visibility: public | hidden
│   ├── category: <test-level category>
│   ├── duration_ms: int
│   ├── exit_code: int | null
│   └── detail: str             # safe only — never the hidden expected output
├── passed_count: int
└── total_count: int
```

## The secrecy rule for `detail`

`detail` is what a learner may read. It may contain:

- The compiler's diagnostics, in full. The learner needs the line and column.
- For a **public** test: the input and the output their program produced.
- The applied limit, for `timeout` and `output_limit_exceeded`.
- The exit code, for `runtime_error`.

It must **never** contain:

- The expected output of a hidden test.
- The hidden test's input.
- A path, filename, or identifier that reveals a hidden test's identity.
- A stack trace from the grader itself (that is an `internal_error` detail and
  goes to logs, not to the learner).

## Why the split exists

A grader that reports a missing compiler as "wrong answer" produces three
consequences, all of them bad:

1. The learner is told they got a problem wrong when the machine broke. They
   will change correct code.
2. The support queue fills with tickets that cannot be answered, because there
   is no submission error to point at.
3. The aggregate statistics become meaningless — the pass rate now measures
   the grader's uptime as much as the learner's ability.

Split the categories and you can measure them separately: learner failure rate
is a teaching signal, infrastructure failure rate is an operational signal.
