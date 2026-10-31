"""Automatic Sprinklers, the Auto-Feeder and the Auto-Healers (both games).

Fish Tycoon (DS Store Items, the Upgrades page): the Auto-Feeder and the Auto-Healer. Plant
Tycoon (Store Upgrades and Items, the Upgrades view): Automatic Sprinklers and the Auto-Healer.
Each $10,000 ($0 with Free upgrades), bought once, unpurchased with a click (no refund), kept per
slot in "Auto Upgrades <slot>.dat".

The emulation tests run each DLL's own code and the vanilla executables' code in Unicorn
(tests/store_emulator.py): the fish update 0x41FE70 with the DLL's step hook (0x4204B3) and death
hook (0x420622) written in, the feeding 0x412160, and the plant update 0x42DF80 with the DLL's
age-unit hooks (0x42E134, 0x42E2DF) written in.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import tycoon_fix_patcher as combined  # noqa: E402

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
FISH_IMAGES = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
PLANT_SHEET = ROOT / "assets" / "plant_tycoon_upgrades" / "Images" / "Chemicals_Grid_upgrades.png"
SOURCES = ROOT / "assets" / "auto_upgrades"

FEEDER_TEXT = "Automatically feeds all your fish in every tank. No more starvation, ever!"
FISH_HEALER_TEXT = "Magically cures all diseases from fish and restores them to full health. Works in every tank."
SPRINKLERS_TEXT = ("Automatically waters all pots in the greenhouse. Optimizes water levels for minimal pest "
                   "infestations and problems.")
PLANT_HEALER_TEXT = ("Magically cures all diseases from plants and restores them to full health. Works in every "
                     "greenhouse.")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return struct.unpack(">II", data[16:24])


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


def jump(emu, at: int, to: int, length: int) -> None:
    """Write the DLL's jump into the emulated game, as the install does."""
    emu.uc.mem_write(at, b"\xE9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (length - 5))


# ------------------------------------------------------------------ art and texts

class ArtAndManifestTests(unittest.TestCase):
    def test_the_owner_pictures_are_committed(self) -> None:
        self.assertEqual(png_size(SOURCES / "automatic_sprinklers_source.png"), (159, 130))
        self.assertEqual(png_size(SOURCES / "auto_feeder_source.png"), (197, 154))
        self.assertEqual(png_size(SOURCES / "auto_healer_source.png"), (197, 154))
        for name in ("auto-upgrades-fish.png", "auto-upgrades-plant.png"):
            self.assertTrue((ROOT / "docs" / "images" / name).is_file(), name)

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "needs Pillow")
    def test_the_healer_is_the_feeder_in_hot_pink(self) -> None:
        import numpy as np
        from PIL import Image
        import build_auto_healer_source
        built = build_auto_healer_source.healer(Image.open(SOURCES / "auto_feeder_source.png"))
        committed = Image.open(SOURCES / "auto_healer_source.png").convert("RGBA")
        self.assertTrue((np.asarray(built) == np.asarray(committed)).all())

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "needs Pillow")
    def test_the_pictures_match_their_neighbours(self) -> None:
        from PIL import Image
        for name in ("ITEM_AUTO_FEEDER.png", "ITEM_AUTO_HEALER.png"):
            box = Image.open(FISH_IMAGES / name).getchannel("A").getbbox()
            self.assertEqual((box[3] - box[1], box[3]), (57, 62), name)        # as item_growthhormone.png
            self.assertEqual(png_size(FISH_IMAGES / name), (73, 65), name)
        sheet = Image.open(PLANT_SHEET).convert("RGBA")
        self.assertEqual(sheet.size, (140, 20 * 70))   # rows 18-19: Extra Chemical Slots
        cell = lambda row, col=0: sheet.crop((col * 70, row * 70, col * 70 + 70, row * 70 + 70)).getchannel("A").getbbox()
        sprinklers, healer, formula = cell(16), cell(17), cell(9)
        self.assertEqual((sprinklers[3] - sprinklers[1], sprinklers[3]), (49, 65))    # the seed box's drawer beside it
        self.assertEqual((healer[1], healer[3]), (formula[1], formula[3]))            # the formula above it
        self.assertIsNone(cell(16, 1))
        self.assertIsNone(cell(17, 1))

    @unittest.skipUnless(E is not None and FISH_EXE is not None and FISH_EXE.is_file()
                         and PLANT_EXE is not None and PLANT_EXE.is_file(), "needs the vanilla games")
    def test_the_art_is_rebuilt_by_its_pinned_scripts(self) -> None:
        import numpy as np
        from PIL import Image
        import build_auto_upgrades_assets
        import build_plant_upgrades_assets
        for name, image in build_auto_upgrades_assets.fish_pictures().items():
            committed = Image.open(FISH_IMAGES / name).convert("RGBA")
            self.assertTrue((np.asarray(image) == np.asarray(committed)).all(), name)
        sheet = build_plant_upgrades_assets.formula_bottle(PLANT_EXE.parent / "Images")
        self.assertTrue((np.asarray(sheet) == np.asarray(Image.open(PLANT_SHEET).convert("RGBA"))).all())

    def test_the_manifests_name_them(self) -> None:
        store = combined.patch_settings("fish")["ds_store"]
        destinations = {f["destination"] for f in store["companion"]["files"]}
        for name in ("ITEM_AUTO_FEEDER.png", "ITEM_AUTO_HEALER.png"):
            self.assertIn(f"Images/{name}", destinations)
        for text in ("Auto-Feeder ($10,000)", "Auto-Healer ($10,000)", "Unpurchase"):
            self.assertIn(text, store["description"])
        upgrades = combined.patch_settings("plant")["plant_upgrades"]
        for text in ("Automatic Sprinklers ($10,000)", "Auto-Healer ($10,000)", "unpurchase"):
            self.assertIn(text, upgrades["description"])
        self.assertIn("the Auto-Feeder ($10,000), the Auto-Healer ($10,000)",
                      combined.patch_settings("fish")["free_upgrades"]["description"])
        self.assertIn("Automatic Sprinklers ($10,000), the Auto-Healer ($10,000)",
                      combined.patch_settings("plant")["free_upgrades"]["description"])


# ------------------------------------------------------------------ Fish Tycoon

S_DIFFICULTY, S_CURED, S_SPENT, S_TANK, S_MONEY, S_SPEED = 0x14, 0x34, 0x24, 0x384, 0x38C, 0x1E168
FISH, TANK, REC = 0x390, 0x51EC, 0x288
F_LIVE, F_AGE, F_LAST_AGE, F_DUE, F_HEALTH, F_DISEASE, F_FOOD, F_BODY, F_FIN = (
    0x00, 0x0C, 0x08, 0x10, 0x3C, 0x40, 0x44, 0x4C, 0x50)
NOW = 1_000_000
STEP = 600                                       # seconds per age step at Normal speed (60 x 10)
FEEDER, HEALER = 10, 11                          # the items' places in ITEM
CELLS = {FEEDER: (170, 200), HEALER: (260, 200)}


def fish_record(age: int = 25, body: int = 5, fin: int = 7, health: int = 70, food: int = 50, disease: int = 0,
                steps: int = 1, seed: int = 0) -> bytes:
    r = bytearray((i * 13 + seed * 7 + 1) & 0x3F for i in range(REC))
    struct.pack_into("<IIii", r, 0, NOW - steps * STEP, 0, age, age)
    struct.pack_into("<iii", r, 0x10, 0, body, fin)
    struct.pack_into("<iii", r, 0x3C, health, disease, food)
    struct.pack_into("<ii", r, 0x4C, body, fin)
    struct.pack_into("<i", r, 0x14, 0)                  # no animal mark
    return bytes(r)


@_needs(FISH_EXE)
class FishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_ds_store", ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll", Path(cls.tmp.name))
        import fish_patcher
        manifest = combined.load_manifest("fish")
        data, _ = fish_patcher.apply_patch_bytes(FISH_EXE.read_bytes(),
                                                 fish_patcher.active_patch_records(manifest, {"bigger_tanks"}))
        cls.exe30 = Path(cls.tmp.name) / "Fish Tycoon 30.exe"
        cls.exe30.write_bytes(data)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ the store
    def store(self, money: int, free: bool = False, answer_yes: bool = True):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        emu.hook_import("GetTickCount", lambda e: 0, 0)
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)            # no Extra Tanks.dll loaded

        def message(e):
            e.calls.append(("MessageBoxW", e.wstring(e.arg(2)), e.wstring(e.arg(1))))
            return 6 if answer_yes else 7
        emu.hook_import("MessageBoxW", message, 16)
        for name in ("GetActiveWindow", "GetForegroundWindow"):
            emu.hook_import(name, lambda e: 0, 0)
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        emu.hook(0x004221A0, emu.record("dialog", args=1), 8)
        emu.hook(0x00401D00, emu.record("run", 0), 8)                   # Yes
        emu.hook(0x00422440, emu.record("free"), 0)
        emu.hook(0x00425120, emu.record("sounds"), 0)
        emu.hook(0x004251A0, emu.record("sound"), 4)
        table, price = emu.alloc(16), emu.text("Price:")
        emu.hook(0x00427060, lambda e: table, 0)
        emu.hook(0x00427050, lambda e: price, 4)
        emu.hook(0x0041BE70, lambda e: 1, 4)
        emu.hook(0x00408A40, emu.record("draw"), 12)
        emu.hook(0x00408AE0, emu.record("draw"), 24)
        emu.hook(0x00408B80, lambda e: (e.calls.append(("text", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 20)
        state, impl, scene = emu.alloc(0x40000), emu.alloc(0x100), emu.alloc(0x100)
        emu.write32(scene + 8, impl)
        emu.write32(impl + 0x10, state)
        emu.write32(impl + 0x0C, emu.alloc(0x40))
        emu.write32(state + S_MONEY, money)
        emu.write32(emu.sym("_free_on"), int(free))
        emu.write32(emu.sym("_page_upgrades"), 1)
        emu.write32(0x0045ABDC, state)
        emu.state, emu.scene = state, scene
        return emu

    def select(self, emu, item: int) -> None:
        emu.call(emu.sym("@on_mouse@20"), 3, *CELLS[item], ecx=emu.scene)

    def buy(self, emu, item: int) -> None:
        self.select(emu, item)
        emu.call(emu.sym("_buy"), emu.scene)

    def owned(self, emu) -> tuple[int, int]:
        raw = bytes(emu.uc.mem_read(emu.sym("_auto_owned"), 2))
        return raw[0], raw[1]

    def money(self, emu) -> tuple[int, int]:
        return emu.read32(emu.state + S_MONEY), emu.read32(emu.state + S_SPENT)

    def shown(self, emu, item: int) -> list[str]:
        emu.calls.clear()
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        return [c[1] for c in emu.calls if c[0] == "text"]

    def test_names_descriptions_and_prices(self) -> None:
        for item, name, words in ((FEEDER, "Auto-Feeder", FEEDER_TEXT), (HEALER, "Auto-Healer", FISH_HEALER_TEXT)):
            emu = self.store(0)
            self.select(emu, item)
            texts = self.shown(emu, item)
            self.assertIn(name, texts)
            self.assertIn(words, [t.replace("\n", " ") for t in texts])            # the owner's exact words
            self.assertIn("Price:  $10000", texts)
            emu = self.store(0, free=True)
            self.select(emu, item)
            self.assertIn("Price:  $0", self.shown(emu, item))

    def test_buying_once_with_the_games_question(self) -> None:
        for item, k in ((FEEDER, 0), (HEALER, 1)):
            emu = self.store(10007)
            self.buy(emu, item)
            self.assertIn(("dialog", (0xEC,)), emu.calls)                       # the game's purchase question
            self.assertEqual(self.owned(emu)[k], 1)
            self.assertEqual(self.money(emu), (7, 10000))
            emu.calls.clear()
            emu.call(emu.sym("_buy"), emu.scene)                                # Buy again: the stock answer
            self.assertIn(("hint", (0x1C,)), emu.calls)                         # "You already own this!"
            self.assertEqual(self.money(emu), (7, 10000))
            self.assertIn("Owned. Click it again to unpurchase.", self.shown(emu, item))
            emu = self.store(9999)
            self.buy(emu, item)
            self.assertIn(("hint", (2,)), emu.calls)                            # "You can't afford to buy this yet!"
            self.assertEqual(self.owned(emu), (0, 0))
            emu = self.store(0, free=True)
            self.buy(emu, item)
            self.assertEqual(self.owned(emu)[k], 1)
            self.assertEqual(self.money(emu), (0, 0))

    def test_unpurchase_switches_off_without_a_refund(self) -> None:
        for item, k, name in ((FEEDER, 0, "Auto-Feeder"), (HEALER, 1, "Auto-Healer")):
            emu = self.store(10000, answer_yes=False)
            self.buy(emu, item)
            self.assertEqual(self.owned(emu)[k], 1)
            self.select(emu, item)                                              # clicked again: the question
            asked = [c for c in emu.calls if c[0] == "MessageBoxW"]
            self.assertEqual(asked[-1][1:], (name, f"Unpurchase {name}? It switches off. There is no refund, and "
                                                   "buying it again costs the full price."))
            self.assertEqual(self.owned(emu)[k], 1)                             # No: nothing changes
            self.assertEqual(self.money(emu), (0, 10000))
            emu = self.store(10000)
            self.buy(emu, item)
            self.select(emu, item)
            self.assertEqual(self.owned(emu)[k], 0)                             # Yes: off
            self.assertEqual(self.money(emu), (0, 10000))                       # no refund
            emu.write32(emu.state + S_MONEY, 10000)
            self.buy(emu, item)                                                 # buying again: the full price
            self.assertEqual(self.owned(emu)[k], 1)
            self.assertEqual(self.money(emu), (0, 20000))
            emu = self.store(0, free=True)
            self.buy(emu, item)
            self.select(emu, item)
            self.buy(emu, item)
            self.assertEqual((self.owned(emu)[k], self.money(emu)), (1, (0, 0)))

    def test_a_first_click_on_an_owned_item_only_selects_it(self) -> None:
        emu = self.store(10000)
        self.buy(emu, FEEDER)
        self.select(emu, HEALER)
        self.select(emu, FEEDER)
        self.assertFalse([c for c in emu.calls if c[0] == "MessageBoxW"])
        self.assertEqual(self.owned(emu), (1, 0))

    # ------------------------------------------------------------ the sidecar
    def test_ownership_round_trip_new_game_and_unreadable(self) -> None:
        from test_ds_store_animals import Files
        emu = self.store(0)
        files = Files(emu)
        path = "C:\\Docs\\LDW\\Fish Tycoon\\Fish Tycoon Fix Patcher Data\\Auto Upgrades 3.dat"
        emu.uc.mem_write(emu.sym("_auto_owned"), bytes([0, 1]))
        emu.call(emu.sym("_auto_save"), 3)
        self.assertEqual(files.files[path], struct.pack("<4I", 0x55415446, 1, 0, 1))
        self.assertNotIn(path + ".tmp", files.files)
        emu.uc.mem_write(emu.sym("_auto_owned"), bytes([1, 0]))
        emu.call(emu.sym("_auto_load"), 3)
        self.assertEqual(self.owned(emu), (0, 1))
        emu.call(emu.sym("_auto_load"), 4)                                      # no file: owns neither
        self.assertEqual(self.owned(emu), (0, 0))
        emu.call(emu.sym("_auto_load"), 3)
        emu.call(emu.sym("_clear_animals"), emu.state)                          # a new game
        self.assertEqual(self.owned(emu), (0, 0))
        files.files[path] = b"\x00" * 15
        emu.uc.mem_write(emu.sym("_auto_owned"), bytes([1, 1]))
        emu.call(emu.sym("_auto_load"), 3)
        self.assertEqual(self.owned(emu), (0, 0))
        self.assertIn(path + ".unreadable", files.files)                        # set aside, never deleted

    def test_unpurchase_is_saved_as_off(self) -> None:
        from test_ds_store_animals import Files
        emu = self.store(10000)
        self.buy(emu, HEALER)
        self.select(emu, HEALER)
        files = Files(emu)
        emu.call(emu.sym("_auto_save"), 2)
        path = "C:\\Docs\\LDW\\Fish Tycoon\\Fish Tycoon Fix Patcher Data\\Auto Upgrades 2.dat"
        self.assertEqual(files.files[path], struct.pack("<4I", 0x55415446, 1, 0, 0))

    # ------------------------------------------------------------ the effect
    def tanks(self, owned: tuple[int, int], exe: Path | None = None, rolls=None):
        emu = E.Emulator(exe or FISH_EXE, self.dll, self.symbols)
        rolls = list(rolls or [])
        emu.hook(0x00403240, lambda e: rolls.pop(0) if rolls else 9999 % max(1, e.arg(0)))
        emu.hook(0x004020D0, lambda e: 50_000)
        emu.hook(0x004032C0, lambda e: NOW, 0)
        emu.hook(0x0041FA30, emu.record("baby"), 0x38)
        emu.hook(0x00415E70, emu.record("view sync"), 4)
        emu.hook(0x00413B00, emu.record("splash"), 0x0C)
        emu.hook(0x00425120, lambda e: 0, 0)
        emu.hook(0x004251A0, lambda e: 0, 4)
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)
        state, impl, view = emu.alloc(0x1E600), emu.alloc(0x400), emu.alloc(0x6000)
        emu.write32(impl + 0x34, state)
        emu.write32(impl + 0x3C, emu.alloc(4))
        emu.write32(emu.read32(impl + 0x3C), view)
        emu.write32(view + 0x5DE4, state)
        emu.write32(state + S_SPEED, 10)
        emu.write32(state + 0x244, 1)                                           # Fish Food research 1
        emu.write32(state + 0x258, 1)
        emu.write32(state + S_DIFFICULTY, 1)
        emu.write32(0x0045ABDC, state)
        jump(emu, 0x004204B3, emu.sym("_stub_auto_step"), 10)
        jump(emu, 0x00420622, emu.sym("_stub_death"), 10)
        jump(emu, 0x004121F4, emu.sym("_stub_overfeed"), 10)
        emu.uc.mem_write(emu.sym("_auto_owned"), bytes(owned))
        emu.state, emu.impl, emu.view = state, impl, view
        return emu

    def put(self, emu, tank: int, slot: int, record: bytes) -> int:
        at = emu.state + FISH + tank * TANK + slot * REC
        emu.uc.mem_write(at, record)
        return at

    def field(self, emu, at: int, offset: int) -> int:
        return emu.read32(at + offset, signed=True)

    def update(self, emu) -> None:
        emu.call(0x0041FE70, ecx=emu.impl, esi=emu.impl)

    def test_every_tank_and_slot_is_fed_and_healed(self) -> None:
        # Tank 1, Tank 2, the Sale Tank and the isolation tank; slot 29 with Bigger tanks.
        for exe, places in ((None, ((0, 0), (1, 4), (2, 20), (3, 0))), (self.exe30, ((0, 29), (2, 29)))):
            emu = self.tanks((1, 1), exe)
            hungry = {place: self.put(emu, *place, fish_record(health=30, food=3, disease=2, steps=40))
                      for place in places}
            self.update(emu)
            for place, at in hungry.items():
                self.assertEqual(self.field(emu, at, F_HEALTH), 100, place)
                self.assertEqual(self.field(emu, at, F_DISEASE), 0, place)
                self.assertIn(self.field(emu, at, F_FOOD), (99, 100), place)  # full: never 2 or less
                self.assertEqual(self.field(emu, at, F_AGE), 25 + 40, place)   # alive through every step
            self.assertEqual(emu.read32(emu.state + S_CURED), len(places))    # one Fish Cured per cure

    def test_off_they_change_nothing(self) -> None:
        results = []
        for owned in ((0, 0), None):
            emu = self.tanks(owned or (0, 0))
            if owned is None:                                                   # the stock code, no DLL hooks
                emu.uc.mem_write(0x004204B3, bytes.fromhex("8B5634399C17D0030000"))
                emu.uc.mem_write(0x00420622, bytes.fromhex("8B5634399C17CC030000"))
            at = self.put(emu, 1, 3, fish_record(health=30, food=3, disease=2, steps=12))
            self.update(emu)
            results.append(bytes(emu.uc.mem_read(at, REC)))
        self.assertEqual(results[0], results[1])

    def test_each_one_alone(self) -> None:
        emu = self.tanks((1, 0))                                                # the feeder only
        at = self.put(emu, 0, 0, fish_record(body=4, fin=8, health=60, food=3, disease=1, steps=3))
        self.update(emu)
        self.assertIn(self.field(emu, at, F_FOOD), (99, 100))
        self.assertEqual(self.field(emu, at, F_DISEASE), 1)                    # still sick
        emu = self.tanks((0, 1))                                                # the healer only
        at = self.put(emu, 0, 0, fish_record(health=60, food=40, disease=1, steps=3))
        self.update(emu)
        self.assertEqual((self.field(emu, at, F_HEALTH), self.field(emu, at, F_DISEASE)), (100, 0))
        self.assertEqual(self.field(emu, at, F_FOOD), 37)                       # the stock food drop, 1 a step

    def test_a_dead_fish_is_never_revived_fed_or_cured(self) -> None:
        emu = self.tanks((1, 1))
        dead = fish_record(health=0, food=0, disease=2, steps=30)
        at = self.put(emu, 0, 5, dead)
        self.update(emu)
        self.assertEqual(bytes(emu.uc.mem_read(at, REC)), dead)
        emu.call(emu.sym("_auto_tend_all"), emu.state)                          # nor at a purchase
        self.assertEqual(bytes(emu.uc.mem_read(at, REC)), dead)

    def feed_by_hand(self, emu) -> None:
        emu.write32(emu.view + 0x5DD8, 1)                                       # one swimming fish: slot 0 of tank 0
        emu.write32(emu.view + 0x1144, 0)
        emu.write32(emu.view + 0x1148, 0)
        emu.call(0x00412160, 400, 300, ecx=emu.view)                            # the game's feeding

    def test_feeding_by_hand_with_the_feeder_never_costs_health(self) -> None:
        emu = self.tanks((1, 0))
        at = self.put(emu, 0, 0, fish_record(body=4, fin=8, health=80, food=30, steps=1))
        self.update(emu)
        self.assertIn(self.field(emu, at, F_FOOD), (99, 100))                  # kept full
        health = self.field(emu, at, F_HEALTH)
        for _ in range(3):                                                      # fed again and again on top
            self.feed_by_hand(emu)
            self.assertEqual(self.field(emu, at, F_FOOD), 100)
            self.assertEqual(self.field(emu, at, F_HEALTH), health)            # no overfeeding harm

    def test_feeding_by_hand_without_the_feeder_is_stock(self) -> None:
        for owned in ((0, 0), (0, 1)):                                          # the healer alone changes nothing here
            emu = self.tanks(owned)
            at = self.put(emu, 0, 0, fish_record(body=4, fin=8, health=80, food=90, steps=0))
            self.feed_by_hand(emu)
            self.assertEqual((self.field(emu, at, F_FOOD), self.field(emu, at, F_HEALTH)), (100, 78), owned)
            emu = self.tanks(owned)
            at = self.put(emu, 0, 0, fish_record(body=4, fin=8, health=80, food=40, steps=0))
            self.feed_by_hand(emu)                                              # 90: not overfed
            self.assertEqual((self.field(emu, at, F_FOOD), self.field(emu, at, F_HEALTH)), (90, 80), owned)
        emu = self.tanks((1, 0))                                                # the seahorse: spared, as stock
        at = self.put(emu, 0, 0, fish_record(body=22, fin=22, health=80, food=90, steps=0))
        self.feed_by_hand(emu)
        self.assertEqual(self.field(emu, at, F_HEALTH), 80)

    def test_a_purchase_reaches_every_tank_and_the_extra_tanks_off_screen(self) -> None:
        emu = self.tanks((1, 1))
        blocks = [emu.alloc(TANK + 5 * REC) for _ in range(3)]
        thunk = emu.thunk()
        emu.hook(thunk, lambda e: blocks[e.arg(0)], 4)
        emu.hook_import("GetModuleHandleW", lambda e: 0x6C000000 if e.wstring(e.arg(0)) == "Extra Tanks.dll" else 0, 4)
        emu.hook_import("GetProcAddress", lambda e: thunk if e.cstring(e.arg(1)) == b"FtfpExtraTanksHeld" else 0, 8)
        sick = fish_record(health=20, food=4, disease=2, steps=0)
        places = [self.put(emu, t, 7, sick) for t in range(4)]
        for b in blocks:                                                        # Tanks 4-6, held off screen
            emu.uc.mem_write(b + 20 * REC, sick)
            places.append(b + 20 * REC)
        emu.call(emu.sym("_auto_tend_all"), emu.state)
        for at in places:
            self.assertEqual((self.field(emu, at, F_HEALTH), self.field(emu, at, F_DISEASE),
                              self.field(emu, at, F_FOOD)), (100, 0, 100))

    def test_an_extra_tank_updated_off_screen(self) -> None:
        # Extra Tanks.dll plays Tanks 4-6 by moving each one's block into a stock tank's place and
        # running the game's own update (FtfpExtraTanksUpdate); the step hook is in that code.
        emu = self.tanks((1, 1))
        held = fish_record(health=25, food=2, disease=1, steps=20)
        block = bytearray(TANK)
        block[9 * REC:10 * REC] = held
        stock = bytes(emu.uc.mem_read(emu.state + FISH + 2 * TANK, TANK))
        emu.uc.mem_write(emu.state + FISH + 2 * TANK, bytes(block))             # moved in
        self.update(emu)
        block = bytes(emu.uc.mem_read(emu.state + FISH + 2 * TANK, TANK))
        emu.uc.mem_write(emu.state + FISH + 2 * TANK, stock)                    # moved back out
        f = block[9 * REC:10 * REC]
        health, disease, food = struct.unpack_from("<iii", f, F_HEALTH)
        self.assertEqual((health, disease), (100, 0))
        self.assertIn(food, (99, 100))


# ------------------------------------------------------------------ Plant Tycoon

PLANT_STATE = 0x60000
POT0, POT_SIZE = 0x2188, 0x5600
P_CLOCK, P_BANK, P_LAST_AGE, P_AGE, P_WATER, P_HEALTH, P_PESTS, P_DIED = 0x04, 0x08, 0x0C, 0x10, 0x20, 0x24, 0x28, 0x3C
P_PLANTED, P_FOLIAGE, P_FLOWER, P_AGE7 = 0x38, 0x4C, 0x50, 0x9C
S_CASH, S_PLANT_DIFFICULTY, S_PLANT_SPEED, S_PLANTS_CURED = 0x217C, 0x518, 0x534, 0x40
UNIT = 600                                       # seconds per age unit at speed 10
PLANT_NOW = 5_000_000
SPRINKLERS_AT, PLANT_HEALER_AT = (430, 140), (680, 150)


@_needs(PLANT_EXE)
class PlantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_plant_upgrades", ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll",
            Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def owned(self, emu) -> tuple[int, int]:
        raw = bytes(emu.uc.mem_read(emu.sym("_auto_owned"), 2))
        return raw[0], raw[1]

    # ------------------------------------------------------------ the store
    def store(self, cash: int, free: bool = False, answer_yes: bool = True):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.hook_printf()

        def message(e):
            e.calls.append(("MessageBoxW", e.wstring(e.arg(2)), e.wstring(e.arg(1))))
            return 6 if answer_yes else 7
        emu.hook_import("MessageBoxW", message, 16)
        for name, pop in (("GetActiveWindow", 0), ("GetForegroundWindow", 0), ("GetModuleHandleW", 4),
                          ("GetProcAddress", 8)):
            emu.hook_import(name, emu.record(name), pop)
        emu.hook(0x0044A580, emu.record("sound"), 4)
        emu.hook(0x0044E894, lambda e: e.alloc(e.arg(0)), 0)
        emu.hook(0x00409870, lambda e: (e.calls.append(("tip", e.cstring(e.arg(3)).decode("latin-1"))), 0)[1], 0x1C)
        emu.hook(0x00409AA0, lambda e: (e.calls.append(("tip", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 0x10)
        emu.hook(0x0040B400, emu.record("control"), 4)
        emu.hook(0x00432E90, emu.record("dialog"), 4)
        emu.hook(0x00401C90, emu.record("run"), 8)
        emu.hook(0x004307A0, emu.record("dtor"), 0)
        state = emu.alloc(PLANT_STATE)
        scene = emu.alloc(0x400)
        emu.write32(scene + 0x1BC, state)
        emu.write32(state + S_CASH, cash)
        emu.write8(emu.sym("_free_upgrades"), int(free))
        emu.state, emu.scene = state, scene
        return emu

    def click(self, emu, at: tuple[int, int]) -> None:
        emu.write32(emu.sym("_upgrades_view"), 1)
        emu.call(emu.sym("_on_click"), emu.scene, *at)

    def cash(self, emu) -> int:
        return emu.read32(emu.state + S_CASH)

    def asked(self, emu) -> list[tuple[str, str]]:
        return [c[1:] for c in emu.calls if c[0] == "MessageBoxW"]

    def test_buying_with_the_yes_no(self) -> None:
        for at, k, name, words in ((SPRINKLERS_AT, 0, "Automatic Sprinklers", SPRINKLERS_TEXT),
                                   (PLANT_HEALER_AT, 1, "Auto-Healer", PLANT_HEALER_TEXT)):
            emu = self.store(10005)
            self.click(emu, at)
            self.assertEqual(self.asked(emu)[-1], (name, f"Buy {name} for $10000?\n\n{words}"))   # the owner's words
            self.assertEqual(self.cash(emu), 5)
            self.assertEqual(self.owned(emu)[k], 1)
            emu = self.store(10005, answer_yes=False)
            self.click(emu, at)
            self.assertEqual((self.cash(emu), self.owned(emu)), (10005, (0, 0)))
            emu = self.store(9999)
            self.click(emu, at)
            self.assertEqual(self.asked(emu)[-1], (name, f"You can't afford to buy this yet! {name} costs $10,000."))
            self.assertEqual(self.owned(emu), (0, 0))
            emu = self.store(0, free=True)
            self.click(emu, at)
            self.assertEqual(self.asked(emu)[-1][1].splitlines()[0], f"Buy {name} for $0?")
            self.assertEqual((self.cash(emu), self.owned(emu)[k]), (0, 1))

    def test_unpurchase_and_buying_again(self) -> None:
        for at, k, name in ((SPRINKLERS_AT, 0, "Automatic Sprinklers"), (PLANT_HEALER_AT, 1, "Auto-Healer")):
            emu = self.store(10000, answer_yes=False)
            emu.uc.mem_write(emu.sym("_auto_owned") + k, b"\x01")
            self.click(emu, at)                                                 # No: nothing changes
            self.assertEqual(self.asked(emu)[-1], (name, f"Unpurchase {name}? It switches off. There is no refund, "
                                                         "and buying it again costs the full price."))
            self.assertEqual((self.owned(emu)[k], self.cash(emu)), (1, 10000))
            emu = self.store(10000)
            emu.uc.mem_write(emu.sym("_auto_owned") + k, b"\x01")
            self.click(emu, at)                                                 # Yes: off, no refund
            self.assertEqual((self.owned(emu)[k], self.cash(emu)), (0, 10000))
            self.click(emu, at)                                                 # bought again: full price
            self.assertEqual((self.owned(emu)[k], self.cash(emu)), (1, 0))
            emu = self.store(0, free=True)
            emu.uc.mem_write(emu.sym("_auto_owned") + k, b"\x01")
            self.click(emu, at)
            self.click(emu, at)
            self.assertEqual((self.owned(emu)[k], self.cash(emu)), (1, 0))

    def test_tooltips_and_their_glyphs(self) -> None:
        import test_store_extras
        font = test_store_extras.plant_font()
        emu = self.store(0)
        emu.call(emu.sym("_auto_make_tips"), emu.scene)
        tips = [c[1] for c in emu.calls if c[0] == "tip"]
        self.assertEqual(tips, ["Automatic Sprinklers\nPrice: $ 10000", "Auto-Healer\nPrice: $ 10000"])
        emu.uc.mem_write(emu.sym("_auto_owned"), b"\x01\x01")
        emu.calls.clear()
        emu.call(emu.sym("_auto_set_tips"), 1)
        tips = [c[1] for c in emu.calls if c[0] == "tip"]
        self.assertEqual(tips, ["Automatic Sprinklers\nOwned, click to unpurchase",
                                "Auto-Healer\nOwned, click to unpurchase"])
        for text in tips:
            self.assertLessEqual(set(text) - {"\n"}, font, text)

    def test_ownership_round_trip_new_game_delete_and_unreadable(self) -> None:
        from test_ds_store_animals import Files
        emu = self.store(0)
        files = Files(emu)
        emu.hook_import("LoadLibraryW", lambda e: 0x7000, 4)
        emu.hook_import("GetModuleFileNameW",
                        lambda e: files._put(e.arg(1), "C:\\Game\\Plant Tycoon.exe"), 12)
        path = "C:\\Docs\\LDW\\Plant Tycoon\\Plant Tycoon Fix Patcher Data\\Auto Upgrades 2.dat"
        emu.uc.mem_write(emu.sym("_auto_owned"), b"\x01\x00")
        emu.call(emu.sym("_auto_save"), 2)
        self.assertEqual(files.files[path], struct.pack("<4I", 0x55415050, 1, 1, 0))
        self.assertNotIn(path + ".tmp", files.files)
        emu.uc.mem_write(emu.sym("_auto_owned"), b"\x00\x01")
        emu.call(emu.sym("_auto_load"), 2)
        self.assertEqual(self.owned(emu), (1, 0))
        emu.call(emu.sym("_auto_load"), 5)
        self.assertEqual(self.owned(emu), (0, 0))
        emu.call(emu.sym("_auto_load"), 2)
        emu.call(emu.sym("_auto_new_game"))
        self.assertEqual(self.owned(emu), (0, 0))
        emu.call(emu.sym("_auto_delete"), 2)
        self.assertNotIn(path, files.files)
        files.files[path] = b"garbage!"
        emu.uc.mem_write(emu.sym("_auto_owned"), b"\x01\x01")
        emu.call(emu.sym("_auto_load"), 2)
        self.assertEqual(self.owned(emu), (0, 0))
        self.assertIn(path + ".unreadable", files.files)

    # ------------------------------------------------------------ the effect
    def greenhouse(self, owned: tuple[int, int], rolls=None):
        """The game's plant update (0x42DF80) on a real plant vtable, with the DLL's hooks written in."""
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.hook_printf()
        emu.rolls = dict(rolls or {})
        emu.seen = []

        def random(e):
            bound = e.arg(0)
            queue = e.rolls.get(bound)
            return queue.pop(0) if queue else bound - 1                          # the highest roll: nothing happens
        emu.hook(0x004033B0, random, 0)
        emu.hook(0x0042D3E0, lambda e: 1, 0)                                     # flowering: not reached (age < 21)
        emu.hook(0x0042DEC0, lambda e: 0, 0)
        emu.hook(0x0041D830, lambda e: 0, 8)
        emu.hook(0x0041EB00, lambda e: 0, 8)
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)                      # no Extra Greenhouses.dll
        state = emu.alloc(PLANT_STATE)
        emu.write32(state + S_PLANT_SPEED, 10)
        emu.write32(state + S_PLANT_DIFFICULTY, 1)
        jump(emu, 0x0042E134, emu.sym("_stub_unit_top"), 5)
        jump(emu, 0x0042E2DF, emu.sym("_stub_units_done"), 10)
        emu.uc.mem_write(emu.sym("_auto_owned"), bytes(owned))
        emu.state = state
        return emu

    def plant(self, emu, pot: int, units: int, age: float = 10.0, water: int = 150, health: int = 60,
              pests: int = 0, foliage: int = 1, flower: int = 1) -> int:
        """A live plant in `pot` (any record: a state pot, or an extra greenhouse's), `units` behind."""
        emu.write32(pot + P_CLOCK, PLANT_NOW - units * UNIT)
        emu.write32(pot + P_BANK, 0)
        emu.uc.mem_write(pot + P_LAST_AGE, struct.pack("<ff", age, age))
        for field, value in ((P_WATER, water), (P_HEALTH, health), (P_PESTS, pests), (P_FOLIAGE, foliage),
                             (P_FLOWER, flower), (P_DIED, 0)):
            emu.write32(pot + field, value)
        emu.write8(pot + P_PLANTED, 1)
        emu.write8(pot + P_AGE7, 1)                                              # past the age-7 branch roll
        obj = emu.alloc(0x20)
        emu.write32(obj, 0x0046943C)                                             # a stock plant vtable
        emu.write32(obj + 8, pot)
        emu.write32(obj + 0xC, emu.state)
        return obj

    def run_update(self, emu, obj: int) -> None:
        emu.call(0x0042DF80, PLANT_NOW, ecx=obj)

    def watch_rolls(self, emu, pot: int) -> None:
        """The water the infestation roll reads at the top of each unit (0x42CA80)."""
        emu.hook(0x0042CA80, lambda e: (e.seen.append(e.read32(pot + P_WATER, signed=True)), 0)[1], 0)

    def read(self, emu, pot: int, field: int) -> int:
        return emu.read32(pot + field, signed=True)

    def test_sprinklers_keep_the_best_water_through_a_catch_up(self) -> None:
        for where in ("greenhouse 1", "extra greenhouse"):
            emu = self.greenhouse((1, 0))
            pot = emu.state + POT0 + 6 * POT_SIZE if where == "greenhouse 1" else emu.alloc(POT_SIZE)
            obj = self.plant(emu, pot, units=40, water=1000)                     # watered over the top by hand
            self.watch_rolls(emu, pot)
            self.run_update(emu, obj)
            self.assertEqual(len(emu.seen), 40, where)                           # every unit played
            self.assertEqual(set(emu.seen), {800}, where)                        # never above 900, never dry
            self.assertEqual(self.read(emu, pot, P_WATER), 800, where)
            self.assertEqual(self.read(emu, pot, P_HEALTH), 100, where)          # class A, Common soil: +1 a unit
        stock = self.greenhouse((0, 0))
        pot = stock.state + POT0
        obj = self.plant(stock, pot, units=40, water=150)
        self.run_update(stock, obj)
        self.assertEqual(self.read(stock, pot, P_WATER), 0)                     # stock: dry
        self.assertLess(self.read(stock, pot, P_HEALTH), 60)

    def test_the_healer_clears_pests_and_keeps_full_health(self) -> None:
        emu = self.greenhouse((0, 1), rolls={10000: [0] * 30})                  # infested every unit
        pot = emu.state + POT0
        obj = self.plant(emu, pot, units=30, water=500, health=40, pests=1, foliage=19, flower=19)   # class D
        self.run_update(emu, obj)
        self.assertEqual((self.read(emu, pot, P_PESTS), self.read(emu, pot, P_HEALTH)), (0, 100))
        self.assertEqual(emu.read32(emu.state + S_PLANTS_CURED), 31)           # the first, then each unit's
        self.assertEqual(self.read(emu, pot, P_WATER), 500 - 30 * 7)            # the sprinklers are not bought
        stock = self.greenhouse((0, 0), rolls={10000: [0] * 30})
        pot = stock.state + POT0
        obj = self.plant(stock, pot, units=30, water=500, health=40, pests=1, foliage=19, flower=19)
        self.run_update(stock, obj)
        self.assertEqual(self.read(stock, pot, P_HEALTH), 0)                    # stock: dead

    def test_a_dead_plant_is_never_revived(self) -> None:
        emu = self.greenhouse((1, 1))
        pot = emu.state + POT0 + 3 * POT_SIZE
        obj = self.plant(emu, pot, units=20, water=20, health=0, pests=1)
        emu.write32(pot + P_DIED, 1)
        before = bytes(emu.uc.mem_read(pot, POT_SIZE))
        self.run_update(emu, obj)
        after = bytearray(emu.uc.mem_read(pot, POT_SIZE))
        self.assertEqual(bytes(after), before)
        emu.call(emu.sym("_auto_tend_all"), emu.state)                          # nor at a purchase
        self.assertEqual(bytes(emu.uc.mem_read(pot, POT_SIZE)), before)

    def test_a_plant_that_dies_of_old_age_mid_catch_up_stays_as_stock_leaves_it(self) -> None:
        results = []
        for owned in ((0, 0), (1, 1)):
            emu = self.greenhouse(owned, rolls={1000: [999, 999, 0]})          # old age on the third unit
            pot = emu.state + POT0
            obj = self.plant(emu, pot, units=8, age=1800.0, water=500, health=100)
            self.run_update(emu, obj)
            results.append((self.read(emu, pot, P_HEALTH), self.read(emu, pot, P_DIED)))
        self.assertEqual(results[0][1], 1)
        self.assertEqual(results[1], results[0])                               # the healer never lifted it

    def test_a_purchase_reaches_every_greenhouse_off_screen(self) -> None:
        emu = self.greenhouse((1, 1))
        banks = {(g, k): (emu.state + POT0 + k * POT_SIZE if g == 0 else emu.alloc(POT_SIZE))
                 for g in range(6) for k in range(15)}
        for (g, k), pot in banks.items():
            emu.write32(pot + P_FOLIAGE, 1 + k)
            emu.write8(pot + P_PLANTED, 1)
            for field, value in ((P_HEALTH, 30), (P_PESTS, 1), (P_WATER, 950)):
                emu.write32(pot + field, value)
        pot_fn, owned_fn = emu.thunk(), emu.thunk()
        emu.hook(pot_fn, lambda e: banks.get((e.arg(0), e.arg(1)), 0), 0)
        emu.hook(owned_fn, lambda e: 5, 0)
        exports = {b"FtfpExtraGreenhousesPot": pot_fn, b"FtfpExtraGreenhousesOwned": owned_fn}
        emu.hook_import("GetModuleHandleW", lambda e: 0x6C000000 if e.wstring(e.arg(0)) == "Extra Greenhouses.dll" else 0, 4)
        emu.hook_import("GetProcAddress", lambda e: exports.get(e.cstring(e.arg(1)), 0), 8)
        emu.call(emu.sym("_auto_tend_all"), emu.state)
        for place, pot in banks.items():
            self.assertEqual((self.read(emu, pot, P_HEALTH), self.read(emu, pot, P_PESTS),
                              self.read(emu, pot, P_WATER)), (100, 0, 800), place)
        self.assertEqual(emu.read32(emu.state + S_PLANTS_CURED), 90)


if __name__ == "__main__":
    unittest.main()
