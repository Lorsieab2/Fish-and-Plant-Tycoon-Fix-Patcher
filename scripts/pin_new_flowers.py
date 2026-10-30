"""Pin the New Flowers setting into the plant manifest.

    python scripts/pin_new_flowers.py "<vanilla Plant Tycoon folder>"

Run after rebuilding "Unused Flowers.dll" (scripts/build_ftfp_new_flowers.ps1)
or its art (scripts/build_new_flowers_assets.py). It

  * records every companion file under assets/plant_tycoon_flowers by size
    and SHA-256, with the game-relative destination it is copied to;
  * computes the output executable's SHA-256 for every combination of
    settings that includes New Flowers (the manifest's byte patches, then the
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
import plant_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "plant_manifest.json"
SOURCE = "assets/plant_tycoon_flowers"
SETTING_ID = "new_flowers"
PROFILE = ds_fish_loader.PLANT

SETTING = {
    "id": SETTING_ID,
    "name": "Add unused flowers",
    "summary": "Adds the 14 flowers that are in the game's art but never used: 322 new species, reached by Mutation Liquid and breeding.",
    "description": (
        "Adds the 14 flower heads that ship in the game's art but no plant uses, as new flowers: "
        "Nightingale, Rosetta, Lilac, Veronica, Violetta, Stella, Silvermist, Anagallis, Buttercup, "
        "Cerulean, Phalaena, Mirabilis, Indigoberry and Prunus (names by Virtual_Lady and Lorsieab2), "
        "322 new species with the 23 foliages. "
        "All are the rarest class. Mutation Liquid can now step a Tilia flower one place further, "
        "into the new ones, with the same odds, and breeding with one of them follows the DS fish rule (an odd sum rounds up or down at random). "
        "Runs as a companion DLL the game loads at start; each save slot keeps the new species' "
        "prices and discoveries in a separate file beside the save. See "
        "docs/plant-tycoon-new-flowers-design.md."
    ),
    "warning": (
        "Turning this off after new flowers are in a save leaves those plants with flowers the game "
        "cannot draw or price. Sell or compost them before switching it off."
    ),
    "category": "main",
    "default": False,
    "separate_output": True,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def companion_files() -> list[dict]:
    source = ROOT / SOURCE
    files = [{"path": PROFILE.dll_name, "destination": f"{PROFILE.patcher_files_folder}/{PROFILE.dll_name}"}]
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
    vanilla = (Path(sys.argv[1]) / "Plant Tycoon.exe").read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = dict(SETTING)
    setting["companion"] = {"source": SOURCE, "startup_loader": True, "files": companion_files()}
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID] + [setting]

    assets = plant_patcher.asset_setting_ids(manifest)
    others = [s["id"] for s in manifest["settings"]
              if s["id"] != SETTING_ID and s["id"] not in assets and not s.get("requires_settings")]
    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    for count in range(len(others) + 1):
        for combo in itertools.combinations(others, count):
            enabled = set(combo) | {SETTING_ID}
            patches = plant_patcher.active_patch_records(manifest, enabled)
            patched, _ = plant_patcher.apply_patch_bytes(vanilla, patches)
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled))
            pins[plant_patcher.settings_key(enabled, manifest)] = hashlib.sha256(patched).hexdigest().upper()
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(setting['companion']['files'])} companion files and "
          f"{2 ** len(others)} New Flowers executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
