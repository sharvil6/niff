import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DB_PATH = Path("data/niff.db")
# Built web page (`npm run build` in web/). Served at / when it exists; the API works without it.
DEFAULT_WEB_DIST = Path("web/dist")


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    # Secret: excluded from repr so it can't leak into logs or error messages.
    ynab_token: str | None = field(default=None, repr=False)
    # Plans to sync. Explicit rather than "every plan the token sees", so old or Fresh Start
    # copies of a plan can't duplicate accounts in net worth.
    ynab_plan_ids: tuple[str, ...] = ()
    sync_interval_minutes: int = 60
    web_dist: Path = DEFAULT_WEB_DIST
    log_level: str = "INFO"

    @property
    def ynab_configured(self) -> bool:
        return bool(self.ynab_token and self.ynab_plan_ids)

    @classmethod
    def from_env(cls) -> "Settings":
        plan_ids = os.environ.get("NIFF_YNAB_PLAN_IDS", "")
        return cls(
            db_path=Path(os.environ.get("NIFF_DB_PATH", DEFAULT_DB_PATH)),
            ynab_token=os.environ.get("NIFF_YNAB_TOKEN") or None,
            ynab_plan_ids=tuple(p.strip() for p in plan_ids.split(",") if p.strip()),
            web_dist=Path(os.environ.get("NIFF_WEB_DIST", DEFAULT_WEB_DIST)),
            log_level=os.environ.get("NIFF_LOG_LEVEL") or "INFO",
        )
