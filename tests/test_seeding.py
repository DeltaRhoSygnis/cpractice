"""Tests for one-time, non-destructive seeding of the example problems.

Seeding must be safe to run on every start: it copies a seed package only when
the marker has never recorded it and the target is absent. A package the user
edited is never overwritten, and a package the user deleted is never
resurrected.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.runtime import (
    ensure_runtime_directories,
    read_state,
    seed_problems,
    write_env_template,
    write_state,
)
from tests.conftest import make_settings


def _seed(tmp_path: Path) -> Path:
    seed = tmp_path / "seed" / "demo"
    (seed / "starter").mkdir(parents=True)
    (seed / "problem.json").write_text('{"id": "demo"}', encoding="utf-8")
    return tmp_path / "seed"


def test_seed_copies_missing_packages(tmp_path) -> None:
    copied = seed_problems(tmp_path / "problems", seed_dir=_seed(tmp_path))
    assert copied == ["demo"]
    assert (tmp_path / "problems" / "demo" / "problem.json").is_file()
    assert not (tmp_path / "problems" / ".demo.tmp").exists()


def test_seed_is_idempotent(tmp_path) -> None:
    seed = _seed(tmp_path)
    seed_problems(tmp_path / "problems", seed_dir=seed)
    assert seed_problems(tmp_path / "problems", seed_dir=seed) == []


def test_stale_staging_directory_is_replaced(tmp_path) -> None:
    problems = tmp_path / "problems"
    staging = problems / ".demo.tmp"
    staging.mkdir(parents=True)
    (staging / "junk").write_text("interrupted copy", encoding="utf-8")

    assert seed_problems(problems, seed_dir=_seed(tmp_path)) == ["demo"]
    assert not staging.exists()
    assert (problems / "demo" / "problem.json").is_file()


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


# --- Marker contract ---------------------------------------------------------


def test_marker_records_copied_ids(tmp_path) -> None:
    seed_problems(tmp_path / "problems", seed_dir=_seed(tmp_path))

    marker = tmp_path / "problems" / ".seeded"
    assert json.loads(marker.read_text(encoding="utf-8")) == {"seeded": ["demo"]}


def test_existing_package_is_recorded_without_copying(tmp_path) -> None:
    seed = _seed(tmp_path)
    target = tmp_path / "problems" / "demo"
    target.mkdir(parents=True)
    (target / "problem.json").write_text('{"id": "hand-made"}', encoding="utf-8")

    assert seed_problems(tmp_path / "problems", seed_dir=seed) == []

    marker = tmp_path / "problems" / ".seeded"
    assert json.loads(marker.read_text(encoding="utf-8"))["seeded"] == ["demo"]

    # Recording the hand-made package also means a later deletion is honoured.
    shutil.rmtree(target)
    assert seed_problems(tmp_path / "problems", seed_dir=seed) == []
    assert not target.exists()


def test_corrupt_marker_does_not_reseed_over_existing_packages(tmp_path) -> None:
    problems = tmp_path / "problems"
    target = problems / "demo"
    target.mkdir(parents=True)
    (target / "problem.json").write_text('{"id": "hand-made"}', encoding="utf-8")
    (problems / ".seeded").write_text("not json", encoding="utf-8")

    assert seed_problems(problems, seed_dir=_seed(tmp_path)) == []
    assert json.loads((target / "problem.json").read_text())["id"] == "hand-made"
    assert json.loads((problems / ".seeded").read_text(encoding="utf-8"))["seeded"] == ["demo"]


def test_seed_without_seed_directory_creates_no_marker(tmp_path) -> None:
    problems = tmp_path / "problems"

    assert seed_problems(problems, seed_dir=tmp_path / "missing") == []
    assert not (problems / ".seeded").exists()


def test_seeding_a_directory_into_itself_is_a_no_op(tmp_path) -> None:
    seed = _seed(tmp_path)

    assert seed_problems(seed, seed_dir=seed) == []
    assert not (seed / ".seeded").exists()
    assert json.loads((seed / "demo" / "problem.json").read_text())["id"] == "demo"


# --- Template contract -------------------------------------------------------


def test_env_template_is_not_overwritten(tmp_path) -> None:
    existing = tmp_path / "env.example"
    existing.write_text("# my own notes\n", encoding="utf-8")

    write_env_template(tmp_path)

    assert existing.read_text(encoding="utf-8") == "# my own notes\n"


# --- Startup contract --------------------------------------------------------


def test_ensure_runtime_directories_creates_seeds_and_template(tmp_path) -> None:
    settings = make_settings(tmp_path, cpractice_home=tmp_path / "home")

    ensure_runtime_directories(settings)

    assert settings.problems_path.is_dir()
    assert settings.workspaces_path.is_dir()
    assert settings.database_file.parent.is_dir()
    assert (settings.problems_path / "c-sum-two-integers" / "problem.json").is_file()
    assert (settings.problems_path / "pset-vote-tally" / "problem.json").is_file()
    assert (settings.home / "env.example").is_file()

    # A second start copies nothing and leaves the marker stable.
    marker = settings.problems_path / ".seeded"
    before = marker.read_text(encoding="utf-8")
    ensure_runtime_directories(settings)
    assert marker.read_text(encoding="utf-8") == before


# --- Durable state -----------------------------------------------------------


def test_read_state_returns_none_when_absent(tmp_path) -> None:
    assert read_state(tmp_path) is None


def test_state_round_trips_exactly(tmp_path) -> None:
    write_state(tmp_path, host="127.0.0.1", port=9123)

    assert read_state(tmp_path) == {"host": "127.0.0.1", "port": 9123}
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8")) == {
        "host": "127.0.0.1",
        "port": 9123,
    }


def test_read_state_rejects_malformed_state(tmp_path) -> None:
    (tmp_path / "state.json").write_text('{"host": "127.0.0.1"}', encoding="utf-8")
    assert read_state(tmp_path) is None
