"""The Breeding Guide window and its sheets (src/breeding_guide.py), headless.

The sheets are checked as data (spoilers off shows only the discovered species
and what they reveal; spoilers on shows everything), then the window is built
on small synthetic saves (no owner data): its tabs, the spoiler switch and
its memory, sorting, the search filter, export to .csv and .xlsx and back,
the breeding calculator, the planner, the Plant model, the "coming in this
update" view, and that the window fits the screen.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_fish as bf  # noqa: E402
import breeding_guide as bg  # noqa: E402
from test_breeding_fish import make_save, make_settings, make_sidecar  # noqa: E402

DISCOVERED = {(20, 16): 48, (0, 0): 4, (4, 4): 5, (10, 10): 17, (20, 20): 4}


def make_documents(root: Path) -> Path:
    folder = root / "LDW" / "Fish Tycoon - Modded Upgrades"
    folder.mkdir(parents=True)
    make_settings(folder, ["Tester", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER"])
    make_save(folder, 1, {**DISCOVERED, (19, 23): 38}, ds_columns=True)
    make_sidecar(folder, 1, {(29, 29): 40})
    return root


class SheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = bf.load(None, False)

    def test_spoilers_off_shows_only_what_the_save_reveals(self) -> None:
        view = bg.View(self.model, set(DISCOVERED), spoilers=False)
        species = view.species_sheet()
        self.assertEqual(species.title, "Discovered Species")
        self.assertEqual({tuple(k) for k in species.keys}, set(DISCOVERED))
        fins = view.part_sheet("fin")
        self.assertEqual({k[1] for k in fins.keys}, {16, 0, 4, 10, 20})
        self.assertEqual(view.name((7, 7)), bg.UNDISCOVERED)          # Canary: never seen
        self.assertEqual(view.name((4, 0)), "Silky Fatfish")          # made of parts already seen
        for row in species.rows:                                      # no unseen part in the combos
            for cell in (row[5], row[6]):
                for name in ("Canary", "Fire-Arrow", "Catfish", "Tiger"):
                    self.assertNotIn(name, cell)
        calc = view.calculator_sheet((0, 0), (4, 4), "none")
        self.assertEqual(calc.rows[0][0], "Hornet Arrowfish" if view.revealed((2, 2)) else bg.UNDISCOVERED)
        self.assertEqual(calc.rows[0][3], 100.0)

    def test_spoilers_on_shows_everything(self) -> None:
        view = bg.View(self.model, set(DISCOVERED), spoilers=True)
        species = view.species_sheet()
        self.assertEqual(species.title, "All Species")
        self.assertEqual(len(species.rows), 441)
        self.assertEqual(species.columns[-1], "Discovered")
        self.assertEqual(sum(r[-1] == "Yes" for r in species.rows), len(DISCOVERED))
        self.assertEqual(len(view.part_sheet("body").rows), 21)
        self.assertEqual(view.name((7, 7)), "Canary Fire-Arrow")

    def test_patcher_species_are_marked(self) -> None:
        view = bg.View(bf.load(None, True), set(), spoilers=True)
        species = view.species_sheet()
        patcher = [r for r, t in zip(species.rows, species.tags) if "patcher" in t]
        self.assertEqual(len(patcher), 784 - 441)
        self.assertTrue(all(r[14] == "DS Exclusive Fish" for r in patcher))

    def test_planner_sheet(self) -> None:
        view = bg.View(self.model, set(DISCOVERED), spoilers=True)
        sheet = view.planner_sheet([(4, 4), (10, 10)], (7, 7), "none")
        self.assertEqual(sheet.rows, [[1, "Breeding", "Pink Fatfish", "Golden Goldbulb", "Canary Fire-Arrow", 100.0]])
        self.assertIn("You already have it", view.planner_sheet([(7, 7)], (7, 7), "none").message)
        self.assertIn("No breeding chain", view.planner_sheet([(0, 0)], (7, 7), "none").message)

    def test_filter_and_sort_keys(self) -> None:
        view = bg.View(self.model, set(DISCOVERED), spoilers=True)
        sheet = view.species_sheet()
        rows = bg.filter_rows(sheet, "spotanus")
        self.assertEqual(sum("Spotanus" in sheet.rows[i][0] for i in rows), 21)
        self.assertTrue(all(any("spotanus" in str(c).casefold() for c in sheet.rows[i]) for i in rows))
        self.assertLess(len(rows), len(sheet.rows))
        self.assertEqual(len(bg.filter_rows(sheet, "Canary Fire-Arrow")), 1)
        self.assertLess(bg.sort_key(9), bg.sort_key(10))
        self.assertLess(bg.sort_key("1,234"), bg.sort_key("12,345"))
        self.assertLess(bg.sort_key("apple"), bg.sort_key("Banana"))

    def test_export_round_trip(self) -> None:
        view = bg.View(self.model, set(DISCOVERED), spoilers=False)
        sheet = view.species_sheet()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            bg.export_csv(path, sheet)
            with open(path, newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], sheet.columns)
            self.assertEqual([r[0] for r in rows[1:]], [r[0] for r in sheet.rows])
            path = Path(tmp) / "out.xlsx"
            bg.export_xlsx(path, sheet, [1, 0])
            cells = bg.read_xlsx(path)
            self.assertEqual(cells[0], sheet.columns)
            self.assertEqual(cells[1][0], sheet.rows[1][0])
            self.assertEqual(float(cells[1][4]), sheet.rows[1][4])
            self.assertEqual(len(cells), 3)

    def test_detect_extras(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saves = root / "LDW" / "Fish Tycoon - Modded Upgrades"
            saves.mkdir(parents=True)
            self.assertFalse(bg.detect_extras("fish", saves, 1, [])[0])
            make_sidecar(saves, 1, {})
            on, why = bg.detect_extras("fish", saves, 1, [])
            self.assertTrue(on)
            self.assertIn("DS Fish 1.dat", why)
            copy = root / "Games" / "Fish Tycoon - Modded Upgrades"
            copy.mkdir(parents=True)
            (copy / "Fish Tycoon - Modded Upgrades.exe").write_bytes(b"MZ")
            (copy / "FishTycoonBugFixPatchLog.json").write_text(json.dumps({"enabled_settings": ["fix_vanilla_bugs"]}))
            self.assertFalse(bg.detect_extras("fish", saves, 1, [root / "Games"])[0])
            (copy / "FishTycoonBugFixPatchLog.json").write_text(json.dumps({"enabled_settings": ["ds_fish"]}))
            self.assertTrue(bg.detect_extras("fish", saves, 2, [root / "Games"])[0])


def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        return None
    root.withdraw()
    return root


class WindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display for Tk")
        self.tmp = tempfile.TemporaryDirectory()
        self.documents = make_documents(Path(self.tmp.name))
        self.settings = {"show_spoilers": False}
        self.saved = 0

        def save() -> str:
            self.saved += 1
            return ""

        bg._open_window = None
        self.guide = bg.open_window(self.root, "fish", settings=self.settings, save_settings=save,
                                    documents=self.documents)
        self.root.update()

    def tearDown(self) -> None:
        if getattr(self, "guide", None) is not None:
            self.guide.close()
        if self.root is not None:
            self.root.destroy()
            self.tmp.cleanup()

    def tabs(self) -> list[str]:
        nb = self.guide.notebook
        return [nb.tab(t, "text") for t in nb.tabs()]

    def select(self, title: str) -> None:
        nb = self.guide.notebook
        nb.select(nb.tabs()[self.tabs().index(title)])
        self.root.update()

    def test_tabs_and_the_save(self) -> None:
        self.assertEqual(self.tabs(), ["Fins", "Bodies", "Discovered Species", "Breeding Calculator", "Have to Want"])
        self.assertEqual(self.guide.folder_var.get(), "Fish Tycoon - Modded Upgrades")
        self.assertEqual(self.guide.slot_var.get(), "Player 1: Tester")
        # the save's DS data turns the patcher species on, and its DS species are read
        expected = set(DISCOVERED) | {(19, 23), (29, 29)}
        self.assertEqual(set(self.guide.sheets["species"].keys), expected)
        self.assertIn("DS Exclusive Fish", self.guide.status_var.get())

    def test_spoilers_switch_is_remembered(self) -> None:
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.assertTrue(self.settings["show_spoilers"])
        self.assertEqual(self.saved, 1)
        self.assertEqual(len(self.guide.trees["species"].get_children()), 784)
        self.assertIn("All Species", self.tabs())
        self.guide.spoilers_var.set(False)
        self.root.update()
        self.assertEqual(len(self.guide.trees["species"].get_children()), len(DISCOVERED) + 2)

    def test_sort_and_filter(self) -> None:
        self.select("Discovered Species")
        tree = self.guide.trees["species"]
        self.guide.sort("species", 4)                                   # base value, ascending
        values = [int(tree.set(i, "c4")) for i in tree.get_children()]
        self.assertEqual(values, sorted(values))
        self.guide.sort("species", 4)                                   # and descending
        values = [int(tree.set(i, "c4")) for i in tree.get_children()]
        self.assertEqual(values, sorted(values, reverse=True))
        self.guide.search_var.set("greenfin spot")
        self.root.update()
        names = [tree.set(i, "c0") for i in tree.get_children()]
        self.assertEqual(names, ["Greenfin Spotanus"])
        self.assertIn("Magic Fish of Fertility", tree.item(tree.get_children()[0], "values"))
        self.guide.search_var.set("")
        self.root.update()
        self.assertEqual(len(tree.get_children()), len(DISCOVERED) + 2)

    def test_export(self) -> None:
        self.select("Fins")
        out = Path(self.tmp.name) / "fins.xlsx"
        self.guide.export("xlsx", str(out))
        cells = bg.read_xlsx(out)
        self.assertEqual(cells[0][0], "Fin")
        self.assertEqual(len(cells) - 1, len(self.guide.trees["part:fin"].get_children()))
        out = Path(self.tmp.name) / "fins.csv"
        self.guide.export("csv", str(out))
        self.assertTrue(out.read_text(encoding="utf-8-sig").startswith("Fin,Index"))

    def test_calculator(self) -> None:
        self.select("Breeding Calculator")
        names = [s.name for s in self.guide.calc_choices]
        self.guide.calc_boxes[0].current(names.index("Greenfin Spotanus"))
        self.guide.calc_boxes[1].current(names.index("Twin-Fin Spotanus"))
        self.guide.effects_var.set("none")
        self.guide.calculate()
        tree = self.guide.trees["calculator"]
        rows = [tree.item(i, "values") for i in tree.get_children()]
        # Flagged (fin 18) is in no discovered species, so the child is not named
        self.assertEqual(rows, [(bg.UNDISCOVERED, "?", "?", "100.00", "No")])
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.select("Breeding Calculator")
        names = [s.name for s in self.guide.calc_choices]
        self.guide.calc_boxes[0].current(names.index("Greenfin Spotanus"))
        self.guide.calc_boxes[1].current(names.index("Twin-Fin Spotanus"))
        self.guide.calculate()
        tree = self.guide.trees["calculator"]
        rows = [tree.item(i, "values") for i in tree.get_children()]
        self.assertEqual(rows, [("Flagged Spotanus", "Spotanus", "Flagged", "100.00", "No")])
        self.guide.effects_var.set("max")
        self.guide.calculate()
        odds = [float(tree.set(i, "c3")) for i in tree.get_children()]
        self.assertAlmostEqual(sum(odds), 100.0, places=6)

    def test_planner(self) -> None:
        self.select("Have to Want")
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.select("Have to Want")
        names = [s.name for s in self.guide.have_choices]
        self.guide.have_list.selection_clear(0, "end")
        for name in ("Pink Fatfish", "Golden Goldbulb"):
            self.guide.have_list.selection_set(names.index(name))
        wants = [s.name for s in self.guide.want_choices]
        self.guide.want_box.current(wants.index("Canary Fire-Arrow"))
        self.guide.effects_var.set("none")
        self.guide.plan()
        tree = self.guide.trees["planner"]
        rows = [tree.item(i, "values") for i in tree.get_children()]
        self.assertEqual(rows, [("1", "Breeding", "Pink Fatfish", "Golden Goldbulb", "Canary Fire-Arrow", "100.00")])

    def test_plant_model_loads(self) -> None:
        self.guide.game_var.set("Plant Tycoon")
        self.root.update()
        self.assertEqual(self.tabs(), ["Flowers", "Foliage", "Discovered Species", "Breeding Calculator", "Have to Want"])
        self.assertIsNotNone(self.guide.model)
        self.assertEqual(self.guide.model.game, "plant")

    def test_coming_in_this_update(self) -> None:
        saved = dict(bg.MODEL_MODULES)
        bg.MODEL_MODULES["plant"] = "breeding_plant_not_in_this_build"
        try:
            bg._MODELS.clear()
            self.guide.game_var.set("Plant Tycoon")
            self.root.update()
            self.assertIsNone(self.guide.model)
            self.assertEqual(self.guide.status_var.get(), bg.COMING)
            self.assertIn("disabled", self.guide.export_xlsx_button.state())
        finally:
            bg.MODEL_MODULES.clear()
            bg.MODEL_MODULES.update(saved)
            bg._MODELS.clear()

    def test_fits_the_screen(self) -> None:
        window = self.guide.window
        window.update_idletasks()
        screen_w, screen_h = window.winfo_screenwidth(), window.winfo_screenheight()
        geometry = window.geometry().split("+")[0]
        width, height = (int(v) for v in geometry.split("x"))
        self.assertLessEqual(width, screen_w)
        self.assertLessEqual(height, screen_h - 60)
        self.assertLessEqual(window.winfo_reqheight(), screen_h)
        # no widget in the window is anywhere near Windows' 32,767-pixel drawing limit
        stack = [window]
        while stack:
            widget = stack.pop()
            self.assertLess(widget.winfo_reqheight(), 32767)
            stack.extend(widget.winfo_children())


class WiringTests(unittest.TestCase):
    def test_tools_tab_and_release(self) -> None:
        tools = (ROOT / "src" / "tools_tab.py").read_text(encoding="utf-8")
        self.assertIn('"breeding_guide": breeding_guide.HELP', tools)
        self.assertIn("breeding_guide.open_window(", tools)
        self.assertEqual(tools.count('"breeding_guide"'), 4)
        release = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        for name in ("breeding_guide", "breeding_fish", "breeding_plant"):
            self.assertIn(f'"src/{name}.py"', release)

    def test_spoilers_are_remembered_in_the_settings_file(self) -> None:
        root = tk_root()
        if root is None:
            self.skipTest("no display for Tk")
        root.destroy()
        import tycoon_fix_patcher_gui as gui
        with tempfile.TemporaryDirectory() as tmp:
            saved = gui.SETTINGS_PATH
            gui.SETTINGS_PATH = Path(tmp) / "settings.json"
            try:
                gui.SETTINGS_PATH.write_text(json.dumps({"breeding_guide": {"show_spoilers": True}}))
                app = gui.App()
                app.withdraw()
                self.assertTrue(app.breeding_settings["show_spoilers"])
                app.breeding_settings["show_spoilers"] = False
                self.assertEqual(app._save_settings(), "")
                app.destroy()
                data = json.loads(gui.SETTINGS_PATH.read_text(encoding="utf-8"))
                self.assertEqual(data["breeding_guide"], {"show_spoilers": False})
            finally:
                gui.SETTINGS_PATH = saved


if __name__ == "__main__":
    unittest.main()
