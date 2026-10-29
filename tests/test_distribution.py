"""Tests for the distribution-code contract (spec S4, plan Phase 2).

A problem set ships a *starter* that must compile, must not already pass the
tests, must not be the reference, and should carry a ``TODO``. These tests
drive the :class:`DistributionChecker` directly and through the quality gate,
using the real compiler. If no usable C compiler is present, the compile-based
tests are skipped rather than failed (the repository's grading tests assume a
working gcc; this guard makes the intent explicit).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.generation.quality_gate import QualityGate, Severity
from app.schemas.problem import (
    ConceptPair,
    Difficulty,
    Distribution,
    Problem,
    ProblemKind,
    ProblemMetadata,
)
from app.schemas.test_case import TestCase, Visibility
from app.services.distribution import (
    DistributionChecker,
    DistributionConcern,
)

REFERENCE_OK = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""

# Compiles, but always prints 0 - fails the tests, and carries a TODO.
STARTER_GOOD = """\
#include <stdio.h>
int main(void){
    int a,b;
    if(scanf("%d %d",&a,&b)!=2)return 1;
    /* TODO: compute the sum instead of printing 0 */
    printf("%d\\n",0);
    return 0;
}
"""

# Compiles, but has no TODO marker.
STARTER_NO_TODO = """\
#include <stdio.h>
int main(void){
    int a,b;
    if(scanf("%d %d",&a,&b)!=2)return 1;
    printf("%d\\n",0);
    return 0;
}
"""

# Does not compile: missing operand and an unterminated call.
STARTER_BROKEN = """\
#include <stdio.h>
int main(void){ int a; /* TODO: read input */ printf(\"oops\" return 0; }
"""


def _compiler_available() -> bool:
    """Whether a C compiler is present and can compile+execute a program."""
    compiler = shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        return False
    with tempfile.TemporaryDirectory(prefix="cpractice-dist-check-") as tmp:
        source = Path(tmp) / "main.c"
        binary = Path(tmp) / "program"
        source.write_text("int main(void){return 0;}\n", encoding="utf-8")
        compiled = subprocess.run(
            [compiler, str(source), "-o", str(binary)],
            capture_output=True,
            check=False,
            shell=False,
        )
        if compiled.returncode != 0 or not binary.exists():
            return False
        try:
            ran = subprocess.run(
                [str(binary)], capture_output=True, check=False, shell=False, timeout=10
            )
        except OSError:
            return False
        return ran.returncode == 0


_REQUIRES_COMPILER = pytest.mark.skipif(
    not _compiler_available(),
    reason="no C compiler able to compile and execute a program",
)


def _tests() -> list[TestCase]:
    return [
        TestCase(id="a", name="A", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(id="b", name="B", stdin="-1 -2\n", expected_stdout="-3\n"),
        TestCase(
            id="c",
            name="C",
            visibility=Visibility.HIDDEN,
            stdin="0 0\n",
            expected_stdout="0\n",
        ),
        TestCase(
            id="d",
            name="D",
            visibility=Visibility.HIDDEN,
            stdin="1000 2000\n",
            expected_stdout="3000\n",
        ),
    ]


def _problem_set(**overrides) -> Problem:
    metadata_kwargs = {
        "id": "pset-test",
        "title": "Pset Test",
        "difficulty": Difficulty.BEGINNER,
        "kind": ProblemKind.PROBLEM_SET,
        "concept": ConceptPair(new_concept="arrays", assumed_known=["for_loops"]),
        "distribution": Distribution(has_starter=True),
        **overrides.pop("metadata", {}),
    }
    defaults = {
        "metadata": ProblemMetadata(**metadata_kwargs),
        "statement_md": "# Task\n\nAdd two numbers.",
        "starter_code": STARTER_GOOD,
        "reference_solution": REFERENCE_OK,
        "tests": _tests(),
    }
    defaults.update(overrides)
    return Problem(**defaults)


def _codes(findings) -> list[str]:
    return [f.concern.value for f in findings]


# --- direct checker --------------------------------------------------------


@_REQUIRES_COMPILER
def test_starter_that_fails_to_compile_is_fatal() -> None:
    result = DistributionChecker().check(_problem_set(starter_code=STARTER_BROKEN))

    assert result.passed is False
    assert DistributionConcern.STARTER_DOES_NOT_COMPILE.value in _codes(result.findings)


@_REQUIRES_COMPILER
def test_starter_that_passes_all_tests_is_fatal() -> None:
    result = DistributionChecker().check(_problem_set(starter_code=REFERENCE_OK))

    # Identical to the reference, so both rules apply; the key one is that a
    # solving starter is fatal.
    assert result.passed is False
    assert DistributionConcern.STARTER_PASSES_ALL_TESTS.value in _codes(result.findings)


@_REQUIRES_COMPILER
def test_starter_identical_to_reference_is_fatal() -> None:
    # Whitespace differs only, so it still does not pass all tests cleanly? It
    # does pass (same program), but the identity rule must fire on its own too.
    identical = REFERENCE_OK + "\n"
    result = DistributionChecker().check(_problem_set(starter_code=identical))

    assert DistributionConcern.STARTER_IDENTICAL_TO_REFERENCE.value in _codes(
        result.findings
    )


def test_missing_todo_is_only_a_warning() -> None:
    result = DistributionChecker().check(
        _problem_set(starter_code=STARTER_NO_TODO)
    )

    # The only finding is the missing-TODO warning; nothing fatal.
    assert result.passed is True
    assert result.fatal == []
    assert DistributionConcern.STARTER_MISSING_TODOS.value in _codes(result.findings)


@_REQUIRES_COMPILER
def test_good_starter_passes() -> None:
    result = DistributionChecker().check(_problem_set())

    assert result.passed is True
    assert result.findings == []


def test_legacy_exercise_is_exempt() -> None:
    exercise = _problem_set(
        metadata={"kind": ProblemKind.EXERCISE},
        starter_code="",
    )

    result = DistributionChecker().check(exercise)

    assert result.findings == []


@_REQUIRES_COMPILER
def test_empty_starter_on_problem_set_is_fatal() -> None:
    result = DistributionChecker().check(_problem_set(starter_code=""))

    assert result.passed is False
    assert DistributionConcern.STARTER_DOES_NOT_COMPILE.value in _codes(result.findings)


# --- through the quality gate ----------------------------------------------


@_REQUIRES_COMPILER
def test_gate_rejects_broken_starter() -> None:
    report = QualityGate(mutation_enabled=False).check(
        _problem_set(starter_code=STARTER_BROKEN)
    )

    assert report.valid is False
    assert "starter-compiles" in [f.code for f in report.errors]


@_REQUIRES_COMPILER
def test_gate_rejects_solving_starter() -> None:
    report = QualityGate(mutation_enabled=False).check(
        _problem_set(starter_code=REFERENCE_OK)
    )

    assert report.valid is False
    assert "starter-passes-all-tests" in [f.code for f in report.errors]


@_REQUIRES_COMPILER
def test_gate_rejects_starter_identical_to_reference() -> None:
    report = QualityGate(mutation_enabled=False).check(
        _problem_set(starter_code=REFERENCE_OK + "\n")
    )

    assert report.valid is False
    assert "starter-identical-to-reference" in [f.code for f in report.errors]


def test_gate_warns_on_missing_todo_but_stays_valid() -> None:
    report = QualityGate(mutation_enabled=False).check(
        _problem_set(starter_code=STARTER_NO_TODO)
    )

    assert report.valid is True
    assert "starter-missing-todos" in [f.code for f in report.warnings]


@_REQUIRES_COMPILER
def test_gate_accepts_good_starter() -> None:
    report = QualityGate(mutation_enabled=False).check(_problem_set())

    assert report.valid is True
    assert report.distribution is not None
    assert report.distribution["passed"] is True
    assert "starter-compiles" not in [f.code for f in report.findings]


def test_gate_ignores_legacy_exercise_distribution() -> None:
    exercise = _problem_set(
        metadata={"kind": ProblemKind.EXERCISE},
        starter_code="",
    )
    report = QualityGate(mutation_enabled=False).check(exercise)

    assert report.distribution is None
    assert "starter-compiles" not in [f.code for f in report.findings]


# --- fixture package -------------------------------------------------------


@pytest.fixture()
def fixture_problem():
    from app.storage.problem_repository import ProblemRepository

    repo = ProblemRepository(Path(__file__).resolve().parent.parent / "app" / "seed_problems")
    return repo.load("pset-vote-tally")


def test_fixture_package_loads_as_problem_set(fixture_problem) -> None:
    assert fixture_problem.metadata.kind is ProblemKind.PROBLEM_SET
    assert fixture_problem.metadata.concept is not None
    assert fixture_problem.metadata.distribution.has_starter is True
    assert len(fixture_problem.public_tests) >= 3
    assert len(fixture_problem.hidden_tests) >= 2
    assert fixture_problem.starter_code.strip()


def test_fixture_package_is_loaded_by_load_all() -> None:
    from app.storage.problem_repository import ProblemRepository

    repo = ProblemRepository(Path(__file__).resolve().parent.parent / "app" / "seed_problems")
    ids = [p.id for p in repo.load_all()]

    assert "pset-vote-tally" in ids


@_REQUIRES_COMPILER
def test_fixture_reference_passes_and_starter_does_not(fixture_problem) -> None:
    from app.grading.evaluator import Evaluator, GradingConfig

    config = GradingConfig(
        standard=fixture_problem.metadata.compiler.standard,
        timeout_ms=fixture_problem.metadata.time_limit_ms,
        memory_limit_mb=fixture_problem.metadata.memory_limit_mb,
        default_comparison=fixture_problem.metadata.comparison,
    )
    evaluator = Evaluator(config)

    reference = evaluator.grade_source(
        fixture_problem.reference_solution,
        fixture_problem.tests,
        entrypoint=fixture_problem.metadata.entrypoint,
    )
    assert reference.compilation.success is True
    assert reference.all_passed is True

    starter = evaluator.grade_source(
        fixture_problem.starter_code,
        fixture_problem.tests,
        entrypoint=fixture_problem.metadata.entrypoint,
    )
    assert starter.compilation.success is True
    assert starter.all_passed is False


@_REQUIRES_COMPILER
def test_fixture_distribution_passes_through_gate(fixture_problem) -> None:
    # The gate now also enforces concept legality (spec S3), so the fixture's
    # known concepts must be declared as known for it to be a legal pset. The
    # distribution rules under test remain unchanged.
    report = QualityGate(known_concepts=["for_loops", "input_output"]).check(
        fixture_problem
    )

    assert report.valid is True
    assert report.distribution is not None
    assert report.distribution["passed"] is True


# --- generation prompt requirements ----------------------------------------


def test_system_prompt_states_distribution_contract() -> None:
    from app.generation.prompts import GENERATION_SYSTEM_PROMPT

    text = GENERATION_SYSTEM_PROMPT.lower()

    assert "starter" in text
    assert "compil" in text  # must compile
    assert "todo" in text
    # Must not pass the tests on its own.
    assert "not pass" in text or "must not pass" in text


def test_reference_prompt_asset_states_distribution_contract() -> None:
    from app.ai.prompts_loader import load_prompt

    text = load_prompt("create_reference_solution").lower()

    assert "starter" in text
    assert "compil" in text
    assert "todo" in text
    assert "must not pass" in text or "not pass" in text

