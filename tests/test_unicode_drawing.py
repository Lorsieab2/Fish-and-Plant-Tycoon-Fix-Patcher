"""Unicode Text.dll's drawing (both games), the shared Unicode spec's row 3: the glyph source order,
the fallback chain, the missing-glyph box, composition, whole-run shaping, and letters drawn in each
game font's style.

* In Unicorn (the DLL's and the game's own code; Windows' fonts stood in for by replacing the DLL's
  raster_glyph and raster_cluster):
  - a letter with a combining mark that NFC makes one letter is that letter: the game's own é for
    e + U+0301, pixel for pixel; one the font lacks is asked for as the one code point;
  - a run of a script that needs shaping (Arabic, Hebrew, Devanagari, Thai...) with the spaces
    between its words is asked for whole, once; when no font has it whole it is drawn a grapheme at
    a time;
  - the fallback chain is the spec's list in its order.
* Natively (tests/native_glyphs.py: the DLL's own pen_for_style, raster_glyph and raster_cluster with
  Windows' real fonts), Windows only:
  - a letter Windows draws for a game font stands on that font's baseline, is as tall as its
    capitals, and has its side bearings;
  - the chain picks Segoe UI Symbol for a symbol before the CJK fonts, Segoe UI Historic for
    cuneiform;
  - an Arabic run is joined (narrower than its letters drawn alone), a Hebrew run is right to left;
  - Use Unicode Font fits the chosen face's em to the game font's width of "The quick brown fox
    jumps over the lazy dog 0123456789", within 60%..130%.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_unicode_text as T  # noqa: E402
from test_unicode_text import needs  # noqa: E402

try:
    import test_unicode_glyphs as G
    import native_glyphs as NG
except ImportError:          # no Unicorn
    G = NG = None

ROOT = Path(__file__).resolve().parents[1]

SPEC_CHAIN = (
    "Segoe UI", "Segoe UI Historic", "Segoe UI Symbol", "Segoe UI Emoji", "Yu Gothic", "Meiryo", "Microsoft YaHei",
    "Microsoft JhengHei", "Malgun Gothic", "SimSun-ExtB", "Nirmala UI", "Ebrima", "Gadugi", "Leelawadee UI",
    "Myanmar Text", "Javanese Text", "Mongolian Baiti", "Microsoft Himalaya", "Microsoft Yi Baiti",
    "Microsoft New Tai Lue", "Microsoft Tai Le", "Microsoft PhagsPa", "Sylfaen", "Cambria Math", "Noto Sans",
    "Noto Sans Symbols", "Noto Sans Symbols 2", "Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Sans Math",
    "Noto Sans Cuneiform", "Noto Color Emoji",
)

ARABIC = "سلام عليكم"
HEBREW = "שלום עולם"
DEVANAGARI = "नमस्ते दुनिया"
THAI = "สวัสดี"


def dll_chain() -> list[str]:
    text = (ROOT / "native" / "common" / "unicode_glyphs.h").read_text(encoding="utf-8")
    body = text[text.index("static const wchar_t *const CHAIN[] = {"):]
    body = body[:body.index("};")]
    return re.findall(r'L"([^"]+)"', body)


class ChainTests(unittest.TestCase):
    def test_the_chain_is_the_spec_list_in_its_order(self) -> None:
        chain = dll_chain()
        self.assertEqual(tuple(chain[:len(SPEC_CHAIN)]), SPEC_CHAIN)
        # then the faces the DLL had before (kept) and the bundled fonts, Last Resort last
        self.assertEqual(chain[-1], "Last Resort")
        for kept in ("SimSun", "SimSun-ExtG", "MingLiU-ExtB", "Unifont", "Unifont Upper", "Noto Serif Tangut"):
            self.assertIn(kept, chain[len(SPEC_CHAIN):])
        self.assertEqual(len(chain), len(set(chain)))
        text = (ROOT / "native" / "common" / "unicode_glyphs.h").read_text(encoding="utf-8")
        self.assertIn(f"#define CHAIN_EMOJI {chain.index('Segoe UI Emoji')} ", text)

    def test_the_text_makers_chain_has_the_same_order(self) -> None:
        import text_maker
        names = list(dict.fromkeys(name for _file, name in text_maker.FALLBACK_CHAIN))
        order = [n for n in SPEC_CHAIN if n in names]
        self.assertEqual([n for n in names if n in SPEC_CHAIN], order)


class PieceCase:
    """The game's own draw with the DLL's, Windows' fonts stood in for."""
    game = "fish"

    def setUp(self) -> None:
        self.base = G.GlyphCase()
        self.base.game = self.game
        self.base.setUp()
        self.pieces: list[tuple[int, ...]] = []
        self.whole = True
        self.base.fde.emu.hook(self.base.symbols["_raster_cluster"], self._cluster, 0)

    def _cluster(self, e) -> int:
        cps_at, n, height, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(7))
        cps = tuple(e.read32(cps_at + 4 * k) for k in range(n))
        self.pieces.append(cps)
        if not self.whole:
            return 0
        w, xoff, adv = 3 + n, 0, 5 + n
        e.uc.mem_write(coverage, b"\xFF" * (w * height))
        e.write32(w_at, w)
        e.write32(xoff_at, xoff)
        e.write32(adv_at, adv)
        return 1

    def test_a_letter_and_its_mark_draw_as_the_games_own_letter(self) -> None:
        b = self.base
        for typed, own in (("Renée", "Renée".encode("latin-1")), ("Ärger", "Ärger".encode("latin-1")),
                           ("ñ", "ñ".encode("latin-1"))):
            with self.subTest(typed=typed):
                self.assertEqual(b.draw(typed.encode("utf-8")), b.draw(own, own=True))
                self.assertEqual(b.width(typed.encode("utf-8")), b.width(own, own=True))
        self.assertEqual(b.rasters, [])
        self.assertEqual(self.pieces, [])

    def test_a_composed_letter_the_font_lacks_is_asked_for_alone(self) -> None:
        b = self.base
        b.draw("ź".encode("utf-8"))           # ź U+017A
        self.assertIn((0x17A, b.height), b.rasters)
        self.assertEqual(self.pieces, [])

    def test_a_run_to_shape_is_asked_for_whole(self) -> None:
        b = self.base
        # (an Arabic run with its Arabic-Indic digits: tests/test_unicode_bidi.py, whole-line order)
        for run in (ARABIC, HEBREW, DEVANAGARI, THAI):
            with self.subTest(run=run):
                self.pieces.clear()
                shown = b.draw(("A " + run + " b").encode("utf-8"))
                self.assertIn(tuple(ord(c) for c in run), self.pieces)
                n = len(run)
                # drawn at the pen as one piece
                a_end = 5 + b.width(b"A ", own=True) + b.spacing
                b.fde.fill((10, 20, 30))
                b.draw(b"A ", own=True, fill=False)
                b.draw(b" b", own=True, x=a_end + 5 + n + b.spacing, fill=False)
                b.paint(a_end, 7, 3 + n, b.height)
                self.assertEqual(shown, bytes(b.fde.screen_image.data))
                self.assertEqual(b.width(("A " + run + " b").encode("utf-8")),
                                 b.width(b"A  b", own=True) + 5 + n + b.spacing)

    def test_spaces_join_a_run_only_inside_it(self) -> None:
        b = self.base
        b.draw("שלום  abc".encode("utf-8"))
        self.assertIn(tuple(ord(c) for c in "שלום"), self.pieces)
        self.assertNotIn(tuple(ord(c) for c in "שלום  "), self.pieces)

    def test_a_run_no_font_has_whole_is_drawn_a_grapheme_at_a_time(self) -> None:
        b = self.base
        self.whole = False
        b.draw("नमस्ते".encode("utf-8"))
        self.assertIn(tuple(ord(c) for c in "नमस्ते"), self.pieces)
        # then its graphemes: न, म, स्ते (a conjunct with its vowel sign) ...
        self.assertIn((ord("न"), b.height), b.rasters)


    def type_into(self, limit: int, chars: list[int], measured: bool = True) -> bytes:
        """Letters typed into a box of `limit` bytes through the game's own key handler, the box
        having measured its text with the game font first (as its draw does)."""
        b = self.base
        emu = b.fde.emu
        handler, events, changed = G.TypingCase.HANDLER[self.game]
        emu.hook(events, lambda e: 0x0BAD0000, 0)
        emu.hook(changed, lambda e: 0, 8)
        box, buffer = G.box_with(emu, limit)
        if measured:
            emu.call(b.symbols["_box_width"], b.font, box, 0, buffer, G.N.f32(1.0))
        for ch in chars:
            emu.call(handler, 5, 0, ch, ecx=box)
        return emu.cstring(buffer)

    def widest(self) -> int:
        b = self.base
        return max(b.width(bytes([c]), own=True) for c in range(0x21, 0x7F))

    def test_wide_letters_are_refused_in_a_box_that_is_not_a_name(self) -> None:
        """A registration or price box (8 bytes here): a letter is refused when the text would be
        wider than 8 of the font's widest plain letters, even with bytes to spare; plain letters,
        and a name box, are as before."""
        limit = 8
        most = limit * self.widest()
        self.base.fde.emu.hook(self.base.symbols["_raster_glyph"], self._wide_raster, 0)   # 100 px a letter
        self.assertTrue(100 <= most < 200 + self.base.spacing)
        # two letters are 6 bytes (room for them) but wider than the stock box allows: the second is refused
        self.assertEqual(self.type_into(limit, [0x3042, 0x3042]), "あ".encode("utf-8"))
        self.assertEqual(self.type_into(limit, [ord(c) for c in "WWWWWWWW"]), b"WWWWWWWW")
        # without a measure (no font known) the byte limit alone
        self.assertEqual(self.type_into(limit, [0x3042, 0x3042, 0x3042], measured=False),
                         "あ".encode("utf-8") * 2)
        # a name box scrolls instead
        name = self.type_into(G.T.unicode_data.NAME_BOX_BYTES, [0x3042] * 12)
        self.assertEqual(name, "あ".encode("utf-8") * 12)

    def _wide_raster(self, e) -> int:
        cp, height, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(6))
        e.uc.mem_write(coverage, b"\xFF" * (8 * height))
        e.write32(w_at, 8)
        e.write32(xoff_at, 0)
        e.write32(adv_at, 100)
        return 1


@needs("fish")
class FishPieceTests(PieceCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantPieceTests(PieceCase, unittest.TestCase):
    game = "plant"


# Item 16 (line breaking): neither game has a word wrapper. The engine's text measure (Fish 0x4023D0,
# Plant 0x402380) is called only by the layout of buttons, labels and text boxes, none of which looks at
# a space or a newline; the draw (Fish 0x4087E0, Plant 0x408E20) breaks a line only at "\n" (Fish
# 0x408874 cmp al, 0xA). So translations and names are broken only where their text has "\n", and the
# patcher's Time Warp popup is a Windows dialog, which Windows breaks itself. There is nothing to hook
# with UAX #14 line breaking.
MEASURES = {"fish": 0x4023D0, "plant": 0x402380}


def _callers_of(exe: bytes, target: int) -> list[tuple[int, int]]:
    """(start, end) file offsets of every function holding a call to `target` (bounded by int3 padding)."""
    import struct
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    count, opt = struct.unpack_from("<H", exe, pe + 6)[0], struct.unpack_from("<H", exe, pe + 20)[0]
    sections = [struct.unpack_from("<IIII", exe, pe + 24 + opt + 40 * i + 8) for i in range(count)]

    def va(o: int) -> int | None:
        for _vs, rva, size, raw in sections:
            if raw <= o < raw + size:
                return 0x400000 + rva + o - raw
        return None
    out = set()
    at = exe.find(b"\xE8")
    while at >= 0:
        here = va(at)
        if here is not None and here + 5 + struct.unpack_from("<i", exe, at + 1)[0] == target:
            start = at
            while start > 2 and not (exe[start - 1] == 0xCC and exe[start - 2] == 0xCC):
                start -= 1
            end = at
            while end < len(exe) - 1 and not (exe[end] == 0xCC and exe[end + 1] == 0xCC):
                end += 1
            out.add((start, end, va(start)))
        at = exe.find(b"\xE8", at + 1)
    return sorted(out)


class NoWordWrapperTests(unittest.TestCase):
    def test_neither_game_has_a_word_wrapper(self) -> None:
        try:
            import capstone
        except ImportError:
            self.skipTest("needs capstone")
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for game in ("fish", "plant"):
            if not T.EXES[game].is_file():
                continue
            exe = T.EXES[game].read_bytes()
            functions = _callers_of(exe, MEASURES[game])
            self.assertGreater(len(functions), 3)
            for start, end, address in functions:
                with self.subTest(game=game, function=hex(address)):
                    body = list(md.disasm(exe[start:end], address))
                    compares = [i for i in body if i.mnemonic == "cmp" and i.op_str.endswith((", 0x20", ", 0xa"))]
                    self.assertEqual(compares, [], "a measure next to a space or newline test: a wrapper?")


def _native_ready() -> bool:
    return NG is not None and NG.available() and T._ready("fish") and T._ready("plant")


def gdi_extent(face: str, em: int, weight: int, text: str) -> int:
    """GetTextExtentPoint32W of `text` in `face` at em `em` (what fit_em measures)."""
    gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32
    gdi32.CreateFontW.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.GetTextExtentPoint32W.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p)
    gdi32.DeleteObject.argtypes = (ctypes.c_void_p,)
    gdi32.DeleteDC.argtypes = (ctypes.c_void_p,)
    dc = gdi32.CreateCompatibleDC(None)
    font = gdi32.CreateFontW(-em, 0, 0, 0, weight, 0, 0, 0, 1, 7, 0, 4, 0, face)
    old = gdi32.SelectObject(dc, font)
    size = (ctypes.c_long * 2)()
    gdi32.GetTextExtentPoint32W(dc, text, len(text), size)
    gdi32.SelectObject(dc, old)
    gdi32.DeleteObject(font)
    gdi32.DeleteDC(dc)
    del user32
    return size[0]


@unittest.skipUnless(os.name == "nt" and _native_ready(), "needs Windows, the pinned MSVC toolset, Unicorn and the games")
class NativeDrawingTests(unittest.TestCase):
    servers: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.servers = {game: NG.GlyphServer(game) for game in ("fish", "plant")}

    @classmethod
    def tearDownClass(cls) -> None:
        for server in cls.servers.values():
            server.close()

    def styles(self):
        for game, server in self.servers.items():
            for key in [k for _va, k in T.FONT_SITES[game]]:
                yield game, server, key, G.font_style(game, key)

    def index_of(self, game: str, key: str) -> int:
        return [k for _va, k in T.FONT_SITES[game]].index(key) if game == "plant" else \
            ["paddington_tt_18", "paddington_tt_30", "font_triplex_sanslightlin_bold_16pt"].index(key)

    def test_letters_stand_on_the_fonts_baseline_as_tall_as_its_capitals(self) -> None:
        for game, server, key, style in self.styles():
            server.pen(self.index_of(game, key), style["height"])
            for letter in ("Ж", "Ω", "Ł"):
                with self.subTest(game=game, font=key, letter=letter):
                    piece = server.raster(letter)
                    self.assertEqual(piece.kind, 1)
                    top, bottom = piece.ink_rows()
                    self.assertEqual(bottom, style["baseline"] - 1)
                    self.assertLessEqual(abs(top - style["cap_top"]), 1 if letter != "Ł" else 2)
                    # the font's own side bearings around the ink
                    self.assertEqual(piece.xoff, style["left"])
                    self.assertEqual(piece.adv, piece.w + style["left"] + style["right"])

    def test_the_chain_order(self) -> None:
        server = self.servers["fish"]
        server.pen(0, 20)
        chain = dll_chain()
        for text, face in (("★", "Segoe UI Symbol"), ("\U00012000", "Segoe UI Historic"), ("中", "Yu Gothic"),
                           ("가", "Malgun Gothic"), ("क्ष", "Nirmala UI"), ("Ж", "Segoe UI")):
            with self.subTest(text=text):
                self.assertEqual(chain[server.raster(text).drawn_by], face)

    def test_a_run_is_joined_and_ordered(self) -> None:
        server = self.servers["fish"]
        server.pen(0, 20)
        beh = server.raster("ب")
        self.assertLess(server.raster("ببب").adv, beh.adv * 3)
        # Hebrew right to left: the run's left end is its last letter
        run, bet = server.raster("אב"), server.raster("ב")
        left = [[run.coverage(x, y) for x in range(bet.w)] for y in range(run.height)]
        alone = [[bet.coverage(x, y) for x in range(bet.w)] for y in range(bet.height)]
        self.assertEqual(left, alone)

    def test_use_unicode_font_fits_the_em(self) -> None:
        server = self.servers["fish"]
        sentence = "The quick brown fox jumps over the lazy dog 0123456789"
        server.poke("system_font", 1)
        try:
            server.set_chosen_font("Arial")
            # (font, the game font's width of the sentence): fitted, held at 60%, held at 130% (once each:
            # the DLL fits each style once)
            for index, key, game_width in ((0, "paddington_tt_18", 420), (1, "paddington_tt_30", 100),
                                           (2, "font_triplex_sanslightlin_bold_16pt", 5000)):
                style = G.font_style("fish", key)
                with self.subTest(font=key, game_width=game_width):
                    server.pen(index, style["height"])
                    server.poke_offset("pen", 40, game_width)     # pen.game_fit
                    width = gdi_extent("Arial", style["em"], style["weight"], sentence)
                    em = (style["em"] * game_width * 2 + width) // (2 * width)
                    em = max(style["em"] * 6 // 10, min(style["em"] * 13 // 10, em))
                    drawn = server.raster("H")
                    self.assertEqual(drawn.kind, 1)
                    self.assertEqual(server.raster("H").drawn_by, -1)      # the chosen face
                    top, bottom = drawn.ink_rows()
                    self.assertEqual(bottom, style["baseline"] - 1)
                    self.assertAlmostEqual(bottom - top + 1, em * 0.716, delta=1.0)
                    # Use Unicode Font keeps the face's own advance (no game bearings)
                    self.assertNotEqual(drawn.adv, drawn.w + style["left"] + style["right"] + 1000)
        finally:
            server.poke("system_font", 0)
            server.set_chosen_font("Segoe UI")


if __name__ == "__main__":
    unittest.main()
