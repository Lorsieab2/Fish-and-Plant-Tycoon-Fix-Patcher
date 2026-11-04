"""Disable Press C for Cash Cheat: "No C Cheat.dll" changes the byte at 0x41ED75 (the distance of
the key handler's `je` for 'c') so 'c' skips the +$1000. Run in Unicorn from the DLL's own
FtfpStartup; skipped without Unicorn, the pinned MSVC toolset or the vanilla executable.
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
DLL = ROOT / "assets" / "fish_tycoon_no_c_cheat" / "No C Cheat.dll"
SITE, HANDLER = 0x41ED75, 0x41ED10
SETTING = "disable_c_cheat"


def manifest() -> dict:
    return json.loads((ROOT / "data" / "fish_manifest.json").read_text(encoding="utf-8"))


class SettingTests(unittest.TestCase):
    def test_the_setting_is_a_default_loader_tail_in_every_preset(self) -> None:
        m = manifest()
        setting = next(s for s in m["settings"] if s["id"] == SETTING)
        self.assertEqual(setting["name"], "Disable Press C for Cash Cheat")
        self.assertTrue(setting["default"])
        self.assertEqual(setting["companion"]["loader_tail"], "No C Cheat.dll")
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
        self.assertIn("assets/fish_tycoon_no_c_cheat/No C Cheat.dll", build_release.bundled_asset_files())


def needs():
    ready = E is not None and E.toolchain_ready() and EXE is not None and EXE.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


@needs()
class PatchedBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_no_c_cheat", DLL, Path(cls.tmp.name))

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
            path = "C:\\Game\\Fish Tycoon Fix Patcher DLLs\\No C Cheat.dll"
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

    def press(self, emu, char: str) -> int:
        """Run the key handler 0x41ED10 for one typed character: the money after (starts at 5000)."""
        game = emu.alloc(0x20000)
        emu.write32(game + 0x38C, 5000)
        emu.hook(0x41B070, lambda e: game, 0)            # the game-state getter
        emu.write32(E.STACK + E.STACK_SIZE - 0x2000, 0)
        sp = E.STACK + E.STACK_SIZE - 0x1000
        for off, val in ((0, 0x1234), (4, 5), (8, 0), (12, ord(char)), (16, 0)):
            emu.write32(sp + off, val)                   # return, message 5, p, the key, q
        emu.uc.reg_write(X.UC_X86_REG_ESP, sp)
        emu.uc.reg_write(X.UC_X86_REG_ECX, emu.alloc(0x40))
        emu.uc.mem_write(emu.uc.reg_read(X.UC_X86_REG_ECX), struct.pack("<I", emu.alloc(0x40)))
        emu.uc.emu_start(HANDLER, 0x1234, count=1000)
        self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_EIP), 0x1234)
        self.money_flag = emu.uc.mem_read(game + 0x1E50C, 1)[0]
        return int.from_bytes(emu.uc.mem_read(game + 0x38C, 4), "little")

    def test_the_vanilla_executable_holds_the_stock_byte(self) -> None:
        data = EXE.read_bytes()
        code = bytes.fromhex("83e8637430" "83e81274")       # sub 0x63 / je +0x30 / sub 0x12 / je
        self.assertEqual(data.count(code), 1)
        self.assertEqual(data[data.index(code) + 4], 0x30)

    def test_it_installs_and_logs_installed(self) -> None:
        emu = self.emulator()
        self.assertEqual(self.install(emu), 1)
        self.assertEqual(emu.call(emu.sym("_FtfpNoCCheatInstalled@0")), 1)
        self.assertEqual(emu.logs, ["No C Cheat: installed\r\n"])
        self.assertEqual(emu.protects, [(SITE, 1, 0x40), (SITE, 1, 0x20)])

    def test_it_writes_nothing_when_the_code_is_not_stock(self) -> None:
        emu = self.emulator(b"\x31")
        self.assertEqual(self.install(emu), 0)
        self.assertEqual(bytes(emu.uc.mem_read(SITE, 1)), b"\x31")
        self.assertEqual(emu.protects, [])
        self.assertTrue(emu.logs[0].startswith("No C Cheat: not installed ("), emu.logs)

    def test_c_adds_nothing_after_and_1000_before(self) -> None:
        emu = self.emulator()
        self.assertEqual(self.press(emu, "c"), 6000, "stock")
        self.assertEqual(self.install(emu), 1)
        self.assertEqual(self.press(emu, "c"), 5000)
        self.assertEqual(self.press(emu, "x"), 5000)

    def test_u_and_w_behave_as_stock(self) -> None:
        for char in "uw":
            stock = self.emulator()
            before = self.press(stock, char), self.money_flag
            patched = self.emulator()
            self.assertEqual(self.install(patched), 1)
            self.assertEqual((self.press(patched, char), self.money_flag), before, char)
        self.assertEqual(self.press(self.emulator(), "u"), 5000)
        self.assertEqual(self.money_flag, 1, "u sets the registered flag (0x1E50C)")


if __name__ == "__main__":
    unittest.main()
