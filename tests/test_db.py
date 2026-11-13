import sqlite3
from pathlib import Path

import pytest

from niff.db import Migration, connect, load_migrations, migrate, schema_version


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_migrate_fresh_database_creates_tables(db_path: Path) -> None:
    conn = connect(db_path)

    applied = migrate(conn)

    assert applied == len(load_migrations())
    assert schema_version(conn) == len(load_migrations())
    assert {"accounts", "sync_state"} <= table_names(conn)


def test_migrate_twice_is_a_no_op(conn: sqlite3.Connection) -> None:
    version = schema_version(conn)

    assert migrate(conn) == 0
    assert schema_version(conn) == version


def test_failed_migration_rolls_back_and_keeps_version(db_path: Path) -> None:
    conn = connect(db_path)
    good = Migration(1, "0001_good.sql", "CREATE TABLE good (a INTEGER) STRICT;")
    bad = Migration(2, "0002_bad.sql", "CREATE TABLE half_done (a INTEGER); SELECT * FROM nope;")

    with pytest.raises(RuntimeError, match=r"0002_bad\.sql"):
        migrate(conn, [good, bad])

    assert schema_version(conn) == 1
    assert "good" in table_names(conn)
    assert "half_done" not in table_names(conn)
    assert not conn.in_transaction


def test_connection_pragmas(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_strict_table_rejects_wrong_type(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO accounts (ynab_account_id, name, type, on_budget, balance, updated_at)"
            " VALUES ('acc-1', 'Checking', 'checking', 1, 'not a number', '2026-01-01')"
        )
