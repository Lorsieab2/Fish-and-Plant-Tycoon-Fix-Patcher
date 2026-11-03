"""Unicode 18.0 in "Unicode Text.dll", run natively: the DLL's own raster_glyph and raster_cluster
(native/common/unicode_glyphs.h) loaded into a small x86 program with Windows' real fonts and the
fonts the patcher ships beside it ("Fonts", loaded with AddFontResourceExW(FR_PRIVATE)).

* A letter no Windows font has draws from the bundled fonts: Tangut (Noto Serif Tangut), Early
  Dynastic Cuneiform (Noto Sans Cuneiform), letters new in Unicode 18.0 (Small Seal, Jurchen:
  Last Resort's placeholder). Without the Fonts folder the same letters have no font.
* A grapheme of several code points draws whole: an emoji ZWJ sequence, a flag and a keycap
  (by Segoe UI Emoji: in colour, a flag as its two letters, as Windows draws flags), a letter with a combining mark, a Devanagari conjunct.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_unicode_text as T  # noqa: E402
from test_unicode_text import E  # noqa: E402

HELPER = r"""
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
typedef int (__cdecl *raster_fn)(unsigned int, int, unsigned char *, int *, int *, int *);
typedef int (__cdecl *cluster_fn)(const unsigned int *, int, int, unsigned char *, int *, int *, int *);
static unsigned char buf[512 * 128 * 4];
/* helper <dll> <raster_glyph rva> <raster_cluster rva> <height> <out> <cp> [<cp> ...] */
int main(int argc, char **argv) {
    HMODULE m;
    unsigned int cps[32];
    int w = 0, xoff = 0, adv = 0, kind, height, n = 0, i;
    FILE *out;
    if (argc < 7) return 2;
    m = LoadLibraryA(argv[1]);
    if (m == NULL) return 3;
    height = atoi(argv[4]);
    for (i = 6; i < argc && n < 32; ++i) cps[n++] = strtoul(argv[i], NULL, 16);
    if (n == 1) kind = ((raster_fn)((char *)m + strtoul(argv[2], NULL, 16)))(cps[0], height, buf, &w, &xoff, &adv);
    else kind = ((cluster_fn)((char *)m + strtoul(argv[3], NULL, 16)))(cps, n, height, buf, &w, &xoff, &adv);
    if (fopen_s(&out, argv[5], "wb") != 0) return 4;
    fwrite(&kind, 4, 1, out); fwrite(&w, 4, 1, out); fwrite(&xoff, 4, 1, out); fwrite(&adv, 4, 1, out);
    fclose(out);
    return 0;
}
"""


def _ready() -> bool:
    return os.name == "nt" and E is not None and E.toolchain_ready() and (T.ASSETS["fish"] / "Unicode Text.dll").is_file()


@unittest.skipUnless(_ready(), "needs Windows, the pinned MSVC toolset and Unicorn's emulator module")
class NativeUnicode18Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        out = Path(cls.temp.name)
        built, symbols = T.built("fish")
        cls.glyph_rva = symbols["_raster_glyph"] - T.DLL_BASE
        cls.cluster_rva = symbols["_raster_cluster"] - T.DLL_BASE
        # the DLL as installed (its Fonts folder beside it), and the same DLL alone
        for name, fonts in (("with", True), ("without", False)):
            folder = out / name
            folder.mkdir()
            shutil.copyfile(built, folder / "Unicode Text.dll")
            if fonts:
                shutil.copytree(T.ASSETS["fish"] / "Fonts", folder / "Fonts")
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

    def raster(self, cps: list[int], fonts: bool = True, height: int = 22) -> tuple[int, int, int, int]:
        out = Path(self.temp.name) / ("r_" + "_".join(f"{c:x}" for c in cps) + f"_{int(fonts)}.bin")
        dll = Path(self.temp.name) / ("with" if fonts else "without") / "Unicode Text.dll"
        result = subprocess.run([str(self.helper), str(dll), f"{self.glyph_rva:x}", f"{self.cluster_rva:x}",
                                 str(height), str(out)] + [f"{c:x}" for c in cps], capture_output=True)
        self.assertEqual(result.returncode, 0)
        return struct.unpack_from("<4i", out.read_bytes())

    def test_letters_windows_lacks_draw_from_the_bundled_fonts(self) -> None:
        for cp in (0x17000, 0x12480, 0x3D000, 0x18E00, 0x191A0, 0x12550):
            with self.subTest(cp=hex(cp)):
                kind, w, _xoff, adv = self.raster([cp])
                self.assertEqual(kind, 1)
                self.assertGreater(w, 3)
                self.assertGreater(adv, 3)

    def test_new_letters_have_no_font_without_the_bundled_ones(self) -> None:
        for cp in (0x3D000, 0x18E00):
            with self.subTest(cp=hex(cp)):
                self.assertEqual(self.raster([cp], fonts=False)[0], 0)

    def test_graphemes_draw_whole(self) -> None:
        family = [0x1F468, 0x200D, 0x1F469, 0x200D, 0x1F467, 0x200D, 0x1F466]
        single = self.raster([0x1F468])
        for cps, colour in ((family, 2), ([0x1F1EF, 0x1F1F5], 1), ([0x31, 0xFE0F, 0x20E3], 2),
                            ([0x65, 0x301], 1), ([0x915, 0x94D, 0x937], 1)):
            with self.subTest(cps=[hex(c) for c in cps]):
                kind, w, _xoff, adv = self.raster(cps)
                self.assertEqual(kind, colour)
                self.assertGreater(w, 3)
        # the family is one emoji, about as wide as one person, not four
        self.assertLess(self.raster(family)[3], single[3] * 2)
