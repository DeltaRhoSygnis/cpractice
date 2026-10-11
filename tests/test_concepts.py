"""Tests for problem-set concept legality (spec S3).

These cover the deterministic pairing rule: a legal pair is accepted, and each
documented violation is rejected. They also pin the static scan against
hand-written reference snippets so the scanner cannot quietly drift.
"""

from __future__ import annotations

from app.schemas.problem import ConceptPair, Problem, ProblemKind, ProblemMetadata
from app.services.concepts import (
    ConceptConcern,
    ConceptLegalityChecker,
    is_problem_set,
    required_concepts,
    scan_reference,
)

# --- reference snippets -----------------------------------------------------

LOOP_REFERENCE = """\
#include <stdio.h>
int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;
    for (int i = 0; i < n; i++) printf("%d ", i);
    return 0;
}
"""

ARRAY_REFERENCE = """\
#include <stdio.h>
int main(void) {
    int a[3] = {1, 2, 3};
    int sum = 0;
    for (int i = 0; i < 3; i++) sum += a[i];
    printf("%d\\n", sum);
    return 0;
}
"""

STRUCT_REFERENCE = """\
#include <stdio.h>
struct Point { int x; int y; };
int main(void) {
    struct Point p = {1, 2};
    printf("%d\\n", p.x + p.y);
    return 0;
}
"""

RECURSIVE_REFERENCE = """\
#include <stdio.h>
int fact(int n) {
    if (n <= 1) return 1;
    return n * fact(n - 1);
}
int main(void) { printf("%d\\n", fact(5)); return 0; }
"""

POINTER_REFERENCE = """\
#include <stdio.h>
void swap(int *a, int *b) { int t = *a; *a = *b; *b = t; }
int main(void) { int x = 1, y = 2; swap(&x, &y); printf("%d %d\\n", x, y); return 0; }
"""

# Multiplication must never be mistaken for pointer syntax.
ARITHMETIC_REFERENCE = """\
#include <stdio.h>
int main(void) { int a = 2, b = 3; printf("%d\\n", a * b); return 0; }
"""


# --- helpers ----------------------------------------------------------------


def _pset(
    reference: str,
    *,
    new_concept: str = "for_loops",
    assumed_known: list[str] | None = None,
    topics: list[str] | None = None,
    target_skills: list[str] | None = None,
    kind: ProblemKind = ProblemKind.PROBLEM_SET,
    concept: bool = True,
) -> Problem:
    metadata = ProblemMetadata(
        id="p",
        title="P",
        kind=kind,
        topics=topics or [],
        target_skills=target_skills or [],
        concept=(
            ConceptPair(
                new_concept=new_concept,
                assumed_known=assumed_known if assumed_known is not None else ["input_output"],
            )
            if concept
            else None
        ),
    )
    return Problem(metadata=metadata, statement_md="x", reference_solution=reference)


# --- the scan ---------------------------------------------------------------


def test_scan_detects_loop_constructs() -> None:
    markers = scan_reference(LOOP_REFERENCE)

    assert markers["for_loops"] is True
    assert markers["while_loops"] is False


def test_scan_detects_arrays() -> None:
    assert scan_reference(ARRAY_REFERENCE)["arrays"] is True


def test_scan_detects_structs() -> None:
    assert scan_reference(STRUCT_REFERENCE)["structs"] is True


def test_scan_detects_recursion() -> None:
    assert scan_reference(RECURSIVE_REFERENCE)["recursion"] is True


def test_scan_detects_pointers_in_declarations() -> None:
    assert scan_reference(POINTER_REFERENCE)["pointers"] is True


def test_scan_does_not_confuse_multiplication_with_pointers() -> None:
    markers = scan_reference(ARITHMETIC_REFERENCE)

    assert markers["pointers"] is False
    assert markers["arrays"] is False


def test_scan_ignores_markers_in_comments_and_strings() -> None:
    src = '/* struct for_loops */\n#include <stdio.h>\nint main(void){ printf("for while struct"); return 0; }'

    markers = scan_reference(src)

    assert markers["for_loops"] is False
    assert markers["while_loops"] is False
    assert markers["structs"] is False


def test_scan_does_not_flag_a_call_to_another_function() -> None:
    src = "#include <stdio.h>\nint helper(int n){return n;}\nint main(void){return helper(1);}"

    assert scan_reference(src)["recursion"] is False


# --- required_concepts ------------------------------------------------------


def test_required_concepts_from_loop_reference() -> None:
    assert required_concepts(_pset(LOOP_REFERENCE)) == frozenset({"for_loops"})


def test_required_concepts_from_array_reference() -> None:
    assert required_concepts(_pset(ARRAY_REFERENCE)) == frozenset(
        {"for_loops", "arrays"}
    )


def test_required_concepts_from_struct_reference() -> None:
    assert required_concepts(_pset(STRUCT_REFERENCE)) == frozenset({"structs"})


def test_required_concepts_from_recursive_reference() -> None:
    # No ``recursion`` tag exists in the ladder, so a self-call requires the
    # ``functions`` stage (see the module docstring).
    assert required_concepts(_pset(RECURSIVE_REFERENCE)) == frozenset({"functions"})


def test_required_concepts_from_pointer_reference() -> None:
    assert required_concepts(_pset(POINTER_REFERENCE)) == frozenset({"pointers"})


def test_required_concepts_includes_declared_concept_topics() -> None:
    problem = _pset(ARITHMETIC_REFERENCE, topics=["counting"], target_skills=["min_max"])

    assert required_concepts(problem) == frozenset({"counting", "min_max"})


def test_required_concepts_ignores_free_form_topics_and_skills() -> None:
    # A skill tag is descriptive, not a concept; it must not widen requirements.
    problem = _pset(ARITHMETIC_REFERENCE, topics=["io"], target_skills=["loop_bounds"])

    assert required_concepts(problem) == frozenset()


# --- legality checker -------------------------------------------------------


def test_legal_pair_is_accepted() -> None:
    # Frontier is stage 2 (loops). new_concept is for_loops, declared known.
    problem = _pset(
        LOOP_REFERENCE,
        new_concept="for_loops",
        assumed_known=["input_output"],
    )
    checklist = ["expressions", "types", "input_output", "if_else", "boolean_expressions"]

    result = ConceptLegalityChecker().check(problem, checklist)

    assert result.passed
    assert result.findings == []


def test_reference_above_frontier_is_rejected() -> None:
    # The learner has not reached arrays (frontier stage 2) but the reference
    # uses one.
    problem = _pset(
        ARRAY_REFERENCE,
        new_concept="for_loops",
        assumed_known=["input_output"],
    )
    checklist = ["expressions", "types", "input_output", "if_else", "boolean_expressions"]

    result = ConceptLegalityChecker().check(problem, checklist)

    assert not result.passed
    assert ConceptConcern.ABOVE_FRONTIER in {f.concern for f in result.fatal}


def test_new_concept_already_known_is_rejected() -> None:
    problem = _pset(
        LOOP_REFERENCE,
        new_concept="for_loops",
        assumed_known=["input_output"],
    )
    # for_loops is already checked.
    checklist = ["expressions", "types", "input_output", "for_loops", "while_loops", "loop_state"]

    result = ConceptLegalityChecker().check(problem, checklist)

    assert not result.passed
    assert ConceptConcern.NEW_CONCEPT_KNOWN in {f.concern for f in result.fatal}


def test_empty_assumed_known_is_rejected_defensively() -> None:
    # The schema forbids this, but the gate must not rely on the schema alone.
    problem = _pset(LOOP_REFERENCE)
    problem.metadata.concept.assumed_known = []

    result = ConceptLegalityChecker().check(problem, ["input_output"])

    assert not result.passed
    assert ConceptConcern.EMPTY_ASSUMED_KNOWN in {f.concern for f in result.fatal}


def test_undeclared_known_concept_is_a_non_fatal_warning() -> None:
    # The reference uses for_loops; the pair declares no known concept that is
    # a loop, but the learner does know it, so it is legal to use — warn only.
    problem = _pset(
        LOOP_REFERENCE,
        new_concept="while_loops",
        assumed_known=["input_output"],
    )
    checklist = [
        "expressions", "types", "input_output",
        "if_else", "boolean_expressions", "for_loops",
    ]

    result = ConceptLegalityChecker().check(problem, checklist)

    assert result.passed
    assert [f.concern for f in result.findings] == [ConceptConcern.NOT_DECLARED]
    assert result.findings[0].fatal is False


def test_complete_ladder_never_flags_above_frontier() -> None:
    # With every concept known there is nothing above the frontier; the only
    # possible complaint is that a "new" concept is already known.
    from app.services.curriculum import concept_tags

    problem = _pset(ARRAY_REFERENCE, new_concept="arrays", assumed_known=["for_loops"])

    result = ConceptLegalityChecker().check(problem, list(concept_tags()))

    concerns = {f.concern for f in result.findings}
    assert ConceptConcern.ABOVE_FRONTIER not in concerns
    assert concerns == {ConceptConcern.NEW_CONCEPT_KNOWN}


# --- backwards compatibility ------------------------------------------------


def test_legacy_pset_without_concept_block_skips_checks() -> None:
    problem = _pset(ARRAY_REFERENCE, concept=False)

    assert is_problem_set(problem) is False
    result = ConceptLegalityChecker().check(problem, [])

    assert result.passed
    assert result.findings == []


def test_plain_exercise_skips_checks() -> None:
    problem = _pset(ARRAY_REFERENCE, kind=ProblemKind.EXERCISE, concept=True)

    assert is_problem_set(problem) is False
    assert ConceptLegalityChecker().check(problem, []).passed


def test_pset_with_concept_block_is_checked() -> None:
    problem = _pset(LOOP_REFERENCE)

    assert is_problem_set(problem) is True


# --- finding shape ----------------------------------------------------------


def test_findings_serialise_with_concern_and_fatal() -> None:
    problem = _pset(ARRAY_REFERENCE, new_concept="for_loops", assumed_known=["input_output"])
    checklist = ["expressions", "types", "input_output"]

    payload = ConceptLegalityChecker().check(problem, checklist).to_dict()

    assert payload["passed"] is False
    assert payload["findings"][0]["concern"] == "concept-above-frontier"
    assert payload["findings"][0]["fatal"] is True
