"""Pin the "Bigger tanks: 30 fish" setting into the fish manifest.

    python scripts/pin_tank_expansion.py "<vanilla Fish Tycoon folder>"

Each tank's block in the game's state already holds 31 fish records; the
game only ever uses the first 21. This setting raises every place that
limits a tank to 21 fish to 30 (TANK_PATCHES, explained in
docs/fish-tycoon-tank-expansion.md). 30 is 10 x 3, so the loops the
compiler unrolled three slots at a time only change their count. Record 30
stays free (DS Store Items keeps its animals in its own sidecar, not in the
records).

Selling keeps the stock limit: at most 21 adults are for sale at once (the
first 21 adults in slot order are tried each second, as the stock 21-slot
tank tries at most 21), the crowd counts at most 21 adults, and the selling
scene says at most 21. That needs three small routines (SALE_CODE) in the
.text slack at 0x43FE00, which the .text virtual size record maps.

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
import fish_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "fish_manifest.json"
EXE = "Fish Tycoon.exe"
SETTING_ID = "bigger_tanks"
PREFIX = "tank30_"
OLD_PREFIXES = ("tank26_", "tank30_")
FISH = 30
STOCK_SALE = 21                  # adults for sale at once in the stock game (its tank holds 21)

SETTING = {
    "id": SETTING_ID,
    "name": "Bigger tanks: 30 fish",
    "summary": "Every tank holds 30 fish instead of 21; at most 21 are for sale at once, as in the stock game.",
    "description": (
        "Raises every tank (Tank One, Tank Two and the selling tank) from 21 fish to 30. Each tank's block in "
        "the game's state already has room for 31 fish records and the save already stores all of them, so "
        "nothing about the save changes; the game simply only ever used the first 21. Every place that "
        "assumes 21 is raised, so fish 22-30 get everything fish 1-21 get: adding a fish, the swimming fish "
        "on screen, the per-step update (age, food, health, sickness, breeding, death), new game, the "
        "magic-fish check, thought bubbles, medicines, chemicals and growth hormone, customers, the selling "
        "screen, the starter-egg check and the sickness crowding count. Selling keeps the stock limit: at "
        "most 21 adults are for sale at once (the first 21 adults of the selling tank), and the crowd and "
        "the selling screen count at most 21, so nothing sells faster than in the stock game. The isolation "
        "tank still holds one fish. With DS Store Items on, the store's animals live in their own file "
        "beside the save, so they never take a fish's place. Touches 29 places in the game's code, plus "
        "three short routines for the selling limit. See docs/fish-tycoon-tank-expansion.md."
    ),
    "warning": (
        "Turning this off while a tank holds more than 21 fish hides the fish in slots 22-30 until it is on "
        "again. Sell or move fish down to 21 per tank before switching it off."
    ),
    "category": "main",
    "default": False,
}

# The routines live in the .text slack (file offset = VA - 0x400000; zero in the vanilla file).
CAVE = 0x43FE00
SALE_AT, CROWD_AT, SHOWN_AT = 0x43FE00, 0x43FE60, 0x43FE80
CAVE_END = 0x43FEA0
RANDOM = 0x403240


def rel32(at: int, size: int, target: int) -> bytes:
    """The rel32 of a branch whose instruction starts at `at` and is `size` bytes long."""
    return struct.pack("<i", target - (at + size))


def sale_code() -> bytes:
    """0x42448A, the sale loop's "next slot" (every adult that did not sell comes here): stop once the
    21st adult has been tried, else the next slot, up to 30 (the end compare was 0x3528, 21 slots).
    An adult is what the loop tries: live, health above 0, age 20 or more (0x424253-0x424277)."""
    at = SALE_AT
    code = bytearray()
    code += b"\x50\x51\x52"                                  # push eax / ecx / edx
    code += b"\x8B\x57\x70"                                  # mov edx, [edi + 0x70]   the state
    code += b"\x8B\x4C\x24\x1C"                              # mov ecx, [esp + 0x1C]   the slot ([esp + 0x10])
    code += b"\x33\xC0"                                      # xor eax, eax            adults in slots 0..slot
    code += b"\x81\xC2" + struct.pack("<I", 0xA768)          # add edx, 0xA768         tank 2, slot 0
    loop = len(code)
    code += b"\x83\x3A\x00\x74\x0F"                          # cmp [edx], 0 / je next
    code += b"\x83\x7A\x3C\x00\x74\x09"                      # cmp [edx + 0x3C], 0 / je next
    code += b"\x83\x7A\x0C\x14\x7C\x03"                      # cmp [edx + 0xC], 0x14 / jl next
    code += b"\x83\xC0\x01"                                  # add eax, 1
    code += b"\x81\xC2" + struct.pack("<I", 0x288)           # next: add edx, 0x288
    code += b"\x83\xE9\x01"                                  # sub ecx, 1
    code += b"\x79" + bytes([(loop - (len(code) + 2)) & 0xFF])   # jns loop
    code += b"\x83\xF8" + bytes([STOCK_SALE])                # cmp eax, 21
    code += b"\x5A\x59\x58"                                  # pop edx / ecx / eax (flags kept)
    code += b"\x0F\x8D" + rel32(at + len(code), 6, 0x4244A1)  # jge 0x4244A1  (done for this second)
    code += b"\x83\x44\x24\x10\x01"                          # add [esp + 0x10], 1
    code += b"\x81\xC6" + struct.pack("<I", 0x288)           # add esi, 0x288
    code += b"\x81\xFE" + struct.pack("<I", FISH * 0x288)    # cmp esi, 30 * 0x288
    code += b"\x0F\x8C" + rel32(at + len(code), 6, 0x424250)  # jl 0x424250
    code += b"\xE9" + rel32(at + len(code), 5, 0x4244A1)     # jmp 0x4244A1
    return bytes(code)


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


def shown_code() -> bytes:
    """0x42391C, the selling screen's "fish for sale" number (edi): at most 21."""
    at = SHOWN_AT
    code = bytearray()
    code += b"\x8B\xC7"                                      # mov eax, edi
    code += b"\x83\xF8" + bytes([STOCK_SALE])                # cmp eax, 21
    code += b"\x7E\x05"                                      # jle +5
    code += b"\xB8" + struct.pack("<I", STOCK_SALE)          # mov eax, 21
    code += b"\x50"                                          # push eax       (was push edi)
    code += b"\x8D\x4C\x24\x14"                              # lea ecx, [esp + 0x14]
    code += b"\xE9" + rel32(at + len(code), 5, 0x423921)     # jmp back
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
    # E. Selling keeps the stock limit of 21 for sale at once.
    ("sale_next_slot", "0x2448A",
     "83 44 24 10 01 81 C6 88 02 00 00 81 FE 28 35 00 00 0F 8C AF FD FF FF", jump(0x42448A, SALE_AT, 23)),
    ("sale_crowd_cap", "0x23EEA", "6A 02 E8 4F F3 FD FF", jump(0x423EEA, CROWD_AT, 7)),
    ("sale_shown_cap", "0x2391C", "57 8D 4C 24 14", jump(0x42391C, SHOWN_AT, 5)),
    ("sale_code", hex(SALE_AT - 0x400000), None, hex_bytes(sale_code())),
    ("sale_crowd_code", hex(CROWD_AT - 0x400000), None, hex_bytes(crowd_code())),
    ("sale_shown_code", hex(SHOWN_AT - 0x400000), None, hex_bytes(shown_code())),
]

TEXT_VSIZE = {
    "id": "extend_text_virtual_size_for_bigger_tanks",
    "file_path": EXE,
    "offset": "0x1F8",
    "expected": "9F E2 03 00",
    "replacement": "00 F0 03 00",
    "requires": [SETTING_ID],
    "excludes": ["fix_vanilla_bugs", "golden_seahorse_repurchase", "universal_supply_slots"],
    "note": "30 fish per tank: map the .text slack that holds the selling-limit routines (0x43FE00).",
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
