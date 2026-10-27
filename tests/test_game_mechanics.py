"""The Game Mechanics page: exact odds, labels, wording rules, rendering."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import game_mechanics as gm  # noqa: E402

VAGUE = re.compile(r"\b(etc\.?|some effect|not worked out|somehow|various|roughly)\b", re.IGNORECASE)


def all_text(page: gm.GamePage) -> list[str]:
    texts = [page.intro, page.time_and_units]
    for group in page.groups:
        texts.append(group.note)
        for fact in group.facts:
            texts.append(fact.text)
            texts.extend(fact.subs)
            texts.extend(text for _, text in fact.patched)
    return texts


class OddsTests(unittest.TestCase):
    def test_rand_mod_n_is_counted_over_the_whole_rand_period(self) -> None:
        # rand() % 100: values 0-67 come up 328 times in 32768, 68-99 come up 327 times.
        self.assertEqual(gm.rand_count(100, 41), 41 * 328)
        self.assertEqual(gm.rand_count(100, 82), 68 * 328 + 14 * 327)
        self.assertEqual(gm.chance(100, 41), "41.04%")
        self.assertEqual(gm.chance(100, 50), "50.05%")
        self.assertEqual(gm.chance(10000, 10), "0.12%")
        self.assertEqual(gm.chance(2, 1), "50.00%")

    def test_random_zero_and_one_always_return_zero(self) -> None:
        self.assertEqual(gm.chance(0, 1), "100.00%")
        self.assertEqual(gm.chance(1, 1), "100.00%")

    def test_tiny_chances_keep_their_digits(self) -> None:
        self.assertNotEqual(gm.chance(30000, 1), "0.00%")

    def test_test_wording(self) -> None:
        self.assertEqual(gm.at_most(100, 40), "Random(100) <= 40 (41.04%)")
        self.assertEqual(gm.below(100, 82), "Random(100) < 82 (82.04%)")


class PageTests(unittest.TestCase):
    def test_every_page_loads_and_renders(self) -> None:
        for game_id in gm.GAMES:
            page = gm.load_page(game_id)
            self.assertEqual(page.game_id, game_id)
            text = gm.render_text(page)
            self.assertIn("Time and units", text)
            self.assertGreater(len(page.groups), 3)

    def test_no_vague_wording(self) -> None:
        for game_id in gm.GAMES:
            for text in all_text(gm.load_page(game_id)):
                self.assertIsNone(VAGUE.search(text), text)

    def test_patched_lines_name_real_settings(self) -> None:
        known = {game_id: set(gm.manifest_settings(game_id)) for game_id in gm.GAMES}
        for game_id in gm.GAMES:
            for group in gm.load_page(game_id).groups:
                for fact in group.facts:
                    for setting_id, _ in fact.patched:
                        self.assertIn(setting_id, known[game_id])

    def test_patched_line_uses_the_manifest_name_and_default(self) -> None:
        settings = {"x": {"name": "Some Fix", "default": True}}
        self.assertEqual(gm.patched_line("fish", "x", "it changes.", settings),
                         "With the patcher (Some Fix, on by default): it changes.")
        self.assertIsNone(gm.patched_line("fish", "missing", "it changes.", settings))

    def test_every_bullet_is_labelled(self) -> None:
        for game_id in gm.GAMES:
            for style, line in gm.render_lines(gm.load_page(game_id)):
                if style == "bullet":
                    self.assertRegex(line, r"^\[(VERIFIED-E|VERIFIED-C|UNCONFIRMED)\] ")

    def test_chances_on_the_page_are_exact(self) -> None:
        # Any "Random(n) <= m" or "Random(n) < k" on the page must carry its exact odds.
        pattern = re.compile(r"Random\((\d+)\) (<=|<) (\d+) \((\d+\.\d+)%\)")
        for game_id in gm.GAMES:
            for text in all_text(gm.load_page(game_id)):
                for n, op, value, shown in pattern.findall(text):
                    k = int(value) + (1 if op == "<=" else 0)
                    self.assertEqual(f"{shown}%", gm.chance(int(n), k), text)
                for n, value, shown in re.findall(r"Random\((\d+)\) >= (\d+) \((\d+\.\d+)%\)", text):
                    self.assertEqual(f"Random({n}) >= {value} ({shown}%)", gm.at_least(int(n), int(value)), text)


class WindowSourceTests(unittest.TestCase):
    def test_tools_tab_opens_the_window(self) -> None:
        source = (ROOT / "src" / "tools_tab.py").read_text(encoding="utf-8")
        self.assertIn("Game Mechanics...", source)
        self.assertIn("game_mechanics_window.open_window", source)

    def test_window_never_writes_files(self) -> None:
        source = (ROOT / "src" / "game_mechanics_window.py").read_text(encoding="utf-8")
        source += (ROOT / "src" / "game_mechanics.py").read_text(encoding="utf-8")
        for call in ("write_text", "write_bytes", "open(", "unlink", "rmtree", "mkdir"):
            self.assertNotIn(call, source, call)


if __name__ == "__main__":
    unittest.main()
