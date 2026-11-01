"""The treated price beside the set price (Plant Tycoon, Store Upgrades and Items).

The owner (2026-10-31): "put the 'treated' price beside the normal 'set' price", and "Only show the
treated price in: The nursery; The window that pops up when you set prices; Not anywhere else".
A plant treated with the Radioactive Plant Formula (or its Bomb) shows "Treated: $M" beside its set
price on the nursery's bottom bar ("Asking Price: $P" when clicked, "Plant sold! Price: $P" when
sold) and in the Set Price of Plant popup; M is the number sale_price pays. Untreated plants show
nothing extra, and the greenhouse panel's "Price: $P" (0x428736) is left stock.

* The sites: each new site in upgrade_sites.h holds its vanilla bytes, disassembles as listed, and
  the DLL writes exactly them (and leaves the greenhouse panel's price draw alone).
* The draws, emulated in Unicorn on the vanilla Plant Tycoon.exe (tests/store_emulator.py) with
  Extra Greenhouses.dll and Store Upgrades and Items.dll mapped (as tests/test_radioactive_max_price.py):
  the game's text draw (0x4092A0), its "$P" draw (0x44CCD0) and the font width (0x402380) are
  recorded, the plant is planted, grown, treated with the DLL's own formula and sold by the stock
  sale (0x435C70).
"""

from __future__ import annotations

import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_plant as BP  # noqa: E402
import test_radioactive_max_price as R  # noqa: E402

E = R.E
PLANT_EXE = R.PLANT_EXE
HEADER = ROOT / "native" / "ftfp_plant_upgrades" / "upgrade_sites.h"
SOURCE = ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c"
BASE = 0x400000

DRAW_TEXT, MONEY_TEXT, TEXT_WIDTH, GRAPHICS_GET, GAME_STATE, FIELD_VALUE = (
    0x004092A0, 0x0044CCD0, 0x00402380, 0x00407A90, 0x0041FCD0, 0x0040C770)
GLYPH = 9                               # the recorded font's width per character

# name: (va, the vanilla instructions)
NEW_SITES = {
    "ASKING_PICK": (0x4366F9, ["mov dword ptr [esi + 8], edx", "call 0x403430"]),
    "ASKING_DRAW": (0x437CDC, ["call 0x44ccd0"]),
    "SOLD_DRAW": (0x437E77, ["call 0x44ccd0"]),
}
POPUP_SLOT, POPUP_STOCK = 0x469680, 0x416730


def header_site(name: str) -> tuple[int, bytes]:
    text = HEADER.read_text(encoding="utf-8")
    va = int(re.search(rf"#define SITE_{name}_VA (0x[0-9A-F]+)u", text).group(1), 16)
    raw = re.search(rf"SITE_{name}_EXPECT\[\] = \{{ ([^}}]*) \}}", text).group(1)
    return va, bytes(int(x, 16) for x in raw.split(", "))


def vanilla_at(va: int, n: int) -> bytes:
    data = PLANT_EXE.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    for i in range(count):
        at = pe + 24 + optional + i * 40
        vsize, rva, raw_size, raw = struct.unpack_from("<IIII", data, at + 8)
        if rva <= va - BASE < rva + max(vsize, raw_size):
            off = raw + va - BASE - rva
            return data[off:off + n]
    raise AssertionError(hex(va))


@unittest.skipUnless(PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon.exe")
class Sites(unittest.TestCase):
    def test_each_new_site_is_the_vanilla_code(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, (va, instructions) in NEW_SITES.items():
            got_va, expect = header_site(name)
            self.assertEqual(got_va, va, name)
            self.assertEqual(vanilla_at(va, len(expect)), expect, name)
            self.assertEqual([f"{i.mnemonic} {i.op_str}" for i in md.disasm(expect, va)], instructions, name)
        va, expect = header_site("PRICE_POPUP_OVERLAY")
        self.assertEqual((va, expect), (POPUP_SLOT, struct.pack("<I", POPUP_STOCK)))
        self.assertEqual(vanilla_at(POPUP_SLOT, 4), expect)
        self.assertEqual(vanilla_at(POPUP_STOCK, 1), b"\xC3", "the popup's overlay slot is the empty `ret`")
        self.assertEqual(vanilla_at(0x43001A, 6), b"\xC7\x06" + struct.pack("<I", 0x469664),
                         "the Set Price of Plant popup's constructor sets that vtable")

    def test_the_dll_installs_them_and_leaves_the_greenhouse_panel_alone(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("JMP(w++, ASKING_PICK, stub_asking_pick);", source)
        self.assertIn("CALL(w++, ASKING_DRAW, stub_asking_draw);", source)
        self.assertIn("CALL(w++, SOLD_DRAW, stub_sold_draw);", source)
        self.assertIn("site_data(w++, SITE_PRICE_POPUP_OVERLAY_VA", source)
        self.assertIn("#define CODE_SITES 30", source)
        self.assertIn("#define DATA_SITES 7", source)
        header = HEADER.read_text(encoding="utf-8")
        for va in range(0x428700, 0x428750):                    # the greenhouse panel's "Price: $P" (0x428736)
            self.assertNotIn(f"_VA 0x{va:08X}u", header)


@R.needs(PLANT_EXE)
class TreatedPriceShown(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        R.XG._build()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", R.PLANT_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ the rig
    def game(self):
        game = R.XG.Game(3)
        emu = game.emu
        game.upgrades, _ = R.map_second(emu, self.dll, self.symbols)
        for va, name, stub in ((0x435CF2, "SALE_RECORD", "_stub_sale_record"), (0x435D12, "SALE_CASH", "_stub_sale_cash"),
                               (0x42DF91, "DEAD_UNTAG", "_stub_dead_untag"), (0x42FCDD, "PLANT_SEED", "_stub_plant_seed")):
            R.branch(emu, va, game.upgrades[stub], R.site_length(name))
        emu.write32(0x0049333C, game.state)
        name = "___stdio_common_vsprintf_s"
        emu.hook(game.upgrades[name], lambda e: e._printf(False))
        graphics, inner, font = emu.alloc(0x10), emu.alloc(0x80), emu.alloc(0x80)
        emu.write32(graphics, inner)                                 # 0x407A90's object: [inner + 0x5C] the font
        emu.write32(inner + 0x5C, font)
        game.drawn, game.money = [], []
        emu.hook(GRAPHICS_GET, lambda e: graphics)
        emu.hook(GAME_STATE, lambda e: game.state)
        emu.hook(TEXT_WIDTH, lambda e: GLYPH * len(e.cstring(e.arg(0))), 8)
        emu.hook(DRAW_TEXT, lambda e: game.drawn.append(
            (e.cstring(e.arg(0)).decode("latin-1"), e.arg(1), e.arg(2))) or 0, 0x14)
        emu.hook(MONEY_TEXT, lambda e: game.money.append((e.arg(0), e.arg(1), e.arg(2))) or 0, 0xC)
        return game

    def grown(self, treated: bool, k: int = 4):
        """A Fabled Lemonbush (V = 250) in pot k, mature, for sale; treated with one formula dose."""
        game = self.game()
        emu = game.emu
        game.plant(0, k, 11, 10)
        game.tick(7200)
        if treated:
            game.arrange(0)
            plant = emu.call(R.XG.GET_PLANT, k // 5, k % 5, ecx=game.manager)
            emu.call(game.upgrades["_apply_chemical"], game.scene, k % 5, k // 5, plant, 36)
            game.arrange(R.XG.HOME)
        emu.write8(game.pot(0, k) + R.XG.FOR_SALE, 1)
        return game

    def asking(self, game) -> int:
        return game.emu.read32(game.state + ((11 + 0x37) * 26 + 10) * 4)

    def paid_by_sale_price(self, game, k: int, asking: int) -> int:
        return game.emu.call(game.upgrades["_sale_price"], game.pot(0, k), asking, 0)

    def nursery(self, game) -> int:
        emu = game.emu
        nursery = emu.alloc(0xB00)
        emu.write32(nursery + 0xA3C, game.state)
        emu.write32(nursery + 0xA44, game.manager)
        emu.write32(nursery + 0xA4C, emu.alloc(0x40))
        emu.hook(0x0043ACD0, lambda e: 0)
        emu.hook(0x00449F00, lambda e: emu.alloc(0x10))
        return nursery

    def treated_lines(self, game) -> list[tuple[str, int, int]]:
        return [d for d in game.drawn if d[0].startswith("Treated")]

    # ------------------------------------------------------------ the nursery: "Asking Price: $P"
    def test_the_asking_price_line(self) -> None:
        best = BP.load(None).prices((11, 10), "max").highest_selling
        self.assertEqual(best, 1186)
        for treated in (True, False):
            game = self.grown(treated)
            emu = game.emu
            nursery, asking = self.nursery(game), self.asking(game)
            emu.call(game.upgrades["_on_asking_pick"], nursery, game.pot(0, 4) - game.state - 0x2188)
            strings = emu.alloc(0x10)
            emu.call(game.upgrades["_on_asking_draw"], strings, asking, 626, 539, nursery)
            self.assertEqual(game.money, [(asking, 626, 539)], "the stock \"$P\" is drawn as before")
            if not treated:
                self.assertEqual(self.treated_lines(game), [], "an untreated plant shows nothing extra")
                continue
            paid = self.paid_by_sale_price(game, 4, asking)
            self.assertEqual(paid, best)
            text = f"Treated: ${paid}"
            x = min(626 + GLYPH * len(f"${asking}") + 14, 798 - GLYPH * len(text))
            self.assertEqual(self.treated_lines(game), [(text, x, 539)])
            self.assertGreaterEqual(x, 626 + GLYPH * len(f"${asking}"), "beside the $P, never over it")

    def test_the_asking_line_forgets_a_pot_that_holds_another_plant(self) -> None:
        game = self.grown(True)
        emu = game.emu
        nursery, asking = self.nursery(game), self.asking(game)
        emu.call(game.upgrades["_on_asking_pick"], nursery, game.pot(0, 4) - game.state - 0x2188)
        emu.write32(game.pot(0, 4) + 0x50, 9)                       # another flower in that pot now
        emu.call(game.upgrades["_on_asking_draw"], emu.alloc(0x10), asking, 626, 539, nursery)
        self.assertEqual(self.treated_lines(game), [])

    # ------------------------------------------------------------ the nursery: "Plant sold! Price: $P"
    def test_the_sold_line_shows_what_the_sale_paid(self) -> None:
        for treated in (True, False):
            game = self.grown(treated)
            emu = game.emu
            nursery, asking = self.nursery(game), self.asking(game)
            cash = emu.read32(game.state + R.S_CASH)
            emu.call(0x00435C70, 0, 0, 0, 4, ecx=nursery)                 # the stock sale of pot 4
            paid = emu.read32(game.state + R.S_CASH) - cash
            self.assertEqual(paid, 1186 if treated else asking)
            self.assertEqual(game.pot_bytes(0, 4)[R.POT_MARK], 0, "the sale spent the mark")
            self.assertEqual((emu.read32(nursery + 0x10), emu.read32(nursery + 0x14)), (0, 4), "the sold list")
            emu.write32(nursery + 0x50, 0)
            emu.call(game.upgrades["_on_sold_draw"], emu.alloc(0x10), asking, 636, 539, nursery)
            self.assertEqual(game.money, [(asking, 636, 539)])
            if treated:
                text = f"Treated: ${paid}"
                x = min(636 + GLYPH * len(f"${asking}") + 14, 798 - GLYPH * len(text))
                self.assertEqual(self.treated_lines(game), [(text, x, 539)])
            else:
                self.assertEqual(self.treated_lines(game), [])

    # ------------------------------------------------------------ the Set Price of Plant popup
    def popup(self, game, k: int, typed: int) -> int:
        emu = game.emu
        popup = emu.alloc(0x80)
        emu.write32(popup + 0x14, 210)                               # left, top, right
        emu.write32(popup + 0x18, 183)
        emu.write32(popup + 0x1C, 590)
        emu.write32(popup + 0x50, emu.alloc(0x40))                   # its price field
        emu.write32(popup + 0x54, k // 5)
        emu.write32(popup + 0x58, k % 5)
        emu.hook(FIELD_VALUE, lambda e: typed)
        return popup

    def test_the_popup_shows_the_treated_price_under_the_price(self) -> None:
        for treated in (True, False):
            game = self.grown(treated)
            emu = game.emu
            asking = self.asking(game)
            emu.call(game.upgrades["@price_popup_overlay@4"], ecx=self.popup(game, 4, asking))
            if not treated:
                self.assertEqual(game.drawn, [], "an untreated plant: the popup is stock")
                continue
            paid = self.paid_by_sale_price(game, 4, asking)
            text = f"Treated: ${paid}"
            self.assertEqual(game.drawn, [(text, 210 + (380 - GLYPH * len(text)) // 2, 183 + 130)])
            self.assertEqual(paid, 1186)

    def test_the_popup_follows_the_price_typed(self) -> None:
        """Typed above the highest selling price, the sale pays the asking price (never less than P),
        and the popup says so; past 9999 it is 9999, as the popup's OK keeps it."""
        game = self.grown(True)
        emu = game.emu
        for typed, shown in ((5, 1186), (2000, 2000), (12000, 9999)):
            game.drawn.clear()
            emu.call(game.upgrades["@price_popup_overlay@4"], ecx=self.popup(game, 4, typed))
            self.assertEqual([d[0] for d in game.drawn], [f"Treated: ${shown}"], typed)

    def test_a_dead_treated_plant_shows_nothing(self) -> None:
        game = self.grown(True)
        emu = game.emu
        emu.write32(game.pot(0, 4) + 0x24, 0)
        emu.call(game.upgrades["@price_popup_overlay@4"], ecx=self.popup(game, 4, 100))
        self.assertEqual(game.drawn, [])


if __name__ == "__main__":
    unittest.main()
