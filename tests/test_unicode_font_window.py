"""The Tools tab's "Unicode Font..." window (src/unicode_font_window.py) and its File= key.

* The patch writes the chosen font file's name as File= in Unicode Text.ini beside Font=, and copies
  the file beside Unicode Text.dll (which loads it for the game only: native/common/unicode_config.h);
  a missing or non-font file is left out. All three command lines take --unicode-font-file.
* Save keeps the choice in the patcher's settings and updates a modded copy's Unicode Text.ini
  (Font=, File=), every other line kept.
* The previews (Windows only) draw each game font as Use Unicode Font will: its line height, the em
  fitted to the fox sentence within 60%..130%.
* The Tools tab offers "Unicode Font..." and "Game Text..."; the Game Text window shows text "As
  Render Unicode with In-Game Fonts draws it", "As the stock game shows it" and "As Use Unicode Font
  draws it", and labels every character (game), (patcher-made), (drawn by Windows: face) or (missing).
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fish_patcher  # noqa: E402

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"


def manifest(game: str) -> dict:
    import tycoon_fix_patcher as combined
    return combined.load_manifest(game)


class FontFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.font = self.dir / "My Font=Bold.ttf"
        self.font.write_bytes(b"\x00\x01\x00\x00fake font")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_ini_names_the_file_and_the_patch_copies_it(self) -> None:
        for game, folder in (("fish", "Fish Tycoon Fix Patcher DLLs"), ("plant", "Plant Tycoon Fix Patcher DLLs")):
            with self.subTest(game=game):
                m = manifest(game)
                dest, data = fish_patcher.unicode_ini(m, {"unicode_system_font"}, "My Font", self.font)
                self.assertIn(b"Font=My Font\r\n", data)
                self.assertIn(b"File=My Font Bold.ttf\r\n", data)
                staging = self.dir / f"stage_{game}"
                done = fish_patcher.install_unicode_ini(m, {"unicode_system_font"}, staging, "My Font", self.font)
                self.assertEqual((staging / folder / "My Font Bold.ttf").read_bytes(), self.font.read_bytes())
                self.assertIn(f"{folder}/My Font Bold.ttf", [d["path"] for d in done])
                # no file, a missing file or not a font file: Font= alone
                for other in (None, self.dir / "gone.ttf", self.dir / "notes.txt"):
                    _dest, data = fish_patcher.unicode_ini(m, {"unicode_system_font"}, "My Font", other)
                    self.assertNotIn(b"File=", data)

    def test_the_command_lines_take_the_file(self) -> None:
        import plant_patcher
        import tycoon_fix_patcher as combined
        args = combined._parser().parse_args(["--game", "fish", "--vanilla-dir", "x", "--unicode-font-file", "a.ttf"])
        self.assertEqual(args.unicode_font_file, "a.ttf")
        ns = combined._namespace("fish", "x", "y", [], True, "Arial", "a.ttf")
        self.assertEqual((ns.unicode_font, ns.unicode_font_file), ("Arial", "a.ttf"))
        for module in (fish_patcher, plant_patcher):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertIn('"--unicode-font-file"', source)
            self.assertIn('getattr(args, "unicode_font_file", None)', source)

    def test_save_updates_a_modded_copy(self) -> None:
        import unicode_font_window as w
        folder = self.dir / "Fish Tycoon - Modded Upgrades" / "Fish Tycoon Fix Patcher DLLs"
        folder.mkdir(parents=True)
        (folder / "Unicode Text.ini").write_bytes(b"; Written by the patcher\r\n[Unicode Text]\r\nMode=system\r\n"
                                                  b"Font=Segoe UI\r\nPaste=1\r\n")
        ini = w.apply_to_copy(folder.parent, "fish", "My Font", self.font)
        self.assertEqual(ini.read_bytes(), b"; Written by the patcher\r\n[Unicode Text]\r\nMode=system\r\n"
                                           b"Font=My Font\r\nPaste=1\r\nFile=My Font Bold.ttf\r\n")
        self.assertTrue((folder / "My Font Bold.ttf").is_file())
        # back to an installed family: File= goes
        w.apply_to_copy(folder.parent, "fish", "Arial", None)
        self.assertEqual(ini.read_bytes(), b"; Written by the patcher\r\n[Unicode Text]\r\nMode=system\r\n"
                                           b"Font=Arial\r\nPaste=1\r\n")
        # a copy without the setting is left alone
        self.assertIsNone(w.apply_to_copy(self.dir / "elsewhere", "plant", "Arial", None))

    def test_search(self) -> None:
        import unicode_font_window as w
        faces = ["Segoe UI", "Segoe UI Emoji", "Arial", "Yu Gothic UI"]
        self.assertEqual(w.matching(faces, "segoe emo"), ["Segoe UI Emoji"])
        self.assertEqual(w.matching(faces, ""), faces)


class ToolsTabTests(unittest.TestCase):
    def test_the_entries(self) -> None:
        source = (ROOT / "src" / "tools_tab.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('("Unicode Font...", "unicode_font"'), 2)
        self.assertEqual(source.count('("Game Text...", "text_maker"'), 2)
        self.assertNotIn('"Text Maker..."', source)
        gui = (ROOT / "src" / "tycoon_fix_patcher_gui.py").read_text(encoding="utf-8")
        self.assertIn('"unicode_font_file": chosen_unicode_font_file(self)', gui)


def _fonts_ready() -> bool:
    if os.name != "nt":
        return False
    try:
        import text_raster
        return text_raster.available() and (VANILLA / "Fish Tycoon" / "Fish Tycoon.exe").is_file()
    except Exception:
        return False


@unittest.skipUnless(_fonts_ready(), "needs Windows' font drawing and the vanilla games")
class PreviewTests(unittest.TestCase):
    def test_previews_keep_each_fonts_line_and_fit_the_em(self) -> None:
        import text_maker as tm
        import unicode_font_window as w
        for game, folder in (("fish", "Fish Tycoon"), ("plant", "Plant Tycoon")):
            fonts = [f for f in tm.load_fonts(game, VANILLA / folder) if f.in_game]
            rows = w.preview_rows(fonts, "Arial", None, "The Smith Family Zoë")
            self.assertEqual(len(rows), len(fonts))
            for font, (_label, own, unicode) in zip(fonts, rows):
                with self.subTest(font=font.key):
                    self.assertEqual(unicode.height, font.line_height)
                    self.assertGreater(unicode.width, 20)
                    em0 = tm.unicode_style(font)["em"]
                    em = tm.fit_unicode_em(font, "Arial")
                    self.assertTrue(em0 * 6 // 10 <= em <= em0 * 13 // 10)
                    # the alpha steps are the font's own
                    self.assertTrue(set(unicode.data[3::4]) <= set(font.quantise) | {0})


@unittest.skipUnless(_fonts_ready(), "needs Windows' font drawing and the vanilla games")
class GameTextTests(unittest.TestCase):
    def test_labels(self) -> None:
        import text_maker as tm
        font = tm.load_fonts("fish", VANILLA / "Fish Tycoon")[0]
        self.assertEqual(tm.source_label(font, "A"), "(game)")
        self.assertEqual(tm.source_label(font, "é"), "(patcher-made)")
        self.assertEqual(tm.source_label(font, "中"), "(drawn by Windows: Yu Gothic)")
        self.assertEqual(tm.source_label(font, "🐟"), "(drawn by Windows: Segoe UI Emoji)")
        self.assertEqual(tm.source_label(font, "\u200d"), "")
        rows = tm.characters_in(font, "Aé中A")
        self.assertEqual([(c, label) for c, label, _how in rows],
                         [("A", "(game)"), ("é", "(patcher-made)"), ("中", "(drawn by Windows: Yu Gothic)")])
        glyph = tm._missing_box(font, "x")
        self.assertTrue(glyph.source.startswith("no font on this PC"))

    def test_the_three_ways_to_show(self) -> None:
        import tkinter as tk
        import text_maker_window as w
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        root.withdraw()
        try:
            root.unicode_font = tk.StringVar(master=root, value="Arial")
            win = w.open_window(root, "fish", {"fish": [str(VANILLA / "Fish Tycoon")], "plant": []})
            self.assertEqual(win.window.title(), "Game Text")
            widths = {}
            for mode in w.SHOW_MODES:
                win.show_var.set(mode)
                win._show_chosen()
                win._draw()
                widths[mode] = win.picture(True).width
            self.assertEqual(set(widths), {"As Render Unicode with In-Game Fonts draws it", "As the stock game shows it",
                                           "As Use Unicode Font draws it"})
            self.assertEqual(len(set(widths.values())), 3)          # three different drawings
            win.window.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
