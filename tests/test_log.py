import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from niff.config import Settings
from niff.log import LOGGER_NAME, configure_logging
from niff.main import create_app


@pytest.fixture(autouse=True)
def fresh_niff_logger() -> Iterator[logging.Logger]:
    """Start each test without Niff's handler, so it binds to this test's captured stderr."""
    logger = logging.getLogger(LOGGER_NAME)
    saved_handlers, saved_level = logger.handlers[:], logger.level
    logger.handlers.clear()
    yield logger
    logger.handlers[:] = saved_handlers
    logger.setLevel(saved_level)


def test_app_prints_niff_info_logs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    create_app(Settings(db_path=tmp_path / "niff.db"))

    logging.getLogger("niff.sync").info("Coffee Shop plan: delta, 2 accounts changed")

    err = capsys.readouterr().err
    assert "INFO niff.sync: Coffee Shop plan: delta, 2 accounts changed" in err


def test_log_level_filters_and_setup_is_idempotent(
    fresh_niff_logger: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("warning")
    configure_logging("warning")

    logging.getLogger("niff.sync").info("hidden")
    logging.getLogger("niff.sync").warning("shown")

    err = capsys.readouterr().err
    assert "hidden" not in err
    assert err.count("shown") == 1
    assert len(fresh_niff_logger.handlers) == 1


def test_log_level_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIFF_LOG_LEVEL", "DEBUG")

    assert Settings.from_env().log_level == "DEBUG"
