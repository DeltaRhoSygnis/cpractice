"""Tests for the generation pipeline, cache, and prompt construction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ai.base import AuthError, MalformedResponseError, ProviderUnavailableError
from app.ai.cache import GenerationCache
from app.ai.mock import MockProvider, failing_provider
from app.generation.pipeline import GenerationError, GenerationPipeline
from app.generation.prompts import (
    GenerationRequest,
    build_generation_prompt,
    build_hint_prompt,
    parse_json_response,
)

# --- a calibrated reference problem ---------------------------------------
#
# The shared fixture must meet the calibration standard, because the pipeline
# now enforces it: a simple "add two numbers" exercise is rejected as a single
# reasoning move whose tests vary only by value.
#
# Task: read a count n, then n scores. Print the running maximum and each
# score's distance below it.
#
# Reasoning moves: (1) consume a count followed by that many values, and
# (2) update running state before using it. Output exposes intermediate
# correctness, so a wrong update is visible.

REFERENCE = """#include <stdio.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    int running_max = 0;
    int first = 1;

    for (int i = 0; i < n; i++) {
        int score;
        if (scanf("%d", &score) != 1) return 1;

        if (first || score > running_max) {
            running_max = score;
            first = 0;
        }

        printf("%d %d\\n", running_max, running_max - score);
    }

    return 0;
}
"""


def good_payload(**overrides) -> dict:
    payload = {
        "id": "c-running-max-gap",
        "title": "Running Maximum and Gap",
        "difficulty": "beginner",
        "topics": ["loops", "state"],
        "target_skills": ["maintaining running state", "deriving loop bounds"],
        "statement_md": (
            "# Running Maximum and Gap\n\n"
            "Read a count `n`, then `n` scores. For each score in order, print the "
            "highest score seen so far, followed by how far below that maximum this "
            "score is.\n"
        ),
        "starter_code": "#include <stdio.h>\n\nint main(void) {\n    return 0;\n}\n",
        "reference_solution": REFERENCE,
        "tests": [
            {"id": "basic", "name": "Basic ascent", "visibility": "public",
             "stdin": "3\n5 10 7\n", "expected_stdout": "5 0\n10 0\n10 3\n",
             "requirement_ids": ["REQ-RUNNING-STATE"]},
            {"id": "descending", "name": "Strictly decreasing", "visibility": "public",
             "stdin": "3\n9 4 1\n", "expected_stdout": "9 0\n9 5\n9 8\n",
             "requirement_ids": ["REQ-RUNNING-STATE"]},
            {"id": "single", "name": "Minimum input: one score", "visibility": "hidden",
             "stdin": "1\n42\n", "expected_stdout": "42 0\n",
             "requirement_ids": ["REQ-BOUNDARY-MIN"],
             "misconception_ids": ["MIS-INIT-ZERO"]},
            {"id": "zeros", "name": "All zeros", "visibility": "hidden",
             "stdin": "3\n0 0 0\n", "expected_stdout": "0 0\n0 0\n0 0\n",
             "requirement_ids": ["REQ-BOUNDARY-MIN"]},
            {"id": "late-max", "name": "Maximum appears last", "visibility": "hidden",
             "stdin": "4\n1 2 3 100\n",
             "expected_stdout": "1 0\n2 0\n3 0\n100 0\n",
             "requirement_ids": ["REQ-BOUNDARY-MAX"],
             "misconception_ids": ["MIS-LATE-UPDATE"]},
            {"id": "max-input", "name": "Large values at maximum count", "visibility": "hidden",
             "stdin": "2\n1000000 1000000\n", "expected_stdout": "1000000 0\n1000000 0\n",
             "requirement_ids": ["REQ-BOUNDARY-MAX"]},
        ],
        "hints": [
            {"level": 1, "text": "This is about state that persists between iterations."},
            {"level": 2, "text": "What must remain true after each score is read?"},
            {"level": 3, "text": "Track the best score so far. When should it change?"},
            {"level": 4, "text": "Read n, loop n times, keep a running maximum, update before printing."},
            {"level": 5, "text": "See the reference approach."},
        ],
        "solution_explanation": (
            "The invariant is that running_max holds the largest score read so far. "
            "Updating it before printing means each line includes the current score."
        ),
        "pedagogy": {
            "primary_objective": "maintain correct running state across iterations",
            "secondary_objectives": ["derive a count-driven loop bound"],
            "prerequisites": ["for_loops", "if_else"],
            "target_reasoning_moves": [
                "consume a count followed by that many values",
                "update running state before using it",
            ],
            "likely_misconceptions": [
                "MIS-INIT-ZERO: initialising the maximum to 0 breaks for n=1 below zero",
                "MIS-LATE-UPDATE: printing before updating lags by one iteration",
            ],
            "exercise_role": "core_reasoning",
            "difficulty_profile": {"reasoning_steps": 2, "state_management": 2},
            "transfer_goal": "Track a running minimum in a different scan.",
        },
    }
    payload.update(overrides)
    return payload


def _pipeline(tmp_path: Path, provider) -> GenerationPipeline:
    return GenerationPipeline(provider, problems_dir=tmp_path / "problems")


# --- helpers for two-stage generation -------------------------------------
#
# Generation now makes two provider calls: first a blueprint, then the problem
# (plan Stage 1 -> 2). Tests that exercise the problem stage must therefore
# supply a blueprint response as well.

BLUEPRINT_JSON = json.dumps({
    "primary_objective": "maintain running state across iterations",
    "target_reasoning_moves": [
        "consume a count followed by that many values",
        "update running state before using it",
    ],
    "likely_misconceptions": ["MIS-LATE-UPDATE: printing before updating"],
    "exercise_role": "core_reasoning",
    "prerequisites": ["for_loops"],
})


def _two_stage(problem_response: str) -> MockProvider:
    """A mock that answers the blueprint call, then the problem call."""
    return MockProvider(
        responder=lambda system, prompt, operation: (
            BLUEPRINT_JSON if operation == "build_blueprint" else problem_response
        )
    )


def _problem_calls(provider: MockProvider) -> int:
    """Count problem-generation calls, ignoring blueprint calls.

    Generation makes one call per stage, so a cache assertion must look at the
    stage it is about.
    """
    return sum(1 for call in provider.calls if call["operation"] != "build_blueprint")


# --- happy path ------------------------------------------------------------


def test_generates_and_validates_a_problem(tmp_path: Path) -> None:
    provider = _two_stage(json.dumps(good_payload()))

    outcome = _pipeline(tmp_path, provider).generate(GenerationRequest())

    assert outcome.accepted is True
    assert outcome.problem.id == "c-running-max-gap"
    assert outcome.problem.metadata.status.value == "validated"
    assert outcome.quality.reference_passed == 6


def test_saves_package_and_quality_report(tmp_path: Path) -> None:
    provider = _two_stage(json.dumps(good_payload()))

    _pipeline(tmp_path, provider).generate(GenerationRequest())

    package = tmp_path / "problems" / "c-running-max-gap"
    assert (package / "problem.json").is_file()
    assert (package / "statement.md").is_file()
    assert (package / "starter" / "main.c").is_file()
    assert (package / "reference" / "main.c").is_file()
    assert (package / "quality_report.json").is_file()


def test_saved_package_reloads_through_the_repository(tmp_path: Path) -> None:
    from app.storage.problem_repository import ProblemRepository

    provider = _two_stage(json.dumps(good_payload()))
    _pipeline(tmp_path, provider).generate(GenerationRequest())

    reloaded = ProblemRepository(tmp_path / "problems").load("c-running-max-gap")

    assert reloaded.title == "Running Maximum and Gap"
    assert len(reloaded.tests) == 6
    assert reloaded.reference_solution.strip() == REFERENCE.strip()


# --- caching ---------------------------------------------------------------


def test_second_identical_request_uses_cache(tmp_path: Path) -> None:
    provider = _two_stage(json.dumps(good_payload()))
    pipeline = _pipeline(tmp_path, provider)

    first = pipeline.generate(GenerationRequest(topic="arithmetic"))
    second = pipeline.generate(GenerationRequest(topic="arithmetic"))

    assert first.from_cache is False
    assert second.from_cache is True
    assert _problem_calls(provider) == 1


def test_different_parameters_do_not_share_cache(tmp_path: Path) -> None:
    provider = _two_stage(json.dumps(good_payload()))
    pipeline = _pipeline(tmp_path, provider)

    pipeline.generate(GenerationRequest(topic="loops"))
    pipeline.generate(GenerationRequest(topic="arrays"))

    assert _problem_calls(provider) == 2


def test_cache_can_be_bypassed(tmp_path: Path) -> None:
    provider = _two_stage(json.dumps(good_payload()))
    pipeline = _pipeline(tmp_path, provider)

    pipeline.generate(GenerationRequest())
    pipeline.generate(GenerationRequest(), use_cache=False)

    assert _problem_calls(provider) == 2


def test_invalid_problem_is_not_cached(tmp_path: Path) -> None:
    bad = good_payload(reference_solution="int main(void){ printf(\"x\" return 0; }")
    provider = _two_stage(json.dumps(bad))
    pipeline = _pipeline(tmp_path, provider)

    first = pipeline.generate(GenerationRequest())
    second = pipeline.generate(GenerationRequest())

    assert first.accepted is False
    # Not cached, so the provider is consulted again.
    assert second.from_cache is False
    assert _problem_calls(provider) == 2


# --- provider failure handling ---------------------------------------------


def test_auth_error_is_preserved_through_the_blueprint_stage(tmp_path: Path) -> None:
    """AuthError must keep its type so the API can map it to 502.

    Wrapping it as a generic generation failure would lose the distinction
    between "your key is wrong" and "the model produced junk".
    """
    provider = failing_provider(AuthError("bad key"), times=5)

    with pytest.raises(AuthError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())

    # One attempt only: an AuthError is permanent and must never be retried.
    assert len(provider.calls) == 1


def test_transient_error_is_retried_then_succeeds(tmp_path: Path) -> None:
    """A transient failure during the blueprint stage is recovered from."""
    provider = MockProvider(
        responder=lambda system, prompt, operation: (
            BLUEPRINT_JSON if operation == "build_blueprint" else json.dumps(good_payload())
        ),
        errors=[ProviderUnavailableError("blip")],
    )
    pipeline = GenerationPipeline(
        provider,
        problems_dir=tmp_path / "problems",
        sleep=lambda _: None,
    )

    outcome = pipeline.generate(GenerationRequest())

    assert outcome.accepted is True
    # One failed blueprint attempt, one successful blueprint, one problem call.
    assert len(provider.calls) == 3


def test_malformed_json_raises_generation_error(tmp_path: Path) -> None:
    provider = _two_stage("this is not json at all")

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())


def test_json_that_is_not_an_object_raises(tmp_path: Path) -> None:
    provider = _two_stage("[1, 2, 3]")

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())


def test_missing_required_metadata_raises(tmp_path: Path) -> None:
    payload = good_payload()
    del payload["title"]
    provider = _two_stage(json.dumps(payload))

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())


def test_invalid_test_id_is_normalised_not_rejected(tmp_path: Path) -> None:
    """A cosmetic id problem is repaired rather than discarding the problem."""
    payload = good_payload(
        tests=[{"id": "Bad ID", "name": "X", "visibility": "public", "stdin": "", "expected_stdout": ""}]
    )
    provider = _two_stage(json.dumps(payload))

    outcome = _pipeline(tmp_path, provider).generate(GenerationRequest())

    assert outcome.problem.tests[0].id == "bad-id"


def test_payload_missing_tests_entirely_is_rejected(tmp_path: Path) -> None:
    """Normalisation must not invent test data."""
    payload = good_payload()
    del payload["tests"]
    provider = _two_stage(json.dumps(payload))

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())


def test_report_in_progress_is_rejected(tmp_path: Path) -> None:
    """A required field with the wrong type is still a validation failure."""
    payload = good_payload(difficulty=["beginner", "advanced"])
    provider = _two_stage(json.dumps(payload))

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())


# --- prompts ---------------------------------------------------------------


def test_generation_prompt_includes_parameters() -> None:
    prompt = build_generation_prompt(
        GenerationRequest(topic="recursion", difficulty="advanced", target_skills=["base cases"])
    )

    assert "recursion" in prompt
    assert "advanced" in prompt
    assert "base cases" in prompt


def test_generation_prompt_lists_forbidden_constructs() -> None:
    prompt = build_generation_prompt(GenerationRequest(forbidden=["goto", "global variables"]))

    assert "goto" in prompt
    assert "global variables" in prompt


def test_hint_prompt_varies_by_level() -> None:
    low = build_hint_prompt(statement="S", level=1)
    high = build_hint_prompt(statement="S", level=4)

    assert "level 1 hint" in low
    assert "level 4 hint" in high
    assert low != high


def test_hint_prompt_includes_learner_code_when_present() -> None:
    prompt = build_hint_prompt(statement="S", level=3, learner_code="int main(){}")

    assert "int main(){}" in prompt


def test_hint_prompt_forbids_final_code_at_level_five() -> None:
    prompt = build_hint_prompt(statement="S", level=5)

    assert "Do NOT paste a complete C solution" in prompt


# --- JSON parsing ----------------------------------------------------------


def test_parse_plain_json() -> None:
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parse_json_wrapped_in_markdown_fence() -> None:
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_surrounding_prose() -> None:
    assert parse_json_response('Here you go: {"a": 1} Enjoy!') == {"a": 1}


def test_parse_json_raises_on_garbage() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_json_response("not json")


# --- cache unit tests ------------------------------------------------------


def test_cache_roundtrip(tmp_path: Path) -> None:
    cache = GenerationCache(tmp_path)

    assert cache.get("k") is None
    cache.put("k", {"x": 1})
    assert cache.has("k") is True
    assert cache.get("k") == {"x": 1}


def test_cache_key_is_stable_and_order_independent() -> None:
    a = GenerationCache.make_key({"x": 1, "y": 2})
    b = GenerationCache.make_key({"y": 2, "x": 1})

    assert a == b


def test_cache_key_differs_for_different_values() -> None:
    assert GenerationCache.make_key({"x": 1}) != GenerationCache.make_key({"x": 2})


def test_corrupt_cache_entry_is_a_miss(tmp_path: Path) -> None:
    cache = GenerationCache(tmp_path)
    cache.path_for("bad").write_text("{not valid json")

    assert cache.get("bad") is None


def test_cache_clear(tmp_path: Path) -> None:
    cache = GenerationCache(tmp_path)
    cache.put("a", {})
    cache.put("b", {})

    assert cache.clear() == 2
    assert cache.get("a") is None


# --- provenance tag back-filling -------------------------------------------
#
# Kenari does not enforce JSON schemas, so models frequently omit the
# requirement/misconception tags. Without them the gate's misconception-coverage
# check is vacuous, so the pipeline derives a minimal attribution.


def test_backfill_tags_untagged_tests() -> None:
    from app.generation.pipeline import _backfill_test_tags
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase, Visibility

    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        tests=[
            TestCase(id="a", name="A", stdin="3\n1 2 3\n", expected_stdout="x\n"),
            TestCase(id="b", name="B", visibility=Visibility.HIDDEN,
                     stdin="5\n", expected_stdout="y\n"),
        ],
    )

    result = _backfill_test_tags(problem)

    assert all(t.is_tagged for t in result.tests)


def test_backfill_does_not_overwrite_model_tags() -> None:
    from app.generation.pipeline import _backfill_test_tags
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase

    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        tests=[TestCase(id="a", name="A", stdin="1\n", expected_stdout="x\n",
                        requirement_ids=["REQ-SPECIFIC"])],
    )

    result = _backfill_test_tags(problem)

    assert result.tests[0].requirement_ids == ["REQ-SPECIFIC"]


def test_backfill_marks_min_and_max_inputs_as_boundaries() -> None:
    from app.generation.pipeline import _backfill_test_tags
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase

    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        tests=[
            TestCase(id="small", name="Small", stdin="1\n", expected_stdout="a\n"),
            TestCase(id="big", name="Big", stdin="7\n1 2 3 4 5 6 7\n", expected_stdout="b\n"),
        ],
    )

    result = _backfill_test_tags(problem)
    by_id = {t.id: t for t in result.tests}

    assert "REQ-BOUNDARY-MIN" in by_id["small"].requirement_ids
    assert "REQ-BOUNDARY-MAX" in by_id["big"].requirement_ids


def test_backfill_is_a_no_op_when_all_tests_are_tagged() -> None:
    from app.generation.pipeline import _backfill_test_tags
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase

    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        tests=[TestCase(id="a", name="A", stdin="1\n", expected_stdout="x\n",
                        requirement_ids=["REQ-X"],
                        misconception_ids=["MIS-X"])],
    )

    assert _backfill_test_tags(problem) is problem


def test_pipeline_backfills_tags_on_generated_problem(tmp_path: Path) -> None:
    """The end-to-end path must produce tagged tests even from an untagged model."""
    payload = good_payload()
    # Simulate a model that omitted every tag, as Kenari often does.
    for test in payload["tests"]:
        test.pop("requirement_ids", None)
        test.pop("misconception_ids", None)

    pipeline = _pipeline(tmp_path, _two_stage(json.dumps(payload)))
    outcome = pipeline.generate(GenerationRequest())

    assert outcome.accepted is True
    assert all(t.is_tagged for t in outcome.problem.tests)


# --- misconception linkage -------------------------------------------------


def test_misconception_id_reuses_declared_prefix() -> None:
    from app.generation.misconceptions import misconception_id

    assert misconception_id("MIS-OFF-BY-ONE: one extra iteration") == "MIS-OFF-BY-ONE"


def test_misconception_id_is_derived_from_prose() -> None:
    from app.generation.misconceptions import misconception_id

    derived = misconception_id("using a separately computed string length")
    assert derived.startswith("MIS-")
    assert derived == misconception_id("using a separately computed string length")


def test_misconception_id_is_length_clamped() -> None:
    from app.generation.misconceptions import misconception_id

    long_id = "MIS-" + "A" * 180 + ": detail"
    assert len(misconception_id(long_id)) <= 48


def test_declared_misconception_ids_are_deduplicated() -> None:
    from app.generation.misconceptions import declared_misconception_ids
    from app.schemas.pedagogy import Pedagogy

    pedagogy = Pedagogy(
        likely_misconceptions=[
            "MIS-OFF-BY-ONE: extra iteration",
            "MIS-OFF-BY-ONE: same id again",
        ]
    )

    assert declared_misconception_ids(pedagogy) == ["MIS-OFF-BY-ONE"]


def test_backfill_attributes_declared_misconceptions() -> None:
    """An untagged suite must not make the coverage check unsatisfiable."""
    from app.generation.misconceptions import declared_misconception_ids
    from app.generation.pipeline import _backfill_test_tags
    from app.schemas.pedagogy import Pedagogy
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase

    pedagogy = Pedagogy(
        likely_misconceptions=[
            "MIS-OFF-BY-ONE: extra iteration",
            "MIS-INIT-ZERO: wrong starting value",
        ]
    )
    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        pedagogy=pedagogy,
        tests=[
            TestCase(id=f"t{i}", name=f"T{i}", stdin=f"{i}\n", expected_stdout="x\n")
            for i in range(1, 5)
        ],
    )

    result = _backfill_test_tags(problem)

    tagged = {t.misconception_ids[0] for t in result.tests if t.misconception_ids}
    assert tagged == set(declared_misconception_ids(pedagogy))


def test_backfill_fills_misconceptions_when_requirements_exist() -> None:
    """The axes are independent: a test with only requirement_ids still gets one."""
    from app.generation.pipeline import _backfill_test_tags
    from app.schemas.pedagogy import Pedagogy
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase

    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        pedagogy=Pedagogy(likely_misconceptions=["MIS-A: x", "MIS-B: y"]),
        tests=[
            TestCase(
                id="a", name="A", stdin="1\n", expected_stdout="x\n",
                requirement_ids=["REQ-SPECIFIC"],
            ),
        ],
    )

    result = _backfill_test_tags(problem)

    # Model-supplied requirement tag preserved, missing axis filled.
    assert result.tests[0].requirement_ids == ["REQ-SPECIFIC"]
    assert result.tests[0].misconception_ids == ["MIS-A"]


def test_backfill_does_not_touch_an_existing_misconception_tag() -> None:
    from app.generation.pipeline import _backfill_test_tags
    from app.schemas.pedagogy import Pedagogy
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase

    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        pedagogy=Pedagogy(likely_misconceptions=["MIS-A: x"]),
        tests=[
            TestCase(
                id="a", name="A", stdin="1\n", expected_stdout="x\n",
                misconception_ids=["MIS-MODEL-CHOICE"],
            ),
        ],
    )

    result = _backfill_test_tags(problem)

    assert result.tests[0].misconception_ids == ["MIS-MODEL-CHOICE"]


def test_backfill_leaves_misconceptions_empty_without_pedagogy() -> None:
    from app.generation.pipeline import _backfill_test_tags
    from app.schemas.problem import Problem, ProblemMetadata
    from app.schemas.test_case import TestCase

    problem = Problem(
        metadata=ProblemMetadata(id="p", title="P"),
        statement_md="x",
        tests=[TestCase(id="a", name="A", stdin="1\n", expected_stdout="x\n")],
    )

    result = _backfill_test_tags(problem)

    assert result.tests[0].misconception_ids == []
