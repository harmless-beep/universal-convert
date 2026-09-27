# Universal Convert

A cross-platform **"Convert With..."** right-click menu entry for Windows, macOS and
Linux. Select any file (or a whole batch), right-click, and a small dialog offers
exactly the conversions that make sense for what you selected.

```
Images (.jpg .jpeg .png .webp .gif .bmp .tiff)
  Resize (exact pixels / percentage / preset: Web-1920, Email-1024,
          Print-A4@300dpi, Thumbnail-256 - presets editable in config)
  Compress (quality 1-100, or auto-optimize with optional target size)
  Convert format (PNG <-> JPG <-> WEBP <-> PDF, per-image or combined)

PDFs (.pdf)
  To images (one per page, PNG/JPG, 96/150/300 DPI)
  To DOCX (best-effort, editable)
  Compress (lossless, or lossy re-render)
  Merge (2+ PDFs)  /  Split (page ranges like 1-3,5 or one file per page)

Office (.docx .pptx .xlsx, plus .doc/.xls/.odp/.odt/.ods)
  To PDF  (LibreOffice headless - no Microsoft Office needed)
  PPTX -> slide images (one PNG per slide, packed as .zip)
```

Batch mode everywhere: select 50 files, get one dialog, one progress bar,
and a per-file results list. One corrupt file never aborts the batch.

---

## Install

| OS | Command | Where the entry appears |
|----|---------|--------------------------|
| **Windows** | `powershell -ExecutionPolicy Bypass -File installers/windows.ps1` | Right-click file → **Convert With...** (Win11: under *Show more options*) |
| **macOS** | `bash installers/macos.sh` | Finder → right-click → **Quick Actions** → Convert With... |
| **Linux** | `bash installers/linux.sh` | GNOME Files: right-click → **Scripts** → Convert With... · Dolphin: right-click → Convert With... |

Each installer checks Python, installs `pypdf` + `PyMuPDF` via pip, offers to
install LibreOffice if document conversions are missing, and registers the menu
entry **for the current user only** (no admin rights). Every installer supports
`--uninstall` / `-Uninstall` (config files are kept).

**Requirements:** Python 3.9+ with tkinter (python.org / python3-tk packages
include it), `pip install Pillow pypdf PyMuPDF` (installer does this),
[LibreOffice](https://www.libreoffice.org/) only for Office/PDF *document*
conversions — image actions work without it.

---

## How the pieces connect

```
right-click
   │
   ▼
main.py ────────────── platform_util/aggregate.py
   │     (Windows quirk: Explorer launches ONE process PER selected file.
   │      The first process becomes the "owner", the others hand it their
   │      file paths through a locked queue file and exit. After a short
   │      debounce the owner shows ONE dialog with the whole selection.
   │      macOS/Linux pass all files in one invocation - no aggregation.)
   ▼
ui/dialog.py  ── asks: which action + options? (only valid ones are listed;
   │             options pre-filled from your last run)
   ▼
core/runner.py  ── validates the selection, resolves the output folder
   │              (subfolder / next-to-originals / custom) and dispatches:
   ▼
core/images.py ──── Pillow: resize, compress, format convert, image→PDF
core/pdf.py ─────── PyMuPDF: pages→images, lossy compress
                    pypdf: merge / split / lossless compress
                    LibreOffice or pure-Python fallback: PDF→DOCX
core/documents.py ─ LibreOffice headless: DOCX/PPTX/XLSX→PDF, PPTX→slide zip
   │
   ▼
platform_util/notify.py     toast / osascript / notify-send
platform_util/openfolder.py opens the output folder, file selected
```

**File by file:**

| Path | What it does |
|------|--------------|
| `main.py` | Entry point. Aggregates the multi-selection, shows the dialog, provides `--cli`, `--info`, `--probe` modes. Last-resort exception trap keeps stack traces away from users. |
| `core/errors.py` | `UserError` = "safe to show the user". Everything else is logged to `logs/universal-convert.log` and reported as a friendly message. |
| `core/settings.py` | Shipped defaults (`config/settings.json`) deep-merged with your overrides in the OS-appropriate config dir; remembers last-used options per action. |
| `core/detect.py` | Maps file extensions → action catalog. An action is offered only if it can consume **every** supported selected file (intersection rule); unsupported files are skipped with a visible note. |
| `core/batch.py` | Output folder resolution, collision-free naming (`photo (1).jpg`, never overwrites), and the per-file batch runner that survives individual failures. |
| `core/images.py` | All Pillow work: LANCZOS resize (incl. animated GIFs frame-by-frame), EXIF orientation fix, alpha flattening for JPG, auto-optimize quality ladder. |
| `core/pdf.py` | PyMuPDF renders every page at any DPI; pypdf merges/splits/recompresses; PDF→DOCX uses LibreOffice and falls back to a text-only DOCX it builds itself. |
| `core/documents.py` | LibreOffice conversions. Converts into a private temp dir, then moves results through the collision-safe namer (LO would silently overwrite). Same-stem files are converted in separate LO calls to avoid output collisions. |
| `core/libreoffice.py` | Finds `soffice` on all three OSes, runs it with an isolated profile (`-env:UserInstallation=...`) so it never fights an open LibreOffice window, turns cryptic failures into friendly messages. |
| `core/runner.py` | The single dispatch point used by dialog, CLI and tests. |
| `ui/dialog.py` | The Tk window: action radios, per-action option panels, progress bar, results view. Conversion runs on a worker thread; Tk polls plain state (thread-safe pattern). |
| `platform_util/aggregate.py` | The Windows one-process-per-file problem, solved with a lock-protected queue file + earliest-timestamp owner election (pure stdlib, no helper EXEs). |
| `platform_util/notify.py` | Success toast: PowerShell WinRT toast / `osascript` / `notify-send`. |
| `platform_util/openfolder.py` | `explorer /select` / `open -R` / `xdg-open`. |
| `installers/windows.ps1` | Registry verb under `HKCU\Software\Classes\*\shell\ConvertWith` (`MultiSelectModel=Document`), Python discovery, pip deps, optional winget LibreOffice, `-Uninstall`. |
| `installers/macos.sh` | Generates a real Automator Quick Action bundle (`~/Library/Services/Convert With....workflow`) programmatically: NSServices plist + Run-Shell-Script wflow, plus stable launcher wrappers and services-cache refresh. |
| `installers/linux.sh` | Nautilus script (`~/.local/share/nautilus/scripts/`), KDE Dolphin service-menu `.desktop`, generic `.desktop` launcher, uninstall. |
| `config/settings.json` | Preset sizes, default quality/DPI, output behavior. Edit freely — upgrades keep your changes. |
| `tests/selftest.py` | 27 assertions across detection, every image/PDF action, error paths, aggregation and CLI. Generates its own fixtures (images, 3-page PDF, minimal DOCX/PPTX/XLSX) — zero extra test dependencies. |

---

## CLI

The dialog is the everyday interface, but everything works headless too:

```bash
python main.py --info photo.jpg                     # what actions are valid?
python main.py --cli --action resize --width 800 photo.jpg
python main.py --cli --action compress --auto-optimize --quality 85 *.png
python main.py --cli --action convert --format pdf a.png b.png   # combined PDF
python main.py --cli --action pdf_split --ranges 1-3,5 doc.pdf
python main.py --cli --action pdf_merge a.pdf b.pdf
python main.py --cli --action office_to_pdf report.docx
python main.py --cli --action pptx_to_images deck.pptx
```

## Settings

User settings live at:

- Windows: `%APPDATA%\UniversalConvert\settings.json`
- macOS: `~/Library/Application Support/UniversalConvert/settings.json`
- Linux: `~/.config/universal-convert/settings.json`

Everything is optional; delete the file to reset. `presets` values can be an
int (long-edge pixels) or a paper spec like `"A4@300"` (A4 at 300 DPI; A3 and
Letter available).

## Notes & limitations

- **Windows 11**: registry context entries live under *Show more options*
  (or press `Shift+F10`). This is standard for all non-shell-extension menus.
- **PDF→DOCX** is best-effort by nature: LibreOffice reconstruction first,
  a text-only DOCX fallback second. Scanned PDFs contain no text.
- **PNG "compress"** is lossless: smaller files come from better compression
  effort, never worse pixels. Convert to JPG/WEBP for real size wins.
- LibreOffice conversion quality varies by document; password-protected and
  heavily-styled files may degrade.
- The macOS/Linux installers are generated and structurally validated here
  (plist parsing, `bash -n`) but need a real Mac/Linux box for end-to-end
  confirmation — see the checklist below.

## Verification checklist for macOS / Linux

macOS:
1. `bash installers/macos.sh` (will ask for password once, for `/usr/local/bin` wrappers)
2. Finder → select 2+ images → right-click → Quick Actions → Convert With...
3. If missing: System Settings → Privacy & Security → Extensions → Finder →
   enable "Convert With...". Log out/in if still absent.

Linux (GNOME):
1. `bash installers/linux.sh`, then `nautilus -q`
2. Select files → right-click → Scripts → Convert With...

Linux (KDE):
1. Same installer; Dolphin → right-click → Convert With...

## Development

```bash
python tests/selftest.py     # full suite, exit code 0 = green
python main.py --probe file  # prints the aggregated selection (IPC test)
```
