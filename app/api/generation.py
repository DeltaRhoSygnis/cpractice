"""Generation API endpoints.

Exposes problem generation through the HTTP layer. The endpoint reports the
quality gate's findings so a rejection is explained rather than silent.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.ai.base import (
    AIProviderError,
    AuthError,
    InvalidRequestError,
    MalformedResponseError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.generation.pipeline import GenerationError
from app.generation.prompts import GenerationRequest

router = APIRouter(prefix="/problems", tags=["generation"])


class GenerateRequest(BaseModel):
    """Client-supplied generation parameters."""

    topic: str = Field(default="loops", min_length=1, max_length=100)
    difficulty: str = Field(default="beginner", pattern="^(beginner|intermediate|advanced)$")
    target_skills: list[str] = Field(default_factory=list, max_length=10)
    constraints: str = Field(default="", max_length=500)
    forbidden: list[str] = Field(default_factory=list, max_length=10)
    hints_enabled: bool = True
    use_cache: bool = True


@router.post("/generate")
def generate_problem(request: Request, body: GenerateRequest) -> dict:
    """Generate, validate, and save a new problem package."""
    pipeline = getattr(request.app.state, "generation_pipeline", None)
    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI provider is not configured. Set KENARI_API_KEY "
                "(or select another provider via AI_PROVIDER)."
            ),
        )

    generation_request = GenerationRequest(
        topic=body.topic,
        difficulty=body.difficulty,
        target_skills=body.target_skills,
        constraints=body.constraints,
        forbidden=body.forbidden,
        hints_enabled=body.hints_enabled,
    )

    try:
        outcome = pipeline.generate(generation_request, use_cache=body.use_cache)
    except AuthError as exc:
        raise HTTPException(status_code=502, detail=f"AI authentication failed: {exc}") from exc
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"AI quota or rate limit reached: {exc}",
        ) from exc
    except InvalidRequestError as exc:
        raise HTTPException(status_code=502, detail=f"AI rejected the request: {exc}") from exc
    except MalformedResponseError as exc:
        raise HTTPException(status_code=502, detail=f"AI returned unusable output: {exc}") from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"AI provider unavailable: {exc}") from exc
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail=f"generated problem was rejected: {exc}") from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    quality = outcome.quality

    return {
        "accepted": outcome.accepted,
        "from_cache": outcome.from_cache,
        "problem_id": outcome.problem.id,
        "status": outcome.problem.metadata.status.value,
        "reference": {
            "compiled": quality.reference_compiled,
            "passed": quality.reference_passed,
            "total": quality.reference_total,
        },
        "errors": [f.to_dict() for f in quality.errors],
        "warnings": [f.to_dict() for f in quality.warnings],
    }
