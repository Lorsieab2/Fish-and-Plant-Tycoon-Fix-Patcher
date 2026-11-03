"""Word breaking for the scripts written without spaces: Thai, Lao, Burmese (Myanmar), Khmer, and
Chinese and Japanese.

A line that must wrap should break between words. The word lists are ICU's dictionaries
(assets/translations/word-lists/, ICU 77.1, shipped unchanged with ICU-LICENSE.txt; they are also
what Translations.dll reads in the game when Windows' own icu.dll is missing). This module is the
patcher's editor side, and the reference the DLL's C code (native/ftfp_translations/word_break.h)
is written to agree with.

Method (the same in the DLL): the text is cut into runs of one script (Thai, Lao, Myanmar, Khmer,
or Han/Hiragana/Katakana together). Inside a run, a word starts at every place that is not a
combining mark, and the next word is the LONGEST dictionary word there (maximal matching, as ICU's
dictionary breaker does) that is followed by the end of the run or by another word (looking ahead
up to two more words, as ICU's does), else the longest. A stretch no word matches is one unknown
piece (a run of Katakana, or one Thai stretch up to the next known word; any other Han or Kana
character is a piece of its own).

analyze(text) gives, for each character, 0 (not in a segmented run: no information), 1 (inside a
word: never break before it), 2 (a word starts here: a break may go before it). A run whose list is
missing is left at 0. Lists load lazily, the first time text of that script is seen, and are kept.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "assets" / "translations" / "word-lists"
FILES = {"thai": "thaidict.txt", "lao": "laodict.txt", "myanmar": "burmesedict.txt",
         "khmer": "khmerdict.txt", "cj": "cjdict.txt"}
MAX_WORD = 48                 # longest word kept, in characters (the longest in the lists is 33)

# (low, high) of the characters each list's run is made of; punctuation, digits' signs and the
# like are left out, so they end a run.
RANGES = {
    "thai": ((0x0E01, 0x0E3A), (0x0E40, 0x0E4E), (0x0E50, 0x0E59)),
    "lao": ((0x0E81, 0x0ECD), (0x0ED0, 0x0ED9), (0x0EDC, 0x0EDF)),
    "myanmar": ((0x1000, 0x1049), (0x1050, 0x109F)),
    "khmer": ((0x1780, 0x17D3), (0x17DD, 0x17E9)),
    "cj": ((0x2E80, 0x2FDF), (0x3005, 0x3005), (0x3007, 0x3007), (0x3021, 0x3029), (0x3038, 0x303B),
           (0x3041, 0x309A), (0x309D, 0x309F), (0x30A1, 0x30FA), (0x30FC, 0x30FF), (0x31F0, 0x31FF),
           (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0xFF66, 0xFF9F), (0x20000, 0x3FFFD)),
}
# A character that joins the one before it: a word never starts on it.
JOINERS = ((0x0E31, 0x0E31), (0x0E34, 0x0E3A), (0x0E47, 0x0E4E), (0x0EB1, 0x0EB1), (0x0EB4, 0x0EBC),
           (0x0EC8, 0x0ECD), (0x102B, 0x103E), (0x1056, 0x1059), (0x105E, 0x1060), (0x1062, 0x1064),
           (0x1067, 0x106D), (0x1071, 0x1074), (0x1082, 0x108D), (0x108F, 0x108F), (0x109A, 0x109D),
           (0x17B4, 0x17D3), (0x17DD, 0x17DD), (0x3099, 0x309A))
COENG = 0x17D2                # the Khmer subscript sign: the consonant after it joins it too
KATAKANA = ((0x30A1, 0x30FA), (0x30FC, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F))


def _in(cp: int, ranges) -> bool:
    for lo, hi in ranges:
        if lo <= cp <= hi:
            return True
    return False


def script_of(cp: int) -> str:
    """"thai", "lao", "myanmar", "khmer" or "cj" for a character a word list covers, else ""."""
    if cp < 0x0E01:
        return ""
    for name, ranges in RANGES.items():
        if _in(cp, ranges):
            return name
    return ""


class Dictionary:
    def __init__(self, words: set[str], longest: int) -> None:
        self.words = words
        self.longest = longest


_CACHE: dict[str, Optional[Dictionary]] = {}


def parse(data: bytes) -> Dictionary:
    """A list's text: UTF-8 (a byte order mark first), "#" lines are comments, one word a line (the
    Chinese and Japanese list adds a tab and a frequency)."""
    words: set[str] = set()
    longest = 0
    for line in data.decode("utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        word = line.split("\t")[0].strip()
        if not word or len(word) > MAX_WORD:
            continue
        words.add(word)
        longest = max(longest, len(word))
    return Dictionary(words, longest)


def dictionary(script: str, folder: Path | None = None) -> Optional[Dictionary]:
    """The word list of a script, loaded once; None when the file is missing or unreadable."""
    key = f"{folder or ''}|{script}"
    if key not in _CACHE:
        try:
            _CACHE[key] = parse(((folder or FOLDER) / FILES[script]).read_bytes())
        except (OSError, ValueError):
            _CACHE[key] = None
    return _CACHE[key]


def _starts(run: str) -> list[bool]:
    """starts[i]: a word may start at run[i] (it is not a combining mark, nor after a Khmer coeng)."""
    out = []
    for i, ch in enumerate(run):
        cp = ord(ch)
        out.append(not _in(cp, JOINERS) and not (i > 0 and ord(run[i - 1]) == COENG))
    return out


def segment(run: str, words: Dictionary, script: str) -> list[int]:
    """The start index of every word of one run (always begins with 0)."""
    n = len(run)
    starts = _starts(run)
    longest_at: dict[int, int] = {}

    def valid_end(e: int) -> bool:
        return e == n or starts[e]

    def matches(i: int) -> list[int]:
        if not starts[i]:
            return []
        return [length for length in range(min(words.longest, n - i), 0, -1)
                if valid_end(i + length) and run[i:i + length] in words.words]

    def longest(i: int) -> int:
        if i not in longest_at:
            found = matches(i)
            longest_at[i] = found[0] if found else 0
        return longest_at[i]

    out: list[int] = []
    i = 0
    while i < n:
        out.append(i)
        if not starts[i]:
            i += 1
            continue
        lengths = matches(i)
        choice = 0
        for length in lengths:
            j = i + length
            if j == n:
                choice = length
                break
            second = longest(j)
            if not second:
                continue
            k = j + second
            if k == n or longest(k):
                choice = length
                break
        if not choice and lengths:
            choice = lengths[0]
        if choice:
            i += choice
            continue
        # no word here: one unknown piece
        j = i + 1
        if script == "cj":
            if _in(ord(run[i]), KATAKANA):
                while j < n and _in(ord(run[j]), KATAKANA):
                    j += 1
        else:
            while j < n and not (starts[j] and longest(j)):
                j += 1
        i = j
    return out


def analyze(text: str, folder: Path | None = None) -> list[int]:
    """Per character: 0 no information, 1 inside a word, 2 a word starts here (see the module's text)."""
    state = [0] * len(text)
    i = 0
    n = len(text)
    while i < n:
        script = script_of(ord(text[i]))
        if not script:
            i += 1
            continue
        j = i + 1
        while j < n and script_of(ord(text[j])) == script:
            j += 1
        words = dictionary(script, folder)
        if words is not None:
            begins = set(segment(text[i:j], words, script))
            for k in range(i, j):
                state[k] = 2 if (k - i) in begins else 1
        i = j
    return state


def words_of(text: str, folder: Path | None = None) -> list[str]:
    """The text cut at every word start (a convenience for tests and tools)."""
    state = analyze(text, folder)
    out: list[str] = []
    cur = ""
    for ch, s in zip(text, state):
        if s == 2 and cur:
            out.append(cur)
            cur = ""
        cur += ch
    if cur:
        out.append(cur)
    return out
