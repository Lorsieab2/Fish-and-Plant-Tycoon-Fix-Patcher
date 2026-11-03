"""Every string literal a shipped patcher DLL holds, for tests/test_translation_coverage.py.

A DLL's literals are read from its C sources (its native folder and every header it includes),
adjacent literals joined as the compiler joins them, and kept when the DLL as shipped holds them
(ANSI with its terminator, or UTF-16 for L"..."): the texts the DLL can show. The C runtime's own
texts are not in our sources, so they never appear.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"

# Each shipped DLL: (game, its native folder). Translations.dll itself shows no text.
DLLS = {
    ("fish", "Tank Counts.dll"): ("fish_tycoon_counts", "ftfp_tank_counts"),
    ("fish", "DS Exclusive Fish.dll"): ("fish_tycoon_ds", "ftfp_ds_fish"),
    ("fish", "DS Store Items.dll"): ("fish_tycoon_ds_store", "ftfp_ds_store"),
    ("fish", "Extra Tanks.dll"): ("fish_tycoon_extra_tanks", "ftfp_extra_tanks"),
    ("fish", "Optimize Prices.dll"): ("fish_tycoon_optimize_prices", "ftfp_fish_prices"),
    ("fish", "Multiple Ornaments.dll"): ("fish_tycoon_ornaments", "ftfp_ornaments"),
    ("fish", "Extra Supply Slots.dll"): ("fish_tycoon_supply_slots", "ftfp_supply_slots"),
    ("fish", "Unicode Text.dll"): ("fish_tycoon_unicode", "ftfp_fish_unicode"),
    ("fish", "Maximizable Window.dll"): ("fish_tycoon_window", "ftfp_fish_window"),
    ("plant", "Extra Chemical Slots.dll"): ("plant_tycoon_chem_slots", "ftfp_chem_slots"),
    ("plant", "Greenhouse Counts.dll"): ("plant_tycoon_counts", "ftfp_greenhouse_counts"),
    ("plant", "Unused Flowers.dll"): ("plant_tycoon_flowers", "ftfp_new_flowers"),
    ("plant", "Extra Greenhouses.dll"): ("plant_tycoon_greenhouses", "ftfp_extra_greenhouses"),
    ("plant", "Optimize Prices.dll"): ("plant_tycoon_optimize_prices", "ftfp_plant_prices"),
    ("plant", "Sort Seeds.dll"): ("plant_tycoon_sort_seeds", "ftfp_sort_seeds"),
    ("plant", "Unicode Text.dll"): ("plant_tycoon_unicode", "ftfp_plant_unicode"),
    ("plant", "Extra Seed Boxes.dll"): ("plant_tycoon_upgrades", "ftfp_seed_boxes"),
    ("plant", "Store Upgrades and Items.dll"): ("plant_tycoon_upgrades", "ftfp_plant_upgrades"),
}

_TOKEN = re.compile(r'//[^\n]*|/\*.*?\*/|(L?)"((?:[^"\\\n]|\\.)*)"|\'(?:[^\'\\\n]|\\.)*\'|#\s*include\s*[<"][^>"\n]*[>"]'
                    r'|[^\s]', re.S)
_ESCAPE = re.compile(r'\\(x[0-9A-Fa-f]+|[0-7]{1,3}|.)', re.S)
_SIMPLE = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "0": "\0", "a": "\a", "b": "\b",
           "f": "\f", "v": "\v", "?": "?"}


def _unescape(body: str) -> str:
    def one(m: re.Match) -> str:
        e = m.group(1)
        if e[0] == "x":
            return chr(int(e[1:], 16))
        if e[0].isdigit() and e[0] in "01234567" and (len(e) > 1 or e != "0"):
            return chr(int(e, 8))
        return _SIMPLE.get(e, e)
    return _ESCAPE.sub(one, body)


@dataclass(frozen=True)
class Literal:
    text: str
    wide: bool
    where: str          # file:line


def _sources(folder: str) -> list[Path]:
    """The folder's sources and every header they include, once each."""
    todo = sorted((NATIVE / folder).glob("*.c")) + sorted((NATIVE / folder).glob("*.h"))
    seen: list[Path] = []
    while todo:
        path = todo.pop(0).resolve()
        if path in seen or not path.is_file():
            continue
        seen.append(path)
        for inc in re.findall(r'#\s*include\s*"([^"]+)"', path.read_text(encoding="cp1252")):
            todo.append(path.parent / inc)
    return seen


def literals(folder: str) -> list[Literal]:
    out: list[Literal] = []
    for path in _sources(folder):
        text = path.read_text(encoding="cp1252")
        pending: list[str] = []
        wide = False
        start = 0
        for m in _TOKEN.finditer(text):
            if m.group(2) is not None or (m.group(0).startswith(('"', 'L"'))):
                if not pending:
                    start = text.count("\n", 0, m.start()) + 1
                    wide = m.group(1) == "L"
                pending.append(_unescape(m.group(2) or ""))
                continue
            if m.group(0).startswith(("//", "/*")):
                continue
            if pending:
                out.append(Literal("".join(pending), wide, f"{path.name}:{start}"))
                pending = []
        if pending:
            out.append(Literal("".join(pending), wide, f"{path.name}:{start}"))
    return out


def shipped(game: str, dll: str) -> bytes:
    asset, _folder = DLLS[(game, dll)]
    return (ROOT / "assets" / asset / dll).read_bytes()


def in_dll(lit: Literal, data: bytes) -> bool:
    if lit.wide:
        return (lit.text.encode("utf-16-le") + b"\0\0") in data
    try:
        return (lit.text.encode("cp1252") + b"\0") in data
    except UnicodeEncodeError:
        return False


def dll_texts(game: str, dll: str) -> dict[tuple[str, bool], str]:
    """Every literal of the DLL's sources that the shipped DLL holds and that has words in it:
    (text, wide) -> where it is in the sources."""
    data = shipped(game, dll)
    found: dict[tuple[str, bool], str] = {}
    for lit in literals(DLLS[(game, dll)][1]):
        if re.search(r"[A-Za-z\xC0-\xFF]{2}", lit.text) and in_dll(lit, data):
            found.setdefault((lit.text, lit.wide), lit.where)
    return found
