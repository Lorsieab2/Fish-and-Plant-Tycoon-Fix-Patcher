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


class MaxPricesEntryTests(unittest.TestCase):
    """Each game's Species / prices section explains the Max Prices button: where it is, the limit it
    sets and how, which save-wide effects count and which do not, and that sales there are slower."""

    def entry(self, game_id: str):
        title = {"fish": "Species and prices", "plant": "Prices"}[game_id]
        group = next(g for g in gm.load_page(game_id).groups if g.title == title)
        return next(f for f in group.facts if f.text.startswith("The highest asking price that sells"))

    def test_fish(self) -> None:
        fact = self.entry("fish")
        button = dict(fact.patched)["optimize_prices"]
        for text in ("2B - 1", "0x424240", "0x4243DC", "ornaments", "Golden Seahorse", "Advertising",
                     "much more slowly"):
            self.assertIn(text, fact.text)
        for text in ("Max Prices", "Species Chart", "x 400-519", "Fish Store", "x 420-539", "2B - 1",
                     "much more slowly", "not read"):
            self.assertIn(text, button)
        rendered = gm.render_text(gm.load_page("fish"))
        self.assertIn("Max Prices", rendered)

    def test_plant(self) -> None:
        fact = self.entry("plant")
        button = dict(fact.patched)["optimize_prices"]
        for text in ("2V", "0x436BE0", "Golden Berries", "0x2183", "only save-wide", "Plant Food",
                     "pests", "Visitors", "much more slowly"):
            self.assertIn(text, fact.text)
        for text in ("Max Prices", "Nursery", "x 449-611", "Golden Berries", "per-plant effects are left out",
                     "much more slowly"):
            self.assertIn(text, button)
        self.assertIn("Max Prices", gm.render_text(gm.load_page("plant")))

    def test_the_examples_are_the_models(self) -> None:
        import breeding_plant as BP
        fact = self.entry("plant")
        for v in (100, 250):
            self.assertIn(f"{BP.shop_max_price(v, False)}", fact.text)
            self.assertIn(f"{BP.shop_max_price(v, True)}", fact.text)


VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"


class SpeciesCountTests(unittest.TestCase):
    """Each Prices section states the number of species, stock and with the patcher's added species,
    and the numbers are the Breeding Guide models' (src/breeding_*.py load(None, extras)) and the
    executables' own species loops."""

    def counts_fact(self, game_id: str):
        title = {"fish": "Species and prices", "plant": "Prices"}[game_id]
        group = next(g for g in gm.load_page(game_id).groups if g.title == title)
        return next(f for f in group.facts if f.text.startswith("There are "))

    def test_numbers_are_the_models(self) -> None:
        import breeding_fish as BF
        import breeding_plant as BP
        for game_id, module, setting in (("fish", BF, "ds_fish"), ("plant", BP, "new_flowers")):
            stock = len(module.load(None, False).species())
            extra = len(module.load(None, True).species())
            fact = self.counts_fact(game_id)
            self.assertTrue(fact.text.startswith(f"There are {stock} species"), fact.text)
            added = dict(fact.patched)[setting]
            self.assertTrue(added.startswith(f"{extra} species"), added)
            self.assertIn(f"{extra - stock} more", added)
        self.assertEqual((len(BF.load(None, False).species()), len(BF.load(None, True).species())), (21 * 21, 28 * 28))
        self.assertEqual((len(BP.load(None, False).species()), len(BP.load(None, True).species())), (23 * 23, 23 * 37))

    @unittest.skipUnless((VANILLA / "Fish Tycoon" / "Fish Tycoon.exe").is_file(), "needs the vanilla Fish Tycoon.exe")
    def test_fish_counter_walks_21_by_21(self) -> None:
        exe = (VANILLA / "Fish Tycoon" / "Fish Tycoon.exe").read_bytes()
        self.assertEqual(exe[0x1924B:0x1924E], bytes.fromhex("8D5815"))          # lea ebx, [eax + 0x15]: 21 rows
        self.assertEqual(exe[0x19253:0x19258], bytes.fromhex("BA07000000"))      # mov edx, 7: 7 x 3 entries
        self.assertEqual(exe[0x19277:0x1927D], bytes.fromhex("81C6D8040000"))    # add esi, 0x4D8: a 31-entry row

    @unittest.skipUnless((VANILLA / "Plant Tycoon" / "Plant Tycoon.exe").is_file(), "needs the vanilla Plant Tycoon.exe")
    def test_plant_counter_walks_23_by_23(self) -> None:
        exe = (VANILLA / "Plant Tycoon" / "Plant Tycoon.exe").read_bytes()
        self.assertEqual(exe[0x4C579:0x4C581], bytes.fromhex("83C17D" "BB17000000"))  # flags from + 0x7D, 23 foliages
        self.assertEqual(exe[0x4C583:0x4C588], bytes.fromhex("BA17000000"))           # 23 flowers
        self.assertEqual(exe[0x1DBE1:0x1DBE9], bytes.fromhex("C744241017000000"))     # 0x41DBD0: 23 foliages
        self.assertEqual(exe[0x1DBF2:0x1DBF7], bytes.fromhex("BB17000000"))           # 23 flowers


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
