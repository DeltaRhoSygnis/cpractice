"""Shelf runner: prepare a batch of psets in one provider run (spec S7).

A *shelf* is a set of problem sets prepared **before** the learner is present.
The runner is deliberately thin around the existing pipeline:

    N pset requests
      └─ for each: refuse (over budget) / serve from cache / submit to the batch
           └─ batch provider: one job -> N raw responses
                └─ for each response: GenerationPipeline.generate(...)
                     └─ the SAME QualityGate decides validated / rejected

Two invariants are load-bearing and must not be relaxed:

1. **The gate is the only acceptance authority.** The batch path calls the same
   :class:`~app.generation.pipeline.GenerationPipeline.generate` with the same
   :class:`~app.generation.quality_gate.QualityGate` as an interactive request.
   Batching changes *when and how many* calls are made, never *what is
   accepted*.
2. **A failing item is data, not a job failure.** An item whose response is
   malformed, whose provider call failed, or whose package the gate rejects is
   recorded with its findings; the rest of the shelf still prepares (spec S10).

Idempotency and budget come from existing machinery: the content-addressed
:class:`~app.ai.cache.GenerationCache` key is consulted before submission, and
``AI_DAILY_REQUEST_BUDGET`` bounds how many items may reach the provider.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from app.ai.base import (
    AIProvider,
    AIProviderError,
    BatchItemResult,
    BatchProvider,
    BatchRequest,
    GenerationResponse,
)
from app.ai.cache import GenerationCache
from app.generation.pipeline import GenerationError, GenerationOutcome, GenerationPipeline
from app.generation.prompts import (
    GENERATION_SYSTEM_PROMPT,
    GenerationRequest,
    build_generation_prompt,
)
from app.schemas.pedagogy import ExerciseRole
from app.storage.usage_ledger import BatchProvenance, BatchProvenanceStore

logger = logging.getLogger("cpractice")


class ShelfOutcome(str, Enum):
    """Why an item ended the way it did."""

    #: The gate accepted the package; it was stored.
    VALIDATED = "validated"
    #: The response or package failed; findings are recorded.
    REJECTED = "rejected"
    #: The provider failed for this item; the job continued.
    PROVIDER_FAILED = "provider_failed"
    #: An identical request was already prepared; no provider call was made.
    CACHED = "cached"
    #: The daily budget was exhausted; the item never reached the provider.
    REFUSED = "refused"


@dataclass
class ShelfItem:
    """One pset to prepare.

    ``request`` is a normal :class:`GenerationRequest`; ``custom_id`` is the
    correlation id echoed by the batch provider. When absent, a stable id is
    derived from the item's position so results can always be matched.
    """

    request: GenerationRequest
    custom_id: str = ""


@dataclass
class ShelfItemResult:
    """The recorded outcome for one shelf item."""

    custom_id: str
    outcome: ShelfOutcome
    #: The stored problem id, when a package was produced.
    problem_id: str | None = None
    from_cache: bool = False
    #: Gate findings (code + message) when the package was rejected.
    findings: list[dict] = field(default_factory=list)
    #: A short, non-sensitive reason when the item was refused or failed.
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "custom_id": self.custom_id,
            "outcome": self.outcome.value,
            "problem_id": self.problem_id,
            "from_cache": self.from_cache,
            "findings": self.findings,
            "detail": self.detail,
        }


@dataclass
class ShelfReport:
    """The result of one shelf run."""

    job_id: str
    items: list[ShelfItemResult] = field(default_factory=list)

    @property
    def validated(self) -> list[ShelfItemResult]:
        return [i for i in self.items if i.outcome is ShelfOutcome.VALIDATED]

    @property
    def rejected(self) -> list[ShelfItemResult]:
        return [i for i in self.items if i.outcome is ShelfOutcome.REJECTED]

    @property
    def provider_failed(self) -> list[ShelfItemResult]:
        return [i for i in self.items if i.outcome is ShelfOutcome.PROVIDER_FAILED]

    @property
    def refused(self) -> list[ShelfItemResult]:
        return [i for i in self.items if i.outcome is ShelfOutcome.REFUSED]

    @property
    def cached(self) -> list[ShelfItemResult]:
        return [i for i in self.items if i.outcome is ShelfOutcome.CACHED]

    @property
    def problem_ids(self) -> list[str]:
        """Ids of every pset now present on the shelf (validated or cached)."""
        return [
            i.problem_id
            for i in self.items
            if i.problem_id and i.outcome in (ShelfOutcome.VALIDATED, ShelfOutcome.CACHED)
        ]

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "prepared": len(self.validated) + len(self.cached),
            "validated": len(self.validated),
            "cached": len(self.cached),
            "rejected": len(self.rejected),
            "provider_failed": len(self.provider_failed),
            "refused": len(self.refused),
            "problems": self.problem_ids,
            "items": [i.to_dict() for i in self.items],
        }


class _BatchReplayProvider(AIProvider):
    """Serves a prefetched batch response to one :meth:`generate` call.

    The shelf runner submits prompts as a batch and receives N raw responses.
    To run each response through the **real** pipeline, it hands the pipeline
    this thin adapter: it replays the prefetched text for the generation
    operation and delegates everything else (for example a blueprint call, when
    blueprints are designed) to the underlying provider. Selecting which text
    to replay is explicit via :meth:`use_response`, so no ordering is assumed
    beyond the runner's own loop.

    ``identity`` supplies ``name``/``model``. It is the pipeline's original
    provider, so the cache key the pipeline computes while replaying is byte
    for byte the key the runner computed before submitting - a mismatch there
    would make a re-run duplicate psets instead of hitting the cache.
    """

    def __init__(self, delegate: AIProvider, identity: AIProvider) -> None:
        self._delegate = delegate
        self._identity = identity
        self._pending: str | None = None
        self._pending_usage = None
        self._pending_error: AIProviderError | None = None

    # -- identity mirrors the pipeline's provider so cache keys stay stable --
    @property
    def name(self) -> str:
        return self._identity.name

    @property
    def model(self) -> str:
        return self._identity.model

    def use_response(self, result: BatchItemResult) -> None:
        self._pending_error = result.error
        self._pending = result.text
        self._pending_usage = result.usage

    def generate(self, *, system, prompt, operation="generate", json_schema=None) -> GenerationResponse:
        if operation == "generate_problem" and (
            self._pending is not None or self._pending_error is not None
        ):
            error = self._pending_error
            # Capture usage before ``_pending_text`` clears it, and let that
            # helper be the single place that consumes ``_pending``.
            usage = self._pending_usage
            text = self._pending_text()
            self._pending_error = None
            if error is not None:
                raise error
            return GenerationResponse(text=text, usage=usage)

        return self._delegate.generate(
            system=system, prompt=prompt, operation=operation, json_schema=json_schema
        )

    def _pending_text(self) -> str:
        # Read once into a local so a re-entrant call cannot double-consume.
        text = self._pending
        self._pending = None
        self._pending_usage = None
        return text or ""

    def check_connectivity(self) -> bool:
        return self._delegate.check_connectivity()

    def capabilities(self) -> dict:
        return self._delegate.capabilities()


class ShelfRunner:
    """Prepares a shelf of psets through a batch provider and the pipeline."""

    def __init__(
        self,
        *,
        pipeline: GenerationPipeline,
        batch_provider: BatchProvider,
        problems_dir: Path,
        cache: GenerationCache | None = None,
        provenance_store: BatchProvenanceStore | None = None,
        daily_budget: int = 0,
        requests_today: int = 0,
        exercise_role: ExerciseRole = ExerciseRole.CORE_REASONING,
        prerequisites: list[str] | None = None,
        known_concepts: list[str] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.batch_provider = batch_provider
        self.problems_dir = Path(problems_dir)
        self.cache = cache or pipeline.cache
        self.provenance_store = provenance_store
        #: 0 means unlimited (mirrors ``AI_DAILY_REQUEST_BUDGET``).
        self.daily_budget = daily_budget
        #: Requests already spent today, so the shelf honours the shared budget.
        self.requests_today = requests_today
        self.exercise_role = exercise_role
        self.prerequisites = list(prerequisites or [])
        self.known_concepts = list(known_concepts or [])

    # -- public API --------------------------------------------------------

    def prepare(self, items: list[ShelfItem], *, job_id: str) -> ShelfReport:
        """Prepare every item, returning a per-item report.

        A failure in one item never aborts the run: each is recorded and the
        shelf continues (spec S10). Only an unrecoverable provider/transport
        error for the whole job is raised, because then no item can be served.
        """
        report = ShelfReport(job_id=job_id)
        if not items:
            return report

        # 1. Split items: cache hits cost nothing and are not submitted.
        to_submit: list[_Prepared] = []
        budget_used = self.requests_today

        for index, item in enumerate(items):
            custom_id = item.custom_id or f"item-{index:03d}"
            prepared = _Prepared(
                item=item,
                custom_id=custom_id,
                cache_key=self.pipeline.cache_key_for(
                    item.request,
                    design_blueprint=False,
                    exercise_role=self.exercise_role,
                    prerequisites=self.prerequisites,
                ),
            )

            cached = self.cache.get(prepared.cache_key)
            if cached is not None:
                problem_id = _problem_id_from_payload(cached)
                report.items.append(
                    ShelfItemResult(
                        custom_id=custom_id,
                        outcome=ShelfOutcome.CACHED,
                        problem_id=problem_id,
                        from_cache=True,
                    )
                )
                self._record_provenance(
                    problem_id, job_id, ShelfOutcome.CACHED, from_cache=True
                )
                continue

            if self._over_budget(budget_used):
                report.items.append(
                    ShelfItemResult(
                        custom_id=custom_id,
                        outcome=ShelfOutcome.REFUSED,
                        detail=(
                            f"daily request budget of {self.daily_budget} reached; "
                            "item not submitted"
                        ),
                    )
                )
                # A refusal is not a stored pset, so it carries no provenance.
                continue

            budget_used += 1
            to_submit.append(prepared)

        if not to_submit:
            self._sort_items(report)
            return report

        # 2. One batch submission for every non-cached, in-budget item.
        batch_requests = [
            BatchRequest(
                custom_id=prepared.custom_id,
                system=GENERATION_SYSTEM_PROMPT,
                prompt=build_generation_prompt(prepared.item.request),
                operation="generate_problem",
                json_schema=None,
            )
            for prepared in to_submit
        ]

        results = self._submit(batch_requests)
        by_id = {result.custom_id: result for result in results}

        # 3. Run each response through the real pipeline + gate. The pipeline's
        #    provider is swapped for the replay adapter so no provider call is
        #    made during this pass; the replay adapter mirrors the original
        #    provider's identity so the pipeline's cache key is unchanged.
        original_provider = self.pipeline.provider
        delegate = self._batch_delegate()
        replay = _BatchReplayProvider(delegate, identity=original_provider)
        self.pipeline.provider = replay
        try:
            for prepared in to_submit:
                batch_result = by_id.get(prepared.custom_id)
                report.items.append(
                    self._process(prepared, batch_result, replay, job_id=job_id)
                )
        finally:
            self.pipeline.provider = original_provider

        self._sort_items(report)
        return report

    # -- internals ---------------------------------------------------------

    def _submit(self, batch_requests: list[BatchRequest]) -> list[BatchItemResult]:
        """Submit the batch, translating a job-level failure into a taxonomy error.

        ``BatchProvider.submit`` raises only for a whole-job failure. That is
        raised to the caller: with no responses there is nothing to record
        per item, and the API layer must map it to a status code.
        """
        return self.batch_provider.submit(batch_requests)

    def _process(
        self,
        prepared: "_Prepared",
        batch_result: BatchItemResult | None,
        replay: _BatchReplayProvider,
        *,
        job_id: str,
    ) -> ShelfItemResult:
        if batch_result is None:
            return ShelfItemResult(
                custom_id=prepared.custom_id,
                outcome=ShelfOutcome.PROVIDER_FAILED,
                detail="batch provider returned no result for this item",
            )

        if not batch_result.ok:
            error = batch_result.error
            return ShelfItemResult(
                custom_id=prepared.custom_id,
                outcome=ShelfOutcome.PROVIDER_FAILED,
                detail=f"{type(error).__name__}: {error}" if error else "provider failed",
            )

        replay.use_response(batch_result)

        try:
            outcome = self.pipeline.generate(
                prepared.item.request,
                design_blueprint=False,
                exercise_role=self.exercise_role,
                prerequisites=self.prerequisites,
                known_concepts=self.known_concepts or None,
            )
        except AIProviderError as exc:
            return ShelfItemResult(
                custom_id=prepared.custom_id,
                outcome=ShelfOutcome.PROVIDER_FAILED,
                detail=f"{type(exc).__name__}: {exc}",
            )
        except GenerationError as exc:
            # The response reached the pipeline but could not be turned into a
            # package (unparseable JSON, missing tests, ...). That is a rejected
            # item with a finding, not a provider failure.
            return ShelfItemResult(
                custom_id=prepared.custom_id,
                outcome=ShelfOutcome.REJECTED,
                findings=[{"code": "generation-error", "message": str(exc)}],
                detail=str(exc),
            )

        return self._from_outcome(prepared, outcome, job_id=job_id)

    def _from_outcome(
        self, prepared: "_Prepared", outcome: GenerationOutcome, *, job_id: str
    ) -> ShelfItemResult:
        if outcome.accepted:
            self._record_provenance(
                outcome.problem.id, job_id, ShelfOutcome.VALIDATED,
                from_cache=outcome.from_cache,
            )
            return ShelfItemResult(
                custom_id=prepared.custom_id,
                outcome=ShelfOutcome.VALIDATED,
                problem_id=outcome.problem.id,
                from_cache=outcome.from_cache,
            )

        findings = [
            {"code": f.code, "message": f.message, "severity": f.severity.value}
            for f in outcome.quality.errors
        ]
        # A rejected package is still traceable to its job (spec S7): record the
        # outcome, but only for a package that was actually parsed (it has an
        # id). Unparseable output never reaches here.
        self._record_provenance(
            outcome.problem.id, job_id, ShelfOutcome.REJECTED, from_cache=False
        )
        return ShelfItemResult(
            custom_id=prepared.custom_id,
            outcome=ShelfOutcome.REJECTED,
            problem_id=outcome.problem.id,
            findings=findings,
            detail="problem set did not pass the quality gate",
        )

    def _record_provenance(
        self,
        problem_id: str | None,
        job_id: str,
        outcome: ShelfOutcome,
        *,
        from_cache: bool,
    ) -> None:
        if self.provenance_store is None or not problem_id:
            return
        self.provenance_store.record(
            BatchProvenance(
                problem_id=problem_id,
                job_id=job_id,
                provider=self.batch_provider.name,
                model=self.batch_provider.model,
                prompt_version=_prompt_version(),
                outcome=outcome.value,
                from_cache=from_cache,
            )
        )

    def _batch_delegate(self) -> AIProvider:
        """The provider used for non-replayed calls (e.g. blueprints).

        The batch provider may also implement :class:`AIProvider` (the mock
        does); when it does, it answers those calls too. Otherwise they are
        routed through the pipeline's own provider, so a blueprint still works.
        """
        if isinstance(self.batch_provider, AIProvider):
            return self.batch_provider
        return self.pipeline.provider

    def _over_budget(self, used: int) -> bool:
        if self.daily_budget <= 0:
            return False
        return used >= self.daily_budget

    @staticmethod
    def _sort_items(report: ShelfReport) -> None:
        """Order the report by input position, not completion order."""
        report.items.sort(key=lambda i: i.custom_id)


@dataclass
class _Prepared:
    """Internal bookkeeping for one item being prepared."""

    item: ShelfItem
    custom_id: str
    cache_key: str


def _prompt_version() -> str:
    from app.ai.prompts_loader import PROMPT_VERSION

    return PROMPT_VERSION


def _problem_id_from_payload(payload: dict) -> str | None:
    """Recover the problem id from a cached payload, defensively."""
    if not isinstance(payload, dict):
        return None
    problem_id = payload.get("id")
    return problem_id if isinstance(problem_id, str) and problem_id else None


def shelf_item_count_within_budget(items: int, daily_budget: int, *, requests_today: int = 0) -> int:
    """How many of ``items`` a shelf run may submit under the budget.

    Exposed so a caller can size a shelf from ``AI_DAILY_REQUEST_BUDGET`` before
    building requests. A budget of 0 means unlimited.
    """
    if daily_budget <= 0:
        return items
    remaining = max(0, daily_budget - requests_today)
    return min(items, remaining)
