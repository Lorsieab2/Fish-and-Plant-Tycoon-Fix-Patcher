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
    image: int             # thiscall (name): a whole picture
    sprite: int            # thiscall (id) on the sprite manager: the sprite's strip
    sprite_image: int      # thiscall (id): the sprite's whole picture
    text_width: int        # thiscall (text, scale) on a font
    text_height: int       # thiscall (text) on a font
    draw_text: int         # thiscall (text, x, y, colour, font) on the graphics impl
    graphics: int          # the graphics singleton
    sprintf: int
    widget_base: int       # thiscall (parent): every widget's base constructor
    draws: dict            # graphics wrapper -> (kind, pop, argument names)


PLANT = Calls(0x40A4D0, 0x40A730, 0x40A740, 0x409FB0, 0x409E20, 0x420460, 0x420550, 0x402380, 0x402450, 0x408E20,
              0x493948, 0x44F30B, 0x4097E0, {
                  0x409080: ("image", 0xC, ("obj", "x", "y")),
                  0x409090: ("image", 0x10, ("obj", "x", "y", "alpha")),
                  0x409120: ("frame", 0x10, ("obj", "x", "y", "cell")),
                  0x409130: ("frame", 0x14, ("obj", "x", "y", "cell", "alpha")),
                  0x409220: ("tinted", 0x1C, ("obj", "x", "y", "cell", "tint", "alpha", "alpha2")),
                  # the sprite manager's draws, by sprite id
                  0x4207F0: ("frame", 0x14, ("id", "x", "y", "alpha", "scale")),
                  0x4208F0: ("frame", 0x1C, ("id", "cell", "x", "y", "alpha", "scale", "centred")),
              })


class DrawEmulator(se.ScreenEmulator):
    def __init__(self, game: str, size, sprites: dict | None = None) -> None:
        """`size(name)`: (width, height) of a picture file of the game copy; `sprites`: the
        sprite table, id -> (file, cols, rows)."""
        super().__init__(game, widgets=True)
        c = self.c = PLANT
        self.size = size
        self.table = sprites or {}
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
            elif file.casefold().endswith((".png", ".jpg", ".bmp")):
                self.sprites[ident] = self.image(file)
        emu.hook(c.sprite, lambda e: self.sprites.get(e.arg(0), 0), 4)
        emu.hook(c.sprite_image, lambda e: self.sprites.get(e.arg(0), 0), 4)
        emu.uc.hook_add(UC_HOOK_CODE, self._widget, begin=c.widget_base, end=c.widget_base)
        # the game's state (0x41FCD0's object) is far bigger than a made-up singleton: its own block
        made = self.run(0x41FCD0)
        self.game_state = self._zeroed(0x70000)
        for g in self.globals:
            if emu.read32(g) == made:
                emu.write32(g, self.game_state)

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

    def image(self, file: str) -> int:
        obj = self._zeroed(0x10)
        self.emu.call(self.c.image, self.emu.text(file), ecx=obj)
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
        if "id" in args:
            file, cols, rows = self.table.get(args["id"], ("<sprite %#x>" % args["id"], 1, 1))
        else:
            file, cols, rows = self.describe(args["obj"])
        self.draws.append(Draw(kind, file, cols, rows, args.get("cell", 0), s32(args["x"]), s32(args["y"]),
                               tint=args.get("tint", 0), alpha=f32(args["alpha"]) if "alpha" in args else 1.0,
                               scale=args.get("scale", 100), via=address))
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

    def children(self, screen: int) -> list:
        """The widgets a screen or dialog shows, in its list's order (0x40B400 adds at the head)."""
        out, node = [], self.emu.read32(self.emu.read32(screen + 4) + 0x18)
        while node:
            out.append(self.emu.read32(node))
            node = self.emu.read32(node + 4)
        return out

    def show(self, screen: int) -> None:
        """Draw a screen or dialog as the game does each frame (0x40B6B0: its background, its
        widgets, its overlay), shown."""
        self.emu.write8(self.emu.read32(screen + 4), 1)
        for widget in self.children(screen):
            self.vcall(widget, 5, 1)
        self.vcall(screen, 5)

    def thunk_returning(self, value: int, kind: str = "", pop: int = 0) -> int:
        """A function (for a vtable) that returns `value`, recorded as a Draw of `kind` if given."""
        address = self.emu.thunk()
        self.emu.hook(address, lambda e: (self.draws.append(Draw(kind)) if kind else None) or value, pop)
        return address

    # ---- running
    def run(self, address: int, *args: int, this: int = 0) -> int:
        return self.emu.call(address, *args, ecx=this)

    def vcall(self, obj: int, slot: int, *args: int) -> int:
        return self.emu.call(self.emu.read32(self.emu.read32(obj) + 4 * slot), *args, ecx=obj)


# ------------------------------------------------------------------ Fish Tycoon
#
# Fish Tycoon's screens, popups and widgets run the same way, with the game's own sprite table
# (0x4552F0, its getters 0x41BAE0 / 0x41BBB0 / 0x41BD00 run), its picture and strip objects, its
# buttons, radio buttons and text widgets, its draws down to the blitters, and a game state made by
# the game itself (0x41AC20, the state's constructor, then 0x41AA70, the new game). Replaced:
# * a picture file's loading (0x409AB0): its surface answers the file's real width and height;
# * the two blitters at the bottom (0x404150, 0x4041C0) and the rectangle fill (0x407940) are
#   recorded, not run; the text draw (0x4087E0) is recorded;
# * the text width and height (0x4023D0 / 0x4024A0) answer pictures_screens.Composer.text_size;
# * the static CRT's sprintf (0x42B20B) is Python's; the sound manager's getter answers no sound.
# The graphics (0x45AFE8): an 800 x 600 screen on a 1920 x 1080 desktop, the clip (0, 0, 800, 600), the default font 0;
# the fonts (0x45B270): the game's three, numbered 0, 1, 2.

FISH_STATE, FISH_GRAPHICS, FISH_FONTS = 0x45ABDC, 0x45AFE8, 0x45B270
FISH_CASH, FISH_HELD, FISH_SUPPLY, FISH_SUPPLY_STRIDE = 0x38C, 0x1E4E8, 0x2B8, 0x1C
FISH_TANK, FISH_TANK_STRIDE, FISH_ORNAMENTS, FISH_ORNAMENT_STRIDE = 0x390, 0x51EC, 0x5068 - 0xC, 0x28
# What the tank's start (0x421940) sets on the tank screen's own object: its sliding parts at rest
# (+4, +8, +0xC = 0; the bottom bar's top +0x10 = 485; +0x14 = 496, +0x18 = 639), nothing in the
# hand (+0x1C, +0x28 = 99).
FISH_TANK_AT_REST = ((4, 0), (8, 0), (0xC, 0), (0x10, 0x1E5), (0x14, 0x1F0), (0x18, 0x27F), (0x1C, 0x63), (0x28, 0x63))


class FishScreens(se.ScreenEmulator):
    def __init__(self, size, measure) -> None:
        """`size(name)`: (width, height) of a picture file of the game copy; `measure(font,
        bytes)`: the text's (width, height)."""
        super().__init__("fish", widgets=True)
        emu = self.emu
        self.size, self.measure = size, measure
        self.files: dict[int, str] = {}
        self.draws: list[tuple] = []
        emu.hook(0x409AB0, self._load, 4)
        emu.hook(0x4251A0, lambda e: 0, 4)
        emu.hook(0x42B20B, lambda e: DrawEmulator._sprintf(self, e), 0)
        emu.hook(0x404150, self._blit, 0x1C)
        emu.hook(0x4041C0, self._blit, 0x28)
        emu.hook(0x407940, self._fill, 8)
        emu.hook(0x4087E0, self._text, 0x14)
        emu.hook(0x4023D0, lambda e: self._measure(e)[0], 8)
        emu.hook(0x4024A0, lambda e: self._measure(e)[1], 4)
        holder, impl = self._zeroed(0x10), self._zeroed(0x200)
        emu.write32(holder, impl)
        emu.write32(FISH_GRAPHICS, holder)
        self.graphics, self.impl = holder, impl
        emu.write32(impl + 8, 800)
        emu.write32(impl + 0xC, 600)
        emu.write32(impl + 0x10, 1920)               # the desktop, bigger: a window is possible
        emu.write32(impl + 0x14, 1080)
        emu.write32(impl + 0x30, self._zeroed(0x40))
        for k, v in enumerate((0, 0, 800, 600)):
            emu.write32(impl + 0x38 + 4 * k, v)
        self.fonts: dict[int, int] = {}
        fonts = self._zeroed(0x10)
        for n in range(3):
            font = self._zeroed(0x40)
            self.fonts[font] = n
            emu.write32(fonts + 4 * n, font)
        emu.write32(impl + 0x34, emu.read32(fonts))
        emu.write32(emu.read32(FISH_FONTS), fonts)
        self.state = self._zeroed(0x1E600)
        emu.write32(FISH_STATE, self.state)
        emu.call(0x41AC20, ecx=self.state)
        emu.call(0x41AA70, ecx=self.state)
        emu.write32(self.state + FISH_HELD, 0xFFFFFFFF)

    def _this(self) -> int:
        return self.emu.uc.reg_read(X.UC_X86_REG_ECX)

    def _load(self, emu) -> int:
        this = self._this()
        name = emu.cstring(emu.arg(0)).decode("latin-1")
        w, h = self.size(name)
        surface = self._zeroed(0x40)
        emu.write32(surface + 8, w)
        emu.write32(surface + 0xC, h)
        self.files[surface] = name
        emu.write32(this, surface)
        emu.write8(this + 4, 1)
        return this

    def _blit(self, emu) -> int:
        a = [s32(emu.arg(k)) for k in range(7)]
        if a[5] > a[3] and a[6] > a[4]:
            self.draws.append(("pic", self.files.get(emu.arg(0), "?").casefold(), tuple(a[3:7]), a[1], a[2]))
        return 0

    def _fill(self, emu) -> int:
        rect = struct.unpack("<4i", emu.uc.mem_read(emu.arg(0), 16))
        self.draws.append(("fill", rect, emu.arg(1)))
        return 0

    def _font(self, obj: int) -> int:
        return self.fonts.get(obj or self.emu.read32(self.impl + 0x34), 0)

    def _measure(self, emu) -> tuple:
        return self.measure(self._font(self._this()), emu.cstring(emu.arg(0)) if emu.arg(0) else b"")

    def _text(self, emu) -> int:
        text = emu.cstring(emu.arg(0))
        if text:
            colour = emu.arg(3)
            self.draws.append(("text", text, s32(emu.arg(1)), s32(emu.arg(2)),
                               0xFFFFFFFF if colour >> 24 == 0 else colour, self._font(emu.arg(4))))
        return 0

    # ---- the game's state
    def empty_tank(self, tank: int = 0) -> None:
        """No ornaments in the tank (the new game's plant gone) and no supplies in the slots."""
        at = self.state + FISH_TANK + tank * FISH_TANK_STRIDE + FISH_ORNAMENTS
        for k in range(5):
            self.emu.write8(at + k * FISH_ORNAMENT_STRIDE, 0)
        for k in range(4):
            self.emu.uc.mem_write(self.state + FISH_SUPPLY + k * FISH_SUPPLY_STRIDE, bytes(FISH_SUPPLY_STRIDE))

    # ---- screens and popups
    def children(self, screen: int) -> list:
        out, node = [], self.emu.read32(self.emu.read32(screen + 4) + 0x18)
        while node:
            out.append(self.emu.read32(node))
            node = self.emu.read32(node + 4)
        return out

    def make(self, ctor: int, *args: int, size: int = 0x400) -> int:
        screen = self._zeroed(size)
        self.emu.call(ctor, *args, ecx=screen)
        return screen

    def show(self, screen: int) -> None:
        """Shown (its node's byte, each widget's show(1): the vtable's sixth entry), then painted
        as each frame paints a screen (0x40AC90: its draw, its widgets, its overlay)."""
        self.emu.write8(self.emu.read32(screen + 4), 1)
        for widget in self.children(screen):
            self.emu.call(self.emu.read32(self.emu.read32(widget) + 20), 1, ecx=widget)
        self.draws.clear()
        self.emu.call(0x40AC90, ecx=screen)
