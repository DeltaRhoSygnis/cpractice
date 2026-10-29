"""Tests for milestone 1: application foundation and health endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def response_keys(payload: object) -> set[str]:
    """Collect every dict key appearing anywhere in a JSON payload."""
    keys: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                keys.add(str(key))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return keys


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "CPractice"
    assert "version" in body


def test_health_reports_capabilities_without_secret_values(client: TestClient) -> None:
    body = client.get("/api/health").json()
    capabilities = body["capabilities"]

    assert set(capabilities) == {"compiler", "ai", "storage", "grading"}
    assert capabilities["ai"]["provider"] == "kenari"

    # A boolean presence flag is reported; the key value itself never is.
    assert capabilities["ai"]["key_configured"] is False
    # Neither the config field name nor any raw key string is echoed back.
    assert "google_api_key" not in response_keys(body)


def test_health_reports_grading_probe_and_home(client) -> None:
    body = client.get("/api/health").json()
    assert "grading" in body["capabilities"]
    assert body["capabilities"]["grading"]["ready"] in (True, False)
    assert body["home"] == str(client.app.state.settings.home)


def test_health_reports_key_configured_when_present(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=tmp_path / "problems",
        workspaces_dir=tmp_path / "workspaces",
        ai_provider="kenari",
        kenari_api_key="present-but-never-returned",
    )
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()

    assert body["capabilities"]["ai"]["key_configured"] is True
    # The literal secret must not leak into the response.
    assert "present-but-never-returned" not in str(body)


def test_health_reports_google_key_when_google_selected(tmp_path: Path) -> None:
    """The key-presence check follows the configured provider."""
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=tmp_path / "problems",
        workspaces_dir=tmp_path / "workspaces",
        ai_provider="google",
        google_api_key="google-key-present",
    )
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()

    assert body["capabilities"]["ai"]["provider"] == "google"
    assert body["capabilities"]["ai"]["key_configured"] is True
    assert "google-key-present" not in str(body)


def test_health_ignores_key_for_inactive_provider(tmp_path: Path) -> None:
    """A google key must not satisfy a kenari-configured instance."""
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=tmp_path / "problems",
        workspaces_dir=tmp_path / "workspaces",
        ai_provider="kenari",
        kenari_api_key=None,
        google_api_key="google-key-present",
    )
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()

    assert body["capabilities"]["ai"]["key_configured"] is False


def test_lifespan_creates_runtime_directories(settings: Settings) -> None:
    assert not settings.problems_path.exists()
    assert not settings.workspaces_path.exists()

    with TestClient(create_app(settings)):
        pass

    assert settings.problems_path.is_dir()
    assert settings.workspaces_path.is_dir()
    assert settings.database_file.parent.is_dir()


def test_static_frontend_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "CPractice" in response.text
    assert "text/html" in response.headers["content-type"]


def test_unknown_api_route_returns_404(client: TestClient) -> None:
    assert client.get("/api/does-not-exist").status_code == 404
