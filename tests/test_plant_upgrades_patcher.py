"""Add new store upgrades and items (Plant Tycoon) in the patcher: the
setting, its dependency, the companion files (the Upgrades and Seed Boxes
DLLs and the art), the pins and the committed DLLs.

Synthetic fixtures only, as tests/test_new_flowers_patcher.py. The behaviour
in the running game is covered by the live checks in
docs/plant-tycoon-upgrades-design.md.
"""

from __future__ import annotations

from argparse import Namespace
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import plant_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402
from test_ds_fish_patcher import MSVC, SDK, SDK_VERSION  # noqa: E402
from test_new_flowers_patcher import synthetic_plant_exe  # noqa: E402

UPGRADES = ROOT / "assets" / "plant_tycoon_upgrades"
BOXES = UPGRADES
FOLDER = ds_fish_loader.PLANT.patcher_files_folder


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("plant")
        self.settings = combined.patch_settings("plant")

    def test_setting_is_off_by_default_needs_the_flowers_and_warns(self) -> None:
        upgrades = self.settings["plant_upgrades"]
        self.assertEqual(upgrades["name"], "Add new store upgrades and items")
        self.assertEqual(self.settings["new_flowers"]["name"], "Add unused flowers")
        self.assertNotIn("seed_boxes", self.settings)
        self.assertFalse(upgrades["default"])
        self.assertEqual(upgrades["requires_settings"], ["new_flowers"])
        for text in ("Legendary Seeds", "Radioactive Plant Formula", "$10,000", "$5000", "Fourth", "Fifth",
                     "Sixth", "Even more space for your seeds!", "greenhouse"):
            self.assertIn(text, upgrades["description"])
        self.assertIn("use up the formula", upgrades["warning"])
        self.assertIn("boxes 4-6", upgrades["warning"])

    def test_every_combination_is_pinned_as_the_same_one_without_them(self) -> None:
        # It writes no executable bytes: the flowers' DLL loads the Upgrades DLL, which loads the boxes'.
        pins = self.manifest["patched_sha256_by_settings"]
        screen_items = {"time_warp", "free_upgrades", "add_money"}       # tests/test_store_extras.py
        added = [key for key in pins if "plant_upgrades" in key.split(",") and not screen_items & set(key.split(","))]
        self.assertEqual(len(added), 8)          # with and without Sort Seeds and the R key
        for key in added:
            enabled = set(key.split(","))
            self.assertIn("new_flowers", enabled)
            base = plant_patcher.settings_key(enabled - {"plant_upgrades"}, self.manifest)
            self.assertEqual(pins[key], pins[base], key)

    def test_companion_files_are_pinned_and_present(self) -> None:
        expected = {
            "plant_upgrades": {f"{FOLDER}/Store Upgrades and Items.dll", f"{FOLDER}/Extra Seed Boxes.dll",
                               "Images/seed_grid_legendary.png", "Images/Chemicals_Grid_upgrades.png",
                               "Images/upgrades_link.png"},
        }
        for setting_id, destinations in expected.items():
            companion = self.settings[setting_id]["companion"]
            self.assertFalse(companion.get("startup_loader", False))
            self.assertEqual({f["destination"] for f in companion["files"]}, destinations)
            for entry in companion["files"]:
                data = (ROOT / companion["source"] / entry["path"]).read_bytes()
                self.assertEqual(len(data), entry["size"], entry["path"])
                self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"], entry["path"])

    def test_new_images_never_replace_stock_files(self) -> None:
        # The DLL points the game's sheet records at its own copies; the stock sheets stay as they are.
        names = {f["destination"].lower() for f in self.settings["plant_upgrades"]["companion"]["files"]}
        self.assertNotIn("images/seed_grid.png", names)
        self.assertNotIn("images/chemicals_grid.png", names)

    def test_dlls_import_only_kernel32_and_export_their_startups(self) -> None:
        for path, export in ((UPGRADES / "Store Upgrades and Items.dll", b"FtfpUpgradesStartup"),
                             (BOXES / "Extra Seed Boxes.dll", b"FtfpSeedBoxesStartup")):
            data = path.read_bytes()
            lowered = data.lower()
            self.assertIn(b"kernel32.dll", lowered)
            for other in (b"msvcr", b"vcruntime"):   # user32: Time Warp's popups
                self.assertNotIn(other, lowered, other)
            self.assertIn(export, data)

    def test_each_dll_loads_the_next_from_its_own_folder(self) -> None:
        flowers = (ROOT / "assets" / "plant_tycoon_flowers" / "Unused Flowers.dll").read_bytes()
        self.assertIn("Store Upgrades and Items.dll".encode("utf-16-le"), flowers)
        self.assertIn(b"FtfpUpgradesStartup", flowers)
        upgrades = (UPGRADES / "Store Upgrades and Items.dll").read_bytes()
        self.assertIn("Extra Seed Boxes.dll".encode("utf-16-le"), upgrades)
        self.assertIn(b"FtfpSeedBoxesStartup", upgrades)

    def test_store_texts_are_the_owners(self) -> None:
        data = (UPGRADES / "Store Upgrades and Items.dll").read_bytes()
        for text in (b"Legendary Seeds", b"rediscovered on Isola", b"Radioactive Plant Formula",
                     b"No more dead leaves!", b"Contains 3 doses.", b"Fourth Seed Box", b"Sixth Seed Box",
                     b"Even more space for your seeds!"):
            self.assertIn(text, data)


class RequirementTests(unittest.TestCase):
    def test_settings_without_what_they_build_on_are_refused(self) -> None:
        manifest = combined.load_manifest("plant")
        with self.assertRaisesRegex(fish_patcher.PatchError,
                                    "Add new store upgrades and items needs Add unused flowers"):
            fish_patcher.check_setting_requirements(manifest, {"plant_upgrades"})
        fish_patcher.check_setting_requirements(manifest, {"new_flowers", "plant_upgrades"})


class ApplyTests(unittest.TestCase):
    def test_files_land_beside_new_flowers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = root / "repo" / "data" / "plant_manifest.json"
            plant_patcher.write_json(manifest_path, combined.load_manifest("plant"))
            for folder in ("plant_tycoon_flowers", "plant_tycoon_upgrades"):
                shutil.copytree(ROOT / "assets" / folder, root / "repo" / "assets" / folder)
            vanilla = root / "Plant Tycoon"
            (vanilla / "Images").mkdir(parents=True)
            (vanilla / "Images" / "seed_Grid.png").write_bytes(b"stock")
            (vanilla / "Plant Tycoon.exe").write_bytes(synthetic_plant_exe())
            output = root / "Plant Tycoon - Modded"
            args = Namespace(game_dir=str(vanilla), manifest=str(manifest_path), output_dir=str(output), dry_run=False,
                             enable=["new_flowers", "plant_upgrades"], disable=None, disable_all=True)
            digest = hashlib.sha256(ds_fish_loader.append_startup_loader(
                synthetic_plant_exe(), ds_fish_loader.PLANT)[0]).hexdigest().upper()
            with mock.patch.object(plant_patcher, "validate_original_executable",
                                   return_value={"path": "x", "sha256": "x"}), \
                    mock.patch.object(plant_patcher, "expected_patched_hash", return_value=digest):
                self.assertEqual(plant_patcher.apply_manifest(args), 0)
            output = root / "Plant Tycoon - Modded Upgrades"    # new content gets its own copy
            folder = output / FOLDER
            self.assertEqual((folder / "Store Upgrades and Items.dll").read_bytes(),
                             (UPGRADES / "Store Upgrades and Items.dll").read_bytes())
            self.assertEqual((folder / "Extra Seed Boxes.dll").read_bytes(), (BOXES / "Extra Seed Boxes.dll").read_bytes())
            self.assertTrue((folder / "Unused Flowers.dll").is_file())
            self.assertTrue((output / "Images" / "seed_grid_legendary.png").is_file())
            self.assertEqual((output / "Images" / "seed_Grid.png").read_bytes(), b"stock")


@unittest.skipUnless((MSVC / "bin" / "Hostx64" / "x86" / "cl.exe").is_file(), "the pinned MSVC toolset is not installed")
class CommittedDllTests(unittest.TestCase):
    """Each committed DLL is exactly what its committed source builds to
    (its build script's flags; /Brepro makes it repeatable)."""

    def rebuild(self, name: str, committed: Path) -> None:
        native = ROOT / "native" / name
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            command = [
                str(MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/LD", "/O2", "/MT", "/W4", "/WX",
                "/GS-", "/Brepro", f"/Fo{out}\\",
                "/I", str(MSVC / "include"),
                "/I", str(SDK / "Include" / SDK_VERSION / "um"),
                "/I", str(SDK / "Include" / SDK_VERSION / "shared"),
                "/I", str(SDK / "Include" / SDK_VERSION / "ucrt"),
                str(native / f"{name}.c"),
                "/link", "/Brepro", f"/DEF:{native / f'{name}.def'}",
                f"/LIBPATH:{MSVC / 'lib' / 'x86'}",
                f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'um' / 'x86'}",
                f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'ucrt' / 'x86'}",
                f"/IMPLIB:{out / f'{name}.lib'}", f"/OUT:{out / 'rebuilt.dll'}",
                "/RELEASE", "/SAFESEH:NO", "kernel32.lib", "user32.lib",
            ]
            result = subprocess.run(command, cwd=out, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((out / "rebuilt.dll").read_bytes(), committed.read_bytes(),
                             f"rebuild {committed.name} and re-pin (scripts/pin_plant_upgrades.py)")

    def test_upgrades_rebuild_matches(self) -> None:
        self.rebuild("ftfp_plant_upgrades", UPGRADES / "Store Upgrades and Items.dll")

    def test_seed_boxes_rebuild_matches(self) -> None:
        self.rebuild("ftfp_seed_boxes", BOXES / "Extra Seed Boxes.dll")


class ReleaseTests(unittest.TestCase):
    def test_release_packages_both(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_release

        packaged = set(build_release.FILES) | set(build_release.bundled_asset_files())
        self.assertIn("assets/plant_tycoon_upgrades/Store Upgrades and Items.dll", packaged)
        self.assertIn("assets/plant_tycoon_upgrades/Images/upgrades_link.png", packaged)
        self.assertIn("assets/plant_tycoon_upgrades/Extra Seed Boxes.dll", packaged)
        self.assertIn("assets/plant_tycoon_flowers/Unused Flowers.dll", packaged)
        self.assertIn("docs/plant-tycoon-upgrades-design.md", packaged)


if __name__ == "__main__":
    unittest.main()
