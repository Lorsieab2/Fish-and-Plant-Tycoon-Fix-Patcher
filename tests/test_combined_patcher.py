from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fish_patcher
import plant_patcher
import tycoon_fix_patcher as combined
import tycoon_fix_patcher_gui as gui


class CombinedPatcherTests(unittest.TestCase):
    def test_exact_two_game_contract(self) -> None:
        self.assertEqual(list(combined.GAMES), ["fish", "plant"])
        self.assertEqual(combined.GAMES["fish"].exe_name, "Fish Tycoon.exe")
        self.assertEqual(combined.GAMES["plant"].exe_name, "Plant Tycoon.exe")
        self.assertEqual(
            combined.GAMES["fish"].modded_exe_name,
            "Fish Tycoon - Modded.exe",
        )
        self.assertEqual(
            combined.GAMES["plant"].modded_exe_name,
            "Plant Tycoon - Modded.exe",
        )

    def test_default_output_folders_are_separate_siblings(self) -> None:
        fish = combined.default_output_dir("fish", Path("C:/Games/Fish Tycoon"))
        plant = combined.default_output_dir("plant", Path("C:/Games/Plant Tycoon"))
        self.assertEqual(fish.as_posix(), "C:/Games/Fish Tycoon - Modded")
        self.assertEqual(plant.as_posix(), "C:/Games/Plant Tycoon - Modded")

    def test_chosen_parent_creates_only_exact_modded_folder_names(self) -> None:
        parent = Path("C:/My Modified Games")
        self.assertEqual(
            combined.output_dir_at("fish", parent).as_posix(),
            "C:/My Modified Games/Fish Tycoon - Modded",
        )
        self.assertEqual(
            combined.output_dir_at("plant", parent).as_posix(),
            "C:/My Modified Games/Plant Tycoon - Modded",
        )

    def test_find_game_in_parent_checks_root_and_immediate_children(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fish_dir = root / "Installed Fish"
            fish_dir.mkdir()
            fish_exe = fish_dir / "Fish Tycoon.exe"
            fish_exe.write_bytes(b"fish")
            nested = fish_dir / "Too Deep"
            nested.mkdir()
            (nested / "Fish Tycoon.exe").write_bytes(b"ignored")
            self.assertEqual(
                combined.find_game_in_parent("fish", root),
                [fish_exe],
            )

    def test_find_game_in_parent_requires_exact_vanilla_name(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Fish Tycoon - Modded.exe").write_bytes(b"modded")
            self.assertEqual(combined.find_game_in_parent("fish", root), [])

    def test_manifests_pin_exact_modded_executable_names(self) -> None:
        self.assertEqual(
            combined.load_manifest("fish")["output"]["exe_name"],
            "Fish Tycoon - Modded.exe",
        )
        self.assertEqual(
            combined.load_manifest("plant")["output"]["exe_name"],
            "Plant Tycoon - Modded.exe",
        )

    def test_apply_removes_vanilla_exe_name_from_modded_folder(self) -> None:
        for game_id, engine in (
            ("fish", fish_patcher),
            ("plant", plant_patcher),
        ):
            spec = combined.GAMES[game_id]
            with self.subTest(game=game_id), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                vanilla = root / spec.title
                output = root / spec.modded_folder_name
                vanilla.mkdir()
                source = vanilla / spec.vanilla_exe_name
                source.write_bytes(b"test executable")
                (vanilla / "support.dat").write_bytes(b"support")
                args = Namespace(
                    game_dir=str(vanilla),
                    manifest=str(spec.manifest_path),
                    output_dir=str(output),
                    dry_run=False,
                    enable=[],
                    disable=None,
                    disable_all=True,
                )
                identity = {
                    "path": str(source),
                    "sha256": engine.sha256_file(source),
                }
                with mock.patch.object(
                    engine, "validate_original_executable", return_value=identity
                ):
                    self.assertEqual(engine.apply_manifest(args), 0)
                self.assertFalse((output / spec.vanilla_exe_name).exists())
                self.assertTrue((output / spec.modded_exe_name).is_file())
                self.assertEqual((output / "support.dat").read_bytes(), b"support")

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

    def test_requested_creator_description_is_exact(self) -> None:
        self.assertEqual(
            gui.CREATOR_DESCRIPTION,
            "🪴 Created with Codex AI. Made with love by Lorsieab2 :) 🐟",
        )
        self.assertEqual(
            gui.CREATOR_TEXT,
            "Created with Codex AI. Made with love by Lorsieab2 :)",
        )

    def test_supplied_picture_assets_are_used(self) -> None:
        self.assertEqual(gui.FISH_PICTURE_PATH, ROOT / "assets" / "fish.png")
        self.assertEqual(gui.PLANT_PICTURE_PATH, ROOT / "assets" / "plant.png")
        self.assertTrue(gui.FISH_PICTURE_PATH.is_file())
        self.assertTrue(gui.PLANT_PICTURE_PATH.is_file())
        source = (ROOT / "src" / "tycoon_fix_patcher_gui.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('text="🐟🪴"', source)
        self.assertIn("self.iconphoto(True, self.window_icon)", source)
        self.assertIn("image=self.plant_heading", source)
        self.assertIn("image=self.fish_heading", source)


if __name__ == "__main__":
    unittest.main()
