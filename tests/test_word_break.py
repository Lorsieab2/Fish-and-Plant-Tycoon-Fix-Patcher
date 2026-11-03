"""Word breaking for the scripts written without spaces (src/word_break.py, src/text_wrap.py):

* the shipped ICU word lists (assets/translations/word-lists) are byte-identical to the README's
  SHA-256 table, and the licence ships with them and in the release;
* longest-match segmentation on known Thai, Japanese, Chinese, Lao, Khmer and Burmese samples;
* Wrap to fit breaks between words, never splits a dictionary word while a word boundary fits, and
  keeps the kinsoku rules (no line starts with a closing mark, none ends with an opening one);
* edge cases: empty lines, Latin mixed with Thai or CJK, one word longer than the room, %s / %d and
  {choices} inside the text, lines with no dictionary word, lists that are missing.
No game and no extra package are needed: CI runs these.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import text_wrap as tw  # noqa: E402
import word_break as wb  # noqa: E402

LISTS = ROOT / "assets" / "translations" / "word-lists"
THAI = "นี่คือประโยคภาษาไทยที่ยาวมากและไม่มีช่องว่างระหว่างคำเลย"
JAPANESE = "私は昨日東京で新しいコンピュータを買いました。"
CHINESE = "我们今天去公园玩，好吗？"
TRADITIONAL = "我們今天去公園玩"


def px(line: str) -> int:
    """A stand-in for the game's font: 10 pixels a character (Latin the same, to keep it exact)."""
    return 10 * len(line)


def break_offsets(text: str, wrapped: str) -> list[int]:
    """Where in `text` each line of `wrapped` starts (spaces at a break are dropped by wrapping)."""
    out, at = [], 0
    for line in wrapped.split("\n")[1:]:
        at = text.index(line[:1], at + 1) if line else at
        out.append(at)
    return out


class ShippedLists(unittest.TestCase):
    def test_sha256_matches_the_readme(self) -> None:
        readme = (LISTS / "README.md").read_text(encoding="utf-8")
        rows = re.findall(r"\|\s*`([^`]+)`\s*\|[^|]*\|\s*([\d,]+)\s*\|\s*`([0-9a-f]{64})`", readme)
        names = {name for name, _size, _digest in rows}
        self.assertEqual(names, {"thaidict.txt", "laodict.txt", "khmerdict.txt", "burmesedict.txt",
                                 "cjdict.txt", "ICU-LICENSE.txt"})
        for name, size, digest in rows:
            data = (LISTS / name).read_bytes()
            self.assertEqual(len(data), int(size.replace(",", "")), name)
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, name)

    def test_the_release_and_the_manifests_carry_the_lists_and_the_licence(self) -> None:
        import json
        import build_release as br
        shipped = set(br.bundled_asset_files())
        for name in ("thaidict.txt", "laodict.txt", "khmerdict.txt", "burmesedict.txt", "cjdict.txt",
                     "ICU-LICENSE.txt", "README.md"):
            self.assertIn(f"assets/translations/word-lists/{name}", shipped)
        self.assertIn("src/word_break.py", br.FILES)
        for game in ("fish", "plant"):
            manifest = json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
            tr = next(s for s in manifest["settings"] if s["id"] == "translations")
            folder = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}[game] + " Fix Patcher DLLs"
            destinations = {f["destination"] for f in tr["companion"]["files"]}
            self.assertIn(f"{folder}/word-lists/cjdict.txt", destinations)
            self.assertIn(f"{folder}/word-lists/ICU-LICENSE.txt", destinations)

    def test_every_list_parses(self) -> None:
        for script in wb.FILES:
            d = wb.dictionary(script)
            self.assertIsNotNone(d, script)
            self.assertGreater(len(d.words), 20000, script)
            self.assertLessEqual(d.longest, wb.MAX_WORD)


class Segmentation(unittest.TestCase):
    def test_thai(self) -> None:
        self.assertEqual(wb.words_of(THAI), ["นี่", "คือ", "ประโยค", "ภาษา", "ไทย", "ที่", "ยาว", "มาก", "และ",
                                             "ไม่มี", "ช่อง", "ว่าง", "ระหว่าง", "คำ", "เลย"])

    def test_japanese(self) -> None:
        self.assertEqual(wb.words_of(JAPANESE), ["私", "は", "昨日", "東京", "で", "新しい", "コンピュータ", "を",
                                                 "買い", "まし", "た。"])

    def test_chinese(self) -> None:
        self.assertEqual(wb.words_of(CHINESE), ["我们", "今天", "去", "公园", "玩，", "好", "吗？"])
        self.assertEqual(wb.words_of(TRADITIONAL), ["我們", "今天", "去", "公園", "玩"])

    def test_lao_khmer_burmese(self) -> None:
        self.assertEqual(wb.words_of("ພາສາລາວ"), ["ພາສາ", "ລາວ"])
        self.assertEqual(wb.words_of("ខ្ញុំស្រលាញ់ប្រទេសកម្ពុជា"), ["ខ្ញុំ", "ស្រលាញ់", "ប្រទេស", "កម្ពុជា"])
        self.assertEqual(wb.words_of("မြန်မာဘာသာစကား"), ["မြန်မာဘာသာ", "စကား"])

    def test_the_longest_word_wins(self) -> None:
        d = wb.dictionary("thai")
        for word in ("ประเทศไทย", "ภาษาไทย"):
            if word in d.words:
                self.assertEqual(wb.words_of(word), [word])
        # the words always add up to the text
        for text in (THAI, JAPANESE, CHINESE, "ພາສາລາວ"):
            self.assertEqual("".join(wb.words_of(text)), text)

    def test_a_word_never_starts_on_a_combining_mark(self) -> None:
        state = wb.analyze(THAI)
        for ch, s in zip(THAI, state):
            if 0x0E31 == ord(ch) or 0x0E34 <= ord(ch) <= 0x0E3A or 0x0E47 <= ord(ch) <= 0x0E4E:
                self.assertEqual(s, 1, ch)

    def test_a_katakana_run_is_one_word_when_unknown(self) -> None:
        self.assertEqual(wb.words_of("ズズズズズズ"), ["ズズズズズズ"])

    def test_empty_and_other_scripts_have_no_information(self) -> None:
        self.assertEqual(wb.analyze(""), [])
        self.assertEqual(wb.analyze("Fish 100% tank"), [0] * len("Fish 100% tank"))
        self.assertEqual(wb.words_of(""), [])
        self.assertEqual(wb.analyze("ab" + "ปลา" + "cd"), [0, 0, 2, 1, 1, 0, 0])

    def test_runs_stop_at_punctuation_and_other_scripts(self) -> None:
        state = wb.analyze("ปลา。ทอง")
        self.assertEqual(state[3], 0)                       # the ideographic full stop is no run
        self.assertEqual(state[4], 2)                       # a new run starts a word
        mixed = wb.analyze("ปลา猫")
        self.assertEqual(mixed[3], 2)                        # Thai then Han: two runs

    def test_the_parser_reads_comments_a_bom_and_frequencies(self) -> None:
        d = wb.parse("﻿  # header\n# more\n\nabc\t12\r\ndef \nxyz".encode("utf-8"))
        self.assertEqual(d.words, {"abc", "def", "xyz"})
        self.assertEqual(d.longest, 3)

    def test_a_missing_list_gives_no_information(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(wb.analyze(THAI, Path(empty)), [0] * len(THAI))


class WrapThai(unittest.TestCase):
    def test_breaks_between_words_at_every_limit(self) -> None:
        state = wb.analyze(THAI)
        for limit in range(20, 400, 10):
            result = tw.wrap(THAI, limit, px)
            self.assertEqual(result.text.replace("\n", ""), THAI)
            at = 0
            for line in result.text.split("\n")[:-1]:
                at += len(line)
                self.assertEqual(state[at], 2, (limit, result.text))     # every break is a word boundary

    def test_no_line_is_wider_than_the_limit_unless_one_word_is(self) -> None:
        longest_word = max(len(w) for w in wb.words_of(THAI))
        for limit in range(10 * longest_word, 400, 10):
            result = tw.wrap(THAI, limit, px)
            self.assertEqual(result.cannot_wrap, [])
            self.assertTrue(all(px(line) <= limit for line in result.text.split("\n")), (limit, result.text))

    def test_a_word_longer_than_the_room_is_reported_not_split(self) -> None:
        result = tw.wrap("ประเทศ", 20, px)
        self.assertEqual(result.text, "ประเทศ")
        self.assertEqual(result.cannot_wrap, ["ประเทศ"])
        result = tw.wrap("ก " + "ประเทศ" + " ข", 30, px)
        self.assertEqual(result.text, "ก\nประเทศ\nข")

    def test_mixed_latin_and_thai(self) -> None:
        text = "Fish ปลาทอง tank มีอาหาร 100%"
        result = tw.wrap(text, 80, px)
        self.assertEqual(result.text.replace("\n", " ").replace("  ", " ").replace(" ", ""), text.replace(" ", ""))
        self.assertTrue(all(px(line) <= 80 for line in result.text.split("\n")), result.text)
        for line in result.text.split("\n"):
            self.assertEqual(line, line.strip())
        self.assertIn("Fish", result.text.split("\n")[0])

    def test_latin_and_thai_without_a_space_stay_together(self) -> None:
        self.assertEqual(tw.wrap("Fishปลา", 30, px).text, "Fishปลา")

    def test_lines_with_no_dictionary_word_do_not_break_or_crash(self) -> None:
        text = "ฟฟฟฟฟฟฟฟฟฟฟฟฟฟฟฟฟฟฟฟ"
        result = tw.wrap(text, 50, px)
        self.assertEqual(result.text.replace("\n", ""), text)
        self.assertEqual(result.text, text)                              # no word, no break: never cut
        self.assertTrue(result.cannot_wrap)
        r = tw.wrap("ฝฝฝ ฟฟฟฟฟฟฟ ฝฝฝ", 40, px)                # spaces still break
        self.assertEqual(r.text.replace("\n", " "), "ฝฝฝ ฟฟฟฟฟฟฟ ฝฝฝ")

    def test_empty_lines_and_blank_paragraphs(self) -> None:
        self.assertEqual(tw.wrap("", 50, px).text, "")
        self.assertEqual(tw.wrap("\n", 50, px).text, "")
        self.assertEqual(tw.wrap("   ", 50, px).text, "")
        text = "ปลา\n\nทอง"
        self.assertEqual(tw.wrap(text, 200, px).text, text)
        self.assertEqual(tw.wrap("ปลา\nทอง", 200, px).text, "ปลาทอง")      # a soft break is decided again

    def test_placeholders_inside_thai_are_never_split(self) -> None:
        text = "คุณมี %d ปลา และ %s ในถัง {count: one=ปลา | other=ปลา} ทั้งหมด"
        tokens = ("%d", "%s", "{count: one=ปลา | other=ปลา}")
        for limit in range(20, 300, 10):
            result = tw.wrap(text, limit, px)
            self.assertEqual(re.sub(r"\s", "", result.text), re.sub(r"\s", "", text))
            for token in tokens:
                self.assertTrue(any(token in line for line in result.text.split("\n")), (limit, token, result.text))

    def test_missing_lists_keep_the_old_behaviour(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            old = wb.FOLDER
            wb._CACHE.clear()
            wb.FOLDER = Path(empty)
            try:
                result = tw.wrap(THAI, 100, px)
                self.assertEqual(result.text, THAI)                      # never cut
                self.assertTrue(result.cannot_wrap)
                japanese = tw.wrap(JAPANESE, 100, px)
                self.assertGreater(japanese.text.count("\n"), 0)         # CJK breaks between characters
                self.assertTrue(all(px(line) <= 100 for line in japanese.text.split("\n")))
            finally:
                wb.FOLDER = old
                wb._CACHE.clear()


NO_START = set("。、，．）」』】〕〉》〗〙〛｝］！？：；・ーゝゞヽヾ々〻ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ")
NO_END = set("（「『【〔〈《〖〘〚｛［")


class WrapCjk(unittest.TestCase):
    SAMPLES = (JAPANESE, CHINESE * 3, TRADITIONAL * 4, "「こんにちは」と彼は言った。（本当に？）私は驚いた！" * 2,
               "価格は（税込）1,000円です。「購入」ボタンを押してください。")

    def test_kinsoku_at_every_limit(self) -> None:
        for text in self.SAMPLES:
            for limit in range(30, 300, 10):
                result = tw.wrap(text, limit, px)
                lines = result.text.split("\n")
                self.assertEqual(result.text.replace("\n", ""), text)
                for line in lines[1:]:
                    self.assertNotIn(line[0], NO_START, (limit, result.text))
                for line in lines[:-1]:
                    self.assertNotIn(line[-1], NO_END, (limit, result.text))

    def test_a_dictionary_word_is_never_split_while_a_boundary_fits(self) -> None:
        for text in self.SAMPLES:
            state = wb.analyze(text)
            for limit in range(30, 300, 10):
                result = tw.wrap(text, limit, px)
                if result.cut:
                    continue                                    # a word alone was wider than the room
                at = 0
                for line in result.text.split("\n")[:-1]:
                    at += len(line)
                    self.assertNotEqual(state[at], 1, (limit, result.text))

    def test_every_line_fits_when_a_break_is_possible(self) -> None:
        for text in self.SAMPLES:
            for limit in range(40, 300, 10):
                result = tw.wrap(text, limit, px)
                self.assertTrue(all(px(line) <= limit for line in result.text.split("\n")), (limit, result.text))

    def test_a_word_wider_than_the_room_is_cut_between_characters_with_kinsoku(self) -> None:
        result = tw.wrap("コンピュータ。", 40, px)                  # 6 characters, room for 4
        lines = result.text.split("\n")
        self.assertGreater(len(lines), 1)
        self.assertGreater(result.cut, 0)
        self.assertEqual(result.text.replace("\n", ""), "コンピュータ。")
        for line in lines[1:]:
            self.assertNotIn(line[0], NO_START)
        result = tw.wrap("研究生命的起源", 20, px)
        self.assertTrue(all(px(line) <= 20 for line in result.text.split("\n")))

    def test_mixed_latin_and_cjk(self) -> None:
        text = "Fish Tycoonは楽しいゲームです。You have %d fish!"
        for limit in range(60, 260, 20):
            result = tw.wrap(text, limit, px)
            self.assertEqual(re.sub(r"\s", "", result.text), re.sub(r"\s", "", text))
            self.assertTrue(all(px(line) <= limit for line in result.text.split("\n")), (limit, result.text))
            self.assertTrue(any("%d" in line for line in result.text.split("\n")), (limit, result.text))

    def test_placeholders_inside_cjk_are_never_split(self) -> None:
        text = "あなたは%d匹の魚と%sを持っています。{n: one=魚 | other=魚}が必要です。"
        for limit in range(30, 300, 10):
            result = tw.wrap(text, limit, px)
            flat = result.text.replace("\n", "")
            self.assertEqual(flat, text)
            for token in ("%d", "%s", "{n: one=魚 | other=魚}"):
                # no break inside the token: its characters sit on one line
                self.assertTrue(any(token in line for line in result.text.split("\n")), (limit, token, result.text))

    def test_empty_lines_and_lines_with_no_words(self) -> None:
        self.assertEqual(tw.wrap("", 50, px).text, "")
        self.assertEqual(tw.wrap("。", 50, px).text, "。")
        self.assertEqual(tw.wrap("。。。。。。。。", 30, px).text.replace("\n", ""), "。。。。。。。。")
        rare = "𠀀𠀁𠀂𠀃𠀄𠀅𠀆𠀇𠀈𠀉"                                    # Han with no dictionary entry
        result = tw.wrap(rare, 50, px)
        self.assertEqual(result.text.replace("\n", ""), rare)
        self.assertTrue(all(px(line) <= 50 for line in result.text.split("\n")))


if __name__ == "__main__":
    unittest.main()
