import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DB_PATH = Path("data/niff.db")


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    # Secret: excluded from repr so it can't leak into logs or error messages.
    ynab_token: str | None = field(default=None, repr=False)
    ynab_plan_id: str | None = None
    sync_interval_minutes: int = 60

    @property
    def ynab_configured(self) -> bool:
        return bool(self.ynab_token and self.ynab_plan_id)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(os.environ.get("NIFF_DB_PATH", DEFAULT_DB_PATH)),
            ynab_token=os.environ.get("NIFF_YNAB_TOKEN") or None,
            ynab_plan_id=os.environ.get("NIFF_YNAB_PLAN_ID") or None,
        )
