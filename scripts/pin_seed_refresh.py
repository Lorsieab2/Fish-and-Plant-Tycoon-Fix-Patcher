"""Pin the "R refreshes the seed shop" setting into the plant manifest.

    python scripts/pin_seed_refresh.py "<vanilla Plant Tycoon folder>"

The Supplies store's key handler (0x447950, the store scene's vtable slot 2)
sends a typed character through a byte table (0x4479F4, characters '1'..'s')
to one of five cases (jump table 0x4479E0). Case 4 (0x44797E: return 0) is
every character the store ignores, 'r' and 'R' included. The patch points
case 4 at a few bytes in the zero tail of .text (VA 0x464930), which do:

    mov eax, [esp+0xC]       ; the typed character
    or al, 0x20              ; 'R' -> 'r'
    cmp al, 'r'
    jne done
    push ecx
    mov ecx, [ecx+0x1BC]     ; the game state (as the store's Escape case reads it)
    test ecx, ecx
    je skip
    call 0x41DC60            ; the game's own seed-shelf roll (thiscall on the state)
  skip:
    pop ecx
  done:
    xor al, al               ; exactly what case 4 returned
    ret 0xC

0x41DC60 is the routine the 86401-second reroll calls (0x428A20), so the odds
are the game's own; with "Add new store upgrades and items" its Legendary
Seeds hook (0x41DDDA, the roll's tail) rerolls those too. The daily reroll
time (state+0x5A0) is not touched and nothing is added to the save. Every
other ignored key still returns 0. The .text section's VirtualSize grows
from 0x6392F to its raw size 0x64000 so the tail is mapped.

Then every PE checksum record and every executable pin is rebuilt for all
setting combinations.
"""

from __future__ import annotations

import hashlib
from itertools import combinations
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ds_fish_loader  # noqa: E402
import plant_patcher  # noqa: E402

MANIFEST = ROOT / "data" / "plant_manifest.json"
EXE = "Plant Tycoon.exe"
SETTING_ID = "seed_refresh_key"
CAVE_VA = 0x464930
JUMP_ENTRY_VA = 0x4479F0           # case 4 of the store's character switch
STOCK_CASE4 = 0x44797E
ROLL_VA = 0x41DC60
TEXT_VSIZE_OLD = 0x6392F
TEXT_VSIZE_NEW = 0x64000
CHECKSUM_OFFSET = 0x150

SETTING = {
    "id": SETTING_ID,
    "name": "R refreshes the seed shop",
    "summary": "Press R in the Supplies store to restock the seed shelves at once (Legendary Seeds too), with the game's own odds.",
    "description": (
        "A cheat key for the Supplies store: pressing R (or r) on the store screen restocks all nine "
        "seed packets at once, using the game's own restock roll, so the odds are the stock ones. "
        "With Add new store upgrades and items, the three Legendary Seeds are rerolled too. Bought-out "
        "shelves fill again. The daily restock still comes at its usual time, and nothing extra is "
        "saved. R does nothing on any other screen."
    ),
    "category": "main",
    "default": True,
}


def offset(va: int) -> int:
    return va - 0x400000


def cave_bytes() -> bytes:
    code = bytearray()
    code += b"\x8B\x44\x24\x0C"              # mov eax, [esp+0xC]
    code += b"\x0C\x20"                      # or al, 0x20
    code += b"\x3C\x72"                      # cmp al, 'r'
    code += b"\x75\x11"                      # jne done (+17)
    code += b"\x51"                          # push ecx
    code += b"\x8B\x89\xBC\x01\x00\x00"      # mov ecx, [ecx+0x1BC]
    code += b"\x85\xC9"                      # test ecx, ecx
    code += b"\x74\x05"                      # je skip (+5)
    call_at = CAVE_VA + len(code)
    code += b"\xE8" + struct.pack("<i", ROLL_VA - (call_at + 5))
    code += b"\x59"                          # skip: pop ecx
    code += b"\x32\xC0"                      # done: xor al, al
    code += b"\xC2\x0C\x00"                  # ret 0xC
    assert len(code) == 32 and 10 + code[9] == len(code) - 5 and 21 + code[20] == len(code) - 6, len(code)
    return bytes(code)


def hex_bytes(raw: bytes) -> str:
    return " ".join(f"{b:02X}" for b in raw)


def text_vsize_offset(data: bytes) -> int:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + optional_size
    assert data[table:table + 5] == b".text"
    return table + 8


def records(vanilla: bytes) -> list[dict]:
    cave = cave_bytes()
    vso = text_vsize_offset(vanilla)
    return [
        {"id": "seed_refresh_text_size", "file_path": EXE, "offset": hex(vso),
         "expected": hex_bytes(struct.pack("<I", TEXT_VSIZE_OLD)),
         "replacement": hex_bytes(struct.pack("<I", TEXT_VSIZE_NEW)), "requires": [SETTING_ID],
         "note": "The .text section's VirtualSize, 0x6392F -> 0x64000 (its raw size), so the zero tail "
                 "that holds the R key's code is mapped."},
        {"id": "seed_refresh_code", "file_path": EXE, "offset": hex(offset(CAVE_VA)),
         "expected": hex_bytes(bytes(len(cave))), "replacement": hex_bytes(cave), "requires": [SETTING_ID],
         "note": "VA 0x464930 (the zero tail of .text): if the typed character is r or R, call the game's "
                 "own seed-shelf roll 0x41DC60 on the state ([store+0x1BC]); always return 0, as the "
                 "ignored-key case did."},
        {"id": "seed_refresh_key_case", "file_path": EXE, "offset": hex(offset(JUMP_ENTRY_VA)),
         "expected": hex_bytes(struct.pack("<I", STOCK_CASE4)),
         "replacement": hex_bytes(struct.pack("<I", CAVE_VA)), "requires": [SETTING_ID],
         "note": "Case 4 of the store's character switch (jump table 0x4479E0), the ignored keys, now "
                 "goes through the R key code at 0x464930 instead of straight to 'return 0'."},
    ]


def checksum(data: bytes) -> str:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert pe + 88 == CHECKSUM_OFFSET
    value = ds_fish_loader.pe_checksum(data[:pe + 88] + b"\0\0\0\0" + data[pe + 92:])
    return hex_bytes(struct.pack("<I", value))


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / EXE).read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    # after the old-age fix, before the content settings
    at = next(i for i, s in enumerate(manifest["settings"]) if s["id"] == "no_old_age_plant_deaths") + 1
    manifest["settings"].insert(at, dict(SETTING))
    manifest["patches"] = [p for p in manifest["patches"]
                           if SETTING_ID not in p.get("requires", []) and not p["id"].startswith("update_pe_checksum")]
    manifest["patches"] += records(vanilla)

    # PE checksum: one record per combination of the byte-patch settings.
    byte_settings = sorted({r for p in manifest["patches"] for r in p.get("requires", [])})
    original_sum = hex_bytes(vanilla[CHECKSUM_OFFSET:CHECKSUM_OFFSET + 4])
    for count in range(1, len(byte_settings) + 1):
        for combo in combinations(byte_settings, count):
            patched, _ = plant_patcher.apply_patch_bytes(
                vanilla, plant_patcher.active_patch_records(manifest, set(combo)))
            manifest["patches"].append({
                "id": "update_pe_checksum_" + "_".join(combo), "file_path": EXE, "offset": hex(CHECKSUM_OFFSET),
                "expected": original_sum, "replacement": checksum(patched), "requires": list(combo),
                "excludes": [s for s in byte_settings if s not in combo],
                "note": f"PE optional-header CheckSum, recomputed for this exact combination ({', '.join(combo)}).",
            })

    # Every executable pin, all combinations of the settings that change the executable.
    assets = plant_patcher.asset_setting_ids(manifest)
    settings = {s["id"]: s for s in manifest["settings"]}
    exe_ids = [sid for sid in settings if sid not in assets]
    pins = {}
    for count in range(1, len(exe_ids) + 1):
        for combo in combinations(exe_ids, count):
            enabled = set(combo)
            if any(set(settings[s].get("requires_settings", [])) - enabled for s in enabled):
                continue
            patched, _ = plant_patcher.apply_patch_bytes(vanilla, plant_patcher.active_patch_records(manifest, enabled))
            if any(settings[s].get("companion", {}).get("startup_loader") for s in enabled):
                patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled))
            pins[plant_patcher.settings_key(enabled, manifest)] = hashlib.sha256(patched).hexdigest().upper()
    manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(records(vanilla))} patches, {2 ** len(byte_settings) - 1} checksum records, {len(pins)} pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
