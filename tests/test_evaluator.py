"""End-to-end tests for the deterministic evaluator.

Covers every result category required by milestone 2.
"""

from __future__ import annotations

import pytest

from app.grading.evaluator import Evaluator, GradingConfig, is_hidden
from app.schemas.grading import ResultCategory
from app.schemas.test_case import ComparisonMode, TestCase, Visibility

SUM_PROGRAM = """\
#include <stdio.h>
int main(void) {
    int a, b;
    if (scanf("%d %d", &a, &b) != 2) return 1;
    printf("%d\\n", a + b);
    return 0;
}
"""

BROKEN_PROGRAM = """\
#include <stdio.h>
int main(void) { printf("unterminated return 0; }
"""

CRASH_PROGRAM = """\
int main(void) { return *(volatile int *)0; }
"""

HANG_PROGRAM = """\
int main(void) { for(;;); }
"""

FLOOD_PROGRAM = """\
#include <stdio.h>
int main(void){ for (long i=0;i<2000000;i++) putchar('X'); return 0; }
"""


def _sum_tests() -> list[TestCase]:
    return [
        TestCase(id="basic", name="Basic input", stdin="2 3\n", expected_stdout="5\n"),
        TestCase(id="negative", name="Negative numbers", stdin="-4 1\n", expected_stdout="-3\n"),
        TestCase(
            id="hidden-zero",
            name="Zero handling",
            visibility=Visibility.HIDDEN,
            stdin="0 0\n",
            expected_stdout="0\n",
        ),
    ]


def test_all_passed_for_correct_submission() -> None:
    report = Evaluator().grade_source(SUM_PROGRAM, _sum_tests(), problem_id="sum")

    assert report.compilation.success is True
    assert report.total_count == 3
    assert report.passed_count == 3
    assert report.all_passed is True
    assert all(t.category is ResultCategory.PASSED for t in report.tests)


def test_wrong_answer_is_detected() -> None:
    wrong = SUM_PROGRAM.replace("a + b", "a - b")

    report = Evaluator().grade_source(wrong, _sum_tests())

    assert report.compilation.success is True
    assert report.passed_count < report.total_count
    assert any(t.category is ResultCategory.WRONG_ANSWER for t in report.tests)


def test_compilation_error_marks_every_test() -> None:
    report = Evaluator().grade_source(BROKEN_PROGRAM, _sum_tests())

    assert report.compilation.success is False
    assert report.compilation.diagnostics != ""
    assert all(t.category is ResultCategory.COMPILATION_ERROR for t in report.tests)


def test_runtime_error_is_detected() -> None:
    # Expect a clean exit so the crash is categorised as a runtime error.
    tests = [TestCase(id="crash", name="Crash", stdin="", expected_stdout="", expected_exit_code=0)]

    report = Evaluator().grade_source(CRASH_PROGRAM, tests)

    assert report.tests[0].category is ResultCategory.RUNTIME_ERROR
    # The detail names the signal rather than a generic "wrong output".
    assert "signal" in report.tests[0].detail


def test_abort_is_a_runtime_error_even_when_nonzero_exit_expected() -> None:
    program = "#include <stdlib.h>\nint main(void){ abort(); }\n"
    tests = [TestCase(id="abort", name="Abort", expected_exit_code=134)]

    report = Evaluator().grade_source(program, tests)

    # A signal death is a runtime error regardless of the expected exit code.
    assert report.tests[0].category is ResultCategory.RUNTIME_ERROR


def test_timeout_is_detected() -> None:
    tests = [TestCase(id="hang", name="Hang", timeout_ms=700)]
    config = GradingConfig(timeout_ms=700)

    report = Evaluator(config).grade_source(HANG_PROGRAM, tests)

    assert report.tests[0].category is ResultCategory.TIMEOUT


def test_output_limit_is_detected() -> None:
    tests = [TestCase(id="flood", name="Flood")]
    config = GradingConfig(max_output_bytes=4096, timeout_ms=5000)

    report = Evaluator(config).grade_source(FLOOD_PROGRAM, tests)

    assert report.tests[0].category is ResultCategory.OUTPUT_LIMIT_EXCEEDED


def test_expected_nonzero_exit_code_passes() -> None:
    program = "int main(void){ return 3; }"
    tests = [TestCase(id="exit3", name="Exit 3", expected_stdout="", expected_exit_code=3)]

    report = Evaluator().grade_source(program, tests)

    assert report.tests[0].category is ResultCategory.PASSED


def test_whitespace_tolerant_mode_passes_for_loose_spacing() -> None:
    program = '#include <stdio.h>\nint main(void){ printf("a   b\\n"); return 0; }\n'
    tests = [
        TestCase(
            id="loose",
            name="Loose spacing",
            expected_stdout="a b\n",
            comparison=ComparisonMode.WHITESPACE_TOLERANT,
        )
    ]

    report = Evaluator().grade_source(program, tests)

    assert report.tests[0].category is ResultCategory.PASSED


def test_wrong_answer_detail_never_reveals_expected_output() -> None:
    tests = [TestCase(id="secret", name="Secret", stdin="2 2\n", expected_stdout="SECRET-EXPECTED-VALUE\n")]

    report = Evaluator().grade_source(SUM_PROGRAM, tests)

    test_result = report.tests[0]
    assert test_result.category is ResultCategory.WRONG_ANSWER
    # The hidden expected value must never appear in the diagnostic.
    assert "SECRET-EXPECTED-VALUE" not in test_result.detail


def test_missing_compiler_is_internal_error_not_wrong_answer() -> None:
    config = GradingConfig(compiler="definitely-not-a-compiler")

    report = Evaluator(config).grade_source(SUM_PROGRAM, _sum_tests())

    assert report.compilation.success is False
    assert all(t.category is ResultCategory.INTERNAL_ERROR for t in report.tests)


def test_temporary_workspace_is_cleaned_up() -> None:
    import tempfile

    before = set(__import__("pathlib").Path(tempfile.gettempdir()).glob("cpractice-grade-*"))
    Evaluator().grade_source(SUM_PROGRAM, _sum_tests())
    after = set(__import__("pathlib").Path(tempfile.gettempdir()).glob("cpractice-grade-*"))

    assert before == after


def test_is_hidden_helper() -> None:
    public = TestCase(id="p", name="P")
    hidden = TestCase(id="h", name="H", visibility=Visibility.HIDDEN)

    assert is_hidden(hidden) is True
    assert is_hidden(public) is False
