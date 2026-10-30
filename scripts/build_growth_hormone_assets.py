"""Build the Radioactive Growth Hormone's art: the stock Growth Hormone, recoloured green.

    python scripts/build_growth_hormone_assets.py "<vanilla Fish Tycoon folder>"

The sources are the game's own pictures in Assets/ft.dat:

* item_growthhormone.png (48 x 65), the store picture;
* tool_growthhormone.png (24 x 35), the bottle on the supply shelf (sprite 0x7A);
* tool_dropper4.png (21 x 21), the Growth Hormone's dropper, the cursor while you use it (sprite 0x7B).

Each pixel's hue is turned from the stock violet-blue (0.667) to a radioactive green (HUE_TO), and
its saturation raised a little (SATURATION); brightness and alpha are kept, so the bottle keeps
its shading, highlights and glass. It writes

* assets/fish_tycoon_ds_store/Images/ITEM_RADIOACTIVE_GROWTHHORMONE.png,
  TOOL_RADIOACTIVE_GROWTHHORMONE.png and TOOL_dropper_RADIOACTIVE.png, at the stock sizes;
* docs/images/radioactive-growth-hormone-fish.png: the Upgrades page with every item in its
  net cell (ftfp_ds_store.c's ITEM table), and the stock and green art side by side, 3x.

tests/test_radioactive_growth_hormone.py rebuilds the three pictures and compares their pixels
with the committed ones.
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
OUT = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
PREVIEW = ROOT / "docs" / "images" / "radioactive-growth-hormone-fish.png"

HUE_FROM = 2 / 3            # the stock liquid (measured: 0.664-0.667)
HUE_TO = 0.30               # a radioactive yellow-green
SATURATION = 1.25

# stock picture in ft.dat -> the green one's file name
ART = {
    "item_growthhormone.png": "ITEM_RADIOACTIVE_GROWTHHORMONE.png",
    "tool_growthhormone.png": "TOOL_RADIOACTIVE_GROWTHHORMONE.png",
    "tool_dropper4.png": "TOOL_dropper_RADIOACTIVE.png",
}

# The Upgrades page's net cells (x, y, w, h), as in ftfp_ds_store.c's ITEM table.
CELLS = (("ITEM_DS_PUFFER.png", 44, 83, 85, 70), ("ITEM_DS_STINGRAY.png", 141, 87, 73, 71),
         ("ITEM_DS_EEL.png", 234, 93, 71, 71), ("ITEM_FISHEGGS_EXOTIC.png", 320, 98, 77, 69),
         ("ITEM_TIME_WARP.png", 411, 100, 79, 66), ("ITEM_ADD_MONEY.png", 503, 100, 79, 66),
         ("ITEM_RADIOACTIVE_GROWTHHORMONE.png", 595, 90, 79, 72))


def green(image: Image.Image) -> Image.Image:
    """The hue turned by HUE_TO - HUE_FROM, saturation x SATURATION; value and alpha kept."""
    rgba = np.asarray(image.convert("RGBA")).astype(float) / 255
    out = rgba.copy()
    for y in range(rgba.shape[0]):
        for x in range(rgba.shape[1]):
            h, s, v = colorsys.rgb_to_hsv(*rgba[y, x, :3])
            out[y, x, :3] = colorsys.hsv_to_rgb((h + HUE_TO - HUE_FROM) % 1.0, min(1.0, s * SATURATION), v)
    return Image.fromarray((out * 255).round().astype("uint8"), "RGBA")


def stock_images(game: Path) -> dict[str, Image.Image]:
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist()}
        wanted = list(ART) + ["supplyshop_bg_out.bmp"]
        return {name: Image.open(io.BytesIO(archive.read(names[name]))).convert("RGBA") for name in wanted}


def build(game: Path) -> dict[str, Image.Image]:
    """The green pictures, by output file name."""
    stock = stock_images(game)
    return {out: green(stock[name]) for name, out in ART.items()}


def preview(game: Path, built: dict[str, Image.Image]) -> Image.Image:
    stock = stock_images(game)
    screen = stock["supplyshop_bg_out.bmp"].copy()
    for name, x, y, w, h in CELLS:
        art = built[name] if name in built else Image.open(OUT / name).convert("RGBA")
        screen.alpha_composite(art, (x + (w - art.width) // 2, y + (h - art.height) // 2))
    # On the description panel: each stock picture and its green one, side by side, 2x.
    x = 62
    for name, out in ART.items():
        for art in (stock[name], built[out]):
            big = art.resize((art.width * 2, art.height * 2), Image.NEAREST)
            screen.alpha_composite(big, (x, 348))
            x += big.width + 6
        x += 24
    return screen


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    game = Path(sys.argv[1])
    built = build(game)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, image in built.items():
        image.save(OUT / name)
        print(f"{(OUT / name).relative_to(ROOT).as_posix()}: {image.width} x {image.height}")
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    preview(game, built).convert("RGB").save(PREVIEW)
    print(f"preview: {PREVIEW.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
