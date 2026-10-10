"""Opt-in live provider smoke test.

This module is **skipped by default**: the platform's test suite must never
depend on a live API call. It runs only when ``CPRACTICE_LIVE_AI=1`` is set
and a key is present.

Use it to verify real provider connectivity and a real generation round-trip:

    CPRACTICE_LIVE_AI=1 python -m pytest tests/test_live_gemini.py -v
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.ai.google import GoogleProvider
from app.config import get_settings
from app.generation.pipeline import GenerationError, GenerationPipeline
from app.generation.prompts import GenerationRequest

LIVE = os.environ.get("CPRACTICE_LIVE_AI") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="live AI test disabled; set CPRACTICE_LIVE_AI=1 to enable",
)


@pytest.fixture()
def provider() -> GoogleProvider:
    settings = get_settings()
    if not settings.google_api_key:
        pytest.skip("GOOGLE_API_KEY is not configured")
    return GoogleProvider(settings.google_api_key, model=settings.ai_model)


def test_connectivity(provider: GoogleProvider) -> None:
    """The provider is reachable and the credentials are accepted."""
    assert provider.check_connectivity() is True


def test_real_generation_roundtrip(provider: GoogleProvider, tmp_path: Path) -> None:
    """A real generation request produces a problem that passes the gate."""
    pipeline = GenerationPipeline(provider, problems_dir=tmp_path / "problems")

    try:
        outcome = pipeline.generate(
            GenerationRequest(topic="loops", difficulty="beginner", target_skills=["iteration"]),
            use_cache=False,
        )
    except GenerationError as exc:
        pytest.fail(f"generation failed: {exc}")

    print("\n--- generated problem ---")
    print("id:      ", outcome.problem.id)
    print("title:   ", outcome.problem.title)
    print("status:  ", outcome.problem.metadata.status.value)
    print(
        "reference:",
        f"{outcome.quality.reference_passed}/{outcome.quality.reference_total}",
        f"compiled={outcome.quality.reference_compiled}",
    )
    print("errors:  ", [f.code for f in outcome.quality.errors])
    print("warnings:", [f.code for f in outcome.quality.warnings])
    print("statement preview:", outcome.problem.statement_md[:200].replace("\n", " "))

    # The generator must at minimum return a parseable, self-consistent problem.
    assert outcome.problem.tests, "generated problem has no tests"
    assert outcome.quality.reference_compiled, "reference did not compile"


def test_quality_gate_rejects_a_broken_reference(provider: GoogleProvider, tmp_path: Path) -> None:
    """A deliberately broken reference must be rejected by the gate.

    Exercises the provider path while proving the gate, not the AI, decides
    validity.
    """
    from app.generation.quality_gate import QualityGate
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase

    problem = Problem(
        metadata=ProblemMetadata(id="broken", title="Broken"),
        statement_md="# Broken",
        reference_solution='int main(void){ printf("oops" return 0; }',
        tests=[
            TestCase(id="a", name="A", stdin="", expected_stdout=""),
            TestCase(id="b", name="B", stdin="", expected_stdout=""),
            TestCase(id="c", name="C", stdin="", expected_stdout=""),
            TestCase(id="d", name="D", stdin="", expected_stdout=""),
        ],
    )

    report = QualityGate().check(problem)

    assert report.valid is False
    assert "reference-does-not-compile" in [f.code for f in report.errors]
