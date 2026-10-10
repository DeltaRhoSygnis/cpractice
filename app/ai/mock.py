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
