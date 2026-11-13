"""Typed reads and writes for the tables in the database. No ORM: plain SQL."""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from niff.db import transaction


@dataclass(frozen=True)
class Account:
    ynab_account_id: str
    name: str
    type: str
    on_budget: bool
    closed: bool
    deleted: bool
    balance: int  # milliunits


@dataclass(frozen=True)
class SyncState:
    source: str
    server_knowledge: int | None
    last_synced_at: datetime | None


def _to_text(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat()


def upsert_accounts(conn: sqlite3.Connection, accounts: Iterable[Account], now: datetime) -> None:
    """Insert accounts, or update existing ones matched by YNAB account ID."""
    updated_at = _to_text(now)
    rows = [
        (
            a.ynab_account_id,
            a.name,
            a.type,
            int(a.on_budget),
            int(a.closed),
            int(a.deleted),
            a.balance,
            updated_at,
        )
        for a in accounts
    ]
    with transaction(conn):
        conn.executemany(
            """
            INSERT INTO accounts
                (ynab_account_id, name, type, on_budget, closed, deleted, balance, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ynab_account_id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                on_budget = excluded.on_budget,
                closed = excluded.closed,
                deleted = excluded.deleted,
                balance = excluded.balance,
                updated_at = excluded.updated_at
            """,
            rows,
        )


def list_accounts(conn: sqlite3.Connection) -> list[Account]:
    """Open, non-deleted accounts, ordered by name."""
    rows: list[sqlite3.Row] = conn.execute(
        """
        SELECT ynab_account_id, name, type, on_budget, closed, deleted, balance
        FROM accounts
        WHERE closed = 0 AND deleted = 0
        ORDER BY name
        """
    ).fetchall()
    return [
        Account(
            ynab_account_id=row["ynab_account_id"],
            name=row["name"],
            type=row["type"],
            on_budget=bool(row["on_budget"]),
            closed=bool(row["closed"]),
            deleted=bool(row["deleted"]),
            balance=row["balance"],
        )
        for row in rows
    ]


def get_sync_state(conn: sqlite3.Connection, source: str) -> SyncState:
    """The stored cursor for a source, or an empty state if it has never synced."""
    row: sqlite3.Row | None = conn.execute(
        "SELECT server_knowledge, last_synced_at FROM sync_state WHERE source = ?", (source,)
    ).fetchone()
    if row is None:
        return SyncState(source=source, server_knowledge=None, last_synced_at=None)
    synced_at: str | None = row["last_synced_at"]
    return SyncState(
        source=source,
        server_knowledge=row["server_knowledge"],
        last_synced_at=datetime.fromisoformat(synced_at) if synced_at else None,
    )


def set_sync_state(
    conn: sqlite3.Connection, source: str, server_knowledge: int, synced_at: datetime
) -> None:
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO sync_state (source, server_knowledge, last_synced_at)
            VALUES (?, ?, ?)
            ON CONFLICT (source) DO UPDATE SET
                server_knowledge = excluded.server_knowledge,
                last_synced_at = excluded.last_synced_at
            """,
            (source, server_knowledge, _to_text(synced_at)),
        )
