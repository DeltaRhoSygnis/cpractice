"""Gemini Batch API adapter (spec S7).

The Gemini Batch API enqueues many ``generateContent`` requests as one
long-running operation, processed asynchronously at a lower cost. It is a
**transport** layer only: this adapter submits requests and returns one raw
text (or one error) per request. The shelf runner feeds each text to the same
:class:`~app.generation.pipeline.GenerationPipeline` and the same
:class:`~app.generation.quality_gate.QualityGate` as interactive generation, so
batching never changes what is accepted.

Envelope assumptions (documented; TESTED WITH A MOCKED HTTP CLIENT)
------------------------------------------------------------------
Verified against Google's Batch API reference
(https://ai.google.dev/api/batch-api). The wire shapes used here are:

Submit::

    POST {root}/models/{model}:batchGenerateContent
    { "batch": {
        "displayName": "<job id>",
        "inputConfig": { "requests": { "requests": [
            { "request": {
                "systemInstruction": {"parts": [{"text": ...}]},
                "contents": [{"role": "user", "parts": [{"text": ...}]}],
                "generationConfig": {...}          # only when a schema is given
              },
              "metadata": {"custom_id": "<correlation id>"}   # assumption
            }, ...
        ] } }
    } }

Response: a long-running ``Operation``::

    { "name": "batches/<id>", "done": false|true, "metadata": {...},
      "response": { "inlinedResponses": { "inlinedResponses": [
          {"response": {<GenerateContentResponse>}},          # success
          {"error": {"code": ..., "message": ...}}            # per-item failure
      ] } } }

Poll::

    GET {root}/batches/<id>

    Repeated until ``done`` is true (or until the injected poll budget is
    exhausted).

Assumptions that are **not** guaranteed by the public reference and are
therefore marked explicitly:

1. **Correlation.** The reference states inlined responses are returned "in
   the same order as the input requests", so results are matched to requests
   **by position**. A ``metadata.custom_id`` is also sent, and if the response
   echoes ``metadata`` the adapter prefers that echo; otherwise it falls back
   to position. Both paths are tested.
2. **Per-item error shape.** A per-item failure is the ``output.error`` union
   arm, a ``google.rpc.Status`` (``{"code", "message"}``). The ``code`` is an
   HTTP-style/gRPC code; it is mapped through the same status→taxonomy table
   as the interactive adapter.
3. **Not-done polling.** When ``done`` is false the adapter sleeps and polls
   ``GET batches/<id>``. ``sleep`` is injectable so tests do not wait.

The API key is sent only as the ``x-goog-api-key`` header and is never
embedded in a URL, a payload, or an error message.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.ai.base import (
    AuthError,
    BatchItemResult,
    BatchProvider,
    BatchRequest,
    InvalidRequestError,
    MalformedResponseError,
    ProviderUnavailableError,
    RateLimitError,
    UsageRecord,
)

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

# Network timeout for a single HTTP request, in seconds.
_DEFAULT_TIMEOUT_SECONDS = 60.0

# How many times to poll a not-yet-done operation before giving up. Bounded so
# a stuck job cannot spin forever. The batch API is asynchronous by design, so
# the default is generous but finite.
_DEFAULT_MAX_POLLS = 60

# Default delay between polls, in seconds.
_DEFAULT_POLL_INTERVAL_SECONDS = 5.0


class GoogleBatchProvider(BatchProvider):
    """Adapter for the Gemini ``batchGenerateContent`` endpoint.

    Parameters
    ----------
    api_key:
        The API key. A missing key raises :class:`AuthError` immediately, so a
        misconfigured deployment fails at construction rather than mid-job.
    model:
        The model id (without the ``models/`` prefix).
    client:
        An injected ``httpx.Client``. Tests supply one backed by
        ``httpx.MockTransport`` so no network call is ever made.
    sleep:
        Injected sleep callable, used between polls. Tests pass a no-op.
    """

    name = "google-batch"

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str = "gemini-2.0-flash",
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
        max_polls: int = _DEFAULT_MAX_POLLS,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
        sleep=time.sleep,
    ) -> None:
        if not api_key:
            raise AuthError("GOOGLE_API_KEY is not configured")
        self._api_key = api_key
        self.model = model
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self._max_polls = max(1, max_polls)
        self._poll_interval = poll_interval_seconds
        self._sleep = sleep

    # -- public interface --------------------------------------------------

    def submit(self, requests: list[BatchRequest]) -> list[BatchItemResult]:
        """Submit every request as one batch and return one result per request.

        A job-level failure (the batch could not be enqueued, polled, or its
        output was unreadable) raises an :class:`AIProviderError`. A failure
        confined to a single item is returned as a :class:`BatchItemResult`
        with ``error`` set - it never fails the job (spec S10).
        """
        if not requests:
            return []

        operation = self._create_batch(requests)
        job_name = operation.get("name")
        if not isinstance(job_name, str) or not job_name:
            raise MalformedResponseError("batch response contained no operation name")

        operation = self._await_completion(job_name, operation)
        return self._collect_results(requests, operation)

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
            "batch": True,
            "structured_output": True,
        }

    # -- job lifecycle -----------------------------------------------------

    def _create_batch(self, requests: list[BatchRequest]) -> dict[str, Any]:
        payload = {
            "batch": {
                "displayName": f"cpractice-shelf-{int(time.time() * 1000)}",
                "inputConfig": {
                    "requests": {
                        "requests": [
                            _inlined_request(request) for request in requests
                        ]
                    }
                },
            }
        }

        url = f"{_API_ROOT}/models/{self.model}:batchGenerateContent"
        return self._post(url, payload, operation="batch_submit")

    def _await_completion(self, job_name: str, operation: dict[str, Any]) -> dict[str, Any]:
        """Poll ``GET batches/<id>`` until the operation reports ``done``.

        The operation name from the submit response is authoritative (the
        reference documents ``batches/{id}``); the URL is built from it rather
        than from the model, so the poll does not depend on the model string.
        """
        polls = 0
        while not _is_done(operation):
            if polls >= self._max_polls:
                raise ProviderUnavailableError(
                    f"batch job {job_name!r} did not complete within "
                    f"{self._max_polls} poll(s)"
                )
            self._sleep(self._poll_interval)
            operation = self._get_batch(job_name)
            polls += 1

        # An operation that finished with a job-level error is a job failure.
        error = operation.get("error")
        if isinstance(error, dict):
            raise _status_to_error(error, context="batch job failed")

        return operation

    def _get_batch(self, job_name: str) -> dict[str, Any]:
        return self._get(f"{_API_ROOT}/{job_name}", operation="batch_poll")

    # -- response parsing --------------------------------------------------

    def _collect_results(
        self, requests: list[BatchRequest], operation: dict[str, Any]
    ) -> list[BatchItemResult]:
        """Turn an operation into one result per request, in input order.

        The reference documents inlined responses as ordered the same as the
        input, so position is the primary correlation. If a response echoes
        ``metadata.custom_id`` it is preferred, which is robust to a provider
        that reorders.
        """
        entries = _extract_inlined_responses(operation)

        by_custom_id: dict[str, dict[str, Any]] = {}
        ordered: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ordered.append(entry)
            metadata = entry.get("metadata")
            if isinstance(metadata, dict):
                custom_id = metadata.get("custom_id")
                if isinstance(custom_id, str) and custom_id:
                    by_custom_id[custom_id] = entry

        results: list[BatchItemResult] = []
        for index, request in enumerate(requests):
            entry = by_custom_id.get(request.custom_id)
            if entry is None and index < len(ordered):
                entry = ordered[index]
            if entry is None:
                results.append(
                    BatchItemResult(
                        custom_id=request.custom_id,
                        error=MalformedResponseError(
                            "batch response contained no result for this request"
                        ),
                    )
                )
                continue
            results.append(self._parse_entry(request, entry))

        return results

    def _parse_entry(self, request: BatchRequest, entry: dict[str, Any]) -> BatchItemResult:
        error = entry.get("error")
        if isinstance(error, dict):
            return BatchItemResult(
                custom_id=request.custom_id,
                error=_status_to_error(error, context="batch item failed"),
            )

        response = entry.get("response")
        if not isinstance(response, dict):
            return BatchItemResult(
                custom_id=request.custom_id,
                error=MalformedResponseError("batch item had neither response nor error"),
            )

        # A GenerateContentResponse arm. The interactive adapter's extractors
        # are reused so the two paths cannot drift apart.
        from app.ai.google import GoogleProvider

        try:
            text = GoogleProvider._extract_text(response)
        except MalformedResponseError as exc:
            return BatchItemResult(custom_id=request.custom_id, error=exc)

        usage = _extract_usage(response, self.model, request.operation)
        return BatchItemResult(custom_id=request.custom_id, text=text, usage=usage)

    # -- HTTP --------------------------------------------------------------

    def _post(self, url: str, payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
        try:
            response = self._request("POST", url, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"provider timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"network error: {exc}") from exc
        return self._handle_response(response, operation=operation)

    def _get(self, url: str, *, operation: str) -> dict[str, Any]:
        try:
            response = self._request("GET", url)
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
        """Translate HTTP status codes into the shared error taxonomy."""
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
            raise InvalidRequestError(f"batch endpoint or job not found: {detail}")
        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitError(
                f"rate limited or quota exhausted: {detail}", retry_after
            )
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"provider error {response.status_code}: {detail}"
            )

        raise InvalidRequestError(f"unexpected status {response.status_code}: {detail}")

    def close(self) -> None:
        if self._owns_client and self._client is not None:  # pragma: no cover
            self._client.close()


# --- envelope helpers -------------------------------------------------------


def _inlined_request(request: BatchRequest) -> dict[str, Any]:
    """Render one :class:`BatchRequest` as an ``InlinedRequest``.

    The ``custom_id`` travels in ``metadata`` so a provider that echoes it can
    be matched regardless of order; the ordering fallback does not depend on it.
    """
    generate_content: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": request.system}]},
        "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
    }
    if request.json_schema is not None:
        generate_content["generationConfig"] = {
            "responseMimeType": "application/json",
            "responseSchema": request.json_schema,
        }

    return {
        "request": generate_content,
        "metadata": {"custom_id": request.custom_id},
    }


def _is_done(operation: dict[str, Any]) -> bool:
    return operation.get("done") is True


def _extract_inlined_responses(operation: dict[str, Any]) -> list[Any]:
    """Pull the inlined response list out of an operation defensively.

    Accepts both the documented nested shape
    (``response.inlinedResponses.inlinedResponses``) and a flatter
    ``response.inlinedResponses`` list, because the reference shows the same
    name at two levels and a defensive adapter is cheaper than a rejection.
    """
    response = operation.get("response")
    if not isinstance(response, dict):
        return []

    inlined = response.get("inlinedResponses")
    if isinstance(inlined, list):
        return inlined
    if isinstance(inlined, dict):
        nested = inlined.get("inlinedResponses")
        if isinstance(nested, list):
            return nested
    return []


def _status_to_error(status: dict[str, Any], *, context: str) -> Exception:
    """Map a ``google.rpc.Status`` onto the shared error taxonomy.

    gRPC/HTTP-style codes are mapped the same way the interactive adapter maps
    HTTP status codes, so a provider failure is classified identically on both
    paths.
    """
    code = _as_int(status.get("code"))
    message = str(status.get("message", ""))[:300]
    detail = f"{context}: {message}" if message else context

    if code in (401, 403, 7, 16):  # UNAUTHENTICATED / PERMISSION_DENIED
        return AuthError(detail)
    if code in (400, 3, 5):  # INVALID_ARGUMENT / NOT_FOUND
        return InvalidRequestError(detail)
    if code in (429, 8, 9):  # RESOURCE_EXHAUSTED / ABORTED
        return RateLimitError(detail)
    if code is not None and code >= 500:
        return ProviderUnavailableError(detail)
    if code in (14, 13):  # UNAVAILABLE / INTERNAL
        return ProviderUnavailableError(detail)
    if code in (4, 10):  # DEADLINE_EXCEEDED / ALREADY_EXISTS
        return ProviderUnavailableError(detail)
    if code is not None and code != 0:
        return InvalidRequestError(detail)
    return MalformedResponseError(detail)


def _extract_usage(
    response: dict[str, Any], model: str, operation: str
) -> UsageRecord | None:
    meta = response.get("usageMetadata")
    if not isinstance(meta, dict):
        return None
    return UsageRecord(
        provider="google-batch",
        model=model,
        operation=operation,
        input_tokens=meta.get("promptTokenCount"),
        output_tokens=meta.get("candidatesTokenCount"),
    )


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


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
