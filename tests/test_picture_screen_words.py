"""Picture Studio's "Screens, bars and buttons" words (src/pictures_screens.py): the games' own text
on the composed screens, buttons and message boxes.

* The words, their places, colours, fonts and alignment are read back out of the executables:
  Plant Tycoon's button labels by running the screens' constructors in Unicorn
  (tests/screen_emulator.py records each button and the label it is given), Fish Tycoon's options
  popup the same way, the rest from the draw calls' pushes.
* The text width and height the layouts are worked out from are the games' own functions run in
  Unicorn (Fish 0x4023D0 / 0x4024A0, Plant 0x402380 / 0x402450) on the real fonts, and the words
  are drawn as the game's draw 0x4087E0 draws them (tests/font_draw_emulator.py), and placed as
  its left / centred / right / between wrappers place them.
* Static checks name what is read without running: CheckboxStrip's frame count and the message
  boxes' sizing constants.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import picture_image as pi  # noqa: E402
import pictures_screens as S  # noqa: E402
import screen_emulator as se  # noqa: E402
from test_picture_items import FISH, PLANT, UNICORN, capstone, disassemble  # noqa: E402

FISH_EXE, PLANT_EXE = FISH / "Fish Tycoon.exe", PLANT / "Plant Tycoon.exe"
GAMES = (FISH / "Assets" / "ft.dat").is_file() and (PLANT / "Images").is_dir()
ONE = struct.unpack("<I", struct.pack("<f", 1.0))[0]

SAMPLES = {
    "fish": (b"Your cash: $1000", b"Age: ", b"Fish for sale: ", b"#1/7", b"Hello\nWorld, longer line",
             b"Welcome to Fish Tycoon!\n\nYour goal", b"", b"Status: Pregnant"),
    "plant": (b"No plant selected", b"CASH", b"$1000", b"Sell All", b"Take Snapshot",
              b"Now drag a seed from the Seed Tray\nto the wet soil that you prepared. \n", b"Ok\n"),
}


def code(exe: Path, start: int, end: int) -> list:
    return [f"{i.mnemonic} {i.op_str}" for i in disassemble(exe, start, end)]


class Formulas(unittest.TestCase):
    def test_c_division(self) -> None:
        self.assertEqual((S.cdiv(7, 2), S.cdiv(-7, 2), S.cdiv(-1, 2), S.cdiv(6, 4)), (3, -3, 0, 1))

    def test_catalog(self) -> None:
        fish, plant = S.by_key("fish"), S.by_key("plant")
        for key in ("screen:tank1fish", "screen:tank1stopped", "screen:options", "screen:tip1c",
                    "screen:supplies:research", "screen:sell:picked", "screen:trophy"):
            self.assertIn(key, fish)
        for key in ("screen:greenhouse:pot", "message:aa", "question:10a", "checkbox1"):
            self.assertIn(key, plant)
        green = plant["screen:greenhouse"].pieces
        self.assertIn(S.Piece("sell_button.png", 115, 407, cols=3, rows=1), green, "Sell All")
        pressed = S.label("widePTButton.png", 10, 20, S.ident(0x12), frame=2)
        self.assertEqual((pressed[1].x, pressed[1].y), (12, 22), "a pressed label is 2 right and down")


@unittest.skipUnless(GAMES, "the vanilla games")
class Words(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import pictures_game_art as ga
        cls.fish = S.Composer(ga.GameArt("fish", FISH))
        cls.plant = S.Composer(ga.GameArt("plant", PLANT))

    def test_text_is_read_from_the_executable(self) -> None:
        self.assertEqual(self.fish.text_bytes(S.FISH_CASH.text), b"Your cash: $1000")
        self.assertEqual(self.fish.text_bytes(S.Text((S.at(0x44C364),))), b"#1/7")
        self.assertEqual(self.fish.text_bytes(S.Text((S.fmt(0x44C230, S.ident(0xAD), 25),))), b"Price:  $25")
        self.assertEqual(self.plant.text_bytes(S.Text((S.fmt(0x4691BC, S.ident(0x18A), 12),))), b"Buds in 12 Min.")
        self.assertEqual(self.plant.text_bytes(S.Text((S.at(0x469850),))), b"Change Scene")

    def test_screens_with_words_render(self) -> None:
        for composer, keys in ((self.fish, ("screen:tank1fish", "screen:options", "screen:tipec", "screen:trophy")),
                               (self.plant, ("screen:greenhouse", "screen:menu", "message:cd", "question:3e"))):
            for key in keys:
                image = composer.render(S.by_key(composer.art.game)[key])
                self.assertGreater(image.width, 100, key)

    def test_message_box_grows_with_its_text(self) -> None:
        short = self.plant.render(S.by_key("plant")["message:6e"])
        long_ = self.plant.render(S.by_key("plant")["message:cd"])
        self.assertLess(short.width, long_.width)
        self.assertEqual(short.width % 64, 0)


@unittest.skipUnless(UNICORN and GAMES, "the vanilla games and Unicorn")
class TheGamesTextCode(unittest.TestCase):
    """The width / height / draw / placement functions run in Unicorn."""

    WIDTH = {"fish": (0x4023D0, 0x4024A0), "plant": (0x402380, 0x402450)}

    @classmethod
    def setUpClass(cls) -> None:
        import pictures_game_art as ga
        cls.composers = {"fish": S.Composer(ga.GameArt("fish", FISH)), "plant": S.Composer(ga.GameArt("plant", PLANT))}

    def _emulator(self, game: str, font: int):
        import font_draw_emulator as fde
        import text_maker as tm
        emu = fde.FontDrawEmulator(game, 900, 200)
        spec = [s for s in tm.FONTS[game] if s.table is not None][font]
        return emu, emu.load_font(spec.key, spec.table)

    def test_width_and_height(self) -> None:
        for game, fonts in (("fish", (0, 1, 2)), ("plant", (0,))):
            width, height = self.WIDTH[game]
            for font in fonts:
                emu, wrapper = self._emulator(game, font)
                for text in SAMPLES[game]:
                    at = emu.emu.text(text.decode("latin-1"))
                    got = (emu.emu.call(width, at, ONE, ecx=wrapper), emu.emu.call(height, at, ecx=wrapper))
                    self.assertEqual(self.composers[game].text_size(font, text), got, (game, font, text))

    def test_drawn_and_placed_as_the_game_does(self) -> None:
        # (game, wrapper address, piece, the wrapper's own arguments after the text)
        cases = (("fish", 0x408B80, S.say(10, 20, S.ident(7), colour=0xFF66CCFF), (10, 20)),
                 ("fish", 0x408BE0, S.say(300, 20, S.ident(0xF0), font=1, align="centre"), (300, 20)),
                 ("fish", 0x408B90, S.say(400, 20, S.ident(1), align="right"), (400, 20)),
                 ("fish", 0x408C30, S.say(0, 40, S.ident(0), align="between", x2=800), (0, 800, 40)),
                 ("plant", 0x4092B0, S.say(118, 30, S.ident(0x18D), colour=0xFF000000, align="centre"), (118, 30)),
                 ("plant", 0x4092A0, S.say(13, 30, S.ident(0x3F)), (13, 30)))
        for game, wrapper_at, piece, args in cases:
            composer = self.composers[game]
            emu, font = self._emulator(game, piece.text.font)
            emu.fill((40, 60, 90))
            holder = emu.emu.alloc(4)
            emu.emu.write32(holder, emu.impl)
            data = composer.text_bytes(piece.text)
            at = emu.emu.text(data.decode("latin-1"))
            emu.emu.call(wrapper_at, at, *args, piece.text.colour, font, ecx=holder)
            screen = pi.Image(900, 200)
            screen.data[:] = bytes((40, 60, 90, 255)) * (900 * 200)
            _data, x, y, _w, _h = composer.text_place(piece)
            composer.draw_text(screen, piece, data, x, y)
            self.assertEqual(bytes(screen.data), bytes(emu.screen_image.data), (game, hex(wrapper_at)))
            self.assertEqual((emu.blits[0].x, emu.blits[0].y), (x, y), (game, hex(wrapper_at)))


@unittest.skipUnless(se.available("plant") and se.available("fish"), "the vanilla games, Unicorn, capstone, pefile")
class Constructors(unittest.TestCase):
    """The screens' constructors run in Unicorn: each button, its place and its label."""

    def _plant(self, ctor: int) -> list:
        emu = se.ScreenEmulator("plant")
        try:
            emu.construct(ctor)
        except Exception:                       # noqa: BLE001  a constructor may stop after its buttons
            pass
        return [b for b in emu.order if b.label]

    def _part(self, part) -> str:
        import translation_strings as ts
        exe = PLANT_EXE.read_bytes()
        if part[0] == "id":
            return {s.id: s.english for s in ts.read_table("plant", exe)}[part[1]]
        at = ts._offset(exe, part[1])
        return exe[at:exe.index(b"\0", at)].decode("cp1252")

    def test_plant_tabs(self) -> None:
        for ctor, labels in ((0x424BB0, S.GREENHOUSE_TABS), (0x4332C0, S.SEEDBOX_TABS), (0x446630, S.STORE_TABS),
                             (0x418E70, S.COLLECTIONS_TABS)):
            tabs = {b.x: b for b in self._plant(ctor) if b.y == S.TAB_Y}
            for k, x in enumerate(S.TAB_XS):
                if labels[k] is None:
                    self.assertNotIn(x, tabs, hex(ctor))
                else:
                    self.assertEqual(tabs[x].label, self._part(labels[k]), (hex(ctor), x))
                    self.assertEqual(tabs[x].colours[0], S.PLANT_LILAC)

    def test_plant_buttons(self) -> None:
        import pictures_plant_data as D
        found = {(D.SPRITES[b.sprite][0] if b.sprite is not None else None, b.x, b.y, b.label)
                 for ctor in (0x424BB0, 0x448630, 0x420A00, 0x421880, 0x418E70, 0x429D00) for b in self._plant(ctor)}
        expected = set()
        for key in ("screen:greenhouse", "screen:arrangement1", "screen:help1", "screen:story2", "screen:collections0",
                    "screen:menu"):
            pieces = S.by_key("plant")[key].pieces
            for k, piece in enumerate(pieces):
                if piece.text is not None and piece.text.align == "button":
                    button = pieces[k - 1]
                    expected.add((button.file, button.x, button.y, self._part(piece.text.parts[0])))
        self.assertTrue(expected)
        self.assertEqual(expected - found, set())
        self.assertIn(("sell_button.png", 115, 407, "Sell All"), found)

    def test_fish_options(self) -> None:
        emu = se.ScreenEmulator("fish")
        emu.record(0x40A7C0, 0x20, 8)           # a radio button (id, sprite, x, y, parent, text, colour, font)
        emu.record(0x40C110, 0x1C, 7)           # a text (parent, x, y, text, align, font, scale)
        try:
            emu.construct(0x422530)
        except Exception:                       # noqa: BLE001  it stops after its widgets
            pass
        radios = [(emu.emu.cstring(a[5]), a[2], a[3]) for at, _t, a in emu.calls if at == 0x40A7C0]
        heads = [(emu.emu.cstring(a[3]), a[1], a[2], ("left", "centre")[a[4]]) for at, _t, a in emu.calls
                 if at == 0x40C110]
        import translation_strings as ts
        strings = {s.id: s.english.encode("cp1252") for s in ts.read_table("fish", FISH_EXE.read_bytes())}
        self.assertEqual(radios, [(strings[t], x, y) for t, x, y, _on in S.FISH_OPTIONS_RADIOS])
        self.assertEqual(heads, [(strings[t], x, y, al) for t, x, y, al in S.FISH_OPTIONS_HEADERS])


@unittest.skipUnless(capstone and PLANT_EXE.is_file() and FISH_EXE.is_file(), "the vanilla games and capstone")
class StaticReading(unittest.TestCase):
    def test_checkbox_strip_has_two_frames(self) -> None:
        lines = code(PLANT_EXE, 0x42AF58, 0x42AFFB)
        self.assertIn("mov ebx, 2", lines)
        self.assertFalse([line for line in lines[1:-4] if line.startswith(("mov ebx", "xor ebx", "pop ebx"))])
        self.assertEqual(lines[-4:-1], ["push 1", "push ebx", "push 0x4693ac"], "CheckboxStrip.png: 2 x 1")

    def test_message_box_sizes(self) -> None:
        lines = code(PLANT_EXE, 0x44D7BD, 0x44D7C6)
        self.assertEqual(lines, ["push 0x34", "add edi, 0x48", "lea ebx, [ebx + ebp*2 + 0x24]"])
        self.assertIn("add eax, 0x24", code(PLANT_EXE, 0x44D832, 0x44D845))
        self.assertIn("add ebp, 0x3c", code(PLANT_EXE, 0x42A8B6, 0x42A8DB))
        self.assertIn("add eax, 0x14", code(PLANT_EXE, 0x42A90D, 0x42A929))
        self.assertIn("add ebx, 0x28", code(FISH_EXE, 0x4222CB, 0x4222F0))
        self.assertIn("lea ebp, [eax + ecx + 0x3c]", code(FISH_EXE, 0x4222FF, 0x42230F))
        self.assertEqual(S.FISH_OPTIONS_SIZE, (0x10E, 0x15E))
        self.assertEqual(code(FISH_EXE, 0x422578, 0x422582), ["push 0x15e", "push 0x10e"])


if __name__ == "__main__":
    unittest.main()
