"""Picture Studio's Items tab (src/pictures_fish_items.py, src/pictures_plant_items.py): every item
of both games, drawn as the game draws it.

* The numbers are the games': Fish Tycoon's store records (0x457EF0), sprite table (0x4552F0),
  supply icons and cursors (0x427F4B..0x427FEC), the food slot by research level (0x420A02),
  the tank effects (0x410AE0 run in Unicorn), the store's pointed-at and picked scales (0x408030
  and 0x4271F0 run in Unicorn); Plant Tycoon's store shelves (0x447D40), Tools box (0x44DD70) and
  mouse pictures (0x429267..), and both games' item names from their string tables.
* A handful of pictures are pinned: the Studio's render must be, pixel for pixel, the
  composition of the game's own art the game draws (sheet, cell, offsets, order, alpha).
* The Moray Eel (DS Store Items): out of its home, in its home (draw_home: the back layer, the
  rock, the front layer over the rock's centred shadow), and its home alone, against the DLL's
  own numbers.

The checks against the executables need the vanilla games (and Unicorn / capstone); they skip
without.
"""

from __future__ import annotations

from pathlib import Path
import re
import struct
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import picture_image as pi  # noqa: E402
import pictures_fish as pf  # noqa: E402
import pictures_fish_items as fi  # noqa: E402
import pictures_plant as pp  # noqa: E402
import pictures_plant_items as pit  # noqa: E402

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
FISH = VANILLA / "Fish Tycoon"
PLANT = VANILLA / "Plant Tycoon"

try:
    import fish_draw_emulator as fde
    UNICORN = fde.available()
except ImportError:                                   # no Unicorn
    fde = None
    UNICORN = False
try:
    import capstone
except ImportError:                                   # no capstone
    capstone = None


def compose(pieces) -> pi.Image:
    """(picture, x, y[, alpha]) drawn in order on a canvas just big enough, cut to its pixels."""
    left = min(x for _p, x, y, *_a in pieces)
    top = min(y for _p, x, y, *_a in pieces)
    right = max(x + p.width for p, x, y, *_a in pieces)
    bottom = max(y + p.height for p, x, y, *_a in pieces)
    canvas = pi.Image(right - left, bottom - top)
    for piece, x, y, *alpha in pieces:
        canvas.draw(piece, x - left, y - top, alpha[0] if alpha else 255)
    return canvas.cropped(0)


def cell(image: pi.Image, cols: int, rows: int, k: int) -> pi.Image:
    return image.sub(*_rect(image, cols, rows, k))


def _rect(image, cols, rows, k):
    l, t, r, b = pi.cell_rect(image.width, image.height, cols, rows, k)
    return l, t, r - l, b - t


def same(test, a: pi.Image, b: pi.Image, label: str) -> None:
    test.assertEqual((a.width, a.height), (b.width, b.height), label)
    test.assertEqual(bytes(a.data), bytes(b.data), label)


def disassemble(exe: Path, start: int, end: int) -> list:
    data = exe.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    base = struct.unpack_from("<I", data, pe + 0x34)[0]
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 0x14)[0]
    for k in range(sections):
        at = pe + 0x18 + opt + 0x28 * k
        vsize, rva, raw_size, raw = struct.unpack_from("<4I", data, at + 8)
        if rva <= start - base < rva + max(vsize, raw_size):
            off = raw + start - base - rva
            md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
            return [i for i in md.disasm(data[off:off + end - start], start)]
    raise AssertionError(f"{start:#x} is in no section")


def game_strings(exe: Path) -> dict:
    """The exe's string table entries: key (eShortDescX ...) -> its English text."""
    data = exe.read_bytes()
    return {m.group(2).decode(): m.group(1).decode("latin-1").strip()
            for m in re.finditer(rb"([\x20-\x7e\n]{2,90})\x00+(e[A-Z]\w+)\x00", data)}


# ------------------------------------------------------------------ Fish Tycoon

class FishArt:
    def __init__(self) -> None:
        self.zip = zipfile.ZipFile(FISH / "Assets" / "ft.dat")
        self.names = {n.casefold(): n for n in self.zip.namelist() if not n.startswith("__MACOSX")}

    def image(self, name: str) -> pi.Image:
        if name.casefold() in self.names:
            return pi.decode_png(self.zip.read(self.names[name.casefold()]))
        return pi.decode_png(pf.patcher_art()[name].read_bytes())


class FishItemCatalogTests(unittest.TestCase):
    def test_every_item_has_its_pictures_and_marks(self) -> None:
        self.assertEqual(len(fi.ITEMS), len(fi.BY_KEY), "keys are unique")
        for item in fi.ITEMS:
            self.assertIn(item.category, fi.CATEGORIES)
            self.assertTrue(fi.views(item), item.name)
            self.assertFalse(item.patcher and item.unused, item.name)
        unused = {i.name for i in fi.ITEMS if i.unused}
        self.assertEqual(len(unused), 7, unused)
        stock_store = sorted(i.store for i in fi.ITEMS if i.store is not None)
        self.assertEqual(stock_store, list(range(26)), "every one of the store's 26 items")
        patcher = {i.key for i in fi.ITEMS if i.patcher}
        self.assertTrue({"eggs_exotic", "rgh", "revival", "clonafish", "muta_fin", "muta_body", "puffer", "ray",
                         "eel", "time_warp", "add_money", "auto_feeder", "auto_healer", "supply_slots"} <= patcher)
        self.assertEqual(set(fi.patcher_files()) - set(pf.patcher_art()), set(), "the patcher's art ships")

    def test_the_studio_offers_them_by_category(self) -> None:
        r = pf.FishRenderer(None)
        items = next(s for s in r.custom_choices(frozenset(), False, {(0, 0)}) if s.key == "items")
        self.assertEqual([f.key for f in items.fields], ["category", "item", "view"])
        refined = r.refine_choices("items", {"category": "Ornaments", "item": None})
        self.assertIn("Yellow coral", [o.label for o in refined["item"]])
        self.assertTrue(next(o for o in refined["item"] if o.label == "Yellow coral").unused)
        views = [o.key for o in r.refine_choices("items", {"category": "Fish eggs", "item": "eggs_rare"})["view"]]
        self.assertEqual(views[:3], ["store", "hover", f"picked{fi.PICKED_PULSE[0]}"])
        self.assertIn("slot", views)
        self.assertIn("tank15", views)
        batch = r.custom_batch("items")
        self.assertEqual(len(batch), sum(len(fi.views(i)) for i in fi.ITEMS))
        self.assertIsNone(r.custom_batch("fish"), "the Fish tab has too many pictures for one batch")


@unittest.skipUnless(UNICORN and (FISH / "Assets" / "ft.dat").is_file(), "the vanilla Fish Tycoon and Unicorn")
class FishItemsAreTheGames(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.art = FishArt()
        cls.emu = fde.FishDrawEmulator({})
        cls.renderer = pf.load(FISH)

    def mem32(self, address: int, signed: bool = True) -> int:
        return self.emu.emu.read32(address, signed=signed)

    def test_store_records_are_the_games(self) -> None:
        for k in range(26):
            at = 0x457EF0 + k * 0x34
            self.assertEqual(self.mem32(at + 0x10), k)
            (ix, iy), shadow, file = fi.STORE[k]
            self.assertEqual((self.mem32(at + 0x18), self.mem32(at + 0x1C)), (ix, iy), k)
            sx, sy = self.mem32(at + 0x20), self.mem32(at + 0x24)
            self.assertEqual(None if sx == -1 else (sx, sy), shadow, k)
            sprite = self.mem32(at + 0x28)
            self.assertEqual(sprite, fi.STORE_SPRITES[k])
            self.assertEqual(self.emu.table_entry(sprite), (file, 0, 0), k)
        self.assertEqual(self.mem32(0x457EF0 + 26 * 0x34), -1, "26 records, then the end")
        self.assertEqual(self.emu.table_entry(0x8D)[0], fi.SHADOW_FILE)
        for sprite, entry in fi.SPRITE_FILES.items():
            self.assertEqual(self.emu.table_entry(sprite), entry, hex(sprite))

    def test_unused_art_is_in_the_game_but_in_no_sprite_record(self) -> None:
        table = {self.emu.table_entry(k)[0].casefold() for k in range(197)}
        for item in fi.ITEMS:
            if item.unused:
                self.assertIn(item.whole.casefold(), self.art.names, item.name)
                self.assertNotIn(item.whole.casefold(), table, item.name)
            elif not item.patcher:
                for name in (item.icon, item.cursor[0] if item.cursor else None):
                    if name:
                        self.assertIn(name.casefold(), table, item.name)

    @unittest.skipUnless(capstone, "capstone")
    def test_supply_icons_and_cursors_are_the_games(self) -> None:
        pushes, found = [], {}
        for ins in disassemble(fde.EXE, 0x427F4B, 0x427FEF):
            if ins.mnemonic == "push":
                pushes.append(int(ins.op_str, 0))
            elif ins.mnemonic == "call":
                self.assertEqual(int(ins.op_str, 0), 0x427540)
                cursor, icon, item, slot = pushes[-4:]
                found[item] = (slot, icon, cursor)
                pushes = []
        self.assertEqual(found, fi.STOCK_SUPPLY)
        for item, (_slot, icon, cursor) in fi.STOCK_SUPPLY.items():
            entry = next(i for i in fi.ITEMS if i.store == item)
            self.assertEqual(entry.icon, fi.SPRITE_FILES[icon][0])
            self.assertEqual(entry.cursor, fi.SPRITE_FILES[cursor])

    @unittest.skipUnless(capstone, "capstone")
    def test_food_follows_the_research_level(self) -> None:
        writes = [(int(i.op_str.split("+ ")[1].split("]")[0], 0), int(i.op_str.split(", ")[1], 0))
                  for i in disassemble(fde.EXE, 0x420A02, 0x420A5D) if i.mnemonic == "mov" and "], 0x" in i.op_str]
        self.assertEqual(writes, [(0x2C4, fi.FOOD[1][0]), (0x2C4, fi.FOOD[3][0]), (0x2C8, fi.FOOD[3][1]),
                                  (0x2C4, fi.FOOD[2][0]), (0x2C8, fi.FOOD[2][1])])
        new_game = [i.op_str for i in disassemble(fde.EXE, 0x419982, 0x419996)]
        self.assertEqual(new_game, ["dword ptr [ecx + 0x2c4], 0x78", "dword ptr [ecx + 0x2c8], 0x6e"])
        def push8(va):                       # the effect type pushed for 0x413B00 at va
            op, value = bytes(self.emu.emu.uc.mem_read(va, 2))
            self.assertEqual(op, 0x6A, hex(va))
            return value
        self.assertEqual([push8(0x420BF3), push8(0x420C04), push8(0x420C15)],
                         [fi.FOOD[1][2], fi.FOOD[2][2], fi.FOOD[3][2]], "food, by research level")
        self.assertEqual({push8(0x420C56), push8(0x420E45)}, {3}, "medicines (slot 1) and chemicals (slot 2)")
        self.assertEqual({push8(0x421392), push8(0x421461), push8(0x421534)}, {4}, "the three eggs")

    def test_tank_effects_are_the_games(self) -> None:
        emu = self.emu.emu
        for kind, (sprite, file, cols, rows, frames, alpha) in fi.EFFECTS.items():
            base = emu.alloc(0x42 * 0x40 + 0x40)
            emu.uc.mem_write(base, bytes(0x42 * 0x40 + 0x40))
            emu.call(0x410AE0, kind, 100, 200, ecx=base)
            self.assertEqual(emu.read32(base + 4), sprite, kind)
            self.assertEqual(self.emu.table_entry(sprite), (file, cols, rows), kind)
            self.assertEqual(emu.read32(base), frames - 1, f"type {kind}: frames 0..last")
            self.assertEqual(emu.read32(base + 0x3C), alpha, kind)
            self.assertEqual(emu.uc.mem_read(base + 0x30, 1)[0], 1, "drawn with its alpha (0x408AB0)")

    def test_the_picked_pulse_is_the_games(self) -> None:
        from unicorn import x86_const as X
        import store_emulator as se
        emu = self.emu.emu
        impl = emu.alloc(0x40)
        emu.write32(impl, 3)
        emu.write32(impl + 4, 7)                           # a new pick: the angle starts again
        emu.uc.mem_write(0x458470, struct.pack("<d", -360.0))
        out = []
        for _ in range(72):
            emu.uc.reg_write(X.UC_X86_REG_ESP, se.STACK + se.STACK_SIZE - 0x1000)
            emu.uc.reg_write(X.UC_X86_REG_ECX, impl)
            emu.uc.reg_write(X.UC_X86_REG_FPCW, 0x027F)
            emu.uc.emu_start(0x4271F0, 0x427239, count=100000)
            eax = emu.uc.reg_read(X.UC_X86_REG_EAX)
            out.append(0x50 - (eax - (1 << 32) if eax & 0x80000000 else eax))
        self.assertEqual(out, list(fi.PICKED_CYCLE) * 2)
        self.assertEqual(fi.PICKED_PULSE, tuple(sorted(set(out), reverse=True)))

    def test_store_draws_are_the_games(self) -> None:
        """0x407D60 (at rest) and 0x408030 (pointed at, picked) on the item's sprite: the blit's
        place, rectangle and scale are the plan's."""
        for key in ("hormone", "eggs_rare", "ship", "research_food"):
            item = fi.BY_KEY[key]
            (ix, iy), shadow, file = fi.STORE[item.store]
            sprite = fi.STORE_SPRITES[item.store]
            image = self.art.image(file)
            self.emu.sizes[("image", sprite)] = (image.width, image.height)
            self.emu.sizes[("image", 0x8D)] = (self.art.image(fi.SHADOW_FILE).width,
                                               self.art.image(fi.SHADOW_FILE).height)
            wrapper = self.emu.emu.call(fde.GET_IMAGE, sprite)
            for view in ("store", "hover", f"picked{fi.PICKED_PULSE[0]}", f"picked{fi.PICKED_PULSE[-1]}"):
                plan = fi.plan(item, view)
                call = plan[-1]
                self.emu.blits = []
                if call.scale == 100:
                    self.emu.emu.call(0x407D60, wrapper, ix, iy, ecx=self.emu.gfx)
                else:
                    self.emu.emu.call(0x408030, wrapper, ix, iy, call.scale, 1, 0, ecx=self.emu.gfx)
                blit = self.emu.blits[-1]
                _p, dx, dy = pi.scaled_cell(image, (0, 0, image.width, image.height), call.scale)
                self.assertEqual((blit.x, blit.y, blit.src, round(blit.scale * 100)),
                                 (call.x + dx, call.y + dy, (0, 0, image.width, image.height), call.scale),
                                 (key, view))
                if view == "store":
                    self.assertEqual([(c.file, c.x, c.y) for c in plan[:-1]],
                                     [(fi.SHADOW_FILE, *shadow)] if shadow else [])

    def render(self, key: str, view: str) -> pi.Image:
        return self.renderer.render_custom({"subject": "items", "item": key, "view": view}).cropped(0)

    def test_pinned_pictures(self) -> None:
        art = self.art
        same(self, self.render("ick", "store"),
             compose([(art.image("ITEM_SHADOW.png"), 64, 85), (art.image("ITEM_ICK.png"), 64, 84)]), "Ick, at rest")
        gh = art.image("ITEM_growthhormone.png")
        piece, dx, dy = pi.scaled_cell(gh, (0, 0, gh.width, gh.height), 120)
        same(self, self.render("hormone", "hover"), compose([(piece, dx, dy)]), "Growth Hormone, pointed at")
        same(self, self.render("hormone", "slot"), art.image("TOOL_GROWTHHORMONE.png").cropped(0), "its slot icon")
        same(self, self.render("hormone", "hand"), art.image("TOOL_dropper4.png").cropped(0), "its dropper")
        same(self, self.render("food3", "hand"),
             cell(art.image("ANIM_TINYSHRIMP_Grid.png"), 16, 2, 0).cropped(0), "live food on the mouse")
        same(self, self.render("food2", "tank7"),
             compose([(cell(art.image("pellets_Grid.png"), 16, 1, 7), 0, 0, 175)]), "pellets falling")
        same(self, self.render("orange_beaker", "whole"), art.image("item_orangebeaker.png").cropped(0), "unused")
        same(self, self.render("rgh", "store"), art.image("ITEM_RADIOACTIVE_GROWTHHORMONE.png").cropped(0),
             "DS Store Items: no shadow on its page")
        same(self, self.render("eggs_exotic", "slot"), art.image("TOOL_FISHEGGS_EXOTIC.png").cropped(0), "patcher")
        same(self, self.render("supply_slots", "store"), art.image("ITEM_EXTRA_SUPPLY_SLOTS.png").cropped(0),
             "Extra Supply Slots")


class MorayEelTests(unittest.TestCase):
    """The owner's three eel pictures: out of its home (swimming), in its home, its home alone."""

    @classmethod
    def setUpClass(cls) -> None:
        c = (ROOT / "native" / "ftfp_ds_store" / "ftfp_ds_store.c").read_text(encoding="utf-8")
        h = (ROOT / "native" / "ftfp_ds_store" / "store_data.h").read_text(encoding="utf-8")
        cls.defs = {m.group(1): int(m.group(2), 0) for m in
                    re.finditer(r"#define (\w+) (0x[0-9A-Fa-f]+|\d+)u?\b", c + "\n" + h)}
        cls.c = c

    def test_the_numbers_are_the_dlls(self) -> None:
        d = self.defs
        self.assertEqual((pf.HOME_IDLE, pf.HOME_ACTION), (d["HOME_IDLE"], d["HOME_ACTION"]))
        self.assertEqual(pf.HOME_IDLE + pf.HOME_ACTION, d["HOME_FRAMES"])
        self.assertEqual((pf.ROCK_H, pf.ROCK_SINK), (d["ROCK_H"], d["ROCK_SINK"]))
        self.assertEqual(pf.STORE_SHEETS[pf.SPR_HOME_BACK], ("DS_EEL_HOME_BACK_Grid.png", d["HOME_COLS"],
                                                             d["HOME_FRAMES"] // d["HOME_COLS"]))
        # draw_home_backs (shadow, back layer) before the stock ornaments, draw_home_fronts after.
        stub = self.c[self.c.index("static void stub_ornaments"):]
        self.assertLess(stub.index("draw_home_backs"), stub.index("k_draw_ornaments"))
        self.assertLess(stub.index("k_draw_ornaments"), stub.index("draw_home_fronts"))
        self.assertIn("*I(o, O_X) + *I(o, O_W) / 2 - SHADOW_W / 2, *I(o, O_Y) + *I(o, O_H) - 25", self.c)

    def test_listed_under_the_creatures_and_saved_by_save_all(self) -> None:
        r = pf.FishRenderer(None)
        creatures = r.custom_choices(frozenset(), True, None)[1]
        self.assertEqual(creatures.key, "creature")
        keys = [o.key for o in creatures.fields[0].options]
        self.assertTrue({"eel", "eel_home", "eel_rock"} <= set(keys))
        self.assertEqual(len(next(f for f in creatures.fields if f.key == "home_frame").options), 32)
        batch = r.custom_batch("creature")
        eel = [spec for _f, _n, spec in batch if str(spec["creature"]).startswith("eel")]
        self.assertEqual(sum(1 for s in eel if s["creature"] == "eel_home"), 32, "every home frame")
        self.assertEqual(sum(1 for s in eel if s["creature"] == "eel_rock"), 1)
        self.assertEqual(sum(1 for s in eel if s["creature"] == "eel"), 18, "3 ways of facing x 6 frames")

    def test_the_eel_and_its_home_are_drawn_as_draw_home_does(self) -> None:
        art = {n: pi.decode_png(p.read_bytes()) for n, p in pf.patcher_art().items()}
        renderer = pf.load(FISH) if (FISH / "Assets" / "ft.dat").is_file() else None
        if renderer is None:
            self.skipTest("the vanilla Fish Tycoon (its shadow picture)")
        shadow = FishArt().image("TANK_OBJECT_SHADOW.png")
        rock = art["DS_EEL_ROCK.png"]
        floor = self.defs["ROCK_H"] - self.defs["ROCK_SINK"]
        sx, sy = self.defs["ROCK_W"] // 2 - pf.SHADOW_W // 2, floor - 25
        self.assertEqual(shadow.width, pf.SHADOW_W)
        cols, rows = self.defs["HOME_COLS"], self.defs["HOME_FRAMES"] // self.defs["HOME_COLS"]
        for frame in (0, 6, 12, 13, 20, 31):
            back = cell(art["DS_EEL_HOME_BACK_Grid.png"], cols, rows, frame)
            front = cell(art["DS_EEL_HOME_FRONT_Grid.png"], cols, rows, frame)
            got = renderer.render_custom({"subject": "creature", "creature": "eel_home", "home_frame": frame})
            same(self, got.cropped(0), compose([(shadow, sx, sy), (back, 0, 0), (rock, 0, 0), (front, 0, 0)]),
                 f"in its home, frame {frame + 1}")
        got = renderer.render_custom({"subject": "creature", "creature": "eel_rock"})
        same(self, got.cropped(0), compose([(shadow, sx, sy), (rock, 0, 0)]), "its home alone")
        swimming = renderer.plan_custom({"subject": "creature", "creature": "eel", "facing": "left", "frame": 2})
        self.assertEqual([(c.file, c.cell) for c in swimming], [("DS_EEL_Grid.png", 2)],
                         "out of its home: its swimming sheet (companion_sheet), as tests/test_pictures_fish.py proves")


# ------------------------------------------------------------------ Plant Tycoon

class PlantArt:
    def __init__(self) -> None:
        self.files = {p.name.casefold(): p for p in (PLANT / "Images").iterdir()}

    def image(self, name: str) -> pi.Image:
        path = pp.patcher_art().get(name) or self.files[name.casefold()]
        return pi.decode_png(path.read_bytes())


class PlantItemCatalogTests(unittest.TestCase):
    def test_every_item_has_its_pictures(self) -> None:
        self.assertEqual(len(pit.ITEMS), len(pit.BY_KEY))
        counts = {c: sum(1 for i in pit.ITEMS if i.category == c) for c in pit.CATEGORIES}
        self.assertEqual(counts, {"Seeds": 92 + 23, "Chemicals": 9 + 6, "Tools": 15, "Nursery ornaments": 15,
                                  "Pots": 7, "Store Upgrades and Items": 8})
        for item in pit.ITEMS:
            self.assertTrue(pit.views(item), item.name)
        self.assertEqual(set(pit.patcher_files()) - set(pp.patcher_art()), set())
        self.assertFalse(any(i.unused for i in pit.ITEMS), "Plant Tycoon has no unused item art")

    def test_the_studio_offers_them_by_category(self) -> None:
        r = pp.Renderer(None)
        items = next(s for s in r.custom_choices(frozenset(), True, None) if s.key == "items")
        self.assertEqual([f.key for f in items.fields], ["category", "item", "view"])
        tools = r.refine_choices("items", {"category": "Tools"})
        self.assertEqual(tools["item"][0].label, "Common Soil")
        views = [o.key for o in r.refine_choices("items", {"category": "Tools", "item": "toolshears2"})["view"]]
        self.assertEqual(views, ["shelf", "owned", "tool", "tool_use"])
        views = [o.key for o in r.refine_choices("items", {"category": "Chemicals", "item": "chem36"})["view"]]
        self.assertEqual(views, ["shelf", "tray", "pour"])


@unittest.skipUnless((PLANT / "Plant Tycoon.exe").is_file(), "the vanilla Plant Tycoon")
class PlantItemsAreTheGames(unittest.TestCase):
    EXE = PLANT / "Plant Tycoon.exe"

    @classmethod
    def setUpClass(cls) -> None:
        cls.art = PlantArt()
        cls.renderer = pp.load(PLANT)

    def test_names_are_the_games(self) -> None:
        s = game_strings(self.EXE)
        self.assertEqual(pit.CHEMICAL_NAMES, tuple(s[f"eShortDesc{k}"] for k in (
            "PlantFood", "Vitamins", "Insecticide", "BioFood", "Rescue", "Fertility", "InstaGrow", "Mutation", "Dew")))
        for k, name in enumerate(pit.CHEMICAL_NAMES):          # the tray's names, row k = eChemicalName k + 1
            self.assertTrue(name.casefold().startswith(s[f"eChemicalName{k + 1}"].casefold()), name)
        for what, key in (("soil", "Soil"), ("water", "Water"), ("shears", "Shears"), ("net", "Net"), ("box", "Box")):
            names = dict(pit.TOOL_COLUMNS)[what]
            self.assertEqual(names, tuple(s[f"eShortDesc{key}{n}"] for n in (1, 2, 3)))
        self.assertEqual(pp.ORNAMENT_NAMES, tuple(s[f"eShortDesc{k}"] for k in (
            "Turtle", "Sundial", "WeatherVane", "BugZap", "Owl", "Buddha", "BirdHouse", "Cherub", "Bench",
            "Fountain", "Sign", "Fence", "Gate", "CashReg", "Paint")))

    @unittest.skipUnless(capstone, "capstone")
    def test_the_store_shelves_are_the_games(self) -> None:
        code = disassemble(self.EXE, 0x447D40, 0x447FF8)
        text = [f"{i.mnemonic} {i.op_str}" for i in code]
        sheets = [int(i.op_str, 0) for i in code if i.mnemonic == "push" and i.op_str in
                  ("0x25", "0x2e", "0xb0", "0xb1", "0xb2", "0xb3")]
        self.assertEqual(sheets, [pit.SHADOW, pit.SEEDS, pit.SHADOW, pit.TOOLS, pit.TICK, pit.SHADOW,
                                  pit.CHEMICALS, pit.SHADOW, pit.ORNAMENTS, pit.TICK])
        # the offsets, in the order the shelves draw them: seeds' shadow, tools' shadow and tick,
        # chemicals' shadow, ornaments' shadow and tick
        wanted = ["lea edx, [ebp + 5]", "lea eax, [edi + 5]",
                  "lea eax, [ebx + 0x1e]", "lea eax, [edi + 0x19]", "lea eax, [ebx + 0x16]", "lea ecx, [edi + 0x13]",
                  "lea eax, [ebp + 0x1e]", "lea edx, [edi + 0x19]", "add ebx, 2",
                  "lea eax, [ebx + 0xa]", "lea eax, [edi + 5]", "lea eax, [ebx + 2]", "lea ecx, [edi - 1]"]
        at = 0
        for line in text:
            if at < len(wanted) and line == wanted[at]:
                at += 1
        self.assertEqual(at, len(wanted), f"missing {wanted[at:at + 1]}")
        self.assertEqual(pit.SHELF["seed"], ((5, 5), None))
        self.assertEqual(pit.SHELF["tool"], ((0x19, 0x1E), (0x13, 0x16)))
        self.assertEqual(pit.SHELF["chemical"][0], (0x19, 0x1E))
        self.assertEqual(pit.SHELF["ornament"], ((5, 0xA), (-1, 2)))
        self.assertEqual(pp.sprite(pit.SHADOW)[0], "peep_shadow1.png")
        for sheet in (pit.SHADOW, pit.TICK):
            self.assertIn("4207f0", " ".join(t for t in text if "call" in t))
        for k, (name, cols, rows) in ((pit.TOOLS, ("Tools_Grid.png", 5, 3)), (pit.CHEMICALS, ("Chemicals_Grid.png", 2, 9)),
                                      (pit.ORNAMENTS, ("Ornaments_Grid.png", 5, 3))):
            self.assertEqual(pp.sprite(k), (name, cols, rows))

    @unittest.skipUnless(capstone, "capstone")
    def test_tools_and_bottles_in_the_box_and_on_the_mouse(self) -> None:
        box = [f"{i.mnemonic} {i.op_str}" for i in disassemble(self.EXE, 0x44DD70, 0x44DE9A)]
        for sheet in pit.HAND_SHEETS.values():
            at = box.index(f"push {hex(sheet)}")
            self.assertEqual(box[at - 1], "push eax")
            self.assertEqual(box[at - 2], "add eax, eax", "the Tools box: frame 2 x level")
        mouse = [f"{i.mnemonic} {i.op_str}" for i in disassemble(self.EXE, 0x429267, 0x4295BB)]
        for sheet in pit.HAND_SHEETS.values():
            spots = [k for k, line in enumerate(mouse) if line == f"push {hex(sheet)}"]
            frames = {next(mouse[j] for j in range(k - 1, k - 5, -1) if "eax + eax" in mouse[j] or "add eax, eax" in mouse[j])
                      for k in spots}
            self.assertEqual(len(spots), 2, hex(sheet))
            self.assertTrue(any("eax + eax + 1" in f for f in frames), f"{sheet:#x}: in use, 2 x level + 1")
            self.assertIn("add eax, eax", frames)
        self.assertIn("lea ecx, [eax + eax - 0x35]", mouse, "a bottle pouring: 2 id - 53")
        self.assertIn("lea ecx, [eax + eax - 0x36]", mouse, "a bottle held: 2 id - 54")

    @unittest.skipUnless(capstone, "capstone")
    def test_the_48_bugs_are_the_games(self) -> None:
        """The bug names by the game's bug number: the name switch 0x418940 (jump table 0x418DA4),
        each case copying its name string; the Collections screen draws leaf k for bug k (0x4184BB)."""
        data = self.EXE.read_bytes()
        table = disassemble(self.EXE, 0x418940, 0x41894D)
        self.assertEqual(table[1].op_str, "eax, 0x2f", "48 bugs")
        names = []
        for k in range(48):
            target = struct.unpack_from("<I", self._bytes(0x418DA4 + 4 * k, 4))[0]
            push = next(i for i in disassemble(self.EXE, target, target + 16) if i.mnemonic == "push")
            at = int(push.op_str, 0)
            text = self._bytes(at, 40)
            names.append(text[:text.index(b"\0")].decode("latin-1"))
        self.assertEqual(tuple(names), pp.BUG_NAMES)
        del data
        leaf = [f"{i.mnemonic} {i.op_str}" for i in disassemble(self.EXE, 0x418490, 0x4184CD)]
        self.assertIn("push esi", leaf)
        self.assertIn("push 0xdb", leaf)
        self.assertEqual(pp.sprite(pp.LEAF_SPRITE), ("collectionLeafGrid.png", 8, 6))
        art = self.art.image("collectionLeafGrid.png")
        got = self.renderer.render_custom({"subject": "bug", "bug": 30, "frame": "leaf"}).cropped(0)
        same(self, got, compose([(cell(art, 8, 6, 30), 0, 0)]), "the Ghost Dragonfly's leaf")
        bugs = self.renderer.custom_batch("bug")
        self.assertEqual(len(bugs), 48 * 7)
        self.assertEqual(bugs[0][0], ("Butterflies and moths", "1. Blue Butterfly"))
        self.assertEqual(bugs[-1][0], ("Spiders", "48. Golden Spider"))

    def _bytes(self, va: int, n: int) -> bytes:
        data = self.EXE.read_bytes()
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        base = struct.unpack_from("<I", data, pe + 0x34)[0]
        opt = struct.unpack_from("<H", data, pe + 0x14)[0]
        for k in range(struct.unpack_from("<H", data, pe + 6)[0]):
            vsize, rva, raw_size, raw = struct.unpack_from("<4I", data, pe + 0x18 + opt + 0x28 * k + 8)
            if rva <= va - base < rva + max(vsize, raw_size):
                return data[raw + va - base - rva:raw + va - base - rva + n]
        raise AssertionError(hex(va))

    def test_the_patchers_shelf_numbers(self) -> None:
        c = (ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c").read_text(encoding="utf-8")
        self.assertIn("SHEET_CHEMICALS, GREENHOUSE_FRAME, 404, 50, 1.0f,\n      408, 80, 403, 72", c)
        self.assertEqual(pit.SHELF["greenhouse"], ((408 - 404, 80 - 50), (403 - 404, 72 - 50)))
        frames = {k: f for k, _n, _s, f, _shelf in pit.PATCHER_UPGRADES}
        for define, key in (("WARP_FRAME", "time_warp"), ("MONEY_FRAME", "add_money"),
                            ("GREENHOUSE_FRAME", "extra_greenhouse"), ("NURSERY_FRAME", "extra_nursery"),
                            ("BOX_FRAME", "extra_seed_box")):
            self.assertEqual(int(re.search(rf"#define {define} (\d+)", c).group(1)), frames[key], define)

    def render(self, key: str, view: str) -> pi.Image:
        return self.renderer.render_custom({"subject": "items", "item": key, "view": view}).cropped(0)

    def test_pinned_pictures(self) -> None:
        art = self.art
        shadow, tick = art.image("peep_shadow1.png"), art.image("CHECKMARK.png")
        tools = art.image("Tools_Grid.png")
        same(self, self.render("toolwater1", "owned"),
             compose([(shadow, 25, 30), (cell(tools, 5, 3, 6), 0, 0), (tick, 19, 22)]), "Filtered Water, owned")
        same(self, self.render("toolshears2", "tool_use"), compose([(cell(art.image("scissors.png"), 2, 3, 5), 0, 0)]),
             "golden shears cutting")
        chems = art.image("Chemicals_Grid.png")
        same(self, self.render("chem34", "pour"), compose([(cell(chems, 2, 9, 15), 0, 0)]), "Mutation Liquid pouring")
        same(self, self.render("chem27", "shelf"), compose([(shadow, 25, 30), (cell(chems, 2, 9, 0), 0, 0)]),
             "Plant Food on its shelf")
        same(self, self.render("ornament9", "owned"),
             compose([(shadow, 5, 10), (cell(art.image("Ornaments_Grid.png"), 5, 3, 9), 0, 0), (tick, -1, 2)]),
             "the Fountain, owned")
        same(self, self.render("seed5_2", "shelf"),
             compose([(shadow, 5, 5), (cell(art.image("seed_grid.png"), 16, 6, 18), 0, 0)]), "an Extinct packet")
        upgrades = art.image("Chemicals_Grid_upgrades.png")
        same(self, self.render("chem36", "shelf"), compose([(shadow, 25, 30), (cell(upgrades, 2, 23, 18), 0, 0)]),
             "the Radioactive Plant Formula (patcher)")
        same(self, self.render("extra_greenhouse", "owned"),
             compose([(shadow, 4, 30), (cell(upgrades, 2, 23, 30), 0, 0), (tick, -1, 22)]), "Extra Greenhouse")
        same(self, self.render("legendary7", "packet"),
             compose([(cell(art.image("seed_grid_legendary.png"), 16, 8, 102), 0, 0)]), "a Legendary packet")


if __name__ == "__main__":
    unittest.main()
