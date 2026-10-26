"""Build the Plant Upgrades art from the vanilla Plant Tycoon images.

    python scripts/build_plant_upgrades_assets.py "<vanilla Plant Tycoon folder>"

Writes, under assets/plant_tycoon_upgrades/Images:

* seed_grid_legendary.png: the stock seed_Grid.png (16 x 6 cells of 50 x 50)
  made two rows taller. The new frames 96..118 hold the Legendary Seeds, one
  per foliage (frame 95 + foliage): the stock Extinct seed of that foliage
  (frame foliage*4 - 1) recoloured prismatic, the owner's pick. The DLL points
  the game's seed sheet record at this file and gives it 8 rows, so the stock
  file is never changed.
* Chemicals_Grid_upgrades.png: the stock Chemicals_Grid.png (2 x 9 cells of
  70 x 70: each chemical upright, then pouring) with a 10th row for the
  Radioactive Plant Formula (chemical id 36): the Mutation Liquid bottle (row
  7) made prismatic on its coloured parts only, so the white bottle stays
  white (the owner's pick). The DLL points the chemical sheet record at it.
* upgrades_link.png: the store's "Upgrades" link, two frames side by side
  (normal white, hover yellow), set from the game's own font (PTfontsmall.png
  and its glyph table in the executable) and drawn at 80% of the shelf-sign
  size (the owner asked for it a bit smaller). The DLL registers it as a sprite.
"""

from __future__ import annotations

import colorsys
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "plant_tycoon_upgrades" / "Images"
SEED_CELL = 50
SEED_COLUMNS = 16
SEED_ROWS = 6
LEGENDARY_ROWS = 8
FOLIAGES = 23
FIRST_LEGENDARY = 96
CHEM_CELL = 70
CHEM_ROWS = 9
MUTATION_ROW = 7
FONT_TABLE = 0x47A550          # PTfontsmall glyphs: {char, x0, y0, x1, y1} records, ended by a char <= 0
IMAGE_BASE = 0x400000
LINK_TEXT = "Upgrades"
LINK_SCALE = 0.8
LINK_COLOURS = ((255, 255, 255), (255, 224, 96))     # normal, hover


def seed_box(frame: int) -> tuple[int, int, int, int]:
    x, y = (frame % SEED_COLUMNS) * SEED_CELL, (frame // SEED_COLUMNS) * SEED_CELL
    return x, y, x + SEED_CELL, y + SEED_CELL


def prismatic(cell: Image.Image, only_coloured: bool = False) -> Image.Image:
    """A rainbow sweeping diagonally across the art. Each pixel keeps its
    brightness and adds its own hue to the sweep, so spots, stripes, labels
    and shading stay visible (the owner's pick after comparing blends).
    With only_coloured, near-white and grey parts are left as they are."""
    a = np.asarray(cell.convert("RGBA")).astype(float) / 255
    out = a.copy()
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            if a[y, x, 3] == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(*a[y, x, :3])
            if only_coloured and s <= 0.25:
                continue
            out[y, x, :3] = colorsys.hsv_to_rgb(((x + y) / 70 + h) % 1, max(s, 0.6), v)
    return Image.fromarray((out * 255).round().astype("uint8"), "RGBA")


def legendary_seeds(images: Path) -> Image.Image:
    stock = Image.open(images / "seed_Grid.png").convert("RGBA")
    if stock.size != (SEED_COLUMNS * SEED_CELL, SEED_ROWS * SEED_CELL):
        raise SystemExit(f"seed_Grid.png is {stock.size}, expected the stock 800 x 300")
    sheet = Image.new("RGBA", (stock.width, LEGENDARY_ROWS * SEED_CELL))
    sheet.paste(stock, (0, 0))
    for foliage in range(1, FOLIAGES + 1):
        extinct = stock.crop(seed_box(foliage * 4 - 1))
        sheet.paste(prismatic(extinct), seed_box(FIRST_LEGENDARY - 1 + foliage)[:2])
    return sheet


def formula_bottle(images: Path) -> Image.Image:
    stock = Image.open(images / "Chemicals_Grid.png").convert("RGBA")
    if stock.size != (2 * CHEM_CELL, CHEM_ROWS * CHEM_CELL):
        raise SystemExit(f"Chemicals_Grid.png is {stock.size}, expected the stock 140 x 630")
    sheet = Image.new("RGBA", (stock.width, (CHEM_ROWS + 1) * CHEM_CELL))
    sheet.paste(stock, (0, 0))
    for column in (0, 1):
        box = (column * CHEM_CELL, MUTATION_ROW * CHEM_CELL, (column + 1) * CHEM_CELL, (MUTATION_ROW + 1) * CHEM_CELL)
        sheet.paste(prismatic(stock.crop(box), only_coloured=True), (column * CHEM_CELL, CHEM_ROWS * CHEM_CELL))
    return sheet


def glyphs(exe: bytes) -> dict[int, tuple[int, int, int, int]]:
    table, at = {}, FONT_TABLE - IMAGE_BASE
    while True:
        char, x0, y0, x1, y1 = struct.unpack_from("<5i", exe, at)
        if char <= 0 or char > 255:
            return table
        table[char] = (x0, y0, x1, y1)
        at += 20


def upgrades_link(folder: Path) -> Image.Image:
    """The word as the game sets it: each glyph's rectangle, side by side."""
    table = glyphs((folder / "Plant Tycoon.exe").read_bytes())
    font = Image.open(folder / "Images" / "PTfontsmall.png").convert("RGBA")
    rects = [table[ord(ch)] for ch in LINK_TEXT]
    word = Image.new("RGBA", (sum(r[2] - r[0] for r in rects), max(r[3] - r[1] for r in rects)))
    x = 0
    for x0, y0, x1, y1 in rects:
        word.alpha_composite(font.crop((x0, y0, x1, y1)), (x, 0))
        x += x1 - x0
    word = word.resize((round(word.width * LINK_SCALE), round(word.height * LINK_SCALE)), Image.LANCZOS)
    sheet = Image.new("RGBA", (word.width * 2, word.height))
    for frame, colour in enumerate(LINK_COLOURS):
        tinted = np.asarray(word).copy()
        tinted[..., :3] = (tinted[..., :3].astype(float) * np.array(colour) / 255).round().astype("uint8")
        sheet.paste(Image.fromarray(tinted, "RGBA"), (frame * word.width, 0))
    return sheet


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    images = Path(sys.argv[1]) / "Images"
    OUT.mkdir(parents=True, exist_ok=True)
    legendary_seeds(images).save(OUT / "seed_grid_legendary.png")
    formula_bottle(images).save(OUT / "Chemicals_Grid_upgrades.png")
    link = upgrades_link(Path(sys.argv[1]))
    link.save(OUT / "upgrades_link.png")
    print(f"upgrades_link.png: 2 frames of {link.width // 2} x {link.height}")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
