import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from niff.db import connect, migrate


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "niff.db"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    """A connection to a fresh, fully migrated database."""
    conn = connect(db_path)
    migrate(conn)
    try:
        yield conn
    finally:
        conn.close()
