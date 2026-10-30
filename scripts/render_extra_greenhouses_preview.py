"""Render the extra greenhouses' switch as it looks on the greenhouse screen.

    python scripts/render_extra_greenhouses_preview.py "<vanilla Plant Tycoon folder>"

writes docs/images/extra-greenhouses-switch.png: the greenhouse background
(main_bg.png), a pot on every table spot (pot.png, at the game's own pot
places: 0x42FDE0 x = 323 + 93 * column, y = 117 + 144 * row, drawn at
x - 28, y - 15 by 0x42F740), the two gold arrows (leftarrow.png /
rightarrow.png, first frame) where Extra Greenhouses.dll puts them, and
"Greenhouse 2 of 6" set from the game's own font (PTfontsmall.png with the
glyph table at 0x47A550), centred where the DLL draws it. No plant art: the
picture is about the switch.
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native" / "ftfp_extra_greenhouses" / "ftfp_extra_greenhouses.c"
OUT = ROOT / "docs" / "images" / "extra-greenhouses-switch.png"
FONT_TABLE, IMAGE_BASE, TEXT_COLOUR = 0x47A550, 0x400000, 0x48EA2C


def constant(name: str) -> int:
    match = re.search(rf"#define {name} (\d+)", SOURCE.read_text(encoding="utf-8-sig"))
    return int(match.group(1))


def file_offset(exe: bytes, va: int) -> int:
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    count = struct.unpack_from("<H", exe, pe + 6)[0]
    table = pe + 24 + struct.unpack_from("<H", exe, pe + 20)[0]
    for i in range(count):
        vsize, rva, raw_size, raw = struct.unpack_from("<IIII", exe, table + 40 * i + 8)
        if rva <= va - IMAGE_BASE < rva + max(vsize, raw_size):
            return raw + va - IMAGE_BASE - rva
    raise ValueError(hex(va))


def glyphs(exe: bytes) -> dict[int, tuple[int, int, int, int]]:
    table, at = {}, file_offset(exe, FONT_TABLE)
    while True:
        char, x0, y0, x1, y1 = struct.unpack_from("<5i", exe, at)
        if char <= 0 or char > 255:
            return table
        table[char] = (x0, y0, x1, y1)
        at += 20


def label(folder: Path, exe: bytes, text: str) -> Image.Image:
    table = glyphs(exe)
    missing = sorted({ch for ch in text if ch != " " and ord(ch) not in table})
    if missing:
        raise SystemExit(f"the game's font has no glyph for {missing}")
    font = Image.open(folder / "Images" / "PTfontsmall.png").convert("RGBA")
    space = max(4, (table[ord("n")][2] - table[ord("n")][0]) // 2)
    rects = [table.get(ord(ch)) for ch in text]
    width = sum(r[2] - r[0] if r else space for r in rects)
    height = max(r[3] - r[1] for r in rects if r)
    word = Image.new("RGBA", (width, height))
    x = 0
    for r in rects:
        if r is None:
            x += space
            continue
        word.alpha_composite(font.crop(r), (x, 0))
        x += r[2] - r[0]
    colour = struct.unpack_from("<I", exe, file_offset(exe, TEXT_COLOUR))[0]
    if colour:                                           # the game's text colour, if it starts set
        r_, g_, b_ = colour & 0xFF, (colour >> 8) & 0xFF, (colour >> 16) & 0xFF
        pixels = word.load()
        for yy in range(word.height):
            for xx in range(word.width):
                p = pixels[xx, yy]
                pixels[xx, yy] = (p[0] * r_ // 255, p[1] * g_ // 255, p[2] * b_ // 255, p[3])
    return word


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1])
    exe = (folder / "Plant Tycoon.exe").read_bytes()
    images = folder / "Images"
    screen = Image.open(images / "main_bg.png").convert("RGBA")
    pots = Image.open(images / "pot.png").convert("RGBA")
    frame_h = pots.height // 7
    for row in range(3):
        for column in range(5):
            style = (row * 5 + column) % 6
            pot = pots.crop((0, style * frame_h, pots.width, (style + 1) * frame_h))
            screen.alpha_composite(pot, (323 + 93 * column - 28, 117 + 144 * row - 15))
    y = constant("ARROW_Y")
    for name, x in (("leftarrow.png", constant("LEFT_X")), ("rightarrow.png", constant("RIGHT_X"))):
        arrow = Image.open(images / name).convert("RGBA")
        screen.alpha_composite(arrow.crop((0, 0, arrow.height, arrow.height)), (x, y))
    word = label(folder, exe, "Greenhouse 2 of 6")
    screen.alpha_composite(word, (constant("LABEL_X") - word.width // 2, constant("LABEL_Y")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    screen.convert("RGB").save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
