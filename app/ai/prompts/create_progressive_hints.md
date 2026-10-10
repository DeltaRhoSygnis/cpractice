# Stage — Create progressive hints

Write a hint ladder from the blueprint's objective and likely misconceptions.

## Rules

Each hint must be **more specific than the last**. A ladder that restates the
same idea in different words is useless.

1. **Reframe** — name the relevant concept. Do not describe steps.
2. **Reasoning question** — ask what must change, what must remain true, or
   what the first and last case is.
3. **Decomposition** — point at a subproblem or a useful intermediate state.
4. **Algorithmic direction** — describe the strategy. Still no C code.
5. **Pseudocode** — enough structure to translate. Not valid C.
6. **Solution** — the reference implementation, with a short explanation.

## Constraints

* Hints must be **problem-specific**. Generic advice ("use a loop carefully")
  is not a hint.
* Never include a complete working C program at any level below the final one.
* Never reveal a hidden test's input or expected output.
* Level 5/6 (solution) is surfaced only on explicit learner request; write it as
  the reference plus reasoning, not as a copied block of code alone.
* Keep each hint short. One idea per level.

## How many levels

Not every exercise needs all six. Use as many as the objective genuinely
supports, and omit padding levels.
