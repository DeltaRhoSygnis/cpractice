"""Tests for the problem-package import endpoint.

An import must survive the exact same gauntlet an AI-generated package faces:
the schemas reject shape violations, the quality gate rejects weak/incorrect
content, and only valid packages are written to disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

REFERENCE_OK = """\
#include <stdio.h>
int main(void){int a,b;if(scanf("%d %d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}
"""


def _package(**overrides) -> dict:
    package = {
        "id": "import-add-two",
        "version": 1,
        "title": "Imported: Add Two Numbers",
        "language": "c",
        "difficulty": "beginner",
        "status": "draft",
        "entrypoint": "main.c",
        "statement_md": "# Task\n\nRead two integers and print their sum.",
        "starter_code": "int main(void){return 0;}",
        "reference_solution": REFERENCE_OK,
        "tests": [
            {"id": "a", "name": "A", "stdin": "1 2\n", "expected_stdout": "3\n"},
            {"id": "b", "name": "B", "stdin": "-1 -2\n", "expected_stdout": "-3\n"},
            {"id": "c", "name": "C", "visibility": "hidden", "stdin": "0 0\n", "expected_stdout": "0\n"},
            {"id": "d", "name": "D", "visibility": "hidden", "stdin": "1000 2000\n", "expected_stdout": "3000\n"},
        ],
        "hints": [{"level": i, "text": f"hint {i}"} for i in range(1, 6)],
    }
    package.update(overrides)
    return package


def _import(client: TestClient, package: dict, overwrite: bool = False):
    return client.post(
        "/api/problems/import",
        json={"package": package, "overwrite": overwrite},
    )


def _make_client(tmp_path: Path) -> TestClient:
    app = create_app(make_settings(tmp_path))
    return TestClient(app)


def test_valid_package_imports_and_round_trips(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        response = _import(client, _package())

        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] is True
        assert body["status"] == "validated"

        # Same on-disk layout the pipeline produces for generated problems.
        package_dir = tmp_path / "problems" / "import-add-two"
        assert (package_dir / "problem.json").is_file()
        assert (package_dir / "statement.md").is_file()
        assert (package_dir / "reference" / "main.c").is_file()
        assert (package_dir / "quality_report.json").is_file()

        stored = json.loads((package_dir / "problem.json").read_text())
        assert stored["tests"][2]["visibility"] == "hidden"

        # The package must reload through the public API afterwards.
        listed = {p["id"] for p in client.get("/api/problems").json()["problems"]}
        assert "import-add-two" in listed


def test_package_without_reference_is_rejected_and_not_written(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        response = _import(client, _package(reference_solution=""))

        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] is False
        codes = {f["code"] for f in body["errors"]}
        assert "missing-reference" in codes
        assert not (tmp_path / "problems" / "import-add-two").exists()


def test_package_with_too_few_hidden_tests_is_rejected(tmp_path: Path) -> None:
    tests = _package()["tests"][:2]  # both public, no hidden test
    with _make_client(tmp_path) as client:
        body = _import(client, _package(tests=tests)).json()
        codes = {f["code"] for f in body["errors"]}
        assert "too-few-hidden-tests" in codes


def test_invalid_payload_is_422_not_silently_accepted(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        response = _import(client, _package(id="has spaces"))
        assert response.status_code == 422


def test_duplicate_import_conflicts_then_overwrite_wins(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        assert _import(client, _package()).json()["accepted"] is True

        conflict = _import(client, _package())
        assert conflict.status_code == 409

        replaced = _import(client, _package(title="Second Edit"), overwrite=True)
        assert replaced.status_code == 200
        assert replaced.json()["accepted"] is True
