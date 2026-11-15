import logging
from pathlib import Path

import pytest

from niff import scheduler
from niff.config import Settings
from niff.scheduler import start_scheduler, sync_job
from niff.ynab import YnabError, YnabRateLimited
from tests.fakes import FAKE_TOKEN


def test_settings_repr_hides_token() -> None:
    settings = Settings(ynab_token=FAKE_TOKEN, ynab_plan_ids=("fake-plan-id",))

    assert FAKE_TOKEN not in repr(settings)
    assert settings.ynab_configured


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIFF_DB_PATH", "/tmp/elsewhere.db")
    monkeypatch.setenv("NIFF_YNAB_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("NIFF_YNAB_PLAN_IDS", " fake-plan-id, fake-side-plan-id ,,")

    settings = Settings.from_env()

    assert settings.db_path == Path("/tmp/elsewhere.db")
    assert settings.ynab_token == FAKE_TOKEN
    assert settings.ynab_plan_ids == ("fake-plan-id", "fake-side-plan-id")
    assert settings.ynab_configured


def test_settings_need_plan_ids_to_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIFF_YNAB_TOKEN", FAKE_TOKEN)
    monkeypatch.delenv("NIFF_YNAB_PLAN_IDS", raising=False)

    assert not Settings.from_env().ynab_configured


def test_scheduler_is_not_started_without_ynab_config(tmp_path: Path) -> None:
    assert start_scheduler(Settings(db_path=tmp_path / "niff.db")) is None


@pytest.mark.parametrize(
    "error", [YnabRateLimited(429, "too_many_requests"), YnabError(500, "internal"), ValueError()]
)
def test_sync_job_logs_failures_instead_of_raising(
    error: Exception, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def failing_run_sync(settings: Settings) -> None:
        raise error

    monkeypatch.setattr(scheduler, "run_sync", failing_run_sync)

    with caplog.at_level(logging.WARNING):
        sync_job(Settings(ynab_token=FAKE_TOKEN, ynab_plan_ids=("fake-plan-id",)))

    assert "YNAB sync" in caplog.text
    assert FAKE_TOKEN not in caplog.text
