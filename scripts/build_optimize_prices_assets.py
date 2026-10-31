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
* assets/fish_tycoon_optimize_prices/Images/OptimizePricesStoreButton.png:
  the same button for the Fish Store screen (the sale scene, opened with Sell
  Fish), lettered on that screen's own bottom bar (sellfishshop_bg_png.png at
  544-693 x 547-596, between "Your cash" and Done) in the game's own font
  (paddington_tt_18.png and its glyph table in the executable): white with a
  dark rim, gold on hover, pressed 1 px down.
* MaxPricesButton.png, MaxPricesStoreButton.png (Fish Tycoon) and
  max_prices_button.png (Plant Tycoon): the "Max Prices" buttons, made the
  same way, each lettered on its own bar's art where it sits, left of
  Optimize Prices (Plant: the same wide purple button, the lettering at
  Optimize Prices' scale).
* docs/images/optimize-prices-fish.png and optimize-prices-plant.png: both
  buttons where the DLL puts them (native/ftfp_fish_prices, native/ftfp_plant_prices);
  docs/images/optimize-prices-fish-store.png: the Fish Store screen with both
  buttons and Done, and sample "Fish for sale", "Price" and "Your cash" texts
  where the game writes them.
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

import build_counts_previews as counts  # noqa: E402
import build_plant_upgrades_assets as upgrades  # noqa: E402

TEXT = "Optimize Prices"
FISH_OUT = ROOT / "assets" / "fish_tycoon_optimize_prices" / "Images" / "OptimizePricesButton.png"
STORE_OUT = ROOT / "assets" / "fish_tycoon_optimize_prices" / "Images" / "OptimizePricesStoreButton.png"

# The Fish Store screen (native/ftfp_fish_prices: SALE_BUTTON_X / _Y; Done, 0x424588).
STORE_POS, STORE_SIZE = (544, 547), (150, 50)        # the bar between "Your cash" (to 300) and Done
STORE_DONE = (701, 547)
STORE_RIM = (10, 38, 12)                              # a dark rim on this green bar
# Sample texts where the sale scene writes them (0x4238E3, 0x423917, 0x42398E / 0x4239CC).
STORE_TEXTS = (("Your cash: $1,234", (41, 559)), ("Fish for sale: 4", (229, 414)),
               ("Price:", (229, 480)), ("$35", (304, 480)))
PLANT_OUT = ROOT / "assets" / "plant_tycoon_optimize_prices" / "Images" / "optimize_prices_button.png"
PREVIEWS = ROOT / "docs" / "images"

# Where the DLLs put the buttons (BUTTON_X / BUTTON_Y in their sources).
FISH_POS, FISH_SIZE = (524, 546), (160, 53)          # left of Done (690, 546), as tall as it
DONE_POS, DONE_SIZE = (690, 546), (83, 53)
PLANT_POS = (620, 561)                               # the brick strip of the Nursery's bottom bar
NURSERY_UI_Y = 600 - 116
PLANT_TEXT_COLOURS = ((255, 255, 255), (255, 224, 96), (214, 178, 60))     # normal, hover, pressed

# The Max Prices buttons, left of each Optimize Prices button (MAX_BUTTON_X / _Y in the DLL sources).
MAX_TEXT = "Max Prices"
FISH_MAX_OUT = FISH_OUT.parent / "MaxPricesButton.png"
STORE_MAX_OUT = FISH_OUT.parent / "MaxPricesStoreButton.png"
PLANT_MAX_OUT = PLANT_OUT.parent / "max_prices_button.png"
FISH_MAX_POS, FISH_MAX_SIZE = (400, 546), (120, 53)     # the chart's bar, 4 px left of Optimize Prices
STORE_MAX_POS, STORE_MAX_SIZE = (420, 547), (120, 50)   # the Fish Store's bar, right of "Your cash"
PLANT_MAX_POS = (449, 561)                              # the brick strip, 8 px left of Optimize Prices


def fish_button(background: Image.Image, text: str = TEXT, pos=FISH_POS, size=FISH_SIZE) -> Image.Image:
    bg = background.convert("RGB")
    bg = bg.crop((0, 0, bg.width, bg.height + 1))            # the stock buttons run one row past the screen
    x0, y0 = pos
    w, h = size
    bar = bg.crop((x0, y0, x0 + w, y0 + h))
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 17)
    strip = Image.new("RGB", (w * 3, h))
    for f, (colour, drop) in enumerate((((255, 255, 255), 0), ((255, 222, 110), 0), ((225, 205, 160), 1))):
        frame = bar.copy()
        draw = ImageDraw.Draw(frame)
        box = draw.textbbox((0, 0), text, font=font)
        x = (w - (box[2] - box[0])) // 2 - box[0]
        y = (h - (box[3] - box[1])) // 2 - box[1] + drop
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                if abs(dx) + abs(dy) <= 3:
                    draw.text((x + dx, y + dy), text, font=font, fill=(12, 34, 44))
        draw.text((x, y), text, font=font, fill=colour)
        strip.paste(frame, (f * w, 0))
    return strip


def store_button(background: Image.Image, sheet: Image.Image, table: dict, text: str = TEXT,
                 pos=STORE_POS, size=STORE_SIZE) -> Image.Image:
    """The Fish Store's button: `text` set glyph by glyph in paddington_tt_18 on the bar, a 3-frame strip."""
    bg = background.convert("RGBA")
    bg = bg.crop((0, 0, bg.width, bg.height + 1))            # the stock buttons run one row past the screen
    x0, y0 = pos
    w, h = size
    bar = bg.crop((x0, y0, x0 + w, y0 + h))
    rim = counts.set_text(sheet, table, text, STORE_RIM)
    strip = Image.new("RGBA", (w * 3, h))
    for f, (colour, drop) in enumerate((((255, 255, 255), 0), ((255, 222, 110), 0), ((225, 205, 160), 1))):
        frame = bar.copy()
        word = counts.set_text(sheet, table, text, colour)
        x = (w - word.width) // 2
        y = (h - word.height) // 2 + drop
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                if abs(dx) + abs(dy) <= 3:
                    frame.alpha_composite(rim, (x + dx, y + dy))
        frame.alpha_composite(word, (x, y))
        strip.paste(frame, (f * w, 0))
    return strip.convert("RGB")


def store_preview(background: Image.Image, done: Image.Image, button: Image.Image, sheet: Image.Image,
                  table: dict, max_button: Image.Image) -> Image.Image:
    """The Fish Store screen: the stock Done, both buttons, and sample texts where the game writes them."""
    screen = background.convert("RGBA")
    screen = screen.crop((0, 0, 800, 601))
    screen.alpha_composite(done.convert("RGBA").crop((0, 0, done.width // 3, done.height)), STORE_DONE)
    screen.alpha_composite(button.convert("RGBA").crop((0, 0) + STORE_SIZE), STORE_POS)
    screen.alpha_composite(max_button.convert("RGBA").crop((0, 0) + STORE_MAX_SIZE), STORE_MAX_POS)
    for text, at in STORE_TEXTS:
        counts.draw(screen, sheet, table, text, at)
    return screen.crop((0, 0, 800, 600))


def plant_word(folder: Path, text: str = TEXT) -> Image.Image:
    table = upgrades.glyphs((folder / "Plant Tycoon.exe").read_bytes())
    font = Image.open(folder / "Images" / "PTfontsmall.png").convert("RGBA")
    rects = [table[ord(ch)] for ch in text]
    word = Image.new("RGBA", (sum(r[2] - r[0] for r in rects), max(r[3] - r[1] for r in rects)))
    x = 0
    for x0, y0, x1, y1 in rects:
        word.alpha_composite(font.crop((x0, y0, x1, y1)), (x, 0))
        x += x1 - x0
    return word


def plant_scale(folder: Path) -> float:
    """The lettering's scale on the wide button: Optimize Prices' own, which Max Prices shares."""
    base = Image.open(folder / "Images" / "widePTButton.png")
    fw, fh = base.width // 3, base.height
    word = plant_word(folder)
    return min(upgrades.LINK_SCALE, (fw - 18) / word.width, (fh - 10) / word.height)


def plant_button(folder: Path, text: str = TEXT) -> Image.Image:
    base = Image.open(folder / "Images" / "widePTButton.png").convert("RGBA")
    fw, fh = base.width // 3, base.height
    word = plant_word(folder, text)
    scale = plant_scale(folder)
    word = word.resize((round(word.width * scale), round(word.height * scale)), Image.LANCZOS)
    sheet = base.copy()
    for frame, colour in enumerate(PLANT_TEXT_COLOURS):
        tinted = np.asarray(word).copy()
        tinted[..., :3] = (tinted[..., :3].astype(float) * np.array(colour) / 255).round().astype("uint8")
        x = frame * fw + (fw - word.width) // 2
        y = (fh - word.height) // 2 + (1 if frame == 2 else 0)
        sheet.alpha_composite(Image.fromarray(tinted, "RGBA"), (x, y))
    return sheet


def fish_preview(background: Image.Image, done: Image.Image, button: Image.Image, max_button: Image.Image) -> Image.Image:
    screen = background.convert("RGBA")
    screen.alpha_composite(done.convert("RGBA").crop((0, 0) + DONE_SIZE), DONE_POS)
    screen.alpha_composite(button.convert("RGBA").crop((0, 0) + FISH_SIZE), FISH_POS)
    screen.alpha_composite(max_button.convert("RGBA").crop((0, 0) + FISH_MAX_SIZE), FISH_MAX_POS)
    return screen.crop((0, 0, 800, 600))


def plant_preview(folder: Path, button: Image.Image, max_button: Image.Image) -> Image.Image:
    images = folder / "Images"
    screen = Image.open(images / "Nursery_BG.jpg").convert("RGBA")
    screen.alpha_composite(Image.open(images / "nurseryUI.png").convert("RGBA"), (0, NURSERY_UI_Y))
    fw = button.width // 3
    screen.alpha_composite(button.crop((0, 0, fw, button.height)), PLANT_POS)
    screen.alpha_composite(max_button.crop((0, 0, max_button.width // 3, max_button.height)), PLANT_MAX_POS)
    return screen.crop((340, 400, 800, 600))                 # the bar's right half, where the buttons are


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    fish, plant = Path(sys.argv[1]), Path(sys.argv[2])
    with zipfile.ZipFile(fish / "Assets" / "ft.dat") as archive:
        background = Image.open(io.BytesIO(archive.read("species_bg.bmp")))
        background.load()
        done = Image.open(io.BytesIO(archive.read("speciesdonebutton.png")))
        done.load()
        store = {name: Image.open(io.BytesIO(archive.read(name))) for name in (
            "sellfishshop_bg_png.png", "selldonebutton.png", "paddington_tt_18.png")}
        for image in store.values():
            image.load()
    glyphs = counts.glyph_table((fish / "Fish Tycoon.exe").read_bytes(), counts.FISH_GLYPHS)
    font = store["paddington_tt_18.png"].convert("RGBA")
    sbutton = store_button(store["sellfishshop_bg_png.png"], font, glyphs)
    sbutton.save(STORE_OUT, optimize=True)
    smax = store_button(store["sellfishshop_bg_png.png"], font, glyphs, MAX_TEXT, STORE_MAX_POS, STORE_MAX_SIZE)
    smax.save(STORE_MAX_OUT, optimize=True)
    store_preview(store["sellfishshop_bg_png.png"], store["selldonebutton.png"], sbutton, font,
                  glyphs, smax).convert("RGB").save(PREVIEWS / "optimize-prices-fish-store.png", optimize=True)
    FISH_OUT.parent.mkdir(parents=True, exist_ok=True)
    PLANT_OUT.parent.mkdir(parents=True, exist_ok=True)
    fbutton = fish_button(background)
    fbutton.save(FISH_OUT, optimize=True)
    fmax = fish_button(background, MAX_TEXT, FISH_MAX_POS, FISH_MAX_SIZE)
    fmax.save(FISH_MAX_OUT, optimize=True)
    pbutton = plant_button(plant)
    pbutton.save(PLANT_OUT, optimize=True)
    pmax = plant_button(plant, MAX_TEXT)
    pmax.save(PLANT_MAX_OUT, optimize=True)
    fish_preview(background, done, fbutton, fmax).convert("RGB").save(PREVIEWS / "optimize-prices-fish.png",
                                                                      optimize=True)
    plant_preview(plant, pbutton, pmax).convert("RGB").save(PREVIEWS / "optimize-prices-plant.png", optimize=True)
    print(f"{FISH_OUT.name} {fbutton.size}; {FISH_MAX_OUT.name} {fmax.size}; {STORE_MAX_OUT.name} {smax.size}; "
          f"{PLANT_OUT.name} {pbutton.size}; {PLANT_MAX_OUT.name} {pmax.size}; three previews in docs/images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
