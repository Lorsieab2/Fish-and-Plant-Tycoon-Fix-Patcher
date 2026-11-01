"""One tooltip at a time in the Plant Tycoon store (Store Upgrades and Items.dll).

The owner (2026-11-01): tooltips must never overlap one another from another page or view.  A game
tooltip (0x409870) is a shell around a body that takes every mouse move itself (0x409D70) and is
drawn whenever the mouse is over its rect (0x409B70); nothing reads the shell's +8, which the DLL
used to set to hide the stock items' tooltips on its Upgrades view (and its own on the stock view).
The stock shelves and the Upgrades view's items share the same places, so both came up together.
Now a hidden tooltip has an empty rect and no hover.

Emulated on the vanilla executable (tests/store_emulator.py): the DLL rebuilt from its committed
source, the store's own tooltip builder (0x446D40) making the stock items' tooltips with every item
on the shelves, and the game's own mouse handler of a tooltip body.
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

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
DLL = ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll"
READY = E is not None and E.toolchain_ready() and PLANT_EXE is not None and PLANT_EXE.is_file()
needs_game = unittest.skipUnless(READY, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")

STOCK_TIPS = range(6, 54)                 # the store's item tooltips: scene + 0x10 + 4 * slot
SEED_RECORD = 36                          # the DLL's seed_record; present at +24


def contains(r: tuple[int, int, int, int], x: int, y: int) -> bool:
    return r[0] <= x <= r[2] and r[1] <= y <= r[3]


@needs_game
class StoreTooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------------ the store
    def store(self):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.uc.mem_map(0, 0x1000)                                       # fs:[0]
        emu.hook_printf()
        emu.tips = {}
        zero = emu.thunk()
        emu.hook(zero, lambda e: 0, 0)                                   # every companion's "owned": 0
        emu.hook_import("GetModuleHandleW", lambda e: 0x6D000000, 4)    # every companion DLL is there
        emu.hook_import("GetProcAddress", lambda e: zero, 8)
        for name, pop in (("GetActiveWindow", 0), ("GetForegroundWindow", 0)):
            emu.hook_import(name, emu.record(name), pop)
        emu.hook(0x0044A580, emu.record("sound"), 4)
        emu.hook(0x0044E894, lambda e: e.alloc(max(e.arg(0), 0x40)), 0)
        emu.hook(0x00409870, self._tip_new, 0x1C)
        emu.hook(0x00409AA0, self._tip_text, 0x10)
        emu.hook(0x0040B400, emu.record("control"), 4)
        emu.hook(0x0040B480, self._tip_remove, 4)
        emu.hook(0x0044CA70, lambda e: e.text(f"String {e.arg(0):#x}"), 4)
        emu.hook(0x0044F30B, self._sprintf, 0)                           # cdecl: the caller pops
        emu.hook(0x00402050, lambda e: 0, 0)                             # no button down
        emu.hook(0x00402060, lambda e: 0, 0)                             # the tooltips' clock
        emu.hook(0x004208F0, lambda e: 0, 0x1C)                          # the DLL's draws
        emu.hook(0x004207F0, lambda e: 0, 0x14)
        state = emu.alloc(0x60000)
        scene = emu.alloc(0x400)
        emu.write32(scene + 4, emu.alloc(0x20))                          # its rect (0x40B380): at 0, 0
        emu.write32(scene + 0x1BC, state)
        emu.write32(scene + 0x1C8, emu.alloc(0x40))
        for offset in range(0x5BC, 0x900):                               # every stock item on the shelves
            emu.write8(state + offset, 1)
        legendary = emu.sym("_legendary")
        for i in range(3):
            emu.write8(legendary + SEED_RECORD * i + 24, 1)
        for i in range(2):                                               # the Extra Greenhouse and Nursery
            emu.write32(emu.sym("_extra_owned") + 4 * i, zero)
            emu.write32(emu.sym("_extra_buy") + 4 * i, zero)
        for flag in ("_warp_on", "_money_on"):
            emu.write32(emu.sym(flag), 1)
        emu.state, emu.scene = state, scene
        return emu

    def _tip_new(self, e) -> int:
        """0x409870: the shell (+8 1, +0xC its body) and the body (0x4094A0: +4 id, +0x10 rect,
        +0x30 parent, +0x39 1, +0x3A not hovered)."""
        tip = e.uc.reg_read(X.UC_X86_REG_ECX)
        rect = struct.unpack("<4i", e.uc.mem_read(e.arg(1), 16))
        body = e.alloc(0x6C)
        e.write32(body + 4, e.arg(0))
        e.uc.mem_write(body + 0x10, struct.pack("<4i", *rect))
        e.write32(body + 0x30, e.arg(2))
        e.write8(body + 0x39, 1)
        e.write32(tip + 0xC, body)
        e.write8(tip + 8, 1)
        e.tips[tip] = {"rect": rect, "text": e.cstring(e.arg(3)).decode("latin-1"), "body": body}
        return tip

    def _tip_text(self, e) -> int:
        tip = e.uc.reg_read(X.UC_X86_REG_ECX)
        if tip in e.tips:
            e.tips[tip]["text"] = e.cstring(e.arg(0)).decode("latin-1")
        return 0

    def _tip_remove(self, e) -> int:
        e.tips.pop(e.arg(0), None)
        return 0

    def _sprintf(self, e) -> int:
        e.uc.mem_write(e.arg(0), b"Stock item\x00")
        return 10

    def stock_builder(self, emu) -> None:
        """The store's own (0x446D40, thiscall scene (1)): makes or retexts every stock item's tooltip."""
        emu.call(0x00446D40, 1, ecx=emu.scene)

    def view(self, emu, upgrades: int) -> None:
        emu.write32(emu.sym("_upgrades_view"), upgrades)
        emu.call(emu.sym("_set_tooltips"), emu.scene)
        emu.call(emu.sym("_on_draw"), emu.scene)

    def stock_tip_set(self, emu) -> set[int]:
        return {emu.read32(emu.scene + 0x10 + 4 * s) for s in STOCK_TIPS} - {0}

    def body_rect(self, emu, tip: int) -> tuple[int, int, int, int]:
        return struct.unpack("<4i", emu.uc.mem_read(emu.tips[tip]["body"] + 0x10, 16))

    def live(self, emu) -> dict[int, tuple]:
        """Every tooltip the mouse can bring up now (its body keeps a rect), with that rect."""
        out = {}
        for tip in emu.tips:
            r = self.body_rect(emu, tip)
            if r[0] <= r[2] and r[1] <= r[3]:
                self.assertEqual(r, emu.tips[tip]["rect"])                # only ever its own rect
                out[tip] = r
            else:
                self.assertFalse(emu.uc.mem_read(emu.tips[tip]["body"] + 0x3A, 1)[0])
        return out

    def move(self, emu, x: int, y: int) -> list[int]:
        """The mouse to (x, y) through every body's own handler (0x409D70); the hovered tooltips."""
        for t in emu.tips.values():
            emu.call(0x00409D70, 1, x, y, ecx=t["body"])
        return [tip for tip, t in emu.tips.items() if emu.uc.mem_read(t["body"] + 0x3A, 1)[0]]

    # ------------------------------------------------------------------ the tests
    def made(self):
        emu = self.store()
        self.stock_builder(emu)
        self.assertGreaterEqual(len(self.stock_tip_set(emu)), 20)
        emu.call(emu.sym("_on_activate"), emu.scene, 1)
        self.stock_builder(emu)                                          # the store retexts them on entry
        return emu

    def test_each_view_has_at_most_one_tooltip_under_any_point(self) -> None:
        emu = self.made()
        stock = self.stock_tip_set(emu)
        own = set(emu.tips) - stock
        self.assertGreaterEqual(len(own), 12)
        for upgrades in (0, 1, 0, 1):
            self.view(emu, upgrades)
            live = self.live(emu)
            with self.subTest(view="Upgrades" if upgrades else "stock"):
                if upgrades:                                              # its own items (no Seed Box here)
                    self.assertTrue(set(live) <= own and len(live) >= len(own) - 1, (len(live), len(own)))
                else:
                    self.assertEqual(set(live), stock)
                for x in range(0, 800, 3):
                    for y in range(0, 600, 3):
                        under = [t for t, r in live.items() if contains(r, x, y)]
                        self.assertLessEqual(len(under), 1, (x, y, [emu.tips[t]["text"] for t in under]))

    def test_the_games_own_hover_brings_up_only_the_view_shown(self) -> None:
        emu = self.made()
        stock = self.stock_tip_set(emu)
        for upgrades in (0, 1):
            self.view(emu, upgrades)
            for tip, t in list(emu.tips.items()):
                r = t["rect"]
                x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
                hovered = self.move(emu, x, y)
                with self.subTest(view=upgrades, item=t["text"]):
                    self.assertLessEqual(len(hovered), 1)
                    if hovered:
                        self.assertEqual(hovered[0] in stock, not upgrades)

    def test_a_hovered_tooltip_goes_with_its_view_and_a_remade_one_stays_hidden(self) -> None:
        emu = self.made()
        self.view(emu, 0)
        tip = sorted(self.stock_tip_set(emu))[0]
        r = emu.tips[tip]["rect"]
        self.assertEqual(self.move(emu, r[0] + 2, r[1] + 2), [tip])
        self.view(emu, 1)                                                 # no mouse move: gone at once
        self.assertNotIn(tip, [t for t in emu.tips if emu.uc.mem_read(emu.tips[t]["body"] + 0x3A, 1)[0]])
        for s in STOCK_TIPS:                                              # the store remakes them all
            emu.write32(emu.scene + 0x10 + 4 * s, 0)
        self.stock_builder(emu)
        emu.call(emu.sym("_on_draw"), emu.scene)                          # the next frame
        stock = self.stock_tip_set(emu)
        self.assertFalse(set(self.live(emu)) & stock)
        self.view(emu, 0)                                                 # and back on the stock view
        self.assertEqual(set(self.live(emu)), stock)


if __name__ == "__main__":
    unittest.main()
