"""Tests for result reporting and the safety of diagnostics.

The central rule under test: hidden expected output must never reach a client.
"""

from __future__ import annotations

from app.feedback.reporter import (
    ResultReporter,
    public_test_contract,
    summarize_failures,
)
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
    ProblemMetadata,
)
from app.schemas.problem import ProblemKind
from app.schemas.test_case import ComparisonMode, TestCase, Visibility
from app.services.checker import build_checker

SUM_PROGRAM = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""

# The hidden test's real expected output. It is the thing that must never leak.
SECRET = "1110"


def _tests() -> list[TestCase]:
    return [
        TestCase(id="pub", name="Public basic", stdin="1 2\n", expected_stdout="3\n"),
        TestCase(
            id="sec",
            name="Hidden boundary",
            visibility=Visibility.HIDDEN,
            stdin="999 111\n",
            expected_stdout=SECRET + "\n",
        ),
    ]


# A submission that is correct for small inputs but wrong at the boundary, so
# the public test passes while the hidden test fails.
BOUNDARY_BUG_PROGRAM = """\
#include <stdio.h>
int main(void){
    int a, b;
    if (scanf("%d %d", &a, &b) != 2) return 1;
    if (a + b > 1000) { printf("overflow\\n"); return 0; }
    printf("%d\\n", a + b);
    return 0;
}
"""


def _report() -> GradingReport:
    """A partially failing attempt: the public test passes, the hidden fails."""
    return Evaluator().grade_source(BOUNDARY_BUG_PROGRAM, _tests(), problem_id="p")


# --- payload shape ---------------------------------------------------------


def test_build_returns_expected_top_level_keys() -> None:
    payload = ResultReporter().build(_report(), problem_id="p")

    assert set(payload) == {
        "problem_id",
        "compilation",
        "summary",
        "tests",
        "failures",
        "verdict",
    }


def test_summary_counts_are_reported() -> None:
    payload = ResultReporter().build(_report(), problem_id="p")

    assert payload["summary"]["total"] == 2
    assert payload["summary"]["passed"] == 1
    assert payload["summary"]["all_passed"] is False


def test_verdict_is_partial_when_some_pass() -> None:
    payload = ResultReporter().build(_report(), problem_id="p")

    assert payload["verdict"] == "partial"


def test_verdict_is_compilation_failed_when_broken() -> None:
    report = Evaluator().grade_source('int main(void){ printf("x" return 0; }', _tests())

    payload = ResultReporter().build(report, problem_id="p")

    assert payload["verdict"] == "compilation_failed"
    assert payload["compilation"]["success"] is False


def test_verdict_is_passed_when_all_pass() -> None:
    report = Evaluator().grade_source(SUM_PROGRAM, _tests())

    assert ResultReporter().build(report, problem_id="p")["verdict"] == "passed"


# --- hidden data safety ----------------------------------------------------


def test_hidden_expected_output_never_appears_in_client_payload() -> None:
    payload = ResultReporter().build(_report(), problem_id="p")
    rendered = str(payload)

    assert SECRET not in rendered


def test_hidden_test_detail_is_withheld_but_public_detail_is_shown() -> None:
    payload = ResultReporter().build(_report(), problem_id="p")

    by_id = {t["test_id"]: t for t in payload["tests"]}
    assert "detail" in by_id["pub"]
    assert "detail" not in by_id["sec"]


def test_hidden_detail_can_be_enabled_server_side() -> None:
    # Used for server logging/tests, never for a client response.
    reporter = ResultReporter(include_hidden_details=True)
    payload = reporter.build(_report(), problem_id="p")

    by_id = {t["test_id"]: t for t in payload["tests"]}
    assert "detail" in by_id["sec"]
    # Even then, the expected value itself is not present.
    assert SECRET not in str(payload)


def test_failure_summary_omits_hidden_expected_output() -> None:
    report = _report()

    summary = summarize_failures(report)

    assert SECRET not in summary


def test_public_test_contract_excludes_hidden_tests() -> None:
    rendered = public_test_contract(_tests())

    assert "Public basic" in rendered
    assert "Hidden boundary" not in rendered
    assert SECRET not in rendered


def test_public_test_contract_handles_no_public_tests() -> None:
    hidden_only = [TestCase(id="h", name="H", visibility=Visibility.HIDDEN)]

    assert public_test_contract(hidden_only) == "(no public examples)"


# --- failure summaries -----------------------------------------------------


def test_summarize_reports_all_passed() -> None:
    report = Evaluator().grade_source(SUM_PROGRAM, _tests())

    assert summarize_failures(report) == "All tests passed."


def test_summarize_reports_compilation_failure() -> None:
    report = Evaluator().grade_source('int main(void){ printf("x" return 0; }', _tests())

    assert "did not compile" in summarize_failures(report)


def test_summarize_lists_failing_tests() -> None:
    summary = summarize_failures(_report())

    assert "Hidden boundary" in summary


def test_failures_helper_returns_only_failures() -> None:
    failures = ResultReporter.failures(_report())

    # Only the hidden boundary test fails for this fixture.
    assert [f.test_id for f in failures] == ["sec"]


def test_failure_summary_knows_hidden_visibility() -> None:
    failures = ResultReporter.failures(_report())
    hidden = [f for f in failures if f.test_id == "sec"]

    assert hidden[0].is_hidden is True


# --- category descriptions -------------------------------------------------


# --- checker payload (spec S5) --------------------------------------------


def _checker_problem() -> Problem:
    return Problem(
        metadata=ProblemMetadata(
            id="p",
            title="Probe",
            kind=ProblemKind.PROBLEM_SET,
            entrypoint="main.c",
        ),
        statement_md="# Task",
        tests=_tests(),
    )


def test_no_checker_key_when_problem_has_none() -> None:
    """Legacy exercises keep the exact payload they always had."""
    payload = ResultReporter().build(_report(), problem_id="p")

    assert "checks" not in payload


def test_checks_array_is_added_when_a_checker_is_supplied() -> None:
    problem = _checker_problem()
    payload = ResultReporter().build(
        _report(), problem_id="p", checker=build_checker(problem)
    )

    assert "checks" in payload
    assert [c["name"] for c in payload["checks"]][:2] == ["exists", "compiles"]


def test_checker_addition_preserves_every_existing_field() -> None:
    problem = _checker_problem()
    # Reuse one report so timing fields cannot differ between the two builds.
    report = _report()
    without = ResultReporter().build(report, problem_id="p")
    with_checker = ResultReporter().build(
        report, problem_id="p", checker=build_checker(problem)
    )

    for key, value in without.items():
        assert with_checker[key] == value, f"{key} must be unchanged"
    # The addition is purely additive.
    assert set(with_checker) == set(without) | {"checks"}


def test_hidden_check_in_payload_carries_no_stdin_or_expected_stdout() -> None:
    problem = _checker_problem()
    payload = ResultReporter().build(
        _report(), problem_id="p", checker=build_checker(problem)
    )
    rendered = str(payload)

    hidden = next(c for c in payload["checks"] if c["name"] == "sec")
    # Name only; the secret expected value and hidden stdin never appear.
    assert hidden["description"] == "Hidden boundary"
    assert hidden["data"] == {}
    assert SECRET not in rendered
    assert "999 111" not in rendered


def test_checker_uses_the_same_outcome_as_the_report() -> None:
    problem = _checker_problem()
    source = (
        '#include <stdio.h>\n'
        'int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;'
        'printf("%d\\n",a+b);return 0;}\n'
    )
    report = Evaluator().grade_source(source, _tests(), problem_id="p")

    payload = ResultReporter().build(
        report, problem_id="p", checker=build_checker(problem)
    )
    by_id = {c["name"]: c for c in payload["checks"]}

    assert by_id["compiles"]["passed"] is True
    assert by_id["pub"]["passed"] is True
    assert by_id["sec"]["passed"] is True


def test_all_actionable_categories_have_descriptions() -> None:
    for category in (
        ResultCategory.WRONG_ANSWER,
        ResultCategory.RUNTIME_ERROR,
        ResultCategory.TIMEOUT,
        ResultCategory.OUTPUT_LIMIT_EXCEEDED,
        ResultCategory.COMPILATION_ERROR,
        ResultCategory.INTERNAL_ERROR,
    ):
        report = GradingReport(
            problem_id="p",
            compilation=CompilationResult(success=True),
            tests=[
                TestResult(
                    test_id="t",
                    test_name="T",
                    visibility="public",
                    category=category,
                )
            ],
        )
        summary = summarize_failures(report)
        assert "the test did not pass" not in summary
