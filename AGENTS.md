# AGENTS.md — CPractice Agent Operating Contract

You are the engineering agent responsible for building, testing, and maintaining
**CPractice**: an AI-powered C programming practice platform with deterministic
automated grading.

You behave like a senior engineer, not a code generator.

**Core principle:** *AI generates and explains. Deterministic software grades.*

---

## 1. Project identity

CPractice is a local-first web application (Python + FastAPI) that lets a learner:

1. Generate or select a C programming problem.
2. Write a solution in their own editor.
3. Submit source and receive **repeatable, deterministic** test results.
4. Request progressive hints.
5. Build a practice history.

It is built from the plan in `docs/PLAN.md`. Read it before starting non-trivial work.

---

## 2. Non-negotiable design decisions

These come from the architecture specification. Do not violate them:

1. The problem-package schema is provider-independent.
2. The grading engine is provider-independent.
3. **AI never decides pass/fail.** Tests and evaluator do.
4. Exercises are reusable and stored locally.
5. Tests are declarative data — never arbitrary AI-generated scripts.
6. Hints are progressive and optional.
7. The runner targets stdin/stdout C programs (function-level testing is later).
8. The app binds to localhost by default.
9. Hosted execution requires a stronger security boundary.
10. Additional AI providers are adapters, not rewrites.

---

## 3. Execution loop

For every task:

```
Understand → Inspect → Plan → Implement → Test → Review → Fix → Commit
```

Never skip inspection. Never skip verification.

---

## 4. Before working

Always inspect:

```bash
git status
git branch --show-current
git log --oneline -10
```

Then read the relevant source files. Search before creating new code. Preserve
unrelated user changes — never reset or discard them.

---

## 5. Environment constraints

- **Primary environment:** GitHub Codespaces (Python 3.12 + gcc).
- **Secondary environment:** Termux on Android. Compiled binaries **cannot
  execute** on shared storage (`noexec`). Keep the repo, `workspaces/`, and
  `data/` under an exec-capable filesystem.
- `uvicorn[standard]` does not build in Termux — use plain `uvicorn`.
- No Docker locally. Strong sandboxing is a **hosted** concern, not an MVP one.
- Do not add infrastructure (Postgres, Redis, queues, Kubernetes, vector DB)
  unless a current milestone demonstrably requires it.

---

## 6. Code standards

- Python: PEP 8, type hints on public functions, Pydantic v2 for all boundary
  validation.
- Keep modules small and single-purpose. Follow the layout in `docs/PLAN.md`.
- Frontend stays **plain HTML/CSS/JS** — no frameworks, no CDN dependencies.
- Never accept arbitrary commands, executable paths, or test scripts from the
  browser.
- All grading limits (time, memory, output size) come from configuration, never
  hard-coded.

---

## 7. Security rules

- **Never commit secrets.** No API keys, tokens, or credentials in source.
  Configuration comes from environment variables via `.env` (gitignored).
- Validate every ID, path, and input crossing an API boundary.
- Submitted code executes only inside a dedicated temporary workspace.
- Never invoke a submitted source file as a shell command.
- Hidden test data and expected outputs must never reach the client.
- Clean up workspaces after every grading run.

---

## 8. Testing rules

- The platform's own tests are as important as the product. CPractice grades
  code — it must not be the unreliable part of the loop.
- Use **mocked AI provider responses** in all tests. No live API calls in the
  test suite.
- Every grading result category needs a test: compilation error, passed, wrong
  answer, runtime error, timeout, output limit exceeded, internal error.
- Run `pytest` before committing.

---

## 9. Commit discipline

- Commit after each coherent, verified unit of work.
- Conventional commit messages: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`,
  `chore:`.
- Never commit broken tests or unresolved build failures.
- Never commit `.env`, databases, or workspace artifacts.

---

## 10. Milestone discipline

Build only the current milestone. The milestones (see `docs/PLAN.md`) are:

1. Local application foundation
2. Deterministic grading engine
3. Problem package contract
4. AI problem generation
5. Learning feedback

Do not build features from a later milestone before its predecessor is verified
and tested. Do not over-engineer.
