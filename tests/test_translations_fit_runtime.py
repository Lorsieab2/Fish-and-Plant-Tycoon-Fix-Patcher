"""Translations.dll fits every translated line to its room on the 800 x 600 screen (native/
ftfp_translations/translation_fit.h, translation_limits.h), run in Unicorn against the real games:

* every game line of both games is translated with a worst case (a long German-like line, a
  Chinese line with no spaces, a Thai line, an Arabic line, an emoji line; in Windows-1252 and,
  with "Unicode Text.dll" drawing, in UTF-8), the game's fonts are made, and the game's own lookup
  is called: every line it returns is within its room measured with the game's measure (called by
  the DLL at 0x4023D0 / 0x402380, here answering the fonts' real widths), or is the English;
* re-broken where the English breaks lines (at spaces, CJK between letters, never inside a
  cluster), cut with "..." where it does not, English when even that does not fit; a printf format
  is never cut; nothing is written past the line's byte limit;
* screens drawn by the games' own code (tests/draw_emulator.py) with what the DLL returns: Plant
  Tycoon's main menu, Options dialog, a message and a question box, Fish Tycoon's Options popup and a
  message box: no word is drawn outside the screen or wider than its room.
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
import translation_format as tf  # noqa: E402
import translation_strings as ts  # noqa: E402
import translations_emulator as te  # noqa: E402

try:
    import draw_emulator as de
    import build_translation_limits as L
    DRAW = de.available("fish") and de.available("plant")
except ImportError:
    DRAW = False

READY = te.ready() and DRAW
PATH = "C:\\Translations\\Test.txt"
INI = {g: te.FOLDERS[g] + "Translation.ini" for g in ("fish", "plant")}

GERMAN = ("Donaudampfschifffahrtsgesellschaftskapitän und die Grundstücksverkehrsgenehmigung für "
          "Fischzüchter mit außergewöhnlich langen Wörtern im Spiel")
CJK = "这是一个非常长的中文句子没有任何空格所以游戏必须在字符之间断行才能显示在屏幕上，好吗？" * 2
THAI = "นี่คือประโยคภาษาไทยที่ยาวมากและไม่มีช่องว่างระหว่างคำเลยเพราะภาษาไทยไม่ใช้ช่องว่าง"
ARABIC = "هذه جملة عربية طويلة جدا تحتوي على كلمات كثيرة لكي نرى هل تتسع على الشاشة أم لا"
EMOJI = "🐟🐠🐡🦈🐙 🦑🦀🦞🐚🌊 " * 6
WORST = (GERMAN, CJK, THAI, ARABIC, EMOJI)


def worst_case(english: str, kind: int, limit: int | None) -> str:
    """A worst-case translation of the line: its placeholders kept, at most its byte limit."""
    template = tf.parse_template(english)
    tail = " ".join(c.text for c in template.conversions)
    body = WORST[kind]
    make = lambda b: b + (" " + tail if tail else "")  # noqa: E731
    while limit is not None and len(make(body).encode("utf-8")) > limit and len(body) > 1:
        body = body[:-1]
    return make(body)


class Fonts:
    """The game's fonts made where the DLL looks for them, its measure and height answering the
    fonts' real widths (cp1252: the game's own measure, pictures_screens.Composer.text_size; UTF-8:
    the Text Maker's layout, what "Unicode Text.dll"'s measure hook draws)."""

    def __init__(self, rt: te.Runtime, game: str, utf8: bool) -> None:
        self.game, self.utf8 = game, utf8
        self.c = L.composer(game)
        self.fonts = tfit.fonts_by_number(game, L.FOLDERS[game])
        e = rt.emu
        self.objects = {}
        if game == "fish":
            manager, array = e.alloc(16), e.alloc(16)
            e.write32(0x45B270, manager)
            e.write32(manager, array)
            for n in range(3):
                font = e.alloc(64)
                self.objects[font] = n
                e.write32(array + 4 * n, font)
            width, height = 0x4023D0, 0x4024A0
        else:
            graphics, impl, font = e.alloc(16), e.alloc(0x100), e.alloc(64)
            e.write32(0x493948, graphics)
            e.write32(graphics, impl)
            e.write32(impl + 0x5C, font)
            self.objects[font] = 0
            width, height = 0x402380, 0x402450
        from unicorn import x86_const as X
        reg = lambda: e.uc.reg_read(X.UC_X86_REG_ECX)  # noqa: E731
        e.hook(width, lambda emu: self.size(self.objects.get(reg(), 0), emu.cstring(emu.arg(0)))[0], 8)
        e.hook(height, lambda emu: self.size(self.objects.get(reg(), 0), emu.cstring(emu.arg(0)))[1], 4)

    def size(self, font: int, data: bytes) -> tuple:
        if not self.utf8:
            return self.c.text_size(font, data)
        import text_maker as tm
        f = self.fonts[font] or self.fonts[0]
        text = data.decode("utf-8", "replace")
        widest = max(tm.layout(f, line)[1] for line in text.split("\n"))
        return widest, f.line_height * (text.count("\n") + 1)


def lines_and_limits(game: str):
    exe = (L.FOLDERS[game] / ts.EXE_NAMES[game]).read_bytes()
    limits = tfit.limits(game)
    out = []
    for s in ts.read_table(game, exe):
        if s.id in ts.NEVER_TRANSLATED[game] or not s.english.strip():
            continue
        limit = limits.get(f"strings/{s.id}")
        if limit is None or limit.width is None:
            continue
        out.append((s, limit, ts.game_limit(game, s)))
    return out


def runtime(game: str, rows, utf8: bool) -> tuple:
    entries = [tf.Entry(tf.make_key("strings", str(s.id), s.english), s.english) for s, _l, _b in rows]
    f = tf.new_file(game, entries, "Test", "de")
    for row, (s, _limit, byte_limit) in zip(f.rows, rows):
        row.translation = worst_case(s.english, s.id % len(WORST), byte_limit)
    data = tf.to_bytes(f)
    rt = te.Runtime(game, {INI[game]: te.ini(PATH), PATH: data}, unicode_active=1 if utf8 else None)
    rt.emu.call_count = 2_000_000_000            # every line of the game read, and fitted at the first lookup
    if game == "plant":
        rt.hook_plant_table()
    fonts = Fonts(rt, game, utf8)
    return rt, fonts, {r.key: r.translation for r in f.rows}


@unittest.skipUnless(READY, "MSVC, Unicorn, capstone, the vanilla games and Translations.dll")
class EveryLineFits(unittest.TestCase):
    def check_game(self, game: str, utf8: bool) -> None:
        rows = lines_and_limits(game)
        rt, fonts, _translations = runtime(game, rows, utf8)
        self.assertEqual(rt.start(), 1)
        self.assertEqual(rt.emu.call(rt.emu.sym("_FtfpTranslationsFitted@0")), 0)   # no fonts yet
        fitted = broken = cut = english = 0
        for s, limit, byte_limit in rows:
            got = rt.lookup(s.id)
            if got == s.english.encode("cp1252", "replace"):
                english += 1
                continue
            fitted += 1
            text = got.decode("utf-8" if utf8 else "cp1252")
            for line in got.split(b"\n"):
                self.assertLessEqual(fonts.size(limit.font, line)[0], limit.width, (game, hex(s.id), text))
            if byte_limit is not None:
                self.assertLessEqual(len(got), byte_limit, (game, hex(s.id)))
            if limit.height:
                self.assertLessEqual(fonts.size(limit.font, got)[1], limit.height, (game, hex(s.id)))
            if limit.format:
                self.assertNotIn(b"...", got, (game, hex(s.id)))       # a format is never cut
            broken += b"\n" in got and "\n" not in s.english
            cut += got.endswith(b"...") or b"...\n" in got
        self.assertEqual(rt.emu.call(rt.emu.sym("_FtfpTranslationsFitted@0")), 1)
        self.assertGreater(fitted, len(rows) // 3, game)
        self.assertGreater(cut, 0, game)
        self.assertIn("fitted to their room on the screen", rt.log)
        return broken, cut, english

    def test_fish_windows_1252(self) -> None:
        self.check_game("fish", False)

    def test_fish_utf8(self) -> None:
        self.check_game("fish", True)

    def test_plant_windows_1252(self) -> None:
        self.check_game("plant", False)

    def test_plant_utf8(self) -> None:
        self.check_game("plant", True)


@unittest.skipUnless(READY, "MSVC, Unicorn, capstone, the vanilla games and Translations.dll")
class Fitting(unittest.TestCase):
    """The rules on single lines, through the DLL."""

    def one(self, game: str, ident: int, english: str, translation: str, utf8: bool = False) -> bytes:
        f = tf.new_file(game, [tf.Entry(tf.make_key("strings", str(ident), english), english)], "Test", "de")
        f.rows[0].translation = translation
        rt = te.Runtime(game, {INI[game]: te.ini(PATH), PATH: tf.to_bytes(f)}, unicode_active=1 if utf8 else None)
        if game == "plant":
            rt.hook_plant_table()
        self.fonts = Fonts(rt, game, utf8)
        self.assertEqual(rt.start(), 1)
        return rt.lookup(ident)

    def english(self, game: str, ident: int) -> str:
        exe = (L.FOLDERS[game] / ts.EXE_NAMES[game]).read_bytes()
        return next(s.english for s in ts.read_table(game, exe) if s.id == ident)

    def test_a_single_line_spot_is_cut_with_an_ellipsis(self) -> None:
        english = self.english("plant", 0x9)                                  # "Options": a menu button
        limit = tfit.limits("plant")["strings/9"]
        got = self.one("plant", 0x9, english, "Einstellungsmöglichkeiten des Spiels Einstellungsmöglichkeiten des Spiels Einstellungsmöglichkeiten des Spiels Einstellungsmöglichkeiten des Spiels ")
        self.assertTrue(got.endswith(b"..."), got)
        self.assertLessEqual(self.fonts.size(0, got)[0], limit.width)
        self.assertTrue("Einstellungsmöglichkeiten des Spiels Einstellungsmöglichkeiten des Spiels Einstellungsmöglichkeiten des Spiels Einstellungsmöglichkeiten des Spiels ".encode("cp1252").startswith(got[:-3]))

    def test_a_short_line_is_left_alone(self) -> None:
        english = self.english("plant", 0x9)
        self.assertEqual(self.one("plant", 0x9, english, "Optionen"), b"Optionen")

    def test_a_multiline_spot_is_rebroken_at_spaces(self) -> None:
        ident = next(s.id for s, limit, b in lines_and_limits("plant") if limit.multiline and limit.proven
                     and b is None and not limit.format)
        english = self.english("plant", ident)
        limit = tfit.limits("plant")[f"strings/{ident}"]
        words = ("Wort " * 200)[: 600].strip()
        got = self.one("plant", ident, english, words)
        self.assertGreater(got.count(b"\n"), 0)
        self.assertEqual(got.replace(b"\n", b" "), words.encode())                # only the breaks changed
        for line in got.split(b"\n"):
            self.assertLessEqual(self.fonts.size(0, line)[0], limit.width)

    def test_cjk_breaks_between_letters_never_before_a_closing_mark(self) -> None:
        ident = next(s.id for s, limit, b in lines_and_limits("plant") if limit.multiline and limit.proven
                     and b is None and not limit.format)
        english = self.english("plant", ident)
        text = "这是一个很长的句子，" * 30
        got = self.one("plant", ident, english, text, utf8=True).decode("utf-8")
        self.assertGreater(got.count("\n"), 0)
        self.assertEqual(got.replace("\n", ""), text)
        for line in got.split("\n")[1:]:
            self.assertNotEqual(line[:1], "，")

    def test_thai_and_chinese_break_between_words_from_the_word_lists(self) -> None:
        """icu.dll does not load in Unicorn, so the DLL reads ICU's lists beside it (word_break.h)."""
        import word_break as wb
        ident = next(s.id for s, limit, b in lines_and_limits("plant") if limit.multiline and limit.proven
                     and b is None and not limit.format)
        english = self.english("plant", ident)
        tiny = ("\ufeff# a small list\n" + "".join(w + "\t5\n" for w in "我们 今天 去 公园 玩 好 吗".split())).encode("utf-8")
        import tempfile
        folder = Path(tempfile.mkdtemp())
        (folder / "cjdict.txt").write_bytes(tiny)
        for name, text, script in (("thaidict.txt", THAI * 2, "thai"), ("cjdict.txt", "我们今天去公园玩，好吗？" * 6, "cj")):
            data = tiny if script == "cj" else (wb.FOLDER / name).read_bytes()
            lists = {INI["plant"].replace("Translation.ini", "word-lists\\" + name): data}
            f = tf.new_file("plant", [tf.Entry(tf.make_key("strings", str(ident), english), english)], "Test", "de")
            f.rows[0].translation = text
            rt = te.Runtime("plant", {INI["plant"]: te.ini(PATH), PATH: tf.to_bytes(f), **lists}, unicode_active=1)
            rt.hook_plant_table()
            rt.emu.call_count = 2_000_000_000                # the list is read and hashed by the DLL's own code
            self.fonts = Fonts(rt, "plant", True)
            self.assertEqual(rt.start(), 1)
            got = rt.lookup(ident).decode("utf-8")
            state = wb.analyze(text, folder if script == "cj" else None)
            self.assertGreater(got.count("\n"), 0, script)
            self.assertEqual(got.replace("\n", ""), text)
            at = 0
            for line in got.split("\n")[:-1]:
                at += len(line)
                self.assertEqual(state[at], 2, (script, got))                     # only between words
            if script == "cj":
                for line in got.split("\n")[1:]:
                    self.assertNotIn(line[:1], "，。？")

    def test_a_word_wider_than_the_room_breaks_between_characters(self) -> None:
        """One dictionary word wider than the room breaks between characters (kinsoku kept), as text_wrap does."""
        ident = next(s.id for s, limit, b in lines_and_limits("plant") if limit.multiline and limit.proven
                     and b is None and not limit.format)
        english = self.english("plant", ident)
        word = "\u30d7\u30ed\u30b0\u30e9\u30df\u30f3\u30b0\u8a00\u8a9e\u958b\u767a\u74b0\u5883\u306e\u69cb\u7bc9\u3068\u904b\u7528" * 3
        text = word + "\u3002"
        lists = {INI["plant"].replace("Translation.ini", "word-lists\\cjdict.txt"): (word + "\t5\n").encode("utf-8")}
        f = tf.new_file("plant", [tf.Entry(tf.make_key("strings", str(ident), english), english)], "Test", "de")
        f.rows[0].translation = text
        rt = te.Runtime("plant", {INI["plant"]: te.ini(PATH), PATH: tf.to_bytes(f), **lists}, unicode_active=1)
        rt.hook_plant_table()
        rt.emu.call_count = 2_000_000_000
        self.fonts = Fonts(rt, "plant", True)
        self.assertEqual(rt.start(), 1)
        got = rt.lookup(ident).decode("utf-8")
        self.assertGreater(got.count("\n"), 0)
        self.assertNotIn("...", got)
        self.assertEqual(got.replace("\n", ""), text)                              # nothing lost
        for line in got.split("\n")[1:]:
            self.assertNotEqual(line[:1], "\u3002")

    def test_too_tall_for_its_box_shows_english(self) -> None:
        """A message box's text taller than the box the game can make on the screen: English."""
        ident, limit = next((s.id, l) for s, l, b in lines_and_limits("plant") if l.height and b is None)
        english = self.english("plant", ident)
        tail = " ".join(c.text for c in tf.parse_template(english).conversions)
        got = self.one("plant", ident, english, "Zeile\n" * 60 + "Ende" + (" " + tail if tail else ""))
        self.assertEqual(got, english.encode("cp1252"))
        got = self.one("plant", ident, english, "Zeile\n" * 3 + "Ende" + (" " + tail if tail else ""))
        self.assertTrue(got.startswith(b"Zeile\n"))

    def test_a_cluster_is_never_cut(self) -> None:
        english = self.english("plant", 0x9)
        text = "e\u0301" * 300                                                   # e + combining acute
        got = self.one("plant", 0x9, english, text, utf8=True).decode("utf-8")
        self.assertTrue(got.endswith("..."))
        body = got[:-3]
        self.assertEqual(len(body) % 2, 0)
        self.assertTrue(body == "e\u0301" * (len(body) // 2))


def drawn_rooms(r, census) -> list:
    out = []
    for data, x, y, font in r.texts:
        w = L.composer(r.game).text_size(font, data)[0]
        out.append((data, x, x + w))
    return out


@unittest.skipUnless(READY, "MSVC, Unicorn, capstone, the vanilla games and Translations.dll")
class ScreensWithFittedText(unittest.TestCase):
    """The games' own screens drawn with what the DLL returns for every line (the German-like worst
    case, Windows-1252): no word leaves the screen."""

    def fitted(self, game: str) -> dict:
        rows = lines_and_limits(game)
        rt, _fonts, _t = runtime(game, [(s, l, b) for s, l, b in rows], False)
        rt.start()
        return {s.id: rt.lookup(s.id).decode("cp1252") for s, _l, _b in rows}

    def check(self, run, strings: dict) -> None:
        """Every translated word drawn is inside the screen from side to side (the game's own words
        that were not translated are the game's business)."""
        translated = {v.encode("cp1252") for v in strings.values()}
        seen = 0
        for data, x, _y, font in run.texts:
            if data not in translated:
                continue
            seen += 1
            w = L.composer(run.game).text_size(font, data)[0]
            self.assertTrue(0 <= x and x + w <= 800, (data, x, w))
        return seen

    def screen(self, game: str, scenario, strings: dict):
        r = L.Run(game)
        r.d.strings.update(strings)
        r.d._string_at.clear()          # lines looked up while the game state was made: again
        if game == "fish":              # the lookup itself (0x426FD0), as Translations.dll hooks it
            r.emu.hook(0x426FD0, r.d._lookup, 4)
        scenario(r)
        r.collect()
        return r

    def test_plant_screens(self) -> None:
        strings = self.fitted("plant")

        def menu(r):
            d = r.d
            screen = d._zeroed(0x800)
            d.run(0x429D00, this=screen)
            d.show(screen)

        def options(r):
            d = r.d
            dialog = d._zeroed(0x200)
            d.run(0x42AF10, d.emu.text(strings[0x192]), 1, this=dialog)
            d.vcall(d.emu.read32(dialog + 0x3C), 3, d.emu.read32(dialog + 0x14), d.emu.read32(dialog + 0x18), 0x3F800000)
            d.run(0x42B710, this=dialog)
            for widget, _id in d.widgets:
                d.vcall(widget, 5, 1)
                d.vcall(widget, 6)

        def message(r):
            d = r.d
            box = d._zeroed(0x200)
            d.run(0x44D690, 0x6E, 0, 0, 0, this=box)
            d.vcall(d.emu.read32(box + 0x3C), 3, d.emu.read32(box + 0x14), d.emu.read32(box + 0x18), 0x3F800000)
            d.run(0x44DBB0, this=box)

        def question(r):
            box = r.d._zeroed(0x200)
            r.d.run(0x42AB50, 0x77, 1, 1, 0, 0, this=box)
            r.d.show(box)
        seen = [self.check(self.screen("plant", scenario, strings), strings) for scenario in (menu, options, message, question)]
        self.assertTrue(all(seen), seen)

    def test_fish_screens(self) -> None:
        strings = self.fitted("fish")
        seen = []
        for ctor, args in ((0x422530, ()), (0x4221A0, (0x1C, 1)), (0x41C380, ())):
            def scenario(r, ctor=ctor, args=args):
                screen = r.d.make(ctor, *args, size=0x400)
                r.d.show(screen)
            seen.append(self.check(self.screen("fish", scenario, strings), strings))
        self.assertTrue(all(seen[:2]), seen)


if __name__ == "__main__":
    unittest.main()
