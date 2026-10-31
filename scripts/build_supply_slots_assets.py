"""Build the "Extra supply slots" art from the game's own pictures, and the page mockups.

    python scripts/build_supply_slots_assets.py "<vanilla Fish Tycoon folder>"

Everything is made from the game's own pictures in Assets\\ft.dat (owner: native game art):

* SupplyArrowLeft.png / SupplyArrowRight.png (3 frames of 18 x 15: normal, hover, not
  bought): the game's UP_ARROW.png turned on its side and scaled to fit, exactly as Extra
  Tanks' tank arrows (scripts/build_extra_tanks_assets.py), drawn at scale 1 one above the
  other in the strip of top bar between supply slot 4 (x <= 199) and the first Magic Breeds
  silhouette (x >= 227). The third frame is the first greyed and darkened, as Extra Tanks'
  "not bought" tank buttons.
* SupplySlotUnused.png (36 x 40): page 3 has three slots; the fourth slot's frame of the top
  bar, greyed and darkened the same way, so it does not look like a slot.
* ITEM_EXTRA_SUPPLY_SLOTS.png: the Upgrades screen's picture of the item -- the top bar's
  frames of supply slots 2-4 with the game's own medicine, chemical and egg pictures in them.

Also writes docs/images/extra-supply-slots-page-<1|2|3>.png (the tank screen's top with
each page, as ftfp_supply_slots.c draws it, at twice the size) and
docs/images/extra-supply-slots-locked.png (before they are bought).
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_extra_tanks_assets as tanks  # noqa: E402

OUT = ROOT / "assets" / "fish_tycoon_supply_slots" / "Images"
PREVIEWS = ROOT / "docs" / "images"

# ftfp_supply_slots.c: BOX, PICTURE_X, ARROW_X / ARROW_Y_LEFT / ARROW_Y_RIGHT / ARROW_W / ARROW_H.
BOXES = ((14, 9, 49, 48), (63, 9, 98, 48), (113, 9, 148, 48), (164, 9, 199, 48))
PICTURE_X = (0x19, 78, 126, 174)
PICTURE_Y = 15
ARROW = (204, 8, 18, 15)
ARROW_RIGHT_Y = 31
MAGIC_BREEDS_X = 227                      # the first silhouette (0x41D75C)
TOOLS = ("tool_foodcan_flakes.png", "tool_fishvitamins.png", "tool_growthhormone.png", "tool_fisheggs_common.png",
         "tool_icktreatment.png", "tool_unknownchemical.png", "tool_fisheggs_rare.png", "tool_fungaltreatment.png",
         "tool_fisheggs_unusual.png")


def read_game(game: Path) -> dict[str, Image.Image]:
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist() if not n.startswith("__MACOSX")}
        wanted = ("ui_maintank_top_png.png", "up_arrow.png", "maintank1_bg_png.png") + TOOLS
        return {w: Image.open(io.BytesIO(archive.read(names[w]))).convert("RGBA") for w in wanted}


def greyed(image: Image.Image) -> Image.Image:
    """Greyed and darkened, as Extra Tanks' tank not bought yet (frame 3 of its buttons)."""
    px = np.array(image).astype(float)
    grey = px[:, :, :3].mean(axis=2, keepdims=True)
    px[:, :, :3] = (0.35 * px[:, :, :3] + 0.65 * grey) * 0.55
    return Image.fromarray(np.clip(px, 0, 255).astype(np.uint8), "RGBA")


def build(game: Path) -> dict[str, Image.Image]:
    art = read_game(game)
    out: dict[str, Image.Image] = {}
    _x, _y, w, h = ARROW
    right = art["up_arrow.png"].rotate(-90, expand=True)
    right = right.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
    hover = np.array(right).astype(float)
    hover[:, :, :3] = np.minimum(255, hover[:, :, :3] * 1.35 + 30)
    lit = Image.fromarray(hover.astype(np.uint8), "RGBA")
    for name, normal_img, lit_img in (("SupplyArrowRight.png", right, lit),
                                      ("SupplyArrowLeft.png", right.transpose(Image.FLIP_LEFT_RIGHT),
                                       lit.transpose(Image.FLIP_LEFT_RIGHT))):
        sheet = Image.new("RGBA", (3 * w, h), (0, 0, 0, 0))
        sheet.paste(normal_img, (0, 0))
        sheet.paste(lit_img, (w, 0))
        sheet.paste(greyed(normal_img), (2 * w, 0))
        out[name] = sheet
    bar = art["ui_maintank_top_png.png"]
    left, top, r, b = BOXES[3]
    out["SupplySlotUnused.png"] = greyed(bar.crop((left, top, r + 1, b + 1)))
    # The store's picture: slots 2-4 of the bar with a medicine, a chemical and eggs in them.
    rows = []
    for tools in (("tool_icktreatment.png", "tool_growthhormone.png", "tool_fisheggs_common.png"),
                  ("tool_fungaltreatment.png", "tool_unknownchemical.png", "tool_fisheggs_rare.png")):
        row = bar.crop((BOXES[1][0] - 3, 5, BOXES[3][2] + 4, 53)).copy()
        for p, tool in zip((1, 2, 3), tools):
            row.alpha_composite(art[tool], (PICTURE_X[p] - (BOXES[1][0] - 3), PICTURE_Y - 5))
        rows.append(row)
    strip = Image.new("RGBA", (rows[0].width, 2 * rows[0].height), (0, 0, 0, 0))
    strip.paste(rows[0], (0, 0))
    strip.paste(rows[1], (0, rows[0].height))
    scale = 76 / strip.width
    out["ITEM_EXTRA_SUPPLY_SLOTS.png"] = strip.convert("RGBa").resize(
        (76, max(1, round(strip.height * scale))), Image.LANCZOS).convert("RGBA")
    return out


def preview(game: Path, images: dict[str, Image.Image], page: int, owned: bool = True,
            hover: int = -1) -> Image.Image:
    """The tank screen's top 120 rows as ftfp_supply_slots.c draws page `page` (1-3), with
    supplies in every slot; hover = the arrow (0 upper, 1 lower) under the mouse."""
    art = read_game(game)
    screen = art["maintank1_bg_png.png"].crop((0, 0, 800, 120)).copy()
    screen.alpha_composite(art["ui_maintank_top_png.png"], (0, 0))
    pages = {1: TOOLS[0:4], 2: TOOLS[4:8], 3: TOOLS[8:9] + (TOOLS[3], TOOLS[5])}
    for p, tool in enumerate(pages[page]):
        screen.alpha_composite(art[tool], (PICTURE_X[p], PICTURE_Y))
    if page == 3:
        screen.alpha_composite(images["SupplySlotUnused.png"], BOXES[3][:2])
    x, y, w, h = ARROW
    for a, (name, ay) in enumerate((("SupplyArrowLeft.png", y), ("SupplyArrowRight.png", ARROW_RIGHT_Y))):
        frame = 2 if not owned else 1 if a == hover else 0
        screen.alpha_composite(images[name].crop((frame * w, 0, (frame + 1) * w, h)), (x, ay))
    return screen.resize((1600, 240), Image.NEAREST)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    game = Path(sys.argv[1])
    images = build(game)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, image in images.items():
        image.save(OUT / name)
        print(f"{(OUT / name).relative_to(ROOT).as_posix()}: {image.width} x {image.height}")
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    for page in (1, 2, 3):
        path = PREVIEWS / f"extra-supply-slots-page-{page}.png"
        preview(game, images, page, hover=1 if page == 2 else -1).convert("RGB").save(path)
        print(path.relative_to(ROOT).as_posix())
    path = PREVIEWS / "extra-supply-slots-locked.png"
    preview(game, images, 1, owned=False).convert("RGB").save(path)
    print(path.relative_to(ROOT).as_posix())
    # The Upgrades screen with the item in its net cell (ftfp_ds_store.c ITEM: 320, 168, 77 x 69),
    # drawn over docs/images/auto-upgrades-fish.png (the screen's own capture).
    store = Image.open(PREVIEWS / "auto-upgrades-fish.png").convert("RGBA")
    icon = images["ITEM_EXTRA_SUPPLY_SLOTS.png"]
    store.alpha_composite(icon, (320 + (77 - icon.width) // 2, 168 + (69 - icon.height) // 2))
    path = PREVIEWS / "extra-supply-slots-store.png"
    store.convert("RGB").save(path)
    print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
