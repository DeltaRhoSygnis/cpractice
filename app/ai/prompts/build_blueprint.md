# Stage 1 — Build the exercise blueprint

You are designing the *intent* of an exercise before writing it.

## Why this stage exists

"loops" is not an objective. An objective is an observable reasoning action the
learner must perform, such as: *"derive a loop's initial value, condition, and
update so that every required item is processed exactly once, with no
out-of-range access."*

A blueprint prevents the generator from producing a generic textbook exercise.

## Rules

1. `primary_objective` must be a **specific, observable reasoning action**, not
   a topic label. If you cannot state what the learner must *do*, sharpen it.
2. `prerequisites` must be concepts the learner is assumed to already know.
   Do not require unstated concepts.
3. `target_reasoning_moves` are the concrete decisions the learner must make.
   Aim for one to three; more than that overloads a single exercise.
4. `likely_misconceptions` must be **specific wrong approaches** the tests can
   distinguish, such as "off-by-one: processes one element too many" — not
   vague labels like "carelessness".

   **Prefix each with a stable ID in `MIS-` form**, e.g.
   `"MIS-INIT-ZERO: initialising the maximum to 0 fails for all-negative input"`.
   The test-design stage references these IDs, so they must be stable and unique.

5. `target_reasoning_moves` should likewise be referenceable. Give each a short
   stable `REQ-` id when useful, e.g. `"REQ-SINGLE-PASS: process the array in one
   pass"`. Tests will cite these.

6. `difficulty_profile` justifies the level by reasoning demand, not by input
   size or code length.

7. `transfer_goal` names a materially different task the learner should find
   easier afterwards. It must not be a superficial renaming.

8. Choose the `exercise_role` that matches what this exercise is *for*:
   `diagnostic_warmup`, `core_reasoning`, `transfer`, `challenge`,
   `debugging`, or `reflection`.

## Problem sets

When the request is for a **problem set**, design the blueprint around a
realistic scenario, not an abstract task:

9. `primary_objective` must state the reasoning the *new* concept demands and
   how it is combined with concepts the learner already knows. A problem set
   connects known and unknown; it never drills the new concept in isolation.
10. `prerequisites` are exactly the concepts the learner already knows. Require
    nothing outside them plus the single new concept.
11. `likely_misconceptions` must name the wrong approaches a learner is most
    likely to take when *combining* the concepts (for example: "reads the whole
    line before tracking the running state, so the first item is mishandled").
    Keep the `MIS-...` ids.
12. `transfer_goal` must name a materially different real-world task that uses
    the same combination.

## Output

Return JSON matching the blueprint schema. Include `acceptance_criteria`: the
conditions that must hold for this exercise to be publishable.
