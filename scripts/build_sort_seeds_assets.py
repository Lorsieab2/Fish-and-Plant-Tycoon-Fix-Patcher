"""Build the Sort Seeds button image from the vanilla Plant Tycoon folder.

    python scripts/build_sort_seeds_assets.py "<vanilla Plant Tycoon folder>"

* sort_seeds_button.png: "Sort Seeds" set in the game's own font
  (PTfontsmall.png and its glyph table in the executable) at the size of the
  store's "Upgrades" link, three frames side by side as the game's file
  buttons take them (the gold arrows are built the same way): normal white,
  hover yellow, pressed a darker yellow.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_plant_upgrades_assets as upgrades  # noqa: E402

OUT = ROOT / "assets" / "plant_tycoon_sort_seeds" / "Images"
TEXT = "Sort Seeds"
COLOURS = ((255, 255, 255), (255, 224, 96), (214, 178, 60))     # normal, hover, pressed


def button(folder: Path) -> Image.Image:
    table = upgrades.glyphs((folder / "Plant Tycoon.exe").read_bytes())
    font = Image.open(folder / "Images" / "PTfontsmall.png").convert("RGBA")
    rects = [table[ord(ch)] for ch in TEXT]
    word = Image.new("RGBA", (sum(r[2] - r[0] for r in rects), max(r[3] - r[1] for r in rects)))
    x = 0
    for x0, y0, x1, y1 in rects:
        word.alpha_composite(font.crop((x0, y0, x1, y1)), (x, 0))
        x += x1 - x0
    word = word.resize((round(word.width * upgrades.LINK_SCALE), round(word.height * upgrades.LINK_SCALE)),
                       Image.LANCZOS)
    sheet = Image.new("RGBA", (word.width * len(COLOURS), word.height))
    for frame, colour in enumerate(COLOURS):
        tinted = np.asarray(word).copy()
        tinted[..., :3] = (tinted[..., :3].astype(float) * np.array(colour) / 255).round().astype("uint8")
        sheet.paste(Image.fromarray(tinted, "RGBA"), (frame * word.width, 0))
    return sheet


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    OUT.mkdir(parents=True, exist_ok=True)
    image = button(Path(sys.argv[1]))
    image.save(OUT / "sort_seeds_button.png", optimize=True)
    print(f"sort_seeds_button.png {image.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
