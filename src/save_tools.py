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
name box in the stock game takes up to 31 characters (Fish Tycoon: a 0x20-byte
buffer, 0x40BC90); names here are limited to the same, printable ASCII only.

A save folder whose copy of the game has "Render Unicode with In-Game Fonts" (its
"Unicode Text.dll" leaves "<Game> Fix Patcher Data\\Unicode Text.ini" there) takes
the DLL's names: up to NAME_LIMIT (300) letters, the one limit of every name box
in both games (native/common/unicode_names.h), in Latin-1 (é ñ ü ß ...). The
game's own fields keep the SHORT FORM: each letter as its Latin-1 byte, "?" for a
letter Latin-1 has not, cut after 31 letters, so the stock game still loads the
save; the full name is in "<Game> Fix Patcher Data\\Names <slot>.dat" (the short
form, NUL, the full name in UTF-8, NUL), used only while the player list still
holds that short form. Rename Players writes it and Copy Player Slot copies it
with the new name.

Nothing is written without a backup first: a rename copies the whole save
folder into its Backups folder (save_backup.py) before it changes anything. A
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


def _is_player_name(name: str | None) -> bool:
    return bool(name and name.strip()) and name.strip().casefold() != EMPTY_SLOT_NAME.casefold()


def _name_inside(fmt: SaveFormat, folder: Path, slot: int) -> str | None:
    """The player's name inside "<Game><slot>.ldw"; None when the slot has no such file."""
    path = folder / f"{fmt.title}{slot}.ldw"
    if not path.is_file():
        return None
    try:
        return _name_at(_read_ldw(path), fmt.slot_name_offset, fmt.max_name + 1)
    except (OSError, SaveToolError):
        return ""


def player_name(game_id: str, folder: Path, slot: int, listed: str) -> str:
    """The name of the player in `slot`: the player list's, or, where the list says "NEW PLAYER"
    but the slot's saved game holds a player, the name inside that save."""
    if _is_player_name(listed):
        return listed
    inside = _name_inside(FORMATS[game_id], folder, slot)
    return inside if _is_player_name(inside) else listed


def slot_is_active(game_id: str, folder: Path, slot: int, name: str) -> bool:
    """A slot someone plays. The game's player slots are the files "<Game>1.ldw" to
    "<Game>5.ldw": a slot is in use when its file is on disk with a player's name, in the
    player list or inside the save."""
    fmt = FORMATS[game_id]
    if not (folder / f"{fmt.title}{slot}.ldw").is_file():
        return False
    return _is_player_name(player_name(game_id, folder, slot, name))


def slot_is_empty(game_id: str, folder: Path, slot: int) -> bool:
    """A slot that can be copied to: one not in use, above all one with no "<Game><slot>.ldw",
    where the game starts a new player whatever the player list still says."""
    return not slot_is_active(game_id, folder, slot, read_slot_names(game_id, folder)[slot - 1])


def players(game_id: str, folder: Path) -> list[tuple[int, str]]:
    """(slot, name) of each slot in use, as player_name names it."""
    return [(slot, full_name(game_id, folder, slot, player_name(game_id, folder, slot, name)))
            for slot, name in enumerate(read_slot_names(game_id, folder), start=1)
            if slot_is_active(game_id, folder, slot, name)]


UNICODE_MARKER = "Unicode Text.ini"
NAME_LIMIT = 300            # every name box with Unicode Text.dll (native/common/unicode_names.h)
NAMES_FILE = "Names {slot}.dat"
LATIN1, ANY_SCRIPT = 1, 2   # unicode_level


def _data_folder(fmt: SaveFormat, folder: Path) -> Path:
    return folder / f"{fmt.title} Fix Patcher Data"


def unicode_level(game_id: str, folder: Path) -> int:
    """What this save folder's copy of the game types and draws in names: 0 plain ASCII (the stock
    game), LATIN1, or ANY_SCRIPT once its "Unicode Text.dll" draws UTF-8. The DLL (Render Unicode
    with In-Game Fonts, or Use Unicode Font) leaves its marker in "<Game> Fix Patcher Data"."""
    marker = _data_folder(FORMATS[game_id], folder) / UNICODE_MARKER
    if not marker.is_file():
        return 0
    try:
        text = marker.read_text(encoding="latin-1")
    except OSError:
        return LATIN1
    return ANY_SCRIPT if "any script" in text else LATIN1


def unicode_names(game_id: str, folder: Path) -> int:
    """Nonzero (its unicode_level) when this save folder's copy takes more than plain ASCII names."""
    return unicode_level(game_id, folder)


def name_limit(game_id: str, folder: Path | None = None) -> int:
    """The most letters a name may have in this save folder: the stock game's 31, or NAME_LIMIT
    where the copy has Unicode Text.dll."""
    if folder is not None and unicode_level(game_id, folder):
        return NAME_LIMIT
    return FORMATS[game_id].max_name


def name_allowed(ch: str, unicode: int | bool) -> bool:
    import unicodedata
    code, level = ord(ch), int(unicode)
    if 0x20 <= code < 0x7F:
        return True
    if level >= LATIN1 and 0xA0 <= code <= 0xFF:
        return True
    return level >= ANY_SCRIPT and code >= 0xA0 and unicodedata.category(ch) not in ("Cc", "Cs", "Co", "Cn")


def short_form(name: str, length: int = 31) -> bytes:
    """The name as the game's own field keeps it: each letter its Latin-1 byte, "?" for a letter
    Latin-1 has not, at most `length` letters."""
    return bytes(ord(c) if 0x20 <= ord(c) <= 0xFF and not 0x7F <= ord(c) < 0xA0 else 0x3F
                 for c in name[:length])


def _names_path(fmt: SaveFormat, folder: Path, slot: int) -> Path:
    return _data_folder(fmt, folder) / NAMES_FILE.format(slot=slot)


def _names_bytes(name: str) -> bytes:
    return short_form(name) + b"\0" + name.encode("utf-8") + b"\0"


def full_name(game_id: str, folder: Path, slot: int, listed: str) -> str:
    """The full name of the player whose short form is `listed`: "Names <slot>.dat" when its short
    form is that one, else `listed` itself."""
    path = _names_path(FORMATS[game_id], folder, slot)
    try:
        data = path.read_bytes()
    except OSError:
        return listed
    parts = data.split(b"\0")
    if len(parts) < 2 or parts[0] != listed.encode("latin-1", "replace") or not parts[1]:
        return listed
    try:
        return parts[1].decode("utf-8")
    except UnicodeDecodeError:
        return listed


def validate_name(game_id: str, name: str, unicode: int | bool = False) -> str:
    """`unicode`: what the save folder's copy takes (unicode_level; True is LATIN1)."""
    fmt = FORMATS[game_id]
    limit = NAME_LIMIT if unicode else fmt.max_name
    if not name or name != name.strip():
        raise SaveToolError("A name cannot be empty or start or end with a space.")
    if name.casefold() == EMPTY_SLOT_NAME.casefold():
        raise SaveToolError(f"\"{EMPTY_SLOT_NAME}\" is how the game marks an empty slot; choose another name.")
    if len(name) > limit:
        raise SaveToolError(f"A name can be at most {limit} characters, as in the game.")
    if any(not name_allowed(c, unicode) for c in name):
        if int(unicode) >= ANY_SCRIPT:
            raise SaveToolError("Use letters, numbers, punctuation and symbols; no control characters.")
        if unicode:
            raise SaveToolError("Use letters, numbers and punctuation of Western European languages "
                                "(Ã© Ã± Ã¼ ÃŸ Ã† ...): the game takes no others yet.")
        raise SaveToolError("Use plain letters, numbers and punctuation (the game's font has no others). "
                            "Accented letters need a copy of the game patched with "
                            "\"Render Unicode with In-Game Fonts\", started once.")
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
    level = unicode_level(game_id, folder)
    new_name = validate_name(game_id, new_name, level)
    settings_path = _settings_path(fmt, folder)
    settings = _read_ldw(settings_path)
    old_name = player_name(game_id, folder, slot, read_slot_names(game_id, folder)[slot - 1])
    old_full = full_name(game_id, folder, slot, old_name)
    if not slot_is_active(game_id, folder, slot, old_name):
        raise SaveToolError(f"Slot {slot} has no saved game to rename; only slots in use can be renamed.")
    if save_backup.game_running(folder, processes):
        raise SaveToolError(f"{save_backup.game_exe_name(folder)} is running. Quit the game first; nothing was changed.")
    backup = save_backup.copy_save_folder(folder, suffix=save_backup.BEFORE_RENAME).backup_folder

    offset = fmt.names_offset + (slot - 1) * fmt.name_stride
    settings[offset: offset + fmt.name_stride] = short_form(new_name).ljust(fmt.name_stride, b"\0")
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
            data[at: at + field] = short_form(new_name).ljust(field, b"\0")
            writes.append((path, data))
            changed.append(path.name)
        else:
            skipped.append(path.name)
    if level:
        # the full name beside the save, for the copy's Unicode Text.dll
        names = _names_path(fmt, folder, slot)
        names.parent.mkdir(parents=True, exist_ok=True)
        writes.append((names, bytearray(_names_bytes(new_name))))
        changed.append(names.name)
    for path, data in writes:
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(bytes(data))
        temp.replace(path)
    return {"old_name": old_full, "new_name": new_name, "changed": changed,
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
              processes=None, overwrite: bool = False) -> dict:
    """Copy player slot `source` to slot `target` (1-5) under `new_name`: the slot's save
    files, the patcher's own files for it, and the name in the player list and inside the
    copied save, with the game closed. `target` must be empty unless `overwrite` is set,
    when the player there is replaced. Backs the folder up first, as
    "Backups\\Backup <date> (before copy)" inside it. The target slot's own files (in the
    backup) are replaced or removed, so nothing of an old player mixes in."""
    import save_backup
    fmt = FORMATS[game_id]
    for slot in (source, target):
        if not 1 <= slot <= fmt.slots:
            raise SaveToolError(f"Slot must be 1-{fmt.slots}.")
    if source == target:
        raise SaveToolError("Choose a different slot to copy to.")
    level = unicode_level(game_id, folder)
    new_name = validate_name(game_id, new_name, level)
    settings_path = _settings_path(fmt, folder)
    settings = _read_ldw(settings_path)
    names = read_slot_names(game_id, folder)
    old_name = player_name(game_id, folder, source, names[source - 1])
    old_full = full_name(game_id, folder, source, old_name)
    if not slot_is_active(game_id, folder, source, old_name):
        raise SaveToolError(f"Slot {source} has no saved game to copy.")
    replaced = None
    if slot_is_active(game_id, folder, target, names[target - 1]):
        if not overwrite:
            raise SaveToolError(f"Slot {target} holds a saved game; copy only to an empty slot.")
        replaced = player_name(game_id, folder, target, names[target - 1])
        replaced = full_name(game_id, folder, target, replaced)
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
            data[at: at + field] = short_form(new_name).ljust(field, b"\0")
        copies.append((folder / f"{fmt.title}{target + extra}.ldw", bytes(data)))
    target_names = _names_path(fmt, folder, target)
    for path, what, extra, kind in _slot_side_files(fmt, folder, source):
        copy_to = path.with_name(f"{what} {target + extra}{kind}.dat")
        if copy_to != target_names:            # the full name is written anew below
            copies.append((copy_to, path.read_bytes()))
    if level:
        copies.append((target_names, _names_bytes(new_name)))
    backup = save_backup.copy_save_folder(folder, suffix=save_backup.BEFORE_COPY).backup_folder

    # The target slot's own files (a replaced player's, or an empty slot's leftovers) are set
    # aside, not deleted: moved into "Backups\Replaced by copy <date> - Player <n> - <old name>",
    # keeping their paths (as every LDW patcher does), and moved back if the copy fails.
    old_files = [folder / f"{fmt.title}{target + extra}.ldw" for extra in fmt.slot_file_offsets]
    old_files = [path for path in old_files if path.is_file()]
    old_files += [path for path, *_rest in _slot_side_files(fmt, folder, target)]
    gone = full_name(game_id, folder, target, player_name(game_id, folder, target, names[target - 1]))
    gone = gone.strip() or EMPTY_SLOT_NAME
    gone = re.sub(r'[\\/:*?"<>|]', "_", gone).rstrip(". ")
    aside = folder / save_backup.BACKUPS_FOLDER / (
        f"Replaced by copy {datetime.now():%Y-%m-%d %H-%M-%S} - Player {target} - {gone}")
    base, count = aside, 1
    while aside.exists():
        count += 1
        aside = base.with_name(f"{base.name} ({count})")
    offset = fmt.names_offset + (target - 1) * fmt.name_stride
    settings[offset: offset + fmt.name_stride] = short_form(new_name).ljust(fmt.name_stride, b"\0")
    settings[fmt.started_offset + target - 1] = settings[fmt.started_offset + source - 1] or 1
    copies.append((settings_path, bytes(settings)))
    moved: list[tuple[Path, Path]] = []
    written: list[Path] = []
    try:
        for path in old_files:
            dest = aside / path.relative_to(folder)
            dest.parent.mkdir(parents=True, exist_ok=True)
            path.replace(dest)
            moved.append((path, dest))
        for path, data in copies:
            temp = path.with_name(path.name + ".tmp")
            temp.write_bytes(data)
            if path != settings_path:
                written.append(path)
            temp.replace(path)
    except BaseException:
        for path, _data in copies:
            path.with_name(path.name + ".tmp").unlink(missing_ok=True)
        for path in written:
            path.unlink(missing_ok=True)
        for path, dest in reversed(moved):
            dest.replace(path)
        raise
    return {"source": source, "target": target, "old_name": old_full, "new_name": new_name,
            "copied": [path.name for path, _data in copies[:-1]],
            "removed": [path.name for path, _dest in moved],
            "set_aside": str(aside) if moved else None,
            "replaced": replaced, "backup": str(backup)}
