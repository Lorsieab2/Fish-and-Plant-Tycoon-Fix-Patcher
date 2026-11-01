"""A game's screens and dialogs drawn in Unicorn, every draw call recorded: Picture Studio's
"Screens, bars and buttons" tests compare the records with pictures_screens's pieces.

What runs is the game's machine code (tests/screen_emulator.py's ScreenEmulator with the game's
own widgets): the screen or dialog constructor, its buttons, check boxes and labels, its draw
functions and the dialog code that places it, the image and sprite-strip objects (cell sizes, a
frame's rectangle), the string lookups and the printf the game formats its words with. Replaced:
* a picture file's loading: the image object answers the picture's real width and height (read
  from the game copy's file by the test);
* the text width and height (Plant 0x402380 / 0x402450, Fish 0x4023D0 / 0x4024A0) answer what
  pictures_screens.Composer.text_size measures (tests/test_picture_screen_words.py runs the
  games' own functions on the real fonts and checks they agree);
* the graphics calls that draw (image, strip frame, tinted frame, text) are recorded with their
  arguments and not run; the screen is 800 x 600;
* the static CRT's sprintf is Python's (%d / %i / %u / %s, flags and widths).
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import struct

import screen_emulator as se

try:
    from unicorn import UC_HOOK_CODE
    from unicorn import x86_const as X
except ImportError:              # CI installs neither: the tests that use this skip
    UC_HOOK_CODE = None

available = se.available


def picture_sizes(game: str):
    """name -> (width, height) of the vanilla game's picture files, read from their headers (PNG,
    JPEG, BMP); (0, 0) for a file the copy lacks."""
    import zipfile
    folder = se.EXES[game].parent
    if game == "fish":
        archive = zipfile.ZipFile(folder / "Assets" / "ft.dat")
        files = {n.casefold(): n for n in archive.namelist()}
        read = lambda n: archive.read(files[n.casefold()]) if n.casefold() in files else b""  # noqa: E731
    else:
        files = {p.name.casefold(): p for p in (folder / "Images").iterdir()}
        read = lambda n: files[n.casefold()].read_bytes() if n.casefold() in files else b""  # noqa: E731
    cache: dict = {}

    def size(name: str) -> tuple:
        if name not in cache:
            cache[name] = header_size(read(name))
        return cache[name]
    return size


def header_size(data: bytes) -> tuple:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"BM":
        w, h = struct.unpack("<ii", data[18:26])
        return w, abs(h)
    if data[:2] == b"\xff\xd8":
        at = 2
        while at + 9 < len(data):
            marker, length = data[at + 1], struct.unpack(">H", data[at + 2:at + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[at + 5:at + 9])
                return w, h
            at += 2 + length
    return 0, 0


@dataclass
class Draw:
    kind: str              # "image", "frame", "tinted", "text"
    file: str = ""
    cols: int = 1
    rows: int = 1
    cell: int = 0
    x: int = 0
    y: int = 0
    text: bytes = b""
    colour: int = 0
    font: int = 0
    tint: int = 0
    alpha: float = 1.0
    scale: int = 100
    via: int = 0           # the graphics call


def s32(v: int) -> int:
    return struct.unpack("<i", struct.pack("<I", v & 0xFFFFFFFF))[0]


def f32(v: int) -> float:
    return struct.unpack("<f", struct.pack("<I", v & 0xFFFFFFFF))[0]


@dataclass(frozen=True)
class Calls:
    image_load: int        # thiscall (name): a picture file's surface
    width: int             # thiscall () on that surface
    height: int
    strip: int             # thiscall (name, cols, rows): a sprite strip
    sprite: int            # thiscall (id) on the sprite manager: the sprite's strip
    sprite_image: int      # thiscall (id): the sprite's whole picture
    text_width: int        # thiscall (text, scale) on a font
    text_height: int       # thiscall (text) on a font
    draw_text: int         # thiscall (text, x, y, colour, font) on the graphics impl
    graphics: int          # the graphics singleton
    sprintf: int
    widget_base: int       # thiscall (parent): every widget's base constructor
    draws: dict            # graphics wrapper -> (kind, pop, argument names)


PLANT = Calls(0x40A4D0, 0x40A730, 0x40A740, 0x409FB0, 0x420460, 0x420550, 0x402380, 0x402450, 0x408E20,
              0x493948, 0x44F30B, 0x4097E0, {
                  0x409080: ("image", 0xC, ("obj", "x", "y")),
                  0x409090: ("image", 0x10, ("obj", "x", "y", "alpha")),
                  0x409120: ("frame", 0x10, ("obj", "x", "y", "cell")),
                  0x409130: ("frame", 0x14, ("obj", "x", "y", "cell", "alpha")),
                  0x409220: ("tinted", 0x1C, ("obj", "x", "y", "cell", "tint", "alpha", "alpha2")),
              })


class DrawEmulator(se.ScreenEmulator):
    def __init__(self, game: str, size, sprites: dict | None = None) -> None:
        """`size(name)`: (width, height) of a picture file of the game copy; `sprites`: the
        sprite table, id -> (file, cols, rows)."""
        super().__init__(game, widgets=True)
        c = self.c = PLANT
        self.size = size
        self.files: dict[int, str] = {}          # a loaded surface -> its file
        self.draws: list[Draw] = []
        self.widgets: list[tuple[int, int]] = []  # (widget, parent) in the order made
        self.fonts: dict[int, int] = {}          # a font object -> the game's font number
        self.measure = None                      # (font number, bytes) -> (width, height)
        emu = self.emu
        emu.hook(c.image_load, self._load, 4)
        emu.hook(c.width, lambda e: self.size(self.files[self._this()])[0], 0)
        emu.hook(c.height, lambda e: self.size(self.files[self._this()])[1], 0)
        emu.hook(c.text_width, self._text_width, 8)
        emu.hook(c.text_height, self._text_height, 4)
        emu.hook(c.draw_text, self._draw_text, 0x14)
        emu.hook(c.sprintf, self._sprintf, 0)
        for address, (kind, pop, names) in c.draws.items():
            emu.hook(address, lambda e, a=address: self._draw(a), pop)
        # the graphics singleton: an 800 x 600 screen, a default font
        graphics, impl = self._zeroed(0x10), self._zeroed(0x100)
        emu.write32(graphics, impl)
        emu.write32(impl + 8, 800)
        emu.write32(impl + 0xC, 600)
        self.default_font = self._zeroed(0x10)
        self.fonts[self.default_font] = 0
        emu.write32(impl + 0x5C, self.default_font)
        emu.write32(c.graphics, graphics)
        self.graphics = graphics
        # the sprites: each made by the game's own strip constructor, handed out by id
        self.sprites: dict[int, int] = {}
        for ident, (file, cols, rows) in (sprites or {}).items():
            if cols and rows:
                self.sprites[ident] = self.strip(file, cols, rows)
        emu.hook(c.sprite, lambda e: self.sprites.get(e.arg(0), 0), 4)
        emu.hook(c.sprite_image, lambda e: self.sprites.get(e.arg(0), 0), 4)
        emu.uc.hook_add(UC_HOOK_CODE, self._widget, begin=c.widget_base, end=c.widget_base)

    def _this(self) -> int:
        return self.emu.uc.reg_read(X.UC_X86_REG_ECX)

    # ---- pictures
    def _load(self, emu) -> int:
        this = self._this()
        self.files[this] = emu.cstring(emu.arg(0)).decode("latin-1")
        return this

    def strip(self, file: str, cols: int, rows: int) -> int:
        obj = self._zeroed(0x40)
        self.emu.call(self.c.strip, self.emu.text(file), cols, rows, ecx=obj)
        return obj

    def describe(self, obj: int) -> tuple:
        """(file, cols, rows) of an image or strip object (its surface at +4; a strip's vtable
        is the game's strip vtable, its columns and rows at +8 / +0xC)."""
        emu = self.emu
        file = self.files.get(emu.read32(obj + 4), f"<{obj:#x}>")
        if emu.read32(obj) != 0x4655A0:            # not a plain image: a strip
            return file, emu.read32(obj + 8), emu.read32(obj + 0xC)
        return file, 1, 1

    # ---- widgets
    def _widget(self, uc, _address, _size, _data) -> None:
        esp = uc.reg_read(X.UC_X86_REG_ESP)
        self.widgets.append((uc.reg_read(X.UC_X86_REG_ECX), self.emu.read32(esp + 4)))

    # ---- text
    def _font(self, obj: int) -> int:
        return self.fonts.get(obj, 0)

    def _measure(self, font: int, data: bytes) -> tuple:
        if self.measure is None:
            raise RuntimeError("no text measure set")
        return self.measure(font, data)

    def _text_width(self, emu) -> int:
        return self._measure(self._font(self._this()), emu.cstring(emu.arg(0)) if emu.arg(0) else b"")[0]

    def _text_height(self, emu) -> int:
        return self._measure(self._font(self._this()), emu.cstring(emu.arg(0)) if emu.arg(0) else b"")[1]

    def _draw_text(self, emu) -> int:
        font = emu.arg(4) or emu.read32(emu.read32(emu.read32(self.c.graphics)) + 0x5C)
        self.draws.append(Draw("text", text=emu.cstring(emu.arg(0)), x=s32(emu.arg(1)), y=s32(emu.arg(2)),
                               colour=emu.arg(3), font=self._font(font), via=self.c.draw_text))
        return 0

    def _draw(self, address: int) -> int:
        kind, _pop, names = self.c.draws[address]
        emu = self.emu
        args = {n: emu.arg(i) for i, n in enumerate(names)}
        file, cols, rows = self.describe(args["obj"])
        self.draws.append(Draw(kind, file, cols, rows, args.get("cell", 0), s32(args["x"]), s32(args["y"]),
                               tint=args.get("tint", 0), alpha=f32(args["alpha"]) if "alpha" in args else 1.0,
                               via=address))
        return 0

    # ---- printf
    def _sprintf(self, emu) -> int:
        buffer, fmt = emu.arg(0), emu.cstring(emu.arg(1))
        cursor = [2]

        def one(match):
            flags, width, kind = match.group(1), match.group(2), match.group(3)
            raw = emu.arg(cursor[0])
            cursor[0] += 1
            if kind == b"s":
                value = emu.cstring(raw)
            elif kind == b"u":
                value = b"%d" % raw
            else:
                value = b"%d" % s32(raw)
            return (b"%" + flags + width + b"s") % value
        out = re.sub(rb"%([-0 +#]*)(\d*)([diusx])", one, fmt.replace(b"%%", b"\x00")).replace(b"\x00", b"%")
        emu.uc.mem_write(buffer, out + b"\0")
        return len(out)

    # ---- running
    def run(self, address: int, *args: int, this: int = 0) -> int:
        return self.emu.call(address, *args, ecx=this)

    def vcall(self, obj: int, slot: int, *args: int) -> int:
        return self.emu.call(self.emu.read32(self.emu.read32(obj) + 4 * slot), *args, ecx=obj)
