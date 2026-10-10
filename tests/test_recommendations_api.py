"""Tests for the recommendations endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

REPO_PROBLEMS = Path(__file__).resolve().parent.parent / "problems"
EXAMPLE_ID = "c-sum-two-integers"

STARTER = "int main(void){return 0;}"
REFERENCE = (
    '#include <stdio.h>\n'
    'int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;'
    'printf("%d\\n",a+b);return 0;}\n'
)


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                database_path=tmp_path / "data" / "cpractice.db",
                problems_dir=REPO_PROBLEMS,
                workspaces_dir=tmp_path / "workspaces",
                kenari_api_key=None,
            )
        )
    )


def test_recommendations_without_history_are_exploratory(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get("/api/recommendations").json()

    assert body["evidence_based"] is False
    if body["count"]:
        assert all(r["exploratory"] for r in body["recommendations"])


def test_recommendations_become_evidence_based_after_failures(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        # Two failing attempts satisfy the minimum sample for a weakness signal.
        for _ in range(2):
            client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER})

        body = client.get("/api/recommendations").json()

    # The example problem declares topics, so a weakness signal now exists.
    assert body["evidence_based"] is True


def test_recommendation_cites_observed_attempt_counts(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        for _ in range(2):
            client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER})
        body = client.get("/api/recommendations").json()

    assert body["count"] >= 1
    rec = body["recommendations"][0]
    assert rec["evidence"]["attempts"] == 2
    assert rec["evidence"]["failures"] == 2
    assert "failed" in rec["reason"].lower() or "attempts" in rec["reason"].lower()


def test_solved_problem_is_not_recommended(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": REFERENCE})
        body = client.get("/api/recommendations").json()

    ids = [r["problem_id"] for r in body["recommendations"]]
    assert EXAMPLE_ID not in ids


def test_limit_is_validated(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/api/recommendations?limit=0").status_code == 422
        assert client.get("/api/recommendations?limit=99").status_code == 422


def test_recommendations_are_unique(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        for _ in range(2):
            client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER})
        body = client.get("/api/recommendations").json()

    ids = [r["problem_id"] for r in body["recommendations"]]
    assert len(ids) == len(set(ids))
