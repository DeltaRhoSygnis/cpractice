# Verdict taxonomy and result schema

A grader must be able to say *why* a submission failed, and must never let a
language model decide the verdict. This is the outcome model.

## The seven outcome categories

| Category | Meaning | Learner-facing action |
|---|---|---|
| `passed` | The output matched the expected output for this test. | Continue. |
| `wrong_answer` | The program ran and produced a different answer. | Fix the logic. |
| `runtime_error` | The program crashed (signal, abort, or a non-zero exit that is not a verdict). | Fix the crash. |
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
- A compile failure is attempt-level and short-circuits the run: no test is
  executed, and the verdict is `compilation_error`.
- Any test `timeout`, `runtime_error` or `output_limit_exceeded` -> the attempt
  verdict is the *first* such category in the order above. Report which test
  produced it.
- Otherwise -> `wrong_answer`.
- An `internal_error` anywhere -> the attempt is `internal_error`, and it is
  never counted against the learner.

## Partial credit

Partial credit is computed from the per-test counts, never from a single
overall boolean:

```
score = passed_tests / total_tests
```

Two constraints on that number:

- **Hidden tests and public tests are counted separately** if the course
  weights them. A student must be able to see which public test failed.
- **An attempt that ends in `internal_error` or `compilation_error` has no
  score.** A grader failure is not a low score; it is a missing score.

## What a model may and may not do

**May:** write the statement, draft hints, propose candidate test inputs,
explain a verdict.

**May not:** decide `passed` or `wrong_answer`, author an expected output,
change a category, or score a submission.

If a model is down, wrong, or cheap, the verdict does not change. This is the
property that makes the grader worth trusting, and it is why the outcome model
belongs to software and not to a prompt.
