"""Self-test suite: generates its own fixtures, asserts real outputs.

Run from anywhere:  python tests/selftest.py
Exit code 0 = all green. Uses only the project's own dependencies
(Pillow, PyMuPDF, pypdf) - no test frameworks.

Fixtures are built from scratch:
  images   - drawn with Pillow
  pdf      - written with PyMuPDF (3 pages, distinct text)
  docx/pptx/xlsx - minimal but valid OOXML zips (bare Office XML)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import detect  # noqa: E402
from core.batch import summarize  # noqa: E402
from core.runner import run_action  # noqa: E402
from core.settings import load_settings  # noqa: E402

PASS = 0
FAIL = 0
WORK = Path(tempfile.mkdtemp(prefix="uc-selftest-"))


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" -- {detail}" if detail else ""))


# --------------------------------------------------------------- fixtures
def make_fixtures() -> dict:
    from PIL import Image, ImageDraw

    fx = {}
    img_dir = WORK / "fixtures"
    img_dir.mkdir(parents=True, exist_ok=True)

    # two test images with distinct sizes
    for name, size, color in (("photo_a.png", (800, 600), (200, 60, 60)),
                              ("photo_b.png", (1200, 900), (60, 200, 60))):
        img = Image.new("RGB", size, color)
        d = ImageDraw.Draw(img)
        d.ellipse([50, 50, size[0] - 50, size[1] - 50], fill=(255, 255, 255))
        p = img_dir / name
        img.save(p)
        fx[name.split(".")[0]] = str(p)

    # transparent PNG (alpha flattening)
    alpha = Image.new("RGBA", (400, 400), (10, 10, 200, 120))
    p = img_dir / "alpha.png"
    alpha.save(p)
    fx["alpha"] = str(p)

    # 3-page PDF with text
    import fitz

    pdf = fitz.open()
    for i in range(3):
        page = pdf.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Page {i + 1} of selftest",
                         fontsize=24, fontname="helv")
    p = img_dir / "doc.pdf"
    pdf.save(str(p))
    pdf.close()
    fx["pdf"] = str(p)
    return fx


def make_office_fixtures() -> dict:
    """Minimal but schema-valid OOXML files (zip + bare XML)."""
    fx_dir = WORK / "fixtures"
    out = {}

    CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types">{}</Types>')
    RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package'
            '/2006/relationships"><Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="{target}"/></Relationships>')

    # ---- docx ----
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        '<w:p><w:r><w:t>Hello from the Universal Convert selftest.</w:t></w:r></w:p>'
        '</w:body></w:document>'
    )
    p = fx_dir / "sample.docx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("[Content_Types].xml", CT.format(
            '<Override PartName="/word/document.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.'
            'openxmlformats-package.relationships+xml"/>'))
        zf.writestr("_rels/.rels", RELS.format(target="word/document.xml"))
        zf.writestr("word/document.xml", doc_xml)
    out["docx"] = str(p)

    # ---- pptx (one slide) ----
    pres = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/'
            'presentationml/2006/main" xmlns:r="http://schemas.openxmlformats'
            '.org/officeDocument/2006/relationships"/>')
    slide = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<p:sld xmlns:p="http://schemas.openxmlformats.org/'
             'presentationml/2006/main"><p:cSld/></p:sld>')
    p = fx_dir / "deck.pptx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("[Content_Types].xml", CT.format(
            '<Override PartName="/ppt/presentation.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.presentationml.'
            'presentation.main+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.presentationml.'
            'slide+xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.'
            'openxmlformats-package.relationships+xml"/>'))
        zf.writestr("_rels/.rels", RELS.format(target="ppt/presentation.xml"))
        zf.writestr("ppt/presentation.xml", pres)
        zf.writestr("ppt/slides/slide1.xml", slide)
    out["pptx"] = str(p)

    # ---- xlsx ----
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main"><sheetData/></worksheet>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
          '2006/main" xmlns:r="http://schemas.openxmlformats.org/'
          'officeDocument/2006/relationships"><sheets><sheet name="S1" '
          'sheetId="1" r:id="rId1"/></sheets></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/'
               'package/2006/relationships"><Relationship Id="rId1" '
               'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
               'relationships/worksheet" Target="sheets/sheet1.xml"/>'
               '</Relationships>')
    p = fx_dir / "book.xlsx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("[Content_Types].xml", CT.format(
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.spreadsheetml.'
            'worksheet+xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.'
            'openxmlformats-package.relationships+xml"/>'))
        zf.writestr("_rels/.rels", RELS.format(target="xl/workbook.xml"))
        zf.writestr("xl/workbook.xml", wb)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    out["xlsx"] = str(p)
    return out


# ------------------------------------------------------------------ tests
def outdir_for(name: str) -> Path:
    d = WORK / "out" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_for(outdir: Path):
    s = load_settings()
    s.set("output.folder_mode", "custom")
    s.set("output.custom_path", str(outdir))
    s.set("output.open_when_done", False)  # never pop explorer during tests
    s.set("output.notify", False)
    return s


def test_detection(fx):
    print("\n== detection ==")
    a = detect.actions_for([fx["photo_a"]])
    check("single image offers resize/compress/convert",
          {x.id for x in a} >= {"resize", "compress", "convert"})

    a = detect.actions_for([fx["pdf"]])
    ids = {x.id for x in a}
    check("single pdf: no merge", "pdf_merge" not in ids and "pdf_split" in ids)

    a = detect.actions_for([fx["pdf"], fx["pdf"]])
    check("two pdfs: merge offered", "pdf_merge" in {x.id for x in a})

    a = detect.actions_for([fx["docx"], fx["pptx"]])
    check("mixed office: office_to_pdf, no pptx_to_images",
          "office_to_pdf" in {x.id for x in a}
          and "pptx_to_images" not in {x.id for x in a})

    a = detect.actions_for([fx["docx"], fx["pptx"]])
    check("pptx alone: slide images offered",
          "pptx_to_images" in {x.id for x in detect.actions_for([fx["pptx"]])})

    a = detect.actions_for(["notes.txt"])
    check("txt only: no actions", a == [])


def test_images(fx):
    from PIL import Image

    print("\n== image actions ==")
    s = settings_for(outdir_for("img"))

    results = run_action("resize", [fx["photo_a"]],
                         {"mode": "pixels", "width": 320, "keep_aspect": True}, s)
    check("resize to 320px wide", results[0].ok and
          Image.open(results[0].output).size == (320, 240),
          str([r.error for r in results]))

    results = run_action("resize", [fx["photo_a"]],
                         {"mode": "percent", "percent": 50}, s)
    check("resize 50%", results[0].ok and
          Image.open(results[0].output).size == (400, 300),
          str([r.error for r in results]))

    results = run_action("resize", [fx["photo_a"]],
                         {"mode": "preset", "preset": "thumbnail"}, s)
    check("resize preset thumbnail<=256", results[0].ok and
          max(Image.open(results[0].output).size) <= 256,
          str([r.error for r in results]))

    results = run_action("compress", [fx["photo_a"]],
                         {"quality": 60, "auto": False}, s)
    out_file = results[0].output if results[0].ok else ""
    check("compress writes an output file",
          bool(out_file) and Path(out_file).is_file()
          and Path(out_file).suffix == ".png",
          str([r.error for r in results]))

    results = run_action("compress", [fx["alpha"]],
                         {"quality": 60, "auto": False}, s)
    check("compress with alpha", results[0].ok, str([r.error for r in results]))

    results = run_action("convert", [fx["alpha"]],
                         {"format": "jpg", "combined": True}, s)
    ok_jpg = results[0].ok and results[0].output.endswith(".jpg")
    no_alpha = ok_jpg and Image.open(results[0].output).mode == "RGB"
    check("convert RGBA->JPG flattens", no_alpha, str([r.error for r in results]))

    results = run_action("convert", [fx["photo_a"], fx["photo_b"]],
                         {"format": "pdf", "combined": True}, s)
    import fitz
    one_pdf = results[0].ok and results[0].output == results[1].output
    pages = fitz.open(results[0].output).page_count if one_pdf else 0
    check("images -> one combined PDF (2 pages)", one_pdf and pages == 2,
          str([r.error for r in results]))

    results = run_action("convert", [fx["photo_a"], fx["photo_b"]],
                         {"format": "pdf", "combined": False}, s)
    check("images -> separate PDFs", results[0].ok and results[1].ok
          and results[0].output != results[1].output,
          str([r.error for r in results]))

    # corrupt file -> friendly per-file failure, batch survives
    bad = outdir_for("img") / "corrupt.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage" * 10)
    results = run_action("convert", [str(bad), fx["photo_a"]],
                         {"format": "webp", "combined": True}, s)
    check("corrupt image fails friendly, batch survives",
          (not results[0].ok) and results[1].ok
          and "corrupt" in results[0].error.lower(),
          str([(r.ok, r.error) for r in results]))


def test_pdf(fx):
    import fitz

    print("\n== pdf actions ==")
    s = settings_for(outdir_for("pdf"))

    results = run_action("pdf_to_images", [fx["pdf"]],
                         {"dpi": 96, "format": "png"}, s)
    r = results[0]
    check("pdf -> 3 png pages", r.ok and len(getattr(r, "outputs", []) or []) == 3,
          str([x.error for x in results]))

    results = run_action("pdf_to_images", [fx["pdf"]],
                         {"dpi": 150, "format": "jpg"}, s)
    r = results[0]
    outs = getattr(r, "outputs", []) or []
    check("pdf -> 3 jpg pages", r.ok and len(outs) == 3
          and outs[0].endswith(".jpg"), str([x.error for x in results]))

    # merge: pdf + itself
    results = run_action("pdf_merge", [fx["pdf"], fx["pdf"]],
                         {"output_name": "merged.pdf"}, s)
    merged = results[0].output if results and results[0].ok else None
    check("merge 2 pdfs -> 6 pages",
          merged and fitz.open(merged).page_count == 6,
          str([x.error for x in results]))

    # split ranges
    results = run_action("pdf_split", [fx["pdf"]],
                         {"mode": "range", "ranges": "2-3"}, s)
    out = results[0].output if results[0].ok else None
    check("split ranges 2-3 -> 2 pages",
          out and fitz.open(out).page_count == 2,
          str([x.error for x in results]))

    # split every page
    results = run_action("pdf_split", [fx["pdf"]], {"mode": "pages"}, s)
    r = results[0]
    outs = getattr(r, "outputs", []) or []
    check("split every page -> 3 files", r.ok and len(outs) == 3,
          str([x.error for x in results]))

    # invalid range -> friendly error
    results = run_action("pdf_split", [fx["pdf"]],
                         {"mode": "range", "ranges": "99"}, s)
    check("invalid range -> friendly failure",
          not results[0].ok and "out of bounds" in results[0].error,
          str([x.error for x in results]))

    # compress (lossless)
    results = run_action("pdf_compress", [fx["pdf"]],
                         {"lossy": False, "quality": 75}, s)
    check("pdf compress (lossless)", results[0].ok
          and Path(results[0].output).stat().st_size > 0,
          str([x.error for x in results]))

    # password-protected pdf -> friendly
    locked = outdir_for("pdf") / "locked.pdf"
    try:
        src = fitz.open(fx["pdf"])
        src.save(str(locked), encryption=fitz.PDF_ENCRYPT_AES_256,
                 owner_pw="x", user_pw="x")
        src.close()
        results = run_action("pdf_to_images", [str(locked)],
                             {"dpi": 96, "format": "png"}, s)
        check("password pdf -> friendly failure",
              not results[0].ok and "password" in results[0].error.lower(),
              str([x.error for x in results]))
    except Exception as exc:  # noqa: BLE001
        check("password pdf fixture", False, repr(exc))


def test_office(fx, office):
    import fitz

    print("\n== office actions (LibreOffice) ==")
    from core.libreoffice import find_soffice

    if find_soffice() is None:
        print("  [SKIP] LibreOffice not installed - office tests skipped")
        return

    s = settings_for(outdir_for("office"))

    results = run_action("office_to_pdf", [office["docx"]], {}, s)
    ok1 = results[0].ok and results[0].output.endswith(".pdf")
    check("docx -> pdf", ok1, str([x.error for x in results]))

    results = run_action("office_to_pdf", [office["xlsx"]], {}, s)
    check("xlsx -> pdf", results[0].ok, str([x.error for x in results]))

    results = run_action("office_to_pdf", [office["pptx"]], {}, s)
    check("pptx -> pdf", results[0].ok, str([x.error for x in results]))

    results = run_action("pptx_to_images", [office["pptx"]],
                         {"dpi": 96, "format": "png"}, s)
    r = results[0]
    is_zip = r.ok and r.output.endswith(".zip")
    contains = is_zip and zipfile.ZipFile(r.output).namelist()[0].startswith("slide_")
    check("pptx -> slide images zip", is_zip and contains,
          str([x.error for x in results]))

    results = run_action("pdf_to_docx", [fx["pdf"]], {}, s)
    check("pdf -> docx (LO or text fallback)", results[0].ok
          and Path(results[0].output).stat().st_size > 100,
          str([x.error for x in results]))


def test_robustness(fx):
    """One bad file / a cancelled run must never poison the whole batch."""
    import threading

    print("\n== robustness ==")
    s = settings_for(outdir_for("robust"))
    resize = {"mode": "pixels", "width": 160, "keep_aspect": True}

    ghost = str(WORK / "fixtures" / "gone.png")
    results = run_action("resize", [fx["photo_a"], ghost, fx["photo_b"]],
                         dict(resize), s)
    check("missing file fails on its own, batch continues",
          len(results) == 3 and results[0].ok and not results[1].ok
          and results[2].ok,
          str([(r.input, r.ok) for r in results]))
    check("missing file says why", "not found" in results[1].error.lower(),
          results[1].error)
    check("selection order preserved",
          [Path(r.input).name for r in results]
          == ["photo_a.png", "gone.png", "photo_b.png"],
          str([r.input for r in results]))

    out_dir = outdir_for("robust")
    written = set(out_dir.glob("*"))

    armed = threading.Event()
    armed.set()
    results = run_action("resize", [fx["photo_a"], fx["photo_b"]],
                         dict(resize), s, cancel=armed)
    check("cancel before the start: every file reported, nothing written",
          len(results) == 2 and all("Cancelled" in r.error for r in results)
          and set(out_dir.glob("*")) == written,
          str([(r.ok, r.error) for r in results]))
    check("summary reports a stopped run",
          summarize(results).startswith("Stopped after 0 of 2"),
          summarize(results))

    after_one = threading.Event()

    def stop_after_first(done: int, _total: int, _name: str) -> None:
        if done >= 1:
            after_one.set()

    results = run_action("resize", [fx["photo_a"], fx["photo_b"], fx["alpha"]],
                         {"mode": "pixels", "width": 100, "keep_aspect": True},
                         s, progress=stop_after_first, cancel=after_one)
    ok = [r for r in results if r.ok]
    stopped = [r for r in results if "Cancelled" in r.error]
    check("cancel mid-run stops between files (no half-written output)",
          len(results) == 3 and len(ok) == 1 and len(stopped) == 2,
          str([(Path(r.input).name, r.ok, r.error) for r in results]))
    check("stopped run counts are honest",
          summarize(results).startswith("Stopped after 1 of 3"),
          summarize(results))

    # the cancel switch must not leak into the next run
    results = run_action("resize", [fx["photo_a"]], dict(resize), s)
    check("cancel state cleared for the next run", results[0].ok,
          str([r.error for r in results]))


def test_aggregation():
    print("\n== aggregation (Windows multi-select) ==")
    if sys.platform != "win32":
        print("  [SKIP] Windows-only path")
        return
    files = [str(WORK / "fixtures" / "photo_a.png")]
    proc = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--probe", *files],
        capture_output=True, text=True, timeout=30, cwd=str(ROOT),
    )
    lines = proc.stdout.strip().splitlines()
    check("single instance probe returns its file",
          proc.returncode == 0 and lines and lines[0].startswith("PROBE-FILES:")
          and files[0] in proc.stdout, proc.stdout + proc.stderr)

    # 3 concurrent single-file probes -> exactly one owner reports all 3
    env_files = [str(WORK / "fixtures" / "photo_a.png"),
                 str(WORK / "fixtures" / "photo_b.png"),
                 str(WORK / "fixtures" / "alpha.png")]
    procs = [subprocess.Popen(
        [sys.executable, str(ROOT / "main.py"), "--probe", f],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=str(ROOT)) for f in env_files]
    outs = [p.communicate(timeout=30)[0] for p in procs]
    owners = [o for o in outs if o.count("\n") >= 3]
    check("3 concurrent probes -> exactly 1 owner collects all 3",
          len(owners) == 1 and all(f in owners[0] for f in env_files),
          repr(outs))


def test_cli(fx):
    print("\n== CLI ==")
    out = WORK / "cli-out"
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--cli", "--action", "resize",
         "--width", "200", "--out", f"custom:{out}", fx["photo_a"]],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    made = list(out.glob("photo_a*resized*.png"))
    check("cli resize", proc.returncode == 0 and made,
          proc.stdout + proc.stderr)

    proc = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--info", fx["pdf"]],
        capture_output=True, text=True, timeout=30, cwd=str(ROOT),
    )
    check("cli --info", proc.returncode == 0 and "pdf_split" in proc.stdout,
          proc.stdout + proc.stderr)

    notes = WORK / "notes.txt"
    notes.write_text("not an image", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--cli", "--action", "resize",
         "--width", "120", "--out", f"custom:{out}", fx["photo_a"], str(notes)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    check("cli skips unsupported files",
          proc.returncode == 0 and "Skipping 1 unsupported" in proc.stdout
          and "FAIL" not in proc.stdout,
          proc.stdout + proc.stderr)

    bad = WORK / "bad.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage" * 5)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--cli", "--action", "convert",
         "--format", "jpg", "--out", f"custom:{out}", str(bad)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    check("cli prints why a file failed",
          proc.returncode == 1 and "FAIL" in proc.stdout
          and "bad.png ->" in proc.stdout,
          proc.stdout + proc.stderr)


def main() -> int:
    print(f"Universal Convert selftest  (workdir: {WORK})")
    fx = make_fixtures()
    office = make_office_fixtures()
    everything = {**fx, **office}

    test_detection(everything)
    test_images(fx)
    test_pdf(fx)
    test_office(fx, office)
    test_robustness(fx)
    test_aggregation()
    test_cli(fx)

    print(f"\nRESULT: {PASS} passed, {FAIL} failed")
    shutil.rmtree(WORK, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
