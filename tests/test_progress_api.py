"""Tests for the progress, attempts, and usage endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

EXAMPLE_ID = "c-sum-two-integers"
REPO_PROBLEMS = Path(__file__).resolve().parent.parent / "problems"

REFERENCE = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""

STARTER = "int main(void){return 0;}"


def _client(tmp_path: Path, **overrides) -> TestClient:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=REPO_PROBLEMS,
        workspaces_dir=tmp_path / "workspaces",
        **overrides,
    )
    return TestClient(create_app(settings))


# --- attempts --------------------------------------------------------------


def test_attempts_start_empty(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get("/api/attempts").json()

    assert body == {"count": 0, "attempts": []}


def test_submission_is_recorded_as_an_attempt(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        submit = client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": REFERENCE})
        assert submit.json()["attempt_id"] is not None

        body = client.get("/api/attempts").json()

    assert body["count"] == 1
    assert body["attempts"][0]["verdict"] == "passed"
    assert body["attempts"][0]["succeeded"] is True


def test_attempt_detail_includes_test_results(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        attempt_id = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER}
        ).json()["attempt_id"]

        body = client.get(f"/api/attempts/{attempt_id}").json()

    assert body["total"] == 6
    assert len(body["test_results"]) == 6


def test_unknown_attempt_returns_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/api/attempts/9999").status_code == 404


def test_attempts_can_be_filtered_by_problem(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER})
        body = client.get(f"/api/attempts?problem_id={EXAMPLE_ID}").json()
        empty = client.get("/api/attempts?problem_id=nope").json()

    assert body["count"] == 1
    assert empty["count"] == 0


def test_attempt_limit_is_validated(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/api/attempts?limit=0").status_code == 422
        assert client.get("/api/attempts?limit=999").status_code == 422


# --- progress --------------------------------------------------------------


def test_progress_starts_empty(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get("/api/progress").json()

    assert body["attempts"] == 0
    assert body["test_pass_rate"] is None


def test_progress_reflects_submissions(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER})
        client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": REFERENCE})

        body = client.get("/api/progress").json()

    assert body["attempts"] == 2
    assert body["problems_solved"] == 1
    assert body["tests_total"] == 12
    assert body["tests_passed"] == 6


def test_progress_reports_partial_pass_rate(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER})
        body = client.get("/api/progress").json()

    assert body["test_pass_rate"] == 0.0


def test_progress_tracks_hint_usage(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post(
            f"/api/problems/{EXAMPLE_ID}/submit",
            json={"source": STARTER, "hints_used": 3},
        )
        body = client.get("/api/attempts").json()

    assert body["attempts"][0]["hints_used"] == 3


# --- usage -----------------------------------------------------------------


def test_usage_starts_empty(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get("/api/usage").json()

    assert body["today"]["requests"] == 0
    assert body["budget"]["unlimited"] is True
    assert body["budget"]["remaining"] is None


def test_usage_reports_the_active_provider(tmp_path: Path) -> None:
    """The reported provider is the one actually in use, not the selection.

    With no credential the application is offline and there is no provider to
    report; the usage endpoint says so instead of naming one.
    """
    with _client(tmp_path) as client:
        body = client.get("/api/usage").json()

    assert body["provider"] == "none"
    assert body["model"]


def test_usage_reports_budget_when_set(tmp_path: Path) -> None:
    with _client(tmp_path, ai_daily_request_budget=10) as client:
        body = client.get("/api/usage").json()

    assert body["budget"]["daily_limit"] == 10
    assert body["budget"]["remaining"] == 10
    assert body["budget"]["unlimited"] is False


def test_usage_never_exposes_secrets(tmp_path: Path) -> None:
    with _client(tmp_path, kenari_api_key="kn-should-never-appear") as client:
        body = client.get("/api/usage").text

    assert "kn-should-never-appear" not in body


# --- persistence across restarts -------------------------------------------


def test_history_survives_a_restart(tmp_path: Path) -> None:
    """Previously saved history remains usable after the app restarts."""
    with _client(tmp_path) as client:
        client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": REFERENCE})

    # A second app instance over the same database file.
    with _client(tmp_path) as client:
        body = client.get("/api/attempts").json()

    assert body["count"] == 1
    assert body["attempts"][0]["succeeded"] is True


def test_saved_problems_remain_usable_without_a_provider(tmp_path: Path) -> None:
    """Design decision #4: cached exercises outlive provider outage."""
    with _client(tmp_path) as client:
        listing = client.get("/api/problems").json()
        assert listing["count"] >= 1

        # Grading works with no AI configured at all.
        response = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit", json={"source": REFERENCE}
        )

    assert response.status_code == 200
    assert response.json()["summary"]["all_passed"] is True
