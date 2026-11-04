"""Snail and Plant of Curing stack: "Snail and Curing.dll" rewrites the sickness tick's 42 bytes
at 0x41E21C (up to 0x41E246) so the Plant of Curing halves X and the Cleaning Snail then halves
it again on a roll of 49 or less. Run in Unicorn from the DLL's own FtfpStartup; skipped without
Unicorn, the pinned MSVC toolset or the vanilla executable.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

import build_release  # noqa: E402

EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
DLL = ROOT / "assets" / "fish_tycoon_snail_curing" / "Snail and Curing.dll"
SITE, END, RANDOM = 0x41E21C, 0x41E246, 0x403240
PLANT, SNAIL = 0x190, 0x140
STOCK = bytes.fromhex("83bf90010000007518" "83bf4001000000" "7418" "6a64" "e80b50feff" "83c404"
                      "83f8317f09" "8bc699" "2bc2d1f88bf0")
SETTING = "snail_curing_stack"


def manifest() -> dict:
    return json.loads((ROOT / "data" / "fish_manifest.json").read_text(encoding="utf-8"))


def halve(x: int) -> int:
    """The stock halving: mov eax,esi / cdq / sub eax,edx / sar eax,1."""
    return (x + (1 if x < 0 else 0)) >> 1


class SettingTests(unittest.TestCase):
    def test_the_setting_is_a_default_loader_tail_in_every_preset(self) -> None:
        m = manifest()
        setting = next(s for s in m["settings"] if s["id"] == SETTING)
        self.assertEqual(setting["name"], "Snail and Plant of Curing stack")
        self.assertTrue(setting["default"])
        self.assertEqual(setting["companion"]["loader_tail"], "Snail and Curing.dll")
        entry = setting["companion"]["files"][0]
        self.assertEqual(entry["size"], len(DLL.read_bytes()))
        import hashlib
        self.assertEqual(entry["sha256"], hashlib.sha256(DLL.read_bytes()).hexdigest().upper())
        sys.path.insert(0, str(ROOT / "src"))
        import fish_patcher
        import tycoon_fix_patcher_gui as gui
        self.assertIn(SETTING, fish_patcher.loader_tail_dlls(m, {SETTING}))
        self.assertNotIn(SETTING, fish_patcher.pin_settings(m, {SETTING, "fix_vanilla_bugs"}))
        self.assertIn(SETTING, gui.preset_selection("owners_defaults", "fish"))
        self.assertIn(SETTING, gui.preset_selection("default_patches", "fish"))
        self.assertNotIn(SETTING, gui.OWNERS_DEFAULTS_OFF)

    def test_the_release_includes_the_dll(self) -> None:
        self.assertIn("assets/fish_tycoon_snail_curing/Snail and Curing.dll", build_release.bundled_asset_files())


def needs():
    ready = E is not None and E.toolchain_ready() and EXE is not None and EXE.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


@needs()
class PatchedBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_snail_curing", DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def emulator(self, stock: bytes | None = None):
        emu = E.Emulator(EXE, self.dll, self.symbols)
        emu.uc.mem_map(0, 0x1000)             # fs:[0] for __try's SEH frame
        emu.protects = []
        emu.logs = []

        def protect(e) -> int:
            emu.protects.append((e.arg(0), e.arg(1), e.arg(2)))
            e.write32(e.arg(3), 0x20)
            return 1

        def module_name(e) -> int:
            path = "C:\\Game\\Fish Tycoon Fix Patcher DLLs\\Snail and Curing.dll"
            e.uc.mem_write(e.arg(1), path.encode("utf-16-le") + b"\0\0")
            return len(path)

        def write_file(e) -> int:
            emu.logs.append(bytes(e.uc.mem_read(e.arg(1), e.arg(2))).decode("latin-1"))
            return 1

        emu.hook_import("VirtualProtect", protect, 16)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.hook_import("GetModuleFileNameW", module_name, 12)
        emu.hook_import("CreateFileW", lambda e: 5, 28)
        emu.hook_import("WriteFile", write_file, 20)
        emu.hook_import("CloseHandle", lambda e: 1, 4)
        if stock is not None:
            emu.uc.mem_write(SITE, stock)
        return emu

    def install(self, emu) -> int:
        return emu.call(emu.sym("_FtfpStartup@0"))

    def run_block(self, emu, x: int, plant: int, snail: int, roll: int) -> tuple[int, int]:
        """Run the 42 bytes with X in esi: (X after, how many times Random was called)."""
        game = emu.alloc(0x400)
        emu.write32(game + PLANT, plant)
        emu.write32(game + SNAIL, snail)
        rolls = []

        def random(e) -> int:
            rolls.append(e.arg(0))
            return roll

        emu.hook(RANDOM, random)
        emu.uc.reg_write(X.UC_X86_REG_EDI, game)
        emu.uc.reg_write(X.UC_X86_REG_ESI, x)
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        emu.uc.emu_start(SITE, END, count=1000)
        self.assertEqual(rolls, [100] * len(rolls))
        self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_EIP), END)
        self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_ESP), E.STACK + E.STACK_SIZE - 0x1000, "Random is cleaned up")
        return emu.uc.reg_read(X.UC_X86_REG_ESI), len(rolls)

    def test_the_vanilla_executable_holds_the_stock_bytes(self) -> None:
        data = EXE.read_bytes()
        self.assertEqual(len(STOCK), END - SITE)
        self.assertEqual(data.count(STOCK), 1)
        self.assertIn(b"\x8b\x43\x34\x83\x78\x14", data[data.index(STOCK) + 42:][:6])

    def test_it_installs_and_logs_installed(self) -> None:
        emu = self.emulator()
        self.assertEqual(self.install(emu), 1)
        self.assertEqual(emu.call(emu.sym("_FtfpSnailCuringInstalled@0")), 1)
        self.assertEqual(emu.logs, ["Snail and Curing: installed\r\n"])
        self.assertEqual(emu.protects, [(SITE, 42, 0x40), (SITE, 42, 0x20)])
        self.assertNotEqual(bytes(emu.uc.mem_read(SITE, 42)), STOCK)

    def test_it_writes_nothing_when_the_code_is_not_stock(self) -> None:
        other = bytearray(STOCK)
        other[20] ^= 1
        emu = self.emulator(bytes(other))
        self.assertEqual(self.install(emu), 0)
        self.assertEqual(bytes(emu.uc.mem_read(SITE, 42)), bytes(other))
        self.assertEqual(emu.protects, [])
        self.assertTrue(emu.logs[0].startswith("Snail and Curing: not installed ("), emu.logs)

    def test_every_case(self) -> None:
        emu = self.emulator()
        self.assertEqual(self.install(emu), 1)
        for x in (1, 2, 3, 5, 10, 20, 30, 33, 7, 11):
            for plant, snail, roll, quarter in (
                    (0, 0, 0, x), (0, 0, 99, x),
                    (0, 1, 49, halve(x)), (0, 1, 0, halve(x)), (0, 1, 50, x), (0, 1, 99, x),
                    (1, 0, 0, halve(x)), (1, 0, 99, halve(x)),
                    (1, 1, 49, halve(halve(x))), (1, 1, 0, halve(halve(x))),
                    (1, 1, 50, halve(x)), (1, 1, 99, halve(x))):
                with self.subTest(x=x, plant=plant, snail=snail, roll=roll):
                    after, rolled = self.run_block(emu, x, plant, snail, roll)
                    self.assertEqual(after, quarter)
                    self.assertEqual(rolled, 1 if snail else 0)

    def test_the_stock_block_never_stacks(self) -> None:
        """The same harness on the unpatched bytes: plant and snail together halve once."""
        emu = self.emulator()
        for plant, snail, roll, expect in ((1, 1, 0, 10), (0, 1, 0, 10), (1, 0, 0, 10), (0, 0, 0, 20)):
            after, _ = self.run_block(emu, 20, plant, snail, roll)
            self.assertEqual(after, expect, (plant, snail))


if __name__ == "__main__":
    unittest.main()
