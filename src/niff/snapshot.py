"""Net worth right now, from the local mirror. No network calls.

Net worth is the sum of every open account in the configured plans. YNAB already stores cards
and loans as negative balances, so a plain sum is correct. Amounts are milliunits.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from niff.store import Account, list_accounts, list_plan_day_totals, list_plans


@dataclass(frozen=True)
class PlanTotal:
    id: str
    name: str
    last_synced_at: datetime | None
    total: int  # milliunits


@dataclass(frozen=True)
class Snapshot:
    net_worth: int  # milliunits
    plans: list[PlanTotal]  # in configured order
    accounts: list[Account]  # open accounts, grouped by plan in configured order, then by name


def build_snapshot(conn: sqlite3.Connection, plan_ids: Sequence[str]) -> Snapshot:
    """Only configured plans count, in the order configured; plans not yet synced are skipped."""
    stored = {plan.id: plan for plan in list_plans(conn)}
    plans = [stored[plan_id] for plan_id in plan_ids if plan_id in stored]
    order = {plan.id: position for position, plan in enumerate(plans)}

    # list_accounts orders by plan name then account name; the stable sort keeps the name order.
    accounts = sorted(
        (a for a in list_accounts(conn) if a.plan_id in order),
        key=lambda a: order[a.plan_id],
    )
    totals = dict.fromkeys(order, 0)
    for account in accounts:
        totals[account.plan_id] += account.balance

    return Snapshot(
        net_worth=sum(totals.values()),
        plans=[
            PlanTotal(
                id=plan.id,
                name=plan.name,
                last_synced_at=plan.last_synced_at,
                total=totals[plan.id],
            )
            for plan in plans
        ],
        accounts=accounts,
    )


@dataclass(frozen=True)
class DailyNetWorth:
    day: date
    net_worth: int  # milliunits


def net_worth_history(conn: sqlite3.Connection, plan_ids: Sequence[str]) -> list[DailyNetWorth]:
    """Net worth for every day with recorded balances, oldest first. Only configured plans count.

    A plan with no balances on a day (its sync failed, or Niff wasn't running) counts with its
    last recorded total, so a missed sync doesn't show as a dip. A plan counts only from its first
    recorded day.
    """
    configured = set(plan_ids)
    latest: dict[str, int] = {}  # plan ID -> its most recent total so far
    history: list[DailyNetWorth] = []
    for row in list_plan_day_totals(conn):  # ordered by day
        if row.plan_id not in configured:
            continue
        latest[row.plan_id] = row.total
        point = DailyNetWorth(day=row.day, net_worth=sum(latest.values()))
        if history and history[-1].day == row.day:
            history[-1] = point
        else:
            history.append(point)
    return history
