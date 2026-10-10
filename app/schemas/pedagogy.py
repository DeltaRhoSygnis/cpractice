"""Pedagogical metadata schemas.

These fields describe **what an exercise is for**, separately from what it asks
the learner to do. They are optional so that problems authored before this
schema existed still load unchanged (backwards compatibility).

The numeric difficulty dimensions are ordinal *descriptors used for review*.
They are not measurements of ability and must not be treated as scores.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExerciseRole(str, Enum):
    """The role an exercise plays in a practice sequence (spec section 6)."""

    DIAGNOSTIC_WARMUP = "diagnostic_warmup"
    CORE_REASONING = "core_reasoning"
    TRANSFER = "transfer"
    CHALLENGE = "challenge"
    DEBUGGING = "debugging"
    REFLECTION = "reflection"


#: Reasoning moves each role requires. Warm-ups are the only role permitted to
#: be single-move; a stream of them is the documented failure mode.
MIN_REASONING_MOVES: dict[ExerciseRole, int] = {
    ExerciseRole.DIAGNOSTIC_WARMUP: 1,
    ExerciseRole.CORE_REASONING: 2,
    ExerciseRole.TRANSFER: 2,
    ExerciseRole.CHALLENGE: 3,
    ExerciseRole.DEBUGGING: 0,
    ExerciseRole.REFLECTION: 0,
}


class DifficultyProfile(BaseModel):
    """Ordinal descriptors of where an exercise's difficulty comes from.

    Scale 0-3: 0 = none required, 3 = central to the problem. These describe the
    problem, not the learner.
    """

    model_config = ConfigDict(extra="forbid")

    concept_novelty: int = Field(default=0, ge=0, le=3)
    reasoning_steps: int = Field(default=0, ge=0, le=3)
    algorithm_selection: int = Field(default=0, ge=0, le=3)
    state_management: int = Field(default=0, ge=0, le=3)
    edge_case_burden: int = Field(default=0, ge=0, le=3)
    decomposition: int = Field(default=0, ge=0, le=3)
    reading_complexity: int = Field(default=0, ge=0, le=3)
    prerequisite_depth: int = Field(default=0, ge=0, le=3)

    @property
    def total(self) -> int:
        return sum(
            (
                self.concept_novelty,
                self.reasoning_steps,
                self.algorithm_selection,
                self.state_management,
                self.edge_case_burden,
                self.decomposition,
                self.reading_complexity,
                self.prerequisite_depth,
            )
        )


class Pedagogy(BaseModel):
    """Author-facing pedagogical metadata for one exercise."""

    model_config = ConfigDict(extra="forbid")

    primary_objective: str = Field(default="", max_length=500)
    secondary_objectives: list[str] = Field(default_factory=list, max_length=8)
    prerequisites: list[str] = Field(default_factory=list, max_length=12)
    target_reasoning_moves: list[str] = Field(default_factory=list, max_length=8)
    likely_misconceptions: list[str] = Field(default_factory=list, max_length=10)
    exercise_role: ExerciseRole = ExerciseRole.CORE_REASONING
    difficulty_profile: DifficultyProfile = Field(default_factory=DifficultyProfile)
    transfer_goal: str = Field(default="", max_length=500)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=10)

    #: Author-only: the intended approach. Never shown by default.
    solution_outline: str = Field(default="", max_length=4000)

    def required_move_count(self) -> int:
        return MIN_REASONING_MOVES.get(self.exercise_role, 2)

    @property
    def is_warmup(self) -> bool:
        return self.exercise_role is ExerciseRole.DIAGNOSTIC_WARMUP
