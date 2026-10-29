"""Tests for application configuration loading.

These tests assert *code defaults*, so they construct ``Settings`` with the
``_env_file`` disabled and clear provider credentials. The autouse fixture in
``conftest.py`` already removes credentials; passing ``_env_file=None`` makes
the intent explicit and immune to a developer's local ``.env``.
"""

from __future__ import annotations

from pathlib import Path

from app.config import ROOT_DIR, Settings


def _settings(**overrides) -> Settings:
    """Settings with no .env file and no credential inheritance."""
    return Settings(_env_file=None, **overrides)


def test_defaults_are_localhost_only() -> None:
    settings = _settings()

    # Design decision #8: bind to localhost by default.
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_default_limits_are_sane() -> None:
    settings = _settings()

    assert settings.run_wall_timeout_ms > 0
    assert settings.run_memory_limit_mb > 0
    assert settings.run_max_output_bytes > 0


def test_relative_paths_resolve_under_repo_root() -> None:
    settings = _settings(
        database_path=Path("data/cpractice.db"),
        problems_dir=Path("problems"),
        workspaces_dir=Path("workspaces"),
    )

    assert settings.database_file == ROOT_DIR / "data" / "cpractice.db"
    assert settings.problems_path == ROOT_DIR / "problems"
    assert settings.workspaces_path == ROOT_DIR / "workspaces"


def test_absolute_paths_are_respected() -> None:
    absolute = Path("/tmp/cpractice-elsewhere")
    settings = _settings(problems_dir=absolute)

    assert settings.problems_path == absolute


def test_secrets_default_to_none() -> None:
    settings = _settings()

    assert settings.google_api_key is None
    assert settings.kenari_api_key is None


def test_default_provider_is_kenari() -> None:
    settings = _settings()

    # Kenari is the gateway used for deepseek-v4-1-flash.
    assert settings.ai_provider == "kenari"
    assert settings.ai_model == "deepseek-v4-1-flash"
    assert settings.kenari_base_url == "https://kenari.id/v1"


def test_placeholder_key_is_not_a_configured_key() -> None:
    settings = Settings(_env_file=None, kenari_api_key="your-kenari-key-here")
    assert settings.any_ai_key_configured is False
    assert settings.resolved_ai_provider is None
