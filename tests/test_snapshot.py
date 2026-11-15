import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from niff.config import Settings
from niff.db import open_database, transaction
from niff.main import create_app
from niff.snapshot import build_snapshot
from niff.store import Account, Plan, set_plan_cursor, upsert_accounts, upsert_plans

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

HOUSEHOLD = Plan(id="fake-plan-id", name="Example Household")
SIDE = Plan(id="fake-side-plan-id", name="Example Side Plan")
OLD = Plan(id="fake-old-plan-id", name="Example Household (Fresh Start)")

CHECKING = Account(
    plan_id=HOUSEHOLD.id,
    ynab_account_id="fake-checking",
    name="Everyday Checking",
    type="checking",
    on_budget=True,
    closed=False,
    deleted=False,
    balance=1_234_560,
)
CARD = replace(
    CHECKING, ynab_account_id="fake-card", name="Rewards Card", type="creditCard", balance=-45_000
)
BROKERAGE = replace(
    CHECKING,
    ynab_account_id="fake-brokerage",
    name="Brokerage",
    type="otherAsset",
    on_budget=False,
    balance=2_000_000,
)
SIDE_SAVINGS = replace(
    CHECKING,
    plan_id=SIDE.id,
    ynab_account_id="fake-side-savings",
    name="Side Savings",
    type="savings",
    balance=500_000,
)
OLD_CHECKING = replace(CHECKING, plan_id=OLD.id, ynab_account_id="fake-old-checking")
CLOSED = replace(CHECKING, ynab_account_id="fake-closed", name="Closed", closed=True)
DELETED = replace(CHECKING, ynab_account_id="fake-deleted", name="Deleted", deleted=True)


def seed(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        upsert_plans(conn, [HOUSEHOLD, SIDE, OLD])
        upsert_accounts(
            conn,
            [CHECKING, CARD, BROKERAGE, SIDE_SAVINGS, OLD_CHECKING, CLOSED, DELETED],
            NOW,
        )
        set_plan_cursor(conn, HOUSEHOLD.id, 100, NOW)


def test_empty_database_has_zero_net_worth(conn: sqlite3.Connection) -> None:
    snapshot = build_snapshot(conn, [HOUSEHOLD.id])

    assert (snapshot.net_worth, snapshot.plans, snapshot.accounts) == (0, [], [])


def test_net_worth_sums_open_accounts_across_configured_plans(conn: sqlite3.Connection) -> None:
    seed(conn)

    snapshot = build_snapshot(conn, [HOUSEHOLD.id, SIDE.id])

    household = 1_234_560 - 45_000 + 2_000_000  # card is negative; off-budget counts
    assert [(p.name, p.total) for p in snapshot.plans] == [
        ("Example Household", household),
        ("Example Side Plan", 500_000),
    ]
    assert snapshot.net_worth == household + 500_000


def test_closed_deleted_and_unconfigured_accounts_are_excluded(conn: sqlite3.Connection) -> None:
    seed(conn)

    snapshot = build_snapshot(conn, [HOUSEHOLD.id, SIDE.id])

    ids = {a.ynab_account_id for a in snapshot.accounts}
    assert ids == {"fake-checking", "fake-card", "fake-brokerage", "fake-side-savings"}
    assert OLD.id not in {p.id for p in snapshot.plans}


def test_plans_and_accounts_follow_configured_order(conn: sqlite3.Connection) -> None:
    seed(conn)

    snapshot = build_snapshot(conn, [SIDE.id, HOUSEHOLD.id])

    assert [p.id for p in snapshot.plans] == [SIDE.id, HOUSEHOLD.id]
    assert [a.name for a in snapshot.accounts] == [
        "Side Savings",
        "Brokerage",
        "Everyday Checking",
        "Rewards Card",
    ]


def test_configured_plan_not_yet_synced_is_skipped(conn: sqlite3.Connection) -> None:
    seed(conn)

    snapshot = build_snapshot(conn, ["fake-never-synced", HOUSEHOLD.id])

    assert [p.id for p in snapshot.plans] == [HOUSEHOLD.id]


def test_snapshot_endpoint_returns_integer_milliunits(tmp_path: Path) -> None:
    db_path = tmp_path / "niff.db"
    conn = open_database(db_path)
    try:
        seed(conn)
    finally:
        conn.close()
    settings = Settings(db_path=db_path, ynab_plan_ids=(HOUSEHOLD.id, SIDE.id))

    with TestClient(create_app(settings)) as client:
        body = client.get("/snapshot").json()

    assert body["net_worth"] == 3_689_560
    assert body["plans"][0] == {
        "id": HOUSEHOLD.id,
        "name": "Example Household",
        "last_synced_at": "2026-01-15T12:00:00Z",
        "total": 3_189_560,
    }
    assert body["plans"][1]["last_synced_at"] is None
    assert body["accounts"][0] == {
        "id": "fake-brokerage",
        "plan_id": HOUSEHOLD.id,
        "name": "Brokerage",
        "type": "otherAsset",
        "on_budget": False,
        "balance": 2_000_000,
    }
    assert all(isinstance(a["balance"], int) for a in body["accounts"])
