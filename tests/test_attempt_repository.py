"""Tests for attempt persistence and progress reporting."""

from __future__ import annotations

from pathlib import Path

from app.grading.evaluator import Evaluator
from app.schemas.grading import GradingReport
from app.schemas.problem import Problem, ProblemMetadata
from app.schemas.test_case import TestCase, Visibility
from app.storage.attempt_repository import AttemptRepository, ProblemIndex
from app.storage.database import Database

SUM = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""

# A submission that is wrong for every test: it subtracts instead of adding.
SUBTRACT = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a-b);return 0;}
"""

# The hidden test's real expected output (1000 + 8191919). It must never be
# stored in the database or surface anywhere.
SECRET = "8192919"


def _tests() -> list[TestCase]:
    return [
        TestCase(id="pub", name="Public", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(
            id="sec",
            name="Hidden",
            visibility=Visibility.HIDDEN,
            stdin="1000 8191919\n",
            expected_stdout=SECRET + "\n",
        ),
    ]


def _report(source: str) -> GradingReport:
    return Evaluator().grade_source(source, _tests(), problem_id="p")


def _repository(tmp_path: Path) -> AttemptRepository:
    database = Database(tmp_path / "db.sqlite")
    # The attempts table references problems, so index the problem first.
    index = ProblemIndex(database)
    index.upsert(
        Problem(metadata=ProblemMetadata(id="p", title="P", topics=["io"]),
                statement_md="x", tests=_tests()),
        "/tmp/p",
    )
    return AttemptRepository(database)


# --- recording -------------------------------------------------------------


def test_record_returns_an_id(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    attempt_id = repository.record(_report(SUM), problem_id="p")

    assert attempt_id > 0


def test_recorded_attempt_is_readable(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    attempt_id = repository.record(_report(SUM), problem_id="p")

    attempt = repository.get(attempt_id)

    assert attempt is not None
    assert attempt.problem_id == "p"
    assert attempt.passed == 2
    assert attempt.total == 2
    assert attempt.succeeded is True
    assert attempt.verdict == "passed"


def test_test_results_are_persisted(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    attempt_id = repository.record(_report(SUM), problem_id="p")

    results = repository.test_results(attempt_id)

    assert {r["test_id"] for r in results} == {"pub", "sec"}


def test_hidden_test_detail_is_not_stored(tmp_path: Path) -> None:
    """Hidden diagnostics must not be persisted, in case history is exported."""
    buggy = SUBTRACT
    repository = _repository(tmp_path)
    attempt_id = repository.record(_report(buggy), problem_id="p")

    results = repository.test_results(attempt_id)
    hidden = [r for r in results if r["test_id"] == "sec"][0]

    assert hidden["detail"] == ""
    assert SECRET not in str(results)


def test_failed_attempt_records_verdict(tmp_path: Path) -> None:
    buggy = SUBTRACT
    repository = _repository(tmp_path)

    attempt = repository.get(repository.record(_report(buggy), problem_id="p"))

    assert attempt.verdict == "all_failed"
    assert attempt.passed == 0


def test_compilation_failure_is_recorded(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    attempt = repository.get(
        repository.record(_report('int main(void){ printf("x" return 0; }'), problem_id="p")
    )

    assert attempt.compilation_ok is False
    assert attempt.verdict == "compilation_failed"


def test_hints_used_is_recorded(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    attempt_id = repository.record(_report(SUM), problem_id="p", hints_used=3)

    assert repository.get(attempt_id).hints_used == 3


def test_recent_returns_newest_first(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first = repository.record(_report(SUM), problem_id="p")
    second = repository.record(_report(SUM), problem_id="p")

    recent = repository.recent()

    assert [a.id for a in recent][:2] == [second, first]


def test_recent_can_filter_by_problem(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")
    index = ProblemIndex(database)
    for pid in ("p", "q"):
        index.upsert(
            Problem(metadata=ProblemMetadata(id=pid, title=pid), statement_md="x", tests=_tests()),
            f"/tmp/{pid}",
        )
    repository = AttemptRepository(database)
    repository.record(_report(SUM), problem_id="p")
    repository.record(_report(SUM), problem_id="q")

    only_q = repository.recent(problem_id="q")

    assert [a.problem_id for a in only_q] == ["q"]


def test_recent_limit_is_respected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    for _ in range(5):
        repository.record(_report(SUM), problem_id="p")

    assert len(repository.recent(limit=2)) == 2


def test_get_unknown_attempt_returns_none(tmp_path: Path) -> None:
    assert _repository(tmp_path).get(9999) is None


# --- progress --------------------------------------------------------------


def test_progress_on_empty_history(tmp_path: Path) -> None:
    progress = _repository(tmp_path).progress()

    assert progress["attempts"] == 0
    assert progress["problems_solved"] == 0
    assert progress["test_pass_rate"] is None


def test_progress_counts_attempts_and_solves(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.record(_report(SUM), problem_id="p")

    progress = repository.progress()

    assert progress["attempts"] == 1
    assert progress["problems_solved"] == 1
    assert progress["distinct_problems"] == 1


def test_progress_reports_a_pass_rate_over_observed_tests(tmp_path: Path) -> None:
    buggy = SUBTRACT
    repository = _repository(tmp_path)
    repository.record(_report(buggy), problem_id="p")

    progress = repository.progress()

    # Reported as an observed ratio, not a claim about ability.
    assert progress["tests_total"] == 2
    assert progress["tests_passed"] == 0
    assert progress["test_pass_rate"] == 0.0


def test_progress_lists_failure_categories(tmp_path: Path) -> None:
    buggy = SUBTRACT
    repository = _repository(tmp_path)
    repository.record(_report(buggy), problem_id="p")

    progress = repository.progress()

    assert progress["failure_categories"]


def test_progress_lists_weak_topics(tmp_path: Path) -> None:
    buggy = SUBTRACT
    repository = _repository(tmp_path)
    repository.record(_report(buggy), problem_id="p")

    progress = repository.progress()

    assert progress["weak_topics"]
    assert progress["weak_topics"][0]["failures"] >= 1


def test_progress_never_leaks_hidden_expected_values(tmp_path: Path) -> None:
    buggy = SUBTRACT
    repository = _repository(tmp_path)
    repository.record(_report(buggy), problem_id="p")

    assert SECRET not in str(repository.progress())


# --- problem index ---------------------------------------------------------


def test_index_upsert_is_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")
    index = ProblemIndex(database)
    problem = Problem(metadata=ProblemMetadata(id="p", title="P"), statement_md="x", tests=_tests())

    index.upsert(problem, "/tmp/p")
    index.upsert(problem, "/tmp/p")

    assert len(index.all()) == 1


def test_index_updates_existing_row(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")
    index = ProblemIndex(database)
    index.upsert(Problem(metadata=ProblemMetadata(id="p", title="Old"), statement_md="x"), "/tmp/p")
    index.upsert(Problem(metadata=ProblemMetadata(id="p", title="New"), statement_md="x"), "/tmp/p")

    rows = index.all()

    assert rows[0]["title"] == "New"
