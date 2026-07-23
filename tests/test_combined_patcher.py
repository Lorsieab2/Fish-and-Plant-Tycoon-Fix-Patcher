from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fish_patcher
import plant_patcher
import tycoon_fix_patcher as combined


class CombinedPatcherTests(unittest.TestCase):
    def test_exact_two_game_contract(self) -> None:
        self.assertEqual(list(combined.GAMES), ["fish", "plant"])
        self.assertEqual(combined.GAMES["fish"].exe_name, "Fish Tycoon.exe")
        self.assertEqual(combined.GAMES["plant"].exe_name, "Plant Tycoon.exe")

    def test_default_output_folders_are_separate_siblings(self) -> None:
        fish = combined.default_output_dir("fish", Path("C:/Games/Fish Tycoon"))
        plant = combined.default_output_dir("plant", Path("C:/Games/Plant Tycoon"))
        self.assertEqual(fish.as_posix(), "C:/Games/Fish Tycoon - Fixed")
        self.assertEqual(plant.as_posix(), "C:/Games/Plant Tycoon - Fixed")

    def test_current_manifest_versions_and_default_settings(self) -> None:
        fish = combined.load_manifest("fish")
        plant = combined.load_manifest("plant")
        self.assertEqual(fish["version"], "v1.2.4")
        self.assertEqual(plant["version"], "v1.0.0")
        self.assertEqual(
            list(combined.patch_settings("fish")),
            [
                "crimson_comet_20_percent_cure",
                "unknown_chemical_three_uses",
                "universal_supply_slots",
            ],
        )
        self.assertEqual(
            list(combined.patch_settings("plant")),
            ["no_old_age_plant_deaths"],
        )

    def test_all_fish_setting_combinations_have_pinned_hashes(self) -> None:
        manifest = combined.load_manifest("fish")
        for key, digest in manifest["patched_sha256_by_settings"].items():
            self.assertTrue(key)
            self.assertEqual(len(digest), 64)

    def test_disable_all_is_supported_by_both_engines(self) -> None:
        args = Namespace(disable_all=True, enable=None, disable=None)
        self.assertEqual(
            fish_patcher.enabled_settings(combined.load_manifest("fish"), args),
            set(),
        )
        self.assertEqual(
            plant_patcher.enabled_settings(combined.load_manifest("plant"), args),
            set(),
        )

    def test_both_resource_sections_are_pinned_for_icon_preservation(self) -> None:
        for game_id in combined.GAMES:
            resource = combined.load_manifest(game_id)["target"]["resource_section"]
            self.assertEqual(resource["name"], ".rsrc")
            self.assertGreater(resource["size"], 0)
            self.assertEqual(len(resource["sha256"]), 64)

    def test_patch_ranges_apply_to_synthetic_guarded_inputs(self) -> None:
        for game_id, engine in (
            ("fish", fish_patcher),
            ("plant", plant_patcher),
        ):
            manifest = combined.load_manifest(game_id)
            enabled = set(combined.patch_settings(game_id))
            records = engine.active_patch_records(manifest, enabled)
            data = bytearray(int(manifest["target"]["size"]))
            for record in records:
                offset = engine.parse_int(record["offset"], "offset")
                expected = engine.parse_hex(record["expected"], "expected")
                data[offset : offset + len(expected)] = expected
            result, summary = engine.apply_patch_bytes(bytes(data), records)
            self.assertEqual(len(summary), len(records))
            for record in records:
                offset = engine.parse_int(record["offset"], "offset")
                replacement = engine.parse_hex(record["replacement"], "replacement")
                self.assertEqual(
                    result[offset : offset + len(replacement)], replacement
                )

    def test_restore_interface_is_exposed(self) -> None:
        self.assertTrue(callable(combined.restore_game))


if __name__ == "__main__":
    unittest.main()
