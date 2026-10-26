# Fish Tycoon PC (LDW, `Fish Tycoon.exe`) vs Nintendo DS: magic fish, store items, research

All PC facts below were traced in the vanilla exe (VA given). Anything not traced is
marked **guess** or **not traced**. DS facts are copied from the DS session's brief and
were not re-checked here.

## 0. Tick and scale (read this first)

**PC tick timing (traced).**
- `0x4218D0` (tank-scene update) calls the fish update `0x41FE70` once every **300 s of
  wall-clock time** (`time()` via `0x4020D0` → `_time64` `0x42B122`; next run = now+0x12C).
  `0x41FE70` is also called on entering the tank scene (`0x421AAA`).
- `0x41FE70` adds elapsed wall-clock seconds to each fish's accumulator (record `+0x04`),
  then converts it to **age steps: one step per `60 × speed` seconds**, where speed =
  `state+0x1E168` minutes. The options code sets 5, 10 or 15 (`0x422FD4`-`0x423023`);
  9999 means "time paused" (any value > 100 zeroes the accumulator). The new-game path sets 5 or 10
  (`0x41C2E6`/`0x41C2FF`, `0x421976`).
- The health tick, disease roll, food decrement, starvation and the per-tick magic-fish
  effects run **once per age step** (the loop `0x420468`-`0x420687` walks from the last
  processed age `+0x08` up to the current age `+0x0C`). So one PC tick = one age step =
  **5, 10 or 15 real minutes**, and a fish is adult at age 20.
- Offline catch-up is capped. The accumulator is limited to 259200 s, and then to about 25200 s (7 h)
  depending on speed (`0x41FF1D`-`0x41FF7A`). Quirk: at speed 15, a value over 18000 is
  set to 25200, which raises it.
- Research progress (`0x4208F0`-`0x42098E`) gains 2 points per step and completes at 100,
  so it takes 50 steps.

**Scale.** PC health is 0-100, and each tick applies a signed delta, often large (-19
to +5 from genes alone). The DS subtracts a small "loss" from 0-101 and uses many small
percentage rolls. Per-tick percentages cannot be compared directly unless the DS tick
length is known. Only the direction and structure of each effect are compared.

**PC fish record** (state + 0x390 + tank*0x51EC + slot*0x288): +0x00 last-update time
(non-zero = live), +0x04 time accumulator, +0x08 last processed age, +0x0C age, +0x10
due age of pregnancy, +0x14/+0x18 mate genes, +0x3C health, **+0x40 disease (0 none, 1, 2)**,
**+0x44 food/satiety (0-100)**, +0x4C body, +0x50 fin.

**PC difficulty-like setting `state+0x14`** (0/1/2). Inferred from its uses: 0 = easiest.
The value 0 gives +1 egg, a 31% +1 health per tick and disease odds x0.8, and turns off
contagion. The value 2 gives disease odds x1.5 and processes every skipped Growth Hormone tick. The
meaning of each value is inferred; the option label was not traced.

## 1. PC health tick `0x41DF50` (per fish per step)

1. Gene tier delta by Environment level (`state+0x258`): tier 1 +1/+3/+5, tier 2
   -1/+1/+3, tier 3 -19/-6/0. A tier comes from the hardcoded lists (an even gene outside them uses an
   uninitialised value at `0x41E083`).
2. Temperature Regulator (`+0x12C`): `Random(100) <= 40`, so a 41% chance of +1 (`0x41E08A`).
3. Aeration System (`+0x118`): a 41% chance of +1 (`0x41E0A8`).
4. If `state+0x14 == 0`, a 31% chance of +1 (`0x41E0C3`).
5. If the fish is sick **or** food < 5, a positive total is set to 0. If it is sick, -1 more (`0x41E0DE`).
6. Clamp the result to 0-100.

The caller `0x41FE70` then applies the following in order, for each step:
- **Orange Snooper** +1 (`0x420476`).
- Disease roll `0x41E120` (adults only, `0x420498`).
- **Crimson Comet** cure (`0x4204C4`).
- A sick fish loses its pregnancy (`0x4204FA`).
- Food decrement by Food research (`0x420500`).
- Starvation block (`0x42055B`).
- Clamps.
- Death if health <= 0 (`0x420622`).

**There is no death-save roll** (no Moray Eel and no Environment bonus).

## 2. PC disease `0x41E120` (adult, not already sick)

Rolls `Random(10000) < X`, then sets disease = `Random(2)+1`. X is built in this order:
- Base from the **body** gene tier only and **Food research** level `state+0x244` (not
  Environment!):

  | Body tier | Food L1 | L2 | L3 |
  |---|---|---|---|
  | 1 (0,4..20) | 10 | 5 | 1 |
  | 2 (2,6..18) | 20 | 10 | 3 |
  | 3 (odd) | 30 | 20 | 5 |
  | other value | 2 | 2 | 2 |
- `state+0x14`: 0 gives X -= X/5; 2 gives X += X/2.
- **Plant of Curing** (`+0x190`) **always** halves X. If it is not owned, the **Cleaning Snail** (`+0x140`)
  halves X with 50% (`Random(100) <= 49`). The two never stack (`0x41E21C`).
- Contagion: +6 per sick fish in the same tank, only if `state+0x14 != 0` (`0x41E246`).
- Age > 600 gives +15. The +30 branch for age > 800 is dead code, because the >600 test catches it first (`0x41E28F`).

DS: per 40000. The DS base is 2, Environment-driven (+5 per missing level for odd genes, +3 for
half genes, -5 at L3). The snail and plant each give an independent 49% halve, plus age/100. A sick DS fish
has a 40% chance per tick of loss += disease.
**Verdict: Different.** On the PC, Food research drives the odds, not Environment. The PC
odds are per 10000, the Plant of Curing is a sure halve that does not stack with the snail,
the PC has contagion and an age step at 600, and a sick PC fish always takes -1 and cannot gain health.

## 3. Magic fish (`0x41DE90(k, tank)`: a fish in that tank with health != 0, age >= 20 and the pair)

Every caller was traced. There are only 6 (`grep "call 0x41de90"`). The name for each k
comes from string IDs 165-171 (Fertility, Sustenance, Curing, Growth, Health, Mutation,
Golden Guppy) and matches the traced effects.

| k | Pair (body,fin) | Name | PC effect (VA) | DS effect | Verdict |
|---|---|---|---|---|---|
| 0 | (20,16) Greenfin Spotanus | Fertility | At hatch in the same tank: one extra baby (`0x4202D9` → `0x41FA30`). The baseline is 1 baby, and the Plant of Fertility gives +1 more (`0x420356`). | 2 babies instead of 1; the plant gives +1 | **Same** |
| 1 | (14,14) Speckled Leaffish | Sustenance | When food <= 2, food is set to 0 and the fish loses 1 health per step. With this fish in the tank, the -1 is skipped only if `Random(0)` is non-zero. `Random(0)` always returns 0 (`0x403240` → `0x4032B5`), so starvation damage is **always prevented** (`0x420576`). | Starvation roll 50% → 20%; ±1 adjustment by play time | **Different:** the PC fish gives full immunity to starvation damage (a side effect of `Random(0)`) |
| 2 | (11,11) Crimson Comet | Curing | Sick fish in the tank: cured if `Random(0)` is non-zero. **Vanilla never cures** (`Random(0)` = 0) (`0x4204C4`). Fix Patcher: a 20% cure per step. | 1% per tick | **Different:** vanilla PC is dead code; the patched PC is 20%/step against 1%/tick |
| 3 | (10,9) Oriental Goldbulb | Growth | In each update call there are `(steps due + 1)` rolls. Each roll is `Random(100) <= 10`, an 11% chance, and needs the accumulator above 270 s. A success gives age +1 (`0x420019`). Each extra age also triggers an extra health/disease/food step. **Estimate** assuming only the 300 s timer: about 2 rolls per step at speed 5 (+22% aging), 3 at speed 10 (+33%), 4 at speed 15 (+44%). | +15% chance per tick of an extra growth step | **Different in rate** (11% per roll, several rolls per step). The mechanism is the same. |
| 4 | (5,8) Orange Snooper | Health | +1 health per step, unconditional, after the health tick and before the clamp (`0x420476`). Side effect: a tick that clamps a fish to 0 is followed by +1, so the fish survives unless starvation then takes it to 0. | loss -1 every tick | **Same** in intent. On the PC it also works as a partial death guard. |
| 5 | (13,6) Wasp Grouper | Mutation | At hatch (tank != 3): a 16% chance (`Random(100) <= 15`) to step the **stored mate's** body or fin (50/50) by ±1, bouncing at 0 and 20. Both values are clamped to 0-20 (`0x42014C`-`0x42025B`). This happens once per litter, before the floor average. The baby gene therefore moves by 0 or 1. Bug: the fin branch tests the body value for its bounce. | Every baby gene gets -1/0/+1 (1/3 each) after averaging, clamped 0-27 | **Different:** the PC is much weaker (16%, one parent gene, once per litter) |
| 6 | (7,7) Canary Fire-Arrow | "The Golden Guppy" | **No effect.** `0x41DE90(6)` is never called. Only the discovery decal (`0x41401C`, decal 0x15) and the name exist. | No effect (never called) | **Same** (none) |

## 4. Consumables (item use handler `0x420B70`, category switch at `[this+0x1C]`)

Each consumable affects every fish in the **current tank**: either the tank's fish-sprite list (medicine) or the 21-slot loop (chemicals). PC prices are from the state init at `0x419A43`.

| # | Item (PC price) | PC behaviour | DS | Verdict |
|---|---|---|---|---|
| 0 | Ick Treatment (30) | `0x420C4B`: each sick fish with **disease 2** is cured if `Random(100) < C`, where C depends on `state+0x14`: 0→70, 1→40, 2→25, other→30. Only works when the medicine slot holds item 0. Uses 1 of the 3 doses. | 40% cure per sick fish | **Same at setting 1 (40%)**, different otherwise. The PC also needs the matching disease. |
| 1 | Fungal Treatment (40) | The same code for **disease 1** with item 1. The tutorial flag `state+0x1E1A8 == 1` makes it always cure. | 40% | Same as Ick (40% at setting 1) |
| 2 | Fish Vitamins (140) | `0x42120A`: each fish with 0 < health < 100: health += `Random(10)+6` = **6-15**, cap 100. | +20-69 | **Different:** smaller boost |
| 3 | Growth Hormone (380) | `0x4210F2`: each fish with age <= 40: age += `Random(5)+2` = **2-6**. Unless `state+0x14 == 2`, the fish's last-processed age is set to age-1, so the skipped steps get **no** health/disease/food ticks. | age += 5-14 | **Different:** smaller jump, age <= 40 only, and it skips ticks |
| 4 | Unknown Chemical (650) | `0x420E93`: each fish (not body 22) has a **26%** chance. Then a 50% chance of body, else fin, and the gene moves ±1 (always -1 at 20, +1 at 0) inside 0-20. Vanilla gives **1 dose** (`0x4210B7` writes 1). | 75%; 49% fin else body; gene += 0-13, wrapping mod 28 | **Different:** the PC chance is lower, the step is ±1 only, there is no wrap, and the bias is 50/50 |
| 5 | Common Fish Eggs (120) | `0x4213D1`: count = `Random(2)+3` = **3-4**, +1 with the item-13 plant (`+0x17C`), +1 if `state+0x14 == 0`. Genes: body and fin each `Random(6)*4` = {0,4,8,12,16,20}. **No (20,16) remap in this path.** The remap exists only for the new-game starter fish at `0x4219F7`, so common eggs can hatch Greenfin Spotanus (1/36 per egg). | 3-6 eggs, genes {0,4,...,24} | **Different:** fewer eggs and no 24 gene (the PC has no gene 24) |
| 6 | Unusual Fish Eggs (450) | `0x4214A0`: same count. Genes `Random(5)*4+2` = {2,6,10,14,18}, all tier 2. | Same pool as common (possibly incomplete) | **Different:** the PC unusual eggs are all tier-2 genes |
| 7 | Rare Fish Eggs (1200) | `0x421573`: same count. Genes `Random(10)*2` = **{0,2,...,18}**, even only, a mix of tier 1 and 2. **No odd genes, and never 20.** | Odd genes 1-27 | **Different:** the PC rare eggs never give tier-3 (odd) genes |

Feeding (not a store item): every live fish in the tank gets food +50, cap 100 (`0x4121A3`). This does not depend on research. The food sprite type changes with Food research level (`0x420BE0`).

## 5. Permanent items (ownership dword `state+0x78+i*0x14`, set to 1 at `0x427BA5`; effects are global, not per tank)

| # | Item (PC price) | PC behaviour (VA) | DS | Verdict |
|---|---|---|---|---|
| 8 | Aeration System (70) | +1 health on a 41% roll per fish per step (`0x41E0A8`). Gated: zeroed if the fish is sick or food < 5. Other reads are cosmetic (bubbles `0x41EED4`, sound `0x421AE3`). | 4% chance of loss -1 for healthy fed fish | **Different in magnitude** (41% vs 4%). The direction and the gate are the same. |
| 9 | Temperature Regulator (175) | The same 41% +1 (`0x41E08A`). Cosmetic draw at `0x41EEF5`. | 6% | **Different in magnitude** |
| 10 | Cleaning Snail (80) | Halves the disease odds with a 50% chance, only when the Plant of Curing is not owned (`0x41E225`). Snail drawing at `0x42201B`. | 49% halve of infection | **Nearly the same.** On the PC it is redundant once the Plant of Curing is owned. |
| 11 | Golden Seahorse (1300) | **No health effect.** Economy only: crowd size +2 (`0x423EF6`), and each customer's buy chance +2 points (`0x412626`: `Random(100) < base + 2*(AdvLevel + Seahorse)`). Purchase also places the seahorse (body 22, which does not age, `0x41FF95`) via `0x427DBA` (**guess**: adds the seahorse fish). | 10% chance of loss -1 | **Different:** economy on the PC, health on the DS |
| 12 | Shop label **"Plant of Incubation"** (200) | Its dword `+0x168` drives the **nutrition** effect. Only while starving (food <= 2 → 0): a 21% chance (`Random(100) <= 20`) of food +5 per step (`0x4205A1`). | Incubation: +1 egg per purchase | See the row below. **The PC labels look swapped** (see note). |
| 13 | Shop label **"Plant of Nutrition"** (350) | Its dword `+0x17C` drives the **incubation** effect: +1 egg per batch, for all three egg types (`0x4213DB`, `0x4214AA`, `0x42157D`). | Nutrition: if food < 50, a 3.8% chance of food +1 | By effect: PC Incubation is +1 egg (**Same**). PC Nutrition is 21% food +5, only at food <= 2 (**Different:** it is a starvation rescue, not a top-up). |
| 14 | Plant of Curing (650) | **Always** halves the disease odds (`0x41E21C`). | 49% halve | **Different:** a sure halve on the PC |
| 15 | Plant of Fertility (1250) | +1 baby per litter (`0x420356`). | +1 baby | **Same** |
| 16 | Shell Ornament (20) | **Not decorative only.** Each owned ornament gives +1 crowd (`0x423F23`), and the ornament count lowers the chance of one fish thought bubble (`0x413651`, `0x413785`; **guess**: the "bored/wants decoration" thought). Placed as a tank object in the current tank (`0x419C00`, max 6). | Decorative only | **Different** (crowd +1 on the PC) |
| 17 | Pagoda Ornament (50) | Same as Shell (`0x423F1D`). | Decorative | **Different** |
| 18 | Diver Ornament (350) | Same (`0x423F17`). | Decorative | **Different** |
| 19 | Fancy Coral Ornament (950) | Same (`0x423F0E`). | Decorative | **Different** |
| 20 | Sunken Antique Column (1500) | Same (`0x423F05`). Note: store index 20 is the Column and 21 is the Ship (name IDs 216/214). | Decorative | **Different** |
| 21 | Sunken Ship Ornament (3500) | Same (`0x423EFC`). | Decorative | **Different** |
| 22 | Second Tank (450) | Ownership `+0x230` is read at `0x41388D`, `0x41F1A4`, `0x41F6F6`, `0x421DFE` and `0x427E6A` (tank switching and UI). **Not traced in detail**; presumed unlock. | Unlocks a tank | **Same (presumed)** |
| - | Sting Ray, Puffer Fish, Moray Eel (DS only) | No PC item | - | **PC has no equivalent** |

**Label swap note (traced, worth confirming in game).** Store record 12 (`0x457EF0 +
12*0x34`) has index 12 and name/description string IDs 198/199. These are "Plant of
Incubation" and "...increases the viability of purchased eggs". Record 13 has IDs 200/201,
"Plant of Nutrition". The purchase writes the dword at `state+0x78+index*0x14`. Index 12
(`+0x168`) is read only by the starvation/food code (`0x4205A1`) and the plant drawing.
Index 13 (`+0x17C`) is read by the three egg-hatch paths. So in vanilla PC, the plant sold
as Incubation feeds starving fish, and the plant sold as Nutrition adds eggs.

## 6. Research (store items 23-25; ownership dword = level 1-3, starts at 1)

Two purchases each (L1→L2→L3, refused above level 2 at `0x42760F`). Each takes 50 steps to finish (`0x420989`).

| Research | PC level field | PC effect (VA) | DS | Verdict |
|---|---|---|---|---|
| Fish Food (23) | `state+0x244`; price 200, then 650, then 1200 | (a) **Food decrement per step:** L1 always -1, L2 61% (`<= 60`), L3 31% (`<= 30`) (`0x420500`). (b) **Disease odds** base table in section 2 (`0x41E138`). (c) Food sprite flakes/pellets/live (`0x420BE0`, `0x420A05`). | Food -1 chance ~6.2% with no research, then 3.1/1.5/0.7%. No disease effect listed. | **Different:** the PC has 3 levels, not 4, much higher rates per (longer) tick, and it also lowers disease |
| Fish Environment (24) | `state+0x258`; 500, then 1750, then 2500 | **Only** the health-tick tier table (section 1, `0x41E014`/`0x41E038`/`0x41E05C`). No disease effect and no death-save effect. | Lowers infection; L1/L2 cancel the hybrid +1 loss; L3 gives -1 loss to all fish and +25 on the death save | **Different:** on the PC it gives health deltas only. The PC disease link is through Food research, and the PC has no death save. |
| Advertising (25) | `state+0x26C`; 350, then 1500, then 1200 | (a) Crowd size (sell scene, `0x423EEA`): `4 + ornaments + 2*Seahorse + 2*Adv*(adultsInTank2/3 + Random(2) + 2)`, passed to the customer spawner `0x4123B0`. Tank 2 is **guessed** to be the selling tank. (b) Customer buy chance +2 points per level (`0x412620`). (c) On completing L2: every species base price (`+0x24`) += price/10. On L3: += price/7 (`0x420A6E`-`0x420B40`). (d) Shop posters at L2/L3 (`0x423766`, `0x4237B5`) and a click hotspot (`0x423CBA`), cosmetic. | Crowd effect not traced | **Not comparable** (DS not traced). The PC effect is listed in full here. |

## 7. Births and newborns

- PC newborn (`0x41FA30`): health 100, food 90. Age is 1 for eggs; for a birth it is the mother's age minus the due age.
  Genes are `floor((a+b)/2)`. **No health penalty to the mother** was found in the hatch block
  (`0x420113`-`0x4203DD`). Pregnancies in tank 3 do not hatch (`0x42013D`).
- DS: health 101, food 90, growth counter 15, birth +2 loss to the mother; random rounding on odd sums.
- **Verdict: Different** (no maternal cost on the PC; floor rounding; health 100 against 101).

## 8. Not traced / open

- `0x419CA0` (the base customer buy chance used with Advertising/Seahorse): not traced.
- Second Tank (+0x230) reads: listed only, not walked.
- Seahorse purchase branch `0x427DBA`: assumed to add the body-22 seahorse fish; not walked.
- The meaning of tanks 2 and 3 (selling tank / isolation tank) is inferred, not proven.
- The option labels for `state+0x14` (difficulty) and the speed values 5/10/15 were not read from the UI strings.
- The ornament thought-bubble id 0xD meaning is a guess.
- The DS tick length is unknown here, so no rate can be converted between platforms.
