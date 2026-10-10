"""Problem API endpoints.

Response models are deliberately **narrower** than the internal schemas:
hidden test content (stdin, expected stdout) is never sent to the client.
Only the count and names of hidden tests are exposed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas.problem import Problem
from app.storage.problem_repository import ProblemNotFoundError, ProblemValidationError

router = APIRouter(prefix="/problems", tags=["problems"])


def _public_test_summary(test) -> dict:
    """Safe representation of a public test."""
    return {
        "id": test.id,
        "name": test.name,
        "stdin": test.stdin,
        "expected_stdout": test.expected_stdout,
    }


def _hidden_test_summary(test) -> dict:
    """Hidden tests expose only identity - never input or expected output."""
    return {"id": test.id, "name": test.name}


def _problem_detail(problem: Problem, *, include_solution: bool = False) -> dict:
    """Build the client-safe view of a problem."""
    payload = {
        "id": problem.id,
        "version": problem.metadata.version,
        "title": problem.title,
        "difficulty": problem.metadata.difficulty.value,
        "topics": problem.metadata.topics,
        "target_skills": problem.metadata.target_skills,
        "language": problem.metadata.language,
        "entrypoint": problem.metadata.entrypoint,
        "comparison": problem.metadata.comparison.value,
        "time_limit_ms": problem.metadata.time_limit_ms,
        "memory_limit_mb": problem.metadata.memory_limit_mb,
        "status": problem.metadata.status.value,
        "statement_md": problem.statement_md,
        "starter_code": problem.starter_code,
        "public_tests": [_public_test_summary(t) for t in problem.public_tests],
        "hidden_test_count": len(problem.hidden_tests),
        "hidden_tests": [_hidden_test_summary(t) for t in problem.hidden_tests],
        "hint_count": len(problem.hints),
        "max_hint_level": problem.max_hint_level,
    }

    # Pedagogical framing, if the problem declares it. Author-only fields
    # (the solution outline) are withheld so the intended approach is not
    # disclosed before the learner attempts it.
    if problem.pedagogy is not None:
        pedagogy = problem.pedagogy
        payload["pedagogy"] = {
            "primary_objective": pedagogy.primary_objective,
            "exercise_role": pedagogy.exercise_role.value,
            "prerequisites": pedagogy.prerequisites,
            "target_reasoning_moves": pedagogy.target_reasoning_moves,
            "transfer_goal": pedagogy.transfer_goal,
        }

    # Solution content is only included when explicitly requested.
    if include_solution:
        payload["solution_explanation"] = problem.solution_explanation
        payload["reference_solution"] = problem.reference_solution

    return payload


@router.get("")
def list_problems(request: Request) -> dict:
    """List saved problem packages (summaries only)."""
    problems = request.app.state.problem_service.list_problems()

    return {
        "count": len(problems),
        "problems": [
            {
                "id": p.id,
                "version": p.metadata.version,
                "title": p.title,
                "difficulty": p.metadata.difficulty.value,
                "topics": p.metadata.topics,
                "status": p.metadata.status.value,
                "test_count": len(p.tests),
            }
            for p in problems
        ],
    }


@router.get("/{problem_id}")
def get_problem(request: Request, problem_id: str) -> dict:
    """Read one problem package, with hidden test content withheld."""
    try:
        problem = request.app.state.problem_service.get(problem_id)
    except ProblemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProblemValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _problem_detail(problem)
