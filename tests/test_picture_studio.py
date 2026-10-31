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
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import picture_image as pi  # noqa: E402
import picture_studio as ps  # noqa: E402
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
        self.assertEqual(len(self.studio.custom_boxes["fish"]["body"]["box"].cget("values")), 21)
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

    def test_plant_tycoon_without_its_renderer_says_so(self) -> None:
        if ps.load_renderer_module("plant") is not None:
            self.skipTest("the Plant Tycoon renderer is in this build")
        self.studio.game_var.set("Plant Tycoon")
        self.root.update()
        self.assertEqual(self.studio.status_var.get(), ps.COMING)


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
