"""New Flowers (Plant Tycoon) in the patcher: the setting, the startup loader,
the companion files, the pins and the committed DLL."""

from __future__ import annotations

from argparse import Namespace
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import ds_fish_loader  # noqa: E402
import plant_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402
from test_ds_fish_patcher import MSVC, SDK, SDK_VERSION  # noqa: E402

SETTING = "new_flowers"
ASSETS = ROOT / "assets" / "plant_tycoon_flowers"
PLANT = ds_fish_loader.PLANT


# The supported Plant Tycoon.exe's sections: name, virtual size, address, raw size, raw offset.
PLANT_SECTIONS = [
    (".text", 0x6392F, 0x1000, 0x64000, 0x1000),
    (".rdata", 0x144F6, 0x65000, 0x15000, 0x65000),
    (".data", 0x1C024, 0x7A000, 0x1A000, 0x7A000),
    (".shr", 0x4, 0x97000, 0x1000, 0x94000),
    (".rsrc", 0x15DE0, 0x98000, 0x16000, 0x95000),
]


def synthetic_plant_exe() -> bytes:
    """A file laid out like the supported Plant Tycoon.exe (700,416 bytes): its
    section table and the stock `call WinMain`, for the loader."""
    data = bytearray(700416)
    pe = 0xF8
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe)
    data[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, pe + 4, 0x14C, len(PLANT_SECTIONS), 0, 0, 0, 0xE0, 0x10F)
    optional = pe + 24
    struct.pack_into("<H", data, optional, 0x10B)
    struct.pack_into("<I", data, optional + 28, 0x400000)
    struct.pack_into("<II", data, optional + 32, 0x1000, 0x1000)
    struct.pack_into("<I", data, optional + 56, 0xAE000)
    struct.pack_into("<I", data, optional + 60, 0x1000)
    table = optional + 0xE0
    for index, (name, vsize, vaddr, rsize, raw) in enumerate(PLANT_SECTIONS):
        at = table + 40 * index
        data[at:at + 8] = name.encode().ljust(8, b"\0")
        struct.pack_into("<IIII", data, at + 8, vsize, vaddr, rsize, raw)
    call = PLANT.winmain_call_va - 0x400000
    data[call:call + 5] = b"\xE8" + struct.pack("<i", PLANT.winmain_va - (PLANT.winmain_call_va + 5))
    return bytes(data)


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("plant")
        self.setting = combined.patch_settings("plant")[SETTING]

    def test_setting_is_off_by_default_and_warns(self) -> None:
        self.assertFalse(self.setting["default"])
        self.assertIn("Sell or compost them", self.setting["warning"])
        for name in ("Nightingale", "Rosetta", "Mirabilis", "Prunus", "Silvermist"):
            self.assertIn(name, self.setting["description"])

    def test_every_combination_is_pinned(self) -> None:
        pins = self.manifest["patched_sha256_by_settings"]
        self.assertRegex(pins.get(SETTING, ""), r"^[0-9A-F]{64}$")
        self.assertRegex(pins.get(f"{SETTING},no_old_age_plant_deaths", ""), r"^[0-9A-F]{64}$")

    def test_companion_files_are_pinned_and_present(self) -> None:
        companion = self.setting["companion"]
        self.assertTrue(companion["startup_loader"])
        destinations = {f["destination"] for f in companion["files"]}
        self.assertEqual(destinations, {
            "Plant Tycoon Fix Patcher DLLs/Unused Flowers.dll",
            "Images/flowers64x64_grid.png",
            "Images/flowers64x64_grid_mask.png",
        })
        for entry in companion["files"]:
            data = (ROOT / companion["source"] / entry["path"]).read_bytes()
            self.assertEqual(len(data), entry["size"], entry["path"])
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"], entry["path"])

    def test_dll_imports_only_kernel32(self) -> None:
        data = (ASSETS / "Unused Flowers.dll").read_bytes()
        lowered = data.lower()
        self.assertIn(b"kernel32.dll", lowered)
        for other in (b"user32.dll", b"msvcr", b"vcruntime"):
            self.assertNotIn(other, lowered, other)
        self.assertIn(b"FtfpStartup", data)
        for name in (b"Nightingale", b"Phalaena", b"Cerulean"):
            self.assertIn(name, data)


class LoaderTests(unittest.TestCase):
    def test_plant_loader_routes_winmain_and_names_the_dll(self) -> None:
        out, records = ds_fish_loader.append_startup_loader(synthetic_plant_exe(), PLANT)
        self.assertIn(b".ftfpst", out[:0x1000])
        self.assertEqual(records[3]["offset"], f"0x{PLANT.winmain_call_va - 0x400000:X}")
        self.assertIn("Plant Tycoon Fix Patcher DLLs\\Unused Flowers.dll".encode("utf-16-le"), out)
        pe = struct.unpack_from("<I", out, 0x3C)[0]
        self.assertEqual(struct.unpack_from("<I", out, pe + 24 + 64)[0], ds_fish_loader.pe_checksum(
            out[:pe + 88] + b"\0\0\0\0" + out[pe + 92:]))

    def test_gui_details_use_the_plant_profile(self) -> None:
        details = combined.setting_companion_details("plant", SETTING)
        self.assertTrue(any("Unused Flowers.dll" in d.note for d in details))
        self.assertTrue(any(d.virtual_address == PLANT.winmain_call_va for d in details))


class ApplyTests(unittest.TestCase):
    def test_files_land_and_the_sheet_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest_path = root / "repo" / "data" / "plant_manifest.json"
            plant_patcher.write_json(manifest_path, combined.load_manifest("plant"))
            shutil.copytree(ASSETS, root / "repo" / "assets" / "plant_tycoon_flowers")
            vanilla = root / "Plant Tycoon"
            (vanilla / "Images").mkdir(parents=True)
            (vanilla / "Images" / "flowers64x64_Grid.png").write_bytes(b"stock")
            (vanilla / "Plant Tycoon.exe").write_bytes(synthetic_plant_exe())
            output = root / "Plant Tycoon - Modded"
            args = Namespace(game_dir=str(vanilla), manifest=str(manifest_path), output_dir=str(output),
                             dry_run=False, enable=[SETTING], disable=None, disable_all=True)
            digest = hashlib.sha256(
                ds_fish_loader.append_startup_loader(synthetic_plant_exe(), PLANT)[0]).hexdigest().upper()
            with mock.patch.object(plant_patcher, "validate_original_executable",
                                   return_value={"path": "x", "sha256": "x"}), \
                    mock.patch.object(plant_patcher, "expected_patched_hash", return_value=digest):
                self.assertEqual(plant_patcher.apply_manifest(args), 0)
            output = root / "Plant Tycoon - Modded Upgrades"    # new content gets its own copy
            self.assertEqual((output / "Plant Tycoon Fix Patcher DLLs" / "Unused Flowers.dll").read_bytes(),
                             (ASSETS / "Unused Flowers.dll").read_bytes())
            self.assertEqual((output / "Images" / "flowers64x64_grid.png").read_bytes(),
                             (ASSETS / "Images" / "flowers64x64_grid.png").read_bytes())
            self.assertEqual(len(args.last_apply_summary["startup_loader"]), 5)


@unittest.skipUnless((MSVC / "bin" / "Hostx64" / "x86" / "cl.exe").is_file(), "the pinned MSVC toolset is not installed")
class CommittedDllTests(unittest.TestCase):
    def test_rebuild_matches_the_committed_dll(self) -> None:
        native = ROOT / "native" / "ftfp_new_flowers"
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            command = [
                str(MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/LD", "/O2", "/MT", "/W4", "/WX",
                "/GS-", "/Brepro", f"/Fo{out}\\",
                "/I", str(MSVC / "include"),
                "/I", str(SDK / "Include" / SDK_VERSION / "um"),
                "/I", str(SDK / "Include" / SDK_VERSION / "shared"),
                "/I", str(SDK / "Include" / SDK_VERSION / "ucrt"),
                str(native / "ftfp_new_flowers.c"),
                "/link", "/Brepro", f"/DEF:{native / 'ftfp_new_flowers.def'}",
                f"/LIBPATH:{MSVC / 'lib' / 'x86'}",
                f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'um' / 'x86'}",
                f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'ucrt' / 'x86'}",
                f"/IMPLIB:{out / 'ftfp_new_flowers.lib'}", f"/OUT:{out / 'rebuilt.dll'}",
                "/RELEASE", "/SAFESEH:NO", "kernel32.lib",
            ]
            result = subprocess.run(command, cwd=out, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((out / "rebuilt.dll").read_bytes(), (ASSETS / "Unused Flowers.dll").read_bytes(),
                             "rebuild the DLL (scripts/build_ftfp_new_flowers.ps1) and re-pin (scripts/pin_new_flowers.py)")


if __name__ == "__main__":
    unittest.main()
