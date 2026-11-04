"""Click the greenhouse to deselect ("Click to Deselect.dll", Plant Tycoon).

The game's own greenhouse press (the mouse slot 0x4273D0 -> 0x426040, its pot test 0x423970, its select
0x423630, the faucet's rectangle test 0x435FF0) runs in Unicorn on the patched executable
(tests/test_every_patch.py's World: the real startup loader loads the real DLL); only what those call
(draws, sounds, strings) is a recorded stand-in. Each click is made twice from the same starting state: with
the DLL's jump in place and with the stock bytes put back at its one site. Whatever the setting does not mean
to change must come out identical.
"""

from __future__ import annotations

import gc
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_every_patch as T  # noqa: E402

MANIFEST = json.loads((ROOT / "data" / "plant_manifest.json").read_text(encoding="utf-8"))
SETTING = "greenhouse_click_deselect"
DLL = "Click to Deselect.dll"
SELECTED, HELD, NONE = 0x63E58, 0x56C, 0x63
FRAME = 0x104
SITES = {0x42734C: bytes.fromhex("8B5668" "83BA6C05000000"),       # the press off the cells: mov edx, [esi+0x68]; cmp ...
         0x427295: bytes.fromhex("E896C3FFFF")}                      # the call of the select, 0x423630
PLANTS = (0, 1, 2, 3, 7, 14)             # the slots that hold a plant (the sprite byte +0x38 of their pot record)
FLOORS = ((255, 300), (500, 30), (765, 150), (500, 490))      # off the bench cells: left strip, wall, right strip, below
FLOOR = FLOORS[0]
SCENE_SPAN, STATE_SPAN = 0x120, 0x63E70


def pot_point(k: int) -> tuple[int, int]:
    """A point inside pot k's cell (5 columns of 93 px from x 270, 3 rows of 144 from y 43: 0x423970)."""
    return 316 + 93 * (k % 5), 110 + 144 * (k // 5)


@dataclass
class Result:
    selected: int
    held: int
    frame: int
    state: bytes
    scene: bytes
    calls: list

    def same_as(self, other: "Result") -> bool:
        return (self.state, self.scene, self.calls) == (other.state, other.scene, other.calls)

    def differing(self, other: "Result") -> tuple[list[int], list[int]]:
        return ([i for i, (a, b) in enumerate(zip(self.state, other.state)) if a != b],
                [i for i, (a, b) in enumerate(zip(self.scene, other.scene)) if a != b])


class Clicks(T.PlantGreenhouseScreen if T.E else object):
    """The greenhouse screen with its press path real."""
    ROOTS = (0x428810, 0x4257A0, 0x428E70, 0x4273D0, 0x426040, 0x423970, 0x423AA0, 0x423A10, 0x4165A0, 0x423630,
             0x4244C0, 0x424680, 0x435FF0, 0x428250)

    def __init__(self, w) -> None:
        super().__init__(w)
        for offset in (0x94, 0x9C):                  # the select's two parts (the news line, the marker)
            w.emu.write32(self.scene + offset, T.alloc_zero(w, 0x100))


class Game:
    """One built game (the setting plus others) with its greenhouse screen."""

    def __init__(self, settings: set[str]) -> None:
        self.build = T.build("plant", T.with_requirements(MANIFEST, settings))
        self.world = T.World(self.build)
        self.world.run_loader()
        self.emu = self.world.emu
        self.screen = Clicks(self.world)
        self.state, self.scene = self.screen.state, self.screen.scene
        for k in PLANTS:
            self.emu.write8(self.state + 0x2188 + k * 0x5600 + 0x38, 1)
        self.patched = {va: bytes(self.emu.uc.mem_read(va, len(stock))) for va, stock in SITES.items()}
        self.start = (bytes(self.emu.uc.mem_read(self.state, STATE_SPAN)),
                      bytes(self.emu.uc.mem_read(self.scene, SCENE_SPAN)))

    def log(self) -> str | None:
        return self.world.log(DLL)

    def press(self, setting: bool, selected: int, held: int, x: int, y: int) -> Result:
        """Press (x, y) from the starting state with `selected` and `held`, the DLL's jump in place or
        the stock bytes; the mouse slot is the one the game's table holds (any companion's wrapper first)."""
        emu, uc = self.emu, self.emu.uc
        uc.mem_write(self.state, self.start[0])
        uc.mem_write(self.scene, self.start[1])
        for va, stock in SITES.items():
            uc.mem_write(va, self.patched[va] if setting else stock)
            uc.ctl_remove_cache(va, va + len(stock))                  # the translated code of the old bytes
        emu.write32(self.state + SELECTED, selected)
        emu.write32(self.state + HELD, held)
        emu.write8(self.scene + FRAME, 1 if selected != NONE else 0)
        self.world.log_calls.clear()
        self.world.call(emu.read32(0x469224), 2, x, y, ecx=self.scene)
        return Result(emu.read32(self.state + SELECTED), emu.read32(self.state + HELD), uc.mem_read(self.scene + FRAME, 1)[0],
                      bytes(uc.mem_read(self.state, STATE_SPAN)), bytes(uc.mem_read(self.scene, SCENE_SPAN)),
                      [name for name, _ in self.world.log_calls])

    def both(self, selected: int, held: int, x: int, y: int) -> tuple[Result, Result]:
        return self.press(True, selected, held, x, y), self.press(False, selected, held, x, y)


def _needs():
    return unittest.skipUnless(T._ready("plant"), "needs Unicorn, Capstone and the vanilla Plant Tycoon")


class StockBytesTests(unittest.TestCase):
    """No Unicorn needed: the DLL's one site is the stock code of the vanilla executable."""

    def test_the_site_holds_the_stock_bytes(self) -> None:
        source = (ROOT / "native" / "ftfp_greenhouse_deselect" / "ftfp_greenhouse_deselect.c").read_text(encoding="utf-8")
        self.assertIn("#define PRESS_SITE_VA 0x0042734Cu", source)
        self.assertIn("0x8B, 0x56, 0x68,", source)
        self.assertIn("0x83, 0xBA, 0x6C, 0x05, 0x00, 0x00, 0x00", source)
        self.assertIn("#define SELECT_SITE_VA 0x00427295u", source)
        self.assertIn("{ 0xE8, 0x96, 0xC3, 0xFF, 0xFF }", source)
        exe = T.VANILLA_DIRS["plant"] / "Plant Tycoon.exe"
        if not exe.is_file():
            self.skipTest("needs the vanilla Plant Tycoon")
        data = exe.read_bytes()
        for va, stock in SITES.items():
            self.assertEqual(data[va - 0x400000:va - 0x400000 + len(stock)], stock, hex(va))
        self.assertEqual(data[0x27356:0x27358], bytes.fromhex("740F"))          # the je it jumps back to

    def test_the_setting_is_a_default_loader_tail(self) -> None:
        setting = next(s for s in MANIFEST["settings"] if s["id"] == SETTING)
        self.assertEqual(setting["name"], "Click the greenhouse to deselect")
        self.assertIs(setting["default"], True)
        self.assertEqual(setting["companion"]["loader_tail"], DLL)
        listed = setting["companion"]["files"][0]
        data = (ROOT / setting["companion"]["source"] / DLL).read_bytes()
        self.assertEqual(listed["size"], len(data))

    def test_the_release_includes_the_dll(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_release
        self.assertIn(f"assets/plant_tycoon_deselect/{DLL}", build_release.bundled_asset_files())


@_needs()
class GreenhouseDeselectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.game = Game({SETTING})

    @classmethod
    def tearDownClass(cls) -> None:
        del cls.game
        gc.collect()

    def test_it_installed(self) -> None:
        self.assertTrue(self.game.log().startswith("Click to Deselect: installed"), self.game.log())
        self.assertEqual(self.game.build.dlls, [DLL])

    def test_a_background_click_clears_the_selection(self) -> None:
        for point in FLOORS:
            on, off = self.game.both(7, 0, *point)
            self.assertEqual((on.selected, on.frame, on.held), (NONE, 0, 0), point)
            self.assertEqual((off.selected, off.frame), (7, 1), point)           # without it: unchanged, as before

    def test_an_empty_bench_cell_is_background_too(self) -> None:
        for k in (5, 9, 12):                                                      # slots that hold no plant
            on, off = self.game.both(7, 0, *pot_point(k))
            self.assertEqual((on.selected, on.frame, on.held), (NONE, 0, 0), k)
            self.assertEqual(off.selected, k, "the stock press selects the empty slot")

    def test_it_clears_the_stock_way(self) -> None:
        """The two fields the screen's own reset writes (0x4231F8, 0x423213) and nothing else, the same calls."""
        for point in (FLOOR, pot_point(5)):
            on, off = self.game.both(7, 0, *point)
            state, scene = on.differing(off)
            self.assertEqual(state, [SELECTED] if point == FLOOR else state[:1] and state, point)
            self.assertIn(FRAME, scene, point)
        on, off = self.game.both(7, 0, *FLOOR)
        self.assertEqual(on.calls, off.calls)
        state, scene = on.differing(off)
        self.assertEqual(state, [SELECTED], "only the selection differs in the state (99 = none)")
        self.assertEqual(scene, [FRAME], "only the selection frame differs in the scene")

    def test_nothing_selected_is_the_games(self) -> None:
        for point in FLOORS + (pot_point(5), pot_point(2)):
            on, off = self.game.both(NONE, 0, *point)
            self.assertTrue(on.same_as(off), point)

    def test_a_click_on_a_plant_still_selects_it(self) -> None:
        for k in (0, 3, 7, 14):
            on, off = self.game.both(2 if k == 7 else 7, 0, *pot_point(k))
            self.assertEqual((on.selected, on.frame), (k, 1), k)
            self.assertTrue(on.same_as(off), f"pot {k}: exactly as without the setting")

    def test_a_click_on_the_selected_plant_keeps_it_selected(self) -> None:
        on, off = self.game.both(7, 0, *pot_point(7))
        self.assertEqual((on.selected, on.frame), (7, 1))
        self.assertTrue(on.same_as(off))

    def test_a_click_while_holding_something_is_the_games(self) -> None:
        for held in (1, 2, 3, 4, 9, 14, 0x3E8 + 3):                      # tools, pollen, chemicals, a pot
            for point in FLOORS + (pot_point(5), (400, 500), (260, 120)):
                on, off = self.game.both(7, held, *point)
                self.assertTrue(on.same_as(off), f"held {held} at {point}")
                self.assertEqual(on.selected, off.selected)

    def test_clicks_that_are_not_the_background_are_unchanged(self) -> None:
        places = {
            "the left panel": (100, 300), "the panel's edge": (235, 250), "the tray": (33, 210),
            "the water and health meters": (30, 380), "the faucet": (780, 470), "the faucet's corner": (754, 430),
            "the bottom bar": (400, 540), "the bottom bar's edge": (600, 506), "the top-left corner": (5, 5),
            "a plant": pot_point(2), "a plant in the last slot": pot_point(14),
        }
        for what, point in places.items():
            for selected in (7, NONE):
                on, off = self.game.both(selected, 0, *point)
                self.assertTrue(on.same_as(off), f"{what} with {selected} selected")
                self.assertEqual(on.selected, off.selected, what)

    def test_the_panel_reads_the_cleared_selection_as_no_plant_selected(self) -> None:
        """After the click the game's own panel draw (0x428250) takes selection 99: it draws string 0x18D
        centred (and no plant's name and stats)."""
        on, _off = self.game.both(7, 0, *FLOOR)
        self.assertEqual(on.selected, NONE)
        world = self.game.world
        world.log_calls.clear()
        world.call(0x428250, on.selected, ecx=self.game.scene)
        self.assertEqual([name for name, _ in world.log_calls], ["string", "graphics", "centred text"])


@_needs()
class WithExtraGreenhousesTests(unittest.TestCase):
    """With Extra Greenhouses (and its arrows once one is bought) beside it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.game = Game({SETTING, "extra_greenhouses"})
        world = cls.game.world
        world.call(world.companions["Extra Greenhouses.dll"].exports["FtfpExtraGreenhousesBuy"], what="buy")

    @classmethod
    def tearDownClass(cls) -> None:
        del cls.game
        gc.collect()

    def test_both_installed_in_order(self) -> None:
        self.assertEqual(self.game.world.top_level[-2:], ["Extra Greenhouses.dll", DLL])
        self.assertTrue(self.game.log().startswith("Click to Deselect: installed"))

    def test_a_background_click_clears_the_selection(self) -> None:
        for point in FLOORS[1:]:                                           # the left strip is the arrow's
            on, off = self.game.both(7, 0, *point)
            self.assertEqual((on.selected, on.frame), (NONE, 0), point)
            self.assertEqual(off.selected, 7)

    def test_the_arrows_are_the_games_not_a_background(self) -> None:
        """An arrow press is Extra Greenhouses': it plays its click and switches greenhouse (which itself
        clears the selection, with or without this setting); this DLL adds nothing and takes nothing."""
        for point in ((770, 260), (245, 260)):                            # the right arrow, the left one
            on, off = self.game.both(7, 0, *point)
            self.assertEqual((on.selected, on.frame, on.held, on.calls), (off.selected, off.frame, off.held, off.calls), point)
            self.assertEqual(on.calls, ["game 0x44A580"], "only the arrow's click sound: no select, no stock press")

    def test_a_click_on_a_plant_and_a_held_tool_are_unchanged(self) -> None:
        on, off = self.game.both(7, 0, *pot_point(3))
        self.assertEqual(on.selected, 3)
        self.assertTrue(on.same_as(off))
        on, off = self.game.both(7, 3, *FLOOR)
        self.assertTrue(on.same_as(off))


if __name__ == "__main__":
    unittest.main()
