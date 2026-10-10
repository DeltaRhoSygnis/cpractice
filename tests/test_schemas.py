"""Tests for schema validation of tests and grading results."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.grading import (
    CompilationResult,
    GradingReport,
    ResultCategory,
    TestResult,
)
from app.schemas.test_case import ComparisonMode, TestCase, Visibility


def test_minimal_test_case_is_valid() -> None:
    test = TestCase(id="case-1", name="Case 1")

    assert test.stdin == ""
    assert test.expected_exit_code == 0
    assert test.visibility is Visibility.PUBLIC


def test_test_id_must_be_lowercase_slug() -> None:
    with pytest.raises(ValidationError):
        TestCase(id="Bad ID!", name="X")


def test_uppercase_test_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TestCase(id="Case", name="X")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TestCase(id="ok", name="Ok", unexpected="nope")  # type: ignore[call-arg]


def test_timeout_must_be_positive_and_bounded() -> None:
    with pytest.raises(ValidationError):
        TestCase(id="t", name="T", timeout_ms=0)
    with pytest.raises(ValidationError):
        TestCase(id="t", name="T", timeout_ms=999_999)


def test_comparison_mode_enum_values() -> None:
    assert ComparisonMode.EXACT_NORMALIZED.value == "exact_normalized"
    assert ComparisonMode.WHITESPACE_TOLERANT.value == "whitespace_tolerant"


def test_grading_report_counts() -> None:
    report = GradingReport(
        problem_id="p1",
        compilation=CompilationResult(success=True),
        tests=[
            TestResult(test_id="a", test_name="A", visibility="public", category=ResultCategory.PASSED),
            TestResult(test_id="b", test_name="B", visibility="public", category=ResultCategory.WRONG_ANSWER),
        ],
    )

    assert report.passed_count == 1
    assert report.total_count == 2
    assert report.all_passed is False


def test_empty_report_is_not_all_passed() -> None:
    report = GradingReport(problem_id="p", compilation=CompilationResult(success=True))

    assert report.total_count == 0
    assert report.all_passed is False


def test_test_result_passed_property() -> None:
    passed = TestResult(test_id="a", test_name="A", visibility="public", category=ResultCategory.PASSED)
    failed = TestResult(test_id="b", test_name="B", visibility="public", category=ResultCategory.TIMEOUT)

    assert passed.passed is True
    assert failed.passed is False
