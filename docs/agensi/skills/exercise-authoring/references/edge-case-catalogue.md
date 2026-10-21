# Edge-Case Coverage Catalogue

Reference for the `exercise-authoring` skill. Read this when choosing which
test cases to write, or when auditing an existing test set for gaps.

## The catalogue

Each entry says what to generate and why it earns its place. Apply the
categories that apply to the exercise's shape; record in the exercise metadata
which categories were considered and skipped, and why.

### Nominal
A typical input taken straight from the statement, using values the
constraints explicitly allow. This is the case a learner checks their
understanding against. It must exist, and it must be boring.

### Minimal
The smallest legal input. Empty collection, zero, one element, empty string,
the minimum allowed value. Exists because the empty case is the most common
missing branch — an exercise whose reference solution crashes on it is
undiagnosable for the learner.

### Maximal
The largest legal value, and ideally several large values in different
dimensions at once. Exists because accumulators, counters, and time
complexity break here first.

### Boundary
The value immediately below each threshold, the threshold itself, and the
value immediately above it. Examples of thresholds that must be tested on
both sides:

- A stated upper bound on a value ("at most 1000 items").
- A stated range ("between 1 and 100").
- A capacity or allocation size.
- A length limit on a string or line.
- A sign change (−1, 0, +1).

This is the highest-value category in the catalogue. Off-by-one is the most
common correctness bug in submitted code, and it is invisible unless a test
sits exactly on the edge.

### Degenerate / shape
Inputs whose *shape* stresses the algorithm without exceeding any limit:

- All elements equal.
- Already sorted, ascending.
- Strictly decreasing.
- All duplicates.
- Alternating high/low values.
- A palindrome.
- Exactly two distinct values.

Exercises that assume a particular input shape (sorted, unique) must state
that assumption in the statement — and if the statement does not state it, the
exercise must not assume it. Either way, test the shape you permit.

### Negative and special values

- Negative numbers, where the constraints allow them.
- Zero, in every role it can appear in (as a value, as a count, as a bound).
- Very large magnitudes that overflow a 32-bit intermediate even though the
  final answer fits.
- Empty and whitespace-only lines, where the format permits.
- Unicode or non-ASCII characters, if the statement does not restrict the
  character set.

### Input-format stress
The same logical input expressed in every way the format allows:

- A trailing newline present versus absent.
- Extra spaces between tokens.
- Extra blank lines.
- Leading whitespace on a line.
- Values split across lines, if the format permits it.

If the statement says "read whitespace-separated tokens", then extra whitespace
must be tolerated. If it says "read exactly one integer per line", it must
not. The test set has to match the promise.

### Idempotence and repetition
For exercises with accumulation, running the computation twice over the same
input must give the same answer, and an input repeated in a list must not
corrupt the state. Exists because incremental state is where most subtle
bugs live.

### Multi-case handling
For exercises that process several cases in one run: the all-valid case, the
case with one invalid element, the case where the first element is invalid,
and the case where the last element is invalid. First-position and
last-position failures are handled differently by different implementations.

## Choosing the count

Aim for the smallest set that covers every applicable category and every
stated constraint. Typical good exercises need 8–20 hidden cases; a serious
one with several constraints needs more. A set of 40 cases that all exercise
the same branch is not better than 8 that each exercise a different one.

## The coverage table

Keep this next to the test set. It is what makes coverage auditable rather
than aspirational.

| # | Test id | Category | Constraint it covers | Bug it would catch |
|---|---|---|---|---|
| 1 | basic-1 | nominal | — | total failure |
| 2 | empty | minimal | — | missing empty branch |
| 3 | max-values | maximal | upper bound | accumulator overflow |
| 4 | at-limit | boundary | upper bound | `<` vs `<=` |
| 5 | over-limit-invalid | boundary | upper bound | input validation missing |
| 6 | all-same | degenerate | — | assumptions about ordering |
| 7 | negative | negative | signed range | unsigned assumption |
| 8 | extra-spaces | format | whitespace tolerance | brittle parser |

Update it whenever a test is added or removed. If a stated constraint has no
row, the constraint is untested.

## The mutation cross-check

For every row that claims to catch a bug, write the mutant that bug produces
and confirm the row catches it. A row whose mutant survives is a false claim,
and the row is either missing or too weak.

| Constraint | Mutant | Must fail |
|---|---|---|
| upper bound `n ≤ 1000` | `<` → `<=` | at-limit, over-limit cases |
| at least one element | drop the empty guard | empty case |
| print in order | reverse the output order | the ordering case |
| inclusive range | `>=` → `>` | the low-boundary case |
| unique elements | remove the duplicate check | the all-duplicates case |

This is the only way to know the coverage table is true.
