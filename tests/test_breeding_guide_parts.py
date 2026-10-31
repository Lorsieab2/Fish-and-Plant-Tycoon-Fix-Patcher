"""The Breeding Guide's part tabs with Show Spoilers off: exactly the parts the save has
discovered, in both games, with the patcher's parts (DS Exclusive Fish, Unused Flowers) only
when the save has that setting's data file; nothing undiscovered named anywhere a spoiler-off
view or export shows; the counts; and everything with spoilers on.

The rule (src/breeding_guide.py, View): neither game keeps a flag per part, so a part is
discovered when a species the save has discovered has it. The executable checks below pin the
game code that rule rests on (they skip without the vanilla executables). Every save here is a
small synthetic file in a temporary folder, never the owner's.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_fish as bf  # noqa: E402
import breeding_guide as bg  # noqa: E402
import breeding_pictures as bpx  # noqa: E402
import breeding_plant as bp  # noqa: E402
from test_breeding_fish import make_save, make_sidecar  # noqa: E402

VANILLA = Path(os.environ.get("LDW_VANILLA_GAMES", str(
    Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games")))
FISH_EXE = Path(os.environ.get("FISH_TYCOON_VANILLA", str(VANILLA / "Fish Tycoon"))) / "Fish Tycoon.exe"
PLANT_EXE = VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"

# Fish: (body, fin) -> asking price. Bodies 0 Shark, 4 Fatfish, 10 Goldbulb, 20 Spotanus;
# fins 0 Silky, 4 Pink, 16 Greenfin. Silky Fatfish (4, 0) and Pink Shark (0, 4) are made of
# discovered parts but are not discovered themselves.
FISH_FOUND = {(0, 0): 4, (4, 4): 5, (10, 4): 17, (20, 16): 48}
FISH_BODIES = {"Shark", "Fatfish", "Goldbulb", "Spotanus"}
FISH_FINS = {"Silky", "Pink", "Greenfin"}
# DS: a PC body with a DS fin (in the save's spare columns) and a DS body (in the sidecar).
DS_IN_SAVE = {(2, 25): 30}               # Angel Arrowfish: fin Angel
DS_IN_SIDECAR = {(25, 1): 20}            # Tiger Bicolor: body Bicolor, fin Tiger

# Plant: (foliage, flower). Foliages 1 Reptans, 5 Astera, 9 Maranta; flowers 1 Spotted,
# 5 Bluestar, 3 Daisy. New flower 30 Silvermist on foliage 5, from the sidecar.
PLANT_FOUND = {(1, 1), (5, 5), (9, 3)}
PLANT_FOLIAGES = {"Reptans", "Astera", "Maranta"}
PLANT_FLOWERS = {"Spotted", "Bluestar", "Daisy"}
NEW_FOUND = {(5, 30)}

# Phrases of the guide's own text that contain a part's word without naming that part.
GENERIC = ("Golden Seahorse", "Golden Guppy", "Golden Berries of Wealth", "Magic Fish of Mutation")


def make_plant_save(folder: Path, slot: int, found) -> Path:
    """A Plant Tycoon save of the stock size with the discovered byte of each species in
    `found` set (state + 0x64 + foliage x 24 + flower)."""
    body = bytearray(bp.SAVE_BODY)
    for foliage, flower in found:
        body[bp.DISCOVERED_STATE - 8 + foliage * 24 + flower] = 1
    path = folder / f"Plant Tycoon{slot}.ldw"
    path.write_bytes(b"ldwg" + bytes(20) + bytes(body))
    return path


def make_new_flowers(folder: Path, slot: int, found) -> Path:
    """Unused Flowers' sidecar (ftfp_new_flowers.c: magic, version, size, price[24][14],
    discovered[24][14])."""
    flags = bytearray(24 * 14)
    for foliage, flower in found:
        flags[foliage * 14 + flower - 24] = 1
    body = bytes(24 * 14 * 4) + bytes(flags)
    side = folder / "Plant Tycoon Fix Patcher Data"
    side.mkdir(exist_ok=True)
    path = side / f"New Flowers {slot}.dat"
    path.write_bytes(struct.pack("<3I", bp.SIDECAR_MAGIC, bp.SIDECAR_VERSION, len(body)) + body)
    return path


def view_for(game: str, folder: Path, slot: int, spoilers: bool) -> bg.View:
    """The view the window builds for this save: the setting from its data file (no game copy
    here), the model, the save's discovered species."""
    extras, _why = bg.detect_extras(game, folder, slot, ())
    model = (bf if game == "fish" else bp).load(None, extras)
    return bg.View(model, model.discovered(folder, slot), spoilers)


def names_in(sheet: bg.Sheet) -> set[str]:
    return {row[0] for row in sheet.rows}


def every_text(view: bg.View) -> list[str]:
    """Every text a view shows: the part sheets (cells, details, the count), the species sheet
    (cells and the details worked out on selection), the calculator for every pair of the
    species it offers and the planner for every one, with each effects choice, the effects
    labels, and the picture tabs' names and headers."""
    texts: list[str] = []

    def sheet_text(sheet: bg.Sheet) -> None:
        texts.extend([sheet.title, sheet.header, sheet.message, sheet.intro] + list(sheet.columns))
        texts.extend(str(c) for row in sheet.rows for c in row)
        texts.extend(d() if callable(d) else d for d in sheet.details)

    for kind in view.kinds:
        sheet_text(view.part_sheet(kind))
    sheet_text(view.species_sheet())
    choices = [s.key for s in view.species_choices()]
    for value, label in view.effects_choices():
        texts.append(label)
        for a in choices:
            for b in choices:
                sheet_text(view.calculator_sheet(a, b, value))
        for want in choices:
            sheet_text(view.planner_sheet([k for k in choices if k != want], want, value))
    for tab_id, _title in bpx.TABS[view.model.game]:
        texts.append(bpx.header_for(view, tab_id))
        texts.extend(item.name for group in bpx.items_for(view, tab_id) for item in group.items)
    if view.model.game == "plant":                       # the Seed Pictures grid
        columns, rows = bg.seed_grid(view)
        texts.extend(columns)
        texts.extend(label for _part, label, _cells in rows)
        texts.extend(f"{i.name}, {i.tier}" for _part, _label, cells in rows for i in cells)
    import breeding_collectopedia as bc                  # the Collectopedia, every filter
    texts.extend(bc.Collectopedia(view).texts())
    return texts


def undiscovered_words(view: bg.View) -> set[str]:
    """The names a spoiler-off view must never show: every undiscovered part and species."""
    words = {p.name for k in view.kinds for p in view.model.parts(k) if (p.kind, p.index) not in view.found_parts}
    words |= {s.name.strip() for s in view.all_species if tuple(s.key) not in view.discovered}
    return words


def assert_never_named(case: unittest.TestCase, texts, words) -> None:
    blob = "\n".join(t for t in texts if t)
    for phrase in GENERIC:
        blob = blob.replace(phrase, "")
    blob = re.sub(r"\s+", " ", blob)
    for word in sorted(words):
        pattern = r"(?<![\w-])" + re.escape(re.sub(r"\s+", " ", word)) + r"(?![\w-])"
        found = re.search(pattern, blob)
        case.assertIsNone(found, f"{word!r} is named: ...{blob[max(0, found.start() - 80):found.end() + 80] if found else ''}...")


class FishPartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_stock_save_shows_exactly_its_parts(self) -> None:
        make_save(self.folder, 1, FISH_FOUND)
        view = view_for("fish", self.folder, 1, spoilers=False)
        self.assertFalse(view.model.extras)
        self.assertEqual(names_in(view.part_sheet("body")), FISH_BODIES)
        self.assertEqual(names_in(view.part_sheet("fin")), FISH_FINS)
        self.assertEqual(view.part_sheet("body").header, "4 of 21 bodies discovered.")
        self.assertEqual(view.part_sheet("fin").header, "3 of 21 fins discovered.")
        self.assertEqual(view.part_count("fin"), (3, 21))
        # the picture tabs: the same parts, no "?"
        for kind, expected in (("body", FISH_BODIES), ("fin", FISH_FINS)):
            items = [i for g in bpx.part_items(view, kind) for i in g.items]
            self.assertEqual({i.name for i in items}, expected)
            self.assertTrue(all(i.art and not i.hidden for i in items))
            self.assertEqual(bpx.header_for(view, f"pictures:{kind}"), view.part_count_text(kind))

    def test_ds_parts_only_with_the_ds_fish_data_file(self) -> None:
        make_save(self.folder, 1, {**FISH_FOUND, **DS_IN_SAVE}, ds_columns=True)
        # no "DS Fish 1.dat" and no game copy saying otherwise: the setting is off for this
        # save, so only the stock 21 x 21 is read and no DS part is listed or counted
        view = view_for("fish", self.folder, 1, spoilers=False)
        self.assertFalse(view.model.extras)
        self.assertEqual(names_in(view.part_sheet("fin")), FISH_FINS)
        self.assertEqual(view.part_count("body"), (4, 21))
        self.assertEqual(view.part_count("fin"), (3, 21))
        self.assertNotIn("Angel", "\n".join(every_text(view)))
        self.assertEqual(bf.read_discovered(self.folder, 1, extras=False), set(FISH_FOUND))
        # with it: the DS fin from the save's columns and the DS body (and its fin) from the file
        make_sidecar(self.folder, 1, DS_IN_SIDECAR)
        view = view_for("fish", self.folder, 1, spoilers=False)
        self.assertTrue(view.model.extras)
        self.assertEqual(names_in(view.part_sheet("fin")), FISH_FINS | {"Angel", "Tiger"})
        self.assertEqual(names_in(view.part_sheet("body")), FISH_BODIES | {"Arrowfish", "Bicolor"})
        self.assertEqual(view.part_count("fin"), (5, 28))
        self.assertEqual(view.part_count("body"), (6, 28))
        self.assertEqual(view.part_sheet("fin").header, "5 of 28 fins discovered (7 of them DS Exclusive Fish, 1 discovered).")
        self.assertEqual(view.part_sheet("body").header,
                         "6 of 28 bodies discovered (7 of them DS Exclusive Fish, 1 discovered).")
        patcher = {r[0] for r in view.part_sheet("body").rows if r[-1] == "DS Exclusive Fish"}
        self.assertEqual(patcher, {"Bicolor"})
        items = {i.name for g in bpx.part_items(view, "fin") for i in g.items}
        self.assertEqual(items, FISH_FINS | {"Angel", "Tiger"})

    def test_a_ds_sidecar_that_is_not_one_is_not_read(self) -> None:
        """As the DLL's on_load: an unreadable sidecar's DS bodies start undiscovered; the DS
        fins already set up in the save's own columns stay discovered."""
        make_save(self.folder, 1, {**FISH_FOUND, **DS_IN_SAVE}, ds_columns=True)
        path = make_sidecar(self.folder, 1, DS_IN_SIDECAR)
        path.write_bytes(b"FTDS" + bytes(20))
        self.assertEqual(bf.read_discovered(self.folder, 1, extras=True), set(FISH_FOUND) | set(DS_IN_SAVE))
        view = view_for("fish", self.folder, 1, spoilers=False)            # the file is there: on
        self.assertEqual(names_in(view.part_sheet("body")), FISH_BODIES | {"Arrowfish"})
        self.assertEqual(names_in(view.part_sheet("fin")), FISH_FINS | {"Angel"})

    def test_nothing_undiscovered_is_named(self) -> None:
        make_save(self.folder, 1, {**FISH_FOUND, **DS_IN_SAVE}, ds_columns=True)
        make_sidecar(self.folder, 1, DS_IN_SIDECAR)
        view = view_for("fish", self.folder, 1, spoilers=False)
        words = undiscovered_words(view)
        self.assertIn("Wasp", words)
        self.assertIn("Wasp Grouper", words)
        self.assertIn("Silky Fatfish", words)          # both parts seen, the species is not
        texts = every_text(view)
        assert_never_named(self, texts, words)
        # the Mutation fish by its title only
        self.assertIn("Max effects, with Magic Fish of Mutation", [label for _v, label in view.effects_choices()])
        self.assertIn("Magic Fish of Mutation", view.how("fin", 4))
        self.assertIn("Magic Fish of Mutation", view.effects_text("max_mutation"))

    def test_the_mutation_fish_is_named_once_discovered(self) -> None:
        make_save(self.folder, 1, {**FISH_FOUND, bf.MUTATION_FISH: 95})
        view = view_for("fish", self.folder, 1, spoilers=False)
        self.assertIn("Max effects, with Wasp Grouper", [label for _v, label in view.effects_choices()])
        self.assertIn("(Wasp Grouper)", view.effects_text("max_mutation"))
        self.assertIn("Wasp", names_in(view.part_sheet("fin")))

    def test_spoilers_on_shows_everything(self) -> None:
        make_save(self.folder, 1, {**FISH_FOUND, **DS_IN_SAVE}, ds_columns=True)
        make_sidecar(self.folder, 1, DS_IN_SIDECAR)
        view = view_for("fish", self.folder, 1, spoilers=True)
        for kind in ("body", "fin"):
            sheet = view.part_sheet(kind)
            self.assertEqual(names_in(sheet), {p.name for p in view.model.parts(kind)})
            self.assertEqual(len(sheet.rows), 28)
            self.assertEqual(len([i for g in bpx.part_items(view, kind) for i in g.items]), 28)
        self.assertEqual(view.part_sheet("fin").header,
                         "5 of 28 fins discovered (7 of them DS Exclusive Fish, 1 discovered); "
                         "Show Spoilers lists all 28.")
        self.assertIn("Max effects, with Wasp Grouper", [label for _v, label in view.effects_choices()])
        self.assertIn("Wasp", view.how("body", 13) + view.effects_text("max_mutation"))

    def test_exports_follow_the_rule(self) -> None:
        make_save(self.folder, 1, {**FISH_FOUND, **DS_IN_SAVE}, ds_columns=True)
        make_sidecar(self.folder, 1, DS_IN_SIDECAR)
        view = view_for("fish", self.folder, 1, spoilers=False)
        words = undiscovered_words(view)
        for kind in view.kinds:
            sheet = view.part_sheet(kind)
            csv_path, xlsx_path = self.folder / f"{kind}.csv", self.folder / f"{kind}.xlsx"
            bg.export_csv(csv_path, sheet)
            bg.export_xlsx(xlsx_path, sheet)
            with open(csv_path, newline="", encoding="utf-8-sig") as handle:
                from_csv = list(csv.reader(handle))
            from_xlsx = bg.read_xlsx(xlsx_path)
            self.assertEqual(len(from_csv) - 1, len(sheet.rows))
            self.assertEqual({r[0] for r in from_xlsx[1:]}, names_in(sheet))
            assert_never_named(self, [c for r in from_csv + from_xlsx for c in r], words)


class PlantPartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        make_plant_save(self.folder, 2, PLANT_FOUND)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_stock_save_shows_exactly_its_parts(self) -> None:
        view = view_for("plant", self.folder, 2, spoilers=False)
        self.assertFalse(view.model.extras)
        self.assertEqual(names_in(view.part_sheet("foliage")), PLANT_FOLIAGES)
        self.assertEqual(names_in(view.part_sheet("flower")), PLANT_FLOWERS)
        self.assertEqual(view.part_sheet("foliage").header, "3 of 23 foliage discovered.")
        self.assertEqual(view.part_sheet("flower").header, "3 of 23 flowers discovered.")
        for kind, expected in (("foliage", PLANT_FOLIAGES), ("flower", PLANT_FLOWERS)):
            self.assertEqual({i.name for g in bpx.part_items(view, kind) for i in g.items}, expected)
        seeds = {i.name for g in bpx.seed_items(view) for i in g.items}
        self.assertEqual(seeds, {f"{n} seed" for n in PLANT_FOLIAGES})

    def test_new_flowers_only_with_the_new_flowers_data_file(self) -> None:
        view = view_for("plant", self.folder, 2, spoilers=False)
        self.assertEqual(view.part_count("flower"), (3, 23))
        make_new_flowers(self.folder, 2, NEW_FOUND)
        view = view_for("plant", self.folder, 2, spoilers=False)
        self.assertTrue(view.model.extras)
        self.assertEqual(names_in(view.part_sheet("flower")), PLANT_FLOWERS | {"Silvermist"})
        self.assertEqual(names_in(view.part_sheet("foliage")), PLANT_FOLIAGES)      # Astera already seen
        self.assertEqual(view.part_count("flower"), (4, 37))
        self.assertEqual(view.part_sheet("flower").header,
                         "4 of 37 flowers discovered (14 of them Unused Flowers, 1 discovered).")
        self.assertEqual({i.name for g in bpx.part_items(view, "flower") for i in g.items},
                         PLANT_FLOWERS | {"Silvermist"})
        legendary = [g for g in bpx.seed_items(view) if g.tier == "Legendary"][0]
        self.assertEqual({i.name for i in legendary.items}, {f"{n} seed" for n in PLANT_FOLIAGES})
        # a data file of another slot does not count
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        make_plant_save(other, 3, PLANT_FOUND)
        make_new_flowers(other, 4, NEW_FOUND)
        self.assertEqual(view_for("plant", other, 3, spoilers=False).part_count("flower"), (3, 23))

    def test_nothing_undiscovered_is_named(self) -> None:
        make_new_flowers(self.folder, 2, NEW_FOUND)
        view = view_for("plant", self.folder, 2, spoilers=False)
        words = undiscovered_words(view)
        for word in ("Aureus Scandens", "Nox Orchid", "Arthurium", "Tilia", "Nox", "Prunus", "Spotted Astera"):
            self.assertIn(word, words)
        assert_never_named(self, every_text(view), words)
        self.assertIn("Golden Berries of Wealth (a magic plant)", view.effects_text("max"))

    def test_spoilers_on_shows_everything(self) -> None:
        make_new_flowers(self.folder, 2, NEW_FOUND)
        view = view_for("plant", self.folder, 2, spoilers=True)
        self.assertEqual(len(view.part_sheet("flower").rows), 37)
        self.assertEqual(len(view.part_sheet("foliage").rows), 23)
        self.assertEqual(len([i for g in bpx.part_items(view, "flower") for i in g.items]), 37)
        self.assertIn("Aureus Scandens", view.effects_text("max"))

    def test_exports_follow_the_rule(self) -> None:
        make_new_flowers(self.folder, 2, NEW_FOUND)
        view = view_for("plant", self.folder, 2, spoilers=False)
        words = undiscovered_words(view)
        for kind in view.kinds:
            sheet = view.part_sheet(kind)
            out = self.folder / f"{kind}.xlsx"
            bg.export_xlsx(out, sheet)
            rows = bg.read_xlsx(out)
            self.assertEqual({r[0] for r in rows[1:]}, names_in(sheet))
            assert_never_named(self, [c for r in rows for c in r], words)


class WindowTests(unittest.TestCase):
    """The window on a synthetic Fish Tycoon save (tests/test_breeding_guide.py's: Pink Fatfish,
    Silky Shark ..., a DS fin in the save's columns and Moorish Idle in "DS Fish 1.dat")."""

    def setUp(self) -> None:
        from test_breeding_guide import make_documents, tk_root
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display for Tk")
        self.tmp = tempfile.TemporaryDirectory()
        documents = make_documents(Path(self.tmp.name))
        bg._open_window = None
        self.guide = bg.open_window(self.root, "fish", settings={"show_spoilers": False}, documents=documents)
        self.root.update()

    def tearDown(self) -> None:
        self.guide.close()
        self.root.destroy()
        self.tmp.cleanup()

    def shown(self, sheet_id: str) -> set[str]:
        tree = self.guide.trees[sheet_id]
        return {tree.item(i, "values")[0] for i in tree.get_children()}

    def test_part_tabs_count_list_and_export_only_discovered_parts(self) -> None:
        view = self.guide.view
        self.assertTrue(view.model.extras)
        # DISCOVERED + (19, 23) in the save + (29, 29) in the sidecar: fins 16, 0, 4, 10, 20, 23, 29
        fins = {"Greenfin", "Silky", "Pink", "Golden", "Small-Fin", "Twin-Fin", "Moorish"}
        self.assertEqual({p.name for p in view.model.parts("fin") if ("fin", p.index) in view.found_parts}, fins)
        self.assertEqual(self.shown("part:fin"), fins)
        self.assertEqual(self.guide.trees["part:fin"].header_label.cget("text"), view.part_count_text("fin"))
        self.assertEqual(view.part_count_text("fin"), "7 of 28 fins discovered (7 of them DS Exclusive Fish, 2 discovered).")
        words = undiscovered_words(view)
        nb = self.guide.notebook
        for sheet_id in ("part:fin", "part:body"):
            nb.select(nb.tabs()[self.guide.tab_ids.index(sheet_id)])
            self.root.update()
            for fmt in ("csv", "xlsx"):
                out = Path(self.tmp.name) / f"{sheet_id[5:]}.{fmt}"
                self.assertEqual(self.guide.export(fmt, str(out)), str(out))
                if fmt == "csv":
                    with open(out, newline="", encoding="utf-8-sig") as handle:
                        rows = list(csv.reader(handle))
                else:
                    rows = bg.read_xlsx(out)
                self.assertEqual({r[0] for r in rows[1:]}, self.shown(sheet_id))
                assert_never_named(self, [c for r in rows for c in r], words)
        labels = [b.cget("text") for b in self.guide.calc_effect_buttons]
        self.assertEqual(labels[2], "Max effects, with Magic Fish of Mutation")
        pictures = self.guide.pictures["pictures:fin"]
        self.assertEqual({c[0].name for c in pictures["cells"]}, fins)
        self.assertEqual(pictures["header"].cget("text"), view.part_count_text("fin"))
        # spoilers on: everything
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.assertEqual(len(self.shown("part:fin")), 28)
        self.assertEqual(len(self.guide.pictures["pictures:fin"]["cells"]), 28)
        self.assertEqual(self.guide.calc_effect_buttons[2].cget("text"), "Max effects, with Wasp Grouper")

    def test_the_files_are_read_again_when_the_save_is_picked_again(self) -> None:
        """No cached discovery: picking the player again reads the save and the data file fresh."""
        from test_breeding_guide import DISCOVERED
        folder = self.guide.current_folder()
        self.assertNotIn("Wasp", self.shown("part:fin"))
        make_save(folder, 1, {**DISCOVERED, (19, 23): 38, bf.MUTATION_FISH: 95}, ds_columns=True)
        make_sidecar(folder, 1, {(29, 29): 40, (24, 6): 9})                 # Discus body, Wasp fin
        self.guide._reload()
        self.root.update()
        self.assertIn("Wasp", self.shown("part:fin"))
        self.assertIn("Grouper", self.shown("part:body"))
        self.assertIn("Discus", self.shown("part:body"))

    def test_the_help_explains_the_rule_and_fits_the_screen(self) -> None:
        window = bg.show_help(self.guide.window)
        self.root.update()
        try:
            text = window.help_text.get("1.0", "end")
            self.assertIn("a part is discovered when a species you have discovered has it", text)
            self.assertIn("n of N discovered", text)
            self.assertNotIn("Wasp Grouper", text)
            self.assertLessEqual(window.winfo_reqheight(), window.winfo_screenheight())
        finally:
            window.destroy()


def _text_section(path: Path) -> tuple[int, bytes]:
    """(virtual address, bytes) of an executable's .text section."""
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    for i in range(count):
        at = pe + 24 + optional + 40 * i
        if data[at:at + 8].rstrip(b"\0") == b".text":
            _vsize, va, size, raw = struct.unpack_from("<IIII", data, at + 8)
            return base + va, data[raw:raw + size]
    raise AssertionError("no .text")


class GameRuleTests(unittest.TestCase):
    """The game code the part rule rests on: one discovery record per species, none per part."""

    @unittest.skipUnless(FISH_EXE.is_file(), "needs the vanilla Fish Tycoon.exe")
    def test_fish_tycoon_records_discovery_only_per_species(self) -> None:
        va, text = _text_section(FISH_EXE)
        # every write to a species entry's asking price (state + 0x14B60 + (body x 31 + fin) x 40):
        # the new game's -1 (0x418D4E), the discovery (0x41E38D) and the Species screen's keypad
        # (the isolation tank fish's price)
        writes = [va + m.start() for m in re.finditer(
            rb"(?:\x89|\xC7)[\x80-\xBF][\x00-\xFF]?\x60\x4B\x01\x00", text, re.S)]
        self.assertEqual(writes, [0x418D4E, 0x41E38D, 0x425C23, 0x425C7C, 0x425DEF])
        # 0x41E2D0 sets the price only of a species still at -1, and its one caller is the fish
        # update for an adult (0x420748)
        self.assertEqual(text[0x41E2EF - va:0x41E2EF - va + 8], bytes.fromhex("83bc30604b0100ff"))
        callers = [va + i for i in range(len(text) - 5) if text[i] == 0xE8
                   and (va + i + 5 + struct.unpack_from("<i", text, i + 1)[0]) & 0xFFFFFFFF == 0x41E2D0]
        self.assertEqual(callers, [0x420748])

    @unittest.skipUnless(PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon.exe")
    def test_plant_tycoon_records_discovery_only_per_species(self) -> None:
        va, text = _text_section(PLANT_EXE)
        # mov byte [state + foliage x 24 + flower + 0x64], 1: maturity and Mutation Liquid only
        writes = [va + m.start() for m in re.finditer(rb"\xC6\x44[\x00-\xFF]\x64\x01", text, re.S)]
        self.assertEqual(writes, [0x426F11, 0x42E2C4])
        self.assertEqual(bp.DISCOVERED_STATE, 0x64)


if __name__ == "__main__":
    unittest.main()
