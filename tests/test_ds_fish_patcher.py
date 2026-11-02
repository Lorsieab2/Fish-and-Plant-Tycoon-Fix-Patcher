"""DS Fish in the patcher: the startup loader, the companion files, the pins.

Synthetic fixtures only (a PE built from the manifest's recorded section
layout), so no copy of the game is needed. The companion's own rules are
tested in tests/test_ds_fish_logic.py.
"""

from __future__ import annotations

from argparse import Namespace
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

SETTING = "ds_fish"


def synthetic_exe() -> bytes:
    """A file laid out like the supported Fish Tycoon.exe: its headers and
    section table from the manifest, and the stock `call WinMain`."""
    target = combined.load_manifest("fish")["target"]
    data = bytearray(int(target["size"]))
    pe = 0xF8
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe)
    data[pe:pe + 4] = b"PE\0\0"
    layout = target["section_layout"]
    struct.pack_into("<HHIIIHH", data, pe + 4, 0x14C, len(layout), 0, 0, 0, 0xE0, 0x10F)
    optional = pe + 24
    struct.pack_into("<H", data, optional, 0x10B)
    struct.pack_into("<I", data, optional + 28, 0x400000)
    struct.pack_into("<II", data, optional + 32, 0x1000, 0x1000)
    struct.pack_into("<I", data, optional + 56, 0x60000)
    struct.pack_into("<I", data, optional + 60, 0x1000)
    table = optional + 0xE0
    for index, section in enumerate(layout):
        at = table + 40 * index
        data[at:at + 8] = section["name"].encode().ljust(8, b"\0")
        struct.pack_into(
            "<IIII", data, at + 8,
            int(section["virtual_size"], 16), int(section["virtual_address"], 16),
            int(section["raw_size"], 16), int(section["raw_offset"], 16),
        )
    call = ds_fish_loader.WINMAIN_CALL_VA - 0x400000
    data[call:call + 5] = b"\xE8" + struct.pack("<i", ds_fish_loader.WINMAIN_VA - (ds_fish_loader.WINMAIN_CALL_VA + 5))
    return bytes(data)


class StartupLoaderTests(unittest.TestCase):
    def test_loader_adds_one_read_execute_section_and_routes_winmain(self) -> None:
        before = synthetic_exe()
        after, records = ds_fish_loader.append_startup_loader(before)
        pe = 0xF8
        self.assertEqual(struct.unpack_from("<H", after, pe + 6)[0], 6)
        header = after[0x2B8:0x2B8 + 40]
        self.assertEqual(header[:8], b".ftfpst\0")
        vsize, rva, rsize, raw = struct.unpack_from("<IIII", header, 8)
        self.assertEqual(rva, 0x60000)
        self.assertEqual(raw, len(before))
        self.assertEqual(struct.unpack_from("<I", header, 36)[0], 0x60000020, "code, read, execute; never writable")
        self.assertEqual(struct.unpack_from("<I", after, pe + 24 + 56)[0], 0x61000)
        block = after[raw:raw + vsize]
        self.assertIn(ds_fish_loader.TAIL, block)
        self.assertIn(b"FtfpStartup\0", block)
        call = ds_fish_loader.WINMAIN_CALL_VA - 0x400000
        target = ds_fish_loader.WINMAIN_CALL_VA + 5 + struct.unpack_from("<i", after, call + 1)[0]
        self.assertEqual(after[call], 0xE8)
        self.assertTrue(0x460000 <= target < 0x460000 + vsize, "WinMain's call goes to the stub")
        # The stub ends in a jump back to WinMain.
        jmp = block.rindex(b"\xE9", 0, len(block))
        self.assertEqual(0x460000 + jmp + 5 + struct.unpack_from("<i", block, jmp + 1)[0], ds_fish_loader.WINMAIN_VA)
        self.assertEqual(len(records), 5)
        # Only the documented places change before the appended block.
        changed = [i for i in range(len(before)) if before[i] != after[i]]
        allowed = set(range(pe + 6, pe + 8)) | set(range(pe + 24 + 56, pe + 24 + 60)) | set(range(0x2B8, 0x2E0)) \
            | set(range(call + 1, call + 5)) | set(range(pe + 24 + 64, pe + 24 + 68))
        self.assertTrue(set(changed) <= allowed, [hex(i) for i in changed if i not in allowed][:5])

    def test_checksum_is_recomputed(self) -> None:
        after, _ = ds_fish_loader.append_startup_loader(synthetic_exe())
        stored = struct.unpack_from("<I", after, 0x150)[0]
        self.assertEqual(stored, ds_fish_loader.pe_checksum(after))

    def test_refuses_a_second_loader_and_a_moved_winmain_call(self) -> None:
        once, _ = ds_fish_loader.append_startup_loader(synthetic_exe())
        with self.assertRaises(ds_fish_loader.LoaderError):
            ds_fish_loader.append_startup_loader(once)
        moved = bytearray(synthetic_exe())
        moved[ds_fish_loader.WINMAIN_CALL_VA - 0x400000 + 1] ^= 1
        with self.assertRaises(ds_fish_loader.LoaderError):
            ds_fish_loader.append_startup_loader(bytes(moved))

    def test_described_changes_match_the_loader(self) -> None:
        before = synthetic_exe()
        after, _ = ds_fish_loader.append_startup_loader(before)
        for offset, _va, length, note in ds_fish_loader.described_changes():
            self.assertTrue(note)
            if offset < len(before):
                self.assertNotEqual(before[offset:offset + length], after[offset:offset + length], note)


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("fish")
        self.setting = next(s for s in self.manifest["settings"] if s["id"] == SETTING)

    def test_setting_is_on_by_default_and_warns(self) -> None:
        self.assertTrue(self.setting["default"])  # on by default (the owner, 2026-11-01: new content stays on)
        self.assertIn("Sell or trash every DS fish", self.setting["warning"])

    def test_every_combination_with_ds_fish_is_pinned(self) -> None:
        # DS Store Items builds on DS Fish; tests/test_ds_store_patcher.py pins those.
        others = [s["id"] for s in self.manifest["settings"] if s["id"] not in (SETTING, "ds_store", "time_warp", "free_upgrades", "add_money",
                                                                                    "extra_tanks", "extra_supply_slots",
                                                                                    "unicode_ingame_fonts", "translations", "unicode_system_font",
                                                                                    "copy_paste_text_boxes")]
        pins = self.manifest["patched_sha256_by_settings"]
        for count in range(len(others) + 1):
            for combo in itertools.combinations(others, count):
                key = fish_patcher.settings_key(set(combo) | {SETTING})
                self.assertRegex(pins.get(key, ""), r"^[0-9A-F]{64}$", key)
                if combo:
                    self.assertIn(fish_patcher.settings_key(set(combo)), pins)

    def test_companion_files_are_pinned_and_present(self) -> None:
        companion = self.setting["companion"]
        self.assertTrue(companion["startup_loader"])
        destinations = {f["destination"] for f in companion["files"]}
        self.assertIn("Fish Tycoon Fix Patcher DLLs/DS Exclusive Fish.dll", destinations)
        self.assertEqual(len([d for d in destinations if d.startswith("Images/")]), 23)
        for entry in companion["files"]:
            path = ROOT / companion["source"] / entry["path"]
            data = path.read_bytes()
            self.assertEqual(len(data), entry["size"], entry["path"])
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"], entry["path"])

    def test_companion_dll_imports_only_kernel32(self) -> None:
        data = (ROOT / "assets" / "fish_tycoon_ds" / "DS Exclusive Fish.dll").read_bytes()
        self.assertEqual(data[:2], b"MZ")
        lowered = data.lower()
        self.assertIn(b"kernel32.dll", lowered)
        for other in (b"user32.dll", b"msvcr", b"vcruntime", b"shell32.dll\0\0"):
            self.assertNotIn(other, lowered, other)
        self.assertIn(b"FtfpStartup", data)


class ApplyTests(unittest.TestCase):
    """apply_manifest with DS Fish: files copied, refused when tampered, gone when off."""

    def _fixture(self, root: Path) -> tuple[Namespace, Path, Path]:
        manifest = combined.load_manifest("fish")
        bundle = root / "repo" / "assets" / "fish_tycoon_ds"
        shutil.copytree(ROOT / "assets" / "fish_tycoon_ds", bundle)
        manifest_path = root / "repo" / "data" / "fish_manifest.json"
        fish_patcher.write_json(manifest_path, manifest)
        vanilla = root / "Fish Tycoon"
        (vanilla / "Images").mkdir(parents=True)
        (vanilla / "Fish Tycoon.exe").write_bytes(synthetic_exe())
        # The patcher is given the plain "- Modded" folder (the GUI's default); new content
        # goes to "- Modded Upgrades" beside it.
        args = Namespace(game_dir=str(vanilla), manifest=str(manifest_path),
                         output_dir=str(root / "Fish Tycoon - Modded"),
                         dry_run=False, enable=[SETTING], disable=None, disable_all=True)
        return args, root / "Fish Tycoon - Modded Upgrades", bundle

    def _apply(self, args: Namespace) -> None:
        identity = {"path": "x", "sha256": "x"}
        expected = lambda manifest, enabled: hashlib.sha256(  # noqa: E731
            ds_fish_loader.append_startup_loader(synthetic_exe())[0]).hexdigest().upper() if SETTING in enabled else ""
        with mock.patch.object(fish_patcher, "validate_original_executable", return_value=identity), \
                mock.patch.object(fish_patcher, "expected_patched_hash", side_effect=expected):
            self.assertEqual(fish_patcher.apply_manifest(args), 0)

    def test_companion_files_land_at_their_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args, output, bundle = self._fixture(Path(raw))
            self._apply(args)
            dll = output / "Fish Tycoon Fix Patcher DLLs" / "DS Exclusive Fish.dll"
            self.assertEqual(dll.read_bytes(), (bundle / "DS Exclusive Fish.dll").read_bytes())
            self.assertTrue((output / "Images" / "FISH_29_body_Grid.png").is_file())
            exe = (output / "Fish Tycoon - Modded Upgrades.exe").read_bytes()
            self.assertIn(b".ftfpst", exe[:0x1000])
            self.assertEqual(len(args.last_apply_summary["startup_loader"]), 5)

    def test_turning_it_off_makes_the_plain_copy_and_keeps_the_upgrades_one(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args, upgrades, _ = self._fixture(Path(raw))
            self._apply(args)
            args.enable = []
            self._apply(args)
            plain = Path(raw) / "Fish Tycoon - Modded"
            self.assertFalse((plain / "Fish Tycoon Fix Patcher DLLs").exists())
            self.assertFalse((plain / "Images" / "FISH_29_body_Grid.png").exists())
            self.assertNotIn(b".ftfpst", (plain / "Fish Tycoon - Modded.exe").read_bytes()[:0x1000])
            self.assertFalse((plain / "Fish Tycoon - Modded Upgrades.exe").exists())
            self.assertTrue((upgrades / "Fish Tycoon Fix Patcher DLLs" / "DS Exclusive Fish.dll").is_file())
            self.assertIn(b".ftfpst", (upgrades / "Fish Tycoon - Modded Upgrades.exe").read_bytes()[:0x1000])

    def test_a_folder_the_user_named_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args, _, _ = self._fixture(Path(raw))
            args.output_dir = str(Path(raw) / "My Fish")
            self._apply(args)
            self.assertTrue((Path(raw) / "My Fish" / "Fish Tycoon - Modded Upgrades.exe").is_file())
            self.assertFalse((Path(raw) / "Fish Tycoon - Modded Upgrades").exists())

    def test_a_tampered_companion_file_is_refused_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args, output, bundle = self._fixture(Path(raw))
            with open(bundle / "DS Exclusive Fish.dll", "ab") as handle:
                handle.write(b"\0")
            with self.assertRaises(fish_patcher.PatchError):
                self._apply(args)
            self.assertFalse(output.exists())

    def test_an_unsafe_destination_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args, output, _ = self._fixture(Path(raw))
            manifest_path = Path(args.manifest)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            setting = next(s for s in manifest["settings"] if s["id"] == SETTING)
            setting["companion"]["files"][0]["destination"] = "../outside.dll"
            fish_patcher.write_json(manifest_path, manifest)
            with self.assertRaises(fish_patcher.PatchError):
                self._apply(args)
            self.assertFalse(output.exists())


MSVC = Path(r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231")
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10")
SDK_VERSION = "10.0.26100.0"


@unittest.skipUnless((MSVC / "bin" / "Hostx64" / "x86" / "cl.exe").is_file(), "the pinned MSVC toolset is not installed")
class CommittedDllTests(unittest.TestCase):
    """The committed DLL is exactly what its committed source builds to
    (the flags of scripts/build_ftfp_ds_fish.ps1; /Brepro makes it repeatable)."""

    def test_rebuild_matches_the_committed_dll(self) -> None:
        import subprocess

        native = ROOT / "native" / "ftfp_ds_fish"
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            command = [
                str(MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/LD", "/O2", "/MT", "/W4", "/WX",
                "/GS-", "/Brepro", f"/Fo{out}\\",
                "/I", str(MSVC / "include"),
                "/I", str(SDK / "Include" / SDK_VERSION / "um"),
                "/I", str(SDK / "Include" / SDK_VERSION / "shared"),
                "/I", str(SDK / "Include" / SDK_VERSION / "ucrt"),
                str(native / "ftfp_ds_fish.c"),
                "/link", "/Brepro", f"/DEF:{native / 'ftfp_ds_fish.def'}",
                f"/LIBPATH:{MSVC / 'lib' / 'x86'}",
                f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'um' / 'x86'}",
                f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'ucrt' / 'x86'}",
                f"/IMPLIB:{out / 'ftfp_ds_fish.lib'}", f"/OUT:{out / 'rebuilt.dll'}",
                "/RELEASE", "/SAFESEH:NO", "kernel32.lib",
            ]
            result = subprocess.run(command, cwd=out, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                (out / "rebuilt.dll").read_bytes(),
                (ROOT / "assets" / "fish_tycoon_ds" / "DS Exclusive Fish.dll").read_bytes(),
                "rebuild the DLL (scripts/build_ftfp_ds_fish.ps1) and re-pin (scripts/pin_ds_fish.py)",
            )


class GuiAndReleaseTests(unittest.TestCase):
    def test_gui_lists_the_companion_files_and_loader_changes(self) -> None:
        self.assertEqual(len(combined.setting_companion_files("fish", SETTING)), 24)
        self.assertEqual(len(combined.setting_companion_details("fish", SETTING)), 6)
        source = (ROOT / "src" / "tycoon_fix_patcher_gui.py").read_text(encoding="utf-8")
        self.assertIn("setting_companion_files", source)
        self.assertIn("setting_companion_details", source)

    def test_release_packages_the_companion(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_release

        packaged = set(build_release.FILES) | set(build_release.bundled_asset_files())
        self.assertIn("src/ds_fish_loader.py", packaged)
        self.assertIn("assets/fish_tycoon_ds/DS Exclusive Fish.dll", packaged)
        self.assertIn("assets/fish_tycoon_ds/Images/FISH_DS_teen_Grid.png", packaged)
        self.assertIn("docs/fish-tycoon-ds-fish-testing-guide.md", packaged)


if __name__ == "__main__":
    unittest.main()
