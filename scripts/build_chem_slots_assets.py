"""The Extra Chemical Slots art: rows 18 and 19 of the Plant Upgrades chemicals sheet.

scripts/build_plant_upgrades_assets.py writes them into
assets/plant_tycoon_upgrades/Images/Chemicals_Grid_upgrades.png with plant_rows() from here
(the game's one spare sprite record holds the Upgrades link, so new art lives in that sheet, which
Store Upgrades and Items.dll registers with 20 rows). Every picture is pre-scaled and drawn at
scale 1: the plant game's draw (0x4208F0) ignores its scale argument.

* Row 18, frame 36: the store item, on the chemicals shelf's third row (drawn at 598, 177): two of
  the game's own bottles (Chemicals_Grid.png, upright: chemical 28's bottle and chemical 31's jug)
  side by side with a small gold arrow (the game's rightarrow.png) in front, the whole the visible
  height of the Radioactive Plant Formula two rows above it (41 px, its bottom at 54 of the cell),
  standing on that line, inside the item's click rectangle (cell x 12..57, y 8..60).
* Row 19, frames 38 and 39: the greenhouse's page arrows, the game's gold rightarrow.png and
  leftarrow.png (first frame, their 45 x 45 art) shrunk to ARROW_SIZE and set at the cell's top
  left; Extra Chemical Slots.dll draws the cell at (154, 104), on the Tools box's plaque.
"""

from __future__ import annotations

from PIL import Image

CELL = 70
ICON_ROW = 18
ARROW_ROW = 19
ARROW_SIZE = 24                    # native/ftfp_chem_slots/ftfp_chem_slots.c ARROW_W / ARROW_H
ICON_HEIGHT = 41                   # the formula's visible height (row 9: Mutation Liquid's flask)
ICON_BOTTOM = 54                   # its bottom line in the cell
ICON_LEFT, ICON_RIGHT = 14, 56     # inside the click rectangle's cell x 12..57
BOTTLES = (28, 31)                 # chemical ids: upright frame 2 * id - 54


def _frame(sheet: Image.Image, frame: int) -> Image.Image:
    x, y = (frame % 2) * CELL, (frame // 2) * CELL
    cell = sheet.crop((x, y, x + CELL, y + CELL))
    return cell.crop(cell.getbbox())


def _arrow(images, name: str, size: int) -> Image.Image:
    strip = Image.open(images / name).convert("RGBA")
    art = strip.crop((0, 0, strip.height, strip.height))
    art = art.crop(art.getbbox())
    return art.resize((size, size), Image.LANCZOS)


def icon(stock: Image.Image, images) -> Image.Image:
    """The store item: two bottles, a gold arrow in front, the formula's height on its line."""
    bottles = [_frame(stock, 2 * cid - 54) for cid in BOTTLES]
    gap = 2
    group = Image.new("RGBA", (sum(b.width for b in bottles) + gap, max(b.height for b in bottles)))
    x = 0
    for b in bottles:
        group.alpha_composite(b, (x, group.height - b.height))
        x += b.width + gap
    arrow = _arrow(images, "rightarrow.png", round(group.height * 0.42))
    whole = Image.new("RGBA", (group.width + arrow.width // 3, group.height))
    whole.alpha_composite(group, (0, 0))
    whole.alpha_composite(arrow, (whole.width - arrow.width, whole.height - arrow.height))
    scale = min(ICON_HEIGHT / whole.height, (ICON_RIGHT - ICON_LEFT) / whole.width)
    small = whole.resize((round(whole.width * scale), round(whole.height * scale)), Image.LANCZOS)
    cell = Image.new("RGBA", (CELL, CELL))
    left = ICON_LEFT + (ICON_RIGHT - ICON_LEFT - small.width) // 2
    cell.alpha_composite(small, (left, ICON_BOTTOM - small.height))
    return cell


def arrows(images) -> tuple[Image.Image, Image.Image]:
    """The page arrows: right (to page 2), left (back to page 1), each at its cell's top left."""
    out = []
    for name in ("rightarrow.png", "leftarrow.png"):
        cell = Image.new("RGBA", (CELL, CELL))
        cell.alpha_composite(_arrow(images, name, ARROW_SIZE), (0, 0))
        out.append(cell)
    return out[0], out[1]


def plant_rows(stock: Image.Image, images) -> dict[int, tuple[Image.Image, Image.Image]]:
    """{row: (frame 2 row, frame 2 row + 1)} for the chemicals sheet."""
    item = icon(stock, images)
    return {ICON_ROW: (item, item), ARROW_ROW: arrows(images)}
