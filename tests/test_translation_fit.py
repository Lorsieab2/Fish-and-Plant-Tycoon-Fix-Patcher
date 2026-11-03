"""Translated lines that do not fit their spot on the screen (src/translation_fit.py,
data/translation_limits.json written by scripts/build_translation_limits.py):

* the data file has every patcher text's key, sane pixel widths, and the C header is what the
  JSON makes (no game needed: CI runs these);
* with the vanilla games and Unicorn: the census run again gives exactly the committed file, the
  rooms it finds agree with the places Picture Studio's screens put the words (themselves checked
  against the games' own draws), and every message box limit is the widest text the game's box
  keeps on the screen (one more pixel and a piece leaves it);
* the validator warns (never refuses) a line wider than its room, naming the key, the width and the
  room, measured in the game's own font, for long German-like, Chinese, Thai, Arabic and emoji lines.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_translation_limits as L  # noqa: E402
import translation_fit as tfit  # noqa: E402
import translation_format as tfmt  # noqa: E402
import translation_strings as ts  # noqa: E402

try:
    import capstone  # noqa: F401
    import unicorn  # noqa: F401
    import draw_emulator as de
    EMULATOR = de.available("fish") and de.available("plant")
except ImportError:
    EMULATOR = False

VANILLA = L.VANILLA
GAMES_HERE = all((L.FOLDERS[g] / ts.EXE_NAMES[g]).is_file() for g in ("fish", "plant"))

LONG_GERMAN = ("Donaudampfschifffahrtsgesellschaftskapitänswitwenrentenauszahlungsstelle und "
               "Grundstücksverkehrsgenehmigungszuständigkeitsübertragungsverordnung")
CJK = "这是一个非常长的中文句子没有任何空格所以游戏必须在字符之间断行才能显示在屏幕上" * 2
THAI = "นี่คือประโยคภาษาไทยที่ยาวมากและไม่มีช่องว่างระหว่างคำเลยเพราะภาษาไทยไม่ใช้ช่องว่าง" * 2
ARABIC = "هذه جملة عربية طويلة جدا تحتوي على كلمات كثيرة لكي نرى هل تتسع على الشاشة أم لا " * 3
EMOJI = "🐟🐠🐡🦈🐙🦑🦀🦞🐚🌊" * 12


def data() -> dict:
    return json.loads(L.DATA.read_text(encoding="utf-8"))


class DataFile(unittest.TestCase):
    def test_shape_and_numbers(self) -> None:
        d = data()
        self.assertEqual(d["version"], L.VERSION)
        self.assertEqual(d["screen"], [800, 600])
        for game in ("fish", "plant"):
            lines = d["games"][game]["lines"]
            self.assertGreater(len([k for k in lines if k.startswith("strings/")]), 200)
            for key, e in lines.items():
                self.assertIn(e["font"], (0, 1, 2), key)
                if e["width"] is None:
                    self.assertEqual(e["kind"], "windows popup", key)
                    continue
                self.assertTrue(0 < e["width"] <= 800, key)
                self.assertIsInstance(e["multiline"], bool)
                if e["proven"]:
                    self.assertTrue(e["kind"] != "safe rule" and (e.get("where") or key.startswith("mod/")), key)
                else:
                    self.assertEqual(e["kind"], "safe rule", key)
            for kind, (w, h) in d["games"][game]["boxes"].items():
                self.assertTrue(0 < w <= 800 and 0 < h <= 600, kind)

    def test_no_game_text_in_the_file(self) -> None:
        """Numbers only: the patcher never ships the games' text."""
        text = L.DATA.read_text(encoding="utf-8")
        for word in ("Your cash", "Please register", "Gardening Supplies"):
            self.assertNotIn(word, text)

    def test_every_patcher_text_has_its_room(self) -> None:
        d = data()
        for game in ("fish", "plant"):
            lines = d["games"][game]["lines"]
            for e in ts.mod_entries(game):
                base = tfit.base_of(e.key)
                self.assertIn(base, lines, e.key)
                self.assertEqual(lines[base]["width"] is None, e.wide, e.key)

    def test_the_header_is_what_the_json_makes(self) -> None:
        self.assertEqual(L.HEADER.read_text(encoding="utf-8"), L.render_header(data()))

    def test_safe_rule(self) -> None:
        self.assertEqual(L.safe_limit(0), 800)
        self.assertEqual(L.safe_limit(40), 56)            # at least 16 more
        self.assertEqual(L.safe_limit(200), 250)          # a quarter more
        self.assertEqual(L.safe_limit(700), 800)          # never past the screen

    def test_limits_are_read(self) -> None:
        key = tfmt.make_key("strings", "1", "Age: ")
        limit = tfit.limit_for("fish", key)
        self.assertIsNotNone(limit)
        self.assertEqual(limit, tfit.limits("fish")["strings/1"])


def fake_measure(_font: int, line: str) -> int:
    return 10 * len(line)


class Validator(unittest.TestCase):
    def make(self, translation: str) -> tfmt.TranslationFile:
        entries = [tfmt.Entry(tfmt.make_key("strings", "1", "Age: "), "Age: ")]
        f = tfmt.new_file("fish", entries, "Deutsch", "de")
        f.rows[0].translation = translation
        return tfmt.parse_bytes(tfmt.to_bytes(f), "fish"), entries

    def test_too_wide_is_a_warning_naming_key_width_and_room(self) -> None:
        limit = tfit.Limit(100, 0, False, True, "left")
        tf, entries = self.make("Alter des Fisches in Tagen: ")
        widths = lambda key, english, t: (  # noqa: E731
            (w.message() if (w := tfit.too_wide("fish", key, t, fake_measure, limit)) else None))
        report = tfmt.validate(tf, entries, widths)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.translated, 1)              # still used: width never refuses a line
        self.assertTrue(report.usable)
        [warning] = report.warnings
        self.assertEqual(warning.key, entries[0].key)
        self.assertIn("280 pixels", warning.message)
        self.assertIn("room is 100 pixels", warning.message)
        self.assertIn("line 1", warning.message)

    def test_fits_no_warning(self) -> None:
        limit = tfit.Limit(100, 0, False, True, "left")
        self.assertIsNone(tfit.too_wide("fish", "strings/1~00000000", "Alter: ", fake_measure, limit))
        self.assertIsNone(tfit.too_wide("fish", "x", "Alter: " * 40, fake_measure, tfit.Limit(None)))

    def test_the_line_that_is_too_wide(self) -> None:
        limit = tfit.Limit(100, 0, True, False, "safe rule")
        found = tfit.too_wide("fish", "k", "short\n" + "x" * 11 + "\nok", fake_measure, limit)
        self.assertEqual((found.line, found.width, found.room), (2, 110, 100))
        self.assertIn("safe rule", found.message())
        self.assertIn("re-breaks", found.message())

    def test_choices_at_their_longest(self) -> None:
        limit = tfit.Limit(100, 0, False, True, "left")
        self.assertIsNotNone(tfit.too_wide("fish", "k", "{%1: one=a | other=" + "b" * 11 + "}", fake_measure, limit))


@unittest.skipUnless(GAMES_HERE, "the vanilla games (their fonts)")
class RealFonts(unittest.TestCase):
    """The game's own fonts (with the patcher-made and Windows-drawn letters the Text Maker adds)."""

    def test_worst_case_lines_warn_with_real_widths(self) -> None:
        for game in ("fish", "plant"):
            check = tfit.checker(game, [str(L.FOLDERS[game])])
            self.assertIsNotNone(check)
            proven = next(base for base, lim in tfit.limits(game).items()
                          if lim.proven and lim.width and base.startswith("strings/"))
            key = proven.replace("/", "/", 1) + "~00000000"
            for line in (LONG_GERMAN, CJK, THAI, ARABIC, EMOJI):
                message = check(key, "English", line)
                self.assertIsNotNone(message, (game, line[:10]))
                self.assertIn("too wide for its spot", message)
            self.assertIsNone(check(key, "English", "Ok"))


@unittest.skipUnless(EMULATOR and GAMES_HERE, "the vanilla games, Unicorn and capstone")
class Census(unittest.TestCase):
    def test_message_box_limits_are_the_games_own(self) -> None:
        """At the recorded widest text the game's box is on the screen; one pixel more and it is not."""
        for game in ("fish", "plant"):
            boxes = data()["games"][game]["boxes"]
            c = L.composer(game)
            for kind, (w, h) in boxes.items():
                ident = L.BOX_SAMPLE[(game, kind)]
                sample = c._game()[2][ident] if ident is not None else L.TIP_SAMPLE
                w0, h0 = c.text_size(0, sample)
                self.assertTrue(L.on_screen(L._box_run(game, kind, w - w0, 0, sample)), (game, kind))
                self.assertFalse(L.on_screen(L._box_run(game, kind, w - w0 + 1, 0, sample)), (game, kind))
                self.assertTrue(L.on_screen(L._box_run(game, kind, 0, h - h0, sample)), (game, kind))
                self.assertFalse(L.on_screen(L._box_run(game, kind, 0, h - h0 + 1, sample)), (game, kind))

    def test_rooms_agree_with_picture_studio(self) -> None:
        """Words Picture Studio places (checked against the games' draws by
        tests/test_picture_screen_draws.py): a left-placed word's room is at most the screen's from
        its x, a centred one's at most twice its centre's distance from the nearer edge."""
        import pictures_screens as S
        d = data()
        checked = 0
        for game, keys in (("plant", ("screen:menu", "screen:greenhouse")), ("fish", ("screen:menu",))):
            c = L.composer(game)
            lines = d["games"][game]["lines"]
            for key in keys:
                for p in c.pieces(S.by_key(game)[key]):
                    if p.text is None or len(p.text.parts) != 1 or p.text.parts[0][0] != "id":
                        continue
                    entry = lines.get(f"strings/{p.text.parts[0][1]}")
                    if not entry or not entry["proven"]:
                        continue
                    data_, x, _y, w, _h = c.text_place(p)
                    if p.text.align == "left":
                        self.assertLessEqual(entry["width"], max(800 - x, w), (game, key, data_))
                    elif p.text.align in ("centre", "button"):
                        centre = x + w / 2
                        self.assertLessEqual(entry["width"], max(2 * min(centre, 800 - centre), w), (game, key, data_))
                    checked += 1
        self.assertGreater(checked, 5)

    def test_the_census_makes_the_committed_file(self) -> None:
        """The whole census again (a few minutes): the committed JSON is exactly what it writes."""
        self.assertEqual(L.dumps(L.build()), L.DATA.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
