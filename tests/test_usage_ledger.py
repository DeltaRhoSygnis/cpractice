"""Tests for the usage ledger and daily budget enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.base import (
    AuthError,
    ProviderUnavailableError,
    RateLimitError,
    UsageRecord,
)
from app.ai.mock import MockProvider
from app.storage.database import Database
from app.storage.usage_ledger import LedgeredProvider, UsageLedger, _classify


def _ledger(tmp_path: Path) -> UsageLedger:
    return UsageLedger(Database(tmp_path / "db.sqlite"))


# --- recording -------------------------------------------------------------


def test_records_a_successful_call(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)

    ledger.record_success(
        UsageRecord(provider="kenari", model="m", operation="generate_problem",
                    input_tokens=10, output_tokens=5)
    )

    today = ledger.today()
    assert today.requests == 1
    assert today.input_tokens == 10
    assert today.output_tokens == 5
    assert today.total_tokens == 15
    assert today.failures == 0


def test_records_a_failure(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)

    ledger.record_failure(
        RateLimitError("quota"), provider="kenari", model="m", operation="generate_problem"
    )

    today = ledger.today()
    assert today.requests == 1
    assert today.failures == 1


def test_recent_lists_newest_first(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.record_success(UsageRecord(provider="p", model="m", operation="first"))
    ledger.record_success(UsageRecord(provider="p", model="m", operation="second"))

    recent = ledger.recent()

    assert recent[0]["operation"] == "second"


def test_ledger_stores_no_prompts_or_content(tmp_path: Path) -> None:
    """The ledger records metadata only, never prompt or response text."""
    ledger = _ledger(tmp_path)
    ledger.record_success(UsageRecord(provider="p", model="m", operation="op"))

    row = ledger.recent()[0]

    assert set(row) == {
        "created_at", "provider", "model", "operation",
        "status", "input_tokens", "output_tokens",
    }


# --- classification --------------------------------------------------------


def test_error_classification() -> None:
    assert _classify(RateLimitError("x")) == "rate_limited"
    assert _classify(AuthError("x")) == "auth_error"
    assert _classify(ProviderUnavailableError("x")) == "unavailable"
    assert _classify(ValueError("x")) == "error"


# --- budget ----------------------------------------------------------------


def test_budget_is_unlimited_by_default(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    for _ in range(5):
        ledger.record_success(UsageRecord(provider="p", model="m", operation="op"))

    assert ledger.budget_exceeded(0) is False


def test_budget_blocks_when_reached(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.record_success(UsageRecord(provider="p", model="m", operation="op"))

    assert ledger.budget_exceeded(1) is True
    assert ledger.budget_exceeded(2) is False


# --- ledgated provider -----------------------------------------------------


def test_ledgered_provider_records_success(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    provider = LedgeredProvider(MockProvider(responses="ok"), ledger)

    provider.generate(system="s", prompt="p", operation="generate_problem")

    assert ledger.today().requests == 1


def test_ledgered_provider_records_failure_and_reraises(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)

    class Failing(MockProvider):
        def generate(self, **kwargs):
            raise AuthError("bad key")

    provider = LedgeredProvider(Failing(), ledger)

    with pytest.raises(AuthError):
        provider.generate(system="s", prompt="p", operation="generate_problem")

    assert ledger.today().failures == 1


def test_ledgered_provider_enforces_budget(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    provider = LedgeredProvider(MockProvider(responses="ok"), ledger, daily_budget=1)

    provider.generate(system="s", prompt="p", operation="op")

    with pytest.raises(RateLimitError) as excinfo:
        provider.generate(system="s", prompt="p", operation="op")

    assert "budget" in str(excinfo.value)


def test_budget_refusal_is_recorded(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    provider = LedgeredProvider(MockProvider(responses="ok"), ledger, daily_budget=1)
    provider.generate(system="s", prompt="p", operation="op")

    with pytest.raises(RateLimitError):
        provider.generate(system="s", prompt="p", operation="op")

    # The refusal itself is auditable.
    assert ledger.today().requests == 2
    assert ledger.today().failures == 1


def test_ledgered_provider_delegates_metadata(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    inner = MockProvider(responses="ok", model="inner-model")
    provider = LedgeredProvider(inner, ledger)

    assert provider.name == "mock"
    assert provider.model == "inner-model"
    assert provider.capabilities()["mock"] is True
    assert provider.check_connectivity() is True


def test_wrapping_does_not_change_returned_response(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    provider = LedgeredProvider(MockProvider(responses="payload"), ledger)

    result = provider.generate(system="s", prompt="p")

    assert result.text == "payload"
