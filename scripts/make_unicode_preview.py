"""Draw the Unicode preview sheet: for each game font (Fish Tycoon's Paddington 18 and 30 and Triplex Sans
Bold 16, Plant Tycoon's PT Font Small), rows of text as "Render Unicode with In-Game Fonts" draws them:
the game's own letters, the patcher-made ones, letters from the fallback chain for sample scripts, the
fonts the patcher ships, and the missing-glyph box.

    python scripts/make_unicode_preview.py ["<output.png>"]

Every row is drawn by the real code: Unicode Text.dll (rebuilt from its source) and the game's own font
loader and draw run in Unicorn against the vanilla executables (tests/font_draw_emulator.py), and each
letter the DLL asks Windows for is made by the DLL's own raster_glyph / raster_cluster, run natively in
the game font's style with Windows' fonts and the bundled ones (tests/native_glyphs.py); a line's bidi
levels are the DLL's own line_levels (Windows' Uniscribe), run natively too. Needs Windows,
the pinned MSVC toolset, Unicorn and the vanilla games (tests/test_unicode_text.py).
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from picture_image import Image  # noqa: E402
import text_raster  # noqa: E402

OUT = Path.home() / "Downloads" / "Unicode preview sheet.png"
SCALE = 2
BACKGROUND = (24, 40, 72)
WHITE = 0xFFFFFFFF
LABEL_W = 330

# (label, text); "!box" rows draw with no font found (the missing-glyph box)
ROWS = (
    ("The game's own letters", "Fish Tycoon 2024: Player ABC xyz $15"),
    ("Patcher-made (Latin-1, Windows-1252)", "Zoë Ñúñez · Œuvre € ¿Qué? «ß»"),
    ("Latin accents (NFC + fallback)", "Ăą Ćč Đđ Őő Łł Ŵŵ İı ǅ ẞ"),
    ("Combining marks (e + U+0301 ...)", "Renée Ärger ño"),
    ("Greek", "Ελληνικά αβγ ΩΣ"),
    ("Cyrillic", "Кириллица Жж Щщ"),
    ("Arabic (shaped, right to left)", "مرحبا بالعالم"),
    ("Hebrew (right to left)", "שלום עולם"),
    ("Devanagari (shaped)", "नमस्ते दुनिया"),
    ("Thai", "สวัสดีครับ"),
    ("Chinese and Japanese", "中文 日本語 ひらがな"),
    ("Korean", "한국어 가나다"),
    ("Bidi: a mixed line (UAX #9 order)", "Fish مرحبا 123 שלום Tycoon"),
    ("Bidi: numbers in right-to-left text", "שלום 1234 עולם · מחיר 12.5% · مرحبا ١٢٣"),
    ("Emoji (in colour)", "🐟🌻 👨‍👩‍👧 👍🏽 ❤️"),
    ("Flags (Twemoji Mozilla)", "🇯🇵 🇺🇸 🇫🇷 🇧🇷 🇺🇦 🏴󠁧󠁢󠁥󠁮󠁧󠁿 "
                                "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    ("Bundled: Tangut, cuneiform, Unicode 18", "𗀀𗀁 𒀀𒀁 \U0003D000"),
    ("Missing-glyph box (no font has it)", "!box"),
)


def label_image(text: str, size: int = 14, colour=(230, 230, 230)) -> Image:
    r = text_raster.raster(text, "Segoe UI", size, 600)
    out = Image(r.width, r.height)
    for i in range(r.width * r.height):
        a = r.bgra[i * 4 + 3]
        if a:
            out.data[i * 4:i * 4 + 4] = bytes((*colour, a))
    return out


def crop_row(screen: Image, x0: int, y0: int, w: int, h: int) -> Image:
    return screen.sub(x0, y0, w, h)


def draw_font_rows(game: str, font_index: int, server, fonts_present: bool = True) -> tuple[str, list[tuple[str, Image]]]:
    import test_unicode_text as T
    import test_unicode_names as N
    dll, symbols = T.built(game)
    fde = T.fde.FontDrawEmulator(game, screen_w=1400, screen_h=80, dll=dll, symbols=symbols)
    N.Game(game, emu=fde.emu)
    emu = fde.emu
    va, key = T.FONT_SITES[game][font_index]
    push = bytes(emu.uc.mem_read(va, 10))
    table, name_at = struct.unpack_from("<I", push, 1)[0], struct.unpack_from("<I", push, 6)[0]
    name = emu.cstring(name_at).decode("ascii")
    font = fde.load_font_at(name_at, table, (T.ASSETS[game] / "Images" / f"{name}.png").read_bytes())
    inner = emu.read32(font + 4)
    height = emu.read32(inner + 4)
    server.pen(font_index, height)
    state = {"none": False}

    def put(e, piece, w_at, xoff_at, adv_at, coverage) -> int:
        if state["none"] or piece.kind == 0:
            return 0
        e.uc.mem_write(coverage, piece.data)
        e.write32(w_at, piece.w)
        e.write32(xoff_at, piece.xoff & 0xFFFFFFFF)
        e.write32(adv_at, piece.adv)
        return piece.kind

    def glyph(e) -> int:
        cp, _h, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(6))
        return put(e, server.raster([cp]), w_at, xoff_at, adv_at, coverage)

    def cluster(e) -> int:
        cps_at, n, _h, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(7))
        cps = [e.read32(cps_at + 4 * k) for k in range(n)]
        rtl = e.read32(symbols["_piece_rtl"])           # a right-to-left run of a line: shaped so natively too
        if rtl:
            server.poke("piece_rtl", 1)
        try:
            return put(e, server.raster(cps), w_at, xoff_at, adv_at, coverage)
        finally:
            if rtl:
                server.poke("piece_rtl", 0)

    def line_levels(e) -> int:
        units_at, n, levels_at = e.arg(0), e.arg(1), e.arg(2)
        raw = bytes(e.uc.mem_read(units_at, 2 * n))
        levels = server.levels(raw.decode("utf-16-le", "surrogatepass"))
        if levels is None:
            return 0
        e.uc.mem_write(levels_at, bytes(levels))
        return 1

    emu.hook(symbols["_raster_glyph"], glyph, 0)
    emu.hook(symbols["_raster_cluster"], cluster, 0)
    emu.hook(symbols["_line_levels"], line_levels, 0)
    rows = []
    for label, text in ROWS:
        state["none"] = text == "!box"
        raw = ("Fish \U000E0000\U000F1234 Tycoon" if text == "!box" else text).encode("utf-8")
        at = emu.alloc(len(raw) + 1)
        emu.uc.mem_write(at, raw + b"\0")
        width = emu.call(N.GAMES[game]["width"], at, N.f32(1.0), ecx=font)
        fde.fill(BACKGROUND)
        emu.call(N.GAMES[game]["draw"], at, 6, 4, WHITE, font, ecx=fde.impl)
        image = crop_row(fde.screen_image, 0, 0, min(1400, max(40, width + 14)), height + 8)
        rows.append((label, image))
    title = {"paddington_tt_18": "Fish Tycoon: Paddington 18 (main text)",
             "paddington_tt_30": "Fish Tycoon: Paddington 30 (titles)",
             "font_triplex_sanslightlin_bold_16pt": "Fish Tycoon: Triplex Sans Bold 16 (labels)",
             "PTfontsmall": "Plant Tycoon: PT Font Small (all text)"}[key]
    return title, rows


def main() -> int:
    import native_glyphs as NG
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    sections = []
    for game, count in (("fish", 3), ("plant", 1)):
        server = NG.GlyphServer(game)
        try:
            for index in range(count):
                sections.append(draw_font_rows(game, index, server))
        finally:
            server.close()
    pieces = []
    total_h, total_w = 16, 0
    head = label_image("Unicode Text.dll: what Render Unicode with In-Game Fonts draws (the DLL's and the games' own "
                       "drawing code; 2x)", 18, (255, 255, 255))
    pieces.append((head, 16, total_h))
    total_h += head.height + 12
    for title, rows in sections:
        t = label_image(title, 16, (255, 214, 102))
        pieces.append((t, 16, total_h))
        total_h += t.height + 4
        for label, image in rows:
            lab = label_image(label, 13)
            big = image.scaled(SCALE)
            row_h = max(lab.height, big.height)
            pieces.append((lab, 24, total_h + (row_h - lab.height) // 2))
            pieces.append((big, LABEL_W, total_h))
            total_w = max(total_w, LABEL_W + big.width + 16)
            total_h += row_h + 2
        total_h += 14
    sheet = Image(max(total_w, head.width + 32), total_h)
    sheet.data[:] = bytes((16, 24, 40, 255)) * (sheet.width * sheet.height)
    for picture, x, y in pieces:
        sheet.draw(picture, x, y)
    out.write_bytes(sheet.to_png())
    print(f"{out} ({sheet.width} x {sheet.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
