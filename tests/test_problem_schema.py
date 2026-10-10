"""Tests for problem package schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.problem import (
    Difficulty,
    Hint,
    Problem,
    ProblemMetadata,
    ProblemStatus,
)
from app.schemas.test_case import ComparisonMode, TestCase, Visibility


def _metadata(**overrides) -> dict:
    base = {"id": "demo-problem", "title": "Demo"}
    base.update(overrides)
    return base


def test_minimal_metadata_defaults() -> None:
    meta = ProblemMetadata(**_metadata())

    assert meta.schema_version == "1.0"
    assert meta.language == "c"
    assert meta.difficulty is Difficulty.BEGINNER
    assert meta.status is ProblemStatus.DRAFT
    assert meta.comparison is ComparisonMode.EXACT_NORMALIZED
    assert meta.entrypoint == "main.c"


def test_problem_id_must_be_lowercase_slug() -> None:
    with pytest.raises(ValidationError):
        ProblemMetadata(**_metadata(id="Not Valid Id"))


def test_entrypoint_must_be_a_c_file() -> None:
    assert ProblemMetadata(**_metadata(entrypoint="solution.c")).entrypoint == "solution.c"
    with pytest.raises(ValidationError):
        ProblemMetadata(**_metadata(entrypoint="solution.py"))


def test_compiler_standard_is_restricted() -> None:
    assert ProblemMetadata(**_metadata(compiler={"standard": "c17"})).compiler.standard == "c17"
    with pytest.raises(ValidationError):
        ProblemMetadata(**_metadata(compiler={"standard": "c++20"}))


def test_limits_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ProblemMetadata(**_metadata(time_limit_ms=0))
    with pytest.raises(ValidationError):
        ProblemMetadata(**_metadata(memory_limit_mb=0))


def test_blank_topic_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProblemMetadata(**_metadata(topics=["loops", "  "]))


def test_metadata_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProblemMetadata(**_metadata(unexpected="x"))


def test_problem_requires_a_statement() -> None:
    with pytest.raises(ValidationError):
        Problem(metadata=ProblemMetadata(**_metadata()), statement_md="")


def test_duplicate_test_ids_are_rejected() -> None:
    tests = [
        TestCase(id="same", name="A"),
        TestCase(id="same", name="B"),
    ]
    with pytest.raises(ValidationError):
        Problem(metadata=ProblemMetadata(**_metadata()), statement_md="x", tests=tests)


def test_duplicate_hint_levels_are_rejected() -> None:
    hints = [Hint(level=1, text="a"), Hint(level=1, text="b")]
    with pytest.raises(ValidationError):
        Problem(metadata=ProblemMetadata(**_metadata()), statement_md="x", hints=hints)


def test_public_and_hidden_test_partitioning() -> None:
    tests = [
        TestCase(id="pub", name="Public"),
        TestCase(id="sec", name="Hidden", visibility=Visibility.HIDDEN),
    ]
    problem = Problem(metadata=ProblemMetadata(**_metadata()), statement_md="x", tests=tests)

    assert [t.id for t in problem.public_tests] == ["pub"]
    assert [t.id for t in problem.hidden_tests] == ["sec"]


def test_hint_lookup_and_max_level() -> None:
    hints = [Hint(level=1, text="one"), Hint(level=3, text="three")]
    problem = Problem(metadata=ProblemMetadata(**_metadata()), statement_md="x", hints=hints)

    assert problem.hint_for_level(1).text == "one"
    assert problem.hint_for_level(3).text == "three"
    assert problem.hint_for_level(2) is None
    assert problem.max_hint_level == 3


def test_hint_level_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Hint(level=0, text="too low")
    with pytest.raises(ValidationError):
        Hint(level=6, text="too high")


def test_convenience_accessors() -> None:
    problem = Problem(
        metadata=ProblemMetadata(**_metadata(id="my-problem", title="My Title")),
        statement_md="x",
    )

    assert problem.id == "my-problem"
    assert problem.title == "My Title"
