"""Save tools for Fish Tycoon and Plant Tycoon: back up, restore, rename slots.

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

Nothing is written without a backup first: every restore and rename zips the
whole save folder into the backups folder before it changes anything. A
rename changes a slot file's name only where that file holds exactly the
slot's old name, so a file whose layout is not the one described here is left
alone.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile
import zipfile


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


FORMATS = {
    "fish": SaveFormat("fish", "Fish Tycoon", 0x20, 42, 0x1E3B5, (0, 20)),
    "plant": SaveFormat("plant", "Plant Tycoon", 0x22, 33, 0x18, (0, 20, 40)),
}

HEADER = b"ldwg"
BACKUPS_FOLDER = "Fish and Plant Tycoon Fix Patcher Save Backups"


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
    return ldw_folder(documents) / BACKUPS_FOLDER


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


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H%M%S")


def back_up(folder: Path, backups: Path | None = None, reason: str = "") -> Path:
    """Zip the whole save folder (subfolders included) into the backups folder."""
    if not folder.is_dir():
        raise SaveToolError(f"Save folder not found: {folder}")
    backups = backups or default_backups_folder(folder.parent.parent)
    backups.mkdir(parents=True, exist_ok=True)
    suffix = f" ({reason})" if reason else ""
    target = backups / f"{folder.name} {_stamp()}{suffix}.zip"
    n = 2
    while target.exists():
        target = backups / f"{folder.name} {_stamp()}{suffix} {n}.zip"
        n += 1
    temp = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(folder).as_posix())
    with zipfile.ZipFile(temp) as archive:
        if archive.testzip() is not None:
            raise SaveToolError("The backup failed its own check; nothing was changed.")
    temp.replace(target)
    return target


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = []
    for info in archive.infolist():
        name = Path(info.filename)
        if name.is_absolute() or ".." in name.parts or info.filename.startswith(("/", "\\")):
            raise SaveToolError(f"The backup holds an unsafe path: {info.filename}")
        members.append(info)
    return members


def restore(backup: Path, folder: Path, backups: Path | None = None) -> Path:
    """Make the save folder exactly the backup's contents. The folder as it was
    is backed up first; returns that backup."""
    with zipfile.ZipFile(backup) as archive:
        if archive.testzip() is not None:
            raise SaveToolError("The backup is damaged; nothing was changed.")
        members = _safe_members(archive)
        if not any(Path(m.filename).name.endswith("0.ldw") for m in members):
            raise SaveToolError("This zip does not look like a save backup (no settings file).")
        before = back_up(folder, backups, "before restore") if folder.is_dir() else None
        staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=folder.parent))
        try:
            archive.extractall(staging, members)
            if folder.exists():
                shutil.rmtree(folder)
            staging.replace(folder)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
    return before if before else backup


def rename_slot(game_id: str, folder: Path, slot: int, new_name: str,
                backups: Path | None = None) -> dict:
    """Rename player slot `slot` (1-5): the settings file's slot list and the
    name inside that slot's own save files. Backs the folder up first."""
    fmt = FORMATS[game_id]
    if not 1 <= slot <= fmt.slots:
        raise SaveToolError(f"Slot must be 1-{fmt.slots}.")
    new_name = validate_name(game_id, new_name)
    settings_path = _settings_path(fmt, folder)
    settings = _read_ldw(settings_path)
    old_name = read_slot_names(game_id, folder)[slot - 1]
    if not slot_is_active(game_id, folder, slot, old_name):
        raise SaveToolError(f"Slot {slot} has no saved game to rename; only slots in use can be renamed.")
    backup = back_up(folder, backups, f"before renaming slot {slot}")

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
