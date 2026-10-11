"""Tests for the known-concepts preferences API (spec S3)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.curriculum import concept_tags


def test_known_concepts_starts_empty(client: TestClient) -> None:
    response = client.get("/api/preferences/known-concepts")

    assert response.status_code == 200
    body = response.json()
    assert body["known_concepts"] == []
    assert body["frontier"] == 0


def test_known_concepts_round_trip(client: TestClient) -> None:
    checklist = ["expressions", "types", "input_output", "if_else", "boolean_expressions"]

    put = client.put(
        "/api/preferences/known-concepts", json={"known_concepts": checklist}
    )
    assert put.status_code == 200
    assert put.json()["known_concepts"] == checklist
    assert put.json()["frontier"] == 2

    get = client.get("/api/preferences/known-concepts")
    assert get.status_code == 200
    assert get.json()["known_concepts"] == checklist


def test_unknown_tag_is_rejected_with_422(client: TestClient) -> None:
    response = client.put(
        "/api/preferences/known-concepts",
        json={"known_concepts": ["arrays", "not_a_concept"]},
    )

    assert response.status_code == 422
    assert "not_a_concept" in response.json()["detail"]


def test_put_replaces_rather_than_appends(client: TestClient) -> None:
    client.put(
        "/api/preferences/known-concepts",
        json={"known_concepts": ["expressions", "types"]},
    )
    client.put(
        "/api/preferences/known-concepts", json={"known_concepts": ["input_output"]}
    )

    assert client.get("/api/preferences/known-concepts").json()["known_concepts"] == [
        "input_output"
    ]


def test_duplicate_tags_are_deduplicated(client: TestClient) -> None:
    response = client.put(
        "/api/preferences/known-concepts",
        json={"known_concepts": ["types", "types", "expressions"]},
    )

    assert response.json()["known_concepts"] == ["types", "expressions"]


def test_full_checklist_reports_no_frontier(client: TestClient) -> None:
    response = client.put(
        "/api/preferences/known-concepts",
        json={"known_concepts": list(concept_tags())},
    )

    assert response.status_code == 200
    assert response.json()["frontier"] is None
