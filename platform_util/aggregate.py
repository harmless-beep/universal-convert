"""Multi-select aggregation.

The Windows gotcha: a static registry context-menu verb is launched ONCE PER
SELECTED FILE - selecting 5 files spawns 5 pythonw processes, each with a
single path. (MultiSelectModel only controls menu visibility/count, not
invocation. That's why tools like singleinstance.exe exist.)

We solve it in pure stdlib with a locked queue file + owner election:

  1. Every instance appends {files, start_time, pid} to a queue file under an
     exclusive lock (msvcrt.locking on Windows, fcntl.flock elsewhere).
  2. Every instance sleeps `debounce_ms` - siblings launched together append
     within this window.
  3. The instance with the earliest start_time owns the batch: it reads the
     whole queue, dedupes, truncates it, and proceeds with ALL files.
  4. Later instances find their line gone (= consumed by the owner) and exit.
     If the owner apparently vanished, the next-earliest instance force-claims.

On macOS/Linux the file manager passes the whole selection in ONE invocation,
so aggregation is a no-op there (returned directly).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from core.errors import PROJECT_ROOT, get_logger

QUEUE_LOCK_TIMEOUT_S = 3.0


def _queue_dir() -> Path:
    # The tag must be identical for every sibling process of ONE install:
    # that is how they find each other's queue lines. A frozen build unpacks
    # to a fresh random temp dir on every launch, so tag the executable
    # instead of the (per-run) project root.
    anchor = Path(sys.executable) if getattr(sys, "frozen", False) else PROJECT_ROOT
    tag = hashlib.sha256(
        str(anchor).lower().encode("utf-8", "replace")
    ).hexdigest()[:8]
    base = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp")
    return base / f"universal-convert-{tag}"


def _queue_file() -> Path:
    return _queue_dir() / "queue.jsonl"


def _lock_file():
    """Open (creating if needed) the side-car lock file and take an
    exclusive blocking lock with timeout. Returns an open fd."""
    qdir = _queue_dir()
    qdir.mkdir(parents=True, exist_ok=True)
    lock_path = qdir / "queue.lock"
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o666)
    deadline = time.monotonic() + QUEUE_LOCK_TIMEOUT_S
    if sys.platform == "win32":
        import msvcrt

        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return fd
            except OSError:
                if time.monotonic() > deadline:
                    os.close(fd)
                    raise TimeoutError("queue lock timeout")
                time.sleep(0.02)
    else:
        import fcntl

        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError:
                if time.monotonic() > deadline:
                    os.close(fd)
                    raise TimeoutError("queue lock timeout")
                time.sleep(0.02)


def _unlock(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_lines(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "start" in obj:
                    out.append(obj)
    except OSError:
        pass
    return out


def _write_lines(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def gather(files: list[str], debounce_ms: int = 500,
           max_wait_ms: int = 1500) -> list[str] | None:
    """Return the complete selection for this invocation (deduped, ordered),
    or None when another instance owns the batch (caller must exit quietly)."""
    if not files:
        return []
    if sys.platform != "win32":
        return _dedupe(files)   # single invocation on macOS/Linux
    if len(files) > 1:
        # Not launched by Explorer (CLI already batched) - no siblings expected
        return _dedupe(files)

    log = get_logger()
    my_start = time.time_ns()
    me = {"files": list(files), "start": my_start, "pid": os.getpid()}
    qpath = _queue_file()

    try:
        fd = _lock_file()
        try:
            with open(str(qpath), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(me, ensure_ascii=False) + "\n")
                fh.flush()
        finally:
            _unlock(fd)
    except Exception as exc:  # noqa: BLE001 - never break launch over IPC
        log.warning("aggregate: enqueue failed (%s); continuing with %s",
                    exc, files)
        return _dedupe(files)

    time.sleep(max(0, debounce_ms) / 1000.0)

    deadline = time.monotonic() + max(100, max_wait_ms) / 1000.0
    while True:
        try:
            fd = _lock_file()
        except TimeoutError:
            break
        try:
            rows = _read_lines(qpath)
            mine = [r for r in rows if r.get("pid") == os.getpid()]
            if not mine:
                # our line is gone -> an owner already consumed the batch
                log.debug("aggregate: pid=%s yields to owner", os.getpid())
                return None
            earliest = min(r["start"] for r in rows)
            if earliest == my_start or time.monotonic() >= deadline:
                # I own the batch (or the owner vanished - force claim)
                merged: list[str] = []
                for row in sorted(rows, key=lambda r: r["start"]):
                    merged.extend(row.get("files", []))
                _write_lines(qpath, [])  # truncate under lock
                log.debug("aggregate: owner pid=%s collected %d file(s)",
                          os.getpid(), len(merged))
                return _dedupe(merged)
        finally:
            _unlock(fd)
        time.sleep(0.1)

    # Could not resolve ownership in time: degrade gracefully.
    log.warning("aggregate: timed out; continuing with %s", files)
    return _dedupe(files)


def _dedupe(files: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for f in files:
        key = os.path.normcase(os.path.abspath(f))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out
