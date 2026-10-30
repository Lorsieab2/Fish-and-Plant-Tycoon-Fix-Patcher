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
        self.assertEqual(rig.emu.call(rig.sym["@save_slot_hook@12"], 3, ecx=rig.state) & 0xFF, 1)
        self.assertEqual(saved, [(3, tank_one)], "the save got Tank One in its own place")
        self.assertEqual(rig.tank(0), extras[1], "the extra is back on screen after the save")
        data = files.files[self.PATH]
        self.assertEqual(len(data), 20 + 3 * TANK)
        self.assertEqual(data[20:], b"".join(extras))
        self.assertNotIn(self.PATH + ".tmp", files.files)
        # Load: the extras come back from the file; Tank One is the save's.
        for e in range(3):
            rig.put_extra(e, bytes(TANK))
        rig.put_tank(0, tank_one)
        rig.emu.call(rig.sym["@load_hook@12"], 3, ecx=rig.state)
        self.assertEqual([rig.extra(e) for e in range(3)], extras)
        self.assertEqual(rig.var("_shown"), -1)
        self.assertEqual(rig.var("_owner"), rig.state)

    def test_settings_slot_is_not_ours(self) -> None:
        rig, files, saved = self.rig()
        rig.emu.call(rig.sym["@save_slot_hook@12"], 0, ecx=rig.state)
        self.assertEqual(files.files, {})

    def test_damaged_file_is_set_aside_and_extras_start_empty(self) -> None:
        rig, files, _ = self.rig()
        good = 20 + 3 * TANK
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
    SITES = (0x4218FF, 0x421AAA, 0x421D43, 0x421FFB, 0x42208E, 0x41A663, 0x41AAC3, 0x421646, 0x427B30)
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


class Manifest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.settings = {s["id"]: s for s in self.manifest["settings"]}

    def test_setting(self) -> None:
        s = self.settings["extra_tanks"]
        self.assertEqual(s["name"], "3 extra tanks")
        self.assertFalse(s["default"])
        self.assertTrue(s["separate_output"], "new content goes in the Modded Upgrades copy")
        self.assertIn("empty", s["warning"].lower())
        self.assertTrue(s["companion"]["startup_loader"])

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
        without = [k for k in pins if "extra_tanks" not in k.split(",")]
        for key in without:
            with_it = ",".join(sorted(set(filter(None, key.split(","))) | {"extra_tanks"}))
            self.assertIn(with_it, pins, f"no pin for {with_it}")
        self.assertIn("extra_tanks", pins)

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
        for enabled in ({"extra_tanks"}, {"extra_tanks", "maximizable_window", "fix_vanilla_bugs"},
                        {"extra_tanks", "ds_fish", "ds_store", "bigger_tanks"}):
            patched, _ = fish_patcher.apply_patch_bytes(vanilla, fish_patcher.active_patch_records(self.manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.fish_profile(enabled))
            self.assertEqual(hashlib.sha256(patched).hexdigest().upper(), pins[fish_patcher.settings_key(enabled)])
            self.assertIn("Extra Tanks.dll".encode("utf-16-le"), patched)


if __name__ == "__main__":
    unittest.main()
