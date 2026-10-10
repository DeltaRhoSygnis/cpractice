# CPractice — Execution Plan

Derived from the CPractice architecture specification. This is the approved
execution plan and milestone tracker for the MVP.

**Scope decision:** Milestones 1–5 (foundation → grading engine → package
contract → AI generation → learning feedback).
**Build approach:** Strict milestone sequencing — the deterministic checker is
proven before AI generation is added.
**Target environment:** GitHub Codespaces (primary) / Termux (secondary, with
the `noexec` storage constraint documented in the README).

---

## Design decisions (preserved from the specification)

1. The problem-package schema is provider-independent.
2. The grading engine is provider-independent.
3. **AI never decides pass/fail.**
4. Exercises are reusable and stored locally.
5. Tests are declarative data, not arbitrary AI-generated scripts.
6. Hints are progressive and optional.
7. The initial runner targets stdin/stdout C programs.
8. The local app binds to localhost by default.
9. Hosted execution requires a stronger security boundary.
10. Additional AI providers are adapters, not rewrites.

---

## Environment findings (verified)

| Finding | Impact | Resolution |
|---|---|---|
| Android shared storage is `noexec` | Compiled binaries build but cannot execute there | Repo + workspaces live in an exec-capable filesystem |
| Termux `gcc` is clang 21.1.8 | Some flags differ | Fixed flag set: `-std=c11 -O2 -pipe -Wall -Wextra`; avoid `-fsanitize`/`-march=native` |
| `uvicorn[standard]` needs Rust-built `watchfiles` | Fails to build in Termux | Depend on plain `uvicorn` |
| No Docker / no root locally | Strong sandboxing unavailable | Local isolation = dedicated tmpdir + timeouts + output caps; hosted uses containers |
| Python 3.14 on Termux | Some wheels may be unavailable | Codespaces pins Python 3.12 |

---

## Technology stack

| Component | Choice |
|---|---|
| Frontend | Plain HTML + CSS + JavaScript (no framework, no CDN) |
| Backend | Python + FastAPI |
| Validation | Pydantic v2 + JSON Schema |
| C compiler | GCC (clang on Termux) |
| Execution | Python `subprocess` with strict limits |
| Platform tests | pytest (mocked AI provider) |
| Metadata | SQLite |
| Problem packages | JSON + Markdown + C files |
| AI | Provider adapter interface; first impl = Google Gemini |

---

## Milestone plan

### M1 — Local application foundation
- FastAPI app skeleton, `config.py` (pydantic-settings), static file serving.
- `GET /api/health`.
- Minimal `web/` shell (dashboard placeholder).
- **Done when:** app starts and the browser can reach the backend.

### M2 — Deterministic grading engine
- `grading/compiler.py` — fixed-flag compilation, capture diagnostics.
- `grading/runner.py` — subprocess with wall-clock timeout + output cap.
- `grading/comparator.py` — `exact_normalized` and `whitespace_tolerant` modes.
- `grading/evaluator.py` — orchestrates compile → run each test → report.
- Result categories: compilation error, passed, wrong answer, runtime error,
  timeout, output limit exceeded, internal checker error.
- **Done when:** tests cover correct, wrong, compile-fail, runtime-fail,
  timeout, and output-limit paths.

### M3 — Problem package contract
- Pydantic schemas: `schemas/problem.py`, `test_case.py`, `grading.py`.
- Sample manual package `problems/example-problem/`.
- `storage/problem_repository.py` load/validate.
- **Done when:** a manual package loads, validates, and grades with no AI.

### M4 — AI problem generation
- `ai/base.py` provider interface; `ai/google.py` Gemini adapter;
  `ai/rate_limits.py`, `ai/cache.py`; `MockProvider` for tests.
- `generation/prompts.py`, `pipeline.py`, `quality_gate.py`.
- Quality gate: schema → compile reference → run reference vs tests →
  example consistency → flag.
- `POST /api/problems/generate`.
- **Done when:** malformed output is rejected; a validated exercise is saved.

### M5 — Learning feedback
- `feedback/reporter.py` (safe diagnostics, hidden outputs never exposed).
- `feedback/hint_service.py` — 5 progressive levels + explicit solution reveal.
- `POST /api/problems/{id}/hint`, `POST /api/problems/{id}/solution`.
- **Done when:** learner can attempt → inspect → get a hint → retry without a
  new AI conversation.

---

## API surface (initial)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | health |
| POST | `/api/problems/generate` | request a new exercise |
| GET | `/api/problems` | list saved exercises |
| GET | `/api/problems/{id}` | read an exercise |
| POST | `/api/problems/{id}/submit` | submit C source for grading |
| POST | `/api/problems/{id}/hint` | next progressive hint |
| POST | `/api/problems/{id}/solution` | explicit solution reveal |
| GET | `/api/attempts` | recent attempts |
| GET | `/api/progress` | practice summary |

---

## SQLite tables

- `problems` — id, version, topics, difficulty, status, timestamps, package path
- `attempts` — problem id, timestamps, compilation status, passed/total, duration, hint level
- `test_results` — attempt id, test id, result category, safe diagnostics
- `provider_usage` — provider, model, operation, status, usage metadata, timestamp
- `settings` — non-secret preferences

---

## Build order (implementation sequence)

1. `requirements.txt` / `config.py` / `main.py` / `/api/health`
2. `grading/compiler.py` → `runner.py` → `comparator.py` → `evaluator.py` + tests
3. `schemas/` + `problems/example-problem/` + `storage/problem_repository.py`
4. `ai/` (base + mock + google) + `generation/` (pipeline + quality gate)
5. `feedback/` (reporter + hint_service)
6. `web/` wired to the API
7. `storage/database.py` + attempt/provider-usage persistence

---

## Testing strategy

Every layer has platform tests. Wherever AI is involved, use deterministic
**mocked provider responses** — the platform's own tests must not require live
API calls.

Coverage targets: schema validation, malformed AI output, reference compile
failure, correct/incorrect/boundary submissions, compile/runtime/timeout/output
failures, comparison modes, provider rate-limit/timeout/auth errors, cache
hit/miss, persistence, API validation, workspace cleanup, workspace escape
attempts, and hidden-data separation.

---

## Risk register

| Risk | Mitigation |
|---|---|
| AI creates a wrong exercise | Structured output, reference compile, quality gate |
| Tests miss wrong solutions | Boundary cases, mutation-style checks |
| AI quota exhausted | Cache packages, reuse saved exercises, retries |
| AI gives away the answer | Progressive hints, explicit reveal, hidden outputs |
| Submitted C program hangs | Wall-clock timeout + process termination |
| Hosted execution exploited | Containers, no network, unprivileged, disposable FS |
| Overengineering | Build only the current milestone |

---

## Progress tracker

- [ ] M1 — Local application foundation
- [ ] M2 — Deterministic grading engine
- [ ] M3 — Problem package contract
- [ ] M4 — AI problem generation
- [ ] M5 — Learning feedback
