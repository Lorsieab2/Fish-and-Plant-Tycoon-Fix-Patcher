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


    # ------------------------------------------------------------ copy a slot

    def side_files(self, folder: Path, game_id: str, slot: int) -> dict[str, bytes]:
        fmt = save_tools.FORMATS[game_id]
        data = folder / f"{fmt.title} Fix Patcher Data"
        data.mkdir(exist_ok=True)
        made = {f"Extra Tanks {slot}.dat": b"tanks%d" % slot, f"Tank Animals {slot}.previous.dat": b"prev%d" % slot,
                f"DS Fish {slot}.tmp": b"tmp", f"Tank Animals {slot}.unreadable-1.dat": b"aside"}
        for name, body in made.items():
            (data / name).write_bytes(body)
        return made

    def test_copy_makes_the_empty_slot_a_copy_under_the_new_name(self) -> None:
        for game_id in save_tools.FORMATS:
            fmt = save_tools.FORMATS[game_id]
            folder = make_folder(self.root, game_id, ["Ana", "Bo", "Cy", "Di", "Ed"], f"{game_id} c")
            for extra in fmt.slot_file_offsets:
                (folder / f"{fmt.title}{4 + extra}.ldw").unlink()
            names = save_tools.read_slot_names(game_id, folder)
            settings = bytearray((folder / f"{fmt.title}0.ldw").read_bytes())
            at = fmt.names_offset + 3 * fmt.name_stride
            settings[at: at + fmt.name_stride] = b"NEW PLAYER".ljust(fmt.name_stride, b"\0")
            settings[fmt.started_offset + 1] = 1                  # Bo's game is started; slot 4's is not
            (folder / f"{fmt.title}0.ldw").write_bytes(bytes(settings))
            self.side_files(folder, game_id, 2)
            data = folder / f"{fmt.title} Fix Patcher Data"
            before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            report = save_tools.copy_slot(game_id, folder, 2, 4, "Bo Again", NoGame())
            self.assertEqual((report["old_name"], report["new_name"]), ("Bo", "Bo Again"))
            self.assertEqual(save_tools.read_slot_names(game_id, folder), [names[0], "Bo", "Cy", "Bo Again", "Ed"])
            self.assertTrue(save_tools.slot_is_active(game_id, folder, 4, "Bo Again"))
            started = (folder / f"{fmt.title}0.ldw").read_bytes()[fmt.started_offset: fmt.started_offset + 5]
            self.assertEqual(started[3], 1, "the copy is marked as a started game, else the game starts anew")
            for extra in fmt.slot_file_offsets:
                source = (folder / f"{fmt.title}{2 + extra}.ldw").read_bytes()
                copy = (folder / f"{fmt.title}{4 + extra}.ldw").read_bytes()
                self.assertEqual(len(copy), len(source))
                self.assertTrue(copy[fmt.slot_name_offset:].startswith(b"Bo Again\0"))
                field = fmt.slot_name_offset + fmt.max_name + 1
                self.assertEqual(copy[:fmt.slot_name_offset], source[:fmt.slot_name_offset])
                self.assertEqual(copy[field:], source[field:], "everything but the name is the same")
            self.assertEqual((data / "Extra Tanks 4.dat").read_bytes(), b"tanks2")
            self.assertEqual((data / "Tank Animals 4.previous.dat").read_bytes(), b"prev2")
            self.assertFalse((data / "DS Fish 4.tmp").exists(), "temporary files are not copied")
            self.assertFalse((data / "Tank Animals 4.unreadable-1.dat").exists(), "set-aside files are not copied")
            for rel, body in before.items():
                if rel.name != f"{fmt.title}0.ldw":
                    self.assertEqual((folder / rel).read_bytes(), body, f"{rel} must not change")
            backup = Path(report["backup"])
            self.assertTrue(backup.name.endswith("(before copy)"))
            self.assertFalse((backup / f"{fmt.title}4.ldw").exists(), "the backup is from before the copy")
            self.assertFalse(list(folder.glob("*.tmp")))

    def test_copy_replaces_an_empty_slots_leftovers(self) -> None:
        fmt = save_tools.FORMATS["plant"]
        folder = make_folder(self.root, "plant", ["Ana", "Bo", "NEW PLAYER", "Di", "Ed"])
        (folder / f"{fmt.title}41.ldw").unlink()               # Ana has no third file
        old = self.side_files(folder, "plant", 3)                # an old player's files on slot 3
        self.side_files(folder, "plant", 1)
        (folder / f"{fmt.title} Fix Patcher Data" / "Extra Tanks 1.dat").unlink()
        report = save_tools.copy_slot("plant", folder, 1, 3, "Ana Two", NoGame())
        data = folder / f"{fmt.title} Fix Patcher Data"
        self.assertFalse((folder / f"{fmt.title}43.ldw").exists(), "slot 3's old third file is gone")
        self.assertFalse((data / "Extra Tanks 3.dat").exists(), "and its old patcher data")
        self.assertEqual((data / "Tank Animals 3.previous.dat").read_bytes(), b"prev1")
        self.assertIn(f"{fmt.title}43.ldw", report["removed"])
        backup = Path(report["backup"])
        self.assertEqual((backup / f"{fmt.title} Fix Patcher Data" / "Extra Tanks 3.dat").read_bytes(),
                         old["Extra Tanks 3.dat"], "the leftovers are in the backup")

    def test_a_slot_the_game_still_lists_is_not_empty(self) -> None:
        for game_id in save_tools.FORMATS:
            fmt = save_tools.FORMATS[game_id]
            folder = make_folder(self.root, game_id, ["Ana", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER", "Ed"],
                                 f"{game_id} e")
            for extra in fmt.slot_file_offsets:
                (folder / f"{fmt.title}{3 + extra}.ldw").unlink()
                (folder / f"{fmt.title}{4 + extra}.ldw").unlink()
            settings = bytearray((folder / f"{fmt.title}0.ldw").read_bytes())
            settings[fmt.started_offset + 3] = 1                     # slot 4: a started game, no files
            (folder / f"{fmt.title}0.ldw").write_bytes(bytes(settings))
            # Slot 2: "NEW PLAYER" in the list, but its save still holds a player's name ("Bo"), as seen in a
            # vanilla Fish Tycoon folder; the game lists that slot as Bo.
            data = bytearray((folder / f"{fmt.title}2.ldw").read_bytes())
            data[fmt.slot_name_offset: fmt.slot_name_offset + 3] = b"Bo\0"
            (folder / f"{fmt.title}2.ldw").write_bytes(bytes(data))
            self.assertEqual([save_tools.slot_is_empty(game_id, folder, s) for s in range(1, 6)],
                             [False, False, True, False, False])
            for target in (2, 4, 5):
                with self.assertRaises(save_tools.SaveToolError, msg=target):
                    save_tools.copy_slot(game_id, folder, 1, target, "Ann", NoGame())
            self.assertFalse((folder / "Backups").exists())

    def test_copy_is_refused_before_anything_changes(self) -> None:
        folder = make_folder(self.root, "fish", ["Ana", "Bo", "NEW PLAYER", "Di", "Ed"])
        fmt = save_tools.FORMATS["fish"]
        (folder / f"{fmt.title}3.ldw").unlink()
        (folder / f"{fmt.title}23.ldw").unlink()

        class Running:
            def find(self, exe_name):
                return [1234]

        cases = ((1, 2, "Ann", NoGame()), (3, 1, "Ann", NoGame()), (1, 1, "Ann", NoGame()), (1, 6, "Ann", NoGame()),
                 (1, 3, "NEW PLAYER", NoGame()), (1, 3, "x" * 32, NoGame()), (1, 3, "Ann", Running()))
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        for source, target, name, processes in cases:
            with self.assertRaises(save_tools.SaveToolError, msg=(source, target, name)):
                save_tools.copy_slot("fish", folder, source, target, name, processes)
        self.assertFalse((folder / "Backups").exists())
        self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)
        self.assertEqual(save_tools.copy_slot("fish", folder, 1, 3, "Ann", NoGame())["target"], 3)

class ToolsTabWiringTests(unittest.TestCase):
    def test_gui_has_the_tools_tab_and_ships_the_module(self) -> None:
        source = (ROOT / "src" / "tycoon_fix_patcher_gui.py").read_text(encoding="utf-8")
        self.assertIn('notebook.add(tools, text="Tools")', source)
        self.assertIn("tools_tab.ToolsTab(self, tab)", source)
        tools = (ROOT / "src" / "tools_tab.py").read_text(encoding="utf-8")
        for handler in ("back_up", "restore", "rename", "copy_player", "mechanics", "show_help"):
            self.assertIn(f"    def {handler}(", tools)
        release = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        self.assertIn('"src/save_tools.py"', release)
        self.assertIn('"src/save_backup.py"', release)
        self.assertIn('"src/tools_tab.py"', release)


if __name__ == "__main__":
    unittest.main()
