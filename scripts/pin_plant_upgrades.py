"""Pin the "Add new store upgrades and items" setting into the plant manifest.

    python scripts/pin_plant_upgrades.py

Run after rebuilding "FTFP Plant Upgrades.dll" (scripts/build_ftfp_plant_upgrades.ps1),
"FTFP Seed Boxes.dll" (scripts/build_ftfp_seed_boxes.ps1) or the Upgrades art
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
DLL_NAMES = ("FTFP Plant Upgrades.dll", "FTFP Seed Boxes.dll")
FOLDER = ds_fish_loader.PLANT.patcher_files_folder

SETTING = {
    "id": SETTING_ID,
    "name": "Add new store upgrades and items",
    "summary": "Adds an Upgrades view to the Supplies store with Legendary Seeds (the new flowers), the Radioactive Plant Formula, and the Fourth, Fifth and Sixth Seed Box. Needs Add unused flowers.",
    "description": (
        "Adds an Upgrades link on the bricks at the left of the Supplies store. It opens a second "
        "view of the store with only the new items, each where it would sit in the store: "
        "Legendary Seeds on the seed shelves (three a day, $5000 each, any foliage with one of the "
        "unused flowers; the stock seed packets keep their stock flowers), the Radioactive Plant "
        "Formula with the chemicals ($10,000, 3 doses, far beyond spamming Fertilizer Bombs and Plant "
        "Food: every branch grows, the largest size, full bloom, a flower on every spot of every "
        "branch and leaf, no dead or brown leaves, full health, and 5 seeds when pollinated), and the Fourth, Fifth "
        "and Sixth Seed Box with the tool upgrades (\"Even more space for your seeds!\", $1000 each, "
        "bought in order like the stock boxes). Each new box opens a 40-seed drawer in a second "
        "chest on the Seed Storage screen; the gold arrows on its title bar switch between boxes "
        "1-3 and 4-6, and the greenhouse fills boxes 4-6 once 1-3 are full. Click Supplies in the "
        "bottom bar to leave the Upgrades view. Needs Add unused flowers. Each save slot keeps the "
        "new data in separate files beside the save. See docs/plant-tycoon-upgrades-design.md."
    ),
    "warning": (
        "Turning this off leaves bought Legendary seeds drawn as another seed packet, the formula "
        "drawn as an Insta-Grow Vaporbomb that does nothing, and boxes 4-6 hidden with their seeds. "
        "Plant or sell the seeds, use up the formula and move seeds out of boxes 4-6 before "
        "switching it off."
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
