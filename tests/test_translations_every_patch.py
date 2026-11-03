"""Translations.dll in Unicorn with every patcher DLL: each DLL's texts follow the translation.

For one text of every patcher DLL (the DLL mapped beside the game, as the startup loader leaves
it): a translated line is what every pointer of the DLL to that text now shows; a line too long
for its space, and a line the file lacks, leave the English. Unused Flowers builds its species
names again from the translated words (FtfpTranslationApplied).

The counted texts (src/translation_strings.py COUNTED_STRINGS: "2 doses left", the Time Warp's
questions...) go through FtfpTranslateCounted with the real numbers: every one of them is
translated with its choices made by the number, a too-long one and a missing one give -1 (the
DLL writes its English), and nothing is ever written past the caller's space.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import translation_format as tf  # noqa: E402
import translation_strings as ts  # noqa: E402
import translations_emulator as te  # noqa: E402
from test_translations_runtime import _pointer_slots, make, runtime  # noqa: E402

BASE = 0x50000000
GAME_LINE = (1, "Age: ", "\xc2ge : ")

# (game, DLL, its asset folder, a text of it, a translation, a translation too long for its space)
CASES = [
    ("fish", "Tank Counts.dll", "fish_tycoon_counts", "Fish: ", "Poissons : ", "P" * 1001),
    ("fish", "DS Exclusive Fish.dll", "fish_tycoon_ds", "Tiger ", "Tigr\xe9 ", "Tigre magnifique "),
    ("fish", "DS Store Items.dll", "fish_tycoon_ds_store", "Treated: $", "Trait\xe9 : $", "T" * 37),
    ("fish", "Extra Tanks.dll", "fish_tycoon_extra_tanks", "You don't own this tank yet!",
     "Cet aquarium n'est pas encore \xe0 toi !", "C" * 1001),
    ("fish", "Extra Supply Slots.dll", "fish_tycoon_supply_slots", "You don't own the extra supply slots yet!",
     "Les emplacements en plus ne sont pas encore \xe0 toi !", "L" * 1001),
    ("fish", "Optimize Prices.dll", "fish_tycoon_optimize_prices",
     "Set every discovered species\nto its best price per day?", "Meilleur prix par jour\npour chaque esp\xe8\x63\x65 ?",
     "M" * 1001),
    ("plant", "Greenhouse Counts.dll", "plant_tycoon_counts", "Plants: ", "Plantes : ", "P" * 1001),
    ("plant", "Extra Greenhouses.dll", "plant_tycoon_greenhouses", "Greenhouse ", "Serre ", "S" * 41),
    ("plant", "Optimize Prices.dll", "plant_tycoon_optimize_prices",
     "Set every discovered species\nto its best price per day?", "Meilleur prix par jour ?", "M" * 1001),
    ("plant", "Sort Seeds.dll", "plant_tycoon_sort_seeds",
     "Sort Seeds in Seed Boxes?\n\nThis will rearrange all seeds throughout\nyour available seed boxes. Some may "
     "move\nto other pages.\nClick YES to Confirm, NO to Cancel.", "Trier les graines ?", "T" * 1001),
    ("plant", "Extra Seed Boxes.dll", "plant_tycoon_upgrades", "Boxes 1-3", "Bo\xeetes 1-3", "B" * 1001),
    ("plant", "Store Upgrades and Items.dll", "plant_tycoon_upgrades", "Extra Seed Box", "Bo\xeete", "B" * 15),
    ("plant", "Unused Flowers.dll", "plant_tycoon_flowers", "Nightingale", "Rossignol", "R" * 25),
]


def _mod(game: str, dll: str, english: str, wide: bool = False) -> ts.ModString:
    return next(m for m in ts.MOD_STRINGS if (m.game, m.dll, m.english, m.wide) == (game, dll, english, wide))


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class EveryDll(unittest.TestCase):
    def check(self, game, dll, folder, english, translation, too_long) -> None:
        m = _mod(game, dll, english)
        key = ts.mod_key(m)
        data = (ROOT / "assets" / folder / dll).read_bytes()
        slots = _pointer_slots(te.relocate(data, BASE), BASE, english.encode("cp1252") + b"\0")
        self.assertTrue(slots, f"{dll} has no pointer to {english!r}")
        others = [x for x in ts.MOD_STRINGS if x.dll == dll and x.game == game and not x.wide and not x.counted
                  and x.english != english]
        # translated
        rt = runtime(game, make(game, [(key, english, translation), GAME_LINE]), dlls={dll: (data, BASE)})
        self.assertEqual(rt.start(), 1, rt.log)
        for slot in slots:
            self.assertEqual(rt.emu.cstring(rt.emu.read32(slot)), translation.encode("cp1252"), (dll, english))
        for other in others[:3]:                             # the DLL's other texts: not in the file, English
            for slot in _pointer_slots(te.relocate(data, BASE), BASE, other.english.encode("cp1252") + b"\0"):
                self.assertEqual(rt.emu.cstring(rt.emu.read32(slot)), other.english.encode("cp1252"), other.english)
        # too long for its space: English, and the log says why
        self.assertGreater(len(too_long.encode("utf-8")), ts.mod_limit(m))
        rt = runtime(game, make(game, [(key, english, too_long), GAME_LINE]), dlls={dll: (data, BASE)})
        self.assertEqual(rt.start(), 1, rt.log)
        for slot in slots:
            self.assertEqual(rt.emu.cstring(rt.emu.read32(slot)), english.encode("cp1252"), (dll, english))
        self.assertIn("too long", rt.log)
        # missing from the file: English
        rt = runtime(game, make(game, [GAME_LINE]), dlls={dll: (data, BASE)})
        self.assertEqual(rt.start(), 1, rt.log)
        for slot in slots:
            self.assertEqual(rt.emu.cstring(rt.emu.read32(slot)), english.encode("cp1252"), (dll, english))
        return rt

    def test_every_dll(self) -> None:
        for case in CASES:
            with self.subTest(dll=case[1], game=case[0]):
                self.check(*case)

    def test_every_dll_with_texts_has_a_case(self) -> None:
        covered = {(c[0], c[1]) for c in CASES}
        for m in ts.MOD_STRINGS:
            if not m.counted:
                self.assertIn((m.game, m.dll), covered, m.dll)

    def test_a_popup_text_is_translated_as_utf16(self) -> None:
        dll, english = "Store Upgrades and Items.dll", "You already have the extra chemical slots!"
        m = _mod("plant", dll, english, wide=True)
        data = (ROOT / "assets" / "plant_tycoon_upgrades" / dll).read_bytes()
        slots = _pointer_slots(te.relocate(data, BASE), BASE, english.encode("utf-16-le") + b"\0\0")
        self.assertTrue(slots)
        rt = runtime("plant", make("plant", [(ts.mod_key(m), english, "Tu as d\xe9j\xe0 les emplacements !"),
                                             GAME_LINE]), dlls={dll: (data, BASE)})
        self.assertEqual(rt.start(), 1, rt.log)
        for slot in slots:
            self.assertEqual(rt.emu.wstring(rt.emu.read32(slot)), "Tu as d\xe9j\xe0 les emplacements !")

    def test_unused_flowers_builds_its_names_again(self) -> None:
        dll = "Unused Flowers.dll"
        data = (ROOT / "assets" / "plant_tycoon_flowers" / dll).read_bytes()
        rows = [(ts.mod_key(_mod("plant", dll, "Nightingale")), "Nightingale", "Rossignol"),
                (ts.mod_key(_mod("plant", dll, "Fern")), "Fern", "Foug\xe8re"), GAME_LINE]
        rt = runtime("plant", make("plant", rows), dlls={dll: (data, BASE)})
        self.assertEqual(rt.start(), 1, rt.log)
        image = bytes(rt.emu.uc.mem_read(BASE, te.se.pe_image(data)[1]))
        self.assertIn("Rossignol Foug\xe8re\0".encode("cp1252"), image)
        self.assertIn(b"Rossignol Reptans\0", image)               # a word not translated stays English
        self.assertIn("Lilac Foug\xe8re\0".encode("cp1252"), image)


def _numbers_for(english: str) -> int:
    return len(tf.parse_template(english).conversions)


def _expected(translation: str, code: str, numbers: list[int], encoding: str) -> bytes:
    text = tf.evaluate(translation, code, {f"%{k + 1}": n for k, n in enumerate(numbers)})
    values = iter(numbers)
    text = re.sub(r"%%|%[di]", lambda m: "%" if m.group() == "%%" else str(next(values)), text)
    return text.encode(encoding)


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class CountedTexts(unittest.TestCase):
    def counted(self, rt: te.Runtime, english: str, wide: bool, numbers: list[int], cap: int) -> tuple[int, bytes]:
        e = rt.emu
        text = e.alloc(len(english) * 2 + 8)
        e.uc.mem_write(text, english.encode("utf-16-le" if wide else "cp1252") + b"\0\0")
        values = e.alloc(4 * max(1, len(numbers)))
        for k, n in enumerate(numbers):
            e.write32(values + 4 * k, n & 0xFFFFFFFF)
        out = e.alloc(cap * 2 + 64)
        e.uc.mem_write(out, b"\xAA" * (cap * 2 + 64))
        result = e.call(e.sym("_FtfpTranslateCounted@24"), text, int(wide), values, len(numbers), out, cap)
        raw = bytes(e.uc.mem_read(out, cap * 2 + 64))
        unit = 2 if wide else 1
        self.assertEqual(raw[cap * unit:], b"\xAA" * (cap * (2 - unit) + 64), "written past the caller's space")
        if result & 0x80000000:
            return -1, b""
        return result, raw[:result * unit]

    def test_every_counted_text(self) -> None:
        for game in ("fish", "plant"):
            texts = [m for m in ts.MOD_STRINGS if m.game == game and m.counted]
            rows = []
            for m in texts:
                # each word's letters swapped in case, the placeholders and choices kept
                translation = re.sub(r"(?<![%A-Za-z])([A-Za-z]+)(?![A-Za-z:=])", lambda x: x.group(1).swapcase(),
                                     m.english)
                self.assertEqual(tf.check_translation(m.english, translation)[0], [], translation)
                rows.append((ts.mod_key(m), m.english, translation))
            rt = runtime(game, make(game, rows + [GAME_LINE], code="en", language="English"))
            self.assertEqual(rt.start(), 1, rt.log)
            for m, (_k, _e, translation) in zip(texts, rows):
                for numbers in ([1] * _numbers_for(m.english), [2, 500, 2][:_numbers_for(m.english)]):
                    got, out = self.counted(rt, m.english, m.wide, numbers, 400)
                    want = _expected(translation, "en", numbers, "utf-16-le" if m.wide else "cp1252")
                    self.assertEqual(out, want, (m.dll, m.english, numbers))
                    self.assertEqual(got, len(want) // (2 if m.wide else 1))
                # the caller's space is too small: -1, nothing past it
                self.assertEqual(self.counted(rt, m.english, m.wide, [1] * _numbers_for(m.english), 4)[0], -1)
            # an English the file lacks (or another game's): -1, the DLL writes its English
            self.assertEqual(self.counted(rt, "%d {%1: one=nothing | other=nothings}", False, [1], 64)[0], -1)

    def test_choices_use_the_real_number(self) -> None:
        m = next(m for m in ts.MOD_STRINGS if m.counted and m.dll == "Extra Chemical Slots.dll")
        translation = "Осталось %d {%1: one=доза | " \
                      "few=дозы | many=доз | other=дозы}"
        rt = runtime("plant", make("plant", [(ts.mod_key(m), m.english, translation), GAME_LINE], code="ru",
                                   language="Русский"), unicode_active=1)
        self.assertEqual(rt.start(), 1, rt.log)
        for n, word in ((1, "доза"), (3, "дозы"), (5, "доз"),
                        (21, "доза"), (12, "доз")):
            got, out = self.counted(rt, m.english, False, [n], 96)
            self.assertEqual(out.decode("utf-8"), f"Осталось {n} {word}")

    def test_a_counted_text_too_long_for_its_space_shows_english(self) -> None:
        m = next(m for m in ts.MOD_STRINGS if m.counted and m.dll == "Tank Counts.dll")
        too_long = "%d " + "x" * (ts.mod_limit(m) + 1)
        rt = runtime("fish", make("fish", [(ts.mod_key(m), m.english, too_long), GAME_LINE]))
        self.assertEqual(rt.start(), 1, rt.log)
        self.assertIn("too long", rt.log)
        self.assertEqual(self.counted(rt, m.english, False, [3], 48)[0], -1)

    def test_a_counted_text_is_never_pointed_at(self) -> None:
        dll = "Optimize Prices.dll"
        m = next(m for m in ts.MOD_STRINGS if m.counted and m.dll == dll and m.game == "plant")
        data = (ROOT / "assets" / "plant_tycoon_optimize_prices" / dll).read_bytes()
        rt = runtime("plant", make("plant", [(ts.mod_key(m), m.english, "%d {%1: one=prix | other=prix} fix\xe9s."),
                                             GAME_LINE]), dlls={dll: (data, BASE)})
        self.assertEqual(rt.start(), 1, rt.log)
        for slot in _pointer_slots(te.relocate(data, BASE), BASE, m.english.encode("cp1252") + b"\0"):
            self.assertEqual(rt.emu.cstring(rt.emu.read32(slot)), m.english.encode("cp1252"))
        self.assertEqual(self.counted(rt, m.english, False, [1], 48)[1], "1 prix fix\xe9s.".encode("cp1252"))

    def test_without_a_translation_every_call_is_english(self) -> None:
        m = next(m for m in ts.MOD_STRINGS if m.counted and m.wide and m.game == "fish")
        rt = runtime("fish", None)
        self.assertEqual(rt.start(), 0)
        self.assertEqual(self.counted(rt, m.english, True, [1, 2, 3][:_numbers_for(m.english)], 256)[0], -1)


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class PercentSigns(unittest.TestCase):
    """"2 %" (French typography): plain text, escaped "%%" only where the line is a format."""
    TEXTS = ["2 %", "2\u00a0%", "2\u202f%", "50 % de r\u00e9duction"]

    def test_fish_goals_line_is_a_format(self) -> None:
        english = "You have sold %d fish!"
        for text in self.TEXTS:
            rt = runtime("fish", make("fish", [(69, english, f"%d vendus, {text}"), (1, "Age: ", text)]))
            self.assertEqual(rt.start(), 1, rt.log)
            # what the lookup hands the game's sprintf: every plain '%' as "%%"
            self.assertEqual(rt.lookup(69), f"%d vendus, {text.replace('%', '%%')}".encode("cp1252", "replace"))
            # which sprintf prints with one '%'
            self.assertEqual(rt.lookup(69).decode("cp1252") % 5, f"5 vendus, {text}".replace("\u202f", "?"))
            # a line that is not a format: as written
            self.assertEqual(rt.lookup(1), text.encode("cp1252", "replace"))

    def test_plant_dll_format_and_counted_text(self) -> None:
        dll = "Store Upgrades and Items.dll"
        data = (ROOT / "assets" / "plant_tycoon_upgrades" / dll).read_bytes()
        fmt = _mod("plant", dll, "%sPrice: $ %i")
        counted = next(m for m in ts.MOD_STRINGS if m.counted and m.dll == "Extra Chemical Slots.dll")
        rows = [(ts.mod_key(fmt), fmt.english, "%s2 % $ %i"),
                (ts.mod_key(counted), counted.english, "%d {%1: one=dose | other=doses} (50 % de r\u00e9duction)"),
                GAME_LINE]
        rt = runtime("plant", make("plant", rows), dlls={dll: (data, BASE)})
        self.assertEqual(rt.start(), 1, rt.log)
        slots = _pointer_slots(te.relocate(data, BASE), BASE, fmt.english.encode("cp1252") + b"\0")
        self.assertTrue(slots)
        for slot in slots:                                   # the DLL sprintf's it: "%%"
            self.assertEqual(rt.emu.cstring(rt.emu.read32(slot)), b"%s2 %% $ %i")
        got, out = CountedTexts.counted(self, rt, counted.english, False, [3], 96)
        self.assertEqual(out, "3 doses (50 % de r\u00e9duction)".encode("cp1252"))   # one '%', as shown


if __name__ == "__main__":
    unittest.main()
