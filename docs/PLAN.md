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
| No Android wheels for `pydantic-core` / `rpds-py` | pip compiles Rust from source (~20-40 min, once) | Accept once; wheels are then cached |
| Android `RLIMIT_AS` aborts the bionic linker | Program dies at load, intermittently at every value | Skip `RLIMIT_AS` on Android |
| Android `RLIMIT_NPROC` corrupts signal reporting | Crashes report as exit 1 → wrong answer | Skip `RLIMIT_NPROC` on Android; detect crashes via negative exit codes |
| No Docker / no root locally | Strong sandboxing unavailable | Local isolation = dedicated tmpdir + timeouts + output caps; hosted uses containers |
| Python 3.14 on Termux | Some wheels may be unavailable | Codespaces pins Python 3.12 |

### Codespaces constraint: do not add devcontainer features

Verified by experiment against this repository:

| devcontainer config | Result |
|---|---|
| `image` only | Builds correctly: Debian image, Python 3.12, `postCreateCommand` runs, secrets injected |
| `image` + any `ghcr.io` feature (e.g. `sshd`) | Build fails and GitHub silently falls back to a minimal Alpine *recovery container* (`CODESPACES_RECOVERY_CONTAINER=true`) with no Python, no secrets, and no setup |

A recovery container is easy to mistake for a working codespace. Check for it with::

    echo "${CODESPACES_RECOVERY_CONTAINER:-<unset>}"

**Therefore:** the devcontainer intentionally declares **no `features` block**.
Interactive access uses the browser or VS Code terminal rather than `gh codespace
ssh`. Re-adding a feature will silently break secret injection, the Python
toolchain, and `postCreateCommand`.

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
| AI | Provider adapter interface; first impl = **Kenari** (deepseek-v4-1-flash) |

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

- [x] M1 — Local application foundation
- [x] M2 — Deterministic grading engine
- [x] M3 — Problem package contract
- [x] M4 — AI problem generation
- [ ] M5 — Learning feedback

### M1 delivered

| File | Purpose |
|---|---|
| `app/config.py` | pydantic-settings config; localhost-only defaults; secret presence only |
| `app/main.py` | app factory + lifespan (creates runtime dirs) |
| `app/api/health.py` | `GET /api/health` with capability reporting |
| `web/index.html`, `web/styles.css`, `web/app.js` | zero-dependency status shell |
| `tests/test_config.py`, `tests/test_health_api.py` | foundation tests |

**M1 done-when:** the application starts locally and the browser can reach the
backend — covered by `test_static_frontend_is_served` and
`test_health_reports_ok`.

### M2 delivered

| File | Purpose |
|---|---|
| `app/schemas/test_case.py` | declarative `TestCase` contract + comparison modes |
| `app/schemas/grading.py` | `CompilationResult`, `TestResult`, `GradingReport`, result categories |
| `app/grading/compiler.py` | fixed-flag C compilation, truncated diagnostics |
| `app/grading/runner.py` | process-group execution, timeout, output cap, resource limits |
| `app/grading/comparator.py` | `exact_normalized` + `whitespace_tolerant` modes |
| `app/grading/evaluator.py` | orchestration, result classification, safe diagnostics |

**M2 done-when:** automated tests verify correct output, wrong output,
compilation failure, runtime failure, timeout, and output-limit handling —
all covered in `tests/test_evaluator.py`.

#### Platform findings (Android / Termux)

Verified by experiment and encoded in `app/grading/runner.py`:

| Limit | Behaviour | Resolution |
|---|---|---|
| `RLIMIT_AS` | bionic linker aborts at load (`MapShadow CHECK p != MAP_FAILED`); failure is intermittent at *every* value, including large ones | Skipped on Android |
| `RLIMIT_NPROC` | setting it in the child makes signal deaths report as exit code `1` instead of a negative signal | Skipped on Android |
| `RLIMIT_CPU` | reliable | Applied everywhere |
| wall-clock timeout | reliable via process-group kill | Applied everywhere |

Consequence: crash detection must use **negative exit codes (signal death)**,
never a heuristic over positive exit codes. A segfault is a runtime error
regardless of the exit code a test expects.

### M3 delivered

| File | Purpose |
|---|---|
| `app/schemas/problem.py` | `ProblemMetadata`, `Problem`, `Hint`, difficulty/status enums, test-id and hint-level uniqueness |
| `app/storage/problem_repository.py` | loads and validates packages from disk; rejects path traversal |
| `app/services/problem_service.py` | application layer; derives grading config from metadata |
| `app/api/problems.py` | `GET /api/problems`, `GET /api/problems/{id}` with safe views |
| `problems/c-sum-two-integers/` | complete manual package: statement, starter, reference, 6 tests, 5 hints |

**M3 done-when:** a manually authored package can be loaded, validated, and
graded without AI involvement —
`test_example_package_reference_passes_all_tests` and
`test_example_package_starter_does_not_pass` prove both directions.

#### Package layout

```
problems/<problem-id>/
    problem.json          # metadata + tests + hints + solution_explanation
    statement.md          # required
    starter/main.c        # optional
    reference/main.c      # optional until the quality gate runs
    quality_report.json   # written by M4
```

#### Hidden-data rule

The API response models are narrower than the internal schemas. Hidden tests
expose **only `id` and `name`** - never `stdin` or `expected_stdout`. The
reference solution is withheld unless explicitly requested. Verified by
`test_hidden_test_content_is_never_exposed`.

### M4 delivered

| File | Purpose |
|---|---|
| `app/ai/base.py` | provider interface + error taxonomy (auth / invalid / rate-limit / unavailable / malformed) |
| `app/ai/google.py` | Gemini REST adapter; maps HTTP status to the taxonomy, never leaks the key |
| `app/ai/mock.py` | scriptable provider so tests need no live calls |
| `app/ai/rate_limits.py` | bounded retry with exponential backoff; permanent errors never retried |
| `app/ai/cache.py` | content-addressed generation cache (quota defence) |
| `app/generation/prompts.py` | system/user prompts, JSON schema, tolerant JSON parsing |
| `app/generation/quality_gate.py` | structural + behavioural validation with severity findings |
| `app/generation/pipeline.py` | request → parse → gate → save |
| `app/generation/normalize.py` | maps model output variants onto the canonical schema |
| `app/ai/kenari.py` | Kenari gateway adapter (OpenAI-compatible) |
| `app/api/generation.py` | `POST /api/problems/generate` |

#### Live verification (Kenari / deepseek-v4-1-flash)

Real generations through the gateway, all validated by the deterministic gate:

| Topic | Difficulty | Result | Reference |
|---|---|---|---|
| loops | beginner | validated | 8/8 |
| arrays | intermediate | validated | 9/9 |
| recursion | advanced | validated | 13/13 |
| strings | beginner | validated | 5/5 |
| sorting | intermediate | validated | 10/10 |

#### Why normalisation exists

Kenari documents that `response_format` is **forwarded, not enforced** — the
gateway does not verify the result, so a reply may be valid JSON, invalid
JSON, or fenced JSON, using different field names. Observed in real responses:

| Model returned | Normalised to |
|---|---|
| `description` | `statement_md` |
| `input_format` / `output_format` / `constraints` | appended to the statement |
| `public_tests` + `hidden_tests` | one `tests` list with `visibility` |
| `input` / `expected_output` | `stdin` / `expected_stdout` |
| `topic: "loops"` | `topics: ["loops"]` |
| hints as bare strings | `{level, text}` objects, renumbered 1..n |
| stray scalar inside `tests` | skipped |
| `schema_version: 1` | `"1"` |

Normalisation performs only lossless mapping: it never invents test data, and a
payload with no usable tests is still rejected. Everything is re-validated
against the Pydantic schemas afterwards, so the gate - not the model - still
decides validity.

**M4 done-when:** a generated exercise is rejected if malformed or
inconsistent, and a validated exercise is saved for reuse.

#### Quality gate behaviour

The gate never awards a numeric "quality score". It reports findings with a
severity and validates only when no ERROR-level finding exists. Checks:

- structure: statement present, reference present, tests present, hidden-test
  minimum, duplicate ids, duplicate input/expected pairs, hint depth
- limits: unreasonable time/memory limits are errors
- behaviour: **compiles the reference and runs it against every test**; a
  reference that fails its own tests rejects the problem

This is the enforcement point for design decision #3 - *AI never decides
pass/fail*.

#### Provider failure handling

| Failure | Action |
|---|---|
| `AuthError` | fail immediately (never retried) |
| `InvalidRequestError` | fail immediately (never retried) |
| `RateLimitError` | bounded retry, honouring `Retry-After` |
| `ProviderUnavailableError` | bounded retry with exponential backoff |
| `MalformedResponseError` | bounded retry (model formatting is transient) |

#### Offline-first behaviour

The application starts and serves everything without AI credentials;
generation returns `503` with a clear message. Saved problems remain fully
practisable, satisfying the M6 goal early (design decision #4).
