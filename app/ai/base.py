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


# --- Batch request/response ------------------------------------------------


@dataclass(frozen=True)
class BatchRequest:
    """One item in a batch: a prompt plus a caller-supplied correlation id.

    The ``custom_id`` is echoed back by the provider so a batch result can be
    matched to the request that produced it, regardless of completion order.
    It carries no content of its own - the shelf runner uses it to recover the
    originating :class:`app.generation.prompts.GenerationRequest`.
    """

    custom_id: str
    system: str
    prompt: str
    operation: str = "generate"
    json_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class BatchItemResult:
    """The outcome of a single batch item.

    Exactly one of ``text`` (success) or ``error`` (failure) is set. A
    per-item failure is data, not an exception: one bad item must not fail the
    job (spec S7, S10). ``error`` is an :class:`AIProviderError` instance so
    the caller can classify it with the shared taxonomy.
    """

    custom_id: str
    text: str | None = None
    usage: UsageRecord | None = None
    error: AIProviderError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.text is not None


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


class BatchProvider(ABC):
    """Capability for submitting many requests as one job (spec S7).

    Batching is a **transport** change, not an acceptance change: a batch
    adapter returns raw text per item, and the same
    :class:`app.generation.pipeline.GenerationPipeline` plus the same
    :class:`app.generation.quality_gate.QualityGate` decide validity. It is a
    separate interface so an adapter can implement interactive generation, batch
    generation, or both, without ``AIProvider.generate`` changing for providers
    that only do one.

    Implementations must:

    * raise a subclass of :class:`AIProviderError` for a job-level failure
      (auth, unavailable, invalid request) rather than leak vendor exceptions;
    * report a *per-item* failure inside the returned list, never by raising, so
      one bad item does not fail the whole job;
    * echo ``custom_id`` so results can be matched to requests.
    """

    #: Human-readable provider name, e.g. ``"google-batch"``.
    name: str = "unknown-batch"
    #: Model identifier in use.
    model: str = "unknown"

    @abstractmethod
    def submit(self, requests: list[BatchRequest]) -> list[BatchItemResult]:
        """Submit ``requests`` as one batch and return one result per request.

        The returned list has exactly one entry per input request, matched by
        ``custom_id``. A job-level failure (the whole batch could not be
        submitted or retrieved) raises an :class:`AIProviderError`; a failure
        confined to one item is reported as a :class:`BatchItemResult` carrying
        ``error``.
        """

    def check_connectivity(self) -> bool:
        """Return True when the batch endpoint is reachable and authorized."""
        return True

    # -- capability reporting ---------------------------------------------

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "batch": True,
        }
