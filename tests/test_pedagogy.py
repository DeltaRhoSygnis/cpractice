"""Tests for the pedagogical schema and backwards compatibility."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.pedagogy import (
    MIN_REASONING_MOVES,
    DifficultyProfile,
    ExerciseRole,
    Pedagogy,
)
from app.schemas.problem import Problem, ProblemMetadata
from app.schemas.test_case import TestCase
from app.storage.problem_repository import ProblemRepository

REPO_PROBLEMS = Path(__file__).resolve().parent.parent / "app" / "seed_problems"


# --- difficulty profile ----------------------------------------------------


def test_difficulty_profile_defaults_to_zero() -> None:
    assert DifficultyProfile().total == 0


def test_difficulty_profile_is_bounded() -> None:
    with pytest.raises(ValidationError):
        DifficultyProfile(reasoning_steps=4)
    with pytest.raises(ValidationError):
        DifficultyProfile(state_management=-1)


def test_difficulty_profile_totals() -> None:
    profile = DifficultyProfile(reasoning_steps=2, state_management=3)

    assert profile.total == 5


def test_difficulty_profile_rejects_unknown_dimensions() -> None:
    with pytest.raises(ValidationError):
        DifficultyProfile(intelligence=3)  # type: ignore[call-arg]


# --- pedagogy --------------------------------------------------------------


def test_pedagogy_defaults_to_core_reasoning() -> None:
    assert Pedagogy().exercise_role is ExerciseRole.CORE_REASONING


def test_required_move_counts_by_role() -> None:
    assert Pedagogy(exercise_role=ExerciseRole.DIAGNOSTIC_WARMUP).required_move_count() == 1
    assert Pedagogy(exercise_role=ExerciseRole.CORE_REASONING).required_move_count() == 2
    assert Pedagogy(exercise_role=ExerciseRole.CHALLENGE).required_move_count() == 3


def test_every_role_declares_a_minimum() -> None:
    for role in ExerciseRole:
        assert role in MIN_REASONING_MOVES


def test_warmup_predicate() -> None:
    assert Pedagogy(exercise_role=ExerciseRole.DIAGNOSTIC_WARMUP).is_warmup is True
    assert Pedagogy(exercise_role=ExerciseRole.CORE_REASONING).is_warmup is False


def test_pedagogy_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Pedagogy(unexpected="x")  # type: ignore[call-arg]


def test_author_only_outline_is_stored() -> None:
    pedagogy = Pedagogy(solution_outline="loop n times, track the best score")

    assert pedagogy.solution_outline


# --- test-case provenance --------------------------------------------------


def test_test_case_carries_requirement_and_misconception_tags() -> None:
    test = TestCase(
        id="t",
        name="T",
        requirement_ids=["REQ-BOUNDARY-02"],
        misconception_ids=["MIS-OFF-BY-ONE"],
    )

    assert test.is_tagged is True
    assert test.is_boundary is True


def test_untagged_test_reports_as_such() -> None:
    assert TestCase(id="t", name="T").is_tagged is False


def test_test_rationale_is_optional() -> None:
    assert TestCase(id="t", name="T").rationale == ""


# --- problem integration ---------------------------------------------------


def test_problem_without_pedagogy_is_valid() -> None:
    """Legacy packages must keep loading unchanged."""
    problem = Problem(metadata=ProblemMetadata(id="p", title="P"), statement_md="# P")

    assert problem.pedagogy is None


def test_problem_with_pedagogy_is_valid() -> None:
    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="# P",
        pedagogy=Pedagogy(primary_objective="derive loop bounds"),
    )

    assert problem.pedagogy.primary_objective == "derive loop bounds"


# --- backwards compatibility with shipped problems -------------------------


def test_shipped_example_still_loads() -> None:
    problem = ProblemRepository(REPO_PROBLEMS).load("c-sum-two-integers")

    assert problem.id == "c-sum-two-integers"
    assert problem.tests
    # Authored before the pedagogy schema existed.
    assert problem.pedagogy is None


def test_all_shipped_problems_load() -> None:
    problems = ProblemRepository(REPO_PROBLEMS).load_all()

    assert problems
    for problem in problems:
        assert problem.statement_md


def test_legacy_package_json_round_trips(tmp_path: Path) -> None:
    """A package written before pedagogy existed must reload identically."""
    package = tmp_path / "legacy"
    (package / "starter").mkdir(parents=True)
    (package / "statement.md").write_text("# Legacy")
    (package / "problem.json").write_text(json.dumps({
        "id": "legacy",
        "title": "Legacy Problem",
        "tests": [{"id": "a", "name": "A", "stdin": "1\n", "expected_stdout": "1\n"}],
    }))

    problem = ProblemRepository(tmp_path).load("legacy")

    assert problem.id == "legacy"
    assert problem.pedagogy is None
    assert problem.tests[0].requirement_ids == []


def test_pedagogy_persists_and_reloads(tmp_path: Path) -> None:
    package = tmp_path / "with-pedagogy"
    (package / "starter").mkdir(parents=True)
    (package / "statement.md").write_text("# With Pedagogy")
    (package / "problem.json").write_text(json.dumps({
        "id": "with-pedagogy",
        "title": "With Pedagogy",
        "tests": [{"id": "a", "name": "A", "stdin": "1\n", "expected_stdout": "1\n",
                   "requirement_ids": ["REQ-1"]}],
        "pedagogy": {
            "primary_objective": "derive loop bounds",
            "exercise_role": "challenge",
            "target_reasoning_moves": ["a", "b", "c"],
        },
    }))

    problem = ProblemRepository(tmp_path).load("with-pedagogy")

    assert problem.pedagogy is not None
    assert problem.pedagogy.exercise_role is ExerciseRole.CHALLENGE
    assert problem.tests[0].requirement_ids == ["REQ-1"]
