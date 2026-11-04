"""Pin the "Zoom in when pruning" setting into the Plant Tycoon manifest.

    python -X utf8 scripts/pin_prune_zoom.py

Run after rebuilding "Prune Zoom.dll" (scripts/build_ftfp_prune_zoom.ps1). It records
assets/plant_tycoon_prune_zoom/Prune Zoom.dll by size and SHA-256, copied to "Plant Tycoon Fix Patcher
DLLs", as a loader tail ("loader_tail": src/ds_fish_loader.py, with_tails; src/fish_patcher.py,
build_executable): the startup loader loads it after every other companion, and the setting is left out of
the executable pins, so no combination needs a new pin.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCE = "assets/plant_tycoon_prune_zoom"
SETTING_ID = "prune_zoom"
DLL_NAME = "Prune Zoom.dll"
FOLDER = "Plant Tycoon Fix Patcher DLLs"

SETTING = {
    "id": SETTING_ID,
    "name": "Zoom in when pruning",
    "summary": "With the shears, click a plant to see it larger, with the part the shears would cut lit, as in "
               "the iOS version.",
    "description": (
        "In the greenhouse, while you hold the shears, a click on a plant opens a zoom instead of pruning: a light "
        "box over that part of the greenhouse with the pot and plant drawn larger in the middle, by the game's own "
        "drawing. The part the shears would cut is lit, and a click in the box cuts exactly that part of the real "
        "plant, so you never prune the wrong part by accident. The X in the box's corner closes it, as does a "
        "click outside the box (that click prunes nothing), putting the shears down or taking anything else. "
        "Without the shears nothing changes. Runs as a companion DLL the game loads at start, after the others; "
        "saves are unchanged."
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
