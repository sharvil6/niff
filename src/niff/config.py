import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path("data/niff.db")


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(db_path=Path(os.environ.get("NIFF_DB_PATH", DEFAULT_DB_PATH)))
