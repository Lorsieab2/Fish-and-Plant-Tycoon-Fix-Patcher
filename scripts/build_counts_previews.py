"""Render what the tank and greenhouse counts look like in each game.

    python scripts/build_counts_previews.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>"

Writes, in docs/images, tank-counts-fish.png and greenhouse-counts-plant.png
(the counts shown) and tank-counts-fish-off.png and
greenhouse-counts-plant-off.png (hidden: only the on/off button): each game's
screen background with the text set in the game's own font (paddington_tt_18
from ft.dat and PTfontsmall.png, each with its glyph table in the executable)
at the place, colours and shadow the DLLs draw it (native/ftfp_tank_counts,
native/ftfp_greenhouse_counts). The tank screen's top bar, bottom panels and
isolation tank are laid over it as the game draws them (the bottom panels at
y 485, the isolation tank at x 496).
"""

from __future__ import annotations

import io
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PREVIEWS = ROOT / "docs" / "images"
IMAGE_BASE = 0x400000
WHITE, YELLOW = (255, 255, 255), (255, 208, 64)        # the DLLs' 0xFFFFFFFF and 0xFFFFD040

FISH_LINES = ("Fish: 12 of 21 (8 adults, 3 teens, 1 baby)  Dead: 1",
              "Sick: 2 fungus, 1 ick",
              "Creatures: Golden Seahorse, Moray Eel",
              "Isolation tank: 1 of 1 (1 adult)")
FISH_AT, FISH_LINE_H, FISH_BUTTON, FISH_GLYPHS = (12, 62), 20, (694, 60), 0x458580      # paddington_tt_18
PLANT_LINES = ("Plants: 9 of 15 (5 mature, 2 with buds, 2 seedlings)  Dead: 1",
               "Infested: 1  Unhealthy: 1")
PLANT_AT, PLANT_LINE_H, PLANT_BUTTON, PLANT_GLYPHS = (236, 4), 22, (694, 26), 0x47A550  # PTfontsmall


def glyph_table(exe: bytes, address: int) -> dict[int, tuple[int, int, int, int]]:
    """{char, x0, y0, x1, y1} int records, ended by char 0 (the executables' font tables)."""
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    count = struct.unpack_from("<H", exe, pe + 6)[0]
    optional = struct.unpack_from("<H", exe, pe + 20)[0]
    at = None
    for i in range(count):
        header = pe + 24 + optional + i * 40
        _vsize, rva, raw_size, raw = struct.unpack_from("<IIII", exe, header + 8)
        if rva <= address - IMAGE_BASE < rva + raw_size:
            at = raw + address - IMAGE_BASE - rva
    table = {}
    while True:
        char, x0, y0, x1, y1 = struct.unpack_from("<5i", exe, at)
        if char == 0:
            return table
        table[char & 0xFF] = (x0, y0, x1, y1)
        at += 20


def set_text(sheet: Image.Image, table: dict, text: str, colour: tuple[int, int, int]) -> Image.Image:
    """The text laid glyph by glyph (each advances by its own width), tinted like the game's text."""
    rects = [table[ord(ch)] for ch in text]
    word = Image.new("RGBA", (sum(r[2] - r[0] for r in rects), max(r[3] - r[1] for r in rects)))
    x = 0
    for x0, y0, x1, y1 in rects:
        word.alpha_composite(sheet.crop((x0, y0, x1, y1)), (x, 0))
        x += x1 - x0
    tinted = np.asarray(word).copy()
    tinted[..., :3] = (tinted[..., :3].astype(float) * np.array(colour) / 255).round().astype("uint8")
    return Image.fromarray(tinted, "RGBA")


def draw(screen: Image.Image, sheet: Image.Image, table: dict, text: str, at: tuple[int, int],
         colour: tuple[int, int, int] = WHITE) -> None:
    screen.alpha_composite(set_text(sheet, table, text, (0, 0, 0)), (at[0] + 1, at[1] + 1))
    screen.alpha_composite(set_text(sheet, table, text, colour), at)


def draw_counts(screen: Image.Image, sheet: Image.Image, table: dict, shown: bool, lines: tuple[str, ...],
                at: tuple[int, int], line_h: int, button: tuple[int, int]) -> None:
    draw(screen, sheet, table, "Counts: On" if shown else "Counts: Off", button, YELLOW)
    if shown:
        for i, line in enumerate(lines):
            draw(screen, sheet, table, line, (at[0], at[1] + i * line_h))


def fish_preview(game: Path, shown: bool) -> Image.Image:
    exe = (game / "Fish Tycoon.exe").read_bytes()
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist()}

        def image(name: str) -> Image.Image:
            return Image.open(io.BytesIO(archive.read(names[name]))).convert("RGBA")
        screen = image("maintank1_bg_png.png")
        draw_counts(screen, image("paddington_tt_18.png"), glyph_table(exe, FISH_GLYPHS), shown, FISH_LINES,
                    FISH_AT, FISH_LINE_H, FISH_BUTTON)
        for name, at in (("ui_maintank_top_png.png", (0, 0)), ("ui_maintank_bottom_left_png.png", (0, 485)),
                         ("ui_isotank_png.png", (496, 485)), ("ui_maintank_bottom_right_png.png", (639, 485))):
            screen.alpha_composite(image(name), at)
    return screen


def plant_preview(game: Path, shown: bool) -> Image.Image:
    exe = (game / "Plant Tycoon.exe").read_bytes()
    screen = Image.open(game / "Images" / "main_bg.png").convert("RGBA")
    sheet = Image.open(game / "Images" / "PTfontsmall.png").convert("RGBA")
    draw_counts(screen, sheet, glyph_table(exe, PLANT_GLYPHS), shown, PLANT_LINES, PLANT_AT, PLANT_LINE_H,
                PLANT_BUTTON)
    return screen


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    fish, plant = Path(sys.argv[1]), Path(sys.argv[2])
    for shown, suffix in ((True, ""), (False, "-off")):
        fish_preview(fish, shown).convert("RGB").save(PREVIEWS / f"tank-counts-fish{suffix}.png", optimize=True)
        plant_preview(plant, shown).convert("RGB").save(PREVIEWS / f"greenhouse-counts-plant{suffix}.png",
                                                        optimize=True)
    print(f"previews in {PREVIEWS.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
