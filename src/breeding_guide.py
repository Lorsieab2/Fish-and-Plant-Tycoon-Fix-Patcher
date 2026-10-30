"""The Breeding Guide window (Tools tab -> "Breeding Guide..."), for both games.

One window, one model per game (docs/breeding-guide-interface.md):
src/breeding_fish.py for Fish Tycoon and src/breeding_plant.py for Plant
Tycoon, picked up as soon as that module exists. Tabs, each a sortable,
filterable sheet that exports to .xlsx or .csv:

* the parts (Fish: Fins and Bodies; Plant: Flowers and Foliage): how each is
  obtained, its rarity and the species that have it;
* Discovered Species (All Species with spoilers): the pairs that breed each
  species, by each part, and its prices with 0 and with max effects;
* Breeding Calculator: every child two parents can give, with its odds;
* Have -> Want: the shortest breeding chain from the species you have.

It reads one save slot and never writes anything but an export the player
asks for. With Show Spoilers off it shows the save's discovered species and
only what they reveal: their parts, and species made of parts already seen;
anything else is "Undiscovered species". The patcher's own species (DS
Exclusive Fish, Unused Flowers) are in only when the chosen game copy was
patched with that setting.

The sheets are plain data (build_* below), so the tests check them without a
window; the window only draws them.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import importlib
import json
from pathlib import Path
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from xml.sax.saxutils import escape
import zipfile

import save_tools

TITLES = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}
MODEL_MODULES = {"fish": "breeding_fish", "plant": "breeding_plant"}
KIND_TITLES = {"body": "Bodies", "fin": "Fins", "foliage": "Foliage", "flower": "Flowers"}
KIND_NAMES = {"body": "Body", "fin": "Fin", "foliage": "Foliage", "flower": "Flower"}
EFFECTS = (("none", "0 effects"), ("max", "max effects"))
UNDISCOVERED = "Undiscovered species"
COMING = "Plant Tycoon's Breeding Guide is coming in this update."


@dataclass(frozen=True)
class Part:                      # Fish: a body or a fin; Plant: a foliage or a flower
    kind: str
    index: int
    name: str
    patcher: bool
    how: str


@dataclass(frozen=True)
class Species:
    key: tuple[int, int]
    name: str
    parts: tuple[Part, Part]
    patcher: bool
    rarity: str
    value: int


@dataclass(frozen=True)
class Prices:
    best_per_day: int
    best_per_day_income: float
    highest_selling: int
    note: str


class Extras:
    """How each game's patcher species are recognised: the setting in the copy's patch log
    (written beside its .exe), the companion DLL in the copy, or the setting's data file
    beside the save."""

    SETTINGS = {
        "fish": ("ds_fish", "DS Exclusive Fish", "FishTycoonBugFixPatchLog.json",
                 "Fish Tycoon Fix Patcher DLLs\\DS Exclusive Fish.dll",
                 "Fish Tycoon Fix Patcher Data\\DS Fish {slot}.dat"),
        "plant": ("new_flowers", "Unused Flowers", "PlantTycoonFixPatchLog.json",
                  "Plant Tycoon Fix Patcher DLLs\\Unused Flowers.dll",
                  "Plant Tycoon Fix Patcher Data\\New Flowers {slot}.dat"),
    }


def setting_name(game_id: str) -> str:
    return Extras.SETTINGS[game_id][1]


def find_game_copy(save_folder: Path, parents) -> Path | None:
    """The game copy whose save folder this is: the game names its save folder after its
    .exe (README, "Where your saves go"), so "<parent>\\<name>\\<name>.exe"."""
    name = Path(save_folder).name
    for parent in parents:
        if not parent:
            continue
        folder = Path(parent) / name
        if (folder / f"{name}.exe").is_file():
            return folder
        if Path(parent).name.casefold() == name.casefold() and (Path(parent) / f"{name}.exe").is_file():
            return Path(parent)
    return None


def detect_extras(game_id: str, save_folder: Path | None, slot: int | None, parents=()) -> tuple[bool, str]:
    """(on, why): whether this save's game copy was patched with the setting that adds the
    patcher's species. Read only."""
    setting, title, log_name, dll, data = Extras.SETTINGS[game_id]
    if save_folder is None:
        return False, "No save chosen."
    copy = find_game_copy(save_folder, parents)
    if copy is not None:
        try:
            log = json.loads((copy / log_name).read_text(encoding="utf-8"))
            enabled = log.get("enabled_settings", [])
        except (OSError, ValueError, AttributeError):
            enabled = None
        if isinstance(enabled, list):
            if setting in enabled:
                return True, f"{title} is on in {copy} (its patch log)."
            return False, f"{title} is off in {copy} (its patch log)."
        if (copy / dll).is_file():
            return True, f"{title} is installed in {copy}."
        return False, f"{title} is not installed in {copy}."
    if slot is not None and (Path(save_folder) / data.format(slot=slot)).is_file():
        return True, f"This save has {title} data ({data.format(slot=slot)})."
    return False, f"{title} is not on for this save (no game copy or data file shows it)."


_MODELS: dict = {}
_PRICES: dict = {}


def prices_of(model, key, effects: str):
    """model.prices, kept for the session (a model is kept too, see load_model)."""
    cache_key = (id(model), tuple(key), effects)
    if cache_key not in _PRICES:
        _PRICES[cache_key] = model.prices(tuple(key), effects)
    return _PRICES[cache_key]


def load_model(game_id: str, game_folder=None, extras: bool = False):
    """The game's model, or None while its module is not in this build. One model per game,
    folder and extras for the session, so its worked-out prices are kept."""
    key = (game_id, str(game_folder or ""), bool(extras))
    if key in _MODELS:
        return _MODELS[key]
    try:
        module = importlib.import_module(MODEL_MODULES[game_id])
    except ImportError:
        return None
    _MODELS[key] = module.load(game_folder, extras)
    return _MODELS[key]


# ------------------------------------------------------------------ sheets


class Sheet:
    def __init__(self, title: str, columns: list[str], rows: list[list], *, kinds=None, tags=None,
                 keys=None, details=None, message: str = "") -> None:
        self.title = title
        self.columns = columns
        self.rows = rows
        self.kinds = kinds or ["text"] * len(columns)   # text, int, money, percent
        self.tags = tags or [()] * len(rows)
        self.keys = keys or [None] * len(rows)
        self.details = details or [""] * len(rows)
        self.message = message


def column_width(title: str, kind: str) -> int:
    """A column's starting width in pixels (every column can be dragged wider)."""
    if title in ("Index", "Step", "Discovered", "Rarity", "Species with it", "Base value", "Odds (%)"):
        return 90
    if title.startswith(("Bred from", "How it", "Species", "Notes")) and title != "Species":
        return 380 if title != "Notes" else 200
    if title in ("Species", "Child", "Patcher", "How") or title.startswith(("Mother", "Father", "Parent")):
        return 180 if title != "Patcher" else 130
    return 110 if kind != "text" else 120


def display(value, kind: str) -> str:
    if value is None or value == "":
        return ""
    if kind == "money" and isinstance(value, (int, float)):
        return f"{value:,.0f}"
    if kind == "percent" and isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value)


def sort_key(value):
    if isinstance(value, (int, float)):
        return (0, float(value), "")
    text = str(value or "")
    cleaned = text.replace(",", "").replace("$", "").rstrip("%").strip()
    try:
        return (0, float(cleaned), "")
    except ValueError:
        return (1, 0.0, text.casefold())


def filter_rows(sheet: Sheet, text: str) -> list[int]:
    """Indexes of the rows with `text` in any cell (case-insensitive)."""
    needle = text.strip().casefold()
    if not needle:
        return list(range(len(sheet.rows)))
    return [i for i, row in enumerate(sheet.rows)
            if any(needle in display(v, k).casefold() for v, k in zip(row, sheet.kinds))]


def _kinds_order(model) -> list[str]:
    kinds = getattr(model, "kinds", None)
    if kinds:
        return list(kinds)
    first = model.species()[0]
    return [first.parts[1].kind, first.parts[0].kind]


def _kind_name(model, kind: str) -> str:
    label = getattr(model, "part_label", None)
    return label(kind) if label else KIND_NAMES.get(kind, kind.title())


class View:
    """What the window shows for one model, save and spoiler choice."""

    def __init__(self, model, discovered: set | None, spoilers: bool) -> None:
        self.model = model
        self.spoilers = bool(spoilers)
        self.all_species = model.species()
        self.by_key = {tuple(s.key): s for s in self.all_species}
        self.has_save = discovered is not None             # None: no save was read
        self.discovered = {tuple(k) for k in (discovered or set()) if tuple(k) in self.by_key}
        self.kinds = _kinds_order(model)
        if self.spoilers:
            self.shown = list(self.all_species)
        else:
            self.shown = [s for s in self.all_species if tuple(s.key) in self.discovered]
        self.known_parts = {(p.kind, p.index) for s in self.shown for p in s.parts}
        if self.spoilers:
            self.known_parts |= {(p.kind, p.index) for k in self.kinds for p in model.parts(k)}

    def revealed(self, key) -> bool:
        """Spoiler-free to name: discovered, or made only of parts already seen."""
        if self.spoilers:
            return True
        species = self.by_key.get(tuple(key))
        return species is not None and all((p.kind, p.index) in self.known_parts for p in species.parts)

    def name(self, key) -> str:
        return self.by_key[tuple(key)].name if self.revealed(key) else UNDISCOVERED

    def part(self, kind: str, index: int):
        return next((p for p in self.model.parts(kind) if p.index == index), None)

    def species_choices(self) -> list:
        """The species a player can pick as a parent or as what they have."""
        return sorted(self.shown, key=lambda s: s.name.casefold())

    def want_choices(self) -> list:
        return sorted((s for s in self.all_species if self.revealed(s.key)), key=lambda s: s.name.casefold())

    # ---- parts
    def part_sheet(self, kind: str) -> Sheet:
        model = self.model
        title = KIND_TITLES.get(kind, kind.title())
        name = _kind_name(model, kind)
        rarity = getattr(model, "part_rarity", None)
        columns = [name, "Index", "How it is obtained", "Rarity", "Species with it", "Species", "Patcher"]
        kinds = ["text", "int", "text", "text", "int", "text", "text"]
        rows, tags, keys, details = [], [], [], []
        for part in model.parts(kind):
            if (part.kind, part.index) not in self.known_parts:
                continue
            having = sorted((s.name for s in self.shown if any(p.kind == kind and p.index == part.index
                                                                  for p in s.parts)), key=str.casefold)
            patcher = setting_name(model.game) if part.patcher else ""
            rows.append([part.name, part.index, part.how, rarity(part) if rarity else "", len(having),
                         ", ".join(having), patcher])
            tags.append(("patcher",) if part.patcher else ())
            keys.append((kind, part.index))
            details.append(f"{part.name} ({name.lower()} {part.index})\n\nHow it is obtained: {part.how}\n\n"
                           f"{len(having)} species: " + (", ".join(having) or "none shown yet"))
        message = "" if rows else "No species discovered in this save yet." if not self.spoilers else ""
        return Sheet(title, columns, rows, kinds=kinds, tags=tags, keys=keys, details=details, message=message)

    # ---- species
    def _combos(self, species, slot: int) -> str:
        part = species.parts[slot]
        combos = getattr(self.model, "part_combos", None)
        pairs = combos(part.kind, part.index) if combos is not None else self._part_table(slot).get(part.index, [])
        out = []
        for a, b, p in pairs:
            if (part.kind, a) not in self.known_parts or (part.kind, b) not in self.known_parts:
                continue
            pa, pb = self.part(part.kind, a), self.part(part.kind, b)
            if pa is None or pb is None:
                continue
            text = pa.name if a == b else f"{pa.name} x {pb.name}"
            if a == b:
                text = f"{pa.name} x {pa.name}"
            out.append(text + ("" if p >= 1 else f" ({100 * p:.0f}%)"))
        return "; ".join(out)

    def _part_table(self, slot: int) -> dict[int, list[tuple[int, int, float]]]:
        """For a model without part_combos: which pairs of this part give each index, with no
        effects, from the model's own children() (the other part held the same in both
        parents). Worked out once per part."""
        cache = self.__dict__.setdefault("_part_tables", {})
        if slot in cache:
            return cache[slot]
        first = self.all_species[0]
        other = first.key[1 - slot]
        kind = first.parts[slot].kind
        indexes = [p.index for p in self.model.parts(kind)]
        table: dict[int, list[tuple[int, int, float]]] = {}

        def key(i):
            return (i, other) if slot == 0 else (other, i)

        for n, a in enumerate(indexes):
            for b in indexes[n:]:
                if key(a) not in self.by_key or key(b) not in self.by_key:
                    continue
                chances: dict[int, float] = {}
                for child, p in self.model.children(key(a), key(b), "none"):
                    chances[child[slot]] = chances.get(child[slot], 0.0) + p
                for index, p in chances.items():
                    table.setdefault(index, []).append((a, b, p))
        cache[slot] = table
        return table

    def species_sheet(self) -> Sheet:
        model = self.model
        first = self.all_species[0]
        n0, n1 = _kind_name(model, first.parts[0].kind), _kind_name(model, first.parts[1].kind)
        note = getattr(model, "species_note", None)
        columns = ["Species", n0, n1, "Rarity", "Base value", f"Bred from ({n0.lower()})",
                   f"Bred from ({n1.lower()})",
                   "Best price per day (0 effects)", "Money per day (0 effects)",
                   "Best price per day (max effects)", "Money per day (max effects)",
                   "Highest price that sells (0 effects)", "Highest price that sells (max effects)",
                   "Notes", "Patcher"]
        kinds = ["text", "text", "text", "text", "int", "text", "text",
                 "int", "money", "int", "money", "int", "int", "text", "text"]
        if self.spoilers and self.has_save:
            columns.append("Discovered")
            kinds.append("text")
        rows, tags, keys, details = [], [], [], []
        for s in self.shown:
            p0, p1 = prices_of(model, s.key, "none"), prices_of(model, s.key, "max")
            patcher = setting_name(model.game) if s.patcher else ""
            row = [s.name, s.parts[0].name, s.parts[1].name, s.rarity, s.value, self._combos(s, 0),
                   self._combos(s, 1), p0.best_per_day, p0.best_per_day_income, p1.best_per_day,
                   p1.best_per_day_income, p0.highest_selling, p1.highest_selling,
                   note(s.key) if note else "", patcher]
            found = tuple(s.key) in self.discovered
            if self.spoilers and self.has_save:
                row.append("Yes" if found else "No")
            rows.append(row)
            tag = ("patcher",) if s.patcher else ()
            if self.spoilers and self.has_save and not found:
                tag += ("undiscovered",)
            tags.append(tag)
            keys.append(tuple(s.key))
            details.append(lambda s=s, p0=p0, p1=p1: self.species_details(s, p0, p1))   # on selection
        message = "" if rows else "No species discovered in this save yet. Tick Show Spoilers to see every species."
        title = "All Species" if self.spoilers else "Discovered Species"
        return Sheet(title, columns, rows, kinds=kinds, tags=tags, keys=keys, details=details, message=message)

    def species_details(self, s, p0, p1) -> str:
        lines = [f"{s.name}: {s.parts[0].name} {s.parts[0].kind}, {s.parts[1].name} {s.parts[1].kind}; "
                 f"{s.rarity}, base value {s.value}."]
        labels = getattr(self.model, "parent_labels", ("Parent 1", "Parent 2"))
        ways = self.model.ways_to_breed(s.key, "none")
        shown = [(m, f, p) for m, f, p in ways if self.revealed(m) and self.revealed(f)]
        if shown:
            lines.append(f"Best parents ({labels[0].split(':')[0]} x {labels[1].split(':')[0]}), 0 effects:")
            lines.extend(f"  {self.name(m)} x {self.name(f)}: {100 * p:.2f}%" for m, f, p in shown[:10])
        for label, prices in (("0 effects", p0), ("max effects", p1)):
            lines.append(f"Prices, {label}: best per day {prices.best_per_day} "
                         f"({prices.best_per_day_income:,.0f} a day), highest that sells "
                         f"{prices.highest_selling}. {prices.note}")
        return "\n".join(lines)

    # ---- the calculator and the planner
    def calculator_sheet(self, mother, father, effects: str) -> Sheet:
        first = self.all_species[0]
        n0, n1 = _kind_name(self.model, first.parts[0].kind), _kind_name(self.model, first.parts[1].kind)
        columns = ["Child", n0, n1, "Odds (%)", "Discovered"]
        kinds = ["text", "text", "text", "percent", "text"]
        rows, tags, keys = [], [], []
        if mother is not None and father is not None:
            for child, odds in self.model.children(tuple(mother), tuple(father), effects):
                s = self.by_key[tuple(child)]
                known = self.revealed(child)
                found = tuple(child) in self.discovered
                rows.append([s.name if known else UNDISCOVERED, s.parts[0].name if known else "?",
                             s.parts[1].name if known else "?", 100 * odds, "Yes" if found else "No"])
                tags.append((("patcher",) if s.patcher and known else ())
                            + (("undiscovered",) if self.has_save and not found else ()))
                keys.append(tuple(child))
        return Sheet("Breeding Calculator", columns, rows, kinds=kinds, tags=tags, keys=keys)

    def planner_sheet(self, have, want, effects: str) -> Sheet:
        labels = getattr(self.model, "parent_labels", ("Parent 1", "Parent 2"))
        columns = ["Step", "How", labels[0].split(":")[0], labels[1].split(":")[0], "Child", "Odds (%)"]
        kinds = ["int", "text", "text", "text", "text", "percent"]
        rows, keys = [], []
        message = ""
        if want is not None and have:
            if tuple(want) in {tuple(k) for k in have}:
                message = "You already have it."
            else:
                steps = self.model.plan([tuple(k) for k in have], tuple(want), effects)
                if not steps:
                    message = ("No breeding chain reaches it from these species"
                               + (" with 0 effects; try max effects." if effects == "none" else "."))
                else:
                    message = f"{len(steps)} step(s), the fewest generations first; scroll for all of them."
                for number, step in enumerate(steps, start=1):
                    m, f = step["parents"]
                    via = step.get("via", "breeding")
                    if via == "Mutation Liquid":          # one dose on a plant of the parent
                        row = [number, via, f"Mutation Liquid on {self.name(m)}", ""]
                    else:
                        row = [number, via.capitalize(), self.name(m), self.name(f)]
                    rows.append(row + [self.name(step["child"]), 100 * step["odds"]])
                    keys.append(tuple(step["child"]))
        return Sheet("Have to Want", columns, rows, kinds=kinds, keys=keys, message=message)


# ------------------------------------------------------------------ export


def export_csv(path, sheet: Sheet, row_indexes=None) -> None:
    indexes = range(len(sheet.rows)) if row_indexes is None else row_indexes
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(sheet.columns)
        for i in indexes:
            writer.writerow(["" if v is None else v for v in sheet.rows[i]])


_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _column(n: int) -> str:
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _cell(ref: str, value, header: bool = False) -> str:
    if isinstance(value, bool) or value is None or value == "":
        value = "" if value is None or value == "" else str(value)
    if isinstance(value, (int, float)) and not header:
        return f'<c r="{ref}"><v>{value!r}</v></c>' if isinstance(value, float) else f'<c r="{ref}"><v>{value}</v></c>'
    text = escape(_BAD_XML.sub("", str(value)))
    style = ' s="1"' if header else ""
    return f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{text}</t></is></c>'


def export_xlsx(path, sheet: Sheet, row_indexes=None) -> None:
    """A one-sheet .xlsx written with the standard library (zip + XML): a bold, frozen
    header row with a filter, numbers as numbers."""
    indexes = list(range(len(sheet.rows)) if row_indexes is None else row_indexes)
    name = re.sub(r"[\[\]:*?/\\]", " ", sheet.title)[:31] or "Sheet1"
    rows_xml = ["<row r=\"1\">" + "".join(_cell(f"{_column(c)}1", v, True) for c, v in enumerate(sheet.columns))
                + "</row>"]
    for r, i in enumerate(indexes, start=2):
        rows_xml.append(f'<row r="{r}">' + "".join(_cell(f"{_column(c)}{r}", v) for c, v in enumerate(sheet.rows[i]))
                        + "</row>")
    last = _column(len(sheet.columns) - 1)
    widths = []
    for c, title in enumerate(sheet.columns):
        longest = max([len(title)] + [len(display(sheet.rows[i][c], sheet.kinds[c])) for i in indexes[:400]])
        widths.append(f'<col min="{c + 1}" max="{c + 1}" width="{min(60, max(8, longest + 2))}" customWidth="1"/>')
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.styles+xml"/></Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
            f'<sheet name="{escape(name, {chr(34): "&quot;"})}" sheetId="1" r:id="rId1"/></sheets>'
            '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
            f"'{escape(name)}'!$A$1:${last}${len(indexes) + 1}</definedName></definedNames></workbook>"),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{rel}/styles" Target="styles.xml"/></Relationships>'),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<styleSheet xmlns="{main}">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{main}" xmlns:r="{rel}">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
            'state="frozen"/></sheetView></sheetViews>'
            f'<cols>{"".join(widths)}</cols><sheetData>{"".join(rows_xml)}</sheetData>'
            f'<autoFilter ref="A1:{last}{len(indexes) + 1}"/></worksheet>'),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, text in files.items():
            info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))


def read_xlsx(path) -> list[list[str]]:
    """The cells of an .xlsx written by export_xlsx, as text (for the tests)."""
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    out = []
    for row in root.find("m:sheetData", ns):
        cells = []
        for c in row:
            if c.get("t") == "inlineStr":
                cells.append("".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t")))
            else:
                v = c.find("m:v", ns)
                cells.append("" if v is None else v.text)
        out.append(cells)
    return out


# ------------------------------------------------------------------ help

HELP = (
    "Breeding Guide",
    [
        "A spreadsheet of each game's breeding: every part (Fish Tycoon: fins and bodies; Plant Tycoon: "
        "flowers and foliage), how it is obtained, its rarity and the species that have it; and every species, "
        "the pairs of parts that breed it and its prices. Pick the game, a save folder and a player: it only "
        "reads that save and never changes it.",
        "Spoilers: it opens on the save's discovered species and shows only what they reveal (their parts, "
        "and species made of parts you have already seen). Under Options, Show Spoilers shows every species, "
        "the full charts and every price; the choice is remembered.",
        "Patcher species (DS Exclusive Fish, Unused Flowers) are listed only when the save's game copy was "
        "patched with that setting: its patch log beside the .exe says so, or the setting's data file is "
        "beside the save. They are marked in the Patcher column.",
        "Fish Tycoon breeding, from the game's code: the baby's body is the mother's and the father's bodies "
        "averaged and rounded down, and the same for the fin. The mother is the fish already in the isolation "
        "tank, the father the fish you drop on it. A pair with a DS gene uses the DS game's rule: an odd total "
        "rounds up or down at random, one roll per litter shared by body and fin. Max effects adds a live adult "
        "Magic Fish of Mutation in the mother's tank: 16.02% per litter to step the father's body or fin one "
        "place first. The Fertility fish and plant add babies but do not change each baby's odds.",
        "Prices, from the game's selling code: once a real-time second each adult in the selling tank rolls "
        "Random(900) <= T: T = 30K at half the base price B or less, 10K below B, 4K from B to 1.5B, K above, "
        "and never at 2B or more, with K = (customers browsing + 2) / 2; after a sale nothing sells for 5 "
        "seconds. \"Best price per day\" is the asking price that earns the most a day; \"Highest price that "
        "sells\" is 2B - 1.",
        "Assumptions: selling runs on real time, so the game speed does not matter. A full selling tank (21 "
        "adults of the species, refilled at once) and the selling scene open all day. 0 effects: Advertising "
        "level 1 and nobody browsing, the lowest odds. Max effects: Advertising level 3 (B + 1/10, then + 1/7), "
        "all 6 ornaments and the Golden Seahorse, and the whole crowd (66 or 72 customers) browsing, the "
        "highest odds. Your shop is between the two.",
        "Plant Tycoon, from its code: breeding has no luck, each gene of the seed is the parents' average "
        "rounded up; only Mutation Liquid adds odds, and with max effects a chain step can be \"Mutation "
        "Liquid on\" a plant. Its prices assume every visitor up to the limit is browsing (an upper bound), "
        "and because a plant keeps growing, its best price per day is its highest price that sells. With max "
        "effects a chain can be long (the fewest generations, not the fewest steps): the step count is shown "
        "and the list scrolls. Each species' details list the exact assumptions.",
        "Click a column header to sort, and type in Search to filter. Export saves the open sheet as .xlsx or "
        ".csv. The Breeding Calculator lists every child two parents can give, with its odds; Have to Want finds "
        "the shortest breeding chain from the species you have to the one you want.",
    ],
)


def show_help(parent: tk.Misc) -> tk.Toplevel:
    title, lines = HELP
    window = tk.Toplevel(parent)
    window.title(f"How to use: {title}")
    window.transient(parent)
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
    for line in lines:
        ttk.Label(frame, text=line, wraplength=480, justify="left").pack(anchor="w", pady=(0, 6))
    ttk.Button(frame, text="Close", command=window.destroy).pack(anchor="e", pady=(6, 0))
    window.bind("<Escape>", lambda _e: window.destroy())
    return window


# ------------------------------------------------------------------ the window

_open_window: "BreedingGuide | None" = None


def open_window(parent: tk.Misc, game_id: str = "fish", *, settings: dict | None = None,
                save_settings=None, documents: Path | None = None, game_parents=()) -> "BreedingGuide":
    """Open (or raise) the Breeding Guide. `settings` holds "show_spoilers", remembered by
    `save_settings()`; `game_parents` are folders the game copies may sit in."""
    global _open_window
    if _open_window is not None and _open_window.window.winfo_exists():
        _open_window.window.deiconify()
        _open_window.window.lift()
        if game_id in TITLES:
            _open_window.game_var.set(TITLES[game_id])
        return _open_window
    _open_window = BreedingGuide(parent, game_id, settings=settings, save_settings=save_settings,
                                 documents=documents, game_parents=game_parents)
    return _open_window


class BreedingGuide:
    def __init__(self, parent: tk.Misc, game_id: str = "fish", *, settings: dict | None = None,
                 save_settings=None, documents: Path | None = None, game_parents=()) -> None:
        self.settings = settings if settings is not None else {}
        self.save_settings = save_settings
        self.documents = documents
        self.game_parents = list(game_parents)
        self.window = tk.Toplevel(parent)
        self.window.title("Breeding Guide")
        screen_w, screen_h = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        width, height = min(1180, screen_w - 60), min(800, screen_h - 110)
        self.window.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}+{max(0, (screen_h - height) // 3)}")
        self.window.minsize(min(760, width), min(500, height))
        self.window.bind("<Escape>", lambda _e: self.close())
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.game_var = tk.StringVar(value=TITLES.get(game_id, TITLES["fish"]))
        self.folder_var = tk.StringVar()
        self.slot_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.spoilers_var = tk.BooleanVar(value=bool(self.settings.get("show_spoilers", False)))
        self.search_var = tk.StringVar()
        self.effects_var = tk.StringVar(value="none")
        self.folders: list[Path] = []
        self.slots: list[tuple[int, str]] = []
        self.model = None
        self.view: View | None = None
        self.sheets: dict[str, Sheet] = {}
        self.trees: dict[str, ttk.Treeview] = {}
        self.shown_rows: dict[str, list[int]] = {}
        self.sort_state: dict[str, tuple[int, bool]] = {}
        self.extras_reason = ""
        self._build()
        self.game_var.trace_add("write", lambda *_a: self._load_folders())
        self.spoilers_var.trace_add("write", lambda *_a: self._spoilers_changed())
        self.search_var.trace_add("write", lambda *_a: self._refill_current())
        self._load_folders()

    # ---- layout
    def _build(self) -> None:
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="Game:").pack(side="left")
        ttk.Combobox(top, textvariable=self.game_var, values=list(TITLES.values()), state="readonly",
                     width=14).pack(side="left", padx=(4, 12))
        ttk.Label(top, text="Save folder:").pack(side="left")
        self.folder_box = ttk.Combobox(top, textvariable=self.folder_var, state="readonly", width=34)
        self.folder_box.pack(side="left", padx=(4, 12))
        self.folder_box.bind("<<ComboboxSelected>>", lambda _e: self._load_slots())
        ttk.Label(top, text="Player:").pack(side="left")
        self.slot_box = ttk.Combobox(top, textvariable=self.slot_var, state="readonly", width=26)
        self.slot_box.pack(side="left", padx=(4, 12))
        self.slot_box.bind("<<ComboboxSelected>>", lambda _e: self._reload())
        ttk.Button(top, text="?", width=2, command=lambda: show_help(self.window)).pack(side="right")
        ttk.Label(outer, textvariable=self.status_var, foreground="#245a9a", wraplength=1100,
                  justify="left").pack(anchor="w", pady=(6, 0))

        options = ttk.LabelFrame(outer, text="Options", padding=(10, 4))
        options.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(options, text="Show Spoilers", variable=self.spoilers_var).pack(side="left")
        ttk.Label(options, text="(every species, the full charts and every price)").pack(side="left", padx=(6, 18))
        ttk.Label(options, text="Search:").pack(side="left")
        self.search_entry = ttk.Entry(options, textvariable=self.search_var, width=28)
        self.search_entry.pack(side="left", padx=(4, 4))
        ttk.Button(options, text="Clear", command=lambda: self.search_var.set("")).pack(side="left")

        self.body = ttk.Frame(outer)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(8, 0))
        self.export_xlsx_button = ttk.Button(bottom, text="Export .xlsx...", command=lambda: self.export("xlsx"))
        self.export_xlsx_button.pack(side="left")
        self.export_csv_button = ttk.Button(bottom, text="Export .csv...", command=lambda: self.export("csv"))
        self.export_csv_button.pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="Close", command=self.close).pack(side="right")

    def close(self) -> None:
        global _open_window
        if _open_window is self:
            _open_window = None
        if self.window.winfo_exists():
            self.window.destroy()

    @property
    def game_id(self) -> str:
        return next((g for g, t in TITLES.items() if t == self.game_var.get()), "fish")

    # ---- save choice
    def _load_folders(self) -> None:
        try:
            self.folders = save_tools.save_folders(self.game_id, self.documents)
        except OSError:
            self.folders = []
        self.folder_box.configure(values=[f.name for f in self.folders])
        if self.folders:
            modded = [i for i, f in enumerate(self.folders) if " - Modded" in f.name]
            self.folder_box.current(modded[0] if modded else 0)
        else:
            self.folder_var.set("")
        self._load_slots()

    def _load_slots(self) -> None:
        self.slots = []
        folder = self.current_folder()
        if folder is not None:
            try:
                names = save_tools.read_slot_names(self.game_id, folder)
            except (OSError, save_tools.SaveToolError):
                names = []
            self.slots = [(slot, name) for slot, name in enumerate(names, start=1)
                          if save_tools.slot_is_active(self.game_id, folder, slot, name)]
        self.slot_box.configure(values=[f"Player {slot}: {name}" for slot, name in self.slots])
        if self.slots:
            self.slot_box.current(0)
        else:
            self.slot_var.set("")
        self._reload()

    def current_folder(self) -> Path | None:
        index = self.folder_box.current()
        return self.folders[index] if 0 <= index < len(self.folders) else None

    def current_slot(self) -> int | None:
        index = self.slot_box.current()
        return self.slots[index][0] if 0 <= index < len(self.slots) else None

    def _spoilers_changed(self) -> None:
        self.settings["show_spoilers"] = bool(self.spoilers_var.get())
        if self.save_settings is not None:
            try:
                self.save_settings()
            except Exception:                      # remembering is a convenience, never an error
                pass
        self._refresh()

    # ---- the model and the sheets
    def _reload(self) -> None:
        folder, slot = self.current_folder(), self.current_slot()
        extras, self.extras_reason = detect_extras(self.game_id, folder, slot, self.game_parents)
        copy = find_game_copy(folder, self.game_parents) if folder is not None else None
        self.model = load_model(self.game_id, copy, extras)
        self.discovered: set | None = None
        self.read_problem = ""
        if self.model is not None and folder is not None and slot is not None:
            try:
                self.discovered = set(self.model.discovered(folder, slot))
            except Exception as exc:               # an unreadable save shows as no discoveries
                self.read_problem = f"The save could not be read: {exc}"
                self.discovered = set()
        self._refresh()

    def _refresh(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self.trees.clear()
        self.sheets.clear()
        if self.model is None:
            ttk.Label(self.body, text=COMING, font=("Segoe UI", 11)).pack(anchor="w", pady=20)
            self.status_var.set(COMING)
            for button in (self.export_xlsx_button, self.export_csv_button):
                button.state(["disabled"])
            self.view = None
            return
        for button in (self.export_xlsx_button, self.export_csv_button):
            button.state(["!disabled"])
        self.view = View(self.model, self.discovered, self.spoilers_var.get())
        found = len(self.view.discovered)
        total = len(self.view.all_species)
        save = (f"{self.folder_var.get()}, {self.slot_var.get()}: {found} of {total} species discovered."
                if self.discovered is not None else "No save chosen: no species are discovered.")
        self.status_var.set(" ".join(x for x in (save, self.read_problem, "Patcher species: " + self.extras_reason) if x))

        self.notebook = ttk.Notebook(self.body)
        self.notebook.pack(fill="both", expand=True)
        for kind in self.view.kinds:
            self._add_sheet_tab(f"part:{kind}", self.view.part_sheet(kind))
        self._add_sheet_tab("species", self.view.species_sheet())
        self._add_calculator()
        self._add_planner()
        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self._refill_current())

    def _sheet_frame(self, sheet_id: str, parent, sheet: Sheet, details: bool = True) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        message = ttk.Label(frame, text=sheet.message, foreground="#a01010")
        message.pack(anchor="w")
        grid = ttk.Frame(frame)
        grid.pack(fill="both", expand=True)
        tree = ttk.Treeview(grid, columns=[f"c{i}" for i in range(len(sheet.columns))], show="headings",
                            selectmode="browse", height=12)
        ys = ttk.Scrollbar(grid, orient="vertical", command=tree.yview)
        xs = ttk.Scrollbar(grid, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        grid.rowconfigure(0, weight=1)
        grid.columnconfigure(0, weight=1)
        for i, title in enumerate(sheet.columns):
            tree.heading(f"c{i}", text=title, command=lambda c=i, s=sheet_id: self.sort(s, c))
            width = column_width(title, sheet.kinds[i])
            tree.column(f"c{i}", width=width, minwidth=50, stretch=False,
                        anchor="w" if sheet.kinds[i] == "text" else "e")
        tree.tag_configure("patcher", foreground="#5a3d00")
        tree.tag_configure("undiscovered", foreground="#7a7a7a")
        tree.message_label = message
        self.trees[sheet_id] = tree
        self.sheets[sheet_id] = sheet
        if details:
            text = tk.Text(frame, height=6, wrap="word", font=("Segoe UI", 9), relief="flat", borderwidth=1)
            text.pack(fill="x", pady=(6, 0))
            text.configure(state="disabled")
            tree.bind("<<TreeviewSelect>>", lambda _e, s=sheet_id, t=text: self._show_details(s, t))
        self._fill(sheet_id)

    def _add_sheet_tab(self, sheet_id: str, sheet: Sheet) -> None:
        tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab, text=sheet.title)
        self._sheet_frame(sheet_id, tab, sheet)

    def _species_label(self, s) -> str:
        return f"{s.name}  ({s.parts[0].name} / {s.parts[1].name})"

    def _effects_row(self, parent, command) -> None:
        row = ttk.Frame(parent)
        row.pack(anchor="w", pady=(4, 0))
        ttk.Label(row, text="Effects:").pack(side="left")
        for value, label in EFFECTS:
            ttk.Radiobutton(row, text=label.capitalize(), value=value, variable=self.effects_var,
                            command=command).pack(side="left", padx=(6, 0))
        effects = " ".join(self.model.effects_max())
        ttk.Label(parent, text=f"Max effects: {effects}", wraplength=1050, justify="left",
                  foreground="#555555").pack(anchor="w", pady=(2, 4))

    def _add_calculator(self) -> None:
        tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab, text="Breeding Calculator")
        labels = getattr(self.model, "parent_labels", ("Parent 1", "Parent 2"))
        choices = self.view.species_choices()
        self.calc_choices = choices
        values = [self._species_label(s) for s in choices]
        pick = ttk.Frame(tab)
        pick.pack(fill="x")
        self.calc_vars = []
        self.calc_boxes = []
        for row, label in enumerate(labels):
            ttk.Label(pick, text=label + ":").grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            box = ttk.Combobox(pick, textvariable=var, values=values, state="readonly", width=48)
            box.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=2)
            box.bind("<<ComboboxSelected>>", lambda _e: self.calculate())
            if values:
                box.current(min(row, len(values) - 1))
            self.calc_vars.append(var)
            self.calc_boxes.append(box)
        self._effects_row(tab, self.calculate)
        self.calc_tab = tab
        self._sheet_frame("calculator", tab, self.view.calculator_sheet(None, None, "none"), details=False)
        self.calculate()

    def calculate(self) -> None:
        if self.view is None or "calculator" not in self.trees:
            return
        picked = [box.current() for box in self.calc_boxes]
        keys = [self.calc_choices[i].key if 0 <= i < len(self.calc_choices) else None for i in picked]
        sheet = self.view.calculator_sheet(keys[0], keys[1], self.effects_var.get())
        if not self.calc_choices:
            sheet.message = "No species discovered in this save yet. Tick Show Spoilers to pick any species."
        self._replace_sheet("calculator", sheet)

    def _add_planner(self) -> None:
        tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab, text="Have to Want")
        choices = self.view.species_choices()
        self.have_choices = choices
        wants = self.view.want_choices()
        self.want_choices = wants
        top = ttk.Frame(tab)
        top.pack(fill="x")
        left = ttk.Frame(top)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="The species you have (Ctrl-click for more):").pack(anchor="w")
        box = ttk.Frame(left)
        box.pack(fill="both")
        self.have_list = tk.Listbox(box, selectmode="extended", height=6, width=48, exportselection=False,
                                    font=("Segoe UI", 9))
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.have_list.yview)
        self.have_list.configure(yscrollcommand=scroll.set)
        self.have_list.pack(side="left", fill="both")
        scroll.pack(side="left", fill="y")
        for s in choices:
            self.have_list.insert("end", self._species_label(s))
        discovered = self.view.discovered
        for i, s in enumerate(choices):
            if tuple(s.key) in discovered:
                self.have_list.selection_set(i)
        right = ttk.Frame(top)
        right.pack(side="left", fill="both", padx=(16, 0))
        ttk.Label(right, text="The species you want:").pack(anchor="w")
        self.want_box = ttk.Combobox(right, values=[self._species_label(s) for s in wants], state="readonly",
                                     width=48)
        self.want_box.pack(anchor="w", pady=(2, 6))
        buttons = ttk.Frame(right)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Find the Chain", command=self.plan).pack(side="left")
        ttk.Button(buttons, text="Select All", command=lambda: self.have_list.selection_set(0, "end")).pack(
            side="left", padx=(8, 0))
        ttk.Button(buttons, text="Select None", command=lambda: self.have_list.selection_clear(0, "end")).pack(
            side="left", padx=(8, 0))
        self._effects_row(tab, self.plan)
        self._sheet_frame("planner", tab, self.view.planner_sheet([], None, "none"), details=False)

    def plan(self) -> None:
        if self.view is None or "planner" not in self.trees:
            return
        have = [self.have_choices[i].key for i in self.have_list.curselection()]
        index = self.want_box.current()
        want = self.want_choices[index].key if 0 <= index < len(self.want_choices) else None
        sheet = self.view.planner_sheet(have, want, self.effects_var.get())
        if want is None:
            sheet.message = "Choose the species you want."
        elif not have:
            sheet.message = "Select at least one species you have."
        self.window.configure(cursor="watch")
        try:
            self._replace_sheet("planner", sheet)
        finally:
            self.window.configure(cursor="")

    def _replace_sheet(self, sheet_id: str, sheet: Sheet) -> None:
        self.sheets[sheet_id] = sheet
        self.trees[sheet_id].message_label.configure(text=sheet.message)
        self.sort_state.pop(sheet_id, None)
        self._fill(sheet_id)

    # ---- filling, sorting, filtering
    def current_sheet_id(self) -> str | None:
        if self.view is None:
            return None
        try:
            index = self.notebook.index(self.notebook.select())
        except tk.TclError:
            return None
        ids = [f"part:{k}" for k in self.view.kinds] + ["species", "calculator", "planner"]
        return ids[index] if 0 <= index < len(ids) else None

    def _refill_current(self) -> None:
        sheet_id = self.current_sheet_id()
        if sheet_id is not None:
            self._fill(sheet_id)

    def _fill(self, sheet_id: str) -> None:
        tree, sheet = self.trees[sheet_id], self.sheets[sheet_id]
        rows = filter_rows(sheet, self.search_var.get())
        sort = self.sort_state.get(sheet_id)
        if sort is not None:
            column, descending = sort
            rows.sort(key=lambda i: sort_key(sheet.rows[i][column]), reverse=descending)
        tree.delete(*tree.get_children())
        for i in rows:
            tree.insert("", "end", iid=str(i), values=[display(v, k) for v, k in zip(sheet.rows[i], sheet.kinds)],
                        tags=sheet.tags[i])
        self.shown_rows[sheet_id] = rows
        for c, title in enumerate(sheet.columns):
            arrow = ""
            if sort is not None and sort[0] == c:
                arrow = " â–¼" if sort[1] else " â–²"
            tree.heading(f"c{c}", text=title + arrow)

    def sort(self, sheet_id: str, column: int) -> None:
        current = self.sort_state.get(sheet_id)
        descending = current is not None and current[0] == column and not current[1]
        self.sort_state[sheet_id] = (column, descending)
        self._fill(sheet_id)

    def _show_details(self, sheet_id: str, text: tk.Text) -> None:
        tree, sheet = self.trees[sheet_id], self.sheets[sheet_id]
        picked = tree.selection()
        body = sheet.details[int(picked[0])] if picked else ""
        if callable(body):
            body = body()
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", body)
        text.configure(state="disabled")

    # ---- export
    def export(self, fmt: str, path: str | None = None) -> str | None:
        sheet_id = self.current_sheet_id()
        if sheet_id is None:
            return None
        sheet = self.sheets[sheet_id]
        if path is None:
            default = f"{self.game_var.get()} {sheet.title}.{fmt}"
            path = filedialog.asksaveasfilename(
                parent=self.window, title=f"Export {sheet.title}", defaultextension=f".{fmt}",
                initialfile=default, filetypes=[("Excel workbook", "*.xlsx")] if fmt == "xlsx" else [("CSV", "*.csv")])
            if not path:
                return None
        rows = self.shown_rows.get(sheet_id)
        try:
            (export_xlsx if fmt == "xlsx" else export_csv)(path, sheet, rows)
        except OSError as exc:
            messagebox.showerror("Breeding Guide", f"Nothing was exported:\n\n{exc}", parent=self.window)
            return None
        self.status_var.set(f"Exported {len(rows or sheet.rows)} row(s) of {sheet.title} to {path}.")
        return path
