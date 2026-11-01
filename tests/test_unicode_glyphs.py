"""Full Unicode in the games (Unicode Text.dll, both games): UTF-8 text drawn and measured letter
by letter, and any letter typed. The DLL's own code and the game's run in Unicorn against the
vanilla executables; Windows' fonts are stood in for (the DLL's raster_glyph is replaced by a
known picture), so what is checked is where each letter comes from and where it goes.

* A letter the game's font has (ASCII, Latin-1 as UTF-8 or as its old byte, a Windows-1252
  letter such as €) is drawn by the game's own code, pixel for pixel as before.
* Any other letter is a run-time glyph in the text's colour, placed at the pen and advanced by
  its own width plus the font's spacing; the measure agrees. A letter no font has is '?'.
* In a text box a letter goes in as its UTF-8 bytes, whole or not at all; Backspace takes off a
  whole letter; a name box stops at 300 letters.
"""

from __future__ import annotations

import struct
import unittest

import test_unicode_text as T
from test_unicode_text import E, needs
import test_unicode_names as N

NO_FONT = 0xE000          # the stand-in fonts have no letter for it


def fake_glyph(cp: int) -> tuple[int, int, int]:
    """(width, left edge from the pen, advance) of the stand-in letter."""
    w = 4 + cp % 3
    return w, 1, w + 2


class GlyphCase:
    game = "fish"
    COLOUR = 0xFF40D0FF                 # 0xAABBGGRR

    def setUp(self) -> None:
        dll, symbols = T.built(self.game)
        self.symbols = symbols
        self.fde = T.fde.FontDrawEmulator(self.game, screen_w=900, dll=dll, symbols=symbols)
        self.g = N.Game(self.game, emu=self.fde.emu)
        self.rasters = []
        self.fde.emu.hook(symbols["_raster_glyph"], self._raster, 0)
        va = T.FONT_SITES[self.game][0][0]
        push = bytes(self.fde.emu.uc.mem_read(va, 10))
        table, name_at = struct.unpack_from("<I", push, 1)[0], struct.unpack_from("<I", push, 6)[0]
        name = self.fde.emu.cstring(name_at).decode("ascii")
        self.font = self.fde.load_font_at(name_at, table, (T.ASSETS[self.game] / "Images" / f"{name}.png").read_bytes())
        inner = self.fde.emu.read32(self.font + 4)
        self.height = self.fde.emu.read32(inner + 4)
        self.spacing = self.fde.emu.read32(inner + 8, signed=True)

    def _raster(self, e) -> int:
        cp, height, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(6))
        self.rasters.append((cp, height))
        if cp == NO_FONT:
            return 0
        w, xoff, adv = fake_glyph(cp)
        e.uc.mem_write(coverage, b"\xFF" * (w * height))
        e.write32(w_at, w)
        e.write32(xoff_at, xoff)
        e.write32(adv_at, adv)
        return 1

    def text_at(self, raw: bytes) -> int:
        at = self.fde.emu.alloc(len(raw) + 1)
        self.fde.emu.uc.mem_write(at, raw + b"\0")
        return at

    def draw(self, raw: bytes, own: bool = False, x: int = 5, colour: int | None = None, fill: bool = True) -> bytes:
        if fill:
            self.fde.fill((10, 20, 30))
        target = self.symbols["_orig_draw"] if own else N.GAMES[self.game]["draw"]
        self.fde.emu.call(target, self.text_at(raw), x, 7, self.COLOUR if colour is None else colour, self.font,
                          ecx=self.fde.impl)
        return bytes(self.fde.screen_image.data)

    def width(self, raw: bytes, own: bool = False) -> int:
        target = self.symbols["_orig_width"] if own else N.GAMES[self.game]["width"]
        return self.fde.emu.call(target, self.text_at(raw), N.f32(1.0), ecx=self.font)

    def paint(self, x: int, y: int, w: int, h: int) -> None:
        c = self.COLOUR
        rgb = bytes((c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF, 255))
        img = self.fde.screen_image
        for row in range(y, y + h):
            for col in range(x, x + w):
                if 0 <= col < img.width and 0 <= row < img.height:
                    at = (row * img.width + col) * 4
                    img.data[at: at + 4] = rgb

    def test_the_games_letters_are_drawn_by_the_game(self) -> None:
        for text, old in (("Renée Ørsted", "Renée Ørsted".encode("latin-1")), ("€5 „Grüße“ …", "€5 „Grüße“ …".encode("cp1252")),
                          ("Hello", b"Hello")):
            with self.subTest(text=text):
                self.assertEqual(self.draw(text.encode("utf-8")), self.draw(old, own=True))
                self.assertEqual(self.width(text.encode("utf-8")), self.width(old, own=True))
                # the old one-byte text reads the same
                self.assertEqual(self.draw(old), self.draw(old, own=True))
        self.assertEqual(self.rasters, [])

    def test_other_letters_are_run_time_glyphs_at_the_pen(self) -> None:
        for cp in (0x3042, 0x1F41F, 0x12000, 0x0130, 0xAC00):
            with self.subTest(cp=hex(cp)):
                text = "A" + chr(cp) + "b"
                w, xoff, adv = fake_glyph(cp)
                shown = self.draw(text.encode("utf-8"))
                self.assertIn((cp, self.height), self.rasters)
                a_end = 5 + self.width(b"A", own=True) + self.spacing
                self.fde.fill((10, 20, 30))
                self.draw(b"A", own=True, fill=False)
                self.draw(b"b", own=True, x=a_end + adv + self.spacing, fill=False)
                self.paint(a_end + xoff, 7, w, self.height)
                self.assertEqual(shown, bytes(self.fde.screen_image.data))
                self.assertEqual(self.width(text.encode("utf-8")), self.width(b"Ab", own=True) + adv + self.spacing)

    def test_a_letter_no_font_has_is_a_question_mark(self) -> None:
        text = ("x" + chr(NO_FONT) + "y").encode("utf-8")
        self.assertEqual(self.draw(text), self.draw(b"x?y", own=True))
        self.assertEqual(self.width(text), self.width(b"x?y", own=True))

    def test_lines(self) -> None:
        text = ("a" + chr(0x3042) + "\nbc").encode("utf-8")
        w, _xoff, adv = fake_glyph(0x3042)
        self.assertEqual(self.width(text), max(self.width(b"a", own=True) + self.spacing + adv,
                                               self.width(b"bc", own=True)))


def box_with(emu, limit: int, text: bytes = b"") -> tuple[int, int]:
    box = emu.alloc(0x60)
    emu.uc.mem_write(box, bytes(0x60))
    focus = emu.alloc(0x10)
    emu.write8(focus + 8, 1)
    buffer = emu.alloc(limit + 8)
    emu.uc.mem_write(buffer, text + b"\0")
    emu.write8(box + 0x25, 1)
    emu.write32(box + 0x1C, focus)
    emu.write32(box + 0x28, limit)
    emu.write32(box + 0x30, buffer)
    return box, buffer


class TypingCase:
    game = "fish"
    HANDLER = {"fish": (0x40BFC0, T.FISH_EVENTS_GET, 0x402030), "plant": (0x40CA90, T.PLANT_EVENTS_GET, 0x402020)}

    def type(self, chars, limit: int = 0x20, text: bytes = b"") -> bytes:
        g = N.Game(self.game)
        emu = g.emu
        handler, events, changed = self.HANDLER[self.game]
        emu.hook(events, lambda e: 0x0BAD0000, 0)
        emu.hook(changed, lambda e: 0, 8)
        box, buffer = box_with(emu, limit, text)
        for ch in chars:
            self.assertEqual(emu.call(handler, 5, 0, ch, ecx=box) & 0xFF, 1)
        return emu.cstring(buffer)

    def test_letters_go_in_whole(self) -> None:
        name = "山田 Ölçer 🐟 𒀀 İstanbul"
        self.assertEqual(self.type([ord(c) for c in name], limit=200), name.encode("utf-8"))
        # a letter that does not fit whole stays out
        self.assertEqual(self.type([0x61, 0x62, 0x3042], limit=4), b"ab")
        self.assertEqual(self.type([0x61, 0x3042], limit=4), "aあ".encode("utf-8"))
        # control characters, C1 controls and lone surrogates are dropped
        self.assertEqual(self.type([0x61, 0x7F, 0x85, 0xD800, 0x110000, 0x62], limit=40), b"ab")

    def test_backspace_takes_a_whole_letter(self) -> None:
        self.assertEqual(self.type([0x3042, 0x1F41F, 8], limit=40), "あ".encode("utf-8"))
        self.assertEqual(self.type([8], limit=40, text="Zoë".encode("utf-8")), b"Zo")
        self.assertEqual(self.type([8, 8, 8], limit=40, text="é".encode("utf-8")), b"")
        # an old one-byte name loses one letter (its byte) too
        self.assertEqual(self.type([8], limit=40, text=b"Ren\xe9"), b"Ren")

    def test_a_name_box_stops_at_300_letters(self) -> None:
        stored = self.type([0x3042] * 301, limit=1200)
        self.assertEqual(stored, "あ".encode("utf-8") * 300)


INI = "Unicode Text.ini"


class SystemFontCase:
    """Use Unicode Font: the same DLL told by "Unicode Text.ini" beside it (written by the patcher) to
    draw every letter with the chosen font; the game's fonts stay as they are."""
    game = "fish"

    def test_the_ini_sets_the_mode_and_the_font(self) -> None:
        dll, symbols = T.built(self.game)
        ini = T.GAME_DIR[self.game] + T.DLL_FOLDER[self.game] + INI
        fde = T.fde.FontDrawEmulator(self.game, screen_w=900, dll=dll, symbols=symbols)
        emu = fde.emu
        files = T.hook_windows(emu, self.game, present=set(),          # no extended font pictures needed
                               existing={ini: "; patcher\r\n[Unicode Text]\r\nMode=system\r\nFont=Comic Sans MS\r\n".encode()})
        stock = T.code_bytes(emu, [(va, 10) for va, _k in T.FONT_SITES[self.game]])
        self.assertEqual(T.startup(emu, symbols), 1)
        self.assertIn("Use Unicode Font", files["text"])
        self.assertEqual(emu.read32(symbols["_system_font"]), 1)
        self.assertEqual(emu.wstring(symbols["_chosen_font"]), "Comic Sans MS")
        # the game's fonts are left as they are
        self.assertEqual(T.code_bytes(emu, [(va, 10) for va, _k in T.FONT_SITES[self.game]]), stock)
        # every letter, ASCII too, comes from the run-time glyphs
        rasters = []

        def raster(e) -> int:
            cp, height, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(6))
            rasters.append(cp)
            e.uc.mem_write(coverage, b"\xFF" * (3 * height))
            e.write32(w_at, 3)
            e.write32(xoff_at, 0)
            e.write32(adv_at, 4)
            return 1
        emu.hook(symbols["_raster_glyph"], raster, 0)
        key = T.FONT_SITES[self.game][0][1]
        spec = next(s for s in T.tm.FONTS[self.game] if s.key == key)
        font = fde.load_font({"font_triplex_sanslightlin_bold_16pt": "FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT"}.get(key, key),
                             spec.table)
        fde.draw(font, "Hi 山".encode("utf-8"), 4, 4, 0xFFFFFFFF)
        self.assertEqual(rasters, [ord("H"), ord("i"), ord(" "), 0x5C71])

    def test_no_ini_is_the_in_game_fonts(self) -> None:
        dll, symbols = T.built(self.game)
        emu = E.Emulator(T.EXES[self.game], dll, symbols)
        emu.uc.mem_map(0, 0x1000)
        T.hook_windows(emu, self.game)
        self.assertEqual(T.startup(emu, symbols), 1)
        self.assertEqual(emu.read32(symbols["_system_font"]), 0)


class PatcherIniTests(unittest.TestCase):
    def test_the_patcher_writes_the_mode_and_the_font(self) -> None:
        import fish_patcher
        import tycoon_fix_patcher as combined
        for game, folder in (("fish", "Fish Tycoon Fix Patcher DLLs"), ("plant", "Plant Tycoon Fix Patcher DLLs")):
            manifest = combined.load_manifest(game)
            dest, data = fish_patcher.unicode_ini(manifest, {"unicode_system_font", "fix_vanilla_bugs"}, "Comic Sans MS")
            self.assertEqual(dest, f"{folder}/Unicode Text.ini")
            self.assertIn(b"Mode=system\r\nFont=Comic Sans MS\r\n", data)
            _dest, data = fish_patcher.unicode_ini(manifest, {"unicode_ingame_fonts"}, None)
            self.assertIn(b"Mode=ingame\r\nFont=Segoe UI\r\n", data)
            self.assertIsNone(fish_patcher.unicode_ini(manifest, {"fix_vanilla_bugs"}, "Arial"))
        self.assertEqual(fish_patcher.clean_font_name("  Yu  Gothic\r\nMode=x "), "Yu Gothic Mode x")
        self.assertEqual(fish_patcher.clean_font_name(""), "Segoe UI")
        self.assertEqual(fish_patcher.clean_font_name("游ゴシック"), "游ゴシック")


@needs("fish")
class FishSystemFontTests(SystemFontCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantSystemFontTests(SystemFontCase, unittest.TestCase):
    game = "plant"


@needs("fish")
class FishGlyphTests(GlyphCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantGlyphTests(GlyphCase, unittest.TestCase):
    game = "plant"


@needs("fish")
class FishTypingTests(TypingCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantTypingTests(TypingCase, unittest.TestCase):
    game = "plant"


if __name__ == "__main__":
    unittest.main()
