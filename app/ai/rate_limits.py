"""Bounded retry with backoff.

Only *retryable* failures are retried. Authentication and invalid-request
errors are permanent and fail immediately; quota exhaustion is bounded so the
application cannot spin against a limit it cannot satisfy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.ai.base import (
    AIProviderError,
    AuthError,
    InvalidRequestError,
    MalformedResponseError,
    ProviderUnavailableError,
    RateLimitError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for bounded retry behaviour."""

    max_attempts: int = 3
    backoff_base_seconds: float = 2.0
    backoff_max_seconds: float = 30.0
    #: Whether rate limits should be retried at all.
    retry_rate_limits: bool = True
    #: Whether a malformed response is worth one more attempt.
    retry_malformed: bool = True


#: Errors that are never worth retrying.
_PERMANENT = (AuthError, InvalidRequestError)


def is_retryable(error: Exception, policy: RetryPolicy) -> bool:
    """Decide whether ``error`` may be retried under ``policy``."""
    if isinstance(error, _PERMANENT):
        return False
    if isinstance(error, RateLimitError):
        return policy.retry_rate_limits
    if isinstance(error, MalformedResponseError):
        return policy.retry_malformed
    if isinstance(error, ProviderUnavailableError):
        return True
    return False


def backoff_delay(attempt: int, policy: RetryPolicy, *, retry_after: float | None = None) -> float:
    """Compute the delay before retry number ``attempt`` (1-based).

    A provider-supplied ``Retry-After`` wins over the computed backoff.
    """
    if retry_after is not None and retry_after >= 0:
        return min(retry_after, policy.backoff_max_seconds)

    delay = policy.backoff_base_seconds * (2 ** (attempt - 1))
    return min(delay, policy.backoff_max_seconds)


def with_retry(operation, policy: RetryPolicy, *, sleep=time.sleep):
    """Run ``operation()`` with bounded retries.

    ``sleep`` is injectable so tests do not actually wait.
    """
    last_error: Exception | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except AIProviderError as exc:
            last_error = exc
            if not is_retryable(exc, policy) or attempt == policy.max_attempts:
                raise

            retry_after = getattr(exc, "retry_after_seconds", None)
            sleep(backoff_delay(attempt, policy, retry_after=retry_after))

    # Unreachable: the loop either returns or raises.
    raise last_error  # pragma: no cover
