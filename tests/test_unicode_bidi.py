"""Whole-line bidi (UAX #9) in Unicode Text.dll, both games: a line that mixes left-to-right and
right-to-left text is put in visual order as a whole (native/common/unicode_glyphs.h walk_bidi_line).

* Natively (tests/native_glyphs.py, the DLL's own code with Windows' Uniscribe), Windows only:
  - line_levels gives every UTF-16 unit Uniscribe's level from a full bidi analysis with a
    left-to-right base: European digits after Arabic letters are an Arabic number (level 2), the
    spaces between right-to-left words are right to left, one between a right-to-left and a
    left-to-right word is left to right; and the Unicorn stand-in (uniscribe_levels) gives the same;
  - visual_order (ScriptLayout across all of a line's runs) and the DLL's own rule L2 (reverse_runs,
    used without Uniscribe) agree on every order of levels tried;
  - a right-to-left run shaped with a right-to-left base (piece_rtl) puts its trailing "!" on its
    left, and an all-Hebrew run is the same picture as before.
* In Unicorn (the DLL's and the game's own draw and measure; Windows' letters stood in for, Uniscribe's
  levels from Windows' own ScriptItemize):
  - "Fish مرحبا 123 שלום Tycoon" is drawn left to right as Fish, שלום, 123, مرحبا, Tycoon, each
    right-to-left run asked for whole and shaped right to left, the digits and spaces the game's own;
  - numbers inside right-to-left text read left to right ("שלום 1234 עולם", "מחיר 12.5% היום",
    Arabic letters with Arabic-Indic digits);
  - the width the games lay names and labels out with is the drawn width, line by line;
  - a line with no right-to-left letter is pixel for pixel what v1.0.26 drew (hashes taken from
    v1.0.26's DLL), and never asks for bidi levels;
  - without Uniscribe a line is drawn in its logical order as before.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_unicode_text as T  # noqa: E402
from test_unicode_text import needs  # noqa: E402

try:
    import test_unicode_glyphs as G
    import native_glyphs as NG
except ImportError:          # no Unicorn
    G = NG = None

ROOT = Path(__file__).resolve().parents[1]

ARABIC = "مرحبا"
HEBREW = "שלום"
HEBREW2 = "עולם"
MIXED = f"Fish {ARABIC} 123 {HEBREW} Tycoon"

# Lines with no right-to-left letter, drawn and measured by v1.0.26's DLL in Unicorn with the same
# stand-ins (raster_glyph: G.fake_glyph; raster_cluster: 3 + n columns, advance 5 + n): the first 16
# hex digits of the screen's SHA-256 and the measured width.
LTR_LINES = (
    "Hello, World 123",
    "Ünïcödé ź İstanbul 山田 太郎",
    "नमस्ते दुनिया and สวัสดี",
    "fish \U0001F41F \U0001F468‍\U0001F469‍\U0001F467 \U0001F1EF\U0001F1F5 "
    "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F 1️⃣",
    "line one\nline two ź\n中文 (x)",
    "١٢٣ abc ۴۵",
    "á é (x) [y] <z> «»",
    "Ж Ω Ł ★ \U00012000 ",
)
V1_0_26 = {
    "fish": [("a5eb50d86b148193", 138), ("4f97c72cc41d71d1", 188), ("6c4e9e276c49e56e", 66),
             ("986a312bf4d76227", 97), ("20bc96660eb8a395", 78), ("78d6de92e63bf292", 51),
             ("417527bac668ed82", 129), ("a668ab52932247d9", 69)],
    "plant": [("6169405d1e4ae63b", 135), ("65c034d98b8e5eec", 192), ("917bfa06174d3f99", 72),
              ("4dce7d2a7e279acc", 103), ("3c6810eac0648949", 78), ("81b1a3d893995208", 57),
              ("10e92f650f17db0f", 151), ("b83079de7b9a7ffa", 75)],
}


def units_of(text: str) -> list[int]:
    raw = text.encode("utf-16-le")
    return [raw[i] | raw[i + 1] << 8 for i in range(0, len(raw), 2)]


def cps(text: str) -> tuple[int, ...]:
    return tuple(ord(c) for c in text)


class BidiCase:
    """The game's own draw with the DLL's; Windows' letters stood in for, Uniscribe's levels real."""
    game = "fish"

    def setUp(self) -> None:
        if os.name != "nt":
            self.skipTest("needs Windows' Uniscribe for the bidi levels")
        self.base = G.GlyphCase()
        self.base.game = self.game
        self.base.setUp()
        self.pieces: list[tuple[tuple[int, ...], int]] = []
        self.whole = True
        self.base.fde.emu.hook(self.base.symbols["_raster_cluster"], self._cluster, 0)

    def _cluster(self, e) -> int:
        cps_at, n, height, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(7))
        got = tuple(e.read32(cps_at + 4 * k) for k in range(n))
        self.pieces.append((got, e.read32(self.base.symbols["_piece_rtl"])))
        if not self.whole:
            return 0
        e.uc.mem_write(coverage, b"\xFF" * ((3 + n) * height))
        e.write32(w_at, 3 + n)
        e.write32(xoff_at, 0)
        e.write32(adv_at, 5 + n)
        return 1

    def asked(self) -> list[tuple[tuple[int, ...], int]]:
        """The pieces asked for, in order, once each (the draw and the measure cache their own)."""
        return list(dict.fromkeys(self.pieces))

    def expect(self, tokens: list[tuple[str, object]]) -> tuple[bytes, int]:
        """The screen and width of `tokens` drawn left to right from x 5: ("own", bytes) the game's own
        letters, ("piece", n) a stand-in piece of n code points."""
        b = self.base
        b.fde.fill((10, 20, 30))
        x = 5
        for kind, value in tokens:
            if kind == "own":
                b.draw(value, own=True, x=x, fill=False)
                x += b.width(value, own=True) + b.spacing
            else:
                b.paint(x, 7, 3 + value, b.height)
                x += 5 + value + b.spacing
        return bytes(b.fde.screen_image.data), x - 5 - b.spacing

    def check(self, text: str, tokens: list[tuple[str, object]]) -> None:
        screen, width = self.expect(tokens)
        self.assertEqual(self.base.draw(text.encode("utf-8")), screen)
        self.assertEqual(self.base.width(text.encode("utf-8")), width)

    def test_a_mixed_line_is_drawn_in_visual_order(self) -> None:
        # logical: Fish_ | مرحبا_ (1) | 123 (2) | _שלום (1) | _Tycoon; visual: Fish_ שלום_ 123 _مرحبا _Tycoon
        self.check(MIXED, [("own", b"Fish "), ("piece", 4), ("own", b" "), ("own", b"123"), ("own", b" "),
                           ("piece", 5), ("own", b" Tycoon")])
        self.assertIn((cps(HEBREW), 1), self.pieces)        # each right-to-left run whole, shaped right to left
        self.assertIn((cps(ARABIC), 1), self.pieces)
        self.assertEqual(self.base.bidi_lines[-1], units_of(MIXED))

    def test_numbers_in_right_to_left_text_read_left_to_right(self) -> None:
        self.check(f"{HEBREW} 1234 {HEBREW2}", [("piece", 4), ("own", b" "), ("own", b"1234"), ("own", b" "),
                                               ("piece", 4)])
        self.assertEqual(self.pieces[0], (cps(HEBREW2), 1))      # the last word first, on the left
        self.pieces.clear()
        self.check("מחיר 12.5% היום", [("piece", 4), ("own", b" "), ("own", b"12.5%"), ("own", b" "),
                                       ("piece", 4)])
        self.assertEqual([p for p, _r in self.asked()], [cps("היום"), cps("מחיר")])
        # Arabic letters and Arabic-Indic digits (an Arabic number, its own run, left to right)
        self.pieces.clear()
        self.check(f"A {ARABIC} ١٢٣ b", [("own", b"A "), ("piece", 3), ("own", b" "), ("piece", 5),
                                         ("own", b" b")])
        self.assertEqual(self.asked(), [(cps("١٢٣"), 0), (cps(ARABIC), 1)])

    def test_a_right_to_left_line(self) -> None:
        # all right to left: one piece, as before
        self.check(f"{HEBREW} {HEBREW2}", [("piece", 9)])
        self.assertEqual(self.asked(), [(cps(f"{HEBREW} {HEBREW2}"), 1)])

    def test_every_line_on_its_own(self) -> None:
        b = self.base
        text = f"abc\n{HEBREW} 12\nxyz"
        widths = [b.width(b"abc", own=True), 5 + 4 + b.spacing + b.width(b" 12", own=True),
                  b.width(b"xyz", own=True)]
        self.assertEqual(b.width(text.encode("utf-8")), max(widths))
        b.bidi_lines.clear()
        b.draw(text.encode("utf-8"))
        self.assertEqual(b.bidi_lines, [units_of(f"{HEBREW} 12")])      # only the line with a Hebrew word

    def test_a_run_no_font_has_whole_is_drawn_unit_by_unit_last_first(self) -> None:
        self.whole = False
        self.base.draw(f"x {ARABIC} {HEBREW} y".encode("utf-8"))
        asked = [p for p, _r in self.pieces]
        # the whole run first, then its units last first: the Hebrew word, then the Arabic word
        self.assertEqual(asked[0], cps(f"{ARABIC} {HEBREW}"))
        self.assertLess(asked.index(cps(HEBREW)), asked.index(cps(ARABIC)))

    def test_a_line_with_no_right_to_left_letter_is_as_before(self) -> None:
        b = self.base
        b.bidi_lines.clear()
        for line, (digest, width) in zip(LTR_LINES, V1_0_26[self.game]):
            with self.subTest(line=line):
                raw = line.encode("utf-8")
                self.assertEqual(hashlib.sha256(b.draw(raw)).hexdigest()[:16], digest)
                self.assertEqual(b.width(raw), width)
        self.assertEqual(b.bidi_lines, [])

    def test_without_uniscribe_a_line_is_in_its_logical_order(self) -> None:
        b = self.base
        b.fde.emu.hook(b.symbols["_line_levels"], lambda e: 0, 0)
        b.draw(MIXED.encode("utf-8"))
        # as v1.0.26: the Arabic word, then the Hebrew word, each a run left as it is typed
        self.assertEqual(self.pieces, [(cps(ARABIC), 0), (cps(HEBREW), 0)])


@needs("fish")
class FishBidiTests(BidiCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantBidiTests(BidiCase, unittest.TestCase):
    game = "plant"


def _native_ready() -> bool:
    return NG is not None and NG.available() and T._ready("fish")


@unittest.skipUnless(os.name == "nt" and _native_ready(), "needs Windows, the pinned MSVC toolset, Unicorn and the games")
class NativeBidiTests(unittest.TestCase):
    server = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = NG.GlyphServer("fish")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.close()

    def test_uniscribe_levels(self) -> None:
        s = self.server
        self.assertEqual(s.levels(MIXED), [0] * 5 + [1] * 6 + [2] * 3 + [1] * 5 + [0] * 7)
        self.assertEqual(s.levels("שלום 12.5% עולם"), [1] * 5 + [2] * 5 + [1] * 5)
        self.assertEqual(s.levels("abc (x) 123"), [0] * 11)
        self.assertEqual(s.levels("مرحبا ١٢٣"), [1] * 6 + [2] * 3)
        for line in (MIXED, "שלום 12.5% עולם", "abc א\U0001F41Fב def", "a‏(b", f"{ARABIC}!"):
            with self.subTest(line=line):
                self.assertEqual(NG.uniscribe_levels(units_of(line)), s.levels(line))

    def test_scriptlayout_and_rule_l2_agree(self) -> None:
        rnd = random.Random(26)
        for _ in range(400):
            levels = [rnd.choice((0, 0, 1, 1, 2, 3, 4)) for _ in range(rnd.randint(1, 12))]
            with self.subTest(levels=levels):
                layout, by_hand = self.server.order(levels)
                self.assertEqual(layout, by_hand)
                self.assertEqual(sorted(layout), list(range(len(levels))))
        self.assertEqual(self.server.order([0, 1, 2, 1, 0])[0], [0, 3, 2, 1, 4])

    def test_a_right_to_left_piece(self) -> None:
        s = self.server
        s.pen(0, 20)
        try:
            s.poke("piece_rtl", 1)
            rtl = s.raster(f"{HEBREW}!")
            plain_rtl = s.raster(f"{HEBREW} {HEBREW2}")
        finally:
            s.poke("piece_rtl", 0)
        bang = s.raster("!")
        plain = s.raster(f"{HEBREW} {HEBREW2}")
        # the "!" ends the sentence on its left
        left = [[rtl.coverage(x, y) for x in range(bang.w)] for y in range(rtl.height)]
        alone = [[bang.coverage(x, y) for x in range(bang.w)] for y in range(bang.height)]
        self.assertEqual(left, alone)
        # a Hebrew run alone: the same picture with a right-to-left base
        self.assertEqual((plain_rtl.w, plain_rtl.adv, plain_rtl.data), (plain.w, plain.adv, plain.data))


class SourceTests(unittest.TestCase):
    def test_only_lines_with_a_right_to_left_letter_take_the_bidi_path(self) -> None:
        text = (ROOT / "native" / "common" / "unicode_glyphs.h").read_text(encoding="utf-8")
        body = text[text.index("static int walk_bidi_line(walk *w, const unsigned char **p) {"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("if (!rtl) return 0;", body)
        self.assertLess(body.index("if (!rtl) return 0;"), body.index("line_levels("))
        self.assertIn("state.uBidiLevel = 0;", text)       # the games' left-to-right base
        self.assertIn("gdi.layout(runs, levels, order, NULL)", text)


if __name__ == "__main__":
    unittest.main()
