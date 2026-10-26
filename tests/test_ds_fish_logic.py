"""The DS Fish companion's rules, checked decision by decision.

native/ftfp_ds_fish/ds_fish_logic_harness.c compiles the companion's source
with a scripted Random(n) and prints every decision; this test checks them
against the rules in docs/fish-tycoon-ds-fish-technical-map.md:

  * breeding: PC x PC is the PC's floor average; a pair with a DS gene is the
    DS game's average with an odd sum rounded by the litter roll (and, when
    the DS dump is present, exactly the DS session's breeding_*.csv);
  * the Unknown Chemical / Magic Fish of Mutation step: the vanilla roll with
    20 continuing into 23 and 29 as the end; the seahorse body never moves;
  * rarity tiers, sprite decoding (PC genes exactly as the game decodes them,
    when the vanilla executable is available to emulate), fin anchors, the
    head-on rule, prices and names.

The harness is built by MSVC (see the build command in the class below);
when it is missing the test is skipped, so the suite still runs anywhere.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS_OUTPUT = ROOT / "build" / "ftfp_ds_fish" / "logic.txt"
LAYOUT = ROOT / "data" / "ds_fish_layout.json"
GENES = list(range(21)) + list(range(23, 30))
DS_DUMP = Path(os.environ.get("FISH_TYCOON_DS_DUMP", r"C:\Users\Owner\Downloads\Current Modded LDW Games and Dumps\Game Dumps\Fish Tycoon (USA) - Dump"))
VANILLA = Path(os.environ.get("FISH_TYCOON_VANILLA", r"C:\Users\Owner\Downloads\Current Modded LDW Games and Dumps\Vanilla Games\Fish Tycoon"))


def ds(gene: int) -> int:
    return gene if gene <= 20 else gene - 2


def exe(index: int) -> int:
    return index if index <= 20 else index + 2


def is_ds(gene: int) -> bool:
    return 23 <= gene <= 29


def load_lines() -> dict[str, list[list[str]]]:
    lines: dict[str, list[list[str]]] = {}
    for line in HARNESS_OUTPUT.read_text(encoding="utf-8").splitlines():
        kind, *rest = line.split(" ", 4 if line.startswith("species") else -1)
        lines.setdefault(kind, []).append(rest)
    return lines


@unittest.skipUnless(HARNESS_OUTPUT.is_file(), "build and run native/ftfp_ds_fish/ds_fish_logic_harness.c first")
class DsFishLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lines = load_lines()

    def test_breeding(self) -> None:
        results: dict[tuple[int, int], set[int]] = {}
        for a, b, _coin, baby in self.lines["breed"]:
            results.setdefault((int(a), int(b)), set()).add(int(baby))
        self.assertEqual(len(results), len(GENES) ** 2)
        for (a, b), babies in results.items():
            if not is_ds(a) and not is_ds(b):
                self.assertEqual(babies, {(a + b) // 2}, f"PC x PC {a} x {b}")
            else:
                s = ds(a) + ds(b)
                expected = {exe(s // 2)} | ({exe(s // 2 + 1)} if s % 2 else set())
                self.assertEqual(babies, expected, f"DS pair {a} x {b}")
            if a == b:
                self.assertEqual(babies, {a}, "same x same breeds true")

    @unittest.skipUnless((DS_DUMP / "text" / "breeding_body.csv").is_file(), "DS dump not present")
    def test_breeding_matches_the_ds_tables(self) -> None:
        results: dict[tuple[int, int], set[int]] = {}
        for a, b, _coin, baby in self.lines["breed"]:
            results.setdefault((int(a), int(b)), set()).add(int(baby))
        for part in ("body", "fin"):
            with open(DS_DUMP / "text" / f"breeding_{part}.csv", newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    a, b = exe(int(row["parent1_idx"])), exe(int(row["parent2_idx"]))
                    if not (is_ds(a) or is_ds(b)):
                        continue                       # PC x PC keeps the PC's own rule
                    ds_babies = {exe(int(row["baby_idx"]))}
                    if row["baby_idx_alt"]:
                        ds_babies.add(exe(int(row["baby_idx_alt"])))
                    self.assertEqual(results[(a, b)], ds_babies, f"{part} {a} x {b}")

    def test_mutation_step(self) -> None:
        for gene, roll, after in self.lines["step"]:
            gene, roll, after = int(gene), int(roll), int(after)
            if gene == 22:
                self.assertEqual(after, 22, "the seahorse body never mutates")
                continue
            if gene == 29:
                expected = 28
            elif roll <= 49 or gene == 0:
                expected = 23 if gene == 20 else gene + 1
            else:
                expected = 20 if gene == 23 else gene - 1
            self.assertEqual(after, expected, f"gene {gene} roll {roll}")

    def test_no_pc_pair_breeds_a_ds_gene(self) -> None:
        for a, b, _coin, baby in self.lines["breed"]:
            if not is_ds(int(a)) and not is_ds(int(b)):
                self.assertFalse(is_ds(int(baby)))

    def test_tiers(self) -> None:
        for gene, tier in self.lines["tier"]:
            gene, tier = int(gene), int(tier)
            if gene in (21, 22):
                expected = 3 if gene == 21 else 0     # 21 is odd (never a fish gene); 22 is the seahorse
            else:
                d = ds(gene)
                expected = 3 if d % 2 else 2 if d % 4 == 2 else 1
            self.assertEqual(tier, expected, f"gene {gene}")

    def test_sprite_decoding(self) -> None:
        decoded = {int(i): (int(e), int(f)) for i, e, f in self.lines["decode"]}
        vanilla = self._vanilla_decoder()
        for sprite_id, (entry, frame) in decoded.items():
            gene = (sprite_id - 10000) // 100
            if is_ds(gene):
                as_pc = (sprite_id - (gene - 20) * 100)            # same frame code on gene 20
                pc_entry, pc_frame = vanilla(as_pc) if vanilla else decoded[as_pc]
                part = pc_entry - (38 + 3 * 20)
                self.assertEqual((entry, frame), (197 + 3 * (gene - 23) + part, pc_frame), f"id {sprite_id}")
            elif vanilla and gene <= 22:
                self.assertEqual((entry, frame), vanilla(sprite_id), f"id {sprite_id}")

    def test_fin_anchors(self) -> None:
        layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
        pairs = {(p["body"], p["fin"]): p["anchor"] for p in layout["pair_anchors"]}
        for body, fin, *anchor in self.lines["anchor"]:
            body, fin, anchor = int(body), int(fin), [int(v) for v in anchor]
            if is_ds(body) or is_ds(fin):
                self.assertEqual(anchor, pairs[(body, fin)], f"{body} x {fin}")
            else:
                self.assertEqual(anchor, [-1, -1, -1, -1], "PC x PC keeps the game's anchors")

    def test_head_on_pc_pairs_unchanged(self) -> None:
        for body, fin, _frame, top, bot in self.lines["headon"]:
            if not is_ds(int(body)) and not is_ds(int(fin)):
                self.assertEqual((int(top), int(bot)), (-13 - 17, 10 - 21))

    def test_prices_and_names(self) -> None:
        body_value = [2, 10, 5, 10, 2, 14, 5, 25, 8, 10, 15, 10, 2, 18, 15, 10, 9, 10, 9, 20, 2, 10, 4, 9, 6, 10, 8, 17]
        fin_value = [2, 10, 4, 10, 2, 10, 6, 10, 6, 20, 4, 24, 2, 10, 4, 10, 6, 10, 3, 10, 2, 10, 5, 11, 3, 15, 7, 15]
        names = {}
        for body, fin, price, *name in self.lines["species"]:
            body, fin, price = int(body), int(fin), int(price)
            b, f = ds(body), ds(fin)
            expected = body_value[b] + fin_value[f] + (10 if b == f and b > 20 else 0)
            self.assertEqual(price, expected, f"{body} x {fin}")
            names[(body, fin)] = name[0] if name else ""
        self.assertEqual(names[(29, 29)], "Moorish Idle")
        self.assertEqual(names[(23, 20)], "Twin-Fin Clownfish")
        self.assertEqual(names[(0, 23)], "Small-Fin Shark")
        self.assertTrue(all(len(n) < 32 for n in names.values()))

    @unittest.skipUnless((DS_DUMP / "text" / "species_values.csv").is_file(), "DS dump not present")
    def test_prices_match_the_ds_table(self) -> None:
        with open(DS_DUMP / "text" / "species_values.csv", newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        prices = {(int(b), int(f)): int(p) for b, f, p, *_ in self.lines["species"]}
        for b in range(28):
            for f in range(28):
                if b > 20 or f > 20:
                    self.assertEqual(prices[(exe(b), exe(f))], int(rows[b + 1][f + 1]), f"DS {b} x {f}")

    @staticmethod
    def _vanilla_decoder():
        exe_path = VANILLA / "Fish Tycoon.exe"
        try:
            import pefile
            from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
            from unicorn.x86_const import UC_X86_REG_ESP
        except ImportError:
            return None
        if not exe_path.is_file():
            return None
        image = pefile.PE(str(exe_path)).get_memory_mapped_image()
        # One emulator for every id: the decoder writes only its output pair.
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x400000, 0x60000)
        mu.mem_write(0x400000, image[:0x60000])
        mu.mem_map(0x20000000, 0x10000)

        def decode(sprite_id: int) -> tuple[int, int]:
            sp, out = 0x20008000, 0x20004000
            mu.mem_write(sp, struct.pack("<III", 0x20001000, sprite_id, out))
            mu.reg_write(UC_X86_REG_ESP, sp)
            mu.emu_start(0x4122A0, 0x20001000, count=200)
            return struct.unpack("<ii", mu.mem_read(out, 8))

        return decode


if __name__ == "__main__":
    unittest.main()
