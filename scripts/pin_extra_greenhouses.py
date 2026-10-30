"""Pin the "5 extra greenhouses" setting into the plant manifest.

    python scripts/pin_extra_greenhouses.py "<vanilla Plant Tycoon folder>"

Run after rebuilding "Extra Greenhouses.dll" (scripts/build_ftfp_extra_greenhouses.ps1),
and after scripts/pin_new_flowers.py, scripts/pin_plant_upgrades.py and
scripts/pin_sort_seeds.py. It

  * records the companion file under assets/plant_tycoon_greenhouses (the DLL)
    by size and SHA-256, with its game-relative destination;
  * pins the output executable for every combination with the setting: the
    startup loader then loads "Extra Greenhouses.dll" (src/ds_fish_loader.py,
    PLANT_GREENHOUSES), which starts the other companions itself.

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
SOURCE = "assets/plant_tycoon_greenhouses"
SETTING_ID = "extra_greenhouses"
DLL_NAME = "Extra Greenhouses.dll"
FOLDER = ds_fish_loader.PLANT.patcher_files_folder

SETTING = {
    "id": SETTING_ID,
    "name": "5 extra greenhouses",
    "summary": "Adds five more greenhouses of 15 pots (90 pots in all): gold arrows on the greenhouse screen page "
               "through Greenhouse 1 to 6, and every pot works exactly like the stock ones.",
    "description": (
        "Gold arrows (the game's own, as on the Seed Storage screen) on the greenhouse screen page through "
        "Greenhouse 1, the stock one, to Greenhouse 6 and round again; the screen says \"Greenhouse 2 of 6\". "
        "Each greenhouse is the stock greenhouse screen, and the game's own code runs on its 15 pots: plants "
        "grow, age, need water and care, flower, take pollen, give seeds, get pests and die exactly as in "
        "Greenhouse 1, also while you look at another greenhouse or another screen, while you are away "
        "(caught up when you come back) and through the Time Warp. Every chemical, tool, upgrade and magic "
        "plant works in every greenhouse. Drop a plant on an arrow to move it to the first empty pot of the "
        "greenhouse that arrow leads to; pollen you take can be carried to another greenhouse. The nursery "
        "shows the plants for sale from every greenhouse in its 15 spots, and the game's limit holds: at most "
        "15 plants are for sale at once, counting every greenhouse. Greenhouses 2-6 are kept beside each save "
        "in \"Plant Tycoon Fix Patcher Data\\Extra Greenhouses <slot>.dat\"; the save itself keeps the stock "
        "layout. Runs as a companion DLL the game loads at start."
    ),
    "warning": (
        "Greenhouses 2-6 only exist while this setting is on. Before switching it off, empty them: move every "
        "plant to Greenhouse 1, or sell or compost it. Their plants stay in the slot's Extra Greenhouses file "
        "and come back if you switch the setting on again."
    ),
    "category": "main",
    "default": False,
    "separate_output": True,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def companion_files() -> list[dict]:
    data = (ROOT / SOURCE / DLL_NAME).read_bytes()
    return [{"path": DLL_NAME, "destination": f"{FOLDER}/{DLL_NAME}", "size": len(data), "sha256": sha256(data)}]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / "Plant Tycoon.exe").read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "startup_loader": True, "files": companion_files()}
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID] + [setting]

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    added = 0
    for key in [""] + list(pins):
        enabled = {s for s in key.split(",") if s} | {SETTING_ID}
        patched, _ = plant_patcher.apply_patch_bytes(vanilla, plant_patcher.active_patch_records(manifest, enabled))
        patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled))
        pins[plant_patcher.settings_key(enabled, manifest)] = sha256(patched)
        added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(setting['companion']['files'])} companion file and {added} Extra Greenhouses executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
