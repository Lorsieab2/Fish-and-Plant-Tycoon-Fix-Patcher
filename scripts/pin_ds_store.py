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
    "summary": "Adds an Upgrades page to the Supplies store with the DS version's store items: the Magic Pufferfish, Blue-Spotted Stingray and Moray Eel (with its rock), tank animals that help your fish without taking a fish's place, Exotic Fish Eggs that hatch only DS fish, and the Radioactive Growth Hormone, which makes young fish adults with full health and no sickness. Needs DS Exclusive Fish.",
    "description": (
        "Adds an Upgrades button to the Supplies store with the Nintendo DS version's store items. "
        "The Magic Pufferfish, Blue-Spotted Stingray and Moray Eel are tank companions like the Golden Seahorse: "
        "they swim in your tank, can be dragged between tanks, never age, breed or get sold, and "
        "magically enhance the life and environment of your fish (the exact effects are in the "
        "Tools tab's Game Mechanics). The Moray Eel comes with its rock, a decoration you can "
        "move: drop the eel on its rock to send it home, and drag it out by its head. Trashing "
        "the eel trashes its rock, and the other way round. The animals never take a fish's "
        "place: each tank has 5 animal slots of its own, the Golden Seahorse's included. "
        "Exotic Fish Eggs ($2300) hatch only the DS-exclusive bodies and fins. The Radioactive "
        "Growth Hormone ($10,000, 3 doses) is a green Growth Hormone used the same way and on the "
        "same fish (each live fish aged 40 or less in the tank you use it on): each becomes an "
        "adult at once if younger, gets full health and is cured of any sickness. The Golden "
        "Seahorse keeps its PC effects and gains its DS one. Needs DS Exclusive Fish."
    ),
    "warning": (
        "Turning this off after buying a store animal leaves it in your tank drawn as a Golden "
        "Seahorse, and the eel's rock as a sprite the game cannot draw. Move the animals to the "
        "trash and the eel out of its rock before switching it off."
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
