"""Render the extra greenhouses' and nurseries' mockups from the game's own art.

    python scripts/render_extra_greenhouses_preview.py "<vanilla Plant Tycoon folder>"

writes, in docs/images:

* extra-greenhouses-switch.png: the greenhouse background (main_bg.png), a
  pot on every table spot (pot.png, at the game's own pot places: 0x42FDE0
  x = 323 + 93 * column, y = 117 + 144 * row, drawn at x - 28, y - 15 by
  0x42F740), the two gold arrows (leftarrow.png / rightarrow.png, first frame)
  and "Greenhouse 2 of 3", where Extra Greenhouses.dll draws them;
* extra-nurseries-switch.png: the nursery background (Nursery_BG.jpg and its
  bar, nurseryUI.png), the arrows and "Nursery 2 of 3";
* extra-greenhouses-store.png: the Supplies store's background (Store_BG.jpg)
  with the two new Upgrades items where Store Upgrades and Items.dll draws
  them: the Extra Greenhouse (greenhouse1.png at 0.29) on the tool shelf and
  the Extra Nursery (goldpot.png at 0.84) on the Nursery shelf, with their
  tooltips' text below.

Every word is set from the game's own font (PTfontsmall.png with the glyph
table at 0x47A550); a missing glyph stops the script. No plant art: the
pictures are about the switches.
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native" / "ftfp_extra_greenhouses" / "ftfp_extra_greenhouses.c"
IMAGES_OUT = ROOT / "docs" / "images"
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


def words(folder: Path, exe: bytes, text: str) -> Image.Image:
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


def arrows(screen: Image.Image, images: Path, left: int, right: int, y: int) -> None:
    for name, x in (("leftarrow.png", left), ("rightarrow.png", right)):
        arrow = Image.open(images / name).convert("RGBA")
        screen.alpha_composite(arrow.crop((0, 0, arrow.height, arrow.height)), (x, y))


def centred(screen: Image.Image, word: Image.Image, x: int, y: int) -> None:
    screen.alpha_composite(word, (x - word.width // 2, y))


def scaled(path: Path, scale: float) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    return image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)


def save(screen: Image.Image, name: str) -> None:
    out = IMAGES_OUT / name
    out.parent.mkdir(parents=True, exist_ok=True)
    screen.convert("RGB").save(out, optimize=True)
    print(f"wrote {out.relative_to(ROOT)}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1])
    exe = (folder / "Plant Tycoon.exe").read_bytes()
    images = folder / "Images"
    for text in ("Greenhouse 6 of 6", "Nursery 6 of 6", "Extra Greenhouse 5 of 5", "Extra Nursery", "Sold out"):
        words(folder, exe, text)                         # every label the DLLs can draw has its glyphs

    screen = Image.open(images / "main_bg.png").convert("RGBA")
    pots = Image.open(images / "pot.png").convert("RGBA")
    frame_h = pots.height // 7
    for row in range(3):
        for column in range(5):
            style = (row * 5 + column) % 6
            pot = pots.crop((0, style * frame_h, pots.width, (style + 1) * frame_h))
            screen.alpha_composite(pot, (323 + 93 * column - 28, 117 + 144 * row - 15))
    arrows(screen, images, constant("LEFT_X"), constant("RIGHT_X"), constant("ARROW_Y"))
    centred(screen, words(folder, exe, "Greenhouse 2 of 3"), constant("LABEL_X"), constant("LABEL_Y"))
    save(screen, "extra-greenhouses-switch.png")

    # The stock nursery screen as its draw lays it out (0x437183..0x437880 and 0x4375EC): the
    # background, the 15 plant stands (singleTable1.png, sprite 0xC7) at the game's own places, its two
    # bushes and the bottom bar; a potted plant (pot.png, a flower head from Flowers56x56_Grid.png) on
    # some stands. Nursery 1 and Nursery 2 are drawn by the same code: only the plants and the label differ.
    stands = [(77, 210), (106, 425), (219, 478), (355, 436), (486, 488), (546, 487), (604, 427), (634, 236),
              (676, 204), (587, 100), (457, 95), (244, 98), (68, 313), (694, 345), (640, 301)]
    flowers = Image.open(images / "Flowers56x56_Grid.png").convert("RGBA")
    for page, cells in ((1, (0, 9, 18, 27, 36, 45, 3, 12)), (2, (6, 15, 24, 33, 42))):
        screen = Image.open(images / "Nursery_BG.jpg").convert("RGBA")
        stand = Image.open(images / "singleTable1.png").convert("RGBA")
        for x, y in stands:
            screen.alpha_composite(stand, (x, y))
        screen.alpha_composite(Image.open(images / "EBushTable1.png").convert("RGBA"), (744, 355))
        screen.alpha_composite(Image.open(images / "spikeyNEBush1.png").convert("RGBA"), (665, 48))
        for n, cell in enumerate(cells):
            x, y = stands[(n * 2 + page) % len(stands)]
            style = (cell + page) % 6
            pot = pots.crop((0, style * frame_h, pots.width, (style + 1) * frame_h)).resize((52, 44))
            head = flowers.crop(((cell % 14) * 56, (cell // 14) * 56, (cell % 14) * 56 + 56, (cell // 14) * 56 + 56))
            screen.alpha_composite(pot, (x + 8, y - 30))
            screen.alpha_composite(head, (x + 6, y - 72))
        bar = Image.open(images / "nurseryUI.png").convert("RGBA")
        screen.alpha_composite(bar, (0, 0x1E4))
        arrows(screen, images, constant("NU_LEFT_X"), constant("NU_RIGHT_X"), constant("NU_ARROW_Y"))
        centred(screen, words(folder, exe, f"Nursery {page} of 3"), constant("NU_LABEL_X"), constant("NU_LABEL_Y"))
        save(screen, "extra-nurseries-switch.png" if page == 2 else "extra-nurseries-nursery-1.png")

    screen = Image.open(images / "Store_BG.jpg").convert("RGBA")
    for picture, scale, x, y, tip in (("greenhouse1.png", 0.29, 404 + 6, 50, "Extra Greenhouse 2 of 5"),
                                      ("goldpot.png", 0.84, 440 + 6, 296, "Extra Nursery 1 of 5")):
        item = scaled(images / picture, scale)
        screen.alpha_composite(item, (x, y))
        centred(screen, words(folder, exe, tip), x + item.width // 2, y + item.height + 4)
        centred(screen, words(folder, exe, "Price: $ 10000"), x + item.width // 2, y + item.height + 20)
    save(screen, "extra-greenhouses-store.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
