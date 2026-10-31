"""Generate src/pictures_plant_data.py: the numbers Picture Studio's Plant Tycoon renderer
(src/pictures_plant.py) draws with, read from the vanilla "Plant Tycoon.exe" (SHA-256
D1F83E3E...D6F9) and the patcher's own companion sources. No art: only sheet names, cell
grids, part boxes, joints, flower spots and the plant classes' starting shapes.

    python scripts/build_picture_studio_plant_data.py ["<vanilla Plant Tycoon.exe>"]

What it reads (src/pictures_plant.py's docstring has the drawing rules):

* SPRITES: the sprite table 0x4855F0 (0x34-byte records {id, file, +8, +0xC, columns, rows}).
* FOLIAGE_SHAPES: the plant factory 0x42EE20 (jump table 0x42F3B0, index (foliage - 1) % 23 + 1),
  each class's vtable slot 10 (its root draw, `push <shape table>`), and the shape table: 0xF4-byte
  part definitions ending with id -1, kept as 61 raw ints each.
* FLOWER_ART: the flower art records 0x48E6B8 (genes 0-23, 0x1C bytes: gene, worth, sheet, mask,
  first cell, anchor x, anchor y) and Unused Flowers' ART (native/ftfp_new_flowers, genes 24-37).
* FORMULA_SPOTS: the Radioactive Plant Formula's extra flower spots
  (native/ftfp_plant_upgrades/upgrade_sites.h) as (foliage, part definition, spot, x, y).
* STARTING_SHAPES: each class's constructor (the branch records it writes into a fresh pot
  record), run in Unicorn with Random answered by SHAPE_SEEDS rolls (one per "Shape n" choice).
  Needs Unicorn (tests/store_emulator.py); the shipped renderer never does.
"""

from __future__ import annotations

import random
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
OUT = ROOT / "src" / "pictures_plant_data.py"
EXE = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon" / "Plant Tycoon.exe"
EXE_SHA256 = "D1F83E3E3CAFE177452E2F8B6AF4B68CACED783B77A304370389375DB611D6F9"
NEW_FLOWERS = ROOT / "native" / "ftfp_new_flowers" / "ftfp_new_flowers.c"
UPGRADE_SITES = ROOT / "native" / "ftfp_plant_upgrades" / "upgrade_sites.h"

SPRITE_TABLE, SPRITE_COUNT, SPRITE_SIZE = 0x4855F0, 222, 0x34
FACTORY_TABLE = 0x42F3B0
FLOWER_ART_TABLE, FLOWER_ART_SIZE = 0x48E6B8, 0x1C
DEF_SIZE, DEF_INTS = 0xF4, 0xF4 // 4
RECORD = 0x5600
BRANCHES_AT, BRANCH_SIZE, BRANCH_MAX = 0xA8, 0x16C, 60
SHAPE_COUNT = 12                     # "Shape 1" .. "Shape 12" in Make your own
RANDOM, NEW = 0x004033B0, 0x0044E894


class Exe:
    def __init__(self, data: bytes) -> None:
        self.data = data
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        count = struct.unpack_from("<H", data, pe + 6)[0]
        optional = struct.unpack_from("<H", data, pe + 20)[0]
        self.sections = []
        for i in range(count):
            vsize, rva, raw_size, raw = struct.unpack_from("<IIII", data, pe + 24 + optional + i * 40 + 8)
            self.sections.append((rva, max(vsize, raw_size), raw))

    def read(self, va: int, size: int) -> bytes:
        rva = va - 0x400000
        for start, size_, raw in self.sections:
            if start <= rva < start + size_:
                return self.data[raw + rva - start: raw + rva - start + size]
        raise ValueError(hex(va))

    def ints(self, va: int, n: int) -> tuple:
        return struct.unpack(f"<{n}i", self.read(va, 4 * n))

    def cstring(self, va: int) -> str:
        out = bytearray()
        while True:
            byte = self.read(va + len(out), 1)[0]
            if byte == 0:
                return out.decode("latin-1")
            out.append(byte)


def sprites(exe: Exe) -> dict:
    out = {}
    for i in range(SPRITE_COUNT):
        rec = struct.unpack("<13I", exe.read(SPRITE_TABLE + i * SPRITE_SIZE, SPRITE_SIZE))
        if 0x400000 < rec[1] < 0x500000:
            out[rec[0]] = (exe.cstring(rec[1]), rec[4], rec[5])
    return out


def _calls_in(exe: Exe, va: int, limit: int = 0x60) -> list[int]:
    """The rel32 call targets in the first `limit` bytes at va."""
    code, out = exe.read(va, limit), []
    for i in range(len(code) - 4):
        if code[i] == 0xE8:
            out.append((va + i + 5 + struct.unpack_from("<i", code, i + 1)[0]) & 0xFFFFFFFF)
    return out


def classes(exe: Exe) -> dict:
    """foliage -> (constructor, vtable, shape table)."""
    table = struct.unpack("<24I", exe.read(FACTORY_TABLE, 24 * 4))
    out = {}
    for foliage in range(1, 24):
        ctor = next(c for c in _calls_in(exe, table[foliage]) if c != NEW)
        code = exe.read(ctor, 0x100)
        # The first `mov dword ptr [reg], imm32` (C7 0x/45 00) after the base constructor is the vtable.
        vtable = next(value for m in re.finditer(rb"\xC7(?:[\x00-\x03\x06\x07]|\x45\x00)", code, re.S)
                      for value in [struct.unpack_from("<I", code, m.end())[0]]
                      if 0x460000 <= value < 0x480000)
        root_draw = struct.unpack("<I", exe.read(vtable + 40, 4))[0]
        draw = exe.read(root_draw, 0x40)
        shape = next(struct.unpack_from("<I", draw, m.start() + 1)[0] for m in re.finditer(rb"\x68", draw)
                     if 0x470000 <= struct.unpack_from("<I", draw, m.start() + 1)[0] < 0x4A0000)
        out[foliage] = (ctor, vtable, shape)
    return out


def growth_start(exe: Exe, vtable: int) -> float:
    """Vtable slot 19 (`fld dword ptr [constant]; ret`): the fraction a branch starts at."""
    code = exe.read(struct.unpack("<I", exe.read(vtable + 19 * 4, 4))[0], 7)
    assert code[:2] == b"\xD9\x05" and code[6] == 0xC3, code.hex()
    return struct.unpack("<f", exe.read(struct.unpack_from("<I", code, 2)[0], 4))[0]


def formula_tables() -> set:
    """The shape tables Store Upgrades and Items.dll knows (SHAPE_TABLES): only their counts rise."""
    text = UPGRADE_SITES.read_text(encoding="utf-8")
    return {int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{8})u", text[text.index("SHAPE_TABLES[]"):].split(";")[0])}


def shape_table(exe: Exe, address: int) -> tuple:
    defs, n = [], 0
    while exe.ints(address + n * DEF_SIZE, 1)[0] != -1:
        defs.append(exe.ints(address + n * DEF_SIZE, DEF_INTS))
        n += 1
    return tuple(defs)


def flower_art(exe: Exe) -> dict:
    art = {g: exe.ints(FLOWER_ART_TABLE + g * FLOWER_ART_SIZE, 7) for g in range(24)}
    text = NEW_FLOWERS.read_text(encoding="utf-8")
    anchor = {name: int(value) for name, value in re.findall(r"#define (MIRABILIS_ANCHOR_[XY]) (-?\d+)", text)}
    block = text[text.index("static const flower_art ART["):]
    block = block[block.index("= {") + 3:block.index("};")]
    for row in re.findall(r"\{\s*([^}]*)\}", block):
        values = [anchor.get(v.strip(), None) if not re.fullmatch(r"-?\d+", v.strip()) else int(v) for v in row.split(",")]
        art[values[0]] = tuple(values)
    return art


def formula_spots(tables: dict) -> tuple:
    """(foliage, definition, spot, x, y) for each extra spot the formula's DLL writes."""
    text = UPGRADE_SITES.read_text(encoding="utf-8")
    listed = {int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{8})u", text[text.index("SHAPE_TABLES[]"):].split(";")[0])}
    out = []
    for at, x, y in re.findall(r"\{\s*0x([0-9A-Fa-f]+)u,\s*(-?\d+),\s*(-?\d+)\s*\}", text):
        at = int(at, 16)
        for foliage, (_c, _v, table, defs) in tables.items():
            if table in listed and table <= at < table + len(defs) * DEF_SIZE:
                d, offset = divmod(at - table, DEF_SIZE)
                spot, rest = divmod(offset - 0xAC, 12)
                assert rest == 0 and 0 <= spot < 6, hex(at)
                out.append((foliage, d, spot, int(x), int(y)))
    return tuple(sorted(out))


def starting_shapes(exe_path: Path, tables: dict) -> dict:
    """foliage -> shapes; a shape is a tuple of branch records (part, type, born, children), as the
    class's constructor writes them in a fresh pot record, Random answered by SHAPE_SEEDS."""
    import store_emulator as E
    out = {}
    for foliage, (ctor, _v, _t, _d) in tables.items():
        shapes = []
        for n in range(SHAPE_COUNT):
            rolls = random.Random(f"plant {foliage} shape {n + 1}")
            emu = E.Emulator(exe_path, None, {})
            emu.uc.mem_map(0, 0x1000)
            emu.hook(RANDOM, lambda e, r=rolls: r.randrange(e.arg(0)) if e.arg(0) > 0 else 0)
            for singleton in (0x41FCD0, 0x420670, 0x407A90):
                emu.hook(singleton, lambda e: e.alloc(0x100))
            record = emu.alloc(RECORD)
            emu.write32(record + 0x4C, foliage)
            emu.write32(record + 0x50, 1)
            obj = emu.alloc(0x58)
            emu.call(ctor, record, ecx=obj)
            data = bytes(emu.uc.mem_read(record, RECORD))
            changed = [i for i in range(RECORD) if data[i] and i not in range(0x4C, 0x54)]
            assert all(BRANCHES_AT <= i < BRANCHES_AT + BRANCH_MAX * BRANCH_SIZE or i in range(0x80, 0x84)
                       for i in changed), (foliage, [hex(i) for i in changed if not BRANCHES_AT <= i < 0x5600])
            shapes.append(branches(data))
        out[foliage] = tuple(shapes)
    return out


NURSERY_LAYERS = 0x437070          # the nursery's scenery draw: (2) behind the plants, (1) in front
ORNAMENTS_AT, ORNAMENT_SIZE, ORNAMENT_COUNT = 0x9EC, 0x20, 15     # state + 0x9EC + k x 0x20: owned byte
SCENE_STATE, SCENE_SPRITES, SCENE_MANAGER = 0xA3C, 0xA40, 0xA44
SPRITE_DRAW = 0x4207F0             # (sprite, x, y, alpha 0-1 float, scale %): a whole picture


def nursery_draws(exe_path: Path, owned: set) -> list:
    """0x437070(2) then 0x437070(1) with the ornaments `owned`: each sprite call (id, x, y, scale
    percent, alpha percent) in order (0x4207F0 takes id, x, y, alpha, scale). Magic plants' golden pots (0x42F4B0 / 0x435EE0) and the
    visitors (0x417C50, 0x417350) are left out."""
    import store_emulator as E
    emu = E.Emulator(exe_path, None, {})
    emu.uc.mem_map(0, 0x1000)
    calls = []
    signed = lambda v: v - (1 << 32) if v & 0x80000000 else v

    def record(e):
        alpha = struct.unpack("<f", struct.pack("<I", e.arg(3)))[0]
        calls.append((e.arg(0), signed(e.arg(1)), signed(e.arg(2)), e.arg(4), round(alpha * 100)))
        return 0
    emu.hook(SPRITE_DRAW, record, 0x14)
    for address, pop in ((0x42F4B0, 0x10), (0x435EE0, 0x10), (0x417350, 0)):
        emu.hook(address, lambda e: 0, pop)
    emu.hook(0x417C50, lambda e: e.alloc(0x100))
    state = emu.alloc(0x63E70)
    for k in owned:
        emu.write8(state + ORNAMENTS_AT + k * ORNAMENT_SIZE, 1)
    scene = emu.alloc(0x1000)
    emu.write32(scene + SCENE_STATE, state)
    emu.write32(scene + SCENE_SPRITES, emu.alloc(0x10))
    emu.write32(scene + SCENE_MANAGER, emu.alloc(0x100))
    for layer in (2, 1):
        emu.call(NURSERY_LAYERS, layer, ecx=scene)
    return calls


def decorations(exe_path: Path) -> dict:
    """ornament k -> the sprite calls owning it adds to the nursery's scenery (drawn only when it is
    owned), in the game's order."""
    base = nursery_draws(exe_path, set())
    out = {}
    for k in range(ORNAMENT_COUNT):
        rest = list(base)
        added = []
        for call in nursery_draws(exe_path, {k}):
            if call in rest:
                rest.remove(call)
            else:
                added.append(call)
        if added:
            out[k] = tuple(added)
    return out


def branches(record: bytes) -> tuple:
    """The branch records up to the first unused one: (part, type, born, ((joint, child), ...))."""
    out = []
    for k in range(BRANCH_MAX):
        at = BRANCHES_AT + k * BRANCH_SIZE
        part, kind = struct.unpack_from("<ii", record, at)
        if kind == 0:
            break
        born = struct.unpack_from("<f", record, at + 8)[0]
        count = struct.unpack_from("<i", record, at + 0x1C)[0]
        children = tuple(struct.unpack_from("<ii", record, at + 0x20 + j * 0x10) for j in range(count))
        flowers = struct.unpack_from("<i", record, at + 0xC0)[0]
        assert flowers == 0
        out.append((part, kind, born, children))
    return tuple(out)


def main() -> int:
    import hashlib
    exe_path = Path(sys.argv[1]) if len(sys.argv) > 1 else EXE
    data = exe_path.read_bytes()
    if hashlib.sha256(data).hexdigest().upper() != EXE_SHA256:
        raise SystemExit(f"{exe_path} is not the vanilla Plant Tycoon.exe ({EXE_SHA256[:8]}...)")
    OUT.write_text(render(exe_path), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


def render(exe_path: Path) -> str:
    exe = Exe(exe_path.read_bytes())
    table = {f: (c, v, s, shape_table(exe, s)) for f, (c, v, s) in classes(exe).items()}
    lines = [
        '"""Generated by scripts/build_picture_studio_plant_data.py from the vanilla Plant Tycoon.exe',
        f'(SHA-256 {EXE_SHA256[:8]}...{EXE_SHA256[-4:]}) and the patcher\'s companion sources. Do not edit:',
        'run the script (tests/test_pictures_plant.py checks it). Numbers only, no art."""',
        "",
        "# sprite id -> (file, columns, rows)",
        "SPRITES = {",
    ]
    lines += [f"    0x{k:X}: {v!r}," for k, v in sorted(sprites(exe).items())]
    lines += ["}", "", "# foliage -> (constructor, vtable, shape table address)", "CLASSES = {"]
    lines += [f"    {f}: (0x{c:X}, 0x{v:X}, 0x{s:X})," for f, (c, v, s, _d) in table.items()]
    lines += ["}", "", "# foliage -> vtable slot 19: the fraction of full size a branch starts at",
              "GROWTH_START = {"]
    lines += [f"    {f}: {growth_start(exe, v)!r}," for f, (c, v, s, _d) in table.items()]
    known = formula_tables()
    lines += ["}", "", "# the foliages whose shape table Store Upgrades and Items.dll knows (their spot counts rise)",
              f"FORMULA_FOLIAGES = {sorted(f for f, (c, v, s, _d) in table.items() if s in known)!r}"]
    lines += ["", "# foliage -> part definitions (61 raw ints each, 0xF4 bytes)", "SHAPE_TABLES = {"]
    for f, (_c, _v, _s, defs) in table.items():
        lines.append(f"    {f}: (")
        lines += [f"        {d!r}," for d in defs]
        lines.append("    ),")
    lines += ["}", "", "# gene -> (gene, worth, sheet, mask, first cell, anchor x, anchor y)", "FLOWER_ART = {"]
    lines += [f"    {g}: {v!r}," for g, v in sorted(flower_art(exe).items())]
    lines += ["}", "", "# the Radioactive Plant Formula's extra flower spots: (foliage, definition, spot, x, y)",
              f"FORMULA_SPOTS = {formula_spots(table)!r}", "",
              f"SHAPE_COUNT = {SHAPE_COUNT}",
              "# foliage -> shapes -> branches (part, type, born, ((joint, child), ...)) from each class's",
              "# constructor with Random answered by random.Random(f'plant {foliage} shape {n}')",
              "STARTING_SHAPES = {"]
    for f, shapes in starting_shapes(exe_path, table).items():
        lines.append(f"    {f}: (")
        lines += [f"        {s!r}," for s in shapes]
        lines.append("    ),")
    lines += ["}", "",
              "# nursery ornament k (state + 0x9EC + k x 0x20 owned) -> the sprite calls (0x4207F0: id, x, y,",
              "# scale %, alpha %) the nursery's scenery draw (0x437070(2), then (1)) adds when it is owned",
              "DECORATIONS = {"]
    lines += [f"    {k}: {v!r}," for k, v in decorations(exe_path).items()]
    lines += ["}", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
