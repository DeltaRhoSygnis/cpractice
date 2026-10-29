"""Tests for home-directory resolution.

Installed users get one writable home (``~/.cpractice`` by default). A source
checkout keeps using the repository root so existing developer workflows do not
move files. ``CPRACTICE_HOME`` always wins.
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings, resolve_home
from tests.conftest import make_settings


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


def test_empty_override_is_treated_as_unset(monkeypatch, tmp_path) -> None:
    """``CPRACTICE_HOME=`` must not resolve to the current directory."""
    monkeypatch.setenv("CPRACTICE_HOME", "   ")
    monkeypatch.setattr("app.config.is_source_checkout", lambda root=None: False)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    assert resolve_home() == tmp_path / ".cpractice"
    assert Settings(_env_file=None, cpractice_home="  ").home == tmp_path / ".cpractice"


def test_test_settings_keep_the_home_inside_tmp_path(tmp_path) -> None:
    """The suite must never write runtime files into the checkout."""
    assert make_settings(tmp_path).home == tmp_path


def test_suite_never_resolves_home_to_the_checkout() -> None:
    """The autouse fixture must keep runtime files out of the repository."""
    checkout = Path(__file__).resolve().parent.parent
    assert Settings(_env_file=None).home != checkout
