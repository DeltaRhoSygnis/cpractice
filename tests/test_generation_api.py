"""Tests for the generation API endpoint.

The payload reuses the calibrated fixture from the pipeline tests: the pipeline
now enforces the calibration standard, so a single-reasoning-move exercise would
be rejected here rather than proving anything about the endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.base import AuthError
from app.ai.mock import MockProvider, failing_provider
from app.config import Settings
from app.generation.pipeline import GenerationPipeline
from app.main import create_app
from tests.test_generation_pipeline import good_payload as _calibrated_payload

REFERENCE = _calibrated_payload()["reference_solution"]

PAYLOAD = _calibrated_payload(
    id="c-api-running-max",
    title="API Running Maximum",
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=tmp_path / "problems",
        workspaces_dir=tmp_path / "workspaces",
        kenari_api_key=None,
        google_api_key=None,
    )


def _client_with_provider(tmp_path: Path, provider) -> TestClient:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        # Replace the pipeline with one backed by the mock provider.
        app.state.generation_pipeline = GenerationPipeline(
            provider,
            problems_dir=tmp_path / "problems",
            sleep=lambda _: None,
        )
        yield_client = client
    return yield_client


@pytest.fixture()
def client_with_mock(tmp_path: Path):
    app = create_app(_settings(tmp_path))
    provider = MockProvider(responses=json.dumps(PAYLOAD))
    with TestClient(app) as client:
        app.state.generation_pipeline = GenerationPipeline(
            provider, problems_dir=tmp_path / "problems", sleep=lambda _: None
        )
        yield client, provider


# --- no provider configured ------------------------------------------------


def test_generation_without_key_returns_503(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post("/api/problems/generate", json={})

    assert response.status_code == 503
    assert "KENARI_API_KEY" in response.json()["detail"] or "GOOGLE_API_KEY" in response.json()["detail"]


def test_health_reports_ai_disabled_without_key(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        body = client.get("/api/health").json()

    assert body["capabilities"]["ai"]["key_configured"] is False


# --- happy path ------------------------------------------------------------


def test_generate_succeeds_with_mock_provider(client_with_mock) -> None:
    client, _ = client_with_mock

    response = client.post("/api/problems/generate", json={"topic": "arithmetic"})

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["problem_id"] == "c-api-running-max"
    assert body["status"] == "validated"
    assert body["reference"]["passed"] == 6
    assert body["errors"] == []


def test_generated_problem_is_listed_afterwards(client_with_mock) -> None:
    client, _ = client_with_mock
    client.post("/api/problems/generate", json={})

    listing = client.get("/api/problems").json()

    assert "c-api-running-max" in [p["id"] for p in listing["problems"]]


def test_generated_problem_is_fetchable(client_with_mock) -> None:
    client, _ = client_with_mock
    client.post("/api/problems/generate", json={})

    response = client.get("/api/problems/c-api-running-max")

    assert response.status_code == 200
    assert response.json()["title"] == "API Running Maximum"


def test_second_request_reports_cache_hit(client_with_mock) -> None:
    client, provider = client_with_mock

    first = client.post("/api/problems/generate", json={}).json()
    second = client.post("/api/problems/generate", json={}).json()

    assert first["from_cache"] is False
    assert second["from_cache"] is True
    assert len(provider.calls) == 1


# --- validation ------------------------------------------------------------


def test_invalid_difficulty_is_rejected(client_with_mock) -> None:
    client, _ = client_with_mock

    response = client.post("/api/problems/generate", json={"difficulty": "impossible"})

    assert response.status_code == 422


def test_blank_topic_is_rejected(client_with_mock) -> None:
    client, _ = client_with_mock

    assert client.post("/api/problems/generate", json={"topic": ""}).status_code == 422


# --- provider error mapping ------------------------------------------------


def test_auth_error_maps_to_502(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        app.state.generation_pipeline = GenerationPipeline(
            failing_provider(AuthError("bad key"), times=5),
            problems_dir=tmp_path / "problems",
            sleep=lambda _: None,
        )
        response = client.post("/api/problems/generate", json={})

    assert response.status_code == 502
    assert "authentication" in response.json()["detail"].lower()


def test_malformed_output_maps_to_422(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        app.state.generation_pipeline = GenerationPipeline(
            MockProvider(responses="not json"), problems_dir=tmp_path / "problems", sleep=lambda _: None
        )
        response = client.post("/api/problems/generate", json={})

    assert response.status_code == 422


def test_rejected_problem_is_reported_with_findings(tmp_path: Path) -> None:
    bad = dict(PAYLOAD)
    bad["reference_solution"] = 'int main(void){ printf("x" return 0; }'
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        app.state.generation_pipeline = GenerationPipeline(
            MockProvider(responses=json.dumps(bad)),
            problems_dir=tmp_path / "problems",
            sleep=lambda _: None,
        )
        response = client.post("/api/problems/generate", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert body["status"] == "rejected"
    assert any(f["code"] == "reference-does-not-compile" for f in body["errors"])
