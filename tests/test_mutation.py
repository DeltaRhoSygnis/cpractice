"""Tests for mutation testing.

The purpose under test: detect tests that fail to discriminate a correct
solution from an obviously wrong one. This is the answer to the circularity of
"the reference passes its own tests".
"""

from __future__ import annotations

from app.generation.mutation import (
    MutationTester,
    MutantOutcome,
    generate_mutants,
    mutation_finding,
)
from app.generation.quality_gate import QualityGate, Severity
from app.schemas.problem import Problem, ProblemMetadata
from app.schemas.test_case import ComparisonMode, TestCase, Visibility
from app.storage.problem_repository import ProblemRepository
from pathlib import Path

REFERENCE = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""


def _problem(tests: list[TestCase], *, comparison=ComparisonMode.EXACT_NORMALIZED,
             reference: str = REFERENCE) -> Problem:
    return Problem(
        metadata=ProblemMetadata(id="p", title="P", comparison=comparison),
        statement_md="# P",
        reference_solution=reference,
        tests=tests,
    )


def _tests() -> list[TestCase]:
    """Tests strong enough to catch a subtraction mutant.

    Four tests so the gate's minimum-test structural check also passes.
    """
    return [
        TestCase(id="a", name="A", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(id="b", name="B", stdin="-1 -2\n", expected_stdout="-3\n"),
        TestCase(id="c", name="C", visibility=Visibility.HIDDEN,
                 stdin="10 5\n", expected_stdout="15\n"),
        TestCase(id="d", name="D", visibility=Visibility.HIDDEN,
                 stdin="100 200\n", expected_stdout="300\n"),
    ]


def _weak_tests() -> list[TestCase]:
    """Tests that pass a subtraction mutant while looking plausible.

    Each case has a different input (so they are not flagged as duplicates), but
    every one has the same result under addition and subtraction: when one
    operand is zero, ``a + b == a - b``. Four tests, two hidden, so no
    structural error masks the mutation finding.
    """
    return [
        TestCase(id="w1", name="W1", stdin="0 0\n", expected_stdout="0\n"),
        TestCase(id="w2", name="W2", stdin="5 0\n", expected_stdout="5\n"),
        TestCase(id="w3", name="W3", visibility=Visibility.HIDDEN,
                 stdin="-7 0\n", expected_stdout="-7\n"),
        TestCase(id="w4", name="W4", visibility=Visibility.HIDDEN,
                 stdin="42 0\n", expected_stdout="42\n"),
    ]


# --- mutant generation -----------------------------------------------------


def test_generates_mutants_from_a_reference() -> None:
    mutants = generate_mutants(REFERENCE)

    assert mutants
    assert all(m.source != REFERENCE for m in mutants)
    assert all(m.name and m.description for m in mutants)


def test_arithmetic_mutation_is_generated() -> None:
    names = {m.name for m in generate_mutants(REFERENCE)}

    assert "add-to-sub" in names


def test_removing_return_zero_is_not_a_mutant() -> None:
    """C99 implies `return 0` in main, so that mutant is equivalent, not wrong.

    An equivalent mutant survives for every problem and is pure noise.
    """
    names = {m.name for m in generate_mutants(REFERENCE)}

    assert "drop-return-0" not in names


def test_mutant_sources_are_unique() -> None:
    sources = [m.source for m in generate_mutants(REFERENCE)]

    assert len(sources) == len(set(sources))


def test_reference_without_mutable_patterns_yields_few_mutants() -> None:
    mutants = generate_mutants("int main(void){ return 0; }")

    assert isinstance(mutants, list)


# --- testing mutants --------------------------------------------------------


def test_strong_tests_kill_the_arithmetic_mutant() -> None:
    report = MutationTester().test(_problem(_tests()))

    killed = {r.name for r in report.killed}
    assert "add-to-sub" in killed


def test_mutation_score_is_reported() -> None:
    report = MutationTester().test(_problem(_tests()))

    assert report.mutation_score is not None
    assert 0.0 <= report.mutation_score <= 1.0


def test_invalid_mutants_are_excluded_from_the_score() -> None:
    """A mutant that fails to compile proves nothing about the tests."""
    report = MutationTester().test(_problem(_tests()))

    assert report.total_tested == len(report.killed) + len(report.survived)
    assert all(r.name not in {k.name for k in report.killed} for r in report.not_compiled)


def test_no_tests_yields_no_signal() -> None:
    report = MutationTester().test(_problem([]))

    assert report.mutation_score is None
    assert report.total_tested == 0


def test_no_reference_yields_no_signal() -> None:
    report = MutationTester().test(_problem(_tests(), reference=""))

    assert report.total_tested == 0


def test_disabled_tester_does_nothing() -> None:
    report = MutationTester(enabled=False).test(_problem(_tests()))

    assert report.results == []


# --- weak tests are detected ------------------------------------------------


def test_weak_tests_let_a_wrong_variant_survive() -> None:
    """The core capability: a test that cannot catch an obvious bug is visible."""
    # A single test whose expected output happens to be the same under both
    # addition and subtraction: 0 + 0 == 0 - 0.
    weak = [TestCase(id="only", name="Only", stdin="0 0\n", expected_stdout="0\n")]

    report = MutationTester().test(_problem(weak))

    assert report.survived, "a wrong variant should have passed the weak test"
    assert report.is_strong is False


def test_survivors_are_reported_with_descriptions() -> None:
    weak = [TestCase(id="only", name="Only", stdin="0 0\n", expected_stdout="0\n")]

    report = MutationTester().test(_problem(weak))

    assert all(r.description for r in report.survived)


# --- findings ---------------------------------------------------------------


def test_weak_tests_become_an_error_finding() -> None:
    weak = _weak_tests()
    report = MutationTester().test(_problem(weak))

    finding = mutation_finding(report, _problem(weak))

    assert finding is not None
    assert finding[0] == "weak-tests"


def test_too_few_tests_makes_a_survivor_a_warning() -> None:
    weak = [TestCase(id="only", name="Only", stdin="0 0\n", expected_stdout="0\n")]
    report = MutationTester().test(_problem(weak))

    finding = mutation_finding(report, _problem(weak))

    assert finding is not None
    assert finding[0] == "possibly-weak-tests"


def test_no_finding_when_all_mutants_are_killed() -> None:
    report = MutationTester().test(_problem(_tests()))

    assert mutation_finding(report, _problem(_tests())) is None


def test_newline_mutant_survival_is_not_flagged_under_exact_normalized() -> None:
    """`exact_normalized` ignores a trailing newline by design.

    Counting the missing-newline mutant as weakness would flag every problem
    that uses the mode correctly.
    """
    problem = _problem(_tests(), comparison=ComparisonMode.EXACT_NORMALIZED)
    report = MutationTester().test(problem)

    survived = {r.name for r in report.survived}
    assert "drop-newline" in survived, "fixture must exercise the newline mutant"

    assert mutation_finding(report, problem) is None


# --- quality gate integration ----------------------------------------------


def test_gate_reports_weak_tests_as_an_error() -> None:
    problem = _problem(_weak_tests())

    report = QualityGate().check(problem)

    assert report.valid is False
    assert "weak-tests" in [f.code for f in report.errors]


def test_gate_includes_mutation_data_in_the_report() -> None:
    report = QualityGate().check(_problem(_tests()))

    assert report.mutation is not None
    assert "mutation_score" in report.mutation


def test_gate_skips_mutation_when_reference_is_broken() -> None:
    """Every mutant would fail for the same reason, so mutation is meaningless."""
    problem = _problem(_tests(), reference='int main(void){ printf("x" return 0; }')

    report = QualityGate().check(problem)

    assert report.mutation is None
    assert "reference-does-not-compile" in [f.code for f in report.errors]


def test_shipped_example_problem_passes_mutation_testing() -> None:
    """The example package must not be flagged as weak."""
    repo = ProblemRepository(Path(__file__).resolve().parent.parent / "problems")
    problem = repo.load("c-sum-two-integers")

    report = QualityGate().check(problem)

    assert report.valid is True
    assert "weak-tests" not in [f.code for f in report.errors]


def test_mutation_can_be_disabled_on_the_gate() -> None:
    report = QualityGate(mutation_enabled=False).check(_problem(_tests()))

    assert report.mutation is None
