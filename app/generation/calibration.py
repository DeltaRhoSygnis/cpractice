"""Calibration checks for problem quality.

A prompt alone cannot guarantee quality — the architecture spec is explicit that
the strategy must be *"define observable acceptance criteria"*, not adjectives.
This module implements the mechanically checkable subset of those criteria.

It detects the documented failure mode directly: an exercise with a single
reasoning move whose tests are only "the same shape with different numbers".

These checks are heuristic. They produce **findings**, and the gate decides
whether a finding is fatal. They never claim to measure teaching quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.schemas.problem import Problem
from app.schemas.test_case import Visibility


class CalibrationConcern(str, Enum):
    """Machine-detectable calibration weaknesses."""

    SINGLE_REASONING_MOVE = "single-reasoning-move"
    UNIFORM_TESTS = "uniform-tests"
    NO_STRUCTURED_INPUT = "no-structured-input"
    NUMERIC_ONLY_OUTPUT = "numeric-only-output"
    NO_BOUNDARY_TESTS = "no-boundary-tests"
    NO_MISCONCEPTION_TESTS = "no-misconception-tests"
    TRIVIAL_SOLUTION = "trivial-solution"


@dataclass(frozen=True)
class CalibrationFinding:
    """One calibration concern with the evidence behind it."""

    concern: CalibrationConcern
    message: str
    fatal: bool

    def to_dict(self) -> dict:
        return {
            "concern": self.concern.value,
            "message": self.message,
            "fatal": self.fatal,
        }


@dataclass(frozen=True)
class CalibrationResult:
    """Outcome of calibrating one problem."""

    findings: list[CalibrationFinding]

    @property
    def fatal(self) -> list[CalibrationFinding]:
        return [f for f in self.findings if f.fatal]

    @property
    def passed(self) -> bool:
        return not self.fatal

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
        }


#: Reference-solution size below which the exercise is likely a one-liner.
_TRIVIAL_LINE_COUNT = 8

#: A solution with fewer than this many distinct control-flow constructs is
#: unlikely to require two reasoning moves.
_MIN_CONTROL_FLOW = 1


class CalibrationChecker:
    """Mechanically checks the calibration standard against a problem."""

    def __init__(self, *, strict: bool = True) -> None:
        #: In strict mode, calibration concerns are fatal for core problems.
        self.strict = strict

    def check(self, problem: Problem) -> CalibrationResult:
        """Evaluate a problem against the machine-checkable criteria."""
        findings: list[CalibrationFinding] = []
        role = problem.pedagogy.exercise_role if problem.pedagogy else "core_reasoning"

        # Warm-ups are explicitly permitted to be simple; everything else is
        # held to the standard.
        if role != "diagnostic_warmup":
            findings.extend(self._check_reasoning_moves(problem))
            findings.extend(self._check_input_structure(problem))
            findings.extend(self._check_output_informativeness(problem))

        findings.extend(self._check_test_variety(problem))
        findings.extend(self._check_boundary_coverage(problem))

        return CalibrationResult(findings=findings)

    # -- reasoning moves ---------------------------------------------------

    def _check_reasoning_moves(self, problem: Problem) -> list[CalibrationFinding]:
        source = problem.reference_solution
        body = _strip_comments(source)

        significant = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and not _is_boilerplate(line)
        ]

        findings: list[CalibrationFinding] = []

        if len(significant) < _TRIVIAL_LINE_COUNT:
            findings.append(
                CalibrationFinding(
                    CalibrationConcern.TRIVIAL_SOLUTION,
                    (
                        f"reference solution has only {len(significant)} significant "
                        "line(s); a core problem should require decomposition"
                    ),
                    fatal=self.strict,
                )
            )
            return findings

        control_flow = len(re.findall(r"\b(for|while|if|switch)\b", body))
        if control_flow < _MIN_CONTROL_FLOW + 1:
            findings.append(
                CalibrationFinding(
                    CalibrationConcern.SINGLE_REASONING_MOVE,
                    (
                        f"reference contains {control_flow} control-flow construct(s); "
                        "a core problem needs at least two non-mechanical decisions"
                    ),
                    fatal=self.strict,
                )
            )

        # A declared multi-move objective is contradicted by a trivial solution.
        if problem.pedagogy:
            moves = problem.pedagogy.target_reasoning_moves
            if len(moves) >= 2 and len(significant) < _TRIVIAL_LINE_COUNT:
                findings.append(
                    CalibrationFinding(
                        CalibrationConcern.SINGLE_REASONING_MOVE,
                        (
                            f"blueprint declares {len(moves)} reasoning moves but the "
                            "reference is too small to require them"
                        ),
                        fatal=self.strict,
                    )
                )

        return findings

    # -- input structure ---------------------------------------------------

    def _check_input_structure(self, problem: Problem) -> list[CalibrationFinding]:
        """A single scalar input is not a parsing task."""
        inputs = [t.stdin.strip() for t in problem.tests if t.stdin.strip()]
        if not inputs:
            return []

        # A structured input has more than one token in at least one case.
        max_tokens = max(len(i.split()) for i in inputs)
        if max_tokens <= 1:
            return [
                CalibrationFinding(
                    CalibrationConcern.NO_STRUCTURED_INPUT,
                    (
                        "every test supplies at most one value; core problems should "
                        "require recognising input structure"
                    ),
                    fatal=self.strict,
                )
            ]
        return []

    # -- output informativeness -------------------------------------------

    def _check_output_informativeness(self, problem: Problem) -> list[CalibrationFinding]:
        """A bare number hides intermediate correctness."""
        outputs = [t.expected_stdout.strip() for t in problem.tests if t.expected_stdout.strip()]
        if not outputs:
            return []

        numeric = all(re.fullmatch(r"-?\d+", o) for o in outputs)
        if numeric:
            return [
                CalibrationFinding(
                    CalibrationConcern.NUMERIC_ONLY_OUTPUT,
                    (
                        "every expected output is a single number; prefer output that "
                        "exposes intermediate correctness"
                    ),
                    fatal=False,  # A warning: many good problems end in a number.
                )
            ]
        return []

    # -- test variety ------------------------------------------------------

    def _check_test_variety(self, problem: Problem) -> list[CalibrationFinding]:
        """Detect 'same shape, different numbers' suites."""
        tests = problem.tests
        if len(tests) < 4:
            return []

        shapes = {_input_shape(t.stdin) for t in tests}
        if len(shapes) == 1:
            return [
                CalibrationFinding(
                    CalibrationConcern.UNIFORM_TESTS,
                    (
                        f"all {len(tests)} tests share one input shape ({next(iter(shapes))}); "
                        "they vary only by value, so they cannot distinguish approaches"
                    ),
                    fatal=self.strict,
                )
            ]
        return []

    def _check_boundary_coverage(self, problem: Problem) -> list[CalibrationFinding]:
        """Every problem needs an explicit boundary case."""
        if not problem.tests:
            return []

        # Boundary evidence: a declared requirement/misconception tag, or an
        # input that is the smallest/largest in the suite.
        has_tag = any(
            getattr(t, "requirement_ids", None) or getattr(t, "misconception_ids", None)
            for t in problem.tests
        )

        sizes = [len(t.stdin.split()) for t in problem.tests]
        has_extreme = min(sizes) != max(sizes) if sizes else False

        if not has_tag and not has_extreme:
            return [
                CalibrationFinding(
                    CalibrationConcern.NO_BOUNDARY_TESTS,
                    (
                        "no test is tagged to a requirement or misconception, and all "
                        "inputs are the same size; boundaries are untested"
                    ),
                    fatal=False,
                )
            ]
        return []


# --- helpers ---------------------------------------------------------------


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", "", source)
    return source


_BOILERPLATE = re.compile(
    r"^\s*(#\s*include|#\s*define|int\s+main\s*\(|\{|\}|return\s+0\s*;|return\s+EXIT_SUCCESS\s*;)\s*$"
)


def _is_boilerplate(line: str) -> bool:
    return bool(_BOILERPLATE.match(line))


def _input_shape(stdin: str) -> str:
    """Classify an input's structure: token count plus line count."""
    stripped = stdin.strip()
    if not stripped:
        return "empty"
    tokens = len(stripped.split())
    lines = len([l for l in stripped.splitlines() if l.strip()])
    return f"{lines}line/{tokens}tok"
