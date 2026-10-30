"""The Breeding Guide's Fish Tycoon model (docs/breeding-guide-interface.md).

Every rule is the game's own, from the vanilla LDW "Fish Tycoon.exe" (the
build the patcher pins) and, for the DS Exclusive Fish setting, from the
companion DLL's source (native/ftfp_ds_fish/ftfp_ds_fish.c). The tests in
tests/test_breeding_fish.py run the executable's own code in Unicorn
(tests/store_emulator.py) and check each table and rule below against it.

Genes. A fish is a body gene and a fin gene (fish record +0x4C / +0x50),
0-20 in the stock game; DS Exclusive Fish adds 23-29 (21 is the Golden
Seahorse's sprite slot and 22 its body, so both are skipped).

Names. A species' name is its fin's name and its body's name (0x419600, up
to 31 characters: the entry's name field is 0x20 bytes).

Base price B (entry +0x24). Set for every species by 0x418B10 when a game
starts (BASE_PRICES, emulated); the DS species use the DLL's DS formula
(body value + fin value, +10 for a matching DS pair). Advertising research
raises every B when a level finishes (0x420A6B): level 2 B += B / 10
(0x420AE6), level 3 B += B / 7 (0x420A82); the DLL applies the same to the
DS species (inflate_prices).

Breeding. Drop an adult on the isolation tank while another fish is in it:
the fish already there (the mother) becomes pregnant and stores the dropped
fish's (the father's) body and fin (record +0x14 / +0x18). At the birth
(0x42014C) a live adult Magic Fish of Mutation (Wasp Grouper, 13/6) in the
mother's tank gives Random(100) <= 15 to step the stored father's body
(Random(100) <= 49) or else fin, up on Random(100) <= 49 and otherwise
down; at 20 always down, at 0 always up, and the fin branch tests the
father's BODY for those two ends (a stock slip, 0x4201CC / 0x4201E8), then
both are clamped to 0-20 (0x42021D / 0x420245). Each baby is then made by
0x41FA30: body = (mother body + father body) / 2, fin the same, C division
of non-negative numbers, so rounded down (0x41FAAB). The litter is 1 baby,
+1 with the Magic Fish of Fertility, +1 with the Plant of Fertility; every
baby of a litter uses the same (possibly stepped) father, so the odds per
baby are the same at any litter size.

With DS Exclusive Fish the DLL replaces three of those steps: the step is
step_gene (the fin's own value is tested, 29 is the top end, 20 steps up into
23 and 23 down into 20), the clamp is 0-29, and a gene pair with a DS gene
breeds by the DS game's rule (breed_gene): the average on DS indices, an odd
sum rounded up or down by one Random(2) per litter that the body and fin
share. Two PC genes keep the PC's rounded-down average.

Selling (0x424240, once a real-time second while the selling scene is open;
see SALE_* below for the exact bands) and the 5 real-time seconds without a
sale after one (0x4240AB: next check at +5, cleared only once the clock is
past it, 0x4246E3) give the prices.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import struct

from breeding_guide import Part, Prices, Species        # the interface's dataclasses, defined once

GAME = "fish"

RAND_PERIOD = 32768        # the game's Random(n) is MSVC rand() % n, rand() 0..32767


def rand_count(n: int, k: int) -> int:
    """How many rand() values make Random(n) < k."""
    if n <= 1:
        return RAND_PERIOD if k > 0 else 0
    k = max(0, min(k, n))
    full, extra = divmod(RAND_PERIOD, n)
    return full * k + min(k, extra)


def chance_at_most(n: int, k: int) -> float:
    """The exact chance that Random(n) <= k."""
    return rand_count(n, k + 1) / RAND_PERIOD


P_MUTATE = chance_at_most(100, 15)       # 16.02%: the Mutation fish acts on a litter (0x420168)
P_BODY = chance_at_most(100, 49)         # 50.05%: it steps the body, otherwise the fin (0x42017B)
P_UP = chance_at_most(100, 49)           # 50.05%: one step up, otherwise down (0x420197 / 0x4201E0)
P_COIN = 0.5                             # the DS rounding: Random(2), 16384 of 32768 each way

# ------------------------------------------------------------------ the tables

PC_LAST = 20
SEAHORSE = 22
DS_FIRST, DS_LAST = 23, 29
PC_GENES = tuple(range(0, PC_LAST + 1))
DS_GENES = tuple(range(DS_FIRST, DS_LAST + 1))

# By DS index (exe genes 0-20, then DS 21-27 = exe 23-29): the exe's strings
# (0x4423C8.. for the fins; the bodies likewise) and the DLL's ds_data.h.
BODY_NAMES = (
    "Shark", "Catfish", "Arrowfish", "Snout", "Fatfish", "Snooper", "Goldshark", "Fire-Arrow", "Fruitfish",
    "Flashfish", "Goldbulb", "Comet", "Stickfish", "Grouper", "Leaffish", "Carp", "Beta", "Pigmy", "Bananafish",
    "Quicksilver", "Spotanus", "Clownfish", "Discus", "Bicolor", "Trigger", "Surgeonfish", "Tang", "Idle",
)
FIN_NAMES = (
    "Silky", "Tiger", "Hornet", "Fanned", "Pink", "Snubbed", "Wasp", "Canary", "Orange", "Oriental", "Golden",
    "Crimson", "Spined", "Stubby", "Speckled", "Razorback", "Greenfin", "Great-Sail", "Flagged", "Finless",
    "Twin-Fin", "Small-Fin", "Roundy", "Angel", "Clown", "Yellow", "Blue", "Moorish",
)
# The DS game's values (DLL ds_data.h: DS_BODY_VALUE / DS_FIN_VALUE), by DS index.
DS_BODY_VALUE = (2, 10, 5, 10, 2, 14, 5, 25, 8, 10, 15, 10, 2, 18, 15, 10, 9, 10, 9, 20, 2, 10, 4, 9, 6, 10, 8, 17)
DS_FIN_VALUE = (2, 10, 4, 10, 2, 10, 6, 10, 6, 20, 4, 24, 2, 10, 4, 10, 6, 10, 3, 10, 2, 10, 5, 11, 3, 15, 7, 15)

# B for each stock species, [body][fin], as 0x418B10 sets it (emulated).
BASE_PRICES = (
    (4, 12, 6, 12, 4, 12, 8, 12, 8, 22, 6, 26, 4, 12, 6, 12, 8, 12, 5, 12, 4),
    (12, 20, 30, 20, 12, 20, 16, 20, 16, 30, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12),
    (7, 15, 9, 15, 7, 15, 33, 15, 11, 25, 9, 29, 7, 15, 9, 15, 11, 15, 8, 15, 7),
    (12, 20, 14, 20, 12, 20, 16, 20, 16, 30, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12),
    (4, 12, 6, 12, 4, 12, 8, 12, 8, 22, 6, 26, 4, 12, 6, 12, 8, 12, 5, 12, 4),
    (16, 24, 18, 24, 16, 24, 20, 24, 70, 34, 18, 38, 16, 24, 18, 24, 20, 24, 17, 24, 16),
    (7, 15, 9, 15, 7, 15, 11, 15, 11, 25, 9, 29, 7, 15, 33, 15, 11, 15, 8, 15, 7),
    (27, 35, 29, 35, 27, 35, 31, 190, 31, 45, 29, 49, 27, 35, 29, 35, 31, 35, 28, 35, 27),
    (10, 18, 12, 18, 10, 18, 14, 18, 20, 28, 12, 32, 10, 18, 12, 18, 14, 18, 11, 18, 10),
    (12, 20, 14, 20, 12, 20, 16, 20, 16, 30, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12),
    (17, 25, 19, 25, 17, 25, 21, 25, 21, 70, 33, 39, 17, 25, 19, 25, 21, 25, 18, 25, 17),
    (12, 20, 14, 20, 12, 20, 16, 20, 16, 30, 14, 70, 12, 20, 14, 20, 16, 20, 13, 20, 12),
    (4, 12, 6, 12, 4, 12, 8, 12, 8, 22, 6, 26, 4, 12, 6, 12, 8, 12, 5, 12, 4),
    (20, 28, 22, 28, 20, 28, 95, 28, 24, 38, 22, 42, 20, 28, 22, 28, 24, 28, 21, 28, 20),
    (17, 25, 19, 25, 17, 25, 21, 25, 21, 35, 19, 39, 17, 25, 55, 25, 21, 25, 18, 25, 17),
    (12, 20, 14, 20, 12, 20, 16, 20, 16, 30, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12),
    (11, 19, 13, 19, 11, 19, 15, 19, 15, 29, 13, 33, 11, 19, 13, 19, 15, 19, 12, 19, 11),
    (12, 20, 14, 20, 12, 20, 16, 20, 16, 45, 14, 34, 12, 20, 14, 20, 16, 20, 13, 20, 12),
    (11, 19, 13, 19, 11, 19, 15, 19, 15, 29, 13, 33, 11, 19, 13, 19, 15, 19, 12, 19, 11),
    (22, 30, 24, 30, 22, 30, 26, 30, 26, 40, 24, 44, 22, 30, 24, 30, 26, 30, 23, 30, 22),
    (4, 12, 6, 12, 4, 12, 8, 12, 8, 22, 6, 26, 4, 12, 6, 12, 48, 12, 5, 12, 4),
)

# 0x41DE90: the seven magic fish, (body, fin).
MAGIC = {
    (20, 16): "Magic Fish of Fertility",
    (14, 14): "Magic Fish of Sustenance",
    (11, 11): "Magic Fish of Curing",
    (10, 9): "Magic Fish of Growth",
    (5, 8): "Magic Fish of Health",
    (13, 6): "Magic Fish of Mutation",
    (7, 7): "The Golden Guppy (magic fish)",
}
MUTATION_FISH = (13, 6)

TIER_NAMES = {1: "Common", 2: "Half-rare", 3: "Rare"}
NAME_FIELD = 31                    # the species entry's name is 0x20 bytes with its 0

# ------------------------------------------------------------------ the selling model

SALE_ROLL = 900                    # Random(900) <= T sells (0x424350 / 0x42437B / 0x42442F / 0x42446B)
SALE_PAUSE = 5                     # real-time seconds with no sale roll after a sale
DAY_SECONDS = 86400
SELLING_TANK = 21                  # adults the selling tank holds (stock game)
CUSTOMER_MAX = 4 + 6 + 2           # 4, +1 per ornament (6), +2 with the Golden Seahorse


def sale_threshold(price: int, base: int, browsing: int, sick: bool = False) -> int | None:
    """T in Random(900) <= T for one adult in the selling tank (0x424240), or None when it
    cannot sell (asking 2B or more). K = (N + 2) / 2, N the customers browsing or at the
    tanks (0x413800). Outside the tutorial's first-sale window."""
    k = (browsing + 2) // 2
    if price < base and not sick:
        return 30 * k if base - price >= base // 2 else 10 * k
    if price >= 2 * base:
        return None
    if price - base <= base // 2 and not sick:
        return 4 * k
    return k


def sale_chance(price: int, base: int, browsing: int) -> float:
    """The exact chance one healthy adult sells at one roll."""
    t = sale_threshold(price, base, browsing)
    if t is None:
        return 0.0
    return rand_count(SALE_ROLL, t + 1) / RAND_PERIOD


def income_per_day(price: int, base: int, browsing: int, fish: int = SELLING_TANK) -> float:
    """Money per real-time day at this asking price: the rolls go through the selling tank
    in slot order until one sells, then 5 seconds pass without a roll."""
    p = sale_chance(price, base, browsing)
    if p <= 0 or price <= 0:
        return 0.0
    q = 1.0 - (1.0 - p) ** fish
    return price * DAY_SECONDS / (SALE_PAUSE + 1.0 / q)


# The crowd counted when the selling scene opens (Game Mechanics, Selling):
# 4 + ornaments + 2 (Golden Seahorse) + 2 x Advertising level x (adults / 3 + Random(2) + 2).
def crowd(ornaments: int, seahorse: bool, advertising: int, adults: int, extra: int) -> int:
    return 4 + ornaments + (2 if seahorse else 0) + 2 * advertising * (adults // 3 + extra + 2)


EFFECTS = {
    # what each column assumes: Advertising level, customers browsing per crowd roll
    "none": {"advertising": 1, "browsing": (0,)},
    "max": {"advertising": 3, "browsing": tuple(crowd(6, True, 3, SELLING_TANK, r) for r in (0, 1))},
}


@lru_cache(maxsize=None)
def best_asking_price(base: int, crowds: tuple[int, ...]) -> tuple[int, float]:
    """The asking price (1 to 2B - 1) with the most money per real day, averaged over the
    crowd sizes (each equally likely); the lowest such price on a tie."""
    best_price, best_income = 0, 0.0
    for price in range(1, 2 * base):
        income = sum(income_per_day(price, base, n) for n in crowds) / len(crowds)
        if income > best_income + 1e-9:
            best_price, best_income = price, income
    return best_price, best_income


def advertised(base: int, level: int) -> int:
    """B after the Advertising research levels have finished: level 2 adds B / 10, level 3
    then adds B / 7 (0x420AE6, 0x420A82; rounded down, as the game's integer division)."""
    if level >= 2:
        base += base // 10
    if level >= 3:
        base += base // 7
    return base


def is_ds(gene: int) -> bool:
    return DS_FIRST <= gene <= DS_LAST


def ds_index(gene: int) -> int:
    return gene if gene <= PC_LAST else gene - 2


def exe_gene(index: int) -> int:
    return index if index <= PC_LAST else index + 2


def gene_tier(gene: int) -> int:
    """1 common, 2 half-rare, 3 rare: the game's lists (0x41DF99), the DS genes by the same
    rule on their DS index (DLL gene_tier)."""
    d = ds_index(gene)
    if d % 2:
        return 3
    return 2 if d % 4 == 2 else 1


def gene_up(gene: int) -> int:
    return DS_FIRST if gene == PC_LAST else gene + 1


def gene_down(gene: int) -> int:
    return PC_LAST if gene == DS_FIRST else gene - 1


def _how(kind: str, gene: int) -> str:
    noun = "body" if kind == "body" else "fin"
    if is_ds(gene):
        before = PC_LAST if gene == DS_FIRST else gene - 1
        return (f"DS Exclusive Fish only. The Unknown Chemical ($650), or the Magic Fish of Mutation at a "
                f"birth, steps a {noun} at {before} up into it (20, then 23 to 29); breeding, with at least "
                f"one DS parent; "
                f"Exotic Fish Eggs ($2300, with DS Store Items). Never from two PC parents.")
    if gene % 2:
        return (f"Breeding only: no egg lays it. Two parents whose {noun}s add up to {2 * gene} or "
                f"{2 * gene + 1} (for example {gene - 1} + {gene + 1}); or the Unknown Chemical ($650), "
                f"or the Magic Fish of Mutation at a birth, stepping a {noun} at {gene - 1} or {gene + 1}.")
    if gene == 20:
        return ("Common Fish Eggs ($120, 1 in 6 each) and the starter eggs; Rare Fish Eggs never lay 20. "
                f"Breeding: both parents' {noun}s at 20.")
    if gene % 4 == 0:
        return "Common Fish Eggs ($120, 1 in 6), Rare Fish Eggs ($1200, 1 in 10) and the starter eggs."
    return "Unusual Fish Eggs ($450, 1 in 5) and Rare Fish Eggs ($1200, 1 in 10)."


def _part_name(kind: str, gene: int) -> str:
    return (BODY_NAMES if kind == "body" else FIN_NAMES)[ds_index(gene)]


def species_name(body: int, fin: int) -> str:
    return f"{_part_name('fin', fin)} {_part_name('body', body)}"[:NAME_FIELD]


def base_price(body: int, fin: int) -> int:
    if not is_ds(body) and not is_ds(fin):
        return BASE_PRICES[body][fin]
    b, f = ds_index(body), ds_index(fin)
    return DS_BODY_VALUE[b] + DS_FIN_VALUE[f] + (10 if b == f and b > PC_LAST else 0)


# ------------------------------------------------------------------ save files

SAVE_HEADER = 0x18                 # "ldwg" header, then the state from +8
STATE_SIZE = 0x1E3C8
SPECIES_BASE = 0x14B40             # state offset of the species table
ROW_STRIDE, ENTRY_SIZE = 31, 40
ENTRY_PRICE, ENTRY_BASE = 0x20, 0x24
SIDECAR_FOLDER = "Fish Tycoon Fix Patcher Data"
SIDECAR_MAGIC, SIDECAR_VERSION = 0x53445446, 1           # "FTDS" (DLL on_save)
DS_ROWS_BYTES = len(DS_GENES) * ROW_STRIDE * ENTRY_SIZE


class SaveReadError(RuntimeError):
    pass


def _entry_discovered(data: bytes, at: int) -> bool:
    if at + ENTRY_SIZE > len(data) or data[at] == 0:
        return False                                     # no name: not a species entry
    price, base = struct.unpack_from("<ii", data, at + ENTRY_PRICE)
    return price != -1 and base != 0


def read_discovered(save_folder, slot: int, extras: bool) -> set[tuple[int, int]]:
    """The species slot `slot` has discovered (its asking price is set, entry +0x20 != -1):
    "Fish Tycoon<slot>.ldw" for the stock table and the PC body x DS fin columns, and the
    DS Fish companion's "DS Fish <slot>.dat" for the DS body rows. Read only."""
    folder = Path(save_folder)
    path = folder / f"Fish Tycoon{slot}.ldw"
    data = path.read_bytes()
    if len(data) < SAVE_HEADER + STATE_SIZE or data[:4] != b"ldwg":
        raise SaveReadError(f"{path.name} is not a Fish Tycoon save.")
    table = SAVE_HEADER + SPECIES_BASE - 8
    fins = PC_GENES + (DS_GENES if extras else ())
    found = set()
    for body in PC_GENES:
        for fin in fins:
            if _entry_discovered(data, table + (body * ROW_STRIDE + fin) * ENTRY_SIZE):
                found.add((body, fin))
    if extras:
        sidecar = folder / SIDECAR_FOLDER / f"DS Fish {slot}.dat"
        try:
            rows = sidecar.read_bytes()
        except OSError:
            rows = b""
        if len(rows) >= 12 + DS_ROWS_BYTES and struct.unpack_from("<3I", rows, 0) == (
                SIDECAR_MAGIC, SIDECAR_VERSION, DS_ROWS_BYTES):
            for body in DS_GENES:
                for fin in PC_GENES + DS_GENES:
                    at = 12 + ((body - DS_FIRST) * ROW_STRIDE + fin) * ENTRY_SIZE
                    if _entry_discovered(rows, at):
                        found.add((body, fin))
    return found


# ------------------------------------------------------------------ the model


class FishModel:
    game = GAME
    kinds = ("fin", "body")
    parent_labels = ("Mother: the fish already in the isolation tank",
                     "Father: the fish you drop on it")
    patcher_setting = "DS Exclusive Fish"

    def __init__(self, extras: bool = False) -> None:
        self.extras = bool(extras)
        self.genes = PC_GENES + (DS_GENES if self.extras else ())
        self._parts = {
            kind: [Part(kind, g, _part_name(kind, g), is_ds(g), _how(kind, g)) for g in self.genes]
            for kind in ("body", "fin")
        }
        self._part_by = {(p.kind, p.index): p for kind in self._parts for p in self._parts[kind]}
        self._species = [
            Species((b, f), species_name(b, f), (self._part_by[("body", b)], self._part_by[("fin", f)]),
                    is_ds(b) or is_ds(f), TIER_NAMES[max(gene_tier(b), gene_tier(f))], base_price(b, f))
            for b in self.genes for f in self.genes
        ]
        self._by_key = {s.key: s for s in self._species}
        self._children: dict = {}
        self._prices: dict = {}

    # ---- parts and species
    def parts(self, kind: str) -> list[Part]:
        return list(self._parts[kind])

    def species(self) -> list[Species]:
        return list(self._species)

    def get(self, key: tuple[int, int]) -> Species:
        return self._by_key[tuple(key)]

    def species_note(self, key: tuple[int, int]) -> str:
        return MAGIC.get(tuple(key), "")

    def part_label(self, kind: str) -> str:
        return {"body": "Body", "fin": "Fin"}[kind]

    def part_rarity(self, part: Part) -> str:
        """The gene's tier (0x41DF99; DS genes by the DLL's gene_tier): a fish is as rare as
        its rarer part."""
        return TIER_NAMES[gene_tier(part.index)]

    # ---- breeding
    def _gene_child(self, a: int, b: int) -> tuple[int, int, bool]:
        """(low, high, coin): the baby's gene from a mother gene and a father gene."""
        if not (is_ds(a) or is_ds(b)):
            return (a + b) // 2, (a + b) // 2, False
        s = ds_index(a) + ds_index(b)
        if s % 2 == 0:
            return exe_gene(s // 2), exe_gene(s // 2), False
        return exe_gene(s // 2), exe_gene(s // 2 + 1), True

    def _father_variants(self, father: tuple[int, int], effects: str) -> list[tuple[tuple[int, int], float]]:
        fb, ff = father
        if effects != "max":
            return [((fb, ff), 1.0)]
        out: dict[tuple[int, int], float] = {}

        def add(key, p):
            if p > 0:
                out[key] = out.get(key, 0.0) + p

        add((fb, ff), 1.0 - P_MUTATE)
        body_p, fin_p = P_MUTATE * P_BODY, P_MUTATE * (1.0 - P_BODY)
        if self.extras:
            for p, gene, is_body in ((body_p, fb, True), (fin_p, ff, False)):
                if gene == DS_LAST:
                    steps = [(gene_down(gene), 1.0)]
                elif gene == 0:
                    steps = [(1, 1.0)]
                else:
                    steps = [(gene_up(gene), P_UP), (gene_down(gene), 1.0 - P_UP)]
                for new, q in steps:
                    add((new, ff) if is_body else (fb, new), p * q)
        else:
            clamp = lambda g: max(0, min(PC_LAST, g))                       # noqa: E731
            # body branch: its own value at the ends
            if fb == PC_LAST:
                add((fb - 1, ff), body_p)
            elif fb == 0:
                add((1, ff), body_p)
            else:
                add((fb + 1, ff), body_p * P_UP)
                add((fb - 1, ff), body_p * (1.0 - P_UP))
            # fin branch: the BODY's value at the ends (the stock slip), then the clamp
            if fb == PC_LAST:
                add((fb, clamp(ff - 1)), fin_p)
            elif fb == 0:
                add((fb, clamp(ff + 1)), fin_p)
            else:
                add((fb, clamp(ff + 1)), fin_p * P_UP)
                add((fb, clamp(ff - 1)), fin_p * (1.0 - P_UP))
        return list(out.items())

    def children(self, a: tuple[int, int], b: tuple[int, int], effects: str) -> list[tuple[tuple[int, int], float]]:
        key = (tuple(a), tuple(b), effects)
        cached = self._children.get(key)
        if cached is not None:
            return list(cached)
        (mb, mf) = a
        out: dict[tuple[int, int], float] = {}
        for (fb, ff), p in self._father_variants(tuple(b), effects):
            blo, bhi, bcoin = self._gene_child(mb, fb)
            flo, fhi, fcoin = self._gene_child(mf, ff)
            if bcoin and fcoin:                                       # one roll for both
                cases = [((blo, flo), P_COIN), ((bhi, fhi), 1 - P_COIN)]
            else:
                bodies = [(blo, P_COIN), (bhi, 1 - P_COIN)] if bcoin else [(blo, 1.0)]
                fins = [(flo, P_COIN), (fhi, 1 - P_COIN)] if fcoin else [(flo, 1.0)]
                cases = [((x, y), px * py) for x, px in bodies for y, py in fins]
            for child, q in cases:
                out[child] = out.get(child, 0.0) + p * q
        result = sorted(((k, v) for k, v in out.items() if v > 0), key=lambda kv: (-kv[1], kv[0]))
        self._children[key] = tuple(result)
        return list(result)

    def _could_give(self, mother_gene: int, father_gene: int, target: int, effects: str) -> bool:
        fathers = {father_gene}
        if effects == "max":
            fathers |= {gene_up(father_gene), gene_down(father_gene), father_gene + 1, father_gene - 1}
        for g in fathers:
            if g in self.genes:
                lo, hi, _coin = self._gene_child(mother_gene, g)
                if target in (lo, hi):
                    return True
        return False

    def ways_to_breed(self, key: tuple[int, int], effects: str, limit: int = 20):
        tb, tf = key
        body_pairs = [(x, y) for x in self.genes for y in self.genes if self._could_give(x, y, tb, effects)]
        fin_pairs = [(x, y) for x in self.genes for y in self.genes if self._could_give(x, y, tf, effects)]
        best: dict[frozenset, tuple[float, tuple[int, int], tuple[int, int]]] = {}
        for mb, fb in body_pairs:
            for mf, ff in fin_pairs:
                mother, father = (mb, mf), (fb, ff)
                odds = dict(self.children(mother, father, effects)).get((tb, tf), 0.0)
                if odds <= 0:
                    continue
                pair = frozenset((mother, father))
                have = best.get(pair)
                if have is None or odds > have[0] + 1e-15:
                    best[pair] = (odds, mother, father)
        ranked = sorted(best.values(), key=lambda t: (-t[0], t[1], t[2]))
        return [(m, f, odds) for odds, m, f in ranked[:limit]]

    def part_combos(self, kind: str, index: int) -> list[tuple[int, int, float]]:
        """Every pair of parent bodies (or fins) that gives this gene with no effects, as
        (a, b, chance), a <= b; the chance is below 1 only for a DS pair with an odd sum."""
        out = []
        for x in self.genes:
            for y in self.genes:
                if y < x:
                    continue
                lo, hi, coin = self._gene_child(x, y)
                p = (P_COIN if lo == index else 0.0) + ((1 - P_COIN) if hi == index else 0.0) if coin \
                    else (1.0 if lo == index else 0.0)
                if p > 0:
                    out.append((x, y, p))
        return out

    def plan(self, have, want: tuple[int, int], effects: str) -> list[dict]:
        want = tuple(want)
        owned = {tuple(k) for k in have if tuple(k) in self._by_key}
        if want in owned or not owned or want not in self._by_key:
            return []
        order = sorted(owned)
        frontier = set(owned)
        found: dict[tuple[int, int], tuple[float, tuple, tuple]] = {}
        cost = {k: 0 for k in owned}           # breeding steps needed to have each species
        ordered = effects == "max"
        while frontier and want not in found:
            # breadth first, so the chain is as short (in generations) as it can be; among
            # the pairs that give a new species, the one needing the fewest steps, then the
            # best odds
            new: dict[tuple[int, int], tuple[float, tuple, tuple]] = {}
            new_cost: dict[tuple[int, int], int] = {}
            for i, m in enumerate(order):
                for j, f in enumerate(order):
                    if not ordered and j < i:
                        continue
                    if m not in frontier and f not in frontier:
                        continue
                    steps_needed = 1 + cost[m] + (cost[f] if f != m else 0)
                    for child, odds in self.children(m, f, effects):
                        if child in owned:
                            continue
                        have_best = new.get(child)
                        if have_best is None or (steps_needed, -odds) < (new_cost[child], -have_best[0] - 1e-15):
                            new[child] = (odds, m, f)
                            new_cost[child] = steps_needed
            if not new:
                break
            found.update(new)
            owned.update(new)
            cost.update(new_cost)
            order = sorted(owned)
            frontier = set(new)
        if want not in found:
            return []
        steps: list[dict] = []
        done = {tuple(k) for k in have}

        def need(key):
            if key in done:
                return
            odds, m, f = found[key]
            need(m)
            need(f)
            steps.append({"parents": (m, f), "child": key, "odds": odds})
            done.add(key)

        need(want)
        return steps

    # ---- prices
    def prices(self, key: tuple[int, int], effects: str) -> Prices:
        cache_key = (tuple(key), effects)
        cached = self._prices.get(cache_key)
        if cached is not None:
            return cached
        setup = EFFECTS[effects]
        base = advertised(base_price(*key), setup["advertising"])
        crowds = setup["browsing"]
        best_price, best_income = best_asking_price(base, crowds)
        if effects == "max":
            note = (f"B {base} after Advertising levels 2 and 3; {crowds[0]} or {crowds[1]} customers "
                    f"browsing (6 ornaments, the Golden Seahorse, Advertising level 3, a full selling "
                    f"tank); {SELLING_TANK} adults for sale, real time, a {SALE_PAUSE}-second pause after a sale.")
        else:
            note = (f"B {base}; nobody browsing (K = 1), Advertising level 1; {SELLING_TANK} adults for "
                    f"sale, real time, a {SALE_PAUSE}-second pause after a sale.")
        result = Prices(best_price, best_income, 2 * base - 1, note)
        self._prices[cache_key] = result
        return result

    def effects_max(self) -> list[str]:
        return [
            "Breeding: a live adult Magic Fish of Mutation (Wasp Grouper) in the mother's tank: "
            f"{100 * P_MUTATE:.2f}% per litter to step the father's body or fin one place before the "
            "babies are made. The Magic Fish and Plant of Fertility add babies (up to 3 a litter) but do "
            "not change the odds of each baby.",
            "Prices: Advertising research levels 2 and 3 (every base price + 1/10, then + 1/7).",
            "Customers: all 6 ornaments, the Golden Seahorse and Advertising level 3, with a full "
            f"selling tank: {EFFECTS['max']['browsing'][0]} or {EFFECTS['max']['browsing'][1]} customers, "
            "all counted as browsing.",
        ]

    def discovered(self, save_folder, slot: int) -> set[tuple[int, int]]:
        return read_discovered(save_folder, slot, self.extras)


def load(game_folder_or_exe=None, extras: bool = False) -> FishModel:
    """The model for a game copy; `extras` adds the DS Exclusive Fish species. The tables are
    the vanilla executable's own (proven by tests/test_breeding_fish.py), so the copy itself
    is not read."""
    return FishModel(extras)
