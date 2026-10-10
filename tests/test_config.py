"""Tests for application configuration loading."""

from __future__ import annotations

from pathlib import Path

from app.config import ROOT_DIR, Settings


def test_defaults_are_localhost_only() -> None:
    settings = Settings()

    # Design decision #8: bind to localhost by default.
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_default_limits_are_sane() -> None:
    settings = Settings()

    assert settings.run_wall_timeout_ms > 0
    assert settings.run_memory_limit_mb > 0
    assert settings.run_max_output_bytes > 0


def test_relative_paths_resolve_under_repo_root() -> None:
    settings = Settings(
        database_path=Path("data/cpractice.db"),
        problems_dir=Path("problems"),
        workspaces_dir=Path("workspaces"),
    )

    assert settings.database_file == ROOT_DIR / "data" / "cpractice.db"
    assert settings.problems_path == ROOT_DIR / "problems"
    assert settings.workspaces_path == ROOT_DIR / "workspaces"


def test_absolute_paths_are_respected() -> None:
    absolute = Path("/tmp/cpractice-elsewhere")
    settings = Settings(problems_dir=absolute)

    assert settings.problems_path == absolute


def test_secrets_default_to_none() -> None:
    settings = Settings()

    assert settings.google_api_key is None
    assert settings.ai_provider == "google"
