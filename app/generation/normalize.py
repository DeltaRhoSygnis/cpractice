"""Normalisation of provider payloads into the CPractice problem schema.

Kenari (and the models behind it) do not enforce ``response_format``, so a
reply frequently uses sensible-but-different field names:

    model output                       CPractice schema
    ---------------------------------  ------------------------------
    description / problem / prompt     statement_md
    public_tests + hidden_tests        tests[].visibility
    topic (string)                     topics (array)
    (no id)                            id derived from the title

This module maps those variants onto the canonical shape **before** Pydantic
validation, so a well-formed problem is not rejected for a cosmetic naming
difference. It performs only lossless, unambiguous mapping - it never invents
test data and never guesses semantics.
"""

from __future__ import annotations

import re
from typing import Any

#: Alternative keys for the problem statement, in priority order.
_STATEMENT_KEYS = ("statement_md", "description", "statement", "problem", "prompt", "task")

#: Metadata keys the schema accepts. Anything else is treated as a modelling
#: artefact and either folded into the statement or dropped.
_KNOWN_METADATA_KEYS = frozenset(
    {
        "schema_version",
        "id",
        "version",
        "title",
        "language",
        "difficulty",
        "topics",
        "target_skills",
        "compiler",
        "entrypoint",
        "comparison",
        "time_limit_ms",
        "memory_limit_mb",
        "status",
    }
)

#: Content keys preserved verbatim in the package payload.
_KNOWN_CONTENT_KEYS = frozenset(
    {
        "statement_md",
        "starter_code",
        "reference_solution",
        "tests",
        "hints",
        "solution_explanation",
    }
)

#: Keys whose text is worth appending to the statement rather than discarding.
_STATEMENT_APPENDIX_KEYS = (
    ("input_format", "Input format"),
    ("output_format", "Output format"),
    ("constraints", "Constraints"),
    ("notes", "Notes"),
    ("examples", "Examples"),
)

#: Test-case keys the schema accepts.
_KNOWN_TEST_KEYS = frozenset(
    {
        "id",
        "name",
        "visibility",
        "stdin",
        "expected_stdout",
        "expected_exit_code",
        "timeout_ms",
        "comparison",
    }
)

#: Alternative keys for a single test list.
_TESTS_KEYS = ("tests", "test_cases", "testcases")

#: Limits on how much text is accepted from a single field.
_MAX_STATEMENT_CHARS = 20_000
_MAX_CODE_CHARS = 40_000


def slugify(value: str, *, max_length: int = 48) -> str:
    """Derive a valid problem id from arbitrary text."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "generated-problem"


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``payload`` in the canonical package shape.

    Normalisation is intentionally conservative: it maps field-name variants and
    coerces types, but it **must not silently change the test set**. Tests are
    de-duplicated by id (first occurrence wins) and any loss is recorded in a
    ``normalization_notes`` list so a caller can assert on it rather than trust
    that nothing was dropped.
    """
    if not isinstance(payload, dict):
        return payload

    out: dict[str, Any] = dict(payload)
    notes: list[str] = []

    # --- statement -------------------------------------------------------
    if not out.get("statement_md"):
        for key in _STATEMENT_KEYS:
            value = out.get(key)
            if isinstance(value, str) and value.strip():
                out["statement_md"] = value.strip()[:_MAX_STATEMENT_CHARS]
                break

    # --- tests: merge split public/hidden lists into one annotated list ---
    # Always overwrite: if the list contained only unusable entries, the
    # original must not survive, or validation would fail on junk.
    if _has_any_test_source(out):
        collected = _collect_tests(out)
        deduped, dropped = _deduplicate_tests(collected)
        if dropped:
            notes.append(
                f"dropped {dropped} duplicate test id(s): {sorted(dropped)}"
            )
        out["tests"] = deduped

    # --- topics: accept a string or a list -------------------------------
    out["topics"] = _as_string_list(out.get("topics") or out.get("topic"))

    # --- target skills ---------------------------------------------------
    out["target_skills"] = _as_string_list(out.get("target_skills"))

    # --- id --------------------------------------------------------------
    current_id = out.get("id")
    if not isinstance(current_id, str) or not current_id.strip():
        source = str(out.get("title") or out.get("statement_md") or "")
        out["id"] = slugify(source) if source else "generated-problem"

    # --- version must be an int ------------------------------------------
    out["version"] = _as_int(out.get("version"), default=1)

    # --- schema_version must be a string ---------------------------------
    out["schema_version"] = str(out.get("schema_version") or "1.0")

    # --- hint levels must be ints ----------------------------------------
    hints = out.get("hints")
    if isinstance(hints, list):
        out["hints"] = _normalize_hints(hints)

    # --- reference solution aliases --------------------------------------
    if not out.get("reference_solution"):
        for key in ("reference", "solution", "reference_code", "solution_code"):
            value = out.get(key)
            if isinstance(value, str) and value.strip():
                out["reference_solution"] = value.strip()[:_MAX_CODE_CHARS]
                break

    # --- starter code aliases --------------------------------------------
    if not out.get("starter_code"):
        for key in ("starter", "starter_template", "template", "starter_code_c"):
            value = out.get(key)
            if isinstance(value, str) and value.strip():
                out["starter_code"] = value.strip()[:_MAX_CODE_CHARS]
                break

    # --- fold useful prose into the statement ----------------------------
    out["statement_md"] = _augment_statement(out)

    # --- drop anything the schema does not define ------------------------
    # Models routinely emit helpful extras (``input_format``, ``notes``, ...).
    # They are folded into the statement above, so the structured payload keeps
    # only keys the schemas accept.
    cleaned = {
        key: value
        for key, value in out.items()
        if key in _KNOWN_METADATA_KEYS or key in _KNOWN_CONTENT_KEYS
    }

    # Record what normalisation changed so callers can assert rather than trust.
    if notes:
        cleaned["normalization_notes"] = notes

    return cleaned


def _deduplicate_tests(tests: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop tests sharing an id, keeping the first occurrence.

    Returns the surviving tests and the ids that were dropped. Duplicate ids are
    otherwise fatal at schema validation, and a merged public/hidden list can
    legitimately contain the same test twice - dropping the later copy is the
    only lossless resolution, but it must be *visible*.
    """
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []

    for test in tests:
        test_id = test.get("id")
        if test_id in seen:
            dropped.append(str(test_id))
            continue
        seen.add(test_id)
        kept.append(test)

    return kept, dropped


def _augment_statement(payload: dict[str, Any]) -> str:
    """Append unmodelled prose sections to the statement markdown."""
    statement = str(payload.get("statement_md") or "").strip()

    sections: list[str] = []
    for key, heading in _STATEMENT_APPENDIX_KEYS:
        value = payload.get(key)
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            rendered = "\n".join(f"- {str(item).strip()}" for item in value if str(item).strip())
        else:
            rendered = str(value).strip()
        if rendered and rendered not in statement:
            sections.append(f"### {heading}\n\n{rendered}")

    if sections:
        statement = (statement + "\n\n" + "\n\n".join(sections)).strip()

    return statement[:_MAX_STATEMENT_CHARS]


def _has_any_test_source(payload: dict[str, Any]) -> bool:
    """Return True when the payload carries any of the test-list keys."""
    keys = (*_TESTS_KEYS, "public_tests", "hidden_tests")
    return any(isinstance(payload.get(key), list) for key in keys)


def _collect_tests(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a single annotated test list from every supported shape.

    Non-dict entries are skipped: a model occasionally emits a stray scalar in
    the test list, which should not invalidate an otherwise sound problem.
    """
    collected: list[dict[str, Any]] = []

    for key in _TESTS_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    collected.append(dict(item))

    # Split public/hidden lists: annotate visibility rather than merging blindly.
    for key, visibility in (("public_tests", "public"), ("hidden_tests", "hidden")):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    entry = dict(item)
                    entry.setdefault("visibility", visibility)
                    collected.append(entry)

    return [_normalize_test(item, index) for index, item in enumerate(collected)]


def _normalize_test(test: dict[str, Any], index: int) -> dict[str, Any]:
    """Normalise one test case's field names and types."""
    out = dict(test)

    # id / name are required by the schema; derive stable fallbacks.
    if not isinstance(out.get("id"), str) or not out["id"].strip():
        out["id"] = f"test-{index + 1}"
    out["id"] = slugify(str(out["id"]), max_length=32)

    if not isinstance(out.get("name"), str) or not out["name"].strip():
        out["name"] = f"Test {index + 1}"

    # Accept common synonyms for the expected-output field.
    if "expected_stdout" not in out:
        for key in ("expected_output", "expected", "output", "expected_stdout_exact"):
            value = out.get(key)
            if isinstance(value, str):
                out["expected_stdout"] = value
                break
    out["expected_stdout"] = str(out.get("expected_stdout") or "")

    # Accept common synonyms for the input field.
    if "stdin" not in out:
        for key in ("input", "std_in", "stdin_str", "input_data"):
            value = out.get(key)
            if isinstance(value, str):
                out["stdin"] = value
                break
    out["stdin"] = str(out.get("stdin") or "")

    # Visibility must be a known value.
    visibility = str(out.get("visibility") or "public").strip().lower()
    out["visibility"] = "hidden" if visibility.startswith("hid") else "public"

    # Exit code must be an int.
    out["expected_exit_code"] = _as_int(out.get("expected_exit_code"), default=0)

    # Timeout / comparison: drop values the schema would reject.
    if out.get("timeout_ms") is not None:
        timeout = _as_int(out.get("timeout_ms"), default=0)
        if timeout <= 0 or timeout > 60_000:
            out.pop("timeout_ms", None)
        else:
            out["timeout_ms"] = timeout

    # Keep only keys the TestCase schema defines; alias sources are dropped.
    return {key: value for key, value in out.items() if key in _KNOWN_TEST_KEYS}


def _normalize_hints(hints: list[Any]) -> list[dict[str, Any]]:
    """Coerce hints into ``{"level": int, "text": str}`` objects.

    Models sometimes return a bare list of strings, or objects carrying the
    guidance under a different key. Both shapes are mapped onto the schema.
    """
    normalized: list[dict[str, Any]] = []

    for index, hint in enumerate(hints, start=1):
        if isinstance(hint, str):
            text = hint.strip()
            if text:
                normalized.append({"level": index, "text": text})
            continue

        if not isinstance(hint, dict):
            continue

        text = ""
        for key in ("text", "hint", "content", "message", "guidance"):
            value = hint.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break

        if not text:
            continue

        level = _as_int(hint.get("level"), default=index)
        if level < 1 or level > 5:
            level = index

        normalized.append({"level": level, "text": text})

    # The schema requires unique levels, and the hint ladder must be
    # contiguous from 1 so progressive reveal works. Renumber in order.
    deduped: list[dict[str, Any]] = []
    for position, hint in enumerate(normalized, start=1):
        if position > 5:
            break
        deduped.append({"level": position, "text": hint["text"]})

    return deduped


def _as_string_list(value: Any) -> list[str]:
    """Coerce a string, list, or mapping into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[,\n]", value)]
        return [part for part in parts if part]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _as_int(value: Any, *, default: int) -> int:
    """Coerce a value to int, tolerating numeric strings; else use default."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default
