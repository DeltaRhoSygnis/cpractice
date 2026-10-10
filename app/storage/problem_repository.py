"""Problem repository — loads problem packages from the filesystem.

A package directory has the canonical layout::

    <problems_dir>/<problem-id>/
        problem.json          # metadata + tests + hints
        statement.md          # problem statement
        starter/main.c        # starter code
        reference/main.c      # reference solution
        quality_report.json   # optional, written by the quality gate

Packages are validated on load. An invalid package is reported, never
silently accepted.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas.problem import CONTENT_KEYS, Problem, ProblemMetadata
from app.schemas.test_case import TestCase

METADATA_FILENAME = "problem.json"
STATEMENT_FILENAME = "statement.md"
STARTER_DIR = "starter"
REFERENCE_DIR = "reference"
QUALITY_REPORT_FILENAME = "quality_report.json"


class ProblemNotFoundError(LookupError):
    """Raised when a problem id has no package on disk."""


class ProblemValidationError(ValueError):
    """Raised when a package exists but fails schema validation."""


class ProblemRepository:
    """Reads problem packages from a root directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # -- paths -------------------------------------------------------------

    def package_dir(self, problem_id: str) -> Path:
        self._validate_id(problem_id)
        return self.root / problem_id

    def exists(self, problem_id: str) -> bool:
        return (self.package_dir(problem_id) / METADATA_FILENAME).is_file()

    # -- loading -----------------------------------------------------------

    def load(self, problem_id: str) -> Problem:
        """Load and validate one problem package."""
        package_dir = self.package_dir(problem_id)
        metadata_path = package_dir / METADATA_FILENAME

        if not metadata_path.is_file():
            raise ProblemNotFoundError(f"no package for problem '{problem_id}'")

        raw = json.loads(metadata_path.read_text(encoding="utf-8"))

        # problem.json holds both metadata and package content. Separate the
        # content keys before validating metadata, which forbids extras.
        metadata_raw = {
            key: value
            for key, value in raw.items()
            if key not in CONTENT_KEYS
        }

        try:
            metadata = ProblemMetadata.model_validate(metadata_raw)
            tests = [TestCase.model_validate(item) for item in raw.get("tests", [])]
            problem = Problem(
                metadata=metadata,
                statement_md=self._read_text(package_dir / STATEMENT_FILENAME),
                starter_code=self._read_optional(package_dir / STARTER_DIR / metadata.entrypoint),
                reference_solution=self._read_optional(
                    package_dir / REFERENCE_DIR / metadata.entrypoint
                ),
                tests=tests,
                hints=raw.get("hints", []),
                solution_explanation=raw.get("solution_explanation", ""),
            )
        except ValidationError as exc:
            raise ProblemValidationError(
                f"problem '{problem_id}' failed validation: {exc}"
            ) from exc

        return problem

    def list_ids(self) -> list[str]:
        """Return the ids of every package directory present."""
        if not self.root.is_dir():
            return []
        ids = [
            entry.name
            for entry in sorted(self.root.iterdir())
            if entry.is_dir() and (entry / METADATA_FILENAME).is_file()
        ]
        return [pid for pid in ids if self._is_valid_id(pid)]

    def load_all(self) -> list[Problem]:
        """Load every package, skipping (and reporting) invalid ones."""
        problems: list[Problem] = []
        for problem_id in self.list_ids():
            try:
                problems.append(self.load(problem_id))
            except (ProblemNotFoundError, ProblemValidationError, json.JSONDecodeError):
                continue
        return problems

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _read_text(path: Path) -> str:
        if not path.is_file():
            raise ProblemValidationError(f"missing required file: {path.name}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _read_optional(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    @staticmethod
    def _is_valid_id(problem_id: str) -> bool:
        return bool(problem_id) and problem_id[0].isalnum() and all(
            char.islower() or char.isdigit() or char == "-" for char in problem_id
        )

    @classmethod
    def _validate_id(cls, problem_id: str) -> None:
        # Reject traversal and absolute paths before touching the filesystem.
        if not cls._is_valid_id(problem_id):
            raise ProblemNotFoundError(f"invalid problem id: {problem_id!r}")
