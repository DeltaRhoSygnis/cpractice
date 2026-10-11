"""Tests for the C curriculum map and operational skill definitions."""

from __future__ import annotations

from app.services.curriculum import (
    SKILLS,
    STAGES,
    skills_for_stage_concepts,
    skills_up_to,
    stage_for_skill,
    unknown_skills,
    validate_skills,
)


# --- stage map -------------------------------------------------------------


def test_stages_are_ordered_and_contiguous() -> None:
    indexes = [s.index for s in STAGES]

    assert indexes == list(range(len(STAGES)))


def test_every_stage_has_a_name_and_concepts() -> None:
    for stage in STAGES:
        assert stage.name
        assert stage.concepts
        assert stage.reasoning_practice


def test_stage_zero_is_foundations() -> None:
    assert STAGES[0].index == 0
    assert "expressions" in STAGES[0].concepts


def test_final_stage_is_integration() -> None:
    assert STAGES[-1].name == "Integration"


# --- skill definitions -----------------------------------------------------


def test_every_skill_has_an_operational_definition() -> None:
    """A skill without observable evidence cannot be assessed (plan 5.2)."""
    for skill in SKILLS.values():
        assert skill.is_observable(), f"{skill.tag} lacks observable evidence"


def test_skill_demonstrations_are_specific_statements() -> None:
    for skill in SKILLS.values():
        for statement in skill.demonstrates:
            assert len(statement) > 20, f"{skill.tag}: {statement!r} is not specific"


def test_skills_reference_a_real_stage() -> None:
    indexes = {s.index for s in STAGES}
    for skill in SKILLS.values():
        assert skill.stage in indexes, f"{skill.tag} points at a missing stage"


def test_loop_bounds_states_what_it_observes() -> None:
    """The plan's own worked example."""
    skill = SKILLS["loop_bounds"]

    assert any("first and final iteration" in d for d in skill.demonstrates)
    assert any("inclusive or exclusive" in d for d in skill.demonstrates)
    assert any("count" in d for d in skill.demonstrates)


def test_algorithm_decomposition_states_what_it_observes() -> None:
    skill = SKILLS["algorithm_decomposition"]

    assert any("inputs" in d and "output" in d for d in skill.demonstrates)
    assert any("steps" in d for d in skill.demonstrates)


def test_array_traversal_states_what_it_observes() -> None:
    skill = SKILLS["array_traversal"]

    assert any("valid indexes" in d for d in skill.demonstrates)
    assert any("empty" in d for d in skill.demonstrates)


# --- lookups ---------------------------------------------------------------


def test_stage_for_skill() -> None:
    assert stage_for_skill("loop_bounds").index == 2
    assert stage_for_skill("array_traversal").index == 6


def test_stage_for_unknown_skill_is_none() -> None:
    assert stage_for_skill("no_such_skill") is None


def test_skills_up_to_a_stage() -> None:
    early = skills_up_to(2)

    assert all(s.stage <= 2 for s in early)
    assert any(s.tag == "loop_bounds" for s in early)
    assert not any(s.tag == "array_traversal" for s in early)


def test_skills_for_stage_concepts() -> None:
    skills = skills_for_stage_concepts(["arrays"])

    assert any(s.tag == "array_traversal" for s in skills)


# --- validation ------------------------------------------------------------


def test_unknown_skills_are_reported() -> None:
    assert unknown_skills(["loop_bounds", "made_up"]) == ["made_up"]


def test_validate_skills_splits_known_and_unknown() -> None:
    known, unknown = validate_skills(["loop_bounds", "nope", "accumulation"])

    assert known == ["loop_bounds", "accumulation"]
    assert unknown == ["nope"]


def test_no_unknown_skills_in_the_shipped_map() -> None:
    assert unknown_skills(list(SKILLS)) == []


# --- concept ladder (problem-set engine, spec S3) --------------------------


def test_concept_tags_covers_every_stage_concept() -> None:
    from app.services.curriculum import concept_tags

    assert set(concept_tags()) == {
        concept for stage in STAGES for concept in stage.concepts
    }


def test_stage_index_for_concept() -> None:
    from app.services.curriculum import stage_index_for_concept

    assert stage_index_for_concept("expressions") == 0
    assert stage_index_for_concept("pointers") == 9
    assert stage_index_for_concept("not_a_concept") is None


def test_frontier_with_empty_checklist_is_stage_zero() -> None:
    from app.services.curriculum import frontier

    assert frontier([]) == 0


def test_frontier_with_partial_checklist() -> None:
    from app.services.curriculum import frontier

    # All of stage 0 and stage 1 are checked; stage 2 is not.
    checklist = ["expressions", "types", "input_output", "if_else", "boolean_expressions"]

    assert frontier(checklist) == 2


def test_frontier_ignores_unknown_tags() -> None:
    from app.services.curriculum import frontier

    # An unknown tag must not widen the "known" set.
    assert frontier(["nonsense"]) == 0


def test_frontier_with_full_checklist_is_none() -> None:
    from app.services.curriculum import concept_tags, frontier

    assert frontier(list(concept_tags())) is None


def test_forbidden_set_is_everything_above_the_frontier() -> None:
    from app.services.curriculum import forbidden_set, stage_index_for_concept

    # Stage 0 is checked, so the frontier is stage 1.
    forbidden = forbidden_set(["expressions", "types", "input_output"])

    assert all(stage_index_for_concept(tag) > 1 for tag in forbidden)
    assert "for_loops" in forbidden  # stage 2 is above the stage-1 frontier
    assert "if_else" not in forbidden  # stage 1 is *at* the frontier, not above


def test_forbidden_set_empty_when_ladder_complete() -> None:
    from app.services.curriculum import concept_tags, forbidden_set

    assert forbidden_set(list(concept_tags())) == frozenset()


def test_unknown_concepts_are_reported() -> None:
    from app.services.curriculum import unknown_concepts

    assert unknown_concepts(["arrays", "made_up", "made_up"]) == ["made_up"]
