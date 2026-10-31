"""The Revival Potion, ClonaFish, Revita-Seed and the Radioactive Plant Formula Bomb.

Fish Tycoon (DS Store Items, the Upgrades page): the Revival Potion (item 30, $10,000, 3 doses)
and ClonaFish (item 31, $2,500, 3 doses), supply-slot chemicals used like the stock Growth
Hormone. Plant Tycoon (Store Upgrades and Items, the Upgrades view): the Revival Potion
(chemical 37, $10,000, 3 doses), Revita-Seed (38, $2,500, 3 doses) and the Formula Bomb
(39, $30,000, 3 doses). The owner's spec is docs/revival-potion-spec.md.

The emulation tests run each DLL's own code and the vanilla executables' code (the Fish
use handler 0x420B70, AddFish 0x419C50) in Unicorn (tests/store_emulator.py).
"""

from __future__ import annotations

import importlib.util
import io
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import tycoon_fix_patcher as combined  # noqa: E402

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
FISH_IMAGES = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
PLANT_SHEET = ROOT / "assets" / "plant_tycoon_upgrades" / "Images" / "Chemicals_Grid_upgrades.png"
FISH_ART = {"ITEM_REVIVAL_POTION.png": (48, 65), "TOOL_REVIVAL_POTION.png": (24, 35),
            "TOOL_dropper_REVIVAL.png": (21, 21), "ITEM_CLONAFISH.png": (48, 65), "TOOL_CLONAFISH.png": (24, 35),
            "TOOL_dropper_CLONAFISH.png": (21, 21)}

REVIVAL, CLONA = 30, 31
SPR = {REVIVAL: (238, 239, 240), CLONA: (241, 242, 243)}       # store picture, shelf, cursor
S_DIFFICULTY, S_CURED, S_SPENT, S_TANK, S_MONEY = 0x14, 0x34, 0x24, 0x384, 0x38C
SLOT3 = 0x2B8 + 2 * 0x1C
FISH, TANK, REC = 0x390, 0x51EC, 0x288
F_LIVE, F_BANK, F_LAST_AGE, F_AGE, F_DUE, F_MARK = 0x00, 0x04, 0x08, 0x0C, 0x10, 0x14
F_HEALTH, F_DISEASE, F_FOOD, F_BODY, F_FIN = 0x3C, 0x40, 0x44, 0x4C, 0x50
NOW = 4321                                                       # the state's clock (0x4032C0)
CELLS = {REVIVAL: (725, 125), CLONA: (86, 200)}


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def visible_height(path: Path) -> int:
    from PIL import Image
    box = Image.open(path).convert("RGBA").getchannel("A").getbbox()
    return box[3] - box[1]


class ArtAndManifestTests(unittest.TestCase):
    def test_the_fish_art_is_pinned_with_the_store(self) -> None:
        store = combined.patch_settings("fish")["ds_store"]
        destinations = {f["destination"] for f in store["companion"]["files"]}
        for name, size in FISH_ART.items():
            self.assertIn(f"Images/{name}", destinations)
            self.assertEqual(png_size(FISH_IMAGES / name), size, name)          # the stock pictures' sizes
        for text in ("Revival Potion ($10,000, 3 doses)", "ClonaFish ($2,500, 3 doses)", "every live fish", "doubling"):
            self.assertIn(text, store["description"])
        free = combined.patch_settings("fish")["free_upgrades"]["description"]
        self.assertIn("the Revival Potion ($10,000), ClonaFish ($2,500)", free)

    def test_the_plant_art_and_texts_are_pinned(self) -> None:
        upgrades = combined.patch_settings("plant")["plant_upgrades"]
        self.assertIn("Images/Chemicals_Grid_upgrades.png", {f["destination"] for f in upgrades["companion"]["files"]})
        for text in ("Revival Potion", "Revita-Seed", "$2,500", "Radioactive Plant Formula Bomb", "$30,000",
                     "every live plant in the greenhouse"):
            self.assertIn(text, upgrades["description"])
        self.assertEqual(png_size(PLANT_SHEET), (140, 21 * 70))     # rows 10-12 new; 13 Time Warp, 14 Add Money,
                                                                     # 15 the Extra Greenhouse, 16-17 the Auto items
        free = combined.patch_settings("plant")["free_upgrades"]["description"]
        for text in ("the Revival Potion ($10,000)", "Revita-Seed ($2,500)", "the Formula Bomb ($30,000)"):
            self.assertIn(text, free)

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "needs Pillow")
    def test_the_icons_match_their_neighbours_visible_size(self) -> None:
        # The owner: not cell-sized. The stock Growth Hormone shows 57 px in the store and 31 on the shelf.
        for name in ("ITEM_REVIVAL_POTION.png", "ITEM_CLONAFISH.png", "ITEM_RADIOACTIVE_GROWTHHORMONE.png"):
            self.assertEqual(visible_height(FISH_IMAGES / name), 57, name)
        for name in ("TOOL_REVIVAL_POTION.png", "TOOL_CLONAFISH.png", "TOOL_RADIOACTIVE_GROWTHHORMONE.png"):
            self.assertEqual(visible_height(FISH_IMAGES / name), 31, name)
        from PIL import Image
        sheet = Image.open(PLANT_SHEET).convert("RGBA")
        upright = lambda row: sheet.crop((0, row * 70, 70, row * 70 + 70)).getchannel("A").getbbox()
        for row in (10, 11):                                         # as tall as the formula (row 9), same bottom
            self.assertEqual((upright(row)[1], upright(row)[3]), (upright(9)[1], upright(9)[3]), row)
        self.assertEqual(upright(12), upright(5))                    # the bomb: the stock Fertilizer Bomb's shape

    @unittest.skipUnless(E is not None and FISH_EXE is not None and FISH_EXE.is_file()
                         and PLANT_EXE is not None and PLANT_EXE.is_file(), "needs the vanilla games")
    def test_the_art_is_rebuilt_by_its_pinned_scripts(self) -> None:
        import numpy as np
        from PIL import Image
        import build_plant_upgrades_assets
        import build_potion_assets
        built = build_potion_assets.fish_pictures(FISH_EXE.parent)
        self.assertEqual(set(built), set(FISH_ART))
        for name, image in built.items():
            committed = np.asarray(Image.open(FISH_IMAGES / name).convert("RGBA"))
            self.assertTrue((np.asarray(image) == committed).all(), name)
        sheet = build_plant_upgrades_assets.formula_bottle(PLANT_EXE.parent / "Images")
        committed = Image.open(PLANT_SHEET).convert("RGBA")
        self.assertTrue((np.asarray(sheet) == np.asarray(committed)).all())
        # Rows 10 and 11 are the owner's own pictures: the amber flask and the teal bottle (revita_seed_source.png).
        stock = Image.open(PLANT_EXE.parent / "Images" / "Chemicals_Grid.png").convert("RGBA")
        for row, source in ((10, build_potion_assets.REVIVAL), (11, build_potion_assets.REVITA)):
            self.assertEqual(source.name, {10: "revival_potion_source.png", 11: "revita_seed_source.png"}[row])
            for column, cell in enumerate(build_potion_assets.plant_cells(source, stock)):
                part = committed.crop((column * 70, row * 70, column * 70 + 70, row * 70 + 70))
                self.assertTrue((np.asarray(cell) == np.asarray(part)).all(), (row, column))
        for preview in ("revival-potion-fish.png", "revival-potion-plant.png"):
            self.assertTrue((ROOT / "docs" / "images" / preview).is_file())

    def test_the_owner_icons_are_committed(self) -> None:
        self.assertEqual(png_size(ROOT / "assets" / "revival_potion" / "revival_potion_source.png"), (37, 67))
        self.assertEqual(png_size(ROOT / "assets" / "clonafish" / "clonafish_source.png"), (39, 65))
        self.assertEqual(png_size(ROOT / "assets" / "revita_seed" / "revita_seed_source.png"), (39, 65))


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


@_needs(FISH_EXE)
class FishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_ds_store", ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ the store
    def store(self, money: int, free: bool = False, universal: bool = False):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        emu.hook_import("GetTickCount", lambda e: 0, 0)
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)            # no Extra Tanks.dll loaded
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        emu.hook(0x004221A0, emu.record("dialog", args=1), 8)
        emu.hook(0x00401D00, emu.record("run", 0), 8)                            # Yes
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
        for name, on in (("_free_on", free), ("_page_upgrades", 1), ("_exotic_any_slot", universal)):
            emu.write32(emu.sym(name), int(on))
        emu.state, emu.scene = state, scene
        return emu

    def select(self, emu, item: int) -> None:
        emu.call(emu.sym("@on_mouse@20"), 3, *CELLS[item], ecx=emu.scene)

    def buy(self, emu, item: int) -> None:
        self.select(emu, item)
        emu.call(emu.sym("_buy"), emu.scene)

    def slot(self, emu, k: int = 2) -> tuple[int, ...]:
        return struct.unpack("<6i", emu.uc.mem_read(emu.state + 0x2B8 + k * 0x1C, 24))

    def shown(self, emu, item: int) -> list[str]:
        self.select(emu, item)
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        return [c[1] for c in emu.calls if c[0] == "text"]

    def test_names_descriptions_and_prices(self) -> None:
        for item, name, words, price in (
                (REVIVAL, "Revival Potion", "This magical potion instantly revives dead fish and restores them to "
                 "full health. Contains 3 doses.", 10000),
                (CLONA, "ClonaFish", "A wonder drug that instantly clones all fish in the tank. Make sure "
                 "there's enough space in the tank! Contains 3 doses.", 2500)):
            texts = self.shown(self.store(0), item)
            self.assertIn(name, texts)
            self.assertIn(words, [t.replace("\n", " ") for t in texts])                  # the owner's exact words
            self.assertEqual([t for t in texts if t.startswith("Price:")][-1], f"Price:  ${price}")
            texts = self.shown(self.store(0, free=True), item)
            self.assertEqual([t for t in texts if t.startswith("Price:")][-1], "Price:  $0")

    def test_bought_into_slot_3_with_3_doses_and_free_upgrades_take_nothing(self) -> None:
        for item, price in ((REVIVAL, 10000), (CLONA, 2500)):
            emu = self.store(price + 7)
            self.buy(emu, item)
            self.assertEqual(self.slot(emu), (item, 1, 3, SPR[item][1], SPR[item][2], 2 * 0x30 + 0x1E))
            self.assertEqual((emu.read32(emu.state + S_MONEY), emu.read32(emu.state + S_SPENT)), (7, price))
            emu = self.store(price - 1)
            self.buy(emu, item)
            self.assertIn(("hint", (2,)), emu.calls)                     # "You can't afford to buy this yet!"
            self.assertEqual(self.slot(emu), (0,) * 6)
            emu = self.store(0, free=True)
            self.buy(emu, item)
            self.assertEqual(self.slot(emu)[:3], (item, 1, 3))
            self.assertEqual((emu.read32(emu.state + S_MONEY), emu.read32(emu.state + S_SPENT)), (0, 0))

    def test_universal_slots_stack_3_doses_per_purchase(self) -> None:
        for item in (REVIVAL, CLONA):
            emu = self.store(30000, universal=True)
            self.buy(emu, item)
            self.buy(emu, item)
            self.assertEqual(self.slot(emu, 1), (item, 1, 6, SPR[item][1], SPR[item][2], 1 * 0x30 + 0x1E))

    def run_stub(self, name: str, targets: tuple[int, ...], **regs) -> int:
        from unicorn import x86_const as X
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        reached = []

        def stop(e, at):
            reached.append(at)
            e.uc.emu_stop()
            return 0
        for at in targets:
            emu.hook(at, lambda e, at=at: stop(e, at))
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        for reg, value in regs.items():
            emu.uc.reg_write(getattr(X, f"UC_X86_REG_{reg.upper()}"), value)
        emu.uc.emu_start(emu.sym(name), 0, count=50)
        return reached[0]

    def test_buying_a_stock_chemical_over_them_asks_to_replace(self) -> None:
        for item in (REVIVAL, CLONA):
            self.assertEqual(self.run_stub("_stub_chem_confirm", (0x428191, 0x4281D6), ecx=SPR[item][1]), 0x428191)

    # ------------------------------------------------------------ a dose
    def tank(self, item: int, slots: int = 21, last_tank: int = 3):
        """The vanilla use handler (0x420B70) with the DLL's chemical switch at 0x420E6F, slot #3 picked."""
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        stub = emu.sym("_stub_chem_use")
        emu.uc.mem_write(0x420E6F, b"\xE9" + struct.pack("<i", stub - 0x420E74) + b"\x90" * 7)
        emu.uc.mem_write(0x4206B3, bytes([slots]))                         # the update's slots (Bigger tanks: 26)
        emu.uc.mem_write(0x419C74, bytes([slots]))                         # AddFish's limit, rewritten with it
        emu.uc.mem_write(0x4206C7, bytes([last_tank]))                     # the update's last tank
        emu.hook(0x00413B00, emu.record("effect", args=3), 12)
        emu.hook(0x004251A0, lambda e: 0, 4)
        emu.hook(0x0040AE20, emu.record("play"), 4)
        emu.hook(0x00413BD0, lambda e: 0, 4)                               # no fish on screen: no sparkles
        emu.hook(0x004020D0, lambda e: 5000, 0)
        emu.hook(0x00403240, lambda e: 0, 0)
        emu.hook(0x004032C0, lambda e: NOW, 0)
        emu.hook(0x00415E70, emu.record("view sync", args=1), 4)
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        state, impl = emu.alloc(0x50000), emu.alloc(0x100)
        for at in range(0, 0x50000, 4):                                    # every field: a pattern
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        emu.write32(state + S_TANK, 0)
        emu.uc.mem_write(state + SLOT3, struct.pack("<6i", item, 1, 3, SPR[item][1], SPR[item][2], 0x7E))
        for tank in range(last_tank + 1):                                  # every record empty
            for slot in range(31):
                emu.write32(state + FISH + tank * TANK + slot * REC, 0)
        emu.write32(impl + 0x1C, 2)
        emu.write32(impl + 0x34, state)
        emu.write32(impl + 0x3C, emu.alloc(0x40))
        emu.write32(impl + 0x44, emu.alloc(0x40))
        emu.write32(impl + 0x4C, emu.alloc(0x40))
        for at, value in ((0xA8, 0), (0xAC, 0), (0xB0, 800), (0xB4, 600)):
            emu.write32(impl + at, value)
        emu.state, emu.impl = state, impl
        return emu

    def at(self, emu, slot: int, tank: int = 0) -> int:
        return emu.state + FISH + tank * TANK + slot * REC

    def fish(self, emu, slot: int, body: int, fin: int, health: int = 60, tank: int = 0, extra=None) -> int:
        """A record: its pattern bytes stay (every field the game keeps), with these set."""
        at = self.at(emu, slot, tank)
        values = {F_LIVE: 1234, F_BANK: 55, F_AGE: 30, F_LAST_AGE: 30, F_DUE: 0, F_MARK: 0, F_HEALTH: health,
                  F_DISEASE: 0, F_FOOD: 40, F_BODY: body, F_FIN: fin}
        values.update(extra or {})
        for field, value in values.items():
            emu.write32(at + field, value)
        return at

    def dose(self, emu) -> None:
        emu.write32(emu.impl + 0x1C, 2)
        emu.call(0x00420B70, 400, 300, ecx=emu.impl)

    def record(self, emu, at: int) -> bytes:
        return bytes(emu.uc.mem_read(at, REC))

    def slot_record(self, emu) -> tuple[int, ...]:
        return struct.unpack("<3i", emu.uc.mem_read(emu.state + SLOT3, 12))

    # --- the Revival Potion
    def test_revival_restores_exactly_the_alive_state(self) -> None:
        emu = self.tank(REVIVAL)
        dead = self.fish(emu, 3, 4, 6, health=0, extra={F_AGE: 57, F_LAST_AGE: 57, F_DISEASE: 2, F_FOOD: 3, F_DUE: 60})
        live = self.fish(emu, 0, 1, 1, health=35)
        other = self.fish(emu, 3, 4, 6, health=0, tank=1)                  # another tank
        animal = self.fish(emu, 26, 22, 30, health=0, extra={F_MARK: 0x41435446})   # a store animal's slot
        before = bytes(emu.uc.mem_read(emu.state, 0x50000))
        self.dose(emu)
        expected = bytearray(before[dead - emu.state:dead - emu.state + REC])
        struct.pack_into("<i", expected, F_HEALTH, 100)                    # full health
        struct.pack_into("<i", expected, F_LIVE, NOW)                      # its clock: now, as the update sets it
        self.assertEqual(self.record(emu, dead), bytes(expected))          # age, food, sickness, pregnancy kept
        changed = bytearray(before)
        changed[dead - emu.state:dead - emu.state + REC] = expected
        struct.pack_into("<i", changed, SLOT3 + 8, 2)                      # one dose spent
        self.assertEqual(bytes(emu.uc.mem_read(emu.state, 0x50000)), bytes(changed))   # nothing else changed
        for at in (live, other, animal):
            self.assertEqual(self.record(emu, at), before[at - emu.state:at - emu.state + REC])

    def test_revival_reaches_every_slot_the_update_reaches(self) -> None:
        for slots in (21, 26, 30):                                         # stock, Bigger tanks, 30 per tank
            emu = self.tank(REVIVAL, slots=slots)
            last = self.fish(emu, slots - 1, 2, 2, health=0)
            past = self.fish(emu, slots, 2, 2, health=0) if slots < 31 else None
            self.dose(emu)
            self.assertEqual(emu.read32(last + F_HEALTH), 100, slots)
            if past is not None and slots < 26:
                self.assertEqual(emu.read32(past + F_HEALTH), 0, slots)

    def test_revival_in_an_extra_tank(self) -> None:
        emu = self.tank(REVIVAL, last_tank=6)                              # tanks read from the update's bound
        emu.write32(emu.state + S_TANK, 6)
        dead = self.fish(emu, 0, 2, 2, health=0, tank=6)
        self.dose(emu)
        self.assertEqual(emu.read32(dead + F_HEALTH), 100)
        emu = self.tank(REVIVAL)
        emu.write32(emu.state + S_TANK, 6)                                 # past the game's last tank: nothing
        dead = self.fish(emu, 0, 2, 2, health=0, tank=6)
        self.dose(emu)
        self.assertEqual(emu.read32(dead + F_HEALTH), 0)

    def test_doses_count_down_and_the_slot_empties(self) -> None:
        for item in (REVIVAL, CLONA):
            emu = self.tank(item)
            for left in (2, 1):
                self.dose(emu)
                self.assertEqual(self.slot_record(emu), (item, 1, left))
            self.dose(emu)
            self.assertEqual(self.slot_record(emu), (0, 0, 0))
            self.assertEqual(emu.read32(emu.impl + 0x1C), 0x63)

    # --- ClonaFish: every live fish, once a dose (the owner, 2026-10-31: "it should double all fish")
    def live_count(self, emu, tank: int = 0) -> int:
        return sum(1 for s in range(31) if emu.read32(self.at(emu, s, tank)) != 0)

    def test_clonafish_doubles_the_tank_with_exact_copies(self) -> None:
        emu = self.tank(CLONA)
        same = [self.fish(emu, s, 6, 6, extra={F_DUE: 44, F_DISEASE: 1}) for s in (0, 2, 4)]   # 3 of one species
        originals = [self.record(emu, at) for at in same]
        self.dose(emu)
        self.assertEqual(self.live_count(emu), 6)                          # 3 become 6
        self.assertEqual([self.record(emu, self.at(emu, s)) for s in (1, 3, 5)], originals)   # first free records
        self.assertIn(("view sync", (self.at(emu, 0),)), emu.calls)
        self.assertNotIn("hint", [c[0] for c in emu.calls])
        self.dose(emu)
        self.assertEqual(self.live_count(emu), 12)                         # then 12
        self.dose(emu)
        self.assertEqual(self.live_count(emu), 21)                         # then full (21 of 24)
        self.assertEqual(self.slot_record(emu), (0, 0, 0))                 # three doses used

    def test_this_doses_clones_are_not_cloned_again_by_it(self) -> None:
        emu = self.tank(CLONA)
        self.fish(emu, 0, 1, 2)
        self.dose(emu)
        self.assertEqual(self.live_count(emu), 2)                          # 1 + 1, not 1 + 1 + 1 + ...

    def test_clonafish_skips_dead_fish_animals_and_seahorses(self) -> None:
        emu = self.tank(CLONA)
        live = self.fish(emu, 0, 3, 5)
        self.fish(emu, 1, 9, 9, health=0)                                  # dead: never cloned
        self.fish(emu, 2, 22, 22)                                          # a seahorse-type record: never
        self.fish(emu, 26, 7, 7, extra={F_MARK: 0x41435446})               # a store animal: never
        self.dose(emu)
        self.assertEqual(self.record(emu, self.at(emu, 3)), self.record(emu, live))
        self.assertEqual(emu.read32(self.at(emu, 4)), 0)                   # nothing else added

    def test_clonafish_stops_when_the_tank_is_full(self) -> None:
        emu = self.tank(CLONA)
        for slot in range(19):
            self.fish(emu, slot, slot, 1)                                  # 19 fish, 2 free records
        firsts = [self.record(emu, self.at(emu, s)) for s in (0, 1)]
        self.dose(emu)
        self.assertEqual([self.record(emu, self.at(emu, s)) for s in (19, 20)], firsts)   # slot order; the rest get none
        self.assertEqual(emu.read32(self.at(emu, 21)), 0)
        self.assertNotIn("hint", [c[0] for c in emu.calls])                # something was cloned
        self.assertEqual(self.slot_record(emu)[2], 2)                      # the dose is spent

    def test_a_full_tank_shows_the_games_tank_is_full(self) -> None:
        emu = self.tank(CLONA)
        for slot in range(21):
            self.fish(emu, slot, 1, 1)                                     # 21 fish, no room
        before = bytes(emu.uc.mem_read(self.at(emu, 0), 31 * REC))
        self.dose(emu)
        self.assertIn(("hint", (6,)), emu.calls)                           # "The tank is full!"
        self.assertEqual(bytes(emu.uc.mem_read(self.at(emu, 0), 31 * REC)), before)
        emu = self.tank(CLONA)                                             # no fish at all: no message
        self.dose(emu)
        self.assertNotIn("hint", [c[0] for c in emu.calls])

    def test_clonafish_with_30_per_tank_and_in_tanks_4_to_6(self) -> None:
        emu = self.tank(CLONA, slots=30)
        for slot in range(15):
            self.fish(emu, slot, 10, 10)
        self.dose(emu)
        self.assertEqual(self.live_count(emu), 30)                         # 15 doubled into slots 15-29
        for tank in (4, 5, 6):
            emu = self.tank(CLONA, slots=30, last_tank=6)
            emu.write32(emu.state + S_TANK, tank)
            original = self.record(emu, self.fish(emu, 28, 1, 2, tank=tank))
            self.fish(emu, 0, 1, 2, tank=tank)
            self.dose(emu)
            self.assertEqual(self.live_count(emu, tank), 4, tank)
            self.assertEqual(self.record(emu, self.at(emu, 2, tank=tank)), original, tank)
            self.assertEqual(self.live_count(emu, 0), 0, tank)             # the other tanks are untouched

PLANT_STATE = 0x60000
POT0, POT_SIZE = 0x2188, 0x5600


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

    def greenhouse(self, difficulty: int = 1, bonus: int = 0):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.hook_printf()
        state, greenhouse, plants = emu.alloc(PLANT_STATE), emu.alloc(0x200), emu.alloc(0x40)
        for at in range(0, PLANT_STATE, 4):
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        emu.write32(state + 0x518, difficulty)
        emu.write8(state + 0x2181, bonus)
        emu.write32(greenhouse + 0x68, state)
        emu.write32(greenhouse + 0x70, plants)
        emu.hook(0x00403430, lambda e: 777777, 0)                          # the game's clock
        emu.rolls = []
        emu.hook(0x004033B0, lambda e: (e.calls.append(("random", e.arg(0))), e.rolls.pop(0) if e.rolls else 0)[1], 0)

        def value(e):                                                      # the plant's value rule
            pot = e.read32(e.uc.reg_read(E.X.UC_X86_REG_ECX) + 8)
            e.calls.append(("value", pot))
            e.write32(pot + 0x48, 500)
            return 0
        emu.hook(0x0042DD80, value, 0)
        # Plant objects: vtable +0x44 add_flowers (recorded), +4 a shape table the DLL does not know, +8 the pot.
        add_flowers = emu.thunk()
        emu.hook(add_flowers, lambda e: (e.calls.append(("flowers", e.uc.reg_read(E.X.UC_X86_REG_ECX))), 0)[1], 8)
        vtable = emu.alloc(0x80)
        emu.write32(vtable + 0x44, add_flowers)
        emu.objects = {}

        def plant_at(e):
            row, col = e.arg(0), e.arg(1)
            if (row, col) not in e.objects:
                plant = e.alloc(0x20)
                e.write32(plant, vtable)
                e.write32(plant + 4, e.alloc(0x10))
                e.write32(plant + 8, state + POT0 + (row * 5 + col) * POT_SIZE)
                e.objects[(row, col)] = plant
            e.calls.append(("plant at", row, col))
            return e.objects[(row, col)]
        emu.hook(0x0042F6C0, plant_at, 8)
        emu.state, emu.gh = state, greenhouse
        return emu

    def pot(self, emu, k: int) -> int:
        return emu.state + POT0 + k * POT_SIZE

    def apply(self, emu, chemical: int, k: int, plant: int = 0) -> None:
        emu.call(emu.sym("_apply_chemical"), emu.gh, k % 5, k // 5, plant, chemical)

    def plant(self, emu, k: int) -> int:
        return emu.call(0x0042F6C0, k // 5, k % 5, ecx=emu.read32(emu.gh + 0x70))

    # --- the Revival Potion
    def test_revival_brings_a_dead_plant_back_at_full_health(self) -> None:
        emu = self.greenhouse(difficulty=1)
        pot = self.pot(emu, 7)
        for field, value in ((0x24, 0), (0x3C, 1), (0x44, 0), (0x48, 0), (0x04, 1000), (0x94, 3), (0x90, 2)):
            emu.write32(pot + field, value)
        plant = self.plant(emu, 7)
        before = bytes(emu.uc.mem_read(emu.state, PLANT_STATE))
        emu.rolls = [40]
        self.apply(emu, 37, 7, plant)
        expected = bytearray(before)
        for field, value in ((0x24, 100), (0x3C, 0), (0x04, 777777), (0x48, 500),
                             (0x44, 500 - 500 // 3 + 40)):                 # Normal: a third either way, Random(332) = 40
            struct.pack_into("<i", expected, pot - emu.state + field, value)
        self.assertEqual(bytes(emu.uc.mem_read(emu.state, PLANT_STATE)), bytes(expected))
        self.assertIn(("random", 2 * (500 // 3)), emu.calls)
        self.assertIn(("value", pot), emu.calls)

    def test_revival_prices_by_difficulty_and_the_bonus(self) -> None:
        for difficulty, bonus, expected in ((0, 0, 500 - 100), (2, 0, 500 - 250), (1, 1, 500 + 3 * 125)):
            emu = self.greenhouse(difficulty, bonus)
            pot = self.pot(emu, 0)
            emu.write32(pot + 0x24, 0)
            self.apply(emu, 37, 0, self.plant(emu, 0))
            self.assertEqual(emu.read32(pot + 0x44), expected, (difficulty, bonus))

    def test_revival_does_nothing_to_a_live_plant(self) -> None:
        emu = self.greenhouse()
        emu.write32(self.pot(emu, 3) + 0x24, 1)
        before = bytes(emu.uc.mem_read(emu.state, PLANT_STATE))
        self.apply(emu, 37, 3, self.plant(emu, 3))
        self.assertEqual(bytes(emu.uc.mem_read(emu.state, PLANT_STATE)), before)

    # --- Revita-Seed
    def test_revita_seed_resets_only_the_depleted_state(self) -> None:
        emu = self.greenhouse()
        pot = self.pot(emu, 4)
        emu.write8(pot + 0x6C, 1)
        for field, value in ((0x94, 5), (0x90, 0), (0x7C, 2), (0x24, 70)):
            emu.write32(pot + field, value)
        before = bytes(emu.uc.mem_read(emu.state, PLANT_STATE))
        self.apply(emu, 38, 4)
        expected = bytearray(before)
        expected[pot - emu.state + 0x6C] = 0                               # pollen is taken again
        for field in (0x90, 0x94, 0x7C):
            struct.pack_into("<i", expected, pot - emu.state + field, 0)   # as a fresh plant
        self.assertEqual(bytes(emu.uc.mem_read(emu.state, PLANT_STATE)), bytes(expected))

    def test_revita_seed_leaves_plants_that_are_not_depleted(self) -> None:
        for pollinated, taken in ((1, 4), (1, 0), (0, 5)):
            emu = self.greenhouse()
            pot = self.pot(emu, 0)
            emu.write8(pot + 0x6C, pollinated)
            emu.write32(pot + 0x94, taken)
            before = bytes(emu.uc.mem_read(emu.state, PLANT_STATE))
            self.apply(emu, 38, 0)
            self.assertEqual(bytes(emu.uc.mem_read(emu.state, PLANT_STATE)), before, (pollinated, taken))

    # --- the Formula Bomb
    def layout(self, emu, pots: int) -> list[int]:
        """Pots with a plant (+0x38) and their health; the live ones are the bomb's targets."""
        live = []
        for k in range(pots):
            pot = self.pot(emu, k)
            present, health = (k % 4 != 1), (0 if k % 5 == 3 else 20 + k)
            emu.write8(pot + 0x38, int(present))
            emu.write32(pot + 0x24, health)
            emu.write8(pot + 0x6C, k % 2)
            emu.write32(pot + 0x94, k % 3)
            if present and health > 0:
                live.append(k)
        return live

    def test_one_bomb_is_one_formula_dose_on_every_live_plant(self) -> None:
        bombed = self.greenhouse()
        live = self.layout(bombed, 15)
        self.apply(bombed, 39, 0)
        dosed = self.greenhouse()
        self.assertEqual(self.layout(dosed, 15), live)
        for k in live:
            self.apply(dosed, 36, k, self.plant(dosed, k))
        self.assertEqual(bytes(bombed.uc.mem_read(bombed.state, PLANT_STATE)),
                         bytes(dosed.uc.mem_read(dosed.state, PLANT_STATE)))
        flowered = lambda emu: sorted(k for (k, p) in emu.objects.items() if ("flowers", p) in emu.calls)
        self.assertEqual(flowered(bombed), flowered(dosed))
        self.assertEqual(len(flowered(bombed)), len(live))
        self.assertEqual(sorted((c[1], c[2]) for c in bombed.calls if c[0] == "plant at"),
                         sorted((k // 5, k % 5) for k in live))
        for k in range(15):                                                # the formula really ran
            self.assertEqual(bombed.read32(self.pot(bombed, k) + 0x24),
                             100 if k in live else (0 if k % 5 == 3 else 20 + k), k)

    def test_the_bomb_reaches_the_pots_the_stock_bomb_reaches(self) -> None:
        # The stock Fertilizer Bomb's own bounds (0x426D54: pots, 0x426D3A: columns), read: an
        # extra greenhouse shown in these pots, or a larger one, gets the same.
        emu = self.greenhouse()
        emu.uc.mem_write(0x426D56, struct.pack("<I", 20 * POT_SIZE))
        live = self.layout(emu, 20)
        self.apply(emu, 39, 0)
        self.assertIn(19, live)
        self.assertEqual(emu.read32(self.pot(emu, 19) + 0x24), 100)
        self.assertIn(("plant at", 3, 4), emu.calls)

    # --- the purchase and the switch
    def run_until(self, emu, stub: str, stop: int, **regs) -> None:
        for reg, value in regs.items():
            emu.uc.reg_write(getattr(E.X, f"UC_X86_REG_{reg.upper()}"), value)
        emu.uc.reg_write(E.X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        emu.uc.emu_start(emu.sym(stub), stop, count=1000)

    def test_doses_per_purchase(self) -> None:
        for chemical, upgrade_view, doses in ((37, 1, 3), (38, 1, 3), (39, 1, 3), (37, 0, None)):
            emu = self.greenhouse()
            dialog = emu.alloc(0x200)
            emu.write32(dialog + 0xB8, chemical)
            emu.write8(emu.sym("_upgrade_dialog"), upgrade_view)
            table = emu.alloc(0x2000)
            emu.write32(table + 0x8DC, 77)                                 # what the stock record says
            self.run_until(emu, "_stub_chem_doses", 0x00432E4A, ebp=dialog, eax=0, ecx=table)
            self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EDX), doses if doses else 77, (chemical, upgrade_view))

    def test_the_dialog_rides_the_vaporbomb_path_only_from_the_upgrades_view(self) -> None:
        for chemical, upgrade_view, building in ((37, 1, 37), (38, 1, 38), (39, 1, 39), (37, 0, 0), (36, 0, 36)):
            emu = self.greenhouse()
            emu.write8(emu.sym("_upgrade_dialog"), upgrade_view)
            esp = E.STACK + E.STACK_SIZE - 0x1000
            emu.write32(esp + 4, chemical)
            emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
            emu.uc.emu_start(emu.sym("_stub_dialog"), 0x00430957, count=1000)
            self.assertEqual(emu.read32(emu.sym("_building_chem")) & 0xFF, building, chemical)

    def test_the_switch_sends_36_to_39_here(self) -> None:
        for chemical, back in ((36, 0x0042720B), (37, 0x0042720B), (38, 0x0042720B), (39, 0x0042720B),
                               (35, 0x004266AD), (40, 0x004266AD)):
            emu = self.greenhouse()
            emu.hook(emu.sym("_apply_chemical"), emu.record("apply", args=5), 0)
            esp = E.STACK + E.STACK_SIZE - 0x1000
            emu.write32(esp + 0x20, chemical)
            emu.write32(esp + 0x14, 0)
            emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
            emu.uc.reg_write(E.X.UC_X86_REG_ESI, emu.gh)
            emu.uc.emu_start(emu.sym("_stub_apply"), back, count=1000)
            self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EIP), back, chemical)

    def test_names_and_tooltips_use_drawable_glyphs(self) -> None:
        import test_store_extras
        font = test_store_extras.plant_font()
        texts = []
        for name in ("REVIVAL_TITLE", "REVIVAL_DESC", "REVIVAL_NAME", "REVITA_TITLE", "REVITA_DESC", "REVITA_NAME",
                     "BOMB_TITLE", "BOMB_DESC", "BOMB_NAME"):
            emu = self.greenhouse()
            texts.append(emu.cstring(emu.sym(f"_{name}")).decode("latin-1"))
        joined = " ".join(t.replace("\n", " ") for t in texts)
        self.assertIn("This magical potion instantly revives dead plants and restores them to full health. "
                      "Contains 3 doses.", joined)
        self.assertIn("Revitalizes depleted plants so they can produce more seeds. Contains 3 doses.", joined)
        for text in texts:
            self.assertLessEqual(set(text) - {"\n"}, font, text)


if __name__ == "__main__":
    unittest.main()
