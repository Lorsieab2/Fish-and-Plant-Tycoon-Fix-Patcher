"""Make data/unicode/font_coverage.json: which code points each bundled fallback font (data/unicode/
fonts.json, shipped in assets/<game>_tycoon_unicode/Fonts) maps to a real glyph, from its cmap read
with fontTools, as (first, last) ranges. tests/test_unicode18.py proves from it, with no font
library, that every assigned code point of Unicode 18.0 has a glyph in the chain, and checks it
against the font files themselves when fontTools is installed.

    pip install fonttools
    python scripts/build_unicode18_coverage.py           # write it
    python scripts/build_unicode18_coverage.py --report  # also print the counts per font

The font files are read as data only (fontTools parses their tables; nothing in them runs).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import unicode_data as U  # noqa: E402

FONTS = ROOT / "assets" / "fish_tycoon_unicode" / "Fonts"
OUT = ROOT / "data" / "unicode" / "font_coverage.json"


def mapped(path: Path) -> list[int]:
    """Code points the font's best Unicode cmap maps to a glyph other than .notdef (glyph 0)."""
    from fontTools.ttLib import TTFont
    font = TTFont(str(path), lazy=True)
    order = font.getGlyphOrder()
    notdef = order[0] if order else ".notdef"
    best = font.getBestCmap() or {}
    return sorted(cp for cp, glyph in best.items() if glyph not in (notdef, ".notdef"))


def to_ranges(cps: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for cp in cps:
        if out and out[-1][1] + 1 == cp:
            out[-1][1] = cp
        else:
            out.append([cp, cp])
    return out


def build() -> dict:
    fonts = json.loads((ROOT / "data" / "unicode" / "fonts.json").read_text(encoding="utf-8"))["fonts"]
    out = []
    for f in fonts:
        path = FONTS / f["file"]
        data = path.read_bytes()
        out.append({"file": f["file"], "family": f["family"],
                    "sha256": hashlib.sha256(data).hexdigest().upper(), "ranges": to_ranges(mapped(path))})
    return {"unicode": U.VERSION, "fonts": out}


def main() -> int:
    doc = build()
    OUT.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    if "--report" in sys.argv[1:]:
        assigned = {cp for cp in U.assigned_code_points() if not U.is_noncharacter(cp)}
        covered: set[int] = set()
        for f in doc["fonts"]:
            cps = {cp for a, b in f["ranges"] for cp in range(a, b + 1)} & assigned
            print(f"{f['family']}: {len(cps)} assigned code points, {len(cps - covered)} not in a font before it")
            if f["family"] != "Last Resort":
                covered |= cps
        print(f"assigned: {len(assigned)}; only Last Resort: {len(assigned - covered)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
