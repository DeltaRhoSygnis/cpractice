"""Problem package schemas.

A problem package is the **contract** between the AI generator, the UI, and
the grading engine. It is provider-independent (design decision #1): nothing
here refers to any AI vendor.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.test_case import ComparisonMode, TestCase

SCHEMA_VERSION = "1.0"


class Difficulty(str, Enum):
    """Coarse difficulty band."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ProblemStatus(str, Enum):
    """Publication state of a problem package."""

    DRAFT = "draft"
    VALIDATED = "validated"
    REJECTED = "rejected"


class CompilerSettings(BaseModel):
    """Compiler configuration for a problem."""

    model_config = ConfigDict(extra="forbid")

    standard: str = Field(default="c11", pattern=r"^c(89|99|11|17|23)$")


class Hint(BaseModel):
    """A single progressive hint.

    Levels are ordered; ``level`` 1 is the gentlest. Level 5 is the solution
    reveal and must be requested explicitly by the learner.
    """

    model_config = ConfigDict(extra="forbid")

    level: int = Field(ge=1, le=5)
    text: str = Field(min_length=1)


class ProblemMetadata(BaseModel):
    """Core metadata for a problem package."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=200)

    language: str = Field(default="c", pattern=r"^c$")
    difficulty: Difficulty = Difficulty.BEGINNER
    topics: list[str] = Field(default_factory=list)
    target_skills: list[str] = Field(default_factory=list)

    compiler: CompilerSettings = Field(default_factory=CompilerSettings)
    entrypoint: str = Field(default="main.c", pattern=r"^[A-Za-z0-9_.-]+\.c$")

    comparison: ComparisonMode = ComparisonMode.EXACT_NORMALIZED
    time_limit_ms: int = Field(default=1000, gt=0, le=60_000)
    memory_limit_mb: int = Field(default=128, gt=0, le=4096)

    status: ProblemStatus = ProblemStatus.DRAFT

    @field_validator("topics", "target_skills")
    @classmethod
    def _no_blank_entries(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("entries must not be blank")
        return cleaned


class Problem(BaseModel):
    """A complete problem package (metadata + content + tests)."""

    model_config = ConfigDict(extra="forbid")

    metadata: ProblemMetadata
    statement_md: str = Field(min_length=1)
    starter_code: str = ""
    tests: list[TestCase] = Field(default_factory=list)
    reference_solution: str = ""
    hints: list[Hint] = Field(default_factory=list)
    solution_explanation: str = ""

    @model_validator(mode="after")
    def _validate_tests_and_hints(self) -> Problem:
        self._check_unique_test_ids()
        self._check_hint_levels()
        return self

    def _check_unique_test_ids(self) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for test in self.tests:
            if test.id in seen:
                duplicates.add(test.id)
            seen.add(test.id)
        if duplicates:
            raise ValueError(f"duplicate test ids: {sorted(duplicates)}")

    def _check_hint_levels(self) -> None:
        levels = [hint.level for hint in self.hints]
        duplicates = {level for level in levels if levels.count(level) > 1}
        if duplicates:
            raise ValueError(f"duplicate hint levels: {sorted(duplicates)}")

    # -- convenience accessors --------------------------------------------

    @property
    def id(self) -> str:
        return self.metadata.id

    @property
    def title(self) -> str:
        return self.metadata.title

    @property
    def public_tests(self) -> list[TestCase]:
        return [t for t in self.tests if t.visibility.value == "public"]

    @property
    def hidden_tests(self) -> list[TestCase]:
        return [t for t in self.tests if t.visibility.value == "hidden"]

    def hint_for_level(self, level: int) -> Hint | None:
        """Return the hint at ``level``, if present."""
        for hint in self.hints:
            if hint.level == level:
                return hint
        return None

    @property
    def max_hint_level(self) -> int:
        return max((hint.level for hint in self.hints), default=0)
