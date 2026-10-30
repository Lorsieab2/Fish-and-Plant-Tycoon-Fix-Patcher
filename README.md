# Fish & Plant Tycoon Fix Patcher

<img src="assets/fish.png" alt="Fish" width="96"> <img src="assets/plant.png" alt="Potted plant" width="96">

🪴 Created with Codex AI, with contributions from Claude AI. Made with love by Lorsieab2 :) 🐟

An offline Windows patcher combining the current Fish Tycoon Fix Patcher and
Plant Tycoon Fix Patcher in the same player-facing format as the Virtual
Villagers Fun Patcher.

Current release: **v1.0.17**. See [CHANGELOG.md](CHANGELOG.md) for what each
version changed.

## Supported copies

Only the free Windows downloads from LDW's own site, <https://ldw.com>, are
supported. Every LDW PC game is free there, so there is no reason to source the
games anywhere else. Each engine is pinned to one exact executable identity, and
builds from any other distribution have not been checked against those pins, so
the patcher will refuse them rather than guess.

## Requirements

Windows, and Python 3 with Tkinter (the standard python.org installer includes
it). The launcher uses `py -3` when the Python launcher is present and falls
back to `python`. Nothing else is installed or downloaded, and the patcher
never needs the internet.

## Included fixes

### Fish Tycoon

- Fix Vanilla Bugs (on by default): the Plant of Incubation and Plant of
  Nutrition do what their names say (the game had their effects swapped).
  The Golden Seahorse arrives with full health and food (100 and 100; the
  game gave it health 80-94 and food 50), and a seahorse already in a save is
  filled up the first time the save is loaded with the patch. The game never
  lowers its meters, so it stays full.
- Crimson Comet 20% curing fix.
- Unknown Chemical: 3 uses.
- Universal supply slots 2-4 for the eight supported medicine, chemical, and
  egg types.
- Buy Multiple Golden Seahorses. Allows purchasing of multiple Golden
  Seahorses, in case you trash or lose it somehow. It shipped broken from
  v1.0.6 and was fixed in v1.0.12; see
  [docs/golden-seahorse-defects.md](docs/golden-seahorse-defects.md).
- Bigger tanks: 30 fish (off by default; **EXPERIMENTAL - USE AT OWN RISK**). Tank 1, Tank 2 and the Sale Tank
  (Tank 3) hold 30 fish instead of 21 (the isolation tank still holds one;
  with 3 extra tanks, Tanks 4-6 hold 30 too), and
  fish 22-30 get everything fish 1-21 get. Every adult in the Sale Tank is
  for sale with the stock odds per fish, one sale a second at most as in the
  stock game; the crowd counts at most 21 adults, the stock game's most. The
  game's save already has room for them, so saves keep their layout. Sell or
  move fish down to 21 per tank before turning it off again. Design:
  [docs/fish-tycoon-tank-expansion.md](docs/fish-tycoon-tank-expansion.md).
- 3 extra tanks (off by default; **EXPERIMENTAL - USE AT OWN RISK**; **needs
  DS Store Items, which it turns on**). Tank 4, Tank 5 and Tank 6:
  three more full tanks for breeding, exactly like Tank 1 and Tank 2. Buy
  them on the Supplies store's Upgrades screen: the Extra Tank item (the
  game's own Second Tank picture), $10,000 each ($0 with Free upgrades), opens
  the next tank each time, Tank 4 first. Until then a tank's button is
  greyed out and says "You don't own this tank yet!". Tank 4 looks like
  Tank 1, Tank 5 like Tank 2 and Tank 6 like the Sale Tank, without
  its For Sale sign. Fish live, age, eat, get sick, breed and give birth
  there; food, medicines, chemicals, eggs, ornaments, research, the plants,
  the magic fish, the Golden Seahorse, the DS store animals and Bigger tanks
  all work as in a stock tank, because the game's own code runs them. Two
  small arrows left of the Tank 1 button switch the tank buttons to the
  three new tanks and back. Drag a fish, a DS store animal or an ornament
  onto a button to move it to that tank, or onto an arrow to move it to the
  previous or next tank (Tank 1, Tank 2, the Sale Tank, then the extra
  tanks you own, and round again); a full tank refuses it as in the stock
  game. Each extra tank has a "For sale" button (Off at first): On, it shows
  the Sale Tank's For Sale! sign and its fish sell together with the Sale
  Tank's, by the game's own sale code (one sale a second, the same prices,
  odds and effects; the sale scene's pictures and "Fish for sale" number count
  every selling tank; the crowd never passes the stock maximum). Every tank
  screen shows its name (Tank 1, Tank 2, Tank 3 (the Sale Tank), Tank 4, Tank 5, Tank 6).
  Mockups: [docs/images/extra-tank-4-selling-on.png](docs/images/extra-tank-4-selling-on.png)
  and the other `extra-tank-*` pictures and the Sale Tank beside Tank 6: [docs/images/tank-3-sale-vs-tank-6-for-sale-on.png](docs/images/tank-3-sale-vs-tank-6-for-sale-on.png). It runs as a companion DLL the game loads at start
  (`Fish Tycoon Fix Patcher DLLs\Extra Tanks.dll`), in the "Modded Upgrades"
  copy; the saves keep their stock layout and each save slot keeps its extra
  tanks, with their DS store animals and For sale buttons, and how many are
  bought, in `Fish Tycoon Fix Patcher Data\Extra
  Tanks <slot>.dat` beside the saves; a new game starts with none. Empty the
  three tanks before turning it off again. Design and the emulated checks:
  [docs/fish-tycoon-extra-tanks-design.md](docs/fish-tycoon-extra-tanks-design.md).
  Pictures: [docs/images/extra-tanks-extra-page.png](docs/images/extra-tanks-extra-page.png).
- Maximizable window (on by default). In windowed mode the window's Maximize
  button works, and its edges can be dragged to resize it. At any size other
  than the game's own, the picture is scaled to fill the window, keeping its
  shape, with black bars where it does not fit, and smoothed (on a very large
  window where smoothing would slow the game, nearest pixel instead); the
  mouse lands where you point. Restored, the window is its normal size and
  drawn exactly as before; fullscreen is unchanged. It runs as a companion
  DLL the game loads at start
  (`Fish Tycoon Fix Patcher DLLs\Maximizable Window.dll`), in the plain
  "Fish Tycoon - Modded" copy; nothing is saved. How it works, with every
  address: `native/ftfp_fish_window/ftfp_fish_window.c`. Plant Tycoon draws
  through SDL2, a different renderer, so this setting is Fish Tycoon's only.
- Optimize Prices button (on by default). An "Optimize Prices" button on the
  Species Chart's bottom bar, left of Done (where you set prices). It asks
  "Set every discovered species to its best price per day?"; on Yes, every
  species you have discovered gets the Breeding Guide's "best per day"
  asking price (the price that earns the most money over time), worked out
  in the game with the guide's own maths for your shop as it is now: each
  species' base price (with the Advertising rises), the ornaments you own,
  the Golden Seahorse and your Advertising level, with a full selling tank.
  Then it says "N prices set." Undiscovered
  species keep their prices and nothing else changes; the prices are the
  ones you would type yourself, saved with the game as usual. The DS species
  are included with DS Exclusive Fish. It runs as a companion DLL
  (`Fish Tycoon Fix Patcher DLLs\Optimize Prices.dll`) in the plain
  "Fish Tycoon - Modded" copy. Picture:
  [docs/images/optimize-prices-fish.png](docs/images/optimize-prices-fish.png).
- Tank and greenhouse counts (on by default). Lines in the game's own font
  at the top left of the water on the tank screen, for the tank you are
  looking at, Tanks 4-6 too with 3 extra tanks: "Fish: 12 of 21 (8 adults,
  3 teens, 1 baby)" (of 30 with Bigger tanks), "Sick: 2 fungus, 1 ick  Low
  Health: 3" when live fish are sick (the game's own names for its two
  sicknesses) or have Low Health (health 25 or less: exactly when the game
  draws their health bar red; the game has no word for it; German "Niedrige
  Gesundheit"), "Creatures: Golden Seahorse, Moray Eel" when it has any, and
  "Isolation tank: 1 of 1 (1 adult)" (with "Sick: ..." when it is). With 3
  extra tanks the lines sit lower, under the tank's name and For sale button.
  A "Counts: On" / "Counts: Off" button at the top right of the water hides or
  shows them; hidden, only the button stays. The choice is kept in
  `Fish Tycoon Fix Patcher DLLs\Tank Counts.ini`, never in a save, and the
  button takes only its own clicks (never while you drag a fish).
  The stages are the game's own: a baby
  is age 1-5, a teen 6-19, an adult 20 and up (the ages at which the game
  switches the fish's picture). Dead fish are left out of the count and shown
  after it as "Dead: 2" until you throw them away; they, and a Golden
  Seahorse the stock game put in a fish slot, still take a place in the tank.
  The creatures are the Golden Seahorse and DS Store Items' animals (the
  Moray Eel in its rock too). In German the game's own German words are used.
  The counts update every frame and are drawn just after the tank's
  background, so fish, ornaments and buttons are drawn over them and nothing
  is covered; display only, nothing in the game or the saves changes. It runs
  as a companion DLL the game loads at start
  (`Fish Tycoon Fix Patcher DLLs\Tank Counts.dll`, which also loads DS
  Exclusive Fish's or the Maximizable window's DLL when those are on), in the
  plain "Fish Tycoon - Modded" copy. How it works, with every address:
  `native/ftfp_tank_counts/ftfp_tank_counts.c`. Pictures:
  [docs/images/tank-counts-fish.png](docs/images/tank-counts-fish.png),
  [docs/images/tank-counts-fish-off.png](docs/images/tank-counts-fish-off.png).
- DS Exclusive Fish (off by default). Adds the Nintendo DS version's seven
  extra bodies (Clownfish, Discus, Bicolor, Trigger, Surgeonfish, Tang, Idle)
  and seven extra fins (Small Fin, Roundy, Angel, Clown, Yellow, Blue,
  Moorish): 343 new species. Eggs, the store and two PC parents never give
  them. The Unknown Chemical, and the Magic Fish of Mutation at hatching, can
  step a Spotanus body or Twin-Fin fin one place further into them, with the
  same odds as before. Breeding a DS fish, prices, rarity, names and fin
  placement follow the DS game. It runs as a companion DLL the game loads at
  start (`Fish Tycoon Fix Patcher DLLs\DS Exclusive Fish.dll`), its sprites go
  in `Images`, and each save slot keeps its DS species data in
  `Fish Tycoon Fix Patcher Data\DS Fish <slot>.dat` beside the saves; the
  save files themselves keep their stock layout. How to get each one:
  [docs/fish-tycoon-ds-fish-testing-guide.md](docs/fish-tycoon-ds-fish-testing-guide.md);
  every address it uses:
  [docs/fish-tycoon-ds-fish-technical-map.md](docs/fish-tycoon-ds-fish-technical-map.md).
  Sell or trash every DS fish before turning it off again.
- DS Store Items (off by default; needs DS Exclusive Fish, which it turns on
  with it). An Upgrades button in the Supplies store opens the DS version's
  store items. The Puffer Fish, Sting Ray and Moray Eel ($1250 each) are tank
  companions like the Golden Seahorse: they swim, can be dragged between
  tanks, never age, breed or get sold, and magically enhance the life and
  environment of your fish (the Tools tab's Game Mechanics lists the exact
  effects). The Moray Eel comes with its rock: drop the eel on it to send it
  home, move the rock and the eel goes with it, and drag it out by its head.
  Trashing the eel trashes its rock, and the other way round. The animals,
  the Golden Seahorse included, never take a fish's place: each tank has 5
  animal slots of its own, kept in `Fish Tycoon Fix Patcher Data\Tank Animals
  <slot>.dat` beside the saves (with 3 extra tanks, the animals in Tanks 4-6
  move with their tank and are kept in its `Extra Tanks <slot>.dat`). Without
  Buy Multiple Golden Seahorses each animal is one of each, counting every
  tank, Tanks 4-6 included. The store animals arrive with full health and
  food (100 and 100), and ones already in a save (the eel in its rock too)
  are filled up the first time the save is loaded with the patch; nothing in
  the game lowers their meters. Exotic Fish Eggs ($2300) hatch only the DS-exclusive bodies and fins.
  The Radioactive Growth Hormone ($10,000, 3 doses; $0 with Free upgrades) is
  the stock Growth Hormone recoloured green, bought into supply slot #3 and
  used on a tank like the stock chemicals (Universal supply slots apply). Each
  dose reaches every fish in the tank on screen, any age, fry included (the
  stock Growth Hormone stops at 40 and stays stock): every pregnant one gives
  birth at once, through the game's own birth rules (the same litter, Magic
  Fish mutation, Plant of Fertility and "no room" as a natural birth); then
  younger ones, the newborns too, become adults (age 20), and every one gets
  full health (100) and is cured of ick or fungus. Other tanks and the store
  animals are left alone. Picture:
  [docs/images/radioactive-growth-hormone-fish.png](docs/images/radioactive-growth-hormone-fish.png).
  The Revival Potion ($10,000, 3 doses; $0 with Free upgrades), the owner's
  amber flask, is a slot-#3 chemical like the hormone: each dose revives every
  dead fish in the tank on screen at full health; its age, food, sickness and
  pregnancy stay as they were, and the time it lay dead is not played as time
  away. Dead fish stay in the tank until you throw them away (the game never
  removes them), so every dead fish still there can be revived. ClonaFish
  ($2,500, 3 doses; $0 with Free upgrades), the owner's magenta bottle: each
  dose adds one exact copy of every unique fish in the tank on screen (a live
  fish no other live fish there shares both its body and its fin with), in
  slot order, through the game's own add-fish code, until the tank is full;
  if there was no room for even one, the game's "The tank is full!" shows.
  Both work in every tank slot the game uses (Bigger tanks, and more) and in
  every tank the game updates. Picture:
  [docs/images/revival-potion-fish.png](docs/images/revival-potion-fish.png).
  The Golden Seahorse keeps its PC effects and gains its DS one. It runs as a
  second companion DLL (`Fish Tycoon Fix Patcher DLLs\DS Store Items.dll`),
  loaded by DS Fish's; besides the game's own save it writes only the
  animals' `Tank Animals <slot>.dat`.
  Design and live checks:
  [docs/fish-tycoon-ds-store-items-design.md](docs/fish-tycoon-ds-store-items-design.md).
  Trash the store animals, and let the eel out of its rock, before turning it
  off again.
- Time Warp (off by default; turns on the store's Upgrades screen it lives on).
  A clock item on the Upgrades screen: pay a flat $500, type 1-72 real-time
  hours in a small Windows popup, confirm Yes, and the game plays those hours as
  if you had been away, with no catch-up cap. At Normal speed 1 hour is 6 age
  steps/units; at 2x (Fish) 12 and Fast (Plant) 30; at 1/2 speed / Slow 4.
  Refused while time is stopped. Once the hours have been played, an OK box says
  so: "Time Warp done: 12 hours played (72 age steps). $500 paid." ($0 paid with Free upgrades).
- Free upgrades (off by default; **needs DS Store Items, which it turns on**).
  Every item on the Supplies store's Upgrades screen costs $0: the Puffer Fish,
  Sting Ray and Moray Eel ($1250 each), Exotic Fish Eggs ($2300), the
  Radioactive Growth Hormone ($10,000), the Revival Potion ($10,000),
  ClonaFish ($2,500), and the Time Warp clock ($500), Add Money ($950) and
  the Extra Tank ($10,000 each) when they are on. The price shows $0 and no
  money is taken; everything else (one of each animal, the supply slots,
  Tanks 4-6 bought in order, the game's purchase question) stays. The game's own store items keep their
  prices.
- Add Money cheat ($1,000) (off by default; **needs DS Store Items, which it
  turns on**). A pile of gold coins on the Upgrades screen, next to the Time
  Warp clock: $950 ($0 with Free upgrades), bought like the other items, adds
  $1,000 to your money, as often as you like. Money stops at the largest
  value the game holds ($2,147,483,647). Picture:
  [docs/images/add-money-fish.png](docs/images/add-money-fish.png).
- Multiple ornaments (off by default; **EXPERIMENTAL - USE AT OWN RISK**). The Shell, Pagoda, Diver, Fancy Coral,
  Sunken Antique Column and Sunken Ship can be bought again once you own
  them, at their normal price, up to 10 extra copies per tank. The copies are
  only for decorating: they are drawn, fall, and are dragged, placed and
  moved to another tank's button by the game's own ornament code, exactly
  like the original, and the trash can takes them (never the original). The
  ornament's effect comes from owning it, once, game-wide, as in the stock
  game: copies never add to it, and throwing copies away never removes it.
  The copies are kept beside each save slot in `Fish Tycoon Fix Patcher
  Data\Ornaments <slot>.dat`; the save itself is unchanged. It runs as a
  companion DLL (`Fish Tycoon Fix Patcher DLLs\Multiple Ornaments.dll`), the
  first one the game loads. Picture:
  [docs/images/multiple-ornaments-tank.png](docs/images/multiple-ornaments-tank.png).
  Trash the extra copies before turning it off again (with it off they are
  not shown; they come back if you turn it on).

### Plant Tycoon

- Fix Vanilla Bugs (on by default): a new game no longer starts with every
  plant at the Flower of Knowledge (Nox Orchid) price when the save open
  before it had found the Nox Orchid (the game had priced the new game before
  forgetting the old one's magic plants). Existing saves with Nox prices but
  no Nox Orchid are re-priced the first time they load: if the save has not
  found the Flower of Knowledge and every species it has not discovered is at
  that price, those species get normal prices, the 322 Unused Flowers too.
  Discovered species keep their prices (you may have set them), and a save
  with any other undiscovered price is left alone.
- No old-age plant deaths. The original age check and `Random(1000)` call remain;
  the eligible death range is empty.
- R refreshes the seed shop (on by default). Pressing R (or r) in the Supplies
  store restocks all nine seed packets at once with the game's own restock roll,
  so the odds are the stock ones; with Add new store upgrades and items the
  Legendary Seeds are rerolled too. R does nothing on other screens, the daily
  restock keeps its time, and nothing extra is saved. Three byte changes, each
  checked against the vanilla bytes.
- Add Missing Assets to LDW Version (on by default, new in v1.0.15). Adds
  files the LDW download is missing, using the Steam version's files. The merge
  is only additive: a file is copied into the modded folder only where the game
  lacks it, a game file is never replaced, and a bundled file identical to the
  game's own is ignored. Turn it off and patch again to get a folder without
  them. Against the supported LDW build it adds 15 sounds (birds, bell, bug
  sounds, butterfly, cricket loop, cross-breeding chimes and harp, gentle
  fountain, insect buzz, medical drip, wind in the trees and windchimes); 294
  bundled files are identical to the game's own and are ignored, and 7 that
  differ are left at the game's version.
- Add unused flowers (off by default). Fourteen flower heads ship in the game's art
  but no plant uses them; this adds them as new flowers: Nightingale, Rosetta,
  Lilac, Veronica, Violetta, Stella, Silvermist, Anagallis, Buttercup,
  Cerulean, Phalaena, Mirabilis, Indigoberry and Prunus. With the 23 foliages
  that is 322 new species, all in the rarest class. Flower names: credit to
  Virtual_Lady and Lorsieab2.
  - Mutation Liquid can step a Tilia flower one place further, into the new
    ones, with the same odds.
  - Breeding mixes them by the game's own rule.
  - Mirabilis is recoloured golden so it isn't confused with Jalapa.
  - It runs as a companion DLL the game loads at start
    (`Plant Tycoon Fix Patcher DLLs\Unused Flowers.dll`). Each save slot
    keeps the new species' prices and discoveries in
    `Plant Tycoon Fix Patcher Data\New Flowers <slot>.dat` beside the saves.
  - Design:
    [docs/plant-tycoon-new-flowers-design.md](docs/plant-tycoon-new-flowers-design.md).
    Sell or compost the new flowers before turning it off again.
- Add new store upgrades and items (off by default; needs Add unused
  flowers). An Upgrades link on the bricks at the left of the Supplies store
  opens a second view of the store with only the new items, each where it
  would sit in the stock store:
  - Legendary Seeds on the seed shelves: three a day, $5000 each, any foliage
    with one of the new flowers (the stock packets keep their stock flowers).
  - Radioactive Plant Formula with the chemicals: $10,000, 3 doses; far
    beyond spamming Fertilizer Bombs and Plant Food: every branch grows (dead
    ones and the ones the plant's shape normally hides), the largest size,
    full bloom, a flower on every spot of every branch and leaf (hundreds on a
    big plant), no dead or brown leaves, full health, and 5 seeds when
    pollinated.
  - Radioactive Plant Formula Bomb under the formula: $30,000, 3 bombs; the
    stock Fertilizer Bomb made rainbow. One bomb gives every live plant in the
    greenhouse on screen exactly one Radioactive Plant Formula dose (the
    plants the Fertilizer Bomb reaches, in whichever greenhouse is shown).
  - Revival Potion beside the formula: $10,000, 3 doses, the owner's amber
    flask. Dropped on a dead plant, it comes back to life at full health; the
    parts that were already dead before it died stay dead (prune them or use
    the formula), and the seeds it lost when it died stay lost.
  - Revita-Seed beside that: $2,500, 3 doses, the owner's teal bottle.
    Dropped on a plant that has given all its seeds, it can be pollinated
    again and give seeds again, exactly like a fresh plant.
  - Picture: [docs/images/revival-potion-plant.png](docs/images/revival-potion-plant.png).
  - The Fourth, Fifth and Sixth Seed Box with the tool upgrades: $1000
    each, bought in order like the stock ones. Each opens a 40-seed drawer in
    a second chest; the gold arrows on the Seed Storage title bar switch
    between boxes 1-3 and 4-6, and the greenhouse fills boxes 4-6 once 1-3
    are full.
  - Click Supplies in the bottom bar to go back.
  - Design:
    [docs/plant-tycoon-upgrades-design.md](docs/plant-tycoon-upgrades-design.md).
- Time Warp (off by default; turns on the store's Upgrades screen it lives on).
  A clock item on the Upgrades screen: pay a flat $500, type 1-72 real-time
  hours in a small Windows popup, confirm Yes, and the game plays those hours as
  if you had been away, with no catch-up cap. At Normal speed 1 hour is 6 age
  steps/units; at 2x (Fish) 12 and Fast (Plant) 30; at 1/2 speed / Slow 4.
  Refused while time is stopped. Once the hours have been played, an OK box says
  so: "Time Warp done: 12 hours played (72 age units). $500 paid." ($0 paid with Free upgrades).
- Free upgrades (off by default; **needs Add new store upgrades and items,
  which it turns on**). Every item on the Supplies store's Upgrades view costs
  $0: Legendary Seeds ($5000), the Radioactive Plant Formula ($10,000), the
  Formula Bomb ($30,000), the Revival Potion ($10,000), Revita-Seed ($2,500), the
  Fourth, Fifth and Sixth Seed Box ($1000 each), and the Time Warp clock ($500),
  Add Money ($950), the Extra Greenhouse ($10,000 each) and the Extra Nursery
  ($10,000 each) when they are on. The price shows $0 and no money is
  taken; everything else (three Legendary Seeds a day, room in the trays, the
  boxes, greenhouses and nurseries in order) stays. The game's own store items keep their prices.
- Add Money cheat ($1,000) (off by default; **needs Add new store upgrades and
  items, which it turns on**). A pile of gold coins on the Upgrades view's
  Nursery shelf, next to the Time Warp clock: $950 ($0 with Free upgrades),
  asked Yes/No, adds $1,000 to your money through the game's own cash code, as
  often as you like. Cash stops at the game's own maximum, $4,000,000,000.
  Picture: [docs/images/add-money-plant.png](docs/images/add-money-plant.png).
- Sort Seeds button (off by default). A "Sort Seeds" button on the Seed
  Storage title bar. After a Yes/No question it sorts every seed in the
  unlocked seed box space by the class of the plant it grows, its foliage and
  flower, then its parents (unknown first), and packs them from the first
  slot: boxes 1-3 fill before 4-6, and locked drawers stay empty. It checks
  that exactly the same seeds come out as went in before writing anything.
- Optimize Prices button (on by default). An "Optimize Prices" button on the
  Nursery's bottom bar, at the right. It asks "Set every discovered species
  to its best price per day?"; on Yes, every species you have discovered gets
  the Breeding Guide's "best per day" asking price (the price that earns the
  most money over time), worked out in the game with the guide's own maths
  for your nursery as it is now: each species' value, the Golden Berries of
  Wealth, and the visitors your ornaments, magic plants and bug collection
  bring with all 15 sale spots filled, for a healthy, flowering plant without
  Plant Food or pruning. Then it says "N prices set." Undiscovered species
  keep their prices and nothing else changes; the prices are the ones the
  "Set species price" box would write, saved with the game as usual. The 322
  Unused Flowers species are included when that setting is on. It runs as a
  companion DLL (`Plant Tycoon Fix Patcher DLLs\Optimize Prices.dll`) in the
  plain "Plant Tycoon - Modded" copy. Picture:
  [docs/images/optimize-prices-plant.png](docs/images/optimize-prices-plant.png).
- Tank and greenhouse counts (on by default). A line in the game's own font
  along the top of the greenhouse screen: "Plants: 9 of 15 (5 mature, 2 with
  buds, 2 seedlings)", counting the pots of the greenhouse on screen
  (Greenhouses 2-6 too, with 5 extra greenhouses) that hold a living plant,
  and under it "Infested: 2  Unhealthy: 1" when any living plant is (the
  status panel's own words: the game has one pest, the small black insects,
  and calls a plant Unhealthy below health 30). A "Counts: On" / "Counts:
  Off" button at the top right hides or shows them, kept in
  `Plant Tycoon Fix Patcher DLLs\Greenhouse Counts.ini`, never in a save; it
  takes only its own clicks (never while you hold a seed or tool). Once you
  own an extra greenhouse the lines sit under the gold arrows and the button
  moves left of the right arrow, above the greenhouse's name. The stages
  are the selected plant's own countdown: a seedling before age 21 ("Buds in
  ... Min."), with buds from 21 ("Mature in ... Min."), mature from 24. Dead
  plants are left out of the count and shown after it as "Dead: 1" until you
  trash them. The line updates every frame and is drawn just after the
  greenhouse's background, so plants, pots, tools and buttons are drawn over
  it; display only, nothing in the game or the saves changes. It runs as a
  companion DLL the game loads at start
  (`Plant Tycoon Fix Patcher DLLs\Greenhouse Counts.dll`, which also loads
  Unused Flowers' or Sort Seeds' DLL when those are on). How it works:
  `native/ftfp_greenhouse_counts/ftfp_greenhouse_counts.c`. Pictures:
  [docs/images/greenhouse-counts-plant.png](docs/images/greenhouse-counts-plant.png),
  [docs/images/greenhouse-counts-plant-off.png](docs/images/greenhouse-counts-plant-off.png).
- 5 extra greenhouses (**EXPERIMENTAL - USE AT OWN RISK**; off by default;
  **needs Add new store upgrades and items, which it turns on**; in the
  "Modded Upgrades" copy). Every greenhouse screen is named at the top in the
  game's font ("Greenhouse 1" is the stock one). Up to six
  greenhouses of 15 pots, 90 pots in all. An Extra Greenhouse item on the
  store's Upgrades screen (the tool shelf, beside the Fourth to Sixth Seed Box,
  pictured with the game's own greenhouse) sells Greenhouses 2-6 in order,
  $10,000 each ($0 with Free upgrades), and gets a tick once all five are
  yours; a new game starts with none. Once you own one, the game's own gold
  arrows (as on the Seed Storage screen) at the top of the greenhouse screen
  page through Greenhouse 1, the stock one, and the ones you own, and the
  screen says "Greenhouse 2 of 3". Greenhouses you have not bought cannot be
  reached, and no plant can be moved into them. Each greenhouse is the stock screen with the
  game's own code running on its pots: plants grow, need water and care,
  flower, take pollen, give seeds, get pests and die exactly as in Greenhouse
  1, also while you look at another greenhouse, while you are away and through
  the Time Warp, and every chemical, tool, upgrade and magic plant works in
  each. Drag a plant onto an arrow to move it to the same pot place in the
  greenhouse that arrow leads to (or its first empty pot if that place is
  taken); pollen and seeds taken from a plant are carried across, and held
  tools, chemicals and tray seeds stay in your hand. The nursery
  shows the plants for sale from every greenhouse in its stock 15 spots, and
  without 5 extra nurseries at most 15 plants can be for sale at once.
  Greenhouses 2-6 are kept per slot in
  "Plant Tycoon Fix Patcher Data\Extra Greenhouses <slot>.dat" beside the
  saves (the save itself keeps its stock layout). **Empty Greenhouses 2-6
  before switching it off.**
  - Pictures: [docs/images/extra-greenhouses-switch.png](docs/images/extra-greenhouses-switch.png),
    [docs/images/extra-greenhouses-store.png](docs/images/extra-greenhouses-store.png).
  - Design:
    [docs/plant-tycoon-extra-greenhouses-design.md](docs/plant-tycoon-extra-greenhouses-design.md).
- 5 extra nurseries (**EXPERIMENTAL - USE AT OWN RISK**; off by default;
  **needs Add new store upgrades and items, which it turns on**; in the
  "Modded Upgrades" copy). Without any, the game's own limit holds: at most 15
  plants are for sale at once. An Extra Nursery item on the Upgrades screen's
  Nursery shelf (the game's own golden pot) sells Nurseries 2-6 in order,
  $10,000 each ($0 with Free upgrades); each one bought adds 15 spots (90 with
  all five). Each nursery is the stock nursery screen, run by the game's own
  code, with its own 15 spots. While you are in the nursery, every nursery
  you own sells at once through the game's own buy roll (only the one on
  screen has visitors walking about; away from the nursery nothing sells, as
  in the stock game). Every nursery screen is named at
  the top ("Nursery 1" is the stock one), and gold arrows there page through
  the ones you own. Plants are tagged for sale in the greenhouse as in the
  stock game and fill the nurseries in order: Nursery 1 first (a Greenhouse 1
  plant at its own pot's spot), then Nursery 2, and so on. The nurseries
  bought are kept with the extra greenhouses in "Extra Greenhouses
  <slot>.dat". **Take plants off sale until 15 or fewer are for sale before
  switching it off.**
  - Pictures: Nursery 2 [docs/images/extra-nurseries-switch.png](docs/images/extra-nurseries-switch.png)
    beside the stock Nursery 1 [docs/images/extra-nurseries-nursery-1.png](docs/images/extra-nurseries-nursery-1.png).

## Use

1. Extract the release ZIP.
2. Double-click `Launch Fish and Plant Tycoon Fix Patcher.bat`.
3. Click **Find Both in Parent Folder...** and pick the folder your game
   folders sit in, or select each vanilla folder yourself.
4. Select **One Game** or **Both Games**.
5. Choose the fixes you want, using **Defaults**, **Enable All**, or
   **Disable All** if it is quicker.
6. Validate, dry run, or create the fixed copy/copies.

The GUI remembers separate vanilla and modded paths for both games. Every blue
underlined path is a direct File Explorer link to that folder.

### Finding your games

Point the patcher at the folder that holds your game folders and it fills in
the rest. **Find Both in Parent Folder...** looks for the exact
`Fish Tycoon.exe` and `Plant Tycoon.exe` in that folder and its immediate
subfolders, and fills in the vanilla and modded folder fields for both games.
**Find Fish Tycoon...** and **Find Plant Tycoon...** do the same for one game.
An exact match is required: a missing or ambiguous result is reported rather
than guessed at.

This only fills in a path. Whatever it finds still has to pass the exact
identity check below before anything is written.

### Where the modded copies go

Choose one parent location in the GUI. The patcher creates complete separate
output folders named `Fish Tycoon - Modded` and `Plant Tycoon - Modded`.
Their executables are named `Fish Tycoon - Modded.exe` and
`Plant Tycoon - Modded.exe`. Original folders and executables are not replaced.
With a setting that adds new content on (DS Exclusive Fish, DS Store Items,
Multiple ornaments, 3 extra tanks, Add unused flowers, Add new store upgrades and items), the copy is
`Fish Tycoon - Modded Upgrades` / `Plant Tycoon - Modded Upgrades` (folder and
EXE) instead, beside the plain copy; the game names its save folder after the
EXE, so it keeps its own saves.
The **One Game** tab also retains each original patcher's verified
restore-from-backup operation.

### Where your saves go

Both games build their save path as
`Documents\LDW\<exe name>\<game name><number>.ldw`. The folder comes from the
executable: the game reads its own file name with `GetModuleFileNameA` and drops
the path and `.exe`. The file names are the game's own fixed name, through the
`%s%d.ldw` format string each build carries.

So a modded copy gets a folder of its own, next to your original game's:

```
Documents\LDW\
    Fish Tycoon\               <- original game
        Fish Tycoon0.ldw        <- settings
        Fish Tycoon1.ldw ...    <- saves
    Fish Tycoon - Modded\      <- modded copy
        Fish Tycoon0.ldw        <- settings
        Fish Tycoon1.ldw ...    <- saves
```

The file names are the same in both folders, but the folders are separate, so
your original saves are never touched and the two builds cannot overwrite each
other. `Documents` is wherever Windows keeps it, which is often
`OneDrive\Documents`. Things that follow and are easy to be surprised by:

- File `0` holds settings rather than a save, and it lives in the per-executable
  folder too, so a modded copy starts with fresh settings instead of inheriting
  the ones from your original game.
- Renaming a modded executable changes which folder it uses. Rename it and its
  saves appear to vanish; they are still there in the folder named after the old
  executable.

## Tools

The **Tools** tab is laid out and works like the Virtual Villagers Fun
Patcher's: the tools for the game chosen on the One Game tab, then the same
tools for each game (Back up saves, Restore saves..., Rename players...,
Game mechanics..., Breeding guide...), and Back Up Saves (Both)... for both at once. Every tool
has a "?" guide. They work on the modded copies' save folders ("- Modded",
"- Modded Upgrades" and any other "<Game> - Modded..." folder; see "Where
your saves go"). Every file operation uses Windows' long-path form, so a deep
folder never fails with "path too long".

- **Backup and Restore Saves.** A backup is a copy of the save folder (the
  game's saves and the patcher's own per-player files) in a `Backups` folder
  inside it, named `Backup <date and time>`. Every copied file is read back
  and checked against the original's SHA-256 and keeps its times; a copy that
  fails is set aside as `INCOMPLETE` and never offered. If the game is
  running it is paused for the copy and resumed afterwards. Backups are
  listed newest first with the players they hold. A restore needs the game
  closed and puts back the whole folder, or one player slot (that player's
  save files, the patcher's files for that slot, and the slot's name in the
  player list); the saves as they are now are backed up first as
  `(before restore)`, so a restore can itself be undone. Zip backups made by
  v1.0.17 can be imported into the list.
- **Rename Player Slots.** Changes a player's name in the game's player list
  and inside that player's own save files, up to 31 plain characters as in the
  game, with the game closed. The save folder is backed up first, as
  `(before rename)`. A save file is changed only where
  it holds exactly the old name; anything else is left alone. The layouts are
  in `src/save_tools.py`.
- **Game Mechanics.** A read-only page, with a tab for each game, on how the
  games really work underneath, read from their code:
  - time away, health, food, sickness, pests, breeding, seeds, the store,
    research, selling, magic fish and plants, and bugs;
  - an index of every random roll and timer.

  Every chance is the game's own test with its exact odds (`Random(100) < 50`
  is 50.05%, not 50%). Each line is labelled VERIFIED-C, VERIFIED-E or
  UNCONFIRMED. A "With the patcher" line marks what one of this patcher's
  settings changes. It never touches a save, so the games can stay open. See
  [docs/game-mechanics-window.md](docs/game-mechanics-window.md).
- **Breeding Guide.** Spreadsheets of each game's breeding, for the save and
  player you pick (read only; nothing is ever written to a save):
  - a sheet per part (Fish Tycoon: Fins and Bodies; Plant Tycoon: Flowers and
    Foliage): how each is obtained, its rarity and the species that have it;
  - the species: the pairs of parts that breed each one, its base value, and
    two prices each with 0 effects and with Max effects: the best asking
    price per day and the highest price that still sells (no mutation changes
    a price);
  - a Breeding Calculator (two parents: every child and its exact odds) and
    the Breeding Planner (the shortest breeding chain from the species you
    have to the one you want), each with three effects choices: 0 effects,
    Max effects without the mutation, and Max effects with it (the Wasp
    Grouper in Fish Tycoon, Mutation Liquid in Plant Tycoon).

  Rarities use the games' own words: Common, Unusual and Rare in Fish Tycoon
  (as its Common and Unusual Fish Eggs), Common, Endangered and Extinct (the
  seed packets) in Plant Tycoon, Legendary for the Unused Flowers. Every
  "how it is obtained" quotes the exact odds from the game's code. A
  scrolling pane under each sheet shows the picked row's details.

  It opens on the species the save has discovered and shows only those and
  their parts (parent suggestions and the planner use only them too);
  **Show Spoilers** (under Options, remembered) shows every species, the full
  charts and every price. The patcher's own species (DS Exclusive Fish,
  Unused Flowers) appear only when the save's game copy was patched with that
  setting, marked in a Patcher column. Columns sort with a click, a Search box
  filters, and Export saves the open sheet as .xlsx or .csv. Every rule is the
  game's own: the Fish Tycoon model (`src/breeding_fish.py`) is checked
  against the vanilla executable in Unicorn by `tests/test_breeding_fish.py`
  (base prices 0x418B10, Advertising 0x420A82, the baby's genes 0x41FAAB, the
  Mutation fish 0x42014C, the sale odds 0x424240), and the Plant Tycoon model
  is `src/breeding_plant.py`. The prices' assumptions (real time, a full
  selling tank, how many customers browse) are in its "?" guide.
  Pictures: [docs/images/breeding-guide-fish-discovered-species.png](docs/images/breeding-guide-fish-discovered-species.png)
  and the other `docs/images/breeding-guide-*.png`.

## Safety

Each engine remains bound to the exact supported stock executable identity,
including SHA-256, size, PE fields, and resource-section hash. Every changed
byte is guarded, expected output hashes are pinned, backups are created, output
files are read back, and the original icon resources remain intact.

When both games are selected, both inputs are dry-run validated before either
output folder is written.

No game executable or save is included in this repository or release. The one
exception to shipping game files is `assets/plant_tycoon_steam/`: Plant Tycoon
files taken from the Steam version (316 sounds, images and other files), used
only to fill in what the LDW release is missing. LDW no longer updates the
games, so there is no other way for the LDW version to get them. Each is pinned by size and SHA-256 and refused if it does not match.

## What each patch does

Every setting in the GUI has a **Technical details** disclosure, collapsed by
default. For an executable fix it lists each byte-level change the setting
installs — virtual address, file offset, size, and what that change does. The
same note is written into the patch log next to each change, so a completed run
records not just what bytes moved but why. For Add Missing Assets it lists every
file the setting can add, and the patch log records each file as added,
identical and ignored, or kept at the game's version.
`docs/fish-tycoon-technical-details.md` and
`docs/plant-tycoon-technical-details.md` go further into the disassembly and the
asset merge.

## Credits

- Created with Codex AI, with contributions from Claude AI. Made with love by
  Lorsieab2.
- Plant Tycoon's new flower names (Add unused flowers): credit to
  **Virtual_Lady** and **Lorsieab2**.

## Tests

```
python tests/test_combined_patcher.py
```

The suite covers the exact executable identities, that every setting combination has a pinned output hash, the
game search, the GUI wiring, and the asset merge: additive only, identical files
ignored, tampered or outside bundles refused, and every bundled file stored by
git byte-for-byte against its pin. It uses synthetic fixtures and the bundled
assets only, so it needs no copy of either game.
