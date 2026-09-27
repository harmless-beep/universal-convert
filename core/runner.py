"""Action dispatcher: (action_id, paths, opts) -> engine function.

One entry point used by the GUI dialog, the CLI, and tests, so every
frontend gets identical behavior (output folder rules, batch semantics).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import documents, images, pdf
from .batch import OutputNamer, Result, resolve_output_dir
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
) -> list[Result]:
    if not paths:
        raise UserError("No files selected.")
    fn = _DISPATCH.get(action_id)
    if fn is None:
        raise UserError(f"Unknown action: {action_id}")
    missing = [p for p in paths if not Path(p).is_file()]
    if missing:
        raise UserError(f"File not found:\n{missing[0]}")
    if action_id == "resize" and "preset_specs" not in opts:
        # engines don't read settings; inject the user's preset table here
        opts = {**opts, "preset_specs": settings.get("presets", {})}
    namer = OutputNamer(resolve_output_dir(settings, paths))
    return fn(paths, opts, namer, progress)
