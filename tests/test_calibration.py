"""Tests for the calibration standard.

The calibration checker exists to detect the documented failure mode: a single
reasoning move whose tests vary only by value. These tests prove it rejects that
and accepts a genuinely demanding exercise.
"""

from __future__ import annotations

from app.generation.calibration import (
    CalibrationChecker,
    CalibrationConcern,
    _input_shape,
)
from app.schemas.pedagogy import ExerciseRole, Pedagogy
from app.schemas.problem import Problem, ProblemMetadata
from app.schemas.test_case import TestCase, Visibility

# --- fixtures --------------------------------------------------------------

# The weak shape the standard exists to reject: one formula, tests varying only
# by value.
WEAK_REFERENCE = """\
#include <stdio.h>
int main(void){int n;if(scanf("%d",&n)!=1)return 1;printf("%d\\n",n*(n+1)/2);return 0;}
"""


def _weak_tests() -> list[TestCase]:
    return [
        TestCase(id=f"n{i}", name=f"N{i}", stdin=f"{i}\n", expected_stdout=f"{i}\n")
        for i in (1, 5, 100, 0)
    ]


# A problem that meets the standard: structured input, running state, output
# that exposes intermediate correctness.
STRONG_REFERENCE = """\
#include <stdio.h>
int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;
    int best = 0, first = 1;
    for (int i = 0; i < n; i++) {
        int s;
        if (scanf("%d", &s) != 1) return 1;
        if (first || s > best) { best = s; first = 0; }
        printf("%d %d\\n", best, best - s);
    }
    return 0;
}
"""


def _strong_tests() -> list[TestCase]:
    return [
        TestCase(id="a", name="Ascending", stdin="3\n5 10 7\n",
                 expected_stdout="5 0\n10 0\n10 3\n",
                 requirement_ids=["REQ-RUNNING-STATE"]),
        TestCase(id="b", name="Descending", stdin="3\n9 4 1\n",
                 expected_stdout="9 0\n9 5\n9 8\n",
                 requirement_ids=["REQ-RUNNING-STATE"]),
        TestCase(id="c", name="Single", visibility=Visibility.HIDDEN,
                 stdin="1\n42\n", expected_stdout="42 0\n",
                 requirement_ids=["REQ-BOUNDARY-MIN"],
                 misconception_ids=["MIS-INIT"]),
        TestCase(id="d", name="Late max", visibility=Visibility.HIDDEN,
                 stdin="4\n1 2 3 100\n",
                 expected_stdout="1 0\n2 0\n3 0\n100 0\n",
                 requirement_ids=["REQ-BOUNDARY-MAX"]),
    ]


def _problem(reference: str, tests: list[TestCase], *, role=None, moves=None) -> Problem:
    pedagogy = None
    if role is not None:
        pedagogy = Pedagogy(
            primary_objective="maintain running state across iterations",
            exercise_role=role,
            target_reasoning_moves=moves or ["a", "b"],
        )
    return Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="# P",
        reference_solution=reference,
        tests=tests,
        pedagogy=pedagogy,
    )


# --- the failure mode ------------------------------------------------------


def test_rejects_single_formula_problem() -> None:
    result = CalibrationChecker().check(_problem(WEAK_REFERENCE, _weak_tests()))

    assert result.passed is False


def test_flags_trivial_reference() -> None:
    result = CalibrationChecker().check(_problem(WEAK_REFERENCE, _weak_tests()))

    concerns = {f.concern for f in result.findings}
    assert CalibrationConcern.TRIVIAL_SOLUTION in concerns


def test_flags_uniform_tests() -> None:
    """Tests that vary only by value cannot distinguish approaches."""
    result = CalibrationChecker().check(_problem(WEAK_REFERENCE, _weak_tests()))

    concerns = {f.concern for f in result.findings}
    assert CalibrationConcern.UNIFORM_TESTS in concerns


def test_flags_single_token_input() -> None:
    result = CalibrationChecker().check(_problem(WEAK_REFERENCE, _weak_tests()))

    concerns = {f.concern for f in result.findings}
    assert CalibrationConcern.NO_STRUCTURED_INPUT in concerns


def test_flags_numeric_only_output_as_a_warning() -> None:
    result = CalibrationChecker().check(_problem(WEAK_REFERENCE, _weak_tests()))

    numeric = [f for f in result.findings if f.concern is CalibrationConcern.NUMERIC_ONLY_OUTPUT]
    assert numeric
    # A number-only output is common and valid; only a warning.
    assert numeric[0].fatal is False


# --- the standard is achievable -------------------------------------------


def test_accepts_a_calibrated_problem() -> None:
    result = CalibrationChecker().check(_problem(STRONG_REFERENCE, _strong_tests()))

    assert result.passed is True, [f.message for f in result.findings]


def test_calibrated_problem_produces_no_findings() -> None:
    result = CalibrationChecker().check(_problem(STRONG_REFERENCE, _strong_tests()))

    assert result.findings == []


# --- warm-up exemption -----------------------------------------------------


def test_warmups_may_be_simple() -> None:
    """The diagnostic role is explicitly allowed to be single-move."""
    problem = _problem(WEAK_REFERENCE, _weak_tests(), role=ExerciseRole.DIAGNOSTIC_WARMUP)

    result = CalibrationChecker().check(problem)

    concerns = {f.concern for f in result.findings}
    assert CalibrationConcern.TRIVIAL_SOLUTION not in concerns
    assert CalibrationConcern.SINGLE_REASONING_MOVE not in concerns


def test_warmup_still_held_to_test_variety() -> None:
    """Even a warm-up should not have a suite of identical shapes."""
    problem = _problem(WEAK_REFERENCE, _weak_tests(), role=ExerciseRole.DIAGNOSTIC_WARMUP)

    result = CalibrationChecker().check(problem)

    assert CalibrationConcern.UNIFORM_TESTS in {f.concern for f in result.findings}


# --- role requirements -----------------------------------------------------


def test_core_role_requires_two_moves_by_default() -> None:
    problem = _problem(STRONG_REFERENCE, _strong_tests(), role=ExerciseRole.CORE_REASONING,
                       moves=["only one"])

    # The move count is a quality-gate concern; calibration reads the reference.
    assert problem.pedagogy.required_move_count() == 2


def test_challenge_role_requires_three_moves() -> None:
    pedagogy = Pedagogy(exercise_role=ExerciseRole.CHALLENGE)

    assert pedagogy.required_move_count() == 3


# --- input shape helper ----------------------------------------------------


def test_input_shape_distinguishes_structure() -> None:
    assert _input_shape("5\n") == "1line/1tok"
    assert _input_shape("3\n1 2 3\n") == "2line/4tok"
    assert _input_shape("") == "empty"


def test_differing_input_shapes_are_not_uniform() -> None:
    tests = [
        TestCase(id="a", name="A", stdin="1\n", expected_stdout="x\n"),
        TestCase(id="b", name="B", stdin="2 3\n", expected_stdout="y\n"),
        TestCase(id="c", name="C", stdin="4\n5 6\n7 8\n", expected_stdout="z\n"),
        TestCase(id="d", name="D", stdin="9\n", expected_stdout="w\n"),
    ]

    result = CalibrationChecker().check(_problem(STRONG_REFERENCE, tests))

    assert CalibrationConcern.UNIFORM_TESTS not in {f.concern for f in result.findings}


# --- result shape ----------------------------------------------------------


def test_result_serialises() -> None:
    payload = CalibrationChecker().check(_problem(WEAK_REFERENCE, _weak_tests())).to_dict()

    assert payload["passed"] is False
    assert all(set(f) == {"concern", "message", "fatal"} for f in payload["findings"])


def test_strict_mode_controls_severity() -> None:
    lenient = CalibrationChecker(strict=False).check(_problem(WEAK_REFERENCE, _weak_tests()))

    assert lenient.passed is True
    assert lenient.findings  # still reported, just not fatal
