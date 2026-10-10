"""Tests for the problem API endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

EXAMPLE_ID = "c-sum-two-integers"
REPO_PROBLEMS = Path(__file__).resolve().parent.parent / "problems"


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=REPO_PROBLEMS,
        workspaces_dir=tmp_path / "workspaces",
    )
    return TestClient(create_app(settings))


def test_list_problems_includes_example(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/problems")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    ids = [p["id"] for p in body["problems"]]
    assert EXAMPLE_ID in ids


def test_get_problem_returns_detail(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(f"/api/problems/{EXAMPLE_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == EXAMPLE_ID
    assert body["statement_md"]
    assert body["starter_code"]
    assert body["hint_count"] == 5
    assert body["max_hint_level"] == 5


def test_public_tests_include_content(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get(f"/api/problems/{EXAMPLE_ID}").json()

    assert len(body["public_tests"]) == 3
    first = body["public_tests"][0]
    assert "stdin" in first
    assert "expected_stdout" in first


def test_hidden_test_content_is_never_exposed(tmp_path: Path) -> None:
    """Hidden inputs and expected outputs must not reach the client."""
    with _client(tmp_path) as client:
        body = client.get(f"/api/problems/{EXAMPLE_ID}").json()

    # Hidden content that exists on disk.
    problem_json = json.loads((REPO_PROBLEMS / EXAMPLE_ID / "problem.json").read_text())
    hidden = [t for t in problem_json["tests"] if t["visibility"] == "hidden"]
    assert hidden, "example must contain hidden tests for this test to be meaningful"

    raw = json.dumps(body)
    for test in hidden:
        assert test["expected_stdout"].strip() not in raw or test["expected_stdout"].strip() == "0"
        # The specific hidden stdin must never appear verbatim.
        assert test["stdin"].strip() not in raw

    # And the summary objects must not carry content keys at all.
    for summary in body["hidden_tests"]:
        assert set(summary) == {"id", "name"}


def test_hidden_test_count_is_reported(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get(f"/api/problems/{EXAMPLE_ID}").json()

    assert body["hidden_test_count"] == 3


def test_reference_solution_is_not_exposed_by_default(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get(f"/api/problems/{EXAMPLE_ID}").json()

    assert "reference_solution" not in body
    assert "solution_explanation" not in body


def test_unknown_problem_returns_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/problems/no-such-problem")

    assert response.status_code == 404


def test_path_traversal_attempt_returns_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        # Encoded traversal must not reach outside the problems directory.
        response = client.get("/api/problems/..%2F..%2Fetc%2Fpasswd")

    assert response.status_code in (404, 422)


def test_empty_problems_dir_returns_empty_list(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=tmp_path / "empty-problems",
        workspaces_dir=tmp_path / "workspaces",
    )
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/problems").json()

    assert body == {"count": 0, "problems": []}
