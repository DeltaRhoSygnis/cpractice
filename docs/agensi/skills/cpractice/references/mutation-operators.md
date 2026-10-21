# Proving your hidden tests are not vacuous

A reference solution passing its own tests proves **consistency**, not
**correctness**. A wrong reference with matching wrong tests passes cleanly.
Mutation testing supplies the missing instrument.

## The method

1. Derive deliberately-wrong variants ("mutants") of the reference solution.
2. Run each mutant against the problem's test suite.
3. A mutant that **fails** a test is **killed** - the tests detect that bug.
   A mutant that **passes every test** **survived** - the tests are too weak to
   notice an obviously wrong program.

A high survival rate means the suite does not discriminate. Fix the suite;
never quietly accept the survivors.

## C-specific operators worth having

| Operator | Mutation | The beginner bug it represents |
|---|---|---|
| `add-to-sub` | `+` becomes `-` | Sign error in an accumulation |
| `sub-to-add` | `-` becomes `+` | Sign error in a subtraction |
| `mul-to-add` | `*` becomes `+` | Multiplication written as addition |
| `lt-to-le` | `<=` becomes `<` | Off-by-one at the boundary |
| `le-to-lt` | `<` becomes `<=` | Off-by-one at the boundary |
| `gt-to-ge` | `>=` becomes `>` | Boundary, wrong side |
| `eq-to-ne` | `==` becomes `!=` | Equality inverted |
| `inc-to-dec` | `++` becomes `--` | Loop runs the wrong way |
| `drop-newline` | trailing `\n` removed | Output formatting differs |
| `drop-increment` | loop increment deleted | Infinite loop or early exit |

## Rules that keep the signal honest

- **Mutate only the first occurrence** of each pattern, so each mutant is
  small and still compiles most of the time.
- **Do not remove `return 0;` from `main`.** Since C99 an implicit
  `return 0;` is added, so that mutant is semantically equivalent to the
  reference and would survive every time - pure noise that would wrongly flag
  correct tests as weak.
- **Treat `drop-newline` as an expected survivor** when the comparison mode
  ignores a single trailing newline. Reporting it would flag every problem
  that legitimately uses that mode.
- **Collapse duplicate mutants.** Two operators that produce the same source
  are one mutant, not two.
- **Report the operator, the mutant and the reason** - never a number without
  evidence.

## Reading the result

| Surviving mutants | What it means | What to do |
|---|---|---|
| 0 | The suite discriminates. | Ship it. |
| 1-2 | Usually a formatting-only survivor. | Confirm it is expected; add a test if it is not. |
| 3+ on arithmetic problems | The suite is too weak. | Add the missing boundary and interior cases. |

## Worked example

Reference solution for "sum two integers":

```c
#include <stdio.h>
int main(void) {
    int a, b;
    if (scanf("%d %d", &a, &b) != 2) return 1;
    printf("%d\n", a + b);
    return 0;
}
```

| Mutant | Killed by | What it proves |
|---|---|---|
| `a + b` -> `a - b` | the negative-input test | The suite checks the sign of the answer |
| `a + b` -> `a * b` | the two-positive test | The suite checks the operation |
| trailing `\n` removed | the exact-comparison test | The output format is pinned |

If the negative-input test is missing, the `add-to-sub` mutant survives - and
the grader will happily accept `a - b` for every student who forgets to
negate. That is the entire failure mode this instrument exists to catch.

## The rule that matters most

Survivors are a **finding**, not a score. Report the operator, the mutant and
the reason. Never present a mutation score as a quality number to be
optimised - the goal is a suite that catches the mistakes students actually
make.
