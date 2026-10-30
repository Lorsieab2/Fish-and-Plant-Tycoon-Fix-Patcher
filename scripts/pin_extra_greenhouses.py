"""Pin the "5 extra greenhouses" and "5 extra nurseries" settings into the plant manifest.

    python scripts/pin_extra_greenhouses.py "<vanilla Plant Tycoon folder>"

Run after rebuilding "Extra Greenhouses.dll" (scripts/build_ftfp_extra_greenhouses.ps1),
and after scripts/pin_new_flowers.py, scripts/pin_plant_upgrades.py and
scripts/pin_sort_seeds.py. It

  * records each setting's companion files under assets/plant_tycoon_greenhouses
    by size and SHA-256, with their game-relative destinations: both ship
    "Extra Greenhouses.dll"; each ships its own .ini, which turns its part of
    the DLL on;
  * pins the output executable for every combination with either setting: the
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
import experimental  # noqa: E402
import plant_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "plant_manifest.json"
SOURCE = "assets/plant_tycoon_greenhouses"
DLL_NAME = "Extra Greenhouses.dll"
FOLDER = ds_fish_loader.PLANT.patcher_files_folder
EXPERIMENTAL = "EXPERIMENTAL - USE AT OWN RISK."

GREENHOUSES = {
    "id": "extra_greenhouses",
    "name": "5 extra greenhouses",
    "summary": f"{EXPERIMENTAL} Five more greenhouses of 15 pots (90 pots in all), bought one by one on the "
               "store's Upgrades screen for $10,000 each; gold arrows on the greenhouse screen page through the "
               "ones you own, and every pot works exactly like the stock ones. Needs Add new store upgrades and "
               "items.",
    "description": (
        f"{EXPERIMENTAL} "
        "An Extra Greenhouse item on the store's Upgrades screen (tool shelf, beside the Fourth to Sixth Seed "
        "Box) sells Greenhouses 2-6 in order, $10,000 each ($0 with Free upgrades), with a tick once all five "
        "are yours. Once you own one, gold arrows (the game's own, as on the Seed Storage screen) on the "
        "greenhouse screen page through Greenhouse 1, the stock one, and the ones you own, and the screen says "
        "\"Greenhouse 2 of 3\". "
        "Each greenhouse is the stock greenhouse screen, and the game's own code runs on its 15 pots: plants "
        "grow, age, need water and care, flower, take pollen, give seeds, get pests and die exactly as in "
        "Greenhouse 1, also while you look at another greenhouse or another screen, while you are away "
        "(caught up when you come back) and through the Time Warp. Every chemical, tool, upgrade and magic "
        "plant works in every greenhouse. Drag a plant onto an arrow to move it to the same pot place in the "
        "greenhouse that arrow leads to (or its first empty pot if that place is taken); pollen and seeds you "
        "take from a plant are carried along, and tools, chemicals and tray seeds stay in your hand. Plants "
        "tagged for sale in any greenhouse go to the nursery; without 5 extra nurseries the game's limit holds: "
        "at most 15 plants are for sale at once, counting every greenhouse. Greenhouses 2-6 are kept beside "
        "each save in \"Plant Tycoon Fix Patcher Data\\Extra Greenhouses <slot>.dat\"; the save itself keeps "
        "the stock layout. Runs as a companion DLL the game loads at start."
    ),
    "warning": (
        "Greenhouses 2-6 only exist while this setting is on. Before switching it off, empty them: move every "
        "plant to Greenhouse 1, or sell or compost it. Their plants stay in the slot's Extra Greenhouses file "
        "and come back if you switch the setting on again."
    ),
    "category": "main",
    "default": False,
    "separate_output": True,
    "requires_settings": ["plant_upgrades"],
    "ini": "Extra Greenhouses.ini",
}

NURSERIES = {
    "id": "extra_nurseries",
    "name": "5 extra nurseries",
    "summary": f"{EXPERIMENTAL} Five more nurseries of 15 spots, bought one by one on the store's Upgrades "
               "screen for $10,000 each: each one raises how many plants can be for sale at once by 15 (90 with "
               "all five). Gold arrows on the nursery screen page through the ones you own. Needs Add new store "
               "upgrades and items.",
    "description": (
        f"{EXPERIMENTAL} "
        "An Extra Nursery item on the store's Upgrades screen (the Nursery shelf, beside Add Money) sells "
        "Nurseries 2-6 in order, $10,000 each ($0 with Free upgrades), with a tick once all five are yours. "
        "Without any, the game's own limit holds: at most 15 plants are for sale at once. Each one bought adds "
        "15 more (30, 45, ... 90). Each nursery is the stock nursery screen with its own 15 spots, its own "
        "visitors, prices and sales, run by the game's own code; gold arrows (the game's own, as on the Seed "
        "Storage screen) on the nursery screen page through Nursery 1, the stock one, and the ones you own, and "
        "the screen says \"Nursery 2 of 3\". Plants are tagged for sale in the greenhouse as in the stock game "
        "and fill the nurseries in order: Nursery 1 first (a Greenhouse 1 plant at its own pot's spot, as in "
        "the stock game), then Nursery 2, and so on. While you are in the nursery, all of them sell at once "
        "through the game's own buy roll; away from it nothing sells, as in the stock game. Kept beside each save with the extra greenhouses in \"Plant Tycoon Fix Patcher "
        "Data\\Extra Greenhouses <slot>.dat\". Runs as a companion DLL the game loads at start."
    ),
    "warning": (
        "Before switching it off, take plants off sale until 15 or fewer are for sale; the nurseries you "
        "bought stay in the slot's Extra Greenhouses file and come back if you switch the setting on again."
    ),
    "category": "main",
    "default": False,
    "separate_output": True,
    "requires_settings": ["plant_upgrades"],
    "ini": "Extra Nurseries.ini",
}

GREENHOUSES = experimental.mark(GREENHOUSES)
NURSERIES = experimental.mark(NURSERIES)
SETTINGS = (GREENHOUSES, NURSERIES)
IDS = {s["id"] for s in SETTINGS}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def companion_files(ini: str) -> list[dict]:
    files = []
    for name in (DLL_NAME, ini):
        data = (ROOT / SOURCE / name).read_bytes()
        files.append({"path": name, "destination": f"{FOLDER}/{name}", "size": len(data), "sha256": sha256(data)})
    return files


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / "Plant Tycoon.exe").read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    settings = [s for s in manifest["settings"] if s["id"] not in IDS]
    for spec in SETTINGS:
        setting = {k: v for k, v in spec.items() if k != "ini"}
        setting["companion"] = {"source": SOURCE, "startup_loader": True, "files": companion_files(spec["ini"])}
        settings.append(setting)
    manifest["settings"] = settings

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if not IDS & set(k.split(","))}
    added = 0
    for key in [""] + list(pins):
        base = {s for s in key.split(",") if s}
        for extra in ({"extra_greenhouses"}, {"extra_nurseries"}, IDS):
            enabled = base | extra
            patched, _ = plant_patcher.apply_patch_bytes(vanilla, plant_patcher.active_patch_records(manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled))
            pins[plant_patcher.settings_key(enabled, manifest)] = sha256(patched)
            added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned 2 settings and {added} Extra Greenhouses / Nurseries executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
