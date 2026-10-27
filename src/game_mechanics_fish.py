"""Fish Tycoon's Game Mechanics page: the facts.

Traced in the vanilla LDW "Fish Tycoon.exe" (v1.6.2). Every chance is the
game's own test with its exact odds (game_mechanics.chance).
"""

from __future__ import annotations

from game_mechanics import Fact, GamePage, Group, at_most, below, chance

STEP = "one age step (5, 10 or 15 real-life minutes at 2x speed, Normal and 1/2 speed)"


def page() -> GamePage:
    return GamePage(
        game_id="fish",
        title="Fish Tycoon",
        intro=(
            "How Fish Tycoon really works underneath, read from the game's code. Every chance below "
            "is the game's own roll: Random(n) is the C runtime's rand() % n, so a roll like "
            "\"Random(100) <= 40\" is 41.04%, not 41%."
        ),
        time_and_units=(
            "Fish live in age steps. The speed option sets the real-life length of one step: 2x speed "
            "5 minutes, Normal 10 minutes (the default), 1/2 speed 15 minutes; Stop Time pauses. A "
            "fish is a baby at age 1-5, a teen at 6-19 and an adult from 20. \"Per step\" means once "
            "per age step of each fish. \"Real-life\" times are wall-clock time, whether the game is "
            "open or not. Difficulty is Easy, Medium (the default) or Hard."
        ),
        groups=(
            Group("Time away (catch-up)", TIME_AWAY),
            Group("Which tank counts", SCOPE),
            Group("Ages and stages", AGES),
            Group("Health", HEALTH),
            Group("Sickness", SICKNESS),
            Group("Food", FOOD),
            Group("Breeding and babies", BREEDING),
            Group("Eggs", EGGS),
            Group("Magic fish", MAGIC_FISH),
            Group("Medicines and chemicals", CONSUMABLES),
            Group("Permanent store items", PERMANENT_ITEMS),
            Group("Research", RESEARCH),
            Group("Selling and customers", SELLING),
            Group("Species and prices", PRICES),
            Group("A new game", NEW_GAME),
            Group("Goals and popups", GOALS),
            Group("DS store animals", DS_ANIMALS,
                  note="Only with the DS Store Items setting. The store calls them \"magically enhancing\"; "
                       "these are their real effects."),
            Group("Chance and timer index", INDEX),
        ),
    )


TIME_AWAY = (
    Fact(
        "Fish only update while the tank screen is open: once every 301 real-life seconds or more, "
        "at once when you open the tank screen or switch tanks, and again 11 real-life seconds "
        "later; also 2 real-life seconds after the Unknown Chemical, 8 after Growth Hormone, 5 "
        "after the starter eggs and 11 after other eggs. It is put off 10 real-life seconds while "
        "you drag a fish. In the store, the selling scene, the species screen or the options, nothing "
        "updates; the time is caught up the next time the tank screen opens.",
    ),
    Fact(
        "Every update covers all four tanks (Tank One, Tank Two, the selling tank and the "
        "isolation tank), whichever is on screen.",
    ),
    Fact(
        "An update turns each fish's banked real-life time into age steps and runs every step's "
        "health, sickness, food and death checks one by one. The time banked at once is capped:",
        subs=(
            "More than 72 real-life hours (259200 s) banked: 72 hours of steps, so 864 steps at 2x "
            "speed, 432 at Normal and 288 at 1/2 speed.",
            "Up to 72 real-life hours, by speed. 2x speed: up to 32400 real-life seconds (108 "
            "steps) is kept, more becomes 25200 s (84 steps). Normal: more than 25200 real-life "
            "seconds becomes 25200 s (42 steps). 1/2 speed: more than 18000 real-life seconds is "
            "raised to 25200 s (28 steps).",
            "So time away is not counted evenly. At Normal speed, 71 real-life hours away gives 42 "
            "steps (7 hours' worth) and 73 real-life hours away gives 432 steps (72 hours' worth).",
            "The rest of the banked time below one step is kept for the next update.",
        ),
    ),
    Fact(
        "Stop Time: no fish ages, eats, gets sick or dies, and research stops. Paused real-life time "
        "is thrown away, also while the game is closed. Leaving Stop Time resets every fish's banked "
        "time.",
    ),
    Fact(
        "Research uses its own timer, which is never capped: all time away counts in full.",
    ),
    Fact(
        "A pregnant fish gives birth at the first update after her due age, so a mother who is due "
        "while you are away gives birth when you return, and her babies start older: they catch up "
        "the steps they missed at their next update.",
    ),
    Fact(
        "If the computer's clock goes backwards, a fish whose last update is in the future is set to "
        "30 real-life seconds ago.",
    ),
)

AGES = (
    Fact("Babies are 1-5, teens 6-19, adults 20 and up. A fish shows as a baby from age 1."),
    Fact(
        "From an egg (age 1) to adult (20) is 19 steps: 95, 190 or 285 real-life minutes at 2x "
        "speed, Normal and 1/2 speed.",
    ),
    Fact(
        "Only adults get sick, count as magic fish, breed, sell, or reveal their species. Growth "
        "Hormone works up to age 40.",
    ),
    Fact(
        "There is no death of old age and no age limit. The only effect of old age is +15 to the "
        "sickness odds above age 600 (see Sickness).",
    ),
    Fact("The Golden Seahorse never ages."),
)

HEALTH = (
    Fact(
        "Health runs from 0 to 100. Each age step, each fish's health changes by the sum of the "
        "parts below, then is clamped to 0-100. A fish at 0 dies at the end of that step and stays "
        "in the tank as a dead fish until you throw it away.",
        subs=(
            "Rarity by Fish Environment research level (L1 / L2 / L3): common genes +1 / +3 / +5, "
            "half-rare genes -1 / +1 / +3, rare genes -19 / -6 / 0. A fish takes the rarest of "
            "its body and fin.",
            f"Temperature Regulator owned: {at_most(100, 40)} chance of +1.",
            f"Aeration System owned: {at_most(100, 40)} chance of +1.",
            f"Easy difficulty: {at_most(100, 30)} chance of +1.",
            "If the fish is sick or its food is below 5, a positive total becomes 0; if it is sick, "
            "-1 more.",
        ),
    ),
    Fact(
        "Common genes are 0, 4, 8, 12, 16 and 20; half-rare genes are 2, 6, 10, 14 and 18; every odd "
        "gene is rare.",
        patched=(("ds_fish", "the DS genes follow the DS game's rarity: 23, 25, 27 and 29 are rare, "
                  "24 and 28 half-rare, 26 common."),),
    ),
    Fact(
        "There is no survival roll: a fish whose health reaches 0 dies.",
        patched=(("ds_store", "with a Moray Eel in the tank (swimming or in its rock), a dying fish "
                  f"survives at health 10 on {below(10, 1)}."),),
    ),
    Fact(
        "Overfeeding: feeding a fish whose food would go above 100 costs it 2 health. The Golden "
        "Seahorse is never hurt by it.",
    ),
)

SICKNESS = (
    Fact(
        "Only adults get sick, and only when not sick already. Each age step a fish rolls "
        "Random(10000) < X; its sickness is then fungus or ick, "
        f"{chance(2, 1)} each.",
        subs=(
            "X by the body's rarity and Fish Food research level (L1 / L2 / L3): common 10 / 5 / 1, "
            "half-rare 20 / 10 / 3, rare 30 / 20 / 5. Only the body counts, and Fish Environment "
            "research does not change it.",
            "Easy: X - X/5. Hard: X + X/2.",
            "Plant of Curing owned: X halved, always. Otherwise the Cleaning Snail halves it on "
            f"{at_most(100, 49)}. The two never stack.",
            "Each other sick fish in the same tank: +6 (not on Easy), dead fish that were sick "
            "included.",
            "Age above 600: +15.",
        ),
    ),
    Fact(
        "Example: a rare-bodied adult with no Food research on Medium is sick on Random(10000) < 30, "
        f"{chance(10000, 30)} per step.",
    ),
    Fact(
        "A second age bonus, +30 above age 800, is dead code: the age-600 test catches every such "
        "fish first.",
    ),
    Fact(
        "A sick fish cannot gain health and loses 1 extra each step (see Health), loses a pregnancy "
        "at every step, and sells far less easily (see Selling and customers).",
    ),
)

SCOPE = (
    Fact(
        "Every update runs all four tanks together: the first tank, Tank Two, the selling tank and "
        "the isolation tank. A tank you are not looking at keeps going (0x41FE70, tanks 0-3).",
    ),
    Fact(
        "Magic fish work only in their own tank: a live adult (age 20 or more) of the species must "
        "be in the same tank as the fish it acts on (0x41DE90 scans only that tank).",
        subs=(
            "Health, Sustenance, Growth and Curing act on the fish in their tank, the isolation tank "
            "included.",
            "Fertility and Mutation act at a birth: what counts is the tank the mother gives birth "
            "in. Births never happen in the isolation tank, so there they do nothing.",
            "The customer bonus of a discovered magic species is permanent and counts everywhere.",
        ),
    ),
    Fact(
        "Owned items work in every tank, wherever they are drawn: the Aeration System, Temperature "
        "Regulator, Cleaning Snail, all four plants, research and the Golden Seahorse are game-wide "
        "flags. The snail and plants are only drawn in the tank screens; that is all.",
    ),
    Fact(
        "Ornaments count wherever they are: each one owned adds a customer, in any tank. Moving "
        "them is only decoration. The only tank-specific part of the customer count is the adults "
        "in the selling tank.",
    ),
    Fact(
        "Things you use act on the tank you are looking at (never directly on the isolation tank):",
        subs=(
            "Food and the Ick and Fungal Treatments: every fish in that tank, plus the fish in the "
            "isolation tank if there is one.",
            "Vitamins, Growth Hormone and the Unknown Chemical: only that tank's fish.",
            "Eggs hatch into that tank.",
        ),
    ),
    Fact("Sickness spreads per tank: each other sick fish in the same tank adds 6 to the odds "
         "(not on Easy)."),
    Fact("DS store animals act only on the fish in their own tank.",
         patched=(("ds_store", "the Stingray, Pufferfish and Moray Eel each count only in the tank "
                   "they are in."),)),
)

FOOD = (
    Fact(
        "Food runs from 0 to 100. Feeding gives every live fish in the tank you are looking at +50, and the fish in "
        "the isolation tank too, capped at 100, "
        "whatever the Fish Food research level; research only changes the food's look.",
    ),
    Fact(
        "Each age step a fish loses food by Fish Food research level: L1 always -1, "
        f"L2 -1 on {at_most(100, 60)}, L3 -1 on {at_most(100, 30)}.",
    ),
    Fact(
        "Starving: at food 2 or less, food drops to 0 and the fish loses 1 health per step.",
        subs=(
            "The Plant of Incubation ($200) rescues starving fish: "
            f"{at_most(100, 20)} chance per step of food +5. (The two plants do each other's job in "
            "the game: see Permanent store items. With Fix Vanilla Bugs it is the Plant of Nutrition.)",
            "Magic Fish of Sustenance in the tank: the -1 health is never taken (see Magic fish).",
        ),
    ),
)

BREEDING = (
    Fact(
        "Breeding is certain: there is no roll and no male or female. Drop an adult fish on the "
        "isolation tank while another fish is in it, and the fish already there becomes pregnant, "
        "as long as it is a live, healthy, adult fish that is not already pregnant. The fish you "
        "dropped can be sick; it goes back to its tank unchanged.",
    ),
    Fact(
        "She is due at her age + 3 and gives birth at the first update after that: 4 age steps "
        "after mating, which is 3 to 4 step lengths of real-life time (her part-step already banked "
        "counts): 15-20, 30-40 or 45-60 real-life minutes at 2x speed, Normal and 1/2 speed. While she stays in the "
        "isolation tank her pregnancy is frozen; she gives birth once she is back in another tank "
        "and has aged a step.",
    ),
    Fact(
        "A litter is 1 baby, +1 with a live adult Magic Fish of Fertility in her tank, +1 with the "
        "Plant of Fertility: 1-3 babies. Neither parent pays anything for it.",
    ),
    Fact(
        "A baby's body is the parents' bodies averaged and rounded down, and the same for the fin. "
        "Babies start at health 100 and food 90, in their mother's tank.",
        patched=(("ds_fish", "for a body (or fin) pair with a DS gene, the DS game's rule: the "
                  "average, with an odd total rounded up or down at random, one roll per litter "
                  "shared by body and fin; a pair without a DS gene still rounds down."),),
    ),
    Fact(
        "A baby born into a full tank (21 fish) is lost without a message. The game's "
        "\"One of your tanks is full!\" warning is never shown.",
        patched=(("bigger_tanks", "Tank One, Tank Two and the selling tank hold 26 fish."),),
    ),
    Fact("A sick mother loses her pregnancy; a dead mother never gives birth."),
)

EGGS = (
    Fact(
        "Every egg type hatches Random(2) + 3 babies (3 or 4, "
        f"{chance(2, 1)} each), +1 with the Plant of Nutrition ($350; the Plant of "
        "Incubation with Fix Vanilla Bugs), +1 on "
        "Easy. Eggs hatch at age 1 in the tank you drop them in.",
    ),
    Fact(
        "Common Fish Eggs ($120): body and fin each one of 0, 4, 8, 12, 16, 20 (1 in 6 each), so "
        "1 egg in 36 is the magic Greenfin Spotanus.",
    ),
    Fact("Unusual Fish Eggs ($450): body and fin each one of 2, 6, 10, 14, 18 (1 in 5 each)."),
    Fact(
        "Rare Fish Eggs ($1200): body and fin each one of 0, 2, 4 ... 18 (1 in 10 each). Never a "
        "rare (odd) gene and never 20.",
    ),
    Fact(
        "Eggs only go in slot #4.",
        patched=(("universal_supply_slots", "eggs, medicines and chemicals can go in any of slots "
                  "2-4."),),
    ),
    Fact(
        "Exotic Fish Eggs: not in the unpatched game.",
        patched=(("ds_store", "Exotic Fish Eggs ($2300; slot #4, or any of slots 2-4 with Universal "
                  "supply slots, where they stack like the other eggs) hatch as many babies as the "
                  "other eggs, each with a random DS-only body and a random DS-only fin (genes "
                  "23-29, 1 in 7 each)."),),
    ),
)

MAGIC_FISH = (
    Fact(
        "A magic fish counts when a live adult of its species is in the same tank. Finding all "
        "seven wins the game.",
    ),
    Fact("Fertility, Greenfin Spotanus (body 20, fin 16): one extra baby per litter in its tank."),
    Fact(
        "Sustenance, Speckled Leaffish (14, 14): starving fish in its tank never lose health. "
        "The game rolls Random(0) to allow the loss, and Random(0) is always 0.",
    ),
    Fact(
        "Curing, Crimson Comet (11, 11): does nothing. Its cure needs Random(0) to be non-zero, and "
        "Random(0) is always 0.",
        patched=(("crimson_comet_20_percent_cure",
                  f"each sick fish in its tank is cured on {below(100, 20)} per age step."),),
    ),
    Fact(
        f"Growth, Oriental Goldbulb (10, 9): each fish in its tank rolls {at_most(100, 10)} on "
        "every update for each step it takes plus one, when the fish's banked real-life time "
        "(before it is turned into steps) is over 270 seconds; a success adds 1 age, with its own health, sickness and "
        "food step.",
        subs=(
            "Live play gives about 2, 3 or 4 rolls per step (2x speed, Normal, 1/2 speed); a long "
            "time away gives about 1 roll per step, because a catch-up is one update.",
        ),
    ),
    Fact(
        "Health, Orange Snooper (5, 8): +1 health to every fish in its tank, each age step, after "
        "the step's (already clamped) health change, then clamped to 100 again. So a fish the "
        "health change left at 0 is raised to 1 and survives that step, unless starvation takes "
        "the point back.",
    ),
    Fact(
        f"Mutation, Wasp Grouper (13, 6): at each birth in its tank, {at_most(100, 15)} chance to "
        "move the father's stored body or fin one step up or down before the babies' genes are "
        "averaged. Once per litter.",
        subs=("Stock bug: the fin step tests the body's value for its 0 and 20 bounce.",),
        patched=(("ds_fish", "the step can also go from 20 into the DS genes, and the fin step "
                  "tests the fin's own value (the stock bug is fixed)."),),
    ),
    Fact(
        "The Golden Guppy, Canary Fire-Arrow (7, 7): no effect. The game never checks for it, but "
        "it counts toward the seven.",
    ),
    Fact(
        "Each magic species you have discovered also makes customers 1 point more likely to walk "
        "to the tanks (see Selling and customers).",
    ),
)

CONSUMABLES = (
    Fact(
        "Buying one fills its supply slot: medicines go in slot #2, chemicals in slot #3, eggs in slot "
        "#4 (any of 2-4 with Universal supply slots). A medicine, Fish Vitamins or Growth Hormone "
        "purchase holds 3 doses; the Unknown Chemical 1; eggs are one batch. Each use spends one, on "
        "the tank you are looking at. There is no cooldown: \"one drop every half hour\" is only "
        "advice.",
    ),
    Fact(
        "Ick Treatment ($30, 3 doses): every fish with ick in the tank you use it on, and the fish in "
        "the isolation tank, is cured on Random(100) < C: Easy 70 "
        f"({chance(100, 70)}), Medium 40 ({chance(100, 40)}), Hard 25 ({chance(100, 25)}). Each fish "
        "rolls on its own; a failed roll leaves it sick, and you can dose again at once. It does "
        "nothing for fungus.",
    ),
    Fact(
        "Fungal Treatment ($40, 3 doses): the same for fungus, with the same odds; it does nothing for "
        "ick. In the tutorial, until the breeding tip appears, any medicine (Ick or Fungal "
        "Treatment) cures a fungus-sick fish with no roll; the first such cure brings up that tip, "
        "and after that the normal odds apply.",
    ),
    Fact(
        "Fish Vitamins ($140, 3 doses): each fish in the tank you use it on with health 1-99 gains "
        "6-15 health (Random(10) + 6, 10% each), capped at 100. Sick fish get it too, but it does not "
        "cure them. Dead fish (health 0) and fish at 100 get nothing. It does not reach the isolation "
        "tank.",
    ),
    Fact(
        "Growth Hormone ($380, 3 doses): each fish in the tank you use it on aged 40 or less gains "
        "2-6 age (Random(5) + 2, 20% each), so babies and teens grow up sooner. Only one age step's "
        "health, sickness and food checks run for the whole jump (the last one); on Hard every "
        "skipped step runs. Fish older than 40 and dead fish get nothing. A new game starts with 1 dose in slot #3.",
    ),
    Fact(
        f"Unknown Chemical ($650): each live fish (not the Golden Seahorse) in the tank you use it on "
        f"is changed on {at_most(100, 25)}. Then its body changes on {at_most(100, 49)}, otherwise its "
        f"fin; the gene moves one step up on {at_most(100, 49)}, otherwise down, but always down at "
        "20 and always up at 0. One dose. It is how you reach odd (rare) genes and new species "
        "without breeding.",
        patched=(
            ("unknown_chemical_three_uses", "one purchase gives 3 doses."),
            ("ds_fish", "a body or fin at 20 can also step up into the DS genes (23-29), with the "
             "same odds; 29 is the new end."),
        ),
    ),
    Fact("Common, Unusual and Rare Fish Eggs: see Eggs."),
)

PERMANENT_ITEMS = (
    Fact(
        "Each permanent item is bought once and works game-wide from then on, in all four tanks "
        "(see Which tank counts), whichever tank you were in when you bought it.",
    ),
    Fact(
        f"Aeration System ($70): each age step, each fish gets {at_most(100, 40)} chance of +1 "
        "health, added before the step's total is taken. If the fish is sick or its food is below 5, "
        "a positive total becomes 0, so it only helps healthy, fed fish. It also adds bubbles and a "
        "sound.",
    ),
    Fact(
        f"Temperature Regulator ($175): a second, separate {at_most(100, 40)} chance of +1 health per "
        "fish per step, with the same rule for sick or hungry fish. With both, a fish gets 0, 1 or 2 "
        "of these points a step.",
    ),
    Fact(
        f"Cleaning Snail ($80): an adult's sickness odds X are halved on {at_most(100, 49)} each step. "
        "It does nothing once you own the Plant of Curing (the two never stack). It is drawn in the "
        "tank you are looking at; that is only for show.",
    ),
    Fact(
        "Golden Seahorse ($1300): no effect on fish. It brings 2 more customers to the selling "
        "scene and makes each customer 2 points (out of 100, every quarter real-life second) more "
        "likely to walk to the tanks. Both count even after it is gone. It arrives as an adult in "
        "Tank One (Tank Two, then the selling tank, if that is full) and never ages with time, "
        "eats, gets sick or breeds, and overfeeding never hurts it. Growth Hormone still raises "
        "its age number.",
        patched=(
            ("golden_seahorse_repurchase", "it can be bought any number of times, even while one "
             "is in a tank; extra ones add no customers or walk-over points."),
            ("ds_store", f"it also gives healthy, fed fish in its tank {below(100, 82)} chance of +1 "
             "health each step."),
        ),
    ),
    Fact(
        "A Golden Seahorse in the selling tank is never sold in normal play. The stock sale code "
        "(0x424240, run every real-life second) does not check for it, so it does look at it as a "
        "live adult, but its price lookup lands just past the species table, where both the asking "
        "price and the base price read 0 (in every save checked). 0 is \"2B or more\", which never "
        "sells.",
        subs=(
            "One exception: in a game started with the tutorial, until its \"basics\" tip (tutorial "
            "popup 19) has shown and while you have sold at most 1 fish, any fish priced under $50 is treated as a big bargain. In "
            "that short window a seahorse in the selling tank could sell, for $0.",
        ),
        patched=(("ds_store", "the sale code skips it (and the DS animals) entirely."),),
    ),
    Fact(
        "The two plants do each other's job. The Plant of Incubation ($200, \"increases the "
        f"viability of purchased eggs\") rescues starving fish: a fish at food 2 or less has "
        f"{at_most(100, 20)} chance each step of food +5. The Plant of Nutrition ($350) adds 1 egg to "
        "every egg batch (Common, Unusual, Rare).",
        patched=(("fix_vanilla_bugs", "the effects are swapped back: the Plant of Incubation adds the "
                  "egg (Exotic Fish Eggs too) and the Plant of Nutrition rescues starving fish. Names, "
                  "pictures and prices are unchanged, and plants already owned switch over."),),
    ),
    Fact(
        "Plant of Curing ($650): every adult's sickness odds X are halved, every step, in every tank. "
        "It makes the Cleaning Snail useless. It does not cure a sick fish.",
    ),
    Fact(
        "Plant of Fertility ($1250): every litter gets one more baby (1-3 with the Magic Fish of "
        "Fertility). It does not change eggs.",
    ),
    Fact(
        "Ornaments (Shell $20, Pagoda $50, Diver $350, Fancy Coral $950, Sunken Antique Column $1500, "
        "Sunken Ship $3500): each one owned brings 1 more customer to the selling scene, whichever "
        "tank it is in. That is their only effect.",
        subs=(
            "A purchase drops it into the tank you are looking at; drag it to place it, or onto the "
            "Tank Two button to move it there (with the Second Tank). Each ornament can be bought "
            "once (6 in all); a tank has room for 6.",
            "Fewer ornaments make the customers' diver \"?\" thought (they want more decor) more "
            "likely: it shows when Random(4) is above the number you own. The thought changes "
            "nothing.",
        ),
    ),
    Fact(
        "Second Tank ($450): unlocks Tank Two, a second full-size tank (21 fish) with its own fish, "
        "ornaments and magic fish. You can drop fish and ornaments on its button to move them.",
        patched=(("bigger_tanks", "it holds 26 fish, like Tank One and the selling tank."),),
    ),
)

RESEARCH = (
    Fact(
        "Each research line starts at level 1 and can be bought twice: Fish Food $200 then $650, "
        "Fish Environment $500 then $1750, Advertising $350 then $1500.",
    ),
    Fact(
        "A research gains 2 points for every age step's worth of real-life time and finishes at 100. "
        "It starts at 1 with one step already counted, so it takes about 49 steps: about 4 h 5 min, "
        "8 h 10 min or 12 h 15 min of real-life time at 2x speed, Normal and 1/2 speed. Its timer is never capped, so "
        "time away counts in full; Stop Time throws the time away.",
    ),
    Fact(
        "Fish Food research: its level (state + 0x244) starts at 1; the first purchase ($200) raises "
        "it to 2 and the second ($650) to 3, each after the research finishes. The level does three "
        "things, and nothing else:",
        subs=(
            "Food lasts longer. Each age step a fish loses 1 food: at level 1 always, at level 2 on "
            f"{at_most(100, 60)}, at level 3 on {at_most(100, 30)}. So one feeding (+50) lasts about 50 "
            "steps at level 1, about 82 at level 2 and about 161 at level 3, and a full fish (100) "
            "takes about 98, 160 or 316 steps to start starving (food 2 or less).",
            "Adults get sick less often: the sickness roll's base X (out of 10000 per step) is, at "
            "levels 1 / 2 / 3, common bodies 10 / 5 / 1, half-rare 20 / 10 / 3, rare 30 / 20 / 5 "
            "(see Sickness for what else changes X).",
            "The food looks different: flakes at level 1, pellets at level 2, live food at level 3. "
            "Feeding still gives every fish +50 food, capped at 100, at every level.",
            "It does not change health, breeding, prices or customers.",
        ),
    ),
    Fact(
        "Fish Environment research ($500 then $1750): changes only the part of each step's health "
        "change that comes from the fish's rarest gene (its body or fin, whichever is rarer):",
        subs=(
            "Common genes: +1 / +3 / +5 health per step at levels 1 / 2 / 3.",
            "Half-rare genes: -1 / +1 / +3.",
            "Rare (odd) genes: -19 / -6 / 0. So at level 1 a rare fish loses 19 health a step "
            "(dies in about 6 steps without help); level 3 makes rare fish safe.",
            "It does not change sickness, food, breeding, prices or customers.",
        ),
    ),
    Fact(
        "Advertising research ($350 then $1500): three effects, all in the selling scene:",
        subs=(
            "More customers: the crowd counted when you open the selling scene includes 2 x level x "
            "(adults in the selling tank / 3, rounded down, + Random(2) + 2).",
            "Customers walk to the tanks more often: +2 points per level on the quarter real-life second "
            "Random(100) roll (see Selling and customers).",
            "On finishing level 2 every species' base price rises by a tenth, on level 3 by a "
            "seventh; your asking prices stay, so they become better bargains (higher sale odds).",
            "The shop's posters change at levels 2 and 3; that is only for show.",
        ),
    ),
)

SELLING = (
    Fact(
        "Customers: 4 + 1 per ornament owned + 2 for the Golden Seahorse + 2 x Advertising level x "
        "(adults in the selling tank / 3, rounded down, + Random(2) + 2). Counted once each time you "
        "open the selling scene; they keep coming and going until you leave.",
    ),
    Fact(
        "Selling only happens while the selling scene is open. Once every real-life second, the "
        "adults in the selling tank are tried in slot order; the first that sells ends that second. "
        "After a sale there is no other for 5 real-life seconds.",
    ),
    Fact(
        "Each fish rolls Random(900) <= T, with K = (N + 2) / 2 rounded down and N the customers "
        "browsing or at the tank. P is your asking price, B the species' base price:",
        subs=(
            "P below B by at least half of B (rounded down): T = 30K. With no customers browsing, "
            f"{at_most(900, 30)}.",
            f"P below B by less than half: T = 10K ({at_most(900, 10)} with none browsing).",
            f"P from B to 1.5B: T = 4K ({at_most(900, 4)} with none browsing).",
            f"P above 1.5B, or the fish is sick: T = K ({at_most(900, 1)} with none browsing).",
            "P of 2B or more: never sells.",
            f"A sick fish also needs {at_most(100, 20)} on top.",
            "So more browsing customers raise every chance, and fish sell even with no one at the "
            "tank.",
        ),
    ),
    Fact("You are paid your asking price P, whatever it is, even 0."),
    Fact(
        "Every quarter real-life second (0.26 s in practice), each customer standing inside first "
        f"leaves on {below(100, 3)}; otherwise it walks over to the tanks on Random(100) < k, with "
        "k = magic species discovered + 2 x (Advertising level + Golden Seahorse). Example: "
        f"Advertising level 1 and nothing else, {below(100, 2)} for that second roll.",
    ),
    Fact(
        "Thought bubbles are only hints and change nothing: a frowning \"$!\" means a fish is "
        "overpriced (2B or more, or on Random(100) < 50 (50.05%) above 1.5B), a smiling \"$\" a bargain, a stinky "
        "fish a sick or dead one, a diver with \"?\" that customers want more ornaments, and a fish "
        "with \"?\" that 3 random looks at the selling tank found no adult (or only adults "
        "priced from B to 1.5B).",
    ),
)

PRICES = (
    Fact(
        "Each species has a base price B from 4 to 190 (its fin's part plus its body's part, with "
        "13 fixed exceptions such as the Golden Guppy at 190).",
        patched=(("ds_fish", "DS species use the DS game's body and fin values, +10 for a matching "
                  "DS pair."),),
    ),
    Fact(
        "When a species is first discovered (a live adult in any tank), its asking price is set to "
        "B plus or minus Random(n), minus on "
        f"{at_most(100, 49)}, with n = B/10 on Easy, B/5 on Medium, B/2 on Hard.",
    ),
    Fact(
        "After that the asking price never changes by itself: only the species screen's arrows "
        "and keypad (0 to 9999) change it, and only Advertising changes B.",
    ),
)

NEW_GAME = (
    Fact(
        "A new game starts with $300, food, 1 dose of Growth Hormone and the starter eggs in "
        "slot #4. Difficulty carries over from the options.",
    ),
    Fact(
        "Starter eggs: 7 babies if Tank One, Tank Two and the selling tank are all empty (the "
        "isolation tank is not checked), otherwise 3, all at age 4. The "
        "first is always a Greenfin Spotanus (body 20, fin 16), the Magic Fish of Fertility: the "
        "code adds it with fixed genes and throws its Random(5) away (0x41FD7C).",
        subs=(
            "The other babies: the second has body and fin each Random(5) x 4 (0-16); the third body "
            "Random(5) x 4 + 4 (4-20) and fin 0; the fourth body Random(5) x 4 and fin 20; the fifth "
            "to seventh body and fin each Random(6) x 4 (0-20), where a roll of Greenfin Spotanus "
            "becomes a Spined Spotanus (fin 12), so there is never a second one.",
            "So a new game always gets one, but you can still end up without it: buying other eggs "
            "before hatching the starter eggs replaces them (\"Replace eggs in slot #4?\"), a full "
            "tank silently loses the baby, and the magic fish only counts (and is announced) once it "
            "is an adult, so a Spotanus that starves, is sold or is trashed while young is never "
            "found.",
        ),
    ),
    Fact(
        "Answering Yes to \"Would you like HELP the first time?\" turns on the tutorial, sets 2x "
        "speed and adds 4 teen fish at age 19. No sets Normal speed and adds none.",
    ),
)

GOALS = (
    Fact(
        "The only goal is finding all seven magic fish, which opens the win screen. No tutorial "
        "popup gives money or items.",
    ),
    Fact("The autosave runs every 30 real-life minutes, in any screen."),
)

DS_ANIMALS = (
    Fact(
        "The Puffer Fish, Sting Ray and Moray Eel ($1250 each) are tank companions built like the "
        "Golden Seahorse: they never age, eat, get sick, breed or get sold, and customers ignore "
        "them. Their effects count only in the tank they are in. \"Healthy, fed\" means not sick "
        "and food above 5.",
        patched=(("ds_store", "the effects below apply."),),
    ),
    Fact(f"Sting Ray: healthy, fed fish in its tank get {below(100, 82)} chance of +1 health each "
         "step."),
    Fact(
        "Puffer Fish: healthy, fed fish in its tank get +1 food each step, and "
        f"{below(100, 60)} chance of +1 more. With no Fish Food research this outpaces the step's "
        "-1.",
    ),
    Fact(
        f"Moray Eel: a fish in its tank that would die survives at health 10 on {below(10, 1)}. "
        "It counts while it swims and while it is in its rock.",
    ),
    Fact(f"Two Sting Rays or Puffer Fish in a tank each roll separately; extra Moray Eels add "
         f"nothing (one {below(10, 1)} roll per dying fish)."),
)

INDEX = (
    Fact(
        "The rolls that change fish, with their exact odds (the customers' own movement rolls "
        "are in Selling and customers):",
        subs=(
            f"Health: Temperature Regulator and Aeration System {at_most(100, 40)} each; Easy "
            f"{at_most(100, 30)}.",
            "Sickness: Random(10000) < X (see Sickness); fungus or ick "
            f"{chance(2, 1)}; Cleaning Snail {at_most(100, 49)}.",
            f"Food: Fish Food L2 {at_most(100, 60)}, L3 {at_most(100, 30)}; Plant of Incubation "
            f"(Nutrition with Fix Vanilla Bugs) {at_most(100, 20)}.",
            f"Growth fish {at_most(100, 10)}; Mutation fish {at_most(100, 15)}, then body or fin "
            f"and up or down {at_most(100, 49)} each.",
            f"Unknown Chemical {at_most(100, 25)}, then {at_most(100, 49)} twice.",
            f"Ick and Fungal Treatment: {below(100, 70)} / {below(100, 40)} / {below(100, 25)}.",
            "Fish Vitamins Random(10) + 6; Growth Hormone Random(5) + 2.",
            "Eggs: Random(2) + 3 babies; genes Random(6), Random(5) or Random(10). Starter "
            "eggs: Random(5) and Random(6) (see A new game).",
            "Selling: Random(900) <= T each real-life second; sick fish "
            f"{at_most(100, 20)}; customer walks to the tanks Random(100) < k.",
            f"New species price: Random(n), minus on {at_most(100, 49)}.",
            "Customers: crowd Random(2) (see Selling and customers).",
        ),
    ),
    Fact(
        "Every timer:",
        subs=(
            f"Age step: {STEP}.",
            "Fish and research update: every 301 real-life seconds or more on the tank screen, at "
            "once when it opens, and 11 real-life seconds after opening it or dropping eggs (see "
            "Time away for the other short waits).",
            "Pregnancy: 4 age steps.",
            "Research: about 49 age steps.",
            "Selling: one sale roll per real-life second; none for 5 real-life seconds after a "
            "sale; customers decide every quarter real-life second.",
            "Autosave: every 30 real-life minutes.",
        ),
    ),
)


if __name__ == "__main__":
    import sys

    import game_mechanics

    sys.stdout.write(game_mechanics.render_text(page()))
