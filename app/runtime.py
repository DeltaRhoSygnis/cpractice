"""Runtime directory preparation and durable local state.

Everything CPractice writes at runtime lives under one home directory. This
module creates the directories the application expects, seeds the hand-authored
example problems exactly once, and reads/writes the small state files used by
the CLI.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from app.config import Settings

logger = logging.getLogger("cpractice")

#: Seed packages shipped inside the ``app`` package, so an installed wheel
#: works offline.
SEED_PROBLEMS_DIR = Path(__file__).resolve().parent / "seed_problems"

#: Records every problem id that has ever been seeded into a problems directory.
SEED_MARKER_NAME = ".seeded"

#: Fully commented template. It contains no active setting and no real secret.
ENV_TEMPLATE_NAME = "env.example"

#: Last host/port the CLI started, used by ``cpractice open``.
STATE_NAME = "state.json"

_ENV_TEMPLATE = """\
# CPractice configuration template.
# Copy this file to `.env` in the same directory and uncomment what you need.
# No setting below is active; CPractice never writes your real `.env`.

# --- AI provider ---
# "kenari" (default) or "google".
# AI_PROVIDER=kenari

# Model identifier. With the kenari gateway this is a catalog id, e.g.
# deepseek-v4-1-flash, optionally suffixed with ":free".
# AI_MODEL=deepseek-v4-1-flash

# Kenari gateway (OpenAI-compatible). One key reaches every catalog model.
# Get a key at https://kenari.id  (keys start with "kn-").
# KENARI_API_KEY=your-kenari-key-here
# KENARI_BASE_URL=https://kenari.id/v1

# Google AI Studio / Gemini (alternative adapter; only used when
# AI_PROVIDER=google). Get a key at https://aistudio.google.com/apikey
# GOOGLE_API_KEY=

# --- Rate limiting / retry (provider-adapter level) ---
# AI_MAX_RETRIES=3
# AI_BACKOFF_BASE_SECONDS=2
# AI_MAX_CONCURRENT_REQUESTS=2
# AI_DAILY_REQUEST_BUDGET=0

# --- Grading engine ---
# CC_COMPILER=gcc
# CC_STANDARD=c11
# RUN_WALL_TIMEOUT_MS=3000
# RUN_MEMORY_LIMIT_MB=128
# RUN_MAX_OUTPUT_BYTES=65536

# --- Server ---
# Localhost by default. Never bind 0.0.0.0 without a security review.
# HOST=127.0.0.1
# PORT=8000

# --- Storage ---
# Relative paths resolve under this home directory.
# DATABASE_PATH=data/cpractice.db
# PROBLEMS_DIR=problems
# WORKSPACES_DIR=workspaces
"""


def _read_seeded(marker: Path) -> list[str]:
    """Return the ids recorded in the marker, or an empty list.

    A missing, unreadable, or malformed marker is treated as "nothing recorded
    yet"; callers then apply the target-exists rule, which still protects
    hand-made packages from being overwritten.
    """
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    ids = payload.get("seeded")
    if not isinstance(ids, list):
        return []
    return [problem_id for problem_id in ids if isinstance(problem_id, str)]


def _write_marker(marker: Path, seeded: list[str]) -> None:
    """Write the marker atomically so a crash never leaves it half-written."""
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(
        json.dumps({"seeded": seeded}, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(marker)


def seed_problems(problems_dir: Path, seed_dir: Path | None = None) -> list[str]:
    """Copy example packages that have never been seeded into ``problems_dir``.

    A package is copied only when its id is absent from ``problems_dir/.seeded``
    and the target directory does not exist. An existing target is recorded and
    left untouched, so user edits are never overwritten and a package the user
    deleted is never resurrected. Returns the ids copied by this call.
    """
    problems_dir = Path(problems_dir)
    seed_dir = Path(seed_dir) if seed_dir is not None else SEED_PROBLEMS_DIR
    problems_dir.mkdir(parents=True, exist_ok=True)

    # Seeding a directory into itself would record marker state in the package
    # and can never copy anything; treat it as a no-op.
    if problems_dir.resolve() == seed_dir.resolve():
        return []

    marker = problems_dir / SEED_MARKER_NAME
    recorded = _read_seeded(marker)
    known = set(recorded)
    copied: list[str] = []
    changed = False

    if seed_dir.is_dir():
        for package in sorted(seed_dir.iterdir(), key=lambda path: path.name):
            if not package.is_dir() or not (package / "problem.json").is_file():
                continue

            problem_id = package.name
            if problem_id in known:
                continue

            target = problems_dir / problem_id
            if target.exists():
                known.add(problem_id)
                recorded.append(problem_id)
                changed = True
                continue

            # Copy into a staging directory and rename, so a crash mid-copy
            # never leaves a partial package that a later run would record as
            # seeded and never repair.
            staging = problems_dir / f".{problem_id}.tmp"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(package, staging)
            staging.replace(target)
            known.add(problem_id)
            recorded.append(problem_id)
            copied.append(problem_id)
            changed = True

    if changed:
        _write_marker(marker, recorded)
    if copied:
        logger.info("seeded example problems: %s", ", ".join(copied))
    return copied


def write_env_template(home: Path) -> None:
    """Write a fully commented ``env.example`` when the home has none yet.

    An existing template is never replaced: it may carry the operator's notes.
    """
    home = Path(home)
    target = home / ENV_TEMPLATE_NAME
    if target.exists():
        return

    home.mkdir(parents=True, exist_ok=True)
    temporary = home / (ENV_TEMPLATE_NAME + ".tmp")
    temporary.write_text(_ENV_TEMPLATE, encoding="utf-8")
    temporary.replace(target)


def ensure_runtime_directories(settings: Settings) -> None:
    """Create the writable directories and populate first-run assets."""
    settings.problems_path.mkdir(parents=True, exist_ok=True)
    settings.workspaces_path.mkdir(parents=True, exist_ok=True)
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)

    seed_problems(settings.problems_path)
    write_env_template(settings.home)


def read_state(home: Path) -> dict[str, object] | None:
    """Return the last recorded ``{"host", "port"}``, or ``None``.

    Anything that does not carry exactly a string host and an integer port is
    treated as absent, so a corrupt state file falls back to configured values.
    """
    try:
        payload = json.loads((Path(home) / STATE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    host = payload.get("host")
    port = payload.get("port")
    if not isinstance(host, str) or isinstance(port, bool) or not isinstance(port, int):
        return None
    return {"host": host, "port": port}


def write_state(home: Path, *, host: str, port: int) -> None:
    """Record the host and port the server was last started on."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)

    target = home / STATE_NAME
    temporary = home / (STATE_NAME + ".tmp")
    temporary.write_text(
        json.dumps({"host": host, "port": int(port)}) + "\n", encoding="utf-8"
    )
    temporary.replace(target)
