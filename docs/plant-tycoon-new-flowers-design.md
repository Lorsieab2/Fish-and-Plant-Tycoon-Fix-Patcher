# New flowers in PC Plant Tycoon: design

Status: design. The site inventory behind it (every place the game assumes
flower genes 1-23, with bytes and hook ranges) is summarized in "Hooks"
below; the full table goes into docs/plant-tycoon-new-flowers-technical-map.md
when the DLL is built.

## What the player gets

Fourteen flower heads that ship in the game's art but no flower gene uses
become flower genes 24-37. With the 23 foliages that is 322 new species
(851 in all, up from 529). Every new flower is the rarest class (tier 4).

| Gene | Name | Art (sheet, first of its 3 views) | Looks like |
|---|---|---|---|
| 24 | Nightingale | flowers56x56, cell 6 | blue rose |
| 25 | Rosetta | flowers56x56, cell 33 | pink rose |
| 26 | Lilac | flowers56x56, cell 24 | lilac star |
| 27 | Veronica | flowers56x56, cell 27 | blue-white star |
| 28 | Violetta | flowers56x56, cell 54 | purple violet |
| 29 | Stella | flowers56x56, cell 51 | yellow star |
| 30 | Forget-me-not | flowers56x56, cell 39 | small teal flower |
| 31 | Anagallis | flowers56x56, cell 42 | small red flower |
| 32 | Buttercup | flowers56x56, cell 48 | small yellow flower |
| 33 | Cerulean | flowers64x64, cell 12 | cyan orchid |
| 34 | Phalaena | flowers64x64, cell 27 | white-purple orchid |
| 35 | Mirabilis | flowers64x64, cell 33 (new) | trumpet, recoloured golden yellow, short fading tube, no bulb |
| 36 | Indigoberry | fruit, cell 6 | blueberries |
| 37 | Prunus | fruit, cell 15 | purple plum |

The names are the owner's. A species is named like the game's own: the
flower name, then the foliage noun ("Rosetta Fern"). Mirabilis's art was magenta like the
game's Jalapa, so it is recoloured golden yellow and copied into the 64x64
sheet's empty cells 33-35 (`scripts/build_new_flowers_assets.py`, which
ships the stock sheet and mask with those three cells filled). The owner
picked its look in game: a third of the trumpet's tube, fading out, with no
green bulb, anchored halfway between the bell's centre and the tube's end
(offsets 0, -12 in the flower record).

## How they are obtained (the user's decisions)

- **Mutation Liquid.** Its flower step (+1 or -1, 50.00% each) now runs over
  1..37: a Tilia (23) can step up into gene 24, and the new end is 37,
  which bounces back to 36. The odds are unchanged.
- **Tier-4 seeds.** A fourth seed packet tier in the store, beside Common,
  Endangered and Extinct (the owner approved these):
  - $5000 per seed (Extinct is $2000);
  - 3 seeds, rerolled every in-game day with the others;
  - foliage: any of the 23, equally likely;
  - flower: any of 24-37, equally likely.
- **Breeding** (decided, user: the same approach as the DS fish): stock x
  stock keeps the game's rule, the parents' average rounded up. With a
  new-flower parent the average's odd sums are rounded up or down at random,
  one roll per pollination, as the DS breeds its fish; the seed's class
  (packet art) and trash value follow the flower it lands on. Two new-flower
  parents give new-flower seeds, a pair always breeds true, and a mixed pair
  can land between. The roll lives in this DLL's hook of the pollination's tail
  (`0x4241B4`), so it applies with "Add unused flowers" alone; it then
  passes the pot on to "Store Upgrades and Items.dll" (events version 2) for the
  Legendary seed art and the formula's held-back seeds.

## Rules for the new species

- **Class D (tier 4)** comes for free: the game makes any gene above 17
  class D. So, as with the Extinct flowers 18-23:
  - health per age unit -10 / -5 / +1 on Common / Bio-organic / Isola soil;
  - infestation 200 / 100 / 50 per 10000 by water;
  - seeds worth $10;
  - the seed art follows the foliage (no new seed art).
- **Value V** = foliage base + flower add, as for every species. Flower adds
  for the new genes (between the Extinct flowers' 26-64 and the top
  override): Nightingale and Rosetta 60; Lilac, Veronica, Violetta and Stella 45;
  Forget-me-not, Anagallis and Buttercup 35; Cerulean and Phalaena 70;
  Mirabilis 55; Indigoberry and Prunus 50.
- **Asking price P** at a new game: V plus or minus Random(V/2), the same
  rule as every other species; and x1.75 with the Flower of Knowledge.
- **Magic plants:** none of the new species is magic.

## How it is built

The same design as the DS Fish mod:
- a companion DLL ("Unused Flowers.dll") loaded by a startup loader the
  patcher appends to Plant Tycoon.exe (`src/ds_fish_loader.py`, PLANT
  profile);
- the DLL checks every site it changes and installs all of them or none;
- saves keep their stock layout. Each save slot's per-species data for the
  322 new species (asking price, discovered flag) and the three tier-4
  seeds go in "Plant Tycoon Fix Patcher Data\New Flowers <slot>.dat" beside
  the saves.

### Hooks (from the site inventory)

1. **Flower art lookup `0x42D2D0`.** Returns DLL records for 24-37, which
   point at the existing sheets 81/82/83 and their masks. This also fixes a
   crash: Bio-organic Plant Food, the Fertilizer Bomb and Mutation Liquid's
   foliage step dereference the lookup's NULL at `0x42DDB0`.
2. **Draw and flowering bounds.** `0x42D9D2` and `0x42E394` go from 23 to
   37.
3. **Asking price P.** Ten index sites are redirected to the DLL's table for
   genes 24-37: the info panel, the "Set species price" dialog (its OK,
   + and - buttons write), the sale payout and statistic, the nursery tag,
   the buy roll and the sold ticker.
4. **Value V.** The buy roll's five index sites.
5. **Visitor comments.** The combined V and P read at `0x439A1F`.
6. **Names.** The info panel's name read at `0x4286E2`; the DLL builds the
   322 names.
7. **Discovered.** The writes at `0x426F0B` (Mutation Liquid) and `0x42E2BB`
   (age 24). Stock code would mark other species and overwrite statistics.
8. **"Species Discovered" statistic** `0x44C5A1`: counts the new species
   too.
9. **Price setup `0x41DBD0`** (new game, Flower of Knowledge) and **new game
   `0x41EF30`**: price and reset the new species.
10. **Save `0x41D120`, load `0x41EE00`, delete `0x41D1F0`:** the sidecar.
11. **Mutation Liquid's flower bounce** `0x42FACE` / `0x42FAD5`: 23 becomes
    37, 22 becomes 36.
12. **Tier-4 seeds:** built as the Legendary Seeds of the Add new store upgrades and items
    setting (`docs/plant-tycoon-upgrades-design.md`), which this DLL loads.

Only Mirabilis needs new art (its recolour); the other flower heads are
cells of the game's own flower sheets, and seed art depends only on the
foliage and the class.
