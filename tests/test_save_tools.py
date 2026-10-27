"""Save tools: player slots and renaming. Synthetic save folders
laid out like the games' own (see src/save_tools.py), so no game is needed."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import save_tools  # noqa: E402


class NoGame:
    """A process list with the game not running."""

    def find(self, exe_name):
        return []

SIZES = {"fish": (0xE8, 0x1E3C8), "plant": (0xC0, 0x53FB0)}


def ldw(size: int) -> bytearray:
    data = bytearray(24 + size)
    data[:4] = b"ldwg"
    data[0x10:0x14] = size.to_bytes(4, "little")
    return data


def make_folder(root: Path, game_id: str, names: list[str], folder: str | None = None) -> Path:
    fmt = save_tools.FORMATS[game_id]
    settings_size, slot_size = SIZES[game_id]
    path = root / "LDW" / (folder or fmt.title)
    path.mkdir(parents=True)
    settings = ldw(settings_size)
    for i, name in enumerate(names):
        at = fmt.names_offset + i * fmt.name_stride
        settings[at: at + len(name)] = name.encode()
    settings[-4:] = b"TAIL"
    (path / f"{fmt.title}0.ldw").write_bytes(bytes(settings))
    for i, name in enumerate(names, start=1):
        for extra in fmt.slot_file_offsets:
            slot = ldw(slot_size)
            slot[fmt.slot_name_offset: fmt.slot_name_offset + len(name)] = name.encode()
            slot[fmt.slot_name_offset + 40] = 0x7A          # data after the name field
            (path / f"{fmt.title}{i + extra}.ldw").write_bytes(bytes(slot))
    return path


class SaveToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backups = self.root / "backups"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_slot_names_are_read_for_both_games(self) -> None:
        for game_id in save_tools.FORMATS:
            folder = make_folder(self.root, game_id, ["Ana", "NEW PLAYER", "Bo", "", "Cy"], f"{game_id} saves")
            self.assertEqual(save_tools.read_slot_names(game_id, folder), ["Ana", "NEW PLAYER", "Bo", "", "Cy"])

    def test_save_folders_lists_the_game_and_its_copies(self) -> None:
        make_folder(self.root, "fish", ["A"] * 5, "Fish Tycoon")
        make_folder(self.root, "fish", ["A"] * 5, "Fish Tycoon - Modded")
        make_folder(self.root, "plant", ["A"] * 5, "Plant Tycoon")
        (self.root / "LDW" / "Fish Tycoon Empty").mkdir()
        found = [p.name for p in save_tools.save_folders("fish", self.root)]
        self.assertEqual(found, ["Fish Tycoon", "Fish Tycoon - Modded"])

    def test_the_tools_list_only_the_patchers_copies(self) -> None:
        make_folder(self.root, "fish", ["A"] * 5, "Fish Tycoon")
        make_folder(self.root, "fish", ["A"] * 5, "Fish Tycoon - Modded")
        make_folder(self.root, "fish", ["A"] * 5, "Fish Tycoon - Modded Upgrades")
        make_folder(self.root, "fish", ["A"] * 5, "Fish Tycoon - Copy")
        found = [p.name for p in save_tools.modded_save_folders("fish", self.root)]
        self.assertEqual(found, ["Fish Tycoon - Modded", "Fish Tycoon - Modded Upgrades"])
        self.assertTrue(save_tools.is_save_folder("fish", self.root / "LDW" / "Fish Tycoon"))
        self.assertFalse(save_tools.is_save_folder("plant", self.root / "LDW" / "Fish Tycoon"))

    def test_rename_changes_the_list_and_the_slot_files_only(self) -> None:
        for game_id in save_tools.FORMATS:
            fmt = save_tools.FORMATS[game_id]
            folder = make_folder(self.root, game_id, ["Ana", "Bo", "Cy", "Di", "Ed"], f"{game_id} r")
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            report = save_tools.rename_slot(game_id, folder, 2, "Robert Fishkeeper", NoGame())
            self.assertEqual(report["old_name"], "Bo")
            self.assertEqual(save_tools.read_slot_names(game_id, folder), ["Ana", "Robert Fishkeeper", "Cy", "Di", "Ed"])
            expected = {f"{fmt.title}0.ldw"} | {f"{fmt.title}{2 + extra}.ldw" for extra in fmt.slot_file_offsets}
            self.assertEqual(set(report["changed"]), expected)
            for name, data in before.items():
                after = (folder / name).read_bytes()
                self.assertEqual(len(after), len(data))
                if name not in expected:
                    self.assertEqual(after, data, f"{name} must not change")
            slot = (folder / f"{fmt.title}2.ldw").read_bytes()
            self.assertTrue(slot[fmt.slot_name_offset:].startswith(b"Robert Fishkeeper\0"))
            self.assertEqual(slot[fmt.slot_name_offset + 40], 0x7A, "data after the name field is kept")
            self.assertTrue((folder / f"{fmt.title}0.ldw").read_bytes().endswith(b"TAIL"))
            self.assertTrue(Path(report["backup"]).is_dir())
            self.assertTrue(Path(report["backup"]).name.endswith("(before rename)"))

    def test_rename_leaves_a_file_whose_name_does_not_match(self) -> None:
        fmt = save_tools.FORMATS["fish"]
        folder = make_folder(self.root, "fish", ["Ana", "Bo", "Cy", "Di", "Ed"])
        other = folder / f"{fmt.title}22.ldw"
        data = bytearray(other.read_bytes())
        data[fmt.slot_name_offset: fmt.slot_name_offset + 4] = b"Zed\0"
        other.write_bytes(bytes(data))
        report = save_tools.rename_slot("fish", folder, 2, "Bea", NoGame())
        self.assertIn(other.name, report["skipped"])
        self.assertEqual(other.read_bytes(), bytes(data))

    def test_bad_names_are_refused_before_anything_changes(self) -> None:
        folder = make_folder(self.root, "fish", ["Ana", "Bo", "Cy", "Di", "Ed"])
        for bad in ("", " Ana", "x" * 32, "Zoë", "tab\there", "NEW PLAYER", "New Player"):
            with self.assertRaises(save_tools.SaveToolError, msg=bad):
                save_tools.rename_slot("fish", folder, 1, bad, NoGame())
        self.assertFalse((folder / "Backups").exists())
        self.assertEqual(save_tools.read_slot_names("fish", folder)[0], "Ana")

    def test_only_slots_with_a_saved_game_can_be_renamed(self) -> None:
        fmt = save_tools.FORMATS["plant"]
        folder = make_folder(self.root, "plant", ["Ana", "NEW PLAYER", "", "Di", "Ed"])
        (folder / f"{fmt.title}4.ldw").unlink()            # listed, but its game is gone
        for slot in (2, 3, 4):
            with self.assertRaises(save_tools.SaveToolError, msg=f"slot {slot}"):
                save_tools.rename_slot("plant", folder, slot, "Someone", NoGame())
        self.assertFalse((folder / "Backups").exists(), "nothing is backed up or written")
        self.assertEqual(save_tools.read_slot_names("plant", folder), ["Ana", "NEW PLAYER", "", "Di", "Ed"])
        self.assertTrue(save_tools.slot_is_active("plant", folder, 1, "Ana"))
        self.assertEqual(save_tools.rename_slot("plant", folder, 5, "Edna", NoGame())["new_name"], "Edna")

    def test_rename_refuses_while_the_game_runs(self) -> None:
        class Running:
            def find(self, exe_name):
                return [1234]

        folder = make_folder(self.root, "fish", ["Ana", "Bo", "Cy", "Di", "Ed"], "Fish Tycoon - Modded")
        with self.assertRaises(save_tools.SaveToolError):
            save_tools.rename_slot("fish", folder, 1, "Zed", Running())
        self.assertEqual(save_tools.read_slot_names("fish", folder)[0], "Ana")


class ToolsTabWiringTests(unittest.TestCase):
    def test_gui_has_the_tools_tab_and_ships_the_module(self) -> None:
        source = (ROOT / "src" / "tycoon_fix_patcher_gui.py").read_text(encoding="utf-8")
        self.assertIn('notebook.add(tools, text="Tools")', source)
        self.assertIn("tools_tab.ToolsTab(self, tab)", source)
        tools = (ROOT / "src" / "tools_tab.py").read_text(encoding="utf-8")
        for handler in ("back_up", "restore", "rename", "mechanics", "show_help"):
            self.assertIn(f"    def {handler}(", tools)
        release = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        self.assertIn('"src/save_tools.py"', release)
        self.assertIn('"src/save_backup.py"', release)
        self.assertIn('"src/tools_tab.py"', release)


if __name__ == "__main__":
    unittest.main()
