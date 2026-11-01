"""Build the "Render Unicode with In-Game Fonts" fonts: each game font with every Latin-1
letter it lacks added, patcher-made in its own style (src/text_maker.py).

    python scripts/build_unicode_assets.py ["<folder with Fish Tycoon and Plant Tycoon>"]

For every font the games load (Fish Tycoon's paddington_tt_18, paddington_tt_30 and
FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT, Plant Tycoon's PTfontsmall) it writes

* assets/<game>_tycoon_unicode/Images/<font>_unicode.png: the game's font picture, unchanged,
  with rows of patcher-made letters added below it (the same width, so the game's loader lays
  out its own records exactly as before); and
* native/ftfp_<game>_unicode/unicode_fonts.h: the font's table for the DLL, the game's own
  records (in order, so the loader's re-layout and its line height are the same) and one record
  per added letter after them, placed so that after the loader's pass (Fish 0x402648, Plant
  0x402618: records past the right edge move down a row, everything after them with them) each
  lands on its letter. A record the game has only as an empty box (paddington's % * + < = > [ \\
  ] ^ { | } ~) keeps its place in the table but gets char 0x100 + its byte, which the loader's
  byte index (0x4026AB) never matches, so the byte's added letter is found instead.

The letters filled in: every byte of Windows-1252 the font lacks -- printable ASCII, Latin-1
(U+00A0-U+00FF, what the games' text boxes take) and the Windows-1252 letters at 0x80-0x9F
(€ ‚ ƒ „ … † ‡ ˆ ‰ Š ‹ Œ Ž ' ' " " • – — ˜ ™ š › œ ž Ÿ), which text written by the Translations
setting in Windows-1252 uses. The five bytes Windows-1252 leaves undefined (0x81 0x8D 0x8F 0x90
0x9D) stay as the game has them (its record 0).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from picture_image import Image  # noqa: E402
import text_maker  # noqa: E402

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
GAME_FOLDERS = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}
ASSETS = {"fish": ROOT / "assets" / "fish_tycoon_unicode", "plant": ROOT / "assets" / "plant_tycoon_unicode"}
HEADERS = {"fish": ROOT / "native" / "ftfp_fish_unicode" / "unicode_fonts.h",
           "plant": ROOT / "native" / "ftfp_plant_unicode" / "unicode_fonts.h"}
# The C names of each font's table and picture name in the header.
C_NAMES = {"paddington_tt_18": "paddington_18", "paddington_tt_30": "paddington_30",
           "font_triplex_sanslightlin_bold_16pt": "triplex_16", "PTfontsmall": "ptfontsmall"}
# The name the game asks for (its own spelling) and the picture this adds.
GAME_NAMES = {"paddington_tt_18": "paddington_tt_18", "paddington_tt_30": "paddington_tt_30",
              "font_triplex_sanslightlin_bold_16pt": "FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT",
              "PTfontsmall": "PTfontsmall"}
GAP = 1                 # pixels between added letters (and above each added row)


def unicode_name(key: str) -> str:
    return GAME_NAMES[key] + "_unicode"


CP1252_UNDEFINED = (0x81, 0x8D, 0x8F, 0x90, 0x9D)


def char_of(byte: int) -> str:
    """The letter a byte stands for in the games' text: Windows-1252 (Latin-1 from 0xA0)."""
    return bytes([byte]).decode("cp1252")


def wanted_bytes() -> list[int]:
    return [b for b in range(0x20, 0x100) if b != 0x7F and b not in CP1252_UNDEFINED]


def missing_bytes(font: text_maker.GameFont) -> list[int]:
    return [b for b in wanted_bytes() if not font.has_byte(b)]


def loader_shift(raw: list[list[int]], width: int) -> tuple[int, int]:
    """(dx, dy) the loader's pass has reached after the game's own records: added records
    are stored that much right and up so they land where they are drawn."""
    height = raw[0][4] - raw[0][2]
    dx = dy = 0
    for index, rec in enumerate(raw):
        if index >= 0x100:
            break
        x0, x1 = rec[1] - dx, rec[3] - dx
        if x1 > width:
            dx += x0
            dy += height + 1
    return dx, dy


def glyph_pixels(glyph: text_maker.Glyph, height: int) -> Image:
    """The added letter as the game will draw it: its record is `advance` wide."""
    px = glyph.pixels
    out = Image(glyph.advance, height)
    for row in range(min(height, px.height)):
        n = min(px.width, glyph.advance) * 4
        out.data[row * out.width * 4: row * out.width * 4 + n] = px.data[row * px.width * 4: row * px.width * 4 + n]
    return out


def extend_font(font: text_maker.GameFont, raw: list[list[int]]) -> tuple[Image, list[list[int]], list[tuple]]:
    """The extended picture, the DLL's table (raw, before the loader's pass) and what was added:
    (byte, x0, y0, x1, y1 as drawn, how it was made)."""
    sheet, width, height = font.sheet, font.sheet.width, font.line_height
    added: list[tuple] = []
    x, y = 0, sheet.height + GAP
    pieces = []
    for byte in missing_bytes(font):
        # The soft hyphen shows as the font's own hyphen (a name is never broken at it).
        glyph = font.char_glyph("-") if byte == 0xAD else None
        glyph = glyph or text_maker.make_glyph(font, char_of(byte))
        px = glyph_pixels(glyph, height)
        if px.width > width:
            raise SystemExit(f"{font.key}: {char_of(byte)!r} is wider than the picture")
        if x + px.width > width:
            x, y = 0, y + height + GAP
        pieces.append((px, x, y))
        added.append((byte, x, y, x + px.width, y + height, glyph.source))
        x += px.width + GAP
    out = Image(width, y + height)
    out.data[:len(sheet.data)] = sheet.data          # the game's own picture, byte for byte
    for px, gx, gy in pieces:
        for row in range(px.height):
            start = ((gy + row) * width + gx) * 4
            out.data[start:start + px.width * 4] = px.data[row * px.width * 4:(row + 1) * px.width * 4]
    table = [list(r) for r in raw]
    regenerated = {b for b, *_ in added}
    for rec in table:
        code = rec[0] & 0xFF if rec[0] < 0 else rec[0]
        if code in regenerated:
            rec[0] = 0x100 + code              # the box: never found by the byte index
    if font.index[0] in [i for i, r in enumerate(table) if r[0] >= 0x100]:
        raise SystemExit(f"{font.key}: record 0 would be hidden")
    dx, dy = loader_shift(raw, width)
    if len(raw) + len(added) > 0x100:
        raise SystemExit(f"{font.key}: more than 256 records; the loader lays out only 256")
    for byte, x0, y0, x1, y1, _how in added:
        table.append([byte, x0 + dx, y0 - dy, x1 + dx, y1 - dy])
    check, _h = text_maker.relayout(table, width)
    for (byte, x0, y0, x1, y1, _how), rec in zip(added, check[len(raw):]):
        if rec != [byte, x0, y0, x1, y1]:
            raise SystemExit(f"{font.key}: {chr(byte)!r} would not land on its letter: {rec}")
    if [r[1:] for r in check[:len(raw)]] != [r[1:] for r in text_maker.relayout(raw, width)[0]]:
        raise SystemExit(f"{font.key}: the game's own records moved")
    return out, table, added


def header(game: str, fonts: list[tuple[text_maker.GameFont, list[list[int]], list[tuple], str]]) -> str:
    lines = [
        "/* Generated by scripts/build_unicode_assets.py from the vanilla game: do not edit.",
        "   Each font's table for the DLL: the game's own records, then one per added letter",
        "   (Images\\<font>_unicode.png, patcher-made in the font's style). The game's loader",
        "   re-lays these records in place, so the tables are writable. */",
        "",
    ]
    for font, table, added, digest in fonts:
        name = C_NAMES[font.key]
        lines.append(f"/* {font.key}: {len(table) - len(added)} game records, {len(added)} added; "
                     f"{unicode_name(font.key)}.png SHA-256 {digest} */")
        lines.append(f"static const char name_{name}[] = \"{unicode_name(font.key)}\";")
        lines.append(f"static int table_{name}[] = {{")
        for rec in table:
            note = ""
            if 0x100 <= rec[0] < 0x200:
                note = f"  /* {chr(rec[0] - 0x100)!r}: the game's empty box, hidden */"
            elif rec in table[len(table) - len(added):]:
                note = f"  /* 0x{rec[0]:02X} added (U+{ord(char_of(rec[0])):04X}) */"
            lines.append("    " + ", ".join(str(v) for v in rec) + "," + note)
        lines.append("    0, 0, 0, 0, 0")
        lines.append("};")
        lines.append("")
    return "\n".join(lines)


def build(game: str, folder: Path) -> list[str]:
    exe = (folder / text_maker.EXE_NAMES[game]).read_bytes()
    report = []
    built = []
    images = ASSETS[game] / "Images"
    images.mkdir(parents=True, exist_ok=True)
    for font in text_maker.load_fonts(game, folder):
        if not font.in_game or font.spec.table is None:
            continue
        raw = text_maker.read_table(exe, font.spec.table)
        picture, table, added = extend_font(font, raw)
        data = picture.to_png()
        (images / f"{unicode_name(font.key)}.png").write_bytes(data)
        digest = hashlib.sha256(data).hexdigest().upper()
        built.append((font, table, added, digest))
        report.append(f"{game} {font.key}: {len(added)} letters added, picture {picture.width}x{picture.height}")
        for byte, *_rect, how in added:
            report.append(f"    0x{byte:02X} {char_of(byte)!r}: {how}")
    HEADERS[game].parent.mkdir(parents=True, exist_ok=True)
    HEADERS[game].write_text(header(game, built) + "\n", encoding="utf-8", newline="\n")
    return report


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else VANILLA
    for game, name in GAME_FOLDERS.items():
        for line in build(game, root / name):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
