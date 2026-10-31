"""DS Store Items in the patcher: the setting, its dependency on DS Fish, the
companion files, the pins and the committed DLL.

Synthetic fixtures only, as tests/test_ds_fish_patcher.py. The store's
behaviour in the running game is covered by the live checks in
docs/fish-tycoon-ds-store-items-design.md.
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
import tycoon_fix_patcher as combined  # noqa: E402
from test_ds_fish_patcher import MSVC, SDK, SDK_VERSION, synthetic_exe  # noqa: E402

SETTING = "ds_store"
STORE = ROOT / "assets" / "fish_tycoon_ds_store"


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("fish")
        self.setting = combined.patch_settings("fish")[SETTING]

    def test_setting_is_off_by_default_needs_ds_fish_and_warns(self) -> None:
        self.assertFalse(self.setting["default"])
        self.assertEqual(self.setting["requires_settings"], ["ds_fish"])
        self.assertIn("Tank Animals <slot>.dat", self.setting["warning"])
        self.assertIn("rock", self.setting["warning"])
        self.assertIn("Game Mechanics", self.setting["description"])

    def test_every_combination_is_pinned_as_the_same_one_without_it(self) -> None:
        # The store writes no executable bytes: DS Fish's DLL loads its DLL.
        pins = self.manifest["patched_sha256_by_settings"]
        screen_items = {"time_warp", "free_upgrades", "add_money"}       # tests/test_store_extras.py
        screen_items |= {"multiple_ornaments", "extra_tanks", "extra_supply_slots"}   # their own loaders go first: tests/test_multiple_ornaments.py, tests/test_extra_tanks.py, tests/test_supply_slots.py
        with_store = [key for key in pins if SETTING in key.split(",") and not screen_items & set(key.split(","))]
        self.assertEqual(len(with_store), 512)        # 64, each with and without the window, Optimize Prices and the counts
        for key in with_store:
            enabled = set(key.split(","))
            self.assertIn("ds_fish", enabled)
            self.assertEqual(pins[key], pins[fish_patcher.settings_key(enabled - {SETTING})], key)

    def test_companion_files_are_pinned_and_present(self) -> None:
        companion = self.setting["companion"]
        self.assertFalse(companion.get("startup_loader", False))
        destinations = {f["destination"] for f in companion["files"]}
        self.assertIn(f"{ds_fish_loader.PATCHER_FILES_FOLDER}/DS Store Items.dll", destinations)
        self.assertEqual(len([d for d in destinations if d.startswith("Images/")]), 26)
        self.assertIn("Images/ITEM_ADD_MONEY.png", destinations)
        self.assertIn("Images/DS_PUFFER_PUFF_Grid.png", destinations)
        self.assertIn("Images/SuppliesUpgradesButton.png", destinations)
        for entry in companion["files"]:
            data = (ROOT / companion["source"] / entry["path"]).read_bytes()
            self.assertEqual(len(data), entry["size"], entry["path"])
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"], entry["path"])

    def test_dll_imports_only_kernel32_and_exports_its_startup(self) -> None:
        data = (STORE / "DS Store Items.dll").read_bytes()
        lowered = data.lower()
        self.assertIn(b"kernel32.dll", lowered)
        for other in (b"msvcr", b"vcruntime"):   # user32: Time Warp's popups
            self.assertNotIn(other, lowered, other)
        self.assertIn(b"FtfpStoreStartup", data)

    def test_store_knows_the_seahorse_repurchase_patch(self) -> None:
        # With "Buy Multiple Golden Seahorses" on, the animals can be bought more than once at a time:
        # the DLL recognises the setting by its jump at 0x4282B2.
        patch = next(p for p in self.manifest["patches"] if p["id"] == "redirect_golden_seahorse_store_blocker")
        self.assertEqual(int(patch["offset"], 16) + 0x400000, 0x4282B2)
        jump = bytes.fromhex(patch["replacement"].replace(" ", ""))
        source = (ROOT / "native" / "ftfp_ds_store" / "ftfp_ds_store.c").read_text(encoding="utf-8")
        self.assertIn("{ " + ", ".join(f"0x{b:02X}" for b in jump) + " }", source)
        self.assertIn("0x004282B2u", source)

    def test_ds_fish_loads_the_store_dll_from_its_own_folder(self) -> None:
        data = (ROOT / "assets" / "fish_tycoon_ds" / "DS Exclusive Fish.dll").read_bytes()
        self.assertIn("DS Store Items.dll".encode("utf-16-le"), data)
        self.assertIn(b"FtfpStoreStartup", data)


class RequirementTests(unittest.TestCase):
    def test_store_without_ds_fish_is_refused(self) -> None:
        manifest = combined.load_manifest("fish")
        with self.assertRaisesRegex(fish_patcher.PatchError, "DS Store Items needs DS Exclusive Fish"):
            fish_patcher.check_setting_requirements(manifest, {SETTING})
        fish_patcher.check_setting_requirements(manifest, {SETTING, "ds_fish"})
        fish_patcher.check_setting_requirements(manifest, {"ds_fish"})

    def test_gui_links_the_two_settings(self) -> None:
        source = (ROOT / "src" / "tycoon_fix_patcher_gui.py").read_text(encoding="utf-8")
        self.assertIn("requires_settings", source)
        self.assertIn("_link_setting_requirements", source)


class ApplyTests(unittest.TestCase):
    def test_store_files_land_beside_ds_fish(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = root / "repo" / "data" / "fish_manifest.json"
            fish_patcher.write_json(manifest_path, combined.load_manifest("fish"))
            for folder in ("fish_tycoon_ds", "fish_tycoon_ds_store"):
                shutil.copytree(ROOT / "assets" / folder, root / "repo" / "assets" / folder)
            vanilla = root / "Fish Tycoon"
            (vanilla / "Images").mkdir(parents=True)
            (vanilla / "Fish Tycoon.exe").write_bytes(synthetic_exe())
            output = root / "Fish Tycoon - Modded"
            args = Namespace(game_dir=str(vanilla), manifest=str(manifest_path), output_dir=str(output),
                             dry_run=False, enable=["ds_fish", SETTING], disable=None, disable_all=True)
            digest = hashlib.sha256(ds_fish_loader.append_startup_loader(synthetic_exe())[0]).hexdigest().upper()
            with mock.patch.object(fish_patcher, "validate_original_executable", return_value={"path": "x", "sha256": "x"}), \
                    mock.patch.object(fish_patcher, "expected_patched_hash", return_value=digest):
                self.assertEqual(fish_patcher.apply_manifest(args), 0)
            output = root / "Fish Tycoon - Modded Upgrades"     # new content gets its own copy
            folder = output / ds_fish_loader.PATCHER_FILES_FOLDER
            self.assertEqual((folder / "DS Store Items.dll").read_bytes(), (STORE / "DS Store Items.dll").read_bytes())
            self.assertTrue((folder / "DS Exclusive Fish.dll").is_file())
            self.assertTrue((output / "Images" / "DS_EEL_ROCK.png").is_file())


@unittest.skipUnless((MSVC / "bin" / "Hostx64" / "x86" / "cl.exe").is_file(), "the pinned MSVC toolset is not installed")
class CommittedDllTests(unittest.TestCase):
    """The committed DLL is exactly what its committed source builds to
    (scripts/build_ftfp_ds_store.ps1's flags; /Brepro makes it repeatable)."""

    def test_rebuild_matches_the_committed_dll(self) -> None:
        native = ROOT / "native" / "ftfp_ds_store"
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            command = [
                str(MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/LD", "/O2", "/MT", "/W4", "/WX",
                "/GS-", "/Brepro", f"/Fo{out}\\",
                "/I", str(MSVC / "include"),
                "/I", str(SDK / "Include" / SDK_VERSION / "um"),
                "/I", str(SDK / "Include" / SDK_VERSION / "shared"),
                "/I", str(SDK / "Include" / SDK_VERSION / "ucrt"),
                str(native / "ftfp_ds_store.c"),
                "/link", "/Brepro", f"/DEF:{native / 'ftfp_ds_store.def'}",
                f"/LIBPATH:{MSVC / 'lib' / 'x86'}",
                f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'um' / 'x86'}",
                f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'ucrt' / 'x86'}",
                f"/IMPLIB:{out / 'ftfp_ds_store.lib'}", f"/OUT:{out / 'rebuilt.dll'}",
                "/RELEASE", "/SAFESEH:NO", "kernel32.lib", "user32.lib",
            ]
            result = subprocess.run(command, cwd=out, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                (out / "rebuilt.dll").read_bytes(), (STORE / "DS Store Items.dll").read_bytes(),
                "rebuild the DLL (scripts/build_ftfp_ds_store.ps1) and re-pin (scripts/pin_ds_store.py)",
            )


class ReleaseTests(unittest.TestCase):
    def test_release_packages_the_store(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_release

        packaged = set(build_release.FILES) | set(build_release.bundled_asset_files())
        self.assertIn("assets/fish_tycoon_ds_store/DS Store Items.dll", packaged)
        self.assertIn("assets/fish_tycoon_ds_store/Images/SuppliesUpgradesButton.png", packaged)


if __name__ == "__main__":
    unittest.main()
