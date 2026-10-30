"""No chemical takes a plant off sale (the owner, 2026-10-30: "the chemicals should not clear the Sell tag").

A plant's Sell tag is its pot's on-sale byte, +0x9D (the Sell button, 0x427CDD). The cause: the
Radioactive Plant Formula (chemical 36, and its Bomb, 39, which gives every live plant one Formula
dose) set +0x9C, the "age-7 branch roll done" byte, with a 4-byte write, which also zeroed +0x9D
and the sold byte +0x9E. Now it writes the one byte, as the game does (0x42E482).

A dead plant: the stock plant update clears +0x9D every update while health <= 0 (0x42DF91). The
DLL's dead_untag site marks the pot first (+0x9F = 'S', a byte no game code reads or writes), and
the Revival Potion (37) puts the tag back, when the plant can be sold and the nurseries have room.

These run the DLL's code with the vanilla executable's own code in Unicorn (tests/store_emulator.py):
the chemical-use path from the switch at 0x4266A6 through the stock tail, and the plant update
0x42DF80 on a dead plant.
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
FORMULA, REVIVAL, REVITA, BOMB = 36, 37, 38, 39
HEALTH, DIED, AGE, PLANTED, FOLIAGE, PRICE, VALUE = 0x24, 0x3C, 0x10, 0x38, 0x4C, 0x44, 0x48
POLLINATED, TAKEN = 0x6C, 0x94
FOR_SALE, SOLD, KEPT_AT, KEPT = 0x9D, 0x9E, 0x9F, 0x53
SWITCH, DEAD_UNTAG, PLANT_UPDATE = 0x004266A6, 0x0042DF91, 0x0042DF80
EXTRA = 0x7E570000                                   # a module handle for "Extra Greenhouses.dll"


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


def jump(emu, at: int, to: int, length: int) -> None:
    emu.uc.mem_write(at, b"\xE9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (length - 5))


@_needs(PLANT_EXE)
class SellTagTests(unittest.TestCase):
    pot = RP.PlantTests.pot
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

    # --------------------------------------------------------------- the game
    def greenhouse(self, for_sale: int | None = None, nurseries: int = -1):
        """RP's greenhouse, with the DLL's two hooks written as FtfpStartup writes them, the tail's
        sound and tray calls answered, and "Extra Greenhouses.dll" loaded when for_sale is given
        (its count of plants for sale over all six greenhouses, and its nurseries owned)."""
        emu = RP.PlantTests.greenhouse(self)
        jump(emu, SWITCH, emu.sym("_stub_apply"), 7)
        jump(emu, DEAD_UNTAG, emu.sym("_stub_dead_untag"), 7)
        emu.hook(0x0044A520, emu.record("sound"), 8)                    # the chemical's sound
        emu.hook(0x00416700, lambda e: 0, 4)                            # the tray: the bottle is used up
        greenhouse = emu.gh
        for field in (0x60, 0x74, 0x8C):
            emu.write32(greenhouse + field, emu.alloc(0x40))
        emu.write32(emu.state + 0x56C, 5)                               # a chemical held
        names = {}

        def module(e):
            name = e.wstring(e.arg(0))
            return EXTRA if name == "Extra Greenhouses.dll" and for_sale is not None else 0

        def proc(e):
            if e.arg(0) != EXTRA:
                return 0
            name = e.cstring(e.arg(1)).decode()
            if name not in names:
                names[name] = e.thunk()
                value = {"FtfpExtraGreenhousesForSale": for_sale, "FtfpExtraNurseriesOwned": nurseries}.get(name, 0)
                e.hook(names[name], lambda e2, v=value: v, 0)
            return names[name]
        emu.hook_import("GetModuleHandleW", module, 4)
        emu.hook_import("GetProcAddress", proc, 8)
        emu.hook_import("GetActiveWindow", lambda e: 0x1234, 0)
        emu.hook_import("GetForegroundWindow", lambda e: 0x1234, 0)
        emu.told = []
        emu.hook_import("MessageBoxW", lambda e: (e.told.append((e.wstring(e.arg(2)), e.wstring(e.arg(1)))), 1)[1], 16)
        return emu

    def tagged(self, emu, k: int, price: int = 1234, health: int = 80) -> int:
        """A mature plant for sale in pot k, at the player's price."""
        pot = self.pot(emu, k)
        emu.write8(pot + PLANTED, 1)
        emu.write32(pot + FOLIAGE, 3)
        emu.write32(pot + HEALTH, health)
        emu.write32(pot + DIED, 0)
        emu.uc.mem_write(pot + AGE, struct.pack("<f", 30.0))
        emu.write32(pot + PRICE, price)
        emu.write32(pot + VALUE, 900)
        emu.uc.mem_write(pot + 0x9C, bytes([0, 1, 0, 0]))               # rolled no; for sale; not sold; no mark
        return pot

    def use(self, emu, chemical: int, k: int) -> None:
        """The greenhouse's own chemical use from its switch (0x4266A6) through the stock tail."""
        from unicorn import x86_const as X
        frame = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.mem_write(frame, bytes(0x40))
        emu.write32(frame + 0x14, self.plant(emu, k))
        emu.write32(frame + 0x1C, E.RETURN)
        emu.write32(frame + 0x20, chemical)
        for register, value in ((X.UC_X86_REG_ESP, frame), (X.UC_X86_REG_ESI, emu.gh),
                                (X.UC_X86_REG_EBX, k % 5), (X.UC_X86_REG_EBP, k // 5),
                                (X.UC_X86_REG_EDI, k * RP.POT_SIZE)):
            emu.uc.reg_write(register, value)
        emu.uc.reg_write(X.UC_X86_REG_FPCW, 0x027F)
        emu.uc.emu_start(SWITCH, E.RETURN, count=5_000_000)
        self.assertIn("sound", [c[0] for c in emu.calls])               # the stock tail ran

    def update(self, emu, k: int) -> None:
        """The game's own plant update (0x42DF80) of pot k."""
        emu.call(PLANT_UPDATE, 999999, ecx=self.plant(emu, k))

    def die(self, emu, k: int) -> None:
        """Pot k's plant dies as the game's age step leaves a dead plant (0x42E270-0x42E29D), then
        two updates (each clears the tag while health <= 0)."""
        pot = self.pot(emu, k)
        emu.write32(pot + HEALTH, 0)
        emu.write32(pot + DIED, 1)
        emu.write32(pot + PRICE, 0)
        emu.write32(pot + VALUE, 0)
        self.update(emu, k)
        self.update(emu, k)

    def flags(self, emu, pot: int) -> bytes:
        return bytes(emu.uc.mem_read(pot + 0x9D, 3))                    # for sale, sold, the mark

    # ------------------------------------------------------- the four chemicals
    def test_the_formula_keeps_the_tag_and_the_price(self) -> None:
        emu = self.greenhouse()
        pot = self.tagged(emu, 7)
        self.use(emu, FORMULA, 7)
        self.assertEqual(emu.read32(pot + HEALTH), 100)                 # the formula ran
        self.assertEqual(emu.uc.mem_read(pot + 0x9C, 1)[0], 1)          # its one byte: the branch roll done
        self.assertEqual(self.flags(emu, pot), bytes([1, 0, 0]))
        self.assertEqual(emu.read32(pot + PRICE), 1234)

    def test_the_formula_leaves_a_sold_plant_sold(self) -> None:
        emu = self.greenhouse()
        pot = self.tagged(emu, 2)
        emu.uc.mem_write(pot + FOR_SALE, bytes([0, 1]))                 # bought by a visitor
        self.use(emu, FORMULA, 2)
        self.assertEqual(self.flags(emu, pot), bytes([0, 1, 0]))

    def test_revita_seed_and_the_revival_potion_keep_the_tag_on_a_live_plant(self) -> None:
        for chemical, depleted in ((REVITA, True), (REVITA, False), (REVIVAL, False)):
            emu = self.greenhouse()
            pot = self.tagged(emu, 4)
            emu.write8(pot + POLLINATED, 1)
            emu.write32(pot + TAKEN, 5 if depleted else 2)
            self.use(emu, chemical, 4)
            self.assertEqual(self.flags(emu, pot), bytes([1, 0, 0]), (chemical, depleted))
            self.assertEqual(emu.read32(pot + PRICE), 1234, chemical)
            if depleted:
                self.assertEqual(emu.uc.mem_read(pot + POLLINATED, 1)[0], 0)       # Revita-Seed ran

    def test_the_bomb_keeps_every_tag_in_the_greenhouse(self) -> None:
        emu = self.greenhouse()
        pots = [self.tagged(emu, k, price=100 + k) for k in range(15)]
        for k in range(1, 15, 3):
            emu.write8(pots[k] + FOR_SALE, 0)                           # some not for sale
        emu.write32(pots[5] + HEALTH, 0)                                # a dead one: the bomb skips it
        self.use(emu, BOMB, 0)
        for k, pot in enumerate(pots):
            self.assertEqual(emu.uc.mem_read(pot + FOR_SALE, 1)[0], 0 if k % 3 == 1 else 1, k)
            self.assertEqual(emu.read32(pot + PRICE), 100 + k, k)
            self.assertEqual(emu.read32(pot + HEALTH), 0 if k == 5 else 100, k)

    def test_no_stock_code_but_the_sell_buttons_the_sale_and_the_dead_update_writes_the_tag(self) -> None:
        # Every instruction of the game that writes a pot's +0x9D (directly, or the Sell button's
        # pointer from 0x427CE5): none is in the chemical use (0x426600-0x4273A8) or anything it calls.
        import capstone
        data = PLANT_EXE.read_bytes()
        base, _size, sections, _imports = E.pe_image(data)
        rva, raw, raw_size = sections[0]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        md.skipdata = True
        writes = set()
        for ins in md.disasm(data[raw:raw + raw_size], base + rva):
            target = ins.op_str.split(",")[0]
            if not (target.endswith("+ 0x9d]") or target.endswith("+ 0x2225]")
                    or ins.op_str.endswith("+ 0x9d]") or ins.op_str.endswith("+ 0x2225]")):
                continue
            if ins.mnemonic == "lea" or (ins.mnemonic not in ("cmp", "test")
                                         and ("0x9d]" in target or "0x2225]" in target)):
                writes.add(ins.address)                                 # a write, or a pointer to the byte
        self.assertEqual(sorted(writes), [0x427CE5, 0x427D3E, 0x427F05, 0x428038, 0x42DF91, 0x435C90])
        # The Sell button and Sell All (0x427960), the plant update's dead-plant clear (0x42DF80) and a
        # visitor's purchase (0x435C70).

    # ------------------------------------------------------- death and revival
    def test_a_tagged_plant_that_dies_and_is_revived_is_for_sale_again(self) -> None:
        emu = self.greenhouse()
        pot = self.tagged(emu, 7)
        self.die(emu, 7)
        self.assertEqual(self.flags(emu, pot), bytes([0, 0, KEPT]))   # off sale while dead, as in stock
        emu.rolls = [40]
        self.use(emu, REVIVAL, 7)
        self.assertEqual(emu.read32(pot + HEALTH), 100)
        self.assertEqual(self.flags(emu, pot), bytes([1, 0, 0]))
        self.assertEqual(emu.read32(pot + PRICE), 500 - 500 // 3 + 40)   # the planting rule (death set 0)
        self.assertEqual(emu.told, [])

    def test_an_untagged_plant_revived_stays_untagged(self) -> None:
        emu = self.greenhouse()
        pot = self.tagged(emu, 3)
        emu.write8(pot + FOR_SALE, 0)
        self.die(emu, 3)
        self.assertEqual(self.flags(emu, pot), bytes([0, 0, 0]))
        self.use(emu, REVIVAL, 3)
        self.assertEqual(emu.read32(pot + HEALTH), 100)
        self.assertEqual(self.flags(emu, pot), bytes([0, 0, 0]))

    def test_a_plant_that_died_outside_the_update_is_remembered_too(self) -> None:
        # Health reaching 0 between updates: the next update's clear still marks the pot.
        emu = self.greenhouse()
        pot = self.tagged(emu, 0)
        emu.write32(pot + HEALTH, -3)
        self.update(emu, 0)
        self.assertEqual(self.flags(emu, pot), bytes([0, 0, KEPT]))
        self.use(emu, REVIVAL, 0)
        self.assertEqual(self.flags(emu, pot), bytes([1, 0, 0]))

    def test_a_live_plant_update_never_marks(self) -> None:
        emu = self.greenhouse()
        pot = self.tagged(emu, 1)
        emu.write32(pot + 0x04, 0)                                      # no clock: the update returns at once
        self.update(emu, 1)
        self.assertEqual(self.flags(emu, pot), bytes([1, 0, 0]))

    def test_a_new_plant_in_the_pot_drops_the_mark(self) -> None:
        from unicorn import x86_const as X
        emu = self.greenhouse()
        pot = self.tagged(emu, 6)
        self.die(emu, 6)
        emu.uc.reg_write(X.UC_X86_REG_ESI, pot)
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        emu.uc.emu_start(emu.sym("_stub_plant_seed"), 0x0042FCE4, count=100)   # a seed planted there
        self.assertEqual(emu.uc.mem_read(pot + KEPT_AT, 1)[0], 0)
        emu.write32(pot + HEALTH, 0)                                    # (dead again, never tagged)
        self.use(emu, REVIVAL, 6)
        self.assertEqual(self.flags(emu, pot), bytes([0, 0, 0]))

    def test_the_mark_goes_with_the_pot_through_greenhouses_2_to_6(self) -> None:
        # Extra Greenhouses moves whole 0x5600-byte pot records (swap_pos; ExtraGreenhousesMarkTests
        # below runs its own code): a plant that died for sale in another greenhouse comes back into
        # whichever of the 15 state pots shows it and is revived for sale there.
        for k in (0, 5, 9, 14):
            emu = self.greenhouse(for_sale=3, nurseries=0)
            pot = self.tagged(emu, k)
            self.die(emu, k)
            record = bytes(emu.uc.mem_read(pot, RP.POT_SIZE))
            other = (k + 3) % 15
            emu.uc.mem_write(self.pot(emu, other), record)               # shown in another pot place
            emu.uc.mem_write(pot, bytes(RP.POT_SIZE))
            self.use(emu, REVIVAL, other)
            self.assertEqual(self.flags(emu, self.pot(emu, other)), bytes([1, 0, 0]), k)

    def test_full_nurseries_leave_it_off_sale_and_say_so(self) -> None:
        for for_sale, nurseries, back in ((None, -1, True), (14, -1, True), (15, -1, False), (14, 0, True),
                                          (15, 0, False), (29, 1, True), (30, 1, False), (89, 5, True),
                                          (90, 5, False)):
            emu = self.greenhouse(for_sale=for_sale, nurseries=nurseries)
            pot = self.tagged(emu, 8)
            self.die(emu, 8)
            self.use(emu, REVIVAL, 8)
            self.assertEqual(emu.read32(pot + HEALTH), 100)
            self.assertEqual(self.flags(emu, pot), bytes([1 if back else 0, 0, 0]), (for_sale, nurseries))
            if back:
                self.assertEqual(emu.told, [], (for_sale, nurseries))
            else:
                limit = 15 * (max(nurseries, 0) + 1)
                self.assertEqual(len(emu.told), 1)
                caption, text = emu.told[0]
                self.assertEqual(caption, "Revival Potion")
                self.assertIn(f"only {limit} plants can be for sale at once", text)
                self.assertIn("nurseries are full" if limit > 15 else "nursery is full", text)

    def test_a_plant_too_young_to_sell_is_not_put_on_sale(self) -> None:
        emu = self.greenhouse()
        pot = self.tagged(emu, 11)
        self.die(emu, 11)
        emu.uc.mem_write(pot + AGE, struct.pack("<f", 23.5))            # (only reachable by an edited save)
        self.use(emu, REVIVAL, 11)
        self.assertEqual(self.flags(emu, pot), bytes([0, 0, 0]))
        self.assertEqual(emu.told, [])


@unittest.skipUnless(E is not None and E.toolchain_ready() and PLANT_EXE is not None and PLANT_EXE.is_file(),
                     "needs Unicorn, the pinned MSVC toolset and the vanilla executable")
class ExtraGreenhousesMarkTests(unittest.TestCase):
    """Extra Greenhouses' own code (tests/test_extra_greenhouses.py's game: the vanilla game's new game,
    planting, updates and chemical switch, with that DLL): the stock chemicals in Greenhouses 1-6, and
    the mark (+0x9F) moving with its plant."""

    @classmethod
    def setUpClass(cls) -> None:
        import test_extra_greenhouses as EG
        EG._build()
        cls.EG = EG

    def test_no_stock_chemical_takes_a_plant_off_sale(self) -> None:
        # The switch's nine cases, chemicals 27-35, each run by the game on pot 7 of Greenhouse 1 and of
        # Greenhouse 4, with every live plant there for sale (the bombs reach all of them).
        EG = self.EG
        for g in (0, 3):
            for chemical in range(27, 36):
                game = EG.grow(g, 17, ((2, 13, 13), (7, 11, 10), (11, 22, 23)), (7200,))
                live = [k for k in (2, 7, 11) if game.emu.read32(game.pot(g, k) + HEALTH, signed=True) > 0]
                self.assertEqual(live[:2], [2, 7])
                for k in live:
                    game.emu.write8(game.pot(g, k) + FOR_SALE, 1)
                game.chemical(g, 7, chemical)
                for k in live:
                    self.assertEqual(game.emu.uc.mem_read(game.pot(g, k) + FOR_SALE, 1)[0], 1,
                                     f"chemical {chemical}, greenhouse {g + 1}, pot {k}")

    def test_the_mark_follows_the_plant_to_every_greenhouse_and_home(self) -> None:
        EG = self.EG
        for g in range(1, EG.EXTRA + 1):
            game = EG.Game()
            emu = game.emu
            home = game.pot(g, 7)
            emu.write8(home + KEPT_AT, KEPT)                             # Greenhouse g+1's dead plant
            game.show(g)                                                 # its greenhouse on screen
            state_pot = game.state + EG.POTS_AT + 7 * EG.POT
            self.assertEqual(emu.uc.mem_read(state_pot + KEPT_AT, 1)[0], KEPT, g)
            game.show(0, active=0)                                       # every other screen: home
            self.assertEqual(emu.uc.mem_read(game.pot(g, 7) + KEPT_AT, 1)[0], KEPT, g)
            self.assertEqual(emu.uc.mem_read(state_pot + KEPT_AT, 1)[0], 0, g)


if __name__ == "__main__":
    unittest.main()
