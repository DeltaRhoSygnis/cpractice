"""Practice sequencing — choosing what to practise next, and in what role.

The plan's rule (section 6): a unit of practice should be mostly core reasoning.
Warm-ups do not accumulate; a stream of single-move exercises is the documented
failure mode. This module decides the next exercise's *role* from evidence,
rather than drifting toward whatever is easiest to generate.

Recommendations are advice, never automatic judgements about the learner. The
caller may always override.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.schemas.pedagogy import ExerciseRole
from app.schemas.problem import Problem
from app.services.curriculum import SKILLS, Skill
from app.storage.attempt_repository import AttemptRecord


class SequenceReason(str, Enum):
    """Why the sequencer chose a role."""

    NO_EVIDENCE = "no_evidence"
    PREREQUISITE_GAP = "prerequisite_gap"
    FAILED_CORE = "failed_core"
    PASSED_CORE_NEEDS_TRANSFER = "passed_core_needs_transfer"
    MASTERED = "mastered"
    HINT_DEPENDENT = "hint_dependent"


@dataclass(frozen=True)
class NextExercise:
    """A recommendation for the next exercise's shape."""

    skill_tag: str | None
    role: ExerciseRole
    reason: SequenceReason
    explanation: str
    evidence: dict = field(default_factory=dict)


@dataclass
class SkillEvidence:
    """Observed performance on one skill tag."""

    tag: str
    attempts: int = 0
    solved: int = 0
    fails: int = 0
    hints_used: int = 0
    solves_without_hints: int = 0

    @property
    def attempted(self) -> bool:
        return self.attempts > 0

    @property
    def solved_rate(self) -> float:
        return self.solved / self.attempts if self.attempts else 0.0

    @property
    def needs_hints(self) -> bool:
        """Solved, but always leaned on hints."""
        return self.solved > 0 and self.solves_without_hints == 0


class PracticeSequencer:
    """Chooses the next exercise's skill and role from recorded evidence."""

    #: Below this many attempts a skill is not yet a reliable signal.
    MIN_ATTEMPTS = 2

    def __init__(self, *, min_attempts: int = MIN_ATTEMPTS) -> None:
        self.min_attempts = min_attempts

    # -- evidence ----------------------------------------------------------

    def skill_evidence(
        self,
        attempts: list[AttemptRecord],
        problems_by_id: dict[str, Problem],
    ) -> dict[str, SkillEvidence]:
        """Aggregate attempts by the skills their problems declare."""
        totals: dict[str, SkillEvidence] = {}

        for attempt in attempts:
            problem = problems_by_id.get(attempt.problem_id)
            if problem is None:
                continue

            tags = _problem_skill_tags(problem)
            for tag in tags:
                evidence = totals.setdefault(tag, SkillEvidence(tag=tag))
                evidence.attempts += 1
                evidence.hints_used += attempt.hints_used
                if attempt.succeeded:
                    evidence.solved += 1
                    if attempt.hints_used == 0:
                        evidence.solves_without_hints += 1
                else:
                    evidence.fails += 1

        return totals

    # -- sequencing --------------------------------------------------------

    def next_exercise(
        self,
        *,
        attempts: list[AttemptRecord],
        problems_by_id: dict[str, Problem],
        requested_skill: str | None = None,
    ) -> NextExercise:
        """Recommend the skill and role for the next exercise."""
        evidence = self.skill_evidence(attempts, problems_by_id)

        if requested_skill:
            return self._for_skill(requested_skill, evidence.get(requested_skill))

        if not evidence:
            return NextExercise(
                skill_tag=None,
                role=ExerciseRole.CORE_REASONING,
                reason=SequenceReason.NO_EVIDENCE,
                explanation=(
                    "No performance history yet, so start with a core reasoning "
                    "problem. There is no evidence to target."
                ),
            )

        # A skill that is repeatedly failed needs core practice, not escalation.
        failing = [
            e for e in evidence.values()
            if e.attempts >= self.min_attempts and e.fails > 0
        ]
        if failing:
            worst = min(failing, key=lambda e: (e.solved_rate, -e.fails, e.tag))
            skill = SKILLS.get(worst.tag)
            return NextExercise(
                skill_tag=worst.tag,
                role=ExerciseRole.CORE_REASONING,
                reason=SequenceReason.FAILED_CORE,
                explanation=(
                    f"Failed {worst.fails} of {worst.attempts} attempts on "
                    f"{_skill_name(skill)}. Another core problem targets the gap "
                    "rather than raising difficulty."
                ),
                evidence={"attempts": worst.attempts, "fails": worst.fails},
            )

        # Solve rate is good but always with hints: practise independence with
        # less scaffolding, do not just raise difficulty.
        hint_dependent = [
            e for e in evidence.values()
            if e.attempts >= self.min_attempts and e.needs_hints
        ]
        if hint_dependent:
            weakest = min(hint_dependent, key=lambda e: e.solves_without_hints)
            return NextExercise(
                skill_tag=weakest.tag,
                role=ExerciseRole.TRANSFER,
                reason=SequenceReason.HINT_DEPENDENT,
                explanation=(
                    f"Solved {_skill_name(SKILLS.get(weakest.tag))} only with hints. "
                    "A transfer problem practises the same skill unaided."
                ),
                evidence={"attempts": weakest.attempts, "hints": weakest.hints_used},
            )

        # Solid without hints: extend to a transfer, then a challenge.
        strong = [
            e for e in evidence.values()
            if e.attempts >= self.min_attempts and e.solves_without_hints > 0
        ]
        if strong:
            best = max(strong, key=lambda e: (e.solves_without_hints, e.tag))
            solved_transfer = self._has_role(
                best.tag, ExerciseRole.TRANSFER, attempts, problems_by_id
            )
            role = ExerciseRole.CHALLENGE if solved_transfer else ExerciseRole.TRANSFER
            return NextExercise(
                skill_tag=best.tag,
                role=role,
                reason=(
                    SequenceReason.MASTERED if solved_transfer
                    else SequenceReason.PASSED_CORE_NEEDS_TRANSFER
                ),
                explanation=(
                    f"Solved {_skill_name(SKILLS.get(best.tag))} without hints. "
                    + (
                        "A challenge problem combines it with previously practised concepts."
                        if solved_transfer
                        else "A transfer problem applies it in a new context."
                    )
                ),
                evidence={"solves_without_hints": best.solves_without_hints},
            )

        return NextExercise(
            skill_tag=None,
            role=ExerciseRole.CORE_REASONING,
            reason=SequenceReason.NO_EVIDENCE,
            explanation="Not enough evidence yet to target a specific skill.",
        )

    # -- internals ---------------------------------------------------------

    def _for_skill(self, tag: str, evidence: SkillEvidence | None) -> NextExercise:
        if evidence is None or evidence.attempts < self.min_attempts:
            return NextExercise(
                skill_tag=tag,
                role=ExerciseRole.CORE_REASONING,
                reason=SequenceReason.NO_EVIDENCE,
                explanation=(
                    f"Requested {_skill_name(SKILLS.get(tag))}; not enough history "
                    "to choose a role, so start with a core problem."
                ),
            )

        if evidence.fails > 0:
            return NextExercise(
                skill_tag=tag,
                role=ExerciseRole.CORE_REASONING,
                reason=SequenceReason.FAILED_CORE,
                explanation=(
                    f"{evidence.fails} of {evidence.attempts} attempts on "
                    f"{_skill_name(SKILLS.get(tag))} failed. Practice the core skill."
                ),
                evidence={"attempts": evidence.attempts, "fails": evidence.fails},
            )

        if evidence.needs_hints:
            return NextExercise(
                skill_tag=tag,
                role=ExerciseRole.TRANSFER,
                reason=SequenceReason.HINT_DEPENDENT,
                explanation=(
                    f"{_skill_name(SKILLS.get(tag))} is solved only with hints. "
                    "Try a transfer problem unaided."
                ),
            )

        return NextExercise(
            skill_tag=tag,
            role=ExerciseRole.CHALLENGE,
            reason=SequenceReason.MASTERED,
            explanation=(
                f"{_skill_name(SKILLS.get(tag))} is solid without hints. "
                "Try a harder variation."
            ),
        )

    @staticmethod
    def _has_role(
        skill_tag: str,
        role: ExerciseRole,
        attempts: list[AttemptRecord],
        problems_by_id: dict[str, Problem],
    ) -> bool:
        """True when the learner has already solved a problem of this role."""
        solved_ids = {a.problem_id for a in attempts if a.succeeded}
        for problem_id in solved_ids:
            problem = problems_by_id.get(problem_id)
            if problem is None or problem.pedagogy is None:
                continue
            if problem.pedagogy.exercise_role is not role:
                continue
            if skill_tag in _problem_skill_tags(problem):
                return True
        return False


# --- helpers ---------------------------------------------------------------


def _problem_skill_tags(problem: Problem) -> list[str]:
    """Skill tags a problem targets.

    Uses the problem's declared ``target_skills``. Prerequisites are inputs the
    exercise assumes, not skills it develops, so they are deliberately excluded.
    """
    return list(problem.metadata.target_skills)


def _skill_name(skill: Skill | None) -> str:
    return skill.name if skill else "this skill"
