"""CPractice FastAPI application entry point.

Run locally with::

    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.ai.base import AIProviderError, AuthError
from app.ai.cache import GenerationCache
from app.ai.google import GoogleProvider
from app.ai.kenari import KenariProvider
from app.ai.rate_limits import RetryPolicy
from app.api import generation, health, problems, progress, submissions
from app.config import Settings, get_settings
from app.feedback.hint_service import HintService
from app.generation.pipeline import GenerationPipeline
from app.services.adaptive_service import AdaptivePlanner
from app.services.problem_service import ProblemService
from app.services.submission_service import SubmissionService
from app.storage.attempt_repository import AttemptRepository, ProblemIndex
from app.storage.database import Database
from app.storage.problem_repository import ProblemRepository
from app.storage.usage_ledger import LedgeredProvider, UsageLedger

logger = logging.getLogger("cpractice")


def _ensure_directories(settings: Settings) -> None:
    """Create the runtime directories the application expects."""
    settings.problems_path.mkdir(parents=True, exist_ok=True)
    settings.workspaces_path.mkdir(parents=True, exist_ok=True)
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)


def _build_generation_pipeline(settings: Settings, ledger: UsageLedger) -> GenerationPipeline | None:
    """Build the AI generation pipeline, or None when no provider is configured.

    The application must start without AI credentials: offline practice with
    saved exercises is a first-class use case (design decision #4).
    """
    provider = None

    if settings.ai_provider == "kenari":
        try:
            provider = KenariProvider(
                settings.kenari_api_key,
                model=settings.ai_model,
                base_url=settings.kenari_base_url,
            )
        except AuthError:
            logger.warning("no KENARI_API_KEY configured; AI generation is disabled")
            return None
    elif settings.ai_provider == "google":
        try:
            provider = GoogleProvider(settings.google_api_key, model=settings.ai_model)
        except AuthError:
            logger.warning("no GOOGLE_API_KEY configured; AI generation is disabled")
            return None
    else:
        logger.warning("unknown AI provider %r; generation disabled", settings.ai_provider)
        return None

    # Wrap so every call is recorded and the daily budget is enforced.
    recorded = LedgeredProvider(provider, ledger, daily_budget=settings.ai_daily_request_budget)

    return GenerationPipeline(
        recorded,
        problems_dir=settings.problems_path,
        cache=GenerationCache(settings.problems_path / ".cache"),
        retry_policy=RetryPolicy(
            max_attempts=settings.ai_max_retries,
            backoff_base_seconds=settings.ai_backoff_base_seconds,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup/shutdown hooks."""
    settings: Settings = app.state.settings
    _ensure_directories(settings)

    database = Database(settings.database_file)
    app.state.database = database
    app.state.attempt_repository = AttemptRepository(database)
    app.state.problem_index = ProblemIndex(database)
    app.state.usage_ledger = UsageLedger(database)
    app.state.adaptive_planner = AdaptivePlanner()

    # Index the problem packages that already exist on disk.
    _sync_problem_index(app)

    app.state.generation_pipeline = _build_generation_pipeline(settings, app.state.usage_ledger)
    # Reuse the pipeline's provider for hint generation; stored hints work
    # regardless, so this stays optional.
    provider = app.state.generation_pipeline.provider if app.state.generation_pipeline else None
    app.state.hint_service = HintService(provider)
    logger.info(
        "CPractice %s started (provider=%s, compiler=%s, ai=%s, db=%s)",
        settings.app_version,
        settings.ai_provider,
        settings.cc_compiler,
        "enabled" if app.state.generation_pipeline else "disabled",
        database.path.name,
    )
    yield
    logger.info("CPractice shutting down")


def _sync_problem_index(app: FastAPI) -> None:
    """Bring the problems table in step with the package directory."""
    service: ProblemService = app.state.problem_service
    index: ProblemIndex = app.state.problem_index

    problems = service.list_problems()
    paths = {
        problem.id: str(service.repository.package_dir(problem.id)) for problem in problems
    }
    try:
        index.sync(problems, paths)
    except Exception as exc:  # pragma: no cover - index is a convenience
        logger.warning("could not sync problem index: %s", exc)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI-powered C programming practice with deterministic grading. "
            "AI generates and explains; deterministic software grades."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.problem_service = ProblemService(ProblemRepository(settings.problems_path))
    app.state.submission_service = SubmissionService()

    # --- API routes ---
    app.include_router(health.router, prefix="/api")
    app.include_router(problems.router, prefix="/api")
    app.include_router(generation.router, prefix="/api")
    app.include_router(submissions.router, prefix="/api")
    app.include_router(progress.router, prefix="/api")

    # --- Static frontend ---
    # Mounted last so it never shadows /api routes.
    if settings.web_dir.is_dir():

        class NoCacheStaticFiles(StaticFiles):
            """Serve assets without letting the browser reuse stale copies.

            During development the browser would otherwise keep a cached
            ``app.js`` and never pick up changes, which looks like the UI
            "not updating". Revalidation is cheap on localhost.
            """

            def file_response(self, *args, **kwargs):
                response = super().file_response(*args, **kwargs)
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
                return response

        app.mount(
            "/",
            NoCacheStaticFiles(directory=settings.web_dir, html=True),
            name="web",
        )

    return app


app = create_app()
