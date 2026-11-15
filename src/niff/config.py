import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DB_PATH = Path("data/niff.db")


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    # Secret: excluded from repr so it can't leak into logs or error messages.
    ynab_token: str | None = field(default=None, repr=False)
    # Plans to sync. Explicit rather than "every plan the token sees", so old or Fresh Start
    # copies of a plan can't duplicate accounts in net worth.
    ynab_plan_ids: tuple[str, ...] = ()
    sync_interval_minutes: int = 60

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
        )
