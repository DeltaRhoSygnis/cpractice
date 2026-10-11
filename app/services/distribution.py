"""Distribution-code contract checks (spec S4).

A problem set ships *distribution code*: a starter the learner completes. The
starter is a first-class artefact with hard requirements, not decoration:

* it **must compile** — the learner can run the checker immediately;
* it **must not** already pass the tests — otherwise the distribution code
  *is* the solution ("distribution code solves the pset");
* it **must not** be the reference verbatim;
* it **should** carry at least one ``TODO`` marking what to implement.

This module produces *findings* (matching the calibration idiom); the quality
gate decides whether each one is fatal. It reuses the deterministic evaluator
and compiler rather than reimplementing compilation or execution.

These rules apply only to packages that declare themselves as problem sets
(``kind == ProblemKind.PROBLEM_SET``). Legacy exercises are untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.grading.evaluator import Evaluator, GradingConfig
from app.schemas.problem import Problem, ProblemKind


class DistributionConcern(str, Enum):
    """Machine-detectable distribution-code contract violations."""

    STARTER_DOES_NOT_COMPILE = "starter-compiles"
    STARTER_PASSES_ALL_TESTS = "starter-passes-all-tests"
    STARTER_IDENTICAL_TO_REFERENCE = "starter-identical-to-reference"
    STARTER_MISSING_TODOS = "starter-missing-todos"


@dataclass(frozen=True)
class DistributionFinding:
    """One distribution-code concern with the evidence behind it."""

    concern: DistributionConcern
    message: str
    fatal: bool

    def to_dict(self) -> dict:
        return {
            "concern": self.concern.value,
            "message": self.message,
            "fatal": self.fatal,
        }


@dataclass(frozen=True)
class DistributionResult:
    """Outcome of checking one problem's distribution code."""

    findings: list[DistributionFinding]

    @property
    def fatal(self) -> list[DistributionFinding]:
        return [f for f in self.findings if f.fatal]

    @property
    def passed(self) -> bool:
        return not self.fatal

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
        }


#: Matches a ``TODO`` marker in any case. Distribution code must identify what
#: the learner has to implement, so its presence is checked, not its format.
_TODO_PATTERN = re.compile(r"\btodo\b", re.IGNORECASE)


class DistributionChecker:
    """Checks the distribution-code contract against a problem set.

    ``evaluator`` may be supplied to reuse a configured evaluator; otherwise a
    fresh one is built per problem from the problem's own grading limits, so
    the starter is compiled and run exactly as the reference is.
    """

    def __init__(self, evaluator: Evaluator | None = None) -> None:
        self.evaluator = evaluator

    def check(self, problem: Problem) -> DistributionResult:
        """Evaluate a problem set's distribution code.

        Non-problem-set packages are exempt: an empty starter on a legacy
        exercise is legitimate and must not be flagged.
        """
        if problem.metadata.kind is not ProblemKind.PROBLEM_SET:
            return DistributionResult(findings=[])

        findings: list[DistributionFinding] = []
        starter = problem.starter_code

        # An empty starter on a problem set is a missing artefact, not a
        # compile failure; report it as such and stop (there is nothing to run).
        if not starter.strip():
            findings.append(
                DistributionFinding(
                    DistributionConcern.STARTER_DOES_NOT_COMPILE,
                    "problem set has an empty starter; distribution code is required",
                    fatal=True,
                )
            )
            findings.append(
                DistributionFinding(
                    DistributionConcern.STARTER_MISSING_TODOS,
                    "starter contains no TODO marker",
                    fatal=False,
                )
            )
            return DistributionResult(findings=findings)

        # -- labelled check (cheap, static) ---------------------------------
        if not _TODO_PATTERN.search(starter):
            findings.append(
                DistributionFinding(
                    DistributionConcern.STARTER_MISSING_TODOS,
                    "starter contains no TODO marker identifying what to implement",
                    fatal=False,
                )
            )

        # -- identical-to-reference check (cheap, static) --------------------
        if problem.reference_solution.strip() and (
            starter.strip() == problem.reference_solution.strip()
        ):
            findings.append(
                DistributionFinding(
                    DistributionConcern.STARTER_IDENTICAL_TO_REFERENCE,
                    "starter is identical to the reference solution; the answer is shipped",
                    fatal=True,
                )
            )

        # -- behavioural checks (compile + run) ------------------------------
        self._check_behaviour(problem, starter, findings)

        return DistributionResult(findings=findings)

    # -- internals ---------------------------------------------------------

    def _check_behaviour(
        self,
        problem: Problem,
        starter: str,
        findings: list[DistributionFinding],
    ) -> None:
        if not problem.tests:
            # Nothing to run against; structural checks already require tests.
            return

        config = GradingConfig(
            standard=problem.metadata.compiler.standard,
            timeout_ms=problem.metadata.time_limit_ms,
            memory_limit_mb=problem.metadata.memory_limit_mb,
            default_comparison=problem.metadata.comparison,
        )
        evaluator = self.evaluator or Evaluator(config)

        grading = evaluator.grade_source(
            starter,
            problem.tests,
            problem_id=problem.id,
            problem_title=problem.title,
            entrypoint=problem.metadata.entrypoint,
        )

        if not grading.compilation.success:
            findings.append(
                DistributionFinding(
                    DistributionConcern.STARTER_DOES_NOT_COMPILE,
                    (
                        "starter fails to compile: "
                        f"{grading.compilation.diagnostics[:300]}"
                    ),
                    fatal=True,
                )
            )
            # A starter that does not compile cannot be judged on passing.
            return

        if grading.total_count and grading.all_passed:
            findings.append(
                DistributionFinding(
                    DistributionConcern.STARTER_PASSES_ALL_TESTS,
                    (
                        "starter already passes every test "
                        f"({grading.passed_count}/{grading.total_count}); "
                        "distribution code solves the pset"
                    ),
                    fatal=True,
                )
            )
