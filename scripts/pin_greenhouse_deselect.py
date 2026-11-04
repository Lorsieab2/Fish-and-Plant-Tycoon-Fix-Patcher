"""Pin the "Click the greenhouse to deselect" setting into the Plant Tycoon manifest.

    python -X utf8 scripts/pin_greenhouse_deselect.py

Run after rebuilding "Click to Deselect.dll" (scripts/build_ftfp_greenhouse_deselect.ps1). It records
assets/plant_tycoon_deselect/Click to Deselect.dll by size and SHA-256, copied to "Plant Tycoon Fix
Patcher DLLs", as a loader tail ("loader_tail": src/ds_fish_loader.py, with_tails; src/fish_patcher.py,
build_executable): the startup loader loads it after every other companion, and the setting is left out of
the executable pins (the executable without it must match its pin, then the loader gets the DLL added),
so no combination needs a new pin.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCE = "assets/plant_tycoon_deselect"
SETTING_ID = "greenhouse_click_deselect"
DLL_NAME = "Click to Deselect.dll"
FOLDER = "Plant Tycoon Fix Patcher DLLs"

SETTING = {
    "id": SETTING_ID,
    "name": "Click the greenhouse to deselect",
    "summary": "Click the greenhouse's empty background to go from a selected plant back to \"No plant "
               "selected\".",
    "description": (
        "In the greenhouse, a click on the empty background (the floor and the walls: not a plant or a pot, "
        "the left panel, the tools and chemicals, the tap and hose, the buttons, the counts button or the "
        "extra greenhouses' arrows) clears the selected plant, exactly as if nothing had been picked: the "
        "left panel shows \"No plant selected\" again. Nothing happens while you hold a tool, a seed, pollen "
        "or a pot, and every click that already did something does the same as before. Runs as a companion "
        "DLL the game loads at start, after the others; saves are unchanged."
    ),
    "category": "main",
    "default": True,
    "separate_output": True,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def companion() -> dict:
    data = (ROOT / SOURCE / DLL_NAME).read_bytes()
    files = [{"path": DLL_NAME, "destination": f"{FOLDER}/{DLL_NAME}", "size": len(data), "sha256": sha256(data)}]
    return {"source": SOURCE, "loader_tail": DLL_NAME, "files": files}


def main() -> int:
    path = ROOT / "data" / "plant_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entry = dict(SETTING)
    entry["companion"] = companion()
    ids = [s["id"] for s in manifest["settings"]]
    if SETTING_ID in ids:
        manifest["settings"][ids.index(SETTING_ID)] = entry
    else:
        manifest["settings"].append(entry)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"plant: pinned {DLL_NAME} (a loader tail; no executable pins change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
