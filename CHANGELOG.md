# Changelog

## v1.0.17

New content for both games (DS fish, fins and store animals; the 14 unused
flowers and a store Upgrades page), bigger tanks, a Tools tab, and fixes.

### Both games

- No path is too long: the patcher's staging copy and the save backups use
  Windows' extended-length paths, so a deep output or save folder never fails
  with "path too long"; the staging folder's name is also shorter.

- The companion DLLs are named after their settings and kept in
  "Fish Tycoon Fix Patcher DLLs" / "Plant Tycoon Fix Patcher DLLs" inside
  the modded copy: DS Exclusive Fish.dll, DS Store Items.dll, Unused
  Flowers.dll, Store Upgrades and Items.dll, Extra Seed Boxes.dll.

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
  every picture in a scrolling grid. The pictures are read at run time from
  the chosen save's own game copy (its Images folder, then Fish Tycoon's
  ft.dat, as the game loads them), the patcher's DS sheets, Exotic Fish Eggs
  and Legendary Seeds included; no game art is shipped. With spoilers off an
  undiscovered part is a "?" with no name, and a copy whose images are
  missing or unreadable says so. It reads the chosen save
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

### Plant Tycoon

- **5 extra greenhouses**, a new setting, off by default, in the "Modded
  Upgrades" copy: six greenhouses of 15 pots, 90 pots in all. The game's own
  gold arrows on the greenhouse screen page through Greenhouse 1 (the stock
  one) to Greenhouse 6, and the screen says "Greenhouse n of 6". Every
  greenhouse is the stock screen with the game's own code running on its
  pots, so every plant, chemical, tool, upgrade and magic plant works the same
  in each, and every greenhouse grows while you look elsewhere, while you are
  away and through the Time Warp (checked in emulation byte for byte against
  the stock pots). Drag a plant onto an arrow to move it to the same pot place
  in the next (or previous) greenhouse, or its first empty pot if that place
  is taken; pollen and seeds taken from a plant are carried between
  greenhouses, and held tools, chemicals and tray seeds stay in hand. The
  nursery keeps its 15 spots: at most 15 plants are for sale at once, counting
  every greenhouse. Greenhouses 2-6 are kept per save slot in "Plant Tycoon Fix
  Patcher Data\Extra Greenhouses <slot>.dat"; the save keeps its stock layout.
  Empty them before switching the setting off. Design:
  docs/plant-tycoon-extra-greenhouses-design.md; picture:
  docs/images/extra-greenhouses-switch.png.
- The Time Warp also moves the clocks of the extra greenhouses' plants.

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
    hundreds on a big plant. No dead leaves, full health, and 5 seeds when
    pollinated.
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

### Both games

- With a setting that adds new content on (DS Exclusive Fish or DS Store
  Items; Add unused flowers or Add new store upgrades and items), the copy is
  "Fish Tycoon - Modded Upgrades" / "Plant Tycoon - Modded Upgrades" (folder
  and EXE), beside the plain "- Modded" copy, so the two never replace each
  other. A folder you name yourself keeps its name.

### Fish Tycoon

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
- **Credits:** Plant Tycoon's new flower names are by Virtual_Lady and
  Lorsieab2 (README, How to Use, the patcher window and the setting).
- **Game Mechanics**: a new "Which tank counts" section (Fish) and "Where things count" section (Plant): magic fish only in their own tank, owned items and ornaments everywhere, food and Ick/Fungal treatment also reach the isolation fish, magic plants permanent once discovered, plants for sale still in their pot.
- **Game Mechanics**: Fish Food research is explained in full (food
  duration per level, sickness odds, food look), and the starter-eggs entry
  shows why the first baby is always a Greenfin Spotanus and how a player
  can still end up without one.
- **Bigger tanks: 26 fish**, a new setting, off by default. Every tank holds
  26 fish instead of 21: 45 byte changes to every place that assumes 21.
  The state already has 31 fish records per tank and saves all of them, so
  the save layout is unchanged.
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
    each tank has 5 animal slots of its own (slots 26-30), and saves from
    earlier builds are moved over on load. With Buy Multiple Golden
    Seahorses on they can be bought more than once.
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
  - Selling-tank customers no longer look at any seahorse-type companion
    (stock code read the Golden Seahorse's species data out of range).
  - Runs as "DS Store Items.dll", loaded by "DS Exclusive Fish.dll"; all or
    nothing, with its own log. Nothing new is saved outside the game's own
    save.

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
