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

# The tiers in the game's own words. The game prints no tier label, so each is the word the
# exe itself uses for exactly those genes: "Common Fish Eggs" (string 0x4457C8) lay exactly
# the tier 1 genes 0, 4 ... 20 (Random(6) x 4, 0x4213F8), "Unusual Fish Eggs" (0x4456F4)
# exactly the tier 2 genes 2, 6 ... 18 (Random(5) x 4 + 2, 0x4214C7), and the odd genes,
# which no egg lays, are the "Extremely rare hybrids" (0x4469D8). Pinned by
# tests/test_breeding_fish.py (test_tier_words_are_the_exes).
TIER_NAMES = {1: "Common", 2: "Unusual", 3: "Rare"}
TIER_STRINGS = {1: (0x4457C8, "Common Fish Eggs"), 2: (0x4456F4, "Unusual Fish Eggs"),
                3: (0x4469D8, "Extremely rare hybrids are extremely fragile.")}
NAME_FIELD = 31                    # the species entry's name is 0x20 bytes with its 0

# ------------------------------------------------------------------ how parts are obtained

# The store's eggs: (name, price, Random(n), multiplier, add) - each baby's body and fin are
# each Random(n) x multiplier + add, rolled separately (hatch code 0x4213F8 / 0x4214C7 /
# 0x4215A0; prices set by the new-game store table, 0x419A88 / 0x419A92 / 0x419A9C).
STORE_EGGS = (
    ("Common Fish Eggs", 120, 6, 4, 0),
    ("Unusual Fish Eggs", 450, 5, 4, 2),
    ("Rare Fish Eggs", 1200, 10, 2, 0),
)
EGG_ADDRESSES = {"Common Fish Eggs": (0x4213D1, 0x421437), "Unusual Fish Eggs": (0x4214A0, 0x42150A),
                 "Rare Fish Eggs": (0x421573, 0x4215DB)}
UNKNOWN_CHEMICAL_PRICE = 650       # 0x419A7E
P_CHEMICAL = chance_at_most(100, 25)  # 26.03%: each live fish in the tank is changed (0x420EE3)
EXOTIC_EGGS = ("Exotic Fish Eggs", 2300, 7)   # DS Store Items (ftfp_ds_store.c: price 2300, DS_GENES 7)
# The starter eggs of a new game (0x41FC90): babies 1-7 (7 in a new game, the tanks empty).
# (body, fin) for each, as sets: the first is fixed, the fifth to seventh remap (20, 16) to (20, 12).
STARTER_BABIES = (
    ({20}, {16}),
    ({4 * r for r in range(5)}, {4 * r for r in range(5)}),
    ({4 * r + 4 for r in range(5)}, {0}),
    ({4 * r for r in range(5)}, {20}),
) + (({4 * r for r in range(6)}, {4 * r for r in range(6)}),) * 3


def random_is(n: int, value: int) -> float:
    """The exact chance that Random(n) gives `value`."""
    return (rand_count(n, value + 1) - rand_count(n, value)) / RAND_PERIOD


def egg_chance(n: int, mul: int, add: int, gene: int) -> float:
    """The chance an egg baby's body (or fin) is `gene`, for genes Random(n) x mul + add."""
    r, rest = divmod(gene - add, mul)
    return random_is(n, r) if rest == 0 and 0 <= r < n else 0.0


def chemical_steps(gene: int, extras: bool) -> list[tuple[int, float]]:
    """Where one Unknown Chemical step (0x420EFB body / 0x420F27 fin, which test the gene's own
    value) takes a gene: always down at the top end (20, or 29 with DS Exclusive Fish's
    step_gene), always up at 0, else up on Random(100) <= 49."""
    top = DS_LAST if extras else PC_LAST
    up = gene_up(gene) if extras else gene + 1
    down = gene_down(gene) if extras else gene - 1
    if gene == top:
        return [(down, 1.0)]
    if gene == 0:
        return [(up, 1.0)]
    return [(up, P_UP), (down, 1.0 - P_UP)]


def _pct(p: float) -> str:
    return "always" if p >= 1.0 else f"{100 * p:.2f}%"

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


def power(x: float, n: int) -> float:
    """x to the whole power n, one multiplication at a time: the Optimize Prices DLL
    (native/common/price_math.h) does the same steps, so both get the same doubles."""
    result = 1.0
    for _ in range(n):
        result *= x
    return result


def income_per_day(price: int, base: int, browsing: int, fish: int = SELLING_TANK) -> float:
    """Money per real-time day at this asking price: the rolls go through the selling tank
    in slot order until one sells, then 5 seconds pass without a roll."""
    p = sale_chance(price, base, browsing)
    if p <= 0 or price <= 0:
        return 0.0
    q = 1.0 - power(1.0 - p, fish)
    return price * DAY_SECONDS / (SALE_PAUSE + 1.0 / q)


# The crowd counted when the selling scene opens (Game Mechanics, Selling):
# 4 + ornaments + 2 (Golden Seahorse) + 2 x Advertising level x (adults / 3 + Random(2) + 2).
# The selling scene counts at most 21 adults for its crowd (stock: the tank holds 21; Bigger tanks
# caps its count at 21 at 0x423EEA, docs/fish-tycoon-tank-expansion.md section 2E).
CROWD_ADULTS_MAX = 21


def crowd(ornaments: int, seahorse: bool, advertising: int, adults: int, extra: int) -> int:
    adults = min(adults, CROWD_ADULTS_MAX)
    return 4 + ornaments + (2 if seahorse else 0) + 2 * advertising * (adults // 3 + extra + 2)


def shop_crowds(ornaments: int, seahorse: bool, advertising: int, tank: int = SELLING_TANK) -> tuple[int, int]:
    """The two crowds (Random(2) gives 0 or 1) a full selling tank of `tank` adults draws."""
    return tuple(crowd(ornaments, seahorse, advertising, tank, r) for r in (0, 1))


EFFECTS = {
    # what each column assumes: Advertising level, customers browsing per crowd roll
    "none": {"advertising": 1, "browsing": (0,)},
    "max": {"advertising": 3, "browsing": shop_crowds(6, True, 3)},
}


@lru_cache(maxsize=None)
def best_asking_price(base: int, crowds: tuple[int, ...], fish: int = SELLING_TANK) -> tuple[int, float]:
    """The asking price (1 to 2B - 1) with the most money per real day, averaged over the
    crowd sizes (each equally likely); the lowest such price on a tie."""
    best_price, best_income = 0, 0.0
    for price in range(1, 2 * base):
        income = sum(income_per_day(price, base, n, fish) for n in crowds) / len(crowds)
        if income > best_income + 1e-9:
            best_price, best_income = price, income
    return best_price, best_income


def shop_best_price(base: int, ornaments: int, seahorse: bool, advertising: int, tank: int = SELLING_TANK) -> int:
    """The Optimize Prices button's price for a species of base price B (entry + 0x24, which
    already has the Advertising rises): the Breeding Guide's best per day for the shop as it is,
    its ornaments, Golden Seahorse and Advertising level, with a full selling tank of `tank`
    adults (21, or 30 with Bigger tanks; the crowd counts at most 21 of them)."""
    return best_asking_price(base, shop_crowds(ornaments, seahorse, advertising, tank), tank)[0]


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
    """1 Common, 2 Unusual, 3 Rare (TIER_NAMES): the game's lists (0x41DF99), the DS genes by the same
    rule on their DS index (DLL gene_tier)."""
    d = ds_index(gene)
    if d % 2:
        return 3
    return 2 if d % 4 == 2 else 1


def gene_up(gene: int) -> int:
    return DS_FIRST if gene == PC_LAST else gene + 1


def gene_down(gene: int) -> int:
    return PC_LAST if gene == DS_FIRST else gene - 1


def egg_sources(kind: str, gene: int, extras: bool) -> list[tuple[str, int, float]]:
    """(egg, price, chance per baby) for every egg that can hatch a baby with this body (fin)."""
    out = [(name, price, egg_chance(n, mul, add, gene)) for name, price, n, mul, add in STORE_EGGS]
    if extras:
        name, price, n = EXOTIC_EGGS
        out.append((name, price, egg_chance(n, 1, DS_FIRST, gene)))
    return [e for e in out if e[2] > 0]


def starter_gives(kind: str, gene: int) -> bool:
    slot = 0 if kind == "body" else 1
    return any(gene in baby[slot] for baby in STARTER_BABIES)


def chemical_sources(gene: int, extras: bool) -> list[tuple[int, float]]:
    """(gene before, chance its step lands on `gene`) for one Unknown Chemical step."""
    genes = PC_GENES + (DS_GENES if extras else ())
    return [(g, p) for g in genes for new, p in chemical_steps(g, extras) if new == gene]


def breeding_sums(gene: int) -> tuple[int, ...]:
    """The PC parent totals whose rounded-down average is `gene` (0x41FAAB)."""
    return tuple(s for s in (2 * gene, 2 * gene + 1) if s <= 2 * PC_LAST)


def named_pairs(pairs, kind: str, name, plural: str) -> list[str]:
    """Parent pairs of parts, (a, b, chance), by name, one line per first parent ("Shark with
    Fatfish, Snooper (50%)"); pairs with a part `name` hides are counted, never named."""
    groups: dict[str, list[str]] = {}
    hidden = 0
    for a, b, p in pairs:
        na, nb = name(kind, a), name(kind, b)
        if na is None or nb is None:
            hidden += 1
            continue
        groups.setdefault(na, []).append(nb + ("" if p >= 1 else f" ({_pct(p)})"))
    lines = [f"  {a} with {', '.join(bs)}" for a, bs in groups.items()]
    if hidden:
        lines.append(f"  and {hidden} pair{'s' if hidden != 1 else ''} with undiscovered {plural}")
    return lines


def named_list(items, kind: str, name, plural: str, text) -> str:
    """`text(name, chance)` for each (part, chance) the namer shows, then a count of the others."""
    shown, hidden = [], 0
    for g, p in items:
        n = name(kind, g)
        if n is None:
            hidden += 1
        else:
            shown.append(text(n, p))
    if hidden:
        shown.append(f"{hidden} undiscovered " + (plural if hidden != 1 else plural[:-1].replace("ie", "y")))
    return "; ".join(shown)


def how_text(kind: str, gene: int, extras: bool, combos, name=None) -> str:
    """How a body (fin) is first obtained, each route with its exact odds from the game's code
    (and, for the DS genes, the DS Fish and DS Store DLLs' source), by the game's names only:
    the parent pairs, the parts the Unknown Chemical changes into it. `name(kind, gene)` gives
    a part's name, or None to leave it out (spoilers off)."""
    if name is None:
        name = _part_name
    noun = "body" if kind == "body" else "fin"
    nouns = "bodies" if kind == "body" else "fins"
    lines = []
    eggs = egg_sources(kind, gene, extras)
    if eggs:
        lines.append("Eggs: " + "; ".join(
            f"{egg} (${price}), {_pct(p)} of the babies" + (" (with DS Store Items)" if egg == EXOTIC_EGGS[0] else "")
            for egg, price, p in eggs) + ".")
    elif not is_ds(gene):
        lines.append("No egg lays it.")
    if starter_gives(kind, gene):
        lines.append("The starter eggs of a new game.")
    pairs = named_pairs(combos, kind, name, nouns)
    if pairs:
        rule = (f"the baby's {noun} is halfway between its parents' {nouns} in the game's list, the earlier one "
                "when two are in the middle")
        if extras:
            rule += (f"; with a DS parent, two {nouns} with no single middle one give either middle {noun} "
                     "(the chance is shown)")
        lines.append(f"Breeding ({rule}); these parent {nouns} give it:")
        lines.extend(pairs)
        if is_ds(gene):
            lines.append("Never from two PC parents.")
    chem = chemical_sources(gene, extras)
    if chem:
        lines.append(f"Unknown Chemical (${UNKNOWN_CHEMICAL_PRICE}): each live fish in the tank changes on "
                     f"{_pct(P_CHEMICAL)} a dose, its body on {_pct(P_BODY)} (else its fin), to the next {noun} "
                     "along either way; it becomes this one from "
                     + named_list(chem, kind, name, nouns,
                                  lambda n, p: f"a {n} {noun}" + (" always" if p >= 1 else f" on {_pct(p)}")) + ".")
    lines.append(f"The Magic Fish of Mutation (Wasp Grouper) in the mother's tank: {_pct(P_MUTATE)} a litter "
                 "the father's body or fin first changes to the next one along (the Breeding Calculator's "
                 "\"Max effects, with Wasp Grouper\").")
    return "\n".join(lines)


def flat(text: str) -> str:
    """A how text on one line, for a sheet cell."""
    import re
    text = text.replace(":\n  ", ": ").replace("\n  ", "; ")
    return re.sub(r"(?<=[.])\n", " ", text).replace("\n", ". ")


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
            kind: [Part(kind, g, _part_name(kind, g), is_ds(g), flat(self.how(kind, g))) for g in self.genes]
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

    def how(self, kind: str, index: int, name=None) -> str:
        """How a part is first obtained, one route a line; `name(kind, index)` gives the names
        shown (None leaves a part out, counted)."""
        return how_text(kind, index, self.extras, self.part_combos(kind, index), name)

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
        if effects != "max_mutation":            # only the Wasp Grouper steps the father
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
        if effects == "max_mutation":
            fathers |= {gene_up(father_gene), gene_down(father_gene), father_gene + 1, father_gene - 1}
        for g in fathers:
            if g in self.genes:
                lo, hi, _coin = self._gene_child(mother_gene, g)
                if target in (lo, hi):
                    return True
        return False

    def ways_to_breed(self, key: tuple[int, int], effects: str, limit: int = 20, allowed=None):
        """Parent pairs (mother, father, odds) that can give `key`, best odds first, cut to
        `limit`. With `allowed`, only parents in it are used, before ranking and cutting."""
        tb, tf = key
        body_pairs = [(x, y) for x in self.genes for y in self.genes if self._could_give(x, y, tb, effects)]
        fin_pairs = [(x, y) for x in self.genes for y in self.genes if self._could_give(x, y, tf, effects)]
        best: dict[frozenset, tuple[float, tuple[int, int], tuple[int, int]]] = {}
        for mb, fb in body_pairs:
            for mf, ff in fin_pairs:
                mother, father = (mb, mf), (fb, ff)
                if allowed is not None and (mother not in allowed or father not in allowed):
                    continue
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

    def plan(self, have, want: tuple[int, int], effects: str, allowed=None) -> list[dict]:
        """The shortest chain from `have` to `want`. With `allowed`, every species the chain
        breeds is in it (the spoiler-free planner uses only discovered species)."""
        want = tuple(want)
        owned = {tuple(k) for k in have if tuple(k) in self._by_key}
        if want in owned or not owned or want not in self._by_key:
            return []
        if allowed is not None:
            allowed = {tuple(k) for k in allowed}
            if want not in allowed:
                return []
        order = sorted(owned)
        frontier = set(owned)
        found: dict[tuple[int, int], tuple[float, tuple, tuple]] = {}
        cost = {k: 0 for k in owned}           # breeding steps needed to have each species
        ordered = effects == "max_mutation"    # only then does which parent is the father matter
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
                        if child in owned or (allowed is not None and child not in allowed):
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
        # The Wasp Grouper changes no price: the sale roll (0x424240) and the base prices
        # (0x418B10, Advertising 0x420A6B) never read it, so "max_mutation" prices are "max"'s.
        effects = "max" if effects == "max_mutation" else effects
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

    # The three effects choices: (value, label). "max" is every other effect at its best with no
    # mutation; "max_mutation" adds the Wasp Grouper.
    effects_choices = (("none", "0 effects"), ("max", "Max effects, without"),
                       ("max_mutation", "Max effects, with Wasp Grouper"))
    mutation_name = "Wasp Grouper"

    def effects_text(self, effects: str) -> list[str]:
        """What an effects choice assumes, in words."""
        if effects == "none":
            return ["No magic fish, research or ornaments: Advertising level 1 and nobody browsing; "
                    "each baby's body and fin are halfway between its parents'."]
        out = []
        if effects == "max_mutation":
            out.append("Breeding: a live adult Magic Fish of Mutation (Wasp Grouper) in the mother's tank: "
                       f"{100 * P_MUTATE:.2f}% per litter the father's body or fin first changes to the next one "
                       "along before the babies are made.")
        else:
            out.append("Breeding: no Magic Fish of Mutation (Wasp Grouper), so no mutation chance; each baby's "
                       "body and fin are halfway between its parents'.")
        return out + self._max_rest()

    def effects_max(self) -> list[str]:
        return self.effects_text("max_mutation")

    def _max_rest(self) -> list[str]:
        return [
            "The Magic Fish and Plant of Fertility add babies (up to 3 a litter) but do not change the odds "
            "of each baby.",
            "Prices: Advertising research levels 2 and 3 (every base price + 1/10, then + 1/7); the Wasp "
            "Grouper changes no price.",
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
