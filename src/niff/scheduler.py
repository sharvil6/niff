"""Background jobs, run inside the API process with APScheduler.

APScheduler 3.x ships without type hints, so it is confined to this module behind a small typed
wrapper.
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportMissingTypeStubs=false

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from niff.config import Settings
from niff.sync import run_sync
from niff.ynab import YnabError, YnabRateLimited

log = logging.getLogger(__name__)


def sync_job(settings: Settings) -> None:
    """One scheduled sync. Failures are logged and wait for the next run; no retries."""
    try:
        run_sync(settings)
    except YnabRateLimited:
        log.warning("YNAB sync skipped: rate limited, will retry next run")
    except YnabError as exc:
        log.warning("YNAB sync failed: %s", exc)
    except Exception:
        log.exception("YNAB sync crashed")


class SyncScheduler:
    def __init__(self, settings: Settings) -> None:
        self._scheduler = BackgroundScheduler(timezone=UTC)
        self._scheduler.add_job(
            sync_job,
            "interval",
            minutes=settings.sync_interval_minutes,
            args=[settings],
            id="ynab_sync",
            next_run_time=datetime.now(UTC),  # also run once at startup
            max_instances=1,
            coalesce=True,
        )

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)


def start_scheduler(settings: Settings) -> SyncScheduler | None:
    """Start hourly YNAB sync, or return None when YNAB isn't configured."""
    if not settings.ynab_configured:
        log.info("YNAB not configured; scheduled sync disabled")
        return None
    scheduler = SyncScheduler(settings)
    scheduler.start()
    return scheduler
