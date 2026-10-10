"""Tests for practice sequencing.

The plan's rule under test: a unit of practice should be mostly core reasoning.
Warm-ups do not accumulate, and difficulty is not raised just because a learner
keeps failing - a repeated failure calls for another core problem, not a harder
one.
"""

from __future__ import annotations

from app.schemas.pedagogy import ExerciseRole, Pedagogy
from app.schemas.problem import Problem, ProblemMetadata
from app.services.sequencer import (
    PracticeSequencer,
    SequenceReason,
    SkillEvidence,
)
from app.storage.attempt_repository import AttemptRecord


def _problem(
    pid: str,
    *,
    skills: list[str],
    role: ExerciseRole = ExerciseRole.CORE_REASONING,
) -> Problem:
    return Problem(
        metadata=ProblemMetadata(id=pid, title=pid, target_skills=skills),
        statement_md="# P",
        pedagogy=Pedagogy(exercise_role=role),
    )


def _attempt(
    pid: str, *, passed: int, total: int, hints: int = 0
) -> AttemptRecord:
    return AttemptRecord(
        id=1, problem_id=pid, created_at="now", compilation_ok=True,
        passed=passed, total=total,
        verdict="passed" if passed == total else "partial",
        duration_ms=1, hints_used=hints,
    )


def _solved(pid: str, *, hints: int = 0) -> AttemptRecord:
    return _attempt(pid, passed=3, total=3, hints=hints)


def _failed(pid: str) -> AttemptRecord:
    return _attempt(pid, passed=0, total=3)


# --- no evidence -----------------------------------------------------------


def test_no_history_starts_with_core_reasoning() -> None:
    result = PracticeSequencer().next_exercise(attempts=[], problems_by_id={})

    assert result.role is ExerciseRole.CORE_REASONING
    assert result.reason is SequenceReason.NO_EVIDENCE
    assert result.skill_tag is None
    assert "no evidence" in result.explanation.lower()


# --- repeated failure ------------------------------------------------------


def test_repeated_failure_asks_for_another_core_problem() -> None:
    """Not a harder one: difficulty is not raised to punish failure."""
    problems = {"a": _problem("a", skills=["reversing"])}
    attempts = [_failed("a"), _failed("a")]

    result = PracticeSequencer().next_exercise(attempts=attempts, problems_by_id=problems)

    assert result.role is ExerciseRole.CORE_REASONING
    assert result.reason is SequenceReason.FAILED_CORE
    assert result.skill_tag == "reversing"
    assert "Failed 2 of 2" in result.explanation


def test_single_failure_is_not_yet_evidence() -> None:
    problems = {"a": _problem("a", skills=["reversing"])}

    result = PracticeSequencer().next_exercise(
        attempts=[_failed("a")], problems_by_id=problems
    )

    # One failure is below the minimum sample, so no targeted claim is made.
    assert result.reason is SequenceReason.NO_EVIDENCE


# --- hint dependence -------------------------------------------------------


def test_hint_dependent_success_asks_for_a_transfer() -> None:
    problems = {"a": _problem("a", skills=["loop_bounds"])}
    attempts = [_solved("a", hints=3), _solved("a", hints=2)]

    result = PracticeSequencer().next_exercise(attempts=attempts, problems_by_id=problems)

    assert result.role is ExerciseRole.TRANSFER
    assert result.reason is SequenceReason.HINT_DEPENDENT
    assert "hint" in result.explanation.lower()


# --- mastery ---------------------------------------------------------------


def test_unaided_success_asks_for_a_transfer_first() -> None:
    problems = {"a": _problem("a", skills=["loop_bounds"])}
    attempts = [_solved("a"), _solved("a")]

    result = PracticeSequencer().next_exercise(attempts=attempts, problems_by_id=problems)

    assert result.role is ExerciseRole.TRANSFER
    assert result.reason is SequenceReason.PASSED_CORE_NEEDS_TRANSFER


def test_solved_transfer_escalates_to_challenge() -> None:
    problems = {
        "core": _problem("core", skills=["loop_bounds"]),
        "transfer": _problem("transfer", skills=["loop_bounds"], role=ExerciseRole.TRANSFER),
    }
    attempts = [_solved("core"), _solved("core"), _solved("transfer")]

    result = PracticeSequencer().next_exercise(attempts=attempts, problems_by_id=problems)

    assert result.role is ExerciseRole.CHALLENGE
    assert result.reason is SequenceReason.MASTERED


# --- explicit skill request ------------------------------------------------


def test_requested_skill_without_history_starts_at_core() -> None:
    result = PracticeSequencer().next_exercise(
        attempts=[], problems_by_id={}, requested_skill="array_traversal"
    )

    assert result.skill_tag == "array_traversal"
    assert result.role is ExerciseRole.CORE_REASONING


def test_requested_skill_ignores_other_evidence() -> None:
    problems = {"a": _problem("a", skills=["loop_bounds"])}
    attempts = [_failed("a"), _failed("a")]

    result = PracticeSequencer().next_exercise(
        attempts=attempts, problems_by_id=problems, requested_skill="array_traversal"
    )

    assert result.skill_tag == "array_traversal"


def test_requested_mastered_skill_escalates() -> None:
    problems = {"a": _problem("a", skills=["loop_bounds"])}
    attempts = [_solved("a"), _solved("a")]

    result = PracticeSequencer().next_exercise(
        attempts=attempts, problems_by_id=problems, requested_skill="loop_bounds"
    )

    assert result.role is ExerciseRole.CHALLENGE


# --- evidence aggregation --------------------------------------------------


def test_evidence_aggregates_by_declared_skill() -> None:
    problems = {"a": _problem("a", skills=["loop_bounds", "accumulation"])}
    attempts = [_solved("a"), _failed("a")]

    evidence = PracticeSequencer().skill_evidence(attempts, problems)

    assert evidence["loop_bounds"].attempts == 2
    assert evidence["loop_bounds"].solved == 1
    assert evidence["loop_bounds"].fails == 1
    assert evidence["accumulation"].attempts == 2


def test_attempts_for_unknown_problems_are_ignored() -> None:
    evidence = PracticeSequencer().skill_evidence([_solved("ghost")], {})

    assert evidence == {}


def test_prerequisites_are_not_counted_as_targets() -> None:
    """Prerequisites are assumed knowledge, not skills the exercise develops."""
    problem = Problem(
        metadata=ProblemMetadata(id="a", title="A", target_skills=["loop_bounds"]),
        statement_md="# P",
        pedagogy=Pedagogy(prerequisites=["for_loops", "if_else"]),
    )

    evidence = PracticeSequencer().skill_evidence([_solved("a")], {"a": problem})

    assert "loop_bounds" in evidence
    assert "for_loops" not in evidence


# --- skill evidence shape --------------------------------------------------


def test_skill_evidence_reports_rates() -> None:
    evidence = SkillEvidence(tag="t", attempts=4, solved=3, fails=1)

    assert evidence.solved_rate == 0.75
    assert evidence.attempted is True


def test_skill_evidence_without_attempts() -> None:
    evidence = SkillEvidence(tag="t")

    assert evidence.solved_rate == 0.0
    assert evidence.attempted is False


def test_needs_hints_predicate() -> None:
    assert SkillEvidence(tag="t", attempts=2, solved=2, solves_without_hints=0).needs_hints
    assert not SkillEvidence(tag="t", attempts=2, solved=2, solves_without_hints=1).needs_hints
