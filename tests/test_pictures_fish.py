"""Picture Studio, Fish Tycoon: the drawing rules in src/pictures_fish.py, proven against the
game's own code.

* The fish draw: for many bodies, fins, ages, states, ways of swimming and frames, the game's
  0x415DF0 sets up a fish record and its 0x4145F0 draws it, in Unicorn on the vanilla
  executable (tests/fish_draw_emulator.py), down to the blits; every blit (sheet, source
  rectangle, place, surface alpha, scale) must be the plan's.
* The blitter: the game's 0x4041C0 is run on real pixels for the teens' scaled draw and the
  fins' surface alpha, and its screen must be the one picture_image's rules give.
* The ornaments: the game's ornament pass 0x41D600 draws a tank's records; same check.
* DS Exclusive Fish: the companion's own C (decode_sprite, pair_anchors, head_on_x, built
  with its logic harness) must give what pictures_fish gives for every gene pair.
* The save reader, on synthetic saves and sidecars (never the owner's saves).

The emulated checks need the vanilla game (and MSVC for the DS harness); they skip without.
"""

from __future__ import annotations

import io
import json
import struct
import subprocess
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

import picture_image as pi
import pictures_fish as pf

ROOT = Path(__file__).resolve().parents[1]

try:
    import fish_draw_emulator as fde
    EMULATOR = fde.available()
except ImportError:                                    # no Unicorn
    fde = None
    EMULATOR = False


class ArtSizes(dict):
    """(kind, sprite) -> (width, height) of the real art: the vanilla game's, then the patcher's."""

    def __init__(self, emulator) -> None:
        super().__init__()
        self.emulator = emulator
        self.zip = zipfile.ZipFile(fde.VANILLA / "Assets" / "ft.dat")
        self.names = {n.casefold(): n for n in self.zip.namelist()}

    def read(self, name: str) -> bytes | None:
        if name.casefold() in self.names:
            return self.zip.read(self.names[name.casefold()])
        path = pf.patcher_art().get(name)
        return path.read_bytes() if path else None

    def __missing__(self, key):
        _kind, ident = key
        name = self.emulator.table_entry(ident)[0]
        data = self.read(name)
        value = struct.unpack(">II", data[16:24])
        self[key] = value
        return value


@unittest.skipUnless(EMULATOR, "the vanilla Fish Tycoon (and Unicorn) are needed")
class FishDrawMatchesTheGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sizes = None
        cls.emu = fde.FishDrawEmulator({})
        cls.sizes = ArtSizes(cls.emu)
        cls.emu.sizes = cls.sizes
        cls.renderer = pf.load(fde.VANILLA)

    def expected(self, plan) -> list[tuple]:
        """The plan as the blits it must give: file, rectangle, place, alpha, scale."""
        out = []
        for call in plan:
            data = self.sizes.read(call.file)
            w, h = struct.unpack(">II", data[16:24])
            rect = pi.cell_rect(w, h, call.cols, call.rows, call.cell)
            x, y = call.x, call.y
            if call.scale != 100:
                sheet = pi.decode_png(data)
                _piece, dx, dy = pi.scaled_cell(sheet, rect, call.scale)
                x, y = x + dx, y + dy
            out.append((call.file.casefold(), rect, x, y, call.alpha, call.scale))
        return out

    def recorded(self, blits) -> list[tuple]:
        out = []
        for b in blits:
            name = self.emu.table_entry(b.sprite)[0]
            alpha = int(b.alpha * 255.0 + 0.5)
            scale = round(b.scale * 100)
            out.append((name.casefold(), b.src, b.x, b.y, alpha, scale))
        return out

    def check(self, fish: pf.Fish, mode: int, frame: int, stage: int, height: int, label: str) -> None:
        rec = self.emu.fish_record(alive=fish.alive, age=fish.age, health=fish.health, disease=fish.disease,
                                   body=fish.body, fin=fish.fin, height=height)
        game = self.recorded(self.emu.draw(rec, 1000, 1000, mode, frame, frame, stage))
        plan = self.expected(pf.plan_fish(fish, mode, frame, frame, stage, height=height, x=1000, y=1000))
        self.assertEqual(plan, game, label)

    def test_sprite_setup_is_the_games(self) -> None:
        for body in range(21):
            for fin in range(21):
                rec = self.emu.fish_record(body=body, fin=fin)
                f = self.emu.sprite_fields(rec)
                s = pf.fish_sprites(body, fin)
                self.assertEqual((f["body_id"], f["top_id"], f["bot_id"], f["alpha"], f["top"], f["bot"]),
                                 (s.body_id, s.top_id, s.bot_id, s.alpha, s.top, s.bot), (body, fin))

    def test_sprite_table_is_the_games(self) -> None:
        for index in list(pf.STOCK_SHEETS) + list(range(38, 101)):
            name, cols, rows = self.emu.table_entry(index)
            self.assertEqual(pf.sheet(index), (name, cols, rows), index)

    def test_adults_every_body_fin_way_and_frame(self) -> None:
        for body in range(21):
            for fin in (0, 4, 6, 11, 15, 19, (body * 7) % 21):
                fish = pf.Fish(body, fin, 30)
                for mode in (0, 1, 3, 4):
                    for frame in range(6):
                        self.check(fish, mode, frame, pf.STAGE_ADULT, 50, f"{body}/{fin} mode {mode} frame {frame}")

    def test_sick_and_dead_adults(self) -> None:
        for body in range(0, 21, 3):
            for disease in (1, 2):
                for mode in (0, 1, 3):
                    self.check(pf.Fish(body, 5, 30, 60, disease), mode, 2, pf.STAGE_ADULT, 50,
                               f"{body} disease {disease} mode {mode}")
            self.check(pf.Fish(body, 5, 30, 0), 1, 0, pf.STAGE_ADULT, 50, f"dead {body}")
            self.check(pf.Fish(body, 5, 30, -3), 0, 4, pf.STAGE_ADULT, 50, f"dead {body}, health below 0")

    def test_teens_at_every_age_and_babies(self) -> None:
        for body in (0, 3, 9, 13, 20):
            for age in range(6, 20):
                for mode in (0, 1, 3):
                    self.check(pf.Fish(body, 2, age), mode, age % 6, pf.STAGE_TEEN, 48, f"teen {body} age {age}")
            self.check(pf.Fish(body, 2, 9, 0), 1, 0, pf.STAGE_TEEN, 48, f"dead teen {body}")
            for age in range(1, 6):
                for mode in (0, 1, 3):
                    self.check(pf.Fish(body, 2, age), mode, 5, pf.STAGE_BABY, 32, f"baby {body} age {age}")
            self.check(pf.Fish(body, 2, 4, 0), 1, 0, pf.STAGE_BABY, 32, f"dead baby {body}")

    def test_golden_seahorse(self) -> None:
        for mode in (0, 1, 3, 4):
            for frame in range(6):
                self.check(pf.Fish(22, 22, 21), mode, frame, pf.STAGE_SEAHORSE, 50, f"seahorse {mode} {frame}")

    def test_stages_follow_the_view_setup(self) -> None:
        """0x415460's rules, read from its code (0x4156D6-0x415833)."""
        self.assertIsNone(pf.stage_of(pf.Fish(3, 3, 0)))
        self.assertEqual([pf.stage_of(pf.Fish(3, 3, a)) for a in (1, 5, 6, 19, 20, 99)],
                         [pf.STAGE_BABY, pf.STAGE_BABY, pf.STAGE_TEEN, pf.STAGE_TEEN, pf.STAGE_ADULT, pf.STAGE_ADULT])
        self.assertEqual(pf.stage_of(pf.Fish(3, 3, 4, health=0)), pf.STAGE_TEEN)
        self.assertEqual(pf.stage_of(pf.Fish(22, 22, 21)), pf.STAGE_SEAHORSE)
        self.assertEqual((pf.view_height(pf.STAGE_BABY, 50), pf.view_height(pf.STAGE_TEEN, 50)), (32, 48))

    def test_custom_pictures_are_the_plans(self) -> None:
        """Make your own uses the same plans (and draws the stage the game would)."""
        r = self.renderer
        plan = r.plan_custom({"subject": "fish", "body": 13, "fin": 6, "stage": "teen12", "facing": "right", "frame": 2})
        self.assertEqual(plan, pf.plan_fish(pf.Fish(13, 6, 12), 0, 2, 2, pf.STAGE_TEEN, height=48))
        image = r.render_custom({"subject": "fish", "body": 11, "fin": 11, "stage": "adult"})
        self.assertGreater(image.width, 100)
        self.assertIsNotNone(image.bbox())


@unittest.skipUnless(EMULATOR, "the vanilla Fish Tycoon (and Unicorn) are needed")
class BlitterMatchesTheGame(unittest.TestCase):
    """The pixels: the game's blitter on a test picture against picture_image's rules."""

    @staticmethod
    def pattern(w: int, h: int) -> bytes:
        return b"".join(bytes(((x * 37 + y * 11) % 256, (x * 5 + y * 13) % 256, (x * y) % 256,
                               (0 if (x + y) % 7 == 0 else 255 if (x * y) % 3 else (x * 29 + y * 3) % 256)))
                        for y in range(h) for x in range(w))

    def screen_expected(self, image: pi.Image, x: int, y: int, background, alpha: int, sw: int, sh: int):
        out = [background] * (sw * sh)
        weights = [(a * alpha + 127) >> 8 for a in range(256)] if alpha < 255 else list(range(256))
        for j in range(image.height):
            for i in range(image.width):
                px, py = x + i, y + j
                if not (0 <= px < sw and 0 <= py < sh):
                    continue
                r, g, b, a = image.pixel(i, j)
                if a == 0 and alpha == 255:
                    continue                   # the per-pixel path skips clear pixels; the alpha path blends them too
                a = weights[a]
                d = out[py * sw + px]
                out[py * sw + px] = tuple((s * a + dv * (255 - a) + 0x7F) >> 8 for s, dv in zip((r, g, b), d))
        return out

    def test_teen_scaling(self) -> None:
        w, h = 88, 40
        rgba = self.pattern(w, h)
        sheet = pi.Image(w, h, rgba)
        blitter = fde.BlitterEmulator(160, 80)
        source = blitter.source(w, h, rgba)
        f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]   # noqa: E731
        for scale in (101, 106, 112, 118, 121, 127, 133, 136, 139):
            for rect in ((0, 0, 44, 20), (44, 20, 88, 40)):
                blitter.fill_screen((10, 200, 30))
                piece, dx, dy = pi.scaled_cell(sheet, rect, scale)
                # 0x407750 centres it, then the blitter draws at the moved place, uncentred
                blitter.blit(source, rect, 20 + dx, 9 + dy, 1.0, f32(scale / 100.0))
                got = blitter.screen_rgb()
                want = self.screen_expected(piece, 20 + dx, 9 + dy, (10, 200, 30), 255, 160, 80)
                self.assertEqual(got, want, f"scale {scale} rect {rect}")

    def test_fin_surface_alpha(self) -> None:
        w, h = 30, 12
        rgba = self.pattern(w, h)
        image = pi.Image(w, h, rgba)
        blitter = fde.BlitterEmulator(64, 32)
        source = blitter.source(w, h, rgba)
        f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]   # noqa: E731
        for alpha in (200, 210, 240):
            for background in ((0, 0, 0), (255, 255, 255), (90, 30, 200)):
                blitter.fill_screen(background)
                blitter.blit(source, (0, 0, w, h), 5, 7, f32(alpha / 255.0), 1.0, centred=True)
                self.assertEqual(blitter.screen_rgb(), self.screen_expected(image, 5, 7, background, alpha, 64, 32),
                                 f"alpha {alpha} on {background}")
        # and picture_image draws a fin with the same alpha on a clear canvas
        canvas = pi.Image(w, h)
        canvas.draw(image, 0, 0, alpha=200)
        for i in range(w * h):
            self.assertEqual(canvas.data[i * 4 + 3], (rgba[i * 4 + 3] * 200 + 127) >> 8)


@unittest.skipUnless(EMULATOR, "the vanilla Fish Tycoon (and Unicorn) are needed")
class OrnamentsMatchTheGame(unittest.TestCase):
    def test_ornament_pass(self) -> None:
        emu = fde.FishDrawEmulator({})
        sizes = ArtSizes(emu)
        emu.sizes = sizes
        e = emu.emu
        impl = e.alloc(0x100)
        e.write32(impl + 0x34, emu.state)
        e.write32(impl + 0x38, emu.sprite_holder)
        e.write32(impl + 0x54, emu.gfx_holder)
        e.write32(impl + 0x28, 0x63)                         # nothing held
        e.write32(emu.state + 0x384, 1)                       # Tank 2 on screen
        records = [(177, 120, 300, False), (178, 400, 280, False), (179, 600, 310, True),
                   (180, 60, 420, False), (181, 250, 350, False), (182, 700, 200, False)]
        base = emu.state + pf.ORN_BASE + 1 * pf.TANK_STRIDE
        plan = []
        for k, (sprite, x, y, falling) in enumerate(records):
            at = base + k * pf.ORN_STRIDE
            h = sizes.read(pf.sheet(sprite)[0])
            height = struct.unpack(">II", h[16:24])[1]
            e.write8(at, 1)
            e.write32(at + 4, x)
            e.write32(at + 8, y)
            e.write32(at + 0x10, 1 if falling else 0)
            e.write32(at + 0x1C, height)
            e.write32(at + 0x24, sprite)
            plan += pf.plan_ornament(sprite, x=x, y=y, h=height, falling=falling)
        emu.blits = []
        e.call(0x0041D600, ecx=impl)
        game = [(emu.table_entry(b.sprite)[0].casefold(), b.x, b.y) for b in emu.blits]
        self.assertEqual(game, [(c.file.casefold(), c.x, c.y) for c in plan])


HARNESS = ROOT / "native" / "ftfp_ds_fish" / "ds_fish_logic_harness.c"


def build_ds_harness(out: Path) -> Path | None:
    try:
        import store_emulator as se
    except ImportError:
        return None
    if not se.toolchain_ready():
        return None
    exe = out / "harness.exe"
    command = [str(se.MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/O2", "/W3", f"/Fe{exe}",
               f"/Fo{out}\\", "/I", str(se.MSVC / "include"),
               "/I", str(se.SDK / "Include" / se.SDK_VERSION / "um"),
               "/I", str(se.SDK / "Include" / se.SDK_VERSION / "shared"),
               "/I", str(se.SDK / "Include" / se.SDK_VERSION / "ucrt"), str(HARNESS), "/link",
               f"/LIBPATH:{se.MSVC / 'lib' / 'x86'}", f"/LIBPATH:{se.SDK / 'Lib' / se.SDK_VERSION / 'um' / 'x86'}",
               f"/LIBPATH:{se.SDK / 'Lib' / se.SDK_VERSION / 'ucrt' / 'x86'}", "kernel32.lib", "user32.lib"]
    result = subprocess.run(command, cwd=out, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return exe


class DsFishRulesAreTheDlls(unittest.TestCase):
    """The DS genes: pictures_fish against DS Exclusive Fish's own C code."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        exe = build_ds_harness(Path(cls.temp.name))
        cls.lines = None
        if exe is not None:
            text = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout
            cls.lines = {}
            for line in text.splitlines():
                kind, *rest = line.split(" ")
                cls.lines.setdefault(kind, []).append(rest)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def setUp(self) -> None:
        if self.lines is None:
            self.skipTest("MSVC is needed to build the DS Exclusive Fish logic harness")

    def test_decode(self) -> None:
        for sprite_id, entry, frame in self.lines["decode"]:
            self.assertEqual(pf.decode(int(sprite_id)), (int(entry), int(frame)), sprite_id)

    def test_pair_anchors(self) -> None:
        for body, fin, *anchor in self.lines["anchor"]:
            body, fin, anchor = int(body), int(fin), tuple(int(v) for v in anchor)
            s = pf.fish_sprites(body, fin)
            if anchor == (-1, -1, -1, -1):
                self.assertFalse(pf.is_ds(body) or pf.is_ds(fin))
            else:
                self.assertEqual(s.top + s.bot, anchor, (body, fin))

    def test_head_on(self) -> None:
        for body, fin, frame, top, bot in self.lines["headon"]:
            body, fin, frame = int(body), int(fin), int(frame)
            self.assertEqual(pf.head_on_x(body, fin, 0, frame, 17, -13), int(top), (body, fin, frame))
            self.assertEqual(pf.head_on_x(body, fin, 1, frame, 21, 10), int(bot), (body, fin, frame))


class DsDataIsCurrent(unittest.TestCase):
    def test_generated_module_matches_the_layout(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_picture_fish_ds", ROOT / "scripts" / "build_picture_fish_ds.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        current = (ROOT / "src" / "pictures_fish_ds.py").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(current, module.render(), "run scripts/build_picture_fish_ds.py")

    def test_ds_plans_use_the_ds_sheets(self) -> None:
        plan = pf.plan_fish(pf.Fish(25, 3, 30), 1, 0, 0, pf.STAGE_ADULT)
        self.assertEqual([c.file for c in plan], ["FISH_03_top_Grid.png", "FISH_03_bot_Grid.png", "FISH_25_body_Grid.png"])
        layout = json.loads((ROOT / "data" / "ds_fish_layout.json").read_text(encoding="utf-8"))
        anchor = next(p["anchor"] for p in layout["pair_anchors"] if (p["body"], p["fin"]) == (25, 3))
        self.assertEqual((plan[0].x, plan[0].y), (50 - anchor[0], anchor[1]))
        teen = pf.plan_fish(pf.Fish(26, 26, 10), 1, 0, 0, pf.STAGE_TEEN)
        self.assertEqual((teen[0].file, teen[0].cell), ("FISH_DS_teen_Grid.png", 3 * 18))
        dead = pf.plan_fish(pf.Fish(29, 1, 30, 0), 1, 0, 0, pf.STAGE_ADULT)
        self.assertEqual((dead[0].file, dead[0].cell), ("FISH_DS_adult_dead_Grid.png", 6))

    def test_store_animals(self) -> None:
        """DS Store Items' companion_sheet: each animal's own sheet, centred on the seahorse's box."""
        for fin, file, (w, h) in ((30, "DS_PUFFER_Grid.png", (74, 71)), (31, "DS_STINGRAY_Grid.png", (145, 63)),
                                  (32, "DS_EEL_Grid.png", (234, 45))):
            plan = pf.plan_fish(pf.Fish(22, fin, 21), 1, 2, 2, pf.STAGE_SEAHORSE, height=50, x=300, y=200)
            self.assertEqual((plan[0].file, plan[0].cell, plan[0].x, plan[0].y),
                             (file, 2, 300 + 57 - w // 2, 203 + 30 - h // 2))
        puffed = pf.plan_fish(pf.Fish(22, 30, 21), 0, 1, 1, pf.STAGE_SEAHORSE, puff=3)
        self.assertEqual((puffed[0].file, puffed[0].cell), ("DS_PUFFER_PUFF_Grid.png", 4 + 3))


# ------------------------------------------------------------------ the save reader (synthetic)


def make_save(folder: Path, slot: int = 1, fish=(), ornaments=(), owned=(), state_extra=None) -> Path:
    state = bytearray(pf.STATE_SIZE)
    for tank, s, body, fin, age, health, disease in fish:
        at = pf.FISH_BASE + tank * pf.TANK_STRIDE + s * pf.SLOT_STRIDE - 8
        struct.pack_into("<i", state, at, 1)
        struct.pack_into("<i", state, at + 0x0C, age)
        struct.pack_into("<i", state, at + 0x3C, health)
        struct.pack_into("<i", state, at + 0x40, disease)
        struct.pack_into("<ii", state, at + 0x4C, body, fin)
        sp = pf.fish_sprites(body, fin) if body != 22 else pf.fish_sprites(22, 22)
        struct.pack_into("<4i", state, at + 0x54, sp.body_id, sp.top_id, sp.bot_id, sp.alpha)
        struct.pack_into("<4i", state, at + 0x68, *sp.top, *sp.bot)
    for tank, k, sprite, x, y, h in ornaments:
        at = pf.ORN_BASE + tank * pf.TANK_STRIDE + k * pf.ORN_STRIDE - 8
        state[at] = 1
        struct.pack_into("<ii", state, at + 4, x, y)
        struct.pack_into("<i", state, at + 0x1C, h)
        struct.pack_into("<i", state, at + 0x24, sprite)
    for off in owned:
        struct.pack_into("<i", state, off - 8, 1)
    if state_extra:
        state_extra(state)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"Fish Tycoon{slot}.ldw"
    path.write_bytes(b"ldwg" + bytes(0x14) + bytes(state))
    return path


def put_fish(path: Path, tank: int, s: int, body: int, fin: int, age: int, health: int = 100, disease: int = 0) -> None:
    """A fish record written into an existing synthetic save, as the game sets one up."""
    data = bytearray(path.read_bytes())
    at = pf.SAVE_HEADER - 8 + pf.FISH_BASE + tank * pf.TANK_STRIDE + s * pf.SLOT_STRIDE
    struct.pack_into("<i", data, at, 1)
    struct.pack_into("<i", data, at + 0x0C, age)
    struct.pack_into("<i", data, at + 0x3C, health)
    struct.pack_into("<i", data, at + 0x40, disease)
    struct.pack_into("<ii", data, at + 0x4C, body, fin)
    sp = pf.fish_sprites(body, fin)
    struct.pack_into("<4i", data, at + 0x54, sp.body_id, sp.top_id, sp.bot_id, sp.alpha)
    struct.pack_into("<4i", data, at + 0x68, *sp.top, *sp.bot)
    path.write_bytes(bytes(data))


def fake_game_copy(folder: Path) -> Path:
    """A stand-in Fish Tycoon copy: an .exe and an Images folder with every sheet the pictures
    need, each cell a small coloured block (no game art)."""
    images = folder / "Images"
    images.mkdir(parents=True)
    (folder / "Fish Tycoon.exe").write_bytes(b"MZ")
    names = {}
    for index in list(pf.STOCK_SHEETS) + list(range(38, 101)):
        names[pf.sheet(index)[0]] = pf.sheet(index)[1:]
    for n, (name, (cols, rows)) in enumerate(names.items()):
        cols, rows = max(1, cols), max(1, rows)
        image = pi.Image(cols * 12, rows * 10)
        block = pi.Image(8, 6, bytes(((n * 40) % 256, 90, 160, 255)) * 48)
        for c in range(cols):
            for r in range(rows):
                image.draw(block, c * 12 + 2, r * 10 + 2)
        (images / name).write_bytes(image.to_png())
    return folder


def animal_record(fin: int, age: int = 21) -> bytes:
    rec = bytearray(pf.SLOT_STRIDE)
    struct.pack_into("<i", rec, 0, 1)
    struct.pack_into("<I", rec, 0x14, pf.ANIMAL_MARK)
    struct.pack_into("<i", rec, 0x0C, age)
    struct.pack_into("<i", rec, 0x3C, 100)
    struct.pack_into("<ii", rec, 0x4C, 22, fin)
    return bytes(rec)


class SaveReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name) / "Fish Tycoon"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_tanks_fish_ornaments_and_equipment(self) -> None:
        make_save(self.folder, 2, fish=[(0, 0, 11, 11, 25, 100, 0), (0, 4, 3, 5, 8, 90, 0), (1, 0, 13, 6, 2, 80, 0),
                                       (2, 7, 0, 0, 40, 0, 0), (3, 0, 5, 5, 30, 50, 1), (1, 3, 22, 22, 21, 100, 0),
                                       (0, 9, 4, 4, 0, 100, 0)],
                  ornaments=[(0, 0, 178, 100, 200, 120), (2, 5, 182, 50, 60, 70)],
                  owned=(0x190, 0x140))
        before = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        r = pf.FishRenderer(None)
        items = r.saved_items(self.folder, 2)
        labels = [(i.location, i.kind, i.label) for i in items]
        self.assertIn(("Tank 1", "fish", "Crimson Comet (adult, age 25)"), labels)
        self.assertIn(("Tank 1", "fish", "Snubbed Snout (teen, age 8)"), labels)
        self.assertIn(("Tank 2", "fish", "Wasp Grouper (baby, age 2)"), labels)
        self.assertIn(("Tank 3 (Sale Tank)", "fish", "Silky Shark (adult, age 40, dead)"), labels)
        self.assertIn(("Isolation Tank", "fish", "Snubbed Snooper (adult, age 30, sick (ick))"), labels)
        self.assertIn(("Tank 2", "creature", "Golden Seahorse"), labels)
        self.assertIn(("Tank 1", "decoration", "Pagoda Ornament"), labels)
        self.assertIn(("Tank 3 (Sale Tank)", "decoration", "Sunken Ship Ornament"), labels)
        self.assertIn(("Every tank", "decoration", "Plant of Curing from Isola"), labels)
        self.assertIn(("Every tank", "creature", "Cleaning Snail"), labels)
        self.assertFalse(any("age 0" in label for _l, _k, label in labels), "age 0 is not drawn")
        # the plans are the game's plans for those records
        crimson = next(i for i in items if i.label.startswith("Crimson"))
        self.assertEqual(r.plan_saved(self.folder, 2, crimson.id),
                         pf.plan_fish(pf.Fish(11, 11, 25, 100, 0), 1, 0, 0, pf.STAGE_ADULT, height=50))
        after = {p: p.read_bytes() for p in self.folder.rglob("*") if p.is_file()}
        self.assertEqual(before, after, "the save is only read")

    def test_extra_tanks_v4_and_v3(self) -> None:
        make_save(self.folder, 1)
        sidecars = self.folder / pf.SIDECAR_FOLDER
        sidecars.mkdir()
        for version in (4, 3):
            held = pf.TANK_STRIDE + (5 * pf.SLOT_STRIDE if version == 4 else 0)
            blocks = bytearray(3 * held)
            rec = bytearray(pf.SLOT_STRIDE)
            struct.pack_into("<i", rec, 0, 1)
            struct.pack_into("<i", rec, 0x0C, 22)
            struct.pack_into("<i", rec, 0x3C, 100)
            struct.pack_into("<ii", rec, 0x4C, 25, 27)
            blocks[held + 2 * pf.SLOT_STRIDE:held + 3 * pf.SLOT_STRIDE] = rec   # Tank 5, place 3
            if version == 4:
                at = held + pf.TANK_STRIDE
                blocks[at:at + pf.SLOT_STRIDE] = animal_record(31)
            else:
                at = held + 27 * pf.SLOT_STRIDE
                blocks[at:at + pf.SLOT_STRIDE] = animal_record(31)
            header = struct.pack("<7I", pf.EXTRA_MAGIC, version, 3, pf.TANK_STRIDE, zlib.crc32(bytes(blocks)), 2, 0)
            (sidecars / "Extra Tanks 1.dat").write_bytes(header + bytes(blocks))
            items = pf.FishRenderer(None).saved_items(self.folder, 1)
            labels = [(i.location, i.label) for i in items]
            self.assertIn(("Tank 5", "Bicolor Yellow"[0:0] + pf.species_name(25, 27) + " (adult, age 22)"), labels, version)
            self.assertIn(("Tank 5", "Blue-Spotted Stingray"), labels, version)
        # a damaged file is not loaded
        data = bytearray((sidecars / "Extra Tanks 1.dat").read_bytes())
        data[100] ^= 1
        (sidecars / "Extra Tanks 1.dat").write_bytes(bytes(data))
        r = pf.FishRenderer(None)
        self.assertFalse(any(i.location == "Tank 5" for i in r.saved_items(self.folder, 1)))
        self.assertTrue(r._save.notes)

    def test_tank_animals_follow_the_dlls_rules(self) -> None:
        def fingerprint(state):
            struct.pack_into("<i", state, 0x38C - 8, 5000)
            struct.pack_into("<i", state, 0x24 - 8, 700)
            struct.pack_into("<i", state, 0x3C - 8, 9)
            struct.pack_into("<i", state, 0x44 - 8, 300)
        make_save(self.folder, 3, state_extra=fingerprint)
        sidecars = self.folder / pf.SIDECAR_FOLDER
        sidecars.mkdir()
        records = bytearray(15 * pf.SLOT_STRIDE)
        records[0:pf.SLOT_STRIDE] = animal_record(30)                      # Tank 1
        at = (2 * 5 + 1) * pf.SLOT_STRIDE
        records[at:at + pf.SLOT_STRIDE] = animal_record(32)                # Sale Tank

        def write(money, sessions, minutes):
            header = struct.pack("<10I", pf.TA_MAGIC, 1, 15, pf.SLOT_STRIDE, money, 700, sessions, minutes, 0,
                                 pf._fnv(bytes(records)))
            (sidecars / "Tank Animals 3.dat").write_bytes(header + bytes(records))

        write(5000, 9, 300)
        labels = [(i.location, i.label) for i in pf.FishRenderer(None).saved_items(self.folder, 3)]
        self.assertIn(("Tank 1", "Magic Pufferfish"), labels)
        self.assertIn(("Tank 3 (Sale Tank)", "Moray Eel"), labels)
        write(4000, 8, 200)                      # an earlier point of the same save: still loaded
        self.assertIn(("Tank 1", "Magic Pufferfish"),
                      [(i.location, i.label) for i in pf.FishRenderer(None).saved_items(self.folder, 3)])
        write(4000, 10, 200)                     # a later point (an older save restored): not loaded
        self.assertNotIn(("Tank 1", "Magic Pufferfish"),
                         [(i.location, i.label) for i in pf.FishRenderer(None).saved_items(self.folder, 3)])

    def test_multiple_ornaments_copies(self) -> None:
        make_save(self.folder, 1)
        sidecars = self.folder / pf.SIDECAR_FOLDER
        sidecars.mkdir()
        counts = [0] * 8
        records = bytearray(8 * 10 * pf.ORN_STRIDE)
        for t, sprite in ((0, 177), (0, 181), (4, 179)):                    # logical 4 = Tank 5
            rec = bytearray(pf.ORN_STRIDE)
            rec[0] = 1
            struct.pack_into("<i", rec, 0x1C, 60)
            struct.pack_into("<i", rec, 0x20, 60)
            struct.pack_into("<i", rec, 0x24, sprite)
            at = (t * 10 + counts[t]) * pf.ORN_STRIDE
            records[at:at + pf.ORN_STRIDE] = rec
            counts[t] += 1
        header = struct.pack("<5I", pf.ORN_MAGIC, 1, 8, 10, pf.ORN_STRIDE) + struct.pack("<8I", *counts)
        (sidecars / "Ornaments 1.dat").write_bytes(header + bytes(records))
        labels = [(i.location, i.label) for i in pf.FishRenderer(None).saved_items(self.folder, 1)]
        self.assertIn(("Tank 1", "Shell Ornament"), labels)
        self.assertIn(("Tank 1", "Fancy Coral Ornament"), labels)

    def test_not_a_save(self) -> None:
        self.folder.mkdir(parents=True)
        (self.folder / "Fish Tycoon1.ldw").write_bytes(b"nope")
        with self.assertRaises(pi.PictureError):
            pf.FishRenderer(None).saved_items(self.folder, 1)


class ChoicesTests(unittest.TestCase):
    def test_spoilers_off_offers_only_discovered_parts(self) -> None:
        r = pf.FishRenderer(None)
        subjects = r.custom_choices(frozenset(), False, {(11, 11), (13, 6)})
        fish = subjects[0]
        fields = {f.key: f for f in fish.fields}
        self.assertEqual([o.key for o in fields["body"].options], [11, 13])
        self.assertEqual([o.key for o in fields["fin"].options], [6, 11])
        everything = {f.key: f for f in r.custom_choices(frozenset({"ds_fish", "ds_store"}), True, None)[0].fields}
        self.assertEqual(len(everything["body"].options), 28)
        self.assertTrue(all(o.patcher for o in everything["body"].options if o.key >= 23))
        none = {f.key: f for f in r.custom_choices(frozenset(), False, None)[0].fields}
        self.assertEqual(none["body"].options, ())
        creatures = [o.key for o in r.custom_choices(frozenset(), True, None)[1].fields[0].options]
        self.assertNotIn("eel", creatures)
        self.assertIn("eel", [o.key for o in r.custom_choices(frozenset({"ds_store"}), True, None)[1].fields[0].options])

    def test_required_files_name_every_stock_sheet(self) -> None:
        names = pf.required_files()
        self.assertIn("FISH_teen_Grid.png", names)
        self.assertIn("FISH_20_top_Grid.png", names)
        self.assertNotIn("FISH_23_body_Grid.png", names)
        self.assertTrue(set(pf.patcher_files()) <= set(pf.patcher_art()), "every DS sheet ships with the patcher")


if __name__ == "__main__":
    unittest.main()
