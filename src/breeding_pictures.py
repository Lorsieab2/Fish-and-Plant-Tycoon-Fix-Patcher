"""The Breeding Guide's picture tabs: every fin, body and egg (Fish Tycoon) and every
flower, foliage and seed packet (Plant Tycoon), grouped by rarity in the games' own words.

No game art is shipped: every picture is read at run time from the game copy the guide
found for the chosen save (Fish Tycoon: its Images folder, then Assets\\ft.dat, the same
order as the game's loader 0x409B00, where a file on disk wins over ft.dat; Plant Tycoon:
its Images folder). The patcher's own parts come from the files the patcher installed in
that copy (DS Exclusive Fish's FISH_23..29 sheets, DS Store Items' Exotic Fish Eggs icon,
the Store Upgrades seed sheet; the Unused Flowers are cells of the stock flower sheets).

Where each picture comes from:

Fish Tycoon
  * Body: FISH_<gene>_body_Grid.png, 7 x 3 cells (the resource table 0x4552F0, entry
    38 + 3 x gene), cell 0, the adult facing left. Fin: FISH_<gene>_top_Grid.png and
    FISH_<gene>_bot_Grid.png, 13 x 2 cells (entries 40 + 3 g and 39 + 3 g), cell 0 of each,
    top above bottom. The game draws a fish as both fins behind its body (0x4145F0).
  * Eggs: the store's item icons ITEM_FISHEGGS_COMMON / UNUSUAL / RARE.png (strings
    0x442A64 / 0x442A48 / 0x442A30); Exotic Fish Eggs: ITEM_FISHEGGS_EXOTIC.png
    (ftfp_ds_store.c).

Plant Tycoon
  * Flower: the game's flower art records (0x48E6B8: gene, worth, sheet, mask, first cell,
    anchor x, y): sheet 81 is flowers56x56_grid.png, 82 flowers64x64_grid.png, 83
    fruit_grid.png (the sprite table at 0x485E80: ids 0x51-0x53); each flower has three
    views from the first cell, the last one full bloom. The Unused Flowers are the DLL's own
    records (ftfp_new_flowers.c, ART), cells of the same sheets.
  * Foliage: the plant factory 0x42EE20 builds a plant's class by foliage (jump table
    0x42F3B0, case = foliage); each class draws from its own parts sheet (theFernClass,
    Fern.png ...; the class names are the exe's RTTI). The picture is that sheet, scaled.
  * Seed: seed_grid.png (sprite 0x2E, 16 x 6 cells of 50); a packet's frame is
    (foliage - 1) x 4 + 0 for a Common flower, + 1 Endangered, + 2 Extinct up to Venomous..,
    + 3 for the rarest flowers (0x41DD54). Legendary Seeds: seed_grid_legendary.png, frame
    95 + foliage (ftfp_plant_upgrades.c).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
import zipfile

# ------------------------------------------------------------------ the art, as data


@dataclass(frozen=True)
class Cell:
    """One cell of a sprite sheet: file, columns, rows, cell index."""
    file: str
    cols: int
    rows: int
    index: int


@dataclass(frozen=True)
class Whole:
    """A whole image."""
    file: str


@dataclass
class Item:
    name: str                    # "" when hidden
    tier: str
    art: tuple = ()              # Cells / Wholes, stacked top to bottom
    hidden: bool = False


@dataclass
class Group:
    tier: str
    items: list = field(default_factory=list)


# Plant Tycoon's flower art records (0x48E6B8): gene -> (sheet id, first cell).
FLOWER_ART = {
    1: (81, 45), 2: (82, 3), 3: (81, 21), 4: (81, 3), 5: (81, 12), 6: (81, 30), 7: (81, 36), 8: (81, 57),
    9: (82, 9), 10: (81, 9), 11: (82, 30), 12: (82, 18), 13: (82, 6), 14: (83, 3), 15: (81, 0), 16: (83, 0),
    17: (83, 9), 18: (82, 0), 19: (81, 60), 20: (82, 24), 21: (82, 21), 22: (81, 18), 23: (83, 12),
    # Unused Flowers (ftfp_new_flowers.c, ART)
    24: (81, 6), 25: (81, 33), 26: (81, 24), 27: (81, 27), 28: (81, 54), 29: (81, 51), 30: (81, 39),
    31: (81, 42), 32: (81, 48), 33: (82, 12), 34: (82, 27), 35: (82, 33), 36: (83, 6), 37: (83, 15),
}
FLOWER_SHEETS = {81: ("flowers56x56_grid.png", 14, 5), 82: ("flowers64x64_grid.png", 12, 3),
                 83: ("fruit_grid.png", 12, 2)}
FLOWER_VIEWS = 3                 # three views from the first cell; the last is full bloom

# The plant factory's class for each foliage (0x42F3B0, RTTI names) and the parts sheet
# each class draws from (the sprite table 0x485E80, ids 0x39-0x4F).
FOLIAGE_ART = {
    1: "ivy_Grid.png", 2: "Caladium.png", 3: "Lemon Grass.png", 4: "Orchid.png", 5: "flower1_Grid.png",
    6: "Banana Plant.png", 7: "Fern.png", 8: "Ananas.png", 9: "Dieffenbachia.png", 10: "Banana Tree.png",
    11: "Lemon Tree.png", 12: "Bamboo Tree.png", 13: "Bonsai.png", 14: "Oak Tree.png", 15: "Cowboy Cactus.png",
    16: "Cactus 1 parts.png", 17: "ball-cactus_Grid.png", 18: "Bop.png", 19: "Tiger Fern.png",
    20: "Pitcher Plant.png", 21: "Willow Tree.png", 22: "Test Plant Parts.png", 23: "Ridged Cactus.png",
}
FOLIAGE_CLASSES = {
    1: "theIvy1PlantClass", 2: "theCaladiumPlantClass", 3: "theLemonGrassClass", 4: "theOrchidClass",
    5: "theFlower1PlantClass", 6: "theBananaPlantClass", 7: "theFernClass", 8: "theAnanasClass",
    9: "theDieffenbachiaClass", 10: "theBananaTreeClass", 11: "theLemonTreeClass", 12: "theBambooTreeClass",
    13: "theBonsaiTreeClass", 14: "theOakTreeClass", 15: "theCowboyCactusClass", 16: "theCactus1PlantClass",
    17: "theBallCactusClass", 18: "theBopPlantClass", 19: "theTigerFernClass", 20: "thePitcherPlantClass",
    21: "theWillowTreeClass", 22: "theTestPlantClass", 23: "theBallCactus2Class",
}
SEED_SHEET = ("seed_grid.png", 16, 6)
LEGENDARY_SHEET = ("seed_grid_legendary.png", 16, 8)
LEGENDARY_FRAME_BASE = 95

FISH_EGGS = (("Common Fish Eggs", "Common", "ITEM_FISHEGGS_COMMON.png"),
             ("Unusual Fish Eggs", "Unusual", "ITEM_FISHEGGS_UNUSUAL.png"),
             ("Rare Fish Eggs", "Rare", "ITEM_FISHEGGS_RARE.png"))
EXOTIC_EGGS = ("Exotic Fish Eggs", "Exotic (DS Store Items)", "ITEM_FISHEGGS_EXOTIC.png")

TABS = {"fish": (("pictures:fin", "Fin Pictures"), ("pictures:body", "Body Pictures"),
                 ("pictures:eggs", "Egg Pictures")),
        "plant": (("pictures:flower", "Flower Pictures"), ("pictures:foliage", "Foliage Pictures"),
                  ("pictures:seeds", "Seed Pictures"))}


def seed_frame(foliage: int, flower_tier: int) -> int:
    """0x41DD54: (foliage - 1) x 4 + the flower's tier (0 Common, 1 Endangered, 2 Extinct, 3 the
    rarest flowers)."""
    return (foliage - 1) * 4 + flower_tier


def _order(model) -> list[str]:
    order = getattr(model, "rarity_order", None)
    if order:
        return list(order)
    if model.game == "fish":
        return ["Common", "Unusual", "Rare"]
    return ["Common", "Endangered", "Extinct", "Legendary"]


def _grouped(items: list[Item], order: list[str]) -> list[Group]:
    groups = {t: Group(t) for t in order}
    for item in items:
        groups.setdefault(item.tier, Group(item.tier)).items.append(item)
    return [g for g in groups.values() if g.items]


def part_art(model, kind: str, index: int) -> tuple:
    if model.game == "fish":
        if kind == "body":
            return (Cell(f"FISH_{index:02d}_body_Grid.png", 7, 3, 0),)
        return (Cell(f"FISH_{index:02d}_top_Grid.png", 13, 2, 0), Cell(f"FISH_{index:02d}_bot_Grid.png", 13, 2, 0))
    if kind == "flower":
        sheet, first = FLOWER_ART[index]
        name, cols, rows = FLOWER_SHEETS[sheet]
        return (Cell(name, cols, rows, first + FLOWER_VIEWS - 1),)
    return (Whole(FOLIAGE_ART[index]),)


def part_items(view, kind: str) -> list[Group]:
    """Every part of a kind as a picture, grouped by rarity; with spoilers off a part no
    discovered species has is a "?" with no name."""
    model = view.model
    rarity = getattr(model, "part_rarity")
    items = []
    for part in model.parts(kind):
        tier = rarity(part)
        shown = view.spoilers or (part.kind, part.index) in view.known_parts
        items.append(Item(part.name if shown else "", tier, part_art(model, kind, part.index) if shown else (),
                          hidden=not shown))
    return _grouped(items, _order(model))


def egg_items(view) -> list[Group]:
    eggs = list(FISH_EGGS) + ([EXOTIC_EGGS] if view.model.extras else [])
    return [Group(tier, [Item(name, tier, (Whole(file),))]) for name, tier, file in eggs]


def seed_items(view) -> list[Group]:
    """The seed packets by type: each foliage the type sells, with the seed's picture (the
    picture follows the flower's tier, so Extinct packets have two)."""
    import breeding_plant as bp
    model = view.model
    name_of = {p.index: p.name for p in model.parts("foliage")}

    def item(foliage, tier, art, suffix=""):
        shown = view.spoilers or ("foliage", foliage) in view.known_parts
        return Item(f"{name_of[foliage]} seed{suffix}" if shown else "", tier, art if shown else (), hidden=not shown)

    file, cols, rows = SEED_SHEET
    groups = [
        Group("Common", [item(f, "Common", (Cell(file, cols, rows, seed_frame(f, 0)),)) for f in bp.COMMON_GENES]),
        Group("Endangered", [item(f, "Endangered", (Cell(file, cols, rows, seed_frame(f, 1)),))
                             for f in bp.ENDANGERED_GENES]),
    ]
    extinct = []
    rarest = f" ({bp.FLOWER_WORD[18].strip()} to {bp.FLOWER_WORD[23].strip()} flower)"
    for f in sorted(bp.EXTINCT_GENES):
        if f <= 23:
            extinct.append(item(f, "Extinct", (Cell(file, cols, rows, seed_frame(f, 2)),)))
            extinct.append(item(f, "Extinct", (Cell(file, cols, rows, seed_frame(f, 3)),), rarest))
    groups.append(Group("Extinct", extinct))
    if model.extras:
        lfile, lcols, lrows = LEGENDARY_SHEET
        groups.append(Group("Legendary", [item(f, "Legendary", (Cell(lfile, lcols, lrows, LEGENDARY_FRAME_BASE + f),))
                                          for f in bp.STOCK_FOLIAGES]))
    return groups


def items_for(view, tab_id: str) -> list[Group]:
    what = tab_id.split(":", 1)[1]
    if what == "eggs":
        return egg_items(view)
    if what == "seeds":
        return seed_items(view)
    return part_items(view, what)


# ------------------------------------------------------------------ reading the art


class ArtSource:
    """The game copy's images, read only: the Images folder first (case-insensitive, as
    Windows finds it), then Fish Tycoon's Assets\\ft.dat (a ZIP, lower-case names)."""

    def __init__(self, copy) -> None:
        self.copy = Path(copy) if copy else None
        self.problem = ""
        self._images: dict[str, Path] = {}
        self._zip_names: dict[str, str] = {}
        self._zip = None
        if self.copy is None:
            self.problem = "No game copy was found for this save, so its pictures cannot be read."
            return
        images = self.copy / "Images"
        try:
            self._images = {p.name.casefold(): p for p in images.iterdir() if p.is_file()}
        except OSError:
            self._images = {}
        dat = self.copy / "Assets" / "ft.dat"
        if dat.is_file():
            try:
                self._zip = zipfile.ZipFile(dat)
                self._zip_names = {n.casefold(): n for n in self._zip.namelist() if not n.startswith("__MACOSX")}
            except (OSError, zipfile.BadZipFile) as exc:
                self.problem = f"The game's art file could not be read ({dat.name}: {exc})."
        if not self._images and not self._zip_names:
            self.problem = self.problem or f"No game images were found in {self.copy}."

    def read(self, name: str) -> bytes | None:
        key = name.casefold()
        path = self._images.get(key)
        try:
            if path is not None:
                return path.read_bytes()
            if key in self._zip_names:
                return self._zip.read(self._zip_names[key])
        except (OSError, KeyError, zipfile.BadZipFile):
            return None
        return None

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()


MAX_SIDE = 120


def photo(tk_mod, master, source: ArtSource, art: tuple, cache: dict):
    """A Tk image of the art (cells stacked top to bottom), scaled down to fit, or None when
    a file is missing or unreadable."""
    pieces = []
    for a in art:
        sheet = cache.get(a.file)
        if sheet is None:
            data = source.read(a.file)
            if data is None:
                return None
            try:
                sheet = tk_mod.PhotoImage(master=master, data=base64.b64encode(data))
            except tk_mod.TclError:
                return None
            cache[a.file] = sheet
        if isinstance(a, Cell):
            w, h = sheet.width() // a.cols, sheet.height() // a.rows
            x, y = (a.index % a.cols) * w, (a.index // a.cols) * h
            if y + h > sheet.height():
                return None
            piece = tk_mod.PhotoImage(master=master, width=w, height=h)
            piece.tk.call(piece, "copy", sheet, "-from", x, y, x + w, y + h, "-to", 0, 0)
        else:
            piece = sheet
        pieces.append(piece)
    width = max(p.width() for p in pieces)
    height = sum(p.height() for p in pieces)
    image = tk_mod.PhotoImage(master=master, width=width, height=height)
    top = 0
    for p in pieces:
        image.tk.call(image, "copy", p, "-to", (width - p.width()) // 2, top)
        top += p.height()
    factor = max(1, -(-max(width, height) // MAX_SIDE))
    return image.subsample(factor) if factor > 1 else image
