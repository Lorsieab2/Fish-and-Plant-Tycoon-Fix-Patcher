"""Pin the "Fix Vanilla Bugs" setting into the fish manifest.

    python scripts/pin_vanilla_fixes.py "<vanilla Fish Tycoon folder>"

Stock bugs fixed by data changes alone, each listed in VANILLA_FIXES:

  * The two store plants do each other's job. The $200 Plant of Incubation
    ("...increases the viability of purchased eggs") sets the dword at
    state + 0x168, but only the starvation code reads it (0x4205A1: a
    starving fish gets food +5 on Random(100) <= 20). The $350 Plant of
    Nutrition sets state + 0x17C, which the three egg-hatch paths read
    (0x4213DB, 0x4214AA, 0x42157D: +1 egg per batch). The four reads swap
    their offset, so each plant does what its name says. The store (names,
    pictures, prices) and the plant drawn in the tank stay as they are, and
    saves need no change: an owned plant keeps its dword.

  * The Golden Seahorse is bought with health Random(15) + 80 and food 50
    (0x427E0C, 0x427E23), below the game's full meters of 100. Owner's call
    (2026-10-29): it comes full. The roll's call becomes `mov eax, 20` (the
    stock `add eax, 80` that follows makes 100) and the food store's
    immediate 50 becomes 100.

  * Seahorses already in a save get full meters when it loads. The game
    never lowers a seahorse's health or food (its age step skips body 22 at
    0x42043F, overfeeding skips it at 0x4121F4; only feeding and one supply
    item raise them), so filling them on every load fills them once and needs
    no sidecar. The load routine 0x41AE70 reads the save into a stack buffer
    and copies it into the state (0x41AF54 push size, 0x41AF62 memcpy, which
    DS Exclusive Fish hooks). The push becomes a jump to SEAHORSE_LOAD_CAVE,
    which sets health and food to 100 in every live record of body 22 and fin
    22 in the read buffer (tanks 0-3, slots 0-30), then pushes the size and
    jumps back. Only those two dwords of those records change; the game
    writes them to the save on its next save. The cave sits in the zero tail
    of .text, so .text's VirtualSize grows to 0x3F000 as for the other
    payloads there.

Then run scripts/pin_tank_expansion.py (it rebuilds the PE checksum record
and pin of every byte-patch combination, this setting's included),
scripts/pin_ds_fish.py and scripts/pin_ds_store.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "fish_manifest.json"
EXE = "Fish Tycoon.exe"
SETTING_ID = "fix_vanilla_bugs"

SETTING = {
    "id": SETTING_ID,
    "name": "Fix Vanilla Bugs",
    "summary": (
        "Fixes stock bugs: the Plant of Incubation and Plant of Nutrition do what their names say, and the "
        "Golden Seahorse has full health and food."
    ),
    "description": (
        "Fixes bugs in the base game. The store's two plants do each other's job: the Plant of Incubation "
        "($200, \"increases the viability of purchased eggs\") actually rescues starving fish (on "
        "Random(100) <= 20 per step, food +5), and the Plant of Nutrition ($350) actually adds 1 egg to "
        "every egg batch. Their effects are swapped back: the Plant of Incubation adds the egg and the Plant "
        "of Nutrition rescues starving fish. Names, pictures and prices are unchanged, and plants already "
        "bought switch to their proper effect. The Golden Seahorse arrives with full health and a full food "
        "meter (the base game gives it health 80-94 and food 50), and a seahorse already in a save is filled "
        "up the first time the save is loaded with this setting. The game never lowers a seahorse's meters, so "
        "it stays full; nothing else about it changes."
    ),
    "category": "main",
    "default": True,
}

STARVING_CHECK = 0x4205A1     # cmp dword ptr [eax + 0x168], ebx
EGG_READS = (0x4213DB, 0x4214AA, 0x42157D)      # mov ecx, dword ptr [edi + 0x17c]
SEAHORSE_HEALTH_ROLL = 0x427E0C                 # call 0x403240 (Random(15)), then add eax, 0x50
SEAHORSE_FOOD = 0x427E2A                        # the 50 of mov dword ptr [esp + 0x80], 0x32
LOAD_PUSH_SIZE = 0x41AF54                       # push 0x1E3C8, before the memcpy into the state
LOAD_BACK = 0x41AF59                            # lea ecx, [esp + 0x120]
SEAHORSE_LOAD_CAVE = 0x43F880                   # zero tail of .text, after the other payloads
TEXT_VIRTUAL_SIZE = 0x1F8                       # .text VirtualSize: 0x3E29F -> 0x3F000
FULL_METER = 100                                # the game's cap for health and food


def offset(va: int) -> int:
    return va - 0x400000      # file offset = VA - image base


def rel32(source_end: int, target: int) -> bytes:
    return ((target - source_end) & 0xFFFFFFFF).to_bytes(4, "little")


def seahorse_load_cave() -> bytes:
    """Full meters for every live Golden Seahorse (body 22, fin 22) in the read save buffer.

    At 0x41AF54 the buffer (the state from +8) is at [esp + 0x11C], so the first fish
    record (state + 0x390) is at [esp + 0x4A4]; tanks are 0x51EC apart, records 0x288,
    31 records a tank. eax (the memcpy destination) is kept; ecx and edx are free."""
    first = 0x11C + 0x390 - 8
    full = FULL_METER.to_bytes(4, "little")
    code = bytearray()
    code += b"\x8D\x94\x24" + first.to_bytes(4, "little")                      # lea edx, [esp + 0x4A4]
    tank = len(code)
    code += b"\xB9\x1F\x00\x00\x00"                                            # mov ecx, 31
    record = len(code)
    code += b"\x83\x3A\x00" + b"\x74\x1A"                                      # cmp [edx], 0 ; je next
    code += b"\x83\x7A\x4C\x16" + b"\x75\x14"                                  # body 22?     ; jne next
    code += b"\x83\x7A\x50\x16" + b"\x75\x0E"                                  # fin 22?      ; jne next
    code += b"\xC7\x42\x3C" + full                                             # health = 100
    code += b"\xC7\x42\x44" + full                                             # food = 100
    code += b"\x81\xC2" + (0x288).to_bytes(4, "little")                        # next: add edx, 0x288
    code += b"\x49"                                                            # dec ecx
    code += b"\x75" + bytes([(record - (len(code) + 2)) & 0xFF])               # jnz record
    code += b"\x81\xC2" + (0x51EC - 31 * 0x288).to_bytes(4, "little")          # add edx, to the next tank
    code += b"\x8D\x8C\x24" + (first + 4 * 0x51EC).to_bytes(4, "little")       # lea ecx, past tank 3
    code += b"\x3B\xD1"                                                        # cmp edx, ecx
    code += b"\x72" + bytes([(tank - (len(code) + 2)) & 0xFF])                 # jb tank
    code += b"\x68\xC8\xE3\x01\x00"                                            # push 0x1E3C8 (the stock push)
    code += b"\xE9" + rel32(SEAHORSE_LOAD_CAVE + len(code) + 5, LOAD_BACK)     # jmp 0x41AF59
    return bytes(code)


def spaced(raw: bytes) -> str:
    return raw.hex(" ").upper()


# (patch id, file offset, expected, replacement, note)
VANILLA_FIXES = [
    ("fix_plant_effect_starving", offset(STARVING_CHECK), "39 98 68 01 00 00", "39 98 7C 01 00 00",
     "The starvation rescue checks the Plant of Nutrition (state + 0x17C), not the Plant of Incubation."),
] + [
    (f"fix_plant_effect_eggs_{va:X}", offset(va), "8B 8F 7C 01 00 00", "8B 8F 68 01 00 00",
     "The extra egg checks the Plant of Incubation (state + 0x168), not the Plant of Nutrition.")
    for va in EGG_READS
] + [
    ("fix_golden_seahorse_spawn_health", offset(SEAHORSE_HEALTH_ROLL), "E8 2F B4 FD FF", "B8 14 00 00 00",
     "A bought Golden Seahorse's health is 100 (mov eax, 20, then the stock add eax, 80), not Random(15) + 80."),
    ("fix_golden_seahorse_spawn_food", offset(SEAHORSE_FOOD), "32 00 00 00", "64 00 00 00",
     "A bought Golden Seahorse's food is 100, not 50."),
    ("fix_golden_seahorse_load_jump", offset(LOAD_PUSH_SIZE), "68 C8 E3 01 00",
     spaced(b"\xE9" + rel32(LOAD_PUSH_SIZE + 5, SEAHORSE_LOAD_CAVE)),
     f"Loading a save jumps to the full-meters routine at 0x{SEAHORSE_LOAD_CAVE:X} before copying it into the "
     "state; the routine does the stock push 0x1E3C8 and jumps back."),
    ("install_golden_seahorse_load_full_meters", offset(SEAHORSE_LOAD_CAVE), spaced(bytes(len(seahorse_load_cave()))),
     spaced(seahorse_load_cave()),
     "Every live Golden Seahorse (body 22, fin 22) in the save just read gets health 100 and food 100."),
    ("extend_text_virtual_size_for_fix_vanilla_bugs", TEXT_VIRTUAL_SIZE, "9F E2 03 00", "00 F0 03 00",
     ".text VirtualSize 0x3E29F -> 0x3F000 (its raw size), so the full-meters routine in the zero tail is mapped "
     "as code."),
]

# The other settings' VirtualSize records write the same value; this setting's record replaces them.
OTHER_VIRTUAL_SIZE_RECORDS = (
    "extend_text_virtual_size_for_golden_seahorse_repurchase",
    "extend_text_virtual_size_for_golden_seahorse_repurchase_with_slots",
    "extend_text_virtual_size_for_slots_payload",
)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / EXE).read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    manifest["settings"].insert(0, dict(SETTING))
    manifest["patches"] = [p for p in manifest["patches"] if SETTING_ID not in p.get("requires", [])
                           or p["id"].startswith("update_pe_checksum")]
    for patch in manifest["patches"]:
        if patch["id"] in OTHER_VIRTUAL_SIZE_RECORDS and SETTING_ID not in patch.get("excludes", []):
            patch["excludes"] = sorted(patch.get("excludes", []) + [SETTING_ID])
    for name, offset, expected, replacement, note in VANILLA_FIXES:
        raw = bytes.fromhex(expected.replace(" ", ""))
        if vanilla[offset:offset + len(raw)] != raw:
            raise SystemExit(f"{name} at 0x{offset:X}: the vanilla bytes are not {expected}")
        manifest["patches"].append({"id": name, "file_path": EXE, "offset": hex(offset), "expected": expected,
                                    "replacement": replacement, "requires": [SETTING_ID], "note": note})
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(VANILLA_FIXES)} vanilla fixes; now run pin_tank_expansion.py, pin_ds_fish.py, pin_ds_store.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
