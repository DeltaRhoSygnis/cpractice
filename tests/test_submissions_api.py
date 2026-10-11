"""Tests for the submission, hint, and solution endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.mock import MockProvider
from app.config import Settings
from app.feedback.hint_service import HintService
from app.main import create_app

EXAMPLE_ID = "c-sum-two-integers"
PSET_ID = "pset-vote-tally"
REPO_PROBLEMS = Path(__file__).resolve().parent.parent / "problems"

REFERENCE = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""

STARTER = "int main(void){return 0;}"


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=REPO_PROBLEMS,
        workspaces_dir=tmp_path / "workspaces",
        kenari_api_key=None,
    )
    return TestClient(create_app(settings))


# --- submission ------------------------------------------------------------


def test_correct_submission_passes_every_test(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit", json={"source": REFERENCE}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["all_passed"] is True
    assert body["verdict"] == "passed"
    assert body["next_action"] == "done"


def test_starters_wrong_output_is_reported(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER}
        )

    body = response.json()
    assert body["summary"]["all_passed"] is False
    assert body["summary"]["passed"] == 0
    assert body["failures"]
    assert body["next_action"] == "request_hint"


def test_compilation_error_maps_to_fix_compilation(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit",
            json={"source": 'int main(void){ printf("x" return 0; }'},
        )

    body = response.json()
    assert body["verdict"] == "compilation_failed"
    assert body["compilation"]["success"] is False
    assert body["compilation"]["diagnostics"]
    assert body["next_action"] == "fix_compilation"


def test_hidden_expected_output_never_reaches_the_client(tmp_path: Path) -> None:
    """The example problem has three hidden tests; none may leak their values."""
    problem_json = json.loads((REPO_PROBLEMS / EXAMPLE_ID / "problem.json").read_text())
    hidden = [t for t in problem_json["tests"] if t["visibility"] == "hidden"]
    assert hidden, "fixture must contain hidden tests"

    with _client(tmp_path) as client:
        response = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER}
        )

    body = response.json()

    # Structural check: hidden test entries must not carry a "detail" field,
    # which is where any observed/expected comparison could surface.
    hidden_ids = {t["id"] for t in hidden}
    for entry in body["tests"]:
        if entry["test_id"] in hidden_ids:
            assert "detail" not in entry

    # And no hidden *input* may appear anywhere in the payload.
    raw = json.dumps(body)
    for test in hidden:
        stdin = test["stdin"].strip()
        if len(stdin) >= 3:  # skip values too short to be meaningful
            assert stdin not in raw


def test_hidden_expected_output_is_absent_from_discovery_endpoint(tmp_path: Path) -> None:
    """The problem detail endpoint must expose hidden tests by name only."""
    problem_json = json.loads((REPO_PROBLEMS / EXAMPLE_ID / "problem.json").read_text())
    hidden = [t for t in problem_json["tests"] if t["visibility"] == "hidden"]

    with _client(tmp_path) as client:
        body = client.get(f"/api/problems/{EXAMPLE_ID}").json()

    for summary in body["hidden_tests"]:
        assert set(summary) == {"id", "name"}

    raw = json.dumps(body)
    for test in hidden:
        assert test["expected_stdout"].strip() not in raw or test["expected_stdout"].strip() == "0"


def test_empty_submission_is_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": "   "})

    assert response.status_code in (400, 422)


def test_oversized_submission_is_rejected(tmp_path: Path) -> None:
    huge = "x" * (200 * 1024)

    with _client(tmp_path) as client:
        response = client.post(f"/api/problems/{EXAMPLE_ID}/submit", json={"source": huge})

    assert response.status_code == 400
    assert "limit" in response.json()["detail"]


# --- checker in the submission response (spec S5) --------------------------


def test_legacy_exercise_submission_has_no_checks_key(tmp_path: Path) -> None:
    """An exercise without a checker keeps the exact payload it always had."""
    with _client(tmp_path) as client:
        body = client.post(
            f"/api/problems/{EXAMPLE_ID}/submit", json={"source": STARTER}
        ).json()

    assert "checks" not in body


def test_problem_set_submission_includes_ordered_checks(tmp_path: Path) -> None:
    problem_json = json.loads((REPO_PROBLEMS / PSET_ID / "problem.json").read_text())
    test_ids = [t["id"] for t in problem_json["tests"]]

    with _client(tmp_path) as client:
        response = client.post(
            f"/api/problems/{PSET_ID}/submit",
            json={"source": "int main(void){return 0;}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "checks" in body

    names = [c["name"] for c in body["checks"]]
    assert names[:2] == ["exists", "compiles"]
    assert names[2:] == test_ids


def test_problem_set_checks_have_the_report_shape(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.post(
            f"/api/problems/{PSET_ID}/submit",
            json={"source": "int main(void){return 0;}"},
        ).json()

    for check in body["checks"]:
        assert set(check) >= {
            "name",
            "description",
            "passed",
            "blocked",
            "cause",
            "data",
            "visibility",
        }
        # A check never carries per-test data that could leak hidden inputs.
        assert check["data"] == {}


def test_compilation_failure_blocks_behavioural_checks_in_response(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        body = client.post(
            f"/api/problems/{PSET_ID}/submit",
            json={"source": 'int main(void){ printf("x" return 0; }'},
        ).json()

    by_name = {c["name"]: c for c in body["checks"]}
    assert by_name["compiles"]["passed"] is False
    # Behavioural checks are blocked, not failed.
    behavioural = [c for c in body["checks"] if c["name"] not in ("exists", "compiles")]
    assert behavioural, "the pset must have behavioural checks"
    assert all(c["blocked"] for c in behavioural)
    assert all(c["cause"] == "compilation failed" for c in behavioural)


def test_hidden_checks_expose_name_only_in_response(tmp_path: Path) -> None:
    problem_json = json.loads((REPO_PROBLEMS / PSET_ID / "problem.json").read_text())
    hidden = [t for t in problem_json["tests"] if t["visibility"] == "hidden"]
    assert hidden, "fixture must contain hidden tests"

    with _client(tmp_path) as client:
        body = client.post(
            f"/api/problems/{PSET_ID}/submit",
            json={"source": "int main(void){return 0;}"},
        ).json()

    hidden_ids = {t["id"] for t in hidden}
    raw = json.dumps(body)
    for check in body["checks"]:
        if check["name"] in hidden_ids:
            assert check["visibility"] == "hidden"
            assert check["data"] == {}
    # No hidden stdin or expected output may appear anywhere in the payload.
    for test in hidden:
        assert test["expected_stdout"].strip() not in raw
        stdin = test["stdin"].strip()
        if len(stdin) >= 3:
            assert stdin not in raw


def test_submitting_to_unknown_problem_returns_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/problems/nope/submit", json={"source": STARTER})

    assert response.status_code == 404


# --- hints -----------------------------------------------------------------


def test_first_hint_is_level_one(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"hints_used": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["level"] == 1
    assert body["text"]
    assert body["source"] == "stored"
    assert body["next_level"] == 2


def test_hints_advance_one_level(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"hints_used": 2}).json()

    assert body["level"] == 3
    assert body["next_level"] == 4


def test_exhausted_hints_return_409(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"hints_used": 5})

    assert response.status_code == 409


def test_specific_level_can_be_requested(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"level": 4}).json()

    assert body["level"] == 4


def test_level_five_is_flagged_as_solution_reveal(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"level": 5}).json()

    assert body["is_solution_reveal"] is True


def test_invalid_level_is_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"level": 0}).status_code == 422
        assert client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"level": 9}).status_code == 422


def test_hint_count_is_bounded(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={"hints_used": 99}).status_code == 422


def test_hint_works_without_an_ai_provider(tmp_path: Path) -> None:
    """Stored hints must serve offline practice (design decision #4)."""
    with _client(tmp_path) as client:
        response = client.post(f"/api/problems/{EXAMPLE_ID}/hint", json={})

    assert response.status_code == 200


def test_generated_hint_uses_provider_when_no_stored_hint(tmp_path: Path) -> None:
    """When a level has no stored hint, the provider is consulted."""
    problems_dir = tmp_path / "problems"
    package = problems_dir / "partial-hints"
    (package / "starter").mkdir(parents=True)
    (package / "reference").mkdir(parents=True)
    (package / "statement.md").write_text("# Problem\n\nRead two integers.")
    (package / "reference" / "main.c").write_text("int main(void){return 0;}\n")
    # Only levels 1 and 2 exist, so level 3 must be generated.
    (package / "problem.json").write_text(json.dumps({
        "id": "partial-hints",
        "title": "Partial Hints",
        "tests": [
            {"id": "a", "name": "A", "visibility": "public", "stdin": "", "expected_stdout": ""},
        ],
        "hints": [{"level": 1, "text": "one"}, {"level": 2, "text": "two"}],
    }))

    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "cpractice.db",
        problems_dir=problems_dir,
        workspaces_dir=tmp_path / "workspaces",
    )
    app = create_app(settings)
    provider = MockProvider(responses="generated guidance")

    with TestClient(app) as client:
        app.state.hint_service = HintService(provider)
        response = client.post("/api/problems/partial-hints/hint", json={"level": 3})

    assert response.status_code == 200
    assert response.json()["source"] == "generated"
    assert response.json()["text"] == "generated guidance"


# --- solution reveal -------------------------------------------------------


def test_solution_requires_explicit_confirmation(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(f"/api/problems/{EXAMPLE_ID}/solution", json={})

    assert response.status_code == 400
    assert "confirm" in response.json()["detail"].lower()


def test_confirmed_solution_is_returned(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            f"/api/problems/{EXAMPLE_ID}/solution", json={"confirm": True}
        )

    assert response.status_code == 200
    body = response.json()
    assert "scanf" in body["reference_solution"]
    assert body["problem_id"] == EXAMPLE_ID


def test_solution_reveal_is_not_part_of_normal_problem_view(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get(f"/api/problems/{EXAMPLE_ID}").json()

    assert "reference_solution" not in body
