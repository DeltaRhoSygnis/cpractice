"""The zero-credential path: CPractice must be fully usable without an AI key.

An instructor is not a developer. If CPractice cannot boot, list problems and
grade a submission with no provider credentials, nobody outside the project can
use it - and the landing page must not promise otherwise.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

REPO_PROBLEMS = Path(__file__).resolve().parent.parent / "app" / "seed_problems"
EXAMPLE_ID = "c-sum-two-integers"

REFERENCE = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""


def _offline_client(tmp_path: Path) -> TestClient:
    """An app with no provider credentials and no .env file."""
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=REPO_PROBLEMS,
        workspaces_dir=tmp_path / "workspaces",
        kenari_api_key=None,
        google_api_key=None,
    )
    return TestClient(create_app(settings))


def test_app_boots_without_any_provider_key(tmp_path: Path) -> None:
    with _offline_client(tmp_path) as client:
        body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["capabilities"]["ai"]["key_configured"] is False


def test_problems_are_listable_without_any_provider_key(tmp_path: Path) -> None:
    with _offline_client(tmp_path) as client:
        response = client.get("/api/problems")

    assert response.status_code == 200
    assert response.json()


def test_submission_is_graded_without_any_provider_key(tmp_path: Path) -> None:
    with _offline_client(tmp_path) as client:
        response = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit", json={"source": REFERENCE}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "passed"
    assert body["summary"]["all_passed"] is True


def test_generation_endpoint_reports_that_ai_is_unavailable(tmp_path: Path) -> None:
    """The failure must be explicit, not a 500 and not a silent empty response."""
    with _offline_client(tmp_path) as client:
        response = client.post("/api/problems/generate", json={"topic": "loops"})

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
