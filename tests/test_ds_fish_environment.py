"""DS fish need Fish Environment level 3, exactly like the game's rare fish.

The owner's rule: a fish with a DS body or a DS fin (exe genes 23-29) keeps
full health only at Fish Environment level 3, as the PC game's rare (odd-gene)
fish do. The game's health tick (0x41DF50) picks the step's health change by
the fish's tier and the Environment level (state + 0x258):

    tier 1 (common)     +1 / +3 / +5      (0x41E011)
    tier 2 (half-rare)  -1 / +1 / +3      (0x41E035)
    tier 3 (rare)      -19 / -6 /  0      (0x41E059)

DS Exclusive Fish.dll replaces the tier test at 0x41DF68 (stub_tier_health)
and gives every fish with a DS part tier 3 (health_tier). Here the vanilla
executable runs its own tick in Unicorn with the DLL installed by its own
FtfpStartup (every site byte-checked, all or nothing): a DS-body fish, a
DS-fin fish and a stock rare fish change health identically at levels 1, 2
and 3, full health only at level 3, and stock common and half-rare fish are
unchanged. The sickness odds (the body's own tier, 0x41E157) and the tutorial
goal (0x41FC0F) keep the DS genes' own tiers.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
DLL = ROOT / "assets" / "fish_tycoon_ds" / "DS Exclusive Fish.dll"

HEALTH_TICK = 0x0041DF50
STATE_PTR = 0x34                         # the tank object's game state ([edi + 0x34])
ENVIRONMENT = 0x258                      # Fish Environment research level, 1-3
TEMPERATURE, AERATION, DIFFICULTY = 0x12C, 0x118, 0x14
F_HEALTH, F_SICK, F_FOOD, F_BODY, F_FIN = 0x3C, 0x40, 0x44, 0x4C, 0x50

RARE_STEP = {1: -19, 2: -6, 3: 0}        # the stock rare fish (0x41E059)
COMMON_STEP = {1: 1, 2: 3, 3: 5}         # 0x41E011
HALF_STEP = {1: -1, 2: 1, 3: 3}          # 0x41E035
DS_GENES = range(23, 30)
TEB, GDT = 0x7FFD0000, 0x7FFE0000


def thread_block(emu) -> None:
    """fs: a TEB with an empty SEH chain, for FtfpStartup's __try (as tests/test_every_patch.py)."""
    from unicorn import x86_const as X
    uc = emu.uc
    uc.mem_map(TEB, 0x2000)
    uc.mem_write(TEB, struct.pack("<7I", 0xFFFFFFFF, E.STACK + E.STACK_SIZE, E.STACK, 0, 0, 0, TEB))
    uc.mem_map(GDT, 0x1000)

    def descriptor(base: int, limit: int, flags: int) -> bytes:
        return struct.pack("<Q", (limit & 0xFFFF) | (base & 0xFFFFFF) << 16 | 0x92 << 40
                           | (limit >> 16 & 0xF) << 48 | flags << 52 | (base >> 24) << 56)
    uc.mem_write(GDT + 8 * 2, descriptor(0, 0xFFFFF, 0xC))
    uc.mem_write(GDT + 8 * 3, descriptor(TEB, 0xFFF, 0x4))
    uc.reg_write(X.UC_X86_REG_GDTR, (0, GDT, 0xFFF, 0))
    for reg in (X.UC_X86_REG_SS, X.UC_X86_REG_DS, X.UC_X86_REG_ES):
        uc.reg_write(reg, 2 << 3)
    uc.reg_write(X.UC_X86_REG_FS, 3 << 3)


@unittest.skipUnless(E is not None and EXE is not None and EXE.is_file() and DLL.is_file()
                     and E.toolchain_ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class DsFishEnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        _, cls.symbols = E.build_with_map("ftfp_ds_fish", DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def game(self, installed: bool = True):
        emu = E.Emulator(EXE, DLL, self.symbols)
        thread_block(emu)
        emu.hook_import("GetModuleFileNameW", lambda e: 0, 12)     # no log, no companions beside it
        emu.hook_import("GetFileAttributesW", lambda e: 0xFFFFFFFF, 4)

        def protect(e):
            if e.arg(3):
                e.write32(e.arg(3), 0x20)
            return 1
        emu.hook_import("VirtualProtect", protect, 16)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.hook(0x00403240, lambda e: self.fail("the tick rolled a die with no tank items"), 4)
        if installed:
            self.assertEqual(emu.call(self.symbols["_FtfpStartup@0"]), 1, "DS Fish installed")
            self.assertEqual(emu.uc.mem_read(0x41DF68, 1)[0], 0xE9, "the health tier test is hooked")
        return emu

    def step(self, emu, body: int, fin: int, level: int, health: int) -> int:
        """One health tick of one fish at an Environment level; its new health."""
        state, tank, fish = emu.alloc(0x400), emu.alloc(0x40), emu.alloc(0x100)
        emu.write32(state + ENVIRONMENT, level)
        for offset, value in ((TEMPERATURE, 0), (AERATION, 0), (DIFFICULTY, 1)):   # no random +1s
            emu.write32(state + offset, value)
        emu.write32(tank + STATE_PTR, state)
        for offset, value in ((F_HEALTH, health), (F_SICK, 0), (F_FOOD, 50), (F_BODY, body), (F_FIN, fin)):
            emu.write32(fish + offset, value)
        emu.call(HEALTH_TICK, fish, ecx=tank)
        return emu.read32(fish + F_HEALTH, signed=True)

    def changes(self, emu, body: int, fin: int) -> dict[int, int]:
        return {level: self.step(emu, body, fin, level, 50) - 50 for level in (1, 2, 3)}

    def test_ds_body_ds_fin_and_stock_rare_fish_are_identical(self) -> None:
        emu = self.game()
        stock_rare = self.changes(emu, 13, 13)                       # Sunburst Rattlefish: odd genes
        self.assertEqual(stock_rare, RARE_STEP)
        for gene in DS_GENES:
            with self.subTest(gene=gene):
                self.assertEqual(self.changes(emu, gene, 0), stock_rare, "DS body, common PC fin")
                self.assertEqual(self.changes(emu, 0, gene), stock_rare, "common PC body, DS fin")
                self.assertEqual(self.changes(emu, gene, gene), stock_rare, "DS body and fin")
                self.assertEqual(self.changes(emu, gene, 2), stock_rare, "DS body, half-rare PC fin")

    def test_full_health_only_at_level_3(self) -> None:
        emu = self.game()
        for body, fin in ((26, 0), (0, 26), (24, 28), (13, 13)):   # 26 Trigger / Clown, the DS "common" gene
            with self.subTest(fish=(body, fin)):
                self.assertEqual(self.step(emu, body, fin, 3, 100), 100)
                self.assertEqual(self.step(emu, body, fin, 2, 100), 94)
                self.assertEqual(self.step(emu, body, fin, 1, 100), 81)
                self.assertEqual(self.step(emu, body, fin, 1, 10), 0, "clamped at 0: it dies")

    def test_stock_fish_are_unchanged(self) -> None:
        installed, vanilla = self.game(), self.game(installed=False)
        for body in range(21):
            for fin in range(21):
                for level in (1, 2, 3):
                    with self.subTest(fish=(body, fin), level=level):
                        self.assertEqual(self.step(installed, body, fin, level, 50),
                                         self.step(vanilla, body, fin, level, 50))
        self.assertEqual(self.changes(installed, 0, 4), COMMON_STEP)      # a stock Level 1 fish
        self.assertEqual(self.changes(installed, 2, 4), HALF_STEP)

    def test_the_rest_keeps_the_ds_tiers(self) -> None:
        """Only the health tick changed: the tier the rest of the DLL uses is still the DS game's."""
        source = (ROOT / "native" / "ftfp_ds_fish" / "ftfp_ds_fish.c").read_text(encoding="utf-8")
        self.assertIn("call health_tier", source)
        self.assertEqual(source.count("call health_tier"), 1)
        self.assertIn("call gene_tier", source)                            # sickness: the body's own tier
        self.assertIn("call rare_pair", source)                            # tutorial goal 0x17


if __name__ == "__main__":
    unittest.main()
