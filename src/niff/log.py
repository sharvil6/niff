"""Log setup for Niff's own messages.

uvicorn configures only its own loggers, so without this `niff.*` records reach no handler and
Python's last-resort handler prints WARNING and above, dropping INFO lines such as sync results.
"""

import logging

LOGGER_NAME = "niff"
_HANDLER_NAME = "niff-stderr"
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Send `niff.*` records at `level` and above to stderr. Safe to call more than once.

    The handler sits on the `niff` logger, not the root, so it leaves uvicorn's and other
    libraries' logging alone. Records still propagate to the root, which has no handler under
    uvicorn or the CLI, so nothing prints twice (and pytest's caplog still sees them).
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())  # an unknown level name raises ValueError at startup
    if not any(handler.get_name() == _HANDLER_NAME for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.set_name(_HANDLER_NAME)
        handler.setFormatter(logging.Formatter(FORMAT))
        logger.addHandler(handler)
