"""Mock provider for tests and offline use.

The platform's own tests must never require live AI calls. This provider
returns scripted responses and can be told to raise specific errors, so every
failure path in the pipeline is testable deterministically.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.ai.base import (
    AIProvider,
    AIProviderError,
    BatchItemResult,
    BatchProvider,
    BatchRequest,
    GenerationResponse,
    MalformedResponseError,
    UsageRecord,
)

Responder = Callable[[str, str, str], str]


class MockProvider(AIProvider):
    """A scriptable provider that never touches the network.

    Parameters
    ----------
    responses:
        A single response string, or a list returned in call order.
    responder:
        Optional callable ``(system, prompt, operation) -> str`` used instead
        of ``responses``. Useful when the reply must depend on the prompt.
    errors:
        Exceptions raised in call order, before returning a response. Lets a
        test drive retry behaviour.
    """

    name = "mock"

    def __init__(
        self,
        responses: str | list[str] | None = None,
        *,
        responder: Responder | None = None,
        errors: list[Exception] | None = None,
        model: str = "mock-model",
        connectivity: bool = True,
    ) -> None:
        self._responses = [responses] if isinstance(responses, str) else list(responses or [])
        self._responder = responder
        self._errors = list(errors or [])
        self._connectivity = connectivity
        self.model = model

        self.calls: list[dict[str, str]] = []

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        operation: str = "generate",
        json_schema: dict[str, Any] | None = None,
    ) -> GenerationResponse:
        self.calls.append({"system": system, "prompt": prompt, "operation": operation})

        if self._errors:
            error = self._errors.pop(0)
            if error is not None:
                raise error

        if self._responder is not None:
            text = self._responder(system, prompt, operation)
        elif self._responses:
            # Repeat the final response once the script is exhausted.
            index = min(len(self.calls) - 1, len(self._responses) - 1)
            text = self._responses[index]
        else:
            raise MalformedResponseError("MockProvider has no scripted response")

        return GenerationResponse(
            text=text,
            usage=UsageRecord(provider=self.name, model=self.model, operation=operation),
        )

    def check_connectivity(self) -> bool:
        return self._connectivity

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "structured_output": True,
            "mock": True,
        }


def failing_provider(error: AIProviderError, *, times: int = 1) -> MockProvider:
    """Build a mock that raises ``error`` for the first ``times`` calls."""
    return MockProvider(
        responses='{"ok": true}',
        errors=[error] * times,
    )


class MockBatchProvider(MockProvider, BatchProvider):
    """A scriptable batch provider that never touches the network.

    It answers both interfaces, because a shelf run needs a blueprint call (an
    interactive :meth:`generate`) *and* the batch submission. Responses are
    scripted per ``custom_id`` (or by a callable), so a test can make one item
    malformed while the others are valid.

    Parameters
    ----------
    batch_responses:
        Maps a request ``custom_id`` to the text to return for it. A missing id
        falls back to ``default_batch_response``.
    default_batch_response:
        Text returned for any ``custom_id`` not present in ``batch_responses``.
    batch_responder:
        Optional callable ``(request) -> str`` used instead of the maps. Useful
        when the reply must depend on the prompt.
    batch_errors:
        Maps a ``custom_id`` to an :class:`AIProviderError` to report for that
        item. The error is returned *inside* the result list, never raised -
        per-item failures are data (spec S10).
    """

    name = "mock-batch"

    def __init__(
        self,
        responses: str | list[str] | None = None,
        *,
        responder: Responder | None = None,
        errors: list[Exception] | None = None,
        model: str = "mock-model",
        connectivity: bool = True,
        batch_responses: dict[str, str] | None = None,
        default_batch_response: str | None = None,
        batch_responder: Callable[[BatchRequest], str] | None = None,
        batch_errors: dict[str, AIProviderError] | None = None,
        batch_job_error: AIProviderError | None = None,
    ) -> None:
        super().__init__(
            responses,
            responder=responder,
            errors=errors,
            model=model,
            connectivity=connectivity,
        )
        self._batch_responses = dict(batch_responses or {})
        self._default_batch_response = default_batch_response
        self._batch_responder = batch_responder
        self._batch_errors = dict(batch_errors or {})
        #: When set, every :meth:`submit` raises this instead of returning.
        self._batch_job_error = batch_job_error
        #: Every submitted batch, in call order.
        self.batch_calls: list[list[BatchRequest]] = []

    def submit(self, requests: list[BatchRequest]) -> list[BatchItemResult]:
        self.batch_calls.append(list(requests))

        if self._batch_job_error is not None:
            raise self._batch_job_error

        results: list[BatchItemResult] = []
        for request in requests:
            error = self._batch_errors.get(request.custom_id)
            if error is not None:
                results.append(BatchItemResult(custom_id=request.custom_id, error=error))
                continue

            if self._batch_responder is not None:
                text = self._batch_responder(request)
            elif request.custom_id in self._batch_responses:
                text = self._batch_responses[request.custom_id]
            elif self._default_batch_response is not None:
                text = self._default_batch_response
            else:
                results.append(
                    BatchItemResult(
                        custom_id=request.custom_id,
                        error=MalformedResponseError(
                            f"MockBatchProvider has no scripted response for "
                            f"{request.custom_id!r}"
                        ),
                    )
                )
                continue

            results.append(
                BatchItemResult(
                    custom_id=request.custom_id,
                    text=text,
                    usage=UsageRecord(
                        provider=self.name,
                        model=self.model,
                        operation=request.operation,
                    ),
                )
            )

        return results

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "structured_output": True,
            "batch": True,
            "mock": True,
        }
