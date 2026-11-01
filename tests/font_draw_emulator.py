"""The games' own font loader and text draw, run in Unicorn on the vanilla executables, on the
real font pictures. The Text Maker's tests compare its pictures with what this draws.

What runs is the game's machine code: the font's init and loader (Fish 0x402350 / 0x402510,
Plant 0x402300 / 0x4024E0: the table pass and the byte index), the text draw (Fish 0x4087E0,
Plant 0x408E20), its glyph lookup (0x4028C0 / 0x402890), the colour copy that ANDs every
pixel with the colour (0x402730 / 0x402700) and the clip (0x4076B0 / 0x407840). Replaced by
Python: operator new, the image file's check and loading (the picture is handed over as an
SDL surface), and SDL itself: SDL_CreateRGBSurface, SDL_MapRGBA, lock and unlock, and
SDL_UpperBlit, which records each blit and lays it on a screen with SDL's own blend
(text_maker.sdl_blend, the C BlitRGBtoRGBPixelAlpha).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from picture_image import Image  # noqa: E402
import text_maker  # noqa: E402
from store_emulator import Emulator, VANILLA  # noqa: E402


@dataclass(frozen=True)
class Addresses:
    exe: Path
    new: int
    file_exists: int
    image_ctor: int
    image_surface: int
    font_init: int
    draw: int
    create_surface: int
    lock: int
    map_rgba: int
    unlock: int
    upper_blit: int
    default_font: int     # the graphics impl's default font field
    clip: int             # the graphics impl's clip rectangle (left, top, right, bottom)
    sdl2: bool


GAMES = {
    "fish": Addresses(VANILLA / "Fish Tycoon" / "Fish Tycoon.exe", 0x42A793, 0x409920, 0x409AB0, 0x409DD0,
                      0x402350, 0x4087E0, 0x42A5DC, 0x42A5D6, 0x42A5D0, 0x42A5CA, 0x42A600, 0x34, 0x38, False),
    "plant": Addresses(VANILLA / "Plant Tycoon" / "Plant Tycoon.exe", 0x44E894, 0x40A3F0, 0x40A4D0, 0x40A800,
                       0x402300, 0x408E20, 0x44E666, 0x44E660, 0x44E65A, 0x44E654, 0x44E696, 0x5C, 0x60, True),
}


def available(game: str) -> bool:
    return GAMES[game].exe.is_file()


def font_picture(game: str, key: str) -> bytes:
    folder = GAMES[game].exe.parent
    if game == "fish":
        with zipfile.ZipFile(folder / "Assets" / "ft.dat") as archive:
            return archive.read(f"{key.lower()}.png")
    return (folder / "Images" / f"{key}.png").read_bytes()


@dataclass
class BlitRecord:
    src: tuple          # (x, y, w, h)
    x: int
    y: int
    tinted: bool


class FontDrawEmulator:
    def __init__(self, game: str, screen_w: int = 900, screen_h: int = 200) -> None:
        self.game = game
        a = self.a = GAMES[game]
        emu = self.emu = Emulator(a.exe, None, {})
        emu.uc.mem_map(0, 0x1000)                     # fs:[0], the SEH chain, reads address 0
        self.images: dict[int, int] = {}              # image object -> surface
        self.pictures: dict[str, Image] = {}
        self.sheet_surfaces: set[int] = set()
        self.formats: dict[int, tuple] = {}           # format -> masks
        self.surfaces: dict[int, tuple[int, int]] = {}
        self.blits: list[BlitRecord] = []
        self.screen_image = Image(screen_w, screen_h)
        emu.hook(a.new, lambda e: e.alloc(max(1, e.arg(0))), 0)
        emu.hook(a.file_exists, lambda e: 1, 0)
        emu.hook(a.image_ctor, self._image_ctor, 4)
        emu.hook(a.image_surface, self._image_surface, 0)
        emu.hook(a.create_surface, self._create_surface, 0)
        emu.hook(a.lock, lambda e: 0, 0)
        emu.hook(a.unlock, lambda e: 0, 0)
        emu.hook(a.map_rgba, self._map_rgba, 0)
        emu.hook(a.upper_blit, self._upper_blit, 0)
        self.screen = self._surface(screen_w, screen_h, (0xFF0000, 0xFF00, 0xFF, 0))
        self.impl = emu.alloc(0x100)
        emu.write32(self.impl + 0x30, self.screen)
        for i, v in enumerate((0, 0, screen_w, screen_h)):
            emu.write32(self.impl + a.clip + 4 * i, v)

    # ---- SDL surfaces as the game reads them
    def _format(self, masks: tuple) -> int:
        emu = self.emu
        fmt = emu.alloc(0x40)
        if self.a.sdl2:
            emu.write8(fmt + 8, 32)
            emu.write8(fmt + 9, 4)
            for i, m in enumerate(masks):
                emu.write32(fmt + 12 + 4 * i, m)
        else:
            emu.write8(fmt + 4, 32)
            emu.write8(fmt + 5, 4)
            for i, m in enumerate(masks):
                emu.write32(fmt + 16 + 4 * i, m)
        self.formats[fmt] = masks
        return fmt

    def _surface(self, w: int, h: int, masks: tuple) -> int:
        emu = self.emu
        surface = emu.alloc(0x40)
        emu.write32(surface + 4, self._format(masks))
        emu.write32(surface + 8, w)
        emu.write32(surface + 0xC, h)
        emu.write32(surface + 0x10, w * 4)
        emu.write32(surface + 0x14, emu.alloc(w * h * 4 + 16))
        self.surfaces[surface] = (w, h)
        return surface

    def _picture_surface(self, picture: Image) -> int:
        surface = self._surface(picture.width, picture.height, (0xFF0000, 0xFF00, 0xFF, 0xFF000000))
        argb = bytearray(len(picture.data))
        argb[0::4], argb[1::4], argb[2::4], argb[3::4] = (picture.data[2::4], picture.data[1::4],
                                                          picture.data[0::4], picture.data[3::4])
        self.emu.uc.mem_write(self.emu.read32(surface + 0x14), bytes(argb))
        self.sheet_surfaces.add(surface)
        return surface

    def surface_image(self, surface: int) -> Image:
        w, h = self.surfaces[surface]
        raw = bytes(self.emu.uc.mem_read(self.emu.read32(surface + 0x14), w * h * 4))
        image = Image(w, h)
        image.data[0::4], image.data[1::4], image.data[2::4], image.data[3::4] = raw[2::4], raw[1::4], raw[0::4], raw[3::4]
        return image

    # ---- hooks
    def _image_ctor(self, emu: Emulator) -> int:
        from store_emulator import X  # noqa: PLC0415
        this = emu.uc.reg_read(X.UC_X86_REG_ECX)
        name = emu.cstring(emu.arg(0)).decode("latin-1")
        key = name[:-4] if name.lower().endswith(".png") else name
        self.images[this] = self._picture_surface(self.pictures[key.lower()])
        return this

    def _image_surface(self, emu: Emulator) -> int:
        from store_emulator import X  # noqa: PLC0415
        return self.images[emu.uc.reg_read(X.UC_X86_REG_ECX)]

    def _create_surface(self, emu: Emulator) -> int:
        _flags, w, h, _depth, r, g, b, alpha = (emu.arg(i) for i in range(8))
        return self._surface(w, h, (r, g, b, alpha))

    def _map_rgba(self, emu: Emulator) -> int:
        fmt, r, g, b, alpha = (emu.arg(i) for i in range(5))
        masks = self.formats[fmt]
        value = 0
        for channel, mask in zip((r & 0xFF, g & 0xFF, b & 0xFF, alpha & 0xFF), masks):
            if mask:
                shift = (mask & -mask).bit_length() - 1
                value |= (channel << shift) & mask
        return value

    def _upper_blit(self, emu: Emulator) -> int:
        src, srect, dst, drect = (emu.arg(i) for i in range(4))
        assert dst == self.screen
        if self.a.sdl2:
            sx, sy, sw, sh = struct.unpack("<4i", emu.uc.mem_read(srect, 16))
            dx, dy = struct.unpack("<2i", emu.uc.mem_read(drect, 8))
        else:
            sx, sy, sw, sh = struct.unpack("<hhHH", emu.uc.mem_read(srect, 8))
            dx, dy = struct.unpack("<hh", emu.uc.mem_read(drect, 4))
        self.blits.append(BlitRecord((sx, sy, sw, sh), dx, dy, src not in self.sheet_surfaces))
        piece = self.surface_image(src).sub(sx, sy, sw, sh)
        text_maker.sdl_blend(self.screen_image, piece, dx, dy)
        return 0

    # ---- the game's calls
    def load_font(self, key: str, table: int) -> int:
        self.pictures[key.lower()] = Image.from_png(font_picture(self.game, key))
        wrapper = self.emu.alloc(0x10)
        self.emu.call(self.a.font_init, self.emu.text(key), table, 0, ecx=wrapper)
        return wrapper

    def fill(self, rgb: tuple) -> None:
        self.screen_image.data[:] = bytes((*rgb, 255)) * (self.screen_image.width * self.screen_image.height)

    def draw(self, font: int, text: bytes, x: int, y: int, colour: int) -> None:
        address = self.emu.alloc(len(text) + 1)
        self.emu.uc.mem_write(address, text + b"\0")
        self.emu.call(self.a.draw, address, x, y, colour, font, ecx=self.impl)
