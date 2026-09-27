"""Office document actions (LibreOffice headless).

  office_to_pdf   DOCX/PPTX/XLSX -> PDF
  pptx_to_images  PPTX -> PDF -> one PNG per slide -> .zip

Both convert into a private temp dir first, then move results into the
user's output folder through OutputNamer - LibreOffice would otherwise
silently overwrite files that already exist there.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from .batch import CANCELLED, OutputNamer, Result, cancelled
from .errors import UserError, get_logger

Progress = Callable[[int, int, str], None] | None


def _unique_stem_batches(paths: list[str]) -> list[list[Path]]:
    """LibreOffice names outputs after input stems, so two inputs like
    report.docx + report.xlsx would collide (report.pdf). Pack paths so
    every batch has unique stems - usually just one batch."""
    batches: list[list[Path]] = []
    seen: set[str] = set()
    for p in paths:
        key = Path(p).stem.lower()
        if key in seen:
            batches.append([Path(p)])  # rare: split off
            continue
        seen.add(key)
        if not batches or len(batches[0]) >= 50:
            batches.append([])
        batches[0].append(Path(p))
    return [b for b in batches if b]


def do_office_to_pdf(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    from .libreoffice import convert_to, require_soffice

    require_soffice()  # friendly error early, before touching files
    results: dict[str, Result] = {}
    done = 0

    for batch in _unique_stem_batches(paths):
        if cancelled():
            get_logger().info("cancelled: office->pdf stopped before a batch")
            break
        tmp = Path(tempfile.mkdtemp(prefix="uc-lo-pdf-"))
        try:
            produced, missing = convert_to(batch, "pdf", tmp, strict=False)
            produced_map = {p.name.lower(): p for p in produced}
            for src in batch:
                done += 1
                expect = (src.stem + ".pdf").lower()
                made = produced_map.get(expect)
                if made and made.is_file():
                    dest = namer.unique(namer.output_dir / f"{src.stem}.pdf")
                    shutil.move(str(made), str(dest))
                    results[str(src)] = Result(
                        input=str(src), output=str(dest), ok=True,
                        note="via LibreOffice headless",
                    )
                else:
                    results[str(src)] = Result(
                        input=str(src), output=None, ok=False,
                        error="LibreOffice could not read this file "
                              "(corrupt, locked, or unsupported format).",
                    )
                if progress:
                    progress(done, len(paths), Path(src).name)
                if cancelled():
                    break
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    return _in_order(paths, results)


def _in_order(paths: list[str], produced: dict[str, Result]) -> list[Result]:
    """One result per input, in the caller's order.

    Keys may be the normalized path (`str(Path(p))`) rather than exactly
    what the caller passed - anything not produced (or dropped by
    cancellation) becomes an explicit failure instead of disappearing,
    which used to make the summary under-report the batch.
    """
    out: list[Result] = []
    for p in paths:
        r = produced.pop(str(Path(p)), None)
        if r is None:
            r = produced.pop(p, None)
        if r is None:
            r = Result(input=p, output=None, ok=False,
                       error=CANCELLED if cancelled()
                       else "No output was produced for this file.")
        r.input = p
        out.append(r)
    return out


def do_pptx_to_images(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    from .libreoffice import convert_to, require_soffice
    from .pdf import do_pdf_to_images

    require_soffice()
    fmt = str(opts.get("format", "png")).lower()
    dpi = int(opts.get("dpi", 150))
    results: list[Result] = []

    for i, path in enumerate(paths):
        tmp = Path(tempfile.mkdtemp(prefix="uc-lo-slides-"))
        try:
            produced, _ = convert_to([Path(path)], "pdf", tmp, strict=False)
            if not produced:
                results.append(Result(
                    input=path, output=None, ok=False,
                    error="LibreOffice could not read this presentation "
                          "(corrupt or unsupported format).",
                ))
                continue
            pdf_path = produced[0]

            # Render pages with the shared PDF engine into a temp namer
            page_namer = OutputNamer(tmp)
            page_results = do_pdf_to_images(
                [str(pdf_path)], {"dpi": dpi, "format": fmt},
                page_namer, progress=None,
            )
            if not page_results or not page_results[0].ok:
                err = page_results[0].error if page_results else "render failed"
                results.append(Result(input=path, output=None, ok=False, error=err))
                continue
            pages: list[Path] = [
                Path(p) for p in (page_results[0].outputs or [page_results[0].output])
                if p
            ]

            # Repack as slide_001.png ... inside a zip
            stem = Path(path).stem
            zip_out = namer.unique(namer.output_dir / f"{stem}_slides.zip")
            with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
                for n, page in enumerate(sorted(pages), start=1):
                    zf.write(page, arcname=f"slide_{n:03d}{page.suffix}")
            r = Result(input=path, output=str(zip_out), ok=True,
                       note=f"{len(pages)} slide{'s' if len(pages) != 1 else ''}")
            r.outputs = [str(zip_out)]
            results.append(r)
            if progress:
                progress(i + 1, len(paths), Path(path).name)
        except UserError as exc:
            results.append(Result(input=path, output=None, ok=False, error=exc.message))
        except Exception as exc:  # noqa: BLE001
            get_logger().error("PPTX->images failed for %s: %s", path, exc)
            results.append(Result(
                input=path, output=None, ok=False,
                error=f"Could not convert {Path(path).name}: {exc}",
            ))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    return results
