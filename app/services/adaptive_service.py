"""Adaptive practice — recommend or generate exercises targeting weaknesses.

Recommendations are driven by **recorded evidence**, not by a guess. The rule
from the architecture spec is explicit: prefer recommending a relevant exercise
based on observed attempts over simply raising difficulty.

This module never invents a weakness. If there is no history for a topic, it
says so and falls back to a breadth-first suggestion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.problem import Difficulty, Problem
from app.storage.attempt_repository import AttemptRecord


@dataclass(frozen=True)
class TopicEvidence:
    """Observed performance for one topic."""

    topic: str
    attempts: int
    failures: int
    solved: int

    @property
    def failure_rate(self) -> float:
        return self.failures / self.attempts if self.attempts else 0.0

    @property
    def attempted(self) -> bool:
        return self.attempts > 0


@dataclass(frozen=True)
class Recommendation:
    """A suggested next exercise, with the evidence behind it."""

    problem_id: str
    title: str
    difficulty: str
    topics: list[str]
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    #: True when this is a breadth suggestion rather than evidence-driven.
    exploratory: bool = False


class AdaptivePlanner:
    """Turn attempt history into a defensible next-exercise suggestion."""

    #: A topic needs at least this many attempts before it can be called weak.
    MIN_ATTEMPTS_FOR_SIGNAL = 2

    def __init__(self, *, min_attempts: int = MIN_ATTEMPTS_FOR_SIGNAL) -> None:
        self.min_attempts = min_attempts

    # -- evidence ----------------------------------------------------------

    def topic_evidence(
        self,
        attempts: list[AttemptRecord],
        problems_by_id: dict[str, Problem],
    ) -> dict[str, TopicEvidence]:
        """Aggregate attempt outcomes by topic."""
        totals: dict[str, dict[str, int]] = {}

        for attempt in attempts:
            problem = problems_by_id.get(attempt.problem_id)
            if problem is None:
                continue
            for topic in problem.metadata.topics:
                bucket = totals.setdefault(topic, {"attempts": 0, "failures": 0, "solved": 0})
                bucket["attempts"] += 1
                if attempt.succeeded:
                    bucket["solved"] += 1
                else:
                    bucket["failures"] += 1

        return {
            topic: TopicEvidence(
                topic=topic,
                attempts=values["attempts"],
                failures=values["failures"],
                solved=values["solved"],
            )
            for topic, values in totals.items()
        }

    def weak_topics(
        self,
        attempts: list[AttemptRecord],
        problems_by_id: dict[str, Problem],
    ) -> list[TopicEvidence]:
        """Topics with enough evidence and a non-zero failure rate, worst first."""
        evidence = self.topic_evidence(attempts, problems_by_id)

        weak = [
            e
            for e in evidence.values()
            if e.attempts >= self.min_attempts and e.failures > 0
        ]

        # Order by failure rate, then by absolute failures, then name so the
        # result is deterministic.
        return sorted(weak, key=lambda e: (-e.failure_rate, -e.failures, e.topic))

    # -- recommendation ----------------------------------------------------

    def recommend(
        self,
        *,
        problems: list[Problem],
        attempts: list[AttemptRecord],
        solved_problem_ids: set[str] | None = None,
        limit: int = 3,
    ) -> list[Recommendation]:
        """Suggest next exercises, weakest topic first."""
        solved = solved_problem_ids or set()
        by_id = {p.id: p for p in problems}
        weak = self.weak_topics(attempts, by_id)

        recommendations: list[Recommendation] = []

        for evidence in weak:
            candidate = self._best_candidate(
                problems=problems,
                topic=evidence.topic,
                solved=solved,
                exclude={r.problem_id for r in recommendations},
            )
            if candidate is None:
                continue

            recommendations.append(
                Recommendation(
                    problem_id=candidate.id,
                    title=candidate.title,
                    difficulty=candidate.metadata.difficulty.value,
                    topics=candidate.metadata.topics,
                    reason=(
                        f"You have failed {evidence.failures} of {evidence.attempts} "
                        f"attempts on '{evidence.topic}'."
                    ),
                    evidence={
                        "topic": evidence.topic,
                        "attempts": evidence.attempts,
                        "failures": evidence.failures,
                        "solved": evidence.solved,
                        "failure_rate": round(evidence.failure_rate, 3),
                    },
                )
            )
            if len(recommendations) >= limit:
                return recommendations

        if len(recommendations) < limit:
            recommendations.extend(
                self._exploratory(
                    problems=problems,
                    solved=solved,
                    exclude={r.problem_id for r in recommendations},
                    limit=limit - len(recommendations),
                )
            )

        return recommendations

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _best_candidate(
        *,
        problems: list[Problem],
        topic: str,
        solved: set[str],
        exclude: set[str],
    ) -> Problem | None:
        """Pick the easiest unsolved problem covering ``topic``."""
        candidates = [
            p
            for p in problems
            if topic in p.metadata.topics and p.id not in solved and p.id not in exclude
        ]
        if not candidates:
            return None

        order = {
            Difficulty.BEGINNER: 0,
            Difficulty.INTERMEDIATE: 1,
            Difficulty.ADVANCED: 2,
        }
        return min(candidates, key=lambda p: (order[p.metadata.difficulty], p.id))

    @staticmethod
    def _exploratory(
        *,
        problems: list[Problem],
        solved: set[str],
        exclude: set[str],
        limit: int,
    ) -> list[Recommendation]:
        """Suggest unsolved problems when no weakness signal exists."""
        candidates = [
            p
            for p in problems
            if p.id not in solved and p.id not in exclude
            and p.metadata.status.value in ("validated", "draft")
        ]

        order = {
            Difficulty.BEGINNER: 0,
            Difficulty.INTERMEDIATE: 1,
            Difficulty.ADVANCED: 2,
        }
        candidates.sort(key=lambda p: (order[p.metadata.difficulty], p.id))

        return [
            Recommendation(
                problem_id=p.id,
                title=p.title,
                difficulty=p.metadata.difficulty.value,
                topics=p.metadata.topics,
                reason=(
                    "No performance history yet for your topics, so this is a "
                    "breadth suggestion rather than a weakness match."
                ),
                exploratory=True,
            )
            for p in candidates[:limit]
        ]


@dataclass(frozen=True)
class WeaknessBrief:
    """A plain-language summary of observed weaknesses, for a prompt or UI."""

    topics: list[dict[str, Any]]
    has_signal: bool

    def to_prompt_text(self) -> str:
        """Render the brief for inclusion in a generation prompt."""
        if not self.has_signal:
            return "No performance history yet."

        lines = ["Observed weak areas (from recorded attempts):"]
        for entry in self.topics:
            lines.append(
                f"- {entry['topic']}: {entry['failures']}/{entry['attempts']} attempts failed"
            )
        return "\n".join(lines)


def build_weakness_brief(
    *,
    problems: list[Problem],
    attempts: list[AttemptRecord],
) -> WeaknessBrief:
    """Summarise observed weaknesses for targeted generation."""
    planner = AdaptivePlanner()
    by_id = {p.id: p for p in problems}
    weak = planner.weak_topics(attempts, by_id)

    return WeaknessBrief(
        topics=[
            {
                "topic": e.topic,
                "attempts": e.attempts,
                "failures": e.failures,
                "solved": e.solved,
                "failure_rate": round(e.failure_rate, 3),
            }
            for e in weak
        ],
        has_signal=bool(weak),
    )
