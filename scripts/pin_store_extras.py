"""Pin the "Free upgrades" and "Add Money cheat ($1,000)" settings into the
fish and plant manifests.

    python scripts/pin_store_extras.py

Run after scripts/pin_time_warp.py, and after rebuilding "DS Store Items.dll"
(scripts/build_ftfp_ds_store.ps1), "Store Upgrades and Items.dll"
(scripts/build_ftfp_plant_upgrades.ps1) or their art. Both settings live on
the store's Upgrades screen (DS Store Items / Add new store upgrades and
items), which they turn on, as Time Warp does: its DLL reads "Free
Upgrades.ini" / "Add Money.ini" beside it, and each setting ships only that
file. They write no executable bytes, so each pin with them is the same
combination's pin without them.

The Upgrades screen settings' own companion files (the rebuilt DLLs and the
new art) are re-recorded in place, so the settings keep their order.
"""

from __future__ import annotations

import hashlib
import json
from itertools import combinations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pin_ds_store  # noqa: E402
import pin_plant_upgrades  # noqa: E402

GAMES = {
    "fish": {
        "manifest": ROOT / "data" / "fish_manifest.json",
        "folder": "Fish Tycoon Fix Patcher DLLs",
        "screen_setting": "ds_store",
        "screen_files": pin_ds_store.companion_files,
        "screen": "the Supplies store's Upgrades page (DS Store Items)",
        "items": "the Magic Pufferfish, Blue-Spotted Stingray and Moray Eel ($1250 each), Exotic Fish Eggs "
                 "($2300), the Radioactive Growth Hormone ($10,000), the Revival Potion ($10,000), ClonaFish "
                 "($2,500), and the Time Warp clock ($500), Add Money ($950) and the Extra Tank ($10,000 each) when "
                 "those settings are on",
        "free_rules": "The Puffer Fish, Sting Ray and Moray Eel are still one of each in your tanks (unless Buy "
                      "Multiple Golden Seahorses is on), the eggs and the chemicals still go in a supply slot, the "
                      "extra tanks are still bought in order (Tank 4, then 5, then 6), and "
                      "the game's own purchase confirmations are still asked.",
        "where": "in the net next to the Time Warp clock",
    },
    "plant": {
        "manifest": ROOT / "data" / "plant_manifest.json",
        "folder": "Plant Tycoon Fix Patcher DLLs",
        "screen_setting": "plant_upgrades",
        "screen_files": pin_plant_upgrades.companion_files,
        "screen": "the Supplies store's Upgrades view (Add new store upgrades and items)",
        "items": "Legendary Seeds ($5000), the Radioactive Plant Formula ($10,000), the Revival Potion "
                 "($10,000), Revita-Seed ($2,500), the Formula Bomb ($30,000), the Fourth, Fifth and Sixth "
                 "Seed Box ($1000 each), and the Time Warp clock ($500), Add Money ($950), the Extra Greenhouse "
                 "($10,000 each) and the Extra Nursery ($10,000 each) when those settings are on",
        "free_rules": "Legendary Seeds are still three a day and need room in the seed tray, the formula, the Revival "
                      "Potion, Revita-Seed and the Formula Bomb need room in the chemical tray, and the seed boxes, "
                      "extra greenhouses and extra nurseries are still bought in order, once each.",
        "where": "on the Nursery shelf next to the Time Warp clock",
    },
}

SETTINGS = {
    "free_upgrades": {
        "source": "assets/free_upgrades",
        "file": "Free Upgrades.ini",
    },
    "add_money": {
        "source": "assets/money_cheat",
        "file": "Add Money.ini",
    },
}


def setting(setting_id: str, game: dict) -> dict:
    if setting_id == "free_upgrades":
        return {
            "id": setting_id,
            "name": "Free upgrades",
            "summary": "Every item on the store's Upgrades screen costs $0.",
            "description": (
                f"Every item on {game['screen']}, which this setting turns on, costs $0: {game['items']}. "
                "The price shown says $0 and no money is taken. Everything else stays: "
                f"{game['free_rules']} The game's own store items keep their prices. Saves keep their layout."
            ),
            "category": "main",
            "default": False,
            "requires_settings": [game["screen_setting"]],
        }
    return {
        "id": setting_id,
        "name": "Add Money cheat ($1,000)",
        "summary": "Adds a +$1,000 item to the store's Upgrades screen: pay $950, get $1,000, as often as you like.",
        "description": (
            f"Adds a pile of gold coins, +$1,000, {game['where']} on {game['screen']}, which this setting turns "
            "on. It costs $950 ($0 with Free upgrades), is bought like the other items there (the price is shown, "
            "you need the money, and you confirm), and then adds $1,000 to your money: $50 more each time, or "
            "$1,000 with Free upgrades. It can be bought any number of times. Money never goes past the game's "
            "own maximum. Saves keep their layout."
        ),
        "category": "main",
        "default": False,
        "requires_settings": [game["screen_setting"]],
    }


def companion(setting_id: str, game: dict) -> dict:
    item = SETTINGS[setting_id]
    data = (ROOT / item["source"] / item["file"]).read_bytes()
    return {"source": item["source"], "files": [{
        "path": item["file"], "destination": f"{game['folder']}/{item['file']}",
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}]}


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    new_ids = set(SETTINGS)
    for game_id, game in GAMES.items():
        manifest = json.loads(game["manifest"].read_text(encoding="utf-8"))
        for entry in manifest["settings"]:
            if entry["id"] == game["screen_setting"]:
                entry["companion"]["files"] = game["screen_files"]()
        kept = [s for s in manifest["settings"] if s["id"] not in new_ids]
        for setting_id in SETTINGS:
            entry = setting(setting_id, game)
            entry["companion"] = companion(setting_id, game)
            kept.append(entry)
        manifest["settings"] = kept
        pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if not new_ids & set(k.split(","))}
        added = 0
        for key, value in list(pins.items()):
            enabled = set(key.split(","))
            if game["screen_setting"] not in enabled:
                continue
            for count in (1, 2):
                for extra in combinations(sorted(new_ids), count):
                    pins[",".join(sorted(enabled | set(extra)))] = value
                    added += 1
        manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
        game["manifest"].write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{game_id}: {added} Free upgrades / Add Money pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
