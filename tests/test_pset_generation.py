"""Problem-set generation tests (spec S7, plan Phase 3).

A problem set is generated, validated and persisted as a complete package
*before* it is presented: scenario, distribution code, tagged tests, reference,
and a checker built from the pset specification. These tests drive the whole
path with a mocked provider, so no live API call is ever made.

The gate is exercised directly too, to pin its concept-legality behaviour: a
legal pairing passes, an above-frontier reference is rejected, and a
``new_concept`` the learner already knows is rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ai.mock import MockProvider
from app.generation.pipeline import GenerationError, GenerationPipeline
from app.generation.prompts import GenerationRequest, build_generation_prompt
from app.generation.quality_gate import QualityGate
from app.schemas.problem import (
    ConceptPair,
    Problem,
    ProblemKind,
    ProblemMetadata,
)
from app.schemas.test_case import TestCase, Visibility
from app.storage.problem_repository import ProblemRepository

# --- a calibrated problem set ----------------------------------------------
#
# The "vote tally" pset is a real package under ``app/seed_problems/`` (plan
# task 2.5).
# Its payload is reconstructed here as the mocked provider response so the
# generator path is exercised against content already known to pass the gate
# (reference compiles+passes, starter compiles+does not pass, mutation
# survives). Building it from the package keeps the two in step.

_FIXTURE = Path(__file__).resolve().parent.parent / "app" / "seed_problems" / "pset-vote-tally"


def _fixture_problem() -> Problem:
    return ProblemRepository(_FIXTURE.parent).load("pset-vote-tally")


def pset_payload() -> dict:
    """A complete pset response in the wire shape a provider returns."""
    problem = _fixture_problem()
    return {
        "id": "c-sales-tally",
        "title": "Village Vote Tally",
        "difficulty": "beginner",
        "topics": ["arrays", "loops"],
        "target_skills": ["array_traversal"],
        "statement_md": problem.statement_md,
        "starter_code": problem.starter_code,
        "reference_solution": problem.reference_solution,
        "tests": [t.model_dump(mode="json") for t in problem.tests],
        "hints": [h.model_dump(mode="json") for h in problem.hints],
        "solution_explanation": problem.solution_explanation,
    }


def pset_response() -> str:
    return json.dumps(pset_payload())


BLUEPRINT_JSON = json.dumps(
    {
        "primary_objective": (
            "combine array indexing with a loop to count occurrences "
            "and derive a winning candidate"
        ),
        "secondary_objectives": ["track a running best"],
        "prerequisites": ["for_loops", "input_output"],
        "target_reasoning_moves": [
            "count each candidate's votes in an array",
            "derive the winner with a strict-majority boundary",
        ],
        "likely_misconceptions": [
            "MIS-NO-TALLY: never counts the ballots",
            "MIS-LAST-TIE: resolves a tie to the larger candidate",
        ],
        "exercise_role": "core_reasoning",
        "transfer_goal": "tally a stream of sensor readings into buckets.",
    }
)


def _pset_provider(problem_response: str) -> MockProvider:
    """Two-stage mock: a blueprint call, then the problem call."""
    return MockProvider(
        responder=lambda system, prompt, operation: (
            BLUEPRINT_JSON if operation == "build_blueprint" else problem_response
        )
    )


def _pset_request() -> GenerationRequest:
    return GenerationRequest(
        topic="voting",
        difficulty="beginner",
        kind=ProblemKind.PROBLEM_SET,
        new_concept="arrays",
        assumed_known=["for_loops", "input_output"],
    )


def _pipeline(tmp_path: Path, provider, *, known_concepts=None) -> GenerationPipeline:
    return GenerationPipeline(
        provider,
        problems_dir=tmp_path / "problems",
        known_concepts=known_concepts or ["for_loops", "input_output"],
    )


# --- gate: concept legality -------------------------------------------------
#
# A minimal pset whose reference and pair can be varied independently. The
# distribution/reference rules are disabled here so each test isolates the
# concept check (the full gate is exercised by the pipeline tests below).


LOOP_ONLY = """\
#include <stdio.h>
int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;
    for (int i = 0; i < n; i++) printf("%d ", i);
    return 0;
}
"""

ARRAYS_AND_LOOPS = """\
#include <stdio.h>
int main(void) {
    int a[3] = {1, 2, 3};
    int sum = 0;
    for (int i = 0; i < 3; i++) sum += a[i];
    printf("%d\\n", sum);
    return 0;
}
"""


def _concept_problem(reference: str, *, new_concept: str, assumed_known: list[str]) -> Problem:
    metadata = ProblemMetadata(
        id="concept-check",
        title="Concept Check",
        kind=ProblemKind.PROBLEM_SET,
        concept=ConceptPair(new_concept=new_concept, assumed_known=assumed_known),
    )
    return Problem(
        metadata=metadata,
        statement_md="# Task",
        reference_solution=reference,
        tests=[
            TestCase(id="a", name="A", stdin="3\n", expected_stdout="0 1 2 \n"),
            TestCase(id="b", name="B", stdin="1\n", expected_stdout="0 \n"),
            TestCase(id="c", name="C", visibility=Visibility.HIDDEN, stdin="2\n",
                     expected_stdout="0 1 \n"),
            TestCase(id="d", name="D", visibility=Visibility.HIDDEN, stdin="4\n",
                     expected_stdout="0 1 2 3 \n"),
        ],
    )


def _concept_only_gate(known_concepts: list[str]) -> QualityGate:
    # Distribution and mutation would add unrelated findings; a legal reference
    # for these tests may not even be shippable as a pset. Isolate the check.
    gate = QualityGate(mutation_enabled=False, known_concepts=known_concepts)
    return gate


def test_legal_concept_pair_passes_the_gate() -> None:
    problem = _concept_problem(
        LOOP_ONLY, new_concept="for_loops", assumed_known=["input_output"]
    )
    gate = _concept_only_gate(["input_output"])

    report = gate.check(problem)

    assert "concept-above-frontier" not in [f.code for f in report.errors]
    assert report.concepts is not None
    assert report.concepts["passed"] is True


def test_above_frontier_reference_is_rejected() -> None:
    # The reference needs arrays and loops, but only for_loops is declared new
    # and neither is in the checklist: arrays reaches past the frontier.
    problem = _concept_problem(
        ARRAYS_AND_LOOPS, new_concept="for_loops", assumed_known=["input_output"]
    )
    gate = _concept_only_gate(["input_output"])

    report = gate.check(problem)

    assert report.valid is False
    assert "concept-above-frontier" in [f.code for f in report.errors]
    assert report.concepts["passed"] is False


def test_new_concept_already_known_is_rejected() -> None:
    problem = _concept_problem(
        LOOP_ONLY, new_concept="for_loops", assumed_known=["input_output"]
    )
    # The learner already knows for_loops, so it cannot be the new concept.
    gate = _concept_only_gate(["input_output", "for_loops"])

    report = gate.check(problem)

    assert report.valid is False
    assert "new-concept-known" in [f.code for f in report.errors]


def test_empty_default_checklist_rejects_a_combined_pset() -> None:
    """The gate's default checklist is empty - documented behaviour (spec S3).

    With no known concepts, a pset may only use the single new concept. A
    reference that also needs a *known* concept has no checklist entry to
    authorise it, so it is rejected rather than assumed known.
    """
    problem = _concept_problem(
        ARRAYS_AND_LOOPS, new_concept="arrays", assumed_known=["for_loops"]
    )
    gate = _concept_only_gate([])

    report = gate.check(problem)

    assert report.valid is False
    assert "concept-above-frontier" in [f.code for f in report.errors]


def test_empty_default_checklist_accepts_a_single_concept_pset() -> None:
    """The one legal case with an empty checklist: required ⊆ {new_concept}."""
    problem = _concept_problem(
        LOOP_ONLY, new_concept="for_loops", assumed_known=["input_output"]
    )
    gate = _concept_only_gate([])

    report = gate.check(problem)

    assert report.concepts["passed"] is True
    assert "concept-above-frontier" not in [f.code for f in report.errors]


def test_exercise_is_untouched_by_the_concept_check() -> None:
    metadata = ProblemMetadata(
        id="plain", title="Plain", kind=ProblemKind.EXERCISE,
        concept=ConceptPair(new_concept="arrays", assumed_known=["for_loops"]),
    )
    problem = Problem(
        metadata=metadata,
        statement_md="# Task",
        reference_solution=ARRAYS_AND_LOOPS,
        tests=[
            TestCase(id="a", name="A", stdin="1 2\n", expected_stdout="3\n"),
            TestCase(id="b", name="B", stdin="3 4\n", expected_stdout="7\n"),
            TestCase(id="c", name="C", visibility=Visibility.HIDDEN, stdin="0 0\n",
                     expected_stdout="0\n"),
            TestCase(id="d", name="D", visibility=Visibility.HIDDEN, stdin="5 6\n",
                     expected_stdout="11\n"),
        ],
    )

    report = _concept_only_gate([]).check(problem)

    assert report.concepts is None
    assert "concept-above-frontier" not in [f.code for f in report.findings]


# --- gate: distribution (pipeline-level coverage) ---------------------------


def test_pipeline_rejects_a_pset_whose_starter_already_passes(tmp_path: Path) -> None:
    """A distribution starter that solves the pset is rejected by the gate."""
    payload = pset_payload()
    # Ship the reference as the starter: it compiles and passes every test.
    payload["starter_code"] = payload["reference_solution"]
    provider = _pset_provider(json.dumps(payload))

    outcome = _pipeline(tmp_path, provider).generate(_pset_request())

    assert outcome.accepted is False
    codes = [f.code for f in outcome.quality.errors]
    assert "starter-passes-all-tests" in codes
    # Rejected packages are not written.
    assert not (tmp_path / "problems" / "c-sales-tally").exists()


# --- pipeline: end-to-end pset generation -----------------------------------


def test_pset_request_yields_a_validated_problem(tmp_path: Path) -> None:
    provider = _pset_provider(pset_response())

    outcome = _pipeline(tmp_path, provider).generate(_pset_request())

    assert outcome.accepted is True
    problem = outcome.problem
    assert problem.metadata.kind is ProblemKind.PROBLEM_SET
    assert problem.metadata.concept == ConceptPair(
        new_concept="arrays", assumed_known=["for_loops", "input_output"]
    )
    assert problem.metadata.distribution.has_starter is True
    assert problem.metadata.distribution.todo_count >= 1
    assert problem.metadata.checker is not None


def test_pset_checker_prefix_is_exists_then_compiles(tmp_path: Path) -> None:
    provider = _pset_provider(pset_response())

    outcome = _pipeline(tmp_path, provider).generate(_pset_request())

    checks = outcome.problem.metadata.checker.checks
    assert [c.id for c in checks[:2]] == ["exists", "compiles"]
    # One behavioural check per test, in declaration order.
    behavioural = [c for c in checks if c.test_id is not None]
    assert [c.test_id for c in behavioural] == [t.id for t in outcome.problem.tests]


def test_pset_enables_the_prediction_mechanic(tmp_path: Path) -> None:
    provider = _pset_provider(pset_response())

    outcome = _pipeline(tmp_path, provider).generate(_pset_request())

    prediction = outcome.problem.metadata.prediction
    assert prediction.enabled is True
    assert prediction.sample_test_id in [t.id for t in outcome.problem.public_tests]


def test_pset_todo_count_matches_the_starter(tmp_path: Path) -> None:
    from app.services.distribution import count_todos

    provider = _pset_provider(pset_response())

    outcome = _pipeline(tmp_path, provider).generate(_pset_request())

    starter = outcome.problem.starter_code
    assert outcome.problem.metadata.distribution.todo_count == count_todos(starter)


def test_pset_without_a_concept_is_rejected_before_generation(tmp_path: Path) -> None:
    provider = _pset_provider(pset_response())
    request = GenerationRequest(
        kind=ProblemKind.PROBLEM_SET, new_concept="", assumed_known=["for_loops"]
    )

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(request)


# --- persistence / round-trip -----------------------------------------------


def test_saved_pset_round_trips_including_checker_and_concept(tmp_path: Path) -> None:
    provider = _pset_provider(pset_response())
    pipeline = _pipeline(tmp_path, provider)
    outcome = pipeline.generate(_pset_request())

    reloaded = ProblemRepository(tmp_path / "problems").load("c-sales-tally")

    assert reloaded.metadata.kind is ProblemKind.PROBLEM_SET
    assert reloaded.metadata.concept == outcome.problem.metadata.concept
    assert reloaded.metadata.distribution == outcome.problem.metadata.distribution
    assert reloaded.metadata.checker == outcome.problem.metadata.checker
    assert reloaded.metadata.prediction == outcome.problem.metadata.prediction


def test_save_writes_starter_and_records_distribution(tmp_path: Path) -> None:
    provider = _pset_provider(pset_response())
    pipeline = _pipeline(tmp_path, provider)
    outcome = pipeline.generate(_pset_request())

    package = tmp_path / "problems" / "c-sales-tally"
    raw = json.loads((package / "problem.json").read_text(encoding="utf-8"))

    assert (package / "starter" / "main.c").is_file()
    assert raw["kind"] == "problem_set"
    assert raw["distribution"]["has_starter"] is True
    assert raw["distribution"]["todo_count"] == outcome.problem.metadata.distribution.todo_count
    assert raw["concept"]["new_concept"] == "arrays"


def test_checker_is_persisted_and_reused_on_reload(tmp_path: Path) -> None:
    """A reloaded pset presents the stored checker, not a rebuilt one."""
    provider = _pset_provider(pset_response())
    pipeline = _pipeline(tmp_path, provider)
    pipeline.generate(_pset_request())

    reloaded = ProblemRepository(tmp_path / "problems").load("c-sales-tally")

    assert reloaded.metadata.checker is not None
    assert reloaded.metadata.checker.checks[0].id == "exists"
    assert reloaded.metadata.checker.checks[1].id == "compiles"


def test_cached_pset_restores_its_checker(tmp_path: Path) -> None:
    provider = _pset_provider(pset_response())
    pipeline = _pipeline(tmp_path, provider)

    first = pipeline.generate(_pset_request())
    second = pipeline.generate(_pset_request())

    assert second.from_cache is True
    assert second.problem.metadata.checker == first.problem.metadata.checker
    assert second.problem.metadata.concept == first.problem.metadata.concept


# --- legacy / exercise regression guard -------------------------------------


def test_exercise_generation_is_unchanged(tmp_path: Path) -> None:
    """A plain exercise stays ``kind: exercise`` with no pset artefacts."""
    from tests.test_generation_pipeline import BLUEPRINT_JSON as EX_BP
    from tests.test_generation_pipeline import good_payload

    provider = MockProvider(
        responder=lambda system, prompt, operation: (
            EX_BP if operation == "build_blueprint" else json.dumps(good_payload())
        )
    )
    outcome = _pipeline(tmp_path, provider).generate(GenerationRequest())

    assert outcome.accepted is True
    assert outcome.problem.metadata.kind is ProblemKind.EXERCISE
    assert outcome.problem.metadata.concept is None
    assert outcome.problem.metadata.checker is None
    assert outcome.problem.metadata.distribution.has_starter is False
    assert outcome.problem.metadata.prediction.enabled is False


# --- prompts ----------------------------------------------------------------


def test_pset_prompt_demands_the_pset_shape() -> None:
    prompt = build_generation_prompt(_pset_request())

    assert "problem set" in prompt.lower()
    assert "arrays" in prompt  # the new concept
    assert "for_loops" in prompt  # a known concept to combine
    assert "scenario" in prompt.lower()
    assert "TODO" in prompt
    assert "distribution code" in prompt.lower()


def test_exercise_prompt_is_not_a_pset_prompt() -> None:
    prompt = build_generation_prompt(GenerationRequest(topic="arithmetic"))

    assert "problem set" not in prompt.lower()
