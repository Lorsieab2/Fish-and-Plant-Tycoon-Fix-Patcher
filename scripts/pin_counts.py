"""Pin the "Tank and greenhouse counts" setting into both games' manifests.

    python scripts/pin_counts.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>"

Run after rebuilding "Tank Counts.dll" (scripts/build_ftfp_tank_counts.ps1)
or "Greenhouse Counts.dll" (scripts/build_ftfp_greenhouse_counts.ps1). For
each game it

  * records the companion DLL by size and SHA-256, with its game-relative
    destination;
  * pins the output executable for every combination with the setting: the
    startup loader then loads the counts DLL (src/ds_fish_loader.py,
    FISH_COUNTS / PLANT_COUNTS), which loads the DLL the loader would have
    loaded without it.

The other combinations' pins are left exactly as they are.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import plant_patcher  # noqa: E402

SETTING_ID = ds_fish_loader.COUNTS_SETTING
NAME = "Tank and greenhouse counts"

FISH_SETTING = {
    "id": SETTING_ID,
    "name": NAME,
    "summary": "Shows how many fish the tank on screen holds, and how many are adults, teens and babies, its "
               "creatures and the isolation tank, in the game's own font.",
    "description": (
        "Adds three lines at the top left of the water on the tank screen, for the tank you are looking at: "
        "\"Fish: 12 of 21 (8 adults, 3 teens, 1 baby)\" (26 with Bigger tanks), then the creatures in it "
        "(\"Creatures: Golden Seahorse, Moray Eel\"), then \"Isolation tank: 1 of 1 (1 adult)\". Adults, teens "
        "and babies are the game's own stages: a baby is age 1-5, a teen 6-19, an adult 20 and up. Dead fish "
        "are left out of the count and shown after it as \"Dead: 2\" until you throw them away. The lines "
        "follow the game's language (English or German), update every frame, and sit behind the fish, so "
        "nothing in the tank is ever covered. Display only: nothing in the game or your saves changes. Runs as "
        "a companion DLL the game loads at start."
    ),
    "category": "main",
    "default": True,
}

PLANT_SETTING = {
    "id": SETTING_ID,
    "name": NAME,
    "summary": "Shows how many of the greenhouse's 15 pots hold a living plant, and how many are mature, have "
               "buds or are seedlings, in the game's own font.",
    "description": (
        "Adds one line along the top of the greenhouse screen: \"Plants: 9 of 15 (5 mature, 2 with buds, "
        "2 seedlings)\", counting the pots that hold a living plant. The stages are the game's own: a plant "
        "is a seedling before age 21 (its countdown says \"Buds in ... Min.\"), has buds from 21 (\"Mature in "
        "... Min.\") and is mature from 24. Dead plants are left out of the count and shown after it as "
        "\"Dead: 1\" until you trash them. The line updates every frame and sits behind the plants, so no "
        "plant, pot or tool is ever covered. Display only: nothing in the game or your saves changes. Runs as "
        "a companion DLL the game loads at start."
    ),
    "category": "main",
    "default": True,
}

GAMES = (
    # manifest, setting, source folder, DLL, profile, insert after, patcher module, its key function
    ("fish", FISH_SETTING, "assets/fish_tycoon_counts", ds_fish_loader.FISH_COUNTS, "maximizable_window",
     fish_patcher, lambda enabled, manifest: fish_patcher.settings_key(enabled)),
    ("plant", PLANT_SETTING, "assets/plant_tycoon_counts", ds_fish_loader.PLANT_COUNTS, "add_missing_ldw_assets",
     plant_patcher, plant_patcher.settings_key),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def fast_pe_checksum(data: bytes | bytearray) -> int:
    """ds_fish_loader.pe_checksum, vectorised (the same sum: 16-bit words with
    the end-around carry, skipping the checksum field, plus the length)."""
    pe = int.from_bytes(bytes(data[0x3C:0x40]), "little")
    checksum_offset = pe + 24 + 64
    padded = bytes(data) + (b"\0" if len(data) % 2 else b"")
    words = np.frombuffer(padded, dtype="<u2").astype(np.uint64)
    words[checksum_offset // 2: checksum_offset // 2 + 2] = 0
    total = int(words.sum())
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (total + len(data)) & 0xFFFFFFFF


def pin_game(game: str, setting_base: dict, source: str, profile: ds_fish_loader.LoaderProfile, after: str,
             patcher, key_of, vanilla: bytes) -> int:
    manifest_path = ROOT / "data" / f"{game}_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dll = (ROOT / source / profile.dll_name).read_bytes()
    setting = dict(setting_base)
    setting["companion"] = {"source": source, "startup_loader": True, "files": [{
        "path": profile.dll_name, "destination": f"{profile.patcher_files_folder}/{profile.dll_name}",
        "size": len(dll), "sha256": sha256(dll)}]}
    settings = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    at = next(i for i, s in enumerate(settings) if s["id"] == after) + 1
    manifest["settings"] = settings[:at] + [setting] + settings[at:]

    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
    keys = list(dict.fromkeys([""] + list(pins)))
    for key in keys:
        enabled = {s for s in key.split(",") if s} | {SETTING_ID}
        patched, _ = patcher.apply_patch_bytes(vanilla, patcher.active_patch_records(manifest, enabled))
        patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled)
                                                          if game == "plant" else ds_fish_loader.fish_profile(enabled))
        pins[key_of(enabled, manifest)] = sha256(patched)
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(keys)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    folders = {"fish": (Path(sys.argv[1]), "Fish Tycoon.exe"), "plant": (Path(sys.argv[2]), "Plant Tycoon.exe")}
    sample = (folders["fish"][0] / folders["fish"][1]).read_bytes()
    if fast_pe_checksum(sample) != ds_fish_loader.pe_checksum(sample):
        raise SystemExit("the vectorised PE checksum disagrees with ds_fish_loader.pe_checksum")
    ds_fish_loader.pe_checksum = fast_pe_checksum
    for game, setting, source, profile, after, patcher, key_of in GAMES:
        folder, exe = folders[game]
        count = pin_game(game, setting, source, profile, after, patcher, key_of, (folder / exe).read_bytes())
        print(f"{game}: pinned {profile.dll_name} and {count} executable combinations with the counts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
