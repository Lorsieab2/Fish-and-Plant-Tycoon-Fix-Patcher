# Fish & Plant Tycoon Fix Patcher

<img src="assets/fish.png" alt="Fish" width="96"> <img src="assets/plant.png" alt="Potted plant" width="96">

🪴 Created with Codex AI, with contributions from Claude AI. Made with love by Lorsieab2 :) 🐟

An offline Windows patcher combining the current Fish Tycoon Fix Patcher and
Plant Tycoon Fix Patcher in the same player-facing format as the Virtual
Villagers Fun Patcher.

Current release: **v1.0.22**. See [CHANGELOG.md](CHANGELOG.md) for what each
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
- Buy Multiple Golden Seahorses (off by default). Allows purchasing of multiple Golden
  Seahorses, in case you trash or lose it somehow. It shipped broken from
  v1.0.6 and was fixed in v1.0.12; see
  [docs/golden-seahorse-defects.md](docs/golden-seahorse-defects.md).
- Bigger tanks: 30 fish (on by default; **EXPERIMENTAL - USE AT OWN RISK**). Tank 1, Tank 2 and the Sale Tank
  (Tank 3) hold 30 fish instead of 21 (the isolation tank still holds one;
  with 3 extra tanks, Tanks 4-6 hold 30 too), and
  fish 22-30 get everything fish 1-21 get. Every adult in the Sale Tank is
  for sale with the stock odds per fish, one sale a second at most as in the
  stock game; the crowd counts at most 21 adults, the stock game's most. The
  game's save already has room for them, so saves keep their layout. Sell or
  move fish down to 21 per tank before turning it off again. Design:
  [docs/fish-tycoon-tank-expansion.md](docs/fish-tycoon-tank-expansion.md).
- 3 extra tanks (on by default; **EXPERIMENTAL - USE AT OWN RISK**; **needs
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
  onto a button to move it to that tank; carry it over an arrow and the
  buttons switch to the other three tanks, so you can drop it on any of the
  six (letting go on the arrow itself keeps it where it was); a full tank
  refuses it as in the stock game. Each extra tank has a "For sale" button (Off at first): On, it shows
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
- Optimize Prices button (off by default). An "Optimize Prices" button on the
  Species Chart's bottom bar, left of Done (where you set prices), and the
  same button on the Fish Store screen (opened with Sell Fish), on its bottom
  bar left of Done, so it can be used any time: the Species Chart only opens
  with a fish in the isolation tank. Both do the same. It asks
  "Set every discovered species to its best price per day?"; on Yes, every
  species you have discovered gets the Breeding Guide's "best per day"
  asking price (the price that earns the most money over time), worked out
  in the game with the guide's own maths for your shop as it is now: each
  species' base price (with the Advertising rises), the ornaments you own,
  the Golden Seahorse and your Advertising level, with a full selling tank.
  Then it says "N prices set." Undiscovered
  species keep their prices and nothing else changes; the prices are the
  ones you would type yourself, saved with the game as usual. The DS species
  are included with DS Exclusive Fish. Beside it on both screens, a
  "Max Prices" button (left of Optimize Prices) asks "Set every discovered
  species to its highest selling price? Fish at this price sell much more
  slowly." and on Yes sets every discovered species to the highest asking
  price a customer still buys at, the guide's "highest selling": twice the
  species' base price, less 1. The sale roll (0x424240) compares the price
  only with the species' base price (2 x base or more never sells,
  0x4243DC), so nothing in a save raises that limit: ornaments, the Golden
  Seahorse and Advertising bring more customers, not higher prices, and the
  Advertising research raises the base price itself, which the button reads
  at the click. Then "N prices set." It runs as a companion DLL
  (`Fish Tycoon Fix Patcher DLLs\Optimize Prices.dll`) in the plain
  "Fish Tycoon - Modded" copy. Pictures:
  [docs/images/optimize-prices-fish.png](docs/images/optimize-prices-fish.png),
  [docs/images/optimize-prices-fish-store.png](docs/images/optimize-prices-fish-store.png).
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
  The counts update every frame and are drawn over everything in the tank
  (fish, creatures, ornaments, decorations, bubbles, the tank's name and For
  sale button), under only a fish or item in your hand and the game's popups;
  display only, nothing in the game or the saves changes. It runs
  as a companion DLL the game loads at start
  (`Fish Tycoon Fix Patcher DLLs\Tank Counts.dll`, which also loads DS
  Exclusive Fish's or the Maximizable window's DLL when those are on), in the
  plain "Fish Tycoon - Modded" copy. How it works, with every address:
  `native/ftfp_tank_counts/ftfp_tank_counts.c`. Pictures:
  [docs/images/tank-counts-fish.png](docs/images/tank-counts-fish.png),
  [docs/images/tank-counts-fish-off.png](docs/images/tank-counts-fish-off.png).
- DS Exclusive Fish (on by default). Adds the Nintendo DS version's seven
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
- DS Store Items (on by default; needs DS Exclusive Fish, which it turns on
  with it). An Upgrades button in the Supplies store opens the DS version's
  store items. The Puffer Fish, Sting Ray and Moray Eel ($1250 each) are tank
  companions like the Golden Seahorse: they swim, can be dragged between
  tanks, never age, breed or get sold, and magically enhance the life and
  environment of your fish (the Tools tab's Game Mechanics lists the exact
  effects). The Moray Eel comes with its rock: drop the eel on it to send it
  home, move the rock and the eel goes with it, and drag it out by its head.
  Trashing the eel trashes its rock, and the other way round, wherever the
  other one is (Tanks 4-6 included). The animals,
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
  Fish mutation, Plant of Fertility and "no room" as a natural birth), and
  the babies stay babies, as born (a later dose grows them up); then of the
  fish that were there before, younger ones become adults (age 20), and every
  one gets full health (100) and is cured of ick or fungus. Other tanks and the store
  animals are left alone. Treated fish sell for the highest possible price:
  every fish a dose heals is marked, and when it is sold (from the Sale Tank,
  or Tanks 4-6 with For sale On) you are paid its species' highest selling
  price, 2B - 1 with B its base price after both Advertising levels (the
  Breeding Guide's "Highest selling" with Max effects; a Golden Guppy pays
  $475), instead of your asking price. Which fish sells and when still follow
  your asking price. The treated price is shown beside the price you set, for
  a treated fish only: "Treated: $475" under the sold fish's "Price: $40" in
  the Fish Store (the selling screen), and under "Price: $40" on the Species
  Chart (where you set the price); nowhere else, not in any tank. The mark stays with the fish through moves between tanks,
  saves and ClonaFish clones (a clone of a treated fish is treated too), never
  passes to babies, and ends when the fish is sold, dies or is thrown away.
  Picture:
  [docs/images/radioactive-growth-hormone-fish.png](docs/images/radioactive-growth-hormone-fish.png).
  The Revival Potion ($10,000, 3 doses; $0 with Free upgrades), the owner's
  amber flask, is a slot-#3 chemical like the hormone: each dose revives every
  dead fish in the tank on screen at full health; its age, food, sickness and
  pregnancy stay as they were, and the time it lay dead is not played as time
  away. Dead fish stay in the tank until you throw them away (the game never
  removes them), so every dead fish still there can be revived. ClonaFish
  ($2,500, 3 doses; $0 with Free upgrades), the owner's magenta bottle: each
  dose adds one exact copy of every live fish in the tank on screen, any
  species, so each dose doubles the tank (the fish there before the dose are
  copied; a clone is cloned again by the next dose), in slot order, through
  the game's own add-fish code, until the tank is full;
  if there was no room for even one, the game's "The tank is full!" shows.
  Both work in every tank slot the game uses (Bigger tanks, and more) and in
  every tank the game updates. Picture:
  [docs/images/revival-potion-fish.png](docs/images/revival-potion-fish.png).
  Muta-Fin and Muta-Body ($2,500 each, 3 doses; $0 with Free upgrades), the
  stock Unknown Chemical's flask in royal blue and in sea green, after the
  Extra Supply Slots: each dose is the Unknown Chemical's for one part only.
  It reaches the same fish (every live fish in the tank on screen, any age,
  not the Golden Seahorse or the store animals, never the isolation tank),
  changes each on the same 26% chance and steps its fin (Muta-Fin) or its
  body (Muta-Body) one gene up or down by the game's own step; the other part
  never changes. With DS Exclusive Fish the step reaches the DS genes, as the
  Unknown Chemical's does. New species are discovered as usual, once the fish
  is an adult. Pictures:
  [docs/images/muta-chemicals-fish.png](docs/images/muta-chemicals-fish.png),
  [docs/images/muta-chemicals-icons.png](docs/images/muta-chemicals-icons.png).
  Exotic Fish Eggs and the five chemicals can be thrown away: let go on the
  trash can, the whole slot (every dose or hatch left) goes, with the trash
  sound and no question (the game only asks about a fish). The stock game
  throws no supply away, so the food and the stock medicines, chemicals and
  eggs still go back to their slot.
  The Auto-Feeder and the Auto-Healer ($10,000 each, bought once; $0 with Free
  upgrades), the owner's green feeder and the same machine in hot pink, beside
  ClonaFish: in every tank (Tanks 1-2, the Sale Tank, the isolation tank, and
  Tanks 4-6 with 3 extra tanks, on screen or not, through time away and the
  Time Warp step by step), every live fish's food is kept full, at 100 (never
  hungry, never starving, and while it is owned feeding by hand never costs
  health for overfeeding), and every live
  fish is cured of ick and fungus (each counted under Fish Cured) and kept at
  health 100. Neither touches a dead fish. Click an owned one again and answer
  Yes to unpurchase it: it switches off at once, with no refund (buying it
  again costs the full price). Ownership is kept in `Auto Upgrades <slot>.dat`
  beside the save. Picture:
  [docs/images/auto-upgrades-fish.png](docs/images/auto-upgrades-fish.png).
  The Golden Seahorse keeps its PC effects and gains its DS one. Every supply
  slot (the stock four, and the extra ones with Extra supply slots) shows a
  tooltip while the mouse is over it, in the game's own rope-edged hint box
  just under the top bar (only the hovered slot of the page shown, one at a
  time): the item's name and what is left of it as the game will spend
  it -- doses for medicines and chemicals, uses for the Unknown Chemical (one
  in the stock game, three with Unknown Chemical: 3 uses or Universal supply
  slots), batches for eggs (one, or the stack with Universal supply slots) --
  in German when the game is; the fish food shows its name only (the game
  keeps no amount of it); nothing shows over an empty slot, while a hint is
  up or while something is held. Pictures:
  [docs/images/supply-slot-tooltip-hormone.png](docs/images/supply-slot-tooltip-hormone.png),
  [the fish food](docs/images/supply-slot-tooltip-food.png),
  [eggs](docs/images/supply-slot-tooltip-eggs.png). It runs as a
  second companion DLL (`Fish Tycoon Fix Patcher DLLs\DS Store Items.dll`),
  loaded by DS Fish's; besides the game's own save it writes only the
  animals' `Tank Animals <slot>.dat`.
  Design and live checks:
  [docs/fish-tycoon-ds-store-items-design.md](docs/fish-tycoon-ds-store-items-design.md).
  Trash the store animals, and let the eel out of its rock, before turning it
  off again.
- Time Warp (on by default; turns on the store's Upgrades screen it lives on).
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
  ClonaFish ($2,500), Muta-Fin ($2,500), Muta-Body ($2,500), the Auto-Feeder
  ($10,000), the Auto-Healer ($10,000), and
  the Time Warp clock ($500), Add Money ($950), the Extra Tank ($10,000 each)
  and the Extra Supply Slots ($10,000) when they are on. The price shows $0 and no
  money is taken; everything else (one of each animal, the supply slots,
  Tanks 4-6 bought in order, the game's purchase question) stays. The game's own store items keep their
  prices.
- Add Money cheat ($1,000) (off by default; **needs DS Store Items, which it
  turns on**). A pile of gold coins on the Upgrades screen, next to the Time
  Warp clock: $950 ($0 with Free upgrades), bought like the other items, adds
  $1,000 to your money, as often as you like. Money stops at the largest
  value the game holds ($2,147,483,647). Picture:
  [docs/images/add-money-fish.png](docs/images/add-money-fish.png).
- Everything is Free (off by default; **CHEAT**; not turned on by Select All
  Patches or Owner's Defaults: tick it yourself). "Every store item and upgrade is free. Obviously a cheat
  mod, have fun!" Every price you pay is $0 and the store says $0: every
  Supplies store item (food, medicines, chemicals, eggs, plants, ornaments,
  Tank Two, the Golden Seahorse), research, and everything on the Upgrades
  screen (the DS animals, Exotic Fish Eggs, the potions, ClonaFish, the Auto
  items, the Time Warp clock, the Extra Tank, the Extra Supply Slots, and
  copies with Multiple ornaments), as Free upgrades does. Add Money then costs
  $0 and still adds $1,000. Only the price changes: one of each, "already in
  your inventory", the extra tanks in order, room in a slot, the research
  levels and the purchase questions all stay. The executable's own price
  reads are zeroed in place (the price table in the save is never touched);
  the store DLLs read "Everything Free.ini" beside them. Selling fish is
  unchanged.
- Extra supply slots (on by default; **EXPERIMENTAL - USE AT OWN RISK**;
  **needs DS Store Items, which it turns on**). Eleven supply slots instead of
  four, in three pages at the top left of the tank screen: page 1 is the
  stock four (the fish food and slots 2-4), page 2 four more and page 3
  three more (its fourth frame is greyed). Two small arrows right of slot 4
  (the game's own arrow, as the 3 extra tanks' arrows) turn the page; carry
  an item over an arrow to turn the page while you hold it. Buy all seven at
  once on the Supplies store's Upgrades screen: Extra Supply Slots, $10,000
  ($0 with Free upgrades), then "This is in your inventory." and "You already
  own this!". Until then the arrows are grey and say "You don't own the extra
  supply slots yet!" under the top bar. Once bought, "1/3", "2/3" or "3/3"
  under the arrows, small and in the bar's yellow, says which page shows
  (nothing before the purchase: there is only one page then). Every extra slot works like slots
  2-4: the store fills the first free slot over all three pages (with
  Universal supply slots a stack of the same item first, anywhere); every
  medicine, chemical and egg -- the stock ones and DS Store Items'
  Radioactive Growth Hormone, Revival Potion, ClonaFish, Muta-Fin, Muta-Body
  and Exotic Fish Eggs
  -- is used from it on the tank by the game's own code, with the same doses
  and hatches; the trash takes the patcher's supplies as from slots 2-4 and
  never the stock ones. Drag a supply onto any slot, on any page, to move
  it: onto an empty slot it moves, onto the same item it stacks (with
  Universal supply slots), onto another item the two change places. Without
  Universal supply slots, slots 2-4 keep their kind (medicine, chemicals,
  eggs) and each extra slot takes any one item, one purchase at a time, as a
  stock slot does; with all eleven full the store asks the stock "Replace
  ...?" questions. The fish food stays in slot 1, the Supplies store still
  shows the stock four; DS Store Items' tooltips name the item in every
  slot, extra ones too, and what is left of it. Mockups:
  [docs/images/extra-supply-slots-page-1.png](docs/images/extra-supply-slots-page-1.png),
  [page 2](docs/images/extra-supply-slots-page-2.png),
  [page 3](docs/images/extra-supply-slots-page-3.png),
  [before buying](docs/images/extra-supply-slots-locked.png) and
  [the Upgrades screen](docs/images/extra-supply-slots-store.png). It runs as
  a companion DLL the game loads at start (`Fish Tycoon Fix Patcher
  DLLs\Extra Supply Slots.dll`), in the "Modded Upgrades" copy; the saves keep
  their stock layout and each save slot keeps its seven extra slots and the
  purchase in `Fish Tycoon Fix Patcher Data\Extra Supply Slots <slot>.dat`
  beside the saves (written whole or not at all; one that cannot be read is
  set aside as `.unreadable-<n>.dat`, never deleted). A new game empties them.
  Turning it off: use or move what is on pages 2 and 3 first. Nothing is
  deleted -- the file stays and everything comes back, with the purchase,
  when you turn it on again -- but until then the game cannot reach them.
- Multiple ornaments (on by default; **EXPERIMENTAL - USE AT OWN RISK**). The Shell, Pagoda, Diver, Fancy Coral,
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
- Add unused flowers (on by default). Fourteen flower heads ship in the game's art
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
- Add new store upgrades and items (on by default; needs Add unused
  flowers). An Upgrades link on the bricks at the left of the Supplies store
  opens a second view of the store with only the new items, each where it
  would sit in the stock store:
  - Legendary Seeds on the seed shelves: three a day, $5000 each, any foliage
    with one of the new flowers (the stock packets keep their stock flowers).
  - Radioactive Plant Formula with the chemicals: $10,000, 3 doses; far
    beyond spamming Fertilizer Bombs and Plant Food: every branch grows (dead
    ones and the ones the plant's shape normally hides), the largest size,
    full bloom, a flower on every spot of every branch and leaf (hundreds on a
    big plant), no dead or brown leaves, full health, and always 5 seeds:
    an already pollinated plant has all its seeds ripe at once, any other
    gives all 5 at its next pollination (the Formula Bomb too). Treated
    plants sell for the highest possible price: when a visitor buys a plant
    given the formula (or its Bomb), in any nursery, you are paid its species'
    highest selling price, the highest asking price a visitor still buys at
    with every effect at its best (the Breeding Guide's "Highest selling" with
    Max effects; a Fabled Lemonbush pays $1186), instead of your asking price.
    Whether and when it sells still follow your asking price. The mark stays
    with the plant through moves, nurseries and saves, and ends when it is
    sold, dies or its pot is replanted. The treated price is shown beside the
    set price, as "Treated: $1186", in two places only: the nursery's bottom
    bar ("Asking Price: $665 Treated: $1186" when you click a treated plant
    for sale, "Plant sold! Price: $665 Treated: $1186" when one sells) and the
    Set Price of Plant window under its price. The greenhouses show only the
    set price. The store describes both items with "Allows treated plants to
    sell at max price, regardless of their set value."
  - Radioactive Plant Formula Bomb under the formula: $30,000, 3 doses; the
    stock Fertilizer Bomb made rainbow. One bomb gives every live plant in the
    greenhouse on screen exactly one Radioactive Plant Formula dose (the
    plants the Fertilizer Bomb reaches, in whichever greenhouse is shown).
  - Revival Potion beside the formula: $10,000, 3 doses, the owner's amber
    flask. Dropped on a dead plant, it comes back to life at full health; the
    parts that were already dead before it died stay dead (prune them or use
    the formula), and the seeds it lost when it died stay lost. A plant that
    was for sale when it died is for sale again, unless the nurseries are
    already full (then a message says so). No chemical, stock or new, takes
    a plant off sale.
  - Revita-Seed beside that: $2,500, 3 doses, the owner's teal bottle.
    Dropped on a plant that has given all its seeds, it can be pollinated
    again and give seeds again, exactly like a fresh plant.
  - Picture: [docs/images/revival-potion-plant.png](docs/images/revival-potion-plant.png).
  - Muta-Flower and Muta-Foliage on the chemicals shelf's third row: $2,500
    each, 3 doses, the stock Mutation Liquid's bottle in pink and in green.
    Each is the Mutation Liquid for one part only, on the plant it is dropped
    on: Muta-Flower steps the flower, Muta-Foliage the foliage, one up or one
    down, 50% each, with the game's own step and bounces; the other part never
    changes. The new species is discovered at once, as with the Mutation
    Liquid; the unused flowers come only with Add unused flowers. Picture:
    [docs/images/muta-chemicals-plant.png](docs/images/muta-chemicals-plant.png).
  - The formula, the bomb, the Revival Potion, Revita-Seed, Muta-Flower and
    Muta-Foliage can be thrown
    in the Trash bin: held from the chemical tray and let go or clicked on
    the bin, the bottle goes with every dose left, with the bin's sound and
    no question, as a seed packet does (no money back). A selected plant is
    not asked about. The stock game never bins a chemical or a tool, and
    still doesn't for its own. Legendary Seeds and new-flower seeds go in the
    bin like any seed (sold for their value).
  - Automatic Sprinklers on the tool shelf under the Extra Greenhouse, and the
    Auto-Healer beside the Formula Bomb: $10,000 each, bought once (the
    owner's sprinkler head, and the Fish Tycoon healer machine in hot pink).
    In every greenhouse (Greenhouses 2-6 too, on screen or not, through time
    away and the Time Warp unit by unit), the sprinklers keep every live
    plant's water at 800 (never too dry, and below the 900 at which pests
    come three times as often), and the Auto-Healer clears pests (each counted under
    Plants Cured) and keeps health at 100. Neither touches a dead plant (the
    Revival Potion's job), and old age still ends a plant's life. Click an
    owned one and answer Yes to unpurchase it: it switches off at once, with
    no refund (buying it again costs the full price). Ownership is kept in
    `Auto Upgrades <slot>.dat`. Picture:
    [docs/images/auto-upgrades-plant.png](docs/images/auto-upgrades-plant.png).
  - One Extra Seed Box item on the tool shelf, beside the Extra Greenhouse:
    each click buys the next of the Fourth to Ninth Seed Box, in order, $1000
    each, with a Yes / No like the Extra Greenhouse; its tooltip says which
    comes next ("Extra Seed Box 4 of 6"), and it gets a tick once all six are
    yours ("You already have all six extra seed boxes!"). Saves keep the boxes
    they had. Each opens a 40-seed drawer: boxes 4-6 in a second
    chest, boxes 7-9 in a third. The gold arrows on the Seed Storage title bar
    step through boxes 1-3, 4-6 and 7-9 (each page once it has a box, then
    round again), and the greenhouse fills boxes 4-6 once 1-3 are full, then
    7-9: 360 seeds in all. Kept in `Seed Boxes <slot>.dat` (a file from an
    older version, boxes 4-6 only, still loads). Pictures:
    [docs/images/extra-seed-box-store.png](docs/images/extra-seed-box-store.png),
    [docs/images/seed-boxes-7-9-storage.png](docs/images/seed-boxes-7-9-storage.png).
  - Click Supplies in the bottom bar to go back.
  - Design:
    [docs/plant-tycoon-upgrades-design.md](docs/plant-tycoon-upgrades-design.md).
- Time Warp (on by default; turns on the store's Upgrades screen it lives on).
  A clock item on the Upgrades screen: pay a flat $500, type 1-72 real-time
  hours in a small Windows popup, confirm Yes, and the game plays those hours as
  if you had been away, with no catch-up cap. At Normal speed 1 hour is 6 age
  steps/units; at 2x (Fish) 12 and Fast (Plant) 30; at 1/2 speed / Slow 4.
  Refused while time is stopped. Once the hours have been played, an OK box says
  so: "Time Warp done: 12 hours played (72 age units). $500 paid." ($0 paid with Free upgrades).
- Free upgrades (off by default; **needs Add new store upgrades and items,
  which it turns on**). Every item on the Supplies store's Upgrades view costs
  $0: Legendary Seeds ($5000), the Radioactive Plant Formula ($10,000), the
  Formula Bomb ($30,000), the Revival Potion ($10,000), Revita-Seed ($2,500),
  Muta-Flower ($2,500), Muta-Foliage ($2,500),
  Automatic Sprinklers ($10,000), the Auto-Healer ($10,000), the
  Extra Seed Box ($1000 each), and the Time Warp clock ($500),
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
- Everything is Free (off by default; **CHEAT**; not turned on by Select All
  Patches or Owner's Defaults: tick it yourself). "Every store item and upgrade is free. Obviously a cheat
  mod, have fun!" Every price you pay is $0 and the purchase window says
  "Price: $0": seeds, the Extinct and imported seeds, tools, chemicals,
  nursery items, and everything on the Upgrades view (Legendary Seeds, the
  Formula, the Bomb, the potions, Revita-Seed, the Extra Seed Box,
  the Extra Greenhouse and Nursery, the Automatic Sprinklers, the
  Auto-Healer, the Time Warp clock), as Free upgrades does. Add Money then
  costs $0 and still adds $1,000. Only the price changes: three Legendary
  Seeds a day, room in the seed and chemical trays, tools you already own,
  and the boxes, greenhouses and nurseries in order all stay. Selling plants
  is unchanged.
- Sort Seeds button (on by default). A "Sort Seeds" button on the Seed
  Storage title bar. After a Yes/No question it sorts every seed in the
  unlocked seed box space by the class of the plant it grows, its foliage and
  flower, then its parents (unknown first), and packs them from the first
  slot: boxes 1-3 fill before 4-6, and locked drawers stay empty. It checks
  that exactly the same seeds come out as went in before writing anything.
- Optimize Prices button (off by default). An "Optimize Prices" button on the
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
  Unused Flowers species are included when that setting is on. Left of it on
  the same bar, a "Max Prices" button asks "Set every discovered species to
  its highest selling price? Plants at this price sell much more slowly."
  and on Yes sets every discovered species to the highest asking price a
  visitor still buys at, the guide's "highest selling": the price visitors
  see must stay below twice the species' value (the buy roll, 0x436BE0).
  The only save-wide effect on the price seen is the Golden Berries of
  Wealth (a quarter off, so a higher limit), read at the click; Plant Food,
  pruning, dead leaves, health, flowers and pests are each plant's own and
  are left out (a healthy, flowering, unpruned plant without Plant Food).
  Then "N prices set." It runs as a
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
  own an extra greenhouse the lines sit under the greenhouse's name and the
  button moves right of the name, above it. The stages
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
- 5 extra greenhouses (**EXPERIMENTAL - USE AT OWN RISK**; on by default;
  **needs Add new store upgrades and items, which it turns on**; in the
  "Modded Upgrades" copy). Every greenhouse screen is named at the top in the
  game's font ("Greenhouse 1" is the stock one). Up to six
  greenhouses of 15 pots, 90 pots in all. An Extra Greenhouse item on the
  store's Upgrades screen (the tool shelf, beside the Extra Seed Box,
  pictured with the game's own greenhouse) sells Greenhouses 2-6 in order,
  $10,000 each ($0 with Free upgrades), and gets a tick once all five are
  yours; a new game starts with none. Once you own one, the game's own gold
  arrows (as on the Seed Storage screen) on both sides of the greenhouse
  screen, beside the middle shelf, page through Greenhouse 1, the stock one, and the ones you own, and the
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
- 5 extra nurseries (**EXPERIMENTAL - USE AT OWN RISK**; on by default;
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
- Extra chemical slots (**EXPERIMENTAL - USE AT OWN RISK**; on by default;
  **needs Add new store upgrades and items, which it turns on**; in the
  "Modded Upgrades" copy). The greenhouse's Tools box is a 4 x 2 grid: the
  four tools, and under them the four chemical slots. This adds a second page
  of 8 chemical slots that fills both rows (12 chemical slots in all). An
  Extra Chemical Slots item on the store's Upgrades screen (the chemicals
  shelf, under the Formula Bomb) costs $10,000 ($0 with Free upgrades), is
  bought once and gets a tick. Then a small gold arrow (the game's own,
  shrunk) sits on each side of the Tools box, with "1/2" / "2/2" under the
  right one: click either arrow, or carry a chemical over one, to turn the
  page. The tools stay on
  page 1; a tool already in your hand stays there. Every page-2 slot works
  like a stock one: the store fills a chemical onto its own bottle on either
  page, else the first free slot of page 1, then of page 2, and says the tray
  is full only when all 12 are; every chemical (the game's and the Upgrades
  screen's) is used from it with its doses; the Upgrades screen's chemicals
  go in the trash from it. A chemical in your hand can be put on any other
  slot of either page (moved, stacked onto the same chemical, or swapped).
  Every chemical slot of both pages shows a tooltip with the chemical's name
  and the doses left ("Revival Potion / 2 doses left"), nothing over an
  empty slot; this replaces the stock tray tooltips while the setting is on,
  bought or not. The tray is shared by every greenhouse. Page 2 and the
  purchase are kept per slot in "Plant Tycoon Fix Patcher Data\Extra Chemical
  Slots <slot>.dat" (the save keeps its stock layout); a new game empties
  page 2. The store's own tray picture shows page 1. **Turning it off hides
  page 2 but loses nothing:** while Add new store upgrades and items stays on,
  loading a save puts page 2's chemicals into the 4 stock slots as far as
  there is room (onto the same chemical, else a free slot), and the rest and
  the purchase stay in the slot's file until you turn it on again.
  Runs as a companion DLL the game loads at start
  (`Plant Tycoon Fix Patcher DLLs\Extra Chemical Slots.dll`, loaded after the
  other companions).
  - Pictures: [docs/images/extra-chemical-slots-page-1.png](docs/images/extra-chemical-slots-page-1.png),
    [docs/images/extra-chemical-slots-page-2.png](docs/images/extra-chemical-slots-page-2.png),
    [docs/images/extra-chemical-slots-store.png](docs/images/extra-chemical-slots-store.png).
  - Design: the "Extra Chemical Slots" section of
    [docs/plant-tycoon-upgrades-design.md](docs/plant-tycoon-upgrades-design.md).

## Use

1. Extract the release ZIP.
2. Double-click `Launch Fish and Plant Tycoon Fix Patcher.bat`.
3. Click **Find Both in Parent Folder...** and pick the folder your game
   folders sit in, or select each vanilla folder yourself.
4. Select **One Game** or **Both Games**.
5. Choose the fixes you want. The buttons above the tabs set both games'
   lists at once (see "Choosing patches" below); every row can still be
   ticked or unticked by hand afterwards.
6. Validate, dry run, or create the fixed copy/copies.

### Choosing patches

Above the One Game / Both Games tabs, as in the Virtual Villagers Fun
Patcher, one row of buttons (each with a **?** that explains it) replaces the
ticks in **both games** at once:

- **Select All Patches**: every patch except Everything is Free (a **CHEAT**,
  which you tick yourself).
- **Default Patches**: each game's recommended set, the one a fresh install
  starts with. Everything that costs something in the game (money, tech
  points, food) and everything that adds new content is on: every fix, the
  DS Exclusive Fish and DS Store Items, the unused flowers and new store
  upgrades and items, Time Warp, Sort Seeds and the EXPERIMENTAL settings
  (Bigger tanks, 3 extra tanks, Extra supply slots, Multiple ornaments, 5
  extra greenhouses, 5 extra nurseries, Extra chemical slots). So the
  default copies are the "- Modded Upgrades" ones. Cheats and anything free
  are off until you tick them: **Everything is Free**, **Free upgrades**
  (both make prices $0), **Add Money**, **Buy Multiple Golden Seahorses**
  and the **Optimize Prices button**.
- **Owner's Defaults**: the patcher owner's own choice, every patch in both
  games except Everything is Free: Default Patches plus Free upgrades, Add
  Money, Buy Multiple Golden Seahorses and the Optimize Prices button.
- **Deselect All Patches**: unticks every patch in both games.

A setting that needs another one (DS Store Items needs DS Exclusive Fish,
Time Warp needs DS Store Items or the new store upgrades) brings it along, as
when you tick it yourself.

**Patch Selection Settings...** (on its own row, with its **?**) opens a
window listing every patch name once, with the games that have it ("(both
games)", "(Fish Tycoon)" or "(Plant Tycoon)"). Tick the names you want and
press **Tick These** or **Untick These**: each one is changed in every game
that has it, and the status line says what changed ("Ticked 4 patches across
the games: Fix Vanilla Bugs, Time Warp.").

Your ticks are remembered in `patcher_local_settings.json` beside the
patcher, written whenever they change and read when it starts; a setting the
file does not know yet starts at its default.

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
Multiple ornaments, 3 extra tanks, Extra supply slots, Add unused flowers, Add new store upgrades and items), the copy is
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
Copy player slot..., Game mechanics..., Breeding guide..., Picture
studio...), and Back Up Saves (Both)... for both at once. Every tool
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
- **Copy Player Slot.** Copies a player into another slot of the same save
  folder under a new name: the slot's save files and the
  patcher's own files for it (`<Game> Fix Patcher Data\<what> <slot>.dat`
  and their `.previous` copies: extra tanks and greenhouses, supply slots, DS
  fish, tank animals, seed boxes, new flowers and the rest), with the new name
  in the player list and inside the copied save. The original is not changed.
  The target can be an empty slot or one in use, whose player is replaced
  after a warning that names them (No is the default). The replaced player's
  files, or anything an earlier player left on an empty slot, are not deleted
  but moved into `Backups\Replaced by copy <date> - Player <n> - <name>`,
  keeping their paths, and moved back if the copy fails; that folder is not a
  backup Restore Saves lists. It asks before copying, needs the game closed
  and backs the save folder up first, as `(before copy)`. As in
  the game, the slots are the files `<Game>1.ldw` to `<Game>5.ldw`: a slot
  without its file is empty even when the player list still names someone,
  and a slot whose file holds a player is that player even when the list says
  "NEW PLAYER" (all the tools list players this way).
- **Game Mechanics.** A read-only page, with a tab for each game, on how the
  games really work underneath, read from their code:
  - time away, health, food, sickness, pests, breeding, seeds, the store,
    research, selling, magic fish and plants, and bugs (Plant Tycoon's 48
    collectible bugs one by one: family, rarity and how each appears, and
    the bonus for catching all 48);
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
    Grouper in Fish Tycoon, Mutation Liquid in Plant Tycoon);
  - the **Collectopedia**: a checklist of every species, a row per body
    (foliage) and a column per fin (flower), each box ticked where the save
    has ever had that species (its own discovered record; the DS Exclusive
    Fish and Unused Flowers too when that setting is on for the save). Only
    the save ticks a box. It counts "n of N species collected" overall, per
    rarity and per part, filters All / Collected / Missing and by Search, has
    a sortable List view, and exports as .xlsx or .csv. With spoilers off a
    species not collected yet is a "?" with no name or picture.

  Rarities: Common, Uncommon and Rare in Fish Tycoon (the Common and Unusual
  Fish Eggs lay the Common and Uncommon parts). In Plant Tycoon, flower and
  foliage parts go by tier, from the soil they need to grow: Tier 1 (class A,
  Citrus and the like), Tier 2 (class B, Rosaceae), Tier 3 (class C, Nox),
  Tier 4 (class D, Arthurium) and Tier 5 (the Legendary flowers of Unused
  Flowers); a species is as high as its higher part. The seed packets keep
  their names (Common, Endangered, Extinct, Legendary Seeds). Every
  "how it is obtained" quotes the exact odds from the game's code. A
  scrolling pane under each sheet shows the picked row's details.

  It opens on the species the save has discovered and shows only those and
  their parts (parent suggestions and the planner use only them too);
  **Show Spoilers** (under Options, remembered) shows every species, the full
  charts and every price. With spoilers off each part tab (Fins, Bodies,
  Flowers, Foliage and their picture tabs) lists exactly the parts the save
  has discovered, with "n of N discovered" at the top. Neither game keeps a
  flag per part: Fish Tycoon's only discovery record is a species' asking
  price (-1 until the species is first an adult, 0x41E2D0), Plant Tycoon's a
  byte per species (set at maturity, 0x42E2C4, and by Mutation Liquid,
  0x426F11), and both name a fish or plant only by its species. So a part is
  discovered when a species the save has discovered has it; the DS species
  are read from "DS Fish <slot>.dat" and the save's own spare columns, the
  Unused Flowers from "New Flowers <slot>.dat", as their DLLs keep them.
  Undiscovered parts are left out (no "?"), and no column, detail, effects
  label or export names an undiscovered part or species (the Mutation fish
  is "Magic Fish of Mutation" until it is discovered). The patcher's own
  species (DS Exclusive Fish, Unused Flowers) appear only when the save's
  game copy was patched with that setting, or the setting's data file is
  beside the save, marked in a Patcher column. Columns sort with a click, a Search box
  filters, and Export saves the open sheet as .xlsx or .csv. Every rule is the
  game's own: the Fish Tycoon model (`src/breeding_fish.py`) is checked
  against the vanilla executable in Unicorn by `tests/test_breeding_fish.py`
  (base prices 0x418B10, Advertising 0x420A82, the baby's genes 0x41FAAB, the
  Mutation fish 0x42014C, the sale odds 0x424240), and the Plant Tycoon model
  is `src/breeding_plant.py`. The prices' assumptions (real time, a full
  selling tank, how many customers browse) are in its "?" guide.

  Picture tabs (Fin, Body and Egg Pictures; Flower, Foliage and Seed
  Pictures) show every part grouped by rarity; Seed Pictures is a grid, a
  row per foliage (Common first, then Endangered and Extinct, the game's
  classes A to D) and a column per seed tier, lowest on the left (the shop
  draws a packet by its flower: Common, Endangered, Extinct and the rarest
  Extinct flowers; then Legendary with Unused Flowers). The pictures are kept inside
  the patcher, in a "Breeding Guide Pictures" folder beside it: the first time
  the guide finds any copy of the game (the game folder picked on the Game
  tab, the patcher's "- Modded" and "- Modded Upgrades" copies, or a default
  install) it copies the sheets it needs from it, read only, with a manifest
  of their SHA-256 hashes, and shows them from there for every save folder
  and player. If it has found none yet, click "Find game..." on a picture tab
  and pick the game folder. The folder is made on your own machine from your
  own copy; no game art is in this repository or the release, and the folder
  is ignored by git. A damaged or partial picture folder is made again, never
  used. The patcher's own art (DS sheets, Exotic Fish Eggs, the Unused
  Flowers' sheet, Legendary Seeds) comes from `assets/`.
  Pictures: [docs/images/breeding-guide-fish-discovered-species.png](docs/images/breeding-guide-fish-discovered-species.png)
  and the other `docs/images/breeding-guide-*.png`.
- **Picture Studio.** The fish and plants in your saves, and pictures you make
  yourself, drawn exactly as the game draws them, saved as transparent PNGs:
  - From my save: the save folder and player (read only), everything the save
    holds tank by tank (Tanks 1-3, the isolation tank, Tanks 4-6 from "Extra
    Tanks <slot>.dat"), then the creatures (the Golden Seahorse, DS Store
    Items' animals, the Cleaning Snail) and decorations (ornaments, Multiple
    Ornaments' copies, plants and equipment), each at its own age and state.
    As in the game, a fish is named only from age 20: with Show Spoilers off
    younger ones are "Baby fish" / "Teen fish", in the list and in file names.
    In a tank with fish, its decorations and creatures are in their own
    "Decorations and creatures" sub-list, after the fish. "Save all in this
    tank" saves every picture in it into a new folder, the decorations and
    creatures in a "Decorations and creatures" folder inside it, and says how
    many of each it saved. In
    Plant Tycoon: every pot, greenhouse by greenhouse (Greenhouses 2-6 from
    "Extra Greenhouses <slot>.dat"), and the decorations, each plant at its own
    age, growth and health; "Save all in this greenhouse".
  - Make your own, Fish Tycoon: Fin, Body, Stage (baby, teen at every age
    6-19, adult) and State (healthy, ick, fungus, dead), facing left or right
    or turning (Facing), at any frame; creatures and decorations on their own tabs,
    and Eggs: the 16 pictures of eggs dropped into a tank, as the game's tank
    effect draws them. The game draws nothing for a fish before it hatches
    (age 0); a hatched fish is a baby (the fry) until age 6. It has no old age
    and no belly-up pose apart from the dead pictures.
    The DS Exclusive Fish bodies and fins, DS Store Items' animals and the
    eel's rock are always offered, marked "(patcher)": their pictures ship
    with the patcher, so no setting needs to be found for the save.
  - Make your own, Plant Tycoon: Flower (the 14 Unused Flowers always too,
    marked "(patcher)"), Foliage, Stage (seed, sprout, seedling, growing, budding, normal bloom, max bloom, max
    bloom with every effect, as after the Radioactive Plant Formula) and State
    (alive, or dead at any of those stages),
    the plant's starting shape and its pot; decorations, bugs and pots on
    their own tabs. "Unused parts": the 12 parts in the game's own plant
    tables that no plant ever grows (Reptans 6, Astera, Fern, Ananas 2,
    Pitcher, Ridgeball), alive or dead, as the game's branch draw draws them.
    Neither game has unused fish bodies or fins: all 21 of each are bred. The game draws no wilting or infested look: a plant is
    drawn alive or dead (0x42E4A0 checks only health 0).
  - With Show Spoilers off (the Breeding Guide's setting) Make your own offers
    only the parts you have discovered.
  - PNG sizes: the game's own size, 2x or 4x (crisp), or any width and height
    (smooth); cut to the drawn pixels with a small clear margin, or none.

  Every drawing rule is the game's own, ported to Python (no Pillow or
  Unicorn is needed): `src/pictures_fish.py`, proven by
  `tests/test_pictures_fish.py`, which runs the game's fish draw (0x4145F0),
  sprite setup (0x415DF0), ornament pass (0x41D600) and blitter (0x4041C0) in
  Unicorn on the vanilla executable and checks every draw against the plan
  (and the DS Exclusive Fish rules against the companion's own C), and
  `src/pictures_plant.py`, proven by `tests/test_pictures_plant.py` against
  Plant Tycoon's own pot, plant, branch and flower draws (0x42F740, 0x42E4A0,
  0x42E690, 0x42D9C0), its growth and its scaler (0x404610). The
  pictures come from your own copy of the game, kept in a "Picture Studio
  Pictures" folder beside the patcher, as the Breeding Guide's. See
  [docs/picture-studio-interface.md](docs/picture-studio-interface.md).

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
