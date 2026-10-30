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
  white (the owner's pick), an 11th and 12th with the Revival Potion
  (chemical 37) and Revita-Seed (chemical 38) from the owner's icons
  (scripts/build_potion_assets.py: upright, then pouring), a 13th with the
  Radioactive Plant Formula Bomb (chemical 39): the stock Fertilizer Bomb
  (row 5) with its white glass turned rainbow and its yellow label white,
  the cap left grey (the owner's pick), a 14th
  with the Time Warp clock and a 15th with Add Money's gold coins; rows 16 and 17
  (the 17th and 18th) hold Automatic Sprinklers and the Auto-Healer, upright only
  (scripts/build_auto_upgrades_assets.py). A chemical's row is
  its id - 27 (the game draws frame 2 x id - 54). The DLL points the chemical
  sheet record at it.
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

import build_money_cheat_assets
import build_potion_assets

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
FERTILIZER_BOMB_ROW = 5        # chemical 32, the stock Fertilizer Bomb
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


def rainbow_bomb(cell: Image.Image) -> Image.Image:
    """The Formula Bomb (owner, 2026-10-30): the Fertilizer Bomb's white glass
    turned rainbow and its yellow label turned white, shading kept. The grey
    cap above the glass stays as it is."""
    a = np.asarray(cell.convert("RGBA")).astype(float) / 255
    out = a.copy()
    rows = [y for y in range(a.shape[0]) if any(a[y, x, 3] > 0 and colorsys.rgb_to_hsv(*a[y, x, :3])[1] > 0.25
                                                for x in range(a.shape[1]))]
    glass_top = min(rows) if rows else 0                   # the cap ends where the label starts
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            if a[y, x, 3] == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(*a[y, x, :3])
            if s > 0.25:                                   # the yellow label: white
                out[y, x, :3] = (min(1, v * 1.05),) * 3
            elif y >= glass_top:                           # the white glass: rainbow
                out[y, x, :3] = colorsys.hsv_to_rgb(((x + y) / 40) % 1, 0.75, v)
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
    sheet = Image.new("RGBA", (stock.width, (CHEM_ROWS + 9) * CHEM_CELL))
    sheet.paste(stock, (0, 0))
    for column in (0, 1):
        box = (column * CHEM_CELL, MUTATION_ROW * CHEM_CELL, (column + 1) * CHEM_CELL, (MUTATION_ROW + 1) * CHEM_CELL)
        sheet.paste(prismatic(stock.crop(box), only_coloured=True), (column * CHEM_CELL, CHEM_ROWS * CHEM_CELL))
    # Rows 10 and 11 (frames 20-23): chemicals 37 and 38, the Revival Potion and Revita-Seed.
    for row, source in build_potion_assets.PLANT_ROWS.items():
        for column, cell in enumerate(build_potion_assets.plant_cells(source, stock)):
            sheet.paste(cell, (column * CHEM_CELL, row * CHEM_CELL))
    # Row 12 (frames 24 and 25): the Formula Bomb, the stock Fertilizer Bomb (row 5) with rainbow glass.
    for column in (0, 1):
        box = (column * CHEM_CELL, FERTILIZER_BOMB_ROW * CHEM_CELL, (column + 1) * CHEM_CELL, (FERTILIZER_BOMB_ROW + 1) * CHEM_CELL)
        sheet.paste(rainbow_bomb(stock.crop(box)), (column * CHEM_CELL, (CHEM_ROWS + 3) * CHEM_CELL))
    # Row 13 (frames 26 and 27): the Time Warp clock, the owner's icon, centred in its cell.
    clock = Image.open(ROOT / "assets" / "time_warp" / "time_warp_icon_source.png").convert("RGBA")
    clock.thumbnail((CHEM_CELL - 6, CHEM_CELL - 6), Image.LANCZOS)
    for column in (0, 1):
        at = (column * CHEM_CELL + (CHEM_CELL - clock.width) // 2, (CHEM_ROWS + 4) * CHEM_CELL + (CHEM_CELL - clock.height) // 2)
        sheet.alpha_composite(clock, at)
    # Row 14 (frames 28 and 29): Add Money, the owner's pile of gold coins, in the clock's 64 px box.
    pile = build_money_cheat_assets.coins(build_money_cheat_assets.PLANT_ICON_BOX)
    for column in (0, 1):
        at = (column * CHEM_CELL + (CHEM_CELL - pile.width) // 2, (CHEM_ROWS + 5) * CHEM_CELL + (CHEM_CELL - pile.height) // 2)
        sheet.alpha_composite(pile, at)
    # Rows 16 and 17 (frames 32 and 34): Automatic Sprinklers and the Auto-Healer, upright only
    # (scripts/build_auto_upgrades_assets.py). Row 15 is the Extra Greenhouse's.
    import build_auto_upgrades_assets
    for row, cell in build_auto_upgrades_assets.plant_rows(stock, Image.open(images / "Tools_Grid.png").convert("RGBA")).items():
        sheet.paste(cell, (0, row * CHEM_CELL))
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
