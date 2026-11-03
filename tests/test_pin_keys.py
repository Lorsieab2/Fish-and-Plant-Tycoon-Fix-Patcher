"""The executable pins' keys are exactly the combinations the patcher can build.

The expected set is recomputed here from the settings' rules, independently of
scripts/pin_keys.py: every non-empty set of the settings that are neither loader tails
(fish_patcher.pin_settings leaves them out) nor asset merges, with every `requires_settings`
on and no `conflicts_settings` pair. A pin script that drops combinations (as pin_ds_store.py
did for every setting that needs DS Store Items) or adds loader-tail keys (as pin_new_flowers.py
did) fails here.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import fish_patcher  # noqa: E402
import pin_keys  # noqa: E402


def manifest(game: str) -> dict:
    return json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))


def expected_keys(m: dict) -> set[str]:
    ids = [s["id"] for s in m["settings"] if "asset_merge" not in s]
    ids = sorted(fish_patcher.pin_settings(m, set(ids)))
    by_id = {s["id"]: s for s in m["settings"]}
    keys = set()
    for bits in itertools.product((False, True), repeat=len(ids)):
        on = {i for i, b in zip(ids, bits) if b}
        if not on:
            continue
        if any(not set(by_id[i].get("requires_settings", [])) <= on for i in on):
            continue
        if any(set(by_id[i].get("conflicts_settings", [])) & on for i in on):
            continue
        keys.add(",".join(sorted(on)))
    return keys


class PinKeys(unittest.TestCase):
    def test_the_keys_are_every_buildable_combination(self) -> None:
        for game in ("fish", "plant"):
            m = manifest(game)
            have = set(m["patched_sha256_by_settings"])
            want = expected_keys(m)
            self.assertEqual(len(have - want), 0, f"{game}: keys the patcher never builds: {sorted(have - want)[:5]}")
            self.assertEqual(len(want - have), 0, f"{game}: combinations with no pin: {sorted(want - have)[:5]}")
            self.assertEqual(want, pin_keys.valid_keys(m))

    def test_no_key_names_a_loader_tail(self) -> None:
        for game in ("fish", "plant"):
            m = manifest(game)
            tails = {s["id"] for s in m["settings"] if (s.get("companion") or {}).get("loader_tail")}
            self.assertTrue(tails)
            for key in m["patched_sha256_by_settings"]:
                self.assertFalse(tails & set(key.split(",")), key)

    def test_finish_keeps_exactly_the_valid_keys(self) -> None:
        m = manifest("plant")
        pins = dict(m["patched_sha256_by_settings"])
        pins["extra_greenhouses,sort_seeds"] = "0" * 64                  # needs Store Upgrades: never built
        pins["new_flowers,translations"] = "0" * 64                     # a loader tail
        self.assertEqual(pin_keys.finish(m, pins), m["patched_sha256_by_settings"])


if __name__ == "__main__":
    unittest.main()
