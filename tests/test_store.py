import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from niff.store import Account, get_sync_state, list_accounts, set_sync_state, upsert_accounts

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

CHECKING = Account(
    ynab_account_id="fake-checking",
    name="Everyday Checking",
    type="checking",
    on_budget=True,
    closed=False,
    deleted=False,
    balance=1_234_560,
)
CARD = Account(
    ynab_account_id="fake-card",
    name="Rewards Card",
    type="creditCard",
    on_budget=True,
    closed=False,
    deleted=False,
    balance=-45_000,
)


def test_upsert_inserts_new_accounts(conn: sqlite3.Connection) -> None:
    upsert_accounts(conn, [CHECKING, CARD], NOW)

    assert list_accounts(conn) == [CHECKING, CARD]


def test_upsert_updates_existing_account_without_duplicating(conn: sqlite3.Connection) -> None:
    upsert_accounts(conn, [CHECKING], NOW)
    renamed = replace(CHECKING, name="Main Checking", balance=999_000)

    upsert_accounts(conn, [renamed], NOW)

    assert list_accounts(conn) == [renamed]
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1


def test_list_accounts_hides_closed_and_deleted(conn: sqlite3.Connection) -> None:
    closed = replace(CHECKING, ynab_account_id="fake-old", name="Old Savings", closed=True)
    deleted = replace(CHECKING, ynab_account_id="fake-gone", name="Gone", deleted=True)

    upsert_accounts(conn, [CHECKING, closed, deleted], NOW)

    assert list_accounts(conn) == [CHECKING]


def test_sync_state_is_empty_before_first_sync(conn: sqlite3.Connection) -> None:
    state = get_sync_state(conn, "ynab")

    assert state.server_knowledge is None
    assert state.last_synced_at is None


def test_sync_state_round_trips(conn: sqlite3.Connection) -> None:
    set_sync_state(conn, "ynab", 42, NOW)
    set_sync_state(conn, "ynab", 43, NOW)

    state = get_sync_state(conn, "ynab")

    assert state.server_knowledge == 43
    assert state.last_synced_at == NOW


def test_naive_timestamps_are_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        upsert_accounts(conn, [CHECKING], datetime(2026, 1, 15, 12, 0))
