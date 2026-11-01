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

    def test_tutorial_arrows(self) -> None:
        """0x41F230 run for every message: the message box's arrow direction and point."""
        import screen_emulator as se
        found = {}
        for ident in range(0xA0, 0xC8):
            e = se.ScreenEmulator("plant")
            made = []
            e.emu.hook(0x44D690, lambda em: made.append(tuple(em.arg(i) for i in range(4))) or 0, 0x10)
            for address, pop in ((0x401C90, 8), (0x44DB70, 0), (0x44DAF0, 0), (0x41D830, 8)):
                e.emu.hook(address, lambda em: 0, pop)
            e.emu.call(0x41F230, ident, 0, ecx=e._zeroed(0x70000))
            self.assertEqual(len(made), 1, hex(ident))
            self.assertEqual(made[0][0], ident)
            if made[0][1]:
                found[ident] = made[0][1:]
        self.assertEqual(found, S.PLANT_TUTORIAL)

    def message_box(self, d, ident: int) -> int:
        direction, x, y = S.PLANT_TUTORIAL.get(ident, (0, 0, 0))
        box = d._zeroed(0x200)
        d.run(0x44D690, ident, direction, x, y, this=box)
        d.vcall(d.emu.read32(box + 0x3C), 3, d.emu.read32(box + 0x14), d.emu.read32(box + 0x18), 0x3F800000)
        d.run(0x44DBB0, this=box)
        ok = d.emu.read32(box + 0x74)
        d.vcall(ok, 5, 1)
        d.vcall(ok, 6)
        return box

    def test_message_boxes_on_the_screen(self) -> None:
        """The message box (0x44D690) built, placed and drawn by the game: tiles, text, the
        tutorial's arrow at rest (first frame), OK."""
        for ident in (0x6E, 0x78, 0x8C, 0xCD, 0xA4, 0xA5, 0xAA, 0xB0, 0xB3, 0xB8, 0xC4):
            d = self.emulator()
            self.message_box(d, ident)
            self.assertEqual(recorded(d.draws), composed(self.composer, S.plant_message(self.composer, ident, True)),
                             hex(ident))
            pieces = S.plant_message(self.composer, ident)
            left = min(p.x for p in S.plant_message(self.composer, ident, True) if p.file.endswith("TileGrid.png"))
            self.assertEqual(min(p.x for p in pieces), 0)
            self.assertEqual(left, (800 - max(p.x for p in pieces if p.file) - 64) // 2)

    def test_dialog_backdrop(self) -> None:
        """A modal dialog's draw (0x401E10, second argument 0): the screen under it, then black at
        [0x4653A4] = 0.25 over the whole screen, then the dialog; the rectangle fill 0x407B80 run
        on a screen's pixels."""
        import font_draw_emulator as fde
        import picture_image as pi
        d = self.emulator()
        under, dialog = d._zeroed(0x40), d._zeroed(0x80)
        fills = []
        d.emu.write32(under, d._zeroed(0x40))
        d.emu.write32(d.emu.read32(under) + 0x14, d.thunk_returning(0, "under"))
        d.emu.write32(dialog + 8, under)
        d.emu.write32(dialog + 0x10, d.graphics)
        d.emu.hook(0x407B80, lambda e: fills.append((struct.unpack("<4i", e.uc.mem_read(e.arg(0), 16)),
                                                     [de.f32(e.arg(k)) for k in range(1, 5)])) or 0, 0x14)
        d.emu.hook(0x40B6B0, lambda e: d.draws.append(de.Draw("dialog")) or 0, 0)
        d.run(0x401E10, this=dialog)
        self.assertEqual([x.kind for x in d.draws], ["under", "dialog"])
        self.assertEqual(fills, [((0, 0, 800, 600), [0.0, 0.0, 0.0, 0.25])])
        self.assertEqual(S.plant_alpha(0.25), S.PLANT_SHADE[3])

        emu = fde.FontDrawEmulator("plant", 64, 16)
        pixels = bytes(v for k in range(64 * 16) for v in ((k * 7) % 256, (k * 13) % 256, (k * 29) % 256, 255))
        emu.emu.uc.mem_write(emu.emu.read32(emu.screen + 0x14), pixels)
        emu.emu.hook(0x44E678, lambda e: 0, 0)           # SDL_MapRGB: black
        rect = emu.emu.alloc(16)
        emu.emu.uc.mem_write(rect, struct.pack("<4i", 0, 0, 64, 16))
        holder = emu.emu.alloc(4)
        emu.emu.write32(holder, emu.impl)
        emu.emu.call(0x407B80, rect, *(struct.unpack("<I", struct.pack("<f", v))[0] for v in (0, 0, 0, 0.25)),
                     ecx=holder)
        screen = pi.Image(64, 16)
        screen.data[:] = bytes(emu.surface_image(emu.screen).data)    # (a copy, then the same start)
        start = pi.Image(64, 16)
        start.data[:] = bytes(v for k in range(64 * 16) for v in ((k * 29) % 256, (k * 13) % 256, (k * 7) % 256, 255))
        S._shade(start, (*S.PLANT_SHADE, 64, 16), 0, 0)
        self.assertEqual(bytes(start.data), bytes(screen.data))

    def screen(self, ctor: int, page: int | None = None, player: bool = False) -> list:
        """A screen built and drawn by the game (its constructor, then 0x40B6B0): no pot picked
        (99), $1000, a player named Player."""
        d = self.emulator()
        state = d.game_state
        d.emu.write32(state + 0x63E58, 99)
        d.emu.write32(state + 0x217C, 1000)
        if player:
            d.emu.write32(state + 0x53FB8, 1)
            d.emu.uc.mem_write(state + 8, b"Player\0")
        screen = d._zeroed(0x800)
        d.run(ctor, this=screen)
        if ctor == 0x429D00:
            d.run(0x429C10, this=screen)             # the player's name and Change (0x429C10)
        if page is not None:
            d.emu.write32(screen + 0x1C, page)
            d.run(0x420F00, this=screen)
            d.run(0x420F00, this=screen)
        d.show(screen)
        return recorded(d.draws)

    def test_screens_as_the_game_draws_them(self) -> None:
        """Every picture, word and button of these screens where the game draws them, and nothing
        more: their constructors and draws run (the words' places from the draw calls' pushes)."""
        for ctor, key, kwargs in ((0x424BB0, "screen:greenhouse", {}), (0x429D00, "screen:menu", {"player": True})):
            got = self.screen(ctor, **kwargs)
            want = composed(self.composer, self.composer.pieces(S.by_key("plant")[key]))
            self.assertEqual(sorted(got), sorted(want), key)
        for page in range(6):
            got = self.screen(0x420A00, page=page)
            want = composed(self.composer, S.by_key("plant")[f"screen:help{page + 1}"].pieces)
            self.assertEqual(sorted(got), sorted(want), page)

    def test_screens_words(self) -> None:
        """Screens whose pictures leave out what depends on a game (the seed tray's seeds, the
        Store's shelves): every word the game draws is in the picture, and every piece of the
        picture is drawn by the game."""
        for ctor, key in ((0x4332C0, "screen:seedbox0"), (0x446630, "screen:store")):
            got = self.screen(ctor)
            want = composed(self.composer, S.by_key("plant")[key].pieces)
            self.assertEqual(sorted(x for x in got if x[0] == "text"), sorted(x for x in want if x[0] == "text"), key)
            for x in want:
                self.assertIn(x, got, key)

    def test_greenhouse_replay_button(self) -> None:
        """The greenhouse's text button 8 "Replay Tutorial Instruction" in each state."""
        for frame in (0, 1, 2):
            d = self.emulator()
            screen = d._zeroed(0x800)
            d.run(0x424BB0, this=screen)
            button = next(w for w, ident in d.widgets if ident == 8)
            d.vcall(button, 5, 1)
            d.emu.write32(d.emu.read32(button + 0x10) + 0x30, frame)
            d.draws.clear()
            d.vcall(button, 6)
            self.assertEqual(recorded(d.draws), composed(self.composer, [S.plant_replay(frame)]), frame)

    def test_question_boxes(self) -> None:
        """0x42AB50(text, green, cancel, ...) -> 0x42A700, built, centred and drawn by the game; the
        calls the game makes (0x42A605, 0x4247CC, 0x425AFF, 0x428202, 0x415E7A)."""
        for text, green, cancel in ((0x3E, 1, 1), (0x10A, 0, 1), (0x77, 0, 0), (0x16, 1, 1), (0x10A, 1, 0)):
            d = self.emulator()
            box = d._zeroed(0x200)
            d.run(0x42AB50, text, green, cancel, 0, 0, this=box)
            d.show(box)
            want = composed(self.composer, S.plant_question(self.composer, text, bool(cancel), bool(green), True))
            self.assertEqual(sorted(recorded(d.draws)), sorted(want), hex(text))
        for text, green, cancel in ((0x10A, False, True), (0x77, False, False), (0x3E, True, True)):
            self.assertEqual(S.by_key("plant")[f"question:{text:x}"].name.startswith("Green"), green)

    def test_tooltip(self) -> None:
        """The tooltip control (0x409870) a chemical slot makes, drawn by 0x409B70 once the mouse
        has rested: its two see-through rectangles (0x407AF0) and its text, where the game puts
        them for the mouse at the slot's middle (and at the screen's corner, kept on it)."""
        for chem, doses, mouse in ((0x1A4, 3, (0x21, 0xD5)), (0x1AB, 5, (0x21 + 90, 0xD5)), (0x1A6, 1, (790, 590))):
            d = self.emulator()
            fills, ticks = [], [0]
            d.emu.hook(0x407AF0, lambda e: fills.append((*struct.unpack("<4i", e.uc.mem_read(e.arg(0), 16)), e.arg(1)))
                       or 0, 8)
            d.emu.hook(0x402060, lambda e: ticks[0], 0)

            def point(e, m=mouse):
                e.write32(e.arg(0), m[0])
                e.write32(e.arg(0) + 4, m[1])
                return e.arg(0)
            d.emu.hook(0x407D20, point, 4)
            text = S.fmt(0x46924C, S.ident(chem), S.ident(0x1AD), doses)
            data = self.composer.text_bytes(S.Text((text,)))
            rect = d.emu.alloc(16)
            d.emu.uc.mem_write(rect, struct.pack("<4i", *S.PLANT_CHEM_SLOT))
            tip = d._zeroed(0x20)
            d.run(0x409870, 0x170, rect, 0, d.emu.text(data.decode("cp1252")), 0, 0, 0, this=tip)
            body = d.emu.read32(tip + 0xC)
            d.emu.write8(body + 0x39, 1)
            d.emu.write8(body + 0x3A, 1)
            d.emu.write32(body + 0x3C, 500)             # shown from 500 ms on
            d.run(0x409B70, this=body)                  # resting: follows the mouse
            ticks[0] = 10 ** 6
            d.run(0x409B70, this=body)                  # shown
            pieces = S.plant_tooltip(self.composer, text, mouse)
            want = [(q.x, q.y, q.x + q.fill[4], q.y + q.fill[5], q.fill[3] << 24 | q.fill[2] << 16 | q.fill[1] << 8 | q.fill[0])
                    for q in pieces if q.shade]
            self.assertEqual(fills, want, hex(chem))
            self.assertEqual(recorded(d.draws), composed(self.composer, pieces[2:]), hex(chem))

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


def tip_rig_ready() -> bool:
    try:
        import test_supply_slot_tooltips as tips
    except ImportError:
        return False
    return READY and tips.ready()


@unittest.skipUnless(tip_rig_ready(), "Unicorn, MSVC, the vanilla Fish Tycoon.exe and the DS Store Items DLL")
class FishTooltips(unittest.TestCase):
    """The patcher's supply slot tooltips (native/ftfp_ds_store slot_tooltip) run in Unicorn with
    the game's default font's real widths: the box and the lines where the pictures put them."""

    def test_supply_slot_tooltips(self) -> None:
        import pictures_game_art as ga
        import test_supply_slot_tooltips as tips
        import test_supply_slots as T
        composer = S.Composer(ga.GameArt("fish", FISH))
        for k, rec, lines in ((0, tips.FOOD, (S.sample("Fish Food"),)),
                              (1, T.record(0, 2, 1), (S.ident(0xAE), S.sample("2 doses left"))),
                              (2, T.record(4, 3, 2), (S.ident(0xB6), S.sample("1 use left"))),
                              (3, T.record(5, 3, 3), (S.ident(0xB8), S.sample("1 batch left")))):
            rig = tips.TipRig()
            rig.emu.hook(0x004023D0, lambda e: composer.text_size(0, e.cstring(e.arg(0)))[0], 8)
            rig.put_stock(k, rec)
            said = rig.tip(*T.centre(k))
            pieces = S.fish_tooltip(composer, k, lines)
            self.assertEqual(said, [composer.text_bytes(S.Text((part,))).decode("cp1252") for part in lines])
            fill = pieces[0]
            self.assertEqual(rig.boxes, [(fill.x + 1, fill.y + 1, fill.x + fill.fill[4] - 1, fill.y + fill.fill[5] - 1)])
            texts = [c for c in rig.calls if c[0] == "text"]
            for call, piece in zip(texts, [q for q in pieces if q.text is not None]):
                self.assertEqual(call[2:5], (piece.x, piece.text.x2, piece.y))


if __name__ == "__main__":
    unittest.main()
