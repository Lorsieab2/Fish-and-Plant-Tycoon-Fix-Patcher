"""Pin the "Extra supply slots" setting into the fish manifest.

    python -X utf8 scripts/pin_supply_slots.py "<vanilla Fish Tycoon folder>" [--files-only]

Run after rebuilding "Extra Supply Slots.dll" (scripts/build_ftfp_supply_slots.ps1) or
its art (scripts/build_supply_slots_assets.py), and again after any other script that adds
or re-pins combinations (it re-pins every combination with the setting from the ones
without it); then scripts/pin_time_warp.py and scripts/pin_store_extras.py. It

  * records every companion file under assets/fish_tycoon_supply_slots by size and
    SHA-256, with the game-relative destination it is copied to;
  * pins the output executable for every combination with the setting (each has DS Store
    Items, which the setting needs: it is sold on its Upgrades screen). Its startup loader
    loads "Extra Supply Slots.dll" (src/ds_fish_loader.py, FISH_SUPPLY_SLOTS), so every
    combination with it has its own pin.

--files-only re-records the companion files and leaves every pin as it is (the DLL and its
art are not part of the executable).

Combinations without the setting are left exactly as they are: with it off the patcher
writes the same bytes as before.
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
import fish_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "fish_manifest.json"
SOURCE = "assets/fish_tycoon_supply_slots"
SETTING_ID = ds_fish_loader.SUPPLY_SLOTS_SETTING
DLL_NAME = ds_fish_loader.FISH_SUPPLY_SLOTS.dll_name
AFTER = "extra_tanks"                      # its place in the list: right after "3 extra tanks"

SETTING = {
    "id": SETTING_ID,
    "name": "Extra supply slots",
    "summary": "Seven more supply slots (11 in all) in three pages beside the tank screen's slots, bought "
               "on the store's Upgrades screen for $10,000. Needs DS Store Items.",
    "description": (
        "Adds seven supply slots to the four at the top left of the tank screen: page 1 is the stock four "
        "(the fish food and slots 2-4), page 2 four more and page 3 three more. Two small arrows right of "
        "slot 4 turn the page; carry an item over an arrow to turn it while you hold it, so it can be "
        "dropped on any slot. Buy them on the Supplies store's Upgrades screen (Extra Supply Slots, "
        "$10,000, $0 with Free upgrades): one purchase opens all seven; until then the arrows are grey and "
        "say \"You don't own the extra supply slots yet!\". Every extra slot works exactly like slots 2-4: "
        "the store fills the first free slot over all three pages (with Universal supply slots, a stack of "
        "the same item first), and every medicine, chemical and egg -- the stock ones and DS Store Items' "
        "Radioactive Growth Hormone, Revival Potion, ClonaFish, Muta-Fin, Muta-Body and Exotic Fish Eggs -- is used "
        "from it on "
        "the tank by the game's own code, with the same doses, stacking and trash as in slots 2-4. Drag a "
        "supply onto another slot, on any page, to move it there: onto an empty slot it moves, onto the same "
        "item it stacks (with Universal supply slots), onto another item the two change places. Without "
        "Universal supply slots, slots 2-4 keep their own kind (medicine, chemicals, eggs) and each extra "
        "slot holds any one item. The fish food stays in slot 1. Runs as a companion DLL the game loads at "
        "start; the save files keep their stock layout, and each save slot keeps its extra slots and the "
        "purchase in \"Fish Tycoon Fix Patcher Data\\Extra Supply Slots <slot>.dat\" beside the saves. A new "
        "game empties them. Needs DS Store Items, which it turns on (the Upgrades screen they are sold on)."
    ),
    "warning": (
        "Use or move what is in the extra supply slots (pages 2 and 3) before turning this off: without it "
        "the game cannot reach them. Nothing is deleted -- they stay in \"Extra Supply Slots <slot>.dat\" "
        "and come back, with the purchase, when you turn it on again -- but until then they are out of the "
        "game."
    ),
    "category": "main",
    "default": True,
    "separate_output": True,
    "requires_settings": ["ds_store"],
}
SETTING = experimental.mark(SETTING)       # src/experimental.py: the owner's label


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def companion_files() -> list[dict]:
    source = ROOT / SOURCE
    files = [{"path": DLL_NAME, "destination": f"{ds_fish_loader.PATCHER_FILES_FOLDER}/{DLL_NAME}"}]
    for image in sorted((source / "Images").glob("*.png")):
        files.append({"path": f"Images/{image.name}", "destination": f"Images/{image.name}"})
    for entry in files:
        data = (source / entry["path"]).read_bytes()
        entry["size"] = len(data)
        entry["sha256"] = sha256(data)
    return files


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--files-only"]
    files_only = len(args) != len(sys.argv) - 1
    if len(args) != 1:
        raise SystemExit(__doc__)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "startup_loader": True, "files": companion_files()}
    ids = [s["id"] for s in manifest["settings"]]
    if SETTING_ID in ids:
        manifest["settings"][ids.index(SETTING_ID)] = setting
    elif AFTER in ids:
        manifest["settings"].insert(ids.index(AFTER) + 1, setting)
    else:
        manifest["settings"].append(setting)
    added = 0
    if not files_only:
        vanilla = (Path(args[0]) / "Fish Tycoon.exe").read_bytes()
        pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
        for key in list(pins):
            if "ds_store" not in key.split(","):
                continue                                   # it needs DS Store Items (its Upgrades screen)
            enabled = set(key.split(",")) | {SETTING_ID}
            patched, _ = fish_patcher.apply_patch_bytes(vanilla, fish_patcher.active_patch_records(manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.fish_profile(enabled))
            pins[fish_patcher.settings_key(enabled)] = sha256(patched)
            added += 1
        manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(),
                                                             key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(setting['companion']['files'])} companion files and {added} executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
