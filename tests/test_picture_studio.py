"""The Picture Studio window (src/picture_studio.py) and its wiring, headless, on synthetic
saves and a stand-in game copy (no owner data, no game art): the save list by tank, the
previews, Save PNG at every size and Save all, Make your own with Show Spoilers on and off,
that it reads none of the patcher window's settings, never writes the save, and that the
window and its help fit the screen."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import picture_image as pi  # noqa: E402
import picture_studio as ps  # noqa: E402
import pictures_fish as pf  # noqa: E402
from test_breeding_fish import make_save, make_settings  # noqa: E402
from test_breeding_guide import tk_root  # noqa: E402
from test_pictures_fish import fake_game_copy, put_fish  # noqa: E402

DISCOVERED = {(11, 11): 40, (13, 6): 30}


class ExportChoiceTests(unittest.TestCase):
    def test_sizes(self) -> None:
        self.assertEqual(ps.export_options("1x"), {"margin": pi.MARGIN, "scale": 1})
        self.assertEqual(ps.export_options("4x", margin=False), {"margin": 0, "scale": 4})
        self.assertEqual(ps.export_options("custom", "300", ""), {"margin": pi.MARGIN, "size": (300, 0)})
        with self.assertRaises(pi.PictureError):
            ps.export_options("custom", "abc", "")

    def test_detect_settings_reads_the_copys_log_then_the_save_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            save = parent / "saves" / "Fish Tycoon - Modded"
            save.mkdir(parents=True)
            self.assertEqual(ps.detect_settings("fish", save, 1, [parent])[0], frozenset())
            (save / "Fish Tycoon Fix Patcher Data").mkdir()
            (save / "Fish Tycoon Fix Patcher Data" / "Tank Animals 1.dat").write_bytes(b"x")
            self.assertEqual(ps.detect_settings("fish", save, 1, [parent])[0], frozenset({"ds_store"}))
            copy = parent / "Fish Tycoon - Modded"
            copy.mkdir()
            (copy / "Fish Tycoon - Modded.exe").write_bytes(b"MZ")
            (copy / "FishTycoonBugFixPatchLog.json").write_text('{"enabled_settings": ["ds_fish"]}', encoding="utf-8")
            self.assertEqual(ps.detect_settings("fish", save, 1, [parent])[0], frozenset({"ds_fish"}))


class WindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display for Tk")
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.documents = base / "docs"
        self.folder = self.documents / "LDW" / "Fish Tycoon - Modded"
        self.folder.mkdir(parents=True)
        make_settings(self.folder, ["Tester", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER"])
        save = make_save(self.folder, 1, DISCOVERED)
        put_fish(save, 0, 0, 11, 11, 25)
        put_fish(save, 0, 1, 13, 6, 9)
        put_fish(save, 1, 0, 3, 4, 2)
        put_fish(save, 3, 0, 0, 0, 30, 60, 1)
        self.copy = fake_game_copy(base / "games" / "Fish Tycoon")
        self.before = {p: p.read_bytes() for p in self.documents.rglob("*") if p.is_file()}
        self.settings = {"show_spoilers": False}
        ps._open_window = None
        self.studio = ps.open_window(self.root, "fish", settings=self.settings, save_settings=lambda: None,
                                     documents=self.documents, game_parents=[str(self.copy.parent)])
        self.studio.quiet = True
        self.root.update()

    def tearDown(self) -> None:
        if getattr(self, "studio", None) is not None:
            self.studio.close()
        if self.root is not None:
            self.root.destroy()
            self.tmp.cleanup()

    def tree_items(self) -> dict[str, list[str]]:
        tree = self.studio.save_tree
        return {tree.item(p, "text"): [tree.item(c, "text") for c in tree.get_children(p)] for p in tree.get_children()}

    def select(self, label: str) -> None:
        tree = self.studio.save_tree
        for node, item in self.studio.item_nodes.items():
            if item.label == label:
                tree.selection_set(node)
                self.root.update()
                return
        self.fail(f"{label} is not listed")

    def test_lists_the_save_by_tank_and_previews(self) -> None:
        tabs = [self.studio.notebook.tab(t, "text") for t in self.studio.notebook.tabs()]
        self.assertEqual(tabs, ["From my save", "Make your own"])
        items = self.tree_items()
        self.assertEqual(items["Tank 1"], ["Crimson Comet (adult, age 25)", "Teen fish (age 9)"])
        self.assertEqual(items["Tank 2"], ["Baby fish (age 2)"])
        self.assertEqual(items["Isolation Tank"], ["Silky Shark (adult, age 30, sick (ick))"])
        self.select("Crimson Comet (adult, age 25)")
        image = self.studio.shown["save"]
        self.assertIsNotNone(image.bbox())
        self.assertIsNotNone(getattr(self.studio.save_preview["canvas"], "photo", None))

    def test_save_png_sizes_and_margin(self) -> None:
        self.select("Crimson Comet (adult, age 25)")
        shown = self.studio.shown["save"].cropped(0)
        out = Path(self.tmp.name) / "out"
        out.mkdir()
        for size, factor in (("1x", 1), ("2x", 2), ("4x", 4)):
            self.studio.size_var.set(size)
            self.studio.margin_var.set(False)
            path = self.studio.save_png("save", str(out / f"{size}.png"))
            image = pi.decode_png(path.read_bytes())
            self.assertEqual((image.width, image.height), (shown.width * factor, shown.height * factor))
            self.assertEqual(path.read_bytes()[25], 6, "RGBA")
        self.studio.margin_var.set(True)
        self.studio.size_var.set("custom")
        self.studio.width_var.set("200")
        self.studio.height_var.set("")
        path = self.studio.save_png("save", str(out / "custom.png"))
        image = pi.decode_png(path.read_bytes())
        self.assertEqual(image.width, 200)
        self.assertEqual(image.pixel(0, 0)[3], 0, "a clear margin")

    def test_save_all_in_a_tank(self) -> None:
        self.select("Teen fish (age 9)")
        out = Path(self.tmp.name) / "all"
        out.mkdir()
        target = self.studio.save_all(str(out))
        self.assertEqual(sorted(p.name for p in target.iterdir()),
                         ["Crimson Comet (adult, age 25).png", "Teen fish (age 9).png"])
        self.assertEqual(target.name, "Tester - Tank 1")

    def test_make_your_own_with_and_without_spoilers(self) -> None:
        boxes = self.studio.custom_boxes["fish"]
        self.assertEqual(list(boxes["body"]["box"].cget("values")), ["Comet", "Grouper"])
        self.assertEqual(list(boxes["fin"]["box"].cget("values")), ["Wasp", "Crimson"])
        self.studio.custom_notebook.select(0)
        self.root.update()
        self.assertIn("custom", self.studio.shown)
        self.studio.spoilers_var.set(True)
        self.root.update()
        self.assertEqual(len(self.studio.custom_boxes["fish"]["body"]["box"].cget("values")), 28)   # 21 + 7 DS
        self.assertTrue(self.settings["show_spoilers"], "the Breeding Guide's setting, remembered")
        spec = self.studio.custom_spec()
        self.assertEqual(spec["subject"], "fish")
        for tab in range(len(self.studio.subjects)):
            self.studio.custom_notebook.select(tab)
            self.root.update()
            self.assertIn("custom", self.studio.shown, self.studio.subjects[tab].title)

    def test_young_fish_are_named_only_with_spoilers(self) -> None:
        """The game names a fish only from age 20 (info panel 0x41D9ED): with Show Spoilers off a
        baby or teen is "Baby fish" / "Teen fish", in the list and in the PNG's file name; adults
        keep their species name; spoilers on names them all."""
        items = self.tree_items()
        self.assertEqual(items["Tank 1"], ["Crimson Comet (adult, age 25)", "Teen fish (age 9)"])
        self.assertEqual(items["Tank 2"], ["Baby fish (age 2)"])
        self.select("Teen fish (age 9)")
        self.assertEqual(self.studio.picture_name("save"), "Teen fish (age 9), Tank 1")
        out = Path(self.tmp.name) / "young"
        out.mkdir()
        target = self.studio.save_all(str(out))
        names = " ".join(p.name for p in target.iterdir())
        self.assertNotIn("Grouper", names)
        self.assertNotIn("Wasp", names)
        self.studio.spoilers_var.set(True)
        self.root.update()
        items = self.tree_items()
        self.assertEqual(items["Tank 1"], ["Crimson Comet (adult, age 25)", "Wasp Grouper (teen, age 9)"])
        self.assertEqual(items["Tank 2"], ["Pink Snout (baby, age 2)"])
        self.select("Wasp Grouper (teen, age 9)")
        self.assertEqual(self.studio.picture_name("save"), "Wasp Grouper (teen, age 9), Tank 1")
        self.studio.spoilers_var.set(False)
        self.root.update()
        self.assertEqual(self.tree_items()["Tank 2"], ["Baby fish (age 2)"])

    def add_tank_1_decoration_and_seahorse(self) -> None:
        """A rock ornament (sprite 178) and a Golden Seahorse in Tank 1, then the list again."""
        path = self.folder / "Fish Tycoon1.ldw"
        data = bytearray(path.read_bytes())
        at = pf.SAVE_HEADER - 8 + pf.ORN_BASE
        data[at] = 1
        struct.pack_into("<ii", data, at + 4, 100, 200)
        struct.pack_into("<i", data, at + 0x1C, 120)
        struct.pack_into("<i", data, at + 0x24, 178)
        path.write_bytes(bytes(data))
        put_fish(path, 0, 2, 22, 22, 21)
        self.studio.renderer._save_key = None
        self.studio._fill_save_list()
        self.root.update()

    def test_decorations_and_creatures_have_their_own_sub_list(self) -> None:
        """The owner's rule: under each tank, the decorations, creatures and anything else that is
        not a fish are in their own "Decorations and creatures" node, after the fish; a place
        with no fish lists its things directly."""
        self.add_tank_1_decoration_and_seahorse()
        tree = self.studio.save_tree
        tank = self.studio.location_nodes["Tank 1"]
        children = [tree.item(c, "text") for c in tree.get_children(tank)]
        self.assertEqual(children, ["Crimson Comet (adult, age 25)", "Teen fish (age 9)", "Decorations and creatures"])
        group = tree.get_children(tank)[-1]
        inside = [self.studio.item_nodes[c] for c in tree.get_children(group)]
        self.assertEqual(sorted(i.kind for i in inside), ["creature", "decoration"])
        self.assertIn("Golden Seahorse", [i.label for i in inside])
        for node, item in self.studio.item_nodes.items():
            if item.location == "Tank 1" and item.kind == "fish":
                self.assertEqual(tree.parent(node), tank)
        self.assertEqual([tree.item(c, "text") for c in tree.get_children(self.studio.location_nodes["Tank 2"])],
                         ["Baby fish (age 2)"])
        tree.selection_set(group)
        self.root.update()
        self.assertEqual(self.studio.selected_location(), "Tank 1")
        self.select("Golden Seahorse")
        self.assertIsNotNone(self.studio.shown.get("save"))

    def test_save_all_says_what_it_saves(self) -> None:
        """"Save all in this tank" (from a fish, or from the sub-list) saves the whole tank: the fish
        in the folder, the decorations and creatures in a "Decorations and creatures" folder in
        it, and says so."""
        self.add_tank_1_decoration_and_seahorse()
        self.assertIn("fish, creatures and decorations", self.studio.save_all_note.cget("text"))
        tree = self.studio.save_tree
        tree.selection_set(tree.get_children(self.studio.location_nodes["Tank 1"])[-1])
        self.root.update()
        out = Path(self.tmp.name) / "grouped"
        out.mkdir()
        target = self.studio.save_all(str(out))
        self.assertEqual(target.name, "Tester - Tank 1")
        self.assertEqual(sorted(p.name for p in target.iterdir()),
                         ["Crimson Comet (adult, age 25).png", "Decorations and creatures", "Teen fish (age 9).png"])
        inside = sorted(p.name for p in (target / "Decorations and creatures").iterdir())
        self.assertEqual(len(inside), 2)
        self.assertIn("Golden Seahorse.png", inside)
        self.assertIn("4 picture(s) of Tank 1", self.studio.last_message)
        self.assertIn("2 fish, and 2 in the \"Decorations and creatures\" folder", self.studio.last_message)

    def test_facing_and_frame_under_the_fish_preview(self) -> None:
        """The box under the preview is "Facing:" (Facing left / Facing right / Turning), in the
        save tab and Make your own, and it is shown for fish."""
        self.assertEqual(list(self.studio.facing_box.cget("values")), ["Facing left", "Facing right", "Turning"])
        self.assertTrue(self.studio.ways_frame.winfo_ismapped())
        labels = [w.cget("text") for w in self.studio.ways_frame.winfo_children() if isinstance(w, ttk.Label)]
        self.assertEqual(labels, ["Facing:", "Frame:"])
        fish = self.studio.custom_boxes["fish"]
        self.assertEqual(fish["facing"]["field"].label, "Facing")
        self.assertEqual(list(fish["facing"]["box"].cget("values")), ["Facing left", "Facing right", "Turning"])
        source = "\n".join((ROOT / f).read_text(encoding="utf-8") for f in
                           ("src/picture_studio.py", "src/pictures_fish.py", "README.md", "How to Use.txt"))
        self.assertNotIn("Swimming left", source)
        self.assertNotIn('"Swimming:"', source)
        self.studio.game_var.set("Plant Tycoon")
        self.root.update()
        self.assertFalse(self.studio.ways_frame.winfo_ismapped(), "plants have no Facing or Frame")
        self.assertNotIn("facing", {k for boxes in self.studio.custom_boxes.values() for k in boxes})

    def test_never_writes_the_save(self) -> None:
        self.select("Silky Shark (adult, age 30, sick (ick))")
        self.studio.facing_box.current(1)
        self.studio._show_saved()
        after = {p: p.read_bytes() for p in self.documents.rglob("*") if p.is_file()}
        self.assertEqual(self.before, after)

    def test_fits_the_screen_and_the_help_too(self) -> None:
        window = self.studio.window
        window.update_idletasks()
        screen_w, screen_h = window.winfo_screenwidth(), window.winfo_screenheight()
        width, height = (int(v) for v in window.geometry().split("+")[0].split("x"))
        self.assertLessEqual(width, screen_w)
        self.assertLessEqual(height, screen_h - 60)
        self.assertLessEqual(window.winfo_reqheight(), screen_h)
        help_window = ps.show_help(window)
        help_window.update_idletasks()
        self.assertLessEqual(help_window.winfo_reqheight(), screen_h - 40)
        self.assertIn("Show Spoilers", help_window.help_text.get("1.0", "end"))
        help_window.destroy()

    def test_plant_tycoon_has_its_renderer(self) -> None:
        self.assertIsNotNone(ps.load_renderer_module("plant"), "src/pictures_plant.py ships with the Studio")
        self.studio.game_var.set("Plant Tycoon")
        self.root.update()
        self.assertNotEqual(self.studio.status_var.get(), ps.COMING)
        self.assertEqual([self.studio.notebook.tab(t, "text") for t in self.studio.notebook.tabs()],
                         ["From my save", "Make your own"])


PLANT_VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon"


@unittest.skipUnless((PLANT_VANILLA / "Images").is_dir(), "needs the vanilla Plant Tycoon's pictures (read only)")
class PlantWindowTests(unittest.TestCase):
    """Both games in one window: Plant Tycoon's subjects and its save list, from a synthetic save
    (tests/test_pictures_plant.py) and the vanilla game's pictures, read only."""

    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display for Tk")
        from test_pictures_plant import SaveReaderTests, synthetic_save
        self.tmp = tempfile.TemporaryDirectory()
        self.documents = Path(self.tmp.name) / "docs"
        folder = self.documents / "LDW" / "Plant Tycoon - Modded"
        folder.mkdir(parents=True)
        settings = bytearray(0x22 + 5 * 33)
        settings[:4] = b"ldwg"
        for i, name in enumerate(["Gardener", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER", "NEW PLAYER"]):
            settings[0x22 + i * 33:0x22 + i * 33 + len(name)] = name.encode("ascii")
        (folder / "Plant Tycoon0.ldw").write_bytes(bytes(settings))
        grow = SaveReaderTests.plant
        synthetic_save(folder, 1, {0: grow(None, 14, 13, "bloom"), 7: grow(None, 1, 3, "seedling")})
        ps._open_window = None
        self.studio = ps.open_window(self.root, "plant", settings={"show_spoilers": True}, save_settings=lambda: None,
                                     documents=self.documents, game_parents=[str(PLANT_VANILLA.parent)])
        self.studio.quiet = True
        self.root.update()

    def tearDown(self) -> None:
        if getattr(self, "studio", None) is not None:
            self.studio.close()
        if self.root is not None:
            self.root.destroy()
            self.tmp.cleanup()

    def test_subjects_save_list_and_pictures(self) -> None:
        studio = self.studio
        self.assertNotEqual(studio.status_var.get(), ps.COMING)
        titles = [s.title for s in studio.subjects]
        for title in ("Plant", "Unused parts", "Decorations", "Bugs", "Pots"):
            self.assertIn(title, titles)
        plant = {f.key for f in studio.subjects[titles.index("Plant")].fields}
        self.assertTrue({"flower", "foliage", "stage"} <= plant)
        stages = [o.label.casefold() for f in studio.subjects[titles.index("Plant")].fields if f.key == "stage"
                  for o in f.options]
        states = [o.key for f in studio.subjects[titles.index("Plant")].fields if f.key == "state" for o in f.options]
        self.assertEqual(states, ["alive", "dead"])
        self.assertTrue(any("budding" in s for s in stages))
        self.assertTrue(studio.items, "the save's plants are listed")
        tree = studio.save_tree
        self.assertTrue(any(tree.item(p, "text").startswith("Greenhouse") for p in tree.get_children()))
        node = next(iter(studio.item_nodes))
        tree.selection_set(node)
        self.root.update()
        self.assertIsNotNone(studio.shown.get("save"))
        for tab in range(len(studio.subjects)):
            studio.custom_notebook.select(tab)
            self.root.update()
            self.assertIn("custom", studio.shown, studio.subjects[tab].title)


class WiringTests(unittest.TestCase):
    def test_tools_tab_release_and_independence(self) -> None:
        tools = (ROOT / "src" / "tools_tab.py").read_text(encoding="utf-8")
        self.assertIn('"picture_studio": picture_studio.HELP', tools)
        self.assertIn("picture_studio.open_window(", tools)
        self.assertEqual(tools.count('"picture_studio"'), 4)
        release = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        for name in ("picture_image", "picture_studio", "pictures_fish", "pictures_fish_ds"):
            self.assertIn(f'"src/{name}.py"', release)
        source = (ROOT / "src" / "picture_studio.py").read_text(encoding="utf-8")
        # It reads none of the patcher window's settings (Enable All and the rest).
        for word in ("enable_all", "setting_vars", "Enable All", "app."):
            self.assertNotIn(word, source)
        for module in ("picture_image", "picture_studio", "pictures_fish"):
            text = (ROOT / "src" / f"{module}.py").read_text(encoding="utf-8")
            self.assertNotIn("import unicorn", text)
            self.assertNotIn("from PIL", text)
            self.assertNotIn("import PIL", text)


if __name__ == "__main__":
    unittest.main()
