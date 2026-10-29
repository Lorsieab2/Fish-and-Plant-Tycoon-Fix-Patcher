"""Pin the "Time Warp" setting into the fish and plant manifests.

    python scripts/pin_time_warp.py

Run after scripts/pin_ds_store.py (fish) and scripts/pin_plant_upgrades.py and
scripts/pin_seed_refresh.py (plant). The setting needs the game's Upgrades
screen (DS Store Items / Add new store upgrades and items), whose DLL draws the
Time Warp item and runs it while "Time Warp.ini" sits beside it; the setting
ships only that file. It writes no executable bytes, so each pin with the
setting is the same combination's pin without it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "assets/time_warp"
FILE = "Time Warp.ini"
SETTING_ID = "time_warp"

GAMES = {
    "fish": {
        "manifest": ROOT / "data" / "fish_manifest.json",
        "folder": "Fish Tycoon Fix Patcher DLLs",
        "requires": ["ds_store"],
        "screen": "the Supplies store's Upgrades page (DS Store Items)",
        "ages": "every fish in all four tanks ages with every check (health, sickness, food, breeding and "
                "births), and research progresses",
    },
    "plant": {
        "manifest": ROOT / "data" / "plant_manifest.json",
        "folder": "Plant Tycoon Fix Patcher DLLs",
        "requires": ["plant_upgrades"],
        "screen": "the Supplies store's Upgrades view (Add new store upgrades and items)",
        "ages": "every plant ages with every check (water, health, pests, seeds ripening, old age), and the seed "
                "shop restocks if it is due",
    },
}


def setting(game: dict) -> dict:
    return {
        "id": SETTING_ID,
        "name": "Time Warp",
        "summary": "Adds a Time Warp item to the store's Upgrades screen: $500 to skip 1-72 hours, as if you had been away.",
        "description": (
            f"Adds a Time Warp item (a clock) to {game['screen']}, which this setting turns on. Clicking it "
            "asks, in a small Windows popup, how many hours should pass (1 to 72), then asks Yes/No and charges a "
            f"flat $500. Then {game['ages']}, exactly as if you had been away that many real-life hours, with no "
            "catch-up cap. Plants or fish can starve, dry out or die along the way, as they would while you were "
            "away. Refused while time is stopped. Saves keep their layout."
        ),
        "category": "main",
        "default": False,
        "requires_settings": list(game["requires"]),
    }


def companion(game: dict) -> dict:
    data = (ROOT / SOURCE / FILE).read_bytes()
    return {"source": SOURCE, "files": [{
        "path": FILE, "destination": f"{game['folder']}/{FILE}",
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}]}


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    for game_id, game in GAMES.items():
        manifest = json.loads(game["manifest"].read_text(encoding="utf-8"))
        entry = setting(game)
        entry["companion"] = companion(game)
        manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID] + [entry]
        pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
        added = 0
        for key, value in list(pins.items()):
            enabled = set(key.split(","))
            if set(game["requires"]) <= enabled:
                pins[",".join(sorted(enabled | {SETTING_ID}))] = value
                added += 1
        manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
        game["manifest"].write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{game_id}: {added} Time Warp pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
