"""The "Convert With..." dialog.

One window, two jobs:
  1. Ask: which action + options for the selected files (only valid actions
     are listed; options pre-fill from the user's last run).
  2. Run it with live progress, then report per-file results.

Runs the conversion on a worker thread; the Tk main thread only polls state
(standard Tk threading discipline - never touch widgets off-main-thread).
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from tkinter.font import Font

from core import detect
from core.batch import first_output, summarize
from core.errors import (
    LOG_FILE,
    UserError,
    describe_paths,
    friendly_message,
    get_logger,
    log_exception,
)
from core.runner import run_action
from core.settings import Settings


class ConversionDialog:
    def __init__(self, files: list[str], settings: Settings):
        self.files = files
        self.settings = settings
        self.cat = detect.categorize(files)
        self.actions = detect.actions_for(files)
        self.results: list | None = None
        self.worker: threading.Thread | None = None
        self.state: dict = {"running": False, "done": False,
                            "progress": (0, 1, ""), "results": None, "error": ""}
        self._run_total = 0     # files actually handed to the engine
        self._bar: tuple[int, int] | None = None   # last file-level bar position

        self.root = tk.Tk()
        self.root.title("Convert With...")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.after(250, lambda: self.root.attributes("-topmost", False))

        bold = Font(family="TkDefaultFont", size=10, weight="bold")
        self._panels: dict[str, ttk.Frame] = {}
        self._building = ""
        pad = {"padx": 10, "pady": 4}

        # ---- header: what did the user select? -------------------------
        head = ttk.Frame(self.root)
        head.pack(fill="x", **pad)
        n = len(files)
        title = ttk.Label(head, text=f"{n} file{'s' if n != 1 else ''} selected",
                          font=bold)
        title.pack(anchor="w")
        ttk.Label(head, text=self.cat.counts_line(n) + "  ·  " +
                  describe_paths(files, 2), foreground="#555").pack(anchor="w")
        if self.cat.other:
            ttk.Label(
                head,
                text=f"{len(self.cat.other)} unsupported file(s) will be skipped "
                     f"({describe_paths(self.cat.other, 2)})",
                foreground="#a05a00", wraplength=420, justify="left",
            ).pack(anchor="w", pady=(2, 0))

        ttk.Separator(self.root).pack(fill="x", pady=4)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, **pad)

        # ---- action list -----------------------------------------------
        ttk.Label(body, text="What should happen?", font=bold).pack(anchor="w")
        self.action_var = tk.StringVar(
            value=self.actions[0].id if self.actions else "")
        for a in self.actions:
            ttk.Radiobutton(
                body, text=a.label, value=a.id, variable=self.action_var,
                command=self._on_action_change,
            ).pack(anchor="w", padx=(12, 0))
        if not self.actions:
            ttk.Label(
                body, foreground="#a02222",
                text="No conversion is available for this selection.",
            ).pack(anchor="w", padx=12)

        self.desc = ttk.Label(body, foreground="#555", wraplength=420,
                              justify="left")
        self.desc.pack(anchor="w", padx=(24, 0), pady=(0, 6))

        # ---- options panel (swapped per action) -------------------------
        self.opts_frame = ttk.Frame(body)
        self.opts_frame.pack(fill="x", pady=(0, 6))
        self._opt_widgets: dict[str, dict] = {}

        # ---- output folder ----------------------------------------------
        ttk.Separator(self.root).pack(fill="x", pady=2)
        out_row = ttk.Frame(self.root)
        out_row.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(out_row, text="Save output:").pack(side="left")
        self.out_var = tk.StringVar(
            value=self.settings.get("output.folder_mode", "subfolder"))
        ttk.Radiobutton(out_row, text="In a 'Converted' subfolder",
                        value="subfolder", variable=self.out_var).pack(
            side="left", padx=(8, 4))
        ttk.Radiobutton(out_row, text="Next to the originals",
                        value="same", variable=self.out_var).pack(side="left")

        # ---- progress + buttons ------------------------------------------
        self.progress = ttk.Progressbar(self.root, mode="determinate", length=430)
        self.progress.pack(fill="x", padx=10, pady=(2, 0))
        self.status = ttk.Label(self.root, text=" ", foreground="#555",
                                wraplength=430, justify="left")
        self.status.pack(fill="x", padx=10)

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=10, pady=8)
        self._cancel_event = threading.Event()
        self.convert_btn = ttk.Button(btns, text="Convert", command=self._convert)
        self.convert_btn.pack(side="right")
        self.cancel_btn = ttk.Button(btns, text="Cancel",
                                     command=self._cancel_run,
                                     state="disabled")
        self.cancel_btn.pack(side="right", padx=(0, 8))
        self.close_btn = ttk.Button(btns, text="Close", command=self._close)
        self.close_btn.pack(side="right", padx=(0, 8))

        self._build_option_panels()
        self._on_action_change()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        if not self.actions:
            self.convert_btn.state(["disabled"])
        self.root.bind("<Escape>", self._on_escape)
        self.root.bind("<Return>", self._on_return)
        # Tk swallows callback exceptions (invisible under pythonw): log them
        # and put a visible line in the status area instead.
        self.root.report_callback_exception = self._callback_error

    # ------------------------------------------------------------- keyboard
    def _on_escape(self, _event=None) -> str:
        self._close()
        return "break"

    def _on_return(self, _event=None) -> str | None:
        widget = self.root.focus_get()
        # Let the focused control handle Return first (entries, buttons...).
        if widget is not None and widget.winfo_class() in (
                "TEntry", "Entry", "TSpinbox", "Spinbox", "TCombobox",
                "ComboBox", "TButton", "Button"):
            return None
        self._convert()
        return "break"

    def _callback_error(self, _exc_type, exc_value, _tb) -> None:
        log_exception("dialog callback failed", exc_value)
        try:
            self.status.config(text=friendly_message(exc_value),
                               foreground="#a02222")
        except Exception:  # noqa: BLE001 - status may already be gone
            pass

    # ------------------------------------------------------------------ run
    def run(self) -> None:
        self.root.mainloop()
        self._after_close()

    def _after_close(self) -> None:
        """Post-loop side effects: toast + open the output folder."""
        results = self.results
        if not results:
            return
        if self.settings.get("output.notify", True):
            from platform_util.notify import notify

            ok = sum(1 for r in results if r.ok)
            failed = len(results) - ok
            body = summarize(results)
            if failed:
                body += "\nSee the log for details."
            notify("Universal Convert", body)
        if self.settings.get("output.open_when_done", True) and ok_count(results):
            from platform_util.openfolder import open_output

            open_output(first_output(results))

    # -------------------------------------------------------------- options
    def _remember(self, key: str, widget: tk.Widget, attr: str,
                  action: str | None = None) -> None:
        # Files the widget under the panel currently being built. An explicit
        # `action` is needed from event callbacks, where the building context
        # is long gone.
        self._opt_widgets.setdefault(action or self._building, {})[key] = (
            widget, attr)

    def _build_option_panels(self) -> None:
        """Pre-build every panel once; raise the one for the active action."""
        presets = self.settings.get("presets", {})
        last_any = self.settings

        def panel(action_id: str) -> ttk.Frame:
            self._building = action_id
            f = ttk.Frame(self.opts_frame)
            self._opt_widgets.setdefault(action_id, {})
            self._panels[action_id] = f
            return f

        # -- resize -------------------------------------------------------
        f = panel("resize")
        row1 = ttk.Frame(f); row1.pack(anchor="w")
        mode_var = tk.StringVar(
            value=last_any.get("last_used.resize.mode",
                               self.settings.get("resize.default_mode", "preset")))
        ttk.Label(row1, text="Mode:").pack(side="left")
        for text, val in (("Preset", "preset"), ("Percent", "percent"),
                          ("Pixels", "pixels")):
            ttk.Radiobutton(row1, text=text, value=val, variable=mode_var,
                            command=lambda: self._resize_mode(mode_var, f)
                            ).pack(side="left", padx=4)
        preset_row = ttk.Frame(f); preset_row.pack(anchor="w", padx=(24, 0))
        ttk.Label(preset_row, text="Preset:").pack(side="left")
        preset_var = tk.StringVar(
            value=last_any.get("last_used.resize.preset",
                               self.settings.get("resize.default_preset", "web")))
        preset_cb = ttk.Combobox(
            preset_row, textvariable=preset_var, state="readonly", width=12,
            values=[p for p in ("web", "email", "print", "thumbnail") if p in presets],
        )
        preset_cb.pack(side="left", padx=4)
        self._remember("preset", preset_var, "get")
        pct_row = ttk.Frame(f); pct_row.pack(anchor="w", padx=(24, 0))
        ttk.Label(pct_row, text="Scale to %:").pack(side="left")
        pct_var = tk.StringVar(value=str(last_any.get("last_used.resize.percent", 50)))
        ttk.Spinbox(pct_row, from_=1, to=1000, textvariable=pct_var, width=6
                    ).pack(side="left", padx=4)
        self._remember("percent", pct_var, "get")
        px_row = ttk.Frame(f); px_row.pack(anchor="w", padx=(24, 0))
        ttk.Label(px_row, text="Width:").pack(side="left")
        w_var = tk.StringVar(value=str(
            last_any.get("last_used.resize.width",
                         self.settings.get("resize.default_width", 1920))))
        ttk.Spinbox(px_row, from_=1, to=30000, textvariable=w_var, width=7
                    ).pack(side="left", padx=(2, 8))
        ttk.Label(px_row, text="Height (blank = keep aspect):").pack(side="left")
        h_var = tk.StringVar(value=str(
            last_any.get("last_used.resize.height", "")))
        ttk.Spinbox(px_row, from_=0, to=30000, textvariable=h_var, width=7
                    ).pack(side="left", padx=2)
        self._remember("width", w_var, "get")
        self._remember("height", h_var, "get")
        self._resize_mode(mode_var, f)
        self._remember("mode", mode_var, "get")

        # -- compress ------------------------------------------------------
        f = panel("compress")
        q_row = ttk.Frame(f); q_row.pack(anchor="w", fill="x")
        ttk.Label(q_row, text="Quality:").pack(side="left")
        q_var = tk.IntVar(value=int(
            last_any.get("last_used.compress.quality",
                         self.settings.get("compress.default_quality", 85))))
        q_scale = ttk.Scale(q_row, from_=1, to=100, variable=q_var, length=220)
        q_scale.pack(side="left", padx=6)
        q_lbl = ttk.Label(q_row, text=str(q_var.get()), width=4)
        q_lbl.pack(side="left")
        q_var.trace_add("write", lambda *_: q_lbl.config(text=str(q_var.get())))
        auto_var = tk.BooleanVar(value=bool(
            last_any.get("last_used.compress.auto",
                         self.settings.get("compress.auto", False))))
        tgt_row = ttk.Frame(f); tgt_row.pack(anchor="w")
        ttk.Label(tgt_row, text="Target size (KB, optional):").pack(side="left")
        tgt_var = tk.StringVar(
            value=str(last_any.get("last_used.compress.target_kb") or ""))
        ttk.Entry(tgt_row, textvariable=tgt_var, width=8).pack(side="left", padx=4)

        def _auto_toggled(*_):
            for w in (q_scale,):
                w.state(["disabled"] if auto_var.get() else ["!disabled"])
            self._remember("quality", q_var, "get", "compress")
            self._remember("auto", auto_var, "get", "compress")
            self._remember("target_kb", tgt_var, "get", "compress")

        ttk.Checkbutton(f, text="Auto-optimize (best quality under target size)",
                        variable=auto_var, command=_auto_toggled).pack(anchor="w")
        _auto_toggled()

        # -- convert -------------------------------------------------------
        f = panel("convert")
        ttk.Label(f, text="Convert to:").pack(anchor="w")
        fmt_var = tk.StringVar(
            value=last_any.get("last_used.convert.format",
                               self.settings.get("convert.default_format", "jpg")))
        fmt_cb = ttk.Combobox(f, textvariable=fmt_var, state="readonly",
                              values=["png", "jpg", "webp", "pdf"], width=10)
        fmt_cb.pack(anchor="w", padx=(24, 0))
        comb_var = tk.BooleanVar(value=bool(
            last_any.get("last_used.convert.combined",
                         self.settings.get("convert.combined_pdf", True))))
        self._comb_var = comb_var
        ttk.Checkbutton(f, text="All images into one PDF (when converting to PDF)",
                        variable=comb_var).pack(anchor="w")
        self._remember("format", fmt_var, "get")
        self._remember("combined", comb_var, "get")

        # -- pdf_to_images --------------------------------------------------
        f = panel("pdf_to_images")
        row = ttk.Frame(f); row.pack(anchor="w")
        ttk.Label(row, text="Resolution:").pack(side="left")
        dpi_var = tk.StringVar(value=str(
            last_any.get("last_used.pdf_to_images.dpi",
                         self.settings.get("pdf.default_dpi", 150))))
        ttk.Combobox(row, textvariable=dpi_var, values=["96", "150", "300"],
                     width=6, state="readonly").pack(side="left", padx=4)
        ttk.Label(row, text="Format:").pack(side="left", padx=(12, 0))
        ifmt_var = tk.StringVar(
            value=last_any.get("last_used.pdf_to_images.format",
                               self.settings.get("pdf.default_format", "png")))
        ttk.Combobox(row, textvariable=ifmt_var, values=["png", "jpg"],
                     width=6, state="readonly").pack(side="left", padx=4)
        self._remember("dpi", dpi_var, "get")
        self._remember("format", ifmt_var, "get")

        # -- pdf_to_docx -----------------------------------------------------
        f = panel("pdf_to_docx")
        ttk.Label(f, foreground="#555", wraplength=400, justify="left",
                  text="Produces an editable .docx. Layout is reconstructed "
                       "best-effort - complex designs will not match exactly."
                  ).pack(anchor="w")

        # -- pdf_compress -----------------------------------------------------
        f = panel("pdf_compress")
        lossy_var = tk.BooleanVar(value=bool(
            last_any.get("last_used.pdf_compress.lossy",
                         self.settings.get("pdf.lossy_compress", False))))
        q2_var = tk.IntVar(value=int(
            last_any.get("last_used.pdf_compress.quality",
                         self.settings.get("pdf.lossy_quality", 75))))
        ttk.Radiobutton(f, text="Lossless (no quality loss, modest savings)",
                        value=False, variable=lossy_var).pack(anchor="w")
        ttk.Radiobutton(f, text="Lossy (re-compresses embedded images)",
                        value=True, variable=lossy_var).pack(anchor="w")
        q2_row = ttk.Frame(f); q2_row.pack(anchor="w", padx=(24, 0))
        ttk.Label(q2_row, text="Image quality:").pack(side="left")
        ttk.Scale(q2_row, from_=10, to=95, variable=q2_var, length=200
                  ).pack(side="left", padx=6)
        self._remember("lossy", lossy_var, "get")
        self._remember("quality", q2_var, "get")

        # -- pdf_merge ---------------------------------------------------------
        f = panel("pdf_merge")
        ttk.Label(f, foreground="#555", wraplength=400, justify="left",
                  text="Pages are appended in the order shown: "
                  ).pack(anchor="w")
        ttk.Label(f, foreground="#555", wraplength=400, justify="left",
                  text=describe_paths(self.cat.pdfs, 6)).pack(anchor="w")
        name_var = tk.StringVar(value="merged.pdf")
        nrow = ttk.Frame(f); nrow.pack(anchor="w", pady=(4, 0))
        ttk.Label(nrow, text="Output name:").pack(side="left")
        ttk.Entry(nrow, textvariable=name_var, width=24).pack(
            side="left", padx=4)
        self._remember("output_name", name_var, "get")

        # -- pdf_split ---------------------------------------------------------
        f = panel("pdf_split")
        mode_var2 = tk.StringVar(
            value=last_any.get("last_used.pdf_split.mode", "range"))
        ttk.Radiobutton(f, text="Extract page ranges", value="range",
                        variable=mode_var2).pack(anchor="w")
        rng_row = ttk.Frame(f); rng_row.pack(anchor="w", padx=(24, 0))
        ttk.Label(rng_row, text="Pages:").pack(side="left")
        rng_var = tk.StringVar(
            value=last_any.get("last_used.pdf_split.ranges", "1-3"))
        ttk.Entry(rng_row, textvariable=rng_var, width=14).pack(
            side="left", padx=4)
        ttk.Label(rng_row, text="e.g.  1-3,5", foreground="#777").pack(side="left")
        ttk.Radiobutton(f, text="Every page as its own PDF", value="pages",
                        variable=mode_var2).pack(anchor="w")
        self._remember("mode", mode_var2, "get")
        self._remember("ranges", rng_var, "get")

        # -- office_to_pdf -------------------------------------------------------
        f = panel("office_to_pdf")
        ttk.Label(f, foreground="#555", wraplength=400, justify="left",
                  text="Converts via LibreOffice in headless mode "
                       "(Microsoft Office is not required)."
                  ).pack(anchor="w")

        # -- pptx_to_images --------------------------------------------------------
        f = panel("pptx_to_images")
        row = ttk.Frame(f); row.pack(anchor="w")
        ttk.Label(row, text="Resolution:").pack(side="left")
        sdpi_var = tk.StringVar(value=str(
            last_any.get("last_used.pptx_to_images.dpi",
                         self.settings.get("pdf.default_dpi", 150))))
        ttk.Combobox(row, textvariable=sdpi_var, values=["96", "150", "300"],
                     width=6, state="readonly").pack(side="left", padx=4)
        ttk.Label(row, text="Format:").pack(side="left", padx=(12, 0))
        sfmt_var = tk.StringVar(
            value=last_any.get("last_used.pptx_to_images.format", "png"))
        ttk.Combobox(row, textvariable=sfmt_var, values=["png", "jpg"],
                     width=6, state="readonly").pack(side="left", padx=4)
        ttk.Label(f, foreground="#555",
                  text="Each slide becomes one image, packed into a .zip."
                  ).pack(anchor="w")
        self._remember("dpi", sdpi_var, "get")
        self._remember("format", sfmt_var, "get")

    def _resize_mode(self, mode_var: tk.StringVar, f: ttk.Frame) -> None:
        """Show only the sub-row matching the chosen resize mode."""
        rows = list(f.winfo_children())
        # order: row1 (modes), preset_row, pct_row, px_row
        visible = {"preset": 1, "percent": 2, "pixels": 3}.get(mode_var.get())
        for i, row in enumerate(rows[1:], start=1):
            if visible is not None and i == visible:
                row.pack(anchor="w", padx=(24, 0))
            else:
                row.pack_forget()

    def _on_action_change(self) -> None:
        action = self.action_var.get()
        meta = next((a for a in self.actions if a.id == action), None)
        self.desc.config(text=meta.description if meta else "")
        for aid, panel in self._panels.items():
            if aid == action:
                panel.pack(fill="x", pady=(2, 0))
            else:
                panel.pack_forget()

    # ------------------------------------------------------------------ run
    def _collect_opts(self) -> dict:
        action = self.action_var.get()
        widgets = self._opt_widgets.get(action, {})
        opts: dict = {}
        for key, (widget, attr) in widgets.items():
            try:
                opts[key] = getattr(widget, attr)()
            except Exception:
                opts[key] = None

        # normalize per action
        if action == "resize":
            mode = opts.get("mode", "preset")
            opts["mode"] = mode
            if mode == "percent":
                opts["percent"] = _to_float(opts.get("percent"), 50.0)
            elif mode == "pixels":
                opts["width"] = int(_to_float(opts.get("width"), 1920))
                h = str(opts.get("height") or "").strip()
                opts["height"] = int(h) if h.isdigit() else None
                opts["keep_aspect"] = opts["height"] is None
            else:
                opts["preset"] = opts.get("preset") or "web"
        elif action == "compress":
            opts["quality"] = int(_to_float(opts.get("quality"), 85))
            opts["auto"] = bool(opts.get("auto"))
            kb = str(opts.get("target_kb") or "").strip()
            opts["target_kb"] = int(kb) if kb.isdigit() else None
        elif action == "convert":
            opts["format"] = (opts.get("format") or "jpg").lower()
            opts["combined"] = bool(getattr(self, "_comb_var", tk.BooleanVar()).get())
        elif action == "pdf_to_images":
            opts["dpi"] = int(_to_float(opts.get("dpi"), 150))
            opts["format"] = (opts.get("format") or "png").lower()
        elif action == "pdf_compress":
            opts["lossy"] = bool(opts.get("lossy"))
            opts["quality"] = int(_to_float(opts.get("quality"), 75))
        elif action == "pdf_split":
            opts["mode"] = opts.get("mode") or "range"
            opts["ranges"] = (opts.get("ranges") or "1").strip()
        return opts

    def _run_files(self) -> list[str]:
        """The files actually handed to the engine.

        `actions_for` only ever offers actions that fit the *supported* files,
        so anything unsupported is dropped here - otherwise it would fail as a
        spurious error (and drag the output folder along with it).
        """
        supported = set(self.cat.supported)
        return [p for p in self.files if p in supported]

    def _cancel_run(self) -> None:
        """Ask the worker to stop after the file it is on right now."""
        if not (self.state.get("running") and not self.state.get("done")):
            return
        self._cancel_event.set()
        self.cancel_btn.state(["disabled"])
        self.status.config(text="Stopping after the current file…",
                           foreground="#a05a00")

    def _convert(self) -> None:
        if self.state.get("running") and not self.state.get("done"):
            return  # already converting; ignore the extra click
        action = self.action_var.get()
        to_run = self._run_files()
        if not action or not to_run:
            self.root.bell()
            self.status.config(
                foreground="#a05a00",
                text=("Nothing to convert: none of the selected files are "
                      "supported." if not to_run
                      else "Pick what should happen first."),
            )
            return

        opts = self._collect_opts()
        try:
            self.settings.set("output.folder_mode", self.out_var.get())
            self.settings.remember_last(action, opts)
            self.settings.save()
        except Exception as exc:  # noqa: BLE001 - never block a conversion
            log_exception("could not remember these settings", exc)

        self.convert_btn.state(["disabled"])
        self._cancel_event.clear()
        self.cancel_btn.state(["!disabled"])
        self._run_total = len(to_run)
        self._bar = (self._run_total, 0)
        self.progress.config(mode="determinate", value=0,
                             maximum=max(self._run_total, 1))
        self.status.config(text="Working…", foreground="#555")
        self.state = {"running": True, "done": False,
                      "progress": (0, self._run_total, ""), "results": None,
                      "error": ""}

        settings = self.settings

        def work():
            try:
                results = run_action(action, to_run, opts, settings,
                                     progress=self._thread_progress,
                                     cancel=self._cancel_event)
                self.state["results"] = results
            except UserError as exc:
                self.state["error"] = exc.message
            except Exception as exc:  # noqa: BLE001
                get_logger().error("dialog worker: %s", exc)
                log_exception("conversion failed", exc)
                self.state["error"] = friendly_message(exc)
            finally:
                # Always release the UI, even if the error handler itself
                # failed - otherwise the dialog locks up with no way out.
                self.state["done"] = True

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.root.after(80, self._poll)

    def _thread_progress(self, done: int, total: int, name: str) -> None:
        # called from the worker thread: only touch plain data here
        self.state["progress"] = (done, total, name)

    def _poll(self) -> None:
        done, total, name = self.state["progress"]
        run_total = self._run_total or 1
        if total == run_total or run_total == 1:
            # file-level report (or page-level inside a single-file run);
            # anything else is a mid-file counter and must not drag the
            # bar backwards.
            self._bar = (max(total, 1), min(done, total))
        if self._bar:
            self.progress.config(maximum=self._bar[0], value=self._bar[1])
        if name:
            if total == run_total:
                self.status.config(
                    text=f"Converting {name}…  ({done}/{total})")
            else:
                self.status.config(text=f"Converting {name}…")
        if self.state["done"]:
            self._finish()
            return
        self.root.after(80, self._poll)

    def _finish(self) -> None:
        self.convert_btn.state(["!disabled"])
        self.cancel_btn.state(["disabled"])
        error = self.state["error"]
        results = self.state["results"]
        if error:
            self.status.config(text=error, foreground="#a02222")
            return
        if results is None:
            # worker died without results and without an error we could show
            get_logger().error("conversion ended without results")
            self.status.config(
                text=f"The conversion stopped unexpectedly. "
                     f"Details: {LOG_FILE}",
                foreground="#a02222",
            )
            return
        self.results = results
        ok = sum(1 for r in results if r.ok)
        failed = len(results) - ok
        color = "#1a7a2e" if not failed else "#a05a00"
        self.status.config(text=summarize(results), foreground=color)
        self._show_results(results)

    def _show_results(self, results: list) -> None:
        win = tk.Toplevel(self.root)
        win.title("Conversion results")
        win.transient(self.root)
        win.resizable(False, False)
        failed = [r for r in results if not r.ok
                  and not r.error.startswith("Cancelled")]
        stopped = sum(1 for r in results if not r.ok
                      and r.error.startswith("Cancelled"))

        ttk.Label(win, text=summarize(results),
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w",
                                                           padx=12, pady=(10, 4))

        holder = ttk.Frame(win)
        holder.pack(fill="both", expand=True, padx=(12, 6))
        body = tk.Text(holder, width=64, height=min(len(results), 18),
                       wrap="word", relief="solid", borderwidth=1,
                       padx=8, pady=6, font=("TkDefaultFont", 9),
                       cursor="arrow")
        vsb = ttk.Scrollbar(holder, orient="vertical", command=body.yview)
        body.configure(yscrollcommand=vsb.set)
        body.tag_configure("ok", foreground="#1a7a2e")
        body.tag_configure("bad", foreground="#a02222")
        for r in results:
            mark = "✓" if r.ok else "✗"
            line = f"{mark}  {Path(r.input).name}"
            if r.ok:
                if r.note:
                    line += f"  —  {r.note}"
                elif r.output:
                    line += f"  →  {Path(r.output).name}"
            else:
                line += f"  —  {r.error or 'failed'}"
            body.insert("end", line + "\n", "ok" if r.ok else "bad")
        body.configure(state="disabled")
        vsb.pack(side="right", fill="y")
        body.pack(side="left", fill="both", expand=True)

        if failed:
            ttk.Label(
                win, foreground="#555", wraplength=430, justify="left",
                text=f"{len(failed)} file{'s' if len(failed) != 1 else ''} "
                     f"failed. The rest were written normally - the exact "
                     f"reasons are next to each file above.",
            ).pack(anchor="w", padx=12, pady=(4, 0))
        elif stopped:
            ttk.Label(
                win, foreground="#555", wraplength=430, justify="left",
                text=f"Stopped early: {stopped} file"
                     f"{'s' if stopped != 1 else ''} were not processed.",
            ).pack(anchor="w", padx=12, pady=(4, 0))

        row = ttk.Frame(win)
        row.pack(fill="x", padx=12, pady=(6, 10))
        if failed:
            ttk.Button(row, text="Open log", command=self._open_log).pack(
                side="left")
        ttk.Button(row, text="OK", command=win.destroy).pack(side="right")
        win.attributes("-topmost", True)
        win.after(200, lambda: win.attributes("-topmost", False))

    def _open_log(self) -> None:
        from platform_util.openfolder import open_file

        if not open_file(str(LOG_FILE)):
            self.status.config(text=f"Log: {LOG_FILE}", foreground="#555")

    def _close(self) -> None:
        if self.state.get("running") and not self.state.get("done"):
            # simple guard: block closing mid-conversion (conversions are short)
            self.root.bell()
            return
        self.root.destroy()


def ok_count(results: list) -> bool:
    return any(r.ok for r in results)


def _to_float(value, default: float) -> float:
    try:
        return float(str(value).strip() or default)
    except (TypeError, ValueError):
        return default
