"""Pin the "Multiple ornaments" setting into the fish manifest.

    python scripts/pin_multiple_ornaments.py "<vanilla Fish Tycoon folder>"

Run after rebuilding "Multiple Ornaments.dll" (scripts/build_ftfp_ornaments.ps1).
It

  * records the companion DLL under assets/fish_tycoon_ornaments by size and
    SHA-256, with its game-relative destination;
  * pins the output executable for every combination with the setting. The
    startup loader then loads "Multiple Ornaments.dll" (src/ds_fish_loader.py,
    FISH_ORNAMENTS), which loads DS Exclusive Fish's or the Maximizable
    window's DLL after it, so each pin is the same combination's patch bytes
    with that loader.

The other combinations' pins are left exactly as they are: with the setting
off nothing changes.
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
SOURCE = "assets/fish_tycoon_ornaments"
SETTING_ID = "multiple_ornaments"
DLL_NAME = ds_fish_loader.FISH_ORNAMENTS.dll_name
FOLDER = ds_fish_loader.FISH_ORNAMENTS.patcher_files_folder

SETTING = {
    "id": SETTING_ID,
    "name": "Multiple ornaments",
    "summary": "Buy the Shell, Pagoda, Diver, Fancy Coral, Sunken Antique Column and Sunken Ship again: "
               "the extra copies are decoration (up to 10 per tank).",
    "description": (
        "Each of the six store ornaments can be bought again once you own it, at its normal price, even when "
        "one is already in that tank or another. Every extra copy is only for decorating: it is drawn, falls "
        "to the gravel, and is dragged, placed and moved to another tank's button exactly like the original, "
        "and you can throw it in the trash can. The ornament's effect (one more customer in the selling "
        "scene, and fewer \"more decor\" thoughts) comes from owning it, once, as in the stock game: copies "
        "never add to it, and throwing copies away never takes it away. Up to 10 copies per tank. The copies "
        "are kept beside each save slot in \"Fish Tycoon Fix Patcher Data\\Ornaments <slot>.dat\"; the save "
        "itself keeps its layout."
    ),
    "warning": (
        "Throw your extra copies in the trash can before turning this off: with it off they are not shown "
        "(they stay in their own file and come back if you turn it on again). The originals and their effect "
        "are not changed either way."
    ),
    "category": "main",
    "default": False,
    "separate_output": True,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def record(path: str, destination: str) -> dict:
    data = (ROOT / SOURCE / path).read_bytes()
    return {"path": path, "destination": destination, "size": len(data), "sha256": sha256(data)}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / "Fish Tycoon.exe").read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "startup_loader": True,
                            "files": [record(DLL_NAME, f"{FOLDER}/{DLL_NAME}")]}
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
    print(f"Pinned the Multiple Ornaments DLL and {added} executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
