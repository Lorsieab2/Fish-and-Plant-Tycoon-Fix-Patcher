"""Fix Vanilla Bugs (Fish Tycoon): the store plants' swapped labels."""

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

    def test_the_two_plant_records_swap_their_name_and_description(self) -> None:
        patches = {p["id"]: p for p in self.manifest["patches"] if p["id"].startswith("fix_plant_labels_")}
        self.assertEqual(set(patches), {"fix_plant_labels_12", "fix_plant_labels_13"})
        for index, before, after in ((12, (198, 199), (200, 201)), (13, (200, 201), (198, 199))):
            patch = patches[f"fix_plant_labels_{index}"]
            self.assertEqual(int(patch["offset"], 16), 0x457EF0 + index * 0x34 + 0x2C - 0x400000)
            self.assertEqual(struct.unpack("<2I", bytes.fromhex(patch["expected"].replace(" ", ""))), before)
            self.assertEqual(struct.unpack("<2I", bytes.fromhex(patch["replacement"].replace(" ", ""))), after)
            self.assertEqual(patch["requires"], ["fix_vanilla_bugs"])

    @unittest.skipUnless(VANILLA.is_file(), "the vanilla Fish Tycoon.exe is not here")
    def test_on_the_vanilla_executable(self) -> None:
        data = VANILLA.read_bytes()
        for index, ids in ((12, (198, 199)), (13, (200, 201))):
            at = 0x457EF0 + index * 0x34
            self.assertEqual(struct.unpack_from("<I", data, at + 0x10 - 0x400000)[0], index)
            self.assertEqual(struct.unpack_from("<2I", data, at + 0x2C - 0x400000), ids)
        records = fish_patcher.active_patch_records(self.manifest, {"fix_vanilla_bugs"})
        patched, _ = fish_patcher.apply_patch_bytes(data, records)
        self.assertEqual(struct.unpack_from("<2I", patched, 0x457EF0 + 12 * 0x34 + 0x2C - 0x400000), (200, 201))
        self.assertEqual(struct.unpack_from("<2I", patched, 0x457EF0 + 13 * 0x34 + 0x2C - 0x400000), (198, 199))


if __name__ == "__main__":
    unittest.main()
