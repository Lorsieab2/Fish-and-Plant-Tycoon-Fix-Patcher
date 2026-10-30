"""Render docs/images/multiple-ornaments-tank.png: Tank One with the six ornaments
and decorative copies, placed the way the game draws them.

    python scripts/render_ornament_preview.py "<vanilla Fish Tycoon folder>"

Art comes from the game's own Assets/ft.dat (never shipped). Each ornament is
drawn as the stock pass 0x41D600 draws one at rest: its shadow
(TANK_OBJECT_SHADOW.png) at (x - 25, y + h - 25), then the ornament at (x, y),
with y = 470 - h, where the stock fall (0x41DB00) lands it. Later records are
drawn on top, and the copies after the originals, as "Multiple Ornaments.dll"
draws them.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "multiple-ornaments-tank.png"

ORIGINALS = [("shell02.png", 90), ("pagoda1.png", 190), ("diverblue.png", 330), ("beigecoral.png", 450),
             ("column01.png", 560), ("junk1.png", 640)]
COPIES = [("shell02.png", 40), ("shell02.png", 140), ("shell02.png", 285), ("pagoda1.png", 400),
          ("beigecoral.png", 250), ("beigecoral.png", 700), ("diverblue.png", 520), ("column01.png", 20),
          ("junk1.png", 600), ("shell02.png", 745)]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    game = Path(sys.argv[1])
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        def art(name: str) -> Image.Image:
            return Image.open(io.BytesIO(archive.read(name))).convert("RGBA")
        tank = art("maintank1_bg_png.png")
        shadow = art("tank_object_shadow.png")
        sprites = {name: art(name) for name, _ in ORIGINALS}
    picture = tank.copy()
    for name, x in ORIGINALS + COPIES:
        image = sprites[name]
        y = 470 - image.height
        picture.alpha_composite(shadow, (x - 25, y + image.height - 25))
        picture.alpha_composite(image, (x, y))
    draw = ImageDraw.Draw(picture)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    caption = "Tank One: the six ornaments (one each) and 10 decorative copies, the most a tank holds"
    box = draw.textbbox((0, 0), caption, font=font)
    draw.rectangle((0, 0, picture.width, box[3] + 12), fill=(0, 0, 0, 170))
    draw.text((10, 6), caption, fill=(255, 255, 255, 255), font=font)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    picture.convert("RGB").save(OUT, optimize=True)
    print(f"{OUT.relative_to(ROOT)}: {picture.width} x {picture.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
