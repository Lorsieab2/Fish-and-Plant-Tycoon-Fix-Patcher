"""Fish Tycoon's screensaver: while it runs, a click or a key only ends it, with every companion DLL.

The stock tank screen's mouse (0x421F80, the screen's vtable slot 0x443A58) checks the screensaver
flag (state+0x1E4F9) first: set, it clears it, puts the display back and returns; only when it is
clear does it call the tank's own click handler 0x421B80 (from 0x421FFB). A key (0x41ED10, slot
0x443A5C) with the flag set calls the mouse slot with a click. So a DLL that hooks the tank's
clicks inside 0x421B80, or its call at 0x421FFB, is never reached during the screensaver, and one
that wraps the mouse slot itself must check the flag (Tank Counts does; its own test is
test_tank_greenhouse_counts' test_the_screensaver_shows_nothing_and_its_clicks_are_the_games).

These tests run the vanilla handlers in Unicorn with the flag set and trace every instruction:
none of the click sites any Fish DLL declares (Extra Tanks' arrows, toggle and page-2 buttons and
Extra Supply Slots' arrows and pages at 0x421FFB / 0x421D43, Multiple Ornaments' and DS Store
Items' pick and drag inside 0x421B80) is ever executed, and the screensaver ends. With the flag
clear the same click does reach 0x421FFB (the trace sees the DLLs' path). The DLLs' declared sites
are read from their sources (tests/test_every_patch.py's declared_sites), so a new hook on the
tank's click path that the stock flag check does not cover fails here.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import store_emulator as E
    from unicorn import UC_HOOK_CODE
except ImportError:          # Unicorn is not installed
    E = None

from test_every_patch import PROJECTS, declared_sites  # noqa: E402

FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None

MOUSE, KEYS, TANK_CLICK, TANK_CLICK_CALL = 0x421F80, 0x41ED10, 0x421B80, 0x421FFB
TANK_CLICK_END = 0x421F80            # 0x421B80's code runs up to the mouse handler
MOUSE_END = 0x422004
VTABLE, MOUSE_SLOT, KEY_SLOT = 0x443A54, 0x443A58, 0x443A5C
S_SCREENSAVER, S_STARTING = 0x1E4F9, 0x1E4FA
WINDOW_END_SITE = 0x421FCD           # Maximizable Window's own screensaver end (the fix itself)
ORNAMENT_PICK = (0x41EFB0, 0x41F100)  # the pick 0x421B80 calls from 0x421C93


def click_path_sites() -> dict[str, set[int]]:
    """{dll: the sites it declares on the tank screen's click and key path}."""
    out = {}
    for dll, project in PROJECTS["fish"].items():
        sites = {va for va in declared_sites(project)
                 if TANK_CLICK <= va < MOUSE_END or ORNAMENT_PICK[0] <= va < ORNAMENT_PICK[1]
                 or KEYS <= va < KEYS + 0x130 or va in (MOUSE_SLOT, KEY_SLOT)}
        if sites:
            out[dll] = sites
    return out


class DeclaredSitesTests(unittest.TestCase):
    def test_the_dlls_on_the_click_path_are_the_known_ones(self) -> None:
        self.assertEqual(click_path_sites(), {
            "Extra Tanks.dll": {0x421D43, 0x421FFB},
            "Extra Supply Slots.dll": {0x421D43, 0x421FFB},
            "Multiple Ornaments.dll": {0x41EFD9, 0x421BA0, 0x421D43},
            "DS Store Items.dll": {0x41F064},
            "Tank Counts.dll": {MOUSE_SLOT},
            "Maximizable Window.dll": {WINDOW_END_SITE},
            "No C Cheat.dll": {0x41ED75},      # the 'c' case's jump distance, after the screensaver test
        })

    def test_only_tank_counts_wraps_the_mouse_slot_and_nobody_the_keys(self) -> None:
        sites = click_path_sites()
        self.assertEqual([d for d, s in sites.items() if MOUSE_SLOT in s], ["Tank Counts.dll"])
        self.assertEqual([d for d, s in sites.items() if KEY_SLOT in s or any(KEYS <= v < KEYS + 0x130 for v in s)],
                         ["No C Cheat.dll"])     # one byte in the 'c' case; the screensaver test comes first
        source = (ROOT / "native" / "ftfp_tank_counts" / "ftfp_tank_counts.c").read_text(encoding="latin-1")
        self.assertIn("AT(state, S_SCREENSAVER, unsigned char) == 0", source)   # its click: only off


@unittest.skipUnless(E is not None and FISH_EXE is not None and FISH_EXE.is_file(),
                     "needs Unicorn and the vanilla Fish Tycoon.exe")
class StockHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        emu = self.emu = E.Emulator(FISH_EXE, None, {})
        self.state = emu.alloc(0x1E600)
        emu.uc.mem_write(self.state, bytes(0x1E600))
        video = emu.alloc(0x60)
        emu.uc.mem_write(video, bytes(0x60))
        emu.write8(video + 0x1E, 1)                 # windowed
        holder = emu.alloc(4)
        emu.write32(holder, video)
        emu.write32(0x45AFE8, holder)
        self.scene = emu.alloc(0x100)
        emu.uc.mem_write(self.scene, bytes(0x100))
        emu.write32(self.scene, VTABLE)
        emu.write32(self.scene + 0x08, emu.alloc(0x40))
        emu.write32(self.scene + 0x34, self.state)
        self.calls: list[str] = []
        emu.hook(0x41B070, lambda e: self.state)
        emu.hook(0x40AAC0, lambda e: self.calls.append("redraw") or 0, 4)
        emu.hook(0x421940, lambda e: self.calls.append("relayout") or 0)
        emu.hook(TANK_CLICK, lambda e: self.calls.append("tank click") or 0, 12)
        self.ran: set[int] = set()
        emu.uc.hook_add(UC_HOOK_CODE, lambda uc, address, size, data: self.ran.add(address))

    def flag(self, on: int) -> None:
        self.emu.write8(self.state + S_SCREENSAVER, on)

    def dll_sites_run(self) -> dict[str, list[str]]:
        return {dll: sorted(hex(v) for v in sites if v in self.ran and v != WINDOW_END_SITE)
                for dll, sites in click_path_sites().items() if any(v in self.ran for v in sites - {WINDOW_END_SITE})}

    def test_a_click_during_the_screensaver_only_ends_it(self) -> None:
        # button down (ends it), up and move (ignored); at the hidden tank buttons and arrows
        # (top right), the supply slots and their arrows (bottom), and the water
        for kind in (2, 3, 1):
            for x, y in ((20, 20), (513, 20), (490, 30), (700, 560), (400, 300)):
                with self.subTest(kind=kind, x=x, y=y):
                    self.one_click(kind, x, y)

    def one_click(self, kind: int, x: int, y: int) -> None:
        self.flag(1)
        self.calls.clear()
        self.ran.clear()
        self.emu.call(MOUSE, kind, x, y, ecx=self.scene)
        self.assertNotIn("tank click", self.calls)
        self.assertNotIn(TANK_CLICK_CALL, self.ran)
        self.assertEqual(self.dll_sites_run(), {})
        ended = kind == 2
        self.assertEqual(self.emu.uc.mem_read(self.state + S_SCREENSAVER, 1), b"\x00" if ended else b"\x01")
        self.assertEqual(WINDOW_END_SITE in self.ran, ended)

    def test_a_key_during_the_screensaver_only_ends_it(self) -> None:
        self.flag(1)
        self.assertEqual(self.emu.read32(MOUSE_SLOT), MOUSE)       # the key's click goes through this slot
        self.assertEqual(self.emu.call(KEYS, 0x61, 0x61, 0, ecx=self.scene) & 0xFF, 1)
        self.assertEqual(self.emu.uc.mem_read(self.state + S_SCREENSAVER, 1), b"\x00")
        self.assertNotIn("tank click", self.calls)
        self.assertEqual(self.dll_sites_run(), {})
        self.assertIn(WINDOW_END_SITE, self.ran)

    def test_while_the_interface_slides_off_clicks_are_the_tanks_as_stock(self) -> None:
        # 0x1E4FA alone (the slide after the button): the stock mouse does not check it.
        self.emu.write8(self.state + S_STARTING, 1)
        self.emu.call(MOUSE, 2, 513, 20, ecx=self.scene)
        self.assertEqual(self.calls, ["tank click"])
        self.assertIn(TANK_CLICK_CALL, self.ran)

    def test_without_the_screensaver_the_click_reaches_the_dlls_path(self) -> None:
        self.flag(0)
        self.emu.call(MOUSE, 2, 513, 20, ecx=self.scene)
        self.assertEqual(self.calls, ["tank click"])
        self.assertIn(TANK_CLICK_CALL, self.ran)                   # Extra Tanks' / Supply Slots' hook site
        self.assertNotIn(WINDOW_END_SITE, self.ran)


if __name__ == "__main__":
    unittest.main()
