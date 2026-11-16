"""Typed reads and writes for the tables in the database. No ORM: plain SQL.

Write functions don't open transactions themselves: the caller wraps them in
``niff.db.transaction()``, so several writes can commit or roll back together.
"""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime


@dataclass(frozen=True)
class Plan:
    """A YNAB plan (formerly "budget")."""

    id: str  # YNAB's plan ID
    name: str


@dataclass(frozen=True)
class PlanCursor:
    """Where a plan's last sync left off. ``server_knowledge`` is None before the first sync."""

    server_knowledge: int | None
    last_synced_at: datetime | None


@dataclass(frozen=True)
class Account:
    plan_id: str  # YNAB's plan ID
    ynab_account_id: str
    name: str
    type: str
    on_budget: bool
    closed: bool
    deleted: bool
    balance: int  # milliunits


def _to_text(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat()


def _from_text(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _require_transaction(conn: sqlite3.Connection) -> None:
    if not conn.in_transaction:
        raise RuntimeError("store writes must run inside niff.db.transaction()")


def upsert_plans(conn: sqlite3.Connection, plans: Iterable[Plan]) -> None:
    """Insert plans, or update their names. Cursors are left untouched."""
    _require_transaction(conn)
    conn.executemany(
        """
        INSERT INTO ynab_plans (ynab_plan_id, name) VALUES (?, ?)
        ON CONFLICT (ynab_plan_id) DO UPDATE SET name = excluded.name
        """,
        [(p.id, p.name) for p in plans],
    )


@dataclass(frozen=True)
class StoredPlan:
    id: str  # YNAB's plan ID
    name: str
    last_synced_at: datetime | None


def list_plans(conn: sqlite3.Connection) -> list[StoredPlan]:
    """Every plan that has been synced, in no particular order."""
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT ynab_plan_id, name, last_synced_at FROM ynab_plans"
    ).fetchall()
    return [
        StoredPlan(
            id=row["ynab_plan_id"],
            name=row["name"],
            last_synced_at=_from_text(row["last_synced_at"]),
        )
        for row in rows
    ]


def get_plan_cursor(conn: sqlite3.Connection, plan_id: str) -> PlanCursor:
    row: sqlite3.Row | None = conn.execute(
        "SELECT server_knowledge, last_synced_at FROM ynab_plans WHERE ynab_plan_id = ?",
        (plan_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown plan: {plan_id}")
    return PlanCursor(
        server_knowledge=row["server_knowledge"],
        last_synced_at=_from_text(row["last_synced_at"]),
    )


def set_plan_cursor(
    conn: sqlite3.Connection, plan_id: str, server_knowledge: int, synced_at: datetime
) -> None:
    _require_transaction(conn)
    updated = conn.execute(
        """
        UPDATE ynab_plans SET server_knowledge = ?, last_synced_at = ?
        WHERE ynab_plan_id = ?
        """,
        (server_knowledge, _to_text(synced_at), plan_id),
    ).rowcount
    if updated != 1:
        raise KeyError(f"unknown plan: {plan_id}")


def upsert_accounts(conn: sqlite3.Connection, accounts: Iterable[Account], now: datetime) -> None:
    """Insert accounts, or update existing ones matched by YNAB account ID.

    Each account's plan must already exist (see ``upsert_plans``).
    """
    _require_transaction(conn)
    updated_at = _to_text(now)
    rows = [
        (
            a.plan_id,
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
    conn.executemany(
        """
        INSERT INTO accounts
            (plan_id, ynab_account_id, name, type, on_budget, closed, deleted, balance,
             updated_at)
        VALUES ((SELECT id FROM ynab_plans WHERE ynab_plan_id = ?), ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (ynab_account_id) DO UPDATE SET
            plan_id = excluded.plan_id,
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
    """Open, non-deleted accounts, ordered by plan name then account name."""
    rows: list[sqlite3.Row] = conn.execute(
        """
        SELECT p.ynab_plan_id, a.ynab_account_id, a.name, a.type, a.on_budget, a.closed,
               a.deleted, a.balance
        FROM accounts AS a
        JOIN ynab_plans AS p ON p.id = a.plan_id
        WHERE a.closed = 0 AND a.deleted = 0
        ORDER BY p.name, a.name
        """
    ).fetchall()
    return [
        Account(
            plan_id=row["ynab_plan_id"],
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


def record_balances(conn: sqlite3.Connection, plan_id: str, day: date, now: datetime) -> int:
    """Save each open account's current balance as the plan's balance for ``day``.

    Run after ``upsert_accounts``. Rows already saved for ``day`` are overwritten, so a day keeps
    the last balance seen. An account closed or deleted since loses its row for ``day``, so the
    day's history matches the current accounts. Returns how many balances were saved.
    """
    _require_transaction(conn)
    conn.execute(
        """
        DELETE FROM balance_history
        WHERE date = ? AND account_id IN (
            SELECT a.id FROM accounts AS a JOIN ynab_plans AS p ON p.id = a.plan_id
            WHERE p.ynab_plan_id = ? AND (a.closed = 1 OR a.deleted = 1)
        )
        """,
        (day.isoformat(), plan_id),
    )
    return conn.execute(
        """
        INSERT INTO balance_history (account_id, date, balance, source, recorded_at)
        SELECT a.id, ?, a.balance, a.source, ?
        FROM accounts AS a JOIN ynab_plans AS p ON p.id = a.plan_id
        WHERE p.ynab_plan_id = ? AND a.closed = 0 AND a.deleted = 0
        ON CONFLICT (account_id, date) DO UPDATE SET
            balance = excluded.balance,
            source = excluded.source,
            recorded_at = excluded.recorded_at
        """,
        (day.isoformat(), _to_text(now), plan_id),
    ).rowcount


@dataclass(frozen=True)
class PlanDayTotal:
    plan_id: str  # YNAB's plan ID
    day: date
    total: int  # milliunits: sum of the plan's recorded balances that day


def list_plan_day_totals(conn: sqlite3.Connection) -> list[PlanDayTotal]:
    """Each plan's total for every day it has recorded balances, ordered by day."""
    rows: list[sqlite3.Row] = conn.execute(
        """
        SELECT p.ynab_plan_id, h.date, SUM(h.balance) AS total
        FROM balance_history AS h
        JOIN accounts AS a ON a.id = h.account_id
        JOIN ynab_plans AS p ON p.id = a.plan_id
        GROUP BY p.ynab_plan_id, h.date
        ORDER BY h.date, p.ynab_plan_id
        """
    ).fetchall()
    return [
        PlanDayTotal(
            plan_id=row["ynab_plan_id"], day=date.fromisoformat(row["date"]), total=row["total"]
        )
        for row in rows
    ]
