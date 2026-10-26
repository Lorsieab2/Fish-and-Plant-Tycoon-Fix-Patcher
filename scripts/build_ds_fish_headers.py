"""Generate the DS Fish companion's C headers from the vanilla executable.

    python scripts/build_ds_fish_headers.py "<vanilla Fish Tycoon folder>"

writes native/ftfp_ds_fish/ds_sites.h and native/ftfp_ds_fish/ds_data.h.

ds_sites.h pins every place the companion writes into the game. For each site
this script disassembles the vanilla executable and requires the exact
instructions listed below, so a site that is not what the code assumes stops
the build instead of shipping. Each site's stock bytes become the bytes the
companion requires before it writes anything (all sites or none, at run
time). The bytes do not depend on which Fix Patcher settings are on: no site
here overlaps a Fix Patcher patch (checked against data/fish_manifest.json).

ds_data.h carries the tables the hooks read: the per-pair fin anchors and the
head-on extents from data/ds_fish_layout.json, the DS price tables and the
species names.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "native" / "ftfp_ds_fish"
BASE = 0x400000
EXE_SHA256 = None   # identity is the patcher's job; the instructions below pin the bytes

# (name, va, expected instructions) -- a site's length is the sum of these.
SITES = [
    # Unknown Chemical: the body / fin +-1 step (the 26% and 50/50 rolls before it are untouched).
    ("mutate_body", 0x420EFB, ["mov eax, dword ptr [edi + 0x4c]", "cmp eax, 0x14"]),
    ("mutate_fin", 0x420F27, ["mov eax, dword ptr [edi + 0x50]", "cmp eax, 0x14"]),
    # Hatch: the Magic Fish of Mutation's step of the stored mate gene, and the 0..20 clamp after it.
    ("hatch_body", 0x420180, ["mov eax, dword ptr [esi + 0x34]", "cmp dword ptr [edi + eax + 0x3a4], 0x14"]),
    ("hatch_fin", 0x4201C9, ["mov ecx, dword ptr [esi + 0x34]", "cmp dword ptr [edi + ecx + 0x3a4], 0x14"]),
    ("hatch_clamp", 0x420213, ["mov edx, dword ptr [esi + 0x34]", "mov ecx, dword ptr [edi + edx + 0x3a4]"]),
    # Baby genes: (a + b) / 2 for body and fin.
    ("breed", 0x41FAAB, ["lea eax, [edi + ebx]", "cdq", "sub eax, edx", "mov edx, dword ptr [esp + 0x2a8]",
                         "mov dword ptr [esp + 0x1c], ecx", "mov ecx, eax", "lea eax, [edx + ebp]", "cdq",
                         "sub eax, edx", "sar eax, 1", "sar ecx, 1"]),
    # Rarity tiers: health tick, disease odds, the "bred a rare fish" goal.
    ("tier_health", 0x41DF68, ["mov edx, eax", "and edx, 0x80000001"]),
    ("tier_disease", 0x41E157, ["test eax, eax", "je 0x41e1d9", "cmp eax, 4"]),
    ("tier_goal", 0x41FC0F, ["mov eax, dword ptr [esp + 0x5c]", "mov ecx, eax"]),
    # Sprites: id -> (table entry, frame); teen and dead adult sprites.
    ("decode", 0x4122A0, ["mov ecx, dword ptr [esp + 4]", "add ecx, 0xffffd8f0"]),
    ("teen", 0x41474B, ["push eax", "mov eax, dword ptr [esp + 0x34]", "push eax", "push ebx", "push 0x24",
                        "call 0x41bca0"]),
    ("dead", 0x41477E, ["mov ecx, dword ptr [esi + 0x4c]", "mov edx, dword ptr [esp + 0x24]", "push ecx",
                        "push edx", "push ebx", "push 0x25", "jmp 0x414c93"]),
    # Fins: the pair anchors after the game sets its per-body ones, and the head-on x.
    ("anchors", 0x415E3C, ["pop edi", "pop esi", "pop ebx", "ret 0xc"]),
    ("head_on_top", 0x41492A, ["mov eax, dword ptr [esp + 0x10]", "fdiv qword ptr [0x4404a8]",
                               "sub eax, dword ptr [esi + 0x68]"]),
    ("head_on_bot", 0x4149A6, ["mov eax, dword ptr [esp + 0x1c]", "sub eax, dword ptr [esi + 0x70]"]),
    # Species table: whole-table passes.
    ("count_species", 0x419240, ["push ebx", "push esi", "xor eax, eax", "push edi"]),
    ("init_prices", 0x418D6B, ["pop edi", "pop esi", "pop ebp", "pop ebx", "ret"]),
    ("build_names", 0x419839, ["pop edi", "pop esi", "pop ebp", "pop ebx", "add esp, 8", "ret"]),
    ("inflate_7", 0x420A82, ["mov dword ptr [esp + 0x10], eax", "jmp 0x420a90"]),
    ("inflate_10", 0x420AE6, ["mov dword ptr [esp + 0x10], 0"]),
    # Saves: the per-slot sidecar.
    ("save", 0x419100, ["mov edx, dword ptr [esp + 4]", "test edx, edx"]),
    ("load", 0x41AF62, ["call 0x42cb10"]),          # the save-slot path's memcpy into the state
]

# Immediates and displacements that name the sprite table (patched to the
# companion's longer copy): (name, va, instruction, value it holds).
TABLE_REFS = [
    ("tbl_free_start", 0x41BA82, "mov esi, 0x45530c", 0x45530C),
    ("tbl_free_end", 0x41BAC7, "cmp esi, 0x456ec0", 0x456EC0),
]
TABLE_FUNCS = [0x41BB05, 0x41BBD5, 0x41BCB4, 0x41BD25]   # each: bound 0xC4, then cmp/lea on 0x4552F0

INDEX_PATTERN = re.compile(r"mov (\w+), (\w+)")


def load_exe(folder: Path) -> bytes:
    return (folder / "Fish Tycoon.exe").read_bytes()


def disasm(data: bytes, va: int, count: int) -> list:
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    out = []
    for ins in md.disasm(data[va - BASE: va - BASE + 64], va):
        out.append(ins)
        if len(out) == count:
            break
    return out


def text(ins) -> str:
    return f"{ins.mnemonic} {ins.op_str}".strip()


def c_bytes(raw: bytes) -> str:
    return ", ".join(f"0x{b:02X}" for b in raw)


def branch_targets(data: bytes) -> set[int]:
    """Every direct jump/call target in .text: a site may begin at one, never contain one."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.skipdata = True
    targets = set()
    for ins in md.disasm(data[0x1000:0x3F29F], BASE + 0x1000):
        if (ins.mnemonic.startswith("j") or ins.mnemonic == "call") and ins.op_str.startswith("0x"):
            targets.add(int(ins.op_str, 16))
    return targets


def fix_patcher_ranges() -> list[tuple[int, int]]:
    manifest = json.loads((ROOT / "data" / "fish_manifest.json").read_text(encoding="utf-8"))
    ranges = []
    for patch in manifest["patches"]:
        start = int(patch["offset"], 16) + BASE
        ranges.append((start, start + len(bytes.fromhex(patch["replacement"].replace(" ", "")))))
    return ranges


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = load_exe(Path(sys.argv[1]))
    taken = fix_patcher_ranges()
    targets = branch_targets(data)
    lines = ["/* Generated by scripts/build_ds_fish_headers.py from the vanilla Fish Tycoon.exe. Do not edit. */",
             "#ifndef FTFP_DS_SITES_H", "#define FTFP_DS_SITES_H", ""]
    used: list[tuple[int, int, str]] = []

    def claim(name: str, va: int, length: int) -> None:
        for start, end in taken:
            if va < end and start < va + length:
                raise SystemExit(f"{name} at 0x{va:X} overlaps a Fix Patcher patch at 0x{start:X}")
        for start, end, other in used:
            if va < end and start < va + length:
                raise SystemExit(f"{name} at 0x{va:X} overlaps {other}")
        inside = sorted(t for t in targets if va < t < va + length)
        if inside:
            raise SystemExit(f"{name} at 0x{va:X} contains branch target(s) {[hex(t) for t in inside]}")
        used.append((va, va + length, name))

    def emit(name: str, va: int, raw: bytes) -> None:
        claim(name, va, len(raw))
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
        emit(name, va, raw)

    for name, va, expect, value in TABLE_REFS:
        ins = disasm(data, va, 1)[0]
        if text(ins) != expect:
            raise SystemExit(f"{name} at 0x{va:X}: expected {expect!r}, found {text(ins)!r}")
        raw = bytes(ins.bytes)
        at = raw.find(value.to_bytes(4, "little"))
        emit(name, va, raw)
        lines.append(f"#define SITE_{name.upper()}_IMM_AT {at}")

    for n, va in enumerate(TABLE_FUNCS):
        bound, cmp_, lea = disasm(data, va, 3)[0], None, None
        follow = disasm(data, va, 6)
        cmp_ = next(i for i in follow if "0x4552f0" in i.op_str and i.mnemonic == "cmp")
        lea = next(i for i in follow if "0x4552f0" in i.op_str and i.mnemonic == "lea")
        if not re.fullmatch(r"cmp e\w\w, 0xc4", text(bound)):
            raise SystemExit(f"sprite bound at 0x{va:X}: found {text(bound)!r}")
        for kind, ins, value in (("bound", bound, 0xC4), ("cmp", cmp_, 0x4552F0), ("lea", lea, 0x4552F0)):
            raw = bytes(ins.bytes)
            name = f"tbl_{n}_{kind}"
            emit(name, ins.address, raw)
            lines.append(f"#define SITE_{name.upper()}_IMM_AT {raw.find(value.to_bytes(4, 'little'))}")
    lines.append("#define TABLE_FUNC_COUNT 4")

    # Species-table index sites: mov R,S / shl R,5 / sub R,S  (R = S * 31).
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    text_section = data[0x1000:0x3F29F]
    index_sites = []
    for offset in range(len(text_section) - 7):
        va = BASE + 0x1000 + offset
        trio = list(md.disasm(text_section[offset: offset + 16], va))[:3]
        if len(trio) < 3:
            continue
        m = INDEX_PATTERN.fullmatch(text(trio[0]))
        if not m:
            continue
        r, s = m.groups()
        if text(trio[1]) == f"shl {r}, 5" and text(trio[2]) == f"sub {r}, {s}" and r != s:
            index_sites.append((va, r, s, b"".join(bytes(i.bytes) for i in trio)))
    if len(index_sites) != 33:
        raise SystemExit(f"expected 33 species index sites, found {len(index_sites)}")
    lines.append("")
    lines.append("/* Species-table index sites: R = S * 31, replaced by a call that returns the row for gene S. */")
    lines.append("typedef struct { unsigned int va; int reg_r; int reg_s; unsigned char expect[7]; } ds_index_site;")
    regs = ["eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"]
    lines.append(f"#define INDEX_SITE_COUNT {len(index_sites)}")
    lines.append("static const ds_index_site INDEX_SITES[INDEX_SITE_COUNT] = {")
    for va, r, s, raw in index_sites:
        if len(raw) != 7:
            raise SystemExit(f"index site 0x{va:X} is {len(raw)} bytes")
        claim(f"index_0x{va:X}", va, 7)
        lines.append(f"    {{ 0x{va:08X}u, {regs.index(r)}, {regs.index(s)}, {{ {c_bytes(raw)} }} }},  /* mov {r},{s}; shl; sub */")
    lines.append("};")
    pairs = sorted({(r, s) for _, r, s, _ in index_sites})
    lines.append("/* register pairs used: " + ", ".join(f"{r}<-{s}" for r, s in pairs) + " */")
    lines += ["", "#endif", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ds_sites.h").write_text("\n".join(lines), encoding="utf-8")
    print(f"ds_sites.h: {len(SITES)} code sites, {2 + 3 * len(TABLE_FUNCS)} table references, "
          f"{len(index_sites)} index sites; pairs {pairs}")
    write_data()
    return 0


def write_data() -> None:
    layout = json.loads((ROOT / "data" / "ds_fish_layout.json").read_text(encoding="utf-8"))
    # DS price tables (Fish Tycoon DS arm9.bin 0x0203D6C8 / 0x0203D6E4), indexed by DS index.
    body_value = [2, 10, 5, 10, 2, 14, 5, 25, 8, 10, 15, 10, 2, 18, 15, 10, 9, 10, 9, 20, 2, 10, 4, 9, 6, 10, 8, 17]
    fin_value = [2, 10, 4, 10, 2, 10, 6, 10, 6, 20, 4, 24, 2, 10, 4, 10, 6, 10, 3, 10, 2, 10, 5, 11, 3, 15, 7, 15]
    pc_bodies = ["Shark", "Catfish", "Arrowfish", "Snout", "Fatfish", "Snooper", "Goldshark", "Fire-Arrow",
                 "Fruitfish", "Flashfish", "Goldbulb", "Comet", "Stickfish", "Grouper", "Leaffish", "Carp", "Beta",
                 "Pigmy", "Bananafish", "Quicksilver", "Spotanus"]
    pc_fins = ["Silky", "Tiger", "Hornet", "Fanned", "Pink", "Snubbed", "Wasp", "Canary", "Orange", "Oriental",
               "Golden", "Crimson", "Spined", "Stubby", "Speckled", "Razorback", "Greenfin", "Great-Sail", "Flagged",
               "Finless", "Twin-Fin"]
    ds_bodies = [b["name"].replace(" ", "-") for b in layout["bodies"]]
    ds_fins = [f["name"].replace(" ", "-") for f in layout["fins"]]
    lines = ["/* Generated by scripts/build_ds_fish_headers.py. Do not edit. */",
             "#ifndef FTFP_DS_DATA_H", "#define FTFP_DS_DATA_H", "",
             "#define DS_FIRST_GENE 23", "#define DS_LAST_GENE 29", "#define DS_COUNT 7", "",
             "/* DS price values by DS index (exe gene 0-20 = DS 0-20, exe 23-29 = DS 21-27). */",
             f"static const unsigned char DS_BODY_VALUE[28] = {{ {', '.join(map(str, body_value))} }};",
             f"static const unsigned char DS_FIN_VALUE[28] = {{ {', '.join(map(str, fin_value))} }};", "",
             "/* Names by DS index; fins carry the trailing space the game's own fin names have. */",
             "static const char *const DS_BODY_NAME[28] = { " + ", ".join(f'"{n}"' for n in pc_bodies + ds_bodies) + " };",
             "static const char *const DS_FIN_NAME[28] = { " + ", ".join(f'"{n} "' for n in pc_fins + ds_fins) + " };", ""]
    # Pair anchors [body DS index][fin DS index] = top x, top y, bottom x, bottom y (0 when not a DS pair).
    table = [[[0, 0, 0, 0] for _ in range(28)] for _ in range(28)]
    ds = lambda gene: gene if gene <= 20 else gene - 2   # noqa: E731
    for row in layout["pair_anchors"]:
        table[ds(row["body"])][ds(row["fin"])] = row["anchor"]
    lines.append("/* Fin anchors for every pair with a DS gene, [body][fin] by DS index: top x, top y, bottom x, bottom y. */")
    lines.append("static const signed char DS_PAIR_ANCHOR[28][28][4] = {")
    for b in range(28):
        lines.append("    { " + ", ".join("{" + ",".join(str(v) for v in table[b][f]) + "}" for f in range(28)) + " },")
    lines.append("};")
    # Head-on extents, by DS index: frames 0,12..17; body / top / bot (left, right).
    lines.append("/* Art extents (left, right) on frames 0, 12-17, by DS index: [gene][part body/top/bot][frame][2]. */")
    lines.append("static const unsigned char DS_EXTENT[28][3][7][2] = {")
    for d in range(28):
        gene = d if d <= 20 else d + 2
        e = layout["head_on"]["extents"][str(gene)]
        lines.append("    { " + ", ".join("{" + ", ".join("{" + ",".join(str(v) for v in fr) + "}" for fr in e[p]) + "}"
                                          for p in ("body", "top", "bot")) + " },")
    lines += ["};", "", "#endif", ""]
    (OUT / "ds_data.h").write_text("\n".join(lines), encoding="utf-8")
    print("ds_data.h written")


if __name__ == "__main__":
    raise SystemExit(main())
