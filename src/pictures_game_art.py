"""Picture Studio: "All game art", every picture file of both games (and of the patcher), one
picture per sprite cell, cut as the game cuts it, for the "All game art" tab of "Make your own".

What is exact, and what is not (the tab's note says the same):

* A sheet the game loads is listed by its sprite record (Fish Tycoon's table 0x4552F0, 197
  records of {id, file, columns, rows}; Plant Tycoon's 0x4855F0, pictures_plant_data.SPRITES): a
  grid's cell k is the game's cut (Fish Tycoon 0x4095F0, Plant Tycoon 0x409EE0: width // columns
  by height // rows, column and row clamped), a plain image is whole; each drawn at scale 1 and
  full strength, as the game's own cell and image draws do when they are not scaled or faded.
* A picture file the game has but its executable never names (no sprite record, button,
  background or font loads it) is "(unused)"; it has no grid, so it is shown whole. "Names" is
  strict: the whole file name, or its stem as a whole string of its own (a font class such as
  "ptfontsmall", or a stem the game numbers itself: Plant Tycoon builds male_Bodies00 from
  "male_bodies" with "%s%d%d%s" at 0x40A12F). A stem that is only part of another file's name
  does not count (logo1.gif is not logo1.png; bushDetailE.png is not bushDetailE2.png). Fish
  Tycoon builds no picture name from a format string (its only ones, "%s%s" / "%s%s%s" at
  0x410692 / 0x410724, join the folder and a name, and "%s%d" at 0x4439C0 is text), so its eight
  species_*.png pieces, never named, are unused (the species screen is species_bg.bmp alone).
* The patcher's own picture files (assets/) are "(patcher)", with the grid the patcher's DLL gives
  them (pictures_fish.sheet), else whole.
* BMP, JPEG and GIF pictures are read by picture_formats (the JPEGs exactly as the game's
  libjpeg-9 decodes them); a GIF has one picture per frame (each of the games' has one).
* A file the game's sprite table names but its folder lacks (Plant Tycoon: SPLASH2_BG.jpg,
  SPLASH3_BG.bmp, MenuButtonMain.png, wheel-barrow.png, collection_jar_leaves.png) is named in the
  tab's note and never drawn: there is no art to draw. Plant Tycoon's stylesheet.css is not a
  picture.
* The compositions the game builds from several pictures are on the "Screens, bars and buttons"
  tab (pictures_screens).

The art is read straight from the game copy the Studio found (read only), not from its cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from picture_image import PictureError

PATCHER_ROOT = Path(__file__).resolve().parents[1] / "assets"
PATCHER_FOLDERS = {
    "fish": ("fish_tycoon_ds", "fish_tycoon_ds_store", "fish_tycoon_extra_tanks", "fish_tycoon_optimize_prices",
             "fish_tycoon_supply_slots"),
    "plant": ("plant_tycoon_flowers", "plant_tycoon_upgrades", "plant_tycoon_optimize_prices",
              "plant_tycoon_sort_seeds"),
}

@dataclass(frozen=True)
class Sheet:
    name: str
    cols: int
    rows: int
    category: str
    patcher: bool = False
    unused: bool = False
    readable: bool = True
    missing: bool = False                 # named by the game, not in its folder

    @property
    def frames(self) -> int:
        return max(1, self.cols) * max(1, self.rows)

    @property
    def key(self) -> str:
        return ("patcher:" if self.patcher else "") + self.name


FISH_RULES = (
    ("Fish", ("fish_", "seahorse", "ds_puffer", "ds_stingray", "ds_eel", "ick")),
    ("Items and tools", ("item_", "tool_", "supplyshop_itemforsale")),
    ("Tank pieces and ornaments", ("tank", "maintank", "wood", "plant", "shell", "pagoda", "diver", "column",
                                    "coral", "junk", "shadow", "forsale")),
    ("Effects and animations", ("sparkle", "flakes", "liquid", "eggs", "pellets", "anim_", "bubble")),
    ("Fish store and customers", ("people", "sellshop", "fishstore", "sellingarea", "thoughts", "hand",
                                  "sellfish")),
    ("Screens, buttons and UI", ("button", "rope", "custompopup", "arrow", "ui_", "options", "species_",
                                 "research", "font", "paddington", "questionmark", "mainmenu", "trophy",
                                 "intro", "help", "supply", "tankname", "supplypage", "maxprices", "optimize",
                                 "suppliesupgrades", "_bg", "credits", "gamewin", "splash", "meter", "delete me",
                                 "empty_thoughts", "30day", "canyoufind", "ftpre")),
)
PLANT_RULES = (
    ("Plants and flowers", ("plant parts", "cactus", "flower", "ivy_", "fern", "banana", "lemon", "willow",
                            "dieffenbachia", "bamboo tree", "caladium", "bonsai", "oak tree", "orchid",
                            "ananas", "bop", "pitcher", "unknown.png", "fruit_")),
    ("Items and tools", ("tools_grid", "chemicals_grid", "seed_grid", "soilbag", "waterbucket", "scissors",
                         "net.png", "hose", "pot.png", "goldpot", "soil.png", "pricetag", "ornaments_grid",
                         "collection", "bug", "checkmark", "spray", "pollen")),
    ("Nursery, greenhouse and scenery", ("bench", "birdh", "turtle", "greenhouse", "barrel", "bush", "zapper",
                                         "weathervane", "cherub", "sundial", "owl", "wheel", "gate", "fence",
                                         "fountain", "nursery", "cashreg", "sign", "plantables", "tables",
                                         "spiderweb", "waterfall", "foam", "waterspray", "grassknoll", "vane",
                                         "lightbeam", "plant_focus", "shadow", "soldsign")),
    ("Visitors", ("female", "male", "peep", "thought", "idea")),
    ("Effects and animations", ("sparkle", "falling", "dust", "flies", "small_bugs")),
    ("Screens, buttons and UI", ("button", "arrow", "dlg", "slider", "radio", "font", "logo", "bg", "meter",
                                 "checkbox", "photomsg", "loadcolor", "seedbox", "upgrades_link", "_link",
                                 "trashbin", "hand", "menu", "story", "loading", "splash", "help", "credits",
                                 "stylesheet", "30day", "ptwin", "addl")),
)
OTHER = "Other pictures"


def named(exe: bytes, key: str) -> bool:
    """Whether the executable (lower case) names the file: the whole name, or its stem (or the
    stem less trailing digits) as a whole string of its own, never as part of another name."""
    import re
    if key.encode("latin-1", "replace") + b"\x00" in exe:      # the whole name, as the end of a string
        return True
    stem = key.rsplit(".", 1)[0]
    for word in {stem, stem.rstrip("0123456789")}:
        if len(word) <= 3:
            continue
        pattern = rb"(?:^|[\x00/\\])" + re.escape(word.encode("latin-1", "replace")) + rb"\x00"
        if re.search(pattern, exe):
            return True
    return False


def category(game: str, name: str) -> str:
    low = name.casefold()
    for title, words in (FISH_RULES if game == "fish" else PLANT_RULES):
        if any(w in low for w in words):
            return title
    return OTHER


def categories(game: str) -> tuple:
    return tuple(t for t, _w in (FISH_RULES if game == "fish" else PLANT_RULES)) + (OTHER,)


def game_table(game: str) -> list:
    """The game's sprite records: (file, columns, rows), in the table's order, once each file."""
    if game == "fish":
        import pictures_fish_art_table as t
        records = list(t.FISH_SPRITES)
    else:
        import pictures_plant_data as D
        records = [D.SPRITES[k] for k in sorted(D.SPRITES)]
    seen, out = set(), []
    for name, cols, rows in records:
        if not name or name == "No Graphic" or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        out.append((name, cols, rows))
    return out


def patcher_grids(game: str) -> dict:
    """The grids the patcher's DLLs give their own sheets (file -> (columns, rows))."""
    out = {}
    if game == "fish":
        import pictures_fish as pf
        for index in range(pf.DS_SPRITE_BASE, pf.DS_SPRITE_DEAD + 1):
            name, cols, rows = pf.sheet(index)
            out[name.casefold()] = (cols, rows)
        for name, cols, rows in pf.STORE_SHEETS.values():
            out[name.casefold()] = (cols, rows)
    else:
        import pictures_plant_items as pit
        out[pit.CHEM_UPGRADES[0].casefold()] = pit.CHEM_UPGRADES[1:]
        out[pit.SEED_LEGENDARY[0].casefold()] = pit.SEED_LEGENDARY[1:]
        out["flowers64x64_grid.png"] = (12, 3)
        out["flowers64x64_grid_mask.png"] = (12, 3)
        out["upgrades_link.png"] = (1, 2)
    return out


def patcher_files(game: str) -> dict:
    out = {}
    for folder in PATCHER_FOLDERS[game]:
        images = PATCHER_ROOT / folder / "Images"
        if images.is_dir():
            for path in sorted(images.iterdir()):
                if path.suffix.casefold() == ".png":
                    out.setdefault(path.name, path)
    return out


class GameArt:
    """The sheets of a game copy (read only) and of the patcher, and their cells."""

    def __init__(self, game: str, copy) -> None:
        import breeding_pictures as bp
        import picture_image as pi
        self.game = game
        self.pi = pi
        self.source = bp.ArtSource(copy) if copy else None
        self.problem = "" if self.source is not None and not self.source.problem else \
            "No game copy was found: click \"Find game...\" for the game's own art."
        self._images: dict = {}
        self.sheets = self._sheets()
        self.by_key = {s.key: s for s in self.sheets}

    def _game_names(self) -> dict:
        if self.source is None:
            return {}
        names = {k: p.name for k, p in getattr(self.source, "_images", {}).items()}
        names.update({k: v for k, v in getattr(self.source, "_zip_names", {}).items() if "/" not in v})
        return names

    def _exe_text(self) -> bytes:
        """The game's executable, lower case: a file it names anywhere (a sprite record, a button,
        a background, a font) is used."""
        copy = getattr(self.source, "copy", None) if self.source is not None else None
        if copy is None:
            return b""
        for path in sorted(Path(copy).glob("*.exe")):
            if path.name.casefold() != "uninst.exe":
                try:
                    return path.read_bytes().lower()
                except OSError:
                    return b""
        return b""

    def _sheets(self) -> list:
        table = game_table(self.game)
        names = self._game_names()
        exe = self._exe_text()
        listed = set()
        out = []
        import picture_formats as F
        for name, cols, rows in table:
            listed.add(name.casefold())
            present = not names or name.casefold() in names
            readable = name.casefold().endswith(F.READABLE) and present
            out.append(Sheet(name, cols, rows, category(self.game, name), readable=readable,
                             missing=bool(names) and not present))
        for key, name in sorted(names.items()):
            if key not in listed:
                out.append(Sheet(name, 0, 0, category(self.game, name), unused=bool(exe) and not named(exe, key),
                                 readable=key.endswith(F.READABLE)))
        grids = patcher_grids(self.game)
        for name in patcher_files(self.game):
            cols, rows = grids.get(name.casefold(), (0, 0))
            out.append(Sheet(name, cols, rows, category(self.game, name), patcher=True))
        return out

    def drawable(self) -> list:
        return [s for s in self.sheets if s.readable]

    def not_drawn(self) -> list:
        return [s.name for s in self.sheets if not s.readable and not s.missing]

    def missing(self) -> list:
        return [s.name for s in self.sheets if s.missing]

    def image(self, sheet: Sheet):
        key = sheet.key.casefold()
        if key not in self._images:
            if sheet.patcher:
                data = patcher_files(self.game)[sheet.name].read_bytes()
            else:
                data = self.source.read(sheet.name) if self.source is not None else None
            if data is None:
                raise PictureError(f"{sheet.name} is not in the game copy found; click \"Find game...\".")
            import picture_formats as F
            self._images[key] = F.decode(sheet.name, data)
        return self._images[key]

    def render(self, key: str, frame: int):
        sheet = self.by_key.get(key)
        if sheet is None or not sheet.readable:
            raise PictureError("Pick a picture.")
        if not 0 <= frame < sheet.frames:
            raise PictureError("That picture has no such frame.")
        image = self.image(sheet)
        left, top, right, bottom = self.pi.cell_rect(image.width, image.height, sheet.cols, sheet.rows, frame)
        out = self.pi.Image(right - left, bottom - top)
        out.draw(image.sub(left, top, right - left, bottom - top), 0, 0)
        return out


# ------------------------------------------------------------------ the "All game art" tab

NOTE = ("Every picture file of the game (PNG, BMP, JPEG and GIF), one picture per sprite cell, cut as the game "
        "cuts it and drawn at full size and strength. (unused): a file the game's executable never names (no "
        "sprite record, button, background or font loads it), shown whole. (patcher): the patcher's own art. "
        "The game's compositions of several pieces are on the Screens, bars and buttons tab. ")


def fields(art: GameArt, spec: dict) -> dict:
    from picture_image import Option
    sheets = art.drawable()
    present = [c for c in categories(art.game) if any(s.category == c for s in sheets)] or [OTHER]
    category_ = spec.get("category") if spec.get("category") in present else present[0]
    in_category = [s for s in sheets if s.category == category_]
    options = tuple(Option(s.key, s.name, s.patcher, s.unused) for s in in_category) or \
        (Option("", "No pictures (no game copy found)"),)
    chosen = art.by_key.get(spec.get("sheet"))
    if chosen is None or chosen.category != category_ or not chosen.readable:
        chosen = in_category[0] if in_category else None
    if chosen is None:
        frames = (Option(0, "Frame 1"),)
    elif chosen.frames == 1:
        frames = (Option(0, "The whole picture"),)
    else:
        frames = tuple(Option(k, f"Frame {k + 1} of {chosen.frames}") for k in range(chosen.frames))
    return {"category": tuple(Option(c, c) for c in present), "sheet": options, "frame": frames}


def subject(art: GameArt):
    from picture_image import Field, Subject
    f = fields(art, {})
    note = NOTE
    missing = art.missing()
    if missing:
        note += ("Named by the game's sprite table but not in its folder, so not drawn (there is no art): "
                 + ", ".join(missing) + ". ")
    other = art.not_drawn()
    if other:
        note += "Not a picture: " + ", ".join(other) + "."
    if art.problem:
        note = art.problem + " " + note
    return Subject("art", "All game art", (
        Field("category", "Category", f["category"], f["category"][0].key),
        Field("sheet", "Picture file", f["sheet"], f["sheet"][0].key),
        Field("frame", "Frame", f["frame"], 0)), note)


def batch(art: GameArt) -> list:
    out = []
    for s in art.drawable():
        if not s.patcher and art.source is None:
            continue
        mark = " (patcher)" if s.patcher else " (unused)" if s.unused else ""
        stem = s.name.rsplit(".", 1)[0] + mark
        if s.frames == 1:
            out.append(((s.category,), stem, {"subject": "art", "category": s.category, "sheet": s.key, "frame": 0}))
        else:
            out += [((s.category, stem), f"{stem} - frame {k + 1}",
                     {"subject": "art", "category": s.category, "sheet": s.key, "frame": k}) for k in range(s.frames)]
    return out


def render(art: GameArt, spec: dict):
    try:
        frame = int(spec.get("frame") or 0)
    except (TypeError, ValueError):
        raise PictureError("Pick a frame.") from None
    return art.render(str(spec.get("sheet") or ""), frame)
