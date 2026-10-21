"""Concept legality for problem sets (spec S3).

A problem set must combine exactly one *new* concept with concepts the learner
already knows. Whether that holds is a **deterministic** question, never an AI
judgement:

* :func:`required_concepts` works out which concepts the declared metadata and
  the reference solution actually need.
* :class:`ConceptLegalityChecker` compares that set against the learner's
  checklist and the frontier, producing findings the gate turns into pass/fail.

The vocabulary is exactly the ``concepts`` tuples in
:mod:`app.services.curriculum`; no new vocabulary is invented. Legality is only
checked for packages that declare themselves problem sets with a concept pair —
a legacy exercise (or a pset with no ``concept`` block) is never inspected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.schemas.problem import Problem, ProblemKind
from app.services import curriculum


def is_problem_set(problem: Problem) -> bool:
    """Whether a package should be run through the concept-legality gate.

    Backwards compatibility (spec S10): a package without a ``concept`` block
    is treated as plain exercise content and skips every problem-set check.
    """
    return (
        problem.metadata.kind == ProblemKind.PROBLEM_SET
        and problem.metadata.concept is not None
    )


# --- static scan ------------------------------------------------------------

#: Comment stripping, mirroring ``app.generation.calibration`` so both scanners
#: agree on what counts as code. String literals are removed too: a marker such
#: as ``struct`` inside a printed message is not a use of the language feature.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
_CHAR_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'")

#: ``for`` / ``while`` keywords, as whole words (``for`` inside ``before`` must
#: not match).
_FOR_KEYWORD = re.compile(r"\bfor\b")
_WHILE_KEYWORD = re.compile(r"\bwhile\b")

#: ``struct`` as a whole word.
_STRUCT_KEYWORD = re.compile(r"\bstruct\b")

#: A subscription expression: an identifier (optionally followed by more
#: identifiers, ``.`` or ``->`` selectors) immediately followed by ``[...]``.
#: This is the "array declaration/indexing" marker from the spec.
_SUBSCRIPT = re.compile(r"[A-Za-z_]\w*(?:\s*(?:\.|->)\s*[A-Za-z_]\w*)*\s*\[")

#: A pointer declarator: a C base type followed by one or more ``*``. This is
#: the spec's "pointer syntax in declarations" marker. It is deliberately
#: anchored to a type keyword so that multiplication (``a * b``) is never
#: mistaken for pointer syntax — a false positive here would wrongly reject a
#: problem set.
_POINTER_DECL = re.compile(
    r"\b(?:"
    r"int|char|void|float|double|long|short|unsigned|signed|"
    r"size_t|ssize_t|ptrdiff_t|FILE|bool|struct\s+[A-Za-z_]\w*"
    r")\b\s*(?:const\s+)?\*"
)

#: A function definition header: an identifier followed by a parenthesised
#: parameter list and an opening brace.
_FUNCTION_DEF = re.compile(r"\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", re.DOTALL)


def _strip_comments_and_literals(source: str) -> str:
    """Return ``source`` with comments and string/char literals removed."""
    source = _BLOCK_COMMENT.sub(" ", source)
    source = _LINE_COMMENT.sub(" ", source)
    source = _STRING_LITERAL.sub('""', source)
    source = _CHAR_LITERAL.sub("''", source)
    return source


def _function_body(body: str, open_brace_index: int) -> str:
    """Return the text of a brace-delimited block starting at ``open_brace_index``.

    Brace matching is naive with respect to braces inside literals, but the
    caller has already stripped comments and literals, so a plain counter is
    accurate for real C source.
    """
    depth = 0
    for index in range(open_brace_index, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                return body[open_brace_index + 1 : index]
    return body[open_brace_index + 1 :]


def _has_self_recursion(body: str) -> bool:
    """Whether a function defined in ``body`` calls itself.

    A self-call is a call to the enclosing function's name appearing **inside
    that function's own body**. Scoping the search to the body is what keeps a
    call from ``main`` to a ``helper`` from being mistaken for recursion: the
    helper's name appears twice in the file, but never inside the helper.
    """
    for match in _FUNCTION_DEF.finditer(body):
        name = match.group(1)
        inner = _function_body(body, match.end() - 1)
        if re.search(rf"\b{re.escape(name)}\s*\(", inner):
            return True
    return False


#: Marker -> the curriculum concept it requires. Every value is a real concept
#: tag, so the result can be positioned on the ladder.
#:
#: ``recursion`` is deliberately **not** used as a tag: ``STAGES`` declares no
#: such concept and inventing vocabulary would violate the spec's "no new
#: vocabulary" rule. A self-call is therefore required at the ``functions``
#: stage — the stage where defining and calling functions becomes available —
#: which is the lowest stage that a recursive reference provably needs. This
#: errs toward *not* over-rejecting, matching the rule that a false positive is
#: a wrongly rejected problem set.
_MARKER_CONCEPTS: dict[str, str] = {
    "for_loops": "for_loops",
    "while_loops": "while_loops",
    "arrays": "arrays",
    "structs": "structs",
    "recursion": "functions",
    "pointers": "pointers",
}


def scan_reference(reference_solution: str) -> dict[str, bool]:
    """Report which concept markers a reference solution contains.

    The scan is intentionally precise and documented marker-by-marker so a
    reviewer can see exactly why a pset was rejected:

    * ``for_loops`` / ``while_loops`` — the ``for`` / ``while`` keyword as a
      whole word in code (comments and literals stripped).
    * ``arrays`` — a subscript expression, ``identifier[...]``, including
      element access through ``.`` / ``->``. Array *declarations* produce a
      subscript too (``int a[10];``).
    * ``structs`` — the ``struct`` keyword.
    * ``recursion`` — a function that calls its own name.
    * ``pointers`` — a pointer *declarator*: a C base type followed by ``*``
      (``int *p``, ``char *s``, ``struct Node *n``), including the same in a
      parameter list. A bare ``*`` used as multiplication, or an address-of
      ``&`` used as a call argument (``scanf("%d", &n)``), does not register:
      neither needs the learner to understand pointer declarations.
    """
    body = _strip_comments_and_literals(reference_solution)

    return {
        "for_loops": bool(_FOR_KEYWORD.search(body)),
        "while_loops": bool(_WHILE_KEYWORD.search(body)),
        "arrays": bool(_SUBSCRIPT.search(body)),
        "structs": bool(_STRUCT_KEYWORD.search(body)),
        "recursion": _has_self_recursion(body),
        "pointers": bool(_POINTER_DECL.search(body)),
    }


def required_concepts(problem: Problem) -> frozenset[str]:
    """The concept tags a problem's reference actually needs.

    Two conservative sources are combined:

    1. **Declared metadata.** A ``topics`` or ``target_skills`` entry that is
       *itself* a concept tag is required. Free-form topics and operational
       skill tags (e.g. ``loop_bounds``) are descriptive and are deliberately
       **not** expanded into concepts: expanding a skill to its whole stage
       would demand concepts the reference may not use, and a false positive
       wrongly rejects a pset.
    2. **A static scan** of ``reference_solution`` (see :func:`scan_reference`).
       The scan is the enforcement backstop, so an undeclared array or loop is
       still caught even when the metadata is silent.

    The result contains only real curriculum tags, so the legality checker can
    always place each one on the ladder.
    """
    declared = set(problem.metadata.topics) | set(problem.metadata.target_skills)
    required = {tag for tag in declared if curriculum.concept_exists(tag)}

    for marker, present in scan_reference(problem.reference_solution).items():
        if present:
            required.add(_MARKER_CONCEPTS[marker])

    return frozenset(required)


# --- legality checker -------------------------------------------------------


class ConceptConcern(str, Enum):
    """Machine-detectable concept-legality problems."""

    ABOVE_FRONTIER = "concept-above-frontier"
    NEW_CONCEPT_KNOWN = "new-concept-known"
    EMPTY_ASSUMED_KNOWN = "empty-assumed-known"
    NOT_DECLARED = "concept-not-declared"


@dataclass(frozen=True)
class ConceptFinding:
    """One concept-legality concern, with the evidence behind it.

    Matches the shape of ``app.generation.calibration.CalibrationFinding``:
    ``concern`` names the problem, ``message`` explains it, ``fatal`` tells the
    gate whether it blocks. Errors are fatal; the one warning is not.
    """

    concern: ConceptConcern
    message: str
    fatal: bool

    def to_dict(self) -> dict:
        return {
            "concern": self.concern.value,
            "message": self.message,
            "fatal": self.fatal,
        }


@dataclass(frozen=True)
class ConceptLegalityResult:
    """Outcome of checking one problem set against a checklist."""

    findings: list[ConceptFinding]

    @property
    def fatal(self) -> list[ConceptFinding]:
        return [f for f in self.findings if f.fatal]

    @property
    def passed(self) -> bool:
        return not self.fatal

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
        }


class ConceptLegalityChecker:
    """Checks the deterministic pairing rule (spec S3) for a problem set.

    The rule::

        new_concept ∉ checklist
        assumed_known non-empty and ⊆ checklist
        required_concepts(reference) ⊆ assumed_known ∪ {new_concept}

    Violations are errors except ``concept-not-declared``, which warns when the
    reference merely happens to use a concept the pset did not declare it
    combines (that concept is still within the frontier, so it is legal to
    use — the warning is about intent, not permission).
    """

    def check(self, problem: Problem, checklist: list[str]) -> ConceptLegalityResult:
        """Evaluate ``problem`` against ``checklist``."""
        # Backwards compatibility: only declared problem sets are inspected.
        if not is_problem_set(problem):
            return ConceptLegalityResult(findings=[])

        concept = problem.metadata.concept
        # ``is_problem_set`` guarantees this, but keep mypy/readers honest.
        if concept is None:  # pragma: no cover - defensive
            return ConceptLegalityResult(findings=[])

        known = curriculum.known_set(checklist)
        boundary = curriculum.frontier(checklist)
        declared = set(concept.assumed_known) | {concept.new_concept}
        required = required_concepts(problem)

        findings: list[ConceptFinding] = []

        # Defensive re-check: the schema already forbids an empty
        # ``assumed_known``, but a gate must not rely on the schema alone.
        if not concept.assumed_known:
            findings.append(
                ConceptFinding(
                    ConceptConcern.EMPTY_ASSUMED_KNOWN,
                    (
                        "assumed_known is empty: a problem set must combine the "
                        "new concept with at least one already-known concept"
                    ),
                    fatal=True,
                )
            )

        if concept.new_concept in known:
            findings.append(
                ConceptFinding(
                    ConceptConcern.NEW_CONCEPT_KNOWN,
                    (
                        f"new_concept {concept.new_concept!r} is already in the "
                        "checklist; the new concept must be unknown to the learner"
                    ),
                    fatal=True,
                )
            )

        if boundary is None:
            # The learner knows the whole ladder: nothing is above the frontier,
            # so every concept is permitted.
            forbidden_required: set[str] = set()
        else:
            forbidden_required = {
                tag for tag in required if tag not in known and tag != concept.new_concept
            }

        if forbidden_required:
            findings.append(
                ConceptFinding(
                    ConceptConcern.ABOVE_FRONTIER,
                    (
                        "reference requires concept(s) the learner has not reached: "
                        f"{sorted(forbidden_required)} (frontier stage {boundary})"
                    ),
                    fatal=True,
                )
            )

        # Known concepts the reference uses but the pset did not declare it
        # combines. Legal to use, worth flagging for review.
        undeclared = sorted(
            tag for tag in required if tag in known and tag not in declared
        )
        if undeclared:
            findings.append(
                ConceptFinding(
                    ConceptConcern.NOT_DECLARED,
                    (
                        "reference uses known concept(s) not declared in the pair: "
                        f"{undeclared}; declare them in assumed_known to make the "
                        "combination explicit"
                    ),
                    fatal=False,
                )
            )

        return ConceptLegalityResult(findings=findings)
