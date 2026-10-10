"""Tests for the problem quality gate.

The gate must reject a problem whose reference fails, whose tests are absent,
or whose limits are unreasonable — and it must never claim correctness it
cannot verify.
"""

from __future__ import annotations

import pytest

from app.generation.quality_gate import (
    QualityGate,
    Severity,
    apply_status,
)
from app.schemas.problem import (
    Difficulty,
    Hint,
    Problem,
    ProblemMetadata,
    ProblemStatus,
)
from app.schemas.test_case import TestCase, Visibility

REFERENCE_OK = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""

REFERENCE_BROKEN = "int main(void){ printf(\"oops\" return 0; }"

REFERENCE_WRONG = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a-b);return 0;}
"""


def _tests() -> list[TestCase]:
    return [
        TestCase(id="a", name="A", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(id="b", name="B", stdin="-1 -2\n", expected_stdout="-3\n"),
        TestCase(id="c", name="C", visibility=Visibility.HIDDEN, stdin="0 0\n", expected_stdout="0\n"),
        TestCase(id="d", name="D", visibility=Visibility.HIDDEN, stdin="1000 2000\n", expected_stdout="3000\n"),
    ]


def _problem(**overrides) -> Problem:
    metadata_kwargs = {
        "id": "test-problem",
        "title": "Test Problem",
        "difficulty": Difficulty.BEGINNER,
        **overrides.pop("metadata", {}),
    }
    defaults = {
        "metadata": ProblemMetadata(**metadata_kwargs),
        "statement_md": "# Task\n\nAdd two numbers.",
        "starter_code": "int main(void){return 0;}",
        "reference_solution": REFERENCE_OK,
        "tests": _tests(),
        "hints": [Hint(level=i, text=f"hint {i}") for i in range(1, 6)],
    }
    defaults.update(overrides)
    return Problem(**defaults)


# --- happy path ------------------------------------------------------------


def test_valid_problem_passes() -> None:
    report = QualityGate().check(_problem())

    assert report.valid is True
    assert report.errors == []
    assert report.reference_compiled is True
    assert report.reference_passed == 4
    assert report.reference_total == 4


def test_apply_status_marks_validated() -> None:
    problem = _problem()
    report = QualityGate().check(problem)

    assert apply_status(problem, report).metadata.status is ProblemStatus.VALIDATED


# --- structural rejections -------------------------------------------------


def test_missing_tests_is_an_error() -> None:
    report = QualityGate().check(_problem(tests=[]))

    assert report.valid is False
    assert "no-tests" in [f.code for f in report.errors]


def test_empty_statement_is_an_error() -> None:
    report = QualityGate().check(_problem(statement_md="   "))

    assert "empty-statement" in [f.code for f in report.errors]


def test_missing_reference_is_an_error() -> None:
    report = QualityGate().check(_problem(reference_solution=""))

    assert "missing-reference" in [f.code for f in report.errors]


def test_too_few_hidden_tests_is_an_error() -> None:
    tests = [
        TestCase(id="a", name="A", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(id="b", name="B", stdin="-1 -2\n", expected_stdout="-3\n"),
        TestCase(id="c", name="C", visibility=Visibility.HIDDEN, stdin="5 5\n", expected_stdout="10\n"),
    ]
    report = QualityGate().check(_problem(tests=tests))

    assert "too-few-hidden-tests" in [f.code for f in report.errors]


def test_too_few_public_tests_is_only_a_warning() -> None:
    tests = [
        TestCase(id="a", name="A", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(id="c", name="C", visibility=Visibility.HIDDEN, stdin="0 0\n", expected_stdout="0\n"),
        TestCase(id="d", name="D", visibility=Visibility.HIDDEN, stdin="1000 2000\n", expected_stdout="3000\n"),
        TestCase(id="e", name="E", visibility=Visibility.HIDDEN, stdin="7 8\n", expected_stdout="15\n"),
    ]
    report = QualityGate().check(_problem(tests=tests))

    codes = [f.code for f in report.warnings]
    assert "too-few-public-tests" in codes


def test_duplicate_test_cases_warn() -> None:
    tests = [
        TestCase(id="a", name="A", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(id="b", name="B", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(id="c", name="C", visibility=Visibility.HIDDEN, stdin="0 0\n", expected_stdout="0\n"),
        TestCase(id="d", name="D", visibility=Visibility.HIDDEN, stdin="9 9\n", expected_stdout="18\n"),
    ]
    report = QualityGate().check(_problem(tests=tests))

    assert "duplicate-test-cases" in [f.code for f in report.warnings]


# --- resource limits -------------------------------------------------------


def test_unreasonable_time_limit_is_an_error() -> None:
    report = QualityGate().check(_problem(metadata={"time_limit_ms": 60000}))

    assert "unreasonable-time-limit" in [f.code for f in report.errors]


def test_unreasonable_memory_limit_is_an_error() -> None:
    report = QualityGate().check(_problem(metadata={"memory_limit_mb": 4000}))

    assert "unreasonable-memory-limit" in [f.code for f in report.errors]


# --- behavioural checks ----------------------------------------------------


def test_broken_reference_is_rejected() -> None:
    report = QualityGate().check(_problem(reference_solution=REFERENCE_BROKEN))

    assert report.valid is False
    assert report.reference_compiled is False
    assert "reference-does-not-compile" in [f.code for f in report.errors]


def test_reference_that_fails_its_own_tests_is_rejected() -> None:
    """The central check: a wrong reference means the tests are wrong."""
    report = QualityGate().check(_problem(reference_solution=REFERENCE_WRONG))

    assert report.valid is False
    assert "reference-fails-tests" in [f.code for f in report.errors]
    assert report.reference_compiled is True
    assert report.reference_passed < report.reference_total


def test_apply_status_marks_rejected() -> None:
    problem = _problem(reference_solution=REFERENCE_WRONG)
    report = QualityGate().check(problem)

    assert apply_status(problem, report).metadata.status is ProblemStatus.REJECTED


# --- hints -----------------------------------------------------------------


def test_shallow_hints_warn() -> None:
    report = QualityGate().check(_problem(hints=[Hint(level=1, text="only one"), Hint(level=2, text="two")]))

    assert "shallow-hints" in [f.code for f in report.warnings]


def test_hint_containing_code_warns() -> None:
    hints = [Hint(level=i, text=f"hint {i}") for i in range(1, 5)]
    hints.append(Hint(level=5, text="Use int main(void){ ... }"))
    report = QualityGate().check(_problem(hints=hints))

    assert "hint-reveals-code" in [f.code for f in report.warnings]


# --- report shape ----------------------------------------------------------


def test_report_serialises_to_dict() -> None:
    report = QualityGate().check(_problem(reference_solution=REFERENCE_WRONG))
    payload = report.to_dict()

    assert payload["valid"] is False
    assert payload["reference_compiled"] is True
    assert isinstance(payload["findings"], list)
    assert all(set(f) == {"code", "message", "severity"} for f in payload["findings"])


def test_severity_values() -> None:
    assert Severity.ERROR.value == "error"
    assert Severity.WARNING.value == "warning"
