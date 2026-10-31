"""The Seventh, Eighth and Ninth Seed Box (Plant Tycoon, Add new store upgrades and items).

Emulated on the vanilla executable (tests/store_emulator.py): each DLL's own code is rebuilt from
its committed source and run in Unicorn beside the game's own code.

* The store ("Store Upgrades and Items.dll"): a click on a box runs the DLL's on_click, and the
  dialog it builds runs the game's own purchase helper 0x430950 (the stock dialog's decisions: the
  price, "You need the previous upgrade first!", "You already have this item!", "You can't afford
  to buy this yet!") and, when the dialog offers Buy, the game's own Buy (0x432D00, button 3), which
  sets the owned byte and takes the cash through 0x41ED70.
* Seed Storage ("Extra Seed Boxes.dll"): the DLL's scene wrappers around the game's own mouse code
  (0x434D70): a tray seed stored in a box 7-9 slot and taken back, by click and by drag and drop;
  the arrows; the drawer level 0x41DE60 and the greenhouse's send-to-box 0x4245F0 with the DLL's
  stubs written in.
* The sidecar: a version 1 file (the Fourth-Sixth) loads into version 2 with nothing lost; a round
  trip; a new game; a damaged file set aside.
* Sort Seeds ("Sort Seeds.dll"): its own sort over the three chests the Seed Boxes DLL lists.
* The Upgrades view: the DLL's own draw calls, composited from the game's sheets
  (scripts/render_seed_boxes_preview.py), overlap nothing; the click rectangles neither.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
UPGRADES = ROOT / "assets" / "plant_tycoon_upgrades"
READY = E is not None and E.toolchain_ready() and PLANT_EXE is not None and PLANT_EXE.is_file()
needs_game = unittest.skipUnless(READY, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")

S_CASH, S_HELD, S_SECOND, S_THIRD = 0x217C, 0x56C, 0x80C, 0x8AC
BOX, TRAY, REC, RECORDS = 0x52CCC, 0x52B88, 0x24, 120
TOOL_RECORD = 0x6E8
EMPTY_RECORD = 0x0041D420


def game_string_id(name: str) -> int:
    """A string id from the game's own table of {id, name, text, override} records."""
    exe = PLANT_EXE.read_bytes()
    at = exe.index(name.encode("ascii") + b"\0")
    va = None
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    count = struct.unpack_from("<H", exe, pe + 6)[0]
    table = pe + 24 + struct.unpack_from("<H", exe, pe + 20)[0]
    for i in range(count):
        vsize, rva, raw_size, raw = struct.unpack_from("<IIII", exe, table + 40 * i + 8)
        if raw <= at < raw + raw_size:
            va = 0x400000 + rva + at - raw
    ref = exe.index(struct.pack("<I", va))
    return struct.unpack_from("<I", exe, ref - 4)[0]


def seed_record(tag: int, foliage: int = 3, flower: int = 5) -> bytes:
    r = bytearray(REC)
    struct.pack_into("<6i", r, 0, 1, 2, 3, 4, foliage, flower)
    r[0x18] = 1
    struct.pack_into("<ii", r, 0x1C, 7, tag)                  # the picture frame, the value
    return bytes(r)


def jump(emu, at: int, to: int, length: int) -> None:
    emu.uc.mem_write(at, b"\xE9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (length - 5))


# ------------------------------------------------------------------ the store

@needs_game
class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", UPGRADES / "Store Upgrades and Items.dll",
                                                Path(cls.tmp.name))
        cls.NEED_PREREQ = game_string_id("eSayNeedPrereq")
        cls.DONT_NEED = game_string_id("eSayDontNeed")
        cls.NEED_CASH = game_string_id("eSayNeedCash")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def store(self, cash: int, owned, free: bool = False, version: int = 2):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.hook_printf()
        emu.uc.mem_map(0, 0x1000)                                       # fs:[0], the SEH chain
        emu.owned = list(owned) + [0] * (6 - len(owned))
        emu.strings, emu.dialogs = [], []
        for name, pop in (("GetModuleHandleW", 4), ("GetProcAddress", 8)):
            emu.hook_import(name, emu.record(name), pop)
        emu.hook(0x0044A580, emu.record("sound"), 4)
        emu.hook(0x0044E894, lambda e: e.alloc(max(e.arg(0), 0x40)), 0)
        emu.hook(0x00409870, emu.record("tip"), 0x1C)
        emu.hook(0x00409AA0, emu.record("tip text"), 0x10)
        emu.hook(0x0040B400, emu.record("control"), 4)
        emu.hook(0x0040CBE0, lambda e: e.alloc(0x40), 0x1C)            # a text control: built, never drawn
        emu.hook(0x00430900, lambda e: 0, 0)

        def sprintf(e):                                                  # the game's CRT sprintf: the price line
            fmt = e.cstring(e.arg(1)).decode("latin-1")
            e.uc.mem_write(e.arg(0), fmt.replace("%d", str(e.arg(2))).replace("%i", str(e.arg(2))).encode() + b"\0")
            return 0
        emu.hook(0x0044F30B, sprintf, 0)

        def string(e):
            e.strings.append(e.arg(0))
            return e.text(f"string {e.arg(0):#x}")
        emu.hook(0x0044CA70, string, 4)
        state = emu.alloc(0x60000)
        for k in range(15):                                             # stock tool records, recognisable
            emu.uc.mem_write(state + TOOL_RECORD + k * 0x20, bytes([0xA0 + k]) * 0x20)
        emu.stock_records = bytes(emu.uc.mem_read(state + TOOL_RECORD, 15 * 0x20))
        emu.write32(state + S_CASH, cash)
        scene = emu.alloc(0x400)
        emu.write32(scene + 0x1BC, state)
        events, owned_fn, set_fn, nothing = emu.alloc(0x20), emu.thunk(), emu.thunk(), emu.thunk()
        emu.hook(owned_fn, lambda e: e.owned[e.arg(0)] if 0 <= e.arg(0) < 6 else 0, 0)

        def set_owned(e):
            e.owned[e.arg(0)] = int(e.arg(1) != 0)
            return 0
        emu.hook(set_fn, set_owned, 0)
        emu.hook(nothing, lambda e: 0, 0)
        emu.write32(events, version)
        for k, fn in enumerate((nothing, nothing, nothing, nothing, owned_fn, set_fn), start=1):
            emu.write32(events + 4 * k, fn)
        emu.write32(emu.sym("_boxes"), events)
        emu.write8(emu.sym("_free_upgrades"), int(free))

        def ctor(e):
            """The stock dialog's ctor as far as the purchase goes: its fields, then the helper (same call)."""
            dlg = e.uc.reg_read(E.X.UC_X86_REG_ECX)
            e.write32(dlg + 0x74, state)
            e.write32(dlg + 0x70, e.alloc(0x40))
            e.write32(dlg + 0x7C, e.alloc(0x40))
            for off, v in ((0x14, 100), (0x18, 100), (0x1C, 500), (0x20, 400)):
                e.write32(dlg + off, v)
            e.write32(dlg + 0xB8, e.arg(0))
            e.write32(dlg + 0x90, 0xFFFFFFFF)
            e.uc.reg_write(E.X.UC_X86_REG_EIP, 0x00430950)

        def run(e):
            """The player clicks Buy when the dialog offers it (+0xA8), else OK."""
            dlg = e.uc.reg_read(E.X.UC_X86_REG_ECX)
            e.dialogs.append({"index": e.read32(dlg + 0xB8), "buy": e.uc.mem_read(dlg + 0xA8, 1)[0],
                              "price": e.read32(dlg + 0x84), "strings": list(e.strings),
                              "record4": bytes(e.uc.mem_read(state + TOOL_RECORD + 4 * 0x20, 0x20)),
                              "record9": bytes(e.uc.mem_read(state + TOOL_RECORD + 9 * 0x20, 0x20))})
            e.strings.clear()
            if e.dialogs[-1]["buy"]:
                esp = e.uc.reg_read(E.X.UC_X86_REG_ESP)
                e.write32(esp + 4, 8)                                   # button-up
                e.write32(esp + 8, 3)                                   # Buy (ecx is still the dialog)
                e.uc.reg_write(E.X.UC_X86_REG_EIP, 0x00432D00)
            else:
                esp = e.uc.reg_read(E.X.UC_X86_REG_ESP)
                e.uc.reg_write(E.X.UC_X86_REG_EIP, e.read32(esp))
                e.uc.reg_write(E.X.UC_X86_REG_ESP, esp + 12)
        emu.uc.hook_add(E.UC_HOOK_CODE, lambda uc, a, s, d: ctor(emu), begin=0x00432E90, end=0x00432E90)
        emu.uc.hook_add(E.UC_HOOK_CODE, lambda uc, a, s, d: run(emu), begin=0x00401C90, end=0x00401C90)
        emu.hook(0x004307A0, emu.record("dtor"), 0)
        emu.state, emu.scene = state, scene
        return emu

    def click_box(self, emu, box: int) -> None:
        x = (461 if box < 3 else 322) + 38
        y = 52 + 70 * (box % 3) + 30
        emu.write32(emu.sym("_upgrades_view"), 1)
        emu.call(emu.sym("_on_click"), emu.scene, x, y)

    def cash(self, emu) -> int:
        return emu.read32(emu.state + S_CASH)

    def title(self, emu, string_id: int) -> str:
        return emu.cstring(emu.call(emu.sym("_stub_string"), string_id)).decode("latin-1")

    def test_titles_and_description(self) -> None:
        emu = self.store(0, [])
        self.assertEqual([self.title(emu, 0x1F8 + k) for k in range(3)],
                         ["Seventh Seed Box", "Eighth Seed Box", "Ninth Seed Box"])
        self.assertEqual(self.title(emu, 0x1F4), "Even more space for your seeds!")
        self.assertEqual([self.title(emu, 0x1F1 + k) for k in range(3)],
                         ["Fourth Seed Box", "Fifth Seed Box", "Sixth Seed Box"])

    def test_bought_in_order_after_the_sixth(self) -> None:
        emu = self.store(5000, [1, 1, 0])
        self.click_box(emu, 3)                                          # the Seventh before the Sixth
        d = emu.dialogs[-1]
        self.assertIn(self.NEED_PREREQ, d["strings"])
        self.assertFalse(d["buy"])
        self.assertEqual(d["index"], 14)                                # the Fourth's picture, as stock art
        self.assertEqual((self.cash(emu), emu.owned), (5000, [1, 1, 0, 0, 0, 0]))
        self.click_box(emu, 2)                                          # the Sixth
        self.assertEqual((self.cash(emu), emu.owned), (4000, [1, 1, 1, 0, 0, 0]))
        self.click_box(emu, 5)                                          # the Ninth before the Eighth
        self.assertIn(self.NEED_PREREQ, emu.dialogs[-1]["strings"])
        self.assertEqual(emu.owned, [1, 1, 1, 0, 0, 0])
        for box, cash in ((3, 3000), (4, 2000), (5, 1000)):             # Seventh, Eighth, Ninth
            self.click_box(emu, box)
            d = emu.dialogs[-1]
            self.assertTrue(d["buy"], box)
            self.assertEqual(d["price"], 1000, box)                     # as the Sixth
            self.assertEqual(d["index"], 14 + 5 * (box - 3), box)       # frames 4, 9, 14: the Fourth-Sixth's art
            self.assertEqual(struct.unpack_from("<i", d["record9"], 0x10)[0], 0x1F8 + box - 3)
            self.assertEqual(self.cash(emu), cash, box)
            self.assertEqual(emu.owned[box], 1, box)
        self.click_box(emu, 5)                                          # owned: the stock answer
        self.assertIn(self.DONT_NEED, emu.dialogs[-1]["strings"])
        self.assertEqual(self.cash(emu), 1000)
        self.assertEqual(bytes(emu.uc.mem_read(emu.state + TOOL_RECORD, 15 * 0x20)), emu.stock_records)

    def test_cant_afford_and_free_upgrades(self) -> None:
        emu = self.store(999, [1, 1, 1])
        self.click_box(emu, 3)
        self.assertIn(self.NEED_CASH, emu.dialogs[-1]["strings"])
        self.assertEqual((self.cash(emu), emu.owned[3]), (999, 0))
        emu = self.store(0, [1, 1, 1], free=True)
        for box in (3, 4, 5):
            self.click_box(emu, box)
            self.assertEqual(emu.dialogs[-1]["price"], 0)
        self.assertEqual((self.cash(emu), emu.owned), (0, [1] * 6))
        self.assertEqual(bytes(emu.uc.mem_read(emu.state + TOOL_RECORD, 15 * 0x20)), emu.stock_records)

    def test_the_fourth_to_sixth_are_unchanged(self) -> None:
        emu = self.store(3000, [])
        self.click_box(emu, 1)
        self.assertIn(self.NEED_PREREQ, emu.dialogs[-1]["strings"])
        self.assertEqual(emu.dialogs[-1]["index"], 19)
        for box in (0, 1, 2):
            self.click_box(emu, box)
            self.assertEqual(emu.dialogs[-1]["index"], 14 + 5 * box)
        self.assertEqual((self.cash(emu), emu.owned), (0, [1, 1, 1, 0, 0, 0]))

    def test_an_older_seed_boxes_dll_sells_only_the_fourth_to_sixth(self) -> None:
        emu = self.store(5000, [1, 1, 1], version=1)
        self.click_box(emu, 3)
        self.assertEqual((emu.dialogs, self.cash(emu)), ([], 5000))
        emu.calls.clear()
        emu.call(emu.sym("_on_activate"), emu.scene, 1)
        tips = [c for c in emu.calls if c[0] == "tip"]
        self.assertEqual(len(tips), 13 + 2)                             # every tip is made (and both auto items')
        emu.write32(emu.sym("_upgrades_view"), 1)
        emu.call(emu.sym("_set_tooltips"), emu.scene)
        shown = [emu.uc.mem_read(emu.read32(emu.sym("_tips") + 4 * i) + 8, 1)[0] for i in range(7, 13)]
        self.assertEqual(shown, [1, 1, 1, 0, 0, 0])                    # boxes 7-9 stay hidden

    def test_tooltips(self) -> None:
        import test_store_extras
        font = test_store_extras.plant_font()
        for free, price in ((False, "1000"), (True, "0")):
            emu = self.store(0, [1, 1, 1, 1], free=free)
            emu.hook(0x00409870, lambda e: (e.calls.append(("tip", e.cstring(e.arg(3)).decode("latin-1"))), 0)[1], 0x1C)
            emu.call(emu.sym("_on_activate"), emu.scene, 1)
            tips = [c[1] for c in emu.calls if c[0] == "tip"]
            self.assertIn("Seventh Seed Box", tips)                     # owned: the name alone
            self.assertIn(f"Eighth Seed Box\nPrice: $ {price}", tips)
            self.assertIn(f"Ninth Seed Box\nPrice: $ {price}", tips)
            for text in tips:
                self.assertLessEqual(set(text) - {"\n"}, font, text)


@needs_game
class ShelfTests(unittest.TestCase):
    """The Upgrades view as the DLL draws it: boxes 7-9 overlap nothing, and nor do their click areas."""

    @classmethod
    def setUpClass(cls) -> None:
        import render_seed_boxes_preview as P
        cls.P = P
        cls.sheets = P.Sheets(PLANT_EXE.parent)
        cls.draws = P.store_draws((1, 1, 1, 1, 1, 1))

    def test_drawn_where_planned_at_scale_one(self) -> None:
        boxes = [d for d in self.draws if d[0] == "sprite" and d[1] == 0xB2]
        self.assertEqual([(d[2], d[3], d[4]) for d in boxes],
                         [(4, 461, 50), (9, 461, 111), (14, 461, 172), (4, 322, 50), (9, 322, 111), (14, 322, 172)])
        ticks = [d for d in self.draws if d[0] == "shadow" and d[1] == 0x25]
        for x, y in ((322, 50), (322, 111), (322, 172)):
            self.assertIn(("shadow", 0x25, 0, x + 19, y + 22), ticks)

    def test_boxes_7_to_9_overlap_nothing(self) -> None:
        def inter(a, b):
            return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
        sprites = [(d, self.P.visible_rect(self.sheets, d)) for d in self.draws if d[0] == "sprite"]
        mine = [(d, r) for d, r in sprites if d[1] == 0xB2 and d[3] == 322]
        others = [(d, r) for d, r in sprites if not (d[1] == 0xB2 and d[3] == 322)]
        self.assertEqual(len(mine), 3)
        for d, r in mine:
            for o, q in others + [m for m in mine if m[0] is not d]:
                self.assertFalse(inter(r, q), (d, o, r, q))
        greenhouse = next(r for d, r in sprites if d[1] == 0xB3 and d[2] == 30)
        sprinklers = next(r for d, r in sprites if d[1] == 0xB3 and d[2] == 32)
        for d, r in mine:
            self.assertGreaterEqual(min(greenhouse[0], sprinklers[0]) - r[2], 14, d)   # a clear gap, as box 4's

    def test_click_rectangles_overlap_nothing(self) -> None:
        import re
        source = (ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c").read_text(encoding="utf-8")
        auto = (ROOT / "native" / "ftfp_plant_upgrades" / "auto_upgrades.h").read_text(encoding="utf-8")
        rects = [tuple(int(v) for v in m) for m in re.findall(r"\{ (\d+), (\d+), (\d+), (\d+) \} \}", source + auto)]
        self.assertGreaterEqual(len(rects), 4)                          # extra greenhouse/nursery, both auto items
        for box in range(6):
            x = 461 if box < 3 else 322
            rects.append((x + 10, 52 + 70 * (box % 3), x + 67, 113 + 70 * (box % 3)))
        mine = rects[-3:]
        for r in mine:
            for q in rects:
                if q is r:
                    continue
                self.assertFalse(r[0] <= q[2] and q[0] <= r[2] and r[1] <= q[3] and q[1] <= r[3], (r, q))

    def test_mockups_are_committed(self) -> None:
        for name in ("seed-boxes-7-9-store.png", "seed-boxes-7-9-storage.png"):
            self.assertTrue((ROOT / "docs" / "images" / name).is_file(), name)


# ------------------------------------------------------------------ Seed Storage

@needs_game
class SeedStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_seed_boxes", UPGRADES / "Extra Seed Boxes.dll",
                                                Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def game(self, owned=(1, 1, 1, 1, 1, 1), stock_level: int = 2):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.uc.mem_map(0, 0x1000)
        emu.texts = []
        emu.hook(0x0044A580, emu.record("sound"), 4)
        emu.hook(0x0044E894, lambda e: e.alloc(max(e.arg(0), 0x40)), 0)
        emu.hook(0x00401AA0, emu.record("button"), 0x18)
        emu.hook(0x0040B400, emu.record("control"), 4)
        emu.hook(0x00407A90, lambda e: e.alloc(0x40), 0)
        emu.hook(0x004092B0, lambda e: (e.texts.append(e.cstring(e.arg(0)).decode("latin-1")), 0)[1], 0x14)
        emu.hook(0x004342F0, lambda e: 0, 0)                            # the stock draw: nothing to see here
        emu.hook(0x00433930, lambda e: 0, 4)                            # the stock activate
        emu.hook(0x00421190, emu.record("fly"), 0x20)                   # a seed's flight (animation only)
        emu.hook(0x004347B0, lambda e: 0, 8)                            # the hover
        state = emu.alloc(0x60000)
        for at in [state + BOX + i * REC for i in range(RECORDS)] + [state + TRAY + i * REC for i in range(8)]:
            emu.call(EMPTY_RECORD, at)
        emu.write8(state + S_SECOND, int(stock_level >= 1))
        emu.write8(state + S_THIRD, int(stock_level >= 2))
        emu.call(emu.sym("_clear_new_chests"))
        for i, v in enumerate(owned):
            emu.call(emu.sym("_FtfpSeedBoxSetOwned"), i, v)
        scene = emu.alloc(0x400)
        for off in (0x20, 0x38, 0x40, 0x44):
            emu.write32(scene + off, emu.alloc(0x100))
        emu.write32(scene + 0x2C, state)
        jump(emu, 0x0041DE60, emu.sym("_stub_level"), 7)
        jump(emu, 0x004245F0, emu.sym("_stub_send"), 7)
        emu.state, emu.scene = state, scene
        return emu

    def arrow(self, emu, right: bool = True) -> None:
        emu.call(emu.sym("@scene_command@16"), 8, 8 if right else 7, ecx=emu.scene)

    def mouse(self, emu, msg: int, x: int, y: int) -> None:
        emu.call(emu.sym("@scene_mouse@20"), msg, x, y, ecx=emu.scene)

    def shown(self, emu) -> int:
        return emu.read32(emu.sym("_chest"))

    def label(self, emu) -> str:
        emu.texts.clear()
        emu.call(emu.sym("@scene_draw@8"), ecx=emu.scene)
        return emu.texts[-1] if emu.texts else ""

    @staticmethod
    def box_xy(row: int, col: int) -> tuple[int, int]:
        return 242 + 53 * col + 10, 46 + 152 * (row // 4) + 34 * (row % 4) + 10

    @staticmethod
    def tray_xy(slot: int) -> tuple[int, int]:
        return 0x15 + 0x2B * (slot % 4) + 10, 0x1E + 0x22 * (slot // 4) + 10

    def slot(self, emu, row: int, col: int) -> bytes:
        return bytes(emu.uc.mem_read(emu.state + BOX + (row * 10 + col) * REC, REC))

    def tray(self, emu, slot: int) -> bytes:
        return bytes(emu.uc.mem_read(emu.state + TRAY + slot * REC, REC))

    def test_events_are_version_2_with_six_boxes(self) -> None:
        emu = self.game(owned=(1, 1, 1, 1, 0, 1))
        self.assertEqual(emu.read32(emu.sym("_events")), 2)
        got = [emu.call(emu.sym("_FtfpSeedBoxOwned"), i) for i in range(7)]
        self.assertEqual(got, [1, 1, 1, 1, 0, 1, 0])
        chests, rows = emu.alloc(16), emu.alloc(16)
        emu.call(emu.sym("_FtfpSeedBoxesChestList"), emu.state, chests, rows, 3)
        self.assertEqual(emu.read32(rows + 8), 4)                        # the Ninth counts only after the Eighth

    def test_arrows_step_through_the_chests_that_have_a_box(self) -> None:
        emu = self.game()
        self.assertEqual(self.label(emu), "Boxes 1-3")
        steps = []
        for right in (True, True, True, False, False):
            self.arrow(emu, right)
            steps.append((self.shown(emu), self.label(emu)))
        self.assertEqual(steps, [(1, "Boxes 4-6"), (2, "Boxes 7-9"), (0, "Boxes 1-3"), (2, "Boxes 7-9"),
                                 (1, "Boxes 4-6")])
        emu = self.game(owned=(1, 1, 1, 0, 0, 0))                      # no Seventh: two pages
        self.arrow(emu)
        self.arrow(emu)
        self.assertEqual(self.shown(emu), 0)
        self.arrow(emu, right=False)
        self.assertEqual(self.shown(emu), 1)
        emu = self.game(owned=(0,) * 6)                                 # no Fourth: the arrows do nothing new
        self.arrow(emu)
        self.assertEqual((self.shown(emu), self.label(emu)), (0, ""))

    def test_each_chest_keeps_its_own_seeds_and_drawers(self) -> None:
        for owned, levels in (((1, 1, 1, 1, 0, 0), 0), ((1, 1, 1, 1, 1, 0), 1), ((1,) * 6, 2)):
            emu = self.game(owned)
            emu.uc.mem_write(emu.state + BOX, seed_record(1))
            self.arrow(emu)
            emu.uc.mem_write(emu.state + BOX, seed_record(2))
            self.arrow(emu)
            self.assertEqual(self.shown(emu), 2)
            self.assertEqual(emu.call(0x0041DE60, ecx=emu.state), levels)   # one drawer per box 7-9 owned
            emu.uc.mem_write(emu.state + BOX, seed_record(3))
            for tag in (3, 1, 2, 3):                                     # 7-9, round to 1-3, 4-6, 7-9
                self.assertEqual(struct.unpack_from("<i", self.slot(emu, 0, 0), 0x20)[0], tag)
                self.arrow(emu)
            self.assertEqual(emu.call(0x0041DE60, ecx=emu.state), 2)        # the stock chest: the stock rule

    def test_storing_and_taking_seeds_in_boxes_7_to_9(self) -> None:
        emu = self.game()
        self.arrow(emu)
        self.arrow(emu)                                                  # Boxes 7-9
        for row, col in ((0, 0), (5, 3), (11, 9)):                       # the Seventh, Eighth and Ninth's drawers
            emu.uc.mem_write(emu.state + TRAY + 2 * REC, seed_record(40 + row))
            self.mouse(emu, 2, *self.tray_xy(2))                         # pick up the tray seed
            self.assertEqual(emu.read32(emu.state + S_HELD), 12)
            self.mouse(emu, 2, *self.box_xy(row, col))                   # click it into the box
            self.assertEqual(self.slot(emu, row, col), seed_record(40 + row), (row, col))
            self.assertEqual(self.tray(emu, 2)[0x18], 0)
            self.assertEqual(emu.read32(emu.state + S_HELD), 0)
        self.arrow(emu)                                                  # away and back: still there
        self.arrow(emu, right=False)
        self.assertEqual(self.shown(emu), 2)
        self.assertEqual(self.slot(emu, 11, 9), seed_record(51))
        self.mouse(emu, 2, *self.box_xy(5, 3))                           # take one back out
        self.assertEqual(emu.read32(emu.state + S_HELD), 100 + 53)
        self.mouse(emu, 2, *self.tray_xy(6))
        self.assertEqual(self.tray(emu, 6), seed_record(45))
        self.assertEqual(self.slot(emu, 5, 3)[0x18], 0)

    def test_drag_and_drop_into_and_out_of_boxes_7_to_9(self) -> None:
        emu = self.game()
        self.arrow(emu, right=False)                                     # Boxes 7-9 the other way round
        self.assertEqual(self.shown(emu), 2)
        emu.uc.mem_write(emu.state + TRAY, seed_record(77))
        self.mouse(emu, 2, *self.tray_xy(0))
        self.mouse(emu, 3, *self.box_xy(9, 4))                           # released over the Ninth's drawer
        self.assertEqual(self.slot(emu, 9, 4), seed_record(77))
        self.mouse(emu, 2, *self.box_xy(9, 4))
        self.mouse(emu, 3, *self.box_xy(1, 1))                           # box to box
        self.assertEqual((self.slot(emu, 1, 1), self.slot(emu, 9, 4)[0x18]), (seed_record(77), 0))

    def test_a_locked_drawer_of_boxes_7_to_9_takes_nothing(self) -> None:
        emu = self.game(owned=(1, 1, 1, 1, 0, 0))                       # the Seventh only
        self.arrow(emu)
        self.arrow(emu)
        emu.uc.mem_write(emu.state + TRAY, seed_record(5))
        self.mouse(emu, 2, *self.tray_xy(0))
        self.mouse(emu, 2, *self.box_xy(4, 0))                           # the Eighth's drawer, not owned
        self.assertEqual(self.slot(emu, 4, 0)[0x18], 0)
        self.mouse(emu, 2, *self.box_xy(3, 9))                           # the Seventh's last slot
        self.assertEqual(self.slot(emu, 3, 9), seed_record(5))

    def send(self, emu, tag: int) -> tuple[int, int, int]:
        greenhouse, row, col = emu.alloc(0x100), emu.alloc(4), emu.alloc(4)
        emu.write32(greenhouse + 0x68, emu.state)
        emu.uc.mem_write(emu.state + TRAY + 3 * REC, seed_record(tag))
        ok = emu.call(0x004245F0, 3, row, col, ecx=greenhouse) & 0xFF
        return ok, emu.read32(row), emu.read32(col)

    def test_the_greenhouse_fills_boxes_1_3_then_4_6_then_7_9(self) -> None:
        emu = self.game()
        full = seed_record(9)
        for i in range(RECORDS):
            emu.uc.mem_write(emu.state + BOX + i * REC, full)
        emu.call(emu.sym("@scene_activate@12"), 1, ecx=emu.scene)
        self.arrow(emu)
        for i in range(RECORDS):
            emu.uc.mem_write(emu.state + BOX + i * REC, full)
        self.arrow(emu)
        self.arrow(emu)                                                  # back to boxes 1-3; 1-6 full
        self.assertEqual(self.send(emu, 123), (1, 0, 0))                 # into box 7's first slot
        self.assertEqual(emu.read32(emu.sym("_resident")), 2)
        self.assertEqual(self.slot(emu, 0, 0), seed_record(123))         # the flying seed's slot is on hand
        for n in range(1, 120):
            self.assertEqual(self.send(emu, 200 + n)[0], 1)
        self.assertEqual(self.send(emu, 999)[0], 0)                      # all nine full: the stock message
        self.assertEqual(emu.read32(emu.sym("_resident")), 0)            # the stock chest back

    def test_the_greenhouse_skips_boxes_7_to_9_until_the_seventh(self) -> None:
        emu = self.game(owned=(1, 1, 1, 0, 0, 0))
        full = seed_record(9)
        for i in range(RECORDS):
            emu.uc.mem_write(emu.state + BOX + i * REC, full)
        self.arrow(emu)
        for i in range(RECORDS):
            emu.uc.mem_write(emu.state + BOX + i * REC, full)
        self.arrow(emu)
        self.assertEqual(self.send(emu, 1)[0], 0)
        self.assertEqual(emu.read32(emu.sym("_resident")), 0)

    def test_the_chest_list_for_sort_seeds(self) -> None:
        emu = self.game(owned=(1, 1, 1, 1, 1, 0), stock_level=1)
        chests, rows = emu.alloc(16), emu.alloc(16)
        self.assertEqual(emu.call(emu.sym("_FtfpSeedBoxesChestList"), emu.state, chests, rows, 2), 0)
        self.assertEqual(emu.call(emu.sym("_FtfpSeedBoxesChestList"), emu.state, chests, rows, 3), 3)
        self.assertEqual([emu.read32(rows + 4 * c) for c in range(3)], [8, 12, 8])
        self.assertEqual(emu.read32(chests), emu.state + BOX)
        self.arrow(emu)
        self.arrow(emu)
        emu.call(emu.sym("_FtfpSeedBoxesChestList"), emu.state, chests, rows, 3)
        self.assertEqual(emu.read32(chests + 8), emu.state + BOX)        # boxes 7-9 on screen: in the array
        self.assertEqual(emu.read32(chests), emu.sym("_held"))

    # ------------------------------------------------------------ the sidecar
    def files(self, emu):
        from test_ds_store_animals import Files
        files = Files(emu)
        emu.hook_import("LoadLibraryW", lambda e: 0x7000, 4)
        emu.hook_import("GetModuleFileNameW", lambda e: files._put(e.arg(1), "C:\\Game\\Plant Tycoon.exe"), 12)
        return files

    PATH = "C:\\Docs\\LDW\\Plant Tycoon\\Plant Tycoon Fix Patcher Data\\Seed Boxes 3.dat"

    def empty_chest(self, emu) -> bytes:
        at = emu.alloc(RECORDS * REC)
        for i in range(RECORDS):
            emu.call(EMPTY_RECORD, at + i * REC)
        return bytes(emu.uc.mem_read(at, RECORDS * REC))

    def test_a_version_1_file_loads_with_nothing_lost(self) -> None:
        emu = self.game(owned=(0,) * 6)
        files = self.files(emu)
        chest = bytearray(self.empty_chest(emu))
        chest[0:REC] = seed_record(61)
        chest[119 * REC:120 * REC] = seed_record(62)
        old = struct.pack("<3I", 0x58425350, 1, 4 + RECORDS * REC) + bytes([1, 1, 0, 0]) + bytes(chest)
        files.files[self.PATH] = old
        emu.call(emu.sym("_on_load"), emu.state, 3)
        self.assertEqual([emu.call(emu.sym("_FtfpSeedBoxOwned"), i) for i in range(6)], [1, 1, 0, 0, 0, 0])
        held = emu.sym("_held")
        self.assertEqual(bytes(emu.uc.mem_read(held + RECORDS * REC, RECORDS * REC)), bytes(chest))
        self.assertEqual(bytes(emu.uc.mem_read(held + 2 * RECORDS * REC, RECORDS * REC)), self.empty_chest(emu))
        self.assertEqual(files.files[self.PATH], old)                    # read, never rewritten on load
        emu.call(emu.sym("_before_save"), emu.state, 3)                  # the next save writes version 2
        new = files.files[self.PATH]
        self.assertEqual(struct.unpack_from("<3I", new), (0x58425350, 2, 8 + 2 * RECORDS * REC))
        self.assertEqual(new[12:20], bytes([1, 1, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(new[20:20 + RECORDS * REC], bytes(chest))
        self.assertEqual(new[20 + RECORDS * REC:], self.empty_chest(emu))

    def test_round_trip_new_game_and_damaged_files(self) -> None:
        emu = self.game()
        files = self.files(emu)
        self.arrow(emu)
        emu.uc.mem_write(emu.state + BOX + 7 * REC, seed_record(70))
        self.arrow(emu)
        emu.uc.mem_write(emu.state + BOX + 118 * REC, seed_record(71))   # boxes 7-9 on screen at the save
        emu.call(emu.sym("_before_save"), emu.state, 3)
        self.assertEqual(emu.read32(emu.sym("_resident")), 0)            # the save holds the stock chest
        saved = files.files[self.PATH]
        self.assertNotIn(self.PATH + ".tmp", files.files)
        self.assertEqual(len(saved), 12 + 8 + 2 * RECORDS * REC)
        emu2 = self.game(owned=(0,) * 6)
        files2 = self.files(emu2)
        files2.files[self.PATH] = saved
        emu2.call(emu2.sym("_on_load"), emu2.state, 3)
        self.assertEqual([emu2.call(emu2.sym("_FtfpSeedBoxOwned"), i) for i in range(6)], [1] * 6)
        self.arrow(emu2)
        self.assertEqual(bytes(emu2.uc.mem_read(emu2.state + BOX + 7 * REC, REC)), seed_record(70))
        self.arrow(emu2)
        self.assertEqual(bytes(emu2.uc.mem_read(emu2.state + BOX + 118 * REC, REC)), seed_record(71))
        emu2.call(emu2.sym("_before_save"), emu2.state, 3)
        self.assertEqual(files2.files[self.PATH], saved)                 # byte for byte
        emu2.call(emu2.sym("_on_new_game"))                              # a new game: nothing owned, empty
        self.assertEqual([emu2.call(emu2.sym("_FtfpSeedBoxOwned"), i) for i in range(6)], [0] * 6)
        held = emu2.sym("_held")
        for c in (1, 2):
            self.assertEqual(bytes(emu2.uc.mem_read(held + c * RECORDS * REC, RECORDS * REC)), self.empty_chest(emu2))
        for damaged in (saved[:-1], saved + b"\0", saved[:4] + struct.pack("<I", 3) + saved[8:], b"PSBX"):
            emu3 = self.game(owned=(1,) * 6)
            files3 = self.files(emu3)
            files3.files[self.PATH] = damaged
            emu3.call(emu3.sym("_on_load"), emu3.state, 3)
            self.assertEqual([emu3.call(emu3.sym("_FtfpSeedBoxOwned"), i) for i in range(6)], [0] * 6)
            self.assertEqual(files3.files.get(self.PATH + ".unreadable"), damaged)   # set aside, never deleted
            self.assertNotIn(self.PATH, files3.files)


class BackupNamingTests(unittest.TestCase):
    """The version 2 file keeps the version 1 name, so the backups' slot naming still finds it (and the
    copies the DLL makes: ".tmp" while writing, ".unreadable" when set aside)."""

    def test_every_seed_boxes_file_is_its_slot(self) -> None:
        import save_backup
        for slot in (1, 2, 3, 4, 5):
            for suffix in (".dat", ".dat.tmp", ".dat.unreadable"):
                name = Path("Plant Tycoon Fix Patcher Data") / f"Seed Boxes {slot}{suffix}"
                self.assertEqual(save_backup.file_slot("plant", name), slot, name)
            self.assertEqual(save_backup.file_slot("plant", Path("Plant Tycoon Fix Patcher Data")
                                                   / f"Seed Boxes {20 + slot}.dat"), slot)    # the game's backups
        source = (ROOT / "native" / "ftfp_seed_boxes" / "ftfp_seed_boxes.c").read_text(encoding="utf-8")
        self.assertIn('L"\\\\Seed Boxes "', source)
        self.assertIn('L".unreadable"', source)
        self.assertIn('L".tmp"', source)


# ------------------------------------------------------------------ every patch at once

PLANT_HEADERS = ("ftfp_new_flowers/flower_sites.h", "ftfp_plant_upgrades/upgrade_sites.h",
                 "ftfp_seed_boxes/box_sites.h", "ftfp_extra_greenhouses/greenhouse_sites.h")


def header_sites() -> list[tuple[int, int, str]]:
    import re
    sites = []
    for name in PLANT_HEADERS:
        text = (ROOT / "native" / name).read_text(encoding="utf-8")
        lengths = dict(re.findall(r"#define SITE_(\w+)_LEN (\d+)", text))
        for site, va in re.findall(r"#define SITE_(\w+)_VA (0x[0-9A-Fa-f]+)u", text):
            sites.append((int(va, 16), int(lengths[site]), f"{name}:{site}"))
    return sites


@needs_game
class EveryPatchTests(unittest.TestCase):
    """Enable All: every Plant setting on at once. Every DLL site is still the stock code in that
    executable (so each companion's all-or-none install finds what it expects), no site overlaps a
    manifest patch, the startup loader or another DLL's site, and the three companions this feature
    changes install on it and log so."""

    @classmethod
    def setUpClass(cls) -> None:
        import ds_fish_loader
        import plant_patcher
        import tycoon_fix_patcher as combined
        cls.manifest = combined.load_manifest("plant")
        cls.enabled = {s["id"] for s in cls.manifest["settings"]}
        vanilla = PLANT_EXE.read_bytes()
        records = plant_patcher.active_patch_records(cls.manifest, cls.enabled)
        patched, _ = plant_patcher.apply_patch_bytes(vanilla, records)
        cls.profile = ds_fish_loader.plant_profile(cls.enabled)
        patched, _ = ds_fish_loader.append_startup_loader(patched, cls.profile)
        cls.records, cls.vanilla, cls.patched = records, vanilla, patched
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.tmp.name) / "Plant Tycoon.exe"
        cls.exe.write_bytes(patched)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_enable_all_is_the_pinned_build(self) -> None:
        import hashlib
        import plant_patcher
        key = plant_patcher.settings_key(self.enabled, self.manifest)
        pin = self.manifest["patched_sha256_by_settings"].get(key)
        self.assertIsNotNone(pin, key)
        self.assertEqual(hashlib.sha256(self.patched).hexdigest().upper(), pin)
        for s in ("plant_upgrades", "sort_seeds", "extra_greenhouses", "extra_nurseries", "new_flowers",
                  "time_warp", "free_upgrades", "add_money", "seed_refresh_key"):
            self.assertIn(s, self.enabled)

    def test_no_site_overlaps_and_every_site_is_stock(self) -> None:
        import ds_fish_loader
        import render_extra_greenhouses_preview as R
        fixed = header_sites()
        for va, length, name in fixed:
            at = R.file_offset(self.vanilla, va)
            self.assertEqual(self.patched[at:at + length], self.vanilla[at:at + length], name)
        for _off, va, length, what in ds_fish_loader.described_changes(self.profile):
            if va is not None:
                fixed.append((va, length, "startup loader: " + what[:30]))
        # manifest patches by their real VA (file offset -> VA through the sections)
        pe = struct.unpack_from("<I", self.vanilla, 0x3C)[0]
        count = struct.unpack_from("<H", self.vanilla, pe + 6)[0]
        table = pe + 24 + struct.unpack_from("<H", self.vanilla, pe + 20)[0]
        sections = [struct.unpack_from("<IIII", self.vanilla, table + 40 * i + 8) for i in range(count)]
        for record in self.records:
            offset = int(record["offset"], 16)
            for _vs, rva, raw_size, raw in sections:
                if raw <= offset < raw + raw_size:
                    fixed.append((0x400000 + rva + offset - raw, len(bytes.fromhex(record["replacement"])),
                                  f"patch {record['id']}"))
        fixed = sorted(set(fixed))
        for (a, la, na), (b, lb, nb) in zip(fixed, fixed[1:]):
            if na.startswith("patch ") and nb.startswith("patch "):
                continue                                              # the manifest's own, checked by its tests
            self.assertLessEqual(a + la, b, f"{na} 0x{a:X}+{la} overlaps {nb} 0x{b:X}")

    def startup(self, project: str, dll: Path, export: str, log: str) -> tuple[int, str]:
        from test_ds_store_animals import Files
        build = Path(self.tmp.name) / project
        build.mkdir(exist_ok=True)
        built, symbols = E.build_with_map(project, dll, build)
        emu = E.Emulator(self.exe, built, symbols)
        emu.uc.mem_map(0, 0x1000)                                       # fs:[0], the __try chain
        emu.hook_printf()
        files = Files(emu)
        emu.hook_import("GetModuleFileNameW", lambda e: files._put(e.arg(1), "C:\\Game\\Plant Tycoon.exe"), 12)
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)
        emu.hook_import("LoadLibraryW", lambda e: 0, 4)
        emu.hook_import("GetFileAttributesW", lambda e: 0xFFFFFFFF, 4)
        emu.hook_import("GetProcAddress", lambda e: 0, 8)
        emu.hook_import("VirtualProtect", lambda e: (e.write32(e.arg(3), 0x20), 1)[1], 16)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.hook_import("GetPrivateProfileIntW", lambda e: e.arg(2), 16)        # an .ini setting: its default
        emu.hook_import("LoadLibraryExW", lambda e: 0, 12)
        result = emu.call(emu.sym(export))
        logs = [data for path, data in files.files.items() if path.endswith("\\" + log)]   # beside the game or the DLL
        text = b"".join(logs).decode("latin-1")
        return result, text

    def test_the_companions_install_on_the_enable_all_build(self) -> None:
        result, log = self.startup("ftfp_seed_boxes", UPGRADES / "Extra Seed Boxes.dll", "_FtfpSeedBoxesStartup@0",
                                   "Extra Seed Boxes.log")
        self.assertNotEqual(result, 0)
        self.assertEqual(log, "Seed Boxes: installed (all sites)\r\n")
        result, log = self.startup("ftfp_sort_seeds", ROOT / "assets" / "plant_tycoon_sort_seeds" / "Sort Seeds.dll",
                                   "_FtfpStartup@0", "Sort Seeds.log")
        self.assertEqual((result, log), (1, "Sort Seeds: installed\r\n"))
        result, log = self.startup("ftfp_plant_upgrades", UPGRADES / "Store Upgrades and Items.dll",
                                   "_FtfpUpgradesStartup@0", "Store Upgrades and Items.log")
        self.assertNotEqual(result, 0)
        self.assertIn("installed", log)
        self.assertNotIn("NOT installed", log)

    def test_the_other_plant_companions_install_on_the_enable_all_build(self) -> None:
        for project, dll, log in (("ftfp_new_flowers", "plant_tycoon_flowers/Unused Flowers.dll", "Unused Flowers.log"),
                                  ("ftfp_extra_greenhouses", "plant_tycoon_greenhouses/Extra Greenhouses.dll",
                                   "Extra Greenhouses.log"),
                                  ("ftfp_greenhouse_counts", "plant_tycoon_counts/Greenhouse Counts.dll", None),
                                  ("ftfp_plant_prices", "plant_tycoon_optimize_prices/Optimize Prices.dll",
                                   "Optimize Prices.log")):
            result, text = self.startup(project, ROOT / "assets" / dll, "_FtfpStartup@0", log or "-")
            self.assertNotEqual(result, 0, project)
            if log:
                self.assertIn("installed", text, project)
                self.assertNotIn("NOT installed", text, project)


# ------------------------------------------------------------------ Sort Seeds

@needs_game
class SortSeedsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_sort_seeds", ROOT / "assets" / "plant_tycoon_sort_seeds" / "Sort Seeds.dll", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_sort_seeds_fills_1_3_then_4_6_then_7_9(self) -> None:
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        state = emu.alloc(0x60000)
        chests = [state + BOX, emu.alloc(RECORDS * REC), emu.alloc(RECORDS * REC)]
        for c in chests:
            for i in range(RECORDS):
                emu.call(EMPTY_RECORD, c + i * REC)
        tags = []
        for c, count in ((0, 110), (1, 90), (2, 100)):
            for i in range(count):
                tag = 1000 * c + i
                tags.append(tag)
                emu.uc.mem_write(chests[c] + (119 - i) * REC, seed_record(tag, 1 + (tag * 7) % 23, 1 + tag % 37))
        listed = emu.thunk()

        def chest_list(e):
            self.assertEqual(e.arg(3), 3)                               # Sort Seeds asks for three
            for c in range(3):
                e.write32(e.arg(1) + 4 * c, chests[c])
                e.write32(e.arg(2) + 4 * c, 12)
            return 3
        emu.hook(listed, chest_list, 0)
        emu.write32(emu.sym("_boxes_chests"), listed)
        scene = emu.alloc(0x100)
        emu.write32(scene + 0x2C, state)
        emu.call(emu.sym("_sort_seeds"), scene)
        self.assertEqual(emu.read32(emu.sym("_last_sorted"), signed=True), 300)
        counts, seen = [], []
        for c in chests:
            present = [bytes(emu.uc.mem_read(c + i * REC, REC)) for i in range(RECORDS)]
            counts.append(sum(r[0x18] != 0 for r in present))
            seen += [struct.unpack_from("<i", r, 0x20)[0] for r in present if r[0x18]]
        self.assertEqual(counts, [120, 120, 60])
        self.assertEqual(sorted(seen), sorted(tags))                    # every seed once


if __name__ == "__main__":
    unittest.main()
