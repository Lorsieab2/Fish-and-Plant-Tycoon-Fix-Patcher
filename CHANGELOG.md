# Changelog

## Unreleased

- **Extra Nursery item a bit smaller** (Plant Tycoon, 5 extra nurseries). The
  golden pot on the Upgrades view's Nursery shelf was drawn at its full 76 x 64
  (the plant store's draw ignores the 0.84 scale it was given), taller than the
  Time Warp clock and the coins beside it. It is now pre-scaled to the clock's
  visible height (52 px), standing on the same shelf line, from a new row 20 of
  the Upgrades chemicals sheet, drawn at scale 1 at (449, 296); its click and
  tooltip rectangle is its picture's (453-514 x 305-356). Tests:
  tests/test_nursery_icon.py.
- **Extra chemical slots** (Plant Tycoon, new setting, off by default,
  EXPERIMENTAL; needs Add new store upgrades and items, which it turns on;
  Enable All turns it on). The greenhouse's Tools box is a 4 x 2 grid (the
  four tools, and the 4-slot chemical tray under them); a second page of 8
  chemical slots fills both rows, 12 in all. Bought once on the Upgrades
  screen: Extra Chemical Slots, on the chemicals shelf's third row under the
  Formula Bomb, $10,000 ($0 with Free upgrades, through the Upgrades DLL's
  price), with a tick afterwards; until then the tray is the stock four. Then
  a small gold arrow (the game's own, pre-scaled) and "1/2" / "2/2" in the
  game's font sit on the Tools box's plaque, clear of every other control;
  clicking the arrow or carrying a chemical over it turns the page (the tools
  stay on page 1; a tool in the hand stays there). Each page-2 slot is run by
  the game's own code: picked up, its record takes a stock tray record's place
  (that slot's own bottle waits and is drawn in its place), so every chemical,
  the game's and the Upgrades screen's, is used with its doses, kept in the
  hand while doses remain, and the Upgrades screen's four go in the trash
  (PR #76) exactly as from page 1. The store fills a chemical onto its own
  bottle on either page, else the first free slot of page 1, then of page 2,
  and refuses ("There is no room in your Chemical Tray.") only when all 12
  are full. A held bottle let go or clicked on another slot of either page
  moves there (empty), stacks (the same chemical) or swaps. Every chemical
  slot of both pages has a tooltip of the game's own kind with the chemical's
  name and doses left ("Revival Potion / 2 doses left"), none over an empty
  slot or the bottle in the hand; they replace the stock tray tooltips while
  the setting is on, bought or not. The tray is shared by every greenhouse
  (with 5 extra greenhouses too) and untouched by the Time Warp. The save
  keeps its stock layout (a page-2 bottle in the hand is put back for the
  save and picked up again after); page 2 and the purchase are kept per save
  slot in "Plant Tycoon Fix Patcher Data\Extra Chemical Slots <slot>.dat"
  (written atomically, set aside if unreadable, understood by Back Up Saves);
  a new game empties it. Turning the setting off loses nothing: Store
  Upgrades and Items then puts page 2's chemicals into the stock tray on load
  as far as they fit, and the file keeps the rest and the purchase (rewritten
  only when the game saves). New companion "Extra Chemical Slots.dll"
  (native/ftfp_chem_slots), loaded after every other companion: seven code
  sites (five greenhouse calls, the tray's add and room) overlapping no other
  patch, and the greenhouse screen's mouse and activation slots, chained with
  Greenhouse Counts and Extra Greenhouses; all or none. Store Upgrades and
  Items: the item, the save events passed on, the setting-off fallback, and
  two more rows of its chemicals sheet (the item and the arrows). Tests:
  tests/test_chem_slots.py (Unicorn, the vanilla executable, both DLLs).
- **Muta-Fin and Muta-Body** (Fish Tycoon, DS Store Items) and **Muta-Flower
  and Muta-Foliage** (Plant Tycoon, Add new store upgrades and items), four
  new chemicals on the Upgrades screens, $2,500 for 3 doses each ($0 with Free
  upgrades or Everything is Free). Each is its game's own mutation chemical
  for one part only. Fish: the stock Unknown Chemical's dose (0x420E93) with
  its body-or-fin roll left out: the same fish (live, health not 0, not a
  seahorse-type record, any age, the tank on screen, over the stock loop's
  records, so Bigger tanks too), the same 26.03% each, the same step (stock,
  or DS Exclusive Fish's step_gene through a new export, so the DS genes come
  only with it), the same sprite rebuild, sparkle and next update; the other
  part never changes. Plant: the Mutation Liquid's own step function (0x42FA80)
  entered at its flower or foliage branch, then the rest of its case
  (0x426EFA: discovery, Unused Flowers' discovery, the encyclopedia, the
  sparkles); its 50/50 direction and bounces, Unused Flowers' 37 bound, the
  foliage regrowth. Doses, stacking, Universal and Extra supply slots, the
  supply-slot tooltips, the trash and German texts as the other patcher
  chemicals. Icons are recolours of the stock bottles (scripts/build_muta_assets.py:
  royal blue, sea green, pink, green), the Plant ones in chemical-sheet rows
  21-22 (chemicals 48-49; the sheet is 23 rows, the dialog picture bound
  0x32). DS Exclusive Fish lends DS Store Items 32 sprite entries (was 26).
  The Breeding Guide's how-to-get texts name them. Tests compare every Muta
  dose with the stock chemical's, byte for byte, over many seeds of the
  game's own rand() (tests/test_muta_chemicals.py).
- Supply slot tooltips are patch-accurate, read from the running game's own
  code: the Unknown Chemical shows its count only when the use's "set to 1"
  (0x4210B7) is gone (Unknown Chemical: 3 uses, Universal supply slots), and
  each stock egg shows its stack only when that egg's own hatch keeps the
  stack (Universal supply slots' patches at 0x4213A7, 0x421476 and 0x421549),
  instead of inferring the eggs from the use trampoline. Tests build the
  pinned executable of every setting that changes a count (and Enable All),
  put each supply in its slot with 1-3 left, and use it on the tank with the
  game's own code until the slot is empty: the uses always equal the
  tooltip's number. Fix vanilla bugs' Plant of Incubation adds a baby to a
  batch, never a batch, so egg tooltips are unchanged by it.
- **Everything is Free**, both games, a new setting: "Every store item and
  upgrade is free. Obviously a cheat mod, have fun!" Off by default and the
  first **cheat** setting (`"cheat": true`, src/cheat.py): the patcher shows
  CHEAT beside its name, styled as the EXPERIMENTAL label, and **Enable All
  no longer turns it on** (Defaults leaves it off too; tick it yourself;
  Disable All turns it off). Every price the player pays is $0 and shown as
  $0; only prices change, every limit stays. Fish Tycoon: the stock store's
  prices all live in the state's item table (+0x74 + item x 20, research at
  0x240/0x254/0x268), and each read of it is zeroed in place, 20 patches: the
  panel's price line (0x4274AD), the Buy click's money test (0x428118), the
  supply-slot purchase and its Money Spent (0x427553/0x427560; the universal
  slots and Extra Supply Slots buy through it), the permanent-item purchase
  (0x427B83/0x427B90), the Golden Seahorse refund (0x427EA2/0x427EAF, so it
  refunds $0) and the six research charges (0x427600). The table, which the
  save holds, is never written. Plant Tycoon: the purchase dialog's price
  (dialog + 0x84) is read as 0 by its seven cash tests (never too poor), its
  17 "Price: $%d" lines and its four Buy charges (AddCash at
  0x432D96-0x432E1D), 28 patches; seeds, tools, chemicals, nursery items and
  every Upgrades item sold through the dialog (Legendary Seeds, the formula,
  the potions, Revita-Seed, the Bomb, Seed Boxes 4-9) go through it. The
  setting ships "Everything Free.ini" beside the DLLs; DS Store Items, Store
  Upgrades and Items (Free upgrades implied: Time Warp, Add Money for $0 that
  still adds $1,000, the Extra Tank, Extra Supply Slots, the Extra Greenhouse
  and Nursery, the Auto items) and Multiple Ornaments (copies) read it at
  start-up. No patch overlaps another setting's or any companion DLL's site
  (scripts/pin_everything_free.py checks, and tests/test_everything_free.py
  emulates every kind of purchase, patched and stock, in Unicorn).

- **Supply slot tooltips and page numbers** (Fish Tycoon). DS Store Items:
  every supply slot, the stock four and the extra ones, shows a tooltip while
  the mouse is over it, in the game's own hint box (the hint object's own
  box drawing, 0x423280: its fill and rope edges) just under the top bar, in
  the hint font: the item's name (the game's own names, German too) and what
  is left of it as the game will spend it -- "2 doses left", "1 use left" for
  the stock Unknown Chemical (its count with Unknown Chemical: 3 uses or
  Universal supply slots), "1 batch left" for eggs (the stack with Universal
  supply slots); the fish food by name only. None over an empty slot, while
  a hint is up or while something is held. Drawn where the game draws its
  hints, after what the hand holds (0x41D127, a new DS Store Items site that
  no other companion or patch touches). It belongs to DS Store Items, so it
  shows whenever that setting is on, with or without Extra supply slots,
  which tells it what each place shows (FtfpSupplySlotsShown). Extra supply
  slots: "1/3", "2/3" or "3/3" under the slot arrows once the slots are
  bought, in the game's own font, small and in the bar's yellow.
- **Extra supply slots** (Fish Tycoon, new setting, off by default,
  EXPERIMENTAL; needs DS Store Items, which it turns on; Enable All turns it
  on). Eleven supply slots instead of four, in three pages beside the tank
  screen's slots (page 1 the stock four, page 2 four more, page 3 three more),
  turned by two small arrows right of slot 4 (the stock UP_ARROW art, as the
  extra tanks' arrows), or by carrying an item over an arrow. Bought once on
  the Upgrades screen: Extra Supply Slots, $10,000 ($0 with Free upgrades);
  before that the arrows are grey and refuse with "You don't own the extra
  supply slots yet!" where Extra Tanks says its own. Each extra slot is a
  stock slot record run by the game's own code: picked up, it takes the
  place of the stock slot its item is used from (the stock slot's own record
  waits and comes back), so every medicine, chemical and egg, DS Store Items'
  Radioactive Growth Hormone, Revival Potion, ClonaFish and Exotic Fish Eggs
  too, works from it exactly as from slots 2-4, the trash included; the
  stock store's Buy and DS Store Items' purchases fill the first free slot
  over all three pages (a stack of the same item first with Universal supply
  slots). Supplies can be dragged between any two slots, on any page (moved,
  stacked or swapped; without Universal supply slots slots 2-4 keep their
  kind). The save keeps its stock layout; the seven slots and the purchase
  are kept per save slot in "Fish Tycoon Fix Patcher Data\Extra Supply Slots
  <slot>.dat" (written atomically, set aside if unreadable, understood by
  Back Up Saves); a new game empties them. New companion "Extra Supply
  Slots.dll" (native/ftfp_supply_slots), loaded after Extra Tanks (or first,
  loading Multiple Ornaments / DS Exclusive Fish itself); ten sites, all or
  none, five of them chained with Extra Tanks, Multiple Ornaments and DS
  Store Items. Turning it off keeps the file: the items come back when it is
  turned on again. Tests: tests/test_supply_slots.py (Unicorn, the vanilla
  and Universal supply slots executables, DS Store Items beside it, and the
  executable with every Fish setting on).
- **Seventh, Eighth and Ninth Seed Box** (Plant Tycoon, Add new store
  upgrades and items): $1000 each like the Sixth ($0 with Free upgrades),
  bought in order after the Sixth through the stock purchase dialog (its
  "You need the previous upgrade first!", "You already have this item!" and
  can't-afford answers, the Fourth-Sixth's art, the tick once owned). They
  stand in their own column on the tool shelf at x 322, left of the Extra
  Greenhouse and the Automatic Sprinklers, overlapping nothing. Each opens a
  40-seed drawer in a third chest: the Seed Storage arrows now step through
  "Boxes 1-3", "Boxes 4-6" and "Boxes 7-9" (each page once it has a box,
  then round again), with every drawer, click, drag and drop working as in
  boxes 1-6; the greenhouse fills boxes 7-9 once 1-6 are full; Sort Seeds
  fills 1-3, then 4-6, then 7-9 (360 seeds at most, the same check that no
  seed is lost). `Seed Boxes <slot>.dat` is version 2 (the six purchases and
  both new chests); a version 1 file loads with boxes 7-9 empty and is
  rewritten as version 2 at the next save; a damaged file is set aside as
  `.unreadable`, never deleted; a new game starts with none. Game Mechanics:
  a new "How many seeds you can hold" section (120, 240 or 360 in boxes, the
  8-slot tray, up to 75 ripe seeds on plants per greenhouse, 450 with
  Greenhouses 2-6, and the totals), checked against the code. Mockups:
  docs/images/seed-boxes-7-9-store.png and seed-boxes-7-9-storage.png.
- Treated fish and plants sell for the highest possible price (both games).
  A fish given a Radioactive Growth Hormone dose (DS Store Items), and a plant
  given the Radioactive Plant Formula or its Bomb (Store Upgrades and Items),
  is marked; when it is sold you are paid its species' highest selling price,
  the Breeding Guide's "Highest selling" with Max effects (Fish: 2B - 1 with B
  after both Advertising levels, a Golden Guppy $475; Plant: the highest
  asking price a visitor still buys at with every effect at its best, a
  Fabled Lemonbush $1186), into the money, Money Earned and the selling
  scene's sold-fish price. The sale chance and timing are still the asking
  price's. Fish: the one sale call (0x4244D4, the Sale Tank and Tanks 4-6 lent
  its place); the mark is the fish record's +0x48, a dword no game code reads
  (written only by the birth, as 0, and the record copy 0x41E850), so it
  follows the fish through moves, Tanks 4-6, saves and ClonaFish clones (a
  clone of a treated fish is treated); newborns never are; cleared at the
  sale, death, the trash or a revival. Plant: the sale's two price reads
  (0x435CF2, 0x435D12), every nursery, the off-screen ones too; the mark is
  'R' in the pot's +0x9F, the byte the Revival Potion's 'S' uses on dead
  plants (a plant that dies loses 'R' first), so it follows the pot through
  Extra Greenhouses and saves; cleared at the sale, death or replanting. The
  three items' store texts say so ("Treated fish sell for the highest
  possible price!", German "Behandelte Fische werden zum Höchstpreis
  verkauft!"; "Treated plants sell for the highest possible price!"). The
  price maths is native/common/max_sale_price.h, checked against the Python
  for every species.
- **Max Prices button**, both games, part of the Optimize Prices button
  setting: a second button, "Max Prices", left of each Optimize Prices
  button in the same style (Fish Tycoon: the Species Chart's bar at x
  400-519 and the Fish Store's bar at x 420-539, between "Your cash" and
  Optimize Prices; Plant Tycoon: the Nursery's brick strip at x 449-611).
  It asks "Set every discovered species to its highest selling price?
  Fish/Plants at this price sell much more slowly." and on Yes sets every
  discovered species to the highest asking price a buyer still accepts, the
  Breeding Guide's "highest selling", then says "N prices set.". Fish
  Tycoon: 2 x base price - 1 in every save, because the sale roll
  (0x424240) compares the asking price only with the species' own base price
  (0x4243DC-0x4243EA); ornaments, the Golden Seahorse and Advertising change
  the odds, never the limit (Advertising's research raises the base price
  itself, read at the click). Plant Tycoon: the price visitors see must stay
  below 2 x value (0x436BE0); the Golden Berries of Wealth (state + 0x2183,
  a quarter off the price seen, 0x436E22) are the only save-wide step and
  raise the limit; Plant Food, pruning, dead leaves, health, flowers and
  pests are each plant's own and are left out. The maths is the guide's own
  price search (shop_max_price in src/breeding_*.py, pm_*_max in
  native/common/price_math.h, checked equal for every species value). The
  same companion DLL, the same vtable slots: the install is still all or
  none.
- Game Mechanics, both games: the number of species. Fish Tycoon 441
  (21 bodies x 21 fins; the species-discovered count, 0x419240, walks the
  same 21 x 21 entries), 784 with DS Exclusive Fish (28 x 28, 343 more, its
  DLL's own count). Plant Tycoon 529 (23 foliages x 23 flowers; the
  Statistics screen's Species Discovered, 0x44C572-0x44C59F, walks the same
  23 x 23 flags), 851 with Unused Flowers (23 x 37, 322 more, added at
  0x44C5A1). Tested against the Breeding Guide models and the executables'
  own loops.
- Breeding Guide, both games, Show Spoilers off: the Fins, Bodies, Flowers
  and Foliage tabs and their picture tabs list exactly the parts the save has
  discovered, with "n of N discovered" at the top (the patcher's DS fish and
  Unused Flowers counted only when that setting is on for the save). A part
  is discovered when a species the save has discovered has it: neither game
  keeps a flag per part (Fish Tycoon: a species' asking price, 0x41E2D0;
  Plant Tycoon: a byte per species, 0x42E2C4 and 0x426F11; the DS Fish and
  Unused Flowers DLLs keep the same per-species record in their data files).
  The picture tabs leave undiscovered parts out instead of showing a "?", as
  the sheets do, and the Seed Pictures show only the discovered foliages'
  packets. Nothing undiscovered is named anywhere with spoilers off: the
  Magic Fish of Mutation is no longer called the Wasp Grouper (in "how it is
  obtained", the effects buttons and their notes) until it is discovered, the
  Golden Berries of Wealth and Flower of Knowledge are no longer named by
  their species, and the rarest seed packets no longer name Arthurium and
  Tilia until both are discovered. Exports follow the same rule.
- Plant Tycoon, 5 extra greenhouses: the gold arrows moved from beside the
  greenhouse's name to the two sides of the screen, centred on the middle
  shelf (x 220-269 and 748-797, y 236-285). Both lie wholly outside the grid
  the game picks a pot by (0x423970: x 270-730, y 43-475), so a click or drag
  on any plant, pruning included, works everywhere as in the stock game; tall
  top-row plants no longer cover them. They are drawn over the plants (from
  0x429066, after the pots, plants and sparkles) and under whatever the hand
  holds (a dragged plant, seeds, pollen, a tool) and popups. A press inside an
  arrow is the arrow's even where the widest full-grown plants (Fern, Bonsai,
  Dieffenbachia, Oak, Tiger Fern) reach under it, and switches greenhouse once;
  a plant dropped on an arrow moves on as before. The name and the greenhouse
  counts stay where they were. The nursery arrows move up 3 px (y 1-50) so
  they end above every nursery plant's click box (0x436420).

## v1.0.17

New content for both games (DS fish, fins and store animals; the 14 unused
flowers and a store Upgrades page), bigger tanks, 3 extra tanks (Tanks 4-6),
5 extra greenhouses and nurseries, tank and greenhouse counts, the
Auto-Feeder, Automatic Sprinklers and Auto-Healers, a Tools tab, and fixes.

### Both games

- **Experimental settings.** 3 extra tanks, Bigger tanks: 30 fish, Multiple
  ornaments, 5 extra greenhouses and 5 extra nurseries carry the owner's
  "EXPERIMENTAL - USE AT OWN RISK" label: it is shown in red beside each name in
  the patcher, their summaries and descriptions start with it, and they are off
  by default ("Defaults" leaves them off; "Enable All" still turns them on).
  One shared flag (`"experimental": true` in the manifests, src/experimental.py).

- **Everything in one update.** The new settings work together:
  - DS Store Items' animals (the Golden Seahorse with it, the Puffer, Ray and
    Eel) move with their tank into Tanks 4-6 and are kept there in "Extra Tanks
    <slot>.dat" (version 4: each tank's 5 animal records after its block; a
    version-3 file has its animals in records 26-30 moved over when it loads).
    Buying an animal again ("one of each" with Buy Multiple Golden Seahorses off)
    sees the ones in Tanks 4-6.
  - The Time Warp warps Tanks 4-6 too.
  - Tank counts count the tank on screen, Tanks 4-6 included, and are drawn
    over 3 extra tanks' arrows, tank name and For sale button; the Optimize Prices button loads
    before Extra Greenhouses, which chains its two Nursery slots.
  - The Radioactive Growth Hormone, Revival Potion and ClonaFish reach all 30
    slots with Bigger tanks (they read the game's own bounds, which Bigger tanks
    rewrites), and the Optimize Prices button reads the 30-fish bound.

- **Tank and greenhouse counts** (on by default, both games). Fish Tycoon's
  tank screen shows, at the top left of the water, "Fish: 12 of 21 (8 adults,
  3 teens, 1 baby)" for the tank on screen (of 30 with Bigger tanks), its
  creatures ("Creatures: Golden Seahorse, Moray Eel", read from DS Store
  Items' animal records) and "Isolation tank: 1 of 1 (1 adult)". With 3 extra
  tanks it counts Tanks 4-6 too, and the lines move down (y 136) under the
  tank's name and For sale button. Plant Tycoon's greenhouse shows "Plants: 9
  of 15 (5 mature, 2 with buds, 2 seedlings)" along the top for the
  greenhouse on screen, Greenhouses 2-6 too; once an extra greenhouse is
  bought (the gold arrows show) the line moves under the arrows (y 62). The
  stages are the games'
  own: a fish is a baby at age 1-5, a teen at 6-19 and an adult from 20 (the
  view builder's picture thresholds, 0x413F1C and 0x413F65); a plant is a
  seedling before age 21 and has buds until 24, when it is mature (the
  selected plant's countdowns, 0x4237E3 and 0x423866). Dead fish and plants
  are shown apart as "Dead: n"; Fish Tycoon follows the game's German. Sick
  fish are named by sickness ("Sick: 2 fungus, 1 ick", German "Krank: ...
  Pilzinfektion, ... Weisspünktchen"; fish +0x40, 1 and 2), with "Low
  Health: n" (German "Niedrige Gesundheit") for live fish whose health bar
  the game draws red (health 25 or less, 0x41BF33), and plants by
  the status panel's words ("Infested: 2  Unhealthy: 1"; pot +0x28 set, else
  health below 30). A "Counts: On" / "Counts: Off" button (the water's top
  right; the greenhouse wall's top right) hides or shows them, remembered in
  "Tank Counts.ini" / "Greenhouse Counts.ini" beside the DLL, never in a
  save; it takes only a press on itself while nothing is held. Once an extra
  greenhouse is bought the plant button moves to (646, 4), right of the right
  gold arrow and above the greenhouse's name. Drawn
  every frame in each game's own font, on top of the tank or greenhouse (see
  "drawn on top" below), and display only. Each game's companion DLL
  (`Tank Counts.dll`, `Greenhouse Counts.dll`) is loaded by the startup loader
  (after Extra Tanks.dll; Extra
  Greenhouses.dll starts it itself) and loads the DLL the loader loaded before,
  so every combination without the counts keeps its pin. Pictures:
  [docs/images/tank-counts-fish.png](docs/images/tank-counts-fish.png),
  [docs/images/tank-counts-fish-off.png](docs/images/tank-counts-fish-off.png),
  [docs/images/greenhouse-counts-plant.png](docs/images/greenhouse-counts-plant.png),
  [docs/images/greenhouse-counts-plant-off.png](docs/images/greenhouse-counts-plant-off.png).

- No path is too long: the patcher's staging copy and the save backups use
  Windows' extended-length paths, so a deep output or save folder never fails
  with "path too long"; the staging folder's name is also shorter.

- The companion DLLs are named after their settings and kept in
  "Fish Tycoon Fix Patcher DLLs" / "Plant Tycoon Fix Patcher DLLs" inside
  the modded copy: DS Exclusive Fish.dll, DS Store Items.dll, Unused
  Flowers.dll, Store Upgrades and Items.dll, Extra Seed Boxes.dll.

- **Optimize Prices button** (new setting, on by default in both games, in
  the plain "- Modded" copy). Fish Tycoon: an "Optimize Prices" button on the
  Species Chart's bottom bar, left of Done; Plant Tycoon: one on the Nursery's
  bottom bar, at the right. It asks "Set every discovered species to its best
  price per day?" (the game's own Yes/No box); on Yes every discovered
  species' asking price becomes the Breeding Guide's "best per day" price for
  the shop as it is now, and an OK box says "N prices set." Fish: each
  species' base price (with the Advertising rises), the ornaments owned, the
  Golden Seahorse and the Advertising level, with a full selling tank (21 fish,
  or 30 with Bigger tanks; the crowd counts at most 21 adults, as the game does).
  Plant: each species' value, the Golden Berries
  of Wealth, and the visitor limit from the ornaments owned, the magic plants
  found and the bug collection with all 15 sale spots filled, for a healthy,
  flowering plant. The maths is the guide's own, ported to C
  (`native/common/price_math.h`) and checked against the Python for
  thousands of inputs. Only discovered species' price cells are written
  (the ones the game's own price controls write, so the screens and saves
  agree); the DS species and the Unused Flowers are included when those
  settings are on, through new lookups in their DLLs. A companion DLL,
  "Optimize Prices.dll", which the startup loader now loads after any other
  companion; it wraps two slots of the screen's table after checking both
  are the stock ones, or changes nothing.

- **Tools** tab, laid out like the Virtual Villagers Fun Patcher's: links
  for the game on the One Game tab and for each game, each with a "?" guide,
  opening Back Up Saves, Restore Saves, Rename Players and Game Mechanics
  windows that work like VV's. A backup is a checked copy
  (SHA-256, times kept) in the save folder's own Backups folder; a running
  game is paused for it and resumed. A restore, with the game closed, puts
  back the whole folder or one player slot, after backing up the saves as they
  are now. Every change backs the save folder up first.
- **Breeding Guide** (Tools tab), both games: a sortable, searchable sheet
  per part (Fish: Fins and Bodies; Plant: Flowers and Foliage) with how each
  is obtained, its rarity and its species; the species with the pairs that
  breed them, the best price per day and the highest price that sells, each
  with 0 and with Max effects; a Breeding Calculator and a Breeding Planner,
  each with three effects choices: 0 effects, Max effects without the
  mutation, and Max effects with it (Fish: "with Wasp Grouper"; Plant: "with
  Mutation Liquid", the seed after one dose); no mutation changes a price.
  Rarities are in the games' own words: Fish Tycoon's Common, Unusual
  (formerly shown as "Half-rare") and Rare, Plant Tycoon's Common,
  Endangered and Extinct seed packets, Legendary for the Unused Flowers.
  Every part's "how it is obtained" gives each route's exact odds and price
  from the game's code (eggs, starter eggs, Unknown Chemical, seed packets,
  Mutation Liquid, Legendary and Exotic eggs), checked by emulation. It
  names the exact parent pairs by the game's own body, fin, flower and
  foliage names, one line per parent ("Shark with Leaffish, Carp", with the
  chance for a DS or Unused Flowers pair), and names the parts the Unknown
  Chemical or Mutation Liquid turn into it; with spoilers off it names only
  discovered parts and counts the rest ("and 4 pairs with undiscovered
  fins"). No text in the guide shows internal gene numbers, sums or index
  ranges any more (the parts sheets' Index column is gone). A scrolling
  details pane sits under every sheet. Picture tabs: Fin, Body and Egg
  Pictures (Fish Tycoon), Flower, Foliage and Seed Pictures (Plant Tycoon),
  each grouped by rarity in the game's words, with the name and rarity under
  every picture in a scrolling grid. The pictures live inside the patcher:
  the first time the guide finds any copy of the game (the game folder picked
  on the Game tab, the patcher's "- Modded" or "- Modded Upgrades" copies, a
  default install, or a folder picked with the picture tabs' "Find game..."
  button) it copies every sheet it needs, read only (its Images folder, then
  Fish Tycoon's ft.dat, as the game loads them), into "Breeding Guide
  Pictures\Fish" or "\Plant" in the patcher's folder, with a manifest of each
  file's size and SHA-256, written in a temporary folder and swapped in
  whole; from then on every save folder and player shows them with no game
  copy needed. A cache that does not match its manifest is made again, never
  used. The patcher's own art (the DS sheets, Exotic Fish Eggs, the Unused
  Flowers' flower sheet, Legendary Seeds) comes from the patcher's own
  assets. No game art is in the repository or the release: the cache is
  built on the player's machine from their own copy and is ignored by git.
  With spoilers off an undiscovered part is a "?" with no name; with no cache
  and no copy yet, one line says to pick the game folder on the Game tab or
  click "Find game...". It reads the chosen save
  and player only, opens on the species that save has discovered (each
  species' own discovered flag; a species merely made of seen parts is not
  listed, suggested or planned through), and Show Spoilers (remembered)
  shows everything. DS Exclusive Fish
  and Unused Flowers species appear only for a copy patched with them.
  Export to .xlsx (written with the standard library) or .csv. The Fish
  Tycoon rules and prices are checked against the vanilla executable in
  Unicorn (tests/test_breeding_fish.py).
- **Game Mechanics** (Tools tab): how both games really work, read from their
  code, with every random roll's exact odds and what each patcher setting
  changes. It is read-only.
- **Free upgrades**, a new setting (both games), off by default; it needs
  the store's Upgrades screen (DS Store Items / Add new store upgrades and
  items) and turns it on, as Time Warp does. Every item on that screen costs
  $0 (shown as $0, no money taken); stock limits, the purchase questions and
  what each item does are unchanged, and the game's own store items keep their
  prices. Checked by running the store DLLs' own code against the vanilla
  executables in Unicorn (tests/test_store_extras.py).
- **Add Money cheat ($1,000)**, a new setting (both games), off by default,
  with the same dependency. A pile of gold coins (the owner's picture) on the
  Upgrades screen: $950, or $0 with Free upgrades, then +$1,000, any number of
  times. Money stops at the game's maximum: $2,147,483,647 in Fish Tycoon (a
  signed 32-bit int), $4,000,000,000 in Plant Tycoon (its own cash code,
  0x41ED70).
  The item is labelled "Add $1,000" (German "Plus 1.000 $"): Fish Tycoon's title
  font has no "+" and drew a box instead.
- **Time Warp**, a new setting (both games), off by default. A clock (the owner's
  icon) on the store's Upgrades screen: a flat $500 to play 1-72 real-time hours
  as time away, typed into a small Windows popup and confirmed Yes/No. No
  catch-up cap: Fish Tycoon feeds the hours in 4-hour pieces through its own
  fish update; Plant Tycoon moves each plant's clock and runs its own plant
  update, and the seed-restock timer moves too. Refused while time is stopped.
  Live-tested in both games (Normal, 2x / Fast, Stop Time, cancel, no money).
  After the warp has been played, an OK box says what it did, e.g. "Time Warp
  done: 12 hours played (72 age steps). $500 paid." (age units in Plant Tycoon;
  $0 paid with Free upgrades); a refusal shows no such box.
- With a setting that adds new content on (DS Exclusive Fish or DS Store
  Items; Add unused flowers or Add new store upgrades and items), the copy is
  "Fish Tycoon - Modded Upgrades" / "Plant Tycoon - Modded Upgrades" (folder
  and EXE), beside the plain "- Modded" copy, so the two never replace each
  other. A folder you name yourself keeps its name.
- **Restore Saves, one player slot:** the patcher's own files of that slot now
  include their temporary, previous and set-aside copies (for example
  "DS Fish 2.unreadable-1.dat", "Tank Animals 2.previous.dat") and the files
  beside the game's older copies of that save (slot + 20, and + 40 in Plant
  Tycoon). Before, such a file counted as belonging to no slot, so one copy
  that differed refused every one-slot restore.
- **Game Mechanics: every magic fish and magic plant, one by one.** How to get
  each (eggs or shop seeds with exact odds, breeding pairs, the Unknown Chemical
  or Mutation Liquid), its value and what finding it does, plus the win screens,
  the Trophy Case, statistics and one-time messages. Found from the code: a new
  game's two Seed Storage seeds always breed Plant Tycoon's Magic Tree of
  Fragrance. Both pages now cover the same topics, each mapping the other
  game's topics (or saying "not in <game>"), and both say the stores handle no
  hidden keys (no timed stock in Fish Tycoon; only the seed shelves in Plant
  Tycoon). Tests keep the parity.
- **Game Mechanics: Clocks and Hidden keys, clicks and cheats.** Each page now
  starts with a Clocks section (game time = age steps/units, real time = wall
  clock; what Stop Time, message boxes and a closed game do to each timer), and
  every duration names its clock (a test enforces it). New section listing every
  hidden key, click and cheat, from the code: Fish Tycoon's typed tank cheats
  (c +$1000, u full version, w fake win), the hidden Trophy Case strip, the
  selling shop's hidden click spots and all 40 shop tips; Plant Tycoon's
  hotkeys (Space pauses, F1 snapshot, F3 pointer, F10 unchecked price box), the
  faucet's 50 random tips, the nursery decoration clicks and the Sundial. Dead
  code (Fish's expiry check, Plant's "d then w" $50,000 cheat) is marked not
  reachable, also enforced by a test.
- **Game Mechanics accuracy pass.** Every fact on both pages was re-checked
  against the game code: 18 Fish and 21 Plant corrections (for example Growth
  Hormone runs one step's checks, the first-sale bonus only exists in tutorial
  games, the plant-bug qualifier lists, the Crude Butterfly Net, exact Extinct
  and Legendary seed odds), new patched lines for Bigger tanks and Add unused
  flowers, and every time now says real-life time or in-game age steps/units.
- **Game Mechanics: every store item, upgrade and research explained.** Fish:
  each medicine and chemical (doses, odds, which tank), every permanent item,
  ornament and the Second Tank, and Fish Environment and Advertising in full.
  Plant: Soil, Water, Shears, Net and Seed box upgrades one by one, every
  chemical's reach, each nursery ornament's two scores, and the modded Legendary
  Seeds, Radioactive Plant Formula and Fourth-Sixth Seed Boxes.
- **Game Mechanics**: a new "Which tank counts" section (Fish) and "Where things count" section (Plant): magic fish only in their own tank, owned items and ornaments everywhere, food and Ick/Fungal treatment also reach the isolation fish, magic plants permanent once discovered, plants for sale still in their pot.
- **Game Mechanics**: Fish Food research is explained in full (food
  duration per level, sickness odds, food look), and the starter-eggs entry
  shows why the first baby is always a Greenfin Spotanus and how a player
  can still end up without one.
- **Game Mechanics** covers every setting of this release in one consistent
  account: Bigger tanks at 30 fish (Tank 1, Tank 2, the Sale Tank and, with
  3 extra tanks, Tanks 4-6; the isolation tank holds 1), the store animals'
  own records, the Radioactive Growth Hormone's instant births, the Revival
  Potion, ClonaFish, the Revita-Seed and the Formula Bomb, Tanks 4-6 with
  their For sale buttons, the extra greenhouses and nurseries, and the tank
  and greenhouse counts.
- **Breeding Guide**: the Plant Tycoon help now says how "best price per
  day" is worked out (one pot grown to age 24 and sold, then replanted), in
  place of an old sentence that called it the highest price that sells.
- **Breeding Guide pictures**: a save folder whose own game copy is gone
  (e.g. "Fish Tycoon - Modded" after only "- Modded Upgrades" is kept) showed
  "No game copy was found" and "(no picture)" everywhere: the guide looked
  only for the copy named after the save folder, and was not told the game
  folder picked on the Game tab. It now looks in every folder the patcher
  knows (the Game tab's game folder, the output folder and copies and the
  folders they sit in, the default installs) and keeps the pictures in its
  own cache, so they show for every save folder and player of both games.
- **Tank and greenhouse counts are drawn on top.** The counts and their
  "Counts: On" button were drawn right after the screen's background, so
  decorations, ornaments, a big rock or the aerator's bubbles could cover
  them. Fish Tycoon's counts are now drawn first thing in the tank screen's
  overlay (its table's slot 0x443A70), after the tank's whole draw and its
  controls (3 extra tanks' arrows, tank name and For sale button and
  Multiple ornaments' copies included) and before what the hand holds (a
  dragged fish or ornament, a held tool). Plant Tycoon's are drawn at
  0x4291D2 in the greenhouse overlay, after the tables, pots, plants, bugs and
  tools and before what the hand holds, the bottom bar's money and news line
  and the timed messages; 5 extra greenhouses' greenhouse name, drawn after
  the overlay, never overlaps them. Popups and dialogs stay on top. The
  text, its places and the button are unchanged. Neither DLL touches the
  tank's background call (0x422013) or the greenhouse's background slot
  (0x469238) any more.
- **What the patcher adds goes in the trash.** The stock trash can (Fish: bottom
  right of the tank screen; Plant: the Trash bin by the cash) takes fish, seeds
  and plants, never a supply, chemical or ornament. Audited every item the
  patcher adds; the ones it did not take now go:
  - Fish (DS Store Items): Exotic Fish Eggs, the Radioactive Growth Hormone,
    the Revival Potion and ClonaFish let go on the trash can are thrown away,
    the whole slot with every dose or hatch left (the slot emptied as the game
    empties a used-up one), with the fish trash's sound and no question (the
    game asks only about a live fish). New site 0x421B52 (the release's call
    of the supply use).
  - Fish (DS Store Items): the Moray Eel and its rock now go together also
    when one of them is in Tanks 4-6 and the other is not (3 extra tanks'
    held tanks are searched after the stock ones).
  - Plant (Add new store upgrades and items): the Radioactive Plant Formula,
    the Formula Bomb, the Revival Potion and Revita-Seed, held from the
    chemical tray and let go or clicked on the bin, are thrown away with
    every dose left, with the bin's sound and no question, as a seed packet
    (the bottle leaves the tray as the game empties a used-up one). A plant
    selected at the time is never asked about or deleted. New sites 0x425FF2
    (the mouse-up's trash call) and 0x4272DC (the press off the pots).
  - Already taken, unchanged: Multiple ornaments' copies (after the game's
    question, any tank, Tanks 4-6 too; never the original), the DS store
    animals and the Golden Seahorse (the fish trash), anything in Tanks 4-6
    and Greenhouses 2-6 (shown in a stock place, so the stock trash runs),
    Legendary and new-flower seeds (sold for their value).
  - Never taken, as stock: the tools (Fish: the food; Plant: the watering
    can, shears, net and the other rack tools) and the game's own medicines,
    chemicals and eggs.
  - Tests: tests/test_trash_patcher_items.py runs every case on the vanilla
    executables in Unicorn (dropped on the can, by one pixel off it, in a
    maximized window, Tanks 1-6, the tools and stock supplies kept).
- **"Contains N doses."** Every patcher chemical's store description ends
  with the stock wording (the owner's rule): the Radioactive Growth Hormone
  said "Enough for 3 treatments." and the Radioactive Plant Formula Bomb
  "Contains 3 bombs."; both now say "Contains 3 doses.", as the Revival
  Potion, ClonaFish, Revita-Seed and the formula already did. The German
  Fish Tycoon texts keep the game's own "Reicht für 3 Behandlungen.".
  tests/test_consumable_doses.py checks every store item's text against the
  doses a purchase really gives.
- The patcher window keeps its pictures and remembered choices in its own
  Tk interpreter: with another Tk window still open, its title-bar icon
  could fail to load ("can't use pyimage as iconphoto").

### Plant Tycoon

- **5 extra greenhouses** (EXPERIMENTAL - USE AT OWN RISK), a new setting,
  off by default, in the "Modded Upgrades" copy (needs Add new store upgrades
  and items). Every greenhouse screen is named ("Greenhouse 1" the stock
  one). Up to six greenhouses of 15
  pots, 90 pots in all. An Extra Greenhouse item on the store's Upgrades
  screen sells Greenhouses 2-6 in order, $10,000 each ($0 with Free
  upgrades), ticked when all five are owned; a new game starts with none.
  The game's own gold arrows on the greenhouse screen page through
  Greenhouse 1 (the stock one) and the ones you own, and the screen says
  "Greenhouse n of m". Every
  greenhouse is the stock screen with the game's own code running on its
  pots, so every plant, chemical, tool, upgrade and magic plant works the same
  in each, and every greenhouse grows while you look elsewhere, while you are
  away and through the Time Warp (checked in emulation byte for byte against
  the stock pots). Drag a plant onto an arrow to move it to the same pot place
  in the next (or previous) greenhouse, or its first empty pot if that place
  is taken; pollen and seeds taken from a plant are carried between
  greenhouses, and held tools, chemicals and tray seeds stay in hand. Without
  extra nurseries the nursery keeps its 15 spots: at most 15 plants are for
  sale at once, counting every greenhouse. Greenhouses 2-6 are kept per save
  slot in "Plant Tycoon Fix Patcher Data\Extra Greenhouses <slot>.dat"; the
  save keeps its stock layout. Empty them before switching the setting off.
  Design: docs/plant-tycoon-extra-greenhouses-design.md; pictures:
  docs/images/extra-greenhouses-switch.png, extra-greenhouses-store.png.
- **5 extra nurseries** (EXPERIMENTAL - USE AT OWN RISK), a new setting, off
  by default (needs Add new store upgrades and items). An Extra Nursery item
  on the Upgrades screen's Nursery shelf sells Nurseries 2-6 in order,
  $10,000 each ($0 with Free upgrades). Without any, the stock limit of 15
  plants for sale holds; each one bought adds 15 (90 with all five). Each
  nursery is the stock nursery screen with its own 15 spots, visitors, prices
  and sales, named at the top ("Nursery 1" the stock one), with gold arrows
  to page through the ones you own; tagged plants fill them in order. While
  you are in the nursery all bought nurseries sell at once through the
  game's own buy roll (visitors only for the one on screen).
  Picture: docs/images/extra-nurseries-switch.png.
- The Time Warp also moves the clocks of the extra greenhouses' plants.
- Free upgrades also makes the Extra Greenhouse and Extra Nursery free.
- **R refreshes the seed shop**, a new setting, on by default. Press R in the
  Supplies store to restock the seed shelves at once (Legendary Seeds too),
  through the game's own restock roll (0x41DC60). Three byte changes: the
  store's ignored-key case goes through 32 bytes in the zero tail of .text.
  Proven by emulating the patched key handler.
- **Sort Seeds button**, a new setting, off by default. A "Sort Seeds"
  button on the Seed Storage title bar asks "Sort Seeds in Seed Boxes?" (Yes /
  No), then sorts every seed in the unlocked seed box space: by the class of
  the plant it grows (A to D), its foliage, its flower, then its parents
  (unknown "?" first), packed from the first slot, boxes 1-3 before 4-6.
  The sort is built in a copy and written only if it holds exactly the same
  seeds. Works with the Fourth-Sixth Seed Box arrows. Game Mechanics has a
  "Sorting seeds" section.
- **Add unused flowers**, a new setting, off by default. The 14 flower heads that
  ship in the game's art but no plant uses become flowers 24-37:
  - the owner's names: Nightingale, Rosetta, Lilac, Veronica, Violetta, Stella,
    Silvermist, Anagallis, Buttercup, Cerulean, Phalaena, Mirabilis
    (recoloured golden), Indigoberry and Prunus;
  - 322 new species, all in the rarest class;
  - reached by Mutation Liquid (now running over flowers 1-37 with unchanged
    odds) and by breeding.
  - It runs as "Unused Flowers.dll", loaded by a startup loader the patcher
    appends to Plant Tycoon.exe (the same loader as DS Fish), all or nothing.
  - It also stops the game's own out-of-range writes and the crash a new
    flower would otherwise cause in Bio-organic Plant Food, the Fertilizer
    Bomb and Mutation Liquid.
  - Saves keep their stock layout; the new species' prices and discoveries
    go in a file per save slot.
  - Mirabilis: a third of its trumpet tube, fading out, no green bulb,
    anchored halfway between the bell and the tube's end.
- **Add new store upgrades and items**, a new setting, off by default,
  needs Add unused flowers. An Upgrades link on the bricks of the Supplies
  store opens a view with only the new items, where they would sit in the
  store:
  - Legendary Seeds (three a day, $5000, prismatic packets, any foliage with a
    new flower; the stock packets keep their stock flowers);
  - Breeding with one of the new flowers follows the DS fish rule: the
    parents' average, an odd sum rounded up or down at random (stock x
    stock still rounds up, as in the game). It is part of Add unused
    flowers, so it works without the store upgrades too.
  - Radioactive Plant Formula ($10,000, 3 doses): far beyond spamming
    Fertilizer Bombs and Plant Food. Every branch grows (dead ones and the
    ones the plant's shape normally hides), the largest size, full bloom,
    and a flower on every spot of every branch and leaf: up to 6 per part,
    hundreds on a big plant. No dead leaves, full health, and always 5
    seeds (the owner: they were not consistent): a plant already pollinated
    gets all its seeds ripe at once (through the game's own ripening: its
    pollination age is moved 7 units back), and any other gives all 5 at
    its next pollination, infested or not (the old formula only gave back
    a pollinated plant's held-back seeds, still to ripen over 7 units, and
    left a plant pollinated later at the stock 5, 4 or 3). The mark is
    cleared when a new plant is planted in the pot. The Formula Bomb gives
    every plant it reaches the same.
  - Radioactive Plant Formula Bomb ($30,000, 3 doses): the stock Fertilizer
    every plant it reaches the same. A plant for sale stays for sale (the
    owner: the chemicals should not clear the Sell tag): the formula set
    the game's one-byte "branch roll done" flag (+0x9C) with a 4-byte
    write, which also cleared the next bytes, the on-sale flag (+0x9D) and
    the sold flag (+0x9E); it now writes the one byte, as the game does.
  - Radioactive Plant Formula Bomb ($30,000, 3 bombs): the stock Fertilizer
    Bomb's art made rainbow. One bomb gives every live plant in the
    greenhouse on screen one Radioactive Plant Formula dose: the pots the
    Fertilizer Bomb reaches, read from its own code.
  - Revival Potion ($10,000, 3 doses): a dead plant comes back to life at
    full health, with its value and price set again by the game's rules;
    parts dead before it died stay dead, as with the game's own healing.
    A plant that was for sale when it died is for sale again (the game
    takes a dead plant off sale at every update; the DLL remembers it in the
    pot's record, byte +0x9F, which no game code uses, so it follows the
    plant through Greenhouses 2-6, the nurseries and the save). If the
    nurseries are already full (Extra Greenhouses: 15 for sale per nursery
    owned, over every greenhouse) it stays off sale and a message says so.
  - Revita-Seed ($2,500, 3 doses): a plant that has given all its seeds can
    be pollinated again, exactly like a fresh plant.
  - the Fourth, Fifth and Sixth Seed Box ($1000 each): a second chest on
    the Seed Storage screen behind gold arrows, also filled by the greenhouse
    once boxes 1-3 are full.
  - It runs as "Store Upgrades and Items.dll" and "Extra Seed Boxes.dll", loaded
    by the unused-flowers DLL; the stock images are never replaced and saves
    keep their stock layout.
- The release ZIP now packages every companion setting's files (New Flowers'
  were missing).
- **Fix Vanilla Bugs**, a new setting (as in Fish Tycoon), on by default.
  Fixed: a new save no longer starts with every plant at the Flower of
  Knowledge (Nox Orchid) price, V + 3 x (V/4), though it has not found the Nox
  Orchid. The stock new game (0x41EF30) priced every species (0x41DBD0, called
  at 0x41EFB8) before it cleared the magic plant flags (0x41F170), so it used
  the flag of the save that was open, and the game opens your last save when
  it starts. The call at 0x41EFB8 now goes through a few bytes in the zero tail
  of .text (0x464950) that clear those same seven flags (state +
  0x2180..0x2186) first. Finding the Flower of Knowledge still raises every
  price, and Unused Flowers' 322 species follow suit. Proven by emulating the
  vanilla and patched code (tests/test_knowledge_price_new_game.py). Fish
  Tycoon has no such price.
- Fix Vanilla Bugs also repairs existing saves with Nox prices but no Nox
  Orchid: they are re-priced the first time they load. The load's call at
  0x41EEF9 (just after the save is copied in) goes through 0x464970 first. A
  save is repaired only when its Flower of Knowledge flag is clear and every
  species it has not discovered (V of 4 or more) asks exactly V + 3 x (V/4),
  a price the stock rule cannot give without the flag (V -+ Random(V/2) stays
  within V/2 - 1 of V). Only those undiscovered species are re-priced, by the
  price setup's own formula and Random calls; discovered species keep their
  prices, which you may have set, and a save with any other undiscovered
  price is left alone. Nothing else in the save changes, the game saves the
  new prices at its next save, and the repair never runs twice. Unused
  Flowers re-prices its 322 species in the New Flowers file by the same rule.
  Proven by emulating the vanilla and patched load
  (tests/test_knowledge_price_load_repair.py).
- **Credits:** Plant Tycoon's new flower names are by Virtual_Lady and
  Lorsieab2 (README, How to Use, the patcher window and the setting).
- Plant Tycoon, 5 extra greenhouses: the gold arrows now stand right beside
  "Greenhouse n of 6" on the top wall (x 367-416 and 583-632), where they can
  be seen and clicked; they were under the stock left panel and the camera
  button. Dragging a plant onto them uses the new places.
- **Automatic Sprinklers and Auto-Healer** on the store's Upgrades view (the
  sprinklers on the tool shelf under the Extra Greenhouse, the healer beside the
  Formula Bomb; chemical sheet rows 16 and 17): $10,000 each ($0 with Free
  upgrades), bought once with the same Yes / No as Add Money. At the top of
  every age unit of every live potted plant (every greenhouse, Greenhouses 2-6
  too, time away and the Time Warp unit by unit; hooks at 0x42E134 and
  0x42E2DF) and after each update: water 800 (never dry, below 100, and below
  the 900 above which the pest odds triple); pests cleared (one Plants
  Cured each) and health 100. A dead plant is never touched; a plant that dies of
  old age during a catch-up stays as the game leaves it. Dead branches from the
  age-7 roll are part of growth and stay.
- Unpurchase as in Fish Tycoon; ownership in "Plant Tycoon Fix Patcher
  Data\Auto Upgrades <slot>.dat".
- Mockups: docs/images/auto-upgrades-fish.png, docs/images/auto-upgrades-plant.png.

### Fish Tycoon

- **3 extra tanks**, a new setting, off by default, EXPERIMENTAL - USE AT OWN
  RISK, in the "Fish Tycoon - Modded Upgrades" copy. It needs DS Store Items
  (and turns it on): the tanks are bought on its Upgrades screen, the Extra
  Tank item, $10,000 each ($0 with Free upgrades), Tank 4, then 5,
  then 6; until then a tank's button is greyed out and refuses ("You
  don't own this tank yet!"), and the arrows skip it. Tank 4 looks like
  Tank 1, Tank 5 like Tank 2, Tank 6 like the Sale Tank without
  its For Sale sign (the game's own background and decoration draws). Tank 4, Tank 5 and Tank 6 are full tanks
  like Tank 1 and Tank 2, for breeding: fish live, age, eat, get sick,
  breed and give birth in them, and food, medicines, chemicals, eggs,
  ornaments, research, the plants, the magic fish, the Golden Seahorse, the
  DS store animals and Bigger tanks (30 fish) work there exactly as in a stock
  tank. Two
  small arrows left of the Tank 1 button page the tank buttons to the three
  new tanks and back; drag a fish, animal or ornament onto a button to move it
  there, or onto an arrow to move it to the previous or next tank (Tank 1,
  Tank 2, the Sale Tank, Tank 4, Tank 5, Tank 6, round). Each extra tank
  has a "For sale" button (Off at first): On shows the Sale Tank's For Sale!
  sign and sells its fish together with the Sale Tank's through the game's
  own sale roll, each selling tank lent the Sale Tank's place in turn (one
  sale a second, the same odds; the sale scene's pictures and "Fish for sale"
  count cover every selling tank; the crowd stays within the stock maximum).
  Every tank screen shows its name: Tank 1, Tank 2, Tank 3 (the Sale Tank),
  Tank 4, Tank 5, Tank 6. The toggles are saved per slot. The DS store
  animals move with their tank: in Tanks 4-6 they keep their own 5 animal
  places per tank, saved in the extra tanks' file (version 4 of it stores
  each tank's 5 animal records after its block; a version-3 file's animals,
  kept in fish records 26-30, are moved over when it loads), and DS Store
  Items' "one of each" check (with Buy Multiple Golden Seahorses off) sees
  the animals in Tanks 4-6 too. The game has room for four tanks
  only, so a companion DLL (`Fish Tycoon Fix Patcher DLLs\Extra Tanks.dll`)
  keeps three more tank blocks and runs the game's own code on them: the tank
  on screen is swapped into Tank 1's place, and every fish update runs the
  game's own update once more over the other blocks. The saves keep their
  stock layout; each slot's extra tanks are in `Fish Tycoon Fix Patcher
  Data\Extra Tanks <slot>.dat`. Empty them before turning the setting off.
  Checked tick for tick against a stock tank in emulation
  (tests/test_extra_tanks.py). Design:
  [docs/fish-tycoon-extra-tanks-design.md](docs/fish-tycoon-extra-tanks-design.md).
- **Maximizable window**, a new setting, on by default, in the plain
  "Fish Tycoon - Modded" copy. In windowed mode the Maximize button works and
  the window can be resized by its edges. Fish Tycoon draws through SDL 1.2 at
  a fixed size, and SDL gives its window no maximize box and pins its size.
  At any other size than the game's own, the picture is scaled to fill the
  window with its shape kept, black bars where it does not fit, smoothed
  (GDI HALFTONE; at a size where smoothing would take over 11 ms a frame,
  nearest pixel instead, so the game keeps its 33 ms frame), and the mouse
  is mapped back to the game's coordinates. At the game's own size (restored)
  and in fullscreen, everything goes through SDL exactly as before. A
  companion DLL (`Fish Tycoon Fix Patcher DLLs\Maximizable Window.dll`)
  routes the game's SDL_SetVideoMode and SDL_Flip imports through itself,
  after checking both and their thunks (0x42A606, 0x42A62A), both or neither.
  With DS Exclusive Fish on, its DLL loads this one. Plant Tycoon is not
  included: it draws through SDL2 (a different renderer). Emulated in
  tests/test_fish_window.py.
- **Fix Vanilla Bugs**, a new setting, on by default. In the stock game the
  two plants do each other's job: the $200 Plant of Incubation rescues
  starving fish and the $350 Plant of Nutrition adds 1 egg per batch. Four
  code bytes swap which plant each effect checks, so the Plant of Incubation
  adds the egg (Exotic Fish Eggs too) and the Plant of Nutrition rescues
  starving fish. Names, pictures, prices and saves are unchanged.
- **Tank creatures have full meters** (owner's request). With Fix Vanilla
  Bugs the Golden Seahorse is bought with health 100 and food 100 (stock:
  health 80-94, food 50), and with DS Store Items so are the Puffer Fish,
  Sting Ray and Moray Eel (they copied the seahorse's 80-94 and 50). A
  creature already in a save, the eel in its rock included, is filled to
  100 and 100 the first time the save is loaded with the patch, by the game's
  own load before anything reads the meters; the game saves it as usual.
  Nothing in the game ever lowers these meters (the age step skips them, and
  overfeeding never hurts them), so they stay full and no sidecar is needed.
  Only the two meters change: fish and everything else in the save load
  exactly as before. Proven by emulating the game's purchase and load code,
  stock and patched, and the DS Store Items DLL's (tests/test_vanilla_fixes.py,
  tests/test_store_extras.py).
- **Bigger tanks: 30 fish**, a new setting, off by default. Tank 1, Tank 2
  and the Sale Tank (Tank 3) hold 30 fish instead of 21 (the isolation tank
  still holds one; with 3 extra tanks, Tanks 4-6 hold 30 too, by the game's
  own AddFish limit): 28 byte changes to every place that assumes 21, so fish
  22-30 get everything fish 1-21 get (ageing, food, health, sickness and its
  spread, breeding, magic fish, medicines, chemicals, growth hormone, the
  store animals' effects, customers, selling). 30 is 10 x 3, so the loops the
  compiler unrolled three at a time only change their count. Every adult in
  the selling tank is for sale with the stock odds per fish, one sale a
  second at most as in the stock game; the crowd counts at most 21 adults,
  the stock game's most (one short routine). The state already has 31 fish
  records per tank and saves all of them, so the save layout is unchanged.
  Each family of effects is run in the game's own code, stock and patched,
  with the fish in slot 0 and in slot 29, and gives the same result
  (tests/test_fish_30.py). An earlier preview had this at 26 fish.
- **DS Exclusive Fish**, a new setting, off by default (fish manifest
  v1.3.0). The Nintendo DS version's seven extra bodies and seven extra fins,
  343 new species:
  - Reached only through the Unknown Chemical and the Magic Fish of Mutation,
    which can now step a Spotanus body or Twin-Fin fin one place further, with
    unchanged odds. Eggs, the store and two PC parents never give them.
  - A pair with a DS parent breeds by the DS game's rule (the average, an odd
    total rounded up or down at random); PC x PC is unchanged.
  - Prices, rarity tiers, names and fin placement come from the DS game.
    Sprites are generated from the DS art in the PC's 18-frame turn layout,
    with every DS fin placed per body/fin pair as the DS draws it.
  - Runs as a companion DLL ("DS Exclusive Fish.dll") loaded by a small startup
    loader the patcher appends to the executable. It checks all 69 places it
    changes in the running game and installs all of them or none, and writes
    a one-line log of the result. DS species data that does not fit the save
    goes in a separate file per save slot; saves keep their stock layout.
  - Docs: docs/fish-tycoon-ds-fish-testing-guide.md (how to get each fish),
    docs/fish-tycoon-ds-fish-technical-map.md (every address),
    docs/fish-tycoon-pc-vs-ds-differences.md (how the PC and DS differ for
    magic fish, items and research).
- **DS Store Items**, a new setting, off by default, that needs DS Exclusive
  Fish. An Upgrades button in the Supplies store opens the DS version's
  store items:
  - Puffer Fish, Sting Ray and Moray Eel, $1250 each: tank companions built
    like the Golden Seahorse, with the DS effects rescaled to the PC's age
    steps (health for healthy fed fish, food, and the eel's 1-in-10 save of
    a dying fish). The Golden Seahorse keeps its PC effects and gains its DS
    one.
  - The animals, the Golden Seahorse included, never take a fish's place:
    each tank has 5 animal places of its own, kept beside the save in
    "Fish Tycoon Fix Patcher Data\Tank Animals <slot>.dat" (written each
    time the game saves, atomically, and read back), so all 30 fish slots of
    Bigger tanks stay the fish's. A save from an earlier build, which kept
    them in fish slots 26-30, has them moved there the first time it loads;
    those slots are cleared only once the file is written. The file names
    the save it belongs to, so a save restored from a backup never picks up
    a later one's animals (such a file is set aside, never deleted). With
    Buy Multiple Golden Seahorses on they can be bought more than once.
  - The Puffer Fish puffs up now and then while it swims.
  - Holding an animal shows its name in the tank's info panel, as a fish's
    does: Golden Seahorse, Magic Pufferfish, Blue-Spotted Stingray, Moray
    Eel (the stock game showed none, not even for the Golden Seahorse). The
    store sells them under these names. Magic fish, medicines, chemicals and
    the store animals' own effects never touch the animals.
  - The Moray Eel's rock is a movable decoration; the eel goes home in it,
    moves with it, and is dragged out by its head. Trashing the eel trashes
    its rock, and the other way round. At home it idles in the cave mouth
    (a frame every 10 seconds) and every 30-90 seconds plays the DS's
    action burst at the DS's pace: it ducks, peeks, lunges and snaps out in
    front of the rock with a bite. Where the DS shows it behind the rock,
    it is drawn in front of it.
  - DS fins now sit on the body in the game: a left-facing fish (frames
    0-5) draws its fins at x + 50 - anchor and a right-facing one at x +
    anchor, the other way round from what the DS pair anchors assumed, so
    every DS fin was 8-26 px toward the head.
  - Exotic Fish Eggs, $2300: hatch only DS-exclusive bodies and fins.
    With Universal supply slots on, they stack and hatch from any of
    slots 2-4, like the stock eggs.
  - Radioactive Growth Hormone, $10,000 ($0 with Free upgrades), 3 doses:
    the stock Growth Hormone's bottle, shelf picture and dropper recoloured
    green (scripts/build_growth_hormone_assets.py, from the game's own art;
    picture: docs/images/radioactive-growth-hormone-fish.png). It is bought
    into slot #3 like the stock chemicals ("Replace chemical in slot #3?"
    if one is there; with Universal supply slots it stacks 3 doses a
    purchase and works from any of slots 2-4) and used on a tank the same
    way. Each dose reaches every live fish in the tank you use it on, any
    age (the owner: the stock Growth Hormone stops at 40, and stays
    stock). Every pregnant one gives birth at once through the game's own
    birth code, call for call (the litter, the Magic Fish mutation of the
    father's genes, the Magic Fish of Fertility's and the Plant of
    Fertility's extra babies, and a full tank losing the babies, all as a
    natural birth; the isolation tank never gives birth, as stock). The
    babies stay babies, exactly as born (the owner: a dose had raised them
    to 20, the age the game shows a species name from, so baby fish showed
    their names); a later dose grows them up. Then each fish that was in the
    tank before the births becomes an adult
    (age 20) if younger, gets full health (100) and is cured of ick or
    fungus (counted under Fish Cured); older fish keep their age. Dead fish,
    other tanks and the store animals are not reached. Fry are fish in the
    tank (eggs hatch straight into age-1 fish), so they grow up too; eggs
    on the shelf are not touched.
    On every difficulty, Hard included, the next update runs only one
    step's health, sickness and food checks, as the stock hormone does on
    Easy and Medium, so the fish stay healthy (the stock Growth Hormone is
    unchanged: on Hard it still runs every skipped step). DS Exclusive Fish now lends the
    store 24 sprite entries (was 16).
  - Revival Potion, $10,000 ($0 with Free upgrades), 3 doses, the owner's
    amber flask: a slot-#3 chemical like the hormone. Each dose revives
    every dead fish in the tank on screen at full health (100). A dead fish
    is only health 0 in the game, kept in the tank until you throw it away;
    the potion sets health 100 and the fish's clock to now, so the time it
    lay dead is not played as time away. Age, food, sickness and pregnancy
    stay as they were.
  - ClonaFish, $2,500 ($0 with Free upgrades), 3 doses, the owner's magenta
    bottle: each dose clones every live fish in the tank on screen once,
    any species, so each dose doubles the tank (the owner: it first cloned
    only fish no other fish shared a species with); an exact copy of its
    record, through the game's own AddFish, in slot order until the tank is
    full. The fish there before the dose are copied, so this dose's clones
    are cloned by the next dose, not this one. "The tank is full!" shows if not one
    could be cloned.
  - The new items read the game's own limits (the update's slots and tanks,
    the hormone's loop end, AddFish's), so they work the same with Bigger
    tanks, 30 per tank and extra tanks.
  - The new icons match their neighbours' visible size (the stock Growth
    Hormone's: 57 px in the store, 31 on the shelf); previews in
    docs/images/revival-potion-fish.png and revival-potion-plant.png.
  - Selling-tank customers no longer look at any seahorse-type companion
    (stock code read the Golden Seahorse's species data out of range).
  - Runs as "DS Store Items.dll", loaded by "DS Exclusive Fish.dll"; all or
    nothing, with its own log. Besides the game's own save, only the
    animals' "Tank Animals <slot>.dat" (and, with 3 extra tanks, the extra
    tanks' file) is written.
- **Multiple ornaments**, a new setting, off by default, in the "- Modded
  Upgrades" copy (owner's request: "the effect only works once and doesn't
  stack, the others are just for decorating!"):
  - The Shell, Pagoda, Diver, Fancy Coral, Sunken Antique Column and Sunken
    Ship can be bought again once owned, at their stock price, even with one
    already in that tank or another. Up to 10 extra copies per tank.
  - A copy is drawn, falls to the gravel, and is picked up, dragged, dropped
    and moved to another tank's button by the game's own ornament code, so it
    behaves exactly like the original; the trash can takes a copy (after the
    game's "Delete?" question), never an original.
  - The effect is counted once, as in the stock game: an ornament's only
    effect is that you own it (one more customer in the selling scene, fewer
    "more decor" thoughts), game-wide. Copies never touch it, and the
    customer and thought numbers are identical with 0, 1 or 3 copies
    (checked by emulating the game's own code).
  - Copies are kept beside each save slot in "Fish Tycoon Fix Patcher
    Data\Ornaments <slot>.dat" (written whole, then moved into place); the
    save keeps its stock layout and size. A file that cannot be read is set
    aside as "Ornaments <slot>.unreadable-N.dat", never deleted.
  - Runs as "Multiple Ornaments.dll", loaded by the startup loader before
    DS Exclusive Fish's or the Maximizable window's DLL; ten places, all or
    none, with its own log. Picture:
    docs/images/multiple-ornaments-tank.png.
- **Maximizable window: clicks land under the cursor.** In a maximized or
  resized window the game's own cursor was drawn at the unscaled pointer
  position (SDL reads the pointer itself with GetCursorPos + ScreenToClient
  after every batch of messages), while clicks were scaled, so a click landed
  up and to the left of the cursor: Tank Five or Six opened the Trophy Case
  (the magic fish shelf) and its Done button could not be hit. The DLL now
  also scales SDL's own ScreenToClient, so the cursor, hovers, clicks and drags
  all agree. At the window's own size nothing changes.
- **3 extra tanks: one place for "You don't own this tank yet!".** It was
  drawn beside the mouse, so a click on Tank Six put it off screen. It is now
  centred across the screen just under the top bar, for every button, arrow
  and drop.
- **3 extra tanks: carry over an arrow to reach Tanks 4-6.** Carrying a fish,
  DS store animal or ornament over either small arrow turns the tank buttons
  to the other page (once each time it comes onto an arrow), so it can be
  dropped on any of the six tanks' buttons. Letting go on an arrow itself
  keeps it where it was (before, an arrow moved it to the previous or next
  tank).
- **Optimize Prices on the Fish Store screen.** The Species Chart opens only
  with a fish in the isolation tank, so the Optimize Prices button is now also
  on the Fish Store screen, opened with Sell Fish, on its bottom bar between
  "Your cash" and Done. It is the Species Chart's button, lettered in the
  game's own font on that screen's bar, and a click does exactly what the
  chart's does: the same question, the same prices for every discovered
  species (native/common/price_math.h) and the same "N prices set." The chart
  keeps its button. "Optimize Prices.dll" now wraps four slots, the chart's
  command and opening and the Fish Store's, all four or none; the sale
  scene's customers and sales (and Extra Tanks' changes to them) are
  untouched. Picture: docs/images/optimize-prices-fish-store.png.
- The Optimize Prices pin script keeps the setting where it is in the
  manifest when it re-pins (it used to move it after the Maximizable window).
- **Auto-Feeder and Auto-Healer** on DS Store Items' Upgrades page, beside
  ClonaFish: $10,000 each ($0 with Free upgrades), bought once with the
  game's purchase question. In each age step of every live fish in every tank
  (Tanks 1-2, the Sale Tank, the isolation tank, all 30 slots with Bigger
  tanks, Tanks 4-6 with 3 extra tanks, on screen or not, time away and the Time
  Warp included), right after the sickness roll (a new hook at 0x4204B3): the
  Auto-Feeder keeps food full at 100 (never below 5, never starving; while it is
  owned a feeding by hand never costs health for overfeeding, a hook at
  0x4121F4); the Auto-Healer clears
  fungus and ick (one Fish Cured each) and sets health to 100, again at the
  step's death test. A dead fish is never touched. The owner's art: the green
  feeder and the same machine in hot pink (scripts/build_auto_healer_source.py),
  57 px tall like the store's other pictures (scripts/build_auto_upgrades_assets.py;
  DS Exclusive Fish lends two more sprite entries, 244 and 245).
- Clicking an owned one again asks "Unpurchase ...?" (Yes / No): Yes switches it
  off at once, no refund; buying it again costs the full price.
- Ownership per slot in "Fish Tycoon Fix Patcher Data\Auto Upgrades <slot>.dat",
  written with the save (a .tmp renamed over); a new game owns neither.

## v1.0.16

Fixes from a full audit of both games' patches and of the patcher around them.
Every patch was re-traced in the game code, every setting combination was
re-applied to the supported LDW executables, and each patched build was put
through the Windows loader with its patch bytes checked in memory. The patches
themselves were all correct; the fixes below are in the patcher, its texts and
its documentation.

### Fish Tycoon

- **Unknown Chemical: 3 uses** now also corrects the German store text,
  "Reicht für eine Behandlung." becomes "Reicht für 3 Behandlungen." (the
  game's own wording for Growth Hormone). Only the English line was changed
  before. Manifest v1.2.11; the pinned hashes of the eight combinations that
  include this setting changed, the other seven did not.
- **Universal supply slots 2-4** now warns, in both tabs, that switching it on
  or off on a save that already holds supplies changes their uses: an egg or
  Unknown Chemical bought with the setting off lasts three uses once it is on,
  and stacks or items in other slots misbehave after it is turned off. The
  executable cannot tell a leftover record from a real stack, so the warning
  asks players to use up slots 2-4 first.
- The Fish engine now enforces the resource-section pin its manifest declares,
  as the documentation already said it did.

### Both games

- **Patch Both** no longer writes one game and then refuses the other. An
  existing output folder the patcher did not create is now refused in the
  dry run, before anything is written, and a failed final swap puts the
  previous modded folder back.
- Games whose files are read-only now patch, re-patch and restore. Before,
  patching failed with "Access is denied" and left a staging folder behind
  on every attempt.
- The patcher window no longer gets stuck when its settings file cannot be
  saved (for example when it is extracted somewhere read-only): it still
  patches and closes, and says once that your choices will not be
  remembered.
- The save-location documentation is corrected. Both games keep saves in
  `Documents\LDW\<exe name>\<game name><number>.ldw`, so a modded copy has
  its own folder; the docs had the folder and file names swapped.

## v1.0.15

### Add Missing Assets to LDW Version

New Plant Tycoon setting, on by default. It adds sounds and images the LDW
download is missing, using the Steam version's files, which now ship in
`assets/plant_tycoon_steam/`. LDW no longer updates the games, so this is the
one exception to shipping no game files.

- Only additive. A file is copied into the modded folder only where the game
  lacks it. A game file is never replaced, and a bundled file identical to the
  game's own is ignored. The patch log records each file as added, identical
  and ignored, or kept at the game's version.
- Turning the setting off and patching again produces a folder without the
  added files, because every run rebuilds the modded folder from the vanilla
  one.
- Every bundled file is pinned by size and SHA-256 in the manifest, and all
  are checked before anything is written. `scripts/pin_plant_assets.py`
  regenerates the pins.
- `.gitattributes` keeps git from converting line endings in the bundle, so
  every checkout gets the exact pinned bytes. The release build checks every
  packaged asset against its pin, and a test compares what git stores with
  the pins.
- The executable is not touched, so the pinned executable hashes are
  unchanged and the setting has no effect on them.
- Upgrading keeps the new default. The saved settings file now records which
  settings existed when it was written, so a setting added later starts at its
  default instead of loading as unticked. Files from v1.0.14 and earlier are
  read the same way, and every choice they did record is kept.
- Plant manifest is now v1.1.0 (`plant-tycoon-pc-fixes-v2`). Folders written
  by the previous revision are still recognised and replaced normally.


## v1.0.14

The patcher now shows what each setting actually changes, not just what it is
for. No patch data, manifest or executable output changed.

- Every setting gained a **Technical details** disclosure listing each byte-level
  change it installs: the virtual address, the file offset, the size, and the
  note explaining what that change does and why. Collapsed by default, so the
  window stays readable for players and the detail is one click away for anyone
  who wants it.
- The PE checksum records are summarised in one line rather than listed
  individually; there is one per setting combination and they are bookkeeping
  rather than behaviour.
- Entries are grouped by the location they change, so several manifest entries
  writing the same place appear once, with a note saying variants exist.
- Tests assert every setting has detail, every change carries a note, the
  virtual addresses match the known layout, and nothing a setting installs is
  missing from what the reader sees.


## v1.0.13

Quality pass. No patch data, manifest or executable output changed.

- The packaged Fish technical details still carried a v1.2.6 heading while the
  manifest had moved to v1.2.10, so a reader of the release ZIP was told they
  were looking at a version that no longer exists. Corrected, and tests now
  fail if that heading stops naming the manifest version, or if a shipped doc
  describes a working setting as non-functional.
- Removed the orphaned v1.0.8 tag, left behind when that release was deleted.


## v1.0.12

### Buy Multiple Golden Seahorses

The Golden Seahorse setting works, and is renamed from "allow repurchase" to
"Buy Multiple Golden Seahorses" to say what it actually does. Its display name
changed; its id did not, so saved selections still resolve.

The base game blocks a second purchase in three separate places, all keyed off
the ownership dword at `state + index*20 + 0x78`:

- the store click handler compares that dword against the `+0x7C` field at VA
  0x4282CA and refuses when they differ
- the purchase routine returns at VA 0x427B66 before the code that deducts the
  price, so a confirm prompt appears but nothing is charged or granted
- the panel redraw shows "This is in your inventory." instead of the price at
  VA 0x42735C

Each is wrapped so store item 11 takes the normal buy path and every other item
keeps its original behaviour. Verified in game: the price shows, the purchase
charges, and the seahorse appears in the first free tank.

The setting is now on by default, alongside the other three fixes.

Everything shipped for this setting before v1.0.12 was wrong. It targeted item
18, the Diver Ornament; its jump landed one byte before its own wrapper; and
its second hook sat on the research items' code path. Those are recorded in
docs/golden-seahorse-defects.md.

### Other

- Plant Tycoon's old-age setting now spells out the routine: a plant's age
  starts at 0, becomes eligible once it passes 1720.0 internal age units (the
  double at VA 0x4695E0), and from then every update rolls Random(1000) and
  kills on 0-9, a 1% chance per eligible update that keeps recurring for the
  rest of the plant's life. The patch makes that range empty, so the chance is
  exactly 0. Plants still die of neglect and disease.
- Credited Claude AI's contribution in the patcher and in the repository
  description.

### Documentation

- Corrected the save-location claim. The docs said each modded build used its
  own "- Modded save location", which reads as a separate folder. It does not:
  both games build the path as `Documents\LDW\<game name>\<exe name><slot>.ldw`,
  where the folder is the game's own fixed name and only the file names come
  from the executable, through the `%s%d.ldw` format string in each build. A
  modded copy writes its files beside the original ones in the same folder.
- Documented that slot 0 is the settings file rather than a save, and that it
  follows the executable name too, so a modded copy starts with fresh settings
  instead of inheriting the original game's.
- Documented that renaming a modded executable changes which .ldw files it
  reads, so its saves appear to vanish until it is named back.


## v1.0.11

Golden Seahorse repurchase now works. It had four defects, not one.

- It targeted store item index 18, which is the Diver Ornament. The Golden
  Seahorse is index 11. Counting the 24-byte store name records from VA
  0x004578B4 gives 26 items, matching the `cmp edi, 0x19` bound on both store
  switches, with indices 0-7 the eight consumables the slots feature targets.
- The store-selection redirect resolved to VA 0x43F7FF, one byte before its
  wrapper at 0x43F800, landing on padding. Both it and the wrapper's internal
  branches are rebuilt against the correct addresses.
- The purchase-side hook at VA 0x004281BE was on the switch arm for the three
  research items, which the seahorse never reaches, and its wrapper ran off its
  own end into padding, crashing the game on any research item. Both patches
  are removed; those items are byte-identical to vanilla again.
- The section VirtualSize overlap was fixed in v1.0.9.

The setting now skips the single ownership gate at VA 0x004282B0 for item 11
only, and leaves every other item on its original path. It stays off by
default, as before. The three-setting build without it is byte-identical to the
output recorded in QA.md for v1.0.3.

Fish manifest is v1.2.6; every pinned hash and PE checksum regenerated.

Every other patch was audited the same way and all of them check out:

- Crimson Comet: the wrapper's `setb al` leaves the upper bytes of EAX zero
  because the roll is under 100, so the caller's `test eax, eax` reads it
  correctly. 20 percent confirmed.
- Unknown Chemical: the NOPped store is standalone, and EAX is reloaded before
  its next use, so removing it disturbs no register flow.
- Universal slots: every branch inside the 961-byte payload lands on an
  instruction boundary of the payload, and all 14 addresses it branches out to
  are genuine instruction boundaries in the original code.
- Plant old-age deaths: `jg` is a signed compare and the operand sign-extends,
  so 0xFF really is -1 and every roll 0-999 skips the branch.

Also fixed: output folders are now recognized by manifest family rather than by
exact id, so revising the manifest no longer makes the patcher refuse to
replace a folder an earlier release created. That break shipped in v1.0.10.


## v1.0.10

- Every patch now carries an accurate technical note: the address it changes,
  the instruction or string before and after, and why. The notes are written
  into the patch log beside each change, so a run records what it did and not
  just which bytes moved.
- Rewrote the setting descriptions the patcher shows, so each one states what
  it repairs, how, and how many places it touches.
- Documented three defects in the Golden Seahorse repurchase setting, two of
  them still unfixed, in docs/golden-seahorse-defects.md. The setting is
  labelled as non-working in the patcher and stays off by default.
- Removed the install-location scanning added in v1.0.7. Finding games is back
  to choosing the parent folder that holds them, the way the Virtual Villagers
  patcher does it: Find Both in Parent Folder, or one button per game.
- The release ZIP now contains docs/golden-seahorse-defects.md, which the
  README and several patch notes link to, and tests check that every document
  referenced from the README or a patch note is actually packaged.


## v1.0.9

Fixes Fish Tycoon builds that Windows refused to start with "This app can't
run on your PC".

- The two Golden Seahorse patches set the `.text` section's VirtualSize to
  0x40000, the section's raw end offset, rather than a size. That pushed
  `.text` to RVA 0x41000, past `.rdata` at 0x40000, and the Windows loader
  rejects an image whose sections overlap. Corrected to 0x3F000, the value the
  slots patch already used and the largest that clears `.rdata`.
- Every combination that enabled Golden Seahorse was affected: 8 of the 16.
  Combinations without it were unaffected, and Plant Tycoon was never
  affected.
- No PE checksum patch covered the Golden Seahorse combinations, so those
  builds kept a checksum computed for different bytes. There is now exactly one
  checksum patch per combination, each recomputed.
- Recorded the target's PE section layout in the manifest, and added tests that
  walk every setting combination to check no section overruns the next one and
  that each combination has exactly one checksum patch. These run offline and
  need no copy of the game.
- Regenerated every pinned output hash. Fish manifest is now v1.2.5.

## v1.0.8

- Autodetect no longer searches Steam or GOG library folders. Only the free
  Windows downloads from LDW's own site are supported, and no other
  distribution has been checked against the pinned executable identities.
- Documented that supported rule in the README and How to Use, replacing the
  v1.0.7 wording that listed storefront paths among the searched locations and
  so implied those copies would work.
- Noted that autodetect only fills in a path, and that whatever it finds still
  has to pass the exact identity check.
- An unsupported executable is now refused with the supported download source
  instead of a bare size or hash mismatch, so a copy from elsewhere — wherever
  it was found — says what to do about it.

## v1.0.7

- Added an `Autodetect Games` button that searches the usual Windows install
  locations for the exact `Fish Tycoon.exe` and `Plant Tycoon.exe` and fills in
  the vanilla and modded folder fields for whatever it finds.
- Added a `Scan a Folder...` button that runs the same search, deeper, in one
  folder or drive you choose.
- The search skips Windows system folders and any existing `- Modded` folder,
  runs on a background thread with live progress, and stops at a folder and
  time budget so a slow or cloud-synced location cannot hang the patcher.
- When one game is found in more than one place, the patcher asks which install
  to use instead of guessing.
- Added `Defaults`, `Enable All`, and `Disable All` buttons to each game's
  patch list.
- Moved the per-game `Find [Game]...` buttons up beside the new autodetect
  controls, so they work on both tabs, and every action button is now locked
  while a scan, patch, or restore is running.
- The window body now scrolls, so nothing is squeezed on a shorter screen.
- The search revisits a folder reached again from a nearer root, so a game in
  the default Steam library is still found after its Program Files ancestor was
  walked first.
- README: documented the requirements, the game search, the output-folder
  naming under its own heading, and how to run the tests.

## v1.0.5

- Added separate `Find Fish Tycoon in Parent Folder...` and
  `Find Plant Tycoon in Parent Folder...` buttons to the Both Games tab,
  alongside the existing combined finder.
- The finder accepts one exact vanilla executable in the selected folder or
  one of its immediate subfolders and refuses missing or ambiguous matches.

## v1.0.4

- Renamed generated game folders to exactly `Fish Tycoon - Modded` and
  `Plant Tycoon - Modded`.
- Renamed generated executables to exactly `Fish Tycoon - Modded.exe` and
  `Plant Tycoon - Modded.exe` so each modified game uses its matching isolated
  save location.
- Added a remembered GUI option for choosing the parent location where the
  modified game folders are created.
- Removed the vanilla executable filename from each generated modded folder.

## v1.0.3

- Replaced both picture assets with the final transparent PNGs supplied by
  Lorsieab2.
- Added emoji-sized plant and fish pictures around the creator sentence.
- Surrounded the main patcher title with the plant and fish pictures.
- Added a paired plant-and-fish application icon to the native window title
  bar.

## v1.0.2

- Replaced the text emoji banner with the two exact fish and potted-plant
  pictures supplied by Lorsieab2.
- Removed the pictures' dark square backgrounds and preserved transparent PNG
  assets in the GUI and release package.

## v1.0.1

- Added the requested `🐟🪴` picture-style emoji banner.
- Added the exact creator description:
  `🪴 Created with Codex AI. Made with love by Lorsieab2 :) 🐟`

## v1.0.0

- Combined the current Fish Tycoon Fix Patcher v1.2.4 and Plant Tycoon Fix
  Patcher v1.0.0 engines and manifests.
- Added One Game and Both Games workflows modeled on the Virtual Villagers Fun
  Patcher.
- Added remembered, auto-filled vanilla/modded paths and clickable folder
  links.
- Preserved exact-build validation, guarded patches, pinned hashes, backups,
  restore, full-folder copying, readback verification, and original icon
  resources.
## v1.0.7

- Added an opt-in Golden Seahorse repurchase setting targeting store item
  index 18 and its two already-owned purchase gates.
