from pathlib import Path

from fastapi.testclient import TestClient

from niff.config import Settings
from niff.main import create_app


def test_built_page_is_served_at_root_and_api_still_wins(tmp_path: Path) -> None:
    web_dist = tmp_path / "dist"
    (web_dist / "assets").mkdir(parents=True)
    (web_dist / "index.html").write_text("<!doctype html><title>Niff</title>")
    (web_dist / "assets" / "app.js").write_text("console.log('niff')")
    settings = Settings(db_path=tmp_path / "niff.db", web_dist=web_dist)

    with TestClient(create_app(settings)) as client:
        page = client.get("/")
        asset = client.get("/assets/app.js")
        snapshot = client.get("/api/snapshot")
        health = client.get("/healthz")

    assert page.status_code == 200
    assert "<title>Niff</title>" in page.text
    assert asset.status_code == 200
    assert snapshot.json() == {"net_worth": 0, "plans": [], "accounts": []}
    assert health.json() == {"status": "ok"}


def test_api_runs_without_a_built_page(tmp_path: Path) -> None:
    settings = Settings(db_path=tmp_path / "niff.db", web_dist=tmp_path / "missing")

    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/snapshot").status_code == 200
        assert client.get("/healthz").status_code == 200


def test_snapshot_moved_under_api(tmp_path: Path) -> None:
    settings = Settings(db_path=tmp_path / "niff.db", web_dist=tmp_path / "missing")

    with TestClient(create_app(settings)) as client:
        assert client.get("/snapshot").status_code == 404
