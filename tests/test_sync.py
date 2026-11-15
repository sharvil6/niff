import sqlite3
from datetime import UTC, datetime

import pytest

from niff import sync
from niff.store import get_plan_cursor, list_accounts
from niff.sync import PlanSyncResult, sync_plans
from tests.fakes import FakeYnab

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
HOUSEHOLD = "fake-plan-id"
SIDE = "fake-side-plan-id"


def test_first_sync_stores_accounts_and_cursor(
    conn: sqlite3.Connection, fake_ynab: FakeYnab
) -> None:
    fake_ynab.respond(200, "plans.json")
    fake_ynab.respond(200, "accounts_full.json")

    with fake_ynab.client() as client:
        results = sync_plans(conn, client, [HOUSEHOLD], NOW)

    assert results == [PlanSyncResult("Example Household", full=True, accounts_changed=2)]
    assert [a.name for a in list_accounts(conn)] == ["Everyday Checking", "Rewards Card"]
    cursor = get_plan_cursor(conn, HOUSEHOLD)
    assert (cursor.server_knowledge, cursor.last_synced_at) == (100, NOW)


def test_delta_sync_sends_cursor_and_applies_changes(
    conn: sqlite3.Connection, fake_ynab: FakeYnab
) -> None:
    for fixture in ["plans.json", "accounts_full.json", "plans.json", "accounts_delta.json"]:
        fake_ynab.respond(200, fixture)

    with fake_ynab.client() as client:
        sync_plans(conn, client, [HOUSEHOLD], NOW)
        results = sync_plans(conn, client, [HOUSEHOLD], NOW)

    assert fake_ynab.requests[3].url.params["last_knowledge_of_server"] == "100"
    assert results[0].full is False
    accounts = list_accounts(conn)
    assert [(a.name, a.balance) for a in accounts] == [("Everyday Checking", 1_200_060)]
    assert get_plan_cursor(conn, HOUSEHOLD).server_knowledge == 105


def test_two_plans_sync_with_separate_cursors(
    conn: sqlite3.Connection, fake_ynab: FakeYnab
) -> None:
    for fixture in ["plans.json", "accounts_full.json", "accounts_side.json"]:
        fake_ynab.respond(200, fixture)

    with fake_ynab.client() as client:
        results = sync_plans(conn, client, [HOUSEHOLD, SIDE], NOW)

    assert [(r.plan_name, r.accounts_changed) for r in results] == [
        ("Example Household", 2),
        ("Example Side Plan", 1),
    ]
    assert [request.url.path for request in fake_ynab.requests[1:]] == [
        f"/v1/plans/{HOUSEHOLD}/accounts",
        f"/v1/plans/{SIDE}/accounts",
    ]
    assert get_plan_cursor(conn, HOUSEHOLD).server_knowledge == 100
    assert get_plan_cursor(conn, SIDE).server_knowledge == 7
    assert [(a.plan_id, a.name) for a in list_accounts(conn)] == [
        (HOUSEHOLD, "Everyday Checking"),
        (HOUSEHOLD, "Rewards Card"),
        (SIDE, "Side Savings"),
    ]


def test_unconfigured_plans_are_ignored(conn: sqlite3.Connection, fake_ynab: FakeYnab) -> None:
    fake_ynab.respond(200, "plans.json")
    fake_ynab.respond(200, "accounts_side.json")

    with fake_ynab.client() as client:
        sync_plans(conn, client, [SIDE], NOW)

    plans = conn.execute("SELECT ynab_plan_id FROM ynab_plans").fetchall()
    assert [row["ynab_plan_id"] for row in plans] == [SIDE]
    assert len(fake_ynab.requests) == 2


def test_one_failing_plan_does_not_block_the_other(
    conn: sqlite3.Connection, fake_ynab: FakeYnab
) -> None:
    fake_ynab.respond(200, "plans.json")
    fake_ynab.respond(401, "error_401.json")
    fake_ynab.respond(200, "accounts_side.json")

    with fake_ynab.client() as client:
        results = sync_plans(conn, client, [HOUSEHOLD, SIDE], NOW)

    assert results[0].plan_name == "Example Household"
    assert results[0].error == "YNAB request failed: 401 unauthorized"
    assert results[1] == PlanSyncResult("Example Side Plan", full=True, accounts_changed=1)
    assert get_plan_cursor(conn, HOUSEHOLD).server_knowledge is None
    assert [a.name for a in list_accounts(conn)] == ["Side Savings"]


def test_configured_plan_not_visible_to_token_fails_clearly(
    conn: sqlite3.Connection, fake_ynab: FakeYnab
) -> None:
    fake_ynab.respond(200, "plans.json")

    with fake_ynab.client() as client, pytest.raises(RuntimeError, match="not visible"):
        sync_plans(conn, client, [HOUSEHOLD, "fake-typo-plan-id"], NOW)

    assert list_accounts(conn) == []


def test_failure_while_saving_rolls_back_accounts_and_cursor(
    conn: sqlite3.Connection, fake_ynab: FakeYnab, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ynab.respond(200, "plans.json")
    fake_ynab.respond(200, "accounts_full.json")

    def broken_set_plan_cursor(*args: object) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(sync, "set_plan_cursor", broken_set_plan_cursor)

    with fake_ynab.client() as client:
        results = sync_plans(conn, client, [HOUSEHOLD], NOW)

    assert results[0].error == "disk I/O error"
    assert list_accounts(conn) == []
    assert get_plan_cursor(conn, HOUSEHOLD).server_knowledge is None
