"""Application configuration.

All settings are loaded from environment variables (optionally via a local
``.env`` file). Secrets are never hard-coded and never committed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root: this file lives at <root>/app/config.py
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration for CPractice."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "CPractice"
    app_version: str = "0.1.0"
    debug: bool = False

    # --- Server ---
    # Localhost by default. Never bind to 0.0.0.0 without a security review.
    host: str = "127.0.0.1"
    port: int = 8000

    # --- AI provider ---
    ai_provider: str = "kenari"
    ai_model: str = "deepseek-v4-1-flash"

    # Kenari gateway (OpenAI-compatible) - primary provider.
    kenari_api_key: str | None = None
    kenari_base_url: str = "https://kenari.id/v1"

    # Google AI Studio / Gemini (alternative adapter).
    google_api_key: str | None = None

    ai_max_retries: int = 3
    ai_backoff_base_seconds: float = 2.0
    ai_max_concurrent_requests: int = 2
    ai_daily_request_budget: int = 0  # 0 = unlimited

    # --- Grading engine ---
    cc_compiler: str = "gcc"
    cc_standard: str = "c11"
    run_wall_timeout_ms: int = 3000
    run_memory_limit_mb: int = 128
    run_max_output_bytes: int = 65536

    # --- Storage ---
    database_path: Path = Field(default=Path("data/cpractice.db"))
    problems_dir: Path = Field(default=Path("problems"))
    workspaces_dir: Path = Field(default=Path("workspaces"))

    # --- Derived paths (absolute) ---
    @property
    def database_file(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def problems_path(self) -> Path:
        path = Path(self.problems_dir)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def workspaces_path(self) -> Path:
        path = Path(self.workspaces_dir)
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def web_dir(self) -> Path:
        return ROOT_DIR / "web"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()
