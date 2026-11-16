"""Developer commands. Output goes to your terminal only; never paste it into the repo.

uv run niff plans   # list YNAB plans to find IDs for NIFF_YNAB_PLAN_IDS
uv run niff sync    # run one YNAB sync now
"""

import argparse
import sys

from niff.config import Settings
from niff.log import configure_logging
from niff.sync import run_sync
from niff.ynab import YnabClient, YnabError


def _plans(settings: Settings) -> int:
    if not settings.ynab_token:
        print("NIFF_YNAB_TOKEN is not set", file=sys.stderr)
        return 1
    with YnabClient(settings.ynab_token) as client:
        for plan in client.list_plans():
            print(f"{plan.id}  {plan.name}")
    return 0


def _sync(settings: Settings) -> int:
    results = run_sync(settings)
    for result in results:
        if result.error:
            print(f"{result.plan_name}: failed ({result.error})")
        else:
            kind = "full" if result.full else "delta"
            print(
                f"{result.plan_name}: {kind}, {result.accounts_changed} accounts changed, "
                f"{result.balances_recorded} balances recorded"
            )
    return 1 if any(result.error for result in results) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="niff")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plans", help="list YNAB plans and their IDs")
    commands.add_parser("sync", help="run one YNAB sync now")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    configure_logging(settings.log_level)
    try:
        return _plans(settings) if args.command == "plans" else _sync(settings)
    except (YnabError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
