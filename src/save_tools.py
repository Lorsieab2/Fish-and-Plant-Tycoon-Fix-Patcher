"""Save tools for Fish Tycoon and Plant Tycoon: the save formats and renaming slots
(backup and restore are in save_backup.py).

Both games keep their saves in Documents\\LDW\\<exe name>\\ (see README,
"Where your saves go"): file 0 holds the settings, including the five player
slot names, and each slot's game is in numbered files beside it.

    file           Fish Tycoon                  Plant Tycoon
    settings (0)   names at 0x20, 42 bytes each names at 0x22, 33 bytes each
    slot files     n and 20+n                   n, 20+n and 40+n
    name in a slot file at 0x1E3B5              at 0x18

Every file starts with the game's 24-byte "ldwg" header, and the games check
only that magic and the data size, so a name can be changed in place. The
name box in the game takes up to 31 characters (Fish Tycoon: a 0x20-byte
buffer, 0x40BC90); names here are limited to the same, printable ASCII only.

Nothing is written without a backup first: a rename copies the whole save
folder into its Backups folder (save_backup.py) before it changes anything. A
rename changes a slot file's name only where that file holds exactly the
slot's old name, so a file whose layout is not the one described here is left
alone.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import re


class SaveToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class SaveFormat:
    game_id: str
    title: str                      # also the save files' prefix
    names_offset: int               # first slot name in the settings file
    name_stride: int
    slot_name_offset: int           # the name inside a slot's own files
    slot_file_offsets: tuple[int, ...]   # slot n's files are n + each of these
    slots: int = 5
    max_name: int = 31

    @property
    def started_offset(self) -> int:
        """One byte a slot right after the names: 1 = the slot has a game (0: the game starts a new
        one, with its story, whatever files are on disk). Fish 0xF2, Plant 0xC7."""
        return self.names_offset + self.slots * self.name_stride


FORMATS = {
    "fish": SaveFormat("fish", "Fish Tycoon", 0x20, 42, 0x1E3B5, (0, 20, 40)),
    "plant": SaveFormat("plant", "Plant Tycoon", 0x22, 33, 0x18, (0, 20, 40)),
}

HEADER = b"ldwg"
OLD_BACKUPS_FOLDER = "Fish and Plant Tycoon Fix Patcher Save Backups"   # v1.0.17 zip backups


def documents_folder() -> Path:
    """The Documents folder the games use (often OneDrive\\Documents)."""
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(260)
        # SHGetFolderPathW(NULL, CSIDL_PERSONAL, NULL, SHGFP_TYPE_CURRENT, buffer)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, buffer) == 0 and buffer.value:
            return Path(buffer.value)
    return Path.home() / "Documents"


def ldw_folder(documents: Path | None = None) -> Path:
    return (documents or documents_folder()) / "LDW"


def default_backups_folder(documents: Path | None = None) -> Path:
    return ldw_folder(documents) / OLD_BACKUPS_FOLDER


def save_folders(game_id: str, documents: Path | None = None) -> list[Path]:
    """Every save folder this game has under Documents\\LDW: the original game's
    and each copy's (a copy saves under its own executable name)."""
    fmt = FORMATS[game_id]
    root = ldw_folder(documents)
    if not root.is_dir():
        return []
    found = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if child.is_dir() and child.name.casefold().startswith(fmt.title.casefold()) \
                and (child / f"{fmt.title}0.ldw").is_file():
            found.append(child)
    return found


MODDED_SUFFIXES = (" - Modded", " - Modded Upgrades")


def modded_save_folders(game_id: str, documents: Path | None = None) -> list[Path]:
    """The save folders of this patcher's copies only: "<Game> - Modded" and
    "<Game> - Modded Upgrades" (the game saves under its executable's name)."""
    fmt = FORMATS[game_id]
    names = {(fmt.title + suffix).casefold() for suffix in MODDED_SUFFIXES}
    return [path for path in save_folders(game_id, documents) if path.name.casefold() in names]


def is_save_folder(game_id: str, folder: Path) -> bool:
    return (folder / f"{FORMATS[game_id].title}0.ldw").is_file()


def _settings_path(fmt: SaveFormat, folder: Path) -> Path:
    return folder / f"{fmt.title}0.ldw"


def _read_ldw(path: Path) -> bytearray:
    data = bytearray(path.read_bytes())
    if len(data) < 24 or data[:4] != HEADER:
        raise SaveToolError(f"Not a game save file: {path}")
    return data


def _name_at(data: bytes, offset: int, length: int) -> str:
    raw = bytes(data[offset: offset + length])
    return raw.split(b"\0", 1)[0].decode("latin-1")


def read_slot_names(game_id: str, folder: Path) -> list[str]:
    fmt = FORMATS[game_id]
    data = _read_ldw(_settings_path(fmt, folder))
    end = fmt.names_offset + fmt.slots * fmt.name_stride
    if len(data) < end:
        raise SaveToolError("The settings file is shorter than this game's slot list.")
    return [_name_at(data, fmt.names_offset + i * fmt.name_stride, fmt.name_stride) for i in range(fmt.slots)]


EMPTY_SLOT_NAME = "NEW PLAYER"     # what the game lists for a slot nobody plays


def slot_is_active(game_id: str, folder: Path, slot: int, name: str) -> bool:
    """A slot someone plays: a real name in the player list and its saved game on disk."""
    fmt = FORMATS[game_id]
    if not name or name.strip().casefold() == EMPTY_SLOT_NAME.casefold():
        return False
    return (folder / f"{fmt.title}{slot}.ldw").is_file()


def slot_is_empty(game_id: str, folder: Path, slot: int) -> bool:
    """A slot that can be copied to: "NEW PLAYER" (or blank) in the player list, not marked as a
    started game, and no saved game of its own with a player's name in it (the game lists such a
    slot under that name even when the list says "NEW PLAYER")."""
    fmt = FORMATS[game_id]
    settings = _read_ldw(_settings_path(fmt, folder))
    name = read_slot_names(game_id, folder)[slot - 1]
    if name.strip() and name.strip().casefold() != EMPTY_SLOT_NAME.casefold():
        return False
    if len(settings) > fmt.started_offset + slot - 1 and settings[fmt.started_offset + slot - 1]:
        return False
    path = folder / f"{fmt.title}{slot}.ldw"
    if path.is_file():
        try:
            inside = _name_at(_read_ldw(path), fmt.slot_name_offset, fmt.max_name + 1).strip()
        except SaveToolError:
            return True
        if inside and inside.casefold() != EMPTY_SLOT_NAME.casefold():
            return False
    return True


def validate_name(game_id: str, name: str) -> str:
    fmt = FORMATS[game_id]
    if not name or name != name.strip():
        raise SaveToolError("A name cannot be empty or start or end with a space.")
    if name.casefold() == EMPTY_SLOT_NAME.casefold():
        raise SaveToolError(f"\"{EMPTY_SLOT_NAME}\" is how the game marks an empty slot; choose another name.")
    if len(name) > fmt.max_name:
        raise SaveToolError(f"A name can be at most {fmt.max_name} characters, as in the game.")
    if any(not (0x20 <= ord(c) < 0x7F) for c in name):
        raise SaveToolError("Use plain letters, numbers and punctuation (the game's font has no others).")
    return name


def rename_slot(game_id: str, folder: Path, slot: int, new_name: str,
                processes=None) -> dict:
    """Rename player slot `slot` (1-5): the settings file's slot list and the
    name inside that slot's own save files, with the game closed. Backs the
    folder up first, as "Backups\\Backup <date> (before rename)" inside it."""
    import save_backup
    fmt = FORMATS[game_id]
    if not 1 <= slot <= fmt.slots:
        raise SaveToolError(f"Slot must be 1-{fmt.slots}.")
    new_name = validate_name(game_id, new_name)
    settings_path = _settings_path(fmt, folder)
    settings = _read_ldw(settings_path)
    old_name = read_slot_names(game_id, folder)[slot - 1]
    if not slot_is_active(game_id, folder, slot, old_name):
        raise SaveToolError(f"Slot {slot} has no saved game to rename; only slots in use can be renamed.")
    if save_backup.game_running(folder, processes):
        raise SaveToolError(f"{save_backup.game_exe_name(folder)} is running. Quit the game first; nothing was changed.")
    backup = save_backup.copy_save_folder(folder, suffix=save_backup.BEFORE_RENAME).backup_folder

    offset = fmt.names_offset + (slot - 1) * fmt.name_stride
    settings[offset: offset + fmt.name_stride] = new_name.encode("ascii").ljust(fmt.name_stride, b"\0")
    changed = [settings_path.name]
    writes = [(settings_path, settings)]
    skipped = []
    old_field = old_name.encode("latin-1") + b"\0"
    for extra in fmt.slot_file_offsets:
        path = folder / f"{fmt.title}{slot + extra}.ldw"
        if not path.is_file():
            continue
        data = _read_ldw(path)
        at = fmt.slot_name_offset
        if old_name and bytes(data[at: at + len(old_field)]) == old_field:
            field = fmt.max_name + 1
            data[at: at + field] = new_name.encode("ascii").ljust(field, b"\0")
            writes.append((path, data))
            changed.append(path.name)
        else:
            skipped.append(path.name)
    for path, data in writes:
        temp = path.with_suffix(".ldw.tmp")
        temp.write_bytes(bytes(data))
        temp.replace(path)
    return {"old_name": old_name, "new_name": new_name, "changed": changed,
            "skipped": skipped, "backup": str(backup)}


# The patcher's own per-slot files, "<Game> Fix Patcher Data\<what> <n>.dat" and the
# ".previous" copy its DLLs keep; anything else there (".tmp", set-aside files) is not copied.
_SIDE_FILE = re.compile(r"^(?P<what>.+) (?P<n>\d+)(?P<kind>\.previous)?\.dat$", re.I)


def _slot_side_files(fmt: SaveFormat, folder: Path, slot: int) -> list[tuple[Path, str, int, str]]:
    """(path, what, extra, kind) of each patcher data file of `slot`."""
    data = folder / f"{fmt.title} Fix Patcher Data"
    found = []
    if data.is_dir():
        for path in sorted(data.iterdir()):
            match = _SIDE_FILE.match(path.name)
            if not match or not path.is_file():
                continue
            number = int(match.group("n"))
            for extra in fmt.slot_file_offsets:
                if number - extra == slot:
                    found.append((path, match.group("what"), extra, match.group("kind") or ""))
                    break
    return found


def copy_slot(game_id: str, folder: Path, source: int, target: int, new_name: str,
              processes=None) -> dict:
    """Copy player slot `source` to the empty slot `target` (1-5) under `new_name`: the
    slot's save files, the patcher's own files for it, and the name in the player list
    and inside the copied save, with the game closed. Backs the folder up first, as
    "Backups\\Backup <date> (before copy)" inside it. Leftover files of the empty
    target slot (in the backup) are replaced or removed, so nothing of an old player
    mixes in."""
    import save_backup
    fmt = FORMATS[game_id]
    for slot in (source, target):
        if not 1 <= slot <= fmt.slots:
            raise SaveToolError(f"Slot must be 1-{fmt.slots}.")
    if source == target:
        raise SaveToolError("Choose a different slot to copy to.")
    new_name = validate_name(game_id, new_name)
    settings_path = _settings_path(fmt, folder)
    settings = _read_ldw(settings_path)
    names = read_slot_names(game_id, folder)
    old_name = names[source - 1]
    if not slot_is_active(game_id, folder, source, old_name):
        raise SaveToolError(f"Slot {source} has no saved game to copy.")
    if not slot_is_empty(game_id, folder, target):
        raise SaveToolError(f"Slot {target} is in use; copy only to an empty slot (\"{EMPTY_SLOT_NAME}\").")
    if save_backup.game_running(folder, processes):
        raise SaveToolError(f"{save_backup.game_exe_name(folder)} is running. Quit the game first; nothing was changed.")
    copies: list[tuple[Path, bytes]] = []
    old_field = old_name.encode("latin-1") + b"\0"
    for extra in fmt.slot_file_offsets:
        path = folder / f"{fmt.title}{source + extra}.ldw"
        if not path.is_file():
            continue
        data = _read_ldw(path)
        at = fmt.slot_name_offset
        if bytes(data[at: at + len(old_field)]) == old_field:
            field = fmt.max_name + 1
            data[at: at + field] = new_name.encode("ascii").ljust(field, b"\0")
        copies.append((folder / f"{fmt.title}{target + extra}.ldw", bytes(data)))
    for path, what, extra, kind in _slot_side_files(fmt, folder, source):
        copies.append((path.with_name(f"{what} {target + extra}{kind}.dat"), path.read_bytes()))
    backup = save_backup.copy_save_folder(folder, suffix=save_backup.BEFORE_COPY).backup_folder

    written = {path for path, _data in copies}
    stale = [folder / f"{fmt.title}{target + extra}.ldw" for extra in fmt.slot_file_offsets]
    stale += [path for path, *_rest in _slot_side_files(fmt, folder, target)]
    removed = []
    for path in stale:
        if path not in written and path.is_file():
            path.unlink()
            removed.append(path.name)
    offset = fmt.names_offset + (target - 1) * fmt.name_stride
    settings[offset: offset + fmt.name_stride] = new_name.encode("ascii").ljust(fmt.name_stride, b"\0")
    settings[fmt.started_offset + target - 1] = settings[fmt.started_offset + source - 1] or 1
    copies.append((settings_path, bytes(settings)))
    for path, data in copies:
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(data)
        temp.replace(path)
    return {"source": source, "target": target, "old_name": old_name, "new_name": new_name,
            "copied": [path.name for path, _data in copies[:-1]], "removed": removed,
            "backup": str(backup)}
