"""YNAB → local mirror sync. Logs counts only, never names or amounts."""

import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from niff.config import Settings
from niff.db import open_database, transaction
from niff.store import get_plan_cursor, set_plan_cursor, upsert_accounts, upsert_plans
from niff.ynab import YnabClient, YnabError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanSyncResult:
    plan_name: str
    full: bool = False
    accounts_changed: int = 0
    error: str | None = None  # set when this plan failed; other plans still sync


def sync_plan(
    conn: sqlite3.Connection, client: YnabClient, plan_id: str, now: datetime
) -> tuple[bool, int]:
    """Fetch one plan's accounts changed since its cursor and apply them.

    Returns (whether this was a full fetch, number of accounts changed).

    The accounts and the new cursor are saved in one transaction, so the cursor can never move
    ahead of the data (losing changes) or fall behind it.
    """
    cursor = get_plan_cursor(conn, plan_id).server_knowledge
    delta = client.get_accounts(plan_id, cursor)
    with transaction(conn):
        upsert_accounts(conn, delta.accounts, now)
        set_plan_cursor(conn, plan_id, delta.server_knowledge, now)
    return cursor is None, len(delta.accounts)


def sync_plans(
    conn: sqlite3.Connection, client: YnabClient, plan_ids: Sequence[str], now: datetime
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
            full, changed = sync_plan(conn, client, plan.id, now)
        except (YnabError, sqlite3.Error) as exc:
            log.warning("YNAB sync plan %d/%d failed: %s", number, len(plans), exc)
            results.append(PlanSyncResult(plan_name=plan.name, error=str(exc)))
            continue
        log.info(
            "YNAB sync plan %d/%d (%s): %d accounts changed",
            number,
            len(plans),
            "full" if full else "delta",
            changed,
        )
        results.append(PlanSyncResult(plan_name=plan.name, full=full, accounts_changed=changed))
    return results


def run_sync(settings: Settings) -> list[PlanSyncResult]:
    """One complete sync of every configured plan, using the configured database and token."""
    if not (settings.ynab_token and settings.ynab_plan_ids):
        raise RuntimeError("YNAB is not configured: set NIFF_YNAB_TOKEN and NIFF_YNAB_PLAN_IDS")
    conn = open_database(settings.db_path)
    try:
        with YnabClient(settings.ynab_token) as client:
            return sync_plans(conn, client, settings.ynab_plan_ids, datetime.now(UTC))
    finally:
        conn.close()
