"""Pin the "Everything is Free" cheat into the fish and plant manifests.

    python -X utf8 scripts/pin_everything_free.py "<folder holding Fish Tycoon\\ and Plant Tycoon\\>"

Every price the player pays becomes $0, in both games. Off by default, and a
cheat (``"cheat": true``, src/cheat.py): "Enable All" leaves it off.

How. Every stock store charge reads the price from one place, and each such
read is replaced in place, the same length, by a zero:

  * Fish Tycoon keeps every Supplies store price in the state's item table
    (state + 0x74 + item x 20: food, medicines, chemicals, eggs, plants,
    ornaments, Tank Two, the Golden Seahorse, and the three research lines at
    0x240 / 0x254 / 0x268). The table is read only by the store panel's price
    line (0x4274AD), the Buy click's "enough money?" test (0x428118), the
    supply-slot purchase (0x427553 and its Money Spent add, 0x427560; the
    universal-slots payload buys through it too), the permanent-item purchase
    (0x427B83 / 0x427B90), the Golden Seahorse refund when no tank has room
    (0x427EA2 / 0x427EAF, so the refund is $0 too) and the six research
    purchases (0x427600). Each read becomes "xor reg, reg". The table itself
    (saved with the game) is never written.
  * Plant Tycoon's purchase dialog (0x430950) holds the price at dialog +
    0x84: the dialog's "enough cash?" tests become "cmp reg, reg" (never too
    poor), its "Price: $%d" lines read 0, and the four Buy charges (AddCash
    with -price, 0x432D96-0x432E1D) charge 0. Seeds, the Extinct and imported
    seeds, tools, chemicals, nursery items, and everything Store Upgrades and
    Items sells through the dialog (Legendary Seeds, the formula, the potions,
    Revita-Seed, the Bomb, the Fourth to Ninth Seed Box) go through it.

The companion DLLs that sell things themselves (DS Store Items, Multiple
Ornaments, Store Upgrades and Items) read "Everything Free.ini" beside them,
which this setting ships, and then charge, show and require $0, as Free
upgrades does (Everything is Free implies it). Add Money then costs $0 and
still adds $1,000. Limits (one of each, sold out, in order, three Legendary
Seeds a day, room in a tray) are untouched: only prices change.

Every site must hold exactly the listed stock instruction, must not overlap
another setting's patch or any companion DLL's site (native/*/**_sites.h), and
the instruction after it must not read the flags the "xor" changes. Then the
PE checksum record of every byte-setting combination and every executable pin
with the setting are rebuilt; the pins without it are left exactly as they
are. Run scripts/pin_time_warp.py and scripts/pin_store_extras.py after it.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cheat  # noqa: E402
import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import plant_patcher  # noqa: E402

SETTING_ID = "everything_free"
SOURCE = "assets/everything_free"
FILE = "Everything Free.ini"
BASE = 0x400000
CHECKSUM_OFFSET = 0x150
# These settings' pins are rebuilt by pin_time_warp.py / pin_store_extras.py from the others.
REPINNED_LATER = {"time_warp", "free_upgrades", "add_money"}
TEXT = "Every store item and upgrade is free. Obviously a cheat mod, have fun!"

ZERO = {"eax": "33 C0", "ebx": "33 DB", "ecx": "33 C9", "edx": "33 D2"}
SAME = {"edx": "3B D2", "ecx": "3B C9"}

# (va, the stock instruction, what it becomes, why)
FISH_SITES: list[tuple[int, str, str, str]] = [
    (0x4274AD, "mov eax, dword ptr [edx + ecx*4 + 0x74]", "zero eax",
     "the store panel's price line ('%s  $%d', 0x4274C3): $0"),
    (0x428118, "mov ebx, dword ptr [edx + eax + 0x74]", "zero ebx",
     "the Buy click's money test (0x42811C, price > money): never too little money"),
    (0x427553, "mov edx, dword ptr [ecx + eax + 0x74]", "zero edx",
     "a supply-slot item (food, medicine, chemical, eggs; 0x427540): $0 taken from the money"),
    (0x427560, "mov eax, dword ptr [ecx + eax + 0x74]", "zero eax",
     "the same purchase's Money Spent: + $0"),
    (0x427B83, "mov edx, dword ptr [eax + edi + 0x74]", "zero edx",
     "a permanent item (plants, ornaments, Tank Two, the Golden Seahorse; 0x427B30): $0 taken"),
    (0x427B90, "mov edx, dword ptr [eax + edi + 0x74]", "zero edx",
     "the same purchase's Money Spent: + $0"),
    (0x427EA2, "mov edx, dword ptr [eax + edi + 0x74]", "zero edx",
     "the Golden Seahorse refund when no tank has room: $0 back (it cost $0)"),
    (0x427EAF, "mov ecx, dword ptr [eax + edi + 0x74]", "zero ecx",
     "the same refund's Money Spent: - $0"),
]
for _va, _field, _what in ((0x42764E, 0x268, "Fish Environment level 1"), (0x42765D, 0x268, None),
                           (0x427684, 0x268, "Fish Environment level 2"), (0x427693, 0x268, None),
                           (0x4276CC, 0x254, "Advertising level 1"), (0x4276DB, 0x254, None),
                           (0x427702, 0x254, "Advertising level 2"), (0x427711, 0x254, None),
                           (0x427743, 0x240, "Fish Health level 1"), (0x427752, 0x240, None),
                           (0x42776D, 0x240, "Fish Health level 2"), (0x42777C, 0x240, None)):
    FISH_SITES.append((_va, f"mov edx, dword ptr [eax + 0x{_field:x}]", "zero edx",
                       f"research (0x427600), {_what}: $0 taken" if _what else "the same research's Money Spent: + $0"))

PLANT_SITES: list[tuple[int, str, str, str]] = []
for _va in (0x430A9C, 0x430BF7, 0x430D13, 0x430DF9):
    PLANT_SITES.append((_va, "cmp edx, dword ptr [esi + 0x84]", "same edx",
                        "the purchase dialog's cash test (cash < price?): never too poor"))
PLANT_SITES += [
    (0x431570, "cmp edx, edi", "cmp edi, edi",
     "the tool dialog's cash test (price > cash?): never too poor"),
    (0x432170, "cmp edx, dword ptr [ecx + 0x217c]", "same edx",
     "the nursery-item dialog's cash test (price > cash?): never too poor"),
    (0x43273F, "cmp ecx, dword ptr [eax + 0x217c]", "same ecx",
     "the chemical dialog's cash test (price > cash?): never too poor"),
]
for _va, _reg in ((0x430B07, "eax"), (0x430C62, "eax"), (0x430D7D, "eax"), (0x4310D3, "eax"), (0x43142B, "ecx"),
                  (0x431668, "eax"), (0x4318BE, "eax"), (0x431A93, "ecx"), (0x431C9C, "edx"), (0x431E91, "eax"),
                  (0x432083, "eax"), (0x432262, "eax"), (0x432455, "eax"), (0x432644, "eax"), (0x43282E, "edx"),
                  (0x432A25, "eax"), (0x432C18, "eax")):
    PLANT_SITES.append((_va, f"mov {_reg}, dword ptr [esi + 0x84]", f"zero {_reg}",
                        "the purchase dialog's 'Price: $%d' (0x4653BC into dialog + 0xA9): $0"))
for _va, _reg, _what in ((0x432D96, "ecx", "a seed packet"), (0x432DB3, "edx", "a nursery item"),
                         (0x432DE8, "edx", "a tool"), (0x432E1D, "edx", "a chemical")):
    PLANT_SITES.append((_va, f"mov {_reg}, dword ptr [ebp + 0x84]", f"zero {_reg}",
                        f"Buy, {_what}: AddCash(-price) (0x41ED70) with price $0"))

GAMES = {
    "fish": {
        "manifest": ROOT / "data" / "fish_manifest.json",
        "exe": "Fish Tycoon.exe",
        "folder": "Fish Tycoon Fix Patcher DLLs",
        "sites": FISH_SITES,
        "dlls": ["ftfp_ds_fish", "ftfp_ds_store", "ftfp_ornaments", "ftfp_extra_tanks", "ftfp_supply_slots"],
        "after": "add_money",
    },
    "plant": {
        "manifest": ROOT / "data" / "plant_manifest.json",
        "exe": "Plant Tycoon.exe",
        "folder": "Plant Tycoon Fix Patcher DLLs",
        "sites": PLANT_SITES,
        "dlls": ["ftfp_plant_upgrades", "ftfp_seed_boxes", "ftfp_new_flowers", "ftfp_extra_greenhouses",
                 "ftfp_chem_slots"],
        "after": "add_money",
    },
}

# The DLLs that sell something themselves and read the setting's file.
READERS = {
    "fish": {"ds_store": "assets/fish_tycoon_ds_store/DS Store Items.dll",
             "multiple_ornaments": "assets/fish_tycoon_ornaments/Multiple Ornaments.dll"},
    "plant": {"plant_upgrades": "assets/plant_tycoon_upgrades/Store Upgrades and Items.dll"},
}

FLAG_READERS = re.compile(r"^(j(?!mp)|set|cmov|adc|sbb|pushf|lahf|rc[lr])")
FLAG_WRITERS = {"add", "sub", "cmp", "test", "xor", "and", "or", "neg", "inc", "dec", "imul", "shl", "shr", "sar"}
ENDS = {"call", "ret", "jmp"}


def setting() -> dict:
    return cheat.mark({
        "id": SETTING_ID,
        "name": "Everything is Free",
        "summary": TEXT,
        "description": TEXT,
        "category": "main",
        "default": False,
    })


def hex_bytes(raw: bytes) -> str:
    return " ".join(f"{b:02X}" for b in raw)


def replacement(how: str, length: int) -> bytes:
    kind, reg = how.split(" ", 1)
    if kind == "zero":
        head = bytes.fromhex(ZERO[reg])
    elif kind == "same":
        head = bytes.fromhex(SAME[reg])
    elif how == "cmp edi, edi":
        head = b"\x3B\xFF"
    else:
        raise ValueError(how)
    return head + b"\x90" * (length - len(head))


def dll_ranges(projects: list[str]) -> list[tuple[int, int, str]]:
    ranges = []
    for project in projects:
        for header in (ROOT / "native" / project).glob("*sites.h"):
            text = header.read_text(encoding="utf-8")
            vas = dict(re.findall(r"#define (?:SITE|SLOT)_(\w+)_VA (0x[0-9A-Fa-f]+)u?", text))
            lens = dict(re.findall(r"#define SITE_(\w+)_LEN (\d+)", text))
            for name, va in vas.items():
                start = int(va, 16)
                ranges.append((start, start + int(lens.get(name, 4)), f"{project} {name}"))
    return ranges


def check_sites(data: bytes, game: dict, manifest: dict) -> list[dict]:
    import capstone                     # only here: CI has no capstone, and the tests import this module

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    taken = []
    for p in manifest["patches"]:
        if SETTING_ID in p.get("requires", []) or p["id"].startswith("update_pe_checksum"):
            continue
        start = int(p["offset"], 16) + BASE
        taken.append((start, start + len(p["replacement"].split()), p["id"]))
    taken += dll_ranges(game["dlls"])
    records, used = [], []
    for va, expect, how, why in game["sites"]:
        ins = list(md.disasm(data[va - BASE: va - BASE + 96], va))
        got = f"{ins[0].mnemonic} {ins[0].op_str}"
        if got != expect:
            raise SystemExit(f"0x{va:X}: expected '{expect}', found '{got}'")
        raw = bytes(ins[0].bytes)
        for start, end, other in taken + used:
            if va < end and start < va + len(raw):
                raise SystemExit(f"0x{va:X} overlaps {other} at 0x{start:X}")
        if how.startswith("zero"):          # the xor changes the flags: nothing after may read them first
            for nxt in ins[1:]:
                if FLAG_READERS.match(nxt.mnemonic):
                    raise SystemExit(f"0x{va:X}: {nxt.mnemonic} at 0x{nxt.address:X} reads the flags")
                if nxt.mnemonic in FLAG_WRITERS or nxt.mnemonic in ENDS:
                    break
            else:
                raise SystemExit(f"0x{va:X}: no flag writer within 96 bytes")
        new = replacement(how, len(raw))
        used.append((va, va + len(raw), f"site 0x{va:X}"))
        records.append({
            "id": f"everything_free_{va:06x}",
            "file_path": game["exe"],
            "offset": hex(va - BASE),
            "expected": hex_bytes(raw),
            "replacement": hex_bytes(new),
            "requires": [SETTING_ID],
            "note": f"VA 0x{va:X} '{expect}' -> '{how.replace('zero ', 'xor ').replace('same ', 'cmp ')}': {why}.",
        })
    return records


def byte_settings(manifest: dict) -> list[str]:
    return sorted({r for p in manifest["patches"] if not p["id"].startswith("update_pe_checksum")
                   for r in p.get("requires", [])})


def checksum(data: bytes) -> str:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert pe + 88 == CHECKSUM_OFFSET, hex(pe + 88)
    value = ds_fish_loader.pe_checksum(data[:pe + 88] + b"\0\0\0\0" + data[pe + 92:])
    return hex_bytes(struct.pack("<I", value))


def companion() -> dict:
    data = (ROOT / SOURCE / FILE).read_bytes()
    return {"source": SOURCE, "files": [{
        "path": FILE, "destination": f"{{folder}}/{FILE}",
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}]}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1])
    for game_id, game in GAMES.items():
        patcher = fish_patcher if game_id == "fish" else plant_patcher
        vanilla_dir = folder / ("Fish Tycoon" if game_id == "fish" else "Plant Tycoon")
        vanilla = (vanilla_dir / game["exe"]).read_bytes()
        manifest = json.loads(game["manifest"].read_text(encoding="utf-8"))

        # The DLLs that read the setting's file were rebuilt: their records follow.
        for sid, path in READERS[game_id].items():
            entry = next(s for s in manifest["settings"] if s["id"] == sid)
            data = (ROOT / path).read_bytes()
            name = Path(path).name
            for record in entry["companion"]["files"]:
                if record["path"] == name:
                    record["size"] = len(data)
                    record["sha256"] = hashlib.sha256(data).hexdigest().upper()

        entry = setting()
        comp = companion()
        comp["files"][0]["destination"] = comp["files"][0]["destination"].format(folder=game["folder"])
        entry["companion"] = comp
        ids = [s["id"] for s in manifest["settings"]]
        if SETTING_ID in ids:
            manifest["settings"][ids.index(SETTING_ID)] = entry
        else:
            manifest["settings"].insert(ids.index(game["after"]) + 1, entry)

        manifest["patches"] = [p for p in manifest["patches"]
                               if SETTING_ID not in p.get("requires", []) or p["id"].startswith("update_pe_checksum")]
        records = check_sites(vanilla, game, manifest)
        manifest["patches"] = [p for p in manifest["patches"] if not p["id"].startswith("update_pe_checksum")]
        manifest["patches"] += records

        settings = byte_settings(manifest)
        vanilla_sum = hex_bytes(vanilla[CHECKSUM_OFFSET:CHECKSUM_OFFSET + 4])
        for count in range(1, len(settings) + 1):
            for combo in itertools.combinations(settings, count):
                patched, _ = patcher.apply_patch_bytes(vanilla, patcher.active_patch_records(manifest, set(combo)))
                manifest["patches"].append({
                    "id": "update_pe_checksum_" + "_".join(combo), "file_path": game["exe"],
                    "offset": hex(CHECKSUM_OFFSET), "expected": vanilla_sum, "replacement": checksum(patched),
                    "requires": list(combo), "excludes": [s for s in settings if s not in combo],
                    "note": f"PE optional-header CheckSum, recomputed for this exact combination ({', '.join(combo)}).",
                })

        old = manifest["patched_sha256_by_settings"]
        pins = {k: v for k, v in old.items() if SETTING_ID not in k.split(",")}
        added = 0
        for key in [""] + list(pins):
            enabled = set(key.split(",")) - {""}
            if enabled & REPINNED_LATER:
                continue
            enabled.add(SETTING_ID)
            patched, _ = patcher.apply_patch_bytes(vanilla, patcher.active_patch_records(manifest, enabled))
            if fish_patcher.needs_startup_loader(manifest, enabled):
                profile = (ds_fish_loader.fish_profile if game_id == "fish" else ds_fish_loader.plant_profile)(enabled)
                patched, _ = ds_fish_loader.append_startup_loader(patched, profile)
            new_key = patcher.settings_key(enabled) if game_id == "fish" else patcher.settings_key(enabled, manifest)
            pins[new_key] = hashlib.sha256(patched).hexdigest().upper()
            added += 1
        # Every pin without the setting is unchanged (its checksum record kept its value).
        for key, value in old.items():
            if SETTING_ID not in key.split(","):
                assert pins[key] == value, key
        manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(), key=lambda kv: (len(kv[0].split(",")), kv[0])))
        game["manifest"].write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{game_id}: {len(records)} patches, {2 ** len(settings) - 1} checksum records, {added} pins with the setting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
