"""Deterministic test evaluator.

Orchestrates the full grading sequence for one submission:
compile -> run each test -> compare -> structured report.

The evaluator is provider-independent and never consults an AI. Failure of the
learner's program and failure of the infrastructure are reported distinctly.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.grading.compiler import CompilerError, compile_source
from app.grading.comparator import outputs_match
from app.grading.runner import run_binary
from app.schemas.grading import (
    CompilationResult,
    GradingReport,
    ResultCategory,
    TestResult,
)
from app.schemas.test_case import ComparisonMode, TestCase, Visibility

_DEFAULT_MAX_OUTPUT_BYTES = 65536


@dataclass(frozen=True)
class GradingConfig:
    """Effective grading limits for one evaluation."""

    compiler: str = "gcc"
    standard: str = "c11"
    timeout_ms: int = 3000
    memory_limit_mb: int = 128
    max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES
    default_comparison: ComparisonMode = ComparisonMode.EXACT_NORMALIZED


class Evaluator:
    """Grades C source against a set of declarative test cases."""

    def __init__(self, config: GradingConfig | None = None) -> None:
        self.config = config or GradingConfig()

    def grade_source(
        self,
        source: str,
        tests: list[TestCase],
        *,
        problem_id: str = "",
        problem_title: str = "",
        entrypoint: str = "main.c",
    ) -> GradingReport:
        """Compile ``source`` and run every test, returning a full report."""
        with tempfile.TemporaryDirectory(prefix="cpractice-grade-") as tmp:
            workspace = Path(tmp)
            source_path = workspace / entrypoint
            source_path.write_text(source, encoding="utf-8")
            binary_path = workspace / "program"

            return self._grade_in_workspace(
                workspace=workspace,
                source_path=source_path,
                binary_path=binary_path,
                tests=tests,
                problem_id=problem_id,
                problem_title=problem_title,
            )

    # -- internals ---------------------------------------------------------

    def _grade_in_workspace(
        self,
        *,
        workspace: Path,
        source_path: Path,
        binary_path: Path,
        tests: list[TestCase],
        problem_id: str,
        problem_title: str,
    ) -> GradingReport:
        try:
            compilation = compile_source(
                source_path,
                binary_path,
                compiler=self.config.compiler,
                standard=self.config.standard,
            )
        except CompilerError as exc:
            # Infrastructure fault: not the learner's wrong answer.
            return GradingReport(
                problem_id=problem_id,
                problem_title=problem_title,
                compilation=CompilationResult(success=False, diagnostics=str(exc)),
                tests=[
                    TestResult(
                        test_id=test.id,
                        test_name=test.name,
                        visibility=test.visibility.value,
                        category=ResultCategory.INTERNAL_ERROR,
                        detail="compiler unavailable",
                    )
                    for test in tests
                ],
            )

        if not compilation.success:
            return GradingReport(
                problem_id=problem_id,
                problem_title=problem_title,
                compilation=compilation,
                tests=[
                    TestResult(
                        test_id=test.id,
                        test_name=test.name,
                        visibility=test.visibility.value,
                        category=ResultCategory.COMPILATION_ERROR,
                        detail="submission did not compile",
                    )
                    for test in tests
                ],
            )

        results = [
            self._run_test(binary_path, workspace, test) for test in tests
        ]
        _cleanup_binary(binary_path)

        return GradingReport(
            problem_id=problem_id,
            problem_title=problem_title,
            compilation=compilation,
            tests=results,
        )

    def _run_test(
        self, binary_path: Path, workspace: Path, test: TestCase
    ) -> TestResult:
        timeout_ms = test.timeout_ms or self.config.timeout_ms
        comparison = test.comparison or self.config.default_comparison

        outcome = run_binary(
            binary_path,
            stdin_text=test.stdin,
            workspace=workspace,
            timeout_ms=timeout_ms,
            max_output_bytes=self.config.max_output_bytes,
            memory_limit_mb=self.config.memory_limit_mb,
        )

        category, detail = self._classify(outcome, test, comparison)

        return TestResult(
            test_id=test.id,
            test_name=test.name,
            visibility=test.visibility.value,
            category=category,
            duration_ms=outcome.duration_ms,
            exit_code=outcome.exit_code,
            detail=detail,
        )

    def _classify(self, outcome, test: TestCase, comparison: ComparisonMode):
        """Map a run outcome to a result category + safe detail string."""
        if outcome.spawn_error:
            return ResultCategory.INTERNAL_ERROR, f"could not execute program: {outcome.spawn_error}"

        if outcome.timed_out:
            return ResultCategory.TIMEOUT, "program exceeded the time limit"

        if outcome.output_limit_exceeded:
            return (
                ResultCategory.OUTPUT_LIMIT_EXCEEDED,
                "program produced more output than allowed",
            )

        # Died from a signal (segfault, abort, ...) is always a runtime error,
        # regardless of what exit code the test expects.
        if outcome.killed_by_signal:
            return (
                ResultCategory.RUNTIME_ERROR,
                f"program terminated by signal {outcome.signal_number}",
            )

        # A non-zero exit that differs from the contract is a runtime error.
        if outcome.exit_code != test.expected_exit_code:
            return (
                ResultCategory.WRONG_ANSWER,
                f"expected exit code {test.expected_exit_code}, got {outcome.exit_code}",
            )

        if not outputs_match(outcome.stdout, test.expected_stdout, comparison):
            return ResultCategory.WRONG_ANSWER, _wrong_answer_detail(outcome.stdout)

        return ResultCategory.PASSED, ""


def _wrong_answer_detail(observed_stdout: str) -> str:
    """Safe diagnostic for a wrong answer.

    Reports only the learner's *own* output shape - never the hidden expected
    value (feedback rule: hidden outputs stay hidden).
    """
    produced = observed_stdout.strip()
    if not produced:
        return "program produced no output on stdout"
    preview = produced if len(produced) <= 200 else produced[:200] + "…"
    return f"output did not match the expected result (produced: {preview!r})"


def _cleanup_binary(binary_path: Path) -> None:
    try:
        binary_path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best effort
        pass


def cleanup_workspace(workspace: Path) -> None:
    """Remove a workspace directory tree, ignoring errors."""
    shutil.rmtree(workspace, ignore_errors=True)


def is_hidden(test: TestCase) -> bool:
    """Convenience predicate for hidden tests."""
    return test.visibility is Visibility.HIDDEN
