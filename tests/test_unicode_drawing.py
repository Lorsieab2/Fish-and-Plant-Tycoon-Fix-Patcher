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
        for run in (ARABIC, HEBREW, DEVANAGARI, THAI, "مرحبا ١٢٣"):
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


@needs("fish")
class FishPieceTests(PieceCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantPieceTests(PieceCase, unittest.TestCase):
    game = "plant"


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
