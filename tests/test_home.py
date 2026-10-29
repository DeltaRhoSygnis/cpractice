"""Tests for home-directory resolution.

Installed users get one writable home (``~/.cpractice`` by default). A source
checkout keeps using the repository root so existing developer workflows do not
move files. ``CPRACTICE_HOME`` always wins.
"""

from __future__ import annotations

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
