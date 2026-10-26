"""Bigger tanks: 26 fish (Fish Tycoon) in the patcher: the setting, its byte
patches, and the checksum record and pin of every byte-patch combination."""

from __future__ import annotations

import itertools
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402
import pin_tank_expansion  # noqa: E402

SETTING = "bigger_tanks"


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("fish")
        self.setting = combined.patch_settings("fish")[SETTING]

    def test_setting_is_off_by_default_and_says_what_it_does(self) -> None:
        self.assertFalse(self.setting["default"])
        self.assertEqual(self.setting["name"], "Bigger tanks: 26 fish")
        self.assertIn("26 fish", self.setting["summary"])
        self.assertIn("down to 21", self.setting["warning"])

    def test_every_patch_requires_the_setting_and_matches_the_list(self) -> None:
        mine = [p for p in self.manifest["patches"] if p["id"].startswith("tank26_")]
        self.assertEqual(len(mine), 45)
        self.assertEqual(len(pin_tank_expansion.TANK_PATCHES), 45)
        for patch in mine:
            self.assertEqual(patch["requires"], [SETTING])
            self.assertEqual(len(patch["expected"].split()), len(patch["replacement"].split()), patch["id"])

    def test_no_patch_overlaps_another_settings_patch(self) -> None:
        def span(p: dict) -> tuple[int, int]:
            start = int(p["offset"], 16)
            return start, start + len(p["replacement"].split())
        mine = [span(p) for p in self.manifest["patches"] if p["id"].startswith("tank26_")]
        others = [span(p) for p in self.manifest["patches"]
                  if not p["id"].startswith("tank26_") and not p["id"].startswith("update_pe_checksum")]
        for a, b in mine:
            for c, d in others:
                self.assertFalse(a < d and c < b, f"0x{a:X} overlaps 0x{c:X}")

    def test_every_byte_combination_has_a_checksum_record_and_a_pin(self) -> None:
        settings = pin_tank_expansion.byte_settings(self.manifest)
        self.assertIn(SETTING, settings)
        self.assertEqual(len(settings), 5)
        checksums = {tuple(p["requires"]) for p in self.manifest["patches"] if p["id"].startswith("update_pe_checksum")}
        pins = self.manifest["patched_sha256_by_settings"]
        for count in range(1, len(settings) + 1):
            for combo in itertools.combinations(sorted(settings), count):
                self.assertIn(combo, checksums)
                self.assertRegex(pins.get(fish_patcher.settings_key(set(combo)), ""), r"^[0-9A-F]{64}$", combo)
        self.assertEqual(len(checksums), 2 ** len(settings) - 1)

    def test_release_packages_the_doc(self) -> None:
        import build_release

        self.assertIn("docs/fish-tycoon-tank-expansion.md", build_release.FILES)
        self.assertTrue((ROOT / "docs" / "fish-tycoon-tank-expansion.md").is_file())


if __name__ == "__main__":
    unittest.main()
