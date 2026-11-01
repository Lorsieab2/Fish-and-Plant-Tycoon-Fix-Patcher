# Fish Tycoon: Bigger tanks (30 fish)

The setting **Bigger tanks: 30 fish** (`bigger_tanks`, on by default since v1.0.22) raises Tank One, Tank Two and the
selling tank from 21 fish to 30. The isolation tank still holds one fish. It is 29 patch records in
`data/fish_manifest.json` (`tank30_*`, each requiring the setting) plus one .text size record, written by
`scripts/pin_tank_expansion.py`, which also rebuilds the PE checksum record and the pinned hash of every
combination of the byte-patch settings. No DLL is involved.

Earlier builds had this setting at 26 fish (`tank26_*`, 45 records). 30 replaces it: 30 is 10 x 3, so the
loops the compiler unrolled three slots at a time (group D) only change their count, where 26 needed
their stride, their third check and three debug writes changed too. One setting, one size: a player who
had 26 now has 30.

Why there is room: each tank's block in the game's state holds 31 fish records of 0x288 bytes (the tank
constructor 0x41A9A0 builds them), the save copies the whole state, and the game only ever uses slots 0-20.
Slots 21-29 become fish slots; record 30 stays unused. The DS Store Items' animals no longer live in
these records at all (section 6).

Checked by emulation, not yet in the running game: `tests/test_fish_30.py` runs every family of effects
in the game's own code, stock and patched, with the fish in slot 0 and in slot 29, and requires the same
result byte for byte.


Static analysis. The target is the vanilla `Fish Tycoon.exe`, image base 0x400000, file offset = VA - 0x400000.
A record (tank t, slot s) is at state + 0x390 + t*0x51EC + s*0x288. Each tank has 31 records, and all 31 are saved.

## 1. Method

* Every `0x288` stride or `imul ...,0x288` in .text (68 hits) and every `0x51EC`; every caller of the view
  accessors 0x413B30, 0x413B50 and 0x413BD0, of REMOVE_FISH 0x418E20, and of AddFish 0x419C50.
* For each of those functions, every back-edge and its bound.
* All 43 `0x15` immediates in .text, and every `0x14` immediate in the functions that touch records.
* Loops whose stride is a multiple of 0x288 (0x510, 0x798, ...): **six loops unrolled x3** (7 x 3 = 21).
* Every compare against 0x3528 (21 x 0x288) and against any tank-end address: tanks 0..3, offsets relative
  to the tank, to state and to state+8, and field offsets added to the end. Only 0x3528 itself turned up.
* Strings: no "21" or "twenty-one" anywhere. "The tank is full!", "There is no room in any of your tanks
  for the seahorse!" and "One of your tanks is full! ..." need no edit: they follow AddFish's answer.
  The help pages are bitmaps (help1..4_bg.bmp); tip 16 says 20 fish per tank (stock text, not edited).
* Every read of a swimming entry's slot (`+0x44`, or the getter 0x413B50): all 20 go straight into
  `imul ...,0x288` (section 6). Rechecked for this change with capstone.
* The other settings' code (Fix Patcher payloads, DS Fish and DS Store sites, Time Warp): none has a slot
  bound of its own except Time Warp's banked-time loop, which reads the update loop's bound (0x4206B3) and
  now goes to 30.

These matched the search but are not slot limits (checked and rejected):
* 0x41236A and 0x414C6D: animation frame >= 21.
* 0x418CF0, 0x418D62, 0x41981A, 0x41982C, 0x419617, 0x420A94 and 0x420AF4: species tables (21 bodies x 31 fins).
* 0x41D196, 0x422B01, 0x41D865, 0x41D8DB and 0x41EF73: sprite ids and screen coordinates.
* 0x420668 and 0x425535: tutorial ids.
* 0x4210A5: `push 0x15` is a sparkle effect id.
* 0x421362: the item switch.
* 0x427E1B: the seahorse age, 21.
* 0x420407: the tank-3 base, 0xF5C4.
* Every `cmp [rec+0xC],0x14` (adult age), every body check on `[rec+0x4C]`, and the `0x14` body and fin ids.

## 2. The sites (all checked against the vanilla bytes by `tests/test_tank_expansion.py`)

### A. Slot-index bounds, 0x15 -> 0x1E (10 sites)

| site | function | limits |
|---|---|---|
| 0x419C72 | AddFish 0x419C50 | first free slot; every add goes through it (drop, hatch, seahorse, starter fish, eggs) |
| 0x4140C5 | view build 0x413D80 | one swimming entry per live slot |
| 0x415893 | view refresh 0x415460 | same |
| 0x4206B1 | update 0x41FE70, pass 1 (tanks 0..3) | age, food, health, hatch, disease, death, the DS animals' effects |
| 0x4206E0 | update, pass 2 (`[esp+0x18]` down-counter) | adults, breeding, achievements |
| 0x41A90C | reset 0x41A8F0 (tanks 0..2) | REMOVE_FISH on a new game |
| 0x4198F7 | reset 0x4198F0 (tanks 0..3) | clears +0 on a new game |
| 0x41DF20 | magic-fish scan 0x41DE90 | magic fish effects |
| 0x413538 | thoughts 0x413530 | `Random(21)` slot of the selling tank becomes `Random(30)` |
| 0x425567 | tutorial step 0xD | makes the first adult fish in tank 0 or 2 sick |

### B. Byte-offset ends, 0x3528 -> 0x4BF0 (30 x 0x288) (4 sites)

* 0x421043: Unknown Chemical, the tank in use.
* 0x42118E: growth hormone (age +2..6). The Radioactive Growth Hormone (PR #57) reads this loop end
  (0x421190), so it follows.
* 0x42128A: the health item (+6..15, at most 100).
* 0x424495: the sale loop over the selling tank (0x424240).

### C. Sparkles over view ENTRIES, 0x15 -> 0x1F (4 sites)

0x420E24, 0x4210AF, 0x4211FE, 0x4212FD run over the view entry index 0..20; fish are entries 1..F, so the
stock game already misses its 21st fish (a cosmetic stock off-by-one). 0x1F covers entries 0..30, all 30
fish. The item's real effect runs on the records (group B) or on every entry (0x420CD0, no bound).

### D. Loops unrolled x3: 7 passes -> 10 (9 sites)

| loop | what | change |
|---|---|---|
| 0x41E260 (in 0x41DF50, sickness roll) | +6 sickness chance per sick fish in the tank | `mov ecx, 7` -> 10 |
| 0x41FCA8 (0x41FC90, starter eggs) | "any fish in tanks 0/1/2?": 7 eggs if none, else 3 | **code**: `mov ecx, ebp; lea ebx,[ebx]` -> `mov ecx, 0xA; nop x3` (ebp = 7 is also the egg count) |
| 0x41FCE6, 0x41FD26 | the same for tanks 1 and 2 | `mov ecx, 7` -> 10 |
| 0x4230B4 (0x422F10, debug path) | writes rec+4 and rec+8 of every slot | end `cmp eax, 0x3528` -> 0x4BF0 |
| 0x42381F (selling screen) | healthy adults in the selling tank, the "for sale" number | `lea edx, [edi + 7]` -> `+ 0xA` |
| 0x423E85 (0x423E00, selling scene) | adults in the selling tank, for the crowd | `mov ecx, 7` -> 10 |
| 0x423F62, 0x423F82 (same function) | live non-seahorse fish in the selling tank | `mov edx, 7` -> 10; `lea ebx, [edx + 0xF]` -> `+ 0xC` (ebx is body 22 = count + 15, so 10 + 12) |

### E. Selling (owner's rule: the selling tank holds 30, each fish with the stock odds)

* The sale loop (0x424240, once a real-time second while the selling scene is open) tries the adults in
  slot order and stops at the first that sells. Its end is site 0x424495 (group B), so every adult in
  slots 0..29 gets its roll with the stock threshold, and still at most one fish sells a second.
* The crowd: the selling scene counts its adults (0x423E85 loop) for `2 x Advertising x (adults / 3 + ...)`
  customers. At 0x423EEA a jump to 0x43FE00 caps that count at 21, the stock selling tank's most, then
  runs the moved `push 2; call Random` and jumps back to 0x423EF1. So 30 adults bring the stock game's
  largest crowd, never more, and no fish's odds go past the stock game's best.
* The routine sits in the zero slack after .text; `extend_text_virtual_size_for_bigger_tanks` maps it
  (`excludes` the three other records that map the same slack, so exactly one is active).

## 3. Per-slot arrays sized for 21

None. Customers keep a slot index and read the record; thoughts have no array; the sell scene copies from
the record; species, journal and research are 21 bodies x 31 fins plus scalars; the isolation tank is the
same 31-record block (its fish is slot 0, appended after the tank's own fish); the view holds 150 entries
of 0x84 bytes (count at view+0x5DD8; the refresh keeps a stack copy of 0x96). 30 fish + 5 animals + 1
isolation fish = 36 entries.

## 4. Drawing and update cost

The update visits 30 records instead of 21 per tank (the work per fish is unchanged); the view draws up to
36 entries instead of 27. Both were already sized for 150 entries. Swimming space is the stock tank
rectangle; the fish move as before (the mover has no per-count rule). Only the running game can say how
crowded 30 fish look.

## 5. Overlaps

* No byte of a `tank30_` record overlaps another setting's record (test). The nearest is
  `unknown_chemical_remove_runtime_count_reset_*` at 0x4210B7; sparkle_entries_b changes only 0x4210B1.
* The DS Fish and DS Store sites share functions with these but no bytes: SITE_TICK 0x420470, SITE_DEATH
  0x420622, SITE_CUSTOMERS 0x42426F (jumps to 0x42448A, the stock "next slot"), SITE_THOUGHTS 0x41355F,
  SITE_MUTATE_* 0x420EFB / 0x420F27, SITE_EGG_USE 0x421356, SITE_TIER_GOAL 0x41FC0F, and DS Store's
  0x4140D0 / 0x41589E (section 6), which sit after the bound compares 0x4140C5 / 0x415893.
* The crowd routine uses 0x43FE00-0x43FE15 of the slack. Other branches adding code to the slack must
  start after 0x43FE20.

## 6. The DS Store animals

The animals (the Golden Seahorse too, with DS Store Items) used to live in records 26-30. They now have
5 records per tank of their own inside DS Store Items.dll, saved in `Tank Animals <slot>.dat`
(docs/fish-tycoon-ds-store-items-design.md). How the game still draws, moves, feeds, picks up, drops
and trashes them with its own code:

* Every stock use of a swimming entry's slot is `state + 0x390 + tank*0x51EC + slot*0x288` in 32-bit
  arithmetic (the 20 reads listed in section 1, the drop 0x41EFF0, the trash, REMOVE_FISH 0x418E20, the
  info panel 0x41DA40). VIEW_MOVE 0x414F50 only compares a slot with -1. Nothing compares a slot with
  a bound or indexes another array by it.
* So each animal gets the one slot number for which that sum lands on its record in the DLL: with d the
  distance from the tank's records (kept a multiple of 8), slot = (d / 8) x 81^-1 mod 2^29, since
  0x288 = 8 x 81. The number is below 2^29, never -1 and never 0..30.
* The view's build and refresh loops (0x413D80, 0x415460) go on, at their `jl` back to the top (0x4140D0,
  0x41589E), from the last fish slot to the tank's animals, with the loop's own slot and record
  variables set to the animal's. Each animal entry is built by the stock loop body, as when it sat in
  slots 26-30. The bound compares themselves stay the setting's (21 or 30).

## 7. Old saves and turning it off

* A vanilla save's slots 21..29 hold whatever the heap held (zero in every save checked). A save from the
  26-fish build has fish in 21..25 (now ordinary fish slots) and, with DS Store Items, animals in 26..30:
  those move to the animals' own records on the first load (section 6, and the DS Store design doc).
* Without DS Store Items, a Golden Seahorse in a fish slot is a stock fish record and stays one.
* **Turning the setting off** with fish in slots 21..29 keeps them in the save, but they stop updating and
  are not shown until it is on again. The warning says so.

## 8. Python lists

`scripts/pin_tank_expansion.py` TANK_PATCHES gives each record as (name, file offset, expected bytes,
replacement); `crowd_code()` builds the routine. `tests/test_tank_expansion.py` SITES gives each site's
instruction before and after.
