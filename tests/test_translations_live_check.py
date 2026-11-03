"""The first live check of v1.0.26 with the French (TEST) translation (translations/<game>/fr.tsv)
found French text running off the screen or into its neighbours. Each case again, in Unicorn: the
same French lines through Translations.dll (fitted with the game's measure answering the fonts' real
widths) and drawn where the game (or the patcher DLL) draws them.

1. The Counts button: "Compteurs : oui" drawn by Tank Counts.dll / Greenhouse Counts.dll from x 694
   (Plant: 646 under the Extra Greenhouses arrows) ran off the right edge (screenshots 18, 26, 27).
2. Plant Options: "Morceaux de musique" under the check boxes, "Arreter le temps" into "Lente" (23).
3. Plant greenhouse panel: "ARGENT" into "$250", "Poubelle" over its frame, "Pepiniere" off the right
   edge (26, 27).
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

    def check(self, game: str, places) -> None:
        rt, fonts = french(game)
        name, path, slug = COUNTS[game]
        image = te.relocate(path.read_bytes(), BASE)
        for english, french_text in ((b"Counts: On\0", "Compteurs : oui"), (b"Counts: Off\0", "Compteurs : non")):
            slots = _pointer_slots(image, BASE, english)
            self.assertTrue(slots, english)
            shown = rt.emu.cstring(rt.emu.read32(slots[0]))
            limit = tfit.limits(game)[f"mod/{slug}.{'counts_on' if b'On' in english else 'counts_off'}"]
            self.assertTrue(limit.proven)
            w = fonts.size(0, shown)[0]
            self.assertGreater(fonts.size(0, french_text.encode("cp1252"))[0], limit.width, "the French was too wide")
            for x, right in places:
                self.assertLessEqual(x + w + 1, right, (game, shown))      # with its shadow, inside the screen
            self.assertTrue(shown.endswith(b"..."), shown)                 # cut: "oui" / "non" is not shown
            self.assertTrue(french_text.encode("cp1252").startswith(shown[:-3].rstrip()))

    def test_fish(self) -> None:
        self.check("fish", ((694, 800),))

    def test_plant(self) -> None:
        self.check("plant", ((694, 800), (646, 745)))


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
        """2. 0x2F "Morceaux de musique" clear of the first check box; 0x37 "Arreter le temps" clear of
        0x39 "Lente"."""
        texts, r = self.draw(R.L._plant_options)
        tracks = self.text(texts, 0x2F)
        # the four check boxes: the small pictures on the line's row
        boxes = [(x, y, x + w, y + h) for x, y, w, h in r.pictures
                 if (x, y, w, h) not in r.backdrop and w <= 64 and h <= 64 and y < tracks[3] and y + h > tracks[1]]
        self.assertEqual(len(boxes), 4, boxes)
        for cell in boxes:
            self.assertFalse(overlaps(tracks, cell), (self.strings[0x2F], tracks, cell))
        self.assertFalse(overlaps(self.text(texts, 0x37), self.text(texts, 0x39)),
                         (self.strings[0x37], self.strings[0x39]))
        for t, rect in texts:
            self.assertLessEqual(rect[2], 800, t)

    def test_greenhouse_panel(self) -> None:
        """3. 0x3F "ARGENT" clear of the cash; 0x190 "Poubelle" inside its room; 0x180 "Pepiniere"
        inside the screen."""
        def greenhouse(r):
            d = r.d
            d.emu.write32(d.game_state + 0x63E58, 99)
            d.emu.write32(d.game_state + 0x217C, 250)
            screen = d._zeroed(0x800)
            d.run(0x424BB0, this=screen)
            d.show(screen)
        texts, _r = self.draw(greenhouse)
        cash_label = self.text(texts, 0x3F)
        cash = [rect for t, rect in texts if t.startswith("$")]
        self.assertTrue(cash)
        self.assertFalse(any(overlaps(cash_label, c) for c in cash), (self.strings[0x3F], cash_label, cash))
        trash = self.text(texts, 0x190)
        self.assertLessEqual(trash[2] - trash[0], tfit.limits("plant")["strings/400"].width)
        nursery = [rect for t, rect in texts if t == self.strings[0x180]]
        self.assertTrue(nursery)
        for rect in nursery:
            self.assertLessEqual(rect[2], 800, self.strings[0x180])
        for t, rect in texts:
            self.assertLessEqual(rect[2], 800, t)


if __name__ == "__main__":
    unittest.main()
