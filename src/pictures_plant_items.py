"""Picture Studio, Plant Tycoon: every item of the game (and of the patcher), drawn as the game
draws it, for the "Items" tab of "Make your own" (docs/picture-studio-interface.md, "Items").

Where each picture comes from, in the vanilla Plant Tycoon.exe (tests/test_picture_items.py
checks these numbers against the executable and pins pictures against the game's art). Every
draw here is the sprite manager's whole-picture draw 0x4207F0 or cell draw 0x4208F0, at scale 1
and alpha 100 (the picture as it is):

* The Supplies store (0x447D40) draws each shelf item on peep_shadow1.png (sprite 0xB0) and, when
  owned, CHECKMARK.png (0x25) over it:
  - the seed shelf, 3 x 3 packets at (602 + 57 c, 315 + 66 r): the shadow at (x + 5, y + 5),
    then seed_grid.png (0x2E) frame = the packet's;
  - the tool shelf, Tools_Grid.png (0xB2) frame 5 r + c at (233 + 57 c, 50 + 61 r): the shadow
    at (x + 25, y + 30), the tick at (x + 19, y + 22) (state + 0x6EC + 0x20 frame);
  - the chemicals shelf, Chemicals_Grid.png (0xB3) frame 2 k (k = 3 r + c, the bottle upright)
    at (598 + 57 c, 55 + 66 r): the shadow at (x + 25, y + 30);
  - the nursery shelf, Ornaments_Grid.png (0xB1) frame 5 r + c at (253 + 57 c, 297 + 64 r):
    the shadow at (x + 5, y + 10), the tick at (x - 1, y + 2) (state + 0x9EC + 0x20 frame).
* The greenhouse's Tools box (0x44DD70): the soil bag, watering can, shears and net
  (soilbag_grid.png 0x2F, waterbucket_grid.png 0x9C, scissors.png 0xA1, net.png 0xA3, 2 x 3
  cells) at frame 2 x the upgrade level; on the mouse (0x429260..) the same, and frame
  2 x level + 1 while it is pressed over the pots (the can poured, the shears open ...).
* The chemical tray (0x416650): Chemicals_Grid frame 2 x id - 54 (ids 27-35, the game's
  eChemicalName1..9); a held bottle (0x42957C) the same, and frame 2 x id - 53 (pouring) while
  pressed over the pots. A seed packet held (0x4294AB) is its seed_grid frame.
* A seed packet's frame (0x41DD54): (foliage - 1) x 4 + 0 for a Common flower, 1 Endangered,
  2 Extinct, 3 the rarest Extinct flowers (18-23).
* Pots: the pot draw 0x42F740 (pictures_plant.SceneryPlanner.pot).
* The patcher's Store Upgrades and Items (native/ftfp_plant_upgrades on_draw, auto_draw,
  chem_draw, muta_draw): the same shelf draw from its taller copies of the sheets,
  Chemicals_Grid_upgrades.png (chemicals 36-39, 48, 49 at frame 2 x id - 54; the Time Warp 26,
  Add Money 28, Extra Greenhouse 30, Automatic Sprinklers 32, Auto-Healer 34, Extra Chemical
  Slots 36, Extra Nursery 40) and seed_grid_legendary.png (a Legendary Seed: frame 95 +
  foliage), and the Extra Seed Box (Tools_Grid frame 4); the Extra Greenhouse's shadow at
  (x + 4, y + 30) and tick at (x - 1, y + 22).

* Using an item on a pot starts the effect manager's sprays (the add 0x41C1F0 and its kin; drawn by
  0x41C000 with 0x4208F0 at alpha 1.0, scale 100, every cell of the sheet in turn): the chemical
  switch 0x4266B6 (table 0x4273A8) adds, per chemical, the effect types in CHEM_EFFECTS; soil
  dropped in a pot falls as type 5 (0x423DD5), water poured as type 8 (0x424042). The type's sheet
  is the add's switch 0x41BADE (table 0x41BEA0). The patcher's chemicals 36-39 start no effect
  (ftfp_plant_upgrades.c: apply_chemical, then the tail that only plays the sound); Muta-Flower and
  Muta-Foliage continue into the Mutation Liquid's case (k_mutation_rest 0x426EFA), so theirs are
  its effects.

The game has no unused item art: every cell of these sheets is drawn by one of the above (the
seed sheet's last four cells, 92-95, are empty).
"""

from __future__ import annotations

from dataclasses import dataclass

from picture_image import PictureError

SHADOW, TICK = 0xB0, 0x25
SEEDS, TOOLS, CHEMICALS, ORNAMENTS = 0x2E, 0xB2, 0xB3, 0xB1
HAND_SHEETS = {"soil": 0x2F, "water": 0x9C, "shears": 0xA1, "net": 0xA3}
CHEM_UPGRADES = ("Chemicals_Grid_upgrades.png", 2, 23)
SEED_LEGENDARY = ("seed_grid_legendary.png", 16, 8)
LEGENDARY_BASE = 95
SHELF = {   # (shadow offset, tick offset or None)
    "seed": ((5, 5), None), "tool": ((25, 30), (19, 22)), "chemical": ((25, 30), None),
    "ornament": ((5, 10), (-1, 2)), "upgrade": ((25, 30), (19, 22)), "greenhouse": ((4, 30), (-1, 22)),
}
CHEMICAL_NAMES = ("Plant Food", "Vitamins", "Insect Poison", "Bio-organic Plant Food", "Plant Rescue Formula",
                  "Fertilizer Bomb", "Insta-Grow Formula", "Mutation Liquid", "Insta-Grow Vaporbomb")   # ids 27-35
TOOL_COLUMNS = (("soil", ("Common Soil", "Bio-organic Soil", "Soil from Isola")),
                ("water", ("Tap Water", "Filtered Water", "Water from Isola")),
                ("shears", ("Dull Pruning Shears", "Sharp Pruning Shears", "Golden Pruning Shears")),
                ("net", ("Crude Butterfly Net", "Large Butterfly Net", "Golden Butterfly Net")),
                ("box", ("First Seed Box", "Second Seed Box", "Third Seed Box")))
HAND_WORDS = {"soil": "pouring soil", "water": "watering", "shears": "cutting", "net": "catching"}
# The seed packets keep the shop's names (the owner, 2026-11-01): a flower of each frame's group gives
# the packet by breeding_plant.part_packet (frame 3 is still an Extinct packet, for flowers 18-23).
PACKET_FRAME_FLOWERS = (1, 3, 2, 18)


def packet_words(frame_tier: int) -> str:
    import breeding_plant as bp
    words = f"{bp.part_packet(PACKET_FRAME_FLOWERS[frame_tier], 'flower')} Seeds packet"
    if frame_tier == 3:
        words += f" ({bp.FLOWER_WORD[18]} to {bp.FLOWER_WORD[23]} flower)"
    return words
PATCHER_CHEMICALS = ((36, "Radioactive Plant Formula"), (37, "Revival Potion"), (38, "Revita-Seed"),
                     (39, "Radioactive Plant Formula Bomb"), (48, "Muta-Flower"), (49, "Muta-Foliage"))
PATCHER_UPGRADES = (   # key, name, (file, cols, rows) or sheet id, frame, shelf kind
    ("extra_seed_box", "Extra Seed Box", TOOLS, 4, "upgrade"),
    ("time_warp", "Time Warp", CHEM_UPGRADES, 26, "chemical"),
    ("add_money", "Add Money", CHEM_UPGRADES, 28, "chemical"),
    ("extra_greenhouse", "Extra Greenhouse", CHEM_UPGRADES, 30, "greenhouse"),
    ("sprinklers", "Automatic Sprinklers", CHEM_UPGRADES, 32, "upgrade"),
    ("auto_healer", "Auto-Healer", CHEM_UPGRADES, 34, "upgrade"),
    ("chem_slots", "Extra Chemical Slots", CHEM_UPGRADES, 36, "upgrade"),
    ("extra_nursery", "Extra Nursery", CHEM_UPGRADES, 40, "upgrade"),
)
POT_SOILS = ("common soil", "bio-organic soil", "soil from Isola")
EFFECT_SPRITES = {3: 0xAA, 5: 0x27, 8: 0x2A, 11: 0x31, 12: 0x32, 13: 0x34, 14: 0x35, 15: 0x33, 17: 0xAD}
EFFECT_WORDS = {3: "sparkles", 5: "falling soil", 8: "falling water", 11: "white spray", 12: "red spray",
                13: "blue spray", 14: "purple spray", 15: "yellow spray", 17: "blurry sparkles"}
CHEM_EFFECTS = {27: (14, 14, 14), 28: (15, 15), 29: (11, 11, 11), 30: (12, 12, 12, 12), 31: (15, 15, 15, 15),
                32: (12, 12, 15, 15), 33: (15, 15, 12, 12, 12, 11), 34: (15, 11, 14, 12, 13, 17, 3),
                35: (14, 14, 13, 13)}
CHEM_EFFECTS.update({48: CHEM_EFFECTS[34], 49: CHEM_EFFECTS[34]})   # Muta-Flower, Muta-Foliage
TOOL_EFFECTS = {"soil": 5, "water": 8}


def effect_types(item) -> tuple:
    """The effect types the item starts on a pot, each sheet once, in the game's order."""
    if item.chemical is not None:
        return tuple(dict.fromkeys(CHEM_EFFECTS.get(item.chemical, ())))
    if item.hand in TOOL_EFFECTS:
        return (TOOL_EFFECTS[item.hand],)
    return ()
CATEGORIES = ("Seeds", "Chemicals", "Tools", "Nursery ornaments", "Pots", "Store Upgrades and Items")


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    category: str
    sheet: object = None              # a sprite id, or (file, columns, rows)
    frame: int = 0
    shelf: str | None = None          # the shelf's draw (SHELF)
    hand: str | None = None           # a greenhouse tool (HAND_SHEETS) and its level
    level: int = 0
    chemical: int | None = None       # a chemical id: the tray and the pour
    ornament: int | None = None       # a nursery ornament (its nursery picture)
    pot: int | None = None            # a pot style
    patcher: bool = False
    unused: bool = False


def _items() -> tuple:
    import breeding_plant as bp
    seeds, chems, tools, orns, pots, upgrades = CATEGORIES
    out = []
    for foliage in range(1, 24):
        for tier in range(4):
            out.append(Item(f"seed{foliage}_{tier}", f"{bp.FOLIAGE_WORD[foliage]} seed, {packet_words(tier)}", seeds, SEEDS,
                            (foliage - 1) * 4 + tier, "seed"))
    for foliage in range(1, 24):
        out.append(Item(f"legendary{foliage}", f"{bp.FOLIAGE_WORD[foliage]} seed, Legendary Seeds packet", seeds,
                        SEED_LEGENDARY, LEGENDARY_BASE + foliage, "seed", patcher=True))
    for k, name in enumerate(CHEMICAL_NAMES):
        out.append(Item(f"chem{27 + k}", name, chems, CHEMICALS, 2 * k, "chemical", chemical=27 + k))
    for ident, name in PATCHER_CHEMICALS:
        out.append(Item(f"chem{ident}", name, chems, CHEM_UPGRADES, 2 * ident - 54, "chemical", chemical=ident,
                        patcher=True))
    for level in range(3):
        for column, (what, names) in enumerate(TOOL_COLUMNS):
            out.append(Item(f"tool{what}{level}", names[level], tools, TOOLS, 5 * level + column, "tool",
                            hand=what if what in HAND_SHEETS else None, level=level))
    import pictures_plant as pp
    for k, name in enumerate(pp.ORNAMENT_NAMES):
        out.append(Item(f"ornament{k}", name, orns, ORNAMENTS, k, "ornament", ornament=k))
    import pictures_plant_data as D
    for style in range(D.SPRITES[pp.POT_SPRITE][2]):
        out.append(Item(f"pot{style}", f"Pot {style + 1}", pots, pot=style))
    for key, name, sheet, frame, shelf in PATCHER_UPGRADES:
        out.append(Item(key, name, upgrades, sheet, frame, shelf, patcher=True))
    return tuple(out)


ITEMS = _items()
BY_KEY = {item.key: item for item in ITEMS}


def views(item: Item) -> tuple:
    out = []
    if item.shelf:
        out.append(("shelf", "In the store (on its shadow)"))
        if SHELF[item.shelf][1] and item.category != CATEGORIES[0]:
            out.append(("owned", "In the store, owned (with the tick)"))
    if item.category == CATEGORIES[0]:
        out.append(("packet", "The packet (the seed tray, on the mouse)"))
    if item.hand:
        out.append(("tool", "In the Tools box, and on the mouse"))
        out.append(("tool_use", f"On the mouse over a pot ({HAND_WORDS[item.hand]})"))
    if item.chemical is not None:
        out.append(("tray", "In the chemical tray, and on the mouse"))
        out.append(("pour", "On the mouse over a pot (pouring)"))
    for kind in effect_types(item):
        import pictures_plant as pp
        name, cols, rows = pp.sprite(EFFECT_SPRITES[kind])
        frames = max(1, cols) * max(1, rows)
        out += [(f"fx{kind}_{k}", f"Used on a pot: {EFFECT_WORDS[kind]}, frame {k + 1} of {frames}")
                for k in range(frames)]
    if item.ornament is not None:
        import pictures_plant_data as D
        if item.ornament in D.DECORATIONS:
            out.append(("nursery", "In the nursery (as the Decorations tab draws it)"))
    if item.pot is not None:
        out.append(("empty", "Empty"))
        for level, soil in enumerate(POT_SOILS):
            out += [(f"soil{level}", f"With {soil}"), (f"wet{level}", f"With {soil}, watered"),
                    (f"planted{level}", f"With {soil}, planted"),
                    (f"plantedwet{level}", f"With {soil}, planted and watered")]
    return tuple(out)


class ItemPlanner:
    """The draws, in the game's order, through pictures_plant's own planner (its cells and rects)."""

    def __init__(self, planner, scenery) -> None:
        self.planner = planner
        self.scenery = scenery

    def cell(self, sheet, frame: int, x: int = 0, y: int = 0):
        import pictures_plant as pp
        if isinstance(sheet, int):
            name, cols, rows = pp.sprite(sheet)
        else:
            name, cols, rows = sheet
        cols, rows = max(1, cols), max(1, rows)
        cw, ch = self.planner.cells((name, cols, rows))
        col, row = min(frame % cols, cols - 1), min(frame // cols, rows - 1)
        return pp.PlantDraw(name, cols, rows, row * cols + col, x, y,
                            rect=(col * cw, row * ch, col * cw + cw, row * ch + ch))

    def whole(self, sheet: int, x: int, y: int):
        import pictures_plant as pp
        name, _c, _r = pp.sprite(sheet)
        w, h = self.planner.cells((name, 1, 1))
        return pp.PlantDraw(name, 1, 1, 0, x, y, rect=(0, 0, w, h))

    def plan(self, item: Item, view: str) -> list:
        view = str(view)
        if view in ("shelf", "owned") and item.shelf:
            (sx, sy), tick = SHELF[item.shelf]
            out = [self.whole(SHADOW, sx, sy), self.cell(item.sheet, item.frame)]
            if view == "owned":
                if tick is None:
                    raise PictureError("The store shows no tick on this.")
                out.append(self.whole(TICK, *tick))
            return out
        if view == "packet" and item.category == CATEGORIES[0]:
            return [self.cell(item.sheet, item.frame)]
        if view in ("tool", "tool_use") and item.hand:
            return [self.cell(HAND_SHEETS[item.hand], 2 * item.level + (1 if view == "tool_use" else 0))]
        if view in ("tray", "pour") and item.chemical is not None:
            frame = 2 * item.chemical - 54 + (1 if view == "pour" else 0)
            return [self.cell(item.sheet, frame)]
        if view.startswith("fx") and "_" in view:
            kind, k = (int(v) for v in view[2:].split("_"))
            import pictures_plant as pp
            if kind in effect_types(item):
                name, cols, rows = pp.sprite(EFFECT_SPRITES[kind])
                if 0 <= k < max(1, cols) * max(1, rows):
                    return [self.cell(EFFECT_SPRITES[kind], k)]
        if view == "nursery" and item.ornament is not None:
            return self.scenery.decoration(item.ornament)
        if item.pot is not None:
            if view == "empty":
                return self.scenery.pot(item.pot, "none", 0, False)
            for prefix, soil, wet in (("plantedwet", "planted", True), ("planted", "planted", False),
                                      ("soil", "soil", False), ("wet", "soil", True)):
                if view.startswith(prefix) and view[len(prefix):].isdigit():
                    level = int(view[len(prefix):])
                    if level not in (0, 1, 2):
                        break
                    return self.scenery.pot(item.pot, soil, level, wet)
        raise PictureError("The game does not draw this item that way.")


def stock_files() -> list:
    import pictures_plant as pp
    ids = [SHADOW, TICK, SEEDS, TOOLS, CHEMICALS, ORNAMENTS, *HAND_SHEETS.values(), *EFFECT_SPRITES.values()]
    return [pp.sprite(i)[0] for i in ids]


def patcher_files() -> list:
    return [CHEM_UPGRADES[0], SEED_LEGENDARY[0]]
