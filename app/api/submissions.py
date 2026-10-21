"""Submission and learning-feedback endpoints.

Routes are registered inside the problems prefix but kept in their own module
so the problems module stays focused on read access.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.feedback.hint_service import (
    HintForbiddenError,
    HintUnavailableError,
)
from app.services.submission_service import SubmissionError
from app.storage.problem_repository import ProblemNotFoundError, ProblemValidationError

logger = logging.getLogger("cpractice")

router = APIRouter(prefix="/problems", tags=["submissions"])


class SubmitRequest(BaseModel):
    """A learner's C source submission."""

    source: str = Field(min_length=1)
    #: How many hints the learner has already consumed, for ladder position.
    hints_used: int = Field(default=0, ge=0, le=5)
    #: Optional hypothesis: what the learner expects the program to print
    #: (spec S6). Recorded and diffed, never graded.
    predicted_stdout: str | None = Field(default=None, max_length=4096)


class HintRequest(BaseModel):
    """A request for the next hint (or a specific level)."""

    hints_used: int = Field(default=0, ge=0, le=5)
    level: int | None = Field(default=None, ge=1, le=5)
    source: str = ""
    failure_summary: str = Field(default="", max_length=2000)


class SolutionRequest(BaseModel):
    """Explicit solution reveal."""

    confirm: bool = False


def _load_problem(request: Request, problem_id: str):
    """Load a problem, translating repository errors into HTTP responses."""
    try:
        return request.app.state.problem_service.get(problem_id)
    except ProblemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProblemValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{problem_id}/submit")
def submit(request: Request, problem_id: str, body: SubmitRequest) -> dict:
    """Compile and run a submission against the problem's tests."""
    problem = _load_problem(request, problem_id)

    try:
        outcome = request.app.state.submission_service.submit(
            problem, body.source, predicted_stdout=body.predicted_stdout
        )
    except SubmissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = outcome.payload
    payload["hints_used"] = body.hints_used
    payload["next_action"] = _next_action(outcome.report, problem, body.hints_used)

    # Persist the attempt so history and progress reflect real usage.
    try:
        attempt_id = request.app.state.attempt_repository.record(
            outcome.report,
            problem_id=problem.id,
            hints_used=body.hints_used,
            verdict=payload["verdict"],
            predicted_stdout=body.predicted_stdout,
        )
        payload["attempt_id"] = attempt_id
    except Exception as exc:  # pragma: no cover - history is best-effort
        # A storage failure must not lose the grading result the learner needs.
        logger.warning("could not record attempt: %s", exc)
        payload["attempt_id"] = None

    return payload


@router.post("/{problem_id}/hint")
def hint(request: Request, problem_id: str, body: HintRequest) -> dict:
    """Serve the next progressive hint, or a specific level."""
    problem = _load_problem(request, problem_id)
    service = request.app.state.hint_service

    try:
        if body.level is not None:
            result = service.get_level(
                problem,
                level=body.level,
                learner_code=body.source,
                observed_failure=body.failure_summary,
            )
        else:
            result = service.next_hint(
                problem,
                levels_used=body.hints_used,
                learner_code=body.source,
                observed_failure=body.failure_summary,
            )
    except HintForbiddenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HintUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    state = service.state(problem, levels_used=result.level)

    return {
        "level": result.level,
        "text": result.text,
        "source": result.source,
        "is_solution_reveal": result.is_solution_reveal,
        "hints_used": result.level,
        "next_level": None if state.exhausted else state.next_level,
        "solution_available": state.solution_available,
    }


@router.post("/{problem_id}/solution")
def solution(request: Request, problem_id: str, body: SolutionRequest) -> dict:
    """Reveal the reference solution. Requires explicit confirmation."""
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="solution reveal must be confirmed explicitly (confirm=true)",
        )

    problem = _load_problem(request, problem_id)

    try:
        reference = request.app.state.hint_service.reveal_solution(problem)
    except HintUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "problem_id": problem.id,
        "reference_solution": reference,
        "solution_explanation": problem.solution_explanation,
    }


def _next_action(report, problem, hints_used: int) -> str:
    """Suggest what the learner should do next, based on observed facts."""
    if report.all_passed:
        return "done"
    if not report.compilation.success:
        return "fix_compilation"
    if problem.max_hint_level > hints_used:
        return "request_hint"
    return "review_and_retry"
