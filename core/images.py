"""Image engine - all Pillow-based actions.

Functions take (paths, opts, namer, progress) and return list[Result].
`opts` is a plain dict produced by the dialog (or CLI flags); `namer`
resolves output paths; `progress(done, total, filename)` is optional.

Handles animated GIFs frame-by-frame, EXIF orientation, alpha channels,
and maps Pillow's exceptions to friendly UserError messages.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import Image as ImageT

from .batch import OutputNamer, Result, run_batch
from .errors import UserError

Progress = Callable[[int, int, str], None] | None

# Preset paper definitions for "print": name -> (width_in, height_in) at 300 dpi
_PAPERS_MM = {"A4": (210.0, 297.0), "A3": (297.0, 420.0), "Letter": (215.9, 279.4)}

RESAMPLE = Image.LANCZOS


def _open(path: str) -> ImageT:
    try:
        img = Image.open(path)
        img.load()
    except FileNotFoundError:
        raise
    except PermissionError:
        raise
    except UnidentifiedImageError as exc:
        raise UserError(
            f"Cannot read this image (file is corrupt or not a real image):\n{path}"
        ) from exc
    except OSError as exc:
        raise UserError(
            f"Could not open the image:\n{path}\n({exc})"
        ) from exc
    return ImageOps.exif_transpose(img) or img


def _frames(img: ImageT) -> list[ImageT]:
    """All frames of a (possibly animated) image; single frame otherwise."""
    frames = [frame.copy() for frame in _iter_frames(img)]
    return frames or [img.copy()]

def _iter_frames(img: ImageT):
    from PIL import ImageSequence

    return ImageSequence.Iterator(img)


def _is_animated(path: str) -> bool:
    try:
        with Image.open(path) as im:
            return getattr(im, "n_frames", 1) > 1
    except Exception:
        return False


def _save(img: ImageT, dest: Path, ext: str, **kwargs) -> None:
    try:
        if ext == ".jpg" and img.mode in ("RGBA", "LA", "P"):
            img = _flatten_alpha(img)
        elif ext in (".jpg", ".bmp") and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(dest, **kwargs)
    except (OSError, ValueError, KeyError) as exc:
        raise UserError(f"Could not save {dest.name}: {exc}") from exc


def _flatten_alpha(img: ImageT, background=(255, 255, 255)) -> ImageT:
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        base = Image.new("RGB", img.size, background)
        base.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
        return base
    return img.convert("RGB")


# --------------------------------------------------------------------------
# Resize
# --------------------------------------------------------------------------

def _target_size(img: ImageT, opts: dict) -> tuple[int, int]:
    w, h = img.size
    mode = opts.get("mode", "preset")

    if mode == "percent":
        pct = float(opts.get("percent", 50))
        pct = min(max(pct, 1.0), 1000.0)
        return max(1, round(w * pct / 100)), max(1, round(h * pct / 100))

    if mode == "pixels":
        tw = max(1, int(opts.get("width", w)))
        keep = bool(opts.get("keep_aspect", True))
        if keep:
            ratio = min(tw / w, tw / h) if not opts.get("height") else None
            if opts.get("height"):
                th = max(1, int(opts["height"]))
                ratio = min(tw / w, th / h)
            else:
                ratio = tw / w
            return max(1, round(w * ratio)), max(1, round(h * ratio))
        th = max(1, int(opts.get("height", h)))
        return tw, th

    # preset
    preset = opts.get("preset", "web")
    spec = opts.get("preset_specs", {}).get(preset, preset)
    return _preset_size(img, spec)


def _preset_size(img: ImageT, spec) -> tuple[int, int]:
    """spec is an int (long edge px), 'A4@300' style paper, or (w, h)."""
    w, h = img.size
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        bw, bh = int(spec[0]), int(spec[1])
    elif isinstance(spec, int):
        long_edge = max(1, spec)
        if w >= h:
            bw, bh = long_edge, max(1, round(h * long_edge / w))
        else:
            bh, bw = long_edge, max(1, round(w * long_edge / h))
        return bw, bh
    elif isinstance(spec, str) and "@" in spec:
        name, _, dpi = spec.partition("@")
        mm = _PAPERS_MM.get(name.strip().upper()) or _PAPERS_MM.get(name.strip())
        if mm is None:
            raise UserError(
                f"Unknown paper preset '{name}'. Known: {', '.join(_PAPERS_MM)}."
            )
        dpi_val = float(dpi or 300)
        bw = round(mm[0] / 25.4 * dpi_val)
        bh = round(mm[1] / 25.4 * dpi_val)
    else:
        raise UserError(f"Invalid preset value: {spec!r}")

    ratio = min(bw / w, bh / h)
    return max(1, round(w * ratio)), max(1, round(h * ratio))


def do_resize(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    label = {
        "percent": "resized",
        "pixels": "resized",
        "preset": f"{opts.get('preset', 'web')}-preset",
    }.get(opts.get("mode", "preset"), "resized")

    def worker(path: str) -> str:
        img = _open(path)
        size = _target_size(img, opts)
        if _is_animated(path):
            frames = _frames(img)
            resized = [f.resize(size, RESAMPLE) for f in frames]
            out = namer.for_input(path, Path(path).suffix.lower(), label)
            durations = frames[0].info.get("duration")
            save_kwargs = {"save_all": True, "append_images": resized[1:],
                           "duration": durations, "loop": frames[0].info.get("loop", 0)}
            try:
                resized[0].save(out, **save_kwargs)
            except (OSError, ValueError, TypeError) as exc:
                # extension may not support animation (jpg/bmp): fall back to frame 1
                out = namer.unique(out)
                _save(resized[0], out, out.suffix.lower())
                del exc
            return str(out)
        resized = img.resize(size, RESAMPLE)
        out = namer.for_input(path, Path(path).suffix.lower(), label)
        _save(resized, out, out.suffix.lower())
        return str(out)

    return run_batch(paths, _with_progress(worker, len(paths), progress))


def _with_progress(worker, total: int, progress: Progress):
    if progress is None:
        return worker
    state = {"i": 0}

    def wrapped(path: str) -> str:
        out = worker(path)
        state["i"] += 1
        progress(state["i"], total, Path(path).name)
        return out

    return wrapped


# --------------------------------------------------------------------------
# Compress
# --------------------------------------------------------------------------

def _save_image_bytes(
    img: ImageT, dest: Path, ext: str, quality: int, auto: bool = False
) -> int:
    """Save and return file size; raises on failure."""
    if ext == ".png":
        # PNG: lossless. quality maps to zlib effort (size shrinks a bit,
        # pixels stay identical) - honest behavior for a lossless format.
        level = 9 if quality >= 70 else (6 if quality >= 40 else 3)
        if auto:
            level = 9
        kwargs = {"optimize": True, "compress_level": level}
    elif ext in (".jpg", ".jpeg"):
        q = min(max(int(quality), 1), 95)
        kwargs = {"quality": q, "optimize": True, "progressive": True}
    elif ext == ".webp":
        q = min(max(int(quality), 1), 100)
        kwargs = {"quality": q, "method": 4 if auto else 0}
    elif ext in (".gif",):
        kwargs = {"optimize": True}
    elif ext in (".bmp", ".tif", ".tiff"):
        kwargs = {"compression": "tiff_deflate"} if ext in (".tif", ".tiff") else {}
    else:
        kwargs = {}

    target = img
    if ext == ".jpg":
        target = _flatten_alpha(img)
    elif target.mode not in ("RGB", "L", "P", "RGBA", "LA"):
        target = target.convert("RGBA" if "A" in target.getbands() else "RGB")

    try:
        target.save(dest, **kwargs)
    except (OSError, ValueError, TypeError) as exc:
        raise UserError(f"Could not save {dest.name}: {exc}") from exc
    return dest.stat().st_size


def _auto_shrink(img: ImageT, dest: Path, ext: str, target_kb: int | None) -> int:
    """Auto-optimize: start high, step down quality until target met (or floor)."""
    ladder = [90, 80, 70, 60, 50, 40, 30, 20, 12, 5]
    best_size = math.inf
    best_q = ladder[0]
    for q in ladder:
        size = _save_image_bytes(img, dest, ext, quality=q, auto=True)
        if size < best_size:
            best_size, best_q = size, q
        if target_kb and size <= target_kb * 1024:
            return size
        if ext == ".png":
            break  # PNG is lossless; one optimized pass is all there is
    if best_q != ladder[0]:
        _save_image_bytes(img, dest, ext, quality=best_q, auto=True)
    return int(best_size)


def do_compress(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    quality = int(opts.get("quality", 85))
    quality = min(max(quality, 1), 100)
    auto = bool(opts.get("auto", False))
    target_kb = opts.get("target_kb") or None

    def worker(path: str) -> str:
        img = _open(path)
        ext = Path(path).suffix.lower()
        out = namer.for_input(path, ext, "compressed")
        if ext == ".bmp":
            raise UserError(
                "BMP is already uncompressed. Convert to PNG or JPG instead "
                "for a smaller file."
            )
        if _is_animated(path):
            frames = _frames(img)
            try:
                frames[0].save(
                    out, save_all=True, append_images=frames[1:],
                    optimize=True,
                    duration=frames[0].info.get("duration"),
                    loop=frames[0].info.get("loop", 0),
                )
            except (OSError, ValueError, TypeError) as exc:
                raise UserError(f"Could not compress {Path(path).name}: {exc}") from exc
            return str(out)
        if auto:
            _auto_shrink(img, out, ext, target_kb)
        else:
            _save_image_bytes(img, out, ext, quality)
        return str(out)

    return run_batch(paths, _with_progress(worker, len(paths), progress))


# --------------------------------------------------------------------------
# Convert format (PNG <-> JPG <-> WEBP <-> PDF)
# --------------------------------------------------------------------------

VALID_FORMATS = ("png", "jpg", "jpeg", "webp", "pdf")


def do_convert(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    target = str(opts.get("format", "jpg")).lower().lstrip(".")
    if target == "jpeg":
        target = "jpg"
    if target not in VALID_FORMATS:
        raise UserError(f"Unsupported target format: {target}")

    if target == "pdf":
        return _images_to_pdf(paths, opts, namer, progress)

    results: list[Result] = []

    def worker(path: str) -> str:
        img = _open(path)
        if _is_animated(path) and target == "webp":
            frames = _frames(img)
            out = namer.for_input(path, "." + target, "")
            try:
                frames[0].save(out, save_all=True, append_images=frames[1:],
                               quality=90, method=3)
            except (OSError, ValueError, TypeError) as exc:
                raise UserError(f"Could not convert {Path(path).name}: {exc}") from exc
            return str(out)
        img = _open(path)
        if target in ("jpg", "pdf"):
            img = _flatten_alpha(img)
        ext = "." + target
        same_ext = Path(path).suffix.lower() == ext
        out = namer.for_input(path, ext, "converted" if same_ext else "")
        if target == "png":
            _save(img, out, ext, optimize=True)
        elif target == "jpg":
            _save(img, out, ext, quality=95, optimize=True, progressive=True)
        else:  # webp
            _save(img, out, ext, quality=95, method=4)
        return str(out)

    results = run_batch(paths, _with_progress(worker, len(paths), progress))
    return results


def _images_to_pdf(
    paths: list[str],
    opts: dict,
    namer: OutputNamer,
    progress: Progress = None,
) -> list[Result]:
    combined = bool(opts.get("combined", True)) and len(paths) > 1
    results: list[Result] = []

    if combined:
        try:
            pages: list[ImageT] = []
            for i, p in enumerate(paths):
                img = _open(p)
                pages.append(_flatten_alpha(img).convert("RGB"))
                if progress:
                    progress(i + 1, len(paths), Path(p).name)
            out = namer.fixed("combined.pdf")
            pages[0].save(out, save_all=True, append_images=pages[1:])
            for p in paths:
                results.append(Result(input=p, output=str(out), ok=True))
            return results
        except UserError as exc:
            return [Result(input=p, output=None, ok=False, error=exc.message)
                    for p in paths]

    def worker(path: str) -> str:
        img = _flatten_alpha(_open(path)).convert("RGB")
        out = namer.for_input(path, ".pdf", "")
        img.save(out, "PDF", resolution=150.0)
        return str(out)

    return run_batch(paths, _with_progress(worker, len(paths), progress))
