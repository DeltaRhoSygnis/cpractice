"""Reporting of grading results.

Turns a :class:`GradingReport` into:

* a structured, client-safe payload, and
* a short natural-language summary suitable for including in an AI prompt.

The hard rule: **no hidden expected output ever leaves this module.** A hidden
test contributes at most its id, name, and result category. Diagnostics for a
failing hidden test describe only the learner's own behaviour (timeout, crash,
wrong length) - never the expected value.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.grading import GradingReport, ResultCategory, TestResult
from app.schemas.test_case import TestCase, Visibility

#: Result categories a learner can act on.
_ACTIONABLE = {
    ResultCategory.WRONG_ANSWER: "the output did not match",
    ResultCategory.RUNTIME_ERROR: "the program terminated abnormally",
    ResultCategory.TIMEOUT: "the program ran too long",
    ResultCategory.OUTPUT_LIMIT_EXCEEDED: "the program produced too much output",
    ResultCategory.COMPILATION_ERROR: "the submission did not compile",
    ResultCategory.INTERNAL_ERROR: "the checker could not run the test",
}


@dataclass(frozen=True)
class FailureSummary:
    """A single failing test, expressed safely."""

    test_id: str
    test_name: str
    visibility: str
    category: str
    detail: str

    @property
    def is_hidden(self) -> bool:
        return self.visibility == Visibility.HIDDEN.value


class ResultReporter:
    """Builds client-safe and AI-safe representations of a grading report."""

    def __init__(self, *, include_hidden_details: bool = False) -> None:
        # ``include_hidden_details`` exists for the server's own logging and for
        # tests. It must never be enabled for a client response.
        self.include_hidden_details = include_hidden_details

    # -- client payload ----------------------------------------------------

    def build(self, report: GradingReport, problem_id: str) -> dict:
        """Return the JSON payload describing an attempt."""
        failures = self.failures(report)

        return {
            "problem_id": problem_id,
            "compilation": {
                "success": report.compilation.success,
                # Diagnostics are the compiler's own output about the learner's
                # code, so they are safe to show.
                "diagnostics": report.compilation.diagnostics,
            },
            "summary": {
                "passed": report.passed_count,
                "total": report.total_count,
                "all_passed": report.all_passed,
            },
            "tests": [self._test_payload(t) for t in report.tests],
            "failures": [
                {
                    "test_id": f.test_id,
                    "test_name": f.test_name,
                    "visibility": f.visibility,
                    "category": f.category,
                    "detail": f.detail,
                }
                for f in failures
            ],
            "verdict": self.verdict(report),
        }

    def _test_payload(self, test: TestResult) -> dict:
        payload = {
            "test_id": test.test_id,
            "test_name": test.test_name,
            "visibility": test.visibility,
            "passed": test.passed,
            "category": test.category.value,
            "duration_ms": test.duration_ms,
        }

        # A public test's detail is safe. A hidden test's detail is only
        # included when explicitly enabled server-side.
        if test.visibility == Visibility.PUBLIC.value or self.include_hidden_details:
            payload["detail"] = test.detail

        return payload

    # -- derived views -----------------------------------------------------

    @staticmethod
    def failures(report: GradingReport) -> list[FailureSummary]:
        """Return the failing tests in report order."""
        return [
            FailureSummary(
                test_id=t.test_id,
                test_name=t.test_name,
                visibility=t.visibility,
                category=t.category.value,
                detail=t.detail,
            )
            for t in report.tests
            if not t.passed
        ]

    @staticmethod
    def verdict(report: GradingReport) -> str:
        """A one-line human verdict."""
        if not report.compilation.success:
            return "compilation_failed"
        if report.all_passed:
            return "passed"
        if report.passed_count == 0:
            return "all_failed"
        return "partial"


def summarize_failures(report: GradingReport, problem: "object" = None) -> str:
    """Build a short description of what failed, safe for an AI prompt.

    Hidden tests contribute only their name and category - never their input or
    expected output. This is what the hint service is allowed to see.
    """
    if not report.compilation.success:
        return "The submission did not compile."

    failures = [t for t in report.tests if not t.passed]
    if not failures:
        return "All tests passed."

    lines: list[str] = []
    for test in failures:
        reason = _ACTIONABLE.get(test.category, "the test did not pass")
        if test.visibility == Visibility.HIDDEN.value:
            # Deliberately vague: the learner may not even see hidden test names
            # in normal feedback, but naming them is harmless and useful.
            lines.append(f'- "{test.test_name}": {reason}')
        else:
            lines.append(f'- "{test.test_name}": {reason}')

    return "\n".join(lines)


def public_test_contract(tests: list[TestCase]) -> str:
    """Render only the *public* tests as context for an AI prompt."""
    rendered: list[str] = []
    for test in tests:
        if test.visibility is not Visibility.PUBLIC:
            continue
        rendered.append(
            f"- {test.name}: input {test.stdin.strip()!r} -> expected {test.expected_stdout.strip()!r}"
        )
    return "\n".join(rendered) if rendered else "(no public examples)"
