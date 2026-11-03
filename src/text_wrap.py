"""Wrap to fit: re-break a translation so no line is wider than the widest line of its English.

The games break lines only at "\\n" (the draw at Fish 0x408874 and Plant's equivalent), so the
translation editor does the breaking. Only whitespace and newlines change, never the words.

Pure code: the caller gives `measure(line) -> pixels`, the Text Maker's own measuring of a line in the
game's font. Breaks follow UAX #14 as far as this needs (the repo has no LineBreak.txt, so the rules
are written directly): after spaces; after a hyphen (not before a digit); between CJK characters
(kana, ideographs, fullwidth forms) with the kinsoku rules (a line does not start with the closing
and small marks such as the ideographic full stop, comma, closing brackets, ! and ?, nor end with an
opening bracket); never inside a grapheme cluster (unicode_data.graphemes, the Text Maker's clusters) or a placeholder (%d, %s,
{choices}); a word wider than the limit is cut. Thai, Lao, Khmer and Myanmar have no spaces between
words and the repo has no dictionary: a run of them is never cut and is reported as "cannot wrap".
Hangul breaks at spaces only (Korean has them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable

import translation_format as tfmt
import unicode_data

PLACEHOLDER_RE = re.compile(tfmt.CONVERSION_RE.pattern + r"|\{[^{}]*\}")
Measure = Callable[[str], int]

NO_START = set("。、，．）」』】〕〉》〗〙〛｝］！？：；・ーゝゞヽヾ々〻ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ"
               "‼⁇⁈⁉…‥〜～!?,.;:)]}%”’»")
NO_END = set("（「『【〔〈《〖〘〚｛［([{“‘«¡¿")
NO_BREAK_AROUND = set("   ⁠﻿")
HYPHENS = set("-‐–­")
SPACES = set(" \t            　")
SPACE_CHARS = "".join(SPACES)
THAI_LIKE = ((0x0E00, 0x0EFF), (0x1000, 0x109F), (0x1780, 0x17FF), (0x19E0, 0x19FF), (0xAA60, 0xAA7F),
             (0xA9E0, 0xA9FF), (0x1A20, 0x1AAF))
ID_RANGES = ((0x2E80, 0x2FFF), (0x3040, 0x30FF), (0x3100, 0x312F), (0x3190, 0x31FF), (0x3200, 0x4DBF),
             (0x4E00, 0x9FFF), (0xA960, 0xA97F), (0xF900, 0xFAFF), (0xFE30, 0xFE4F), (0xFF00, 0xFFEF),
             (0x1B000, 0x1B16F), (0x1F200, 0x1F2FF), (0x20000, 0x3FFFD), (0x3000, 0x303F))


def _in(cp: int, ranges) -> bool:
    return any(a <= cp <= b for a, b in ranges)


@dataclass
class Atom:
    text: str
    kind: str       # "sp" space, "id" CJK, "sa" Thai-like, "ph" placeholder, "al" other, "nl" newline

    @property
    def no_start(self) -> bool:
        return self.kind != "ph" and self.text[0] in NO_START

    @property
    def no_end(self) -> bool:
        return self.kind != "ph" and self.text[-1] in NO_END


def _kind(unit: str) -> str:
    ch = unit[0]
    cp = ord(ch)
    if ch in "\r\n":
        return "nl"
    if ch in SPACES:
        return "sp"
    if _in(cp, THAI_LIKE):
        return "sa"
    if _in(cp, ID_RANGES):
        return "id"
    return "al"


def atoms_of(text: str) -> list[Atom]:
    """Grapheme clusters, with every placeholder one atom."""
    out: list[Atom] = []
    pos = 0
    for m in PLACEHOLDER_RE.finditer(text):
        out += [Atom(c, _kind(c)) for c in unicode_data.graphemes(text[pos:m.start()])]
        out.append(Atom(m.group(), "ph"))
        pos = m.end()
    out += [Atom(c, _kind(c)) for c in unicode_data.graphemes(text[pos:])]
    return out


def can_break(a: Atom, b: Atom) -> bool:
    """May a line end after atom a, with b starting the next?"""
    if a.kind in ("sp", "nl") and b.kind in ("sp", "nl"):
        return False
    if a.kind == "sp":
        return not b.no_start
    if b.kind == "sp":
        return False
    al, bl = a.text[-1], b.text[0]
    if al in NO_BREAK_AROUND or bl in NO_BREAK_AROUND:
        return False
    if al == "​":
        return True
    if b.no_start or a.no_end:
        return False
    if a.kind == "al" and al in HYPHENS:
        return not bl.isdigit() and b.kind != "sa"
    return a.kind == "id" or b.kind == "id"


def english_width(english: str, measure: Measure) -> int:
    """The widest line of the English: the room a translation is held to."""
    return max((measure(line) for line in english.split("\n")), default=0)


@dataclass
class WrapResult:
    text: str
    cannot_wrap: list[str] = field(default_factory=list)   # runs wider than the room that cannot be cut
    cut: int = 0                                           # words cut because they alone were too wide


def _segments(atoms: list[Atom]) -> list[list[Atom]]:
    """Pieces between break opportunities; a piece keeps its trailing spaces."""
    segs: list[list[Atom]] = []
    cur: list[Atom] = []
    for i, a in enumerate(atoms):
        cur.append(a)
        if i + 1 < len(atoms) and can_break(a, atoms[i + 1]):
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    return segs


def _join(atoms: list[Atom]) -> str:
    return "".join(a.text for a in atoms)


def _width(measure: Measure, atoms: list[Atom]) -> int:
    return measure(_join(atoms).rstrip(SPACE_CHARS))


def _cut(seg: list[Atom], limit: int, measure: Measure) -> list[list[Atom]]:
    """A piece that alone is too wide: lines of as many atoms as fit (at least one), not starting a
    line with a closing mark nor ending one with an opening mark."""
    lines: list[list[Atom]] = []
    rest = list(seg)
    while rest:
        n = 1
        while n < len(rest) and _width(measure, rest[:n + 1]) <= limit:
            n += 1
        while n > 1 and n < len(rest) and (rest[n].no_start or rest[n - 1].no_end):
            n -= 1
        lines.append(rest[:n])
        rest = rest[n:]
    return lines


def _wrap_paragraph(text: str, limit: int, measure: Measure, result: WrapResult) -> str:
    lines: list[list[Atom]] = []
    cur: list[Atom] = []
    for seg in _segments(atoms_of(text)):
        if cur and _width(measure, cur + seg) <= limit:
            cur += seg
            continue
        if cur:
            lines.append(cur)
            cur = []
        if _width(measure, seg) <= limit:
            cur = list(seg)
        elif any(a.kind == "sa" for a in seg):
            result.cannot_wrap.append(_join(seg).strip())
            cur = list(seg)
        else:
            pieces = _cut(seg, limit, measure)
            result.cut += 1
            lines.extend(pieces[:-1])
            cur = pieces[-1]
    if cur:
        lines.append(cur)
    return "\n".join(_join(line).rstrip(SPACE_CHARS) for line in lines)


def _joiner(before: str, after: str) -> str:
    """What replaces a single newline when lines are joined before re-breaking: a space between
    spaced scripts, nothing next to CJK or Thai (which have none) or next to a space."""
    if not before or not after or before[-1] in SPACES or after[0] in SPACES:
        return ""
    if _kind(before[-1]) in ("id", "sa") or _kind(after[0]) in ("id", "sa"):
        return ""
    return " "


def wrap(text: str, limit: int, measure: Measure) -> WrapResult:
    """Re-break `text` so no line is wider than `limit` pixels. A blank line (two newlines) stays a
    paragraph break; a single newline is a soft break that is decided again."""
    result = WrapResult(text)
    paragraphs = re.split(r"\n[ \t]*\n", text.replace("\r\n", "\n"))
    out = []
    for para in paragraphs:
        lines = para.split("\n")
        joined = lines[0]
        for line in lines[1:]:
            joined += _joiner(joined, line) + line
        out.append(_wrap_paragraph(joined, limit, measure, result))
    result.text = "\n\n".join(out)
    return result


def needs_wrap(translation: str, english: str, measure: Measure) -> bool:
    """The translation has a line wider than the widest line of the English."""
    return bool(translation) and english_width(translation, measure) > english_width(english, measure)
