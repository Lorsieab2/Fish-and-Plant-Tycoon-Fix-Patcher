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
        "at once when you open the tank screen or switch tanks, and 10 real-life seconds after "
        "either. In the store, the selling scene, the species screen or the options, nothing "
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
            "Up to 72 hours, by speed. 2x speed: up to 32400 s (108 steps) is kept, more becomes "
            "25200 s (84 steps). Normal: more than 25200 s becomes 25200 s (42 steps). 1/2 speed: "
            "more than 18000 s is raised to 25200 s (28 steps).",
            "So time away is not counted evenly. At Normal speed, 71 hours away gives 42 steps "
            "(7 hours' worth) and 73 hours away gives 432 steps (72 hours' worth).",
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
            "Each other sick fish in the same tank: +6 (not on Easy).",
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

FOOD = (
    Fact(
        "Food runs from 0 to 100. Feeding gives every live fish in the tank +50, capped at 100, "
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
        "She is due at her age + 3 and gives birth at the first update after that: 4 age steps, "
        "20, 40 or 60 real-life minutes at 2x speed, Normal and 1/2 speed. While she stays in the "
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
        patched=(("ds_fish", "when either parent has a DS gene, the DS game's rule applies: the "
                  "average, with an odd total rounded up or down at random, one roll per litter."),),
    ),
    Fact(
        "A baby born into a full tank (21 fish) is lost without a message. The game's "
        "\"One of your tanks is full!\" warning is never shown.",
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
        "every update for each step it takes plus one, when more than 270 real-life seconds have "
        "built up toward its next step; a success adds 1 age, with its own health, sickness and "
        "food step.",
        subs=(
            "Live play gives about 2, 3 or 4 rolls per step (2x speed, Normal, 1/2 speed); a long "
            "time away gives about 1 roll per step, because a catch-up is one update.",
        ),
    ),
    Fact(
        "Health, Orange Snooper (5, 8): +1 health to every fish in its tank, each age step, after "
        "the health change and before the clamp.",
    ),
    Fact(
        f"Mutation, Wasp Grouper (13, 6): at each birth in its tank, {at_most(100, 15)} chance to "
        "move the father's stored body or fin one step up or down before the babies' genes are "
        "averaged. Once per litter.",
        subs=("Stock bug: the fin step tests the body's value for its 0 and 20 bounce.",),
        patched=(("ds_fish", "the step can also go from 20 into the DS genes."),),
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
    Fact("A medicine or chemical acts on every fish in the tank you use it on. There is no "
         "cooldown: \"one drop every half hour\" is only advice."),
    Fact(
        "Ick Treatment ($30, 3 doses): each fish with ick is cured on Random(100) < C: Easy 70 "
        f"({chance(100, 70)}), Medium 40 ({chance(100, 40)}), Hard 25 ({chance(100, 25)}).",
    ),
    Fact(
        "Fungal Treatment ($40, 3 doses): the same for fungus. During the tutorial, while it asks "
        "you to breed, any medicine cures fungus every time.",
    ),
    Fact("Fish Vitamins ($140): each fish with health 1-99 gains 6-15 health (Random(10) + 6), "
         "capped at 100."),
    Fact(
        "Growth Hormone ($380): each fish aged 40 or less gains 2-6 age (Random(5) + 2). The skipped "
        "steps get no health, sickness or food changes, except on Hard.",
    ),
    Fact(
        f"Unknown Chemical ($650): each live fish (not the Golden Seahorse) is changed on "
        f"{at_most(100, 25)}. Then its body changes on {at_most(100, 49)}, otherwise its fin; "
        f"the gene moves one step up on {at_most(100, 49)}, otherwise down, but always down at 20 "
        "and always up at 0. One dose.",
        patched=(
            ("unknown_chemical_three_uses", "one purchase gives 3 doses."),
            ("ds_fish", "a body or fin at 20 can also step up into the DS genes (23-29), with the "
             "same odds; 29 is the new end."),
        ),
    ),
)

PERMANENT_ITEMS = (
    Fact(f"Aeration System ($70): {at_most(100, 40)} chance of +1 health per fish per step "
         "(blocked for a sick or hungry fish)."),
    Fact("Temperature Regulator ($175): the same, a second roll."),
    Fact(f"Cleaning Snail ($80): halves the sickness odds on {at_most(100, 49)}; it does nothing "
         "once you own the Plant of Curing."),
    Fact(
        "Golden Seahorse ($1300): no effect on fish. It brings 2 more customers to the selling "
        "scene and makes each customer 2 points more likely to walk to the tanks. Both count even "
        "after it is gone.",
        patched=(
            ("golden_seahorse_repurchase", "it can be bought again after it is gone."),
            ("ds_store", f"it also gives healthy, fed fish in its tank {below(100, 82)} chance of +1 "
             "health each step."),
        ),
    ),
    Fact(
        "The two plants do each other's job. The Plant of Incubation ($200, \"increases the "
        f"viability of purchased eggs\") rescues starving fish ({at_most(100, 20)}, food +5 per "
        "step). The Plant of Nutrition ($350) adds 1 egg to every egg batch.",
        patched=(("fix_vanilla_bugs", "the effects are swapped back: the Plant of Incubation adds the "
                  "egg (Exotic Fish Eggs too) and the Plant of Nutrition rescues starving fish. Names, "
                  "pictures and prices are unchanged, and plants already owned switch over."),),
    ),
    Fact("Plant of Curing ($650): always halves the sickness odds."),
    Fact("Plant of Fertility ($1250): one extra baby per litter."),
    Fact(
        "Ornaments (Shell $20, Pagoda $50, Diver $350, Fancy Coral $950, Sunken Antique Column $1500, "
        "Sunken Ship $3500): each brings 1 more customer to the selling scene. They are movable, "
        "6 per tank at most.",
    ),
    Fact("Second Tank ($450): a second full-size tank."),
)

RESEARCH = (
    Fact(
        "Each research line starts at level 1 and can be bought twice: Fish Food $200 then $650, "
        "Fish Environment $500 then $1750, Advertising $350 then $1500.",
    ),
    Fact(
        "A research gains 2 points for every age step's worth of real-life time and finishes at 100. "
        "It starts at 1 with one step already counted, so it takes about 49 steps: about 4 h 5 min, "
        "8 h 10 min or 12 h 15 min at 2x speed, Normal and 1/2 speed. Its timer is never capped, so "
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
    Fact("Fish Environment: only the rarity part of the health change (see Health)."),
    Fact(
        "Advertising: more customers and a higher chance that they walk to the tanks (see Selling "
        "and customers). On finishing level 2 every species' base price rises by a tenth, on level "
        "3 by a seventh; your asking prices stay, so they become better bargains.",
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
        "After a sale there is no other for 5 seconds.",
    ),
    Fact(
        "Each fish rolls Random(900) <= T, with K = (N + 2) / 2 rounded down and N the customers "
        "browsing or at the tank. P is your asking price, B the species' base price:",
        subs=(
            "P at least half below B: T = 30K. With no customers browsing, "
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
        "Each customer standing inside walks over to the tanks on Random(100) < k every quarter "
        "second, with k = magic species discovered + 2 x (Advertising level + Golden Seahorse). "
        f"Example: Advertising level 1 and nothing else, {below(100, 2)}.",
    ),
    Fact(
        "Thought bubbles are only hints and change nothing: a frowning \"$!\" means a fish is "
        "overpriced (2B or more, or half the time above 1.5B), a smiling \"$\" a bargain, a stinky "
        "fish a sick or dead one, a diver with \"?\" that customers want more ornaments, and a fish "
        "with \"?\" that no adult is for sale.",
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
        "Starter eggs: 7 babies if all three main tanks are empty, otherwise 3, all at age 4. The "
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
    Fact("Two or more of the same animal in a tank each roll separately."),
)

INDEX = (
    Fact(
        "Every gameplay roll, with its exact odds:",
        subs=(
            f"Health: Temperature Regulator and Aeration System {at_most(100, 40)} each; Easy "
            f"{at_most(100, 30)}.",
            "Sickness: Random(10000) < X (see Sickness); fungus or ick "
            f"{chance(2, 1)}; Cleaning Snail {at_most(100, 49)}.",
            f"Food: Fish Food L2 {at_most(100, 60)}, L3 {at_most(100, 30)}; Plant of Incubation "
            f"(Nutrition with Fix Vanilla Bugs) {at_most(100, 20)}.",
            f"Growth fish {at_most(100, 10)}; Mutation fish {at_most(100, 15)}.",
            f"Unknown Chemical {at_most(100, 25)}, then {at_most(100, 49)} twice.",
            f"Ick and Fungal Treatment: {below(100, 70)} / {below(100, 40)} / {below(100, 25)}.",
            "Fish Vitamins Random(10) + 6; Growth Hormone Random(5) + 2.",
            "Eggs: Random(2) + 3 babies; genes Random(6), Random(5) or Random(10).",
            "Selling: Random(900) <= T each second; sick fish "
            f"{at_most(100, 20)}; customer walks to the tanks Random(100) < k.",
            f"New species price: Random(n), minus on {at_most(100, 49)}.",
        ),
    ),
    Fact(
        "Every timer:",
        subs=(
            f"Age step: {STEP}.",
            "Fish and research update: every 301 real-life seconds or more on the tank screen, at "
            "once when it opens, and 10 seconds after opening it or dropping eggs.",
            "Pregnancy: 4 age steps.",
            "Research: about 49 age steps.",
            "Selling: one sale roll per real-life second; 5 seconds after a sale; customers decide "
            "every quarter second.",
            "Autosave: every 30 real-life minutes.",
        ),
    ),
)


if __name__ == "__main__":
    import sys

    import game_mechanics

    sys.stdout.write(game_mechanics.render_text(page()))
