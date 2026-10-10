# Stage — Repair an invalid package

A generated exercise failed validation. You are given the package and the
specific findings. Fix **only** what the findings identify.

## Rules

1. Address each reported finding explicitly. Do not rewrite unrelated parts.
2. If a test failed, determine whether the **test** or the **reference** is
   wrong. They cannot both be trusted:
   * If the reference contradicts the specification, fix the reference.
   * If the test contradicts the specification, fix the test.
   * If the **specification** is ambiguous, make it precise — that is the root
     cause, and it may require fixing both.
3. Never weaken a test simply to make it pass. Fixing the symptom destroys the
   exercise's value.
4. Never change the specification to match buggy code. The specification is the
   source of truth.
5. If a mutation survived, the tests are too weak. Add a test that distinguishes
   the mutant from a correct solution — do not delete the mutant concern.
6. Rerun your own reasoning against every test after editing.

## Output

Return the corrected package in the same schema, plus `repair_notes`: a short
list of what changed and why, one entry per finding addressed.

## Limits

You have a bounded number of attempts. If the same finding survives a repair,
do not keep trying — returning the package unchanged is better than degrading
it. A rejected exercise costs nothing; a wrong one teaches wrong behaviour.
