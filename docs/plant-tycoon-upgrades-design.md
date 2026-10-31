# Plant Tycoon: Add new store upgrades and items

One optional Plant Tycoon setting, **Add new store upgrades and items**
(`plant_upgrades`), built on **Add unused flowers** (`new_flowers`,
`docs/plant-tycoon-new-flowers-design.md`). It ships two companion DLLs:

| Companion DLL | What | Loaded by |
|---|---|---|
| `Store Upgrades and Items.dll` | the store's Upgrades view, Legendary Seeds, the formula, the boxes' purchase | `Unused Flowers.dll` |
| `Extra Seed Boxes.dll` | the Fourth-Ninth Seed Box: the second and third chests and the greenhouse overflow | `Store Upgrades and Items.dll` |

The setting writes no byte of the executable. Each DLL sits in
`Plant Tycoon Fix Patcher DLLs` beside the one that loads it, and each writes
its own sites (all of them or none, after checking every one holds its
vanilla bytes) and logs the result to `<name>.log` in that folder. Every pin
with the setting is therefore the same as the pin without it
(`scripts/pin_plant_upgrades.py`).

## What the player sees (the owner's design)

- An **Upgrades** link on the teal bricks at the left of the Supplies store, set
  in the game's own font at 80% of the shelf-sign size, white, yellow on hover.
- It opens a **separate view of the store** with only the new items, each where
  it would sit in the stock store. The link is hidden there; the bottom bar's
  **Supplies** plate leads back, and leaving the store always resets to the
  stock view.
  - **Legendary Seeds** (seed shelves, lower right): three packets a day, $5000
    each. Any foliage with one of the 14 new flowers (genes 24-37). The art is
    each foliage's Extinct seed recoloured prismatic (a diagonal hue sweep plus
    each pixel's own hue, brightness kept, so the details stay visible). The
    stock packets keep their stock rolls, so only these can grow the new
    flowers. Dialog: "These ultra-rare seeds were only recently rediscovered
    on Isola and require the best of care to survive."
  - **Radioactive Plant Formula** (chemicals, upper right): chemical id 36,
    $10,000, 3 doses. Icon: the Mutation Liquid bottle, prismatic on its
    coloured parts only. On a plant: full health, every dead (brown) branch
    alive again, and every branch the plant's shape hides (type 2) grown too,
    size 110 (the largest), full bloom (grown to age 28 through the Insta-Grow
    mechanism), and the one-time age-7 branch-death roll switched off. A dead
    plant stays dead, as with the stock cures.

    Decided (user): "max insane flowering", beyond spamming the Fertilizer
    Bomb and Bio-organic Plant Food 100 times. Those stop where the plant's
    shape stops: a part definition (0xF4 bytes in its family's shape table)
    lists 0-6 flower spots, most of them on joints, and a spot on a joint is
    taken while a branch grows there (`0x42D330`). So the formula:
    - fills every part definition's empty spots up to 6 (leaves too; spots
      the artists left unused past the count are kept). The header script
      places each one on the part's own visible pixels in its sheet (def
      +0x08, box +0x14..+0x20), up to 2 px inside the outline and as far as
      possible from the others; a thin stem gets a smaller margin, and a part
      with no visible pixels its pivot, so no slot is ever empty (a flower on
      an empty spot would draw far from its plant). The DLL writes them into
      all 23 shape tables at start-up;
      the draw reads a flower's spot by index without checking the count, so
      the flowers draw after a restart too;
    - raises every count to 6 only while it flowers the plant, and restores
      them, so stock flowering and the stock items are unchanged;
    - answers "free" for every spot while it flowers (hook at `0x42D330`);
    - always gives 5 seeds (owner, 2026-10-31). Pollination (`0x4240A0`)
      sets `+0x6C`, `+0x98` = the age, `+0x90` = 0 ripe and `+0x94` = the
      seeds counted as taken already (Random(3) - `+0x7C`: 5, 4 or 3 given;
      4 if infested); ripening (`0x42E0C6`) makes
      min(age - `+0x98` - 2, 5) - `+0x94` ripe each update. On a pollinated
      plant the formula gives back the held-back seeds (`+0x94` = the seeds
      picked), sets `+0x98` = age - 7 so the game's ripening counts all 5
      ripe, and `+0x90` = 5 - `+0x94` at once. On any other it marks `+0x7C`
      ("RFS5"), and `on_pollinated` then gives all 5. The new site
      `plant_seed` (`0x42FCDD`, in planting `0x42FC70`) sets a new plant's
      `+0x7C` to 0, so the mark never passes to the pot's next plant; the
      mark is in the pot record, so it moves with the pot when Extra
      Greenhouses exchanges records. Before this fix the formula only gave
      back held-back seeds, still ripening over 7 units, and a plant
      pollinated later got the stock 5, 4 or 3;
    - then adds flowers until no spot is left (`0x42ED60(360, 0)`).
    Live: a rose bush went from 5 flowers to 276, a 37-branch plant from 4 to
    276, and every one of the 14 new flowers from a handful to 39-132.
  - **Fourth, Fifth and Sixth Seed Box** (seed-box column of Tool Upgrades,
    upper left): $1000 each, "Even more space for your
    seeds!", stock seed-box art at the stock places with the stock tick once
    owned. Bought in order, through the stock dialog and its messages.
  - **Seventh, Eighth and Ninth Seed Box** (owner, 2026-10-30): $1000 each as
    the Sixth, the same description, the Fourth-Sixth's art (Tools_Grid frames
    4, 9, 14) in their own column at (322, 50 / 111 / 172), drawn at scale 1:
    the art is visible over x + 6 .. x + 76, so it ends at 398, 16 px before
    the Extra Greenhouse's art (414) and the Automatic Sprinklers' (415), as
    the Fourth's starts 17 px after the greenhouse's. Click rectangles
    (332-389, 52 + 70 r .. 113 + 70 r) touch no other item's. Bought after the
    Sixth, in order (below). Mockup: `docs/images/seed-boxes-7-9-store.png`,
    composited from the DLL's own draw calls by
    `scripts/render_seed_boxes_preview.py`.
- The stock seed box is one 120-seed chest of three 40-seed drawers (First,
  Second, Third Seed Box). The new boxes are a **second chest** (the Fourth to
  Sixth) and a **third chest** (the Seventh to Ninth) with the same three
  drawers. Once the Fourth is owned, the stock gold arrows (`leftarrow.png` /
  `rightarrow.png`) on the Seed Storage title bar step through "Boxes 1-3",
  "Boxes 4-6" and "Boxes 7-9" (right forwards, left backwards, round again),
  skipping a chest with no box yet. The title bar had room for no more box
  controls (the Sort Seeds button at 396, the label at 660), so the third
  chest is one more page on the same arrows rather than a new tab. Each box
  opens one drawer. Mockup: `docs/images/seed-boxes-7-9-storage.png`.
- The greenhouse knows the new boxes: a seed sent to the seed box goes to the
  first free slot of boxes 1-3, then of boxes 4-6, then of boxes 7-9, and
  "Your seed box is already full!" only comes when all are full.

## Art (`scripts/build_plant_upgrades_assets.py`)

The stock sheets are never replaced. The DLL points the game's sprite records
at taller copies:

| File | Sheet | What |
|---|---|---|
| `Images/seed_grid_legendary.png` | 0x2E (record 0x485F48) | `seed_Grid.png` (16 x 6 of 50 x 50) plus two rows; frame 95 + foliage = that foliage's Legendary seed |
| `Images/Chemicals_Grid_upgrades.png` | 0xB3 (record 0x4875A0) | `Chemicals_Grid.png` (2 x 9 of 70 x 70) plus a 10th row: the formula upright and pouring |
| `Images/upgrades_link.png` | 0x8B (the table's spare last record, 0x4882D4) | the link, 2 frames of 64 x 17, set from `PTfontsmall.png` with the glyph table at 0x47A550 |

Sprite records are `{id, file, +8, +0xC, columns, rows, ...}` (0x34 bytes, table
0x4855F0, 222 records); an image loads on first use and frames past the last
row are clamped (0x409EE0), so without the mod a Legendary seed shows as a
stock packet and the formula as the Vaporbomb.

## The Upgrades DLL: sites (`native/ftfp_plant_upgrades/upgrade_sites.h`)

Generated and checked by `scripts/build_plant_upgrades_headers.py` (stock
instructions, no branch target inside, no overlap with a Fix Patcher patch or
a New Flowers site).

| Site | VA | What the stub does |
|---|---|---|
| roll_tail | 0x41DDDA | after the daily seed roll (and a new game's): roll the three Legendary packets |
| dialog_entry | 0x430950 | purchase-dialog helper: index 52-54 rides the Extinct seed path (6-8), 36 the Vaporbomb path (35), each with a flag |
| dialog_picture | 0x430827 | the dialog's packet picture for 52-54 |
| price_buyable / price_poor / price_tray_full | 0x430CA8 / 0x431015 / 0x43136E | $5000 instead of $2000 while a Legendary dialog is built |
| dialog_done | 0x433240 | clears both flags right after the helper |
| buy_seed | 0x432D45 | Buy: the Legendary packet to the first free seed-tray slot, cash charged |
| chem_price | 0x432716 | the formula's price, and room for chemical 36 in the tray |
| chem_doses | 0x432E43 | 3 doses per purchase |
| chem_apply | 0x4266A6 | chemical 36 on a pot runs the formula, then the stock tail (sound, keep or drop the bottle) |
| tray_name_greenhouse / tray_name_store | 0x4277B4 / 0x4484AA | the tray tooltip names chemical 36 |
| string_lookup | 0x44CA70 | the mod's texts (string ids 0x1F0-0x1F4, and 0x11D/0x11E, 0x165/0x166 under the flags) |
| store_activate | 0x446D40 | builds the mod's tooltips once; every activation starts on the stock view |
| store_draw | 0x447DA2 | draws the link, or the Upgrades view instead of the stock grids (then 0x447FF8) |
| store_click | 0x448173 | button-down: the link, the Supplies plate, the Upgrades items (the dialog is run from the DLL: ctor 0x432E90, modal 0x401C90, dtor 0x4307A0) |
| store_hover | 0x448433 | hover for the link |
| trash_drop | 0x425FF2 | the greenhouse mouse-up's `call 0x424680` (the stock trash): a held chemical 36-39 let go on the bin is thrown away (tray record present byte 0, held 0, sound 0x23), else the stock trash |
| trash_press | 0x4272DC | the press off the pots: the same for a held chemical 36-39 pressed on the bin, ending through 0x42739C, so the selected plant is never asked about or emptied |
| joint_free | 0x42D330 | "is this flower spot free?": every spot answers free while the formula flowers |
| plant_seed | 0x42FCDD | planting: a new plant's formula mark (+0x7C) starts at 0 |
| unit_top / units_done | 0x42E134 / 0x42E2DF | Automatic Sprinklers and the Auto-Healer, each age unit and after the loop (below) |
| dead_untag | 0x42DF91 | the plant update's dead-plant untag: remembers a plant was for sale (+0x9F) for the Revival Potion (below); a dead plant loses the formula's 'R' mark |
| sale_record / sale_cash | 0x435CF2 / 0x435D12 | a visitor's purchase (0x435C70): a plant treated with the formula pays its species' highest selling price into Money Earned and the cash (below) |
| chem_picture_bound | 0x4308D3 | immediate 0x24 -> 0x28: the dialog draws chemicals 36-39 |
| seed/chem sheet records, link record | 0x485F4C, 0x485F5C, 0x4875A4, 0x4875B4, 0x4882D4 | the sprite records above |

The Fourth-Sixth boxes are sold through the stock tool-upgrade dialog: while
one of their dialogs is open, tool records 4, 9 and 14 (`state+0x6E8+k*0x20`,
the stock seed-box drawers) describe the new boxes (price, owned byte, title
and description ids), so the stock code checks "already have it", "needs the
previous upgrade" and the cash, and Buy sets the owned byte. The stock
records are restored when the dialog closes.

The Seventh-Ninth go through the dialog of tool record 9 (index 19): the
helper 0x430950 takes a tool record's row and column from the index
(index - 10 = row x 5 + column) and, for row 1 and below, refuses with
"You need the previous upgrade first!" (string 0x1B1) unless record k - 5 is
owned (`cmp byte [ecx + 0x64C]`, 0x4319A1). So record 4 describes the box
before (the Sixth, Seventh or Eighth: its owned byte) and record 9 the box
being bought (price, owned byte, title 0x1F8-0x1FA, description 0x1F4); Buy
(0x432D00, button 3) sets record 9's owned byte, which is read back as the
box's. Right after the ctor the DLL sets the dialog's +0xB8 (its index) to 14,
19 or 24, so the picture (drawn from +0xB8 at 0x430827: frame index - 10 of
the tool sheet) is the Fourth, Fifth or Sixth's; +0xB8 is otherwise read only
by the Buy of category 4 (another store shelf). Tooltips: "Seventh Seed
Box\nPrice: $ 1000" (owned: the name alone), shown only with a version 2
Seed Boxes DLL.

`ftfp_box_events.version` is 2: `owned` / `set_owned` take boxes 0-5. The
Upgrades DLL still accepts version 1 (an older Seed Boxes DLL) and then sells
and draws only the Fourth-Sixth, so a mixed pair can never take money for a
box it cannot hold.

Per slot, the three Legendary packets on sale are kept in
`<save folder>\Plant Tycoon Fix Patcher Data\Plant Upgrades <slot>.dat`; bought
seeds and doses live in the stock trays, so the save keeps its stock layout.

## The Seed Boxes DLL: sites (`native/ftfp_seed_boxes/box_sites.h`)

| Site | Address | What |
|---|---|---|
| box_level | 0x41DE60 (code) | drawer level of the chest in the game's array: the stock rule, or one drawer per new box owned |
| send_to_box | 0x4245F0 (code) | the greenhouse's send-to-box search: stock chest first, then the second, then the third |
| scene_mouse | 0x469704 (Seed Storage vtable) | wraps 0x434D70 |
| scene_command | 0x46970C | wraps 0x433F80; buttons 7/8 (the arrows) step to the previous / next chest with a box |
| scene_draw | 0x469718 | wraps 0x4342F0; draws "Boxes 1-3" / "Boxes 4-6" / "Boxes 7-9" |
| scene_activate | 0x469724 | wraps 0x433930; makes the arrows once, shows them once the Fourth is owned |

The box array (`state+0x52CCC`, 10 x 12 records of 0x24 bytes) always holds
the chest on screen; the DLL keeps the other chests (`held[3]`, the resident
one's copy stale): making chest c resident copies the array out to the old
resident's copy and c's copy in. The
stock chest is put back before every save (the save event) and whenever the
Seed Storage screen opens or closes, so saves keep their stock layout and load
as vanilla without the mod. After the greenhouse fills a seed into a new
chest, that chest stays in the array until the next save or Seed Storage
visit, so the flying seed and the pot-seed overwrite (0x4281AF) see the slot
the search returned. The drawer level of a resident new chest is its own
boxes owned, in order (a box counts only when every box before it is owned).

`Seed Boxes <slot>.dat` (magic `PSBX`): version 2 is a 12-byte header
{magic, 2, 8648} then owned[8] (the Fourth to Ninth, 6-7 zero), boxes 4-6
(0x10E0 bytes) and boxes 7-9 (0x10E0 bytes). Version 1 ({magic, 1, 4324},
owned[4] and boxes 4-6) still loads: the Fourth-Sixth and boxes 4-6 as they
were, boxes 7-9 empty records (0x41D420) and not owned; the file is left as it
is until the next save writes version 2 (through a `.tmp`, then a replace).
Any other version, a wrong size, a short file or bytes after the body: set
aside as `.unreadable` (never deleted), nothing owned. The name is the same, so
the backups' slot naming (`save_backup.file_slot`) is unchanged.

Sort Seeds asks for the chests through `FtfpSeedBoxesChestList(state,
chests, rows, capacity)` (3 chests, 4 rows per box owned; 0 when capacity < 3).
The version 1 export `FtfpSeedBoxesChests` (two chests) is gone, so an older
Sort Seeds DLL beside this one finds no export and stays off rather than
sorting only some boxes, and the new Sort Seeds beside an older Seed Boxes DLL
does the same.

The New Flowers DLL passes its save (now with the game state), load, delete
and new-game events to the Upgrades DLL, which passes them on to the Seed
Boxes DLL.

## Revival Potion, Revita-Seed and the Formula Bomb (owner, 2026-10-30)

| Chemical | Id / sheet row | Price | Place on the Upgrades view |
|---|---|---|---|
| Radioactive Plant Formula | 36 / row 9 | $10,000, 3 doses | (598, 55) |
| Revival Potion | 37 / row 10 | $10,000, 3 doses | (655, 55) |
| Revita-Seed | 38 / row 11 | $2,500, 3 doses | (712, 55) |
| Radioactive Plant Formula Bomb | 39 / row 12 | $30,000, 3 doses | (598, 116) |

The Time Warp clock moved to row 13 (frame 26) and Add Money's coins to row
14 (frame 28), the Extra Greenhouse item is row 15 (frame 30), and Automatic
Sprinklers and the Auto-Healer are rows 16 and 17 (frames 32 and 34); the sheet
has 18 rows (`chem_rows = 18`). The game draws chemical c as frame
2c - 54, so a chemical's row is c - 27. Dialog indices 37-51 are stock store
items, so 37-39 are these chemicals only while a dialog opened from the
Upgrades view is up (`upgrade_dialog`): the dialog entry rides the Vaporbomb
path for them, the picture stub jumps to the chemicals' branch (`0x4308CC`,
its bound raised to 0x28), the price stub pushes the chemical's own id for
the tray-room check, Buy gives 3 doses, the tray tooltips name them (string
ids 0x1F5-0x1F7) and the use switch (`0x4266A6`) sends 36-39 to
`apply_chemical`, then the stock tail.

Revival Potion. A dead plant (age step `0x42E244`): health `+0x24` <= 0;
once, `+0x3C` = 1, `+0x94` (seeds taken) = 5 - `+0x90` (ripe), `+0x44` and
`+0x48` (price and value) = 0; the update returns while health <= 0
(`0x42DFA6`) so its clock `+0x04` stops, and it clears `+0x9D` (on sale)
each update; the greenhouse draws every part brown (`0x42E7AE`). A dose:
health 100, `+0x3C` = 0, `+0x04` = the game clock (`0x403430`, as a
planting, `0x42FCAA`), the value by `0x42DD80` and the price by the
planting rule (`0x42FD11`-`0x42FD9E`). Parts dead before it died stay dead.
The price: the only code that writes a pot's `+0x44` is the planting rule
and the death above (the player never sets a price), so the planting rule
is the stock rule for a plant that has none.

The Sell tag (owner, 2026-10-30: "the chemicals should not clear the Sell
tag"). The game writes `+0x9D` only at the Sell button and Sell All
(`0x427CE5`, `0x427D3E`, `0x427F05`, `0x428038`), a visitor's purchase
(`0x435C90`, which sets the sold byte `+0x9E`) and the dead-plant clear
(`0x42DF91`); no stock chemical touches it. The formula's "branch roll done"
(`+0x9C`, a byte the game sets at `0x42E482`) was written as a 4-byte int,
clearing `+0x9D`, `+0x9E` and `+0x9F`: it is one byte now. `dead_untag`
(`0x42DF91`, 7 bytes, `stub_dead_untag`): when it is about to clear a set
`+0x9D`, it first sets `+0x9F` = `'S'` (`0x53`). `+0x9F` is the padding
after the three flag bytes: no instruction of the game addresses it (no
`+0x9F` / `+0x2227` operand; the dword operands at `+0x9C` all belong to
other objects). In the record, it moves with the plant (the save body is the
state, Extra Greenhouses moves whole records). Planting clears it
(`plant_seed`). A Revival dose consumes it: `+0x9D` = 1 when the plant passes
the Sell button's test (`+0x38`, `+0x4C`, age `+0x10` >= 24.0 at
`0x4677E8`, alive) and Extra Greenhouses' `FtfpExtraGreenhousesForSale()` is
below 15 x (`FtfpExtraNurseriesOwned()` + 1); otherwise a "Revival Potion"
message says the nurseries are full and the plant stays off sale.

Revita-Seed. Pollination (`0x4240A0`) sets `+0x6C` (byte) for good, `+0x98`
the age, `+0x90` = 0, `+0x94` = 0-2 or 4; ripening (`0x42E0C6`) and picking
(`0x426208`, refused at `+0x94` >= 5) use them; pollen is refused while
`+0x6C` is set (`0x425EA3`). Depleted = `+0x6C` set and `+0x94` >= 5; a
dose sets `+0x6C`, `+0x90`, `+0x94` and the DLL's `+0x7C` to 0.

Formula Bomb. The Fertilizer Bomb (chemical 32, `0x426BA8`) reaches every
pot of the greenhouse on screen with a plant (`+0x38`) and health above 0,
rows of `0x1D1 / 0x5D` columns (`0x426D3C`) up to `0x50A00 / 0x5600` pots
(`0x426D56`), with the plant object `0x42F6C0(row, col)`; the bomb reads
those two immediates and gives each such pot one `apply_formula`. Its art is
the Fertilizer Bomb's row (5) with its white glass turned rainbow and its
yellow label white, the cap left grey (the owner's pick).

Icons (scripts/build_potion_assets.py): upright at the Mutation Liquid
flask's visible height (41 px) on its bottom line; pouring at the same scale.
Preview: docs/images/revival-potion-plant.png. For the extra greenhouses:
the pots are addressed as the stock chemicals address them
(`state + 0x2188 + (row * 5 + col) * 0x5600`) and the bomb's range is the
stock bomb's; an extra-greenhouse build that swaps its pots into those 15
records is reached, one that does not must hook these the same way.

## Treated plants sell for the highest price (owner, 2026-10-31: "Always pays the max")

Every live plant `apply_formula` reaches (a Formula dose or the Bomb) gets
`'R'` (`0x52`) in its pot's `+0x9F`, the byte proven unused above, which the
Revival Potion's `'S'` shares: `'S'` is only ever on a dead plant and `'R'`
only on a live one, because `stub_dead_untag` (every update of a dead plant)
clears `'R'` before it may set `'S'`, and the Revival Potion clears an `'R'`
it finds; `restore_sale` tests for `'S'` alone. Planting (`plant_seed`) clears
the byte. It is in the pot's record, so it goes with the plant through Extra
Greenhouses' whole-record moves, its nurseries (the plants for sale arranged
into the 15 spots, the off-screen ones too) and the save.

A visitor's purchase (`0x435C70`) reads the species' asking price twice,
after New Flowers' index stubs: `0x435CF2` (`mov edx, [eax + ecx*4]; add
[eax + 0x34], edx`, Money Earned) and `0x435D12` (`mov edx, [ecx + eax*4];
push edx; call 0x41ED70`, the cash). The two stubs replace that price with
`sale_price(pot, P, sold)`: for an `'R'` pot the species' highest selling
price, `native/common/max_sale_price.h` (the Breeding Guide's
`prices(key, "max").highest_selling`: the highest asking price whose price
seen with every effect at its best stays below 2V; never less than P; a
Fabled Lemonbush $1186), and the second clears the mark. The buy roll
(`0x436BE0`) that chose the plant is over, so its chance is P's. The extra
nurseries' off-screen sales are this same code on their arranged pots.

## Live checks (test copy with the sdlpoke test shim)

- All three DLLs log "installed (all sites)".
- The link shows in the game's font, turns yellow on hover, opens the Upgrades
  view; the Supplies plate returns; the stock view is unchanged.
- Legendary dialog: prismatic packet, "Legendary Seeds", $5000, the owner's
  text; Buy puts it in the seed tray, charges $5000 and empties the shelf.
- Formula dialog: bottle, title, $10,000 (shown as $2500 before the price
  change), the owner's text; with a full chemical tray the stock "There is no
  room in your Chemical Tray." message; Buy adds chemical 36 with 3 doses.
- A Legendary seed (foliage 12, Buttercup) planted at age 6, one dose: age 28,
  size 110, health 100, bloom 100, 58 flowers ("Buttercup Bamboo").
- Fifth Seed Box first: "You need the previous upgrade first!". Fourth then
  Fifth: $1000 each, ticks shown, stock seed-box records unchanged.
- Seed Storage: arrows, "Boxes 4-6" with two drawers open; a seed moved from
  box 1 through the tray into box 5.
- Boxes 1-3 full: the greenhouse's "Seed moved to seed box." put the seed in
  box 4's first slot.
- Quit through the menu and reload: the second chest, its seeds, the purchases
  and the unsold Legendary packets all come back.

Not checked live: the hover tooltips of the Upgrades items (the test shim
cannot show any tooltip, stock ones included).

The Seventh-Ninth Seed Box were checked in emulation, not live (the owner was
playing): `tests/test_seed_boxes_7_9.py` runs both DLLs' own code and the
game's own purchase helper, Buy, Seed Storage mouse code, drawer level and
send-to-box on the vanilla executable (order, price, $0 free, can't afford,
already owned; storing, taking, drag and drop and locked drawers in boxes
7-9; the arrows; the greenhouse filling 1-3, 4-6, 7-9; the version 1 sidecar,
a round trip, a new game and damaged files; Sort Seeds over three chests),
and, on the Enable All build (every Plant setting), checks every DLL site is
still the stock code and overlaps no other site, manifest patch or the
startup loader, and that the Seed Boxes, Upgrades, Sort Seeds, Unused
Flowers, Extra Greenhouses, Greenhouse Counts and Optimize Prices DLLs install
and log so.

## Limits

- An autosave that fires while a Fourth-Ninth box dialog is open would save
  the box records as the dialog shows them (the owned bytes of the stock
  drawers could change). The window is the few seconds the dialog is open.
- Like New Flowers, the sidecars follow the slot number, not the game's backup
  rotation.

## Automatic Sprinklers and the Auto-Healer

`native/ftfp_plant_upgrades/auto_upgrades.h`. Two permanent items, $10,000 each
($0 with Free upgrades), drawn from chemical-sheet rows 16 and 17 (frames 32 and
34, upright only; row 15 is the Extra Greenhouse's): the sprinklers at (409, 111)
on the tool shelf under the Extra Greenhouse, the healer at (655, 116) beside the
Formula Bomb, each with the owned tick. Click: Yes / No to buy; owned, Yes / No to
unpurchase (no refund). Tooltips: "<name>\nPrice: $ 10000" or "<name>\nOwned,
click to unpurchase".

Hooks (upgrade_sites.h): `unit_top` 0x42E134 (`cmp [edi+0x28], ebp; jne 0x42E144`,
the top of the plant update's age-unit loop, edi = the pot, esi = the plant) and
`units_done` 0x42E2DF (after the loop). Both call auto_tend: water (+0x20) = 800,
pests (+0x28) = 0 with one Plants Cured (state + 0x40), health (+0x24) = 100. A pot
at health 0 is never touched, and once one is seen at 0 within an update the rest
of that update leaves it (the stock loop can lift a plant that died of old age
back above 0). Extra Greenhouses runs the stock update once per greenhouse with its
pots moved in, so every greenhouse gets the same. A purchase tends every live pot
at once (FtfpExtraGreenhousesPot for Greenhouses 2-6).

Water: each unit drops 6 + difficulty - the water upgrade (cacti 3 less); below
100 after the drop is too dry (-1 health, no gain, size loss before 21); above 900
the pest roll (0x42CB9E) triples. 800 sits high in 108-900, below the 900 pest line; nothing in the update raises the water.

Ownership: "Plant Tycoon Fix Patcher Data\Auto Upgrades <slot>.dat", 16 bytes
("PPAU", version 1, sprinklers, healer), written with the save through a .tmp;
read at load (no file: neither owned; a bad file is set aside as .unreadable);
deleted with the slot; a new game clears both. Tests: tests/test_auto_upgrades.py.
