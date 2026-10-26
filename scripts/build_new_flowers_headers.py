"""Generate the New Flowers companion's C headers from the vanilla Plant Tycoon.exe.

    python scripts/build_new_flowers_headers.py "<vanilla Plant Tycoon folder>"

writes native/ftfp_new_flowers/flower_sites.h and flower_stubs.h.

flower_sites.h pins every place the companion writes into the game, the same
way scripts/build_ds_fish_headers.py does for Fish Tycoon. Each site is
disassembled from the vanilla executable and must hold exactly the listed
instructions. A site may begin at a branch target but never contain one, and
must not overlap a Fix Patcher patch (data/plant_manifest.json). The stock
bytes become the bytes the DLL requires before it writes anything (all
sites or none, at run time).

flower_stubs.h holds one naked stub per species-table index site: the 15
places that compute `(foliage + K) * 26 + flower` to read or write a
species' value V (K = 0x1D) or asking price P (K = 0x37). Each stub replays
the game's three instructions, then lets the DLL swap the index for a
flower 24-37, so the game's own read or write lands in the DLL's table.
"""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "native" / "ftfp_new_flowers"
BASE = 0x400000

# (name, va, expected instructions)
SITES = [
    ("art_lookup", 0x42D2D0, ["push esi", "mov esi, dword ptr [esp + 8]"]),
    ("vp_comments", 0x439A1F, ["lea ebp, [edx + 0x37]", "add edx, 0x1d", "imul ebp, ebp, 0x1a",
                               "imul edx, edx, 0x1a", "add edx, ecx", "mov edx, dword ptr [eax + edx*4]",
                               "add ebp, ecx", "mov ecx, dword ptr [esp + 0x14]",
                               "mov ebp, dword ptr [eax + ebp*4]"]),
    ("name", 0x4286E2, ["lea ecx, [eax + ecx + 0x540cc]"]),
    ("discover_mutation", 0x426F0B, ["lea ecx, [ecx + ecx*2]", "lea ecx, [edx + ecx*8]",
                                     "mov byte ptr [ecx + eax + 0x64], 1"]),
    ("discover_age", 0x42E2BB, ["lea edx, [ecx + ecx*2]", "lea ecx, [eax + edx*8]", "mov edx, dword ptr [esi + 0xc]",
                                "mov byte ptr [ecx + edx + 0x64], 1"]),
    ("discovered_count", 0x44C5A1, ["mov edx, dword ptr [esi + 0x60]", "push edx", "lea eax, [esp + 0x38]"]),
    ("price_setup", 0x41DBD0, ["sub esp, 8", "push ebx", "push ebp"]),
    ("new_game", 0x41EF30, ["push ebx", "push esi", "push edi", "xor ebx, ebx"]),
    ("save", 0x41D120, ["mov edx, dword ptr [esp + 4]", "test edx, edx"]),
    ("load", 0x41EE00, ["mov eax, 0x54074"]),
    ("delete", 0x41D1F0, ["jmp 0x403650"]),
    # The tail of a pot's pollination (esi = its record): new-flower breeding, then the
    # Upgrades DLL's seed handling.
    ("pollinated", 0x4241B4, ["pop edi", "pop esi", "pop ebp", "pop ebx", "ret 8"]),
]

# One-byte or one-dword immediates: (name, va, instruction, value, new value).
IMMEDIATES = [
    ("draw_bound", 0x42D9CD + 3, "cmp eax, 0x16", 0x16, 0x24),            # flowers 1..37 are drawn
    ("flowering_bound", 0x42E38F + 3, "cmp ecx, 0x16", 0x16, 0x24),       # and grow flowers
    ("mutation_top", 0x42FACC, "cmp eax, 0x17", 0x17, 0x25),              # Mutation Liquid: above 37 ...
    ("mutation_bounce", 0x42FAD2, "mov dword ptr [esi + 0x50], 0x16", 0x16, 0x24),   # ... becomes 36
]

# Species-table index sites: (va, family "P" or "V", the consumer's state register).
INDEX_SITES = [
    (0x428718, "P", "eax"), (0x4304EA, "P", "ecx"), (0x4305AE, "P", "edi"), (0x43060C, "P", "eax"),
    (0x4306C4, "P", "eax"), (0x435CE5, "P", "eax"), (0x435D05, "P", "ecx"), (0x4366E9, "P", "ecx"),
    (0x436D3A, "P", "edx"), (0x437E5C, "P", "ecx"),
    (0x436E8A, "V", "eax"), (0x436EDA, "V", "ecx"), (0x436F05, "V", "ecx"), (0x436FA8, "V", "ecx"),
    (0x436FD1, "V", "ecx"),
]
PUSHAD_OFFSET = {"eax": 28, "ecx": 24, "edx": 20, "ebx": 16, "ebp": 8, "esi": 4, "edi": 0}


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
    """Every direct jump/call target, and every dword in the image that points into .text
    (jump tables): a site may begin at one, never contain one."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.skipdata = True
    targets = set()
    text_end = 0x465000
    for ins in md.disasm(data[0x1000:text_end - BASE], BASE + 0x1000):
        if (ins.mnemonic.startswith("j") or ins.mnemonic in ("call", "loop")) and ins.op_str.startswith("0x"):
            targets.add(int(ins.op_str, 16))
    for off in range(0x1000, len(data) - 4, 4):
        v = struct.unpack_from("<I", data, off)[0]
        if 0x401000 <= v < text_end:
            targets.add(v)
    return targets


def fix_patcher_ranges() -> list[tuple[int, int]]:
    manifest = json.loads((ROOT / "data" / "plant_manifest.json").read_text(encoding="utf-8"))
    ranges = []
    for patch in manifest.get("patches", []):
        start = int(patch["offset"], 16) + BASE
        ranges.append((start, start + len(bytes.fromhex(patch["replacement"].replace(" ", "")))))
    return ranges


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = (Path(sys.argv[1]) / "Plant Tycoon.exe").read_bytes()
    taken = fix_patcher_ranges()
    targets = branch_targets(data)
    used: list[tuple[int, int, str]] = []
    lines = ["/* Generated by scripts/build_new_flowers_headers.py from the vanilla Plant Tycoon.exe. Do not edit. */",
             "#ifndef FTFP_FLOWER_SITES_H", "#define FTFP_FLOWER_SITES_H", ""]

    def claim(name: str, va: int, length: int, inner_ok: bool = False) -> None:
        for start, end in taken:
            if va < end and start < va + length:
                raise SystemExit(f"{name} at 0x{va:X} overlaps a Fix Patcher patch at 0x{start:X}")
        for start, end, other in used:
            if va < end and start < va + length:
                raise SystemExit(f"{name} at 0x{va:X} overlaps {other}")
        if not inner_ok:
            inside = sorted(t for t in targets if va < t < va + length)
            if inside:
                raise SystemExit(f"{name} at 0x{va:X} contains branch target(s) {[hex(t) for t in inside]}")
        used.append((va, va + length, name))

    def emit(name: str, va: int, raw: bytes) -> None:
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
        claim(name, va, len(raw))
        emit(name, va, raw)
        lines.append(f"#define SITE_{name.upper()}_BACK 0x{va + len(raw):08X}u")

    for name, va, expect, value, new in IMMEDIATES:
        ins = disasm(data, va, 1)[0]
        if text(ins) != expect:
            raise SystemExit(f"{name} at 0x{va:X}: expected {expect!r}, found {text(ins)!r}")
        raw = bytes(ins.bytes)
        size = 1 if value < 0x80 and raw[-1] == value and len(raw) == 3 else 4
        at = len(raw) - size
        if int.from_bytes(raw[at:], "little") != value:
            raise SystemExit(f"{name} at 0x{va:X}: immediate is not 0x{value:X}")
        claim(name, va, len(raw), inner_ok=True)       # an immediate write never moves code
        emit(name, va, raw)
        lines.append(f"#define SITE_{name.upper()}_IMM_AT {at}")
        lines.append(f"#define SITE_{name.upper()}_IMM_SIZE {size}")
        lines.append(f"#define SITE_{name.upper()}_NEW 0x{new:X}")

    stubs = ["/* Generated by scripts/build_new_flowers_headers.py. Do not edit. */",
             "#ifndef FTFP_FLOWER_STUBS_H", "#define FTFP_FLOWER_STUBS_H", "",
             "/* One stub per species-table index site: the game's three instructions, then",
             "   index_fix(flower, index, state, family) may swap the index (in R) for a flower",
             "   24-37 so that the game's own [state + R*4] lands in the DLL's table. */", ""]
    table = ["typedef struct { unsigned int va; int length; const unsigned char *expect; const void *stub; } flower_index_site;",
             f"#define INDEX_SITE_COUNT {len(INDEX_SITES)}"]
    entries = []
    for va, family, state in INDEX_SITES:
        trio = disasm(data, va, 3)
        t = [text(i) for i in trio]
        m0 = re.fullmatch(r"add (\w+), (0x37|0x1d)", t[0])
        if not m0 or (m0.group(2) == "0x37") != (family == "P"):
            raise SystemExit(f"index site 0x{va:X}: {t}")
        reg = m0.group(1)
        if t[1] != f"imul {reg}, {reg}, 0x1a" or not t[2].startswith(f"add {reg}, dword ptr ["):
            raise SystemExit(f"index site 0x{va:X}: {t}")
        operand = t[2].split(", ", 1)[1]
        if "esp" in operand or reg in operand:
            raise SystemExit(f"index site 0x{va:X} reads its flower through esp or {reg}")
        follow = [text(i) for i in disasm(data, trio[2].address + trio[2].size, 3)]
        if not any(f"[{state} + {reg}*4]" in f for f in follow):
            raise SystemExit(f"index site 0x{va:X}: no consumer [{state} + {reg}*4] in {follow}")
        raw = b"".join(bytes(i.bytes) for i in trio)
        claim(f"index_0x{va:X}", va, len(raw))
        back = va + len(raw)
        name = f"stub_index_{va:06X}"
        stubs += [f"static const DWORD k_back_{va:06X} = 0x{back:08X}u;",
                  f"__declspec(naked) static void {name}(void) {{",
                  "    __asm {",
                  f"        {t[0]}", f"        {t[1]}", f"        {t[2]}",
                  "        pushad",
                  f"        push {1 if family == 'P' else 0}",
                  f"        push {state}",
                  f"        push {reg}",
                  f"        mov eax, {operand}",
                  "        push eax",
                  "        call index_fix",
                  f"        mov [esp + {PUSHAD_OFFSET[reg]}], eax",
                  "        popad",
                  f"        jmp k_back_{va:06X}",
                  "    }", "}", ""]
        entries.append(f"    {{ 0x{va:08X}u, {len(raw)}, (const unsigned char *)\"{''.join(f'\\x{b:02X}' for b in raw)}\", "
                       f"(const void *)(UINT_PTR){name} }},   /* {family}: {'; '.join(t)} */")
    stubs += table
    stubs.append("static const flower_index_site INDEX_SITES[INDEX_SITE_COUNT] = {")
    stubs += entries
    stubs += ["};", "", "#endif", ""]
    lines += ["", "#endif", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "flower_sites.h").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "flower_stubs.h").write_text("\n".join(stubs), encoding="utf-8")
    print(f"flower_sites.h: {len(SITES)} code sites, {len(IMMEDIATES)} immediates; "
          f"flower_stubs.h: {len(INDEX_SITES)} index sites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
