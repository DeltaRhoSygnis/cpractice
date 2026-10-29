# Student-First Product Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CPractice installable as one `cpractice` command with a browser-only interface, a truthful `doctor`, and a student-first README.

**Architecture:** Move runtime assets into the `app` package so a wheel actually runs; resolve one user home for installed mode; add a thin `app/cli.py` over the existing FastAPI app; extend `/api/health` with a real compile-and-run probe; simplify the dashboard and split advanced material into `docs/ADVANCED.md`.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, pydantic-settings, argparse, setuptools, pytest, plain HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-10-29-student-first-surface-design.md`

## Global Constraints

- Python `>=3.12`; no new runtime dependencies.
- Keep `127.0.0.1` as the default bind; non-loopback requires `--allow-lan`.
- AI never decides pass/fail; do not touch grading verdict logic.
- Hidden test data must never reach the client.
- Frontend stays plain HTML/CSS/JS, no framework, no CDN.
- `mcp==1.30.0` stays optional; the default install must not pull it.
- `uvicorn[standard]` stays out; Termux must remain supported.
- No `.env`, database, or workspace artifact is committed.
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`.

## Review Focus

- Python below 3.12 or native Windows: `cpractice` must print one actionable line and exit non-zero, never a traceback (tests: Task 5).
- A compiler exists but binaries cannot execute (Termux `noexec`): health and `doctor` must report *not ready*, not green (Task 4).
- `.env.example` placeholders copied into `.env`: AI must report offline, not "on" (Task 2).
- A user edits or deletes a seeded package: it must never be overwritten or resurrected (Task 3).
- A non-loopback bind or an occupied port: refuse or reuse deliberately, with a clear message (Task 6).

---

### Task 1: Package the runtime assets

**Files:**
- Move: `web/` → `app/web/`
- Move: `problems/c-sum-two-integers/` → `app/seed_problems/c-sum-two-integers/`
- Move: `problems/pset-vote-tally/` → `app/seed_problems/pset-vote-tally/`
- Modify: `app/config.py:112-113`
- Modify: `pyproject.toml:56-62`
- Modify: `.gitignore`
- Modify: `tests/test_web_ui.py:15-16`, `tests/test_offline_mode.py`, `tests/test_problems_api.py:13-20`, `tests/test_recommendations_api.py`, `tests/test_progress_api.py`, `tests/test_submissions_api.py:16-32`
- Test: `tests/test_packaging_assets.py`

**Interfaces:**
- Produces: `Settings.web_dir: Path` (packaged `app/web`); seed packages at `app/seed_problems/<id>/`.
- Later tasks read seed packages from `app/seed_problems`; nothing else may assume repo-root `web/` or `problems/`.

- [ ] **Step 1: Move the assets**

```bash
git mv web app/web
mkdir -p app/seed_problems
git mv problems/c-sum-two-integers app/seed_problems/c-sum-two-integers
git mv problems/pset-vote-tally app/seed_problems/pset-vote-tally
touch problems/.gitkeep
```

- [ ] **Step 2: Write the failing asset test**

`tests/test_packaging_assets.py`:

```python
from pathlib import Path

from app import __file__ as app_init
from app.config import Settings


def test_web_assets_live_inside_the_package() -> None:
    settings = Settings(_env_file=None)
    assert (settings.web_dir / "index.html").is_file()
    assert (settings.web_dir / "app.js").is_file()


def test_seed_problems_live_inside_the_package() -> None:
    seed = Path(app_init).resolve().parent / "seed_problems"
    assert (seed / "c-sum-two-integers" / "problem.json").is_file()
    assert (seed / "pset-vote-tally" / "problem.json").is_file()
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `python3 -m pytest tests/test_packaging_assets.py -q`
Expected: FAIL (module `app` has no `seed_problems`; `web_dir` still `ROOT_DIR/web`).

- [ ] **Step 4: Point the app and tests at the packaged paths**

`app/config.py`:

```python
@property
def web_dir(self) -> Path:
    return Path(__file__).resolve().parent / "web"
```

Update every test constant that used `Path(__file__).parent.parent / "problems"` to `Path(__file__).parent.parent / "app" / "seed_problems"`. In `tests/test_web_ui.py`, `WEB` becomes `Path(app.__file__).resolve().parent / "web"`.

`.gitignore`: replace the two tracked-fixture exceptions with:

```gitignore
problems/*
!problems/.gitkeep
```

`pyproject.toml`:

```toml
[tool.setuptools]
include-package-data = true

[tool.setuptools.package-data]
"app" = [
  "ai/prompts/*.md",
  "web/*",
  "seed_problems/*/problem.json",
  "seed_problems/*/statement.md",
  "seed_problems/*/starter/*.c",
  "seed_problems/*/reference/*.c",
]
```

- [ ] **Step 5: Run the affected tests and commit**

Run: `python3 -m pytest tests/test_packaging_assets.py tests/test_web_ui.py tests/test_problems_api.py -q`
Expected: PASS.

```bash
git add -A
git commit -m "refactor: package web assets and seed problems inside app"
```

---

### Task 2: One home directory and honest placeholder keys

**Files:**
- Modify: `app/config.py`
- Modify: `tests/conftest.py:23-30`
- Test: `tests/test_home.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `app.config.is_source_checkout(root: Path = ROOT_DIR) -> bool`; `app.config.resolve_home() -> Path`; `Settings.home -> Path`; `Settings.cpractice_home: Path | None`.
- Later tasks use `settings.home` for `.env`, `state.json`, and doctor output.

- [ ] **Step 1: Write the failing tests**

`tests/test_home.py`:

```python
from pathlib import Path

from app.config import Settings, resolve_home


def test_checkout_mode_resolves_to_repo_root(monkeypatch) -> None:
    monkeypatch.delenv("CPRACTICE_HOME", raising=False)
    monkeypatch.setattr("app.config.is_source_checkout", lambda root=None: True)
    assert resolve_home() == Path(__file__).resolve().parent.parent


def test_installed_mode_uses_dot_cpractice(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CPRACTICE_HOME", raising=False)
    monkeypatch.setattr("app.config.is_source_checkout", lambda root=None: False)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    assert resolve_home() == tmp_path / ".cpractice"


def test_cpractice_home_wins(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CPRACTICE_HOME", str(tmp_path / "custom"))
    assert resolve_home() == tmp_path / "custom"


def test_relative_paths_resolve_under_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CPRACTICE_HOME", str(tmp_path))
    settings = Settings(_env_file=None)
    assert settings.database_file == tmp_path / "data" / "cpractice.db"
    assert settings.problems_path == tmp_path / "problems"
```

Add to `tests/test_config.py`:

```python
def test_placeholder_key_is_not_a_configured_key() -> None:
    settings = Settings(_env_file=None, kenari_api_key="your-kenari-key-here")
    assert settings.any_ai_key_configured is False
    assert settings.resolved_ai_provider is None
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m pytest tests/test_home.py tests/test_config.py -q`
Expected: FAIL (`resolve_home` missing; placeholder counted as a key).

- [ ] **Step 3: Implement home resolution**

In `app/config.py` (add `import os`):

```python
DEFAULT_HOME_NAME = ".cpractice"
PLACEHOLDER_KEY_VALUES = frozenset({"your-kenari-key-here", "your-google-key-here", "change-me"})


def is_source_checkout(root: Path = ROOT_DIR) -> bool:
    return (root / "pyproject.toml").is_file() and (root / "app" / "web").is_dir()


def resolve_home() -> Path:
    override = os.environ.get("CPRACTICE_HOME")
    if override:
        return Path(override).expanduser()
    if is_source_checkout():
        return ROOT_DIR
    return Path.home() / DEFAULT_HOME_NAME
```

Set `env_file=resolve_home() / ".env"` in `SettingsConfigDict`. Add `cpractice_home: Path | None = None` and:

```python
@property
def home(self) -> Path:
    if self.cpractice_home:
        return Path(self.cpractice_home).expanduser()
    return resolve_home()
```

Change `database_file`, `problems_path`, `workspaces_path` to resolve relative paths under `self.home` instead of `ROOT_DIR`.

Filter placeholders in `ai_key_for`:

```python
value = (getattr(self, spec.key_field, None) or "").strip()
if not value or value.lower() in PLACEHOLDER_KEY_VALUES or value.lower().startswith("your-"):
    return None
return value
```

In `tests/conftest.py`, add `"CPRACTICE_HOME"` to `_CREDENTIAL_VARS` so a developer's shell cannot leak into the suite.

- [ ] **Step 4: Run the tests and commit**

Run: `python3 -m pytest tests/test_home.py tests/test_config.py -q`
Expected: PASS.

```bash
git add app/config.py tests/conftest.py tests/test_home.py tests/test_config.py
git commit -m "feat: resolve one home directory and ignore placeholder keys"
```

---

### Task 3: Seed example problems once, safely

**Files:**
- Create: `app/runtime.py`
- Modify: `app/main.py:43-47` (replace `_ensure_directories`)
- Test: `tests/test_seeding.py`

**Interfaces:**
- Produces: `app.runtime.ensure_runtime_directories(settings: Settings) -> None`; `app.runtime.seed_problems(problems_dir: Path, seed_dir: Path | None = None) -> list[str]`; `app.runtime.write_env_template(home: Path) -> None`; `app.runtime.read_state(home: Path) -> dict[str, object] | None`; `app.runtime.write_state(home: Path, *, host: str, port: int) -> None`.
- `seed_problems` returns the ids copied in this call; marker file is `problems/.seeded` with `{"seeded": [ids...]}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_seeding.py`:

```python
import json
from pathlib import Path

from app.runtime import seed_problems, write_env_template


def _seed(tmp_path: Path) -> Path:
    seed = tmp_path / "seed" / "demo"
    (seed / "starter").mkdir(parents=True)
    (seed / "problem.json").write_text('{"id": "demo"}', encoding="utf-8")
    return tmp_path / "seed"


def test_seed_copies_missing_packages(tmp_path) -> None:
    copied = seed_problems(tmp_path / "problems", seed_dir=_seed(tmp_path))
    assert copied == ["demo"]
    assert (tmp_path / "problems" / "demo" / "problem.json").is_file()


def test_seed_is_idempotent(tmp_path) -> None:
    seed = _seed(tmp_path)
    seed_problems(tmp_path / "problems", seed_dir=seed)
    assert seed_problems(tmp_path / "problems", seed_dir=seed) == []


def test_seed_does_not_overwrite_user_edits(tmp_path) -> None:
    seed = _seed(tmp_path)
    target = tmp_path / "problems" / "demo"
    target.mkdir(parents=True)
    (target / "problem.json").write_text('{"id": "edited"}', encoding="utf-8")
    seed_problems(tmp_path / "problems", seed_dir=seed)
    assert json.loads((target / "problem.json").read_text())["id"] == "edited"


def test_deleted_seed_is_not_resurrected(tmp_path) -> None:
    seed = _seed(tmp_path)
    seed_problems(tmp_path / "problems", seed_dir=seed)
    import shutil
    shutil.rmtree(tmp_path / "problems" / "demo")
    assert seed_problems(tmp_path / "problems", seed_dir=seed) == []


def test_env_template_has_no_active_key(tmp_path) -> None:
    write_env_template(tmp_path)
    text = (tmp_path / "env.example").read_text(encoding="utf-8")
    assert "KENARI_API_KEY" in text
    assert all(not line.strip() or line.strip().startswith("#") for line in text.splitlines())
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m pytest tests/test_seeding.py -q`
Expected: FAIL (`app.runtime` missing).

- [ ] **Step 3: Implement `app/runtime.py` and wire startup**

Implement `seed_problems` with `shutil.copytree`, a JSON marker read/write, and these rules: skip an id already listed in `.seeded`; if the target exists, record the id and skip; otherwise copy and record. Write the marker atomically (`tmp` then `replace`).

`ensure_runtime_directories` creates `problems_path`, `workspaces_path`, `database_file.parent`, calls `seed_problems(settings.problems_path)`, and calls `write_env_template(settings.home)`. `write_env_template` writes `home / "env.example"` only when absent, with every key line commented out.

`read_state` / `write_state` read and write `home / "state.json"` as `{"host": str, "port": int}`.

In `app/main.py`, import `ensure_runtime_directories` and replace the `_ensure_directories(settings)` call in `lifespan`; delete the old helper.

- [ ] **Step 4: Run the tests and commit**

Run: `python3 -m pytest tests/test_seeding.py tests/test_health_api.py -q`
Expected: PASS (the lifespan test still sees the runtime directories created).

```bash
git add app/runtime.py app/main.py tests/test_seeding.py
git commit -m "feat: seed example problems once behind a marker"
```

---

### Task 4: Truthful grading probe and health payload

**Files:**
- Create: `app/grading/probe.py`
- Modify: `app/api/health.py`
- Modify: `tests/test_health_api.py:39-42`
- Test: `tests/test_probe.py`

**Interfaces:**
- Produces: `GradingProbe(ready: bool, compiler: str, standard: str, detail: str)`; `probe_grading(*, compiler: str, standard: str, workdir: Path | None = None, timeout_ms: int = 3000, use_cache: bool = True) -> GradingProbe`.
- `/api/health` adds top-level `home: str` and `capabilities["grading"] = {"ready": bool, "compiler": str, "detail": str}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_probe.py`:

```python
import shutil
import stat
from pathlib import Path

import pytest

from app.grading.probe import probe_grading


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_probe_reports_ready_with_real_compiler(tmp_path) -> None:
    result = probe_grading(compiler="gcc", standard="c11", workdir=tmp_path, use_cache=False)
    assert result.ready is True
    assert result.detail == ""


def test_probe_reports_failure_for_unusable_compiler(tmp_path) -> None:
    fake = tmp_path / "fake-cc"
    fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    result = probe_grading(compiler=str(fake), standard="c11", workdir=tmp_path, use_cache=False)
    assert result.ready is False
    assert result.detail
```

Add to `tests/test_health_api.py`:

```python
def test_health_reports_grading_probe_and_home(client) -> None:
    body = client.get("/api/health").json()
    assert "grading" in body["capabilities"]
    assert body["capabilities"]["grading"]["ready"] in (True, False)
    assert body["home"] == str(client.app.state.settings.home)
```

Update the existing capability-set assertion to `{"compiler", "ai", "storage", "grading"}`.

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m pytest tests/test_probe.py tests/test_health_api.py -q`
Expected: FAIL (`app.grading.probe` missing; no `grading` key).

- [ ] **Step 3: Implement the probe and extend health**

`probe_grading` writes `int main(void){puts("ok");return 0;}` to a temp file (under `workdir` when given), calls `compile_source(...)`, then `run_binary(...)` with a 2 s timeout, and returns ready only when compilation succeeded and stdout strips to `"ok"`. Catch `CompilerError` and `OSError` and return `ready=False` with a short `detail`. Cache successful/failed results in a module dict keyed by `(compiler, standard)` for 60 s when `use_cache=True`.

In `app/api/health.py`, call `probe_grading(compiler=settings.cc_compiler, standard=settings.cc_standard)` and add the `grading` capability and `home` field. Keep the existing `compiler.available` field for compatibility.

- [ ] **Step 4: Run the tests and commit**

Run: `python3 -m pytest tests/test_probe.py tests/test_health_api.py -q`
Expected: PASS.

```bash
git add app/grading/probe.py app/api/health.py tests/test_probe.py tests/test_health_api.py
git commit -m "feat: report real grading readiness in health"
```

---

### Task 5: `cpractice` CLI skeleton and `doctor`

**Files:**
- Create: `app/cli.py`
- Modify: `pyproject.toml:53-54`
- Test: `tests/test_cli_doctor.py`

**Interfaces:**
- Produces: `app.cli.main(argv: Sequence[str] | None = None) -> int`; `build_parser() -> argparse.ArgumentParser`; `is_windows() -> bool`; `is_termux() -> bool`; `compiler_remediation() -> str`; `server_is_cpractice(url: str) -> bool`; `port_is_free(host: str, port: int) -> bool`; `cmd_doctor(args) -> int`.
- Every command imports `app.main` lazily so `doctor` runs on native Windows.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli_doctor.py`:

```python
from app import cli
from app.grading.probe import GradingProbe


def test_parser_exposes_commands() -> None:
    for command in ("start", "doctor", "problems", "open", "version"):
        assert cli.build_parser().parse_args([command]).command == command


def test_doctor_fails_with_remediation_when_compiler_missing(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setenv("CPRACTICE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "is_windows", lambda: False)
    monkeypatch.setattr(cli, "is_termux", lambda: False)
    monkeypatch.setattr(
        cli, "probe_grading",
        lambda **kwargs: GradingProbe(False, "gcc", "c11", "compiler failed"),
    )
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "build-essential" in out or "xcode-select" in out or "gcc" in out


def test_doctor_explains_native_windows(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "is_windows", lambda: True)
    assert cli.main(["doctor"]) == 1
    assert "WSL2" in capsys.readouterr().out
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m pytest tests/test_cli_doctor.py -q`
Expected: FAIL (`app.cli` missing).

- [ ] **Step 3: Implement the skeleton and doctor**

`build_parser()` creates the five subcommands with `dest="command"` and `main()` dispatches to `cmd_<name>`, returning the command's int. Use `argparse.ArgumentParser(prog="cpractice")`.

`server_is_cpractice(url)` performs a short `httpx.get(url + "/api/health")` and returns true only when the JSON body's `app` is `"CPractice"`; `port_is_free(host, port)` attempts a `socket.bind` and closes it.

`doctor` calls `ensure_runtime_directories(settings)` and then prints one line per check (`[ok]` / `[fail]`): Python version (`>=3.12`), home directory writable, grading probe (`use_cache=False`, `workdir=settings.workspaces_path`), the configured port free or held by CPractice, and AI status (informational, never a failure). On native Windows print the WSL2 instructions and return 1 before importing `app.main`. `compiler_remediation()` returns `pkg install clang` on Termux, `xcode-select --install` on macOS, `sudo apt install build-essential` on Debian-like Linux, and a generic "install gcc" line otherwise.

Add to `pyproject.toml`:

```toml
cpractice = "app.cli:main"
```

- [ ] **Step 4: Run the tests and commit**

Run: `python3 -m pytest tests/test_cli_doctor.py -q`
Expected: PASS.

```bash
git add app/cli.py pyproject.toml tests/test_cli_doctor.py
git commit -m "feat: add cpractice command and doctor"
```

---

### Task 5b: `cpractice-mcp` explains the optional SDK

**Files:**
- Modify: `app/mcp/server.py:506-536`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `app.mcp.server.main(argv: list[str] | None = None) -> int`; returns 1 and prints the `cpractice[mcp]` install line when the SDK is missing.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mcp_server.py`:

```python
def test_main_explains_missing_mcp_sdk(monkeypatch, capsys) -> None:
    def boom(base_url=None):
        raise ImportError("No module named 'mcp'")

    monkeypatch.setattr(mcp_server, "build_server", boom)
    assert mcp_server.main([]) == 1
    assert "cpractice[mcp]" in capsys.readouterr().out
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest tests/test_mcp_server.py::test_main_explains_missing_mcp_sdk -q`
Expected: FAIL (`main` returns `None` and raises).

- [ ] **Step 3: Catch the optional import**

Wrap `build_server(args.base_url)` in `try/except ImportError`; on failure print the install command and return 1. Return 0 after `mcp.run(...)`. Change the module footer to `raise SystemExit(main())`.

- [ ] **Step 4: Run the test and commit**

Run: `python3 -m pytest tests/test_mcp_server.py -q`
Expected: PASS (SDK-dependent registration tests still skip when absent).

```bash
git add app/mcp/server.py tests/test_mcp_server.py
git commit -m "fix: explain the optional MCP SDK instead of a traceback"
```

---

### Task 6: `start`, `open`, `problems`, `version`

**Files:**
- Modify: `app/cli.py`
- Test: `tests/test_cli_start.py`

**Interfaces:**
- Consumes: `server_is_cpractice(url)`, `port_is_free(host, port)`, `ensure_runtime_directories(settings)`, `read_state`/`write_state`.
- Produces: `resolve_bind(args, settings) -> tuple[str, int]`; `cmd_start(args) -> int`; `cmd_open(args) -> int`; `cmd_problems(args) -> int`; `cmd_version(args) -> int`; `open_browser(url: str) -> None`; `_run_server(app, host: str, port: int) -> None`.
- `cmd_start` persists `state.json` through `app.runtime.write_state`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli_start.py`:

```python
import json

from app import cli


def test_non_loopback_requires_allow_lan(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "is_windows", lambda: False)
    assert cli.main(["start", "--host", "0.0.0.0"]) == 2
    assert "--allow-lan" in capsys.readouterr().out


def test_existing_cpractice_is_reused(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CPRACTICE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "is_windows", lambda: False)
    monkeypatch.setattr(cli, "server_is_cpractice", lambda url: True)
    monkeypatch.setattr(cli, "open_browser", lambda url: None)
    monkeypatch.setattr(cli, "_run_server", lambda app, host, port: (_ for _ in ()).throw(AssertionError("must not start")))
    assert cli.main(["start"]) == 0


def test_start_records_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CPRACTICE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "is_windows", lambda: False)
    monkeypatch.setattr(cli, "server_is_cpractice", lambda url: False)
    monkeypatch.setattr(cli, "port_is_free", lambda host, port: True)
    monkeypatch.setattr(cli, "open_browser", lambda url: None)
    monkeypatch.setattr(cli, "_run_server", lambda app, host, port: None)
    assert cli.main(["start", "--port", "9123", "--no-browser"]) == 0
    assert json.loads((tmp_path / "state.json").read_text()) == {"host": "127.0.0.1", "port": 9123}
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python3 -m pytest tests/test_cli_start.py -q`
Expected: FAIL (subcommands not implemented).

- [ ] **Step 3: Implement the four commands**

`resolve_bind` precedence: `args.host` / `args.port` > `CPRACTICE_HOST` / `CPRACTICE_PORT` > `settings.host` / `settings.port` > defaults. `cmd_start` refuses a non-loopback host without `--allow-lan` (return 2). It probes `http://host:port/api/health`; a CPractice response opens the browser and returns 0; an occupied port that is not CPractice prints the conflict and returns 1. Otherwise it calls `ensure_runtime_directories`, `write_state`, builds the app lazily, starts a daemon thread that waits for health then calls `open_browser` unless `--no-browser`, and calls `_run_server` (wrapping `uvicorn.run`).

`cmd_open` reads `state.json` (falling back to configured host/port), verifies `/api/health`, and opens the browser or prints "no CPractice server is running".

`cmd_problems` loads `ProblemRepository(settings.problems_path).load_all()` and prints `id  title  (difficulty)`.

`cmd_version` prints `CPractice {settings.app_version}` and `home: {settings.home}`.

- [ ] **Step 4: Run the tests and commit**

Run: `python3 -m pytest tests/test_cli_start.py tests/test_cli_doctor.py -q`
Expected: PASS.

```bash
git add app/cli.py tests/test_cli_start.py
git commit -m "feat: add start, open, problems and version commands"
```

---

### Task 7: Student-first dashboard

**Files:**
- Modify: `web/index.html` (no structural change required unless the status strip needs a container)
- Modify: `web/app.js:220-370` (dashboard view)
- Modify: `web/styles.css`
- Test: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: `api.health()` and the `/api/health` fields `home`, `capabilities.grading.ready`, `capabilities.ai.any_key_configured`.
- Produces: a collapsed `<details class="advanced">` around the generation form and a status strip; no second polling loop.

- [ ] **Step 1: Write the failing UI test**

Add to `tests/test_web_ui.py`:

```python
def test_dashboard_exposes_advanced_disclosure_and_status(client) -> None:
    js = client.get("/app.js").text
    assert "Advanced" in js
    assert "Grading ready" in js
    assert "Data folder" in js
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m pytest tests/test_web_ui.py::test_dashboard_exposes_advanced_disclosure_and_status -q`
Expected: FAIL.

- [ ] **Step 3: Implement the disclosure and status strip**

In the dashboard render function, build the existing generation card into `generationCard`, then append:

```js
el("details", { class: "advanced" }, [
  el("summary", { text: "Advanced: generate or import a problem" }),
  generationCard,
])
```

Render a status strip above the cards:

```js
el("p", { class: "status-strip" }, [
  health.capabilities.grading.ready ? "Grading ready" : "Compiler missing — run cpractice doctor",
  health.capabilities.ai.any_key_configured ? "AI on" : "AI offline",
  `Data folder: ${health.home}`,
])
```

Handle a missing/older health payload defensively (optional chaining; the UI must not throw if a field is absent). Add `.advanced` and `.status-strip` styles using the existing CSS variables; keep contrast AA and do not add external fonts.

- [ ] **Step 4: Run the UI tests and commit**

Run: `python3 -m pytest tests/test_web_ui.py -q`
Expected: PASS.

```bash
git add web/app.js web/styles.css tests/test_web_ui.py
git commit -m "feat: make the dashboard student-first with an advanced door"
```

---

### Task 8: README, advanced docs, and install helper

**Files:**
- Modify: `README.md` (replace)
- Create: `docs/ADVANCED.md`
- Create: `scripts/install.sh`
- Test: `bash -n scripts/install.sh`

**Interfaces:**
- Consumes: the command names and flags from Tasks 5-6.
- Produces: the public install story and the advanced documentation destination.

- [ ] **Step 1: Write the README**

Keep 120-150 lines in the order from the spec: logo/badges, what it is, install (two commands), first problem (60-second loop), who it is for, why grading can be trusted, managing your practice (`doctor`, three pages, data home), AI is optional, Advanced link, Development link. Reference only images that are committed; do not link a screenshot placeholder. No MCP configuration, no API table, no environment-variable table.

- [ ] **Step 2: Move advanced material**

Create `docs/ADVANCED.md` with sections: MCP server and client configs, HTTP API table, importing packages, generation and batch, provider configuration, full environment-variable table, LAN sharing, and packaging/release notes. Move content from the current README rather than rewriting behaviour.

- [ ] **Step 3: Add the guided installer**

`scripts/install.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
# Detect uv/pipx and a C compiler; print the next command; install only with --yes.
```

It must not pipe a remote script into a shell. It prints `uv tool install "cpractice @ git+https://github.com/DeltaRhoSygnis/cpractice.git"` or the `pipx` equivalent, and the compiler remediation from `doctor` for the detected platform.

- [ ] **Step 4: Verify and commit**

Run: `chmod +x scripts/install.sh && bash -n scripts/install.sh`
Expected: no output, exit 0.

```bash
git add README.md docs/ADVANCED.md scripts/install.sh
git commit -m "docs: rewrite README for learners and move advanced material"
```

---

### Task 9: Wheel verification in CI

**Files:**
- Create: `tests/test_packaging.py`
- Modify: `.github/workflows/tests.yml`
- Modify: `pytest.ini` only if a marker is needed

**Interfaces:**
- Consumes: packaged paths from Task 1.
- Produces: a CI gate proving the wheel contains `app/web` and `app/seed_problems`.

- [ ] **Step 1: Write the opt-in wheel test**

`tests/test_packaging.py`:

```python
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(os.environ.get("CPRACTICE_BUILD_WHEEL") != "1", reason="set CPRACTICE_BUILD_WHEEL=1")
def test_wheel_contains_runtime_assets(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(tmp_path), str(ROOT)],
        check=True,
        capture_output=True,
    )
    wheel = next(tmp_path.glob("*.whl"))
    names = zipfile.ZipFile(wheel).namelist()
    assert "app/web/index.html" in names
    assert "app/web/app.js" in names
    assert any(name.startswith("app/seed_problems/c-sum-two-integers/") for name in names)
    assert any(name.startswith("app/seed_problems/pset-vote-tally/") for name in names)
```

- [ ] **Step 2: Run it and confirm it fails without the env var**

Run: `python3 -m pytest tests/test_packaging.py -q`
Expected: 1 skipped.

- [ ] **Step 3: Wire CI**

Add a step after the suite in `.github/workflows/tests.yml`:

```yaml
      - name: Verify wheel contents
        if: matrix.python-version == '3.12'
        env:
          CPRACTICE_BUILD_WHEEL: "1"
        run: python -m pytest tests/test_packaging.py -q
```

- [ ] **Step 4: Run the gate locally and commit**

Run: `CPRACTICE_BUILD_WHEEL=1 python3 -m pytest tests/test_packaging.py -q`
Expected: PASS (network is needed for build isolation).

```bash
git add tests/test_packaging.py .github/workflows/tests.yml
git commit -m "test: verify the wheel ships web assets and seed problems"
```

---

## Final verification

- [ ] `python3 -m pytest -q` — full suite green on the supported 3.12 toolchain.
- [ ] `pip wheel --no-deps -w dist .` then install the wheel in a clean venv:
      `pip install dist/*.whl && cpractice --help && cpractice doctor`.
- [ ] `CPRACTICE_HOME=$(mktemp -d) cpractice start --no-browser` serves `/api/health` and `/`.
- [ ] On a machine without gcc, `cpractice doctor` prints the platform remediation and exits 1.
- [ ] README first screen contains the install and first-problem path with no MCP/API material.
- [ ] `git status` is clean; no `.env`, database, or workspace file is tracked.
