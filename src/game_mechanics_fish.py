"""Fish Tycoon's Game Mechanics page: the facts.

Traced in the vanilla LDW "Fish Tycoon.exe" (v1.6.2). Every chance is the
game's own test with its exact odds (game_mechanics.chance).
"""

from __future__ import annotations

from game_mechanics import Fact, GamePage, Group, at_most, below, chance

STEP = "one age step (5, 10 or 15 real-time minutes at 2x speed, Normal and 1/2 speed)"


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
            "Two clocks (see Clocks for every timer). Game time is fish age steps: the speed option "
            "sets the real-time length of one step, 2x speed 5 minutes, Normal 10 minutes (the "
            "default), 1/2 speed 15 minutes, and Stop Time pauses it; it keeps counting while the "
            "game is closed. Real time is the wall clock: it ignores the speed setting, and most "
            "real-time timers only run while the game is open, in their own screen. A fish is a "
            "baby at age 1-5, a teen at 6-19 and an adult from 20 (game time). \"Per step\" means "
            "once per age step of each fish. Difficulty is Easy, Medium (the default) or Hard."
        ),
        groups=(
            Group("Clocks", CLOCKS),
            Group("Time away (catch-up)", TIME_AWAY),
            Group("Which tank counts", SCOPE),
            Group("Ages and stages", AGES),
            Group("Health", HEALTH),
            Group("Sickness", SICKNESS),
            Group("Food", FOOD),
            Group("Breeding and babies", BREEDING),
            Group("Eggs", EGGS),
            Group("Magic fish", MAGIC_FISH),
            Group("Magic fish one by one: how to get each", MAGIC_HOW),
            Group("Medicines and chemicals", CONSUMABLES),
            Group("Permanent store items", PERMANENT_ITEMS),
            Group("Research", RESEARCH),
            Group("Everything together: a tank with every upgrade, research and creature", TOTALS),
            Group("Selling and customers", SELLING),
            Group("Species and prices", PRICES),
            Group("A new game", NEW_GAME),
            Group("Goals and popups", GOALS),
            Group("DS store animals", DS_ANIMALS,
                  note="Only with the DS Store Items setting. The store calls them \"magically enhancing\"; "
                       "these are their real effects."),
            Group("3 extra tanks (patcher)", EXTRA_TANKS,
                  note="Only with the 3 extra tanks setting (off by default)."),
            Group("Time Warp (patcher)", TIME_WARP, note="Only with the Time Warp setting (off by default), which also turns on the store's Upgrades screen it lives on."),
            Group("Hidden keys, clicks and cheats", HIDDEN),
            Group("Plant Tycoon's topics here", OTHER_GAME),
            Group("Chance and timer index", INDEX),
        ),
    )


CLOCKS = (
    Fact(
        "Game time = age steps (5, 10 or 15 real-time minutes at 2x speed, Normal and 1/2 speed). "
        "It is the wall clock turned into steps, so it keeps counting while the game is closed (the "
        "save keeps the clock), caught up when the tank screen next updates (see Time away). Stop "
        "Time throws the banked time away. Game time runs: fish ageing, health, sickness, food, "
        "breeding and pregnancy (4 age steps), and research (about 49 age steps).",
    ),
    Fact(
        "Real time = the wall clock or the game's own tick counter, the same at every speed. None "
        "of these timers is paused by Stop Time except the ambient sounds, and none counts while "
        "the game is closed:",
        subs=(
            "Fish update check: every 301 real-time seconds or more, only while the tank screen is "
            "open (see Time away for the short waits).",
            "Selling: one sale roll per real-time second while the selling scene is open, none for "
            "5 real-time seconds after a sale. It keeps rolling while a message box covers the "
            "selling scene (code reading, not seen live).",
            "Customers decide every quarter real-time second (26 hundredths in practice); they "
            "stand still while a message box is open.",
            "Autosave: every 30 real-time minutes from the game's start, in any screen, but not "
            "while a message box is open.",
            "Thought bubbles and the shop's click texts stay 4-5 real-time seconds; tank hints 2 "
            "real-time seconds.",
            "Ambient tank sounds: every 210 real-time seconds on the tank screen (the first 630 "
            "real-time seconds after the intro); skipped under Stop Time.",
            "Tutorial waits (real-time): the next tip 25 seconds after a mating, 500 seconds (shown "
            "at the first fish update after that, so 500-801 seconds) after the \"basics\" tip, "
            "7 seconds after returning from the species screen. The three share one timer, so a "
            "later one replaces an earlier one. They start over after a restart.",
            "Splash screen: 3 real-time seconds (6 in the full version). The \"Real Hours Played\" "
            "statistic counts real time from your first tank visit to quitting, this session only.",
        ),
    ),
    Fact(
        "While a message box is open (tips, Buy?, Options, Statistics, Unlock), the screen behind "
        "it is still drawn but its update stops: fish do not update, customers freeze, and the "
        "autosave waits. The game keeps running when it is not the active window or is minimised.",
    ),
    Fact(
        "Speed 1/2 speed, Normal and 2x speed change only game time. Stop Time pauses fish steps, "
        "research and the ambient sounds; nothing else checks it.",
    ),
)

TIME_AWAY = (
    Fact(
        "Fish only update while the tank screen is open: once every 301 real-time seconds or more, "
        "at once when you open the tank screen or switch tanks, and again 11 real-time seconds "
        "later; also 2 real-time seconds after the Unknown Chemical, 8 after Growth Hormone, 5 "
        "after the starter eggs and 11 after other eggs. It is put off 10 real-time seconds while "
        "you drag a fish. In the store, the selling scene, the species screen or the options, nothing "
        "updates; the time is caught up the next time the tank screen opens.",
    ),
    Fact(
        "Every update covers all four tanks (Tank One, Tank Two, the selling tank and the "
        "isolation tank), whichever is on screen.",
        patched=(("extra_tanks", "and Tank Three, Tank Four and Tank Five, with the same catch-up."),),
    ),
    Fact(
        "An update turns each fish's banked real time into age steps and runs every step's "
        "health, sickness, food and death checks one by one. The time banked at once is capped:",
        subs=(
            "More than 72 real-time hours (259200 s) banked: 72 hours of steps, so 864 steps at 2x "
            "speed, 432 at Normal and 288 at 1/2 speed.",
            "Up to 72 real-time hours, by speed. 2x speed: up to 32400 real-time seconds (108 "
            "steps) is kept, more becomes 25200 s (84 steps). Normal: more than 25200 real-time "
            "seconds becomes 25200 s (42 steps). 1/2 speed: more than 18000 real-time seconds is "
            "raised to 25200 s (28 steps).",
            "So time away is not counted evenly. At Normal speed, 71 real-time hours away gives 42 "
            "steps (7 hours' worth) and 73 real-time hours away gives 432 steps (72 hours' worth).",
            "The rest of the banked time below one step is kept for the next update.",
        ),
    ),
    Fact(
        "Stop Time: no fish ages, eats, gets sick or dies, and research stops. Paused real time "
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
        "30 real-time seconds ago.",
    ),
)

AGES = (
    Fact("Babies are 1-5, teens 6-19, adults 20 and up. A fish shows as a baby from age 1."),
    Fact(
        "From an egg (age 1) to adult (20) is 19 steps: 95, 190 or 285 real-time minutes at 2x "
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
        "Quick answers: does it have to be in the selling tank (or any particular tank)?",
        subs=(
            "Ornaments: no. Each one owned adds a customer wherever it is, and it can never be "
            "thrown away.",
            "Golden Seahorse and customers: it does not need to be in the selling tank. Its 2 more "
            "customers and walk-over points come from owning it, from any tank, even after it is "
            "gone.",
            "Golden Seahorse's DS-exclusive health bonus (with DS Store Items): it works only on "
            "the fish in the tank the seahorse is swimming in (see Permanent store items).",
            "Magic fish: to be found, a live adult in any tank (then it counts for customers "
            "forever, even if it dies). For its effect, yes: it must be a live adult in the same "
            "tank as the fish it acts on (Fertility and Mutation: the tank where the mother gives "
            "birth). Selling-tank fish only get it from a magic fish in the selling tank.",
            "Plants, snail, aerator, regulator and research: no, they work in every tank.",
        ),
        patched=(("ds_store", "Puffer Fish, Sting Ray and Moray Eel: yes, each acts only on the "
                  "fish in its own tank, and a creature in the selling tank is never sold."),),
    ),
    Fact(
        "Do duplicates stack? (two or more of the same thing)",
        subs=(
            "Magic fish: no. Two of the same magic fish in a tank work exactly like one (the game "
            "only checks whether at least one live adult is there): still one extra baby, still +1 "
            "health, one Growth or Mutation roll.",
            "Ornaments, plants, the snail, the aerator, the regulator and the Second Tank: each can "
            "only be bought once, so there are no duplicates.",
            "Golden Seahorse, stock effects: no. More seahorses (with Buy Multiple Golden "
            "Seahorses) add no more customers or walk-over points; owning one is what counts.",
        ),
        patched=(("ds_store", f"the DS-exclusive effects: Golden Seahorse and Sting Ray stack, "
                  f"each one in a tank gives its own {below(100, 82)} roll for +1 health; Puffer "
                  f"Fish stack, each one gives +1 food and its own {below(100, 60)} roll for +1 "
                  f"more (food and health still cap at 100); Moray Eels do not stack, a dying fish "
                  f"gets one {below(10, 1)} roll however many eels are in the tank."),),
    ),
    Fact(
        "Every update runs all four tanks together: the first tank, Tank Two, the selling tank and "
        "the isolation tank. A tank you are not looking at keeps going (0x41FE70, tanks 0-3).",
        patched=(("extra_tanks", "Tank Three, Tank Four and Tank Five too, by a second run of the same "
                  "update (see 3 extra tanks)."),),
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
        "after mating, which is 3 to 4 step lengths of real time (her part-step already banked "
        "counts): 15-20, 30-40 or 45-60 real-time minutes at 2x speed, Normal and 1/2 speed. While she stays in the "
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
                  "23-29, 1 in 7 each)."),
                 ("free_upgrades", "Exotic Fish Eggs cost $0."),),
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
        "every update for each step it takes plus one, when the fish's banked real time "
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

MAGIC_HOW = (
    Fact(
        "How a magic fish is found: at a fish update (the tank screen, see Clocks), any tank holding "
        "a live adult (age 20 or more) of the species. The first one sets the species' asking "
        "price and shows its message once (\"You discovered the Magic Fish of ...! ... This fish "
        "was added to your trophy case.\"), with either answer to the tutorial question. It stays "
        "found for the rest of the game, even if the fish dies. Each one found is +1 to the "
        "customers' walk-over roll and lights a decal on the tank's top strip.",
        subs=(
            "Breeding: a baby's gene is the parents' genes averaged and rounded down, so gene t "
            "needs parents adding up to 2t or 2t + 1. Gene 20 needs both parents at 20. Two Common "
            "or two Unusual eggs' fish give only even genes; a Common with an Unusual gives odd "
            "ones.",
            "Rare-gene fish (any odd gene) lose 19 health an age step at Fish Environment level "
            "1 and cannot grow up from an egg there: research Environment, or skip ages with "
            "Growth Hormone, or make an adult one with the Unknown Chemical.",
            "Unknown Chemical: per dose, each fish in the tank moves one particular gene one "
            "particular way on about 6.5% (body +1 6.52%, body -1 6.51%, fin +1 6.51%, fin -1 "
            "6.49%), so a fish one step from a magic one becomes it on about 6.5% per dose.",
        ),
        patched=(("ds_fish", "the DS genes add routes, never remove one: a DS gene 23 can step "
                  "down to 20, and a DS x PC pair averages over the DS order (for example a DS "
                  "parent 21 with a PC 19 always gives 20). Exotic Fish Eggs hatch only DS genes, so "
                  "never a magic fish."),),
    ),
    Fact(
        "Fertility, Greenfin Spotanus (body 20, fin 16), common genes, base price B = 48.",
        subs=(
            "Every new game: the first starter egg is always one (see A new game).",
            "Common Fish Eggs: 2.777% per egg. Never from Unusual or Rare eggs.",
            "Breeding: both parents need body 20; for example Spined Spotanus (20, 12) x Twin-Fin "
            "Spotanus (20, 20), both from Common eggs, or two Greenfin Spotanus.",
            "Unknown Chemical from (19, 16), (20, 15) or (20, 17).",
            "Effect: one more baby per litter in its tank.",
        ),
    ),
    Fact(
        "Sustenance, Speckled Leaffish (14, 14), half-rare genes, B = 55.",
        subs=(
            "Unusual Fish Eggs: 3.999% per egg; Rare Fish Eggs: 1.000% per egg. Never from Common "
            "eggs.",
            "Breeding: Spined Stickfish (12, 12) x Greenfin Beta (16, 16), both Common; or Flagged "
            "Goldbulb (10, 18) x Golden Bananafish (18, 10), both Unusual.",
            "Unknown Chemical from (13, 14), (15, 14), (14, 13) or (14, 15).",
            "Effect: starving fish in its tank never lose health. Its message says you won't need "
            "to feed as often; food still drops at the normal rate.",
        ),
    ),
    Fact(
        "Curing, Crimson Comet (11, 11), rare genes, B = 70.",
        subs=(
            "Never from eggs. Breeding a Common with an Unusual: Orange Fruitfish (8, 8) x Speckled "
            "Leaffish (14, 14), Spined Stickfish (12, 12) x Golden Goldbulb (10, 10), or Pink "
            "Fatfish (4, 4) x Flagged Bananafish (18, 18).",
            "Unknown Chemical from (10, 11), (12, 11), (11, 10) or (11, 12).",
            "Effect: none in the unpatched game (its cure can never happen; see Magic fish).",
        ),
        patched=(("crimson_comet_20_percent_cure", f"each sick fish in its tank is cured on "
                  f"{below(100, 20)} per age step."),),
    ),
    Fact(
        "Growth, Oriental Goldbulb (10, 9), rare genes, B = 70.",
        subs=(
            "Never from eggs. Breeding needs a Rare-egg or bred parent: Golden Stickfish (12, 10) "
            "x Orange Fruitfish (8, 8), Orange Goldbulb (10, 8) x Golden Goldbulb (10, 10), or "
            "Spined Leaffish (14, 12) x Wasp Goldshark (6, 6).",
            "Unknown Chemical from (9, 9), (11, 9), (10, 8) or (10, 10).",
            "Effect: fish in its tank sometimes gain an extra age step (see Magic fish).",
        ),
    ),
    Fact(
        "Health, Orange Snooper (5, 8), rare genes, B = 70.",
        subs=(
            "Never from eggs. Breeding: Orange Arrowfish (2, 8) x Orange Fruitfish (8, 8), Orange "
            "Goldshark (6, 8) x Orange Fatfish (4, 8), or Pink Shark (0, 4) x Spined Goldbulb (10, "
            "12).",
            "Unknown Chemical from (4, 8), (6, 8), (5, 7) or (5, 9).",
            "Effect: +1 health per age step to every fish in its tank.",
        ),
    ),
    Fact(
        "Mutation, Wasp Grouper (13, 6), rare genes, B = 95.",
        subs=(
            "Never from eggs. Breeding: Pink Goldbulb (10, 4) x Orange Beta (16, 8), Wasp Leaffish "
            "(14, 6) x Wasp Stickfish (12, 6), or Hornet Bananafish (18, 2) x Golden Fruitfish (8, "
            "10).",
            "Unknown Chemical from (12, 6), (14, 6), (13, 5) or (13, 7).",
            "Effect: a 16.02% chance per litter in its tank to move one of the father's genes one "
            "step. Its message says babies can be unrelated to either parent; the change is one "
            "step at most.",
        ),
    ),
    Fact(
        "The Golden Guppy, Canary Fire-Arrow (7, 7), rare genes, B = 190, the highest base price.",
        subs=(
            "Never from eggs. Breeding a Common with an Unusual: Pink Fatfish (4, 4) x Golden "
            "Goldbulb (10, 10), Orange Fruitfish (8, 8) x Wasp Goldshark (6, 6), or Silky "
            "Stickfish (12, 0) x Speckled Arrowfish (2, 14).",
            "Unknown Chemical from (6, 7), (8, 7), (7, 6) or (7, 8).",
            "Effect: none (its message says it will make you rich; only its high price does). It "
            "counts toward the seven.",
        ),
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
        "scene and makes each customer 2 points (out of 100, every quarter real-time second) more "
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
        "The Golden Seahorse's health and food meters (shown while you hold it) start at health "
        "80-94 (80 + Random(15)) and food 50. Nothing in the game lowers "
        "them: its age step is skipped, so it never goes hungry, loses health or dies, and "
        "overfeeding never hurts it. Feeding its tank raises its food by 50, up to 100, as for a fish.",
        patched=(("fix_vanilla_bugs", "it arrives with health 100 and food 100, and a seahorse already "
                  "in a save is filled to 100 and 100 the first time the save is loaded; it then stays "
                  "full."),),
    ),
    Fact(
        "Does the Golden Seahorse have to be in a particular tank? Its stock effects (2 more "
        "customers, 2 walk-over points) do not care: they come from owning it, from any tank, and "
        "stay after it is gone.",
        patched=(("ds_store", f"its DS health bonus does care: it works only in the tank the "
                  f"seahorse is swimming in (Tank One, Tank Two or the selling tank; never the "
                  f"isolation tank), and only while it is there. Each age step, every fish in that "
                  f"tank that is not sick, has food above 5 and is alive gets {below(100, 82)} for "
                  "+1 health (capped at 100); the seahorse itself and the other creatures get "
                  "nothing. Two seahorses in one tank (with Buy Multiple Golden Seahorses) roll "
                  "twice, and a Sting Ray in the same tank adds its own roll."),),
    ),
    Fact(
        "A Golden Seahorse in the selling tank is never sold in normal play. The stock sale code "
        "(0x424240, run every real-time second) does not check for it, so it does look at it as a "
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
        "tank it is in: they do not need to be in the selling tank (the customer count reads only "
        "which ornaments you own). That is their only effect. An ornament can never be thrown "
        "away (the trash can ignores them), so once bought it counts for the rest of the game.",
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
        "A research gains 2 points for every age step's worth of real time and finishes at 100. "
        "It starts at 1 with one step already counted, so it takes about 49 steps: about 4 h 5 min, "
        "8 h 10 min or 12 h 15 min of real time at 2x speed, Normal and 1/2 speed. Its timer is never capped, so "
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
            "Customers walk to the tanks more often: +2 points per level on the quarter real-time second "
            "Random(100) roll (see Selling and customers).",
            "On finishing level 2 every species' base price rises by a tenth, on level 3 by a "
            "seventh; your asking prices stay, so they become better bargains (higher sale odds).",
            "The shop's posters change at levels 2 and 3; that is only for show.",
        ),
    ),
)

TOTALS = (
    Fact(
        "Health per age step for one fish that is not sick and has food 5 or more (above 5 for the "
        "DS creatures), with Fish Environment level 3, the Aeration System and the Temperature "
        "Regulator, on Medium:",
        subs=(
            f"Environment level 3: common genes +5, half-rare +3, rare 0. Aeration System and "
            f"Temperature Regulator: {at_most(100, 40)} each for +1, so +0.82 on average.",
            "A live adult Orange Snooper (Magic Fish of Health) in the same tank: +1 more.",
            f"With DS Store Items, each Golden Seahorse and each Sting Ray swimming in the same "
            f"tank: {below(100, 82)} for +1 more, so +0.82 on average each.",
            "Averages with the Snooper: common +6.8, half-rare +4.8, rare +1.8 a step; add +0.82 "
            "for each seahorse or Sting Ray. Health never goes above 100. On Easy add "
            f"{at_most(100, 30)} for +1.",
            "A sick fish gets none of the plus side and loses 1; a fish with food below 5 gets none "
            "of it either.",
        ),
    ),
    Fact(
        "Food per age step with Fish Food level 3: -1 on " + at_most(100, 30) + " (-0.31 on "
        "average). With DS Store Items, each Puffer Fish in the tank gives a healthy, fed fish +1 "
        f"and {below(100, 60)} for +1 more (+1.60 on average), so with one Puffer food goes up by "
        "about 1.29 a step instead of down (capped at 100). A starving fish (food 2 or less) with "
        "the starvation plant owned gets " + at_most(100, 20) + " for +5 food, and with a "
        "Speckled Leaffish (Magic Fish of Sustenance) in the tank it never loses health to "
        "starvation.",
    ),
    Fact(
        "Sickness with Fish Food level 3 and the Plant of Curing: the base odds out of 10000 per "
        "step are common 1, half-rare 3, rare 5, halved by the Plant of Curing (the Cleaning Snail "
        "adds nothing on top). Medicines cure as usual; the Crimson Comet only cures with its "
        "patch.",
    ),
    Fact(
        "Death: a fish whose health reaches 0 dies, unless (with DS Store Items) a Moray Eel is in "
        f"the tank: then it survives at health 10 on {below(10, 1)}.",
    ),
    Fact(
        "Breeding with everything: a litter is 3 babies (1, +1 Plant of Fertility, +1 Magic Fish "
        "of Fertility in the mother's tank); eggs hatch 4 or 5 (+1 from the egg plant), 5 or 6 on "
        "Easy.",
    ),
    Fact(
        "Customers with everything: 4 + 6 ornaments + 2 for the Golden Seahorse + 6 x (adults in "
        "the selling tank / 3, rounded down, + 2 or 3) with Advertising level 3, and each customer "
        "walks to the tanks on Random(100) < 7 + 2 x 3 + 2 = up to 15 (15.01%) with all seven magic "
        "fish found. None of this depends on which tank the ornaments, seahorse or magic fish are "
        "in.",
    ),
)

SELLING = (
    Fact(
        "Customers: 4 + 1 per ornament owned + 2 for the Golden Seahorse + 2 x Advertising level x "
        "(adults in the selling tank / 3, rounded down, + Random(2) + 2). Counted once each time you "
        "open the selling scene; they keep coming and going until you leave.",
    ),
    Fact(
        "Selling only happens while the selling scene is open. Once every real-time second, the "
        "adults in the selling tank are tried in slot order; the first that sells ends that second. "
        "After a sale there is no other for 5 real-time seconds.",
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
        "Every quarter real-time second (0.26 s in practice), each customer standing inside first "
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
        "The only goal is finding all seven magic fish. The seventh one's message is followed by "
        "the win screen (\"You have discovered the 7 Magic Fish of Isola! The lagoon and the "
        "ecosystem are saved...\"); a click or key goes back to the tank. It gives no money or "
        "reward, the game goes on, and it shows once per game. No tutorial popup or research "
        "popup gives money or items.",
    ),
    Fact(
        "Trophy Case (the strip at the top of the tank screen): the seven magic fish, each drawn "
        "with its name once found, or a \"?\" and \"#k/7\" until then. Clicking a found one "
        "shows its title (\"The Magic Fish of Fertility\" ...) for 2-3 real-time seconds; nothing "
        "else. Stats opens the Statistics screen.",
    ),
    Fact(
        "Statistics: Real Hours Played (real time since the game began), Units of Food Given, Fish "
        "Trashed, Fish Cured, Fish Sold, Average Price per Fish, Money Earned, Money Spent, Species "
        "Discovered and Magic Fish Found. None changes the game. Species discovery (a live adult of "
        "any species) only sets its asking price and counts here and on the shop poster.",
    ),
    Fact(
        "Not reachable (dead code): a second win popup text (\"Congratulations! You discovered the "
        "7 Magic Fish of Isola! The island is restored!...\") and a \"tank full\" popup are never "
        "queued.",
    ),
    Fact("The autosave runs every 30 real-time minutes, in any screen (not while a message box is "
         "open)."),
)

DS_ANIMALS = (
    Fact(
        "The Puffer Fish, Sting Ray and Moray Eel ($1250 each) are tank companions built like the "
        "Golden Seahorse: they never age, eat, get sick, breed or get sold, and customers ignore "
        "them. Their effects count only in the tank they are in. \"Healthy, fed\" means not sick "
        "and food above 5.",
        patched=(("ds_store", "the effects below apply."),
                 ("free_upgrades", "they cost $0 (still one of each in your tanks, unless Buy Multiple "
                  "Golden Seahorses is on)."),),
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
    Fact(
        "Their health and food meters work like the Golden Seahorse's: nothing in the game lowers "
        "them, and feeding their tank raises their food. A Moray Eel in its rock keeps its meters "
        "in the rock.",
        patched=(("ds_store", "they arrive with health 100 and food 100, and every Puffer Fish, Sting "
                  "Ray and Moray Eel already in a save (an eel in its rock too) is filled to 100 and 100 "
                  "the first time the save is loaded; they then stay full."),),
    ),
)

EXTRA_TANKS = (
    Fact(
        "Tank Three, Tank Four and Tank Five are full tanks like Tank One and Tank Two. The game itself "
        "has room for four tanks only (Tank One, Tank Two, the Sale Tank and the isolation tank, each a "
        "0x51EC-byte block of the game's state at 0x390 + tank x 0x51EC, the species table straight after), "
        "so the patcher keeps three more blocks of the same layout and runs the game's own code on them.",
        label="E",
    ),
    Fact(
        "How to reach them: either of the two small arrows left of the Tank One button switches the three "
        "tank buttons to Tank Three, Tank Four and Tank Five, and back. Click a button to look at that tank. "
        "Drag a fish, animal or ornament onto a button to move it there, or onto the left or right arrow to "
        "move it to the previous or next tank (Tank One, Tank Two, the Sale Tank, Tank Three, Four, Five, "
        "and round again): into the first free place, up to the tank's size (21 fish, or more with the "
        "tank size setting; six ornaments), by the game's own code, and \"The tank is full!\" when there "
        "is none, as on the stock buttons.",
        label="E",
    ),
    Fact(
        "The tank you look at is put in Tank One's place while you look at it (Tank One waits in the "
        "patcher), so everything you use acts on it exactly as on a stock tank: food (the isolation fish "
        "fed too), the Ick and Fungal Treatments, Vitamins, Growth Hormone, the Unknown Chemical, eggs, "
        "ornaments and the trash. It is drawn with Tank One's background.",
        label="E",
    ),
    Fact(
        "How they tick: each fish update, the game's own update runs once more with the three blocks the "
        "patcher holds in the places of Tank One, Tank Two and the Sale Tank and an empty isolation tank. "
        "Every fish keeps its own clock, so an extra tank's fish age, eat, heal, get sick, breed, give "
        "birth and die exactly as in a stock tank, also after time away (the same 72-hour cap). Magic "
        "fish, the Wasp Grouper and DS store animals count only in their own tank; research, the plants "
        "and owned items count everywhere, as in every tank. Research gains nothing from the second run.",
        label="E",
    ),
    Fact(
        "Selling is unchanged: only the Sale Tank sells, and the extra tanks are never in its place "
        "while anything but the fish update runs. The number of fish for sale, customers and the sale "
        "scene see the Sale Tank only, with the stock limit (the tank's size).",
        label="E",
    ),
    Fact(
        "Saved per save slot in \"Fish Tycoon Fix Patcher Data\\Extra Tanks <slot>.dat\" beside the "
        "saves, written whenever the game saves (on quitting and the 30-minute autosave), after the "
        "save itself; the save file keeps its stock layout, with Tank One in its place. A missing file "
        "means empty extra tanks; a damaged one is set aside, never deleted, and a new game empties them.",
        label="E",
    ),
    Fact(
        "The starter eggs count a fish in an extra tank as a fish in a tank (3 eggs, not 7). The stock "
        "Golden Seahorse still goes to Tank One first (with DS Store Items, to the tank you came from).",
        label="E",
    ),
    Fact(
        "Not the same as a stock tank: the background (always Tank One's); with Buy Multiple Golden "
        "Seahorses off, DS Store Items does not see a store animal kept in an extra tank you are not "
        "looking at, so it can be bought again; the tutorial's sick-fish step can pick an extra tank's "
        "fish while you look at it.",
    ),
)

HIDDEN = (
    Fact(
        "Hidden typed cheats on the tank screen (lowercase letters only; Shift or Caps Lock stops "
        "them). They work in every game, with no setting or debug mode, while the tank screen is "
        "up and the screensaver is off (handler 0x41ED10):",
        subs=(
            "c: +$1000 cash per press, no limit.",
            "u: marks this copy as the full (registered) version for the session, which unlocks "
            "the store's full-version-only items. Whether it lasts after a restart was not "
            "checked.",
            "w: shows the game-win screen within a fraction of a real-time second. It changes "
            "nothing: no magic fish is found or saved, and any click or key goes back to the "
            "tank.",
        ),
    ),
    Fact(
        "Add Money: not in the unpatched game. Money is a signed 32-bit number (state+0x38C), "
        "so it cannot go past $2,147,483,647; the stock sale (0x424074) and the c cheat add to it "
        "with no check.",
        patched=(("add_money", "a pile of gold coins on the Supplies store's Upgrades page, next to the "
                  "Time Warp clock: $950 ($0 with Free upgrades), the game's purchase question, then "
                  "+$1,000, any number of times. It stops at $2,147,483,647 and never wraps."),),
    ),
    Fact(
        "Hidden click on the tank screen: the strip at the top of the tank, from (212, 4) to (480, "
        "44), opens the Trophy Case. There is no button there.",
    ),
    Fact(
        "Hidden clicks in the selling shop (\"Click around the shop for hidden tips!\"): each spot "
        "plays a sound and shows a line of text for 4-5 real-time seconds. None changes the game:",
        subs=(
            "Left of the window, (65, 111)-(103, 216): a random game tip (below). The first click "
            "in a tutorial game shows the fragile-hybrids tip instead.",
            "The poster, (118, 74)-(218, 141): \"You have discovered N species!\". The first click "
            "in a tutorial game shows the poster tip, which says clicking the poster again gives "
            "game tips; the code gives tips on the other spot, so the poster only shows the "
            "species count.",
            "(229, 139)-(335, 174): \"You have cured N fish!\". (342, 66)-(456, 106): \"You have "
            "fed your fish N times!\". (29, 266)-(99, 326): \"You have earned N Isola-bucks so "
            "far!\". (185, 146)-(230, 191): \"You have trashed N fish!\".",
            "(2, 325)-(36, 361) and (649, 122)-(729, 213): \"You have bought N of the 4 Magic "
            "Plants!\".",
            "(337, 111)-(637, 186), the selling tank: a sound only.",
            "With Advertising level 2 or 3, the bag display at (100, 231)-(145, 270): \"You have "
            "sold N fish!\". Level 2 also adds small plants and level 3 a sign and a sale sign; "
            "those have no click of their own.",
            "A click anywhere else on a customer makes it show a thought bubble.",
        ),
    ),
    Fact(
        "The random shop tip is one of 40, picked by Random(40): tips 1-8 2.502% each, 9-40 "
        "2.499% each (tip 20 and tip 28 are the same text, so that text is 5.0%). There is no "
        "memory, so a tip can repeat. The texts are the game's own and some are wrong (see the "
        "notes after the list):",
        subs=(
            "1. Did you know there are over 400 species of fish?",
            "2. If your baby fish are dying, research Fish Environment!",
            "3. The fish's 'age' does not refer to years, but more like hours.",
            "4. Most fish are inexpensive, but some are worth more than $300!",
            "5. Meds don't always work in one try.",
            "6. Breeding two identical fish produces offspring of the same species.",
            "7. New breeds start with a price somewhere near their true value.",
            "8. If you'd like to feed your fish less often, research better Food.",
            "9. Researching Fish Food makes fish get sick less often.",
            "10. Any adult fish in your selling tank can be purchased by customers in the store.",
            "11. Fish keep growing (and getting hungry!) even when the game is off.",
            "12. One way to find the Magic Fish is to keep track of every species combination.",
            "13. If you price your fish too high, they will sell slowly or not at all.",
            "14. If you price your fish too low, they will sell very fast but will make little money.",
            "15. Growth Hormone affects each fish a little differently.",
            "16. You cannot have more than 20 fish per tank.",
            "17. Fish from Isola don't die of old age!",
            "18. There is more than one approach to solving the game.",
            "19. Changing the price of a fish will change it for all fish of that species.",
            "20. To change the price of a species, use the 'Species' button.",
            "21. Diseases spread to other fish in the same tank!",
            "22. Ornaments help bring people into your store.",
            "23. Magic Fish help bring people into your store.",
            "24. Having lots of fish for sale helps bringing people into your store.",
            "25. Sick fish cannot be impregnated.",
            "26. Compare your game stats with those of other players via the Statistics Screen.",
            "27. You can click on the Magic Fish in the trophy case.",
            "28. To change the price of a species, use the 'Species' button.",
            "29. You can change the speed of time in the options menu.",
            "30. The cleaning snails reduce disease in every tank.",
            "31. Here on Isola, we use Isola-bucks!",
            "32. Magic Fish only affect fish in the tank they are swimming in.",
            "33. Dead Magic Fish are no longer beneficial.",
            "34. Dead fish increase disease among your fish.",
            "35. You can move ornaments between tanks.",
            "36. Researching Advertising will have a huge effect on crowds in your store.",
            "37. If you often have dead baby fish, research Fish Environment.",
            "38. Often the more fragile fish are more valuable.",
            "39. Hybrids are very fragile. They need more advanced Environment.",
            "40. Extremely rare hybrids are extremely fragile.",
            "Notes: tip 16 says 20 fish per tank; a tank holds 21. Tip 17 says fish don't die of "
            "old age; that is right, they only die of health 0.",
        ),
    ),
    Fact(
        "Tutorial tips (only in a game started with Yes to help): each shows once, one at a time, "
        "when its trigger happens (see Goals and popups). A message box closes with Escape or "
        "Return.",
    ),
    Fact(
        "Ordinary keys nobody mentions:",
        subs=(
            "Tank screen: Escape opens the main menu. In screensaver mode any key or click ends "
            "it and updates the fish at once.",
            "Species screen: number keys (top row or keypad) type the selected species' price, "
            "like the on-screen keypad, up to 4 digits; Escape is Done.",
            "Selling scene and Supplies store: Escape is Done. Trophy Case: Escape goes back.",
            "Message boxes: Return is the first button; Escape closes or cancels.",
            "Alt+F4 or closing the window quits.",
        ),
    ),
    Fact(
        "Not reachable (dead code, so nothing the player can do): a \"This copy of Fish Tycoon has "
        "expired\" check (its switch is never set), a Backspace branch on the species screen "
        "(the game never sends that key code), and F-keys, arrows, Tab and Delete (no screen "
        "uses them).",
    ),
    Fact(
        "The stores handle no hidden keys. The Supplies store (key handler 0x428770, shared with "
        "the Trophy Case) and the selling shop (key handler 0x423DB0) each react only to Escape "
        "(Done). No key redraws, restocks or reprices anything. Nothing in the Fish Tycoon store "
        "has a stock or a timer: medicines, chemicals and eggs can be bought at any time (one "
        "batch per supply slot), each permanent item and ornament once, and one research at a "
        "time; asking prices change only on the species screen.",
    ),
    Fact("The patcher adds no keys. Its additions are clicks: the store's Upgrades button, the DS "
         "animals (with DS Store Items) and the Time Warp clock (with Time Warp)."),
)

OTHER_GAME = (
    Fact('Where things count: see Which tank counts.'),
    Fact('Water: not in Fish Tycoon. Fish have food instead (see Food).'),
    Fact('Health and soil: see Health. Soil is not in Fish Tycoon; Fish Environment research plays its part (see Research).'),
    Fact('Pests: see Sickness (ick and fungus).'),
    Fact('Size: not in Fish Tycoon; fish have no size.'),
    Fact('Flowers: not in Fish Tycoon.'),
    Fact('Pollination and seeds: see Breeding and babies.'),
    Fact('Mutation Liquid: see the Unknown Chemical (Medicines and chemicals) and the Mutation fish (Magic fish).'),
    Fact("Shop seeds: see Eggs. Fish Tycoon's store has no daily stock (see Hidden keys, clicks and cheats)."),
    Fact('Selling and visitors: see Selling and customers.'),
    Fact('Prices: see Species and prices.'),
    Fact('Tools and shears (upgrades): not in Fish Tycoon; its permanent items and research take their place (see Permanent store items and Research).'),
    Fact('Chemicals: see Medicines and chemicals.'),
    Fact('Nursery ornaments: see the ornaments in Permanent store items.'),
    Fact('Magic plants: see Magic fish and Magic fish one by one.'),
    Fact('Everything together: a pot with every upgrade and magic plant: see Everything together: a tank with every upgrade, research and creature.'),
    Fact('Bugs (a collection): not in Fish Tycoon; the Trophy Case of magic fish is its only collection (see Goals and popups).'),
    Fact('Goals, messages and statistics: see Goals and popups.'),
    Fact("Sorting seeds: not in Fish Tycoon (the patcher's Sort Seeds button is Plant Tycoon only)."),
)

TIME_WARP = (
    Fact(
        "Not in the unpatched game.",
        patched=(("time_warp", "a clock on the Supplies store's Upgrades page (next to the Exotic Fish "
                  "Eggs). Buy opens a small Windows popup: type how many real-time hours should pass "
                  "(1-72), then Yes/No. It costs a flat $500, whatever the hours. It is refused, with "
                  "nothing charged, while time is stopped (Stop Time), with less than $500, or before a "
                  "tank has been opened since the game started."),
                 ("free_upgrades", "a warp costs $0."),),
    ),
    Fact(
        "How much game time a warp gives depends on the speed setting, because the hours are "
        "real-time hours turned into age steps exactly as time away is:",
        subs=(
            "2x speed: 12 age steps per hour, so 72 hours = 864 steps.",
            "Normal: 6 age steps per hour, so 72 hours = 432 steps.",
            "1/2 speed: 4 age steps per hour, so 72 hours = 288 steps.",
            "Stop Time: refused (a stopped game throws time away).",
        ),
        patched=(("time_warp", "live check: at Normal, a 12-hour warp aged new babies from age 4 to "
                  "76 (72 steps); at 2x speed, a 6-hour warp did the same and finished Fish Food "
                  "research."),),
    ),
    Fact(
        "What it does: exactly what time away does, but with no catch-up cap (the stock game would "
        "cut 7-72 real-time hours down to 7 hours' worth of age steps at Normal, see Time away).",
        subs=(
            "The hours go in 4-hour pieces, each followed by the game's own fish update, so every "
            "fish in all four tanks gets every age step's health, sickness, food, pregnancy and death "
            "checks, babies are born, magic fish can be found, and running research gains its 2 "
            "points per step (it finishes at most one level per 4-hour piece).",
            "A Growth fish (Oriental Goldbulb) gets one roll per step plus one per piece, fewer than "
            "in live play, the same as a long time away.",
            "Not affected: selling and customers (nothing sells during a warp), the autosave, and "
            "the Real Hours Played statistic.",
            "Fish can starve or die along the way, as they would while you were away.",
        ),
    ),
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
            "Selling: Random(900) <= T each real-time second; sick fish "
            f"{at_most(100, 20)}; customer walks to the tanks Random(100) < k.",
            f"New species price: Random(n), minus on {at_most(100, 49)}.",
            "Customers: crowd Random(2) (see Selling and customers).",
        ),
    ),
    Fact(
        "Every timer:",
        subs=(
            f"Age step: {STEP}.",
            "Fish and research update: every 301 real-time seconds or more on the tank screen, at "
            "once when it opens, and 11 real-time seconds after opening it or dropping eggs (see "
            "Time away for the other short waits).",
            "Pregnancy: 4 age steps.",
            "Research: about 49 age steps.",
            "Selling: one sale roll per real-time second; none for 5 real-time seconds after a "
            "sale; customers decide every quarter real-time second.",
            "Autosave: every 30 real-time minutes.",
        ),
    ),
)


if __name__ == "__main__":
    import sys

    import game_mechanics

    sys.stdout.write(game_mechanics.render_text(page()))
