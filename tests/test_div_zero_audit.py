"""Integer divide-by-zero audit of vanilla Fish Tycoon.exe and Plant Tycoon.exe.

Virtual Families 1 crashes to the desktop when its bank dialog's 7-day chart
divides by a value that is 0 (money under $0.43 and nobody earning pay). These
tests pin down that neither tycoon game has that kind of crash: every `div` and
`idiv` in each executable's .text is listed and put in a category, and the
sites whose divisor comes from game data are run in Unicorn.

Fish Tycoon has 190 sites, Plant Tycoon 199. In both, 60 are the static C
runtime's own (time conversion by 400/100/7, printf's radix, 64-bit _alldiv
helpers; nothing in the game code calls those helpers). The game code's sites:

  const         the divisor is a nonzero immediate loaded in the same block
                (checked here instruction by instruction);
  random        Random(n) itself: it divides only when 1 <= n <= 0x7FFF
                (unsigned n - 1 <= 0x7FFE); n <= 0 takes the floating-point
                path, which returns 0, so Random(0) cannot divide (run below);
  blit          the engine's scaled draw: the divisor is the box's pixel count,
                summed from do-while loop trip counts (at least 1 each);
  frame_rate    1000 / the game class's frame rate (a virtual returning a
                constant);
  sprite        sprite sheets and animations: frame columns and rows passed as
                code constants, or the shipped image's size over them;
  archive       the engine's packed-file read (count = bytes / size; every
                caller passes size 1 or a length it checked for 0);
  guarded       a test or compare right before skips the division at 0;
  key_check     the registration code's hash: the divisor is the typed name's
                length, checked for 0 by the caller (or 0x22);
  one_or_two    Plant Tycoon's fades: the divisor is 1 + (a flag), 1 or 2;
  slide_steps   Plant Tycoon's sliding panels: the step count is the 6th
                argument of 0x421190, `push 5` at all 14 calls (checked);
  game_speed    Fish Tycoon's age step: seconds / 60 / the game speed (state +
                0x1E168), run for every live fish. The speed is 0 in no state
                the game makes: a new game sets 10, the options dialog writes
                only 9999, 10, 15, 5 (or 8 when no button is checked), loading
                a save turns anything over 100 into 10, and a save must be the
                full 0x1E3C8 bytes the game writes. Shown here: the real code
                faults with speed 0 and gives the stock count with 5/10/15, and
                every write to the field is one of those.

So no site can divide by 0 in play or from a save the game writes; nothing in
Fix Vanilla Bugs changes for this. The patcher's own code was checked too: no
division in any executable patch of either manifest (also tested here), and
the native DLLs' divisions are by constants or behind a check (the one
unchecked divisor, Time Warp's report of Fish Tycoon's speed, has the same
never-0 speed).
"""

from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path

try:
    import capstone
    from capstone import x86 as cs_x86
except ImportError:  # CI has only pytest; these tests need Capstone and Unicorn
    capstone = None
try:
    from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_INTR, UC_MODE_32, Uc, UcError
    from unicorn import x86_const as X
except ImportError:
    Uc = None

ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
FISH = VANILLA / "Fish Tycoon" / "Fish Tycoon.exe"
PLANT = VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"


def _r(*pairs: tuple[int, int]) -> set[int]:
    return {a for lo, hi in pairs for a in range(lo, hi)}


# The game code ends where the C runtime starts; every site from there on is the runtime's.
CRT_START = {"fish": 0x42ABFD, "plant": 0x44ECFE}
TOTAL = {"fish": 190, "plant": 199}
CRT_SITES = 60

FISH_SITES = {
    "const": {0x40FACB, 0x4164F9, 0x41650B, 0x416520, 0x416535, 0x416555, 0x4165EA, 0x41661A, 0x41662E,
              0x416642, 0x416656, 0x4166FC, 0x416725, 0x416739, 0x41674D, 0x416761, 0x41680F, 0x416871,
              0x416886, 0x41689B, 0x416930, 0x416A4A, 0x416A5C, 0x416A70, 0x41A394, 0x41A3D0, 0x41A405,
              0x41A43A, 0x41A46F, 0x41A4A4, 0x41DB9E},
    "random": {0x403258},
    "blit": _r((0x4041C0, 0x405FC0), (0x405FC0, 0x4073A0)),       # 0x4041C0 (43 sites), 0x405FC0 (26)
    "frame_rate": {0x40792B},
    "sprite": {0x407F23, 0x407F32, 0x407FB3, 0x407FC2, 0x409601, 0x409613, 0x40962C, 0x409718, 0x409727,
               0x409805, 0x409812, 0x422DF7},
    "archive": {0x40D72E, 0x40D760},
    "guarded": {0x419210, 0x426E34},
    "key_check": {0x41A265, 0x41A2A7, 0x41A2D6, 0x41A311, 0x41A4D9, 0x41A50E,
                  0x42968C, 0x4296CC, 0x42970D, 0x429750},
    "game_speed": {0x41FFFF, 0x420953},
}

PLANT_SITES = {
    "const": {0x410C6B, 0x419507, 0x41BAC6, 0x4235D2, 0x4235F8, 0x4246B8, 0x425873, 0x425BE8, 0x425D0F,
              0x425F31, 0x42619A, 0x4262E6, 0x4265FB, 0x4272F0, 0x42818A, 0x4290AF, 0x429119, 0x4295D3,
              0x42D5A0, 0x42EE6A, 0x42F499, 0x430063, 0x43083F, 0x432F50, 0x433AAA, 0x433B83, 0x433C9A,
              0x433D9A, 0x433EB9, 0x434454, 0x4344A5, 0x43466E, 0x434AED, 0x437F3F},
    "random": {0x4033C8},
    "blit": _r((0x404610, 0x406280), (0x406280, 0x407520)),       # 0x404610 (43 sites), 0x406280 (26)
    "frame_rate": {0x407ABB},
    "sprite": {0x4082B3, 0x4082C2, 0x408343, 0x408352, 0x4086B3, 0x4086C2, 0x408783, 0x408792, 0x409EF1,
               0x409F03, 0x409F1C, 0x40A008, 0x40A017, 0x40A1CA, 0x40A1D7, 0x40A1E3, 0x40A1EE, 0x40A2D5,
               0x40A2E2, 0x40CD85, 0x40CD9F},
    "archive": {0x40E8CE, 0x40E900},
    "guarded": {0x42D8FC, 0x44B673},
    "key_check": {0x411ECC, 0x411F0C, 0x411F4D, 0x411F90},
    "one_or_two": {0x42013D, 0x42171D, 0x421E8F},
    "slide_steps": {0x42123F, 0x42124E},
}

FISH_SPEED = 0x1E168
# Every write to the speed: the new game, the load's "over 100" reset, two more resets, and the options
# dialog's `mov [eax + 0x1E168], edi`.
FISH_SPEED_WRITES = {0x418AFB: 10, 0x41AAAD: 10, 0x41C2E6: 10, 0x41C2FF: 5, 0x421976: 5, 0x4230D7: None}
# The options dialog's choices for edi (0x422F10, run for message 8 only: `cmp [esp + 4], 8`).
FISH_SPEED_CHOICES = {0x422FD4: 9999, 0x422FEF: 10, 0x42300A: 15, 0x423023: 5}

_cache: dict[str, tuple[bytes, list]] = {}


def _image(path: Path) -> tuple[int, list[tuple[str, int, int, int, int, int]]]:
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    sections = []
    for k in range(count):
        at = pe + 24 + optional + 40 * k
        name = data[at:at + 8].rstrip(b"\0").decode()
        vsize, va, rsize, raw = struct.unpack_from("<IIII", data, at + 8)
        flags = struct.unpack_from("<I", data, at + 36)[0]
        sections.append((name, base + va, vsize, raw, rsize, flags))
    return base, sections


def _code(game: str) -> tuple[bytes, list]:
    if game not in _cache:
        path = FISH if game == "fish" else PLANT
        data = path.read_bytes()
        _, sections = _image(path)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        md.skipdata = True
        md.detail = True
        insns = []
        for _name, va, vsize, raw, rsize, flags in sections:
            if flags & 0x20000000:          # executable: .text only in both games
                insns += [i for i in md.disasm(data[raw:raw + min(vsize, rsize)], va) if i.id != 0]
        _cache[game] = (data, insns)
    return _cache[game]


def _divisions(game: str) -> list:
    return [i for i in _code(game)[1] if i.mnemonic in ("div", "idiv")]


def _branch_targets(insns: list) -> set[int]:
    out = set()
    for i in insns:
        if (i.group(cs_x86.X86_GRP_JUMP) or i.group(cs_x86.X86_GRP_CALL)) and i.operands \
                and i.operands[0].type == cs_x86.X86_OP_IMM:
            out.add(i.operands[0].imm)
    return out


_SUBREGS = {"eax": ("al", "ah", "ax"), "ebx": ("bl", "bh", "bx"), "ecx": ("cl", "ch", "cx"),
            "edx": ("dl", "dh", "dx"), "esi": ("si",), "edi": ("di",), "ebp": ("bp",)}


def _constant_divisor(insns: list, targets: set[int], index: int) -> int | None:
    """The immediate the divisor register was loaded with in the division's own block, or None."""
    division = insns[index]
    operand = division.operands[0]
    if operand.type != cs_x86.X86_OP_REG:
        return None
    reg = division.reg_name(operand.reg)
    names = {reg, *_SUBREGS.get(reg, ())}
    for j in range(index - 1, max(index - 60, 0), -1):
        insn = insns[j]
        if insns[j + 1].address in targets or insn.mnemonic in ("ret", "jmp"):
            return None                     # left the block before finding the load
        written = {insn.reg_name(r) for r in insn.regs_access()[1]}
        if written & names:
            if insn.mnemonic == "mov" and insn.operands[1].type == cs_x86.X86_OP_IMM:
                return insn.operands[1].imm
            return None
    return None


def _ready(path: Path, need_unicorn: bool = False) -> bool:
    return capstone is not None and path.is_file() and (Uc is not None or not need_unicorn)


# ------------------------------------------------------------------ Unicorn

class _Game:
    """The vanilla executable mapped at its image base, with a stack; runs a stretch of its own code."""

    STACK, STACK_SIZE = 0x0F000000, 0x00100000
    DATA, DATA_SIZE = 0x20000000, 0x00100000
    STOP = 0x30000000

    def __init__(self, path: Path) -> None:
        data = path.read_bytes()
        base, sections = _image(path)
        end = max(va + max(vsize, rsize) for _n, va, vsize, _r, rsize, _f in sections)
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(base, (end - base + 0xFFF) & ~0xFFF)
        self.uc.mem_write(base, data[:0x1000])
        for _name, va, vsize, raw, rsize, _flags in sections:
            self.uc.mem_write(va, data[raw:raw + min(vsize, rsize)])
        self.uc.mem_map(self.STACK, self.STACK_SIZE)
        self.uc.mem_map(self.DATA, self.DATA_SIZE)
        self.uc.mem_map(self.STOP, 0x1000)
        self.uc.mem_write(self.STOP, b"\xF4")          # hlt: never reached, the run stops before it
        self.interrupts: list[int] = []
        self.uc.hook_add(UC_HOOK_INTR, self._interrupt)
        self.uc.reg_write(X.UC_X86_REG_ESP, self.STACK + self.STACK_SIZE - 0x1000)

    def _interrupt(self, uc, number, _user) -> None:
        self.interrupts.append(number)
        uc.emu_stop()

    def run(self, start: int, stop: int) -> bool:
        """Run start..stop; True when it got there, False on a CPU fault (interrupt 0 is #DE)."""
        self.interrupts.clear()
        try:
            self.uc.emu_start(start, stop, count=100000)
        except UcError:
            if not self.interrupts:
                self.interrupts.append(-1)
        return not self.interrupts and self.uc.reg_read(X.UC_X86_REG_EIP) == stop

    def call_random(self, random: int, rand: int, n: int, rand_value: int) -> int:
        """Random(n) (cdecl) with the CRT rand() it calls answering rand_value."""
        def fake_rand(uc, address, _size, _user) -> None:
            esp = uc.reg_read(X.UC_X86_REG_ESP)
            back = struct.unpack("<I", uc.mem_read(esp, 4))[0]
            uc.reg_write(X.UC_X86_REG_EAX, rand_value)
            uc.reg_write(X.UC_X86_REG_ESP, esp + 4)
            uc.reg_write(X.UC_X86_REG_EIP, back)
        hook = self.uc.hook_add(UC_HOOK_CODE, fake_rand, begin=rand, end=rand)
        esp = self.STACK + self.STACK_SIZE - 0x1000
        self.uc.mem_write(esp, struct.pack("<II", self.STOP, n & 0xFFFFFFFF))
        self.uc.reg_write(X.UC_X86_REG_ESP, esp)
        try:
            if not self.run(random, self.STOP):
                raise AssertionError(f"Random({n}) faulted: {self.interrupts}")
        finally:
            self.uc.hook_del(hook)
        return self.uc.reg_read(X.UC_X86_REG_EAX)


class DivisionInventory(unittest.TestCase):
    """Every div/idiv of each executable is in exactly one category, and the categories hold."""

    def _check(self, game: str, sites: dict[str, set[int]]) -> None:
        found = {i.address for i in _divisions(game)}
        self.assertEqual(len(found), TOTAL[game])
        crt = {a for a in found if a >= CRT_START[game]}
        self.assertEqual(len(crt), CRT_SITES)
        listed: set[int] = set()
        for category, addresses in sites.items():
            mine = addresses & found if category == "blit" else addresses
            self.assertFalse(mine & listed, category)
            self.assertLessEqual(mine, found, f"{category}: not a division")
            listed |= mine
        self.assertEqual(found - crt, listed, "a division with no category")

    @unittest.skipUnless(capstone is not None and FISH.is_file(), "needs Capstone and vanilla Fish Tycoon")
    def test_fish_sites(self) -> None:
        self._check("fish", FISH_SITES)
        self.assertEqual(len(FISH_SITES["blit"] & {i.address for i in _divisions("fish")}), 69)

    @unittest.skipUnless(capstone is not None and PLANT.is_file(), "needs Capstone and vanilla Plant Tycoon")
    def test_plant_sites(self) -> None:
        self._check("plant", PLANT_SITES)
        self.assertEqual(len(PLANT_SITES["blit"] & {i.address for i in _divisions("plant")}), 69)

    def _check_constants(self, game: str, sites: set[int]) -> None:
        _data, insns = _code(game)
        targets = _branch_targets(insns)
        index = {i.address: k for k, i in enumerate(insns)}
        for address in sorted(sites):
            with self.subTest(site=hex(address)):
                value = _constant_divisor(insns, targets, index[address])
                self.assertIsNotNone(value)
                self.assertNotEqual(value, 0)

    @unittest.skipUnless(capstone is not None and FISH.is_file(), "needs Capstone and vanilla Fish Tycoon")
    def test_fish_constant_divisors(self) -> None:
        self._check_constants("fish", FISH_SITES["const"])

    @unittest.skipUnless(capstone is not None and PLANT.is_file(), "needs Capstone and vanilla Plant Tycoon")
    def test_plant_constant_divisors(self) -> None:
        self._check_constants("plant", PLANT_SITES["const"])

    @unittest.skipUnless(capstone is not None and PLANT.is_file(), "needs Capstone and vanilla Plant Tycoon")
    def test_plant_slide_steps_are_always_5(self) -> None:
        """0x421190(a1..a8) stores a6 at +0x20, the divisor of 0x42123F/0x42124E; every call pushes 5, 4, 4
        as a6, a5, a4 (in that order) on the way to it."""
        data, insns = _code("plant")
        calls = [i.address for i in insns if i.mnemonic == "call" and i.operands
                 and i.operands[0].type == cs_x86.X86_OP_IMM and i.operands[0].imm == 0x421190]
        self.assertEqual(len(calls), 14)
        setup = data[0x21190 + 0x2B:0x21190 + 0x2E]      # 0x4211BB: mov [ecx + 0x20], edx (edx = a6)
        self.assertEqual(setup, b"\x89\x51\x20")
        for call in calls:
            with self.subTest(call=hex(call)):
                # a8 .. a4 are pushed first (push 0, 0, 5, 4, 4, other code between them); two calls
                # share them with their neighbour before a branch, so the window reaches back 0x100.
                pushes = [i.op_str for i in insns if call - 0x100 <= i.address < call and i.mnemonic == "push"]
                runs = [pushes[k:k + 5] for k in range(len(pushes))]
                self.assertIn(["0", "0", "5", "4", "4"], runs)

    @unittest.skipUnless(capstone is not None and FISH.is_file(), "needs Capstone and vanilla Fish Tycoon")
    def test_fish_speed_is_never_written_as_0(self) -> None:
        data, insns = _code("fish")
        writes = {}
        for i in insns:
            if i.mnemonic != "mov" or len(i.operands) != 2 or i.operands[0].type != cs_x86.X86_OP_MEM:
                continue
            if i.operands[0].mem.disp == FISH_SPEED:
                second = i.operands[1]
                writes[i.address] = second.imm if second.type == cs_x86.X86_OP_IMM else None
        self.assertEqual(writes, FISH_SPEED_WRITES)
        self.assertTrue(all(v is None or v > 0 for v in writes.values()))
        for address, value in FISH_SPEED_CHOICES.items():              # mov edi, value
            self.assertEqual(data[address - 0x400000:address - 0x400000 + 5], b"\xBF" + struct.pack("<I", value))
        # The last choice falls back to the handler's first argument, which it has checked is 8.
        self.assertEqual(data[0x2302A:0x2302E], b"\x8B\x7C\x24\x10")        # mov edi, [esp + 0x10]
        self.assertEqual(data[0x22F10:0x22F15], b"\x83\x7C\x24\x04\x08")    # cmp dword [esp + 4], 8
        self.assertEqual(data[0x22F18:0x22F1A], b"\x0F\x85")                # jne (anything else)
        # A loaded save over 100 becomes 10, and a save is read only whole (0x1E3C8 bytes, 0x403350).
        self.assertEqual(data[0x1AAA4:0x1AAB7], bytes.fromhex("83 BE 68 E1 01 00 64 7E 0A"      # cmp speed, 100 ; jle
                                                              "C7 86 68 E1 01 00 0A 00 00 00"))  # speed = 10
        self.assertEqual(data[0x1AF2D:0x1AF32], b"\x68\xC8\xE3\x01\x00")


class DivisionEmulation(unittest.TestCase):
    """The game-data divisors, run in Unicorn: what faults and what each guard does."""

    @unittest.skipUnless(_ready(FISH, True), "needs Capstone, Unicorn and vanilla Fish Tycoon")
    def test_fish_age_step_faults_only_at_speed_0(self) -> None:
        """0x41FFD1..0x420005 for one fish: steps = seconds / 60 / speed (0x41FFFF), with the stock
        `speed > 100` reset of the seconds first. Speed 0 is #DE (the crash); the game's own speeds
        give the stock count."""
        game = _Game(FISH)
        scene, state, fish = game.DATA, game.DATA + 0x1000, 0x400
        for speed, seconds, steps in ((10, 6000, 10), (5, 6000, 20), (15, 54000, 60), (9999, 6000, 0),
                                      (0, 6000, None)):
            with self.subTest(speed=speed):
                game.uc.mem_write(scene + 0x34, struct.pack("<I", state))
                game.uc.mem_write(state + FISH_SPEED, struct.pack("<i", speed))
                game.uc.mem_write(state + fish + 0x394, struct.pack("<I", seconds))
                for reg, value in ((X.UC_X86_REG_ESI, scene), (X.UC_X86_REG_EDI, fish), (X.UC_X86_REG_EBX, 100)):
                    game.uc.reg_write(reg, value)
                finished = game.run(0x41FFD1, 0x420005)
                if steps is None:
                    self.assertFalse(finished)
                    self.assertEqual(game.interrupts, [0])
                    self.assertEqual(game.uc.reg_read(X.UC_X86_REG_EIP), 0x41FFFF)
                else:
                    self.assertTrue(finished, game.interrupts)
                    self.assertEqual(game.uc.reg_read(X.UC_X86_REG_EAX), steps)

    def _random(self, path: Path, random: int, rand: int) -> None:
        game = _Game(path)
        for n, value, expected in ((0, 12345, 0), (-5, 12345, 0), (1, 12345, 0), (7, 12345, 12345 % 7),
                                   (100, 32767, 67)):
            with self.subTest(n=n, rand=value):
                self.assertEqual(game.call_random(random, rand, n, value), expected)

    @unittest.skipUnless(_ready(FISH, True), "needs Capstone, Unicorn and vanilla Fish Tycoon")
    def test_fish_random_0_does_not_divide(self) -> None:
        self._random(FISH, 0x403240, 0x42B808)

    @unittest.skipUnless(_ready(PLANT, True), "needs Capstone, Unicorn and vanilla Plant Tycoon")
    def test_plant_random_0_does_not_divide(self) -> None:
        self._random(PLANT, 0x4033B0, 0x44F908)

    @unittest.skipUnless(_ready(FISH, True), "needs Capstone, Unicorn and vanilla Fish Tycoon")
    def test_fish_guarded_divisions(self) -> None:
        game = _Game(FISH)
        obj = game.DATA
        # 0x419200: [ecx + 0x20] / [ecx + 0x28], 0 when either is 0.
        for count, total, expected in ((0, 50, 0), (4, 50, 12)):
            game.uc.mem_write(obj + 0x20, struct.pack("<ii", total, 0) + struct.pack("<i", count))
            game.uc.mem_write(game.STACK + game.STACK_SIZE - 0x1000, struct.pack("<I", game.STOP))
            game.uc.reg_write(X.UC_X86_REG_ESP, game.STACK + game.STACK_SIZE - 0x1000)
            game.uc.reg_write(X.UC_X86_REG_ECX, obj)
            self.assertTrue(game.run(0x419200, game.STOP), game.interrupts)
            self.assertEqual(game.uc.reg_read(X.UC_X86_REG_EAX), expected)
        # 0x426E24..0x426E3A: [state + 0x44] / [state + 0x3C] only when [state + 0x3C] != 0 (ebx = 0).
        for divisor, expected in ((0, 0), (3, 33)):
            game.uc.mem_write(obj + 0x2C, struct.pack("<I", obj + 0x100))
            game.uc.mem_write(obj + 0x100 + 0x3C, struct.pack("<ii", divisor, 0) + struct.pack("<i", 100))
            game.uc.mem_write(obj + 0x800 - 0x18, struct.pack("<i", -1))
            for reg, value in ((X.UC_X86_REG_ESI, obj), (X.UC_X86_REG_EBX, 0), (X.UC_X86_REG_EBP, obj + 0x800)):
                game.uc.reg_write(reg, value)
            self.assertTrue(game.run(0x426E24, 0x426E3A), game.interrupts)
            self.assertEqual(struct.unpack("<i", game.uc.mem_read(obj + 0x800 - 0x18, 4))[0], expected)

    @unittest.skipUnless(_ready(PLANT, True), "needs Capstone, Unicorn and vanilla Plant Tycoon")
    def test_plant_guarded_divisions(self) -> None:
        game = _Game(PLANT)
        obj = game.DATA
        # 0x44B660..0x44B678: [x + 0x3C] = [x + 0x34] / [x + 0x38], 0 when [x + 0x38] is 0.
        for divisor, expected in ((0, 0), (4, 25)):
            game.uc.mem_write(obj + 0x4C, struct.pack("<I", obj + 0x100))
            game.uc.mem_write(obj + 0x100 + 0x34, struct.pack("<iii", 100, divisor, -1))
            game.uc.reg_write(X.UC_X86_REG_ESI, obj)
            self.assertTrue(game.run(0x44B660, 0x44B678), game.interrupts)
            self.assertEqual(struct.unpack("<i", game.uc.mem_read(obj + 0x100 + 0x3C, 4))[0], expected)
        # 0x42D8C4 onward: the divisor is (elapsed - [p + 0x88]) + 1, reached only when elapsed > [p + 0x88].
        self.assertEqual(_code("plant")[0][0x2D8D8:0x2D8DC], b"\x3B\xC8\x7F\x0C")   # cmp ecx, eax ; jg
        self.assertEqual(_code("plant")[0][0x2D8F9:0x2D8FE], b"\x83\xC1\x01\xF7\xF9")  # add ecx, 1 ; idiv ecx

    @unittest.skipUnless(_ready(PLANT, True), "needs Capstone, Unicorn and vanilla Plant Tycoon")
    def test_plant_slide_step_would_fault_at_0(self) -> None:
        """0x421210 (one slide step) with its step count 0 faults at 0x42123F, which is why the count's
        source matters (always 5, test_plant_slide_steps_are_always_5); with 5 it moves 1/5 of the way."""
        game = _Game(PLANT)
        obj, x, y = game.DATA, game.DATA + 0x200, game.DATA + 0x204
        for steps in (5, 0):
            with self.subTest(steps=steps):
                game.uc.mem_write(x, struct.pack("<ii", 0, 0))
                # active, -, &x, &y, target x 100, target y 50, width 0, height 0, steps
                game.uc.mem_write(obj, struct.pack("<BxxxiIIiiiii", 1, -1, x, y, 100, 50, 0, 0, steps))
                game.uc.mem_write(game.STACK + game.STACK_SIZE - 0x1000, struct.pack("<I", game.STOP))
                game.uc.reg_write(X.UC_X86_REG_ESP, game.STACK + game.STACK_SIZE - 0x1000)
                game.uc.reg_write(X.UC_X86_REG_ECX, obj)
                finished = game.run(0x421210, game.STOP)
                if steps:
                    self.assertTrue(finished, game.interrupts)
                    self.assertEqual(struct.unpack("<ii", game.uc.mem_read(x, 8)), (20, 10))
                else:
                    self.assertEqual(game.interrupts, [0])
                    self.assertEqual(game.uc.reg_read(X.UC_X86_REG_EIP), 0x42123F)


class PatcherCode(unittest.TestCase):
    """The patcher's own executable patches divide nowhere."""

    @unittest.skipUnless(capstone is not None, "needs Capstone")
    def test_no_division_in_executable_patches(self) -> None:
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for manifest in ("fish_manifest.json", "plant_manifest.json"):
            patches = json.loads((ROOT / "data" / manifest).read_text(encoding="utf-8"))["patches"]
            for patch in patches:
                if not patch.get("file_path", "").lower().endswith(".exe") or not patch.get("replacement"):
                    continue
                code = bytes.fromhex(patch["replacement"].replace(" ", ""))
                with self.subTest(patch=patch["id"]):
                    self.assertFalse([i for i in md.disasm(code, 0) if i.mnemonic in ("div", "idiv")])


if __name__ == "__main__":
    unittest.main()
