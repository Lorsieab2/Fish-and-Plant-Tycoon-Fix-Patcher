# DS store items in PC Fish Tycoon

Status: built ("DS Store Items.dll", the "DS Store Items" setting) and run in
the game; see "Live checks" at the end. Every hook site is pinned by
`scripts/build_ds_store_headers.py` against the vanilla executable, and
none overlaps a Fix Patcher patch or a DS Fish site.

## What the player gets

A new **Upgrades** text button in the Supplies store (bottom bar, left of
Buy, at (440, 551)). It opens a second page with four items:

| Item | Price | Kind |
|---|---|---|
| Puffer Fish | $1250 | tank companion, like the Golden Seahorse |
| Sting Ray | $1250 | tank companion |
| Moray Eel | $1250 | tank companion, comes with its rock |
| Exotic Fish Eggs | $2300 | eggs; hatch only DS-exclusive bodies and fins |

Buy and Done work as on the stock page; Upgrades again (or Done) returns.
Store descriptions follow the Golden Seahorse's ("... magically enhances
your environment and the life of your fish. Comes fully installed."). The
exact effects are listed in the Tools tab's Game Mechanics page, not in the
store (the user's call).

## Companions (Puffer Fish, Sting Ray, Moray Eel)

They behave like the Golden Seahorse: they swim in a tank and the player can
drag them between tanks. They are never selected for the isolation tank,
mutated, bred, aged or sold, and they show the seahorse's health and food
meters.

Their meters (owner's request, 2026-10-29): a bought animal has health 100
and food 100, the game's cap for both (0x41E0FE, 0x4121CB) and its full bar
(0x41BF10); earlier builds copied the seahorse's `Random(15) + 80` and 50.
After a save loads (`on_state_load`, after `settle_animals`), every Puffer
Fish, Sting Ray and Moray Eel, and an eel at home in its rock (its spare
bytes), is set to 100 and 100. No code lowers a seahorse-type record's
meters: the age step skips body 22 (0x42043F, so no food loss, health tick
or death), overfeeding skips it (0x4121F4), and only feeding (0x4121A3, +50)
and one supply item (0x42125C) raise them. So filling them on every load
fills each creature once, and no sidecar is kept. The stock Golden Seahorse
gets the same, from Fix Vanilla Bugs (`scripts/pin_vanilla_fixes.py`).

How: each is a fish record built exactly like the Golden Seahorse's
(`0x427DBA`), with the seahorse's body gene 22. So every place the game
special-cases the seahorse applies to it unchanged:
- overfeeding;
- view stage 3;
- never ageing, and the skipped per-step block;
- no mutation, and no isolation tank;
- the sell-tank count;
- the meters, medicines and chemicals.

The animal is marked by its fin gene: 22 Golden Seahorse, 30 Puffer Fish,
31 Sting Ray, 32 Moray Eel. The game's fin tables (`0x411100`, `0x4111E0`)
treat anything above 20 as their default case. Nothing reads a seahorse's
fin except the stage-3 draw. The DLL hooks that draw at `0x414C8A` to pick
the animal's own sheet, centred on the seahorse's 116 x 62 hit box.

### Animal slots: they never take a fish's place

Decided (user): "26 fish + 5 animals". The state already holds 31 fish
records per tank; the stock game uses 21, and "Bigger tanks: 26 fish" uses
26. Every animal, the Golden Seahorse included, lives in slots 26-30, so a
tank full of fish still takes up to 5 animals:
- the two loops that build the swimming view (`0x4140C5`, `0x415893`) run
  to 31 instead of 21 or 26 (the DLL accepts either stock value);
- buying places the animal in the first free slot 26-30 of the tank (else
  another tank), and the stock Golden Seahorse purchase is moved there too
  (`0x427E43`);
- an animal dropped on a tank button moves to that tank's animal slots;
- loading a save (the state's Load at `0x4424D0`) moves animals from older
  builds out of the fish slots, and a new game clears slots 26-30
  (`0x41AACA`).

With "Buy Multiple Golden Seahorses" on, the store animals can be bought
more than once too; with it off, one of each, buyable again after trashing.

### Names

The tank's info panel shows a held fish's species name from the species table
(`0x41D980` calls `0x419290`); a seahorse-type record has no name there, so
stock code showed nothing for the Golden Seahorse. The DLL hooks that call
(`0x41DA0A`) and, for an animal, returns its name (user): Golden Seahorse,
Magic Pufferfish, Blue-Spotted Stingray, Moray Eel. The store page uses the
same names.

No stock slot loop reaches slots 26-30 (magic fish, medicines, the Unknown
Chemical, the age step), and the DLL's own effects skip seahorse-type
records, so nothing but the animals' placement code ever touches them.

Customers in the selling tank (`0x42426F`) and their thought bubbles
(`0x41355F`) now skip every seahorse-type companion, the Golden Seahorse
included; stock code read their species data out of range.

Owning one of the new animals means it is in a tank (or, for the eel, in its
rock), so a trashed animal can be bought again. The Golden Seahorse keeps
the stock rule.

Art, from the DS session's 3D renders, in the seahorse's 18-frame layout
(faces left, mirrored, turning):

- Puffer Fish: it swims deflated and now and then puffs up while swimming
  (its 4 DS puff frames, in their own sheet, `DS_PUFFER_PUFF_Grid.png`),
  then deflates again.
- Sting Ray: the 8-frame side-view swim.
- Moray Eel: the tailed swimming eel (16-frame swim).

### The eel's rock

Decided (user): the eel **roams** the tank like the other companions, and the
rock is a separate decoration the player drags like the shell or pagoda. Drop
the eel on its rock and it goes home: it disappears from the open water and
the rock plays the DS in-rock animation (eel back layer, rock, eel front
layer), with the head peeking out. While it is home, **moving the rock moves
the eel with it**. Pressing on its head (the cave mouth, rock x 60-115,
y 55-115) pulls it out already held, so the player drags it out of the rock.
At home the eel idles in the cave mouth (DS frames 1-13, forward then back,
one frame every 10 s) and every 30-90 s plays the DS's action burst, frames
14-31 then 0, at 120 ms a frame with the closing bite held 500 ms (user). In
DS frames 15, 21, 26, 27 and 31 the DS shows the eel behind the rock; here its
back layer is merged into the front one, so it is drawn whole in front.

Trashing goes both ways: the eel thrown away takes its rock with it, and the
rock dropped on the trash can asks "Delete this fish?" and takes its eel
(home in it, or swimming) with it.

The rock and the eel's home state need no sidecar:
- The rock is one of the tank's six ornament records (sprite 228 with the
  eel away, 229 with the eel home), saved with the game.
- While the eel is home, the record's spare bytes 1-3 keep its health, its
  food and a 0xE1 flag.
- Going home (detour of the fish drop at `0x41F064`): the DLL removes the
  eel's fish record (`0x418E20`) and drops its view entry (`0x415380`).
- Coming out (detour of the ornament pick at `0x41E570`): the DLL rebuilds
  the record and resyncs the view (`0x415E70`, as after a hatch).
- The two layers are drawn around the stock ornament pass (detour of its
  tail jump at `0x41EF1B`).

The rock goes in the same tank as the eel when there is room, else in the
first tank with a free ornament slot. A purchase with no room anywhere is
refused before paying, with "The tank is full!".

## Effects, rescaled to the PC

DS chances are per DS tick and small; the PC's tick is one age step (5-15
real minutes) with bigger effects. The calibration comes from the two items
both games share: Aeration and Temperature Regulator are 4% and 6% on the
DS and 41% each on the PC, about 8x. Food is scaled the same way against
food loss: the DS drains food at 6.2% per tick with no Food research, and
the PC at 100% per step, about 16x.

| Item | DS (per DS tick) | PC (per age step), in the companion's tank |
|---|---|---|
| Golden Seahorse | healthy, fed fish: 10% chance of +1 health | **keeps** its PC effects (+2 crowd, +2 buy chance) **and adds** 82% chance of +1 health to healthy, fed fish |
| Sting Ray | healthy, fed fish: 10% chance of +1 health | 82% chance of +1 health to healthy, fed fish |
| Puffer Fish | healthy fish with food > 5: 10% chance of food +1 | +1 food, and 60% chance of +1 more, to healthy fish with food > 5 (as on the DS, this outpaces food loss) |
| Moray Eel | a dying fish survives on a roll of 25 (+25 Environment L3) +10 | the PC has no survival roll at all; with an eel in the tank (swimming or home), a dying fish survives with 10% chance, at health 10 |

"Healthy, fed" means no disease and food above 5: the condition the DS uses,
and the PC's own health tick gate at `0x41E0DE`. Each companion in the tank
rolls separately. The health and food effects run right after the game's
own health tick, through the call at `0x420470`. The eel's save detours the
death test at `0x420622`. A companion's effect counts only in the tank it is
in (the DS keeps item flags per tank). The seahorse's PC effects stay
global, as in the base game.

## Exotic Fish Eggs

"These special eggs were extremely hard to obtain. Research FISH ENVIRONMENT
before you try to hatch these." $2300. A green recolor of the Rare Eggs
(store icon and cursor icon).

They behave like the other eggs:
- they go in slot #4: item value 28 (26 is the starter eggs, 27 the store's
  "none"), icon sprite 223, cursor 224;
- the same number of eggs per use: `Random(2) + 3`, +1 with the egg plant,
  +1 on the easiest setting;
- each egg gets a random DS-only body and a random DS-only fin (genes 23-29,
  even odds).

They hatch through a detour of the egg switch at `0x421356`, which reuses
the stock hatch epilogue `0x421437`. The stock confirm text at `0x4281AF`
also treats them as eggs ("Replace eggs in slot #4?").

With the Fix Patcher's "Universal supply slots" setting (its payload knows
item values 0-7 only), the DLL makes Exotic Eggs follow that setting's egg
rules (user: existing patches should cover the new content):
- buying: a stack of Exotic Eggs in slots 2-4 gains one hatch, else the
  first empty slot takes them, else the setting's three "replace?" prompts;
- using: the payload's use trampoline lets item values above 7 through
  untouched at `0x43F593`; the DLL redirects that jump so item 28 takes the
  eggs branch (swapped into slot #4 for the hatch), from any slot;
- hatching takes one from the stack and clears the slot at zero.
The redirect is written only when the payload is in the executable, and the
log says "Exotic Eggs and the hormone use universal supply slots". Without
the setting they stay in slot #4 and a purchase replaces them, as with stock
eggs.
Checked live: two purchases stacked in slot 2 (count 2), two hatches from
slot 2 gave 4 DS babies each time and then emptied it; slot 4's starter eggs
were untouched.

## Radioactive Growth Hormone

Owner's spec (2026-10-30): $10,000, 3 doses, like Plant's Radioactive Plant
Formula; $0 with Free upgrades; the stock Growth Hormone's art recoloured
green; each dose on exactly the fish the stock Growth Hormone reaches.

The stock Growth Hormone (item 3, $380, 3 doses), from the vanilla code:
- bought into slot #3 (state + 0x2F0: item, present, count, shelf icon 0x7A
  TOOL_GROWTHHORMONE.png, cursor 0x7B TOOL_dropper4.png, x 0x7E) by the
  writer `0x427540`, count 3; "Replace chemical in slot #3?" (0xEE) when the
  slot holds a chemical (`0x428172`);
- used by the supply-use handler `0x420B70`: slot #3 is case 2 (`0x420E3A`,
  splash and sound), then the switch on the item at `0x420E72`; item 3 is
  `0x4210F2`;
- targets (`0x421100`-`0x421194`): every record of the tank being looked at
  (state + 0x384) up to `cmp ebx, 0x3528` at `0x42118E` (21 records, 26 with
  Bigger tanks), that is live (+0x00), has health (+0x3C) not 0 and age
  (+0x0C) 40 or less;
- effect: age += Random(5) + 2; unless Hard (state + 0x14 == 2), the
  last-processed age (+0x08) = age - 1; the next fish update 7 s on
  (scene + 0x30, `0x42117D`);
- then a sparkle (effect 0xF) on each live fish on screen (`0x42119A`) and
  the shared tail `0x421302`: one dose spent, the slot cleared at 0.

The Radioactive Growth Hormone is item 29 in the same slot, shelf picture
236 and cursor 237 (lent by DS Fish, which now lends 20 entries, 220-239).
The DLL's site at `0x420E6F` (the switch) sends item 29 to `rgh_dose`, then
into the stock sparkle and tail; every other item goes on exactly as before.
`rgh_dose` walks the same records with the same tests (the loop end is read
from `0x421190`, so Bigger tanks counts too, never past the animals' slots)
and, for each:
- age below 20 (the game's adult age: `0x4200AC`, the sickness roll's
  `0x420498`, sales' `0x42426F`): age 20, and the last-processed age 19
  unless Hard, as the stock hormone writes it; older fish keep their age;
- health 100, the game's maximum;
- sickness (+0x40: 1 fungus, 2 ick, the only values `0x41E120` sets)
  cleared as the medicines clear it (`0x420D1D`, `0x420D57`): +0x40 = 0
  and one more Fish Cured (state + 0x34);
- the next fish update 7 s on, as stock.
Fry are fish records from age 1 (eggs hatch straight into the tank), so they
grow up; eggs on the shelf are an item, not fish. The store animals (the
Golden Seahorse too) live in slots 26-30, past the loop, so neither hormone
reaches them. Buying: as a stock chemical without Universal supply slots
(the DLL's site at `0x428189` also makes buying a stock chemical over it
ask "Replace chemical in slot #3?"); with them, a stack in slots 2-4 gains 3
doses, else the first empty slot, else the three "replace?" prompts, and
the use trampoline's gate sends item 29 to the chemicals (`0x43F5A2`).
Art: scripts/build_growth_hormone_assets.py turns each stock picture's hue
from 0.667 to 0.30 and its saturation x1.25, keeping brightness and alpha;
docs/images/radioactive-growth-hormone-fish.png shows the page and the
pictures. Tests: tests/test_radioactive_growth_hormone.py (emulated: the
purchase, the price, a dose through the vanilla use handler, the countdown,
the stubs). Not yet checked live.

## Store page mechanics

- The Upgrades button is id 3, a 3-frame 100x50 strip. It is added once, on
  the store's first activation, with the stock button sequence (`0x401B10`,
  `0x4015E0`, `0x40A9E0`).
- On the Upgrades page, the store's item-table pointer (`impl+0x28`) points
  at an empty table. The stock grid, the research shelf items and their
  clicks go blank. The background, slot icons, cash text and hints keep
  working.
- The DLL draws the four items and the info panel in the store's overlay
  slot (vtable `0x44C2B0`), does its own hit testing in OnMouse
  (`0x44C298`), and handles Upgrades and Buy in OnCommand (`0x44C2A0`).
- Buy runs the stock confirm dialog (`0x4221A0` / `0x401D00`) and charges
  money and "total spent" as the stock purchase does. The stock buy path's
  jump tables stop at item 25.
- OnActivate (`0x44C2B8`) always returns to the stock page.
- Item names and descriptions come from the DLL in English and German
  (`[[0x45B314]] == 1`). "Price:" and "This is in your inventory." are the
  game's own strings.

## Ownership and saves

Everything is in the game's own save:
- the companions are fish records;
- the rock is an ornament record;
- the eggs are the slot #4 record.

There is no store sidecar.

## Packaging

- A second companion DLL, `DS Store Items.dll`, sits in "Fish Tycoon Fix
  Patcher Files" beside `DS Exclusive Fish.dll`. DS Fish loads it after its own
  install and lends it sprite table entries 220-235 (12 used).
- It writes its own log, "DS Store Items.log".
- The "DS Store Items" setting declares `"requires_settings": ["ds_fish"]`.
  The patcher refuses it on its own, and the GUI ticks DS Exclusive Fish
  with it.
- It writes no executable bytes, so each of its pins equals the same
  combination's pin without it.

## Live checks (2026-10-26, a patched copy of the vanilla game)

- Both logs say "installed (all sites)".
- The store page: the Upgrades button, the page itself, hover and selection,
  the info panel, the price, and "This is in your inventory."
- Buying: the stock "Buy this item?" and "Replace eggs in slot #4?" dialogs
  appear, and money is charged exactly (3 x $1250 + $2300).
- The three animals swim in Tank One, and the rock falls to the gravel.
- The eel:
  - dropped on its rock, it goes home and plays the in-rock animation;
  - moving the rock moves it;
  - a click on its head lets it out at once, with the health it had;
  - the home state survives quitting and reloading.
- Exotic Fish Eggs dragged into the tank hatched 3 babies, all with DS genes
  (bodies 26, 24, 29; fins 27, 23, 26), and emptied slot #4.
- One age step with the Puffer Fish in the tank took the babies' food from
  60 to 61, 60 and 61. The step itself costs 1 food; the puffer gave +1, and
  +1 more to two of the three.
- Animal slots (with "Bigger tanks", a tank of 26 fish): two Puffer Fish,
  the Sting Ray, the Moray Eel and then the Golden Seahorse all went into
  slots 26-29 with the 26 fish untouched; they survived quitting and
  reloading. The puffer puffs up while swimming.
- The eel dropped on the Tank Two button moved to Tank Two's slot 26; thrown
  away there, its rock in Tank One went too. The rock thrown away took the
  swimming eel with it.
- Pressing on the eel's head brought it out held; the harness posts mouse
  messages, and the stock drag follows the real cursor, so the drag itself
  was not watched (the drop worked).
- Not checked in the running game: moving animals out of the fish slots of
  a save from an earlier build, the eel's death save, and the
  selling-tank guards (they are a compare and a jump each, pinned by the
  header script).
