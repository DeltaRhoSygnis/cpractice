"""Tests for the generation-time checker (spec S5, plan Phase 4).

The checker is metadata *over* existing tests. These tests prove four things:

* it is synthesised deterministically (``exists``, ``compiles``, then one check
  per test in declaration order);
* dependency failures mark dependents **blocked**, never failed;
* a hidden check exposes its name/description but never its stdin or expected
  stdout;
* a problem without a checker keeps the exact payload it always had.

The compile-dependent cases use the real evaluator; a working C compiler is
assumed for those (the repository's grading tests already assume one).
"""

from __future__ import annotations

from app.grading.evaluator import Evaluator
from app.schemas.grading import (
    CompilationResult,
    GradingReport,
    ResultCategory,
    TestResult,
)
from app.schemas.problem import (
    CheckerPlan,
    Problem,
    ProblemKind,
    ProblemMetadata,
)
from app.schemas.test_case import TestCase, Visibility
from app.services.checker import build_checker, evaluate_checks

SECRET = "999999"


def _tests() -> list[TestCase]:
    return [
        TestCase(id="pub-1", name="Public basic", stdin="2 3\n", expected_stdout="5\n"),
        TestCase(id="pub-2", name="Public zero", stdin="0 0\n", expected_stdout="0\n"),
        TestCase(
            id="sec-1",
            name="Hidden boundary",
            visibility=Visibility.HIDDEN,
            stdin="500000 499999\n",
            expected_stdout=SECRET + "\n",
        ),
    ]


def _problem(*, kind: ProblemKind = ProblemKind.PROBLEM_SET) -> Problem:
    return Problem(
        metadata=ProblemMetadata(
            id="checker-probe",
            title="Checker Probe",
            kind=kind,
            entrypoint="main.c",
        ),
        statement_md="# Task\n\nAdd two integers.",
        tests=_tests(),
    )


def _pass_report() -> GradingReport:
    return GradingReport(
        problem_id="checker-probe",
        compilation=CompilationResult(success=True),
        tests=[
            TestResult(
                test_id=t.id,
                test_name=t.name,
                visibility=t.visibility.value,
                category=ResultCategory.PASSED,
            )
            for t in _tests()
        ],
    )


def _compilation_failure_report() -> GradingReport:
    return GradingReport(
        problem_id="checker-probe",
        compilation=CompilationResult(success=False, diagnostics="expected ';'"),
        # The evaluator emits no test results when compilation fails.
        tests=[],
    )


# --- build_checker ---------------------------------------------------------


def test_build_synthesises_exists_and_compiles_first() -> None:
    plan = build_checker(_problem())

    assert plan.prefix == ["exists", "compiles"]
    assert [c.id for c in plan.checks[:2]] == ["exists", "compiles"]


def test_prefix_descriptions_name_the_entrypoint() -> None:
    plan = build_checker(_problem())

    assert plan.checks[0].description == "main.c exists."
    assert plan.checks[1].description == "main.c compiles."
    assert plan.checks[0].after is None
    assert plan.checks[1].after == "exists"


def test_each_test_maps_to_one_check_in_declaration_order() -> None:
    plan = build_checker(_problem())

    behavioural = plan.checks[2:]
    assert [c.id for c in behavioural] == ["pub-1", "pub-2", "sec-1"]
    assert [c.test_id for c in behavioural] == ["pub-1", "pub-2", "sec-1"]
    assert all(c.after == "compiles" for c in behavioural)


def test_behavioural_description_reuses_the_test_name() -> None:
    plan = build_checker(_problem())

    by_id = {c.id: c for c in plan.checks}
    assert by_id["pub-1"].description == "Public basic"
    assert by_id["sec-1"].description == "Hidden boundary"


def test_hidden_visibility_is_carried_onto_the_check() -> None:
    plan = build_checker(_problem())

    by_id = {c.id: c for c in plan.checks}
    assert by_id["sec-1"].visibility is Visibility.HIDDEN
    assert by_id["pub-1"].visibility is Visibility.PUBLIC


def test_build_is_deterministic_across_runs() -> None:
    first = build_checker(_problem())
    second = build_checker(_problem())

    assert first.model_dump() == second.model_dump()


def test_build_checker_uses_legacy_visibility_default_for_public() -> None:
    plan = build_checker(_problem())

    # A plain public test never becomes hidden and vice versa.
    assert plan.checks[2].visibility.value == "public"


# --- evaluate_checks: all pass --------------------------------------------


def test_all_checks_pass_when_everything_passes() -> None:
    plan = build_checker(_problem())
    results = evaluate_checks(plan, _pass_report())

    assert [r["name"] for r in results] == ["exists", "compiles", "pub-1", "pub-2", "sec-1"]
    assert all(r["passed"] for r in results)
    assert not any(r["blocked"] for r in results)


def test_result_dicts_have_the_documented_shape() -> None:
    plan = build_checker(_problem())
    results = evaluate_checks(plan, _pass_report())

    assert set(results[0]) == {
        "name",
        "description",
        "passed",
        "blocked",
        "cause",
        "data",
        "visibility",
    }


def test_compiles_description_matches_the_plan() -> None:
    plan = build_checker(_problem())
    results = evaluate_checks(plan, _pass_report())

    compiles = next(r for r in results if r["name"] == "compiles")
    assert compiles["description"] == "main.c compiles."


# --- evaluate_checks: dependency blocking ---------------------------------


def test_compile_failure_blocks_behavioural_checks_not_fails_them() -> None:
    plan = build_checker(_problem())
    results = evaluate_checks(plan, _compilation_failure_report())

    by_id = {r["name"]: r for r in results}
    # exists still passes (the submission existed), compiles fails.
    assert by_id["exists"]["passed"] is True
    assert by_id["compiles"]["passed"] is False
    assert by_id["compiles"]["blocked"] is False
    assert by_id["compiles"]["cause"] == "compilation failed"

    for name in ("pub-1", "pub-2", "sec-1"):
        assert by_id[name]["passed"] is False
        assert by_id[name]["blocked"] is True, f"{name} must be blocked, not failed"
        assert by_id[name]["cause"] == "compilation failed"


def test_exists_failure_blocks_everything_after_it() -> None:
    plan = build_checker(_problem())
    results = evaluate_checks(plan, _pass_report(), exists_passed=False)

    by_id = {r["name"]: r for r in results}
    assert by_id["exists"]["passed"] is False
    assert by_id["exists"]["blocked"] is False
    # compiles depends on exists, so it is blocked rather than failed.
    assert by_id["compiles"]["blocked"] is True
    assert by_id["compiles"]["passed"] is False
    for name in ("pub-1", "pub-2", "sec-1"):
        assert by_id[name]["blocked"] is True


def test_a_failing_behavioural_check_is_failed_not_blocked() -> None:
    plan = build_checker(_problem())
    report = GradingReport(
        problem_id="checker-probe",
        compilation=CompilationResult(success=True),
        tests=[
            TestResult(
                test_id="pub-1",
                test_name="Public basic",
                visibility="public",
                category=ResultCategory.PASSED,
            ),
            TestResult(
                test_id="pub-2",
                test_name="Public zero",
                visibility="public",
                category=ResultCategory.WRONG_ANSWER,
            ),
            TestResult(
                test_id="sec-1",
                test_name="Hidden boundary",
                visibility="hidden",
                category=ResultCategory.WRONG_ANSWER,
            ),
        ],
    )

    results = evaluate_checks(plan, report)
    by_id = {r["name"]: r for r in results}

    assert by_id["pub-1"]["passed"] is True
    assert by_id["pub-2"]["blocked"] is False and by_id["pub-2"]["passed"] is False
    assert by_id["sec-1"]["blocked"] is False and by_id["sec-1"]["passed"] is False


def test_evaluate_is_deterministic() -> None:
    plan = build_checker(_problem())

    assert evaluate_checks(plan, _pass_report()) == evaluate_checks(plan, _pass_report())


# --- hidden-data safety ----------------------------------------------------


def test_hidden_check_never_exposes_stdin_or_expected_stdout() -> None:
    plan = build_checker(_problem())
    results = evaluate_checks(plan, _pass_report())

    hidden = next(r for r in results if r["name"] == "sec-1")
    rendered = str(results)

    # The hidden test's stdin and expected output must not appear anywhere.
    assert "500000" not in rendered
    assert SECRET not in rendered
    # Nor may a check carry per-test data at all.
    assert hidden["data"] == {}
    assert hidden["visibility"] == "hidden"
    # The name is present (hidden checks appear by name only).
    assert hidden["description"] == "Hidden boundary"


def test_checker_plan_rejects_duplicate_ids() -> None:
    import pytest
    from pydantic import ValidationError

    from app.schemas.problem import CheckSpec

    with pytest.raises(ValidationError):
        CheckerPlan(
            prefix=["exists", "compiles"],
            checks=[
                CheckSpec(id="dup", description="A", after="compiles"),
                CheckSpec(id="dup", description="B", after="compiles"),
            ],
        )


# --- real evaluation (compiler) -------------------------------------------


def test_real_compilation_failure_blocks_behavioural_checks() -> None:
    problem = _problem()
    report = Evaluator().grade_source(
        'int main(void){ printf("x" return 0; }',
        problem.tests,
        problem_id=problem.id,
        entrypoint=problem.metadata.entrypoint,
    )
    results = evaluate_checks(build_checker(problem), report)
    by_id = {r["name"]: r for r in results}

    assert by_id["compiles"]["passed"] is False
    assert by_id["compiles"]["blocked"] is False
    assert all(by_id[t.id]["blocked"] for t in problem.tests)


def test_real_successful_run_passes_every_check() -> None:
    problem = _problem()
    source = (
        '#include <stdio.h>\n'
        'int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;'
        'printf("%d\\n",a+b);return 0;}\n'
    )
    report = Evaluator().grade_source(
        source,
        problem.tests,
        problem_id=problem.id,
        entrypoint=problem.metadata.entrypoint,
    )
    results = evaluate_checks(build_checker(problem), report)

    assert all(r["passed"] for r in results)
