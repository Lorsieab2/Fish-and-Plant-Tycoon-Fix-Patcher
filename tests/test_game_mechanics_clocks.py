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
