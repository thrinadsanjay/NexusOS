"""Logging configuration for the ``nexus`` CLI.

Logs go to stderr (so ``--json`` output on stdout stays machine-readable) and,
optionally, to a file. The default level is WARNING; ``--verbose`` enables DEBUG.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

LOGGER_NAME = "nexus"


def configure_logging(verbose: bool = False, log_file: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.propagate = False

    stderr_handler = RichHandler(
        console=Console(stderr=True),
        show_time=verbose,
        show_path=False,
        rich_tracebacks=verbose,
    )
    stderr_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.addHandler(stderr_handler)

    if log_file is not None:
        log_file = log_file.expanduser()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(file_handler)
        logger.setLevel(logging.DEBUG)
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
