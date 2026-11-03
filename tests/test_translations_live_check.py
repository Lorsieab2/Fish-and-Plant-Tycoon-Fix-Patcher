"""The first live check of v1.0.26 with the French (TEST) translation (translations/<game>/fr.tsv)
found French text running off the screen. The owner's rule: "i dont care if things run out of boxes,
they just need to not run off the screen" (the screen is 800 pixels wide). Each case again, in Unicorn:
the same French lines through Translations.dll (fitted with the game's measure answering the fonts' real
widths) and drawn where the game (or the patcher DLL) draws them. Every line's drawn right edge must be
at most 800; staying clear of a neighbouring box, word or check box is NOT required.

1. The Counts button: "Compteurs : oui" drawn by Tank Counts.dll / Greenhouse Counts.dll from x 694
   (Plant: 646 under the Extra Greenhouses arrows) ran off the right edge (screenshots 18, 26, 27): it is
   now drawn whole, moved left to end at x 796.
2. Plant Options: "Morceaux de musique", "Arreter le temps" draw whole (they fit before x 800).
3. Plant greenhouse panel: "ARGENT", "Poubelle", "Pepiniere" draw whole (26, 27).
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import translation_fit as tfit  # noqa: E402
import translations_emulator as te  # noqa: E402

try:
    import test_translations_fit_runtime as R
    from test_translations_runtime import _pointer_slots
    READY = R.READY
except ImportError:
    READY = False

COUNTS = {"fish": ("Tank Counts.dll", ROOT / "assets" / "fish_tycoon_counts" / "Tank Counts.dll", "tank_counts"),
          "plant": ("Greenhouse Counts.dll", ROOT / "assets" / "plant_tycoon_counts" / "Greenhouse Counts.dll",
                    "greenhouse_counts")}
BASE = 0x50000000


def french(game: str):
    """The French test translation through Translations.dll, the game's fonts made: (runtime, fonts)."""
    data = (ROOT / "translations" / game / "fr.tsv").read_bytes()
    name, path, _slug = COUNTS[game]
    rt = te.Runtime(game, {R.INI[game]: te.ini(R.PATH), R.PATH: data}, dlls={name: (path.read_bytes(), BASE)})
    rt.emu.call_count = 2_000_000_000
    if game == "plant":
        rt.hook_plant_table()
    fonts = R.Fonts(rt, game, False)
    assert rt.start() == 1
    rt.lookup(1)                                   # the first lookup with the fonts made: every line fitted
    return rt, fonts


def overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@unittest.skipUnless(READY, "MSVC, Unicorn, capstone, the vanilla games and Translations.dll")
class CountsButton(unittest.TestCase):
    """1. "Compteurs : oui" / "non" where the Counts DLL draws it."""

    def check(self, game: str, starts) -> None:
        rt, fonts = french(game)
        name, path, slug = COUNTS[game]
        image = te.relocate(path.read_bytes(), BASE)
        for english, french_text in ((b"Counts: On\0", "Compteurs : oui"), (b"Counts: Off\0", "Compteurs : non")):
            slots = _pointer_slots(image, BASE, english)
            self.assertTrue(slots, english)
            shown = rt.emu.cstring(rt.emu.read32(slots[0]))
            limit = tfit.limits(game)[f"mod/{slug}.{'counts_on' if b'On' in english else 'counts_off'}"]
            self.assertTrue(limit.proven)
            self.assertEqual(limit.width, 796)                             # the room is the screen's edge
            w = fonts.size(0, shown)[0]
            self.assertEqual(shown.replace(bytes([0xA0]), b" "), french_text.encode("cp1252"))   # whole, not cut
            self.assertLessEqual(w, limit.width)
            for start in starts:
                # count_toggle.h's toggle_label: from `start`, or moved left to end at 796
                x = start if start + w <= 796 else 796 - w
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x + w + 1, 800, (game, shown))        # with its shadow, on the screen
                print(f"{game} {shown.decode('cp1252')!r} from {start}: drawn x {x} to {x + w}")

    def test_fish(self) -> None:
        self.check("fish", (694,))

    def test_plant(self) -> None:
        self.check("plant", (694, 646))


@unittest.skipUnless(READY, "MSVC, Unicorn, capstone, the vanilla games and Translations.dll")
class PlantScreens(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import translation_strings as ts
        rt, cls.fonts = french("plant")
        exe = (R.L.FOLDERS["plant"] / ts.EXE_NAMES["plant"]).read_bytes()
        cls.english = {s.id: s.english for s in ts.read_table("plant", exe)}
        cls.strings = {i: rt.lookup(i).decode("cp1252") for i in cls.english if i not in ts.NEVER_TRANSLATED["plant"]}

    def draw(self, scenario):
        r = R.L.Run("plant")
        r.d.strings.update(self.strings)
        r.d._string_at.clear()
        scenario(r)
        r.collect()
        c = R.L.composer("plant")
        texts = []
        for data, x, y, font in r.texts:
            w, h = c.text_size(font, data)
            texts.append((data.decode("cp1252"), (x, y, x + w, y + h)))
        return texts, r

    def text(self, texts, ident):
        found = [rect for t, rect in texts if t == self.strings[ident]]
        self.assertTrue(found, (ident, self.strings[ident]))
        return found[0]

    def test_options_dialog(self) -> None:
        """2. 0x2F "Morceaux de musique", 0x37 "Arreter le temps": drawn whole, on the screen."""
        texts, _r = self.draw(R.L._plant_options)
        for ident in (0x2F, 0x37):
            rect = self.text(texts, ident)
            print(f"options {self.strings[ident]!r}: x {rect[0]} to {rect[2]}")
        for t, rect in texts:
            self.assertLessEqual(rect[2], 800, t)

    def test_greenhouse_panel(self) -> None:
        """3. 0x3F "ARGENT", 0x190 "Poubelle", 0x180 "Pepiniere": drawn whole, on the screen."""
        def greenhouse(r):
            d = r.d
            d.emu.write32(d.game_state + 0x63E58, 99)
            d.emu.write32(d.game_state + 0x217C, 250)
            screen = d._zeroed(0x800)
            d.run(0x424BB0, this=screen)
            d.show(screen)
        texts, _r = self.draw(greenhouse)
        for ident in (0x3F, 0x190, 0x180):
            rect = self.text(texts, ident)
            print(f"greenhouse {self.strings[ident]!r}: x {rect[0]} to {rect[2]}")
        for t, rect in texts:
            self.assertLessEqual(rect[2], 800, t)


if __name__ == "__main__":
    unittest.main()
