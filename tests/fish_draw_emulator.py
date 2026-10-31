"""Fish Tycoon's own drawing code, run in Unicorn on the vanilla executable, with every sprite
draw recorded. Picture Studio's tests compare these records with pictures_fish's plans.

What runs is the game's machine code: the fish draw 0x4145F0, the sprite setup 0x415DF0 (fin
alpha 0x411100, fin anchors 0x4111E0), the sprite-id decoder 0x4122A0, the grid draws
0x407EF0 / 0x407F80 / 0x408190 / 0x407D60, the cell rectangle 0x4095F0 and the clip
0x4076B0 / 0x407750. Replaced by Python: the two sprite getters (0x41BCA0: the sprite table's
grid sprite; 0x41BE70: a plain image), which hand back stand-in sprites the size of the real
art, and the two blitters at the bottom (0x404150, the plain SDL blit, and 0x4041C0, the
blit with surface alpha and scale), which record what they are asked to draw.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from store_emulator import Emulator

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Fish Tycoon"
EXE = VANILLA / "Fish Tycoon.exe"
SPRITE_TABLE, SPRITE_COUNT, SPRITE_STRIDE = 0x004552F0, 197, 0x24

FISH_DRAW = 0x004145F0
SPRITE_SETUP = 0x00415DF0
GET_GRID = 0x0041BCA0
GET_IMAGE = 0x0041BE70
BLIT = 0x00404150
BLIT_EX = 0x004041C0

CLIP = (0, 0, 4000, 4000)


def available() -> bool:
    return EXE.is_file()


@dataclass(frozen=True)
class Blit:
    """One blit the game asked for: the sheet (sprite table index, or image id for a plain
    image), the source rectangle, the top-left on screen, the surface alpha (0-255) and the
    scale (percent) and whether a scaled picture is centred on its unscaled place."""
    kind: str                  # "grid" (sprite table) / "image" (plain image)
    sprite: int
    src: tuple                 # (left, top, right, bottom)
    x: int
    y: int
    alpha: float = 1.0
    scale: float = 1.0
    centred: bool = False


class FishDrawEmulator:
    def __init__(self, sizes: dict) -> None:
        """`sizes`: (kind, id) -> (width, height) of the real art (the stand-ins' sizes)."""
        self.sizes = sizes
        self.emu = Emulator(EXE, None, {})
        emu = self.emu
        self.view = emu.alloc(0x6000)
        self.state = emu.alloc(0x1E600)
        self.sprite_holder = emu.alloc(0x10)
        self.gfx_holder = emu.alloc(0x10)
        self.gfx = emu.alloc(0x100)
        self.screen = emu.alloc(0x40)
        emu.write32(self.view + 0x5DE4, self.state)
        emu.write32(self.view + 0x5DE8, self.sprite_holder)
        emu.write32(self.view + 0x5DF0, self.gfx_holder)
        emu.write32(self.gfx_holder, self.gfx)
        emu.write32(self.gfx + 0x30, self.screen)
        for i, v in enumerate(CLIP):
            emu.write32(self.gfx + 0x38 + 4 * i, v)
        self.surfaces: dict[int, tuple[str, int]] = {}
        self._grids: dict[int, int] = {}
        self._images: dict[int, int] = {}
        self.blits: list[Blit] = []
        emu.hook(GET_GRID, self._get_grid, 4)
        emu.hook(GET_IMAGE, self._get_image, 4)
        emu.hook(BLIT, self._blit, 0x1C)
        emu.hook(BLIT_EX, self._blit_ex, 0x28)

    # ---- the sprite table, as the game holds it
    def table_entry(self, index: int) -> tuple[str, int, int]:
        at = SPRITE_TABLE + index * SPRITE_STRIDE
        _id, name, cols, rows = struct.unpack("<4I", bytes(self.emu.uc.mem_read(at, 16)))
        return self.emu.cstring(name).decode("latin-1"), cols, rows

    def _image_object(self, kind: str, ident: int) -> int:
        w, h = self.sizes[(kind, ident)]
        surface = self.emu.alloc(0x40)
        self.emu.write32(surface + 8, w)
        self.emu.write32(surface + 0xC, h)
        image = self.emu.alloc(0x10)
        self.emu.write32(image, surface)
        self.emu.write8(image + 4, 1)
        self.surfaces[surface] = (kind, ident)
        return image

    def _get_grid(self, emu: Emulator) -> int:
        index = emu.arg(0)
        if index not in self._grids:
            _name, cols, rows = self.table_entry(index)
            image = self._image_object("grid", index)
            w, h = self.sizes[("grid", index)]
            sprite = emu.alloc(0x40)
            emu.write32(sprite + 4, image)
            emu.write32(sprite + 8, cols)
            emu.write32(sprite + 0xC, rows)
            emu.write32(sprite + 0x10, w // cols)
            emu.write32(sprite + 0x14, h // rows)
            emu.write32(sprite + 0x30, 0)
            self._grids[index] = sprite
        return self._grids[index]

    def _get_image(self, emu: Emulator) -> int:
        ident = emu.arg(0)
        if ident not in self._images:
            wrapper = emu.alloc(0x40)            # a plain sprite: +4 its image (0x4095B0 / 0x4095C0)
            emu.write32(wrapper + 4, self._image_object("image", ident))
            self._images[ident] = wrapper
        return self._images[ident]

    def _blit(self, emu: Emulator) -> int:
        surface, x, y, l, t, r, b = (emu.arg(i) for i in range(7))
        kind, ident = self.surfaces[surface]
        self.blits.append(Blit(kind, ident, (_s(l), _s(t), _s(r), _s(b)), _s(x), _s(y)))
        return 0

    def _blit_ex(self, emu: Emulator) -> int:
        surface, x, y, l, t, r, b = (emu.arg(i) for i in range(7))
        alpha, scale = (struct.unpack("<f", struct.pack("<I", emu.arg(i)))[0] for i in (7, 8))
        centred = bool(emu.arg(9) & 0xFF)
        kind, ident = self.surfaces[surface]
        self.blits.append(Blit(kind, ident, (_s(l), _s(t), _s(r), _s(b)), _s(x), _s(y), alpha, scale, centred))
        return 0

    # ---- a fish
    def fish_record(self, *, alive: int = 1, age: int = 30, health: int = 100, disease: int = 0,
                    body: int = 0, fin: int = 0, height: int | None = None) -> int:
        """A tank fish record (0x288 bytes) with its sprite fields set by the game's own
        0x415DF0, and +0x64 (the view's body height) as 0x415460 sets it, or `height`."""
        emu = self.emu
        rec = emu.alloc(0x288)
        emu.write32(rec, alive)
        emu.write32(rec + 0x0C, age)
        emu.write32(rec + 0x3C, health & 0xFFFFFFFF)
        emu.write32(rec + 0x40, disease)
        emu.write32(rec + 0x4C, body)
        emu.write32(rec + 0x50, fin)
        emu.call(SPRITE_SETUP, rec + 0x54, body, fin, ecx=self.view)
        if height is not None:
            emu.write32(rec + 0x64, height)
        return rec

    def sprite_fields(self, rec: int) -> dict:
        r = lambda off: self.emu.read32(rec + off, signed=True)   # noqa: E731
        return {"body_id": r(0x54), "top_id": r(0x58), "bot_id": r(0x5C), "alpha": r(0x60), "height": r(0x64),
                "top": (r(0x68), r(0x6C)), "bot": (r(0x70), r(0x74))}

    def draw(self, rec: int, x: int, y: int, mode: int, body_frame: int, fin_frame: int, stage: int) -> list[Blit]:
        self.blits = []
        self.emu.call(FISH_DRAW, x, y, rec, mode, body_frame, fin_frame, stage, ecx=self.view)
        return list(self.blits)


LOCK, UNLOCK, UPPER_BLIT = 0x0042A5D6, 0x0042A5CA, 0x0042A600


class BlitterEmulator:
    """The game's own blitter 0x4041C0 (surface alpha and scale), run on real pixels: a source
    surface in the 32-bit ARGB layout SDL_DisplayFormatAlpha gives the game's art, onto a
    32-bit screen. SDL's lock and unlock do nothing here; SDL_UpperBlit (the plain path the
    blitter takes at scale 1 and alpha 1) is not expected and fails the run."""

    def __init__(self, screen_w: int = 400, screen_h: int = 300) -> None:
        self.emu = Emulator(EXE, None, {})
        emu = self.emu
        emu.hook(LOCK, lambda e: 0, 0)
        emu.hook(UNLOCK, lambda e: 0, 0)

        def upper(_e):
            raise AssertionError("the blitter took SDL's own blit")
        emu.hook(UPPER_BLIT, upper, 0)
        self.screen_w, self.screen_h = screen_w, screen_h
        self.screen = self._surface(screen_w, screen_h, alpha_mask=0)
        self.gfx = emu.alloc(0x100)
        emu.write32(self.gfx + 0x30, self.screen)
        emu.write32(self.gfx + 8, screen_w)              # the screen's size, the blitter's clip
        emu.write32(self.gfx + 0xC, screen_h)

    def _format(self, alpha_mask: int) -> int:
        emu = self.emu
        fmt = emu.alloc(0x40)
        emu.uc.mem_write(fmt + 4, bytes((32, 4, 0, 0, 0, 0 if alpha_mask else 8, 16, 8, 0, 24 if alpha_mask else 0)))
        emu.write32(fmt + 16, 0x00FF0000)
        emu.write32(fmt + 20, 0x0000FF00)
        emu.write32(fmt + 24, 0x000000FF)
        emu.write32(fmt + 28, alpha_mask)
        emu.uc.mem_write(fmt + 36, b"\xff")
        return fmt

    def _surface(self, w: int, h: int, alpha_mask: int) -> int:
        emu = self.emu
        surface = emu.alloc(0x40)
        pixels = emu.alloc(w * h * 4 + 16)
        emu.write32(surface + 4, self._format(alpha_mask))
        emu.write32(surface + 8, w)
        emu.write32(surface + 12, h)
        emu.uc.mem_write(surface + 16, struct.pack("<H", w * 4))
        emu.write32(surface + 20, pixels)
        emu.uc.mem_write(surface + 32, struct.pack("<hhHH", 0, 0, w, h))
        return surface

    def source(self, w: int, h: int, rgba: bytes) -> int:
        """A source surface from straight RGBA bytes."""
        surface = self._surface(w, h, alpha_mask=0xFF000000)
        argb = bytearray(len(rgba))
        argb[0::4], argb[1::4], argb[2::4], argb[3::4] = rgba[2::4], rgba[1::4], rgba[0::4], rgba[3::4]
        self.emu.uc.mem_write(self.emu.read32(surface + 20), bytes(argb))
        return surface

    def fill_screen(self, rgb: tuple) -> None:
        r, g, b = rgb
        self.emu.uc.mem_write(self.emu.read32(self.screen + 20), bytes((b, g, r, 0)) * (self.screen_w * self.screen_h))

    def screen_rgb(self) -> list[tuple[int, int, int]]:
        raw = bytes(self.emu.uc.mem_read(self.emu.read32(self.screen + 20), self.screen_w * self.screen_h * 4))
        return [(raw[i + 2], raw[i + 1], raw[i]) for i in range(0, len(raw), 4)]

    def blit(self, src: int, rect: tuple, x: int, y: int, alpha: float, scale: float, centred: bool = False) -> None:
        l, t, r, b = rect
        f32 = lambda v: struct.unpack("<I", struct.pack("<f", v))[0]   # noqa: E731
        self.emu.call(BLIT_EX, src, x & 0xFFFFFFFF, y & 0xFFFFFFFF, l, t, r, b, f32(alpha), f32(scale),
                      1 if centred else 0, ecx=self.gfx)


def _s(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value
