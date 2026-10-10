"""Tests for adaptive practice recommendations."""

from __future__ import annotations

from app.schemas.problem import Difficulty, Problem, ProblemMetadata, ProblemStatus
from app.services.adaptive_service import (
    AdaptivePlanner,
    build_weakness_brief,
)
from app.storage.attempt_repository import AttemptRecord


def _problem(
    pid: str,
    *,
    topics: list[str],
    difficulty: Difficulty = Difficulty.BEGINNER,
    status: ProblemStatus = ProblemStatus.VALIDATED,
) -> Problem:
    return Problem(
        metadata=ProblemMetadata(
            id=pid, title=pid.title(), topics=topics, difficulty=difficulty, status=status
        ),
        statement_md="x",
    )


def _attempt(pid: str, *, passed: int, total: int) -> AttemptRecord:
    return AttemptRecord(
        id=1, problem_id=pid, created_at="now", compilation_ok=True,
        passed=passed, total=total, verdict="passed" if passed == total else "partial",
        duration_ms=1, hints_used=0,
    )


# --- evidence ---------------------------------------------------------------


def test_no_history_yields_no_evidence() -> None:
    planner = AdaptivePlanner()
    problems = {"a": _problem("a", topics=["loops"])}

    evidence = planner.topic_evidence([], problems)

    assert evidence == {}


def test_evidence_aggregates_by_topic() -> None:
    planner = AdaptivePlanner()
    problems = {"a": _problem("a", topics=["loops", "io"])}
    attempts = [_attempt("a", passed=0, total=2), _attempt("a", passed=2, total=2)]

    evidence = planner.topic_evidence(attempts, problems)

    assert evidence["loops"].attempts == 2
    assert evidence["loops"].failures == 1
    assert evidence["loops"].solved == 1
    assert evidence["loops"].failure_rate == 0.5


def test_attempts_for_unknown_problems_are_ignored() -> None:
    planner = AdaptivePlanner()

    evidence = planner.topic_evidence([_attempt("ghost", passed=0, total=1)], {})

    assert evidence == {}


def test_single_attempt_is_not_yet_a_weakness_signal() -> None:
    """One failure is not evidence; the planner requires a minimum sample."""
    planner = AdaptivePlanner(min_attempts=2)
    problems = {"a": _problem("a", topics=["loops"])}

    weak = planner.weak_topics([_attempt("a", passed=0, total=2)], problems)

    assert weak == []


def test_repeated_failures_become_a_weakness_signal() -> None:
    planner = AdaptivePlanner(min_attempts=2)
    problems = {"a": _problem("a", topics=["loops"])}
    attempts = [_attempt("a", passed=0, total=2), _attempt("a", passed=0, total=2)]

    weak = planner.weak_topics(attempts, problems)

    assert [w.topic for w in weak] == ["loops"]


def test_fully_solved_topic_is_not_weak() -> None:
    planner = AdaptivePlanner(min_attempts=2)
    problems = {"a": _problem("a", topics=["loops"])}
    attempts = [_attempt("a", passed=2, total=2), _attempt("a", passed=2, total=2)]

    assert planner.weak_topics(attempts, problems) == []


def test_weak_topics_are_ordered_worst_first() -> None:
    planner = AdaptivePlanner(min_attempts=2)
    problems = {
        "a": _problem("a", topics=["loops"]),
        "b": _problem("b", topics=["recursion"]),
    }
    # Every attempt here is a failure (not fully solved), so both topics exceed
    # the minimum sample. The higher absolute failure count ranks first.
    attempts = [
        _attempt("a", passed=0, total=2),   # loops:     2 attempts, 2 failures
        _attempt("a", passed=0, total=2),
        _attempt("b", passed=0, total=2),   # recursion: 3 attempts, 3 failures
        _attempt("b", passed=0, total=2),
        _attempt("b", passed=0, total=2),
    ]

    weak = planner.weak_topics(attempts, problems)

    assert [w.topic for w in weak] == ["recursion", "loops"]


def test_partial_attempt_counts_as_a_failure_for_the_topic() -> None:
    """A topic is not solved until a problem in it is fully solved."""
    planner = AdaptivePlanner(min_attempts=1)
    problems = {"a": _problem("a", topics=["loops"])}

    evidence = planner.topic_evidence([_attempt("a", passed=1, total=2)], problems)

    assert evidence["loops"].failures == 1
    assert evidence["loops"].solved == 0


# --- recommendation ---------------------------------------------------------


def test_recommends_a_problem_in_the_weak_topic() -> None:
    planner = AdaptivePlanner(min_attempts=2)
    problems = [
        _problem("seen", topics=["loops"]),
        _problem("fresh", topics=["loops"]),
    ]
    attempts = [_attempt("seen", passed=0, total=2), _attempt("seen", passed=0, total=2)]

    recommendations = planner.recommend(problems=problems, attempts=attempts)

    assert recommendations[0].problem_id == "fresh"
    assert "loops" in recommendations[0].reason or "failed" in recommendations[0].reason


def test_recommendation_cites_observed_evidence() -> None:
    planner = AdaptivePlanner(min_attempts=2)
    problems = [_problem("seen", topics=["loops"]), _problem("fresh", topics=["loops"])]
    attempts = [_attempt("seen", passed=0, total=2), _attempt("seen", passed=0, total=2)]

    rec = planner.recommend(problems=problems, attempts=attempts)[0]

    assert rec.evidence["topic"] == "loops"
    assert rec.evidence["attempts"] == 2
    assert rec.evidence["failures"] == 2
    assert rec.exploratory is False


def test_recommendation_skips_already_solved_problems() -> None:
    planner = AdaptivePlanner(min_attempts=2)
    problems = [_problem("seen", topics=["loops"])]
    attempts = [_attempt("seen", passed=0, total=2), _attempt("seen", passed=0, total=2)]

    recs = planner.recommend(problems=problems, attempts=attempts, solved_problem_ids={"seen"})

    assert all(r.problem_id != "seen" for r in recs)


def test_prefers_easier_problem_within_a_weak_topic() -> None:
    planner = AdaptivePlanner(min_attempts=2)
    problems = [
        _problem("hard", topics=["loops"], difficulty=Difficulty.ADVANCED),
        _problem("easy", topics=["loops"], difficulty=Difficulty.BEGINNER),
    ]
    attempts = [_attempt("seen", passed=0, total=2), _attempt("seen", passed=0, total=2)]
    problems.append(_problem("seen", topics=["loops"]))

    rec = planner.recommend(problems=problems, attempts=attempts)[0]

    assert rec.problem_id == "easy"


def test_no_history_falls_back_to_exploratory_suggestions() -> None:
    planner = AdaptivePlanner()
    problems = [
        _problem("a", topics=["loops"], difficulty=Difficulty.BEGINNER),
        _problem("b", topics=["arrays"], difficulty=Difficulty.INTERMEDIATE),
    ]

    recs = planner.recommend(problems=problems, attempts=[])

    assert recs
    assert all(r.exploratory for r in recs)
    # Explicitly labelled as breadth, not a weakness match.
    assert "breadth" in recs[0].reason.lower()


def test_exploratory_suggestions_are_easiest_first() -> None:
    planner = AdaptivePlanner()
    problems = [
        _problem("hard", topics=["x"], difficulty=Difficulty.ADVANCED),
        _problem("easy", topics=["x"], difficulty=Difficulty.BEGINNER),
    ]

    recs = planner.recommend(problems=problems, attempts=[])

    assert recs[0].problem_id == "easy"


def test_recommendations_are_limited() -> None:
    planner = AdaptivePlanner()
    problems = [_problem(f"p{i}", topics=["x"]) for i in range(10)]

    recs = planner.recommend(problems=problems, attempts=[], limit=3)

    assert len(recs) == 3


def test_no_duplicate_recommendations() -> None:
    planner = AdaptivePlanner(min_attempts=2)
    problems = [_problem("only", topics=["loops"])]
    attempts = [_attempt("only", passed=0, total=2), _attempt("only", passed=0, total=2)]

    recs = planner.recommend(problems=problems, attempts=attempts)

    ids = [r.problem_id for r in recs]
    assert len(ids) == len(set(ids))


# --- weakness brief ---------------------------------------------------------


def test_brief_reports_no_signal_without_history() -> None:
    brief = build_weakness_brief(problems=[_problem("a", topics=["loops"])], attempts=[])

    assert brief.has_signal is False
    assert "No performance history" in brief.to_prompt_text()


def test_brief_includes_observed_weakness() -> None:
    problems = [_problem("a", topics=["loops"])]
    attempts = [_attempt("a", passed=0, total=2), _attempt("a", passed=0, total=2)]

    brief = build_weakness_brief(problems=problems, attempts=attempts)

    assert brief.has_signal is True
    text = brief.to_prompt_text()
    assert "loops" in text
    assert "2/2" in text
