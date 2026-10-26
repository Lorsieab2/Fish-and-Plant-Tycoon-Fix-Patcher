# Plant Tycoon: Add new store upgrades and items

One optional Plant Tycoon setting, **Add new store upgrades and items**
(`plant_upgrades`), built on **Add unused flowers** (`new_flowers`,
`docs/plant-tycoon-new-flowers-design.md`). It ships two companion DLLs:

| Companion DLL | What | Loaded by |
|---|---|---|
| `Store Upgrades and Items.dll` | the store's Upgrades view, Legendary Seeds, the formula, the boxes' purchase | `Unused Flowers.dll` |
| `Extra Seed Boxes.dll` | the Fourth-Sixth Seed Box: the second chest and the greenhouse overflow | `Store Upgrades and Items.dll` |

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
    - then adds flowers until no spot is left (`0x42ED60(360, 0)`).
    Live: a rose bush went from 5 flowers to 276, a 37-branch plant from 4 to
    276, and every one of the 14 new flowers from a handful to 39-132.
  - **Fourth, Fifth and Sixth Seed Box** (seed-box column of Tool Upgrades,
    upper left): $1000 each, "Even more space for your
    seeds!", stock seed-box art at the stock places with the stock tick once
    owned. Bought in order, through the stock dialog and its messages.
- The stock seed box is one 120-seed chest of three 40-seed drawers (First,
  Second, Third Seed Box). The new boxes are a **second chest** with the same
  three drawers. Once the Fourth is owned, the stock gold arrows
  (`leftarrow.png` / `rightarrow.png`) on the Seed Storage title bar switch
  between "Boxes 1-3" and "Boxes 4-6". Each box opens one drawer.
- The greenhouse knows the new boxes: a seed sent to the seed box goes to the
  first free slot of boxes 1-3, then of boxes 4-6, and "Your seed box is
  already full!" only comes when all are full.

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
| chem_picture_bound | 0x4308D3 | immediate 0x24 -> 0x25: the dialog draws chemical 36's bottle |
| seed/chem sheet records, link record | 0x485F4C, 0x485F5C, 0x4875A4, 0x4875B4, 0x4882D4 | the sprite records above |

The Fourth-Sixth boxes are sold through the stock tool-upgrade dialog: while
one of their dialogs is open, tool records 4, 9 and 14 (`state+0x6E8+k*0x20`,
the stock seed-box drawers) describe the new boxes (price, owned byte, title
and description ids), so the stock code checks "already have it", "needs the
previous upgrade" and the cash, and Buy sets the owned byte. The stock
records are restored when the dialog closes.

Per slot, the three Legendary packets on sale are kept in
`<save folder>\Plant Tycoon Fix Patcher Data\Plant Upgrades <slot>.dat`; bought
seeds and doses live in the stock trays, so the save keeps its stock layout.

## The Seed Boxes DLL: sites (`native/ftfp_seed_boxes/box_sites.h`)

| Site | Address | What |
|---|---|---|
| box_level | 0x41DE60 (code) | drawer level of the chest in the game's array: the stock rule, or one drawer per new box owned |
| send_to_box | 0x4245F0 (code) | the greenhouse's send-to-box search: stock chest first, then the second chest |
| scene_mouse | 0x469704 (Seed Storage vtable) | wraps 0x434D70 |
| scene_command | 0x46970C | wraps 0x433F80; buttons 7/8 (the arrows) switch chests |
| scene_draw | 0x469718 | wraps 0x4342F0; draws "Boxes 1-3" / "Boxes 4-6" |
| scene_activate | 0x469724 | wraps 0x433930; makes the arrows once, shows them once the Fourth is owned |

The box array (`state+0x52CCC`, 10 x 12 records of 0x24 bytes) always holds
the chest on screen; switching swaps the 0x10E0 bytes with the DLL's copy. The
stock chest is put back before every save (the save event) and whenever the
Seed Storage screen opens or closes, so saves keep their stock layout and load
as vanilla without the mod. After the greenhouse fills a seed into the second
chest, that chest stays in the array until the next save or Seed Storage
visit, so the flying seed and the pot-seed overwrite (0x4281AF) see the slot
the search returned. The second chest and the three purchases are kept in
`Seed Boxes <slot>.dat`.

The New Flowers DLL passes its save (now with the game state), load, delete
and new-game events to the Upgrades DLL, which passes them on to the Seed
Boxes DLL.

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

## Limits

- An autosave that fires while a Fourth-Sixth box dialog is open would save
  the box records as the dialog shows them (the owned bytes of the stock
  drawers could change). The window is the few seconds the dialog is open.
- Like New Flowers, the sidecars follow the slot number, not the game's backup
  rotation.
