"""Pin the "Add new store upgrades and items" setting into the plant manifest.

    python scripts/pin_plant_upgrades.py

Run after rebuilding "Store Upgrades and Items.dll" (scripts/build_ftfp_plant_upgrades.ps1),
"Extra Seed Boxes.dll" (scripts/build_ftfp_seed_boxes.ps1) or the Upgrades art
(scripts/build_plant_upgrades_assets.py), and after scripts/pin_new_flowers.py.
It

  * records every companion file under assets/plant_tycoon_upgrades (both
    DLLs and the art) by size and SHA-256, with the game-relative destination
    it is copied to;
  * pins the output executable for every combination with the setting. It
    writes no executable bytes (the unused-flowers DLL loads the Upgrades DLL,
    which loads the Seed Boxes DLL), so each pin is the same combination's pin
    without it.

The other combinations' pins are left exactly as they are.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ds_fish_loader  # noqa: E402

MANIFEST = ROOT / "data" / "plant_manifest.json"
SOURCE = "assets/plant_tycoon_upgrades"
SETTING_ID = "plant_upgrades"
DLL_NAMES = ("Store Upgrades and Items.dll", "Extra Seed Boxes.dll")
FOLDER = ds_fish_loader.PLANT.patcher_files_folder

SETTING = {
    "id": SETTING_ID,
    "name": "Add new store upgrades and items",
    "summary": "Adds an Upgrades view to the Supplies store with Legendary Seeds (the new flowers), the Radioactive Plant Formula and its Bomb, the Revival Potion, Revita-Seed, Automatic Sprinklers, the Auto-Healer, and the Fourth, Fifth and Sixth Seed Box. Needs Add unused flowers.",
    "description": (
        "Adds an Upgrades link on the bricks at the left of the Supplies store. It opens a second "
        "view of the store with only the new items, each where it would sit in the store: "
        "Legendary Seeds on the seed shelves (three a day, $5000 each, any foliage with one of the "
        "unused flowers; the stock seed packets keep their stock flowers), the Radioactive Plant "
        "Formula with the chemicals ($10,000, 3 doses, far beyond spamming Fertilizer Bombs and Plant "
        "Food: every branch grows, the largest size, full bloom, a flower on every spot of every "
        "branch and leaf, no dead or brown leaves, full health, and always 5 seeds: all 5 when it is "
        "pollinated later, or, if it is already pollinated, all its seeds ripe at once), the Revival "
        "Potion beside it ($10,000, 3 doses: a dead plant it is dropped on comes back to life at full "
        "health), Revita-Seed beside that ($2,500, 3 doses: a plant that has given all its seeds can "
        "be pollinated again, as a fresh plant can), the Radioactive Plant Formula Bomb under the "
        "formula ($30,000, 3 bombs: one Radioactive Plant Formula dose for every live plant in the "
        "greenhouse on screen, the pots the Fertilizer Bomb reaches), Automatic Sprinklers ($10,000) "
        "on the tool shelf under the Extra Greenhouse and the Auto-Healer ($10,000) beside the Formula "
        "Bomb (each bought once; they work on every live potted plant in every greenhouse, on screen or "
        "not, through time away and the Time Warp too: the sprinklers keep the water at 500, never too "
        "dry and never so wet that pests come three times as often; the Auto-Healer clears pests, each "
        "counted under Plants Cured, and keeps health at 100; neither touches a dead plant, and old age "
        "still ends a plant's life; unpurchase: click an owned one and answer Yes, it switches off at "
        "once with no refund, and buying it again costs the full price; ownership is kept in \"Auto "
        "Upgrades <slot>.dat\"), and the Fourth, Fifth "
        "and Sixth Seed Box with the tool upgrades (\"Even more space for your seeds!\", $1000 each, "
        "bought in order like the stock boxes). Each new box opens a 40-seed drawer in a second "
        "chest on the Seed Storage screen; the gold arrows on its title bar switch between boxes "
        "1-3 and 4-6, and the greenhouse fills boxes 4-6 once 1-3 are full. Click Supplies in the "
        "bottom bar to leave the Upgrades view. Needs Add unused flowers. Each save slot keeps the "
        "new data in separate files beside the save. See docs/plant-tycoon-upgrades-design.md."
    ),
    "warning": (
        "Turning this off leaves bought Legendary seeds drawn as another seed packet, the formula "
        "drawn as an Insta-Grow Vaporbomb that does nothing (the Revival Potion, Revita-Seed and the Formula Bomb as "
        "the last stock chemical, doing nothing too), boxes 4-6 hidden with their seeds, "
        "and the extra flowers the formula grew drawn away from their plants. Plant or sell the "
        "seeds, use up the formula, the Revival Potion, Revita-Seed and the Formula Bomb, sell or compost the plants it was used on, and move seeds out "
        "of boxes 4-6 before switching it off."
    ),
    "category": "main",
    "default": False,
    "separate_output": True,
    "requires_settings": ["new_flowers"],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def companion_files() -> list[dict]:
    root = ROOT / SOURCE
    files = [{"path": name, "destination": f"{FOLDER}/{name}"} for name in DLL_NAMES]
    for image in sorted((root / "Images").glob("*.png")):
        files.append({"path": f"Images/{image.name}", "destination": f"Images/{image.name}"})
    for entry in files:
        path = root / entry["path"]
        entry["size"] = path.stat().st_size
        entry["sha256"] = sha256(path)
    return files


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "files": companion_files()}
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] not in (SETTING_ID, "seed_boxes")] + [setting]

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items()
            if not {SETTING_ID, "seed_boxes"} & set(k.split(","))}
    added = 0
    for key, value in list(pins.items()):
        enabled = set(key.split(","))
        if "new_flowers" in enabled:
            pins[",".join(sorted(enabled | {SETTING_ID}))] = value
            added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(setting['companion']['files'])} companion files and {added} executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
