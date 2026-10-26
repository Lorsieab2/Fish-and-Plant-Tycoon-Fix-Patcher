# How to get the DS fish (testing guide)

This is the "DS Exclusive Fish" setting (Fish Tycoon). The odds come from
the PC game's own code; the breeding results from the DS game's own code.

## The new types

Every fish is a body plus a fin. The DS adds 7 of each. A fish's rarity tier
is the higher of its two parts' tiers. Most new fish are tier 3, so keep
them in a tank at **environment level 3**: a tier 3 fish loses 19 health per
tick at level 1 and 6 at level 2.

| Step | Body | Fin | Tier |
|---|---|---|---|
| 1 | Clownfish | Small Fin | 3 |
| 2 | Discus | Roundy | 2 |
| 3 | Bicolor | Angel | 3 |
| 4 | Trigger | Clown | 1 |
| 5 | Surgeonfish | Yellow | 3 |
| 6 | Tang | Blue | 2 |
| 7 | Idle | Moorish | 3 |

"Step" is how far past the PC's most common body (Spotanus) or fin
(Twin-Fin) the type sits. Higher steps are harder to reach.

**Matching pairs** (same step for body and fin) are worth $10 more: Small Fin
Clownfish, Roundy Discus, Angel Bicolor, Clown Trigger, Yellow Surgeonfish,
Blue Tang and Moorish Idle. Prices for species with a DS part run from $5
(Fatfish Clown) to $42 (Moorish Idle).

Eggs, the store and breeding two PC fish **never** give a DS fish.

## 1. Start with Spotanus and Twin-Fin fish

The way in is through the common end of the list:
- A **Spotanus** body can mutate into a **Clownfish** body.
- A **Twin-Fin** fin can mutate into a **Small Fin** fin.

Spotanus and Twin-Fin both come from eggs and the store. **Twin-Fin
Spotanus** carries both, so it is the best starter fish.

## 2. Use the Unknown Chemical

Each dose goes through every live fish in the tank:
1. Each fish has a 26% chance to be affected.
2. An affected fish changes either its body or its fin (50/50).
3. That part moves one step up or down the list (50/50).

So per dose, each fish has about a **6.5% chance to step its body one step
deeper** and the same chance for its fin.

A tank of 21 Twin-Fin Spotanus gives about 1.4 new Clownfish bodies and 1.4
new Small Fin fins per dose. With the Fix Patcher's "Unknown Chemical: 3
uses" setting, one bottle is three doses.

To go deeper, keep dosing the DS fish. Each step is another 6.5%, and the
same chance pushes back toward the PC fish, so reaching step 7 (Idle or
Moorish) by mutation alone is a long grind.

## 3. Breed to multiply and go deeper

Breeding a DS fish follows the DS game's own rule (traced from the DS ROM):
the baby's body is the average of the parents' bodies, and the same for
fins, counting along the list from Shark/Silky to Idle/Moorish. When the two
parents' positions add up to an odd number the game rounds up or down at
random, 50/50, once per litter. Two PC parents keep the PC's own rule
(always rounded down), so they never give a DS fish.

- **Two of the same type always breed true.**
- A baby is never rarer than its rarer parent. Breeding spreads what you
  already have; only mutation reaches a new deepest step.
- A DS fish x a PC fish lands halfway between them. Clownfish x Spotanus is
  a 50/50 between Spotanus and Clownfish; Small Fin x Twin-Fin between
  Twin-Fin and Small Fin.

Ways to breed each type ("always" pairs land on it every time; "half" pairs
land on it or a neighbour):

| Target | Always | Half the time |
|---|---|---|
| Clownfish | Clownfish x Clownfish, Spotanus x Discus, Quicksilver x Bicolor, Bananafish x Trigger, Pigmy x Surgeonfish | Clownfish x Discus, Spotanus x Clownfish, Spotanus x Bicolor, Quicksilver x Discus |
| Discus | Discus x Discus, Clownfish x Bicolor, Spotanus x Trigger, Quicksilver x Surgeonfish, Bananafish x Tang | Discus x Bicolor, Clownfish x Discus, Clownfish x Trigger, Spotanus x Bicolor |
| Bicolor | Bicolor x Bicolor, Discus x Trigger, Clownfish x Surgeonfish, Spotanus x Tang, Quicksilver x Idle | Bicolor x Trigger, Discus x Bicolor, Discus x Surgeonfish, Clownfish x Trigger |
| Trigger | Trigger x Trigger, Bicolor x Surgeonfish, Discus x Tang, Clownfish x Idle | Trigger x Surgeonfish, Bicolor x Trigger, Bicolor x Tang, Discus x Surgeonfish |
| Surgeonfish | Surgeonfish x Surgeonfish, Trigger x Tang, Bicolor x Idle | Surgeonfish x Tang, Trigger x Surgeonfish, Trigger x Idle, Bicolor x Tang |
| Tang | Tang x Tang, Surgeonfish x Idle | Tang x Idle, Surgeonfish x Tang, Trigger x Idle |
| Idle | Idle x Idle | Tang x Idle |
| Small Fin | Small Fin x Small Fin, Twin-Fin x Roundy, Finless x Angel, Flagged x Clown, Great-Sail x Yellow | Small Fin x Roundy, Twin-Fin x Small Fin, Twin-Fin x Angel, Finless x Roundy |
| Roundy | Roundy x Roundy, Small Fin x Angel, Twin-Fin x Clown, Finless x Yellow, Flagged x Blue | Roundy x Angel, Small Fin x Roundy, Small Fin x Clown, Twin-Fin x Angel |
| Angel | Angel x Angel, Roundy x Clown, Small Fin x Yellow, Twin-Fin x Blue, Finless x Moorish | Angel x Clown, Roundy x Angel, Roundy x Yellow, Small Fin x Clown |
| Clown | Clown x Clown, Angel x Yellow, Roundy x Blue, Small Fin x Moorish | Clown x Yellow, Angel x Clown, Angel x Blue, Roundy x Yellow |
| Yellow | Yellow x Yellow, Clown x Blue, Angel x Moorish | Yellow x Blue, Clown x Yellow, Clown x Moorish, Angel x Blue |
| Blue | Blue x Blue, Yellow x Moorish | Blue x Moorish, Yellow x Blue, Clown x Moorish |
| Moorish | Moorish x Moorish | Blue x Moorish |

## 4. Optional: the Magic Fish of Mutation

The **Wasp Grouper** is the Magic Fish of Mutation. While an adult one is in
the tank, each hatching has a 16% chance to step the father's body or fin one
place before the baby is worked out (the PC's own rule, kept). With the mod
the step can go from Spotanus or Twin-Fin into the DS types, so two PC
parents can then produce a half-DS baby, and in a tank of DS fish it helps
push one step deeper.

## 5. Things to check while testing

- The mod is on: `Fish Tycoon Fix Patcher Files\FTFP DS Fish.log` beside the
  game reads "DS Fish: installed (all sites)".
- Eggs and store fish never come out as a DS type.
- The Unknown Chemical can step Spotanus to Clownfish, Twin-Fin to Small Fin,
  and back.
- A new DS species shows its name and DS price on the Species screen when
  first discovered, and customers buy it.
- DS fish turn, grow from baby to teen to adult, and die with the correct
  sprites, and their fins stay attached through the turn.
- Tier 3 DS fish lose health at environment levels 1-2 and hold steady at
  level 3.
- Saving, quitting and reloading keeps DS fish and DS species data (the file
  `Fish Tycoon Fix Patcher Data\DS Fish <slot>.dat` beside the saves).
- A Wasp Grouper in the tank occasionally gives a DS baby from Spotanus or
  Twin-Fin parents.
