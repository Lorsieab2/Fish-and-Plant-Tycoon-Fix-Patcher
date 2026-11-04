"""Pin the "Snail and Plant of Curing stack" setting into the fish manifest.

    python scripts/pin_snail_curing.py

Run after rebuilding "Snail and Curing.dll" (scripts/build_ftfp_snail_curing.ps1). It records
assets/fish_tycoon_snail_curing/Snail and Curing.dll by size and SHA-256 as a loader tail
("loader_tail": src/ds_fish_loader.py, with_tails): the startup loader loads it after the other
companions and the setting is left out of the executable pins, so no pin changes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "assets/fish_tycoon_snail_curing"
SETTING_ID = "snail_curing_stack"
DLL_NAME = "Snail and Curing.dll"
FOLDER = "Fish Tycoon Fix Patcher DLLs"

SETTING = {
    "id": SETTING_ID,
    "name": "Snail and Plant of Curing stack",
    "summary": "The Cleaning Snail and the Plant of Curing both cut the odds of a fish getting sick, and together they quarter them about half the time.",
    "description": (
        "In the stock game the Cleaning Snail's 50% halving of a fish's sickness odds does nothing once you own "
        "the Plant of Curing, which halves them on its own. With this setting the snail's halving also works when "
        "you own the plant: the plant halves the odds, then half the time the snail halves them again, so owning "
        "both quarters the odds about half the time. With only one of them, or neither, nothing changes. The "
        "halving is applied before the extra odds for other sick fish and for age, which are never halved. This "
        "is not counted as a bug, so it is not part of Fix Vanilla Bugs. Runs as a companion DLL the game loads "
        "at start; saves are unchanged."
    ),
    "category": "main",
    "default": True,
    "separate_output": True,
}


def main() -> int:
    path = ROOT / "data" / "fish_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    data = (ROOT / SOURCE / DLL_NAME).read_bytes()
    entry = dict(SETTING)
    entry["companion"] = {"source": SOURCE, "loader_tail": DLL_NAME, "files": [
        {"path": DLL_NAME, "destination": f"{FOLDER}/{DLL_NAME}", "size": len(data),
         "sha256": hashlib.sha256(data).hexdigest().upper()}]}
    ids = [s["id"] for s in manifest["settings"]]
    if SETTING_ID in ids:
        manifest["settings"][ids.index(SETTING_ID)] = entry
    else:
        manifest["settings"].append(entry)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"pinned {DLL_NAME} (a loader tail; no executable pins change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
