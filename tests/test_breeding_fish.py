"""The Breeding Guide's Fish Tycoon model (src/breeding_fish.py), checked against the game.

* EmulatedTests run the vanilla executable's own code in Unicorn
  (tests/store_emulator.py) and compare it with the model: the base price
  table and names (0x418B10, 0x419600), the Advertising price rises
  (0x420A82, 0x420AE6), the baby's genes (0x41FAAB), the Magic Fish of
  Mutation's step at a birth (0x42014C-0x420263, every Random outcome
  weighted by its exact count), the sale odds (0x424240) and the game's own
  "species discovered" count (0x419240) on a save. They skip when the
  executable or Unicorn is missing.
* DsRulesTests check the DS species against the DS Fish DLL's own source
  (native/ftfp_ds_fish/ds_data.h, and the logic harness output when built).
* ModelTests: probabilities sum to 1, ways to breed and plans are valid, the
  prices follow the selling model, and a save's discovered species are read
  from small synthetic saves (no owner data), never written.
"""

from __future__ import annotations

import os
from pathlib import Path
import random
import re
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_fish as bf  # noqa: E402

VANILLA = Path(os.environ.get(
    "FISH_TYCOON_VANILLA",
    str(Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Fish Tycoon")))
EXE = VANILLA / "Fish Tycoon.exe"
RANDOM = 0x00403240
HARNESS_OUTPUT = ROOT / "build" / "ftfp_ds_fish" / "logic.txt"


def _emulator():
    try:
        from store_emulator import Emulator
    except ImportError:
        return None
    return Emulator(EXE, None, {})


def unicorn_ready() -> bool:
    try:
        import unicorn  # noqa: F401
    except ImportError:
        return False
    return EXE.is_file()


# ---------------------------------------------------------------- fixtures

def make_save(folder: Path, slot: int, discovered: dict[tuple[int, int], int], *, ds_columns: bool = False,
              name: str = "Tester") -> Path:
    """A Fish Tycoon save with the stock layout: every species named and priced as a new game
    makes it (-1 = undiscovered), `discovered` set to their asking prices."""
    state = bytearray(bf.STATE_SIZE)
    table = bf.SPECIES_BASE - 8
    fins = bf.PC_GENES + (bf.DS_GENES if ds_columns else ())
    for body in bf.PC_GENES:
        for fin in fins:
            at = table + (body * bf.ROW_STRIDE + fin) * bf.ENTRY_SIZE
            text = bf.species_name(body, fin).encode("latin-1")
            state[at: at + len(text)] = text
            price = discovered.get((body, fin), -1)
            struct.pack_into("<ii", state, at + bf.ENTRY_PRICE, price, bf.base_price(body, fin))
    state[0x1E3B5 - 0x18: 0x1E3B5 - 0x18 + len(name)] = name.encode("ascii")
    path = folder / f"Fish Tycoon{slot}.ldw"
    path.write_bytes(b"ldwg" + bytes(20) + bytes(state))
    return path


def make_settings(folder: Path, names: list[str]) -> None:
    data = bytearray(256)
    data[:4] = b"ldwg"
    for i, n in enumerate(names):
        data[0x20 + i * 42: 0x20 + i * 42 + len(n)] = n.encode("ascii")
    (folder / "Fish Tycoon0.ldw").write_bytes(bytes(data))


def make_sidecar(folder: Path, slot: int, discovered: dict[tuple[int, int], int]) -> Path:
    rows = bytearray(bf.DS_ROWS_BYTES)
    for body in bf.DS_GENES:
        for fin in bf.PC_GENES + bf.DS_GENES:
            at = ((body - bf.DS_FIRST) * bf.ROW_STRIDE + fin) * bf.ENTRY_SIZE
            text = bf.species_name(body, fin).encode("latin-1")
            rows[at: at + len(text)] = text
            struct.pack_into("<ii", rows, at + bf.ENTRY_PRICE, discovered.get((body, fin), -1),
                             bf.base_price(body, fin))
    data_folder = folder / bf.SIDECAR_FOLDER
    data_folder.mkdir(exist_ok=True)
    path = data_folder / f"DS Fish {slot}.dat"
    path.write_bytes(struct.pack("<3I", bf.SIDECAR_MAGIC, bf.SIDECAR_VERSION, bf.DS_ROWS_BYTES) + bytes(rows))
    return path


# ---------------------------------------------------------------- the executable

@unittest.skipUnless(unicorn_ready(), "the vanilla Fish Tycoon.exe and Unicorn are needed to emulate it")
class EmulatedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.emu = _emulator()

    def _new_state(self) -> int:
        state = self.emu.alloc(0x1E510)
        self.emu.call(0x418B10, ecx=state)
        self.emu.call(0x419600, ecx=state)
        return state

    def _entry(self, state: int, body: int, fin: int) -> int:
        return state + bf.SPECIES_BASE + (body * bf.ROW_STRIDE + fin) * bf.ENTRY_SIZE

    def test_base_prices_and_names(self) -> None:
        state = self._new_state()
        for body in bf.PC_GENES:
            for fin in bf.PC_GENES:
                at = self._entry(state, body, fin)
                price, base = struct.unpack("<ii", self.emu.uc.mem_read(at + 0x20, 8))
                self.assertEqual(price, -1, "a new game knows no species")
                self.assertEqual(base, bf.BASE_PRICES[body][fin], (body, fin))
                self.assertEqual(self.emu.cstring(at).decode("latin-1"), bf.species_name(body, fin))

    def _run(self, start: int, stop: int, **registers) -> None:
        from unicorn import x86_const as X
        esp = 0x0F000000 + 0x00100000 - 0x2000
        self.emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        for name, value in registers.items():
            self.emu.uc.reg_write(getattr(X, f"UC_X86_REG_{name.upper()}"), value & 0xFFFFFFFF)
        self.emu.uc.emu_start(start, stop, count=2_000_000)

    def test_advertising_rises(self) -> None:
        state = self._new_state()
        holder = self.emu.alloc(0x40)
        self.emu.write32(holder + 0x34, state)
        samples = [(b, f) for b in bf.PC_GENES for f in bf.PC_GENES]
        before = {k: struct.unpack("<i", self.emu.uc.mem_read(self._entry(state, *k) + 0x24, 4))[0] for k in samples}
        self._run(0x420AE6, 0x420B42, esi=holder)                  # level 2 finished: B / 10
        for k in samples:
            got = struct.unpack("<i", self.emu.uc.mem_read(self._entry(state, *k) + 0x24, 4))[0]
            self.assertEqual(got, bf.advertised(before[k], 2), k)
        self._run(0x420A82, 0x420B42, esi=holder, eax=0)           # level 3 finished: B / 7
        for k in samples:
            got = struct.unpack("<i", self.emu.uc.mem_read(self._entry(state, *k) + 0x24, 4))[0]
            self.assertEqual(got, bf.advertised(before[k], 3), k)

    def test_baby_genes(self) -> None:
        from unicorn import x86_const as X
        model = bf.load(None, False)
        for a in bf.PC_GENES:
            for b in bf.PC_GENES:
                esp = 0x0F000000 + 0x00100000 - 0x2000
                self.emu.write32(esp + 0x2A8, b)
                self._run(0x41FAAB, 0x41FAC8, edi=a, ebx=b, ebp=a, ecx=0)
                body = self.emu.uc.reg_read(X.UC_X86_REG_ECX)
                fin = self.emu.uc.reg_read(X.UC_X86_REG_EAX)
                expected = model._gene_child(a, b)[0]
                self.assertEqual((body, fin), (expected, expected), (a, b))

    def test_mutation_fish_step(self) -> None:
        """Every path through the birth-time step, weighted by the exact counts of the Random
        values that take it, against the model's father distribution (stock game)."""
        model = bf.load(None, False)
        state = self.emu.alloc(0x1000)
        holder = self.emu.alloc(0x40)
        self.emu.write32(holder + 0x34, state)
        script: list[int] = []

        def random_hook(emu) -> int:
            return script.pop(0) if script else 0

        self.emu.hook(RANDOM, random_hook, 0)
        self.emu.hook(0x0041DE90, lambda emu: 1, 8)                 # a Wasp Grouper is in the tank
        weight = {0: bf.chance_at_most(100, 15), 16: 1 - bf.chance_at_most(100, 15)}
        half = {0: bf.chance_at_most(100, 49), 50: 1 - bf.chance_at_most(100, 49)}
        for fb in bf.PC_GENES:
            for ff in bf.PC_GENES:
                got: dict[tuple[int, int], float] = {}
                for r1 in (0, 16):
                    for r2 in ((0, 50) if r1 == 0 else (None,)):
                        for r3 in ((0, 50) if r1 == 0 else (None,)):
                            script[:] = [r for r in (r1, r2, r3) if r is not None]
                            self.emu.write32(state + 0x3A4, fb)
                            self.emu.write32(state + 0x3A8, ff)
                            self._run(0x42014C, 0x420263, esi=holder, edi=0, ebx=0)
                            # a roll the code does not make (a gene at an end) leaves both of
                            # its halves with the same result, so weighting it still sums to 1
                            p = weight[r1] * (half[r2] * half[r3] if r1 == 0 else 1.0)
                            key = (self.emu.read32(state + 0x3A4), self.emu.read32(state + 0x3A8))
                            if p > 0:
                                got[key] = got.get(key, 0.0) + p
                expected = dict(model._father_variants((fb, ff), "max_mutation"))
                self.assertEqual(set(got), set(expected), (fb, ff))
                for key, p in expected.items():
                    self.assertAlmostEqual(got[key], p, places=12, msg=(fb, ff, key))

    def _sells(self, price: int, base: int, browsing: int, roll: int, sick: bool = False,
               sick_roll: int = 0) -> bool:
        if not hasattr(self, "_sale_state"):
            self._sale_state, self._sale_this = self.emu.alloc(0x1E510), self.emu.alloc(0x100)
        state, this = self._sale_state, self._sale_this
        self.emu.write32(this + 0x70, state)
        fish = state + 0xA768
        self.emu.write32(fish + 0x00, 1)
        self.emu.write32(fish + 0x3C, 100)          # health
        self.emu.write32(fish + 0x0C, 25)           # adult
        self.emu.write32(fish + 0x4C, 3)            # body
        self.emu.write32(fish + 0x50, 4)            # fin
        self.emu.write32(fish + 0x40, 1 if sick else 0)
        entry = state + bf.SPECIES_BASE + (3 * bf.ROW_STRIDE + 4) * bf.ENTRY_SIZE
        self.emu.write32(entry + 0x20, price)
        self.emu.write32(entry + 0x24, base)
        rolls = [roll, sick_roll]
        sold: list[int] = []
        self.emu.hook(RANDOM, lambda emu: rolls.pop(0), 0)
        self.emu.hook(0x00424010, lambda emu: sold.append(emu.arg(0)) or 0, 4)
        self.emu.call(0x00424240, browsing, ecx=this)
        return bool(sold)

    def test_sale_odds(self) -> None:
        for base in (4, 13, 48, 190):
            prices = sorted({0, 1, base // 2 - 1, base // 2, base - base // 2, base - 1, base, base + base // 2,
                             base + base // 2 + 1, 2 * base - 1, 2 * base, 2 * base + 5})
            for price in [p for p in prices if p >= 0]:
                for browsing in (0, 1, 2, 7, 66, 72):
                    expected = bf.sale_threshold(price, base, browsing)
                    lo, hi = -1, 899                                  # largest roll that sells
                    while lo < hi:
                        mid = (lo + hi + 1) // 2
                        if self._sells(price, base, browsing, mid):
                            lo = mid
                        else:
                            hi = mid - 1
                    got = None if lo < 0 else lo
                    if expected is not None and expected >= 899:
                        self.assertEqual(got, 899, (price, base, browsing))
                    else:
                        self.assertEqual(got, expected, (price, base, browsing))

    def test_sick_fish_needs_the_extra_roll(self) -> None:
        self.assertTrue(self._sells(10, 20, 0, 0, sick=True, sick_roll=20))
        self.assertFalse(self._sells(10, 20, 0, 0, sick=True, sick_roll=21))
        self.assertFalse(self._sells(10, 20, 0, 2, sick=True, sick_roll=0))    # T = K = 1

    def test_discovered_count_on_a_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rng = random.Random(7)
            picked = {(rng.randrange(21), rng.randrange(21)): rng.randrange(1, 400) for _ in range(60)}
            path = make_save(Path(tmp), 2, picked)
            self._check_count(path, 2, len(picked))

    @unittest.skipUnless(os.environ.get("FISH_TYCOON_SAVE_COPIES"), "set FISH_TYCOON_SAVE_COPIES to a folder of save copies")
    def test_discovered_count_on_save_copies(self) -> None:
        root = Path(os.environ["FISH_TYCOON_SAVE_COPIES"])
        checked = 0
        for path in sorted(root.rglob("Fish Tycoon*.ldw")):
            match = re.fullmatch(r"Fish Tycoon([1-5])\.ldw", path.name)
            if not match or "Backups" in path.parts or path.stat().st_size < 0x1E3E0:
                continue
            found = bf.read_discovered(path.parent, int(match.group(1)), extras=False)
            self._check_count(path, int(match.group(1)), len(found))
            checked += 1
        self.assertGreater(checked, 0)

    # ---- how each part is obtained, pinned to the game's code
    def _random(self, values: dict | None = None, script: list | None = None, bounds: list | None = None):
        def handler(emu) -> int:
            n = emu.arg(0)
            if bounds is not None:
                bounds.append(n)
            if script:
                return script.pop(0)
            return min(values.get(n, 0), n - 1) if values is not None else 0
        self.emu.hook(RANDOM, handler, 0)

    def test_store_eggs_are_the_games(self) -> None:
        """Each egg's hatch code (0x4213D1 / 0x4214A0 / 0x421573): Random(2) + 3 babies, each
        body and fin Random(n) x mul + add, exactly STORE_EGGS; and so each part's "how"."""
        babies: list[tuple[int, int]] = []
        self.emu.hook(0x41FA30, lambda emu: babies.append((emu.arg(0), emu.arg(1))) or 0, 56)
        stock, ds = bf.load(None, False), bf.load(None, True)
        for name, price, n, mul, add in bf.STORE_EGGS:
            start, stop = bf.EGG_ADDRESSES[name]
            got: dict[int, int] = {}
            for r in range(n):
                state, holder = self.emu.alloc(0x1E510), self.emu.alloc(0x40)
                self.emu.write32(holder + 0x34, state)
                self.emu.write32(state + 0x14, 1)                  # not Easy: no extra baby
                bounds: list[int] = []
                self._random(script=[0] + [r] * 6, bounds=bounds)
                babies.clear()
                self._run(start, stop, esi=holder, ebp=0)
                self.assertEqual(bounds, [2] + [n] * 6, name)      # 3 babies, two rolls each
                self.assertEqual(babies, [(r * mul + add, r * mul + add)] * 3, (name, r))
                got[r * mul + add] = r
            for model in (stock, ds):
                for kind in ("body", "fin"):
                    for part in model.parts(kind):
                        chance = bf.egg_chance(n, mul, add, part.index)
                        self.assertEqual(chance > 0, part.index in got, (name, part.index))
                        if chance > 0:
                            self.assertAlmostEqual(chance, bf.random_is(n, got[part.index]))
                            self.assertIn(f"{name} (${price}), {100 * chance:.2f}% of the babies", part.how)
                        else:
                            self.assertNotIn(name, part.how)

    def test_store_prices_are_the_games(self) -> None:
        """The new-game store table (0x419A43..): mov dword [ecx + item], price."""
        sites = {0x419A7E: (0xC4, bf.UNKNOWN_CHEMICAL_PRICE), 0x419A88: (0xD8, 120),
                 0x419A92: (0xEC, 450), 0x419A9C: (0x100, 1200)}
        for address, (field, price) in sites.items():
            code = bytes(self.emu.uc.mem_read(address, 10))
            self.assertEqual(code[:2], b"\xC7\x81", hex(address))
            self.assertEqual(struct.unpack_from("<II", code, 2), (field, price), hex(address))
        self.assertEqual([p for _n, p, *_r in bf.STORE_EGGS], [120, 450, 1200])

    def test_starter_eggs_are_the_games(self) -> None:
        """0x41FC90 in a new game (the tanks empty): 7 babies, each with the bodies and fins of
        STARTER_BABIES, over every Random value."""
        babies: list[tuple[int, int]] = []
        self.emu.hook(0x41FA30, lambda emu: babies.append((emu.arg(0), emu.arg(1))) or 0, 56)
        seen: list[tuple[set, set]] = [(set(), set()) for _ in range(7)]
        for r in range(6):
            state, holder = self.emu.alloc(0x1E510), self.emu.alloc(0x40)
            self.emu.write32(holder + 0x34, state)
            self._random(values={5: r, 6: r})
            babies.clear()
            self.emu.call(0x41FC90, ecx=holder)
            self.assertEqual(len(babies), 7)
            for i, (body, fin) in enumerate(babies):
                seen[i][0].add(body)
                seen[i][1].add(fin)
        self.assertEqual(seen, [(set(b), set(f)) for b, f in bf.STARTER_BABIES])
        model = bf.load(None, False)
        for kind in ("body", "fin"):
            for part in model.parts(kind):
                given = any(part.index in s[0 if kind == "body" else 1] for s in seen)
                self.assertEqual("starter eggs" in part.how, given, (kind, part.index))

    def test_unknown_chemical_is_the_games(self) -> None:
        """The Unknown Chemical's loop (0x420E93-0x42104F) on one live fish, every Random path
        weighted by its exact count, against P_CHEMICAL, P_BODY and chemical_steps()."""
        self.emu.hook(0x415DF0, lambda emu: 0, 12)
        weight = {25: bf.P_CHEMICAL, 26: 1 - bf.P_CHEMICAL}
        half = {49: bf.P_BODY, 50: 1 - bf.P_BODY}
        cases = [(b, 5) for b in bf.PC_GENES] + [(5, f) for f in bf.PC_GENES] + [(0, 20), (20, 0), (20, 20), (0, 0)]
        state, holder = self.emu.alloc(0x1E510), self.emu.alloc(0x40)       # reused: the heap is small
        self.emu.write32(holder + 0x34, state)
        for body, fin in cases:
            got: dict[tuple[int, int], float] = {}
            for r1 in (25, 26):
                for r2 in ((49, 50) if r1 == 25 else (None,)):
                    for r3 in ((49, 50) if r1 == 25 else (None,)):
                        self.emu.uc.mem_write(state, bytes(0x1E510))
                        fish = state + 0x390
                        self.emu.write32(fish, 1)
                        self.emu.write32(fish + 0x3C, 100)
                        self.emu.write32(fish + 0x4C, body)
                        self.emu.write32(fish + 0x50, fin)
                        self._random(script=[r for r in (r1, r2, r3) if r is not None])
                        self._run(0x420E93, 0x42104F, esi=holder, eax=0)
                        p = weight[r1] * (half[r2] * half[r3] if r1 == 25 else 1.0)
                        key = (self.emu.read32(fish + 0x4C), self.emu.read32(fish + 0x50))
                        got[key] = got.get(key, 0.0) + p
            expected: dict[tuple[int, int], float] = {(body, fin): 1 - bf.P_CHEMICAL}
            for new, q in bf.chemical_steps(body, False):
                expected[(new, fin)] = expected.get((new, fin), 0.0) + bf.P_CHEMICAL * bf.P_BODY * q
            for new, q in bf.chemical_steps(fin, False):
                expected[(body, new)] = expected.get((body, new), 0.0) + bf.P_CHEMICAL * (1 - bf.P_BODY) * q
            self.assertEqual(set(got), set(expected), (body, fin))
            for key, p in expected.items():
                self.assertAlmostEqual(got[key], p, places=12, msg=(body, fin, key))

    def test_tier_words_are_the_exes(self) -> None:
        """Each rarity word is the exe's own word for those genes (TIER_STRINGS)."""
        for tier, (address, text) in bf.TIER_STRINGS.items():
            self.assertEqual(self.emu.cstring(address).decode("latin-1"), text, hex(address))
            if tier != 2:                   # the middle one is the owner's "Uncommon" (the eggs say "Unusual")
                self.assertIn(bf.TIER_NAMES[tier].casefold(), text.casefold().split())
        self.assertEqual(bf.TIER_NAMES, {1: "Common", 2: "Uncommon", 3: "Rare"})
        model = bf.load(None, False)
        self.assertEqual({model.part_rarity(p) for p in model.parts("fin") if p.index % 4 == 0}, {"Common"})
        self.assertEqual({model.part_rarity(p) for p in model.parts("fin") if p.index % 4 == 2}, {"Uncommon"})
        self.assertEqual({model.part_rarity(p) for p in model.parts("fin") if p.index % 2}, {"Rare"})

    def _check_count(self, path: Path, slot: int, expected: int) -> None:
        data = path.read_bytes()
        state = self.emu.alloc(0x1E510)
        self.emu.uc.mem_write(state + 8, data[0x18:0x18 + bf.STATE_SIZE])
        count = self.emu.call(0x00419240, ecx=state)
        self.assertEqual(count, expected, path.name)
        self.assertEqual(len(bf.read_discovered(path.parent, slot, extras=False)), expected)


# ---------------------------------------------------------------- the DS Fish DLL

class DsRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.header = (ROOT / "native" / "ftfp_ds_fish" / "ds_data.h").read_text(encoding="utf-8")
        self.model = bf.load(None, True)

    def _array(self, name: str) -> list[str]:
        match = re.search(rf"{name}\[\d+\]\s*=\s*\{{(.*?)\}};", self.header, re.S)
        self.assertIsNotNone(match, name)
        return [item.strip() for item in match.group(1).split(",") if item.strip()]

    def test_values_and_names_are_the_dlls(self) -> None:
        self.assertEqual(tuple(int(v) for v in self._array("DS_BODY_VALUE")), bf.DS_BODY_VALUE)
        self.assertEqual(tuple(int(v) for v in self._array("DS_FIN_VALUE")), bf.DS_FIN_VALUE)
        self.assertEqual(tuple(v.strip('"') for v in self._array("DS_BODY_NAME")), bf.BODY_NAMES)
        self.assertEqual(tuple(v.strip('"').rstrip() for v in self._array("DS_FIN_NAME")), bf.FIN_NAMES)

    def test_ds_species(self) -> None:
        self.assertEqual(len(self.model.species()), 28 * 28)
        self.assertEqual(sum(s.patcher for s in self.model.species()), 28 * 28 - 21 * 21)
        self.assertEqual(self.model.get((29, 29)).name, "Moorish Idle")
        self.assertEqual(self.model.get((29, 29)).value, 42)
        self.assertEqual(self.model.get((23, 20)).name, "Twin-Fin Clownfish")
        self.assertEqual(self.model.get((0, 23)).name, "Small-Fin Shark")
        self.assertEqual(self.model.get((3, 26)).value, bf.DS_BODY_VALUE[3] + bf.DS_FIN_VALUE[24])
        self.assertEqual(bf.load(None, False).get((7, 7)).value, 190)

    def test_ds_breeding_rule(self) -> None:
        for a in self.model.genes:
            for b in self.model.genes:
                lo, hi, coin = self.model._gene_child(a, b)
                if not bf.is_ds(a) and not bf.is_ds(b):
                    self.assertEqual((lo, hi, coin), ((a + b) // 2, (a + b) // 2, False))
                else:
                    s = bf.ds_index(a) + bf.ds_index(b)
                    self.assertEqual(lo, bf.exe_gene(s // 2))
                    self.assertEqual(hi, bf.exe_gene(s // 2 + s % 2))
                    self.assertEqual(coin, bool(s % 2))
                    self.assertFalse(lo in (21, 22) or hi in (21, 22))

    def test_body_and_fin_share_the_rounding_roll(self) -> None:
        children = dict(self.model.children((23, 23), (24, 24), "none"))      # DS 21 + 22: odd, both
        self.assertEqual(children, {(23, 23): 0.5, (24, 24): 0.5})
        children = dict(self.model.children((23, 0), (24, 4), "none"))        # odd body, PC fin
        self.assertEqual(children, {(23, 2): 0.5, (24, 2): 0.5})

    def test_mutation_step_with_ds(self) -> None:
        variants = dict(self.model._father_variants((20, 29), "max_mutation"))
        self.assertAlmostEqual(variants[(23, 29)], bf.P_MUTATE * bf.P_BODY * bf.P_UP)
        self.assertAlmostEqual(variants[(19, 29)], bf.P_MUTATE * bf.P_BODY * (1 - bf.P_UP))
        self.assertAlmostEqual(variants[(20, 28)], bf.P_MUTATE * (1 - bf.P_BODY))     # 29 always steps down
        stock = dict(bf.load(None, False)._father_variants((20, 5), "max_mutation"))
        self.assertAlmostEqual(stock[(19, 5)], bf.P_MUTATE * bf.P_BODY)               # 20 always steps down
        self.assertAlmostEqual(stock[(20, 4)], bf.P_MUTATE * (1 - bf.P_BODY))         # the fin tests the body

    @unittest.skipUnless(HARNESS_OUTPUT.is_file(), "build and run native/ftfp_ds_fish/ds_fish_logic_harness.c first")
    def test_against_the_dll_harness(self) -> None:
        results: dict[tuple[int, int], set[int]] = {}
        steps: dict[int, set[int]] = {}
        for line in HARNESS_OUTPUT.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts[0] == "breed":
                results.setdefault((int(parts[1]), int(parts[2])), set()).add(int(parts[4]))
            elif parts[0] == "step":
                steps.setdefault(int(parts[1]), set()).add(int(parts[3]))
        for (a, b), babies in results.items():
            if a in self.model.genes and b in self.model.genes:
                lo, hi, _coin = self.model._gene_child(a, b)
                self.assertEqual(babies, {lo, hi}, (a, b))


# ---------------------------------------------------------------- the model

class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stock = bf.load(None, False)
        cls.ds = bf.load(None, True)

    def test_children_sum_to_one(self) -> None:
        keys = [s.key for s in self.stock.species()]
        for a in keys:
            for b in keys:
                for effects in ("none", "max", "max_mutation"):
                    total = sum(p for _k, p in self.stock.children(a, b, effects))
                    self.assertAlmostEqual(total, 1.0, places=12)
        rng = random.Random(3)
        ds_keys = [s.key for s in self.ds.species()]
        for _ in range(4000):
            a, b = rng.choice(ds_keys), rng.choice(ds_keys)
            for effects in ("none", "max", "max_mutation"):
                children = self.ds.children(a, b, effects)
                self.assertAlmostEqual(sum(p for _k, p in children), 1.0, places=12)
                self.assertTrue(all(k in {s.key for s in self.ds.species()} for k, _p in children))

    def test_same_breeds_true_without_effects(self) -> None:
        for s in self.ds.species():
            self.assertEqual(self.ds.children(s.key, s.key, "none"), [(s.key, 1.0)])

    def test_no_pc_pair_gives_a_ds_gene_without_mutation(self) -> None:
        pc = [s.key for s in self.ds.species() if not s.patcher]
        rng = random.Random(5)
        for _ in range(3000):
            for child, _p in self.ds.children(rng.choice(pc), rng.choice(pc), "none"):
                self.assertFalse(bf.is_ds(child[0]) or bf.is_ds(child[1]))

    def test_ways_to_breed(self) -> None:
        for model in (self.stock, self.ds):
            for key in [(7, 7), (20, 16), (11, 11), (0, 0)] + ([(29, 29), (23, 2)] if model.extras else []):
                for effects in ("none", "max", "max_mutation"):
                    ways = model.ways_to_breed(key, effects)
                    self.assertTrue(ways, (key, effects))
                    self.assertLessEqual(len(ways), 20)
                    odds = [w[2] for w in ways]
                    self.assertEqual(odds, sorted(odds, reverse=True))
                    for m, f, p in ways:
                        self.assertAlmostEqual(dict(model.children(m, f, effects))[key], p)

    def test_magic_fish_examples_from_the_mechanics_page(self) -> None:
        gm = self.stock
        self.assertEqual(gm.children((8, 8), (14, 14), "none"), [((11, 11), 1.0)])     # Crimson Comet
        self.assertEqual(gm.children((4, 4), (10, 10), "none"), [((7, 7), 1.0)])       # Golden Guppy
        self.assertEqual(gm.children((12, 12), (16, 16), "none"), [((14, 14), 1.0)])   # Sustenance

    def test_plan_is_a_valid_chain(self) -> None:
        rng = random.Random(11)
        for model, effects in ((self.stock, "none"), (self.stock, "max_mutation"), (self.ds, "max_mutation")):
            keys = [s.key for s in model.species()]
            for _ in range(6):
                have = rng.sample([k for k in keys if not bf.is_ds(k[0]) and not bf.is_ds(k[1])], 3)
                want = rng.choice(keys)
                if want in have:
                    continue
                steps = model.plan(have, want, effects)
                owned = set(have)
                for step in steps:
                    m, f = step["parents"]
                    self.assertIn(m, owned)
                    self.assertIn(f, owned)
                    self.assertGreater(step["odds"], 0)
                    self.assertAlmostEqual(dict(model.children(m, f, effects))[step["child"]], step["odds"])
                    owned.add(step["child"])
                if steps:
                    self.assertEqual(steps[-1]["child"], want)

    def test_plan_impossible_and_known_routes(self) -> None:
        # without mutation, two even PC genes never leave the range they span
        self.assertEqual(self.stock.plan([(0, 0), (4, 4)], (20, 20), "none"), [])
        self.assertEqual(self.ds.plan([(20, 20)], (23, 23), "none"), [])
        self.assertEqual(self.ds.plan([(20, 20)], (23, 23), "max"), [])        # no Wasp Grouper
        self.assertTrue(self.ds.plan([(20, 20)], (23, 23), "max_mutation"))
        steps = self.stock.plan([(4, 4), (10, 10)], (7, 7), "none")
        self.assertEqual(steps, [{"parents": ((4, 4), (10, 10)), "child": (7, 7), "odds": 1.0}])

    def test_prices(self) -> None:
        for model in (self.stock, self.ds):
            for key in [(7, 7), (0, 0), (20, 16), (13, 6)] + ([(29, 29)] if model.extras else []):
                for effects in ("none", "max"):
                    prices = model.prices(key, effects)
                    base = bf.advertised(bf.base_price(*key), bf.EFFECTS[effects]["advertising"])
                    self.assertEqual(prices.highest_selling, 2 * base - 1)
                    self.assertIsNone(bf.sale_threshold(prices.highest_selling + 1, base, 0))
                    self.assertIsNotNone(bf.sale_threshold(prices.highest_selling, base, 0))
                    crowds = bf.EFFECTS[effects]["browsing"]
                    income = lambda p: sum(bf.income_per_day(p, base, n) for n in crowds) / len(crowds)  # noqa: E731
                    best = max(range(1, 2 * base), key=lambda p: (income(p), -p))
                    self.assertEqual(prices.best_per_day, best)
                    self.assertAlmostEqual(prices.best_per_day_income, income(best))
                    self.assertTrue(prices.note)

    def test_sale_bands(self) -> None:
        self.assertEqual(bf.sale_threshold(5, 10, 0), 30)       # half price or less
        self.assertEqual(bf.sale_threshold(6, 10, 0), 10)       # below B
        self.assertEqual(bf.sale_threshold(10, 10, 0), 4)       # B to 1.5B
        self.assertEqual(bf.sale_threshold(15, 10, 0), 4)
        self.assertEqual(bf.sale_threshold(16, 10, 0), 1)       # above 1.5B
        self.assertIsNone(bf.sale_threshold(20, 10, 0))         # 2B never sells
        self.assertEqual(bf.sale_threshold(5, 10, 4), 90)       # K = (4 + 2) / 2
        self.assertEqual(bf.EFFECTS["max"]["browsing"], (66, 72))

    def test_parts_and_rarity(self) -> None:
        bodies = self.ds.parts("body")
        self.assertEqual([p.index for p in bodies], list(range(21)) + list(range(23, 30)))
        self.assertEqual(bodies[0].name, "Shark")
        self.assertTrue(all(p.how for p in bodies))
        self.assertEqual(self.ds.get((7, 7)).rarity, "Rare")
        self.assertEqual(self.ds.get((2, 4)).rarity, "Uncommon")
        self.assertEqual(self.ds.get((26, 26)).rarity, "Common")       # Trigger / Clown: DS 24
        self.assertEqual(self.stock.species_note((20, 16)), "Magic Fish of Fertility")

    def test_how_quotes_every_proven_route(self) -> None:
        """Each part's "how" names exactly the routes the code gives it, with their odds: the
        eggs (emulated in EmulatedTests), the Unknown Chemical's steps, the breeding totals,
        and for the DS genes the DS Store's Exotic Fish Eggs (its source, pinned below)."""
        for model in (self.stock, self.ds):
            for kind in ("body", "fin"):
                for part in model.parts(kind):
                    g, how = part.index, model.how(kind, part.index)
                    for g0, p in bf.chemical_sources(g, model.extras):
                        word = "always" if p >= 1 else f"on {100 * p:.2f}%"
                        self.assertIn(f"a {bf._part_name(kind, g0)} {kind} {word}", how, (kind, g))
                    self.assertIn(f"{100 * bf.P_CHEMICAL:.2f}% a dose", how)
                    self.assertIn(f"{100 * bf.P_MUTATE:.2f}% a litter", how)
                    # every parent pair of the game's rule, by name, one line per first parent
                    lines = how.splitlines()
                    for a, b, p in model.part_combos(kind, g):
                        line = next(x for x in lines if x.startswith(f"  {bf._part_name(kind, a)} with "))
                        self.assertIn(bf._part_name(kind, b) + ("" if p >= 1 else f" ({100 * p:.2f}%)"), line)
                    if bf.is_ds(g):
                        self.assertIn("Never from two PC parents", how)
                        self.assertIn(f"Exotic Fish Eggs ($2300), {100 * bf.random_is(7, g - 23):.2f}%", how)
                    else:
                        self.assertNotIn("Exotic", how)
                    self.assertEqual("No egg lays it" in how, not bf.is_ds(g) and g % 2 == 1, (kind, g))
                    self.assertEqual(bf.flat(how), part.how)
        # breeding: every PC total that rounds down to the gene, and no other
        for g in bf.PC_GENES:
            self.assertEqual(set(bf.breeding_sums(g)), {a + b for a in bf.PC_GENES for b in bf.PC_GENES
                                                        if (a + b) // 2 == g})

    def test_ds_routes_are_the_dlls(self) -> None:
        store = (ROOT / "native" / "ftfp_ds_store" / "ftfp_ds_store.c").read_text(encoding="utf-8")
        for text in ("#define DS_FIRST_GENE 23", "#define DS_GENES 7", "int fin = DS_FIRST_GENE + RANDOM(DS_GENES);",
                     "int body = DS_FIRST_GENE + RANDOM(DS_GENES);", "{ 0, 2300,", '{ "Exotic Fish Eggs",'):
            self.assertIn(text, store)
        dll = (ROOT / "native" / "ftfp_ds_fish" / "ftfp_ds_fish.c").read_text(encoding="utf-8")
        for text in ("if (g == DS_LAST_GENE) {\n        *gene = gene_down(g);",
                     "} else if (game_random(100) <= 49 || g == 0) {\n        *gene = gene_up(g);",
                     "static int gene_up(int g) { return g == GENE_PC_LAST ? DS_FIRST_GENE : g + 1; }"):
            self.assertIn(text, dll.replace("\r\n", "\n"))
        self.assertEqual(bf.chemical_steps(20, True), [(23, bf.P_UP), (19, 1 - bf.P_UP)])
        self.assertEqual(bf.chemical_steps(29, True), [(28, 1.0)])
        self.assertEqual(bf.chemical_steps(20, False), [(19, 1.0)])

    def test_effects_choices(self) -> None:
        """0 effects, Max without the Wasp Grouper (no mutation: the same odds as 0 effects)
        and Max with it (the odds change); prices are the same with and without it."""
        self.assertEqual([v for v, _l in self.stock.effects_choices], ["none", "max", "max_mutation"])
        self.assertEqual(dict(self.stock.effects_choices)["max_mutation"], "Max effects, with Wasp Grouper")
        a, b = (20, 16), (20, 20)
        self.assertEqual(self.stock.children(a, b, "max"), self.stock.children(a, b, "none"))
        self.assertEqual(self.stock.children(a, b, "max"), [((20, 18), 1.0)])
        self.assertGreater(len(self.stock.children(a, b, "max_mutation")), 1)
        self.assertEqual(self.stock.prices((7, 7), "max_mutation"), self.stock.prices((7, 7), "max"))
        self.assertIn("no mutation chance", " ".join(self.stock.effects_text("max")))
        self.assertIn("Wasp Grouper", " ".join(self.stock.effects_text("max_mutation")))

    def test_discovered_from_a_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            make_settings(folder, ["Tester", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER"])
            pc = {(20, 16): 48, (0, 0): 4, (7, 7): 200}
            make_save(folder, 1, {**pc, (19, 23): 38}, ds_columns=True)
            sidecar = make_sidecar(folder, 1, {(29, 29): 40, (23, 0): 15})
            before = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            times = {p: p.stat().st_mtime_ns for p in before}
            self.assertEqual(self.stock.discovered(folder, 1), set(pc))
            self.assertEqual(self.ds.discovered(folder, 1), set(pc) | {(19, 23), (29, 29), (23, 0)})
            sidecar.write_bytes(b"junk")
            self.assertEqual(self.ds.discovered(folder, 1), set(pc) | {(19, 23)})
            for p, data in before.items():
                if p != sidecar:
                    self.assertEqual(p.read_bytes(), data)
                    self.assertEqual(p.stat().st_mtime_ns, times[p])

    def test_a_save_without_ds_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            make_save(Path(tmp), 3, {(1, 1): 20})
            self.assertEqual(self.ds.discovered(tmp, 3), {(1, 1)})
            (Path(tmp) / "Fish Tycoon4.ldw").write_bytes(b"ldwg" + bytes(40))
            with self.assertRaises(bf.SaveReadError):
                self.ds.discovered(tmp, 4)


if __name__ == "__main__":
    unittest.main()
