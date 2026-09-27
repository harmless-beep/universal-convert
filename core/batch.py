"""Batch mechanics: output folder resolution, collision-free naming, results.

Every action runs through run_batch() so one bad file never aborts the rest -
failures are collected per file and shown in the results view.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import UserError, get_logger, log_exception
from .settings import Settings


@dataclass
class Result:
    input: str
    output: str | None
    ok: bool
    error: str = ""
    note: str = ""                      # e.g. "-120 KB (34%)" or fallback info
    outputs: list[str] | None = None    # all files produced (pages, split parts)

    @property
    def label(self) -> str:
        if self.ok:
            return Path(self.output).name if self.output else "done"
        return self.error


def resolve_output_dir(settings: Settings, inputs: list[str]) -> Path:
    """Where outputs go, per settings:
      subfolder -> <folder of first input>/<subfolder_name>
      same      -> folder of first input
      custom    -> the configured absolute path
    """
    mode = settings.get("output.folder_mode", "subfolder")
    first = Path(inputs[0]).expanduser()
    if mode == "same":
        base = first.parent
    elif mode == "custom":
        custom = settings.get("output.custom_path")
        base = Path(custom).expanduser() if custom else first.parent
        if custom is None:
            base = first.parent
    else:  # subfolder (default)
        name = settings.get("output.subfolder_name", "Converted") or "Converted"
        base = first.parent / name

    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UserError(
            f"Cannot create the output folder:\n{base}\n({exc.strerror or exc})"
        ) from exc
    return base


class OutputNamer:
    """Hands out output paths that never overwrite existing files or
    collide with each other within one run."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self._taken: set[str] = set()

    def unique(self, path: Path) -> Path:
        candidate = path
        n = 1
        while str(candidate).lower() in self._taken or candidate.exists():
            candidate = path.with_stem(f"{path.stem} ({n})")
            n += 1
        self._taken.add(str(candidate).lower())
        return candidate

    def for_input(
        self, input_path: str, ext: str, label: str = ""
    ) -> Path:
        """<stem>[_<label>].<ext> in the output folder, made unique."""
        stem = Path(input_path).stem
        if label:
            stem = f"{stem}_{label}"
        if not ext.startswith("."):
            ext = "." + ext
        return self.unique(self.output_dir / f"{stem}{ext}")

    def fixed(self, name: str) -> Path:
        """A single well-known output (e.g. merged.pdf), made unique."""
        return self.unique(self.output_dir / name)


def run_batch(
    files: list[str],
    worker: Callable[[str], str | None],
) -> list[Result]:
    """Call worker(file) for every file; returns per-file results.

    worker returns the output path (or None when the output location is
    managed elsewhere, e.g. merged PDF). Exceptions become friendly
    per-file failures; unknown exceptions are logged with traceback.
    """
    results: list[Result] = []
    log = get_logger()
    for path in files:
        try:
            out = worker(path)
            results.append(Result(input=path, output=out, ok=True))
            log.info("OK: %s -> %s", path, out or "(in place)")
        except UserError as exc:
            results.append(Result(input=path, output=None, ok=False, error=exc.message))
            log.warning("FAILED: %s: %s", path, exc.message)
        except Exception as exc:  # noqa: BLE001 - batch must survive anything
            log_exception(f"Unexpected failure for {path}", exc)
            from .errors import friendly_message

            results.append(
                Result(input=path, output=None, ok=False, error=friendly_message(exc))
            )
    return results


def first_output(results: list[Result]) -> str | None:
    for r in results:
        if r.ok and r.output:
            return r.output
    return None


def summarize(results: list[Result]) -> str:
    ok = sum(1 for r in results if r.ok)
    failed = len(results) - ok
    if failed == 0:
        return f"All {ok} file{'s' if ok != 1 else ''} converted."
    return f"{ok} succeeded, {failed} failed."
