"""Pin the "Extra chemical slots" setting into the plant manifest.

    python scripts/pin_chem_slots.py "<vanilla Plant Tycoon folder>"

Run after rebuilding "Extra Chemical Slots.dll" (scripts/build_ftfp_chem_slots.ps1),
and after scripts/pin_extra_greenhouses.py; then run scripts/pin_time_warp.py and
scripts/pin_store_extras.py (which also re-record the rebuilt "Store Upgrades and
Items.dll" and its art in place). It

  * records the setting's companion file under assets/plant_tycoon_chem_slots by
    size and SHA-256, with its game-relative destination;
  * pins the output executable for every combination with the setting: the
    startup loader then loads "Extra Chemical Slots.dll" after every other
    companion (src/ds_fish_loader.py, PLANT_CHEM_SLOTS).

The other combinations' pins are left exactly as they are. The setting keeps its
place in the settings list when it is already there, else it goes last (after
the extra nurseries); scripts/pin_time_warp.py and scripts/pin_store_extras.py
move their own settings to the end, so put those back where they were after
running them (tests/test_chem_slots.py checks the order).
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
SOURCE = "assets/plant_tycoon_chem_slots"
DLL_NAME = "Extra Chemical Slots.dll"
FOLDER = ds_fish_loader.PLANT.patcher_files_folder
SETTING_ID = ds_fish_loader.CHEM_SLOTS_SETTING

SETTING = experimental.mark({
    "id": SETTING_ID,
    "name": "Extra chemical slots",
    "summary": "A second page of 8 chemical slots in the greenhouse's Tools box (12 in all), bought once on the "
               "store's Upgrades screen for $10,000; a small gold arrow turns the page. Needs Add new store "
               "upgrades and items.",
    "description": (
        "An Extra Chemical Slots item on the store's Upgrades screen (the chemicals shelf, under the Radioactive "
        "Plant Formula Bomb) costs $10,000 ($0 with Free upgrades) and is bought once, with a tick afterwards. "
        "Once it is yours, a small gold arrow on the plaque of the greenhouse's Tools box turns to page 2: 8 more "
        "chemical slots in both rows of the box (the tools stay on page 1; a tool already in your hand stays "
        "there). Click the arrow, or carry a chemical over it, to turn the page. Every slot works like the "
        "game's own: the store fills a chemical onto its own bottle on either page, else the first free slot of "
        "page 1, then of page 2, and says the tray is full only when all 12 are; every chemical (the game's and "
        "the Upgrades screen's) is used from page 2 with its doses; the tooltips show its name and doses; the "
        "Upgrades screen's chemicals go in the trash from page 2 too. A chemical you hold can be put on any "
        "other slot of either page: into an empty slot, onto the same chemical (the doses add up) or swapping "
        "places. The tray is shared by every greenhouse. Page 2 and the purchase are kept beside each save in "
        "\"Plant Tycoon Fix Patcher Data\\Extra Chemical Slots <slot>.dat\"; the save itself keeps the stock "
        "layout. Runs as a companion DLL the game loads at start."
    ),
    "warning": (
        "Turning it off hides page 2. Its chemicals are not lost: while Add new store upgrades and items stays "
        "on, loading the save puts them in the 4 stock slots (onto the same chemical, else a free slot) as far "
        "as there is room, and the rest stay in the slot's Extra Chemical Slots file, with the purchase, and "
        "come back on page 2 when you switch the setting on again."
    ),
    "category": "main",
    "default": True,
    "separate_output": True,
    "requires_settings": ["plant_upgrades"],
})


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
    old = [s["id"] for s in manifest["settings"]]
    settings = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    at = old.index(SETTING_ID) if SETTING_ID in old else len(settings)
    settings.insert(at, setting)
    manifest["settings"] = settings

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    added = 0
    for key in list(pins):
        base = {s for s in key.split(",") if s}
        if "plant_upgrades" not in base:
            continue
        enabled = base | {SETTING_ID}
        patched, _ = plant_patcher.apply_patch_bytes(vanilla, plant_patcher.active_patch_records(manifest, enabled))
        patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled))
        pins[plant_patcher.settings_key(enabled, manifest)] = sha256(patched)
        added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned the setting and {added} Extra Chemical Slots executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
