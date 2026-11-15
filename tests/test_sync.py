import sqlite3
from datetime import UTC, datetime

import pytest

from niff import sync
from niff.store import get_sync_state, list_accounts
from niff.sync import sync_accounts
from niff.ynab import YnabError
from tests.fakes import FakeYnab

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def test_first_sync_stores_accounts_and_cursor(
    conn: sqlite3.Connection, fake_ynab: FakeYnab
) -> None:
    fake_ynab.respond(200, "accounts_full.json")

    with fake_ynab.client() as client:
        result = sync_accounts(conn, client, "fake-plan-id", NOW)

    assert (result.full, result.accounts_changed) == (True, 2)
    assert [a.name for a in list_accounts(conn)] == ["Everyday Checking", "Rewards Card"]
    state = get_sync_state(conn, "ynab")
    assert (state.server_knowledge, state.last_synced_at) == (100, NOW)


def test_delta_sync_sends_cursor_and_applies_changes(
    conn: sqlite3.Connection, fake_ynab: FakeYnab
) -> None:
    fake_ynab.respond(200, "accounts_full.json")
    fake_ynab.respond(200, "accounts_delta.json")

    with fake_ynab.client() as client:
        sync_accounts(conn, client, "fake-plan-id", NOW)
        result = sync_accounts(conn, client, "fake-plan-id", NOW)

    assert fake_ynab.requests[1].url.params["last_knowledge_of_server"] == "100"
    assert result.full is False
    accounts = list_accounts(conn)
    assert [(a.name, a.balance) for a in accounts] == [("Everyday Checking", 1_200_060)]
    assert get_sync_state(conn, "ynab").server_knowledge == 105


def test_api_error_leaves_database_unchanged(conn: sqlite3.Connection, fake_ynab: FakeYnab) -> None:
    fake_ynab.respond(401, "error_401.json")

    with fake_ynab.client() as client, pytest.raises(YnabError):
        sync_accounts(conn, client, "fake-plan-id", NOW)

    assert list_accounts(conn) == []
    assert get_sync_state(conn, "ynab").server_knowledge is None


def test_failure_while_saving_rolls_back_accounts_and_cursor(
    conn: sqlite3.Connection, fake_ynab: FakeYnab, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ynab.respond(200, "accounts_full.json")

    def broken_set_sync_state(*args: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(sync, "set_sync_state", broken_set_sync_state)

    with fake_ynab.client() as client, pytest.raises(sqlite3.OperationalError):
        sync_accounts(conn, client, "fake-plan-id", NOW)

    assert list_accounts(conn) == []
    assert get_sync_state(conn, "ynab").server_knowledge is None
