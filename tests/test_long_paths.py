"""Paths past Windows' 260-character limit: the patcher's staging copy and the
save backups go through the extended-length form (src/long_paths.py), so a
deep location never fails with "path too long"."""

from __future__ import annotations

from argparse import Namespace
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import ds_fish_loader  # noqa: E402
import long_paths  # noqa: E402
import plant_patcher  # noqa: E402
import save_backup  # noqa: E402
import save_tools  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402
from test_new_flowers_patcher import synthetic_plant_exe  # noqa: E402
from test_save_backup import FakeProcesses  # noqa: E402
from test_save_tools import SIZES, ldw  # noqa: E402

DEEP = ("Very long folder name that a player could well have " * 2).strip()


class LongPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        shutil.rmtree(long_paths.extended(self.root), ignore_errors=True)
        self.temp.cleanup()

    def deep(self, *parts: str) -> Path:
        path = self.root / DEEP / DEEP / DEEP
        for part in parts:
            path = path / part
        return path

    def test_the_forms(self) -> None:
        if os.name == "nt":
            self.assertEqual(str(long_paths.extended("C:\\a\\b")), "\\\\?\\C:\\a\\b")
            self.assertEqual(str(long_paths.extended("\\\\host\\share\\x")), "\\\\?\\UNC\\host\\share\\x")
            self.assertEqual(str(long_paths.plain("\\\\?\\UNC\\host\\share\\x")), "\\\\host\\share\\x")
        self.assertEqual(long_paths.plain(long_paths.extended(self.root)), Path(os.path.abspath(self.root)))

    @unittest.skipUnless(os.name == "nt", "the 260-character limit is Windows'")
    def test_backup_and_restore_in_a_save_folder_past_260_characters(self) -> None:
        fmt = save_tools.FORMATS["plant"]
        folder = self.deep("Plant Tycoon - Modded")
        fs = long_paths.extended(folder)
        (fs / "Plant Tycoon Fix Patcher Data").mkdir(parents=True)
        settings = ldw(SIZES["plant"][0])
        for i, name in enumerate(["Ana", "Bo"]):
            at = fmt.names_offset + i * fmt.name_stride
            settings[at: at + len(name)] = name.encode()
        (fs / "Plant Tycoon0.ldw").write_bytes(bytes(settings))
        for slot in (1, 2):
            for extra in fmt.slot_file_offsets:
                (fs / f"Plant Tycoon{slot + extra}.ldw").write_bytes(bytes(ldw(64)))
            (fs / "Plant Tycoon Fix Patcher Data" / f"Store Upgrades and Items {slot}.dat").write_bytes(b"x")
        result = save_backup.back_up_save_folder(folder, FakeProcesses(), suffix=save_backup.BEFORE_RESTORE)
        longest = max(len(str(long_paths.plain(result.backup_folder) / f.relative)) for f in result.files)
        self.assertGreater(longest, 260, "the test really goes past the limit")
        self.assertFalse(str(result.backup_folder).startswith("\\\\?\\"), "shown paths stay plain")
        (fs / "Plant Tycoon Fix Patcher Data" / "Store Upgrades and Items 2.dat").write_bytes(b"changed")
        listed = save_backup.list_backups("plant", folder)
        self.assertEqual(len(listed), 1)
        save_backup.restore_backup("plant", folder, listed[0].folder, 2, FakeProcesses())
        self.assertEqual((fs / "Plant Tycoon Fix Patcher Data" / "Store Upgrades and Items 2.dat").read_bytes(), b"x")
        save_backup.delete_backup(folder, listed[0].folder)

    @unittest.skipUnless(os.name == "nt", "the 260-character limit is Windows'")
    def test_a_modded_copy_staged_past_260_characters(self) -> None:
        manifest_path = self.root / "repo" / "data" / "plant_manifest.json"
        plant_patcher.write_json(manifest_path, combined.load_manifest("plant"))
        for folder in ("plant_tycoon_flowers", "plant_tycoon_upgrades"):
            shutil.copytree(ROOT / "assets" / folder, self.root / "repo" / "assets" / folder)
        vanilla = self.root / "Plant Tycoon"
        (vanilla / "Images").mkdir(parents=True)
        (vanilla / "Plant Tycoon.exe").write_bytes(synthetic_plant_exe())
        output = self.deep("Plant Tycoon - Modded")
        args = Namespace(game_dir=str(vanilla), manifest=str(manifest_path), output_dir=str(output), dry_run=False,
                         enable=["new_flowers", "plant_upgrades"], disable=None, disable_all=True)
        digest = hashlib.sha256(ds_fish_loader.append_startup_loader(
            synthetic_plant_exe(), ds_fish_loader.PLANT)[0]).hexdigest().upper()
        with mock.patch.object(plant_patcher, "validate_original_executable",
                               return_value={"path": "x", "sha256": "x"}), \
                mock.patch.object(plant_patcher, "expected_patched_hash", return_value=digest):
            self.assertEqual(plant_patcher.apply_manifest(args), 0)
        made = long_paths.extended(self.deep("Plant Tycoon - Modded Upgrades"))
        dll = made / ds_fish_loader.PLANT.patcher_files_folder / "Store Upgrades and Items.dll"
        self.assertTrue(dll.is_file())
        self.assertGreater(len(str(long_paths.plain(dll))), 260)
        self.assertFalse(str(args.last_apply_summary["backup_dir"]).startswith("\\\\?\\"))


if __name__ == "__main__":
    unittest.main()
