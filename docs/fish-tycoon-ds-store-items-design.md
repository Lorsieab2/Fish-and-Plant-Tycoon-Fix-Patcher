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

### Animal records: they never take a fish's place

Decided (user): "30 fish + 5 animals" (earlier "26 fish + 5 animals"). The
state holds 31 fish records per tank; "Bigger tanks: 30 fish" uses 30 of
them for fish. So the animals, the Golden Seahorse included, have 5 records
per tank of their own, in the DLL, and a tank full of fish still takes up to
5 animals:
- the swimming view: the two loops that build and refresh it go on, at their
  `jl` back to the top (`0x4140D0`, `0x41589E`), from the last fish slot to
  the tank's animals. Each animal's entry carries the one slot number for
  which the game's own `state + 0x390 + tank * 0x51EC + slot * 0x288` lands
  on its record in the DLL, so every stock path that follows an entry
  (draw, move, feed, pick up, drop, trash, the info panel) works on it
  unchanged (docs/fish-tycoon-tank-expansion.md 6);
- buying places the animal in the tank's first free animal record (else
  another tank), and the stock Golden Seahorse purchase is moved there too
  (`0x427E43`);
- an animal dropped on a tank button moves to that tank's animal records;
- a new game clears them (`0x41AACA`).

**Saved beside the save.** "Fish Tycoon Fix Patcher Data\Tank Animals
<slot>.dat" (next to DS Fish's "DS Fish <slot>.dat"), written whenever the
game saves that slot, before the game writes its own file: the state's
Save(slot) `0x419100` is reached through its vtable slot `0x4424D4` and its
two calls `0x41A663`, `0x41A66B`, all three pointed at the DLL first. The
file is written atomically (a .tmp file, flushed, moved over the old one,
which becomes `.previous.dat`), then read back and compared. Its header
names the save it belongs to (money, money spent, sessions and minutes
played, as saved):
- the same save: its animals load (or the `.previous` file's, when the
  game's own save did not finish after the file was written);
- an earlier point of the same save (played and saved since with DS Store
  Items off; sessions and minutes only grow): its animals come back;
- anything else (an older save restored from a backup, a new game in the
  slot, a damaged file): the file is set aside (`.other-save-<n>.dat`,
  `.unreadable-<n>.dat`), never deleted, and the save has no animals.

**The one-time move.** Loading a save from an earlier build (the state's
Load at `0x4424D0`), whose animals are in fish records (26-30, or very early
builds' among the fish): they are copied into the animal records, the file
is written and read back, and only then are those fish records cleared
(REMOVE_FISH, and the mark). If the file cannot be written, the records
stay as they were (the view skips them, so nothing shows twice) and the next
save tries again, clearing them only once the file is written; the game's
own file still has them until then. Loading the same save again moves the
same animals and writes the same file. Checked on copies of the owner's
51 Fish Tycoon saves: every animal moved, nothing else in any save changed,
and a second load gave the same result.

With "Buy Multiple Golden Seahorses" on, the store animals can be bought
more than once too; with it off, one of each, buyable again after trashing.

### Names

The tank's info panel shows a held fish's species name from the species table
(`0x41D980` calls `0x419290`); a seahorse-type record has no name there, so
stock code showed nothing for the Golden Seahorse. The DLL hooks that call
(`0x41DA0A`) and, for an animal, returns its name (user): Golden Seahorse,
Magic Pufferfish, Blue-Spotted Stingray, Moray Eel. The store page uses the
same names.

No stock slot loop reaches the animal records (magic fish, medicines, the
Unknown Chemical, the age step run over the fish slots only), and the DLL's
own effects skip seahorse-type records, so nothing but the animals'
placement code and the swimming view ever touches them. Their effects reach
every fish in their tank: the effects run from the per-fish health tick,
which visits all 30 fish slots with Bigger tanks.

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
log says "Exotic Eggs and the store chemicals use universal supply slots". Without
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
  `0x420498`, sales' `0x42426F`): age 20, and the last-processed age 19 on
  every difficulty (the stock hormone skips this on Hard; the owner,
  2026-10-30: the fish stay healthy on Hard too), so the next update runs
  one step's checks; older fish keep their age;
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

### Owner changes (2026-10-30): every fish, and instant births

The Radioactive Growth Hormone now reaches every live fish in the tank on
screen, any age (`gh_reaches`: live, health not 0, not a marked store
animal), over the stock loop's records (read from `0x421190`; no longer
clamped at 26, since marked animals are skipped). The stock Growth Hormone
is untouched. Each dose:

1. **Births.** Pregnancy in the record: `+0x10` the due age (0 = not
   pregnant, set at mating), `+0x14`/`+0x18` the father's body and fin,
   `+0x1C`-`+0x38` the grandparents. The update gives birth at
   `0x420113`-`0x4203DD` when the due age is below the age and the tank is
   not tank 3 (`cmp [esp+0x10], 3` at `0x42013D`, byte `0x420141`): with a
   Magic Fish of kind 5 (`0x41DE90(5, tank)`), Random(100) <= 15 mutates
   the father's genes (Random(100) <= 49: his body +1, or -1 at 20 or on
   the other half unless 0; else the same test on his body but his fin
   changes, a stock quirk), clamped 0-20; then NewBaby `0x41FA30` (one
   AddFish `0x419C50`: no room, no baby), one more with a Magic Fish of
   kind 0 (`0x4202D9`), one more with the Plant of Fertility (state +
   `0x1A4`, `0x420356`); the baby's age is age - due age; `+0x10` = 0
   (`0x4203D2`). `stock_birth` is that code call for call, so the same
   rolls give the same litter (tested against the vanilla block run in the
   emulator). Babies from a dose are aged 1, as a birth on the due step.
   The view is synced after births (`0x415E70`, as after a hatch).
2. **Age-up**, on everyone reached, the newborns included, so the whole
   litter comes out adult; older fish keep their age.

## Revival Potion (item 30)

$10,000, 3 doses, slot #3 like the hormone (shelf sprite 239, cursor 240,
the owner's amber flask; the store picture 238). The switch stub at
`0x420E6F` sends items 29-31 to `new_chemical`, then the stock sparkle
(`0x42119A`) and tail (`0x421302`).

How the game stores a dead fish: only health (`+0x3C`) 0. The death test
(`0x420622`) sets the age to the step it died on (`0x420634`) so the step
loop ends; the record stays live (`+0x00` kept) until the player throws it
away: no timer removes it. Every update skips it (`0x41FEC3`), so its clock
(`+0x00`, set at `0x41FFCA`), banked seconds (`+0x04`), age, food and
sickness freeze. The view draws it dead (`0x4146BF`, `0x4146F6`,
`0x414778`), sinks it (`0x411D5F`) and stops swimming it (`0x414337`), all
from that health test.

A dose, for every record of the tank on screen the update reaches (slots:
byte `0x4206B3`, tanks: byte `0x4206C7`) that is live, at health 0 and not
a marked animal: health 100, and `+0x00` = STATE_NOW (`0x4032C0`), so the
next update does not play the time it lay dead as time away. Age, food,
sickness, pregnancy and the bank stay.

## ClonaFish (item 31)

$2,500, 3 doses, slot #3 (sprites 241-243, the owner's magenta bottle). A
unique fish is live with health above 0, not a marked animal nor a
seahorse-type record, and no other such fish in the tank has both its body
(`+0x4C`) and fin (`+0x50`). The unique fish are found first, copied whole
(0x288 bytes); then each, in slot order, goes through AddFish `0x419C50`,
which is a plain copy into the first free record under its limit (`cmp
eax, 0x15` at `0x419C72`) and answers -1 when full: the dose stops there.
A record has no slot number or id of its own, so the clone is exact. New
fish are synced to the view; if not one clone fitted, the game's hint 6
("The tank is full!") shows. The dose is spent either way (stock order).

## For the integrator: expansions

Every loop reads the game's own bounds, so the expansion branches only need
to keep using them:

- `UPDATE_SLOTS` (byte `0x4206B3`, the update's slot count; Bigger tanks
  writes 26) bounds the Revival Potion and ClonaFish's search; AddFish's own
  byte (`0x419C74`) bounds where clones go. A 30-per-tank build must write
  both (as Bigger tanks does) and keep the store animals marked (`+0x14` =
  "FTCA"), which every new loop skips.
- `GH_LOOP_END` (`0x421190`) bounds the hormone; a 30-per-tank build should
  rewrite it as Bigger tanks does.
- `UPDATE_LAST_TANK` (byte `0x4206C7`) bounds the tank on screen; extra
  tanks that are updated by the game's loop are reached. An extra-tanks
  build that keeps its tanks elsewhere (not `state + 0x390 + tank * 0x51EC`)
  must be checked: the potions address tanks as the game does.
- Check: tests/test_revival_potion.py and test_radioactive_growth_hormone.py
  patch these bytes (26, 30 slots; tanks 0-5/0-6) and must pass on the
  merged build.

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

- the companions: "Tank Animals <slot>.dat" beside the save (above);
- the rock is an ornament record, in the game's save;
- the eggs are the slot #4 record, in the game's save.

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
- Not yet checked in the running game (emulated only, tests/test_ds_store_animals.py):
  the animals' own records and "Tank Animals <slot>.dat" (2026-10-30). The
  live checks above were made when they sat in records 26-30.
