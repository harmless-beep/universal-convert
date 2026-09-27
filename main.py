"""Universal Convert entry point.

Wires together the three frontends:
  - right-click menu: Explorer launches one process PER FILE on Windows, so
    platform_util.aggregate elects an owner that collects the whole selection
  - CLI (main.py --cli ...) used by tests/selftest.py and power users
  - GUI dialog (default when files come from the context menu)

Also provides --probe for the aggregation test and --info to inspect
what actions would be offered for a selection.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make imports work no matter how we're launched (registry verb, double-click,
# shell, tests): everything is relative to this file's directory.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import detect  # noqa: E402
from core.errors import (  # noqa: E402
    APP_NAME,
    LOG_FILE,
    UserError,
    describe_paths,
    friendly_message,
    get_logger,
    log_exception,
)
from core.settings import load_settings  # noqa: E402

PROG = "Universal Convert"


def show_error_box(message: str) -> None:
    """Never let an error reach the user as a traceback."""
    print(message, file=sys.stderr or sys.__stderr__ or sys.stdout)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(PROG, message)
        root.destroy()
    except Exception:  # noqa: BLE001 - pythonw may have no display at all
        pass


def show_info_box(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(PROG, message)
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


def run_gui(files: list[str]) -> int:
    """Open the dialog for the aggregated selection."""
    # Tk first: dialog.py imports tkinter at module import time.
    from ui.dialog import ConversionDialog

    settings = load_settings()
    agg = settings.get("aggregation", {})
    files = platform_gather(files, agg)
    if not files:
        return 0  # another instance owns this batch
    if not any(Path(f).is_file() for f in files):
        show_error_box(
            "The selected items could not be found (moved, renamed, or "
            "on a disconnected drive?)."
        )
        return 1

    dialog = ConversionDialog(files, settings)
    dialog.run()
    return 0


def platform_gather(files: list[str], agg_cfg: dict) -> list[str] | None:
    from platform_util.aggregate import gather

    return gather(
        files,
        debounce_ms=int(agg_cfg.get("debounce_ms", 500)),
        max_wait_ms=int(agg_cfg.get("max_wait_ms", 1500)),
    )


def build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="Convert files from the right-click menu or the command line.",
    )
    p.add_argument("files", nargs="*", help="files to convert")
    p.add_argument("--cli", action="store_true",
                   help="headless mode: convert immediately, no dialog")
    p.add_argument("--info", action="store_true",
                   help="show what actions are available for the selection")
    p.add_argument("--probe", action="store_true",
                   help="internal: aggregation test - print collected files")
    p.add_argument("--no-gui", action="store_true",
                   help="same as --cli (alias)")
    p.add_argument("--action", help="action id (see --info)")
    p.add_argument("--out", help="output mode: subfolder|same|custom[:PATH]")
    p.add_argument("--width", type=int, help="resize width in pixels")
    p.add_argument("--height", type=int, help="resize height in pixels")
    p.add_argument("--percent", type=float, help="resize by percentage")
    p.add_argument("--preset", help="resize preset: web|email|print|thumbnail")
    p.add_argument("--quality", type=int, help="compression quality 1-100")
    p.add_argument("--auto-optimize", action="store_true", dest="auto_optimize",
                   help="auto-optimize images instead of fixed quality")
    p.add_argument("--format", help="target format (png|jpg|webp|pdf)")
    p.add_argument("--dpi", type=int, help="rendering DPI for PDF -> images")
    p.add_argument("--ranges", help="page ranges for split, e.g. 1-3,5")
    p.add_argument("--pages", action="store_true",
                   help="split mode: one file per page")
    p.add_argument("--lossy", action="store_true",
                   help="lossy PDF compression (re-render images)")
    p.add_argument("--pdf-pages", action="store_true",
                   help="image -> PDF: one PDF per image (default: combined)")
    return p


def cli_opts(args: argparse.Namespace) -> dict:
    """Translate CLI flags into the same opts dict the dialog produces."""
    opts: dict = {}
    a = args.action
    if a == "resize":
        if args.percent is not None:
            opts.update(mode="percent", percent=args.percent)
        elif args.preset:
            opts.update(mode="preset", preset=args.preset)
        else:
            opts.update(mode="pixels", width=args.width or 1920,
                        height=args.height, keep_aspect=True)
    elif a == "compress":
        opts.update(quality=args.quality or 85, auto=bool(args.auto_optimize))
    elif a == "convert":
        opts.update(format=args.format or "jpg", combined=not args.pdf_pages)
    elif a == "pdf_to_images":
        opts.update(dpi=args.dpi or 150, format=args.format or "png")
    elif a == "pdf_compress":
        opts.update(lossy=bool(args.lossy), quality=args.quality or 75)
    elif a == "pdf_split":
        opts.update(mode="pages" if args.pages else "range",
                    ranges=args.ranges or "1")
    elif a == "pdf_merge":
        opts.update(output_name="merged.pdf")
    elif a in ("office_to_pdf", "pptx_to_images", "pdf_to_docx"):
        opts.update(dpi=args.dpi or 150, format=args.format or "png")
    return opts


def cli_out_settings(args: argparse.Namespace, settings) -> None:
    if not args.out:
        return
    if args.out == "same":
        settings.set("output.folder_mode", "same")
    elif args.out.startswith("custom:"):
        settings.set("output.folder_mode", "custom")
        settings.set("output.custom_path", args.out.split(":", 1)[1])
    else:
        settings.set("output.folder_mode", "subfolder")


def run_cli(args: argparse.Namespace) -> int:
    from core.batch import summarize
    from core.runner import run_action

    files = [str(Path(f)) for f in args.files if f != "-"]
    settings = load_settings()
    cli_out_settings(args, settings)

    actions = detect.actions_for(files)
    if args.action is None:
        ids = ", ".join(a.id for a in actions) or "(none)"
        print(f"Available actions: {ids}")
        return 2
    if args.action not in (a.id for a in actions):
        print(f"Action '{args.action}' is not valid for this selection.")
        print(f"Available: {', '.join(a.id for a in actions) or '(none)'}")
        return 2

    results = run_action(args.action, files, cli_opts(args), settings)
    print(summarize(results))
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        line = f"  [{status}] {Path(r.input).name}"
        if r.ok and r.output:
            line += f" -> {r.output}"
        if r.note:
            line += f" ({r.note})"
        print(line)
    return 0 if all(r.ok for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    args = build_cli_parser().parse_args(argv)
    log = get_logger()
    log.info("=== %s launched: %s", PROG, argv if argv is not None else sys.argv[1:])

    try:
        if args.probe:
            files = platform_gather([f for f in args.files], {})
            print("PROBE-FILES:" + "\n".join(files or []))
            return 0

        if args.info:
            files = [f for f in args.files]
            cat = detect.categorize(files)
            print(cat.counts_line(len(files)))
            for a in detect.actions_for(files):
                print(f"  {a.id:<16} {a.label}")
            return 0

        if args.cli or args.no_gui:
            return run_cli(args)

        files = [f for f in args.files]
        if not files:
            build_cli_parser().print_help()
            return 2
        return run_gui(files)

    except UserError as exc:
        log.warning("UserError: %s", exc.message)
        show_error_box(exc.message)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - last resort, still no traceback
        log_exception("Unhandled error", exc)
        show_error_box(
            friendly_message(exc)
            + f"\n\nFull details: {LOG_FILE}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
