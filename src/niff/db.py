"""SQLite connections and schema migrations.

Migrations are numbered SQL files in ``niff/migrations`` (``0001_initial.sql``, ...). The applied
version is SQLite's ``PRAGMA user_version``. Each migration runs in its own transaction, so a
failure leaves the database at the previous version. Migrations only move forward.
"""

import re
import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection in SQLite's autocommit mode; use ``transaction()`` for writes."""
    conn = sqlite3.connect(path, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    """Run a block in one write transaction: commit on success, roll back on error."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def load_migrations() -> list[Migration]:
    """Read the bundled migration files, checking they are numbered 1, 2, 3... with no gaps."""
    migrations: list[Migration] = []
    for entry in files("niff").joinpath("migrations").iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match:
            migrations.append(Migration(int(match.group(1)), entry.name, entry.read_text()))
    migrations.sort(key=lambda m: m.version)
    versions = [m.version for m in migrations]
    if versions != list(range(1, len(migrations) + 1)):
        raise RuntimeError(f"migrations must be numbered 1..n without gaps, found {versions}")
    return migrations


def schema_version(conn: sqlite3.Connection) -> int:
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    return version


def migrate(conn: sqlite3.Connection, migrations: Sequence[Migration] | None = None) -> int:
    """Apply pending migrations in order. Returns how many were applied."""
    current = schema_version(conn)
    available = load_migrations() if migrations is None else migrations
    pending = [m for m in available if m.version > current]
    for m in pending:
        try:
            conn.executescript(
                f"BEGIN IMMEDIATE;\n{m.sql}\n;PRAGMA user_version = {m.version};\nCOMMIT;"
            )
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise RuntimeError(f"migration {m.name} failed: {exc}") from exc
    return len(pending)
