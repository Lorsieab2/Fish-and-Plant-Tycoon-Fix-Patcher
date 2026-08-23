from __future__ import annotations

from argparse import Namespace
import itertools
import json
import re
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
        self.assertEqual(fish["version"], "v1.2.10")
        self.assertEqual(plant["version"], "v1.0.0")
        self.assertEqual(
            list(combined.patch_settings("fish")),
            [
                "crimson_comet_20_percent_cure",
                "unknown_chemical_three_uses",
                "universal_supply_slots",
                "golden_seahorse_repurchase",
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
            "🪴 Created with Codex AI, with contributions from Claude AI. Made with love by Lorsieab2 :) 🐟",
        )
        self.assertEqual(
            gui.CREATOR_TEXT,
            "Created with Codex AI, with contributions from Claude AI. Made with love by Lorsieab2 :)",
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


class FinderAndRefusalTests(unittest.TestCase):
    def _install(self, root: Path, folder: str, exe: str) -> Path:
        directory = root / folder
        directory.mkdir(parents=True, exist_ok=True)
        (directory / exe).write_bytes(b"exe")
        return directory











    def test_unsupported_build_is_refused_with_the_supported_source(self) -> None:
        # A copy from anywhere else reaches the identity check and must be told
        # where the supported download lives, not just shown a hash mismatch.
        for module, manifest_name, exe_name in (
            (fish_patcher, "fish_manifest.json", "Fish Tycoon.exe"),
            (plant_patcher, "plant_manifest.json", "Plant Tycoon.exe"),
        ):
            manifest = module.read_json(ROOT / "data" / manifest_name)
            with tempfile.TemporaryDirectory() as raw:
                exe = Path(raw) / exe_name
                exe.write_bytes(b"a build this patcher does not support")
                with self.assertRaises(module.PatchError) as caught:
                    module.validate_original_executable(exe, manifest)
            self.assertIn("ldw.com", str(caught.exception))

    def test_gui_exposes_the_finder_and_preset_controls(self) -> None:
        for name in (
            "_build_detect_box",
            "_find_one",
            "_find_both",
            "_apply_detected",
            "_set_all_patches",
            "_reset_patches_to_defaults",
            "_set_busy",
        ):
            self.assertTrue(callable(getattr(gui.App, name)), name)
        source = (ROOT / "src" / "tycoon_fix_patcher_gui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('text="Find Both in Parent Folder..."', source)
        self.assertNotIn("scan_for_games", source)
        self.assertIn('("Enable All", ', source)
        self.assertIn('("Disable All", ', source)
        self.assertIn('("Defaults", ', source)
        # The page is taller than the window, so the body must stay scrollable.
        self.assertIn("self.content_canvas", source)
        self.assertIn('self.bind_all("<MouseWheel>", self._scroll_content)', source)


class SectionLayoutTests(unittest.TestCase):
    """Guards the PE section layout every setting combination produces.

    A patch that grows a section's VirtualSize past the next section's
    VirtualAddress makes an image the Windows loader refuses outright, with
    "This app can't run on your PC" and no other clue. These checks run against
    the layout recorded in the manifest, so they need no copy of the game.
    """

    def _layout(self, game_id: str) -> list[dict]:
        target = combined.load_manifest(game_id)["target"]
        return target.get("section_layout", [])

    def _combinations(self, game_id: str):
        ids = sorted(combined.patch_settings(game_id))
        for size in range(len(ids) + 1):
            for combo in itertools.combinations(ids, size):
                yield set(combo)

    def test_fish_records_its_section_layout(self) -> None:
        layout = self._layout("fish")
        self.assertTrue(layout, "fish manifest must record target.section_layout")
        self.assertEqual(
            [section["name"] for section in layout],
            [".text", ".rdata", ".data", ".shr", ".rsrc"],
        )

    def test_no_setting_combination_overruns_the_next_section(self) -> None:
        for game_id in combined.GAMES:
            layout = self._layout(game_id)
            if not layout:
                continue
            engine = combined.GAMES[game_id].engine
            manifest = combined.load_manifest(game_id)
            # File offset of each section's VirtualSize field.
            size_fields = {
                int(section["header_offset"], 0) + 8: section["name"]
                for section in layout
            }
            for enabled in self._combinations(game_id):
                sizes = {
                    section["name"]: int(section["virtual_size"], 0)
                    for section in layout
                }
                for patch in engine.active_patch_records(manifest, enabled):
                    offset = int(str(patch["offset"]), 0)
                    name = size_fields.get(offset)
                    if name is None:
                        continue
                    raw = bytes.fromhex("".join(str(patch["replacement"]).split()))
                    self.assertEqual(len(raw), 4, f"{patch['id']} must write 4 bytes")
                    sizes[name] = int.from_bytes(raw, "little")
                ordered = sorted(
                    layout, key=lambda section: int(section["virtual_address"], 0)
                )
                for current, following in zip(ordered, ordered[1:]):
                    end = int(current["virtual_address"], 0) + sizes[current["name"]]
                    start = int(following["virtual_address"], 0)
                    self.assertLessEqual(
                        end,
                        start,
                        f"{game_id} [{combined.GAMES[game_id].engine.settings_key(enabled) or 'none'}]: "
                        f"{current['name']} ends at 0x{end:X}, past {following['name']} "
                        f"at 0x{start:X}",
                    )

    def test_every_combination_has_exactly_one_checksum_patch(self) -> None:
        # Two patches writing the same offset would be rejected at apply time,
        # and none at all leaves a stale checksum from the vanilla build.
        manifest = combined.load_manifest("fish")
        engine = combined.GAMES["fish"].engine
        for enabled in self._combinations("fish"):
            checksum_patches = [
                patch
                for patch in engine.active_patch_records(manifest, enabled)
                if str(patch["id"]).startswith("update_pe_checksum")
            ]
            expected = 0 if not enabled else 1
            self.assertEqual(
                len(checksum_patches),
                expected,
                f"{engine.settings_key(enabled) or 'none'} has "
                f"{len(checksum_patches)} checksum patches, expected {expected}",
            )


class ReleasePackagingTests(unittest.TestCase):
    """The ZIP is what players actually get, so what it references must be in it."""

    def _release_files(self) -> set[str]:
        source = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        block = source.split("FILES = [", 1)[1].split("]", 1)[0]
        return set(re.findall(r'"([^"]+)"', block))

    def test_every_packaged_file_exists(self) -> None:
        for relative in self._release_files():
            self.assertTrue((ROOT / relative).is_file(), f"missing: {relative}")

    def test_readme_doc_links_are_packaged(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        packaged = self._release_files()
        for link in set(re.findall(r"\]\((docs/[^)#]+)\)", readme)):
            self.assertIn(link, packaged, f"README links {link}, which the ZIP omits")

    def test_documents_named_in_patch_notes_are_packaged(self) -> None:
        packaged = self._release_files()
        for game_id in combined.GAMES:
            manifest = combined.load_manifest(game_id)
            for patch in manifest["patches"]:
                for named in re.findall(r"docs/[A-Za-z0-9._-]+\.md", str(patch.get("note", ""))):
                    self.assertIn(
                        named,
                        packaged,
                        f"{patch['id']} points at {named}, which the ZIP omits",
                    )

    def test_release_version_matches_the_changelog(self) -> None:
        source = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        version = re.search(r'VERSION = "([^"]+)"', source).group(1)
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        newest = re.search(r"^## (v[\d.]+)", changelog, re.M).group(1)
        self.assertEqual(version, newest, "build_release VERSION and the newest CHANGELOG entry disagree")


class OutputRecognitionTests(unittest.TestCase):
    """Upgrading in place must keep working when the manifest id is revised."""

    CASES = (
        ("fish", fish_patcher, ".fish_tycoon_bug_fix_output.json",
         ["fish-tycoon-pc-fixes-v7", "fish-tycoon-pc-fixes-v8", "fish-tycoon-pc-fixes-v9", "fish-tycoon-pc-fixes-v10", "fish-tycoon-pc-fixes-v11", "fish-tycoon-pc-fixes-v12", "fish-tycoon-pc-fixes-v13"]),
        ("plant", plant_patcher, ".plant_tycoon_fix_output.json",
         ["plant-tycoon-pc-fixes-v1"]),
    )

    def test_previous_manifest_revisions_are_still_recognized(self) -> None:
        for game_id, engine, marker_name, shipped_ids in self.CASES:
            manifest = combined.load_manifest(game_id)
            for shipped in shipped_ids + [str(manifest["id"])]:
                with tempfile.TemporaryDirectory() as raw:
                    out = Path(raw)
                    (out / marker_name).write_text(
                        json.dumps({"manifest_id": shipped}), encoding="utf-8"
                    )
                    self.assertTrue(
                        engine.recognized_output(out, manifest),
                        f"{game_id} refuses to upgrade a folder written by {shipped}",
                    )

    def test_current_id_is_in_the_same_family_as_what_shipped(self) -> None:
        for game_id, engine, _marker, shipped_ids in self.CASES:
            manifest = combined.load_manifest(game_id)
            current = engine.output_family(manifest["id"])
            for shipped in shipped_ids:
                self.assertEqual(engine.output_family(shipped), current)

    def test_a_foreign_or_missing_marker_is_refused(self) -> None:
        manifest = combined.load_manifest("fish")
        for marker in (
            {"manifest_id": "plant-tycoon-pc-fixes-v1"},
            {"manifest_id": "something-else-v1"},
            {"manifest_id": ""},
            {},
        ):
            with tempfile.TemporaryDirectory() as raw:
                out = Path(raw)
                (out / ".fish_tycoon_bug_fix_output.json").write_text(
                    json.dumps(marker), encoding="utf-8"
                )
                self.assertFalse(fish_patcher.recognized_output(out, manifest), marker)
        with tempfile.TemporaryDirectory() as raw:
            self.assertFalse(fish_patcher.recognized_output(Path(raw), manifest))


if __name__ == "__main__":
    unittest.main()
