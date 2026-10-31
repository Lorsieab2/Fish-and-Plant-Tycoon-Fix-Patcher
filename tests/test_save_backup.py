"""Back Up Saves and Restore (src/save_backup.py): the Virtual Villagers Fun
Patcher's design for Fish and Plant Tycoon. Synthetic save folders laid out
like the games' own and a fake process list, so no game is needed."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import save_backup  # noqa: E402
import save_tools  # noqa: E402
from test_save_tools import make_folder  # noqa: E402


class FakeProcesses:
    """A game that is or is not running; records what was paused and resumed."""

    def __init__(self, running: int = 0, refuse: bool = False) -> None:
        self.running = running
        self.refuse = refuse
        self.suspended: list[int] = []
        self.resumed: list[int] = []
        self.asked: list[str] = []

    def find(self, exe_name: str) -> list[int]:
        self.asked.append(exe_name)
        return list(range(100, 100 + self.running))

    def suspend(self, pid: int, exe_name: str) -> object:
        if self.refuse:
            raise save_backup.PauseRefused("access was denied")
        self.suspended.append(pid)
        return pid

    def resume(self, handle: object) -> None:
        self.resumed.append(handle)


def snapshot(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*")
            if p.is_file() and p.relative_to(folder).parts[0] != "Backups"}


class SaveBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = make_folder(self.root, "plant", ["Ana", "Bo", "Cy", "Di", "Ed"], "Plant Tycoon - Modded")
        data = self.folder / "Plant Tycoon Fix Patcher Data"
        data.mkdir()
        for slot in (1, 2):
            (data / f"New Flowers {slot}.dat").write_bytes(f"flowers {slot}".encode())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def back_up(self, processes=None, when=None):
        return save_backup.back_up_save_folder(self.folder, processes or FakeProcesses(), when)

    def test_a_backup_is_a_checked_copy_inside_the_save_folder(self) -> None:
        result = self.back_up(when=datetime(2026, 10, 26, 18, 5, 9))
        self.assertEqual(result.backup_folder, self.folder / "Backups" / "Backup 2026-10-26 18-05-09")
        self.assertEqual(snapshot(result.backup_folder), snapshot(self.folder))
        self.assertEqual(result.file_count, len(snapshot(self.folder)))
        again = self.back_up(when=datetime(2026, 10, 26, 18, 5, 9))
        self.assertEqual(again.backup_folder.name, "Backup 2026-10-26 18-05-09 (2)")
        self.assertFalse((again.backup_folder / "Backups").exists(), "Backups is never copied into itself")

    def test_a_running_game_is_paused_for_the_copy_and_resumed(self) -> None:
        processes = FakeProcesses(running=2)
        result = self.back_up(processes)
        self.assertEqual(processes.asked[0], "Plant Tycoon - Modded.exe")
        self.assertEqual(processes.suspended, [100, 101])
        self.assertEqual(sorted(processes.resumed), [100, 101])
        self.assertEqual(result.paused, 2)

    def test_a_game_that_cannot_be_paused_is_not_backed_up(self) -> None:
        with self.assertRaises(save_backup.PauseRefused):
            self.back_up(FakeProcesses(running=1, refuse=True))
        self.assertEqual(save_backup.list_backups("plant", self.folder), [])

    def test_backups_are_listed_newest_first_with_their_players(self) -> None:
        self.back_up(when=datetime(2026, 10, 26, 10, 0, 0))
        self.back_up(when=datetime(2026, 10, 26, 11, 0, 0))
        (self.folder / "Backups" / "Backup 2026-10-26 12-00-00 INCOMPLETE").mkdir()
        found = save_backup.list_backups("plant", self.folder)
        self.assertEqual([b.when.hour for b in found], [11, 10])
        self.assertEqual(found[0].players, {1: "Ana", 2: "Bo", 3: "Cy", 4: "Di", 5: "Ed"})
        self.assertIn("1: Ana", found[0].describe())

    def test_restore_the_whole_folder(self) -> None:
        before = snapshot(self.folder)
        backup = self.back_up().backup_folder
        (self.folder / "Plant Tycoon1.ldw").write_bytes(b"ldwg changed")
        (self.folder / "Plant Tycoon9.ldw").write_bytes(b"ldwg new")
        result = save_backup.restore_backup("plant", self.folder, backup, None, FakeProcesses())
        self.assertEqual(snapshot(self.folder), before)
        self.assertTrue(result.before_restore.backup_folder.name.endswith("(before restore)"))
        self.assertIn("Plant Tycoon9.ldw", snapshot(result.before_restore.backup_folder))

    def test_restore_one_slot_touches_only_that_slot_and_its_name(self) -> None:
        backup = self.back_up().backup_folder
        save_tools.rename_slot("plant", self.folder, 2, "Bea", FakeProcesses())
        save_tools.rename_slot("plant", self.folder, 3, "Cyd", FakeProcesses())
        data = self.folder / "Plant Tycoon Fix Patcher Data"
        (data / "New Flowers 2.dat").write_bytes(b"later 2")
        (data / "New Flowers 1.dat").write_bytes(b"later 1")
        result = save_backup.restore_backup("plant", self.folder, backup, 2, FakeProcesses())
        names = save_tools.read_slot_names("plant", self.folder)
        self.assertEqual(names[1], "Bo", "slot 2's name is back")
        self.assertEqual(names[2], "Cyd", "slot 3 is untouched")
        self.assertEqual((data / "New Flowers 2.dat").read_bytes(), b"flowers 2")
        self.assertEqual((data / "New Flowers 1.dat").read_bytes(), b"later 1")
        for extra in (0, 20, 40):
            self.assertEqual((self.folder / f"Plant Tycoon{2 + extra}.ldw").read_bytes(),
                             (backup / f"Plant Tycoon{2 + extra}.ldw").read_bytes())
        self.assertIsNotNone(result.before_restore)

    def test_restore_is_refused_while_the_game_runs(self) -> None:
        backup = self.back_up().backup_folder
        (self.folder / "Plant Tycoon1.ldw").write_bytes(b"ldwg changed")
        with self.assertRaises(save_backup.RestoreRefused):
            save_backup.restore_backup("plant", self.folder, backup, None, FakeProcesses(running=1))
        self.assertEqual((self.folder / "Plant Tycoon1.ldw").read_bytes(), b"ldwg changed")

    def test_a_slot_restore_refuses_a_changed_file_of_no_slot(self) -> None:
        backup = self.back_up().backup_folder
        (self.folder / "notes.txt").write_bytes(b"mine")
        with self.assertRaises(save_backup.RestoreRefused):
            save_backup.plan_restore("plant", self.folder, backup, 1)

    def test_file_slots(self) -> None:
        for name, slot in (("Plant Tycoon0.ldw", "settings"), ("Plant Tycoon3.ldw", 3), ("Plant Tycoon23.ldw", 3),
                           ("Plant Tycoon43.ldw", 3), ("Plant Tycoon7.ldw", "unknown"),
                           ("Plant Tycoon Fix Patcher Data/Seed Boxes 4.dat", 4),
                           ("Plant Tycoon Fix Patcher Data/Plant Upgrades 5.dat.unreadable", 5),
                           ("Plant Tycoon Fix Patcher Data/Seed Boxes 43.dat", 3),
                           ("Plant Tycoon Fix Patcher Data/Extra Greenhouses 22.previous.dat", 2)):
            self.assertEqual(save_backup.file_slot("plant", Path(name)), slot, name)
        self.assertEqual(save_backup.file_slot("fish", Path("Fish Tycoon25.ldw")), 5)
        self.assertEqual(save_backup.file_slot("fish", Path("Fish Tycoon45.ldw")), 5)   # Fish keeps n + 40 too
        self.assertEqual(save_backup.file_slot("fish", Path("Fish Tycoon Fix Patcher Data/DS Fish 2.dat")), 2)
        # The copies a DLL names before ".dat": set aside when unreadable, or kept from the last save.
        for name, slot in (("DS Fish 2.unreadable-1.dat", 2), ("Ornaments 3.unreadable-12.dat", 3),
                           ("Tank Animals 4.previous.dat", 4), ("Tank Animals 4.tmp.dat", 4),
                           ("Extra Tanks 1.dat.tmp", 1), ("Tank Animals 4.dat", 4), ("Notes 2.txt", "unknown"),
                           ("DS Fish 7.dat", "unknown"), ("DS Fish 2.unreadable-1.dat.tmp", 2),
                           ("Extra Tanks 21.dat", 1), ("DS Fish 25.unreadable-1.dat", 5), ("DS Fish 45.dat", 5), ("DS Fish 65.dat", "unknown")):
            self.assertEqual(save_backup.file_slot("fish", Path("Fish Tycoon Fix Patcher Data") / name), slot, name)

    def test_delete_backup(self) -> None:
        backup = self.back_up().backup_folder
        save_backup.delete_backup(self.folder, backup)
        self.assertFalse(backup.exists())
        with self.assertRaises(save_backup.RestoreRefused):
            save_backup.delete_backup(self.folder, self.folder)

    def test_an_older_zip_backup_is_imported_as_a_backup(self) -> None:
        archive_path = self.root / "Plant Tycoon - Modded 2026-10-26 101500.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name, data in snapshot(self.folder).items():
                archive.writestr(name, data)
        made = save_backup.import_zip_backup("plant", self.folder, archive_path)
        self.assertEqual(made.name, "Backup 2026-10-26 10-15-00")
        self.assertEqual(snapshot(made), snapshot(self.folder))
        evil = self.root / "evil.zip"
        with zipfile.ZipFile(evil, "w") as archive:
            archive.writestr("../escape.ldw", b"x")
            archive.writestr("Plant Tycoon0.ldw", b"ldwg")
        foreign = self.root / "foreign.zip"
        with zipfile.ZipFile(foreign, "w") as archive:
            archive.writestr("notes.txt", b"hello")
        for bad in (evil, foreign):
            with self.assertRaises(save_backup.BackupError):
                save_backup.import_zip_backup("plant", self.folder, bad)


if __name__ == "__main__":
    unittest.main()
