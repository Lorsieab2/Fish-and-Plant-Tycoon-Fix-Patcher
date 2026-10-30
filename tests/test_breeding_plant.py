"""Breeding Guide, Plant Tycoon's model (src/breeding_plant.py) against the game's own code.

The emulated tests run the vanilla "Plant Tycoon.exe" in Unicorn (tests/store_emulator.py) and,
for Unused Flowers, the DLL rebuilt from its committed source: the value and name tables
(0x41D870, 0x41E550), the pollination (0x4240A0, and the DLL's tail hook at 0x4241B4), Mutation
Liquid (0x42FA80), the nursery's buy roll (0x436BE0), the visitor limit (0x43FF00), and a save
written by the game's own save code (0x41D120) after its own new game (0x41EF30). No save of the
owner's is used or committed: the save fixtures are built in a temporary folder.
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
sys.path.insert(0, str(ROOT / "tests"))

import breeding_plant as B  # noqa: E402

try:
    import store_emulator as E
    from unicorn import UC_HOOK_CODE
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

PLANT_EXE = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon" / "Plant Tycoon.exe"
FLOWERS_DLL = ROOT / "assets" / "plant_tycoon_flowers" / "Unused Flowers.dll"
RANDOM, CLOCK, MEMSET = 0x004033B0, 0x00403430, 0x00451280
STOCK = [(f, fl) for f in range(1, 24) for fl in range(1, 24)]
NEW = [(f, fl) for f in range(1, 24) for fl in range(24, 38)]

HAVE_EXE = E is not None and PLANT_EXE.is_file()
HAVE_DLL = HAVE_EXE and E.toolchain_ready()
needs_exe = unittest.skipUnless(HAVE_EXE, "needs Unicorn and the vanilla Plant Tycoon.exe")
needs_dll = unittest.skipUnless(HAVE_DLL, "needs Unicorn, the vanilla executable and the pinned MSVC toolset")


# ------------------------------------------------------------------ the model alone

class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stock = B.load(None, extras=False)
        self.extras = B.load(None, extras=True)

    def test_part_rarity_is_the_shop_packet_tier(self) -> None:
        """0x41DC60's packets: Common 1, 5, 9, 13, 17; Endangered 3, 7, 11, 15; Extinct the
        even genes 2-16 and 18-23; the new flowers (24-37) are the patcher's."""
        expected = {**{g: "Common" for g in (1, 5, 9, 13, 17)}, **{g: "Endangered" for g in (3, 7, 11, 15)},
                    **{g: "Extinct" for g in (2, 4, 6, 8, 10, 12, 14, 16, 18, 19, 20, 21, 22, 23)}}
        for kind in ("foliage", "flower"):
            for part in self.extras.parts(kind):
                want = "Patcher" if kind == "flower" and part.index >= 24 else expected[part.index]
                self.assertEqual(self.extras.part_rarity(part), want, (kind, part.index))
        self.assertEqual(sum(self.extras.part_rarity(p) == "Patcher" for p in self.extras.parts("flower")), 14)

    def test_extras_adds_the_322_new_species_only_when_on(self) -> None:
        self.assertEqual(len(self.stock.species()), 529)
        self.assertEqual(len(self.extras.species()), 851)
        self.assertFalse(any(s.patcher for s in self.stock.species()))
        new = [s for s in self.extras.species() if s.patcher]
        self.assertEqual(sorted(s.key for s in new), NEW)
        self.assertTrue(all(s.rarity == "D" for s in new))
        self.assertEqual(len(self.stock.parts("flower")), 23)
        self.assertEqual(len(self.extras.parts("flower")), 37)
        self.assertEqual(len(self.extras.parts("foliage")), 23)
        self.assertEqual(self.extras.species_by_key((7, 25)).name, "Rosetta Fern")
        self.assertEqual(self.extras.species_by_key((7, 25)).value, 20 + 60)
        with self.assertRaises(KeyError):
            self.stock.children((1, 24), (1, 1))

    def test_interface(self) -> None:
        self.assertEqual(self.stock.game, "plant")
        s = self.stock.species_by_key((4, 4))
        self.assertEqual((s.name, s.rarity, s.value), ("Nox Orchid", "C", 95))
        self.assertEqual(tuple(p.kind for p in s.parts), ("foliage", "flower"))
        self.assertEqual(self.stock.species_by_key((9, 17)).name, "Citrus  Maranta")      # the exe's own two spaces
        self.assertEqual(self.stock.parts("flower")[16].name, "Citrus")
        self.assertEqual(self.stock.magic((11, 10)), "Fabled Rose of Isola")
        for text in self.stock.effects_max():
            self.assertIsInstance(text, str)

    def test_children_sum_to_one(self) -> None:
        for model, keys in ((self.stock, STOCK), (self.extras, STOCK + NEW)):
            rng = random.Random(5)
            for _ in range(3000):
                a, b = rng.choice(keys), rng.choice(keys)
                kids = model.children(a, b, "none")
                self.assertAlmostEqual(sum(p for _, p in kids), 1.0)
                self.assertEqual(kids, model.children(b, a, "max"))
                for key, _ in kids:
                    self.assertIn(key, set(keys))
            for key in keys[::7]:
                self.assertAlmostEqual(sum(p for _, p in model.mutations(key)), 1.0)

    def test_ways_to_breed(self) -> None:
        ways = self.stock.ways_to_breed((13, 13), "none")
        self.assertLessEqual(len(ways), 20)
        for a, b, odds in ways:
            self.assertIn(((13, 13), odds), self.stock.children(a, b))
        every = self.stock.ways_to_breed((13, 13), "none", limit=100000)
        self.assertIn(((9, 17), (17, 9), 1.0), every)                     # the two starting seeds
        self.assertEqual([o for _, _, o in every], sorted((o for _, _, o in every), reverse=True))
        for a, b, odds in self.extras.ways_to_breed((5, 30), "none"):
            self.assertIn(((5, 30), odds), self.extras.children(a, b))

    def assert_valid_chain(self, model, have, want, steps, effects) -> None:
        known = set(have)
        for step in steps:
            a, b = step["parents"]
            self.assertIn(a, known)
            self.assertIn(b, known)
            if step["via"] == "pollination":
                self.assertIn((step["child"], step["odds"]), model.children(a, b, effects))
            else:
                self.assertEqual(effects, "max")
                self.assertEqual(a, b)
                self.assertIn((step["child"], step["odds"]), model.mutations(a))
            known.add(step["child"])
        self.assertEqual(steps[-1]["child"], want)

    def test_plan_finds_valid_chains(self) -> None:
        cases = [
            (self.stock, [(9, 17), (17, 9)], (13, 13), "none", 1),           # the two starting seeds
            (self.stock, [(9, 9), (9, 13), (13, 9)], (11, 10), "none", 2),     # the Fabled Lemonbush, Common only
            (self.stock, [(5, 5), (3, 3)], (4, 4), "none", 1),                 # Flower of Knowledge
            (self.stock, [(10, 10)], (11, 10), "max", 1),                      # Mutation Liquid
            (self.extras, [(1, 1), (23, 37)], (12, 19), "none", None),
            (self.extras, [(5, 23)], (5, 24), "max", 1),                       # a Tilia steps up into flower 24
        ]
        for model, have, want, effects, length in cases:
            steps = model.plan(have, want, effects)
            self.assertTrue(steps, (have, want))
            self.assert_valid_chain(model, have, want, steps, effects)
            if length is not None:
                self.assertEqual(len(steps), length, steps)
        self.assertEqual(self.stock.plan([(1, 1), (5, 5)], (11, 10), "none"), [])     # never leaves 1..5
        self.assertEqual(self.stock.plan([(1, 1)], (1, 1), "none"), [])
        self.assertTrue(self.stock.plan([(1, 1), (5, 5)], (11, 10), "max"))

    def test_prices(self) -> None:
        for key in ((1, 1), (13, 13), (4, 4), (11, 10), (7, 11)):
            v = B.value(key)
            none, best = self.stock.prices(key, "none"), self.stock.prices(key, "max")
            self.assertEqual(none.highest_selling, 2 * v - 1)
            self.assertGreater(best.highest_selling, none.highest_selling)
            self.assertIsNotNone(B.sale_k(best.highest_selling, v, B.MAX_EFFECTS))
            self.assertIsNone(B.sale_k(best.highest_selling + 1, v, B.MAX_EFFECTS))
            for prices in (none, best):
                self.assertLessEqual(prices.best_per_day, prices.highest_selling)
                self.assertGreater(prices.best_per_day_income, 0)
                self.assertIn("Normal speed", prices.note)
        self.assertEqual(B.knowledge_price(95), 95 + 3 * 23)
        self.assertAlmostEqual(B.roll_chance(1299), 1.0)
        self.assertAlmostEqual(sum(B.roll_chance(t) - B.roll_chance(t - 1) for t in range(1300)), 1.0)


# ------------------------------------------------------------------ the game's code

def _random_hook(values):
    """Random(bound): the next of `values` (or 0), recording each bound."""
    bounds = []

    def handler(emu):
        bounds.append(emu.arg(0))
        return values.pop(0) if values else 0
    return handler, bounds


@needs_exe
class GameTablesTests(unittest.TestCase):
    def test_values_names_and_classes_are_the_games(self) -> None:
        emu = E.Emulator(PLANT_EXE, None, {})
        state = emu.alloc(0x63E64)
        emu.call(0x41D870, ecx=state)

        def sprintf(e):            # 0x41E550 only formats "%s"
            fmt = e.cstring(e.arg(1)).decode("latin-1")
            self.assertEqual(fmt, "%s")
            e.uc.mem_write(e.arg(0), e.cstring(e.arg(2)) + b"\0")
            return 0
        emu.hook(0x44F30B, sprintf)
        emu.call(0x41E550, ecx=state)
        for f, fl in STOCK:
            self.assertEqual(emu.read32(state + ((f + 0x1D) * 26 + fl) * 4, signed=True), B.value((f, fl)))
            self.assertEqual(emu.cstring(state + 0x540CC + (f * 26 + fl) * 96).decode("latin-1"),
                             B.species_name((f, fl)))

    def test_breeding_matches_the_pollination(self) -> None:
        rng = random.Random(11)
        pairs = [(a, b) for a in STOCK[::23] for b in STOCK[::19]] + [(rng.choice(STOCK), rng.choice(STOCK)) for _ in range(300)]
        model = B.load(None, False)
        emu = E.Emulator(PLANT_EXE, None, {})
        handler, _ = _random_hook([])
        emu.hook(RANDOM, handler)
        target, donor = emu.alloc(0x100), emu.alloc(0x100)
        for a, b in pairs:
            for at, (f, fl) in ((target, a), (donor, b)):
                emu.uc.mem_write(at, bytes(0x100))
                emu.write32(at + 0x4C, f)
                emu.write32(at + 0x50, fl)
            emu.call(0x4240A0, target, donor)
            child = (emu.read32(target + 0x64), emu.read32(target + 0x68))
            self.assertEqual(model.children(a, b, "none"), [(child, 1.0)], (a, b))

    def test_classes_are_the_pest_checks(self) -> None:
        """0x42CA80: Random(10000) < X infests; on Tap water at Normal X is 10, 20, 100, 200 by class A-D."""
        x_by_class = {"A": 10, "B": 20, "C": 100, "D": 200}
        emu = E.Emulator(PLANT_EXE, None, {})
        rolls: list[int] = []
        handler, bounds = _random_hook(rolls)
        emu.hook(RANDOM, handler)
        state, plant, obj = emu.alloc(0x63E64), emu.alloc(0x100), emu.alloc(0x20)
        emu.write32(state + 0x518, 1)                                        # Normal difficulty, Tap water
        emu.write32(obj + 8, plant)
        emu.write32(obj + 0xC, state)
        for key in STOCK + NEW:
            x = x_by_class[B.rarity(key)]
            for roll, infested in ((x - 1, 1), (x, 0)):
                emu.uc.mem_write(plant, bytes(0x100))
                emu.write32(plant + 0x4C, key[0])
                emu.write32(plant + 0x50, key[1])
                emu.write32(plant + 0x20, 500)                               # water
                rolls.append(roll)
                bounds.clear()
                emu.call(0x42CA80, ecx=obj)
                self.assertEqual(bounds, [10000])
                self.assertEqual(emu.read32(plant + 0x28), infested, key)

    def test_mutation_liquid(self) -> None:
        for key in [(1, 1), (23, 23), (1, 14), (12, 23), (23, 1), (13, 12), (7, 7)]:
            self.assertEqual(self.mutate(key, extras=False), B.mutation_steps(key, False))
        # Unused Flowers: its two immediates (flower_sites.h MUTATION_TOP / MUTATION_BOUNCE)
        for key in [(5, 23), (5, 37), (5, 36), (1, 24), (23, 30)]:
            self.assertEqual(self.mutate(key, extras=True), B.mutation_steps(key, True))

    def mutate(self, key, extras: bool, dll=None, symbols=None):
        results: dict = {}
        for first, second in ((0, 0), (0, 1), (1, 0), (1, 1)):
            emu = E.Emulator(PLANT_EXE, dll, symbols or {})
            if extras:              # the DLL's two immediates (flower_sites.h)
                emu.write8(0x42FACC + 2, 0x25)
                emu.write32(0x42FAD2 + 3, 0x24)
            handler, bounds = _random_hook([first, second])
            emu.hook(RANDOM, handler)
            state = emu.alloc(0x63E64)
            obj = emu.alloc(0x100)
            emu.write32(obj, state)
            emu.write32(obj + 8, emu.alloc(0x100))                          # pot 0's plant
            emu.write32(state + 0x21D4, key[0])
            emu.write32(state + 0x21D8, key[1])

            def stop(uc, address, size, data):
                if address in (0x42FB35, 0x42FBB4):
                    uc.emu_stop()
            emu.uc.hook_add(UC_HOOK_CODE, stop)
            emu.call(0x42FA80, 0, 0, ecx=obj)
            self.assertEqual(bounds, [2, 2])
            new = (emu.read32(state + 0x21D4, signed=True), emu.read32(state + 0x21D8, signed=True))
            results[new] = results.get(new, 0) + 0.25
        return sorted(results.items())


_BUY = None


def _buy_roll(v: int, asking: int, n: int, c: B.Condition, roll: int):
    """Run the nursery's buy roll 0x436BE0(n) with one plant for sale (spot 0): (sold, Random bounds)."""
    global _BUY
    if _BUY is None:
        emu = E.Emulator(PLANT_EXE, None, {})
        _BUY = (emu, emu.alloc(0x63E64), emu.alloc(0x1000), emu.heap_top)
    emu, state, scene, top = _BUY
    emu.hooks.clear()
    emu.heap_top = top
    emu.uc.mem_write(state, bytes(0x63E64))
    emu.uc.mem_write(scene, bytes(0x1000))
    emu.write32(scene + 0xA3C, state)
    f, fl = 5, 5
    emu.write32(state + 0x21D4, f)
    emu.write32(state + 0x21D8, fl)
    emu.write32(state + 0x21AC, c.health)
    emu.write32(state + 0x21B0, int(c.infested))
    emu.write32(state + ((f + 0x1D) * 26 + fl) * 4, v)
    emu.write32(state + ((f + 0x37) * 26 + fl) * 4, asking)
    emu.write8(state + 0x2183, int(c.golden_berries))
    emu.write8(state + 0x53F3F, int(c.tutorial_first_sale))
    plant = 0x5000
    emu.hook(0x42F8B0, lambda e: int(e.arg(0) == 0 and e.arg(1) == 0), 8)     # spot (row, column) holds a plant
    emu.hook(0x42F6C0, lambda e: plant, 8)
    emu.hook(0x42DDE0, lambda e: int(c.over_pruned))
    emu.hook(0x42DE50, lambda e: int(c.cut_parts_2 or c.over_pruned))
    emu.hook(0x42DEA0, lambda e: int(c.dead_foliage))
    emu.hook(0x42D570, lambda e: c.flowers)
    emu.hook(0x42D650, lambda e: c.plant_food)
    emu.hook(0x43ACD0, lambda e: n)
    handler, bounds = _random_hook([roll])
    emu.hook(RANDOM, handler)
    sold = []
    emu.hook(0x435C70, lambda e: sold.append(1) or 0, 16)
    emu.call(0x436BE0, n, ecx=scene, esi=scene)
    return bool(sold), bounds


@needs_exe
class BuyRollTests(unittest.TestCase):
    CONDITIONS = (
        B.NO_EFFECTS, B.MAX_EFFECTS,
        B.Condition(infested=True), B.Condition(dead_foliage=True), B.Condition(health=10),
        B.Condition(flowers=0), B.Condition(over_pruned=True), B.Condition(plant_food=1),
        B.Condition(tutorial_first_sale=True), B.Condition(golden_berries=True),
        B.Condition(infested=True, golden_berries=True, plant_food=2, dead_foliage=True),
    )

    def check(self, v: int, asking: int, n: int, c: B.Condition) -> None:
        k = B.sale_k(asking, v, c)
        if k is None or n <= 0:
            sold, bounds = _buy_roll(v, asking, n, c, 0)
            self.assertFalse(sold, (v, asking, n, c))
            self.assertEqual(bounds, [])
            self.assertEqual(B.sale_chance(asking, v, n, c), 0.0)
            return
        threshold = k * (n // 2)
        sold, bounds = _buy_roll(v, asking, n, c, threshold)
        self.assertEqual(bounds, [1300])
        self.assertTrue(sold, (v, asking, n, c))
        sold, _ = _buy_roll(v, asking, n, c, threshold + 1)
        self.assertEqual(sold, threshold + 1 > 1299, (v, asking, n, c))
        self.assertAlmostEqual(B.sale_chance(asking, v, n, c), B.roll_chance(threshold))

    def test_the_sale_odds_are_the_games(self) -> None:
        for v in (7, 44, 95, 250):
            prices = sorted({1, v // 2, v - v // 2, v - v // 2 + 1, v - 1, v, v + v // 2, v + v // 2 + 1,
                             2 * v - 1, 2 * v, 3 * v - 1, 3 * v})
            for asking in prices:
                for n in (0, 1, 9, 55):
                    self.check(v, asking, n, B.NO_EFFECTS)
                for c in self.CONDITIONS[1:]:
                    self.check(v, asking, 9, c)

    def test_highest_selling_is_the_games(self) -> None:
        model = B.load(None, False)
        for key in ((13, 13), (11, 10)):
            v = B.value(key)
            for effects, c in (("none", B.NO_EFFECTS), ("max", B.MAX_EFFECTS)):
                top = model.prices(key, effects).highest_selling
                self.assertTrue(_buy_roll(v, top, 55, c, 0)[0])
                self.assertFalse(_buy_roll(v, top + 1, 55, c, 0)[0])

    def test_the_visitor_limit(self) -> None:
        emu = E.Emulator(PLANT_EXE, None, {})
        table = struct.unpack("<15I", bytes(emu.uc.mem_read(0x440020, 60)))
        self.assertEqual(sorted(table).count(0x43FF31), 10)                 # ten +1 ornaments
        self.assertEqual(sorted(table).count(0x43FF36), 5)                  # five +4
        for ornaments, for_sale, magic, bugs, expected_score in (
                (0, 1, 0, 0, 2), (15, 15, 6, 48, 78), (0, 15, 0, 47, 30), (15, 0, 1, 0, 34), (15, 0, 2, 0, 36)):
            emu = E.Emulator(PLANT_EXE, None, {})
            scene, state = emu.alloc(0x170000), emu.alloc(0x63E64)
            emu.write32(scene + 0x16F95C, state)
            for i in range(ornaments):
                emu.write32(scene + 0x16F6B0 + 4 * i, 0x18 + i)
            for i in range(for_sale):
                emu.write32(scene + 0x16F670 + 4 * i, i + 1)
            for flag in (0x2182, 0x2180, 0x2183, 0x2181, 0x2184, 0x2185)[:magic]:
                emu.write8(state + flag, 1)
            emu.hook(0x43FC00, lambda e: 0)
            emu.hook(0x43FBA0, lambda e: 0)
            emu.hook(0x417C50, lambda e: 0)
            emu.hook(0x417350, lambda e, bugs=bugs: bugs)
            limit = emu.call(0x43FF00, ecx=scene)
            self.assertEqual(limit, B.visitor_limit(expected_score))
        self.assertEqual((B.visitor_limit(2), B.visitor_limit(78)), (9, 55))


# ------------------------------------------------------------------ Unused Flowers (the DLL)

@needs_dll
class NewFlowersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_new_flowers", FLOWERS_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def emulator(self):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.call(emu.sym("_build_tables"))
        return emu

    def test_the_new_species_values_and_names(self) -> None:
        emu = self.emulator()
        for f, fl in NEW:
            k = fl - 24
            self.assertEqual(emu.read32(emu.sym("_value") + (f * 14 + k) * 4, signed=True), B.value((f, fl)))
            self.assertEqual(emu.cstring(emu.sym("_names") + (f * 14 + k) * 0x60).decode("latin-1"),
                             B.species_name((f, fl)))

    def test_breeding_with_a_new_flower(self) -> None:
        model = B.load(None, True)
        rng = random.Random(3)
        pairs = [((5, 24), (5, 25)), ((1, 23), (3, 24)), ((23, 37), (1, 1)), ((9, 30), (9, 30)), ((2, 2), (3, 3))]
        pairs += [(rng.choice(STOCK + NEW), rng.choice(NEW)) for _ in range(60)]
        pairs += [(rng.choice(STOCK), rng.choice(STOCK)) for _ in range(20)]
        emu = self.emulator()
        emu.uc.mem_write(0x4241B4, b"\xE9" + struct.pack("<i", emu.sym("_stub_pollinated") - (0x4241B4 + 5)))
        rolls: list[int] = []
        handler, bounds = _random_hook(rolls)
        emu.hook(RANDOM, handler)
        target, donor = emu.alloc(0x100), emu.alloc(0x100)
        for a, b in pairs:
            outcomes: dict = {}
            for roll in (0, 1):
                rolls[:] = [0, roll]                                        # Random(3) seeds, then the DLL's Random(2)
                bounds.clear()
                for at, (f, fl) in ((target, a), (donor, b)):
                    emu.uc.mem_write(at, bytes(0x100))
                    emu.write32(at + 0x4C, f)
                    emu.write32(at + 0x50, fl)
                emu.call(0x4240A0, target, donor)
                child = (emu.read32(target + 0x64), emu.read32(target + 0x68))
                random_flower = (a[1] >= 24 or b[1] >= 24) and (a[1] + b[1]) % 2 == 1
                self.assertEqual(bounds, [3, 2] if random_flower else [3], (a, b))
                outcomes[child] = outcomes.get(child, 0) + 0.5               # Random(2) is 0 or 1, 50% each
            self.assertEqual(sorted(outcomes.items()), model.children(a, b, "none"), (a, b))


# ------------------------------------------------------------------ discovered, from saves the game writes

def _write_game_save(folder: Path, slot: int, discovered: list[tuple[int, int]]) -> None:
    """The game's own new game (0x41EF30, as far as its flag clear), its own "discovered at age 24"
    instructions (0x42E2BB) for each species, then its own save (0x41D120) through its file writer
    (0x403690), with only the C runtime's file calls answered in Python."""
    emu = E.Emulator(PLANT_EXE, None, {})
    rng = random.Random(7)
    emu.hook(RANDOM, lambda e: rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0)
    emu.hook(CLOCK, lambda e: 1000)

    def memset(e):
        e.uc.mem_write(e.arg(0), bytes([e.arg(1) & 0xFF]) * e.arg(2))
        return e.arg(0)
    emu.hook(MEMSET, memset)
    state = emu.alloc(0x63E64)
    esp = E.STACK + E.STACK_SIZE - 0x1000
    emu.write32(esp, E.RETURN)
    emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
    emu.uc.reg_write(X.UC_X86_REG_ECX, state)
    emu.uc.emu_start(0x41EF30, 0x41F17D, count=20_000_000)
    holder = emu.alloc(0x20)
    emu.write32(holder + 0xC, state)
    for f, fl in discovered:
        emu.uc.reg_write(X.UC_X86_REG_ECX, f)
        emu.uc.reg_write(X.UC_X86_REG_EAX, fl)
        emu.uc.reg_write(X.UC_X86_REG_ESI, holder)
        emu.uc.emu_start(0x42E2BB, 0x42E2C9)
    vtable, path_thunk = emu.alloc(0x40), emu.thunk()
    emu.write32(state, vtable)
    emu.write32(vtable + 0xC, path_thunk)
    emu.hook(path_thunk, lambda e: e.text("save.ldw"), 4)
    written = bytearray()

    def fwrite(e):
        written.extend(bytes(e.uc.mem_read(e.arg(0), e.arg(1) * e.arg(2))))
        return e.arg(2)
    for address, handler in ((0x403650, lambda e: 0), (0x4500F0, lambda e: 0), (0x4500BD, lambda e: 0),
                             (0x44FADC, lambda e: 0x7000), (0x45003B, fwrite), (0x44F99C, lambda e: 0)):
        emu.hook(address, handler, 4 if address == 0x403650 else 0)
    emu.call(0x41D120, slot, ecx=state)
    (folder / f"Plant Tycoon{slot}.ldw").write_bytes(bytes(written))


@needs_exe
class DiscoveredTests(unittest.TestCase):
    def test_discovered_reads_the_games_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _write_game_save(folder, 1, [])
            found = [(13, 13), (4, 4), (1, 23), (23, 1), (11, 10)]
            _write_game_save(folder, 3, found)
            data = (folder / "Plant Tycoon3.ldw").read_bytes()
            self.assertEqual(len(data), 344008)
            self.assertEqual(data[:4], b"ldwg")
            model = B.load(None, False)
            self.assertEqual(model.discovered(folder, 1), set())
            before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in folder.iterdir()}
            self.assertEqual(model.discovered(folder, 3), set(found))
            self.assertEqual(B.load(None, True).discovered(folder, 3), set(found))     # no sidecar: stock only
            # Unused Flowers' sidecar (ftfp_new_flowers.c: magic, version, size, price[24][14], discovered[24][14])
            side = folder / "Plant Tycoon Fix Patcher Data"
            side.mkdir()
            flags = bytearray(24 * 14)
            flags[5 * 14 + (30 - 24)] = 1
            flags[23 * 14 + (37 - 24)] = 1
            body = bytes(24 * 14 * 4) + bytes(flags)
            (side / "New Flowers 3.dat").write_bytes(struct.pack("<3I", 0x574C4650, 1, len(body)) + body)
            self.assertEqual(B.load(None, True).discovered(folder, 3), set(found) | {(5, 30), (23, 37)})
            self.assertEqual(model.discovered(folder, 3), set(found))
            for p, (mtime, raw) in before.items():
                self.assertEqual((p.stat().st_mtime_ns, p.read_bytes()), (mtime, raw))

    def test_the_sidecar_layout_is_the_dlls(self) -> None:
        source = (ROOT / "native" / "ftfp_new_flowers" / "ftfp_new_flowers.c").read_text(encoding="utf-8")
        for text in ("#define SIDECAR_MAGIC 0x574C4650u", "#define SIDECAR_VERSION 1u",
                     "int price[FOLIAGE_ROWS][NEW_COUNT];\n    unsigned char discovered[FOLIAGE_ROWS][NEW_COUNT];",
                     "#define FOLIAGE_ROWS 24", "#define NEW_COUNT 14", "L\"\\\\New Flowers \""):
            self.assertIn(text, source)


if __name__ == "__main__":
    unittest.main()
