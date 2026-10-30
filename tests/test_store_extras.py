"""Free upgrades and the Add Money cheat ($1,000), both games.

Both settings live on the store's Upgrades screen (DS Store Items in Fish
Tycoon, Add new store upgrades and items in Plant Tycoon), which they turn on,
as Time Warp does; each ships one ".ini" file beside the store DLL. The
emulation tests run the store DLL's own code against the vanilla executable
in Unicorn (tests/store_emulator.py): prices, purchases, the money cap.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

NEW = ("free_upgrades", "add_money")
SCREEN = {"fish": "ds_store", "plant": "plant_upgrades"}
FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None


class ManifestTests(unittest.TestCase):
    def test_off_by_default_and_need_the_upgrades_screen(self) -> None:
        for game, screen in SCREEN.items():
            settings = combined.patch_settings(game)
            for setting_id in NEW:
                setting = settings[setting_id]
                self.assertFalse(setting["default"], (game, setting_id))
                self.assertEqual(setting["requires_settings"], [screen], (game, setting_id))
                self.assertIn("which this setting turns on", setting["description"])
            self.assertEqual(settings["add_money"]["name"], "Add Money cheat ($1,000)")
            self.assertEqual(settings["free_upgrades"]["name"], "Free upgrades")
            for text in ("$950", "+$1,000", "$0 with Free upgrades", "maximum"):
                self.assertIn(text, settings["add_money"]["description"] + settings["add_money"]["summary"])

    def test_needs_its_screen_from_the_command_line(self) -> None:
        for game, screen in SCREEN.items():
            manifest = combined.load_manifest(game)
            for setting_id in NEW:
                with self.assertRaisesRegex(fish_patcher.PatchError, "needs"):
                    fish_patcher.check_setting_requirements(manifest, {setting_id})

    def test_each_ships_only_its_ini_beside_the_store_dll(self) -> None:
        folders = {"fish": "Fish Tycoon Fix Patcher DLLs", "plant": "Plant Tycoon Fix Patcher DLLs"}
        files = {"free_upgrades": "Free Upgrades.ini", "add_money": "Add Money.ini"}
        for game in SCREEN:
            settings = combined.patch_settings(game)
            for setting_id, name in files.items():
                companion = settings[setting_id]["companion"]
                self.assertEqual([f["destination"] for f in companion["files"]], [f"{folders[game]}/{name}"])
                for entry in companion["files"]:
                    data = (ROOT / companion["source"] / entry["path"]).read_bytes()
                    self.assertEqual(len(data), entry["size"])
                    self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"])

    def test_every_combination_is_pinned_as_the_same_one_without_them(self) -> None:
        # Neither writes executable bytes: each pin equals the pin without them.
        for game, screen in SCREEN.items():
            pins = combined.load_manifest(game)["patched_sha256_by_settings"]
            with_new = [k for k in pins if set(NEW) & set(k.split(","))]
            self.assertTrue(with_new)
            bases = [k for k in pins if screen in k.split(",") and not set(NEW) & set(k.split(","))]
            self.assertEqual(len(with_new), 3 * len(bases), game)
            for key in with_new:
                enabled = set(key.split(","))
                self.assertIn(screen, enabled)
                self.assertEqual(pins[key], pins[",".join(sorted(enabled - set(NEW)))], key)

    def test_the_coins_are_pinned_with_the_upgrades_art(self) -> None:
        store = combined.patch_settings("fish")["ds_store"]["companion"]
        self.assertIn("Images/ITEM_ADD_MONEY.png", {f["destination"] for f in store["files"]})
        def png_size(path: Path) -> tuple[int, int]:
            data = path.read_bytes()
            self.assertEqual(data[12:16], b"IHDR")
            return struct.unpack(">II", data[16:24])
        icon = ROOT / "assets" / "fish_tycoon_ds_store" / "Images" / "ITEM_ADD_MONEY.png"
        self.assertEqual(png_size(icon), (74, 60))     # the DLL's icon_w / icon_h for the item
        sheet = ROOT / "assets" / "plant_tycoon_upgrades" / "Images" / "Chemicals_Grid_upgrades.png"
        self.assertEqual(png_size(sheet), (140, 18 * 70))   # row 14: the coins, 15: the Extra Greenhouse, 16-17 the Auto items (chem_rows = 18)
        self.assertEqual(png_size(ROOT / "assets" / "money_cheat" / "coins_source.png"), (195, 159))


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


# The games' own bitmap fonts. A character a font lacks is drawn as a box (the owner's "□$1,000" on
# Fish Tycoon's item title): every string the store DLLs draw in the game must use only drawable ones.

def _glyph_table(exe: bytes, address: int) -> dict[int, tuple[int, int, int, int]]:
    """A font's glyphs: {char, x0, y0, x1, y1} int records, char signed (0xE4 is -28), ended by 0."""
    base, _size, sections, _imports = E.pe_image(exe)
    at = next(raw + address - base - rva for rva, raw, size in sections if 0 <= address - base - rva < size)
    table = {}
    while True:
        char, x0, y0, x1, y1 = struct.unpack_from("<5i", exe, at)
        if char == 0:
            return table
        table[char & 0xFF] = (x0, y0, x1, y1)
        at += 20


def _drawable(sheet, table: dict) -> set[str]:
    """The characters whose glyph is not the "missing" box (a hollow rectangle)."""
    import numpy as np
    alpha = np.asarray(sheet)[..., 3] > 128

    def box(x0: int, y0: int, x1: int, y1: int) -> bool:
        ink = alpha[y0:y1, x0:x1]
        ys, xs = np.nonzero(ink)
        if len(xs) == 0:
            return False
        ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        if ink.shape[0] < 6 or ink.shape[1] < 4:
            return False
        edge = np.concatenate([ink[0], ink[-1], ink[:, 0], ink[:, -1]]).mean()
        return edge > 0.9 and ink[2:-2, 2:-2].mean() < 0.1
    return {chr(c) for c, rect in table.items() if not box(*rect)} | {" ", "\n"}


def fish_fonts() -> dict[str, set[str]]:
    """The three fonts the game loads (0x4180B0): paddington_tt_18, paddington_tt_30 (the store's item
    title, font 1 at 0x42719F) and font_triplex_sanslightlin_bold_16pt."""
    import io
    import zipfile
    from PIL import Image
    exe = FISH_EXE.read_bytes()
    fonts = {}
    with zipfile.ZipFile(FISH_EXE.parent / "Assets" / "ft.dat") as archive:
        for name, table in (("paddington_tt_18", 0x458580), ("paddington_tt_30", 0x458DC8),
                            ("font_triplex_sanslightlin_bold_16pt", 0x4544B8)):
            sheet = Image.open(io.BytesIO(archive.read(name + ".png"))).convert("RGBA")
            fonts[name] = _drawable(sheet, _glyph_table(exe, table))
    return fonts


def plant_font() -> set[str]:
    """PTfontsmall, the only font the game loads (0x412D9F)."""
    from PIL import Image
    sheet = Image.open(PLANT_EXE.parent / "Images" / "PTfontsmall.png").convert("RGBA")
    return _drawable(sheet, _glyph_table(PLANT_EXE.read_bytes(), 0x47A550))


# ------------------------------------------------------------------ Fish Tycoon

S_MONEY, S_SPENT, S_EGG_COUNT = 0x38C, 0x24, 0x314
ANIMAL_RECORD = 0x390 + 26 * 0x288          # Tank 1's first animal slot
FISH_CELLS = {"puffer": (80, 110), "ray": (180, 130), "eel": (270, 130),"eggs": (350, 130), "warp": (450, 130), "money": (540, 130),
              "hormone": (630, 125), "revival": (725, 125), "clonafish": (86, 200)}


@_needs(FISH_EXE)
class FishStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_ds_store", ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def store(self, money: int, free: bool, add_money: bool = True, warp: bool = True, answer_yes: bool = True):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        emu.hook_printf()
        for name, pop in (("MessageBoxW", 16), ("GetActiveWindow", 0), ("GetForegroundWindow", 0),
                          ("GetModuleHandleW", 4), ("GetTickCount", 0)):
            emu.hook_import(name, emu.record(name, 6 if name == "MessageBoxW" else 0, args=4), pop)
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)                       # HINT
        emu.hook(0x004221A0, emu.record("dialog", args=1), 8)                     # DIALOG_INIT(string id, 1)
        emu.hook(0x00401D00, emu.record("run", 0 if answer_yes else 1), 8)        # DIALOG_RUN: 0 = Yes
        emu.hook(0x00422440, emu.record("free"), 0)
        emu.hook(0x00425120, emu.record("sounds"), 0)
        emu.hook(0x004251A0, emu.record("sound"), 4)                              # no sound object: none played
        table, price = emu.alloc(16), emu.text("Price:")
        emu.hook(0x00427060, lambda e: table, 0)
        emu.hook(0x00427050, lambda e: price, 4)
        emu.hook(0x0041BE70, lambda e: 1, 4)                                       # SPRITE_GET
        emu.hook(0x00408A40, emu.record("draw"), 12)
        emu.hook(0x00408AE0, emu.record("draw"), 24)
        emu.hook(0x00408B80, lambda e: (e.calls.append(("text", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 20)
        state, impl, scene = emu.alloc(0x40000), emu.alloc(0x100), emu.alloc(0x100)
        emu.write32(scene + 8, impl)
        emu.write32(impl + 0x10, state)
        emu.write32(impl + 0x0C, emu.alloc(0x40))
        emu.write32(state + S_MONEY, money)
        for name, on in (("_free_on", free), ("_money_on", add_money), ("_warp_on", warp), ("_page_upgrades", 1)):
            emu.write32(emu.sym(name), int(on))
        emu.state, emu.scene = state, scene
        return emu

    def select(self, emu, item: str) -> None:
        x, y = FISH_CELLS[item]
        emu.call(emu.sym("@on_mouse@20"), 3, x, y, ecx=emu.scene)

    def buy(self, emu, item: str) -> None:
        self.select(emu, item)
        emu.call(emu.sym("_buy"), emu.scene)

    def money(self, emu) -> int:
        return emu.read32(emu.state + S_MONEY, signed=True)

    def shown_price(self, emu, item: str) -> str:
        self.select(emu, item)
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        return [c[1] for c in emu.calls if c[0] == "text" and c[1].startswith("Price:")][-1]

    def test_every_item_shows_its_price_or_zero(self) -> None:
        for item, normal in (("puffer", 1250), ("eggs", 2300), ("warp", 500), ("money", 950), ("hormone", 10000)):
            self.assertEqual(self.shown_price(self.store(0, free=False), item), f"Price:  ${normal}")
            self.assertEqual(self.shown_price(self.store(0, free=True), item), "Price:  $0")
        for animal in ("ray", "eel"):
            self.assertEqual(self.shown_price(self.store(0, free=False), animal), "Price:  $1250")
            self.assertEqual(self.shown_price(self.store(0, free=True), animal), "Price:  $0")

    def test_eggs_bought_free_take_no_money_and_still_fill_the_slot(self) -> None:
        emu = self.store(0, free=True)
        self.buy(emu, "eggs")
        self.assertEqual(self.money(emu), 0)
        self.assertEqual(emu.read32(emu.state + S_SPENT), 0)
        self.assertEqual(emu.read32(emu.state + S_EGG_COUNT), 3)
        emu = self.store(2300, free=False)
        self.buy(emu, "eggs")
        self.assertEqual(self.money(emu), 0)
        self.assertEqual(emu.read32(emu.state + S_SPENT), 2300)
        self.assertEqual(emu.read32(emu.state + S_EGG_COUNT), 3)

    def test_animals_are_affordable_free_and_still_confirmed(self) -> None:
        emu = self.store(0, free=False)
        self.buy(emu, "puffer")
        self.assertIn(("hint", (2,)), emu.calls)                   # "You can't afford to buy this yet!"
        emu = self.store(0, free=True, answer_yes=False)
        self.buy(emu, "puffer")
        self.assertNotIn(("hint", (2,)), emu.calls)
        self.assertIn(("dialog", (0xEC,)), emu.calls)              # the stock purchase question, answered No
        self.assertEqual(self.money(emu), 0)

    def test_time_warp_is_free(self) -> None:
        emu = self.store(0, free=False)
        self.buy(emu, "warp")
        self.assertIn(("hint", (2,)), emu.calls)
        emu = self.store(0, free=True)
        self.buy(emu, "warp")                                     # past the price: no tank opened yet
        self.assertNotIn(("hint", (2,)), emu.calls)
        self.assertTrue(any(c[0] == "MessageBoxW" for c in emu.calls))
        self.assertEqual(self.money(emu), 0)

    def test_add_money_costs_950_and_adds_1000_every_time(self) -> None:
        emu = self.store(1000, free=False)
        for expected in (1050, 1100, 1150):
            self.buy(emu, "money")
            self.assertEqual(self.money(emu), expected)
        self.assertEqual(emu.read32(emu.state + S_SPENT), 3 * 950)

    def test_add_money_refused_below_950(self) -> None:
        emu = self.store(949, free=False)
        self.buy(emu, "money")
        self.assertEqual(self.money(emu), 949)
        self.assertIn(("hint", (2,)), emu.calls)

    def test_add_money_free_adds_1000(self) -> None:
        emu = self.store(0, free=True)
        self.buy(emu, "money")
        self.buy(emu, "money")
        self.assertEqual(self.money(emu), 2000)
        self.assertEqual(emu.read32(emu.state + S_SPENT), 0)

    def test_add_money_stops_at_the_signed_32_bit_maximum(self) -> None:
        emu = self.store(0x7FFFFFFF - 10, free=True)
        self.buy(emu, "money")
        self.assertEqual(self.money(emu), 0x7FFFFFFF)
        self.buy(emu, "money")
        self.assertEqual(self.money(emu), 0x7FFFFFFF)
        emu = self.store(0x7FFFFFFF - 10, free=False)
        self.buy(emu, "money")
        self.assertEqual(self.money(emu), 0x7FFFFFFF)

    def test_add_money_answered_no_changes_nothing(self) -> None:
        emu = self.store(5000, free=False, answer_yes=False)
        self.buy(emu, "money")
        self.assertEqual(self.money(emu), 5000)

    def test_items_hidden_without_their_settings(self) -> None:
        emu = self.store(5000, free=False, add_money=False, warp=False)
        self.select(emu, "money")
        self.assertEqual(emu.read32(emu.sym("_selected"), signed=True), -1)
        self.select(emu, "warp")
        self.assertEqual(emu.read32(emu.sym("_selected"), signed=True), -1)

    def test_drawn_strings_fit_the_game_fonts(self) -> None:
        fonts = fish_fonts()
        self.assertNotIn("+", fonts["paddington_tt_30"])           # why "+$1,000" showed a box
        self.assertIn("+", fonts["font_triplex_sanslightlin_bold_16pt"])
        self.assertLessEqual(set("$,.:!()-09AZaz\xC4\xD6\xDC\xE4\xF6\xFC"), fonts["paddington_tt_30"])
        allowed = set.intersection(*fonts.values())                # title or text: fits all three
        drawn = set()
        for lang in (0, 1):
            for free in (False, True):
                for item in FISH_CELLS:
                    emu = self.store(5000, free=free)
                    language = emu.alloc(4)
                    emu.write32(language, lang)
                    emu.write32(0x0045B314, language)
                    self.select(emu, item)
                    emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
                    drawn |= {c[1] for c in emu.calls if c[0] == "text"}
        self.assertLessEqual({"Add $1,000", "Plus 1.000 $", "Time Warp", "Zeitsprung", "Price:  $0",
                              "Radioactive Growth Hormone", "Radioaktive Wachstumshormone",
                              "Revival Potion", "Wiederbelebungstrank", "ClonaFish", "Price:  $10000", "Price:  $2500",
                              "A wonder drug that instantly clones all\nfish in the tank. Make sure there's\n"
                              "enough space in the tank!\nContains 3 doses.",
                              "This magical potion instantly revives\ndead fish and restores them to full\n"
                              "health. Contains 3 doses."}, drawn)
        for text in drawn:
            self.assertLessEqual(set(text), allowed, text)

    # --- the store animals' meters: full when bought, filled when a save loads
    def buy_animal(self, item: str):
        emu = self.store(5000, free=False)
        emu.hook(0x004160A0, lambda e: e.alloc(0x100), 0)                      # the sprite helper
        emu.hook(0x00415390, emu.record("sprites"), 12)
        emu.hook(0x004032C0, lambda e: 1234, 0)                                # the state's clock
        emu.hook(0x00419C00, emu.record("rock", args=2), 8)                    # the eel's rock, added
        self.buy(emu, item)
        return emu

    def test_bought_animals_have_full_health_and_food(self) -> None:
        for item, fin in (("puffer", 30), ("ray", 31), ("eel", 32)):
            emu = self.buy_animal(item)
            rec = emu.call(emu.sym("_animal"), emu.state, 0, 0)        # Tank One's first animal record
            self.assertEqual((emu.read32(rec + 0x4C), emu.read32(rec + 0x50)), (22, fin), item)
            self.assertEqual((emu.read32(rec + 0x3C), emu.read32(rec + 0x44)), (100, 100), item)
            self.assertEqual(self.money(emu), 5000 - 1250, item)

    def load_save(self, body: bytes) -> tuple[bytes, list[bytes]]:
        """The DLL's Load (the vtable slot at 0x4424D0): the game's own load, then the animals.
        The state, and the 15 animal records (3 tanks x 5)."""
        from test_ds_store_animals import Files
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        emu.files = Files(emu)
        emu.hook_fish_save_read(body)
        state = emu.alloc(0x1E3C8 + 0x1000)
        self.assertEqual(emu.call(emu.sym("@on_state_load@12"), 1, ecx=state) & 0xFF, 1)
        animals = [bytes(emu.uc.mem_read(emu.call(emu.sym("_animal"), state, t, k), 0x288))
                   for t in range(3) for k in range(5)]
        return bytes(emu.uc.mem_read(state, 0x1E3C8 + 8)), animals

    @staticmethod
    def put(body: bytearray, tank: int, slot: int, fin: int, health: int, food: int, kind: int = 22) -> int:
        """A live record in a save's body (the state from +8); animals carry the "FTCA" mark."""
        at = 0x390 + tank * 0x51EC + slot * 0x288 - 8
        struct.pack_into("<I", body, at, 99)
        mark = (struct.unpack("<I", b"FTCA")[0], fin) if kind == 22 else (0, 0)
        struct.pack_into("<II", body, at + 0x14, *mark)
        struct.pack_into("<i", body, at + 0x3C, health)
        struct.pack_into("<i", body, at + 0x40, 0)
        struct.pack_into("<i", body, at + 0x44, food)
        struct.pack_into("<ii", body, at + 0x4C, kind, fin)
        return at

    def test_loading_a_save_fills_the_animals_and_nothing_else(self) -> None:
        """A save from the build that kept the animals in fish records 26-30: they move to their own
        records (filled to 100/100; the Golden Seahorse is Fix Vanilla Bugs' job), those fish records are
        cleared, and nothing else in the state changes but the eel's meters in its rock."""
        body = bytearray(0x1E3C8)
        for i in range(0, 0x390 - 8):                               # the state's other fields: a pattern
            body[i] = (i * 7 + 3) & 0xFF
        moved = [self.put(body, 0, 26, 30, 50, 20),                 # a half-fed Puffer Fish
                 self.put(body, 1, 27, 31, 60, 100),                # a Sting Ray
                 self.put(body, 2, 28, 22, 40, 10)]                 # the Golden Seahorse
        self.put(body, 0, 4, 4, 40, 20, kind=3)                     # a fish
        rock = 0x5208 + 2 * 0x51EC + 0x2C - 8                       # the selling tank's second ornament
        body[rock:rock + 4] = bytes([1, 70, 30, 0xE1])              # the eel at home: health 70, food 30
        struct.pack_into("<i", body, rock + 0x24, 229)
        state, animals = self.load_save(bytes(body))
        expected = bytearray(body)
        for at in moved:                                            # REMOVE_FISH's fields, and the mark
            for field in (0x00, 0x04, 0x08, 0x0C, 0x3C, 0x40, 0x44, 0x4C, 0x50, *range(0x10, 0x3C, 4),
                          0x78, 0x7C, 0x80):
                struct.pack_into("<i", expected, at + field, 0)
        expected[rock + 1:rock + 3] = bytes([100, 100])
        self.assertEqual(state[8:], bytes(expected))
        meters = {struct.unpack_from("<i", a, 0x50)[0]: struct.unpack_from("<iii", a, 0x3C)
                  for a in animals if struct.unpack_from("<I", a, 0)[0]}
        self.assertEqual(meters, {30: (100, 0, 100), 31: (100, 0, 100), 22: (40, 0, 10)})

    def test_loading_a_save_with_full_animals_changes_nothing_but_their_place(self) -> None:
        body = bytearray(0x1E3C8)
        at = self.put(body, 0, 26, 32, 100, 100)
        record = bytes(body[at:at + 0x288])
        state, animals = self.load_save(bytes(body))
        self.assertEqual(animals[0], record)
        self.assertEqual(struct.unpack_from("<I", state, at + 8)[0], 0)

    # --- Time Warp's "done" message
    def warp(self, money: int, free: bool, hours: int = 12, speed: int = 10, answer_yes: bool = True):
        """Buy the Time Warp with a tank open: the popup answers `hours`, the question Yes/No."""
        emu = self.store(money, free)
        emu.write32(emu.state + 0x1E168, speed)
        emu.write32(emu.sym("_tank_scene"), emu.alloc(0x40))

        def message(e):
            e.calls.append(("message", e.wstring(e.arg(1)), self.money(e), updates(e)))
            return 6 if answer_yes else 7                                         # IDYES / IDNO
        def updates(e):
            return sum(1 for c in e.calls if c[0] == "update")
        def ask_hours(e):
            e.write32(e.arg(4) + 4, hours)                                        # tw_dialog_data.hours
            return 1
        emu.hook_import("MessageBoxW", message, 16)
        emu.hook_import("DialogBoxIndirectParamW", ask_hours, 20)
        emu.hook(0x0041FE70, lambda e: (e.calls.append(("update", self.money(e))), 0)[1], 0)   # the fish update
        self.buy(emu, "warp")
        return emu, [c for c in emu.calls if c[0] == "message"]

    def test_warp_done_message_after_the_warp(self) -> None:
        emu, messages = self.warp(5000, free=False)
        self.assertEqual(messages[-1][1], "Time Warp done: 12 hours played (72 age steps). $500 paid.")
        self.assertEqual(messages[-1][2], 4500)                    # paid before it shows
        self.assertEqual(messages[-1][3], 4)                       # after the real-time update and all 3 chunks
        self.assertEqual(len([c for c in emu.calls if c[0] == "update"]), 4)
        self.assertEqual(len(messages), 2)                         # the Yes/No question, then the message

    def test_warp_done_message_counts_the_steps_at_each_speed(self) -> None:
        for speed, hours, steps in ((5, 1, "12 age steps"), (10, 72, "432 age steps"), (15, 5, "20 age steps")):
            _emu, messages = self.warp(500, free=False, hours=hours, speed=speed)
            unit = "hour" if hours == 1 else "hours"
            self.assertEqual(messages[-1][1], f"Time Warp done: {hours} {unit} played ({steps}). $500 paid.")

    def test_warp_done_message_free(self) -> None:
        emu, messages = self.warp(0, free=True, hours=3)
        self.assertEqual(messages[-1][1], "Time Warp done: 3 hours played (18 age steps). $0 paid.")
        self.assertEqual(self.money(emu), 0)

    def test_no_warp_done_message_on_a_refusal(self) -> None:
        for money, speed, answer_yes in ((499, 10, True), (5000, 10 + 9999, True), (5000, 10, False)):
            emu, messages = self.warp(money, free=False, speed=speed, answer_yes=answer_yes)
            self.assertFalse([m for m in messages if m[1].startswith("Time Warp done")], (money, speed, answer_yes))
            self.assertFalse([c for c in emu.calls if c[0] == "update"])
            self.assertEqual(self.money(emu), money)


# ------------------------------------------------------------------ Plant Tycoon

S_CASH = 0x217C
TOOL_RECORD = 0x6E8


@_needs(PLANT_EXE)
class PlantStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_plant_upgrades", ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll",
            Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def store(self, cash: int, free: bool, add_money: bool = True, answer_yes: bool = True):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.hook_printf()

        def message(e):
            e.calls.append(("MessageBoxW", e.wstring(e.arg(1))))
            return 6 if answer_yes else 7                                         # IDYES / IDNO
        emu.hook_import("MessageBoxW", message, 16)
        emu.hook_import("DialogBoxIndirectParamW", emu.record("hours dialog"), 20)  # cancelled
        for name, pop in (("GetActiveWindow", 0), ("GetForegroundWindow", 0), ("GetModuleHandleW", 4),
                          ("GetProcAddress", 8)):
            emu.hook_import(name, emu.record(name), pop)
        emu.hook(0x0044A580, emu.record("sound"), 4)
        emu.hook(0x0044E894, lambda e: e.alloc(e.arg(0)), 0)                      # operator new
        emu.hook(0x00409870, lambda e: (e.calls.append(("tip", e.cstring(e.arg(3)).decode("latin-1"))), 0)[1], 0x1C)
        emu.hook(0x00409AA0, lambda e: (e.calls.append(("tip", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 0x10)
        emu.hook(0x0040B400, emu.record("control"), 4)
        state = emu.alloc(0x60000)

        def box_dialog(e):
            e.calls.append(("dialog", e.arg(0), e.read32(state + TOOL_RECORD + 4 * 0x20)))
            return 0
        emu.hook(0x00432E90, box_dialog, 4)
        emu.hook(0x00401C90, emu.record("run"), 8)
        emu.hook(0x004307A0, emu.record("dtor"), 0)
        scene = emu.alloc(0x400)
        emu.write32(scene + 0x1BC, state)
        emu.write32(state + S_CASH, cash)
        events = emu.alloc(0x20)
        zero = emu.thunk()
        emu.hook(zero, lambda e: 0, 0)                                            # owned(box) = no, set_owned
        emu.write32(events, 1)
        for k in range(1, 7):
            emu.write32(events + 4 * k, zero)
        emu.write32(emu.sym("_boxes"), events)
        emu.write8(emu.sym("_free_upgrades"), int(free))
        emu.write32(emu.sym("_money_on"), int(add_money))
        emu.write32(emu.sym("_warp_on"), 1)
        emu.state, emu.scene = state, scene
        return emu

    def click(self, emu, x: int, y: int) -> None:
        emu.write32(emu.sym("_upgrades_view"), 1)
        emu.call(emu.sym("_on_click"), emu.scene, x, y)

    def cash(self, emu) -> int:
        return emu.read32(emu.state + S_CASH)

    def test_legendary_seed_price(self) -> None:
        for free, expected in ((False, 5000), (True, 0)):
            for stub, back in (("_stub_price_buyable", 0x00430CB2), ("_stub_price_poor", 0x0043101F),
                               ("_stub_price_tray_full", 0x00431378)):
                emu = self.store(0, free)
                dialog = emu.alloc(0x400)
                emu.write8(emu.sym("_building_legendary"), 1)
                emu.run_until(emu.sym(stub), back, esi=dialog)
                self.assertEqual(emu.read32(dialog + 0x84), expected, (stub, free))
                emu = self.store(0, free)                       # a stock Extinct packet keeps $2000
                emu.run_until(emu.sym(stub), back, esi=dialog)
                self.assertEqual(emu.read32(dialog + 0x84), 2000)

    def test_formula_price(self) -> None:
        # The formula $10,000, the Revival Potion $10,000, Revita-Seed $2,500, $0 with Free upgrades;
        # the tray-room check (0x4164B0) is asked about the chemical's own id, and eax is kept.
        for chemical, normal in ((36, 10000), (37, 10000), (38, 2500)):
            for free, expected in ((False, normal), (True, 0)):
                emu = self.store(0, free)
                emu.write8(emu.sym("_building_chem"), chemical)
                emu.uc.reg_write(E.X.UC_X86_REG_EAX, 0x1234)
                emu.run_until(emu.sym("_stub_chem_price"), 0x00432721, esi=emu.alloc(0x100))
                self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EDX), expected, (chemical, free))
                self.assertEqual(emu.read32(emu.uc.reg_read(E.X.UC_X86_REG_ESP)), chemical)
                self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EAX), 0x1234)

    def test_buying_a_free_legendary_packet_still_empties_its_shelf(self) -> None:
        emu = self.store(0, True)
        emu.hook(0x00430900, lambda e: 0, 0)                     # the first free tray slot: 0
        legendary = emu.sym("_legendary")
        emu.write32(legendary + 6 * 4, 1)                        # packet 0 on the shelf
        dialog = emu.alloc(0x400)
        emu.write32(dialog + 0xB8, 52)
        emu.write32(dialog + 0x74, emu.state)
        emu.write32(dialog + 0x84, 0)
        emu.call(emu.sym("_buy_legendary"), dialog)
        self.assertEqual(emu.read32(legendary + 6 * 4) & 0xFF, 0)  # sold: back with the daily restock
        self.assertEqual(emu.read32(emu.state + 0x52B88 + 6 * 4) & 0xFF, 1)
        self.assertEqual(self.cash(emu), 0)

    def test_seed_box_price(self) -> None:
        for free, expected in ((False, 1000), (True, 0)):
            emu = self.store(0, free)
            self.click(emu, 480, 60)                              # the Fourth Seed Box
            self.assertEqual([c for c in emu.calls if c[0] == "dialog"], [("dialog", 14, expected)])
            self.assertEqual(emu.read32(emu.state + TOOL_RECORD + 4 * 0x20), 0)   # stock record put back

    def test_tooltips_show_the_price(self) -> None:
        for free in (False, True):
            emu = self.store(0, free)
            emu.call(emu.sym("_on_activate"), emu.scene, 1)
            tips = [c[1] for c in emu.calls if c[0] == "tip"]
            prices = ("5000", "10000", "1000", "500", "950")
            for price, title in zip(prices, ("Legendary Seeds", "Radioactive", "Fourth Seed Box", "Time Warp",
                                             "Add $1,000")):
                tip = next(t for t in tips if t.startswith(title))
                self.assertTrue(tip.endswith(f"Price: $ {'0' if free else price}"), tip)

    def test_time_warp_is_free(self) -> None:
        emu = self.store(0, False)
        self.click(emu, 310, 310)
        self.assertIn("can't afford", emu.calls[-1][1])
        emu = self.store(0, True)
        self.click(emu, 310, 310)
        self.assertEqual(emu.calls[-1][0], "hours dialog")       # past the price; cancelled
        self.assertEqual(self.cash(emu), 0)

    def test_add_money_costs_950_and_adds_1000_every_time(self) -> None:
        emu = self.store(1000, False)
        for expected in (1050, 1100, 1150):
            self.click(emu, 380, 310)
            self.assertEqual(self.cash(emu), expected)
        self.assertIn("Buy +$1,000 for $950?", [c[1] for c in emu.calls if c[0] == "MessageBoxW"])

    def test_add_money_refused_below_950(self) -> None:
        emu = self.store(949, False)
        self.click(emu, 380, 310)
        self.assertEqual(self.cash(emu), 949)
        self.assertIn("can't afford", emu.calls[-1][1])

    def test_add_money_free_adds_1000(self) -> None:
        emu = self.store(0, True)
        self.click(emu, 380, 310)
        self.click(emu, 380, 310)
        self.assertEqual(self.cash(emu), 2000)
        self.assertIn("Buy +$1,000 for $0?", [c[1] for c in emu.calls if c[0] == "MessageBoxW"])

    def test_add_money_stops_at_the_games_own_maximum(self) -> None:
        # The game's cash function 0x41ED70 keeps cash at most 4,000,000,000 (the double at 0x467F78).
        exe = PLANT_EXE.read_bytes()
        self.assertEqual(struct.unpack_from("<d", exe, 0x467F78 - 0x465000 + 0x65000)[0], 4_000_000_000.0)
        for free in (False, True):
            emu = self.store(4_000_000_000 - 10, free)
            self.click(emu, 380, 310)
            self.assertEqual(self.cash(emu), 4_000_000_000)
            self.click(emu, 380, 310)
            self.assertEqual(self.cash(emu), 4_000_000_000)

    def test_add_money_answered_no_changes_nothing(self) -> None:
        emu = self.store(5000, False, answer_yes=False)
        self.click(emu, 380, 310)
        self.assertEqual(self.cash(emu), 5000)

    def test_drawn_strings_fit_the_game_font(self) -> None:
        font = plant_font()
        self.assertLessEqual(set("+$,.:!()-09AZaz"), font)
        drawn = set()
        for free in (False, True):
            emu = self.store(0, free)
            emu.call(emu.sym("_on_activate"), emu.scene, 1)
            drawn |= {c[1] for c in emu.calls if c[0] == "tip"}
        self.assertIn("Add $1,000\nPrice: $ 950", drawn)
        self.assertGreater(len(drawn), 10)
        for text in drawn:
            self.assertLessEqual(set(text), font, text)

    # --- Time Warp's "done" message
    def warp(self, cash: int, free: bool, hours: int = 12, speed: int = 10, answer_yes: bool = True):
        """Click the Time Warp clock: the popup answers `hours`, the question Yes/No."""
        emu = self.store(cash, free, answer_yes=answer_yes)
        emu.write32(emu.state + 0x534, speed)
        now = 1_000_000
        pot = emu.state + 0x2188                                                  # pot 0: a live plant
        emu.write32(pot + 0x04, now - 30)
        emu.write32(pot + 0x24, 50)
        emu.write32(pot + 0x4C, 1)

        def message(e):
            e.calls.append(("MessageBoxW", e.wstring(e.arg(1)), self.cash(e), e.read32(pot + 0x04),
                            sum(1 for c in e.calls if c[0] == "update")))
            return 6 if answer_yes else 7
        def ask_hours(e):
            e.write32(e.arg(4) + 4, hours)
            return 1
        emu.hook_import("MessageBoxW", message, 16)
        emu.hook_import("DialogBoxIndirectParamW", ask_hours, 20)
        emu.hook(0x00403430, lambda e: now, 0)                                    # the game's clock
        emu.hook(0x0041D810, emu.record("update"), 0)                             # the plant update
        self.click(emu, 310, 310)
        return emu, [c for c in emu.calls if c[0] == "MessageBoxW"], now - 30

    def test_warp_done_message_after_the_warp(self) -> None:
        emu, messages, stamp = self.warp(5000, False)
        self.assertEqual(messages[-1][1], "Time Warp done: 12 hours played (72 age units). $500 paid.")
        self.assertEqual(messages[-1][2], 4500)                    # paid
        self.assertEqual(messages[-1][3], stamp - 12 * 3600)       # the pot's clock moved back
        self.assertEqual(messages[-1][4], 1)                       # and the plant update has run
        self.assertEqual(len(messages), 2)                         # the Yes/No question, then the message

    def test_warp_done_message_counts_the_units_at_each_speed(self) -> None:
        for speed, hours, units in ((2, 1, "30 age units"), (10, 72, "432 age units"), (15, 5, "20 age units")):
            _emu, messages, _stamp = self.warp(500, False, hours=hours, speed=speed)
            unit = "hour" if hours == 1 else "hours"
            self.assertEqual(messages[-1][1], f"Time Warp done: {hours} {unit} played ({units}). $500 paid.")

    def test_warp_done_message_free(self) -> None:
        emu, messages, _stamp = self.warp(0, True, hours=3)
        self.assertEqual(messages[-1][1], "Time Warp done: 3 hours played (18 age units). $0 paid.")
        self.assertEqual(self.cash(emu), 0)

    def test_no_warp_done_message_on_a_refusal(self) -> None:
        for cash, speed, answer_yes in ((499, 10, True), (5000, 10 + 9999, True), (5000, 10, False)):
            emu, messages, _stamp = self.warp(cash, False, speed=speed, answer_yes=answer_yes)
            self.assertFalse([m for m in messages if m[1].startswith("Time Warp done")], (cash, speed, answer_yes))
            self.assertFalse([c for c in emu.calls if c[0] == "update"])
            self.assertEqual(self.cash(emu), cash)

    def test_add_money_hidden_without_its_setting(self) -> None:
        emu = self.store(5000, False, add_money=False)
        self.click(emu, 380, 310)
        self.assertEqual(self.cash(emu), 5000)
        self.assertFalse([c for c in emu.calls if c[0] == "MessageBoxW"])


if __name__ == "__main__":
    unittest.main()
