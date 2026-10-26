"""Pin the DS Fish setting into the fish manifest.

    python scripts/pin_ds_fish.py "<vanilla Fish Tycoon folder>"

Run after rebuilding "FTFP DS Fish.dll" (scripts/build_ftfp_ds_fish.ps1) or
the sheets (scripts/build_ds_fish_assets.py). It

  * records every companion file under assets/fish_tycoon_ds by size and
    SHA-256, with the game-relative destination it is copied to;
  * computes the output executable's SHA-256 for every combination of
    settings that includes DS Fish (the manifest's byte patches, then the
    startup loader), from the vanilla executable, and pins each one.

The other combinations' pins are left exactly as they are.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "fish_manifest.json"
SOURCE = "assets/fish_tycoon_ds"
SETTING_ID = "ds_fish"

SETTING = {
    "id": SETTING_ID,
    "name": "DS Exclusive Fish",
    "summary": "Adds the Nintendo DS version's 7 extra fish bodies and 7 extra fins: 343 new species, reached through the Unknown Chemical and the Magic Fish of Mutation.",
    "description": (
        "Adds the seven bodies and seven fins only the Nintendo DS version has: Clownfish, Discus, "
        "Bicolor, Trigger, Surgeonfish, Tang and Idle bodies, and Small Fin, Roundy, Angel, Clown, "
        "Yellow, Blue and Moorish fins, 343 new species in all. Eggs, the store and breeding two PC "
        "fish never give them. The Unknown Chemical, and the Magic Fish of Mutation at hatching, "
        "can now step a Spotanus body or a Twin-Fin fin one place further, into the DS ones, with "
        "the same odds as before. Breeding a DS fish follows the DS game: the parents' average, an "
        "odd total rounded up or down at random. Prices, rarity (most need environment level 3), "
        "names and fin placement follow the DS game. Runs as a companion DLL the game loads at "
        "start; new sprites go in Images, and each save slot keeps its DS species data in a "
        "separate file beside the save. See docs/fish-tycoon-ds-fish-testing-guide.md."
    ),
    "warning": (
        "Turning this off after DS fish are in a save leaves those fish with genes the game "
        "cannot draw or name. Sell or trash every DS fish before switching it off."
    ),
    "category": "main",
    "default": False,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def companion_files() -> list[dict]:
    source = ROOT / SOURCE
    files = [{
        "path": ds_fish_loader.DLL_NAME,
        "destination": f"{ds_fish_loader.PATCHER_FILES_FOLDER}/{ds_fish_loader.DLL_NAME}",
    }]
    for image in sorted((source / "Images").glob("*.png")):
        files.append({"path": f"Images/{image.name}", "destination": f"Images/{image.name}"})
    for entry in files:
        path = source / entry["path"]
        entry["size"] = path.stat().st_size
        entry["sha256"] = sha256(path)
    return files


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / "Fish Tycoon.exe").read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "startup_loader": True, "files": companion_files()}
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID] + [setting]

    # Settings that build on DS Fish (DS Store Items) are pinned by their own
    # script: run scripts/pin_ds_store.py after this one.
    others = [s["id"] for s in manifest["settings"] if s["id"] != SETTING_ID and not s.get("requires_settings")]
    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    for count in range(len(others) + 1):
        for combo in itertools.combinations(others, count):
            enabled = set(combo) | {SETTING_ID}
            patches = fish_patcher.active_patch_records(manifest, enabled)
            patched, _ = fish_patcher.apply_patch_bytes(vanilla, patches)
            patched, _ = ds_fish_loader.append_startup_loader(patched)
            pins[fish_patcher.settings_key(enabled)] = hashlib.sha256(patched).hexdigest().upper()
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(setting['companion']['files'])} companion files and "
          f"{2 ** len(others)} DS Fish executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
