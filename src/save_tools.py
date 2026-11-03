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
buffer, 0x40BC90); names here are limited to the same, printable ASCII only (what the
stock fonts draw).

A save folder whose copy of the game has "Render Unicode with In-Game Fonts" or "Use
Unicode Font" (its "Unicode Text.dll" leaves "<Game> Fix Patcher Data\\Unicode Text.ini"
there) takes the DLL's names (docs/UNICODE_SPEC.md section 2, the same in every Fun
Patcher): up to NAME_BOX_BYTES (unicode_data.py) bytes as stored, no character cap, cut at
whole characters (grapheme clusters). The bytes are the shared write rule: a Windows-1252
letter is its one byte, any other letter its UTF-8 bytes (unicode_data.encode_game_text), and
the games' bytes are read by the shared read rule (decode_game_text). The game's own 32-byte
fields keep a name that fits as it is; a longer one as its SHORT FORM, its longest start of
whole characters and "..." (or "2...", "3..." when another name already has that start), so
the stock game still loads the save. The whole name is a record of "<Game> Fix Patcher
Data\\Names <slot>.dat" (a header line, then `short<TAB>room<TAB>whole<TAB>CRC-32` lines;
records are never removed, the first of a short form wins). The v1.0.25 files ("short NUL
full NUL", the short form with "?") are still read. Rename Players adds a record and Copy
Player Slot copies the file with the new name's record; the DLL writes the same format
(native/common/unicode_names.h).

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
import zlib

import unicode_data


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


def _field_at(data: bytes, offset: int, length: int) -> bytes:
    return bytes(data[offset: offset + length]).split(b"\0", 1)[0]


def _name_at(data: bytes, offset: int, length: int) -> str:
    """A name field's text, by the shared read rule (UTF-8 sequences, else Windows-1252 bytes)."""
    return unicode_data.decode_game_text(_field_at(data, offset, length))


def read_slot_fields(game_id: str, folder: Path) -> list[bytes]:
    """The player list's five name fields, as bytes."""
    fmt = FORMATS[game_id]
    data = _read_ldw(_settings_path(fmt, folder))
    end = fmt.names_offset + fmt.slots * fmt.name_stride
    if len(data) < end:
        raise SaveToolError("The settings file is shorter than this game's slot list.")
    return [_field_at(data, fmt.names_offset + i * fmt.name_stride, fmt.name_stride) for i in range(fmt.slots)]


def read_slot_names(game_id: str, folder: Path) -> list[str]:
    return [unicode_data.decode_game_text(raw) for raw in read_slot_fields(game_id, folder)]


EMPTY_SLOT_NAME = "NEW PLAYER"     # what the game lists for a slot nobody plays


def _is_player_name(name: str | None) -> bool:
    return bool(name and name.strip()) and name.strip().casefold() != EMPTY_SLOT_NAME.casefold()


def _field_inside(fmt: SaveFormat, folder: Path, slot: int) -> bytes | None:
    """The player's name field inside "<Game><slot>.ldw"; None when the slot has no such file."""
    path = folder / f"{fmt.title}{slot}.ldw"
    if not path.is_file():
        return None
    try:
        return _field_at(_read_ldw(path), fmt.slot_name_offset, fmt.max_name + 1)
    except (OSError, SaveToolError):
        return b""


def _name_inside(fmt: SaveFormat, folder: Path, slot: int) -> str | None:
    """The player's name inside "<Game><slot>.ldw"; None when the slot has no such file."""
    raw = _field_inside(fmt, folder, slot)
    return None if raw is None else unicode_data.decode_game_text(raw)


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
NAME_BOX_BYTES = unicode_data.NAME_BOX_BYTES   # every name box with Unicode Text.dll (bytes as stored)
NAMES_FILE = "Names {slot}.dat"
NAMES_HEADER = "FTFP Names 1"                    # the shared sidecar format's header line
NAME_MARK = "..."                                # ends every short form ("2...", "3..." when taken)
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
    """The most a name may hold in this save folder: the stock game's 31 characters (one byte
    each), or NAME_BOX_BYTES bytes as stored where the copy has Unicode Text.dll."""
    if folder is not None and unicode_level(game_id, folder):
        return NAME_BOX_BYTES
    return FORMATS[game_id].max_name


def name_allowed(ch: str, unicode: int | bool) -> bool:
    """With ANY_SCRIPT, every code point but the ones no name can hold (docs/UNICODE_SPEC.md section 6):
    NUL, the C0 and C1 controls and DEL, a lone surrogate, the line and paragraph separators U+2028 and
    U+2029, and U+FEFF. It decides by code point, never by Python's unicodedata (which is older than the
    letters the games draw), so a letter newer than this Python is taken; private use, noncharacters and
    unassigned code points are taken too, because the game stores them and draws a box."""
    code, level = ord(ch), int(unicode)
    if 0x20 <= code < 0x7F:
        return True
    if level >= LATIN1 and 0xA0 <= code <= 0xFF:
        return True
    return (level >= ANY_SCRIPT and code >= 0xA0 and not 0xD800 <= code <= 0xDFFF
            and code not in (0x2028, 0x2029, 0xFEFF))


def name_bytes(name: str) -> int:
    """The bytes a name box stores for `name` (the shared write rule): what NAME_BOX_BYTES counts."""
    return unicode_data.game_bytes_len(name)


def name_characters(name: str) -> int:
    """The characters a player sees in `name` (grapheme clusters, the DLL's own rule)."""
    return len(unicode_data.graphemes(name))


def old_short_form(name: str, length: int = 31) -> str:
    """The short form v1.0.25 and before kept in the game's fields: each letter as its Latin-1 byte,
    "?" for a letter Latin-1 has not, cut after `length` letters with no mark. Still read: a
    Names file record whose short form is this one is kept (native/common/unicode_names.h too)."""
    return "".join(c if 0x20 <= ord(c) <= 0xFF and not 0x7F <= ord(c) < 0xA0 else "?" for c in name[:length])


def short_form(name: str, length: int = 31, taken: dict[bytes, str] | None = None) -> bytes:
    """What the game's field of `length` bytes keeps for `name` (docs/UNICODE_SPEC.md section 2, the
    same rule as native/common/unicode_names.h short_for), given the short forms already `taken`
    (field bytes -> the whole name they stand for, in order):

    * a short form already standing for this very name, that fits, is used again;
    * a name that fits (the write rule: a Windows-1252 byte a letter, else UTF-8) and stands for no
      other name is kept as it is;
    * else the longest start of whole characters that fits with the mark, trailing spaces dropped,
      then "...", or "2...", "3..." until it stands for no other name."""
    taken = taken or {}
    for short, whole in taken.items():
        if whole == name and len(short) <= length:
            return short
    whole_bytes = unicode_data.encode_game_text(name)
    if len(whole_bytes) <= length and taken.get(whole_bytes, name) == name:
        return whole_bytes
    clusters = unicode_data.graphemes(name)
    n = 1
    while True:
        tail = NAME_MARK if n == 1 else f"{n}{NAME_MARK}"
        if len(tail) > length:
            raise SaveToolError("No short form is left for this name.")
        k = len(clusters)
        while True:
            short = unicode_data.encode_game_text("".join(clusters[:k]).rstrip(" ") + tail)
            if len(short) <= length or k == 0:
                break
            k -= 1
        if len(short) <= length and short not in taken:
            return short
        n += 1


@dataclass(frozen=True)
class NameRecord:
    """One line of a Names file: the short form (as text), the field's room in bytes, the whole name."""
    short: str
    room: int
    whole: str

    @property
    def field(self) -> bytes:
        """The short form's bytes, as the game's field holds them."""
        return unicode_data.encode_game_text(self.short)


def _text_ok(text: str) -> bool:
    return bool(text) and all(ord(c) >= 0x20 and not 0x7F <= ord(c) < 0xA0 and not 0xD800 <= ord(c) <= 0xDFFF
                              for c in text)


def record_valid(short: str, room: int, whole: str) -> bool:
    """A Names record the readers use (docs/UNICODE_SPEC.md section 2): a short form with its mark
    ("..." at its end, or v1.0.25's own short form of the whole name), that fits its room; a whole
    name of at most NAME_BOX_BYTES bytes as stored; no control character in either."""
    if not 1 <= room < NAME_BOX_BYTES or not _text_ok(short) or not _text_ok(whole):
        return False
    if short == whole or unicode_data.game_bytes_len(short) > room or name_bytes(whole) > NAME_BOX_BYTES:
        return False
    return short.endswith(NAME_MARK) or short == old_short_form(whole, room)


def crc32_hex(text: bytes) -> str:
    return f"{zlib.crc32(text) & 0xFFFFFFFF:08X}"


def record_line(record: NameRecord) -> bytes:
    """`short<TAB>room<TAB>whole<TAB>CRC-32` and LF, in UTF-8; the CRC-32 (8 upper-case hex digits) is of
    everything before the last tab."""
    body = f"{record.short}\t{record.room}\t{record.whole}".encode("utf-8")
    return body + b"\t" + crc32_hex(body).encode("ascii") + b"\n"


def parse_names(data: bytes) -> list[NameRecord]:
    """A Names file's valid records, in file order, the first one of each short form only. A file
    of v1.0.25 and before ("short NUL full NUL") reads as its one record. Anything else (a cut or
    merged record, a wrong CRC, a file that is not one) is left out: the save then shows its short
    forms."""
    out: list[NameRecord] = []
    seen: set[str] = set()
    if not data.startswith(NAMES_HEADER.encode("ascii") + b"\n"):
        parts = data.split(b"\0")
        if len(parts) >= 3 and parts[0] and parts[1] and len(parts[0]) <= 31:
            try:
                record = NameRecord(parts[0].decode("latin-1"), 31, parts[1].decode("utf-8"))
            except UnicodeDecodeError:
                return []
            if record_valid(record.short, record.room, record.whole):
                out.append(record)
        return out
    for raw in data.split(b"\n")[1:]:
        fields = raw.split(b"\t")
        if len(fields) != 4 or crc32_hex(raw[:raw.rfind(b"\t")]) != fields[3].decode("latin-1"):
            continue
        try:
            short, room, whole = (f.decode("utf-8") for f in fields[:3])
        except UnicodeDecodeError:
            continue
        if not room.isdigit() or len(room) > 4 or short in seen or not record_valid(short, int(room), whole):
            continue
        seen.add(short)
        out.append(NameRecord(short, int(room), whole))
    return out


def render_names(data: bytes, new: list[NameRecord]) -> bytes:
    """A Names file with `new` records added after what it holds (records are never removed; a
    v1.0.25 file becomes the shared format with its one record first)."""
    if data.startswith(NAMES_HEADER.encode("ascii") + b"\n"):
        out = data if data.endswith(b"\n") else data + b"\n"
    else:
        out = NAMES_HEADER.encode("ascii") + b"\n" + b"".join(record_line(r) for r in parse_names(data))
    return out + b"".join(record_line(r) for r in new)


def _names_path(fmt: SaveFormat, folder: Path, slot: int) -> Path:
    return _data_folder(fmt, folder) / NAMES_FILE.format(slot=slot)


def read_names(game_id: str, folder: Path, slot: int) -> list[NameRecord]:
    try:
        return parse_names(_names_path(FORMATS[game_id], folder, slot).read_bytes())
    except OSError:
        return []


class NameBook:
    """Every slot's Names file in one save folder: what the readers show and the tools write."""

    def __init__(self, game_id: str, folder: Path) -> None:
        self.game_id, self.folder = game_id, Path(folder)
        self.fmt = FORMATS[game_id]
        self.slots = {slot: read_names(game_id, self.folder, slot) for slot in range(1, self.fmt.slots + 1)}

    def full(self, slot: int, stored: str) -> str:
        """The whole name of `stored` (a field's text) in `slot`: the slot's own records first, then
        any slot's marked one; `stored` itself when it is no short form."""
        for record in self.slots.get(slot, []):
            if record.short == stored:
                return record.whole
        for other in range(1, self.fmt.slots + 1):
            for record in self.slots[other]:
                if record.short == stored and record.short.endswith(NAME_MARK):
                    return record.whole
        return stored

    def taken(self, fields: dict[int, bytes], exclude: int | None = None, replaced: int | None = None
              ) -> dict[bytes, str]:
        """Short form bytes -> the whole name, of every record (slot by slot, in file order; the first
        wins; records are never removed, so a renamed slot's still count) and of the fields but
        `exclude`'s (a field that is no short form stands for itself). `replaced`: a slot whose Names
        file is set aside (Copy Player Slot over it), its records left out too."""
        out: dict[bytes, str] = {}
        for slot in range(1, self.fmt.slots + 1):
            if slot == replaced:
                continue
            for record in self.slots[slot]:
                out.setdefault(record.field, record.whole)
        for slot, field in fields.items():
            if slot not in (exclude, replaced) and field:
                out.setdefault(field, self.full(slot, unicode_data.decode_game_text(field)))
        return out

    def store(self, slot: int, whole: str, fields: dict[int, bytes], exclude: int | None = None,
              replaced: int | None = None) -> tuple[bytes, NameRecord | None]:
        """The field bytes for `whole` in `slot` and the new record for its Names file (None when
        none is needed; `replaced`: the slot's own records do not count, its file is set aside).
        Nothing is written here."""
        short = short_form(whole, self.fmt.max_name, self.taken(fields, exclude, replaced))
        if short == unicode_data.encode_game_text(whole):
            return short, None
        text = unicode_data.decode_game_text(short)
        if slot != replaced and any(r.short == text for r in self.slots[slot]):
            return short, None
        return short, NameRecord(text, self.fmt.max_name, whole)


def full_name(game_id: str, folder: Path, slot: int, listed: str) -> str:
    """The whole name of the player whose short form is `listed` (Names <slot>.dat, then the other
    slots' files), else `listed` itself."""
    return NameBook(game_id, folder).full(slot, listed)


def counter_text(game_id: str, folder: Path | None, name: str, slot: int | None = None) -> tuple[str, bool]:
    """The Rename and Copy tools' counter, and whether the name is over the limit: "N / 1200 bytes"
    (and its characters) where the copy has Unicode Text.dll, saying when the save will keep a
    short form; the stock game's "N / 31 characters" elsewhere."""
    limit = name_limit(game_id, folder)
    if limit != NAME_BOX_BYTES:
        return f"{len(name)} / {limit} characters", len(name) > limit
    size = name_bytes(name)
    text = f"{size:,} / {NAME_BOX_BYTES:,} bytes, {name_characters(name):,} characters"
    if size > NAME_BOX_BYTES:
        return text, True
    if name and size > FORMATS[game_id].max_name:
        try:
            short, _record = NameBook(game_id, folder).store(slot or 0, name, _fields(game_id, folder), slot)
        except (OSError, SaveToolError, KeyError):
            short = short_form(name)
        text += f"; the save keeps the short form \"{unicode_data.decode_game_text(short)}\""
    return text, False


def validate_name(game_id: str, name: str, unicode: int | bool = False) -> str:
    """`unicode`: what the save folder's copy takes (unicode_level; True is LATIN1)."""
    fmt = FORMATS[game_id]
    if not name or name != name.strip():
        raise SaveToolError("A name cannot be empty or start or end with a space.")
    if name.casefold() == EMPTY_SLOT_NAME.casefold():
        raise SaveToolError(f"\"{EMPTY_SLOT_NAME}\" is how the game marks an empty slot; choose another name.")
    if any(not name_allowed(c, unicode) for c in name):
        if int(unicode) >= ANY_SCRIPT:
            raise SaveToolError("Use letters, numbers, punctuation and symbols; no control characters.")
        if unicode:
            raise SaveToolError("Use letters, numbers and punctuation of Western European languages "
                                "(é ñ ü ß Æ ...): the game takes no others yet.")
        raise SaveToolError("Use plain letters, numbers and punctuation (the game's font has no others). "
                            "Accented letters need a copy of the game patched with "
                            "\"Render Unicode with In-Game Fonts\", started once.")
    if unicode:
        if name_bytes(name) > NAME_BOX_BYTES:
            raise SaveToolError(f"A name can be at most {NAME_BOX_BYTES:,} bytes as the game stores it (this one "
                                f"is {name_bytes(name):,}); some characters, such as joined emoji, take many bytes.")
    elif len(name) > fmt.max_name:
        raise SaveToolError(f"A name can be at most {fmt.max_name} characters, as in the game.")
    return name


def _fields(game_id: str, folder: Path) -> dict[int, bytes]:
    """Slot -> the player's field bytes (the player list's, or the save's own where the list says
    "NEW PLAYER")."""
    return {slot: _player_field(game_id, folder, slot, raw)
            for slot, raw in enumerate(read_slot_fields(game_id, folder), start=1)}


def _player_field(game_id: str, folder: Path, slot: int, listed: bytes) -> bytes:
    if _is_player_name(unicode_data.decode_game_text(listed)):
        return listed
    inside = _field_inside(FORMATS[game_id], folder, slot)
    return inside if inside and _is_player_name(unicode_data.decode_game_text(inside)) else listed


def _write_all(writes: list[tuple[Path, bytes]]) -> None:
    """Each file through "<file>.tmp" moved over it; on a failure every file written is put back."""
    done: list[tuple[Path, bytes | None]] = []
    try:
        for path, data in writes:
            old = path.read_bytes() if path.is_file() else None
            temp = path.with_name(path.name + ".tmp")
            temp.write_bytes(bytes(data))
            temp.replace(path)
            done.append((path, old))
    except BaseException:
        for path, _data in writes:
            path.with_name(path.name + ".tmp").unlink(missing_ok=True)
        for path, old in reversed(done):
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise


def rename_slot(game_id: str, folder: Path, slot: int, new_name: str,
                processes=None) -> dict:
    """Rename player slot `slot` (1-5): the settings file's slot list and the
    name inside that slot's own save files, with the game closed. Backs the
    folder up first, as "Backups\\Backup <date> (before rename)" inside it. Where the
    copy has Unicode Text.dll a name too long for the game's field is stored as its short form
    and its record is added to "Names <slot>.dat" (written first; a failed rename puts it back)."""
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
    fields = _fields(game_id, folder)
    old_field = fields[slot]
    record = None
    if level:
        new_field, record = NameBook(game_id, folder).store(slot, new_name, fields, exclude=slot)
    else:
        new_field = new_name.encode("ascii")
    backup = save_backup.copy_save_folder(folder, suffix=save_backup.BEFORE_RENAME).backup_folder

    writes: list[tuple[Path, bytes]] = []
    changed, skipped = [], []
    if record is not None:
        # the whole name beside the save, for the copy's Unicode Text.dll: written first
        names = _names_path(fmt, folder, slot)
        names.parent.mkdir(parents=True, exist_ok=True)
        old = names.read_bytes() if names.is_file() else b""
        writes.append((names, render_names(old, [record])))
        changed.append(names.name)
    offset = fmt.names_offset + (slot - 1) * fmt.name_stride
    settings[offset: offset + fmt.name_stride] = new_field.ljust(fmt.name_stride, b"\0")
    changed.append(settings_path.name)
    writes.append((settings_path, bytes(settings)))
    for extra in fmt.slot_file_offsets:
        path = folder / f"{fmt.title}{slot + extra}.ldw"
        if not path.is_file():
            continue
        data = _read_ldw(path)
        at = fmt.slot_name_offset
        if old_field and bytes(data[at: at + len(old_field) + 1]) == old_field + b"\0":
            field = fmt.max_name + 1
            data[at: at + field] = new_field.ljust(field, b"\0")
            writes.append((path, bytes(data)))
            changed.append(path.name)
        else:
            skipped.append(path.name)
    _write_all(writes)
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
    backup) are replaced or removed, so nothing of an old player mixes in. The source's
    "Names <slot>.dat" is copied as the target's, with the new name's record added."""
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
    fields = _fields(game_id, folder)
    old_field = fields[source]
    record = None
    if level:
        new_field, record = NameBook(game_id, folder).store(source, new_name, fields, exclude=target,
                                                            replaced=target)
    else:
        new_field = new_name.encode("ascii")
    copies: list[tuple[Path, bytes]] = []
    for extra in fmt.slot_file_offsets:
        path = folder / f"{fmt.title}{source + extra}.ldw"
        if not path.is_file():
            continue
        data = _read_ldw(path)
        at = fmt.slot_name_offset
        if old_field and bytes(data[at: at + len(old_field) + 1]) == old_field + b"\0":
            field = fmt.max_name + 1
            data[at: at + field] = new_field.ljust(field, b"\0")
        copies.append((folder / f"{fmt.title}{target + extra}.ldw", bytes(data)))
    target_names = _names_path(fmt, folder, target)
    source_names = _names_path(fmt, folder, source)
    for path, what, extra, kind in _slot_side_files(fmt, folder, source):
        copy_to = path.with_name(f"{what} {target + extra}{kind}.dat")
        if copy_to != target_names:            # the Names file is written below
            copies.append((copy_to, path.read_bytes()))
    if source_names.is_file() or record is not None:
        # the source's records (the shared format), plus the new name's: the copy's own Names file
        old = source_names.read_bytes() if source_names.is_file() else b""
        copies.append((target_names, render_names(old, [record] if record is not None else [])))
    backup = save_backup.copy_save_folder(folder, suffix=save_backup.BEFORE_COPY).backup_folder

    # The target slot's own files (a replaced player's, or an empty slot's leftovers) are set
    # aside, not deleted: moved into "Backups\Replaced by copy <date> - Player <n> - <old name>",
    # keeping their paths (as every LDW patcher does), and moved back if the copy fails.
    old_files = [folder / f"{fmt.title}{target + extra}.ldw" for extra in fmt.slot_file_offsets]
    old_files = [path for path in old_files if path.is_file()]
    old_files += [path for path, *_rest in _slot_side_files(fmt, folder, target)]
    gone = full_name(game_id, folder, target, player_name(game_id, folder, target, names[target - 1]))
    gone = gone.strip() or EMPTY_SLOT_NAME
    gone = re.sub(r'[\\/:*?"<>|]', "_", gone).rstrip(". ")[:80].rstrip(". ")
    aside = folder / save_backup.BACKUPS_FOLDER / (
        f"Replaced by copy {datetime.now():%Y-%m-%d %H-%M-%S} - Player {target} - {gone}")
    base, count = aside, 1
    while aside.exists():
        count += 1
        aside = base.with_name(f"{base.name} ({count})")
    offset = fmt.names_offset + (target - 1) * fmt.name_stride
    settings[offset: offset + fmt.name_stride] = new_field.ljust(fmt.name_stride, b"\0")
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
            path.parent.mkdir(parents=True, exist_ok=True)
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
