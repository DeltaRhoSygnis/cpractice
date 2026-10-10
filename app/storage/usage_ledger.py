"""Provider usage ledger.

Records every AI call so quota consumption is auditable and a daily budget can
be enforced. The ledger stores no prompts or responses - only operation
metadata and token counts (section 14 of the architecture spec).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.ai.base import AIProviderError, GenerationResponse, UsageRecord
from app.storage.database import Database


@dataclass(frozen=True)
class UsageSummary:
    """Aggregate usage for a period."""

    requests: int
    failures: int
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class UsageLedger:
    """Writes and reads provider usage records."""

    def __init__(self, database: Database) -> None:
        self.database = database

    # -- writing -----------------------------------------------------------

    def record_success(self, usage: UsageRecord | None, *, operation: str = "") -> None:
        """Record a successful provider call."""
        resolved_operation = operation or (usage.operation if usage else "unknown")
        self._insert(
            provider=usage.provider if usage else "unknown",
            model=usage.model if usage else "unknown",
            operation=resolved_operation,
            status="ok",
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            detail="",
        )

    def record_failure(self, error: Exception, *, provider: str, model: str, operation: str) -> None:
        """Record a failed provider call, classified by error type."""
        self._insert(
            provider=provider,
            model=model,
            operation=operation,
            status=_classify(error),
            input_tokens=None,
            output_tokens=None,
            detail=str(error)[:300],
        )

    def _insert(
        self,
        *,
        provider: str,
        model: str,
        operation: str,
        status: str,
        input_tokens: int | None,
        output_tokens: int | None,
        detail: str,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO provider_usage
                    (provider, model, operation, status, input_tokens, output_tokens, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (provider, model, operation, status, input_tokens, output_tokens, detail),
            )

    # -- reading -----------------------------------------------------------

    def today(self) -> UsageSummary:
        """Usage since midnight UTC."""
        start = datetime.now(timezone.utc).strftime("%Y-%m-%d 00:00:00")
        return self.since(start)

    def since(self, timestamp: str) -> UsageSummary:
        row = (
            self.database.connect()
            .execute(
                """
                SELECT
                    COUNT(*)                                        AS requests,
                    SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS failures,
                    COALESCE(SUM(input_tokens), 0)                  AS input_tokens,
                    COALESCE(SUM(output_tokens), 0)                 AS output_tokens
                FROM provider_usage
                WHERE created_at >= ?
                """,
                (timestamp,),
            )
            .fetchone()
        )

        return UsageSummary(
            requests=int(row["requests"] or 0),
            failures=int(row["failures"] or 0),
            input_tokens=int(row["input_tokens"] or 0),
            output_tokens=int(row["output_tokens"] or 0),
        )

    def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = (
            self.database.connect()
            .execute(
                "SELECT created_at, provider, model, operation, status, "
                "input_tokens, output_tokens FROM provider_usage "
                "ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            )
            .fetchall()
        )
        return [dict(row) for row in rows]

    # -- budget ------------------------------------------------------------

    def budget_exceeded(self, daily_budget: int) -> bool:
        """Return True when today's request count has reached the budget.

        A budget of 0 means unlimited.
        """
        if daily_budget <= 0:
            return False
        return self.today().requests >= daily_budget


def _classify(error: Exception) -> str:
    """Map an error to a stable ledger status."""
    from app.ai.base import (
        AuthError,
        InvalidRequestError,
        MalformedResponseError,
        ProviderUnavailableError,
        RateLimitError,
    )

    if isinstance(error, RateLimitError):
        return "rate_limited"
    if isinstance(error, AuthError):
        return "auth_error"
    if isinstance(error, InvalidRequestError):
        return "invalid_request"
    if isinstance(error, MalformedResponseError):
        return "malformed_response"
    if isinstance(error, ProviderUnavailableError):
        return "unavailable"
    if isinstance(error, AIProviderError):
        return "provider_error"
    return "error"


class LedgeredProvider:
    """Wraps a provider so every call is recorded and budgets are enforced.

    This is a decorator rather than a modification of the adapters: providers
    stay unaware of persistence, and any adapter benefits automatically.
    """

    def __init__(self, provider, ledger: UsageLedger, *, daily_budget: int = 0) -> None:
        self._provider = provider
        self._ledger = ledger
        self._daily_budget = daily_budget

    # -- delegation --------------------------------------------------------

    @property
    def name(self) -> str:
        return self._provider.name

    @property
    def model(self) -> str:
        return self._provider.model

    def capabilities(self) -> dict:
        return self._provider.capabilities()

    def check_connectivity(self) -> bool:
        return self._provider.check_connectivity()

    def generate(self, **kwargs) -> GenerationResponse:
        from app.ai.base import RateLimitError

        operation = kwargs.get("operation", "generate")

        if self._ledger.budget_exceeded(self._daily_budget):
            error = RateLimitError(
                f"daily request budget of {self._daily_budget} reached",
                retry_after_seconds=None,
            )
            self._ledger.record_failure(
                error,
                provider=self._provider.name,
                model=self._provider.model,
                operation=operation,
            )
            raise error

        try:
            response = self._provider.generate(**kwargs)
        except AIProviderError as exc:
            self._ledger.record_failure(
                exc,
                provider=self._provider.name,
                model=self._provider.model,
                operation=operation,
            )
            raise

        self._ledger.record_success(response.usage, operation=operation)
        return response
