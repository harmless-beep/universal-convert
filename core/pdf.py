"""PDF engine: page rendering, merge, split, compression, PDF->DOCX.

Backends:
  - PyMuPDF (fitz): rasterizing pages (all pages, any DPI), lossy compress
  - pypdf:           merge / split / lossless recompress (pure Python)
  - LibreOffice:     PDF -> DOCX (best effort)
  - internal:        text-extraction DOCX fallback if LibreOffice can't

Every backend failure degrades gracefully into a UserError or a Result
with an explanatory note - never a stack trace.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Callable

from .batch import CANCELLED, OutputNamer, Result, cancelled, run_batch
from .errors import UserError, get_logger

Progress = Callable[[int, int, str], None] | None

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - optional at import time
    fitz = None  # type: ignore[assignment]

try:
    import pypdf
except ImportError:  # pragma: no cover
    pypdf = None  # type: ignore[assignment]


def _require(name: str, module, hint: str):
    if module is None:
        raise UserError(f"{name} is not installed. {hint}")
    return module


def _open_pdf(path: str):
    _require("PyMuPDF", fitz, "Install it with: pip install PyMuPDF")
    try:
        doc = fitz.open(path)
    except FileNotFoundError:
        raise
    except Exception as exc:  # noqa: BLE001 - fitz raises many types
        raise UserError(
            f"Cannot read this PDF (corrupt or not a PDF):\n{path}"
        ) from exc
    if doc.needs_pass:
        doc.close()
        raise UserError(f"This PDF is password-protected:\n{path}")
    if doc.page_count == 0:
        doc.close()
        raise UserError(f"This PDF has no pages:\n{path}")
    return doc


def _page_name(stem: str, page_no: int, ext: str, digits: int = 3) -> str:
    return f"{stem}_p{page_no:0{digits}d}{ext}"


# --------------------------------------------------------------------------
# PDF -> images
# --------------------------------------------------------------------------

def do_pdf_to_images(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    dpi = int(opts.get("dpi", 150))
    dpi = min(max(dpi, 36), 1200)
    fmt = str(opts.get("format", "png")).lower()
    if fmt in ("jpeg", "jpg"):
        fmt = "jpg"
    if fmt not in ("png", "jpg"):
        raise UserError(f"Unsupported image format for pages: {fmt}")

    results: list[Result] = []

    if fitz is None:
        results = _pdf_to_images_libreoffice(paths, fmt, namer, progress)
        if results:
            return results
        raise UserError(
            "PDF to images needs PyMuPDF (not installed). "
            "Install it with: pip install PyMuPDF"
        )

    for path in paths:
        if cancelled():
            results.append(Result(input=path, output=None, ok=False,
                                  error=CANCELLED))
            continue
        try:
            doc = _open_pdf(path)
            stem = Path(path).stem
            total = doc.page_count
            outputs: list[str] = []
            scale = dpi / 72.0
            mat = fitz.Matrix(scale, scale)
            for i in range(total):
                page = doc[i]
                pix = page.get_pixmap(matrix=mat, alpha=False)
                out = namer.unique(namer.output_dir / _page_name(stem, i + 1, "." + fmt))
                if fmt == "jpg":
                    try:
                        data = pix.tobytes("jpeg", jpg_quality=90)
                    except TypeError:
                        data = pix.tobytes("jpeg")
                    out.write_bytes(data)
                else:
                    pix.save(str(out))
                outputs.append(str(out))
                if progress:
                    progress(i + 1, total, f"{Path(path).name} (page {i + 1}/{total})")
            doc.close()
            if not outputs:
                raise UserError(f"No pages could be rendered from {Path(path).name}")
            # one Result per input file, pointing at the first page (folder shown in UI)
            r = Result(input=path, output=outputs[0], ok=True)
            r.note = f"{len(outputs)} page{'s' if len(outputs) != 1 else ''} saved"
            r.outputs = outputs  # type: ignore[attr-defined]
            results.append(r)
        except UserError as exc:
            results.append(Result(input=path, output=None, ok=False, error=exc.message))
        except Exception as exc:  # noqa: BLE001
            get_logger().error("PDF render failed for %s: %s", path, exc)
            results.append(Result(
                input=path, output=None, ok=False,
                error=f"Could not render {Path(path).name}: {exc}",
            ))
    return results


def _pdf_to_images_libreoffice(
    paths: list[str], fmt: str, namer: OutputNamer, progress: Progress
) -> list[Result] | None:
    """Fallback: LibreOffice exports only the FIRST page of a PDF.

    Converts into a private temp dir first - writing straight into the
    output dir could clobber an existing file with the same stem.
    """
    import shutil
    import tempfile

    from .libreoffice import convert_to, find_soffice

    if find_soffice() is None:
        return None
    results: list[Result] = []
    tmp = Path(tempfile.mkdtemp(prefix="uc-lo-png-"))
    try:
        try:
            produced, missing = convert_to(
                [Path(p) for p in paths], fmt, tmp, strict=False
            )
        except UserError as exc:
            return [Result(input=p, output=None, ok=False, error=exc.message)
                    for p in paths]
        made_map = {p.name.lower(): p for p in produced}
        for path in paths:
            if cancelled():
                results.append(Result(input=path, output=None, ok=False,
                                      error=CANCELLED))
                continue
            src = made_map.get((Path(path).stem + "." + fmt).lower())
            if src and src.is_file():
                unique = namer.unique(
                    namer.output_dir / f"{Path(path).stem}_p1.{fmt}"
                )
                shutil.move(str(src), str(unique))
                r = Result(input=path, output=str(unique), ok=True)
                r.note = "LibreOffice fallback: only page 1 was converted"
                r.outputs = [str(unique)]
                results.append(r)
            else:
                results.append(Result(
                    input=path, output=None, ok=False,
                    error="LibreOffice could not convert this PDF "
                          "(corrupt or password-protected).",
                ))
            if progress:
                progress(1, 1, Path(path).name)
        del missing
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


# --------------------------------------------------------------------------
# Merge / split
# --------------------------------------------------------------------------

def do_pdf_merge(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    _require("pypdf", pypdf, "Install it with: pip install pypdf")
    if len(paths) < 2:
        raise UserError("Select at least two PDFs to merge.")
    for p in paths:
        if not Path(p).is_file():
            raise UserError(f"File not found:\n{p}")
    out_name = str(opts.get("output_name") or "merged.pdf")
    if not out_name.lower().endswith(".pdf"):
        out_name += ".pdf"
    out = namer.fixed(Path(out_name).name)

    writer = pypdf.PdfWriter()
    try:
        for i, p in enumerate(paths):
            reader = pypdf.PdfReader(p)
            if reader.is_encrypted:
                raise UserError(f"Cannot merge: {Path(p).name} is password-protected.")
            for page in reader.pages:
                writer.add_page(page)
            if progress:
                progress(i + 1, len(paths), Path(p).name)
        with open(out, "wb") as fh:
            writer.write(fh)
    except UserError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UserError(f"Could not merge the PDFs: {exc}") from exc

    return [Result(input=p, output=str(out), ok=True) for p in paths]


def parse_ranges(text: str, n_pages: int) -> list[int]:
    """'1-3,5' -> [0,1,2,4] (0-based). Raises friendly UserError."""
    pages: list[int] = []
    for chunk in str(text).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", chunk)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
        elif re.fullmatch(r"\d+", chunk):
            a = b = int(chunk)
        else:
            raise UserError(
                f"Could not read the page range '{chunk}'.\n"
                "Use formats like: 1-3,5,8"
            )
        if a < 1 or b < 1 or a > n_pages or b > n_pages:
            raise UserError(
                f"Page range '{chunk}' is out of bounds - "
                f"the document has {n_pages} page{'s' if n_pages != 1 else ''}."
            )
        if b < a:
            a, b = b, a
        pages.extend(range(a - 1, b))
    seen: set[int] = set()
    ordered = [p for p in pages if not (p in seen or seen.add(p))]
    if not ordered:
        raise UserError("No pages selected - enter something like 1-3,5")
    return ordered


def do_pdf_split(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    _require("pypdf", pypdf, "Install it with: pip install pypdf")
    mode = opts.get("mode", "range")  # "range" | "pages"
    results: list[Result] = []

    for path in paths:
        if cancelled():
            results.append(Result(input=path, output=None, ok=False,
                                  error=CANCELLED))
            continue
        try:
            reader = pypdf.PdfReader(path)
            if reader.is_encrypted:
                raise UserError(f"{Path(path).name} is password-protected.")
            n_pages = len(reader.pages)
            stem = Path(path).stem

            if mode == "pages":
                outs: list[str] = []
                for i in range(n_pages):
                    writer = pypdf.PdfWriter()
                    writer.add_page(reader.pages[i])
                    out = namer.unique(
                        namer.output_dir / _page_name(stem, i + 1, ".pdf", digits=3)
                    )
                    with open(out, "wb") as fh:
                        writer.write(fh)
                    outs.append(str(out))
                    if progress:
                        progress(i + 1, n_pages,
                                 f"{Path(path).name} (page {i + 1}/{n_pages})")
                r = Result(input=path, output=outs[0], ok=True)
                r.note = f"split into {len(outs)} files"
                r.outputs = outs  # type: ignore[attr-defined]
                results.append(r)
            else:
                wanted = parse_ranges(str(opts.get("ranges", "1")), n_pages)
                writer = pypdf.PdfWriter()
                for i in wanted:
                    writer.add_page(reader.pages[i])
                label = _ranges_label(wanted)
                out = namer.for_input(path, ".pdf", f"pages_{label}")
                with open(out, "wb") as fh:
                    writer.write(fh)
                r = Result(input=path, output=str(out), ok=True)
                r.note = f"pages {label}"
                r.outputs = [str(out)]  # type: ignore[attr-defined]
                results.append(r)
                if progress:
                    progress(1, 1, Path(path).name)
        except UserError as exc:
            results.append(Result(input=path, output=None, ok=False, error=exc.message))
        except Exception as exc:  # noqa: BLE001
            get_logger().error("Split failed for %s: %s", path, exc)
            results.append(Result(
                input=path, output=None, ok=False,
                error=f"Could not split {Path(path).name}: {exc}",
            ))
    return results


def _ranges_label(pages0: list[int]) -> str:
    """[0,1,2,4] -> '1-3_5' (compact, filesystem-safe)."""
    parts: list[str] = []
    start = prev = pages0[0]
    for p in pages0[1:] + [None]:  # type: ignore[list-item]
        if p is not None and p == prev + 1:
            prev = p
            continue
        parts.append(str(start + 1) if start == prev else f"{start + 1}-{prev + 1}")
        if p is not None:
            start = prev = p
    return "_".join(parts)


# --------------------------------------------------------------------------
# Compress
# --------------------------------------------------------------------------

def do_pdf_compress(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    lossy = bool(opts.get("lossy", False))
    quality = int(opts.get("quality", 75))
    dpi = int(opts.get("dpi", 120))

    def worker(path: str) -> str:
        out = namer.for_input(path, ".pdf", "compressed")
        if lossy and fitz is not None:
            doc = _open_pdf(path)
            try:
                if hasattr(doc, "rewrite_images"):
                    doc.rewrite_images(
                        dpi_threshold=max(dpi * 2, 200),
                        dpi_target=min(dpi, 150),
                        quality=min(max(quality, 5), 95),
                    )
                doc.save(str(out), garbage=4, deflate=True, clean=True)
            finally:
                doc.close()
        else:
            _lossless_compress(path, out)
        return str(out)

    results = run_batch(paths, _wrap_progress(worker, len(paths), progress))
    for r in results:
        if r.ok and r.output:
            before, after = Path(r.input).stat().st_size, Path(r.output).stat().st_size
            saved = before - after
            pct = round(saved / before * 100) if before else 0
            if saved > 0:
                r.note = f"-{saved // 1024} KB ({pct}%)"
            else:
                r.note = "already optimally compressed"
    return results


def _lossless_compress(path: str, out: Path) -> None:
    if fitz is not None:
        doc = _open_pdf(path)
        try:
            doc.save(str(out), garbage=4, deflate=True, clean=True,
                     deflate_images=True, deflate_fonts=True)
        finally:
            doc.close()
        return
    _require("pypdf", pypdf, "Install it with: pip install pypdf")
    reader = pypdf.PdfReader(path)
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    try:
        writer.compress_identical_objects(remove_identical=True)
    except AttributeError:
        pass
    with open(out, "wb") as fh:
        writer.write(fh)


# --------------------------------------------------------------------------
# PDF -> DOCX
# --------------------------------------------------------------------------

def do_pdf_to_docx(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    from .libreoffice import convert_to, find_soffice

    results: list[Result] = []
    for i, path in enumerate(paths):
        if cancelled():
            results.append(Result(input=path, output=None, ok=False,
                                  error=CANCELLED))
            continue
        out = namer.for_input(path, ".docx", "")
        note = ""
        converted = False

        if find_soffice() is not None:
            tmp = namer.output_dir / ".uc-tmp-pdfdocx"
            tmp.mkdir(exist_ok=True)
            try:
                produced, _ = convert_to([Path(path)], "docx", tmp)
                produced[0].replace(out)
                converted = out.is_file()
                note = "best-effort layout (LibreOffice)"
            except UserError as exc:
                get_logger().info("LO pdf->docx failed, using text fallback: %s",
                                  exc.message)
            finally:
                try:
                    tmp.rmdir()
                except OSError:
                    for leftover in tmp.glob("*"):
                        leftover.unlink(missing_ok=True)
                    tmp.rmdir()

        if not converted:
            _docx_from_pdf_text(path, out)
            note = "text-only fallback (layout not preserved)"

        r = Result(input=path, output=str(out), ok=True)
        r.note = note
        results.append(r)
        if progress:
            progress(i + 1, len(paths), Path(path).name)
    return results


def _docx_from_pdf_text(path: str, out: Path) -> None:
    """Minimal DOCX built from extracted text - no external deps."""
    _require("PyMuPDF", fitz,
             "Install it with: pip install PyMuPDF (for the text fallback)")
    doc = _open_pdf(path)
    paragraphs: list[str] = []
    try:
        for page in doc:
            paragraphs.extend(page.get_text("text").splitlines())
    finally:
        doc.close()
    _write_minimal_docx(out, paragraphs)


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _write_minimal_docx(out: Path, paragraphs: list[str]) -> None:
    body = []
    for line in paragraphs:
        if line.strip():
            body.append(
                "<w:p><w:r><w:t xml:space=\"preserve\">"
                + _xml_escape(line)
                + "</w:t></w:r></w:p>"
            )
        else:
            body.append("<w:p/>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        + "".join(body)
        + "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
        'package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats'
        '.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", rels)
            zf.writestr("word/document.xml", document)
    except OSError as exc:
        raise UserError(f"Could not write {out.name}: {exc}") from exc


def _wrap_progress(worker, total: int, progress: Progress):
    if progress is None:
        return worker
    state = {"i": 0}

    def wrapped(path: str) -> str:
        out = worker(path)
        state["i"] += 1
        progress(state["i"], total, Path(path).name)
        return out

    return wrapped
