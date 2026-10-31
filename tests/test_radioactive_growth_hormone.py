"""The Radioactive Growth Hormone on Fish Tycoon's Upgrades page (DS Store Items).

$10,000 ($0 with Free upgrades), 3 doses, bought into supply slot #3 like the
stock chemicals. Each dose reaches exactly the fish the stock Growth Hormone
reaches (0x4210F2: each live fish aged 40 or less in the tank being looked
at) and makes each an adult (age 20) if younger, with health 100 and no
sickness. The emulation tests run the DLL's own code and the vanilla
executable's use handler (0x420B70) in Unicorn (tests/store_emulator.py).
"""

from __future__ import annotations

import io
import re
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

IMAGES = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
ART = {"ITEM_RADIOACTIVE_GROWTHHORMONE.png": (48, 65), "TOOL_RADIOACTIVE_GROWTHHORMONE.png": (24, 35),
       "TOOL_dropper_RADIOACTIVE.png": (21, 21)}
FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None

RGH_ITEM, SPR_ITEM, SPR_TOOL, SPR_DROPPER = 29, 235, 236, 237
S_DIFFICULTY, S_CURED, S_SPENT, S_TANK, S_MONEY = 0x14, 0x34, 0x24, 0x384, 0x38C
SLOT3 = 0x2B8 + 2 * 0x1C                     # supply slot #3: item, present, count, icon, cursor, x
FISH, TANK, REC = 0x390, 0x51EC, 0x288
F_LIVE, F_LAST_AGE, F_AGE, F_HEALTH, F_DISEASE, F_FOOD, F_BODY = 0x00, 0x08, 0x0C, 0x3C, 0x40, 0x44, 0x4C
F_DUE, F_MATE_BODY, F_MATE_FIN, F_FIN = 0x10, 0x14, 0x18, 0x50
CELL = (630, 125)                            # the seventh net cell


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


class ArtAndManifestTests(unittest.TestCase):
    def test_the_art_is_pinned_with_the_store(self) -> None:
        store = combined.patch_settings("fish")["ds_store"]
        destinations = {f["destination"] for f in store["companion"]["files"]}
        for name, size in ART.items():
            self.assertIn(f"Images/{name}", destinations)
            self.assertEqual(png_size(IMAGES / name), size, name)          # the stock pictures' sizes
        for text in ("Radioactive Growth Hormone", "$10,000", "every live fish in the tank", "any age",
                     "Revival Potion", "ClonaFish", "$2,500", "birth"):
            self.assertIn(text, store["description"])
        free = combined.patch_settings("fish")["free_upgrades"]["description"]
        self.assertIn("Radioactive Growth Hormone ($10,000)", free)

    def test_ds_fish_lends_the_store_enough_sprites(self) -> None:
        fish = (ROOT / "native" / "ftfp_ds_fish" / "ftfp_ds_fish.c").read_text(encoding="utf-8")
        store = (ROOT / "native" / "ftfp_ds_store" / "ftfp_ds_store.c").read_text(encoding="utf-8")
        lent = int(re.search(r"#define STORE_SPRITE_COUNT (\d+)", fish).group(1))
        named = int(re.search(r"#define STORE_SPRITES (\d+)", store).group(1))
        self.assertEqual(named, 32)                 # with the Revival Potion's and ClonaFish's six, the Auto items' two,
                                                    # Muta-Fin's and Muta-Body's six
        self.assertGreaterEqual(lent, named)

    @unittest.skipUnless(FISH_EXE is not None and FISH_EXE.is_file(), "needs the vanilla executable")
    def test_the_art_is_the_stock_art_recoloured_by_its_build_script(self) -> None:
        import numpy as np
        from PIL import Image
        import build_growth_hormone_assets as build
        built = build.build(FISH_EXE.parent)
        self.assertEqual(set(built), set(ART))
        with zipfile.ZipFile(FISH_EXE.parent / "Assets" / "ft.dat") as archive:
            names = {n.lower(): n for n in archive.namelist()}
            stock = {out: Image.open(io.BytesIO(archive.read(names[src]))).convert("RGBA")
                     for src, out in build.ART.items()}
        for name, image in built.items():
            committed = np.asarray(Image.open(IMAGES / name).convert("RGBA"))
            self.assertTrue((np.asarray(image) == committed).all(), name)          # pinned: rebuilt = committed
            source = np.asarray(stock[name]).astype(int)
            green = committed.astype(int)
            self.assertTrue((green[..., 3] == source[..., 3]).all(), name)        # same shape and alpha
            self.assertLessEqual(np.abs(green[..., :3].max(-1) - source[..., :3].max(-1)).max(), 1, name)  # shading kept
            liquid = (source[..., 3] > 128) & (source[..., 2] - source[..., 1] > 30)
            self.assertTrue(liquid.any(), name)
            self.assertTrue((green[liquid][:, 1] > green[liquid][:, 2]).all(), name)          # now green
            self.assertTrue((green[liquid][:, 1] >= green[liquid][:, 0]).all(), name)
        self.assertTrue((ROOT / "docs" / "images" / "radioactive-growth-hormone-fish.png").is_file())


def _needs():
    ready = E is not None and E.toolchain_ready() and FISH_EXE is not None and FISH_EXE.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


@_needs()
class HormoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_ds_store", ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ the store
    def store(self, money: int, free: bool = False, universal: bool = False, answer_yes: bool = True):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        emu.hook_import("GetTickCount", lambda e: 0, 0)                           # the selection's pulse
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)                       # no Extra Tanks.dll loaded
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)                       # HINT
        emu.hook(0x004221A0, emu.record("dialog", args=1), 8)                     # DIALOG_INIT(string id, 1)
        emu.hook(0x00401D00, emu.record("run", 0 if answer_yes else 1), 8)        # DIALOG_RUN: 0 = Yes
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

    def select(self, emu) -> None:
        emu.call(emu.sym("@on_mouse@20"), 3, *CELL, ecx=emu.scene)

    def buy(self, emu) -> None:
        self.select(emu)
        emu.call(emu.sym("_buy"), emu.scene)

    def slot(self, emu, k: int = 2) -> tuple[int, ...]:
        return struct.unpack("<6i", emu.uc.mem_read(emu.state + 0x2B8 + k * 0x1C, 24))

    def shown(self, emu) -> list[str]:
        self.select(emu)
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        return [c[1] for c in emu.calls if c[0] == "text"]

    def test_price_is_10000_and_0_with_free_upgrades(self) -> None:
        texts = self.shown(self.store(0))
        self.assertIn("Radioactive Growth Hormone", texts)
        self.assertEqual([t for t in texts if t.startswith("Price:")][-1], "Price:  $10000")
        self.assertEqual([t for t in self.shown(self.store(0, free=True)) if t.startswith("Price:")][-1], "Price:  $0")

    def test_bought_into_slot_3_with_3_doses(self) -> None:
        emu = self.store(12000)
        self.buy(emu)
        self.assertIn(("dialog", (0xEC,)), emu.calls)                  # the stock purchase question
        self.assertEqual(self.slot(emu), (RGH_ITEM, 1, 3, SPR_TOOL, SPR_DROPPER, 2 * 0x30 + 0x1E))
        self.assertEqual(emu.read32(emu.state + S_MONEY), 2000)
        self.assertEqual(emu.read32(emu.state + S_SPENT), 10000)

    def test_free_upgrades_take_no_money(self) -> None:
        emu = self.store(0, free=True)
        self.buy(emu)
        self.assertEqual(self.slot(emu)[:3], (RGH_ITEM, 1, 3))
        self.assertEqual((emu.read32(emu.state + S_MONEY), emu.read32(emu.state + S_SPENT)), (0, 0))

    def test_refused_below_10000_and_on_no(self) -> None:
        emu = self.store(9999)
        self.buy(emu)
        self.assertIn(("hint", (2,)), emu.calls)                       # "You can't afford to buy this yet!"
        self.assertEqual(self.slot(emu), (0,) * 6)
        emu = self.store(10000, answer_yes=False)
        self.buy(emu)
        self.assertEqual(self.slot(emu), (0,) * 6)
        self.assertEqual(emu.read32(emu.state + S_MONEY), 10000)

    def test_replaces_a_chemical_in_slot_3_as_the_stock_store_does(self) -> None:
        emu = self.store(10000)
        emu.uc.mem_write(emu.state + SLOT3, struct.pack("<6i", 3, 1, 2, 0x7A, 0x7B, 0x7E))    # Growth Hormone x2
        self.buy(emu)
        self.assertIn(("dialog", (0xEE,)), emu.calls)                  # "Replace chemical in slot #3?"
        self.assertEqual(self.slot(emu), (RGH_ITEM, 1, 3, SPR_TOOL, SPR_DROPPER, 0x7E))

    def test_universal_slots_stack_3_doses_per_purchase(self) -> None:
        emu = self.store(30000, universal=True)
        self.buy(emu)
        self.assertEqual(self.slot(emu, 1), (RGH_ITEM, 1, 3, SPR_TOOL, SPR_DROPPER, 1 * 0x30 + 0x1E))  # first empty
        self.buy(emu)
        self.assertEqual(self.slot(emu, 1)[:3], (RGH_ITEM, 1, 6))      # the stack gains 3, as stock chemicals
        self.assertEqual(self.slot(emu, 2), (0,) * 6)
        self.assertEqual(emu.read32(emu.state + S_MONEY), 10000)

    # ------------------------------------------------------- the stubs
    def run_stub(self, name: str, targets: tuple[int, ...], **regs) -> int:
        """Where a naked stub jumps back into the game: the first of `targets` it reaches."""
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

    def test_buying_a_stock_chemical_over_it_asks_to_replace(self) -> None:
        targets = (0x428191, 0x4281D6)                 # "Replace chemical in slot #3?", or nothing (stock)
        for icon, back in ((SPR_TOOL, 0x428191), (0xAA, 0x428191), (0x50, 0x4281D6)):
            self.assertEqual(self.run_stub("_stub_chem_confirm", targets, ecx=icon), back, icon)

    def test_universal_slots_send_it_to_the_chemicals(self) -> None:
        targets = (0x43F5A2, 0x43F5AC, 0x43F5DE)       # the payload's chemicals, eggs, anything else
        # 29-31: the hormone, the Revival Potion and ClonaFish go to the chemicals.
        for item, back in ((RGH_ITEM, 0x43F5A2), (30, 0x43F5A2), (31, 0x43F5A2), (28, 0x43F5AC), (32, 0x43F5A2), (33, 0x43F5A2), (34, 0x43F5DE),
                           (7, 0x43F5DE)):
            self.assertEqual(self.run_stub("_stub_use_gate", targets, edx=item), back, item)

    # ------------------------------------------------------- a dose
    def tank(self, hard: bool = False, bigger: bool = False, item: int = RGH_ITEM, count: int = 3):
        """The vanilla use handler (0x420B70) with the DLL's chemical switch at 0x420E6F, slot #3 picked."""
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        stub = emu.sym("_stub_chem_use")
        emu.uc.mem_write(0x420E6F, b"\xE9" + struct.pack("<i", stub - 0x420E74) + b"\x90" * 7)
        if bigger:
            emu.uc.mem_write(0x421190, struct.pack("<I", 26 * REC))       # "Bigger tanks"' loop end
        emu.hook(0x00413B00, emu.record("effect", args=3), 12)
        emu.hook(0x004251A0, lambda e: 0, 4)                               # no sound object
        emu.hook(0x0040AE20, emu.record("play"), 4)
        emu.hook(0x00413BD0, lambda e: 0, 4)                               # no fish on screen: no sparkles
        emu.hook(0x004020D0, lambda e: 5000, 0)                            # the clock
        emu.rolls = []                                                     # Random(n): these, then 0
        emu.hook(0x00403240, lambda e: e.rolls.pop(0) if e.rolls else 0, 0)
        emu.magic = set()                                                  # the Magic Fish kinds in the tank
        emu.hook(0x0041DE90, lambda e: int(e.arg(0) in e.magic), 8)
        emu.hook(0x004032C0, lambda e: 4321, 0)                            # the state's clock
        emu.hook(0x00415DF0, lambda e: 0, 12)                              # NewBaby's sprite helper
        emu.hook(0x00415E70, emu.record("view sync", args=1), 4)
        emu.hook(0x0041A940, emu.record("tutorial", args=1), 4)
        state, impl = emu.alloc(0x40000), emu.alloc(0x100)
        for at in range(0, 0x1E3C8, 4):                                    # every field: a pattern
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        emu.write32(state + S_TANK, 0)
        emu.write32(state + S_DIFFICULTY, 2 if hard else 1)
        emu.write32(state + S_CURED, 7)
        emu.write32(state + 0x1A4, 0)                                      # no Plant of Fertility
        emu.uc.mem_write(state + SLOT3, struct.pack("<6i", item, 1, count, SPR_TOOL, SPR_DROPPER, 0x7E))
        for tank in range(4):                                              # every record empty
            for slot in range(31):
                emu.write32(state + FISH + tank * TANK + slot * REC, 0)
        emu.write32(impl + 0x1C, 2)                                        # slot #3 picked
        emu.write32(impl + 0x34, state)
        emu.write32(impl + 0x3C, emu.alloc(0x40))
        emu.write32(impl + 0x4C, emu.alloc(0x40))
        for at, value in ((0xA8, 0), (0xAC, 0), (0xB0, 800), (0xB4, 600)):  # the click is in the tank
            emu.write32(impl + at, value)
        emu.state, emu.impl = state, impl
        return emu

    def fish(self, emu, slot: int, age: int, health: int, disease: int, tank: int = 0, body: int = 3,
             due: int = 0) -> int:
        at = emu.state + FISH + tank * TANK + slot * REC
        emu.write32(at + F_LIVE, 1234)
        for field, value in ((F_AGE, age), (F_LAST_AGE, age), (F_HEALTH, health), (F_DISEASE, disease),
                             (F_BODY, body), (F_DUE, due)):
            emu.write32(at + field, value)
        return at

    def dose(self, emu) -> None:
        emu.write32(emu.impl + 0x1C, 2)                                   # slot #3 picked up
        emu.call(0x00420B70, 400, 300, ecx=emu.impl)

    def field(self, emu, at: int, field: int) -> int:
        return emu.read32(at + field, signed=True)

    def test_a_dose_makes_every_reached_fish_an_adult_healthy_and_cured(self) -> None:
        emu = self.tank()
        fry = self.fish(emu, 0, 1, 40, 0)                 # just hatched
        teen = self.fish(emu, 1, 10, 20, 1)               # fungus
        adult = self.fish(emu, 2, 25, 70, 2)              # ick
        forty = self.fish(emu, 3, 40, 5, 1)               # the stock hormone's oldest
        old = self.fish(emu, 4, 641, 30, 2)               # past the stock hormone: reached too (any age)
        dead = self.fish(emu, 5, 3, 0, 0)                 # dead: not reached
        other_tank = self.fish(emu, 0, 2, 10, 1, tank=1)  # another tank: not reached
        seahorse = self.fish(emu, 26, 21, 50, 0, body=22)   # an animal slot: not reached
        before = bytes(emu.uc.mem_read(emu.state, 0x1E3C8))
        self.dose(emu)
        for at in (fry, teen, adult, forty, old):
            self.assertGreaterEqual(self.field(emu, at, F_AGE), 20)
            self.assertEqual(self.field(emu, at, F_HEALTH), 100)
            self.assertEqual(self.field(emu, at, F_DISEASE), 0)
        self.assertEqual([self.field(emu, at, F_AGE) for at in (fry, teen, adult, forty, old)], [20, 20, 25, 40, 641])
        self.assertEqual([self.field(emu, at, F_LAST_AGE) for at in (fry, teen, adult, forty, old)], [19, 19, 25, 40, 641])
        self.assertEqual(emu.read32(emu.state + S_CURED), 7 + 4)                   # Fish Cured, as the medicine
        self.assertEqual(emu.read32(emu.impl + 0x30), 5000 + 7)                    # the next update, as stock
        # Nothing else changed: the records not reached, and every other field of the state.
        expected = bytearray(before)
        for at, field, value in ((fry, F_AGE, 20), (fry, F_LAST_AGE, 19), (fry, F_HEALTH, 100),
                                 (teen, F_AGE, 20), (teen, F_LAST_AGE, 19), (teen, F_HEALTH, 100), (teen, F_DISEASE, 0),
                                 (adult, F_HEALTH, 100), (adult, F_DISEASE, 0),
                                 (forty, F_HEALTH, 100), (forty, F_DISEASE, 0),
                                 (old, F_HEALTH, 100), (old, F_DISEASE, 0)):
            struct.pack_into("<i", expected, at + field - emu.state, value)
        for at in (fry, teen, adult, forty, old):                                   # treated: the highest price
            struct.pack_into("<I", expected, at + 0x48 - emu.state, 0x58414D52)     # (test_radioactive_max_price)
        struct.pack_into("<i", expected, S_CURED, 11)
        struct.pack_into("<i", expected, SLOT3 + 8, 2)                             # one dose spent
        self.assertEqual(bytes(emu.uc.mem_read(emu.state, 0x1E3C8)), bytes(expected))
        for at in (dead, other_tank, seahorse):
            self.assertEqual(bytes(emu.uc.mem_read(at, REC)), before[at - emu.state:at - emu.state + REC])

    def test_no_catch_up_on_hard_while_the_stock_hormone_is_unchanged(self) -> None:
        # Radioactive: last-processed age 19 on Hard too, so the update runs one step's checks.
        emu = self.tank(hard=True)
        fry = self.fish(emu, 0, 1, 40, 0)
        self.dose(emu)
        self.assertEqual((self.field(emu, fry, F_AGE), self.field(emu, fry, F_LAST_AGE)), (20, 19))
        self.assertEqual(self.field(emu, fry, F_HEALTH), 100)
        # Stock Growth Hormone (Random = 0: +2): on Hard it leaves the last-processed age, as stock ...
        emu = self.tank(hard=True, item=3)
        young = self.fish(emu, 0, 1, 40, 0)
        self.dose(emu)
        self.assertEqual((self.field(emu, young, F_AGE), self.field(emu, young, F_LAST_AGE)), (3, 1))
        # ... and off Hard sets it to age - 1.
        emu = self.tank(item=3)
        young = self.fish(emu, 0, 1, 40, 0)
        self.dose(emu)
        self.assertEqual((self.field(emu, young, F_AGE), self.field(emu, young, F_LAST_AGE)), (3, 2))

    def test_bigger_tanks_reach_26_records_and_never_the_animals(self) -> None:
        emu = self.tank(bigger=True)
        last = self.fish(emu, 25, 2, 10, 1)
        animal = self.fish(emu, 26, 2, 10, 1)
        self.dose(emu)
        self.assertEqual((self.field(emu, last, F_AGE), self.field(emu, last, F_HEALTH)), (20, 100))
        self.assertEqual((self.field(emu, animal, F_AGE), self.field(emu, animal, F_HEALTH)), (2, 10))
        emu = self.tank()
        stock_end = self.fish(emu, 21, 2, 10, 1)                           # the stock loop stops at 21
        self.dose(emu)
        self.assertEqual(self.field(emu, stock_end, F_AGE), 2)

    def test_doses_count_down_and_the_slot_empties(self) -> None:
        emu = self.tank()
        fish = self.fish(emu, 0, 1, 10, 0)
        for left in (2, 1):
            self.dose(emu)
            self.assertEqual(self.slot_record(emu), (RGH_ITEM, 1, left, SPR_TOOL, SPR_DROPPER))
            emu.write32(fish + F_HEALTH, 10)
        self.dose(emu)
        self.assertEqual(self.slot_record(emu), (0, 0, 0, 0, 0))            # the stock tail clears it
        self.assertEqual(self.field(emu, fish, F_HEALTH), 100)
        self.assertEqual(emu.read32(emu.impl + 0x1C), 0x63)                # nothing picked, as stock

    def slot_record(self, emu) -> tuple[int, ...]:
        return struct.unpack("<5i", emu.uc.mem_read(emu.state + SLOT3, 20))

    def test_the_stock_chemicals_still_work_through_the_switch(self) -> None:
        emu = self.tank(item=3)                                           # Growth Hormone, Random = 0: +2
        young = self.fish(emu, 0, 1, 40, 1)
        self.dose(emu)
        self.assertEqual((self.field(emu, young, F_AGE), self.field(emu, young, F_HEALTH),
                          self.field(emu, young, F_DISEASE)), (3, 40, 1))
        emu = self.tank(item=2)                                           # Fish Vitamins, Random = 0: +6
        weak = self.fish(emu, 0, 30, 40, 0)
        self.dose(emu)
        self.assertEqual(self.field(emu, weak, F_HEALTH), 46)

    # ------------------------------------------------------- instant births
    def mother(self, emu, slot: int = 2, age: int = 30, due: int = 33, mate=(7, 9), tank: int = 0) -> int:
        at = self.fish(emu, slot, age, 60, 0, tank=tank, body=3, due=due)
        for field, value in ((F_FIN, 5), (F_MATE_BODY, mate[0]), (F_MATE_FIN, mate[1])):
            emu.write32(at + field, value)
        for k, field in enumerate(range(0x1C, 0x3C, 4)):                  # the grandparents
            emu.write32(at + field, 10 + k)
        return at

    def stock_birth(self, emu, slot: int = 2, tank: int = 0) -> None:
        """The vanilla update's birth code (0x420113-0x420414) for one fish, as the update runs it."""
        from unicorn import x86_const as X
        esp = E.STACK + E.STACK_SIZE - 0x1000
        emu.write32(esp + 0x10, tank)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ESI, emu.impl)
        emu.uc.reg_write(X.UC_X86_REG_EDI, tank * TANK + slot * REC)
        emu.uc.emu_start(0x420113, 0x420414, count=100_000)

    def babies(self, emu) -> list[tuple[int, ...]]:
        return [c[1] for c in emu.calls if c[0] == "baby"]

    def test_the_litter_is_the_stock_birth_for_the_same_rolls(self) -> None:
        # (Magic Fish kinds in the tank, Plant of Fertility, Random rolls, the father's genes)
        cases = (((), 0, [], (7, 9)), ((5,), 0, [10, 20, 30], (7, 9)), ((5,), 0, [10, 20, 70], (0, 9)),
                 ((5,), 0, [10, 70, 30], (7, 9)), ((5,), 0, [10, 70, 70], (7, 9)), ((5,), 0, [10, 5], (20, 3)),
                 ((5,), 0, [10, 60], (20, 20)), ((5,), 0, [16], (7, 9)), ((0,), 1, [], (7, 9)),
                 ((0, 5), 1, [3, 3, 3], (19, 0)))
        for magic, plant, rolls, mate in cases:
            runs = []
            for natural in (True, False):
                emu = self.tank()
                emu.hook(0x0041FA30, emu.record("baby", args=14), 56)
                emu.magic, emu.rolls = set(magic), list(rolls)
                emu.write32(emu.state + 0x1A4, plant)
                if natural:                                   # due on this step: age 30, due 29
                    at = self.mother(emu, due=29, mate=mate)
                    self.stock_birth(emu)
                else:                                         # still pregnant (due 33): the dose
                    at = self.mother(emu, due=33, mate=mate)
                    self.dose(emu)
                runs.append((self.babies(emu), [self.field(emu, at, f) for f in (F_DUE, F_MATE_BODY, F_MATE_FIN)]))
            self.assertEqual(runs[1], runs[0], (magic, plant, rolls, mate))
            self.assertEqual(len(runs[0][0]), 1 + (0 in magic) + plant)
            self.assertEqual(runs[0][1][0], 0)                # no longer pregnant
            self.assertEqual(runs[0][0][0][12:], (1, 0))      # babies aged 1, into tank 0

    def test_newborns_stay_babies_and_only_the_fish_young_before_grow_up(self) -> None:
        # The owner, 2026-10-31 ("babies stay babies"): the game shows a species name only from age
        # 20 (0x41D9ED), so the dose's newborns keep exactly the record the stock birth gives them.
        exe = FISH_EXE.read_bytes()
        self.assertEqual(exe[0x41D9ED - 0x400000:0x41D9F5 - 0x400000], bytes.fromhex("83bc389c03000014"))
        records = []
        for natural in (True, False):
            emu = self.tank()
            emu.magic = {0}                                   # a Magic Fish of Fertility: +1 baby
            emu.write32(emu.state + 0x1A4, 1)                 # the Plant of Fertility: +1 baby
            mom = self.mother(emu, slot=0, due=29 if natural else 33)
            young = [self.fish(emu, s, 5, 50, 0) for s in (1, 3)]   # slot 2 free between them
            self.stock_birth(emu, slot=0) if natural else self.dose(emu)
            babies = [emu.state + FISH + s * REC for s in (2, 4, 5)]   # AddFish: the first free records
            records.append([bytes(emu.uc.mem_read(at, REC)) for at in babies])
            if not natural:
                for at in babies:
                    self.assertNotEqual(self.field(emu, at, F_LIVE), 0)
                    self.assertEqual((self.field(emu, at, F_AGE), self.field(emu, at, F_LAST_AGE)), (1, 0))
                    self.assertEqual((self.field(emu, at, F_BODY), self.field(emu, at, F_FIN)), (5, 7))
                for at in young:                              # young before the dose: adults now
                    self.assertEqual((self.field(emu, at, F_AGE), self.field(emu, at, F_LAST_AGE)), (20, 19))
                    self.assertEqual(self.field(emu, at, F_HEALTH), 100)
                self.assertEqual((self.field(emu, mom, F_DUE), self.field(emu, mom, F_HEALTH)), (0, 100))
                self.assertEqual(self.field(emu, emu.state + FISH + 6 * REC, F_LIVE), 0)
                self.assertIn(("view sync", (emu.state + FISH,)), emu.calls)   # the newborns swim at once
        self.assertEqual(records[1], records[0])              # each baby exactly as a natural birth makes it

    def test_every_birth_source_stays_a_baby(self) -> None:
        for magic, plant, litter in (((), 0, 1), ((0,), 0, 2), ((), 1, 2), ((0, 5), 1, 3)):
            emu = self.tank()
            emu.magic = set(magic)
            emu.write32(emu.state + 0x1A4, plant)
            self.mother(emu, slot=0)
            self.dose(emu)
            ages = [self.field(emu, emu.state + FISH + s * REC, F_AGE) for s in range(1, 1 + litter)]
            self.assertEqual(ages, [1] * litter, (magic, plant))
            self.assertEqual(self.field(emu, emu.state + FISH + (1 + litter) * REC, F_LIVE), 0, (magic, plant))

    def test_a_later_dose_grows_the_babies_up(self) -> None:
        emu = self.tank()
        self.mother(emu, slot=0)
        self.dose(emu)
        baby = emu.state + FISH + 1 * REC
        self.assertEqual(self.field(emu, baby, F_AGE), 1)
        self.dose(emu)
        self.assertEqual((self.field(emu, baby, F_AGE), self.field(emu, baby, F_LAST_AGE)), (20, 19))

    def test_babies_stay_babies_with_30_per_tank_and_in_tanks_4_to_6(self) -> None:
        emu = self.tank()
        emu.uc.mem_write(0x421190, struct.pack("<I", 30 * REC))   # 30 per tank: the loop end ...
        emu.uc.mem_write(0x419C74, bytes([30]))                     # ... and AddFish's limit
        for slot in range(27):
            self.fish(emu, slot, 30, 60, 0, body=4)
        self.mother(emu, slot=27)
        young = self.fish(emu, 28, 5, 50, 0)
        self.dose(emu)
        self.assertEqual(self.field(emu, emu.state + FISH + 29 * REC, F_AGE), 1)   # the baby, in slot 29
        self.assertEqual(self.field(emu, young, F_AGE), 20)
        for tank in (4, 5, 6):                                      # the update's tank bound, read
            emu = self.tank()
            emu.uc.mem_write(0x4206C7, bytes([6]))
            emu.write32(emu.state + S_TANK, tank)
            for slot in range(31):
                emu.write32(emu.state + FISH + tank * TANK + slot * REC, 0)
            self.mother(emu, slot=0, tank=tank)
            young = self.fish(emu, 1, 5, 50, 0, tank=tank)
            self.dose(emu)
            self.assertEqual(self.field(emu, emu.state + FISH + tank * TANK + 2 * REC, F_AGE), 1, tank)
            self.assertEqual(self.field(emu, young, F_AGE), 20, tank)

    def test_a_full_tank_loses_the_babies_as_stock(self) -> None:
        outcomes = []
        for natural in (True, False):
            emu = self.tank()
            for slot in range(21):
                self.fish(emu, slot, 30, 60, 0, body=4)
            mom = self.mother(emu, slot=0, due=29 if natural else 33)
            before = [bytes(emu.uc.mem_read(emu.state + FISH + s * REC, REC)) for s in range(1, 31)]
            self.stock_birth(emu, slot=0) if natural else self.dose(emu)
            after = [bytes(emu.uc.mem_read(emu.state + FISH + s * REC, REC)) for s in range(21, 31)]
            outcomes.append((self.field(emu, mom, F_DUE), after == before[20:]))
        self.assertEqual(outcomes, [(0, True), (0, True)])   # no room: no baby, the pregnancy ends

    def test_fish_not_pregnant_or_not_reached_give_no_birth(self) -> None:
        # Not pregnant, dead, or in another tank (any age is reached: test_old_mothers_give_birth_too).
        emu = self.tank()
        emu.hook(0x0041FA30, emu.record("baby", args=14), 56)
        self.fish(emu, 0, 30, 60, 0)                           # not pregnant
        dead = self.mother(emu, slot=3)
        emu.write32(dead + F_HEALTH, 0)                        # dead
        self.mother(emu, slot=0, tank=1)                       # another tank
        self.dose(emu)
        self.assertEqual(self.babies(emu), [])
        self.assertNotIn("view sync", [c[0] for c in emu.calls])

    def test_old_mothers_give_birth_too(self) -> None:
        emu = self.tank()
        emu.hook(0x0041FA30, emu.record("baby", args=14), 56)
        mom = self.mother(emu, slot=0, age=300, due=305)
        self.dose(emu)
        self.assertEqual(len(self.babies(emu)), 1)
        self.assertEqual((self.field(emu, mom, F_DUE), self.field(emu, mom, F_AGE)), (0, 300))
        self.assertEqual(self.field(emu, mom, F_HEALTH), 100)

    def test_tank_3_never_gives_birth_as_stock(self) -> None:
        emu = self.tank()
        emu.hook(0x0041FA30, emu.record("baby", args=14), 56)
        emu.write32(emu.state + S_TANK, 3)
        mom = self.mother(emu, slot=0, tank=3)
        self.dose(emu)
        self.assertEqual(self.babies(emu), [])
        self.assertEqual(self.field(emu, mom, F_DUE), 33)
        self.assertEqual(self.field(emu, mom, F_HEALTH), 100)  # the rest of the dose still works

    def test_the_stock_growth_hormone_gives_no_birth(self) -> None:
        emu = self.tank(item=3)
        emu.hook(0x0041FA30, emu.record("baby", args=14), 56)
        mom = self.mother(emu, slot=0)
        self.dose(emu)
        self.assertEqual(self.babies(emu), [])
        self.assertEqual(self.field(emu, mom, F_DUE), 33)

    def test_births_reach_30_per_tank_and_extra_tanks(self) -> None:
        # The loop end and the tank count are read from the game (GH 0x421190, update 0x4206C7).
        emu = self.tank()
        emu.hook(0x0041FA30, emu.record("baby", args=14), 56)
        emu.uc.mem_write(0x421190, struct.pack("<I", 30 * REC))
        mom = self.mother(emu, slot=29)
        self.dose(emu)
        self.assertEqual(len(self.babies(emu)), 1)
        self.assertEqual(self.field(emu, mom, F_DUE), 0)
        emu = self.tank()
        emu.hook(0x0041FA30, emu.record("baby", args=14), 56)
        emu.uc.mem_write(0x4206C7, bytes([5]))                 # tanks 0-5
        emu.write32(emu.state + S_TANK, 5)
        for slot in range(31):
            emu.write32(emu.state + FISH + 5 * TANK + slot * REC, 0)
        mom = self.mother(emu, slot=0, tank=5)
        self.dose(emu)
        self.assertEqual([b[13] for b in self.babies(emu)], [5])
        self.assertEqual(self.field(emu, mom, F_HEALTH), 100)


if __name__ == "__main__":
    unittest.main()
