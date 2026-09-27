"""Action dispatcher: (action_id, paths, opts) -> engine function.

One entry point used by the GUI dialog, the CLI, and tests, so every
frontend gets identical behavior (output folder rules, batch semantics).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from . import documents, images, pdf
from .batch import OutputNamer, Result, resolve_output_dir, set_cancel
from .errors import UserError
from .settings import Settings

Progress = Callable[[int, int, str], None] | None

Dispatch = Callable[
    [list[str], dict, OutputNamer, Progress], list[Result]
]

_DISPATCH: dict[str, Dispatch] = {
    "resize": images.do_resize,
    "compress": images.do_compress,
    "convert": images.do_convert,
    "pdf_to_images": pdf.do_pdf_to_images,
    "pdf_to_docx": pdf.do_pdf_to_docx,
    "pdf_compress": pdf.do_pdf_compress,
    "pdf_merge": pdf.do_pdf_merge,
    "pdf_split": pdf.do_pdf_split,
    "office_to_pdf": documents.do_office_to_pdf,
    "pptx_to_images": documents.do_pptx_to_images,
}


def run_action(
    action_id: str,
    paths: list[str],
    opts: dict,
    settings: Settings,
    progress: Progress = None,
    cancel: threading.Event | None = None,
) -> list[Result]:
    """Run one action over `paths`.

    `cancel` is an optional threading.Event the caller can set to stop the
    run between files; engines poll it via batch.cancelled().
    """
    if not paths:
        raise UserError("No files selected.")
    fn = _DISPATCH.get(action_id)
    if fn is None:
        raise UserError(f"Unknown action: {action_id}")
    present = [p for p in paths if Path(p).is_file()]
    if not present:
        raise UserError(f"File not found:\n{paths[0]}")
    if action_id == "resize" and "preset_specs" not in opts:
        # engines don't read settings; inject the user's preset table here
        opts = {**opts, "preset_specs": settings.get("presets", {})}
    namer = OutputNamer(resolve_output_dir(settings, present))
    set_cancel(cancel)
    try:
        results = fn(present, opts, namer, progress)
    finally:
        set_cancel(None)
    return _merge_missing(paths, present, results)


def _merge_missing(
    paths: list[str], present: list[str], results: list[Result]
) -> list[Result]:
    """Re-attach per-file failures for paths that vanished before the run.

    One stale path must not abort a whole batch: files that disappeared are
    reported as failures and every other result keeps its place in the
    original selection order.
    """
    if len(present) == len(paths):
        return results
    by_input: dict[str, Result] = {}
    for r in results:
        by_input.setdefault(r.input, r)
    merged: list[Result] = []
    for p in paths:
        hit = by_input.pop(p, None)
        if hit is not None:
            merged.append(hit)
        elif Path(p).is_file():
            continue  # produced under another key; appended below
        else:
            merged.append(Result(input=p, output=None, ok=False,
                                 error="File not found (moved or deleted?)"))
    merged.extend(r for r in results if r.input in by_input)
    return merged
