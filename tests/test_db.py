import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from niff.db import Migration, connect, load_migrations, migrate, schema_version


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_migrate_fresh_database_creates_tables(db_path: Path) -> None:
    with closing(connect(db_path)) as conn:
        applied = migrate(conn)

        assert applied == len(load_migrations())
        assert schema_version(conn) == len(load_migrations())
        assert {"accounts", "ynab_plans"} <= table_names(conn)
        assert "sync_state" not in table_names(conn)


def test_migrate_twice_is_a_no_op(conn: sqlite3.Connection) -> None:
    version = schema_version(conn)

    assert migrate(conn) == 0
    assert schema_version(conn) == version


def test_failed_migration_rolls_back_and_keeps_version(db_path: Path) -> None:
    good = Migration(1, "0001_good.sql", "CREATE TABLE good (a INTEGER) STRICT;")
    bad = Migration(2, "0002_bad.sql", "CREATE TABLE half_done (a INTEGER); SELECT * FROM nope;")

    with closing(connect(db_path)) as conn:
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
            "INSERT INTO accounts (plan_id, ynab_account_id, name, type, on_budget, balance,"
            " updated_at) VALUES (1, 'acc-1', 'Checking', 'checking', 1, 'not a number',"
            " '2026-01-01')"
        )


def test_plans_migration_applies_on_top_of_existing_data(db_path: Path) -> None:
    first, *rest = load_migrations()
    with closing(connect(db_path)) as conn:
        migrate(conn, [first])
        conn.execute(
            "INSERT INTO accounts (ynab_account_id, name, type, on_budget, balance, updated_at)"
            " VALUES ('fake-checking', 'Everyday Checking', 'checking', 1, 100, '2026-01-01')"
        )
        conn.execute("INSERT INTO sync_state (source, server_knowledge) VALUES ('ynab', 100)")

        migrate(conn, [first, *rest])

        assert schema_version(conn) == len(load_migrations())
        assert "sync_state" not in table_names(conn)
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ynab_plans").fetchone()[0] == 0


def test_balance_history_migration_keeps_existing_accounts_and_cursor(db_path: Path) -> None:
    migrations = load_migrations()
    with closing(connect(db_path)) as conn:
        migrate(conn, migrations[:2])
        conn.execute(
            "INSERT INTO ynab_plans (ynab_plan_id, name, server_knowledge)"
            " VALUES ('fake-plan-id', 'Example Household', 100)"
        )
        conn.execute(
            "INSERT INTO accounts (plan_id, ynab_account_id, name, type, on_budget, balance,"
            " updated_at) VALUES (1, 'fake-checking', 'Everyday Checking', 'checking', 1, 100,"
            " '2026-01-01')"
        )

        migrate(conn, migrations)

        assert "balance_history" in table_names(conn)
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        assert conn.execute("SELECT server_knowledge FROM ynab_plans").fetchone()[0] == 100
