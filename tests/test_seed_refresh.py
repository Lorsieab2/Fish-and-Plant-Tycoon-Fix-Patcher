"""R refreshes the seed shop (Plant Tycoon): the setting, and an emulation proof.

The patched store key handler 0x447950 is run in Unicorn on the patched
executable's own bytes: r and R call the game's seed-shelf roll 0x41DC60 once,
with ecx = the game state ([store + 0x1BC]), and return 0; every other key the
store ignores returns 0 without calling it. Skipped when the vanilla
executable or Unicorn is missing.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import plant_patcher  # noqa: E402
import pin_seed_refresh  # noqa: E402

VANILLA = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon"
           / "Plant Tycoon.exe")
MANIFEST = ROOT / "data" / "plant_manifest.json"

try:
    import unicorn
    from unicorn import x86_const as X
except ImportError:          # pragma: no cover
    unicorn = None


class SettingTests(unittest.TestCase):
    def test_on_by_default_with_three_guarded_patches(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        setting = {s["id"]: s for s in manifest["settings"]}["seed_refresh_key"]
        self.assertTrue(setting["default"])
        self.assertNotIn("companion", setting)
        ids = {p["id"] for p in manifest["patches"] if p.get("requires") == ["seed_refresh_key"] and not p["id"].startswith("update_pe_checksum")}
        self.assertEqual(ids, {"seed_refresh_text_size", "seed_refresh_code", "seed_refresh_key_case"})


@unittest.skipUnless(VANILLA.is_file() and unicorn is not None, "needs the vanilla exe and unicorn")
class EmulationTests(unittest.TestCase):
    STATE = 0x00900000
    SCENE = 0x00800000
    STACK = 0x00700000
    RETURN = 0x00600000

    @classmethod
    def setUpClass(cls) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        data = VANILLA.read_bytes()
        cls.patched, _ = plant_patcher.apply_patch_bytes(
            data, plant_patcher.active_patch_records(manifest, {"seed_refresh_key"}))
        cls.vanilla = data

    def run_key(self, image: bytes, char: int) -> tuple[int, list[int]]:
        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        uc.mem_map(0x400000, 0x100000)
        uc.mem_write(0x401000, image[0x1000:0x1000 + 0x64000])         # .text, tail included
        uc.mem_write(0x465000, image[0x65000:0x65000 + 0x15000])       # .rdata
        for base in (self.STATE, self.SCENE, self.STACK, self.RETURN):
            uc.mem_map(base, 0x10000)
        uc.mem_write(self.SCENE + 0x1BC, struct.pack("<I", self.STATE))
        calls: list[int] = []

        def on_roll(uc_, address, size, user):
            calls.append(uc_.reg_read(X.UC_X86_REG_ECX))
            esp = uc_.reg_read(X.UC_X86_REG_ESP)
            ret = struct.unpack("<I", uc_.mem_read(esp, 4))[0]
            uc_.reg_write(X.UC_X86_REG_ESP, esp + 4)
            uc_.reg_write(X.UC_X86_REG_EIP, ret)

        uc.hook_add(unicorn.UC_HOOK_CODE, on_roll, begin=pin_seed_refresh.ROLL_VA, end=pin_seed_refresh.ROLL_VA)
        esp = self.STACK + 0x8000
        uc.mem_write(esp, struct.pack("<IIII", self.RETURN, 5, char, char))   # ret, msg 5, code, char
        uc.reg_write(X.UC_X86_REG_ESP, esp)
        uc.reg_write(X.UC_X86_REG_ECX, self.SCENE)
        uc.reg_write(X.UC_X86_REG_EAX, 0xFFFFFFFF)
        uc.emu_start(0x447950, self.RETURN, count=200)
        self.assertEqual(uc.reg_read(X.UC_X86_REG_ESP), esp + 16)          # ret 0xC
        return uc.reg_read(X.UC_X86_REG_EAX) & 0xFF, calls

    def test_r_and_capital_r_roll_the_seed_shelves(self) -> None:
        for char in (ord("r"), ord("R")):
            al, calls = self.run_key(self.patched, char)
            self.assertEqual(al, 0)
            self.assertEqual(calls, [self.STATE], chr(char))

    def test_other_ignored_keys_do_nothing(self) -> None:
        for char in (ord("3"), ord("a"), ord("q"), ord("t"), ord("6"), ord("Q")):
            al, calls = self.run_key(self.patched, char)
            self.assertEqual((al, calls), (0, []), chr(char))

    def test_vanilla_r_does_nothing(self) -> None:
        self.assertEqual(self.run_key(self.vanilla, ord("r")), (0, []))


if __name__ == "__main__":
    unittest.main()
