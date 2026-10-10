"""Mutation testing for generated problems.

**Why this exists.** A reference implementation passing its own tests proves
*consistency*, not *correctness*: a wrong reference with matching wrong tests
passes cleanly. The quality gate alone cannot detect that. Mutation testing
supplies the missing instrument.

The method: derive deliberately-wrong variants ("mutants") of the reference,
run each against the problem's tests, and observe whether the tests catch it.

* A mutant that **fails** a test is **killed** - the tests detect that bug.
* A mutant that **passes every test** **survives** - the tests are too weak to
  notice an obviously wrong program.

A high survival rate means the tests do not discriminate. This is reported as a
finding, not silently accepted.

Mutation operators are C-specific, small, and text-based on purpose: the goal is
to catch *common beginner bugs the tests should reject*, not to explore the
whole program space.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from app.grading.compiler import CompilerError
from app.grading.evaluator import Evaluator, GradingConfig
from app.schemas.grading import ResultCategory
from app.schemas.problem import Problem
from app.schemas.test_case import TestCase


class MutantOutcome(str, Enum):
    """What happened when a mutant was run against the tests."""

    KILLED = "killed"  # a test failed -> the tests detect this bug
    SURVIVED = "survived"  # every test passed -> the tests are too weak
    NOT_COMPILED = "not_compiled"  # the mutant was invalid C
    UNTESTABLE = "untestable"  # no tests to run against


@dataclass(frozen=True)
class Mutant:
    """One deliberately-wrong variant of the reference solution."""

    name: str
    description: str
    source: str


@dataclass
class MutantResult:
    """Outcome for a single mutant."""

    name: str
    description: str
    outcome: MutantOutcome
    killed_by: list[str] = field(default_factory=list)


@dataclass
class MutationReport:
    """Aggregate result of mutating a reference against its tests."""

    problem_id: str
    results: list[MutantResult] = field(default_factory=list)

    @property
    def killed(self) -> list[MutantResult]:
        return [r for r in self.results if r.outcome is MutantOutcome.KILLED]

    @property
    def survived(self) -> list[MutantResult]:
        """Mutants the tests failed to catch - the important output."""
        return [r for r in self.results if r.outcome is MutantOutcome.SURVIVED]

    @property
    def not_compiled(self) -> list[MutantResult]:
        return [r for r in self.results if r.outcome is MutantOutcome.NOT_COMPILED]

    @property
    def total_tested(self) -> int:
        """Mutants that produced a meaningful signal."""
        return len(self.killed) + len(self.survived)

    @property
    def mutation_score(self) -> float | None:
        """Killed / (killed + survived). None when nothing was testable."""
        if self.total_tested == 0:
            return None
        return round(len(self.killed) / self.total_tested, 3)

    @property
    def is_strong(self) -> bool:
        """True when every testable mutant was caught."""
        return self.total_tested > 0 and not self.survived

    def to_dict(self) -> dict:
        return {
            "problem_id": self.problem_id,
            "mutation_score": self.mutation_score,
            "strong": self.is_strong,
            "total_tested": self.total_tested,
            "killed": [r.name for r in self.killed],
            "survived": [
                {"name": r.name, "description": r.description} for r in self.survived
            ],
            "not_compiled": [r.name for r in self.not_compiled],
        }


# --- mutation operators ----------------------------------------------------

#: (name, description, pattern, replacement) applied with re.subn.
#: Each entry targets a bug a beginner actually makes and the tests *should*
#: reject. Order matters only for readability.
_OPERATORS: list[tuple[str, str, str, str]] = [
    ("add-to-sub", "changed addition to subtraction", r"\+", "-"),
    ("sub-to-add", "changed subtraction to addition", r"(?<=\w)\s*-\s*(?=\w)", "+"),
    ("mul-to-add", "changed multiplication to addition", r"\*", "+"),
    ("lt-to-le", "off-by-one: `<` became `<=`", r"<=", "<"),
    ("le-to-lt", "off-by-one: `<=` became `<`", r"<(?!=)", "<="),
    ("gt-to-ge", "boundary: `>` became `>=`", r">=", ">"),
    ("eq-to-ne", "equality inverted: `==` became `!=`", r"==", "!="),
    ("inc-to-dec", "increment became decrement", r"\+\+", "--"),
    ("drop-newline", "removed the trailing newline from output", r'\\n"', '"'),
]

#: Statements worth deleting wholesale (missing return / missing loop body).
#: NOTE: removing `return 0;` from `main` is deliberately NOT an operator.
#: Since C99 an implicit `return 0;` is added, so that mutant is semantically
#: equivalent to the reference and would survive for every problem - pure
#: noise that would wrongly flag correct tests as weak.
_DELETIONS: list[tuple[str, str, str]] = [
    ("drop-increment", "removed a loop increment", r"^\s*\w+\s*\+\+\s*;"),
]


#: Mutants whose survival is expected under a given comparison mode, so their
#: survival must not be reported as a weakness.
#:
#: ``drop-newline`` only produces a different *byte string*; under
#: ``exact_normalized`` (which ignores a single trailing newline by design) the
#: difference is intentionally invisible. Reporting it would flag every problem
#: that legitimately uses that mode.
_EXPECTED_SURVIVORS: dict[str, str] = {
    "drop-newline": "exact_normalized",
}


def generate_mutants(reference: str) -> list[Mutant]:
    """Derive wrong-but-plausible variants of ``reference``.

    Only the **first** occurrence of each pattern is mutated, keeping mutants
    small and reducing the chance of producing invalid code. Duplicate mutant
    sources are collapsed.
    """
    mutants: list[Mutant] = []
    seen: set[str] = set()

    for name, description, pattern, replacement in _OPERATORS:
        mutated, count = re.subn(pattern, replacement, reference, count=1)
        if count == 0 or mutated == reference or mutated in seen:
            continue
        seen.add(mutated)
        mutants.append(Mutant(name=name, description=description, source=mutated))

    for name, description, pattern in _DELETIONS:
        mutated, count = re.subn(pattern, "", reference, count=1, flags=re.MULTILINE)
        if count == 0 or mutated == reference or mutated in seen:
            continue
        seen.add(mutated)
        mutants.append(Mutant(name=name, description=description, source=mutated))

    return mutants


class MutationTester:
    """Runs mutants of a reference solution against a problem's tests."""

    #: Mutants that survive are only a *strong* signal when the tests are
    #: numerous enough to be meaningful. Below this, a survivor is reported as
    #: a warning rather than a hard failure.
    MIN_TESTS_FOR_HARD_FAILURE = 3

    def __init__(self, evaluator: Evaluator | None = None, *, enabled: bool = True) -> None:
        self.evaluator = evaluator or Evaluator()
        self.enabled = enabled

    def test(self, problem: Problem) -> MutationReport:
        """Mutate the reference and report which mutants survive."""
        report = MutationReport(problem_id=problem.id)

        if not self.enabled:
            return report

        if not problem.reference_solution.strip() or not problem.tests:
            return report

        config = GradingConfig(
            standard=problem.metadata.compiler.standard,
            timeout_ms=problem.metadata.time_limit_ms,
            memory_limit_mb=problem.metadata.memory_limit_mb,
            default_comparison=problem.metadata.comparison,
        )

        for mutant in generate_mutants(problem.reference_solution):
            report.results.append(
                self._run_mutant(mutant, problem.tests, problem, config)
            )

        return report

    def _run_mutant(
        self,
        mutant: Mutant,
        tests: list[TestCase],
        problem: Problem,
        config: GradingConfig,
    ) -> MutantResult:
        try:
            grading = Evaluator(config).grade_source(
                mutant.source,
                tests,
                problem_id=problem.id,
                entrypoint=problem.metadata.entrypoint,
            )
        except CompilerError:
            # The checker itself could not run: not a statement about the tests.
            return MutantResult(
                name=mutant.name,
                description=mutant.description,
                outcome=MutantOutcome.NOT_COMPILED,
            )

        if not grading.compilation.success:
            # Invalid C is trivially "caught" by the compiler, which tells us
            # nothing about whether the tests discriminate. Report separately so
            # it never inflates the mutation score.
            return MutantResult(
                name=mutant.name,
                description=mutant.description,
                outcome=MutantOutcome.NOT_COMPILED,
            )

        failing = [t.test_id for t in grading.tests if not t.passed]

        if failing:
            return MutantResult(
                name=mutant.name,
                description=mutant.description,
                outcome=MutantOutcome.KILLED,
                killed_by=failing,
            )

        # Every test passed for a deliberately-wrong program.
        return MutantResult(
            name=mutant.name,
            description=mutant.description,
            outcome=MutantOutcome.SURVIVED,
        )


def mutation_finding(report: MutationReport, problem: Problem) -> tuple[str, str] | None:
    """Translate a mutation report into a quality-gate ``(code, message)``.

    Returns None when no finding is warranted. Survivors are always reported;
    whether they are an error or a warning depends on how many tests exist.

    Survivors whose survival is *explained by the problem's own comparison
    mode* are excluded first: under ``exact_normalized`` a missing final
    newline is invisible by design, so counting that mutant as weakness would
    flag every problem using the mode correctly.
    """
    comparison = problem.metadata.comparison.value
    notable = [
        result
        for result in report.survived
        if _EXPECTED_SURVIVORS.get(result.name) != comparison
    ]

    if not notable:
        return None

    names = ", ".join(r.name for r in notable)
    count = len(notable)

    if len(problem.tests) >= MutationTester.MIN_TESTS_FOR_HARD_FAILURE:
        return (
            "weak-tests",
            (
                f"{count} incorrect variant(s) of the reference pass every test, "
                f"so the tests cannot distinguish them from a correct solution: {names}"
            ),
        )

    return (
        "possibly-weak-tests",
        (
            f"{count} incorrect variant(s) pass every test ({names}); with only "
            f"{len(problem.tests)} test(s) this is a weak signal"
        ),
    )
