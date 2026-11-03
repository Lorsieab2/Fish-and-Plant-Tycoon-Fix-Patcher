"""Sentinel translations for tests/test_translation_sentinels.py.

Every line of a game's translation (src/translation_strings.py entries_for: the game's own lines,
the lines an executable patch changes, every patcher DLL text, every counted text) is translated
to a unique sentinel, "§K012§" and the line's placeholders and choices, padded with "_" to the
English's length but never past the line's room, with the English's leading and trailing spaces
and line breaks. The file validates (src/translation_format.py), so Translations.dll uses every
line; a test then follows each sentinel to where the game draws it or a DLL fills it in.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import translation_format as tf  # noqa: E402
import translation_strings as ts  # noqa: E402

PAD = "_"


def tag(n: int) -> str:
    return f"§K{n:03d}§"


def _edges(text: str) -> tuple[str, str]:
    stripped = text.strip(" \n")
    if not stripped:
        return "", ""
    lead = text[:len(text) - len(text.lstrip(" \n"))]
    tail = text[len(text.rstrip(" \n")):]
    return lead, tail


def sentinel(n: int, entry: tf.Entry) -> str:
    """The sentinel translation of one line: its tag, its placeholders in order, a choice for each
    of the English's (by the same subject), its variables, padding, its edges."""
    english = entry.english
    template = tf.parse_template(english)
    parts = [conv.text for conv in template.conversions]
    for select in template.selects:
        if select.kind == "person":
            parts.append("{" + select.subject + ": m=q | f=q | o=q}")
        else:
            parts.append("{" + select.subject + ": one=q | other=qq}")
    parts += ["{" + v + "}" for v in sorted(template.variables)]
    lead, tail = _edges(english)
    body = tag(n) + (" " + " ".join(parts) if parts else "")

    def fits(text: str) -> bool:
        return not tf.too_long(text, entry.max_length, entry.wide, english, entry.is_format)
    room = len(english.encode("utf-16-le")) // 2 if entry.wide else len(english.encode("utf-8"))
    while fits(lead + body + PAD + tail) and tf.measure(lead + body + PAD + tail, entry.wide) <= room:
        body += PAD
    return lead + body + tail


@dataclass
class Line:
    n: int
    entry: tf.Entry
    translation: str

    @property
    def key(self) -> str:
        return self.entry.key

    @property
    def tag(self) -> str:
        return tag(self.n)

    def shown(self, numbers: list[int] | None = None, code: str = "en") -> str:
        """The sentinel as the player sees it: choices made, %d filled with `numbers`."""
        values = {f"%{k + 1}": v for k, v in enumerate(numbers or [])}
        text = tf.evaluate(self.translation, code, values)
        it = iter(numbers or [])
        return re.sub(r"%%|%[di]", lambda m: "%" if m.group() == "%%" else str(next(it)), text)


@lru_cache(maxsize=None)
def entries(game: str) -> tuple[tf.Entry, ...]:
    import store_emulator as se
    exe = {"fish": se.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe",
           "plant": se.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"}[game]
    return tuple(ts.entries_for(game, exe.read_bytes()))


@lru_cache(maxsize=None)
def lines(game: str) -> tuple[Line, ...]:
    return tuple(Line(n, e, sentinel(n, e)) for n, e in enumerate(entries(game)))


def file_bytes(game: str) -> bytes:
    """The sentinel translation file (format 1, language "Sentinel", code "en")."""
    f = tf.new_file(game, list(entries(game)), "Sentinel", "en")
    by_key = {line.key: line.translation for line in lines(game)}
    for row in f.rows:
        row.translation = by_key[row.key]
    return tf.to_bytes(f)


def validate(game: str) -> tf.Report:
    return tf.validate(tf.parse_bytes(file_bytes(game), game), list(entries(game)))


def game_id(key: str) -> int | None:
    parts = tf.split_key(key)
    if parts is None or parts[0] != "strings":
        return None
    return int(parts[1])


def mod_of(game: str) -> dict[str, ts.ModString]:
    out = {}
    for m in ts.MOD_STRINGS:
        if m.game == game:
            out.setdefault(ts.mod_key(m), m)
    return out


def encoded(text: str, wide: bool) -> bytes:
    return text.encode("utf-16-le") + b"\0\0" if wide else text.encode("cp1252") + b"\0"


def string_starts(image: bytes, needle: bytes, wide: bool) -> list[int]:
    """Offsets where `needle` (terminator included) starts a whole string in a DLL image."""
    out, at = [], 0
    unit = 2 if wide else 1
    while True:
        at = image.find(needle, at)
        if at < 0:
            return out
        if (not wide or at % 2 == 0) and (at == 0 or image[at - unit:at] == b"\0" * unit):
            out.append(at)
        at += 1


def u32(data: bytes, at: int) -> int:
    return struct.unpack_from("<I", data, at)[0]
