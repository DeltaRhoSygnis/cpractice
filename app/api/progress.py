"""Progress and history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["progress"])


@router.get("/attempts")
def list_attempts(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    problem_id: str | None = Query(default=None, max_length=64),
) -> dict:
    """List recent attempts, newest first."""
    attempts = request.app.state.attempt_repository.recent(
        limit=limit, problem_id=problem_id
    )

    return {
        "count": len(attempts),
        "attempts": [
            {
                "id": a.id,
                "problem_id": a.problem_id,
                "created_at": a.created_at,
                "verdict": a.verdict,
                "passed": a.passed,
                "total": a.total,
                "hints_used": a.hints_used,
                "duration_ms": a.duration_ms,
                "succeeded": a.succeeded,
            }
            for a in attempts
        ],
    }


@router.get("/attempts/{attempt_id}")
def get_attempt(request: Request, attempt_id: int) -> dict:
    """Read one attempt and its per-test results."""
    repository = request.app.state.attempt_repository
    attempt = repository.get(attempt_id)

    if attempt is None:
        raise HTTPException(status_code=404, detail=f"no attempt {attempt_id}")

    return {
        "id": attempt.id,
        "problem_id": attempt.problem_id,
        "created_at": attempt.created_at,
        "verdict": attempt.verdict,
        "passed": attempt.passed,
        "total": attempt.total,
        "hints_used": attempt.hints_used,
        "duration_ms": attempt.duration_ms,
        "succeeded": attempt.succeeded,
        "test_results": repository.test_results(attempt_id),
    }


@router.get("/progress")
def progress(request: Request) -> dict:
    """Summarise practice history in observed terms."""
    return request.app.state.attempt_repository.progress()


@router.get("/recommendations")
def recommendations(
    request: Request,
    limit: int = Query(default=3, ge=1, le=10),
    skill: str | None = Query(default=None, max_length=64),
) -> dict:
    """Suggest next exercises, driven by recorded evidence.

    Weakness-based when history supports it; explicitly labelled as exploratory
    otherwise, so the difference is never hidden. A ``skill`` query parameter
    targets a specific skill instead.
    """
    planner = request.app.state.adaptive_planner
    sequencer = request.app.state.practice_sequencer
    plans = request.app.state.problem_service.list_problems()
    attempts = request.app.state.attempt_repository.recent(limit=200)

    solved = {
        problem.id
        for problem in plans
        if any(
            a.problem_id == problem.id and a.succeeded for a in attempts
        )
    }

    problems_by_id = {p.id: p for p in plans}

    # The sequencer decides *what shape* the next exercise should be.
    sequence = sequencer.next_exercise(
        attempts=attempts,
        problems_by_id=problems_by_id,
        requested_skill=skill,
    )

    results = planner.recommend(
        problems=plans, attempts=attempts, solved_problem_ids=solved, limit=limit
    )

    return {
        "count": len(results),
        "evidence_based": any(not r.exploratory for r in results),
        "next": {
            "skill": sequence.skill_tag,
            "role": sequence.role.value,
            "reason": sequence.reason.value,
            "explanation": sequence.explanation,
            "evidence": sequence.evidence,
        },
        "recommendations": [
            {
                "problem_id": r.problem_id,
                "title": r.title,
                "difficulty": r.difficulty,
                "topics": r.topics,
                "reason": r.reason,
                "exploratory": r.exploratory,
                "evidence": r.evidence,
            }
            for r in results
        ],
    }


@router.get("/curriculum")
def curriculum(request: Request) -> dict:
    """The C stage map and the operational skill definitions."""
    from app.services.curriculum import SKILLS, STAGES

    return {
        "stages": [
            {
                "index": s.index,
                "name": s.name,
                "concepts": list(s.concepts),
                "reasoning_practice": s.reasoning_practice,
            }
            for s in STAGES
        ],
        "skills": [
            {
                "tag": skill.tag,
                "name": skill.name,
                "stage": skill.stage,
                # What observable performance demonstrates the skill.
                "demonstrates": list(skill.demonstrates),
            }
            for skill in SKILLS.values()
        ],
    }


@router.get("/usage")
def usage(request: Request) -> dict:
    """Report AI provider usage and remaining daily budget."""
    settings = request.app.state.settings
    ledger = request.app.state.usage_ledger
    today = ledger.today()

    budget = settings.ai_daily_request_budget
    remaining = None if budget <= 0 else max(0, budget - today.requests)

    return {
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "today": {
            "requests": today.requests,
            "failures": today.failures,
            "input_tokens": today.input_tokens,
            "output_tokens": today.output_tokens,
            "total_tokens": today.total_tokens,
        },
        "budget": {
            "daily_limit": budget,
            "remaining": remaining,
            "unlimited": budget <= 0,
        },
        "recent": ledger.recent(limit=20),
    }
