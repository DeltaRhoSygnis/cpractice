"""SQLite database access.

A small, dependency-free persistence layer over the standard library ``sqlite3``.
Design notes:

* The database stores **metadata only**. Problem packages stay as files; the
  database indexes them and records attempts and provider usage (section 16 of
  the architecture spec).
* Secrets are never stored here. API keys live in the environment.
* Connections are per-thread because ``sqlite3`` connections are not shareable
  across threads and the app runs request handlers concurrently.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Schema version, recorded in ``PRAGMA user_version`` so migrations can be
# applied incrementally later.
SCHEMA_VERSION = 1

#: Additive columns applied to the base schema after creation. Each entry is
#: ``(table, column, declaration)``. They are applied idempotently (guarded by a
#: ``PRAGMA table_info`` check), so both a fresh database and a pre-existing one
#: converge on the same shape without dropping or altering existing columns.
#: The prediction (`spec S6`) stores the learner's hypothesis; it is never
#: scored and is nullable so every existing row reads back as NULL.
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("attempts", "predicted_stdout", "TEXT"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS problems (
    id            TEXT PRIMARY KEY,
    version       INTEGER NOT NULL DEFAULT 1,
    title         TEXT NOT NULL,
    difficulty    TEXT NOT NULL,
    topics        TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL,
    test_count    INTEGER NOT NULL DEFAULT 0,
    package_path  TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attempts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id        TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    compilation_ok    INTEGER NOT NULL DEFAULT 0,
    passed            INTEGER NOT NULL DEFAULT 0,
    total             INTEGER NOT NULL DEFAULT 0,
    verdict           TEXT NOT NULL,
    duration_ms       INTEGER NOT NULL DEFAULT 0,
    hints_used        INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attempts_problem ON attempts(problem_id, created_at DESC);

CREATE TABLE IF NOT EXISTS test_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  INTEGER NOT NULL,
    test_id     TEXT NOT NULL,
    category    TEXT NOT NULL,
    visibility  TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    -- Safe diagnostics only; never hidden expected output.
    detail      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (attempt_id) REFERENCES attempts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_test_results_attempt ON test_results(attempt_id);

CREATE TABLE IF NOT EXISTS provider_usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    operation      TEXT NOT NULL,
    status         TEXT NOT NULL,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    detail         TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_usage_created ON provider_usage(created_at DESC);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    """Owns the SQLite file and hands out connections."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._initialise()

    # -- connections -------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """Return this thread's connection, creating it on first use."""
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(
                self.path,
                # Handlers may run on different threads; the connection itself
                # stays per-thread.
                check_same_thread=True,
                isolation_level=None,  # explicit transactions
            )
            connection.row_factory = sqlite3.Row
            # Enforce foreign keys; off by default in SQLite.
            connection.execute("PRAGMA foreign_keys = ON")
            # Better concurrency for a local app.
            connection.execute("PRAGMA journal_mode = WAL")
            self._local.connection = connection
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block in a transaction, rolling back on error."""
        connection = self.connect()
        connection.execute("BEGIN")
        try:
            yield connection
        except Exception:
            connection.execute("ROLLBACK")
            raise
        else:
            connection.execute("COMMIT")

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None

    # -- setup -------------------------------------------------------------

    def _initialise(self) -> None:
        connection = self.connect()
        connection.executescript(_SCHEMA)
        self._apply_migrations(connection)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _apply_migrations(self, connection: sqlite3.Connection) -> None:
        """Apply additive columns idempotently.

        ``executescript`` above already creates any missing table with the base
        schema, but a table that existed *before* a column was added is left
        untouched by ``CREATE TABLE IF NOT EXISTS``. This walks each additive
        column and adds it only when absent, so running the migration twice is a
        no-op and an old database keeps working.
        """
        for table, column, declaration in _ADDITIVE_COLUMNS:
            existing = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                # ``table``/``column``/``declaration`` are module constants, not
                # user input; identifiers cannot be parameterised anyway.
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
                )

    @property
    def schema_version(self) -> int:
        row = self.connect().execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row else 0
