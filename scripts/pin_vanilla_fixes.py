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
    "summary": "Fixes stock bugs: the Plant of Incubation and Plant of Nutrition do what their names say.",
    "description": (
        "Fixes bugs in the base game. The store's two plants do each other's job: the Plant of Incubation "
        "($200, \"increases the viability of purchased eggs\") actually rescues starving fish (on "
        "Random(100) <= 20 per step, food +5), and the Plant of Nutrition ($350) actually adds 1 egg to "
        "every egg batch. Their effects are swapped back: the Plant of Incubation adds the egg and the Plant "
        "of Nutrition rescues starving fish. Names, pictures and prices are unchanged, and plants already "
        "bought switch to their proper effect."
    ),
    "category": "main",
    "default": True,
}

STARVING_CHECK = 0x4205A1     # cmp dword ptr [eax + 0x168], ebx
EGG_READS = (0x4213DB, 0x4214AA, 0x42157D)      # mov ecx, dword ptr [edi + 0x17c]


def offset(va: int) -> int:
    return va - 0x400000      # file offset = VA - image base


# (patch id, file offset, expected, replacement, note)
VANILLA_FIXES = [
    ("fix_plant_effect_starving", offset(STARVING_CHECK), "39 98 68 01 00 00", "39 98 7C 01 00 00",
     "The starvation rescue checks the Plant of Nutrition (state + 0x17C), not the Plant of Incubation."),
] + [
    (f"fix_plant_effect_eggs_{va:X}", offset(va), "8B 8F 7C 01 00 00", "8B 8F 68 01 00 00",
     "The extra egg checks the Plant of Incubation (state + 0x168), not the Plant of Nutrition.")
    for va in EGG_READS
]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / EXE).read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    manifest["settings"].insert(0, dict(SETTING))
    manifest["patches"] = [p for p in manifest["patches"] if SETTING_ID not in p.get("requires", [])
                           or p["id"].startswith("update_pe_checksum")]
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
