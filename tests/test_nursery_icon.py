"""The Extra Nursery's store item (5 extra nurseries): the game's golden pot, pre-scaled.

The plant store's draw (0x4208F0) ignores its scale argument, so the 0.84 the item used to pass drew
goldpot.png (sprite 0x2C) at its full 76 x 64, taller than the Time Warp clock and Add Money's coins
beside it. The pot is now row 20 (frame 40) of the Upgrades DLL's chemicals sheet, the clock's visible
height, standing on the clock's and the coins' bottom line, drawn at scale 1; its click and tooltip
rectangle is its picture's.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import store_emulator as E
    from PIL import Image
except ImportError:
    E = None

SHEET = ROOT / "assets" / "plant_tycoon_upgrades" / "Images" / "Chemicals_Grid_upgrades.png"
SOURCE = ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c"
EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
SHEET_CHEMICALS = 0xB3
RECT = (453, 305, 514, 356)                 # ftfp_plant_upgrades.c, the Extra Nursery's rect (inclusive)


def _ready() -> bool:
    return E is not None and EXE is not None and EXE.is_file() and E.toolchain_ready()


def cell(sheet, frame: int):
    return sheet.crop(((frame % 2) * 70, (frame // 2) * 70, (frame % 2) * 70 + 70, (frame // 2) * 70 + 70))


def overlaps(a, b) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


@unittest.skipUnless(_ready(), "needs Unicorn, PIL, the pinned MSVC toolset and the vanilla executable")
class NurseryIconTests(unittest.TestCase):
    def test_the_pot_is_the_clocks_height_on_the_shelf_line_and_smaller_than_before(self) -> None:
        sheet = Image.open(SHEET).convert("RGBA")
        pot, clock, coins = (cell(sheet, f).getbbox() for f in (40, 26, 28))
        self.assertEqual(pot[3] - pot[1], clock[3] - clock[1])            # 52 px, as the Time Warp clock
        self.assertEqual(pot[3], clock[3])                                # the same bottom line
        self.assertEqual(pot[3], coins[3])
        stock = Image.open(EXE.parent / "Images" / "goldpot.png")
        self.assertLess(pot[3] - pot[1], stock.height)                    # 52 < the 64 it was drawn at
        self.assertLess(pot[2] - pot[0], stock.width)
        import build_plant_upgrades_assets as B
        self.assertEqual(B.nursery_icon(EXE.parent / "Images").tobytes(), cell(sheet, 40).tobytes())

    def test_drawn_at_scale_one_with_its_click_rectangle_and_overlapping_nothing(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("SHEET_CHEMICALS, NURSERY_FRAME, NURSERY_X, NURSERY_Y, 1.0f", source)
        self.assertIn("{ 453, 305, 514, 356 }", source)
        import render_seed_boxes_preview as S
        sheets = S.Sheets(EXE.parent)
        drawn = S.store_draws((1, 1, 1, 1, 1, 1), chem_slots=0)
        self.assertIn(("sprite", SHEET_CHEMICALS, 40, 449, 296), drawn)
        self.assertFalse([d for d in drawn if d[0] == "sprite" and d[1] == 0x2C])     # never the full-size pot
        visible = S.visible_rect(sheets, ("sprite", SHEET_CHEMICALS, 40, 449, 296))
        self.assertEqual((visible[0], visible[1], visible[2] - 1, visible[3] - 1), RECT)   # click = picture
        for d in drawn:
            if d[0] != "sprite" or d[1:] == (SHEET_CHEMICALS, 40, 449, 296):
                continue
            other = S.visible_rect(sheets, d)
            if other is not None:
                self.assertFalse(overlaps(RECT, (other[0], other[1], other[2] - 1, other[3] - 1)), d)


if __name__ == "__main__":
    unittest.main()
