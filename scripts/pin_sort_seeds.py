"""Pin the "Sort Seeds button" setting into the plant manifest.

    python scripts/pin_sort_seeds.py "<vanilla Plant Tycoon folder>"

Run after rebuilding "Sort Seeds.dll" (scripts/build_ftfp_sort_seeds.ps1) or
its button (scripts/build_sort_seeds_assets.py), and after
scripts/pin_new_flowers.py and scripts/pin_plant_upgrades.py. It

  * records the companion files under assets/plant_tycoon_sort_seeds (the DLL
    and the button) by size and SHA-256, with their game-relative
    destinations;
  * pins the output executable for every combination with the setting. With
    the new flowers on, "Unused Flowers.dll" loads this DLL, so the pin is the
    same combination's pin without it; otherwise the startup loader loads
    "Sort Seeds.dll" itself (src/ds_fish_loader.py, PLANT_SORT).

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
import plant_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "plant_manifest.json"
SOURCE = "assets/plant_tycoon_sort_seeds"
SETTING_ID = "sort_seeds"
DLL_NAME = "Sort Seeds.dll"
FOLDER = ds_fish_loader.PLANT.patcher_files_folder

SETTING = {
    "id": SETTING_ID,
    "name": "Sort Seeds button",
    "summary": "Adds a Sort Seeds button to the Seed Storage screen: sorts every seed by the plant it grows, then its parents, into the unlocked seed boxes in order.",
    "description": (
        "Adds a \"Sort Seeds\" button on the Seed Storage screen's title bar. One click sorts every "
        "seed in your unlocked seed box space and packs them from the first slot, left to right and "
        "top to bottom: the First Seed Box's drawer fills first, then the Second's and the Third's "
        "if you bought them, then the Fourth, Fifth and Sixth, then the Seventh, Eighth and Ninth "
        "with Add new store upgrades and items. "
        "Locked drawers stay empty. Order, lowest first: the class of the plant the seed grows "
        "(the game's own A, B, C, D rarity), then its foliage, then its flower, then the parents "
        "(the seed's own plant, then the pollen donor; unknown \"?\" parents first). Seeds that tie "
        "keep their order. The sort checks that exactly the same seeds come out as went in before "
        "it writes anything, never touches the seed tray, and does nothing while you hold a seed. "
        "Runs as a companion DLL the game loads at start; saves are unchanged."
    ),
    "category": "main",
    "default": True,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def companion_files() -> list[dict]:
    root = ROOT / SOURCE
    files = [{"path": DLL_NAME, "destination": f"{FOLDER}/{DLL_NAME}"}]
    for image in sorted((root / "Images").glob("*.png")):
        files.append({"path": f"Images/{image.name}", "destination": f"Images/{image.name}"})
    for entry in files:
        data = (root / entry["path"]).read_bytes()
        entry["size"] = len(data)
        entry["sha256"] = sha256(data)
    return files


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / "Plant Tycoon.exe").read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "startup_loader": True, "files": companion_files()}
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID] + [setting]

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    keys = [""] + list(pins)
    added = 0
    for key in keys:
        enabled = {s for s in key.split(",") if s} | {SETTING_ID}
        if "new_flowers" in enabled:
            value = pins[key]
        else:
            patched, _ = plant_patcher.apply_patch_bytes(vanilla, plant_patcher.active_patch_records(manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled))
            value = sha256(patched)
        pins[plant_patcher.settings_key(enabled, manifest)] = value
        added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(setting['companion']['files'])} companion files and {added} Sort Seeds executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
