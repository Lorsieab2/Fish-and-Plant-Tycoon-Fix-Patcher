"""Picture Studio's "Screens, bars and buttons" tab (src/pictures_screens.py): the games' pictures
made of several pieces, put together as the games put them together.

* Fish Tycoon's meter 0x41BF10 runs in Unicorn for many values: its bar and source rectangle are
  pictures_screens.fish_meter's. The meters' and the research bar's places, the 3 x 1 button
  strips and the tank buttons are read back out of the executable.
* The rope box is pixel for pixel what scripts/build_supply_slots_assets.hint_box draws (pinned
  against the stock 0x423280 by tests/test_supply_slot_tooltips.py).
* Plant Tycoon's meters (0x4282BE..0x4282F1, 0x423C70), loading bar (0x44DF60 and its caller),
  the loading screen's logos and the Collections screen's leaf and jar tables (0x482078,
  0x482208) are read back out of the executable.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import picture_image as pi  # noqa: E402
import pictures_screens as S  # noqa: E402
from test_picture_items import FISH, PLANT, UNICORN, capstone, disassemble, same  # noqa: E402

FISH_EXE, PLANT_EXE = FISH / "Fish Tycoon.exe", PLANT / "Plant Tycoon.exe"


def pushes(exe: Path, start: int, end: int) -> list:
    return [int(i.op_str, 0) for i in disassemble(exe, start, end)
            if i.mnemonic == "push" and i.op_str.startswith("0x") or (i.mnemonic == "push" and i.op_str.isdigit())]


class Catalog(unittest.TestCase):
    def test_both_games_have_every_kind(self) -> None:
        for game in ("fish", "plant"):
            pictures = S.pictures(game)
            self.assertEqual(len({p.key for p in pictures}), len(pictures), game)
            cats = S.categories(game)
            self.assertIn("Screens", cats)
            self.assertIn("Buttons", cats)
        fish = S.by_key("fish")
        self.assertEqual(len([k for k in fish if k.startswith("button:")]), 3 * len(S.FISH_BUTTONS))
        plant = S.by_key("plant")
        self.assertEqual(len([k for k in plant if k.startswith("button:")]), 4 * len(S.PLANT_BUTTONS))

    def test_the_tab_is_offered_in_both_games(self) -> None:
        import pictures_fish as pf
        import pictures_plant as pp
        for renderer, subjects in ((pf.FishRenderer(None), None), (pp.Renderer(None), None)):
            subjects = {s.key: s for s in renderer.custom_choices(frozenset(), True, None)}
            self.assertEqual(subjects["screens"].title, "Screens, bars and buttons")
            picked = renderer.refine_choices("screens", {"category": "Buttons"})["picture"]
            self.assertTrue(all(S.by_key(renderer.game)[o.key].category == "Buttons" for o in picked))
            self.assertEqual(renderer.custom_batch("screens"), [], "no game copy: nothing to save")

    def test_meter_formulas(self) -> None:
        self.assertEqual(S.fish_meter(0, 0, 0), [])
        self.assertEqual(S.fish_meter(0, 0, 25)[0].file, "UI_meter_red_bar.bmp")
        self.assertEqual(S.fish_meter(0, 0, 26)[0].src, (0, 0, 33, 6))
        self.assertEqual(S.fish_meter(0, 0, 51)[0].file, "UI_meter_green_bar.bmp")
        self.assertEqual(S.plant_meter("healthmeter.png", 200, 292, 140, 0), [])
        piece = S.plant_meter("healthmeter.png", 200, 292, 140, 500)[0]
        self.assertEqual((piece.y, piece.src), (292 + 70, (0, 70, 15, 140)))
        self.assertEqual(S.loading_bar(2), [])
        self.assertEqual(len(S.loading_bar(100)), 40 + 1)
        self.assertEqual(S.loading_bar(100)[-1], S.Piece("BambooMeterFrame1.png", 239, 500))
        cells = [p.cell for p in S.dialog_tiles("OrangeDlgTileGrid.png", 192, 192)]
        self.assertEqual(cells, [8, 1, 0, 3, 7, 2, 5, 4, 6])


@unittest.skipUnless(UNICORN and capstone and FISH_EXE.is_file(), "the vanilla Fish Tycoon, Unicorn and capstone")
class FishNumbersAreTheGames(unittest.TestCase):
    def test_the_meter_is_0x41bf10(self) -> None:
        from fish_draw_emulator import EXE
        from store_emulator import Emulator
        emu = Emulator(EXE, None, {})
        holder = emu.alloc(4)
        emu.write32(holder, emu.alloc(0x40))
        picked, drawn = [], []
        emu.hook(0x41BD00, lambda e: picked.append(e.arg(0)) or 0x5000, 4)
        emu.hook(0x407900, lambda e: 0x6000, 0)

        def record(e):
            drawn.append((e.arg(1), e.arg(2), struct.unpack("<4i", bytes(e.uc.mem_read(e.arg(3), 16)))))
            return 0
        emu.hook(0x408A50, record, 0x14)
        files = {0x1C: "UI_meter_green_bar.bmp", 0x1D: "UI_meter_yellow_bar.bmp", 0x1E: "UI_meter_red_bar.bmp"}
        for value in (1, 2, 10, 25, 26, 49, 50, 51, 77, 98, 99, 100):
            picked.clear()
            drawn.clear()
            emu.call(0x41BF10, 658, 506, value, ecx=holder)
            (piece,) = S.fish_meter(658, 506, value)
            x, y, rect = drawn[-1]
            self.assertEqual((files[picked[-1]], x, y, rect), (piece.file, piece.x, piece.y, piece.src), value)

    def test_places(self) -> None:
        self.assertEqual(pushes(FISH_EXE, 0x427415, 0x427450), [0x200, 0x89, 0xA6, 0x206, 0x8E],
                         "RESEARCH_PROGRESS_BAR (0xA6) at (137, 512), the meter at (142, 518)")
        code = [f"{i.mnemonic} {i.op_str}" for i in disassemble(FISH_EXE, 0x41D861, 0x41D88C)]
        self.assertIn("add edx, 0x15", code)
        self.assertIn("add edx, 0x2f", code)
        self.assertIn("push 0x292", code)
        self.assertEqual(S.FISH_HEALTH_AT, (0x292, 485 + 0x15))
        self.assertEqual(S.FISH_FED_AT, (0x292, 485 + 0x2F))
        self.assertEqual(pushes(FISH_EXE, 0x401731, 0x401735), [1, 3], "every button picture is a 3 x 1 strip")
        self.assertEqual(pushes(FISH_EXE, 0x41D6E0, 0x41D720), [0, 0x16, 0, 0x17])


@unittest.skipUnless(capstone and PLANT_EXE.is_file(), "the vanilla Plant Tycoon and capstone")
class PlantNumbersAreTheGames(unittest.TestCase):
    def test_meters_and_loading(self) -> None:
        self.assertEqual(pushes(PLANT_EXE, 0x4282BE, 0x4282D0), [1, 0x124, 0xC8])
        self.assertEqual(pushes(PLANT_EXE, 0x4282E5, 0x4282F0), [2, 0x124, 0xD])
        self.assertEqual(S.PLANT_HEALTH[1:3], (0xC8, 0x124))
        self.assertEqual(S.PLANT_WATER[1:3], (0xD, 0x124))
        code = [f"{i.mnemonic} {i.op_str}" for i in disassemble(PLANT_EXE, 0x423C70, 0x423CD0)]
        for line in ("mov esi, 1", "cmp esi, 0x3e8", "and eax, 0x70", "add eax, 0x2d", "mov eax, 0x10624dd3"):
            self.assertIn(line, code)
        self.assertEqual(pushes(PLANT_EXE, 0x423167, 0x42319A), [0x64, 0x28, 0xE3, 7, 0x64, 0x190, 0x258, 8],
                         "logo1 (7) at (227, 40), ldw_logo (8) at (600, 400)")
        self.assertEqual(pushes(PLANT_EXE, 0x423146, 0x423160), [6, 0x1F4, 0xF0, 3],
                         "loading.jpg (6), then the bar: mode 3 at (240, 500)")
        code = [f"{i.mnemonic} {i.op_str}" for i in disassemble(PLANT_EXE, 0x44DF60, 0x44DF85)]
        self.assertIn("cmp ecx, 0x64", code)
        self.assertIn("mov ecx, 1", code)

    def test_collections_tables(self) -> None:
        import pefile
        pe = pefile.PE(str(PLANT_EXE), fast_load=True)
        data = PLANT_EXE.read_bytes()

        def read(va, n):
            at = pe.get_offset_from_rva(va - 0x400000)
            return data[at:at + n]
        leaves = struct.unpack("<96i", read(0x482078, 96 * 4))
        self.assertEqual(S.LEAVES, tuple((leaves[2 * k], leaves[2 * k + 1]) for k in range(48)))
        jars = struct.unpack("<144i", read(0x482208, 144 * 4))
        self.assertEqual(S.JARS, tuple((jars[3 * k], jars[3 * k + 1]) for k in range(48)))
        self.assertEqual([jars[3 * k + 2] for k in range(48)], list(range(48)), "record k is bug k")


@unittest.skipUnless((FISH / "Assets" / "ft.dat").is_file() and (PLANT / "Images").is_dir(), "the vanilla games")
class Pictures(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import pictures_game_art as ga
        cls.fish = ga.GameArt("fish", FISH)
        cls.plant = ga.GameArt("plant", PLANT)

    def test_every_piece_is_in_the_games(self) -> None:
        for art in (self.fish, self.plant):
            composer = S.Composer(art)
            for picture in S.pictures(art.game):
                for piece in picture.pieces:
                    if not piece.fill:
                        composer.image(piece.file)

    def test_every_picture_but_the_screens_renders(self) -> None:
        for art in (self.fish, self.plant):
            for picture in S.pictures(art.game):
                if picture.category != "Screens":
                    image = S.render(art, {"picture": picture.key})
                    self.assertGreater(image.width, 0, picture.key)
        for art, key in ((self.fish, "screen:tank1"), (self.plant, "screen:greenhouse")):
            self.assertEqual((S.render(art, {"picture": key}).width, S.render(art, {"picture": key}).height), (800, 600))

    def test_pinned(self) -> None:
        import picture_formats as F
        composer = S.Composer(self.fish)
        frame = composer.image("RESEARCH_PROGRESS_BAR.png")
        bar = composer.image("UI_meter_green_bar.bmp")
        expected = pi.Image(141, 19)
        expected.draw(frame, 0, 0)
        expected.draw(bar.sub(0, 0, 66, 6), 5, 6)
        same(self, S.render(self.fish, {"picture": "research51"}), expected, "research at 51")
        plant = S.Composer(self.plant)
        meter = plant.image("healthmeter.png")
        same(self, S.render(self.plant, {"picture": "health50"}), meter.sub(0, 70, 15, 70), "health at 50")
        self.assertIsNotNone(F)

    def test_rope_box_is_the_tooltip_script_s(self) -> None:
        try:
            from PIL import Image as PIL
        except ImportError:
            self.skipTest("Pillow")
        import build_supply_slots_assets as B
        composer = S.Composer(self.fish)
        art = {name: PIL.frombytes("RGBA", (composer.image(name).width, composer.image(name).height),
                                   bytes(composer.image(name).data)) for name in S.ROPE_FILES}
        art.update({name.lower(): art[name] for name in S.ROPE_FILES})
        for w, h in ((44, 54), (120, 54), (300, 120), (100, 32)):
            screen = PIL.new("RGBA", (400, 200), (0, 0, 0, 0))
            B.hint_box(art, screen, (20, 20, 20 + w, 20 + h))
            ours = S.Composer(self.fish).render(S.Picture("x", "x", "x", tuple(S.rope_box(20, 20, 20 + w, 20 + h)),
                                                          canvas=(400, 200)))
            self.assertEqual(bytes(ours.data), screen.tobytes(), (w, h))
