# Stage 4 — Design tests from requirements

Design the test suite from the **specification and blueprint**, not by running
a reference implementation and recording whatever it prints.

## The independence rule

Expected outputs must come from applying the specification by hand, not from
trusting one implementation. If you derive expected values from the same
reasoning as the reference solution, an error in that reasoning produces a test
suite that agrees with a wrong answer.

For each test, work out the answer from the contract before considering code.

## Required coverage

Include each category that applies:

* Public examples — simple, they illustrate the contract.
* Ordinary valid input.
* **Minimum** valid input (size 0 or 1 if permitted by the contract).
* **Maximum / near-maximum** input within the stated constraints.
* **Boundary transitions** — the first and final valid element, the value at a
  comparison boundary.
* **Misconception cases** — inputs that a specific wrong approach gets wrong.

## Mapping

Every test must carry:

* `requirement_ids`: which stated requirement it checks, e.g.
  `["REQ-BOUNDARY-02"]`.
* `misconception_ids`: which likely misconception it exposes, e.g.
  `["MIS-OFF-BY-ONE-01"]`.

A test that maps to nothing is either redundant or testing undocumented
behaviour. Remove it.

## Visibility

* Public tests: few and illustrative. They must not disclose the whole suite.
* Hidden tests: at least two, and they must include genuine boundary cases —
  not repeats of the public ones with different numbers.

## Do not

* Do not make a test stricter than the written specification.
* Do not test behaviour the specification never describes.
* Do not add several tests that check exactly the same thing.
* Do not reveal hidden expected outputs in the statement or hints.
