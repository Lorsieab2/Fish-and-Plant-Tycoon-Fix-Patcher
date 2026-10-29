"""Every duration on the Game Mechanics pages names its clock.

The owner's rule: a line that gives a duration, rate or timer says whether it
is real time (the wall clock, whatever the game speed) or game time (age
steps in Fish Tycoon, age units in Plant Tycoon, which scale with the speed).
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import game_mechanics as gm  # noqa: E402

DURATION = re.compile(
    r"\b\d[\d,.]*\s*(?:-\s*\d[\d,.]*\s*)?(?:s|sec|seconds?|min|minutes?|h|hours?|days?|ms|cs)\b"
    r"|\bevery (?:quarter )?second\b|\bper second\b|\bquarter second\b",
    re.IGNORECASE,
)
CLOCK = re.compile(r"real time|real-time|game time|age steps?|age units?|per frame|frames?", re.IGNORECASE)
QUOTED = re.compile(r"\"[^\"]*\"")       # the game's own words, e.g. "one drop every half hour"


class ClockTests(unittest.TestCase):
    def test_every_duration_names_its_clock(self) -> None:
        missing = []
        for game_id in gm.GAMES:
            for style, text in gm.render_lines(gm.load_page(game_id)):
                if DURATION.search(QUOTED.sub("", text)) and not CLOCK.search(text):
                    missing.append(f"{game_id} {style}: {text[:120]}")
        self.assertEqual(missing, [])

    def test_each_page_has_a_clocks_group(self) -> None:
        for game_id in gm.GAMES:
            titles = [group.title for group in gm.load_page(game_id).groups]
            self.assertIn("Clocks", titles, game_id)


if __name__ == "__main__":
    unittest.main()


class DeadCodeTests(unittest.TestCase):
    """Verified dead code stays labelled as such, never offered as a player feature."""

    DEAD = {
        "fish": ("has expired", "Backspace branch"),
        "plant": ("\"d then w\" cheat",),
    }

    def test_dead_code_is_labelled_not_reachable(self) -> None:
        for game_id, phrases in self.DEAD.items():
            lines = [text for _, text in gm.render_lines(gm.load_page(game_id))]
            dead = [text for text in lines if "Not reachable" in text]
            self.assertTrue(dead, game_id)
            for phrase in phrases:
                self.assertTrue(any(phrase in text for text in dead), f"{game_id}: {phrase}")
                self.assertFalse(any(phrase in text for text in lines if "Not reachable" not in text),
                                 f"{game_id}: {phrase} appears outside the dead-code line")


class ParityTests(unittest.TestCase):
    """Fish and Plant Tycoon cover the same topics: each page maps every group of the other."""

    SHARED = {"Clocks", "Time away (catch-up)", "Ages and stages", "A new game",
              "Hidden keys, clicks and cheats", "Chance and timer index", "Time Warp (patcher)"}

    def test_every_topic_of_the_other_game_is_mapped(self) -> None:
        titles = {gid: [group.title for group in gm.load_page(gid).groups] for gid in gm.GAMES}
        for game_id, other, name in (("fish", "plant", "Plant"), ("plant", "fish", "Fish")):
            groups = {group.title: group for group in gm.load_page(game_id).groups}
            self.assertTrue(self.SHARED <= set(groups), game_id)
            mapping = " ".join(fact.text for fact in groups[f"{name} Tycoon's topics here"].facts)
            for title in titles[other]:
                if title in self.SHARED or title.endswith("topics here"):
                    continue
                self.assertIn(title.split(" one by one")[0], mapping, f"{game_id}: {title}")
