"""Sort Seeds (Plant Tycoon): the sort's rules and its setting.

native/ftfp_sort_seeds/sort_seeds_logic_harness.c compiles the companion's
own sort code against seed boxes built in memory and prints one line per
check: the order (class, foliage, flower, parents with unknown first, stable),
packing from the first unlocked slot, the first chest filled before the
second, locked drawers and chests never written, no seed lost or added, and
bad input refused. scripts/build_ftfp_sort_seeds.ps1 builds and runs it; when
its output is missing the logic test is skipped.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS_OUTPUT = ROOT / "build" / "ftfp_sort_seeds" / "logic.txt"
MANIFEST = ROOT / "data" / "plant_manifest.json"
VANILLA = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon"
           / "Plant Tycoon.exe")
sys.path.insert(0, str(ROOT / "src"))


class SortSeedsSettingTests(unittest.TestCase):
    def setUp(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.settings = {s["id"]: s for s in manifest["settings"]}

    def test_setting_ships_the_dll_and_button(self) -> None:
        setting = self.settings["sort_seeds"]
        self.assertEqual(setting["name"], "Sort Seeds button")
        companion = setting["companion"]
        self.assertTrue(companion["startup_loader"])
        targets = {f["destination"] for f in companion["files"]}
        self.assertEqual(targets, {"Plant Tycoon Fix Patcher DLLs/Sort Seeds.dll", "Images/sort_seeds_button.png"})
        for item in companion["files"]:
            data = (ROOT / companion["source"] / item["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(), item["sha256"].upper())

    @unittest.skipUnless(VANILLA.is_file(), "the vanilla Plant Tycoon.exe is not here")
    def test_on_its_own_the_loader_loads_sort_seeds(self) -> None:
        import ds_fish_loader
        import plant_patcher
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(ds_fish_loader.plant_profile({"sort_seeds"}).dll_name, "Sort Seeds.dll")
        self.assertEqual(ds_fish_loader.plant_profile({"sort_seeds", "new_flowers"}).dll_name, "Unused Flowers.dll")
        patched, _ = ds_fish_loader.append_startup_loader(VANILLA.read_bytes(), ds_fish_loader.plant_profile({"sort_seeds"}))
        self.assertIn("Sort Seeds.dll".encode("utf-16-le"), patched)
        self.assertEqual(hashlib.sha256(patched).hexdigest().upper(),
                         manifest["patched_sha256_by_settings"]["sort_seeds"])
        pins = manifest["patched_sha256_by_settings"]
        for key, value in pins.items():
            enabled = set(key.split(","))
            if "sort_seeds" in enabled and "new_flowers" in enabled:
                self.assertEqual(value, pins[plant_patcher.settings_key(enabled - {"sort_seeds"}, manifest)], key)

    def test_it_is_not_new_content(self) -> None:
        self.assertFalse(self.settings["sort_seeds"].get("separate_output", False))


@unittest.skipUnless(HARNESS_OUTPUT.is_file(), "build and run the Sort Seeds harness first (scripts/build_ftfp_sort_seeds.ps1)")
class SortSeedsLogicTests(unittest.TestCase):
    def test_every_check_passes(self) -> None:
        lines = HARNESS_OUTPUT.read_text(encoding="ascii").splitlines()
        self.assertEqual(lines[-1], "ALL OK", "\n".join(lines))
        self.assertGreaterEqual(sum(line.startswith("ok ") for line in lines), 12)
        self.assertFalse([line for line in lines if line.startswith("FAIL")])


if __name__ == "__main__":
    unittest.main()
