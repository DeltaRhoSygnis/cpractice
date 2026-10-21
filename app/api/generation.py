"""Generation API endpoints.

Exposes problem generation through the HTTP layer. The endpoint reports the
quality gate's findings so a rejection is explained rather than silent.

A second endpoint prepares a *shelf* of problem sets in one provider run
(spec S7). It reuses the same pipeline and the same gate: batching changes when
and how many calls are made, never what is accepted.
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
from app.api.preferences import KnownConceptsStore
from app.generation.batch import ShelfItem, ShelfRunner
from app.generation.pipeline import GenerationError
from app.generation.prompts import GenerationRequest
from app.schemas.pedagogy import ExerciseRole

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
    #: Which role the exercise should play in the practice sequence.
    exercise_role: str = Field(
        default="core_reasoning",
        pattern=(
            "^(diagnostic_warmup|core_reasoning|transfer|challenge|debugging|reflection)$"
        ),
    )
    #: Concepts the learner already knows; nothing else is required.
    prerequisites: list[str] = Field(default_factory=list, max_length=12)
    #: ``exercise`` (default) or ``problem_set`` (spec S7).
    kind: str = Field(default="exercise", pattern="^(exercise|problem_set)$")
    #: The one new concept a problem set introduces. Required for problem sets.
    new_concept: str = Field(default="", max_length=64)
    #: Known concepts the new one is combined with. Required for problem sets.
    assumed_known: list[str] = Field(default_factory=list, max_length=12)


def _known_concepts(request: Request) -> list[str]:
    """The learner's stored checklist, or empty when none has been saved.

    The checklist is the explicit "known" side of the concept ladder (spec S3)
    and is the source of truth for problem-set legality. Reading it per request
    keeps generation in step with a checklist the learner edits at any time.
    """
    try:
        store = KnownConceptsStore(request.app.state.database.connect())
    except AttributeError:  # pragma: no cover - app always wires the database
        return []
    return store.get()


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

    from app.schemas.problem import ProblemKind

    try:
        kind = ProblemKind(body.kind)
    except ValueError as exc:  # pragma: no cover - the field pattern guards this
        raise HTTPException(status_code=422, detail=f"unknown kind: {body.kind}") from exc

    generation_request = GenerationRequest(
        topic=body.topic,
        difficulty=body.difficulty,
        target_skills=body.target_skills,
        constraints=body.constraints,
        forbidden=body.forbidden,
        hints_enabled=body.hints_enabled,
        kind=kind,
        new_concept=body.new_concept,
        assumed_known=body.assumed_known,
    )

    try:
        outcome = pipeline.generate(
            generation_request,
            use_cache=body.use_cache,
            exercise_role=ExerciseRole(body.exercise_role),
            prerequisites=body.prerequisites,
            known_concepts=_known_concepts(request),
        )
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


# --- batch shelf preparation (spec S7) --------------------------------------


class BatchItemRequest(GenerateRequest):
    """One pset to prepare in a shelf run.

    It carries the same parameters as a single generation request, plus an
    optional ``custom_id`` echoed in the report so a caller can match outcomes
    to inputs.
    """

    custom_id: str = Field(default="", max_length=64)


class BatchRequest(BaseModel):
    """A shelf of psets to prepare in one provider run."""

    items: list[BatchItemRequest] = Field(min_length=1, max_length=50)
    #: A caller-supplied job id, recorded as provenance. Derived when absent.
    job_id: str = Field(default="", max_length=128)


def _batch_provider(request: Request):
    """The app's batch provider, or None when none is configured."""
    return getattr(request.app.state, "batch_provider", None)


@router.post("/batch")
def prepare_batch(request: Request, body: BatchRequest) -> dict:
    """Prepare a shelf of problem sets in one batch provider run.

    The endpoint is provider-gated like single generation: without a batch
    provider it returns 503. Per-item failures are reported, not raised, so a
    partial shelf is a successful response (spec S10).
    """
    pipeline = getattr(request.app.state, "generation_pipeline", None)
    batch_provider = _batch_provider(request)
    if pipeline is None or batch_provider is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No batch AI provider is configured. Set GOOGLE_API_KEY "
                "(Gemini Batch API) or use single-request generation."
            ),
        )

    from app.schemas.problem import ProblemKind

    shelf_items: list[ShelfItem] = []
    for index, item in enumerate(body.items):
        try:
            kind = ProblemKind(item.kind)
        except ValueError as exc:  # pragma: no cover - the field pattern guards this
            raise HTTPException(status_code=422, detail=f"unknown kind: {item.kind}") from exc

        shelf_items.append(
            ShelfItem(
                custom_id=item.custom_id or f"item-{index:03d}",
                request=GenerationRequest(
                    topic=item.topic,
                    difficulty=item.difficulty,
                    target_skills=item.target_skills,
                    constraints=item.constraints,
                    forbidden=item.forbidden,
                    hints_enabled=item.hints_enabled,
                    kind=kind,
                    new_concept=item.new_concept,
                    assumed_known=item.assumed_known,
                ),
            )
        )

    settings = request.app.state.settings
    provenance_store = getattr(request.app.state, "batch_provenance_store", None)
    runner = ShelfRunner(
        pipeline=pipeline,
        batch_provider=batch_provider,
        problems_dir=settings.problems_path,
        provenance_store=provenance_store,
        daily_budget=settings.ai_daily_request_budget,
        requests_today=_requests_today(request),
        known_concepts=_known_concepts(request),
    )

    job_id = body.job_id or f"api-batch-{len(shelf_items)}"

    try:
        report = runner.prepare(shelf_items, job_id=job_id)
    except AuthError as exc:
        raise HTTPException(status_code=502, detail=f"AI authentication failed: {exc}") from exc
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"AI quota or rate limit reached: {exc}",
        ) from exc
    except InvalidRequestError as exc:
        raise HTTPException(status_code=502, detail=f"AI rejected the batch: {exc}") from exc
    except MalformedResponseError as exc:
        raise HTTPException(status_code=502, detail=f"AI returned unusable output: {exc}") from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"AI provider unavailable: {exc}") from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    return report.to_dict()


def _requests_today(request: Request) -> int:
    """Provider requests already made today, for the shared daily budget."""
    ledger = getattr(request.app.state, "usage_ledger", None)
    if ledger is None:
        return 0
    try:
        return ledger.today().requests
    except Exception:  # pragma: no cover - the ledger is a convenience here
        return 0
