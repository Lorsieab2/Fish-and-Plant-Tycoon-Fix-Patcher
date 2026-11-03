"""The Unicode Character Database, version 18.0.0, for the patcher's own tools.

Python's built-in unicodedata is the Unicode version of the Python that runs the patcher (older
than 18.0), so the patcher reads the 18.0 files it ships instead (data/unicode, downloaded from
https://www.unicode.org/Public/18.0.0/ and pinned by size and SHA-256 in data/unicode/sources.json).
They are read as plain text only, when first needed, and kept.

* category(ch), name(ch), lookup(name), is_assigned(cp), assigned_code_points();
* graphemes(text): user-perceived characters, UAX #29 (18.0) extended grapheme clusters, the
  GB9c conjunct rule as changed for 18.0 included (tested against GraphemeBreakTest.txt), with the
  shared spec's two joins on top (docs/UNICODE_SPEC.md section 2): every mark (Mn, Mc, Me) joins
  the character before it, and so does the character after a ZWJ (unless either is a control);
* NAME_BOX_BYTES: THE name limit of every name box, in bytes as stored (written only here;
  scripts/build_unicode18_tables.py writes the DLL's copy);
* decode_game_text / encode_game_text: the shared read and write rule for the games' bytes
  (Windows-1252 bytes and UTF-8 mixed, per sequence);
* blocks(), block_of(cp), age(cp), east_asian_width(cp);
* emoji_sequences(): every RGI emoji sequence (emoji-sequences.txt, emoji-zwj-sequences.txt).

The DLL's own tables (native/common/unicode_grapheme_table.h) are made from the same files by
scripts/build_unicode18_tables.py, so the games and the tools cut text in the same places.
"""

from __future__ import annotations

import bisect
import functools
from pathlib import Path
import re
from typing import Iterator

VERSION = "18.0.0"

# THE name limit (docs/UNICODE_SPEC.md section 2, the owner's "All games: up to 1,200"): every
# name box takes up to this many bytes as stored (encode_game_text), with no separate character
# cap. It is the games' own text box cap (their setLimit clamps there). This is the only place
# the number is written: scripts/build_unicode18_tables.py writes it into the DLL's header
# (native/common/unicode_grapheme_table.h), and tests/test_name_limit.py fails if another file
# spells it.
NAME_BOX_BYTES = 1200

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "unicode"

# Range names of UnicodeData.txt's "<..., First>" / "<..., Last>" pairs (Hangul is algorithmic).
RANGE_NAMES = (
    ("CJK Ideograph", "CJK UNIFIED IDEOGRAPH-"),
    ("Tangut Ideograph", "TANGUT IDEOGRAPH-"),
    ("Jurchen Character", "JURCHEN CHARACTER-"),
    ("Seal Character", "SMALL SEAL CHARACTER-"),
)
CONTROL_CATEGORIES = ("Cc", "Cs", "Co", "Cn")

# Grapheme_Cluster_Break values (the numbers are the DLL's too)
GCB = ("Other", "CR", "LF", "Control", "Extend", "ZWJ", "Regional_Indicator", "Prepend", "SpacingMark",
       "L", "V", "T", "LV", "LVT")
GCB_INDEX = {v: i for i, v in enumerate(GCB)}
INCB = ("None", "Consonant", "Extend", "Linker")
INCB_INDEX = {v: i for i, v in enumerate(INCB)}


def _path(name: str) -> Path:
    return DATA / name


def _records(name: str) -> Iterator[tuple[int, int, list[str]]]:
    """(first, last, fields) of each data line of a UCD property file: 'XXXX..YYYY ; a ; b # ...'."""
    with open(_path(name), encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            fields = [x.strip() for x in line.split(";")]
            span = fields[0]
            if ".." in span:
                a, b = span.split("..")
                first, last = int(a, 16), int(b, 16)
            else:
                first = last = int(span, 16)
            yield first, last, fields[1:]


class RangeMap:
    """Sorted, non-overlapping (first, last) -> value ranges."""

    def __init__(self, ranges, default=None) -> None:
        ranges = sorted(ranges)
        self.firsts = [r[0] for r in ranges]
        self.lasts = [r[1] for r in ranges]
        self.values = [r[2] for r in ranges]
        self.default = default

    def __call__(self, cp: int):
        i = bisect.bisect_right(self.firsts, cp) - 1
        if i >= 0 and cp <= self.lasts[i]:
            return self.values[i]
        return self.default

    def __iter__(self):
        return iter(zip(self.firsts, self.lasts, self.values))


# --------------------------------------------------------------------------- UnicodeData.txt

@functools.lru_cache(maxsize=None)
def _unicode_data() -> tuple[dict[int, tuple[str, str]], list[tuple[int, int, str, str]]]:
    """({code point: (name, category)}, [(first, last, range label, category)])."""
    single: dict[int, tuple[str, str]] = {}
    ranges: list[tuple[int, int, str, str]] = []
    first = None
    with open(_path("UnicodeData.txt"), encoding="utf-8") as f:
        for line in f:
            fields = line.rstrip("\n").split(";")
            if len(fields) < 3:
                continue
            cp, name, gc = int(fields[0], 16), fields[1], fields[2]
            if name.startswith("<") and name.endswith(", First>"):
                first = cp
                continue
            if name.startswith("<") and name.endswith(", Last>"):
                ranges.append((first, cp, name[1:-7], gc))
                first = None
                continue
            single[cp] = ("" if name.startswith("<") else name, gc)
    return single, ranges


def _cp(ch) -> int:
    return ch if isinstance(ch, int) else ord(ch)


def _range_of(cp: int) -> tuple[int, int, str, str] | None:
    for r in _unicode_data()[1]:
        if r[0] <= cp <= r[1]:
            return r
    return None


def category(ch) -> str:
    """The General_Category ("Lu", "Mn", ... "Cn" when unassigned)."""
    cp = _cp(ch)
    hit = _unicode_data()[0].get(cp)
    if hit is not None:
        return hit[1]
    r = _range_of(cp)
    return r[3] if r else "Cn"


def is_noncharacter(cp: int) -> bool:
    return 0xFDD0 <= cp <= 0xFDEF or (cp & 0xFFFE) == 0xFFFE


def is_assigned(cp: int) -> bool:
    return category(cp) != "Cn"


def is_text_letter(cp: int) -> bool:
    """A code point text may hold: assigned and not a control, surrogate, private use or noncharacter."""
    return category(cp) not in CONTROL_CATEGORIES and not is_noncharacter(cp)


def assigned_code_points(exclude=CONTROL_CATEGORIES) -> Iterator[int]:
    """Every assigned code point of 18.0 (by default without controls, surrogates and private use;
    noncharacters are unassigned)."""
    single, ranges = _unicode_data()
    out = [cp for cp, (_n, gc) in single.items() if gc not in exclude]
    for first, last, _label, gc in ranges:
        if gc not in exclude:
            out.extend(range(first, last + 1))
    return iter(sorted(out))


_JAMO_L = ["G", "GG", "N", "D", "DD", "R", "M", "B", "BB", "S", "SS", "", "J", "JJ", "C", "K", "T", "P", "H"]
_JAMO_V = ["A", "AE", "YA", "YAE", "EO", "E", "YEO", "YE", "O", "WA", "WAE", "OE", "YO", "U", "WEO", "WE", "WI",
           "YU", "EU", "YI", "I"]
_JAMO_T = ["", "G", "GG", "GS", "N", "NJ", "NH", "D", "L", "LG", "LM", "LB", "LS", "LT", "LP", "LH", "M", "B",
           "BS", "S", "SS", "NG", "J", "C", "K", "T", "P", "H"]


def _range_name(cp: int, label: str) -> str:
    if label.startswith("Hangul Syllable"):
        s = cp - 0xAC00
        return "HANGUL SYLLABLE " + _JAMO_L[s // 588] + _JAMO_V[(s % 588) // 28] + _JAMO_T[s % 28]
    for start, prefix in RANGE_NAMES:
        if label.startswith(start):
            return f"{prefix}{cp:04X}"
    return ""


def name(ch, default: str | None = None) -> str | None:
    """The character's name (UnicodeData 18.0; ranges by their rule), else `default`."""
    cp = _cp(ch)
    hit = _unicode_data()[0].get(cp)
    if hit is not None:
        return hit[0] or default
    r = _range_of(cp)
    if r is not None:
        return _range_name(cp, r[2]) or default
    return default


@functools.lru_cache(maxsize=None)
def _names() -> dict[str, int]:
    out = {n: cp for cp, (n, _gc) in _unicode_data()[0].items() if n}
    for first, _last, fields in _records("NameAliases.txt"):
        out.setdefault(fields[0], first)
    return out


_RANGE_NAME = re.compile(r"^(.*-)([0-9A-F]{4,6})$")


def lookup(text: str) -> str:
    """The character named `text` (any case; an alias too), as unicodedata.lookup. KeyError when none."""
    key = " ".join(text.upper().replace("_", " ").split())
    cp = _names().get(key)
    if cp is not None:
        return chr(cp)
    m = _RANGE_NAME.match(key)
    if m:
        value = int(m.group(2), 16)
        r = _range_of(value)
        if r is not None and _range_name(value, r[2]) == key:
            return chr(value)
    if key.startswith("HANGUL SYLLABLE "):
        for value in range(0xAC00, 0xD7A4):
            if _range_name(value, "Hangul Syllable") == key:
                return chr(value)
    raise KeyError(text)


def search_names(words: str, limit: int = 200) -> list[int]:
    """Code points whose name has every word of `words` (for the picker's search)."""
    want = words.upper().split()
    if not want:
        return []
    out = []
    for n, cp in sorted(_names().items(), key=lambda kv: kv[1]):
        if all(w in n for w in want):
            out.append(cp)
            if len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- other properties

@functools.lru_cache(maxsize=None)
def blocks() -> tuple[tuple[int, int, str], ...]:
    return tuple((a, b, f[0]) for a, b, f in _records("Blocks.txt"))


@functools.lru_cache(maxsize=None)
def _block_map() -> RangeMap:
    return RangeMap(blocks(), "No_Block")


def block_of(cp: int) -> str:
    return _block_map()(cp)


@functools.lru_cache(maxsize=None)
def _age_map() -> RangeMap:
    return RangeMap([(a, b, f[0]) for a, b, f in _records("DerivedAge.txt")], None)


def age(cp: int) -> str | None:
    """The Unicode version that assigned `cp` ("18.0" for the newest), None when unassigned."""
    return _age_map()(cp)


@functools.lru_cache(maxsize=None)
def _eaw_map() -> RangeMap:
    return RangeMap([(a, b, f[0]) for a, b, f in _records("EastAsianWidth.txt")], "N")


def east_asian_width(cp: int) -> str:
    return _eaw_map()(cp)


@functools.lru_cache(maxsize=None)
def gcb_map() -> RangeMap:
    return RangeMap([(a, b, GCB_INDEX[f[0]]) for a, b, f in _records("GraphemeBreakProperty.txt")], 0)


@functools.lru_cache(maxsize=None)
def incb_map() -> RangeMap:
    ranges = [(a, b, INCB_INDEX[f[1]]) for a, b, f in _records("DerivedCoreProperties.txt")
              if f[0] == "InCB"]
    return RangeMap(ranges, 0)


@functools.lru_cache(maxsize=None)
def mark_map() -> RangeMap:
    """True for a mark (General_Category Mn, Mc or Me): it joins the character before it."""
    single, ranges = _unicode_data()
    out = [(cp, cp, True) for cp, (_n, gc) in single.items() if gc in ("Mn", "Mc", "Me")]
    out += [(a, b, True) for a, b, _l, gc in ranges if gc in ("Mn", "Mc", "Me")]
    return RangeMap(out, False)


@functools.lru_cache(maxsize=None)
def _emoji_property(prop: str) -> RangeMap:
    return RangeMap([(a, b, True) for a, b, f in _records("emoji-data.txt") if f[0] == prop], False)


def extended_pictographic(cp: int) -> bool:
    return _emoji_property("Extended_Pictographic")(cp)


def emoji_presentation(cp: int) -> bool:
    return _emoji_property("Emoji_Presentation")(cp)


@functools.lru_cache(maxsize=None)
def emoji_sequences() -> frozenset[str]:
    """Every RGI emoji sequence of Emoji 18.0 (and each Basic_Emoji code point), as strings."""
    out = set()
    for file in ("emoji-sequences.txt", "emoji-zwj-sequences.txt"):
        with open(_path(file), encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                span = line.split(";")[0].strip()
                if ".." in span:
                    a, b = span.split("..")
                    out.update(chr(c) for c in range(int(a, 16), int(b, 16) + 1))
                else:
                    out.add("".join(chr(int(x, 16)) for x in span.split()))
    return frozenset(out)


# --------------------------------------------------------------------------- graphemes (UAX #29)

_CONTROLS = (GCB_INDEX["CR"], GCB_INDEX["LF"], GCB_INDEX["Control"])
_EXTEND, _ZWJ, _RI = GCB_INDEX["Extend"], GCB_INDEX["ZWJ"], GCB_INDEX["Regional_Indicator"]
_PREPEND, _SPACING = GCB_INDEX["Prepend"], GCB_INDEX["SpacingMark"]
_L, _V, _T, _LV, _LVT = (GCB_INDEX[k] for k in ("L", "V", "T", "LV", "LVT"))
_CR, _LF = GCB_INDEX["CR"], GCB_INDEX["LF"]


class GraphemeState:
    """The rules' memory while walking text: what GB9c, GB11 and GB12/13 need of what came before.
    The same state machine as native/common/unicode_grapheme.h."""

    __slots__ = ("prev", "emoji", "incb", "ri")

    def __init__(self) -> None:
        self.prev = -1        # the previous code point's GCB (-1: none yet)
        self.emoji = 0        # 1: ExtPict Extend*; 2: ExtPict Extend* ZWJ
        self.incb = 0         # 1: InCB=Linker InCB=Extend* (GB9c, as changed for 18.0)
        self.ri = 0           # regional indicators just before

    def push(self, cp: int) -> bool:
        """Take the next code point: True when a grapheme boundary comes before it."""
        g = gcb_map()(cp)
        i = incb_map()(cp)
        pict = extended_pictographic(cp)
        brk = self.prev < 0 or _breaks(self.prev, g, i, pict, self.emoji, self.incb, self.ri)
        if brk and spec_join(self.prev, g, cp):
            brk = False
        self.emoji = 1 if pict else (1 if self.emoji == 1 and g == _EXTEND else
                                     (2 if self.emoji == 1 and g == _ZWJ else 0))
        self.incb = 1 if i == 3 or (self.incb and i == 2) else 0
        self.ri = self.ri + 1 if g == _RI else 0
        self.prev = g
        return brk


def _breaks(prev: int, g: int, i: int, pict: bool, emoji: int, incb: int, ri: int) -> bool:
    if prev == _CR and g == _LF:
        return False                                   # GB3
    if prev in _CONTROLS or g in _CONTROLS:
        return True                                    # GB4, GB5
    if prev == _L and g in (_L, _V, _LV, _LVT):
        return False                                   # GB6
    if prev in (_LV, _V) and g in (_V, _T):
        return False                                   # GB7
    if prev in (_LVT, _T) and g == _T:
        return False                                   # GB8
    if g in (_EXTEND, _ZWJ) or g == _SPACING or prev == _PREPEND:
        return False                                   # GB9, GB9a, GB9b
    if i == 1 and incb:
        return False                                   # GB9c: Linker Extend* x Consonant
    if prev == _ZWJ and emoji == 2 and pict:
        return False                                   # GB11
    if prev == _RI and g == _RI and ri % 2 == 1:
        return False                                   # GB12, GB13
    return True                                        # GB999


def spec_join(prev: int, g: int, cp: int) -> bool:
    """The shared spec's joins on top of UAX #29 (docs/UNICODE_SPEC.md section 2, from VF1 and VF2):
    a mark (Mn, Mc, Me) joins the character before it, and the character after a ZWJ joins it,
    unless the one before or this one is a control (CR, LF or another control). `prev` is the
    previous code point's Grapheme_Cluster_Break (-1: none), `g` this one's."""
    if prev < 0 or prev in _CONTROLS or g in _CONTROLS:
        return False
    return prev == _ZWJ or mark_map()(cp)


def graphemes(text: str) -> list[str]:
    """The text's extended grapheme clusters (UAX #29, Unicode 18.0)."""
    out: list[str] = []
    state = GraphemeState()
    start = 0
    for k, ch in enumerate(text):
        if state.push(ord(ch)) and k > start:
            out.append(text[start:k])
            start = k
    if start < len(text):
        out.append(text[start:])
    return out


def cut_graphemes(text: str, limit: int) -> str:
    """At most `limit` code points of `text`, never part of a grapheme."""
    if len(text) <= limit:
        return text
    out, n = [], 0
    for g in graphemes(text):
        if n + len(g) > limit:
            break
        out.append(g)
        n += len(g)
    return "".join(out)


# --------------------------------------------------------------------------- the games' bytes

# Windows-1252's 0x80-0x9F (0: one of the five bytes it leaves undefined, read as the Latin-1
# control with the same number). The DLL's copy is CP1252_HIGH in native/common/unicode_utf8.h.
CP1252_HIGH = (
    0x20AC, 0, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, 0x02C6, 0x2030, 0x0160, 0x2039, 0x0152, 0, 0x017D, 0,
    0, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014, 0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0, 0x017E,
    0x0178,
)
_BYTE_OF = {(c if c else 0x80 + i): 0x80 + i for i, c in enumerate(CP1252_HIGH)}


def _utf8_at(raw: bytes, k: int) -> tuple[int, int] | None:
    """(code point, length) of a whole, shortest UTF-8 sequence at raw[k] (Unicode Table 3-7: no
    overlong form, no surrogate, nothing past U+10FFFF), or None."""
    c = raw[k]
    if c < 0x80:
        return c, 1
    if 0xC2 <= c <= 0xDF:
        n, cp = 2, c & 0x1F
    elif 0xE0 <= c <= 0xEF:
        n, cp = 3, c & 0x0F
    elif 0xF0 <= c <= 0xF4:
        n, cp = 4, c & 0x07
    else:
        return None
    if k + n > len(raw):
        return None
    for b in raw[k + 1:k + n]:
        if b & 0xC0 != 0x80:
            return None
        cp = (cp << 6) | (b & 0x3F)
    if (n == 3 and cp < 0x800) or (n == 4 and not 0x10000 <= cp <= 0x10FFFF) or 0xD800 <= cp <= 0xDFFF:
        return None
    return cp, n


def byte_char(b: int) -> int:
    """The character a single byte stands for: Windows-1252, its five undefined bytes as Latin-1."""
    if 0x80 <= b <= 0x9F:
        return CP1252_HIGH[b - 0x80] or b
    return b


def decode_game_text(raw: bytes) -> str:
    """The read rule (docs/UNICODE_SPEC.md section 2, one decoder for the DLL and the tools): each
    whole, shortest UTF-8 sequence is its character; every other byte is its Windows-1252
    character (the five undefined bytes 81 8D 8F 90 9D as the Latin-1 control). Per sequence, not
    per string, so mixed text reads correctly. The DLL's copy is utf8_next."""
    out, k = [], 0
    while k < len(raw):
        hit = _utf8_at(raw, k)
        if hit is None:
            out.append(chr(byte_char(raw[k])))
            k += 1
        else:
            out.append(chr(hit[0]))
            k += hit[1]
    return "".join(out)


def game_byte(ch: str) -> int | None:
    """The one byte a character is written as, when Windows-1252 (or Latin-1, for the five) has it."""
    cp = ord(ch)
    if cp < 0x80 or 0xA0 <= cp <= 0xFF:
        return cp
    return _BYTE_OF.get(cp)


def encode_game_text(text: str) -> bytes:
    """The write rule (docs/UNICODE_SPEC.md section 2, from VV): a character Windows-1252 has is its
    one byte, any other its UTF-8 bytes, both mixed in one string; when the mixed bytes would read
    back as different text (a "\u00c3" byte then a "\u00a9" byte spell the UTF-8 of "\u00e9"),
    every non-ASCII character is written as UTF-8 instead. A UTF-8 Windows-1252 character met on
    input (decode_game_text) is so written back as its byte. The DLL's copy is game_encode
    (native/common/unicode_utf8.h)."""
    parts = []
    for ch in text:
        b = game_byte(ch)
        parts.append(bytes((b,)) if b is not None else ch.encode("utf-8", "surrogatepass"))
    mixed = b"".join(parts)
    if decode_game_text(mixed) == text:
        return mixed
    return text.encode("utf-8", "surrogatepass")


def game_bytes_len(text: str) -> int:
    """How many bytes a name box stores for `text` (what NAME_BOX_BYTES counts)."""
    return len(encode_game_text(text))


def cut_game_bytes(text: str, limit: int) -> str:
    """The longest start of `text`, whole graphemes only, that the games store in `limit` bytes."""
    if game_bytes_len(text) <= limit:
        return text
    out: list[str] = []
    for g in graphemes(text):
        if game_bytes_len("".join(out) + g) > limit:
            break
        out.append(g)
    return "".join(out)
