"""Zoom in when pruning ("Prune Zoom.dll", Plant Tycoon).

The emulated tests run the patched executable in Unicorn (tests/test_every_patch.py's World: the real
startup loader loads the real DLL) with a real 800 x 600 screen: the game's own bench draw (0x423580),
pot draw (0x42F740), plant draw (vtable slots 7, 10, 13, 11), sprite draw (0x4208F0), scaler (0x404610),
FillRect (0x407B80) and pixel read (0x407AD0) draw the vanilla game's pictures into it, and the game's own
press (0x426040) prunes, reached through the greenhouse's mouse slot. Only SDL's few calls (map a colour,
fill, blit, lock), the mouse position, operator new, text, the stock mouse's own helpers and the press's
sounds and messages are stand-ins. Each check is made twice where it can be: with the DLL's draw call and
mouse wrapper in place and with the stock ones put back. The zoom prunes a working copy; the X writes it
into the real plant, and that is compared with the same stock prunes made in order.
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
DRAW_SITE, MOUSE_SLOT, ACTIVATE_SLOT, SAVE_SLOT = 0x428FC0, 0x469224, 0x469244, 0x467D6C
STOCK_MOUSE, STOCK_ACTIVATE, PRESS = 0x4273D0, 0x4231E0, 0x426040
SITES = {DRAW_SITE: bytes.fromhex("E8BBA5FFFF"),           # call 0x423580, the benches' plants
         MOUSE_SLOT: struct.pack("<I", STOCK_MOUSE)}       # the greenhouse's mouse slot
UNDO, REDO, CLOSE = 0, 1, 2
PREVIEW = Path.home() / "Downloads" / "Prune zoom preview.png"
W, H = 800, 600
HELD, SHEARS = 0x56C, 3
POT_BASE, POT_STRIDE = 0x2188, 0x5600
BOX_W, BOX_H, ZOOM = 279, 432, 2.0
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
    from store_emulator import THUNKS, THUNK_SIZE
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
    """The same box for every pot: centred on the benches (k is the pot, which no longer moves it)."""
    cx, cy = 270 + 92 * 5 // 2, 43 + 144 * 3 // 2
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
        # the stock mouse's own helpers (its hint, the double-click clock, the release) and what the
        # activation and the Save call are stand-ins; the press runs
        world.stand_in_callees(STOCK_MOUSE, keep={PRESS, POT_AT, 0x435FF0, 0x423AA0, 0x423A10, 0x4165A0, 0x424680,
                                                  PLANT_OF, 0x41DE20})
        for address, name in ((STOCK_ACTIVATE, "activation"), (0x403690, "write the save"),
                              (0x4092A0, "text"), (0x402380, "text width")):
            emu.hook(address, self._recorded(name) if address != 0x402380 else (lambda e: 30), world.pops(address))

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

    def zoom(self) -> dict:
        out = self._zeroed(44)
        self.world.call(self.zoom_state, out)
        v = struct.unpack("<11i", self.uc.mem_read(out, 44))
        return {"pot": v[0], "steps": v[1], "box": v[2:6], "at": v[6], "prunes": v[7], "work": v[8] & 0xFFFFFFFF,
                "part": (v[9], v[10])}

    def shown(self) -> int:
        return self.zoom()["pot"]

    def work(self) -> bytes:
        z = self.zoom()
        return bytes(self.uc.mem_read(z["work"], POT_STRIDE)) if z["pot"] >= 0 else b""

    def sites(self, patched: bool) -> None:
        for va, stock in SITES.items():
            self.uc.mem_write(va, self.patched[va] if patched else stock)
            self.uc.ctl_remove_cache(va, va + len(stock))

    def frame(self, mouse: tuple[int, int], patched: bool = True) -> bytes:
        """One frame of the benches (and the zoom): the background, then the overlay's call at 0x428FC0."""
        self.mouse[:] = mouse
        self.uc.mem_write(self.pixels, self.background)
        self.sites(patched)
        try:
            self.call(self.on_draw if patched else 0x423580)
        finally:
            self.sites(True)
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

    def call(self, address: int, *args: int, ecx: int | None = None) -> int:
        """A thiscall (on the scene by default), with room for the zoom's big plant (the scaler runs per pixel)."""
        emu, uc = self.emu, self.uc
        esp = T.E.STACK + T.E.STACK_SIZE - 0x1000
        for value in reversed(args):
            esp -= 4
            emu.write32(esp, value)
        esp -= 4
        emu.write32(esp, T.E.RETURN)
        uc.reg_write(T.X.UC_X86_REG_ESP, esp)
        uc.reg_write(T.X.UC_X86_REG_ECX, self.scene if ecx is None else ecx)
        uc.reg_write(T.X.UC_X86_REG_FPCW, 0x027F)
        self.world.run(address, T.E.RETURN, f"0x{address:X}", count=400_000_000)
        return uc.reg_read(T.X.UC_X86_REG_EAX)

    def mouse_event(self, kind: int, x: int, y: int, patched: bool = True) -> int:
        """The greenhouse's mouse slot (1 move, 2 press, 3 release), the DLL's wrapper or the stock one."""
        self.calls.clear()
        self.mouse[:] = (x, y)
        return self.call(self.emu.read32(MOUSE_SLOT) if patched else STOCK_MOUSE, kind, x, y) & 0xFF

    def press(self, x: int, y: int, patched: bool = True) -> int:
        return self.mouse_event(2, x, y, patched)

    def stock_prune(self, x: int, y: int) -> int:
        """The game's own press, as the stock mouse makes it (no zoom)."""
        self.calls.clear()
        return self.call(PRESS, x, y) & 0xFF

    def snapshot(self) -> tuple:
        objects = [bytes(self.uc.mem_read(o, 0x58)) for o in self.objects]
        return bytes(self.uc.mem_read(self.state, 0x63E70)), objects, self.rng.getstate()

    def restore(self, snap: tuple) -> None:
        self.uc.mem_write(self.state, snap[0])
        for o, data in zip(self.objects, snap[1]):
            self.uc.mem_write(o, data)
        self.rng.setstate(snap[2])

    def records(self) -> bytes:
        return bytes(self.uc.mem_read(self.state + POT_BASE, 15 * POT_STRIDE))

    def pruned(self) -> int:
        return self.emu.read32(self.state + 0x4C)

    def hold(self, what: int) -> None:
        self.emu.write32(self.state + HELD, what)

    def close(self) -> None:
        """Back to no zoom (its X, if open), the shears in the hand."""
        self.hold(SHEARS)
        z = self.zoom()
        if z["pot"] >= 0:
            self.press(*button_point(z["box"], CLOSE))
        assert self.shown() == -1

    def open(self, k: int) -> tuple:
        self.close()
        self.frame(cell_point(k))
        handled = self.press(*cell_point(k))
        assert handled == 1, "the opening click is handled"
        z = self.zoom()
        assert z["pot"] == k, (z, k)
        return z["box"]

    def parts_in_zoom(self, k: int, box: tuple, count: int = 12, steady: bool = False) -> dict:
        """Cursor point -> the part the game's hit test finds under the shears' tip there, for up to
        `count` points spread over the zoomed plant: the plant's pixels in the zoom are those its branches
        change (a frame with them and one with them hidden in the working copy), each tip well inside them."""
        snap = self.snapshot()
        work = self.zoom()["work"]
        saved = bytes(self.uc.mem_read(work, POT_STRIDE))
        corner = (box[0] + 6, box[3] - 2)
        shown = self.frame(corner)
        for i in range(60):
            at = work + 0xA8 + i * 0x16C + 4
            if self.emu.read32(at) in (1, 4):
                self.emu.write32(at, 2)
        hidden = self.frame(corner)
        self.uc.mem_write(work, saved)
        self.restore(snap)
        drawn = {(i // 4) for i in range(0, W * H * 4, 4) if shown[i:i + 3] != hidden[i:i + 3]}
        top = (box[2] - 80, box[1], box[2], box[1] + 50)               # the buttons and a label
        inner = sorted(q for q in drawn
                       if box[0] + 4 <= q % W <= box[2] - 4 and box[1] + 4 <= q // W <= box[3] - 20
                       and not (top[0] <= q % W <= top[2] and q // W <= top[3])
                       and all(q + dx + dy * W in drawn for dx in (-4, 0, 4) for dy in (-4, 0, 4)))
        found = {}
        for q in inner[len(inner) // (2 * count)::max(1, len(inner) // count)][:count]:
            cursor = (q % W + 4, q // W + 16)
            self.frame(cursor)
            part = self.zoom_part()
            if part[0] >= 0 and steady:
                for dx, dy in ((3, 0), (-3, 0), (0, 3), (0, -3)):     # not on the edge between two parts
                    self.frame((cursor[0] + dx, cursor[1] + dy))
                    if self.zoom_part() != part:
                        part = (-1, -1)
                        break
            if part[0] >= 0:
                found[cursor] = part
        self.uc.mem_write(work, saved)
        self.restore(snap)
        return found

    def zoom_part(self) -> tuple[int, int]:
        """The part the zoom found under the tip last frame."""
        return self.zoom()["part"]


def button_point(box: tuple, which: int) -> tuple[int, int]:
    """The middle of a zoom button (right to left from the box's top-right corner: X, Redo, Undo)."""
    right = box[2] - 5 - (2 - which) * 24
    return right - 9, box[1] + 5 + 10


def _needs():
    ready = (UC_HOOK_CODE is not None and T._ready("plant") and (T.VANILLA_DIRS["plant"] / "Images").is_dir())
    return unittest.skipUnless(ready, "needs Unicorn, Capstone, numpy and the vanilla Plant Tycoon")


class StockBytesTests(unittest.TestCase):
    """No Unicorn needed: the sites hold the stock code; the setting, presets, release and texts."""

    def test_the_sites_hold_the_stock_bytes(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("#define DRAW_SITE_VA 0x00428FC0u", source)
        self.assertIn("{ 0xE8, 0xBB, 0xA5, 0xFF, 0xFF }", source)
        for define in ("#define MOUSE_SLOT_VA 0x00469224u", "#define MOUSE_STOCK 0x004273D0u",
                       "#define ACTIVATE_SLOT_VA 0x00469244u", "#define ACTIVATE_STOCK 0x004231E0u",
                       "#define SAVE_SLOT_VA 0x00467D6Cu", "#define SAVE_STOCK 0x0041D120u"):
            self.assertIn(define, source)
        exe = T.VANILLA_DIRS["plant"] / "Plant Tycoon.exe"
        if not exe.is_file():
            self.skipTest("needs the vanilla Plant Tycoon")
        data = exe.read_bytes()
        at = lambda va, n: data[va - 0x400000:va - 0x400000 + n]  # noqa: E731
        self.assertEqual(at(DRAW_SITE, 5), SITES[DRAW_SITE])
        for va, stock in ((0x469224, 0x4273D0), (0x469244, 0x4231E0), (0x467D6C, 0x41D120)):
            self.assertEqual(struct.unpack("<I", at(va, 4))[0], stock, hex(va))

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

    def test_the_button_names_are_translatable(self) -> None:
        import translation_strings as ts
        mine = {m.english: ts.mod_key(m) for m in ts.MOD_STRINGS if m.dll == DLL}
        self.assertEqual(set(mine), {"Undo", "Redo", "Close"})
        for english, key in mine.items():
            self.assertTrue(key.startswith(f"mod/prune_zoom.{english.lower()}~"), key)
        french = (ROOT / "translations" / "plant" / "fr.tsv").read_text(encoding="utf-8")
        for english, word in (("Undo", "Annuler"), ("Redo", "Rétablir"), ("Close", "Fermer")):
            self.assertIn(f"{mine[english]}\t{english}\t{word}\t", french)
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('{ "Undo", "Redo", "Close" }', source)
        self.assertNotIn("0x0044CA70", source, "no game string ids: the DLL's own texts, which Translations.dll swaps")


class Zoomed(unittest.TestCase):
    """One game for the class; each test starts from the same state with the zoom closed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.game = Greenhouse({SETTING})
        cls.game.hold(SHEARS)
        cls.game.frame((0, 0), patched=False)            # the part places the draws note, once
        cls.start = cls.game.snapshot()

    @classmethod
    def tearDownClass(cls) -> None:
        del cls.game
        gc.collect()

    def setUp(self) -> None:
        self.game.restore(self.start)
        self.game.close()
        self.game.restore(self.start)

    def tearDown(self) -> None:
        self.game.close()


@_needs()
class PruneZoomTests(Zoomed):
    def test_it_installed(self) -> None:
        self.assertTrue(self.game.world.log(DLL).startswith("Prune Zoom: installed"), self.game.world.log(DLL))
        self.assertEqual(self.game.build.dlls, [DLL])

    def test_without_shears_the_draw_and_clicks_are_stock(self) -> None:
        game = self.game
        for held in (0, 1, 4):
            game.hold(held)
            for k in (7, 14):
                point = cell_point(k)
                on, off = game.frames(point)
                self.assertEqual(on, off, f"held {held}, pot {k}")
                for where in (point, (500, 30), (100, 300)):
                    snap = game.snapshot()
                    a = game.press(*where), game.records(), list(game.calls)
                    game.restore(snap)
                    b = game.press(*where, patched=False), game.records(), list(game.calls)
                    game.restore(snap)
                    self.assertEqual(a, b, f"held {held} at {where}")
                    self.assertEqual(game.shown(), -1)

    def test_with_shears_nothing_shows_until_a_plant_is_clicked(self) -> None:
        game = self.game
        for k in (7, 2):
            on, off = game.frames(cell_point(k))
            self.assertEqual(on, off, "hovering draws as stock")
        self.assertEqual(game.shown(), -1)
        snap = game.snapshot()
        a = game.press(500, 30), game.records(), list(game.calls)            # not on a plant: the game's
        game.restore(snap)
        b = game.press(500, 30, patched=False), game.records(), list(game.calls)
        self.assertEqual(a, b)

    def test_a_click_on_a_plant_opens_the_zoom_without_pruning(self) -> None:
        game = self.game
        for k in (7, 0, 14):
            game.close()
            game.frame(cell_point(k))
            before = game.records(), game.pruned()
            self.assertEqual(game.press(*cell_point(k)), 1)
            self.assertEqual((game.records(), game.pruned()), before, "the opening click prunes nothing")
            self.assertEqual(game.calls, [], "and plays nothing")
            self.assertEqual(game.shown(), k)
            self.assertEqual(game.work(), bytes(game.uc.mem_read(game.pot(k), POT_STRIDE)), "the copy is the plant")

    def test_the_box_is_grey_and_see_through_and_only_the_box_changes(self) -> None:
        game = self.game
        box = game.open(7)
        mouse = (box[0] + 10, box[3] - 10)
        on, off = game.frames(mouse)
        changed = [i // 4 for i in range(0, len(on), 4) if on[i:i + 3] != off[i:i + 3]]
        xs, ys = [p % W for p in changed], [p // W for p in changed]
        self.assertTrue(box[0] <= min(xs) and max(xs) <= box[2] and box[1] <= min(ys), (min(xs), max(xs), min(ys)))
        self.assertLessEqual(max(ys), max(box[3], box[1] + 60), "the box (and a button's name under it)")
        for x, y in ((box[0] + 3, box[3] - 3), (box[0] + 40, box[1] + 40)):
            at = (y * W + x) * 4
            for c in range(3):
                self.assertAlmostEqual(on[at + c], (off[at + c] + 128) / 2, delta=2, msg=(x, y, c))

    def test_behind_the_box_the_benches_are_drawn_as_without_the_zoom(self) -> None:
        """The screen just before the box is blended over it (the FillRect's call) is the stock frame."""
        game = self.game
        box = game.open(7)
        caught = []

        def at_fill(uc, address, size, data):
            if not caught:
                caught.append(bytes(uc.mem_read(game.pixels, W * H * 4)))
        hook = game.uc.hook_add(UC_HOOK_CODE, at_fill, begin=0x407B80, end=0x407B80)
        try:
            snap = game.snapshot()
            game.frame((box[0] + 100, box[1] + 200))
        finally:
            game.uc.hook_del(hook)
        game.restore(snap)
        stock = game.frame((box[0] + 100, box[1] + 200), patched=False)
        self.assertEqual(caught[0], stock)

    def test_the_box_stays_on_the_screen(self) -> None:
        game = self.game
        for k in PLANTS:
            box = game.open(k)
            self.assertEqual(box, expected_box(k), k)
            self.assertTrue(240 <= box[0] and box[2] < 800 and 0 <= box[1] and box[3] < 506, (k, box))
        self.assertEqual(len({game.open(k) for k in PLANTS}), 1, "the box moves with the pot")

    def test_no_plant_changes_while_the_zoom_is_open(self) -> None:
        """Every pot record and the prune count stay byte for byte as without the zoom while it draws, is
        pruned, undone and redone; only the X writes the prunes."""
        game = self.game
        before = game.records(), game.pruned()
        box = game.open(7)
        found = game.parts_in_zoom(7, box, count=4)
        self.assertTrue(found)
        for p in list(found)[:2]:
            game.frame(p)
            game.press(*p)
            self.assertEqual((game.records(), game.pruned()), before, f"pruned at {p}: only the copy")
        self.assertNotEqual(game.work(), before[0][7 * POT_STRIDE:8 * POT_STRIDE], "the copy is pruned")
        for which in (UNDO, REDO, UNDO):
            game.frame(button_point(box, which))
            game.press(*button_point(box, which))
            self.assertEqual((game.records(), game.pruned()), before, which)
        for mouse in ((box[0] + 50, box[1] + 100), (100, 300), cell_point(14)):
            game.frame(mouse)
            self.assertEqual((game.records(), game.pruned()), before, mouse)

    def test_after_the_x_the_plant_is_the_same_stock_prunes_in_order(self) -> None:
        game = self.game
        k = 7
        box = game.open(k)
        found = game.parts_in_zoom(k, box, count=6, steady=True)
        self.assertGreaterEqual(len(found), 2, "the shears find parts of the zoomed plant")
        points = list(found)[:2]
        snap = game.snapshot()
        for p in points:
            game.frame(p)
            self.assertEqual(game.zoom_part(), found[p])
            game.press(*p)
        calls = list(game.calls)
        game.press(*button_point(box, CLOSE))
        zoomed = game.records(), game.pruned(), game.shown()
        game.restore(snap)
        game.close()
        game.restore(snap)
        for p in points:
            rx, ry = zoom_to_real(k, box, (p[0] - 4, p[1] - 16))
            real = (round(rx) + 4, round(ry) + 16)
            game.frame(real, patched=False)
            self.assertEqual(game.hover(k), found[p], f"zoom {p} / real {real}")
            game.stock_prune(*real)
        stock = game.records(), game.pruned(), -1
        self.assertEqual(calls, game.calls, "the same sounds and select as the stock prune")
        self.assertEqual(zoomed, stock)
        self.assertEqual(stock[1], self.start_pruned() + 2)
        self.assertNotEqual(stock[0], snap[0][POT_BASE:POT_BASE + 15 * POT_STRIDE], "it pruned")

    def start_pruned(self) -> int:
        return struct.unpack_from("<I", self.start[0], 0x4C)[0]

    def test_undo_redo_and_a_new_prune(self) -> None:
        game = self.game
        box = game.open(7)
        found = list(game.parts_in_zoom(7, box, count=6))
        self.assertGreaterEqual(len(found), 2)
        undo, redo = button_point(box, UNDO), button_point(box, REDO)
        game.frame(found[0])
        copy0 = game.work()
        game.press(*found[0])
        pruned = game.work()
        self.assertNotEqual(pruned, copy0)
        self.assertEqual(game.zoom()["prunes"], 1)
        game.press(*undo)
        self.assertEqual(game.work(), copy0, "undo: the copy as it was, byte for byte")
        self.assertEqual(game.zoom()["prunes"], 0)
        game.press(*redo)
        self.assertEqual(game.work(), pruned, "redo: the prune's own result")
        self.assertEqual(game.zoom()["prunes"], 1)
        game.press(*undo)
        game.frame(found[1])
        game.press(*found[1])
        z = game.zoom()
        self.assertEqual((z["steps"], z["at"]), (2, 1), "the new prune dropped the redo")
        before = game.work()
        game.press(*redo)
        self.assertEqual(game.work(), before, "nothing to redo")
        game.press(*undo)
        game.press(*undo)                                   # nothing more to undo
        self.assertEqual(game.work(), copy0)
        game.press(*button_point(box, CLOSE))
        self.assertEqual(game.records(), self.start[0][POT_BASE:POT_BASE + 15 * POT_STRIDE], "all undone: no change")
        self.assertEqual(game.pruned(), self.start_pruned())

    def test_the_buttons_are_grey_with_nothing_to_do_and_never_prune(self) -> None:
        game = self.game
        box = game.open(7)

        def face(which: int) -> tuple:
            x, y = button_point(box, which)
            screen = game.frame((box[0] + 20, box[3] - 20))
            at = ((y + 6) * W + x - 7) * 4
            return tuple(screen[at:at + 3])
        grey, light = (198, 198, 198), (237, 242, 219)
        self.assertEqual((face(UNDO), face(REDO), face(CLOSE)), (grey, grey, light))
        for which in (UNDO, REDO):
            before = game.work(), game.records(), game.pruned()
            game.frame(button_point(box, which))
            self.assertEqual(game.zoom_part(), (-1, -1), "no part under the shears on a button")
            self.assertEqual(game.press(*button_point(box, which)), 1)
            self.assertEqual((game.work(), game.records(), game.pruned()), before, which)
            self.assertEqual(game.calls, [])
        p = list(game.parts_in_zoom(7, box, count=4))[0]
        game.frame(p)
        game.press(*p)
        self.assertEqual((face(UNDO), face(REDO)), (light, grey))
        game.press(*button_point(box, UNDO))
        self.assertEqual((face(UNDO), face(REDO)), (grey, light))

    def test_the_zoom_is_modal(self) -> None:
        """Clicks outside the box and a tool put down neither close nor save it; nothing is picked up."""
        game = self.game
        box = game.open(2)
        p = list(game.parts_in_zoom(2, box, count=4))[0]
        game.frame(p)
        game.press(*p)
        work, records = game.work(), game.records()
        for where in ((33, 210), (100, 300), cell_point(14), (780, 470), (500, 490)):
            for kind in (2, 3):
                self.assertEqual(game.mouse_event(kind, *where), 1, where)
                self.assertEqual((game.shown(), game.work(), game.records()), (2, work, records), where)
                self.assertEqual(game.emu.read32(game.state + HELD), SHEARS)
                self.assertEqual(game.calls, [])
        game.hold(0)                                         # the hand empties by other means: still open
        game.frame(cell_point(2))
        self.assertEqual((game.shown(), game.records()), (2, records))
        game.hold(SHEARS)

    def test_leaving_the_greenhouse_or_saving_saves_the_prunes(self) -> None:
        game = self.game
        box = game.open(7)
        p = list(game.parts_in_zoom(7, box, count=4))[0]
        snap = game.snapshot()
        game.frame(p)
        game.press(*p)
        game.call(game.emu.read32(SAVE_SLOT), 1, ecx=game.state)
        saved = game.records(), game.pruned()
        self.assertEqual(game.shown(), 7, "a save keeps the zoom open")
        self.assertEqual(game.zoom()["steps"], 1, "on a fresh copy")
        self.assertNotEqual(saved[0], snap[0][POT_BASE:POT_BASE + 15 * POT_STRIDE])
        self.assertEqual(saved[1], self.start_pruned() + 1)
        game.press(*button_point(box, CLOSE))
        self.assertEqual((game.records(), game.pruned()), saved, "nothing more to write")
        # leaving the greenhouse: the activation slot
        game.restore(snap)
        game.close()
        game.restore(snap)
        box = game.open(7)
        game.frame(p)
        game.press(*p)
        game.call(game.emu.read32(ACTIVATE_SLOT), 0)
        self.assertEqual(game.shown(), -1)
        self.assertEqual((game.records(), game.pruned()), saved, "the same prune, saved on leaving")


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
            for name in ("Click to Deselect.dll", "Extra Greenhouses.dll", "Greenhouse Counts.dll"):
                self.assertIn(name, game.build.dlls)
            game.hold(SHEARS)
            box = game.open(7)
            self.assertEqual(box, expected_box(7))
            self.assertEqual(game.press(770, 260), 1, "modal: the extra greenhouses' arrow is not taken")
            self.assertEqual(game.shown(), 7)
            self.assertEqual(game.press(*button_point(box, CLOSE)), 1)
            self.assertEqual(game.shown(), -1)
        finally:
            del game
            gc.collect()


def dead_grass() -> "pp.Plant":
    """A grown Grass with some leaves dead: branch type 4, which the branch draw (0x42E690) draws from the
    foliage's dead sheet (Lemon Grass_dead.png), as the game leaves a leaf that died (the age-7 roll, or
    drying out)."""
    plant = pp.grow_custom(3, 5, 1, "max")
    leaves = [b for b in plant.branches[1:] if b.kind == 1]
    for b in leaves[::2]:
        b.kind = 4
    return plant


def grown_reptans() -> "pp.Plant":
    """A fully grown Reptans (age 28, the largest size, its most-branched starting shape)."""
    plant = pp.grow_custom(1, 9, 4, "max")
    plant.size = 110
    return plant


PREVIEWS = {
    PREVIEW: (7, lambda: pp.grow_custom(7, 3, 1, "max"), False),
    PREVIEW.with_name("Prune zoom preview - Grass.png"): (7, dead_grass, True),
    PREVIEW.with_name("Prune zoom preview - Reptans.png"): (7, grown_reptans, False),
}


@_needs()
class PreviewTests(unittest.TestCase):
    def test_the_previews_are_the_games_own_drawing(self) -> None:
        """Downloads/Prune zoom preview*.png: the greenhouse's background, the benches, the zoom on the
        middle plant with a part under the shears lit after a prune (so Undo is live), and the shears, all
        drawn by the game's code."""
        game = Greenhouse({SETTING})
        try:
            background = game.picture("main_bg.png")
            game.background = bytes(background.data[:W * H * 4])
            game.hold(SHEARS)
            for path, (k, make, on_dead) in PREVIEWS.items():
                game.close()
                game.uc.mem_write(game.pot(k), make().to_record())
                game.emu.write32(game.manager + 8 + k * 4, 0)      # the game makes the pot's plant object again
                game.objects = [game.plant(j) for j in PLANTS]
                game.frame((0, 0), patched=False)
                box = game.open(k)
                found = game.parts_in_zoom(k, box, count=14)
                self.assertTrue(found, path.name)
                points = sorted(found, key=lambda q: -found[q][0])      # the tips first (the last branches)
                game.frame(points[0])
                game.press(*points[0])                      # one small prune, so Undo is live
                cut = found[points[0]][0]
                kinds = [game.emu.read32(game.zoom()["work"] + 0xA8 + i * 0x16C + 4) for i in range(60)]
                left = [q for q in points[1:] if found[q][0] != cut and kinds[found[q][0]] in (1, 4)]
                dead = [q for q in left if kinds[found[q][0]] == 4]
                point = (dead if on_dead and dead else left or points)[0]
                game.frame(point)                           # the part under the tip, found
                obj = game.plant(k)
                game.emu.write32(obj + 0x30, 80)            # the flash's angle: the next frame is 90, the whitest
                game.frame(point)
                mx, my = point
                game.call(0x4208F0, 0xA1, 0, mx - 0x16, my - 0x16, 0x3F800000, 100, 1, ecx=game.sprites)
                data = bytes(game.uc.mem_read(game.pixels, W * H * 4))
                image = pi.Image(W, H, bytes(b if i % 4 != 3 else 255 for i, b in enumerate(data)))
                if path.parent.is_dir():
                    path.write_bytes(pi.encode_png(image))
        finally:
            del game
            gc.collect()



# ------------------------------------------------------------------ pixel accuracy, densely

PART_CALL, PART_BACK, FLOWER_CALL, FLOWER_BACK = 0x42E7E7, 0x42E7E9, 0x42EB3D, 0x42EB42


def bushy_fern() -> "pp.Plant":
    return pp.grow_custom(7, 3, 4, "max")


def budding_maple() -> "pp.Plant":
    return pp.grow_custom(13, 5, 2, "budding")


# Every kind of part the stock shears cut (0x42D880 on the part the hit test found): a branch the branch
# draw (0x42E690) draws (type 1 alive: leaves and stems; type 4 dead: brown leaves and stems) and a flower
# the flower draw (0x42D9C0) draws on a living plant (state 1: a bud from age 21, a flower head from 24).
KINDS = ("live branch", "dead branch", "bud", "flower head")
ACCURACY_PLANTS = {"Grass with dead leaves": dead_grass, "Reptans": grown_reptans, "Fern in bloom": bushy_fern,
                   "Maple in bud": budding_maple}


class HitMaps:
    """Every pixel's part, as the game's own hit test sees it: each part draw (slot 11, called at 0x42E7E7)
    and flower draw (0x42D9C0, called at 0x42EB3D) makes the part under the tip the last one whose drawing
    changes the tip's pixel (0x42CFE0 reads it before and after), so one draw, with the screen taken before
    and after each part, gives the part for every pixel at once. A frame has three plant draws (slot 10),
    told apart by what the object reads (+8) and the scale: the benches' (the real plant), the zoom's hit
    test (the working copy at its real size), the zoom's picture (the copy at twice the size)."""

    def __init__(self, game: "Greenhouse", k: int) -> None:
        self.game, self.k = game, k
        self.maps: dict[str, dict] = {"real": {}, "find": {}, "zoom": {}}
        self.every: dict[str, dict] = {"real": {}, "find": {}, "zoom": {}}     # every part drawn on a pixel
        self.phase = "real"
        self._before = None

    def _screen(self):
        g = self.game
        return np.frombuffer(bytes(g.uc.mem_read(g.pixels, W * H * 4)), np.uint32).reshape(H, W)

    def _draw(self, uc, address, size, data):
        g = self.game
        obj = uc.reg_read(T.X.UC_X86_REG_ECX)
        if obj != self.obj:                          # (no emulated calls in a hook: all read beforehand)
            return
        scale = struct.unpack("<f", struct.pack("<I", g.emu.read32(uc.reg_read(T.X.UC_X86_REG_ESP) + 12)))[0]
        self.phase = "zoom" if scale > 1.5 else "find" if g.emu.read32(obj + 8) == self.work else "real"

    def _call(self, uc, address, size, data):
        self._before = self._screen()

    def _back(self, uc, address, size, data):
        g = self.game
        esp = uc.reg_read(T.X.UC_X86_REG_ESP)
        branch = g.emu.read32(esp + 0x40, signed=True)
        flower = g.emu.read32(esp + 0x54, signed=True) if address == FLOWER_BACK else -1
        ys, xs = np.nonzero(self._screen() != self._before)
        target, every = self.maps[self.phase], self.every[self.phase]
        for x, y in zip(xs.tolist(), ys.tolist()):
            target[(x, y)] = (branch, flower)
            every.setdefault((x, y), set()).add((branch, flower))

    def take(self, mouse: tuple[int, int]) -> None:
        g = self.game
        self.obj, self.work = g.plant(self.k), g.zoom()["work"]
        draw = g.emu.read32(g.emu.read32(self.obj) + 0x28)
        hooks = [g.uc.hook_add(UC_HOOK_CODE, self._draw, begin=draw, end=draw)]
        hooks += [g.uc.hook_add(UC_HOOK_CODE, self._call, begin=a, end=a) for a in (PART_CALL, FLOWER_CALL)]
        hooks += [g.uc.hook_add(UC_HOOK_CODE, self._back, begin=a, end=a) for a in (PART_BACK, FLOWER_BACK)]
        try:
            g.frame(mouse)
        finally:
            for h in hooks:
                g.uc.hook_del(h)


@_needs()
class PixelAccuracyTests(unittest.TestCase):
    """The part the zoom lights and cuts is the part the game's own prune hit test picks at the shears' cut
    point mapped back to the real plant (the cut point is the cursor less (4, 16), the stock hotspot; the
    zoom maps it back through its scale and offset). For every second zoomed pixel over the zoomed plant
    (every pixel of the real plant) of four plants, which between them have every kind of part the shears
    cut: the zoom's hit test (the working copy at its real size, in a frame) against the bench's stock hit
    test, whole maps from one frame each; then through the DLL at samples of every kind: the part found,
    its flash on exactly that part's pixels in the zoom, and a click there cutting what the stock prune at
    the real point cuts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.game = Greenhouse({SETTING})
        cls.game.background = bytes(cls.game.picture("main_bg.png").data[:W * H * 4])
        for k in PLANTS:
            if k != 7:
                cls.game.uc.mem_write(cls.game.pot(k), bytes(POT_STRIDE))
        cls.counts: dict = {}
        cls.clicked: set = set()

    @classmethod
    def tearDownClass(cls) -> None:
        for name, (agree, total, kinds, samples) in cls.counts.items():
            print(f"\nprune zoom pixel accuracy, {name}: {agree} of {total} points agree; kinds: "
                  f"{', '.join(f'{kind} {n}' for kind, n in kinds.items())}; {samples} DLL samples pass")
        del cls.game
        gc.collect()

    def setUp(self) -> None:
        self.game.hold(SHEARS)

    def kind(self, part: tuple[int, int]) -> str:
        game = self.game
        record = game.pot(7) + 0xA8 + part[0] * 0x16C
        if part[1] < 0:
            return "dead branch" if game.emu.read32(record + 4) == 4 else "live branch"
        age = struct.unpack("<f", game.uc.mem_read(game.pot(7) + 0x10, 4))[0]
        return "bud" if age < 24.0 else "flower head"

    def check(self, name: str, make) -> set:
        game, k = self.game, 7
        game.close()
        game.uc.mem_write(game.pot(k), make().to_record())
        game.emu.write32(game.manager + 8 + k * 4, 0)
        game.objects = [game.plant(j) for j in PLANTS]
        game.frame((0, 0), patched=False)
        box = game.open(k)
        cx, cy = 270 + 92 * (k % 5) + 46, 43 + 144 * (k // 5) + 72
        bx, by = box[0] + BOX_W // 2, box[1] + BOX_H // 2
        corner = (box[0] + 2, box[3] - 2)
        game.frame(corner)
        maps = HitMaps(game, k)
        maps.take(corner)                     # the tip off the plant: nothing lit, the whole maps drawn
        real, zoom, zoom_every = maps.maps["real"], maps.maps["zoom"], maps.every["zoom"]
        self.assertTrue(real and zoom, name)
        # the zoom's hit test at every real pixel the zoom can reach: the copy's draw at its real size over
        # a plain region (the DLL's find_part), one frame with the tip at each mapped point is what it gives;
        # its map is the same draw's, so compare the stock map with a map of the DLL's draw at real size
        found = HitMaps(game, k)
        reach = [(x, y) for (x, y) in real
                 if box[0] + 2 <= bx + 2 * (x - cx) <= box[2] - 2 and box[1] + 30 <= by + 2 * (y - cy) <= box[3] - 2]
        self.assertTrue(reach, name)
        probe = sorted(reach)[len(reach) // 2]
        found.take((bx + 2 * (probe[0] - cx) + 4, by + 2 * (probe[1] - cy) + 16))
        dll = found.maps["find"]
        self.assertTrue(dll, f"{name}: the zoom's hit test ran")
        points = sorted(set(reach) | {p for p in dll
                                      if box[0] + 2 <= bx + 2 * (p[0] - cx) <= box[2] - 2
                                      and box[1] + 30 <= by + 2 * (p[1] - cy) <= box[3] - 2})
        agree = sum(1 for p in points if real.get(p, (-1, -1)) == dll.get(p, (-1, -1)))
        wrong = [(p, real.get(p), dll.get(p)) for p in points if real.get(p, (-1, -1)) != dll.get(p, (-1, -1))]
        self.assertEqual(wrong, [], f"{name}: the zoom's part differs from the stock hit test's")
        kinds: dict = {}
        by_kind: dict = {}
        for p in points:
            part = real.get(p, (-1, -1))
            if part[0] >= 0:
                kind = self.kind(part)
                kinds[kind] = kinds.get(kind, 0) + 1
                by_kind.setdefault(kind, []).append(p)
        # through the DLL: samples of every kind found, at the zoomed cut point
        samples = 0
        for kind, where in by_kind.items():
            inner = [p for p in where if all(real.get((p[0] + dx, p[1] + dy)) == real[p] for dx in (-1, 0, 1)
                                             for dy in (-1, 0, 1))] or where
            for p in inner[:: max(1, len(inner) // 2)][:2]:
                cursor = (bx + 2 * (p[0] - cx) + 4, by + 2 * (p[1] - cy) + 16)
                game.frame(cursor)
                self.assertEqual(game.zoom_part(), real[p], f"{name}: {kind} at {cursor}")
                obj = game.plant(k)
                game.emu.write32(obj + 0x30, 80)               # the flash at its whitest (sin 90)
                lit = game.frame(cursor)
                game.emu.write32(obj + 0x30, 260)              # and at its faintest (sin 270)
                dim = game.frame(cursor)
                changed = {(i // 4 % W, i // 4 // W) for i in range(0, len(lit), 4) if lit[i:i + 3] != dim[i:i + 3]}
                cut = {q for q, part in zoom.items() if part == real[p] or self.grows_on(part, real[p])}
                under = {q for q, parts in zoom_every.items()          # where the lit part lies under others
                         if any(part == real[p] or self.grows_on(part, real[p]) for part in parts)}
                near = {(q[0] + dx, q[1] + dy) for q in under for dx in range(-1, 2) for dy in range(-1, 2)}
                self.assertGreater(len(changed & cut), len(cut) // 2, f"{name}: the {kind} flashes white")
                # nothing else of the zoomed plant flashes (the real plant's own stock flash, under the box,
                # may show through it faded where the real plant is)
                others = {q for q in zoom if q not in near and q not in real} & changed
                # (the game draws the flash from the part's mask sheet; a dead part keeps its living mask)
                self.assertLess(len(others), max(3, len(changed) // 20), f"{name}: lit {real[p]}: the flash is on it")
                samples += 1
        for kind, where in by_kind.items():
            if kind in self.clicked:                 # each kind clicked once, on the first plant that has it
                continue
            self.clicked.add(kind)
            p = where[len(where) // 2]
            cursor = (bx + 2 * (p[0] - cx) + 4, by + 2 * (p[1] - cy) + 16)
            snap = game.snapshot()
            game.frame(cursor)
            game.press(*cursor)
            game.press(*button_point(box, CLOSE))
            zoomed_result = game.records(), game.pruned()
            game.restore(snap)
            game.close()
            game.restore(snap)
            real_cursor = (p[0] + 4, p[1] + 16)
            game.frame(real_cursor, patched=False)
            self.assertEqual(game.hover(k), real[p], f"{name}: the stock hover at {real_cursor}")
            game.stock_prune(*real_cursor)
            stock_result = game.records(), game.pruned()
            game.restore(snap)
            self.assertEqual(zoomed_result, stock_result, f"{name}: {kind}, zoom {cursor} / real {real_cursor}")
            game.open(k)
        self.counts[name] = (agree, len(points), kinds, samples)
        return set(kinds)

    def grows_on(self, part: tuple, lit: tuple) -> bool:
        """`part` is drawn lit with `lit` (the branch draw lights a lit branch's children and flowers too)."""
        if lit[1] >= 0:
            return False
        game, record = self.game, self.game.pot(7) + 0xA8
        branch, seen = part[0], set()
        while branch >= 0 and branch not in seen:
            if branch == lit[0]:
                return True
            seen.add(branch)
            parent = -1
            for i in range(60):
                at = record + i * 0x16C
                for j in range(game.emu.read32(at + 0x1C)):
                    if game.emu.read32(at + 0x20 + j * 0x10 + 4, signed=True) == branch:
                        parent = i
            branch = parent
        return False


    def test_every_kind_of_prunable_part(self) -> None:
        covered = set()
        for name, make in ACCURACY_PLANTS.items():
            with self.subTest(plant=name):
                covered |= self.check(name, make)
        self.assertEqual(covered, set(KINDS))


if __name__ == "__main__":
    unittest.main()
