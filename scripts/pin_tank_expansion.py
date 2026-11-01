"""Pin the "Bigger tanks: 30 fish" setting into the fish manifest.

    python scripts/pin_tank_expansion.py "<vanilla Fish Tycoon folder>"

Each tank's block in the game's state already holds 31 fish records; the
game only ever uses the first 21. This setting raises every place that
limits a tank to 21 fish to 30 (TANK_PATCHES, explained in
docs/fish-tycoon-tank-expansion.md). 30 is 10 x 3, so the loops the
compiler unrolled three slots at a time only change their count. Record 30
stays free (DS Store Items keeps its animals in its own sidecar, not in the
records).

The selling tank holds 30 too, and the sale code tries every adult in slots
0-29 each second with the stock odds per fish; as in the stock game, the
first that sells ends that second (one sale a second at most). The crowd
the selling scene counts from its adults stops at 21 adults, the stock
game's most, so no fish's odds ever go past the stock game's best. That
needs one short routine (crowd_code) in the .text slack at 0x43FE00, which
the .text virtual size record maps.

The script

  * writes the setting and its patch records (each "requires" it);
  * rebuilds the PE checksum record of every combination of the byte-patch
    settings;
  * pins the output executable of every byte-patch combination.

Run scripts/pin_ds_fish.py, scripts/pin_fish_window.py, scripts/pin_ds_store.py,
scripts/pin_time_warp.py and scripts/pin_store_extras.py afterwards: their
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
import experimental  # noqa: E402
import fish_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "fish_manifest.json"
EXE = "Fish Tycoon.exe"
SETTING_ID = "bigger_tanks"
PREFIX = "tank30_"
OLD_PREFIXES = ("tank26_", "tank30_")
FISH = 30
STOCK_SALE = 21                  # the stock selling tank's most adults: the crowd counts no more

SETTING = {
    "id": SETTING_ID,
    "name": "Bigger tanks: 30 fish",
    "summary": "Every tank holds 30 fish instead of 21, the Sale Tank too; each fish sells with the stock odds. "
               "The isolation tank still holds one.",
    "description": (
        "Raises every tank (Tank 1, Tank 2 and the Sale Tank, Tank 3) from 21 fish to 30; with 3 extra tanks, "
        "Tanks 4-6 hold 30 too. Each tank's block in "
        "the game's state already has room for 31 fish records and the save already stores all of them, so "
        "nothing about the save changes; the game simply only ever used the first 21. Every place that "
        "assumes 21 is raised, so fish 22-30 get everything fish 1-21 get: adding a fish, the swimming fish "
        "on screen, the per-step update (age, food, health, sickness, breeding, death), new game, the "
        "magic-fish check, thought bubbles, medicines, chemicals and growth hormone, customers, the selling "
        "screen, the starter-egg check and the sickness crowding count. Every adult in the Sale Tank is "
        "for sale with the stock odds per fish, and as in the stock game at most one fish sells a second; "
        "the crowd counts at most 21 adults (the stock game's most), so no fish's odds go past the stock "
        "game's best. The isolation tank still holds one fish. With DS Store Items on, the store's animals "
        "have 5 places of their own per tank, kept in their own file beside the save, so they never take a "
        "fish's place. Touches 28 places in "
        "the game's code, plus one short routine for the crowd. See docs/fish-tycoon-tank-expansion.md."
    ),
    "warning": (
        "Turning this off while a tank holds more than 21 fish hides the fish in slots 22-30 until it is on "
        "again. Sell or move fish down to 21 per tank before switching it off."
    ),
    "category": "main",
    "default": True,
}
SETTING = experimental.mark(SETTING)       # src/experimental.py: the owner's label

# The routine lives in the .text slack (file offset = VA - 0x400000; zero in the vanilla file).
CAVE = 0x43FE00
CROWD_AT = 0x43FE00
CAVE_END = 0x43FE20
RANDOM = 0x403240


def rel32(at: int, size: int, target: int) -> bytes:
    """The rel32 of a branch whose instruction starts at `at` and is `size` bytes long."""
    return struct.pack("<i", target - (at + size))


def crowd_code() -> bytes:
    """0x423EEA, after the selling scene counts the adults (ebx) for its crowd: at most 21."""
    at = CROWD_AT
    code = bytearray()
    code += b"\x83\xFB" + bytes([STOCK_SALE])                # cmp ebx, 21
    code += b"\x7E\x05"                                      # jle +5
    code += b"\xBB" + struct.pack("<I", STOCK_SALE)          # mov ebx, 21
    code += b"\x6A\x02"                                      # push 2           (the moved instructions)
    code += b"\xE8" + rel32(at + len(code), 5, RANDOM)       # call Random
    code += b"\xE9" + rel32(at + len(code), 5, 0x423EF1)     # jmp back
    return bytes(code)


def jump(at: int, target: int, size: int) -> str:
    raw = b"\xE9" + rel32(at, 5, target) + b"\x90" * (size - 5)
    return hex_bytes(raw)


def hex_bytes(raw: bytes) -> str:
    return " ".join(f"{b:02X}" for b in raw)


# (id, file offset, expected, replacement): whole instructions; see the doc for each.
TANK_PATCHES = [
    # A. Slot-index bounds, 21 -> 30.
    ("addfish_free_slot", "0x19C72", "83 F8 15", "83 F8 1E"),
    ("view_build_slots", "0x140C5", "83 F8 15", "83 F8 1E"),
    ("view_refresh_slots", "0x15893", "83 F8 15", "83 F8 1E"),
    ("update_loop1_slots", "0x206B1", "83 F9 15", "83 F9 1E"),
    ("update_loop2_count", "0x206E0", "C7 44 24 18 15 00 00 00", "C7 44 24 18 1E 00 00 00"),
    ("reset_remove_slots", "0x1A90C", "83 FE 15", "83 FE 1E"),
    ("reset_clear_count", "0x198F7", "BE 15 00 00 00", "BE 1E 00 00 00"),
    ("magic_scan_slots", "0x1DF20", "83 FA 15", "83 FA 1E"),
    ("thoughts_random_slot", "0x13538", "6A 15", "6A 1E"),
    ("tutorial_sick_slots", "0x25567", "83 F8 15", "83 F8 1E"),
    # B. Byte-offset ends, 21 * 0x288 -> 30 * 0x288.
    ("medicine_a_end", "0x21043", "81 FB 28 35 00 00", "81 FB F0 4B 00 00"),
    ("medicine_b_end", "0x2118E", "81 FB 28 35 00 00", "81 FB F0 4B 00 00"),
    ("medicine_c_end", "0x2128A", "81 FB 28 35 00 00", "81 FB F0 4B 00 00"),
    # C. Sparkles over view entries 0..30 (fish are entries 1..30).
    ("sparkle_entries_a", "0x20E24", "83 FF 15", "83 FF 1F"),
    ("sparkle_entries_b", "0x210AF", "83 FF 15", "83 FF 1F"),
    ("sparkle_entries_c", "0x211FE", "83 FF 15", "83 FF 1F"),
    ("sparkle_entries_d", "0x212FD", "83 FF 15", "83 FF 1F"),
    # D. Loops unrolled x3: 7 passes -> 10 (30 = 10 x 3).
    ("sick_crowd_count", "0x1E260", "B9 07 00 00 00", "B9 0A 00 00 00"),
    ("eggs_t0_count_code", "0x1FCA8", "8B CD 8D 9B 00 00 00 00", "B9 0A 00 00 00 90 90 90"),
    ("eggs_t1_count", "0x1FCE6", "B9 07 00 00 00", "B9 0A 00 00 00"),
    ("eggs_t2_count", "0x1FD26", "B9 07 00 00 00", "B9 0A 00 00 00"),
    ("cheat_age_end", "0x230B4", "3D 28 35 00 00", "3D F0 4B 00 00"),
    ("sell_adults_count", "0x2381F", "8D 57 07", "8D 57 0A"),
    ("sellscene_adults_count", "0x23E85", "B9 07 00 00 00", "B9 0A 00 00 00"),
    ("sellscene_comp_count", "0x23F62", "BA 07 00 00 00", "BA 0A 00 00 00"),
    ("sellscene_comp_body22", "0x23F82", "8D 5A 0F", "8D 5A 0C"),
    # E. Selling: the sale loop tries every adult in slots 0-29 (0x424240; one sale a second at most, as
    # stock); the crowd counts at most 21 adults, the stock selling tank's most.
    ("customers_end", "0x24495", "81 FE 28 35 00 00", "81 FE F0 4B 00 00"),
    ("sale_crowd_cap", "0x23EEA", "6A 02 E8 4F F3 FD FF", jump(0x423EEA, CROWD_AT, 7)),
    ("sale_crowd_code", hex(CROWD_AT - 0x400000), None, hex_bytes(crowd_code())),
]

TEXT_VSIZE = {
    "id": "extend_text_virtual_size_for_bigger_tanks",
    "file_path": EXE,
    "offset": "0x1F8",
    "expected": "9F E2 03 00",
    "replacement": "00 F0 03 00",
    "requires": [SETTING_ID],
    "excludes": ["fix_vanilla_bugs", "golden_seahorse_repurchase", "universal_supply_slots"],
    "note": "30 fish per tank: map the .text slack that holds the crowd routine (0x43FE00).",
}

CHECKSUM_OFFSET = 0x150          # PE optional-header CheckSum in Fish Tycoon.exe


def patches(vanilla: bytes) -> list[dict]:
    out = []
    for name, offset, expected, replacement in TANK_PATCHES:
        start = int(offset, 16)
        size = len(replacement.split())
        if expected is None:                                   # code in the zero-filled slack
            expected = hex_bytes(bytes(size))
            if not (CAVE <= start + 0x400000 and start + 0x400000 + size <= CAVE_END):
                raise SystemExit(f"{name} is outside the slack")
        if len(expected.split()) != size:
            raise SystemExit(f"{name}: expected and replacement lengths differ")
        if vanilla[start:start + size] != bytes.fromhex(expected.replace(" ", "")):
            raise SystemExit(f"{name} at {offset}: the vanilla bytes are not {expected}")
        out.append({"id": f"{PREFIX}{name}", "file_path": EXE, "offset": offset, "expected": expected,
                    "replacement": replacement, "requires": [SETTING_ID],
                    "note": f"30 fish per tank: {name.replace('_', ' ')}."})
    return out


def byte_settings(manifest: dict) -> list[str]:
    """Settings that write executable bytes through patch records (Everything is Free too, though it
    also ships a file)."""
    ids = []
    for setting in manifest["settings"]:
        sid = setting["id"]
        if setting.get("asset_merge"):
            continue
        if any(sid in p.get("requires", []) for p in manifest["patches"]):
            ids.append(sid)
    return ids


def checksum(data: bytes) -> bytes:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert pe + 88 == CHECKSUM_OFFSET, hex(pe + 88)
    value = ds_fish_loader.pe_checksum(data[:pe + 88] + b"\0\0\0\0" + data[pe + 92:])
    return struct.pack("<I", value)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / EXE).read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    at = next(i for i, s in enumerate(manifest["settings"]) if s.get("companion"))
    manifest["settings"].insert(at, dict(SETTING))

    kept = [p for p in manifest["patches"]
            if not p["id"].startswith(OLD_PREFIXES) and not p["id"].startswith("update_pe_checksum")
            and p["id"] != TEXT_VSIZE["id"]]
    manifest["patches"] = kept + patches(vanilla) + [dict(TEXT_VSIZE)]

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
    print(f"{len(TANK_PATCHES) + 1} tank patches; {2 ** len(settings) - 1} checksum records and byte-combination pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
