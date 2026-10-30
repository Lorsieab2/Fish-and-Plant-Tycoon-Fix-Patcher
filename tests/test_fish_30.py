"""Bigger tanks: 30 fish, run in the game's own code (Unicorn, tests/store_emulator.py).

Every family of effects that reaches a fish through its record is run twice
with the same random numbers: on the vanilla executable with the fish in a
stock slot, and on the patched executable with the same fish in slot 29 (and
in slot 0). The results must be the same, byte for byte: slots 21-29 behave
exactly like slots 0-20. The selling limit keeps the stock game's 21 adults
for sale at once.
"""

from __future__ import annotations

import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

VANILLA = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Fish Tycoon"
           / "Fish Tycoon.exe")
SETTING = "bigger_tanks"
STATE_SIZE = 0x1E600
FISH, TANK, RECORD = 0x390, 0x51EC, 0x288
NOW = 1_000_000
SPEED = 0x1E168


def patched_exe(enabled: set[str]) -> bytes:
    manifest = combined.load_manifest("fish")
    data, _ = fish_patcher.apply_patch_bytes(VANILLA.read_bytes(), fish_patcher.active_patch_records(manifest, enabled))
    return data


def rec(tank: int, slot: int) -> int:
    return FISH + tank * TANK + slot * RECORD


def fish_record(age: int = 25, body: int = 5, fin: int = 7, health: int = 70, food: int = 50, disease: int = 0,
                pregnant: int = 0, live: int = NOW - 600, seed: int = 0) -> bytes:
    """A live fish as the game keeps it; the other fields a fixed pattern (the same in every copy)."""
    r = bytearray((i * 13 + seed * 7 + 1) & 0x3F for i in range(RECORD))
    struct.pack_into("<IIii", r, 0, live, 0, age, age)
    struct.pack_into("<i", r, 0x10, pregnant)
    struct.pack_into("<ii", r, 0x14, body, fin)                  # the mate's genes
    struct.pack_into("<iii", r, 0x3C, health, disease, food)
    struct.pack_into("<ii", r, 0x4C, body, fin)
    return bytes(r)


def _needs():
    ready = E is not None and VANILLA.is_file()
    return unittest.skipUnless(ready, "needs Unicorn and the vanilla executable")


@_needs()
class EmulatedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe30 = Path(cls.tmp.name) / "Fish Tycoon 30.exe"
        cls.exe30.write_bytes(patched_exe({SETTING}))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ harness
    def emulator(self, patched: bool, seed: int = 11):
        emu = E.Emulator(self.exe30 if patched else VANILLA, None, {})
        rng = random.Random(seed)
        emu.randoms = []

        def game_random(e):
            bound = e.arg(0)
            value = rng.randrange(bound) if bound > 0 else 0
            e.randoms.append((bound, value))
            return value
        emu.hook(0x00403240, game_random)
        emu.hook(0x004020D0, lambda e: 50_000)                       # the real-time clock
        emu.hook(0x004032C0, lambda e: NOW, 0)                       # the state's clock
        emu.calls = []
        state = emu.alloc(STATE_SIZE)
        impl = emu.alloc(0x400)
        view = emu.alloc(0x6000)
        emu.write32(impl + 0x34, state)
        emu.write32(impl + 0x3C, emu.alloc(4))
        emu.write32(emu.read32(impl + 0x3C), view)
        emu.write32(state + SPEED, 10)
        emu.state, emu.impl, emu.view = state, impl, view
        return emu

    def put(self, emu, tank: int, slot: int, record: bytes) -> None:
        emu.uc.mem_write(emu.state + rec(tank, slot), record)

    def get(self, emu, tank: int, slot: int) -> bytes:
        return bytes(emu.uc.mem_read(emu.state + rec(tank, slot), RECORD))

    def records(self, emu, tank: int) -> list[bytes]:
        return [self.get(emu, tank, s) for s in range(31)]

    def run_range(self, emu, start: int, stop: int, **regs) -> None:
        """Run the game's code from start until it reaches stop."""
        esp = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        for name, value in regs.items():
            emu.uc.reg_write(getattr(X, f"UC_X86_REG_{name.upper()}"), value & 0xFFFFFFFF)
        emu.uc.emu_start(start, stop, count=2_000_000)

    def update(self, emu) -> None:
        """The per-step fish update (0x41FE70), the tank screen's `this`."""
        emu.hook(0x0041FA30, self.new_baby, 0x38)
        emu.hook(0x00415E70, emu.record("view sync"), 4)
        emu.hook(0x00415380, emu.record("view move", args=4), 0x10)
        emu.hook(0x00413B00, emu.record("splash"), 0x0C)
        emu.hook(0x00425120, lambda e: 0, 0)
        emu.hook(0x004251A0, lambda e: 0, 4)
        emu.call(0x0041FE70, ecx=emu.impl, esi=emu.impl)

    @staticmethod
    def new_baby(emu) -> int:
        emu.calls.append(("baby", tuple(emu.arg(i) for i in range(14))))
        return 0

    # ------------------------------------------------------------ AddFish
    def test_addfish_fills_30_slots_then_refuses(self) -> None:
        for patched, slots in ((False, 21), (True, 30)):
            emu = self.emulator(patched)
            record = emu.alloc(RECORD)
            emu.uc.mem_write(record, fish_record())
            got = [emu.call(0x00419C50, 1, record, ecx=emu.state) for _ in range(slots + 2)]
            self.assertEqual(got[:slots], list(range(slots)))
            self.assertEqual([g & 0xFFFFFFFF for g in got[slots:]], [0xFFFFFFFF] * 2)
            self.assertEqual(self.get(emu, 1, slots - 1), fish_record())
            self.assertEqual(self.get(emu, 1, 30), bytes(RECORD), "record 30 is never a fish's")

    # ------------------------------------------------------------ the per-step update
    def update_result(self, patched: bool, layout: dict[tuple[int, int], bytes], seed: int):
        emu = self.emulator(patched, seed)
        for (tank, slot), record in layout.items():
            self.put(emu, tank, slot, record)
        self.update(emu)
        return emu

    def assert_same_fish(self, a, b, a_slots: dict[int, tuple[int, int]], b_slots: dict[int, tuple[int, int]]) -> None:
        for key, (tank, slot) in a_slots.items():
            self.assertEqual(self.get(a, tank, slot), self.get(b, *b_slots[key]), key)

    def test_update_reaches_slot_29_exactly_as_slot_0_and_the_stock_game(self) -> None:
        cases = {
            "adult": fish_record(),
            "hungry": fish_record(food=0, health=3),
            "sick": fish_record(disease=2, health=40),
            "baby": fish_record(age=2),
            "egg about to hatch": fish_record(age=0),
            "pregnant": fish_record(pregnant=1),
            "old": fish_record(age=200),
            "golden seahorse": fish_record(body=22, fin=22),
        }
        for name, record in cases.items():
            for seed in (1, 2, 3, 4):
                with self.subTest(name=name, seed=seed):
                    stock = self.update_result(False, {(0, 0): record}, seed)
                    first = self.update_result(True, {(0, 0): record}, seed)
                    last = self.update_result(True, {(0, 29): record}, seed)
                    self.assertEqual(self.get(stock, 0, 0), self.get(first, 0, 0))
                    self.assertEqual(self.get(first, 0, 0), self.get(last, 0, 29))
                    self.assertEqual(stock.randoms, last.randoms)
                    self.assertEqual(stock.calls, last.calls)
                    self.assertEqual(self.get(last, 0, 0), bytes(RECORD))

    def test_update_of_a_full_tank_of_30(self) -> None:
        """Breeding, crowding and sickness among many fish: 21 stock fish in slots 0-20 against the same
        21 fish in slots 9-29 (same order), and every one of 30 fish updated."""
        fish = [fish_record(seed=i, body=i % 20, fin=(i * 3) % 20, pregnant=int(i % 4 == 0),
                            disease=2 if i % 7 == 0 else 0, food=10 + i) for i in range(21)]
        for seed in (5, 6):
            stock = self.update_result(False, {(2, i): f for i, f in enumerate(fish)}, seed)
            moved = self.update_result(True, {(2, 9 + i): f for i, f in enumerate(fish)}, seed)
            self.assert_same_fish(stock, moved, {i: (2, i) for i in range(21)}, {i: (2, 9 + i) for i in range(21)})
            self.assertEqual(stock.randoms, moved.randoms)
            self.assertEqual(stock.calls, moved.calls)                       # the same babies, same genes
            self.assertIn("baby", [c[0] for c in moved.calls])
        full = self.update_result(True, {(2, i): fish_record(seed=i) for i in range(30)}, 7)
        for i in range(30):
            self.assertNotEqual(self.get(full, 2, i), fish_record(seed=i), f"slot {i} was not updated")

    # ------------------------------------------------------------ chemicals, medicines, growth hormone
    LOOPS = {
        # name: (loop top, loop exit, ebp)
        "Unknown Chemical": (0x00420EA0, 0x0042104F, 22),
        "growth hormone (age +2..6)": (0x00421100, 0x0042119A, 0x28),
        "health item (+6..15)": (0x00421210, 0x00421296, 0),
    }

    def item_loop(self, patched: bool, name: str, slot: int, seed: int):
        top, stop, ebp = self.LOOPS[name]
        emu = self.emulator(patched, seed)
        emu.hook(0x00415DF0, emu.record("sprites", args=3), 0x0C)
        emu.write32(emu.state + 0x384, 1)                            # the tank in use: Tank Two
        self.put(emu, 1, slot, fish_record(health=40))
        self.run_range(emu, top, stop, ebx=0, esi=emu.impl, ebp=ebp)
        return emu

    def test_items_reach_slot_29_exactly_as_slot_0(self) -> None:
        for name in self.LOOPS:
            for seed in range(1, 9):
                with self.subTest(item=name, seed=seed):
                    stock = self.item_loop(False, name, 0, seed)
                    last = self.item_loop(True, name, 29, seed)
                    self.assertEqual(self.get(stock, 1, 0), self.get(last, 1, 29))
                    self.assertEqual(stock.randoms, last.randoms)
                    calls = [(c[0], c[1][1:]) for c in stock.calls]
                    self.assertEqual(calls, [(c[0], c[1][1:]) for c in last.calls])
                    self.assertNotEqual(self.get(last, 1, 29), fish_record(health=40)) if name != "Unknown Chemical" \
                        else None

    # ------------------------------------------------------------ starter eggs and sickness crowding
    def test_starter_eggs_see_a_fish_in_slot_29(self) -> None:
        for patched, slot, eggs in ((False, None, 7), (True, None, 7), (False, 20, 3), (True, 29, 3), (True, 21, 3)):
            emu = self.emulator(patched)
            if slot is not None:
                self.put(emu, 2, slot, fish_record())
            self.run_range(emu, 0x0041FC90, 0x0041FD60, ecx=emu.impl)
            self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_EBP), eggs, (patched, slot))

    def test_sickness_crowding_counts_slot_29(self) -> None:
        for patched, slots, extra in ((False, [0, 20], 12), (True, [0, 29], 12), (True, list(range(30)), 180)):
            emu = self.emulator(patched)
            for s in slots:
                self.put(emu, 0, s, fish_record(disease=2))
            frame = E.STACK + E.STACK_SIZE - 0x2000                  # run_range's esp
            emu.write32(frame + 0x1C, 0)                             # the tank
            emu.write32(emu.state + 0x14, 1)                         # not Easy (Easy skips crowding)
            self.run_range(emu, 0x0041E246, 0x0041E28F, ebx=emu.impl, esi=0)
            self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_ESI), extra, (patched, slots))

    # ------------------------------------------------------------ the swimming fish (the view)
    def build_view(self, emu, tank: int, function: int = 0x00413D80) -> list[tuple[int, int]]:
        """The view's build (0x413D80) or refresh (0x415460) for a tank: each entry's (tank, slot)."""
        view = emu.view
        emu.write32(view + 0x5DE4, emu.state)
        emu.write32(view + 0x5DE8, emu.alloc(0x40))
        emu.write32(emu.state + 0x384, tank)
        image = emu.alloc(0x100)
        emu.hook(0x00410FD0, lambda e: 0, 0)
        emu.hook(0x004122A0, lambda e: 0, 8)
        emu.hook(0x0041BCA0, lambda e: image, 4)
        emu.hook(0x004095F0, lambda e: 0, 0x0C)
        emu.hook(0x0042D200, self.stack_probe, 0)
        emu.call(function, emu.state + rec(tank, 0), ecx=view)
        count = emu.read32(view + 0x5DD8)
        return [(emu.read32(view + 0x1080 + i * 0x84 + 0x40), emu.read32(view + 0x1080 + i * 0x84 + 0x44))
                for i in range(1, count + 1) if emu.uc.mem_read(view + 0x1080 + i * 0x84, 1)[0]]

    @staticmethod
    def stack_probe(emu) -> int:
        """The CRT's _chkstk (0x42D200): esp -= eax, keeping the return address."""
        esp = emu.uc.reg_read(X.UC_X86_REG_ESP)
        size = emu.uc.reg_read(X.UC_X86_REG_EAX)
        back = emu.read32(esp)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp + 4 - size - 4)
        emu.write32(esp + 4 - size - 4, back)
        return size

    def test_the_view_shows_all_30(self) -> None:
        for function in (0x00413D80, 0x00415460):
            for patched, slots in ((False, list(range(21))), (True, list(range(30)))):
                emu = self.emulator(patched)
                emu.uc.mem_write(emu.view + 0x1080, bytes(0x84 * 160))
                for s in range(31):
                    self.put(emu, 0, s, fish_record(seed=s))
                got = self.build_view(emu, 0, function)
                self.assertEqual(got, [(0, s) for s in slots], (hex(function), patched))

    # ------------------------------------------------------------ new game
    def test_new_game_clears_all_30(self) -> None:
        for patched, last in ((False, 20), (True, 29)):
            emu = self.emulator(patched)
            for t in range(4):
                for s in range(31):
                    self.put(emu, t, s, fish_record())
            emu.call(0x004198F0, ecx=emu.state)                     # clears +0 of every fish slot
            for t in range(4):
                self.assertEqual(emu.read32(emu.state + rec(t, last)), 0)
                self.assertNotEqual(emu.read32(emu.state + rec(t, last + 1)), 0)

    # ------------------------------------------------------------ selling: the stock limit holds
    def sale(self, patched: bool, adults: list[int], babies: list[int] = (), sells: bool = False, seed: int = 3):
        emu = self.emulator(patched, seed)
        scene = emu.alloc(0x100)
        emu.write32(scene + 0x70, emu.state)
        for s in adults:
            self.put(emu, 2, s, fish_record(seed=s))
        for s in babies:
            self.put(emu, 2, s, fish_record(age=5, seed=s))
        species = emu.state + 0x14B60 + (5 * 31 + 7) * 40             # body 5, fin 7: asking $10 of $100
        emu.write32(species, 10)
        emu.write32(species + 4, 100)
        emu.hook(0x00424010, emu.record("sold", args=1), 4)
        emu.hook(0x00403240, lambda e: (e.randoms.append((e.arg(0), 0 if sells else e.arg(0) - 1)),
                                        0 if sells else e.arg(0) - 1)[1])
        emu.call(0x00424240, 4, ecx=scene)
        return emu

    def tried(self, emu) -> int:
        return sum(1 for bound, _ in emu.randoms if bound == 0x384)

    def test_at_most_21_adults_are_for_sale_at_once(self) -> None:
        self.assertEqual(self.tried(self.sale(False, list(range(21)))), 21)            # the stock most
        self.assertEqual(self.tried(self.sale(True, list(range(30)))), 21)
        self.assertEqual(self.tried(self.sale(True, list(range(21)))), 21)
        self.assertEqual(self.tried(self.sale(True, list(range(10)))), 10)
        # babies take no place: the 21 adults after them are all tried, up to slot 29
        self.assertEqual(self.tried(self.sale(True, list(range(9, 30)), babies=list(range(9)))), 21)
        self.assertEqual(self.tried(self.sale(False, list(range(5, 21)), babies=list(range(5)))), 16)

    def test_a_fish_in_slot_29_sells_exactly_as_slot_0(self) -> None:
        stock = self.sale(False, [0], sells=True)
        last = self.sale(True, [29], babies=list(range(29)), sells=True)
        self.assertEqual(stock.calls, [("sold", (0,))])
        self.assertEqual(last.calls, [("sold", (29,))])
        self.assertEqual(stock.randoms, last.randoms)

    def test_the_crowd_counts_at_most_21_adults(self) -> None:
        for patched, adults, counted in ((False, 21, 21), (True, 30, 21), (True, 22, 21), (True, 21, 21),
                                         (True, 14, 14)):
            emu = self.emulator(patched)
            scene = emu.alloc(0x100)
            emu.write32(scene + 0x70, emu.state)
            for s in range(adults):
                self.put(emu, 2, s, fish_record(seed=s))
            self.run_range(emu, 0x00423E7D, 0x00423F29, edi=scene, ebx=0)
            self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_EBX), counted, (patched, adults))

    def test_the_selling_screen_says_at_most_21(self) -> None:
        for patched, adults, shown in ((False, 21, 21), (True, 30, 21), (True, 25, 21), (True, 12, 12)):
            emu = self.emulator(patched)
            scene = emu.alloc(0x100)
            emu.write32(scene + 0x70, emu.state)
            for s in range(adults):
                self.put(emu, 2, s, fish_record(seed=s))
            text = emu.text("%d")
            emu.hook(0x00427060, lambda e: 0, 0)
            emu.hook(0x00427050, lambda e, t=text: t, 4)
            emu.hook(0x0042B20B, lambda e: 0, 0)
            emu.hook(0x00408B80, lambda e: 0, 0x14)
            self.run_range(emu, 0x00423811, 0x00423921, ecx=scene)
            esp = emu.uc.reg_read(X.UC_X86_REG_ESP)
            self.assertEqual(emu.read32(esp), shown, (patched, adults))


if __name__ == "__main__":
    unittest.main()
