"""Zoom in when pruning ("Prune Zoom.dll", Plant Tycoon).

The emulated tests run the patched executable in Unicorn (tests/test_every_patch.py's World: the real
startup loader loads the real DLL) with a real 800 x 600 screen: the game's own bench draw (0x423580),
pot draw (0x42F740), plant draw (vtable slots 7, 10, 13, 11), sprite draw (0x4208F0), scaler (0x404610),
FillRect (0x407B80) and pixel read (0x407AD0) draw the vanilla game's pictures into it, and the game's own
press (0x426040) prunes. Only SDL's few calls (map a colour, fill, lock), the mouse, operator new and the
press's sounds and messages are stand-ins. Each check is made twice where it can be: with the DLL's two
sites in place and with the stock bytes put back.
"""

from __future__ import annotations

import gc
import json
import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_every_patch as T  # noqa: E402

MANIFEST = json.loads((ROOT / "data" / "plant_manifest.json").read_text(encoding="utf-8"))
SETTING = "prune_zoom"
DLL = "Prune Zoom.dll"
SOURCE = ROOT / "native" / "ftfp_prune_zoom" / "ftfp_prune_zoom.c"
DRAW_SITE, PRESS_SITE = 0x428FC0, 0x426040
SITES = {DRAW_SITE: bytes.fromhex("E8BBA5FFFF"),           # call 0x423580, the benches' plants
         PRESS_SITE: bytes.fromhex("83EC0C5355")}          # the press: sub esp, 0xC; push ebx; push ebp
PREVIEW = Path.home() / "Downloads" / "Prune zoom preview.png"
W, H = 800, 600
HELD, SHEARS = 0x56C, 3
POT_BASE, POT_STRIDE = 0x2188, 0x5600
BOX_W, BOX_H, ZOOM = 279, 432, 1.75
PLANTS = {0: (12, 9), 2: (1, 13), 7: (7, 3), 12: (2, 18), 14: (21, 1)}

RANDOM, NEW, DELETE, MEMSET, MEMCPY = 0x004033B0, 0x0044E894, 0x0044E7B3, 0x00451280, 0x00450C10
WHOLE_IMAGE, FRAME_IMAGE = 0x00420550, 0x00420310
SDL_MAP_RGBA, SDL_LOCK, SDL_MAP_RGB, SDL_FILL, SDL_UNLOCK, SDL_MOUSE = (0x44E65A, 0x44E660, 0x44E678, 0x44E67E,
                                                                     0x44E654, 0x44E642)
SDL_BLIT, SDL_GET_RGB = 0x44E696, 0x44E672
MOUSE, BUTTON = 0x00402030, 0x00402050
PLANT_OF, POT_AT = 0x0042F6C0, 0x00423970

try:
    from unicorn import UC_HOOK_CODE
    from store_emulator import RETURN, THUNKS, THUNK_SIZE
    import picture_image as pi
    import pictures_plant as pp
    import pictures_plant_data as D
    import numpy as np
except ImportError:                       # Unicorn is not installed: the emulated tests skip
    UC_HOOK_CODE = None


def cell_point(k: int) -> tuple[int, int]:
    """A point inside pot k's cell (0x423970: 5 columns of 92 px from x 270, 3 rows of 144 from y 43)."""
    return 270 + 92 * (k % 5) + 46, 43 + 144 * (k // 5) + 100


def anchor(k: int) -> tuple[int, int]:
    """Where the benches draw pot k (0x42FDE0)."""
    return 323 + 93 * (k % 5), 117 + 144 * (k // 5)


def expected_box(k: int) -> tuple[int, int, int, int]:
    cx, cy = 270 + 92 * (k % 5) + 46, 43 + 144 * (k // 5) + 72
    left = min(max(cx - BOX_W // 2, 240), 800 - BOX_W)
    top = min(max(cy - BOX_H // 2, 0), 506 - BOX_H)
    return left, top, left + BOX_W - 1, top + BOX_H - 1


def zoom_to_real(k: int, box: tuple, p: tuple[int, int]) -> tuple[float, float]:
    """The point of the real plant drawn at zoom point p (the inverse of the zoom's scale and offset)."""
    cx, cy = 270 + 92 * (k % 5) + 46, 43 + 144 * (k // 5) + 72
    bx, by = box[0] + BOX_W // 2, box[1] + BOX_H // 2
    return cx + (p[0] - bx) / ZOOM, cy + (p[1] - by) / ZOOM


class Greenhouse:
    """One built game with its greenhouse: plants in PLANTS' pots, a real screen."""

    def __init__(self, settings: set[str]) -> None:
        self.build = T.build("plant", T.with_requirements(MANIFEST, settings))
        world = self.world = T.World(self.build)
        world.run_loader()
        emu = self.emu = world.emu
        self.uc = emu.uc
        self._fast()
        self.rng = random.Random(1)
        self.mouse = [0, 0]
        emu.hook(RANDOM, lambda e: self.rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0)
        emu.hook(NEW, lambda e: self._zeroed(max(e.arg(0), 4)))
        emu.hook(DELETE, lambda e: 0)
        emu.hook(MEMSET, lambda e: e.uc.mem_write(e.arg(0), bytes([e.arg(1) & 0xFF]) * e.arg(2)) or e.arg(0))
        emu.hook(MEMCPY, lambda e: e.uc.mem_write(e.arg(0), bytes(e.uc.mem_read(e.arg(1), e.arg(2)))) or e.arg(0))
        emu.hook(SDL_LOCK, lambda e: 0)
        emu.hook(SDL_UNLOCK, lambda e: 0)
        emu.hook(SDL_MAP_RGB, lambda e: (e.arg(1) & 0xFF) | (e.arg(2) & 0xFF) << 8 | (e.arg(3) & 0xFF) << 16 | 0xFF000000)
        emu.hook(SDL_MAP_RGBA, lambda e: (e.arg(1) & 0xFF) | (e.arg(2) & 0xFF) << 8 | (e.arg(3) & 0xFF) << 16
                 | (e.arg(4) & 0xFF) << 24)
        emu.hook(SDL_FILL, self._sdl_fill)
        emu.hook(SDL_BLIT, self._sdl_blit)
        emu.hook(SDL_GET_RGB, self._sdl_get_rgb)
        emu.hook(SDL_MOUSE, lambda e: 0)
        emu.hook(MOUSE, self._mouse)
        emu.hook(BUTTON, lambda e: 0)
        self.format = self._format()
        self.images: dict = {}
        self.pictures: dict = {}
        self.state = self._zeroed(0x63E70)
        self.screen = self.surface(W, H)
        self.pixels = emu.read32(self.screen + 0x14)
        inner = self.inner = self._zeroed(0x100)
        emu.write32(inner + 8, W)
        emu.write32(inner + 0xC, H)
        emu.write32(inner + 0x30, self.screen)
        for at, value in ((0x60, 0), (0x64, 0), (0x68, W), (0x6C, H)):
            emu.write32(inner + at, value)
        self.graphics = self._zeroed(0x10)
        emu.write32(self.graphics, inner)
        self.sprites = self._zeroed(0x10)
        emu.write32(self.sprites, self._zeroed(0x10))
        emu.write32(self.sprites + 4, self.graphics)
        emu.hook(0x0041FCD0, lambda e: self.state)
        emu.hook(0x00420670, lambda e: self.sprites)
        emu.hook(0x00407A90, lambda e: self.graphics)
        emu.write32(0x00493C34, self.sprites)
        emu.write32(0x0049333C, self.state)
        emu.hook(WHOLE_IMAGE, lambda e: self.image(e.arg(0), whole=True), 4)
        emu.hook(FRAME_IMAGE, lambda e: self.image(e.arg(0), whole=False), 4)
        self.manager = self._zeroed(0x810A4)
        emu.write32(self.manager, self.state)
        emu.write32(self.manager + 4, self.sprites)
        scene = self.scene = self._zeroed(0x200)
        emu.write32(scene + 0x68, self.state)
        emu.write32(scene + 0x70, self.manager)
        for offset in (0x60, 0x6C, 0x74, 0x78, 0x7C, 0x84, 0x90, 0x94, 0x9C):
            emu.write32(scene + offset, self._zeroed(0x100))
        for offset in (0x80, 0x88):                                  # nothing flying, no pot in the hand
            idle = self._zeroed(0x40)
            emu.write32(idle + 4, 0xFFFFFFFF)
            emu.write32(scene + offset, idle)
        tray = self._zeroed(8)
        emu.write32(tray, self.state)
        emu.write32(scene + 0x8C, tray)
        emu.write32(0x493BE8, tray)
        emu.write32(self.state + 0x63E58, 0x63)                       # no plant selected
        self.calls: list[str] = []
        for address, name in ((0x44A580, "sound"), (0x41B190, "message"), (0x41D830, "message once"),
                              (0x4244C0, "put back"), (0x423630, "select"), (0x449F00, "sound bank")):
            emu.hook(address, self._recorded(name), world.pops(address))
        for k, (foliage, flower) in PLANTS.items():
            plant = pp.grow_custom(foliage, flower, 1, "bloom")
            plant.health = 60
            self.uc.mem_write(self.pot(k), plant.to_record())
        self.patched = {va: bytes(self.uc.mem_read(va, len(stock))) for va, stock in SITES.items()}
        self.on_draw = DRAW_SITE + 5 + struct.unpack("<i", self.patched[DRAW_SITE][1:])[0]
        self.zoom_state = world.companions[DLL].exports["FtfpPruneZoomState"]
        self.background = bytes(W * H * 4)
        self.objects = [self.plant(k) for k in PLANTS]

    # ------------------------------------------------------------ the emulator, at native speed
    def _fast(self) -> None:
        """After the loader, Python sees only the hooked addresses (not every instruction)."""
        emu, uc = self.emu, self.uc
        uc.hook_del(emu.code_hook)
        base = T.E.Emulator._on_code
        uc.hook_add(UC_HOOK_CODE, lambda u, a, s, d: base(emu, u, a, s, d), begin=THUNKS, end=THUNKS + THUNK_SIZE - 1)
        added: set = set()
        plain = T.E.Emulator.hook

        def hook(address, handler, pop=0):
            plain(emu, address, handler, pop)
            if address not in added and not THUNKS <= address < THUNKS + THUNK_SIZE:
                added.add(address)
                uc.hook_add(UC_HOOK_CODE, lambda u, a, s, d: base(emu, u, a, s, d), begin=address, end=address)
        emu.hook = hook
        for address in list(emu.hooks):
            if not THUNKS <= address < THUNKS + THUNK_SIZE:
                added.add(address)
                uc.hook_add(UC_HOOK_CODE, lambda u, a, s, d: base(emu, u, a, s, d), begin=address, end=address)

    def _zeroed(self, size: int) -> int:
        address = self.emu.alloc(size)
        self.uc.mem_write(address, bytes(size))
        return address

    def _recorded(self, name: str):
        def handler(e) -> int:
            self.calls.append(name)
            return 0
        return handler

    def _mouse(self, e) -> int:
        out = e.arg(0)
        e.uc.mem_write(out, struct.pack("<ii", *self.mouse))
        return out

    def _format(self) -> int:
        """SDL_PixelFormat of ABGR8888 (bytes R, G, B, A)."""
        fmt = self.emu.alloc(0x28)
        self.uc.mem_write(fmt, struct.pack("<IIBB2xIIII4B4B", 0x16762004, 0, 32, 4, 0xFF, 0xFF00, 0xFF0000,
                                           0xFF000000, 0, 0, 0, 0, 0, 8, 16, 24))
        return fmt

    def surface(self, w: int, h: int, data: bytes | None = None) -> int:
        surface = self.emu.alloc(0x40)
        pixels = self._zeroed(w * h * 4)
        if data is not None:
            self.uc.mem_write(pixels, bytes(data))
        self.uc.mem_write(surface, struct.pack("<IIiiiI", 0, self.format, w, h, w * 4, pixels))
        return surface

    def picture(self, name: str):
        if name not in self.pictures:
            folder = T.VANILLA_DIRS["plant"] / "Images"
            path = next(p for p in folder.iterdir() if p.name.casefold() == name.casefold())
            self.pictures[name] = pi.decode_png(path.read_bytes())
        return self.pictures[name]

    def image(self, sprite: int, whole: bool) -> int:
        key = (sprite, whole)
        if key not in self.images:
            name, cols, rows = D.SPRITES[sprite]
            picture = self.picture(name)
            w, h = picture.width, picture.height
            cols, rows = (1, 1) if whole or not cols else (cols, rows)
            surface = self.surface(w, h, picture.data)
            wrapper = self._zeroed(0x10)
            self.emu.write32(wrapper, surface)
            obj = self._zeroed(0x40)
            for at, value in ((4, wrapper), (8, cols), (0xC, max(1, rows)), (0x10, w // cols), (0x14, h // max(1, rows))):
                self.emu.write32(obj + at, value)
            self.images[key] = obj
        return self.images[key]

    def _sdl_fill(self, e) -> int:
        surface, rect, colour = e.arg(0), e.arg(1), e.arg(2)
        w, h, pitch, pixels = struct.unpack("<iiiI", e.uc.mem_read(surface + 8, 16))
        x, y, rw, rh = struct.unpack("<iiii", e.uc.mem_read(rect, 16)) if rect else (0, 0, w, h)
        x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + rw), min(h, y + rh)
        if x1 > x0:
            row = struct.pack("<I", colour) * (x1 - x0)
            for yy in range(y0, y1):
                e.uc.mem_write(pixels + yy * pitch + x0 * 4, row)
        return 0

    @staticmethod
    def _sdl_get_rgb(e) -> int:
        pixel = e.arg(0)
        for n in range(3):
            e.uc.mem_write(e.arg(2 + n), bytes([(pixel >> (8 * n)) & 0xFF]))
        return 0

    def _sdl_blit(self, e) -> int:
        """SDL_UpperBlit with the source's alpha blended over the screen (SDL_BLENDMODE_BLEND)."""
        src, srect, dst, drect = (e.arg(i) for i in range(4))
        sw, sh, spitch, spix = struct.unpack("<iiiI", e.uc.mem_read(src + 8, 16))
        dw, dh, dpitch, dpix = struct.unpack("<iiiI", e.uc.mem_read(dst + 8, 16))
        sx, sy, w, h = struct.unpack("<iiii", e.uc.mem_read(srect, 16)) if srect else (0, 0, sw, sh)
        dx, dy = struct.unpack("<ii", e.uc.mem_read(drect, 8)) if drect else (0, 0)
        if sx < 0:
            w, dx, sx = w + sx, dx - sx, 0
        if sy < 0:
            h, dy, sy = h + sy, dy - sy, 0
        w, h = min(w, sw - sx), min(h, sh - sy)
        if dx < 0:
            w, sx, dx = w + dx, sx - dx, 0
        if dy < 0:
            h, sy, dy = h + dy, sy - dy, 0
        w, h = min(w, dw - dx), min(h, dh - dy)
        if w <= 0 or h <= 0 or not spix:
            return 0
        source = np.frombuffer(bytes(e.uc.mem_read(spix + sy * spitch, (h - 1) * spitch + (sx + w) * 4)), np.uint8)
        source = np.lib.stride_tricks.as_strided(source[sx * 4:], (h, w, 4), (spitch, 4, 1)).astype(np.uint32)
        start = dpix + dy * dpitch + dx * 4
        target = np.frombuffer(bytes(e.uc.mem_read(start, (h - 1) * dpitch + w * 4)), np.uint8).copy()
        view = np.lib.stride_tricks.as_strided(target, (h, w, 4), (dpitch, 4, 1))
        a = source[:, :, 3:4]
        view[:, :, :3] = ((source[:, :, :3] * a + view[:, :, :3].astype(np.uint32) * (255 - a)) // 255).astype(np.uint8)
        e.uc.mem_write(start, target.tobytes())
        return 0

    # ------------------------------------------------------------ the game
    def pot(self, k: int) -> int:
        return self.state + POT_BASE + k * POT_STRIDE

    def plant(self, k: int) -> int:
        return self.world.call(PLANT_OF, k // 5, k % 5, ecx=self.manager)

    def hover(self, k: int) -> tuple[int, int]:
        obj = self.plant(k)
        return self.emu.read32(obj + 0x1C, signed=True), self.emu.read32(obj + 0x20, signed=True)

    def zoom(self) -> tuple[int, tuple]:
        out = self._zeroed(24)
        self.world.call(self.zoom_state, out)
        values = struct.unpack("<6i", self.uc.mem_read(out, 24))
        return values[0], values[2:]

    def sites(self, patched: bool) -> None:
        for va, stock in SITES.items():
            self.uc.mem_write(va, self.patched[va] if patched else stock)
            self.uc.ctl_remove_cache(va, va + len(stock))

    def frame(self, mouse: tuple[int, int], patched: bool = True) -> bytes:
        """One frame of the benches (and the zoom): the background, then the overlay's call at 0x428FC0."""
        self.mouse[:] = mouse
        self.uc.mem_write(self.pixels, self.background)
        self.call(self.on_draw if patched else 0x423580)
        return bytes(self.uc.mem_read(self.pixels, W * H * 4))

    def frames(self, mouse: tuple[int, int]) -> tuple[bytes, bytes]:
        """The same frame with the setting and without, from the same state (the light on a part under
        the shears pulses, frame by frame)."""
        snap = self.snapshot()
        on = self.frame(mouse)
        after = self.snapshot()
        self.restore(snap)
        off = self.frame(mouse, patched=False)
        self.restore(after)
        return on, off

    def call(self, address: int, *args: int) -> int:
        """A thiscall on the scene, with room for the zoom's big plant (the scaler runs per pixel)."""
        emu, uc = self.emu, self.uc
        esp = T.E.STACK + T.E.STACK_SIZE - 0x1000
        for value in reversed(args):
            esp -= 4
            emu.write32(esp, value)
        esp -= 4
        emu.write32(esp, T.E.RETURN)
        uc.reg_write(T.X.UC_X86_REG_ESP, esp)
        uc.reg_write(T.X.UC_X86_REG_ECX, self.scene)
        uc.reg_write(T.X.UC_X86_REG_FPCW, 0x027F)
        self.world.run(address, T.E.RETURN, f"0x{address:X}", count=400_000_000)
        return uc.reg_read(T.X.UC_X86_REG_EAX)

    def press(self, x: int, y: int, patched: bool = True) -> int:
        self.sites(patched)
        self.calls.clear()
        try:
            return self.call(0x426040, x, y) & 0xFF
        finally:
            self.sites(True)

    def snapshot(self) -> tuple:
        objects = [bytes(self.uc.mem_read(o, 0x60)) for o in self.objects]
        return bytes(self.uc.mem_read(self.state, 0x63E70)), objects, self.rng.getstate()

    def restore(self, snap: tuple) -> None:
        self.uc.mem_write(self.state, snap[0])
        for o, data in zip(self.objects, snap[1]):
            self.uc.mem_write(o, data)
        self.rng.setstate(snap[2])

    def records(self) -> bytes:
        return bytes(self.uc.mem_read(self.state + POT_BASE, 15 * POT_STRIDE))

    def health(self, k: int) -> int:
        return self.emu.read32(self.pot(k) + 0x24, signed=True)

    def kinds(self, k: int) -> list[int]:
        return [self.emu.read32(self.pot(k) + 0xA8 + i * 0x16C + 4) for i in range(60)]

    def hold(self, what: int) -> None:
        self.emu.write32(self.state + HELD, what)

    def close(self) -> None:
        """Back to no zoom: the shears down for a frame."""
        held = self.emu.read32(self.state + HELD)
        self.hold(0)
        self.frame((0, 0))
        self.hold(held)

    def open(self, k: int) -> tuple:
        self.close()
        self.hold(SHEARS)
        self.frame(cell_point(k))
        handled = self.press(*cell_point(k))
        assert handled == 1, "the opening click is handled"
        shown, box = self.zoom()
        assert shown == k, (shown, k)
        return box

    def parts_in_zoom(self, k: int, box: tuple, count: int = 12, steady: bool = False) -> dict:
        """Cursor point -> the part the game's hit test finds under the shears' tip there, for up to
        `count` points spread over the zoomed plant: the plant's pixels in the zoom are those its branches
        change (a frame with them and one with them hidden), each tip well inside them (4 px around)."""
        snap = self.snapshot()
        corner = (box[0] + 6, box[3] - 2)
        shown = self.frame(corner)
        for i in range(60):
            at = self.pot(k) + 0xA8 + i * 0x16C + 4
            if self.emu.read32(at) in (1, 4):
                self.emu.write32(at, 2)
        hidden = self.frame(corner)
        self.restore(snap)
        drawn = {(i // 4) for i in range(0, W * H * 4, 4) if shown[i:i + 3] != hidden[i:i + 3]}
        close = (box[2] - 30, box[1], box[2], box[1] + 30)
        inner = sorted(q for q in drawn
                       if box[0] + 4 <= q % W <= box[2] - 4 and box[1] + 4 <= q // W <= box[3] - 20
                       and not (close[0] <= q % W <= close[2] and q // W <= close[3])
                       and all(q + dx + dy * W in drawn for dx in (-4, 0, 4) for dy in (-4, 0, 4)))
        found = {}
        for q in inner[len(inner) // (2 * count)::max(1, len(inner) // count)][:count]:
            cursor = (q % W + 4, q // W + 16)
            self.frame(cursor)
            part = self.hover(k)
            if part[0] >= 0 and steady:
                for dx, dy in ((3, 0), (-3, 0), (0, 3), (0, -3)):     # not on the edge between two parts
                    self.frame((cursor[0] + dx, cursor[1] + dy))
                    if self.hover(k) != part:
                        part = (-1, -1)
                        break
            if part[0] >= 0:
                found[cursor] = part
        self.restore(snap)
        return found


def _needs():
    ready = UC_HOOK_CODE is not None and T._ready("plant") and (T.VANILLA_DIRS["plant"] / "Images").is_dir()
    return unittest.skipUnless(ready, "needs Unicorn, Capstone and the vanilla Plant Tycoon")


class StockBytesTests(unittest.TestCase):
    """No Unicorn needed: the DLL's sites hold the stock code; the setting, presets and release."""

    def test_the_sites_hold_the_stock_bytes(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("#define DRAW_SITE_VA 0x00428FC0u", source)
        self.assertIn("{ 0xE8, 0xBB, 0xA5, 0xFF, 0xFF }", source)
        self.assertIn("#define PRESS_SITE_VA 0x00426040u", source)
        self.assertIn("{ 0x83, 0xEC, 0x0C, 0x53, 0x55 }", source)
        exe = T.VANILLA_DIRS["plant"] / "Plant Tycoon.exe"
        if not exe.is_file():
            self.skipTest("needs the vanilla Plant Tycoon")
        data = exe.read_bytes()
        for va, stock in SITES.items():
            self.assertEqual(data[va - 0x400000:va - 0x400000 + len(stock)], stock, hex(va))

    def test_the_setting_is_a_default_loader_tail_in_the_presets(self) -> None:
        setting = next(s for s in MANIFEST["settings"] if s["id"] == SETTING)
        self.assertEqual(setting["name"], "Zoom in when pruning")
        self.assertIs(setting["default"], True)
        self.assertEqual(setting["companion"]["loader_tail"], DLL)
        listed = setting["companion"]["files"][0]
        self.assertEqual(listed["size"], len((ROOT / setting["companion"]["source"] / DLL).read_bytes()))
        import test_patch_presets as presets
        self.assertIn(SETTING, presets.DEFAULTS["plant"])
        self.assertIn(SETTING, presets.EXPECTED["owners_defaults"]["plant"])

    def test_the_release_includes_the_dll(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_release
        self.assertIn(f"assets/plant_tycoon_prune_zoom/{DLL}", build_release.bundled_asset_files())

    def test_no_new_visible_text(self) -> None:
        """The zoom draws no words: no string lookup, no text draw (so nothing to translate)."""
        source = SOURCE.read_text(encoding="utf-8")
        for call in ("0x0044CA70", "0x004092A0", "0x004092B0", "mod/"):
            self.assertNotIn(call, source)


@_needs()
class PruneZoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.game = Greenhouse({SETTING})

    @classmethod
    def tearDownClass(cls) -> None:
        del cls.game
        gc.collect()

    def setUp(self) -> None:
        self.game.close()
        self.start = self.game.snapshot()

    def tearDown(self) -> None:
        self.game.restore(self.start)
        self.game.close()

    def test_it_installed(self) -> None:
        self.assertTrue(self.game.world.log(DLL).startswith("Prune Zoom: installed"), self.game.world.log(DLL))
        self.assertEqual(self.game.build.dlls, [DLL])

    def test_without_shears_the_draw_and_clicks_are_stock(self) -> None:
        game = self.game
        for held in (0, 1, 2, 4, 9):
            game.hold(held)
            for k in (7, 0, 14):
                point = cell_point(k)
                on, off = game.frames(point)
                self.assertEqual(on, off, f"held {held}, pot {k}")
                for where in (point, (500, 30), (100, 300)):
                    snap = game.snapshot()
                    on = game.press(*where), game.records(), list(game.calls)
                    game.restore(snap)
                    off = game.press(*where, patched=False), game.records(), list(game.calls)
                    game.restore(snap)
                    self.assertEqual(on, off, f"held {held} at {where}")
                    self.assertEqual(game.zoom()[0], -1)

    def test_with_shears_nothing_shows_until_a_plant_is_clicked(self) -> None:
        game = self.game
        game.hold(SHEARS)
        for k in (7, 2):
            point = cell_point(k)
            on, off = game.frames(point)
            self.assertEqual(on, off, "hovering draws as stock")
        self.assertEqual(game.zoom()[0], -1)

    def test_a_click_on_a_plant_opens_the_zoom_without_pruning(self) -> None:
        game = self.game
        game.hold(SHEARS)
        for k in (7, 0, 14):
            game.close()
            game.frame(cell_point(k))
            before = game.records()
            self.assertEqual(game.press(*cell_point(k)), 1)
            self.assertEqual(game.records(), before, "the opening click prunes nothing")
            self.assertEqual(game.calls, [], "and plays nothing")
            self.assertEqual(game.zoom()[0], k)

    def test_the_zoom_draws_the_box_and_the_bigger_plant(self) -> None:
        game = self.game
        box = game.open(7)
        mouse = (box[0] + 10, box[1] + 60)
        on, off = game.frames(mouse)
        changed = [i // 4 for i in range(0, len(on), 4) if on[i:i + 3] != off[i:i + 3]]
        self.assertTrue(changed)
        xs, ys = [p % W for p in changed], [p // W for p in changed]
        self.assertGreaterEqual(min(xs), box[0])
        self.assertLessEqual(max(xs), box[2])
        self.assertGreaterEqual(min(ys), box[1])
        self.assertLessEqual(max(ys), box[3])
        # the box is the background faded halfway to white where no plant is drawn over it
        x, y = box[0] + 3, box[3] - 3
        at = (y * W + x) * 4
        for c in range(3):
            self.assertGreaterEqual(on[at + c], off[at + c])
        self.assertGreater(len(changed), BOX_W * BOX_H // 2, "the whole box is faded")

    def test_the_box_stays_on_the_screen(self) -> None:
        game = self.game
        for k in PLANTS:
            box = game.open(k)
            self.assertEqual(box, expected_box(k), k)
            self.assertTrue(240 <= box[0] and box[2] < 800 and 0 <= box[1] and box[3] < 506, (k, box))

    def test_a_click_in_the_zoom_cuts_what_the_same_real_click_cuts(self) -> None:
        """The part under the shears in the zoom is the game's own hit test at that point of the bigger
        plant; the same point of the real plant, clicked without the setting, cuts the same part with the
        same result."""
        game = self.game
        k = 7
        box = game.open(k)
        found = game.parts_in_zoom(k, box, count=6, steady=True)
        self.assertGreaterEqual(len(found), 3, "the shears find parts of the zoomed plant")
        checked = 0
        for p in found:
            part = found[p]
            rx, ry = zoom_to_real(k, box, (p[0] - 4, p[1] - 16))
            real = (round(rx) + 4, round(ry) + 16)
            snap = game.snapshot()
            game.frame(p)
            self.assertEqual(game.hover(k), part)
            lit = game.frame(p)                                  # drawn with that part lit
            self.assertEqual(game.hover(k), part)
            game.press(*p)
            zoomed = game.records(), list(game.calls), game.health(k), game.kinds(k)
            game.restore(snap)
            game.close()
            game.frame(real, patched=False)                     # the stock hover at the real point
            self.assertEqual(game.hover(k), part, f"zoom {p} / real {real}")
            game.press(*real, patched=False)
            stock = game.records(), list(game.calls), game.health(k), game.kinds(k)
            game.restore(snap)
            self.assertEqual(zoomed, stock, f"zoom {p} / real {real}")
            self.assertNotEqual(zoomed[0], snap[0][POT_BASE:POT_BASE + 15 * POT_STRIDE], "it pruned")
            self.assertTrue(lit)
            checked += 1
            game.open(k)
        self.assertGreaterEqual(checked, 3)

    def test_the_x_closes_the_zoom_without_pruning(self) -> None:
        game = self.game
        box = game.open(7)
        x, y = box[2] - 15, box[1] + 15
        game.frame((x, y))
        before = game.records()
        self.assertEqual(game.press(x, y), 1)
        self.assertEqual(game.records(), before, "the X prunes nothing")
        self.assertEqual(game.calls, [])
        self.assertEqual(game.zoom()[0], -1)
        on, off = game.frames((x, y))
        self.assertEqual(on, off, "closed: the stock draw")

    def test_it_reopens_on_another_plant(self) -> None:
        game = self.game
        box = game.open(7)
        game.press(box[2] - 15, box[1] + 15)
        self.assertEqual(game.zoom()[0], -1)
        game.frame(cell_point(12))
        self.assertEqual(game.press(*cell_point(12)), 1)
        self.assertEqual(game.zoom()[0], 12)
        box = game.open(7)
        game.press(box[2] - 15, box[1] + 15)
        self.assertEqual(game.press(*cell_point(7)), 1, "the same plant opens again on a new click")
        self.assertEqual(game.zoom()[0], 7)

    def test_a_click_outside_the_box_closes_it_without_pruning(self) -> None:
        game = self.game
        box = game.open(2)                                  # the top row's box: rows 0-2, columns 1-3
        self.assertLess(box[2], cell_point(14)[0])
        before = game.records()
        self.assertEqual(game.press(*cell_point(14)), 1, "a click on another plant only closes the zoom")
        self.assertEqual(game.records(), before)
        self.assertEqual(game.zoom()[0], -1)
        game.open(2)
        snap = game.snapshot()
        on = game.press(100, 300), game.records(), list(game.calls)           # the left panel: the game's
        self.assertEqual(game.zoom()[0], -1)
        game.restore(snap)
        off = game.press(100, 300, patched=False), game.records(), list(game.calls)
        self.assertEqual(on, off)

    def test_putting_the_shears_down_closes_it(self) -> None:
        game = self.game
        for other in (0, 1, 4):
            game.open(7)
            game.hold(other)
            game.frame(cell_point(7))
            self.assertEqual(game.zoom()[0], -1, other)
            game.hold(SHEARS)
            on, off = game.frames(cell_point(7))
            self.assertEqual(on, off)

    def test_only_the_zoomed_plant_keeps_a_part_under_the_shears(self) -> None:
        game = self.game
        box = game.open(7)
        for p in list(game.parts_in_zoom(7, box, count=3)):
            game.frame(p)
            for k in PLANTS:
                if k != 7:
                    self.assertEqual(game.hover(k)[0], -1, (p, k))


@_needs()
class WithTheOtherGreenhouseSettingsTests(unittest.TestCase):
    """Beside Extra Greenhouses, Greenhouse Counts, Click to Deselect, Sort Seeds and Unicode Text."""

    def test_all_installed_and_the_zoom_works(self) -> None:
        others = {"extra_greenhouses", "tank_greenhouse_counts", "greenhouse_click_deselect", "sort_seeds",
                  "unicode_ingame_fonts"}
        game = Greenhouse({SETTING} | others)
        try:
            self.assertEqual(game.world.top_level[-1], DLL, "the last tail")
            self.assertTrue(game.world.log(DLL).startswith("Prune Zoom: installed"))
            for name in ("Click to Deselect.dll", "Extra Greenhouses.dll"):
                self.assertIn(name, game.build.dlls)
            box = game.open(7)
            self.assertEqual(box, expected_box(7))
            self.assertEqual(game.press(box[2] - 15, box[1] + 15), 1)
            self.assertEqual(game.zoom()[0], -1)
        finally:
            del game
            gc.collect()


@_needs()
class PreviewTests(unittest.TestCase):
    def test_the_preview_is_the_games_own_drawing(self) -> None:
        """Downloads/Prune zoom preview.png: the greenhouse's background, the benches, the zoom on the
        middle plant with a part under the shears lit, and the shears, all drawn by the game's code."""
        game = Greenhouse({SETTING})
        try:
            background = game.picture("main_bg.png")
            game.background = bytes(background.data[:W * H * 4])
            box = game.open(7)
            found = game.parts_in_zoom(7, box, count=6)
            point = sorted(found)[len(found) // 2] if found else (box[0] + 140, box[1] + 200)
            game.frame(point)
            game.frame(point)
            mx, my = point
            level = 0
            game.world.call(0x4208F0, 0xA1, level * 2, mx - 0x16, my - 0x16, 0x3F800000, 100, 1,
                            ecx=game.emu.read32(game.scene + 0x6C) and game.sprites)
            data = bytes(game.uc.mem_read(game.pixels, W * H * 4))
            image = pi.Image(W, H, bytes(b if i % 4 != 3 else 255 for i, b in enumerate(data)))
            if PREVIEW.parent.is_dir():
                PREVIEW.write_bytes(pi.encode_png(image))
            self.assertTrue(found)
        finally:
            del game
            gc.collect()


if __name__ == "__main__":
    unittest.main()
