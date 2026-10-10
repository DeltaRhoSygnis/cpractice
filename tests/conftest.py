"""Shared pytest fixtures for the CPractice platform test suite.

The suite is **hermetic**: it never reads a developer's real ``.env``. Settings
are constructed with explicit values, and the ``env`` autouse fixture clears
any provider credentials that may exist in the process environment. Without
this, a local ``KENARI_API_KEY`` would silently change test outcomes (for
example by making "no provider configured" tests take the configured path).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

#: Environment variables that could leak real configuration into tests.
_CREDENTIAL_VARS = (
    "KENARI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "AI_PROVIDER",
    "AI_MODEL",
    "KENARI_BASE_URL",
)


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove provider credentials and force config to ignore any .env file."""
    for name in _CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)

    # Point Settings at a non-existent .env so a developer's file is ignored.
    monkeypatch.setattr("app.config.Settings.model_config", {
        "env_file": None,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    })


def make_settings(tmp_path: Path, **overrides) -> Settings:
    """Build isolated settings with no credentials unless explicitly given."""
    values = {
        "database_path": tmp_path / "data" / "cpractice.db",
        "problems_dir": tmp_path / "problems",
        "workspaces_dir": tmp_path / "workspaces",
        "kenari_api_key": None,
        "google_api_key": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Settings pointing all runtime paths at an isolated temp directory."""
    return make_settings(tmp_path)


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient bound to a freshly built application."""
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
