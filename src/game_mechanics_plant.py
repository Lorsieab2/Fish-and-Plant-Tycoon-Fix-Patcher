"""Plant Tycoon's Game Mechanics page: the facts.

Traced in the vanilla LDW "Plant Tycoon.exe". Every chance is the game's own
test with its exact odds (game_mechanics.chance).
"""

from __future__ import annotations

from game_mechanics import Fact, GamePage, Group, at_least, at_most, below, chance


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
            "Plants live in age units. The speed option sets the real-life length of one unit: Fast 2 "
            "minutes, Normal 10 minutes (the default), Slow 15 minutes; Stop Time pauses. A plant "
            "flowers at age 21 and is mature at 24. \"Per unit\" means once per age unit of each "
            "plant. \"Real-life\" times are wall-clock time, whether the game is open or not. "
            "Difficulty is Easy, Normal (the default) or Hard. The game's timers fire one second "
            "after their nominal time (a \"60-second\" timer runs every 61 seconds)."
        ),
        groups=(
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
            Group("Bugs", BUGS),
            Group("Sorting seeds", SORTING,
                  note="Only with the Sort Seeds button setting: a \"Sort Seeds\" button on the Seed Storage "
                       "title bar."),
            Group("Chance and timer index", INDEX),
        ),
    )


SCOPE = (
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

TIME_AWAY = (
    Fact(
        "Plants only update in the greenhouse: every 61 real-life seconds, at once when you enter "
        "it, and when you change the speed in Options. Time spent anywhere else, or with the game "
        "closed, is caught up the next time you enter the greenhouse.",
    ),
    Fact(
        "Time away is not capped: every missed age unit is simulated one by one (infestation, "
        "health, water loss, dryness, old age, death), so plants can die while the game is closed. "
        "The caps in the code act only on a leftover below one second and never change anything.",
    ),
    Fact(
        "A long catch-up is not exactly like live play:",
        subs=(
            "Its age tests use the plant's final age, not the unit being simulated: dry young "
            "plants shrink only if the final age is below 21, old-age rolls start if the final age "
            "is above 1720, and the species counts as discovered if the final age is 24 or more. A "
            "plant going from age 1650 to 1800 in one catch-up gets 150 old-age rolls instead of 80.",
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
        "A seed planted at age 0 starts at health 90. One age unit is 2, 10 or 15 real-life minutes "
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
        "can be put up for sale, and flower-linked bugs can appear. Flowers keep opening until 28.",
    ),
    Fact(
        f"Above age 1720: each unit, {at_most(1000, 9)} chance that the plant dies of old age, "
        "about 99 more units on average (16 h 30 min at Normal). Age 1720 is 57 h 20 min at Fast, "
        "11 days 22 h 40 min at Normal and 17 days 22 h at Slow.",
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
        "pests and dryness before age 21 lower it. Above 90 the plant grows more flowers. A size "
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
        "seeds, infested), and all are ripe after 7 units: 60-70 real-life minutes at Normal.",
    ),
    Fact(
        "Breeding has no randomness: the seed's foliage is the parents' foliages averaged and "
        "rounded up, and the same for the flower. Every seed of one pollination is the same.",
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
    ),
    Fact("The new species counts as discovered at once, and becomes a magic plant at once if it is "
         "one. These are the only random gene changes in the game."),
)

SHOP_SEEDS = (
    Fact(
        "The seed shop offers 3 seeds of each tier and rerolls them after 86401 real-life seconds; "
        "only once, however long you were away.",
    ),
    Fact(
        "Common ($50): each gene 1, 5, 9 (20.001% each), 13 or 17 (19.998% each), so a Common seed "
        "is the magic Fourpetal Maple 3.999% of the time.",
    ),
    Fact("Endangered ($200): each gene 3, 7, 11 or 15 (exactly 25% each). 1 seed in 16 is the magic "
         "Rosaceae Fern."),
    Fact(
        f"Extinct ($2000): each gene is 18-23 (1 in 6 each) on {below(100, 15)}, otherwise one of 2, "
        "4 ... 16 (exactly 1 in 8 each).",
    ),
)

NEW_GAME = (
    Fact(
        "A new game starts with $250, four plants in the first row (genes from 1, 5, 9, 13, 17, "
        "never the magic Fourpetal Maple), aged as if 4799 real-life seconds had passed at the "
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
        "Every 2 real-life seconds in the nursery, each plant for sale rolls Random(1300) <= k x E, "
        "with E = half the visitors browsing, rounded down. Visitors see a price P' (below) and "
        "compare it with the species' value V:",
        subs=(
            "Before your first sale: k = 70 when P' is below 3V.",
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
        f"the full bug collection. Every 2 seconds, below the limit, {below(100, 55)} chance that "
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
        "Discovering the Flower of Knowledge resets every asking price to V + 3/4 V, once, "
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
        "Upgrades, each needing the one before: Soil Bio-organic $850 then Isola $3000; Water "
        "Filtered $650 then Isola $2700; Shears Sharp $500 then Golden $1200; Net Large $1000 then "
        "Golden $4500; Seed box $700 then $700.",
    ),
    Fact(
        "Shears on a dead part (plant alive): Dull +0 to +3 health, Sharp +0 to +3, Golden +2 to +6. "
        "On a green part or a flower: Dull -10 to -24, Sharp -7 to -13, Golden no damage. Pruning "
        "can kill a plant.",
    ),
    Fact("The Large and Golden nets catch in a 60 x 40 box instead of 40 x 25. With the Golden net "
         "held, flying bugs only flee when the cursor is within 40 x 25 instead of 70 x 65."),
)

CHEMICALS = (
    Fact("A chemical dose is used up before its effect is checked: using one where it cannot work "
         "wastes the dose."),
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
        "Insta-Grow ($250, 5 doses): the plant ages 7 to 14 units quickly (1 in 8 each), with no "
        "water, health, pest or old-age changes for them. The Vaporbomb ($1500, 2 doses) does it to "
        "every live plant.",
    ),
)

ORNAMENTS = (
    Fact(
        "Ornaments only bring visitors. Stone Turtle $50, Sundial $150, Weather Vane $75, Charming "
        "Lantern $125, Owl Statuette $100, Country Wheelbarrow $300, Bird House $60, Cherub "
        "Statuette $325, Bench $550 and Cash Register $750 count 1 each; Fountain $4500, Sign $675, "
        "Fence $1800, Gate $1000 and Refurbishment $2500 count 4 toward the visitor limit (see "
        "Selling and visitors).",
    ),
)

MAGIC = (
    Fact("A magic plant counts once a plant of its species is alive at age 24, or at once through "
         "Mutation Liquid. Finding all six wins the game."),
    Fact("Fruit of Life, Mela Rare Oak (foliage 14, flower 16): every plant gets +2 health and is "
         "cured of pests each unit, pest odds / 3, and 2 more flowers."),
    Fact("Flower of Knowledge, Nox Orchid (4, 4): every asking price becomes V + 3/4 V, once."),
    Fact("Rose of Joy, Rosaceae Fern (7, 7): 4 points toward the visitor score instead of 2."),
    Fact("Golden Berries of Wealth, Aureus Scandens (2, 14): visitors see every price 1/4 lower."),
    Fact("Fabled Rose of Isola, Fabled Lemonbush (11, 10): only the visitor bonus every magic plant "
         "gives (2), and the highest value, 250."),
    Fact("Magic Tree of Fragrance, Fourpetal Maple (13, 13): bugs appear 1 point more often."),
    Fact("Every magic plant adds 2 points to the visitor score S, about 1 more visitor (the Rose "
         "of Joy 4 points, about 2; see Selling and visitors)."),
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

BUGS = (
    Fact(
        "Every 3 real-life seconds in the greenhouse, if no bug is out and time is running, a bug "
        "appears on Random(100) < t, with t = 6 + (20 - bugs collected, at least 0) / 4: "
        f"{below(100, 11)} with none collected, down to {below(100, 6)} from 17. The Magic Tree of "
        "Fragrance adds 1.",
    ),
    Fact(
        f"{at_most(100, 75)}: a random pot gets a chance to bring its plant's bug: foliage 4, 7, 8, "
        "12, 15, 17, 22, 23 from age 7, or flower 4, 6, 9, 10, 11, 12, 14, 20 from age 24. Each of "
        "those 16 genes has its own bug, and 16 of the 48 bugs come only this way.",
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
    Fact("Butterflies and dragonflies fly off 23 real-life seconds after appearing; beetles and "
         "spiders walk until they leave."),
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
            "Selling: Random(1300) <= k x E every 2 seconds per plant.",
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
            "Age unit: 2, 10 or 15 real-life minutes (Fast, Normal, Slow).",
            "Plant update: every 61 real-life seconds in the greenhouse.",
            "Bugs and shop reroll check: every 3 real-life seconds in the greenhouse.",
            "Nursery (visitors and sales): every 2 real-life seconds.",
            "Shop reroll: 86401 real-life seconds.",
            "Autosave: every 601 real-life seconds.",
        ),
    ),
)


if __name__ == "__main__":
    import sys

    import game_mechanics

    sys.stdout.write(game_mechanics.render_text(page()))
