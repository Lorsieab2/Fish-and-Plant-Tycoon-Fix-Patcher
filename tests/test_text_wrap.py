"""Wrap to fit (src/text_wrap.py): the English-width rule, CJK kinsoku, placeholders and grapheme
clusters kept whole, Thai without spaces reported, an over-long word cut, a no-op on a line that
already fits. Measured with a fake font: 10 pixels per letter, 20 per CJK character, 0 per mark."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import text_wrap as tw  # noqa: E402
import unicode_data  # noqa: E402


def measure(line: str) -> int:
    total = 0
    for cluster in unicode_data.graphemes(line):
        cp = ord(cluster[0])
        total += 20 if tw._in(cp, tw.ID_RANGES) else 10
    return total


def widest(text: str) -> int:
    return tw.english_width(text, measure)


class WrapToFit(unittest.TestCase):
    def test_limit_is_the_widest_english_line(self) -> None:
        self.assertEqual(tw.english_width("ab\nabcde\nabc", measure), 50)
        self.assertEqual(tw.english_width("", measure), 0)
        result = tw.wrap("Vous avez vendu beaucoup de poissons ce jour", tw.english_width("abcde\nabcdefghij", measure),
                         measure)
        self.assertLessEqual(widest(result.text), 100)
        self.assertEqual(result.text.replace("\n", " "), "Vous avez vendu beaucoup de poissons ce jour")

    def test_only_whitespace_changes(self) -> None:
        text = "one two three four five six seven eight nine ten"
        out = tw.wrap(text, 120, measure).text
        self.assertEqual(out.split(), text.split())
        self.assertTrue(all(measure(line) <= 120 for line in out.split("\n")))
        self.assertFalse(any(line != line.rstrip() for line in out.split("\n")))

    def test_line_that_fits_is_a_no_op(self) -> None:
        self.assertEqual(tw.wrap("short text", 500, measure).text, "short text")
        self.assertEqual(tw.wrap("one\ntwo", 500, measure).text, "one two")      # soft breaks are decided again
        self.assertFalse(tw.needs_wrap("abc", "abcdef", measure))
        self.assertTrue(tw.needs_wrap("abcdefg", "abcdef", measure))
        self.assertFalse(tw.needs_wrap("", "abcdef", measure))

    def test_blank_line_stays_a_paragraph_break(self) -> None:
        self.assertEqual(tw.wrap("aaa bbb\n\nccc ddd", 500, measure).text, "aaa bbb\n\nccc ddd")

    def test_old_breaks_are_rejoined_then_rebroken(self) -> None:
        self.assertEqual(tw.wrap("aaa\nbbb ccc\nddd", 70, measure).text, "aaa bbb\nccc ddd")

    def test_hyphen_break_but_not_before_a_digit(self) -> None:
        self.assertEqual(tw.wrap("well-known", 60, measure).text, "well-\nknown")
        self.assertEqual(tw.wrap("ab-12345", 40, measure).text.replace("\n", "|").count("|"), 1)
        self.assertNotIn("-\n1", tw.wrap("ab-12345", 40, measure).text)

    def test_cjk_breaks_anywhere_but_kinsoku(self) -> None:
        text = "今日は魚を三匹売りました。ありがとう、また来てください！"
        out = tw.wrap(text, 100, measure).text
        lines = out.split("\n")
        self.assertGreater(len(lines), 1)
        self.assertEqual(out.replace("\n", ""), text)
        for line in lines:
            self.assertLessEqual(measure(line), 100)
            self.assertNotIn(line[0], tw.NO_START)
            self.assertNotIn(line[-1], tw.NO_END)

    def test_kinsoku_forced_cases(self) -> None:
        out = tw.wrap("あいうえ。おかき", 80, measure).text          # four letters fit; 。 may not start a line
        for line in out.split("\n"):
            self.assertNotIn(line[0], "。、，．）」』】！？")
        out = tw.wrap("あいう「えおか」き", 60, measure).text        # 「 may not end a line
        for line in out.split("\n"):
            self.assertNotIn(line[-1], "（「『【")
        self.assertEqual(out.replace("\n", ""), "あいう「えおか」き")

    def test_no_break_inside_a_placeholder(self) -> None:
        for text, limit in (("sold %d fish today", 50), ("Vendu {%1: one=un poisson | other=%d poissons} ici", 60),
                            ("x {name} y", 20), ("売った%d匹の魚", 40)):
            out = tw.wrap(text, limit, measure).text
            for m in tw.PLACEHOLDER_RE.finditer(text):
                self.assertIn(m.group(), out)
            self.assertEqual(out.replace("\n", "").replace(" ", ""), text.replace(" ", ""))

    def test_no_break_inside_a_cluster(self) -> None:
        text = "éééé \U0001F468‍\U0001F469‍\U0001F467 \U0001F1EB\U0001F1F7\U0001F1EF\U0001F1F5"
        for limit in (10, 20, 30):
            out = tw.wrap(text, limit, measure).text
            for line in out.split("\n"):
                self.assertEqual("".join(unicode_data.graphemes(line)), line)
            # no line starts with a combining mark or a joiner
            for line in out.split("\n"):
                self.assertNotIn(line[0], "́‍")
        out = tw.wrap("ééé", 10, measure).text
        self.assertEqual(out, "é\né\né")

    def test_overlong_word_is_cut(self) -> None:
        result = tw.wrap("pneumonoultramicroscopic", 100, measure)
        self.assertEqual(result.cut, 1)
        self.assertEqual(result.text.replace("\n", ""), "pneumonoultramicroscopic")
        self.assertTrue(all(measure(line) <= 100 for line in result.text.split("\n")))
        self.assertEqual(tw.wrap("a b", 100, measure).cut, 0)

    def test_thai_without_spaces_is_reported_not_cut(self) -> None:
        thai = "ฉันขายปลาสามตัววันนี้"
        result = tw.wrap(thai, 50, measure)
        self.assertEqual(result.text, thai)
        self.assertEqual(result.cannot_wrap, [thai])
        self.assertEqual(result.cut, 0)

    def test_thai_with_spaces_breaks_at_the_spaces(self) -> None:
        result = tw.wrap("ฉันขาย ปลาสามตัว วันนี้", 100, measure)
        self.assertEqual(result.text.replace("\n", " "), "ฉันขาย ปลาสามตัว วันนี้")
        self.assertGreater(result.text.count("\n"), 0)

    def test_hangul_breaks_at_spaces_only(self) -> None:
        out = tw.wrap("오늘 물고기를 팔았습니다", 100, measure).text
        self.assertEqual(out.replace("\n", " "), "오늘 물고기를 팔았습니다")

    def test_ascii_english_is_unchanged_when_it_fits(self) -> None:
        for english in ("You have sold %d fish!", "Age: ", "Line one\nLine two is longer"):
            self.assertFalse(tw.needs_wrap(english, english, measure))
        self.assertEqual(tw.wrap("You have sold %d fish!", 220, measure).text, "You have sold %d fish!")


if __name__ == "__main__":
    unittest.main()
