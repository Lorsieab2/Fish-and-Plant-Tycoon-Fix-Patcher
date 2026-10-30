"""Build the Revival Potion, Revita-Seed and ClonaFish art from the owner's icons.

    python scripts/build_potion_assets.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>"

The sources are the owner's pictures, committed as they came:

* assets/revival_potion/revival_potion_source.png (37 x 67): the amber flask, both games;
* assets/clonafish/clonafish_source.png (39 x 65): the magenta bottle, Fish Tycoon;
* assets/revita_seed/revita_seed_source.png (39 x 65): the teal bottle, Plant Tycoon (the owner's red
  original, revita_seed_owner_red.png, sits beside it and is not used).

Each picture matches its neighbours' visible size, not its cell (the owner: the first, cell-sized
build looked huge): the icon's visible part is scaled to the visible height of the stock picture it
sits beside and stands on that picture's bottom line, centred on it, on a canvas that picture's size.

Fish Tycoon (assets/fish_tycoon_ds_store/Images), beside the stock Growth Hormone's pictures:

* ITEM_<NAME>.png: the store picture, 48 x 65 with 57 px visible (item_growthhormone.png);
* TOOL_<NAME>.png: the bottle on the supply shelf, 24 x 35 with 31 px visible (tool_growthhormone.png);
* TOOL_dropper_<NAME>.png: the cursor while it is used, the stock Growth Hormone dropper
  (tool_dropper4.png, 21 x 21) recoloured to the icon's own liquid, as the Radioactive Growth
  Hormone's green dropper is (scripts/build_growth_hormone_assets.py).

Plant Tycoon: rows 10 (chemical 37, the Revival Potion) and 11 (chemical 38, Revita-Seed) of
assets/plant_tycoon_upgrades/Images/Chemicals_Grid_upgrades.png, which
scripts/build_plant_upgrades_assets.py writes with plant_cells() from here: upright in the first
70 x 70 cell at the stock Mutation Liquid flask's visible height (41 px, the Radioactive Plant
Formula's too) on its bottom line, poured (tilted as the stock flasks are, the same scale) in the
second, centred where the stock flask pours.

Every picture is scaled on premultiplied alpha (no dark fringe on the transparent edge) and its
fully transparent pixels are written as 0, 0, 0, 0.

It also renders docs/images/revival-potion-fish.png and docs/images/revival-potion-plant.png: each
game's Upgrades screen with every item at its final size and place, and the new pictures enlarged
beside the stock ones they are matched to.
tests/test_revival_potion.py rebuilds every picture and compares it with the committed one.
"""

from __future__ import annotations

import colorsys
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FISH_OUT = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
PREVIEWS = ROOT / "docs" / "images"

REVIVAL = ROOT / "assets" / "revival_potion" / "revival_potion_source.png"
CLONAFISH = ROOT / "assets" / "clonafish" / "clonafish_source.png"
REVITA = ROOT / "assets" / "revita_seed" / "revita_seed_source.png"

# name in the file names -> (source, the liquid's hue: the median hue of the source's coloured pixels)
FISH_ITEMS = {"REVIVAL_POTION": (REVIVAL, 0.095), "CLONAFISH": (CLONAFISH, 0.831)}
DROPPER_NAMES = {"REVIVAL_POTION": "TOOL_dropper_REVIVAL.png", "CLONAFISH": "TOOL_dropper_CLONAFISH.png"}
STOCK_HUE = 2 / 3                      # the stock Growth Hormone's violet-blue liquid

CHEM_CELL = 70
MUTATION_ROW = 7                        # the stock Mutation Liquid flask, the Radioactive Plant Formula's model
POUR_ANGLE = 40                         # degrees, counter-clockwise: the neck leans left, as the stock flasks pour
PLANT_ROWS = {10: REVIVAL, 11: REVITA}  # sheet row -> source (row = chemical id - 27)


def clean(image: Image.Image) -> Image.Image:
    a = np.asarray(image.convert("RGBA")).copy()
    a[a[..., 3] == 0] = 0
    return Image.fromarray(a, "RGBA")


def recolour(image: Image.Image, hue: float) -> Image.Image:
    """Each pixel's hue turned by hue - STOCK_HUE; saturation, brightness and alpha kept."""
    rgba = np.asarray(image.convert("RGBA")).astype(float) / 255
    out = rgba.copy()
    for y in range(rgba.shape[0]):
        for x in range(rgba.shape[1]):
            h, s, v = colorsys.rgb_to_hsv(*rgba[y, x, :3])
            out[y, x, :3] = colorsys.hsv_to_rgb((h + hue - STOCK_HUE) % 1.0, s, v)
    return clean(Image.fromarray((out * 255).round().astype("uint8"), "RGBA"))


def visible_box(image: Image.Image) -> tuple[int, int, int, int]:
    """The box of the picture's visible (alpha above 0) pixels."""
    return image.getchannel("A").getbbox()


def scaled(image: Image.Image, factor: float) -> Image.Image:
    size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    return clean(image.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA"))


def matched(icon: Image.Image, reference: Image.Image) -> Image.Image:
    """The icon's visible part at the reference's visible height (aspect kept), on a canvas the
    reference's size, standing where the reference stands: the same bottom, centred on it."""
    art = icon.crop(visible_box(icon))
    left, top, right, bottom = visible_box(reference)
    art = scaled(art, (bottom - top) / art.height)
    canvas = Image.new("RGBA", reference.size)
    x = min(max(0, round((left + right - art.width) / 2)), reference.width - art.width)
    canvas.alpha_composite(art, (x, bottom - art.height))
    return clean(canvas)


def fish_stock(game: Path) -> dict[str, Image.Image]:
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist()}
        wanted = ("tool_dropper4.png", "supplyshop_bg_out.bmp", "item_growthhormone.png", "tool_growthhormone.png")
        return {name: Image.open(io.BytesIO(archive.read(names[name]))).convert("RGBA") for name in wanted}


def fish_pictures(game: Path) -> dict[str, Image.Image]:
    """The Fish Tycoon pictures, by file name: each the visible size of the stock Growth Hormone's
    own picture (34 x 57 in the store, 19 x 31 on the shelf), standing where it stands."""
    stock = fish_stock(game)
    out = {}
    for name, (source, hue) in FISH_ITEMS.items():
        icon = Image.open(source).convert("RGBA")
        out[f"ITEM_{name}.png"] = matched(icon, stock["item_growthhormone.png"])
        out[f"TOOL_{name}.png"] = matched(icon, stock["tool_growthhormone.png"])
        out[DROPPER_NAMES[name]] = recolour(stock["tool_dropper4.png"], hue)
    return out


def plant_cells(source: Path, stock_sheet: Image.Image) -> tuple[Image.Image, Image.Image]:
    """One chemical-sheet row, two 70 x 70 cells: the bottle upright at the visible height of the
    stock Mutation Liquid flask (row 7, which the Radioactive Plant Formula is drawn from: 41 px),
    standing on its bottom line; then pouring, tilted as the stock flasks pour, at the same scale,
    centred where the stock flask's pouring frame is."""
    icon = Image.open(source).convert("RGBA")
    cell = lambda column: stock_sheet.crop((column * CHEM_CELL, MUTATION_ROW * CHEM_CELL,
                                            (column + 1) * CHEM_CELL, (MUTATION_ROW + 1) * CHEM_CELL))
    upright = matched(icon, cell(0))
    art = icon.crop(visible_box(icon))
    left, top, right, bottom = visible_box(cell(0))
    factor = (bottom - top) / art.height
    tilted = icon.convert("RGBa").rotate(POUR_ANGLE, resample=Image.BICUBIC, expand=True).convert("RGBA")
    tilted = scaled(tilted.crop(visible_box(tilted)), factor)
    left, top, right, bottom = visible_box(cell(1))
    poured = Image.new("RGBA", (CHEM_CELL, CHEM_CELL))
    poured.alpha_composite(tilted, (round((left + right - tilted.width) / 2), round((top + bottom - tilted.height) / 2)))
    return upright, clean(poured)


# The Fish Tycoon Upgrades page's net cells (x, y, w, h), as in ftfp_ds_store.c's ITEM table.
FISH_CELLS = (("ITEM_DS_PUFFER.png", 44, 83, 85, 70), ("ITEM_DS_STINGRAY.png", 141, 87, 73, 71),
              ("ITEM_DS_EEL.png", 234, 93, 71, 71), ("ITEM_FISHEGGS_EXOTIC.png", 320, 98, 77, 69),
              ("ITEM_TIME_WARP.png", 411, 100, 79, 66), ("ITEM_ADD_MONEY.png", 503, 100, 79, 66),
              ("ITEM_RADIOACTIVE_GROWTHHORMONE.png", 595, 90, 79, 72),
              ("ITEM_REVIVAL_POTION.png", 687, 90, 79, 72), ("ITEM_CLONAFISH.png", 44, 165, 85, 72))


def fish_preview(game: Path, built: dict[str, Image.Image]) -> Image.Image:
    screen = fish_stock(game)["supplyshop_bg_out.bmp"].copy()
    for name, x, y, w, h in FISH_CELLS:
        art = built[name] if name in built else Image.open(FISH_OUT / name).convert("RGBA")
        screen.alpha_composite(art, (x + (w - art.width) // 2, y + (h - art.height) // 2))
    # On the description panel, 2x, to compare: the stock Growth Hormone, the Radioactive one, the
    # Revival Potion and ClonaFish, in the store and on the shelf, then the droppers.
    stock = fish_stock(game)
    rgh = lambda kind: Image.open(FISH_OUT / f"{kind}_RADIOACTIVE_GROWTHHORMONE.png").convert("RGBA")
    rows = ([stock["item_growthhormone.png"], rgh("ITEM"), built["ITEM_REVIVAL_POTION.png"], built["ITEM_CLONAFISH.png"]],
            [stock["tool_growthhormone.png"], rgh("TOOL"), built["TOOL_REVIVAL_POTION.png"], built["TOOL_CLONAFISH.png"],
             stock["tool_dropper4.png"], Image.open(FISH_OUT / "TOOL_dropper_RADIOACTIVE.png").convert("RGBA"),
             built["TOOL_dropper_REVIVAL.png"], built["TOOL_dropper_CLONAFISH.png"]])
    x = 60
    for art in rows[0]:                                   # the store pictures, 2x
        screen.alpha_composite(art.resize((art.width * 2, art.height * 2), Image.NEAREST), (x, 350))
        x += art.width * 2 + 4
    x = 56
    for art in rows[1]:                                   # the shelf pictures and droppers, true size
        screen.alpha_composite(art, (x, 536 - art.height))
        x += art.width + 6
    return screen


# The new chemicals on the Plant Tycoon Upgrades view (ftfp_plant_upgrades.c on_draw): frame -> (x, y).
PLANT_CHEMICALS = {20: (655, 55), 22: (712, 55), 24: (598, 116)}     # + the Formula Bomb, under the formula


def plant_preview(plant: Path, sheet: Image.Image) -> Image.Image:
    """The Add Money preview's view (every other item in its place), with the two new chemicals."""
    import build_money_cheat_assets
    screen = build_money_cheat_assets.plant_preview(plant)
    for frame, (x, y) in PLANT_CHEMICALS.items():
        cell = sheet.crop(((frame % 2) * CHEM_CELL, (frame // 2) * CHEM_CELL,
                           (frame % 2 + 1) * CHEM_CELL, (frame // 2 + 1) * CHEM_CELL))
        screen.alpha_composite(cell, (x, y))
    # Below the shelves, 1.5x, to compare: the stock Mutation Liquid flask (row 7), the formula
    # (row 9), the Revival Potion and Revita-Seed (rows 10, 11); the stock Fertilizer Bomb (row 5)
    # and the Formula Bomb (row 12), each upright and pouring.
    x = 250
    for k, row in enumerate((7, 9) + tuple(PLANT_ROWS) + (5, 12)):
        for column in (0, 1):
            cell = sheet.crop((column * CHEM_CELL, row * CHEM_CELL, (column + 1) * CHEM_CELL, (row + 1) * CHEM_CELL))
            at = (x, 400) if k < 4 else (x - 4 * 132, 470)
            screen.alpha_composite(cell.resize((105, 105), Image.NEAREST), at)
            x += 66
    return screen


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    fish, plant = Path(sys.argv[1]), Path(sys.argv[2])
    built = fish_pictures(fish)
    for name, image in built.items():
        image.save(FISH_OUT / name)
        print(f"{(FISH_OUT / name).relative_to(ROOT).as_posix()}: {image.width} x {image.height}")
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    fish_preview(fish, built).convert("RGB").save(PREVIEWS / "revival-potion-fish.png")
    sheet = Image.open(ROOT / "assets" / "plant_tycoon_upgrades" / "Images" / "Chemicals_Grid_upgrades.png").convert("RGBA")
    plant_preview(plant, sheet).convert("RGB").save(PREVIEWS / "revival-potion-plant.png")
    print("previews: docs/images/revival-potion-fish.png, docs/images/revival-potion-plant.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
