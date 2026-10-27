"""Pin the "Fix Vanilla Bugs" setting into the fish manifest.

    python scripts/pin_vanilla_fixes.py "<vanilla Fish Tycoon folder>"

Stock bugs fixed by data changes alone, each listed in VANILLA_FIXES:

  * The two store plants' labels are swapped. Store record 12 ($200) is
    named "Plant of Incubation" ("...increases the viability of purchased
    eggs"), but its ownership dword (state + 0x168) is read only by the
    starvation code (0x4205A1: a starving fish gets food +5 on
    Random(100) <= 20). Record 13 ($350) is named "Plant of Nutrition", but
    its dword (state + 0x17C) is read by the three egg-hatch paths
    (0x4213DB, 0x4214AA, 0x42157D: +1 egg per batch). The records' name and
    description string IDs (+0x2C, +0x30 of each 0x34-byte record in the
    static store table at 0x457EF0) are swapped, so each plant is named for
    what it does. Prices, pictures and effects stay with the record. The
    store reads the table in place (0x4271AC), so saves need no change.

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
STORE_TABLE = 0x457EF0
RECORD = 0x34
NAME_IDS = 0x2C          # name string ID, then the description's

SETTING = {
    "id": SETTING_ID,
    "name": "Fix Vanilla Bugs",
    "summary": "Fixes stock bugs: the Plant of Incubation and Plant of Nutrition store labels are swapped back.",
    "description": (
        "Fixes bugs in the base game. The store's two plants have each other's name and description: the "
        "plant sold as \"Plant of Incubation\" ($200) actually rescues starving fish (on Random(100) <= 20 "
        "per step, food +5), and the one sold as \"Plant of Nutrition\" ($350) actually adds 1 egg to every "
        "egg batch. Each is now named and described for what it does: the $200 plant is the Plant of "
        "Nutrition and the $350 plant the Plant of Incubation. Prices, pictures and effects are unchanged, "
        "and plants already bought keep working as before."
    ),
    "category": "main",
    "default": True,
}


def record_ids(index: int) -> int:
    return STORE_TABLE + index * RECORD + NAME_IDS - 0x400000      # file offset = VA - image base


def ids_hex(name: int, description: int) -> str:
    return " ".join(f"{b:02X}" for b in name.to_bytes(4, "little") + description.to_bytes(4, "little"))


# (patch id, file offset, expected, replacement, note)
VANILLA_FIXES = [
    ("fix_plant_labels_12", record_ids(12), ids_hex(198, 199), ids_hex(200, 201),
     "Store record 12 ($200, the starvation rescue) gets the Plant of Nutrition's name and description."),
    ("fix_plant_labels_13", record_ids(13), ids_hex(200, 201), ids_hex(198, 199),
     "Store record 13 ($350, +1 egg per batch) gets the Plant of Incubation's name and description."),
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
