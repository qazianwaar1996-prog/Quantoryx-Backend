# utils/logging_config.py
"""
Centralized logging configuration for Quantoryx.

Provides a single :func:`get_logger` entry point so every module shares a
consistent, timestamped format and a configurable level (via the
``QUANTORYX_LOG_LEVEL`` environment variable). Console output remains
human-readable, preserving the framework's existing operator experience
while replacing scattered ``print`` calls with structured logging.
"""

import logging
import os
import sys
from typing import Optional

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root() -> None:
    """Attach a single stdout handler to the Quantoryx root logger once."""
    global _configured
    if _configured:
        return

    level_name = os.environ.get("QUANTORYX_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger("quantoryx")
    root.setLevel(level)

    # Avoid duplicate handlers if the process re-imports this module.
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(handler)

    root.propagate = False
    _configured = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a namespaced logger under the shared ``quantoryx`` root.

    Parameters
    ----------
    name:
        Typically ``__name__``. The ``quantoryx.`` prefix is applied
        automatically so all framework logs share one configurable root.
    """
    _configure_root()
    if not name or name == "__main__":
        return logging.getLogger("quantoryx")
    return logging.getLogger(f"quantoryx.{name}")
