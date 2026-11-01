"""Pin the DS Store Items setting into the fish manifest.

    python scripts/pin_ds_store.py

Run after rebuilding "DS Store Items.dll" (scripts/build_ftfp_ds_store.ps1) or
its art (scripts/build_ds_store_assets.py), and after scripts/pin_ds_fish.py.
It

  * records every companion file under assets/fish_tycoon_ds_store by size
    and SHA-256, with the game-relative destination it is copied to;
  * pins the output executable for every combination with DS Store Items.
    The setting writes no executable bytes (its DLL is loaded by DS Fish's),
    so each pin is the same combination's pin without it.

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

MANIFEST = ROOT / "data" / "fish_manifest.json"
SOURCE = "assets/fish_tycoon_ds_store"
SETTING_ID = "ds_store"
DLL_NAME = "DS Store Items.dll"

SETTING = {
    "id": SETTING_ID,
    "name": "DS Store Items",
    "summary": "Adds an Upgrades page to the Supplies store with the DS version's store items: the Magic Pufferfish, Blue-Spotted Stingray and Moray Eel (with its rock), tank animals that help your fish without taking a fish's place, Exotic Fish Eggs that hatch only DS fish, the Radioactive Growth Hormone, which gives every fish in the tank full health and no sickness, makes young ones adults and pregnant ones give birth, the Revival Potion, which revives dead fish, ClonaFish, which clones every fish in the tank, Muta-Fin and Muta-Body, which mutate only the fins or only the bodies of fish, and the Auto-Feeder and Auto-Healer, which keep every fish in every tank fed and healthy. Needs DS Exclusive Fish.",
    "description": (
        "Adds an Upgrades button to the Supplies store with the Nintendo DS version's store items. "
        "The Magic Pufferfish, Blue-Spotted Stingray and Moray Eel are tank companions like the Golden Seahorse: "
        "they swim in your tank, can be dragged between tanks, never age, breed or get sold, and "
        "magically enhance the life and environment of your fish (the exact effects are in the "
        "Tools tab's Game Mechanics). The Moray Eel comes with its rock, a decoration you can "
        "move: drop the eel on its rock to send it home, and drag it out by its head. Trashing "
        "the eel trashes its rock, and the other way round. The animals never take a fish's "
        "place: each tank has 5 animal places of its own, the Golden Seahorse's included, kept "
        "beside the save in \"Tank Animals <slot>.dat\" (a save from an earlier build has its animals "
        "moved there the first time it loads); with 3 extra tanks, the animals in Tanks 4-6 move with "
        "their tank and are kept with it in \"Extra Tanks <slot>.dat\". "
        "Exotic Fish Eggs ($2300) hatch only the DS-exclusive bodies and fins. The Radioactive "
        "Growth Hormone ($10,000, 3 doses) is a green Growth Hormone used the same way, on every "
        "live fish in the tank you use it on, any age: each pregnant one "
        "gives birth at once, as at the end of a pregnancy (the babies stay babies, as born), then each fish that was there before the births "
        "becomes an adult at once if younger, gets full health and is cured of any sickness. Treated fish "
        "sell for the highest possible price: when a fish the hormone healed is sold, from the Sale Tank or "
        "Tanks 4-6, you are paid its species' highest selling price (2B - 1, B its base price after both "
        "Advertising levels; the Breeding Guide's Highest selling with Max effects) instead of your asking "
        "price, while which fish sells and when still follow your asking price. The treated price is shown "
        "beside the price you set, for a treated fish only: \"Treated: $<price>\" in the Fish Store (the sold "
        "fish's panel) and on the Species Chart (where you set the price), nowhere else. The mark stays with the "
        "fish through moves, saves and ClonaFish clones, and ends when it is sold, dies or is thrown away. The "
        "Revival Potion ($10,000, 3 doses) revives every dead fish in the tank you use it on, at "
        "full health. ClonaFish ($2,500, 3 doses) adds an exact copy of every live fish in the "
        "tank you use it on, doubling it, until the tank is full. Muta-Fin ($2,500, 3 doses) and Muta-Body "
        "($2,500, 3 doses) are the stock Unknown Chemical for one part only: each dose reaches the same fish "
        "as the Unknown Chemical (every live fish in the tank you use it on, any age, not the Golden Seahorse "
        "or the store animals; never the isolation tank or another tank), changes each one on the same 26% "
        "chance, and steps its fin (Muta-Fin) or its body (Muta-Body) one gene up or down by the game's own "
        "step, leaving the other part as it was; with DS Exclusive Fish that step reaches the DS genes as the "
        "Unknown Chemical's does. A new species is discovered as usual, once the fish is an adult. "
        "The Auto-Feeder ($10,000) and the Auto-Healer ($10,000) are bought once and work "
        "on every live fish in every tank (Tanks 1-2, the Sale Tank, the isolation tank and Tanks 4-6, "
        "on screen or not, through time away and the Time Warp too): the Auto-Feeder keeps each fish's "
        "food full at 100, so it never starves, and while it is owned feeding by hand never costs health; the Auto-Healer "
        "cures fungus and ick (each cure counts under Fish Cured) and keeps health at 100. Neither "
        "touches a dead fish. Unpurchase: click an owned one again and answer Yes; it switches off at "
        "once, with no refund (buying it again costs the full price). Ownership is kept beside the save "
        "in \"Auto Upgrades <slot>.dat\"; a new game starts without them. The Golden "
        "Seahorse keeps its PC effects and gains its DS one. Every supply slot (the stock four, and the "
        "extra ones with Extra supply slots) shows a tooltip while the mouse is over it, in the game's own "
        "hint box: the item's name and what is left of it, as the game will spend it (doses, the Unknown "
        "Chemical's uses, egg batches; the fish food: its name only). Needs DS Exclusive Fish."
    ),
    "warning": (
        "Turning this off hides the store animals and the Golden Seahorse: they wait in "
        "\"Tank Animals <slot>.dat\" beside the save and come back when it is on again. The eel's "
        "rock stays in the tank as a sprite the game cannot draw; trash the eel (its rock goes "
        "with it) before switching it off if you mind."
    ),
    "category": "main",
    "default": False,
    "separate_output": True,
    "requires_settings": ["ds_fish"],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def companion_files() -> list[dict]:
    source = ROOT / SOURCE
    files = [{"path": DLL_NAME, "destination": f"{ds_fish_loader.PATCHER_FILES_FOLDER}/{DLL_NAME}"}]
    for image in sorted((source / "Images").glob("*.png")):
        files.append({"path": f"Images/{image.name}", "destination": f"Images/{image.name}"})
    for entry in files:
        path = source / entry["path"]
        entry["size"] = path.stat().st_size
        entry["sha256"] = sha256(path)
    return files


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "files": companion_files()}
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID] + [setting]

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    added = 0
    for key, value in list(pins.items()):
        enabled = set(key.split(","))
        if "ds_fish" in enabled:
            pins[",".join(sorted(enabled | {SETTING_ID}))] = value
            added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(setting['companion']['files'])} companion files and {added} DS Store executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
