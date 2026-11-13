"""Logger factory shared by nexus_core consumers (CLI, Command Center, agent).

All loggers live under the ``nexus`` hierarchy; the host application configures handlers.
"""

from __future__ import annotations

import logging

ROOT = "nexus"


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{ROOT}.{name}")
