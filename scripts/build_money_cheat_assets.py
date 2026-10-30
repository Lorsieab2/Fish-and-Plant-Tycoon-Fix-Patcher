"""Build the Add Money item's picture from the owner's pile of gold coins.

    python scripts/build_money_cheat_assets.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>"

The source is assets/money_cheat/coins_source.png (195 x 159, transparent).
It writes

* assets/fish_tycoon_ds_store/Images/ITEM_ADD_MONEY.png: the coins at the DS
  store animals' icon height (60 px, 74 x 60), for the sixth net cell of the
  Fish Tycoon Upgrades page;
* docs/images/add-money-fish.png and docs/images/add-money-plant.png: each
  game's Upgrades screen background with the items at their final size and
  place, to show what the screen looks like.

Plant Tycoon's coins are row 14 of Chemicals_Grid_upgrades.png, written by
scripts/build_plant_upgrades_assets.py with coins() from here (the Time Warp
clock's 64 px box in a 70 px chemical cell). Downscaling is done on
premultiplied alpha, so the transparent edge gets no dark fringe.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "money_cheat" / "coins_source.png"
FISH_ICON = ROOT / "assets" / "fish_tycoon_ds_store" / "Images" / "ITEM_ADD_MONEY.png"
FISH_ICON_BOX = (80, 60)                 # the DS store animals' icon box (scripts/build_ds_store_assets.py)
PLANT_ICON_BOX = (64, 64)                # the Time Warp clock's box in a 70 x 70 chemical cell
PREVIEWS = ROOT / "docs" / "images"


def coins(box: tuple[int, int]) -> Image.Image:
    """The coins fitted inside box, aspect kept, Lanczos on premultiplied alpha."""
    image = Image.open(SOURCE).convert("RGBA")
    scale = min(box[0] / image.width, box[1] / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def fish_preview(game: Path) -> Image.Image:
    """The Fish Tycoon Upgrades page: the net cells of ftfp_ds_store.c's ITEM table."""
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist()}
        screen = Image.open(io.BytesIO(archive.read(names["supplyshop_bg_out.bmp"]))).convert("RGBA")
    images = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
    cells = (("ITEM_DS_PUFFER.png", 44, 83, 85, 70), ("ITEM_DS_STINGRAY.png", 141, 87, 73, 71),
             ("ITEM_DS_EEL.png", 234, 93, 71, 71), ("ITEM_FISHEGGS_EXOTIC.png", 320, 98, 77, 69),
             ("ITEM_TIME_WARP.png", 411, 100, 79, 66), ("ITEM_ADD_MONEY.png", 503, 100, 79, 66))
    for name, x, y, w, h in cells:
        art = Image.open(images / name).convert("RGBA")
        screen.alpha_composite(art, (x + (w - art.width) // 2, y + (h - art.height) // 2))
    return screen


def plant_preview(game: Path) -> Image.Image:
    """The Plant Tycoon Upgrades view: ftfp_plant_upgrades.c's on_draw places."""
    screen = Image.open(game / "Images" / "Store_BG.jpg").convert("RGBA")
    images = ROOT / "assets" / "plant_tycoon_upgrades" / "Images"
    seeds = Image.open(images / "seed_grid_legendary.png").convert("RGBA")
    chems = Image.open(images / "Chemicals_Grid_upgrades.png").convert("RGBA")
    tools = Image.open(game / "Images" / "Tools_Grid.png").convert("RGBA") if (game / "Images" / "Tools_Grid.png").is_file() else None

    def seed(frame: int) -> Image.Image:
        x, y = (frame % 16) * 50, (frame // 16) * 50
        return seeds.crop((x, y, x + 50, y + 50))

    def chem(frame: int) -> Image.Image:
        x, y = (frame % 2) * 70, (frame // 2) * 70
        return chems.crop((x, y, x + 70, y + 70))

    for i, foliage in enumerate((3, 11, 19)):
        screen.alpha_composite(seed(95 + foliage), (602 + 57 * i, 315))
    screen.alpha_composite(chem(18), (598, 55))           # the formula
    if tools is not None:
        cell = tools.width // 5, tools.height // 3
        for i in range(3):
            frame = i * 5 + 4
            box = ((frame % 5) * cell[0], (frame // 5) * cell[1])
            screen.alpha_composite(tools.crop((box[0], box[1], box[0] + cell[0], box[1] + cell[1])), (461, 50 + 61 * i))
    screen.alpha_composite(chem(26), (300, 296))           # Time Warp (row 13)
    screen.alpha_composite(chem(28), (370, 296))           # Add Money (row 14)
    return screen


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    fish, plant = Path(sys.argv[1]), Path(sys.argv[2])
    icon = coins(FISH_ICON_BOX)
    icon.save(FISH_ICON)
    print(f"{FISH_ICON.relative_to(ROOT).as_posix()}: {icon.width} x {icon.height}")
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    fish_preview(fish).convert("RGB").save(PREVIEWS / "add-money-fish.png")
    plant_preview(plant).convert("RGB").save(PREVIEWS / "add-money-plant.png")
    print(f"previews in {PREVIEWS.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
