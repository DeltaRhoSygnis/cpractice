# Stage 2 — Write the specification

Write the learner-facing problem statement from the approved blueprint.

## Required sections

1. **Title** — concrete, not cute.
2. **Task** — the exact behaviour required.
3. **Input format** — structure and valid domain.
4. **Output format** — exactly what is printed.
5. **Constraints** — value ranges and assumptions the solution may rely on.
6. **Examples** — at least two input/output pairs that are correct.
7. **Restrictions** — libraries or language features that are disallowed.

## Rules

* Every requirement must be **observable**: a test could check it.
* State edge behaviour explicitly. If input of size zero is possible, say what
  must happen. If it is impossible, say so.
* Do not add story text merely to make a simple exercise look sophisticated.
  The reasoning justifies the difficulty; the prose does not.
* Do not mention the intended algorithm. That belongs in author-only material.
* Examples must be consistent with the specification. A contradictory example
  is a hard failure.

## Output

`statement_md` in Markdown, plus the input/output contract fields.
