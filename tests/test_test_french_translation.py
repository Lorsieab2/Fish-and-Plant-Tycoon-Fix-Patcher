"""The owner's "(TEST) - French AI Translation" of both games (translations/fish/ and translations/plant/):
a machine-made French file kept in the repository for testing and for "Download from GitHub...".

Each file must read with zero errors and zero warnings, have every line of the game's template (the
vanilla game's string table, as "Make a translation" reads it, plus every patch's text), keep every
placeholder of its English, fit every limit, carry the exact display name and credit, and hold no
email-like text."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import translation_format as tfmt  # noqa: E402
import translation_strings as tstr  # noqa: E402
import translations as tr  # noqa: E402
from store_emulator import VANILLA  # noqa: E402

LANGUAGE = "(TEST) - French AI Translation"
CREDIT = "(TEST) AI translation"
SPECIES_SOURCES = ("mod/ds_exclusive_fish.", "mod/unused_flowers.")   # names: kept in English on purpose
SAME_IN_FRENCH = {"OK", "Normal", "Options", "Menu", "Pollen", "Stats", "Version 1.0.3.1"}


def path_of(game: str) -> Path:
    return ROOT / "translations" / game / tfmt.file_name(tfmt.GAME_TITLES[game], LANGUAGE)


class TestFrenchFiles(unittest.TestCase):
    _entries: dict[str, list[tfmt.Entry]] = {}

    @classmethod
    def entries(cls, game: str) -> list[tfmt.Entry]:
        if game not in cls._entries:
            exe = VANILLA / tfmt.GAME_TITLES[game] / tstr.EXE_NAMES[game]
            if not exe.is_file():
                raise unittest.SkipTest(f"no vanilla {exe.name} at {exe.parent}")
            cls._entries[game] = tstr.entries_for(game, exe.read_bytes())
        return cls._entries[game]

    def parsed(self, game: str) -> tfmt.TranslationFile:
        return tfmt.parse_bytes(path_of(game).read_bytes(), game)

    def test_files_read_with_no_problems(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                tf = self.parsed(game)
                self.assertEqual(tf.fatal, "")
                self.assertEqual([str(p) for p in tf.problems], [])

    def test_validates_against_the_template_with_zero_errors(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                entries = self.entries(game)
                report = tfmt.validate(self.parsed(game), entries)
                self.assertTrue(report.usable)
                self.assertEqual([str(p) for p in report.errors], [])
                self.assertEqual([str(p) for p in report.warnings], [])
                self.assertEqual(report.english_changed, [])
                self.assertEqual(report.unknown, [])
                self.assertEqual(report.translated, len(entries))

    def test_every_template_key_is_present_and_translated(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                rows = {r.key: r for r in self.parsed(game).rows}
                for entry in self.entries(game):
                    self.assertIn(entry.key, rows)
                    self.assertTrue(rows[entry.key].translation, entry.key)

    def test_only_names_and_same_words_stay_english(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                for row in self.parsed(game).rows:
                    if row.translation == row.english:
                        self.assertTrue(row.key.startswith(SPECIES_SOURCES) or row.english in SAME_IN_FRENCH,
                                        row.key)

    def test_placeholders_match_the_english(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                for row in self.parsed(game).rows:
                    eng, fra = tfmt.parse_template(row.english), tfmt.parse_template(row.translation)
                    self.assertEqual([c.signature for c in eng.conversions], [c.signature for c in fra.conversions],
                                     row.key)
                    self.assertEqual(eng.variables, fra.variables, row.key)
                    self.assertEqual(fra.errors, [], row.key)
                    self.assertFalse(fra.lone_percent and not eng.lone_percent, row.key)

    def test_every_length_is_within_its_limit(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                rows = {r.key: r for r in self.parsed(game).rows}
                for entry in self.entries(game):
                    limit = entry.max_length or tstr.ABSOLUTE_MAX
                    self.assertLessEqual(tfmt.measure(rows[entry.key].translation, entry.wide), limit, entry.key)

    def test_plural_choices_are_french(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                for row in self.parsed(game).rows:
                    for select in tfmt.parse_template(row.translation).selects:
                        keys = {k for k, _ in select.branches}
                        self.assertEqual(select.kind, "number", row.key)
                        self.assertLessEqual(keys, {"one", "many", "other"}, row.key)
                        self.assertIn("one", keys, row.key)
                        self.assertIn("other", keys, row.key)
                self.assertEqual(tfmt.plural_category("fr", 0), "one")
                self.assertEqual(tfmt.plural_category("fr", 2), "other")

    def test_display_name_code_and_credit(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                tf = self.parsed(game)
                self.assertEqual(tf.language, LANGUAGE)
                self.assertEqual(tf.code, "fr")
                self.assertEqual(tf.translator, CREDIT)
                self.assertEqual(tf.game, tfmt.GAME_TITLES[game])
                info = tr.read_info(path_of(game), game)
                self.assertIsNotNone(info)
                self.assertTrue(info.shipped)
                self.assertEqual(info.language, LANGUAGE)
                self.assertEqual(info.translator, CREDIT)
                notes = next(i.notes for k, i in tf.items if k == "row" and getattr(i, "key", "") == "@translator")
                self.assertIn("for testing", notes)

    def test_no_email_like_text_and_only_windows_1252_letters(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                text = tfmt.decode_bytes(path_of(game).read_bytes())
                self.assertEqual(tfmt.find_emails(text), [])
                self.assertNotIn("@", text.replace("\n@format", "").replace("\n@game", "").replace(
                    "\n@language", "").replace("\n@code", "").replace("\n@translator", ""))
                for row in self.parsed(game).rows:
                    row.translation.encode("cp1252")

    def test_new_player_is_never_translated(self):
        for game in tfmt.GAME_TITLES:
            with self.subTest(game=game):
                for row in self.parsed(game).rows:
                    self.assertNotIn(row.english.strip().upper(), {"NEW PLAYER"}, row.key)


if __name__ == "__main__":
    unittest.main()
