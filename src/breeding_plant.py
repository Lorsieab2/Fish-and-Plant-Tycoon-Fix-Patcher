"""Breeding Guide: Plant Tycoon's model (docs/breeding-guide-interface.md).

Every rule here is the game's own, read from the vanilla LDW "Plant Tycoon.exe"
(SHA-256 D1F83E3E...D6F9) and proven by emulating that code in
tests/test_breeding_plant.py, or, for Unused Flowers' 14 new flowers, taken from
the DLL's source (native/ftfp_new_flowers/ftfp_new_flowers.c). Addresses are
virtual addresses in the vanilla executable; "state" is the game object whose
first 8 bytes precede the save body (the save's data at file offset 0x18 is
loaded to state + 8 by 0x41EE00, and saved from there by 0x41D120).

Species and parts
    A plant is (foliage gene, flower gene), each 1-23 (flower 24-37 with Unused
    Flowers). Names: 0x41E550 writes "<flower word> <foliage word>" for every
    species to state + 0x540CC + (foliage * 26 + flower) * 96 (read at
    0x4286E2). Note the game's flower 17 word is "Citrus " with a trailing
    space, so its species have two spaces ("Citrus  Maranta"); species names
    here are exactly the game's, part names are stripped.
    Value V: 0x41D870 writes state + ((foliage + 0x1D) * 26 + flower) * 4: the
    foliage's base plus the flower's add, with 8 fixed exceptions.
    Class A-D (rarity()): the rule inlined in the pollination (0x424100), the
    pest check (0x42CAA6) and the shop (0x41DD54): D if either gene is above
    17; else C if either is even; else B if either is 3, 7, 11 or 15; else A.
    The game never shows a class, so the guide's Rarity is the store's own
    seed packet word for the rarer part (species_rarity, RARITY_STRINGS).

Breeding (pollination 0x4240A0, target pot record esi, donor edi)
    The child's foliage is the parents' foliages averaged, an odd sum rounded
    up (0x4240B5-0x4240D8); the flower the same (0x4240DA-0x424100). No roll:
    every seed of one pollination is that one species. With Unused Flowers,
    the DLL's hook of the pollination's tail (0x4241B4, on_pollinated) rounds
    an odd flower sum down instead on Random(2) == 0 (exactly 50%) when either
    parent's flower is 24-37. No chemical or magic plant enters 0x4240A0.

Mutation Liquid (0x42FA80, one dose on one pot)
    Random(2) != 0: the flower steps, else the foliage steps; then Random(2)
    != 0 steps down, else up (each exactly 50%). Flower above 23 becomes 22,
    0 becomes 2 (0x42FACC/0x42FAE8); with Unused Flowers above 37 becomes 36
    (the DLL rewrites 0x42FACE and 0x42FAD5). Foliage 24 becomes 22, 0 becomes
    2 (0x42FB1C/0x42FB2E). The new species is discovered at once (0x426F0B).

Selling (the nursery tick 0x437960, every 2 real seconds by time() 0x402080,
only while the Nursery screen is open)
    0x436BE0(n), n = browsing visitors (0x43ACD0: visitors present, not
    arriving or leaving), for each of the 15 sale spots: the asking price P
    (state + ((foliage + 0x37) * 26 + flower) * 4) is turned into the price
    visitors see, P', in this order (C integer division):
      over-pruned (0x42DDE0) x5, else 2+ cut parts (0x42DE50) P' - P'/8;
      dead foliage (0x42DEA0) P' + P'/3; health below 15 P' + P'/4;
      no flowers (0x42D570 == 0, not over-pruned) x2;
      1+ Plant Food doses (plant + 0x84, 0x42D650) P' - P'/5, 2+ again;
      infested x3; Golden Berries of Wealth (state + 0x2183) P' - P'/4.
    Then, with E = n / 2 and V the species' value:
      tutorial game before its first sale (state + 0x53F3F) and P' < 3V: k = 70;
      P' < V, not infested: k = 30 if V - P' >= V/2, else 10;
      otherwise P' - V >= V: never sells; P' - V > V/2: k = 2; else k = 5.
    It sells when Random(1300) <= k * E (0x436EA0-0x43702B), Random(n) being
    rand() % n (0x4033B0), rand() 0..32767.
    The visitor limit (0x43FF00, on entering the nursery) is 8 + trunc(47 S /
    78): S = 1 per small ornament and 4 per Sign, Fence, Gate, Refurbishment and
    Fountain (ornament ids 0x18-0x26, jump table 0x440020), 2 per plant for
    sale (0x43FBA0), 4 for the Rose of Joy (0x2182) and 2 for each other magic
    plant, 4 for all 48 bugs. Below the limit, Random(100) < 55: 1-3 arrive.

Prices (0x41DBD0): a new game prices each species V - d on Random(100) <= 50,
else V + d, d = Random(V/2). The Flower of Knowledge (found: 0x41EB3F, then
0x41EB46 calls 0x41DBD0) sets every price once to V + 3 x (V/4).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from breeding_guide import Part, Prices, Species        # the interface's dataclasses, defined once


GAME = "plant"
VANILLA_SHA256 = "D1F83E3E3CAFE177452E2F8B6AF4B68CACED783B77A304370389375DB611D6F9"

STOCK_FOLIAGES = range(1, 24)
STOCK_FLOWERS = range(1, 24)
NEW_FLOWERS = range(24, 38)            # Unused Flowers (extras)

# The game's words (0x41E550), by gene. Flower 17's is "Citrus " in the exe.
FOLIAGE_WORD = (
    "", "Reptans", "Scandens", "Grass", "Orchid", "Astera", "Gladiatus", "Fern", "Ananas", "Maranta",
    "Fanleaf", "Lemonbush", "Bamboo", "Maple", "Rare Oak", "Pipe Cactus", "Pear Cactus", "Ball Cactus",
    "Glaber", "Tigerfern", "Pitcher", "Weeper", "Multiflora", "Ridgeball",
)
FLOWER_WORD = (
    "", "Spotted", "Painted", "Daisy", "Nox", "Bluestar", "Mystic", "Rosaceae", "Viola", "Jalapa", "Fabled",
    "Fragrant", "Blazing", "Fourpetal", "Aureus", "Venomous", "Mela", "Citrus ", "Arthurium", "Venus",
    "Tahitian", "Lilia", "Baccatus", "Tilia",
    # Unused Flowers 24-37 (the DLL's ADJECTIVE, the owner's names)
    "Nightingale", "Rosetta", "Lilac", "Veronica", "Violetta", "Stella", "Silvermist", "Anagallis",
    "Buttercup", "Cerulean", "Phalaena", "Mirabilis", "Indigoberry", "Prunus",
)

# Value V = FOLIAGE_BASE[foliage] + FLOWER_ADD[flower] (0x41D870), except VALUE_EXCEPTIONS.
FOLIAGE_BASE = (0, 4, 28, 16, 36, 5, 36, 20, 28, 5, 30, 18, 34, 6, 32, 22, 42, 6, 68, 48, 70, 60, 64, 66)
FLOWER_ADD = (
    0, 3, 13, 8, 39, 4, 20, 10, 21, 5, 28, 10, 13, 6, 34, 8, 10, 4, 40, 64, 30, 32, 36, 26,
    60, 60, 45, 45, 45, 45, 35, 35, 35, 70, 70, 55, 50, 50,      # Unused Flowers' FLOWER_ADD
)
VALUE_EXCEPTIONS = {
    (2, 14): 130, (3, 15): 79, (4, 4): 95, (7, 7): 75, (7, 11): 46, (11, 10): 250, (13, 13): 44, (14, 16): 110,
}

# The six magic plants: species -> (name, flag byte in state), checked by 0x41EB00.
MAGIC = {
    (14, 16): ("Fruit of Life", 0x2180),
    (4, 4): ("Flower of Knowledge", 0x2181),
    (7, 7): ("Rose of Joy", 0x2182),
    (2, 14): ("Golden Berries of Wealth", 0x2183),
    (11, 10): ("Fabled Rose of Isola", 0x2184),
    (13, 13): ("Magic Tree of Fragrance", 0x2185),
}

# Shop seed packets (0x41DC60): tier -> (genes, price).
COMMON_GENES = (1, 5, 9, 13, 17)                       # Random(5) * 4 + 1
ENDANGERED_GENES = (3, 7, 11, 15)                      # Random(4) * 4 + 3
EXTINCT_GENES = (2, 4, 6, 8, 10, 12, 14, 16, 18, 19, 20, 21, 22, 23)   # 2 + 2 Random(8), or 18 + Random(6) on Random(100) < 15

# Selling.
NURSERY_TICK_SECONDS = 2               # 0x437974-0x43798D: time() + 1, run when time() exceeds it
MATURE_AGE = 24                        # a plant can go up for sale at age 24
NORMAL_UNIT_SECONDS = 600              # one age unit at Normal speed (Game Mechanics page: 10 minutes)
RAND_RANGE = 32768                     # the CRT's rand(): 0..32767
SALE_ROLL = 1300                       # Random(0x514)
MAX_TYPED_PRICE = 9999                 # "Set species price" caps typed values at 9999
ORNAMENT_POINTS = 10 * 1 + 5 * 4       # ids 0x18-0x26: ten +1, five +4 (0x440020)
SALE_SPOTS = 15


def is_new_flower(flower: int) -> bool:
    return 24 <= flower <= 37


# The rarity words are the game's own seed packet names, as the store prints them: "Common
# Seeds" (string 0x46FF58), "Endangered Seeds" (0x46FED4), "Extinct Seeds" (0x46FE48); the
# new flowers are sold only as the patcher's "Legendary Seeds" (ftfp_plant_upgrades.c,
# LEGENDARY_TITLE). Pinned by tests/test_breeding_plant.py (test_rarity_words_are_the_exes).
RARITY_ORDER = ("Common", "Endangered", "Extinct", "Legendary")
RARITY_STRINGS = {"Common": (0x46FF58, "Common Seeds"), "Endangered": (0x46FED4, "Endangered Seeds"),
                  "Extinct": (0x46FE48, "Extinct Seeds")}
LEGENDARY_TITLE = 'static const char LEGENDARY_TITLE[] = "Legendary Seeds\\n";'

# Shop packet prices (the seed purchase dialog, 0x430960: tier = index / 3): Common 50
# (0x430A34), Endangered 200 (0x430B8F), Extinct 2000 (0x430CA8); 3 packets of each tier a
# day (0x41DC86, ebx = 3). Mutation Liquid is chemical 34 (switch 0x4266B6, case 7 calls
# 0x42FA80), price 1000 (new-game table, 0x41E2F2). Legendary Seeds: ftfp_plant_upgrades.c.
PACKET_PRICES = {"Common": 50, "Endangered": 200, "Extinct": 2000}
PACKETS_A_DAY = 3
MUTATION_LIQUID_PRICE = 1000
LEGENDARY_PRICE, LEGENDARY_A_DAY, NEW_FLOWER_COUNT = 5000, 3, 14


def part_rarity(gene: int, kind: str) -> str:
    """A part's rarity: the shop seed packet tier that lays it (0x41DC60), in the store's
    words; the new flowers come only in Legendary Seeds (Unused Flowers)."""
    if kind == "flower" and is_new_flower(gene):
        return "Legendary"
    if gene in COMMON_GENES:
        return "Common"
    if gene in ENDANGERED_GENES:
        return "Endangered"
    return "Extinct"


def species_rarity(key: tuple[int, int]) -> str:
    """A species' rarity: its rarer part's packet."""
    return max(part_rarity(key[0], "foliage"), part_rarity(key[1], "flower"), key=RARITY_ORDER.index)


_RAND = 32768


def random_is(n: int, value: int) -> float:
    """The exact chance Random(n) (rand() % n, rand() 0..32767) gives `value`."""
    full, extra = divmod(_RAND, n)
    return (full + (1 if value < extra else 0)) / _RAND if 0 <= value < n else 0.0


def packet_chance(gene: int) -> tuple[str, float] | None:
    """(packet, chance a packet of it has this gene as its foliage or as its flower), 0x41DC60."""
    if gene in COMMON_GENES:
        return "Common", random_is(5, (gene - 1) // 4)
    if gene in ENDANGERED_GENES:
        return "Endangered", random_is(4, (gene - 3) // 4)
    low = sum(random_is(100, r) for r in range(15))             # Random(100) < 15
    if 18 <= gene <= 23:
        return "Extinct", low * random_is(6, gene - 18)
    if gene in EXTINCT_GENES:
        return "Extinct", (1 - low) * random_is(8, (gene - 2) // 2)
    return None


def rarity(key: tuple[int, int]) -> str:
    """The game's class A-D (0x424100, 0x42CAA6, 0x41DD54)."""
    foliage, flower = key
    if foliage > 17 or flower > 17:
        return "D"
    if foliage % 2 == 0 or flower % 2 == 0:
        return "C"
    if foliage in (3, 7, 11, 15) or flower in (3, 7, 11, 15):
        return "B"
    return "A"


def value(key: tuple[int, int]) -> int:
    if key in VALUE_EXCEPTIONS:
        return VALUE_EXCEPTIONS[key]
    return FOLIAGE_BASE[key[0]] + FLOWER_ADD[key[1]]


def species_name(key: tuple[int, int]) -> str:
    """The game's own name: 0x41E550's "<flower word> <foliage word>" (the DLL builds 24-37 the same way)."""
    return f"{FLOWER_WORD[key[1]]} {FOLIAGE_WORD[key[0]]}"


def knowledge_price(v: int) -> int:
    """The Flower of Knowledge's price (0x41DBD0 with state + 0x2181 set)."""
    return v + 3 * (v // 4)


def visitor_limit(score: int) -> int:
    """0x43FF00: 8 - trunc(S / 78 * -47)."""
    return 8 + (47 * score) // 78


def _cdiv(a: int, b: int) -> int:
    """C's integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


@dataclass(frozen=True)
class Condition:
    """What the buy roll (0x436BE0) reads about the plant for sale."""
    over_pruned: bool = False          # 0x42DDE0: the root cut, or more than 65% of parts cut
    cut_parts_2: bool = False          # 0x42DE50: 2 or more cut parts
    dead_foliage: bool = False         # 0x42DEA0
    health: int = 100                  # pot + 0x21AC, below 15 raises the price seen
    flowers: int = 1                   # 0x42D570, 0 doubles the price seen
    plant_food: int = 0                # plant + 0x84 (0x42D650): 1 and 2+ each lower it by 1/5
    infested: bool = False             # pot + 0x21B0
    golden_berries: bool = False       # state + 0x2183
    tutorial_first_sale: bool = False  # state + 0x53F3F


NO_EFFECTS = Condition()
MAX_EFFECTS = Condition(cut_parts_2=True, plant_food=2, golden_berries=True)


def seen_price(asking: int, c: Condition) -> int:
    """The price visitors see (0x436D4B-0x436E3C)."""
    p = asking
    if c.over_pruned:
        p *= 5
    elif c.cut_parts_2:
        p -= _cdiv(p, 8)
    if c.dead_foliage:
        p += _cdiv(p, 3)
    if c.health < 15:
        p += _cdiv(p, 4)
    if not c.over_pruned and c.flowers == 0:
        p *= 2
    if c.plant_food > 0:
        p -= _cdiv(p, 5)
    if c.plant_food >= 2:
        p -= _cdiv(p, 5)
    if c.infested:
        p *= 3
    if c.golden_berries:
        p -= _cdiv(p, 4)
    return p


def sale_k(asking: int, v: int, c: Condition) -> int | None:
    """k of the roll Random(1300) <= k x E, or None when the plant never sells."""
    p = seen_price(asking, c)
    if c.tutorial_first_sale and p < 3 * v:
        return 70
    if p < v and not c.infested:
        return 30 if v - p >= _cdiv(v, 2) else 10
    if p - v >= v:
        return None
    return 2 if p - v > _cdiv(v, 2) else 5


def roll_chance(threshold: int) -> float:
    """P(Random(1300) <= threshold) with rand() uniform over 0..32767."""
    if threshold < 0:
        return 0.0
    if threshold >= SALE_ROLL - 1:
        return 1.0
    full, extra = divmod(RAND_RANGE, SALE_ROLL)            # 25 full cycles and 268 extra values
    count = (threshold + 1) * full + min(threshold + 1, extra)
    return count / RAND_RANGE


def sale_chance(asking: int, v: int, browsing: int, c: Condition = NO_EFFECTS) -> float:
    """The chance one nursery tick sells this plant: Random(1300) <= k x (browsing / 2)."""
    if browsing <= 0:                                          # 0x436E59: no browsing visitor, no roll
        return 0.0
    k = sale_k(asking, v, c)
    return 0.0 if k is None else roll_chance(k * (browsing // 2))


def income_per_day(asking: int, v: int, browsing: int, c: Condition,
                   unit_seconds: int = NORMAL_UNIT_SECONDS) -> float:
    """Money per real day from one pot kept selling this species: a seed is planted, grows to age 24,
    goes up for sale and waits for a buyer, then the pot is replanted (the plant for sale is the
    pot's plant). Waiting = 2 s ticks / chance, the mean of the geometric wait."""
    chance = sale_chance(asking, v, browsing, c)
    if chance <= 0:
        return 0.0
    cycle = MATURE_AGE * unit_seconds + NURSERY_TICK_SECONDS / chance
    return asking * 86400 / cycle


@lru_cache(maxsize=None)
def price_search(v: int, c: Condition, browsing: int) -> tuple[int, float, int]:
    """(best asking price, its money per day, highest asking price that sells) for value V.

    The prices depend only on V and the conditions, so each is worked out once. Only the
    asking prices that can sell are tried: the price seen rises with the asking price (every
    step of seen_price keeps the order), and outside the tutorial's first sale a plant whose
    price seen is 2V or more never sells (sale_k), so the prices that sell are 1 up to the
    last one seen below 2V."""
    best, best_income, highest = 0, 0.0, 0
    for p in range(1, MAX_TYPED_PRICE + 1):
        if not c.tutorial_first_sale and seen_price(p, c) >= 2 * v:
            break
        if sale_k(p, v, c) is None:
            continue
        highest = p
        income = income_per_day(p, v, browsing, c)
        if income > best_income:
            best, best_income = p, income
    return best, best_income, highest


# The visitor score S (0x43FF00): each owned nursery ornament's points (ids 0x18-0x26 in
# order, its jump table 0x440020), 2 per plant for sale, 4 for the Rose of Joy and 2 for each
# other found magic plant, 4 for all 48 bugs.
ORNAMENT_POINTS_BY_ID = (1, 1, 1, 1, 1, 1, 1, 1, 1, 4, 4, 4, 4, 1, 4)
BUG_COUNT = 48


def visitor_score(ornaments: tuple[bool, ...], rose_of_joy: bool, other_magic: int, all_bugs: bool,
                  for_sale: int = SALE_SPOTS) -> int:
    """S for the ornaments owned (one flag per id 0x18-0x26), the magic plants found and the bug
    collection, with `for_sale` plants for sale (the Optimize Prices button: all 15 spots)."""
    return (sum(p for p, owned in zip(ORNAMENT_POINTS_BY_ID, ornaments) if owned) + 2 * for_sale
            + (4 if rose_of_joy else 0) + 2 * other_magic + (4 if all_bugs else 0))


def shop_best_price(v: int, golden_berries: bool, score: int) -> int:
    """The Optimize Prices button's price for a species of value V: the Breeding Guide's best per
    day for a healthy, flowering, unpruned plant without Plant Food, the Golden Berries of Wealth
    as found, and visitors at the limit for the score S, all browsing."""
    return price_search(v, Condition(golden_berries=golden_berries), visitor_limit(score))[0]


def mutation_steps(key: tuple[int, int], extras: bool) -> list[tuple[tuple[int, int], float]]:
    """One Mutation Liquid dose (0x42FA80): every result with its chance."""
    foliage, flower = key
    top = 37 if extras else 23
    out: dict[tuple[int, int], float] = {}

    def bounce_flower(g: int) -> int:
        return top - 1 if g > top else (2 if g <= 0 else g)

    def bounce_foliage(g: int) -> int:
        return 22 if g >= 24 else (2 if g <= 0 else g)

    for step in (1, -1):
        for new in ((foliage, bounce_flower(flower + step)), (bounce_foliage(foliage + step), flower)):
            out[new] = out.get(new, 0.0) + 0.25
    return sorted(out.items())


class PlantModel:
    game = GAME

    def __init__(self, extras: bool, source: Path | None = None) -> None:
        self.extras = extras
        self.source = source
        flowers = list(STOCK_FLOWERS) + (list(NEW_FLOWERS) if extras else [])
        from breeding_fish import flat
        self._foliage_parts = {g: Part("foliage", g, FOLIAGE_WORD[g], False, flat(_gene_how(g, "foliage", extras)))
                               for g in STOCK_FOLIAGES}
        self._flower_parts = {g: Part("flower", g, FLOWER_WORD[g].strip(), is_new_flower(g),
                                      flat(_gene_how(g, "flower", extras))) for g in flowers}
        self._species = {}
        for f in STOCK_FOLIAGES:
            for fl in flowers:
                key = (f, fl)
                self._species[key] = Species(key, species_name(key), (self._foliage_parts[f], self._flower_parts[fl]),
                                             is_new_flower(fl), species_rarity(key), value(key))
        self._keys = sorted(self._species)

    def how(self, kind: str, index: int, name=None) -> str:
        """How a part is first obtained, one route a line, by name (see _gene_how)."""
        return _gene_how(index, kind, self.extras, name)

    def part_combos(self, kind: str, index: int) -> list[tuple[int, int, float]]:
        return part_combos(kind, index, self.extras)

    # ------------------------------------------------------------ parts and species
    def part_rarity(self, part: Part) -> str:
        return part_rarity(part.index, part.kind)

    def parts(self, kind: str) -> list[Part]:
        if kind == "foliage":
            return list(self._foliage_parts.values())
        if kind == "flower":
            return list(self._flower_parts.values())
        raise ValueError(f"Plant Tycoon parts are 'foliage' or 'flower', not {kind!r}")

    def species(self) -> list[Species]:
        return [self._species[k] for k in self._keys]

    def species_by_key(self, key: tuple[int, int]) -> Species:
        return self._species[tuple(key)]

    @staticmethod
    def magic(key: tuple[int, int]) -> str | None:
        """The magic plant this species is, if any (0x41EB00)."""
        entry = MAGIC.get(tuple(key))
        return entry[0] if entry else None

    # ------------------------------------------------------------ breeding
    def _check(self, key) -> tuple[int, int]:
        key = (int(key[0]), int(key[1]))
        if key not in self._species:
            raise KeyError(f"no species {key}" + ("" if self.extras else " (Unused Flowers is off)"))
        return key

    def children(self, a, b, effects: str = "none") -> list[tuple[tuple[int, int], float]]:
        """The seed two plants give when one pollinates the other (0x4240A0), with its chance.
        Which plant is the target does not matter. No chemical or magic plant enters the
        pollination, so "none" and "max" give the seed itself; "max_mutation" is that seed
        planted and given one Mutation Liquid dose (0x42FA80), every result with its chance."""
        a, b = self._check(a), self._check(b)
        foliage = a[0] if a[0] == b[0] else (a[0] + b[0] + 1) // 2
        total = a[1] + b[1]
        up = a[1] if a[1] == b[1] else (total + 1) // 2
        if self.extras and (is_new_flower(a[1]) or is_new_flower(b[1])) and total % 2:
            seeds = [((foliage, total // 2), 0.5), ((foliage, up), 0.5)]
        else:
            seeds = [((foliage, up), 1.0)]
        if effects != "max_mutation":
            return seeds
        out: dict[tuple[int, int], float] = {}
        for seed, p in seeds:
            for child, q in mutation_steps(seed, self.extras):
                out[child] = out.get(child, 0.0) + p * q
        return sorted(out.items(), key=lambda kv: (-kv[1], kv[0]))

    def mutations(self, key) -> list[tuple[tuple[int, int], float]]:
        """One Mutation Liquid dose on a plant of `key`: each result with its chance."""
        return mutation_steps(self._check(key), self.extras)

    def ways_to_breed(self, key, effects: str = "none", limit: int = 20,
                      allowed=None) -> list[tuple[tuple[int, int], tuple[int, int], float]]:
        """Parent pairs whose pollination gives `key`, best odds first, then the cheapest parents
        to buy from the shop; pairs that include `key` itself are left out. With `allowed`, only
        parents in it are used, before the list is ranked and cut to `limit`."""
        key = self._check(key)
        keys = self._keys if allowed is None else [k for k in self._keys if k in allowed]
        found = []
        for i, a in enumerate(keys):
            for b in keys[i:]:
                if key in (a, b):
                    continue
                for child, odds in self.children(a, b, effects):
                    if child == key:
                        found.append((a, b, odds))
        found.sort(key=lambda t: (-t[2], _shop_cost(t[0], self.extras) + _shop_cost(t[1], self.extras), t[0], t[1]))
        return found[:limit]

    def plan(self, have, want, effects: str = "none", allowed=None) -> list[dict]:
        """The fewest generations from the species in `have` to `want`. Each step is
        {"parents": (a, b), "child": key, "odds": float, "via": "pollination"}; with "max_mutation"
        a step can be {"parents": (a, a), "via": "Mutation Liquid"} (one dose on a plant of a).
        With `allowed`, every species the chain makes is in it (the spoiler-free planner)."""
        want = self._check(want)
        known: dict[tuple[int, int], dict | None] = {self._check(k): None for k in have}
        if want in known:
            return []
        if allowed is not None:
            allowed = {tuple(k) for k in allowed}
            if want not in allowed:
                return []
        frontier = list(known)
        while frontier:
            found: dict[tuple[int, int], dict] = {}
            everyone = list(known)
            for a in frontier:
                for b in everyone:
                    for child, odds in self.children(a, b):
                        if child not in known and (allowed is None or child in allowed):
                            step = {"parents": (a, b), "child": child, "odds": odds, "via": "pollination"}
                            if child not in found or odds > found[child]["odds"]:
                                found[child] = step
                if effects == "max_mutation":
                    for child, odds in self.mutations(a):
                        if allowed is not None and child not in allowed:
                            continue
                        if child not in known and (child not in found or odds > found[child]["odds"]):
                            found[child] = {"parents": (a, a), "child": child, "odds": odds, "via": "Mutation Liquid"}
            if not found:
                return []
            known.update(found)
            if want in known:
                return _chain(known, want)
            frontier = list(found)
        return []

    # ------------------------------------------------------------ prices
    def prices(self, key, effects: str = "none") -> Prices:
        key = self._check(key)
        v = value(key)
        # Mutation Liquid changes no price: the buy roll (0x436BE0) and the prices (0x41DBD0)
        # never read it, so "max_mutation" prices are "max"'s.
        effects = "max" if effects == "max_mutation" else effects
        if effects == "max":
            c, score = MAX_EFFECTS, visitor_score((True,) * len(ORNAMENT_POINTS_BY_ID), True, 5, True)
        else:
            c, score = NO_EFFECTS, visitor_score((False,) * len(ORNAMENT_POINTS_BY_ID), False, 0, False, for_sale=1)
        browsing = visitor_limit(score)
        best, best_income, highest = price_search(v, c, browsing)
        what = ("every effect at its best: the Golden Berries of Wealth (price seen -1/4), 2 Plant Food doses "
                "(-1/5 twice), 2+ parts cut without over-pruning (-1/8), a healthy flowering plant, and the "
                f"visitor score S = {score} (all 15 ornaments, 15 plants for sale, the six magic plants, all 48 bugs)"
                if effects == "max" else
                "no effects: a healthy, flowering, unpruned plant with no Plant Food, alone for sale "
                f"(visitor score S = {score}), no ornaments, magic plants or bug collection")
        note = (f"V = {v}. {what}; visitors at the limit, {browsing}, all browsing (E = {browsing // 2}), an upper "
                f"bound. A nursery tick every {NURSERY_TICK_SECONDS} real seconds, only while the Nursery is open. "
                "Per real day at Normal speed (an age unit is 10 real minutes): one pot replanted at once after "
                "each sale, the plant growing 24 age units (4 h) and then waiting for a buyer. Highest selling = "
                "the highest asking price a visitor still buys at (the price seen must stay below 2V). The Flower of "
                f"Knowledge only resets the asking price to {knowledge_price(v)}; it does not change what visitors accept.")
        return Prices(best, best_income, highest, note)

    effects_choices = (("none", "0 effects"), ("max", "Max effects, without"),
                       ("max_mutation", "Max effects, with Mutation Liquid"))
    mutation_name = "Mutation Liquid"

    def effects_text(self, effects: str) -> list[str]:
        """What an effects choice assumes, in words."""
        if effects == "none":
            return ["No effects: the seed is halfway between its parents; a healthy, flowering, unpruned plant "
                    "with no Plant Food, alone for sale, no ornaments, magic plants or bug collection."]
        if effects == "max_mutation":
            first = ("Breeding: nothing changes a pollination's seed (it comes only from the two parents); "
                     f"Mutation Liquid (${MUTATION_LIQUID_PRICE}) changes a planted plant's flower or foliage to the "
                     "next one along, either way: each of the four results 25% a dose. The Breeding Calculator shows "
                     "the seed after one dose; the Breeding Planner can use a dose. It changes no price.")
        else:
            first = ("Breeding: no Mutation Liquid, so no mutation chance; the seed is halfway between its parents "
                     "(nothing else changes a pollination's seed).")
        return [first] + self._max_rest()

    def effects_max(self) -> list[str]:
        return self.effects_text("max_mutation")

    def _max_rest(self) -> list[str]:
        return [
            f"Golden Berries of Wealth ({species_name((2, 14)).strip()}, a magic plant): visitors see every asking "
            "price a quarter lower, so a higher price still sells.",
            "Plant Food: 2 doses before age 21 make visitors see the price 1/5 lower, twice.",
            "Pruning 2 or more parts, without cutting the root or more than 65% of parts: the price seen is 1/8 "
            "lower; over-pruning makes it 5 times higher.",
            "A healthy, flowering plant: no dead foliage (+1/3), health 15 or more (+1/4), flowers (x2 without), "
            "not infested (x3). The Fruit of Life, Soil and Water from Isola keep plants so.",
            "More visitors: all 15 nursery ornaments (S + 30), 15 plants for sale (S + 30), the six magic plants "
            "(S + 14, the Rose of Joy 4), all 48 bugs (S + 4): the visitor limit 8 + 47 S / 78 reaches 55.",
            f"Flower of Knowledge ({species_name((4, 4)).strip()}, a magic plant): once, every asking price becomes "
            "V + 3 x (V/4); it does not change what visitors accept.",
            "Not counted: the tutorial game's first-sale bonus (until the first sale); plant size and bloom (the "
            "buy roll reads neither).",
        ]

    # ------------------------------------------------------------ saves
    def discovered(self, save_folder, slot: int) -> set[tuple[int, int]]:
        return discovered(save_folder, slot, self.extras)


# ---------------------------------------------------------------- helpers

def _pct(p: float) -> str:
    return f"{100 * p:.2f}%"


def mutation_sources(gene: int, kind: str, extras: bool) -> list[tuple[int, float]]:
    """(gene before, chance per Mutation Liquid dose) for each gene one dose turns into `gene`
    (0x42FA80, mutation_steps)."""
    genes = list(STOCK_FOLIAGES) if kind == "foliage" else list(STOCK_FLOWERS) + (list(NEW_FLOWERS) if extras else [])
    slot = 0 if kind == "foliage" else 1
    out = []
    for s in genes:
        if s == gene:
            continue
        key = (s, 1) if slot == 0 else (1, s)
        p = sum(q for new, q in mutation_steps(key, extras) if new[slot] == gene)
        if p > 0:
            out.append((s, p))
    return out


def breeding_sums(gene: int) -> tuple[int, ...]:
    """The parent totals whose rounded-up average is `gene` (0x4240B5 / 0x4240DA)."""
    return tuple(s for s in (2 * gene - 1, 2 * gene) if s >= 2)


def part_word(kind: str, gene: int) -> str:
    return (FOLIAGE_WORD if kind == "foliage" else FLOWER_WORD)[gene].strip()


def part_combos(kind: str, gene: int, extras: bool) -> list[tuple[int, int, float]]:
    """Every pair of parent foliages (flowers), (a, b, chance) with a <= b, whose pollination
    (0x4240B5 / 0x4240DA: halfway, an odd distance rounding to the later one; Unused Flowers'
    50% rounding either way with a new flower) gives `gene`."""
    genes = list(STOCK_FOLIAGES) if kind == "foliage" else list(STOCK_FLOWERS) + (list(NEW_FLOWERS) if extras else [])
    out = []
    for i, a in enumerate(genes):
        for b in genes[i:]:
            total = a + b
            if kind == "flower" and extras and (is_new_flower(a) or is_new_flower(b)) and total % 2:
                p = (0.5 if total // 2 == gene else 0.0) + (0.5 if (total + 1) // 2 == gene else 0.0)
            else:
                p = 1.0 if (total + 1) // 2 == gene else 0.0
            if p > 0:
                out.append((a, b, p))
    return out


def _gene_how(g: int, kind: str, extras: bool = False, name=None) -> str:
    """How a foliage (flower) is first obtained, each route with its exact odds from the game's
    code (and, for the new flowers, the Unused Flowers and Store Upgrades DLLs' source), by the
    game's names only. `name(kind, gene)` gives a part's name, or None to leave it out."""
    from breeding_fish import named_list, named_pairs
    if name is None:
        name = part_word
    plural = "foliages" if kind == "foliage" else "flowers"
    lines = []
    if kind == "flower" and is_new_flower(g):
        lines.append(f"Unused Flowers only. Legendary Seeds (${LEGENDARY_PRICE}, {LEGENDARY_A_DAY} a day, with Add "
                     f"new store upgrades and items): any foliage, {_pct(random_is(NEW_FLOWER_COUNT, g - 24))} of the "
                     f"packets have this flower.")
    else:
        packet = packet_chance(g)
        if packet is not None:
            packet_name, p = packet
            lines.append(f"{packet_name} Seeds (${PACKET_PRICES[packet_name]}, {PACKETS_A_DAY} packets a day): "
                         f"{_pct(p)} of them have this {kind}.")
    pairs = named_pairs(part_combos(kind, g, extras), kind, name, plural)
    if pairs:
        rule = f"the seed's {kind} is halfway between its parents' in the game's list, the later one when two are"
        rule += " in the middle"
        if extras and kind == "flower":
            rule += "; with an Unused Flowers parent either middle one (the chance is shown)"
        lines.append(f"Breeding ({rule}); these parent {plural} give it:")
        lines.extend(pairs)
    sources = mutation_sources(g, kind, extras)
    if sources:
        lines.append(f"Mutation Liquid (${MUTATION_LIQUID_PRICE}): one dose changes a planted plant's flower or "
                     f"foliage to the next one along either way; it gives this {kind} from "
                     + named_list(sources, kind, name, plural, lambda n, p: f"a {n} {kind} on {_pct(p)}") + ".")
    return "\n".join(lines)


def _shop_cost(key: tuple[int, int], extras: bool) -> int:
    """What one seed of this species costs in the shop, or a large number when the shop never sells it."""
    f, fl = key
    if f in COMMON_GENES and fl in COMMON_GENES:
        return 50
    if f in ENDANGERED_GENES and fl in ENDANGERED_GENES:
        return 200
    if f in EXTINCT_GENES and fl in EXTINCT_GENES:
        return 2000
    if extras and is_new_flower(fl):
        return 5000
    return 100000


def _chain(known: dict, want: tuple[int, int]) -> list[dict]:
    steps: list[dict] = []
    seen: set = set()

    def visit(key):
        step = known.get(key)
        if step is None or key in seen:
            return
        seen.add(key)
        for parent in step["parents"]:
            visit(parent)
        steps.append(step)
    visit(want)
    return steps


# ---------------------------------------------------------------- saves (read-only)

SAVE_HEADER = 0x18                       # "ldwg" header; the body is state + 8 onwards
SAVE_BODY = 0x53FB0
DISCOVERED_STATE = 0x64                  # state + 0x64 + foliage * 24 + flower (0x42E2BB, 0x426F0B)
SIDECAR_MAGIC, SIDECAR_VERSION = 0x574C4650, 1
SIDECAR_BODY = 24 * 14 * 4 + 24 * 14     # price[24][14] then discovered[24][14] (ftfp_new_flowers.c)


def discovered(save_folder, slot: int, extras: bool) -> set[tuple[int, int]]:
    """The species slot `slot`'s save ("Plant Tycoon<slot>.ldw") has discovered; with Unused Flowers,
    also its "Plant Tycoon Fix Patcher Data\\New Flowers <slot>.dat". Only reads."""
    folder = Path(save_folder)
    data = (folder / f"Plant Tycoon{int(slot)}.ldw").read_bytes()
    if len(data) != SAVE_HEADER + SAVE_BODY or data[:4] != b"ldwg":
        raise ValueError(f"not a Plant Tycoon game save: {folder / f'Plant Tycoon{slot}.ldw'}")
    base = SAVE_HEADER + DISCOVERED_STATE - 8
    found = {(f, fl) for f in STOCK_FOLIAGES for fl in STOCK_FLOWERS if data[base + f * 24 + fl]}
    if extras:
        side = folder / "Plant Tycoon Fix Patcher Data" / f"New Flowers {int(slot)}.dat"
        if side.is_file():
            raw = side.read_bytes()
            if len(raw) == 12 + SIDECAR_BODY and struct.unpack_from("<3I", raw) == (SIDECAR_MAGIC, SIDECAR_VERSION, SIDECAR_BODY):
                flags = raw[12 + 24 * 14 * 4:]
                found |= {(f, 24 + k) for f in STOCK_FOLIAGES for k in range(14) if flags[f * 14 + k]}
    return found


def load(game_folder_or_exe=None, extras: bool = False) -> PlantModel:
    """The model. Its tables are the vanilla executable's (see the module docstring); the path is kept
    only to say where the game is."""
    source = Path(game_folder_or_exe) if game_folder_or_exe else None
    return PlantModel(extras, source)


Model = PlantModel
