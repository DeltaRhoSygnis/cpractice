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


# --- design-system guarantees ----------------------------------------------


def test_theme_defines_both_schemes() -> None:
    """The restyle must keep a dark default and a light override."""
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert "prefers-color-scheme: light" in css
    assert "--bg:" in css and "--surface:" in css and "--text:" in css


def test_control_border_has_its_own_token() -> None:
    """Control boundaries must not reuse the decorative hairline.

    WCAG 1.4.11 needs a perceivable edge on inputs; a single `--border` cannot
    serve both a 1px divider and a control outline.
    """
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert "--border-strong:" in css
    assert "border: 1px solid var(--border-strong)" in css


def test_reduced_motion_stops_the_spinner() -> None:
    """Reduced motion must neutralise, not merely slow, the spinner.

    Ordering matters: the reduced-motion `animation: none` must appear AFTER the
    base spinner rule, or equal-specificity source order lets the animation win.
    """
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert "prefers-reduced-motion" in css
    assert "animation: none" in css
    assert css.index(".spinner") < css.index("animation: none")


def test_route_changes_announce_without_live_region_on_view() -> None:
    """Navigation announces via a small status node, not the whole view.

    Making #view a live region would read the entire page aloud on every route.
    """
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert 'id="route-announcer"' in index
    assert 'role="status"' in index
    # #view must NOT itself be a live region.
    assert 'id="view" aria-live' not in index


def test_transitions_name_their_properties() -> None:
    """`transition: all` is banned; each transition lists what it animates."""
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert "transition: all" not in css
    assert "will-change: all" not in css


def test_status_is_never_signalled_by_colour_alone() -> None:
    """Toasts carry an icon and a status word, not just a colour strip."""
    script = (WEB / "app.js").read_text(encoding="utf-8")

    # The toast must expose a non-colour cue: an icon glyph and a status word
    # (used as an aria-label so the state is announced, not only seen).
    assert "TOAST_ICON" in script
    assert "TOAST_WORD" in script
    assert '"✘"' in script and '"✔"' in script


def test_verdict_and_failure_labels_match_backend_enums() -> None:
    """The label maps must key on values the backend can actually send.

    A map wired to invented enum values silently falls back to raw machine
    text, which is the exact thing the labels exist to prevent.
    """
    script = (WEB / "app.js").read_text(encoding="utf-8")

    # Real attempt verdicts: app/feedback/reporter.py::verdict
    for verdict in ("passed", "partial", "all_failed", "compilation_failed"):
        assert f'{verdict}:' in script, f"VERDICT_LABEL missing {verdict!r}"

    # Real failure categories: app/schemas/grading.py::ResultCategory
    for category in ("wrong_answer", "runtime_error", "timeout",
                     "output_limit_exceeded", "compilation_error", "internal_error"):
        assert f'{category}:' in script, f"FAILURE_LABEL missing {category!r}"


def test_pedagogy_renders_learning_objective_card() -> None:
    """The problem workspace must render the optional pedagogy block.

    The API sends `pedagogy` (primary objective, role, prerequisites, reasoning
    moves, transfer goal) but the UI used to ignore it. The card must map the
    `exercise_role` enum to a learner-facing label rather than raw snake_case.
    """
    script = (WEB / "app.js").read_text(encoding="utf-8")

    assert "pedagogy" in script
    assert "primary_objective" in script
    assert "target_reasoning_moves" in script
    # The role enum is shown as a human label, not the machine value.
    assert "core reasoning" in script
    assert "ROLE_LABEL" in script


def test_error_card_uses_http_status_not_message_regex() -> None:
    """Server-vs-client failures are classified by status, not string guessing."""
    script = (WEB / "app.js").read_text(encoding="utf-8")

    assert "error.status" in script
    # The fragile `\b(5\d\d)\b` message probe must be gone.
    assert r"\b(5\d\d)\b" not in script


def test_glass_is_limited_and_has_a_flat_backdrop() -> None:
    """Glass is a deliberate accent, not a theme: the body stays opaque.

    A translucent body behind a translucent header would destroy contrast.
    """
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert "backdrop-filter" in css
    # The body must paint a solid background behind the glass surfaces.
    assert "body {" in css and "background: var(--bg);" in css
