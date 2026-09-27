"""LibreOffice headless wrapper: discovery + `soffice --convert-to` runner.

Why an isolated profile (-env:UserInstallation=...) on every run:
if the user has LibreOffice open, a headless conversion with the default
profile fails with "application is already running". A throwaway profile
per run avoids that entirely (and is cleaned up afterwards).

Discovery checks PATH plus each OS's standard install locations, and the
friendly "not installed" error includes per-OS install instructions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .errors import UserError, get_logger

_UNSET = object()
_CACHE: Path | None | object = _UNSET

INSTALL_HINT = {
    "win32": "Install it from https://www.libreoffice.org/download/ "
             "or run: winget install TheDocumentFoundation.LibreOffice",
    "darwin": "Install it from https://www.libreoffice.org/download/ "
              "or run: brew install --cask libreoffice",
    "linux": "Install it with your package manager, e.g.: "
             "sudo apt install libreoffice",
}


def _candidates() -> list[Path]:
    found: list[Path] = []
    which = shutil.which
    if sys.platform == "win32":
        # .com blocks and relays the exit code; .exe detaches - prefer .com
        for name in ("soffice.com", "soffice.exe", "libreoffice.com"):
            p = which(name)
            if p:
                found.append(Path(p))
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        for base in (pf, pf86, local):
            if base:
                found.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
                found.append(Path(base) / "LibreOffice" / "program" / "soffice.com")
    elif sys.platform == "darwin":
        for p in ("/Applications/LibreOffice.app/Contents/MacOS/soffice",
                  str(Path.home() / "Applications" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice")):
            found.append(Path(p))
        for name in ("soffice", "libreoffice"):
            w = which(name)
            if w:
                found.append(Path(w))
    else:
        for name in ("soffice", "libreoffice"):
            w = which(name)
            if w:
                found.append(Path(w))
        found.append(Path("/usr/bin/soffice"))
        found.append(Path("/usr/lib/libreoffice/program/soffice"))
    return found


def find_soffice(refresh: bool = False) -> Path | None:
    global _CACHE
    if not refresh and _CACHE is not _UNSET:
        return _CACHE  # type: ignore[return-value]
    result: Path | None = None
    for cand in _candidates():
        if cand.is_file():
            result = cand
            break
    _CACHE = result
    return result


def require_soffice() -> Path:
    soffice = find_soffice()
    if soffice is None:
        hint = INSTALL_HINT.get(sys.platform, INSTALL_HINT["linux"])
        raise UserError(
            "LibreOffice is not installed (or not found).\n\n"
            "Office and PDF document conversions need LibreOffice in "
            "headless mode - no Microsoft Office required.\n\n" + hint
        )
    return soffice


def version() -> str | None:
    soffice = find_soffice()
    if not soffice:
        return None
    try:
        out = subprocess.run(
            [str(soffice), "--version"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        return (out.stdout or out.stderr or "").strip().splitlines()[0] or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def convert_to(
    files: list[Path],
    fmt: str,
    outdir: Path,
    timeout: int = 300,
    strict: bool = True,
) -> tuple[list[Path], list[Path]]:
    """Run one headless conversion; returns (produced, missing) paths.

    strict=True  -> raise a friendly UserError if any output is missing
    strict=False -> report missing outputs in the second list instead
    """
    soffice = require_soffice()
    if not files:
        raise UserError("No input files for the conversion.")

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for f in files:
        if not Path(f).is_file():
            raise UserError(f"File not found:\n{f}")

    profile_dir = Path(tempfile.mkdtemp(prefix="uc-lo-profile-"))
    profile_uri = Path(profile_dir).resolve().as_uri()
    args = [
        str(soffice),
        "--headless", "--norestore", "--invisible", "--nolockcheck",
        f"-env:UserInstallation={profile_uri}",
        "--convert-to", fmt,
        "--outdir", str(outdir),
        *[str(f) for f in files],
    ]
    log = get_logger()
    log.debug("LibreOffice cmd: %s", " ".join(args))

    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise UserError(
            f"LibreOffice timed out after {timeout}s. The file may be huge or "
            "damaged - try converting fewer files at once."
        ) from exc
    except OSError as exc:
        raise UserError(f"Could not start LibreOffice: {exc}") from exc
    finally:
        try:
            shutil.rmtree(profile_dir, ignore_errors=True)
        except OSError:
            pass

    produced: list[Path] = []
    missing: list[Path] = []
    for f in files:
        out = outdir / (Path(f).stem + "." + fmt.split(":")[0])
        (produced if out.is_file() else missing).append(out)

    log.debug("LibreOffice rc=%s stdout=%r stderr=%r",
              proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])

    if missing and strict:
        names = ", ".join(p.name for p in missing)
        stderr = (proc.stderr or proc.stdout or "").strip()
        detail = ""
        if stderr:
            # keep only the informative tail, one line
            line = [l for l in stderr.splitlines() if l.strip()]
            if line:
                detail = f"\n\nLibreOffice said: {line[-1][:200]}"
        raise UserError(
            f"LibreOffice could not convert: {names}\n\n"
            "The file may be corrupt, password-protected, or in an "
            "unsupported format." + detail
        )
    if proc.returncode not in (0, None):
        # LO sometimes returns non-zero but still writes the output; since
        # every expected file exists we only log this.
        get_logger().warning("LibreOffice exited with code %s", proc.returncode)
    return produced, missing
