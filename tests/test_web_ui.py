"""Tests for the web UI contract.

The UI is static assets, so these tests assert the interface it depends on:
the assets are served, and the API it calls returns the shapes it renders.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

WEB = Path(__file__).resolve().parent.parent / "web"
REPO_PROBLEMS = Path(__file__).resolve().parent.parent / "problems"
EXAMPLE_ID = "c-sum-two-integers"


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "data" / "cpractice.db",
            problems_dir=REPO_PROBLEMS,
            workspaces_dir=tmp_path / "workspaces",
            kenari_api_key=None,
        )
    )
    with TestClient(app) as test_client:
        yield test_client


# --- assets ----------------------------------------------------------------


def test_index_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "CPractice" in response.text


def test_javascript_is_served(client: TestClient) -> None:
    response = client.get("/app.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_stylesheet_is_served(client: TestClient) -> None:
    response = client.get("/styles.css")

    assert response.status_code == 200
    assert "css" in response.headers["content-type"]


def test_api_routes_take_precedence_over_static_mount(client: TestClient) -> None:
    """The static mount must not shadow /api."""
    assert client.get("/api/health").status_code == 200


def test_unknown_static_path_returns_404(client: TestClient) -> None:
    assert client.get("/no-such-file.js").status_code == 404


# --- offline / no-CDN requirement ------------------------------------------


def test_no_external_resources_are_referenced() -> None:
    """The spec requires an offline-friendly UI with no CDN dependencies."""
    for name in ("index.html", "app.js", "styles.css"):
        content = (WEB / name).read_text(encoding="utf-8")
        assert "http://" not in content
        assert "https://" not in content
        assert "cdn." not in content


def test_no_framework_is_used() -> None:
    """Plain HTML/CSS/JS only, per the low-resource rule."""
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert "<script src=\"/app.js\"></script>" in index
    assert "react" not in index.lower()
    assert "vue" not in index.lower()


# --- accessibility basics --------------------------------------------------


def test_page_declares_language_and_viewport() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert 'lang="en"' in index
    assert 'name="viewport"' in index


def test_page_has_a_skip_link() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert "skip-link" in index
    assert 'href="#main"' in index


def test_main_landmark_is_focusable_for_route_changes() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert 'id="main"' in index
    assert "tabindex" in index


def test_status_signalling_is_not_colour_only() -> None:
    """Every pass/fail state pairs an icon or text with colour."""
    script = (WEB / "app.js").read_text(encoding="utf-8")

    # Icons are defined for each state alongside the colour classes.
    assert "STATUS_ICON" in script
    assert '"✔"' in script and '"✘"' in script


def test_hidden_tests_are_labelled_in_the_ui() -> None:
    script = (WEB / "app.js").read_text(encoding="utf-8")

    assert "hidden test" in script.lower()


# --- API shapes the UI depends on ------------------------------------------


def test_problem_view_shape_matches_ui_expectations(client: TestClient) -> None:
    body = client.get(f"/api/problems/{EXAMPLE_ID}").json()

    for key in ("id", "title", "statement_md", "starter_code",
                "public_tests", "hidden_test_count", "max_hint_level", "difficulty"):
        assert key in body, f"UI reads {key}"

    # The UI deliberately never receives the reference solution up front.
    assert "reference_solution" not in body


def test_submission_shape_matches_ui_expectations(client: TestClient) -> None:
    body = client.post(
        f"/api/problems/{EXAMPLE_ID}/submit",
        json={"source": "int main(void){return 0;}", "hints_used": 0},
    ).json()

    for key in ("verdict", "summary", "compilation", "tests", "next_action"):
        assert key in body, f"UI renders {key}"

    assert set(body["summary"]) >= {"passed", "total", "all_passed"}


def test_hint_shape_matches_ui_expectations(client: TestClient) -> None:
    body = client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"hints_used": 0}).json()

    for key in ("level", "text", "source", "is_solution_reveal", "next_level"):
        assert key in body, f"UI renders {key}"


def test_recommendation_shape_matches_ui_expectations(client: TestClient) -> None:
    body = client.get("/api/recommendations").json()

    assert "evidence_based" in body
    for rec in body["recommendations"]:
        for key in ("problem_id", "title", "reason", "exploratory"):
            assert key in rec, f"UI renders {key}"


def test_progress_shape_matches_ui_expectations(client: TestClient) -> None:
    body = client.get("/api/progress").json()

    for key in ("attempts", "problems_solved", "test_pass_rate",
                "failure_categories", "weak_topics"):
        assert key in body, f"UI renders {key}"


def test_usage_shape_matches_ui_expectations(client: TestClient) -> None:
    body = client.get("/api/usage").json()

    assert set(body) >= {"provider", "model", "today", "budget"}


def test_favicon_is_served(client: TestClient) -> None:
    """Browsers request this automatically; a 404 on every page load is noise."""
    response = client.get("/favicon.svg")

    assert response.status_code == 200
    assert "svg" in response.headers["content-type"]


def test_index_references_the_favicon() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert 'rel="icon"' in index
    assert "/favicon.svg" in index


def test_assets_are_not_cached(client: TestClient) -> None:
    """A stale cached app.js makes the UI look like it never updates."""
    for path in ("/", "/app.js", "/styles.css"):
        response = client.get(path)
        assert response.status_code == 200
        cache_control = response.headers.get("cache-control", "")
        assert "no-cache" in cache_control, f"{path} must not be cached"
