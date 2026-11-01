"""Game Mechanics, Plant Tycoon: the 48 bugs and the full-collection bonus.

The page's tables (game_mechanics_plant.BUG_NAMES, RARITIES, RANDOM_PICKS, QUALIFY_*, FOLIAGE_BUGS,
FLOWER_BUGS) are pinned twice: against the list below, written out by hand from the disassembly, and
against the vanilla executable's own bytes (skipped when it is missing): the name switch 0x418DA4,
the four spawners, the plant path's jump tables and gene compares, the random draw's pushes, the
duplicate payout table and the $5000 grant.
"""

from __future__ import annotations

from pathlib import Path
import re
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import game_mechanics as gm  # noqa: E402
import game_mechanics_plant as GM  # noqa: E402

VANILLA = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon"
           / "Plant Tycoon.exe")
BASE = 0x400000            # .text, .rdata and .data sit at file offset = VA - 0x400000

# number: (name, family, rarity, how): "random" or "foliage <gene>" / "flower <gene>".
EXPECTED = {
    1: ("Blue Butterfly", "Butterfly", "Common", "random"),
    2: ("Mission Blue Butterfly", "Butterfly", "Common", "random"),
    3: ("Fern Butterfly", "Butterfly", "Common", "foliage 7"),
    4: ("Black Moth", "Butterfly", "Common", "random"),
    5: ("Pale Moth", "Butterfly", "Uncommon", "random"),
    6: ("Lapis Butterfly", "Butterfly", "Uncommon", "random"),
    7: ("Lemon Moth", "Butterfly", "Uncommon", "random"),
    8: ("Amber Butterfly", "Butterfly", "Uncommon", "flower 14"),
    9: ("Plum Butterfly", "Butterfly", "Rare", "random"),
    10: ("Cherry Butterfly", "Butterfly", "Rare", "random"),
    11: ("Jet Moth", "Butterfly", "Rare", "flower 4"),
    12: ("Golden Butterfly", "Butterfly", "Rare", "flower 10"),
    13: ("Green Beetle", "Beetle", "Common", "random"),
    14: ("Brown Bug", "Beetle", "Common", "random"),
    15: ("Ladybug", "Beetle", "Common", "random"),
    16: ("Shiny Blue Beetle", "Beetle", "Common", "foliage 17"),
    17: ("Hiding Beetle", "Beetle", "Uncommon", "random"),
    18: ("Zebra Beetle", "Beetle", "Uncommon", "random"),
    19: ("Cockroach", "Beetle", "Uncommon", "random"),
    20: ("Mystic Scarab", "Beetle", "Uncommon", "flower 6"),
    21: ("Ebony Scarab", "Beetle", "Rare", "random"),
    22: ("Fire Scarab", "Beetle", "Rare", "random"),
    23: ("Shiny Flower Beetle", "Beetle", "Rare", "foliage 4"),
    24: ("Golden Beetle", "Beetle", "Rare", "foliage 8"),
    25: ("Blue Dragonfly", "Dragonfly", "Common", "random"),
    26: ("Pink Dragonfly", "Dragonfly", "Common", "random"),
    27: ("Tiger Dragonfly", "Dragonfly", "Common", "flower 9"),
    28: ("Emerald Dragonfly", "Dragonfly", "Common", "random"),
    29: ("Dart Dragonfly", "Dragonfly", "Uncommon", "random"),
    30: ("Fragile Dragonfly", "Dragonfly", "Uncommon", "random"),
    31: ("Ghost Dragonfly", "Dragonfly", "Uncommon", "random"),
    32: ("Glassy Dragonfly", "Dragonfly", "Uncommon", "foliage 22"),
    33: ("Fire Dragonfly", "Dragonfly", "Rare", "random"),
    34: ("Black Dragonfly", "Dragonfly", "Rare", "flower 11"),
    35: ("Earth Dragonfly", "Dragonfly", "Rare", "random"),
    36: ("Golden Dragonfly", "Dragonfly", "Rare", "flower 12"),
    37: ("Cactus Spider", "Spider", "Common", "foliage 15"),
    38: ("Yellow Spider", "Spider", "Common", "random"),
    39: ("Brown Spider", "Spider", "Common", "random"),
    40: ("Spotted Spider", "Spider", "Common", "random"),
    41: ("Pearly Spider", "Spider", "Uncommon", "random"),
    42: ("Limelike Spider", "Spider", "Uncommon", "random"),
    43: ("Bamboo Spider", "Spider", "Uncommon", "foliage 12"),
    44: ("Cricket Spider", "Spider", "Uncommon", "random"),
    45: ("Bumpy Spider", "Spider", "Rare", "random"),
    46: ("Jade Spider", "Spider", "Rare", "random"),
    47: ("Tahitian Spider", "Spider", "Rare", "flower 20"),
    48: ("Golden Spider", "Spider", "Rare", "foliage 23"),
}
GENE_NAMES = {("foliage", 4): "Orchid", ("foliage", 7): "Fern", ("foliage", 8): "Ananas", ("foliage", 12): "Bamboo",
              ("foliage", 15): "Pipe Cactus", ("foliage", 17): "Ball Cactus", ("foliage", 22): "Multiflora",
              ("foliage", 23): "Ridgeball", ("flower", 4): "Nox", ("flower", 6): "Mystic", ("flower", 9): "Jalapa",
              ("flower", 10): "Fabled", ("flower", 11): "Fragrant", ("flower", 12): "Blazing",
              ("flower", 14): "Aureus", ("flower", 20): "Tahitian"}
SPAWNERS = {0x4177C0: 0, 0x417870: 1, 0x417900: 2, 0x4179B0: 3}     # function -> family


def how(bug_id: int) -> str:
    for kind, table in (("foliage", GM.FOLIAGE_BUGS), ("flower", GM.FLOWER_BUGS)):
        for gene, b in table.items():
            if b == bug_id:
                return f"{kind} {gene}"
    return "random" if GM.random_bug_odds(bug_id) else "none"


def group(title: str):
    return next(g for g in gm.load_page("plant").groups if g.title == title)


def group_texts(title: str) -> list[str]:
    out = []
    g = group(title)
    out.append(g.note)
    for f in g.facts:
        out += [f.text, *f.subs, *(t for _, t in f.patched)]
    return out


class TableTests(unittest.TestCase):
    def test_the_48_bugs(self) -> None:
        self.assertEqual(len(GM.BUG_NAMES), 48)
        for number, (name, family, rarity, source) in EXPECTED.items():
            i = number - 1
            self.assertEqual((GM.BUG_NAMES[i], GM.BUG_FAMILIES[i // 12], GM.bug_rarity(i), how(i)),
                             (name, family, rarity, source), number)

    def test_every_bug_comes_one_way(self) -> None:
        plant = set(GM.FOLIAGE_BUGS.values()) | set(GM.FLOWER_BUGS.values())
        drawn = {f * 12 + i for f, picks in enumerate(GM.RANDOM_PICKS) for p in picks.values() for i in p}
        self.assertEqual((len(plant), len(drawn)), (16, 32))
        self.assertEqual(plant | drawn, set(range(48)))
        self.assertFalse(plant & drawn)
        # The random draw gives each rarity only from its own band of indices.
        for picks in GM.RANDOM_PICKS:
            for rarity, indices in picks.items():
                self.assertTrue(all(GM.RARITIES[i // 4] == rarity for i in indices))

    def test_random_shares(self) -> None:
        self.assertEqual(f"{GM.random_bug_odds(0)[3]:.3f}", "6.248")      # 25% x 74.976% x 33.334%
        self.assertEqual(f"{GM.random_bug_odds(4)[3]:.3f}", "1.418")      # 25% x 17.017% x 33.334%
        self.assertEqual(f"{GM.random_bug_odds(8)[3]:.3f}", "1.001")      # 25% x 8.008% x 50%
        total = sum(GM.random_bug_odds(i)[3] for i in range(48) if GM.random_bug_odds(i))
        self.assertAlmostEqual(total, 100.0, places=9)

    def test_qualifying_genes(self) -> None:
        self.assertEqual(GM.QUALIFY_FOLIAGE, (7, 8, 12, 14, 15, 17, 18, 22))
        self.assertEqual(GM.QUALIFY_FLOWER, (6, 9, 11, 12, 18, 19, 20, 23))


class PageTests(unittest.TestCase):
    def lines(self) -> list[str]:
        return list(group("Bugs one by one").facts[0].subs)

    def test_one_line_per_bug_in_order(self) -> None:
        lines = self.lines()
        self.assertEqual(len(lines), 48)
        for number, (name, family, rarity, source) in EXPECTED.items():
            line = lines[number - 1]
            self.assertTrue(line.startswith(f"{number}. {name} - {family}, {rarity} - "), line)
            if source == "random":
                self.assertIn("random draw:", line)
                self.assertNotIn("only from a plant", line)
            else:
                kind, gene = source.split()
                self.assertIn(f"only from a plant: {kind} {GENE_NAMES[kind, int(gene)]} (gene {gene}) from age "
                              f"{7 if kind == 'foliage' else 24}", line)

    def test_qualifying_caveats_name_the_genes(self) -> None:
        lines = self.lines()
        for number in (23, 48):          # foliage Orchid 4 and Ridgeball 23
            self.assertIn("qualifies by its flower, from age 24: Mystic 6, Jalapa 9, Fragrant 11, Blazing 12, "
                          "Arthurium 18, Venus 19, Tahitian 20 or Tilia 23 (always this bug with Arthurium 18, "
                          "Venus 19 or Tilia 23", lines[number - 1])
        for number in (8, 11, 12):       # flower Aureus 14, Nox 4, Fabled 10
            self.assertIn("qualifies by its foliage: Fern 7, Ananas 8, Bamboo 12, Rare Oak 14, Pipe Cactus 15, "
                          "Ball Cactus 17, Glaber 18 or Multiflora 22 (always this bug with Rare Oak 14 or "
                          "Glaber 18", lines[number - 1])
        caveats = [n for n, line in enumerate(lines, 1) if "qualifies by its" in line]
        self.assertEqual(caveats, [8, 11, 12, 23, 48])

    def test_rarity_words_are_exactly_common_uncommon_rare(self) -> None:
        # The owner's rule: "Common", "Uncommon", "Rare", capitalised, and no other rarity words.
        for title in ("Bugs", "Bugs one by one"):
            for text in group_texts(title):
                self.assertIsNone(re.search(r"\b(common|uncommon|rare)\b", text), text)
                self.assertIsNone(re.search(r"(?i)\btier|\bC/U/R\b", text), text)
                self.assertIsNone(re.search(r"\b(COMMON|UNCOMMON|RARE)\b", text), text)
        for line in self.lines():
            self.assertRegex(line, r"^\d+\. [A-Za-z ]+ - (Butterfly|Beetle|Dragonfly|Spider), (Common|Uncommon|Rare) - ")

    def test_bonus(self) -> None:
        text = "\n".join(group_texts("Bugs"))
        for needed in ("$5000", "once per game", "0x417530", "0x53F40", "adds 4 to the visitor score S",
                       "0x43FFEB", "8 + 47 x S / 78", "55", "0x440060", "Random(100) < 80 (80.04%)",
                       "no trophies", "Max Prices"):
            self.assertIn(needed, text)
        rendered = gm.render_text(gm.load_page("plant"))
        self.assertIn("Bugs one by one", rendered)
        self.assertIn("48. Golden Spider - Spider, Rare - only from a plant: foliage Ridgeball (gene 23)", rendered)


@unittest.skipUnless(VANILLA.is_file(), "needs the vanilla Plant Tycoon.exe")
class ExeTests(unittest.TestCase):
    exe = b""

    @classmethod
    def setUpClass(cls) -> None:
        cls.exe = VANILLA.read_bytes()

    def at(self, va: int, n: int) -> bytes:
        return self.exe[va - BASE:va - BASE + n]

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.at(va, 4))[0]

    def cstr(self, va: int) -> str:
        o = va - BASE
        return self.exe[o:self.exe.index(b"\0", o)].decode("latin-1")

    def call_target(self, va: int) -> int:
        self.assertEqual(self.at(va, 1), b"\xE8")
        return (va + 5 + struct.unpack("<i", self.at(va + 1, 4))[0]) & 0xFFFFFFFF

    def spawn_case(self, va: int) -> int:
        """A switch case `push n; call spawner` -> bug id."""
        self.assertEqual(self.at(va, 1), b"\x6A")
        return SPAWNERS[self.call_target(va + 2)] * 12 + self.at(va + 1, 1)[0] - 1

    def test_names(self) -> None:
        self.assertEqual(self.at(0x41894D, 7), bytes.fromhex("FF2485A48D4100"))   # jmp [eax*4 + 0x418DA4]
        for i in range(48):
            case = self.u32(0x418DA4 + 4 * i)
            body = self.at(case, 16)
            push = body.index(b"\x68")
            self.assertEqual(self.cstr(struct.unpack("<I", body[push + 1:push + 5])[0]), GM.BUG_NAMES[i], i)

    def test_spawners_add_the_family_base(self) -> None:
        for fn, family in SPAWNERS.items():
            add = (family * 12 - 1) & 0xFF
            self.assertEqual(self.at(fn + 0xB, 3), bytes([0x83, 0xC0, add]), hex(fn))      # add eax, base - 1
            self.assertEqual(self.at(fn + 0x13, 3), bytes.fromhex("389C01"))              # cmp [ecx+eax+..], bl
            self.assertEqual(self.u32(fn + 0x16), 0x53F4B)                                # collected flags

    def test_plant_spawners(self) -> None:
        for table, index, low, count, fail, expected in (
                (0x417E00, 0x417E24, 4, 20, 0x417DF8, GM.FOLIAGE_BUGS),
                (0x417EF0, 0x417F14, 4, 17, 0x417EE8, GM.FLOWER_BUGS)):
            found = {}
            for k in range(count):
                case = self.u32(table + 4 * self.at(index + k, 1)[0])
                if case != fail:
                    found[low + k] = self.spawn_case(case)
            self.assertEqual(found, expected)
        self.assertEqual(struct.unpack("<d", self.at(0x4677E0, 8))[0], 7.0)
        self.assertEqual(struct.unpack("<f", self.at(0x4677E8, 4))[0], 24.0)

    def test_qualifying_genes(self) -> None:
        def compares(start: int, end: int) -> tuple[int, ...]:
            code = self.at(start, end - start)
            return tuple(sorted(code[i + 2] for i in range(len(code) - 2) if code[i:i + 2] == b"\x83\xF8"))
        self.assertEqual(compares(0x417FAB, 0x417FD5), GM.QUALIFY_FOLIAGE)
        self.assertEqual(compares(0x417FE3, 0x41800E), GM.QUALIFY_FLOWER)

    def test_random_draw(self) -> None:
        cases = [self.u32(0x4183E4 + 4 * f) for f in range(4)] + [0x4183E1]
        for family in range(4):
            code_start, code_end = cases[family], cases[family + 1]
            ids = []
            va = code_start
            while va < code_end:
                if self.at(va, 1) == b"\x6A" and self.at(va + 2, 3) == b"\x8B\xCF\xE8":   # push n; mov ecx, edi; call
                    self.assertEqual(SPAWNERS[self.call_target(va + 4)], family)
                    ids.append(self.at(va + 1, 1)[0] - 1)
                va += 1
            picks = GM.RANDOM_PICKS[family]
            # In the code: Rare, then Uncommon, then Common; each switch's last value first.
            want = [i for rarity in ("Rare", "Uncommon", "Common") for i in reversed(picks[rarity])]
            self.assertEqual(ids, want, family)

    def test_rarity_and_duplicate_pay(self) -> None:
        self.assertEqual(list(self.at(0x4167DC, 48)), [i % 12 // 4 for i in range(48)])
        self.assertEqual([GM.RARITIES.index(GM.bug_rarity(i)) for i in range(48)], list(self.at(0x4167DC, 48)))
        for k, pay in enumerate(GM.DUPLICATE_PAY):
            case = self.u32(0x4167D0 + 4 * k)
            self.assertEqual(self.at(case + 3, 2), bytes([0x6A, pay]))       # push $
            self.assertEqual(self.at(case + 0x16, 5), bytes([0x68, 0x8C + k, 0, 0, 0]))   # message 0x8C-0x8E
        # Collections hover: string 0x1AE + 0 / 1 / 2 by the same index bands.
        self.assertEqual(self.at(0x419B9B, 6), bytes.fromhex("81C5AE010000"))

    def test_spawn_chance_and_bonus(self) -> None:
        self.assertEqual(self.at(0x417BF4, 10), bytes.fromhex("81BF340500000F270000"))   # Stop Time: 9999
        self.assertEqual(self.at(0x417C0B, 3), bytes.fromhex("83F914"))                  # min(collected, 20)
        self.assertEqual(self.at(0x417C28, 3), bytes.fromhex("83C606"))                  # + 6
        self.assertEqual(self.at(0x417C2B, 7), bytes.fromhex("80BF8521000000"))          # Magic Tree of Fragrance
        self.assertEqual(self.at(0x417F4B, 3), bytes.fromhex("83F84B"))                  # plant path: <= 75
        self.assertEqual(self.at(0x4177E6, 3), bytes.fromhex("83F828"))                  # duplicate skip: < 40
        self.assertEqual(self.at(0x417502, 7), bytes.fromhex("80BF403F050000"))          # one-time flag
        self.assertEqual(self.at(0x417512, 3), bytes.fromhex("83F830"))                  # all 48
        self.assertEqual(self.at(0x417530, 5), bytes.fromhex("6888130000"))              # $5000
        self.assertEqual(self.at(0x41753D, 7), bytes.fromhex("81406088130000"))          # Money Earned
        self.assertEqual(self.at(0x43FFF0, 8), bytes.fromhex("83F830750783C604"))        # visitor score + 4
        self.assertEqual(self.at(0x445D74, 3), bytes.fromhex("83F830"))                  # wander to the display
        self.assertEqual(self.at(0x445D83, 3), bytes.fromhex("83F850"))                  # Random(100) < 80
        self.assertEqual(self.cstr(0x467818), "Collected: %i out of 48")


if __name__ == "__main__":
    unittest.main()
