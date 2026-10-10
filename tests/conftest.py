"""Shared pytest fixtures for the CPractice platform test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Settings pointing all runtime paths at an isolated temp directory."""
    return Settings(
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=tmp_path / "problems",
        workspaces_dir=tmp_path / "workspaces",
        google_api_key=None,
    )


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient bound to a freshly built application."""
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
