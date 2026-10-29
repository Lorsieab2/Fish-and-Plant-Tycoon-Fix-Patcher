"""The Flower of Knowledge ("Nox Orchid") price at a new game, both games.

Plant Tycoon's new game (0x41EF30) runs the price setup (0x41DBD0, called at
0x41EFB8) before it clears the magic plant flags (0x41F170), and the price
setup gives every species V + 3 x (V/4) when the Flower of Knowledge flag
(+0x2181) is set. So a new game started after a save with that flag was
loaded (the game loads the last save when it starts, 0x41FA10) is priced as if
it had found the Flower of Knowledge. That is the stock game's own code order;
Unused Flowers.dll prices its 322 species the same way. These tests run the
vanilla code in Unicorn to pin that, and check that the Game Mechanics page
says it.

Fish Tycoon has no such price: its new-game price setup (0x418B10) writes
fixed base prices and "undiscovered" for every species whatever the state held
before, with DS Exclusive Fish too.
"""

from __future__ import annotations

import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import game_mechanics as gm  # noqa: E402

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None

NEW_GAME, PRICE_SETUP, AFTER_FLAG_CLEAR = 0x41EF30, 0x41DBD0, 0x41F17D
KNOWLEDGE = 0x2181
STOCK_SPECIES = [(f, fl) for f in range(1, 24) for fl in range(1, 24)]


def nox(v: int) -> int:
    return v + 3 * (v // 4)


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


@_needs(PLANT_EXE)
class PlantNewGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_new_flowers", ROOT / "assets" / "plant_tycoon_flowers" / "Unused Flowers.dll", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def emulator(self, with_dll: bool):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        rng = random.Random(7)
        emu.hook(0x004033B0, lambda e: rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0)    # Random(bound)
        emu.hook(0x00403430, lambda e: 1000)                                              # the clock

        def memset(e):
            e.uc.mem_write(e.arg(0), bytes([e.arg(1) & 0xFF]) * e.arg(2))
            return e.arg(0)
        emu.hook(0x00451280, memset)
        if with_dll:      # the DLL's two hooks, as FtfpStartup writes them
            emu.call(emu.sym("_build_tables"))
            for va, stub in ((PRICE_SETUP, "_stub_price_setup"), (NEW_GAME, "_stub_new_game")):
                emu.uc.mem_write(va, b"\xE9" + struct.pack("<i", emu.sym(stub) - (va + 5)))
        return emu

    def run_to(self, emu, start: int, stop: int, state: int, *args: int) -> None:
        esp = E.STACK + E.STACK_SIZE - 0x1000
        for value in reversed(args):
            esp -= 4
            emu.write32(esp, value)
        esp -= 4
        emu.write32(esp, E.RETURN)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ECX, state)
        emu.uc.emu_start(start, stop, count=20_000_000)

    def new_game(self, knowledge_before: int, with_dll: bool = False):
        emu = self.emulator(with_dll)
        state = emu.alloc(0x63E64)
        emu.write8(state + KNOWLEDGE, knowledge_before)
        self.run_to(emu, NEW_GAME, AFTER_FLAG_CLEAR, state)
        return emu, state

    @staticmethod
    def stock_prices(emu, state):
        read = lambda o: emu.read32(state + o, signed=True)
        return {(f, fl): (read(((f + 0x1D) * 26 + fl) * 4), read(((f + 0x37) * 26 + fl) * 4))
                for f, fl in STOCK_SPECIES}

    @staticmethod
    def new_prices(emu):
        read = lambda name, f, k: emu.read32(emu.sym(name) + (f * 14 + k) * 4, signed=True)
        return {(f, 24 + k): (read("_value", f, k), read("_price", f, k)) for f in range(1, 24) for k in range(14)}

    def test_a_clean_new_game_gets_the_normal_prices(self) -> None:
        emu, state = self.new_game(0)
        prices = self.stock_prices(emu, state)
        self.assertEqual(prices[(4, 4)][0], 95)                       # the Nox Orchid's V
        for (v, p) in prices.values():
            self.assertLessEqual(abs(p - v), v // 2)
        self.assertLess(sum(p == nox(v) for v, p in prices.values()), 30)
        self.assertEqual(emu.uc.mem_read(state + KNOWLEDGE, 1)[0], 0)

    def test_a_new_game_after_a_knowledge_save_gets_the_knowledge_price(self) -> None:
        # Stock: the flag left by the loaded save is read before the new game clears it.
        emu, state = self.new_game(1)
        prices = self.stock_prices(emu, state)
        self.assertTrue(all(p == nox(v) for v, p in prices.values()))
        self.assertEqual(prices[(4, 4)][1], 95 + 3 * 23)
        self.assertEqual(emu.uc.mem_read(state + KNOWLEDGE, 1)[0], 0)   # the save shows it not found

    def test_finding_the_flower_of_knowledge_gives_the_knowledge_price(self) -> None:
        emu = self.emulator(False)
        state = emu.alloc(0x63E64)
        self.run_to(emu, NEW_GAME, AFTER_FLAG_CLEAR, state)
        self.run_to(emu, 0x41EB00, 0x41EB4B, state, 4, 4)            # the magic plant check, flower (4, 4)
        self.assertEqual(emu.uc.mem_read(state + KNOWLEDGE, 1)[0], 1)
        self.assertTrue(all(p == nox(v) for v, p in self.stock_prices(emu, state).values()))

    def test_unused_flowers_prices_its_species_as_the_game_does(self) -> None:
        for before in (0, 1):
            emu, state = self.new_game(before, with_dll=True)
            stock = self.stock_prices(emu, state)
            new = self.new_prices(emu)
            self.assertEqual(len(new), 322)
            self.assertEqual(all(p == nox(v) for v, p in stock.values()), bool(before))
            self.assertEqual(all(p == nox(v) for v, p in new.values()), bool(before))
            if not before:
                for v, p in new.values():
                    self.assertLessEqual(abs(p - v), v // 2)


@_needs(FISH_EXE)
class FishNewGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_ds_fish", ROOT / "assets" / "fish_tycoon_ds" / "DS Exclusive Fish.dll", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def new_game_prices(self, stale: bool, with_dll: bool):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        size = 0x30000
        state = emu.alloc(size)
        if stale:      # a played game's leftovers: raised base prices, asking prices, research, difficulty
            rng = random.Random(3)
            emu.uc.mem_write(state, bytes(rng.randrange(256) for _ in range(size)))
        emu.call(0x00418B10, ecx=state)
        if with_dll:
            emu.call(emu.sym("@init_ds_species@4"), ecx=state)
        rows = emu.read32(emu.sym("_ds_rows"))
        got = {}
        for b in range(30):
            for f in range(30):
                if b in (21, 22) or f in (21, 22):
                    continue
                if 23 <= b <= 29:
                    if not with_dll:
                        continue
                    at = rows + ((b - 23) * 31 + f) * 0x28
                elif f <= 20 or with_dll:
                    at = state + 0x14B40 + (b * 31 + f) * 0x28
                else:
                    continue
                got[(b, f)] = (emu.read32(at + 0x20, signed=True), emu.read32(at + 0x24, signed=True))
        return got

    def test_the_new_game_prices_ignore_what_came_before(self) -> None:
        for with_dll, count in ((False, 441), (True, 784)):
            clean, stale = self.new_game_prices(False, with_dll), self.new_game_prices(True, with_dll)
            self.assertEqual(len(clean), count)
            self.assertEqual(clean, stale)
            self.assertTrue(all(asking == -1 for asking, _ in stale.values()))
            self.assertEqual(stale[(7, 7)], (-1, 190))                  # the Golden Guppy


class GameMechanicsTextTests(unittest.TestCase):
    def test_the_plant_page_explains_the_knowledge_price_at_a_new_game(self) -> None:
        page = gm.load_page("plant")
        prices = next(group for group in page.groups if group.title == "Prices")
        text = " ".join(fact.text for fact in prices.facts)
        for part in ("Flower of Knowledge price", "0x41EFB8", "0x41F170", "loads your last save"):
            self.assertIn(part, text)
        magic = " ".join(" ".join(fact.subs) for group in page.groups for fact in group.facts)
        self.assertNotIn("not tried live", magic)


if __name__ == "__main__":
    unittest.main()
