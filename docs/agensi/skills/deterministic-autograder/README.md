# deterministic-autograder

A specification you can hand to an agent when you are building a code grader:
verdict categories and partial credit, test discrimination through mutation,
edge-case coverage, the problem-package contract, and the hint ladder.

**Install:** copy this folder into your agent's skills directory
(`~/.claude/skills/`, `.cursor/rules/`, `.codex/skills/`, or the equivalent for
your agent). It contains no scripts and runs no commands - it is instructions
and reference material only.

## What is inside

| File | What it gives you |
|---|---|
| `SKILL.md` | The router: the invariant, the output format, the five-step procedure. |
| `references/result-taxonomy.md` | The seven verdict categories, the result schema, the partial-credit rule. |
| `references/mutation-operators.md` | Ten C-specific mutation operators and how to read survivors. |
| `references/c-edge-cases.md` | The edge-case checklist for student programs. |
| `references/problem-package-schema.md` | The package layout, manifest fields, test case fields and the quality gate. |
| `references/hint-ladder.md` | Five progressive hint levels and the explicit reveal. |

## The one rule everything else serves

**No model decides a verdict.** Output is compared to expected output by
software. A model may write the statement and draft hints; it may not decide
that a submission is correct. The grading engine is provider-independent, so a
model outage, a bad model, or a cheap model cannot change a grade.

## Who it is for

An instructor building an autograder for a programming course, or a developer
building one for a product. The material is written for C because that is
where the mutation operators and the edge-case checklist are sharpest; the
verdict model, the package contract and the hint ladder apply to any language.

## Requirements

None. No runtime, no packages, no network, no credentials, no file access
beyond the files you ask it to read. Works in any agent that supports the
`SKILL.md` format.

## License

MIT.
