"""Tests for the provider interface, mock provider, and retry policy."""

from __future__ import annotations

import pytest

from app.ai.base import (
    AuthError,
    GenerationResponse,
    InvalidRequestError,
    MalformedResponseError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.ai.mock import MockProvider, failing_provider
from app.ai.rate_limits import RetryPolicy, backoff_delay, is_retryable, with_retry


# --- mock provider ---------------------------------------------------------


def test_mock_returns_scripted_response() -> None:
    provider = MockProvider(responses="hello")

    result = provider.generate(system="s", prompt="p")

    assert isinstance(result, GenerationResponse)
    assert result.text == "hello"
    assert result.usage is not None
    assert result.usage.provider == "mock"


def test_mock_records_calls() -> None:
    provider = MockProvider(responses="x")

    provider.generate(system="sys", prompt="pr", operation="op")

    assert provider.calls == [{"system": "sys", "prompt": "pr", "operation": "op"}]


def test_mock_cycles_through_response_list() -> None:
    provider = MockProvider(responses=["one", "two", "three"])
    texts = [provider.generate(system="s", prompt="p").text for _ in range(5)]

    assert texts == ["one", "two", "three", "three", "three"]


def test_mock_responder_receives_prompt() -> None:
    provider = MockProvider(responder=lambda s, p, o: f"echo:{p}")

    assert provider.generate(system="s", prompt="abc").text == "echo:abc"


def test_mock_raises_scripted_errors_in_order() -> None:
    provider = failing_provider(ProviderUnavailableError("boom"), times=2)

    with pytest.raises(ProviderUnavailableError):
        provider.generate(system="s", prompt="p")
    with pytest.raises(ProviderUnavailableError):
        provider.generate(system="s", prompt="p")
    # Third call succeeds.
    assert provider.generate(system="s", prompt="p").text == '{"ok": true}'


def test_mock_without_script_raises_malformed() -> None:
    with pytest.raises(MalformedResponseError):
        MockProvider().generate(system="s", prompt="p")


def test_mock_connectivity_is_configurable() -> None:
    assert MockProvider(connectivity=True).check_connectivity() is True
    assert MockProvider(connectivity=False).check_connectivity() is False


def test_mock_reports_capabilities() -> None:
    caps = MockProvider().capabilities()

    assert caps["provider"] == "mock"
    assert caps["mock"] is True


# --- retry policy ----------------------------------------------------------


def test_auth_errors_are_never_retryable() -> None:
    assert is_retryable(AuthError("no"), RetryPolicy()) is False


def test_invalid_request_is_never_retryable() -> None:
    assert is_retryable(InvalidRequestError("bad"), RetryPolicy()) is False


def test_unavailable_is_retryable() -> None:
    assert is_retryable(ProviderUnavailableError("net"), RetryPolicy()) is True


def test_rate_limit_is_retryable_by_default() -> None:
    assert is_retryable(RateLimitError("slow"), RetryPolicy()) is True


def test_rate_limit_retry_can_be_disabled() -> None:
    policy = RetryPolicy(retry_rate_limits=False)

    assert is_retryable(RateLimitError("slow"), policy) is False


def test_malformed_retry_can_be_disabled() -> None:
    assert is_retryable(MalformedResponseError("junk"), RetryPolicy()) is True
    assert (
        is_retryable(MalformedResponseError("junk"), RetryPolicy(retry_malformed=False))
        is False
    )


# --- backoff ---------------------------------------------------------------


def test_backoff_grows_exponentially() -> None:
    policy = RetryPolicy(backoff_base_seconds=1.0, backoff_max_seconds=100)

    assert backoff_delay(1, policy) == 1.0
    assert backoff_delay(2, policy) == 2.0
    assert backoff_delay(3, policy) == 4.0


def test_backoff_is_capped() -> None:
    policy = RetryPolicy(backoff_base_seconds=1.0, backoff_max_seconds=5.0)

    assert backoff_delay(10, policy) == 5.0


def test_retry_after_overrides_backoff() -> None:
    policy = RetryPolicy(backoff_base_seconds=1.0, backoff_max_seconds=100)

    assert backoff_delay(1, policy, retry_after=7.0) == 7.0


def test_retry_after_is_also_capped() -> None:
    policy = RetryPolicy(backoff_max_seconds=5.0)

    assert backoff_delay(1, policy, retry_after=999.0) == 5.0


# --- with_retry ------------------------------------------------------------


def test_with_retry_succeeds_without_retry() -> None:
    calls = []

    result = with_retry(lambda: (calls.append(1), "ok")[1], RetryPolicy(), sleep=lambda _: None)

    assert result == "ok"
    assert len(calls) == 1


def test_with_retry_recovers_from_transient_error() -> None:
    attempts = {"n": 0}
    delays: list[float] = []

    def operation():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ProviderUnavailableError("transient")
        return "recovered"

    result = with_retry(operation, RetryPolicy(max_attempts=3, backoff_base_seconds=0.01), sleep=delays.append)

    assert result == "recovered"
    assert attempts["n"] == 3
    assert len(delays) == 2


def test_with_retry_gives_up_after_max_attempts() -> None:
    attempts = {"n": 0}

    def operation():
        attempts["n"] += 1
        raise ProviderUnavailableError("always down")

    with pytest.raises(ProviderUnavailableError):
        with_retry(operation, RetryPolicy(max_attempts=3), sleep=lambda _: None)

    assert attempts["n"] == 3


def test_with_retry_does_not_retry_auth_errors() -> None:
    attempts = {"n": 0}

    def operation():
        attempts["n"] += 1
        raise AuthError("bad key")

    with pytest.raises(AuthError):
        with_retry(operation, RetryPolicy(max_attempts=5), sleep=lambda _: None)

    assert attempts["n"] == 1


def test_with_retry_respects_retry_after() -> None:
    delays: list[float] = []
    attempts = {"n": 0}

    def operation():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RateLimitError("slow down", retry_after_seconds=3.0)
        return "ok"

    with_retry(operation, RetryPolicy(backoff_base_seconds=1.0, backoff_max_seconds=10), sleep=delays.append)

    assert delays == [3.0]
