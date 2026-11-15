from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from niff.config import Settings
from niff.db import connect, load_migrations, schema_version
from niff.main import create_app


def test_startup_migrates_and_healthz_reports_ok(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "niff.db"

    with TestClient(create_app(Settings(db_path=db_path))) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    with closing(connect(db_path)) as conn:
        assert schema_version(conn) == len(load_migrations())
