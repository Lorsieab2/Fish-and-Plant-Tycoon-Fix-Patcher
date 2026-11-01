"""Picture Studio's Plant Tycoon renderer (src/pictures_plant.py).

The emulated tests run the vanilla "Plant Tycoon.exe" in Unicorn (tests/store_emulator.py): the
game's own pot draw (0x42F740), plant draw (vtable slots 7, 10, 13, 11: 0x42E4A0, 0x42E690,
0x42CFE0, 0x42D9C0), its flowering (0x42ED60 / 0x42EBC0), its age-7 roll (0x42DEC0), its
constructors and its scaler (0x404610). Every sprite the game blits is recorded at its blitter
(0x404610 / 0x4045A0: sheet, source rectangle, top-left, scale) and compared with the renderer's
plan; the scaler's pixels are compared with the renderer's port. The other tests need nothing but
Python: the save reader on synthetic saves, the PNG output, the choices and spoilers.
"""

from __future__ import annotations

import dataclasses
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import picture_image as pi  # noqa: E402
import pictures_plant as pp  # noqa: E402
import pictures_plant_data as D  # noqa: E402

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon"
PLANT_EXE = VANILLA / "Plant Tycoon.exe"
HAVE_EXE = PLANT_EXE.is_file() and (VANILLA / "Images").is_dir()
needs_game = unittest.skipUnless(E is not None and HAVE_EXE, "needs Unicorn and the vanilla Plant Tycoon")
needs_art = unittest.skipUnless(HAVE_EXE, "needs the vanilla Plant Tycoon's pictures")

RANDOM, NEW, DELETE, MEMSET, MEMCPY = 0x004033B0, 0x0044E894, 0x0044E7B3, 0x00451280, 0x00450C10
BLIT, PLAIN_BLIT = 0x00404610, 0x004045A0
LOCK, UNLOCK = 0x0044E660, 0x0044E654
FACTORY, POT_DRAW, ADD_FLOWERS, AGE_SEVEN = 0x0042EE20, 0x0042F740, 0x0042ED60, 0x0042DEC0
WHOLE_IMAGE, FRAME_IMAGE = 0x00420550, 0x00420310
STATE_SIZE = 0x63E70
ORIGIN = (1000, 1000)                 # where the pot stands on the emulated screen


def png_size(data: bytes) -> tuple:
    return struct.unpack(">II", data[16:24])


class DrawGame:
    """The vanilla game in Unicorn, set up to draw one pot: its sprites are surfaces this harness
    makes (each named by its sprite id), and every blit is recorded instead of drawn."""

    def __init__(self, seed: int = 1, pixels: bool = False) -> None:
        emu = self.emu = E.Emulator(PLANT_EXE, None, {})
        emu.uc.mem_map(0, 0x1000)
        self.rng = random.Random(seed)
        self.blits: list = []
        emu.hook(RANDOM, lambda e: self.rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0)
        emu.hook(NEW, lambda e: e.alloc(max(e.arg(0), 4)))
        emu.hook(DELETE, lambda e: 0)

        def memset(e):
            e.uc.mem_write(e.arg(0), bytes([e.arg(1) & 0xFF]) * e.arg(2))
            return e.arg(0)
        emu.hook(MEMSET, memset)
        emu.hook(MEMCPY, lambda e: e.uc.mem_write(e.arg(0), bytes(e.uc.mem_read(e.arg(1), e.arg(2)))) or e.arg(0))
        emu.hook(LOCK, lambda e: 0)
        emu.hook(UNLOCK, lambda e: 0)
        self.format = self._format()
        self.surfaces: dict = {}           # surface address -> sprite id
        self.images: dict = {}             # (sprite id, whole) -> image object
        self.state = emu.alloc(STATE_SIZE)
        side = self.side = 512 if pixels else 4096
        screen = self.screen = self.surface(side, side, store=pixels)
        inner = self.graphics_inner = emu.alloc(0x100)
        emu.write32(inner + 8, side)
        emu.write32(inner + 0xC, side)
        emu.write32(inner + 0x30, screen)
        for at, value in ((0x60, 0), (0x64, 0), (0x68, side), (0x6C, side)):
            emu.write32(inner + at, value)
        self.graphics = emu.alloc(0x10)
        emu.write32(self.graphics, inner)
        self.sprites = emu.alloc(0x10)
        emu.write32(self.sprites, emu.alloc(0x10))
        emu.write32(self.sprites + 4, self.graphics)          # the sprite manager draws through it (0x420939)
        emu.hook(0x0041FCD0, lambda e: self.state)
        emu.hook(0x00420670, lambda e: self.sprites)
        emu.hook(0x00407A90, lambda e: self.graphics)
        emu.write32(0x00493C34, self.sprites)
        emu.hook(WHOLE_IMAGE, lambda e: self.image(e.arg(0), whole=True), 4)
        emu.hook(FRAME_IMAGE, lambda e: self.image(e.arg(0), whole=False), 4)
        if not pixels:
            emu.hook(BLIT, self._blit, 0x28)
            emu.hook(PLAIN_BLIT, self._plain_blit, 0x1C)
        self.manager = emu.alloc(0x810A4)
        emu.write32(self.manager, self.state)
        emu.write32(self.manager + 4, self.sprites)

    def unused_flowers(self) -> "DrawGame":
        """What Unused Flowers.dll writes for the draw (native/ftfp_new_flowers, flower_sites.h):
        the flower draw's bound 0x16 -> 0x24 (0x42D9D2) and the art lookup (0x42D2D0) answering
        its ART records for genes 24-37."""
        emu = self.emu
        emu.write8(0x0042D9D2, 0x24)
        records = {}
        for gene in range(24, 38):
            records[gene] = emu.alloc(0x1C)
            emu.uc.mem_write(records[gene], struct.pack("<7i", *D.FLOWER_ART[gene]))
        emu.hook(0x0042D2D0, lambda e: records.get(e.arg(0), 0x0048E6B8 + e.arg(0) * 0x1C), 4)
        return self

    # ------------------------------------------------------------ surfaces
    def _format(self) -> int:
        """SDL_PixelFormat of ABGR8888 (bytes R, G, B, A), as SDL_image gives a PNG with alpha."""
        fmt = self.emu.alloc(0x28)
        self.emu.uc.mem_write(fmt, struct.pack("<IIBB2xIIII4B4B", 0x16762004, 0, 32, 4, 0xFF, 0xFF00, 0xFF0000,
                                               0xFF000000, 0, 0, 0, 0, 0, 8, 16, 24))
        return fmt

    def surface(self, w: int, h: int, data: bytes | None = None, store: bool = True) -> int:
        emu = self.emu
        surface = emu.alloc(0x40)
        pixels = emu.alloc(w * h * 4) if store else 0
        if data is not None:
            emu.uc.mem_write(pixels, bytes(data))
        emu.uc.mem_write(surface, struct.pack("<IIiiiI", 0, self.format, w, h, w * 4, pixels))
        return surface

    def image(self, sprite: int, whole: bool) -> int:
        key = (sprite, whole)
        if key not in self.images:
            name, cols, rows = D.SPRITES[sprite]
            data = next(p for p in (VANILLA / "Images").iterdir() if p.name.casefold() == name.casefold()).read_bytes()
            w, h = png_size(data)
            cols, rows = (1, 1) if whole or not cols else (cols, rows)
            surface = self.surface(w, h, store=False)
            self.surfaces[surface] = sprite
            wrapper = self.emu.alloc(0x10)
            self.emu.write32(wrapper, surface)
            obj = self.emu.alloc(0x40)
            for at, value in ((4, wrapper), (8, cols), (0xC, max(1, rows)), (0x10, w // cols), (0x14, h // max(1, rows))):
                self.emu.write32(obj + at, value)
            self.images[key] = obj
        return self.images[key]

    def _blit(self, e) -> int:
        surface, x, y, x0, y0, x1, y1 = (e.arg(i) for i in range(7))
        alpha, scale = struct.unpack("<ff", struct.pack("<II", e.arg(7), e.arg(8)))
        signed = lambda v: v - (1 << 32) if v & 0x80000000 else v
        self.blits.append((D.SPRITES[self.surfaces[surface]][0], (x0, y0, x1, y1), signed(x) - ORIGIN[0],
                           signed(y) - ORIGIN[1], round(scale * 100), int(alpha * 255.0)))
        return 0

    def _plain_blit(self, e) -> int:
        surface, x, y, x0, y0, x1, y1 = (e.arg(i) for i in range(7))
        signed = lambda v: v - (1 << 32) if v & 0x80000000 else v
        self.blits.append((D.SPRITES[self.surfaces[surface]][0], (x0, y0, x1, y1), signed(x) - ORIGIN[0],
                           signed(y) - ORIGIN[1], 100, 255))
        return 0

    # ------------------------------------------------------------ the game
    def pot(self, record: bytes, k: int = 0) -> int:
        address = self.state + 0x2188 + k * 0x5600
        self.emu.uc.mem_write(address, record)
        return address

    def draw_pot(self, record: bytes, soil_upgrade: int = 0) -> list:
        """The game's own pot draw (0x42F740) of pot 0 at ORIGIN."""
        self.pot(record)
        self.emu.write32(self.manager + 8, 0)       # the game makes the pot's plant object again (0x42F6C0)
        for at, level in pp.SOIL_UPGRADES:
            self.emu.write8(self.state + at, 1 if soil_upgrade == level else 0)
        self.blits = []
        self.emu.call(POT_DRAW, 0, 0, ORIGIN[0], ORIGIN[1], 0, ecx=self.manager)
        return self.blits

    def plant_object(self, k: int = 0) -> int:
        obj = self.emu.call(0x0042F6C0, k // 5, k % 5, ecx=self.manager)
        assert obj, "the game made no plant object"
        return obj

    def record(self, k: int = 0) -> bytes:
        return bytes(self.emu.uc.mem_read(self.state + 0x2188 + k * 0x5600, 0x5600))


def plan_tuples(plan) -> list:
    return [(d.file, d.rect, d.x, d.y, d.scale, d.alpha) for d in plan]


class Cells:
    """Cell sizes from the vanilla pictures' headers."""

    def __init__(self) -> None:
        self.sizes = {p.name.casefold(): png_size(p.read_bytes()) for p in (VANILLA / "Images").iterdir()
                      if p.suffix.casefold() == ".png"}

    def __call__(self, key) -> tuple:
        name, cols, rows = key
        w, h = self.sizes[name.casefold()]
        return w // max(1, cols), h // max(1, rows)


def custom_specs():
    """Every foliage with three flowers, each stage alive and dead, two shapes; the Unused
    Flowers too."""
    flowers = [1, 2, 3, 9, 13, 14, 18, 23]
    for foliage in range(1, 24):
        for i, stage in enumerate(k for k, _ in pp.STAGES):
            flower = flowers[(foliage + i) % len(flowers)]
            for shape in (1, 1 + (foliage % D.SHAPE_COUNT)):
                yield foliage, flower, stage, shape, shape != 1 and (foliage + i) % 2 == 0
    for flower in range(24, 38):
        yield 1 + flower % 23, flower, "bloom", 1, flower % 5 == 0


@needs_game
class DrawPlanTests(unittest.TestCase):
    """The renderer's draw calls are the game's, call for call."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cells = Cells()
        cls.planner = pp.Planner(cls.cells)

    def compare(self, plant: pp.Plant, game: DrawGame, label: str, soil: int = 0) -> list:
        record = plant.to_record()
        recorded = game.draw_pot(record, soil)
        read = pp.Plant.from_record(record)          # as a save holds it: the formula is read from its flowers
        planned = plan_tuples(self.planner.plan(read, 0, 0, soil_level=soil))
        self.assertEqual(planned, recorded, label)
        return recorded

    def formula_game(self) -> DrawGame:
        """The game with the shape tables as Store Upgrades and Items.dll leaves them."""
        game = DrawGame()
        for foliage, d, s, x, y in D.FORMULA_SPOTS:
            at = D.CLASSES[foliage][2] + d * 0xF4 + 0xAC + s * 12
            if bytes(game.emu.uc.mem_read(at, 12)) == bytes(12):
                game.emu.uc.mem_write(at, struct.pack("<ii", x, y))
        return game

    def test_plants_of_your_own_draw_as_the_game_draws_them(self) -> None:
        game, formula_game, flowers_game = DrawGame(), None, DrawGame().unused_flowers()
        count = 0
        dead_stages = set()
        for foliage, flower, stage, shape, dead in custom_specs():
            plant = pp.grow_custom(foliage, flower, shape, stage, dead)
            label = f"{foliage}/{flower}/{stage}/{shape}" + (" dead" if dead else "")
            if dead:
                dead_stages.add(stage)
            if stage == "formula":
                formula_game = formula_game or self.formula_game()
                recorded = self.compare(plant, formula_game, label)
            elif flower >= 24:
                recorded = self.compare(plant, flowers_game, label)
            else:
                recorded = self.compare(plant, game, label)
            if stage == "seed":          # under age 1 no branch is drawn: the pot and the planted soil
                self.assertEqual(len(recorded), 2, label)
            else:
                self.assertGreater(len(recorded), 2, label)
            count += 1
        self.assertGreater(count, 200)
        self.assertEqual(dead_stages, {k for k, _ in pp.STAGES}, "every stage drawn dead too")

    def test_a_saved_formula_plant_draws_as_the_patched_game_draws_it(self) -> None:
        """The player's mature, size-110 formula plants (a flower on every spot), read back from
        the record: the formula's flowers are drawn on the spots Store Upgrades and Items.dll
        fills, call for call as the patched game draws them, not at the stock table's empty
        (0, 0) spots."""
        game = self.formula_game()
        for foliage in D.FORMULA_FOLIAGES:
            plant = pp.grow_custom(foliage, 1 + (foliage * 3) % 23, 1, "formula")
            plant.age = pp.f32(134.0)
            record = plant.to_record()
            read = pp.Plant.from_record(record)
            self.assertTrue(read.formula, foliage)
            self.assertEqual(read.size, 110)
            recorded = game.draw_pot(record)
            self.assertEqual(plan_tuples(self.planner.plan(read, 0, 0)), recorded, f"foliage {foliage}")
            stock = dataclasses.replace(read, formula=False)
            self.assertNotEqual(plan_tuples(self.planner.plan(stock, 0, 0)), recorded, f"foliage {foliage}")

    def test_unused_parts_draw_as_the_game_draws_them(self) -> None:
        """Each unused part, alive and dead, as the game's own pot draw draws a plant of that part
        alone (its pot and soil left out of the picture)."""
        game = DrawGame()
        pot_files = {D.SPRITES[pp.POT_SPRITE][0], D.SPRITES[pp.SOIL_SPRITE][0]}
        for foliage, parts in pp.UNUSED_PARTS.items():
            for part in parts:
                for dead in (False, True):
                    plant = pp.unused_part_plant(foliage, part, dead)
                    recorded = [b for b in game.draw_pot(plant.to_record()) if b[0] not in pot_files]
                    planned = plan_tuples(self.planner.plan(plant, 0, 0, pot=False))
                    self.assertEqual(planned, recorded, f"{foliage}:{part} dead {dead}")
                    self.assertEqual(len(planned), 1)

    def test_no_constructor_makes_the_unused_parts(self) -> None:
        """No class's constructor makes a branch of an unused part, with Random answered 0, n - 1
        or at random (20 ways), and every other part with a picture is made."""
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_picture_studio_plant_data as build
        for foliage, (ctor, _v, _t) in D.CLASSES.items():
            emu = E.Emulator(PLANT_EXE, None, {})
            emu.uc.mem_map(0, 0x1000)
            answer = {"f": None}
            emu.hook(RANDOM, lambda e: answer["f"](e.arg(0)) if e.arg(0) > 0 else 0)
            for singleton in (0x41FCD0, 0x420670, 0x407A90):
                emu.hook(singleton, lambda e: e.alloc(0x100))
            made = set()
            ways = [lambda n: 0, lambda n: n - 1] + [random.Random(k).randrange for k in range(20)]
            for way in ways:
                answer["f"] = way
                record = emu.alloc(build.RECORD)
                emu.write32(record + 0x4C, foliage)
                emu.write32(record + 0x50, 1)
                emu.call(ctor, record, ecx=emu.alloc(0x58))
                made |= {b[0] for b in build.branches(bytes(emu.uc.mem_read(record, build.RECORD)))}
            pictured = {p.id for p in pp.SHAPES[foliage] if p.sheet}
            self.assertEqual(pictured - made, set(pp.UNUSED_PARTS.get(foliage, ())), foliage)

    def test_every_age_and_size_and_a_dead_plant(self) -> None:
        game = DrawGame()
        for foliage in range(1, 24):
            plant = pp.grow_custom(foliage, 1 + foliage % 23, 3, "max")
            for age in (0.5, 1.0, 1.7, 3.25, 9.0, 18.9, 19.0, 20.99, 21.0, 22.0, 23.9, 24.0, 25.5, 27.99, 28.0, 41.0):
                for size, health, bloom, pot in ((80, 100, 70, 0), (110, 100, 100, 3), (55, 0, 100, 6), (95, 40, 0, 2)):
                    plant.age, plant.size, plant.health, plant.bloom, plant.pot = pp.f32(age), size, health, bloom, pot
                    self.compare(plant, game, f"{foliage} age {age} size {size} health {health}")

    def test_soil_upgrades_and_water(self) -> None:
        game = DrawGame()
        plant = pp.grow_custom(7, 5, 1, "bloom")
        for level in (0, 1, 2):
            for water in (0, 501, 900):
                plant.water = water
                self.compare(plant, game, f"soil {level} water {water}", soil=level)
        empty = pp.Plant(foliage=0, flower=0, age=0.0, soil=1)
        self.assertEqual(plan_tuples(self.planner.plan(empty, 0, 0)), game.draw_pot(empty.to_record()))

    def test_plants_the_game_grew_draw_as_the_game_draws_them(self) -> None:
        """Plants made and grown by the game's own code (seed planted 0x42FC70, the update
        0x41D810 over days), read back from their records as a save holds them."""
        for foliage in range(1, 24):
            game = GrownGame(seed=foliage)
            game.plant(foliage, 1 + (foliage * 5) % 23)
            for dt in (3600, 7200, 4 * 3600, 6 * 3600, 3600):
                game.tick(dt)
                record = game.record()
                plant = pp.Plant.from_record(record)
                draw = DrawGame()
                self.assertEqual(plan_tuples(self.planner.plan(plant, 0, 0)), draw.draw_pot(record),
                                 f"foliage {foliage} at age {plant.age}")


@needs_game
class SceneryTests(unittest.TestCase):
    """Decorations, bugs and pots: the renderer's draw calls are the game's."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cells = Cells()
        cls.planner = pp.Planner(cls.cells)
        cls.scenery = pp.SceneryPlanner(cls.cells, cls.planner)

    def nursery(self, owned: set) -> list:
        """The game's own scenery draw (0x437070(2), then (1)) with these ornaments owned, every
        blit recorded; the magic plants' golden pots and the visitors are left out."""
        game = DrawGame()
        emu = game.emu
        for address, pop in ((0x0042F4B0, 0x10), (0x00435EE0, 0x10), (0x00417350, 0)):
            emu.hook(address, lambda e: 0, pop)
        emu.hook(0x00417C50, lambda e: e.alloc(0x100))
        for k in owned:
            emu.write8(game.state + pp.ORNAMENTS_AT + k * pp.ORNAMENT_SIZE, 1)
        scene = emu.alloc(0x1000)
        emu.write32(scene + 0xA3C, game.state)
        emu.write32(scene + 0xA40, game.sprites)
        emu.write32(scene + 0xA44, game.manager)
        for layer in (2, 1):
            emu.call(0x00437070, layer, ecx=scene)
        return [(f, r, x + ORIGIN[0], y + ORIGIN[1], s, a) for f, r, x, y, s, a in game.blits]

    def test_every_decoration_is_the_nurserys(self) -> None:
        base = self.nursery(set())
        self.assertEqual(len(D.DECORATIONS), 15)
        for k in range(15):
            rest, added = list(base), []
            for call in self.nursery({k}):
                if call in rest:
                    rest.remove(call)
                else:
                    added.append(call)
            self.assertEqual(plan_tuples(self.scenery.decoration(k)), added, pp.ORNAMENT_NAMES[k])
        everything = self.nursery(set(range(15)))
        for k in range(15):                             # all owned: each one's calls still drawn
            for call in plan_tuples(self.scenery.decoration(k)):
                self.assertIn(call, everything)

    def test_every_bug_frame_is_the_sprite_draw(self) -> None:
        game = DrawGame()
        one = struct.unpack("<I", struct.pack("<f", 1.0))[0]
        for bug in range(pp.BUG_COUNT):
            for frame in range(pp.BUG_FRAMES):
                game.blits = []
                game.emu.call(0x004208F0, pp.BUG_SPRITE, bug * 6 + frame, ORIGIN[0], ORIGIN[1], one, 100, 1,
                              ecx=game.sprites)
                self.assertEqual(plan_tuples(self.scenery.bug(bug, frame)), game.blits, f"bug {bug} frame {frame}")

    def test_every_pot_look_is_the_pot_draw(self) -> None:
        game = DrawGame()
        for style in range(7):
            for soil, _label in pp.SOIL_LOOKS:
                for level in pp.SOIL_LEVELS:
                    for wet in (False, True):
                        plan = plan_tuples(self.scenery.pot(style, soil, level, wet))
                        plant = pp.Plant(foliage=1 if soil == "planted" else 0, flower=0, age=0.0, pot=style,
                                         soil=0 if soil == "none" else 1, water=900 if wet else 0)
                        recorded = game.draw_pot(plant.to_record(), level)
                        # a planted pot's own plant (the game makes a seedling for it) is not the pot
                        self.assertEqual(plan, recorded[:len(plan)], f"{style} {soil} {level} {wet}")
                        self.assertEqual(len(plan), 1 if soil == "none" else 2)


class GrownGame:
    """The vanilla game after its own new game (as tests/test_extra_greenhouses.py's Game, with no
    DLL): seeds planted and grown by the game's code."""

    def __init__(self, seed: int) -> None:
        emu = self.emu = E.Emulator(PLANT_EXE, None, {})
        emu.uc.mem_map(0, 0x1000)
        self.now = 1_000_000
        self.rng = random.Random(seed)
        emu.hook(RANDOM, lambda e: self.rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0)
        emu.hook(0x00403430, lambda e: self.now)
        emu.hook(0x00402080, lambda e: self.now)

        def memset(e):
            e.uc.mem_write(e.arg(0), bytes([e.arg(1) & 0xFF]) * e.arg(2))
            return e.arg(0)
        emu.hook(MEMSET, memset)
        emu.hook(MEMCPY, lambda e: e.uc.mem_write(e.arg(0), bytes(e.uc.mem_read(e.arg(1), e.arg(2)))) or e.arg(0))
        emu.hook(NEW, lambda e: e.alloc(max(e.arg(0), 4)))
        emu.hook(DELETE, lambda e: 0)
        emu.hook(0x0041D830, lambda e: 0, 8)
        for address, pop in ((0x0041C1F0, 0x1C), (0x0041B190, 8), (0x0044A580, 4), (0x0044A520, 8), (0x0044A550, 0xC),
                             (0x00423630, 0xC), (0x00416700, 4), (0x004244C0, 0), (0x00435FF0, 0x18), (0x00401570, 0x14),
                             (0x00409AA0, 0x10), (0x0040B650, 4), (0x00401AA0, 0x18), (0x0040B400, 4), (0x004092B0, 0x14),
                             (0x00401C90, 8), (0x0042AAA0, 0)):
            emu.hook(address, lambda e: 0, pop)
        emu.hook(0x0044CA70, lambda e: e.text("text"), 4)
        state = self.state = emu.alloc(STATE_SIZE)
        esp = E.STACK + E.STACK_SIZE - 0x1000
        emu.write32(esp, E.RETURN)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ECX, state)
        emu.uc.emu_start(0x41EF30, 0x41F17D, count=20_000_000)
        emu.write32(state + 0x534, 10)
        emu.write32(0x0049333C, state)
        emu.write32(0x00493C34, emu.alloc(0x100))
        emu.write32(0x00493948, emu.alloc(0x100))
        manager = self.manager = emu.alloc(0x810A4)
        emu.write32(manager, state)
        emu.write32(manager + 4, emu.read32(0x00493C34))
        emu.write32(0x00493C80, manager)

    def plant(self, foliage: int, flower: int, k: int = 7) -> None:
        seed = self.emu.alloc(0x24)
        self.emu.write32(seed + 0x10, foliage)
        self.emu.write32(seed + 0x14, flower)
        self.emu.call(0x0042FC70, seed, k // 5, k % 5, ecx=self.manager)
        self.k = k

    def tick(self, seconds: int) -> None:
        self.now += seconds
        self.emu.call(0x0041D810, ecx=self.state)

    def record(self) -> bytes:
        return bytes(self.emu.uc.mem_read(self.state + 0x2188 + self.k * 0x5600, 0x5600))


@needs_game
class GrowthTests(unittest.TestCase):
    """The ported growth rules make the records the game's code makes, Random for Random."""

    def game_with(self, plant: pp.Plant, seed: int, formula: bool = False) -> tuple:
        game = DrawGame(seed)
        if formula:
            for foliage, d, s, x, y in D.FORMULA_SPOTS:
                at = D.CLASSES[foliage][2] + d * 0xF4 + 0xAC + s * 12
                if bytes(game.emu.uc.mem_read(at, 12)) == bytes(12):
                    game.emu.uc.mem_write(at, struct.pack("<ii", x, y))
        game.pot(plant.to_record())
        return game, game.plant_object()

    def test_the_starting_shapes_are_the_constructors(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_picture_studio_plant_data as build
        exe = build.Exe(PLANT_EXE.read_bytes())
        table = {f: (c, v, s, build.shape_table(exe, s)) for f, (c, v, s) in build.classes(exe).items()}
        self.assertEqual({f: (c, v, s) for f, (c, v, s, _d) in table.items()}, D.CLASSES)
        self.assertEqual({f: d for f, (_c, _v, _s, d) in table.items()}, D.SHAPE_TABLES)
        self.assertEqual(build.starting_shapes(PLANT_EXE, table), D.STARTING_SHAPES)
        self.assertEqual(build.formula_spots(table), D.FORMULA_SPOTS)
        self.assertEqual({g: v for g, v in build.flower_art(exe).items()}, D.FLOWER_ART)
        self.assertEqual(build.decorations(PLANT_EXE), D.DECORATIONS)

    def test_flowering_is_the_games(self) -> None:
        """0x42ED60(many, more) on the same plant with the same rolls: the same flowers."""
        for foliage in range(1, 24):
            for many, more, seed in ((1, 1, 3), (3, 2, 5), (360, 0, 7)):
                plant = pp.starting_plant(foliage, 5, 1 + foliage % 5)
                plant.age = 25.0
                game, obj = self.game_with(plant, seed)
                game.emu.call(ADD_FLOWERS, many, more, ecx=obj)
                mine = pp.Plant.from_record(plant.to_record())
                rolls = random.Random(seed)
                pp.add_flowers(mine, pp.SHAPES[foliage], foliage, lambda n: rolls.randrange(n) if n > 0 else 0, many, more)
                theirs = pp.Plant.from_record(game.record())
                self.assertEqual([b.flowers for b in mine.branches], [b.flowers for b in theirs.branches],
                                 f"foliage {foliage} ({many}, {more})")
                self.assertEqual(mine.bloom, theirs.bloom)

    def test_the_first_flowering_is_the_updates(self) -> None:
        """The update's flowering block (0x42E375..0x42E45C, run on a plant of 21 with no flowers):
        the counts by size, flower sheet and health, then 0x42ED60."""
        cases = 0
        for foliage in range(1, 24):
            for flower, size, health, seed in ((1, 80, 100, 1), (2, 95, 100, 2), (15, 100, 60, 3), (9, 110, 30, 4),
                                               (13, 60, 79, 5), (4, 91, 100, 6)):
                plant = pp.starting_plant(foliage, flower, 1 + seed % 4)
                plant.age, plant.size, plant.health = 21.5, size, health
                game, obj = self.game_with(plant, seed)
                game.emu.run_until(0x0042E375, 0x0042E45C, esi=obj)
                mine = pp.Plant.from_record(plant.to_record())
                rolls = random.Random(seed)
                pp.first_flowering(mine, pp.SHAPES[foliage], foliage, lambda n: rolls.randrange(n) if n > 0 else 0)
                theirs = pp.Plant.from_record(game.record())
                self.assertEqual([b.flowers for b in mine.branches], [b.flowers for b in theirs.branches],
                                 f"foliage {foliage} flower {flower} size {size} health {health}")
                self.assertEqual(mine.bloom, theirs.bloom)
                cases += any(b.flowers for b in mine.branches)
        self.assertGreater(cases, 100)

    def test_the_formulas_flowering_is_the_dlls(self) -> None:
        """flower_everything: the counts raised to the spots in place (known tables), every spot
        free (0x42D330 answers 1), 0x42ED60(360, 0)."""
        for foliage in range(1, 24):
            plant = pp.starting_plant(foliage, 9, 2)
            for b in plant.branches:
                if b.kind in (2, 4):
                    b.kind = 1
            plant.age = 28.0
            game, obj = self.game_with(plant, 11, formula=True)
            if foliage in D.FORMULA_FOLIAGES:
                for d, part in enumerate(pp.FORMULA_SHAPES[foliage]):
                    at = D.CLASSES[foliage][2] + d * 0xF4 + 0xA8
                    game.emu.write32(at, pp.spot_count(part, foliage, True))
            game.emu.hook(0x0042D330, lambda e: 1, 0xC)
            game.emu.call(ADD_FLOWERS, 360, 0, ecx=obj)
            mine = pp.Plant.from_record(plant.to_record())
            rolls = random.Random(11)
            pp.add_flowers(mine, pp.FORMULA_SHAPES[foliage], foliage, lambda n: rolls.randrange(n) if n > 0 else 0,
                           360, 0, formula=True)
            self.assertEqual([b.flowers for b in mine.branches], [b.flowers for b in pp.Plant.from_record(game.record()).branches],
                             f"foliage {foliage}")

    def test_the_age_seven_roll_is_the_games(self) -> None:
        for foliage in range(1, 24):
            for seed in (1, 2, 3):
                plant = pp.starting_plant(foliage, 5, 1 + seed)
                plant.age = 7.5
                pp.add_flowers(plant, pp.SHAPES[foliage], foliage, random.Random(seed).randrange, 2, 1)
                game, obj = self.game_with(plant, seed)
                game.emu.call(AGE_SEVEN, ecx=obj)
                mine = pp.Plant.from_record(plant.to_record())
                rolls = random.Random(seed)
                pp.age_seven_roll(mine, pp.SHAPES[foliage], lambda n: rolls.randrange(n) if n > 0 else 0)
                theirs = pp.Plant.from_record(game.record())
                self.assertEqual([(b.kind, b.flowers) for b in mine.branches],
                                 [(b.kind, b.flowers) for b in theirs.branches], f"foliage {foliage} seed {seed}")


@needs_game
class ScalerTests(unittest.TestCase):
    """The renderer's port of the game's scaler (0x404610) gives the game's pixels."""

    def test_shrinking_and_enlarging_give_the_games_pixels(self) -> None:
        rng = random.Random(4)
        for w, h in ((7, 5), (23, 17), (40, 33)):
            piece = pi.Image(w, h, bytes(rng.choice((0, rng.randrange(256))) if i % 4 == 3 else rng.randrange(256)
                                         for i in range(w * h * 4)))
            for percent in (13, 25, 33, 50, 61, 70, 85, 99, 101, 110, 150, 233):
                for background in (0, 255):
                    game = DrawGame(pixels=True)
                    screen_w = game.side
                    src = game.surface(w, h, piece.data)
                    pixels = game.emu.read32(game.screen + 0x14)
                    game.emu.uc.mem_write(pixels, bytes([background]) * (screen_w * 4 * 120))
                    scale = struct.unpack("<I", struct.pack("<f", pp.f32(percent / 100.0)))[0]
                    game.emu.call(BLIT, src, 10, 10, 0, 0, w, h, struct.unpack("<I", struct.pack("<f", 1.0))[0], scale, 0,
                                  ecx=game.graphics_inner)
                    mine = pp.resample(piece, percent)
                    for y in range(mine.height):
                        row = bytes(game.emu.uc.mem_read(pixels + ((10 + y) * screen_w + 10) * 4, mine.width * 4))
                        for x in range(mine.width):
                            r, g, b, a = mine.pixel(x, y)
                            want = tuple((c * a + background * (255 - a) + 127) >> 8 if a else background
                                         for c in (r, g, b))
                            self.assertEqual(tuple(row[x * 4:x * 4 + 3]), want, f"{w}x{h} at {percent}% ({x}, {y})")


# ------------------------------------------------------------------ the save reader (synthetic saves)

def synthetic_save(folder: Path, slot: int, pots: dict, sidecar: dict | None = None, upgrade: int = 0,
                   ornaments: tuple = ()) -> None:
    """A save the shape of the game's ("ldwg", 0x18 + 0x53FB0 bytes) with these pot records, and
    Extra Greenhouses' sidecar when given ({(greenhouse 1-5, pot): record})."""
    data = bytearray(pp.SAVE_HEADER + pp.SAVE_BODY)
    data[:4] = b"ldwg"
    body = pp.SAVE_HEADER - 8
    for k, record in pots.items():
        data[body + pp.POTS_AT + k * 0x5600: body + pp.POTS_AT + (k + 1) * 0x5600] = record
    for at, level in pp.SOIL_UPGRADES:
        if upgrade == level:
            data[body + at] = 1
    for k in ornaments:
        data[body + pp.ORNAMENTS_AT + k * pp.ORNAMENT_SIZE] = 1
    (folder / f"Plant Tycoon{slot}.ldw").write_bytes(bytes(data))
    if sidecar is not None:
        side = bytearray(struct.pack("<7I", pp.SIDECAR_MAGIC, 1, 5, 15, 0x5600, 5, 0)) + bytes(5 * 15 * 0x5600)
        for (g, k), record in sidecar.items():
            at = 28 + ((g - 1) * 15 + k) * 0x5600
            side[at:at + 0x5600] = record
        (folder / "Plant Tycoon Fix Patcher Data").mkdir(exist_ok=True)
        (folder / "Plant Tycoon Fix Patcher Data" / f"Extra Greenhouses {slot}.dat").write_bytes(bytes(side))


class FakeSource:
    """Pictures for the tests without the game: every sheet a small coloured grid."""

    made: dict = {}

    def read(self, name: str):
        if name.casefold() not in self.made:
            self.made[name.casefold()] = self._make(name)
        return self.made[name.casefold()]

    def _make(self, name: str):
        for sprite_id, (file, cols, rows) in D.SPRITES.items():
            if file.casefold() == name.casefold():
                w, h = max(1, cols) * 64, max(1, rows) * 64
                if file.casefold() not in {n.casefold() for n in pp.required_files()}:
                    return None
                big = 512 if not cols else 0
                image = pi.Image(max(w, big), max(h, big))
                for i in range(0, len(image.data), 4):
                    image.data[i:i + 4] = bytes((sprite_id % 256, 120, 200, 255))
                return image.to_png()
        return None


class SaveReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.renderer = pp.Renderer(FakeSource())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def plant(self, foliage: int, flower: int, stage: str, for_sale: bool = False) -> bytes:
        plant = pp.grow_custom(foliage, flower, 1, stage)
        plant.for_sale = for_sale
        return plant.to_record()

    def test_greenhouse_1_from_the_save_and_2_to_6_from_the_sidecar(self) -> None:
        synthetic_save(self.folder, 2, {0: self.plant(14, 13, "bloom"), 7: self.plant(1, 3, "seedling", True)},
                       {(1, 4): self.plant(12, 20, "max"), (5, 14): self.plant(21, 8, "budding", True)})
        before = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        items = self.renderer.saved_items(self.folder, 2)
        self.assertEqual([(i.id, i.location) for i in items],
                         [("g0p0", "Greenhouse 1"), ("g0p7", "Greenhouse 1"), ("g1p4", "Greenhouse 2"),
                          ("g5p14", "Greenhouse 6"), ("n0p7", "Nursery"), ("n5p14", "Nursery")])
        self.assertTrue(items[0].label.startswith("Fourpetal Rare Oak (mature"))
        self.assertIn("seedling", items[1].label)
        for item in items:
            image = self.renderer.render_saved(self.folder, 2, item.id)
            self.assertIsNotNone(image.bbox())
        plan = self.renderer.plan_saved(self.folder, 2, "g1p4")
        self.assertEqual(plan, self.renderer.planner.plan(pp.Plant.from_record(self.plant(12, 20, "max")), 0, 0))
        self.assertEqual(before, {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()})   # read only

    def test_no_sidecar_and_an_unreadable_sidecar(self) -> None:
        synthetic_save(self.folder, 1, {3: self.plant(5, 5, "bloom")})
        self.assertEqual([i.id for i in self.renderer.saved_items(self.folder, 1)], ["g0p3"])
        side = self.folder / "Plant Tycoon Fix Patcher Data"
        side.mkdir()
        (side / "Extra Greenhouses 1.dat").write_bytes(b"PTXG" + bytes(100))
        self.assertEqual([i.id for i in self.renderer.saved_items(self.folder, 1)], ["g0p3"])
        self.assertTrue((side / "Extra Greenhouses 1.dat").is_file())       # never set aside or touched

    def test_formula_flowers_sit_on_the_plant(self) -> None:
        """No flower of a saved Radioactive Plant Formula plant lies outside the plant's foliage:
        each flower's centre is inside the box of the part pictures drawn, give or take 16 pixels
        (with the stock tables
        these flowers land at the sheet's (0, 0), far up and to the left of the plant)."""
        pots = {k: self.plant(f, 1 + f % 23, "formula") for k, f in enumerate(D.FORMULA_FOLIAGES[:15])}
        sidecar = {(1 + k // 15, k % 15): self.plant(f, 2 + f % 22, "formula")
                   for k, f in enumerate(D.FORMULA_FOLIAGES[15:])}
        synthetic_save(self.folder, 4, pots, sidecar)
        flower_files = {D.SPRITES[art[2]][0] for art in D.FLOWER_ART.values()}
        pot_files = {D.SPRITES[pp.POT_SPRITE][0], D.SPRITES[pp.SOIL_SPRITE][0]}
        checked = 0
        for item in self.renderer.saved_items(self.folder, 4):
            if not item.id.startswith("g"):
                continue
            self.assertTrue(self.renderer._plant(self.folder, 4, item.id)[0].formula, item.label)
            plan = self.renderer.plan_saved(self.folder, 4, item.id)
            parts = [d for d in plan if d.file not in flower_files and d.file not in pot_files]
            flowers = [d for d in plan if d.file in flower_files]
            box = (min(d.x for d in parts), min(d.y for d in parts),
                   max(d.x + (d.rect[2] - d.rect[0]) * d.scale // 100 for d in parts),
                   max(d.y + (d.rect[3] - d.rect[1]) * d.scale // 100 for d in parts))
            for d in flowers:
                cx = d.x + (d.rect[2] - d.rect[0]) * d.scale // 200
                cy = d.y + (d.rect[3] - d.rect[1]) * d.scale // 200
                m = 16              # a flower's art offset may take its centre a little past a part's edge
                self.assertTrue(box[0] - m <= cx <= box[2] + m and box[1] - m <= cy <= box[3] + m,
                                f"{item.label}: a flower at ({cx}, {cy}) outside the foliage {box}")
                checked += 1
        self.assertGreater(checked, 500)

    def test_a_stock_plant_is_not_read_as_a_formula_plant(self) -> None:
        for foliage in range(1, 24):
            for stage in ("bloom", "max"):
                self.assertFalse(pp.Plant.from_record(self.plant(foliage, 5, stage)).formula, (foliage, stage))

    def test_owned_decorations_are_listed(self) -> None:
        synthetic_save(self.folder, 6, {0: self.plant(9, 4, "bloom")}, ornaments=(0, 9, 14))
        items = [i for i in self.renderer.saved_items(self.folder, 6) if i.kind == "decoration"]
        self.assertEqual([(i.id, i.label, i.location) for i in items],
                         [("d0", "Stone Turtle", "Nursery decorations"), ("d9", "Fountain", "Nursery decorations"),
                          ("d14", "Refurbishment", "Nursery decorations")])
        self.assertEqual(self.renderer.plan_saved(self.folder, 6, "d9"), self.renderer.scenery.decoration(9))
        with self.assertRaises(pi.PictureError):
            self.renderer.plan_saved(self.folder, 6, "d3")

    def test_the_soil_upgrade_is_drawn(self) -> None:
        synthetic_save(self.folder, 3, {0: self.plant(7, 2, "bloom")}, upgrade=2)
        plan = self.renderer.plan_saved(self.folder, 3, "g0p0")
        self.assertEqual(plan[1].cell, 2 * 4 + 1)

    def test_not_a_save_and_a_missing_plant(self) -> None:
        (self.folder / "Plant Tycoon4.ldw").write_bytes(b"nope")
        with self.assertRaises(pi.PictureError):
            self.renderer.saved_items(self.folder, 4)
        with self.assertRaises(pi.PictureError):
            self.renderer.saved_items(self.folder, 9)
        synthetic_save(self.folder, 5, {0: self.plant(2, 2, "bloom")})
        self.renderer.saved_items(self.folder, 5)
        with self.assertRaises(pi.PictureError):
            self.renderer.render_saved(self.folder, 5, "g0p9")


class ChoicesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = pp.Renderer(FakeSource())

    def options(self, extras=frozenset(), spoilers=True, discovered=None) -> dict:
        subject = self.renderer.custom_choices(frozenset(extras), spoilers, discovered)[0]
        return {f.key: f for f in subject.fields}

    def test_every_foliage_flower_stage_shape_and_pot(self) -> None:
        fields = self.options()
        self.assertEqual([o.key for o in fields["foliage"].options], list(range(1, 24)))
        self.assertEqual([o.key for o in fields["flower"].options], list(range(1, 38)))
        self.assertEqual([o.key for o in fields["stage"].options], ["seed", "sprout", "seedling", "growing", "budding", "bloom", "max", "formula"])
        self.assertEqual([f.key for f in self.renderer.custom_choices(frozenset(), True, None)[0].fields][:2],
                         ["flower", "foliage"])
        self.assertEqual([o.key for o in fields["state"].options], ["alive", "dead"])
        self.assertEqual(self.renderer.plan_custom({"subject": "plant", "foliage": 14, "flower": 13, "stage": "dead"}),
                         self.renderer.plan_custom({"subject": "plant", "foliage": 14, "flower": 13, "stage": "bloom",
                                                    "state": "dead"}))
        dead = self.renderer.plan_custom({"subject": "plant", "foliage": 14, "flower": 13, "stage": "budding",
                                          "state": "dead"})
        self.assertTrue(dead and not any("flower" in d.file.casefold() or "fruit" in d.file.casefold() for d in dead))
        self.assertTrue(any(d.file.endswith("_dead.png") for d in dead))
        self.assertEqual(len(fields["shape"].options), D.SHAPE_COUNT)
        self.assertEqual([o.key for o in fields["pot"].options], [-1, 0, 1, 2, 3, 4, 5, 6])

    def test_unused_flowers_are_always_offered(self) -> None:
        """With or without the setting found, the 14 Unused Flowers are offered, marked."""
        self.assertEqual(self.options()["flower"].options, self.options({"new_flowers"})["flower"].options)
        flowers = self.options()["flower"].options
        self.assertEqual([o.key for o in flowers], list(range(1, 38)))
        self.assertTrue(all(o.patcher for o in flowers[23:]) and not any(o.patcher for o in flowers[:23]))
        self.assertEqual(flowers[23].label, "Nightingale")

    def test_spoilers_off_offers_only_discovered_parts(self) -> None:
        fields = self.options({"new_flowers"}, spoilers=False, discovered={(14, 13), (1, 3), (2, 30)})
        self.assertEqual([o.key for o in fields["foliage"].options], [1, 2, 14])
        self.assertEqual([o.key for o in fields["flower"].options], [3, 13, 30])
        everything = self.options(spoilers=False, discovered=None)        # no save: nothing to hide by
        self.assertEqual(len(everything["foliage"].options), 23)
        spoilers = self.options(spoilers=True, discovered={(1, 1)})
        self.assertEqual(len(spoilers["foliage"].options), 23)

    def test_decorations_bugs_and_pots(self) -> None:
        subjects = {s.key: s for s in self.renderer.custom_choices(frozenset(), True, None)}
        self.assertEqual(list(subjects), ["plant", "unused", "decoration", "bug", "pot", "items", "art", "screens"])
        parts = [o.key for o in subjects["unused"].fields[0].options]
        self.assertEqual(len(parts), 12)
        for key in parts:
            for state in ("alive", "dead"):
                plan = self.renderer.plan_custom({"subject": "unused", "part": key, "state": state})
                self.assertEqual(len(plan), 1, key)
        with self.assertRaises(pi.PictureError):
            self.renderer.plan_custom({"subject": "unused", "part": "2:0"})
        self.assertEqual(len(subjects["decoration"].fields[0].options), 15)
        self.assertEqual([len(f.options) for f in subjects["bug"].fields], [48, 7])
        self.assertEqual([len(f.options) for f in subjects["pot"].fields], [7, 3, 3, 2])
        for spec in ({"subject": "decoration", "ornament": 9}, {"subject": "bug", "bug": 47, "frame": 5},
                     {"subject": "pot", "style": 6, "soil": "planted", "level": 2, "wet": True}):
            self.assertIsNotNone(self.renderer.render_custom(spec).bbox())
        for spec in ({"subject": "decoration", "ornament": 15}, {"subject": "bug", "bug": 48},
                     {"subject": "pot", "style": 7}, {"subject": "pot", "soil": "mud"}):
            with self.assertRaises(pi.PictureError):
                self.renderer.render_custom(spec)

    def test_a_bad_spec_is_said_in_words(self) -> None:
        for spec in ({"subject": "fish"}, {"subject": "plant", "foliage": 0}, {"subject": "plant", "flower": 99},
                     {"subject": "plant", "stage": "huge"}, {"subject": "plant", "foliage": "x"}):
            with self.assertRaises(pi.PictureError):
                self.renderer.render_custom(spec)

    def test_the_same_choices_give_the_same_picture(self) -> None:
        spec = {"subject": "plant", "foliage": 11, "flower": 7, "stage": "max", "shape": 4, "pot": 2}
        self.assertEqual(self.renderer.render_custom(spec), self.renderer.render_custom(dict(spec)))
        other = dict(spec, shape=5)
        self.assertNotEqual(self.renderer.plan_custom(spec), self.renderer.plan_custom(other))


class PngTests(unittest.TestCase):
    def test_a_custom_plant_saves_as_a_transparent_png(self) -> None:
        renderer = pp.Renderer(FakeSource())
        image = renderer.render_custom({"subject": "plant", "foliage": 3, "flower": 2, "stage": "bloom", "shape": 1, "pot": -1})
        with tempfile.TemporaryDirectory() as tmp:
            path = pi.save_png(image, Path(tmp) / "plant.png", scale=2)
            back = pi.Image.from_png(path.read_bytes())
        self.assertEqual(back.width, (image.cropped().width) * 2)
        self.assertEqual(back.pixel(0, 0)[3], 0)                       # transparent margin
        self.assertTrue(any(back.data[3::4]))


@needs_art
class RealArtTests(unittest.TestCase):
    def test_every_required_picture_is_in_the_game(self) -> None:
        renderer = pp.load(VANILLA)
        self.assertEqual(renderer.problem, "")
        for name in pp.required_files():
            self.assertTrue(renderer.sheets.has(name), name)

    def test_renders_with_the_game_art(self) -> None:
        renderer = pp.load(VANILLA)
        for stage, _label in pp.STAGES:
            image = renderer.render_custom({"subject": "plant", "foliage": 13, "flower": 13, "stage": stage})
            self.assertIsNotNone(image.bbox())


if __name__ == "__main__":
    unittest.main()
