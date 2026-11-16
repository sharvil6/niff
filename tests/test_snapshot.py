import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from niff.config import Settings
from niff.db import open_database, transaction
from niff.main import create_app
from niff.snapshot import DailyNetWorth, build_snapshot, net_worth_history
from niff.store import (
    Account,
    Plan,
    record_balances,
    set_plan_cursor,
    upsert_accounts,
    upsert_plans,
)

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
        body = client.get("/api/snapshot").json()

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


def record_day(conn: sqlite3.Connection, plan_id: str, day: date, *accounts: Account) -> None:
    with transaction(conn):
        upsert_accounts(conn, accounts, NOW)
        record_balances(conn, plan_id, day, NOW)


def test_history_is_empty_before_any_balances(conn: sqlite3.Connection) -> None:
    assert net_worth_history(conn, [HOUSEHOLD.id]) == []


def test_history_sums_configured_plans_per_day(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        upsert_plans(conn, [HOUSEHOLD, SIDE, OLD])
    jan15, jan16 = date(2026, 1, 15), date(2026, 1, 16)
    side_savings = replace(CHECKING, plan_id=SIDE.id, ynab_account_id="fake-side", balance=5_000)
    old_checking = replace(CHECKING, plan_id=OLD.id, ynab_account_id="fake-old", balance=7_000)
    record_day(conn, HOUSEHOLD.id, jan15, CHECKING, CARD)
    record_day(conn, SIDE.id, jan15, side_savings)
    record_day(conn, OLD.id, jan15, old_checking)  # not configured: never counts
    record_day(conn, HOUSEHOLD.id, jan16, replace(CHECKING, balance=1_300_000), CARD)
    record_day(conn, SIDE.id, jan16, side_savings)

    assert net_worth_history(conn, [HOUSEHOLD.id, SIDE.id]) == [
        DailyNetWorth(jan15, 1_234_560 - 45_000 + 5_000),
        DailyNetWorth(jan16, 1_300_000 - 45_000 + 5_000),
    ]


def test_plan_missing_a_day_counts_with_its_last_total(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        upsert_plans(conn, [HOUSEHOLD, SIDE])
    jan15, jan16, jan17 = date(2026, 1, 15), date(2026, 1, 16), date(2026, 1, 17)
    side_savings = replace(CHECKING, plan_id=SIDE.id, ynab_account_id="fake-side", balance=5_000)
    record_day(conn, HOUSEHOLD.id, jan15, CHECKING)
    record_day(conn, SIDE.id, jan15, side_savings)
    record_day(conn, HOUSEHOLD.id, jan16, CHECKING)  # side plan's sync failed on the 16th
    record_day(conn, SIDE.id, jan17, replace(side_savings, balance=6_000))  # and household's 17th

    assert net_worth_history(conn, [HOUSEHOLD.id, SIDE.id]) == [
        DailyNetWorth(jan15, 1_234_560 + 5_000),
        DailyNetWorth(jan16, 1_234_560 + 5_000),
        DailyNetWorth(jan17, 1_234_560 + 6_000),
    ]
