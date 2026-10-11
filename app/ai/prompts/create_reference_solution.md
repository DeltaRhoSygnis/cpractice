# Stage 5 — Create the reference solution

Produce the reference C implementation for the approved specification.

## Rules

* C11, standard library only, unless the specification explicitly allows more.
* It must compile with `-Wall -Wextra` and produce no warnings that indicate a
  real defect.
* It must read from stdin and write to stdout exactly as specified.
* It must satisfy **every** test, including boundaries and hidden cases.
* It must handle the stated minimum input without undefined behaviour. Never
  read out of bounds or rely on uninitialised values.
* Prefer clarity over cleverness. The reference is also a teaching artefact and
  is shown when the learner explicitly requests the solution.

## Also produce

`solution_explanation`: two or three sentences on *why* the approach is
correct — the invariant it maintains or the boundary it respects. Not a
line-by-line narration.

`solution_outline` (author-only): the reasoning steps, used to validate the
exercise and to author hints. This is not shown to the learner by default.

## Also produce: distribution code (`starter_code`)

The starter is what the learner opens the editor to. It is a first-class
artefact with hard requirements:

* It **must compile** cleanly as C11, so the learner can run the checker
  immediately.
* It **must not pass** the tests on its own: it is missing at least one real
  piece of logic, so completing it is the task. A starter that solves the pset
  is rejected.
* It **must contain at least one `TODO` comment** marking exactly what the
  learner must implement. Mark missing decisions, not formatting.
* It **must not be** the reference solution. Never ship the answer as the
  starter.

## Before returning

Trace your implementation against each planned test by hand. Confirm the
output matches the specification exactly, character for character, including
the trailing newline.
