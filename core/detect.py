"""File-type detection and the action catalog.

One place decides what can be done with which files:
  - categorize(paths)      -> buckets (images / pdfs / office / other)
  - actions_for(paths)     -> ordered list of Action defs valid for the SELECTION

An action is only offered when it applies to *every* selected file (intersection
rule), so a mixed selection of .png + .pdf shows only what can consume both -
the dialog prints a note when actions were hidden because of incompatible files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
PDF_EXTS = {".pdf"}
# Spec lists .docx/.pptx/.xlsx; legacy + LibreOffice formats included since
# LibreOffice headless converts them just as well.
PPTX_EXTS = {".pptx", ".ppt", ".odp"}
DOCX_EXTS = {".docx", ".doc", ".odt"}
XLSX_EXTS = {".xlsx", ".xls", ".ods"}
OFFICE_EXTS = PPTX_EXTS | DOCX_EXTS | XLSX_EXTS


@dataclass
class Categorization:
    images: list[str] = field(default_factory=list)
    pdfs: list[str] = field(default_factory=list)
    office: list[str] = field(default_factory=list)   # docx/xlsx (non-pptx)
    pptx: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)

    @property
    def all_paths(self) -> list[str]:
        return self.images + self.pdfs + self.office + self.pptx + self.other

    @property
    def office_all(self) -> list[str]:
        """Every office-ish file (pptx included) - what office_to_pdf consumes."""
        return self.office + self.pptx

    @property
    def supported(self) -> list[str]:
        """Files this tool can do anything with (unsupported are skipped)."""
        return self.images + self.pdfs + self.office + self.pptx

    def counts_line(self, n_files: int) -> str:
        """Summary like '3 files: 2 images, 1 PDF' for the dialog header."""
        parts: list[str] = []
        if self.images:
            parts.append(f"{len(self.images)} image{'s' if len(self.images) != 1 else ''}")
        if self.pdfs:
            parts.append(f"{len(self.pdfs)} PDF{'s' if len(self.pdfs) != 1 else ''}")
        if self.office_all:
            parts.append(
                f"{len(self.office_all)} document{'s' if len(self.office_all) != 1 else ''}"
            )
        if self.other:
            parts.append(f"{len(self.other)} other")
        label = ", ".join(parts) if parts else "no supported files"
        return f"{n_files} file{'s' if n_files != 1 else ''}: {label}"


def ext_of(path: str) -> str:
    return Path(path).suffix.lower()


def categorize(paths: list[str]) -> Categorization:
    cat = Categorization()
    for p in paths:
        ext = ext_of(p)
        if ext in IMAGE_EXTS:
            cat.images.append(p)
        elif ext in PDF_EXTS:
            cat.pdfs.append(p)
        elif ext in PPTX_EXTS:
            cat.pptx.append(p)
        elif ext in OFFICE_EXTS:
            cat.office.append(p)
        else:
            cat.other.append(p)
    return cat


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    description: str = ""


# Ordered catalog; `applies` decides selection eligibility.
def actions_for(paths: list[str]) -> list[Action]:
    cat = categorize(paths)
    if not paths:
        return []

    actions: list[Action] = []
    supported = cat.supported
    n = len(supported)
    if n == 0:
        return []

    def all_of(buckets: tuple[list[str], ...]) -> bool:
        # An action applies only when every *supported* selected file belongs
        # to one of the listed buckets (mixed-type selections drop actions
        # that can't consume the whole selection).
        return sum(len(b) for b in buckets) == n

    # --- images ---------------------------------------------------------
    if all_of((cat.images,)) and cat.images:
        actions += [
            Action("resize", "Resize images",
                   "Exact pixels, percentage, or preset (Web/Email/Print/Thumbnail)"),
            Action("compress", "Compress images",
                   "Quality slider 1-100, or auto-optimize"),
            Action("convert", "Convert image format",
                   "PNG <-> JPG <-> WEBP <-> PDF"),
        ]

    # --- PDFs -----------------------------------------------------------
    if all_of((cat.pdfs,)) and cat.pdfs:
        actions += [
            Action("pdf_to_images", "PDF -> images",
                   "One image per page (PNG or JPG)"),
            Action("pdf_to_docx", "PDF -> DOCX",
                   "Editable document, best-effort layout (LibreOffice)"),
            Action("pdf_compress", "Compress PDF",
                   "Lossless, or lossy re-render at lower quality"),
        ]
        if len(cat.pdfs) >= 2:
            actions.append(
                Action("pdf_merge", "Merge PDFs",
                       "Combine the selected PDFs into one file")
            )
        actions.append(
            Action("pdf_split", "Split PDF",
                   "Extract page ranges, or one file per page")
        )

    # --- Office ---------------------------------------------------------
    if all_of((cat.office, cat.pptx)) and cat.office_all:
        actions.append(
            Action("office_to_pdf", "Office -> PDF",
                   "DOCX / PPTX / XLSX to PDF (LibreOffice headless)")
        )
        if cat.pptx and not cat.office:
            actions.append(
                Action("pptx_to_images", "PPTX -> slide images",
                       "One PNG per slide, packed into a zip")
            )

    return actions


def action_by_id(action_id: str) -> Action | None:
    for a in all_actions():
        if a.id == action_id:
            return a
    return None


def all_actions() -> list[Action]:
    """Full catalog (used by CLI help and tests)."""
    return [
        Action("resize", "Resize images"),
        Action("compress", "Compress images"),
        Action("convert", "Convert image format"),
        Action("pdf_to_images", "PDF -> images"),
        Action("pdf_to_docx", "PDF -> DOCX"),
        Action("pdf_compress", "Compress PDF"),
        Action("pdf_merge", "Merge PDFs"),
        Action("pdf_split", "Split PDF"),
        Action("office_to_pdf", "Office -> PDF"),
        Action("pptx_to_images", "PPTX -> slide images"),
    ]
