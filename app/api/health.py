"""Health and readiness endpoints.

``/api/health`` answers a simple liveness question and reports which
capabilities are currently configured. It never exposes secret values -
only whether a capability is present.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


def _compiler_available(compiler: str) -> bool:
    """Return True if the configured C compiler is on PATH."""
    if shutil.which(compiler) is None:
        return False
    try:
        result = subprocess.run(
            [compiler, "--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    """Report application liveness and configured capabilities."""
    settings = request.app.state.settings

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "capabilities": {
            "compiler": {
                "configured": settings.cc_compiler,
                "available": _compiler_available(settings.cc_compiler),
            },
            "ai": {
                "provider": settings.ai_provider,
                "model": settings.ai_model,
                # Presence only - never the value.
                "key_configured": bool(settings.google_api_key),
            },
            "storage": {
                "problems_dir": settings.problems_path.is_dir(),
                "workspaces_dir": settings.workspaces_path.is_dir(),
            },
        },
    }
