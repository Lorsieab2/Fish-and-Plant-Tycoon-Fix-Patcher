"""Fix Vanilla Bugs (Fish Tycoon): the store plants' swapped effects."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402
import pin_vanilla_fixes  # noqa: E402

VANILLA = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Fish Tycoon"
           / "Fish Tycoon.exe")


class VanillaFixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("fish")

    def test_setting_is_on_by_default_and_first(self) -> None:
        settings = combined.patch_settings("fish")
        self.assertEqual(list(settings)[0], "fix_vanilla_bugs")
        self.assertTrue(settings["fix_vanilla_bugs"]["default"])
        self.assertIn("Plant of Incubation", settings["fix_vanilla_bugs"]["summary"])

    def test_the_plant_effects_swap_their_dword(self) -> None:
        patches = {p["id"]: p for p in self.manifest["patches"] if p["id"].startswith("fix_plant_")}
        self.assertEqual(len(patches), 4)
        starving = patches["fix_plant_effect_starving"]
        self.assertEqual(int(starving["offset"], 16), 0x205A1)
        self.assertEqual((starving["expected"], starving["replacement"]), ("39 98 68 01 00 00", "39 98 7C 01 00 00"))
        for va in (0x4213DB, 0x4214AA, 0x42157D):
            patch = patches[f"fix_plant_effect_eggs_{va:X}"]
            self.assertEqual(int(patch["offset"], 16), va - 0x400000)
            self.assertEqual((patch["expected"], patch["replacement"]), ("8B 8F 7C 01 00 00", "8B 8F 68 01 00 00"))
        self.assertTrue(all(p["requires"] == ["fix_vanilla_bugs"] for p in patches.values()))

    @unittest.skipUnless(VANILLA.is_file(), "the vanilla Fish Tycoon.exe is not here")
    def test_on_the_vanilla_executable(self) -> None:
        data = VANILLA.read_bytes()
        records = fish_patcher.active_patch_records(self.manifest, {"fix_vanilla_bugs"})
        patched, _ = fish_patcher.apply_patch_bytes(data, records)
        self.assertEqual(struct.unpack_from("<I", patched, 0x205A3)[0], 0x17C)
        for va in (0x4213DB, 0x4214AA, 0x42157D):
            self.assertEqual(struct.unpack_from("<I", data, va + 2 - 0x400000)[0], 0x17C)
            self.assertEqual(struct.unpack_from("<I", patched, va + 2 - 0x400000)[0], 0x168)
        for index, ids in ((12, (198, 199)), (13, (200, 201))):      # the store itself is untouched
            at = 0x457EF0 + index * 0x34 + 0x2C - 0x400000
            self.assertEqual(struct.unpack_from("<2I", patched, at), ids)


if __name__ == "__main__":
    unittest.main()
