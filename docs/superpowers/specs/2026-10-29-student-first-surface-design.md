# CPractice — student-first product surface

Date: 2026-10-29
Status: proposed (awaiting owner approval)

## Intent and why

CPractice is currently a powerful engine with a developer front door: Python
3.12 + gcc + a clone + `pip install -r requirements.txt` + `./start.sh`, and a
393-line README that leads with agents, MCP and the HTTP API. Anyone learning C
— a student, a self-taught developer, a teacher preparing material for their own
use — meets the plumbing before the practice.

The goal is to make CPractice feel like **one small product**:

1. one installation command,
2. one command to start it,
3. one browser page to practise and manage everything,
4. a README that explains that in the first screen.

The audience is individual learners and individual teachers, each on their own
machine. This is explicitly **not** a classroom/multi-user product.

The engine does not change. AI still never decides pass/fail. Grading stays
deterministic. Power features stay, behind an advanced door.

## Goals

- A first-time user can go from nothing to a graded C submission with one
  install command and one run command.
- `cpractice doctor` can answer "why doesn't this work on my machine?" with an
  actionable, OS-specific fix, including the C compiler.
- The browser is the only interface a learner needs: dashboard, problems,
  workspace, progress. Generation, import, MCP and API are reachable but not
  part of the default surface.
- README becomes a short, presentable product page (~120-150 lines) with the
  student path first and a pointer to advanced material.
- The same repo still supports the current developer workflow and the hermetic
  test suite.

## Non-goals

- Multi-user accounts, rosters, class mode, teacher dashboards, auth.
- Public or hosted deployment (still blocked by `SECURITY.md` until the runner
  has a real sandbox).
- Native Windows execution of submitted C. The runner imports the Unix-only
  `resource` module; Windows users are pointed at WSL2. A platform abstraction
  is a later project.
- Single self-contained binary (PyInstaller/Nuitka). Considered and rejected
  for this cut; revisit only if a no-Python install becomes a hard requirement.
- New grading, generation, hint, concept-ladder or MCP features.
- Removing MCP, the HTTP API, batch generation or import.

## Anti-goals

- An "install once" story that silently requires a compiler the user does not
  have and cannot discover how to get.
- A README that is prettier but still leads with MCP configuration.
- Hiding functionality by deleting it, or by making it unreachable.
- A new abstraction layer over the grading engine.

## Constraints

- `AGENTS.md` decisions are binding: localhost default, provider-independent
  schemas/engine, AI never grades, declarative tests, plain HTML/CSS/JS, no new
  infrastructure, all limits from configuration.
- `SECURITY.md`: no auth, no sandbox, single trusted user; never bind `0.0.0.0`
  by default; no secrets in the repo.
- Python is the only runtime; `pipx`/`uv` are acceptable install mechanisms.
  Termux must keep working; `uvicorn[standard]` stays out.
- Grading behaviour and hidden test data must not change.

## Approaches considered

### 1. One command, browser is the product — **chosen**

`pipx install "cpractice @ git+https://github.com/DeltaRhoSygnis/cpractice.git"`
(or the `uv tool` equivalent) installs a single `cpractice` command.
`cpractice start` launches the app and opens the page; `cpractice doctor`
diagnoses Python/gcc/data/port and prints the exact fix; `cpractice problems`
lists the shelf. The browser remains the only interface. Advanced features move
behind an Advanced section in the UI and `docs/ADVANCED.md`.

Trade-off: Python and a C compiler are still prerequisites. The installer is one
command; `doctor` turns the compiler into a guided step rather than a riddle.
Fits the existing architecture, touches no grading code, and is testable.

### 2. One self-contained binary

PyInstaller/Nuitka, one download per OS, no Python. The truest "install
nothing" story, but the grader still needs gcc, so it adds three build pipelines
and platform bugs without removing the compiler. Rejected for this cut.

### 3. README and UI cleanup only

Rewrite the README and simplify navigation, keep
`pip install -r requirements.txt` + `./start.sh`. Cheapest, but the install
stays a developer ritual, so it does not meet the ask. Rejected.

## The design

### 1. `cpractice` command

New module `app/cli.py`, declared in `pyproject.toml`:

```toml
[project.scripts]
cpractice = "app.cli:main"
cpractice-mcp = "app.mcp.server:main"   # unchanged
```

Commands (deliberately small):

| Command | Behaviour |
|---|---|
| `cpractice start` | Ensure home/dirs/seed, run the server in-process, wait for `/api/health`, open the browser unless `--no-browser`. Flags: `--host`, `--port`, `--no-browser`, `--allow-lan`. If CPractice already answers on the target port it opens that instance and exits 0 (matching `start.sh`); if another service holds the port it fails with a clear message. Ctrl+C stops cleanly. |
| `cpractice doctor` | Check Python, the **real** grading path (compile **and run** through `compile_source`/`run_binary`, honouring `CC_COMPILER`/`CC_STANDARD`, in an exec-capable temp dir), home dir writability and exec capability, port availability, and AI status (informational only). Detects native Windows and Termux. Exit 0 when usable, 1 otherwise. Every failure prints one exact remediation command for the detected platform. |
| `cpractice problems` | Print id, title and difficulty of the locally available packages. Read-only. |
| `cpractice open` | Open the running server in a browser, using `state.json` if the configured port does not answer; error clearly if nothing is running. |
| `cpractice version` | Print version and resolved home. |

Configuration precedence for `start`: CLI flags > `CPRACTICE_HOST`/`CPRACTICE_PORT`
> legacy `HOST`/`PORT` from `.env` > defaults (`127.0.0.1:8000`). A
non-loopback bind is refused unless `--allow-lan` is passed; with it, the same
LAN hints as `start.sh` are printed. `doctor` explains both behaviours.

Native Windows: the runner imports the Unix-only `resource` module at module
scope, so `import app.main` currently fails there. The CLI import graph must be
lazy enough that `cpractice doctor` runs on Windows, detects it, prints the WSL2
remediation and exits 1 rather than raising a traceback. `cpractice start` on
native Windows does the same. This is a small platform gate, not a Windows
runner.

MCP stays an optional extra (the pinned `mcp==1.30.0` conflicts with the core
pin set). The `cpractice-mcp` console script remains, but its entry point
catches a missing SDK and prints the exact `pipx install "cpractice[mcp] @ …"`
line instead of a `ModuleNotFoundError` traceback. The default install never
pulls the SDK.

`start` reuses `create_app(settings)` rather than shelling out to `uvicorn`, so
it is one process and the same code path as tests. It sets
`Settings.model_config["env_file"]` based on the resolved home.

Browser opening: `webbrowser.open` normally; on Termux fall back to
`termux-open-url`; `--no-browser` for servers/CI.

### 2. One home directory

A single user-owned home makes installed mode predictable:

- `CPRACTICE_HOME` when set.
- Otherwise, when running from a source checkout (`pyproject.toml` and
  `app/web/` are next to `app/`), keep the current repo-relative behaviour so
  existing tests, `start.sh` and developer muscle memory are unchanged.
- Otherwise `~/.cpractice/` containing `problems/`, `workspaces/`, `data/`,
  `logs/`, `state.json` (last host/port for `cpractice open`) and
  `env.example` (a fully commented template). No `.env` is written on first
  run; a truthy placeholder key must never make the app claim AI is available.

Both modes resolve through one helper in `app/config.py`, so the rest of the
application keeps using `settings.problems_path` etc.

Seeding runs at application startup (not only from the CLI), so an installed
user who runs `uvicorn app.main:app` sees the same shelf. A `problems/.seeded`
marker records package ids that have ever been seeded: an existing package is
never overwritten, and a package the user deliberately deleted is not
resurrected on the next start. New seed packages shipped in a later release are
copied once. The seed source is packaged with the app, so an installed wheel
works offline.

Known placeholder values in `.env.example` (`your-kenari-key-here`, empty
strings) are treated as *unset* by `any_ai_key_configured`, so copying the
template cannot flip the app into a broken "AI on" state.

### 3. Packaging that actually runs

Today the wheel includes prompt templates but not the web assets, and the two
example problems live outside the package. An installed `cpractice start` would
serve nothing. The design fixes that:

- Move `web/` to `app/web/`; `Settings.web_dir` points at the packaged
  directory. Update `tests/test_web_ui.py` accordingly.
- Move the two tracked fixtures to `app/seed_problems/`; `problems/` becomes a
  runtime directory (gitignored with a `.gitkeep`). Update tests that used
  `REPO_PROBLEMS` to use the seed directory.
- Extend `[tool.setuptools.package-data]` to include `web/*` and
  `seed_problems/**/*` (JSON, Markdown, C, expected-output fixtures).
- `problems/` at the repo root remains the default runtime directory in
  checkout mode, so developers still see seeded packages after first start.

Verification will include installing the built wheel into a clean venv and
running `cpractice --help`, `cpractice doctor`, and `cpractice start` against a
temporary home.

### 4. Install story

- Primary, documented: `pipx install "cpractice @ git+https://github.com/DeltaRhoSygnis/cpractice.git"`
  (and the `uv tool install` equivalent). The repository is confirmed public
  (HTTP 200 on 2026-10-29), so the URL works without credentials.
- `scripts/install.sh` is a **guided checker**, not a remote pipe: it detects
  `uv`/`pipx` and a C compiler, prints the exact next command, and only runs the
  install when `--yes` is passed. No `curl | sh` execution of remote code.
- `cpractice doctor` is the post-install repair loop.
- Windows: documented as WSL2 (recommended) with a short native-MSYS2 note and
  an explicit statement that native Windows grading is not supported yet; the
  CLI itself still explains this instead of crashing.
- Termux/Android: `pipx` is the primary path when available; the existing
  `git clone` + `pip install -r requirements.txt` + `./start.sh` flow stays
  documented as the source fallback, and `doctor` detects Termux. `start.sh` is
  a developer convenience from here on, not the headline install.
- PyPI publication is out of scope for this cut; the git URL is the install
  source. A tagged release can replace it later with no user-facing change.

### 5. Browser UI

Keep the three primary destinations: Dashboard, Problems, Progress.

- The dashboard keeps "continue practising" and the problem list.
- The generation form moves into a collapsed **Advanced** disclosure (same
  functionality, not removed). Import keeps its existing entry point inside
  that disclosure.
- A small status strip shows: grading engine ready / compiler missing, AI on or
  offline, and where the data lives. `/api/health` is extended from a
  `shutil.which` check to a cached compile-and-run probe (60 s in-process
  cache), so a Termux `noexec` mount cannot show green while every submission
  returns `internal_error`; `doctor` runs the same probe uncached. The resolved
  home comes from a small read-only endpoint or embedded config.
- No new framework, no CDN, no build step. Existing accessibility patterns
  (skip link, focus management, aria-live route announcer) are preserved.

### 6. README and docs

README structure, in order:

1. Logo, one sentence, badges.
2. **What it is** — deterministic C practice; AI helps, software grades.
3. **Install** — two commands.
4. **Your first problem** — the 60-second loop, with a screenshot.
5. **Who it is for** — learners, self-taught developers, teachers working alone.
6. **Why the grading can be trusted** — the deterministic contract, short.
7. **Managing your practice** — the three pages, `cpractice doctor`, data home.
8. **AI is optional** — offline grading works; key only for generation/live
   hints.
9. **Advanced** — link to `docs/ADVANCED.md`.
10. **Development** — link to `CONTRIBUTING.md`; tests and layout.

`docs/ADVANCED.md` absorbs the material currently dominating the README: MCP
client configuration, HTTP API table, import/batch/generation details, provider
configuration, LAN sharing, and the full environment-variable table.

`docs/PLAN.md`, `SECURITY.md`, `CONTRIBUTING.md` remain authoritative and are
linked, not duplicated.

### 7. Tests and verification

- CLI unit tests: argument parsing, `doctor` with a fake compiler that fails to
  compile/run, home resolution in checkout vs installed mode, seed idempotency
  and no-overwrite, `start` opening an already-running CPractice vs failing when
  another service holds the port.
- Packaging test: build the wheel and assert `app/web/index.html` and the seed
  packages are inside. Marked `slow` or run in CI as a separate step if it
  costs too much for the default suite.
- Web UI tests: Advanced disclosure exists, core nav unchanged, no external
  resources (existing test extended).
- README checks are by review, not automation.
- Manual verification: fresh venv + wheel install; `cpractice doctor` on a
  machine without gcc to see the remediation text; `cpractice start` health
  check; Termux smoke test.

## What is decided here vs left to the builder

Decided with the owner:

- Audience is individual learners and individual teachers; no class mode.
- One install command, browser as the single interface.
- Power features stay behind an advanced door.
- Chosen approach: CLI wrapper + packaging fix + README rewrite, not a binary.

Decided by the builder after a fresh-review pass (owner may veto):

- Command set `start` / `doctor` / `problems` / `open` / `version`.
- Home-directory resolution and checkout detection.
- Moving `web/` and example packages into the package for a runnable wheel.
- Windows supported via WSL2 only in this cut, with a lazy import graph so the
  CLI explains that instead of crashing.
- `cpractice-mcp` keeps its entry point but reports the missing optional SDK
  cleanly; MCP is never part of the default install.
- `start` precedence is flags > `CPRACTICE_HOST/PORT` > `HOST/PORT` > defaults,
  and a non-loopback bind requires `--allow-lan`.
- `start` on an already-running CPractice opens it and exits 0; a port held by
  something else fails clearly. `open` reads `state.json` when the default port
  does not answer.
- Seeding happens at app startup behind a `.seeded` marker (no resurrection of
  deleted packages, no overwrite of edited ones).
- No `.env` is written; `env.example` is fully commented, and placeholder keys
  count as unset.
- `/api/health` does a cached compile-and-run probe; `doctor` does it uncached
  through the real grading modules.
- Termux keeps the source-install fallback; `doctor` detects the platform.
- README length and section order above; the repo is public, so the git install
  command is testable end to end.

Left to the implementation plan:

- Exact rendering of the Advanced disclosure and status strip.
- Wording of every doctor message and remediation command.
- Whether the wheel-contents test runs in the default suite or a CI job.

## Risks

- Moving `web/` and `problems/` touches tests and `.gitignore`; do it in one
  coherent commit with the test updates.
- `pytest.ini` turns `DeprecationWarning` into an error. A newer transitive
  dependency can break collection before any test runs (observed with `anyio`
  on the local Python 3.11 environment). Verification must use the supported
  3.12 toolchain; pinning transitive test dependencies is a separate fix.
- `pipx install git+...` requires network access to GitHub and Python; the README
  must say so plainly rather than implying a zero-dependency download.
- Termux browser opening differs; `doctor` should report it instead of failing
  silently.

## Success criteria

- On a clean Linux machine with Python 3.12 and gcc: one install command, then
  `cpractice start` opens a working page, and a submission gets a deterministic
  verdict.
- On a machine without gcc: `cpractice doctor` explains the missing compiler and
  prints the right install command for that platform.
- A new reader understands what CPractice is and how to start it from the first
  screen of the README, without meeting MCP or the API.
- The existing test suite (plus the new CLI/packaging tests) is green on the
  supported toolchain.
