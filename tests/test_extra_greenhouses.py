"""The "5 extra greenhouses" setting (native/ftfp_extra_greenhouses, docs/plant-tycoon-extra-greenhouses-design.md).

The emulated tests run the vanilla "Plant Tycoon.exe" and the DLL rebuilt from its committed source in
Unicorn (tests/store_emulator.py). Every plant is made by the game's own code (a seed planted by
0x42FC70, grown by the game's own update 0x41D810), and every effect is the game's own code; Python
only answers the clock, Random (one seeded sequence per run), memory, and the screen and sound calls.

"Identical" is checked byte for byte: the same plant, planted, grown and treated with the same random
numbers in Greenhouse 1 (the stock pots) and in each of Greenhouses 2-6, gives the same 0x5600-byte pot
record, the same game state outside the pots, and the same one-time messages.
"""

from __future__ import annotations

import hashlib
import json
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import ds_fish_loader  # noqa: E402
import plant_patcher  # noqa: E402

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

PLANT_EXE = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon" / "Plant Tycoon.exe"
DLL = ROOT / "assets" / "plant_tycoon_greenhouses" / "Extra Greenhouses.dll"
MANIFEST = ROOT / "data" / "plant_manifest.json"
SETTING = "extra_greenhouses"
FOLDER = "Plant Tycoon Fix Patcher DLLs"

RANDOM, CLOCK, SECONDS, MEMSET, MEMCPY = 0x004033B0, 0x00403430, 0x00402080, 0x00451280, 0x00450C10
NEW, DELETE, MESSAGE_ONCE = 0x0044E894, 0x0044E7B3, 0x0041D830
UPDATE, PLANT_SEED, GET_PLANT, POLLINATE, CHEMICAL_SWITCH = 0x0041D810, 0x0042FC70, 0x0042F6C0, 0x004240A0, 0x004266A6
MANAGER_GLOBAL, STATE_GLOBAL, SPRITES_GLOBAL, GRAPHICS_GLOBAL = 0x00493C80, 0x0049333C, 0x00493C34, 0x00493948
STATE_SIZE, POTS_AT, POT, POTS, EXTRA = 0x63E70, 0x2188, 0x5600, 15, 5
HELD, SELECTED, HELD_POT = 0x56C, 0x63E58, 0x3E8
FOR_SALE, PLANTED, FOLIAGE, FLOWER, AGE, HEALTH = 0x9D, 0x38, 0x4C, 0x50, 0x10, 0x24
HOME, NURSERY = 0, 100

SOURCE = ROOT / "native" / "ftfp_extra_greenhouses" / "ftfp_extra_greenhouses.c"


def constant(name: str) -> int:
    """A #define of the DLL's source (the arrows' and labels' places)."""
    import re
    return int(re.search(rf"#define {name} (\d+)", SOURCE.read_text(encoding="utf-8")).group(1))


# The middle of each greenhouse arrow, where a click or a drop lands.
LEFT_ARROW = (constant("LEFT_X") + 25, constant("ARROW_Y") + 25)
RIGHT_ARROW = (constant("RIGHT_X") + 25, constant("ARROW_Y") + 25)

HAVE = E is not None and PLANT_EXE.is_file() and E.toolchain_ready()
needs_game = unittest.skipUnless(HAVE, "needs Unicorn, the vanilla Plant Tycoon.exe and the pinned MSVC toolset")

# Two hours, a day away, an hour, three days away, ... : growth, flowering, seeds, thirst and death.
TICKS = [7200, 86400, 3600, 3 * 86400, 600, 7200, 14400, 86400, 2 * 86400, 3600]


class Game:
    """The vanilla game in Unicorn after its own new game, with the DLL's hooks written as FtfpStartup writes them."""

    built: tuple[Path, dict[str, int]] | None = None

    def __init__(self, seed: int = 11) -> None:
        dll, symbols = Game.built
        emu = self.emu = E.Emulator(PLANT_EXE, dll, symbols)
        emu.uc.mem_map(0, 0x1000)                         # fs:[0], the game's SEH chain
        self.now = 1_000_000
        self.rng = random.Random(seed)
        self.messages: list[int] = []
        self.told: list[str] = []
        emu.hook(RANDOM, lambda e: self.rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0)
        emu.hook(CLOCK, lambda e: self.now)
        emu.hook(SECONDS, lambda e: self.now)

        def memset(e):
            e.uc.mem_write(e.arg(0), bytes([e.arg(1) & 0xFF]) * e.arg(2))
            return e.arg(0)

        def memcpy(e):
            e.uc.mem_write(e.arg(0), bytes(e.uc.mem_read(e.arg(1), e.arg(2))))
            return e.arg(0)
        emu.hook(MEMSET, memset)
        emu.hook(MEMCPY, memcpy)
        emu.hook(NEW, lambda e: e.alloc(max(e.arg(0), 4)))
        emu.hook(DELETE, lambda e: 0)
        emu.hook(MESSAGE_ONCE, lambda e: self.messages.append(e.arg(0)) or 0, 8)
        # Screen, sound and tray calls (none of them reads or writes a pot).
        for address, pop, result in ((0x0041C1F0, 0x1C, 0), (0x0041B190, 8, 0), (0x0044A580, 4, 0),
                                     (0x0044A520, 8, 0), (0x0044A550, 0xC, 0), (0x00423630, 0xC, 0),
                                     (0x00416700, 4, 0), (0x004244C0, 0, 0), (0x00435FF0, 0x18, 0),
                                     (0x00401570, 0x14, 0), (0x00409AA0, 0x10, 0), (0x0040B650, 4, 0),
                                     (0x00401AA0, 0x18, 0), (0x0040B400, 4, 0), (0x004092B0, 0x14, 0),
                                     (0x00401C90, 8, 0), (0x0042AAA0, 0, 0)):
            emu.hook(address, lambda e, r=result: r, pop)
        emu.hook(0x0044CA70, lambda e: e.text("text"), 4)            # the string table

        def box(e):
            entry = e.read32(0x00493CC0 + 0x77 * 4)
            self.told.append(e.cstring(e.read32(entry + 0xC)).decode("latin-1"))
            return 0
        emu.hook(0x0042AB50, box, 0x14)
        entry = emu.alloc(0x10)
        emu.write32(entry, 0x77)
        emu.write32(entry + 8, emu.text("Your seed box is already full!"))
        emu.write32(0x00493CC0 + 0x77 * 4, entry)

        state = self.state = emu.alloc(STATE_SIZE)
        esp = E.STACK + E.STACK_SIZE - 0x1000
        emu.write32(esp, E.RETURN)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ECX, state)
        emu.uc.emu_start(0x41EF30, 0x41F17D, count=20_000_000)      # the game's own new game, to its pot setup
        emu.write32(state + 0x534, 10)                               # normal speed, as the state's reset sets it (0x41D235)
        emu.write32(STATE_GLOBAL, state)
        emu.write32(SPRITES_GLOBAL, emu.alloc(0x100))
        emu.write32(GRAPHICS_GLOBAL, emu.alloc(0x100))
        emu.write32(emu.sym("_owned"), EXTRA)                         # all five bought (OwnershipTests buys them)
        manager = self.manager = emu.alloc(0x810A4)
        emu.write32(manager, state)
        emu.write32(manager + 4, emu.read32(SPRITES_GLOBAL))
        emu.write32(MANAGER_GLOBAL, manager)
        # The DLL's hooks, as FtfpStartup writes them.
        emu.uc.mem_write(UPDATE, b"\xE9" + struct.pack("<i", emu.sym("_stub_update") - (UPDATE + 5)))
        for name, stock in (("gh_command", 0x427960), ("gh_mouse", 0x4273D0), ("gh_activate", 0x4231E0),
                            ("gh_tick", 0x428810), ("nu_activate", 0x4360D0)):
            emu.write32(emu.sym(f"_next_{name}"), stock)
        self.scene = emu.alloc(0x200)
        emu.write32(self.scene + 0x68, state)
        emu.write32(self.scene + 0x70, manager)
        for field in (0x60, 0x64, 0x74, 0x78, 0x8C, 0x9C):
            emu.write32(self.scene + field, emu.alloc(0x40))

    # ------------------------------------------------------------ the DLL
    def arrange(self, kind: int) -> None:
        self.emu.call(self.emu.sym("_arrange"), self.state, kind)

    def show(self, g: int, active: int = 1) -> None:
        """The greenhouse screen showing greenhouse g (0-5)."""
        """The screen `active` (1 greenhouse, 2 nursery, 3 snapshot, 0 any other) with greenhouse g (0-5)."""
        self.emu.write32(self.emu.sym("_shown"), g)
        self.emu.uc.mem_write(self.emu.sym("_scene_on"), bytes(1 if k == active else 0 for k in range(4)))
        self.emu.write32(self.emu.sym("_current"), active)
        self.emu.call(self.emu.sym("_ensure"))

    def pot(self, g: int, k: int) -> int:
        return self.emu.call(self.emu.sym("_FtfpExtraGreenhousesPot"), g, k)

    def pot_bytes(self, g: int, k: int) -> bytes:
        return bytes(self.emu.uc.mem_read(self.pot(g, k), POT))

    def state_outside_pots(self) -> bytes:
        data = bytes(self.emu.uc.mem_read(self.state, STATE_SIZE))
        return data[:POTS_AT] + data[POTS_AT + POTS * POT:]

    # ------------------------------------------------------------ the game
    def plant(self, g: int, k: int, foliage: int, flower: int) -> None:
        """The game's own planting (0x42FC70) of a seed in greenhouse g's pot k."""
        seed = self.emu.alloc(0x24)
        self.emu.write32(seed + 0x10, foliage)
        self.emu.write32(seed + 0x14, flower)
        self.arrange(g)
        self.emu.call(PLANT_SEED, seed, k // 5, k % 5, ecx=self.manager)
        self.arrange(HOME)

    def tick(self, seconds: int) -> None:
        self.now += seconds
        self.emu.call(UPDATE, ecx=self.state)

    def chemical(self, g: int, k: int, chemical: int) -> None:
        """The greenhouse's own chemical code (the switch at 0x4266A6) on greenhouse g's pot k."""
        emu = self.emu
        self.arrange(g)
        plant = emu.call(GET_PLANT, k // 5, k % 5, ecx=self.manager)
        emu.write32(self.state + HELD, 5)
        frame = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.mem_write(frame, bytes(0x40))
        emu.write32(frame + 0x14, plant)
        emu.write32(frame + 0x1C, E.RETURN)
        emu.write32(frame + 0x20, chemical)
        for register, value in ((X.UC_X86_REG_ESP, frame), (X.UC_X86_REG_ESI, self.scene),
                                (X.UC_X86_REG_EBX, k % 5), (X.UC_X86_REG_EBP, k // 5),
                                (X.UC_X86_REG_EDI, k * POT)):
            emu.uc.reg_write(register, value)
        emu.uc.reg_write(X.UC_X86_REG_FPCW, 0x027F)
        emu.uc.emu_start(CHEMICAL_SWITCH, E.RETURN, count=20_000_000)
        self.arrange(HOME)

    def objects_follow_their_records(self) -> bool:
        """Every plant object in the manager points at the state pot it stands for."""
        for k in range(POTS):
            obj = self.emu.read32(self.manager + 8 + 4 * k)
            if obj and self.emu.read32(obj + 8) != self.state + POTS_AT + k * POT:
                return False
        return True


def _build() -> None:
    if Game.built is None:
        Game.tmp = tempfile.TemporaryDirectory()
        Game.built = E.build_with_map("ftfp_extra_greenhouses", DLL, Path(Game.tmp.name))


def grow(g: int, seed: int, plants=((7, 13, 13),), ticks=TICKS) -> Game:
    game = Game(seed)
    for k, foliage, flower in plants:
        game.plant(g, k, foliage, flower)
    for dt in ticks:
        game.tick(dt)
    return game


@needs_game
class TickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _build()

    def trace(self, g: int, seed: int, foliage: int, flower: int):
        game = Game(seed)
        game.plant(g, 7, foliage, flower)
        out = []
        for dt in TICKS:
            game.tick(dt)
            out.append(game.pot_bytes(g, 7))
        return out, game.state_outside_pots(), game.messages, game

    def test_every_extra_greenhouse_pot_ticks_exactly_like_a_stock_pot(self) -> None:
        for seed, (foliage, flower) in ((3, (13, 13)), (8, (22, 23)), (21, (4, 11))):
            stock, stock_state, stock_messages, game = self.trace(0, seed, foliage, flower)
            ages = [struct.unpack_from("<f", record, AGE)[0] for record in stock]
            self.assertGreater(ages[0], 0)                               # the plant really grew
            self.assertTrue(any(struct.unpack_from("<i", r, HEALTH)[0] <= 0 for r in stock))   # and died of thirst
            for g in range(1, EXTRA + 1):
                extra, extra_state, extra_messages, other = self.trace(g, seed, foliage, flower)
                self.assertEqual(extra, stock, f"greenhouse {g + 1}, seed {seed}")
                self.assertEqual(extra_state, stock_state, f"greenhouse {g + 1}: the game state")
                self.assertEqual(extra_messages, stock_messages)
                self.assertTrue(other.objects_follow_their_records())
                self.assertEqual(other.pot_bytes(0, 7), game.pot_bytes(1, 7))   # the stock pot it left alone

    def test_game_wide_effects_reach_every_greenhouse(self) -> None:
        """Permanent, game-wide effects live in the game state, outside the pots: the six magic plants
        and the Golden Berries found (state + 0x2180..0x2186, read by the update at 0x42E171 and the
        planting at 0x42FD77) and every tool upgrade owned (state + 0x6E8 + k * 0x20 + 4). A plant in
        any greenhouse grows exactly as in Greenhouse 1 with all of them, and differently without."""
        def run(g: int, effects: bool) -> list[bytes]:
            game = Game(31)
            if effects:
                for flag in range(0x2180, 0x2187):
                    game.emu.write8(game.state + flag, 1)
                for k in range(15):
                    game.emu.write8(game.state + 0x6E8 + k * 0x20 + 4, 1)
            game.plant(g, 7, 13, 13)
            out = []
            for dt in TICKS[:4]:
                game.tick(dt)
                out.append(game.pot_bytes(g, 7))
            return out
        stock = run(0, True)
        self.assertNotEqual(stock, run(0, False))                           # the effects really act
        for g in range(1, EXTRA + 1):
            self.assertEqual(run(g, True), stock, f"greenhouse {g + 1}")

    def test_switching_never_touches_game_wide_state(self) -> None:
        """Greenhouses and nurseries change only which pots are in the state: everything else (magic
        plants, upgrades, ornaments, research, money, discoveries) is the same on every screen."""
        game = NurseryLimitTests.full_game()
        emu = game.emu
        emu.write32(emu.sym("_nurseries_on"), 1)
        emu.write32(emu.sym("_nurseries"), 2)
        for k in range(POTS):
            NurseryLimitTests().toggle(game, 1, k)
            NurseryLimitTests().toggle(game, 3, k)
        game.show(0, active=0)
        before = game.state_outside_pots()
        for g in range(EXTRA + 1):
            game.show(g)
            self.assertEqual(game.state_outside_pots(), before, f"greenhouse {g + 1}")
        for page in range(3):
            emu.write32(emu.sym("_nursery_shown"), page)
            game.show(0, active=2)
            self.assertEqual(game.state_outside_pots(), before, f"nursery {page + 1}")

    def test_a_full_greenhouse_ticks_like_the_stock_one(self) -> None:
        plants = [(k, 1 + (k * 5) % 23, 1 + (k * 7) % 23) for k in range(POTS)]
        stock = grow(0, 5, plants)
        for g in (2, 5):
            extra = grow(g, 5, plants)
            self.assertEqual([extra.pot_bytes(g, k) for k in range(POTS)],
                             [stock.pot_bytes(0, k) for k in range(POTS)])
            self.assertEqual(extra.state_outside_pots(), stock.state_outside_pots())

    def test_the_time_warp_moves_extra_pots_like_the_stock_pots(self) -> None:
        """Store Upgrades and Items.dll's Time Warp: every live stock pot's clock back by dt (stamps
        ahead of now set to now), then the update; FtfpExtraGreenhousesWarp does the same for the
        extra pots."""
        def warped(g: int) -> bytes:
            game = grow(g, 9, ticks=(7200, 600))                  # alive: the warp moves live pots only
            dt = 30 * 3600
            if g == 0:
                record = game.state + POTS_AT + 7 * POT
                self.assertGreater(game.emu.read32(record + HEALTH, signed=True), 0)
                stamp = min(game.emu.read32(record + 4), game.now)
                game.emu.write32(record + 4, stamp - dt)
            else:
                game.emu.call(game.emu.sym("_FtfpExtraGreenhousesWarp"), dt, game.now)
            game.emu.call(UPDATE, ecx=game.state)
            return game.pot_bytes(g, 7)
        stock = warped(0)
        for g in range(1, EXTRA + 1):
            self.assertEqual(warped(g), stock)


@needs_game
class EffectTests(unittest.TestCase):
    """One test per effect family: the game's own code on an extra greenhouse's pot gives the stock result."""

    PLANTS = ((2, 13, 13), (7, 11, 10), (11, 22, 23))

    @classmethod
    def setUpClass(cls) -> None:
        _build()

    def compare(self, action, label: str) -> None:
        def run(g: int):
            game = grow(g, 17, self.PLANTS, TICKS[:4])
            action(game, g)
            for dt in (3600, 86400):
                game.tick(dt)
            return [game.pot_bytes(g, k) for k in range(POTS)], game.state_outside_pots(), game
        stock, stock_state, _ = run(0)
        for g in range(1, EXTRA + 1):
            extra, extra_state, game = run(g)
            self.assertEqual(extra, stock, f"{label}: greenhouse {g + 1}")
            self.assertEqual(extra_state, stock_state, f"{label}: greenhouse {g + 1}, the game state")
            self.assertTrue(game.objects_follow_their_records())

    def test_every_chemical(self) -> None:
        # The switch's nine cases, chemicals 27-35 (plant foods, pesticides, the two bombs that reach
        # every pot of the greenhouse, Insta-Grow, Mutation Liquid, ...), on pot 7.
        for chemical in range(27, 36):
            self.compare(lambda game, g, c=chemical: game.chemical(g, 7, c), f"chemical {chemical}")

    def test_pollination(self) -> None:
        def pollinate(game, g):
            game.arrange(g)
            target, donor = (game.state + POTS_AT + k * POT for k in (7, 2))
            game.emu.call(POLLINATE, target, donor, ecx=game.scene)
            game.arrange(HOME)
        self.compare(pollinate, "pollination")

    def test_pollen_carried_to_another_greenhouse_keeps_its_donor(self) -> None:
        """Pollen from greenhouse 1's pot 2 dropped on another greenhouse's pot 7 gives that plant the
        seeds stock pollination within one greenhouse gives it."""
        stock = grow(0, 23, ((2, 13, 13), (7, 11, 10)), TICKS[:4])
        stock.arrange(HOME)
        stock.emu.call(POLLINATE, stock.state + POTS_AT + 7 * POT, stock.state + POTS_AT + 2 * POT, ecx=stock.scene)
        for g in range(1, EXTRA + 1):
            game = Game(23)
            game.plant(0, 2, 13, 13)
            game.plant(g, 7, 11, 10)
            for dt in TICKS[:4]:
                game.tick(dt)
            emu = game.emu
            game.show(g)
            emu.write32(emu.sym("_pollen_g"), 0)
            emu.write32(emu.sym("_pollen_k"), 2)
            wrong_donor = game.state + POTS_AT + 2 * POT                  # greenhouse g's own pot 2 (empty)
            emu.call(emu.sym("@pollinate@16"), game.state + POTS_AT + 7 * POT, wrong_donor,
                     ecx=game.scene)
            game.show(0, active=0)
            self.assertEqual(game.pot_bytes(g, 7), stock.pot_bytes(0, 7))
            self.assertEqual(game.pot_bytes(0, 2), stock.pot_bytes(0, 2))
            self.assertEqual(emu.read32(emu.sym("_pollen_g"), signed=True), -1)

    def test_moving_pots_within_a_greenhouse(self) -> None:
        def move(game, g):
            game.arrange(g)
            game.emu.call(0x0042F940, 0, 2, 2, 4, ecx=game.manager)       # pot 2 <-> pot 14
            game.arrange(HOME)
        self.compare(move, "moving a pot")

    def test_emptying_a_pot(self) -> None:
        def empty(game, g):
            game.arrange(g)
            game.emu.call(0x0042F410, 1, 2, ecx=game.manager)            # pot 7
            game.arrange(HOME)
        self.compare(empty, "emptying a pot")


@needs_game
class MoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _build()

    def drop_on_arrow(self, game: Game, right: bool, k: int) -> None:
        emu = game.emu
        emu.write32(game.state + HELD, HELD_POT + k)
        emu.call(emu.sym("@gh_mouse@20"), 3, *(RIGHT_ARROW if right else LEFT_ARROW), ecx=game.scene)

    def test_a_pot_dragged_onto_an_arrow_moves_to_the_same_place_in_that_greenhouse(self) -> None:
        game = grow(0, 4, ((4, 13, 13),), (7200,))
        plant = game.pot_bytes(0, 4)
        empty_target = game.pot_bytes(1, 4)
        game.show(0)
        self.drop_on_arrow(game, True, 4)
        emu = game.emu
        self.assertEqual(emu.read32(emu.sym("_shown")), 1)
        self.assertEqual(emu.read32(game.state + HELD), 0)
        self.assertEqual(bytes(emu.uc.mem_read(game.state + POTS_AT + 4 * POT, POT)), plant)   # on screen now
        self.assertTrue(game.objects_follow_their_records())
        game.show(0, active=0)
        self.assertEqual(game.pot_bytes(1, 4), plant)
        self.assertEqual(game.pot_bytes(0, 4), empty_target)
        # and back: greenhouse 2's left arrow leads to greenhouse 1, whose pot 4 is empty again
        game.show(1)
        self.drop_on_arrow(game, False, 4)
        game.show(0, active=0)
        self.assertEqual(game.pot_bytes(0, 4), plant)
        # greenhouse 1's left arrow leads round to greenhouse 6
        game.show(0)
        self.drop_on_arrow(game, False, 4)
        game.show(0, active=0)
        self.assertEqual(game.pot_bytes(5, 4), plant)
        # it keeps growing there exactly as before
        game.tick(3600)
        self.assertNotEqual(game.pot_bytes(5, 4), plant)

    def test_a_taken_place_moves_it_to_the_first_empty_pot(self) -> None:
        game = grow(0, 4, ((4, 13, 13),), (7200,))
        plant = game.pot_bytes(0, 4)
        for k in (0, 1, 4):
            game.emu.write32(game.pot(1, k) + FOLIAGE, 9)
        game.show(0)
        self.drop_on_arrow(game, True, 4)
        game.show(0, active=0)
        self.assertEqual(game.pot_bytes(1, 2), plant)
        self.assertEqual(game.told, [])

    def test_a_full_greenhouse_takes_no_plant(self) -> None:
        game = grow(0, 4, ((4, 13, 13),), TICKS[:1])
        for k in range(POTS):
            game.emu.write32(game.pot(1, k) + FOLIAGE, 9)
        before = [game.pot_bytes(g, k) for g in range(2) for k in range(POTS)]
        game.show(0)
        self.drop_on_arrow(game, True, 4)
        game.show(0, active=0)
        self.assertEqual([game.pot_bytes(g, k) for g in range(2) for k in range(POTS)], before)
        self.assertEqual(len(game.told), 1)
        self.assertIn("Greenhouse 2 is full!", game.told[0])
        self.assertEqual(game.emu.read32(game.emu.sym("_shown")), 0)

    def test_the_arrows_page_through_all_six(self) -> None:
        game = Game(1)
        emu = game.emu
        seen = []
        for _ in range(7):
            emu.call(emu.sym("@gh_command@16"), 8, 41, ecx=game.scene)
            seen.append(emu.read32(emu.sym("_shown")))
        self.assertEqual(seen, [1, 2, 3, 4, 5, 0, 1])
        emu.call(emu.sym("@gh_command@16"), 8, 40, ecx=game.scene)
        emu.call(emu.sym("@gh_command@16"), 8, 40, ecx=game.scene)
        self.assertEqual(emu.read32(emu.sym("_shown")), 5)


SEED_SITES = ((0x425C1B, "_stub_seed_plant"), (0x42819B, "_stub_seed_box"), (0x424711, "_stub_seed_trash"),
              (0x424508, "_stub_seed_return"))


@needs_game
class CarryTests(unittest.TestCase):
    """What the cursor holds across the arrows. The arrows do not change screen: the stock game drops a
    held item only when a screen opens (0x423206 in the greenhouse's 0x4231E0, 0x4363C3 in the
    nursery's 0x4360D0), so everything stays held, and what belongs to a pot keeps its pot."""

    SEED = bytes(range(0x40, 0x40 + 0x24))

    @classmethod
    def setUpClass(cls) -> None:
        _build()

    def seeds_taken(self, game: Game, g: int, k: int) -> int:
        """Seeds taken from greenhouse g's pot k, as 0x426228 leaves them: held 0x14, the pot selected,
        one seed moved from +0x90 (left) to +0x94 (taken) by 0x42625D / 0x42626F."""
        emu = game.emu
        pot = game.pot(g, k)
        emu.uc.mem_write(pot + 0x54, self.SEED)
        emu.write32(pot + 0x90, 2)
        emu.write32(pot + 0x94, 1)
        for va, stub in SEED_SITES:
            emu.uc.mem_write(va, b"\xE9" + struct.pack("<i", emu.sym(stub) - (va + 5)))
        game.show(g)
        emu.write32(game.state + HELD, 0x14)
        emu.write32(game.state + SELECTED, k)
        emu.call(emu.sym("@gh_command@16"), 8, 41, ecx=game.scene)          # the right arrow
        self.assertEqual(emu.read32(game.state + HELD), 0x14)               # still held
        self.assertEqual(emu.read32(emu.sym("_seed_g"), signed=True), g)
        return pot

    def test_seeds_carried_to_another_greenhouse_go_into_seed_storage(self) -> None:
        game = Game(5)
        emu = game.emu
        self.seeds_taken(game, 0, 6)
        game.show(1)                                                        # on screen: greenhouse 2
        before = bytes(emu.uc.mem_read(game.state + POTS_AT + 6 * POT, POT))

        def mouse(e):                                        # the pointer on the seed box button
            e.uc.mem_write(e.arg(0), struct.pack("<ii", 400, 560))
            return e.arg(0)
        emu.hook(0x00407D20, mouse, 4)
        emu.call(emu.sym("@gh_command@16"), 9, 1, ecx=game.scene)          # the stock drop on the seed box
        box = game.state + 0x52CCC
        self.assertEqual(bytes(emu.uc.mem_read(box, 0x24)), self.SEED)      # greenhouse 1's seed, in box 1
        self.assertEqual(emu.read32(game.state + HELD), 0)
        self.assertEqual(bytes(emu.uc.mem_read(game.state + POTS_AT + 6 * POT, POT)), before)

    def test_carried_seeds_are_read_from_their_own_pot(self) -> None:
        game = Game(5)
        emu = game.emu
        self.seeds_taken(game, 2, 4)
        game.show(3)                                                        # on screen: greenhouse 4
        source = game.pot(2, 4)
        # planting (0x425C1B) and the seed box (0x42819B) copy the record their esi points at
        for va, back, regs in ((0x425C1B, 0x425C22, (X.UC_X86_REG_EDX, X.UC_X86_REG_EAX)),
                               (0x42819B, 0x4281A2, (X.UC_X86_REG_EDX, X.UC_X86_REG_ECX))):
            emu.uc.reg_write(regs[0], 4 * POT)
            emu.uc.reg_write(regs[1], game.state)
            emu.run_until(va, back)
            self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_ESI), source + 0x54, hex(va))
        # the trash pays the seeds' own value (+0x74)
        emu.uc.reg_write(X.UC_X86_REG_ECX, 4 * POT)
        emu.uc.reg_write(X.UC_X86_REG_EDI, game.state)
        emu.run_until(0x424711, 0x424718)
        self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_EBX), struct.unpack_from("<i", self.SEED, 0x20)[0])
        # put back (0x424508 in 0x4244C0): to its own pot, which gets its seed back
        emu.uc.reg_write(X.UC_X86_REG_ECX, game.state)
        emu.run_until(0x424508, 0x4245DD)
        self.assertEqual((emu.read32(source + 0x90), emu.read32(source + 0x94)), (3, 0))
        self.assertEqual(emu.read32(emu.sym("_seed_g"), signed=True), -1)

    def test_seeds_back_in_their_own_greenhouse_take_the_stock_path(self) -> None:
        game = Game(5)
        emu = game.emu
        self.seeds_taken(game, 0, 4)
        emu.call(emu.sym("@gh_command@16"), 8, 40, ecx=game.scene)          # back to greenhouse 1
        emu.uc.reg_write(X.UC_X86_REG_EDX, 4 * POT)
        emu.uc.reg_write(X.UC_X86_REG_EAX, game.state)
        emu.run_until(0x425C1B, 0x425C22)
        self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_ESI), game.state + POTS_AT + 4 * POT + 0x54)
        emu.uc.reg_write(X.UC_X86_REG_ECX, game.state)
        emu.run_until(0x424508, 0x42450E)                                   # the stock put-back, by the selected pot
        self.assertEqual(emu.uc.reg_read(X.UC_X86_REG_EBP), 4)

    def test_tools_chemicals_and_tray_seeds_stay_held(self) -> None:
        for held in (1, 2, 3, 4, 5, 8, 10, 13, 19):                         # tools, chemical tray, seed tray
            game = Game(1)
            emu = game.emu
            game.show(0)
            emu.write32(game.state + HELD, held)
            emu.write32(game.state + SELECTED, 3)
            emu.call(emu.sym("@gh_command@16"), 8, 41, ecx=game.scene)
            self.assertEqual(emu.read32(game.state + HELD), held)
            self.assertEqual(emu.read32(game.state + SELECTED), 0x63)       # no pot selected in the new greenhouse

    def test_pollen_stays_held_with_its_donor(self) -> None:
        game = Game(1)
        emu = game.emu
        game.show(3)
        emu.write32(game.state + HELD, 9)
        emu.write32(game.state + SELECTED, 7)
        emu.call(emu.sym("@gh_command@16"), 8, 40, ecx=game.scene)
        self.assertEqual(emu.read32(game.state + HELD), 9)
        self.assertEqual((emu.read32(emu.sym("_pollen_g")), emu.read32(emu.sym("_pollen_k"))), (3, 7))


@needs_game
class NurseryLimitTests(unittest.TestCase):
    """The stock nursery has 15 spots, one per pot: at most 15 plants are for sale, over all six greenhouses."""

    @classmethod
    def setUpClass(cls) -> None:
        _build()

    @staticmethod
    def full_game() -> Game:
        game = Game(2)
        for g in range(EXTRA + 1):
            for k in range(POTS):
                at = game.pot(g, k)
                game.emu.write8(at + PLANTED, 1)
                game.emu.write32(at + FOLIAGE, 5)
                game.emu.write32(at + FLOWER, 5)
                game.emu.uc.mem_write(at + AGE, struct.pack("<f", 30.0))
                game.emu.write32(at + HEALTH, 100)
        return game

    def toggle(self, game: Game, g: int, k: int) -> None:
        emu = game.emu
        game.show(g)
        emu.write32(game.state + SELECTED, k)
        emu.call(emu.sym("@gh_command@16"), 8, 6, ecx=game.scene)

    def for_sale(self, game: Game) -> int:
        return game.emu.call(game.emu.sym("_FtfpExtraGreenhousesForSale"))

    def test_the_sixteenth_plant_is_refused_in_every_greenhouse(self) -> None:
        game = self.full_game()
        spots = [(g, k) for k in range(3) for g in range(EXTRA + 1)][:15]     # 2-3 plants in each greenhouse
        for n, (g, k) in enumerate(spots, 1):
            self.toggle(game, g, k)
            self.assertEqual(self.for_sale(game), n)
        self.assertEqual(game.told, [])
        for g in range(EXTRA + 1):
            self.toggle(game, g, 10)
            self.assertEqual(self.for_sale(game), 15)
        self.assertEqual(len(game.told), EXTRA + 1)
        self.assertIn("Only 15 plants can be for sale at once", game.told[0])
        self.toggle(game, 0, 0)                                             # taking one off is never refused
        self.assertEqual(self.for_sale(game), 14)
        self.toggle(game, 4, 10)
        self.assertEqual(self.for_sale(game), 15)

    def test_put_all_up_for_sale_stops_at_the_stock_limit(self) -> None:
        game = self.full_game()
        for k in range(5):
            self.toggle(game, 1, k)
        game.show(3)
        game.emu.call(game.emu.sym("@gh_command@16"), 8, 9, ecx=game.scene)   # the stock "all" button
        self.assertEqual(self.for_sale(game), 15)
        self.assertEqual(len(game.told), 1)
        game.show(0, active=0)
        self.assertEqual(sum(game.emu.uc.mem_read(game.pot(3, k) + FOR_SALE, 1)[0] for k in range(POTS)), 10)

    def sell(self, g: int, k: int):
        """Tag greenhouse g's pot k for sale (button 6), open the nursery, let the game's own sale code
        (0x435C70, a visitor buying the plant in its spot) sell it, and close the nursery."""
        game = self.full_game()
        emu = game.emu
        self.toggle(game, g, k)
        nursery = emu.alloc(0xB00)
        emu.write32(nursery + 0xA3C, game.state)
        emu.write32(nursery + 0xA44, game.manager)
        emu.write32(nursery + 0xA4C, emu.alloc(0x40))
        emu.hook(0x0043ACD0, lambda e: 0)                  # no visitors left to react
        emu.hook(0x00449F00, lambda e: emu.alloc(0x10))    # the sound bank
        game.show(g, active=2)
        spots = [j for j in range(POTS) if emu.uc.mem_read(game.state + POTS_AT + j * POT + FOR_SALE, 1)[0]]
        self.assertEqual(len(spots), 1)
        cash, sold = emu.read32(game.state + 0x217C), emu.read32(game.state + 0x38)
        emu.call(0x00435C70, 0, 0, spots[0] // 5, spots[0] % 5, ecx=nursery)
        price = emu.read32(game.state + ((5 + 0x37) * 26 + 5) * 4)
        after = (emu.read32(game.state + 0x217C) - cash, emu.read32(game.state + 0x38) - sold)
        emu.call(emu.sym("@nu_activate@12"), 0, ecx=nursery)                # leaving the nursery
        left = game.pot_bytes(g, k)
        return after, price, left, game

    def test_a_plant_tagged_in_an_extra_greenhouse_sells_like_a_stock_plant(self) -> None:
        stock, price, stock_left, _ = self.sell(0, 6)
        self.assertEqual(stock, (price, 1))
        self.assertEqual(struct.unpack_from("<i", stock_left, FOLIAGE)[0], 0)      # the sold plant left its pot
        for g in range(1, EXTRA + 1):
            extra, _, left, game = self.sell(g, 6)
            self.assertEqual(extra, stock, f"greenhouse {g + 1}")
            self.assertEqual(struct.unpack_from("<i", left, FOLIAGE)[0], 0)
            self.assertEqual(game.emu.read32(game.emu.sym("_arranged")), HOME)
            self.assertNotEqual(struct.unpack_from("<i", game.pot_bytes(0, 0), FOLIAGE)[0], 0)  # spot 0's own plant is home

    def test_the_nursery_shows_the_plants_for_sale_of_every_greenhouse_in_its_15_spots(self) -> None:
        game = self.full_game()
        spots = [(g, k) for g in range(EXTRA + 1) for k in (3, 9, 14)][:15]
        for g, k in spots:
            self.toggle(game, g, k)
        records = {(g, k): game.pot_bytes(g, k) for g in range(EXTRA + 1) for k in range(POTS)}
        game.show(0, active=2)                                              # the nursery
        in_state = [bytes(game.emu.uc.mem_read(game.state + POTS_AT + j * POT, POT)) for j in range(POTS)]
        self.assertEqual(sum(r[FOR_SALE] for r in in_state), 15)            # all of them, in the stock spots
        self.assertEqual(sorted(in_state), sorted(records[s] for s in spots))
        self.assertTrue(game.objects_follow_their_records())
        game.show(0, active=0)                                              # leaving: every plant back home
        self.assertEqual({(g, k): game.pot_bytes(g, k) for g in range(EXTRA + 1) for k in range(POTS)}, records)


@needs_game
class SidecarTests(unittest.TestCase):
    """Extra Greenhouses <slot>.dat: written beside the save through a temporary file, read back on load."""

    @classmethod
    def setUpClass(cls) -> None:
        _build()

    def files(self, game: Game) -> dict[str, bytearray]:
        emu, disk, handles = game.emu, {}, {}

        def path(at):
            return emu.wstring(at)

        def create(e):
            name, access, disposition = path(e.arg(0)), e.arg(1), e.arg(4)
            if disposition == 3 and name not in disk:            # OPEN_EXISTING
                return 0xFFFFFFFF
            if access & 0x40000000:
                disk[name] = bytearray()
            handle = 0x100 + len(handles) * 4
            handles[handle] = [name, 0]
            return handle

        def write(e):
            name = handles[e.arg(0)][0]
            disk[name].extend(bytes(emu.uc.mem_read(e.arg(1), e.arg(2))))
            emu.write32(e.arg(3), e.arg(2))
            return 1

        def read(e):
            entry = handles[e.arg(0)]
            data = disk[entry[0]][entry[1]: entry[1] + e.arg(2)]
            emu.uc.mem_write(e.arg(1), bytes(data))
            entry[1] += len(data)
            emu.write32(e.arg(3), len(data))
            return 1

        def size(e):
            emu.uc.mem_write(e.arg(1), struct.pack("<q", len(disk[handles[e.arg(0)][0]])))
            return 1

        def move(e):
            disk[path(e.arg(1))] = disk.pop(path(e.arg(0)))
            return 1

        def module(e):
            text = "C:\\Game\\Plant Tycoon.exe\0".encode("utf-16-le")
            emu.uc.mem_write(e.arg(1), text)
            return len(text) // 2 - 1

        special = emu.thunk()

        def documents(e):
            emu.uc.mem_write(e.arg(1), "C:\\Docs\0".encode("utf-16-le"))
            return 1
        emu.hook(special, documents, 16)
        for name, handler, pop in (("CreateFileW", create, 28), ("WriteFile", write, 20), ("ReadFile", read, 20),
                                   ("GetFileSizeEx", size, 8), ("MoveFileExW", move, 12),
                                   ("DeleteFileW", lambda e: disk.pop(path(e.arg(0)), None) is not None, 4),
                                   ("CloseHandle", lambda e: 1, 4), ("FlushFileBuffers", lambda e: 1, 4),
                                   ("CreateDirectoryW", lambda e: 1, 8), ("LoadLibraryW", lambda e: 0x7000, 4),
                                   ("GetProcAddress", lambda e: special, 8), ("GetModuleFileNameW", module, 12)):
            emu.hook_import(name, handler, pop)
        return disk

    NAME = "C:\\Docs\\LDW\\Plant Tycoon\\Plant Tycoon Fix Patcher Data\\Extra Greenhouses 4.dat"

    def test_round_trip_and_the_save_holds_the_stock_layout(self) -> None:
        game = Game(6)
        disk = self.files(game)
        for g in range(EXTRA + 1):
            game.plant(g, g + 3, 1 + g, 2 + g)
        game.tick(86400)
        before = {(g, k): game.pot_bytes(g, k) for g in range(EXTRA + 1) for k in range(POTS)}
        stock_pots = bytes(game.emu.uc.mem_read(game.state + POTS_AT, POTS * POT))
        game.show(4)                                         # greenhouse 5 on screen while the game saves
        written = bytearray()

        def save_write(e):                                   # the game's file writer 0x403690(data, size, slot)
            written.extend(bytes(e.uc.mem_read(e.arg(0), e.arg(1))))
            return 1
        game.emu.hook(0x00403690, save_write, 0xC)
        game.emu.call(game.emu.sym("_stub_save"), 4, ecx=game.state, edx=4)
        self.assertEqual(bytes(written[POTS_AT - 8: POTS_AT - 8 + POTS * POT]), stock_pots)
        self.assertEqual(game.emu.read32(game.emu.sym("_arranged")), 4)          # back on screen
        self.assertEqual(list(disk), [self.NAME])
        data = bytes(disk[self.NAME])
        self.assertEqual(struct.unpack_from("<7I", data), (0x47585450, 1, EXTRA, POTS, POT, EXTRA, 0))
        self.assertEqual(len(data), 28 + EXTRA * POTS * POT)
        # a load of slot 4 brings every greenhouse back
        game.emu.call(game.emu.sym("_on_loaded"), game.state, 4)
        for g in range(1, EXTRA + 1):
            for k in range(POTS):
                self.assertEqual(game.pot_bytes(g, k), before[(g, k)])
        self.assertEqual(game.emu.read32(game.emu.sym("_shown")), 0)

    def test_an_unreadable_file_is_set_aside_never_overwritten(self) -> None:
        game = Game(6)
        disk = self.files(game)
        disk[self.NAME] = bytearray(b"PTXG not a sidecar")
        game.plant(3, 0, 5, 5)
        game.emu.call(game.emu.sym("_on_loaded"), game.state, 4)
        self.assertEqual(bytes(disk[self.NAME + ".unreadable"]), b"PTXG not a sidecar")
        self.assertNotIn(self.NAME, disk)
        self.assertEqual(game.emu.read32(game.pot(3, 0) + FOLIAGE), 0)          # empty greenhouses

    def test_no_file_means_empty_greenhouses(self) -> None:
        game = Game(6)
        self.files(game)
        game.plant(2, 0, 5, 5)
        game.emu.call(game.emu.sym("_on_loaded"), game.state, 7)
        self.assertTrue(all(game.emu.read32(game.pot(g, k) + FOLIAGE) == 0
                            for g in range(1, EXTRA + 1) for k in range(POTS)))
        self.assertEqual(game.emu.read32(game.emu.sym("_owned")), 0)               # none bought

    def test_ownership_round_trip_and_a_new_game_resets_it(self) -> None:
        game = Game(6)
        emu = game.emu
        disk = self.files(game)
        emu.write32(emu.sym("_owned"), 2)
        game.plant(2, 5, 4, 4)
        emu.hook(0x00403690, lambda e: 1, 0xC)
        emu.call(emu.sym("_stub_save"), 4, ecx=game.state, edx=4)
        self.assertEqual(struct.unpack_from("<I", disk[self.NAME], 20)[0], 2)
        emu.write32(emu.sym("_owned"), 0)
        emu.call(emu.sym("_on_loaded"), game.state, 4)
        self.assertEqual(emu.read32(emu.sym("_owned")), 2)
        # the game's new game (0x41D3D0 calls 0x42F630 through the DLL): nothing owned, all empty
        emu.call(emu.sym("@new_game_clear@8"), ecx=game.manager)
        self.assertEqual(emu.read32(emu.sym("_owned")), 0)
        self.assertEqual(emu.read32(game.pot(2, 5) + FOLIAGE), 0)

    def test_a_greenhouse_with_plants_is_never_locked_away(self) -> None:
        game = Game(6)
        emu = game.emu
        disk = self.files(game)
        game.plant(4, 1, 4, 4)                                # greenhouse 5
        emu.write32(emu.sym("_owned"), 1)                     # a file that says only one was bought
        emu.hook(0x00403690, lambda e: 1, 0xC)
        emu.call(emu.sym("_stub_save"), 4, ecx=game.state, edx=4)
        emu.call(emu.sym("_on_loaded"), game.state, 4)
        self.assertEqual(emu.read32(emu.sym("_owned")), 4)
        self.assertTrue(disk)


@needs_game
class OwnershipTests(unittest.TestCase):
    """Greenhouses 2-6 are bought in order on the store's Upgrades screen; until then they cannot be reached."""

    @classmethod
    def setUpClass(cls) -> None:
        _build()

    def test_buying_unlocks_them_in_order(self) -> None:
        game = Game(1)
        emu = game.emu
        emu.write32(emu.sym("_owned"), 0)
        got = [emu.call(emu.sym("_FtfpExtraGreenhousesBuy")) for _ in range(7)]
        self.assertEqual(got, [1, 2, 3, 4, 5, 5, 5])
        self.assertEqual(emu.call(emu.sym("_FtfpExtraGreenhousesOwned")), 5)

    def test_every_screen_is_named(self) -> None:
        """The owner's name label: "Greenhouse 1" on the stock screen, " of m" once more are owned."""
        game = Game(1)
        emu = game.emu
        for name, n, of, expected in (("Greenhouse", 0, 1, "Greenhouse 1"), ("Greenhouse", 2, 4, "Greenhouse 3 of 4"),
                                      ("Nursery", 0, 1, "Nursery 1"), ("Nursery", 5, 6, "Nursery 6 of 6")):
            at = emu.call(emu.sym("_screen_label"), emu.text(name), n, of)
            self.assertEqual(emu.cstring(at).decode("latin-1"), expected)

    def test_the_arrows_reach_only_bought_greenhouses(self) -> None:
        for owned, expected in ((0, [0, 0, 0]), (1, [1, 0, 1]), (2, [1, 2, 0])):
            game = Game(1)
            emu = game.emu
            emu.write32(emu.sym("_owned"), owned)
            seen = []
            for _ in range(3):
                emu.call(emu.sym("@gh_command@16"), 8, 41, ecx=game.scene)
                seen.append(emu.read32(emu.sym("_shown")))
            self.assertEqual(seen, expected, owned)

    def test_a_plant_cannot_be_dragged_into_a_locked_greenhouse(self) -> None:
        game = grow(0, 4, ((4, 13, 13),), (7200,))
        emu = game.emu
        plant = game.pot_bytes(0, 4)
        emu.write32(emu.sym("_owned"), 0)
        emu.hook(0x004273D0, lambda e: 0, 0xC)               # the stock mouse: the plant goes back to its pot
        game.show(0)
        emu.write32(game.state + HELD, HELD_POT + 4)
        emu.call(emu.sym("@gh_mouse@20"), 3, *LEFT_ARROW, ecx=game.scene)  # the left arrow's place
        game.show(0, active=0)
        self.assertEqual(game.pot_bytes(0, 4), plant)
        self.assertTrue(all(game.emu.read32(game.pot(g, k) + FOLIAGE) == 0
                            for g in range(1, EXTRA + 1) for k in range(POTS)))
        # with two bought, greenhouse 1's left arrow leads round to greenhouse 3, not 6
        emu.write32(emu.sym("_owned"), 2)
        game.show(0)
        emu.write32(game.state + HELD, HELD_POT + 4)
        emu.call(emu.sym("@gh_mouse@20"), 3, *LEFT_ARROW, ecx=game.scene)
        game.show(0, active=0)
        self.assertEqual(game.pot_bytes(2, 4), plant)


UPGRADES_DLL = ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll"


@needs_game
class StoreItemTests(unittest.TestCase):
    """The Extra Greenhouse item on the Upgrades screen (Store Upgrades and Items.dll): $10,000 each, in order,
    $0 with Free upgrades, through the same Yes / No as Add Money."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", UPGRADES_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def store(self, cash: int, free: bool, answer_yes: bool = True):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.hook_printf()
        emu.owned = 0

        def message(e):
            e.calls.append(("MessageBoxW", e.wstring(e.arg(1))))
            return 6 if answer_yes else 7
        emu.hook_import("MessageBoxW", message, 16)
        for name, pop in (("GetActiveWindow", 0), ("GetForegroundWindow", 0), ("GetModuleHandleW", 4),
                          ("GetProcAddress", 8)):
            emu.hook_import(name, emu.record(name), pop)
        emu.hook(0x0044A580, emu.record("sound"), 4)
        emu.hook(0x00409AA0, lambda e: (e.calls.append(("tip", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 0x10)
        owned, buy = emu.thunk(), emu.thunk()
        emu.hook(owned, lambda e: e.owned, 0)

        def bought(e):
            e.owned = min(e.owned + 1, EXTRA)
            return e.owned
        emu.hook(buy, bought, 0)
        emu.write32(emu.sym("_extra_owned"), owned)
        emu.write32(emu.sym("_extra_buy"), buy)
        emu.write8(emu.sym("_free_upgrades"), int(free))
        state, scene = emu.alloc(0x60000), emu.alloc(0x400)
        emu.write32(scene + 0x1BC, state)
        emu.write32(state + 0x217C, cash)
        emu.write32(emu.sym("_upgrades_view"), 1)
        emu.state, emu.scene = state, scene
        return emu

    def click(self, emu) -> None:
        emu.call(emu.sym("_on_click"), emu.scene, 430, 80)

    def test_each_costs_10000_in_order(self) -> None:
        emu = self.store(25000, False)
        self.click(emu)
        self.assertEqual((emu.owned, emu.read32(emu.state + 0x217C)), (1, 15000))
        self.assertIn("Buy Greenhouse 2 for $10000?", [c[1] for c in emu.calls if c[0] == "MessageBoxW"][-1])
        self.assertEqual(emu.cstring(emu.sym("_extra_tip_text")).decode("latin-1"),
                         "Extra Greenhouse 2 of 5\nPrice: $ 10000")
        self.click(emu)
        self.assertEqual((emu.owned, emu.read32(emu.state + 0x217C)), (2, 5000))
        self.click(emu)                                                       # $5000 left: refused
        self.assertEqual((emu.owned, emu.read32(emu.state + 0x217C)), (2, 5000))
        self.assertIn("can't afford", [c[1] for c in emu.calls if c[0] == "MessageBoxW"][-1])

    def test_free_upgrades_make_them_free_and_the_sixth_is_sold_out(self) -> None:
        emu = self.store(0, True)
        for n in range(1, EXTRA + 1):
            self.click(emu)
            self.assertEqual(emu.owned, n)
        self.assertEqual(emu.read32(emu.state + 0x217C), 0)
        self.click(emu)
        self.assertEqual(emu.owned, EXTRA)
        self.assertIn("already have all five", [c[1] for c in emu.calls if c[0] == "MessageBoxW"][-1])
        self.assertEqual(emu.cstring(emu.sym("_extra_tip_text")).decode("latin-1"), "Extra Greenhouse\nSold out")

    def test_the_extra_nursery_item_is_sold_the_same_way(self) -> None:
        emu = self.store(30000, False)
        owned, buy = emu.read32(emu.sym("_extra_owned")), emu.read32(emu.sym("_extra_buy"))
        emu.write32(emu.sym("_extra_owned") + 4, owned)                      # the nursery item, on the Nursery shelf
        emu.write32(emu.sym("_extra_buy") + 4, buy)
        emu.write32(emu.sym("_extra_owned"), 0)                              # the greenhouse setting off
        emu.call(emu.sym("_on_click"), emu.scene, 470, 320)
        self.assertEqual((emu.owned, emu.read32(emu.state + 0x217C)), (1, 20000))
        self.assertIn("Buy Nursery 2 for $10000?", [c[1] for c in emu.calls if c[0] == "MessageBoxW"][-1])
        self.assertEqual(emu.cstring(emu.sym("_extra_tip_text") + 64).decode("latin-1"),
                         "Extra Nursery 2 of 5\nPrice: $ 10000")
        emu.call(emu.sym("_on_click"), emu.scene, 430, 80)                   # no greenhouse item to click
        self.assertEqual(emu.owned, 1)

    def test_answering_no_buys_nothing(self) -> None:
        emu = self.store(50000, False, answer_yes=False)
        self.click(emu)
        self.assertEqual((emu.owned, emu.read32(emu.state + 0x217C)), (0, 50000))

    def test_the_greenhouse_icon_is_an_opaque_shelf_item_inside_its_click_rect(self) -> None:
        """The live bug (v1.0.17): the item was the game's 157 x 207 garden picture greenhouse1.png (sprite
        0xC2) with a 0.29 that the game's draw does not apply, so a big, see-through greenhouse covered the
        seed boxes and three shelves. Now the DLL's own draw puts a small, opaque greenhouse (frame 30 of
        the mod's chemicals sheet, at scale 1) on the shelf line, inside its click rectangle."""
        import numpy as np
        from PIL import Image
        emu = self.store(0, False)
        draws = []
        emu.hook(0x004208F0, lambda e: (draws.append(("sprite",) + tuple(e.arg(i) for i in range(7))), 0)[1], 0x1C)
        emu.hook(0x004207F0, lambda e: (draws.append(("shadow",) + tuple(e.arg(i) for i in range(5))), 0)[1], 0x14)
        emu.call(emu.sym("_on_draw"), emu.scene)
        as_float = lambda bits: struct.unpack("<f", struct.pack("<I", bits))[0]
        # The extra items are drawn each as its shadow then its picture; only the greenhouse is on.
        # Automatic Sprinklers and the Auto-Healer (frames 32 and 34 of the same sheet) come after them.
        at = [i for i, d in enumerate(draws) if d[0] == "sprite" and d[1] == 0xB3 and d[2] == 30]
        self.assertEqual(len(at), 1)
        (_s, *shadow), (_p, sheet, frame, x, y, scale, alpha, _flag) = draws[at[0] - 1:at[0] + 1]
        self.assertEqual((_s, _p), ("shadow", "sprite"))
        self.assertEqual((sheet, frame, x, y, as_float(scale), alpha), (0xB3, 30, 404, 50, 1.0, 100))
        self.assertEqual([d[2] for d in draws[at[0] + 1:] if d[0] == "sprite" and d[1] == 0xB3], [32, 34])

        art = ROOT / "assets" / "plant_tycoon_upgrades" / "Images" / "Chemicals_Grid_upgrades.png"
        chems = np.asarray(Image.open(art).convert("RGBA"))
        self.assertEqual(chems.shape[0], 18 * 70)                     # chem_rows = 18 in the DLL
        cell = chems[(frame // 2) * 70:(frame // 2 + 1) * 70, (frame % 2) * 70:(frame % 2 + 1) * 70, 3]
        ys, xs = np.nonzero(cell)
        left, top, right, bottom = x + xs.min(), y + ys.min(), x + xs.max(), y + ys.max()   # inclusive, on screen
        width, height = right - left + 1, bottom - top + 1
        # The size of the shelf's items: at most a 57 x 61 shelf place, at least as tall as a seed box.
        images = PLANT_EXE.parent / "Images"
        tools = np.asarray(Image.open(images / "Tools_Grid.png").convert("RGBA"))[:, :, 3]
        box_ys, box_xs = np.nonzero(tools[0:80, 320:400])            # the seed box on this shelf (frame 4)
        self.assertLessEqual((width, height), (57, 61))
        self.assertGreaterEqual(height, box_ys.max() - box_ys.min() + 1)
        self.assertGreaterEqual(width, 30)
        # On the shelf line, as the seed box drawn at (461, 50) beside it, and clear of that box's art.
        self.assertLessEqual(abs(int(bottom) - (50 + int(box_ys.max()))), 1)
        self.assertLess(right, 461 + box_xs.min())
        # Inside its click and tooltip rectangle {404, 52, 461, 113}.
        source = (ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c").read_text(encoding="utf-8")
        self.assertIn('"FtfpExtraGreenhousesBuy", SHEET_CHEMICALS, GREENHOUSE_FRAME, 404, 50, 1.0f,\n'
                      "      408, 80, 403, 72, { 404, 52, 461, 113 } }", source)
        self.assertTrue(404 <= left and right < 461 and 52 <= top and bottom < 113, (left, top, right, bottom))
        # Fully opaque: every pixel of the picture, nothing see-through.
        self.assertTrue((cell[cell > 0] == 255).all())
        # The shadow under its middle, within a few pixels.
        peep = np.asarray(Image.open(images / "peep_shadow1.png").convert("RGBA"))[:, :, 3]
        p_ys, p_xs = np.nonzero(peep)
        self.assertEqual(shadow[0], 0xB0)
        centre = shadow[1] + (p_xs.min() + p_xs.max()) / 2
        self.assertLessEqual(abs(centre - (left + right) / 2), 3)
        # A click on the picture is the item's.
        emu.call(emu.sym("_on_click"), emu.scene, int((left + right) // 2), int((top + bottom) // 2))
        self.assertIn("can't afford", [c[1] for c in emu.calls if c[0] == "MessageBoxW"][-1])


@needs_game
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _build()

    def install(self, corrupt: int | None = None):
        game = Game(1)
        emu = game.emu
        emu.hook_import("VirtualProtect", lambda e: (e.write32(e.arg(3), 0x20), 1)[1], 16)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.uc.mem_write(UPDATE, bytes.fromhex("568BF1E8185CFEFF"))            # undo Game's own wiring
        if corrupt is not None:
            emu.write8(corrupt, emu.uc.mem_read(corrupt, 1)[0] ^ 0xFF)
        before = bytes(emu.uc.mem_read(0x401000, 0x70000))
        result = emu.call(emu.sym("_install_all"))
        return emu, before, bytes(emu.uc.mem_read(0x401000, 0x70000)), result

    def test_all_sites_are_written(self) -> None:
        emu, before, after, result = self.install()
        self.assertEqual(result & 0xFF, 1)
        for va, target, opcode in ((0x41D810, "_stub_update", 0xE9), (0x41D156, "_stub_save", 0xE9),
                                   (0x41EEFE, "_stub_load", 0xE9), (0x41D3DC, "@new_game_clear@8", 0xE8),
                                   (0x415F5E, "@delete_slot@12", 0xE8), (0x425F54, "@pollinate@16", 0xE8),
                                   *((va, stub, 0xE9) for va, stub in SEED_SITES),
                                   (0x437A1C, "@sales_roll@12", 0xE8), (0x435D21, "@sale_visitors@8", 0xE8)):
            code = bytes(emu.uc.mem_read(va, 5))
            self.assertEqual(code[0], opcode)
            self.assertEqual(va + 5 + struct.unpack("<i", code[1:])[0], emu.sym(target))
        self.assertEqual(emu.read32(0x46922C), emu.sym("@gh_command@16"))
        self.assertEqual(emu.read32(emu.sym("_next_gh_command")), 0x427960)
        self.assertEqual(emu.read32(0x469754), emu.sym("@nu_activate@12"))

    def test_one_changed_site_means_nothing_is_written(self) -> None:
        for corrupt in (0x41D3DC, 0x425F55, 0x41EF05):
            emu, before, after, result = self.install(corrupt)
            self.assertEqual(result & 0xFF, 0, hex(corrupt))
            self.assertEqual(before, after, hex(corrupt))


@needs_game
class ExtraNurseryTests(unittest.TestCase):
    """5 extra nurseries: each is the stock nursery screen with its own 15 spots; each one bought raises the
    stock limit of 15 plants for sale by 15."""

    @classmethod
    def setUpClass(cls) -> None:
        _build()

    @staticmethod
    def game(nurseries: int) -> Game:
        game = NurseryLimitTests.full_game()
        game.emu.write32(game.emu.sym("_nurseries_on"), 1)
        game.emu.write32(game.emu.sym("_nurseries"), nurseries)
        return game

    @staticmethod
    def in_nursery(game: Game, page: int) -> list[bytes]:
        game.emu.write32(game.emu.sym("_nursery_shown"), page)
        game.show(0, active=2)
        return [bytes(game.emu.uc.mem_read(game.state + POTS_AT + j * POT, POT)) for j in range(POTS)]

    def test_each_nursery_raises_the_limit_by_15(self) -> None:
        limits = NurseryLimitTests()
        for nurseries in (0, 1, 3):
            game = self.game(nurseries)
            limit = 15 * (nurseries + 1)
            spots = [(g, k) for k in range(POTS) for g in range(EXTRA + 1)]
            for g, k in spots[:limit]:
                limits.toggle(game, g, k)
            self.assertEqual(limits.for_sale(game), limit)
            self.assertEqual(game.told, [])
            limits.toggle(game, *spots[limit])
            self.assertEqual(limits.for_sale(game), limit)
            self.assertIn(f"Only {limit} plants can be for sale at once", game.told[0])

    def test_every_plant_for_sale_has_a_spot_in_one_nursery(self) -> None:
        game = self.game(1)
        limits = NurseryLimitTests()
        tagged = [(0, k) for k in range(5)] + [(2, k) for k in range(POTS)]          # 20 plants for sale
        for g, k in tagged:
            limits.toggle(game, g, k)
        records = {(g, k): game.pot_bytes(g, k) for g in range(EXTRA + 1) for k in range(POTS)}
        first, second = self.in_nursery(game, 0), self.in_nursery(game, 1)
        shown = [r for r in first if r[FOR_SALE]] + [r for r in second if r[FOR_SALE]]
        self.assertEqual((sum(r[FOR_SALE] for r in first), sum(r[FOR_SALE] for r in second)), (15, 5))
        self.assertEqual(sorted(shown), sorted(records[t] for t in tagged))       # each one exactly once
        self.assertEqual(first[:5], [records[(0, k)] for k in range(5)])          # Greenhouse 1's at their own spots
        self.assertTrue(game.objects_follow_their_records())
        game.show(0, active=0)
        self.assertEqual({(g, k): game.pot_bytes(g, k) for g in range(EXTRA + 1) for k in range(POTS)}, records)

    def test_the_arrows_page_through_the_bought_nurseries_and_keep_the_customers(self) -> None:
        """A switch changes only the plants on the stands: the nursery is neither closed nor opened again,
        and the whole nursery scene and its visitor list (places, states, timers, the visitor limit, the
        browsing count) are byte for byte as they were."""
        for nurseries, expected in ((0, [0, 0, 0]), (2, [1, 2, 0])):
            game = self.game(nurseries)
            emu = game.emu
            opened = []
            thunk = emu.thunk()
            emu.hook(thunk, lambda e: opened.append(e.arg(0)) or 0, 4)
            emu.write32(emu.sym("_next_nu_activate"), thunk)
            emu.hook(0x00449F00, lambda e: e.alloc(0x10))
            nursery, visitors = emu.alloc(0xB00), emu.alloc(0x170000)
            noise = random.Random(nurseries).randbytes(0xB00)
            emu.uc.mem_write(nursery, noise)
            emu.write32(nursery + 0xA3C, game.state)
            emu.write32(nursery + 0xA4C, visitors)
            emu.uc.mem_write(visitors, random.Random(5).randbytes(0x170000))
            scene_before = bytes(emu.uc.mem_read(nursery, 0xB00))
            visitors_before = bytes(emu.uc.mem_read(visitors, 0x170000))
            seen = []
            for _ in range(3):
                emu.call(emu.sym("@nu_command@16"), 8, 41, ecx=nursery)
                seen.append(emu.read32(emu.sym("_nursery_shown")))
                self.assertEqual(bytes(emu.uc.mem_read(nursery, 0xB00)), scene_before)
                self.assertEqual(bytes(emu.uc.mem_read(visitors, 0x170000)), visitors_before)
            self.assertEqual(seen, expected)
            self.assertEqual(opened, [])                                         # never closed or reopened
            if nurseries:
                self.assertEqual(emu.read32(emu.sym("_arranged")), 100)          # Nursery 1's plants again

    def test_a_switch_with_a_sold_or_held_plant_is_safe(self) -> None:
        """A plant sold in Nursery 1 stays sold on its stand when you come back (paid once), and a plant
        held to rearrange the nursery is put back before the stands change."""
        game = self.game(1)
        emu = game.emu
        limits = NurseryLimitTests()
        for k in range(POTS):
            limits.toggle(game, 1, k)
        limits.toggle(game, 3, 2)                                               # Nursery 2
        emu.hook(0x00449F00, lambda e: e.alloc(0x10))
        nursery = emu.alloc(0xB00)
        game.show(0, active=2)
        sold = game.state + POTS_AT + 4 * POT                                   # a sale on stand 4: 0x435C70's marks
        emu.write8(sold + 0x9E, 1)
        emu.write8(sold + FOR_SALE, 0)
        record = bytes(emu.uc.mem_read(sold, POT))
        cash = emu.read32(game.state + 0x217C)
        emu.write32(game.state + HELD, HELD_POT + 7)                            # a plant held in the nursery
        emu.call(emu.sym("@nu_command@16"), 8, 41, ecx=nursery)
        self.assertEqual(emu.read32(game.state + HELD), 0)
        stands = [bytes(emu.uc.mem_read(game.state + POTS_AT + j * POT, POT)) for j in range(POTS)]
        self.assertEqual(sum(r[FOR_SALE] for r in stands), 1)                   # Nursery 2's one plant
        self.assertNotIn(record, stands)                                        # the sold one is not shown here
        emu.call(emu.sym("@nu_command@16"), 8, 40, ecx=nursery)
        self.assertEqual(bytes(emu.uc.mem_read(sold, POT)), record)             # back on its stand, still sold
        self.assertEqual(emu.read32(game.state + 0x217C), cash)                 # nothing paid by switching

    def test_closing_the_nursery_empties_every_nurserys_sold_pots(self) -> None:
        game = self.game(1)
        emu = game.emu
        limits = NurseryLimitTests()
        for k in range(POTS):
            limits.toggle(game, 1, k)
        limits.toggle(game, 3, 2)
        for g, k in ((1, 4), (3, 2)):                                           # one sold in each nursery
            at = game.pot(g, k)
            emu.write8(at + 0x9E, 1)
            emu.write8(at + FOR_SALE, 0)
        nursery = emu.alloc(0xB00)
        emu.write32(nursery + 0xA3C, game.state)
        emu.write32(nursery + 0xA44, game.manager)
        game.show(0, active=2)
        emu.call(emu.sym("@nu_activate@12"), 0, ecx=nursery)                    # the stock close, then the others
        for g, k in ((1, 4), (3, 2)):
            self.assertEqual(emu.read32(game.pot(g, k) + FOLIAGE), 0, (g, k))
        self.assertEqual(emu.read32(game.pot(1, 5) + FOLIAGE), 5)               # unsold plants stay

    def test_a_plant_in_the_second_nursery_sells_like_a_stock_one(self) -> None:
        game = self.game(1)
        emu = game.emu
        limits = NurseryLimitTests()
        for k in range(POTS):
            limits.toggle(game, 1, k)
        limits.toggle(game, 4, 9)                                              # the 16th: Nursery 2
        nursery = emu.alloc(0xB00)
        emu.write32(nursery + 0xA3C, game.state)
        emu.write32(nursery + 0xA44, game.manager)
        emu.write32(nursery + 0xA4C, emu.alloc(0x40))
        emu.hook(0x0043ACD0, lambda e: 0)
        emu.hook(0x00449F00, lambda e: emu.alloc(0x10))
        spots = [j for j, r in enumerate(self.in_nursery(game, 1)) if r[FOR_SALE]]
        self.assertEqual(len(spots), 1)
        cash = emu.read32(game.state + 0x217C)
        emu.call(0x00435C70, 0, 0, spots[0] // 5, spots[0] % 5, ecx=nursery)
        self.assertEqual(emu.read32(game.state + 0x217C) - cash, emu.read32(game.state + ((5 + 0x37) * 26 + 5) * 4))
        emu.call(emu.sym("@nu_activate@12"), 0, ecx=nursery)
        self.assertEqual(game.emu.read32(game.pot(4, 9) + FOLIAGE), 0)          # sold: it left its pot
        self.assertEqual(sum(game.emu.uc.mem_read(game.pot(1, k) + FOR_SALE, 1)[0] for k in range(POTS)), 15)

    def test_every_nursery_is_the_stock_screen_plus_its_name(self) -> None:
        """Nursery 2's frame is the stock nursery draw (the scene's own slot, once, on the same scene, with
        Nursery 2's plants in the 15 pots) and then only the name: the same as Nursery 1's."""
        frames = {}
        for page in (0, 1):
            game = self.game(1)
            emu = game.emu
            drawn, texts = [], []
            thunk = emu.thunk()
            emu.hook(thunk, lambda e: drawn.append(e.uc.reg_read(X.UC_X86_REG_ECX)) or 0, 0)
            emu.write32(emu.sym("_next_nu_draw"), thunk)
            emu.hook(0x004092B0, lambda e: texts.append(e.cstring(e.arg(0)).decode("latin-1")) or 0, 0x14)
            emu.write32(emu.sym("_nursery_shown"), page)
            scene = emu.alloc(0xB00)
            emu.call(emu.sym("@nu_draw@8"), ecx=scene)
            frames[page] = (drawn, texts)
            self.assertEqual(drawn, [scene])                               # the stock draw, once
            self.assertEqual(emu.read32(emu.sym("_arranged")), 100 + page)  # its own plants in the pots
        self.assertEqual(frames[0][1], ["Nursery 1 of 2"])
        self.assertEqual(frames[1][1], ["Nursery 2 of 2"])                 # the only difference

    def test_every_bought_nursery_gets_the_stock_roll_and_none_bought_is_stock(self) -> None:
        for nurseries, rolls in ((0, 1), (1, 2), (3, 4)):
            game = self.game(nurseries)
            emu = game.emu
            calls = []
            emu.hook(0x00436BE0, lambda e: calls.append(e.arg(0)) or 0, 4)
            game.show(0, active=2)
            emu.call(emu.sym("@sales_roll@12"), 7, ecx=emu.alloc(0xB00))
            self.assertEqual(calls, [7] * rolls, nurseries)                  # the same visitors browsing, each

    def test_a_plant_in_a_nursery_not_on_screen_sells(self) -> None:
        """Nursery 1 on screen holds 15 plants priced at 3 x V (never sell); Nursery 2's one plant sells
        through the game's own roll and sale. No visitor carries it (they are Nursery 1's), it is paid,
        counted, marked sold in its own greenhouse pot, and leaves that pot like any sold plant."""
        game = Game(2)
        emu = game.emu
        game.plant(4, 9, 7, 7)                                              # a real plant, grown by the game
        game.tick(7200)
        game.tick(7200)
        emu.write32(emu.sym("_nurseries_on"), 1)
        emu.write32(emu.sym("_nurseries"), 1)
        for k in range(POTS):            # Nursery 1's 15 spots: Greenhouse 2's plants, just sold (they keep
            at = game.pot(1, k)          # their spots until the nursery closes, and are never rolled again)
            emu.write8(at + PLANTED, 1)
            emu.write32(at + FOLIAGE, 5)
            emu.write32(at + FLOWER, 5)
            emu.write8(at + 0x9E, 1)
        limits = NurseryLimitTests()
        limits.toggle(game, 4, 9)                                           # so this one is in Nursery 2
        nursery = emu.alloc(0xB00)
        emu.write32(nursery + 0xA3C, game.state)
        emu.write32(nursery + 0xA44, game.manager)
        emu.write32(nursery + 0xA4C, emu.alloc(0x40))
        emu.hook(0x0043ACD0, lambda e: 6)                                   # visitors in the nursery
        emu.uc.mem_write(0x435D21, b"\xE8" + struct.pack("<i", emu.sym("@sale_visitors@8") - (0x435D21 + 5)))
        handed = []
        emu.hook(0x00440940, lambda e: handed.append(1) or 0, 4)
        emu.hook(0x00449F00, lambda e: emu.alloc(0x10))
        emu.hook(RANDOM, lambda e: 0)
        game.show(0, active=2)
        game.show(0, active=0)
        before = {(g, k): game.pot_bytes(g, k) for g in range(EXTRA + 1) for k in range(POTS)}
        game.show(0, active=2)
        ring = bytes(emu.uc.mem_read(nursery + 0x10, 0x48))
        cash, sold = emu.read32(game.state + 0x217C), emu.read32(game.state + 0x38)
        price = emu.read32(game.state + ((7 + 0x37) * 26 + 7) * 4)
        emu.call(emu.sym("@sales_roll@12"), 6, ecx=nursery)
        self.assertEqual(emu.read32(game.state + 0x217C) - cash, price)
        self.assertEqual(emu.read32(game.state + 0x38) - sold, 1)
        self.assertEqual(handed, [])                                        # no visitor of Nursery 1 took it
        self.assertEqual(bytes(emu.uc.mem_read(nursery + 0x10, 0x48)), ring)
        self.assertEqual(emu.read32(emu.sym("_arranged")), 100)             # Nursery 1 back on screen
        self.assertTrue(game.objects_follow_their_records())
        game.show(0, active=0)
        after = game.pot_bytes(4, 9)
        self.assertEqual((after[0x9E], after[FOR_SALE]), (1, 0))             # sold, in its own pot
        fields = lambda r: (r[:0x2C], r[PLANTED], r[FOLIAGE:FOLIAGE + 8], r[FOR_SALE], r[0x9E])
        for key, record in before.items():                                  # every other plant as it was
            if key != (4, 9):                                               # (its object may now be built)
                self.assertEqual(fields(game.pot_bytes(*key)), fields(record), key)
        emu.call(emu.sym("_clear_sold_elsewhere"), game.state)              # back in the greenhouse
        self.assertEqual(emu.read32(game.pot(4, 9) + FOLIAGE), 0)

    def test_owned_nurseries_round_trip_and_a_new_game_resets_them(self) -> None:
        game = Game(6)
        emu = game.emu
        disk = SidecarTests.files(SidecarTests(), game)
        emu.write32(emu.sym("_nurseries_on"), 1)
        emu.write32(emu.sym("_nurseries"), 3)
        emu.hook(0x00403690, lambda e: 1, 0xC)
        emu.call(emu.sym("_stub_save"), 4, ecx=game.state, edx=4)
        self.assertEqual(struct.unpack_from("<I", disk[SidecarTests.NAME], 24)[0], 3)
        emu.write32(emu.sym("_nurseries"), 0)
        emu.call(emu.sym("_on_loaded"), game.state, 4)
        self.assertEqual(emu.read32(emu.sym("_nurseries")), 3)
        emu.call(emu.sym("@new_game_clear@8"), ecx=game.manager)
        self.assertEqual(emu.read32(emu.sym("_nurseries")), 0)

    def test_a_setting_off_offers_nothing(self) -> None:
        game = Game(1)
        emu = game.emu
        self.assertEqual(emu.call(emu.sym("_FtfpExtraNurseriesOwned")), 0xFFFFFFFF)     # its .ini is not there
        emu.write32(emu.sym("_nurseries_on"), 1)
        self.assertEqual(emu.call(emu.sym("_FtfpExtraNurseriesBuy")), 1)
        emu.write32(emu.sym("_greenhouses_on"), 0)
        self.assertEqual(emu.call(emu.sym("_FtfpExtraGreenhousesOwned")), 0xFFFFFFFF)


class BackupTests(unittest.TestCase):
    """Back Up Saves and Restore (src/save_backup.py) with the slot files of the extra greenhouses and
    nurseries ("Plant Tycoon Fix Patcher Data\\Extra Greenhouses <slot>.dat", the pots, the greenhouses and
    the nurseries bought)."""

    def setUp(self) -> None:
        import save_backup
        import save_tools
        from test_save_backup import FakeProcesses, snapshot
        from test_save_tools import make_folder
        self.save_backup, self.save_tools, self.processes, self.snapshot = save_backup, save_tools, FakeProcesses, snapshot
        self.temp = tempfile.TemporaryDirectory()
        self.folder = make_folder(Path(self.temp.name), "plant", ["Ana", "Bo", "Cy", "Di", "Ed"],
                                  "Plant Tycoon - Modded Upgrades")
        self.data = self.folder / "Plant Tycoon Fix Patcher Data"
        self.data.mkdir()
        for slot in (1, 2):
            (self.data / f"Extra Greenhouses {slot}.dat").write_bytes(f"greenhouses {slot}".encode())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def back_up(self) -> Path:
        return self.save_backup.back_up_save_folder(self.folder, self.processes(), None).backup_folder

    def test_each_file_belongs_to_its_slot(self) -> None:
        for name, slot in (("Extra Greenhouses 1.dat", 1), ("Extra Greenhouses 5.dat", 5),
                           ("Extra Greenhouses 3.dat.tmp", 3), ("Extra Greenhouses 2.dat.unreadable", 2)):
            self.assertEqual(self.save_backup.file_slot("plant", Path("Plant Tycoon Fix Patcher Data") / name), slot)

    def test_a_backup_holds_them_and_a_whole_restore_puts_them_back(self) -> None:
        before = self.snapshot(self.folder)
        backup = self.back_up()
        self.assertEqual((backup / "Plant Tycoon Fix Patcher Data" / "Extra Greenhouses 2.dat").read_bytes(),
                         b"greenhouses 2")
        (self.data / "Extra Greenhouses 1.dat").write_bytes(b"later 1")
        (self.data / "Extra Greenhouses 3.dat").write_bytes(b"new 3")
        self.save_backup.restore_backup("plant", self.folder, backup, None, self.processes())
        self.assertEqual(self.snapshot(self.folder), before)

    def test_a_one_slot_restore_puts_back_only_that_slots_file(self) -> None:
        backup = self.back_up()
        (self.data / "Extra Greenhouses 1.dat").write_bytes(b"later 1")
        (self.data / "Extra Greenhouses 2.dat").write_bytes(b"later 2")
        self.save_backup.restore_backup("plant", self.folder, backup, 2, self.processes())
        self.assertEqual((self.data / "Extra Greenhouses 2.dat").read_bytes(), b"greenhouses 2")
        self.assertEqual((self.data / "Extra Greenhouses 1.dat").read_bytes(), b"later 1")


class ArrowLayoutTests(unittest.TestCase):
    """The greenhouse arrows stand on the top wall beside the name, where the player can see and click them:
    clear of the stock left panel (to x 240), the camera button (from x 760), the name at its widest
    ("Greenhouse 6 of 6") and the greenhouse counts ("Counts: On" at 646-744 x 4-24, the Plants line from y 62)."""

    @staticmethod
    def rect(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
        return x, y, x + w, y + h

    @staticmethod
    def apart(a, b) -> bool:
        return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]

    @unittest.skipUnless(PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon.exe (its font)")
    def test_the_arrows_are_beside_the_name_and_clear_of_the_stock_ui(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import render_extra_greenhouses_preview as R
        except ImportError:
            self.skipTest("needs Pillow")
        folder = PLANT_EXE.parent
        exe = PLANT_EXE.read_bytes()
        widest = R.words(folder, exe, "Greenhouse 6 of 6")
        x, y = constant("LABEL_X") - widest.width // 2, constant("LABEL_Y")
        name = (x, y, x + widest.width, y + widest.height)
        left = self.rect(constant("LEFT_X"), constant("ARROW_Y"), 50, 50)
        right = self.rect(constant("RIGHT_X"), constant("ARROW_Y"), 50, 50)
        free = (240, 0, 760, 62)                                        # the top wall, panel to camera, above the Plants line
        for arrow in (left, right):
            self.assertTrue(free[0] <= arrow[0] and arrow[2] <= free[2] and free[1] <= arrow[1] and arrow[3] <= free[3], arrow)
            self.assertTrue(self.apart(arrow, name), arrow)
            self.assertTrue(self.apart(arrow, (646, 4, 744, 24)), arrow)  # "Counts: On"
        self.assertLess(left[2], name[0])
        self.assertGreater(right[0], name[2])
        self.assertLessEqual(name[0] - left[2], 12)                     # just beside the name
        self.assertLessEqual(right[0] - name[2], 12)
        middle = (name[1] + name[3]) / 2
        self.assertLessEqual(abs((left[1] + left[3]) / 2 - middle), 2)  # centred on the text


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.setting = next(s for s in self.manifest["settings"] if s["id"] == SETTING)

    def test_the_setting(self) -> None:
        s = self.setting
        self.assertEqual(s["name"], "5 extra greenhouses")
        self.assertFalse(s["default"])
        self.assertTrue(s["separate_output"])
        self.assertEqual(s["requires_settings"], ["plant_upgrades"])        # sold on the Upgrades screen
        self.assertIn("empty", s["warning"].lower())
        self.assertTrue(s["companion"]["startup_loader"])
        files = {f["destination"]: f for f in s["companion"]["files"]}
        self.assertEqual(set(files), {f"{FOLDER}/Extra Greenhouses.dll", f"{FOLDER}/Extra Greenhouses.ini"})
        data = DLL.read_bytes()
        entry = files[f"{FOLDER}/Extra Greenhouses.dll"]
        self.assertEqual((entry["size"], entry["sha256"]), (len(data), hashlib.sha256(data).hexdigest().upper()))
        nurseries = next(n for n in self.manifest["settings"] if n["id"] == "extra_nurseries")
        self.assertEqual(nurseries["name"], "5 extra nurseries")
        self.assertFalse(nurseries["default"])
        self.assertEqual(nurseries["requires_settings"], ["plant_upgrades"])
        self.assertEqual({f["destination"] for f in nurseries["companion"]["files"]},
                         {f"{FOLDER}/Extra Greenhouses.dll", f"{FOLDER}/Extra Nurseries.ini"})
        for each in (s, nurseries):                                            # the owner's label, wherever shown
            self.assertTrue(each["summary"].startswith("EXPERIMENTAL - USE AT OWN RISK"), each["id"])
            self.assertTrue(each["description"].startswith("EXPERIMENTAL - USE AT OWN RISK"), each["id"])
        for f in self.manifest["settings"]:
            for c in (f.get("companion") or {}).get("files", []):
                source = ROOT / f["companion"]["source"] / c["path"]
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest().upper(), c["sha256"], c["path"])

    def test_the_loader_loads_this_dll_first_when_the_setting_is_on(self) -> None:
        for others in (set(), {"new_flowers"}, {"sort_seeds"}, {"new_flowers", "plant_upgrades", "sort_seeds"}):
            for setting in (SETTING, "extra_nurseries"):
                self.assertEqual(ds_fish_loader.plant_profile(others | {setting}).dll_name, "Extra Greenhouses.dll")
        self.assertEqual(ds_fish_loader.plant_profile({"new_flowers"}).dll_name, "Unused Flowers.dll")
        self.assertEqual(ds_fish_loader.plant_profile({"sort_seeds"}).dll_name, "Sort Seeds.dll")

    def test_every_combination_with_the_setting_is_pinned(self) -> None:
        pins = self.manifest["patched_sha256_by_settings"]
        ours = {SETTING, "extra_nurseries"}
        without = [k for k in pins if not ours & set(k.split(","))]
        for key in without:
            for extra in ({SETTING}, {"extra_nurseries"}, ours):
                enabled = {s for s in key.split(",") if s} | extra
                self.assertIn(plant_patcher.settings_key(enabled, self.manifest), pins)

    def test_off_leaves_every_other_combination_as_it_was(self) -> None:
        self.assertFalse(any(SETTING in p.get("requires", []) for p in self.manifest["patches"]))
        self.assertEqual(ds_fish_loader.plant_profile(set()).dll_name, "Sort Seeds.dll")

    def test_the_release_packages_it(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_release
        packaged = set(build_release.FILES) | set(build_release.bundled_asset_files())
        for path in ("assets/plant_tycoon_greenhouses/Extra Greenhouses.dll",
                     "docs/plant-tycoon-extra-greenhouses-design.md", "docs/images/extra-greenhouses-switch.png"):
            self.assertIn(path, packaged)
            self.assertTrue((ROOT / path).is_file(), path)

    @unittest.skipUnless(PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon.exe")
    def test_pins_are_the_patchers_output(self) -> None:
        vanilla = PLANT_EXE.read_bytes()
        pins = self.manifest["patched_sha256_by_settings"]
        for key in (SETTING, f"new_flowers,{SETTING}", f"sort_seeds,{SETTING}", "extra_nurseries",
                    f"extra_nurseries,{SETTING},new_flowers,plant_upgrades"):
            enabled = set(key.split(","))
            patched, _ = plant_patcher.apply_patch_bytes(vanilla, plant_patcher.active_patch_records(self.manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled))
            self.assertEqual(hashlib.sha256(patched).hexdigest().upper(),
                             pins[plant_patcher.settings_key(enabled, self.manifest)])
            self.assertIn("Extra Greenhouses.dll".encode("utf-16-le"), patched)


if __name__ == "__main__":
    unittest.main()
