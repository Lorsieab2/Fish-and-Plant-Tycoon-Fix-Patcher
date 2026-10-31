"""Generate the DS Store companion's C headers from the vanilla executable.

    python scripts/build_ds_store_headers.py "<vanilla Fish Tycoon folder>"

writes native/ftfp_ds_store/store_sites.h and native/ftfp_ds_store/store_data.h.

store_sites.h pins every place the store companion writes into the game, the
same way scripts/build_ds_fish_headers.py does for DS Fish: each code site is
disassembled from the vanilla executable and must hold exactly the listed
instructions, may begin at a branch target but never contain one, and must
not overlap a Fix Patcher patch (data/fish_manifest.json) or a DS Fish site
(native/ftfp_ds_fish/ds_sites.h). The four store vtable slots are pinned by
the function address each holds.

store_data.h carries the art sizes from data/ds_store_layout.json.
"""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_ds_fish_headers import BASE, branch_targets, c_bytes, disasm, fix_patcher_ranges, load_exe, text  # noqa: E402

OUT = ROOT / "native" / "ftfp_ds_store"

# (name, va, expected instructions)
SITES = [
    # Companions: the stage-3 (seahorse) draw picks each animal's own sheet. It stops
    # short of 0x414C93, which the dead-fish draw jumps to.
    ("draw_companion", 0x414C8A, ["mov edx, dword ptr [esp + 0x24]", "push eax", "push edx", "push ebx",
                                  "push 0x65"]),
    # Effects: the per-step health tick call, and the death test (the eel's save).
    ("tick", 0x420470, ["call 0x41df50"]),
    ("death", 0x420622, ["mov edx, dword ptr [esi + 0x34]", "cmp dword ptr [edi + edx + 0x3cc], ebx"]),
    # Selling tank: customers and thought bubbles skip every seahorse-type companion.
    ("customers", 0x42426F, ["cmp dword ptr [esi + ebx + 0xa774], 0x14", "jl 0x42448a"]),
    ("thoughts", 0x41355F, ["cmp dword ptr [edx + 0xa774], 0x14", "jl 0x413622"]),
    # Exotic Fish Eggs: the egg switch, and the stock "Replace eggs in slot #4?" test.
    ("egg_use", 0x421356, ["mov edx, dword ptr [esi + 0x34]", "mov eax, dword ptr [edx + 0x30c]"]),
    ("egg_confirm", 0x4281AF, ["cmp ecx, 0xac", "jne 0x4281d6"]),
    # Radioactive Growth Hormone: the chemical switch, and the stock "Replace chemical in slot #3?" test.
    ("chem_use", 0x420E6F, ["mov ecx, dword ptr [esi + 0x34]", "mov eax, dword ptr [ecx + 0x2f0]", "sub eax, 2"]),
    ("chem_confirm", 0x428189, ["cmp ecx, 0xaa", "jne 0x4281d6"]),
    # The eel's rock: drawn with the ornaments; the eel goes home on a drop, out on a click.
    ("ornaments", 0x41EF1B, ["jmp 0x41d600"]),
    ("fish_drop", 0x41F064, ["mov ecx, dword ptr [esi + 0x34]", "mov eax, dword ptr [ecx + 0x384]"]),
    ("ornament_pick", 0x41E570, ["mov eax, dword ptr [ecx + 0x34]", "mov edx, dword ptr [eax + 0x384]"]),
    # The animals live in each tank's spare fish records, slots 26-30: the Golden Seahorse's stock
    # placement, new game (clear them), the fish trash (the eel's rock goes with it) and the ornament
    # drop (the rock in the trash, with its eel).
    ("seahorse_place", 0x427E43, ["mov ecx, dword ptr [esi + 0x10]", "lea edx, [esp + 0x3c]"]),
    ("new_game_clear", 0x41AACA, ["call 0x4198f0"]),
    ("fish_trash", 0x41E809, ["mov ecx, dword ptr [esi + 0x34]", "push ebx", "push edi"]),
    ("ornament_drop", 0x41F660, ["push ebx", "push ebp", "mov ebp, dword ptr [esp + 0x10]", "push esi",
                                 "mov esi, ecx"]),
    # The tank's info panel asks the species table for the held fish's name; seahorse-type
    # animals have none there, so the DLL names them.
    ("held_name", 0x41DA0A, ["call 0x419290"]),
    # The animals live in the DLL's own records (saved in "Tank Animals <slot>.dat"): the two loops
    # that build and refresh the swimming fish (the view) go on from the last fish slot to the
    # tank's animals at their `jl` back to the top (the bound itself, 21 or 30 with "Bigger tanks",
    # stays the setting's), and the state's Save(slot) writes the animals' file first.
    ("view_build_next", 0x4140D0, ["jl 0x413dc4"]),
    ("view_refresh_next", 0x41589E, ["jl 0x415533"]),
    ("save_call_game", 0x41A663, ["call 0x419100"]),
    ("save_call_settings", 0x41A66B, ["call 0x419100"]),
    # The release of a held supply (0x421B20 calls the use 0x420B70): the store's own supplies
    # let go on the trash can are thrown away.
    ("supply_drop", 0x421B52, ["call 0x420b70"]),
    # The Auto-Feeder and Auto-Healer: each fish's age step, right after its sickness roll
    # (0x41E120, adults only) and before the sickness costs it a pregnancy (0x4204EE), its food
    # drops and the starvation test (0x42055E).
    ("auto_step", 0x4204B3, ["mov edx, dword ptr [esi + 0x34]", "cmp dword ptr [edi + edx + 0x3d0], ebx"]),
    # The feeding's overfeeding test (a fish whose food passed 100): with the Auto-Feeder owned no
    # fish loses health there, as the seahorse never does.
    ("overfeed", 0x4121F4, ["cmp dword ptr [edx + ebx + 0x3dc], 0x16", "je 0x41220d"]),
    # The sale roll's call of the sale itself (0x424010: price, money, "fish sold", the sold fish's
    # picture and price, REMOVE_FISH(2, slot)), its only caller: a fish treated with the Radioactive
    # Growth Hormone is sold for its species' highest selling price.
    ("sale", 0x4244D4, ["call 0x424010"]),
]

# The Supplies scene's vtable (0x44C294): slot address -> the function it holds.
VTABLE = [
    ("vt_mouse", 0x44C298, 0x427980),
    ("vt_command", 0x44C2A0, 0x428300),
    ("vt_overlay", 0x44C2B0, 0x41B5F0),
    ("vt_activate", 0x44C2B8, 0x427960),
    ("state_load", 0x4424D0, 0x41AE70),            # the state's vtable: Load(slot)
    ("state_save", 0x4424D4, 0x419100),            # and Save(slot)
]


def ds_fish_ranges() -> list[tuple[int, int, str]]:
    header = (ROOT / "native" / "ftfp_ds_fish" / "ds_sites.h").read_text(encoding="utf-8")
    vas = dict(re.findall(r"#define SITE_(\w+)_VA (0x[0-9A-F]+)u", header))
    lens = dict(re.findall(r"#define SITE_(\w+)_LEN (\d+)", header))
    ranges = [(int(vas[k], 16), int(vas[k], 16) + int(lens[k]), f"DS Fish {k}") for k in vas]
    for va in re.findall(r"\{ (0x[0-9A-F]+)u, \d, \d,", header):
        ranges.append((int(va, 16), int(va, 16) + 7, f"DS Fish index {va}"))
    if len(ranges) < 60:
        raise SystemExit("native/ftfp_ds_fish/ds_sites.h looks incomplete; regenerate it first")
    return ranges


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = load_exe(Path(sys.argv[1]))
    taken = [(s, e, "a Fix Patcher patch") for s, e in fix_patcher_ranges()] + ds_fish_ranges()
    targets = branch_targets(data)
    used: list[tuple[int, int, str]] = []
    lines = ["/* Generated by scripts/build_ds_store_headers.py from the vanilla Fish Tycoon.exe. Do not edit. */",
             "#ifndef FTFP_STORE_SITES_H", "#define FTFP_STORE_SITES_H", ""]

    def claim(name: str, va: int, length: int, code: bool) -> None:
        for start, end, other in taken + used:
            if va < end and start < va + length:
                raise SystemExit(f"{name} at 0x{va:X} overlaps {other} at 0x{start:X}")
        if code:
            inside = sorted(t for t in targets if va < t < va + length)
            if inside:
                raise SystemExit(f"{name} at 0x{va:X} contains branch target(s) {[hex(t) for t in inside]}")
        used.append((va, va + length, name))

    def emit(name: str, va: int, raw: bytes, code: bool) -> None:
        claim(name, va, len(raw), code)
        upper = name.upper()
        lines.append(f"#define SITE_{upper}_VA 0x{va:08X}u")
        lines.append(f"#define SITE_{upper}_LEN {len(raw)}")
        lines.append(f"static const unsigned char SITE_{upper}_EXPECT[] = {{ {c_bytes(raw)} }};")

    for name, va, expect in SITES:
        got = disasm(data, va, len(expect))
        if [text(i) for i in got] != expect:
            raise SystemExit(f"{name} at 0x{va:X}: expected {expect}, found {[text(i) for i in got]}")
        raw = b"".join(bytes(i.bytes) for i in got)
        if len(raw) < 5:
            raise SystemExit(f"{name} at 0x{va:X} is {len(raw)} bytes; a jump needs 5")
        emit(name, va, raw, True)

    for name, va, holds in VTABLE:
        raw = data[va - BASE: va - BASE + 4]
        if struct.unpack("<I", raw)[0] != holds:
            raise SystemExit(f"{name} at 0x{va:X}: expected 0x{holds:X}, found 0x{struct.unpack('<I', raw)[0]:X}")
        emit(name, va, raw, False)
        lines.append(f"#define SITE_{name.upper()}_HOLDS 0x{holds:08X}u")

    lines += ["", "#endif", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "store_sites.h").write_text("\n".join(lines), encoding="utf-8")
    print(f"store_sites.h: {len(SITES)} code sites, {len(VTABLE)} vtable slots")
    write_data()
    return 0


def write_data() -> None:
    layout = json.loads((ROOT / "data" / "ds_store_layout.json").read_text(encoding="utf-8"))
    c = layout["companions"]
    home = layout["eel_home"]
    lines = ["/* Generated by scripts/build_ds_store_headers.py from data/ds_store_layout.json. Do not edit. */",
             "#ifndef FTFP_STORE_DATA_H", "#define FTFP_STORE_DATA_H", "",
             f"#define UPGRADES_X {layout['button'][0]}",
             f"#define UPGRADES_Y {layout['button'][1]}", "",
             "/* Companion sheet cells (6 x 3, frames 0-17), in fin-marker order 30, 31, 32. */",
             "static const int COMPANION_CELL[3][2] = { "
             + ", ".join(f"{{ {c[k]['cell'][0]}, {c[k]['cell'][1]} }}" for k in ("PUFFER", "STINGRAY", "EEL")) + " };",
             "",
             f"#define ROCK_W {home['cell'][0]}",
             f"#define ROCK_H {home['cell'][1]}",
             f"#define HOME_COLS {home['cols']}",
             f"#define HOME_FRAMES {home['frames']}",
             "/* The sheet holds the idle frames, then the action burst (it ends with the bite). */",
             f"#define HOME_IDLE {home['idle']}",
             f"#define HOME_ACTION {home['action']}",
             "/* Where the eel's head shows at home, in rock coordinates: left, top, right, bottom. */",
             "static const int HEAD_BOX[4] = { " + ", ".join(str(v) for v in home["head_box"]) + " };",
             "", "#endif", ""]
    (OUT / "store_data.h").write_text("\n".join(lines), encoding="utf-8")
    print("store_data.h written")


if __name__ == "__main__":
    raise SystemExit(main())
