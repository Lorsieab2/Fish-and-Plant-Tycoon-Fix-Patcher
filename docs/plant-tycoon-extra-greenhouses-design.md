# Plant Tycoon: 5 extra greenhouses

One optional Plant Tycoon setting, **5 extra greenhouses** (`extra_greenhouses`,
off by default, in the "Modded Upgrades" copy). It ships one companion DLL,
`Extra Greenhouses.dll`, which the startup loader loads first when the setting
is on; the DLL starts the first of `Greenhouse Counts.dll` (its own setting,
which starts the next two itself), `Unused Flowers.dll` (which starts the
rest) and `Sort Seeds.dll` that is beside it, then installs its own sites, so
it wraps whatever they installed (a vtable slot may hold another companion's
wrapper from the same folder; it is chained). No byte of the executable is patched beyond the
startup loader (`src/ds_fish_loader.py`, `PLANT_GREENHOUSES`).

## What the player sees (the owner's design)

- Six greenhouses of 15 pots (90 pots). The game's own gold arrows
  (`leftarrow.png` / `rightarrow.png`, the ones the Seed Storage screen uses for
  boxes 4-6) at the top of the greenhouse screen page through Greenhouse 1 (the
  stock one) to Greenhouse 6 and round again. "Greenhouse n of 6" is drawn in
  the game's font (the same call the Seed Boxes DLL uses for "Boxes 1-3").
  Picture: `docs/images/extra-greenhouses-switch.png`
  (`scripts/render_extra_greenhouses_preview.py`).
- Every greenhouse is the stock greenhouse screen (background, pots, buttons,
  tray), and the game's own code runs on its pots. No logic is reimplemented
  and there is no new art.
- Moving: drag a plant onto an arrow (as the stock game drags it to another
  pot) and it moves to the same pot place in the greenhouse that arrow leads
  to, or to its first empty pot if that place is taken (which is then shown). A full greenhouse says
  "Greenhouse n is full! There is no empty pot to move this plant to."
- Everything held stays held across the arrows (they do not change screen;
  the stock game empties the hand only when a screen opens: 0x423206 in the
  greenhouse's 0x4231E0, 0x4363C3 in the nursery's 0x4360D0). Pollen and
  seeds taken from a plant keep their own plant (see "Moving things between
  greenhouses"); seed-tray seeds, tools and chemicals belong to no pot.
- Selling: the stock nursery's 15 spots and the stock limit. At most 15 plants
  are for sale at once, counted over all six greenhouses.

## Buying the greenhouses (the owner's change)

Greenhouses 2-6 are bought in order on the store's Upgrades screen, like the
Fourth to Sixth Seed Box, so the setting needs Add new store upgrades and
items (`requires_settings: plant_upgrades`).

- **The item:** "Extra Greenhouse", drawn by `Store Upgrades and Items.dll`.
  - Place: the tool shelf at (404, 50), the fourth tool column, beside the
    Seed Boxes in the fifth. The chemical shelves, where the other branch's
    Revival Potion, Revita-Seed and Formula Bomb go, are left free.
  - Picture: a small, fully opaque greenhouse the size of the shelf's tools,
    drawn at scale 1: row 15 (frame 30) of the mod's
    `Chemicals_Grid_upgrades.png`, made by
    `scripts/build_plant_upgrades_assets.py` from the game's repaired
    greenhouse (`greenhouse2.png`): the building only, cut to opaque and
    shrunk. Its visible part is x 414-451, y 58-111: on the shelf line as the
    seed boxes beside it (their art starts at x 468), inside the click
    rectangle {404, 52, 461, 113}; its shadow and tick are centred under it.
  - v1.0.17 drew the game's `greenhouse1.png` (sprite 0xC2), a 157 x 207
    garden picture with soft, see-through edges, with a 0.29 scale that the
    game's draw does not apply: it came out full size over the seed boxes and
    three shelves. The game's sprite table has one spare record (the Upgrades
    link's), so the icon shares the mod's chemicals sheet, as the Time Warp
    clock and Add Money's coins do.
  - Sold out: the stock tick (sprite 0x25) once all five are owned.
  - Tooltip: "Extra Greenhouse n of 5 / Price: $ 10000", or "Sold out".
- **Buying:** the same Yes / No and "can't afford" boxes as Add Money.
  - $10,000 each, through `price()`, so $0 with Free upgrades.
  - The cash goes through the game's own 0x41ED70.
  - Each purchase calls `FtfpExtraGreenhousesBuy` (one more owned, up to 5).
    The Upgrades DLL finds it with `GetModuleHandleW(L"Extra Greenhouses.dll")`.
- **Locked:** the arrows show only once one is owned, and page only through
  Greenhouse 1 and the owned ones. A plant dropped on an arrow can go only to
  an owned greenhouse. With none owned there are no arrows and no label.
- **Stored:** the owned count is the sidecar header's sixth word. A new game
  sets it to 0. A load reads it, and never locks away a greenhouse that has
  plants.

## Phase 1: where the greenhouse is fixed at 15 pots

Static analysis of the vanilla `Plant Tycoon.exe` (SHA-256 `D1F83E3E…D6F9`).

### The pots

- **Pot records:** `state + 0x2188 + k * 0x5600`, k = row * 5 + column
  (3 rows of 5), 0x50A00 bytes in all. The record holds everything about the
  plant: +0x04 clock stamp, +0x08 accumulated seconds, +0x10/+0x0C age (float),
  +0x18 pot style, +0x20 water, +0x24 health, +0x38 planted, +0x4C foliage,
  +0x50 flower, +0x54.. seed, +0x6C pollinated, +0x9D for sale, +0x9E sold,
  +0xA0/+0xA4 snapshot place, +0xA8 + n * 0x16C branches, +0x55F8 a light fade.
- **Plant manager:** the singleton `[0x493C80]` (0x810A4 bytes, ctor
  0x42F550): +0 state, +4 sprites, **+8 + k * 4 one plant object per pot**,
  +0x44 24 catalogue records and their objects at +0x81044. A plant object
  (0x58 bytes, one class per foliage, factory 0x42EE20, base ctor 0x42C9F0)
  points at its pot record at **+8** and reaches the game only through +0xC
  state, +0x10 sprites and +0x14 graphics. Objects are made lazily from the
  records (0x42F6C0) and rebuilt from them at load (0x42FC40).
- **Manager methods by (row, column):** 0x42F410 empty a pot (memset, style
  Random(6), object deleted), 0x42F660 make an object, 0x42F6C0 get the
  object, 0x42F740 draw a pot, 0x42F870 update all 15 (loop 3 x 5),
  0x42F940 swap two pots (moving a plant), 0x42FA80 Mutation Liquid,
  0x42F4F0 Insta-Grow on a pot, 0x42FC70 plant a seed, 0x42FDE0 draw the 15,
  0x42F630 new game (memset 0x50A00).
- **The save:** body = state + 8 .. + 0x53FB8 (0x53FB0 bytes) behind a 24-byte
  header, written raw by 0x41D120 (0x403690) and read by 0x41EE00, which
  rebuilds the plant objects (0x42FC40 at 0x41EF05). State fields past
  0x53FB8 (+0x63E4C the next update, +0x63E58 the selected pot) are not saved.
  The save has no room: a second set of pots needs 0x50A00 bytes and the whole
  body is 0x53FB0.

### Every loop over the pots

| Code | What | Runs |
|---|---|---|
| 0x41D810 → 0x42F870 | the plant update: each pot's object `vtable[1](now)` = 0x42DF80 (age, water, health, pests, flowers, seeds, old age, death, "discovered" 0x41EB00) | greenhouse tick 0x428BAD every 61 s and at entry, Options 0x42C261.., Time Warp |
| 0x41D6E0 | a new game's four starter seeds, grown 4800 s | new game |
| 0x41D3D0 | new game: pots cleared (0x42F630), styles Random(6) | new game |
| 0x4231E0 | greenhouse activate: sold pots emptied (+0x9E and +0x38) | entering the greenhouse |
| 0x427960 | greenhouse buttons: 6 toggle for sale (selected pot), 7 info, 9 all / none for sale (all 15) | greenhouse |
| 0x426040 | a click on a pot with the held item; chemical switch at 0x4266A6 (table 0x4273A8, chemicals 27-35; cases 5 and 8 reach all 15 pots) | greenhouse |
| 0x425810 | drop: move (0x42F940), pollen (0x4240A0 at 0x425F54), seeds | greenhouse |
| 0x428E70 / 0x42FDE0 | draw | greenhouse |
| 0x428810 | tick: update clock, bugs, the light fade loop | greenhouse |
| 0x417D50.. 0x4180F0 | bug arrivals (Random pot) | greenhouse |
| 0x423630.. 0x424880 | pot info, selection, seed box send (0x4245F0) | greenhouse |
| 0x42FFE0 / 0x430550 | the plant info dialog | greenhouse |
| 0x4360D0 | nursery activate: visitor limit 0x43FF00 (2 per plant for sale) / deactivate: sold pots emptied | nursery |
| 0x436BE0 | the buy roll over the 15 spots (spot k = pot k) | nursery tick 0x437950 |
| 0x435C70 | a sale (+0x9E, cash) | nursery |
| 0x436531 | rearranging the nursery (0x42F940) | nursery |
| 0x439820 | visitor comments | nursery |
| 0x448B60.. | the snapshot (F1) | snapshot scene |

Nothing outside the greenhouse, the nursery and the snapshot reads a pot, and
nothing anywhere reaches a pot except through `state + 0x2188 + k * 0x5600` or
a plant object's +8. The nursery has no array of its own: its 15 spots are the
15 pots, so the stock for-sale limit is 15.

### The approach: the DLL's pots, moved in for each screen

Extending the arrays is impossible (the save has no room, and the manager and
every loop are sized 15). So the DLL keeps 75 more pot records and their plant
objects, and moves the pots each screen should see into the game's 15:

- the greenhouse screen: the greenhouse on screen;
- the nursery: Greenhouse 1's pots, with the other greenhouses' plants for sale
  moved into its free spots (never more than 15);
- the snapshot: the greenhouse that was on screen;
- every other screen, every save and every load: Greenhouse 1 alone, the
  stock layout.

A move exchanges two records and their plant objects (each object re-pointed
at its new record; one that does not point where expected is deleted and the
game rebuilds it). Moves are undone exactly in reverse, so each pot position
keeps its greenhouse: the game's own code can still move plants between pots
(the stock drag, the nursery's rearranging), and a plant moved that way stays
where the game put it.

The plant update is wrapped: it runs the stock update for Greenhouse 1, then
moves each extra greenhouse in and runs the stock update again, with the same
clock. So every pot gets the stock update at the stock times, whichever
screen is up, and time away is caught up from each pot's own clock.

### Sites (`native/ftfp_extra_greenhouses/greenhouse_sites.h`)

Generated and checked by `scripts/build_extra_greenhouses_headers.py` (stock
instructions, no branch target inside, no overlap with a Fix Patcher patch or
a New Flowers, Plant Upgrades or Seed Boxes site). All 29 writes are checked
first and written all or none.

| Site | VA | What |
|---|---|---|
| plant_update | 0x41D810 (8 bytes) | the update of all six greenhouses |
| save_write | 0x41D156 (9 bytes) | before the game writes a slot: Greenhouse 1 in, the sidecar written; after: the screen's pots back |
| load_done | 0x41EEFE (12 bytes) | after a load: the sidecar read (or empty greenhouses), layout reset |
| new_game_clear | 0x41D3DC (call) | a new game empties every greenhouse |
| delete_slot | 0x415F5E (call) | deleting a slot deletes its sidecar |
| pollinate_call | 0x425F54 (call) | pollen carried from another greenhouse keeps its donor |
| seed_plant | 0x425C1B (7 bytes) | carried seeds planted: the seed record of the plant they came from |
| seed_box | 0x42819B (7 bytes) | carried seeds into the seed box: the same |
| seed_trash | 0x424711 (7 bytes) | carried seeds in the trash: their own value (+0x74) |
| seed_return | 0x424508 (6 bytes) | carried seeds put back: to their own pot (+0x90 + 1, +0x94 - 1, as 0x424480) |
| greenhouse vtable | 0x469224, 0x469228, 0x46922C, 0x469238, 0x46923C, 0x469240, 0x469244 | mouse (drop on an arrow), keys, command (arrows, the for-sale limit), overlay, draw (the label), tick, activate (the arrows; other greenhouses' sold pots emptied through 0x42F410) |
| nursery vtable | 0x469734, 0x469738, 0x46973C, 0x469748, 0x46974C, 0x469750, 0x469754 | the nursery's pots |
| snapshot vtable | 0x46988C, 0x469890, 0x469894, 0x4698A0, 0x4698AC | the snapshot's pots |

A vtable slot may hold the stock function or the wrapper of another companion
DLL from the same folder (which is then chained).

The Time Warp (`Store Upgrades and Items.dll`) calls the DLL's
`FtfpExtraGreenhousesWarp(dt, now)` after it moves the stock pots' clocks, so
the extra pots' clocks move by the same rule before the update.

## The nursery limit

- Button 6 (put the selected plant up for sale) is refused with "Your nursery is
  full! Only 15 plants can be for sale at once, counting every greenhouse."
  when 15 are already for sale in all six greenhouses; taking a plant off sale is
  never refused.
- Button 9 (all up for sale) runs the stock code, then takes back the plants it
  just put up for sale, last first, until 15 are for sale, and says so.
- The nursery shows exactly the plants for sale (at most 15), so the visitor
  limit, the buy roll, the prices and the comments are the stock game's.

## 5 extra nurseries (a second setting)

"5 extra nurseries" (`extra_nurseries`, EXPERIMENTAL - USE AT OWN RISK, off
by default, needs `plant_upgrades`) ships the same DLL with "Extra
Nurseries.ini"; "5 extra greenhouses" ships it with "Extra Greenhouses.ini".
Each .ini turns its half of the DLL on, so either setting works alone. With
either one on, the startup loader loads the DLL.

**How the stock game limits sales.** There is no separate cap. The nursery's
15 spots are the 15 pots: the buy roll (0x436BE0, from the nursery tick
0x437950) walks spots 0-14, and a sale (0x435C70) marks pot k sold. The
visitor limit (0x43FF00, run as the nursery opens, 0x4360D0) counts 2 per
pot for sale. So the limit is 15, one per spot.

**The design, the most faithful one: more nurseries, each a stock nursery.**
A bigger nursery would need a new screen layout and a second buy roll. Each
extra nursery is instead the same stock screen with 15 spots, run by the
same code:
- **Which plants go where:** the plants for sale fill the nurseries in
  order. Nursery 1 first: a Greenhouse 1 plant keeps its own pot's spot, as
  in the stock game, and the other greenhouses' plants take the free spots
  in home order (greenhouse by greenhouse, pot by pot). Then Nursery 2, and
  so on.
- **What is in the state:** nursery n moves its plants into the state's 15
  pots. A spot with no plant of that nursery gets an unsold pot from the
  DLL's places, so it shows nothing for sale.
- **Positions:** to make this possible, the DLL tracks all 90 pot places
  (`at_pos` / `where_home`). Any place can be moved into any state spot, and
  every move is taken back, last first.
- **Switching:** the stock gold arrows (ids 40/41 on the nursery scene, at
  220/530 in the sky band) and "Nursery n" in the game's font. A switch only
  rearranges the 15 pots (the owner: switching must not reset the customers).
  It does not close or reopen the nursery, and the nursery scene and its
  visitor list are not touched, so the visitors, their timers, the visitor
  limit and the browsing count all stay.
  - Why it is safe: no visitor holds a plant. A comment picks a stand and
    reads its plant at that moment (0x4399D5), the buy roll goes stand by
    stand, and a sale pays and marks its pot at once.
  - A plant held to rearrange the nursery is put back first, as the stock
    close does (0x4363C3).
  - Sold plants keep their stand on their own nursery. When the nursery
    closes, the stock close empties the screen's sold pots and the DLL
    empties every other nursery's.
- **Limit:** 15 × (1 + nurseries owned). Button 6 refuses the next one with
  "Your nurseries are full! Only N plants ...", and button 9 stops at the
  limit.
- **Bought:** the Extra Nursery item on the Upgrades screen's Nursery shelf at
  (440, 296), drawn with the game's own golden pot (sprite 0x2C, the
  nursery's display), $10,000 each, in order. The count is the sidecar
  header's seventh word; a new game resets it.
- **All bought nurseries sell at once** (the owner's choice, after the Fish
  extra tanks):
  - When it runs: the nursery tick's buy roll (the call at 0x437A1C of
    0x436BE0, every 2 seconds, only on the Nursery screen; the stock game
    sells nowhere else) runs for the nursery on screen.
  - Each other nursery: its plants are moved into the 15 spots for one call
    of the same roll, with the same visitors browsing.
  - Visitors: they belong to the screen. During those calls the sale's
    visitor count (0x43ACD0 at 0x435D21) reads 0, so no visitor carries the
    plant off. The sale ring (nursery + 0x10..0x57) is put back, so no "+$"
    shows on the screen's plants.
  - What a sale does: it is the stock sale, so it pays, counts and marks its
    own pot sold.
  - Spots: a sold plant keeps its spot until the nursery closes, so no other
    plant moves.
  - Visitor limit: computed from the screen's nursery only (at most 15
    plants), so it never passes the stock maximum.
  - No nursery bought: this is exactly the stock roll.

Pictures: `docs/images/extra-nurseries-switch.png`,
`docs/images/extra-greenhouses-store.png`.

## Screen names

Every greenhouse screen draws "Greenhouse n" and every nursery screen
"Nursery n" in the game's font. The stock screens show them too ("Greenhouse
1", "Nursery 1"), and " of m" is added once more than one is owned. The
glyphs are checked against the font table (0x47A550) by
`scripts/render_extra_greenhouses_preview.py`.

## Moving things between greenhouses

The cursor's item is `state + 0x56C`: 1-4 tools, 5-8 the chemical tray,
9 pollen (0x42631F), 10-19 the seed tray (Legendary Seeds too), 0x14 seeds
taken from a plant (0x426228), 0x3E8 + k a plant (pot k). The arrows do not
open a screen, so the stock rule (the hand is emptied only when a screen
opens: 0x423206, 0x4363C3) keeps everything held:

| Held | Across an arrow |
|---|---|
| a plant | dropped on an arrow: moved to the same pot place there, else the first empty pot (stock-style box when full); clicking an arrow while dragging leaves it in its pot |
| pollen | carried; the drop's donor (0x425F54) is the plant it came from |
| seeds from a plant | carried; planting (0x425C1B), the seed box (0x42819B) and the trash (0x424711) read the source plant's seed record, and putting them back (0x424508) returns them to it. Taking them already moved one seed from the pot's +0x90 to +0x94 (0x42625D), exactly as stock |
| seed tray, tools, chemicals | stay held; they belong to no pot and work on the new greenhouse's pots |

Ornaments are never placed (each counts once bought), so nothing moves.

## The sidecar

`<Documents>\LDW\<exe name>\Plant Tycoon Fix Patcher Data\Extra Greenhouses <slot>.dat`:
a 24-byte header (magic `PTXG`, version 1, greenhouses 5, pots 15, bytes per
pot 0x5600, greenhouses owned 0-5) and the 75 pot records. Written with every save of the slot to
`.tmp`, flushed and renamed over the old file; read at load. A file of the
wrong size or header is renamed `.unreadable` and never overwritten. No file
means empty greenhouses (a save from before the setting).

## Tests (`tests/test_extra_greenhouses.py`)

All in Unicorn on the vanilla executable and the DLL rebuilt from source, with
plants made and grown by the game's own code:

- every extra greenhouse's pot ticks byte for byte like a stock pot with the
  same plant (three plants, ten updates with long absences, through to death);
  a full greenhouse of 15 likewise; the Time Warp likewise;
- each effect family gives the stock result in every extra greenhouse: the nine
  chemicals of the switch (both bombs included), pollination, pollen carried
  across greenhouses, moving a pot, emptying a pot;
- moving plants over the arrows (and round from 1 to 6), a full greenhouse;
- the arrows page 1 → 6 → 1;
- the for-sale limit with all six greenhouses full: the 16th refused in every
  greenhouse, "all" stops at 15, the nursery shows the 15 and puts every plant
  back;
- the sidecar round trip with Greenhouse 5 on screen during the save (the save
  holds the stock layout), an unreadable file, no file;
- all sites written, or none when one site differs;
- manifest: the setting, its pinned DLL, the loader, every pinned combination.

## What only the live game can confirm

- The arrows' and label's places (`LEFT_X`, `RIGHT_X`, `ARROW_Y`, `LABEL_X`,
  `LABEL_Y`) against tall plants and the screen's own controls.
- That a drop on an arrow reaches the scene's mouse handler (message 3, the
  button-up) before the arrow button sees it.
- The one-button box text layout.
- Live play across saves, loads, Alt-F4 (an Alt-F4 never saves, so the
  sidecar and the save stay matched), and the other companions together.

## Limits

- The two bombs reach the 15 pots of the greenhouse they are used in, as in the
  stock game (one greenhouse per dose); they do not reach the other five.
- Bugs come to the greenhouse on screen only (stock: only while you are in the
  greenhouse).
- A plant held on the cursor stays in its pot when you click an arrow
  (moving it is the drag onto an arrow).
- Like the other sidecars, the file follows the slot number, not the game's
  backup copies.
