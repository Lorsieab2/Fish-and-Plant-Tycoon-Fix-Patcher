"""Build the Auto-Healer's picture from the Auto-Feeder's: the same machine in hot pink.

    python scripts/build_auto_healer_source.py

Reads assets/auto_upgrades/auto_feeder_source.png (the owner's green feeder, 197 x 154) and writes
assets/auto_upgrades/auto_healer_source.png: every strongly green pixel of the body (saturation above
0.5, hue 0.21-0.42, brightness above 0.25) turned to hot pink (hue 330 degrees), its saturation
raised 5% and its brightness kept; the glass, the food, the greys and the yellow light stay as they
are. The owner picked this recolour; both games' Auto-Healer use it
(scripts/build_auto_upgrades_assets.py).
"""

from __future__ import annotations

import colorsys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FEEDER = ROOT / "assets" / "auto_upgrades" / "auto_feeder_source.png"
HEALER = ROOT / "assets" / "auto_upgrades" / "auto_healer_source.png"
HOT_PINK = 330 / 360


def healer(feeder: Image.Image) -> Image.Image:
    a = np.asarray(feeder.convert("RGBA")).astype(float) / 255
    out = a.copy()
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            if a[y, x, 3] == 0:
                continue
            h, s, v = colorsys.rgb_to_hsv(*a[y, x, :3])
            if s > 0.5 and 0.21 < h < 0.42 and v > 0.25:      # the green body only
                out[y, x, :3] = colorsys.hsv_to_rgb(HOT_PINK, min(1, s * 1.05), v)
    return Image.fromarray((out * 255).round().astype("uint8"), "RGBA")


def main() -> int:
    healer(Image.open(FEEDER)).save(HEALER)
    print(f"{HEALER.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
