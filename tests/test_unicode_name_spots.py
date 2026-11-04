"""Long names stay inside the spots the games draw them in (Unicode Text.dll; v1.0.26's live check
found Plant Tycoon's main-menu name sign and its nickname prompt drawing a long name past their
edges). The game's own code runs in Unicorn: its box constructor with the arguments its screens pass,
its setRect / setLimit / setText, and its box draw (Plant 0x40C090, Fish 0x40B680), which measures
the text and places it; the DLL fits it. Windows' fonts are stood in for (raster_glyph and
raster_cluster give wide letters, as CJK, emoji, flags and Arabic are), so a very long name is far
wider than any spot. What is checked is where ink lands on the screen:

* Plant's main-menu name sign (0x42A39A: centred at x 0x29E, y 0x1B8 on the menu picture's sign,
  which spans x 592..746 on the rows the text crosses): the name ends in an ellipsis and nothing is
  drawn outside the sign, for a player's long name and for any long text.
* The nickname prompt's box (Plant 0x41AEB3: rect 0..384, the dialog's width, inside a 10-pixel
  frame of OrangeDlgTileGrid.png; Fish 0x417C15: rect 0..360 inside the dialog's frame), focused (the
  end of the name and the caret after it) and not: nothing is drawn over the dialog's frame.
"""

from __future__ import annotations

import struct
import unittest

import test_unicode_text as T
from test_unicode_text import needs
import test_unicode_names as N

SPOTS = {
    "plant": dict(make=0x40CCB0, set_text=0x40C6F0, limit=0x40C6E0, set_rect=0x40C580, draw=0x40C090,
                  graphics=0x407A90, line_height=0x402450, ticks=0x402060, line=0x407BC0, caret=None),
    "fish": dict(make=0x40C1E0, set_text=0x40BC40, limit=0x40BC30, set_rect=0x40BAD0, draw=0x40B680,
                 graphics=0x407900, line_height=0x4024A0, ticks=0x402090, line=0x407A10, caret=0x40BC50),
}
# The menu picture's sign where the name crosses it (Plant Tycoon, x 0x29E, y 0x1B8).
SIGN = (592, 746)
# The nickname prompt: the box's rect as the game sets it, and the ink's bounds inside the dialog.
PROMPT = {"plant": dict(rect=(0, 100, 384), inside=(10, 374)), "fish": dict(rect=(0, 0x46, 360), inside=(0, 360))}
BG = (10, 20, 30)
# The font each spot draws with (Fish: the prompt's paddington_tt_30; Plant: PTfontsmall).
FONT_SITE = {"fish": 1, "plant": 0}

NAMES = (
    "Zoë Núñez Œuvre שלום مرحبا 中文 日本語 \U0001F600\U0001F44D\U0001F3FD\U0001F1EB\U0001F1F7 " * 4,
    "山田太郎花子" * 20,
    "\U0001F468‍\U0001F469‍\U0001F467\U0001F1EF\U0001F1F5" * 12,
    "مرحبا بالعالم " * 10,
    "Bartholomew Montgomery Fitzgerald the Third of the Northern Reaches of Ørsted and the Isles",
)


def wide_glyph(e) -> int:
    """raster_glyph stood in for: a letter 12 pixels wide, 14 advance (a CJK letter's size)."""
    cp, height, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(6))
    e.uc.mem_write(coverage, b"\xFF" * (12 * height))
    e.write32(w_at, 12)
    e.write32(xoff_at, 1)
    e.write32(adv_at, 14)
    return 1


def wide_cluster(e) -> int:
    """raster_cluster stood in for: an emoji sequence, a flag or a shaped run, 10 pixels a code point."""
    cps_at, n, height, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(7))
    w = 10 * n
    e.uc.mem_write(coverage, b"\xFF" * (w * height))
    e.write32(w_at, w)
    e.write32(xoff_at, 0)
    e.write32(adv_at, w + 2)
    return 1


class SpotCase:
    game = "plant"

    def setUp(self) -> None:
        dll, symbols = T.built(self.game)
        self.symbols = symbols
        self.fde = T.fde.FontDrawEmulator(self.game, screen_w=900, screen_h=600, dll=dll, symbols=symbols)
        self.g = N.Game(self.game, emu=self.fde.emu)
        emu = self.emu = self.fde.emu
        emu.hook(symbols["_raster_glyph"], wide_glyph, 0)
        emu.hook(symbols["_raster_cluster"], wide_cluster, 0)
        va = T.FONT_SITES[self.game][FONT_SITE[self.game]][0]
        push = bytes(emu.uc.mem_read(va, 10))
        table, name_at = struct.unpack_from("<I", push, 1)[0], struct.unpack_from("<I", push, 6)[0]
        name = emu.cstring(name_at).decode("ascii")
        self.font = self.fde.load_font_at(name_at, table, (T.ASSETS[self.game] / "Images" / f"{name}.png").read_bytes())
        # the graphics the box draw asks for (0x407A90 / 0x407900): a holder of the screen's graphics
        self.holder = emu.alloc(0x10)
        emu.write32(self.holder, self.fde.impl)
        emu.hook(SPOTS[self.game]["graphics"], lambda e: self.holder, 0)
        emu.hook(SPOTS[self.game]["ticks"], lambda e: 0, 0)          # the caret blink's clock
        emu.hook(SPOTS[self.game]["line"], self._line, 0x14)          # the caret line (x0, y0, x1, y1, colour)
        emu.write32(self.symbols["_screen_right"], 800)

    def _line(self, e) -> int:
        """The game's line draw (an SDL fill), its pixels painted on the screen picture."""
        x0, y0, x1, y1 = (e.arg(i) for i in range(4))
        img = self.fde.screen_image
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for x in range(min(x0, x1), max(x0, x1) + 1):
                if 0 <= x < img.width and 0 <= y < img.height:
                    img.data[(y * img.width + x) * 4:(y * img.width + x) * 4 + 4] = b"\xff\xff\xff\xff"
        return 0

    def text_at(self, text: bytes) -> int:
        at = self.emu.alloc(len(text) + 1)
        self.emu.uc.mem_write(at, text + b"\0")
        return at

    def make_box(self, x: int, y: int, text: bytes, align: int, ident: int = 0x64) -> tuple[int, int]:
        """(wrapper, box): made by the game's own constructor with the arguments its screens pass."""
        emu = self.emu
        parent = emu.alloc(0x400)
        emu.uc.mem_write(parent, bytes(0x400))
        wrapper = emu.alloc(0x40)
        emu.uc.mem_write(wrapper, bytes(0x40))
        emu.call(SPOTS[self.game]["make"], parent, ident, x, y, self.text_at(text), self.font, align, 0,
                 N.f32(1.0), ecx=wrapper)
        box = emu.read32(wrapper + 0x10)
        emu.write32(box + 0x18, 0)             # no parent: the box's rect is on the screen as it is
        emu.write8(box + 0x2C, 1)              # shown (the screen's add of its child sets it)
        return wrapper, box

    def set_text(self, wrapper: int, text: bytes) -> None:
        self.emu.call(SPOTS[self.game]["set_text"], self.text_at(text), ecx=wrapper)

    def drawn(self, box: int) -> tuple[int, int] | None:
        """The box drawn by the game's own box draw: (leftmost, rightmost) column with ink."""
        self.fde.fill(BG)
        self.emu.call(SPOTS[self.game]["draw"], ecx=box)
        img = self.fde.screen_image
        bg = bytes((*BG, 255))
        cols = [x for x in range(img.width)
                if any(img.data[(y * img.width + x) * 4:(y * img.width + x) * 4 + 4] != bg for y in range(img.height))]
        return (min(cols), max(cols)) if cols else None


class PlantSignTests(SpotCase):
    def test_the_main_menu_sign_keeps_a_long_name_inside_it(self) -> None:
        wrapper, box = self.make_box(0x29E, 0x1B8, b"Player", 1)
        self.assertEqual(self.emu.read32(box + 0x40), 1)                # centred
        for name in NAMES:
            with self.subTest(name=name[:12]):
                self.set_text(wrapper, name.encode("utf-8"))
                ink = self.drawn(box)
                self.assertIsNotNone(ink)
                self.assertGreaterEqual(ink[0], SIGN[0], f"drawn from x {ink[0]}, left of the sign")
                self.assertLessEqual(ink[1], SIGN[1], f"drawn to x {ink[1]}, right of the sign")
                # still centred on the sign's middle, and the name is not dropped
                self.assertLessEqual(abs((ink[0] + ink[1]) / 2 - 0x29E), 8)
                self.assertGreater(ink[1] - ink[0], 60)
        # a short name is the game's own, untouched
        self.set_text(wrapper, b"Ann")
        ink = self.drawn(box)
        self.assertLess(ink[1] - ink[0], 60)

    def test_a_players_short_form_is_the_whole_name_fitted_to_the_sign(self) -> None:
        name = "Wilhelmina Charlotte Ångström-Lindqvist of Malmö and Stockholm"
        short = self.g.type_name(name, slot=1).rstrip(b"\0")
        wrapper, box = self.make_box(0x29E, 0x1B8, b"Player", 1)
        self.set_text(wrapper, short)
        ink = self.drawn(box)
        self.assertGreaterEqual(ink[0], SIGN[0])
        self.assertLessEqual(ink[1], SIGN[1])


class PromptCase(SpotCase):
    def test_the_nickname_prompt_keeps_a_long_name_inside_the_dialog(self) -> None:
        spot = PROMPT[self.game]
        emu = self.emu
        wrapper, box = self.make_box(0, 0, b"", 1, ident=3)
        x0, y0, x1 = spot["rect"]
        h = emu.call(SPOTS[self.game]["line_height"], 0, ecx=self.font)
        rect = emu.alloc(16)
        emu.uc.mem_write(rect, struct.pack("<4i", x0, y0, x1, y0 + h))
        emu.call(SPOTS[self.game]["set_rect"], rect, ecx=wrapper)
        emu.call(SPOTS[self.game]["limit"], 1, 0x20, ecx=wrapper)
        if SPOTS[self.game]["caret"]:
            emu.call(SPOTS[self.game]["caret"], 0x5F, ecx=wrapper)     # the caret "_" (Fish 0x417C70)
        self.assertEqual(emu.read32(box + 8), 0)
        self.assertEqual(emu.read32(box + 0x10), x1)
        for focused in (0, 1):
            for name in NAMES:
                with self.subTest(focused=focused, name=name[:12]):
                    self.set_text(wrapper, name.encode("utf-8"))
                    emu.write8(box + 0x25, focused)                 # the typing focus
                    emu.write8(box + 0x26, focused)                 # the caret shown
                    ink = self.drawn(box)
                    self.assertIsNotNone(ink)
                    self.assertGreaterEqual(ink[0], spot["inside"][0], f"drawn from x {ink[0]}, over the frame")
                    self.assertLessEqual(ink[1], spot["inside"][1], f"drawn to x {ink[1]}, over the frame")
                    self.assertGreater(ink[1] - ink[0], 150)


@needs("plant")
class PlantMenuSignTests(PlantSignTests, unittest.TestCase):
    game = "plant"


@needs("plant")
class PlantPromptTests(PromptCase, unittest.TestCase):
    game = "plant"


@needs("fish")
class FishPromptTests(PromptCase, unittest.TestCase):
    game = "fish"


if __name__ == "__main__":
    unittest.main()
