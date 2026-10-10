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
from app.ai.rate_limits import RetryPolicy
from app.api import generation, health, problems
from app.config import Settings, get_settings
from app.generation.pipeline import GenerationPipeline
from app.services.problem_service import ProblemService
from app.storage.problem_repository import ProblemRepository

logger = logging.getLogger("cpractice")


def _ensure_directories(settings: Settings) -> None:
    """Create the runtime directories the application expects."""
    settings.problems_path.mkdir(parents=True, exist_ok=True)
    settings.workspaces_path.mkdir(parents=True, exist_ok=True)
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)


def _build_generation_pipeline(settings: Settings) -> GenerationPipeline | None:
    """Build the AI generation pipeline, or None when no provider is configured.

    The application must start without AI credentials: offline practice with
    saved exercises is a first-class use case (design decision #4).
    """
    provider = None

    if settings.ai_provider == "google":
        try:
            provider = GoogleProvider(settings.google_api_key, model=settings.ai_model)
        except AuthError:
            logger.warning("no GOOGLE_API_KEY configured; AI generation is disabled")
            return None
    else:
        logger.warning("unknown AI provider %r; generation disabled", settings.ai_provider)
        return None

    return GenerationPipeline(
        provider,
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
    app.state.generation_pipeline = _build_generation_pipeline(settings)
    logger.info(
        "CPractice %s started (provider=%s, compiler=%s, ai=%s)",
        settings.app_version,
        settings.ai_provider,
        settings.cc_compiler,
        "enabled" if app.state.generation_pipeline else "disabled",
    )
    yield
    logger.info("CPractice shutting down")


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

    # --- API routes ---
    app.include_router(health.router, prefix="/api")
    app.include_router(problems.router, prefix="/api")
    app.include_router(generation.router, prefix="/api")

    # --- Static frontend ---
    # Mounted last so it never shadows /api routes.
    if settings.web_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=settings.web_dir, html=True),
            name="web",
        )

    return app


app = create_app()
