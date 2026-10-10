"""Tests for the SQLite database layer."""

from __future__ import annotations

from pathlib import Path

from app.storage.database import SCHEMA_VERSION, Database


def test_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "cpractice.db"

    Database(path)

    assert path.is_file()


def test_schema_version_is_recorded(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")

    assert database.schema_version == SCHEMA_VERSION


def test_expected_tables_exist(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")

    rows = database.connect().execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {row["name"] for row in rows}

    assert {"problems", "attempts", "test_results", "provider_usage", "settings"} <= names


def test_reopening_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"

    Database(path)
    second = Database(path)

    assert second.schema_version == SCHEMA_VERSION


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")

    connection = database.connect()
    row = connection.execute("PRAGMA foreign_keys").fetchone()

    assert row[0] == 1


def test_wal_mode_is_enabled(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")

    row = database.connect().execute("PRAGMA journal_mode").fetchone()

    assert row[0].lower() == "wal"


def test_transaction_commits(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")

    with database.transaction() as connection:
        connection.execute("INSERT INTO settings (key, value) VALUES ('a', '1')")

    row = database.connect().execute("SELECT value FROM settings WHERE key='a'").fetchone()
    assert row["value"] == "1"


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")

    try:
        with database.transaction() as connection:
            connection.execute("INSERT INTO settings (key, value) VALUES ('b', '2')")
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    row = database.connect().execute("SELECT value FROM settings WHERE key='b'").fetchone()
    assert row is None


def test_cascade_delete_removes_test_results(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite")
    connection = database.connect()

    with database.transaction() as c:
        c.execute(
            "INSERT INTO problems (id, title, difficulty, status, package_path) "
            "VALUES ('p', 'P', 'beginner', 'validated', '/x')"
        )
        c.execute(
            "INSERT INTO attempts (problem_id, verdict) VALUES ('p', 'passed')"
        )
        attempt_id = c.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
        c.execute(
            "INSERT INTO test_results (attempt_id, test_id, category, visibility) "
            "VALUES (?, 't', 'passed', 'public')",
            (attempt_id,),
        )

    with database.transaction() as c:
        c.execute("DELETE FROM attempts WHERE id = ?", (attempt_id,))

    remaining = connection.execute("SELECT COUNT(*) AS n FROM test_results").fetchone()
    assert remaining["n"] == 0
