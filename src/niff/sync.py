"""YNAB → local mirror sync. Logs counts only, never names or amounts."""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from niff.config import Settings
from niff.db import open_database, transaction
from niff.store import get_sync_state, set_sync_state, upsert_accounts
from niff.ynab import YnabClient

YNAB_SOURCE = "ynab"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    full: bool
    accounts_changed: int


def sync_accounts(
    conn: sqlite3.Connection, client: YnabClient, plan_id: str, now: datetime
) -> SyncResult:
    """Fetch accounts changed since the stored cursor and apply them.

    The accounts and the new cursor are saved in one transaction, so the cursor can never move
    ahead of the data (losing changes) or fall behind it.
    """
    cursor = get_sync_state(conn, YNAB_SOURCE).server_knowledge
    delta = client.get_accounts(plan_id, cursor)
    with transaction(conn):
        upsert_accounts(conn, delta.accounts, now)
        set_sync_state(conn, YNAB_SOURCE, delta.server_knowledge, now)
    result = SyncResult(full=cursor is None, accounts_changed=len(delta.accounts))
    log.info(
        "YNAB sync (%s): %d accounts changed",
        "full" if result.full else "delta",
        result.accounts_changed,
    )
    return result


def run_sync(settings: Settings) -> SyncResult:
    """One complete sync using the configured database and token."""
    if not (settings.ynab_token and settings.ynab_plan_id):
        raise RuntimeError("YNAB is not configured: set NIFF_YNAB_TOKEN and NIFF_YNAB_PLAN_ID")
    conn = open_database(settings.db_path)
    try:
        with YnabClient(settings.ynab_token) as client:
            return sync_accounts(conn, client, settings.ynab_plan_id, datetime.now(UTC))
    finally:
        conn.close()
