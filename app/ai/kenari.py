"""Kenari provider adapter.

Kenari (https://kenari.id) is an AI gateway exposing an **OpenAI-compatible**
Chat Completions API. One key (``kn-...``) reaches every model in its catalog;
CPractice uses it for ``deepseek-v4-1-flash``.

    POST https://kenari.id/v1/chat/completions
    Authorization: Bearer kn-...

Structured output is requested with ``response_format``. Per Kenari's own
documentation the gateway does **not** enforce or verify the schema - it is
forwarded to the backing provider or dropped entirely, depending on how that
model is served. A reply may therefore be valid JSON, invalid JSON, or JSON
wrapped in a code fence. This adapter treats ``response_format`` as a hint and
never trusts the shape: the generation pipeline validates the parsed payload
against the Pydantic schemas and retries on failure.
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

DEFAULT_BASE_URL = "https://kenari.id/v1"
_DEFAULT_TIMEOUT_SECONDS = 120.0

# Kenari caps generation at 65536 tokens by default. A structured problem
# package is large, so leave generous headroom while staying under the cap.
_DEFAULT_MAX_TOKENS = 16384


class KenariProvider(AIProvider):
    """Adapter for the Kenari OpenAI-compatible gateway."""

    name = "kenari"

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str = "deepseek-v4-1-flash",
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise AuthError("KENARI_API_KEY is not configured")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
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
        """Generate a completion via chat completions."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self._max_tokens,
        }

        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": operation, "schema": json_schema},
            }

        data = self._post("/chat/completions", payload, operation=operation)

        text = self._extract_text(data)
        usage = self._extract_usage(data, operation)

        return GenerationResponse(text=text, usage=usage)

    def check_connectivity(self) -> bool:
        """Return True when the gateway is reachable and the key is accepted."""
        try:
            self._get("/models")
        except AuthError:
            return False
        except (RateLimitError, ProviderUnavailableError):
            return True
        return True

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "structured_output": True,
            # Not enforced server-side; the caller must validate.
            "structured_output_enforced": False,
            "base_url": self.base_url,
        }

    # -- internals ---------------------------------------------------------

    def _post(self, path: str, payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
        try:
            response = self._request("POST", f"{self.base_url}{path}", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"provider timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"network error: {exc}") from exc

        return self._handle_response(response, operation=operation)

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = self._request("GET", f"{self.base_url}{path}")
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"network error: {exc}") from exc

        return self._handle_response(response, operation="check_connectivity")

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return self._client.request(method, url, headers=headers, timeout=self._timeout, **kwargs)
        with httpx.Client(timeout=self._timeout) as client:
            return client.request(method, url, headers=headers, **kwargs)

    @staticmethod
    def _handle_response(response: httpx.Response, *, operation: str) -> dict[str, Any]:
        """Translate HTTP status codes into the shared error taxonomy."""
        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise MalformedResponseError("provider returned a non-JSON body") from exc

        detail, code = _safe_error_detail(response)

        if response.status_code in (401, 403):
            # 403 also covers subscribers_only / byok_* conditions.
            raise AuthError(f"authentication or access denied: {detail}")
        if response.status_code == 400:
            raise InvalidRequestError(f"invalid request ({code or 'bad_request'}): {detail}")
        if response.status_code == 404:
            raise InvalidRequestError(f"endpoint or model not found: {detail}")
        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitError(f"rate limited or quota exhausted: {detail}", retry_after)
        if response.status_code >= 500:
            raise ProviderUnavailableError(f"provider error {response.status_code}: {detail}")

        raise InvalidRequestError(f"unexpected status {response.status_code}: {detail}")

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        """Pull the assistant text out of an OpenAI-shaped response."""
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise MalformedResponseError("provider response contained no choices")

        first = choices[0] or {}
        message = first.get("message") or {}
        content = message.get("content")

        # Some models place the answer in tool_calls; that is not expected here.
        if content is None:
            finish = first.get("finish_reason")
            raise MalformedResponseError(
                f"provider response contained no message content (finish_reason={finish})"
            )

        if isinstance(content, list):
            # Defensive: some gateways return content as an array of parts.
            chunks = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") in (None, "text")
            ]
            content = "".join(chunks)

        text = str(content).strip()
        if not text:
            raise MalformedResponseError("provider returned empty content")

        # A reply truncated at max_tokens is not usable JSON.
        if first.get("finish_reason") == "length":
            raise MalformedResponseError("provider response was truncated at max_tokens")

        return text

    def _extract_usage(self, data: dict[str, Any], operation: str) -> UsageRecord | None:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return None
        return UsageRecord(
            provider=self.name,
            model=self.model,
            operation=operation,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

    def close(self) -> None:
        if self._owns_client and self._client is not None:  # pragma: no cover
            self._client.close()


def _safe_error_detail(response: httpx.Response) -> tuple[str, str | None]:
    """Extract a short error message and code without leaking the API key."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200], None

    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message", ""))[:300]
        code = error.get("code")
        return message, str(code) if code else None
    return str(body)[:300], None


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
