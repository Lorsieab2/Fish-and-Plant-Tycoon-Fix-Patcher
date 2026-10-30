"""The Radioactive Plant Formula and its Bomb always give 5 seeds (the owner, 2026-10-31).

A plant given the formula (the bottle, chemical 36, or the bomb, 39) gives all 5 seeds when it
is pollinated; one already pollinated gets all its seeds ripe at once, through the game's own
ripening state. These run the DLL's code with the vanilla executable's own pollination
(0x4240A0) and ripening (0x42E0C2-0x42E0F8) in Unicorn (tests/store_emulator.py).
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None
import test_revival_potion as RP  # noqa: E402  (the greenhouse harness)

PLANT_EXE = RP.PLANT_EXE
POLLINATED, RIPE, TAKEN, POLLINATED_AT, HELD, INFESTED, AGE = 0x6C, 0x90, 0x94, 0x98, 0x7C, 0x28, 0x10
FORMULA, REVITA, BOMB = 36, 38, 39
MARK = 0x35534652


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


@_needs(PLANT_EXE)
class FormulaSeedsTests(unittest.TestCase):
    greenhouse = RP.PlantTests.greenhouse
    pot = RP.PlantTests.pot
    apply = RP.PlantTests.apply
    plant = RP.PlantTests.plant

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_plant_upgrades", ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll",
            Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # --------------------------------------------------------------- helpers
    def plant_pot(self, emu, k: int, age: float = 30.0, infested: int = 0) -> int:
        pot = self.pot(emu, k)
        emu.write8(pot + 0x38, 1)
        emu.write32(pot + 0x24, 80)
        emu.uc.mem_write(pot + AGE, struct.pack("<f", age))
        emu.uc.mem_write(pot + 0x14, struct.pack("<f", age))
        emu.write32(pot + INFESTED, infested)
        emu.write8(pot + POLLINATED, 0)
        emu.write32(pot + HELD, 0)
        for field in (0x4C, 0x50):
            emu.write32(pot + field, 3)
        return pot

    def pollinate(self, emu, pot: int, roll: int) -> None:
        """The game's pollination (0x4240A0, Random(3) = roll), then the DLL's tail (Unused Flowers' hook)."""
        emu.rolls = [roll]
        emu.call(0x004240A0, pot, self.pot(emu, 14))
        emu.call(emu.sym("_on_pollinated"), pot)

    def ripen(self, emu, pot: int, age: float) -> None:
        """One age unit's ripening, the game's own (0x42E0C2-0x42E0F8), at this age."""
        from unicorn import x86_const as X
        emu.uc.mem_write(pot + AGE, struct.pack("<f", age))
        plant = emu.alloc(0x20)
        emu.write32(plant + 8, pot)
        emu.uc.reg_write(X.UC_X86_REG_ESI, plant)
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        emu.uc.emu_start(0x0042E0C2, 0x0042E0F8, count=10_000)

    def seeds(self, emu, pot: int) -> tuple[int, int]:
        return emu.read32(pot + RIPE), emu.read32(pot + TAKEN, signed=True)

    def pick_all(self, emu, pot: int) -> int:
        """Ripe seeds picked until none is left (the pick: 0x426208's +0x90 - 1, +0x94 + 1)."""
        picked = 0
        while emu.read32(pot + TAKEN, signed=True) < 5 and emu.read32(pot + RIPE) > 0:
            emu.write32(pot + RIPE, emu.read32(pot + RIPE) - 1)
            emu.write32(pot + TAKEN, emu.read32(pot + TAKEN) + 1)
            picked += 1
        return picked

    # ----------------------------------------------------------------- tests
    def test_stock_pollination_gives_5_4_or_3(self) -> None:
        for roll, given in ((0, 5), (1, 4), (2, 3)):
            emu = self.greenhouse()
            pot = self.plant_pot(emu, 0)
            self.pollinate(emu, pot, roll)
            self.ripen(emu, pot, 40.0)
            self.assertEqual(self.pick_all(emu, pot), given, roll)

    def test_a_formula_plant_pollinated_later_gives_5(self) -> None:
        for roll in (0, 1, 2):
            for infested in (0, 1):
                emu = self.greenhouse()
                pot = self.plant_pot(emu, 0, infested=infested)
                self.apply(emu, FORMULA, 0, self.plant(emu, 0))
                self.assertEqual(emu.read32(pot + HELD), MARK)
                self.pollinate(emu, pot, roll)
                self.assertEqual((emu.read32(pot + TAKEN), emu.read32(pot + HELD)), (0, 0), (roll, infested))
                self.ripen(emu, pot, 30.0 + 7)
                self.assertEqual(self.pick_all(emu, pot), 5, (roll, infested))

    def test_an_already_pollinated_plant_gets_all_its_seeds_ripe_at_once(self) -> None:
        for roll, infested in ((0, 0), (1, 0), (2, 0), (0, 1)):
            emu = self.greenhouse()
            pot = self.plant_pot(emu, 0, infested=infested)
            self.pollinate(emu, pot, roll)                    # just pollinated: nothing ripe yet
            self.assertEqual(emu.read32(pot + RIPE), 0)
            self.apply(emu, FORMULA, 0, self.plant(emu, 0))
            self.assertEqual(self.seeds(emu, pot), (5, 0), (roll, infested))
            self.ripen(emu, pot, 30.0)                        # the game's own ripening keeps all 5
            self.assertEqual(self.seeds(emu, pot), (5, 0), (roll, infested))
            self.assertEqual(self.pick_all(emu, pot), 5)

    def test_a_partly_picked_plant_gets_the_rest_of_its_5(self) -> None:
        emu = self.greenhouse()
        pot = self.plant_pot(emu, 0)
        self.pollinate(emu, pot, 2)                           # 3 given
        self.ripen(emu, pot, 36.0)                            # 6 units: min(6 - 2, 5) - 2 held back = 2 ripe
        self.assertEqual(self.pick_all(emu, pot), 2)          # 2 picked of the 3
        self.apply(emu, FORMULA, 0, self.plant(emu, 0))
        self.assertEqual(self.seeds(emu, pot), (3, 2))
        self.ripen(emu, pot, 36.0)
        self.assertEqual(self.pick_all(emu, pot), 3)          # 5 in all

    def test_the_bomb_on_a_full_greenhouse(self) -> None:
        emu = self.greenhouse()
        pots = [self.plant_pot(emu, k) for k in range(15)]
        for k in range(0, 15, 2):
            self.pollinate(emu, pots[k], k % 3)               # half pollinated (5, 4 or 3), half not
        self.apply(emu, BOMB, 0)
        for k, pot in enumerate(pots):
            if k % 2 == 0:
                self.assertEqual(self.seeds(emu, pot), (5, 0), k)
            else:
                self.assertEqual(emu.read32(pot + HELD), MARK, k)
                self.pollinate(emu, pot, 2)
                self.ripen(emu, pot, 37.0)
                self.assertEqual(self.pick_all(emu, pot), 5, k)

    def test_the_mark_moves_with_the_pot_through_greenhouses_2_to_6(self) -> None:
        # Extra Greenhouses exchanges whole pot records (0x5600 bytes) with its own memory: the mark,
        # in the record, goes with the plant to Greenhouse 2-6 and back.
        emu = self.greenhouse()
        pot = self.plant_pot(emu, 3)
        self.apply(emu, FORMULA, 3, self.plant(emu, 3))
        other = emu.alloc(0x5600)
        here = bytes(emu.uc.mem_read(pot, 0x5600))
        emu.uc.mem_write(pot, bytes(0x5600))                   # Greenhouse 1's pot moves out ...
        emu.uc.mem_write(other, here)
        emu.uc.mem_write(pot, bytes(emu.uc.mem_read(other, 0x5600)))   # ... and back in when shown
        self.pollinate(emu, pot, 2)
        self.ripen(emu, pot, 37.0)
        self.assertEqual(self.pick_all(emu, pot), 5)
        for k in (5, 10, 14):                                  # any of the 15 pots a greenhouse shows
            emu = self.greenhouse()
            pot = self.plant_pot(emu, k)
            self.apply(emu, FORMULA, k, self.plant(emu, k))
            self.pollinate(emu, pot, 1)
            self.ripen(emu, pot, 37.0)
            self.assertEqual(self.pick_all(emu, pot), 5, k)

    def test_revita_seed_then_the_formula(self) -> None:
        emu = self.greenhouse()
        pot = self.plant_pot(emu, 0)
        self.pollinate(emu, pot, 2)
        self.ripen(emu, pot, 40.0)
        self.pick_all(emu, pot)                                # depleted
        self.apply(emu, REVITA, 0)
        self.apply(emu, FORMULA, 0, self.plant(emu, 0))
        self.assertEqual(emu.read32(pot + HELD), MARK)
        self.pollinate(emu, pot, 2)
        self.ripen(emu, pot, 47.0)
        self.assertEqual(self.pick_all(emu, pot), 5)

    def test_a_new_plant_never_inherits_the_mark(self) -> None:
        emu = self.greenhouse()
        pot = self.plant_pot(emu, 0)
        self.apply(emu, FORMULA, 0, self.plant(emu, 0))
        from unicorn import x86_const as X
        emu.uc.reg_write(X.UC_X86_REG_ESI, pot)
        emu.uc.reg_write(X.UC_X86_REG_EDX, 0x1234)
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        emu.uc.emu_start(emu.sym("_stub_plant_seed"), 0x0042FCE4, count=100)   # planting a new seed there
        self.assertEqual((emu.read32(pot + 0x78), emu.read8(pot + POLLINATED) if hasattr(emu, "read8") else
                          emu.uc.mem_read(pot + POLLINATED, 1)[0], emu.read32(pot + HELD)), (0x1234, 0, 0))
        self.pollinate(emu, pot, 2)
        self.ripen(emu, pot, 40.0)
        self.assertEqual(self.pick_all(emu, pot), 3)           # the stock 3

    def test_the_formula_still_skips_a_dead_plant(self) -> None:
        emu = self.greenhouse()
        pot = self.plant_pot(emu, 0)
        emu.write32(pot + 0x24, 0)
        self.apply(emu, FORMULA, 0, self.plant(emu, 0))
        self.assertEqual(emu.read32(pot + HELD), 0)


if __name__ == "__main__":
    unittest.main()
