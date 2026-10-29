"""Pin Plant Tycoon's "Fix Vanilla Bugs" setting into the plant manifest.

    python scripts/pin_plant_vanilla_fixes.py "<vanilla Plant Tycoon folder>"

Stock bugs fixed by byte changes, each listed in records():

  * A new game can start at the Flower of Knowledge (Nox Orchid) prices. The
    new game 0x41EF30 calls the price setup 0x41DBD0 at 0x41EFB8, but clears
    the seven magic plant flags (state + 0x2180..0x2186: a dword, a word and
    a byte at 0x41F170..0x41F182) only later. The price setup gives every
    species V + 3 x (V/4) when the Flower of Knowledge flag (+0x2181) is set,
    so it reads the flag of the save loaded before the new game (the game
    loads the last save when it starts, 0x41FA10). The call at 0x41EFB8 now
    goes to a few bytes in the zero tail of .text (VA 0x464950, after the R
    key's code at 0x464930) that clear exactly those seven bytes, then jump
    to 0x41DBD0. Nothing between 0x41EFB8 and 0x41F170 reads the flags, and
    0x41F170 still clears them, so the only change is that the prices come
    from a clean state. Finding the Flower of Knowledge (0x41EB3F, then
    0x41DBD0 from 0x41EB46) is untouched. Unused Flowers.dll hooks 0x41DBD0's
    entry, so its species see the cleared flag too. Loading a save never runs
    0x41EF30 and is unchanged; saves already priced stay as they are.

The .text section's VirtualSize grows from 0x6392F to its raw size 0x64000
so the tail is mapped; "R refreshes the seed shop" makes the same change, so
this setting's copy of it applies only without that setting.

Then pin_seed_refresh.py's last step runs: every PE checksum record and every
executable pin is rebuilt for all setting combinations.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pin_seed_refresh as seed  # noqa: E402

MANIFEST = ROOT / "data" / "plant_manifest.json"
EXE = "Plant Tycoon.exe"
SETTING_ID = "fix_vanilla_bugs"

NEW_GAME_PRICE_CALL = 0x41EFB8     # call 0x41DBD0 inside the new game 0x41EF30
PRICE_SETUP = 0x41DBD0
CAVE_VA = 0x464950                 # after the R key's 32 bytes at 0x464930
FLAGS = 0x2180                     # seven magic plant flag bytes, 0x2180..0x2186

SETTING = {
    "id": SETTING_ID,
    "name": "Fix Vanilla Bugs",
    "summary": "Fixes stock bugs: a new game no longer starts at the Flower of Knowledge (Nox Orchid) prices.",
    "description": (
        "Fixes bugs in the base game. A new game sets every plant's asking price before it forgets the "
        "magic plants of the save that was open (and the game opens your last save when it starts), so "
        "after a save that has found the Flower of Knowledge (Nox Orchid), a new game prices every plant "
        "at the Flower of Knowledge price, V + 3 x (V/4), though it has not found it. The magic plants are "
        "now forgotten first, so a new game gets the normal prices; finding the Flower of Knowledge still "
        "raises them. Only new games change: saves, including ones already priced this way, stay as they are."
    ),
    "category": "main",
    "default": True,
}


def offset(va: int) -> int:
    return va - 0x400000


def cave_bytes() -> bytes:
    code = bytearray()
    code += b"\x31\xC0"                                    # xor eax, eax
    code += b"\x89\x81" + struct.pack("<I", FLAGS)         # mov [ecx+0x2180], eax  (0x2180..0x2183)
    code += b"\x89\x81" + struct.pack("<I", FLAGS + 3)     # mov [ecx+0x2183], eax  (0x2183..0x2186)
    jump_at = CAVE_VA + len(code)
    code += b"\xE9" + struct.pack("<i", PRICE_SETUP - (jump_at + 5))   # jmp 0x41DBD0 (ecx = the state)
    assert len(code) == 19
    return bytes(code)


def records(vanilla: bytes) -> list[dict]:
    hb = seed.hex_bytes
    cave = cave_bytes()
    stock_call = b"\xE8" + struct.pack("<i", PRICE_SETUP - (NEW_GAME_PRICE_CALL + 5))
    new_call = b"\xE8" + struct.pack("<i", CAVE_VA - (NEW_GAME_PRICE_CALL + 5))
    vso = seed.text_vsize_offset(vanilla)
    out = [
        {"id": "fix_new_game_knowledge_text_size", "file_path": EXE, "offset": hex(vso),
         "expected": hb(struct.pack("<I", seed.TEXT_VSIZE_OLD)),
         "replacement": hb(struct.pack("<I", seed.TEXT_VSIZE_NEW)),
         "requires": [SETTING_ID], "excludes": [seed.SETTING_ID],
         "note": "The .text section's VirtualSize, 0x6392F -> 0x64000 (its raw size), so the zero tail that "
                 "holds the new game's flag clear is mapped. R refreshes the seed shop makes the same change, "
                 "so this copy applies only without it."},
        {"id": "fix_new_game_knowledge_clear", "file_path": EXE, "offset": hex(offset(CAVE_VA)),
         "expected": hb(bytes(len(cave))), "replacement": hb(cave), "requires": [SETTING_ID],
         "note": "VA 0x464950 (the zero tail of .text): clear the seven magic plant flags, state + "
                 "0x2180..0x2186 (the bytes 0x41F170 clears later), then jump to the price setup 0x41DBD0."},
        {"id": "fix_new_game_knowledge_call", "file_path": EXE, "offset": hex(offset(NEW_GAME_PRICE_CALL)),
         "expected": hb(stock_call), "replacement": hb(new_call), "requires": [SETTING_ID],
         "note": "The new game's price setup call (0x41EFB8) goes through 0x464950, so the prices never "
                 "read the Flower of Knowledge flag of the save that was open before."},
    ]
    for record in out:
        at, raw = int(record["offset"], 16), bytes.fromhex(record["expected"].replace(" ", ""))
        if vanilla[at:at + len(raw)] != raw:
            raise SystemExit(f"{record['id']} at 0x{at:X}: the vanilla bytes are not {record['expected']}")
    return out


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / EXE).read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    manifest["settings"].insert(0, dict(SETTING))        # first, as in Fish Tycoon
    manifest["patches"] = [p for p in manifest["patches"] if SETTING_ID not in p.get("requires", [])]
    manifest["patches"] += records(vanilla)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(records(vanilla))} vanilla fix patches; rebuilding checksums and pins")
    return seed.main()


if __name__ == "__main__":
    raise SystemExit(main())
