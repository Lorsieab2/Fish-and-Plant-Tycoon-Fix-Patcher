"""The patcher-made accented letters of the four "Render Unicode with In-Game Fonts" pictures
(Images\\<font>_unicode.png) carry a real accent: a tilde or diaeresis at least three pixels wide
and two tall (v1.0.26 shipped paddington_tt_30 with a 1-pixel tick for the tilde of N and the
capital diaeresis: its own ~ is a 1-pixel placeholder and its capital diaeresis sits beside
the A's top). Read from the shipped pictures and the DLL tables alone (no game needed)."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unicodedata
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from picture_image import Image  # noqa: E402
import text_maker as tm  # noqa: E402

FONTS = {
    "paddington_tt_18": ("fish", "paddington_tt_18_unicode"),
    "paddington_tt_30": ("fish", "paddington_tt_30_unicode"),
    "font_triplex_sanslightlin_bold_16pt": ("fish", "FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT_unicode"),
    "PTfontsmall": ("plant", "PTfontsmall_unicode"),
}
# Accents checked, with how they must look: (least width, least height, dots in a row).
ABOVE = {"̃": ("tilde", 3, 2, 1), "̈": ("diaeresis", 3, 2, 2), "̂": ("circumflex", 3, 2, 1),
         "̊": ("ring", 3, 2, 1), "́": ("acute", 2, 2, 1), "̀": ("grave", 2, 2, 1)}


def tables(game: str) -> dict[str, tuple[list[list[int]], int]]:
    """Each font's table in the DLL header: (records, number of game records)."""
    text = (ROOT / "native" / f"ftfp_{game}_unicode" / "unicode_fonts.h").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"/\* (\S+): (\d+) game records, \d+ added;.*?\{\n(.*?)\n\};", text, re.S):
        rows = []
        for line in m.group(3).splitlines():
            nums = [int(v) for v in re.findall(r"-?\d+", line.split("/*")[0])]
            if len(nums) == 5 and nums != [0, 0, 0, 0, 0]:
                rows.append(nums)
        out[m.group(1)] = (rows, int(m.group(2)))
    return out


def alpha(px: Image, x: int, y: int) -> int:
    return px.data[(y * px.width + x) * 4 + 3]


def pieces(px: Image, solid: int = 160) -> list[set]:
    """The letter's pieces of solid ink (4-connected pixels at least `solid` opaque)."""
    left = {(x, y) for y in range(px.height) for x in range(px.width) if alpha(px, x, y) >= solid}
    out = []
    while left:
        stack = [left.pop()]
        piece = set(stack)
        while stack:
            x, y = stack.pop()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in left:
                    left.remove(n)
                    piece.add(n)
                    stack.append(n)
        out.append(piece)
    return out


def accent(px: Image) -> tuple[int, int, int] | None:
    """The accent above the letter, as (width, rows, most pieces side by side in one row):
    its strong ink (alpha 128+) above the letter body (the biggest piece of solid ink)."""
    parts = pieces(px, 224)
    if not parts:
        return None
    body = max(parts, key=len)
    # The rows above the body's solid top, less the row of its edge's faint ink (a squeezed
    # capital's accent touches it through faint ink).
    rows = range(0, min(y for _x, y in body) - 1)
    strong = [(x, y) for y in rows for x in range(px.width) if alpha(px, x, y) >= 128]
    if not strong:
        return None
    xs = [x for x, _y in strong]
    ys = sorted({y for _x, y in strong})
    runs = 0
    for y in ys:
        on = [alpha(px, x, y) >= 128 for x in range(px.width)]
        runs = max(runs, sum(1 for i, f in enumerate(on) if f and (i == 0 or not on[i - 1])))
    return max(xs) - min(xs) + 1, len(ys), runs


class AccentSizeTests(unittest.TestCase):
    def test_every_patcher_made_accent_is_its_size_in_all_four_fonts(self) -> None:
        checked = 0
        for key, (game, picture) in FONTS.items():
            table, game_records = tables(game)[key]
            data = (ROOT / "assets" / f"{game}_tycoon_unicode" / "Images" / f"{picture}.png").read_bytes()
            sheet = Image.from_png(data)
            laid, _h = tm.relayout(table, sheet.width)
            for rec in laid[game_records:]:
                ch = bytes([rec[0]]).decode("cp1252")
                marks = unicodedata.normalize("NFD", ch)[1:]
                if len(marks) != 1 or marks not in ABOVE:
                    continue
                name, least_w, least_h, dots = ABOVE[marks]
                with self.subTest(font=key, letter=ch):
                    px = sheet.sub(rec[1], rec[2], rec[3] - rec[1], rec[4] - rec[2])
                    found = accent(px)
                    self.assertIsNotNone(found, f"{ch} has no accent above it")
                    width, height, count = found
                    self.assertGreaterEqual(height, least_h, f"{name} of {ch} is {height} px tall")
                    self.assertGreaterEqual(width, least_w, f"{name} of {ch} is {width} px wide")
                    self.assertGreaterEqual(count, dots, f"{name} of {ch} lacks its two dots")
                    if name == "tilde":
                        self.assertGreater(width, height, f"the tilde of {ch} is not wider than tall")
                    checked += 1
        self.assertGreater(checked, 40)

    def test_a_one_pixel_mark_is_never_taken_from_a_font(self) -> None:
        tick = Image(1, 3)
        tick.data[3::4] = b"\xff" * 3
        self.assertFalse(tm.plausible_mark("tilde", tick))
        self.assertFalse(tm.plausible_mark("diaeresis", tick))
        wave = Image(5, 2)
        wave.data[3::4] = b"\xff" * 10
        self.assertTrue(tm.plausible_mark("tilde", wave))
        self.assertTrue(tm.plausible_mark("acute", tick))


if __name__ == "__main__":
    unittest.main()
