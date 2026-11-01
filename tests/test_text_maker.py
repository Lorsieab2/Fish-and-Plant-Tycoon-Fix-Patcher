"""The Text Maker: its pictures match the games' own drawing pixel for pixel (the game's code run
in Unicorn), and its patcher-made letters, clusters and Unicode entry work."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from picture_image import Image  # noqa: E402
import text_maker as tm  # noqa: E402
import text_raster  # noqa: E402

try:
    import font_draw_emulator as fde
except ImportError:          # no Unicorn
    fde = None

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"

# Text each font really has (paddington lacks % * + < = > [ \ ] ^ _ { | } ~ and draws a box).
SAMPLES = {
    "paddington_tt_18": "Fish Tycoon: 123 $45! (Guppy)\nÄÖÜ äöü @ 'Angel' & \"Molly\"?",
    "paddington_tt_30": "Fish Tycoon 2: Magic!\nÄpfel Öl über",
    "font_triplex_sanslightlin_bold_16pt": "Hint: [Click] a fish {now} ~ 50% + 2 = 3\nÄÖÜ äöü <> | ^_",
    "PTfontsmall": "Plant Tycoon 1/2 ¿Qué? Ñandú ©® ½\nÀÉÎÕÜ àéîõü ß ÆØÅ æøå ÿ ~{}|",
}
COLOURS = (0xFFFFFFFF, 0xFFFFD040, 0xFF40D0FF, 0xFF40FF40, 0xFF000000, 0)


def rgb(colour: int) -> int:
    """The game's colour argument (0xAABBGGRR: SDL_MapRGBA gets its low byte as red) as 0xRRGGBB."""
    if colour == 0:
        return 0xFFFFFF                      # alpha 0: the default, white
    return ((colour & 0xFF) << 16) | (colour & 0xFF00) | ((colour >> 16) & 0xFF)


def vanilla(game: str) -> Path:
    return VANILLA / tm.GAME_TITLES[game]


def have(game: str) -> bool:
    return (vanilla(game) / tm.EXE_NAMES[game]).is_file()


class ClusterAndEntryTests(unittest.TestCase):
    def test_clusters_keep_letters_marks_and_emoji_whole(self) -> None:
        family = "\U0001F468‍\U0001F469‍\U0001F467"
        thumbs = "\U0001F44D\U0001F3FD"
        flag = "\U0001F1EB\U0001F1F7"
        text = f"éa{family}{thumbs}{flag}\r\nx❤️"
        self.assertEqual(tm.clusters(text), ["é", "a", family, thumbs, flag, "\r\n", "x", "❤️"])
        self.assertEqual(tm.clusters("\U0001F1EB\U0001F1F7\U0001F1E9"), [flag, "\U0001F1E9"])
        self.assertEqual(tm.clusters("𒀭𒂗"), ["𒀭", "𒂗"])

    def test_any_unicode_entry(self) -> None:
        self.assertEqual(tm.parse_unicode("U+00E9"), "é")
        self.assertEqual(tm.parse_unicode("1F41F"), "\U0001F41F")
        self.assertEqual(tm.parse_unicode("0x12000 u+3042"), "\U00012000あ")
        self.assertEqual(tm.parse_unicode("\\u00fc"), "ü")
        self.assertEqual(tm.parse_unicode("&#233; &#x1F33B;"), "é\U0001F33B")
        self.assertEqual(tm.parse_unicode("latin small letter g with breve"), "ğ")
        self.assertEqual(tm.parse_unicode("日本"), "日本")              # the characters themselves
        self.assertEqual(tm.parse_unicode("D800"), "D800")             # a lone surrogate is not a character
        self.assertEqual(tm.describe("é"), "U+00E9 LATIN SMALL LETTER E WITH ACUTE")

    def test_the_accent_picker_covers_the_languages(self) -> None:
        groups = dict(tm.ACCENTS)
        for group, letters in (("Turkish", "ğışİ"), ("French", "çéœ"), ("Polish", "ł"), ("Czech & Slovak", "ř")):
            for ch in letters:
                self.assertIn(ch, groups[group])


class EngineTests(unittest.TestCase):
    def test_relayout_moves_records_past_the_edge_down_a_row(self) -> None:
        records = [[65, 0, 0, 10, 20], [66, 10, 0, 30, 20], [67, 30, 0, 45, 20]]
        laid, height = tm.relayout(records, 40)
        self.assertEqual(height, 20)
        self.assertEqual(laid[:2], records[:2])
        self.assertEqual(laid[2], [67, 0, 21, 15, 41])       # x - 30, one row (height + 1) down

    def test_byte_index_first_record_wins_and_missing_bytes_draw_record_0(self) -> None:
        records = [[32, 0, 0, 4, 9], [95, 4, 0, 8, 9], [95, 8, 0, 12, 9], [-10, 12, 0, 16, 9]]
        index = tm.byte_index(records)
        self.assertEqual(index[95], 1)
        self.assertEqual(index[0xF6], 3)                     # a negative char is its low byte
        self.assertEqual(index[ord("[")], 0)

    def test_tint_is_the_games_and_of_each_channel(self) -> None:
        image = Image(2, 1, bytes((255, 200, 100, 128, 17, 34, 51, 255)))
        tinted = tm.tint(image, 0xFFD040)
        self.assertEqual(bytes(tinted.data), bytes((255 & 0xFF, 200 & 0xD0, 100 & 0x40, 128,
                                                    17 & 0xFF, 34 & 0xD0, 51 & 0x40, 255)))
        self.assertIs(tm.tint(image, 0xFFFFFF), image)

    def test_sdl_blend_is_sdls_two_channels_at_a_time(self) -> None:
        def reference(s, d, a):     # SDL's BlitRGBtoRGBPixelAlpha, 32-bit unsigned
            s1, d1 = s & 0xFF00FF, d & 0xFF00FF
            d1 = (d1 + ((((s1 - d1) % 2 ** 32) * a % 2 ** 32) >> 8)) & 0xFF00FF
            s2, d2 = s & 0xFF00, d & 0xFF00
            d2 = (d2 + ((((s2 - d2) % 2 ** 32) * a % 2 ** 32) >> 8)) & 0xFF00
            return d1 | d2
        for s, d, a in ((0xFFFFFF, 0x000000, 128), (0x102030, 0xF0E0D0, 77), (0x00FF00, 0xFF00FF, 200),
                        (0xFFD040, 0x183048, 1), (0x000000, 0xFFFFFF, 254)):
            dst = Image(1, 1, bytes(((d >> 16) & 255, (d >> 8) & 255, d & 255, 255)))
            src = Image(1, 1, bytes(((s >> 16) & 255, (s >> 8) & 255, s & 255, a)))
            tm.sdl_blend(dst, src, 0, 0)
            want = reference(s, d, a)
            self.assertEqual(tuple(dst.data[:3]), ((want >> 16) & 255, (want >> 8) & 255, want & 255))

    def test_an_empty_box_is_found_and_a_bar_is_not(self) -> None:
        sheet = Image(20, 10)
        for x in range(1, 8):
            for y in (1, 8):
                sheet.data[(y * 20 + x) * 4 + 3] = 255
        for y in range(1, 9):
            for x in (1, 7, 12, 13, 14):
                sheet.data[(y * 20 + x) * 4 + 3] = 255
        self.assertTrue(tm._is_box(sheet, [37, 0, 0, 9, 10]))
        self.assertFalse(tm._is_box(sheet, [73, 10, 0, 16, 10]))


@unittest.skipUnless(have("fish") and have("plant"), "needs the vanilla games")
class FontsTests(unittest.TestCase):
    def test_every_font_of_both_games(self) -> None:
        fish = tm.load_fonts("fish", vanilla("fish"))
        self.assertEqual([f.key for f in fish], ["paddington_tt_18", "paddington_tt_30",
                                                 "font_triplex_sanslightlin_bold_16pt"])
        self.assertEqual([(len(f.records), f.line_height) for f in fish], [(102, 20), (102, 29), (102, 23)])
        plant = tm.load_fonts("plant", vanilla("plant"))
        self.assertEqual([f.key for f in plant], ["PTfontsmall", "PTfontbig", "ldwarialbold"])
        self.assertEqual((len(plant[0].records), plant[0].line_height), (190, 21))
        self.assertEqual([f.in_game for f in plant], [True, False, False])
        # The fonts without a table: every letter of the picture found, in order.
        self.assertEqual(len(plant[1].records) + len(plant[1].extra), len(tm.FONTS["plant"][1].chars))
        self.assertEqual(len(plant[2].records) + len(plant[2].extra), len(tm.FONTS["plant"][2].chars))
        # paddington_tt_18 draws a box for the letters it lacks
        boxes = {chr(fish[0].records[i][0]) for i in fish[0].boxes}
        self.assertTrue(set("%*+<=>\\]^{|}~") <= boxes)
        self.assertFalse(fish[0].has_byte(ord("%")))
        self.assertTrue(fish[0].has_byte(ord("Ä")))
        self.assertFalse(fish[0].has_byte(ord("[")))          # no record at all: record 0 (space)

    def test_patcher_made_letters(self) -> None:
        font = tm.load_fonts("fish", vanilla("fish"))[0]
        made = dict(tm.generated_in(font, "é è ï Ğ ı ç [ 日 \U0001F41F"))
        self.assertIn("own e + the font's own acute", made["é"])      # its grave, mirrored
        self.assertIn("own e + the font's own grave", made["è"])
        self.assertIn("own i + the font's own diaeresis", made["ï"])
        self.assertIn("own G", made["Ğ"])
        self.assertIn("without its dot", made["ı"])
        self.assertIn("drawn by Windows", made["["])
        self.assertIn("Yu Gothic", made["日"])
        self.assertIn("colour emoji", made["\U0001F41F"])
        for cluster in made:
            glyph = tm.glyph_for(font, cluster)
            self.assertEqual(glyph.pixels.height, font.line_height)
            self.assertTrue(glyph.generated)
        self.assertNotIn("Ä", dict(tm.generated_in(font, "Ä")))       # its own letter
        # ü composed from the font's own pixels draws exactly its own ü would (the font has one)
        own = tm.glyph_for(font, "Ü")
        self.assertFalse(own.generated)
        # non-emoji patcher-made letters are white with the font's own alpha steps
        steps = set(font.sheet.data[3::4])
        for cluster in ("é", "Ğ", "日"):
            glyph = tm.glyph_for(font, cluster)
            self.assertEqual(set(glyph.pixels.data[0::4]) - {0}, {255})
            self.assertTrue(set(glyph.pixels.data[3::4]) <= steps | {0})

    def test_without_making_letters_it_draws_what_the_game_does(self) -> None:
        font = tm.load_fonts("fish", vanilla("fish"))[0]
        game = tm.glyph_for(font, "é", generate=False)          # byte 0xE9: no record: record 0
        self.assertEqual(game.rect, tuple(font.records[0][1:]))
        self.assertEqual(tm.glyph_for(font, "日", generate=False).rect, tuple(font.records[font.index[0x3F]][1:]))


@unittest.skipUnless(fde is not None and have("fish") and have("plant"), "needs Unicorn and the vanilla games")
class GameDrawTests(unittest.TestCase):
    """The game's own loader and draw in Unicorn, on the real pictures, against the Text Maker."""

    def check_font(self, game: str, font: tm.GameFont) -> None:
        emu = fde.FontDrawEmulator(game)
        handle = emu.load_font(font.key if game == "plant" else
                               {"font_triplex_sanslightlin_bold_16pt": "FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT"}.get(
                                   font.key, font.key), font.spec.table)
        text = SAMPLES[font.key]
        for colour in COLOURS:
            with self.subTest(font=font.key, colour=hex(colour)):
                emu.fill((24, 40, 72))
                emu.blits = []
                emu.draw(handle, text.encode("latin-1"), 5, 7, colour)
                self.assertTrue(emu.blits)
                # The game's blits: its own glyph rectangles and places, tinted by its own code
                placed, width, height = tm.layout(font, text)
                self.assertEqual([(b.src, b.x, b.y) for b in emu.blits],
                                 [((p.glyph.rect[0], p.glyph.rect[1], p.glyph.pixels.width,
                                    p.glyph.pixels.height), 5 + p.x, 7 + p.y) for p in placed])
                self.assertTrue(all(b.tinted == ((colour & 0xFFFFFF) != 0xFFFFFF and colour != 0)
                                    for b in emu.blits))
                # The Text Maker's picture is the game's screen, pixel for pixel
                drawn = tm.render(font, text, rgb(colour),
                                  background=(24, 40, 72), margin=0)
                self.assertEqual((drawn.width, drawn.height), (width, height))
                self.assertEqual(emu.screen_image.sub(5, 7, width, height).data, drawn.data)
                # ... and so is the byte-level draw
                screen = Image(emu.screen_image.width, emu.screen_image.height)
                screen.data[:] = bytes((24, 40, 72, 255)) * (screen.width * screen.height)
                tm.render_game_bytes(font, text.encode("latin-1"), rgb(colour),
                                     screen, 5, 7)
                self.assertEqual(screen.data, emu.screen_image.data)

    def test_fish_fonts(self) -> None:
        for font in tm.load_fonts("fish", vanilla("fish")):
            self.check_font("fish", font)

    def test_plant_font(self) -> None:
        self.check_font("plant", tm.load_fonts("plant", vanilla("plant"))[0])

    def test_game_tinted_pixels_are_the_text_makers(self) -> None:
        """The game's own colour copy of the picture (0x402730) is the Text Maker's tint."""
        font = tm.load_fonts("fish", vanilla("fish"))[0]
        emu = fde.FontDrawEmulator("fish")
        handle = emu.load_font("paddington_tt_18", font.spec.table)
        emu.draw(handle, b"A", 0, 0, 0xFFFFD040)
        tinted = [s for s in emu.surfaces if s not in emu.sheet_surfaces and s != emu.screen]
        self.assertEqual(len(tinted), 1)
        self.assertEqual(emu.surface_image(tinted[0]).data, tm.tint(font.sheet, 0x40D0FF).data)


@unittest.skipUnless(text_raster.available(), "needs Direct2D")
class WindowsDrawingTests(unittest.TestCase):
    def test_raster_shapes_joined_emoji_as_one(self) -> None:
        family = "\U0001F468‍\U0001F469‍\U0001F467"
        one = text_raster.raster(family, "Segoe UI Emoji", 40)
        parts = text_raster.raster(family.replace("‍", ""), "Segoe UI Emoji", 40)
        self.assertLess(one.advance, parts.advance * 0.6)
        self.assertGreater(one.baseline, 0)


@unittest.skipUnless(have("fish"), "needs the vanilla game")
class WindowTests(unittest.TestCase):
    def test_window_opens_draws_and_exports(self) -> None:
        import tempfile
        import tkinter as tk
        import text_maker_window
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        root.withdraw()
        try:
            win = text_maker_window.open_window(root, "fish", {"fish": ["", str(vanilla("fish"))], "plant": []})
            win.text.delete("1.0", "end")
            win.text.insert("1.0", "Café 日本")
            win._draw()
            self.assertIn("3 patcher-made", win.status.get())
            self.assertEqual(len(win.made.get_children()), 3)          # é 日 本
            picture = win.picture(True)
            self.assertEqual(picture.pixel(0, 0)[3], 0)                 # transparent
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "out.png"
                path.write_bytes(picture.to_png())
                self.assertEqual(Image.from_png(path.read_bytes()), picture)
            win.game_var.set("Plant Tycoon")
            win._load_game()
            self.assertIn("No copy of Plant Tycoon", win.folder_text.get())
        finally:
            root.destroy()


class WiringTests(unittest.TestCase):
    def test_tools_tab_and_release(self) -> None:
        tools = (ROOT / "src" / "tools_tab.py").read_text(encoding="utf-8")
        self.assertIn('"text_maker": text_maker_window.HELP', tools)
        self.assertEqual(tools.count('"text_maker"'), 4)
        self.assertIn("text_maker_window.open_window(", tools)
        release = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")
        for name in ("text_maker", "text_maker_window", "text_raster"):
            self.assertIn(f'"src/{name}.py"', release)
        for name in ("text_maker", "text_maker_window", "text_raster"):
            source = (ROOT / "src" / f"{name}.py").read_text(encoding="utf-8")
            for word in ("import numpy", "from PIL", "import PIL"):     # the patcher ships neither
                self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
