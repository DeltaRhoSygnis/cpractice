"""Tests for the Kenari provider adapter.

Uses a fake HTTP transport so no live API call is made. The request/response
shapes follow https://kenari.id/docs/chat (OpenAI-compatible).
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
from app.ai.kenari import DEFAULT_BASE_URL, KenariProvider


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_body(text: str = "hello", finish_reason: str = "stop") -> dict:
    return {
        "id": "req_123",
        "object": "chat.completion",
        "model": "deepseek-v4-1-flash",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21},
    }


# --- configuration ---------------------------------------------------------


def test_missing_key_raises_auth_error() -> None:
    with pytest.raises(AuthError):
        KenariProvider(None)


def test_default_base_url_matches_documented_gateway() -> None:
    assert DEFAULT_BASE_URL == "https://kenari.id/v1"


def test_capabilities_note_structured_output_is_not_enforced() -> None:
    caps = KenariProvider("kn-x").capabilities()

    assert caps["provider"] == "kenari"
    assert caps["structured_output"] is True
    # Kenari forwards response_format but does not verify the result.
    assert caps["structured_output_enforced"] is False


# --- request shape ---------------------------------------------------------


def test_posts_to_chat_completions_with_bearer_auth() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    KenariProvider("kn-secret", client=_client(handler)).generate(system="SYS", prompt="PROMPT")

    assert captured["method"] == "POST"
    assert captured["url"] == "https://kenari.id/v1/chat/completions"
    assert captured["auth"] == "Bearer kn-secret"
    assert captured["body"]["model"] == "deepseek-v4-1-flash"


def test_messages_carry_system_and_user_roles() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    KenariProvider("kn-x", client=_client(handler)).generate(system="SYS", prompt="PROMPT")

    messages = captured["body"]["messages"]
    assert messages[0] == {"role": "system", "content": "SYS"}
    assert messages[1] == {"role": "user", "content": "PROMPT"}


def test_json_schema_sets_response_format() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body('{"a": 1}'))

    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    KenariProvider("kn-x", client=_client(handler)).generate(
        system="s", prompt="p", operation="generate_problem", json_schema=schema
    )

    response_format = captured["body"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "generate_problem"
    assert response_format["json_schema"]["schema"] == schema


def test_no_response_format_when_no_schema_given() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")

    assert "response_format" not in captured["body"]


def test_custom_base_url_is_honoured() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_ok_body())

    provider = KenariProvider("kn-x", base_url="https://example.test/v1", client=_client(handler))
    provider.generate(system="s", prompt="p")

    assert captured["url"].startswith("https://example.test/v1/")


# --- response parsing ------------------------------------------------------


def test_extracts_text_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body("result"))

    response = KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")

    assert response.text == "result"
    assert response.usage is not None
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 9


def test_content_as_parts_array_is_joined() -> None:
    body = _ok_body()
    body["choices"][0]["message"]["content"] = [
        {"type": "text", "text": "part one "},
        {"type": "text", "text": "part two"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    response = KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")

    assert response.text == "part one part two"


def test_json_wrapped_in_code_fence_is_returned_as_is() -> None:
    """The adapter returns raw text; the pipeline strips fences and parses."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body('```json\n{"a": 1}\n```'))

    response = KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")

    assert "```" in response.text


def test_truncated_response_raises_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body('{"partial":', finish_reason="length"))

    with pytest.raises(MalformedResponseError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


def test_no_choices_raises_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(MalformedResponseError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


def test_missing_content_raises_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {}, "finish_reason": "stop"}]})

    with pytest.raises(MalformedResponseError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


def test_empty_content_raises_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body("   "))

    with pytest.raises(MalformedResponseError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


# --- error taxonomy --------------------------------------------------------


def test_401_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key", "type": "auth"}})

    with pytest.raises(AuthError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


def test_403_subscribers_only_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"error": {"message": "subscribers only", "code": "subscribers_only"}}
        )

    with pytest.raises(AuthError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


def test_400_model_not_found_raises_invalid_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "unknown model", "code": "model_not_found"}}
        )

    with pytest.raises(InvalidRequestError) as excinfo:
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")

    assert "model_not_found" in str(excinfo.value)


def test_400_context_length_exceeded_raises_invalid_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "too long", "code": "context_length_exceeded"}}
        )

    with pytest.raises(InvalidRequestError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


def test_429_raises_rate_limit_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": {"message": "slow down"}}, headers={"Retry-After": "5"}
        )

    with pytest.raises(RateLimitError) as excinfo:
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")

    assert excinfo.value.retry_after_seconds == 5.0


def test_500_raises_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "server"}})

    with pytest.raises(ProviderUnavailableError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


def test_timeout_raises_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow")

    with pytest.raises(ProviderUnavailableError):
        KenariProvider("kn-x", client=_client(handler)).generate(system="s", prompt="p")


def test_error_detail_never_leaks_the_api_key() -> None:
    secret = "kn-super-secret-value"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(InvalidRequestError) as excinfo:
        KenariProvider(secret, client=_client(handler)).generate(system="s", prompt="p")

    assert secret not in str(excinfo.value)


# --- connectivity ----------------------------------------------------------


def test_check_connectivity_true_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    assert KenariProvider("kn-x", client=_client(handler)).check_connectivity() is True


def test_check_connectivity_false_on_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad"}})

    assert KenariProvider("kn-x", client=_client(handler)).check_connectivity() is False


def test_check_connectivity_true_when_rate_limited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})

    assert KenariProvider("kn-x", client=_client(handler)).check_connectivity() is True


def test_check_connectivity_hits_models_endpoint() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"data": []})

    KenariProvider("kn-x", client=_client(handler)).check_connectivity()

    assert captured["url"] == "https://kenari.id/v1/models"
