"""Provider adapter interface.

Every AI provider implements :class:`AIProvider`. The rest of the application
depends only on this interface, never on a vendor SDK or response format.

Error taxonomy matters for retry policy: only *retryable* failures should be
retried, and quota exhaustion must not be retried indefinitely.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# --- Error taxonomy --------------------------------------------------------


class AIProviderError(RuntimeError):
    """Base class for all provider failures."""


class AuthError(AIProviderError):
    """Invalid or missing credentials. Not retryable."""


class InvalidRequestError(AIProviderError):
    """The request was rejected as malformed or unsupported. Not retryable."""


class RateLimitError(AIProviderError):
    """Quota exhausted or rate limited. Retry only with backoff, if at all."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(AIProviderError):
    """Temporary network or server failure. Retryable with backoff."""


class MalformedResponseError(AIProviderError):
    """The provider returned output that could not be parsed. Retryable once."""


# --- Result types ----------------------------------------------------------


@dataclass(frozen=True)
class UsageRecord:
    """Token/usage metadata reported by a provider, when available."""

    provider: str
    model: str
    operation: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResponse:
    """Raw text plus usage metadata from a provider call."""

    text: str
    usage: UsageRecord | None = None


# --- Interface -------------------------------------------------------------


class AIProvider(ABC):
    """Common interface implemented by every AI provider adapter."""

    #: Human-readable provider name, e.g. ``"google"``.
    name: str = "unknown"
    #: Model identifier in use.
    model: str = "unknown"

    @abstractmethod
    def generate(self, *, system: str, prompt: str, operation: str = "generate") -> GenerationResponse:
        """Send a prompt and return the raw text response.

        Implementations must raise a subclass of :class:`AIProviderError`
        rather than leaking vendor-specific exceptions.
        """

    @abstractmethod
    def check_connectivity(self) -> bool:
        """Return True when the provider is reachable and credentials work."""

    # -- capability reporting ---------------------------------------------

    def capabilities(self) -> dict[str, Any]:
        """Report static capabilities relevant to callers."""
        return {
            "provider": self.name,
            "model": self.model,
            "structured_output": False,
        }
