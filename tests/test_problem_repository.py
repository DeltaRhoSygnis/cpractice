"""Tests for the problem repository (loading packages from disk)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.grading.evaluator import Evaluator, GradingConfig
from app.storage.problem_repository import (
    METADATA_FILENAME,
    ProblemNotFoundError,
    ProblemRepository,
    ProblemValidationError,
)

EXAMPLE_ID = "c-sum-two-integers"


@pytest.fixture()
def repo() -> ProblemRepository:
    # Uses the real example package shipped with the repository.
    return ProblemRepository(Path(__file__).resolve().parent.parent / "problems")


def _write_package(root: Path, problem_id: str, metadata: dict, statement: str = "# S") -> Path:
    package = root / problem_id
    (package / "starter").mkdir(parents=True)
    (package / "reference").mkdir(parents=True)
    (package / METADATA_FILENAME).write_text(json.dumps(metadata))
    (package / "statement.md").write_text(statement)
    (package / "starter" / "main.c").write_text("/* starter */\n")
    (package / "reference" / "main.c").write_text("int main(void){return 0;}\n")
    return package


def test_lists_the_example_problem(repo: ProblemRepository) -> None:
    assert EXAMPLE_ID in repo.list_ids()


def test_loads_example_package(repo: ProblemRepository) -> None:
    problem = repo.load(EXAMPLE_ID)

    assert problem.id == EXAMPLE_ID
    assert problem.title
    assert problem.statement_md
    assert problem.starter_code
    assert problem.reference_solution
    assert len(problem.tests) == 6
    assert len(problem.public_tests) == 3
    assert len(problem.hidden_tests) == 3


def test_example_package_reference_passes_all_tests(repo: ProblemRepository) -> None:
    problem = repo.load(EXAMPLE_ID)
    config = GradingConfig(
        standard=problem.metadata.compiler.standard,
        timeout_ms=problem.metadata.time_limit_ms,
        memory_limit_mb=problem.metadata.memory_limit_mb,
        default_comparison=problem.metadata.comparison,
    )

    report = Evaluator(config).grade_source(
        problem.reference_solution,
        problem.tests,
        problem_id=problem.id,
    )

    assert report.compilation.success is True
    assert report.all_passed is True, [t.test_id for t in report.tests if not t.passed]


def test_example_package_starter_does_not_pass(repo: ProblemRepository) -> None:
    problem = repo.load(EXAMPLE_ID)
    config = GradingConfig(
        standard=problem.metadata.compiler.standard,
        timeout_ms=problem.metadata.time_limit_ms,
        memory_limit_mb=problem.metadata.memory_limit_mb,
        default_comparison=problem.metadata.comparison,
    )

    report = Evaluator(config).grade_source(problem.starter_code, problem.tests)

    assert report.all_passed is False


def test_example_package_has_full_hint_ladder(repo: ProblemRepository) -> None:
    problem = repo.load(EXAMPLE_ID)

    assert problem.max_hint_level == 5
    for level in range(1, 6):
        assert problem.hint_for_level(level) is not None


def test_missing_problem_raises_not_found(repo: ProblemRepository) -> None:
    with pytest.raises(ProblemNotFoundError):
        repo.load("no-such-problem")


def test_exists_reports_presence(repo: ProblemRepository) -> None:
    assert repo.exists(EXAMPLE_ID) is True
    assert repo.exists("no-such-problem") is False


def test_invalid_id_is_rejected(repo: ProblemRepository) -> None:
    for bad in ["..", "../etc", "/etc/passwd", "Upper", "has space", ""]:
        with pytest.raises(ProblemNotFoundError):
            repo.load(bad)


def test_path_traversal_cannot_escape_root(tmp_path: Path) -> None:
    outside = tmp_path / "secret"
    outside.mkdir()
    (outside / METADATA_FILENAME).write_text('{"id":"secret","title":"Secret"}')
    repo = ProblemRepository(tmp_path)

    with pytest.raises(ProblemNotFoundError):
        repo.load("../secret")


def test_invalid_metadata_raises_validation_error(tmp_path: Path) -> None:
    _write_package(tmp_path, "bad-problem", {"id": "bad-problem", "title": ""})
    repo = ProblemRepository(tmp_path)

    with pytest.raises(ProblemValidationError):
        repo.load("bad-problem")


def test_missing_statement_raises_validation_error(tmp_path: Path) -> None:
    package = _write_package(tmp_path, "no-statement", {"id": "no-statement", "title": "T"})
    (package / "statement.md").unlink()
    repo = ProblemRepository(tmp_path)

    with pytest.raises(ProblemValidationError):
        repo.load("no-statement")


def test_content_keys_are_not_treated_as_metadata(tmp_path: Path) -> None:
    """tests/hints/solution_explanation live in problem.json with metadata."""
    metadata = {
        "id": "with-content",
        "title": "With Content",
        "tests": [{"id": "t1", "name": "T1", "stdin": "", "expected_stdout": ""}],
        "hints": [{"level": 1, "text": "hint"}],
        "solution_explanation": "explain",
    }
    _write_package(tmp_path, "with-content", metadata)
    problem = ProblemRepository(tmp_path).load("with-content")

    assert len(problem.tests) == 1
    assert len(problem.hints) == 1
    assert problem.solution_explanation == "explain"


def test_load_all_skips_invalid_packages(tmp_path: Path) -> None:
    _write_package(tmp_path, "good-problem", {"id": "good-problem", "title": "Good"})
    _write_package(tmp_path, "bad-problem", {"id": "bad-problem", "title": ""})
    repo = ProblemRepository(tmp_path)

    ids = [p.id for p in repo.load_all()]

    assert ids == ["good-problem"]


def test_list_ids_on_missing_root_is_empty(tmp_path: Path) -> None:
    assert ProblemRepository(tmp_path / "does-not-exist").list_ids() == []
