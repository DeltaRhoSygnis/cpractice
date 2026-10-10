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

from app.api import health
from app.config import Settings, get_settings

logger = logging.getLogger("cpractice")


def _ensure_directories(settings: Settings) -> None:
    """Create the runtime directories the application expects."""
    settings.problems_path.mkdir(parents=True, exist_ok=True)
    settings.workspaces_path.mkdir(parents=True, exist_ok=True)
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup/shutdown hooks."""
    settings: Settings = app.state.settings
    _ensure_directories(settings)
    logger.info(
        "CPractice %s started (provider=%s, compiler=%s)",
        settings.app_version,
        settings.ai_provider,
        settings.cc_compiler,
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

    # --- API routes ---
    app.include_router(health.router, prefix="/api")

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
