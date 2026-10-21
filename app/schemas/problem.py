"""Problem package schemas.

A problem package is the **contract** between the AI generator, the UI, and
the grading engine. It is provider-independent (design decision #1): nothing
here refers to any AI vendor.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.test_case import ComparisonMode, TestCase, Visibility
from app.schemas.pedagogy import Pedagogy

SCHEMA_VERSION = "1.0"

#: Keys in a problem package payload that hold content rather than metadata.
#: Shared by the repository loader and the generation pipeline so the two
#: cannot drift apart.
CONTENT_KEYS = frozenset(
    {
        "statement_md",
        "starter_code",
        "reference_solution",
        "tests",
        "hints",
        "solution_explanation",
        "pedagogy",
    }
)


class Difficulty(str, Enum):
    """Coarse difficulty band."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ProblemKind(str, Enum):
    """Whether a package is a standalone exercise or a problem set.

    Legacy packages predate this field and default to ``EXERCISE``, so the
    problem-set gate rules (concept legality, distribution code) never apply to
    them.
    """

    EXERCISE = "exercise"
    PROBLEM_SET = "problem_set"


class ConceptPair(BaseModel):
    """The known/unknown concept pair a problem set is built from.

    Exactly one *new* concept is introduced, combined with a non-empty set of
    *already known* concepts (spec S3). The legality of the pair is checked
    deterministically against the learner's checklist, never by the AI.
    """

    model_config = ConfigDict(extra="forbid")

    new_concept: str = Field(min_length=1, max_length=64)
    assumed_known: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("assumed_known")
    @classmethod
    def _no_blank_or_duplicate_known(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("assumed_known entries must not be blank")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("assumed_known entries must be unique")
        return cleaned

    @model_validator(mode="after")
    def _known_must_be_combined(self) -> ConceptPair:
        # "Connect known and unknown": the new concept must be combined with at
        # least one already-known concept, not practised in isolation.
        if not self.assumed_known:
            raise ValueError(
                "a problem set must combine the new concept with at least one "
                "known concept (assumed_known must be non-empty)"
            )
        if self.new_concept in self.assumed_known:
            raise ValueError("new_concept must not also appear in assumed_known")
        return self


class Distribution(BaseModel):
    """Distribution code supplied with a problem set (spec S4)."""

    model_config = ConfigDict(extra="forbid")

    has_starter: bool = False
    todo_count: int = Field(default=0, ge=0, le=50)
    #: Optional partial scaffold. Distinct from the hint ladder: this is a
    #: starting structure, not progressive textual guidance.
    hint_code: str = Field(default="", max_length=20_000)


class CheckSpec(BaseModel):
    """One check in a generation-time checker (spec S5).

    ``exists`` and ``compiles`` are synthesised by the pipeline, not the model.
    Behavioural checks map one-to-one onto a :class:`TestCase`.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=200)
    #: The check that must pass before this one runs. Defaults to ``compiles``.
    after: str | None = "compiles"
    visibility: Visibility = Visibility.PUBLIC
    #: The test this check executes, if any. None for ``exists``/``compiles``.
    test_id: str | None = None


class CheckerPlan(BaseModel):
    """A problem set's ordered checker (spec S5)."""

    model_config = ConfigDict(extra="forbid")

    #: Synthesised prefix checks, in order. Always starts with ``exists``.
    prefix: list[str] = Field(default_factory=lambda: ["exists", "compiles"])
    checks: list[CheckSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_check_ids(self) -> CheckerPlan:
        ids = [c.id for c in self.checks]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate check ids: {sorted(duplicates)}")
        return self


class PredictionPlan(BaseModel):
    """The optional predict-then-verify mechanic (spec S6)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    #: The public test whose sample the learner predicts against.
    sample_test_id: str | None = None


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

    #: Whether this is a standalone exercise or a problem set (spec S10).
    #: Legacy packages load unchanged as ``exercise``.
    kind: ProblemKind = ProblemKind.EXERCISE

    #: Problem-set concept pair. None for exercises; also None for legacy
    #: problem sets authored before this field existed.
    concept: ConceptPair | None = None

    #: Distribution-code metadata for problem sets.
    distribution: Distribution = Field(default_factory=Distribution)

    #: The generation-time checker. None until the pipeline builds it.
    checker: CheckerPlan | None = None

    #: The optional predict-then-verify mechanic.
    prediction: PredictionPlan = Field(default_factory=PredictionPlan)

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

    #: Pedagogical metadata. Optional: problems authored before this schema
    #: existed load unchanged, with pedagogy=None.
    pedagogy: Pedagogy | None = None

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
