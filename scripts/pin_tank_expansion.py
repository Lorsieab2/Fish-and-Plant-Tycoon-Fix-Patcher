"""Pin the "Bigger tanks: 26 fish" setting into the fish manifest.

    python scripts/pin_tank_expansion.py "<vanilla Fish Tycoon folder>"

Each tank's block in the game's state already holds 31 fish records; the
game only ever uses the first 21. This setting raises every place that
limits a tank to 21 fish to 26 (45 byte changes, listed in TANK_PATCHES and
explained in docs/fish-tycoon-tank-expansion.md). Slots 26-30 stay free for
the DS Store Items' animals.

The script

  * writes the setting and its patch records (each "requires" it);
  * rebuilds the PE checksum record of every combination of the byte-patch
    settings (one per combination, as before, now twice as many);
  * pins the output executable of every byte-patch combination.

Run scripts/pin_ds_fish.py and scripts/pin_ds_store.py afterwards: their
combinations include this setting.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "fish_manifest.json"
EXE = "Fish Tycoon.exe"
SETTING_ID = "bigger_tanks"

SETTING = {
    "id": SETTING_ID,
    "name": "Bigger tanks: 26 fish",
    "summary": "Every tank holds 26 fish instead of 21.",
    "description": (
        "Raises every tank (Tank 1, Tank 2 and the selling tank) from 21 fish to 26. Each tank's block in "
        "the game's state already has room for 31 fish records and the save already stores all of them, so "
        "nothing about the save changes; the game simply only ever used the first 21. Every place that "
        "assumes 21 is raised: adding a fish, the swimming fish on screen, the per-step update, new game, "
        "the magic-fish check, thought bubbles, medicines and chemicals, customers, the selling screen and "
        "the sickness crowding count. Loops that test three fish per pass test two, thirteen times. With "
        "DS Store Items on, slots 26-30 hold the store's animals, so they never take a fish's place. "
        "Touches 45 places. See docs/fish-tycoon-tank-expansion.md."
    ),
    "warning": (
        "Turning this off while a tank holds more than 21 fish hides the fish in slots 22-26 until it is on "
        "again. Sell or move fish down to 21 per tank before switching it off."
    ),
    "category": "main",
    "default": False,
}

# (id, file offset, expected, replacement): whole instructions; see the doc for each.
TANK_PATCHES = [
    ("addfish_free_slot", "0x19C72", "83 F8 15", "83 F8 1A"),
    ("view_build_slots", "0x140C5", "83 F8 15", "83 F8 1A"),
    ("view_refresh_slots", "0x15893", "83 F8 15", "83 F8 1A"),
    ("update_loop1_slots", "0x206B1", "83 F9 15", "83 F9 1A"),
    ("update_loop2_count", "0x206E0", "C7 44 24 18 15 00 00 00", "C7 44 24 18 1A 00 00 00"),
    ("reset_remove_slots", "0x1A90C", "83 FE 15", "83 FE 1A"),
    ("reset_clear_count", "0x198F7", "BE 15 00 00 00", "BE 1A 00 00 00"),
    ("magic_scan_slots", "0x1DF20", "83 FA 15", "83 FA 1A"),
    ("thoughts_random_slot", "0x13538", "6A 15", "6A 1A"),
    ("tutorial_sick_slots", "0x25567", "83 F8 15", "83 F8 1A"),
    ("medicine_a_end", "0x21043", "81 FB 28 35 00 00", "81 FB D0 41 00 00"),
    ("medicine_b_end", "0x2118E", "81 FB 28 35 00 00", "81 FB D0 41 00 00"),
    ("medicine_c_end", "0x2128A", "81 FB 28 35 00 00", "81 FB D0 41 00 00"),
    ("customers_end", "0x24495", "81 FE 28 35 00 00", "81 FE D0 41 00 00"),
    ("sparkle_entries_a", "0x20E24", "83 FF 15", "83 FF 1B"),
    ("sparkle_entries_b", "0x210AF", "83 FF 15", "83 FF 1B"),
    ("sparkle_entries_c", "0x211FE", "83 FF 15", "83 FF 1B"),
    ("sparkle_entries_d", "0x212FD", "83 FF 15", "83 FF 1B"),
    ("sick_crowd_count", "0x1E260", "B9 07 00 00 00", "B9 0D 00 00 00"),
    ("sick_crowd_third_skip", "0x1E280", "74 03", "EB 03"),
    ("sick_crowd_stride", "0x1E285", "05 98 07 00 00", "05 10 05 00 00"),
    ("eggs_t0_count_code", "0x1FCA8", "8B CD 8D 9B 00 00 00 00", "B9 0D 00 00 00 90 90 90"),
    ("eggs_t0_third_skip", "0x1FCCF", "74 05", "EB 05"),
    ("eggs_t0_stride", "0x1FCD6", "05 98 07 00 00", "05 10 05 00 00"),
    ("eggs_t1_count", "0x1FCE6", "B9 07 00 00 00", "B9 0D 00 00 00"),
    ("eggs_t1_third_skip", "0x1FD0F", "74 05", "EB 05"),
    ("eggs_t1_stride", "0x1FD16", "05 98 07 00 00", "05 10 05 00 00"),
    ("eggs_t2_count", "0x1FD26", "B9 07 00 00 00", "B9 0D 00 00 00"),
    ("eggs_t2_third_skip", "0x1FD4F", "74 05", "EB 05"),
    ("eggs_t2_stride", "0x1FD56", "05 98 07 00 00", "05 10 05 00 00"),
    ("cheat_age_third_a", "0x2309A", "89 9C 2A A4 08 00 00", "89 9C 2A 1C 06 00 00"),
    ("cheat_age_third_b", "0x230A9", "8B AA AC 08 00 00", "8B AA 24 06 00 00"),
    ("cheat_age_stride", "0x230AF", "05 98 07 00 00", "05 10 05 00 00"),
    ("cheat_age_end", "0x230B4", "3D 28 35 00 00", "3D D0 41 00 00"),
    ("cheat_age_third_c", "0x230B9", "89 AA A8 08 00 00", "89 AA 20 06 00 00"),
    ("sell_adults_count", "0x2381F", "8D 57 07", "8D 57 0D"),
    ("sell_adults_third_skip", "0x23873", "74 1D", "EB 1D"),
    ("sell_adults_stride", "0x23892", "05 98 07 00 00", "05 10 05 00 00"),
    ("sellscene_adults_count", "0x23E85", "B9 07 00 00 00", "B9 0D 00 00 00"),
    ("sellscene_adults_third_skip", "0x23EC9", "74 15", "EB 15"),
    ("sellscene_adults_stride", "0x23EE0", "05 98 07 00 00", "05 10 05 00 00"),
    ("sellscene_comp_count", "0x23F62", "BA 07 00 00 00", "BA 0D 00 00 00"),
    ("sellscene_comp_body22", "0x23F82", "8D 5A 0F", "8D 5A 09"),
    ("sellscene_comp_third_skip", "0x23FC8", "74 14", "EB 14"),
    ("sellscene_comp_stride", "0x23FDE", "05 98 07 00 00", "05 10 05 00 00"),
]

CHECKSUM_OFFSET = 0x150          # PE optional-header CheckSum in Fish Tycoon.exe


def byte_settings(manifest: dict) -> list[str]:
    """Settings that write executable bytes through patch records."""
    ids = []
    for setting in manifest["settings"]:
        sid = setting["id"]
        if setting.get("companion") or setting.get("asset_merge"):
            continue
        if any(sid in p.get("requires", []) for p in manifest["patches"]):
            ids.append(sid)
    return ids


def checksum(data: bytes) -> bytes:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert pe + 88 == CHECKSUM_OFFSET, hex(pe + 88)
    value = ds_fish_loader.pe_checksum(data[:pe + 88] + b"\0\0\0\0" + data[pe + 92:])
    return struct.pack("<I", value)


def hex_bytes(raw: bytes) -> str:
    return " ".join(f"{b:02X}" for b in raw)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / EXE).read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    at = next(i for i, s in enumerate(manifest["settings"]) if s.get("companion"))
    manifest["settings"].insert(at, dict(SETTING))

    patches = [p for p in manifest["patches"]
               if not p["id"].startswith("tank26_") and not p["id"].startswith("update_pe_checksum")]
    for name, offset, expected, replacement in TANK_PATCHES:
        start = int(offset, 16)
        if vanilla[start:start + len(bytes.fromhex(expected.replace(" ", "")))] != bytes.fromhex(expected.replace(" ", "")):
            raise SystemExit(f"{name} at {offset}: the vanilla bytes are not {expected}")
        patches.append({"id": f"tank26_{name}", "file_path": EXE, "offset": offset, "expected": expected,
                        "replacement": replacement, "requires": [SETTING_ID],
                        "note": f"26 fish per tank: {name.replace('_', ' ')}."})
    manifest["patches"] = patches

    settings = byte_settings(manifest)
    vanilla_sum = hex_bytes(vanilla[CHECKSUM_OFFSET:CHECKSUM_OFFSET + 4])
    pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items()
            if set(k.split(",")) - set(settings) and k}       # keep the companion combinations
    for count in range(1, len(settings) + 1):
        for combo in itertools.combinations(sorted(settings), count):
            enabled = set(combo)
            records = fish_patcher.active_patch_records(manifest, enabled)
            patched, _ = fish_patcher.apply_patch_bytes(vanilla, records)
            new_sum = checksum(patched)
            manifest["patches"].append({
                "id": "update_pe_checksum_" + "_".join(combo),
                "file_path": EXE,
                "offset": hex(CHECKSUM_OFFSET),
                "expected": vanilla_sum,
                "replacement": hex_bytes(new_sum),
                "requires": list(combo),
                "excludes": [s for s in sorted(settings) if s not in enabled],
                "note": f"PE optional-header CheckSum, recomputed for this exact combination ({', '.join(combo)}).",
            })
            final, _ = fish_patcher.apply_patch_bytes(vanilla, fish_patcher.active_patch_records(manifest, enabled))
            pins[fish_patcher.settings_key(enabled)] = hashlib.sha256(final).hexdigest().upper()
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(TANK_PATCHES)} tank patches; {2 ** len(settings) - 1} checksum records and byte-combination pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
