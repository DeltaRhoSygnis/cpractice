"""AI package — provider adapters and generation pipeline.

The provider interface hides vendor-specific details (design decision #10):
additional providers are adapters, not rewrites. Nothing outside this package
may depend on a specific vendor's response format.
"""

from app.ai.base import (
    AIProvider,
    AIProviderError,
    AuthError,
    InvalidRequestError,
    MalformedResponseError,
    ProviderUnavailableError,
    RateLimitError,
)

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AuthError",
    "InvalidRequestError",
    "MalformedResponseError",
    "ProviderUnavailableError",
    "RateLimitError",
]
