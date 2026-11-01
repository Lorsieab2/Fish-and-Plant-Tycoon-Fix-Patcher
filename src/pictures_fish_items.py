"""Picture Studio, Fish Tycoon: every item of the game (and of the patcher), drawn as the game
draws it, for the "Items" tab of "Make your own" (docs/picture-studio-interface.md, "Items").

Where each picture comes from, in the vanilla Fish Tycoon.exe (tests/test_picture_items.py
checks every number here against the executable, and pins pictures against the game's art):

* The supply store (0x427239..0x427518) walks the 26 store records at 0x457EF0 (0x34 bytes
  each: +0x10 the item, +0x18/+0x1C the picture's place, +0x20/+0x24 its shadow's, -1 none,
  +0x28 the picture's sprite). An item at rest: ITEM_SHADOW.png (sprite 0x8D) at the shadow's
  place, then the picture, both whole (0x407D60). The item under the mouse: the picture alone
  at 120% (0x408030(sprite, x, y, 120, 1, 0): the scaled blit, centred on its place, see
  picture_image.scaled_cell). The picked item: the same at a pulsing percent, 80 - P, P
  from 0x4271F0 (a sine of an angle that grows 5 degrees a frame; the percents it gives are
  PICKED_PULSE, run in Unicorn by the tests).
* The supply slots (0x41BEB0): the slot record's icon (state + 0x2C4 + k x 0x1C) drawn whole;
  the item held on the mouse (0x41D08F): the record's cursor (+0x2C8 ...), whole, or cell 0 of
  a grid sheet. The purchase writer 0x427540(slot, item, icon, cursor) is called at
  0x427F59..0x427FE7 with each supply's pair (STOCK_SUPPLY); the food slot's pair is set by
  the Fish Food research level (0x420A02: level 1 flakes 0x78 / 0x6E, 2 pellets 0x20 / 0x72,
  3 live food 0x21 / 0x73).
* In the tank: using a supply adds tank effects at the mouse through 0x413B00(type) (the use
  handler 0x420B70, a case per supply slot): food type 2 / 14 / 24 by the research level
  (0x420BF3..0x420C15), every medicine and chemical type 3 (0x420C56, 0x420E45), eggs type 4
  (0x421392 ...). The effect set-up 0x410AE0 (its jump table 0x410EDC, case = type - 2) and the
  effects pass 0x410F50 draw them: flakes_Grid.png 12 frames alpha 254, liquid_Grid.png 16
  frames alpha 254, eggs_Grid.png 16 frames alpha 175, pellets_Grid.png 16 frames alpha 175,
  ANIM_TINYSHRIMP_Grid.png 26 frames alpha 125 (frame = the effect's count, 0 to its last).
  The equipment and ornaments in the tank are drawn as pictures_fish draws them.
* DS Store Items (native/ftfp_ds_store, the patcher's): its Upgrades page (draw_page) draws
  each picture whole, the pointed-at one at 120% and the picked one at a percent pulsing
  48..128 (0x30 + a triangle of 0x50 over 1.6 s) through the same 0x408030, without shadows;
  its supplies' icons and cursors are its TOOL_ / TOOL_dropper_ pictures (buy_chemical,
  buy_universal). Extra Supply Slots' item is its ITEM_EXTRA_SUPPLY_SLOTS.png on that page.
* Unused art: pictures in the game's ft.dat that no sprite record names (the sprite table
  0x4552F0 lists every picture the game loads), drawn whole: nothing in the game says how
  else they would be drawn.
"""

from __future__ import annotations

from dataclasses import dataclass

from picture_image import Draw, PictureError

# ------------------------------------------------------------------ the game's numbers

SHADOW_FILE = "ITEM_SHADOW.png"                # sprite 0x8D
HOVER_SCALE = 120                              # 0x427502: push 0x78
# 0x4271F0's percents for a picked item (80 - P), one per frame from the pick: a 36-frame cycle
# (Unicorn on the vanilla code, tests/test_picture_items.py). The distinct values, largest first.
PICKED_CYCLE = (134, 134, 134, 133, 131, 130, 128, 126, 124, 121, 119, 117, 115, 113, 112, 111, 110, 109,
                109, 109, 110, 111, 112, 113, 115, 117, 119, 121, 124, 126, 128, 130, 131, 133, 134, 134)
PICKED_PULSE = tuple(sorted(set(PICKED_CYCLE), reverse=True))
DS_PULSE = (48, 128)                           # draw_page: 0x30 + t x 0x50 / 800, t 0..800 ms and back
DS_PULSE_STEP = 8

# The 26 stock store records (0x457EF0): item -> (picture x, y), (shadow x, y) or None, sprite file.
STORE = {
    0: ((64, 84), (64, 85), "ITEM_ICK.png"),
    1: ((159, 90), (150, 90), "ITEM_fungaltreatment.png"),
    2: ((251, 101), (238, 103), "ITEM_purplebeaker.png"),
    3: ((333, 98), (333, 101), "ITEM_growthhormone.png"),
    4: ((429, 99), (420, 106), "ITEM_UNKNOWNCHEMICAL.png"),
    5: ((508, 98), (519, 100), "ITEM_FISHEGGS_COMMON.png"),
    6: ((594, 92), (610, 94), "ITEM_FISHEGGS_UNUSUAL.png"),
    7: ((686, 98), (700, 86), "ITEM_FISHEGGS_RARE.png"),
    8: ((74, 165), (59, 164), "SUPPLYSHOP_ITEMFORSALE_AERATOR.png"),
    9: ((155, 172), (148, 172), "ITEM_heater.png"),
    10: ((238, 188), (237, 180), "ITEM_snail.png"),
    11: ((338, 179), (328, 176), "ITEM_seahorse.png"),
    12: ((431, 179), (428, 179), "ITEM_plant1.png"),
    13: ((521, 174), (516, 176), "SUPPLYSHOP_ITEMFORSALE_PLANT05_ORANGEFLOWER.png"),
    14: ((607, 171), (610, 166), "SUPPLYSHOP_ITEMFORSALE_PLANT06_PURPLE.png"),
    15: ((694, 162), (696, 166), "SUPPLYSHOP_ITEMFORSALE_PLANT07_REDGREEN.png"),
    16: ((61, 255), (61, 246), "ITEM_shell.png"),
    17: ((165, 246), (150, 248), "ITEM_pagoda.png"),
    18: ((242, 256), (240, 256), "ITEM_diver.png"),
    19: ((330, 265), (345, 260), "SUPPLYSHOP_ITEMFORSALE_CORAL_RED.png"),
    20: ((429, 258), (424, 256), "ITEM_column.png"),
    21: ((508, 254), (514, 254), "SUPPLYSHOP_ITEMFORSALE_SHIP.png"),
    22: ((604, 246), (607, 246), "ITEM_TANK2.png"),
    23: ((575, 305), None, "ITEM_researchfood.png"),
    24: ((560, 374), None, "ITEM_researchtank.png"),
    25: ((565, 450), None, "ITEM_books.png"),
}
STORE_SPRITES = {0: 142, 1: 143, 2: 144, 3: 145, 4: 146, 5: 147, 6: 148, 7: 149, 8: 1, 9: 2, 10: 150,
                 11: 151, 12: 152, 13: 165, 14: 164, 15: 163, 16: 153, 17: 154, 18: 155, 19: 162, 20: 156,
                 21: 161, 22: 157, 23: 158, 24: 159, 25: 160}
# 0x427540(slot, item, icon sprite, cursor sprite) at 0x427F59..0x427FE7.
STOCK_SUPPLY = {0: (1, 0xA7, 0xAD), 1: (1, 0xA8, 0xAE), 2: (2, 0xA9, 0xAF), 3: (2, 0x7A, 0x7B),
                4: (2, 0xAA, 0xB0), 5: (3, 0x79, 0x79), 6: (3, 0xAB, 0xAB), 7: (3, 0xAC, 0xAC)}
# Tank effects: type -> (sprite, sheet, columns, rows, frames, alpha) (0x410B10, drawn by 0x410F50).
EFFECTS = {2: (0x6E, "flakes_Grid.png", 12, 1, 12, 254), 3: (0x6F, "liquid_Grid.png", 16, 1, 16, 254),
           4: (0x70, "eggs_Grid.png", 16, 1, 16, 175), 14: (0x72, "pellets_Grid.png", 16, 1, 16, 175),
           24: (0x73, "ANIM_TINYSHRIMP_Grid.png", 16, 2, 26, 125)}
# Sprite table entries the items use (0x4552F0: file, columns, rows).
SPRITE_FILES = {
    0x20: ("TOOL_foodcan_pellets.png", 0, 0), 0x21: ("TOOL_foodcan_live.png", 0, 0),
    0x6E: ("flakes_Grid.png", 12, 1), 0x72: ("pellets_Grid.png", 16, 1), 0x73: ("ANIM_TINYSHRIMP_Grid.png", 16, 2),
    0x78: ("TOOL_FOODCAN_FLAKES.png", 0, 0), 0x79: ("TOOL_FISHEGGS_COMMON.png", 0, 0),
    0x7A: ("TOOL_GROWTHHORMONE.png", 0, 0), 0x7B: ("TOOL_dropper4.png", 0, 0),
    0xA7: ("TOOL_ICKTREATMENT.png", 0, 0), 0xA8: ("TOOL_FUNGALTREATMENT.png", 0, 0),
    0xA9: ("TOOL_FISHVITAMINS.png", 0, 0), 0xAA: ("TOOL_UNKNOWNCHEMICAL.png", 0, 0),
    0xAB: ("TOOL_FISHEGGS_UNUSUAL.png", 0, 0), 0xAC: ("TOOL_FISHEGGS_RARE.png", 0, 0),
    0xAD: ("TOOL_dropper1.png", 0, 0), 0xAE: ("TOOL_dropper2.png", 0, 0), 0xAF: ("TOOL_dropper3.png", 0, 0),
    0xB0: ("TOOL_dropper5.png", 0, 0),
}
# 0x420A02: the food slot by Fish Food research level: (icon, cursor, tank effect type).
FOOD = {1: (0x78, 0x6E, 2), 2: (0x20, 0x72, 14), 3: (0x21, 0x73, 24)}

CATEGORIES = ("Medicines and chemicals", "Fish food", "Fish eggs", "Equipment, plants and creatures",
              "Ornaments", "Upgrades and research")


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    category: str
    store: int | None = None          # a stock store record
    ds: str | None = None             # DS Store Items' Upgrades-page picture (file)
    icon: str | None = None           # the supply slot's picture (file)
    cursor: tuple | None = None       # (file, columns, rows): the picture on the mouse
    effect: int | None = None         # the tank effect type of using it
    tank: tuple | None = None         # ("image", sprite) / ("ornament", sprite) / ("snail", ...)
    whole: str | None = None          # unused art, drawn whole
    patcher: bool = False
    unused: bool = False
    note: str = ""


def _sprite_file(sprite: int) -> tuple:
    return SPRITE_FILES[sprite]


def _stock_supply(item: int) -> dict:
    _slot, icon, cursor = STOCK_SUPPLY[item]
    return {"icon": _sprite_file(icon)[0], "cursor": _sprite_file(cursor)}


def _items() -> tuple:
    med, food, eggs, equip, orn, upg = CATEGORIES
    out = [
        Item("ick", "Ick Treatment", med, store=0, effect=3, **_stock_supply(0)),
        Item("fungal", "Fungal Treatment", med, store=1, effect=3, **_stock_supply(1)),
        Item("vitamins", "Fish Vitamins", med, store=2, effect=3, **_stock_supply(2)),
        Item("hormone", "Growth Hormone", med, store=3, effect=3, **_stock_supply(3)),
        Item("unknown", "Unknown Chemical", med, store=4, effect=3, **_stock_supply(4)),
        Item("rgh", "Radioactive Growth Hormone", med, ds="ITEM_RADIOACTIVE_GROWTHHORMONE.png",
             icon="TOOL_RADIOACTIVE_GROWTHHORMONE.png", cursor=("TOOL_dropper_RADIOACTIVE.png", 0, 0), patcher=True),
        Item("revival", "Revival Potion", med, ds="ITEM_REVIVAL_POTION.png", icon="TOOL_REVIVAL_POTION.png",
             cursor=("TOOL_dropper_REVIVAL.png", 0, 0), patcher=True),
        Item("clonafish", "ClonaFish", med, ds="ITEM_CLONAFISH.png", icon="TOOL_CLONAFISH.png",
             cursor=("TOOL_dropper_CLONAFISH.png", 0, 0), patcher=True),
        Item("muta_fin", "Muta-Fin", med, ds="ITEM_MUTA_FIN.png", icon="TOOL_MUTA_FIN.png",
             cursor=("TOOL_dropper_MUTA_FIN.png", 0, 0), patcher=True),
        Item("muta_body", "Muta-Body", med, ds="ITEM_MUTA_BODY.png", icon="TOOL_MUTA_BODY.png",
             cursor=("TOOL_dropper_MUTA_BODY.png", 0, 0), patcher=True),
        Item("orange_beaker", "Orange beaker", med, whole="item_orangebeaker.png", unused=True),
        Item("dropper_sheet", "Dropper sheet", med, whole="tool_dropper_grid.png", unused=True),
    ]
    for level, words in ((1, "flakes"), (2, "pellets"), (3, "live food")):
        icon, cursor, effect = FOOD[level]
        out.append(Item(f"food{level}", f"Fish Food, {words} (Fish Food research level {level})", food,
                        icon=_sprite_file(icon)[0], cursor=_sprite_file(cursor), effect=effect,
                        note="Fish food is never bought: the food slot holds it from the start, and its "
                             "look follows the Fish Food research level."))
    out.append(Item("fishfood_can", "Fish food box", food, whole="item_fishfood.png", unused=True))
    out += [
        Item("eggs_common", "Common Fish Eggs", eggs, store=5, effect=4, **_stock_supply(5)),
        Item("eggs_unusual", "Unusual Fish Eggs", eggs, store=6, effect=4, **_stock_supply(6)),
        Item("eggs_rare", "Rare Fish Eggs", eggs, store=7, effect=4, **_stock_supply(7)),
        Item("eggs_exotic", "Exotic Fish Eggs", eggs, ds="ITEM_FISHEGGS_EXOTIC.png",
             icon="TOOL_FISHEGGS_EXOTIC.png", cursor=("TOOL_FISHEGGS_EXOTIC.png", 0, 0), patcher=True),
        Item("aerator", "Aeration System", equip, store=8, tank=("image", 1)),
        Item("heater", "Temperature Regulator", equip, store=9, tank=("image", 2)),
        Item("snail", "Cleaning Snail", equip, store=10, tank=("snail",)),
        Item("seahorse", "Golden Seahorse", equip, store=11,
             note="The Golden Seahorse in the tank is on the Creatures tab."),
        Item("incubation", "Plant of Incubation from Isola", equip, store=12, tank=("image", 5)),
        Item("nutrition", "Plant of Nutrition from Isola", equip, store=13, tank=("image", 6)),
        Item("curing", "Plant of Curing from Isola", equip, store=14, tank=("image", 7)),
        Item("fertility", "Plant of Fertility from Isola", equip, store=15, tank=("image", 8)),
        Item("puffer", "Magic Pufferfish", equip, ds="ITEM_DS_PUFFER.png", patcher=True,
             note="The animal in the tank is on the Creatures tab."),
        Item("ray", "Blue-Spotted Stingray", equip, ds="ITEM_DS_STINGRAY.png", patcher=True,
             note="The animal in the tank is on the Creatures tab."),
        Item("eel", "Moray Eel", equip, ds="ITEM_DS_EEL.png", patcher=True,
             note="The eel and its home in the tank are on the Creatures tab."),
        Item("plant3a", "Tank plant (3a)", equip, whole="plant3a.png", unused=True),
        Item("plant3b", "Tank plant (3b)", equip, whole="plant3b.png", unused=True),
        Item("shell", "Shell Ornament", orn, store=16, tank=("ornament", 177)),
        Item("pagoda", "Pagoda Ornament", orn, store=17, tank=("ornament", 178)),
        Item("diver", "Diver Ornament", orn, store=18, tank=("ornament", 179)),
        Item("coral", "Fancy Coral Ornament", orn, store=19, tank=("ornament", 181)),
        Item("column", "Sunken Antique Column", orn, store=20, tank=("ornament", 180)),
        Item("ship", "Sunken Ship Ornament", orn, store=21, tank=("ornament", 182)),
        Item("yellow_coral", "Yellow coral", orn, whole="yellowcoral.png", unused=True),
        Item("red_coral", "Red coral (tank picture)", orn, whole="TANKOBJECT_CORAL_RED.png", unused=True),
        Item("tank2", "Second Tank", upg, store=22),
        Item("research_food", "Fish Food Research", upg, store=23),
        Item("research_environment", "Fish Environment Research", upg, store=24),
        Item("research_advertising", "Advertising Research", upg, store=25),
        Item("auto_feeder", "Auto-Feeder", upg, ds="ITEM_AUTO_FEEDER.png", patcher=True),
        Item("auto_healer", "Auto-Healer", upg, ds="ITEM_AUTO_HEALER.png", patcher=True),
        Item("time_warp", "Time Warp", upg, ds="ITEM_TIME_WARP.png", patcher=True),
        Item("add_money", "Add Money", upg, ds="ITEM_ADD_MONEY.png", patcher=True),
        Item("supply_slots", "Extra Supply Slots", upg, ds="ITEM_EXTRA_SUPPLY_SLOTS.png", patcher=True),
    ]
    return tuple(out)


ITEMS = _items()
BY_KEY = {item.key: item for item in ITEMS}

def ds_pulse() -> tuple:
    low, high = DS_PULSE
    return tuple(range(high, low - 1, -DS_PULSE_STEP))


def views(item: Item) -> tuple:
    """(key, label) of every picture the game draws of the item."""
    out = []
    if item.whole:
        return (("whole", "The picture (the game never draws it)"),)
    if item.store is not None or item.ds:
        out.append(("store", "In the store" + (" (with its shadow)" if item.store is not None
                                               and STORE[item.store][1] else "")))
        out.append(("hover", f"In the store, pointed at ({HOVER_SCALE}%)"))
        pulse = PICKED_PULSE if item.store is not None else ds_pulse()
        out += [(f"picked{p}", f"In the store, picked (pulsing): {p}%") for p in pulse]
    if item.icon:
        out.append(("slot", "In its supply slot"))
    if item.cursor:
        out.append(("hand", "In the hand (on the mouse)"))
    if item.effect is not None:
        _sprite, _file, _c, _r, frames, _a = EFFECTS[item.effect]
        what = "Falling in the tank" if item.category == CATEGORIES[1] else \
            "Eggs in the tank" if item.effect == 4 else "A drop in the tank"
        out += [(f"tank{k}", f"{what}: frame {k + 1}") for k in range(frames)]
    if item.tank:
        if item.tank[0] == "snail":
            import pictures_fish as pf
            out += [(f"snail{s}", f"In the tank, {words}") for s, words in pf.SNAIL_VIEWS]
        elif item.tank[0] == "ornament":
            out.append(("tank", "In the tank (resting on its shadow)"))
            out.append(("tank_falling", "In the tank, falling (no shadow)"))
        else:
            out.append(("tank", "In the tank"))
    return tuple(out)


def plan(item: Item, view: str, image_height=None) -> list:
    """The draw calls for one picture of the item (see views)."""
    import pictures_fish as pf
    view = str(view)
    if view == "whole" and item.whole:
        return [Draw(item.whole, 1, 1, 0, 0, 0)]
    if view == "store" or view == "hover" or view.startswith("picked"):
        if item.store is not None:
            (ix, iy), shadow, file = STORE[item.store]
        elif item.ds:
            (ix, iy), shadow, file = (0, 0), None, item.ds
        else:
            raise PictureError("The store does not sell this.")
        if view == "store":
            out = [Draw(SHADOW_FILE, 1, 1, 0, *shadow)] if shadow else []
            return out + [Draw(file, 1, 1, 0, ix, iy)]
        scale = HOVER_SCALE if view == "hover" else int(view[6:])
        allowed = PICKED_PULSE if item.store is not None else ds_pulse()
        if view != "hover" and scale not in allowed:
            raise PictureError("The store never draws that size.")
        return [Draw(file, 1, 1, 0, ix, iy, scale=scale)]
    if view == "slot" and item.icon:
        return [Draw(item.icon, 1, 1, 0, 0, 0)]
    if view == "hand" and item.cursor:
        file, cols, rows = item.cursor
        return [Draw(file, max(1, cols), max(1, rows), 0, 0, 0)]
    if view.startswith("tank") and view[4:].isdigit() and item.effect is not None:
        _sprite, file, cols, rows, frames, alpha = EFFECTS[item.effect]
        k = int(view[4:])
        if not 0 <= k < frames:
            raise PictureError("The game draws no such frame.")
        return [Draw(file, cols, rows, k, 0, 0, alpha=alpha)]
    if item.tank:
        if view.startswith("snail") and item.tank[0] == "snail":
            return [pf.draw_cell(int(view[5:]), 0, 0)]
        if item.tank[0] == "image" and view == "tank":
            return [pf.draw_cell(item.tank[1], 0, 0)]
        if item.tank[0] == "ornament" and view in ("tank", "tank_falling"):
            sprite = item.tank[1]
            h = image_height(sprite) if image_height else 0
            return pf.plan_ornament(sprite, falling=view == "tank_falling", image_h=h)
    raise PictureError("The game does not draw this item that way.")


def stock_files() -> list:
    names = [SHADOW_FILE]
    for item in ITEMS:
        if item.patcher:
            continue
        if item.store is not None:
            names.append(STORE[item.store][2])
        if item.icon:
            names.append(item.icon)
        if item.cursor:
            names.append(item.cursor[0])
        if item.effect is not None:
            names.append(EFFECTS[item.effect][1])
        if item.whole:
            names.append(item.whole)
    return list(dict.fromkeys(names))


def patcher_files() -> list:
    names = []
    for item in ITEMS:
        if item.patcher:
            names += [n for n in (item.ds, item.icon, item.cursor[0] if item.cursor else None) if n]
    return list(dict.fromkeys(names))
