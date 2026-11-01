"""Text Maker: any text in the games' own bitmap fonts, drawn exactly as the games draw it.
Pure Python (the patcher ships no Pillow or numpy): pictures are picture_image.Image, and
letters the fonts lack are drawn by Windows (text_raster.py: DirectWrite and Direct2D).

THE GAMES' FONTS.  Both games use the same font engine (Fish Tycoon 0x402350 / 0x402510,
Plant Tycoon 0x402300 / 0x4024E0): a white picture of the letters (anti-aliased in its alpha)
and a table in the executable of 20-byte records {char, x0, y0, x1, y1}, ended by char 0.

* Fish Tycoon loads three, in its font manager (0x4180B0): paddington_tt_18 (font 0, the
  default text font, table 0x458580), paddington_tt_30 (font 1, titles, 0x458DC8) and
  FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT (font 2, hints and labels, 0x4544B8), the pictures in
  Assets\\ft.dat (an Images folder file of the same name wins).
* Plant Tycoon loads one: PTfontsmall (0x412D9F, table 0x47A550), Images\\PTfontsmall.png.
  Its Images folder also holds PTfontbig.png and ldwarialbold.png, which the game never
  loads (no table for them): the Text Maker offers them too, their letters found by the
  empty columns between them and drawn with 2 pixels between letters.

HOW THE GAME DRAWS (Fish 0x4087E0, Plant 0x408E20, the same code):
* The loader (0x402510 / 0x4024E0) takes the line height from the first record (y1 - y0),
  re-lays records that run past the picture's right edge onto the next row (height + 1 down)
  and makes a 256-entry index: each byte's first record, and record 0 for a byte with none.
* Each byte of the text (read as signed, then masked to 0-255 by the lookup 0x4028C0) is
  looked up; a newline goes back to the start x and down one line height. A record with
  x1 == x0 draws nothing and does not move on. Otherwise the record's rectangle is blitted
  with its top-left at (x, y), and x moves on by (x1 - x0) + the font's spacing (0 for all
  four fonts).
* The colour (0xAARRGGBB): alpha byte 0 means the default colour (white in both games);
  white draws the picture as it is; any other colour draws a copy of the picture whose
  pixels are ANDed with SDL_MapRGBA(r, g, b, 255) (0x402730 / 0x402700): each channel is
  `pixel & colour`, the alpha kept.
* The blit is SDL's per-pixel-alpha blit; on an opaque screen each channel becomes
  d + ((s - d) * a >> 8), computed two channels at a time as SDL's BlitRGBtoRGBPixelAlpha
  does (alpha 0 skips the pixel, 255 copies it).

LETTERS A FONT LACKS are made "patcher-made", in order:
1. composed from the font's own pixels: the base letter plus the accent taken from the
   font itself (from its own accented letters, e.g. the dots of its "a umlaut", or its
   spacing accents ´ ` ^ ¨ ~ ¸ ¯ °; an acute is its grave mirrored), placed as the font
   places its own accents (a capital is made a little shorter when the line has no room);
2. drawn by Windows (DirectWrite: Segoe UI first, then the font that has the letter:
   Segoe UI Historic, Symbol and Emoji, the CJK fonts, Nirmala UI, Ebrima, Noto...),
   sized to the game font's capital height, set on its baseline, in the weight nearest its
   stroke, in white with its alpha steps, so the game's colours apply to it the same way;
   colour emoji keep their colours, and joined emoji, skin tones and combining marks are
   shaped whole.
Every such letter is listed as "patcher-made" and kept in a cache per font.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import bisect
import functools
import os
from pathlib import Path
import struct
import unicodedata
import zipfile

from picture_image import Image
import text_raster

IMAGE_BASE = 0x400000

GAME_TITLES = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}
EXE_NAMES = {"fish": "Fish Tycoon.exe", "plant": "Plant Tycoon.exe"}


@dataclass(frozen=True)
class FontSpec:
    key: str             # the picture's file name without ".png"
    label: str
    table: int | None    # the glyph table's address in the executable (None: not loaded by the game)
    chars: str = ""      # for a font without a table: its letters in picture order
    splits: tuple = ()   # (segment index, letters in it) where letters touch in the picture


FONTS = {
    "fish": (
        FontSpec("paddington_tt_18", "Paddington 18 (the game's main text font)", 0x458580),
        FontSpec("paddington_tt_30", "Paddington 30 (titles)", 0x458DC8),
        FontSpec("font_triplex_sanslightlin_bold_16pt", "Triplex Sans Bold 16 (labels and hints)", 0x4544B8),
    ),
    "plant": (
        FontSpec("PTfontsmall", "PT Font Small (the game's text font)", 0x47A550),
        FontSpec("PTfontbig", "PT Font Big (in the game's folder, not used by the game)", None,
                 "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789$!\",.?/`:-"
                 "ÄäÖöÜüß'ÉéÍíÓóúñ¿¡àÀâÂèêÊîÎôûùç«»", ((18, 2), (43, 2), (94, 3))),
        FontSpec("ldwarialbold", "LDW Arial Bold (in the game's folder, not used by the game)", None,
                 "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!\u2019\u201d,.?/':-"),
    ),
}

# The games' own text colours (0xRRGGBB): the default (white: both games' [0x45427C] /
# [0x47A27C]), and the yellow and black the patcher's own lines and shadows use.
GAME_COLOURS = (
    ("White (the games' default)", 0xFFFFFF),
    ("Yellow (buttons and hover)", 0xFFD040),
    ("Black (shadows)", 0x000000),
    ("Green", 0x40FF40),
    ("Red", 0xFF4040),
)

EFFECTS = ("None", "Shadow", "Outline")


# --------------------------------------------------------------------------- pixels


def alpha_of(image: Image) -> bytes:
    return bytes(image.data[3::4])


def ink(image: Image) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the pixels with any alpha, or None."""
    return image.bbox()


def white(width: int, height: int, alpha: bytes) -> Image:
    """A white picture with this alpha (the games' font pictures are white)."""
    out = Image(width, height)
    out.data[0::4] = out.data[1::4] = out.data[2::4] = b"\xff" * (width * height)
    out.data[3::4] = alpha
    return out


def blank(width: int, height: int) -> Image:
    return Image(max(0, width), max(0, height))


def paste_max(dst: Image, src: Image, x: int, y: int) -> None:
    """src's alpha laid into dst (white) at (x, y), keeping the larger alpha."""
    for yy in range(max(0, y), min(dst.height, y + src.height)):
        for xx in range(max(0, x), min(dst.width, x + src.width)):
            a = src.data[((yy - y) * src.width + (xx - x)) * 4 + 3]
            at = (yy * dst.width + xx) * 4
            if a > dst.data[at + 3]:
                dst.data[at:at + 4] = bytes((255, 255, 255, a))


def column_weights(image: Image) -> list[int]:
    a = image.data[3::4]
    w = image.width
    return [sum(a[x::w]) for x in range(w)]


def quantise_table(levels) -> bytes:
    """A 256-entry table taking any alpha to the nearest of the font's own alpha steps."""
    steps = sorted(set(int(v) for v in levels) | {0})
    out = bytearray(256)
    for v in range(256):
        i = bisect.bisect_left(steps, v)
        if i == 0:
            out[v] = steps[0]
        elif i >= len(steps):
            out[v] = steps[-1]
        else:
            lo, hi = steps[i - 1], steps[i]
            out[v] = lo if v - lo <= hi - v else hi
    return bytes(out)


# --------------------------------------------------------------------------- reading


def _pe_offset(exe: bytes, address: int) -> int | None:
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    count = struct.unpack_from("<H", exe, pe + 6)[0]
    optional = struct.unpack_from("<H", exe, pe + 20)[0]
    for i in range(count):
        header = pe + 24 + optional + i * 40
        _vsize, rva, raw_size, raw = struct.unpack_from("<IIII", exe, header + 8)
        if rva <= address - IMAGE_BASE < rva + raw_size:
            return raw + address - IMAGE_BASE - rva
    return None


def read_table(exe: bytes, address: int) -> list[list[int]]:
    """The executable's {char, x0, y0, x1, y1} records up to the char-0 end (at most 0x400)."""
    at = _pe_offset(exe, address)
    if at is None:
        raise ValueError(f"no glyph table at {address:#x}")
    records = []
    while len(records) < 0x400 and at + 20 <= len(exe):
        record = list(struct.unpack_from("<5i", exe, at))
        if record[0] == 0:
            return records
        records.append(record)
        at += 20
    raise ValueError(f"the glyph table at {address:#x} has no end")


def relayout(records: list[list[int]], width: int) -> tuple[list[list[int]], int]:
    """The loader's pass over the records (Fish 0x402648, Plant 0x402618): the line height
    from the first record, and records past the picture's right edge moved down a row."""
    records = [list(r) for r in records]
    height = records[0][4] - records[0][2] if records else 0
    dx = dy = 0
    for index, rec in enumerate(records):
        if index >= 0x100:
            break
        rec[3] -= dx
        rec[1] -= dx
        rec[2] += dy
        rec[4] += dy
        if rec[3] > width:
            dx += rec[1]
            dy += height + 1
            rec[3] -= rec[1]
            rec[1] = 0
            rec[2] += height + 1
            rec[4] += height + 1
    return records, height


def byte_index(records: list[list[int]]) -> list[int]:
    """Each byte's record: the first with that char (negative chars as their low byte),
    else record 0 (the loader's map at +0x1C)."""
    index = [0] * 256
    seen = set()
    for i, rec in enumerate(records):
        code = rec[0] & 0xFF if rec[0] < 0 else rec[0]
        if 0 <= code < 256 and code not in seen:
            seen.add(code)
            index[code] = i
    return index


def _runs(flags) -> list[tuple[int, int]]:
    runs, i, n = [], 0, len(flags)
    while i < n:
        if flags[i]:
            start = i
            while i < n and flags[i]:
                i += 1
            runs.append((start, i))
        else:
            i += 1
    return runs


def _segments(sheet: Image) -> list[tuple[int, int, int, int]]:
    """Letters in a picture without a table: bands of rows with ink, then runs of columns."""
    a = sheet.data[3::4]
    w, h = sheet.width, sheet.height
    rows = [any(a[y * w:(y + 1) * w]) for y in range(h)]
    bands = _runs(rows)
    if len(bands) == 1:
        bands = [(0, h)]
    segments = []
    for top, bottom in bands:
        cols = [any(a[y * w + x] for y in range(top, bottom)) for x in range(w)]
        segments.extend((x0, top, x1, bottom) for x0, x1 in _runs(cols))
    return segments


def _split(sheet: Image, seg: tuple, parts: int) -> list[tuple]:
    """A run of touching letters cut at its faintest columns."""
    x0, y0, x1, y1 = seg
    weight = column_weights(sheet.sub(x0, y0, x1 - x0, y1 - y0))
    width = x1 - x0
    cuts = []
    for k in range(1, parts):
        guess = width * k // parts
        lo, hi = max(1, guess - width // (2 * parts)), min(width - 1, guess + width // (2 * parts))
        cuts.append(min(range(lo, hi + 1), key=lambda c: weight[c]))
    edges = [0, *cuts, width]
    return [(x0 + edges[i], y0, x0 + edges[i + 1], y1) for i in range(parts)]


# --------------------------------------------------------------------------- the font


@dataclass
class Glyph:
    """A letter ready to draw: straight RGBA pixels (white, or an emoji's colours) the font's
    line height tall, the distance x moves on, and where it came from."""
    pixels: Image
    advance: int
    source: str                        # "game", or how a patcher-made letter was made
    rect: tuple | None = None          # the game record's rectangle (game letters)
    coloured: bool = False             # a colour emoji: drawn in its own colours, not tinted

    @property
    def generated(self) -> bool:
        return self.source != "game"


@dataclass
class GameFont:
    game: str
    spec: FontSpec
    sheet: Image
    records: list                      # re-laid records
    line_height: int
    spacing: int = 0
    in_game: bool = True
    index: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)      # letters beyond Latin-1 (fonts without a table)
    cache: dict = field(default_factory=dict)      # cluster -> Glyph (patcher-made)
    _metrics: dict | None = None
    _boxes: set | None = None
    _levels: bytes | None = None

    @property
    def label(self) -> str:
        return self.spec.label

    @property
    def key(self) -> str:
        return self.spec.key

    def record_for_byte(self, byte: int) -> list[int]:
        return self.records[self.index[byte & 0xFF]]

    @property
    def boxes(self) -> set:
        """The records that are only an empty box (paddington_tt_18 and _30 draw one for the
        letters they lack: % * + < = > [ \\ ] ^ { | } ~)."""
        if self._boxes is None:
            self._boxes = {i for i, rec in enumerate(self.records) if _is_box(self.sheet, rec)}
        return self._boxes

    def has_byte(self, byte: int) -> bool:
        """The font really has this byte: a record of its own that is not an empty box."""
        i = self.index[byte]
        rec = self.records[i]
        code = rec[0] & 0xFF if rec[0] < 0 else rec[0]
        return code == byte and i not in self.boxes

    def game_glyph(self, byte: int) -> Glyph:
        """What the game draws for a byte (its record, or record 0 for a byte it lacks)."""
        x0, y0, x1, y1 = self.record_for_byte(byte)[1:]
        return Glyph(self.sheet.sub(x0, y0, x1 - x0, y1 - y0), x1 - x0, "game", (x0, y0, x1, y1))

    def char_glyph(self, ch: str) -> Glyph | None:
        """The font's own letter for one character, if it has it."""
        if len(ch) != 1:
            return None
        if ch in self.extra:
            x0, y0, x1, y1 = self.extra[ch][1:]
            return Glyph(self.sheet.sub(x0, y0, x1 - x0, y1 - y0), x1 - x0, "game", (x0, y0, x1, y1))
        code = ord(ch)
        if code < 0x20 or code > 0xFF:
            return None
        return self.game_glyph(code) if self.has_byte(code) else None

    @property
    def metrics(self) -> dict:
        if self._metrics is None:
            self._metrics = _measure(self)
        return self._metrics

    @property
    def quantise(self) -> bytes:
        if self._levels is None:
            self._levels = quantise_table(set(self.sheet.data[3::4]))
        return self._levels


def _is_box(sheet: Image, rec) -> bool:
    x0, y0, x1, y1 = rec[1:]
    if x1 - x0 < 3:
        return False
    piece = sheet.sub(x0, y0, x1 - x0, y1 - y0)
    box = ink(piece)
    if box is None:
        return False
    l, t, r, b = box
    w, h = r - l, b - t
    if h < 6 or w < 5:
        return False
    a = piece.data[3::4]
    pw = piece.width

    def on(x, y):
        return a[y * pw + x] > 96
    border = all(on(x, t) and on(x, b - 1) for x in range(l, r)) and all(on(l, y) and on(r - 1, y) for y in range(t, b))
    hollow = not any(a[y * pw + x] > 32 for y in range(t + 2, b - 2) for x in range(l + 2, r - 2))
    return border and hollow


def _measure(font: GameFont) -> dict:
    def ink_of(ch):
        g = font.char_glyph(ch)
        return (g, ink(g.pixels)) if g is not None else (None, None)

    h = font.line_height
    _g, cap = ink_of("H")
    if cap is None:
        _g, cap = ink_of("E")
    cap_top, baseline = (cap[1], cap[3]) if cap else (h // 5, h * 4 // 5)
    _g, xb = ink_of("x")
    x_top = xb[1] if xb else (cap_top + baseline) // 2
    stem = max(1.0, (baseline - cap_top) / 7)
    for ch in "lI|":
        g, box = ink_of(ch)
        if g is not None and box is not None:
            a = g.pixels.data[3::4]
            w = g.pixels.width
            rows = [sum(a[y * w:(y + 1) * w]) / 255 for y in range(box[1], box[3])]
            stem = sum(rows) / len(rows)
            break
    bearings = []
    for ch in "HNOnoabde":
        g, box = ink_of(ch)
        if g is not None and box is not None:
            bearings.append((box[0], g.pixels.width - box[2]))
    left = round(sum(b[0] for b in bearings) / len(bearings)) if bearings else 1
    right = round(sum(b[1] for b in bearings) / len(bearings)) if bearings else 1
    g = font.char_glyph(" ")
    space = g.advance if g is not None else max(3, (baseline - cap_top) // 3)
    return {"cap_top": cap_top, "baseline": baseline, "x_top": x_top, "cap": baseline - cap_top,
            "stem": stem, "left": left, "right": right, "space": space}


# --------------------------------------------------------------------------- loading


def _read_art(folder: Path, game: str, name: str) -> bytes | None:
    """A font picture as the game finds it: Images\\<name> (Plant always; Fish first),
    then Fish Tycoon's Assets\\ft.dat (a ZIP)."""
    images = folder / "Images"
    if images.is_dir():
        for path in images.iterdir():
            if path.name.lower() == name.lower():
                return path.read_bytes()
    if game == "fish":
        dat = folder / "Assets" / "ft.dat"
        if dat.is_file():
            with zipfile.ZipFile(dat) as archive:
                names = {n.lower(): n for n in archive.namelist() if not n.startswith("__MACOSX")}
                if name.lower() in names:
                    return archive.read(names[name.lower()])
    return None


def find_game_folder(game: str, candidates) -> Path | None:
    """The first candidate that is a copy of the game with its fonts."""
    for folder in candidates:
        if not folder or not str(folder).strip():
            continue
        folder = Path(str(folder).strip().strip('"'))
        try:
            if (folder / EXE_NAMES[game]).is_file() and _read_art(folder, game, FONTS[game][0].key + ".png"):
                return folder
        except (OSError, zipfile.BadZipFile):
            continue
    return None


def load_fonts(game: str, folder: Path) -> list[GameFont]:
    """Every font of the game in `folder` (a game copy: vanilla or patched)."""
    folder = Path(folder)
    exe = (folder / EXE_NAMES[game]).read_bytes()
    fonts = []
    for spec in FONTS[game]:
        data = _read_art(folder, game, spec.key + ".png")
        if data is None:
            continue
        sheet = Image.from_png(data)
        if spec.table is not None:
            records, height = relayout(read_table(exe, spec.table), sheet.width)
            font = GameFont(game, spec, sheet, records, height)
        else:
            font = _untabled_font(game, spec, sheet)
        font.index = byte_index(font.records)
        fonts.append(font)
    return fonts


def _untabled_font(game: str, spec: FontSpec, sheet: Image) -> GameFont:
    segments = _segments(sheet)
    splits = dict(spec.splits)
    rects = []
    for i, seg in enumerate(segments):
        rects.extend(_split(sheet, seg, splits[i]) if i in splits else [seg])
    height = max(r[3] - r[1] for r in rects)
    records = [[ord(ch), x0, y0, x1, y0 + height] for ch, (x0, y0, x1, _y1) in zip(spec.chars, rects)]
    # Cut tight in the picture, so drawn with 2 pixels between letters.
    font = GameFont(game, spec, sheet, [r for r in records if r[0] <= 0xFF], height, spacing=2, in_game=False)
    font.extra = {chr(r[0]): r for r in records if r[0] > 0xFF}
    return font


# --------------------------------------------------------------------------- clusters

ZWJ = "\u200d"


def _is_mark(ch: str) -> bool:
    return unicodedata.category(ch) in ("Mn", "Me", "Mc")


def _is_regional(ch: str) -> bool:
    return 0x1F1E6 <= ord(ch) <= 0x1F1FF


def _is_extender(ch: str) -> bool:
    o = ord(ch)
    return (_is_mark(ch) or 0xFE00 <= o <= 0xFE0F or 0x1F3FB <= o <= 0x1F3FF or 0xE0020 <= o <= 0xE007F
            or 0xE0100 <= o <= 0xE01EF)


def clusters(text: str) -> list[str]:
    """User-perceived characters (grapheme clusters): a letter with its combining marks,
    variation selectors, skin tones and tags; emoji joined by ZWJ; regional-indicator
    pairs (flags); CR LF."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        j = i + 1
        if ch == "\r" and j < n and text[j] == "\n":
            out.append("\r\n")
            i = j + 1
            continue
        if ch == "\n":
            out.append(ch)
            i = j
            continue
        if _is_regional(ch) and j < n and _is_regional(text[j]):
            j += 1
        while j < n:
            if _is_extender(text[j]):
                j += 1
            elif text[j] == ZWJ and j + 1 < n and text[j + 1] != "\n":
                j += 2
            elif text[j] == ZWJ:
                j += 1
            else:
                break
        out.append(text[i:j])
        i = j
    return out


# --------------------------------------------------------------------------- Windows fonts

FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
FALLBACK_CHAIN = (
    ("segoeui.ttf", "Segoe UI"), ("seguihis.ttf", "Segoe UI Historic"), ("seguisym.ttf", "Segoe UI Symbol"),
    ("seguiemj.ttf", "Segoe UI Emoji"), ("YuGothM.ttc", "Yu Gothic"), ("msgothic.ttc", "MS Gothic"),
    ("msyh.ttc", "Microsoft YaHei"), ("simsun.ttc", "SimSun"), ("malgun.ttf", "Malgun Gothic"),
    ("Nirmala.ttc", "Nirmala UI"), ("Nirmala.ttf", "Nirmala UI"), ("ebrima.ttf", "Ebrima"),
    ("LeelawUI.ttf", "Leelawadee UI"), ("gadugi.ttf", "Gadugi"), ("javatext.ttf", "Javanese Text"),
    ("mmrtext.ttf", "Myanmar Text"), ("taile.ttf", "Microsoft Tai Le"), ("ntailu.ttf", "Microsoft New Tai Lue"),
    ("himalaya.ttf", "Microsoft Himalaya"), ("monbaiti.ttf", "Mongolian Baiti"), ("msyi.ttf", "Microsoft Yi Baiti"),
    ("phagspa.ttf", "Microsoft PhagsPa"), ("sylfaen.ttf", "Sylfaen"), ("cambria.ttc", "Cambria Math"),
    ("arialuni.ttf", "Arial Unicode MS"),
)
EMOJI_FAMILY = "Segoe UI Emoji"


def _cmap_ranges(path: Path) -> list[tuple[int, int]]:
    """The code points a TrueType/OpenType font (or a .ttc's first font) maps, as sorted
    (first, last) ranges, from its cmap (format 12 preferred, else format 4)."""
    data = path.read_bytes()
    offset = struct.unpack_from(">I", data, 12)[0] if data[:4] == b"ttcf" else 0
    num = struct.unpack_from(">H", data, offset + 4)[0]
    cmap = None
    for i in range(num):
        tag, _sum, at, _len = struct.unpack_from(">4sIII", data, offset + 12 + 16 * i)
        if tag == b"cmap":
            cmap = at
    if cmap is None:
        return []
    best = None
    for i in range(struct.unpack_from(">H", data, cmap + 2)[0]):
        platform, _encoding, sub = struct.unpack_from(">HHI", data, cmap + 4 + 8 * i)
        fmt = struct.unpack_from(">H", data, cmap + sub)[0]
        rank = {12: 2, 4: 1}.get(fmt, 0) if platform in (0, 3) else 0
        if rank and (best is None or rank > best[0]):
            best = (rank, cmap + sub, fmt)
    if best is None:
        return []
    _rank, at, fmt = best
    ranges = []
    if fmt == 12:
        for g in range(struct.unpack_from(">I", data, at + 12)[0]):
            first, last, _glyph = struct.unpack_from(">III", data, at + 16 + 12 * g)
            ranges.append((first, last))
    else:
        segs = struct.unpack_from(">H", data, at + 6)[0] // 2
        ends = struct.unpack_from(f">{segs}H", data, at + 14)
        starts = struct.unpack_from(f">{segs}H", data, at + 16 + 2 * segs)
        ranges.extend((first, last) for first, last in zip(starts, ends) if first != 0xFFFF)
    ranges.sort()
    return ranges


@functools.lru_cache(maxsize=None)
def _coverage(file: str) -> tuple[list[int], list[int]]:
    path = FONT_DIR / file
    try:
        ranges = _cmap_ranges(path) if path.is_file() else []
    except (OSError, struct.error):
        ranges = []
    return [r[0] for r in ranges], [r[1] for r in ranges]


def font_has(file: str, code: int) -> bool:
    firsts, lasts = _coverage(file)
    i = bisect.bisect_right(firsts, code) - 1
    return i >= 0 and code <= lasts[i]


@functools.lru_cache(maxsize=None)
def fallback_files() -> tuple[tuple[str, str], ...]:
    chain = [(f, n) for f, n in FALLBACK_CHAIN if (FONT_DIR / f).is_file()]
    if FONT_DIR.is_dir():
        for path in sorted(FONT_DIR.glob("Noto*")):
            if path.suffix.lower() in (".ttf", ".otf", ".ttc"):
                chain.append((path.name, _family_name(path) or path.stem))
    return tuple(chain)


def _family_name(path: Path) -> str | None:
    """A font file's family name (name table, ID 1, Windows Unicode)."""
    try:
        data = path.read_bytes()
        offset = struct.unpack_from(">I", data, 12)[0] if data[:4] == b"ttcf" else 0
        for i in range(struct.unpack_from(">H", data, offset + 4)[0]):
            tag, _s, at, _l = struct.unpack_from(">4sIII", data, offset + 12 + 16 * i)
            if tag == b"name":
                count, strings = struct.unpack_from(">HH", data, at + 2)
                for k in range(count):
                    pid, eid, lang, nid, length, off = struct.unpack_from(">6H", data, at + 6 + 12 * k)
                    if pid == 3 and nid == 1 and lang == 0x409:
                        return data[at + strings + off:at + strings + off + length].decode("utf-16-be")
    except (OSError, struct.error, UnicodeDecodeError):
        return None
    return None


def is_emoji(cluster: str) -> bool:
    for ch in cluster:
        o = ord(ch)
        if (0x1F000 <= o <= 0x1FAFF or o == 0xFE0F or 0x1F1E6 <= o <= 0x1F1FF
                or (0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF) and "\ufe0f" in cluster):
            return True
    return False


def family_for(cluster: str) -> str:
    """The Windows font to draw a cluster with: the first in the chain that has all its
    visible characters (Segoe UI Emoji first for emoji); DirectWrite falls back from there
    for anything it still lacks."""
    needed = [ord(c) for c in cluster if not _is_extender(c) and c != ZWJ]
    if is_emoji(cluster):
        return EMOJI_FAMILY
    chain = fallback_files()
    for file, name in chain:
        if all(font_has(file, c) for c in needed):
            return name
    for file, name in chain:
        if needed and font_has(file, needed[0]):
            return name
    return "Segoe UI"


# --------------------------------------------------------------------------- patcher-made letters

SS = 4          # drawn 4 times larger, then averaged down (smooth edges like the game's)
WEIGHTS = (300, 400, 600, 700, 900)


@functools.lru_cache(maxsize=None)
def _family_measures(family: str, weight: int) -> tuple[float, float]:
    """A Windows font's capital height and stem width per pixel of size ('H' and 'l')."""
    size = 100
    r = text_raster.raster("H", family, size, weight)
    box = _raster_ink(r)
    cap = (box[3] - box[1]) / size if box else 0.7
    r = text_raster.raster("l", family, size, weight)
    box = _raster_ink(r)
    if not box:
        return cap, 0.09
    a = r.bgra[3::4]
    total = sum(a[box[1] * r.width:box[3] * r.width])
    return cap, total / 255 / (box[3] - box[1]) / size


def _raster_ink(r) -> tuple[int, int, int, int] | None:
    a = r.bgra[3::4]
    w = r.width
    top = bottom = None
    left, right = w, 0
    for y in range(r.height):
        row = a[y * w:(y + 1) * w]
        stripped = row.lstrip(b"\0")
        if stripped:
            if top is None:
                top = y
            bottom = y + 1
            left = min(left, w - len(stripped))
            right = max(right, len(row.rstrip(b"\0")))
    return None if top is None else (left, top, right, bottom)


def _downsample(r, x0: int, y0: int, width: int, height: int) -> tuple[Image, bool]:
    """The 4x drawing's piece at (x0, y0), width x height in final pixels, averaged down
    (premultiplied, so edges stay clean). Returns straight RGBA and whether it has colour."""
    out = Image(width, height)
    src, rw, rh = r.bgra, r.width, r.height
    coloured = False
    n = SS * SS
    for y in range(height):
        for x in range(width):
            b = g = rr = a = 0
            for sy in range(SS):
                yy = y0 + y * SS + sy
                if not 0 <= yy < rh:
                    continue
                base = yy * rw
                for sx in range(SS):
                    xx = x0 + x * SS + sx
                    if 0 <= xx < rw:
                        p = (base + xx) * 4
                        b += src[p]
                        g += src[p + 1]
                        rr += src[p + 2]
                        a += src[p + 3]
            if a:
                at = (y * width + x) * 4
                alpha = (a + n // 2) // n
                if alpha == 0:
                    continue
                cr, cg, cb = min(255, rr * 255 // a), min(255, g * 255 // a), min(255, b * 255 // a)
                if abs(cr - cg) > 8 or abs(cg - cb) > 8:
                    coloured = True
                out.data[at:at + 4] = bytes((cr, cg, cb, alpha))
    return out, coloured


def draw_windows(font: GameFont, text: str, family: str | None = None) -> Glyph:
    """Text drawn by Windows in the game font's style, the font's line height tall, its ink
    on the font's baseline and within the line."""
    m = font.metrics
    h = font.line_height
    family = family or family_for(text)
    emoji = family == EMOJI_FAMILY
    cap_ratio, _stem = _family_measures("Segoe UI", 400)
    size = m["cap"] * SS / cap_ratio if not emoji else (m["cap"] + 4) * SS
    weight = 400
    if not emoji:
        target = m["stem"] * SS
        weight = min(WEIGHTS, key=lambda w: abs(_family_measures("Segoe UI", w)[1] * size - target))
    r = text_raster.raster(text, family, size, weight)
    box = _raster_ink(r)
    if box is None:
        return _space(font, " ")
    # the raster's baseline goes on the font's baseline
    top_in_cell = box[1] - r.baseline + m["baseline"] * SS
    bottom_in_cell = box[3] - r.baseline + m["baseline"] * SS
    shift = 0
    if bottom_in_cell - top_in_cell > h * SS:
        return _scaled_to_line(font, text, family, size, weight)
    if top_in_cell < 0:
        shift = -top_in_cell
    elif bottom_in_cell > h * SS:
        shift = h * SS - bottom_in_cell
    cell_top = round(r.baseline - m["baseline"] * SS - shift)
    left = box[0] - m["left"] * SS
    width = -(-(box[2] + m["right"] * SS - left) // SS)
    pixels, coloured = _downsample(r, left, cell_top, max(1, width), h)
    if not coloured:
        pixels = white(pixels.width, pixels.height, alpha_of(pixels).translate(font.quantise))
    return Glyph(pixels, pixels.width, f"drawn by Windows ({family}) in the font's style"
                 + (", colour emoji" if coloured else ""), coloured=coloured)


def _scaled_to_line(font: GameFont, text: str, family: str, size: float, weight: int) -> Glyph:
    """A drawing taller than the line: drawn smaller until it fits."""
    for factor in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4):
        r = text_raster.raster(text, family, size * factor, weight)
        box = _raster_ink(r)
        if box and box[3] - box[1] <= font.line_height * SS:
            m = font.metrics
            top = box[1] - r.baseline + m["baseline"] * SS
            bottom = box[3] - r.baseline + m["baseline"] * SS
            shift = -top if top < 0 else (font.line_height * SS - bottom if bottom > font.line_height * SS else 0)
            cell_top = round(r.baseline - m["baseline"] * SS - shift)
            left = box[0] - m["left"] * SS
            width = -(-(box[2] + m["right"] * SS - left) // SS)
            pixels, coloured = _downsample(r, left, cell_top, max(1, width), font.line_height)
            if not coloured:
                pixels = white(pixels.width, pixels.height, alpha_of(pixels).translate(font.quantise))
            return Glyph(pixels, pixels.width, f"drawn by Windows ({family}) in the font's style, made smaller "
                         "to fit the line" + (", colour emoji" if coloured else ""), coloured=coloured)
    return _missing_box(font, text)


# combining mark -> (name, the spacing forms to look for in the font, a spacing form for Windows)
MARKS = {
    "\u0300": ("grave", "`", "\u02cb"), "\u0301": ("acute", "\u00b4", "\u02ca"),
    "\u0302": ("circumflex", "^", "\u02c6"), "\u0303": ("tilde", "~", "\u02dc"),
    "\u0304": ("macron", "\u00af", "\u02c9"), "\u0306": ("breve", "", "\u02d8"),
    "\u0307": ("dot above", "", "\u02d9"), "\u0308": ("diaeresis", "\u00a8", "\u00a8"),
    "\u030a": ("ring", "\u00b0", "\u02da"), "\u030b": ("double acute", "", "\u02dd"),
    "\u030c": ("caron", "", "\u02c7"), "\u0327": ("cedilla", "\u00b8", "\u00b8"),
    "\u0328": ("ogonek", "", "\u02db"), "\u0323": ("dot below", ".", "."),
    "\u0326": ("comma below", ",", ","), "\u0331": ("macron below", "_", "\u02cd"),
    "\u0324": ("diaeresis below", "", "\u00a8"), "\u0325": ("ring below", "", "\u02da"),
    "\u032d": ("circumflex below", "", "\u02c6"), "\u0330": ("tilde below", "", "\u02dc"),
}
MARKS_BY_NAME = {v[0]: (v[1], v[2]) for v in MARKS.values()}
BELOW = {"cedilla", "ogonek", "dot below", "comma below", "macron below", "diaeresis below", "ring below",
         "circumflex below", "tilde below"}
# Accented letters whose accent can be lifted off the font's own pixels: mark -> letters.
MARK_SOURCES = {
    "diaeresis": "äÄöÖüÜëËïÏÿ", "acute": "éÉáÁíÍóÓúÚýÝ", "grave": "èÈàÀìÌòÒùÙ",
    "circumflex": "êÊâÂîÎôÔûÛ", "tilde": "ñÑãÃõÕ", "ring": "åÅ", "cedilla": "çÇ",
}


def _crop_ink(image: Image, rows: tuple[int, int] | None = None) -> Image | None:
    piece = image if rows is None else image.sub(0, rows[0], image.width, rows[1] - rows[0])
    box = ink(piece)
    if box is None:
        return None
    a = alpha_of(piece.sub(box[0], box[1], box[2] - box[0], box[3] - box[1]))
    return white(box[2] - box[0], box[3] - box[1], a)


def _own_mark(font: GameFont, name: str, upper: bool) -> Image | None:
    for accented in sorted(MARK_SOURCES.get(name, ""), key=lambda c: c.isupper() != upper):
        g = font.char_glyph(accented)
        base = font.char_glyph(unicodedata.normalize("NFD", accented)[0])
        if g is None or base is None:
            continue
        bink = ink(base.pixels)
        if bink is None:
            continue
        rows = (bink[3], g.pixels.height) if name in BELOW else (0, bink[1])
        if rows[1] > rows[0]:
            mark = _crop_ink(g.pixels, rows)
            if mark is not None:
                return mark
    for ch in MARKS_BY_NAME.get(name, ("", ""))[0]:
        g = font.char_glyph(ch)
        if g is not None:
            mark = _crop_ink(g.pixels)
            if mark is not None:
                return mark
    return None


def _mark_from_font(font: GameFont, name: str, upper: bool) -> Image | None:
    """An accent lifted from the font's own pixels: from one of its accented letters (the
    rows above the plain letter's ink), else its spacing accent; an acute is the font's
    grave mirrored (and the other way round) when it has only one of them."""
    mark = _own_mark(font, name, upper)
    if mark is None and name in ("acute", "grave"):
        other = _own_mark(font, "grave" if name == "acute" else "acute", upper)
        if other is not None:
            mark = other.flipped()
    return mark


def _gap_above(font: GameFont, upper: bool) -> int:
    """How far the font sets its accents above its letters (its own accented letters)."""
    for accented in ("ÄÖÜÉÀ" if upper else "äöüéà"):
        g = font.char_glyph(accented)
        base = font.char_glyph(unicodedata.normalize("NFD", accented)[0])
        if g is None or base is None:
            continue
        bink = ink(base.pixels)
        if bink is None or bink[1] == 0:
            continue
        mark = ink(g.pixels.sub(0, 0, g.pixels.width, bink[1]))
        if mark is not None:
            return max(0, bink[1] - mark[3])
    return 1 if upper else 2


def _drawn_mark(font: GameFont, name: str) -> Image | None:
    """An accent drawn by Windows in the font's style (no accent of its own to use)."""
    spacing = MARKS_BY_NAME.get(name, ("", ""))[1]
    if not spacing:
        return None
    return _crop_ink(draw_windows(font, spacing, "Segoe UI").pixels)


def _dotless(font: GameFont, ch: str) -> Glyph | None:
    """ı and ȷ: the font's i and j without their dot (the ink above the x-height)."""
    base = font.char_glyph({"ı": "i", "ȷ": "j"}[ch])
    if base is None:
        return None
    px = base.pixels.copy()
    rows = max(0, font.metrics["x_top"] - 1)
    for y in range(min(rows, px.height)):
        px.data[y * px.width * 4 + 3:(y + 1) * px.width * 4:4] = bytes(px.width)
    return Glyph(px, base.advance, f"made from the font's own {'i' if ch == 'ı' else 'j'} without its dot")


def _squash(px: Image, top: int, short: int, table: bytes) -> tuple[Image, int]:
    """The letter's ink made `-short` rows shorter (at most a third), kept on its bottom."""
    box = ink(px)
    height = box[3] - top
    new = max(height - height // 3, height + short)
    if new >= height:
        return px, top
    part = px.sub(0, top, px.width, height).resized(px.width, new)
    out = px.copy()
    for y in range(top, box[3]):
        out.data[y * px.width * 4 + 3:(y + 1) * px.width * 4:4] = bytes(px.width)
    squeezed = white(part.width, part.height, alpha_of(part).translate(table))
    paste_max(out, squeezed, 0, box[3] - new)
    return out, box[3] - new


def _widen(px: Image, extra: int) -> Image:
    out = Image(px.width + extra, px.height)
    for y in range(px.height):
        src = y * px.width * 4
        dst = (y * out.width + extra // 2) * 4
        out.data[dst:dst + px.width * 4] = px.data[src:src + px.width * 4]
    return out


def _compose(font: GameFont, cluster: str) -> Glyph | None:
    """A letter with accents from the font's own base letter and accents."""
    nfd = unicodedata.normalize("NFD", cluster)
    base_ch, marks = nfd[0], nfd[1:]
    if not marks or not all(m in MARKS for m in marks):
        return None
    above = [m for m in marks if MARKS[m][0] not in BELOW]
    if base_ch in "ij" and above:          # i and j lose their dot under an accent
        base = _dotless(font, "ı" if base_ch == "i" else "ȷ")
    else:
        base = font.char_glyph(base_ch) or font.cache.get(base_ch)
    if base is None or base.coloured:
        return None
    px = base.pixels.copy()
    upper = base_ch.isupper() or base_ch in "bdfhklt"
    how = []
    box = ink(px)
    if box is None:
        return None
    top = box[1]
    for m in marks:
        name = MARKS[m][0]
        mark = _mark_from_font(font, name, upper)
        source = "the font's own"
        if mark is None:
            mark = _drawn_mark(font, name)
            source = "a Windows-drawn"
        if mark is None:
            return None
        how.append(f"{source} {name}")
        if mark.width > px.width:
            px = _widen(px, mark.width - px.width)
            box = ink(px)
        if base_ch in "ij":
            weights = column_weights(px)
            cx = weights.index(max(weights)) + 0.5
        else:
            cx = (box[0] + box[2]) / 2
        x = min(max(0, int(round(cx - mark.width / 2))), px.width - mark.width)
        h = px.height
        if name in BELOW:
            y = font.metrics["baseline"] - (1 if name in ("cedilla", "ogonek") else -1)
            y = max(0, min(y, h - mark.height))
            if y + mark.height > h:
                mark = mark.sub(0, 0, mark.width, h - y)
        else:
            gap = _gap_above(font, upper)
            if top - gap - mark.height < 0:
                # No room above (a capital in a short line): the letter is made shorter,
                # standing on its baseline, so the accent fits over it.
                px, top = _squash(px, top, top - gap - mark.height, font.quantise)
                if top - gap - mark.height < 0:
                    gap = min(gap, 1)
                    keep = max(1, top - gap)
                    mark = mark.sub(0, mark.height - keep, mark.width, keep)
            y = max(0, top - gap - mark.height)
            top = y
        paste_max(px, mark, x, y)
    advance = px.width if px.width != base.pixels.width else base.advance
    return Glyph(px, advance, f"made from the font's own {base_ch} + " + " + ".join(how))


def _is_space(cluster: str) -> bool:
    return len(cluster) == 1 and (unicodedata.category(cluster) == "Zs" or cluster == "\t")


def _space(font: GameFont, cluster: str) -> Glyph:
    m = font.metrics
    width = {"\t": 4 * m["space"], "\u3000": m["cap"] + m["left"] + m["right"] + 4,
             "\u2003": m["cap"] + 4, "\u2002": (m["cap"] + 4) // 2}.get(cluster, m["space"])
    return Glyph(blank(width, font.line_height), width, "a space the font's width")


def _missing_box(font: GameFont, cluster: str) -> Glyph:
    m = font.metrics
    w = max(4, m["cap"] * 2 // 3)
    px = Image(w + 2, font.line_height)
    t, b = m["cap_top"], m["baseline"]
    for x in range(1, w + 1):
        for y in (t, b - 1):
            px.data[(y * px.width + x) * 4:(y * px.width + x) * 4 + 4] = b"\xff\xff\xff\xff"
    for y in range(t, b):
        for x in (1, w):
            px.data[(y * px.width + x) * 4:(y * px.width + x) * 4 + 4] = b"\xff\xff\xff\xff"
    return Glyph(px, w + 2, "no font on this PC has it: an empty box")


def make_glyph(font: GameFont, cluster: str) -> Glyph:
    """A patcher-made letter for a cluster the font lacks (cached per font)."""
    if cluster in font.cache:
        return font.cache[cluster]
    glyph = None
    if cluster in ("ı", "ȷ"):
        glyph = _dotless(font, cluster)
    if glyph is None:
        glyph = _compose(font, cluster)
    if glyph is None and _is_space(cluster):
        glyph = _space(font, cluster)
    if glyph is None:
        try:
            glyph = draw_windows(font, cluster)
        except text_raster.RasterError:
            glyph = None
    if glyph is None:
        glyph = _missing_box(font, cluster)
    font.cache[cluster] = glyph
    return glyph


def is_zero_width(cluster: str) -> bool:
    return all(c == ZWJ or _is_extender(c) or unicodedata.category(c) in ("Cf", "Cc") for c in cluster)


def glyph_for(font: GameFont, cluster: str, generate: bool = True) -> Glyph | None:
    """The letter to draw for a cluster: the game's own, else patcher-made (None: nothing).
    With `generate` off, what the game itself draws: the character as a Latin-1 byte ("?"
    when it has none) through the font's table."""
    if cluster in ("\n", "\r\n", "\r") or cluster != "\t" and is_zero_width(cluster):
        return None
    own = font.char_glyph(cluster)
    if own is not None:
        return own
    if not generate:
        byte = cluster[0].encode("latin-1", "replace")[0] if cluster else 0x3F
        return font.game_glyph(byte)
    return make_glyph(font, cluster)


# --------------------------------------------------------------------------- drawing


def _and_table(value: int) -> bytes:
    return bytes(v & value for v in range(256))


def tint(image: Image, colour: int) -> Image:
    """The game's colour: each channel ANDed with the colour's (0x402730), alpha kept; white
    leaves the picture as it is."""
    colour &= 0xFFFFFF
    if colour == 0xFFFFFF:
        return image
    out = image.copy()
    out.data[0::4] = out.data[0::4].translate(_and_table((colour >> 16) & 0xFF))
    out.data[1::4] = out.data[1::4].translate(_and_table((colour >> 8) & 0xFF))
    out.data[2::4] = out.data[2::4].translate(_and_table(colour & 0xFF))
    return out


def sdl_blend(dst: Image, src: Image, x: int, y: int) -> None:
    """SDL's per-pixel-alpha blit onto an opaque screen (BlitRGBtoRGBPixelAlpha), in place:
    alpha 0 skips, 255 copies, else two channels at a time d + ((s - d) * a >> 8)."""
    sd, dd = src.data, dst.data
    for yy in range(max(0, y), min(dst.height, y + src.height)):
        s = ((yy - y) * src.width + max(0, x) - x) * 4
        d = (yy * dst.width + max(0, x)) * 4
        for _ in range(max(0, x), min(dst.width, x + src.width)):
            a = sd[s + 3]
            if a == 255:
                dd[d], dd[d + 1], dd[d + 2] = sd[s], sd[s + 1], sd[s + 2]
            elif a:
                sw = (sd[s] << 16) | (sd[s + 1] << 8) | sd[s + 2]
                dw = (dd[d] << 16) | (dd[d + 1] << 8) | dd[d + 2]
                s1, d1 = sw & 0xFF00FF, dw & 0xFF00FF
                d1 = (d1 + ((((s1 - d1) & 0xFFFFFFFF) * a & 0xFFFFFFFF) >> 8)) & 0xFF00FF
                s2, d2 = sw & 0xFF00, dw & 0xFF00
                d2 = (d2 + ((((s2 - d2) & 0xFFFFFFFF) * a & 0xFFFFFFFF) >> 8)) & 0xFF00
                out = d1 | d2
                dd[d], dd[d + 1], dd[d + 2] = (out >> 16) & 0xFF, (out >> 8) & 0xFF, out & 0xFF
            s += 4
            d += 4


@dataclass
class Placed:
    glyph: Glyph
    cluster: str
    x: int
    y: int


def layout(font: GameFont, text: str, generate: bool = True) -> tuple[list[Placed], int, int]:
    """Where each letter goes, as the game's draw loop places them: x moves on by the
    letter's width plus the font's spacing; a newline goes back to x 0 and down a line.
    Returns the letters and the text's width and height."""
    placed: list[Placed] = []
    x = y = width = 0
    lines = 1
    for cluster in clusters(text):
        if cluster in ("\n", "\r\n", "\r"):
            x = 0
            y += font.line_height
            lines += 1
            continue
        glyph = glyph_for(font, cluster, generate)
        if glyph is None or glyph.pixels.width == 0:
            continue
        placed.append(Placed(glyph, cluster, x, y))
        width = max(width, x + glyph.pixels.width)
        x += glyph.advance + font.spacing
    return placed, width, lines * font.line_height


def render(font: GameFont, text: str, colour: int = 0xFFFFFF, effect: str = "None", scale: int = 1,
           background: tuple | None = None, generate: bool = True, margin: int = 2) -> Image:
    """The text as the game draws it. `background` (r, g, b) draws onto an opaque colour with
    SDL's blend; None gives a transparent picture. The shadow is the text in black one pixel
    right and down, drawn first (as the patcher's DLLs and Plant Tycoon's labels draw it);
    the outline is the black text at the eight pixels around."""
    placed, width, height = layout(font, text, generate)
    pad = margin + (1 if effect != "None" else 0)
    canvas = Image(max(1, width + 2 * pad), max(1, height + 2 * pad))
    if background is not None:
        r, g, b = background
        canvas.data[:] = bytes((r, g, b, 255)) * (canvas.width * canvas.height)
        put = sdl_blend
    else:
        put = lambda dst, src, x, y: dst.draw(src, x, y)   # noqa: E731  straight-alpha "over"
    offsets = {"Shadow": [(1, 1)], "Outline": [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]}
    for dx, dy in offsets.get(effect, []):
        for p in placed:
            put(canvas, tint(p.glyph.pixels, 0x000000), pad + p.x + dx, pad + p.y + dy)
    for p in placed:
        put(canvas, p.glyph.pixels if p.glyph.coloured else tint(p.glyph.pixels, colour), pad + p.x, pad + p.y)
    return canvas.scaled(scale) if scale > 1 else canvas


def render_game_bytes(font: GameFont, text: bytes, colour: int, screen: Image, x: int, y: int) -> None:
    """The game's draw loop on raw bytes onto an opaque screen, as 0x4087E0 does it: every
    byte through the index, records with no width skipped, SDL's blend."""
    start = x
    for byte in text:
        if byte == 0x0A:
            x = start
            y += font.line_height
            continue
        glyph = font.game_glyph(byte)
        if glyph.advance == 0:
            continue
        sdl_blend(screen, tint(glyph.pixels, colour), x, y)
        x += glyph.advance + font.spacing


def generated_in(font: GameFont, text: str) -> list[tuple[str, str]]:
    """The patcher-made letters a text uses: (cluster, how it was made), each once."""
    seen, out = set(), []
    for cluster in clusters(text):
        g = glyph_for(font, cluster)
        if g is not None and g.generated and cluster not in seen:
            seen.add(cluster)
            out.append((cluster, g.source))
    return out


def describe(cluster: str) -> str:
    """'U+00E9 LATIN SMALL LETTER E WITH ACUTE' (each code point of a cluster)."""
    return " + ".join(f"U+{ord(ch):04X} {unicodedata.name(ch, '')}".rstrip() for ch in cluster)


def parse_unicode(entry: str) -> str:
    """What the "type any Unicode" box means: "U+1F600", "1F600", "0x1F600", "\\u00e9",
    "&#233;", several separated by spaces, a character name ("LATIN SMALL LETTER E WITH
    ACUTE"), or the characters themselves."""
    text = entry.strip()
    if not text:
        return ""
    try:
        return unicodedata.lookup(text)
    except KeyError:
        pass
    out = []
    for token in text.replace(",", " ").split():
        if token.startswith("&#") and not token.lower().startswith("&#x"):
            try:
                out.append(chr(int(token[2:].rstrip(";"))))
                continue
            except ValueError:
                return text
        t = token
        for prefix in ("U+", "u+", "0x", "0X", "\\u", "\\U", "&#x", "&#X"):
            if t.startswith(prefix):
                t = t[len(prefix):].rstrip(";")
                break
        try:
            value = int(t, 16)
        except ValueError:
            return text
        if not (0 <= value <= 0x10FFFF) or 0xD800 <= value <= 0xDFFF:
            return text
        out.append(chr(value))
    return "".join(out)


# The accent picker: common letters with diacritics, by language.
ACCENTS = (
    ("French", "àâæçéèêëîïôœùûüÿ"),
    ("German", "äöüß"),
    ("Spanish & Portuguese", "áéíñóúü¿¡ãõâêôà"),
    ("Italian", "àèéìíîòóùú"),
    ("Nordic", "åäæøöðþ"),
    ("Turkish", "çğıİöşü"),
    ("Polish", "ąćęłńóśźż"),
    ("Czech & Slovak", "áčďéěíňóřšťúůýžĺľô"),
    ("Hungarian & Romanian", "őűăâîșț"),
    ("Baltic", "āčēģīķļņšūžėįųõ"),
    ("Vietnamese", "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"),
    ("Symbols", "€£¥¢©®™°±×÷½¼¾…–—‘’“”«»•†‡§¶"),
)
