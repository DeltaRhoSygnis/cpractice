"""Tests for payload normalisation.

Written against a real DeepSeek V4.1 Flash response captured through the
Kenari gateway, which used ``description``, ``input_format``, and split
``public_tests``/``hidden_tests`` instead of the canonical field names.
"""

from __future__ import annotations

from app.generation.normalize import normalize_payload, slugify


def test_slugify_produces_valid_ids() -> None:
    assert slugify("Sum of Space-Separated Integers") == "sum-of-space-separated-integers"
    assert slugify("  Weird!! Name??  ") == "weird-name"
    assert slugify("") == "generated-problem"
    assert slugify("!!!") == "generated-problem"


def test_slugify_truncates() -> None:
    assert len(slugify("a" * 200)) <= 48


# --- real-world payload shape ---------------------------------------------


def real_world_payload() -> dict:
    """Mirrors an actual model response observed through Kenari."""
    return {
        "title": "Sum of Space-Separated Integers",
        "topic": "loops",
        "difficulty": "beginner",
        "target_skills": ["iteration"],
        "description": "Read a line of integers and print their sum.",
        "input_format": "A single line of space-separated integers.",
        "output_format": "One integer followed by a newline.",
        "constraints": ["1 <= count <= 1000"],
        "forbidden_constructs": [],
        "hints": [
            {"level": 1, "text": "Use a loop."},
            {"level": 2, "text": "scanf returns the count read."},
        ],
        "public_tests": [
            {"input": "1 2 3", "expected_output": "6\n", "name": "Basic"},
        ],
        "hidden_tests": [
            {"input": "0", "expected_output": "0\n", "name": "Zero"},
        ],
        "reference_solution": "#include <stdio.h>\nint main(void){return 0;}\n",
    }


def test_maps_description_to_statement() -> None:
    out = normalize_payload(real_world_payload())

    assert out["statement_md"].startswith("Read a line of integers")


def test_folds_format_prose_into_statement() -> None:
    out = normalize_payload(real_world_payload())

    assert "### Input format" in out["statement_md"]
    assert "### Output format" in out["statement_md"]
    assert "### Constraints" in out["statement_md"]


def test_merges_split_test_lists_with_visibility() -> None:
    out = normalize_payload(real_world_payload())

    tests = out["tests"]
    assert len(tests) == 2
    assert tests[0]["visibility"] == "public"
    assert tests[1]["visibility"] == "hidden"


def test_maps_test_field_aliases() -> None:
    out = normalize_payload(real_world_payload())

    first = out["tests"][0]
    assert first["stdin"] == "1 2 3"
    assert first["expected_stdout"] == "6\n"
    assert first["expected_exit_code"] == 0


def test_generates_ids_for_unnamed_tests() -> None:
    out = normalize_payload(real_world_payload())

    assert all(test["id"] for test in out["tests"])
    assert out["tests"][0]["id"] == "test-1"


def test_derives_problem_id_from_title() -> None:
    out = normalize_payload(real_world_payload())

    assert out["id"] == "sum-of-space-separated-integers"


def test_scalar_topic_becomes_a_list() -> None:
    out = normalize_payload(real_world_payload())

    assert out["topics"] == ["loops"]


def test_string_topics_are_split() -> None:
    out = normalize_payload({"id": "x", "title": "T", "topics": "loops, arrays"})

    assert out["topics"] == ["loops", "arrays"]


def test_unknown_metadata_keys_are_dropped() -> None:
    out = normalize_payload(real_world_payload())

    for key in ("topic", "description", "input_format", "output_format",
                "constraints", "forbidden_constructs", "public_tests", "hidden_tests"):
        assert key not in out


def test_only_known_keys_survive() -> None:
    out = normalize_payload({"id": "x", "title": "T", "totally_unknown": 123})

    assert "totally_unknown" not in out


# --- type coercion ---------------------------------------------------------


def test_int_version_is_accepted() -> None:
    out = normalize_payload({"id": "x", "title": "T", "version": 3})

    assert out["version"] == 3


def test_string_version_is_coerced() -> None:
    out = normalize_payload({"id": "x", "title": "T", "version": "4"})

    assert out["version"] == 4


def test_unparseable_version_defaults_to_one() -> None:
    out = normalize_payload({"id": "x", "title": "T", "version": "v1"})

    assert out["version"] == 1


def test_int_schema_version_becomes_string() -> None:
    out = normalize_payload({"id": "x", "title": "T", "schema_version": 1})

    assert out["schema_version"] == "1"


def test_missing_schema_version_is_defaulted() -> None:
    out = normalize_payload({"id": "x", "title": "T"})

    assert out["schema_version"] == "1.0"


def test_string_hint_levels_become_ints() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "hints": [{"level": "1", "text": "a"}, {"level": "2", "text": "b"}],
    })

    assert [h["level"] for h in out["hints"]] == [1, 2]


def test_missing_hint_levels_are_numbered() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "hints": [{"text": "a"}, {"text": "b"}],
    })

    assert [h["level"] for h in out["hints"]] == [1, 2]


def test_string_exit_code_is_coerced() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "tests": [{"id": "t", "name": "T", "expected_exit_code": "2"}],
    })

    assert out["tests"][0]["expected_exit_code"] == 2


def test_invalid_timeout_is_dropped() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "tests": [{"id": "t", "name": "T", "timeout_ms": 999999}],
    })

    assert "timeout_ms" not in out["tests"][0]


# --- visibility ------------------------------------------------------------


def test_visibility_variants_map_to_hidden() -> None:
    for value in ("hidden", "Hidden", "HIDDEN", "hidden_test"):
        out = normalize_payload({
            "id": "x", "title": "T",
            "tests": [{"id": "t", "name": "T", "visibility": value}],
        })
        assert out["tests"][0]["visibility"] == "hidden"


def test_unknown_visibility_defaults_to_public() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "tests": [{"id": "t", "name": "T", "visibility": "weird"}],
    })

    assert out["tests"][0]["visibility"] == "public"


# --- robustness ------------------------------------------------------------


def test_non_dict_payload_is_returned_unchanged() -> None:
    assert normalize_payload([1, 2, 3]) == [1, 2, 3]


def test_empty_payload_does_not_crash() -> None:
    out = normalize_payload({})

    assert out["schema_version"] == "1.0"
    assert out["version"] == 1
    assert out["id"] == "generated-problem"


def test_reference_aliases_are_accepted() -> None:
    out = normalize_payload({"id": "x", "title": "T", "reference": "int main(){return 0;}"})

    assert out["reference_solution"] == "int main(){return 0;}"


def test_starter_aliases_are_accepted() -> None:
    out = normalize_payload({"id": "x", "title": "T", "template": "/* TODO */"})

    assert out["starter_code"] == "/* TODO */"


def test_statement_contains_no_duplicated_sections() -> None:
    payload = {
        "id": "x", "title": "T",
        "statement_md": "Already includes the constraint 1 <= n <= 10",
        "constraints": "1 <= n <= 10",
    }
    out = normalize_payload(payload)

    # The appendix is skipped because the text is already present.
    assert out["statement_md"].count("1 <= n <= 10") == 1


# --- hint shapes -----------------------------------------------------------


def test_hints_as_plain_strings_are_numbered() -> None:
    """Observed in a real response: hints came back as bare strings."""
    out = normalize_payload({
        "id": "x", "title": "T",
        "hints": ["Think about representation.", "Try a recurrence.", "Check the base case."],
    })

    assert out["hints"] == [
        {"level": 1, "text": "Think about representation."},
        {"level": 2, "text": "Try a recurrence."},
        {"level": 3, "text": "Check the base case."},
    ]


def test_hint_text_under_alternative_key() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "hints": [{"level": 1, "hint": "Guidance here"}],
    })

    assert out["hints"] == [{"level": 1, "text": "Guidance here"}]


def test_hints_without_levels_are_numbered() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "hints": ["a", "b"],
    })

    assert [h["level"] for h in out["hints"]] == [1, 2]


def test_duplicate_hint_levels_are_renumbered() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "hints": [{"level": 1, "text": "a"}, {"level": 1, "text": "b"}],
    })

    levels = [h["level"] for h in out["hints"]]
    assert len(levels) == len(set(levels))


def test_out_of_range_hint_level_is_renumbered() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "hints": [{"level": 99, "text": "a"}],
    })

    assert out["hints"][0]["level"] == 1


def test_empty_string_hints_are_dropped() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "hints": ["  ", {"level": 2, "text": "  "}, "real hint"],
    })

    assert out["hints"] == [{"level": 1, "text": "real hint"}]


def test_non_dict_test_entries_are_skipped() -> None:
    """Observed live: a stray scalar appeared inside the tests list."""
    out = normalize_payload({
        "id": "x", "title": "T",
        "tests": [
            {"id": "a", "name": "A", "stdin": "1", "expected_stdout": "1"},
            "public",
            {"id": "b", "name": "B", "stdin": "2", "expected_stdout": "2"},
        ],
    })

    assert len(out["tests"]) == 2
    assert [t["id"] for t in out["tests"]] == ["a", "b"]


def test_entirely_non_dict_test_list_yields_no_tests() -> None:
    out = normalize_payload({"id": "x", "title": "T", "tests": ["a", "b"]})

    assert out["tests"] == []


# --- test-count invariants (adversarial review finding) --------------------


def test_duplicate_ids_are_dropped_and_reported() -> None:
    """A merged public/hidden list can repeat a test; the loss must be visible.

    Raised by council review: silently changing the test set looks like success
    because the reference still compiles and passes.
    """
    out = normalize_payload({
        "id": "x", "title": "T",
        "tests": [{"id": "same", "name": "Public", "visibility": "public",
                   "stdin": "1", "expected_stdout": "1"}],
        "hidden_tests": [{"id": "same", "name": "Hidden",
                          "stdin": "2", "expected_stdout": "2"}],
    })

    assert len(out["tests"]) == 1
    assert out["normalization_notes"]
    assert "same" in out["normalization_notes"][0]


def test_first_occurrence_wins_on_duplicate_id() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "tests": [{"id": "same", "name": "First", "visibility": "public",
                   "stdin": "1", "expected_stdout": "1"}],
        "hidden_tests": [{"id": "same", "name": "Second",
                          "stdin": "2", "expected_stdout": "2"}],
    })

    assert out["tests"][0]["name"] == "First"


def test_no_notes_when_nothing_was_dropped() -> None:
    out = normalize_payload({
        "id": "x", "title": "T",
        "tests": [
            {"id": "a", "name": "A", "stdin": "1", "expected_stdout": "1"},
            {"id": "b", "name": "B", "stdin": "2", "expected_stdout": "2"},
        ],
    })

    assert "normalization_notes" not in out
    assert len(out["tests"]) == 2


def test_notes_are_not_left_in_the_payload_as_metadata() -> None:
    """The notes key is transport, not schema content."""
    from app.schemas.problem import CONTENT_KEYS

    assert "normalization_notes" not in CONTENT_KEYS
