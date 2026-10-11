"""Submission service — grades a submission and produces a safe report."""

from __future__ import annotations

from dataclasses import dataclass

from app.feedback.reporter import ResultReporter
from app.grading.evaluator import Evaluator
from app.schemas.grading import GradingReport
from app.schemas.problem import CheckerPlan, Problem, ProblemKind
from app.services.checker import build_checker
from app.services.problem_service import ProblemService

#: Submissions larger than this are rejected before any work is done.
MAX_SOURCE_BYTES = 128 * 1024


class SubmissionError(ValueError):
    """Raised when a submission cannot be accepted."""


@dataclass(frozen=True)
class SubmissionOutcome:
    """A graded submission plus its client-safe payload."""

    report: GradingReport
    payload: dict


class SubmissionService:
    """Coordinates grading and result reporting."""

    def __init__(self, evaluator: Evaluator | None = None) -> None:
        self.evaluator = evaluator or Evaluator()
        self.reporter = ResultReporter()

    def submit(
        self,
        problem: Problem,
        source: str,
        predicted_stdout: str | None = None,
    ) -> SubmissionOutcome:
        """Grade ``source`` against ``problem`` and build a safe report.

        ``predicted_stdout`` is the learner's optional hypothesis (spec S6). It
        is recorded and diffed, never graded: the verdict and pass counts are
        identical with or without it.
        """
        if not source.strip():
            raise SubmissionError("submission is empty")

        size = len(source.encode("utf-8"))
        if size > MAX_SOURCE_BYTES:
            raise SubmissionError(
                f"submission is {size} bytes; the limit is {MAX_SOURCE_BYTES}"
            )

        config = ProblemService.grading_config(problem)
        report = self.evaluator.grade_source(
            source,
            problem.tests,
            problem_id=problem.id,
            problem_title=problem.title,
            entrypoint=problem.metadata.entrypoint,
        )

        payload = self.reporter.build(
            report,
            problem_id=problem.id,
            checker=self.checker_for(problem),
            problem=problem,
            predicted_stdout=predicted_stdout,
        )
        return SubmissionOutcome(report=report, payload=payload)

    @staticmethod
    def checker_for(problem: Problem) -> CheckerPlan | None:
        """Return the checker to report for ``problem``, or None.

        A stored checker wins (it is the author's plan). Otherwise a problem set
        gets a deterministically built one, so every pset presents an ordered,
        dependency-aware checker (spec S5, acceptance criterion 5). Legacy
        exercises get none: their payload stays exactly as it always was.
        """
        if problem.metadata.checker is not None:
            return problem.metadata.checker
        if problem.metadata.kind is ProblemKind.PROBLEM_SET:
            return build_checker(problem)
        return None
