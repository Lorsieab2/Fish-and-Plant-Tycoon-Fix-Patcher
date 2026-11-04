"""Does a translated line fit where the game draws it? The pixel room of every line
(data/translation_limits.json, written by scripts/build_translation_limits.py from runs of the
games' own code) and the line's real width in the game's font (the Text Maker's layout, the
letters the game's font has, the patcher-made ones and the ones Windows draws, as Wrap to fit
measures them).

A line wider than its room is a WARNING, never an error: the translation stays usable, and in the
game Translations.dll fits it (re-broken where the English has line breaks, otherwise cut with an
ellipsis, else the English). Lines whose room no run measured have the safe rule's room (the
English's widest line plus a quarter, at least 16 pixels, never past the screen): "proven" is
False for them. A Windows popup's text has no room (Windows wraps it).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

import translation_format as tfmt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "translation_limits.json"


@dataclass(frozen=True)
class Limit:
    width: int | None          # pixels; None: no limit (a Windows popup)
    font: int = 0              # the game's font number
    multiline: bool = False    # the English breaks lines (the game may re-break a translation)
    proven: bool = False       # measured by running the game's code (else the safe rule)
    kind: str = ""
    height: int | None = None  # a box sized from its text: the tallest text it holds on the screen
    format: bool = False


_CACHE: dict[str, dict[str, Limit]] = {}


def limits(game: str, path: Path | None = None) -> dict[str, Limit]:
    """base key ("strings/12", "mod/<id>") -> Limit; {} when the data file is missing."""
    key = f"{game}:{path or ''}"
    if key not in _CACHE:
        out: dict[str, Limit] = {}
        try:
            data = json.loads((path or DATA).read_text(encoding="utf-8"))
            for base, e in data["games"][game]["lines"].items():
                out[base] = Limit(e.get("width"), e.get("font", 0), bool(e.get("multiline")), bool(e.get("proven")),
                                  e.get("kind", ""), e.get("height"), bool(e.get("format")))
        except (OSError, ValueError, KeyError):
            out = {}
        _CACHE[key] = out
    return _CACHE[key]


def base_of(key: str) -> str | None:
    parts = tfmt.split_key(key)
    if not parts:
        return None
    source, ident, _hash = parts
    return f"{source}/{ident}"


def limit_for(game: str, key: str) -> Limit | None:
    base = base_of(key)
    return limits(game).get(base) if base else None


Measure = Callable[[int, str], int]       # (font number, one line) -> pixels


@dataclass(frozen=True)
class TooWide:
    key: str
    line: int                  # 1-based line of the translation (its "\n" lines)
    text: str
    width: int
    room: int
    limit: Limit

    def message(self) -> str:
        where = "measured in the game" if self.limit.proven else "the safe rule: the English's widest line plus a quarter"
        fix = ("the game re-breaks it, cuts it with an ellipsis if it still does not fit, or shows English"
               if self.limit.multiline else "the game cuts it with an ellipsis, or shows English if even that does not fit")
        return (f"too wide for its spot: line {self.line} of {self.key} is {self.width} pixels, the room is "
                f"{self.room} pixels ({where}); {fix}. Wrap to fit can re-break it.")


def too_wide(game: str, key: str, translation: str, measure: Measure, limit: Limit | None = None,
             english: str | None = None) -> TooWide | None:
    """The first line of the translation (choices at their longest, as the runtime measures it)
    wider than its room, or None. A format line is measured as written (its %d / %s as they are)."""
    limit = limit or limit_for(game, key)
    if limit is None or limit.width is None or not translation:
        return None
    text = tfmt.evaluate(translation, longest=True) if "{" in translation else translation
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        width = measure(limit.font, line)
        if width > limit.width:
            return TooWide(key, n, line, width, limit.width, limit)
    return None


# ---------------------------------------------------------------- measuring with the game's fonts

def fonts_by_number(game: str, folder: Path) -> list:
    """The game's fonts as its code numbers them (Fish 0, 1, 2; Plant 0), from a game copy."""
    import text_maker as tm
    loaded = {f.spec.key: f for f in tm.load_fonts(game, Path(folder))}
    return [loaded.get(spec.key) for spec in tm.FONTS[game] if spec.table is not None]


def measurer(fonts: list) -> Measure:
    """measure(font number, line): the Text Maker's layout width (font 0 when the number is missing)."""
    import text_maker as tm

    def measure(font: int, line: str) -> int:
        f = fonts[font] if 0 <= font < len(fonts) and fonts[font] is not None else fonts[0]
        return tm.layout(f, line)[1]
    return measure


def checker(game: str, folders) -> Callable[[str, str, str], str | None] | None:
    """For tfmt.validate(widths=...): (key, english, translation) -> a warning, or None. None when
    no copy of the game with its fonts is found (then widths are not checked)."""
    import text_maker as tm
    folder = tm.find_game_folder(game, folders)
    if folder is None:
        return None
    fonts = fonts_by_number(game, folder)
    if not fonts or fonts[0] is None:
        return None
    measure = measurer(fonts)

    def check(key: str, english: str, translation: str) -> str | None:
        found = too_wide(game, key, translation, measure, english=english)
        return found.message() if found else None
    return check
