"""Build the Automatic Sprinklers, Auto-Feeder and Auto-Healer art from the owner's pictures.

    python scripts/build_auto_upgrades_assets.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>"

The sources are the owner's pictures, committed as they came (assets/auto_upgrades):

* automatic_sprinklers_source.png (159 x 130): the sprinkler head, Plant Tycoon;
* auto_feeder_source.png (197 x 154): the green feeder, Fish Tycoon;
* auto_healer_source.png (197 x 154): the same machine in hot pink, both games' Auto-Healer
  (scripts/build_auto_healer_source.py makes it from the feeder).

Every picture is pre-scaled to its final size and drawn at scale 1 (the game's store draws ignore a
scale), the visible size of its neighbours on that Upgrades screen, as scripts/build_potion_assets.py
sizes the potions: the visible part scaled to the neighbour's visible height, standing on the
neighbour's bottom line, centred where the neighbour is centred.

Fish Tycoon (assets/fish_tycoon_ds_store/Images, DS Store Items' sprites 244 and 245):

* ITEM_AUTO_FEEDER.png, ITEM_AUTO_HEALER.png: the store pictures, 57 px visible on a 65 px tall
  canvas, bottom at 62, as the stock store pictures beside them (item_growthhormone.png: 34 x 57
  visible, bottom 62; ClonaFish's and the Revival Potion's the same). They are permanent machines,
  like the stock Aeration System, so there is no shelf picture or cursor.

Plant Tycoon: rows 16 and 17 (frames 32 and 34) of
assets/plant_tycoon_upgrades/Images/Chemicals_Grid_upgrades.png, which
scripts/build_plant_upgrades_assets.py writes with plant_rows() from here (the one spare sprite
record holds the Upgrades link, so new art lives in that sheet). Only the first 70 x 70 cell of each
row is drawn (they are never poured):

* row 16, Automatic Sprinklers, on the tool shelf under the Extra Greenhouse (drawn at 397, 111, its art centred on the greenhouse's): the
  visible height of the Fourth Seed Box's drawer beside it (Tools_Grid.png frame 9: 49 px, bottom 65
  of its cell, drawn at 461, 111), standing on that bottom line;
* row 17, the Auto-Healer, on the chemicals shelf beside the Formula Bomb (drawn at 655, 116): the
  visible height of the Radioactive Plant Formula above it (row 9, the stock Mutation Liquid flask of row 7: 41 px, bottom 54), on that line.

It also renders docs/images/auto-upgrades-fish.png and docs/images/auto-upgrades-plant.png: each
game's Upgrades screen with every item at its final size and place.
tests/test_auto_upgrades.py rebuilds every picture and compares it with the committed one.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

import build_potion_assets as potions

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "assets" / "auto_upgrades"
SPRINKLERS = SOURCES / "automatic_sprinklers_source.png"
FEEDER = SOURCES / "auto_feeder_source.png"
HEALER = SOURCES / "auto_healer_source.png"
FISH_OUT = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
PREVIEWS = ROOT / "docs" / "images"

CHEM_CELL = 70
FORMULA_ROW = 7                            # the stock Mutation Liquid flask, which the formula (row 9) is drawn from
SPRINKLERS_ROW, HEALER_ROW = 16, 17
TOOL_COLUMNS, TOOL_ROWS = 5, 3
SEED_BOX_FRAME = 9                         # the Fourth Seed Box's drawer, row 2 of the tool shelf
FISH_VISIBLE, FISH_BOTTOM, FISH_CANVAS_H = 57, 62, 65

# Where the DLLs draw them: Fish (x, y, w, h) net cells (ftfp_ds_store.c ITEM), Plant (x, y) cells.
FISH_CELLS = (("ITEM_AUTO_FEEDER.png", 141, 165, 73, 72), ("ITEM_AUTO_HEALER.png", 234, 165, 71, 72))
PLANT_PLACES = {2 * SPRINKLERS_ROW: (397, 111), 2 * HEALER_ROW: (655, 116)}


def standing(icon: Image.Image, height: int, bottom: int, centre: float, size: tuple[int, int]) -> Image.Image:
    """The icon's visible part at `height` px (aspect kept), its bottom on `bottom`, centred on `centre`."""
    art = icon.crop(potions.visible_box(icon))
    art = potions.scaled(art, height / art.height)
    canvas = Image.new("RGBA", size)
    x = min(max(0, round(centre - art.width / 2)), size[0] - art.width)
    canvas.alpha_composite(art, (x, bottom - art.height))
    return potions.clean(canvas)


def fish_pictures() -> dict[str, Image.Image]:
    """The store pictures: 57 px visible, bottom 62, on a canvas as wide as the art and 65 tall."""
    out = {}
    for name, source in (("ITEM_AUTO_FEEDER.png", FEEDER), ("ITEM_AUTO_HEALER.png", HEALER)):
        icon = Image.open(source).convert("RGBA")
        box = potions.visible_box(icon)
        width = round((box[2] - box[0]) * FISH_VISIBLE / (box[3] - box[1]))
        out[name] = standing(icon, FISH_VISIBLE, FISH_BOTTOM, width / 2, (width, FISH_CANVAS_H))
    return out


def plant_rows(stock_sheet: Image.Image, tools: Image.Image) -> dict[int, Image.Image]:
    """Sheet row -> its first 70 x 70 cell (the second stays empty)."""
    cw, ch = tools.width // TOOL_COLUMNS, tools.height // TOOL_ROWS
    box = tools.crop(((SEED_BOX_FRAME % TOOL_COLUMNS) * cw, (SEED_BOX_FRAME // TOOL_COLUMNS) * ch,
                      (SEED_BOX_FRAME % TOOL_COLUMNS + 1) * cw, (SEED_BOX_FRAME // TOOL_COLUMNS + 1) * ch))
    _, top, _, bottom = potions.visible_box(box)
    sprinklers = standing(Image.open(SPRINKLERS).convert("RGBA"), bottom - top, bottom, CHEM_CELL / 2,
                          (CHEM_CELL, CHEM_CELL))
    formula = stock_sheet.crop((0, FORMULA_ROW * CHEM_CELL, CHEM_CELL, (FORMULA_ROW + 1) * CHEM_CELL))
    left, top, right, bottom = potions.visible_box(formula)
    healer = standing(Image.open(HEALER).convert("RGBA"), bottom - top, bottom, (left + right) / 2,
                      (CHEM_CELL, CHEM_CELL))
    return {SPRINKLERS_ROW: sprinklers, HEALER_ROW: healer}


def fish_preview(game: Path, built: dict[str, Image.Image]) -> Image.Image:
    """Every item of the Upgrades page in its cell (Time Warp and Add Money with their settings, the
    Extra Tank with 3 extra tanks), the two new ones in row 2 beside ClonaFish."""
    screen = potions.fish_stock(game)["supplyshop_bg_out.bmp"].copy()
    cells = potions.FISH_CELLS + (("ITEM_TANK2.png", 598, 246, 160, 70),) + FISH_CELLS
    for name, x, y, w, h in cells:
        if name in built:
            art = built[name]
        elif name == "ITEM_TANK2.png":
            import io
            import zipfile
            with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
                names = {n.lower(): n for n in archive.namelist()}
                art = Image.open(io.BytesIO(archive.read(names["item_tank2.png"]))).convert("RGBA")
        else:
            art = Image.open(FISH_OUT / name).convert("RGBA")
        screen.alpha_composite(art, (x + (w - art.width) // 2, y + (h - art.height) // 2))
    return screen


def plant_preview(plant: Path, sheet: Image.Image) -> Image.Image:
    """Every item of the Upgrades view in its place, with the extra greenhouse and nursery and the
    two new ones; each new one also shown with its owned tick."""
    import build_money_cheat_assets
    screen = build_money_cheat_assets.plant_preview(plant)        # seeds, formula, seed boxes, clock, coins
    for frame, (x, y) in potions.PLANT_CHEMICALS.items():         # Revival Potion, Revita-Seed, Formula Bomb
        screen.alpha_composite(sheet.crop(((frame % 2) * CHEM_CELL, (frame // 2) * CHEM_CELL,
                                           (frame % 2 + 1) * CHEM_CELL, (frame // 2 + 1) * CHEM_CELL)), (x, y))
    images = plant / "Images"
    # The extra greenhouse and nursery items (ftfp_plant_upgrades.c EXTRA_ITEM), at their sizes.
    for picture, scale, x, y in (("greenhouse1.png", 0.29, 404 + 6, 50), ("goldpot.png", 0.84, 440 + 6, 296)):
        art = Image.open(images / picture).convert("RGBA")
        art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
        screen.alpha_composite(art, (x, y))
    for frame, (x, y) in PLANT_PLACES.items():
        cell = sheet.crop(((frame % 2) * CHEM_CELL, (frame // 2) * CHEM_CELL,
                           (frame % 2 + 1) * CHEM_CELL, (frame // 2 + 1) * CHEM_CELL))
        screen.alpha_composite(cell, (x, y))
    return screen


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    fish, plant = Path(sys.argv[1]), Path(sys.argv[2])
    built = fish_pictures()
    for name, image in built.items():
        image.save(FISH_OUT / name)
        print(f"{(FISH_OUT / name).relative_to(ROOT).as_posix()}: {image.width} x {image.height}")
    import build_plant_upgrades_assets
    sheet = build_plant_upgrades_assets.formula_bottle(plant / "Images")
    sheet.save(build_plant_upgrades_assets.OUT / "Chemicals_Grid_upgrades.png")
    print(f"Chemicals_Grid_upgrades.png: {sheet.width} x {sheet.height}")
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    fish_preview(fish, built).convert("RGB").save(PREVIEWS / "auto-upgrades-fish.png")
    plant_preview(plant, sheet).convert("RGB").save(PREVIEWS / "auto-upgrades-plant.png")
    print("previews: docs/images/auto-upgrades-fish.png, docs/images/auto-upgrades-plant.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
