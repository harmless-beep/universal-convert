"""Generate the application icon.

Produces (from one design):
  installers/icons/icon.png   - source art, Linux AppImage / README
  installers/icons/icon.ico   - Windows executable
  installers/icons/icon.icns  - macOS bundle

Run:  python installers/make_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
OUT_DIR = Path(__file__).resolve().parent / "icons"

BG_TOP = (37, 99, 235)    # blue-600
BG_BOTTOM = (6, 182, 212) # cyan-500
INK = (255, 255, 255)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def gradient(size: int) -> Image.Image:
    """Diagonal blue -> cyan gradient (rendered small, upscaled smooth)."""
    small = 256
    img = Image.new("RGB", (small, small))
    px = img.load()
    for y in range(small):
        for x in range(small):
            t = (x + y) / (2 * small - 2)
            px[x, y] = _lerp(BG_TOP, BG_BOTTOM, t)
    return img.resize((size, size), Image.LANCZOS)


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255
    )
    return mask


def _point(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def sync_arrows(size: int, draw: ImageDraw.ImageDraw) -> None:
    """Two circular arrows: the universal 'convert / convert again' mark."""
    cx = cy = size / 2
    r = size * 0.29
    w = size * 0.092
    # 180-deg rotational symmetry, with room in the gaps for the heads
    arcs = ((62.0, 180.0), (242.0, 360.0))

    for start, end in arcs:
        draw.arc(
            [cx - r, cy - r, cx + r, cy + r],
            start=start,
            end=end,
            fill=INK,
            width=round(w),
        )

        # arrow head at the end of the stroke (motion = increasing angle)
        px, py = _point(cx, cy, r, end)
        a = math.radians(end)
        dx, dy = -math.sin(a), math.cos(a)          # tangent, clockwise
        nx, ny = -dy, dx                             # normal
        head_len = w * 1.6
        head_half = w * 1.0
        tip = (px + dx * head_len, py + dy * head_len)
        left = (px + nx * head_half, py + ny * head_half)
        right = (px - nx * head_half, py - ny * head_half)
        draw.polygon([tip, left, right], fill=INK)


def build(size: int = SIZE) -> Image.Image:
    art = gradient(size)
    mask = rounded_mask(size, radius=round(size * 0.205))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(art, (0, 0), mask)
    sync_arrows(size, ImageDraw.Draw(out))
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icon = build()

    png = OUT_DIR / "icon.png"
    icon.save(png)

    ico = OUT_DIR / "icon.ico"
    icon.save(
        ico,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
               (64, 64), (128, 128), (256, 256)],
    )

    icns = OUT_DIR / "icon.icns"
    try:
        icon.save(
            icns,
            sizes=[(16, 16), (32, 32), (64, 64),
                   (128, 128), (256, 256), (512, 512)],
        )
    except Exception as exc:  # noqa: BLE001 - icns support varies by build
        print(f"warning: could not write {icns.name}: {exc}")

    for path in (png, ico, icns):
        if path.exists():
            print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
