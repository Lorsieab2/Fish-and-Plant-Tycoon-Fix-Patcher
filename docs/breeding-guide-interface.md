# Breeding Guide: the model interface

Both games implement the same model, so one GUI (`src/breeding_guide.py`) shows either:

- `src/breeding_fish.py` (Fish Tycoon);
- `src/breeding_plant.py` (Plant Tycoon).

Every fact must come from the game's own code, proven by emulation on the vanilla executable with the
repo's emulator tooling (`tests/store_emulator.py` and friends), or from the patcher's own DLL source. Never
infer.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Part:                      # Fish: a body or a fin; Plant: a foliage or a flower
    kind: str                    # "body" / "fin" (Fish), "foliage" / "flower" (Plant)
    index: int                   # the game's own index
    name: str                    # the game's own name (the exe's strings)
    patcher: bool                # added by a patcher setting (DS Exclusive Fish / Unused Flowers)
    how: str                     # how this part is first obtained, in words (store, egg, chemical, mutation...)

@dataclass(frozen=True)
class Species:
    key: tuple[int, int]         # (body, fin) / (foliage, flower)
    name: str                    # the game's own species name
    parts: tuple[Part, Part]
    patcher: bool
    rarity: str                  # the rarer part's rarity, in the game's words (Fish: Common / Unusual /
                                 # Rare; Plant: Common / Endangered / Extinct seed packets, Legendary)
    value: int                   # the game's base value V

@dataclass(frozen=True)
class Prices:
    best_per_day: int            # the asking price that earns the most money per (real) day
    best_per_day_income: float   # the money per day at that price
    highest_selling: int         # the highest asking price a customer still accepts
    note: str                    # what was assumed (customers per day, speed...)

class Model:
    game: str                                    # "fish" / "plant"
    def parts(self, kind: str) -> list[Part]: ...
    def species(self) -> list[Species]: ...       # every species, the patcher ones only when `extras` is on
    def children(self, a: tuple[int, int], b: tuple[int, int], effects: str) -> list[tuple[tuple[int, int], float]]:
        """Every child two parents can give, with its probability (sums to 1), by the game's rule.
        `effects` is "none" (no effects), "max" (every other effect at its best, no mutation
        chance) or "max_mutation" (max plus the mutation: Fish, a Wasp Grouper in the mother's
        tank; Plant, the seed after one Mutation Liquid dose)."""
    def ways_to_breed(self, key: tuple[int, int], effects: str, limit: int = 20,
                      allowed: set[tuple[int, int]] | None = None) -> list[tuple[tuple[int, int], tuple[int, int], float]]:
        """Parent pairs that can give `key`, best odds first, cut to `limit`. With `allowed`, only
        parents in it are used, filtered before ranking and cutting (the spoiler-free view)."""
    def plan(self, have: list[tuple[int, int]], want: tuple[int, int], effects: str,
             allowed: set[tuple[int, int]] | None = None) -> list[dict]:
        """The shortest breeding chain from the species in `have` to `want`: steps of
        {parents: (a, b), child: key, odds: float}; [] when impossible. With `allowed`, every
        species the chain makes is in it (the spoiler-free planner: discovered species only)."""
    def prices(self, key: tuple[int, int], effects: str) -> Prices:
        """No mutation changes a price, so "max_mutation" gives the "max" prices."""
    effects_choices: tuple[tuple[str, str], ...]  # ("none", "0 effects"), ("max", "Max effects, without"),
                                                  # ("max_mutation", "Max effects, with Wasp Grouper" / "... Mutation Liquid")
    def effects_text(self, effects: str) -> list[str]:
        """What an effects choice assumes, in words."""
    def effects_max(self) -> list[str]:
        """effects_text("max_mutation")."""
    def discovered(self, save_folder, slot: int) -> set[tuple[int, int]]:
        """The species this save has discovered: read-only, never writes the save."""

def load(game_folder_or_exe, extras: bool) -> Model: ...
```

`Part`, `Species` and `Prices` are defined once, in `src/breeding_guide.py`;
both models import them from there.

Optional, used by the window when a model has them: `kinds` (the part tabs'
order), `parent_labels`, `part_label(kind)`, `part_rarity(part)`,
`part_combos(kind, index)` (the pairs of parts that give a part, as
`(a, b, chance)`), `species_note(key)`. A `plan()` step may carry `"via"`:
`"pollination"`, or `"Mutation Liquid"` with parents `(a, a)` (Plant Tycoon),
shown as "Mutation Liquid on a".
