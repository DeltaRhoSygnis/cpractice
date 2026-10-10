"""Tests for the Google Gemini adapter.

Uses a fake HTTP client so no live API call is ever made.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.base import (
    AuthError,
    InvalidRequestError,
    MalformedResponseError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.ai.google import GoogleProvider


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_body(text: str = "hello", **extra) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        **extra,
    }


def test_missing_key_raises_auth_error() -> None:
    with pytest.raises(AuthError):
        GoogleProvider(None)


def test_successful_generation_returns_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body("result text"))

    provider = GoogleProvider("key", client=_client(handler))

    response = provider.generate(system="s", prompt="p")

    assert response.text == "result text"
    assert response.usage is not None
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 5


def test_request_sends_api_key_header_and_system_instruction() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    provider = GoogleProvider("secret-key", client=_client(handler))
    provider.generate(system="SYS", prompt="PROMPT")

    assert captured["headers"]["x-goog-api-key"] == "secret-key"
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "PROMPT"


def test_json_schema_enables_structured_output() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    provider = GoogleProvider("k", client=_client(handler))
    provider.generate(system="s", prompt="p", json_schema={"type": "object"})

    config = captured["body"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"] == {"type": "object"}


def test_401_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(AuthError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_403_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "forbidden"}})

    with pytest.raises(AuthError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_400_raises_invalid_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(InvalidRequestError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_404_raises_invalid_request_for_unknown_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    with pytest.raises(InvalidRequestError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_429_raises_rate_limit_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}}, headers={"Retry-After": "12"})

    with pytest.raises(RateLimitError) as excinfo:
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")

    assert excinfo.value.retry_after_seconds == 12.0


def test_500_raises_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "server"}})

    with pytest.raises(ProviderUnavailableError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_timeout_raises_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("took too long")

    with pytest.raises(ProviderUnavailableError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_empty_candidates_raises_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    with pytest.raises(MalformedResponseError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_blocked_prompt_raises_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    with pytest.raises(MalformedResponseError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_empty_text_raises_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "   "}]}}]})

    with pytest.raises(MalformedResponseError):
        GoogleProvider("k", client=_client(handler)).generate(system="s", prompt="p")


def test_error_detail_never_leaks_the_api_key() -> None:
    secret = "super-secret-api-key-value"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(InvalidRequestError) as excinfo:
        GoogleProvider(secret, client=_client(handler)).generate(system="s", prompt="p")

    assert secret not in str(excinfo.value)


def test_check_connectivity_true_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": []})

    assert GoogleProvider("k", client=_client(handler)).check_connectivity() is True


def test_check_connectivity_false_on_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad"}})

    assert GoogleProvider("k", client=_client(handler)).check_connectivity() is False


def test_check_connectivity_true_when_rate_limited() -> None:
    """Rate limiting means credentials are fine, so connectivity is True."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    assert GoogleProvider("k", client=_client(handler)).check_connectivity() is True


def test_capabilities_report_structured_output() -> None:
    caps = GoogleProvider("k").capabilities()

    assert caps["provider"] == "google"
    assert caps["structured_output"] is True
