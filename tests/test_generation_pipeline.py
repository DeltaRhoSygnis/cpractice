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

REFERENCE = (
    '#include <stdio.h>\n'
    'int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;'
    'printf("%d\\n",a+b);return 0;}\n'
)


def good_payload(**overrides) -> dict:
    payload = {
        "id": "c-generated-sum",
        "title": "Generated Sum",
        "difficulty": "beginner",
        "topics": ["arithmetic"],
        "target_skills": ["scanf"],
        "statement_md": "# Sum\n\nRead two integers and print their sum.",
        "starter_code": "int main(void){return 0;}",
        "reference_solution": REFERENCE,
        "tests": [
            {"id": "a", "name": "A", "visibility": "public", "stdin": "1 2\n", "expected_stdout": "3\n"},
            {"id": "b", "name": "B", "visibility": "public", "stdin": "-1 -2\n", "expected_stdout": "-3\n"},
            {"id": "c", "name": "C", "visibility": "hidden", "stdin": "0 0\n", "expected_stdout": "0\n"},
            {"id": "d", "name": "D", "visibility": "hidden", "stdin": "1000 2000\n", "expected_stdout": "3000\n"},
        ],
        "hints": [
            {"level": 1, "text": "concept"},
            {"level": 2, "text": "direction"},
            {"level": 3, "text": "trace"},
            {"level": 4, "text": "pseudocode"},
            {"level": 5, "text": "see reference approach"},
        ],
        "solution_explanation": "Read two ints and print the sum.",
    }
    payload.update(overrides)
    return payload


def _pipeline(tmp_path: Path, provider) -> GenerationPipeline:
    return GenerationPipeline(provider, problems_dir=tmp_path / "problems")


# --- happy path ------------------------------------------------------------


def test_generates_and_validates_a_problem(tmp_path: Path) -> None:
    provider = MockProvider(responses=json.dumps(good_payload()))

    outcome = _pipeline(tmp_path, provider).generate(GenerationRequest())

    assert outcome.accepted is True
    assert outcome.problem.id == "c-generated-sum"
    assert outcome.problem.metadata.status.value == "validated"
    assert outcome.quality.reference_passed == 4


def test_saves_package_and_quality_report(tmp_path: Path) -> None:
    provider = MockProvider(responses=json.dumps(good_payload()))

    _pipeline(tmp_path, provider).generate(GenerationRequest())

    package = tmp_path / "problems" / "c-generated-sum"
    assert (package / "problem.json").is_file()
    assert (package / "statement.md").is_file()
    assert (package / "starter" / "main.c").is_file()
    assert (package / "reference" / "main.c").is_file()
    assert (package / "quality_report.json").is_file()


def test_saved_package_reloads_through_the_repository(tmp_path: Path) -> None:
    from app.storage.problem_repository import ProblemRepository

    provider = MockProvider(responses=json.dumps(good_payload()))
    _pipeline(tmp_path, provider).generate(GenerationRequest())

    reloaded = ProblemRepository(tmp_path / "problems").load("c-generated-sum")

    assert reloaded.title == "Generated Sum"
    assert len(reloaded.tests) == 4
    assert reloaded.reference_solution.strip() == REFERENCE.strip()


# --- caching ---------------------------------------------------------------


def test_second_identical_request_uses_cache(tmp_path: Path) -> None:
    provider = MockProvider(responses=json.dumps(good_payload()))
    pipeline = _pipeline(tmp_path, provider)

    first = pipeline.generate(GenerationRequest(topic="arithmetic"))
    second = pipeline.generate(GenerationRequest(topic="arithmetic"))

    assert first.from_cache is False
    assert second.from_cache is True
    assert len(provider.calls) == 1


def test_different_parameters_do_not_share_cache(tmp_path: Path) -> None:
    provider = MockProvider(responses=json.dumps(good_payload()))
    pipeline = _pipeline(tmp_path, provider)

    pipeline.generate(GenerationRequest(topic="loops"))
    pipeline.generate(GenerationRequest(topic="arrays"))

    assert len(provider.calls) == 2


def test_cache_can_be_bypassed(tmp_path: Path) -> None:
    provider = MockProvider(responses=json.dumps(good_payload()))
    pipeline = _pipeline(tmp_path, provider)

    pipeline.generate(GenerationRequest())
    pipeline.generate(GenerationRequest(), use_cache=False)

    assert len(provider.calls) == 2


def test_invalid_problem_is_not_cached(tmp_path: Path) -> None:
    bad = good_payload(reference_solution="int main(void){ printf(\"x\" return 0; }")
    provider = MockProvider(responses=json.dumps(bad))
    pipeline = _pipeline(tmp_path, provider)

    first = pipeline.generate(GenerationRequest())
    second = pipeline.generate(GenerationRequest())

    assert first.accepted is False
    # Not cached, so the provider is consulted again.
    assert second.from_cache is False
    assert len(provider.calls) == 2


# --- provider failure handling ---------------------------------------------


def test_auth_error_is_not_retried(tmp_path: Path) -> None:
    provider = failing_provider(AuthError("bad key"), times=5)

    with pytest.raises(AuthError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())

    assert len(provider.calls) == 1


def test_transient_error_is_retried_then_succeeds(tmp_path: Path) -> None:
    provider = MockProvider(
        responses=json.dumps(good_payload()),
        errors=[ProviderUnavailableError("blip")],
    )
    pipeline = GenerationPipeline(
        provider,
        problems_dir=tmp_path / "problems",
        sleep=lambda _: None,
    )

    outcome = pipeline.generate(GenerationRequest())

    assert outcome.accepted is True
    assert len(provider.calls) == 2


def test_malformed_json_raises_generation_error(tmp_path: Path) -> None:
    provider = MockProvider(responses="this is not json at all")

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())


def test_json_that_is_not_an_object_raises(tmp_path: Path) -> None:
    provider = MockProvider(responses="[1, 2, 3]")

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())


def test_missing_required_metadata_raises(tmp_path: Path) -> None:
    payload = good_payload()
    del payload["title"]
    provider = MockProvider(responses=json.dumps(payload))

    with pytest.raises(GenerationError):
        _pipeline(tmp_path, provider).generate(GenerationRequest())


def test_invalid_test_shape_raises(tmp_path: Path) -> None:
    payload = good_payload(
        tests=[{"id": "Bad ID", "name": "X", "visibility": "public", "stdin": "", "expected_stdout": ""}]
    )
    provider = MockProvider(responses=json.dumps(payload))

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
