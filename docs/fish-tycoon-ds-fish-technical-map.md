# DS Fish mod: Fish Tycoon gene map

Reverse-engineering notes for adding the Nintendo DS exclusive fish to the LDW
PC build of Fish Tycoon (`Fish Tycoon.exe`, 385,024 bytes, the build the Fix
Patcher pins). File offset equals VA minus `0x400000` for `.text`, `.rdata`
and `.data`.

## Genes

A fish is two genes, both `0..20` in vanilla:

| Gene | Fish record | State-relative (tank fish) | 0 (rare end) | 20 (common end) |
|---|---|---|---|---|
| Body | `+0x4C` | `+0x3DC` | Shark | Spotanus |
| Fin  | `+0x50` | `+0x3E0` | Silky | Twin-Fin |

Tank fish record: `state + 0x390 + tank*0x51EC + slot*0x288`, 21 slots per
tank (so `0x15` loops over slots are not gene loops). Other record fields used
below: `+0x0C` age (adult at 20), `+0x10` pregnancy timer, `+0x14/+0x18` mate
body/fin, `+0x1C..+0x38` four grandparent pairs, `+0x3C` health.

Special value: **body 22 = Golden Seahorse** (checked at `0x4121F4`,
`0x41404D`, `0x41581B`, `0x41F3C4`, `0x41FF95`, `0x42043F`, `0x4282C1`,
`0x439FB7`). Body 21 is unused, but sprite slot `38+3*21 = 101` is
`seahorse_body_Grid.png`.

Full name order (exe index):

- Bodies 0-20: Shark, Catfish, Arrowfish, Snout, Fatfish, Snooper, Goldshark,
  Fire-Arrow, Fruitfish, Flashfish, Goldbulb, Comet, Stickfish, Grouper,
  Leaffish, Carp, Beta, Pigmy, Bananafish, Quicksilver, Spotanus
- Fins 0-20: Silky, Tiger, Hornet, Fanned, Pink, Snubbed, Wasp, Canary,
  Orange, Oriental, Golden, Crimson, Spined, Stubby, Speckled, Razorback,
  Greenfin, Great-Sail, Flagged, Finless, Twin-Fin

The DS list is the same ladder reversed (DS index = 27 - exe index) with seven
more entries past the common end: bodies Clownfish, Discus, Bicolor, Trigger,
Surgeonfish, Tang, Idle; fins Small Fin, Roundy, Angel, Clown, Yellow, Blue,
Moorish. Exe numbering: **23-29** for both, skipping 21 (seahorse
sprite slot) and 22 (seahorse body).

## Unknown Chemical (the mutation item)

Shared chemical handler; item type at `state+0x2F0` selects the effect
(`2` vitamins at `0x42120A`, `3` growth hormone at `0x4210F2`, `4` Unknown
Chemical at `0x420E93`). Dose counter is `state+0x2F8`.

Mutation loop `0x420EA0`-`0x42103D`, for each live fish in the current tank
whose body is not 22:

1. `Random(100) <= 25` or skip (26%).
2. `Random(100) <= 49` picks body (`+0x4C`), else fin (`+0x50`).
3. At 20: always `-1`. Otherwise `Random(100) <= 49` gives `+1`, else `-1`
   unless the value is 0, which gives `+1`.
4. Rebuilds the seven sprite objects (`0x415DF0`) from the new genes.

Bounds live at `0x420EFE` (body `cmp eax,0x14`), `0x420F12` (body zero test),
`0x420F2A` (fin `cmp eax,0x14`), `0x420F3E` (fin zero test). For the mod the
step from 20 goes to 23 and from 23 back to 20, and 29 becomes the new end;
odds unchanged.

## Breeding

Baby creation `0x41FA30(body, fin, mateBody, mateFin, 4 grandparent pairs,
age, kind)`:

- `0x41FAAB`: baby body = `(body + mateBody) / 2`, baby fin =
  `(fin + mateFin) / 2` (C division, both non-negative, so floor).
- Callers: hatch `0x4202CF`, `0x42034E`, `0x4203CA` (1-3 babies); eggs and
  store at `0x41FE17`, `0x41FE3A`, `0x42142D`, `0x421500`, `0x4215D1`,
  `0x421A20`. Egg and store genes are `Random(6)*4` (0,4,...,20) with
  (20,16) remapped, so they can never produce a DS gene.
- `0x41FC0F`: tutorial goal `0x17` fires when the baby has an odd gene or one
  of 2/6/10/14/18 (a gene eggs cannot give). DS genes 24 and 28 would not
  trigger it.

Hatch-time mate mutation `0x42014C`-`0x42025B`: if the tank holds an adult of
magic fish 5 (`0x41DE90(5)` = body 13, fin 6, Grouper Wasp), 16% chance to
step the stored mate body or fin by +/-1, then clamp both to `0..20` at
`0x42021D` and `0x420245`. Vanilla bug: the fin branch tests the *body* value
for its 0/20 bounce (`0x4201CC`, `0x4201E8`); the clamp hides it. Decided:
this mutation may also reach DS genes, so its bounds and clamps get the same
20 <-> 23 step and 29 end as the Unknown Chemical.

**Breeding rule (as built).** The DS game's own rule, traced by the DS
session (arm9.bin combine function `0x02034B54`, birth `0x02035294`): baby
gene = `(a+b)/2` on DS indices, an odd sum rounded up or down at random, one
roll per litter; body and fin alike, no table, so same x same always breeds
true. The DLL applies it whenever a parent has a DS gene (exe 23-29 mapped to
DS 21-27 and back); PC x PC keeps the PC's floor average, so two PC parents
never give a DS gene. `tests/test_ds_fish_logic.py` checks every pair against
the DS session's `breeding_body.csv` / `breeding_fin.csv`. Not adopted, by
the user's rules: DS eggs giving gene 24 or odd genes, and the DS Mutation
fish's per-baby +/-1 roll (the PC's 16% parent step is kept). The fan-made
breeding spreadsheet the work started from is superseded: it was the average
with inconsistent rounding and two impossible cells (Bicolor x Bicolor,
Pigmy x Pigmy).

## Magic fish

`0x41DE90(k, tank)`: true if the tank has an adult whose (body, fin) equals
magic fish k: 0 (20,16), 1 (14,14), 2 (11,11) Crimson Comet, 3 (10,9),
4 (5,8), 5 (13,6), 6 (7,7). Discovery decals map pairs at `0x413FE0`. All are
fixed PC coordinates; DS genes do not collide.

## Species table

`state + 0x14B40 + (body*31 + fin)*40`, rows of 31 entries (`0x4D8` bytes),
21 rows used, columns 21-30 unused:

| Entry offset | Meaning |
|---|---|
| `+0x00` | name, built by `0x419600` as fin prefix + body |
| `+0x20` | player price; `-1` = undiscovered |
| `+0x24` | base price, set by `0x418B10` (fin base + body bonus, 21x21 switches, plus fixed overrides) |

DS fins 23-29 fit in the spare columns; DS body rows do not (row 21 would
start at `0x1B0F8`, which is other state). Index sites (`body*31+fin`):
`0x413595`, `0x4135C8`, `0x4135F9`, `0x413729`, `0x418CE6`, `0x4192B5`-
`0x419407` (nine), `0x4197C7`, `0x41E2D9` (discover), `0x42071B`,
`0x423701`, `0x423722`, `0x424034`, `0x42405E`, `0x424298`-`0x4243FB` (six),
`0x425314`, `0x425BF7`-`0x425DC6` (five).

Whole-table sweeps, hardcoded 21x21: discovered count `0x419240` (shown via
`%d`, no 441 constant anywhere), price inflation `0x420A90` and `0x420AF0`
(`cmp eax,0x65B8` = 21 rows), name build `0x419600`, price init `0x418B10`.

Plan (following the Virtual Villagers rule of no new save-record fields):
PC body x DS fin entries go in the spare columns 23-29 of the existing rows,
which keeps the save layout unchanged. DS body rows (7 x 31 entries) live in
the companion's own table and persist in a sidecar file keyed to the save
slot. The index sites and sweeps are redirected to a lookup that picks the
right table.

## Prices

Source: the Nintendo DS extraction session, from the USA ROM `arm9.bin`
(value function `0x0201A10C`, body table file `0x3D6C8`, fin table file
`0x3D6E4`; full matrix in `Downloads\Current Modded LDW Games and Dumps\Game Dumps\Fish Tycoon (USA) - Dump\text\species_values.csv`).
The DS uses the same index order as the PC (0 = Shark / Silky), with the new
types at DS 21-27, pairs Clownfish/Small Fin, Discus/Roundy, Bicolor/Angel,
Trigger/Clown, Surgeonfish/Yellow, Tang/Blue, Idle/Moorish.

DS value = `body[b] + fin[f]`, plus 10 when `b == f` and `b > 20`, plus 13
fixed overrides.

| DS idx | Body | value | Fin | value |
|---|---|---|---|---|
| 21 | Clownfish | 10 | Small Fin | 10 |
| 22 | Discus | 4 | Roundy | 5 |
| 23 | Bicolor | 9 | Angel | 11 |
| 24 | Trigger | 6 | Clown | 3 |
| 25 | Surgeonfish | 10 | Yellow | 15 |
| 26 | Tang | 8 | Blue | 7 |
| 27 | Idle | 17 | Moorish | 15 |

PC base prices, emulated from `0x418B10` (unicorn), match the DS formula for
428 of 441 PC species. The 13 that differ are the fixed overrides: the 7 magic
fish plus Catfish Hornet, Arrowfish Wasp, Goldshark Speckled, Fruitfish
Orange, Goldbulb Golden and Pigmy Oriental. PC sets them higher (up to 190)
because the DS stores prices in one byte. No override involves a DS body or
fin, so every DS species uses the DS formula unchanged, and PC species keep
their PC prices. The 343 species with a DS body or fin range from 5
(Fatfish Clown) to 42 (Idle Moorish, 17 + 15 + 10).

Like the PC, the DS sets a new species' price to this value on discovery, and
customers compare the player's price against it.

## Rarity (environment level)

A gene's tier is fixed by its value: odd = tier 3, 2/6/10/14/18 = tier 2,
0/4/8/12/16/20 = tier 1. A fish's tier is the higher of its body and fin.
Eggs and store fish (`Random(6)*4`) are always tier 1.

Health tick `0x41DF50` (environment level at `state+0x258`, 1-3):

| Fish tier | Env 1 | Env 2 | Env 3 |
|---|---|---|---|
| 1 | +1 | +3 | +5 |
| 2 | -1 | +1 | +3 |
| 3 | -19 | -6 | 0 |

Then random +1s from tank items and difficulty, clamped to 0-100. Disease
odds `0x41E120` use the body's tier the same way.

The tier tests are hardcoded lists, not `% 4` (`0x41DF99`-`0x41E00F`,
`0x41E157`-`0x41E18A`, and the tutorial goal at `0x41FC0F`). An even gene
outside the lists falls to `0x41E083`, which uses an uninitialised stack value
as the health change. So the DLL must give DS genes an explicit tier.

DS native tiers follow the same rule on DS indices 21-27 (and match the
colours in the user's spreadsheet):

| DS idx | Body | Fin | Tier |
|---|---|---|---|
| 21 | Clownfish | Small Fin | 3 |
| 22 | Discus | Roundy | 2 |
| 23 | Bicolor | Angel | 3 |
| 24 | Trigger | Clown | 1 |
| 25 | Surgeonfish | Yellow | 3 |
| 26 | Tang | Blue | 2 |
| 27 | Idle | Moorish | 3 |

With exe numbering 23-29 (DS idx + 2), parity is kept but `% 4` is not, so
the tier comes from a DLL table keyed on the gene.

## Sprites

Resource table `0x4552F0`, 197 entries of `0x24` bytes `{id, filename, cols,
rows, ...}`, bounded by `cmp ...,0xC4` in `0x41BB05`, `0x41BBD5`,
`0x41BCB4`, `0x41BD25`. Fish parts are entries `38+3g` (body 7x3),
`39+3g` (bot fin 13x2), `40+3g` (top fin 13x2).

- Sprite ids are `group*100 + frame`: body `10001+100g`, top `10031+100f`,
  bottom `10061+100f` (`0x415DF0`). Decoded to a table entry by `0x4122A0`
  (`lea edx,[eax+eax*2+0x26]`), no bounds check.
- `FISH_teen_Grid.png` is 18x21: one row per body (`0x41472D`). Each row is
  that body's 18 adult body frames shrunk to 44x20 (checked for bodies 0 and
  13), so DS teen rows are generated from the new adult sheets.
- Art decision (user): generate the PC turn frames from the DS sprites.
  Scale 110/64, then squash each frame to the PC widths (frames 0-5 100%
  down to 81%, 6-11 the same mirrored, 12-17 down to 52% head-on). Use the
  regenerated `fin_offsets.csv` (left-facing `top_dx`/`bottom_dx`; the
  `rom_` columns are for right-facing art). Tall DS fish need cells larger
  than 110x50. The DS 3D models are one shared mesh with low-resolution
  texture atlases, so rendering them would not be sharper.
- `FISH_adult_dead_Grid.png` (7x3, sprite 37) holds one dead adult per
  body: greyed, upright, facing right. The DS dead art (`dead_bodies\`,
  64x32, greyed, facing left, fins included) is scaled 110/64 and flipped to
  fill 7 new cells. `FISH_teen_dead_Grid.png` (4x1) is shared.
- `FISH_baby_Grid.png` (18x1) is one shared sheet for every fish; DS fish use
  it unchanged.
- Per-fin alpha switch `0x411100` and per-body fin anchor points `0x4111E0`
  (21 cases each, default case for anything else).

New entries need a bigger table (new section), the four bounds raised, and
`0x4122A0` taught to route genes 23-29 to the new entries.

### Loading and drawing (traced for the build)

- Image loader `0x409B00`: `fopen("\images\<name>")` first, and a file on
  disk wins over `ft.dat` (`IMG_Load` at `0x409C64`). The new sheets ship in
  the game's `Images` folder and need no loader hook. Sprite-table entries
  load lazily on first use (`0x41BBB0`, cached at entry `+0x20`), so the DLL's
  longer copy of the table only needs the four `0xC4` bounds and eight
  `0x4552F0` references redirected.
- Fish draw `0x4145F0`: fins are drawn first (behind), then the body
  (`0x4149DA`). The anchor fields are on the sprite object: top `+0x68/+0x6C`,
  bottom `+0x70/+0x74`, alpha `+0x60`; ids are body `+0x54`, top `+0x58`,
  bottom `+0x5C`. The three cases (table `0x414CD8`):
  - facing left (frames 0-5): fin at body + anchor;
  - mirrored (6-11): body + 50 - anchor;
  - head-on (12-17, `0x4148EA`): body + 44 + c - anchor, with c = 0, -13,
    -13, +10, +10, +10, and the bottom fin 4 px higher.
- Teen fish (sprite `0x24`, row = body) and dead fish (sprite `0x25` adult,
  `0x23` teen) are single sprites: no separate fins are drawn.
- Anchors are set in `0x415DF0(sprite, body, fin)`, which calls the alpha
  switch `0x411100(fin)` and the anchor switch `0x4111E0(body)`. The DLL
  hooks it, and for a pair with a DS gene writes the pair anchor from
  `data/ds_fish_layout.json` (built from the DS offset table). For those
  pairs it also replaces the head-on x (`0x41492A` top, `0x4149A6` bottom)
  so each fin keeps its frame-0 fraction along the body. Checked by
  rendering: every DS-gene pair matches the DS game's own assembly on frame 0
  and stays attached through the turn.
- Startup loader: the C runtime calls WinMain (`0x42A350`) at `0x42D7DE`;
  kernel32 imports `GetModuleHandleA` `0x440144`, `GetProcAddress`
  `0x440150`.

## Saves

The save is the raw state: `ldwg` header, then `0x1E3C8` bytes from
`state+8`. The size is checked at `0x4033E3`; allocation is `0x1E510` at
`0x41B09A`; size constants at `0x419164`, `0x419175`, `0x41AF2D`,
`0x41AF54`. Growing the state needs all of these plus a migration path for
saves of the old size. Modded copies already keep their own save folder.
Decided (user, 2026-10-26): separate files. The save layout and size stay
stock. Genes 23-29 are new values in the existing gene fields, and DS species
data goes in a versioned sidecar file per save slot, as the Virtual Villagers
and Virtual Families patchers do.

## Space

`.text` slack `0xD61` bytes from file `0x3F29F`, partly used by the Fix
Patcher's universal-slots payload (from `0x3F2A0`), and `.text` VirtualSize
cannot pass `0x3F000`. Headers end at `0x2B8` of `0x1000`, so a new section
for code, names and the sprite table fits (in the end the DLL holds them, so no section beyond the loader was needed).

## Architecture (Virtual Villagers Fun Patcher model)

Source: Lorsieab2/Virtual-Villagers-Fun-Patcher, `native/vvfp_startup/`,
`native/shared/install_sites.h`, `native/shared/startup_companions.h`,
`native/shared/patcher_files.h`, `scripts/build_vvfp_*.ps1`,
`data/builds.json`, and the companion tests under `tests/`.

- No proxy DLL. The owner rejected proxying SDL_image: a broken proxy stops
  the game from starting.
- The patcher appends one small PE section to the exe and redirects the CRT's
  `call WinMain` to a stub. The stub loads a startup DLL by full path from a
  patcher-files folder beside the exe, calls its export, then enters WinMain.
  This is fail-open: a missing file or export, or a fault, leaves the stock game.
- The companion DLL is C, built with MSVC x86 (`/LD /O2 /MT /W4`, `.def`
  exports, kernel32 only, deterministic). It is committed to the repo,
  pinned by SHA-256 and size, and has rebuild-equals-committed tests.
- Hooks are applied in memory at fixed addresses, all or nothing, after
  checking the exact stock bytes at every site. Code pages are built RW and
  sealed RX, never W+X. A byte mismatch means the feature stays off.
- The DS hooks must account for the Fix Patcher's own exe edits. A site it
  already patches either is avoided or accepts both byte forms.
- New art ships as separate PNGs loaded by the DLL; `ft.dat` is not edited.
- Sidecar data: one file per save slot beside the save, with a version header.
  A file that cannot be read is renamed `.unreadable-N.dat`, never deleted.

The Virtual Families 1 patcher (Lorsieab2/Virtual-Families-1-Fun-Patcher)
follows the same rules with two variations:
- It loads the DLL from a per-frame tick hook instead of a WinMain stub.
- It builds the DLLs at release time instead of committing them.

VF1 also adds a prover script that generates the `*_sites.h` expected-byte
headers from the vanilla exe (`tools/vf1_kids_sites.py`), and unicorn
emulation tests against the real exe (`tests/kids_emu.py`). Its "up to 28
children" expansion (`docs/UP_TO_28_CHILDREN.md`) is the closest precedent
for growing a fixed-size game table. Warning carried over: never
pattern-match on shared constants such as `0x66666667`, which this exe uses
in many places (for example the discovery price at `0x41E317`).

## Assets

`Assets/ft.dat` is an unencrypted ZIP (483 PNG, 32 BMP, plus `__MACOSX`
junk). The mod needs `FISH_23..29_body/bot/top_Grid.png` and a 28-row
`FISH_teen_Grid.png`.
