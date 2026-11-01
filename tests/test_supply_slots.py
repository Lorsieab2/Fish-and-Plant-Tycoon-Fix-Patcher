"""The "Extra supply slots" setting (Extra Supply Slots.dll), run in Unicorn against the vanilla
Fish Tycoon.exe and the Universal supply slots build (tests/store_emulator.py).

The DLL is rebuilt from its source (it must come out byte-for-byte the shipped DLL), mapped beside
the game, and its own hooks are called with the game's own code running underneath: the release of
a held supply 0x421B20 and every use behind it (0x420B70: medicines, chemicals, eggs, the starter
eggs; DS Store Items' Radioactive Growth Hormone, Revival Potion, ClonaFish and Exotic Fish Eggs
with that DLL mapped too), the stock store's Buy 0x428080 (and Universal supply slots' payload),
and DS Store Items' own purchases. Only the clocks, the dice, the dialogs and the drawing are Python.

* Buying: the Upgrades screen item, its price, Free upgrades, "You already own this!".
* Pages: the arrows by click and by carrying, the refusal before the purchase.
* Purchases fill page 2 and 3 slots: the first free slot, a stack first with Universal slots.
* Using every item type from an extra slot is the same as using it from its stock slot.
* The trash, dragging between slots and pages, stacking with Universal on and off.
* The sidecar round trip, a damaged file set aside, a new game emptied, the save stays stock.
* All-or-none install, chained with the other companions' sites; no site overlaps another DLL's
  or a Fix Patcher patch; the art clears the top bar's other things; the maximized window.
* The manifest: the setting, its files, the loader chain, and the stock game unchanged with it off.
"""

from __future__ import annotations

import json
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import store_emulator as E
    from unicorn import x86_const as X
    HAVE_UNICORN = True
except ImportError:                                    # pragma: no cover
    HAVE_UNICORN = False

import ds_fish_loader  # noqa: E402

EXE = (E.VANILLA if HAVE_UNICORN else Path(".")) / "Fish Tycoon" / "Fish Tycoon.exe"
DLL = ROOT / "assets" / "fish_tycoon_supply_slots" / "Extra Supply Slots.dll"
STORE_DLL = ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll"
MANIFEST = ROOT / "data" / "fish_manifest.json"
LINK = ("/BASE:0x13000000",)                          # scripts/build_ftfp_supply_slots.ps1

STATE_SIZE = 0x1E600
SLOT, REC = 0x2B8, 0x1C
FISH, TANK, FREC = 0x390, 0x51EC, 0x288
NOTHING = 0x63
BOXES = ((14, 9, 49, 48), (63, 9, 98, 48), (113, 9, 148, 48), (164, 9, 199, 48))
ARROW_X, ARROW_UP_Y, ARROW_DOWN_Y, ARROW_W, ARROW_H = 204, 8, 31, 18, 15
TRASH = (650, 541, 689, 600)
ISOLATION = (500, 489, 639, 600)
TANK_RECT = (2, 51, 798, 489)
IN_TANK = (400, 300)
# Stock items: (item, shelf picture, cursor) as the store's dispatcher 0x427F30 writes them.
STOCK_ITEMS = {0: (0xA7, 0xAD), 1: (0xA8, 0xAE), 2: (0xA9, 0xAF), 3: (0x7A, 0x7B), 4: (0xAA, 0xB0),
               5: (0x79, 0x79), 6: (0xAB, 0xAB), 7: (0xAC, 0xAC), 26: (0x79, 0x79)}
EXOTIC, RGH, REVIVAL, CLONA, MUTA_FIN, MUTA_BODY = 28, 29, 30, 31, 32, 33
DS_ITEMS = {EXOTIC: (224, 224), RGH: (236, 237), REVIVAL: (239, 240), CLONA: (242, 243), MUTA_FIN: (247, 248),
            MUTA_BODY: (250, 251)}
NATIVE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 3, 26: 3, EXOTIC: 3, RGH: 2, REVIVAL: 2, CLONA: 2,
          MUTA_FIN: 2, MUTA_BODY: 2}

_BUILT: dict = {}


def ready() -> bool:
    return HAVE_UNICORN and EXE.is_file() and DLL.is_file() and E.toolchain_ready()


def built():
    if "dll" not in _BUILT:
        out = Path(tempfile.mkdtemp(prefix="ftfp_slots_"))
        _BUILT["dll"], _BUILT["symbols"] = E.build_with_map("ftfp_supply_slots", DLL, out, LINK)
    return _BUILT["dll"], _BUILT["symbols"]


def store_built():
    if "store" not in _BUILT:
        out = Path(tempfile.mkdtemp(prefix="ftfp_slots_store_"))
        _BUILT["store"], _BUILT["store_symbols"] = E.build_with_map("ftfp_ds_store", STORE_DLL, out)
    return _BUILT["store"], _BUILT["store_symbols"]


def universal_exe() -> Path:
    if "universal" not in _BUILT:
        import test_fish_30 as F
        path = Path(tempfile.mkdtemp(prefix="ftfp_slots_exe_")) / "universal.exe"
        path.write_bytes(F.patched_exe({"universal_supply_slots"}))
        _BUILT["universal"] = path
    return _BUILT["universal"]


def record(it: int, count: int = 3, k: int = 0) -> bytes:
    icon, cursor = STOCK_ITEMS.get(it) or DS_ITEMS[it]
    return struct.pack("<7i", it, 1, count, icon, cursor, k * 0x30 + 0x1E if k else 0, 0)


EMPTY = bytes(REC)


def centre(p: int) -> tuple[int, int]:
    left, top, right, bottom = BOXES[p]
    return (left + right) // 2, (top + bottom) // 2


def fish_record(seed: int, health: int = 40, disease: int = 1, age: int = 25) -> bytes:
    r = bytearray((i * 13 + seed * 7 + 1) & 0x3F for i in range(FREC))
    struct.pack_into("<IIii", r, 0, 999_000, 0, age, age)
    struct.pack_into("<i", r, 0x10, 0)
    struct.pack_into("<iii", r, 0x3C, health, disease, 50)
    struct.pack_into("<ii", r, 0x4C, 3 + seed % 5, 4 + seed % 7)
    return bytes(r)


class Rig:
    """The game state, the tank screen and the DLL (with DS Store Items beside it when asked)."""

    def __init__(self, universal: bool = False, owned: bool = True, with_store: bool = False,
                 exe: Path | None = None) -> None:
        exe = exe or (universal_exe() if universal else EXE)
        if with_store:
            store, store_symbols = store_built()
            self.emu = emu = E.Emulator(exe, store, store_symbols)
            dll, symbols = built()
            self.slot_imports = emu._map(dll.read_bytes(), resolve=True)
        else:
            dll, symbols = built()
            self.emu = emu = E.Emulator(exe, dll, symbols)
            self.slot_imports = emu.imports
        self.sym = symbols
        emu.uc.mem_map(0, 0x1000)                          # fs:[0] for the DLLs' __try (fs base 0)
        self.state = state = emu.alloc(STATE_SIZE)
        self.impl = impl = emu.alloc(0x200)
        self.ms, self.seed = 5_000_000, 7
        emu.write32(impl + 0x34, state)
        emu.write32(impl + 0x1C, NOTHING)
        emu.write32(impl + 0x28, NOTHING)
        for offset in (0x3C, 0x38, 0x40, 0x44, 0x4C, 0x50, 0x54):
            emu.write32(impl + offset, emu.alloc(0x400))
        view = emu.alloc(0x8000)
        emu.write32(emu.read32(impl + 0x3C), view)        # the view (impl+0x3C holds it)
        emu.write32(view + 0x5DE4, state)                  # its state (0x4154F9)
        for base, rect in ((0x88, TRASH), (0x98, ISOLATION), (0xA8, TANK_RECT)):
            for i, value in enumerate(rect):
                emu.write32(impl + base + 4 * i, value)
        emu.write32(state + 0x1E4E8, 0xFFFFFFFF)          # no fish held
        emu.write32(state + 0x1E168, 10)                   # Normal speed
        emu.write32(state + 0x244, 1)                      # fish food research
        emu.write32(state + 0x258, 1)
        self.mouse_obj = emu.alloc(16)
        emu.write32(self.mouse_obj, emu.alloc(16))
        self.point = [0, 0]
        self.calls = emu.calls
        hook = emu.hook
        hook(0x004020D0, lambda e: self.ms // 1000, 0)
        hook(0x004032C0, lambda e: 1_000_000, 0)
        hook(0x00403240, self._random, 0)
        hook(0x004251A0, lambda e: self.calls.append(("sound", e.arg(0))) or 0, 4)
        hook(0x00425120, lambda e: 0, 0)
        hook(0x0040AE20, lambda e: 0, 4)                   # play (the stock code plays without asking)
        hook(0x00417FA0, lambda e: self.calls.append(("hint", e.arg(0))) or 0, 4)
        hook(0x004021E0, lambda e: self.mouse_obj, 0)
        hook(0x0041BDD0, lambda e: 0x5560, 0)
        hook(0x0041BE70, lambda e: 0x100000 + e.arg(0), 4)
        hook(0x00407B20, lambda e: self.calls.append(("cursor", e.arg(0))) or 0, 12)
        hook(0x00408A40, lambda e: self.calls.append(("draw", e.arg(0), e.arg(1), e.arg(2))) or 0, 12)
        hook(0x00408AA0, lambda e: self.calls.append(("cell", e.arg(0), e.arg(1), e.arg(2), e.arg(3))) or 0, 16)
        hook(0x00402060, self._mouse_pos, 0)
        hook(0x00408C30, lambda e: self.calls.append(("text", e.cstring(e.arg(0)).decode("latin-1"),
                                                      e.arg(1), e.arg(2), e.arg(3))) or 0, 24)
        hook(0x0042A793, lambda e: emu.alloc(max(16, e.arg(0))), 0)
        hook(0x00409540, lambda e: self.calls.append(("image", e.cstring(e.arg(0)).decode())) or
             e.uc.reg_read(X.UC_X86_REG_ECX), 4)
        hook(0x004096C0, lambda e: self.calls.append(("grid", e.cstring(e.arg(0)).decode(), e.arg(1))) or
             e.uc.reg_read(X.UC_X86_REG_ECX), 12)
        hook(0x004221A0, lambda e: self.calls.append(("dialog", e.arg(0))) or 0, 8)
        hook(0x00401D00, lambda e: self.answers.pop(0) if self.answers else 0, 8)
        hook(0x00422440, lambda e: 0, 0)
        self.answers: list[int] = []
        # the stock use's own effects, kept to what changes the state

        self.w(f"_owner", state)
        self.w("_owned", int(owned))
        self.w("_prev_mouse", self._thunk(lambda e: self.calls.append(("stock mouse", e.arg(0))) or 0, 12))
        self.w("_prev_release", 0x00421B20)
        self.w("_prev_store_buy", 0x00428080)
        self.w("_prev_tank_slots", self._thunk(self._stock_slots, 4))
        self.w("_prev_store_slots", self._thunk(self._stock_slots, 4))
        self.w("_prev_draw", self._thunk(lambda e: self.calls.append(("stock overlay",)) or 0, 0))
        self.saved: list[bytes] = []
        self.w("_prev_save", self._thunk(self._save, 4))
        self.w("_prev_save_quit", self._thunk(self._save, 4))
        self.w("_prev_load", self._thunk(lambda e: 1, 4))
        self.w("_prev_new_game", self._thunk(lambda e: self.calls.append(("stock new game",)) or 0, 0))
        for k, it in ((0, None), (1, 0), (2, 3), (3, 26)):
            self.put_stock(k, record(it, 1 if it == 26 else 3, k) if it is not None else
                           struct.pack("<7i", 0x17, 1, 0, 0x78, 0x6E, 0x19, 0xF))

    # ------------------------------------------------------------ helpers
    def w(self, name: str, value: int) -> None:
        self.emu.write32(self.sym[name], value & 0xFFFFFFFF)

    def r(self, name: str) -> int:
        return self.emu.read32(self.sym[name], signed=True)

    def _thunk(self, handler, pop: int) -> int:
        address = self.emu.thunk()
        self.emu.hook(address, handler, pop)
        return address

    def _random(self, emu) -> int:
        n = emu.arg(0)
        self.seed = (self.seed * 214013 + 2531011) & 0xFFFFFFFF
        return ((self.seed >> 16) & 0x7FFF) % n if 0 < n <= 0x7FFF else 0

    def _mouse_pos(self, emu) -> int:
        emu.write32(emu.arg(0), self.point[0])
        emu.write32(emu.arg(0) + 4, self.point[1])
        return 0

    def _stock_slots(self, emu) -> int:
        self.calls.append(("stock slots", tuple(self.stock(k) for k in range(4))))
        return 0

    def _save(self, emu) -> int:
        self.saved.append(bytes(emu.uc.mem_read(self.state + SLOT, 4 * REC)))
        return 1

    def stock(self, k: int) -> bytes:
        return bytes(self.emu.uc.mem_read(self.state + SLOT + k * REC, REC))

    def put_stock(self, k: int, data: bytes) -> None:
        self.emu.uc.mem_write(self.state + SLOT + k * REC, data)

    def extra(self, e: int) -> bytes:
        return bytes(self.emu.uc.mem_read(self.sym["_extra"] + e * REC, REC))

    def put_extra(self, e: int, data: bytes) -> None:
        self.emu.uc.mem_write(self.sym["_extra"] + e * REC, data)

    def held(self) -> int:
        return self.emu.read32(self.impl + 0x1C)

    def mouse(self, kind: int, x: int, y: int) -> int:
        return self.emu.call(self.sym["@mouse_hook@20"], kind, x, y, ecx=self.impl) & 0xFF

    def press(self, x: int, y: int) -> None:
        self.mouse(2, x, y)

    def click(self, x: int, y: int) -> None:
        self.mouse(2, x, y)
        self.mouse(3, x, y)

    def page(self) -> int:
        return self.r("_page")

    def to_page(self, n: int) -> None:
        """Click the lower arrow until page n shows; while something is held, carry it over the arrow."""
        for _ in range(4):
            if self.page() == n:
                return
            if self.emu.uc.mem_read(self.impl, 1)[0]:
                self.mouse(1, 300, 300)
                self.mouse(1, ARROW_X + 5, ARROW_DOWN_Y + 5)
                self.mouse(1, 300, 300)
            else:
                self.click(ARROW_X + 5, ARROW_DOWN_Y + 5)
        raise AssertionError(f"page {n} never showed (page {self.page()})")

    def pick_extra(self, e: int) -> None:
        """Press on extra slot e: its page, then its place."""
        self.to_page(1 + e // 4)
        self.press(*centre(e % 4))

    def pick_stock(self, k: int) -> None:
        """The stock pick of slot k (0x41E545): what the game sets when a stock slot is pressed."""
        self.to_page(0)
        x, y = centre(k)
        self.emu.write32(self.impl + 0x1C, k)
        self.emu.write32(self.impl + 0x20, x + 10)
        self.emu.write32(self.impl + 0x24, y + 10)
        self.emu.write8(self.impl, 1)

    def let_go(self, x: int, y: int) -> int:
        """The stock let-go (0x421D05): the drag flag off, then the release, through this DLL's hook."""
        self.emu.write8(self.impl, 0)
        return self.emu.call(self.sym["@release_hook@16"], x, y, ecx=self.impl) & 0xFF

    def everything(self) -> bytes:
        return bytes(self.emu.uc.mem_read(self.state, STATE_SIZE))


def slots_view(rig: Rig) -> list[bytes]:
    """All eleven: the stock four, then the seven extra, as they really are."""
    return [rig.stock(k) for k in range(4)] + [rig.extra(e) for e in range(7)]


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class Pages(unittest.TestCase):
    def test_either_arrow_turns_the_page_and_wraps(self) -> None:
        rig = Rig()
        self.assertEqual(rig.page(), 0)
        for want in (1, 2, 0):
            rig.click(ARROW_X + 2, ARROW_DOWN_Y + 2)
            self.assertEqual(rig.page(), want)
        for want in (2, 1, 0):
            rig.click(ARROW_X + ARROW_W - 1, ARROW_UP_Y + ARROW_H - 1)
            self.assertEqual(rig.page(), want)
        self.assertIn(("sound", 1), rig.calls, "the stock button sound")

    def test_a_press_off_the_arrow_turns_nothing(self) -> None:
        rig = Rig()
        rig.mouse(2, ARROW_X + 2, ARROW_DOWN_Y + 2)
        rig.mouse(3, ARROW_X + 40, ARROW_DOWN_Y + 2)
        self.assertEqual(rig.page(), 0)
        for x, y in ((ARROW_X - 1, ARROW_UP_Y), (ARROW_X + ARROW_W, ARROW_UP_Y), (ARROW_X, ARROW_UP_Y + ARROW_H),
                     (ARROW_X, ARROW_DOWN_Y - 1)):
            rig.click(x, y)
        self.assertEqual(rig.page(), 0)

    def test_carrying_over_an_arrow_turns_the_page_once_per_visit(self) -> None:
        rig = Rig()
        rig.pick_stock(2)
        rig.mouse(1, ARROW_X + 3, ARROW_DOWN_Y + 3)
        rig.mouse(1, ARROW_X + 4, ARROW_DOWN_Y + 4)               # still over it: no second turn
        self.assertEqual(rig.page(), 1)
        rig.mouse(1, 300, 300)
        rig.mouse(1, ARROW_X + 3, ARROW_DOWN_Y + 3)
        self.assertEqual(rig.page(), 2)
        rig.mouse(1, 300, 300)
        rig.mouse(1, ARROW_X + 3, ARROW_UP_Y + 3)
        self.assertEqual(rig.page(), 1)

    def test_hovering_with_nothing_held_turns_nothing(self) -> None:
        rig = Rig()
        rig.mouse(1, ARROW_X + 3, ARROW_DOWN_Y + 3)
        self.assertEqual(rig.page(), 0)

    def test_before_the_purchase_the_arrows_refuse(self) -> None:
        rig = Rig(owned=False)
        rig.click(ARROW_X + 3, ARROW_DOWN_Y + 3)
        self.assertEqual(rig.page(), 0)
        rig.pick_stock(1)
        rig.mouse(1, ARROW_X + 3, ARROW_DOWN_Y + 3)
        self.assertEqual(rig.page(), 0, "carrying over a grey arrow turns nothing")
        rig.emu.call(rig.sym["@draw_hook@8"], ecx=rig.impl)
        texts = [c for c in rig.calls if c[0] == "text"]
        self.assertEqual(texts[-1][1:], ("You don't own the extra supply slots yet!", 0, 800, 70),
                         "Extra Tanks' refusal place: across the screen, just under the top bar")
        cells = [c for c in rig.calls if c[0] == "cell"]
        self.assertEqual([c[4] for c in cells], [2, 2], "both arrows grey")
        rig.ms += 3000
        rig.calls.clear()
        rig.emu.call(rig.sym["@draw_hook@8"], ecx=rig.impl)
        self.assertFalse([c for c in rig.calls if c[0] == "text"], "gone after 2 seconds")

    def test_the_arrows_draw_normal_and_hovered(self) -> None:
        rig = Rig()
        rig.point = [ARROW_X + 4, ARROW_DOWN_Y + 4]
        rig.emu.call(rig.sym["@draw_hook@8"], ecx=rig.impl)
        cells = [c for c in rig.calls if c[0] == "cell"]
        self.assertEqual([(c[2], c[3], c[4]) for c in cells], [(ARROW_X, ARROW_UP_Y, 0), (ARROW_X, ARROW_DOWN_Y, 1)])
        self.assertIn(("grid", "SupplyArrowLeft.png", 3), rig.calls)
        self.assertIn(("grid", "SupplyArrowRight.png", 3), rig.calls)

    def test_extra_pages_draw_their_slots_and_page_one_is_stock(self) -> None:
        rig = Rig()
        for e in range(7):
            rig.put_extra(e, record([0, 2, 5, 3, 1, 6, 4][e], 3))
        sprites = rig.emu.read32(rig.impl + 0x38)
        rig.w("_drawing_impl", rig.impl)
        for page in (0, 1, 2):
            rig.to_page(page)
            rig.calls.clear()
            rig.emu.call(rig.sym["@tank_slots_hook@12"], 0, ecx=sprites)
            draws = [c[1:] for c in rig.calls if c[0] == "draw"]
            if page == 0:
                self.assertEqual(draws, [])
                self.assertTrue([c for c in rig.calls if c[0] == "stock slots"])
                continue
            self.assertFalse([c for c in rig.calls if c[0] == "stock slots"], "no stock slot shows on pages 2-3")
            if page == 1:
                want = [(0x100000 + STOCK_ITEMS[it][0], x, 15) for it, x in zip((0, 2, 5, 3), (0x19, 78, 126, 174))]
            else:
                want = [(0x100000 + STOCK_ITEMS[it][0], x, 15) for it, x in zip((1, 6, 4), (0x19, 78, 126))]
            self.assertEqual([d for d in draws if 0x100000 <= d[0] < 0x200000], want)
            if page == 2:
                self.assertIn(("image", "SupplySlotUnused.png"), rig.calls)
                self.assertTrue([d for d in draws if d[1:] == (164, 9)], "the fourth frame greyed")
        rig.w("_drawing_impl", 0)

    def test_page_two_and_three_never_pick_a_stock_slot(self) -> None:
        rig = Rig()
        rig.to_page(1)
        for p in range(4):
            rig.press(*centre(p))                                   # all four extra slots empty
            self.assertEqual(rig.held(), NOTHING)
            self.assertEqual(rig.emu.uc.mem_read(rig.impl, 1)[0], 0)


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class PickingUp(unittest.TestCase):
    def test_an_extra_slot_is_held_as_the_game_holds_a_supply(self) -> None:
        for universal in (False, True):
            for it in (0, 3, 6, 26):
                with self.subTest(universal=universal, item=it):
                    rig = Rig(universal)
                    rig.put_extra(5, record(it, 2))
                    before = slots_view(rig)
                    rig.pick_extra(5)
                    k = NATIVE[it]
                    self.assertEqual(rig.held(), k)
                    self.assertEqual(rig.stock(k)[:0x14], record(it, 2)[:0x14], "its record is the one the use reads")
                    self.assertEqual(rig.emu.read32(rig.impl + 0x20), centre(1)[0] + 10)
                    self.assertEqual(rig.emu.read32(rig.impl + 0x24), centre(1)[1] + 10)
                    self.assertEqual(rig.emu.uc.mem_read(rig.impl, 1)[0], 1, "the drag flag")
                    self.assertEqual(rig.emu.read32(rig.emu.read32(rig.mouse_obj) + 4),
                                     rig.emu.read32(rig.impl + 0x50), "the mouse captured")
                    self.assertIn(("cursor", 0x100000 + 0xC3), rig.calls, "the closed hand")
                    rig.to_page(0)                                       # page 1 shows the stock slot's own
                    rig.w("_drawing_impl", rig.impl)
                    rig.emu.call(rig.sym["@tank_slots_hook@12"], 0, ecx=rig.emu.read32(rig.impl + 0x38))
                    shown = [c[1] for c in rig.calls if c[0] == "stock slots"][-1]
                    self.assertEqual(list(shown), before[:4])
                    self.assertEqual(slots_view(rig)[:4], [before[0]] + [rig.stock(i) for i in (1, 2, 3)])
                    rig.let_go(300, 30)                                  # in the top bar: the stock hint
                    self.assertEqual(slots_view(rig), before, "back where it was, everything else as it was")
                    self.assertIn(("hint", 0xD), rig.calls)
                    self.assertEqual(rig.held(), NOTHING)

    def test_a_held_fish_blocks_a_pick(self) -> None:
        rig = Rig()
        rig.put_extra(0, record(2))
        rig.emu.write32(rig.state + 0x1E4E8, 4)
        rig.pick_extra(0)
        self.assertEqual(rig.held(), NOTHING)

    def test_a_stale_pick_is_put_back(self) -> None:
        """The screen reset its held supply (0x421A52: a tank switch): the next draw puts it back."""
        rig = Rig()
        rig.put_extra(2, record(5, 3))
        before = slots_view(rig)
        rig.pick_extra(2)
        rig.emu.write32(rig.impl + 0x1C, NOTHING)
        rig.emu.write8(rig.impl, 0)
        rig.emu.call(rig.sym["@draw_hook@8"], ecx=rig.impl)
        self.assertEqual(slots_view(rig), before)
        self.assertEqual(rig.r("_lift_e"), -1)


class UseRig:
    """One use of an item on the tank, from its stock slot or from an extra slot."""

    @staticmethod
    def prepare(rig: Rig) -> None:
        for s in range(6):
            rig.emu.uc.mem_write(rig.state + FISH + s * FREC, fish_record(s))


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class UsingFromAnExtraSlot(unittest.TestCase):
    """Every item used from an extra slot does to the tank exactly what it does from its own slot,
    the extra slot ends as the stock slot would (a dose less, a hatch less, or empty), and the stock
    slot under it keeps its own item."""

    def compare(self, it: int, count: int, universal: bool, with_store: bool, where=IN_TANK) -> None:
        k = NATIVE[it]
        stock = Rig(universal, with_store=with_store)
        UseRig.prepare(stock)
        stock.put_stock(k, record(it, count, k))
        stock.pick_stock(k)
        stock.let_go(*where)
        extra = Rig(universal, with_store=with_store)
        UseRig.prepare(extra)
        other = record(4 if k != 2 else 1, 2, k)                   # the stock slot's own, kept
        extra.put_stock(k, other)
        extra.put_extra(6, record(it, count, k))
        before_extra = extra.everything()
        extra.pick_extra(6)
        extra.let_go(*where)
        a, b = stock.everything(), extra.everything()
        lo, hi = SLOT + k * REC, SLOT + (k + 1) * REC
        self.assertEqual(b[lo:hi], other, "the stock slot keeps its own item")
        self.assertEqual(extra.extra(6)[:0x14], stock.stock(k)[:0x14] if stock.stock(k)[0xC:0x10] != bytes(4)
                         else bytes(0x14), "the extra slot ends as the stock slot did")
        self.assertEqual(a[:lo] + a[hi:], b[:lo] + b[hi:], "the tank and the game change exactly alike")
        self.assertTrue(before_extra != b or extra.extra(6) != record(it, count, k), "the use did something")
        self.assertEqual(extra.held(), NOTHING)
        self.assertEqual(extra.r("_lift_e"), -1)

    def test_every_stock_item(self) -> None:
        for universal in (False, True):
            for it in (0, 1, 2, 3, 4, 5, 6, 7, 26):
                for count in (3, 1):
                    with self.subTest(universal=universal, item=it, count=count):
                        self.compare(it, count, universal, with_store=False)

    def test_every_patcher_item(self) -> None:
        """DS Store Items mapped beside it: its chemical switch (0x420E6F) and egg switch (0x421356)
        stubs installed as its install writes them, and its trash (0x421B52)."""
        for universal in (False, True):
            for it in (RGH, REVIVAL, CLONA, MUTA_FIN, MUTA_BODY, EXOTIC):
                for count in (3, 1):
                    with self.subTest(universal=universal, item=it, count=count):
                        self.compare_store(it, count, universal, IN_TANK)

    def test_the_trash_takes_patcher_items_and_never_stock_ones(self) -> None:
        trash = ((TRASH[0] + TRASH[2]) // 2, (TRASH[1] + TRASH[3]) // 2)
        for universal in (False, True):
            for it in (RGH, REVIVAL, CLONA, MUTA_FIN, MUTA_BODY, EXOTIC):
                with self.subTest(universal=universal, item=it):
                    rig = self.store_rig(universal)
                    rig.put_extra(4, record(it, 3))
                    rig.pick_extra(4)
                    rig.let_go(*trash)
                    self.assertEqual(rig.extra(4), EMPTY, "thrown away whole")
                    self.assertEqual(rig.stock(NATIVE[it]), record(0 if NATIVE[it] == 1 else 3 if NATIVE[it] == 2
                                                                   else 26, 1 if NATIVE[it] == 3 else 3, NATIVE[it]))
                    self.assertIn(("sound", 4), rig.calls, "the fish trash's sound")
            for it in (0, 3, 7):
                with self.subTest(universal=universal, stock_item=it):
                    rig = self.store_rig(universal)
                    rig.put_extra(4, record(it, 3))
                    before = slots_view(rig)
                    rig.pick_extra(4)
                    rig.let_go(*trash)
                    self.assertEqual(slots_view(rig), before, "stock items go back, as stock")
                    self.assertIn(("hint", 0xD), rig.calls)

    # -- DS Store Items beside it
    def store_rig(self, universal: bool) -> Rig:
        rig = Rig(universal, with_store=True)
        emu = rig.emu
        ss = emu.symbols
        for site, name in ((0x420E6F, "_stub_chem_use"), (0x421356, "_stub_egg_use")):
            emu.uc.mem_write(site, b"\xE9" + struct.pack("<i", ss[name] - (site + 5)))
        emu.uc.mem_write(0x421B52, b"\xE8" + struct.pack("<i", ss["_stub_supply_drop"] - (0x421B52 + 5)))
        if universal:                                    # its use gate, as install_use_gate writes it
            emu.uc.mem_write(0x43F593, b"\xE9" + struct.pack("<i", ss["_stub_use_gate"] - (0x43F593 + 5)))
            emu.write32(ss["_exotic_any_slot"], 1)
        emu.write32(ss["_installed"], 1)
        for name in ("GetModuleHandleW", "GetProcAddress"):
            emu.hook_import(name, lambda e: 0, 4 if name == "GetModuleHandleW" else 8)

        return rig

    def compare_store(self, it: int, count: int, universal: bool, where) -> None:
        k = NATIVE[it]
        stock = self.store_rig(universal)
        UseRig.prepare(stock)
        stock.put_stock(k, record(it, count, k))
        stock.pick_stock(k)
        stock.let_go(*where)
        extra = self.store_rig(universal)
        UseRig.prepare(extra)
        other = record(4 if k == 2 else 1 if k == 1 else 6, 2, k)
        extra.put_stock(k, other)
        extra.put_extra(1, record(it, count))
        before = extra.everything()
        extra.pick_extra(1)
        extra.let_go(*where)
        a, b = stock.everything(), extra.everything()
        if it in (RGH, CLONA):                       # every fish healed / cloned: the dose reached the tank
            self.assertNotEqual(before[FISH:FISH + TANK], b[FISH:FISH + TANK])
        lo, hi = SLOT + k * REC, SLOT + (k + 1) * REC
        self.assertEqual(b[lo:hi], other)
        want = stock.stock(k)
        self.assertEqual(extra.extra(1)[:0x14], want[:0x14] if want[0xC:0x10] != bytes(4) else bytes(0x14))
        self.assertEqual(a[:lo] + a[hi:], b[:lo] + b[hi:])


def no_x(r: bytes) -> bytes:
    """A record without its x (+0x14): only a stock slot's x is ever drawn."""
    return r[:0x14] + r[0x18:]


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class Dragging(unittest.TestCase):
    """A held supply let go on a supply slot of the page shown: moved, stacked or swapped."""

    def test_an_extra_slot_to_an_empty_slot_on_another_page(self) -> None:
        for universal in (False, True):
            rig = Rig(universal)
            rig.put_extra(1, record(6, 3))
            rig.pick_extra(1)
            rig.to_page(2)                                               # carried over the arrow
            self.assertEqual(rig.let_go(*centre(2)), 1)
            self.assertEqual(rig.extra(1), EMPTY)
            self.assertEqual(no_x(rig.extra(6)), no_x(record(6, 3)))
            self.assertEqual(rig.held(), NOTHING)
            self.assertIn(("sound", 2), rig.calls)

    def test_a_stock_slot_to_an_extra_slot_and_back(self) -> None:
        for universal in (False, True):
            rig = Rig(universal)
            chem = rig.stock(2)
            rig.pick_stock(2)
            rig.to_page(1)
            rig.let_go(*centre(0))                                       # page 2's first slot
            self.assertEqual(rig.stock(2), EMPTY)
            self.assertEqual(no_x(rig.extra(0)), no_x(chem))
            rig.pick_extra(0)
            rig.to_page(0)
            rig.let_go(*centre(2))
            self.assertEqual(rig.stock(2), chem, "back in slot #3 with slot #3's x")
            self.assertEqual(rig.extra(0), EMPTY)

    def test_the_same_item_stacks_with_universal_slots(self) -> None:
        rig = Rig(True)
        rig.put_extra(0, record(5, 2))
        rig.put_extra(3, record(5, 1))
        rig.pick_extra(3)
        rig.let_go(*centre(0))
        self.assertEqual(struct.unpack_from("<3i", rig.extra(0)), (5, 1, 3), "the counts add")
        self.assertEqual(rig.extra(3), EMPTY)

    def test_without_universal_slots_the_same_item_changes_places(self) -> None:
        rig = Rig(False)
        rig.put_extra(0, record(5, 2))
        rig.put_extra(3, record(5, 1))
        rig.pick_extra(3)
        rig.let_go(*centre(0))
        self.assertEqual(struct.unpack_from("<3i", rig.extra(0)), (5, 1, 1))
        self.assertEqual(struct.unpack_from("<3i", rig.extra(3)), (5, 1, 2), "no stacking, as stock")

    def test_another_item_changes_places(self) -> None:
        for universal in (False, True):
            rig = Rig(universal)
            rig.put_extra(4, record(2, 3))
            rig.put_extra(6, record(7, 1))
            rig.pick_extra(6)
            rig.to_page(2)
            rig.let_go(*centre(0))
            self.assertEqual(struct.unpack_from("<3i", rig.extra(4)), (7, 1, 1))
            self.assertEqual(struct.unpack_from("<3i", rig.extra(6)), (2, 1, 3))

    def test_stock_slots_keep_their_kind_without_universal_slots(self) -> None:
        rig = Rig(False)
        rig.put_extra(0, record(6, 1))                                   # eggs
        before = slots_view(rig)
        rig.pick_extra(0)
        rig.to_page(0)
        rig.let_go(*centre(1))                                           # slot #2: medicine only
        self.assertEqual(slots_view(rig), before, "refused: everything where it was")
        self.assertIn(("hint", 0xD), rig.calls)
        rig.pick_extra(0)
        rig.to_page(0)
        rig.let_go(*centre(3))                                           # slot #4: the eggs' own
        self.assertEqual(struct.unpack_from("<3i", rig.stock(3)), (6, 1, 1))
        self.assertEqual(struct.unpack_from("<3i", rig.extra(0)), (26, 1, 1), "the starter eggs changed places")
        # The medicine in slot #2 may not go to slot #3, nor a chemical come back into slot #2.
        before = slots_view(rig)
        rig.pick_stock(1)
        rig.let_go(*centre(2))
        self.assertEqual(slots_view(rig), before)

    def test_with_universal_slots_any_stock_slot_takes_anything(self) -> None:
        rig = Rig(True)
        rig.put_extra(0, record(6, 1))
        rig.pick_extra(0)
        rig.to_page(0)
        rig.let_go(*centre(1))
        self.assertEqual(struct.unpack_from("<3i", rig.stock(1)), (6, 1, 1))
        self.assertEqual(struct.unpack_from("<3i", rig.extra(0)), (0, 1, 3), "the medicine went to the extra slot")
        self.assertEqual(struct.unpack_from("<i", rig.stock(1), 0x14)[0], 78, "slot #2's x")

    def test_the_fish_food_and_the_unused_place_are_no_target(self) -> None:
        rig = Rig(True)
        rig.put_extra(4, record(3, 2))
        before = slots_view(rig)
        rig.pick_extra(4)
        rig.to_page(2)
        rig.let_go(*centre(3))                                           # page 3 has no fourth slot
        self.assertEqual(slots_view(rig), before)
        rig.pick_extra(4)
        rig.to_page(0)
        rig.let_go(*centre(0))                                           # the food: the stock answer
        self.assertEqual(slots_view(rig), before)
        self.assertIn(("hint", 0xD), rig.calls)

    def test_back_on_its_own_slot_changes_nothing(self) -> None:
        rig = Rig()
        rig.put_extra(2, record(1, 3))
        before = slots_view(rig)
        rig.pick_extra(2)
        rig.let_go(*centre(2))
        self.assertEqual(slots_view(rig), before)
        self.assertEqual(rig.held(), NOTHING)

    def test_the_fish_food_held_is_left_to_the_stock_code(self) -> None:
        rig = Rig()
        rig.pick_stock(0)
        rig.to_page(1)
        released = rig.emu.thunk()
        rig.emu.hook(released, lambda e: rig.calls.append(("stock release",)) or 0, 8)
        rig.w("_prev_release", released)
        rig.let_go(*centre(1))
        self.assertIn(("stock release",), rig.calls)


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class BuyingSupplies(unittest.TestCase):
    """The stock store's Buy (0x428080), and Universal supply slots' payload behind it."""

    def store(self, rig: Rig, money: int = 50_000) -> int:
        emu = rig.emu
        store = emu.alloc(0x40)
        emu.write32(store + 0x10, rig.state)
        emu.write32(store + 0x0C, emu.alloc(0x40))
        emu.write32(store + 0x20, emu.alloc(0x40))
        emu.write32(rig.state + 0x38C, money)
        rig.emu.write8(rig.state + 0x1E50C, 1)                          # past the store's tutorial
        for it in range(8):
            emu.write32(rig.state + it * 20 + 0x74, 100 + it)            # the prices
        return store

    def buy(self, rig: Rig, store: int, it: int, *answers: int) -> None:
        rig.answers = list(answers)
        rig.emu.call(rig.sym["@store_buy_hook@12"], it, ecx=store)
        self.assertEqual(rig.r("_lend_e"), -1, "every lent slot is back")

    def full(self, rig: Rig) -> None:
        rig.put_stock(1, record(1, 3, 1))
        rig.put_stock(2, record(4, 3, 2))
        rig.put_stock(3, record(7, 3, 3))

    def test_without_universal_slots_a_full_own_slot_fills_the_first_free_extra(self) -> None:
        rig = Rig(False)
        store = self.store(rig)
        self.full(rig)
        stock = [rig.stock(k) for k in range(4)]
        for e in range(7):
            self.buy(rig, store, (0, 3, 5, 2, 6, 1, 4)[e], 0)
            self.assertEqual(struct.unpack_from("<3i", rig.extra(e)), ((0, 3, 5, 2, 6, 1, 4)[e], 1, 3), e)
        self.assertEqual([rig.stock(k) for k in range(4)], stock, "the stock slots are untouched")
        self.assertEqual(rig.emu.read32(rig.state + 0x38C), 50_000 - sum(100 + i for i in (0, 3, 5, 2, 6, 1, 4)))
        self.assertTrue(all(c == ("dialog", 0xEC) for c in rig.calls if c[0] == "dialog"), "Buy this item?")
        # Every slot full: the stock question for slot #3 and the stock purchase over it.
        rig.calls.clear()
        self.buy(rig, store, 3, 0)
        self.assertIn(("dialog", 0xEE), rig.calls)
        self.assertEqual(struct.unpack_from("<3i", rig.stock(2)), (3, 1, 3))

    def test_without_universal_slots_a_free_own_slot_is_used_first(self) -> None:
        rig = Rig(False)
        store = self.store(rig)
        rig.put_stock(1, EMPTY)
        self.buy(rig, store, 1, 0)
        self.assertEqual(struct.unpack_from("<3i", rig.stock(1)), (1, 1, 3))
        self.assertEqual([rig.extra(e) for e in range(7)], [EMPTY] * 7)

    def test_no_leaves_everything(self) -> None:
        for universal in (False, True):
            rig = Rig(universal)
            store = self.store(rig)
            self.full(rig)
            before = slots_view(rig)
            self.buy(rig, store, 5, 1, 1, 1, 1)
            self.assertEqual(slots_view(rig), before)
            self.assertEqual(rig.emu.read32(rig.state + 0x38C), 50_000)

    def test_with_universal_slots_a_stack_anywhere_comes_first(self) -> None:
        rig = Rig(True)
        store = self.store(rig)
        self.full(rig)
        rig.put_extra(5, record(6, 1))
        self.buy(rig, store, 6, 0)
        self.assertEqual(struct.unpack_from("<3i", rig.extra(5)), (6, 1, 2), "one more hatch on the stack")
        rig.put_extra(2, record(2, 2))
        self.buy(rig, store, 2, 0)
        self.assertEqual(struct.unpack_from("<3i", rig.extra(2)), (2, 1, 5), "three more doses")

    def test_with_universal_slots_the_stock_stack_wins(self) -> None:
        rig = Rig(True)
        store = self.store(rig)
        self.full(rig)
        rig.put_extra(0, record(4, 1))
        self.buy(rig, store, 4, 0)
        self.assertEqual(struct.unpack_from("<3i", rig.stock(2)), (4, 1, 4), "Unknown Chemical: one use more")
        self.assertEqual(struct.unpack_from("<3i", rig.extra(0)), (4, 1, 1))

    def test_with_universal_slots_a_free_stock_slot_then_the_first_free_extra(self) -> None:
        rig = Rig(True)
        store = self.store(rig)
        self.full(rig)
        rig.put_stock(3, EMPTY)
        self.buy(rig, store, 0, 0)
        self.assertEqual(struct.unpack_from("<3i", rig.stock(3)), (0, 1, 3))
        for e in range(4):
            rig.put_extra(e, record(1, 3))
        self.buy(rig, store, 5, 0)
        self.assertEqual(struct.unpack_from("<3i", rig.extra(4)), (5, 1, 1), "page 3's first slot")
        self.assertEqual(struct.unpack_from("<3i", rig.stock(1)), (1, 1, 3), "the slot it was lent to is as it was")

    def test_before_the_purchase_only_the_stock_slots(self) -> None:
        rig = Rig(False, owned=False)
        store = self.store(rig)
        self.full(rig)
        self.buy(rig, store, 0, 0)
        self.assertIn(("dialog", 0xEF), rig.calls, "Replace medication in slot #2?")
        self.assertEqual([rig.extra(e) for e in range(7)], [EMPTY] * 7)

    def test_other_store_items_are_never_lent(self) -> None:
        rig = Rig(True)
        store = self.store(rig)
        self.full(rig)
        prev = rig.emu.thunk()
        seen = []
        rig.emu.hook(prev, lambda e: seen.append(slots_view(rig)) or 0, 4)
        rig.w("_prev_store_buy", prev)
        before = slots_view(rig)
        for it in (8, 11, 25):
            rig.emu.call(rig.sym["@store_buy_hook@12"], it, ecx=store)
        self.assertEqual(seen, [before] * 3)


@unittest.skipUnless(ready() and STORE_DLL.is_file(), "needs Unicorn, MSVC, the vanilla exe and both DLLs")
class DsStorePurchases(unittest.TestCase):
    """DS Store Items' own supplies (its buy_universal, buy_chemical and Exotic Fish Eggs) ask this
    DLL to lend the extra slot their purchase goes to, through its exports."""

    def rig(self, universal: bool, money: int = 100_000) -> Rig:
        rig = Rig(universal, with_store=True)
        emu = rig.emu
        ss = emu.symbols
        base = 0x13000000
        emu.write32(ss["_installed"], 1)
        emu.write32(ss["_exotic_any_slot"], int(universal))
        rig.w("_installed", 1)
        emu.write32(0x0045ABDC, rig.state)                               # the game's state pointer
        exports = {name: rig.sym[f"_{name}@{n}"] for name, n in (("FtfpSupplySlotsLend", 4),
                                                                   ("FtfpSupplySlotsReturn", 0),
                                                                   ("FtfpSupplySlotsOwned", 0))}
        emu.hook_import("GetModuleHandleW", lambda e: base if e.wstring(e.arg(0)) == "Extra Supply Slots.dll" else 0, 4)
        emu.hook_import("GetProcAddress", lambda e: exports.get(e.cstring(e.arg(1)).decode(), 0), 8)
        self.impl = emu.alloc(0x40)
        emu.write32(self.impl + 0x10, rig.state)
        emu.write32(self.impl + 0x20, emu.alloc(0x40))
        emu.write32(self.impl + 0x0C, emu.alloc(0x40))
        emu.write32(rig.state + 0x38C, money)
        return rig

    def test_chemicals_fill_extra_slots(self) -> None:
        for universal in (False, True):
            with self.subTest(universal=universal):
                rig = self.rig(universal)
                rig.put_stock(1, record(1, 3, 1))
                rig.put_stock(2, record(4, 3, 2))
                rig.put_stock(3, record(7, 3, 3))
                rig.answers = [0]
                rig.emu.call(rig.emu.symbols["_buy_chemical"], self.impl, rig.state, 500, RGH, *DS_ITEMS[RGH])
                self.assertEqual(struct.unpack_from("<5i", rig.extra(0)), (RGH, 1, 3, *DS_ITEMS[RGH]))
                self.assertEqual(struct.unpack_from("<3i", rig.stock(2)), (4, 1, 3), "slot #3 keeps its own")
                self.assertEqual(rig.emu.read32(rig.state + 0x38C), 99_500)
                if universal:                                            # a second one stacks there
                    rig.answers = [0]
                    rig.emu.call(rig.emu.symbols["_buy_chemical"], self.impl, rig.state, 500, RGH, *DS_ITEMS[RGH])
                    self.assertEqual(struct.unpack_from("<3i", rig.extra(0)), (RGH, 1, 6))

    def test_exotic_eggs_fill_extra_slots(self) -> None:
        for universal in (False, True):
            with self.subTest(universal=universal):
                rig = self.rig(universal)
                rig.put_stock(1, record(1, 3, 1))
                rig.put_stock(2, record(4, 3, 2))
                for e in range(5):
                    rig.put_extra(e, record(2, 3))
                rig.answers = [0, 0]
                if universal:
                    rig.emu.call(rig.emu.symbols["_buy_universal"], self.impl, rig.state, 2300, EXOTIC, 224, 224, 1)
                else:
                    rig.emu.call(rig.sym["_FtfpSupplySlotsLend@4"], EXOTIC)
                    rig.emu.call(rig.emu.symbols["_buy_exotic_stock"], self.impl, rig.state, 2300)
                    rig.emu.call(rig.sym["_FtfpSupplySlotsReturn@0"])
                self.assertEqual(struct.unpack_from("<i", rig.extra(5))[0], EXOTIC)
                self.assertEqual(struct.unpack_from("<3i", rig.stock(3)), (26, 1, 1), "the starter eggs stay")


@unittest.skipUnless(ready() and STORE_DLL.is_file(), "needs Unicorn, MSVC, the vanilla exe and DS Store Items")
class UpgradesScreenItem(unittest.TestCase):
    """DS Store Items' "Extra Supply Slots": $10,000 ($0 with Free upgrades), confirmed, once; "This is in
    your inventory." and "You already own this!" afterwards; its own picture; hidden without the setting."""

    CELL = (350, 200)

    def store(self, money: int, free: bool, owned: int | None):
        dll, symbols = store_built()
        emu = E.Emulator(EXE, dll, symbols)
        emu.hook_printf()
        emu.uc.mem_map(0, 0x1000)                          # fs:[0] for its __try
        self.owned = owned
        module = 0x7200_0000
        emu.hook_import("GetModuleHandleW", lambda e: module if owned is not None and
                        e.wstring(e.arg(0)) == "Extra Supply Slots.dll" else 0, 4)
        owned_fn, buy_fn, image_fn = emu.thunk(), emu.thunk(), emu.thunk()
        emu.hook(owned_fn, lambda e: self.owned if self.owned is not None else 0xFFFFFFFF, 0)

        def buy(e) -> int:
            if self.owned is None or self.owned >= 1:
                return 0xFFFFFFFF
            self.owned = 1
            return 1
        emu.hook(buy_fn, buy, 0)
        emu.hook(image_fn, lambda e: 0x5151_0000, 0)
        exports = {"FtfpSupplySlotsOwned": owned_fn, "FtfpSupplySlotsBuy": buy_fn, "FtfpSupplySlotsImage": image_fn}
        emu.hook_import("GetProcAddress", lambda e: exports.get(e.cstring(e.arg(1)).decode(), 0), 8)
        emu.hook_import("GetTickCount", lambda e: 0, 0)
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        emu.hook(0x004221A0, emu.record("dialog", args=1), 8)
        emu.hook(0x00401D00, emu.record("run", 0), 8)
        emu.hook(0x00422440, emu.record("free"), 0)
        emu.hook(0x00425120, emu.record("sounds"), 0)
        emu.hook(0x004251A0, emu.record("sound"), 4)
        table, price = emu.alloc(16), emu.text("Price:")
        inventory = emu.text("This is in your inventory.")
        emu.hook(0x00427060, lambda e: table, 0)
        emu.hook(0x00427050, lambda e: inventory if e.arg(0) == 0xE9 else price, 4)
        emu.hook(0x0041BE70, lambda e: e.calls.append(("sprite", e.arg(0))) or 1, 4)
        emu.hook(0x00408A40, emu.record("draw", args=3), 12)
        emu.hook(0x00408AE0, emu.record("draw", args=3), 24)
        emu.hook(0x00408B80, lambda e: (e.calls.append(("text", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 20)
        state, impl, scene = emu.alloc(0x40000), emu.alloc(0x100), emu.alloc(0x100)
        emu.write32(scene + 8, impl)
        emu.write32(impl + 0x10, state)
        emu.write32(impl + 0x0C, emu.alloc(0x40))
        emu.write32(state + 0x38C, money)
        emu.write32(emu.sym("_free_on"), int(free))
        emu.write32(emu.sym("_page_upgrades"), 1)
        emu.state, emu.scene = state, scene
        return emu

    def select(self, emu) -> None:
        emu.call(emu.sym("@on_mouse@20"), 3, *self.CELL, ecx=emu.scene)

    def test_price_picture_and_once(self) -> None:
        emu = self.store(25_000, free=False, owned=0)
        self.select(emu)
        self.assertEqual(emu.read32(emu.sym("_selected"), signed=True), 12)
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        texts = [c[1] for c in emu.calls if c[0] == "text"]
        self.assertIn("Extra Supply Slots", texts)
        self.assertIn("Price:  $10000", texts)
        self.assertIn(("draw", (0x5151_0000, 320 + (77 - 76) // 2, 168 + (69 - 51) // 2)), emu.calls,
                      "its own picture, centred in its net cell")
        emu.call(emu.sym("_buy"), emu.scene)
        self.assertEqual(self.owned, 1)
        self.assertEqual(emu.read32(emu.state + 0x38C), 15_000)
        self.assertIn(("dialog", (0xEC,)), emu.calls)
        emu.calls.clear()
        emu.call(emu.sym("_buy"), emu.scene)
        self.assertIn(("hint", (0x1C,)), emu.calls, "You already own this!")
        self.assertEqual(emu.read32(emu.state + 0x38C), 15_000)
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        self.assertIn(("text", "This is in your inventory."), emu.calls)

    def test_free_upgrades(self) -> None:
        emu = self.store(0, free=True, owned=0)
        self.select(emu)
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        self.assertIn(("text", "Price:  $0"), emu.calls)
        emu.call(emu.sym("_buy"), emu.scene)
        self.assertEqual(self.owned, 1)
        self.assertEqual(emu.read32(emu.state + 0x38C), 0)

    def test_too_little_money(self) -> None:
        emu = self.store(9_999, free=False, owned=0)
        self.select(emu)
        emu.call(emu.sym("_buy"), emu.scene)
        self.assertEqual(self.owned, 0)
        self.assertIn(("hint", (2,)), emu.calls)

    def test_hidden_without_the_setting(self) -> None:
        emu = self.store(25_000, free=False, owned=None)
        self.select(emu)
        self.assertEqual(emu.read32(emu.sym("_selected"), signed=True), -1)

    def test_the_net_cell_is_free(self) -> None:
        """Its cell overlaps no other item's."""
        text = (ROOT / "native" / "ftfp_ds_store" / "ftfp_ds_store.c").read_text(encoding="utf-8")
        cells = [tuple(int(v) for v in m.groups()) for m in
                 re.finditer(r"\{ FIN_\w+, \d+, (\d+), (\d+), (\d+), (\d+),", text)]
        cells += [tuple(int(v) for v in m.groups()) for m in re.finditer(r"\{ 0, \d+, (\d+), (\d+), (\d+), (\d+),", text)]
        self.assertEqual(len(cells), 15)
        for i, a in enumerate(cells):
            for b in cells[i + 1:]:
                self.assertFalse(a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3],
                                 (a, b))


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class SavesAndSidecar(unittest.TestCase):
    PATH = "C:\\Docs\\LDW\\Fish Tycoon - Modded Upgrades\\Fish Tycoon Fix Patcher Data\\Extra Supply Slots 3.dat"

    def rig(self):
        from test_extra_tanks import FakeFiles
        rig = Rig()
        files = FakeFiles(rig.emu, "C:\\Docs")
        return rig, files

    def test_round_trip(self) -> None:
        rig, files = self.rig()
        slots = [record((0, 2, 5, 3, 6, 7, 1)[e], e + 1) for e in range(7)]
        for e in range(7):
            rig.put_extra(e, slots[e])
        stock = [rig.stock(k) for k in range(4)]
        self.assertEqual(rig.emu.call(rig.sym["@save_slot_hook@12"], 3, ecx=rig.state) & 0xFF, 1)
        self.assertEqual(rig.saved, [b"".join(stock)], "the save holds the stock slots, as stock")
        data = files.files[self.PATH]
        self.assertEqual(len(data), 24 + 7 * REC)
        self.assertEqual(struct.unpack_from("<6I", data)[:4], (0x53535446, 1, 7, REC))
        self.assertEqual(struct.unpack_from("<I", data, 20)[0], 1, "bought")
        self.assertEqual(data[24:], b"".join(slots))
        self.assertNotIn(self.PATH + ".tmp", files.files)
        for e in range(7):
            rig.put_extra(e, EMPTY)
        rig.w("_owned", 0)
        rig.w("_page", 2)
        rig.emu.call(rig.sym["@load_hook@12"], 3, ecx=rig.state)
        self.assertEqual([rig.extra(e) for e in range(7)], slots)
        self.assertEqual(rig.r("_owned"), 1)
        self.assertEqual(rig.r("_page"), 0, "a loaded game opens on page 1")
        self.assertEqual(rig.r("_owner"), rig.state)

    def test_a_save_while_an_extra_slot_is_held(self) -> None:
        """Quitting with an extra slot's item in the hand: the save gets the stock slots in their own
        places, the file the held item in its extra slot, and the hand keeps holding it."""
        rig, files = self.rig()
        rig.put_extra(5, record(6, 2))
        stock = [rig.stock(k) for k in range(4)]
        rig.pick_extra(5)
        rig.emu.call(rig.sym["@save_quit_hook@12"], 3, ecx=rig.state)
        self.assertEqual(rig.saved, [b"".join(stock)])
        self.assertEqual(files.files[self.PATH][24 + 5 * REC: 24 + 5 * REC + 12], record(6, 2)[:12])
        self.assertEqual(rig.held(), 3)
        self.assertEqual(rig.stock(3)[:12], record(6, 2)[:12], "still held")

    def test_settings_slot_is_not_ours(self) -> None:
        rig, files = self.rig()
        rig.emu.call(rig.sym["@save_slot_hook@12"], 0, ecx=rig.state)
        self.assertEqual(files.files, {})

    def test_damaged_file_is_set_aside_and_slots_start_empty(self) -> None:
        rig, files = self.rig()
        files.files[self.PATH] = b"FTSS" + bytes(24 + 7 * REC - 4)
        rig.put_extra(0, record(2))
        rig.emu.call(rig.sym["@load_hook@12"], 3, ecx=rig.state)
        self.assertEqual(rig.extra(0), EMPTY)
        self.assertEqual(rig.r("_owned"), 0)
        self.assertNotIn(self.PATH, files.files)
        self.assertIn(self.PATH[:-4] + ".unreadable-1.dat", files.files)

    def test_missing_file_means_empty_and_not_bought(self) -> None:
        rig, files = self.rig()
        rig.put_extra(2, record(2))
        rig.emu.call(rig.sym["@load_hook@12"], 4, ecx=rig.state)
        self.assertEqual(rig.extra(2), EMPTY)
        self.assertEqual(rig.r("_owned"), 0)
        self.assertEqual(files.files, {})

    def test_new_game_empties_them(self) -> None:
        rig, _files = self.rig()
        rig.put_extra(1, record(2))
        rig.emu.call(rig.sym["@new_game_hook@8"], ecx=rig.state)
        self.assertEqual(rig.extra(1), EMPTY)
        self.assertEqual(rig.r("_owned"), 0, "a new game has not bought them")
        self.assertIn(("stock new game",), rig.calls)

    def test_a_failed_game_save_writes_no_sidecar(self) -> None:
        rig, files = self.rig()
        failing = rig.emu.thunk()
        rig.emu.hook(failing, lambda e: 0, 4)
        rig.w("_prev_save", failing)
        rig.emu.call(rig.sym["@save_slot_hook@12"], 2, ecx=rig.state)
        self.assertEqual(files.files, {})


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class AllOrNone(unittest.TestCase):
    SITES = (0x421FFB, 0x421D43, 0x42208E, 0x41EF3A, 0x4279F2, 0x4282DA, 0x41A663, 0x41AAC3)
    SLOTS = (0x4424D0, 0x4424D4)

    def rig(self, other_module: int = 0):
        rig = Rig()
        emu = rig.emu
        emu.hook_import("VirtualProtect", lambda e: e.write32(e.arg(3), 0x20) or 1, 16)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetModuleHandleW", lambda e: 0x400000, 4)

        def handle_from(e) -> int:
            address = e.arg(1)
            module = other_module if other_module and other_module <= address < other_module + 0x10000 else 0x400000
            e.write32(e.arg(2), module)
            return 1
        emu.hook_import("GetModuleHandleExW", handle_from, 12)
        return rig

    def code(self, rig: Rig) -> bytes:
        return b"".join(bytes(rig.emu.uc.mem_read(va, 5)) for va in self.SITES + self.SLOTS)

    def install(self, rig: Rig) -> int:
        if not rig.emu.call(rig.sym["_prepare"]):
            return 0
        return rig.emu.call(rig.sym["_ftfp_install_sites"], rig.sym["_writes"], len(self.SITES) + len(self.SLOTS))

    def test_every_site_or_none(self) -> None:
        for va in self.SITES:
            with self.subTest(site=hex(va)):
                rig = self.rig()
                rig.emu.uc.mem_write(va, b"\x90\x90\x90\x90\x90")        # one site not what it expects
                before = self.code(rig)
                self.assertEqual(self.install(rig), 0)
                self.assertEqual(self.code(rig), before, "nothing was written")

    def test_all_sites_go_in(self) -> None:
        rig = self.rig()
        self.assertEqual(self.install(rig), 1)
        for va in self.SITES:
            rel = struct.unpack("<i", rig.emu.uc.mem_read(va + 1, 4))[0]
            self.assertGreaterEqual(va + 5 + rel, 0x13000000, hex(va))
        for va in self.SLOTS:
            self.assertGreaterEqual(rig.emu.read32(va), 0x13000000)
        self.assertEqual(rig.r("_prev_load"), 0x41AE70)
        self.assertEqual(rig.r("_prev_save"), 0x419100)
        self.assertEqual(rig.r("_prev_store_buy"), 0x428080)

    def test_the_shared_sites_are_chained(self) -> None:
        other = 0x20F00000                              # inside the emulator's heap: "another module"
        rig = self.rig(other_module=other)
        for i, va in enumerate((0x421FFB, 0x421D43, 0x41A663, 0x41AAC3)):
            rig.emu.uc.mem_write(va, b"\xE8" + struct.pack("<i", other + 0x100 * (i + 1) - (va + 5)))
        rig.emu.uc.mem_write(0x42208E, b"\xE9" + struct.pack("<i", other + 0x600 - (0x42208E + 5)))
        rig.emu.write32(0x4424D0, other + 0x700)
        rig.emu.write32(0x4424D4, other + 0x800)
        self.assertEqual(self.install(rig), 1)
        for name, want in (("_prev_mouse", 0x100), ("_prev_release", 0x200), ("_prev_save_quit", 0x300),
                           ("_prev_new_game", 0x400), ("_prev_draw", 0x600), ("_prev_load", 0x700),
                           ("_prev_save", 0x800)):
            self.assertEqual(rig.r(name) & 0xFFFFFFFF, other + want, name)

    def test_a_branch_into_the_game_itself_is_refused(self) -> None:
        rig = self.rig()
        rig.emu.uc.mem_write(0x421FFB, b"\xE8" + struct.pack("<i", 0x401000 - (0x421FFB + 5)))
        self.assertEqual(self.install(rig), 0)


def site_ranges() -> dict[str, list[tuple[int, int]]]:
    """Every site every Fish companion writes, from its site header (or its own list): name -> ranges."""
    out: dict[str, list[tuple[int, int]]] = {}
    for header in sorted((ROOT / "native").glob("ftfp_*/*sites*.h")):
        if "plant" in header.parent.name or header.parent.name in (
                "ftfp_new_flowers", "ftfp_extra_greenhouses", "ftfp_seed_boxes", "ftfp_sort_seeds",
                "ftfp_greenhouse_counts", "ftfp_plant_prices", "ftfp_plant_upgrades", "ftfp_chem_slots"):
            continue
        text = header.read_text(encoding="utf-8")
        for m in re.finditer(r"#define SITE_(\w+)_VA 0x([0-9A-Fa-f]+)u", text):
            name, va = m.group(1), int(m.group(2), 16)
            n = re.search(rf"#define SITE_{name}_LEN (\d+)", text)
            length = int(n.group(1)) if n else 4
            out.setdefault(header.parent.name, []).append((va, va + length))
    return out


class SitesOverlapNothing(unittest.TestCase):
    """Every site this DLL writes is either written by no other companion and no Fix Patcher patch, or
    is exactly a site other companions chain too (the same instruction, a call/jmp or a table slot)."""

    SHARED = {0x421FFB, 0x421D43, 0x42208E, 0x41A663, 0x41AAC3, 0x4424D0, 0x4424D4}

    def test_no_overlap(self) -> None:
        ranges = site_ranges()
        mine = ranges.pop("ftfp_supply_slots")
        self.assertEqual(len(mine), 10)
        others = [(name, a, b) for name, rs in ranges.items() for a, b in rs]
        try:
            import build_ds_fish_headers as H
        except ImportError:
            self.skipTest("needs capstone (the header scripts disassemble the game)")
        patches = H.fix_patcher_ranges()
        for a, b in mine:
            for start, end in patches:
                self.assertFalse(start < b and a < end, f"0x{a:X} overlaps a Fix Patcher patch at 0x{start:X}")
            for name, c, d in others:
                if c < b and a < d:
                    self.assertIn(a, self.SHARED, f"0x{a:X} overlaps {name}'s site 0x{c:X}")
                    self.assertEqual((a, b), (c, d), f"0x{a:X}: shared, so exactly the same site as {name}'s")

    def test_the_only_new_sites_are_untouched_by_anyone(self) -> None:
        ranges = site_ranges()
        mine = ranges.pop("ftfp_supply_slots")
        everyone = {a for rs in ranges.values() for a, _ in rs}
        self.assertEqual({a for a, _ in mine} - everyone, {0x41EF3A, 0x4279F2, 0x4282DA})


def built_exe(enabled: set[str]) -> Path:
    key = ",".join(sorted(enabled))
    if key not in _BUILT:
        import test_fish_30 as F
        path = Path(tempfile.mkdtemp(prefix="ftfp_slots_exe_")) / "patched.exe"
        path.write_bytes(F.patched_exe(enabled))
        _BUILT[key] = path
    return _BUILT[key]


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class EveryPatchAtOnce(unittest.TestCase):
    """The owner's rule: everything works with every patch. On the executable with every Fish setting
    on ("Enable All") and with only DS Store Items' settings, every other companion's writes are put in
    first (each site a branch, each table slot a pointer, into another loaded module, as those DLLs
    install before this one); this DLL then installs all of its sites, chaining the shared ones, and its
    log says so. A purchase, a pick, a use and a drop then run on that executable."""

    OTHER = 0x20F00000                                   # inside the emulator's heap: "another module"

    def install_over_everyone(self, enabled: set[str]) -> Rig:
        from test_extra_tanks import FakeFiles
        rig = Rig(exe=built_exe(enabled), universal=False)
        emu = rig.emu
        files = FakeFiles(emu, "C:\\Docs")
        self.files = files
        emu.hook_import("VirtualProtect", lambda e: e.write32(e.arg(3), 0x20) or 1, 16)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetFileAttributesW", lambda e: 0xFFFFFFFF, 4)          # its companions: loaded already

        def handle_from(e) -> int:
            address = e.arg(1)
            inside = self.OTHER <= address < self.OTHER + 0x100000
            e.write32(e.arg(2), self.OTHER if inside else 0x400000)
            return 1
        emu.hook_import("GetModuleHandleExW", handle_from, 12)
        ranges = site_ranges()
        ranges.pop("ftfp_supply_slots")
        n = 0
        for name, sites in ranges.items():
            for a, b in sites:
                n += 1
                target = self.OTHER + 0x40 * n
                if b - a == 4 and a >= 0x440000:                                  # a table slot
                    emu.write32(a, target)
                else:
                    op = emu.uc.mem_read(a, 1)[0]
                    op = op if op in (0xE8, 0xE9) else 0xE9
                    emu.uc.mem_write(a, bytes([op]) + struct.pack("<i", target - (a + 5)) + b"\x90" * (b - a - 5))
        rig.w("_installed", 0)
        self.assertEqual(rig.emu.call(rig.sym["_FtfpStartup@0"]), 1)
        log = files.files["C:\\Games\\Fish Tycoon - Modded Upgrades\\Extra Supply Slots.log"]
        self.assertEqual(log, b"Extra Supply Slots: installed (all sites)\r\n")
        for name in ("_prev_mouse", "_prev_release", "_prev_draw", "_prev_save_quit", "_prev_load", "_prev_save"):
            self.assertGreaterEqual(rig.r(name) & 0xFFFFFFFF, self.OTHER, f"{name} chains the companion before it")
        return rig

    def test_enable_all(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.install_over_everyone({s["id"] for s in manifest["settings"]})

    def test_only_ds_store_items_and_this(self) -> None:
        self.install_over_everyone({"ds_fish", "ds_store", "extra_supply_slots"})

    def test_buying_and_using_on_the_enable_all_executable(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        rig = Rig(exe=built_exe({s["id"] for s in manifest["settings"]}))   # Universal supply slots is in it
        rig.put_stock(1, record(1, 3, 1))
        rig.put_stock(2, record(4, 3, 2))
        rig.put_stock(3, record(7, 3, 3))
        store = BuyingSupplies.store(None, rig)
        rig.answers = [0]
        rig.emu.call(rig.sym["@store_buy_hook@12"], 2, ecx=store)
        self.assertEqual(struct.unpack_from("<3i", rig.extra(0)), (2, 1, 3))
        UseRig.prepare(rig)
        rig.pick_extra(0)
        rig.let_go(*IN_TANK)
        self.assertEqual(struct.unpack_from("<3i", rig.extra(0)), (2, 1, 2), "one dose used")
        self.assertEqual(struct.unpack_from("<3i", rig.stock(2)), (4, 1, 3))


class Layout(unittest.TestCase):
    """The arrows sit in the top bar's gap between supply slot 4 and the Magic Breeds silhouettes, clear
    of the Extra Tanks arrows and the tank buttons; the page-3 cover is the size of a slot frame."""

    def test_the_arrows_are_clear_of_everything_on_the_bar(self) -> None:
        arrows = [(ARROW_X, y, ARROW_X + ARROW_W - 1, y + ARROW_H - 1) for y in (ARROW_UP_Y, ARROW_DOWN_Y)]
        others = list(BOXES) + [(227 + 39 * i, 15, 227 + 39 * i + 38, 45) for i in range(7)]   # the silhouettes
        others += [(495, 8, 512, 22), (495, 31, 512, 45)]                                     # Extra Tanks' arrows
        others += [(513, 2, 598, 54), (610, 2, 695, 54), (707, 2, 792, 54)]                  # the tank buttons
        for a in arrows:
            self.assertLessEqual(a[3], 56, "inside the 57-pixel bar")
            for b in others:
                self.assertFalse(a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3], (a, b))
        self.assertGreater(arrows[1][1], arrows[0][3], "one above the other")

    def test_the_source_and_the_art_agree(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("needs Pillow")
        text = (ROOT / "native" / "ftfp_supply_slots" / "ftfp_supply_slots.c").read_text(encoding="utf-8")
        for name, value in (("ARROW_X", ARROW_X), ("ARROW_Y_LEFT", ARROW_UP_Y), ("ARROW_Y_RIGHT", ARROW_DOWN_Y),
                            ("ARROW_W", ARROW_W), ("ARROW_H", ARROW_H)):
            self.assertRegex(text, rf"#define {name} {value}\b")
        images = ROOT / "assets" / "fish_tycoon_supply_slots" / "Images"
        for name in ("SupplyArrowLeft.png", "SupplyArrowRight.png"):
            self.assertEqual(Image.open(images / name).size, (3 * ARROW_W, ARROW_H), "3 frames at scale 1")
        left, top, right, bottom = BOXES[3]
        self.assertEqual(Image.open(images / "SupplySlotUnused.png").size, (right - left + 1, bottom - top + 1))
        self.assertEqual(Image.open(images / "ITEM_EXTRA_SUPPLY_SLOTS.png").size, (76, 51))

    def test_no_file_name_clashes_with_another_setting(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        mine = {f["destination"].lower() for s in manifest["settings"] if s["id"] == "extra_supply_slots"
                for f in s["companion"]["files"]}
        for s in manifest["settings"]:
            if s["id"] != "extra_supply_slots":
                theirs = {f["destination"].lower() for f in s.get("companion", {}).get("files", [])}
                self.assertFalse(mine & theirs, s["id"])


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class Maximized(unittest.TestCase):
    """In a maximized window Maximizable Window.dll maps every mouse message back to the game's 800 x
    600 before the game sees it (test_fish_window checks the maths), so a click on an arrow or a slot
    anywhere on its pixels reaches this DLL as a click on the arrow or the slot."""

    def test_clicks_on_the_arrows_and_slots(self) -> None:
        import test_fish_window as W
        for cw, ch in ((1920, 1017), (1366, 705), (2560, 1377)):
            x, y, w, h = W.fit(cw, ch)
            to_game = lambda gx, gy: (W.to_picture(x + gx * w // 800 + 1, x, w, 800),     # noqa: E731
                                      W.to_picture(y + gy * h // 600 + 1, y, h, 600))
            with self.subTest(window=(cw, ch)):
                rig = Rig()
                rig.click(*to_game(ARROW_X + 2, ARROW_DOWN_Y + 2))
                self.assertEqual(rig.page(), 1)
                rig.put_extra(2, record(3))
                rig.press(*to_game(*centre(2)))
                self.assertEqual(rig.held(), 2)
                rig.let_go(*to_game(*centre(0)))
                self.assertEqual(struct.unpack_from("<i", rig.extra(0))[0], 3)


class BackupsHoldTheSlots(unittest.TestCase):
    def test_every_file_names_its_slot(self) -> None:
        import save_backup
        for name, slot in (("Extra Supply Slots 1.dat", 1), ("Extra Supply Slots 21.dat", 1),
                           ("Extra Supply Slots 2.unreadable-1.dat", 2), ("Extra Supply Slots 3.dat.tmp", 3)):
            self.assertEqual(save_backup.file_slot("fish", Path("Fish Tycoon Fix Patcher Data") / name), slot, name)


class Manifest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.settings = {s["id"]: s for s in self.manifest["settings"]}

    def test_setting(self) -> None:
        s = self.settings["extra_supply_slots"]
        self.assertEqual(s["name"], "Extra supply slots")
        self.assertTrue(s["summary"].startswith("EXPERIMENTAL - USE AT OWN RISK."))
        self.assertTrue(s["description"].startswith("EXPERIMENTAL - USE AT OWN RISK."))
        self.assertTrue(s["default"])  # on by default (the owner, 2026-11-01: new content stays on)
        self.assertTrue(s["experimental"])
        self.assertTrue(s["separate_output"])
        self.assertEqual(s["requires_settings"], ["ds_store"])
        self.assertIn("nothing is deleted", s["warning"].lower())
        ids = [x["id"] for x in self.manifest["settings"]]
        self.assertEqual(ids.index("extra_supply_slots"), ids.index("extra_tanks") + 1)

    def test_companion_files_are_pinned(self) -> None:
        import hashlib
        companion = self.settings["extra_supply_slots"]["companion"]
        self.assertTrue(companion["startup_loader"])
        source = ROOT / companion["source"]
        names = {e["path"] for e in companion["files"]}
        self.assertEqual(names, {"Extra Supply Slots.dll", "Images/SupplyArrowLeft.png", "Images/SupplyArrowRight.png",
                                 "Images/SupplySlotUnused.png", "Images/ITEM_EXTRA_SUPPLY_SLOTS.png",
                                 "Images/SupplyPage1.png", "Images/SupplyPage2.png", "Images/SupplyPage3.png"})
        for entry in companion["files"]:
            data = (source / entry["path"]).read_bytes()
            self.assertEqual(len(data), entry["size"], entry["path"])
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"], entry["path"])

    def test_every_combination_is_pinned_with_and_without(self) -> None:
        pins = self.manifest["patched_sha256_by_settings"]
        without = [k for k in pins if "extra_supply_slots" not in k.split(",") and "ds_store" in k.split(",")]
        self.assertTrue(without)
        for key in without:
            self.assertIn(",".join(sorted(set(key.split(",")) | {"extra_supply_slots"})), pins)
        for key in pins:
            if "extra_supply_slots" in key.split(","):
                self.assertIn("ds_store", key.split(","))

    def test_off_leaves_every_other_pin_unchanged(self) -> None:
        for patch in self.manifest["patches"]:
            self.assertNotIn("extra_supply_slots", patch.get("requires", []))
        for key in self.manifest["patched_sha256_by_settings"]:
            enabled = set(key.split(",")) - {""}
            names = ds_fish_loader.fish_profile(enabled).dll_names
            self.assertEqual("Extra Supply Slots.dll" in names, "extra_supply_slots" in enabled, key)

    def test_loader_order(self) -> None:
        base = {"ds_fish", "ds_store", "extra_supply_slots"}
        self.assertEqual(ds_fish_loader.fish_profile(base).dll_names, ("Extra Supply Slots.dll",))
        self.assertEqual(ds_fish_loader.fish_profile(base | {"extra_tanks", "multiple_ornaments",
                                                             "tank_greenhouse_counts", "optimize_prices"}).dll_names,
                         ("Extra Tanks.dll", "Extra Supply Slots.dll", "Tank Counts.dll", "Optimize Prices.dll"))
        self.assertEqual(ds_fish_loader.fish_profile(base | {"multiple_ornaments"}).dll_names,
                         ("Extra Supply Slots.dll",), "it loads Multiple Ornaments itself, as Extra Tanks does")

    @unittest.skipUnless(EXE.is_file(), "needs the vanilla Fish Tycoon.exe")
    def test_pins_match_a_fresh_build(self) -> None:
        import hashlib
        import fish_patcher
        pins = self.manifest["patched_sha256_by_settings"]
        vanilla = EXE.read_bytes()
        everything = fish_patcher.pin_settings(self.manifest, {s["id"] for s in self.manifest["settings"]})
        for enabled in ({"extra_supply_slots", "ds_fish", "ds_store"},
                        {"extra_supply_slots", "ds_fish", "ds_store", "universal_supply_slots", "extra_tanks"},
                        everything):
            patched, _ = fish_patcher.apply_patch_bytes(vanilla, fish_patcher.active_patch_records(self.manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.fish_profile(enabled))
            self.assertEqual(hashlib.sha256(patched).hexdigest().upper(), pins[fish_patcher.settings_key(enabled)])
            self.assertIn("Extra Supply Slots.dll".encode("utf-16-le"), patched)


if __name__ == "__main__":
    unittest.main()
