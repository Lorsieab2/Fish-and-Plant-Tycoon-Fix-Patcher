"""The Breeding Guide's Collectopedia tab (src/breeding_collectopedia.py, the window in
src/breeding_guide.py) and the Seed Pictures grid.

Every save here is a small synthetic file in a temporary folder, never the owner's: the ticks
are exactly the save's discovered records (stock, DS Exclusive Fish, Unused Flowers), the
counts per rarity tier and per part, nothing undiscovered named with spoilers off (the tab,
the tooltips, the exports), and the tab follows a change of save or player.
"""

from __future__ import annotations

import csv
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_collectopedia as bc  # noqa: E402
import breeding_fish as bf  # noqa: E402
import breeding_guide as bg  # noqa: E402
import breeding_plant as bp  # noqa: E402
from test_breeding_fish import make_save, make_settings, make_sidecar  # noqa: E402
from test_breeding_guide_parts import (DS_IN_SAVE, DS_IN_SIDECAR, FISH_FOUND, NEW_FOUND, PLANT_FOUND,  # noqa: E402
                                       assert_never_named, make_new_flowers, make_plant_save,
                                       undiscovered_words, view_for)


def every_key(cp: bc.Collectopedia) -> set:
    return {tuple(s.key) for s in cp.species}


def ticked(cp: bc.Collectopedia) -> set:
    return {k for k in every_key(cp) if cp.ticked(k)}


class TickTests(unittest.TestCase):
    """The ticks are exactly the save's discovered records, nothing more or less."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fish_stock(self) -> None:
        make_save(self.folder, 1, FISH_FOUND)
        for spoilers in (False, True):
            cp = bc.Collectopedia(view_for("fish", self.folder, 1, spoilers))
            self.assertFalse(cp.model.extras)
            self.assertEqual(len(cp.species), 21 * 21)
            self.assertEqual(ticked(cp), set(FISH_FOUND))
            self.assertEqual(ticked(cp), bf.read_discovered(self.folder, 1, extras=False))
            self.assertEqual(cp.collected(), (4, 441))
            self.assertEqual(cp.summary(), "4 of 441 species collected (0.9%).")
            # rows are bodies, columns fins, both in the game's order
            self.assertEqual((cp.row_kind, cp.col_kind), ("body", "fin"))
            self.assertEqual([p.index for p in cp.rows], list(bf.PC_GENES))

    def test_fish_ds(self) -> None:
        make_save(self.folder, 1, {**FISH_FOUND, **DS_IN_SAVE}, ds_columns=True)
        cp = bc.Collectopedia(view_for("fish", self.folder, 1, False))
        self.assertFalse(cp.model.extras)                       # no data file: the setting is off
        self.assertEqual(ticked(cp), set(FISH_FOUND))
        make_sidecar(self.folder, 1, DS_IN_SIDECAR)
        cp = bc.Collectopedia(view_for("fish", self.folder, 1, False))
        self.assertTrue(cp.model.extras)
        expected = set(FISH_FOUND) | set(DS_IN_SAVE) | set(DS_IN_SIDECAR)
        self.assertEqual(ticked(cp), expected)
        self.assertEqual(ticked(cp), bf.read_discovered(self.folder, 1, extras=True))
        self.assertEqual(len(cp.species), 28 * 28)
        self.assertEqual(cp.summary(), "6 of 784 species collected (0.8%), 343 of them DS Exclusive Fish (2 collected).")

    def test_plant_stock_and_unused_flowers(self) -> None:
        make_plant_save(self.folder, 2, PLANT_FOUND)
        cp = bc.Collectopedia(view_for("plant", self.folder, 2, False))
        self.assertEqual((cp.row_kind, cp.col_kind), ("foliage", "flower"))
        self.assertEqual(len(cp.species), 23 * 23)
        self.assertEqual(ticked(cp), PLANT_FOUND)
        make_new_flowers(self.folder, 2, NEW_FOUND)
        cp = bc.Collectopedia(view_for("plant", self.folder, 2, False))
        self.assertTrue(cp.model.extras)
        self.assertEqual(len(cp.species), 23 * 37)
        self.assertEqual(ticked(cp), PLANT_FOUND | NEW_FOUND)
        self.assertEqual(ticked(cp), bp.discovered(self.folder, 2, True))
        self.assertEqual(cp.summary(), "4 of 851 species collected (0.5%), 322 of them Unused Flowers (1 collected).")

    def test_no_save(self) -> None:
        cp = bc.Collectopedia(bg.View(bf.load(None, False), None, False))
        self.assertEqual(ticked(cp), set())
        self.assertEqual(cp.summary(), "No save chosen: 0 of 441 species collected.")
        self.assertTrue(all(row[0] == "?" for row in cp.sheet().rows))


class CountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fish_tiers_and_parts(self) -> None:
        # FISH_FOUND: Silky Shark (0, 0), Pink Fatfish (4, 4), Pink Goldbulb (10, 4), Greenfin Spotanus (20, 16)
        make_save(self.folder, 1, FISH_FOUND)
        cp = bc.Collectopedia(view_for("fish", self.folder, 1, False))
        tiers = cp.tiers()
        self.assertEqual([t for t, _g, _n in tiers], ["Common", "Unusual", "Rare"])
        self.assertEqual(sum(n for _t, _g, n in tiers), 441)
        for tier, got, total in tiers:
            self.assertEqual(total, sum(s.rarity == tier for s in cp.species))
            self.assertEqual(got, sum(s.rarity == tier for s in cp.species if tuple(s.key) in FISH_FOUND))
        self.assertEqual(sum(g for _t, g, _n in tiers), 4)
        self.assertEqual(cp.tier_text(), "By rarity: " + "; ".join(f"{t} {g} of {n}" for t, g, n in tiers) + ".")
        bodies = {p.name: (g, n) for p, g, n in cp.part_counts("body")}
        fins = {p.name: (g, n) for p, g, n in cp.part_counts("fin")}
        self.assertEqual(bodies["Shark"], (1, 21))
        self.assertEqual(bodies["Fatfish"], (1, 21))
        self.assertEqual(bodies["Grouper"], (0, 21))
        self.assertEqual(fins["Pink"], (2, 21))
        self.assertEqual(fins["Greenfin"], (1, 21))
        lines = cp.part_progress("fin")
        self.assertIn("Fin Pink: 2 of 21 bodies", lines)
        self.assertEqual(lines[-1], "18 undiscovered fins: 0 of 378 species")
        self.assertIn("Body Shark: 1 of 21 fins", cp.part_progress("body"))
        # spoilers on: every part by name, no lumped line
        on = bc.Collectopedia(view_for("fish", self.folder, 1, True))
        self.assertEqual(len(on.part_progress("fin")), 21)
        self.assertIn("Fin Wasp: 0 of 21 bodies", on.part_progress("fin"))

    def test_plant_tiers_and_parts(self) -> None:
        make_plant_save(self.folder, 2, PLANT_FOUND)
        make_new_flowers(self.folder, 2, NEW_FOUND)
        cp = bc.Collectopedia(view_for("plant", self.folder, 2, False))
        tiers = cp.tiers()
        self.assertEqual([t for t, _g, _n in tiers], ["Common", "Endangered", "Extinct", "Legendary"])
        self.assertEqual(dict((t, n) for t, _g, n in tiers)["Legendary"], 23 * 14)
        self.assertEqual(dict((t, g) for t, g, _n in tiers),
                         {"Common": 2, "Endangered": 1, "Extinct": 0, "Legendary": 1})   # (1,1) (5,5); (9,3); (5,30)
        foliage = {p.name: (g, n) for p, g, n in cp.part_counts("foliage")}
        self.assertEqual(foliage["Astera"], (2, 37))
        self.assertIn("Foliage Astera: 2 of 37 flowers", cp.part_progress("foliage"))
        self.assertIn("Flower Silvermist: 1 of 23 foliage", cp.part_progress("flower"))


class SpoilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def check_no_leak(self, view) -> None:
        cp = bc.Collectopedia(view)
        words = undiscovered_words(view)
        assert_never_named(self, cp.texts(), words)
        for which, _label in bc.FILTERS:
            sheet = cp.sheet(which)
            out_csv, out_xlsx = self.folder / f"{which}.csv", self.folder / f"{which}.xlsx"
            bg.export_csv(out_csv, sheet)
            bg.export_xlsx(out_xlsx, sheet)
            with open(out_csv, newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(len(rows) - 1, len(sheet.rows))
            assert_never_named(self, [c for r in rows + bg.read_xlsx(out_xlsx) for c in r], words)
        # a locked entry has no name and no rarity unless both its parts are seen
        for s in cp.species:
            if not cp.ticked(s.key):
                self.assertEqual(cp.species_label(s.key), "?")
                self.assertTrue(cp.tooltip(s.key).startswith("Not collected yet"))
        return cp

    def test_fish(self) -> None:
        make_save(self.folder, 1, {**FISH_FOUND, **DS_IN_SAVE}, ds_columns=True)
        make_sidecar(self.folder, 1, DS_IN_SIDECAR)
        view = view_for("fish", self.folder, 1, False)
        self.assertIn("Silky Fatfish", undiscovered_words(view))      # both parts seen, the species is not
        cp = self.check_no_leak(view)
        self.assertEqual(cp.tooltip((4, 0)), "Not collected yet (Silky fin, Fatfish body).")
        self.assertEqual(cp.tooltip((13, 6)), "Not collected yet (? fin, ? body).")       # the Wasp Grouper
        self.assertEqual(cp.row((13, 6)), ["?", "?", "?", "?", "No", ""])
        self.assertEqual(cp.row((0, 0)), ["Silky Shark", "Shark", "Silky", cp.by_key[(0, 0)].rarity, "Yes", ""])
        self.assertIn("Silky Shark", cp.tooltip((0, 0)))

    def test_plant(self) -> None:
        make_plant_save(self.folder, 2, PLANT_FOUND)
        make_new_flowers(self.folder, 2, NEW_FOUND)
        self.check_no_leak(view_for("plant", self.folder, 2, False))

    def test_spoilers_on_names_everything(self) -> None:
        make_save(self.folder, 1, FISH_FOUND)
        cp = bc.Collectopedia(view_for("fish", self.folder, 1, True))
        names = {row[0] for row in cp.sheet().rows}
        self.assertEqual(names, {s.name for s in cp.species})
        self.assertEqual(cp.row((13, 6))[:5], ["Wasp Grouper", "Grouper", "Wasp", cp.by_key[(13, 6)].rarity, "No"])
        self.assertIn("not collected yet", cp.tooltip((13, 6)))

    def test_filters(self) -> None:
        make_save(self.folder, 1, FISH_FOUND)
        cp = bc.Collectopedia(view_for("fish", self.folder, 1, False))
        self.assertEqual(len(cp.sheet("all").rows), 441)
        self.assertEqual({r[0] for r in cp.sheet("collected").rows},
                         {"Silky Shark", "Pink Fatfish", "Pink Goldbulb", "Greenfin Spotanus"})
        self.assertEqual(len(cp.sheet("missing").rows), 437)
        # the Pink column: the collected Pinks by name, the locked ones by their Pink fin
        self.assertEqual(cp.matching(cp.sheet("all"), "pink"), {(b, 4) for b in bf.PC_GENES})


def make_two_players(root: Path) -> Path:
    folder = root / "LDW" / "Fish Tycoon - Modded Upgrades"
    folder.mkdir(parents=True)
    make_settings(folder, ["Tester", "Second", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER"])
    make_save(folder, 1, FISH_FOUND)
    make_save(folder, 2, {(13, 6): 95})
    return root


class WindowTests(unittest.TestCase):
    def setUp(self) -> None:
        from test_breeding_guide import tk_root
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display for Tk")
        self.tmp = tempfile.TemporaryDirectory()
        documents = make_two_players(Path(self.tmp.name))
        bg._open_window = None
        self.guide = bg.open_window(self.root, "fish", settings={"show_spoilers": False}, documents=documents)
        self.root.update()
        nb = self.guide.notebook
        nb.select(nb.tabs()[self.guide.tab_ids.index("collectopedia")])
        self.root.update()

    def tearDown(self) -> None:
        self.guide.close()
        self.root.destroy()
        self.tmp.cleanup()

    def marks(self) -> dict:
        return {k: v[0] for k, v in self.guide.collect["state"].items()}

    def test_the_grid_ticks_what_the_save_has(self) -> None:
        c = self.guide.collect
        self.assertEqual(self.guide.current_sheet_id(), "collectopedia")
        self.assertEqual(c["header"].cget("text"), "4 of 441 species collected (0.9%).")
        marks = self.marks()
        self.assertEqual(len(marks), 441)
        self.assertEqual({k for k, m in marks.items() if m == "✓"}, set(FISH_FOUND))
        self.assertEqual({m for k, m in marks.items() if k not in FISH_FOUND}, {"?"})
        # pictures only for the parts the save has discovered (none here without a game copy is fine)
        self.assertTrue(set(c["thumbs"]) <= {(p.kind, p.index) for p in c["cp"].rows + c["cp"].cols
                                             if c["cp"].part_known(p)})
        # the labels: "?" for an undiscovered part, with its count
        self.assertEqual(c["labels"][("fin", 6)], "?  0/21")
        self.assertEqual(c["labels"][("fin", 4)], "Pink  2/21")
        # pointing at a box: the tooltip and the panel, with no picture for a locked one
        cp = c["cp"]
        for key, expected in (((4, 0), "Not collected yet (Silky fin, Fatfish body)."),
                              ((0, 0), cp.tooltip((0, 0)))):
            r = [p.index for p in cp.rows].index(key[0])
            col = [p.index for p in cp.cols].index(key[1])
            event = types.SimpleNamespace(x=self.guide.ROW_HEAD + col * self.guide.CELL + 5,
                                          y=self.guide.COL_HEAD + r * self.guide.CELL + 5, x_root=10, y_root=10)
            self.guide._collect_hover(event)
            self.assertEqual(c["tip_text"], expected)
            self.assertEqual(c["picked_text"].cget("text"), expected)
        self.guide._collect_hover(types.SimpleNamespace(x=2, y=2, x_root=0, y_root=0))
        self.assertFalse(c["picture_a"].cget("image"))

    def test_filters_search_list_and_export(self) -> None:
        guide = self.guide
        guide.collect_filter_var.set("collected")
        self.root.update()
        tree = guide.trees["collectopedia"]
        self.assertEqual(len(tree.get_children()), 4)
        self.assertEqual(sum(on for _m, on in guide.collect["state"].values()), 4)   # the rest faded
        self.assertEqual(len(guide.collect["state"]), 441)                          # still lined up
        guide.collect_filter_var.set("missing")
        guide.search_var.set("Pink")
        self.root.update()
        self.assertEqual({tree.item(i, "values")[0] for i in tree.get_children()}, {"?"})
        self.assertEqual(len(tree.get_children()), 19)                    # the Pink fin's 21 bodies, 2 collected
        guide.collect_mode_var.set("list")
        self.root.update()
        self.assertTrue(guide.collect["list_frame"].winfo_ismapped())
        self.assertFalse(guide.collect["grid_frame"].winfo_ismapped())
        words = undiscovered_words(guide.view)
        for fmt in ("csv", "xlsx"):
            out = Path(self.tmp.name) / f"collect.{fmt}"
            self.assertEqual(guide.export(fmt, str(out)), str(out))
            if fmt == "csv":
                with open(out, newline="", encoding="utf-8-sig") as handle:
                    rows = list(csv.reader(handle))
            else:
                rows = bg.read_xlsx(out)
            self.assertEqual(rows[0], ["Species", "Body", "Fin", "Rarity", "Collected", "Patcher"])
            self.assertEqual(len(rows), 20)
            assert_never_named(self, [c for r in rows for c in r], words)
        guide.search_var.set("")
        guide.collect_filter_var.set("all")
        guide.collect_mode_var.set("grid")
        self.root.update()
        # the choices survive a spoiler switch, and spoilers on names everything
        guide.collect_mode_var.set("list")
        guide.spoilers_var.set(True)
        self.root.update()
        self.assertEqual(guide.current_sheet_id(), "collectopedia")
        self.assertTrue(guide.collect["list_frame"].winfo_ismapped())           # still the list
        self.assertEqual(len(guide.trees["collectopedia"].get_children()), 441)
        names = {guide.trees["collectopedia"].item(i, "values")[0] for i in guide.trees["collectopedia"].get_children()}
        self.assertIn("Wasp Grouper", names)
        self.assertEqual({m for m in self.marks().values()}, {"✓", ""})

    def test_a_save_or_player_change_refreshes_the_tab(self) -> None:
        guide = self.guide
        self.assertEqual({k for k, m in self.marks().items() if m == "✓"}, set(FISH_FOUND))
        guide.slot_box.current(1)                          # Player 2: only the Wasp Grouper
        guide._reload()
        self.root.update()
        self.assertEqual({k for k, m in self.marks().items() if m == "✓"}, {(13, 6)})
        self.assertEqual(guide.collect["header"].cget("text"), "1 of 441 species collected (0.2%).")
        # the save changes on disk: picking the player again reads it fresh
        folder = guide.current_folder()
        make_save(folder, 2, {(13, 6): 95, (5, 5): 9})
        guide._reload()
        self.root.update()
        self.assertEqual({k for k, m in self.marks().items() if m == "✓"}, {(13, 6), (5, 5)})
        guide.slot_box.current(0)
        guide._reload()
        self.root.update()
        self.assertEqual({k for k, m in self.marks().items() if m == "✓"}, set(FISH_FOUND))

    def test_the_help_describes_it_and_fits_the_screen(self) -> None:
        window = bg.show_help(self.guide.window)
        self.root.update()
        try:
            text = window.help_text.get("1.0", "end")
            self.assertIn("Collectopedia", text)
            self.assertIn("only the save ticks or unticks a box", text)
            self.assertIn("Seed Pictures is a grid", text)
            self.assertLessEqual(window.winfo_reqheight(), window.winfo_screenheight())
        finally:
            window.destroy()

    def test_plant_tab(self) -> None:
        self.guide.game_var.set("Plant Tycoon")
        self.root.update()
        self.assertIn("collectopedia", self.guide.tab_ids)
        c = self.guide.collect
        self.assertEqual(len(c["cells"]), len(c["cp"].species))
        self.assertEqual((c["cp"].row_kind, c["cp"].col_kind), ("foliage", "flower"))


class SeedGridTests(unittest.TestCase):
    """Seed Pictures: a row per foliage by class (A, B, C, D), the game's order within; a
    column per seed tier, lowest first; Legendary last with Unused Flowers."""

    A, B, C, D = (1, 5, 9, 13, 17), (3, 7, 11, 15), (2, 4, 6, 8, 10, 12, 14, 16), (18, 19, 20, 21, 22, 23)

    def test_rows_columns_and_headers(self) -> None:
        columns, rows = bg.seed_grid(bg.View(bp.load(None, False), set(), True))
        self.assertEqual(columns, ["Common", "Endangered", "Extinct", "Extinct (Arthurium to Tilia flower)"])
        self.assertEqual([p.index for p, _l, _c in rows], list(self.A + self.B + self.C + self.D))
        self.assertEqual([bg.foliage_class(p.index) for p, _l, _c in rows],
                         ["A"] * 5 + ["B"] * 4 + ["C"] * 8 + ["D"] * 6)
        self.assertEqual(rows[0][1], "Reptans\nCommon, class A")
        self.assertEqual(rows[5][1], "Grass\nEndangered, class B")
        self.assertEqual(rows[-1][1], "Ridgeball\nExtinct, class D")
        for part, _label, cells in rows:
            self.assertEqual([c.tier for c in cells], columns)
            self.assertEqual([c.art[0].index for c in cells], [(part.index - 1) * 4 + k for k in range(4)])
            self.assertTrue(all(c.art[0].file == "seed_grid.png" for c in cells))
        # Unused Flowers on: the Legendary Seed last
        columns, rows = bg.seed_grid(bg.View(bp.load(None, True), set(), True))
        self.assertEqual(columns[-1], "Legendary")
        self.assertEqual(len(columns), 5)
        for part, _label, cells in rows:
            self.assertEqual((cells[-1].art[0].file, cells[-1].art[0].index),
                             ("seed_grid_legendary.png", 95 + part.index))

    def test_spoilers_off(self) -> None:
        # Spotted Reptans (1, 1), Bluestar Astera (5, 5), Daisy Maranta (9, 3), Arthurium Scandens (2, 18)
        view = bg.View(bp.load(None, False), {(1, 1), (5, 5), (9, 3), (2, 18)}, False)
        columns, rows = bg.seed_grid(view)
        self.assertEqual(columns[3], "Extinct (the rarest flowers)")           # Tilia is not discovered
        self.assertEqual([p.name for p, _l, _c in rows], ["Reptans", "Astera", "Maranta", "Scandens"])
        self.assertTrue(all(len(cells) == 4 for _p, _l, cells in rows))       # every row lined up

    def test_the_tab(self) -> None:
        from test_breeding_guide import make_documents, tk_root
        from test_breeding_pictures import make_plant_copy
        root = tk_root()
        if root is None:
            self.skipTest("no display for Tk")
        with tempfile.TemporaryDirectory() as tmp:
            bg._open_window = None
            guide = bg.open_window(root, "plant", settings={"show_spoilers": True},
                                   documents=make_documents(Path(tmp)))
            try:
                root.update()
                copy = make_plant_copy(Path(tmp))
                guide.art_source = lambda: bg.breeding_pictures.ArtSource(copy)
                guide._refresh()
                root.update()
                built = guide.pictures["pictures:seeds"]
                columns, rows = built["grid"]
                self.assertEqual(len(built["cells"]), 4 * 23)
                self.assertTrue(all(image is not None for _i, image, _l in built["cells"]))
                self.assertEqual(built["cells"][0][2], "Reptans seed, Common")
                self.assertEqual(built["cells"][3][2], "Reptans seed, Extinct (Arthurium to Tilia flower)")
                inner = built["canvas"].winfo_children()[0]
                heads = [w.cget("text") for w in inner.grid_slaves(row=0)]
                self.assertEqual(sorted(heads), sorted(columns))
            finally:
                guide.close()
                root.destroy()


if __name__ == "__main__":
    unittest.main()
