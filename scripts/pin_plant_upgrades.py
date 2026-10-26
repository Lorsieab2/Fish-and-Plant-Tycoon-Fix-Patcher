"""Pin the Store Upgrades and Extra Seed Boxes settings into the plant manifest.

    python scripts/pin_plant_upgrades.py

Run after rebuilding "FTFP Plant Upgrades.dll" (scripts/build_ftfp_plant_upgrades.ps1),
"FTFP Seed Boxes.dll" (scripts/build_ftfp_seed_boxes.ps1) or the Upgrades art
(scripts/build_plant_upgrades_assets.py), and after scripts/pin_new_flowers.py.
It

  * records every companion file of both settings by size and SHA-256, with
    the game-relative destination it is copied to;
  * pins the output executable for every combination with either setting.
    Neither writes executable bytes (New Flowers' DLL loads the Upgrades DLL,
    which loads the Seed Boxes DLL), so each pin is the same combination's pin
    without them.

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
FOLDER = ds_fish_loader.PLANT.patcher_files_folder

SETTINGS = [
    ({
        "id": "plant_upgrades",
        "name": "Store Upgrades",
        "description": (
            "Adds an Upgrades link on the bricks at the left of the Supplies store. It opens a second "
            "view of the store with only the new items, each where it would sit in the store: "
            "Legendary Seeds on the seed shelves (three a day, $5000 each, any foliage with one of the "
            "New Flowers; the stock seed packets keep their stock flowers) and the Radioactive Plant "
            "Formula with the chemicals ($10,000, 3 doses: full bloom, as many flowers as the plant can "
            "hold, the largest size, no dead or brown leaves, and full health). Click Supplies in the "
            "bottom bar to go back. Needs New Flowers. See docs/plant-tycoon-upgrades-design.md."
        ),
        "warning": (
            "Turning this off leaves bought Legendary seeds drawn as another seed packet and the formula "
            "drawn as an Insta-Grow Vaporbomb that does nothing. Plant or sell them, and use up the "
            "formula, before switching it off."
        ),
        "category": "main",
        "default": False,
        "requires_settings": ["new_flowers"],
    }, "assets/plant_tycoon_upgrades", "FTFP Plant Upgrades.dll"),
    ({
        "id": "seed_boxes",
        "name": "Extra Seed Boxes",
        "description": (
            "Adds the Fourth, Fifth and Sixth Seed Box (\"Even more space for your seeds!\", $1000 each), "
            "sold in the store's Upgrades view where the stock seed boxes are, and bought in order like "
            "them. Each opens one more 40-seed drawer in a second chest on the Seed Storage screen; the "
            "gold arrows on its title bar switch between boxes 1-3 and 4-6. Seeds sent to the seed box "
            "from the greenhouse fill boxes 1-3 first, then 4-6. Each save slot keeps the second chest in "
            "a separate file beside the save. Needs Store Upgrades."
        ),
        "warning": (
            "Turning this off hides boxes 4-6 and the seeds in them. Move those seeds to boxes 1-3 "
            "before switching it off."
        ),
        "category": "main",
        "default": False,
        "requires_settings": ["plant_upgrades"],
    }, "assets/plant_tycoon_seed_boxes", "FTFP Seed Boxes.dll"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def companion_files(source: str, dll_name: str) -> list[dict]:
    root = ROOT / source
    files = [{"path": dll_name, "destination": f"{FOLDER}/{dll_name}"}]
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
    ids = [setting["id"] for setting, _, _ in SETTINGS]
    kept = [s for s in manifest["settings"] if s["id"] not in ids]
    for template, source, dll_name in SETTINGS:
        setting = dict(template)
        setting["companion"] = {"source": source, "files": companion_files(source, dll_name)}
        kept.append(setting)
    manifest["settings"] = kept

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if not set(ids) & set(k.split(","))}
    added = 0
    for key, value in list(pins.items()):
        enabled = set(key.split(","))
        if "new_flowers" in enabled:
            for extra in ({"plant_upgrades"}, {"plant_upgrades", "seed_boxes"}):
                pins[",".join(sorted(enabled | extra))] = value
                added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {sum(len(s['companion']['files']) for s in kept if s['id'] in ids)} companion files and "
          f"{added} executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
