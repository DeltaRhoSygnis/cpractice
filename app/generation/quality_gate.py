"""Problem quality gate.

A reference implementation passing its own tests does **not** prove the tests
represent the intended problem. This gate therefore checks structure, compiles
and runs the reference against every test, and reports every finding with a
severity. It never awards a numeric "quality score" - the specification is the
source of truth, and the gate reports evidence.

The gate is deliberately conservative: it marks a problem validated only when
all required checks pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.grading.evaluator import Evaluator, GradingConfig
from app.schemas.grading import ResultCategory
from app.schemas.problem import Problem, ProblemStatus
from app.schemas.test_case import Visibility

#: Bounds beyond which resource limits are considered unreasonable.
_MIN_TIME_LIMIT_MS = 100
_MAX_TIME_LIMIT_MS = 10_000
_MIN_MEMORY_LIMIT_MB = 16
_MAX_MEMORY_LIMIT_MB = 1024

#: A problem needs enough tests to be meaningful.
_MIN_TOTAL_TESTS = 4
_MIN_HIDDEN_TESTS = 2
_MIN_PUBLIC_TESTS = 2


class Severity(str, Enum):
    """Severity of a quality-gate finding."""

    ERROR = "error"  # Blocks validation.
    WARNING = "warning"  # Does not block, but should be reviewed.


@dataclass(frozen=True)
class Finding:
    """A single quality-gate observation."""

    code: str
    message: str
    severity: Severity

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "severity": self.severity.value}


@dataclass
class QualityReport:
    """Result of running the quality gate over one problem."""

    problem_id: str
    findings: list[Finding] = field(default_factory=list)
    reference_compiled: bool = False
    reference_passed: int = 0
    reference_total: int = 0

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def valid(self) -> bool:
        """A problem is valid only when no ERROR-level finding exists."""
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "problem_id": self.problem_id,
            "valid": self.valid,
            "reference_compiled": self.reference_compiled,
            "reference_passed": self.reference_passed,
            "reference_total": self.reference_total,
            "findings": [f.to_dict() for f in self.findings],
        }


class QualityGate:
    """Validates generated or loaded problems before publication."""

    def __init__(self, evaluator: Evaluator | None = None) -> None:
        self.evaluator = evaluator or Evaluator()

    def check(self, problem: Problem) -> QualityReport:
        """Run every structural and behavioural check."""
        report = QualityReport(problem_id=problem.id)

        self._check_structure(problem, report)
        self._check_resource_limits(problem, report)
        self._check_reference(problem, report)

        return report

    # -- structural checks -------------------------------------------------

    def _check_structure(self, problem: Problem, report: QualityReport) -> None:
        if not problem.statement_md.strip():
            report.findings.append(
                Finding("empty-statement", "problem statement is empty", Severity.ERROR)
            )

        if not problem.reference_solution.strip():
            report.findings.append(
                Finding(
                    "missing-reference",
                    "no reference solution; tests cannot be verified",
                    Severity.ERROR,
                )
            )

        if not problem.tests:
            report.findings.append(
                Finding("no-tests", "problem defines no tests", Severity.ERROR)
            )
            return

        if len(problem.tests) < _MIN_TOTAL_TESTS:
            report.findings.append(
                Finding(
                    "too-few-tests",
                    f"only {len(problem.tests)} test(s); at least {_MIN_TOTAL_TESTS} expected",
                    Severity.WARNING,
                )
            )

        if len(problem.public_tests) < _MIN_PUBLIC_TESTS:
            report.findings.append(
                Finding(
                    "too-few-public-tests",
                    f"only {len(problem.public_tests)} public test(s); at least {_MIN_PUBLIC_TESTS} expected",
                    Severity.WARNING,
                )
            )

        if len(problem.hidden_tests) < _MIN_HIDDEN_TESTS:
            report.findings.append(
                Finding(
                    "too-few-hidden-tests",
                    f"only {len(problem.hidden_tests)} hidden test(s); at least {_MIN_HIDDEN_TESTS} expected",
                    Severity.ERROR,
                )
            )

        # Duplicate test ids are rejected by the schema, but guard here too for
        # problems assembled programmatically.
        ids = [t.id for t in problem.tests]
        if len(ids) != len(set(ids)):
            report.findings.append(
                Finding("duplicate-test-ids", "test ids are not unique", Severity.ERROR)
            )

        # Test input/expected pairs that repeat exactly add no coverage.
        signatures = [(t.stdin, t.expected_stdout) for t in problem.tests]
        if len(signatures) != len(set(signatures)):
            report.findings.append(
                Finding(
                    "duplicate-test-cases",
                    "two or more tests have identical input and expected output",
                    Severity.WARNING,
                )
            )

        # An example in the statement that no test covers is a contradiction
        # risk; warn when there are no public tests at all (already covered).
        if problem.hints and problem.max_hint_level < 3:
            report.findings.append(
                Finding(
                    "shallow-hints",
                    "hints do not progress beyond level 2",
                    Severity.WARNING,
                )
            )

        for hint in problem.hints:
            if hint.level == 5 and "main(" in hint.text:
                report.findings.append(
                    Finding(
                        "hint-reveals-code",
                        f"level 5 hint contains C code",
                        Severity.WARNING,
                    )
                )

    def _check_resource_limits(self, problem: Problem, report: QualityReport) -> None:
        time_limit = problem.metadata.time_limit_ms
        if not (_MIN_TIME_LIMIT_MS <= time_limit <= _MAX_TIME_LIMIT_MS):
            report.findings.append(
                Finding(
                    "unreasonable-time-limit",
                    f"time limit {time_limit}ms is outside {_MIN_TIME_LIMIT_MS}-{_MAX_TIME_LIMIT_MS}ms",
                    Severity.ERROR,
                )
            )

        memory_limit = problem.metadata.memory_limit_mb
        if not (_MIN_MEMORY_LIMIT_MB <= memory_limit <= _MAX_MEMORY_LIMIT_MB):
            report.findings.append(
                Finding(
                    "unreasonable-memory-limit",
                    f"memory limit {memory_limit}MB is outside {_MIN_MEMORY_LIMIT_MB}-{_MAX_MEMORY_LIMIT_MB}MB",
                    Severity.ERROR,
                )
            )

    # -- behavioural checks ------------------------------------------------

    def _check_reference(self, problem: Problem, report: QualityReport) -> None:
        """Compile and run the reference solution against every test."""
        if not problem.reference_solution.strip() or not problem.tests:
            return

        config = GradingConfig(
            standard=problem.metadata.compiler.standard,
            timeout_ms=problem.metadata.time_limit_ms,
            memory_limit_mb=problem.metadata.memory_limit_mb,
            default_comparison=problem.metadata.comparison,
        )

        grading = Evaluator(config).grade_source(
            problem.reference_solution,
            problem.tests,
            problem_id=problem.id,
            problem_title=problem.title,
            entrypoint=problem.metadata.entrypoint,
        )

        report.reference_compiled = grading.compilation.success
        report.reference_passed = grading.passed_count
        report.reference_total = grading.total_count

        if not grading.compilation.success:
            report.findings.append(
                Finding(
                    "reference-does-not-compile",
                    f"reference solution failed to compile: {grading.compilation.diagnostics[:300]}",
                    Severity.ERROR,
                )
            )
            return

        failing = [t for t in grading.tests if not t.passed]
        if failing:
            summary = ", ".join(f"{t.test_id} ({t.category.value})" for t in failing[:5])
            report.findings.append(
                Finding(
                    "reference-fails-tests",
                    f"reference solution fails {len(failing)}/{grading.total_count} test(s): {summary}",
                    Severity.ERROR,
                )
            )

        # A reference that cannot finish inside the limit indicates the limit
        # is too tight for the intended solution, even if nothing failed.
        timeouts = [t for t in grading.tests if t.category is ResultCategory.TIMEOUT]
        if timeouts:
            report.findings.append(
                Finding(
                    "reference-times-out",
                    "reference solution exceeds the declared time limit",
                    Severity.ERROR,
                )
            )


def apply_status(problem: Problem, report: QualityReport) -> Problem:
    """Return a copy of ``problem`` with its status set from the report.

    Validated only when the gate found no errors (design decision #3: AI never
    decides correctness - the gate's checks do).
    """
    new_status = ProblemStatus.VALIDATED if report.valid else ProblemStatus.REJECTED
    return problem.model_copy(
        update={"metadata": problem.metadata.model_copy(update={"status": new_status})}
    )
