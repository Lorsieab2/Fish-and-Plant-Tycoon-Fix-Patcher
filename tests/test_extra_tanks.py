"""The "3 extra tanks" setting (Extra Tanks.dll), run in Unicorn against the vanilla
Fish Tycoon.exe (tests/store_emulator.py).

The DLL is rebuilt from its source (it must come out byte-for-byte the shipped
DLL), mapped beside the game, and its own hooks are called with the game's own
code running underneath: the fish update 0x41FE70, AddFish 0x419C50,
REMOVE_FISH 0x418E20, the starter eggs 0x41FC90, the store purchase 0x427B30.
Only the clocks, the dice and the sprite/sound helpers are Python.

* Tick for tick: the same fish in a stock tank and in an extra tank give the
  same tank bytes after every update, for every family of effects the update
  has (ageing, food, health, sickness and its spread, breeding and births,
  the magic fish -- Fertility, Mutation (Wasp Grouper), Curing, Health,
  Sustenance --, research, the plants and the owned items).
* On screen: an extra tank swapped into Tank One's place is the block the
  game's own current-tank code reads (chemicals, medicines, food, eggs,
  ornaments), and Tank One is back in its place for saves.
* The Sale Tank is never anything but the Sale Tank: fish for sale and its
  stock limit do not change with fish in every tank.
* Moving fish to and from the extra tanks, with the game's own tank limit.
* The sidecar round trip, a damaged sidecar set aside, a new game emptied.
* All-or-none install, chained with DS Store Items' sites.
* The manifest: the setting, its files, and the stock game unchanged with it off.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

try:
    import store_emulator as E
    HAVE_UNICORN = True
except ImportError:                                    # pragma: no cover
    HAVE_UNICORN = False

EXE = (E.VANILLA if HAVE_UNICORN else Path(".")) / "Fish Tycoon" / "Fish Tycoon.exe"
DLL = ROOT / "assets" / "fish_tycoon_extra_tanks" / "Extra Tanks.dll"
MANIFEST = ROOT / "data" / "fish_manifest.json"

STATE_SIZE = 0x1E600
FISH_BASE, TANK, SLOT = 0x390, 0x51EC, 0x288
STEP = 600                                             # Normal speed: one age step every 600 s

_BUILT: dict = {}


def built():
    if "dll" not in _BUILT:
        out = Path(tempfile.mkdtemp(prefix="ftfp_tanks_"))
        _BUILT["dll"], _BUILT["symbols"] = E.build_with_map("ftfp_extra_tanks", DLL, out)
    return _BUILT["dll"], _BUILT["symbols"]


def fish(now: int, body: int, fin: int, age: int, health: int = 80, food: int = 60, disease: int = 0,
         due: int = 0, mate: tuple[int, int] = (0, 0)) -> bytes:
    rec = bytearray(SLOT)
    struct.pack_into("<IIIIIII", rec, 0, now, 0, age, age, due, mate[0], mate[1])
    struct.pack_into("<III", rec, 0x3C, health, disease, food)
    struct.pack_into("<II", rec, 0x4C, body, fin)
    struct.pack_into("<III", rec, 0x54, 10001 + 100 * body, 10031 + 100 * fin, 10061 + 100 * fin)
    return bytes(rec)


class Rig:
    """The game state, the tank screen and the DLL, with deterministic dice and clocks."""

    def __init__(self, seed: int = 1) -> None:
        dll, symbols = built()
        self.emu = emu = E.Emulator(EXE, dll, symbols)
        self.sym = symbols
        emu.uc.mem_map(0, 0x1000)                          # fs:[0] for the DLL's __try (fs base 0)
        self.state = emu.alloc(STATE_SIZE)
        self.impl = emu.alloc(0x200)
        self.view = emu.alloc(0x6000)
        self.holder = emu.alloc(16)
        emu.write32(self.holder, self.view)
        emu.write32(self.impl + 0x34, self.state)
        emu.write32(self.impl + 0x3C, self.holder)
        for b, left in enumerate((513, 610, 707)):        # the stock button rects (0x41CDD4)
            emu.uc.mem_write(self.impl + 0x58 + b * 0x10, struct.pack("<4i", left, 2, left + 85, 54))
        self.set(0x1E168, 10)                              # Normal speed
        self.set(0x258, 1)                                 # environment research level 1
        self.set(0x244, 1)                                 # fish food research level 1
        self.set(0x14, 1)                                  # Medium
        self.set(0x230, 1)                                 # Tank Two bought
        self.set(0x1E4E8, 0xFFFFFFFF)                      # no fish held
        self.now = 1_000_000
        self.ms = 5_000_000
        self.seed = seed
        self.rolls: list[int] = []
        self.calls: list[tuple] = []
        emu.hook(0x004020D0, lambda e: self.ms, 0)
        emu.hook(0x004032C0, lambda e: self.now, 0)
        emu.hook(0x00403240, self._random, 0)
        emu.hook(0x004251A0, lambda e: 0, 4)               # no sound
        emu.hook(0x00417FA0, lambda e: self.calls.append(("hint", e.arg(0))) or 0, 4)
        emu.hook(0x00415380, lambda e: self.calls.append(("view_move", e.arg(0), e.arg(1) | 0, e.arg(3))) or 0, 16)
        emu.hook(0x00421940, lambda e: self.calls.append(("switch", e.read32(self.state + 0x384))) or 0, 0)
        for name in ("_prev_tick_idle", "_prev_tick_show"):
            emu.write32(symbols[name], 0x0041FE70)
        emu.write32(symbols["_prev_release"], 0x00421B20)
        emu.write32(symbols["_prev_new_game"], 0x0041A8F0)
        emu.write32(symbols["_prev_starter_eggs"], 0x0041FC90)
        emu.write32(symbols["_owner"], self.state)
        emu.write32(symbols["_shown"], 0xFFFFFFFF)
        emu.write32(symbols["_owned"], 3)                   # all three bought, unless a test says otherwise

    # ------------------------------------------------------------ helpers
    def _random(self, emu) -> int:
        n = emu.arg(0)
        self.seed = (self.seed * 214013 + 2531011) & 0xFFFFFFFF
        value = (self.seed >> 16) & 0x7FFF
        self.rolls.append(n)
        return value % n if 0 < n <= 0x7FFF else 0

    def set(self, offset: int, value: int) -> None:
        self.emu.write32(self.state + offset, value)

    def get(self, offset: int) -> int:
        return self.emu.read32(self.state + offset)

    def tank(self, t: int) -> bytes:
        return bytes(self.emu.uc.mem_read(self.state + FISH_BASE + t * TANK, TANK))

    def put_tank(self, t: int, data: bytes) -> None:
        self.emu.uc.mem_write(self.state + FISH_BASE + t * TANK, data)

    def extra(self, e: int) -> bytes:
        return bytes(self.emu.uc.mem_read(self.sym["_store"] + e * TANK, TANK))

    def put_extra(self, e: int, data: bytes) -> None:
        self.emu.uc.mem_write(self.sym["_store"] + e * TANK, data)

    def var(self, name: str, value: int | None = None) -> int:
        if value is not None:
            self.emu.write32(self.sym[name], value & 0xFFFFFFFF)
        return self.emu.read32(self.sym[name], signed=True)

    def tick(self) -> None:
        self.now += STEP
        self.ms += STEP * 1000
        self.emu.call(self.sym["@tick_idle_hook@8"], ecx=self.impl)

    def species(self) -> bytes:
        return bytes(self.emu.uc.mem_read(self.state + 0x14B40, 0x65B8))

    def globals(self) -> bytes:
        """Everything in the state outside the four tanks and the species table."""
        head = bytes(self.emu.uc.mem_read(self.state, FISH_BASE))
        tail = bytes(self.emu.uc.mem_read(self.state + 0x14B40 + 0x65B8, STATE_SIZE - 0x14B40 - 0x65B8))
        return head + tail


def block_with(records: dict[int, bytes]) -> bytes:
    data = bytearray(TANK)
    for slot, rec in records.items():
        data[slot * SLOT: (slot + 1) * SLOT] = rec
    return bytes(data)


NOW = 1_000_000

# Fish for each family of effects the update has (bodies/fins: 0x41DE90's magic pairs).
FAMILIES = {
    "ageing, food and health": {
        0: fish(NOW, 4, 8, 3, 90, 70), 1: fish(NOW, 9, 3, 12, 40, 4), 2: fish(NOW, 20, 16, 25, 100, 100),
        3: fish(NOW, 1, 1, 20, 15, 1),
    },
    "sickness and its spread": {
        0: fish(NOW, 4, 4, 22, 70, 50, disease=1), 1: fish(NOW, 8, 8, 22, 70, 50, disease=2),
        2: fish(NOW, 12, 12, 22, 70, 50), 3: fish(NOW, 3, 5, 21, 50, 30), 4: fish(NOW, 7, 9, 30, 60, 60),
    },
    "breeding and births": {
        0: fish(NOW, 4, 8, 30, 90, 80, due=31, mate=(12, 16)), 1: fish(NOW, 16, 0, 25, 90, 80, due=26, mate=(4, 4)),
        2: fish(NOW, 20, 20, 22, 90, 80),
    },
    "Magic Fish of Fertility and the Wasp Grouper (Mutation)": {
        0: fish(NOW, 13, 6, 25, 100, 90), 1: fish(NOW, 20, 16, 25, 100, 90),        # Wasp Grouper, Fertility
        2: fish(NOW, 4, 8, 30, 90, 80, due=31, mate=(12, 16)), 3: fish(NOW, 0, 0, 28, 90, 80, due=29, mate=(20, 20)),
    },
    "Magic Fish of Curing, Health and Sustenance": {
        0: fish(NOW, 11, 11, 25, 100, 90), 1: fish(NOW, 14, 14, 25, 100, 90), 2: fish(NOW, 10, 9, 25, 100, 90),
        3: fish(NOW, 5, 8, 25, 100, 90),
        4: fish(NOW, 4, 4, 22, 60, 2, disease=1), 5: fish(NOW, 3, 3, 22, 30, 1, disease=2), 6: fish(NOW, 1, 7, 9, 50, 40),
    },
    "a full tank (babies lost as stock)": {
        s: fish(NOW, (s * 3) % 21, (s * 5) % 21, 20 + s, 90, 80, due=(21 + s if s < 3 else 0), mate=(4, 8))
        for s in range(21)
    },
}

# Global upgrades: research levels, the four plants, the Aeration System and the
# Temperature Regulator, Easy (state offsets read by 0x41DF50 / 0x41E120 / the update).
UPGRADES = {0x258: 3, 0x244: 3, 0x26C: 3, 0x12C: 1, 0x118: 1, 0x190: 1, 0x140: 1, 0x168: 1, 0x17C: 1, 0x1A4: 1,
            0x14: 0}


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class TickForTick(unittest.TestCase):
    """The same fish in a stock tank and in an extra tank, update after update."""

    def run_pair(self, records: dict[int, bytes], steps: int = 12, upgrades: dict[int, int] | None = None,
                 stock_tank: int = 1, shown: bool = False) -> None:
        stock, extra = Rig(seed=7), Rig(seed=7)
        for rig in (stock, extra):
            for offset, value in (upgrades or {}).items():
                rig.set(offset, value)
        start = block_with(records)
        stock.put_tank(stock_tank, start)
        if shown:
            # The extra on screen: in Tank One's place, Tank One (empty) held by the DLL.
            extra.put_tank(0, start)
            extra.var("_shown", stock_tank)
        else:
            extra.put_extra(stock_tank, start)
        for step in range(steps):
            stock.tick()
            extra.tick()
            got = extra.tank(0) if shown else extra.extra(stock_tank)
            self.assertEqual(stock.tank(stock_tank), got, f"tank bytes differ after update {step + 1}")
            self.assertEqual(stock.species(), extra.species(), f"species table differs after update {step + 1}")
            self.assertEqual(stock.globals(), extra.globals(), f"game state differs after update {step + 1}")
            self.assertEqual(stock.rolls, extra.rolls, f"the dice differ after update {step + 1}")
        for t in range(4):
            if t != stock_tank:
                self.assertEqual(stock.tank(t) if not shown or t else bytes(TANK), bytes(TANK))
        self.assertTrue(stock.rolls, "the update rolled no dice: the fish were not updated")

    def test_every_family_matches_tank_two(self) -> None:
        for name, records in FAMILIES.items():
            with self.subTest(family=name):
                self.run_pair(records)

    def test_every_family_with_every_upgrade(self) -> None:
        for name, records in FAMILIES.items():
            with self.subTest(family=name):
                self.run_pair(records, upgrades=UPGRADES)

    def test_each_extra_matches_its_stock_place(self) -> None:
        records = FAMILIES["Magic Fish of Fertility and the Wasp Grouper (Mutation)"]
        for t in range(3):
            with self.subTest(extra=t):
                self.run_pair(records, stock_tank=t)

    def test_an_extra_on_screen_matches_tank_one(self) -> None:
        for name, records in FAMILIES.items():
            with self.subTest(family=name):
                self.run_pair(records, stock_tank=0, shown=True)

    def test_time_away_catch_up_matches(self) -> None:
        stock, extra = Rig(seed=3), Rig(seed=3)
        start = block_with(FAMILIES["breeding and births"])
        stock.put_tank(1, start)
        extra.put_extra(1, start)
        for rig in (stock, extra):
            rig.now += 30 * 3600                       # 30 hours away
            rig.tick()
        self.assertEqual(stock.tank(1), extra.extra(1))
        self.assertGreater(struct.unpack_from("<I", stock.tank(1), 0x0C)[0], 30)

    def test_isolation_tank_is_untouched_and_ticks_once(self) -> None:
        stock, extra = Rig(seed=5), Rig(seed=5)
        lone = block_with({0: fish(NOW, 6, 6, 21, 80, 60)})
        for rig in (stock, extra):
            rig.put_tank(3, lone)
        extra.put_extra(2, block_with(FAMILIES["ageing, food and health"]))
        for _ in range(6):
            stock.tick()
            extra.tick()
        self.assertEqual(stock.tank(3), extra.tank(3), "the isolation fish aged differently")


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class OnScreenAndSelling(unittest.TestCase):
    def test_current_tank_code_reads_the_extra(self) -> None:
        """Every chemical, medicine, food, egg and ornament acts on state + 0x390 +
        current * 0x51EC; with an extra on screen that is the extra's block."""
        rig = Rig()
        one, extra = block_with({0: fish(NOW, 1, 1, 22)}), block_with({0: fish(NOW, 2, 2, 22), 1: fish(NOW, 3, 3, 9)})
        rig.put_tank(0, one)
        rig.put_extra(2, extra)
        rig.set(0x384, 1)
        rig.emu.uc.mem_write(rig.impl + 0xC8, b"\0\0\0\0\0")
        rig.var("_page", 1)
        # Press and let go on the third extra button: the game's own switch, current tank 0.
        rig.emu.call(rig.sym["@mouse_hook@20"], 2, 760, 20, ecx=rig.impl)
        rig.emu.call(rig.sym["@mouse_hook@20"], 3, 760, 20, ecx=rig.impl)
        self.assertEqual(rig.var("_shown"), 2)
        self.assertEqual(rig.get(0x384), 0)
        self.assertIn(("switch", 0), rig.calls)
        self.assertEqual(rig.tank(0), extra)
        self.assertEqual(rig.extra(2), one)
        # The game's own ornament placement (0x419C00) into the current tank lands in the extra.
        ornament = bytearray(0x2C)
        ornament[0] = 1
        struct.pack_into("<I", ornament, 0x24, 140)
        orn = rig.emu.alloc(0x2C)
        rig.emu.uc.mem_write(orn, bytes(ornament))
        rig.emu.call(0x00419C00, rig.get(0x384), orn, ecx=rig.state)
        self.assertNotEqual(rig.tank(0)[0x4E78: 0x4E78 + 0x2C * 6], extra[0x4E78: 0x4E78 + 0x2C * 6])
        self.assertEqual(rig.extra(2), one, "Tank One got the ornament")
        # Back to Tank One with the stock button: the extra goes home, ornament and all.
        rig.var("_page", 0)
        rig.emu.uc.mem_write(rig.impl + 0xC8, b"\x01")
        rig.emu.call(rig.sym["@mouse_hook@20"], 3, 550, 20, ecx=rig.impl)
        self.assertEqual(rig.var("_shown"), -1)
        self.assertEqual(rig.tank(0), one)
        self.assertNotEqual(rig.extra(2), extra)

    def test_sale_tank_never_changes_with_full_extra_tanks(self) -> None:
        """The stock limit of fish for sale: only the Sale Tank (tank 2) sells, up to the
        game's own tank size (AddFish's bound at 0x419C72); the extras never change it."""
        rig = Rig()
        full = block_with({s: fish(NOW, s % 21, (s * 2) % 21, 25) for s in range(21)})
        sale = block_with({s: fish(NOW, 4, 8, 25) for s in range(5)})
        rig.put_tank(2, sale)
        for e in range(3):
            rig.put_extra(e, full)
        bound = E.pe_image  # noqa: F841 (the bound is read from the executable below)
        exe = EXE.read_bytes()
        self.assertEqual(exe[0x19C72:0x19C75], bytes.fromhex("83F815"), "AddFish's stock 21-fish bound")
        for _ in range(4):
            rig.tick()
        live = [struct.unpack_from("<I", rig.tank(2), s * SLOT)[0] != 0 for s in range(31)]
        self.assertEqual(sum(live), 5, "fish for sale changed")
        self.assertEqual(rig.tank(2)[5 * SLOT:], sale[5 * SLOT:])
        # A fish dropped on the Sale Tank still goes through the stock drop, and the extras'
        # own AddFish into a full extra is refused at the stock bound.
        rec = rig.emu.alloc(SLOT)
        rig.emu.uc.mem_write(rec, fish(NOW, 1, 1, 22))
        rig.put_tank(0, full)
        self.assertEqual(rig.emu.call(0x00419C50, 0, rec, ecx=rig.state), 0xFFFFFFFF)


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class MovingFish(unittest.TestCase):
    def hold(self, rig: Rig, entry: int, tank: int, slot: int) -> None:
        at = rig.view + 0x1080 + entry * 0x84
        rig.emu.write8(at, 1)
        rig.emu.write32(at + 0x40, tank)
        rig.emu.write32(at + 0x44, slot)
        rig.set(0x1E4E8, entry)

    def test_drop_on_an_extra_button(self) -> None:
        rig = Rig()
        mover = fish(NOW, 4, 8, 22, 77, 66)
        rig.put_tank(1, block_with({3: mover}))
        rig.set(0x384, 1)
        rig.var("_page", 1)
        self.hold(rig, 2, 1, 3)
        rig.emu.call(rig.sym["@release_hook@16"], 640, 20, ecx=rig.impl)      # Tank Four (extra 1)
        self.assertEqual(rig.extra(1)[:SLOT], mover, "the fish is in the extra tank's first free slot")
        self.assertEqual(struct.unpack_from("<I", rig.tank(1), 3 * SLOT)[0], 0, "it left Tank Two")
        self.assertIn(("view_move", 2, -1 & 0xFFFFFFFF, 0xFFFFFFFF), [(c[0], c[1], c[2] & 0xFFFFFFFF, c[3]) for c in rig.calls])
        self.assertEqual(rig.get(0x1E4E8), 0xFFFFFFFF)

    def test_drop_from_an_extra_on_screen_to_tank_one(self) -> None:
        rig = Rig()
        mover = fish(NOW, 9, 9, 30, 50, 50)
        rig.put_tank(0, block_with({0: mover}))                       # the extra, on screen
        rig.put_extra(0, block_with({0: fish(NOW, 1, 1, 25)}))       # Tank One, held by the DLL
        rig.var("_shown", 0)
        rig.var("_page", 0)
        self.hold(rig, 1, 0, 0)
        rig.emu.call(rig.sym["@release_hook@16"], 550, 20, ecx=rig.impl)      # the Tank One button
        self.assertEqual(rig.extra(0)[SLOT:2 * SLOT], mover)
        self.assertEqual(struct.unpack_from("<I", rig.tank(0), 0)[0], 0)

    def test_a_full_extra_refuses_as_stock(self) -> None:
        rig = Rig()
        rig.put_extra(2, block_with({s: fish(NOW, 4, 4, 25) for s in range(21)}))
        mover = fish(NOW, 6, 6, 25)
        rig.put_tank(0, block_with({0: mover}))
        rig.set(0x384, 0)
        rig.var("_page", 1)
        self.hold(rig, 1, 0, 0)
        rig.emu.call(rig.sym["@release_hook@16"], 740, 20, ecx=rig.impl)
        self.assertIn(("hint", 6), rig.calls)                       # "The tank is full!"
        self.assertEqual(rig.tank(0)[:SLOT], mover)

    def test_isolation_fish_to_an_extra(self) -> None:
        rig = Rig()
        mother = fish(NOW, 4, 8, 30, 90, 80, due=33, mate=(12, 12))
        rig.put_tank(3, block_with({0: mother}))
        rig.var("_page", 1)
        self.hold(rig, 4, 3, 0)
        rig.emu.call(rig.sym["@release_hook@16"], 550, 20, ecx=rig.impl)
        self.assertEqual(rig.extra(0)[:SLOT], mother)
        self.assertEqual(struct.unpack_from("<I", rig.tank(3), 0)[0], 0)

    # The arrows: left (previous) at (495-512, 8-22), right (next) at (495-512, 31-45).
    LEFT, RIGHT = (500, 12), (500, 36)

    def test_drag_onto_the_right_arrow_moves_to_the_next_tank(self) -> None:
        rig = Rig()
        mover = fish(NOW, 4, 8, 25, 77, 66)
        rig.put_tank(1, block_with({2: mover}))
        rig.set(0x384, 1)                                            # on Tank Two: next is the Sale Tank
        self.hold(rig, 3, 1, 2)
        rig.emu.call(rig.sym["@release_hook@16"], *self.RIGHT, ecx=rig.impl)
        self.assertEqual(rig.tank(2)[:SLOT], mover, "the game's own AddFish put it in the Sale Tank")
        self.assertEqual(struct.unpack_from("<I", rig.tank(1), 2 * SLOT)[0], 0)

    def test_the_arrows_go_round_the_six_tanks(self) -> None:
        # Tank One <- Tank Five (round), the Sale Tank -> Tank Three, Tank Three on screen -> Tank Four.
        for current, shown, arrow, extra in ((0, -1, self.LEFT, 2), (2, -1, self.RIGHT, 0), (0, 0, self.RIGHT, 1)):
            with self.subTest(current=current, shown=shown, arrow=arrow):
                rig = Rig()
                mover = fish(NOW, 6, 6, 24)
                rig.put_tank(current, block_with({0: mover}))
                rig.set(0x384, current)
                rig.var("_shown", shown)
                self.hold(rig, 1, current, 0)
                rig.emu.call(rig.sym["@release_hook@16"], *arrow, ecx=rig.impl)
                self.assertEqual(rig.extra(extra)[:SLOT], mover)

    def test_left_arrow_from_an_extra_on_screen_goes_back_to_the_sale_tank(self) -> None:
        rig = Rig()
        mover = fish(NOW, 6, 6, 24)
        rig.put_tank(0, block_with({0: mover}))                       # Tank Three on screen
        rig.var("_shown", 0)
        self.hold(rig, 1, 0, 0)
        rig.emu.call(rig.sym["@release_hook@16"], *self.LEFT, ecx=rig.impl)
        self.assertEqual(rig.tank(2)[:SLOT], mover)

    def test_an_arrow_onto_a_full_tank_is_refused(self) -> None:
        rig = Rig()
        rig.put_tank(2, block_with({s: fish(NOW, 4, 4, 25) for s in range(21)}))
        mover = fish(NOW, 6, 6, 25)
        rig.put_tank(1, block_with({0: mover}))
        rig.set(0x384, 1)
        self.hold(rig, 1, 1, 0)
        rig.emu.call(rig.sym["@release_hook@16"], *self.RIGHT, ecx=rig.impl)
        self.assertIn(("hint", 6), rig.calls)
        self.assertEqual(rig.tank(1)[:SLOT], mover)

    def test_an_arrow_onto_an_unbought_tank_two_is_refused_as_stock(self) -> None:
        rig = Rig()
        rig.set(0x230, 0)
        mover = fish(NOW, 6, 6, 25)
        rig.put_tank(0, block_with({0: mover}))
        self.hold(rig, 1, 0, 0)
        rig.emu.call(rig.sym["@release_hook@16"], *self.RIGHT, ecx=rig.impl)
        self.assertIn(("hint", 8), rig.calls)
        self.assertEqual(rig.tank(1), bytes(TANK))

    def test_an_ornament_moves_to_an_extra_tank(self) -> None:
        rig = Rig()
        rig.emu.hook(0x00407AB0, lambda e: 7000, 0)                    # the screen's clock, for the new x
        ornament = bytearray(0x2C)
        ornament[0] = 1
        struct.pack_into("<II", ornament, 0x04, 300, 400)                 # x, y
        struct.pack_into("<III", ornament, 0x1C, 60, 70, 177)             # h, w, sprite (the shell)
        rig.emu.uc.mem_write(rig.state + 0x5208 + 0x51EC * 1 + 2 * 0x2C, bytes(ornament))
        rig.set(0x384, 1)
        rig.emu.write32(rig.impl + 0x1C, 0x63)
        rig.emu.write32(rig.impl + 0x28, 2)
        rig.var("_page", 1)
        rig.emu.call(rig.sym["@release_hook@16"], 740, 20, ecx=rig.impl)      # Tank Five
        self.assertEqual(rig.extra(2)[0x4E78], 1, "the ornament is in Tank Five's first ornament place")
        self.assertEqual(rig.extra(2)[0x4E78 + 0x24: 0x4E78 + 0x28], struct.pack("<I", 177))
        self.assertEqual(rig.tank(1)[0x4E78 + 2 * 0x2C], 0, "it left Tank Two")
        self.assertEqual(rig.emu.read32(rig.impl + 0x28), 0x63)
        self.assertEqual(rig.tank(2), bytes(TANK), "the stock tank lent for the call is back")

    def test_page_zero_buttons_are_stock(self) -> None:
        rig = Rig()
        calls = []
        rig.emu.write32(rig.sym["_prev_mouse"], 0x00421B80)
        rig.emu.hook(0x00421B80, lambda e: calls.append((e.arg(0), e.arg(1), e.arg(2))) or 0, 12)
        for kind in (2, 3):
            rig.emu.call(rig.sym["@mouse_hook@20"], kind, 640, 20, ecx=rig.impl)
        self.assertEqual(calls, [(2, 640, 20), (3, 640, 20)])

    def test_either_arrow_turns_the_page(self) -> None:
        rig = Rig()
        for arrow, page in ((self.RIGHT, 1), (self.LEFT, 0), (self.LEFT, 1)):
            rig.emu.call(rig.sym["@mouse_hook@20"], 2, *arrow, ecx=rig.impl)
            rig.emu.call(rig.sym["@mouse_hook@20"], 3, *arrow, ecx=rig.impl)
            self.assertEqual(rig.var("_page"), page)

    def test_multiple_ornaments_is_told_which_tank_is_on_screen(self) -> None:
        rig = Rig()
        fn = rig.sym["_ornaments_tank_map"]
        self.assertEqual([rig.emu.call(fn, t) for t in range(3)], [0, 1, 2])
        rig.var("_shown", 1)
        self.assertEqual([rig.emu.call(fn, t) for t in range(3)], [4, 1, 2])

    def test_stock_drops_stay_stock(self) -> None:
        rig = Rig()
        calls = []
        rig.emu.hook(0x00421B20, lambda e: calls.append((e.arg(0), e.arg(1))) or 0, 8)
        rig.var("_page", 0)
        self.hold(rig, 1, 0, 0)
        rig.emu.call(rig.sym["@release_hook@16"], 640, 20, ecx=rig.impl)      # Tank Two, nothing shown
        self.assertEqual(calls, [(640, 20)])


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class StarterEggsAndSeahorse(unittest.TestCase):
    def eggs(self, rig: Rig) -> int:
        babies = []
        rig.emu.hook(0x0041FA30, lambda e: babies.append(e.arg(0)) or 0, 56)
        rig.emu.call(rig.sym["@starter_eggs_hook@8"], ecx=rig.impl)
        return len(babies)

    def test_no_fish_anywhere_gives_seven(self) -> None:
        self.assertEqual(self.eggs(Rig()), 7)

    def test_fish_only_in_an_extra_tank_counts_as_a_tank_with_fish(self) -> None:
        rig = Rig()
        rig.put_extra(1, block_with({0: fish(NOW, 4, 4, 22)}))
        self.assertEqual(self.eggs(rig), 3)
        self.assertEqual(rig.tank(1), bytes(TANK), "the stand-in mark was taken away")
        self.assertEqual(rig.tank(2), bytes(TANK))

    def test_fish_in_a_stock_tank_gives_three(self) -> None:
        rig = Rig()
        rig.put_tank(2, block_with({4: fish(NOW, 4, 4, 22)}))
        self.assertEqual(self.eggs(rig), 3)


    def purchase(self, rig: Rig, item: int, ds_store: bool = False) -> bytes:
        """The store's purchase (0x427B30) with the stock body replaced: what Tank One's place held."""
        seen = []
        store_impl = rig.emu.alloc(0x40)
        rig.emu.write32(store_impl + 0x10, rig.state)

        def body(e) -> int:
            from unicorn import x86_const as X
            seen.append(rig.tank(0))
            e.uc.reg_write(X.UC_X86_REG_ESP, e.uc.reg_read(X.UC_X86_REG_ESP) + 0x2B4)
            return 1
        rig.emu.hook(0x00427B36, body, 4)
        if ds_store:
            rig.emu.uc.mem_write(0x427E43, b"\xE9\x00\x00\x00\x00\x90\x90")
        rig.emu.call(rig.sym["@purchase_hook@12"], item, ecx=store_impl)
        return seen[0]

    def test_golden_seahorse_goes_to_tank_one_as_stock(self) -> None:
        rig = Rig()
        one, extra = block_with({0: fish(NOW, 1, 1, 22)}), block_with({0: fish(NOW, 2, 2, 22)})
        rig.put_tank(0, extra)
        rig.put_extra(1, one)
        rig.var("_shown", 1)
        self.assertEqual(self.purchase(rig, 0x0B), one, "the stock seahorse placement saw Tank One")
        self.assertEqual(rig.tank(0), extra, "the extra is back on screen")
        self.assertEqual(self.purchase(rig, 0x10), extra, "other items (ornaments) go to the tank on screen")

    def test_with_ds_store_the_seahorse_goes_to_the_tank_you_came_from(self) -> None:
        rig = Rig()
        extra = block_with({0: fish(NOW, 2, 2, 22)})
        rig.put_tank(0, extra)
        rig.var("_shown", 0)
        self.assertEqual(self.purchase(rig, 0x0B, ds_store=True), extra)


BUTTON_CENTRES = ((555, 28), (652, 28), (749, 28))
ARROW_LEFT, ARROW_RIGHT = (500, 12), (500, 36)


def animal(now: int, fin: int) -> bytes:
    """A DS Store Items animal: a seahorse-type record marked "FTCA", as its DLL builds them."""
    rec = bytearray(fish(now, 22, fin, 21, 100, 100))
    struct.pack_into("<II", rec, 0x14, 0x41435446, fin)
    return bytes(rec)


def ornament(sprite: int, spare: bytes = b"\0\0\0") -> bytes:
    rec = bytearray(0x2C)
    rec[0] = 1
    rec[1:4] = spare
    struct.pack_into("<II", rec, 0x04, 300, 400)
    struct.pack_into("<III", rec, 0x1C, 60, 70, sprite)
    return bytes(rec)


class Screen:
    """The six tanks in page order on a Rig: which is on screen, and where each block is."""

    def __init__(self, rig: Rig) -> None:
        self.rig = rig
        rig.emu.hook(0x0040AE20, lambda e: 0, 4)                    # the stock code plays sounds
        rig.emu.hook(0x00407AB0, lambda e: 7000, 0)                 # the screen's clock (ornament x)

    def show(self, tank: int) -> None:
        rig = self.rig
        if tank < 3:
            rig.set(0x384, tank)
            rig.var("_shown", -1)
        else:
            rig.set(0x384, 0)
            rig.var("_shown", tank - 3)

    def block(self, tank: int) -> bytes:
        rig, shown = self.rig, self.rig.var("_shown")
        if tank == 0:
            return rig.extra(shown) if shown >= 0 else rig.tank(0)
        if tank < 3:
            return rig.tank(tank)
        return rig.tank(0) if shown == tank - 3 else rig.extra(tank - 3)

    def put(self, tank: int, data: bytes) -> None:
        rig, shown = self.rig, self.rig.var("_shown")
        if tank == 0:
            if shown >= 0:
                rig.put_extra(shown, data)
            else:
                rig.put_tank(0, data)
        elif tank < 3:
            rig.put_tank(tank, data)
        elif shown == tank - 3:
            rig.put_tank(0, data)
        else:
            rig.put_extra(tank - 3, data)

    def control(self, source: int, target: int) -> tuple[int, int]:
        """The arrow for a neighbour, else the target's button on its page."""
        if target == (source + 1) % 6:
            return ARROW_RIGHT
        if target == (source - 1) % 6:
            return ARROW_LEFT
        self.rig.var("_page", 1 if target >= 3 else 0)
        return BUTTON_CENTRES[target % 3]

    def hold_fish(self, source: int, slot: int) -> None:
        rig = self.rig
        entry = rig.view + 0x1080 + 3 * 0x84
        rig.emu.write8(entry, 1)
        rig.emu.write32(entry + 0x40, 0 if source >= 3 else source)
        rig.emu.write32(entry + 0x44, slot)
        rig.set(0x1E4E8, 3)

    def release(self, x: int, y: int) -> None:
        self.rig.emu.call(self.rig.sym["@release_hook@16"], x, y, ecx=self.rig.impl)


PAIRS = [(s, t) for s in range(6) for t in range(6) if s != t]


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class MovingBetweenAnyTwoTanks(unittest.TestCase):
    """Every kind of thing between every two of the six tanks, by arrow or button; the stock
    buttons run the game's own drop (0x41EFF0 / 0x41F660)."""

    FISH = {
        "baby": fish(NOW, 4, 8, 2, 100, 90),
        "sick adult": fish(NOW, 9, 3, 25, 40, 30, disease=2),
        "pregnant adult": fish(NOW, 16, 0, 30, 90, 80, due=32, mate=(4, 4)),
        "Golden Seahorse": fish(NOW, 22, 22, 21, 100, 100),
    }

    def move_fish(self, kind: str, rec: bytes, source: int, target: int, slot: int = 4) -> None:
        rig = Rig()
        screen = Screen(rig)
        screen.show(source)
        screen.put(source, block_with({slot: rec}))
        screen.hold_fish(source, slot)
        screen.release(*screen.control(source, target))
        where = 26 if slot >= 26 else 0
        self.assertEqual(screen.block(target)[where * SLOT: (where + 1) * SLOT], rec, f"{kind} {source}->{target}")
        self.assertEqual(struct.unpack_from("<I", screen.block(source), slot * SLOT)[0], 0, f"{kind} left {source}")

    def test_fish_and_the_golden_seahorse(self) -> None:
        for kind, rec in self.FISH.items():
            for source, target in PAIRS:
                with self.subTest(kind=kind, source=source, target=target):
                    self.move_fish(kind, rec, source, target)

    def test_ds_store_animals(self) -> None:
        """Into the target's animal slots (26-30). The stock buttons of Tank Two and the Sale Tank
        (a stock tank in its own place) are DS Store Items' own drop, as before; every other way\n        is this DLL's."""
        for fin in (30, 31, 32):
            for source, target in PAIRS:
                if target < 3 and (target - source) % 6 not in (1, 5) and not (target == 0 and source >= 3):
                    continue
                with self.subTest(fin=fin, source=source, target=target):
                    self.move_fish(f"animal {fin}", animal(NOW, fin), source, target, slot=27)

    def test_ornaments_and_the_eels_rock(self) -> None:
        kinds = {"shell": ornament(177), "the eel at home in its rock": ornament(229, bytes((90, 80, 0xE1))),
                 "the empty rock": ornament(228)}
        for kind, rec in kinds.items():
            for source, target in PAIRS:
                with self.subTest(kind=kind, source=source, target=target):
                    rig = Rig()
                    screen = Screen(rig)
                    screen.show(source)
                    block = bytearray(TANK)
                    block[0x4E78 + 0x2C: 0x4E78 + 2 * 0x2C] = rec
                    screen.put(source, bytes(block))
                    rig.emu.write32(rig.impl + 0x1C, 0x63)
                    rig.emu.write32(rig.impl + 0x28, 1)
                    screen.release(*screen.control(source, target))
                    moved = screen.block(target)[0x4E78: 0x4E78 + 0x2C]
                    self.assertEqual(moved[:4], rec[:4], "the active byte and the eel's home bytes")
                    self.assertEqual(moved[0x1C:0x28], rec[0x1C:0x28], "size and sprite")
                    self.assertEqual(screen.block(source)[0x4E78 + 0x2C], 0, "it left its tank")
                    self.assertEqual(rig.emu.read32(rig.impl + 0x28), 0x63)

    def test_a_full_target_refuses_as_stock(self) -> None:
        for source, target in ((0, 3), (4, 5), (5, 0), (3, 2), (0, 2)):
            with self.subTest(source=source, target=target):
                rig = Rig()
                screen = Screen(rig)
                screen.show(source)
                screen.put(target, block_with({s: fish(NOW, 4, 4, 25) for s in range(21)}))
                mover = fish(NOW, 6, 6, 25)
                screen.put(source, block_with({5: mover}))
                screen.hold_fish(source, 5)
                screen.release(*screen.control(source, target))
                self.assertIn(("hint", 6), rig.calls)
                self.assertEqual(screen.block(source)[5 * SLOT: 6 * SLOT], mover)

    def test_decorative_copies_are_handed_to_multiple_ornaments(self) -> None:
        """Nothing of the game's held: the drop goes on to Multiple Ornaments' own drop as a drop on
        a stock button, with the tank map naming the target for that call only."""
        for source, target, want_to, override in ((0, 1, 1, -1), (1, 5, 2, 5), (2, 3, 0, 3), (3, 0, 2, 0),
                                                  (4, 2, 2, -1)):
            with self.subTest(source=source, target=target):
                rig = Rig()
                screen = Screen(rig)
                screen.show(source)
                rig.emu.write32(rig.impl + 0x1C, 0x63)
                rig.emu.write32(rig.impl + 0x28, 0x63)
                prev = rig.emu.thunk()
                seen = []
                rig.emu.hook(prev, lambda e, r=rig, s=seen: s.append(
                    (e.arg(0), e.arg(1), r.var("_map_override_to"), r.var("_map_override_tank"))) or 1, 8)
                rig.var("_prev_release", prev)
                screen.release(*screen.control(source, target))
                cx, cy = BUTTON_CENTRES[want_to]
                self.assertEqual(seen, [(cx, cy, want_to if override >= 0 else -1, override)])
                self.assertEqual(rig.var("_map_override_to"), -1, "the override lasts one call")

    def test_a_held_item_is_left_to_the_stock_code(self) -> None:
        """A chemical, medicine, food or egg on the cursor let go on a button or an arrow: the stock
        release, as on a stock button (0x420B70 uses it only inside the tank)."""
        for item in (0, 2, 4):
            with self.subTest(item=item):
                rig = Rig()
                rig.emu.write32(rig.impl + 0x1C, item)
                prev = rig.emu.thunk()
                seen = []
                rig.emu.hook(prev, lambda e, s=seen: s.append((e.arg(0), e.arg(1))) or 0, 8)
                rig.var("_prev_release", prev)
                rig.var("_page", 1)
                for at in (ARROW_RIGHT, BUTTON_CENTRES[1]):
                    rig.emu.call(rig.sym["@release_hook@16"], *at, ecx=rig.impl)
                self.assertEqual(seen, [ARROW_RIGHT, BUTTON_CENTRES[1]])

    def test_switching_to_an_extra_tank_is_the_stock_switch(self) -> None:
        """Something held when switching: the stock switch 0x421940 puts it back (it sets the held
        item and ornament to none at 0x421A4B-0x421A55), for an extra tank as for a stock one."""
        self.assertEqual(EXE.read_bytes()[0x21A4B:0x21A58], bytes.fromhex("B86300000033F689451C894528"))
        rig = Rig()
        rig.emu.write32(rig.impl + 0x1C, 2)                         # a chemical held
        rig.var("_page", 1)
        rig.emu.call(rig.sym["@mouse_hook@20"], 2, *BUTTON_CENTRES[1], ecx=rig.impl)
        rig.emu.call(rig.sym["@mouse_hook@20"], 3, *BUTTON_CENTRES[1], ecx=rig.impl)
        self.assertIn(("switch", 0), rig.calls)
        self.assertEqual(rig.var("_shown"), 1)

    def test_eggs_hatch_into_the_extra_tank_on_screen(self) -> None:
        rig = Rig()
        Screen(rig).show(4)
        one = block_with({0: fish(NOW, 1, 1, 22)})
        rig.put_extra(1, one)                                        # Tank One, waiting in the DLL
        rig.emu.call(0x0041FC90, ecx=rig.impl)                       # the game's own egg hatch, current tank
        hatched = [struct.unpack_from("<I", rig.tank(0), s * SLOT)[0] != 0 for s in range(21)]
        self.assertEqual(sum(hatched), 7, "the stock 7 (the stock tanks look empty to it) in Tank Four")
        self.assertEqual(rig.extra(1), one, "Tank One untouched")


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class Buying(unittest.TestCase):
    """The extra tanks are bought on the Upgrades screen, in order; until then they are locked."""

    def test_bought_in_order_three_at_most(self) -> None:
        rig = Rig()
        rig.var("_owned", 0)
        rig.emu.write32(0x0045ABDC, rig.state)                   # the game's state pointer
        rig.var("_installed", 1)
        self.assertEqual(rig.emu.call(rig.sym["_FtfpExtraTanksOwned@0"]), 0)
        self.assertEqual([rig.emu.call(rig.sym["_FtfpExtraTanksBuy@0"]) for _ in range(4)],
                         [1, 2, 3, 0xFFFFFFFF])
        self.assertEqual(rig.emu.call(rig.sym["_FtfpExtraTanksOwned@0"]), 3)

    def test_no_game_open_means_nothing_to_sell(self) -> None:
        rig = Rig()
        rig.var("_installed", 1)
        rig.emu.write32(0x0045ABDC, rig.state + 0x100)           # another state: not the one loaded
        self.assertEqual(rig.emu.call(rig.sym["_FtfpExtraTanksOwned@0"]), 0xFFFFFFFF)
        self.assertEqual(rig.emu.call(rig.sym["_FtfpExtraTanksBuy@0"]), 0xFFFFFFFF)

    def test_a_locked_tank_refuses_a_switch(self) -> None:
        rig = Rig()
        rig.var("_owned", 1)
        rig.var("_page", 1)
        rig.emu.hook(0x004020D0, lambda e: 100, 0)
        for kind in (2, 3):
            rig.emu.call(rig.sym["@mouse_hook@20"], kind, *BUTTON_CENTRES[1], ecx=rig.impl)
        self.assertEqual(rig.var("_shown"), -1)
        self.assertNotIn(("switch", 0), rig.calls)
        self.assertEqual(rig.var("_locked_until"), 102, "the refusal shows for 2 seconds, as the game's hints")
        for kind in (2, 3):                                      # Tank Three is bought
            rig.emu.call(rig.sym["@mouse_hook@20"], kind, *BUTTON_CENTRES[0], ecx=rig.impl)
        self.assertEqual(rig.var("_shown"), 0)

    def test_a_locked_tank_refuses_a_drop(self) -> None:
        rig = Rig()
        rig.var("_owned", 2)
        rig.var("_page", 1)
        mover = fish(NOW, 6, 6, 25)
        rig.put_tank(1, block_with({0: mover}))
        rig.set(0x384, 1)
        Screen(rig).hold_fish(1, 0)
        rig.emu.call(rig.sym["@release_hook@16"], *BUTTON_CENTRES[2], ecx=rig.impl)
        self.assertEqual(rig.tank(1)[:SLOT], mover, "the fish stays")
        self.assertEqual(rig.extra(2), bytes(TANK))
        self.assertIn(("view_move", 3, 1, 0xFFFFFFFF), rig.calls, "back to swimming")
        self.assertGreater(rig.var("_locked_until"), 0)

    def test_the_arrows_skip_tanks_not_bought(self) -> None:
        for owned, source, arrow, target in ((0, 2, ARROW_RIGHT, 0), (1, 3, ARROW_RIGHT, 0), (0, 0, ARROW_LEFT, 2),
                                             (2, 0, ARROW_LEFT, 4)):
            with self.subTest(owned=owned, source=source, arrow=arrow):
                rig = Rig()
                rig.var("_owned", owned)
                screen = Screen(rig)
                screen.show(source)
                mover = fish(NOW, 6, 6, 24)
                screen.put(source, block_with({0: mover}))
                screen.hold_fish(source, 0)
                screen.release(*arrow)
                self.assertEqual(screen.block(target)[:SLOT], mover)

    def test_locked_buttons_draw_their_locked_frame(self) -> None:
        rig = Rig()
        rig.var("_owned", 1)
        rig.var("_page", 1)
        cells = []
        rig.emu.hook(0x00402060, lambda e: e.uc.mem_write(e.arg(0), struct.pack("<ii", 10, 500)) or 0, 0)
        rig.emu.hook(0x00402080, lambda e: 0, 0)
        rig.emu.hook(0x0042A793, lambda e: e.alloc(0x40), 0)
        rig.emu.hook(0x004096C0, lambda e: e.read32(e.uc.reg_read(__import__("unicorn").x86_const.UC_X86_REG_ECX)) or
                     e.uc.reg_read(__import__("unicorn").x86_const.UC_X86_REG_ECX), 12)
        rig.emu.hook(0x00409540, lambda e: e.uc.reg_read(__import__("unicorn").x86_const.UC_X86_REG_ECX), 4)
        rig.emu.hook(0x00408AA0, lambda e: cells.append((e.arg(1), e.arg(3))) or 0, 16)
        rig.emu.call(rig.sym["_draw_extras"], rig.impl)
        self.assertEqual([frame for x, frame in cells if x in (513, 610, 707)], [0, 3, 3])


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class Art(unittest.TestCase):
    """Tank Three/Four/Five are drawn as Tank One/Two/the Sale Tank by the game's own draws, the
    Sale Tank's sign left out."""

    def test_the_tank_number_is_lent_for_the_draws(self) -> None:
        for shown in range(3):
            with self.subTest(shown=shown):
                rig = Rig()
                rig.var("_shown", shown)
                rig.set(0x1E1D8, 1)                               # the Sale Tank's tutorial tip still to come
                seen = []
                for name, va in (("_prev_background", 0x0041D140), ("_prev_decor", 0x0041D340)):
                    rig.emu.write32(rig.sym[name], va)
                    rig.emu.hook(va, lambda e, r=rig: seen.append((r.get(0x384), r.get(0x1E1D8),
                                                                     r.var("_drawing_extra"))) or 0, 0)
                rig.emu.call(rig.sym["@background_hook@8"], ecx=rig.impl)
                rig.emu.call(rig.sym["@decor_hook@8"], ecx=rig.impl)
                self.assertEqual(seen, [(shown, 0, 1), (shown, 0, 1)])
                self.assertEqual((rig.get(0x384), rig.get(0x1E1D8), rig.var("_drawing_extra")), (0, 1, 0))

    def test_stock_tanks_draw_as_stock(self) -> None:
        rig = Rig()
        rig.set(0x384, 2)
        seen = []
        rig.emu.write32(rig.sym["_prev_decor"], 0x0041D340)
        rig.emu.hook(0x0041D340, lambda e: seen.append((rig.get(0x384), rig.var("_drawing_extra"))) or 0, 0)
        rig.emu.call(rig.sym["@decor_hook@8"], ecx=rig.impl)
        self.assertEqual(seen, [(2, 0)])

    def test_the_sign_only_on_the_sale_tank(self) -> None:
        rig = Rig()
        drawn = []
        rig.emu.write32(rig.sym["_prev_sale_sign"], 0x00408A40)
        rig.emu.hook(0x00408A40, lambda e: drawn.append((e.arg(1), e.arg(2))) or 0, 12)
        rig.emu.call(rig.sym["@sale_sign_hook@20"], 0x1234, 620, 360, ecx=rig.impl)
        rig.var("_drawing_extra", 1)
        rig.emu.call(rig.sym["@sale_sign_hook@20"], 0x1234, 620, 360, ecx=rig.impl)
        rig.emu.write32(rig.sym["_prev_sale_shadow"], 0x00408A40)
        rig.emu.call(rig.sym["@sale_shadow_hook@20"], 0x1234, 580, 415, ecx=rig.impl)
        rig.var("_drawing_extra", 0)
        rig.emu.call(rig.sym["@sale_shadow_hook@20"], 0x1234, 580, 415, ecx=rig.impl)
        self.assertEqual(drawn, [(620, 360), (580, 415)], "sign and its shadow only on the Sale Tank")
        exe = EXE.read_bytes()
        self.assertEqual(exe[0x1D452:0x1D460], bytes.fromhex("6868010000686C0200006A04E80D"),
                         "the stock sign: sprite 4 (forsale.png) at (620, 360)")


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and E.toolchain_ready(), "needs Unicorn, MSVC and the game")
class UpgradesScreenItem(unittest.TestCase):
    """DS Store Items' Extra Tank item: $10,000 ($0 with Free upgrades), confirmed, one tank a time,
    "This is in your inventory." when all three are bought, hidden without the setting."""

    CELL = (670, 280)

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_ds_store", ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def store(self, money: int, free: bool, owned: int | None):
        emu = E.Emulator(EXE, self.dll, self.symbols)
        emu.hook_printf()
        self.owned = owned
        module = 0x7100_0000
        emu.hook_import("GetModuleHandleW", lambda e: module if owned is not None and
                        e.wstring(e.arg(0)) == "Extra Tanks.dll" else 0, 4)
        owned_fn, buy_fn = emu.thunk(), emu.thunk()
        emu.hook(owned_fn, lambda e: self.owned if self.owned is not None else 0xFFFFFFFF, 0)

        def buy(e) -> int:
            if self.owned is None or self.owned >= 3:
                return 0xFFFFFFFF
            self.owned += 1
            return self.owned
        emu.hook(buy_fn, buy, 0)
        emu.hook_import("GetProcAddress", lambda e: {"FtfpExtraTanksOwned": owned_fn, "FtfpExtraTanksBuy": buy_fn}
                        .get(e.cstring(e.arg(1)).decode(), 0), 8)
        for name, pop in (("GetTickCount", 0),):
            emu.hook_import(name, emu.record(name), pop)
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        emu.hook(0x004221A0, emu.record("dialog", args=1), 8)
        emu.hook(0x00401D00, emu.record("run", 0), 8)
        emu.hook(0x00422440, emu.record("free"), 0)
        emu.hook(0x00425120, emu.record("sounds"), 0)
        emu.hook(0x004251A0, emu.record("sound"), 4)
        table, price = emu.alloc(16), emu.text("Price:")
        inventory = emu.text("This is in your inventory.")
        emu.hook(0x00427060, lambda e: table, 0)
        emu.hook(0x00427050, lambda e: inventory if e.arg(0) == 0xE9 else price, 4)
        emu.hook(0x0041BE70, lambda e: e.calls.append(("sprite", e.arg(0))) or 1, 4)
        emu.hook(0x00408A40, emu.record("draw", args=3), 12)
        emu.hook(0x00408AE0, emu.record("draw", args=3), 24)
        emu.hook(0x00408B80, lambda e: (e.calls.append(("text", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 20)
        state, impl, scene = emu.alloc(0x40000), emu.alloc(0x100), emu.alloc(0x100)
        emu.write32(scene + 8, impl)
        emu.write32(impl + 0x10, state)
        emu.write32(impl + 0x0C, emu.alloc(0x40))
        emu.write32(state + 0x38C, money)
        emu.write32(emu.sym("_free_on"), int(free))
        emu.write32(emu.sym("_page_upgrades"), 1)
        emu.state, emu.scene = state, scene
        return emu

    def select(self, emu) -> None:
        emu.call(emu.sym("@on_mouse@20"), 3, *self.CELL, ecx=emu.scene)

    def test_price_and_order(self) -> None:
        emu = self.store(25_000, free=False, owned=0)
        self.select(emu)
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        texts = [c[1] for c in emu.calls if c[0] == "text"]
        self.assertIn("Extra Tank", texts)
        self.assertIn("Price:  $10000", texts)
        self.assertIn(("sprite", 157), emu.calls, "the stock Second Tank picture (ITEM_TANK2.png)")
        for _ in range(2):
            emu.call(emu.sym("_buy"), emu.scene)
        self.assertEqual(self.owned, 2)
        self.assertEqual(emu.read32(emu.state + 0x38C), 5_000)
        self.assertEqual(emu.read32(emu.state + 0x24), 20_000, "total spent")
        self.assertIn(("dialog", (0xEC,)), emu.calls, "the game's Buy this item? question")
        emu.call(emu.sym("_buy"), emu.scene)                     # $5,000 left: too little
        self.assertEqual(self.owned, 2)
        self.assertIn(("hint", (2,)), emu.calls)

    def test_free_upgrades(self) -> None:
        emu = self.store(0, free=True, owned=0)
        self.select(emu)
        for _ in range(4):
            emu.call(emu.sym("_buy"), emu.scene)
        self.assertEqual(self.owned, 3)
        self.assertEqual(emu.read32(emu.state + 0x38C), 0)
        self.assertIn(("hint", (0x1C,)), emu.calls, "the fourth: You already own this!")
        emu.calls.clear()
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        self.assertIn(("text", "This is in your inventory."), emu.calls)

    def test_hidden_without_the_setting(self) -> None:
        emu = self.store(25_000, free=False, owned=None)
        self.select(emu)
        self.assertEqual(emu.read32(emu.sym("_selected"), signed=True), -1)


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class SellingTanks(unittest.TestCase):
    """Tanks 3-5 with "For sale" On sell alongside the Sale Tank through the game's own sale code."""

    PRICE = 40

    def rig(self, rolls=None) -> tuple[Rig, int]:
        rig = Rig()
        emu = rig.emu
        emu.write32(0x0045ABDC, rig.state)
        scene = emu.alloc(0x100)
        emu.write32(scene + 0x70, rig.state)
        emu.write32(scene + 0x6C, rig.holder)
        emu.write32(rig.sym["_prev_roll"], 0x00424240)
        for va, pop in ((0x00413C50, 0), (0x00415320, 0), (0x00425120, 0), (0x0040AE20, 4)):
            emu.hook(va, lambda e: 0, pop)
        if rolls is not None:
            def roll(e) -> int:
                rig.rolls.append(e.arg(0))
                return rolls(e.arg(0))
            emu.hook(0x00403240, roll, 0)
        for body in range(21):                                    # every species priced at its base price
            for fin in range(21):
                at = rig.state + 0x14B40 + (body * 31 + fin) * 40
                emu.write32(at + 0x20, self.PRICE)
                emu.write32(at + 0x24, self.PRICE)
        rig.set(0x38C, 1000)
        rig.set(0x26C, 2)                                         # Advertising level 2
        return rig, scene

    def roll(self, rig: Rig, scene: int, browsing: int = 10) -> None:
        rig.emu.call(rig.sym["@roll_hook@12"], browsing, ecx=scene)

    def test_a_selling_extra_tank_sells_from_its_own_block(self) -> None:
        rig, scene = self.rig(rolls=lambda n: 0)                   # every roll succeeds
        rig.var("_selling", 0b010)                                 # Tank Four
        fishes = {3: fish(NOW, 4, 8, 25, 90, 60), 7: fish(NOW, 6, 6, 30, 90, 60)}
        rig.put_extra(1, block_with(fishes))
        sale_before = rig.tank(2)
        self.roll(rig, scene)
        self.assertEqual(struct.unpack_from("<I", rig.extra(1), 3 * SLOT)[0], 0, "the first fish in Tank Four sold")
        self.assertEqual(rig.extra(1)[7 * SLOT: 8 * SLOT], fishes[7])
        self.assertEqual(rig.tank(2), sale_before, "the Sale Tank is untouched")
        self.assertEqual(rig.get(0x38C), 1000 + self.PRICE)
        self.assertEqual(rig.get(0x28), 1, "fish sold")
        self.assertNotEqual(rig.emu.read32(scene + 0x58), 0, "the 5-second pause")

    def test_the_sale_tank_comes_first_and_one_sale_a_second(self) -> None:
        rig, scene = self.rig(rolls=lambda n: 0)
        rig.var("_selling", 0b111)
        own = fish(NOW, 4, 8, 25, 90, 60)
        rig.put_tank(2, block_with({5: own}))
        extra = block_with({0: fish(NOW, 9, 9, 25, 90, 60)})
        for e in range(3):
            rig.put_extra(e, extra)
        self.roll(rig, scene)
        self.assertEqual(struct.unpack_from("<I", rig.tank(2), 5 * SLOT)[0], 0)
        self.assertEqual([rig.extra(e) for e in range(3)], [extra] * 3, "one sale only")
        self.assertEqual(rig.get(0x28), 1)

    def test_every_fish_in_the_pool_gets_the_stock_roll(self) -> None:
        for selling, owned, rolls in ((0b000, 3, 3), (0b001, 3, 5), (0b011, 3, 6), (0b011, 1, 5)):
            with self.subTest(selling=selling, owned=owned):
                rig, scene = self.rig(rolls=lambda n: n - 1)       # no roll succeeds
                rig.var("_selling", selling)
                rig.var("_owned", owned)
                rig.put_tank(2, block_with({s: fish(NOW, 4, 8, 25, 90, 60) for s in range(3)}))
                rig.put_extra(0, block_with({s: fish(NOW, 4, 8, 25, 90, 60) for s in range(2)}))
                rig.put_extra(1, block_with({0: fish(NOW, 4, 8, 25, 90, 60)}))
                self.roll(rig, scene)
                self.assertEqual(rig.rolls.count(900), rolls)
                self.assertEqual(rig.get(0x28), 0)

    def test_all_off_is_the_stock_roll(self) -> None:
        tank = block_with({s: fish(NOW, (s * 5) % 21, (s * 3) % 21, 20 + s, 90 - s, 60) for s in range(8)})
        results = []
        for direct in (False, True):
            rig, scene = self.rig()
            rig.var("_selling", 0)
            rig.put_tank(2, tank)
            rig.put_extra(0, tank)
            for _ in range(40):
                rig.emu.write32(scene + 0x58, 0)
                if direct:
                    rig.emu.call(0x00424240, 10, ecx=scene)
                else:
                    self.roll(rig, scene)
            results.append((rig.tank(2), rig.extra(0), rig.get(0x38C), rig.get(0x28), list(rig.rolls)))
        self.assertEqual(results[0], results[1])
        self.assertGreater(results[0][3], 0, "something sold")

    def test_a_fish_sells_from_an_extra_tank_exactly_as_from_the_sale_tank(self) -> None:
        """The same fish, the same dice, every game-wide effect the sale reads on: research
        (Advertising 3), every ornament and owned item, the Golden Seahorse, the magic fish found,
        the player's own price above and below the base price."""
        tank = block_with({s: fish(NOW, (s * 7) % 21, (s * 5) % 21, 21 + s, 90 - 3 * s, 60, disease=s % 3 == 0)
                           for s in range(12)})
        results = []
        for in_extra in (False, True):
            rig, scene = self.rig()
            for offset in (0x154, 0x21C, 0x208, 0x1F4, 0x1E0, 0x1CC, 0x1B8, 0x1E1E4, 0x1E1E8, 0x1E1EC, 0x1E1F0):
                rig.set(offset, 1)
            rig.set(0x26C, 3)
            for body in range(21):
                for fin in range(21):
                    at = rig.state + 0x14B40 + (body * 31 + fin) * 40
                    rig.emu.write32(at + 0x20, 30 + (body * 3 + fin) % 50)     # asking prices around the base
            if in_extra:
                rig.var("_selling", 0b001)
                rig.put_extra(0, tank)
            else:
                rig.put_tank(2, tank)
            for _ in range(60):
                rig.emu.write32(scene + 0x58, 0)
                self.roll(rig, scene, browsing=40)
            left = rig.extra(0) if in_extra else rig.tank(2)
            results.append((left, rig.get(0x38C), rig.get(0x28), rig.get(0x20), list(rig.rolls)))
        self.assertEqual(results[0], results[1])
        self.assertGreater(results[0][2], 2, "fish sold")

    def test_a_tank_with_for_sale_off_never_sells(self) -> None:
        rig, scene = self.rig(rolls=lambda n: 0)
        rig.var("_selling", 0b001)
        tank = block_with({0: fish(NOW, 4, 8, 25, 90, 60)})
        for e in range(3):
            rig.put_extra(e, tank)
        for _ in range(3):
            rig.emu.write32(scene + 0x58, 0)
            self.roll(rig, scene)
        self.assertEqual(rig.extra(1), tank)
        self.assertEqual(rig.extra(2), tank)
        self.assertEqual(rig.get(0x28), 1, "Tank Three's one fish only")

    def test_an_extra_tank_on_screen_sells_from_its_place(self) -> None:
        rig, scene = self.rig(rolls=lambda n: 0)
        rig.var("_selling", 0b100)
        rig.var("_shown", 2)                                        # Tank Five in Tank One's place
        rig.put_tank(0, block_with({2: fish(NOW, 4, 8, 25, 90, 60)}))
        one = block_with({0: fish(NOW, 1, 1, 25, 90, 60)})
        rig.put_extra(2, one)                                       # Tank One, waiting in the DLL
        self.roll(rig, scene)
        self.assertEqual(struct.unpack_from("<I", rig.tank(0), 2 * SLOT)[0], 0)
        self.assertEqual(rig.extra(2), one)

    def test_the_count_pictures_and_crowd_cover_every_selling_tank(self) -> None:
        rig, scene = self.rig()
        rig.var("_selling", 0b011)
        rig.put_tank(2, block_with({**{s: fish(NOW, 4, 8, 25) for s in range(3)}, 3: fish(NOW, 4, 8, 3),
                                    4: fish(NOW, 22, 22, 21)}))
        rig.put_extra(0, block_with({s: fish(NOW, 4, 8, 25) for s in range(9)}))
        rig.put_extra(1, block_with({0: fish(NOW, 4, 8, 4), 1: fish(NOW, 4, 8, 25, health=0)}))
        rig.put_extra(2, block_with({s: fish(NOW, 4, 8, 25) for s in range(5)}))   # For sale Off
        seen = []
        for name in ("_prev_pictures", "_prev_crowd", "_prev_for_sale_text"):
            thunk = rig.emu.thunk()
            rig.var(name, thunk)
            if name == "_prev_pictures":
                rig.emu.hook(thunk, lambda e: seen.append(("pictures", e.read32(scene + 0x64))) or 0, 4)
            elif name == "_prev_crowd":
                rig.emu.hook(thunk, lambda e: seen.append(("crowd", e.arg(0))) or 0, 4)
            else:
                rig.emu.hook(thunk, lambda e: seen.append(("text", e.arg(2))) or 0, 0)
        rig.emu.call(rig.sym["@pictures_hook@12"], 1, ecx=scene)
        rig.emu.call(rig.sym["@crowd_hook@12"], 100, ecx=rig.holder)
        rig.emu.call(rig.sym["_for_sale_text_hook"], rig.emu.alloc(16), rig.emu.text("%d"), 3)
        # Pictures: live, healthy, not a seahorse: 4 (Sale Tank) + 9 + 1 = 14. Adults for the crowd:
        # 4 (the seahorse counts, as stock) + 9 = 13 -> 2 * 2 * (13 // 3 - 4 // 3) = +12. For sale: 3 + 9 = 12.
        self.assertEqual(seen, [("pictures", 14), ("crowd", 112), ("text", 12)])

    def test_the_crowd_never_passes_a_full_tank(self) -> None:
        rig, scene = self.rig()
        rig.var("_selling", 0b001)
        rig.put_tank(2, block_with({s: fish(NOW, 4, 8, 25) for s in range(20)}))
        rig.put_extra(0, block_with({s: fish(NOW, 4, 8, 25) for s in range(21)}))
        seen = []
        thunk = rig.emu.thunk()
        rig.var("_prev_crowd", thunk)
        rig.emu.hook(thunk, lambda e: seen.append(e.arg(0)) or 0, 4)
        rig.emu.call(rig.sym["@crowd_hook@12"], 100, ecx=rig.holder)
        self.assertEqual(seen, [100 + 2 * 2 * (21 // 3 - 20 // 3)])

    def test_all_off_leaves_count_pictures_and_crowd_stock(self) -> None:
        rig, scene = self.rig()
        rig.var("_selling", 0)
        rig.put_extra(0, block_with({s: fish(NOW, 4, 8, 25) for s in range(9)}))
        rig.emu.write32(scene + 0x64, 77)
        seen = []
        for name in ("_prev_pictures", "_prev_crowd", "_prev_for_sale_text"):
            thunk = rig.emu.thunk()
            rig.var(name, thunk)
            rig.emu.hook(thunk, (lambda e, n=name: seen.append(
                e.read32(scene + 0x64) if n == "_prev_pictures" else e.arg(0) if n == "_prev_crowd" else e.arg(2)) or 0),
                0 if name == "_prev_for_sale_text" else 4)
        rig.emu.call(rig.sym["@pictures_hook@12"], 1, ecx=scene)
        rig.emu.call(rig.sym["@crowd_hook@12"], 100, ecx=rig.holder)
        rig.emu.call(rig.sym["_for_sale_text_hook"], rig.emu.alloc(16), rig.emu.text("%d"), 3)
        self.assertEqual(seen, [77, 100, 3])

    def test_thoughts_look_at_one_selling_tank(self) -> None:
        for pick, expect in ((0, "sale"), (1, "four"), (2, "five")):
            with self.subTest(pick=pick):
                rig, scene = self.rig(rolls=lambda n, p=pick: p)
                rig.var("_selling", 0b110)
                sale = block_with({0: fish(NOW, 1, 1, 25)})
                four = block_with({0: fish(NOW, 2, 2, 25)})
                five = block_with({0: fish(NOW, 3, 3, 25)})
                rig.put_tank(2, sale)
                rig.put_extra(1, four)
                rig.put_extra(2, five)
                seen = []
                thunk = rig.emu.thunk()
                rig.var("_prev_thoughts", thunk)
                rig.emu.hook(thunk, lambda e: seen.append(rig.tank(2)) or 12, 0)
                view = rig.emu.alloc(0x6000)
                rig.emu.write32(view + 0x5DE4, rig.state)
                rig.emu.call(rig.sym["@thoughts_hook@8"], ecx=view)
                self.assertEqual(seen, [{"sale": sale, "four": four, "five": five}[expect]])
                self.assertEqual((rig.tank(2), rig.extra(1), rig.extra(2)), (sale, four, five), "lent back")
                self.assertIn(3, rig.rolls, "Random(3): the Sale Tank and two selling tanks")

    def test_the_toggle(self) -> None:
        rig = Rig()
        stock = rig.emu.thunk()
        rig.emu.hook(stock, lambda e: 0, 12)                        # the stock mouse: nothing there
        rig.var("_prev_mouse", stock)
        rig.var("_shown", 1)
        for kind in (2, 3):
            rig.emu.call(rig.sym["@mouse_hook@20"], kind, 60, 110, ecx=rig.impl)
        self.assertEqual(rig.var("_selling"), 0b010)
        for kind in (2, 3):
            rig.emu.call(rig.sym["@mouse_hook@20"], kind, 60, 110, ecx=rig.impl)
        self.assertEqual(rig.var("_selling"), 0)
        rig.var("_owned", 1)                                        # Tank Four not bought: no toggle
        for kind in (2, 3):
            rig.emu.call(rig.sym["@mouse_hook@20"], kind, 60, 110, ecx=rig.impl)
        self.assertEqual(rig.var("_selling"), 0)
        rig.var("_shown", -1)                                       # a stock tank: no toggle
        rig.var("_owned", 3)
        for kind in (2, 3):
            rig.emu.call(rig.sym["@mouse_hook@20"], kind, 60, 110, ecx=rig.impl)
        self.assertEqual(rig.var("_selling"), 0)

    def test_the_sign(self) -> None:
        for shown, on, drawn_stock, drawn_own in ((2, 0, [], []), (2, 1, [(620, 360), (580, 415)], []),
                                                  (0, 1, [], [(580, 415), (620, 360)]), (1, 0, [], [])):
            with self.subTest(shown=shown, on=on):
                rig = Rig()
                rig.var("_shown", shown)
                rig.var("_selling", on << shown)
                stock, own = [], []
                rig.emu.write32(rig.sym["_prev_sale_sign"], 0x00408A40)
                rig.emu.write32(rig.sym["_prev_sale_shadow"], 0x00408A40)
                rig.emu.write32(rig.sym["_prev_decor"], 0x0041D340)
                rig.emu.hook(0x0041D340, lambda e: 0, 0)
                rig.emu.hook(0x0041BE70, lambda e: 0x5000 + e.arg(0), 4)
                rig.emu.hook(0x00408A40, lambda e: (own if e.arg(0) in (0x5003, 0x5004) and not rig.var("_drawing_extra")
                                                    else stock).append((e.arg(1), e.arg(2))) or 0, 12)
                rig.var("_drawing_extra", 1)
                rig.emu.call(rig.sym["@sale_sign_hook@20"], 0x1234, 620, 360, ecx=rig.impl)
                rig.emu.call(rig.sym["@sale_shadow_hook@20"], 0x1234, 580, 415, ecx=rig.impl)
                rig.var("_drawing_extra", 0)
                rig.emu.call(rig.sym["@decor_hook@8"], ecx=rig.impl)
                self.assertEqual((stock, own), (drawn_stock, drawn_own))


class FakeFiles:
    """CreateFileW / ReadFile / WriteFile / MoveFileExW / ... over a dict."""

    def __init__(self, emu, folder: str) -> None:
        self.emu, self.files, self.handles, self.next = emu, {}, {}, 0x100
        self.folder = folder
        hook = emu.hook_import
        hook("GetModuleHandleW", lambda e: 0x7000_0000 if e.wstring(e.arg(0)).lower() == "shell32.dll" else 0, 4)
        hook("LoadLibraryW", lambda e: 0x7000_0000, 4)
        self.special = emu.thunk()
        emu.hook(self.special, self._special, 16)
        hook("GetProcAddress", lambda e: self.special, 8)
        hook("GetModuleFileNameW", self._exe_name, 12)
        hook("CreateDirectoryW", lambda e: 1, 8)
        hook("CreateFileW", self._create, 28)
        hook("WriteFile", self._write, 20)
        hook("ReadFile", self._read, 20)
        hook("FlushFileBuffers", lambda e: 1, 4)
        hook("CloseHandle", lambda e: 1, 4)
        hook("MoveFileExW", self._move, 12)
        hook("DeleteFileW", lambda e: self.files.pop(e.wstring(e.arg(0)), None) is not None, 4)

    def _special(self, e) -> int:
        out = (self.folder + "\0").encode("utf-16-le")
        e.uc.mem_write(e.arg(1), out)
        return 1

    def _exe_name(self, e) -> int:
        text = "C:\\Games\\Fish Tycoon - Modded Upgrades\\Fish Tycoon - Modded Upgrades.exe"
        e.uc.mem_write(e.arg(1), (text + "\0").encode("utf-16-le"))
        return len(text)

    def _create(self, e) -> int:
        path, access, disposition = e.wstring(e.arg(0)), e.arg(1), e.arg(4)
        if disposition == 3 and path not in self.files:      # OPEN_EXISTING
            return 0xFFFFFFFF
        if disposition == 2:                                 # CREATE_ALWAYS
            self.files[path] = b""
        self.next += 4
        self.handles[self.next] = [path, 0]
        return self.next

    def _write(self, e) -> int:
        h, buf, n, out = e.arg(0), e.arg(1), e.arg(2), e.arg(3)
        path = self.handles[h][0]
        self.files[path] += bytes(e.uc.mem_read(buf, n))
        e.write32(out, n)
        return 1

    def _read(self, e) -> int:
        h, buf, n, out = e.arg(0), e.arg(1), e.arg(2), e.arg(3)
        path, pos = self.handles[h]
        chunk = self.files[path][pos: pos + n]
        e.uc.mem_write(buf, chunk)
        self.handles[h][1] = pos + len(chunk)
        e.write32(out, len(chunk))
        return 1

    def _move(self, e) -> int:
        src, dst, flags = e.wstring(e.arg(0)), e.wstring(e.arg(1)), e.arg(2)
        if src not in self.files or (dst in self.files and not flags & 1):
            return 0
        self.files[dst] = self.files.pop(src)
        return 1


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class SavesAndSidecar(unittest.TestCase):
    PATH = "C:\\Docs\\LDW\\Fish Tycoon - Modded Upgrades\\Fish Tycoon Fix Patcher Data\\Extra Tanks 3.dat"

    def rig(self):
        rig = Rig()
        files = FakeFiles(rig.emu, "C:\\Docs")
        saved = []

        def save(e) -> int:
            saved.append((e.arg(0), bytes(e.uc.mem_read(rig.state + FISH_BASE, TANK))))
            return 1
        stock_save = rig.emu.thunk()
        rig.emu.hook(stock_save, save, 4)
        stock_load = rig.emu.thunk()
        rig.emu.hook(stock_load, lambda e: 1, 4)
        rig.var("_prev_save", stock_save)
        rig.var("_prev_load", stock_load)
        return rig, files, saved

    def test_round_trip(self) -> None:
        rig, files, saved = self.rig()
        tank_one = block_with({0: fish(NOW, 1, 1, 22)})
        extras = [block_with({s: fish(NOW, e + 2, s, 20 + s) for s in range(e + 1)}) for e in range(3)]
        rig.put_tank(0, extras[1])                 # extra 1 on screen
        rig.put_extra(1, tank_one)
        rig.put_extra(0, extras[0])
        rig.put_extra(2, extras[2])
        rig.var("_shown", 1)
        rig.var("_owned", 2)
        rig.var("_selling", 0b011)
        self.assertEqual(rig.emu.call(rig.sym["@save_slot_hook@12"], 3, ecx=rig.state) & 0xFF, 1)
        self.assertEqual(saved, [(3, tank_one)], "the save got Tank One in its own place")
        self.assertEqual(rig.tank(0), extras[1], "the extra is back on screen after the save")
        data = files.files[self.PATH]
        self.assertEqual(len(data), 28 + 3 * TANK)
        self.assertEqual(struct.unpack_from("<7I", data)[:2], (0x54585446, 3))
        self.assertEqual(struct.unpack_from("<I", data, 20)[0], 2, "two bought")
        self.assertEqual(struct.unpack_from("<I", data, 24)[0], 0b011, "For sale on Tanks 3 and 4")
        self.assertEqual(data[28:], b"".join(extras))
        self.assertNotIn(self.PATH + ".tmp", files.files)
        # Load: the extras come back from the file; Tank One is the save's.
        for e in range(3):
            rig.put_extra(e, bytes(TANK))
        rig.put_tank(0, tank_one)
        rig.var("_owned", 0)
        rig.var("_selling", 0)
        rig.emu.call(rig.sym["@load_hook@12"], 3, ecx=rig.state)
        self.assertEqual(rig.var("_selling"), 0b011)
        self.assertEqual([rig.extra(e) for e in range(3)], extras)
        self.assertEqual(rig.var("_owned"), 2)
        self.assertEqual(rig.var("_shown"), -1)
        self.assertEqual(rig.var("_owner"), rig.state)

    def test_settings_slot_is_not_ours(self) -> None:
        rig, files, saved = self.rig()
        rig.emu.call(rig.sym["@save_slot_hook@12"], 0, ecx=rig.state)
        self.assertEqual(files.files, {})

    def test_damaged_file_is_set_aside_and_extras_start_empty(self) -> None:
        rig, files, _ = self.rig()
        good = 28 + 3 * TANK
        files.files[self.PATH] = b"FTXT" + bytes(good - 4)
        rig.put_extra(0, block_with({0: fish(NOW, 1, 1, 22)}))
        rig.emu.call(rig.sym["@load_hook@12"], 3, ecx=rig.state)
        self.assertEqual(rig.extra(0), bytes(TANK))
        self.assertNotIn(self.PATH, files.files)
        self.assertIn(self.PATH[:-4] + ".unreadable-1.dat", files.files)

    def test_missing_file_means_empty_extras(self) -> None:
        rig, files, _ = self.rig()
        rig.put_extra(2, block_with({0: fish(NOW, 1, 1, 22)}))
        rig.emu.call(rig.sym["@load_hook@12"], 4, ecx=rig.state)
        self.assertEqual(rig.extra(2), bytes(TANK))
        self.assertEqual(files.files, {})

    def test_new_game_empties_them(self) -> None:
        rig, _files, _ = self.rig()
        rig.put_extra(1, block_with({0: fish(NOW, 1, 1, 22)}))
        rig.var("_shown", -1)
        rig.emu.call(rig.sym["@new_game_hook@8"], ecx=rig.state)
        self.assertEqual(rig.extra(1), bytes(TANK))
        self.assertEqual(rig.var("_owned"), 0, "a new game owns none")
        self.assertEqual(rig.var("_selling"), 0, "and sells from none")
        self.assertEqual(rig.var("_owner"), rig.state)

    def test_a_failed_game_save_writes_no_sidecar(self) -> None:
        rig, files, _ = self.rig()
        failing = rig.emu.thunk()
        rig.emu.hook(failing, lambda e: 0, 4)
        rig.var("_prev_save", failing)
        rig.emu.call(rig.sym["@save_slot_hook@12"], 2, ecx=rig.state)
        self.assertEqual(files.files, {})


@unittest.skipUnless(HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready(),
                     "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class AllOrNone(unittest.TestCase):
    SITES = (0x4218FF, 0x421AAA, 0x421D43, 0x421FFB, 0x42208E, 0x41A663, 0x41AAC3, 0x421646, 0x427B30,
             0x422013, 0x42203F, 0x41D44A, 0x41D467, 0x4246FB, 0x415131, 0x423F52, 0x423FEE, 0x423927)
    SLOTS = (0x4424D0, 0x4424D4)

    def rig(self, other_module: int = 0):
        rig = Rig()
        emu = rig.emu
        emu.hook_import("VirtualProtect", lambda e: e.write32(e.arg(3), 0x20) or 1, 16)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetModuleHandleW", lambda e: 0x400000, 4)

        def handle_from(e) -> int:
            address = e.arg(1)
            module = other_module if other_module and other_module <= address < other_module + 0x10000 else 0x400000
            e.write32(e.arg(2), module)
            return 1
        emu.hook_import("GetModuleHandleExW", handle_from, 12)
        return rig

    def code(self, rig: Rig) -> bytes:
        return b"".join(bytes(rig.emu.uc.mem_read(va, 6)) for va in self.SITES + self.SLOTS)

    def install(self, rig: Rig) -> int:
        if not rig.emu.call(rig.sym["_prepare"]):
            return 0
        return rig.emu.call(rig.sym["_ftfp_install_sites"], rig.sym["_writes"], len(self.SITES) + len(self.SLOTS))

    def test_every_site_or_none(self) -> None:
        rig = self.rig()
        before = self.code(rig)
        rig.emu.uc.mem_write(0x421D43, b"\xE8\x00\x00\x00\x00")    # one site not stock
        self.assertEqual(self.install(rig), 0)
        after = self.code(rig)
        self.assertEqual(after[:12] + after[18:], before[:12] + before[18:], "a site was written")

    def test_all_sites_go_in(self) -> None:
        rig = self.rig()
        self.assertEqual(self.install(rig), 1)
        dll_base = 0x10000000
        for va in self.SITES:
            op = rig.emu.uc.mem_read(va, 1)[0]
            rel = struct.unpack("<i", rig.emu.uc.mem_read(va + 1, 4))[0]
            self.assertGreaterEqual(va + 5 + rel, dll_base, hex(va))
            self.assertIn(op, (0xE8, 0xE9))
        for va in self.SLOTS:
            self.assertGreaterEqual(rig.emu.read32(va), dll_base)
        self.assertEqual(rig.var("_prev_load"), 0x41AE70)
        self.assertEqual(rig.var("_prev_save"), 0x419100)

    def test_ds_store_sites_are_chained(self) -> None:
        other = 0x20F00000                              # inside the emulator's heap: "another module"
        rig = self.rig(other_module=other)
        stub = other + 0x100
        rel = (stub - (0x421AAA + 5)) & 0xFFFFFFFF
        rig.emu.uc.mem_write(0x421AAA, b"\xE8" + struct.pack("<I", rel))
        rig.emu.write32(0x4424D0, other + 0x200)
        self.assertEqual(self.install(rig), 1)
        self.assertEqual(rig.var("_prev_tick_show") & 0xFFFFFFFF, stub)
        self.assertEqual(rig.var("_prev_load") & 0xFFFFFFFF, other + 0x200)

    def test_a_branch_into_the_game_itself_is_refused(self) -> None:
        rig = self.rig()
        rel = (0x401000 - (0x421AAA + 5)) & 0xFFFFFFFF
        rig.emu.uc.mem_write(0x421AAA, b"\xE8" + struct.pack("<I", rel))
        self.assertEqual(self.install(rig), 0)


class BackupsHoldTheExtraTanks(unittest.TestCase):
    """src/save_backup.py with the setting's files: "Extra Tanks <n>.dat" beside each save, the game's
    older generation (n + 20) too, and a set-aside unreadable file."""

    def setUp(self) -> None:
        import save_backup
        from test_save_tools import make_folder
        self.sb = save_backup
        self.temp = tempfile.TemporaryDirectory()
        self.folder = make_folder(Path(self.temp.name), "fish", ["Ana", "Bo", "Cy", "Di", "Ed"],
                                  "Fish Tycoon - Modded Upgrades")
        self.data = self.folder / "Fish Tycoon Fix Patcher Data"
        self.data.mkdir()
        for name in ("Extra Tanks 1.dat", "Extra Tanks 21.dat", "Extra Tanks 2.dat", "Extra Tanks 22.dat",
                     "Extra Tanks 2.unreadable-1.dat"):
            (self.data / name).write_bytes(f"{name} first".encode())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def processes(self):
        from test_save_backup import FakeProcesses
        return FakeProcesses()

    def test_every_file_names_its_slot(self) -> None:
        for name, slot in (("Extra Tanks 1.dat", 1), ("Extra Tanks 21.dat", 1), ("Extra Tanks 25.dat", 5),
                           ("Extra Tanks 2.unreadable-1.dat", 2), ("Extra Tanks 3.dat.tmp", 3),
                           ("DS Fish 22.dat", 2), ("Extra Tanks 26.dat", "unknown"), ("Extra Tanks 0.dat", "unknown")):
            self.assertEqual(self.sb.file_slot("fish", Path("Fish Tycoon Fix Patcher Data") / name), slot, name)

    def test_a_backup_holds_them_and_a_whole_restore_puts_them_back(self) -> None:
        backup = self.sb.back_up_save_folder(self.folder, self.processes()).backup_folder
        for name in ("Extra Tanks 1.dat", "Extra Tanks 22.dat"):
            self.assertEqual((backup / "Fish Tycoon Fix Patcher Data" / name).read_bytes(), f"{name} first".encode())
        (self.data / "Extra Tanks 1.dat").write_bytes(b"later")
        (self.data / "Extra Tanks 3.dat").write_bytes(b"new")
        self.sb.restore_backup("fish", self.folder, backup, None, self.processes())
        self.assertEqual((self.data / "Extra Tanks 1.dat").read_bytes(), b"Extra Tanks 1.dat first")
        self.assertFalse((self.data / "Extra Tanks 3.dat").exists())

    def test_a_one_slot_restore_takes_only_that_slots_files(self) -> None:
        backup = self.sb.back_up_save_folder(self.folder, self.processes()).backup_folder
        for name in ("Extra Tanks 1.dat", "Extra Tanks 21.dat", "Extra Tanks 2.dat", "Extra Tanks 22.dat"):
            (self.data / name).write_bytes(b"later")
        (self.data / "Extra Tanks 2.unreadable-1.dat").unlink()
        self.sb.restore_backup("fish", self.folder, backup, 2, self.processes())
        for name in ("Extra Tanks 2.dat", "Extra Tanks 22.dat", "Extra Tanks 2.unreadable-1.dat"):
            self.assertEqual((self.data / name).read_bytes(), f"{name} first".encode(), name)
        for name in ("Extra Tanks 1.dat", "Extra Tanks 21.dat"):
            self.assertEqual((self.data / name).read_bytes(), b"later", f"slot 1's {name} is left alone")


class Manifest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.settings = {s["id"]: s for s in self.manifest["settings"]}

    def test_setting(self) -> None:
        s = self.settings["extra_tanks"]
        self.assertEqual(s["name"], "3 extra tanks")
        self.assertTrue(s["summary"].startswith("EXPERIMENTAL - USE AT OWN RISK."))
        self.assertTrue(s["description"].startswith("EXPERIMENTAL - USE AT OWN RISK."))
        self.assertFalse(s["default"])
        self.assertTrue(s["separate_output"], "new content goes in the Modded Upgrades copy")
        self.assertIn("empty", s["warning"].lower())
        self.assertTrue(s["companion"]["startup_loader"])
        self.assertEqual(s["requires_settings"], ["ds_store"], "sold on DS Store Items' Upgrades screen")

    def test_companion_files_are_pinned(self) -> None:
        companion = self.settings["extra_tanks"]["companion"]
        source = ROOT / companion["source"]
        names = {e["path"] for e in companion["files"]}
        self.assertIn("Extra Tanks.dll", names)
        for image in ("ExtraTank1Button.png", "ExtraTank2Button.png", "ExtraTank3Button.png",
                      "Tank1ButtonNormal.png", "TankArrowLeft.png", "TankArrowRight.png"):
            self.assertIn(f"Images/{image}", names)
        for entry in companion["files"]:
            data = (source / entry["path"]).read_bytes()
            self.assertEqual(len(data), entry["size"], entry["path"])
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"], entry["path"])

    def test_every_combination_is_pinned_with_and_without(self) -> None:
        pins = self.manifest["patched_sha256_by_settings"]
        without = [k for k in pins if "extra_tanks" not in k.split(",") and "ds_store" in k.split(",")]
        self.assertTrue(without)
        for key in without:
            with_it = ",".join(sorted(set(key.split(",")) | {"extra_tanks"}))
            self.assertIn(with_it, pins, f"no pin for {with_it}")
        for key in pins:
            if "extra_tanks" in key.split(","):
                self.assertIn("ds_store", key.split(","), f"{key}: the setting needs DS Store Items")

    def test_off_leaves_every_other_pin_unchanged(self) -> None:
        """With the setting off the output is byte-identical to the build before it: no
        manifest patch needs it, and no pin without it changed."""
        for patch in self.manifest["patches"]:
            self.assertNotIn("extra_tanks", patch.get("requires", []))
        try:
            base = subprocess.run(["git", "show", "origin/main:data/fish_manifest.json"], cwd=ROOT,
                                  capture_output=True, text=True, encoding="utf-8", check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("no origin/main to compare with")
        before = json.loads(base)["patched_sha256_by_settings"]
        pins = self.manifest["patched_sha256_by_settings"]
        for key, value in before.items():
            if key in pins:
                self.assertEqual(pins[key], value, key)

    @unittest.skipUnless(EXE.is_file(), "needs the vanilla Fish Tycoon.exe")
    def test_pins_match_a_fresh_build(self) -> None:
        import ds_fish_loader
        import fish_patcher
        pins = self.manifest["patched_sha256_by_settings"]
        vanilla = EXE.read_bytes()
        for enabled in ({"extra_tanks", "ds_fish", "ds_store"},
                        {"extra_tanks", "ds_fish", "ds_store", "maximizable_window", "fix_vanilla_bugs"},
                        {"extra_tanks", "ds_fish", "ds_store", "bigger_tanks"}):
            patched, _ = fish_patcher.apply_patch_bytes(vanilla, fish_patcher.active_patch_records(self.manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.fish_profile(enabled))
            self.assertEqual(hashlib.sha256(patched).hexdigest().upper(), pins[fish_patcher.settings_key(enabled)])
            self.assertIn("Extra Tanks.dll".encode("utf-16-le"), patched)


if __name__ == "__main__":
    unittest.main()
