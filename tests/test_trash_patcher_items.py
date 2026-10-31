"""The trash can takes what the Fix Patcher adds, the way it takes the stock items (both games).

Fish Tycoon: the stock trash takes a fish (and asks "Delete this fish?" while it lives); it never
takes a supply or an ornament. The patcher's
  * Exotic Fish Eggs, Radioactive Growth Hormone, Revival Potion and ClonaFish (DS Store Items) are
    thrown away when let go on the can (the release 0x421B20 calls the use 0x420B70 at 0x421B52);
  * Multiple Ornaments' copies go after the game's question (any tank, Tanks 4-6 too);
  * the Moray Eel and its rock go together, wherever the other one is (Tanks 4-6 too).
Plant Tycoon: the stock trash sells seeds (Legendary and new-flower seeds too) and deletes plants;
it never takes a chemical. The patcher's chemicals (36-39, 48-49) are thrown away when let go or
pressed on the can, without the selected plant being asked about or emptied.

The tools (Fish: the food; Plant: held items 1-4, the watering can, net and the rest) are never
thrown away, and nothing other than the dropped item changes.

Everything runs in Unicorn: the vanilla executables' own code with each DLL rebuilt from its
source (tests/store_emulator.py).
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

import test_fish_window as W  # noqa: E402  the maximized window's letterbox maths

FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
STORE_DLL = ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll"
ORNAMENTS_DLL = ROOT / "assets" / "fish_tycoon_ornaments" / "Multiple Ornaments.dll"
UPGRADES_DLL = ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll"


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


def page_zero(emu) -> None:
    """fs:[0] (the functions' SEH frames) reads and writes linear address 0 in Unicorn."""
    emu.uc.mem_map(0, 0x1000)


# ================================================================== Fish Tycoon

STATE_SIZE = 0x1E600
FISH, TANK, REC = 0x390, 0x51EC, 0x288
ORN_BASE, ORN_STRIDE = 0x5208, 0x2C
S_TANK = 0x384
SLOT = 0x2B8                               # supply slot k: state + 0x2B8 + k * 0x1C (item, present, count, icon, cursor, x)
NOTHING = 0x63
EXOTIC, RGH, REVIVAL, CLONA, MUTA_FIN, MUTA_BODY = 28, 29, 30, 31, 32, 33
ICON = {EXOTIC: 224, RGH: 236, REVIVAL: 239, CLONA: 242, MUTA_FIN: 247, MUTA_BODY: 250}
CURSOR = {EXOTIC: 224, RGH: 237, REVIVAL: 240, CLONA: 243, MUTA_FIN: 248, MUTA_BODY: 251}
# The tank screen's rectangles (0x41CE20-0x41CE88): left, top, right, bottom.
TRASH = (650, 541, 689, 600)
ISOLATION = (500, 489, 639, 600)
TANK_RECT = (2, 51, 798, 489)
SPR_ROCK, FIN_EEL, FTCA = 228, 32, 0x41435446


def fish_slot(emu, k: int) -> tuple[int, ...]:
    return struct.unpack("<6i", emu.uc.mem_read(emu.state + SLOT + k * 0x1C, 24))


def maximized_trash_points() -> list[tuple[int, int]]:
    """Clicks on the trash can in a maximized window (1920 x 1017, 1366 x 705), mapped back to the
    game's 800 x 600 as Maximizable Window maps every mouse message (test_fish_window checks the
    maths against the DLL)."""
    points = []
    for cw, ch in ((1920, 1017), (1366, 705), (2560, 1377)):
        x, y, w, h = W.fit(cw, ch)
        for gx, gy in ((TRASH[0] + 1, TRASH[1] + 1), ((TRASH[0] + TRASH[2]) // 2, (TRASH[1] + TRASH[3]) // 2),
                       (TRASH[2] - 1, TRASH[3] - 1)):
            cx, cy = x + gx * w // 800 + 1, y + gy * h // 600 + 1             # a client pixel over that game pixel
            points.append((W.to_picture(cx, x, w, 800), W.to_picture(cy, y, h, 600)))
    return points


@_needs(FISH_EXE)
class FishSupplyTrashTests(unittest.TestCase):
    """The store's supplies let go on the trash: the release (0x421B20) with the DLL's call at 0x421B52."""

    @classmethod
    def setUpClass(cls) -> None:
        import test_fish_30 as F
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_ds_store", STORE_DLL, Path(cls.tmp.name))
        cls.universal_exe = Path(cls.tmp.name) / "universal.exe"
        cls.universal_exe.write_bytes(F.patched_exe({"universal_supply_slots"}))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def tank(self, universal: bool = False, use_hook: bool = False, current: int = 0):
        emu = E.Emulator(self.universal_exe if universal else FISH_EXE, self.dll, self.symbols)
        site = 0x421B52
        emu.uc.mem_write(site, b"\xE8" + struct.pack("<i", emu.sym("_stub_supply_drop") - (site + 5)))
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)                 # no Extra Tanks.dll
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        emu.hook(0x00425120, lambda e: 0x5000, 0)
        emu.hook(0x004251A0, emu.record("sound", args=1), 4)                # no sound object: none played
        emu.hook(0x0040AE20, lambda e: 0, 4)
        if use_hook:
            emu.hook(0x00420B70, emu.record("use", args=2), 8)
        state, impl = emu.alloc(STATE_SIZE), emu.alloc(0x100)
        for at in range(0, STATE_SIZE, 4):                                   # every field: a pattern
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        emu.write32(state + 0x1E4E8, 0xFFFFFFFF)                              # no fish held
        emu.write32(state + S_TANK, current)
        for k in range(4):                                                    # every slot empty
            emu.uc.mem_write(state + SLOT + k * 0x1C, struct.pack("<6i", 0, 0, 0, 0, 0, k * 0x30 + 0x1E))
        emu.write32(impl + 0x28, NOTHING)                                     # no ornament held
        emu.write32(impl + 0x34, state)
        for offset in (0x3C, 0x44, 0x4C, 0x50):
            emu.write32(impl + offset, emu.alloc(0x40))
        for base, rect in ((0x88, TRASH), (0x98, ISOLATION), (0xA8, TANK_RECT)):
            for i, value in enumerate(rect):
                emu.write32(impl + base + 4 * i, value)
        emu.state, emu.impl = state, impl
        return emu

    def put(self, emu, k: int, item: int, count: int, icon: int | None = None, cursor: int | None = None) -> None:
        emu.uc.mem_write(emu.state + SLOT + k * 0x1C, struct.pack(
            "<6i", item, 1, count, ICON.get(item, 0x7A) if icon is None else icon,
            CURSOR.get(item, 0x7B) if cursor is None else cursor, k * 0x30 + 0x1E))

    def drop(self, emu, k: int, x: int, y: int) -> None:
        emu.write32(emu.impl + 0x1C, k)                                       # slot k held
        emu.call(0x00421B20, x, y, ecx=emu.impl)

    def state(self, emu) -> bytes:
        return bytes(emu.uc.mem_read(emu.state, STATE_SIZE))

    # (item, slot k, count, universal slots)
    CASES = ((EXOTIC, 3, 3, False), (RGH, 2, 3, False), (REVIVAL, 2, 2, False), (CLONA, 2, 1, False),
             (MUTA_FIN, 2, 3, False), (MUTA_BODY, 2, 1, False),
             (EXOTIC, 1, 4, True), (RGH, 3, 6, True), (REVIVAL, 1, 3, True), (CLONA, 2, 9, True),
             (MUTA_FIN, 1, 5, True), (MUTA_BODY, 3, 6, True))

    def test_each_store_supply_on_the_trash_is_thrown_away_whole(self) -> None:
        points = [(TRASH[0], TRASH[1]), (TRASH[2], TRASH[3]), (669, 570)] + maximized_trash_points()
        for item, k, count, universal in self.CASES:
            for x, y in points:
                with self.subTest(item=item, k=k, universal=universal, at=(x, y)):
                    emu = self.tank(universal)
                    self.put(emu, k, item, count)
                    other = (k % 3) + 1                                       # another slot keeps its own supply
                    self.put(emu, other, 3, 2, 0x7A, 0x7B)
                    before = bytearray(self.state(emu))
                    self.drop(emu, k, x, y)
                    self.assertEqual(fish_slot(emu, k), (0, 0, 0, 0, 0, k * 0x30 + 0x1E))   # every dose or hatch
                    self.assertEqual(emu.read32(emu.impl + 0x1C), NOTHING)               # nothing held
                    self.assertIn(("sound", (4,)), emu.calls)                            # the fish trash's sound
                    self.assertNotIn("hint", [c[0] for c in emu.calls])
                    self.assertNotIn("use", [c[0] for c in emu.calls])
                    at = SLOT + k * 0x1C
                    before[at:at + 20] = bytes(20)
                    self.assertEqual(self.state(emu), bytes(before))                     # nothing else changed

    def test_dropped_anywhere_else_it_is_kept_as_stock(self) -> None:
        # Off the can by one pixel, in the bottom bar, on the isolation tank: the stock hint, kept.
        for item, k, count, universal in self.CASES:
            for (x, y), hint in (((TRASH[0] - 1, 570), 0xD), ((TRASH[2] + 1, 570), 0xD), ((669, TRASH[1] - 1), 0xD),
                                 ((300, 560), 0xD), ((560, 550), 0xC)):
                with self.subTest(item=item, k=k, universal=universal, at=(x, y)):
                    emu = self.tank(universal)
                    self.put(emu, k, item, count)
                    before = self.state(emu)
                    self.drop(emu, k, x, y)
                    self.assertEqual(self.state(emu), before)
                    self.assertIn(("hint", (hint,)), emu.calls)
                    self.assertEqual(emu.read32(emu.impl + 0x1C), NOTHING)
                    self.assertNotIn(("sound", (4,)), emu.calls)

    def test_dropped_in_the_tank_it_is_used_as_before(self) -> None:
        for item, k, count, universal in self.CASES:
            emu = self.tank(universal, use_hook=True)
            self.put(emu, k, item, count)
            before = self.state(emu)
            self.drop(emu, k, 400, 300)
            self.assertEqual(emu.calls, [("use", (400, 300))])
            self.assertEqual(self.state(emu), before)

    def test_food_and_the_stock_supplies_are_never_thrown_away(self) -> None:
        # The food (slot #1, a tool) and every stock supply: medicines, chemicals, eggs, the starter eggs.
        stock = ((0, 1, 10, 0x77, 0x78), (1, 1, 3, 0x79, 0x7C), (1, 0, 3, 0x7D, 0x7C), (2, 2, 3, 0x7A, 0x7B),
                 (2, 3, 3, 0x7A, 0x7B), (2, 4, 1, 0x7A, 0x7B), (3, 5, 1, 0x80, 0x80), (3, 6, 1, 0x81, 0x81),
                 (3, 7, 1, 0x82, 0x82), (3, 26, 1, 0x80, 0x80))
        for universal in (False, True):
            for k, item, count, icon, cursor in stock:
                for x, y in ((669, 570), maximized_trash_points()[1]):
                    with self.subTest(universal=universal, k=k, item=item, at=(x, y)):
                        emu = self.tank(universal)
                        self.put(emu, k, item, count, icon, cursor)
                        before = self.state(emu)
                        self.drop(emu, k, x, y)
                        self.assertEqual(self.state(emu), before)
                        self.assertIn(("hint", (0xD,)), emu.calls)                     # the stock hint
                        self.assertNotIn(("sound", (4,)), emu.calls)

    def test_the_tank_on_screen_does_not_matter(self) -> None:
        # The slots belong to no tank: Tank 1, 2 or the Sale Tank, or Tank 4-6 shown in one of their
        # places (Extra Tanks swaps the tank block, never the slots). No fish or ornament changes.
        for current in (0, 1, 2):
            emu = self.tank(current=current)
            self.put(emu, 2, RGH, 3)
            before = self.state(emu)
            self.drop(emu, 2, 669, 570)
            after = self.state(emu)
            self.assertEqual(after[FISH:FISH + 4 * TANK], before[FISH:FISH + 4 * TANK])
            self.assertEqual(fish_slot(emu, 2)[:5], (0, 0, 0, 0, 0))


def animal_record(fin: int, health: int = 80) -> bytes:
    r = bytearray(REC)
    struct.pack_into("<IIii", r, 0, 99, 0, 21, 21)
    struct.pack_into("<II", r, 0x14, FTCA, fin)
    struct.pack_into("<iii", r, 0x3C, health, 0, 90)
    struct.pack_into("<ii", r, 0x4C, 22, fin)
    return bytes(r)


def rock_record(home: bool = False) -> bytes:
    r = bytearray(ORN_STRIDE)
    r[0] = 1
    struct.pack_into("<ii", r, 4, 300, 420)
    struct.pack_into("<iii", r, 0x1C, 40, 80, SPR_ROCK + (1 if home else 0))
    return bytes(r)


@_needs(FISH_EXE)
class FishEelAndRockTests(unittest.TestCase):
    """The Moray Eel and its rock go together, also when the other one is in Tank 4, 5 or 6."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_ds_store", STORE_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def world(self, answer_yes: bool = True):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        page_zero(emu)
        state, impl = emu.alloc(STATE_SIZE), emu.alloc(0x100)
        emu.blocks = [emu.alloc(TANK + 5 * REC) for _ in range(3)]          # Extra Tanks' held tanks
        held = emu.thunk()
        emu.hook(held, lambda e: e.blocks[e.arg(0)] if 0 <= e.arg(0) < 3 else 0, 4)
        emu.hook_import("GetModuleHandleW", lambda e: 0x7000 if e.wstring(e.arg(0)) == "Extra Tanks.dll" else 0, 4)
        emu.hook_import("GetProcAddress", lambda e: held if e.cstring(e.arg(1)) == b"FtfpExtraTanksHeld" else 0, 8)
        emu.hook(0x004221A0, emu.record("question", args=1), 8)
        emu.hook(0x00401D00, lambda e: 0 if answer_yes else 1, 8)
        emu.hook(0x00422440, lambda e: 0, 0)
        emu.hook(0x00425120, lambda e: 0x5000, 0)
        emu.hook(0x004251A0, emu.record("sound", args=1), 4)
        emu.hook(0x0040AE20, lambda e: 0, 4)
        emu.hook(0x00415380, emu.record("view", args=4), 16)
        emu.write32(0x0045ABDC, state)
        emu.write32(impl + 0x34, state)
        emu.write32(impl + 0x28, NOTHING)
        for offset in (0x3C, 0x44, 0x4C, 0x50):
            emu.write32(impl + offset, emu.alloc(0x40))
        for i, value in enumerate(TRASH):
            emu.write32(impl + 0x88 + 4 * i, value)
        emu.state, emu.impl = state, impl
        return emu

    def place(self, emu, tank: int, record: bytes) -> int:
        buffer = emu.alloc(REC)
        emu.uc.mem_write(buffer, record)
        k = emu.call(emu.sym("_place_animal"), emu.state, tank, buffer)
        return emu.call(emu.sym("_animal_slot"), emu.state, tank, k)

    def held_animal(self, emu, e: int, k: int) -> int:
        return emu.blocks[e] + TANK + k * REC

    def held_rock(self, emu, e: int, k: int) -> int:
        return emu.blocks[e] + (ORN_BASE - FISH) + k * ORN_STRIDE

    def everything(self, emu) -> bytes:
        return bytes(emu.uc.mem_read(emu.state, STATE_SIZE)) + b"".join(
            bytes(emu.uc.mem_read(b, TANK + 5 * REC)) for b in emu.blocks)

    def test_the_rock_in_the_trash_takes_the_eel_from_tank_4_6(self) -> None:
        for e in range(3):
            emu = self.world()
            emu.uc.mem_write(emu.state + ORN_BASE + 2 * ORN_STRIDE, rock_record())     # Tank 1, ornament 2
            emu.uc.mem_write(self.held_animal(emu, e, 1), animal_record(FIN_EEL))
            emu.uc.mem_write(self.held_animal(emu, e, 0), animal_record(30))         # a puffer stays
            before = bytearray(self.everything(emu))
            emu.write32(emu.impl + 0x28, 2)
            self.assertEqual(emu.call(emu.sym("_rock_trash"), emu.impl, 669, 570), 1)
            self.assertEqual(emu.calls[0], ("question", (0xAC,)))
            self.assertIn(("sound", (4,)), emu.calls)
            self.assertEqual(emu.read32(emu.impl + 0x28), NOTHING)
            self.assertEqual(emu.read32(self.held_animal(emu, e, 1)), 0)              # the eel is gone
            self.assertEqual(bytes(emu.uc.mem_read(emu.state + ORN_BASE + 2 * ORN_STRIDE, ORN_STRIDE)),
                             bytes(ORN_STRIDE))
            # Nothing else: the eel's record is cleared exactly as REMOVE_FISH clears one.
            after = self.everything(emu)
            changed = [i for i in range(len(after)) if after[i] != before[i]]
            rock = ORN_BASE + 2 * ORN_STRIDE
            eel = STATE_SIZE + e * (TANK + 5 * REC) + TANK + REC
            self.assertTrue(all(rock <= i < rock + ORN_STRIDE or eel <= i < eel + REC for i in changed))
            self.assertEqual(after[eel - REC:eel], before[eel - REC:eel])             # the puffer

    def test_the_eel_in_the_trash_takes_the_rock_from_tank_4_6(self) -> None:
        # The stock fish trash (0x41E720) with the DLL's jump at 0x41E809, on a swimming eel in Tank 1.
        for e in range(3):
            emu = self.world()
            site = 0x41E809
            emu.uc.mem_write(site, b"\xE9" + struct.pack("<i", emu.sym("_stub_fish_trash") - (site + 5)))
            slot = self.place(emu, 0, animal_record(FIN_EEL))
            emu.uc.mem_write(self.held_rock(emu, e, 4), rock_record())
            emu.uc.mem_write(self.held_rock(emu, e, 1), rock_record(home=True))        # a home rock stays
            emu.call(0x0041E720, 0, slot, 7, ecx=emu.impl)
            self.assertEqual(emu.calls[0], ("question", (0xAC,)))                      # "Delete this fish?"
            self.assertEqual(emu.read32((emu.state + FISH + slot * REC) & 0xFFFFFFFF), 0)   # the eel is gone
            self.assertEqual(bytes(emu.uc.mem_read(self.held_rock(emu, e, 4), ORN_STRIDE)), bytes(ORN_STRIDE))
            self.assertEqual(bytes(emu.uc.mem_read(self.held_rock(emu, e, 1), ORN_STRIDE)), rock_record(home=True))

    def test_a_rock_in_a_stock_tank_still_goes_first(self) -> None:
        emu = self.world()
        site = 0x41E809
        emu.uc.mem_write(site, b"\xE9" + struct.pack("<i", emu.sym("_stub_fish_trash") - (site + 5)))
        slot = self.place(emu, 0, animal_record(FIN_EEL))
        emu.uc.mem_write(emu.state + ORN_BASE + 1 * TANK + 0 * ORN_STRIDE, rock_record())   # Tank 2
        emu.uc.mem_write(self.held_rock(emu, 0, 0), rock_record())                          # Tank 4
        emu.call(0x0041E720, 0, slot, 7, ecx=emu.impl)
        self.assertEqual(bytes(emu.uc.mem_read(emu.state + ORN_BASE + TANK, ORN_STRIDE)), bytes(ORN_STRIDE))
        self.assertEqual(bytes(emu.uc.mem_read(self.held_rock(emu, 0, 0), ORN_STRIDE)), rock_record())

    def test_no_keeps_both(self) -> None:
        emu = self.world(answer_yes=False)
        emu.uc.mem_write(emu.state + ORN_BASE, rock_record())
        emu.uc.mem_write(self.held_animal(emu, 0, 0), animal_record(FIN_EEL))
        before = self.everything(emu)
        emu.write32(emu.impl + 0x28, 0)
        self.assertEqual(emu.call(emu.sym("_rock_trash"), emu.impl, 669, 570), 0)
        self.assertEqual(self.everything(emu), before)

    def test_off_the_can_the_rock_is_kept(self) -> None:
        emu = self.world()
        emu.uc.mem_write(emu.state + ORN_BASE, rock_record())
        emu.uc.mem_write(self.held_animal(emu, 0, 0), animal_record(FIN_EEL))
        before = self.everything(emu)
        emu.write32(emu.impl + 0x28, 0)
        self.assertEqual(emu.call(emu.sym("_rock_trash"), emu.impl, TRASH[0] - 1, 570), 0)
        self.assertEqual(self.everything(emu), before)
        self.assertEqual(emu.calls, [])


@_needs(FISH_EXE)
class FishOrnamentCopyTrashTests(unittest.TestCase):
    """Multiple Ornaments' copies in the trash, in Tanks 1-3 and in Tanks 4-6 (shown in a stock place)."""

    @classmethod
    def setUpClass(cls) -> None:
        import test_multiple_ornaments as M
        cls.M = M
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_ornaments", ORNAMENTS_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def world(self, logical: int, answer_yes: bool = True):
        emu = self.M.EmulatedTests.world(self)
        emu.hook(0x00401D00, lambda e: 0 if answer_yes else 1, 8)
        emu.hook(0x0041EA10, emu.record("settle", args=4), 16)
        emu.hook(0x0041E9C0, emu.record("place", args=2), 8)
        mapper = emu.thunk()
        emu.hook(mapper, lambda e: logical if e.arg(0) == 0 else e.arg(0), 0)   # the tank in stock place 0
        emu.write32(emu.sym("_tank_map"), mapper)
        emu.write32(emu.state + S_TANK, 0)
        for i, value in enumerate(TRASH):
            emu.write32(emu.scene + 0x88 + 4 * i, value)
        return emu

    def copies(self, emu, tank: int, n: int) -> list[bytes]:
        recs = [self.M.record(100 + 90 * k, 433) for k in range(n)]
        for k, rec in enumerate(recs):
            emu.uc.mem_write(emu.sym("_copies") + (tank * 10 + k) * ORN_STRIDE, rec)
        emu.write32(emu.sym("_copy_count") + 4 * tank, n)
        return recs

    def drop(self, emu, tank: int, k: int, x: int, y: int) -> int:
        emu.write32(emu.sym("_held_tank"), tank)
        emu.write32(emu.sym("_held_copy"), k)
        return emu.call(emu.sym("_drop_copy"), emu.scene, x, y)

    def saved(self, emu, tank: int) -> list[bytes]:
        """A tank's copies: what the next save writes to "Ornaments <slot>.dat" (on_save writes the
        counts and records whole, to_image, so a copy gone here is gone from the file)."""
        count = emu.read32(emu.sym("_copy_count") + 4 * tank)
        return [bytes(emu.uc.mem_read(emu.sym("_copies") + (tank * 10 + k) * ORN_STRIDE, ORN_STRIDE))
                for k in range(count)]

    def test_a_copy_in_the_trash_is_gone_from_the_tank_and_the_next_save(self) -> None:
        for logical in (0, 3, 4, 5):                                           # Tank 1, and Tanks 4-6
            for x, y in [(669, 570)] + maximized_trash_points()[:3]:
                with self.subTest(tank=logical, at=(x, y)):
                    emu = self.world(logical)
                    recs = self.copies(emu, logical, 3)
                    other = self.copies(emu, 1, 2)                             # Tank 2's copies stay
                    state = bytes(emu.uc.mem_read(emu.state, 0x1E510))
                    self.assertEqual(self.drop(emu, logical, 1, x, y), 1)
                    self.assertEqual(emu.calls[0], ("dialog", (0xAC,)))        # the game's question
                    self.assertIn(("sound", (4,)), emu.calls)
                    self.assertEqual(self.saved(emu, logical), [recs[0], recs[2]])
                    self.assertEqual(self.saved(emu, 1), other)
                    self.assertEqual(bytes(emu.uc.mem_read(emu.state, 0x1E510)), state)   # originals untouched
                    self.assertEqual(emu.read32(emu.sym("_held_tank"), signed=True), -1)

    def test_off_the_can_or_on_no_the_copy_is_kept(self) -> None:
        for logical in (0, 3, 5):
            for (x, y), yes in (((TRASH[0] - 1, 570), True), ((400, 300), True), ((669, 570), False)):
                emu = self.world(logical, answer_yes=yes)
                recs = self.copies(emu, logical, 2)
                self.drop(emu, logical, 0, x, y)
                self.assertEqual(self.saved(emu, logical), recs, (logical, x, y, yes))
                self.assertIn("settle", [c[0] for c in emu.calls])             # it falls or rests, as stock
                self.assertNotIn(("sound", (4,)), emu.calls)


# ================================================================== Plant Tycoon

PLANT_STATE = 0x64000
HELD, SELECTED = 0x56C, 0x63E58
CHEM_TRAY = 0x53F84                        # 4 bottles: present (byte), chemical id, doses; 0xC each
POT0, POT_SIZE = 0x2188, 0x5600
FORMULA, REVIVAL_ID, REVITA, BOMB, MUTA_FLOWER, MUTA_FOLIAGE = 36, 37, 38, 39, 48, 49
P_TRASH = (0xAE, 0x20D, 0xAE + 0x38, 0x20D + 0x4B)       # left, top, right, bottom (inclusive, 0x435FF0)
TRASH_BIN = 0x23                                          # close_trash_bin.ogg


@_needs(PLANT_EXE)
class PlantChemicalTrashTests(unittest.TestCase):
    """The greenhouse's mouse-up (0x425FB8 on, the DLL's call at 0x425FF2) and press (0x4272DC, the DLL's
    jump) with the stock trash (0x424680) and the stock put-back (0x4244C0)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", UPGRADES_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def greenhouse(self, answer_yes: bool = False):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        page_zero(emu)
        emu.uc.mem_write(0x425FF2, b"\xE8" + struct.pack("<i", emu.sym("_stub_trash_drop") - 0x425FF7))
        emu.uc.mem_write(0x4272DC, b"\xE9" + struct.pack("<i", emu.sym("_stub_trash_press") - 0x4272E1) + b"\x90" * 4)
        emu.hook(0x0044A580, emu.record("sound", args=1), 4)
        emu.hook(0x00421190, emu.record("fly back", args=8), 0x20)          # the put-back's animation
        emu.hook(0x0042F690, emu.record("pot emptied", args=1), 4)
        emu.hook(0x0042AB50, emu.record("question", args=5), 0x14)          # "Delete this plant?"
        emu.hook(0x00401C90, lambda e: 0, 8)
        emu.hook(0x0042AB10, lambda e: 0 if answer_yes else 1, 0)
        emu.hook(0x0042AAA0, lambda e: 0, 0)
        emu.hook(0x0041D420, emu.record("seed out of the tray", args=1), 4)
        emu.hook(0x0041ED70, emu.record("cash", args=1), 4)
        emu.hook(0x004033B0, lambda e: 0, 0)
        emu.hook(0x0041B190, emu.record("tip", args=2), 8)
        state, gh = emu.alloc(PLANT_STATE), emu.alloc(0x200)
        for at in range(0, PLANT_STATE, 4):
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        for k in range(4):                                                    # the chemical tray: empty
            emu.uc.mem_write(state + CHEM_TRAY + k * 0xC, bytes(0xC))
        emu.write32(state + SELECTED, 0x63)                                   # no plant selected
        emu.write32(gh + 0x68, state)
        for offset in (0x60, 0x6C, 0x70, 0x74, 0x80, 0x84, 0x8C):
            emu.write32(gh + offset, emu.alloc(0x40))
        emu.write8(gh + 0x105, 0)
        emu.write32(gh + 0x144, 0)
        emu.state, emu.gh = state, gh
        return emu

    def bottle(self, emu, k: int, chemical: int, doses: int) -> None:
        emu.uc.mem_write(emu.state + CHEM_TRAY + k * 0xC, struct.pack("<B3xii", 1, chemical, doses))

    def tray(self, emu) -> list[tuple[int, int, int]]:
        return [struct.unpack("<B3xii", emu.uc.mem_read(emu.state + CHEM_TRAY + k * 0xC, 0xC)) for k in range(4)]

    def release(self, emu, held: int, x: int, y: int) -> None:
        """The mouse-up off the pots (0x425FB8 to its end, 0x426019)."""
        emu.write32(emu.state + HELD, held)
        esp = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.mem_write(esp, bytes(0x100))
        emu.write32(esp + 0xAC, x)
        emu.write32(esp + 0xB0, y)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_EBP, emu.gh)
        emu.uc.emu_start(0x00425FB8, 0x00426019, count=200_000)

    def press(self, emu, held: int, x: int, y: int) -> None:
        """The press off the pots (0x4272DC to the press handler's return)."""
        emu.write32(emu.state + HELD, held)
        esp = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.mem_write(esp, bytes(0x40))
        emu.write32(esp + 0x1C, E.RETURN)                     # after edi, esi, ebp, ebx and 0xC of locals
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ESI, emu.gh)
        emu.uc.reg_write(X.UC_X86_REG_EBX, x)
        emu.uc.reg_write(X.UC_X86_REG_EBP, y)
        emu.uc.emu_start(0x004272DC, E.RETURN, count=200_000)

    def snapshot(self, emu) -> bytes:
        return bytes(emu.uc.mem_read(emu.state, PLANT_STATE))

    def select_plant(self, emu, k: int = 7) -> int:
        pot = emu.state + POT0 + k * POT_SIZE
        emu.write32(emu.state + SELECTED, k)
        emu.write32(pot + 0x1C, 1)                            # +0x21A4: planted
        emu.write32(pot + 0x24, 60)                           # +0x21AC: alive
        emu.write32(pot + 0x4C, 3)                            # +0x21D4
        return pot

    POINTS = ((P_TRASH[0], P_TRASH[1]), (P_TRASH[2], P_TRASH[3]), (0xC0, 0x230), (0xE0, 0x250))

    def test_a_new_chemical_let_go_on_the_trash_is_thrown_away(self) -> None:
        for chemical in (FORMULA, REVIVAL_ID, REVITA, BOMB, MUTA_FLOWER, MUTA_FOLIAGE):
            for slot in range(4):
                for x, y in self.POINTS:
                    with self.subTest(chemical=chemical, slot=slot, at=(x, y)):
                        emu = self.greenhouse()
                        self.bottle(emu, slot, chemical, 2)
                        self.bottle(emu, (slot + 1) % 4, chemical, 3)          # the same chemical in another slot stays
                        self.bottle(emu, (slot + 2) % 4, 30, 1)                # a stock one stays
                        before = bytearray(self.snapshot(emu))
                        self.release(emu, 5 + slot, x, y)
                        tray = self.tray(emu)
                        self.assertEqual(tray[slot][0], 0)                      # the bottle, every dose
                        self.assertEqual(tray[(slot + 1) % 4], (1, chemical, 3))
                        self.assertEqual(tray[(slot + 2) % 4], (1, 30, 1))
                        self.assertEqual(emu.read32(emu.state + HELD), 0)
                        self.assertIn(("sound", (TRASH_BIN,)), emu.calls)
                        self.assertNotIn("question", [c[0] for c in emu.calls])
                        before[CHEM_TRAY + slot * 0xC] = 0
                        struct.pack_into("<i", before, HELD, 0)
                        self.assertEqual(self.snapshot(emu), bytes(before))     # nothing else

    def test_a_new_chemical_pressed_on_the_trash_is_thrown_away_and_no_plant_is_touched(self) -> None:
        for selected in (False, True):
            for chemical in (FORMULA, REVIVAL_ID, REVITA, BOMB, MUTA_FLOWER, MUTA_FOLIAGE):
                for x, y in self.POINTS:
                    with self.subTest(selected=selected, chemical=chemical, at=(x, y)):
                        emu = self.greenhouse(answer_yes=True)
                        if selected:
                            self.select_plant(emu)
                        self.bottle(emu, 2, chemical, 3)
                        before = bytearray(self.snapshot(emu))
                        self.press(emu, 7, x, y)
                        self.assertEqual(self.tray(emu)[2][0], 0)
                        self.assertEqual(emu.read32(emu.state + HELD), 0)
                        self.assertIn(("sound", (TRASH_BIN,)), emu.calls)
                        for label in ("question", "pot emptied", "fly back"):
                            self.assertNotIn(label, [c[0] for c in emu.calls])
                        before[CHEM_TRAY + 2 * 0xC] = 0
                        struct.pack_into("<i", before, HELD, 0)
                        self.assertEqual(self.snapshot(emu), bytes(before))

    def test_off_the_trash_a_new_chemical_stays_held(self) -> None:
        for x, y in ((P_TRASH[0] - 1, 0x230), (P_TRASH[2] + 1, 0x230), (0xC0, P_TRASH[1] - 1), (400, 300)):
            emu = self.greenhouse()
            self.bottle(emu, 0, FORMULA, 3)
            emu.write32(emu.state + HELD, 5)
            before = self.snapshot(emu)
            self.release(emu, 5, x, y)
            self.assertEqual(self.snapshot(emu), before, (x, y))                 # still on the cursor, as stock
            self.assertNotIn(("sound", (TRASH_BIN,)), emu.calls)

    def test_the_stock_chemicals_are_never_thrown_away(self) -> None:
        for chemical in range(27, 36):
            emu = self.greenhouse()
            self.bottle(emu, 1, chemical, 2)
            emu.write32(emu.state + HELD, 6)
            before = self.snapshot(emu)
            self.release(emu, 6, 0xC0, 0x230)
            self.assertEqual(self.snapshot(emu), before, chemical)
            self.assertNotIn(("sound", (TRASH_BIN,)), emu.calls)
        # A press with a plant selected: the stock trash asks about that plant, as before.
        emu = self.greenhouse(answer_yes=False)
        self.select_plant(emu)
        self.bottle(emu, 1, 30, 2)
        self.press(emu, 6, 0xE0, 0x230)
        self.assertEqual([c[1][0] for c in emu.calls if c[0] == "question"], [0x10A])     # "Delete this plant?"
        self.assertEqual(self.tray(emu)[1], (1, 30, 2))

    def test_the_tools_are_never_thrown_away(self) -> None:
        # Held 1-4: the watering can, the bug spray, the clippers and the butterfly net.
        for tool in (1, 2, 3, 4):
            for selected in (False, True):
                emu = self.greenhouse(answer_yes=True)
                if selected:
                    self.select_plant(emu)
                self.bottle(emu, 0, FORMULA, 3)
                emu.write32(emu.state + HELD, tool)
                before = self.snapshot(emu)
                self.release(emu, tool, 0xE0, 0x230)
                self.assertEqual(self.snapshot(emu), before, (tool, selected))  # still held, nothing changed
                self.press(emu, tool, 0xE0, 0x230)
                for label in ("question", "pot emptied"):
                    self.assertNotIn(label, [c[0] for c in emu.calls], (tool, selected))
                self.assertNotIn(("sound", (TRASH_BIN,)), emu.calls)
                self.assertEqual(self.tray(emu)[0], (1, FORMULA, 3))
                after = bytearray(self.snapshot(emu))
                struct.pack_into("<i", after, HELD, tool)                         # only the hand may change
                self.assertEqual(bytes(after), before, (tool, selected))

    def test_legendary_and_new_flower_seeds_are_sold_by_the_stock_trash(self) -> None:
        # Seed-tray slot 0 (held 10): the stock seed trash takes the packet and pays its own value
        # (+0x20: Legendary Seeds 10, a new-flower seed its class's).
        for value in (10, 15):
            emu = self.greenhouse()
            record = emu.state + 0x52A20 + 10 * 36
            emu.write32(record + 0x20, value)
            self.release(emu, 10, 0xC0, 0x230)
            self.assertIn(("seed out of the tray", (record,)), emu.calls)
            self.assertIn(("cash", (value,)), emu.calls)
            self.assertIn(("sound", (TRASH_BIN,)), emu.calls)
            self.assertEqual(emu.read32(emu.state + HELD), 0)


if __name__ == "__main__":
    unittest.main()
