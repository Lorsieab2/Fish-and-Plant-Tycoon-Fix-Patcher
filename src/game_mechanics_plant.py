"""Plant Tycoon's Game Mechanics page: the facts.

Traced in the vanilla LDW "Plant Tycoon.exe". Every chance is the game's own
test with its exact odds (game_mechanics.chance).
"""

from __future__ import annotations

from game_mechanics import Fact, GamePage, Group, at_least, at_most, below, chance, each


def page() -> GamePage:
    return GamePage(
        game_id="plant",
        title="Plant Tycoon",
        intro=(
            "How Plant Tycoon really works underneath, read from the game's code. Every chance below "
            "is the game's own roll: Random(n) is the C runtime's rand() % n, so \"Random(100) < 50\" "
            "is 50.05% and \"Random(10000) < 10\" is 0.12%."
        ),
        time_and_units=(
            "Two clocks (see Clocks for every timer). Game time is plant age units. "
            "The speed option sets the real-time length of one unit: Fast 2 "
            "minutes, Normal 10 minutes (the default; a game started with the tutorial runs at "
            "Fast), Slow 15 minutes; Stop Time pauses. Ages are in-game age units: a plant flowers "
            "at age 21 and is mature at 24. \"Per unit\" means once per age unit of each plant. "
            "Real time is the wall clock, the same at every speed. Plant aging (game time) and the "
            "seed shop's reroll (real time) also count time with the game closed; every other "
            "timer runs only while the game is open, in its own screen. "
            "Difficulty is Easy, Normal (the default) or Hard. The game's timers fire one second "
            "after their nominal time (a \"60-second\" timer runs every 61 seconds)."
        ),
        groups=(
            Group("Clocks", CLOCKS),
            Group("Time away (catch-up)", TIME_AWAY),
            Group("Where things count", SCOPE),
            Group("Ages and stages", AGES),
            Group("Water", WATER),
            Group("Health and soil", HEALTH),
            Group("Pests", PESTS),
            Group("Size", SIZE),
            Group("Flowers", FLOWERS),
            Group("Pollination and seeds", SEEDS),
            Group("Mutation Liquid", MUTATION),
            Group("Shop seeds", SHOP_SEEDS),
            Group("A new game", NEW_GAME),
            Group("Selling and visitors", SELLING),
            Group("Prices", PRICES),
            Group("Tools and shears", TOOLS),
            Group("Chemicals", CHEMICALS),
            Group("Nursery ornaments", ORNAMENTS),
            Group("Magic plants", MAGIC),
            Group("Everything together: a pot with every upgrade and magic plant", TOTALS),
            Group("Bugs", BUGS),
            Group("Goals, messages and statistics", GOALS),
            Group("Sorting seeds", SORTING,
                  note="Only with the Sort Seeds button setting: a \"Sort Seeds\" button on the Seed Storage "
                       "title bar."),
            Group("Time Warp (patcher)", TIME_WARP, note="Only with the Time Warp setting (off by default), which also turns on the store's Upgrades screen it lives on."),
            Group("Extra greenhouses (patcher)", EXTRA_GREENHOUSES,
                  note="Only with the 5 extra greenhouses setting (off by default)."),
            Group("Hidden keys, clicks and cheats", HIDDEN),
            Group("Fish Tycoon's topics here", OTHER_GAME),
            Group("Chance and timer index", INDEX),
        ),
    )


SCOPE = (
    Fact(
        "Quick answers: does it have to be in the nursery, or in a particular pot?",
        subs=(
            "Nursery ornaments: no placing at all; each one counts as soon as it is bought.",
            "Magic plants: no. Once found (a plant of the species alive at age 24, or made with "
            "Mutation Liquid) the effect is permanent and reaches every plant, even after your "
            "plant dies or is sold; the nursery's golden-pot display is only a picture.",
            "Plants for sale: they stay in their greenhouse pots, and everything still reaches "
            "them.",
        ),
    ),
    Fact(
        "Do duplicates stack? Magic plants: no; growing more plants of a magic species changes "
        "nothing, the effect is on or off. Nursery ornaments and tool upgrades are owned or not "
        "(one yes/no each), so there is nothing to stack. Plant Tycoon has no creatures.",
    ),
    Fact(
        "Where a plant stands never matters: no effect checks the pot, row or neighbours. All 15 "
        "pots update together.",
    ),
    Fact(
        "A plant for sale stays in its greenhouse pot, so it keeps aging and everything that reaches "
        "plants reaches it: Fruit of Life, the Fertilizer Bomb, the Insta-Grow Vaporbomb, single "
        "doses. No plant updates while you are in the nursery; that time is caught up in the "
        "greenhouse, so a plant can still sell on its last update's health.",
    ),
    Fact(
        "Magic plants are permanent once discovered (a plant of the species alive at age 24, or at "
        "once with Mutation Liquid). Their effects stay after the plant dies or is sold, and reach "
        "every plant; only a new game clears them.",
    ),
    Fact(
        "Nursery ornaments count as soon as they are bought; there is nothing to place. They only "
        "affect visitors.",
    ),
    Fact(
        "Upgrades are game-wide: soil and water upgrades apply to plants potted before them too; "
        "shears, nets and seed boxes apply when used. The bug collection bonus is permanent.",
    ),
)

CLOCKS = (
    Fact(
        "Game time = age units (2, 10 or 15 real-time minutes at Fast, Normal and Slow). It is the "
        "game's saved clock turned into units, so it keeps counting while the game is closed and is "
        "caught up in the greenhouse (see Time away). Stop Time (Options, or Space in the "
        "greenhouse) throws the elapsed time away. Game time runs: plant ageing, health, water, "
        "pests, size, seed ripening (7 age units), old age and flowering.",
    ),
    Fact(
        "Real time = the wall clock, the same at every speed:",
        subs=(
            "Plant update check: every 61 real-time seconds, only in the greenhouse, and at once "
            "on entering it. It still fires under Stop Time, but adds no age.",
            "Greenhouse check every 3 real-time seconds: bug arrivals (none under Stop Time) and "
            "the seed shop's reroll check.",
            "Seed shop reroll: 86401 real-time seconds, counted with the game closed too, but "
            "checked only in the greenhouse, and only one reroll however long you were away.",
            "Nursery check every 2 real-time seconds, only in the nursery: visitors arrive and "
            "plants sell. It keeps going under Stop Time, so plants still sell while time is "
            "stopped. There is no catch-up for time spent elsewhere.",
            "A flying bug flies off 23 real-time seconds after it appears, Stop Time or not; a "
            "crawling bug pauses 2-8 real-time seconds at a time.",
            "Autosave: every 601 real-time seconds, in every screen, but not while a message box "
            "is open. Quitting does not save; only the autosave and opening the Supplies store "
            "save.",
            "Status-bar messages and tips stay 4-5 real-time seconds; nursery price bubbles and "
            "the Sundial's text 5 real-time seconds; splash pages 4 real-time seconds.",
            "Double-clicking a pot needs two clicks within 250 real-time milliseconds.",
        ),
    ),
    Fact(
        "Frame-based (the game draws at most 30 frames per real-time second): watering adds 6, 9 "
        "or 12 water per frame (at most 180, 270 or 360 per real-time second); Insta-Grow adds "
        "0.07 age units per frame, so its 7-14 units take at least about 3.3-6.7 real-time "
        "seconds. Insta-Grow keeps going under Stop Time and while a message box is open over the "
        "greenhouse.",
    ),
    Fact(
        "While a message box is open, the screen behind it is drawn but does not update: no plant "
        "update, bugs or visitors, and no autosave.",
    ),
)

TIME_AWAY = (
    Fact(
        "Plants only update in the greenhouse: every 61 real-time seconds, at once when you enter "
        "it, and when you change the speed in Options. Time spent anywhere else, or with the game "
        "closed, is caught up the next time you enter the greenhouse.",
    ),
    Fact(
        "Time away is not capped: every missed age unit is simulated one by one (infestation, "
        "health, water loss, dryness, old age, death), so plants can die while the game is closed. "
        "The caps in the code act only on the whole real-time seconds left over after the "
        "conversion (normally 0 or 1, kept for the next update), so they never change anything.",
    ),
    Fact(
        "A long catch-up is not exactly like live play:",
        subs=(
            "Its age tests use the plant's final age, not the unit being simulated: dry young "
            "plants shrink only if the final age is below 21, old-age rolls start if the final age "
            "is above 1720, and the species counts as discovered if the final age is 24 or more. A "
            "plant going from age 1650 to 1800 in one catch-up gets 150 old-age rolls instead of 81.",
            "Health and water are clamped to their limits only after the whole catch-up, so health "
            "can climb above 100 and act as a buffer for later units.",
            "A plant that dies part-way can come back: the next unit's health change still runs, "
            "and if it is positive the plant is alive at the end. In live play a dead plant is "
            "never updated again.",
            "Flowering and the age-7 branch roll run once, after the catch-up.",
        ),
    ),
    Fact(
        "Stop Time is saved with the game. Quit while time is stopped and nothing ages or decays "
        "while you are away; the stopped time is thrown away, not banked.",
    ),
    Fact(
        "The game's clock never runs backwards: it keeps the latest time it has seen, also in the "
        "save, so setting the computer's clock back cannot undo time.",
    ),
    Fact(
        "Insta-Grow and the Vaporbomb skip ahead without simulating the skipped units: no water, "
        "health, pest or old-age changes for them.",
    ),
)

AGES = (
    Fact(
        "A seed planted at age 0 starts at health 90. One age unit is 2, 10 or 15 real-time minutes "
        "(Fast, Normal, Slow).",
    ),
    Fact(
        f"Age 7, once: each live branch has {below(100, 10)} chance to die with everything on it "
        "(dead foliage). Foliage-linked bugs can appear from here.",
    ),
    Fact("Age 21: the plant flowers. Plant Food, Bio-organic Plant Food and the Fertilizer Bomb's "
         "flowers and size only work before 21."),
    Fact(
        "Age 24: mature. The species counts as discovered, the plant can give and take pollen and "
        "can be put up for sale, and flower-linked bugs can appear. Flowers keep opening until age 28.",
    ),
    Fact(
        f"Above age 1720: each unit, {at_most(1000, 9)} chance that the plant dies of old age, "
        "99.3 more age units on average (real time: 3 h 19 min at Fast, 16 h 33 min at Normal, "
        "24 h 50 min at Slow). Age 1720 is 57 h 20 min of real time at Fast, 11 days 22 h 40 "
        "min at Normal and 17 days 22 h at Slow.",
        patched=(("no_old_age_plant_deaths", "plants never die of old age."),),
    ),
)

WATER = (
    Fact("Water runs from 0 to 1000. Planting needs soil and water 200 or more."),
    Fact(
        "The watering can adds 6, 9 or 12 per frame while held over a pot (Tap, Filtered, Isola "
        "water). How much that is per second depends on the frame rate.",
    ),
    Fact(
        "Each age unit a plant loses 6 + difficulty - water level (Easy 0, Normal 1, Hard 2; Tap 0, "
        "Filtered 1, Isola 2): 7 on Normal with Tap water. Pipe Cactus, Pear Cactus, Ball Cactus and "
        "Multiflora lose 3 less.",
    ),
    Fact(
        "Too dry (below 100): -1 health per unit, no health gains, and before age 21 "
        f"{below(100, 50)} chance per unit of size -1.",
    ),
    Fact("Too wet (above 900): the pest chance is tripled. There is no other overwatering penalty."),
)

HEALTH = (
    Fact(
        "Health runs from 0 to 100. Each age unit it changes by the plant's class and soil (Common / "
        "Bio-organic / Isola): class A +1 / +3 / +5, B -1 / +1 / +3, C -5 / -3 / +1, D -10 / -5 / +1. "
        "A gain is skipped while the plant is infested or too dry; a loss always applies.",
    ),
    Fact(
        "Classes, from the foliage and flower genes: D if either gene is above 17; otherwise C if "
        "either is even; otherwise B if either is 3, 7, 11 or 15; otherwise A. Common shop seeds are "
        "class A, Endangered B, Extinct C or D.",
    ),
    Fact("A plant at health 0 dies and is never updated again; its ripe seeds can still be "
         "collected. \"Unhealthy\" shows below 30."),
)

PESTS = (
    Fact(
        "Each age unit a clean plant becomes infested on Random(10000) < X, which is X in 8192 (not X "
        "in 10000). X by class and water (Tap / Filtered / Isola): A 10 / 5 / 1, B 20 / 10 / 5, "
        "C 100 / 20 / 10, D 200 / 100 / 50.",
        subs=(
            "Easy: X - X/20. Hard: X + X/20. Water above 900: x3. Fruit of Life: X/3.",
            f"Examples on Normal: class A on Tap water {chance(10000, 10)} per unit; class D on Tap "
            f"water {chance(10000, 200)}.",
        ),
    ),
    Fact(
        "While infested: -1, -2 or -3 health per unit (Easy, Normal, Hard), "
        f"{below(100, 50)} chance per unit of size -1, no health gains, the sale price looks 3 times "
        "higher to visitors, and pollinating it gives only 1 seed. There is no contagion.",
    ),
    Fact("Insect Poison always cures it. The Fruit of Life magic plant cures it every unit."),
)

SIZE = (
    Fact(
        "Size runs from 50 to 110 and starts at 80. Plant Food and the Fertilizer Bomb raise it; "
        "pests (at any age) and dryness (before age 21) lower it. Above 90 the plant grows more flowers. A size "
        "above 100 looks the same as 100.",
    ),
)

FLOWERS = (
    Fact(
        "At age 21, a plant with no flowers grows them: a counted flowers and b extra ones.",
        subs=(
            "Start a = 1, b = 1. Size above 90: a = 2 or 3, b = 1 or 2 (50.00% each).",
            "Flowers 1, 3, 4, 5, 6, 7, 8, 10, 15, 19 and 22: a + 1 or 2, b + 0 or 1 (50.00% each).",
            "Fruit of Life: a + 2.",
            "Health below 50: a - 2 and b = 0; below 80: a - 1 and b - 1.",
            f"If a is 0 or less it becomes 1 on {at_least(100, 10)}, else 0. If b is 0 or less "
            f"(also after health below 50) it becomes 1 on {at_least(100, 50)}, else 0.",
        ),
    ),
    Fact(
        "Extra flowers are real flowers, but while there are any, all flowers are drawn at 70% "
        "bloom; snipping extras raises the bloom. Bloom only changes the look.",
    ),
    Fact(
        "A plant that got flowers from Bio-organic Plant Food or the Fertilizer Bomb before age 21 "
        "never grows its natural flowers.",
    ),
)

SEEDS = (
    Fact(
        "Pollen can go from a live mature plant (24+) to another live mature plant that is not "
        "pollinated yet. It gives 5, 4 or 3 seeds (33.33% each), or 1 if the target is infested.",
    ),
    Fact(
        "Seeds ripen one per age unit: the first 3, 4, 5 or 7 units after pollination (5, 4, 3 "
        "seeds, infested), and all are ripe after 7 age units: 60-70 real-time minutes at Normal "
        "(12-14 min at Fast, 90-105 min at Slow).",
    ),
    Fact(
        "Breeding has no randomness: the seed's foliage is the parents' foliages averaged and "
        "rounded up, and the same for the flower. Every seed of one pollination is the same.",
        patched=(("new_flowers", "if either parent has a new flower (24-37) and the flower sum is "
                  f"odd, the flower is rounded down or up ({chance(2, 1)} each), one roll per "
                  "pollination; every seed of that pollination is still the same."),),
    ),
    Fact(
        "Throwing a seed away pays by its flower: above 17 $10, even $5, 3/7/11/15 $3, other odd $1. "
        "The seed box holds 40, 80 or 120 seeds by level.",
    ),
)

MUTATION = (
    Fact(
        "Mutation Liquid ($1000, 3 doses) works on any planted plant, at any age. "
        f"{chance(2, 1)}: the flower moves one step up or down ({chance(2, 1)} each); otherwise "
        "the foliage does, and the plant regrows in its new shape. Above 23 becomes 22, 0 becomes 2.",
        patched=(("new_flowers", "the flower steps over 1-37: a Tilia flower (23) can step up into the "
                  "new flowers (24), and 38 bounces back to 36. The foliage still stays within 1-23."),),
    ),
    Fact("The new species counts as discovered at once, and becomes a magic plant at once if it is "
         "one. These are the only random gene changes in the game.",
         patched=(("new_flowers", "breeding with a new flower also rounds an odd flower sum at "
                   "random (see Pollination and seeds)."),)),
)

SHOP_SEEDS = (
    Fact(
        "The seed shop offers 3 seeds of each tier and rerolls them after 86401 real-time seconds; "
        "only once, however long you were away. The reroll is checked every 3 real-time seconds in "
        "the greenhouse only, and it refills shelves you bought out. Nothing else in the store has "
        "a stock or a timer: chemicals, tool upgrades and ornaments can be bought at any time "
        "(the chemical tray and the seed tray have limited room).",
        patched=(("seed_refresh_key", "pressing R (or r) in the Supplies store rerolls all nine "
                  "packets at once with the same roll (0x41DC60, so the same odds), Legendary Seeds "
                  "included with Add new store upgrades and items. The next daily reroll still comes "
                  "at its usual time."),),
    ),
    Fact(
        "Common ($50): each gene 1, 5, 9 (20.001% each), 13 or 17 (19.998% each), so a Common seed "
        "is the magic Fourpetal Maple 3.999% of the time.",
    ),
    Fact("Endangered ($200): each gene 3, 7, 11 or 15 (exactly 25% each). 1 seed in 16 is the magic "
         "Rosaceae Fern."),
    Fact(
        f"Extinct ($2000): each gene, separately, is 18 or 19 ({each(6, 0)} each) or 20-23 "
        f"({each(6, 5)} each) on {below(100, 15)}, otherwise one of 2, 4 ... 16 (exactly 1 in 8 "
        "each).",
    ),
    Fact(
        "Legendary Seeds: not in the unpatched game.",
        patched=(("plant_upgrades", "three at a time on the store's Upgrades view, $5000 each, "
                  "rerolled with the stock seeds (once per 86401 real-time seconds): foliage "
                  f"Random(23) + 1 (1-16 {each(23, 0)} each, 17-23 {each(23, 22)} each), flower one "
                  f"of the 14 new flowers 24-37 (24-31 {each(14, 0)} each, 32-37 {each(14, 13)} "
                  "each), so class D. Besides these, only Mutation Liquid and breeding from a "
                  "new-flower plant give the new flowers."),
                 ("free_upgrades", "they cost $0, still three per restock, each needing room in the "
                  "seed tray."),),
    ),
)

NEW_GAME = (
    Fact(
        "A new game starts with $250, four plants in the first row (genes from 1, 5, 9, 13, 17, "
        "never the magic Fourpetal Maple), aged as if 4799 real-time seconds had passed at the "
        "current speed (age 8 at most), with health 70-89 and water 400.",
    ),
    Fact(
        "Seed storage starts with a Citrus Maranta, a Jalapa Ball Cactus and two random Common-type "
        "seeds; the seed tray with four Common-type seeds that include foliage 1 and 17 and flower "
        "1 and 17.",
    ),
)

SELLING = (
    Fact(
        "A plant can go up for sale when it is alive and mature (24+). When it sells you get the "
        "species' asking price P.",
    ),
    Fact(
        "Every 2 real-time seconds in the nursery, each plant for sale rolls Random(1300) <= k x E, "
        "with E = half the visitors browsing, rounded down. Visitors see a price P' (below) and "
        "compare it with the species' value V:",
        subs=(
            "Only in a game started with the tutorial, before your first sale: k = 70 when P' is "
            "below 3V.",
            "P' at least half below V (not infested): k = 30.",
            "P' below V by less than half (not infested): k = 10.",
            "P' from V to 1.5V, or an infested plant below V: k = 5.",
            "P' above 1.5V and below 2V: k = 2.",
            "P' of 2V or more: never sells.",
            f"Examples: k = 5 with 10 visitors browsing (E = 5), {at_most(1300, 25)}; k = 30 with "
            f"20 browsing, {at_most(1300, 300)}.",
        ),
    ),
    Fact(
        "Visitors see the price P changed, in this order: x5 if over-pruned (the root cut, or more "
        "than 65% of parts cut), otherwise -1/8 with 2 or more cut parts; +1/3 with dead foliage; "
        "+1/4 below health 15; x2 with no flowers (unless over-pruned); -1/5 for one Plant Food "
        "dose and again for a second; x3 if infested; -1/4 with the Golden Berries of Wealth.",
    ),
    Fact(
        "Visitors: up to 8 + 47 x S / 78 (8-55), where S is 2 per plant for sale, 1 or 4 per "
        "ornament (see Nursery ornaments), 4 for the Rose of Joy, 2 per other magic plant and 4 for "
        f"the full bug collection. Every 2 real-time seconds in the nursery, below the limit, "
        f"{below(100, 55)} chance that "
        "1, 2 or 3 arrive (33.33% each); the count can overshoot the limit by 2.",
    ),
    Fact(
        "A new visitor stays on Random(100) < 20 + 60 x T / 67, between 20.02% and 80.04%; T counts "
        "like S with the Fountain at 5 and the Sign, Fence, Gate and Refurbishment at 2, and no bug "
        f"bonus. After each activity a visitor leaves on {below(100, 20)}.",
    ),
    Fact("Visitors' thought bubbles only comment on the plant (no flowers, pruned, cheap, expensive, "
         "unhealthy, dead foliage, pests, fair); they change nothing."),
)

PRICES = (
    Fact(
        "Each species has a value V = its foliage's base + its flower's add, with 8 exceptions "
        "(the top is the Fabled Lemonbush at 250).",
    ),
    Fact(
        "At a new game each species' asking price P is V minus d on "
        f"{at_most(100, 50)}, otherwise V plus d, with d = Random(V/2).",
    ),
    Fact(
        "Except after a save that has found the Flower of Knowledge: then a new game prices "
        "every species at V + 3 x (V/4 rounded down), the Flower of Knowledge price, though the "
        "new game has not found it. The new game (0x41EF30) prices every species (0x41DBD0, "
        "called at 0x41EFB8) before it clears the magic plant flags (0x41F170), so the price "
        "setup reads the Flower of Knowledge flag of the save that was loaded before it. The game "
        "loads your last save when it starts, so starting a new slot right after opening the game "
        "is enough.",
        label="E",
        patched=(("fix_vanilla_bugs", "the new game clears the magic plant flags (the same seven bytes, "
                  "0x2180-0x2186) just before its price setup (0x41EFB8 calls 0x464950, which clears them "
                  "and goes on to 0x41DBD0), so a new game always gets the normal prices. Finding the "
                  "Flower of Knowledge still raises them. A save already priced this way is re-priced "
                  "the first time it loads (the load's call at 0x41EEF9 goes through 0x464970): when its "
                  "Flower of Knowledge flag is clear and every species it has not discovered (V of 4 or "
                  "more) asks exactly V + 3 x (V/4), those species get V -+ Random(V/2) as at a new game. "
                  "Without the flag no price can be that high (Random(V/2) is at most V/2 - 1). "
                  "Discovered species keep their prices, which you may have set; a save with any other "
                  "undiscovered price, or that has found the Flower of Knowledge, is left alone. Nothing "
                  "else changes, and the game saves the new prices at its next save."),
                 ("new_flowers", "the 322 new species are priced the same way: the Flower of Knowledge "
                  "price at a new game in the stock game, the normal prices with Fix Vanilla Bugs, and a "
                  "save's New Flowers file is re-priced by the same rule as it loads.")),
    ),
    Fact(
        "Discovering the Flower of Knowledge resets every asking price to V + 3 x (V/4 rounded "
        "down), once, "
        "overwriting prices you set.",
    ),
    Fact(
        "\"Set species price\": typed values above 9999 become 9999. The arrows step by 1, 5, 10, "
        "25 or 100 by price, never below 1 and with no top; they apply at once and Cancel does not "
        "undo them.",
    ),
)

TOOLS = (
    Fact(
        "Upgrades are bought in the Supplies store's Tool Upgrades column, each needing the one "
        "before, and work game-wide at once: every pot, including plants already potted and plants "
        "for sale.",
    ),
    Fact(
        "Soil: Common (from the start), Bio-organic $850, Soil from Isola $3000. It sets each age "
        "unit's health change by the plant's class (Common / Bio-organic / Isola):",
        subs=(
            "Class A +1 / +3 / +5, B -1 / +1 / +3, C -5 / -3 / +1, D -10 / -5 / +1.",
            "So only Isola soil keeps every class healthy; on Common soil a class D plant loses 10 "
            "health a unit. A gain is skipped while the plant is infested or too dry.",
        ),
    ),
    Fact(
        "Water: Tap (from the start), Filtered $650, Water from Isola $2700. Three effects (Tap / "
        "Filtered / Isola):",
        subs=(
            "The watering can adds 6 / 9 / 12 water per frame held over a pot.",
            "Each unit a plant loses 6 + difficulty minus 0 / 1 / 2 water (see Water).",
            "The pest odds X out of 10000 per unit: class A 10 / 5 / 1, B 20 / 10 / 5, C 100 / 20 / "
            "10, D 200 / 100 / 50 (see Pests).",
        ),
    ),
    Fact(
        "Shears: Dull (from the start), Sharp $500, Golden $1200. They change what pruning does "
        "(below): Sharp shears hurt a green part or flower less than Dull ones, Golden shears never "
        "hurt it, and Golden shears heal more when cutting a dead part.",
    ),
    Fact(
        "Net: Crude Butterfly Net (from the start), Large $1000, Golden $4500. The Large and Golden nets catch in "
        "a 60 x 40 box instead of 40 x 25. With the Golden net held, flying bugs only flee when the "
        "cursor is within 40 x 25 instead of 70 x 65, so they are much easier to catch.",
    ),
    Fact(
        "Seed boxes: First (from the start), Second $700, Third $700. Each opens a 40-seed drawer in "
        "Seed Storage: 40, 80 or 120 seeds. With every unlocked drawer full, the greenhouse says "
        "\"Your seed box is already full!\" and the seed is not moved.",
        patched=(("plant_upgrades", "the Fourth, Fifth and Sixth Seed Box ($1000 each, in order, on "
                  "the store's Upgrades view) open a second 120-seed chest: gold arrows on the Seed "
                  "Storage title bar switch between boxes 1-3 and 4-6, and the greenhouse fills "
                  "boxes 4-6 once 1-3 are full."),
                 ("free_upgrades", "the Fourth, Fifth and Sixth Seed Box cost $0, still in order."),
                 ("sort_seeds", "a Sort Seeds button sorts every unlocked box (see Sorting seeds).")),
    ),
    Fact(
        "Shears on a dead part (plant alive): Dull +0 to +3 health, Sharp +0 to +3, Golden +2 to +6. "
        "On a green part or a flower: Dull -10 to -24, Sharp -7 to -13, Golden no damage. Pruning "
        "can kill a plant.",
    ),
)

CHEMICALS = (
    Fact("A chemical dose is used up before its effect is checked: using one where it cannot work "
         "wastes the dose."),
    Fact("Most chemicals act on the one pot you use them on, which must hold a plant (a plant for "
         "sale too). The Fertilizer Bomb and the Insta-Grow Vaporbomb act on every pot with a live "
         "plant."),
    Fact("Plant Food ($75, 15 doses): before age 21, size +5 to +14. Each dose also makes visitors "
         "see the price 1/5 lower, for up to 2 doses."),
    Fact("Vitamins ($125, 3 doses): health +5 to +14, up to 100."),
    Fact("Insect Poison ($65, 5 doses): cures pests, always."),
    Fact("Bio-organic Plant Food ($175, 25 doses): before age 21, adds flowers."),
    Fact("Plant Rescue Formula ($150, 1 dose): health to 100, if the plant is alive."),
    Fact(
        "Fertilizer Bomb ($150, 1 dose): every live plant gets health +3 to +7; those under age 21 "
        "also get flowers and size +5 to +14, which counts as a Plant Food dose.",
    ),
    Fact(
        "Insta-Grow ($250, 5 doses): the plant gains 7 to 14 age units (1 in 8 each) at 0.07 units "
        "per frame, so over 100-200 frames (its real-time length depends on the frame rate), with no "
        "water, health, pest or old-age changes for them. The Vaporbomb ($1500, 2 doses) does it to "
        "every live plant.",
    ),
    Fact("Mutation Liquid ($1000, 3 doses): changes one gene of the plant; see Mutation Liquid."),
    Fact(
        "Radioactive Plant Formula: not in the unpatched game.",
        patched=(("plant_upgrades", "on the store's Upgrades view, $10,000, 3 doses, one pot per dose. "
                  "On a live plant: health 100, every dead (brown) part alive again, every hidden "
                  "branch of its shape grown, size 110 (the largest), grown to age 28 (full bloom), "
                  "flowers on every flower spot of every live, uncut part (its spots filled up to 6 "
                  "per part), no later dead leaves, and, if it is already pollinated, all 5 of its "
                  "seeds (pollinating it later gives the usual 5, 4 or 3). A dead plant stays dead."),
                 ("free_upgrades", "it costs $0 (it still needs room in the chemical tray)."),),
    ),
)

ORNAMENTS = (
    Fact(
        "Nursery ornaments only bring visitors; they count as soon as they are bought (there is "
        "nothing to place) and visitors walk over to look at them. Each adds to two scores (see "
        "Selling and visitors):",
        subs=(
            "Stone Turtle $50, Sundial $150, Weather Vane $75, Charming Lantern $125, Owl Statuette "
            "$100, Country Wheelbarrow $300, Bird House $60, Cherub Statuette $325, Bench $550 and "
            "Cash Register $750: +1 to the visitor limit score S and +1 to the stay score T.",
            "Sign $675, Fence $1800, Gate $1000 and Refurbishment $2500: +4 to S and +2 to T.",
            "Fountain $4500: +4 to S and +5 to T.",
            "S sets the most visitors at once (8 + 47 x S / 78, rounded down; 1 point is about 0.6 "
            "visitors); T sets how likely a new visitor stays (20 + 60 x T / 67 out of 100).",
        ),
    ),
)

MAGIC = (
    Fact(
        "How a magic plant is found: a plant of its species alive (health above 0) at age 24 or "
        "more at a plant update in the greenhouse, or at once when a Mutation Liquid dose turns a "
        "plant into it (any age; passing through it counts even if a later dose moves on). Each is "
        "found once and stays found until a new game.",
        subs=(
            "On finding it, its message shows once in the greenhouse (within about 3 real-time "
            "seconds), with either answer to the tutorial question. The message says it was "
            "repotted and moved to the nursery; in fact your plant stays in its greenhouse pot and "
            "can be sold or bred like any other. The nursery shows a separate display plant of the "
            "species in a golden pot, and clicking it shows the message again.",
            "Every found magic plant is a place visitors walk to and adds 2 points to the visitor "
            "score S and the stay score T (the Rose of Joy 4). The Statistics screen counts them.",
            "Breeding: a seed's gene is the parents' genes averaged and rounded up, so foliage f "
            "needs parent foliages adding up to 2f - 1 or 2f, and the same for the flower. Two "
            "Common seeds (genes 1, 5, 9, 13, 17) or two Endangered (3, 7, 11, 15) give only odd "
            "genes; a Common with an Endangered gives only even genes 2-16. Averaging never leaves "
            "the parents' range.",
            "Mutation Liquid: each dose moves the flower (50%) or the foliage (50%) one step up or "
            "down (50% each), so a plant one step from a magic one reaches it with 1 dose in 4.",
        ),
    ),
    Fact(
        "Magic Tree of Fragrance, Fourpetal Maple (foliage 13, flower 13), class A, value V = 44.",
        subs=(
            "Easiest of all: the two seeds every new game starts with in Seed Storage, the Citrus "
            "Maranta (9, 17) and the Jalapa Ball Cactus (17, 9), always breed it.",
            "Common shop seeds: 3.999% per seed (11.52% that at least one of the three on the "
            "shelf is one). Also Common (9, 9) x (17, 17), or Endangered (11, 11) x (15, 15).",
            "Mutation Liquid from Extinct (12, 12), (12, 14) or (14, 12): 1 in 8 within 2 doses.",
            "Effect: bugs appear 1 point more often (+1.001% per 3-real-time-second greenhouse "
            "check).",
        ),
    ),
    Fact(
        "Rose of Joy, Rosaceae Fern (7, 7), class B, V = 75.",
        subs=(
            "Endangered shop seeds: exactly 6.25% per seed (17.60% that one of the three is). Or "
            "breed Common (5, 5) x (9, 9), Common (5, 9) x (9, 5), or Endangered (3, 3) x (11, "
            "11).",
            "Mutation Liquid from (6, 7), (8, 7), (7, 6) or (7, 8): 1 in 4 per dose.",
            "Effect: 4 points to the visitor score S and the stay score T instead of 2. Nothing "
            "else.",
        ),
    ),
    Fact(
        "Flower of Knowledge, Nox Orchid (4, 4), class C, V = 95.",
        subs=(
            "Extinct shop seeds: 1.1285% per seed. Or breed Common (5, 5) x Endangered (3, 3), or "
            "Common (1, 5) x Endangered (7, 3).",
            "Mutation Liquid from (3, 4), (5, 4), (4, 3) or (4, 5): 1 in 4 per dose.",
            "Effect: when it is found, every species' asking price is set once to V + 3 x (V/4 "
            "rounded down), overwriting prices you set. Its message says \"from now on\", but it "
            "is a one-time change: later prices you set stay.",
            "A new game started after a save that has it was loaded (the game loads your last save "
            "when it starts) begins with those raised prices, though the new game has not found it "
            "(see Prices). Fix Vanilla Bugs stops this.",
        ),
    ),
    Fact(
        "Golden Berries of Wealth, Aureus Scandens (2, 14), class C, V = 130.",
        subs=(
            "Extinct shop seeds: 1.1285% per seed. Or breed Common (1, 13) x Endangered (3, 15), "
            "or Common (1, 17) x Endangered (3, 11).",
            "Mutation Liquid: from (1, 14) a foliage step always lands on 2 (0 bounces to 2), so 1 "
            "dose in 2; from (3, 14), (2, 13) or (2, 15) 1 in 4.",
            "Effect: visitors see every asking price a quarter lower (P' - P'/4, rounded down), so "
            "plants sell more easily at the same price; you are still paid your full price.",
        ),
    ),
    Fact(
        "Fruit of Life, Mela Rare Oak (14, 16), class C, V = 110.",
        subs=(
            "Extinct shop seeds: 1.1285% per seed. Or breed Common (13, 17) x Endangered (15, 15), "
            "or Common (17, 17) x Endangered (11, 15).",
            "Mutation Liquid from (13, 16), (15, 16), (14, 15) or (14, 17): 1 in 4 per dose.",
            "Effect, on every plant: +2 health and pests cured each age unit (if alive), the pest "
            "odds X divided by 3, and 2 more counted flowers when a plant flowers.",
            "Class C plants lose health on Common soil (-5 a unit), so grow it on Bio-organic or "
            "Isola soil, or use Mutation Liquid (no age needed).",
        ),
    ),
    Fact(
        "Fabled Rose of Isola, Fabled Lemonbush (11, 10), class C, V = 250, the highest value in "
        "the game.",
        subs=(
            "Never from the shop. No pair of Common and Endangered seeds breeds it in one go. Two "
            "ways: breed Common (9, 9) x Extinct (12, 10); or from Common seeds only, (9, 13) x "
            "(13, 9) gives (11, 11), (9, 9) x (13, 9) gives (11, 9), then (11, 11) x (11, 9) gives "
            "it.",
            "Mutation Liquid from (10, 10), (12, 10), (11, 9) or (11, 11): 1 in 4 per dose, 32.81% "
            "within a 3-dose bottle.",
            "Effect: only the 2 visitor points every magic plant gives.",
        ),
    ),
    Fact(
        "Finding all six shows the win screen (\"Amazing! With the restoration of the Magic "
        "Plants...\") when the last message shows. It gives no money or reward and the game "
        "goes on; the middle of the nursery opens it again (see Hidden keys, clicks and cheats).",
        patched=(("new_flowers", "the new flowers are never magic, but as parents they add routes: "
                  "a flower 24 with a flower 8 gives 16 (Fruit of Life), with 4 gives 14 (Golden "
                  "Berries), with 2 gives 13 (Fragrance)."),),
    ),
)

GOALS = (
    Fact(
        "The only goal is finding all six magic plants, which shows the win screen; play goes on "
        "afterwards. There is no map, chapter or island progression: the intro and the win text "
        "are the only story.",
    ),
    Fact(
        "One-time messages, each shown once per game in the greenhouse: the welcome (always), "
        "each magic plant (always), all 48 bugs caught (always, with $5000 once); and only in a game "
        "started with Yes to the tutorial: your first plant death, a plant pruned to death, your "
        "first sale (which also ends the first-sale bonus, see Selling and visitors) and the end "
        "of the tutorial. If 10 messages are already waiting, a new one is lost.",
    ),
    Fact(
        "Statistics screen: Real Hours Played (whole real-time hours since the game began, closed "
        "time included; the nursery Sundial shows it too), Money Earned, Plants Sold, Average "
        "Price, Plants Cured, Seeds Planted, Liters Water Used, Branches Pruned, Net Swung, Bugs "
        "Caught, Nursery Visitors (those who stay), Magic Plants Found and Species Discovered. "
        "None of them changes the game.",
    ),
    Fact(
        "Collections shows only the bug collection; there is no species or magic-plant catalogue. "
        "A plant's species name shows once it is age 24, whether or not the species was "
        "discovered before.",
    ),
    Fact(
        "Snapshots (F1 in the greenhouse, or the camera) save a picture named PlantTycoon_Snapshot "
        "to your Desktop.",
    ),
    Fact("Autosave runs every 601 real-time seconds; quitting does not save (see Clocks)."),
)

SORTING = (
    Fact(
        "Clicking Sort Seeds asks first (Yes / No). Yes sorts every seed in the unlocked seed box space at once; "
        "No, or holding a seed, changes nothing. The seed tray is never touched.",
    ),
    Fact(
        "Where seeds go: packed from the first slot, left to right, top to bottom, through the unlocked "
        "drawers in order: First, Second and Third Seed Box, then the Fourth, Fifth and Sixth (pages 4-6, "
        "with Add new store upgrades and items). Boxes 1-3 fill completely before any seed goes to boxes "
        "4-6. Locked drawers are never written, and the empty slots end up at the end.",
    ),
    Fact(
        "Order, each key only breaking ties of the one before, lowest first:",
        subs=(
            "1. The class of the plant the seed grows, from its foliage and flower genes: A, then B, C, D "
            "(see Health and soil; the new flowers are D). A seed with no known child genes goes last.",
            "2. That plant's foliage gene.",
            "3. That plant's flower gene.",
            "4. The seed's own parent (the plant it ripened on): foliage, then flower.",
            "5. The pollen donor: foliage, then flower.",
            "Unknown parents (shop seeds, the \"?\" in the info panel) count as 0, so they come before every "
            "known parent of the same plant.",
            "6. Seeds equal on all of these keep their old order (top-left first, boxes 1-3 before 4-6).",
        ),
    ),
    Fact(
        "Safety: the sort builds the new boxes in a copy, checks that the copy holds exactly the same seeds "
        "(every byte, and as many) as before, and only then writes it; otherwise nothing changes. Saves are "
        "unchanged in layout.",
    ),
)

TOTALS = (
    Fact(
        "Health per age unit for a plant that is not infested and not too dry, with Soil from "
        "Isola and the Fruit of Life found: class A +5 +2 = +7, class B +3 +2 = +5, class C +1 +2 "
        "= +3, class D +1 +2 = +3 (capped at 100). Without the Fruit of Life on Common soil a class "
        "D plant loses 10 a unit.",
    ),
    Fact(
        "Pests with Water from Isola and the Fruit of Life: the odds X out of 10000 per unit are "
        "class A 1, B 5, C 10, D 50, then divided by 3 by the Fruit of Life, which also cures any "
        "pest every unit, so a plant is never infested for long.",
    ),
    Fact(
        "Water with Water from Isola: a plant loses 6 + difficulty - 2 water per unit (5 on "
        "Normal), and the watering can adds 12 per frame.",
    ),
    Fact(
        "Flowers: the Fruit of Life adds 2 counted flowers when a plant flowers at age 21; the "
        "Radioactive Plant Formula (patched) fills every flower spot.",
    ),
    Fact(
        "Selling with everything: the visitor score S counts 2 per plant for sale, every ornament "
        "(1 or 4 each), the six magic plants (12, the Rose of Joy 4 of them) and the full bug "
        "collection (4); the visitor limit is 8 + 47 x S / 78, at most 55. The Golden Berries "
        "make every price look a quarter lower. None of this depends on where a plant stands.",
    ),
)

BUGS = (
    Fact(
        "Every 3 real-time seconds in the greenhouse, if no bug is out and time is running, a bug "
        "appears on Random(100) < t, with t = 6 + (20 - bugs collected, at least 0) / 4: "
        f"{below(100, 11)} with none collected, down to {below(100, 6)} from 17. The Magic Tree of "
        "Fragrance adds 1.",
    ),
    Fact(
        f"{at_most(100, 75)}: a random pot is tried. It qualifies with foliage 7, 8, 12, 14, 15, 17, "
        "18 or 22 from age 7, or flower 6, 9, 11, 12, 18, 19, 20 or 23 from age 24 (health is not "
        f"checked). Then, foliage first on {below(100, 50)}, otherwise flower first, its bug comes "
        "from foliage 4, 7, 8, 12, 15, 17, 22, 23 (age 7+) or flower 4, 6, 9, 10, 11, 12, 14, 20 "
        "(age 24+). Each of those 16 genes has its own bug, and 16 of the 48 bugs come only this "
        "way; a bug of foliage 4 or 23, or flower 4, 10 or 14, needs the pot's other gene to "
        "qualify it.",
    ),
    Fact(
        "Otherwise a random family (25% each), then with r = Random(100): a common bug on "
        f"{at_least(100, 25)}, an uncommon one on 8 <= r < 25 (17.02%), a rare one on "
        f"{below(100, 8)}.",
    ),
    Fact(
        f"A bug you already have is skipped on {below(100, 40)}, and then nothing appears that time. "
        "Catching a duplicate pays $5, $20 or $40; all 48 pay $5000 once.",
    ),
    Fact("Butterflies and dragonflies fly off 23 real-time seconds after appearing; beetles and "
         "spiders walk until they leave."),
)

HIDDEN = (
    Fact(
        "Greenhouse keys (lowercase letters only):",
        subs=(
            "2 or s: Seed Storage. 3 or p: the Supplies store. 4 or c: Collections. 5 or n: the "
            "Nursery. 1 or m: the greenhouse itself (nothing).",
            "Space: Stop Time on or off (\"Time Paused\" / \"Unpaused\"), the same as the Options "
            "setting.",
            "Escape: the main menu. F1: the snapshot (camera) screen.",
            "F10: opens the asking-price box with none of the Price button's checks. With no pot "
            "selected (as on entering the greenhouse) it works on a pot that does not exist and "
            "writes past the game's data when you press OK. What that does was not tested; do "
            "not use it.",
        ),
    ),
    Fact(
        "Add Money: not in the unpatched game. Every change of cash goes through 0x41ED70, which "
        "keeps it between $0 and $4,000,000,000 (the double at 0x467F78).",
        patched=(("add_money", "a pile of gold coins on the Nursery shelf of the Supplies store's "
                  "Upgrades view, next to the Time Warp clock: $950 ($0 with Free upgrades), Yes/No, "
                  "then +$1,000 through 0x41ED70, any number of times. Cash stops at $4,000,000,000."),),
    ),
    Fact(
        "Keys on the other screens:",
        subs=(
            "Seed Storage: 1 or m greenhouse, 3 or p store, 4 or c Collections, 5 or n Nursery; "
            "Escape back to the greenhouse.",
            "Supplies store: 1 or m greenhouse, 2 or s Seed Storage, 4 or c Collections, 5 or n "
            "Nursery; Escape greenhouse.",
            "Collections: 1 or m greenhouse, 2 or s Seed Storage, 3 or p store, 5 or n Nursery; "
            "Escape or F1 greenhouse. F3 hides or shows the mouse pointer (every other press "
            "hides it, in every screen, until F3 is pressed again there).",
            "Nursery: only 1 or m and Escape (both to the greenhouse). 3 and 4 change the first "
            "visitor's look (a leftover developer key; it changes nothing else).",
            "Splash screen: any key or click shows the next page; F1 skips straight to the "
            "greenhouse (what that does with no game loaded was not tested).",
            "Message boxes: Return is OK, Escape cancels. The price box takes digits and a minus "
            "sign first, so a zero or negative asking price can be typed (what then happens was "
            "not tested).",
        ),
    ),
    Fact(
        "Hidden clicks in the greenhouse:",
        subs=(
            "The faucet (x 754-804, y 430-505), when you hold nothing and click no pot: a random "
            "tip in the status bar for 4-5 real-time seconds (list below).",
            "Double-click the selected pot (no tool held): it shows the seed you planted "
            "(\"Displaying seed in this pot...\").",
        ),
    ),
    Fact(
        "Hidden clicks in the nursery (each only if you own the item):",
        subs=(
            "Bird House: a sound and an animation. Wheelbarrow: a sound and 3-22 sparkles. Stone "
            "Turtle: a sound and three animations. None of them changes visitors or sales.",
            "Sundial: a sound and \"Real Hours Played: N\" for 5 real-time seconds, where N is "
            "the whole real-time hours since the game was started, closed time included (not time "
            "played).",
            "A magic plant's display: shows that magic plant's message again. Nothing else.",
            "The middle of the nursery (363, 275, 75 x 71), once all six magic plants are found: "
            "the win screen again.",
            "A plant for sale: \"Asking Price: P\" for 5 real-time seconds. A visitor: a new "
            "thought bubble. Dragging a plant onto another sale spot swaps the two plants, also in "
            "the greenhouse.",
            "The Weather Vane, Lantern, Owl, Cherub, Bench, Fountain, Sign, Fence, Gate, Cash "
            "Register and Refurbishment do nothing when clicked.",
        ),
    ),
    Fact(
        "The faucet tip is one of 50, picked by Random(50): tips 1-18 2.002% each, 19-50 1.999% "
        "each, with no memory, so a tip can repeat (clicking while that same tip is showing "
        "changes nothing). One more is picked the same way for the loading screen at start-up. "
        "The texts are the game's own; tip 22 is wrong (an infested plant can be pollinated, for "
        "1 seed) and tips 33, 36 and 37 do not hold in the nursery:",
        subs=(
            "1. Time passes whether you're playing the game or not.",
            "2. Duplicate bugs are turned into cash.",
            "3. Careful! Pruning cannot be undone.",
            "4. Ornaments attract more visitors to your nursery.",
            "5. Some exotic plants survive only in special soil.",
            "6. Plants can be damaged by pruning.",
            "7. Pause the game if you go away for very long.",
            "8. Upgraded nets help you catch the faster bugs.",
            "9. Only mature plants display their name.",
            "10. Mature plants produce pollen.",
            "11. Plants produce seeds after you pollinate them.",
            "12. Infested plants have small black insects around them.",
            "13. Plants keep growing even when the game is off.",
            "14. Isola is pronounced ee-zoh-lah!",
            "15. Each Magic Plant has a unique effect.",
            "16. There are over 500 different species of Plants!",
            "17. You can drag seeds directly to the Seeds button.",
            "18. Magic Plants attract visitors to your store.",
            "19. You can breed and sell Magic Plants that you've found.",
            "20. If your plants are dying, buy better soil.",
            "21. There are many approaches to solving the game.",
            "22. Infested plants cannot be pollinated.",
            "23. Some plants can sell for more than $400.",
            "24. Pricing your plants too high inhibits sales.",
            "25. Double-clicking a pot will show what seed you planted.",
            "26. The supply shop's seed inventory changes once a day.",
            "27. Mutation Liquid changes the DNA of the plant.",
            "28. If your plants sell quickly, the price may be too low.",
            "29. The effect of Magic Plants is automatic and permanent.",
            "30. Magic Plants are automatically repotted in golden pots.",
            "31. You can't rush Mother Nature!",
            "32. The 'ESC' key will take you back one screen.",
            "33. There are hotkeys for moving between screens.",
            "34. Dead plants may still have seeds on them.",
            "35. Soil upgrades immediately benefit your plants.",
            "36. The number keys navigate from screen to screen.",
            "37. 'm', 'c', 'p', 's', and 'n' keys will change screens.",
            "38. Trashing a pot containing dirt gives you a new pot.",
            "39. Pruning dead foliage can improve plant health.",
            "40. Moving your hand too quickly scares bugs.",
            "41. Sneaking up on bugs with your net helps you catch them.",
            "42. Plants sell better if flowers are visible.",
            "43. You can share snapshots of your plants.",
            "44. Catching bugs can help finance your purchases.",
            "45. Trashing unwanted seeds turns them into cash.",
            "46. Plants with dead foliage don't sell well.",
            "47. Certain chemicals can advance your breeding program.",
            "48. You can rearrange your plants in the nursery.",
            "49. You can take snapshots of your favorite plants.",
            "50. The speed of time can be changed from Options.",
        ),
    ),
    Fact(
        "Not reachable (dead code): a \"d then w\" cheat for $50,000 cash in the greenhouse. The "
        "code needs a counter at 1 before d, and nothing ever sets it to 1, so it never pays.",
    ),
    Fact(
        "The Supplies store and its seed shelves handle no hidden keys. Its key handler (0x447950) "
        "reacts only to the screen keys 1 or m, 2 or s, 4 or c, 5 or n and to Escape (all listed "
        "above). In the unpatched game no key redraws or restocks the seed shelves or changes a price: the shelves "
        "change only with the reroll every 86401 real-time seconds (see Shop seeds).",
    ),
    Fact(
        "The patcher's own key: R (or r) in the Supplies store restocks the seed shelves "
        "(R refreshes the seed shop, on by default; nothing on any other screen). The patcher's "
        "other additions are clicks, not keys: the Upgrades link in the Supplies store "
        "and the gold box arrows (Add new store upgrades and items), the Sort Seeds button "
        "(Sort Seeds button), and the Time Warp clock (Time Warp).",
    ),
)

OTHER_GAME = (
    Fact('Which tank counts: see Where things count (plants have no tanks; position never matters).'),
    Fact('Health: see Health and soil.'),
    Fact('Sickness: see Pests. Plants have no other disease.'),
    Fact('Food: not in Plant Tycoon. Plants need water instead (see Water).'),
    Fact('Breeding and babies: see Pollination and seeds.'),
    Fact('Eggs: see Shop seeds.'),
    Fact("Magic fish and Magic fish one by one: see Magic plants (each one's own entry)."),
    Fact('Medicines and chemicals: see Chemicals and Mutation Liquid.'),
    Fact('Permanent store items: see Tools and shears (the upgrades) and Nursery ornaments.'),
    Fact('Everything together: a tank with every upgrade, research and creature: see Everything together: a pot with every upgrade and magic plant (plants have no creatures).'),
    Fact('Research: not in Plant Tycoon; the tool upgrades take its place (see Tools and shears).'),
    Fact('Selling and customers: see Selling and visitors.'),
    Fact('Species and prices: see Prices.'),
    Fact('Goals and popups: see Goals, messages and statistics.'),
    Fact("DS store animals: not in Plant Tycoon. The patcher's new Plant Tycoon items are in Shop seeds (Legendary Seeds), Chemicals (Radioactive Plant Formula) and Tools and shears (Fourth to Sixth Seed Box)."),
)

TIME_WARP = (
    Fact(
        "Not in the unpatched game.",
        patched=(("time_warp", "a clock on the Nursery shelf of the Supplies store's Upgrades view "
                  "(its tooltip shows the price). Clicking it opens a small Windows popup: type how many "
                  "real-time hours should pass (1-72), then Yes/No. It costs a flat $500, whatever the "
                  "hours. It is refused, with nothing charged, while time is stopped (Stop Time) or "
                  "with less than $500."),
                 ("free_upgrades", "a warp costs $0."),),
    ),
    Fact(
        "How much game time a warp gives depends on the speed setting, because the hours are "
        "real-time hours turned into age units exactly as time away is:",
        subs=(
            "Fast: 30 age units per hour, so 72 hours = 2160 units.",
            "Normal: 6 age units per hour, so 72 hours = 432 units.",
            "Slow: 4 age units per hour, so 72 hours = 288 units.",
            "Stop Time: refused (a stopped game throws time away).",
        ),
        patched=(("time_warp", "live check: at Normal, a 2-hour warp aged every plant 12 units and "
                  "moved the seed shop's restock 7200 real-time seconds closer; at Fast, a 1-hour warp "
                  "aged them 30 units."),),
    ),
    Fact(
        "What it does: exactly what time away does (Plant Tycoon has no catch-up cap). Every live "
        "plant's clock moves back by the hours and the game's own plant update runs at once, so "
        "each plant gets every age unit's water, health, pest, size, seed-ripening and old-age "
        "checks.",
        subs=(
            "Like a long time away, the whole warp is one catch-up, with its quirks (see Time away): "
            "age tests use the final age, so a long warp at Fast that ends past age 1720 rolls old age "
            "for every unit.",
            "The seed shop's restock time moves the same hours closer, so it restocks once at the "
            "next greenhouse check if it is due. The Sundial's Real Hours Played moves too.",
            "Not affected: nursery sales and visitors, bugs and the autosave. Dead plants and empty "
            "pots are left alone.",
            "Plants can dry out or die along the way, as they would while you were away.",
        ),
    ),
)

EXTRA_GREENHOUSES = (
    Fact(
        "Not in the unpatched game: one greenhouse of 15 pots.",
        patched=(("extra_greenhouses", "six greenhouses of 15 pots, 90 pots in all. Gold arrows on the "
                  "greenhouse screen (the game's own, as on the Seed Storage screen) page through Greenhouse 1, "
                  "the stock one, to Greenhouse 6 and round again; the screen says \"Greenhouse n of 6\". "
                  "Leaving the greenhouse and coming back shows the one you last looked at."),),
    ),
    Fact(
        "Every greenhouse is the stock greenhouse screen, and the game's own code runs on its pots, so "
        "everything on this page holds pot for pot in every greenhouse: ageing, water, health and soil, "
        "pests, size, flowers, pollination and seeds, old age, every chemical (Plant Food, Bio-organic Plant "
        "Food, pesticides, Insta-Grow, the Fertilizer Bomb, Mutation Liquid, the Radioactive Plant Formula, "
        "...), every tool and tool upgrade, the water and soil upgrades, and every magic plant's effect.",
        subs=(
            "The two bombs reach every pot of the greenhouse they are used in, as in the stock game (one "
            "greenhouse per dose).",
            "Magic plants are found by growing one to age 24 in any greenhouse; their effects then reach every "
            "plant in every greenhouse.",
            "Bugs come only to the greenhouse on screen, as they come only while you are in the greenhouse in "
            "the stock game.",
        ),
        patched=(("extra_greenhouses", "checked in emulation: the same plant, planted and grown with the same "
                  "random numbers in Greenhouse 1 and in each of Greenhouses 2-6, ends byte for byte the same "
                  "after each update, each chemical, pollination, moving and emptying a pot."),),
    ),
    Fact(
        "Clocks and time away: every plant update (every 61 real-time seconds in the greenhouse, at once on "
        "entering it, and after a Time Warp) updates all six greenhouses, one after the other, with the same "
        "clock. A greenhouse you are not looking at grows exactly as if it were on screen, and time away is "
        "caught up in every greenhouse when you come back. A Time Warp moves every live plant's clock in all "
        "six greenhouses.",
    ),
    Fact(
        "Moving plants: drag a plant onto an arrow, as you drag it to another pot, to move it to the same "
        "pot place in the greenhouse that arrow leads to, or to its first empty pot if that place is taken "
        "(it then shows that greenhouse). If that greenhouse has no empty pot, a box says so "
        "and the plant stays. Moving within a greenhouse is the stock drag to another pot.",
        subs=(
            "Pollen you collect can be carried to another greenhouse with the arrows; the seeds it makes are "
            "the same as from the same two plants in one greenhouse.",
            "Seeds you take from a plant, or a plant you hold, go back to their pot if you switch greenhouses.",
        ),
    ),
    Fact(
        "Selling: in the stock game you tag any mature, living plant for sale where it stands (select it, then "
        "the greenhouse's nursery button; or the button that tags them all), and it stays in its pot. The game "
        "has no other cap: the nursery's 15 spots are the 15 pots, so at most 15 plants can be for sale at "
        "once. With the extra greenhouses that stock maximum holds for all six together: at most 15 plants are "
        "for sale at once, counting every greenhouse. Putting a 16th up for sale says \"Your nursery is full!\"; the "
        "greenhouse's put-everything-up button stops at 15. The nursery shows the plants for sale from all "
        "six greenhouses, so visitors, prices and the visitor limit (2 per plant for sale, see Selling and "
        "visitors) are exactly the stock game's. Sold plants leave their pots as in the stock game.",
    ),
    Fact(
        "Saves: the save file keeps the stock layout (Greenhouse 1's pots). Greenhouses 2-6 are kept beside "
        "it in \"Plant Tycoon Fix Patcher Data\\Extra Greenhouses <slot>.dat\", written with every save "
        "(to a temporary file, then renamed) and read back when the slot loads. A file that cannot be read "
        "is set aside as \".unreadable\" and never overwritten; deleting the slot deletes it. Switching the "
        "setting off hides Greenhouses 2-6 with their plants (they come back when it is on again), so empty "
        "them first.",
    ),
)

INDEX = (
    Fact(
        "Every gameplay roll, with its exact odds:",
        subs=(
            f"Pests Random(10000) < X (X in 8192); old age {at_most(1000, 9)}; age-7 branches "
            f"{below(100, 10)}; size loss {below(100, 50)}.",
            f"Flowers: Random(2) rolls; a kept at 1 on {at_least(100, 10)}; b on {at_least(100, 50)}.",
            "Seeds: Random(3), 33.33% each.",
            "Mutation Liquid: Random(2), 50.00%, twice.",
            f"Shop seeds: Random(5), Random(4), Random(6), Random(8); Extinct high genes {below(100, 15)}.",
            "Selling: Random(1300) <= k x E every 2 real-time seconds in the nursery, per plant for "
            "sale.",
            f"Visitors: arrival {below(100, 55)}; 1-3 by Random(3); stay Random(100) < 20 + 60T/67; "
            f"leave {below(100, 20)}.",
            f"New asking prices: Random(V/2), minus on {at_most(100, 50)}.",
            f"Bugs: Random(100) < t; plant path {at_most(100, 75)}; duplicate skip {below(100, 40)}.",
            "Shears, Vitamins, Plant Food, Fertilizer Bomb, Insta-Grow: the ranges in their groups.",
        ),
    ),
    Fact(
        "Every timer:",
        subs=(
            "Age unit: 2, 10 or 15 real-time minutes (Fast, Normal, Slow).",
            "Plant update: every 61 real-time seconds in the greenhouse.",
            "Bugs and shop reroll check: every 3 real-time seconds in the greenhouse.",
            "Nursery (visitors and sales): every 2 real-time seconds while in the nursery.",
            "Shop reroll: 86401 real-time seconds.",
            "Autosave: every 601 real-time seconds while the game is open (not while a message box is "
            "open).",
        ),
    ),
)


if __name__ == "__main__":
    import sys

    import game_mechanics

    sys.stdout.write(game_mechanics.render_text(page()))
