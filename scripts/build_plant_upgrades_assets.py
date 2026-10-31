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
  with the Time Warp clock, a 15th with Add Money's gold coins, a 16th (row 15)
  with the Extra Greenhouse item (greenhouse_icon below), and rows 16 and 17
  (the 17th and 18th) hold Automatic Sprinklers and the Auto-Healer, upright only
  (scripts/build_auto_upgrades_assets.py), row 18 the Extra Chemical Slots item and
  row 19 its two gold page arrows (scripts/build_chem_slots_assets.py), row 20 the Extra
  Nursery's golden pot (nursery_icon below), rows 21 and 22 Muta-Flower and Muta-Foliage
  (chemicals 48 and 49, scripts/build_muta_assets.py). A chemical's row is
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
GREENHOUSE_SOURCE = "greenhouse2.png"   # the repaired greenhouse (greenhouse1.png, sprite 0xC2, is the broken one)
GREENHOUSE_CROP = (12, 0, 119, 156)    # the building: its corner posts, roof and step; not the bushes around it
GREENHOUSE_EAVES = 45                   # source rows above the eaves: only the roof, not the trees behind it
GREENHOUSE_BOX = (48, 54)             # the most the picture may be (w, h): the tool shelf's items are 35-69 x 43-49
GREENHOUSE_CENTRE_X = 28                # in the cell: x 432 on screen, the middle of the click rectangle
GREENHOUSE_BOTTOM = 62                  # in the cell, exclusive: the last row at y 111 on screen
NURSERY_ROW = 20                        # the Extra Nursery's golden pot (frames 40 and 41)
NURSERY_HEIGHT = 52                     # the Time Warp clock's visible height beside it (Add Money's: 51)
NURSERY_BOTTOM = 61                     # in the cell, exclusive: the clock's and coins' bottom line (y 357)


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
    sheet = Image.new("RGBA", (stock.width, (CHEM_ROWS + 14) * CHEM_CELL))
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
    # Row 15 (frames 30 and 31): the Extra Greenhouse item, a small opaque greenhouse.
    icon = greenhouse_icon(images)
    for column in (0, 1):
        sheet.alpha_composite(icon, (column * CHEM_CELL, (CHEM_ROWS + 6) * CHEM_CELL))
    # Rows 16 and 17 (frames 32 and 34): Automatic Sprinklers and the Auto-Healer, upright only
    # (scripts/build_auto_upgrades_assets.py).
    import build_auto_upgrades_assets
    for row, cell in build_auto_upgrades_assets.plant_rows(stock, Image.open(images / "Tools_Grid.png").convert("RGBA")).items():
        sheet.paste(cell, (0, row * CHEM_CELL))
    # Rows 18 and 19 (frames 36 and 38-39): Extra Chemical Slots' store item and its page arrows
    # (scripts/build_chem_slots_assets.py).
    import build_chem_slots_assets
    for row, cells in build_chem_slots_assets.plant_rows(stock, images).items():
        for column, cell in enumerate(cells):
            sheet.paste(cell, (column * CHEM_CELL, row * CHEM_CELL))
    # Row 20 (frames 40 and 41): the Extra Nursery item, the game's golden pot pre-scaled.
    pot = nursery_icon(images)
    for column in (0, 1):
        sheet.alpha_composite(pot, (column * CHEM_CELL, NURSERY_ROW * CHEM_CELL))
    # Rows 21 and 22 (frames 42-45): chemicals 48 and 49, Muta-Flower and Muta-Foliage, the stock
    # Mutation Liquid recoloured, upright then pouring (scripts/build_muta_assets.py).
    import build_muta_assets
    for name, cells in build_muta_assets.plant_cells(stock).items():
        for column, cell in enumerate(cells):
            sheet.paste(cell, (column * CHEM_CELL, build_muta_assets.MUTA_ROWS[name] * CHEM_CELL))
    return sheet


def nursery_icon(images: Path) -> Image.Image:
    """The Extra Nursery's store icon, one 70 x 70 cell: the game's golden pot (goldpot.png, sprite
    0x2C, 76 x 64), shrunk to the visible height of its Nursery-shelf neighbours (the Time Warp clock,
    52 px, and Add Money's coins, 51 px: NURSERY_HEIGHT) and standing on their bottom line (61 of the
    cell), centred in the cell. The DLL draws the cell at (449, 296) at scale 1 (the plant store's draw
    ignores a scale: the 0.84 it used to pass drew the pot at its full 76 x 64), so the pot spans
    x 453-514, y 305-356, centred where the full-size pot was (x 484)."""
    pot = Image.open(images / "goldpot.png").convert("RGBA")
    if pot.size != (76, 64):
        raise SystemExit(f"goldpot.png is {pot.size}, expected the stock 76 x 64")
    pot = pot.crop(pot.getbbox())
    scale = NURSERY_HEIGHT / pot.height
    small = pot.resize((round(pot.width * scale), NURSERY_HEIGHT), Image.LANCZOS)
    cell = Image.new("RGBA", (CHEM_CELL, CHEM_CELL))
    cell.alpha_composite(small, ((CHEM_CELL - small.width) // 2, NURSERY_BOTTOM - small.height))
    return cell


def greenhouse_icon(images: Path) -> Image.Image:
    """The Extra Greenhouse's store icon, one 70 x 70 cell: the game's own repaired
    greenhouse (greenhouse2.png, sprite 0x88, 157 x 207), the building alone (cropped
    from the bushes around it, the trees behind its roof taken out), shrunk to the size
    of the tool shelf's items and made fully opaque (every pixel opaque or empty, cut at
    half alpha, so nothing of it is see-through). The DLL draws the cell at the item's place (404, 50) at
    scale 1, so the picture stands on the shelf line (its last row at y 111, as the seed
    boxes beside it) inside the item's click rectangle {404, 52, 461, 113}."""
    stock = Image.open(images / GREENHOUSE_SOURCE).convert("RGBA")
    if stock.size != (157, 207):
        raise SystemExit(f"{GREENHOUSE_SOURCE} is {stock.size}, expected the stock 157 x 207")
    a = np.asarray(stock.crop(GREENHOUSE_CROP)).copy()
    a[..., 3] = np.where(a[..., 3] >= 128, 255, 0)
    r, g = a[..., 0].astype(int), a[..., 1].astype(int)
    leafy = (g > r + 8) & (g >= a[..., 2])                        # the trees behind the roof
    a[:GREENHOUSE_EAVES, :, 3][leafy[:GREENHOUSE_EAVES]] = 0
    solid = Image.fromarray(a, "RGBA")
    solid = solid.crop(solid.getbbox())
    scale = min(GREENHOUSE_BOX[0] / solid.width, GREENHOUSE_BOX[1] / solid.height)
    small = solid.resize((round(solid.width * scale), round(solid.height * scale)), Image.LANCZOS)
    b = np.asarray(small).copy()                 # every pixel opaque or empty: nothing see-through
    b[..., 3] = np.where(b[..., 3] >= 128, 255, 0)
    small = Image.fromarray(b, "RGBA")
    cell = Image.new("RGBA", (CHEM_CELL, CHEM_CELL))
    cell.alpha_composite(small, (GREENHOUSE_CENTRE_X - small.width // 2, GREENHOUSE_BOTTOM - small.height))
    return cell


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
