"""Build the New Flowers art from the vanilla Plant Tycoon images.

    python scripts/build_new_flowers_assets.py "<vanilla Plant Tycoon folder>"

The 14 new flowers use cells of the game's own flower sheets that no flower
uses. One needs new art: Mirabilis (the long-stemmed trumpet, cells 15-17 of
flowers64x64_grid.png) is magenta like the game's Jalapa, so the owner asked
for a recolour. Its three views are copied into the sheet's empty cells
33-35, trimmed to the owner's pick (a third of the trumpet's tube, fading
out, with no green bulb) and finished in polished orange gold like a brass
trumpet, with soft reflections that fade in and out (the stem at a quarter
of the bell's shine), also the owner's pick. The mask sheet's cells are trimmed the same
way (without the fade). Writes
assets/plant_tycoon_flowers/Images/flowers64x64_grid.png and
flowers64x64_grid_mask.png: the stock sheets with those three cells filled.
The DLL's Mirabilis anchor (MIRABILIS_ANCHOR_X/Y) sits halfway between the
bell's centre and the tube's end of these cells.
"""

from __future__ import annotations

import colorsys
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "plant_tycoon_flowers" / "Images"
CELL = 64
COLUMNS = 12
SOURCE_CELLS = (15, 16, 17)
TARGET_CELLS = (33, 34, 35)
NEW_HUE = 0.13                 # golden yellow
MAGENTA = (0.80, 0.05)         # hues treated as the petals (wrapping through red)
TUBE_KEPT = 1 / 3              # share of the trumpet's tube that is kept
TUBE_FADE = 0.6                # how much the tube fades toward its end
BULB_ROWS = 8                  # the green bulb under the tube
ORANGE_GOLD = [(0.0, (70, 25, 0)), (0.3, (170, 75, 0)), (0.55, (240, 140, 10)), (0.75, (255, 195, 40)),
               (0.9, (255, 235, 140)), (1.0, (255, 255, 235))]      # shade -> colour
GOLD_CONTRAST = 2.0
GOLD_REFLECTIONS = 0.6         # strength of the reflection bands
GOLD_SOFTNESS = 3.0            # blur radius: the bands fade in and out
GOLD_GLINT = 0.4               # one diagonal highlight
STEM_SHINE = 0.25              # the stem's share of the bell's shine


def cell_box(index: int) -> tuple[int, int, int, int]:
    x, y = (index % COLUMNS) * CELL, (index // COLUMNS) * CELL
    return x, y, x + CELL, y + CELL


def recolour(cell: Image.Image) -> Image.Image:
    a = np.asarray(cell.convert("RGBA")).astype(float) / 255
    out = a.copy()
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            r, g, b, alpha = a[y, x]
            if alpha == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            if s > 0.15 and (h >= MAGENTA[0] or h <= MAGENTA[1]):
                nr, ng, nb = colorsys.hsv_to_rgb(NEW_HUE, min(1.0, s * 0.95), min(1.0, v * 1.08))
                out[y, x, :3] = (nr, ng, nb)
    return Image.fromarray((out * 255).round().astype("uint8"), "RGBA")


def trumpet_parts(cell: Image.Image) -> tuple[np.ndarray, int, int, int]:
    """(opaque mask, top row, row where the bell ends, bottom row)."""
    alpha = np.asarray(cell.getchannel("A")) > 60
    rows = [y for y in range(alpha.shape[0]) if alpha[y].any()]
    widths = {y: int(alpha[y].sum()) for y in rows}
    top, bottom = rows[0], rows[-1]
    # The bell ends where the opaque width first drops to the stem's; the bulb is the last 8 rows.
    stem_width = min(widths[y] for y in rows[len(rows) // 3: -BULB_ROWS])
    bell_end = next(y for y in rows if y > top + 4 and widths[y] <= stem_width + 2)
    return alpha, top, bell_end, bottom


def shorten_tube(cell: Image.Image) -> Image.Image:
    """Keep TUBE_KEPT of the tube between bell and bulb, joined so an angled
    tube stays continuous; the bulb keeps its place."""
    alpha, top, bell_end, bottom = trumpet_parts(cell)
    bulb_start = bottom - BULB_ROWS
    keep = max(4, int((bulb_start - bell_end) * TUBE_KEPT))
    cut_start, cut_end = bell_end + keep // 2, bulb_start - (keep - keep // 2)

    def tube_x(y: int) -> float:
        return float(np.nonzero(alpha[y])[0].mean())

    dx = round(tube_x(cut_end) - tube_x(cut_start))
    out = Image.new("RGBA", cell.size)
    out.alpha_composite(cell.crop((0, cut_end, cell.width, cell.height)), (0, cut_end))
    shifted = Image.new("RGBA", cell.size)
    shifted.paste(cell.crop((0, 0, cell.width, cut_start)), (dx, cut_end - cut_start))
    out.alpha_composite(shifted)
    return out


def trim(cell: Image.Image, art: bool) -> Image.Image:
    """The shipped Mirabilis: short tube, no bulb; the art's tube also fades
    and loses the bulb's green fringe."""
    short = shorten_tube(cell)
    alpha, top, bell_end, bottom = trumpet_parts(short)
    a = np.asarray(short).astype(float)
    if art:
        bulb_start = bottom - BULB_ROWS
        for y in range(bell_end, bulb_start):
            a[y, :, 3] *= 1 - (y - bell_end) / max(1, bulb_start - bell_end) * TUBE_FADE
        a = a.round()
        alpha, top, bell_end, bottom = trumpet_parts(Image.fromarray(a.astype("uint8"), "RGBA"))
    a[bottom - (BULB_ROWS - 1):, :, 3] = 0
    if art:
        a[(a[..., 1] - a[..., 0]) > 15, 3] = 0
    return Image.fromarray(a.astype("uint8"), "RGBA")


def _blur(values: np.ndarray, radius: float) -> np.ndarray:
    image = Image.fromarray((np.clip(values, 0, 1) * 255).astype("uint8"), "L")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius))).astype(float) / 255


def gold_finish(cell: Image.Image) -> Image.Image:
    """Polished orange gold: the shading's contrast raised and mapped onto a
    gold ramp, with soft reflection bands and a glint, both weaker on the stem."""
    a = np.asarray(cell).astype(float) / 255
    lum = 0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2]
    opaque = a[..., 3] > 0.2
    _, _, bell_end, _ = trumpet_parts(cell)
    yy, xx = np.mgrid[0:lum.shape[0], 0:lum.shape[1]]
    weight = _blur(np.where(yy < bell_end, 1.0, STEM_SHINE), 1.5)
    lum = np.clip((lum - lum[opaque].mean()) * (1 + (GOLD_CONTRAST - 1) * weight) + 0.55, 0, 1)
    shade = _blur(lum * opaque, GOLD_SOFTNESS)
    reflection = _blur(np.sin(shade * np.pi * 3) * 0.5 + 0.5, GOLD_SOFTNESS) * 2 - 1
    lum = np.clip(lum + GOLD_REFLECTIONS * weight * reflection * 0.5 * lum, 0, 1)
    glint = np.exp(-(((xx - yy) + 6) / 5.0) ** 2) * (lum > 0.3)
    lum = np.clip(lum + GOLD_GLINT * weight * glint, 0, 1)
    stops = [s[0] for s in ORANGE_GOLD]
    out = a.copy()
    for channel in range(3):
        out[..., channel] = np.interp(lum, stops, [s[1][channel] for s in ORANGE_GOLD]) / 255
    return Image.fromarray((out * 255).round().astype("uint8"), "RGBA")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    images = Path(sys.argv[1]) / "Images"
    sheet = Image.open(images / "flowers64x64_grid.png").convert("RGBA")
    mask = Image.open(images / "Flowers64x64_Grid_mask.png").convert("RGBA")
    for src, dst in zip(SOURCE_CELLS, TARGET_CELLS):
        if sheet.crop(cell_box(dst)).getbbox():
            raise SystemExit(f"cell {dst} of flowers64x64_grid.png is not empty")
        sheet.paste(gold_finish(trim(recolour(sheet.crop(cell_box(src))), art=True)), cell_box(dst)[:2])
        mask.paste(trim(mask.crop(cell_box(src)).convert("RGBA"), art=False), cell_box(dst)[:2])
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / "flowers64x64_grid.png")
    mask.save(OUT / "flowers64x64_grid_mask.png")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}: Mirabilis in cells {TARGET_CELLS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
