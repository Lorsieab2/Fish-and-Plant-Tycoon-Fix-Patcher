"""Build the Optimize Prices buttons and their previews from the vanilla games.

    python scripts/build_optimize_prices_assets.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>"

* assets/fish_tycoon_optimize_prices/Images/OptimizePricesButton.png: a text
  button, "Optimize Prices" lettered on the Species Chart's own bottom bar
  (species_bg.bmp at the button's place, left of Done) in the stock lettering:
  white with a dark rim like Done's, gold on hover, pressed 1 px down; a
  3-frame strip like the stock buttons (DS Store Items' Upgrades button is
  built the same way).
* assets/plant_tycoon_optimize_prices/Images/optimize_prices_button.png: the
  game's own wide purple button (widePTButton.png: normal, hover, pressed)
  with "Optimize Prices" set in the game's own font (PTfontsmall.png and its
  glyph table in the executable), white, yellow on hover, as Sort Seeds'.
* docs/images/optimize-prices-fish.png and optimize-prices-plant.png: each
  button where the DLL puts it (native/ftfp_fish_prices, native/ftfp_plant_prices).
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_plant_upgrades_assets as upgrades  # noqa: E402

TEXT = "Optimize Prices"
FISH_OUT = ROOT / "assets" / "fish_tycoon_optimize_prices" / "Images" / "OptimizePricesButton.png"
PLANT_OUT = ROOT / "assets" / "plant_tycoon_optimize_prices" / "Images" / "optimize_prices_button.png"
PREVIEWS = ROOT / "docs" / "images"

# Where the DLLs put the buttons (BUTTON_X / BUTTON_Y in their sources).
FISH_POS, FISH_SIZE = (524, 546), (160, 53)          # left of Done (690, 546), as tall as it
DONE_POS, DONE_SIZE = (690, 546), (83, 53)
PLANT_POS = (620, 561)                               # the brick strip of the Nursery's bottom bar
NURSERY_UI_Y = 600 - 116
PLANT_TEXT_COLOURS = ((255, 255, 255), (255, 224, 96), (214, 178, 60))     # normal, hover, pressed


def fish_button(background: Image.Image) -> Image.Image:
    bg = background.convert("RGB")
    bg = bg.crop((0, 0, bg.width, bg.height + 1))            # the stock buttons run one row past the screen
    x0, y0 = FISH_POS
    w, h = FISH_SIZE
    bar = bg.crop((x0, y0, x0 + w, y0 + h))
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 17)
    strip = Image.new("RGB", (w * 3, h))
    for f, (colour, drop) in enumerate((((255, 255, 255), 0), ((255, 222, 110), 0), ((225, 205, 160), 1))):
        frame = bar.copy()
        draw = ImageDraw.Draw(frame)
        box = draw.textbbox((0, 0), TEXT, font=font)
        x = (w - (box[2] - box[0])) // 2 - box[0]
        y = (h - (box[3] - box[1])) // 2 - box[1] + drop
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                if abs(dx) + abs(dy) <= 3:
                    draw.text((x + dx, y + dy), TEXT, font=font, fill=(12, 34, 44))
        draw.text((x, y), TEXT, font=font, fill=colour)
        strip.paste(frame, (f * w, 0))
    return strip


def plant_word(folder: Path) -> Image.Image:
    table = upgrades.glyphs((folder / "Plant Tycoon.exe").read_bytes())
    font = Image.open(folder / "Images" / "PTfontsmall.png").convert("RGBA")
    rects = [table[ord(ch)] for ch in TEXT]
    word = Image.new("RGBA", (sum(r[2] - r[0] for r in rects), max(r[3] - r[1] for r in rects)))
    x = 0
    for x0, y0, x1, y1 in rects:
        word.alpha_composite(font.crop((x0, y0, x1, y1)), (x, 0))
        x += x1 - x0
    return word


def plant_button(folder: Path) -> Image.Image:
    base = Image.open(folder / "Images" / "widePTButton.png").convert("RGBA")
    fw, fh = base.width // 3, base.height
    word = plant_word(folder)
    scale = min(upgrades.LINK_SCALE, (fw - 18) / word.width, (fh - 10) / word.height)
    word = word.resize((round(word.width * scale), round(word.height * scale)), Image.LANCZOS)
    sheet = base.copy()
    for frame, colour in enumerate(PLANT_TEXT_COLOURS):
        tinted = np.asarray(word).copy()
        tinted[..., :3] = (tinted[..., :3].astype(float) * np.array(colour) / 255).round().astype("uint8")
        x = frame * fw + (fw - word.width) // 2
        y = (fh - word.height) // 2 + (1 if frame == 2 else 0)
        sheet.alpha_composite(Image.fromarray(tinted, "RGBA"), (x, y))
    return sheet


def fish_preview(background: Image.Image, done: Image.Image, button: Image.Image) -> Image.Image:
    screen = background.convert("RGBA")
    screen.alpha_composite(done.convert("RGBA").crop((0, 0) + DONE_SIZE), DONE_POS)
    screen.alpha_composite(button.convert("RGBA").crop((0, 0) + FISH_SIZE), FISH_POS)
    return screen.crop((0, 0, 800, 600))


def plant_preview(folder: Path, button: Image.Image) -> Image.Image:
    images = folder / "Images"
    screen = Image.open(images / "Nursery_BG.jpg").convert("RGBA")
    screen.alpha_composite(Image.open(images / "nurseryUI.png").convert("RGBA"), (0, NURSERY_UI_Y))
    fw = button.width // 3
    screen.alpha_composite(button.crop((0, 0, fw, button.height)), PLANT_POS)
    return screen.crop((340, 400, 800, 600))                 # the bar's right half, where the button is


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    fish, plant = Path(sys.argv[1]), Path(sys.argv[2])
    with zipfile.ZipFile(fish / "Assets" / "ft.dat") as archive:
        background = Image.open(io.BytesIO(archive.read("species_bg.bmp")))
        background.load()
        done = Image.open(io.BytesIO(archive.read("speciesdonebutton.png")))
        done.load()
    FISH_OUT.parent.mkdir(parents=True, exist_ok=True)
    PLANT_OUT.parent.mkdir(parents=True, exist_ok=True)
    fbutton = fish_button(background)
    fbutton.save(FISH_OUT, optimize=True)
    pbutton = plant_button(plant)
    pbutton.save(PLANT_OUT, optimize=True)
    fish_preview(background, done, fbutton).convert("RGB").save(PREVIEWS / "optimize-prices-fish.png", optimize=True)
    plant_preview(plant, pbutton).convert("RGB").save(PREVIEWS / "optimize-prices-plant.png", optimize=True)
    print(f"{FISH_OUT.name} {fbutton.size}; {PLANT_OUT.name} {pbutton.size}; two previews in docs/images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
