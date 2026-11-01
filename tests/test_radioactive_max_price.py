"""Treated fish and plants sell for the highest possible price (the owner, 2026-10-31: "Always pays the max").

A fish given a Radioactive Growth Hormone dose (DS Store Items) and a plant given the Radioactive Plant
Formula or its Bomb (Store Upgrades and Items) is marked; when it is sold the player is paid its
species' highest selling price, the Breeding Guide's "Highest selling" with Max effects, while the
sale chance and timing stay the asking price's.

* The price: native/common/max_sale_price.h, compiled (max_sale_price_harness.c), gives the Python
  model's highest selling price (src/breeding_fish.py, src/breeding_plant.py) for every species.
* The fish mark's byte: the fish record's +0x48 is a dword no game code reads, proven from the
  vanilla executable's code (capstone): no operand reaches +0x48 of any fish record in the game
  state, and every other operand at +0x48 is pinned here with the object it is on.
* The sales, emulated in Unicorn on the vanilla executables (tests/store_emulator.py) with two of
  the patcher's DLLs at once: Extra Tanks.dll and DS Store Items.dll for Fish (the stock sale roll,
  Tanks 4-6 lent the Sale Tank's place), Extra Greenhouses.dll and Store Upgrades and Items.dll
  for Plant (the stock sale 0x435C70, the nurseries off screen). The second DLL is mapped at its
  own base with its relocations applied, and its hooks written as its install writes them.
* The mark follows the fish or plant (moves, swaps, extra tanks and greenhouses, saves, clones)
  and is cleared at the sale, death, the trash and a replanting.
* The texts: the three items' store descriptions, the patcher descriptions and Game Mechanics.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_fish as BF  # noqa: E402
import breeding_plant as BP  # noqa: E402

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

VANILLA = E.VANILLA if E else Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
FISH_EXE = VANILLA / "Fish Tycoon" / "Fish Tycoon.exe"
PLANT_EXE = VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"
FISH_DLL = ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll"
PLANT_DLL = ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll"
FISH_C = ROOT / "native" / "ftfp_ds_store" / "ftfp_ds_store.c"
PLANT_C = ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c"

MARK, F_MARK = 0x58414D52, 0x48          # "RMAX" in the fish record's +0x48
RADIOACTIVE, POT_MARK, SALE_KEPT = 0x52, 0x9F, 0x53
SECOND_BASE = 0x18000000                 # where the second DLL is mapped

FISH_SENTENCE = "Treated fish sell for the highest possible price!"
FISH_SENTENCE_DE = "Behandelte Fische werden zum Höchstpreis verkauft!"
PLANT_SENTENCE = "Allows treated plants to sell at max price, regardless of their set value."


def _toolchain() -> bool:
    return E is not None and E.toolchain_ready()


def needs(exe: Path):
    return unittest.skipUnless(_toolchain() and exe.is_file(),
                               "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


# ---------------------------------------------------------------- the price maths

@unittest.skipUnless(_toolchain(), "needs the pinned MSVC toolset")
class MaxPriceMathAgreesWithTheModel(unittest.TestCase):
    """max_sale_price.h gives the Breeding Guide's highest selling price (Max effects) for every species."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        command = [
            str(E.MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/O2", "/MT", "/W4", "/WX", "/GS-",
            f"/Fo{out}\\", f"/Fe{out / 'harness.exe'}",
            "/I", str(E.MSVC / "include"),
            "/I", str(E.SDK / "Include" / E.SDK_VERSION / "ucrt"),
            "/I", str(E.SDK / "Include" / E.SDK_VERSION / "um"),
            "/I", str(E.SDK / "Include" / E.SDK_VERSION / "shared"),
            str(ROOT / "native" / "common" / "max_sale_price_harness.c"),
            "/link", f"/LIBPATH:{E.MSVC / 'lib' / 'x86'}",
            f"/LIBPATH:{E.SDK / 'Lib' / E.SDK_VERSION / 'um' / 'x86'}",
            f"/LIBPATH:{E.SDK / 'Lib' / E.SDK_VERSION / 'ucrt' / 'x86'}",
        ]
        result = subprocess.run(command, cwd=out, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        cls.harness = out / "harness.exe"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def ask(self, lines: list[str]) -> list[int]:
        result = subprocess.run([str(self.harness)], input="\n".join(lines) + "\n", capture_output=True,
                                text=True, check=True)
        return [int(x) for x in result.stdout.split()]

    def test_every_fish_species(self) -> None:
        model = BF.FishModel(extras=True)
        keys = [s.key for s in model.species()]
        self.assertEqual(len(keys), 28 * 28)
        got = self.ask([f"F {b} {f}" for b, f in keys])
        for key, price in zip(keys, got):
            self.assertEqual(price, model.prices(key, "max").highest_selling, key)
        self.assertEqual(self.ask(["F 7 7"]), [475])                        # the Golden Guppy, B = 190
        self.assertEqual(self.ask(["F 22 22", "F 21 3", "F -1 0", "F 30 0"]), [0, 0, 0, 0])   # not species

    def test_every_plant_species(self) -> None:
        model = BP.load(None, extras=True)
        keys = [s.key for s in model.species()]
        self.assertEqual(len(keys), 23 * 37)
        got = self.ask([f"P {f} {fl}" for f, fl in keys])
        for key, price in zip(keys, got):
            self.assertEqual(price, model.prices(key, "max").highest_selling, key)
        self.assertEqual(self.ask(["P 11 10"]), [1186])                     # the Fabled Lemonbush, V = 250
        self.assertEqual(self.ask(["P 0 5", "P 24 1", "P 5 38", "P 5 0"]), [0, 0, 0, 0])

    def test_price_math_h_is_untouched(self) -> None:
        """Kept apart from the Optimize Prices maths: price_math.h is not included or changed by it."""
        header = (ROOT / "native" / "common" / "max_sale_price.h").read_text(encoding="utf-8")
        self.assertNotIn("#include", header)


# ---------------------------------------------------------------- the fish mark's byte

FISH_RECORD = 0x288
STATE_FIELD_BASES = [0x390 + t * 0x51EC + s * FISH_RECORD for t in range(4) for s in range(31)]
# Every function of the vanilla Fish Tycoon.exe with a non-stack operand covering +0x48 of its base,
# and the object that base is (the start is the function's first byte after int3 padding).
OTHER_OBJECTS_AT_0X48 = {
    # The game library (0x401000-0x410FFF: controls, buttons, images, text, sound): no fish there.
    0x4011F0: "library", 0x401650: "library", 0x401A20: "library", 0x407920: "library", 0x407BE0: "library",
    0x408E00: "library", 0x408FE0: "library", 0x409240: "library", 0x409290: "library", 0x40A090: "library",
    0x40A110: "library", 0x40A170: "library", 0x40A480: "library", 0x40B680: "library", 0x40BD30: "library",
    0x40DDF0: "library", 0x40DE60: "library", 0x40FF90: "library",
    # The tank view's swimming entries, 0x84 bytes each at view + 0x1080 (0x4140F8, 0x4158C7, 0x414FB2).
    0x413CF0: "view entry", 0x414F50: "view entry", 0x415460: "view entry",
    0x416E60: "a customer (+0x44 and +0x48 set to -1, byte +0x4C)",
    0x419450: "the state's totals (new game: state + 0x1C .. + 0x60)",
    # The tank scene (esi): +0x48 its string table, read before 0x427050.
    0x41CBB0: "tank scene", 0x41CF20: "tank scene", 0x41D910: "tank scene", 0x41D980: "tank scene",
    0x41DA40: "tank scene", 0x41F800: "tank scene",
    0x41E850: "a fish record copied field by field: +0x48 copied as is",
    0x424690: "not code: the jump table after 0x424E4A, read as instructions",
    0x426160: "a scene's child (+0x2C)", 0x426370: "a scene's child (+0x2C)", 0x426D00: "a scene's child (+0x2C)",
    0x428340: "the store scene", 0x428590: "the store scene",
    # The C runtime (0x42A000 on).
    0x42D8D0: "CRT", 0x4395AF: "CRT", 0x4349F0: "CRT memcpy and memset (16-byte SSE moves at +0x40)",
}


def _capstone():
    return importlib.util.find_spec("capstone") is not None


def _text_section(exe: Path) -> tuple[int, bytes]:
    data = exe.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 52)[0]
    for i in range(count):
        at = pe + 24 + optional + i * 40
        _vsize, rva, raw_size, raw = struct.unpack_from("<IIII", data, at + 8)
        if struct.unpack_from("<I", data, at + 36)[0] & 0x20000000:
            return base + rva, data[raw:raw + raw_size]
    raise AssertionError("no code section")


def _operands(exe: Path):
    """(address, displacement, size, text, base register) of every memory operand, a linear sweep."""
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs
    from capstone.x86 import X86_OP_MEM
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    va0, code = _text_section(exe)
    off = 0
    while off < len(code):
        moved = False
        for ins in md.disasm(code[off:], va0 + off):
            moved = True
            off = ins.address - va0 + ins.size
            for op in ins.operands:
                if op.type == X86_OP_MEM:
                    size = 1 if ins.mnemonic == "lea" else max(op.size, 1)
                    yield (ins.address, op.mem.disp & 0xFFFFFFFF, size, f"{ins.mnemonic} {ins.op_str}",
                           ins.reg_name(op.mem.base) if op.mem.base else "")
        if not moved:
            off += 1


def _function_start(va0: int, code: bytes, va: int) -> int:
    off = va - va0
    while off > 2 and not (code[off - 1] == 0xCC and code[off - 2] == 0xCC):
        off -= 1
    return va0 + off


@unittest.skipUnless(_capstone() and FISH_EXE.is_file(), "needs capstone and the vanilla Fish Tycoon.exe")
class FishMarkByteIsUnused(unittest.TestCase):
    """+0x48 of a fish record: what the game's code does with it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.operands = list(_operands(FISH_EXE))
        cls.va0, cls.code = _text_section(FISH_EXE)

    def test_no_operand_reaches_it_in_the_game_state(self) -> None:
        """state + 0x390 + tank * 0x51EC + slot * 0x288 + 0x48, any tank 0-3 and slot 0-30: no operand
        (any size, not on the stack) covers it, but four on the tank view whose displacement happens to
        be tank 0 slot 5's +0x48 (0x1080): the view's swimming entries start at view + 0x1080, 0x84
        bytes each, its count at +0x5DD8 (0x415CB5, 0x414538). The other fish fields have such
        operands (health, body), so the scan sees them."""
        hits, seen = {}, set()
        for va, disp, size, text, base in self.operands:
            if base == "esp":
                continue
            for start in STATE_FIELD_BASES:
                if disp <= start + F_MARK < disp + size or disp <= start + F_MARK + 3 < disp + size:
                    hits[va] = text
                for field in (0x3C, 0x4C):
                    if disp == start + field:
                        seen.add(field)
        self.assertEqual(hits, {0x414570: "cmp byte ptr [esi + 0x1083], bl", 0x414596: "mov byte ptr [esi + 0x1083], bl",
                                0x4145B0: "mov byte ptr [esi + 0x1083], 1", 0x415CC6: "lea eax, [ebp + 0x1080]"})
        self.assertEqual(seen, {0x3C, 0x4C})

    def test_every_other_operand_is_on_another_object(self) -> None:
        functions = {}
        for va, disp, size, text, base in self.operands:
            if base == "esp" or disp > F_MARK + 3 or disp + size <= F_MARK:
                continue
            functions.setdefault(_function_start(self.va0, self.code, va), []).append((hex(va), text))
        self.assertEqual(sorted(functions), sorted(OTHER_OBJECTS_AT_0X48),
                         {hex(f): v for f, v in functions.items() if f not in OTHER_OBJECTS_AT_0X48})

    def test_the_birth_starts_it_at_zero_and_the_copies_keep_it(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        md = Cs(CS_ARCH_X86, CS_MODE_32)

        def at(va: int, n: int = 1) -> list[str]:
            raw = self.code[va - self.va0: va - self.va0 + 16 * n]
            return [f"{i.mnemonic} {i.op_str}" for i in md.disasm(raw, va)][:n]
        # NewBaby 0x41FA30 builds the record at esp + 0x10: +0x48 (esp + 0x58) = 0 (eax, 0x41FA6D).
        self.assertEqual(at(0x41FA3C), ["lea ecx, [esp + 0x10]"])
        self.assertEqual(at(0x41FA6D), ["xor eax, eax"])
        self.assertEqual(at(0x41FAA7), ["mov dword ptr [esp + 0x58], eax"])
        self.assertEqual(at(0x41FBFE), ["call 0x419c50"])                     # handed to AddFish
        # AddFish copies all 0x288 bytes (0xA2 dwords); REMOVE_FISH (0x418E20) never writes +0x48.
        self.assertEqual(at(0x419C94, 2), ["mov ecx, 0xa2", "rep movsd dword ptr es:[edi], dword ptr [esi]"])
        remove = self.code[0x418E20 - self.va0: 0x419098 - self.va0]
        self.assertNotIn(struct.pack("<I", 0x390 + F_MARK), remove)
        self.assertEqual(at(0x41E882, 2), ["mov ecx, dword ptr [eax + 0x48]", "mov dword ptr [edx + 0x48], ecx"])


# ---------------------------------------------------------------- two DLLs in one emulator

def map_second(emu, dll: Path, symbols: dict[str, int], base: int = SECOND_BASE):
    """Map a second DLL at `base` (its relocations applied) and give each of its imports a thunk;
    returns its symbols at that base and {import name: thunk}."""
    data = dll.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    image_base = struct.unpack_from("<I", data, pe + 52)[0]
    size = struct.unpack_from("<I", data, pe + 80)[0]
    _b, _s, sections, imports = E.pe_image(data)
    reloc_rva, reloc_size = struct.unpack_from("<II", data, pe + 24 + 96 + 5 * 8)
    emu.uc.mem_map(base, (size + 0xFFF) & ~0xFFF)
    emu.uc.mem_write(base, data[:0x1000])
    for rva, raw, raw_size in sections:
        emu.uc.mem_write(base + rva, data[raw:raw + raw_size])
    delta = (base - image_base) & 0xFFFFFFFF
    at = 0
    while at < reloc_size:
        page, block = struct.unpack("<II", emu.uc.mem_read(base + reloc_rva + at, 8))
        if block == 0:
            break
        for i in range((block - 8) // 2):
            entry = struct.unpack("<H", emu.uc.mem_read(base + reloc_rva + at + 8 + 2 * i, 2))[0]
            if entry >> 12 == 3:                                   # IMAGE_REL_BASED_HIGHLOW
                where = base + page + (entry & 0xFFF)
                emu.write32(where, emu.read32(where) + delta)
        at += block
    names = {}
    at = imports
    while True:
        lookup, _t, _f, _name, iat = struct.unpack("<5I", emu.uc.mem_read(base + at, 20))
        if lookup == 0 and iat == 0:
            break
        slot = 0
        while True:
            entry = emu.read32(base + (lookup or iat) + slot * 4)
            if entry == 0:
                break
            name = emu.cstring(base + entry + 2).decode("ascii") if not entry & 0x80000000 else f"#{entry & 0xFFFF}"
            thunk = emu.thunk()
            emu.write32(base + iat + slot * 4, thunk)
            names[name] = thunk
            slot += 1
        at += 20
    return {k: (v + delta) & 0xFFFFFFFF for k, v in symbols.items()}, names


def branch(emu, at: int, to: int, length: int, opcode: int = 0xE9) -> None:
    """The DLL's jump (or call) as its install writes it, the rest of the site padded with nops."""
    emu.uc.mem_write(at, bytes([opcode]) + struct.pack("<i", to - (at + 5)) + b"\x90" * (length - 5))


# ---------------------------------------------------------------- Fish Tycoon

if E is not None and FISH_EXE.is_file():
    import test_extra_tanks as XT
else:                                                                  # pragma: no cover
    XT = None

FISH_BASE, TANK, SLOT = 0x390, 0x51EC, 0x288
S_EARNED, S_SOLD, S_TANK, S_MONEY = 0x20, 0x28, 0x384, 0x38C
SPECIES = 0x14B40
ASKING = 40


def treated(record: bytes) -> bytes:
    rec = bytearray(record)
    struct.pack_into("<I", rec, F_MARK, MARK)
    return bytes(rec)


def entry_at(state: int, body: int, fin: int) -> int:
    return state + SPECIES + (body * 31 + fin) * 40


@needs(FISH_EXE)
class FishSales(unittest.TestCase):
    """The stock sale roll (0x424240) and sale (0x424010) with DS Store Items' sale hook (0x4244D4) and
    Extra Tanks' selling tanks, both DLLs rebuilt from source and run together."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_ds_store", FISH_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def rig(self, rolls=None, exe: bytes | None = None):
        rig = XT.Rig()
        emu = rig.emu
        if exe is not None:                                            # a patched executable's code
            for rva, raw, raw_size in E.pe_image(exe)[2]:
                emu.uc.mem_write(0x400000 + rva, exe[raw:raw + raw_size])
        emu.write32(0x0045ABDC, rig.state)
        scene = emu.alloc(0x100)
        emu.write32(scene + 0x70, rig.state)
        emu.write32(scene + 0x6C, rig.holder)
        emu.write32(rig.sym["_prev_roll"], 0x00424240)
        for va, pop in ((0x00413C50, 0), (0x00415320, 0), (0x00425120, 0), (0x0040AE20, 4),
                        (0x00415DF0, 0xC), (0x00415E70, 4), (0x00413B00, 0xC)):
            emu.hook(va, lambda e: 0, pop)
        if rolls is not None:
            def roll(e) -> int:
                rig.rolls.append(e.arg(0))
                return rolls(e.arg(0))
            emu.hook(0x00403240, roll, 0)
        for body in range(21):
            for fin in range(21):
                emu.write32(entry_at(rig.state, body, fin) + 0x20, ASKING)
                emu.write32(entry_at(rig.state, body, fin) + 0x24, ASKING)
        rig.set(S_MONEY, 1000)
        rig.set(0x26C, 2)                                              # Advertising level 2
        rig.store, rig.store_imports = map_second(emu, self.dll, self.symbols)
        rig.ds_entries = {}

        def ds_module(e) -> int:
            return 0x6D000000 if e.wstring(e.arg(0)) == "DS Exclusive Fish.dll" else 0
        ds_entry = emu.thunk()
        emu.hook(ds_entry, lambda e: rig.ds_entries.get((e.arg(1), e.arg(2)), 0), 12)
        emu.hook(rig.store_imports["GetModuleHandleW"], ds_module, 4)
        emu.hook(rig.store_imports["GetProcAddress"],
                 lambda e: ds_entry if e.cstring(e.arg(1)) == b"FtfpDsFishEntry" else 0, 8)
        branch(emu, 0x4244D4, rig.store["@on_fish_sale@12"], 5, 0xE8)      # SITE_SALE: call
        branch(emu, 0x420622, rig.store["_stub_death"], 10)                 # SITE_DEATH
        return rig, scene

    def roll(self, rig, scene, browsing: int = 10) -> None:
        rig.emu.write32(scene + 0x58, 0)                               # a new second, no pause
        rig.emu.call(rig.sym["@roll_hook@12"], browsing, ecx=scene)

    def mark(self, rig, at: int) -> int:
        return rig.emu.read32(at + F_MARK)

    def test_a_treated_fish_from_the_sale_tank_pays_the_max_an_untreated_one_its_asking_price(self) -> None:
        for dosed, paid in ((True, 475), (False, ASKING)):
            rig, scene = self.rig(rolls=lambda n: 0)
            guppy = XT.fish(XT.NOW, 7, 7, 25, 90, 60)                  # the Golden Guppy: 2 x 238 - 1
            rig.put_tank(2, XT.block_with({5: treated(guppy) if dosed else guppy}))
            self.roll(rig, scene)
            self.assertEqual(rig.get(S_MONEY), 1000 + paid, dosed)
            self.assertEqual(rig.get(S_EARNED), paid, "Money Earned")
            self.assertEqual(rig.emu.read32(scene + 0x28), paid, "the sold fish's price in the selling scene")
            self.assertEqual(rig.get(S_SOLD), 1)
            self.assertEqual(rig.emu.read32(entry_at(rig.state, 7, 7) + 0x20), ASKING, "the asking price is back")
            at = rig.state + FISH_BASE + 2 * TANK + 5 * SLOT
            self.assertEqual((rig.emu.read32(at), self.mark(rig, at)), (0, 0), "sold: gone, and no mark left")

    def test_a_treated_fish_from_tanks_4_to_6_pays_the_max(self) -> None:
        for e in range(3):
            rig, scene = self.rig(rolls=lambda n: 0)
            rig.var("_selling", 1 << e)
            rig.put_extra(e, XT.block_with({3: treated(XT.fish(XT.NOW, 7, 7, 25, 90, 60)),
                                            7: XT.fish(XT.NOW, 6, 6, 30, 90, 60)}))
            sale_before = rig.tank(2)
            self.roll(rig, scene)
            self.assertEqual(rig.get(S_MONEY), 1000 + 475, e)
            self.assertEqual(struct.unpack_from("<II", rig.extra(e), 3 * SLOT)[0], 0, "sold out of its own block")
            self.assertEqual(struct.unpack_from("<I", rig.extra(e), 3 * SLOT + F_MARK)[0], 0)
            self.assertEqual(rig.tank(2), sale_before, "the Sale Tank is untouched")

    def test_a_treated_ds_fish_pays_its_ds_max(self) -> None:
        """A DS body's entry is DS Exclusive Fish's (FtfpDsFishEntry), as the sale's price reads are."""
        rig, scene = self.rig(rolls=lambda n: 0)
        body, fin = 29, 29                                            # Moorish Idle: DS 17 + 15 + 10
        at = entry_at(rig.state, body, fin)                            # where DS Fish sends the sale's reads
        rig.emu.write32(at + 0x20, ASKING)
        rig.emu.write32(at + 0x24, ASKING)
        rig.ds_entries[(body, fin)] = at
        rig.put_tank(2, XT.block_with({0: treated(XT.fish(XT.NOW, body, fin, 25, 90, 60))}))
        self.roll(rig, scene)
        expected = BF.FishModel(extras=True).prices((body, fin), "max").highest_selling
        self.assertGreater(expected, ASKING)
        self.assertEqual(rig.get(S_MONEY), 1000 + expected)
        self.assertEqual(rig.emu.read32(at + 0x20), ASKING)

    def test_with_bigger_tanks_slot_30_pays_the_max(self) -> None:
        import tycoon_fix_patcher as combined
        import fish_patcher
        manifest = combined.load_manifest("fish")
        exe30, _ = fish_patcher.apply_patch_bytes(FISH_EXE.read_bytes(),
                                                  fish_patcher.active_patch_records(manifest, {"bigger_tanks"}))
        rig, scene = self.rig(rolls=lambda n: 0, exe=exe30)
        rig.put_tank(2, XT.block_with({29: treated(XT.fish(XT.NOW, 7, 7, 25, 90, 60))}))
        self.roll(rig, scene)
        self.assertEqual(rig.get(S_MONEY), 1000 + 475)

    def test_the_sale_chance_and_timing_are_unchanged(self) -> None:
        """The same dice give the same rolls and the same fish sold, second by second; only the money
        paid differs (Random(900) against T, the 5-second pause)."""
        results = []
        for dosed in (False, True):
            rig, scene = self.rig()                                    # the rig's own dice, seed 1
            mark = treated if dosed else (lambda r: r)
            rig.var("_selling", 0b001)
            rig.put_tank(2, XT.block_with({s: mark(XT.fish(XT.NOW, 7, 7, 25, 90, 60)) for s in range(0, 10, 2)}))
            rig.put_extra(0, XT.block_with({s: mark(XT.fish(XT.NOW, 7, 7, 25, 90, 60)) for s in range(1, 8, 3)}))
            sold, money = [], []
            for second in range(40):
                before = (rig.tank(2), rig.extra(0))
                self.roll(rig, scene)
                after = (rig.tank(2), rig.extra(0))
                sold.append(tuple((t, s) for t in range(2) for s in range(21)
                                  if struct.unpack_from("<I", before[t], s * SLOT)[0]
                                  and not struct.unpack_from("<I", after[t], s * SLOT)[0]))
                money.append(rig.get(S_MONEY))
            results.append((list(rig.rolls), sold, money))
        (rolls0, sold0, money0), (rolls1, sold1, money1) = results
        self.assertEqual(rolls1, rolls0, "the same dice, in the same order")
        self.assertEqual(sold1, sold0, "the same fish sold in the same seconds")
        sales = sum(len(s) for s in sold0)
        self.assertGreater(sales, 0)
        self.assertEqual(money0[-1] - 1000, sales * ASKING)
        self.assertEqual(money1[-1] - 1000, sales * 475)

    # ------------------------------------------------------------ the mark: set, kept, cleared
    def test_a_dose_marks_the_fish_it_heals_not_the_dead_nor_the_newborns(self) -> None:
        rig, scene = self.rig()
        rig.set(S_TANK, 0)
        adult, young = XT.fish(XT.NOW, 4, 8, 30), XT.fish(XT.NOW, 6, 6, 5)
        dead = XT.fish(XT.NOW, 2, 2, 25, health=0)
        mother = XT.fish(XT.NOW, 4, 4, 30, due=31, mate=(8, 8))
        rig.put_tank(0, XT.block_with({0: adult, 1: young, 2: dead, 3: mother}))
        rig.emu.call(rig.store["_rgh_dose"], rig.impl)
        tank = rig.tank(0)
        marks = [struct.unpack_from("<I", tank, s * SLOT + F_MARK)[0] for s in range(6)]
        live = [struct.unpack_from("<I", tank, s * SLOT)[0] != 0 for s in range(6)]
        self.assertEqual(marks[:4], [MARK, MARK, 0, MARK])
        self.assertTrue(live[4], "the mother gave birth")
        self.assertEqual(marks[4:], [0, 0], "the newborn is not treated")

    def test_the_mark_follows_the_fish(self) -> None:
        rig, scene = self.rig()
        fish = treated(XT.fish(XT.NOW, 7, 7, 25))
        # The stock move between tanks (0x41EFF0): AddFish into the target, REMOVE_FISH from the source.
        rec = rig.emu.alloc(SLOT)
        rig.put_tank(0, XT.block_with({4: fish}))
        rig.emu.uc.mem_write(rec, rig.tank(0)[4 * SLOT: 5 * SLOT])
        slot = rig.emu.call(0x00419C50, 1, rec, ecx=rig.state)
        rig.emu.call(0x00418E20, 0, 4, ecx=rig.state)
        self.assertEqual(rig.tank(1)[slot * SLOT: (slot + 1) * SLOT], fish)
        # The game's own field copy (0x41E850), the isolation tank's AddFish, the record copy as is.
        copy = rig.emu.alloc(SLOT)
        rig.emu.call(0x0041E850, rig.state + FISH_BASE + TANK + slot * SLOT, copy)
        self.assertEqual(rig.emu.read32(copy + F_MARK), MARK)
        self.assertEqual(rig.emu.call(0x00419C50, 3, copy, ecx=rig.state), 0)
        self.assertEqual(struct.unpack_from("<I", rig.tank(3), F_MARK)[0], MARK)
        # A drop on Tank Four's button (Extra Tanks' release hook), then that tank on screen and back.
        mover = XT.MovingFish()
        rig.put_tank(1, XT.block_with({3: fish}))
        rig.set(S_TANK, 1)
        rig.var("_page", 1)
        mover.hold(rig, 2, 1, 3)
        rig.emu.call(rig.sym["@release_hook@16"], 640, 20, ecx=rig.impl)
        self.assertEqual(rig.extra(1)[:SLOT], fish, "in Tank Four with its mark")
        rig.emu.uc.mem_write(rig.impl + 0xC8, b"\0\0\0\0\0")
        rig.emu.call(rig.sym["@mouse_hook@20"], 2, 670, 20, ecx=rig.impl)   # Tank Four on screen
        rig.emu.call(rig.sym["@mouse_hook@20"], 3, 670, 20, ecx=rig.impl)
        self.assertEqual(rig.tank(0)[:SLOT], fish, "swapped into Tank One's place")
        rig.var("_page", 0)
        rig.emu.uc.mem_write(rig.impl + 0xC8, b"\x01")
        rig.emu.call(rig.sym["@mouse_hook@20"], 3, 550, 20, ecx=rig.impl)   # Tank One again
        self.assertEqual(rig.extra(1)[:SLOT], fish, "and back")
        # ClonaFish: the clone is the whole record, mark and all; an untreated fish's clone is not treated.
        rig.set(S_TANK, 0)
        plain = XT.fish(XT.NOW, 5, 5, 25)
        rig.put_tank(0, XT.block_with({0: fish, 1: plain}))
        self.assertEqual(rig.emu.call(rig.store["_new_chemical"], rig.impl, 31), 1)
        tank = rig.tank(0)
        self.assertEqual(tank[2 * SLOT: 3 * SLOT], fish)
        self.assertEqual(tank[3 * SLOT: 4 * SLOT], plain)

    def test_the_mark_is_saved_and_loaded(self) -> None:
        """The save is the state from + 8 (0x419100); the game's own Load (0x41AE70) brings it back."""
        rig, scene = self.rig()
        rig.put_tank(2, XT.block_with({9: treated(XT.fish(XT.NOW, 7, 7, 25))}))
        body = bytes(rig.emu.uc.mem_read(rig.state + 8, 0x1E3C8))
        other, _ = self.rig()
        other.emu.hook_fish_save_read(body)
        other.emu.call(0x0041AE70, 4, ecx=other.state)
        self.assertEqual(other.emu.read32(other.state + FISH_BASE + 2 * TANK + 9 * SLOT + F_MARK), MARK)

    def test_death_clears_the_mark_in_every_tank(self) -> None:
        rig, scene = self.rig()
        dying = treated(XT.fish(XT.NOW, 1, 1, 25, health=1, food=0, disease=2))   # rare genes: -6 a step
        healthy = treated(XT.fish(XT.NOW, 4, 8, 25, health=90, food=60))
        rig.put_tank(0, XT.block_with({0: dying, 1: healthy}))
        rig.put_extra(1, XT.block_with({0: dying}))                    # Tank Five, updated off screen
        rig.tick()
        tank, held = rig.tank(0), rig.extra(1)
        self.assertLessEqual(struct.unpack_from("<i", tank, 0x3C)[0], 0, "it died")
        self.assertEqual(struct.unpack_from("<I", tank, F_MARK)[0], 0)
        self.assertEqual(struct.unpack_from("<I", tank, SLOT + F_MARK)[0], MARK, "the living keep theirs")
        self.assertEqual(struct.unpack_from("<I", held, F_MARK)[0], 0)
        # Revived, it is not treated (a mark from before is cleared by the potion too).
        rig.set(S_TANK, 0)
        rig.emu.write32(rig.state + FISH_BASE + F_MARK, MARK)
        rig.emu.call(rig.store["_new_chemical"], rig.impl, 30)
        self.assertGreater(rig.emu.read32(rig.state + FISH_BASE + 0x3C), 0)
        self.assertEqual(rig.emu.read32(rig.state + FISH_BASE + F_MARK), 0)

    def test_the_trash_clears_the_mark(self) -> None:
        rig, scene = self.rig()
        for tank in range(4):
            rig.put_tank(tank, XT.block_with({6: treated(XT.fish(XT.NOW, 7, 7, 25))}))
            rig.emu.call(rig.store["_fish_trashed"], rig.impl, tank, 6)
            self.assertEqual(rig.emu.read32(rig.state + FISH_BASE + tank * TANK + 6 * SLOT + F_MARK), 0, tank)


# ---------------------------------------------------------------- Plant Tycoon

if E is not None and PLANT_EXE.is_file():
    import test_extra_greenhouses as XG
else:                                                                  # pragma: no cover
    XG = None

POTS_AT, POT, POTS = 0x2188, 0x5600, 15
S_CASH, S_PLANT_EARNED, S_PLANTS_SOLD = 0x217C, 0x34, 0x38


def site_length(name: str) -> int:
    import re
    header = (ROOT / "native" / "ftfp_plant_upgrades" / "upgrade_sites.h").read_text(encoding="utf-8")
    return int(re.search(rf"#define SITE_{name}_LEN (\d+)", header).group(1))


@needs(PLANT_EXE)
class PlantSales(unittest.TestCase):
    """The stock sale (0x435C70) and buy roll with Store Upgrades and Items' sale stubs (0x435CF2,
    0x435D12), death untag (0x42DF91) and planting (0x42FCDD) written in, beside Extra Greenhouses."""

    @classmethod
    def setUpClass(cls) -> None:
        XG._build()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", PLANT_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def game(self, seed: int = 3):
        game = XG.Game(seed)
        emu = game.emu
        game.upgrades, _ = map_second(emu, self.dll, self.symbols)
        for va, name, stub in ((0x435CF2, "SALE_RECORD", "_stub_sale_record"), (0x435D12, "SALE_CASH", "_stub_sale_cash"),
                               (0x42DF91, "DEAD_UNTAG", "_stub_dead_untag"), (0x42FCDD, "PLANT_SEED", "_stub_plant_seed")):
            branch(emu, va, game.upgrades[stub], site_length(name))
        emu.write32(0x0049333C, game.state)
        return game

    def treat(self, game, g: int, k: int) -> None:
        """One Radioactive Plant Formula dose, the DLL's own (apply_chemical, chemical 36)."""
        emu = game.emu
        game.arrange(g)
        plant = emu.call(XG.GET_PLANT, k // 5, k % 5, ecx=game.manager)
        emu.call(game.upgrades["_apply_chemical"], game.scene, k % 5, k // 5, plant, 36)
        game.arrange(XG.HOME)

    def nursery(self, game, visitors: int = 0) -> int:
        emu = game.emu
        nursery = emu.alloc(0xB00)
        emu.write32(nursery + 0xA3C, game.state)
        emu.write32(nursery + 0xA44, game.manager)
        emu.write32(nursery + 0xA4C, emu.alloc(0x40))
        emu.hook(0x0043ACD0, lambda e: visitors)
        emu.hook(0x00449F00, lambda e: emu.alloc(0x10))
        return nursery

    def test_a_treated_plant_sold_in_nursery_1_pays_the_max(self) -> None:
        for dosed in (True, False):
            game = self.game()
            emu = game.emu
            game.plant(0, 4, 11, 10)                                   # a Fabled Lemonbush, V = 250
            game.tick(7200)
            if dosed:
                self.treat(game, 0, 4)
            pot = game.pot(0, 4)
            self.assertEqual(emu.uc.mem_read(pot + POT_MARK, 1)[0], RADIOACTIVE if dosed else 0)
            asking = emu.read32(game.state + ((11 + 0x37) * 26 + 10) * 4)
            cash, earned, sold = (emu.read32(game.state + o) for o in (S_CASH, S_PLANT_EARNED, S_PLANTS_SOLD))
            emu.call(0x00435C70, 0, 0, 0, 4, ecx=self.nursery(game))
            paid = 1186 if dosed else asking
            self.assertGreater(1186, asking)
            self.assertEqual(emu.read32(game.state + S_CASH) - cash, paid, dosed)
            self.assertEqual(emu.read32(game.state + S_PLANT_EARNED) - earned, paid, "Money Earned")
            self.assertEqual(emu.read32(game.state + S_PLANTS_SOLD) - sold, 1)
            self.assertEqual(emu.uc.mem_read(pot + POT_MARK, 1)[0], 0, "the mark is spent")

    def test_the_bomb_treats_every_live_plant(self) -> None:
        game = self.game()
        emu = game.emu
        for k in (0, 6, 14):
            game.plant(0, k, 11, 10)
        game.tick(7200)
        emu.write32(game.pot(0, 6) + 0x24, 0)                          # one is dead: the bomb skips it
        game.arrange(0)
        emu.call(game.upgrades["_apply_chemical"], game.scene, 0, 0, 0, 39)
        game.arrange(XG.HOME)
        marks = [emu.uc.mem_read(game.pot(0, k) + POT_MARK, 1)[0] for k in (0, 6, 14, 3)]
        self.assertEqual(marks, [RADIOACTIVE, 0, RADIOACTIVE, 0])

    def test_a_treated_plant_sold_off_screen_in_nursery_2_pays_the_max(self) -> None:
        """As test_extra_greenhouses' off-screen sale: Nursery 1 on screen, the treated plant in Nursery 2,
        sold by Extra Greenhouses' own roll of the other nurseries."""
        game = self.game(2)
        emu = game.emu
        game.plant(4, 9, 7, 7)                                         # the Rose of Joy, as there
        game.tick(7200)
        game.tick(7200)
        self.assertGreater(struct.unpack_from("<i", game.pot_bytes(4, 9), 0x24)[0], 0)
        self.treat(game, 4, 9)
        self.assertEqual(game.pot_bytes(4, 9)[POT_MARK], RADIOACTIVE)
        best = BP.load(None).prices((7, 7), "max").highest_selling
        emu.write32(emu.sym("_nurseries_on"), 1)
        emu.write32(emu.sym("_nurseries"), 1)
        for k in range(POTS):                                          # Nursery 1's spots: sold already
            at = game.pot(1, k)
            emu.write8(at + XG.PLANTED, 1)
            emu.write32(at + XG.FOLIAGE, 5)
            emu.write32(at + XG.FLOWER, 5)
            emu.write8(at + 0x9E, 1)
        XG.NurseryLimitTests().toggle(game, 4, 9)                      # for sale: Nursery 2
        nursery = self.nursery(game, visitors=6)
        emu.uc.mem_write(0x435D21, b"\xE8" + struct.pack("<i", emu.sym("@sale_visitors@8") - (0x435D21 + 5)))
        emu.hook(0x00440940, lambda e: 0, 4)
        emu.hook(XG.RANDOM, lambda e: 0)
        game.show(0, active=2)
        cash = emu.read32(game.state + S_CASH)
        emu.call(emu.sym("@sales_roll@12"), 6, ecx=nursery)
        self.assertGreater(best, emu.read32(game.state + ((7 + 0x37) * 26 + 7) * 4))
        self.assertEqual(emu.read32(game.state + S_CASH) - cash, best)
        game.show(0, active=0)
        after = game.pot_bytes(4, 9)
        self.assertEqual((after[0x9E], after[POT_MARK]), (1, 0), "sold in its own pot, the mark spent")

    def test_the_mark_follows_the_plant_and_its_record(self) -> None:
        game = self.game()
        emu = game.emu
        game.plant(0, 4, 11, 10)
        game.tick(7200)
        self.treat(game, 0, 4)
        mover = XG.MoveTests()
        game.show(0)
        mover.drop_on_arrow(game, True, 4)                             # to Greenhouse 2, pot 4
        game.show(0, active=0)
        self.assertEqual(game.pot_bytes(1, 4)[POT_MARK], RADIOACTIVE)
        XG.NurseryLimitTests().toggle(game, 1, 4)                      # tagged for sale: still marked
        game.show(1, active=2)
        game.show(0, active=0)
        self.assertEqual(game.pot_bytes(1, 4)[POT_MARK], RADIOACTIVE)
        # The save: Extra Greenhouses' sidecar keeps Greenhouses 2-6 whole, and the load brings them back.
        disk = XG.SidecarTests().files(game)
        game.emu.hook(0x00403690, lambda e: 1, 0xC)
        game.emu.call(game.emu.sym("_stub_save"), 4, ecx=game.state, edx=4)
        emu.uc.mem_write(game.pot(1, 4), bytes(POT))
        game.emu.call(game.emu.sym("_on_loaded"), game.state, 4)
        self.assertTrue(disk)
        self.assertEqual(game.pot_bytes(1, 4)[POT_MARK], RADIOACTIVE)

    def test_death_and_a_new_plant_clear_the_mark_and_the_revival_mark_still_works(self) -> None:
        game = self.game()
        emu = game.emu
        game.plant(0, 4, 11, 10)
        game.plant(0, 5, 11, 10)
        game.tick(7200)
        self.treat(game, 0, 4)
        self.treat(game, 0, 5)
        emu.write8(game.pot(0, 5) + XG.FOR_SALE, 1)                     # pot 5 is for sale when it dies
        for k in (4, 5):
            emu.write32(game.pot(0, k) + 0x24, 0)                      # both die
        game.tick(600)
        self.assertEqual(game.pot_bytes(0, 4)[POT_MARK], 0, "dead: no longer treated")
        self.assertEqual(game.pot_bytes(0, 5)[POT_MARK], SALE_KEPT, "the Revival Potion's mark, as before")
        game.plant(0, 5, 3, 3)                                         # replanted
        self.assertEqual(game.pot_bytes(0, 5)[POT_MARK], 0)
        game.plant(0, 6, 11, 10)
        game.tick(600)
        self.treat(game, 0, 6)
        game.plant(0, 6, 3, 3)                                         # a treated plant's pot replanted
        self.assertEqual(game.pot_bytes(0, 6)[POT_MARK], 0)


# ---------------------------------------------------------------- the texts

def _fish_items():
    from test_consumable_doses import fish_items
    return fish_items()


def _plant_descriptions():
    from test_consumable_doses import plant_descriptions
    return plant_descriptions()


class Texts(unittest.TestCase):
    def test_the_store_descriptions(self) -> None:
        english, german = _fish_items()["Radioactive Growth Hormone"]
        self.assertTrue(english.replace("\n", " ").endswith(f"{FISH_SENTENCE} Contains 3 doses."), english)
        self.assertTrue(german.replace("\n", " ").endswith(f"{FISH_SENTENCE_DE} Reicht für 3 Behandlungen."), german)
        for name in ("FORMULA_DESC", "BOMB_DESC"):
            text = _plant_descriptions()[name]
            self.assertTrue(text.replace("\n", " ").endswith(f"{PLANT_SENTENCE} Contains 3 doses. "), (name, text))
        # The rest of the owner's wording is kept.
        self.assertIn("Every fish in your tank gets full health and no sickness, young ones grow up at once, and "
                      "pregnant ones give birth to babies.", english.replace("\n", " "))
        self.assertIn("Causes maximum flower and plant growth and restores full health to plants. No more dead "
                      "leaves! Always 5 seeds!", _plant_descriptions()["FORMULA_DESC"].replace("\n", " "))
        self.assertIn("The Radioactive Plant Formula for every plant in the greenhouse.",
                      _plant_descriptions()["BOMB_DESC"].replace("\n", " "))

    def test_the_descriptions_fit_the_panels(self) -> None:
        """At most 5 lines (the stock store's longest is 4, Plant's 5 with "Contains"), each no longer than
        the stock texts' longest (Fish 46 characters), Plant 47: the formula's text with the owner's
        sentence ("Allows treated plants to sell at max price, regardless of their set value.") and
        "No more dead leaves!" kept on one line needs 47 at 5 lines; checked in the game, its dialog's
        47-character line ends well inside the red panel."""
        for text in _fish_items()["Radioactive Growth Hormone"]:
            lines = text.split("\n")
            self.assertLessEqual(len(lines), 5, text)
            self.assertLessEqual(max(map(len, lines)), 46, text)
        for name in ("FORMULA_DESC", "BOMB_DESC"):
            lines = _plant_descriptions()[name].rstrip("\n").split("\n")
            self.assertLessEqual(len(lines), 5, name)
            self.assertLessEqual(max(map(len, lines)), 47, name)

    def test_the_patcher_descriptions(self) -> None:
        for game, setting, words in (("fish", "ds_store", "Treated fish sell for the highest possible price"),
                                     ("plant", "plant_upgrades", "treated plants sell for the highest possible price")):
            manifest = json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
            text = next(s for s in manifest["settings"] if s["id"] == setting)["description"]
            self.assertIn(words, text)
            self.assertIn("Highest selling with Max effects", text)

    def test_game_mechanics_entries(self) -> None:
        import game_mechanics as GM
        rules = {
            "fish": {
                "Radioactive Growth Hormone: not in the unpatched game.": ("ds_store", (
                    "Treated fish sell for the highest possible price", "2B - 1", "Advertising",
                    "decided by your asking price", "Random(900)", "real-time second", "ClonaFish clone",
                    "Tanks 4-6", "saves and loads", "real time or age steps", "Babies are never treated",
                    "dies", "thrown away", "$475")),
                "You are paid your asking price P, whatever it is, even 0.": ("ds_store", (
                    "highest selling price", "Tanks 4-6", "chance to sell")),
                "ClonaFish: not in the unpatched game.": ("ds_store", ("treated too",)),
            },
            "plant": {
                "Radioactive Plant Formula: not in the unpatched game.": ("plant_upgrades", (
                    PLANT_SENTENCE, "Treated plants sell for the highest possible price", "below 2V", "decided by your asking "
                    "price", "Random(1300)", "2 real-time seconds", "Extra Greenhouses", "saves and loads",
                    "real time or age units", "nurseries not on screen", "dies", "planted in its pot", "$1186")),
                "Radioactive Plant Formula Bomb: not in the unpatched game.": ("plant_upgrades", (
                    PLANT_SENTENCE, "treated", "highest selling price")),
            },
        }
        for game, facts in rules.items():
            page = GM.load_page(game)
            found = {f.text: f for group in page.groups for f in group.facts}
            for text, (setting, words) in facts.items():
                patched = dict(found[text].patched)[setting]
                for word in words:
                    self.assertIn(word, patched, (game, text, word))
        plant = GM.load_page("plant")
        selling = next(g for g in plant.groups if g.title == "Selling and visitors")
        first = dict(selling.facts[0].patched)["plant_upgrades"]
        self.assertIn("highest selling price", first)
        rendered = {g: GM.render_text(GM.load_page(g)) for g in ("fish", "plant")}
        self.assertIn("sold from Tanks 4-6 is paid its species' highest selling price", rendered["fish"])
        self.assertIn("highest selling price there too", rendered["plant"])         # the extra nurseries
        self.assertIn("Treated fish sell for the highest possible price", rendered["fish"])
        self.assertIn("Treated plants sell for the highest possible price", rendered["plant"])

    def test_the_committed_dlls_carry_the_texts(self) -> None:
        fish = FISH_DLL.read_bytes()
        for text in _fish_items()["Radioactive Growth Hormone"]:
            self.assertIn(text.encode("latin-1") + b"\0", fish)
        plant = PLANT_DLL.read_bytes()
        for name in ("FORMULA_DESC", "BOMB_DESC"):
            self.assertIn(_plant_descriptions()[name].encode("latin-1") + b"\0", plant)


if __name__ == "__main__":
    unittest.main()
