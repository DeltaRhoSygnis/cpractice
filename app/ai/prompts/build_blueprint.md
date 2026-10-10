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
5. `difficulty_profile` justifies the level by reasoning demand, not by input
   size or code length.
6. `transfer_goal` names a materially different task the learner should find
   easier afterwards. It must not be a superficial renaming.
7. Choose the `exercise_role` that matches what this exercise is *for*:
   `diagnostic_warmup`, `core_reasoning`, `transfer`, `challenge`,
   `debugging`, or `reflection`.

## Output

Return JSON matching the blueprint schema. Include `acceptance_criteria`: the
conditions that must hold for this exercise to be publishable.
