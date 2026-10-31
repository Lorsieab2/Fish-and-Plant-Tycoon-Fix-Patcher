"""Build the Muta-Fin, Muta-Body, Muta-Flower and Muta-Foliage art from the stock bottles.

    python scripts/build_muta_assets.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>"

Each is a recolour of the stock mutation bottle of its game: only the liquid's colour turns, every
other pixel (the glass, the white label, the markings, the shading, the alpha) is kept.

* Fish Tycoon: the stock Unknown Chemical (item_unknownchemical.png, tool_unknownchemical.png in
  Assets/ft.dat), a red flask with yellow markings. The red liquid (hue within RED_BAND of red, with
  some saturation) turns; the yellow markings stay yellow.
    - Muta-Fin: royal blue (hue 229, about #2341C8, the owner's pick);
    - Muta-Body: sea green (hue 172).
  Each is at least 39 degrees of dominant hue from every other Fish supply's picture (the stock
  Growth Hormone, 11 degrees from Muta-Fin, is half as saturated and a jar, not a flask).
  Written to assets/fish_tycoon_ds_store/Images, sized as the Revival Potion's and ClonaFish's
  (scripts/build_potion_assets.py matched()): ITEM_<NAME>.png at the stock Growth Hormone store
  picture's visible size and place (34 x 57 visible on 48 x 65, bottom 62), TOOL_<NAME>.png at its
  shelf picture's (31 px visible on 24 x 35), and TOOL_dropper_<NAME>.png, the stock Growth Hormone
  dropper (tool_dropper4.png) recoloured to the liquid, as the other new chemicals' droppers are.

* Plant Tycoon: the stock Mutation Liquid flask (Chemicals_Grid.png row 7), orange with a white label
  and a red biohazard sign. Only the orange turns (hue within ORANGE_BAND); the label, the sign and
  the cap stay.
    - Muta-Flower: pink (hue 0.92);
    - Muta-Foliage: leaf green (hue 0.31).
  Both cells of row 7 (upright, then pouring) are recoloured as they stand, so each picture is the
  stock flask's own size (41 px visible, the Radioactive Plant Formula's and the Revival Potion's) on
  the same shelf line, pre-scaled (the game's store draw ignores a scale). Only the orange turns,
  so the white label and the red sign stay.
  scripts/build_plant_upgrades_assets.py writes them into Chemicals_Grid_upgrades.png at MUTA_ROWS
  (row = chemical id - 27): rows 21 and 22, chemicals 48 and 49, after the rows Extra Chemical
  Slots (PR #91) uses or may use (18-20).

It also renders docs/images/muta-chemicals-fish.png, docs/images/muta-chemicals-plant.png (each
game's Upgrades screen with every item in its place and the new ones beside them) and
docs/images/muta-chemicals-icons.png (the four beside the stock bottles they are made from, enlarged
4x and at game size). tests/test_muta_chemicals.py rebuilds every picture and compares it.
"""

from __future__ import annotations

import colorsys
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import build_potion_assets as potions

ROOT = Path(__file__).resolve().parents[1]
FISH_OUT = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
PREVIEWS = ROOT / "docs" / "images"
CHEM_CELL = 70
MUTATION_ROW = 7

RED_BAND = (0.93, 0.07)          # the Unknown Chemical's red liquid (wraps through 0)
ORANGE_BAND = (0.045, 0.14)      # the Mutation Liquid's orange glass
DROPPER_BAND = (0.58, 0.75)      # the stock Growth Hormone dropper's violet-blue liquid (tool_dropper4.png)
MIN_SATURATION = 0.25

# A colour: (hue, saturation factor, brightness factor). Muta-Fin is the owner's deep royal blue
# (#2341C8: hue 229, the stock red liquid's saturation 0.69 and brightness 0.61 raised to about
# 0.83 and 0.76); the owner turned down the first cyan as too like the other recolours. The others
# keep the stock liquid's saturation and brightness.
# Muta-Body is a saturated sea green (hue 172), out of the first violet's clash with Fish Vitamins
# (284) and the purple beaker: at least 40 degrees from every Fish supply's dominant hue.
ROYAL_BLUE = (229 / 360, 1.2, 1.25)
SEA_GREEN = (172 / 360, 1.15, 1.15)
FISH_COLOURS = {"MUTA_FIN": ROYAL_BLUE, "MUTA_BODY": SEA_GREEN}
PLANT_COLOURS = {"MUTA_FLOWER": (0.92, 1.0, 1.0), "MUTA_FOLIAGE": (0.31, 1.0, 1.0)}
MUTA_ROWS = {"MUTA_FLOWER": 21, "MUTA_FOLIAGE": 22}      # chemicals 48 and 49

# Where the DLLs draw them. Fish: the Upgrades page's net cells (x, y, w, h), row 2 after the Extra
# Supply Slots (ftfp_ds_store.c ITEM). Plant: the chemicals shelf's third row (ftfp_plant_upgrades.c),
# beside Extra Chemical Slots (598, 177).
FISH_CELLS = (("ITEM_MUTA_FIN.png", 411, 168, 79, 69), ("ITEM_MUTA_BODY.png", 503, 168, 79, 69))
PLANT_PLACES = {"MUTA_FLOWER": (655, 177), "MUTA_FOLIAGE": (712, 177)}


def in_band(h: float, band: tuple[float, float]) -> bool:
    lo, hi = band
    return (h >= lo or h <= hi) if lo > hi else lo <= h <= hi


def recolour(image: Image.Image, band: tuple[float, float], colour: tuple[float, float, float]) -> Image.Image:
    """The liquid's pixels (hue in band, saturation above MIN_SATURATION) take the colour's hue,
    their saturation and brightness scaled by its factors (brightness capped at 1); every other
    pixel is kept."""
    hue, s_factor, v_factor = colour
    a = np.asarray(image.convert("RGBA")).astype(float) / 255
    out = a.copy()
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            if a[y, x, 3] == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(*a[y, x, :3])
            if s > MIN_SATURATION and in_band(h, band):
                out[y, x, :3] = colorsys.hsv_to_rgb(hue, min(1.0, s * s_factor), min(1.0, v * v_factor))
    return potions.clean(Image.fromarray((out * 255).round().astype("uint8"), "RGBA"))


def fish_stock(game: Path) -> dict[str, Image.Image]:
    import io
    import zipfile
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist()}
        wanted = ("item_unknownchemical.png", "tool_unknownchemical.png", "tool_dropper4.png",
                  "item_growthhormone.png", "tool_growthhormone.png")
        return {n: Image.open(io.BytesIO(archive.read(names[n]))).convert("RGBA") for n in wanted}


def fish_pictures(game: Path) -> dict[str, Image.Image]:
    stock = fish_stock(game)
    out = {}
    for name, colour in FISH_COLOURS.items():
        item = recolour(stock["item_unknownchemical.png"], RED_BAND, colour)
        tool = recolour(stock["tool_unknownchemical.png"], RED_BAND, colour)
        out[f"ITEM_{name}.png"] = potions.matched(item, stock["item_growthhormone.png"])
        out[f"TOOL_{name}.png"] = potions.matched(tool, stock["tool_growthhormone.png"])
        out[f"TOOL_dropper_{name}.png"] = recolour(stock["tool_dropper4.png"], DROPPER_BAND, colour)
    return out


def plant_cells(stock_sheet: Image.Image) -> dict[str, tuple[Image.Image, Image.Image]]:
    """Name -> (upright, pouring): the stock Mutation Liquid's row 7 cells, recoloured."""
    cells = [stock_sheet.crop((c * CHEM_CELL, MUTATION_ROW * CHEM_CELL, (c + 1) * CHEM_CELL, (MUTATION_ROW + 1) * CHEM_CELL))
             for c in (0, 1)]
    return {name: tuple(recolour(cell, ORANGE_BAND, colour) for cell in cells) for name, colour in PLANT_COLOURS.items()}


def fish_preview(game: Path, built: dict[str, Image.Image]) -> Image.Image:
    import build_auto_upgrades_assets
    screen = build_auto_upgrades_assets.fish_preview(game, {})
    slots = FISH_OUT.parent.parent / "fish_tycoon_supply_slots" / "Images" / "ITEM_EXTRA_SUPPLY_SLOTS.png"
    cells = ((("ITEM_EXTRA_SUPPLY_SLOTS.png", 320, 168, 77, 69),) if slots.is_file() else ()) + FISH_CELLS
    for name, x, y, w, h in cells:
        art = built[name] if name in built else Image.open(slots).convert("RGBA")
        screen.alpha_composite(art, (x + (w - art.width) // 2, y + (h - art.height) // 2))
    return screen


def plant_preview(plant: Path, sheet: Image.Image) -> Image.Image:
    import build_auto_upgrades_assets
    screen = build_auto_upgrades_assets.plant_preview(plant, sheet)
    # Extra Chemical Slots' item beside them (chem_slots_link.h: row 18 at 598, 177).
    screen.alpha_composite(sheet.crop((0, 18 * CHEM_CELL, CHEM_CELL, 19 * CHEM_CELL)), (598, 177))
    for name, (x, y) in PLANT_PLACES.items():
        row = MUTA_ROWS[name]
        screen.alpha_composite(sheet.crop((0, row * CHEM_CELL, CHEM_CELL, (row + 1) * CHEM_CELL)), (x, y))
    return screen


def icon_sheet(fish: Path, plant: Path, built: dict[str, Image.Image], cells: dict) -> Image.Image:
    """Each game's stock bottle and its two recolours: 4x on top, game size below, labelled."""
    stock = fish_stock(fish)
    sheet = Image.open(plant / "Images" / "Chemicals_Grid.png").convert("RGBA")
    mutation = [sheet.crop((c * CHEM_CELL, MUTATION_ROW * CHEM_CELL, (c + 1) * CHEM_CELL, (MUTATION_ROW + 1) * CHEM_CELL))
                for c in (0, 1)]
    columns = [
        ("Unknown Chemical (stock)", [stock["item_unknownchemical.png"], stock["tool_unknownchemical.png"]]),
        ("Muta-Fin", [built["ITEM_MUTA_FIN.png"], built["TOOL_MUTA_FIN.png"], built["TOOL_dropper_MUTA_FIN.png"]]),
        ("Muta-Body", [built["ITEM_MUTA_BODY.png"], built["TOOL_MUTA_BODY.png"], built["TOOL_dropper_MUTA_BODY.png"]]),
        ("Mutation Liquid (stock)", mutation),
        ("Muta-Flower", list(cells["MUTA_FLOWER"])),
        ("Muta-Foliage", list(cells["MUTA_FOLIAGE"])),
    ]
    width, scale = 300, 4
    out = Image.new("RGBA", (width * len(columns), 820), (58, 66, 84, 255))
    draw = ImageDraw.Draw(out)
    for i, (label, pictures) in enumerate(columns):
        x0 = i * width
        draw.text((x0 + 10, 10), label, fill=(255, 255, 255, 255))
        big = pictures[0].crop(potions.visible_box(pictures[0]))
        big = big.resize((big.width * scale, big.height * scale), Image.NEAREST)
        out.alpha_composite(big, (x0 + (width - big.width) // 2, 40 + 280 - big.height))
        x = x0 + 20
        for picture in pictures:                                 # game size
            out.alpha_composite(picture, (x, 720 - picture.height))
            x += picture.width + 10
        draw.text((x0 + 10, 730), "game size: store, shelf/pour, dropper", fill=(200, 200, 200, 255))
    # Every Fish Tycoon supply at game size, stock and patcher, for comparison: the store pictures,
    # then the shelf (supply slot) pictures, the two new ones last.
    full = Image.new("RGBA", (out.width, out.height + 230), (58, 66, 84, 255))
    full.alpha_composite(out)
    draw = ImageDraw.Draw(full)
    stores, shelves = fish_comparison(fish, built)
    for row, (label, pictures) in enumerate((("Fish store pictures", stores), ("Fish shelf pictures", shelves))):
        y = out.height + 10 + row * 110
        draw.text((10, y), label + " (game size; the last two are Muta-Fin and Muta-Body)", fill=(255, 255, 255, 255))
        x = 10
        for picture in pictures:
            full.alpha_composite(picture, (x, y + 95 - picture.height))
            x += picture.width + 8
    return full


FISH_COMPARE_STOCK = ("growthhormone", "fishvitamins", "icktreatment", "fungaltreatment", "unknownchemical",
                      "fisheggs_common", "fisheggs_unusual", "fisheggs_rare")
FISH_COMPARE_PATCH = ("RADIOACTIVE_GROWTHHORMONE", "REVIVAL_POTION", "CLONAFISH", "FISHEGGS_EXOTIC")


def fish_comparison(fish: Path, built: dict[str, Image.Image]) -> tuple[list[Image.Image], list[Image.Image]]:
    import io
    import zipfile
    with zipfile.ZipFile(fish / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist()}
        get = lambda n: Image.open(io.BytesIO(archive.read(names[n]))).convert("RGBA")
        stores = [get(f"item_{n}.png") for n in FISH_COMPARE_STOCK if f"item_{n}.png" in names]
        stores += [get(n) for n in ("item_purplebeaker.png", "item_orangebeaker.png")]
        shelves = [get(f"tool_{n}.png") for n in FISH_COMPARE_STOCK if f"tool_{n}.png" in names]
    stores += [Image.open(FISH_OUT / f"ITEM_{n}.png").convert("RGBA") for n in FISH_COMPARE_PATCH]
    shelves += [Image.open(FISH_OUT / f"TOOL_{n}.png").convert("RGBA") for n in FISH_COMPARE_PATCH]
    stores += [built["ITEM_MUTA_FIN.png"], built["ITEM_MUTA_BODY.png"]]
    shelves += [built["TOOL_MUTA_FIN.png"], built["TOOL_MUTA_BODY.png"]]
    return stores, shelves


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    fish, plant = Path(sys.argv[1]), Path(sys.argv[2])
    built = fish_pictures(fish)
    for name, image in built.items():
        image.save(FISH_OUT / name)
        print(f"{(FISH_OUT / name).relative_to(ROOT).as_posix()}: {image.width} x {image.height}")
    import build_plant_upgrades_assets
    sheet = build_plant_upgrades_assets.formula_bottle(plant / "Images")
    sheet.save(build_plant_upgrades_assets.OUT / "Chemicals_Grid_upgrades.png")
    print(f"Chemicals_Grid_upgrades.png: {sheet.width} x {sheet.height}")
    stock_sheet = Image.open(plant / "Images" / "Chemicals_Grid.png").convert("RGBA")
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    fish_preview(fish, built).convert("RGB").save(PREVIEWS / "muta-chemicals-fish.png")
    plant_preview(plant, sheet).convert("RGB").save(PREVIEWS / "muta-chemicals-plant.png")
    icon_sheet(fish, plant, built, plant_cells(stock_sheet)).convert("RGB").save(PREVIEWS / "muta-chemicals-icons.png")
    print("previews: docs/images/muta-chemicals-fish.png, -plant.png, -icons.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
