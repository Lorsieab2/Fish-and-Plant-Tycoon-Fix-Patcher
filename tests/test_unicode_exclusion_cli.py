"""The command line and the two Unicode text settings (docs/UNICODE_SPEC.md row 1d).

"Render Unicode with In-Game Fonts" (on by default) and "Use Unicode Font" exclude each other: asking
for one turns off the other when that one is only on by default, and asking for both is refused.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fish_patcher  # noqa: E402
import plant_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

INGAME, SYSTEM = "unicode_ingame_fonts", "unicode_system_font"


def args(**kw):
    return Namespace(enable=kw.get("enable"), disable=kw.get("disable"), disable_all=kw.get("disable_all", False))


class ExclusionCli(unittest.TestCase):
    def engines(self):
        yield "fish", fish_patcher
        yield "plant", plant_patcher

    def test_the_default_is_in_game_fonts(self):
        for game, engine in self.engines():
            enabled = engine.enabled_settings(combined.load_manifest(game), args())
            self.assertIn(INGAME, enabled, game)
            self.assertNotIn(SYSTEM, enabled, game)

    def test_asking_for_the_system_font_turns_the_default_off(self):
        for game, engine in self.engines():
            enabled = engine.enabled_settings(combined.load_manifest(game), args(enable=[SYSTEM]))
            self.assertIn(SYSTEM, enabled, game)
            self.assertNotIn(INGAME, enabled, game)

    def test_asking_for_in_game_fonts_turns_the_system_font_off(self):
        for game, engine in self.engines():
            manifest = combined.load_manifest(game)
            enabled = engine.enabled_settings(manifest, args(disable_all=True, enable=[INGAME]))
            self.assertEqual({INGAME} & enabled, {INGAME}, game)
            self.assertNotIn(SYSTEM, enabled, game)

    def test_asking_for_both_is_refused(self):
        for game, engine in self.engines():
            with self.assertRaises(engine.PatchError) as why:
                engine.enabled_settings(combined.load_manifest(game), args(enable=[INGAME, SYSTEM]))
            self.assertIn("cannot both be on", str(why.exception), game)

    def test_the_result_always_passes_the_requirements_check(self):
        for game, engine in self.engines():
            manifest = combined.load_manifest(game)
            for enable in ([], [SYSTEM], [INGAME]):
                fish_patcher.check_setting_requirements(manifest, engine.enabled_settings(manifest, args(enable=enable)))


if __name__ == "__main__":
    unittest.main()
