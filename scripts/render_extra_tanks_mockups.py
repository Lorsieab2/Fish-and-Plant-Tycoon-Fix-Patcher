"""Mockups of Tank Three, Four and Five with selling Off and On, for the owner.

    python scripts/render_extra_tanks_mockups.py "<vanilla Fish Tycoon folder>"

Writes docs/images/extra-tank-<3|4|5>-selling-<off|on>.png from the game's own
art in Assets\\ft.dat and this setting's button art: the tank's background and
wood (Tank Three as Tank One, Tank Four as Tank Two, Tank Five as the Sale
Tank, as 0x41D140 / 0x41D340 draw them), the top bar on the extra tanks' page
with that tank current, and a proposed "For sale" toggle in the game's own
font. With selling On, the Sale Tank's sign (forsale.png, sprite 4, at
(620, 360)) and its shadow (TANK_OBJECT_SHADOW.png at (580, 415)) are drawn
where the Sale Tank has them. The toggle is a proposal: it is not built (see
docs/fish-tycoon-extra-tanks-design.md, "Selling from the extra tanks").
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_extra_tanks_assets as A  # noqa: E402

OUT = ROOT / "docs" / "images"
BACKGROUND = ("maintank1_bg_png.png", "maintank2_bg_png.png", "maintank3_bg_png.png")
WOOD = (                                          # 0x41D340: (file, x, y) per tank number
    (("wood0_png.png", 134, 241),),
    (("wood1_png.png", 22, 90), ("wood2_png.png", 563, 256)),
    (("wood3_png.png", 318, 283),),
)
SIGN = ("forsale.png", 620, 360)
SHADOW = ("tank_object_shadow.png", 580, 415)
TOGGLE_AT = (16, 66)


def art(game: Path) -> dict[str, Image.Image]:
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist() if not n.startswith("__MACOSX")}
        wanted = BACKGROUND + tuple(w[0] for ws in WOOD for w in ws) + (SIGN[0], SHADOW[0], "ui_maintank_top_png.png",
                                                                         "font_triplex_sanslightlin_bold_16pt.png")
        return {w: Image.open(io.BytesIO(archive.read(names[w]))).convert("RGBA") for w in wanted}


def toggle(glyphs, on: bool) -> Image.Image:
    text = A.label(f"For sale: {'On' if on else 'Off'}", glyphs, 0.9)
    plate = Image.new("RGBA", (text.width + 20, text.height + 12), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=8,
                                            fill=(40, 70, 40, 220) if on else (60, 40, 30, 220),
                                            outline=(230, 220, 190, 255), width=2)
    plate.alpha_composite(text, (10, 6))
    return plate


def render(game: Path, images: dict[str, Image.Image], extra: int, on: bool) -> Image.Image:
    a = art(game)
    glyphs = A.font_glyphs(a["font_triplex_sanslightlin_bold_16pt.png"])
    screen = a[BACKGROUND[extra]].copy()
    for name, x, y in WOOD[extra]:
        screen.alpha_composite(a[name], (x, y))
    if on:
        screen.alpha_composite(a[SHADOW[0]], SHADOW[1:])
        screen.alpha_composite(a[SIGN[0]], SIGN[1:])
    screen.alpha_composite(a["ui_maintank_top_png.png"], (0, 0))
    x, y, w, h = A.ARROW_BOX
    screen.alpha_composite(images["TankArrowLeft.png"].crop((0, 0, w, h)), (x, y))
    screen.alpha_composite(images["TankArrowRight.png"].crop((0, 0, w, h)), (x, A.ARROW_RIGHT_Y))
    for b, (left, top, _r, _b) in enumerate(A.BUTTONS):
        frame = 2 if b == extra else 0
        sheet = images[f"ExtraTank{b + 1}Button.png"]
        screen.alpha_composite(sheet.crop((frame * A.FRAME_W, 0, (frame + 1) * A.FRAME_W, A.FRAME_H)), (left, top))
    screen.alpha_composite(toggle(glyphs, on), TOGGLE_AT)
    return screen


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    game = Path(sys.argv[1])
    images = {p.name: Image.open(p).convert("RGBA")
              for p in (ROOT / "assets" / "fish_tycoon_extra_tanks" / "Images").glob("*.png")}
    OUT.mkdir(parents=True, exist_ok=True)
    for extra in range(3):
        for on in (False, True):
            path = OUT / f"extra-tank-{extra + 3}-selling-{'on' if on else 'off'}.png"
            render(game, images, extra, on).convert("RGB").save(path)
            print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
