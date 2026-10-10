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
