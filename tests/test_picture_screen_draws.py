"""Picture Studio's "Screens, bars and buttons" (src/pictures_screens.py) against the games' own draw
code run in Unicorn (tests/draw_emulator.py): each screen, dialog and box is built and drawn by
the game, every draw call recorded (picture, cell, place; words, place, colour), and compared
with the pieces the picture is composed of, placed as pictures_screens.Composer places them.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import capstone  # noqa: F401
    import unicorn  # noqa: F401
    import keystone  # noqa: F401  (the other emulator tests' toolchain; CI has none of the three)
    import draw_emulator as de
    READY = de.available("plant") and de.available("fish")
except ImportError:
    de = None
    READY = False

import pictures_screens as S  # noqa: E402

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
PLANT = VANILLA / "Plant Tycoon"
FISH = VANILLA / "Fish Tycoon"


def white(colour: int) -> int:
    colour &= 0xFFFFFFFF
    return 0xFFFFFFFF if colour >> 24 == 0 else colour


def composed(composer, pieces, skip=()) -> list:
    """The draws a Picture's pieces stand for, as the recorder writes them down."""
    out = []
    for p in pieces:
        if p.text is not None:
            data, x, y, _w, _h = composer.text_place(p)
            if data:
                out.append(("text", data, x, y, white(p.text.colour)))
        elif p.fill is None and p.file not in skip:
            out.append(("tinted" if p.dim else "pic", p.file, p.cell if p.cols * p.rows > 1 else 0, p.x, p.y))
    return out


def recorded(draws, skip=()) -> list:
    out = []
    for d in draws:
        if d.kind == "text":
            if d.text:
                out.append(("text", d.text, d.x, d.y, white(d.colour)))
        elif d.file not in skip:
            out.append(("tinted" if d.kind == "tinted" else "pic", d.file, d.cell, d.x, d.y))
    return out


@unittest.skipUnless(READY, "the vanilla games, Unicorn, capstone and keystone")
class PlantDraws(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import pictures_game_art as ga
        cls.composer = S.Composer(ga.GameArt("plant", PLANT))

    def emulator(self):
        import pictures_plant_data as D
        d = de.DrawEmulator("plant", de.picture_sizes("plant"), D.SPRITES)
        d.measure = self.composer.text_size
        return d

    def options(self, d, speed=10, difficulty=1, windowed=1, sound=1.0, music=0.5, tracks=(1, 0, 0, 0)):
        game = d.run(0x41FCD0)
        d.emu.write8(d.emu.read32(d.graphics) + 0x1E, windowed)
        d.emu.write32(game + 0x534, speed)
        d.emu.write32(game + 0x518, difficulty)
        d.emu.uc.mem_write(game + 0x530, struct.pack("<ff", sound, 0)[:4])
        d.emu.uc.mem_write(game + 0x51C, struct.pack("<f", music))
        for k, ticked in enumerate(tracks):
            d.emu.write32(game + 0x520 + 4 * k, ticked)
        dialog = d._zeroed(0x200)
        done = d.emu.text(d.strings[0x192])
        d.run(0x42AF10, done, 1, this=dialog)
        d.vcall(d.emu.read32(dialog + 0x3C), 3, d.emu.read32(dialog + 0x14), d.emu.read32(dialog + 0x18), 0x3F800000)
        d.run(0x42B710, this=dialog)
        for widget, _id in d.widgets:
            d.vcall(widget, 5, 1)
            d.vcall(widget, 6)
        return dialog

    def test_options_dialog(self) -> None:
        for settings, kwargs in (
                (dict(), dict()),
                (dict(speed=9999, difficulty=2, windowed=0, sound=0.25, music=0.0, tracks=(0, 1, 1, 1)),
                 dict(sound=0.25, music=0.0, windowed=False, difficulty=2, speed=0, tracks=(False, True, True, True))),
                (dict(speed=15, difficulty=0), dict(speed=1, difficulty=0)),
                (dict(speed=2), dict(speed=3))):
            d = self.emulator()
            dialog = self.options(d, **settings)
            self.assertEqual([d.emu.read32(dialog + o) for o in (0x14, 0x18, 0x1C, 0x20)], [80, 44, 720, 556])
            pieces = S.plant_options(self.composer, **kwargs)
            self.assertEqual(recorded(d.draws), composed(self.composer, pieces), settings)

    def test_check_box_ticked_is_its_second_frame(self) -> None:
        d = self.emulator()
        self.options(d, tracks=(0, 1, 0, 1))
        frames = [x.cell for x in d.draws if x.file == "CheckboxStrip.png"]
        self.assertEqual(frames, [0, 1, 0, 1])
        self.assertEqual(S.by_key("plant")["checkbox1"].pieces[0].cell, 1)

    def test_disabled_button_and_its_dim_label(self) -> None:
        """The game's button (0x401B60, 0x401570) drawn by 0x4011B0 with its enabled byte cleared:
        frame 0 tinted, its label in the normal colour and again in [0x47A0FC] at the same place."""
        import pictures_plant_data as D
        for file, text, colour in (("sell_button.png", 0x185, S.PLANT_LILAC), ("widePTButton.png", 0x41, S.PLANT_LILAC),
                                   ("widePTButton02.png", 0x192, 0xFFFFFFFF)):
            d = self.emulator()
            sprite = next(k for k, v in D.SPRITES.items() if v[0] == file)
            button = d._zeroed(0x40)
            d.run(0x401B60, 9, d.sprites[sprite], 115, 407, 0, 0, this=button)
            d.run(0x401570, d.emu.text(d.strings[text]), colour, colour, colour, 0, this=button)
            impl = d.emu.read32(button + 0x10)
            d.emu.write8(impl + 0x29, 0)
            d.vcall(button, 5, 1)
            d.vcall(button, 6)
            self.assertEqual(d.emu.read32(0x47A0FC), S.PLANT_DIM)
            pieces = S.label(file, 115, 407, S.ident(text), colour, dim=True)
            self.assertEqual(recorded(d.draws), composed(self.composer, pieces), file)
            texts = [x for x in d.draws if x.kind == "text"]
            self.assertEqual((texts[0].x, texts[0].y), (texts[1].x, texts[1].y))

    def test_see_through_text_is_drawn_with_the_alpha_blit(self) -> None:
        """A colour less than opaque (the dim label's 0x80646464): the game's text draw, run on the
        real font, blends each letter with its alpha blit into the screen's pixels."""
        import font_draw_emulator as fde
        import picture_image as pi
        import text_maker as tm
        spec = [s for s in tm.FONTS["plant"] if s.table is not None][0]
        for colour in (S.PLANT_DIM, 0x40FFFFFF, 0xC0D7B9BA):
            emu = fde.FontDrawEmulator("plant", 300, 60)
            font = emu.load_font(spec.key, spec.table)
            emu.emu.uc.mem_write(emu.emu.read32(emu.screen + 0x14), bytes((20, 40, 90, 255)) * (300 * 60))
            holder = emu.emu.alloc(4)
            emu.emu.write32(holder, emu.impl)
            emu.emu.call(0x4092A0, emu.emu.text("Sell All"), 10, 10, colour, font, ecx=holder)
            self.assertEqual(emu.blits, [])
            screen = pi.Image(300, 60)
            screen.data[:] = bytes((90, 40, 20, 255)) * (300 * 60)
            self.composer.draw_text(screen, S.say(10, 10, S.sample("Sell All"), colour=colour), b"Sell All", 10, 10)
            self.assertEqual(bytes(screen.data), bytes(emu.surface_image(emu.screen).data), hex(colour))

    def test_main_menu_buttons_run_what_their_labels_say(self) -> None:
        """quit_button.png is labelled "Options" and opens the Options dialog; options_button.png
        is labelled "Quit" and quits (0x42A430, the menu's button handler)."""
        d = self.emulator()
        menu = d._zeroed(0x200)
        d.run(0x429D00, this=menu)
        buttons = {}
        for widget, ident in d.widgets:
            impl = d.emu.read32(widget + 0x10)
            sprite = d.describe(d.emu.read32(impl + 0x3C))[0]
            buttons[sprite] = (ident, d.emu.cstring(d.emu.read32(impl + 0x40)).decode("cp1252"))
        self.assertEqual(buttons["quit_button.png"][1], "Options")
        self.assertEqual(buttons["options_button.png"][1], "Quit")
        happened = []
        d.emu.hook(0x42AF10, lambda e: happened.append(("options dialog", e.cstring(e.arg(0)))) or 0, 8)
        d.emu.hook(0x401C90, lambda e: 0, 8)
        d.emu.hook(0x42B4E0, lambda e: 0, 0)
        d.emu.hook(0x407AA0, lambda e: happened.append(("quit",)) or 0, 0)
        d.emu.hook(0x44A580, lambda e: 0, 4)
        for sprite in ("quit_button.png", "options_button.png"):
            happened.clear()
            d.run(0x42A430, 8, buttons[sprite][0], this=menu)
            self.assertEqual(happened, [("options dialog", b"Done")] if sprite == "quit_button.png" else [("quit",)],
                             sprite)


if __name__ == "__main__":
    unittest.main()
