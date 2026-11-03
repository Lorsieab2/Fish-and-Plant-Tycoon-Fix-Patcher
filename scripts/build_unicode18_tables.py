"""Make native/common/unicode_grapheme_table.h: the Unicode 18.0 tables "Unicode Text.dll" cuts and
draws text with, from the same data/unicode files the patcher's tools read (src/unicode_data.py).

    python scripts/build_unicode18_tables.py           # write the header
    python scripts/build_unicode18_tables.py --check   # exit 1 when the header is not up to date

* NAME_BOX_BYTES: the one name limit, from src/unicode_data.py (the only place it is written).
* GB_RANGES: every code point's grapheme properties, as the first code point of each run of equal
  values: (first << 8) | Grapheme_Cluster_Break (bits 0-3) | InCB << 4 (bits 4-5) |
  Extended_Pictographic << 6 | mark (Mn, Mc, Me: the spec's join) << 7. Sorted, so the DLL finds
  a code point by binary search.
* EMOJI_PRESENTATION: the (first, last) ranges of Emoji_Presentation=Yes.
* EMOJI_SEQUENCES: the FNV-1a hash (32 bits, over each code point's 4 little-endian bytes) of every
  RGI emoji sequence of more than one code point (keycaps, flags, tags, modifiers, ZWJ), sorted.
  A grapheme whose hash is here is drawn with the colour emoji font first.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import unicode_data as U  # noqa: E402

HEADER = ROOT / "native" / "common" / "unicode_grapheme_table.h"


def props(cp: int) -> int:
    return (U.gcb_map()(cp) | (U.incb_map()(cp) << 4) | (int(U.extended_pictographic(cp)) << 6)
            | (int(U.mark_map()(cp)) << 7))


def runs() -> list[tuple[int, int]]:
    """(first, value) of each run of equal props over 0..0x10FFFF (only the edges of the source
    ranges can start a run, so only those are looked at)."""
    edges = {0}
    for m in (U.gcb_map(), U.incb_map(), U.mark_map(),
              U.RangeMap([(a, b, True) for a, b, f in U._records("emoji-data.txt")
                          if f[0] == "Extended_Pictographic"])):
        for first, last, _v in m:
            edges.add(first)
            if last + 1 <= 0x10FFFF:
                edges.add(last + 1)
    out: list[tuple[int, int]] = []
    for cp in sorted(edges):
        v = props(cp)
        if not out or out[-1][1] != v:
            out.append((cp, v))
    return out


def fnv(seq: str) -> int:
    h = 0x811C9DC5
    for ch in seq:
        for b in ord(ch).to_bytes(4, "little"):
            h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def emoji_hashes() -> list[int]:
    hashes = sorted({fnv(s) for s in U.emoji_sequences() if len(s) > 1})
    return hashes


def presentation_ranges() -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for first, last, f in U._records("emoji-data.txt"):
        if f[0] != "Emoji_Presentation":
            continue
        if out and out[-1][1] + 1 == first:
            out[-1] = (out[-1][0], last)
        else:
            out.append((first, last))
    return sorted(out)


def _rows(values: list[str], per: int = 8) -> str:
    return "\n".join("    " + " ".join(values[i:i + per]) for i in range(0, len(values), per))


def render() -> str:
    r = runs()
    pres = presentation_ranges()
    hashes = emoji_hashes()
    return (
        "/* unicode_grapheme_table.h -- made by scripts/build_unicode18_tables.py from data/unicode\n"
        f"   (Unicode {U.VERSION}); do not edit. See native/common/unicode_grapheme.h. */\n"
        "#ifndef FTFP_UNICODE_GRAPHEME_TABLE_H\n#define FTFP_UNICODE_GRAPHEME_TABLE_H\n\n"
        f"#define UNICODE_VERSION_TEXT \"{U.VERSION}\"\n\n"
        "/* THE name limit: every name box takes up to this many bytes as stored (the write rule,\n"
        "   unicode_utf8.h game_encode), no character cap (src/unicode_data.py NAME_BOX_BYTES) */\n"
        f"#define NAME_BOX_BYTES {U.NAME_BOX_BYTES}\n\n"
        "/* (first << 8) | GCB | InCB << 4 | Extended_Pictographic << 6 | mark << 7, one per run */\n"
        f"#define GB_RANGE_COUNT {len(r)}\n"
        "static const unsigned int GB_RANGES[GB_RANGE_COUNT] = {\n"
        + _rows([f"0x{(cp << 8) | v:08X}," for cp, v in r]) + "\n};\n\n"
        "/* Emoji_Presentation=Yes: first, last */\n"
        f"#define EMOJI_PRESENTATION_COUNT {len(pres)}\n"
        "static const unsigned int EMOJI_PRESENTATION[EMOJI_PRESENTATION_COUNT][2] = {\n"
        + _rows([f"{{0x{a:05X}, 0x{b:05X}}}," for a, b in pres], 4) + "\n};\n\n"
        "/* FNV-1a of each RGI emoji sequence of two or more code points, sorted */\n"
        f"#define EMOJI_SEQUENCE_COUNT {len(hashes)}\n"
        "static const unsigned int EMOJI_SEQUENCES[EMOJI_SEQUENCE_COUNT] = {\n"
        + _rows([f"0x{h:08X}u," for h in hashes]) + "\n};\n\n#endif\n"
    )


def main() -> int:
    text = render()
    if sys.argv[1:] == ["--check"]:
        current = HEADER.read_bytes().decode("utf-8").replace("\r\n", "\n") if HEADER.is_file() else ""
        if current != text:
            print(f"{HEADER} is not up to date: run scripts/build_unicode18_tables.py")
            return 1
        print("up to date")
        return 0
    if sys.argv[1:]:
        raise SystemExit(__doc__)
    HEADER.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {HEADER}: {text.count(chr(10))} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
