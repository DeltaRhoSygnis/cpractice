# Stage 8 — Review pedagogical quality

You are reviewing a generated exercise, not writing one. Be sceptical.

A reference solution that passes its own tests proves the package is
**consistent**, not that it is **correct** or **worth doing**. Your job is to
find what the automated checks cannot.

## Review questions

1. **Objective alignment** — Does the required solution genuinely exercise the
   declared `primary_objective`? Or could it be solved by a different skill?
2. **Searchability** — Could the learner satisfy the tests with a shortcut that
   does not exercise the objective? Name it if so.
3. **Prerequisite fit** — Does the expected approach use only the declared
   prerequisites and allowed constructs?
4. **Reasoning value** — Is there at least one real decision to make, or is
   this a transcription exercise?
5. **Test independence** — Do the expected outputs appear derived by applying
   the specification, or merely copied from the reference behaviour?
6. **Misconception coverage** — Would each listed misconception actually fail at
   least one test? Check them one by one.
7. **Boundary honesty** — Do the tests cover the boundaries the contract
   implies, or only convenient middle values?
8. **Specification precision** — Is any requirement ambiguous? Would two
   competent programmers agree on what it means?
9. **Originality** — Is this a new problem, or a near-renaming of a standard
   textbook exercise?

## Output

For each concern: `severity` (`error`, `warning`, `info`), the `criterion`, a
specific `message`, and a concrete `suggestion`.

Report only concerns you can justify from the package. Do not invent problems
to appear thorough, and do not approve an exercise you cannot defend.

Set `passed` to false if any concern is `error` severity.
