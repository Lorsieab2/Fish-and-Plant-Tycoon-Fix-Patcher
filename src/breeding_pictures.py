"""The Breeding Guide's picture tabs: every fin, body and egg (Fish Tycoon) and every
flower, foliage and seed packet (Plant Tycoon), grouped by rarity in the games' own words.

No game art is shipped. The first time the guide finds any copy of the game (the folder
picked on the patcher's Game tab, the patcher's "- Modded" and "- Modded Upgrades" copies,
a default install, or a folder picked with "Find game..."), it copies every sheet the
pictures are cut from into its own picture cache, "<patcher folder>\\Breeding Guide
Pictures\\Fish" (or "\\Plant"), with a manifest of each file's size and SHA-256, written
into a temporary folder and swapped in whole. From then on the pictures come from that
cache, with no game copy needed; a cache whose manifest or files do not match is rebuilt,
never used. The cache is built on the player's own machine from their own copy and is not
in the repository or the release.

Each sheet is read from the game copy as the game's loader 0x409B00 finds it (Fish
Tycoon: its Images folder, then Assets\\ft.dat, a file on disk winning; Plant Tycoon: its
Images folder). The patcher's own parts come from the patcher's own assets, the files it
installs in a patched copy (DS Exclusive Fish's FISH_23..29 sheets, DS Store Items' Exotic
Fish Eggs icon, Unused Flowers' flowers64x64_grid.png, the Store Upgrades seed sheet), so
they show whichever copy the stock art came from.

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
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid
import zipfile

PATCHER_ROOT = Path(__file__).resolve().parents[1]

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
    name: str
    tier: str
    art: tuple = ()              # Cells / Wholes, stacked top to bottom
    hidden: bool = False         # never set now: spoilers off leaves an undiscovered part out


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
    """Every part of a kind as a picture, grouped by rarity; with spoilers off only the parts
    the save has discovered (a part of a discovered species), the others left out, as the
    part sheets leave them out."""
    model = view.model
    rarity = getattr(model, "part_rarity")
    items = [Item(part.name, rarity(part), part_art(model, kind, part.index)) for part in model.parts(kind)
             if view.spoilers or (part.kind, part.index) in view.known_parts]
    return _grouped(items, _order(model))


def egg_items(view) -> list[Group]:
    eggs = list(FISH_EGGS) + ([EXOTIC_EGGS] if view.model.extras else [])
    return [Group(tier, [Item(name, tier, (Whole(file),))]) for name, tier, file in eggs]


def seed_items(view) -> list[Group]:
    """The seed packets by type: each foliage the type sells, with the seed's picture (the
    picture follows the flower's tier, so Extinct packets have two). A packet is named by its
    foliage, so with spoilers off only the discovered foliages' packets are in."""
    import breeding_plant as bp
    model = view.model
    name_of = {p.index: p.name for p in model.parts("foliage")}

    def known(kind, gene):
        return view.spoilers or (kind, gene) in view.known_parts

    def items(genes, tier, art, suffix=""):
        return [Item(f"{name_of[f]} seed{suffix}", tier, art(f)) for f in genes if known("foliage", f)]

    file, cols, rows = SEED_SHEET
    groups = [
        Group("Common", items(bp.COMMON_GENES, "Common", lambda f: (Cell(file, cols, rows, seed_frame(f, 0)),))),
        Group("Endangered", items(bp.ENDANGERED_GENES, "Endangered",
                                  lambda f: (Cell(file, cols, rows, seed_frame(f, 1)),))),
    ]
    # The rarest flowers' packets: named by the first and last of those flowers only when both
    # are discovered (spoilers off never names an undiscovered flower).
    first, last = 18, 23
    rarest = (f" ({bp.FLOWER_WORD[first].strip()} to {bp.FLOWER_WORD[last].strip()} flower)"
              if known("flower", first) and known("flower", last) else " (the rarest flowers)")
    extinct = []
    for f in sorted(g for g in bp.EXTINCT_GENES if g <= 23 and known("foliage", g)):
        extinct.append(Item(f"{name_of[f]} seed", "Extinct", (Cell(file, cols, rows, seed_frame(f, 2)),)))
        extinct.append(Item(f"{name_of[f]} seed{rarest}", "Extinct", (Cell(file, cols, rows, seed_frame(f, 3)),)))
    groups.append(Group("Extinct", extinct))
    if model.extras:
        lfile, lcols, lrows = LEGENDARY_SHEET
        groups.append(Group("Legendary", items(bp.STOCK_FOLIAGES, "Legendary",
                                               lambda f: (Cell(lfile, lcols, lrows, LEGENDARY_FRAME_BASE + f),))))
    return [g for g in groups if g.items]


def header_for(view, tab_id: str) -> str:
    """The line at the top of a picture tab: a part tab's "n of N discovered" (the part
    sheets' own count); the seed tab's packets follow the foliages."""
    what = tab_id.split(":", 1)[1]
    if what in ("eggs",):
        return ""
    if what == "seeds":
        return ("" if view.spoilers else "Seed packets of the foliages you have discovered. ") \
            + view.part_count_text("foliage")
    return view.part_count_text(what)


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
            self._zip = None


# ------------------------------------------------------------------ the picture cache

CACHE_FOLDER = "Breeding Guide Pictures"
CACHE_GAME_FOLDERS = {"fish": "Fish", "plant": "Plant"}
CACHE_FORMAT = "Fish and Plant Tycoon Fix Patcher: Breeding Guide Pictures"
CACHE_VERSION = 1
MANIFEST = "manifest.json"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
GAME_TITLES = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}

# Where the cache lives: the patcher's own folder. A test points it elsewhere.
CACHE_ROOT = PATCHER_ROOT / CACHE_FOLDER


def no_pictures_message(game: str) -> str:
    title = GAME_TITLES.get(game, "the game")
    return (f"No {title} pictures yet: pick your {title} game folder on the patcher's Game tab, or click "
            f"\"Find game...\" here. The guide then keeps its own copy of the pictures, so they show from then on.")


def patcher_art(game: str) -> dict[str, Path]:
    """The patcher's own art, by the file name the guide asks for: the files its settings
    install in a patched copy (data/*_manifest.json, the companions' Images)."""
    assets = PATCHER_ROOT / "assets"
    if game == "fish":
        import breeding_fish as bf
        art = {f"FISH_{g:02d}_{part}_Grid.png": assets / "fish_tycoon_ds" / "Images" / f"FISH_{g:02d}_{part}_Grid.png"
               for g in bf.DS_GENES for part in ("body", "top", "bot")}
        art[EXOTIC_EGGS[2]] = assets / "fish_tycoon_ds_store" / "Images" / EXOTIC_EGGS[2]
        return art
    return {FLOWER_SHEETS[82][0]: assets / "plant_tycoon_flowers" / "Images" / "flowers64x64_grid.png",
            LEGENDARY_SHEET[0]: assets / "plant_tycoon_upgrades" / "Images" / "seed_grid_legendary.png"}


# Plant Tycoon: the images "Add Missing Assets to LDW Version" puts in a patched copy where
# the LDW copy has none (only additive, as that setting is).
PLANT_FILL = PATCHER_ROOT / "assets" / "plant_tycoon_steam" / "Images"


def required_files(game: str) -> list[str]:
    """Every sheet the picture tabs cut a picture from, stock and patcher, as the guide names them."""
    names: list[str] = []
    if game == "fish":
        import breeding_fish as bf
        model = type("M", (), {"game": "fish"})()
        for g in tuple(bf.PC_GENES) + tuple(bf.DS_GENES):
            names += [a.file for a in part_art(model, "body", g) + part_art(model, "fin", g)]
        names += [file for _n, _t, file in FISH_EGGS] + [EXOTIC_EGGS[2]]
    else:
        names += [name for name, _c, _r in FLOWER_SHEETS.values()]
        names += list(FOLIAGE_ART.values())
        names += [SEED_SHEET[0], LEGENDARY_SHEET[0]]
    return list(dict.fromkeys(names))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class PatcherArt:
    """The patcher's own art files, read only."""

    def __init__(self, game: str, files: dict | None = None) -> None:
        files = patcher_art(game) if files is None else files
        self.files = {name.casefold(): Path(path) for name, path in files.items()}

    def read(self, name: str) -> bytes | None:
        path = self.files.get(name.casefold())
        if path is None:
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None


class CacheSource:
    """The guide's own picture cache for one game, checked against its manifest before it is
    used: a missing, changed or unlisted file, or an unreadable manifest, and it is not used."""

    def __init__(self, game: str, root: Path | None = None, *, folder: Path | None = None,
                 spec: "CacheSpec | None" = None) -> None:
        self.game = game
        spec = spec or guide_spec()
        self.folder = Path(folder) if folder is not None else Path(root or spec.root) / CACHE_GAME_FOLDERS[game]
        self.copy = self.folder
        self.problem = ""
        self._data: dict[str, bytes] = {}
        self.manifest: dict = {}
        try:
            manifest = json.loads((self.folder / MANIFEST).read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.problem = "no cache"
            return
        except (OSError, ValueError) as exc:
            self.problem = f"its manifest could not be read ({exc})"
            return
        if not isinstance(manifest, dict) or manifest.get("format") != spec.format \
                or manifest.get("version") != CACHE_VERSION or manifest.get("game") != game \
                or not isinstance(manifest.get("files"), dict):
            self.problem = "its manifest is not this version's"
            return
        files = manifest["files"]
        missing = [n for n in spec.required_for(game) if n not in files]
        if missing:
            self.problem = f"it is partial ({len(missing)} picture file(s) not in it)"
            return
        for name, entry in files.items():
            if not isinstance(entry, dict) or Path(name).name != name:
                self.problem = f"its manifest entry for {name!r} is not valid"
                return
            try:
                data = (self.folder / name).read_bytes()
            except OSError:
                self.problem = f"{name} is missing from it"
                return
            if len(data) != entry.get("size") or _sha256(data) != str(entry.get("sha256", "")).upper() \
                    or not data.startswith(PNG_MAGIC):
                self.problem = f"{name} does not match its manifest"
                return
            self._data[name.casefold()] = data
        self.manifest = manifest

    @property
    def ok(self) -> bool:
        return not self.problem

    def read(self, name: str) -> bytes | None:
        return self._data.get(name.casefold())

    def close(self) -> None:
        pass


def _remove_tree(path: Path) -> None:
    """Remove one of the cache's own folders (never anything else)."""
    shutil.rmtree(path, ignore_errors=True)


def build_cache(game: str, copy: Path, root: Path | None = None,
                spec: "CacheSpec | None" = None) -> tuple[bool, str]:
    """(built, why not): copy every picture sheet from the game copy (read only) and the
    patcher's own art into the cache, all or nothing. The new cache is written in a
    temporary folder beside it, checked, then swapped in; the game copy is never written."""
    spec = spec or guide_spec()
    root = Path(root or spec.root)
    final = root / CACHE_GAME_FOLDERS[game]
    source = ArtSource(copy)
    patcher = PatcherArt(game, spec.patcher)
    fill = {}
    if game == "plant":
        try:
            fill = {p.name.casefold(): p for p in PLANT_FILL.iterdir() if p.is_file()}
        except OSError:
            fill = {}
    try:
        if source.problem:
            return False, source.problem
        files: dict[str, tuple[bytes, str]] = {}
        missing = []
        for name in spec.required_for(game):
            data, where = patcher.read(name), "the patcher's own art"
            if data is None:
                data, where = source.read(name), f"the game copy {copy}"
            if data is None and name.casefold() in fill:
                try:
                    data, where = fill[name.casefold()].read_bytes(), "the patcher's Add Missing Assets images"
                except OSError:
                    data = None
            if data is None or not data.startswith(PNG_MAGIC):
                missing.append(name)
                continue
            files[name] = (data, where)
    finally:
        source.close()
    if missing:
        shown = ", ".join(missing[:4]) + (" ..." if len(missing) > 4 else "")
        return False, f"{len(missing)} picture file(s) are not in {copy} ({shown})."
    temp = root / f".{final.name}.building-{uuid.uuid4().hex[:12]}"
    old = root / f".{final.name}.old-{uuid.uuid4().hex[:12]}"
    try:
        root.mkdir(parents=True, exist_ok=True)
        for leftover in root.glob(f".{final.name}.*"):  # an earlier build that was cut short
            if leftover.is_dir():
                _remove_tree(leftover)
        temp.mkdir()
        entries = {}
        for name, (data, where) in files.items():
            (temp / name).write_bytes(data)
            entries[name] = {"size": len(data), "sha256": _sha256(data), "from": where}
        manifest = {"format": spec.format, "version": CACHE_VERSION, "game": game,
                    "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "built_from": str(copy), "files": entries}
        (temp / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        check = CacheSource(game, folder=temp, spec=spec)
        if not check.ok:
            raise OSError(f"the new cache did not read back: {check.problem}")
        if final.exists():
            os.replace(final, old)
        os.replace(temp, final)
    except OSError as exc:
        _remove_tree(temp)
        if old.exists() and not final.exists():
            try:
                os.replace(old, final)
            except OSError:
                pass
        return False, f"The picture cache could not be written in {root} ({exc})."
    _remove_tree(old)
    return True, ""


class Pictures:
    """What a picture tab reads: the patcher's own art first, then the cache (or, when no
    cache could be made, the game copy itself)."""

    def __init__(self, game: str, base=None, problem: str = "", note: str = "",
                 patcher: dict | None = None) -> None:
        self.game = game
        self.base = base
        self.patcher = PatcherArt(game, patcher)
        self.problem = problem or (getattr(base, "problem", "") if base is not None else no_pictures_message(game))
        self.copy = getattr(base, "copy", None)
        self.note = note

    def read(self, name: str) -> bytes | None:
        data = self.patcher.read(name)
        if data is None and self.base is not None:
            data = self.base.read(name)
        return data

    def close(self) -> None:
        if self.base is not None:
            self.base.close()


@dataclass(frozen=True)
class CacheSpec:
    """Which picture cache: its root folder, manifest format, file list and patcher art (the
    Breeding Guide's by default; Picture Studio has its own, picture_image.picture_source)."""
    root: Path
    format: str
    required: tuple | None = None          # None: required_files(game)
    patcher: dict | None = None            # None: patcher_art(game)

    def required_for(self, game: str) -> list[str]:
        return list(self.required) if self.required is not None else required_files(game)


def guide_spec() -> CacheSpec:
    """The Breeding Guide's cache (CACHE_ROOT is read now, so a test can point it elsewhere)."""
    return CacheSpec(root=CACHE_ROOT, format=CACHE_FORMAT)


def picture_source(game: str, copies=(), root: Path | None = None, spec: CacheSpec | None = None) -> Pictures:
    """The pictures for a game: the cache when it is whole; else built from the first game
    copy that has every sheet; else read straight from a copy; else none, with one line
    saying how to give the guide a copy."""
    spec = spec or guide_spec()
    patcher = spec.patcher
    cache = CacheSource(game, root, spec=spec)
    if cache.ok:
        return Pictures(game, cache, patcher=patcher)
    copies = [Path(c) for c in dict.fromkeys(str(c) for c in copies if c)]
    reasons = []
    for copy in copies:
        built, why = build_cache(game, copy, root, spec)
        if built:
            cache = CacheSource(game, root, spec=spec)
            if cache.ok:
                return Pictures(game, cache, patcher=patcher)
            why = f"the new picture cache did not read back ({cache.problem})"
        reasons.append(why)
    if copies:
        direct = ArtSource(copies[0])
        note = reasons[0] if reasons else ""
        return Pictures(game, direct, note=note, patcher=patcher)
    return Pictures(game, None, patcher=patcher)


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
