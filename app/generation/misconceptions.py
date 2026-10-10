"""Stable identifiers for pedagogical misconceptions.

The blueprint stage asks the model for ``likely_misconceptions``, and the model
answers in prose ("MIS-NO-LENGTH: using a separately computed length ..."). The
quality gate, however, checks *coverage* by matching a test's
``misconception_ids`` against the declared set. Prose statements make that
match impossible, so the warning ``misconceptions-untested`` would fire on every
generated package no matter how good the tests were.

This module bridges the two: it extracts a stable identifier from each declared
misconception so a test can reference it. A misconception that already carries
its own id (``MIS-...``) keeps it; otherwise a deterministic id is derived from
the text, so the mapping is reproducible across runs and cache hits.
"""

from __future__ import annotations

import re

from app.schemas.pedagogy import Pedagogy

#: An existing identifier at the start of a statement, e.g. ``MIS-OFF-BY-ONE:``.
_LEADING_ID = re.compile(r"^\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s*[:\-]\s*")

_MAX_ID_LENGTH = 48


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:_MAX_ID_LENGTH].rstrip("-")


def misconception_id(statement: str) -> str:
    """Return a stable id for one misconception statement.

    A statement that already begins with an identifier (the common case for the
    blueprint prompt) reuses it verbatim so the id lines up with whatever the
    model wrote into ``misconception_ids``. Otherwise a slug is derived from the
    first few meaningful words.
    """
    text = (statement or "").strip()
    match = _LEADING_ID.match(text)
    if match:
        return match.group(1)[:_MAX_ID_LENGTH].rstrip("-")

    slug = _slugify(text)
    if not slug:
        return "MIS-UNSPECIFIED"
    return f"MIS-{slug.upper()}"


def declared_misconception_ids(pedagogy: Pedagogy | None) -> list[str]:
    """Return the stable ids for every misconception a blueprint declares."""
    if pedagogy is None or not pedagogy.likely_misconceptions:
        return []

    ids: list[str] = []
    for statement in pedagogy.likely_misconceptions:
        identifier = misconception_id(statement)
        if identifier not in ids:
            ids.append(identifier)
    return ids
