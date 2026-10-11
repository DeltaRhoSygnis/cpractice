"""Tests for the predict-then-verify mechanic (spec S6, plan Phase 5).

The guarantee under test is twofold:

* the diff is a pure string comparison of three known values, reusing the
  platform comparator; and
* a prediction is **never graded** — it cannot change a verdict or a pass count.

Storage tests cover the additive ``predicted_stdout`` migration, its
idempotency, and backwards compatibility with rows written before it existed.
"""

from __future__ import annotations

from pathlib import Path

from app.feedback.prediction import (
    PredictionDiff,
    SampleRun,
    build_prediction_diff,
    prediction_to_payload,
    select_sample_test,
)
from app.feedback.reporter import ResultReporter
from app.grading.evaluator import Evaluator
from app.schemas.grading import GradingReport
from app.schemas.problem import (
    PredictionPlan,
    Problem,
    ProblemKind,
    ProblemMetadata,
)
from app.schemas.test_case import TestCase, Visibility
from app.storage.attempt_repository import AttemptRepository, ProblemIndex
from app.storage.database import Database

# --- fixtures --------------------------------------------------------------

# Adds two integers. Correct for the sample; the hidden test catches the bug.
SUM = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""

# Subtracts instead of adding: wrong for every test, including the sample.
SUBTRACT = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a-b);return 0;}
"""


def _tests(*, with_misconception: bool = True) -> list[TestCase]:
    return [
        TestCase(
            id="sample",
            name="Sample",
            stdin="1 2\n",
            expected_stdout="3\n",
            misconception_ids=["MIS-OFF-BY-ONE"] if with_misconception else [],
        ),
        TestCase(
            id="hidden",
            name="Hidden",
            visibility=Visibility.HIDDEN,
            stdin="10 20\n",
            expected_stdout="30\n",
        ),
    ]


def _problem(*, with_misconception: bool = True, sample_test_id: str | None = "sample") -> Problem:
    return Problem(
        metadata=ProblemMetadata(
            id="p",
            title="P",
            kind=ProblemKind.PROBLEM_SET,
            prediction=PredictionPlan(enabled=True, sample_test_id=sample_test_id),
        ),
        statement_md="# Add two numbers",
        tests=_tests(with_misconception=with_misconception),
    )


def _report(source: str, tests: list[TestCase] | None = None) -> GradingReport:
    return Evaluator().grade_source(source, tests or _tests(), problem_id="p")


# --- diff: match / mismatch ------------------------------------------------


def test_match_with_expected() -> None:
    diff = build_prediction_diff(
        problem=_problem(), predicted_stdout="3\n", actual_stdout="3\n"
    )

    assert diff.provided is True
    assert diff.sample_test_id == "sample"
    assert diff.expected == "3\n"
    assert diff.predicted == "3\n"
    assert diff.actual == "3\n"
    assert diff.matches_expected is True
    assert diff.matches_actual is True
    assert diff.note is None


def test_mismatch_against_expected_and_actual() -> None:
    diff = build_prediction_diff(
        problem=_problem(), predicted_stdout="4\n", actual_stdout="5\n"
    )

    assert diff.matches_expected is False
    assert diff.matches_actual is False


def test_predicted_equals_actual_but_not_expected() -> None:
    """The learner correctly predicted their own (wrong) program's output."""
    diff = build_prediction_diff(
        problem=_problem(), predicted_stdout="5\n", actual_stdout="5\n"
    )

    assert diff.matches_expected is False
    assert diff.matches_actual is True


def test_normalisation_is_shared_with_the_comparator() -> None:
    """A missing final newline must not register as a mismatch."""
    diff = build_prediction_diff(
        problem=_problem(), predicted_stdout="3", actual_stdout="3\n"
    )

    assert diff.matches_expected is True
    assert diff.matches_actual is True


# --- diff: absent ----------------------------------------------------------


def test_no_prediction_is_omitted() -> None:
    diff = build_prediction_diff(problem=_problem(), predicted_stdout=None)

    assert diff == PredictionDiff(provided=False)
    assert diff.sample_test_id is None
    assert diff.expected is None


def test_empty_prediction_is_treated_as_absent() -> None:
    diff = build_prediction_diff(problem=_problem(), predicted_stdout="")

    assert diff.provided is False


def test_payload_for_missing_prediction_has_only_provided_flag() -> None:
    payload = prediction_to_payload(
        build_prediction_diff(problem=_problem(), predicted_stdout=None)
    )

    assert payload == {"provided": False}


def test_payload_is_json_safe() -> None:
    import json

    payload = prediction_to_payload(
        build_prediction_diff(
            problem=_problem(), predicted_stdout="4\n", actual_stdout="5\n"
        )
    )

    # Round-trips through JSON, so the reporter can embed it verbatim.
    assert json.loads(json.dumps(payload)) == payload


# --- sample selection ------------------------------------------------------


def test_declared_sample_test_is_used() -> None:
    assert select_sample_test(_problem(sample_test_id="sample")).id == "sample"


def test_hidden_sample_id_falls_back_to_first_public() -> None:
    """Hidden data must never be exposed as a prediction sample."""
    problem = _problem(sample_test_id="hidden")

    assert select_sample_test(problem).visibility is Visibility.PUBLIC
    assert select_sample_test(problem).id == "sample"


def test_no_public_test_yields_no_sample() -> None:
    hidden_only = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        tests=[
            TestCase(
                id="hidden",
                name="Hidden",
                visibility=Visibility.HIDDEN,
                expected_stdout="1\n",
            )
        ],
    )

    assert select_sample_test(hidden_only) is None


def test_prediction_without_sample_still_records_prediction() -> None:
    hidden_only = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        tests=[TestCase(id="h", name="H", visibility=Visibility.HIDDEN)],
    )

    diff = build_prediction_diff(problem=hidden_only, predicted_stdout="3\n")

    assert diff.provided is True
    assert diff.sample_test_id is None
    assert diff.expected is None


# --- actual-output availability --------------------------------------------


def test_unavailable_actual_leaves_matches_actual_none() -> None:
    diff = build_prediction_diff(problem=_problem(), predicted_stdout="3\n")

    assert diff.actual is None
    assert diff.matches_actual is None


def test_sample_run_marks_actual_unavailable() -> None:
    diff = build_prediction_diff(
        problem=_problem(),
        predicted_stdout="3\n",
        sample_run=SampleRun(stdout="", available=False),
    )

    assert diff.actual == ""
    assert diff.matches_actual is None


# --- misconception note ----------------------------------------------------


def test_note_appears_when_declared_id_applies() -> None:
    problem = _problem(with_misconception=True)
    report = _report(SUBTRACT, problem.tests)

    diff = build_prediction_diff(
        problem=problem,
        predicted_stdout="3\n",
        actual_stdout="-1\n",
        report=report,
    )

    assert diff.note is not None
    assert "MIS-OFF-BY-ONE" in diff.note


def test_note_never_claims_the_prediction_as_the_observed_output() -> None:
    """Regression: when no output was measured, the note must not invent one.

    A compilation failure (or crash/timeout) leaves ``actual`` unavailable. The
    note must say the prediction could not be checked rather than echoing the
    prediction back as if the program had produced it.
    """
    problem = _problem(with_misconception=True)
    # subtract fails to compile -> the sample fails with no observed output
    report = _report("this is not valid C", problem.tests)

    diff = build_prediction_diff(
        problem=problem,
        predicted_stdout="3\n",
        report=report,
    )

    assert diff.actual is None
    assert diff.note is not None
    # Must not fabricate an observation.
    assert "and got 3" not in diff.note
    assert "MIS-OFF-BY-ONE" in diff.note


def test_no_note_when_no_declared_id() -> None:
    problem = _problem(with_misconception=False)
    report = _report(SUBTRACT, problem.tests)

    diff = build_prediction_diff(
        problem=problem,
        predicted_stdout="3\n",
        actual_stdout="-1\n",
        report=report,
    )

    assert diff.note is None


def test_no_note_when_code_actually_passed_the_sample() -> None:
    """A wrong prediction with correct code is not a misconception."""
    problem = _problem(with_misconception=True)
    report = _report(SUM, problem.tests)

    diff = build_prediction_diff(
        problem=problem,
        predicted_stdout="4\n",
        actual_stdout="3\n",
        report=report,
    )

    assert diff.matches_actual is False  # predicted a different value
    assert diff.note is None  # but the code passed, so no misconception note


def test_note_cites_only_declared_ids() -> None:
    problem = _problem(with_misconception=True)
    report = _report(SUBTRACT, problem.tests)

    diff = build_prediction_diff(
        problem=problem, predicted_stdout="3\n", actual_stdout="-1\n", report=report
    )

    # The note names a declared id and introduces no free-form diagnosis.
    assert diff.note is not None
    assert "declares" in diff.note


# --- the central invariant: prediction is never graded ---------------------


def test_prediction_does_not_change_verdict_or_counts() -> None:
    problem = _problem()
    report = _report(SUBTRACT, problem.tests)

    # Same report, with and without a prediction. The diff reads the report; it
    # must never write back to it.
    without = prediction_to_payload(
        build_prediction_diff(problem=problem, predicted_stdout=None)
    )
    with_prediction = prediction_to_payload(
        build_prediction_diff(
            problem=problem, predicted_stdout="3\n", actual_stdout="-1\n", report=report
        )
    )

    assert without == {"provided": False}
    assert with_prediction["provided"] is True

    # The report is byte-for-byte unchanged by building the diff.
    assert report.passed_count == 0
    assert report.total_count == 2
    assert report.all_passed is False
    assert ResultReporter().verdict(report) == "all_failed"


def test_verdict_is_identical_with_and_without_prediction() -> None:
    problem = _problem()
    report = _report(SUM, problem.tests)

    verdict_before = ResultReporter().verdict(report)

    # Build diffs for several predictions, including a wrong one.
    for predicted in ("3\n", "4\n", "totally wrong", ""):
        build_prediction_diff(
            problem=problem,
            predicted_stdout=predicted or None,
            actual_stdout="3\n",
            report=report,
        )

    assert ResultReporter().verdict(report) == verdict_before
    assert report.passed_count == 2
    assert report.total_count == 2


def test_prediction_diff_exposes_no_grading_fields() -> None:
    """The data structure simply has no field a grade could live in."""
    fields = set(PredictionDiff.__dataclass_fields__)

    assert "verdict" not in fields
    assert "passed" not in fields
    assert "score" not in fields


# --- storage: migration and persistence ------------------------------------


def _repository(tmp_path: Path) -> AttemptRepository:
    database = Database(tmp_path / "db.sqlite")
    ProblemIndex(database).upsert(
        Problem(metadata=ProblemMetadata(id="p", title="P"), statement_md="x", tests=_tests()),
        "/tmp/p",
    )
    return AttemptRepository(database)


def _columns(database: Database, table: str) -> set[str]:
    return {
        row["name"] for row in database.connect().execute(f"PRAGMA table_info({table})")
    }


def test_migration_adds_predicted_stdout_column(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")

    assert "predicted_stdout" in _columns(database, "attempts")


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    Database(path)
    # Re-opening runs _initialise again; a second ALTER must not be attempted.
    second = Database(path)

    assert "predicted_stdout" in _columns(second, "attempts")


def test_legacy_database_without_column_is_upgraded(tmp_path: Path) -> None:
    """A database created before the column existed keeps working."""
    import sqlite3

    path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE attempts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id     TEXT NOT NULL,
            created_at     TEXT NOT NULL DEFAULT (datetime('now')),
            compilation_ok INTEGER NOT NULL DEFAULT 0,
            passed         INTEGER NOT NULL DEFAULT 0,
            total          INTEGER NOT NULL DEFAULT 0,
            verdict        TEXT NOT NULL,
            duration_ms    INTEGER NOT NULL DEFAULT 0,
            hints_used     INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        "INSERT INTO attempts (problem_id, verdict) VALUES ('p', 'passed')"
    )
    connection.commit()
    connection.close()

    database = Database(path)

    assert "predicted_stdout" in _columns(database, "attempts")
    # The pre-existing row reads back with the column NULL.
    row = database.connect().execute("SELECT * FROM attempts").fetchone()
    assert row["predicted_stdout"] is None


def test_prediction_round_trips(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    report = _report(SUBTRACT, _tests())

    attempt_id = repository.record(
        report, problem_id="p", predicted_stdout="3\n"
    )

    attempt = repository.get(attempt_id)
    assert attempt is not None
    assert attempt.predicted_stdout == "3\n"


def test_prediction_defaults_to_none(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    report = _report(SUM, _tests())

    attempt_id = repository.record(report, problem_id="p")

    attempt = repository.get(attempt_id)
    assert attempt is not None
    assert attempt.predicted_stdout is None


def test_prediction_does_not_change_stored_verdict(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    report = _report(SUBTRACT, _tests())

    plain = repository.get(repository.record(report, problem_id="p"))
    predicted = repository.get(
        repository.record(report, problem_id="p", predicted_stdout="3\n")
    )

    assert plain is not None and predicted is not None
    assert plain.verdict == predicted.verdict
    assert plain.passed == predicted.passed
    assert plain.total == predicted.total


def test_test_results_do_not_expose_the_prediction(tmp_path: Path) -> None:
    """The prediction lives on the attempt, not in per-test results."""
    repository = _repository(tmp_path)
    attempt_id = repository.record(
        _report(SUM, _tests()), problem_id="p", predicted_stdout="3\n"
    )

    results = repository.test_results(attempt_id)

    assert all("predicted_stdout" not in row for row in results)
