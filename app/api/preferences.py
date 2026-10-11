"""Learner preferences: the known-concepts checklist.

The checklist is the explicit, user-controlled "known" side of the concept
ladder (spec S3). CPractice never guesses it. It is persisted through the
existing ``settings`` key/value table so no new storage is introduced.

Tags are validated against :func:`app.services.curriculum.concept_tags`:
an unknown tag has no stage and therefore no position on the ladder, so it is
rejected with 422 rather than silently stored.
"""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services import curriculum

router = APIRouter(prefix="/preferences", tags=["preferences"])

#: Key used in the ``settings`` table.
_KNOWN_CONCEPTS_KEY = "known_concepts"


class KnownConceptsPayload(BaseModel):
    """The checklist as sent by the client."""

    known_concepts: list[str] = Field(default_factory=list, max_length=64)


class KnownConceptsStore:
    """Persists the checklist in the ``settings`` key/value table.

    Reading a missing key yields an empty checklist, which is a valid starting
    state (frontier stage 0).
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self) -> list[str]:
        row = self._connection.execute(
            "SELECT value FROM settings WHERE key = ?", (_KNOWN_CONCEPTS_KEY,)
        ).fetchone()
        if row is None:
            return []
        try:
            stored = json.loads(row["value"])
        except (TypeError, ValueError):
            # A corrupt value must not crash practice; start from empty.
            return []
        if not isinstance(stored, list):
            return []
        return [tag for tag in stored if isinstance(tag, str)]

    def set(self, known_concepts: list[str]) -> list[str]:
        # Deduplicate while preserving order; a set is what the ladder uses.
        ordered = list(dict.fromkeys(known_concepts))
        self._connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_KNOWN_CONCEPTS_KEY, json.dumps(ordered)),
        )
        return ordered


def _store(request: Request) -> KnownConceptsStore:
    return KnownConceptsStore(request.app.state.database.connect())


def _validate_tags(tags: list[str]) -> list[str]:
    """Reject tags outside the concept ladder with 422."""
    unknown = curriculum.unknown_concepts(tags)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                "unknown concept tag(s): "
                f"{unknown}; valid tags are {list(curriculum.concept_tags())}"
            ),
        )
    return tags


def _state(checklist: list[str]) -> dict:
    """Checklist plus the frontier it implies, so the UI can show progress."""
    return {
        "known_concepts": checklist,
        "frontier": curriculum.frontier(checklist),
        "known_stages": sorted(
            {curriculum.stage_index_for_concept(tag) for tag in checklist}
            - {None}
        ),
    }


@router.get("/known-concepts")
def get_known_concepts(request: Request) -> dict:
    """Return the stored checklist and the frontier it implies."""
    return _state(_store(request).get())


@router.put("/known-concepts")
def put_known_concepts(request: Request, body: KnownConceptsPayload) -> dict:
    """Replace the checklist. Unknown tags are rejected with 422."""
    tags = _validate_tags(body.known_concepts)
    return _state(_store(request).set(tags))
