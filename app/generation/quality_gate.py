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
from app.generation.calibration import CalibrationChecker
from app.generation.mutation import MutationTester, mutation_finding
from app.schemas.grading import ResultCategory
from app.schemas.problem import Problem, ProblemKind, ProblemStatus
from app.schemas.test_case import Visibility
from app.services.distribution import DistributionChecker

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
    #: Mutation testing result, when it ran.
    mutation: dict | None = None
    #: Calibration result, when it ran.
    calibration: dict | None = None
    #: Distribution-code result, for problem sets.
    distribution: dict | None = None

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
            "mutation": self.mutation,
            "calibration": self.calibration,
            "distribution": self.distribution,
            "findings": [f.to_dict() for f in self.findings],
        }


class QualityGate:
    """Validates generated or loaded problems before publication.

    ``calibration_enabled`` controls the top-level quality standard (see
    ``app/ai/prompts/calibration.md``). It is enabled for generated problems,
    where it is the main defence against a stream of single-move exercises.
    It can be disabled when validating legacy or deliberately simple content,
    where the standard would reject otherwise-correct packages.
    """

    def __init__(
        self,
        evaluator: Evaluator | None = None,
        *,
        mutation_enabled: bool = True,
        calibration_enabled: bool = False,
    ) -> None:
        self.evaluator = evaluator or Evaluator()
        self.mutation_tester = MutationTester(self.evaluator, enabled=mutation_enabled)
        self.calibration_enabled = calibration_enabled
        # The checker derives its grading config from each problem (exactly as
        # the reference check does), so no evaluator is injected here.
        self.distribution_checker = DistributionChecker()

    def check(self, problem: Problem) -> QualityReport:
        """Run every structural and behavioural check."""
        report = QualityReport(problem_id=problem.id)

        self._check_structure(problem, report)
        self._check_pedagogy(problem, report)
        self._check_resource_limits(problem, report)
        self._check_reference(problem, report)
        self._check_distribution(problem, report)

        # Only worth mutating once the reference is known to compile and pass;
        # otherwise every mutant would fail for the same underlying reason.
        if report.reference_compiled and not report.errors:
            self._check_mutations(problem, report)
            self._check_calibration(problem, report)

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

    # -- pedagogy ----------------------------------------------------------

    def _check_pedagogy(self, problem: Problem, report: QualityReport) -> None:
        """Check the pedagogical metadata is present and coherent.

        A problem with no pedagogy block is legacy content and is not penalised.
        A problem that *declares* an objective is held to it.
        """
        pedagogy = problem.pedagogy
        if pedagogy is None:
            return

        if not pedagogy.primary_objective.strip():
            report.findings.append(
                Finding(
                    "missing-objective",
                    "pedagogy declares no primary_objective",
                    Severity.WARNING,
                )
            )
        else:
            # A topic label is not an objective: it must describe an action.
            objective = pedagogy.primary_objective.lower()
            action_words = (
                "derive", "identify", "choose", "trace", "maintain", "decompose",
                "recognise", "recognize", "validate", "classify", "compute",
                "determine", "handle", "construct", "scan", "verify", "apply",
            )
            if not any(word in objective for word in action_words):
                report.findings.append(
                    Finding(
                        "vague-objective",
                        (
                            "primary_objective does not describe an observable action; "
                            f"got {pedagogy.primary_objective!r}"
                        ),
                        Severity.WARNING,
                    )
                )

        required = pedagogy.required_move_count()
        declared = len(pedagogy.target_reasoning_moves)
        if declared < required:
            report.findings.append(
                Finding(
                    "insufficient-reasoning-moves",
                    (
                        f"role {pedagogy.exercise_role.value} requires "
                        f"{required} reasoning move(s); {declared} declared"
                    ),
                    Severity.ERROR,
                )
            )

        # Every declared misconception should be caught by some test.
        if pedagogy.likely_misconceptions:
            tagged = {
                mid
                for test in problem.tests
                for mid in test.misconception_ids
            }
            if not tagged and problem.tests:
                report.findings.append(
                    Finding(
                        "misconceptions-untested",
                        (
                            f"{len(pedagogy.likely_misconceptions)} misconception(s) "
                            "declared but no test is tagged to any of them"
                        ),
                        Severity.WARNING,
                    )
                )

    # -- calibration -------------------------------------------------------

    def _check_calibration(self, problem: Problem, report: QualityReport) -> None:
        """Check the problem meets the documented quality standard.

        This is the mechanical answer to "is this actually a good exercise?".
        It detects the documented failure mode: a single reasoning move whose
        tests are the same shape with different numbers.
        """
        if not self.calibration_enabled:
            return

        result = CalibrationChecker().check(problem)
        report.calibration = result.to_dict()

        for finding in result.findings:
            report.findings.append(
                Finding(
                    f"calibration:{finding.concern.value}",
                    finding.message,
                    Severity.ERROR if finding.fatal else Severity.WARNING,
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

    # -- distribution code --------------------------------------------------

    def _check_distribution(self, problem: Problem, report: QualityReport) -> None:
        """Check the distribution-code contract for problem sets (spec S4).

        Legacy exercises are exempt: the distribution rules never apply to a
        package that does not declare ``kind == problem_set``.
        """
        if problem.metadata.kind is not ProblemKind.PROBLEM_SET:
            return

        result = self.distribution_checker.check(problem)
        report.distribution = result.to_dict()

        for finding in result.findings:
            report.findings.append(
                Finding(
                    finding.concern.value,
                    finding.message,
                    Severity.ERROR if finding.fatal else Severity.WARNING,
                )
            )

    # -- mutation testing --------------------------------------------------

    def _check_mutations(self, problem: Problem, report: QualityReport) -> None:
        """Check the tests actually discriminate a correct solution.

        This is the answer to the circularity of "the reference passes the
        tests": deliberately wrong variants of the reference are run, and any
        that pass every test prove the tests are too weak to notice.
        """
        mutation = self.mutation_tester.test(problem)

        # Nothing was testable (e.g. no mutants could be generated): report
        # "did not run" rather than implying a clean result.
        if not self.mutation_tester.enabled or mutation.total_tested == 0 and not mutation.not_compiled:
            report.mutation = None
            return

        report.mutation = mutation.to_dict()

        finding = mutation_finding(mutation, problem)
        if finding is None:
            return

        code, message = finding
        severity = Severity.ERROR if code == "weak-tests" else Severity.WARNING
        report.findings.append(Finding(code, message, severity))


def apply_status(problem: Problem, report: QualityReport) -> Problem:
    """Return a copy of ``problem`` with its status set from the report.

    Validated only when the gate found no errors (design decision #3: AI never
    decides correctness - the gate's checks do).
    """
    new_status = ProblemStatus.VALIDATED if report.valid else ProblemStatus.REJECTED
    return problem.model_copy(
        update={"metadata": problem.metadata.model_copy(update={"status": new_status})}
    )
