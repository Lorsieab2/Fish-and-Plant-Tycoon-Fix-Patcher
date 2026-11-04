"""Translations.dll (native/ftfp_translations) in Unicorn, against the real games.

Each test writes a translation with src/translation_format.py, hands it to the DLL as the
chosen file (Translation.ini beside it), runs FtfpStartup() and then calls the game's own
string lookup -- the code the game draws every text through -- to see what the player would see:

* a translated line is returned (Fish Tycoon in English and in German, Plant Tycoon);
* a broken line (a placeholder added, the English column edited, a changed English, too long
  for the game's buffer, "NEW PLAYER") falls back to English and the log names its line;
* Fish Tycoon's counted lines choose their plural with the real number (the five sprintf calls);
* Plant Tycoon's lookup chains onto "Store Upgrades and Items.dll"'s jump;
* a patcher DLL's text is translated through its relocations;
* no choice, a file for the other game, a newer format or a broken encoding change nothing;
* the install-site checks: any other code at the lookup or a sprintf call: nothing is written;
* the C reader and the Python validator agree on which lines are usable, line by line.
"""

from __future__ import annotations

from pathlib import Path
import re
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import translation_format as tf  # noqa: E402
import translation_strings as ts  # noqa: E402
import translations_emulator as te  # noqa: E402

PATH = "C:\\Translations\\Test.txt"
INI = {"fish": te.FOLDERS["fish"] + "Translation.ini", "plant": te.FOLDERS["plant"] + "Translation.ini"}
FISH_ENGLISH = {1: "Age: ", 4: "Sick", 7: "Your cash: $", 11: "NEW PLAYER", 69: "You have sold %d fish!",
                70: "You have fed your fish %d times!"}


def make(game: str, rows: list[tuple[int | str, str, str]], code: str = "fr", language: str = "Français",
         title: str | None = None, fmt: str = "1") -> bytes:
    """A translation file: rows are (string id or a full key, English, translation)."""
    entries = []
    for ident, english, _t in rows:
        key = ident if isinstance(ident, str) else tf.make_key("strings", str(ident), english)
        entries.append(tf.Entry(key, english))
    f = tf.new_file(game, entries, language, code)
    for row, (_i, _e, translation) in zip(f.rows, rows):
        row.translation = translation
    if title is not None:
        f.set_info("@game", title, "")
    if fmt != "1":
        f.set_info("@format", fmt, fmt)
    return tf.to_bytes(f)


def runtime(game: str, data: bytes | None, **kw) -> te.Runtime:
    files = {} if data is None else {INI[game]: te.ini(PATH), PATH: data}
    rt = te.Runtime(game, files, **kw)
    if game == "plant":
        rt.hook_plant_table()
    return rt


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class FishLookup(unittest.TestCase):
    def test_a_translated_line_is_returned(self) -> None:
        rt = runtime("fish", make("fish", [(1, "Age: ", "Âge : ")]))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(1), "Âge : ".encode("cp1252"))
        self.assertEqual(rt.lookup(1, german=True), "Âge : ".encode("cp1252"))   # the choice wins over German
        self.assertEqual(rt.lookup(2), b"Status: ")                             # not in the file: English
        self.assertIn("installed (Fish Tycoon", rt.log)
        self.assertIn("1 lines used", rt.log)

    def test_a_broken_line_falls_back_to_english(self) -> None:
        rows = [(1, "Age: ", "Âge : "), (4, "Sick", "Malade {name}")]          # a variable the English lacks
        rt = runtime("fish", make("fish", rows))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(4), b"Sick")
        self.assertEqual(rt.lookup(1), "Âge : ".encode("cp1252"))
        line = next(n for n, text in enumerate(make("fish", rows).decode("utf-8-sig").split("\r\n"), 1)
                    if text.startswith("strings/4~"))
        self.assertIn(f"line {line}: the placeholders", rt.log)
        self.assertIn("1 line(s) show English", rt.log)

    def test_an_edited_english_column_falls_back(self) -> None:
        key = tf.make_key("strings", "4", "Sick")                               # the key of the real English
        rt = runtime("fish", make("fish", [(key, "Sick!", "Malade")]))
        self.assertEqual(rt.start(), 0)                                         # no usable line: nothing installed
        self.assertEqual(rt.lookup(4), b"Sick")
        self.assertIn("does not match the key", rt.log)

    def test_english_changed_since_the_file_was_made(self) -> None:
        rt = runtime("fish", make("fish", [(1, "Age:", "Âge :"), (4, "Sick", "Malade")]))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(1), b"Age: ")                                # the file's English is not the game's
        self.assertEqual(rt.lookup(4), b"Malade")

    def test_too_long_for_the_games_buffer(self) -> None:
        long = "Votre argent liquide, tout compris : $"                         # 7 is copied into a fixed buffer
        self.assertTrue(tf.too_long(long, ts.buffer_limit(len("Your cash: $"))))
        rt = runtime("fish", make("fish", [(7, "Your cash: $", long), (4, "Sick", "Malade")]))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(7), b"Your cash: $")
        self.assertIn("too long", rt.log)
        rt = runtime("fish", make("fish", [(7, "Your cash: $", "Argent : $")]))
        rt.start()
        self.assertEqual(rt.lookup(7), b"Argent : $")

    def test_new_player_is_never_translated(self) -> None:
        rt = runtime("fish", make("fish", [(11, "NEW PLAYER", "NOUVEAU JOUEUR"), (4, "Sick", "Malade")]))
        rt.start()
        self.assertEqual(rt.lookup(11), b"NEW PLAYER")
        self.assertEqual(rt.lookup(4), b"Malade")

    def _sprintf(self, rt: te.Runtime, ident: int, value: int) -> str:
        """The game's call at 0x4247FF (now this DLL's) with the line's text and a number; the
        game's own sprintf is formatted in Python (its CRT is not started in the emulator)."""
        e = rt.emu
        out: list[str] = []

        def sprintf(emu) -> int:
            fmt = emu.cstring(emu.arg(1)).decode("cp1252")
            text = fmt.replace("%d", str(emu.arg(2)))
            out.append(text)
            emu.uc.mem_write(emu.arg(0), text.encode("cp1252") + b"\0")
            return len(text)
        e.hook(0x0042B20B, sprintf, 0)
        call = bytes(e.uc.mem_read(0x004247FF, 5))
        self.assertEqual(call[0], 0xE8)
        target = (0x004247FF + 5 + struct.unpack("<i", call[1:])[0]) & 0xFFFFFFFF
        language = e.alloc(4)
        e.write32(language, 0)
        fmt = e.call(te.FISH_LOOKUP, ident, ecx=language)
        buffer = e.alloc(256)
        e.call(target, buffer, fmt, value)
        return out[-1]

    def test_counted_lines_choose_by_the_real_number(self) -> None:
        text = "Vous avez vendu %d {%1: one=poisson | other=poissons} !"
        rt = runtime("fish", make("fish", [(69, FISH_ENGLISH[69], text)]))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(69), b"Vous avez vendu %d poissons !")      # elsewhere: "other"
        self.assertEqual(self._sprintf(rt, 69, 1), "Vous avez vendu 1 poisson !")
        self.assertEqual(self._sprintf(rt, 69, 0), "Vous avez vendu 0 poisson !")   # French: 0 is "one"
        self.assertEqual(self._sprintf(rt, 69, 7), "Vous avez vendu 7 poissons !")

    def test_plural_rules_match_python(self) -> None:
        text = "%d {%1: zero=Z | one=O | two=T | few=F | many=M | other=X | =11=ELEVEN}"
        english = FISH_ENGLISH[70]
        for code in ("ru", "pl", "ar", "fr", "ja", "lv", "ro", "cs", "en", "pt-PT", "zz"):
            rt = runtime("fish", make("fish", [(70, english, text.replace("%d", "%d fois"))], code=code))
            self.assertEqual(rt.start(), 1, code)
            for n in (0, 1, 2, 3, 5, 11, 12, 21, 22, 25, 101, 111, 1000000):
                got = self._sprintf(rt, 70, n)
                want = tf.evaluate(text.replace("%d", "%d fois"), code, {"%1": n}).replace("%d", str(n))
                self.assertEqual(got, want, (code, n))

    def test_install_sites_are_checked(self) -> None:
        data = make("fish", [(1, "Age: ", "Âge : ")])
        rt = runtime("fish", data)
        rt.emu.uc.mem_write(0x004247FF, b"\x90" * 5)                            # not the stock call
        self.assertEqual(rt.start(), 0)
        self.assertEqual(rt.lookup(1), b"Age: ")
        self.assertIn("NOT installed; the code at 0x004247FF", rt.log)
        self.assertEqual(bytes(rt.emu.uc.mem_read(te.FISH_LOOKUP, 5)), bytes.fromhex("568b742408"))   # untouched
        rt = runtime("fish", data)
        rt.emu.uc.mem_write(te.FISH_LOOKUP, b"\xCC")
        self.assertEqual(rt.start(), 0)

    def test_the_stock_sites_and_what_is_written(self) -> None:
        rt = runtime("fish", make("fish", [(1, "Age: ", "Âge : ")]))
        rt.start()
        self.assertEqual(rt.emu.uc.mem_read(te.FISH_LOOKUP, 1)[0], 0xE9)
        for site in (0x004247FF, 0x00424820, 0x00424841, 0x00424883, 0x004248AF):
            self.assertEqual(rt.emu.uc.mem_read(site, 1)[0], 0xE8)
        self.assertEqual(bytes(rt.emu.uc.mem_read(te.FISH_LOOKUP + 5, 6)), bytes.fromhex("81fef8000000"))


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class Files(unittest.TestCase):
    def test_english_original_changes_nothing(self) -> None:
        rt = runtime("fish", None)
        self.assertEqual(rt.start(), 0)
        self.assertEqual(rt.lookup(1), b"Age: ")
        self.assertEqual(bytes(rt.emu.uc.mem_read(te.FISH_LOOKUP, 5)), bytes.fromhex("568b742408"))
        self.assertIn("no translation chosen", rt.log)

    def test_the_other_games_file_is_refused(self) -> None:
        rt = runtime("fish", make("plant", [(1, "Age: ", "Âge : ")]))
        self.assertEqual(rt.start(), 0)
        self.assertIn("another game", rt.log)

    def test_a_newer_format_is_refused(self) -> None:
        rt = runtime("fish", make("fish", [(1, "Age: ", "Âge : ")], fmt="2"))
        self.assertEqual(rt.start(), 0)
        self.assertIn("newer format", rt.log)

    def test_a_broken_encoding_is_refused(self) -> None:
        data = make("fish", [(1, "Age: ", "Âge : ")]).replace("Â".encode("utf-8"), b"\xC2")
        rt = runtime("fish", data[3:])
        self.assertEqual(rt.start(), 0)
        self.assertIn("not UTF-8", rt.log)

    def test_utf16_and_no_bom(self) -> None:
        text = make("fish", [(1, "Age: ", "Âge : ")]).decode("utf-8-sig")
        for data in (b"\xff\xfe" + text.encode("utf-16-le"), b"\xfe\xff" + text.encode("utf-16-be"),
                     text.encode("utf-8")):
            rt = runtime("fish", data)
            self.assertEqual(rt.start(), 1)
            self.assertEqual(rt.lookup(1), "Âge : ".encode("cp1252"))

    def test_spreadsheet_quotes_and_escapes(self) -> None:
        text = make("fish", [(4, "Sick", "x")]).decode("utf-8-sig")
        text = text.replace("\tSick\tx", '\t"Sick"\t"Ma\\\\la""de\\nx"')
        rt = runtime("fish", text.encode("utf-8"))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(4), b'Ma\\la"de\nx')
        parsed = tf.parse_text(text, "fish")
        self.assertEqual(parsed.rows[0].translation, 'Ma\\la"de\nx')

    def test_the_local_copy_when_the_chosen_file_moved(self) -> None:
        data = make("fish", [(1, "Age: ", "Âge : ")])
        rt = te.Runtime("fish", {INI["fish"]: te.ini("C:\\gone\\Test.txt"), te.FOLDERS["fish"] + "Translation.txt": data})
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(1), "Âge : ".encode("cp1252"))

    def test_utf8_when_unicode_text_draws_it(self) -> None:
        """The contract with "Unicode Text.dll": FtfpUnicodeTextActive() nonzero -> UTF-8, else 1252."""
        data = make("fish", [(1, "Age: ", "Âge : \u65e5\u672c")])
        for active, want, mode in ((1, "Âge : \u65e5\u672c".encode("utf-8"), "UTF-8 text"),
                                   (0, "Âge : ??".encode("cp1252"), "Windows-1252 text"),
                                   (None, "Âge : ??".encode("cp1252"), "Windows-1252 text")):
            rt = te.Runtime("fish", {INI["fish"]: te.ini(PATH), PATH: data}, unicode_active=active)
            self.assertEqual(rt.start(), 1)
            self.assertEqual(rt.lookup(1), want, active)
            self.assertIn(mode, rt.log)

    def test_never_an_email_or_path_in_the_log(self) -> None:
        rt = runtime("fish", make("fish", [(1, "Age: ", "Âge : "), (4, "Sick", "Malade {name}")]))
        rt.start()
        self.assertNotIn("C:\\", rt.log)
        self.assertNotIn("@", rt.log)


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class PlantLookup(unittest.TestCase):
    def test_stock_lookup(self) -> None:
        rt = runtime("plant", make("plant", [(7, "Play", "Jouer"), (0x1AD, "Remaining uses", "Utilisations")]))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(7), b"Jouer")
        self.assertEqual(rt.lookup(8), b"Start Over")
        self.assertEqual(rt.lookup(0x1AD), b"Utilisations")
        self.assertEqual(bytes(rt.emu.uc.mem_read(te.PLANT_LOOKUP + 6, 7)), bytes.fromhex("7508b8f8544600"))

    def test_chains_onto_store_upgrades_jump(self) -> None:
        m = next(m for m in ts.MOD_STRINGS if m.game == "plant" and m.english == "Radioactive Plant Formula")
        rows = [(7, "Play", "Jouer"), (ts.mod_key(m), m.english, "Formule radioactive")]
        rt = runtime("plant", make("plant", rows), chain_plant=True)
        jump = bytes(rt.emu.uc.mem_read(te.PLANT_LOOKUP, 6))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.lookup(7), b"Jouer")                                # through Store Upgrades' stub
        self.assertEqual(rt.lookup(0x1F0), "Formule radioactive".encode("cp1252"))   # its own text, by content
        after = bytes(rt.emu.uc.mem_read(te.PLANT_LOOKUP, 6))
        self.assertEqual(after[0], 0xE9)
        self.assertNotEqual(after[:5], jump[:5])
        self.assertEqual(after[5], 0x90)

    def test_other_code_at_the_lookup_is_refused(self) -> None:
        rt = runtime("plant", make("plant", [(7, "Play", "Jouer")]))
        rt.emu.uc.mem_write(te.PLANT_LOOKUP, b"\x8B\x44\x24\x08")
        self.assertEqual(rt.start(), 0)
        self.assertIn("NOT installed", rt.log)


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class PatcherTexts(unittest.TestCase):
    def test_a_dll_text_is_translated_through_its_relocations(self) -> None:
        dll = (ROOT / "assets" / "fish_tycoon_counts" / "Tank Counts.dll").read_bytes()
        base = 0x50000000
        m = next(m for m in ts.MOD_STRINGS if m.dll == "Tank Counts.dll" and m.english == "Fish: ")
        rows = [(ts.mod_key(m), "Fish: ", "Poissons : "), (1, "Age: ", "Âge : ")]
        rt = runtime("fish", make("fish", rows), dlls={"Tank Counts.dll": (dll, base)})
        relocated = te.relocate(dll, base)
        slots = _pointer_slots(relocated, base, b"Fish: \0")
        self.assertTrue(slots)
        self.assertEqual(rt.start(), 1)
        for slot in slots:
            target = rt.emu.read32(slot)
            self.assertEqual(rt.emu.cstring(target), "Poissons : ".encode("cp1252"))
        self.assertIn(f"{len(slots)} patcher text references", rt.log)
        other = _pointer_slots(relocated, base, b"Sick: \0")
        self.assertEqual(rt.emu.cstring(rt.emu.read32(other[0])), b"Sick: ")   # not translated: unchanged


def _pointer_slots(image: bytes, base: int, text: bytes) -> list[int]:
    """Addresses of the relocated pointers in a mapped DLL that point at `text`."""
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    reloc_rva, reloc_size = struct.unpack_from("<II", image, pe + 24 + 96 + 5 * 8)
    _b, _s, sections, _i = te.se.pe_image(image)

    def offset(rva):
        for s_rva, raw, raw_size in sections:
            if s_rva <= rva < s_rva + raw_size:
                return raw + rva - s_rva
        return None
    found = []
    at = 0
    while at < reloc_size:
        page, size = struct.unpack_from("<II", image, offset(reloc_rva + at))
        for k in range((size - 8) // 2):
            entry = struct.unpack_from("<H", image, offset(reloc_rva + at + 8 + 2 * k))[0]
            if entry >> 12 != 3:
                continue
            value = struct.unpack_from("<I", image, offset(page + (entry & 0xFFF)))[0]
            o = offset(value - base)
            if o is not None and image[o:o + len(text)] == text:
                found.append(base + page + (entry & 0xFFF))
        at += size
    return found


# Lines the C reader and the Python validator must judge alike (English 69: "You have sold %d fish!").
VECTORS = [
    "Vous avez vendu %d poissons !",
    "Vous avez vendu %i poissons !",
    "Vous avez vendu %3d poissons !",
    "Vous avez vendu %s poissons !",
    "Vous avez vendu poissons !",
    "Vous avez vendu %d %d poissons !",
    "%d {%1: one=poisson | other=poissons}",
    "%d {%1: one=poisson | other=poissons",
    "%d {%1: m=il | f=elle | o=iel}",
    "%d {%2: one=a | other=b}",
    "%d {%1: one=a | few=b | other=c}",
    "%d {%1: one=a %d | other=b}",
    "%d {%1: one=a {%1: one=x} | other=b}",
    "%d {%1: one=a | bogus=b}",
    "%d {%1: one=a | m=b}",
    "%d {%1: =0=aucun | =1=un | other=plusieurs}",
    "%d {%1: one=a\\|b | other=c}",
    "%d {{braces}} %%",
    "%d {name}",
    "%d }",
    "%d 100%",
    "%d 100% sûr",
    "%n %d",
    "%d {count: one=a | other=b}",
    "%d {%1: one=a | one=b}",
    "%d {%1: }",
    "%d {%1: one=a | other}",
    "%d {%1 one=a}",
    "%.f %d",
    "%d %ls",
    "  %d  ",
    "%d \u65e5\u672c\u8a9e \U00012000",
    "%d {%1: one=a | other=b} {%1: one=c | other=d}",
    "%d 2 %",
    "%d 2\u00a0%",
    "%d 2\u202f%",
    "%d 50 % de r\u00e9duction",
    "%d % d",
    "%d %%",
    "%d {%1: one=1 % | other=2 %}",
    "%d {{%1: one=a}}",
    "%d {%1: one={x} | other=b}",
]


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class Agreement(unittest.TestCase):
    def test_c_and_python_accept_the_same_lines(self) -> None:
        english = FISH_ENGLISH[69]
        for vector in VECTORS:
            data = make("fish", [(69, english, vector), (1, "Age: ", "Âge : ")])
            parsed = tf.parse_bytes(data, "fish")
            python_ok = tf.key_hash(english) and any(
                r.translation == vector for r in parsed.rows) and tf.make_key("strings", "69", english) in parsed.translations()
            python_ok = python_ok and not tf.too_long(vector, ts.ABSOLUTE_MAX, english=english, is_format=True)
            rt = runtime("fish", data)
            self.assertEqual(rt.start(), 1, vector)
            c_ok = rt.lookup(69) != english.encode("cp1252")
            self.assertEqual(c_ok, python_ok, vector)
            if c_ok:
                want = tf.escape_percents(tf.evaluate(vector), english).encode("cp1252", "replace")   # a format
                self.assertEqual(rt.lookup(69), want, vector)



@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class MainMenuLabels(unittest.TestCase):
    """With the French file installed, every text on each game's main menu is non-empty."""

    MENU = {"fish": [(8, "Player: "), (10, "Change Player")],
            "plant": [(3, "Player: "), (5, "Change"), (7, "Play"), (8, "Start Over"), (9, "Options"), (10, "Help"),
                      (11, "Quit")]}

    def _french(self, game: str) -> te.Runtime:
        data = (ROOT / "translations" / game / "fr.tsv").read_bytes()
        rt = runtime(game, data)
        rt.emu.call_count = 400_000_000
        self.assertEqual(rt.start(), 1, rt.log)
        return rt

    def test_every_main_menu_label_is_non_empty_in_french(self) -> None:
        for game, labels in self.MENU.items():
            rt = self._french(game)
            for ident, english in labels:
                with self.subTest(game=game, id=ident, english=english):
                    text = rt.lookup(ident)
                    self.assertTrue(text.strip(), "blank label")

    def test_every_main_menu_label_is_non_empty_without_a_translation(self) -> None:
        for game, labels in self.MENU.items():
            rt = runtime(game, None)
            rt.start()
            for ident, english in labels:
                with self.subTest(game=game, id=ident):
                    self.assertEqual(rt.lookup(ident), english.encode("cp1252"))

    def test_fish_change_player_literal_is_french_and_non_empty(self) -> None:
        rt = self._french("fish")
        self.assertEqual(ExeLiterals._pushed(rt, 0x0041C689), "Changer de joueur".encode("cp1252"))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(te.ready(), "needs MSVC, the vanilla games and assets/translations/Translations.dll")
class ExeLiterals(unittest.TestCase):
    """Labels the exe pushes as a literal (not through the string table) get the same translation."""

    @staticmethod
    def _pushed(rt: te.Runtime, site: int) -> bytes:
        code = bytes(rt.emu.uc.mem_read(site, 5))
        assert code[0] == 0x68, code.hex()
        at = struct.unpack_from("<I", code, 1)[0]
        data = bytes(rt.emu.uc.mem_read(at, 64))
        return data[:data.index(0)]

    def test_fish_main_menu_change_player(self) -> None:
        rt = runtime("fish", make("fish", [(10, "Change Player", "Changer de joueur")]))
        self.assertEqual(self._pushed(rt, 0x0041C689), b"Change Player")
        self.assertEqual(rt.start(), 1)
        self.assertEqual(self._pushed(rt, 0x0041C689), b"Changer de joueur")
        self.assertEqual(rt.lookup(10), b"Changer de joueur")

    def _place_label(self, width: int) -> tuple[int, list]:
        """Fish's "Change Player" label: the call at 0x41C68E (after the install) with a text `width` pixels wide,
        the label at x = 670, y = 572.  Returns the x the label ends up at and the moves made."""
        rt = runtime("fish", make("fish", [(10, "Change Player", "Changer de joueur")]))
        self.assertEqual(rt.start(), 1)
        e = rt.emu
        code = bytes(e.uc.mem_read(0x0041C68E, 5))
        self.assertEqual(code[0], 0xE8)
        target = (0x0041C68E + 5 + struct.unpack_from("<i", code, 1)[0]) & 0xFFFFFFFF
        self.assertNotEqual(target, 0x004015B0)                                # the call goes to the DLL's hook
        label, inner = e.alloc(0x40), e.alloc(0x80)
        e.write32(label + 0x10, inner)
        e.write32(inner + 8, 670)
        e.write32(inner + 12, 572)
        moves: list = []
        e.hook(0x004015B0, lambda emu: 0, 0x14)                               # the text setter
        e.hook(0x004023D0, lambda emu: width, 8)                              # the game's text measure
        e.hook(0x00401080, lambda emu: moves.append((emu.arg(0), emu.arg(1))) or 0, 8)
        text = e.alloc(32)
        e.uc.mem_write(text, b"Changer de joueur\0")
        e.call(target, text, 0, 0, 0, 0x1234, ecx=label)
        return (moves[-1][0] if moves else 670), moves

    def test_fish_change_player_label_moves_left_when_wide(self) -> None:
        x, moves = self._place_label(300)
        self.assertEqual(x, 796 - 300)                                        # ends at the screen edge, whole
        self.assertEqual(moves, [(496, 572)])

    def test_fish_change_player_label_stays_when_it_fits(self) -> None:
        x, moves = self._place_label(100)
        self.assertEqual((x, moves), (670, []))

    def test_fish_change_player_label_wider_than_the_screen_starts_at_zero(self) -> None:
        x, _moves = self._place_label(900)
        self.assertEqual(x, 0)

    def test_fish_literal_stays_without_a_translation(self) -> None:
        rt = runtime("fish", make("fish", [(1, "Age: ", "Âge : ")]))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(bytes(rt.emu.uc.mem_read(0x0041C689, 5)), bytes.fromhex("68d4384400"))

    def test_fish_literal_site_is_checked(self) -> None:
        rt = runtime("fish", make("fish", [(10, "Change Player", "Changer de joueur")]))
        rt.emu.uc.mem_write(0x0041C689, b"\x90")
        self.assertEqual(rt.start(), 0)
        self.assertIn("NOT installed; the code at 0x0041C689", rt.log)
        self.assertEqual(rt.lookup(10), b"Change Player")                       # nothing was installed

    def test_plant_tab_labels(self) -> None:
        rows = [(384, "Nursery", "Pépinière"), (385, "Supplies", "Fournitures"), (381, "Collect", "Collection")]
        rt = runtime("plant", make("plant", rows))
        self.assertEqual(rt.start(), 1)
        for site, want in ((0x419415, "Pépinière"), (0x4336F2, "Pépinière"), (0x4193AD, "Fournitures"),
                           (0x433622, "Fournitures"), (0x43368A, "Collection")):
            self.assertEqual(self._pushed(rt, site), want.encode("cp1252"), hex(site))
        self.assertEqual(bytes(rt.emu.uc.mem_read(0x419250, 5)), bytes.fromhex("684c7b4600"))   # Stats: no line

    def test_plant_exe_literals_with_their_own_keys(self) -> None:
        def key(english: str) -> str:
            return ts.mod_key(next(m for m in ts.EXE_STRINGS if m.english == english))
        rows = [(key("Change Scene"), "Change Scene", "Changer de d\u00e9cor"),
                (key("Mission Blue Butterfly"), "Mission Blue Butterfly", "Papillon bleu de la mission"),
                (key("%s in %i Min."), "%s in %i Min.", "%s en %i min."),
                (key("Collected: %i out of 48"), "Collected: %i out of 48", "Collect\u00e9s : %i sur 48")]
        rt = runtime("plant", make("plant", rows))
        self.assertEqual(rt.start(), 1)
        self.assertEqual(self._pushed(rt, 0x4488AA), "Changer de d\u00e9cor".encode("cp1252"))
        self.assertEqual(self._pushed(rt, 0x418971), b"Papillon bleu de la mission")
        self.assertEqual(self._pushed(rt, 0x42383E), b"%s en %i min.")
        self.assertEqual(self._pushed(rt, 0x4238C0), b"%s en %i min.")          # the same literal, both pushes
        self.assertEqual(self._pushed(rt, 0x4185A6), "Collect\u00e9s : %i sur 48".encode("cp1252"))
        self.assertEqual(bytes(rt.emu.uc.mem_read(0x41895A, 5)), bytes.fromhex("68207b4600"))   # Blue Butterfly: no line

    def test_plant_exe_literal_site_is_checked(self) -> None:
        english = "Change Scene"
        m = next(m for m in ts.EXE_STRINGS if m.english == english)
        rt = runtime("plant", make("plant", [(ts.mod_key(m), english, "Changer de d\u00e9cor")]))
        rt.emu.uc.mem_write(0x4488AA, b"\x90")
        self.assertEqual(rt.start(), 0)
        self.assertIn("NOT installed; the code at 0x004488AA", rt.log)
        self.assertEqual(bytes(rt.emu.uc.mem_read(0x419415, 5)), bytes.fromhex("68307b4600"))   # nothing was written
