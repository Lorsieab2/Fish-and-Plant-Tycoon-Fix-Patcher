"""Flags drawn as flags in Unicode Text.dll, both games (native/common/unicode_glyphs.h raster_colr).

Windows' Segoe UI Emoji draws a flag (two regional indicators, or a subdivision flag such as
England's black flag and tags) as its two letters ("JP"). The DLL asks Twemoji Mozilla (Mozilla's COLR
version 0 build of Twemoji, shipped beside it and loaded for the game only) first for a flag, and
right after Segoe UI Emoji for any other emoji, and draws its COLR/CPAL layers itself (Direct2D does
not see a font loaded with FR_PRIVATE).

* The font: pinned in data/unicode/fonts.json (size and SHA-256, the same file as Firefox's
  browser/fonts/TwemojiMozilla.ttf), shipped in both games' Fonts folders with its license (CC-BY 4.0
  artwork), loaded by the DLL from its Fonts folder, listed in the manifests' companion files and
  credited in the README.
* Natively (tests/native_glyphs.py: the DLL's own raster_cluster with Windows' fonts and the shipped
  ones), Windows only:
  - JP, US, FR and GB-ENG each come out as ONE colour picture from Twemoji Mozilla: kind 2, no empty
    column inside it (not two letters), about one emoji wide, in the flag's own colours (red on white
    for Japan and England; red, white and blue for the United States);
  - without the Fonts folder the same flag is Segoe UI Emoji's two letters, as before;
  - other emoji are unchanged: Segoe UI Emoji draws them, the same picture with and without the
    shipped fonts.
* In Unicorn: a flag in a line is asked for as one piece (raster_cluster with its code points).
"""

from __future__ import annotations

import hashlib
import json
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
FONT = "Twemoji.Mozilla.ttf"
FONT_SHA256 = "6D90152EE0D29E82FE2A87793AF5AA4B7AD13E6538360889E141E81ED299EE8E"   # v0.7.0 = Firefox's copy
JP = [0x1F1EF, 0x1F1F5]
US = [0x1F1FA, 0x1F1F8]
FR = [0x1F1EB, 0x1F1F7]
GB_ENG = [0x1F3F4, 0xE0067, 0xE0062, 0xE0065, 0xE006E, 0xE0067, 0xE007F]
OTHER_EMOJI = ([0x1F600], [0x1F41F], [0x1F468, 0x200D, 0x1F469, 0x200D, 0x1F467], [0x2764, 0xFE0F],
               [0x1F44D, 0x1F3FD])


class FontTests(unittest.TestCase):
    def setUp(self) -> None:
        doc = json.loads((ROOT / "data" / "unicode" / "fonts.json").read_text(encoding="utf-8"))
        self.entry = next(f for f in doc["colour_fonts"] if f["file"] == FONT)

    def test_the_font_is_pinned_and_shipped_with_its_license(self) -> None:
        self.assertEqual(self.entry["family"], "Twemoji Mozilla")
        self.assertEqual(self.entry["sha256"], FONT_SHA256)
        self.assertTrue(self.entry["license"].startswith("CC-BY-4.0"))
        self.assertIn("/mozilla/twemoji-colr/releases/download/v0.7.0/", self.entry["url"])
        for game in ("fish_tycoon_unicode", "plant_tycoon_unicode"):
            folder = ROOT / "assets" / game / "Fonts"
            data = (folder / FONT).read_bytes()
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest().upper()),
                             (self.entry["size"], self.entry["sha256"]))
            self.assertLess(len(data), 2_000_000)                         # a COLR font, not a bitmap one
            text = (folder / self.entry["license_file"]).read_text(encoding="utf-8")
            for needle in ("Creative Commons Attribution 4.0", "Copyright 2019 Twitter, Inc",
                           "https://creativecommons.org/licenses/by/4.0/", FONT_SHA256, "Apache License"):
                self.assertIn(needle, text)

    def test_the_dll_loads_it_and_the_manifests_ship_it(self) -> None:
        source = (ROOT / "native" / "common" / "unicode_glyphs.h").read_text(encoding="utf-8")
        files = source[source.index("BUNDLED_FONT_FILES[] = {"):]
        self.assertIn(f'L"{FONT}"', files[:files.index("};")])
        chain = source[source.index("static const wchar_t *const CHAIN[] = {"):]
        names = re.findall(r'L"([^"]+)"', chain[:chain.index("};")])
        self.assertIn(f"#define CHAIN_TWEMOJI {names.index('Twemoji Mozilla')} ", source)
        for game in ("fish", "plant"):
            manifest = json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
            for sid in ("unicode_ingame_fonts", "unicode_system_font"):
                setting = next(s for s in manifest["settings"] if s["id"] == sid)
                paths = {f["path"]: f for f in setting["companion"]["files"]}
                self.assertEqual(paths[f"Fonts/{FONT}"]["sha256"], FONT_SHA256)
                self.assertIn("Fonts/LICENSE-TwemojiMozilla.txt", paths)
                self.assertIn("Twemoji Mozilla", setting["description"])

    def test_the_readme_credits_it(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        credits = readme[readme.index("## Credits"):]
        credits = credits[:credits.index("\n## ", 5)]
        for needle in ("Twemoji Mozilla", "Twitter, Inc and other contributors", "CC-BY 4.0",
                       "https://creativecommons.org/licenses/by/4.0/"):
            self.assertIn(needle, credits)


def _native_ready() -> bool:
    return NG is not None and NG.available() and T._ready("fish") and T._ready("plant")


def ink_columns(piece) -> list[bool]:
    return [any(piece.data[(y * piece.w + x) * 4 + 3] for y in range(piece.height)) for x in range(piece.w)]


def colours(piece) -> set[str]:
    """The flag's own colours among its solid pixels (premultiplied B, G, R, A)."""
    seen = set()
    for i in range(0, len(piece.data), 4):
        b, g, r, a = piece.data[i:i + 4]
        if a < 250:
            continue
        if r > 150 and g < 90 and b < 90:
            seen.add("red")
        elif r > 200 and g > 200 and b > 200:
            seen.add("white")
        elif b > 90 and r < 90 and g < 120:
            seen.add("blue")
    return seen


@unittest.skipUnless(os.name == "nt" and _native_ready(), "needs Windows, the pinned MSVC toolset, Unicorn and the games")
class NativeFlagTests(unittest.TestCase):
    servers: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.servers = {"fish": NG.GlyphServer("fish"), "plant": NG.GlyphServer("plant"),
                       "bare": NG.GlyphServer("fish", fonts=False)}
        import test_unicode_drawing as D
        cls.chain = D.dll_chain()

    @classmethod
    def tearDownClass(cls) -> None:
        for server in cls.servers.values():
            server.close()

    def test_a_flag_is_one_colour_picture(self) -> None:
        for game, style in (("fish", 0), ("fish", 1), ("fish", 2), ("plant", 0)):
            server = self.servers[game]
            server.pen(style, 0)
            smile = server.raster([0x1F600])
            for name, cps, want in (("JP", JP, {"red", "white"}), ("US", US, {"red", "white", "blue"}),
                                    ("FR", FR, {"red", "white", "blue"}), ("GB-ENG", GB_ENG, {"red", "white"})):
                with self.subTest(game=game, style=style, flag=name):
                    piece = server.raster(cps)
                    self.assertEqual(piece.kind, 2)
                    self.assertEqual(self.chain[piece.drawn_by], "Twemoji Mozilla")
                    self.assertTrue(all(ink_columns(piece)), "a gap inside: two letters, not one flag")
                    self.assertLessEqual(piece.adv, smile.adv * 3 // 2)        # one emoji wide
                    self.assertGreater(piece.w, smile.w // 2)
                    self.assertEqual(colours(piece) & want, want)

    def test_without_the_shipped_fonts_a_flag_is_its_two_letters_as_before(self) -> None:
        server = self.servers["bare"]
        server.pen(0, 0)
        piece = server.raster(JP)
        self.assertEqual(self.chain[piece.drawn_by], "Segoe UI Emoji")
        self.assertNotEqual(piece.kind, 0)

    def test_other_emoji_are_unchanged(self) -> None:
        with_fonts, bare = self.servers["fish"], self.servers["bare"]
        for style in (0, 1, 2):
            with_fonts.pen(style, 0)
            bare.pen(style, 0)
            for cps in OTHER_EMOJI:
                with self.subTest(style=style, cps=[hex(c) for c in cps]):
                    a, b = with_fonts.raster(cps), bare.raster(cps)
                    self.assertEqual(self.chain[a.drawn_by], "Segoe UI Emoji")
                    self.assertEqual((a.kind, a.w, a.xoff, a.adv, a.data), (b.kind, b.w, b.xoff, b.adv, b.data))


class FlagPieceCase:
    game = "fish"

    def setUp(self) -> None:
        self.base = G.GlyphCase()
        self.base.game = self.game
        self.base.setUp()
        self.pieces: list[tuple[int, ...]] = []
        self.base.fde.emu.hook(self.base.symbols["_raster_cluster"], self._cluster, 0)

    def _cluster(self, e) -> int:
        cps_at, n, height, coverage, w_at, xoff_at, adv_at = (e.arg(i) for i in range(7))
        self.pieces.append(tuple(e.read32(cps_at + 4 * k) for k in range(n)))
        e.uc.mem_write(coverage, b"\xFF" * (5 * height))
        e.write32(w_at, 5)
        e.write32(xoff_at, 0)
        e.write32(adv_at, 7)
        return 1

    def test_a_flag_is_asked_for_as_one_piece(self) -> None:
        b = self.base
        for cps in (JP, US, GB_ENG):
            with self.subTest(cps=[hex(c) for c in cps]):
                self.pieces.clear()
                text = "x" + "".join(chr(c) for c in cps) + "y"
                b.draw(text.encode("utf-8"))
                self.assertEqual(self.pieces, [tuple(cps)])
                self.assertEqual(b.width(text.encode("utf-8")), b.width(b"xy", own=True) + 7 + b.spacing)


@needs("fish")
class FishFlagPieceTests(FlagPieceCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantFlagPieceTests(FlagPieceCase, unittest.TestCase):
    game = "plant"


if __name__ == "__main__":
    unittest.main()
