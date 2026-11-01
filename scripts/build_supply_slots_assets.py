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
* SupplyPage1.png .. SupplyPage3.png: "1/3", "2/3", "3/3" in the game's own font
  (font_triplex_sanslightlin_bold_16pt.png), small (PAGE_HEIGHT pixels) and in the yellow of the
  bar's "Magic Breeds Discovered", drawn at scale 1 centred under the arrows (ftfp_supply_slots.c
  PAGE_CENTRE_X / PAGE_Y).

Also writes docs/images/extra-supply-slots-page-<1|2|3>.png (the tank screen's top with
each page, as ftfp_supply_slots.c draws it, at twice the size),
docs/images/extra-supply-slots-locked.png (before they are bought) and
docs/images/supply-slot-tooltip-<hormone|food|eggs>.png: DS Store Items' tooltip for a slot under the
mouse, its box drawn as the game's hint box (0x423280: the fill colour 0x50 0x4C 0x40 inside, the
CUSTOMPOPUP_FTROPESTYLE_BAR_* ropes just outside the edges, placed as that code places them) and the text in the game's bitmap font. The
game draws the text in its hint font, which is not a file in ft.dat, so the letters are an
approximation of it; the box, its place and its size rules are the DLL's.
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
PAGE_CENTRE_X, PAGE_Y, PAGE_HEIGHT = ARROW[0] + ARROW[2] // 2, 46, 9   # ftfp_supply_slots.c
LABEL_YELLOW = (250, 206, 22)             # the bar's "Magic Breeds Discovered"
ROPES = ("custompopup_ftropestyle_bar_top.png", "custompopup_ftropestyle_bar_bottom.png",
         "custompopup_ftropestyle_bar_left.png", "custompopup_ftropestyle_bar_right.png")
HINT_FILL = (0x50, 0x4C, 0x40, 0xFF)      # the hint box's fill (0x423217)
TIP = {"line": 20, "pad_x": 10, "pad_y": 6, "top": 60, "margin": 12}   # ftfp_ds_store.c TIP_*
TOOLS = ("tool_foodcan_flakes.png", "tool_fishvitamins.png", "tool_growthhormone.png", "tool_fisheggs_common.png",
         "tool_icktreatment.png", "tool_unknownchemical.png", "tool_fisheggs_rare.png", "tool_fungaltreatment.png",
         "tool_fisheggs_unusual.png")


def read_game(game: Path) -> dict[str, Image.Image]:
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist() if not n.startswith("__MACOSX")}
        wanted = ("ui_maintank_top_png.png", "up_arrow.png", "maintank1_bg_png.png",
                  "font_triplex_sanslightlin_bold_16pt.png") + TOOLS + ROPES
        return {w: Image.open(io.BytesIO(archive.read(names[w]))).convert("RGBA") for w in wanted}


def greyed(image: Image.Image) -> Image.Image:
    """Greyed and darkened, as Extra Tanks' tank not bought yet (frame 3 of its buttons)."""
    px = np.array(image).astype(float)
    grey = px[:, :, :3].mean(axis=2, keepdims=True)
    px[:, :, :3] = (0.35 * px[:, :, :3] + 0.65 * grey) * 0.55
    return Image.fromarray(np.clip(px, 0, 255).astype(np.uint8), "RGBA")


def small_label(glyphs, text: str, colour: tuple[int, int, int], height: int) -> Image.Image:
    """Text in the game's bitmap font, scaled to `height` pixels, in one colour."""
    width = sum(glyphs[c].width for c in text)
    canvas = Image.new("RGBA", (width, 24), (0, 0, 0, 0))
    x = 0
    for c in text:
        g = glyphs[c]
        fill = Image.new("RGBA", g.size, colour + (255,))
        fill.putalpha(Image.fromarray(np.array(g)[:, :, 3]))
        canvas.alpha_composite(fill, (x, 0))
        x += g.width
    canvas = canvas.crop(canvas.getbbox())
    scale = height / canvas.height
    return canvas.convert("RGBa").resize((max(1, round(canvas.width * scale)), height),
                                         Image.LANCZOS).convert("RGBA")


def build(game: Path) -> dict[str, Image.Image]:
    art = read_game(game)
    out: dict[str, Image.Image] = {}
    glyphs = tanks.font_glyphs(art["font_triplex_sanslightlin_bold_16pt.png"])
    for n in (1, 2, 3):
        out[f"SupplyPage{n}.png"] = small_label(glyphs, f"{n}/3", LABEL_YELLOW, PAGE_HEIGHT)
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
            hover: int = -1, tooltip: tuple[int, tuple[str, ...]] | None = None,
            pictures: dict[int, Image.Image] | None = None) -> Image.Image:
    """The tank screen's top 120 rows as ftfp_supply_slots.c draws page `page` (1-3), with
    supplies in every slot; hover = the arrow (0 upper, 1 lower) under the mouse."""
    art = read_game(game)
    screen = art["maintank1_bg_png.png"].crop((0, 0, 800, 120)).copy()
    screen.alpha_composite(art["ui_maintank_top_png.png"], (0, 0))
    pages = {1: TOOLS[0:4], 2: TOOLS[4:8], 3: TOOLS[8:9] + (TOOLS[3], TOOLS[5])}
    for p, tool in enumerate(pages[page]):
        picture = (pictures or {}).get(p, art[tool])
        screen.alpha_composite(picture, (PICTURE_X[p], PICTURE_Y))
    if page == 3:
        screen.alpha_composite(images["SupplySlotUnused.png"], BOXES[3][:2])
    x, y, w, h = ARROW
    for a, (name, ay) in enumerate((("SupplyArrowLeft.png", y), ("SupplyArrowRight.png", ARROW_RIGHT_Y))):
        frame = 2 if not owned else 1 if a == hover else 0
        screen.alpha_composite(images[name].crop((frame * w, 0, (frame + 1) * w, h)), (x, ay))
    if owned:
        label = images[f"SupplyPage{page}.png"]
        screen.alpha_composite(label, (PAGE_CENTRE_X - label.width // 2, PAGE_Y))
    if tooltip is not None:
        draw_tooltip(art, screen, *tooltip)
    return screen.resize((1600, 240), Image.NEAREST)


def hint_box(art: dict[str, Image.Image], screen: Image.Image, rect: tuple[int, int, int, int]) -> None:
    """The hint's box as 0x423280 draws it: the fill one pixel larger than the rectangle, then --
    only when the rectangle with its rope is at least as wide as the top bar and as tall as a side
    bar -- the four bars just outside it: the top one right to left and the bottom one left to right
    from corner to corner, the left one down from the rectangle's top, the right one up from its
    bottom, each step overlapping the last (the bar less a 2.5 x thickness)."""
    left, top, right, bottom = rect
    fill = Image.new("RGBA", (right - left + 2, bottom - top + 2), HINT_FILL)
    screen.alpha_composite(fill, (left - 1, top - 1))
    top_r, bottom_r, left_r, right_r = (art[r] for r in ROPES)
    tw, th, lw, lh = top_r.width, top_r.height, left_r.width, left_r.height
    ol, ot, orr, ob = left - lw, top - th, right + lw, bottom + th
    if ob - ot < lh or orr - ol < tw:
        return
    step_x, step_y = lw // 2 + 2 * lw, th // 2 + 2 * th
    x = orr - tw
    screen.alpha_composite(top_r, (x, ot))
    while x > ol:
        x = max(ol, x + step_x - tw)
        screen.alpha_composite(top_r, (x, ot))
    x = ol
    screen.alpha_composite(bottom_r, (x, bottom))
    while x < orr - tw:
        x = min(orr - tw, x + tw - step_x)
        screen.alpha_composite(bottom_r, (x, bottom))
    y = top
    screen.alpha_composite(left_r, (ol, y))
    while y < ob - lh:
        y = min(ob - lh, y + lh - step_y)
        screen.alpha_composite(left_r, (ol, y))
    y = bottom - lh
    screen.alpha_composite(right_r, (right, y))
    while y > ot:
        y = max(ot, y + step_y - lh)
        screen.alpha_composite(right_r, (right, y))


def draw_tooltip(art, screen: Image.Image, position: int, lines: tuple[str, ...]) -> None:
    """ftfp_ds_store.c slot_tooltip: the box centred under the slot, never smaller than its whole
    rope needs (rope_minimum: 44 x 54), clamped to the screen with room for the rope, the lines in
    its middle."""
    glyphs = tanks.font_glyphs(art["font_triplex_sanslightlin_bold_16pt.png"])
    texts = [small_label(glyphs, line, (255, 255, 255), 14) for line in lines]
    top_r, left_r = art[ROPES[0]], art[ROPES[2]]
    width = max(max(t.width for t in texts) + 2 * TIP["pad_x"], top_r.width - 2 * left_r.width)
    height = max(2 * TIP["pad_y"] + len(lines) * TIP["line"], left_r.height - top_r.height)
    left_box, _top, right_box, _bottom = BOXES[position]
    left = max(TIP["margin"], min(800 - TIP["margin"] - width, (left_box + right_box) // 2 - width // 2))
    rect = (left, TIP["top"], left + width, TIP["top"] + height)
    hint_box(art, screen, rect)
    y = TIP["top"] + (height - len(lines) * TIP["line"]) // 2
    for i, text in enumerate(texts):
        screen.alpha_composite(text, (left + (width - text.width) // 2, y + 3 + i * TIP["line"]))


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
    rgh = Image.open(ROOT / "assets" / "fish_tycoon_ds_store" / "Images" / "TOOL_RADIOACTIVE_GROWTHHORMONE.png").convert("RGBA")
    for name, page, position, lines, pictures in (
            ("hormone", 2, 1, ("Radioactive Growth Hormone", "2 doses left"), {1: rgh}),
            ("food", 1, 0, ("Fish Food",), None),
            ("eggs", 1, 3, ("Rare Fish Eggs", "1 batch left"), {3: read_game(game)["tool_fisheggs_rare.png"]})):
        path = PREVIEWS / f"supply-slot-tooltip-{name}.png"
        preview(game, images, page, tooltip=(position, lines), pictures=pictures).convert("RGB").save(path)
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
