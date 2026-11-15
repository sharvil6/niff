import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from niff.db import transaction
from niff.store import (
    Account,
    Plan,
    get_plan_cursor,
    list_accounts,
    set_plan_cursor,
    upsert_accounts,
    upsert_plans,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

HOUSEHOLD = Plan(id="fake-plan-id", name="Example Household")
SIDE = Plan(id="fake-side-plan-id", name="Example Side Plan")

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
SIDE_SAVINGS = replace(
    CHECKING, plan_id=SIDE.id, ynab_account_id="fake-side-savings", name="Side Savings"
)


@pytest.fixture(autouse=True)
def plans(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        upsert_plans(conn, [HOUSEHOLD, SIDE])


def test_upsert_inserts_new_accounts(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        upsert_accounts(conn, [CHECKING, CARD], NOW)

    assert list_accounts(conn) == [CHECKING, CARD]


def test_upsert_updates_existing_account_without_duplicating(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        upsert_accounts(conn, [CHECKING], NOW)
    renamed = replace(CHECKING, name="Main Checking", balance=999_000)

    with transaction(conn):
        upsert_accounts(conn, [renamed], NOW)

    assert list_accounts(conn) == [renamed]
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_list_accounts_orders_by_plan_then_name(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        upsert_accounts(conn, [SIDE_SAVINGS, CARD, CHECKING], NOW)

    assert list_accounts(conn) == [CHECKING, CARD, SIDE_SAVINGS]


def test_list_accounts_hides_closed_and_deleted(conn: sqlite3.Connection) -> None:
    closed = replace(CHECKING, ynab_account_id="fake-old", name="Old Savings", closed=True)
    deleted = replace(CHECKING, ynab_account_id="fake-gone", name="Gone", deleted=True)

    with transaction(conn):
        upsert_accounts(conn, [CHECKING, closed, deleted], NOW)

    assert list_accounts(conn) == [CHECKING]


def test_account_for_unknown_plan_is_rejected(conn: sqlite3.Connection) -> None:
    orphan = replace(CHECKING, plan_id="not-a-known-plan")

    with pytest.raises(sqlite3.IntegrityError), transaction(conn):
        upsert_accounts(conn, [orphan], NOW)


def test_plan_cursor_is_empty_before_first_sync(conn: sqlite3.Connection) -> None:
    cursor = get_plan_cursor(conn, HOUSEHOLD.id)

    assert cursor.server_knowledge is None
    assert cursor.last_synced_at is None


def test_plan_cursors_are_independent(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        set_plan_cursor(conn, HOUSEHOLD.id, 43, NOW)

    assert get_plan_cursor(conn, HOUSEHOLD.id).server_knowledge == 43
    assert get_plan_cursor(conn, HOUSEHOLD.id).last_synced_at == NOW
    assert get_plan_cursor(conn, SIDE.id).server_knowledge is None


def test_renaming_a_plan_keeps_its_cursor(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        set_plan_cursor(conn, HOUSEHOLD.id, 43, NOW)
    with transaction(conn):
        upsert_plans(conn, [replace(HOUSEHOLD, name="Renamed Household")])

    assert get_plan_cursor(conn, HOUSEHOLD.id).server_knowledge == 43


def test_unknown_plan_cursor_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(KeyError):
        get_plan_cursor(conn, "not-a-known-plan")
    with pytest.raises(KeyError), transaction(conn):
        set_plan_cursor(conn, "not-a-known-plan", 1, NOW)


def test_naive_timestamps_are_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="timezone-aware"), transaction(conn):
        upsert_accounts(conn, [CHECKING], datetime(2026, 1, 15, 12, 0))


def test_writes_outside_a_transaction_are_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError, match="transaction"):
        upsert_accounts(conn, [CHECKING], NOW)
