"""Pin the "3 extra tanks" setting into the fish manifest.

    python scripts/pin_extra_tanks.py "<vanilla Fish Tycoon folder>"

Run after rebuilding "Extra Tanks.dll" (scripts/build_ftfp_extra_tanks.ps1) or
its art (scripts/build_extra_tanks_assets.py), and again after any other
script that adds or re-pins combinations (it re-pins every combination with
the setting from the ones without it). It

  * records every companion file under assets/fish_tycoon_extra_tanks by size
    and SHA-256, with the game-relative destination it is copied to;
  * pins the output executable for every combination with the setting. Its
    startup loader loads "Extra Tanks.dll" (src/ds_fish_loader.py,
    FISH_EXTRA_TANKS), which loads DS Exclusive Fish's or the Maximizable
    window's DLL itself, so every combination with it has its own pin.

Combinations without the setting are left exactly as they are: with it off
the patcher writes the same bytes as before.
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
SOURCE = "assets/fish_tycoon_extra_tanks"
SETTING_ID = "extra_tanks"
DLL_NAME = ds_fish_loader.FISH_EXTRA_TANKS.dll_name

SETTING = {
    "id": SETTING_ID,
    "name": "3 extra tanks",
    "summary": "Three more full tanks for breeding: Tank Three, Tank Four and Tank Five, reached with an arrow beside the tank buttons.",
    "description": (
        "Adds Tank Three, Tank Four and Tank Five: full tanks exactly like Tank One and Tank Two, made from the "
        "game's own tank and run by the game's own code. Fish live, age, eat, get sick, breed and give birth in "
        "them; food, medicines, chemicals, eggs, ornaments, research, the plants, the magic fish, the Golden "
        "Seahorse and the DS store animals work there as in any tank, and Bigger tanks applies to them too. A "
        "small arrow left of the Tank One button switches the tank buttons to the three new tanks and back; "
        "drag a fish onto a button to move it there. Only the Sale Tank sells, with the stock game's limits. "
        "Runs as a companion DLL the game loads at start; the save files keep their stock layout, and each "
        "save slot keeps its extra tanks in \"Fish Tycoon Fix Patcher Data\\Extra Tanks <slot>.dat\" beside "
        "the saves."
    ),
    "warning": (
        "Empty Tank Three, Tank Four and Tank Five (move every fish, animal and ornament out) before turning this "
        "off: without it the game cannot reach them. Nothing is deleted (they come back if you turn it on "
        "again), but until then they are out of the game."
    ),
    "category": "main",
    "default": False,
    "separate_output": True,
}


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
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / "Fish Tycoon.exe").read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "startup_loader": True, "files": companion_files()}
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID] + [setting]

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    added = 0
    for key in [""] + list(pins):
        enabled = {s for s in key.split(",") if s} | {SETTING_ID}
        patched, _ = fish_patcher.apply_patch_bytes(vanilla, fish_patcher.active_patch_records(manifest, enabled))
        patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.fish_profile(enabled))
        pins[fish_patcher.settings_key(enabled)] = sha256(patched)
        added += 1
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(setting['companion']['files'])} companion files and {added} executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
