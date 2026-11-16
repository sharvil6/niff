"""YNAB → local mirror sync. Logs counts only, never names or amounts."""

import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from niff.config import Settings
from niff.db import open_database, transaction
from niff.store import (
    get_plan_cursor,
    record_balances,
    set_plan_cursor,
    upsert_accounts,
    upsert_plans,
)
from niff.ynab import YnabClient, YnabError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanSyncResult:
    plan_name: str
    full: bool = False
    accounts_changed: int = 0
    balances_recorded: int = 0
    error: str | None = None  # set when this plan failed; other plans still sync


def sync_plan(
    conn: sqlite3.Connection, client: YnabClient, plan_id: str, now: datetime, tz: tzinfo
) -> tuple[bool, int, int]:
    """Fetch one plan's accounts changed since its cursor, apply them and record today's balances.

    Returns (whether this was a full fetch, accounts changed, balances recorded). "Today" is the
    date of ``now`` in ``tz``.

    The accounts, today's balances and the new cursor are saved in one transaction, so the cursor
    can never move ahead of the data (losing changes) or fall behind it, and the history always
    matches the accounts.
    """
    cursor = get_plan_cursor(conn, plan_id).server_knowledge
    delta = client.get_accounts(plan_id, cursor)
    with transaction(conn):
        upsert_accounts(conn, delta.accounts, now)
        recorded = record_balances(conn, plan_id, now.astimezone(tz).date(), now)
        set_plan_cursor(conn, plan_id, delta.server_knowledge, now)
    return cursor is None, len(delta.accounts), recorded


def sync_plans(
    conn: sqlite3.Connection,
    client: YnabClient,
    plan_ids: Sequence[str],
    now: datetime,
    tz: tzinfo = UTC,
) -> list[PlanSyncResult]:
    """Sync each configured plan. A failing plan is reported and doesn't stop the others."""
    visible = {plan.id: plan for plan in client.list_plans()}
    missing = [plan_id for plan_id in plan_ids if plan_id not in visible]
    if missing:
        raise RuntimeError(
            f"{len(missing)} configured plan ID(s) not visible to this YNAB token: "
            + ", ".join(missing)
        )
    plans = [visible[plan_id] for plan_id in plan_ids]
    with transaction(conn):
        upsert_plans(conn, plans)

    results: list[PlanSyncResult] = []
    for number, plan in enumerate(plans, start=1):
        try:
            full, changed, recorded = sync_plan(conn, client, plan.id, now, tz)
        except (YnabError, sqlite3.Error) as exc:
            log.warning("YNAB sync plan %d/%d failed: %s", number, len(plans), exc)
            results.append(PlanSyncResult(plan_name=plan.name, error=str(exc)))
            continue
        log.info(
            "YNAB sync plan %d/%d (%s): %d accounts changed, %d balances recorded",
            number,
            len(plans),
            "full" if full else "delta",
            changed,
            recorded,
        )
        results.append(
            PlanSyncResult(
                plan_name=plan.name,
                full=full,
                accounts_changed=changed,
                balances_recorded=recorded,
            )
        )
    return results


def run_sync(settings: Settings) -> list[PlanSyncResult]:
    """One complete sync of every configured plan, using the configured database and token."""
    if not (settings.ynab_token and settings.ynab_plan_ids):
        raise RuntimeError("YNAB is not configured: set NIFF_YNAB_TOKEN and NIFF_YNAB_PLAN_IDS")
    conn = open_database(settings.db_path)
    try:
        with YnabClient(settings.ynab_token) as client:
            return sync_plans(
                conn, client, settings.ynab_plan_ids, datetime.now(UTC), settings.timezone
            )
    finally:
        conn.close()
