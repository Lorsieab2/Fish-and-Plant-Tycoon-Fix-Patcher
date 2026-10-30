"""Clicks in a scaled (maximized) Fish Tycoon window reach the right control.

The owner maximized the window, put the game's cursor on "Tank Six" and got the
Trophy Case; its Done button then did nothing. The game draws its own cursor where
SDL_GetMouseState says (0x408650), and SDL sets that from its own GetCursorPos +
ScreenToClient after every batch of messages (DIB_PumpEvents), which the
Maximizable window DLL did not scale; only the click messages were scaled. So the
click landed up and to the left of the cursor -- for Tanks 4-6 on the tank
screen's magic fish shelf (212-480, 4-44, 0x41CE8E), which opens the Trophy Case
(0x421F16 -> 0x418990(4)).

These tests run the whole path: the player puts the game's cursor (SDL_GetMouseState,
from the real SDL.dll's pump through "Maximizable Window.dll") on each tank button
and arrow, clicks or drops a held fish there (the real SDL.dll's window procedure
and pump, through the DLL's window procedure), and the button events SDL queues go
to the tank screen's own mouse handler (0x421B80) through "Extra Tanks.dll"'s
hooks -- at the window's own size and scaled, Tanks 4-6 bought and not -- and the
right tank shows, or the fish goes to the right tank, and no other screen opens.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_extra_tanks as X  # noqa: E402
import test_fish_window as W  # noqa: E402

E = W.E
SIZES = ((800, 600), (1920, 1017), (1366, 705), (2560, 1377), (1280, 1024))
BUTTONS = ((513, 2, 598, 54), (610, 2, 695, 54), (707, 2, 792, 54))       # 0x41CDD4
SHELF = (212, 4, 480, 44)                                               # the magic fish shelf, 0x41CE8E
ARROWS = ((503, 15), (503, 38))                                         # left (previous), right (next)
S_SCENE = 0x1E4FC                                                       # 0x418990: the screen asked for next
WM_LBUTTONUP = 0x202
CENTRES = tuple(((l + r) // 2, (t + b) // 2) for l, t, r, b in BUTTONS)


def _ready() -> bool:
    return (E is not None and E.toolchain_ready() and W.FISH_EXE is not None and W.FISH_EXE.is_file()
            and W.SDL_DLL.is_file() and X.DLL.is_file())


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


@unittest.skipUnless(_ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and SDL.dll, and the built DLLs")
class ScaledWindowClicks(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        W.EmulatedDllTests.setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        W.EmulatedDllTests.tearDownClass()

    # ------------------------------------------------------------ the window and SDL
    def window(self, size: tuple[int, int]) -> W.EmulatedDllTests:
        win = W.EmulatedDllTests("test_own_size_pointer_is_stock")
        win.setUp()
        win.windowed()
        win.sdl_ready()
        win.client = list(size)
        return win

    def aim(self, win: W.EmulatedDllTests, target: tuple[int, int]) -> tuple[int, int]:
        """The client point that puts the game's cursor (SDL_GetMouseState) on target."""
        x, y, w, h = W.fit(*win.client)
        if win.client == [800, 600]:
            x, y, w, h = 0, 0, 800, 600
        # Where the picture shows target; else (SDL's pointer unscaled) the raw client point.
        for at in ((x + ceil_div(target[0] * w, 800), y + ceil_div(target[1] * h, 600)), target):
            win.sdl_message(W.WM_MOUSEMOVE, *at)
            if win.mouse_state() == target:
                return at
        self.fail(f"the game's cursor cannot be put on {target} at {win.client}")

    def click(self, win: W.EmulatedDllTests, target: tuple[int, int]) -> list[tuple[int, int, int]]:
        """Press and let go with the game's cursor on target: the button events SDL queued."""
        at = self.aim(win, target)
        win.events.clear()
        win.sdl_message(W.WM_LBUTTONDOWN, *at)
        win.sdl_message(WM_LBUTTONUP, *at)
        buttons = [event for event in win.events if event[0] in (5, 6)]
        self.assertEqual([kind for kind, _x, _y in buttons], [5, 6])
        return buttons

    # ------------------------------------------------------------ the tank screen
    def rig(self, owned: int, page: int, current: int) -> X.Rig:
        rig = X.Rig()
        emu = rig.emu
        rig.var("_owned", owned)
        rig.var("_page", page)
        rig.set(0x384, current)
        rig.var("_prev_mouse", 0x00421B80)                                 # the stock handler underneath
        for offset, rect in ((0x88, (0x28A, 0x21D, 0x2B1, 0x258)), (0x98, (0x1F4, 0x1E9, 0x27F, 0x258)),
                             (0xA8, (0, 0x33, 0x31E, 0x1E9)), (0xB8, SHELF)):   # the rest of 0x41CDC0's rects
            emu.uc.mem_write(rig.impl + offset, struct.pack("<4i", *rect))
        emu.uc.mem_write(rig.impl + 0xC8, bytes(5))
        emu.write32(rig.impl + 0x1C, 0x63)                                 # nothing held
        emu.write32(rig.impl + 0x28, 0x63)
        holder, inner = emu.alloc(16), emu.alloc(16)
        emu.write32(holder, inner)
        emu.hook(0x004021E0, lambda e: holder, 0)                         # the game's input singleton
        emu.hook(0x0041EFB0, lambda e: rig.calls.append(("tank", e.arg(0), e.arg(1))) or 0, 8)
        emu.hook(0x0041BDD0, lambda e: holder, 0)                         # cursor sprites: nothing to draw
        emu.hook(0x0041BE70, lambda e: 0, 4)                              # (sprite id) -> image
        emu.hook(0x00407B20, lambda e: 0, 12)                             # (image, 1, 1): the cursor
        emu.hook(0x0040AE20, lambda e: 0, 4)                              # sounds
        emu.hook(0x0040AC30, lambda e: rig.calls.append(("leave", e.arg(0))) or 0, 4)
        emu.hook(0x0041E720, lambda e: rig.calls.append(("bottom", e.arg(0))) or 0, 12)
        emu.hook(0x00402080, lambda e: 0, 0)                              # the button is up when it is let go
        emu.hook(0x0041E600, lambda e: rig.calls.append(("carry", e.arg(0), e.arg(1))) or 0, 8)
        # The DLL's own release hook where it patches the stock release call (0x421D43).
        emu.uc.mem_write(0x00421D43, b"\xE8" + struct.pack("<i", rig.sym["@release_hook@16"] - 0x00421D48))
        return rig

    def game(self, rig: X.Rig, events: list[tuple[int, int, int]]) -> None:
        """SDL's events as the game's loop hands them on (0x403DC0): motion 1, down 2, up 3."""
        for kind, x, y in events:
            rig.emu.call(rig.sym["@mouse_hook@20"], {4: 1, 5: 2, 6: 3}[kind], x, y, ecx=rig.impl)

    def no_other_screen(self, rig: X.Rig, label: str) -> None:
        self.assertEqual(rig.get(S_SCENE), 0, f"{label}: another screen (the Trophy Case) was opened")
        self.assertFalse([c for c in rig.calls if c[0] in ("leave", "bottom", "tank")], label)

    # ------------------------------------------------------------ clicks
    def test_every_tank_button_and_arrow(self) -> None:
        for size in SIZES:
            for owned in (0, 3):
                with self.subTest(size=size, owned=owned):
                    self._buttons(size, owned)

    def _buttons(self, size: tuple[int, int], owned: int) -> None:
        win = self.window(size)
        for b in range(3):                                                 # Tank One, Tank Two, the Sale Tank
            rig = self.rig(owned, page=0, current=(b + 1) % 3)
            self.game(rig, self.click(win, CENTRES[b]))
            label = f"{size} stock button {b}"
            self.assertEqual(rig.get(0x384), b, label)
            self.assertIn(("switch", b), rig.calls, label)
            self.no_other_screen(rig, label)
        for a, target in enumerate(ARROWS):
            for page in (0, 1):
                rig = self.rig(owned, page=page, current=1)
                self.game(rig, self.click(win, target))
                label = f"{size} arrow {a} from page {page}"
                self.assertEqual(rig.var("_page"), 1 - page, label)
                self.assertEqual(rig.get(0x384), 1, label)
                self.no_other_screen(rig, label)
        for b in range(3):                                                 # Tank Four, Five, Six
            rig = self.rig(owned, page=1, current=1)
            self.game(rig, self.click(win, CENTRES[b]))
            label = f"{size} Tank {b + 4}, {owned} bought"
            if b < owned:
                self.assertEqual((rig.var("_shown"), rig.get(0x384)), (b, 0), label)
                self.assertIn(("switch", 0), rig.calls, label)
                self.assertEqual(rig.var("_locked_until"), 0, label)
            else:
                self.assertEqual((rig.var("_shown"), rig.get(0x384)), (-1, 1), label)
                self.assertNotIn(("switch", 0), rig.calls, label)
                self.assertGreater(rig.var("_locked_until"), 0, f"{label}: no refusal")
            self.no_other_screen(rig, label)

    # ------------------------------------------------------------ carrying a fish
    def drag(self, win: W.EmulatedDllTests, start: tuple[int, int], *path: tuple[int, int]) -> list:
        """Press on a fish at start, move with the button held through path, let go at its end:
        every event SDL queued after the press (the moves and the release)."""
        at = self.aim(win, start)
        win.sdl_message(W.WM_LBUTTONDOWN, *at)
        win.events.clear()
        for point in path:
            at = self.aim(win, point)
        win.sdl_message(WM_LBUTTONUP, *at)
        return list(win.events)

    def test_a_fish_carried_to_every_tank(self) -> None:
        """From Tank Two on the stock page: Tank One and the Sale Tank by their buttons; Tanks
        Four-Six by carrying the fish over an arrow (the page turns) to their buttons; over an arrow
        and back over it (the page turns back) to the Sale Tank; a drop on an arrow keeps the fish."""
        mover = X.fish(X.NOW, 4, 8, 25, 77, 66)
        away = (560, 150)
        cases = [((CENTRES[0],), 0), ((CENTRES[2],), 2)]
        cases += [((ARROWS[1], away, CENTRES[b]), 3 + b) for b in range(3)]
        cases += [((ARROWS[0], away, CENTRES[b]), 3 + b) for b in range(3)]
        cases += [((ARROWS[1], away, ARROWS[0], away, CENTRES[2]), 2)]
        cases += [((ARROWS[1],), None), ((ARROWS[0], away, ARROWS[1]), None)]
        for size in SIZES:
            for owned in (0, 3):
                with self.subTest(size=size, owned=owned):
                    win = self.window(size)
                    for path, goes in cases:
                        rig = self.rig(owned, page=0, current=1)
                        rig.put_tank(1, X.block_with({2: mover}))
                        X.MovingFish.hold(None, rig, 3, 1, 2)
                        rig.emu.write8(rig.impl, 1)                         # a fish is being dragged
                        before = [rig.tank(t) for t in range(4)] + [rig.extra(e) for e in range(3)]
                        self.game(rig, self.drag(win, (400, 300), *path))
                        label = f"{size} carried through {path}, {owned} bought"
                        after = [rig.tank(t) for t in range(4)] + [rig.extra(e) for e in range(3)]
                        if goes is None or (goes >= 3 and goes - 3 >= owned):
                            self.assertEqual(after, before, f"{label}: the fish stays where it was")
                            if goes is not None:
                                self.assertGreater(rig.var("_locked_until"), 0, f"{label}: no refusal")
                        else:
                            got = rig.extra(goes - 3) if goes >= 3 else rig.tank(goes)
                            self.assertEqual(got[:X.SLOT], mover, label)
                            self.assertEqual(struct.unpack_from("<I", rig.tank(1), 2 * X.SLOT)[0], 0, label)
                        self.assertEqual(rig.get(0x1E4E8), 0xFFFFFFFF, f"{label}: let go, nothing left on the cursor")
                        self.no_other_screen(rig, label)

    def test_the_old_cursor_spot_is_the_magic_fish_shelf(self) -> None:
        """Why the owner got the Trophy Case: with SDL's pointer unscaled, the game's cursor on
        the second and third tank buttons (Tank Five and Six on the extra page) of a 1920 x 1017
        window meant a click on the shelf (the raw client point scaled back to the picture)."""
        x, y, w, h = W.fit(1920, 1017)
        for cx, cy in CENTRES[1:]:
            click = (W.to_picture(cx, x, w, 800), W.to_picture(cy, y, h, 600))
            self.assertTrue(SHELF[0] <= click[0] <= SHELF[2] and SHELF[1] <= click[1] <= SHELF[3], click)


if __name__ == "__main__":
    unittest.main()
