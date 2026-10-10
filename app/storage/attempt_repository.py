"""Attempt and progress persistence.

Records every graded attempt and its per-test results so a learner can review
history and the system can later target weak topics. Only **safe diagnostics**
are stored: hidden expected output is never written here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.grading import GradingReport
from app.schemas.problem import Problem
from app.storage.database import Database


@dataclass(frozen=True)
class AttemptRecord:
    """A stored attempt summary."""

    id: int
    problem_id: str
    created_at: str
    compilation_ok: bool
    passed: int
    total: int
    verdict: str
    duration_ms: int
    hints_used: int

    @property
    def succeeded(self) -> bool:
        return self.total > 0 and self.passed == self.total


class AttemptRepository:
    """Reads and writes attempt history."""

    def __init__(self, database: Database) -> None:
        self.database = database

    # -- writing -----------------------------------------------------------

    def record(
        self,
        report: GradingReport,
        *,
        problem_id: str,
        hints_used: int = 0,
        verdict: str = "",
    ) -> int:
        """Persist a graded attempt plus its per-test results. Returns its id."""
        duration_ms = sum(t.duration_ms for t in report.tests) + report.compilation.duration_ms
        resolved_verdict = verdict or _verdict(report)

        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO attempts
                    (problem_id, compilation_ok, passed, total, verdict, duration_ms, hints_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    problem_id,
                    1 if report.compilation.success else 0,
                    report.passed_count,
                    report.total_count,
                    resolved_verdict,
                    duration_ms,
                    hints_used,
                ),
            )
            attempt_id = int(cursor.lastrowid)

            connection.executemany(
                """
                INSERT INTO test_results
                    (attempt_id, test_id, category, visibility, duration_ms, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        attempt_id,
                        test.test_id,
                        test.category.value,
                        test.visibility,
                        test.duration_ms,
                        # Never store detail for hidden tests.
                        test.detail if test.visibility == "public" else "",
                    )
                    for test in report.tests
                ],
            )

        return attempt_id

    # -- reading -----------------------------------------------------------

    def recent(self, *, limit: int = 20, problem_id: str | None = None) -> list[AttemptRecord]:
        """Return recent attempts, newest first."""
        sql = "SELECT * FROM attempts"
        params: list[Any] = []
        if problem_id:
            sql += " WHERE problem_id = ?"
            params.append(problem_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))

        rows = self.database.connect().execute(sql, params).fetchall()
        return [_row_to_attempt(row) for row in rows]

    def get(self, attempt_id: int) -> AttemptRecord | None:
        row = (
            self.database.connect()
            .execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,))
            .fetchone()
        )
        return _row_to_attempt(row) if row else None

    def test_results(self, attempt_id: int) -> list[dict[str, Any]]:
        rows = (
            self.database.connect()
            .execute(
                "SELECT test_id, category, visibility, duration_ms, detail "
                "FROM test_results WHERE attempt_id = ? ORDER BY id",
                (attempt_id,),
            )
            .fetchall()
        )
        return [dict(row) for row in rows]

    # -- progress ----------------------------------------------------------

    def progress(self) -> dict[str, Any]:
        """Summarise practice history in observed, defensible terms."""
        connection = self.database.connect()

        totals = connection.execute(
            """
            SELECT
                COUNT(*)                                AS attempts,
                COUNT(DISTINCT problem_id)              AS distinct_problems,
                SUM(CASE WHEN total > 0 AND passed = total THEN 1 ELSE 0 END) AS solved,
                COALESCE(SUM(passed), 0)                AS tests_passed,
                COALESCE(SUM(total), 0)                 AS tests_total
            FROM attempts
            """
        ).fetchone()

        # Weak topics: topics with the most failing attempts. Joined from the
        # problems index because topics are stored there.
        weak = connection.execute(
            """
            SELECT p.topics AS topics, COUNT(*) AS failures
            FROM attempts a
            JOIN problems p ON p.id = a.problem_id
            WHERE a.total > 0 AND a.passed < a.total
            GROUP BY p.topics
            ORDER BY failures DESC
            LIMIT 10
            """
        ).fetchall()

        by_category = connection.execute(
            """
            SELECT tr.category AS category, COUNT(*) AS n
            FROM test_results tr
            WHERE tr.category != 'passed'
            GROUP BY tr.category
            ORDER BY n DESC
            """
        ).fetchall()

        tests_total = int(totals["tests_total"] or 0)
        tests_passed = int(totals["tests_passed"] or 0)

        return {
            "attempts": int(totals["attempts"] or 0),
            "distinct_problems": int(totals["distinct_problems"] or 0),
            "problems_solved": int(totals["solved"] or 0),
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            # Explicitly a pass rate over observed tests, not an ability claim.
            "test_pass_rate": round(tests_passed / tests_total, 3) if tests_total else None,
            "failure_categories": {row["category"]: int(row["n"]) for row in by_category},
            "weak_topics": [
                {"topics": [t for t in (row["topics"] or "").split(",") if t],
                 "failures": int(row["failures"])}
                for row in weak
            ],
        }


def _verdict(report: GradingReport) -> str:
    if not report.compilation.success:
        return "compilation_failed"
    if report.all_passed:
        return "passed"
    if report.passed_count == 0:
        return "all_failed"
    return "partial"


def _row_to_attempt(row) -> AttemptRecord:
    return AttemptRecord(
        id=int(row["id"]),
        problem_id=row["problem_id"],
        created_at=row["created_at"],
        compilation_ok=bool(row["compilation_ok"]),
        passed=int(row["passed"]),
        total=int(row["total"]),
        verdict=row["verdict"],
        duration_ms=int(row["duration_ms"]),
        hints_used=int(row["hints_used"]),
    )


class ProblemIndex:
    """Keeps the ``problems`` table in step with the file repository."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, problem: Problem, package_path: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO problems
                    (id, version, title, difficulty, topics, status, test_count, package_path, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    version      = excluded.version,
                    title        = excluded.title,
                    difficulty   = excluded.difficulty,
                    topics       = excluded.topics,
                    status       = excluded.status,
                    test_count   = excluded.test_count,
                    package_path = excluded.package_path,
                    updated_at   = datetime('now')
                """,
                (
                    problem.id,
                    problem.metadata.version,
                    problem.title,
                    problem.metadata.difficulty.value,
                    ",".join(problem.metadata.topics),
                    problem.metadata.status.value,
                    len(problem.tests),
                    package_path,
                ),
            )

    def sync(self, problems: list[Problem], package_paths: dict[str, str]) -> int:
        """Index every problem. Returns the number written."""
        count = 0
        for problem in problems:
            path = package_paths.get(problem.id, "")
            self.upsert(problem, path)
            count += 1
        return count

    def all(self) -> list[dict[str, Any]]:
        rows = self.database.connect().execute(
            "SELECT * FROM problems ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]
