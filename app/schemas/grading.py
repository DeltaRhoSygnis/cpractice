"""Grading result schemas.

The evaluator reports a structured result. Result categories deliberately
distinguish **learner failure** (wrong answer, runtime error, timeout) from
**infrastructure failure** (compiler missing, internal checker error): an
unavailable compiler is not a wrong answer.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResultCategory(str, Enum):
    """Outcome category for a single test or an overall attempt."""

    PASSED = "passed"
    WRONG_ANSWER = "wrong_answer"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"

    # Attempt-level only:
    COMPILATION_ERROR = "compilation_error"
    # Infrastructure failure - never blame the learner.
    INTERNAL_ERROR = "internal_error"


class CompilationResult(BaseModel):
    """Outcome of compiling a submission."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    diagnostics: str = ""
    duration_ms: int = Field(ge=0, default=0)


class TestResult(BaseModel):
    """Outcome of running one test case."""

    model_config = ConfigDict(extra="forbid")

    test_id: str
    test_name: str
    visibility: str
    category: ResultCategory

    duration_ms: int = Field(ge=0, default=0)
    exit_code: int | None = None

    # Safe diagnostics only. Hidden expected output must never appear here.
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.category is ResultCategory.PASSED


class GradingReport(BaseModel):
    """Structured result of grading one submission against one problem."""

    model_config = ConfigDict(extra="forbid")

    problem_id: str
    problem_title: str = ""

    compilation: CompilationResult
    tests: list[TestResult] = Field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for test in self.tests if test.passed)

    @property
    def total_count(self) -> int:
        return len(self.tests)

    @property
    def all_passed(self) -> bool:
        return bool(self.tests) and self.passed_count == self.total_count
