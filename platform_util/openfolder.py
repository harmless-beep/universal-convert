"""Reveal the output folder / file when conversion finishes.

  Windows: explorer.exe /select,"<first output>"  (selects the file)
  macOS:   open -R <first output>
  Linux:   xdg-open <folder>
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from core.errors import get_logger


def open_file(target: str | None) -> bool:
    """Open a file with whatever the OS uses for that type (log, output, ...)."""
    log = get_logger()
    if not target:
        return False
    path = Path(target)
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - intentional shell open
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return True
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(path)],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
        return False
    except Exception as exc:  # noqa: BLE001 - never fail over a click
        log.warning("open_file failed: %s", exc)
        return False


def open_output(target: str | None) -> bool:
    """Open the folder containing `target` (selecting it where supported)."""
    log = get_logger()
    if not target:
        return False
    path = Path(target)
    try:
        if sys.platform == "win32":
            if path.is_dir():
                os.startfile(str(path))  # noqa: S606 - intentional shell open
                return True
            # explorer returns exit code 1 even on success - fire and forget
            subprocess.Popen(
                ["explorer.exe", f"/select,{str(path.resolve())}"],
                creationflags=subprocess.DETACHED_PROCESS
                | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
            return True
        folder = str(path.parent if path.is_file() else path)
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", folder],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
        return False
    except Exception as exc:  # noqa: BLE001 - never fail after a good convert
        log.warning("open_output failed: %s", exc)
        return False
