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
        self.assertEqual(view.name((4, 0)), bg.UNDISCOVERED)          # made of seen parts, not discovered
        for row in species.rows:                                      # no unseen part in the combos
            for cell in (row[5], row[6]):
                for name in ("Canary", "Fire-Arrow", "Catfish", "Tiger"):
                    self.assertNotIn(name, cell)
        calc = view.calculator_sheet((0, 0), (4, 4), "none")
        self.assertEqual(calc.rows[0][0], bg.UNDISCOVERED)              # Hornet Arrowfish: not discovered
        self.assertEqual(calc.rows[0][3], 100.0)

    def test_spoilers_off_lists_exactly_the_discovered_species(self) -> None:
        """Only species whose own discovered flag is set: Pink Fatfish (4, 4) and Silky Shark
        (0, 0) are discovered, so their parts are seen, but the combinations Silky Fatfish
        (4, 0) and Pink Shark (0, 4) are not and must not be listed, suggested or planned
        through. The same in Plant Tycoon."""
        import breeding_plant
        cases = ((self.model, {(0, 0), (4, 4), (2, 2)}, [(4, 0), (0, 4)], "fin", {0, 4, 2}),
                 (breeding_plant.load(None, extras=False), {(1, 1), (5, 5), (3, 3)}, [(1, 5), (5, 1)],
                  "flower", {1, 5, 3}))
        for model, found, seen_parts_only, kind, parts in cases:
            view = bg.View(model, set(found), spoilers=False)
            species = view.species_sheet()
            self.assertEqual(set(species.keys), found)
            self.assertEqual({tuple(s.key) for s in view.species_choices()}, found)
            self.assertEqual({tuple(s.key) for s in view.want_choices()}, found)
            self.assertEqual({k[1] for k in view.part_sheet(kind).keys}, parts)
            names = [r[0] for r in species.rows]
            for key in seen_parts_only:
                self.assertEqual(view.name(key), bg.UNDISCOVERED)
                self.assertNotIn(next(s.name for s in model.species() if tuple(s.key) == key), names)
            for target in found:
                for m, f, _p in view.best_parents(target, "none", limit=1000):
                    self.assertIn(m, found)
                    self.assertIn(f, found)
            want = sorted(found)[1]
            plan = view.planner_sheet(sorted(found - {want}), want, "none")
            self.assertTrue(plan.rows, plan.message)
            self.assertTrue(all(r[4] != bg.UNDISCOVERED for r in plan.rows))
            # with spoilers the same species is named
            self.assertNotEqual(bg.View(model, set(found), spoilers=True).name(seen_parts_only[0]), bg.UNDISCOVERED)

    def test_the_planner_uses_only_discovered_species(self) -> None:
        """Spoilers off: a chain may not breed through an undiscovered species even when that
        is the only way (the model's `allowed`)."""
        found = {(0, 0), (8, 8), (20, 20), (2, 2)}
        # (0,0) x (8,8) -> (4,4), then (0,0) x (4,4) -> (2,2): (4,4) is undiscovered
        sheet = bg.View(self.model, found, spoilers=False).planner_sheet([(0, 0), (8, 8)], (2, 2), "none")
        self.assertEqual(sheet.rows, [])
        self.assertIn("through the species you have discovered", sheet.message)
        spoiled = bg.View(self.model, found, spoilers=True)
        self.assertEqual(len(spoiled.planner_sheet([(0, 0), (8, 8)], (2, 2), "none").rows), 2)

    def test_three_effects_choices(self) -> None:
        """Both games: 0 effects and Max without the mutation give the same odds (none from a
        mutation); Max with it changes them, in the calculator and in the planner."""
        import breeding_plant
        cases = ((self.model, (20, 16), (20, 20), "Wasp Grouper", [(20, 20)], (19, 20)),
                 (breeding_plant.load(None, extras=False), (5, 5), (7, 7), "Mutation Liquid", [(10, 10)], (11, 10)))
        for model, a, b, mutation, have, want in cases:
            labels = [label for _v, label in bg.effects_choices(model)]
            self.assertEqual(labels, ["0 effects", "Max effects, without", f"Max effects, with {mutation}"])
            view = bg.View(model, set(), spoilers=True)
            none, without, with_ = (view.calculator_sheet(a, b, e) for e in ("none", "max", "max_mutation"))
            self.assertEqual(none.rows, without.rows)
            self.assertEqual(len(without.rows), 1)
            self.assertEqual(without.rows[0][3], 100.0)
            self.assertGreater(len(with_.rows), 1)
            self.assertAlmostEqual(sum(r[3] for r in with_.rows), 100.0)
            self.assertIn("no mutation chance", without.intro)
            self.assertIn(mutation, with_.intro)
            self.assertEqual(view.planner_sheet(have, want, "max").rows, [])
            self.assertTrue(view.planner_sheet(have, want, "max_mutation").rows)

    def test_rarity_words(self) -> None:
        """Fish: Common / Uncommon / Rare (never "Half-rare"); Plant: Tier 1 to Tier 5 (the soil tiers)."""
        import breeding_plant
        sheet = bg.View(bf.load(None, True), set(), spoilers=True).species_sheet()
        self.assertEqual({r[sheet.columns.index("Rarity")] for r in sheet.rows}, {"Common", "Uncommon", "Rare"})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "all.csv"
            bg.export_csv(out, sheet)
            text = out.read_text(encoding="utf-8-sig")
            self.assertIn("Uncommon", text)
            self.assertNotIn("Half", text)
        sheet = bg.View(breeding_plant.load(None, extras=True), set(), spoilers=True).species_sheet()
        self.assertEqual({r[sheet.columns.index("Rarity")] for r in sheet.rows},
                         {"Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5"})
        self.assertNotIn("Half", " ".join(bg.HELP[1]))

    def test_how_names_the_exact_parent_pairs(self) -> None:
        """A body, a fin, a flower and a foliage: the parent pairs are named, one line per first
        parent, exactly the pairs the game's rule gives."""
        import breeding_plant
        plant = breeding_plant.load(None, extras=False)
        cases = (
            (self.model, "body", 7, ["  Shark with Leaffish, Carp", "  Fire-Arrow with Fire-Arrow, Fruitfish"]),
            (self.model, "fin", 7, ["  Silky with Speckled, Razorback", "  Canary with Canary, Orange"]),
            (plant, "flower", 3, ["  Spotted with Nox, Bluestar", "  Painted with Daisy, Nox", "  Daisy with Daisy"]),
            (plant, "foliage", 3, ["  Reptans with Orchid, Astera", "  Scandens with Grass, Orchid", "  Grass with Grass"]),
        )
        for model, kind, index, lines in cases:
            how = bg.View(model, set(), spoilers=True).how(kind, index).splitlines()
            for line in lines:
                self.assertIn(line, how, (kind, index))
            pair_lines = [x for x in how if x.startswith("  ")]
            self.assertEqual(sum(len(x.split(" with ")[1].split(", ")) for x in pair_lines),
                             len(model.part_combos(kind, index)))

    def test_spoilers_off_names_only_discovered_parts_in_how(self) -> None:
        import breeding_plant
        view = bg.View(self.model, {(0, 0), (4, 4), (2, 2)}, spoilers=False)
        how = view.how("fin", 2)                                     # Hornet
        self.assertIn("  Silky with Pink", how)
        self.assertIn("  Hornet with Hornet", how)
        for hidden in ("Tiger", "Fanned", "Snubbed"):                # fins of no discovered species
            self.assertNotIn(hidden, how)
        self.assertIn("pairs with undiscovered fins", how)
        self.assertIn("2 undiscovered fins", how)                    # the Unknown Chemical's sources
        cell = view.part_sheet("fin").rows[[k[1] for k in view.part_sheet("fin").keys].index(2)][1]
        self.assertNotIn("Tiger", cell)
        plant = bg.View(breeding_plant.load(None, extras=False), {(1, 1), (5, 5)}, spoilers=False)
        how = plant.how("flower", 3)
        self.assertIn("  Spotted with Bluestar", how)
        self.assertNotIn("Nox", how)
        self.assertNotIn("Painted", how)
        self.assertIn("undiscovered flowers", how)

    def test_no_gene_numbers_in_any_text(self) -> None:
        """Every text the guide shows, in both games, with and without the patcher species:
        no sums, step wording, gene numbers, number ranges or numbers next to a part word."""
        import re
        import breeding_plant
        bad = re.compile(r"add up to|\bsteps\b|\bone step\b|\bgenes?\b|\bindex\b|\b\d+\s*-\s*\d+\b"
                         r"|\b(?:body|bodies|fins?|flowers?|foliages?)\s+\d|\d+\s+(?:body|bodies|fins?|flowers?|foliages?)\b",
                         re.I)
        texts = list(bg.HELP[1])
        for model in (bf.load(None, False), bf.load(None, True), breeding_plant.load(None, False),
                      breeding_plant.load(None, True)):
            for effects in ("none", "max", "max_mutation"):
                texts += model.effects_text(effects)
            keys = [s.key for s in model.species()]
            for spoilers, found in ((True, set(keys[::40])), (False, set(keys[::40]))):
                view = bg.View(model, found, spoilers)
                for kind in view.kinds:
                    sheet = view.part_sheet(kind)
                    texts += [str(c) for r in sheet.rows for c in r] + sheet.columns + list(sheet.details)
                species = view.species_sheet()
                texts += [str(c) for r in species.rows for c, k in zip(r, species.kinds) if k == "text"]
                texts += species.columns + [d() for d in species.details[::25]]
                pick = sorted(found)
                for effects in ("none", "max", "max_mutation"):
                    calc = view.calculator_sheet(pick[0], pick[1], effects)
                    texts += [str(c) for r in calc.rows for c in r] + [calc.intro]
                    texts += [d() if callable(d) else d for d in calc.details]
                    plan = view.planner_sheet(pick[:2], pick[2], effects)
                    texts += [str(c) for r in plan.rows for c in r] + [plan.message] + list(plan.details)
        for text in texts:
            match = bad.search(str(text))
            self.assertIsNone(match, f"{match and match.group(0)!r} in: {str(text)[:300]}")

    def test_revealed_parents_are_filtered_before_the_top_20(self) -> None:
        """Codex's repro: with Pink Fatfish (4,4), Golden Goldbulb (10,10) and Canary Fire-Arrow
        (7,7) discovered, the Canary's suggestions include Pink Fatfish x Golden Goldbulb (100%),
        though it is not among the top 20 of every pair."""
        unfiltered = self.model.ways_to_breed((7, 7), "none")
        self.assertNotIn(frozenset({(4, 4), (10, 10)}), [frozenset({m, f}) for m, f, _p in unfiltered])
        view = bg.View(self.model, {(4, 4), (10, 10), (7, 7)}, spoilers=False)
        best = view.best_parents((7, 7))
        self.assertIn(frozenset({(4, 4), (10, 10)}), [frozenset({m, f}) for m, f, _p in best])
        self.assertTrue(all(view.revealed(m) and view.revealed(f) for m, f, _p in best))
        self.assertEqual(dict(((frozenset({m, f}), p) for m, f, p in best))[frozenset({(4, 4), (10, 10)})], 1.0)
        detail = view.species_sheet().details[view.species_sheet().keys.index((7, 7))]()
        self.assertTrue("Pink Fatfish x Golden Goldbulb" in detail or "Golden Goldbulb x Pink Fatfish" in detail)

    def test_revealed_parents_are_filtered_before_the_top_20_plant(self) -> None:
        import breeding_plant
        model = breeding_plant.load(None, extras=False)
        for target in model.species():
            every = model.ways_to_breed(target.key, "none", limit=10_000)
            if len(every) > 20:
                break
        a, b, odds = every[-1]                                   # far below the top 20
        self.assertNotIn((a, b, odds), model.ways_to_breed(target.key, "none"))
        view = bg.View(model, {a, b, target.key}, spoilers=False)
        best = view.best_parents(target.key)
        self.assertIn((a, b), [(m, f) for m, f, _p in best])
        self.assertTrue(all(view.revealed(m) and view.revealed(f) for m, f, _p in best))

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


def bg_root() -> Path:
    return ROOT


def tk_root():
    """A hidden Tk root, or None with no display. Tk's start-up now and then fails once on
    Windows right after another root was destroyed, so it gets three tries."""
    import gc
    for _attempt in range(3):
        try:
            root = tk.Tk()
        except tk.TclError:
            gc.collect()
            continue
        root.withdraw()
        return root
    return None


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
        self.assertEqual(self.tabs(), ["Fins", "Bodies", "Discovered Species", "Collectopedia", "Breeding Calculator", "Breeding Planner",
                                       "Fin Pictures", "Body Pictures", "Egg Pictures"])
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
        self.assertTrue(out.read_text(encoding="utf-8-sig").startswith("Fin,How it is obtained"))

    def test_calculator(self) -> None:
        self.select("Breeding Calculator")
        names = [s.name for s in self.guide.calc_choices]
        self.guide.calc_boxes[0].current(names.index("Greenfin Spotanus"))
        self.guide.calc_boxes[1].current(names.index("Twin-Fin Spotanus"))
        self.guide.calc_effects_var.set("none")
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
        self.guide.calc_effects_var.set("max_mutation")   # recomputed at once, nothing else to press
        odds = [float(tree.set(i, "c3")) for i in tree.get_children()]
        self.assertAlmostEqual(sum(odds), 100.0, places=6)
        self.assertEqual(len(odds), len(self.guide.model.children((20, 16), (20, 20), "max_mutation")))

    def test_planner(self) -> None:
        self.select("Breeding Planner")
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.select("Breeding Planner")
        names = [s.name for s in self.guide.have_choices]
        self.guide.have_list.selection_clear(0, "end")
        for name in ("Pink Fatfish", "Golden Goldbulb"):
            self.guide.have_list.selection_set(names.index(name))
        wants = [s.name for s in self.guide.want_choices]
        self.guide.want_box.current(wants.index("Canary Fire-Arrow"))
        self.guide.plan_effects_var.set("none")
        self.guide.plan()
        self.assertTrue(self.guide.plan_busy or self.guide.trees["planner"].get_children())
        self.guide.wait_for_plan()
        tree = self.guide.trees["planner"]
        rows = [tree.item(i, "values") for i in tree.get_children()]
        self.assertEqual(rows, [("1", "Breeding", "Pink Fatfish", "Golden Goldbulb", "Canary Fire-Arrow", "100.00")])

    def test_each_tab_has_its_own_effects(self) -> None:
        """Changing the effects on one tab recomputes that tab and never leaves the other
        showing odds worked out with a different choice than the one ticked."""
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.assertIsNot(self.guide.calc_effects_var, self.guide.plan_effects_var)
        names = [s.name for s in self.guide.calc_choices]
        self.guide.calc_boxes[0].current(names.index("Greenfin Spotanus"))
        self.guide.calc_boxes[1].current(names.index("Twin-Fin Spotanus"))
        self.guide.calculate()
        tree = self.guide.trees["calculator"]
        self.assertEqual(len(tree.get_children()), 1)
        self.guide.plan_effects_var.set("max")                       # the planner's own choice
        self.guide.wait_for_plan()
        self.assertEqual(len(tree.get_children()), 1)                 # the calculator is unchanged
        self.assertEqual(self.guide.calc_effects_var.get(), "none")
        self.guide.calc_effects_var.set("max_mutation")
        self.assertEqual(len(tree.get_children()),
                         len(self.guide.model.children((20, 16), (20, 20), "max_mutation")))
        out = Path(self.tmp.name) / "calc.csv"
        self.select("Breeding Calculator")
        self.guide.export("csv", str(out))
        self.assertEqual(len(out.read_text(encoding="utf-8-sig").strip().splitlines()), 1 + len(tree.get_children()))

    def test_a_sort_by_a_column_that_goes_away(self) -> None:
        """Sort All Species by Discovered, then turn spoilers off: that column is gone, so the
        sort is dropped, and every tab is still built."""
        self.guide.spoilers_var.set(True)
        self.root.update()
        sheet = self.guide.sheets["species"]
        self.guide.sort("species", sheet.columns.index("Discovered"))
        self.guide.spoilers_var.set(False)
        self.root.update()
        self.assertNotIn("Discovered", self.guide.sheets["species"].columns)
        self.assertNotIn("species", self.guide.sort_state)
        self.assertEqual(self.guide.build_errors, [])
        self.assertIn("calculator", self.guide.trees)
        self.assertIn("planner", self.guide.trees)
        # a sort whose column is still there survives the refresh
        self.guide.sort("species", 4)
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.assertEqual(self.guide.sort_state["species"], ("Base value", False))
        tree = self.guide.trees["species"]
        values = [int(tree.set(i, "c4")) for i in tree.get_children()]
        self.assertEqual(values, sorted(values))

    def test_a_tab_that_fails_does_not_stop_the_others(self) -> None:
        saved = bg.View.species_sheet

        def broken(view):
            raise RuntimeError("test failure")

        bg.View.species_sheet = broken
        try:
            self.guide.spoilers_var.set(True)
            self.root.update()
        finally:
            bg.View.species_sheet = saved
        self.assertEqual(len(self.tabs()), 9)
        self.assertIn("calculator", self.guide.trees)
        self.assertIn("planner", self.guide.trees)
        self.assertNotIn("species", self.guide.trees)
        self.assertIn("test failure", self.guide.status_var.get())

    def test_a_search_started_before_a_refresh_never_lands_after_it(self) -> None:
        import threading
        import time
        release = threading.Event()
        model = self.guide.model
        real_plan = model.plan

        def slow_plan(*args, **kwargs):
            release.wait(5)
            return real_plan(*args, **kwargs)

        model.plan = slow_plan
        try:
            self.guide.spoilers_var.set(True)
            self.root.update()
            names = [s.name for s in self.guide.have_choices]
            self.guide.have_list.selection_clear(0, "end")
            for name in ("Pink Fatfish", "Golden Goldbulb"):
                self.guide.have_list.selection_set(names.index(name))
            wants = [s.name for s in self.guide.want_choices]
            self.guide.want_box.current(wants.index("Canary Fire-Arrow"))
            self.guide.plan()
            self.assertTrue(self.guide.plan_busy)
            self.guide.spoilers_var.set(False)               # the refresh, while it runs
            self.root.update()
            self.assertFalse(self.guide.plan_busy)
            self.assertNotIn("disabled", self.guide.plan_button.state())
            self.assertEqual(str(self.guide.window.cget("cursor")), "")
            release.set()
            end = time.monotonic() + 1.5
            while time.monotonic() < end:
                self.root.update()
                time.sleep(0.02)
            self.assertEqual(self.guide.trees["planner"].get_children(), ())
            self.assertFalse(self.guide.plan_busy)
        finally:
            release.set()
            model.plan = real_plan

    def test_picks_are_kept_across_a_refresh_when_still_there(self) -> None:
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.select("Breeding Calculator")
        names = [s.name for s in self.guide.calc_choices]
        self.guide.calc_boxes[0].current(names.index("Twin-Fin Spotanus"))
        self.guide.calc_boxes[1].current(names.index("Canary Fire-Arrow"))       # undiscovered
        wants = [s.name for s in self.guide.want_choices]
        self.guide.want_box.current(wants.index("Pink Fatfish"))
        self.guide.spoilers_var.set(False)
        self.root.update()
        self.assertEqual(self.guide.current_sheet_id(), "calculator")            # the same tab
        picked = [self.guide.calc_choices[b.current()].name for b in self.guide.calc_boxes]
        self.assertEqual(picked[0], "Twin-Fin Spotanus")
        self.assertNotEqual(picked[1], "Canary Fire-Arrow")                    # no longer a choice
        self.assertEqual(self.guide.want_choices[self.guide.want_box.current()].name, "Pink Fatfish")

    def test_plant_model_loads(self) -> None:
        self.guide.game_var.set("Plant Tycoon")
        self.root.update()
        self.assertEqual(self.tabs(), ["Flowers", "Foliage", "Discovered Species", "Collectopedia", "Breeding Calculator", "Breeding Planner",
                                       "Flower Pictures", "Foliage Pictures", "Seed Pictures"])
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

    def test_every_tab_has_a_scrolling_details_pane(self) -> None:
        """Both games, every tab: a ttk.Scrollbar beside the details pane (the Tools tab's
        style), and long text scrolls."""
        for game in ("Fish Tycoon", "Plant Tycoon"):
            self.guide.game_var.set(game)
            self.guide.spoilers_var.set(True)
            self.root.update()
            for sheet_id in self.guide.tab_ids:
                if sheet_id.startswith("pictures:"):           # a picture grid, which scrolls itself
                    self.assertIsInstance(self.guide.pictures[sheet_id]["canvas"].scrollbar, tk.ttk.Scrollbar)
                    continue
                self.select(self.tabs()[self.guide.tab_ids.index(sheet_id)])
                text = self.guide.details[sheet_id]
                self.assertIsInstance(text.scrollbar, tk.ttk.Scrollbar, sheet_id)
                self.assertEqual(str(text.scrollbar.cget("orient")), "vertical")
                self.guide._set_details(sheet_id, "\n".join(f"line {i}" for i in range(200)))
                self.root.update()
                self.assertLess(text.yview()[1], 1.0, sheet_id)
                text.yview_scroll(20, "units")
                self.root.update()
                self.assertGreater(text.yview()[0], 0.0, sheet_id)
                self.assertAlmostEqual(text.scrollbar.get()[0], text.yview()[0], places=3)

    def test_three_effects_buttons_on_both_tabs_in_both_games(self) -> None:
        for game, mutation in (("Fish Tycoon", "Wasp Grouper"), ("Plant Tycoon", "Mutation Liquid")):
            self.guide.game_var.set(game)
            self.guide.spoilers_var.set(True)
            self.root.update()
            for buttons in (self.guide.calc_effect_buttons, self.guide.plan_effect_buttons):
                self.assertEqual([b.cget("text") for b in buttons],
                                 ["0 effects", "Max effects, without", f"Max effects, with {mutation}"])
                self.assertEqual([b.cget("value") for b in buttons], ["none", "max", "max_mutation"])
            tree = self.guide.trees["calculator"]
            counts = {}
            for value in ("none", "max", "max_mutation"):
                self.guide.calc_effects_var.set(value)
                counts[value] = [tree.item(i, "values") for i in tree.get_children()]
                pane = self.guide.details["calculator"].get("1.0", "end")
                self.assertEqual(" ".join(self.guide.model.effects_text(value)), pane.strip())
            self.assertIn(mutation, " ".join(self.guide.model.effects_text("max_mutation")))
            self.assertEqual(counts["none"], counts["max"])
            self.assertNotEqual(counts["max"], counts["max_mutation"])
            self.guide.calc_effects_var.set("none")

    def test_the_planner_tab_is_renamed_everywhere(self) -> None:
        self.assertIn("Breeding Planner", self.tabs())
        self.assertNotIn("Have to Want", self.tabs())
        self.assertIn("Breeding Planner", " ".join(bg.HELP[1]))
        for name in ("README.md", "How to Use.txt", "CHANGELOG.md"):
            text = (bg_root() / name).read_text(encoding="utf-8")
            self.assertIn("Breeding Planner", text, name)
            self.assertNotIn("Have to Want", text, name)

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
