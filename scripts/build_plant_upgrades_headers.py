"""Generate the Plant Upgrades companion's site header from the vanilla Plant Tycoon.exe.

    python scripts/build_plant_upgrades_headers.py "<vanilla Plant Tycoon folder>"

writes native/ftfp_plant_upgrades/upgrade_sites.h.

Same rules as scripts/build_new_flowers_headers.py: each code site is
disassembled from the vanilla executable and must hold exactly the listed
instructions; a site may begin at a branch target but never contain one, and
must not overlap a Fix Patcher patch or a New Flowers site. The stock bytes
become the bytes the DLL requires before it writes anything (all sites or
none, at run time). Data sites (the sprite-sheet records the DLL points at
its own images) are pinned the same way, by their stock bytes.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "native" / "ftfp_plant_upgrades"
BASE = 0x400000

_spec = importlib.util.spec_from_file_location("flower_headers", ROOT / "scripts" / "build_new_flowers_headers.py")
flower_headers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flower_headers)
disasm, text, c_bytes = flower_headers.disasm, flower_headers.text, flower_headers.c_bytes

PRICE = "mov dword ptr [esi + 0x84], 0x7d0"

# (name, va, expected instructions). See docs/plant-tycoon-upgrades-design.md for what each one does.
SITES = [
    ("roll_tail", 0x41DDDA, ["pop edi", "pop esi", "pop ebp", "pop ebx", "pop ecx", "ret"]),
    ("dialog_entry", 0x430950, ["push -1", "push 0x463a67"]),
    ("dialog_picture", 0x430827, ["mov eax, dword ptr [esi + 0xb8]"]),
    ("price_buyable", 0x430CA8, [PRICE]),
    ("price_poor", 0x431015, [PRICE]),
    ("price_tray_full", 0x43136E, [PRICE]),
    ("dialog_done", 0x433240, ["cmp byte ptr [esi + 0xa8], 0"]),
    ("buy_seed", 0x432D45, ["mov eax, dword ptr [ebp + 0x94]"]),
    ("chem_price", 0x432716, ["mov edx, dword ptr [eax + ecx + 0x8c8]", "mov ecx, dword ptr [esi + 0x78]", "push edi"]),
    ("chem_doses", 0x432E43, ["mov edx, dword ptr [eax + ecx + 0x8dc]"]),
    ("chem_apply", 0x4266A6, ["mov eax, dword ptr [esp + 0x20]", "add eax, -0x1b"]),
    ("tray_name_greenhouse", 0x4277B4, ["add eax, 0x189"]),
    ("tray_name_store", 0x4484AA, ["add edx, 0x189"]),
    ("string_lookup", 0x44CA70, ["mov eax, dword ptr [esp + 4]", "test eax, eax"]),
    ("store_activate", 0x446D40, ["push -1", "push 0x463e5e"]),
    ("store_draw", 0x447DA2, ["xor ebx, ebx", "mov ebp, 0x13b"]),
    ("store_click", 0x448173, ["mov dword ptr [esp + 0x14], eax", "mov ebp, 0x122"]),
    ("store_hover", 0x448433, ["mov eax, dword ptr [esi + 0x1bc]"]),
    # "is this flower spot free?" (a spot on a joint is taken while a branch grows there): the
    # formula's flowering skips that test, so every spot on every branch flowers.
    ("joint_free", 0x42D330, ["mov eax, dword ptr [esp + 0xc]", "mov edx, dword ptr [esp + 8]"]),
    # Planting (0x42FC70, every new plant: new game, tray, pot seed): the new plant's +0x7C starts
    # at 0, so a formula mark left by the pot's last plant never carries over.
    ("plant_seed", 0x42FCDD, ["mov dword ptr [esi + 0x78], edx", "mov byte ptr [esi + 0x6c], 0"]),
    # The greenhouse trash: the mouse-up's call of the stock trash (0x424680, a held item let go
    # off the pots), and the press off the pots (0x426040 at 0x4272DC, before the selected plant's
    # trash or the put-back): the new chemicals held there are thrown away.
    ("trash_drop", 0x425FF2, ["call 0x424680"]),
    ("trash_press", 0x4272DC, ["mov ecx, dword ptr [esi + 0x68]", "mov eax, dword ptr [ecx + 0x63e58]"]),
    # Automatic Sprinklers and the Auto-Healer: the top of the plant update's age-unit loop (each
    # caught-up unit, edi = the pot) and the code right after the loop (esi = the plant object).
    ("unit_top", 0x42E134, ["cmp dword ptr [edi + 0x28], ebp", "jne 0x42e144"]),
    ("units_done", 0x42E2DF, ["mov ecx, dword ptr [esi + 0xc]", "cmp byte ptr [ecx + 0x53f27], 0"]),
    # The plant update (0x42DF80) clears a dead plant's on-sale flag (+0x9D) every update: the DLL
    # remembers it was for sale (+0x9F) so the Revival Potion can put it back on sale.
    ("dead_untag", 0x42DF91, ["mov byte ptr [eax + 0x9d], 0"]),
    # A visitor's purchase (0x435C70, every nursery's: the extra nurseries' off-screen sales run the
    # same code with their pots arranged in): the two reads of the price it pays, into the money
    # earned (state + 0x34) and into the cash (0x41ED70). A plant given the Radioactive Plant Formula
    # (or its Bomb) pays its species' highest selling price instead. Both start right where New
    # Flowers' index stubs for 0x435CE5 and 0x435D05 come back.
    ("sale_record", 0x435CF2, ["mov edx, dword ptr [eax + ecx*4]", "add dword ptr [eax + 0x34], edx"]),
    ("sale_cash", 0x435D12, ["mov edx, dword ptr [ecx + eax*4]", "push edx", "call 0x41ed70"]),
]

# One-byte immediates: (name, va of the instruction, instruction, value, new value).
IMMEDIATES = [
    ("chem_picture_bound", 0x4308D1, "cmp eax, 0x24", 0x24, 0x32),     # the dialog draws chemicals 36-49 (48, 49: Muta-)
]

# Data in the sprite-sheet table (.data): (name, va, stock bytes).
SPRITES = 0x4855F0
DATA = [
    ("seed_sheet_file", 0x485F4C, None),          # sheet 0x2E file name pointer
    ("seed_sheet_rows", 0x485F5C, struct.pack("<I", 6)),
    ("chem_sheet_file", 0x4875A4, None),          # sheet 0xB3 file name pointer
    ("chem_sheet_rows", 0x4875B4, struct.pack("<I", 9)),
    ("link_record", 0x4882D4, bytes(0x18)),       # the table's spare, all-zero last record
]
SHEET_FILES = {"seed_sheet_file": (0x2E, b"seed_grid.png"), "chem_sheet_file": (0xB3, b"Chemicals_Grid.png")}


# Every plant family's shape table (the pointer each plant constructor stores at +4).
SHAPE_TABLES = [
    0x47CD98, 0x47D488, 0x47DA80, 0x47E540, 0x47EF08, 0x47F7E0, 0x480578, 0x480A78,
    0x480F80, 0x4824C0, 0x482D00, 0x4834E0, 0x484940, 0x488868, 0x489DA0, 0x48AD00,
    0x48B6C8, 0x48C740, 0x48D420, 0x48E0C0, 0x490568, 0x490B60, 0x4914C8,
]


SPRITES_TABLE, SPRITE_RECORDS, SPRITE_STRIDE = 0x4855F0, 222, 0x34


def formula_spots(data: bytes, images: Path) -> list[tuple[int, int, int]]:
    """For every part definition, its empty flower spots past the count, each placed on an opaque
    pixel of the part (its sheet, +0x08, and its box, +0x14..+0x20), at least 2 px inside, as far
    as possible from the spots it already has (farthest-point sampling)."""
    from PIL import Image
    import numpy as np

    word = lambda va: struct.unpack_from("<i", data, va - BASE)[0]
    sheets = {}
    for k in range(SPRITE_RECORDS):
        record = SPRITES_TABLE + k * SPRITE_STRIDE
        if word(record + 4):
            sheets[word(record)] = c_string_at(data, word(record + 4)).decode("latin-1")
    cache: dict[str, np.ndarray] = {}
    out = []
    for table in SHAPE_TABLES:
        va = table
        while word(va) != -1:
            count, (x0, y0, w, h) = word(va + 0xA8), (word(va + 0x14), word(va + 0x18), word(va + 0x1C), word(va + 0x20))
            name = sheets.get(word(va + 8))
            if name and w > 0 and h > 0 and count < 6:
                if name not in cache:
                    cache[name] = np.asarray(Image.open(images / name).convert("RGBA"))[:, :, 3]
                alpha = cache[name][y0:y0 + h, x0:x0 + w]
                # Up to 2 px inside the outline, less for a thin stem or leaf, any visible pixel as
                # a last resort, else the part's pivot: every slot gets a spot, because a flower the
                # formula put on a slot draws at that slot's spot after every restart.
                xs = ys = np.array([], dtype=int)
                for solid, shrink in ((128, 2), (128, 1), (128, 0), (0, 0)):
                    inside = alpha > solid
                    for _ in range(shrink):
                        inside[1:-1, 1:-1] &= inside[:-2, 1:-1] & inside[2:, 1:-1] & inside[1:-1, :-2] & inside[1:-1, 2:]
                        inside[[0, -1], :] = False
                        inside[:, [0, -1]] = False
                    ys, xs = np.nonzero(inside)
                    if len(xs):
                        break
                if not len(xs):
                    xs, ys = np.array([word(va + 0x24) - x0]), np.array([word(va + 0x28) - y0])
                taken = [(word(va + 0xAC + i * 12), word(va + 0xB0 + i * 12)) for i in range(6)
                         if any(word(va + 0xAC + i * 12 + j) for j in (0, 4, 8))]
                pts = np.stack([xs + x0, ys + y0], axis=1)
                if not taken:                          # start nearest the box's centre
                    centre = np.array([x0 + w / 2, y0 + h / 2])
                    taken = [tuple(pts[np.argmin(((pts - centre) ** 2).sum(1))])]
                    first = taken[0]
                else:
                    first = None
                for i in range(count, 6):
                    at = va + 0xAC + i * 12
                    if any(word(at + j) for j in (0, 4, 8)):
                        continue                       # a spot the artists left unused
                    if first is not None:
                        x, y = first
                        first = None
                    else:
                        d = np.min([((pts - np.array(t)) ** 2).sum(1) for t in taken], axis=0)
                        x, y = pts[int(np.argmax(d))]
                        taken.append((x, y))
                    out.append((at, int(x), int(y)))
            va += 0xF4
    return out


def c_string_at(data: bytes, va: int) -> bytes:
    at = va - BASE
    return data[at:data.index(b"\0", at)]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = (Path(sys.argv[1]) / "Plant Tycoon.exe").read_bytes()
    taken = flower_headers.fix_patcher_ranges()
    flower_sites = [(va, va + sum(len(i.bytes) for i in disasm(data, va, len(expect))), name)
                    for name, va, expect in flower_headers.SITES]
    targets = flower_headers.branch_targets(data)
    used: list[tuple[int, int, str]] = list(flower_sites)
    lines = ["/* Generated by scripts/build_plant_upgrades_headers.py from the vanilla Plant Tycoon.exe. Do not edit. */",
             "#ifndef FTFP_UPGRADE_SITES_H", "#define FTFP_UPGRADE_SITES_H", ""]

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
        raw = bytes(ins.bytes)
        if text(ins) != expect or raw[-1] != value:
            raise SystemExit(f"{name} at 0x{va:X}: expected {expect!r}, found {text(ins)!r}")
        claim(name, va, len(raw), inner_ok=True)
        emit(name, va, raw)
        lines.append(f"#define SITE_{name.upper()}_IMM_AT {len(raw) - 1}")
        lines.append(f"#define SITE_{name.upper()}_NEW 0x{new:X}")

    for name, va, stock in DATA:
        if stock is None:
            sheet, file_name = SHEET_FILES[name]
            record = va - 4
            if struct.unpack_from("<I", data, record - BASE)[0] != sheet:
                raise SystemExit(f"{name}: the record at 0x{record:X} is not sheet 0x{sheet:X}")
            stock = data[va - BASE: va - BASE + 4]
            if c_string_at(data, struct.unpack("<I", stock)[0]).lower() != file_name.lower():
                raise SystemExit(f"{name}: sheet 0x{sheet:X} is not {file_name!r}")
        elif data[va - BASE: va - BASE + len(stock)] != stock:
            raise SystemExit(f"{name} at 0x{va:X}: expected {stock.hex(' ')}")
        if name == "link_record" and (va - SPRITES) % 0x34:
            raise SystemExit("link_record is not a sprite record")
        emit(name, va, stock)

    # The plant shape tables: 0xF4-byte part definitions ending with id -1. A definition has
    # room for 6 flower spots (+0xAC, 12 bytes each, count at +0xA8). For the Radioactive Plant
    # Formula the DLL fills the all-zero spots past the count (a few definitions keep unused
    # spots there from the artists; those stay as they are).
    for va in SHAPE_TABLES:
        at, n = va - BASE, 0
        while struct.unpack_from("<i", data, at)[0] != -1:
            count = struct.unpack_from("<i", data, at + 0xA8)[0]
            if not 0 <= count <= 6 or n >= 80:
                raise SystemExit(f"shape table 0x{va:X}: record {n} is not a part definition")
            at += 0xF4
            n += 1
        if n == 0:
            raise SystemExit(f"shape table 0x{va:X} is empty")
    lines.append("")
    spots = formula_spots(data, Path(sys.argv[1]) / "Images")
    lines.append("/* The Radioactive Plant Formula's extra flower spots: (spot address, x, y), each on the")
    lines.append("   part's own visible pixels in its sheet, spread apart. */")
    lines.append("typedef struct { unsigned int at; int x, y; } formula_spot;")
    lines.append(f"static const formula_spot FORMULA_SPOTS[{len(spots)}] = {{")
    lines += [f"    {{ 0x{at:08X}u, {x}, {y} }}," for at, x, y in spots]
    lines.append("};")
    lines.append(f"#define FORMULA_SPOT_COUNT {len(spots)}")
    lines.append("static const unsigned int SHAPE_TABLES[] = { "
                 + ", ".join(f"0x{va:08X}u" for va in SHAPE_TABLES) + " };")
    lines.append(f"#define SHAPE_TABLE_COUNT {len(SHAPE_TABLES)}")

    lines += ["", "#endif", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "upgrade_sites.h").write_text("\n".join(lines), encoding="utf-8")
    print(f"upgrade_sites.h: {len(SITES)} code sites, {len(IMMEDIATES)} immediates, {len(DATA)} data sites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
