"""Problem service — application-level access to problem packages.

Encapsulates repository access and keeps API handlers thin. Also centralises
the rule that hidden test *content* must never leave the server.
"""

from __future__ import annotations

from app.grading.evaluator import GradingConfig
from app.schemas.problem import Problem
from app.storage.problem_repository import (
    ProblemNotFoundError,
    ProblemRepository,
    ProblemValidationError,
)


class ProblemService:
    """Coordinates problem repository access for the API layer."""

    def __init__(self, repository: ProblemRepository) -> None:
        self.repository = repository

    def list_problems(self) -> list[Problem]:
        """Return every valid problem package."""
        return self.repository.load_all()

    def get(self, problem_id: str) -> Problem:
        """Load one problem, raising repository errors unchanged."""
        return self.repository.load(problem_id)

    def exists(self, problem_id: str) -> bool:
        return self.repository.exists(problem_id)

    @staticmethod
    def grading_config(problem: Problem) -> GradingConfig:
        """Derive effective grading limits from a problem's metadata."""
        return GradingConfig(
            standard=problem.metadata.compiler.standard,
            timeout_ms=problem.metadata.time_limit_ms,
            memory_limit_mb=problem.metadata.memory_limit_mb,
            default_comparison=problem.metadata.comparison,
        )


__all__ = [
    "ProblemNotFoundError",
    "ProblemService",
    "ProblemValidationError",
]
