# Edge cases to walk before writing hidden tests

For each student program, walk this checklist before you write a single hidden
test. Each row is a bug that has actually been graded as "correct" because the
suite never asked the right question.

## Reading and formatting

- Does the program read **exactly** the declared number of values? A program
  that stops early and still prints an answer passes a suite that never checks
  the input was consumed.
- Trailing newline present or absent? Decide the comparison mode once
  (exact, or exact-ignoring-one-trailing-newline) and apply it to every test.
- Extra whitespace inside the line? Leading zeros? Fix one canonical output
  format and test against that.
- What if the input has **more** values than declared? Fewer?

## Empty and single-element inputs

- Zero-length array, zero-length string, single element.
- A count of `0` where a division or a modulo appears - division by zero.
- The minimum and maximum representable value for the declared type.

## Boundaries

- `n = 1` and `n = n_max` for every loop.
- A value exactly on the threshold (`<=` versus `<`).
- Negative values, and the sign of zero.

## Accumulation and overflow

- An accumulator that overflows its type. In C this is undefined behaviour,
  so the test either uses a range that cannot overflow or the language
  standard guarantees a wider type.
- Off-by-one in the loop bound: does the last element get processed?

## Types and conversions

- Signed versus unsigned comparison when the value can go negative.
- Implicit truncation from a wider to a narrower type.
- Floating point compared with a tolerance, and when it must be exact.

## Output shape

- One number per line, or one line? Declare it, then test it.
- Trailing spaces. Extra blank lines. Both are wrong if the format says
  otherwise.

## A boundary table that catches most real bugs

| Loop form | Test that catches the off-by-one |
|---|---|
| `for (i = 0; i < n; i++)` | `n = 1` and `n = n_max` |
| `for (i = 1; i <= n; i++)` | `n = 1` and `n = n_max` |
| `while (i < n) { ... i++; }` | a single-element input |
| `for (i = 0; i <= n; i++)` | an input one past the expected range |

## The rule

Write the **expected output by hand**, from the specification, not by running
the reference. If you cannot, you do not yet know what the problem is asking.
