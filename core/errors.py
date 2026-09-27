"""Error handling and logging for Universal Convert.

Design rule (from the spec): the user must NEVER see a stack trace.
Everything user-facing raises UserError with a friendly message; anything
unexpected is caught at the top level in main.py, written to the log file,
and shown as a generic message that points at the log.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

APP_NAME = "Universal Convert"

# Project root = parent of this file's directory (core/.. )
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "universal-convert.log"

_logger: logging.Logger | None = None


class UserError(Exception):
    """An error safe to show verbatim to the user (no traceback needed)."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail  # optional technical detail, goes to the log only


def get_logger() -> logging.Logger:
    """Return the app logger, creating the log file on first use.

    Logging must never crash the app (e.g. read-only install dir), so any
    failure falls back to stderr - or to a NullHandler when stderr is gone
    (pythonw on Windows has no stderr at all).
    """
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("universal_convert")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:  # already configured
        _logger = logger
        return logger

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8", delay=True)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        try:
            stream = sys.stderr or sys.__stderr_
            if stream is not None:
                handler = logging.StreamHandler(stream)
                handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
                logger.addHandler(handler)
        except Exception:
            logger.addHandler(logging.NullHandler())

    _logger = logger
    return logger


def log_exception(context: str, exc: BaseException) -> None:
    """Write a full traceback to the log (never to the UI)."""
    log = get_logger()
    log.error("%s: %s", context, exc)
    log.debug("traceback:\n%s", "".join(traceback.format_exception(exc)))


def friendly_message(exc: BaseException) -> str:
    """Map common exceptions to a user-friendly message.

    Used as the last line of defence for errors we didn't anticipate.
    """
    if isinstance(exc, UserError):
        return exc.message
    if isinstance(exc, FileNotFoundError):
        name = getattr(exc, "filename", None) or "a file"
        return f"File not found: {name}"
    if isinstance(exc, PermissionError):
        name = getattr(exc, "filename", None) or "the file"
        return (
            f"Access denied: {name}\n"
            "The file may be open in another program, or you may not have "
            "permission to write here."
        )
    if isinstance(exc, MemoryError):
        return "Out of memory. Try converting fewer/smaller files at once."
    if isinstance(exc, TimeoutError):
        return "The conversion took too long and was stopped."
    if isinstance(exc, OSError):
        return f"Operating system error: {exc.strerror or exc}"
    # PIL-specific errors
    cls = type(exc).__name__
    if cls in ("UnidentifiedImageError", "DecompressionBombError"):
        return "This image could not be read. The file may be corrupt."
    return (
        "Something went wrong while converting.\n"
        f"Details were written to the log:\n{LOG_FILE}"
    )


def describe_paths(paths: list[str], limit: int = 3) -> str:
    """Human-readable list of files, truncated for message boxes."""
    names = [os.path.basename(p) for p in paths]
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f" … (+{len(names) - limit} more)"
