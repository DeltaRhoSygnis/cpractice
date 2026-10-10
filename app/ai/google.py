"""Google AI Studio / Gemini provider adapter.

Uses the REST API directly (no vendor SDK) so the adapter stays small and the
application keeps no Google-specific dependency. All vendor response shapes
are converted here; nothing else in the codebase sees them.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.base import (
    AIProvider,
    AuthError,
    GenerationResponse,
    InvalidRequestError,
    MalformedResponseError,
    ProviderUnavailableError,
    RateLimitError,
    UsageRecord,
)

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

# Network timeout for a single request, in seconds. Generation can be slow.
_DEFAULT_TIMEOUT_SECONDS = 60.0


class GoogleProvider(AIProvider):
    """Adapter for the Google Gemini ``generateContent`` endpoint."""

    name = "google"

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str = "gemini-2.0-flash",
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise AuthError("GOOGLE_API_KEY is not configured")
        self._api_key = api_key
        self.model = model
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None

    # -- public interface --------------------------------------------------

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        operation: str = "generate",
        json_schema: dict[str, Any] | None = None,
    ) -> GenerationResponse:
        """Generate content, optionally constrained to a JSON schema."""
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }

        if json_schema is not None:
            # Ask the model for structured JSON matching the schema.
            payload["generationConfig"] = {
                "responseMimeType": "application/json",
                "responseSchema": json_schema,
            }

        data = self._post(payload, operation=operation)

        text = self._extract_text(data)
        usage = self._extract_usage(data, operation)

        return GenerationResponse(text=text, usage=usage)

    def check_connectivity(self) -> bool:
        """Return True when the API is reachable and the key is accepted."""
        try:
            self._get_models()
        except AuthError:
            return False
        except (RateLimitError, ProviderUnavailableError):
            # Reachable, but temporarily unusable. Credentials are fine.
            return True
        return True

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "structured_output": True,
        }

    # -- internals ---------------------------------------------------------

    def _post(self, payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
        url = f"{_API_ROOT}/models/{self.model}:generateContent"

        try:
            response = self._request("POST", url, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"provider timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"network error: {exc}") from exc

        return self._handle_response(response, operation=operation)

    def _get_models(self) -> dict[str, Any]:
        try:
            response = self._request("GET", f"{_API_ROOT}/models")
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"network error: {exc}") from exc
        return self._handle_response(response, operation="check_connectivity")

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = {"x-goog-api-key": self._api_key}
        if self._client is not None:
            return self._client.request(method, url, headers=headers, timeout=self._timeout, **kwargs)
        with httpx.Client(timeout=self._timeout) as client:
            return client.request(method, url, headers=headers, **kwargs)

    @staticmethod
    def _handle_response(response: httpx.Response, *, operation: str) -> dict[str, Any]:
        """Translate HTTP status codes into the error taxonomy."""
        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise MalformedResponseError("provider returned non-JSON body") from exc

        detail = _safe_error_detail(response)

        if response.status_code in (401, 403):
            raise AuthError(f"authentication failed: {detail}")
        if response.status_code == 400:
            raise InvalidRequestError(f"invalid request: {detail}")
        if response.status_code == 404:
            raise InvalidRequestError(f"model or endpoint not found: {detail}")
        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitError(f"rate limited or quota exhausted: {detail}", retry_after)
        if response.status_code >= 500:
            raise ProviderUnavailableError(f"provider error {response.status_code}: {detail}")

        raise InvalidRequestError(f"unexpected status {response.status_code}: {detail}")

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        """Pull the text out of a Gemini response, defensively."""
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            # A prompt blocked by safety filters has no candidates.
            feedback = data.get("promptFeedback") or {}
            reason = feedback.get("blockReason")
            if reason:
                raise MalformedResponseError(f"prompt blocked by provider: {reason}")
            raise MalformedResponseError("provider response contained no candidates")

        first = candidates[0] or {}
        content = first.get("content") or {}
        parts = content.get("parts")
        if not isinstance(parts, list):
            finish = first.get("finishReason")
            raise MalformedResponseError(
                f"provider response contained no content parts (finishReason={finish})"
            )

        chunks = [part.get("text", "") for part in parts if isinstance(part, dict)]
        text = "".join(chunks).strip()
        if not text:
            raise MalformedResponseError("provider returned empty text")
        return text

    def _extract_usage(self, data: dict[str, Any], operation: str) -> UsageRecord | None:
        meta = data.get("usageMetadata")
        if not isinstance(meta, dict):
            return None
        return UsageRecord(
            provider=self.name,
            model=self.model,
            operation=operation,
            input_tokens=meta.get("promptTokenCount"),
            output_tokens=meta.get("candidatesTokenCount"),
        )

    def close(self) -> None:
        if self._owns_client and self._client is not None:  # pragma: no cover
            self._client.close()


def _safe_error_detail(response: httpx.Response) -> str:
    """Extract a short error message without leaking the API key."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]

    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message", ""))
        return message[:300]
    return str(body)[:300]


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
