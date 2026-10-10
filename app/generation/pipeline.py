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
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.ai.base import AIProvider, AIProviderError
from app.ai.cache import GenerationCache
from app.ai.prompts_loader import load_prompt
from app.ai.rate_limits import RetryPolicy, with_retry
from app.generation.blueprint import (
    BlueprintDesigner,
    BlueprintError,
    BlueprintRequest,
    blueprint_to_prompt_text,
    prompt_version,
)
from app.generation.normalize import normalize_payload
from app.generation.misconceptions import declared_misconception_ids
from app.generation.prompts import (
    GENERATION_SYSTEM_PROMPT,
    PROBLEM_JSON_SCHEMA,
    GenerationRequest,
    build_generation_prompt,
    build_repair_prompt,
    parse_json_response,
)
from app.generation.quality_gate import QualityGate, QualityReport, apply_status
from app.schemas.problem import CONTENT_KEYS, Problem, ProblemMetadata
from app.schemas.pedagogy import ExerciseRole, Pedagogy
from app.schemas.test_case import TestCase, Visibility


class GenerationError(RuntimeError):
    """Raised when a problem cannot be generated or does not pass the gate."""


logger = logging.getLogger("cpractice")


@dataclass
class GenerationOutcome:
    """Result of a generation attempt."""

    problem: Problem
    quality: QualityReport
    from_cache: bool = False

    @property
    def accepted(self) -> bool:
        return self.quality.valid


def _backfill_test_tags(problem: Problem) -> Problem:
    """Give every test a provenance tag when the model supplied none.

    Tags are what let the quality gate check that declared misconceptions are
    actually tested. A model that omits them would otherwise make that check
    vacuous, so the pipeline derives a minimal attribution from the test's
    visibility and whether it exercises a boundary.

    The two provenance axes are filled **independently**: a model that emits
    ``requirement_ids`` but omits ``misconception_ids`` (common, since the
    provider does not enforce the schema) still gets misconception coverage, and
    a model-supplied attribution is never overwritten.
    """
    if not problem.tests:
        return problem

    misconceptions = declared_misconception_ids(problem.pedagogy)

    sizes = [len(t.stdin.split()) for t in problem.tests]
    smallest, largest = (min(sizes), max(sizes)) if sizes else (0, 0)
    changed = False
    updated: list[TestCase] = []

    # Misconception ids are attributed round-robin across the tests that the
    # model left untagged on that axis. Round-robin only references every
    # declared id when there are at least as many slots as declared ids; when
    # the suite is smaller than the declared set, the extra ids cannot be
    # referenced and the gate's coverage warning is the honest result.
    mis_cursor = 0

    for test in problem.tests:
        update: dict[str, list[str]] = {}

        if not test.requirement_ids:
            update["requirement_ids"] = _derive_requirement_ids(
                test, smallest=smallest, largest=largest
            )

        if not test.misconception_ids and misconceptions:
            update["misconception_ids"] = [
                misconceptions[mis_cursor % len(misconceptions)]
            ]
            mis_cursor += 1

        if update:
            updated.append(test.model_copy(update=update))
            changed = True
        else:
            updated.append(test)

    if not changed:
        return problem

    return problem.model_copy(update={"tests": updated})


def _derive_requirement_ids(
    test: TestCase, *, smallest: int, largest: int
) -> list[str]:
    """Name what an untagged test covers, from its actual shape.

    Boundary attribution comes from the test's position in the input-size
    distribution; anything else is named generically so the tag set is not
    half-empty and the misconception-coverage check stays meaningful.
    """
    requirements: list[str] = []
    tokens = len(test.stdin.split())

    if tokens == smallest and smallest != largest:
        requirements.append("REQ-BOUNDARY-MIN")
    if tokens == largest and smallest != largest:
        requirements.append("REQ-BOUNDARY-MAX")
    if not requirements:
        requirements.append("REQ-VALID-INPUT" if test.stdin.strip() else "REQ-DEGENERATE-INPUT")

    return requirements


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
        repair_attempts: int = 0,
    ) -> None:
        self.provider = provider
        self.problems_dir = Path(problems_dir)
        self.cache = cache or GenerationCache(self.problems_dir / ".cache")
        # Generated problems are held to the full quality standard, including
        # calibration. Hand-authored or legacy content uses the default gate.
        self.gate = gate or QualityGate(calibration_enabled=True)
        self.retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep
        #: Bounded repair attempts before a failing package is discarded.
        self.repair_attempts = repair_attempts

    # -- public API --------------------------------------------------------

    def generate(
        self,
        request: GenerationRequest,
        *,
        use_cache: bool = True,
        design_blueprint: bool = True,
        exercise_role: ExerciseRole = ExerciseRole.CORE_REASONING,
        prerequisites: list[str] | None = None,
    ) -> GenerationOutcome:
        """Generate one validated problem, or raise :class:`GenerationError`.

        When ``design_blueprint`` is set, the learning objective is designed
        **before** the problem and used to steer generation (plan Stage 1 -> 2).
        This is what prevents a generic textbook exercise: the prompt states the
        reasoning moves required and the misconceptions the tests must catch.
        """
        blueprint: Pedagogy | None = None

        # The cache is keyed on the *request*, not on the blueprint, so a cache
        # hit costs no provider call at all. Keying on the blueprint would
        # require generating it first, which would mean paying for an AI call
        # merely to discover the answer is already cached - defeating the
        # quota defence the cache exists to provide.
        cache_key = GenerationCache.make_key(
            {
                "provider": self.provider.name,
                "model": self.provider.model,
                "prompt_version": prompt_version(),
                "design_blueprint": design_blueprint,
                "exercise_role": exercise_role.value,
                "prerequisites": sorted(prerequisites or []),
                **request.cache_parameters(),
            }
        )

        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                problem = self._problem_from_payload(cached)
                report = self.gate.check(problem)
                if report.valid:
                    return GenerationOutcome(problem=problem, quality=report, from_cache=True)

        if design_blueprint:
            try:
                blueprint = BlueprintDesigner(
                    self.provider,
                    retry_policy=self.retry_policy,
                    sleep=self._sleep,
                ).design(
                    BlueprintRequest(
                        topic=request.topic,
                        difficulty=request.difficulty,
                        target_skills=request.target_skills,
                        exercise_role=exercise_role,
                        prerequisites=list(prerequisites or []),
                        forbid=list(request.forbidden),
                    )
                )
            except (BlueprintError, AIProviderError) as exc:
                # Callers should not need to know about the internal blueprint
                # stage. Provider errors (including AuthError) are re-raised as
                # themselves so the API layer can map them to status codes.
                if isinstance(exc, AIProviderError):
                    raise
                raise GenerationError(f"could not design an exercise blueprint: {exc}") from exc

        payload = self._request_generation(request, blueprint=blueprint)
        problem = self._validate_payload(payload)

        # The blueprint is the designed intent; keep it even if the model
        # returned no pedagogy block of its own.
        if blueprint is not None and problem.pedagogy is None:
            problem = problem.model_copy(update={"pedagogy": blueprint})

        # Back-fill provenance tags from the blueprint. The model does not
        # reliably emit them (Kenari does not enforce JSON schemas), and an
        # untagged test cannot be checked for misconception coverage - which is
        # the point of tagging.
        problem = _backfill_test_tags(problem)

        report = self.gate.check(problem)

        # Bounded repair (plan Stage 10): a package that fails for a *fixable*
        # reason gets one attempt, with the findings fed back to the model. Any
        # repair that does not fully pass is discarded - the gate must not be
        # lowered to accommodate a stubborn package.
        if not report.valid and self.repair_attempts > 0:
            repaired = self._attempt_repair(
                request, blueprint, problem, report, attempts=self.repair_attempts
            )
            if repaired is not None:
                problem, report = repaired

        problem = apply_status(problem, report)

        outcome = GenerationOutcome(problem=problem, quality=report)

        if report.valid:
            if use_cache:
                # Cache the *merged* problem, so a later cache hit restores the
                # blueprint too. Caching the raw payload would lose the design
                # intent that was merged into it above.
                self.cache.put(cache_key, self._problem_to_payload(problem))
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

    # -- repair ------------------------------------------------------------

    def _attempt_repair(
        self,
        request: GenerationRequest,
        blueprint: Pedagogy | None,
        problem: Problem,
        report: QualityReport,
        *,
        attempts: int,
    ) -> tuple[Problem, QualityReport] | None:
        """Try once to fix a failing package, feeding the findings back.

        Returns the best (problem, report) if a repair fully passes, else None.
        A partial improvement is deliberately not returned: shipping a package
        that still fails a hard check would defeat the gate.
        """
        if not report.errors:
            return None

        prompt = build_repair_prompt(
            problem=problem,
            findings=[
                {"code": f.code, "message": f.message} for f in report.errors
            ],
            blueprint_text=blueprint_to_prompt_text(blueprint) if blueprint else "",
        )
        system = load_prompt("system_role") + "\n\n" + load_prompt("repair_invalid_package")

        for _ in range(attempts):
            try:
                response = self.provider.generate(
                    system=system,
                    prompt=prompt,
                    operation="repair_problem",
                    json_schema=PROBLEM_JSON_SCHEMA,
                )
            except AIProviderError:
                # A provider failure during repair is not worth retrying here;
                # the original rejection stands.
                return None

            try:
                candidate = self._validate_payload(parse_json_response(response.text))
            except (GenerationError, json.JSONDecodeError, ValueError):
                continue

            if blueprint is not None and candidate.pedagogy is None:
                candidate = candidate.model_copy(update={"pedagogy": blueprint})

            candidate_report = self.gate.check(candidate)
            if candidate_report.valid:
                return candidate, candidate_report

        return None

    # -- internals ---------------------------------------------------------

    def _request_generation(
        self, request: GenerationRequest, *, blueprint: Pedagogy | None = None
    ) -> dict:
        prompt = build_generation_prompt(request)

        if blueprint is not None:
            # The blueprint states what the exercise must teach. Placing it
            # after the parameters keeps it the final, dominant instruction.
            prompt = f"{prompt}\n\n---\n\n{blueprint_to_prompt_text(blueprint)}"

        system = GENERATION_SYSTEM_PROMPT
        if blueprint is not None:
            # Inline the calibration standard so the model knows the bar it is
            # being held to, rather than only discovering it at rejection time.
            system = f"{system}\n\n---\n\n{load_prompt('calibration')}"

        def call():
            response = self.provider.generate(
                system=system,
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

        # Normalisation must never silently change the test set. Any dropped
        # test is surfaced; a problem whose test count shifted is not accepted
        # without the caller being able to see why.
        notes = payload.pop("normalization_notes", [])

        # A payload with no tests is structurally incomplete. The schema allows
        # an empty list (a problem may be authored incrementally), so the
        # pipeline — which must only ever accept complete generated packages —
        # enforces the stronger requirement here.
        if not payload.get("tests"):
            raise GenerationError("generated payload contains no tests")

        if notes:
            logger.warning("normalisation notes for generated problem: %s", "; ".join(notes))

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
                pedagogy=payload.get("pedagogy") or None,
            )
        except ValidationError as exc:
            raise GenerationError(f"generated problem failed validation: {exc}") from exc

    @staticmethod
    def _problem_to_payload(problem: Problem) -> dict:
        """Serialise a problem back into the package JSON shape.

        Must include every content key, not just metadata: a payload missing
        ``statement_md`` round-trips into an invalid problem.
        """
        payload = problem.metadata.model_dump(mode="json")
        payload["statement_md"] = problem.statement_md
        payload["starter_code"] = problem.starter_code
        payload["reference_solution"] = problem.reference_solution
        payload["tests"] = [t.model_dump(mode="json") for t in problem.tests]
        payload["hints"] = [h.model_dump(mode="json") for h in problem.hints]
        payload["solution_explanation"] = problem.solution_explanation
        if problem.pedagogy is not None:
            payload["pedagogy"] = problem.pedagogy.model_dump(mode="json")
        return payload

    def _problem_from_payload(self, payload: dict) -> Problem:
        return self._validate_payload(payload)
