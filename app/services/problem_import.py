"""Import a problem package from a structured payload.

An *import* brings a problem authored outside this instance — by a web agent,
another CPractice instance, or a human — into an existing CPractice database.
The contract is identical to the one :mod:`app.generation.pipeline` produces:
one JSON document shaped like ``problem.json`` (metadata at the top level plus
the content keys recognised by :data:`app.schemas.problem.CONTENT_KEYS`), plus
the package files.

All quality gates apply unchanged:

* the same Pydantic schemas (invalid payloads fail validation, never silently
  accepted — the same rule as :mod:`app.storage.problem_repository`),
* the same deterministic quality gate (the *default* gate: no calibration,
  mutation testing on, concept legality for problem sets checked against the
  learner's own checklist), and
* the same package layout on disk as :meth:`GenerationPipeline.save`.

The quality gate decides pass/fail — an importing caller (AI or human) never
does.

Deliberately mirrors ``GenerationPipeline.save`` / ``_problem_to_payload``
until they are refactored behind a shared package-writer module (the
generation pipeline currently has uncommitted work; the two writers should
converge through that refactor, not by patching around it).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.generation.quality_gate import QualityGate, QualityReport, apply_status
from app.schemas.problem import CONTENT_KEYS, Problem

QUALITY_REPORT_FILENAME = "quality_report.json"
METADATA_FILENAME = "problem.json"
STATEMENT_FILENAME = "statement.md"
STARTER_DIR = "starter"
REFERENCE_DIR = "reference"
HINT_DIR = "hint"


class PackageValidationError(ValueError):
    """The payload does not satisfy the problem package contract."""


@dataclass
class PackageRejected(ValueError):
    """The quality gate rejected the package; nothing was written."""

    report: QualityReport

    def __str__(self) -> str:  # pragma: no cover - diagnostics only
        errors = "; ".join(f"{f.code}: {f.message}" for f in self.report.errors)
        return f"package rejected by quality gate: {errors}"


def problem_from_payload(payload: dict) -> Problem:
    """Build a validated :class:`Problem` from an import payload.

    Mirrors the parsing in :meth:`app.storage.problem_repository.ProblemRepository.load`
    so the two stay in step.
    """
    if not isinstance(payload, dict):
        raise PackageValidationError("package payload must be a JSON object")

    metadata_raw = {key: value for key, value in payload.items() if key not in CONTENT_KEYS}

    try:
        from app.schemas.test_case import TestCase

        tests = [TestCase.model_validate(item) for item in payload.get("tests", [])]
        problem = Problem(
            metadata=metadata_raw,  # type: ignore[arg-type]
            statement_md=payload.get("statement_md") or "",
            starter_code=payload.get("starter_code", ""),
            reference_solution=payload.get("reference_solution", ""),
            tests=tests,
            hints=payload.get("hints", []),
            solution_explanation=payload.get("solution_explanation", ""),
            pedagogy=payload.get("pedagogy") or None,
        )
    except ValidationError as exc:
        raise PackageValidationError(f"package failed validation: {exc}") from exc

    return problem


def problem_to_payload(problem: Problem) -> dict:
    """Serialise a validated problem back into the package JSON shape.

    Must round-trip: the written ``problem.json`` must reload through
    :class:`app.storage.problem_repository.ProblemRepository`. Mirrors
    ``GenerationPipeline._problem_to_payload``.
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


def run_quality_gate(problem: Problem, known_concepts: list[str] | None = None) -> QualityReport:
    """Run the default quality gate (the standard for hand-authored content).

    Concept legality for problem sets is checked against the learner's own
    known-concepts checklist, exactly as the generation pipeline does.
    """
    gate = QualityGate(calibration_enabled=False)
    if known_concepts:
        gate = gate.with_checklist(known_concepts)
    return gate.check(problem)


def validate_and_tag(problem: Problem, report: QualityReport) -> Problem:
    """Return the problem with its status set from the gate's verdict.

    Mirrors :func:`app.generation.quality_gate.apply_status`; kept as a tiny
    local seam so the importer never writes a package without a recorded
    status.
    """
    return apply_status(problem, report)


def write_package(problems_dir: Path, problem: Problem, report: QualityReport) -> Path:
    """Write the package directory (same layout as GenerationPipeline.save) and
    return it. The caller is expected to have already passed the gate; a
    rejected package must never reach this function."""

    package_dir = problems_dir / problem.id
    (package_dir / STARTER_DIR).mkdir(parents=True, exist_ok=True)
    (package_dir / REFERENCE_DIR).mkdir(parents=True, exist_ok=True)

    entrypoint = problem.metadata.entrypoint
    (package_dir / STATEMENT_FILENAME).write_text(problem.statement_md, encoding="utf-8")
    (package_dir / STARTER_DIR / entrypoint).write_text(problem.starter_code, encoding="utf-8")
    (package_dir / REFERENCE_DIR / entrypoint).write_text(
        problem.reference_solution, encoding="utf-8"
    )

    hint_code = problem.metadata.distribution.hint_code
    if hint_code.strip():
        (package_dir / HINT_DIR).mkdir(parents=True, exist_ok=True)
        (package_dir / HINT_DIR / entrypoint).write_text(hint_code, encoding="utf-8")

    if not report.valid:
        raise PackageRejected(report)

    (package_dir / METADATA_FILENAME).write_text(
        json.dumps(problem_to_payload(problem), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (package_dir / QUALITY_REPORT_FILENAME).write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return package_dir
