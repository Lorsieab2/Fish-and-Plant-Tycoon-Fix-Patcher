"""Pin the "Optimize Prices button" setting into both manifests.

    python scripts/pin_optimize_prices.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>"

Run after rebuilding the DLLs (scripts/build_ftfp_optimize_prices.ps1, and
scripts/build_ftfp_ds_fish.ps1 / scripts/build_ftfp_new_flowers.ps1, whose
exports it uses) or the buttons (scripts/build_optimize_prices_assets.py). It

  * records each game's companion files (the DLL and its buttons) by size and
    SHA-256, with their game-relative destinations, and re-records
    "DS Exclusive Fish.dll" and "Unused Flowers.dll" in place;
  * pins the output executable for every combination with the setting: the
    startup loader loads "Optimize Prices.dll" after the companion it loads
    anyway, or on its own (src/ds_fish_loader.py, with_optimize_prices).

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
import plant_patcher  # noqa: E402

SETTING_ID = ds_fish_loader.OPTIMIZE_PRICES_SETTING
DLL_NAME = ds_fish_loader.OPTIMIZE_PRICES_DLL

COMMON = (
    "On Yes, every species you have discovered gets the Breeding Guide's \"best per day\" asking price, the "
    "price that earns the most money over time, worked out in the game with the same maths as the guide for "
    "{shop}. Then it says how many prices it set. Species you have not discovered keep their prices and "
    "nothing else changes; the new prices are the ones you would type yourself, saved with the game as usual. "
    "{max} {extras} Runs as a companion DLL the game loads at start; the save layout is unchanged."
)

MAX_COMMON = (
    "Beside it, a \"Max Prices\" button asks \"Set every discovered species to its highest selling price? "
    "{things} at this price sell much more slowly.\" On Yes, every species you have discovered gets the "
    "highest asking price a {buyer} still buys at (the Breeding Guide's \"highest selling\"): {rule} Then "
    "it says how many prices it set."
)

GAMES = {
    "fish": {
        "manifest": ROOT / "data" / "fish_manifest.json",
        "exe": "Fish Tycoon.exe",
        "source": "assets/fish_tycoon_optimize_prices",
        "folder": ds_fish_loader.FISH.patcher_files_folder,
        "insert_after": "maximizable_window",
        "rerecord": ("ds_fish", "DS Exclusive Fish.dll"),
        "patcher": fish_patcher,
        "profile": ds_fish_loader.fish_profile,
        "summary": "Adds Optimize Prices and Max Prices buttons to the Species Chart and the Fish Store screen: "
                   "they set every discovered species to its best price per day for your shop as it is now, or "
                   "to the highest price a customer still buys at.",
        "first": "Adds an \"Optimize Prices\" button on the Species Chart's bottom bar, left of Done, where you set "
                 "prices, and the same button on the Fish Store screen (opened with Sell Fish), on its bottom "
                 "bar left of Done, so you can use it any time: the Species Chart only opens with a fish in the "
                 "isolation tank. Both buttons do the same thing. It asks \"Set every discovered species to its "
                 "best price per day?\". ",
        "things": "Fish",
        "buyer": "customer",
        "rule": "twice the species' base price, less 1. A customer never buys a fish whose price is twice its base "
                "price or more, and nothing in the game changes that limit: ornaments, the Golden Seahorse and "
                "Advertising bring more customers but not higher prices, and Advertising's research raises the "
                "base price itself, which the button reads when you click it.",
        "shop": "your shop as it is now: each species' base price (with the Advertising price rises), the "
                "ornaments you own, the Golden Seahorse and your Advertising level, with a full selling tank",
        "extras": "With DS Exclusive Fish on, the DS species are included.",
    },
    "plant": {
        "manifest": ROOT / "data" / "plant_manifest.json",
        "exe": "Plant Tycoon.exe",
        "source": "assets/plant_tycoon_optimize_prices",
        "folder": ds_fish_loader.PLANT.patcher_files_folder,
        "insert_after": "sort_seeds",
        "rerecord": ("new_flowers", "Unused Flowers.dll"),
        "patcher": plant_patcher,
        "profile": ds_fish_loader.plant_profile,
        "summary": "Adds Optimize Prices and Max Prices buttons to the Nursery: they set every discovered species "
                   "to its best price per day for your nursery as it is now, or to the highest price a visitor "
                   "still buys at.",
        "first": "Adds an \"Optimize Prices\" button on the Nursery's bottom bar, at the right. It asks \"Set every "
                 "discovered species to its best price per day?\". ",
        "things": "Plants",
        "buyer": "visitor",
        "rule": "visitors buy only while the price they see is below twice the species' value. The Golden Berries "
                "of Wealth, if you have found them, make visitors see every price a quarter lower, so the limit is "
                "higher with them; the button reads them when you click it. Plant Food, pruning, dead leaves, "
                "health, flowers and pests change what visitors see for one plant only, so the button leaves them "
                "out (it is the limit for a healthy, flowering, unpruned plant without Plant Food or pests).",
        "shop": "your nursery as it is now: each species' value, the Golden Berries of Wealth, and the visitors "
                "your ornaments, magic plants and bug collection bring with all 15 sale spots filled, for a "
                "healthy, flowering plant",
        "extras": "With Unused Flowers on, its new species are included.",
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def record(source: str, path: str, destination: str) -> dict:
    data = (ROOT / source / path).read_bytes()
    return {"path": path, "destination": destination, "size": len(data), "sha256": sha256(data)}


def setting(game: dict) -> dict:
    images = sorted((ROOT / game["source"] / "Images").glob("*.png"))
    files = [record(game["source"], DLL_NAME, f"{game['folder']}/{DLL_NAME}")]
    files += [record(game["source"], f"Images/{p.name}", f"Images/{p.name}") for p in images]
    return {
        "id": SETTING_ID,
        "name": "Optimize Prices button",
        "summary": game["summary"],
        "description": game["first"] + COMMON.format(
            shop=game["shop"], extras=game["extras"],
            max=MAX_COMMON.format(things=game["things"], rule=game["rule"], buyer=game["buyer"])),
        "category": "main",
        "default": False,
        "companion": {"source": game["source"], "startup_loader": True, "files": files},
    }


def pin(game: dict, vanilla: bytes) -> int:
    manifest = json.loads(game["manifest"].read_text(encoding="utf-8"))
    ids = [s["id"] for s in manifest["settings"]]
    settings = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    # Re-pinning keeps the setting where it is; a first pin puts it after insert_after.
    at = (ids.index(SETTING_ID) if SETTING_ID in ids
          else next(i for i, s in enumerate(settings) if s["id"] == game["insert_after"]) + 1)
    manifest["settings"] = settings[:at] + [setting(game)] + settings[at:]

    owner, dll = game["rerecord"]
    companion = next(s for s in manifest["settings"] if s["id"] == owner)["companion"]
    for entry in companion["files"]:
        if entry["path"] == dll:
            entry.update(record(companion["source"], entry["path"], entry["destination"]))

    patcher = game["patcher"]
    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    keys = [""] + list(pins)
    for key in keys:
        enabled = {s for s in key.split(",") if s} | {SETTING_ID}
        patched, _ = patcher.apply_patch_bytes(vanilla, patcher.active_patch_records(manifest, enabled))
        patched, _ = ds_fish_loader.append_startup_loader(patched, game["profile"](enabled))
        new_key = (patcher.settings_key(enabled, manifest) if patcher is plant_patcher
                   else patcher.settings_key(enabled))
        pins[new_key] = sha256(patched)
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    game["manifest"].write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(keys)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    for game_id, folder in zip(("fish", "plant"), sys.argv[1:]):
        game = GAMES[game_id]
        count = pin(game, (Path(folder) / game["exe"]).read_bytes())
        print(f"{game_id}: pinned the Optimize Prices files and {count} executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
