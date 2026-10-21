"""Problem API endpoints.

Response models are deliberately **narrower** than the internal schemas:
hidden test content (stdin, expected stdout) is never sent to the client.
Only the count and names of hidden tests are exposed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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


# --- import ------------------------------------------------------------------

class ImportPackageRequest(BaseModel):
    """Import one problem package.

    ``package`` is a single JSON document shaped exactly like the problem
    packages on disk (metadata at the top level plus the content keys in
    ``app.schemas.problem.CONTENT_KEYS``, the same structure the AI generation
    pipeline writes as ``problem.json``). ``overwrite`` replaces an existing
    package with the same id only when explicitly requested.
    """

    package: dict[str, Any]
    overwrite: bool = False


@router.post("/import")
def import_problem(request: Request, body: ImportPackageRequest) -> dict:
    """Import one problem package and grade it with the deterministic gate.

    The gate is authoritative: a package that fails any required check is
    returned with its findings and is **never** written to disk (and never gets
    assigned a passing status). Only the default "hand-authored" gate profile
    applies — no calibration checker, mutation testing on, and concept
    legality for problem sets evaluated against the learner's own stored
    known-concepts checklist, exactly like AI-generated problem sets.
    """
    from pydantic import ValidationError

    from app.schemas.test_case import TestCase
    from app.services import problem_import
    from app.api.preferences import KnownConceptsStore

    try:
        problem_raw = problem_import.problem_from_payload(body.package)
    except problem_import.PackageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    problem_id = problem_raw.id

    service = request.app.state.problem_service
    if service.exists(problem_id) and not body.overwrite:
        raise HTTPException(
            status_code=409,
            detail=(
                f"a package with id '{problem_id}' already exists; "
                "resend with overwrite=true to replace it"
            ),
        )

    store = KnownConceptsStore(request.app.state.database.connect())
    report = problem_import.run_quality_gate(problem_raw, store.get())

    if not report.valid:
        return {
            "accepted": False,
            "problem_id": problem_id,
            "status": problem_raw.metadata.status.value,
            "reference": {
                "compiled": report.reference_compiled,
                "passed": report.reference_passed,
                "total": report.reference_total,
            },
            "errors": [f.to_dict() for f in report.errors],
            "warnings": [f.to_dict() for f in report.warnings],
        }

    problem = problem_import.validate_and_tag(problem_raw, report)
    problems_dir = request.app.state.settings.problems_path
    package_dir = problem_import.write_package(problems_dir, problem, report)

    # Keep the problem index (recommendations / progress) in step with the new
    # package. Mirrors main._sync_problem_index but only for this one problem.
    request.app.state.problem_index.upsert(problem, str(package_dir))

    return {
        "accepted": True,
        "problem_id": problem_id,
        "status": problem.metadata.status.value,
        "package_dir": str(package_dir),
        "reference": {
            "compiled": report.reference_compiled,
            "passed": report.reference_passed,
            "total": report.reference_total,
        },
        "errors": [f.to_dict() for f in report.errors],
        "warnings": [f.to_dict() for f in report.warnings],
    }
