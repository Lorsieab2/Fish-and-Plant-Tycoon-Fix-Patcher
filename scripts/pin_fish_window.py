"""Pin the "Maximizable window" setting into the fish manifest.

    python scripts/pin_fish_window.py "<vanilla Fish Tycoon folder>"

Run after rebuilding "Maximizable Window.dll" (scripts/build_ftfp_fish_window.ps1)
or "DS Exclusive Fish.dll" (scripts/build_ftfp_ds_fish.ps1, which loads it). It

  * records the companion DLL under assets/fish_tycoon_window by size and
    SHA-256, with its game-relative destination, and re-records
    "DS Exclusive Fish.dll" the same way;
  * pins the output executable for every combination with the setting. With
    DS Exclusive Fish on, "DS Exclusive Fish.dll" loads this DLL, so the pin is
    the same combination's pin without it; otherwise the startup loader loads
    "Maximizable Window.dll" itself (src/ds_fish_loader.py, FISH_WINDOW).

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
import fish_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "fish_manifest.json"
SOURCE = "assets/fish_tycoon_window"
SETTING_ID = "maximizable_window"
DLL_NAME = ds_fish_loader.FISH_WINDOW.dll_name
FOLDER = ds_fish_loader.FISH_WINDOW.patcher_files_folder
INSERT_AFTER = "bigger_tanks"

SETTING = {
    "id": SETTING_ID,
    "name": "Maximizable window",
    "summary": "In windowed mode the game's window can be maximized or resized; the picture scales to fit, keeping its shape.",
    "description": (
        "Turns on the Maximize button on Fish Tycoon's window in windowed mode, and lets you drag its edges "
        "to resize it. At any size other than the game's own, the picture is scaled to fill the window with "
        "its shape kept (black bars where it does not fit) and smoothed, and the mouse lands where you "
        "point. Restore the window and it is the normal size again, drawn exactly as before. Fullscreen "
        "is unchanged. Runs as a companion DLL the game loads at start; saves are unchanged."
    ),
    "category": "main",
    "default": True,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def record(source: str, path: str, destination: str) -> dict:
    data = (ROOT / source / path).read_bytes()
    return {"path": path, "destination": destination, "size": len(data), "sha256": sha256(data)}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / "Fish Tycoon.exe").read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "startup_loader": True,
                            "files": [record(SOURCE, DLL_NAME, f"{FOLDER}/{DLL_NAME}")]}
    settings = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    at = next(i for i, s in enumerate(settings) if s["id"] == INSERT_AFTER) + 1
    manifest["settings"] = settings[:at] + [setting] + settings[at:]

    ds_fish = next(s for s in manifest["settings"] if s["id"] == "ds_fish")
    for entry in ds_fish["companion"]["files"]:
        if entry["path"] == ds_fish_loader.DLL_NAME:
            entry.update(record(ds_fish["companion"]["source"], entry["path"], entry["destination"]))

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    keys = [""] + list(pins)
    added = 0
    for key in keys:
        enabled = {s for s in key.split(",") if s} | {SETTING_ID}
        if "ds_fish" in enabled:
            value = pins[key]
        else:
            patched, _ = fish_patcher.apply_patch_bytes(vanilla, fish_patcher.active_patch_records(manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.fish_profile(enabled))
            value = sha256(patched)
        pins[fish_patcher.settings_key(enabled)] = value
        added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned the Maximizable window DLL, re-pinned DS Exclusive Fish.dll and {added} executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
