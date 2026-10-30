"""Build the "3 extra tanks" art from the game's own tank-button art.

    python scripts/build_extra_tanks_assets.py "<vanilla Fish Tycoon folder>"

Everything is made from the game's own pictures in Assets\\ft.dat; nothing is
drawn from scratch (owner: reuse the stock tanks' art):

* ExtraTank1Button.png .. ExtraTank3Button.png (261 x 53, 3 frames of 87 x 53,
  the layout of Tank1Button.png): the stock button art at the same place with
  its label replaced by "Tank Three", "Tank Four" or "Tank Five", written in
  the game's own font (font_triplex_sanslightlin_bold_16pt.png) with the stock
  labels' dark outline. Frame 0 is the top bar as it looks there (the stock
  frame 0 is empty because the bar shows through), frame 1 the hover look
  (the stock frame 1), frame 2 the current tank (the stock frame 2, smaller
  label).
* Tank1ButtonNormal.png (87 x 53): the top bar under the Tank One button,
  drawn while an extra tank is on screen so Tank One does not look current.
* TankArrowRight.png / TankArrowLeft.png (2 frames each, normal and hover):
  the game's UP_ARROW.png turned on its side and scaled to fit the strip of
  bar between the Magic Breeds silhouettes and the Tank One button.

Also writes docs/images/extra-tanks-*.png, the tank screen's top with each
page of buttons, to show what the screen looks like.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "fish_tycoon_extra_tanks" / "Images"
PREVIEWS = ROOT / "docs" / "images"

# The stock buttons' rects (0x41CDD4: impl+0x58/0x68/0x78, left, top, right, bottom).
BUTTONS = ((513, 2, 598, 54), (610, 2, 695, 54), (707, 2, 792, 54))
FRAME_W, FRAME_H = 87, 53
LABELS = ("Tank Three", "Tank Four", "Tank Five")
STOCK_STRIPS = ("tank1button.png", "tank2button.png", "selltankbutton.png")
# The arrow, in the bar between the last Magic Breeds silhouette (x <= 495) and Tank One (x >= 513).
ARROW_BOX = (495, 20, 18, 15)           # x, y, w, h: ftfp_extra_tanks.c ARROW_X/Y/W/H
OUTLINE = (24, 24, 40)


def read_game(game: Path) -> dict[str, Image.Image]:
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist() if not n.startswith("__MACOSX")}
        wanted = ("ui_maintank_top_png.png", "up_arrow.png", "font_triplex_sanslightlin_bold_16pt.png",
                  "maintank1_bg_png.png") + STOCK_STRIPS
        return {w: Image.open(io.BytesIO(archive.read(names[w]))).convert("RGBA") for w in wanted}


# ------------------------------------------------------------------ the font

def font_glyphs(sheet: Image.Image) -> dict[str, Image.Image]:
    """The game's bitmap font: three bands of 24 rows, ASCII 32-126 in order. A glyph's cell is
    a run of columns marked white-with-zero-alpha on the band's first row."""
    px = np.array(sheet)
    glyphs: dict[str, Image.Image] = {}
    code = 32
    for band in range(3):
        y0 = band * 24
        marker = (px[y0, :, 3] == 0) & (px[y0, :, :3].sum(axis=1) == 765)
        x = 0
        while x < sheet.width and code <= 126:
            if not marker[x]:
                x += 1
                continue
            start = x
            while x < sheet.width and marker[x]:
                x += 1
            cell = sheet.crop((start, y0, x, y0 + 24))
            glyphs[chr(code)] = cell
            code += 1
    if len(glyphs) != 95:
        raise SystemExit(f"font sheet: {len(glyphs)} glyphs, expected 95")
    return glyphs


def label(text: str, glyphs: dict[str, Image.Image], scale: float) -> Image.Image:
    """White text in the game's font with a 1-pixel dark outline, like the stock labels."""
    width = sum(glyphs[c].width for c in text)
    canvas = Image.new("RGBA", (width + 4, 24 + 4), (0, 0, 0, 0))
    x = 2
    for c in text:
        g = glyphs[c]
        alpha = np.array(g)[:, :, 3]
        white = Image.new("RGBA", g.size, (255, 255, 255, 255))
        white.putalpha(Image.fromarray(alpha))
        canvas.alpha_composite(white, (x, 2))
        x += g.width
    if scale != 1.0:
        size = (max(1, round(canvas.width * scale)), max(1, round(canvas.height * scale)))
        canvas = canvas.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")
    a = np.array(canvas)[:, :, 3].astype(float) / 255
    ring = np.zeros_like(a)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ring = np.maximum(ring, np.roll(np.roll(a, dy, 0), dx, 1))
    out = np.zeros(a.shape + (4,), dtype=float)
    out[:, :, :3] = np.array(OUTLINE, dtype=float)
    out[:, :, 3] = ring
    white = a[:, :, None]
    out[:, :, :3] = out[:, :, :3] * (1 - white) + 255 * white
    out[:, :, 3] = np.maximum(ring, a) * 255
    trimmed = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
    return trimmed.crop(trimmed.getbbox())


# ------------------------------------------------------------- erase a label

def erase_label(image: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """The stock label taken out: its white letters and their outline are filled from the
    surrounding art by repeated averaging (a diffusion fill). Returns the art and the
    label's box, so the new label goes where the old one was."""
    px = np.array(image.convert("RGB")).astype(float)
    h, w = px.shape[:2]
    white = px.min(axis=2) > 215          # the labels are pure white; the shells never reach it there
    white[:16, :] = False                 # the labels sit in rows 20-35 of every frame
    white[41:, :] = False
    ys, xs = np.nonzero(white)
    box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    mask = white.copy()
    for _ in range(2):
        grown = mask.copy()
        grown[1:, :] |= mask[:-1, :]
        grown[:-1, :] |= mask[1:, :]
        grown[:, 1:] |= mask[:, :-1]
        grown[:, :-1] |= mask[:, 1:]
        mask = grown
    known = ~mask
    fill = px.copy()
    fill[mask] = 0
    weight = known.astype(float)
    for _ in range(400):
        acc = np.zeros_like(fill)
        cnt = np.zeros((h, w))
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            acc += np.roll(np.roll(fill * weight[:, :, None], dy, 0), dx, 1)
            cnt += np.roll(np.roll(weight, dy, 0), dx, 1)
        update = mask & (cnt > 0)
        fill[update] = acc[update] / cnt[update][:, None]
        weight = np.where(update, 1.0, weight)
    out = Image.fromarray(np.clip(fill, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    return out, box


def relabel(image: Image.Image, text: str, glyphs: dict[str, Image.Image], scale: float) -> Image.Image:
    art, box = erase_label(image)
    word = label(text, glyphs, scale)
    room = FRAME_W - 2
    if word.width > room:                 # "Tank Three" is wider than "Tank One"
        word = word.convert("RGBa").resize((room, max(1, round(word.height * room / word.width))),
                                           Image.LANCZOS).convert("RGBA")
    cx = (box[0] + box[2]) / 2
    bottom = box[3] + 1
    x = int(round(cx - word.width / 2))
    x = max(1, min(FRAME_W - 1 - word.width, x))
    art.alpha_composite(word, (x, bottom - word.height + 1))
    return art


# ------------------------------------------------------------------ build

def build(game: Path) -> dict[str, Image.Image]:
    art = read_game(game)
    glyphs = font_glyphs(art["font_triplex_sanslightlin_bold_16pt.png"])
    bar = art["ui_maintank_top_png.png"]
    out: dict[str, Image.Image] = {}
    for i, (text, strip_name) in enumerate(zip(LABELS, STOCK_STRIPS)):
        left, top = BUTTONS[i][0], BUTTONS[i][1]
        strip = art[strip_name]
        normal = bar.crop((left, top, left + FRAME_W, top + FRAME_H))
        frames = (relabel(normal, text, glyphs, 1.0),
                  relabel(strip.crop((FRAME_W, 0, 2 * FRAME_W, FRAME_H)), text, glyphs, 1.0),
                  relabel(strip.crop((2 * FRAME_W, 0, 3 * FRAME_W, FRAME_H)), text, glyphs, 0.82))
        sheet = Image.new("RGBA", (3 * FRAME_W, FRAME_H))
        for f, frame in enumerate(frames):
            sheet.paste(frame, (f * FRAME_W, 0))
        out[f"ExtraTank{i + 1}Button.png"] = sheet
    left, top = BUTTONS[0][0], BUTTONS[0][1]
    out["Tank1ButtonNormal.png"] = bar.crop((left, top, left + FRAME_W, top + FRAME_H))
    x, y, w, h = ARROW_BOX
    right = art["up_arrow.png"].rotate(-90, expand=True)
    right = right.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
    hover = np.array(right).astype(float)
    hover[:, :, :3] = np.minimum(255, hover[:, :, :3] * 1.35 + 30)
    hover_img = Image.fromarray(hover.astype(np.uint8), "RGBA")
    for name, normal_img, lit in (("TankArrowRight.png", right, hover_img),
                                  ("TankArrowLeft.png", right.transpose(Image.FLIP_LEFT_RIGHT),
                                   hover_img.transpose(Image.FLIP_LEFT_RIGHT))):
        sheet = Image.new("RGBA", (2 * w, h), (0, 0, 0, 0))
        sheet.paste(normal_img, (0, 0))
        sheet.paste(lit, (w, 0))
        out[name] = sheet
    return out


def preview(game: Path, images: dict[str, Image.Image], page: int, current: int, hover: int) -> Image.Image:
    """The tank screen's top 120 rows as ftfp_extra_tanks.c draws them: page 0 or 1, the current
    button (frame 2) and a hovered one (frame 1)."""
    art = read_game(game)
    screen = art["maintank1_bg_png.png"].crop((0, 0, 800, 120)).copy()
    screen.alpha_composite(art["ui_maintank_top_png.png"], (0, 0))
    x, y, w, h = ARROW_BOX
    arrow = images["TankArrowRight.png" if page == 0 else "TankArrowLeft.png"]
    screen.alpha_composite(arrow.crop((0, 0, w, h)), (x, y))
    for b, (left, top, _r, _b) in enumerate(BUTTONS):
        if page == 1:
            sheet = images[f"ExtraTank{b + 1}Button.png"]
        else:
            sheet = art[STOCK_STRIPS[b]]
        frame = 2 if b == current else 1 if b == hover else 0
        if page == 0 and frame == 0:
            continue
        screen.alpha_composite(sheet.crop((frame * FRAME_W, 0, (frame + 1) * FRAME_W, FRAME_H)), (left, top))
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
    preview(game, images, 0, 0, -1).convert("RGB").save(PREVIEWS / "extra-tanks-stock-page.png")
    preview(game, images, 1, 0, 2).convert("RGB").save(PREVIEWS / "extra-tanks-extra-page.png")
    print(f"previews in {PREVIEWS.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
