"""Batch shelf preparation tests (spec S7, plan Phase 6).

Every test drives the shelf runner with a mocked batch provider: no live API
call is ever made. The point these tests defend is the spec's central
invariant - *the batch path calls the same pipeline and the same gate as
interactive generation*, so batching can never lower the bar.

Covered:

* N responses -> N outcomes through the real pipeline + gate;
* a malformed item is recorded as rejected while the others validate;
* idempotency: the same batch twice does not duplicate packages;
* a budget smaller than N refuses the excess with no provider call;
* provenance is recorded per stored pset;
* a batch HTTP failure maps onto the shared error taxonomy;
* the gate is not bypassed: an item whose reference fails its tests is rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.ai.base import (
    AuthError,
    BatchRequest,
    InvalidRequestError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.ai.google_batch import GoogleBatchProvider
from app.ai.mock import MockBatchProvider
from app.generation.batch import (
    ShelfItem,
    ShelfOutcome,
    ShelfRunner,
    shelf_item_count_within_budget,
)
from app.generation.pipeline import GenerationPipeline
from app.generation.prompts import GenerationRequest
from app.schemas.problem import ProblemKind
from app.storage.database import Database
from app.storage.problem_repository import ProblemRepository
from app.storage.usage_ledger import BatchProvenanceStore
from tests.test_pset_generation import pset_payload


# --- fixtures ---------------------------------------------------------------

# A shelf item is a problem set: scenario, distribution code, tagged tests,
# reference. ``pset_payload`` reconstructs the known-good "vote tally" package
# so the runner is exercised against content already proven to pass the gate.


def _pset_payload(problem_id: str, title: str) -> dict:
    payload = pset_payload()
    payload["id"] = problem_id
    payload["title"] = title
    return payload


def _pset_request(topic: str = "voting") -> GenerationRequest:
    return GenerationRequest(
        topic=topic,
        kind=ProblemKind.PROBLEM_SET,
        new_concept="arrays",
        assumed_known=["for_loops", "input_output"],
    )


def _shelf(count: int) -> list[ShelfItem]:
    return [
        ShelfItem(custom_id=f"item-{index:03d}", request=_pset_request(f"topic-{index}"))
        for index in range(count)
    ]


def _pipeline(tmp_path: Path, provider) -> GenerationPipeline:
    return GenerationPipeline(
        provider,
        problems_dir=tmp_path / "problems",
        known_concepts=["for_loops", "input_output"],
    )


def _runner(
    tmp_path: Path,
    provider,
    *,
    daily_budget: int = 0,
    requests_today: int = 0,
    provenance: BatchProvenanceStore | None = None,
) -> tuple[ShelfRunner, GenerationPipeline]:
    pipeline = _pipeline(tmp_path, provider)
    runner = ShelfRunner(
        pipeline=pipeline,
        batch_provider=provider,
        problems_dir=tmp_path / "problems",
        provenance_store=provenance,
        daily_budget=daily_budget,
        requests_today=requests_today,
        known_concepts=["for_loops", "input_output"],
    )
    return runner, pipeline


# --- N responses -> N outcomes through the real pipeline + gate -------------


def test_shelf_prepares_n_validated_psets(tmp_path: Path) -> None:
    responses = {
        f"item-{i:03d}": json.dumps(_pset_payload(f"shelf-pset-{i}", f"Shelf Pset {i}"))
        for i in range(3)
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider)

    report = runner.prepare(_shelf(3), job_id="job-1")

    assert len(report.items) == 3
    assert len(report.validated) == 3
    assert report.to_dict()["prepared"] == 3
    # Every package is actually on disk and reloads through the repository.
    repository = ProblemRepository(tmp_path / "problems")
    for i in range(3):
        problem = repository.load(f"shelf-pset-{i}")
        assert problem.metadata.kind is ProblemKind.PROBLEM_SET


def test_shelf_uses_one_batch_submission(tmp_path: Path) -> None:
    """All N items go to the provider as exactly one job (the point of batch)."""
    responses = {
        f"item-{i:03d}": json.dumps(_pset_payload(f"shelf-pset-{i}", f"Pset {i}"))
        for i in range(4)
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider)

    runner.prepare(_shelf(4), job_id="job-1")

    assert len(provider.batch_calls) == 1
    assert len(provider.batch_calls[0]) == 4


def test_shelf_report_order_matches_input_order(tmp_path: Path) -> None:
    responses = {
        f"item-{i:03d}": json.dumps(_pset_payload(f"shelf-pset-{i}", f"Pset {i}"))
        for i in range(3)
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider)

    report = runner.prepare(_shelf(3), job_id="job-1")

    assert [item.custom_id for item in report.items] == [
        "item-000",
        "item-001",
        "item-002",
    ]


# --- partial failure --------------------------------------------------------


def test_malformed_item_is_rejected_while_others_validate(tmp_path: Path) -> None:
    """One bad item does not fail the job (spec S10)."""
    responses = {
        "item-000": json.dumps(_pset_payload("shelf-pset-0", "Good 0")),
        "item-001": "this is not valid JSON at all",
        "item-002": json.dumps(_pset_payload("shelf-pset-2", "Good 2")),
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider)

    report = runner.prepare(_shelf(3), job_id="job-partial")

    outcomes = {item.custom_id: item.outcome for item in report.items}
    assert outcomes["item-000"] is ShelfOutcome.VALIDATED
    assert outcomes["item-001"] is ShelfOutcome.REJECTED
    assert outcomes["item-002"] is ShelfOutcome.VALIDATED
    # The rejection carries a finding rather than being silently dropped.
    rejected = report.rejected[0]
    assert rejected.findings
    assert rejected.findings[0]["code"] == "generation-error"


def test_per_item_provider_error_is_recorded_not_raised(tmp_path: Path) -> None:
    """A provider error confined to one item is data, not a job failure."""
    responses = {
        "item-000": json.dumps(_pset_payload("shelf-pset-0", "Good 0")),
    }
    provider = MockBatchProvider(
        batch_responses=responses,
        batch_errors={"item-001": ProviderUnavailableError("item blip")},
    )
    runner, _ = _runner(tmp_path, provider)

    report = runner.prepare(_shelf(2), job_id="job-partial")

    outcomes = {item.custom_id: item.outcome for item in report.items}
    assert outcomes["item-000"] is ShelfOutcome.VALIDATED
    assert outcomes["item-001"] is ShelfOutcome.PROVIDER_FAILED
    assert "item blip" in report.provider_failed[0].detail


# --- idempotency ------------------------------------------------------------


def test_re_running_the_same_batch_does_not_duplicate_psets(tmp_path: Path) -> None:
    responses = {
        f"item-{i:03d}": json.dumps(_pset_payload(f"shelf-pset-{i}", f"Pset {i}"))
        for i in range(2)
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider)

    first = runner.prepare(_shelf(2), job_id="job-1")
    second = runner.prepare(_shelf(2), job_id="job-2")

    assert len(first.validated) == 2
    # The second run is served entirely from the cache: no new provider call.
    assert len(second.cached) == 2
    assert len(second.validated) == 0
    assert len(provider.batch_calls) == 1
    # Exactly two problem packages exist on disk, not four. The problems
    # directory also holds the content-addressed generation cache (``.cache``),
    # so count only real packages (a directory carrying ``problem.json``).
    problems_dir = tmp_path / "problems"
    ids = sorted(
        p.name for p in problems_dir.iterdir() if (p / "problem.json").is_file()
    )
    assert ids == ["shelf-pset-0", "shelf-pset-1"]


def test_cached_item_reports_its_problem_id(tmp_path: Path) -> None:
    responses = {"item-000": json.dumps(_pset_payload("shelf-pset-0", "Pset 0"))}
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider)

    runner.prepare(_shelf(1), job_id="job-1")
    second = runner.prepare(_shelf(1), job_id="job-2")

    assert second.cached[0].problem_id == "shelf-pset-0"
    assert second.cached[0].from_cache is True


# --- budget -----------------------------------------------------------------


def test_budget_smaller_than_n_refuses_the_excess(tmp_path: Path) -> None:
    """Over-budget items are refused and recorded, with no provider call."""
    responses = {
        f"item-{i:03d}": json.dumps(_pset_payload(f"shelf-pset-{i}", f"Pset {i}"))
        for i in range(4)
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider, daily_budget=2)

    report = runner.prepare(_shelf(4), job_id="job-budget")

    assert len(report.validated) == 2
    assert len(report.refused) == 2
    # Only the two in-budget items reached the provider.
    assert len(provider.batch_calls) == 1
    assert len(provider.batch_calls[0]) == 2
    assert [r.custom_id for r in report.refused] == ["item-002", "item-003"]
    assert all("budget" in r.detail for r in report.refused)


def test_budget_counts_requests_already_spent_today(tmp_path: Path) -> None:
    responses = {"item-000": json.dumps(_pset_payload("shelf-pset-0", "Pset 0"))}
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(
        tmp_path, provider, daily_budget=3, requests_today=3
    )

    report = runner.prepare(_shelf(1), job_id="job-budget")

    assert report.refused
    assert provider.batch_calls == []


def test_zero_budget_is_unlimited(tmp_path: Path) -> None:
    responses = {
        f"item-{i:03d}": json.dumps(_pset_payload(f"shelf-pset-{i}", f"Pset {i}"))
        for i in range(3)
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider, daily_budget=0)

    report = runner.prepare(_shelf(3), job_id="job-unlimited")

    assert len(report.validated) == 3
    assert report.refused == []


def test_shelf_item_count_helper_bounds_a_shelf() -> None:
    assert shelf_item_count_within_budget(5, 0) == 5
    assert shelf_item_count_within_budget(5, 3) == 3
    assert shelf_item_count_within_budget(5, 10) == 5
    assert shelf_item_count_within_budget(5, 10, requests_today=8) == 2
    assert shelf_item_count_within_budget(5, 10, requests_today=10) == 0


# --- provenance -------------------------------------------------------------


def test_provenance_is_recorded_per_stored_pset(tmp_path: Path) -> None:
    from app.ai.prompts_loader import PROMPT_VERSION

    store = BatchProvenanceStore(Database(tmp_path / "db.sqlite"))
    responses = {
        f"item-{i:03d}": json.dumps(_pset_payload(f"shelf-pset-{i}", f"Pset {i}"))
        for i in range(2)
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider, provenance=store)

    runner.prepare(_shelf(2), job_id="job-prov")

    for i in range(2):
        record = store.get(f"shelf-pset-{i}")
        assert record is not None
        assert record.job_id == "job-prov"
        assert record.provider == "mock-batch"
        assert record.model == "mock-model"
        assert record.prompt_version == PROMPT_VERSION
        assert record.outcome == "validated"


def test_provenance_is_grouped_by_job(tmp_path: Path) -> None:
    store = BatchProvenanceStore(Database(tmp_path / "db.sqlite"))
    responses = {
        f"item-{i:03d}": json.dumps(_pset_payload(f"shelf-pset-{i}", f"Pset {i}"))
        for i in range(2)
    }
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider, provenance=store)

    runner.prepare(_shelf(2), job_id="job-group")

    assert len(store.for_job("job-group")) == 2


def test_provenance_records_a_rejected_outcome(tmp_path: Path) -> None:
    """A rejected pset is still traceable to the job that produced it."""
    store = BatchProvenanceStore(Database(tmp_path / "db.sqlite"))
    payload = _pset_payload("shelf-bad", "Bad")
    # A reference that does not compile: the gate must reject it.
    payload["reference_solution"] = 'int main(void){ printf("x" return 0; }'
    provider = MockBatchProvider(batch_responses={"item-000": json.dumps(payload)})
    runner, _ = _runner(tmp_path, provider, provenance=store)

    runner.prepare(_shelf(1), job_id="job-reject")

    record = store.get("shelf-bad")
    assert record is not None
    assert record.outcome == "rejected"


def test_provenance_has_no_prompt_or_response_text(tmp_path: Path) -> None:
    """Provenance is metadata only: never prompts, never response bodies."""
    store = BatchProvenanceStore(Database(tmp_path / "db.sqlite"))
    responses = {"item-000": json.dumps(_pset_payload("shelf-pset-0", "Pset 0"))}
    provider = MockBatchProvider(batch_responses=responses)
    runner, _ = _runner(tmp_path, provider, provenance=store)

    runner.prepare(_shelf(1), job_id="job-meta")

    record = store.get("shelf-pset-0")
    assert record is not None
    serialised = json.dumps(record.to_dict())
    # No statement text, no reference code, no prompt text.
    assert "Village Vote Tally" not in serialised
    assert "#include" not in serialised


# --- gate is not bypassed ---------------------------------------------------


def test_gate_rejects_an_item_whose_reference_fails_its_tests(tmp_path: Path) -> None:
    """The deterministic gate, not the batch transport, decides validity."""
    payload = _pset_payload("shelf-wrong", "Wrong")
    # The reference compiles but produces the wrong output for every test.
    payload["reference_solution"] = (
        "#include <stdio.h>\n"
        "int main(void) { printf(\"nonsense\\n\"); return 0; }\n"
    )
    provider = MockBatchProvider(batch_responses={"item-000": json.dumps(payload)})
    runner, _ = _runner(tmp_path, provider)

    report = runner.prepare(_shelf(1), job_id="job-gate")

    assert len(report.validated) == 0
    assert len(report.rejected) == 1
    codes = [f["code"] for f in report.rejected[0].findings]
    assert "reference-fails-tests" in codes
    # A rejected pset is not written to the shelf.
    assert not (tmp_path / "problems" / "shelf-wrong").exists()


def test_gate_rejects_a_pset_with_a_solved_starter(tmp_path: Path) -> None:
    """A distribution starter that solves the pset is still rejected in batch."""
    payload = _pset_payload("shelf-solved", "Solved")
    payload["starter_code"] = payload["reference_solution"]
    provider = MockBatchProvider(batch_responses={"item-000": json.dumps(payload)})
    runner, _ = _runner(tmp_path, provider)

    report = runner.prepare(_shelf(1), job_id="job-gate")

    assert len(report.rejected) == 1
    codes = [f["code"] for f in report.rejected[0].findings]
    assert "starter-passes-all-tests" in codes


# --- job-level provider failure (Google Batch adapter) ----------------------


def _google_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _batch_operation(responses: list[dict]) -> dict:
    """A completed operation carrying inline responses, as the API returns."""
    return {
        "name": "batches/abc123",
        "done": True,
        "response": {"inlinedResponses": {"inlinedResponses": responses}},
    }


def _candidate(text: str) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2},
    }


def test_google_batch_adapter_returns_one_result_per_request() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen["submit_body"] = json.loads(request.content)
            return httpx.Response(200, json={"name": "batches/abc123", "done": False})
        return httpx.Response(200, json=_batch_operation([
            {"response": _candidate("first")},
            {"response": _candidate("second")},
        ]))

    provider = GoogleBatchProvider("key", client=_google_client(handler), sleep=lambda _: None)
    requests = [
        BatchRequest(custom_id="a", system="s", prompt="p1"),
        BatchRequest(custom_id="b", system="s", prompt="p2"),
    ]

    results = provider.submit(requests)

    assert [r.custom_id for r in results] == ["a", "b"]
    assert [r.text for r in results] == ["first", "second"]
    # The submit envelope carries every request and the correlation id.
    inlined = seen["submit_body"]["batch"]["inputConfig"]["requests"]["requests"]
    assert len(inlined) == 2
    assert inlined[0]["metadata"]["custom_id"] == "a"
    assert inlined[0]["request"]["contents"][0]["parts"][0]["text"] == "p1"


def test_google_batch_adapter_maps_submit_failure_to_taxonomy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    provider = GoogleBatchProvider("key", client=_google_client(handler))

    with pytest.raises(AuthError):
        provider.submit([BatchRequest(custom_id="a", system="s", prompt="p")])


def test_google_batch_adapter_maps_rate_limit_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": {"message": "quota"}}, headers={"Retry-After": "9"}
        )

    provider = GoogleBatchProvider("key", client=_google_client(handler))

    with pytest.raises(RateLimitError) as excinfo:
        provider.submit([BatchRequest(custom_id="a", system="s", prompt="p")])

    assert excinfo.value.retry_after_seconds == 9.0


def test_google_batch_adapter_maps_400_to_invalid_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad batch"}})

    provider = GoogleBatchProvider("key", client=_google_client(handler))

    with pytest.raises(InvalidRequestError):
        provider.submit([BatchRequest(custom_id="a", system="s", prompt="p")])


def test_google_batch_adapter_maps_500_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "server"}})

    provider = GoogleBatchProvider("key", client=_google_client(handler))

    with pytest.raises(ProviderUnavailableError):
        provider.submit([BatchRequest(custom_id="a", system="s", prompt="p")])


def test_google_batch_adapter_per_item_error_is_not_a_job_failure() -> None:
    """A single failed item is returned inside the list, not raised."""
    provider = GoogleBatchProvider(
        "key",
        client=_google_client(
            lambda request: httpx.Response(200, json=_batch_operation([
                {"response": _candidate("ok")},
                {"error": {"code": 400, "message": "item rejected"}},
            ]))
        ),
        sleep=lambda _: None,
    )

    results = provider.submit([
        BatchRequest(custom_id="a", system="s", prompt="p1"),
        BatchRequest(custom_id="b", system="s", prompt="p2"),
    ])

    assert results[0].ok is True
    assert results[1].ok is False
    assert isinstance(results[1].error, InvalidRequestError)


def test_google_batch_adapter_never_leaks_the_key() -> None:
    secret = "super-secret-batch-key"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(InvalidRequestError) as excinfo:
        GoogleBatchProvider(secret, client=_google_client(handler)).submit(
            [BatchRequest(custom_id="a", system="s", prompt="p")]
        )

    assert secret not in str(excinfo.value)


def test_google_batch_adapter_missing_key_raises_auth_error() -> None:
    with pytest.raises(AuthError):
        GoogleBatchProvider(None)


def test_shelf_surfaces_a_job_level_provider_failure(tmp_path: Path) -> None:
    """A whole-job failure is raised so the API layer can map it to a status."""
    provider = MockBatchProvider(
        batch_job_error=ProviderUnavailableError("batch endpoint down")
    )
    runner, _ = _runner(tmp_path, provider)

    with pytest.raises(ProviderUnavailableError):
        runner.prepare(_shelf(2), job_id="job-down")


# --- empty shelf ------------------------------------------------------------


def test_empty_shelf_makes_no_provider_call(tmp_path: Path) -> None:
    provider = MockBatchProvider(batch_responses={})
    runner, _ = _runner(tmp_path, provider)

    report = runner.prepare([], job_id="job-empty")

    assert report.items == []
    assert provider.batch_calls == []
