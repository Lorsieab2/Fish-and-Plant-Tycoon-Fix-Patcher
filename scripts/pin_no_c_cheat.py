"""Pin the "Disable Press C for Cash Cheat" setting into the fish manifest.

    python scripts/pin_no_c_cheat.py

Run after rebuilding "No C Cheat.dll" (scripts/build_ftfp_no_c_cheat.ps1). It records
assets/fish_tycoon_no_c_cheat/No C Cheat.dll by size and SHA-256 as a loader tail
("loader_tail": src/ds_fish_loader.py, with_tails): the startup loader loads it after the other
companions and the setting is left out of the executable pins, so no pin changes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "assets/fish_tycoon_no_c_cheat"
SETTING_ID = "disable_c_cheat"
DLL_NAME = "No C Cheat.dll"
FOLDER = "Fish Tycoon Fix Patcher DLLs"

SETTING = {
    "id": SETTING_ID,
    "name": "Disable Press C for Cash Cheat",
    "summary": "No fair cheating.",
    "description": (
        "No fair cheating. In the stock game, typing a lowercase c on the tank screen gives you $1000 per press. "
        "With this setting the hidden c key no longer adds the $1000. The other hidden keys (u and w) work as "
        "before, and the Add Money setting is separate. Runs as a companion DLL the game loads at start; saves "
        "are unchanged."
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
