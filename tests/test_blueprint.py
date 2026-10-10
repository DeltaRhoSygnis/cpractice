"""Tests for the blueprint stage and versioned prompt assets."""

from __future__ import annotations

import json

import pytest

from app.ai.base import AuthError
from app.ai.mock import MockProvider, failing_provider
from app.ai.prompts_loader import (
    ASSETS,
    PROMPT_VERSION,
    PromptAssetError,
    available_prompts,
    load_prompt,
    missing_assets,
)
from app.generation.blueprint import (
    BlueprintDesigner,
    BlueprintError,
    BlueprintRequest,
    blueprint_to_prompt_text,
)
from app.schemas.pedagogy import ExerciseRole


# --- prompt assets ---------------------------------------------------------


def test_all_declared_prompts_exist() -> None:
    assert missing_assets() == []


def test_prompt_version_is_pinned() -> None:
    assert PROMPT_VERSION


def test_prompts_are_non_empty_markdown() -> None:
    for name in available_prompts():
        text = load_prompt(name)
        assert len(text) > 200, f"{name} is suspiciously short"
        assert "#" in text, f"{name} should have a heading"


def test_unknown_prompt_raises() -> None:
    with pytest.raises(PromptAssetError):
        load_prompt("no_such_prompt")


def test_every_asset_is_reachable_by_logical_name() -> None:
    for name in ASSETS:
        assert load_prompt(name)


def test_calibration_prompt_states_the_failure_mode() -> None:
    text = load_prompt("calibration").lower()

    assert "reasoning move" in text
    assert "same shape" in text or "vary only by value" in text or "uniform" in text


def test_system_role_forbids_ambiguous_phrasing() -> None:
    text = load_prompt("system_role").lower()

    assert "ambiguous" in text or "precise specification" in text


def test_design_tests_prompt_requires_independence() -> None:
    """Expected outputs must not be copied from one implementation's behaviour."""
    text = load_prompt("design_tests").lower()

    assert "independence" in text or "by hand" in text
    assert "misconception" in text


def test_repair_prompt_forbids_weakening_tests() -> None:
    text = load_prompt("repair_invalid_package").lower()

    assert "never weaken" in text or "do not weaken" in text


# --- blueprint request -----------------------------------------------------


def test_request_normalises_optional_lists() -> None:
    request = BlueprintRequest(topic="loops")

    assert request.target_skills == []
    assert request.prerequisites == []
    assert request.forbid == []


def test_request_defaults_to_core_reasoning() -> None:
    assert BlueprintRequest(topic="loops").exercise_role is ExerciseRole.CORE_REASONING


# --- blueprint design ------------------------------------------------------


def _blueprint_payload(**overrides) -> str:
    payload = {
        "primary_objective": "derive loop bounds so each element is processed once",
        "target_reasoning_moves": ["derive the upper bound", "maintain running state"],
        "likely_misconceptions": ["off-by-one: one element too many"],
        "exercise_role": "core_reasoning",
        "prerequisites": ["for_loops"],
        "difficulty_profile": {"reasoning_steps": 2},
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_designs_a_valid_blueprint() -> None:
    designer = BlueprintDesigner(MockProvider(responses=_blueprint_payload()))

    pedagogy = designer.design(BlueprintRequest(topic="loops"))

    assert pedagogy.exercise_role is ExerciseRole.CORE_REASONING
    assert len(pedagogy.target_reasoning_moves) == 2
    assert pedagogy.likely_misconceptions
    assert pedagogy.difficulty_profile.reasoning_steps == 2


def test_sends_system_and_prompt_to_provider() -> None:
    provider = MockProvider(responses=_blueprint_payload())

    BlueprintDesigner(provider).design(BlueprintRequest(topic="arrays"))

    call = provider.calls[0]
    assert "instructor" in call["system"].lower() or "designer" in call["system"].lower()
    assert "arrays" in call["prompt"]


def test_includes_prerequisites_in_prompt() -> None:
    provider = MockProvider(responses=_blueprint_payload())

    BlueprintDesigner(provider).design(
        BlueprintRequest(topic="arrays", prerequisites=["for_loops", "arrays"])
    )

    prompt = provider.calls[0]["prompt"]
    assert "for_loops" in prompt
    assert "do not require others" in prompt.lower()


def test_includes_forbidden_constructs() -> None:
    provider = MockProvider(responses=_blueprint_payload())

    BlueprintDesigner(provider).design(
        BlueprintRequest(topic="arrays", forbid=["goto", "recursion"])
    )

    assert "goto" in provider.calls[0]["prompt"]


# --- rejection of weak blueprints ------------------------------------------


def test_rejects_a_blueprint_with_too_few_reasoning_moves() -> None:
    """A core problem declared with one move is the documented failure mode."""
    payload = _blueprint_payload(target_reasoning_moves=["just one thing"])

    with pytest.raises(BlueprintError) as excinfo:
        BlueprintDesigner(MockProvider(responses=payload)).design(BlueprintRequest(topic="loops"))

    assert "reasoning move" in str(excinfo.value)


def test_allows_a_warmup_with_one_move() -> None:
    payload = _blueprint_payload(
        exercise_role="diagnostic_warmup",
        target_reasoning_moves=["recall operator precedence"],
    )

    pedagogy = BlueprintDesigner(MockProvider(responses=payload)).design(
        BlueprintRequest(topic="expressions", exercise_role=ExerciseRole.DIAGNOSTIC_WARMUP)
    )

    assert pedagogy.exercise_role is ExerciseRole.DIAGNOSTIC_WARMUP


def test_unknown_role_falls_back_to_the_requested_role() -> None:
    payload = _blueprint_payload(exercise_role="not_a_real_role")

    pedagogy = BlueprintDesigner(MockProvider(responses=payload)).design(
        BlueprintRequest(topic="loops", exercise_role=ExerciseRole.CORE_REASONING)
    )

    assert pedagogy.exercise_role is ExerciseRole.CORE_REASONING


def test_unparseable_blueprint_raises() -> None:
    with pytest.raises(BlueprintError):
        BlueprintDesigner(MockProvider(responses="not json")).design(BlueprintRequest(topic="x"))


def test_provider_failure_raises_blueprint_error() -> None:
    with pytest.raises(BlueprintError):
        BlueprintDesigner(failing_provider(AuthError("no key"))).design(
            BlueprintRequest(topic="x")
        )


def test_retries_a_transient_provider_failure() -> None:
    from app.ai.base import ProviderUnavailableError

    provider = MockProvider(
        responses=_blueprint_payload(), errors=[ProviderUnavailableError("blip")]
    )
    designer = BlueprintDesigner(provider, sleep=lambda _: None)

    pedagogy = designer.design(BlueprintRequest(topic="loops"))

    assert pedagogy.primary_objective
    assert len(provider.calls) == 2


# --- prompt rendering ------------------------------------------------------


def test_blueprint_renders_into_design_instructions() -> None:
    pedagogy = BlueprintDesigner(MockProvider(responses=_blueprint_payload())).design(
        BlueprintRequest(topic="loops", prerequisites=["for_loops"])
    )

    text = blueprint_to_prompt_text(pedagogy)

    assert "Primary objective" in text
    assert "reasoning moves" in text.lower()
    assert "for_loops" in text
    assert "calibration" in text.lower()


def test_rendered_instructions_list_misconceptions() -> None:
    pedagogy = BlueprintDesigner(MockProvider(responses=_blueprint_payload())).design(
        BlueprintRequest(topic="loops")
    )

    text = blueprint_to_prompt_text(pedagogy)

    assert "off-by-one" in text
