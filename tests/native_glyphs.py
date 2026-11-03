"""Unicode Text.dll's own Windows-font drawing, run natively (Windows only).

The DLL (rebuilt from its source with a map, tests/store_emulator.py build_with_map) is loaded by a
small 32-bit server program, which calls the DLL's own pen_for_style, raster_glyph and raster_cluster
(native/common/unicode_glyphs.h) at their addresses from the map, with Windows' real fonts and the
fonts the patcher ships beside the DLL ("Fonts", loaded with AddFontResourceExW(FR_PRIVATE)).
Requests go one per line on its standard input:

    pen <style index> <height>          the pen set to that game font's style (-1: no style)
    poke <rva> <value>                  a 32-bit value written into the DLL (system_font, ...)
    peek <rva>                          a 32-bit value read from the DLL
    wpoke <rva> <hex UTF-16 units>      a UTF-16 string written into the DLL (chosen_font)
    raster <hex code point> ...         one code point (raster_glyph) or a piece (raster_cluster)
    levels <hex UTF-16 unit> ...        a line's bidi levels (line_levels: Uniscribe's ScriptItemize)
    order <level> ...                   runs' visual order: visual_order (ScriptLayout), then reverse_runs

and each "raster" answers with a line "kind w xoff adv drawn_by" and then w x height coverage
bytes (kind 1) or w x height x 4 premultiplied B, G, R, A bytes (kind 2) as hex.

tests/test_unicode_drawing.py uses it to check what the DLL draws, and scripts/make_unicode_preview.py
uses it, with the game's own draw run in Unicorn, to draw the preview sheet.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SERVER = r"""
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int (__cdecl *raster_fn)(unsigned int, int, unsigned char *, int *, int *, int *);
typedef int (__cdecl *cluster_fn)(const unsigned int *, int, int, unsigned char *, int *, int *, int *);
typedef void (__cdecl *pen_fn)(int, int);
typedef int (__cdecl *levels_fn)(const unsigned short *, int, unsigned char *);
typedef void (__cdecl *order_fn)(int, const unsigned char *, int *);
static unsigned char buf[1024 * 128 * 4];
static char line[65536];
/* server <dll> <pen_for_style rva> <raster_glyph rva> <raster_cluster rva> <pen rva> <drawn_by rva>
          <line_levels rva> <visual_order rva> <reverse_runs rva> */
int main(int argc, char **argv) {
    HMODULE m;
    char *base;
    pen_fn pen;
    raster_fn glyph;
    cluster_fn cluster;
    int *pen_state, *drawn;
    levels_fn levels;
    order_fn order, reverse;
    if (argc < 10) return 2;
    m = LoadLibraryA(argv[1]);
    if (m == NULL) return 3;
    base = (char *)m;
    pen = (pen_fn)(base + strtoul(argv[2], NULL, 16));
    glyph = (raster_fn)(base + strtoul(argv[3], NULL, 16));
    cluster = (cluster_fn)(base + strtoul(argv[4], NULL, 16));
    pen_state = (int *)(base + strtoul(argv[5], NULL, 16));
    drawn = (int *)(base + strtoul(argv[6], NULL, 16));
    levels = (levels_fn)(base + strtoul(argv[7], NULL, 16));
    order = (order_fn)(base + strtoul(argv[8], NULL, 16));
    reverse = (order_fn)(base + strtoul(argv[9], NULL, 16));
    while (fgets(line, sizeof line, stdin) != NULL) {
        char *word = strtok(line, " \r\n");
        if (word == NULL) continue;
        if (strcmp(word, "pen") == 0) {
            int index = atoi(strtok(NULL, " \r\n")), height = atoi(strtok(NULL, " \r\n"));
            pen(index, height);
            printf("ok %d %d %d %d %d\n", pen_state[0], pen_state[1], pen_state[2], pen_state[3], pen_state[4]);
        } else if (strcmp(word, "poke") == 0) {
            unsigned long rva = strtoul(strtok(NULL, " \r\n"), NULL, 16);
            long value = strtol(strtok(NULL, " \r\n"), NULL, 10);
            *(int *)(base + rva) = (int)value;
            printf("ok\n");
        } else if (strcmp(word, "wpoke") == 0) {
            unsigned long rva = strtoul(strtok(NULL, " \r\n"), NULL, 16);
            char *units = strtok(NULL, " \r\n");
            unsigned short *dst = (unsigned short *)(base + rva);
            int k = 0;
            while (units != NULL && units[k * 4] != 0) {
                char part[5];
                memcpy(part, units + k * 4, 4);
                part[4] = 0;
                dst[k] = (unsigned short)strtoul(part, NULL, 16);
                ++k;
            }
            dst[k] = 0;
            printf("ok\n");
        } else if (strcmp(word, "raster") == 0) {
            unsigned int cps[300];
            int n = 0, w = 0, xoff = 0, adv = 0, kind, i, total, height = pen_state[1];
            char *t;
            while ((t = strtok(NULL, " \r\n")) != NULL && n < 300) cps[n++] = strtoul(t, NULL, 16);
            *drawn = -2;
            memset(buf, 0, sizeof buf);
            if (n == 1) kind = glyph(cps[0], height, buf, &w, &xoff, &adv);
            else kind = cluster(cps, n, height, buf, &w, &xoff, &adv);
            printf("%d %d %d %d %d\n", kind, w, xoff, adv, *drawn);
            total = kind == 2 ? w * height * 4 : kind == 1 ? w * height : 0;
            for (i = 0; i < total; ++i) printf("%02x", buf[i]);
            printf("\n");
        } else if (strcmp(word, "peek") == 0) {
            unsigned long rva = strtoul(strtok(NULL, " \r\n"), NULL, 16);
            printf("%d\n", *(int *)(base + rva));
        } else if (strcmp(word, "levels") == 0) {
            static unsigned short units[1100];
            static unsigned char got[1100];
            int n = 0, i, ok;
            char *t;
            while ((t = strtok(NULL, " \r\n")) != NULL && n < 1100) units[n++] = (unsigned short)strtoul(t, NULL, 16);
            ok = levels(units, n, got);
            printf("%d", ok);
            for (i = 0; ok && i < n; ++i) printf(" %d", got[i]);
            printf("\n");
        } else if (strcmp(word, "order") == 0) {
            static unsigned char runs[300];
            static int a[300], b[300];
            int n = 0, i;
            char *t;
            while ((t = strtok(NULL, " \r\n")) != NULL && n < 300) runs[n++] = (unsigned char)atoi(t);
            order(n, runs, a);
            reverse(n, runs, b);
            for (i = 0; i < n; ++i) printf("%d ", a[i]);
            printf("|");
            for (i = 0; i < n; ++i) printf(" %d", b[i]);
            printf("\n");
        } else {
            printf("?\n");
        }
        fflush(stdout);
    }
    return 0;
}
"""


def uniscribe_levels(units: list[int]) -> list[int] | None:
    """Each UTF-16 unit's bidi level as Uniscribe's ScriptItemize gives it with a full analysis (a
    SCRIPT_CONTROL and a left-to-right SCRIPT_STATE), as the DLL's line_levels asks it: what the
    Unicorn tests stand in for line_levels with (Windows only; None elsewhere or when it fails)."""
    if os.name != "nt" or not units:
        return None
    import ctypes

    class Item(ctypes.Structure):
        _fields_ = [("pos", ctypes.c_int), ("analysis", ctypes.c_uint16), ("state", ctypes.c_uint16)]
    n = len(units)
    text = (ctypes.c_uint16 * n)(*units)
    items = (Item * (n + 2))()
    control, state, count = ctypes.c_uint32(0), ctypes.c_uint16(0), ctypes.c_int(0)
    if ctypes.windll.usp10.ScriptItemize(text, n, n + 1, ctypes.byref(control), ctypes.byref(state), items,
                                         ctypes.byref(count)) != 0:
        return None
    levels = [0] * n
    for i in range(count.value):
        for k in range(items[i].pos, min(items[i + 1].pos, n)):
            levels[k] = items[i].state & 0x1F
    return levels


def available() -> bool:
    try:
        import store_emulator as E
    except ImportError:
        return False
    return os.name == "nt" and E.toolchain_ready()


class Piece:
    def __init__(self, kind: int, w: int, xoff: int, adv: int, drawn_by: int, height: int, data: bytes) -> None:
        self.kind, self.w, self.xoff, self.adv, self.drawn_by, self.height, self.data = (
            kind, w, xoff, adv, drawn_by, height, data)

    def coverage(self, x: int, y: int) -> int:
        return self.data[y * self.w + x]

    def ink_rows(self) -> tuple[int, int] | None:
        rows = [y for y in range(self.height) if any(self.coverage(x, y) for x in range(self.w))]
        return (rows[0], rows[-1]) if rows else None


class GlyphServer:
    """The DLL of `game` (with its Fonts folder beside it unless `fonts` is False), served natively."""

    def __init__(self, game: str, fonts: bool = True) -> None:
        import store_emulator as E
        import test_unicode_text as T
        self.temp = tempfile.TemporaryDirectory()
        out = Path(self.temp.name)
        built, symbols = T.built(game)
        self.symbols = symbols
        folder = out / "dll"
        folder.mkdir()
        shutil.copyfile(built, folder / "Unicode Text.dll")
        if fonts:
            shutil.copytree(T.ASSETS[game] / "Fonts", folder / "Fonts")
        self.folder = folder
        (out / "server.c").write_text(SERVER, encoding="ascii")
        sdk = E.SDK / "Include" / E.SDK_VERSION
        lib = E.SDK / "Lib" / E.SDK_VERSION
        command = [str(E.MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/O2", "/MT", "/W3",
                   str(out / "server.c"), "/Fe" + str(out / "server.exe"), "/Fo" + str(out) + "\\",
                   "/I", str(E.MSVC / "include"), "/I", str(sdk / "um"), "/I", str(sdk / "shared"), "/I", str(sdk / "ucrt"),
                   "/link", "/LIBPATH:" + str(E.MSVC / "lib" / "x86"), "/LIBPATH:" + str(lib / "um" / "x86"),
                   "/LIBPATH:" + str(lib / "ucrt" / "x86"), "kernel32.lib"]
        result = subprocess.run(command, cwd=out, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        names = ("pen_for_style", "raster_glyph", "raster_cluster", "pen", "drawn_by", "line_levels", "visual_order",
                 "reverse_runs")
        rva = {name: symbols[f"_{name}"] - T.DLL_BASE for name in names}
        self.rva = rva
        self.process = subprocess.Popen(
            [str(out / "server.exe"), str(folder / "Unicode Text.dll")]
            + [f"{rva[k]:x}" for k in names],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.height = 16

    def _ask(self, text: str) -> str:
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()
        return self.process.stdout.readline().strip()

    def pen(self, index: int, height: int) -> list[int]:
        answer = self._ask(f"pen {index} {height}").split()
        self.height = int(answer[2])
        return [int(v) for v in answer[1:]]

    def poke(self, symbol: str, value: int) -> None:
        import test_unicode_text as T
        self._ask(f"poke {self.symbols['_' + symbol] - T.DLL_BASE:x} {value}")

    def peek(self, symbol: str) -> int:
        import test_unicode_text as T
        return int(self._ask(f"peek {self.symbols['_' + symbol] - T.DLL_BASE:x}"))

    def poke_offset(self, symbol: str, offset: int, value: int) -> None:
        import test_unicode_text as T
        self._ask(f"poke {self.symbols['_' + symbol] - T.DLL_BASE + offset:x} {value}")

    def set_chosen_font(self, name: str) -> None:
        import test_unicode_text as T
        units = name.encode("utf-16-le")
        hexed = "".join(f"{units[i] | units[i + 1] << 8:04x}" for i in range(0, len(units), 2))
        self._ask(f"wpoke {self.symbols['_chosen_font'] - T.DLL_BASE:x} {hexed}")

    def raster(self, text: str | list[int]) -> Piece:
        cps = [ord(c) for c in text] if isinstance(text, str) else list(text)
        head = self._ask("raster " + " ".join(f"{c:x}" for c in cps)).split()
        body = self.process.stdout.readline().strip()
        kind, w, xoff, adv, drawn = (int(v) for v in head)
        return Piece(kind, w, xoff, adv, drawn, self.height, bytes.fromhex(body))

    def levels(self, text: str) -> list[int] | None:
        """line_levels of `text`: each UTF-16 unit's bidi level, None when it failed."""
        raw = text.encode("utf-16-le")
        units = [raw[i] | raw[i + 1] << 8 for i in range(0, len(raw), 2)]
        answer = [int(v) for v in self._ask("levels " + " ".join(f"{u:x}" for u in units)).split()]
        return answer[1:] if answer[0] else None

    def order(self, levels: list[int]) -> tuple[list[int], list[int]]:
        """(visual_order, reverse_runs) of runs at `levels`."""
        left, right = self._ask("order " + " ".join(str(v) for v in levels)).split("|")
        return [int(v) for v in left.split()], [int(v) for v in right.split()]

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.stdin.close()
            self.process.wait(timeout=30)
        self.temp.cleanup()
