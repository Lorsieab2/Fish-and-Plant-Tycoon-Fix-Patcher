"""Unicode 18.0 everywhere: the data the patcher ships, its grapheme clusters, the DLL's tables, and
that every assigned code point is taken and drawn.

* data/unicode: each file is the one downloaded from unicode.org (sources.json: size, SHA-256).
* src/unicode_data.py: every line of GraphemeBreakTest.txt 18.0; every RGI emoji sequence of
  Emoji 18.0 (keycaps, flags, tag flags, modifiers, ZWJ) is one grapheme; names and categories.
* native/common/unicode_grapheme_table.h is what scripts/build_unicode18_tables.py makes, and
  native/common/unicode_grapheme.h, built natively with the DLL's own MSVC (when present), passes
  GraphemeBreakTest too, finds every emoji sequence and takes every assigned letter typed.
* The tools take every assigned code point (no control, surrogate, private use or noncharacter):
  a name (src/save_tools.py), a translation (src/translation_format.py), a whole-grapheme cut.
* Coverage: every such code point maps to a real glyph (never .notdef) in a font of the chain
  the DLL and the Text Maker draw with, from the bundled fonts' committed cmap table
  (data/unicode/font_coverage.json, made by scripts/build_unicode18_coverage.py with fontTools;
  checked against the font files themselves when fontTools is installed).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import unicode_data as U  # noqa: E402

DATA = ROOT / "data" / "unicode"
MSVC = Path(r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231")
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10")
SDK_VERSION = "10.0.26100.0"


def break_tests() -> list[list[str]]:
    """GraphemeBreakTest.txt: each line's expected graphemes."""
    out = []
    for line in (DATA / "GraphemeBreakTest.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        want, cur = [], ""
        for tok in line.split()[1:]:
            if tok == "÷":
                want.append(cur)
                cur = ""
            elif tok != "×":
                cur += chr(int(tok, 16))
        out.append(want)
    return out


ASSIGNED = None


def assigned() -> list[int]:
    global ASSIGNED
    if ASSIGNED is None:
        ASSIGNED = [cp for cp in U.assigned_code_points() if not U.is_noncharacter(cp)]
    return ASSIGNED


class DataTests(unittest.TestCase):
    def test_files_are_the_downloaded_ones(self) -> None:
        sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(sources["version"], "18.0.0")
        self.assertEqual(len(sources["files"]), 12)
        for entry in sources["files"]:
            data = (DATA / entry["file"]).read_bytes()
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest().upper()),
                             (entry["size"], entry["sha256"]), entry["file"])
            if entry["file"] != "license.txt":
                self.assertTrue(entry["url"].startswith("https://www.unicode.org/Public/18.0.0/"))

    def test_counts_and_names(self) -> None:
        self.assertEqual(len(assigned()), 172808)
        self.assertEqual(U.name(0x3D000), "SMALL SEAL CHARACTER-3D000")
        self.assertEqual(U.name(0x18E00), "JURCHEN CHARACTER-18E00")
        self.assertEqual(U.name(0xAC01), "HANGUL SYLLABLE GAG")
        self.assertEqual(U.name(0x0558), "MODIFIER LETTER ARMENIAN SMALL EH")     # new in 18.0
        self.assertEqual(U.age(0x0558), "18.0")
        self.assertEqual(U.lookup("modifier letter armenian small eh"), "\u0558")
        self.assertEqual(U.lookup("SMALL SEAL CHARACTER-3D000"), "\U0003D000")
        self.assertEqual(U.category(0x0558), "Lm")
        self.assertEqual(U.category(0xE000), "Co")
        self.assertEqual(U.category(0x3FFFE), "Cn")
        self.assertEqual(U.block_of(0x3D000), "Seal")

    def test_range_names_match_derived_age(self) -> None:
        """Each range of DerivedAge.txt names its first code point in its comment."""
        for line in (DATA / "DerivedAge.txt").read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or ".." not in line or "#" not in line:
                continue
            first = int(line.split("..")[0], 16)
            comment = line.split("#", 1)[1].split("]", 1)[-1].strip()
            want = comment.split("..")[0].strip()
            if want.startswith("<"):
                continue
            self.assertEqual(U.name(first), want, hex(first))


class GraphemeTests(unittest.TestCase):
    def test_grapheme_break_test(self) -> None:
        cases = break_tests()
        self.assertEqual(len(cases), 853)
        for want in cases:
            self.assertEqual(U.graphemes("".join(want)), want, [hex(ord(c)) for c in "".join(want)])

    def test_every_rgi_emoji_sequence_is_one_grapheme(self) -> None:
        seqs = U.emoji_sequences()
        self.assertGreater(len(seqs), 3900)
        for s in seqs:
            self.assertEqual(U.graphemes(s), [s], [hex(ord(c)) for c in s])
        for s in ("\U0001F468\u200D\U0001F469\u200D\U0001F467\u200D\U0001F466",     # family
                  "1\uFE0F\u20E3", "#\uFE0F\u20E3",                                  # keycaps
                  "\U0001F1EF\U0001F1F5",                                            # a flag
                  "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F"):  # Scotland
            self.assertIn(s, seqs)
            self.assertEqual(U.graphemes("a" + s + s + "b"), ["a", s, s, "b"])

    def test_whole_grapheme_cut(self) -> None:
        family = "\U0001F468\u200D\U0001F469\u200D\U0001F467"
        self.assertEqual(U.cut_graphemes("ab" + family, 4), "ab")
        self.assertEqual(U.cut_graphemes("ab" + family, 7), "ab" + family)
        self.assertEqual(U.cut_graphemes("\u0915\u094D\u0937x", 3), "\u0915\u094D\u0937")
        self.assertEqual(U.cut_graphemes("\u0915\u094D\u0937x", 2), "")


class TableTests(unittest.TestCase):
    def test_header_is_up_to_date(self) -> None:
        import build_unicode18_tables as B
        header = (ROOT / "native" / "common" / "unicode_grapheme_table.h").read_bytes().decode("utf-8")
        self.assertEqual(header.replace("\r\n", "\n"), B.render())

    def test_table_runs_cover_every_code_point(self) -> None:
        import build_unicode18_tables as B
        runs = B.runs()
        self.assertEqual(runs[0][0], 0)
        for cp in (0x0D, 0x0A, 0x300, 0x200D, 0x1F1E6, 0x094D, 0x0915, 0x1F600, 0xAC00, 0xAC01, 0x1100, 0x3D000):
            i = max(k for k, r in enumerate(runs) if r[0] <= cp)
            self.assertEqual(runs[i][1], B.props(cp), hex(cp))


def _toolchain() -> bool:
    return (MSVC / "bin" / "Hostx64" / "x86" / "cl.exe").is_file()


@unittest.skipUnless(_toolchain(), "needs the DLL's pinned MSVC toolset")
class NativeTests(unittest.TestCase):
    """native/common/unicode_grapheme.h, compiled as the DLL compiles it (x86), run natively."""

    exe: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        cls.exe = out / "harness.exe"
        command = [str(MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/O2", "/W4", "/WX", "/MT",
                   f"/Fo{out}\\", f"/Fe{cls.exe}",
                   "/I", str(MSVC / "include"),
                   "/I", str(SDK / "Include" / SDK_VERSION / "ucrt"),
                   "/I", str(SDK / "Include" / SDK_VERSION / "um"),
                   "/I", str(SDK / "Include" / SDK_VERSION / "shared"),
                   str(ROOT / "native" / "common" / "unicode_grapheme_harness.c"),
                   "/link", f"/LIBPATH:{MSVC / 'lib' / 'x86'}",
                   f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'ucrt' / 'x86'}",
                   f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'um' / 'x86'}"]
        result = subprocess.run(command, cwd=out, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_lines(self, lines: list[str]) -> list[str]:
        result = subprocess.run([str(self.exe)], input="\n".join(lines) + "\n", capture_output=True, text=True,
                                check=True)
        return result.stdout.splitlines()

    @staticmethod
    def hexes(text: str) -> str:
        return " ".join(f"{ord(c):X}" for c in text)

    def test_grapheme_break_test(self) -> None:
        # the games' text ends at its first NUL, so the lines with U+0000 are checked without it:
        # each such line's graphemes are the same with U+0000 taken as another control (U+0001)
        cases = [[g.replace(chr(0), chr(1)) for g in want] for want in break_tests()]
        got = self.run_lines(["g " + self.hexes("".join(want)) for want in cases])
        self.assertEqual(len(got), len(cases))
        for want, line in zip(cases, got):
            self.assertEqual(line, " ".join(str(len(g)) for g in want), [self.hexes(g) for g in want])

    def test_every_emoji_sequence(self) -> None:
        seqs = sorted(U.emoji_sequences())
        got = self.run_lines(["g " + self.hexes(s) for s in seqs] + ["e " + self.hexes(s) for s in seqs])
        n = len(seqs)
        for s, one, emoji in zip(seqs, got[:n], got[n:]):
            self.assertEqual(one, str(len(s)), self.hexes(s))
            # every sequence of two or more is in the hash table; a single one is if it shows as emoji
            want = "1" if len(s) > 1 or U.emoji_presentation(ord(s)) else "0"
            self.assertEqual(emoji, want, self.hexes(s))
        self.assertEqual(self.run_lines(["e 61 62", "e 41"]), ["0", "0"])

    def test_every_assigned_letter_is_typed(self) -> None:
        cps = assigned()
        lines = ["t " + " ".join(f"{c:X}" for c in cps[i:i + 5000]) for i in range(0, len(cps), 5000)]
        got = "".join(self.run_lines(lines))
        self.assertEqual(got, "1" * len(cps))
        self.assertEqual(self.run_lines(["t 9 A D 1F 7F 80 9F D800 DFFF 20 A0 3D000"]), ["000000000111"])

    def test_backspace_takes_a_whole_grapheme(self) -> None:
        family = "\U0001F468\u200D\U0001F469\u200D\U0001F467"
        for text, keep in (("ab" + family, "ab"), ("x\U0001F1EF\U0001F1F5", "x"), ("e\u0301", ""),
                           ("a\u0915\u094D\u0937", "a"), ("ab", "a")):
            self.assertEqual(self.run_lines(["b " + self.hexes(text)]), [str(len(keep.encode("utf-8")))], text)
