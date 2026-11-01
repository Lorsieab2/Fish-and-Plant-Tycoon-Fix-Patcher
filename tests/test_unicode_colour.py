"""Colour emoji (Unicode Text.dll, both games, both modes): a colour font's letter is drawn by
Direct2D and DirectWrite in the font's own colours, as the Text Maker draws it.

* In Unicorn (the DLL's and the game's own code, Windows' fonts stood in for): a colour letter
  from raster_glyph (its premultiplied B, G, R, A pixels) becomes a surface in its own colours,
  never tinted with the text's colour, with the text's alpha, blitted at the pen; the measure is
  its advance as for any run-time letter. The same in the Use Unicode Font mode.
* Natively (the DLL built from its source, loaded by a small 32-bit helper that calls its own
  raster_glyph): an emoji of Segoe UI Emoji comes back in colour and matches, pixel for pixel
  within anti-aliasing, the Text Maker's drawing of it (src/text_raster.py, Direct2D) at the GDI
  font's em size; a one-colour letter (Japanese) is still GDI's coverage; and with Direct2D taken
  away the emoji falls back to one colour.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import test_unicode_text as T
from test_unicode_text import E, needs

try:
    import test_unicode_names as N
except ImportError:          # no Unicorn
    N = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from picture_image import Image  # noqa: E402
import text_maker  # noqa: E402

APPLE = 0x1F34E                  # 🍎
GRIN = 0x1F600                   # 😀
FISH = 0x1F41F                   # 🐟

# the stand-in colour letter: premultiplied (B, G, R, A) pixels, 3 columns
STAND_IN = [(0, 0, 255, 255), (255, 128, 0, 255), (30, 100, 20, 128)]   # red, sky blue, half-clear green
STAND_W, STAND_XOFF, STAND_ADV = 3, 1, 6


def straight(px: tuple[int, int, int, int], alpha: int) -> tuple[int, int, int, int]:
    """The surface's pixel for a premultiplied (B, G, R, A): straight R, G, B, the text's alpha."""
    b, g, r, a = px
    c = [min(255, (v * 255 + a // 2) // a) for v in (r, g, b)]
    return c[0], c[1], c[2], a * alpha // 255


class ColourCase:
    """The colour letter's way from raster_glyph to the screen, in the game's own draw."""
    game = "fish"

    def setUp(self) -> None:
        dll, symbols = T.built(self.game)
        self.symbols = symbols
        self.fde = T.fde.FontDrawEmulator(self.game, screen_w=900, dll=dll, symbols=symbols)
        self.g = N.Game(self.game, emu=self.fde.emu)
        self.fde.emu.hook(symbols["_raster_glyph"], self._raster, 0)
        va = T.FONT_SITES[self.game][0][0]
        push = bytes(self.fde.emu.uc.mem_read(va, 10))
        table, name_at = struct.unpack_from("<I", push, 1)[0], struct.unpack_from("<I", push, 6)[0]
        name = self.fde.emu.cstring(name_at).decode("ascii")
        self.font = self.fde.load_font_at(name_at, table, (T.ASSETS[self.game] / "Images" / f"{name}.png").read_bytes())
        inner = self.fde.emu.read32(self.font + 4)
        self.height = self.fde.emu.read32(inner + 4)
        self.spacing = self.fde.emu.read32(inner + 8, signed=True)

    def _raster(self, e) -> int:
        cp, height, out, w_at, xoff_at, adv_at = (e.arg(i) for i in range(6))
        e.write32(w_at, STAND_W)
        e.write32(xoff_at, STAND_XOFF)
        e.write32(adv_at, STAND_ADV)
        if cp != APPLE:                                     # any other letter: one colour, full cover
            e.uc.mem_write(out, b"\xFF" * (STAND_W * height))
            return 1
        rows = b"".join(bytes(px) for px in STAND_IN) * height
        e.uc.mem_write(out, rows)
        return 2

    def draw(self, raw: bytes, colour: int, own: bool = False, x: int = 5, fill: bool = True) -> bytes:
        if fill:
            self.fde.fill((10, 20, 30))
        at = self.fde.emu.alloc(len(raw) + 1)
        self.fde.emu.uc.mem_write(at, raw + b"\0")
        target = self.symbols["_orig_draw"] if own else N.GAMES[self.game]["draw"]
        self.fde.emu.call(target, at, x, 7, colour, self.font, ecx=self.fde.impl)
        return bytes(self.fde.screen_image.data)

    def width(self, raw: bytes, own: bool = False) -> int:
        at = self.fde.emu.alloc(len(raw) + 1)
        self.fde.emu.uc.mem_write(at, raw + b"\0")
        target = self.symbols["_orig_width"] if own else N.GAMES[self.game]["width"]
        return self.fde.emu.call(target, at, N.f32(1.0), ecx=self.font)

    def expected(self, colour: int, text_colour_rgb: tuple[int, int, int] | None = None) -> bytes:
        """'A', the colour letter at the pen in its own colours and the text's alpha, then 'b'."""
        a_end = 5 + self.width(b"A", own=True) + self.spacing
        self.fde.fill((10, 20, 30))
        self.draw(b"A", colour, own=True, fill=False)
        self.draw(b"b", colour, own=True, x=a_end + STAND_ADV + self.spacing, fill=False)
        piece = Image(STAND_W, self.height)
        for y in range(self.height):
            for x, px in enumerate(STAND_IN):
                at = (y * STAND_W + x) * 4
                piece.data[at:at + 4] = bytes(straight(px, colour >> 24))
        text_maker.sdl_blend(self.fde.screen_image, piece, a_end + STAND_XOFF, 7)
        return bytes(self.fde.screen_image.data)

    def test_a_colour_letter_keeps_its_colours_and_takes_the_texts_alpha(self) -> None:
        text = ("A" + chr(APPLE) + "b").encode("utf-8")
        for colour in (0xFF40D0FF, 0xFFFFFFFF, 0x80FF0000, 0x40102030):     # 0xAABBGGRR
            with self.subTest(colour=hex(colour)):
                shown = self.draw(text, colour)
                self.assertEqual(shown, self.expected(colour))
                # the measure: its advance, as for any run-time letter
                self.assertEqual(self.width(text), self.width(b"Ab", own=True) + STAND_ADV + self.spacing)

    def test_the_same_letter_in_two_text_colours_is_the_same_colours(self) -> None:
        text = chr(APPLE).encode("utf-8")
        yellow = self.draw(text, 0xFF00FFFF)
        blue = self.draw(text, 0xFFFF0000)
        self.assertEqual(yellow, blue)                      # not tinted
        self.assertNotEqual(self.draw(chr(FISH).encode("utf-8"), 0xFF00FFFF),
                            self.draw(chr(FISH).encode("utf-8"), 0xFFFF0000))   # a one-colour letter is

    def test_use_unicode_font_draws_it_in_colour_too(self) -> None:
        self.fde.emu.write32(self.symbols["_system_font"], 1)
        try:
            text = ("A" + chr(APPLE)).encode("utf-8")
            shown = self.draw(text, 0xFF40D0FF)
            # 'A' is a run-time glyph in the text's colour now; the apple keeps its own
            img = self.fde.screen_image
            pen = 5 + STAND_ADV + self.spacing + STAND_XOFF
            row = 7 + self.height // 2
            got = [tuple(img.data[(row * img.width + pen + i) * 4:(row * img.width + pen + i) * 4 + 3])
                   for i in range(2)]
            self.assertEqual(got, [(255, 0, 0), (0, 128, 255)])
            self.assertTrue(shown)
        finally:
            self.fde.emu.write32(self.symbols["_system_font"], 0)


@needs("fish")
class FishColourTests(ColourCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantColourTests(ColourCase, unittest.TestCase):
    game = "plant"


# ---------------------------------------------------------------- natively, with Windows' fonts

HELPER = r"""
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
typedef int (__cdecl *raster_fn)(unsigned int, int, unsigned char *, int *, int *, int *);
static unsigned char buf[512 * 128 * 4];
/* helper <dll> <raster_glyph rva> <dx rva or 0: Direct2D taken away> <cp> <height> <out> */
int main(int argc, char **argv) {
    HMODULE m;
    raster_fn f;
    int w = 0, xoff = 0, adv = 0, kind, height;
    unsigned long dx;
    FILE *out;
    if (argc != 7) return 2;
    m = LoadLibraryA(argv[1]);
    if (m == NULL) return 3;
    f = (raster_fn)((char *)m + strtoul(argv[2], NULL, 16));
    dx = strtoul(argv[3], NULL, 16);
    if (dx) { int *d = (int *)((char *)m + dx); d[0] = 1; d[1] = 0; }   /* tried, not ready */
    height = atoi(argv[5]);
    kind = f(strtoul(argv[4], NULL, 16), height, buf, &w, &xoff, &adv);
    if (fopen_s(&out, argv[6], "wb") != 0) return 4;
    fwrite(&kind, 4, 1, out); fwrite(&w, 4, 1, out); fwrite(&xoff, 4, 1, out); fwrite(&adv, 4, 1, out);
    if (kind) fwrite(buf, 1, (size_t)w * height * (kind == 2 ? 4 : 1), out);
    fclose(out);
    return 0;
}
"""


def _native_ready() -> bool:
    return (os.name == "nt" and E is not None and E.toolchain_ready()
            and (T.ASSETS["fish"] / "Unicode Text.dll").is_file())


def _text_raster():
    try:
        import text_raster  # noqa: PLC0415
    except (ImportError, OSError):
        return None
    return text_raster if text_raster.available() else None


def gdi_em(family: str, height: int) -> tuple[int, int]:
    """(em size, ascent) of the GDI font the DLL makes for a line `height` tall."""
    gdi = ctypes.WinDLL("gdi32")
    gdi.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi.CreateFontW.restype = ctypes.c_void_p
    gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [ctypes.c_uint32] * 8 + [ctypes.c_wchar_p]
    gdi.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi.GetTextMetricsW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi.DeleteDC.argtypes = [ctypes.c_void_p]
    dc = gdi.CreateCompatibleDC(None)
    font = gdi.CreateFontW(height, 0, 0, 0, 600, 0, 0, 0, 1, 4, 0, 4, 0, family)
    gdi.SelectObject(dc, font)
    tm = (ctypes.c_byte * 64)()
    gdi.GetTextMetricsW(dc, tm)
    h, ascent, _descent, internal = struct.unpack_from("<4i", bytes(tm), 0)
    gdi.DeleteObject(font)
    gdi.DeleteDC(dc)
    return h - internal, ascent


@unittest.skipUnless(_native_ready(), "needs Windows, the pinned MSVC toolset and Unicorn's emulator module")
class NativeColourTests(unittest.TestCase):
    """The DLL's own raster_glyph, run natively against Windows' fonts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        out = Path(cls.temp.name)
        cls.dll, symbols = T.built("fish")
        cls.raster_rva = symbols["_raster_glyph"] - T.DLL_BASE
        cls.dx_rva = symbols["_dx"] - T.DLL_BASE
        (out / "helper.c").write_text(HELPER, encoding="ascii")
        sdk = E.SDK / "Include" / E.SDK_VERSION
        lib = E.SDK / "Lib" / E.SDK_VERSION
        command = [str(E.MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/O2", "/MT", "/W3",
                   str(out / "helper.c"), "/Fe" + str(out / "helper.exe"), "/Fo" + str(out) + "\\",
                   "/I", str(E.MSVC / "include"), "/I", str(sdk / "um"), "/I", str(sdk / "shared"), "/I", str(sdk / "ucrt"),
                   "/link", "/LIBPATH:" + str(E.MSVC / "lib" / "x86"), "/LIBPATH:" + str(lib / "um" / "x86"),
                   "/LIBPATH:" + str(lib / "ucrt" / "x86"), "kernel32.lib"]
        result = subprocess.run(command, cwd=out, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        cls.helper = out / "helper.exe"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def raster(self, cp: int, height: int, no_direct2d: bool = False) -> tuple[int, int, int, int, bytes]:
        out = Path(self.temp.name) / f"{cp:x}_{height}_{int(no_direct2d)}.bin"
        result = subprocess.run([str(self.helper), str(self.dll), f"{self.raster_rva:x}",
                                 f"{self.dx_rva if no_direct2d else 0:x}", f"{cp:x}", str(height), str(out)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0)
        data = out.read_bytes()
        kind, w, xoff, adv = struct.unpack_from("<4i", data)
        return kind, w, xoff, adv, data[16:]

    def test_an_emoji_comes_back_in_colour(self) -> None:
        for cp in (APPLE, GRIN, FISH):
            with self.subTest(cp=hex(cp)):
                kind, w, _xoff, adv, pixels = self.raster(cp, 22)
                self.assertEqual(kind, 2)
                self.assertGreater(w, 8)
                self.assertGreater(adv, 8)
                self.assertEqual(len(pixels), w * 22 * 4)
                chromatic = sum(1 for i in range(0, len(pixels), 4)
                                if pixels[i + 3] > 128 and max(pixels[i:i + 3]) - min(pixels[i:i + 3]) > 60)
                self.assertGreater(chromatic, 20)

    def test_one_colour_letters_are_gdis_coverage_as_before(self) -> None:
        for cp in (0x5C71, 0x0130, 0x12000):               # 山, İ, cuneiform
            with self.subTest(cp=hex(cp)):
                kind, w, _xoff, _adv, pixels = self.raster(cp, 22)
                self.assertEqual(kind, 1)
                self.assertEqual(len(pixels), w * 22)

    def test_variation_selectors_and_joiners_take_no_room(self) -> None:
        """An emoji's U+FE0F (as in a heart typed from the emoji panel) left a gap the width of a
        missing letter; it and the zero-width joiner draw nothing and take no width."""
        for cp in (0xFE0F, 0xFE0E, 0x200D, 0xE0100):
            with self.subTest(cp=hex(cp)):
                self.assertEqual(self.raster(cp, 22)[:4], (1, 0, 0, 0))

    def test_without_direct2d_an_emoji_is_one_colour(self) -> None:
        kind, w, _xoff, _adv, pixels = self.raster(APPLE, 22, no_direct2d=True)
        self.assertEqual(kind, 1)
        self.assertEqual(len(pixels), w * 22)
        self.assertGreater(max(pixels), 200)

    def test_it_matches_the_text_makers_drawing(self) -> None:
        """The Text Maker's Direct2D drawing (src/text_raster.py) of the emoji at the GDI font's em
        size, its baseline on the GDI font's: the same pixels, within anti-aliasing."""
        tr = _text_raster()
        if tr is None:
            self.skipTest("Direct2D is not available")
        height = 22
        em, ascent = gdi_em("Segoe UI Emoji", height)
        for cp in (APPLE, GRIN, FISH):
            with self.subTest(cp=hex(cp)):
                kind, w, xoff, _adv, pixels = self.raster(cp, height)
                self.assertEqual(kind, 2)
                ref = tr.raster(chr(cp), "Segoe UI Emoji", float(em), 400)
                top = round(ref.baseline) - ascent             # the reference's row for the DLL's row 0
                left = round(ref.origin_x) + xoff
                diff, worst, count = 0, 0, 0
                for y in range(height):
                    for x in range(w):
                        ry, rx = top + y, left + x
                        mine = pixels[(y * w + x) * 4:(y * w + x) * 4 + 4]
                        if 0 <= ry < ref.height and 0 <= rx < ref.width:
                            theirs = ref.bgra[(ry * ref.width + rx) * 4:(ry * ref.width + rx) * 4 + 4]
                        else:
                            theirs = b"\0\0\0\0"
                        d = max(abs(a - b) for a, b in zip(mine, theirs))
                        diff += d
                        worst = max(worst, d)
                        count += 1
                # the same drawing (pixel for pixel on this machine; a little room for a baseline
                # that falls between pixels differently)
                self.assertLess(diff / count, 3, f"mean difference {diff / count:.1f}")
                self.assertLess(worst, 96)
                ink = sum(1 for i in range(3, len(pixels), 4) if pixels[i] > 200)
                ref_ink = sum(1 for i in range(3, len(ref.bgra), 4) if ref.bgra[i] > 200)
                self.assertLess(abs(ink - ref_ink), max(6, ref_ink // 10))
