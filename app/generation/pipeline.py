"""AI generation pipeline.

Sequence (per the architecture spec):

1. Build a structured generation request.
2. Ask the provider for the problem package.
3. Parse the response into the expected schema.
4. Reject malformed or incomplete output.
5. Compile the reference implementation.
6. Run the reference against the generated tests.
7. Mark validated only if the quality gate passes.
8. Save the package and its quality report.
9. Return the problem for display.

The AI is never the authority on correctness: step 7 delegates to the
deterministic quality gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.ai.base import AIProvider
from app.ai.cache import GenerationCache
from app.ai.rate_limits import RetryPolicy, with_retry
from app.generation.normalize import normalize_payload
from app.generation.prompts import (
    GENERATION_SYSTEM_PROMPT,
    PROBLEM_JSON_SCHEMA,
    GenerationRequest,
    build_generation_prompt,
    parse_json_response,
)
from app.generation.quality_gate import QualityGate, QualityReport, apply_status
from app.schemas.problem import CONTENT_KEYS, Problem, ProblemMetadata
from app.schemas.test_case import TestCase


class GenerationError(RuntimeError):
    """Raised when a problem cannot be generated or does not pass the gate."""


@dataclass
class GenerationOutcome:
    """Result of a generation attempt."""

    problem: Problem
    quality: QualityReport
    from_cache: bool = False

    @property
    def accepted(self) -> bool:
        return self.quality.valid


class GenerationPipeline:
    """Generates, validates, and persists problem packages."""

    def __init__(
        self,
        provider: AIProvider,
        *,
        problems_dir: Path,
        cache: GenerationCache | None = None,
        gate: QualityGate | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep=None,
    ) -> None:
        self.provider = provider
        self.problems_dir = Path(problems_dir)
        self.cache = cache or GenerationCache(self.problems_dir / ".cache")
        self.gate = gate or QualityGate()
        self.retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep

    # -- public API --------------------------------------------------------

    def generate(self, request: GenerationRequest, *, use_cache: bool = True) -> GenerationOutcome:
        """Generate one validated problem, or raise :class:`GenerationError`."""
        cache_key = GenerationCache.make_key(
            {"provider": self.provider.name, "model": self.provider.model, **request.cache_parameters()}
        )

        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                problem = self._problem_from_payload(cached)
                report = self.gate.check(problem)
                if report.valid:
                    return GenerationOutcome(problem=problem, quality=report, from_cache=True)

        payload = self._request_generation(request)
        problem = self._validate_payload(payload)

        report = self.gate.check(problem)
        problem = apply_status(problem, report)

        outcome = GenerationOutcome(problem=problem, quality=report)

        if report.valid:
            if use_cache:
                self.cache.put(cache_key, payload)
            self.save(problem, report)

        return outcome

    def save(self, problem: Problem, report: QualityReport) -> Path:
        """Persist a problem package and its quality report."""
        package_dir = self.problems_dir / problem.id
        (package_dir / "starter").mkdir(parents=True, exist_ok=True)
        (package_dir / "reference").mkdir(parents=True, exist_ok=True)

        (package_dir / "statement.md").write_text(problem.statement_md, encoding="utf-8")
        (package_dir / "starter" / problem.metadata.entrypoint).write_text(
            problem.starter_code, encoding="utf-8"
        )
        (package_dir / "reference" / problem.metadata.entrypoint).write_text(
            problem.reference_solution, encoding="utf-8"
        )

        payload = self._problem_to_payload(problem)
        (package_dir / "problem.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (package_dir / "quality_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return package_dir

    # -- internals ---------------------------------------------------------

    def _request_generation(self, request: GenerationRequest) -> dict:
        prompt = build_generation_prompt(request)

        def call():
            response = self.provider.generate(
                system=GENERATION_SYSTEM_PROMPT,
                prompt=prompt,
                operation="generate_problem",
                json_schema=PROBLEM_JSON_SCHEMA,
            )
            return response.text

        kwargs = {"policy": self.retry_policy}
        if self._sleep is not None:
            kwargs["sleep"] = self._sleep

        text = with_retry(call, **kwargs)

        try:
            payload = parse_json_response(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise GenerationError(f"provider returned unparseable JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise GenerationError("provider returned JSON that is not an object")

        return payload

    def _validate_payload(self, payload: dict) -> Problem:
        """Build a Problem from raw payload, rejecting malformed output.

        The payload is normalised first: models do not honour JSON schemas
        reliably, so field-name variants (``description`` for ``statement_md``,
        split ``public_tests``/``hidden_tests``, a scalar ``topic``) are mapped
        onto the canonical shape before validation.
        """
        payload = normalize_payload(payload)

        # A payload with no tests is structurally incomplete. The schema allows
        # an empty list (a problem may be authored incrementally), so the
        # pipeline — which must only ever accept complete generated packages —
        # enforces the stronger requirement here.
        if not payload.get("tests"):
            raise GenerationError("generated payload contains no tests")

        metadata_raw = {k: v for k, v in payload.items() if k not in CONTENT_KEYS}

        # The provider may omit id/version; derive a stable placeholder rather
        # than failing the whole generation on a cosmetic field.
        metadata_raw.setdefault("id", "generated-problem")
        metadata_raw.setdefault("version", 1)
        metadata_raw.pop("language", None)

        try:
            metadata = ProblemMetadata.model_validate(metadata_raw)
        except ValidationError as exc:
            raise GenerationError(f"generated metadata failed validation: {exc}") from exc

        try:
            tests = [TestCase.model_validate(item) for item in payload.get("tests", [])]
        except ValidationError as exc:
            raise GenerationError(f"generated tests failed validation: {exc}") from exc

        try:
            return Problem(
                metadata=metadata,
                statement_md=payload.get("statement_md", ""),
                starter_code=payload.get("starter_code", ""),
                reference_solution=payload.get("reference_solution", ""),
                tests=tests,
                hints=payload.get("hints", []),
                solution_explanation=payload.get("solution_explanation", ""),
            )
        except ValidationError as exc:
            raise GenerationError(f"generated problem failed validation: {exc}") from exc

    @staticmethod
    def _problem_to_payload(problem: Problem) -> dict:
        """Serialise a problem back into the package JSON shape."""
        payload = problem.metadata.model_dump(mode="json")
        payload["tests"] = [t.model_dump(mode="json") for t in problem.tests]
        payload["hints"] = [h.model_dump(mode="json") for h in problem.hints]
        payload["solution_explanation"] = problem.solution_explanation
        return payload

    def _problem_from_payload(self, payload: dict) -> Problem:
        return self._validate_payload(payload)
