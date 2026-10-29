"""Application configuration.

All settings are loaded from environment variables (optionally via a local
``.env`` file). Secrets are never hard-coded and never committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root: this file lives at <root>/app/config.py
ROOT_DIR = Path(__file__).resolve().parent.parent

#: Directory created for installed users when no source checkout is detected.
DEFAULT_HOME_NAME = ".cpractice"

#: Credential values shipped as examples. They are not real keys and must
#: never make the application believe an AI provider is configured.
PLACEHOLDER_KEY_VALUES = frozenset(
    {"your-kenari-key-here", "your-google-key-here", "change-me"}
)


def is_source_checkout(root: Path = ROOT_DIR) -> bool:
    """True when ``root`` looks like a CPractice source checkout.

    A source checkout keeps its runtime state beside the code, which preserves
    existing developer workflows. Installed packages do not ship the project
    metadata and fall back to a single writable home directory instead.
    """
    return (root / "pyproject.toml").is_file() and (root / "app" / "web").is_dir()


def resolve_home() -> Path:
    """Return the one directory CPractice may write to.

    Priority: the ``CPRACTICE_HOME`` override, then the source checkout root,
    then ``~/.cpractice`` for installed users.
    """
    override = (os.environ.get("CPRACTICE_HOME") or "").strip()
    if override:
        return Path(override).expanduser()
    if is_source_checkout():
        return ROOT_DIR
    return Path.home() / DEFAULT_HOME_NAME


@dataclass(frozen=True)
class ProviderSpec:
    """One AI provider adapter: the credential it needs and its default model.

    Providers are declared here and nowhere else. Adding a new adapter is a
    single new entry - the rest of the application asks these settings which
    provider is usable instead of hard-coding provider names.
    """

    #: The value used for ``AI_PROVIDER``.
    name: str
    #: The ``Settings`` field holding the credential for this provider.
    key_field: str
    #: The model used when the operator did not choose one explicitly.
    default_model: str


#: Every provider the application can talk to.
#:
#: A provider is usable when its credential is present. The selected provider
#: wins; otherwise any provider with a credential is used, so a machine holding
#: only one kind of key still gets a working generation pipeline.
AI_PROVIDERS: dict[str, ProviderSpec] = {
    "kenari": ProviderSpec("kenari", "kenari_api_key", "deepseek-v4-1-flash"),
    "google": ProviderSpec("google", "google_api_key", "gemini-2.0-flash"),
}


class Settings(BaseSettings):
    """Runtime configuration for CPractice."""

    model_config = SettingsConfigDict(
        env_file=resolve_home() / ".env",
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
    # Optional override for the writable home. ``resolve_home()`` supplies the
    # default when this is unset.
    cpractice_home: Path | None = None

    database_path: Path = Field(default=Path("data/cpractice.db"))
    problems_dir: Path = Field(default=Path("problems"))
    workspaces_dir: Path = Field(default=Path("workspaces"))

    @field_validator("cpractice_home", mode="before")
    @classmethod
    def _blank_home_is_unset(cls, value: object) -> object:
        """Treat a blank override as unset instead of resolving it to ``.``."""
        if value is not None and not str(value).strip():
            return None
        return value

    # --- Derived paths (absolute) ---
    @property
    def home(self) -> Path:
        """The writable home directory for this installation."""
        if self.cpractice_home:
            return Path(self.cpractice_home).expanduser()
        return resolve_home()

    @property
    def database_file(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else self.home / path

    @property
    def problems_path(self) -> Path:
        path = Path(self.problems_dir)
        return path if path.is_absolute() else self.home / path

    @property
    def workspaces_path(self) -> Path:
        path = Path(self.workspaces_dir)
        return path if path.is_absolute() else self.home / path

    @property
    def web_dir(self) -> Path:
        return Path(__file__).resolve().parent / "web"

    # --- AI provider resolution -------------------------------------------
    def ai_key_for(self, provider: str) -> str | None:
        """Return the credential configured for ``provider``, if any.

        Unknown providers have no credential field and therefore no key.
        """
        spec = AI_PROVIDERS.get(provider)
        if spec is None:
            return None
        value = (getattr(self, spec.key_field, None) or "").strip()
        if (
            not value
            or value.lower() in PLACEHOLDER_KEY_VALUES
            or value.lower().startswith("your-")
        ):
            return None
        return value

    @property
    def any_ai_key_configured(self) -> bool:
        """True when at least one provider credential is present.

        The check is credential-agnostic: it asks every declared provider
        instead of naming a fixed pair, so a newly added adapter is covered
        the moment it is registered.
        """
        return any(self.ai_key_for(spec.name) for spec in AI_PROVIDERS.values())

    @property
    def resolved_ai_provider(self) -> str | None:
        """The provider that will actually be used, or ``None`` offline.

        The selected provider wins when its credential is present. Otherwise
        any provider holding a credential is used, so a machine that has only
        one kind of key is not silently left without generation.
        """
        if self.ai_key_for(self.ai_provider):
            return self.ai_provider
        for spec in AI_PROVIDERS.values():
            if self.ai_key_for(spec.name):
                return spec.name
        return None

    @property
    def resolved_ai_model(self) -> str:
        """The model the resolved provider will be asked to use.

        An explicitly configured ``AI_MODEL`` always wins. Otherwise the
        resolved provider's own default is used, so the default model never
        belongs to a different provider than the credential.
        """
        if "ai_model" in self.model_fields_set:
            return self.ai_model
        provider = self.resolved_ai_provider
        if provider is None:
            return self.ai_model
        return AI_PROVIDERS[provider].default_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()
