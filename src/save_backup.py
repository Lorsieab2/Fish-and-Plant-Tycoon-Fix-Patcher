"""Back up and restore a Fish Tycoon or Plant Tycoon save folder, the way the
Virtual Villagers Fun Patcher does it (src/vv_save_backup.py there), for one
consistent tool across the owner's patchers.

Back up
    Everything in the save folder (the game's .ldw files and the patcher's
    "<Game> Fix Patcher Data" folder) except its Backups folder is copied into
    "Backups\\Backup YYYY-MM-DD HH-MM-SS" inside the same save folder. Each file
    is read back and checked against the original's size and SHA-256, and keeps
    the original's times. The copy is made under "... (in progress)" and gets
    its final name only once every file checks out; a failed copy is renamed
    "... INCOMPLETE" and never offered. An existing backup is never written
    into.

    If the game that saves there is running, every process of it is paused
    (suspended) for the copy and always resumed afterwards; if one cannot be
    paused, nothing is copied. The game is never closed. Both games save on
    quit and autosave while running, so a running game's backup holds the
    last save or autosave.

Restore
    The whole folder, or one player slot, only while the game is closed, and
    only after the current saves are backed up as "Backup <date> (before
    restore)", so every restore can be undone. A slot is its own files
    ("<Game><slot>.ldw" and the game's older generations "+20", and for Plant
    Tycoon "+40") and the patcher's "<name> <slot>.dat" files, with their
    temporary, previous and set-aside copies. The settings
    file "<Game>0.ldw" is shared by every slot; a one-slot restore puts back
    only that slot's name in its player list and leaves the rest of it alone.
    On any failure every changed file is put back from the before-restore
    backup.

Nothing here touches Tk; the GUI runs it on its thread and the tests drive it
with a temporary folder and a fake process controller.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import shutil
import stat
import sys
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, Protocol

import long_paths
import save_tools

BACKUPS_FOLDER = "Backups"
BACKUP_PREFIX = "Backup "
IN_PROGRESS = " (in progress)"
INCOMPLETE = " INCOMPLETE"
DELETING = " (deleting)"
BEFORE_RESTORE = "(before restore)"
BEFORE_RENAME = "(before rename)"
BEFORE_COPY = "(before copy)"
HASH_CHUNK = 1 << 20
RETRIES = 5
RETRY_SECONDS = 0.5
_BACKUP_NAME = re.compile(
    r"^Backup (\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2})(?: \((\d+)\))?(?: (\(before (?:restore|rename|copy)\)))?$"
)


class BackupError(Exception):
    """A backup, restore or delete that did not happen; the message says why."""


class PauseRefused(BackupError):
    """The game is running and could not be paused, so nothing was copied."""


class RestoreRefused(BackupError):
    """A restore that was not started; nothing was changed."""


def game_exe_name(save_folder: Path) -> str:
    """The exe that saves into ``save_folder``: the games name the folder after themselves."""
    return f"{save_folder.name}.exe"


# --------------------------------------------------------------------- copying

_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003


def _is_link(path: Path) -> bool:
    """A symbolic link or junction, which the copy never follows."""
    if path.is_symlink():
        return True
    try:
        return getattr(path.lstat(), "st_reparse_tag", 0) == _IO_REPARSE_TAG_MOUNT_POINT
    except OSError:
        return False


def files_to_back_up(save_folder: Path) -> list[Path]:
    """Every file under ``save_folder`` except its Backups folder, relative and sorted."""
    files: list[Path] = []
    save_folder = long_paths.extended(save_folder)

    def walk(folder: Path, relative: Path) -> None:
        for entry in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
            if relative == Path() and entry.name.casefold() == BACKUPS_FOLDER.casefold():
                continue
            if entry.is_dir():
                if not _is_link(entry):
                    walk(entry, relative / entry.name)
            elif entry.is_file() and not _is_link(entry):
                files.append(relative / entry.name)

    walk(save_folder, Path())
    return files


@dataclass
class CopiedFile:
    relative: Path
    size: int
    sha256: str


@dataclass
class BackupResult:
    save_folder: Path
    backup_folder: Path
    files: list[CopiedFile] = field(default_factory=list)
    paused: int = 0                                        # game processes paused for the copy
    resume_problems: list[str] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)


def backup_folder_name(now: datetime) -> str:
    return f"{BACKUP_PREFIX}{now.strftime('%Y-%m-%d %H-%M-%S')}"


def _backup_names(now: datetime, suffix: str) -> Iterator[str]:
    base = backup_folder_name(now)
    for attempt in range(1, 1000):
        name = base if attempt == 1 else f"{base} ({attempt})"
        yield f"{name} {suffix}" if suffix else name


def _new_backup_folder(save_folder: Path, now: datetime, suffix: str) -> Path:
    """A new, empty "... (in progress)" folder; an existing backup is never reused."""
    backups = save_folder / BACKUPS_FOLDER
    backups.mkdir(exist_ok=True)
    for name in _backup_names(now, suffix):
        if (backups / name).exists():
            continue
        candidate = backups / (name + IN_PROGRESS)
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise BackupError(f"Too many backups named {backup_folder_name(now)} in {backups}.")


def _finish_backup(staging: Path, now: datetime, suffix: str) -> Path:
    """Give a verified backup its final name (a sync program may hold the folder a moment)."""
    for name in _backup_names(now, suffix):
        final = staging.with_name(name)
        if final.exists():
            continue
        for attempt in range(RETRIES):
            try:
                staging.rename(final)
                return final
            except FileExistsError:
                break
            except PermissionError:
                if attempt == RETRIES - 1:
                    raise
                time.sleep(RETRY_SECONDS)
    raise BackupError(f"No free name for the backup in {staging.parent}.")


def _set_aside(staging: Path) -> Path:
    """Rename a failed backup "... INCOMPLETE" so it is never offered."""
    base = staging.name.removesuffix(IN_PROGRESS) + INCOMPLETE
    for attempt in range(1, 100):
        target = staging.with_name(base if attempt == 1 else f"{base} ({attempt})")
        if target.exists():
            continue
        try:
            staging.rename(target)
        except OSError:
            continue
        return target
    return staging


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _keep_times(path: Path, source: os.stat_result) -> None:
    try:
        os.utime(path, ns=(source.st_atime_ns, source.st_mtime_ns))
    except OSError as exc:
        raise BackupError(f"The time of {path.name} could not be kept ({exc}).") from exc


def _copy_one(source: Path, destination: Path) -> CopiedFile:
    """Copy one file, never over an existing one, and verify it by size and hash."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    original = source.stat()
    with source.open("rb") as reader, destination.open("xb") as writer:
        while chunk := reader.read(HASH_CHUNK):
            size += len(chunk)
            digest.update(chunk)
            writer.write(chunk)
    expected = digest.hexdigest()
    if _hash_file(destination) != (size, expected):
        raise BackupError(f"The copy of {source.name} does not match the original.")
    if _hash_file(source) != (size, expected):
        raise BackupError(f"{source.name} changed while it was being copied.")
    _keep_times(destination, original)
    return CopiedFile(Path(), size, expected)


def copy_save_folder(save_folder: Path, now: datetime | None = None, suffix: str = "") -> BackupResult:
    """Copy the save folder into a new Backups\\Backup <date> folder inside it."""
    shown = long_paths.plain(save_folder)
    save_folder = long_paths.extended(save_folder)
    if not save_folder.is_dir():
        raise BackupError(f"The save folder does not exist: {shown}")
    relatives = files_to_back_up(save_folder)
    if not relatives:
        raise BackupError(f"There is nothing to back up in {shown}.")
    when = now or datetime.now()
    staging = _new_backup_folder(save_folder, when, suffix)
    result = BackupResult(shown, staging)
    try:
        for relative in relatives:
            copied = _copy_one(save_folder / relative, staging / relative)
            copied.relative = relative
            result.files.append(copied)
        result.backup_folder = long_paths.plain(_finish_backup(staging, when, suffix))
    except (OSError, BackupError) as exc:
        where = long_paths.plain(_set_aside(staging))
        reason = exc if isinstance(exc, BackupError) else f"{type(exc).__name__}: {exc}"
        raise BackupError(
            f"The backup could not be completed ({reason}). The partial copy was kept as "
            f"{where} and is NOT a usable backup."
        ) from exc
    return result


# --------------------------------------------------------------------- pausing

class ProcessController(Protocol):
    def find(self, exe_name: str) -> list[int]: ...
    def suspend(self, pid: int, exe_name: str) -> object: ...
    def resume(self, handle: object) -> None: ...


class WindowsProcesses:
    """Find, suspend and resume game processes with the Windows API."""

    PROCESS_SUSPEND_RESUME = 0x0800
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    TH32CS_SNAPPROCESS = 0x00000002
    ERROR_NO_MORE_FILES = 18

    def __init__(self) -> None:
        from ctypes import wintypes

        self._wintypes = wintypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._ntdll = ctypes.WinDLL("ntdll")
        k = self._kernel32
        k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        for name in ("NtSuspendProcess", "NtResumeProcess"):
            function = getattr(self._ntdll, name)
            function.argtypes = [wintypes.HANDLE]
            function.restype = ctypes.c_long

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
            ]

        self._entry_type = PROCESSENTRY32W
        k.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k.Process32FirstW.restype = wintypes.BOOL
        k.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k.Process32NextW.restype = wintypes.BOOL

    def find(self, exe_name: str) -> list[int]:
        k = self._kernel32
        snapshot = k.CreateToolhelp32Snapshot(self.TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == self._wintypes.HANDLE(-1).value:
            raise BackupError(f"Could not list the running programs (error {ctypes.get_last_error()}).")
        pids: list[int] = []
        try:
            entry = self._entry_type()
            entry.dwSize = ctypes.sizeof(entry)
            more = k.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                if entry.szExeFile.casefold() == exe_name.casefold():
                    pids.append(int(entry.th32ProcessID))
                more = k.Process32NextW(snapshot, ctypes.byref(entry))
            error = ctypes.get_last_error()
            if error != self.ERROR_NO_MORE_FILES:
                raise BackupError(f"Could not read the whole list of running programs (error {error}).")
        finally:
            k.CloseHandle(snapshot)
        return pids

    def suspend(self, pid: int, exe_name: str) -> object:
        k = self._kernel32
        handle = k.OpenProcess(self.PROCESS_SUSPEND_RESUME | self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            reason = "access was denied" if error == 5 else f"Windows error {error}"
            raise PauseRefused(f"{exe_name} (process {pid}) is running but could not be paused: {reason}.")
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = self._wintypes.DWORD(len(buffer))
            if not k.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                raise PauseRefused(f"{exe_name} (process {pid}) could not be checked before pausing.")
            if Path(buffer.value).name.casefold() != exe_name.casefold():
                raise PauseRefused(f"Process {pid} is no longer {exe_name}; try the backup again.")
            status = self._ntdll.NtSuspendProcess(handle)
            if status != 0:
                raise PauseRefused(
                    f"{exe_name} (process {pid}) could not be paused (status 0x{status & 0xFFFFFFFF:08X}).")
        except BaseException:
            k.CloseHandle(handle)
            raise
        return handle

    def resume(self, handle: object) -> None:
        try:
            status = self._ntdll.NtResumeProcess(handle)
            if status != 0:
                raise BackupError(
                    f"The game could not be resumed (status 0x{status & 0xFFFFFFFF:08X}). "
                    "Close it from Task Manager if it stays frozen.")
        finally:
            self._kernel32.CloseHandle(handle)


@dataclass
class Pause:
    count: int = 0
    problems: list[str] = field(default_factory=list)


@contextmanager
def paused_game(exe_name: str, processes: ProcessController) -> Iterator[Pause]:
    """Suspend every running process of ``exe_name``; always resume them."""
    pause = Pause()
    paused: list[object] = []
    failure: BaseException | None = None
    try:
        for pid in processes.find(exe_name):
            paused.append(processes.suspend(pid, exe_name))
        pause.count = len(paused)
        yield pause
    except BaseException as exc:
        failure = exc
        raise
    finally:
        errors: list[str] = []
        for handle in reversed(paused):
            try:
                processes.resume(handle)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            if failure is not None:
                failure.add_note("The game could not be resumed: " + "; ".join(errors))
            else:
                pause.problems.extend(errors)


def back_up_save_folder(save_folder: Path, processes: ProcessController | None = None,
                        now: datetime | None = None, suffix: str = "") -> BackupResult:
    """Pause the game that uses ``save_folder`` (if running), copy, resume."""
    controller = processes if processes is not None else WindowsProcesses()
    with paused_game(game_exe_name(save_folder), controller) as pause:
        result = copy_save_folder(save_folder, now, suffix)
    result.paused = pause.count
    result.resume_problems = list(pause.problems)
    return result


def game_running(save_folder: Path, processes: ProcessController | None = None) -> int:
    controller = processes if processes is not None else WindowsProcesses()
    return len(controller.find(game_exe_name(save_folder)))


def describe_size(size: int) -> str:
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


# --------------------------------------------------------------------- listing

@dataclass
class BackupInfo:
    folder: Path
    when: datetime
    label: str                          # "", BEFORE_RESTORE, BEFORE_RENAME or BEFORE_COPY
    file_count: int
    total_bytes: int
    players: dict[int, str]             # slot -> player name, for the slots it holds

    def describe(self) -> str:
        label = f"  {self.label}" if self.label else ""
        players = ", ".join(f"{slot}: {name}" for slot, name in self.players.items()) or "no player saves"
        return (f"{self.when.strftime('%Y-%m-%d %H:%M:%S')}{label}  ·  {players}  ·  "
                f"{self.file_count} files, {describe_size(self.total_bytes)}")


def _parse_backup_name(name: str) -> tuple[datetime, int, str] | None:
    match = _BACKUP_NAME.match(name)
    if not match:
        return None
    try:
        when = datetime.strptime(match.group(1), "%Y-%m-%d %H-%M-%S")
    except ValueError:
        return None
    return when, int(match.group(2) or 1), match.group(3) or ""


def players_in(game_id: str, folder: Path) -> dict[int, str]:
    """Slot -> player name for each slot whose own save is in ``folder``."""
    title = save_tools.FORMATS[game_id].title
    try:
        names = save_tools.read_slot_names(game_id, folder)
    except (OSError, save_tools.SaveToolError):
        names = [""] * save_tools.FORMATS[game_id].slots
    return {slot: names[slot - 1] or "(no name)" for slot in range(1, len(names) + 1)
            if (folder / f"{title}{slot}.ldw").is_file()}


def list_backups(game_id: str, save_folder: Path) -> list[BackupInfo]:
    """This save folder's usable backups, newest first."""
    backups = long_paths.extended(save_folder) / BACKUPS_FOLDER
    if not backups.is_dir():
        return []
    found: list[tuple[datetime, int, BackupInfo]] = []
    for entry in backups.iterdir():
        parsed = _parse_backup_name(entry.name)
        if parsed is None or not entry.is_dir() or _is_link(entry):
            continue
        when, sequence, label = parsed
        files = files_to_back_up(entry)
        size = sum((entry / relative).stat().st_size for relative in files)
        found.append((when, sequence, BackupInfo(long_paths.plain(entry), when, label, len(files), size,
                                                 players_in(game_id, entry))))
    found.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [info for _when, _sequence, info in found]


# --------------------------------------------------------------------- restore

# "<name> <n>.dat", its temporary and set-aside copies ("... 2.dat.tmp",
# "... 2.dat.unreadable"), and the copies a DLL names before ".dat"
# ("DS Fish 2.unreadable-1.dat", "Tank Animals 2.previous.dat"). <n> is the
# game's own save number, so a DLL that writes beside each save also writes
# beside the game's older generations (n + 20 and n + 40, in both games).
_SIDE_FILE_SLOT = re.compile(r" (\d+)(?:\.[a-z]+(?:-\d+)?)?\.dat(?:\.tmp|\.unreadable[^\\/]*)?$", re.I)


def file_slot(game_id: str, relative: Path) -> int | str:
    """The player slot a file belongs to (1-5), "settings" for "<Game>0.ldw", or "unknown"."""
    fmt = save_tools.FORMATS[game_id]
    name = relative.name
    if len(relative.parts) == 1:
        match = re.fullmatch(re.escape(fmt.title) + r"(\d+)\.ldw", name, re.I)
        if match:
            number = int(match.group(1))
            if number == 0:
                return "settings"
            for extra in fmt.slot_file_offsets:
                if 1 <= number - extra <= fmt.slots:
                    return number - extra
        return "unknown"
    if relative.parts[0].casefold() == f"{fmt.title} Fix Patcher Data".casefold():
        match = _SIDE_FILE_SLOT.search(name)
        if match:
            number = int(match.group(1))
            for extra in fmt.slot_file_offsets:
                if 1 <= number - extra <= fmt.slots:
                    return number - extra
    return "unknown"


@dataclass
class RestorePlan:
    save_folder: Path
    backup: Path
    slot: int | None                                    # None: the whole save folder
    replace: list[Path] = field(default_factory=list)   # in both, different: the backup's wins
    add: list[Path] = field(default_factory=list)       # only in the backup
    remove: list[Path] = field(default_factory=list)    # only in the save folder now
    unchanged: list[Path] = field(default_factory=list)
    player_name: str | None = None                       # one slot: its name, put back in the player list

    @property
    def changes(self) -> int:
        return len(self.replace) + len(self.add) + len(self.remove) + (self.player_name is not None)


def _same_file(a: Path, b: Path) -> bool:
    try:
        return _hash_file(a) == _hash_file(b)
    except OSError:
        return False


def _require_backup_of(save_folder: Path, backup: Path) -> None:
    backups = (save_folder / BACKUPS_FOLDER).resolve()
    if (backup.resolve().parent != backups or _parse_backup_name(backup.name) is None
            or not backup.is_dir() or _is_link(backup)):
        raise RestoreRefused(f"{backup} is not one of this save folder's backups.")


def plan_restore(game_id: str, save_folder: Path, backup: Path, slot: int | None = None) -> RestorePlan:
    """Exactly which files a restore replaces, adds and removes.

    Whole folder: the save folder becomes the backup. One slot: only that
    slot's files are touched, plus its name in the player list; a file that
    belongs to no slot and differs is refused, since restoring the slot with
    or without it would leave the save inconsistent."""
    save_folder, backup = long_paths.extended(save_folder), long_paths.extended(backup)
    _require_backup_of(save_folder, backup)
    in_backup = set(files_to_back_up(backup))
    in_folder = set(files_to_back_up(save_folder))
    plan = RestorePlan(save_folder, backup, slot)
    for relative in sorted(in_backup | in_folder, key=lambda p: str(p).casefold()):
        here, there = relative in in_folder, relative in in_backup
        if slot is not None:
            owner = file_slot(game_id, relative)
            if owner == "settings":
                continue
            if owner == "unknown":
                if not (here and there and _same_file(save_folder / relative, backup / relative)):
                    raise RestoreRefused(
                        f"Only the whole save folder can be restored from this backup: {relative} "
                        "does not say which player it belongs to, and it is different in the backup.")
                continue
            if owner != slot:
                continue
        if here and there:
            (plan.unchanged if _same_file(save_folder / relative, backup / relative) else plan.replace).append(relative)
        elif there:
            plan.add.append(relative)
        else:
            plan.remove.append(relative)
    if slot is not None:
        title = save_tools.FORMATS[game_id].title
        if not (backup / f"{title}{slot}.ldw").is_file():
            raise RestoreRefused(f"This backup holds no save for player slot {slot}.")
        try:
            wanted = save_tools.read_slot_names(game_id, backup)[slot - 1]
            current = save_tools.read_slot_names(game_id, save_folder)[slot - 1]
        except (OSError, save_tools.SaveToolError) as exc:
            raise RestoreRefused(f"The player list could not be read ({exc}).") from exc
        if wanted != current:
            plan.player_name = wanted
    return plan


def _place(source: Path, target: Path) -> None:
    """Replace ``target`` with a verified copy of ``source``, atomically."""
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = _hash_file(source)
    while True:
        temp = target.with_name(f"~ftfp-{uuid.uuid4().hex[:8]}.tmp")
        try:
            writer = temp.open("xb")
        except FileExistsError:
            continue
        break
    try:
        with source.open("rb") as reader, writer:
            while chunk := reader.read(HASH_CHUNK):
                writer.write(chunk)
        if _hash_file(temp) != expected:
            raise BackupError(f"The restored copy of {target.name} did not match the backup.")
        _keep_times(temp, source.stat())
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()


def _set_player_name(game_id: str, save_folder: Path, slot: int, name: str) -> None:
    """Write one slot's name into the player list, keeping everything else in it."""
    fmt = save_tools.FORMATS[game_id]
    path = save_folder / f"{fmt.title}0.ldw"
    data = bytearray(path.read_bytes())
    at = fmt.names_offset + (slot - 1) * fmt.name_stride
    data[at: at + fmt.name_stride] = name.encode("latin-1").ljust(fmt.name_stride, b"\0")[: fmt.name_stride]
    temp = path.with_name(path.name + ".ftfp-restore.tmp")
    temp.write_bytes(bytes(data))
    os.replace(temp, path)


@dataclass
class RestoreResult:
    plan: RestorePlan
    before_restore: BackupResult | None


def restore_backup(game_id: str, save_folder: Path, backup: Path, slot: int | None = None,
                   processes: ProcessController | None = None, now: datetime | None = None) -> RestoreResult:
    """Restore ``backup`` (all of it, or one slot) into ``save_folder``, with the game closed.
    The current saves are backed up first as "(before restore)"; any failure puts every file back."""
    controller = processes if processes is not None else WindowsProcesses()
    save_folder, backup = long_paths.extended(save_folder), long_paths.extended(backup)
    exe = game_exe_name(save_folder)
    if game_running(save_folder, controller):
        raise RestoreRefused(
            f"{exe} is running. Quit the game from its own menu first: a running game writes its "
            "saves over the restored ones when it quits. Nothing was changed.")
    plan = plan_restore(game_id, save_folder, backup, slot)
    if plan.changes == 0:
        return RestoreResult(plan, None)
    before = copy_save_folder(save_folder, now, BEFORE_RESTORE) if files_to_back_up(save_folder) else None
    settings = Path(f"{save_tools.FORMATS[game_id].title}0.ldw")
    done: list[Path] = []
    try:
        for relative in plan.replace + plan.add:
            if game_running(save_folder, controller):
                raise BackupError(f"{exe} was started during the restore. Quit it and restore again.")
            done.append(relative)
            _place(backup / relative, save_folder / relative)
        for relative in plan.remove:
            done.append(relative)
            (save_folder / relative).unlink()
        if plan.player_name is not None:
            done.append(settings)
            _set_player_name(game_id, save_folder, slot, plan.player_name)
    except (OSError, BackupError) as exc:
        problems = _roll_back(save_folder, before, done)
        if problems:
            raise BackupError(
                f"The restore failed ({exc}) and some files could not be put back: {', '.join(problems)}. "
                f"Your saves as they were are in {before.backup_folder if before else '(no files)'}.") from exc
        raise BackupError(f"The restore failed ({exc}). Every file was put back as it was.") from exc
    return RestoreResult(plan, before)


def _roll_back(save_folder: Path, before: BackupResult | None, done: list[Path]) -> list[str]:
    problems: list[str] = []
    for relative in reversed(done):
        target = save_folder / relative
        original = long_paths.extended(before.backup_folder) / relative if before else None
        try:
            if original is not None and original.is_file():
                _place(original, target)
            elif target.exists():
                target.unlink()
        except (OSError, BackupError):
            problems.append(str(relative))
    return problems


# --------------------------------------------------------------------- delete

def _clear_read_only(path: str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def delete_backup(save_folder: Path, backup: Path) -> None:
    """Delete one of this save folder's backups. It is renamed "... (deleting)" first, so an
    interrupted delete never leaves a half-emptied folder that still looks like a backup."""
    save_folder, backup = long_paths.extended(save_folder), long_paths.extended(backup)
    _require_backup_of(save_folder, backup)
    doomed = backup.with_name(backup.name + DELETING)
    try:
        backup.rename(doomed)
    except OSError as exc:
        raise BackupError(f"The backup could not be deleted ({exc}); nothing was deleted.") from exc

    def retry_writable(function, path, _error):
        _clear_read_only(path)
        parent = os.path.dirname(path)
        if parent:
            _clear_read_only(parent)
        function(path)

    last: OSError | None = None
    for _attempt in range(RETRIES):
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(doomed, onexc=retry_writable)
            else:
                shutil.rmtree(doomed, onerror=retry_writable)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            last = exc
            time.sleep(RETRY_SECONDS)
    raise BackupError(f"The backup was taken off the list but {doomed} could not be removed completely ({last}).")


# --------------------------------------------------------- older zip backups

# Fix Patcher v1.0.17 made zip backups in Documents\LDW\"Fish and Plant
# Tycoon Fix Patcher Save Backups". Such a zip is imported as one of the save
# folder's backups (nothing in the save folder itself changes), and is then
# restored like any other: whole or one slot, with the current saves backed up
# first.
OLD_BACKUPS_FOLDER = "Fish and Plant Tycoon Fix Patcher Save Backups"
_ZIP_TIME = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2})(\d{2})(\d{2})")


def import_zip_backup(game_id: str, save_folder: Path, archive_path: Path) -> Path:
    title = save_tools.FORMATS[game_id].title
    save_folder = long_paths.extended(save_folder)
    match = _ZIP_TIME.search(archive_path.stem)
    try:
        when = datetime.strptime(" ".join(match.groups()), "%Y-%m-%d %H %M %S") if match else None
    except ValueError:
        when = None
    when = when or datetime.fromtimestamp(archive_path.stat().st_mtime)
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise BackupError("The zip is damaged; nothing was imported.")
        members = []
        for info in archive.infolist():
            name = Path(info.filename)
            if name.is_absolute() or ".." in name.parts or info.filename.startswith(("/", "\\")):
                raise BackupError(f"The zip holds an unsafe path: {info.filename}")
            if not info.is_dir() and name.parts[0].casefold() != BACKUPS_FOLDER.casefold():
                members.append(info)
        if not any(Path(m.filename).as_posix().casefold() == f"{title}0.ldw".casefold() for m in members):
            raise BackupError(f"This zip is not a {title} save backup (it has no {title}0.ldw).")
        staging = _new_backup_folder(save_folder, when, "")
        try:
            archive.extractall(staging, members)
            return long_paths.plain(_finish_backup(staging, when, ""))
        except (OSError, BackupError) as exc:
            where = _set_aside(staging)
            raise BackupError(f"The zip could not be imported ({exc}); the partial copy is {where}.") from exc


# --------------------------------------------------------------------- folders

PATCHER_SUFFIXES = ("Modded", "Modded Upgrades")


def is_patcher_save_folder(game_id: str, name: str) -> bool:
    """Whether ``name`` is the save folder of a copy the patcher built."""
    title = save_tools.FORMATS[game_id].title
    return any(name.casefold() == f"{title} - {suffix}".casefold() for suffix in PATCHER_SUFFIXES)


def find_save_folders(game_id: str, documents: Path | None = None) -> list[Path]:
    """Every Documents\\LDW\\<Game> - Modded... folder that holds saves, the patcher's own first.
    The original game's folder is not listed: the tools are for the modded copies. Another
    "<Game> - Modded..." folder (a copy the player renamed) is listed after them."""
    title = save_tools.FORMATS[game_id].title
    prefix = f"{title} - Modded".casefold()
    found = [path for path in save_tools.save_folders(game_id, documents) if path.name.casefold().startswith(prefix)]
    order = [f"{title} - {suffix}".casefold() for suffix in PATCHER_SUFFIXES]

    def key(path: Path) -> tuple[int, int, str]:
        name = path.name.casefold()
        return (0, order.index(name), name) if name in order else (1, 0, name)

    return sorted(found, key=key)
