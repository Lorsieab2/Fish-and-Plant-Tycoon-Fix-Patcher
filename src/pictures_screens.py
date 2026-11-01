"""Picture Studio: "Screens, bars and buttons", the pictures the games put together from several
pieces: whole screens as assembled, meters and bars empty and filled and joined to their frames,
buttons in each state, rope boxes and dialog boxes, for the tab of that name in "Make your own".

Every number is the game's own (tests/test_picture_screens.py reads them back out of the
executables, and runs Fish Tycoon's meter in Unicorn). The words are drawn as the games draw
them (Text pieces: the game's own text read from the player's copy, its fonts through text_maker,
its colours and its placing; tests/test_picture_screen_words.py runs the games' text code and the
screens' constructors in Unicorn). What is read without running is named in the tab's note.

Fish Tycoon (Fish Tycoon.exe):
* Images: a PNG keeps its alpha (0x409AB0: SDL_DisplayFormatAlpha); a BMP is opaque (the game
  never imports SDL_SetColorKey).
* Meters (0x41BF10(x, y, value)): UI_meter_green_bar.bmp above 50, yellow above 25, red
  otherwise; the source rectangle (0, 0, trunc(value x 130 / 100), 6), unscaled. The Health and
  Fed meters at (658, 506) and (658, 532) (0x41D840) on UI_MAINTANK_BOTTOM_RIGHT_PNG.png at
  (639, 485) (0x41D6E0); the research progress bar: RESEARCH_PROGRESS_BAR.png at (137, 512)
  (0x427415), then the meter at (142, 518) (0x42744F), progress 1..99 (bought at 1, +2 a step).
* Buttons (0x401650): every button picture is a 3 x 1 strip (0x401731); frame 0 normal, 1 mouse
  over, 2 pressed (0x401850, 0x4014F0); a disabled button is not drawn at all (0x4011F0). The
  tank buttons (0x4216E0): frame 2 for the tank shown, 1 / 2 pointed at / pressed, else nothing
  (the top bar's art is their normal look). OptionsRadioButton: frame 0 off, 1 on (0x40A170).
* The rope box (0x423280, the hint and tooltip box): the fill (0x50, 0x4C, 0x40) one pixel larger
  than the box, the four CUSTOMPOPUP_FTROPESTYLE_BAR pictures stepped along its sides, only when
  the box with its rope is at least as big as a top bar and a side bar.
* Screens: the background at (0, 0), the screen's own pieces, then its buttons (0x40AC90).

Plant Tycoon (Plant Tycoon.exe):
* The sprite draws 0x4207F0 / 0x4208F0 take the alpha as a float and the scale as a whole
  percent; alpha A = trunc(alpha x 255 + 0.5), each pixel's alpha (a x A + 127) >> 8, blended
  (src x a + dst x (255 - a) + 127) >> 8 (0x404610, 0x4051A0); a scaled draw is centred on its
  place (0x4078E0) and resampled as pictures_plant.resample.
* Meters (0x423C70(value, x, y, kind), from 0x428250): healthmeter.png at (200, 292) with
  health x 10, watermeter.png at (13, 292) with water 0..1000; v = 1 for 0, else min(value, 1000);
  fill = trunc(h x v / 1000); the rectangle (0, h - fill, w, h) at (x, y + h - fill). The empty
  slots are part of main_bg.png.
* The loading bar (0x44DF60, mode 3, at (240, 500)): pct clamped to 1..100, n =
  trunc(trunc(pct x 320 / 100) / 8) LoadColor.png tiles at (240 + 8k, 500), then
  BambooMeterFrame1.png at (239, 500); nothing at all when n is 0.
* Dialog boxes (0x40CDF0): 64 x 64 tiles of OrangeDlgTileGrid.png / GreenDlgTileGrid.png (the two
  files are the same picture in this build), cols = max(2, ceil(W / 64)), rows likewise; corners
  8, 0, 5, 6, edges 1 (top), 4 (bottom), 3 (left), 2 (right), middle 7.
* Buttons (0x4016F8, 0x4017E0): a 3 x 1 strip, frame 0 normal, 1 mouse over, 2 pressed;
  disabled: frame 0 with each colour (c x 127 >> 8) + 50 (0x409220, tint 0x47A0FC).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from picture_image import Image, PictureError

# ------------------------------------------------------------------ pieces and pictures


@dataclass(frozen=True)
class Text:
    """Words as the game draws them (Fish 0x4087E0, Plant 0x408E20): `parts` joined, each the
    game's own text read from the player's copy of the executable -- ("id", n) a line of its
    string table, ("at", address) a C string in it, ("fmt", address, args) that C string as
    printf fills it (%d / %u / %i / %s; each arg a number or a part) -- or ("sample", "...") a
    sample value for what the game fills in at run time (a player name, a species name).
    `font` is the game's font number (Fish: 0 paddington_tt_18, 1 paddington_tt_30, 2 the
    Triplex font; Plant: 0 PTfontsmall), `colour` the game's 0xAABBGGRR (alpha 0: the default,
    white), `align` how the game places it from x: "left" (0x408B80 / 0x4092A0), "centre"
    (0x408BE0 / 0x4092B0: x - width / 2), "right" (0x408B90: x - width) or "between"
    (0x408C30: centred between x and x2)."""
    parts: tuple
    font: int = 0
    colour: int = 0
    align: str = "left"
    x2: int = 0
    button: str = ""      # align "button": a label centred in this 3 x 1 button picture's frame


def cdiv(a: int, b: int) -> int:
    """C's integer division (toward zero), as the games' cdq / sar pairs do it."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


@dataclass(frozen=True)
class Piece:
    """One draw: cell `cell` of a cols x rows sheet `file` (whole: 1 x 1), the part `src`
    (left, top, right, bottom inside the cell; None: all of it) at (x, y); `alpha` 0..255 (the
    game's), `scale` a whole percent (Plant Tycoon's centred scaler), `dim` Plant Tycoon's
    disabled-button colour. A `fill` (r, g, b, a, w, h) draws a filled rectangle instead."""
    file: str
    x: int
    y: int
    cols: int = 1
    rows: int = 1
    cell: int = 0
    src: tuple | None = None
    alpha: int = 255
    scale: int = 100
    dim: bool = False
    fill: tuple | None = None
    text: Text | None = None
    shade: bool = False   # a fill laid over what is drawn: Plant Tycoon's see-through rectangle


@dataclass(frozen=True)
class Picture:
    key: str
    category: str
    name: str
    pieces: tuple
    crop: tuple | None = None          # (left, top, right, bottom) of the screen shown
    canvas: tuple | None = None        # (w, h): drawn on a screen this big, not cut to its pixels
    unused: bool = False
    patcher: bool = False
    make: Callable | None = field(default=None, compare=False)   # (composer) -> pieces: layouts
    #                                    the game works out from picture and text sizes


def fill(x, y, w, h, rgba) -> Piece:
    return Piece("", x, y, fill=(*rgba, w, h))


# A modal dialog's backdrop (0x401C90 with its second argument 0, every Plant Tycoon dialog and
# message box): the screen under it drawn, then 0x401E57 lays black at alpha 0.25 over all of
# it (0x407B80 -> 0x403870: A = trunc(0.25 x 255 + 0.5) = 64, each channel (c x (255 - A)) >> 8
# + (colour x A) >> 8), then the dialog.
PLANT_SHADE = (0, 0, 0, 64)


def shade(rgba=PLANT_SHADE, w: int = 800, h: int = 600) -> Piece:
    return Piece("", 0, 0, fill=(*rgba, w, h), shade=True)


def say(x: int, y: int, *parts, font: int = 0, colour: int = 0, align: str = "left", x2: int = 0) -> Piece:
    """Words at (x, y), as the game passes them to its text draw."""
    return Piece("", x, y, text=Text(tuple(parts), font, colour, align, x2))


def label(file: str, x: int, y: int, part, colour: int = 0xFFFFFFFF, frame: int = 0, dim: bool = False) -> tuple:
    """A button and its label as the button draws them (Fish 0x4011F0, Plant 0x4011B0): the label
    centred in the frame (by the font's line height), 2 right and down when pressed, in the
    colour the button was given for that state. `dim`: Plant Tycoon's disabled button, frame 0
    dimmed and its label drawn twice at the same place, in its normal colour and then in the
    disabled colour [0x47A0FC] = 0x80646464 (0x40131F: the second draw at the first one's x, y)."""
    shift = 2 if frame == 2 else 0
    button = Piece(file, x, y, cols=3, rows=1, cell=0 if dim else frame, dim=dim)
    words = Piece("", x + shift, y + shift, text=Text((part,), 0, colour, "button", 0, file))
    if dim:
        return button, words, Piece("", x, y, text=Text((part,), 0, PLANT_DIM, "button", 0, file))
    return button, words


PLANT_DIM = 0x80646464                    # [0x47A0FC]: a disabled button's tint and its label's colour


def ident(n: int) -> tuple:
    return ("id", n)


def at(address: int) -> tuple:
    return ("at", address)


def fmt(address: int, *args) -> tuple:
    return ("fmt", address, args)


def sample(text: str) -> tuple:
    return ("sample", text)


def plant_alpha(alpha: float) -> int:
    """0x4050EC: the float alpha as the blitter's 0..255 (trunc(alpha x 255 + 0.5))."""
    from pictures_plant import f32
    return int(f32(alpha) * 255.0 + 0.5)


# ------------------------------------------------------------------ Fish Tycoon

FISH_METER_FILES = {"green": "UI_meter_green_bar.bmp", "yellow": "UI_meter_yellow_bar.bmp", "red": "UI_meter_red_bar.bmp"}
FISH_METER_W = 130
FISH_PANEL = ("UI_MAINTANK_BOTTOM_RIGHT_PNG.png", 639, 485)
FISH_HEALTH_AT, FISH_FED_AT = (658, 506), (658, 532)
FISH_RESEARCH_FRAME = ("RESEARCH_PROGRESS_BAR.png", 137, 512)
FISH_RESEARCH_METER_AT = (142, 518)


def fish_meter(x: int, y: int, value: int) -> list:
    """0x41BF10: the bar for the value, cut to trunc(value x 130 / 100) (C division)."""
    colour = "green" if value > 50 else "yellow" if value > 25 else "red"
    product = value * FISH_METER_W
    width = abs(product) // 100 * (1 if product >= 0 else -1)
    if width <= 0:
        return []
    return [Piece(FISH_METER_FILES[colour], x, y, src=(0, 0, min(width, FISH_METER_W), 6))]


FISH_BUTTONS = (   # every image button: (file, where the game shows it)
    ("mainmenuplaybutton.png", "Main menu: Play"), ("mainmenuoptionsbutton.png", "Main menu: Options"),
    ("mainmenutrophybutton.png", "Main menu: Trophy case"), ("mainmenuhelpbutton.png", "Main menu: Help"),
    ("mainmenuexitbutton.png", "Main menu: Exit"), ("buynowbutton.png", "Main menu: Buy now (trial)"),
    ("maintankmenubutton.png", "Tank: Menu"), ("maintankspeciesbutton.png", "Tank: Species"),
    ("maintanksuppliesbutton.png", "Tank: Supplies"), ("maintanksellbutton.png", "Tank: Sell"),
    ("maintankscreensaverbutton.png", "Tank: Screensaver"),
    ("suppliesbuybutton.png", "Supplies: Buy"), ("suppliesdonebutton.png", "Supplies: Done"),
    ("selldonebutton.png", "Sell fish: Done"), ("speciesdonebutton.png", "Species: Done"),
    ("trophycasestatsbutton.png", "Trophy case: Stats"), ("trophycasedonebutton.png", "Trophy case: Done"),
    ("helpbackbutton.png", "Help: Back"), ("helpnextbutton.png", "Help: Next"),
    ("helpmenubutton.png", "Help: Menu"), ("helpcreditsbutton.png", "Help: Credits"),
    ("introyesbutton.png", "Intro: Yes"), ("intronobutton.png", "Intro: No"),
    ("RopeDlgOkButton.png", "Rope dialogs: OK"), ("RopeDlgCancelButton.png", "Rope dialogs: Cancel"),
    ("RopeDlgRefreshButton.png", "Rope dialogs: Refresh"), ("RopeDlgDeleteButton.png", "Rope dialogs: Delete"),
    ("buyButtonAlert.png", "Buy reminders: Buy"),
)
FISH_STATES = ((0, "normal"), (1, "mouse over"), (2, "pressed"))
FISH_TANK_BUTTONS = (("Tank1Button.png", 513), ("Tank2Button.png", 610), ("SellTankButton.png", 707))
TANK_BUTTON_Y = 2
FISH_TANK_SCREEN_BUTTONS = (("maintankmenubutton.png", 13, 498), ("maintankspeciesbutton.png", 159, 498),
                            ("maintanksuppliesbutton.png", 84, 518), ("maintanksellbutton.png", 230, 518),
                            ("maintankscreensaverbutton.png", 710, 548))
FISH_MENU_BUTTONS = (("mainmenuplaybutton.png", 109, 111), ("mainmenuoptionsbutton.png", 145, 173),
                     ("mainmenutrophybutton.png", 190, 231), ("mainmenuhelpbutton.png", 230, 293),
                     ("mainmenuexitbutton.png", 266, 353))
FISH_TITLE = ("options_fishtycoon_title.bmp", 34, 26)
FISH_HELP = {"back": ("helpbackbutton.png", 75, 548), "next": ("helpnextbutton.png", 663, 550),
             "menu": ("helpmenubutton.png", 285, 541), "credits": ("helpcreditsbutton.png", 437, 541)}
FISH_HELP_PAGES = (("menu", "credits", "next"), ("back", "next", "menu", "credits"),
                   ("back", "next", "menu", "credits"), ("back", "menu", "credits"))

ROPE_FILES = ("CUSTOMPOPUP_FTROPESTYLE_BAR_top.png", "CUSTOMPOPUP_FTROPESTYLE_BAR_bottom.png",
              "CUSTOMPOPUP_FTROPESTYLE_BAR_left.png", "CUSTOMPOPUP_FTROPESTYLE_BAR_right.png")
ROPE_FILL = (0x50, 0x4C, 0x40, 0xFF)          # 0x423217
ROPE_LONG, ROPE_SHORT = 64, 10                # the bars: 64 x 10 (top, bottom), 10 x 64 (sides)


def rope_box(left: int, top: int, right: int, bottom: int) -> list:
    """0x423280: the fill one pixel larger than the box; then, only when the box with its rope is
    at least as wide as a top bar and as tall as a side bar, the bars just outside it: the top one
    right to left and the bottom one left to right from corner to corner, the left one down from
    the box's top, the right one up from its bottom, each step overlapping the last."""
    out = [fill(left - 1, top - 1, right - left + 2, bottom - top + 2, ROPE_FILL)]
    tw, th, lw, lh = ROPE_LONG, ROPE_SHORT, ROPE_SHORT, ROPE_LONG
    ol, ot, orr, ob = left - lw, top - th, right + lw, bottom + th
    if ob - ot < lh or orr - ol < tw:
        return out
    top_f, bottom_f, left_f, right_f = ROPE_FILES
    step_x, step_y = lw // 2 + 2 * lw, th // 2 + 2 * th
    x = orr - tw
    out.append(Piece(top_f, x, ot))
    while x > ol:
        x = max(ol, x + step_x - tw)
        out.append(Piece(top_f, x, ot))
    x = ol
    out.append(Piece(bottom_f, x, bottom))
    while x < orr - tw:
        x = min(orr - tw, x + tw - step_x)
        out.append(Piece(bottom_f, x, bottom))
    y = top
    out.append(Piece(left_f, ol, y))
    while y < ob - lh:
        y = min(ob - lh, y + lh - step_y)
        out.append(Piece(left_f, ol, y))
    y = bottom - lh
    out.append(Piece(right_f, right, y))
    while y > ot:
        y = max(ot, y + step_y - lh)
        out.append(Piece(right_f, right, y))
    return out


def _button(file: str, x: int, y: int, frame: int = 0) -> Piece:
    return Piece(file, x, y, cols=3, rows=1, cell=frame)


# ---- Fish Tycoon's words. Colours: [0x456F7C] etc. hold 0xFF66CCFF (orange); the globals that read
# 0 (never written) are the default colour, white. Fonts: the screens' own font fields are
# GetFont(n) (0x418210 / 0x4181F0) in their constructors; 0 is also the default font (0x418652).
FISH_ORANGE = 0xFF66CCFF
FISH_PANEL_Y = 485                         # [screen + 0x10]: the bottom bar's top (0x41D6FC)
FISH_CASH = say(0x146, FISH_PANEL_Y + 0x59, fmt(0x4439C0, ident(7), 1000))          # 0x41D910
FISH_TIME_STOPPED = say(0, 0x1A4, ident(0), align="between", x2=800)                # 0x41CF20


def fish_info(name: str = "Sample Fish", status: int = 3, age: int = 12) -> list:
    """0x41F800 / 0x41D980 / 0x41DA40: the fish in the isolation tank (or held): its species
    name, "Status: " and its state (Pregnant 3, Sick 4, Dead 5), "Age: " and the age."""
    y = FISH_PANEL_Y
    return [say(0x146, y + 0x14, sample(name), colour=FISH_ORANGE),
            say(0x146, y + 0x28, ident(2)), say(0x18A, y + 0x28, ident(status), colour=FISH_ORANGE),
            say(0x146, y + 0x3B, ident(1)), say(0x178, y + 0x3B, fmt(0x440374, age), colour=FISH_ORANGE)]


def supplies_item(title: int, price: int = 0, level: int = 0, progress: int = 0) -> list:
    """0x4271E0, the picked item: its title (font 1) at (57, 345), its description at (57, 385),
    then a research's level line at (57, 460) and "Progress:" with the research bar, or
    "Price:  $n" at (57, 509)."""
    out = [say(0x39, 0x159, ident(title), font=1, colour=0xFFFFFFFF), say(0x39, 0x181, ident(title + 1))]
    if progress:
        out += [say(0x39, 0x1CC, ident(0xE4 + level)), say(0x39, 0x1FD, ident(0xE7)),
                Piece(*FISH_RESEARCH_FRAME)] + fish_meter(*FISH_RESEARCH_METER_AT, progress)
    else:
        out.append(say(0x39, 0x1FD, fmt(0x44C230, ident(0xAD), price)))
    return out


def sell_words(picked: bool = False) -> list:
    """0x423800: cash, "Fish for sale: " and the count (right-aligned at 409), all font 1; a
    picked fish adds "Price:" and its price, and its name centred at x 117 (font 0)."""
    out = [say(0x29, 0x22F, fmt(0x4439C0, ident(7), 1000), font=1, colour=0xFFFFFFFF),
           say(0xE5, 0x19E, ident(0xF0), font=1, colour=0xFFFFFFFF),
           say(0x199, 0x19F, fmt(0x440374, 3), font=1, colour=FISH_ORANGE, align="right")]
    if picked:
        out += [say(0xE5, 0x1E0, ident(0xAD), font=1, colour=0xFFFFFFFF),
                say(0x130, 0x1E0, fmt(0x443B00, 120), font=1, colour=FISH_ORANGE),
                say(0x75, 0x198, sample("Sample Fish"), align="centre")]
    return out


def species_words() -> list:
    """0x4252C0: "Price:" and the price (font 1), and the family tree's names centred (font 0):
    the species, its parents, its grandparents."""
    out = [say(0x230, 0x5F, ident(0xAD), font=1, colour=0xFFFFFFFF),
           say(0x280, 0x5F, fmt(0x443B00, 50), font=1, colour=FISH_ORANGE),
           say(0x26F, 0xFC, sample("Sample Fish"), align="centre")]
    for x, y in ((0x17E, 0x8F), (0x17E, 0x189), (0x87, 0x5B), (0x87, 0xC9), (0x87, 0x153), (0x87, 0x1C4)):
        out.append(say(x, y, ident(6), align="centre"))
    return out


# 0x4288C0: each empty slot of the trophy case: "#n/7" (its own C string) and questionmark.png
FISH_TROPHY_SLOTS = ((0x44C364, 0xF7, 0xB5, 0xF5, 0x6A), (0x44C35C, 0x20C, 0xB5, 0x20C, 0x6A),
                     (0x44C354, 0x6E, 0x151, 0x70, 0x107), (0x44C34C, 0x293, 0x151, 0x29B, 0x107),
                     (0x44C344, 0xF0, 0x1F1, 0xF3, 0x1A9), (0x44C33C, 0x208, 0x1F1, 0x20C, 0x1A7),
                     (0x44C334, 0x17D, 0x151, 0x180, 0x106))


def trophy_empty() -> list:
    out = []
    for text, tx, ty, ix, iy in FISH_TROPHY_SLOTS:
        out += [say(tx, ty, at(text)), Piece("questionmark.png", ix, iy)]
    return out


# The options popup (0x422530): 270 x 350, centred (0x401D90), a rope box (0x423150); its headers
# (0x40C110: x, y, align) and radio buttons (0x40A7C0: x, y), relative to the popup.
FISH_OPTIONS_SIZE = (0x10E, 0x15E)
FISH_OPTIONS_HEADERS = ((0xC, 0x14, 0xF, "left"), (0xF, 0x8C, 0xF, "left"), (0x13, 0x87, 0x88, "centre"),
                        (0x18, 0x87, 0xE6, "centre"))
FISH_OPTIONS_RADIOS = ((0xD, 0x14, 0x29, True), (0xE, 0x14, 0x45, False), (0x10, 0x92, 0x29, False),
                       (0x11, 0x92, 0x45, True), (0x12, 0x92, 0x61, False), (0x14, 0x10, 0xA2, False),
                       (0x15, 0x92, 0xA2, True), (0x16, 0x10, 0xBE, False), (0x17, 0x92, 0xBE, False),
                       (0x19, 0x10, 0x100, False), (0x1A, 0x92, 0x100, True))


def fish_options(c) -> list:
    """The popup as the game puts it together: a radio's label at (right + 4, its middle) (0x40A170);
    OK at ((270 - 5w/2) / 2, 350 - h/4 - h) and Cancel 3w/2 to its right (w x h: a button frame)."""
    w, h = FISH_OPTIONS_SIZE
    left, top = cdiv(800 - w, 2), cdiv(600 - h, 2)
    out = rope_box(left, top, left + w, top + h)
    bw, bh = c.cell_size("RopeDlgOkButton.png", 3, 1)
    ok_x = cdiv(w - cdiv(5 * bw, 2), 2)
    y = h - cdiv(bh, 4) - bh
    out += [_button("RopeDlgOkButton.png", left + ok_x, top + y),
            _button("RopeDlgCancelButton.png", left + ok_x + cdiv(3 * bw, 2), top + y)]
    for text, x, yy, align in FISH_OPTIONS_HEADERS:
        out.append(say(left + x, top + yy, ident(text), align=align))
    rw, rh = c.cell_size("OptionsRadioButton.png", 2, 1)
    line = c.font(0).line_height
    for text, x, yy, on in FISH_OPTIONS_RADIOS:
        out.append(Piece("OptionsRadioButton.png", left + x, top + yy, cols=2, rows=1, cell=1 if on else 0))
        out.append(say(left + x + rw + 4, top + yy + cdiv(rh - line, 2), ident(text)))
    return out


def fish_message(c, text: int, cancel: bool = False) -> list:
    """The rope message box (0x4221A0): the text (0x40C110, font 0) sets its size: width
    max(text + 40, buttons + 40), height text + button + 60, centred on the screen; the text at
    ((W - text) / 2, 20), OK at ((W - buttons) / 2, H - button - 20), Cancel 3w/2 to its right."""
    data = c.text_bytes(Text((ident(text),)))
    tw, th = c.text_size(0, data)
    bw, bh = c.cell_size("RopeDlgOkButton.png", 3, 1)
    span = cdiv(5 * bw, 2) if cancel else bw
    w, h = max(span + 0x28, tw + 0x28), th + bh + 0x3C
    left, top = cdiv(800 - w, 2), cdiv(600 - h, 2)
    out = rope_box(left, top, left + w, top + h)
    out.append(say(left + cdiv(w - tw, 2), top + 0x14, ident(text)))
    x = left + cdiv(w - span, 2)
    out.append(_button("RopeDlgOkButton.png", x, top + h - bh - 0x14))
    if cancel:
        out.append(_button("RopeDlgCancelButton.png", x + cdiv(3 * bw, 2), top + h - bh - 0x14))
    return out


def _fish_pictures() -> list:
    import pictures_fish_items as fi
    out = []
    meters, bars, buttons, ropes, screens = ("Meters (Health and Fed)", "Research progress bar", "Buttons",
                                             "Rope boxes (hints and tooltips)", "Screens")
    for v in (0, 10, 25, 26, 50, 51, 75, 100):
        colour = "green" if v > 50 else "yellow" if v > 25 else "red"
        out.append(Picture(f"meter{v}", meters, f"A meter alone at {v} ({colour}{', empty: nothing drawn' if not v else ''})",
                           tuple(fish_meter(0, 0, v)) or (fill(0, 0, 1, 1, (0, 0, 0, 0)),)))
    for health, fed in ((100, 100), (100, 50), (75, 30), (51, 26), (50, 25), (25, 10), (10, 0), (0, 0)):
        pieces = [Piece(*FISH_PANEL)] + fish_meter(*FISH_HEALTH_AT, health) + fish_meter(*FISH_FED_AT, fed)
        out.append(Picture(f"panel{health}_{fed}", meters, f"On their panel: Health {health}, Fed {fed}", tuple(pieces)))
    for p in (1, 25, 27, 49, 51, 75, 99):
        pieces = [Piece(*FISH_RESEARCH_FRAME)] + fish_meter(*FISH_RESEARCH_METER_AT, p)
        out.append(Picture(f"research{p}", bars, f"Research progress {p}%", tuple(pieces)))
    for file, where in FISH_BUTTONS:
        for frame, state in FISH_STATES:
            out.append(Picture(f"button:{file}:{frame}", buttons, f"{where} - {state}", (_button(file, 0, 0, frame),)))
    for file, x in FISH_TANK_BUTTONS:
        for frame, state in ((1, "mouse over"), (2, "pressed, or the tank shown")):
            out.append(Picture(f"tankbutton:{file}:{frame}", buttons,
                               f"{file[:-4]} on the top bar - {state}",
                               (Piece("UI_MAINTANK_TOP_PNG.png", 0, 0), _button(file, x, TANK_BUTTON_Y, frame)),
                               crop=(x - 8, 0, x + 95, 57)))
    out.append(Picture("tankbuttons:normal", buttons, "The tank buttons on the top bar - normal (the bar's own art)",
                       (Piece("UI_MAINTANK_TOP_PNG.png", 0, 0),), crop=(505, 0, 800, 57)))
    for frame, state in ((0, "off"), (1, "on")):
        out.append(Picture(f"radio{frame}", buttons, f"Options: radio button - {state}",
                           (Piece("OptionsRadioButton.png", 0, 0, cols=2, rows=1, cell=frame),)))
    out.append(Picture("trashcan", buttons, "Tank: the trash can, open (mouse over it)",
                       (Piece(*FISH_PANEL), Piece("UI_MAINTANK_TRASHCAN_OPEN.png", 650, 541))))
    for w, h, what in ((44, 54, "the smallest box with its whole rope (44 x 54)"),
                       (120, 54, "a one-line tooltip (120 x 54)"), (160, 70, "a two-line tooltip (160 x 70)"),
                       (300, 120, "a hint box (300 x 120)"),
                       (100, 32, "a box too low for its rope (100 x 32): the fill only, as the stock game drew the "
                                 "Fish Food tooltip")):
        out.append(Picture(f"rope{w}x{h}", ropes, what.capitalize(), tuple(rope_box(20, 20, 20 + w, 20 + h))))
    # screens
    tank = []
    for k, bg in enumerate(("MAINTANK1_BG_PNG.png", "MAINTANK2_BG_PNG.png", "MAINTANK3_BG_PNG.png")):
        tank.append((k, bg))
    for k, bg in tank:
        pieces = [Piece(bg, 0, 0), Piece("UI_ISOTANK_PNG.png", 496, 485), Piece("UI_MAINTANK_TOP_PNG.png", 0, 0),
                  Piece("UI_MAINTANK_BOTTOM_LEFT_PNG.png", 0, 485), Piece(*FISH_PANEL)]
        if k < 3:
            file, x = FISH_TANK_BUTTONS[k]
            pieces.append(_button(file, x, TANK_BUTTON_Y, 2))
        pieces += [_button(f, x, y) for f, x, y in FISH_TANK_SCREEN_BUTTONS] + [FISH_CASH]
        out.append(Picture(f"screen:tank{k + 1}", screens, f"Tank {k + 1} (empty, no fish held)", tuple(pieces),
                           canvas=(800, 600)))
        if k == 0:
            tank1 = tuple(pieces)
    out.append(Picture("screen:tank1fish", screens, "Tank 1, a fish in the isolation tank (its words; the fish is "
                       "not drawn)", tank1 + tuple(fish_info()), canvas=(800, 600)))
    out.append(Picture("screen:tank1stopped", screens, "Tank 1, time stopped", tank1 + (FISH_TIME_STOPPED,),
                       canvas=(800, 600)))
    menu = [Piece("options_bg.png", 0, 0)] + [_button(f, x, y) for f, x, y in FISH_MENU_BUTTONS] + [Piece(*FISH_TITLE)]
    out.append(Picture("screen:menu", screens, "Main menu", tuple(menu), canvas=(800, 600)))
    out.append(Picture("screen:options", screens, "Options (over the main menu)", (),
                       canvas=(800, 600), make=lambda c, m=tuple(menu): m + tuple(fish_options(c))))
    for key, ident_, cancel, name in ((0x1C, 0x1C, False, "the first tip"), (0x35, 0x35, False, "a one-line tip"),
                                      (0xEC, 0xEC, True, "a question with OK and Cancel")):
        out.append(Picture(f"screen:tip{key:x}", screens, f"Tank 1 with a message box: {name}", (), canvas=(800, 600),
                           make=lambda c, i=ident_, x=cancel: tank1 + tuple(fish_message(c, i, x))))
    shop = [Piece("supplyshop_bg_out.bmp", 0, 0)]
    for k in range(26):
        (ix, iy), shadow, file = fi.STORE[k]
        if shadow:
            shop.append(Piece(fi.SHADOW_FILE, *shadow))
        shop.append(Piece(file, ix, iy))
    shop += [_button("suppliesbuybutton.png", 578, 551), _button("suppliesdonebutton.png", 695, 551)]
    shop.append(say(0x38, 0x233, fmt(0x4439C0, ident(7), 1000), font=1, colour=0xFFFFFFFF))   # 0x427A43
    out.append(Picture("screen:supplies", screens, "Supplies store (every item for sale)", tuple(shop), canvas=(800, 600)))
    out.append(Picture("screen:supplies:item", screens, "Supplies store, Growth Hormone picked (a sample price)",
                       tuple(shop) + tuple(supplies_item(0xB4, price=25)), canvas=(800, 600)))
    out.append(Picture("screen:supplies:research", screens, "Supplies store, Fish Food Research being researched (51%)",
                       tuple(shop) + tuple(supplies_item(0xDC, level=1, progress=51)), canvas=(800, 600)))
    sell = (Piece("sellfishshop_bg_png.png", 0, 0), _button("selldonebutton.png", 701, 547)) + tuple(sell_words())
    out.append(Picture("screen:sell", screens, "Sell fish (3 for sale)", sell, canvas=(800, 600)))
    out.append(Picture("screen:sell:picked", screens, "Sell fish, a fish picked (a sample name and price)",
                       sell + tuple(sell_words(picked=True)[3:]), canvas=(800, 600)))
    species = (Piece("species_bg.bmp", 0, 0), _button("speciesdonebutton.png", 690, 546))
    out.append(Picture("screen:species", screens, "Species (the price and family tree words; the fish are not drawn)",
                       species + tuple(species_words()), canvas=(800, 600)))
    trophy = (Piece("trophycase_bg.bmp", 0, 0), _button("trophycasestatsbutton.png", 577, 547),
              _button("trophycasedonebutton.png", 694, 547))
    out.append(Picture("screen:trophy", screens, "Trophy case (no Magic Fish found yet)",
                       trophy + tuple(trophy_empty()), canvas=(800, 600)))
    for key, name, bg, buttons_ in (
            ("intro1", "Intro, page 1", "intro1_bg_bmp.bmp", ()),
            ("intro2", "Intro, page 2", "intro2_bg_bmp.bmp", (("introyesbutton.png", 280, 545),
                                                              ("intronobutton.png", 420, 545))),
            ("credits", "Credits", "credits_bg.bmp", ()), ("splash", "Splash", "splash_bg_offf.bmp", ()),
            ("gamewin", "Game won", "gamewin_bg.bmp", ())):
        out.append(Picture(f"screen:{key}", screens, name,
                           (Piece(bg, 0, 0),) + tuple(_button(f, x, y) for f, x, y in buttons_), canvas=(800, 600)))
    for page, names in enumerate(FISH_HELP_PAGES):
        out.append(Picture(f"screen:help{page + 1}", screens, f"Help, page {page + 1}",
                           (Piece(f"help{page + 1}_bg.bmp", 0, 0),) + tuple(_button(*FISH_HELP[n]) for n in names),
                           canvas=(800, 600)))
    return out


# ------------------------------------------------------------------ Plant Tycoon

PLANT_HEALTH = ("healthmeter.png", 200, 292, 140)
PLANT_WATER = ("watermeter.png", 13, 292, 141)
METER_W = 15
PLANT_PANEL_CROP = (0, 280, 240, 445)


def plant_meter(file: str, x: int, y: int, h: int, value: int) -> list:
    """0x423C70: filled from the bottom, trunc(h x v / 1000) rows (v = 1 for 0, at most 1000)."""
    v = 1 if value == 0 else min(value, 1000)
    rows = h * v // 1000 if v >= 0 else -((-h * v) // 1000)
    top = h - rows
    if rows <= 0:
        return []
    return [Piece(file, x, y + top, src=(0, top, METER_W, h))]


def loading_bar(pct: int, x: int = 240, y: int = 500) -> list:
    """0x44DF60 mode 3: whole LoadColor tiles, then the bamboo frame one pixel to the left."""
    pct = max(1, min(100, pct))
    n = pct * 320 // 100 // 8
    if n == 0:
        return []
    return [Piece("LoadColor.png", x + 8 * k, y) for k in range(n)] + [Piece("BambooMeterFrame1.png", x - 1, y)]


DIALOG_FILES = (("OrangeDlgTileGrid.png", "orange"), ("GreenDlgTileGrid.png", "green"))
TILE = 64


def dialog_tiles(file: str, width: int, height: int, x: int = 0, y: int = 0) -> list:
    """0x40CD70 / 0x40CDF0: whole 64 x 64 tiles, at least 2 x 2, never cut."""
    cols, rows = max(2, -(-width // TILE)), max(2, -(-height // TILE))
    out = []
    for r in range(rows):
        for c in range(cols):
            if r == 0:
                cell = 8 if c == 0 else 0 if c == cols - 1 else 1
            elif r == rows - 1:
                cell = 5 if c == 0 else 6 if c == cols - 1 else 4
            else:
                cell = 3 if c == 0 else 2 if c == cols - 1 else 7
            out.append(Piece(file, x + c * TILE, y + r * TILE, cols=9, rows=1, cell=cell))
    return out


def _tile_size(width: int, height: int) -> tuple:
    return max(2, -(-width // TILE)) * TILE, max(2, -(-height // TILE)) * TILE


# The tutorial's message boxes (0x41F230, run in Unicorn by the tests): the message and where its
# pointing arrow points, (direction, x, y): 1 up (arrowglow.png), 2 down (arrowglowdown.png), 3 left
# (arrowleftglow.png), 4 right (arrowrightglow.png, never used); every other message has none.
PLANT_TUTORIAL = {0xA4: (3, 620, 105), 0xA5: (2, 80, 280), 0xA6: (3, 50, 160), 0xA8: (3, 80, 160),
                  0xAA: (3, 170, 50), 0xAC: (3, 40, 200), 0xAF: (3, 200, 480), 0xB0: (1, 140, 320),
                  0xB2: (2, 520, 570), 0xB3: (1, 750, 90), 0xB4: (3, 110, 200), 0xB6: (1, 70, 340),
                  0xB8: (2, 400, 570), 0xBA: (3, 120, 160), 0xBC: (3, 170, 160), 0xBE: (2, 630, 570),
                  0xC0: (1, 100, 400), 0xC2: (2, 750, 570)}
ARROWS = {1: "arrowglow.png", 2: "arrowglowdown.png", 3: "arrowleftglow.png", 4: "arrowrightglow.png"}


def plant_arrow(c, direction: int, x: int, y: int) -> Piece:
    """0x44D8DF: the arrow's picture placed to point at (x, y): up from below it (x - w / 2, y), down
    (x - w / 2, y - h), left (x, y - h / 2), right (x - w, y - h / 2); then pushed along its
    direction by trunc(cos(sin(phase x 3.14159 / 180)) x a quarter of its height (up, down) or
    width (left, right)) (0x44DC12), the phase starting at -360 and stepping 5 or 8 a frame: the
    first frame, drawn here, is pushed out by that quarter less one (it bobs back to about half)."""
    import math
    file = ARROWS[direction]
    w, h = c.cell_size(file)
    amp = (h if direction in (1, 2) else w) // 4
    push = int(math.cos(math.sin(-360.0 * 3.14159 / 180.0)) * amp)
    ax, ay = {1: (x - cdiv(w, 2), y + push), 2: (x - cdiv(w, 2), y - h - push), 3: (x + push, y - cdiv(h, 2)),
              4: (x - w - push, y - cdiv(h, 2))}[direction]
    return Piece(file, ax, ay)


def plant_message(c, text: int, on_screen: bool = False) -> list:
    """The message box (0x44D690): GreenDlgTileGrid tiles for the text + 72 wide and the text + two
    button heights + 36 high (0x44D7BF), the text centred across at (H - that) / 2 + 36
    (0x44DBB0), OK centred at H - h / 2 - h (0x44D874). `on_screen`: where the game shows it, centred
    on the 800 x 600 screen (0x401D20), with the tutorial's pointing arrow (drawn after the text,
    before OK)."""
    data = c.text_bytes(Text((("id", text),)))
    tw, th = c.text_size(0, data)
    bw, bh = c.cell_size("widePTButton.png", 3, 1)
    want_h = th + 2 * bh + 0x24
    w, h = _tile_size(tw + 0x48, want_h)
    x0, y0 = (cdiv(800 - w, 2), cdiv(600 - h, 2)) if on_screen else (0, 0)
    out = dialog_tiles("GreenDlgTileGrid.png", w, h, x0, y0)
    out.append(say(x0 + cdiv(w - tw, 2), y0 + cdiv(h - want_h, 2) + 0x24, ("id", text)))
    if on_screen and text in PLANT_TUTORIAL:
        out.append(plant_arrow(c, *PLANT_TUTORIAL[text]))
    out += label("widePTButton.png", x0 + cdiv(w - bw, 2), y0 + h - cdiv(bh, 2) - bh, ("id", 0x12))
    return out


def plant_question(c, text: int, cancel: bool, green: bool, on_screen: bool = False) -> list:
    """The question box (0x42AB50 -> 0x42A700): Orange- or GreenDlgTileGrid tiles for the wider of
    the text and the buttons, + 60, and the text + a button + 60 high; the text (0x40CBE0)
    centred across at (H - that) / 2 + 20, the buttons at H - h - 20, OK and Cancel 3w/2 apart.
    `on_screen`: centred on the 800 x 600 screen (0x401D20)."""
    data = c.text_bytes(Text((("id", text),)))
    tw, th = c.text_size(0, data)
    bw, bh = c.cell_size("widePTButton.png", 3, 1)
    span = cdiv(5 * bw, 2) if cancel else bw
    want_h = th + bh + 0x3C
    w, h = _tile_size(max(span + 0x3C, tw + 0x3C), want_h)
    x0, y0 = (cdiv(800 - w, 2), cdiv(600 - h, 2)) if on_screen else (0, 0)
    out = dialog_tiles("GreenDlgTileGrid.png" if green else "OrangeDlgTileGrid.png", w, h, x0, y0)
    out.append(say(x0 + cdiv(w - tw, 2), y0 + cdiv(h - want_h, 2) + 0x14, ("id", text)))
    x = x0 + cdiv(w - span, 2)
    out += label("widePTButton.png", x, y0 + h - bh - 0x14, ("id", 0x12))
    if cancel:
        out += label("widePTButton.png", x + cdiv(3 * bw, 2), y0 + h - bh - 0x14, ("id", 0x13))
    return out


# The Options dialog (0x42AF10, opened by the main menu's button 3; its draw 0x42B710): the
# GreenDlgTileGrid picture for 640 x 508 (0x40D160), so 10 x 8 tiles, centred by 0x401D20 at
# (80, 44); its words and radio buttons at L = the dialog's left and T = its top + (512 - 508) / 2
# (0x42B13D..0x42B17C); the title centred at (400, T + 20). The text colour [0x493C70] is never
# written: 0, the text draw's default, white (0x408E7E, [0x47A27C]).
PLANT_OPTIONS_SIZE = (0x280, 0x1FC)
PLANT_OPTIONS_WORDS = ((ident(0x2D), 0x32, 0x3C), (ident(0x2E), 0x32, 0x78), (ident(0x2F), 0x32, 0xAE),
                       (at(0x469428), 0xD8, 0xCC), (at(0x469424), 0x14C, 0xCC), (at(0x469420), 0x1C0, 0xCC),
                       (at(0x46941C), 0x234, 0xCC),
                       (ident(0x3B), 0x32, 0xEF), (ident(0x3C), 0xC8, 0x10D), (ident(0x3D), 0x13C, 0x10D),
                       (ident(0x32), 0x32, 0x130), (ident(0x33), 0xC5, 0x14E), (ident(0x38), 0x12F, 0x14E),
                       (ident(0x35), 0x1AD, 0x14E),
                       (ident(0x36), 0x32, 0x171), (ident(0x37), 0xB1, 0x18F), (ident(0x39), 0x138, 0x18F),
                       (ident(0x38), 0x1A3, 0x18F), (ident(0x3A), 0x221, 0x18F))
PLANT_OPTIONS_RADIO_XS = (0xC8, 0x13C, 0x1B0, 0x224)
PLANT_OPTIONS_SPEEDS = (9999, 15, 10, 2)        # [game + 0x534]: Stop Time, Slow, Normal, Fast
PLANT_OPTIONS_CHECK_XS, PLANT_OPTIONS_CHECK_Y = (0xC8, 0x13C, 0x1B0, 0x224), 0xAE   # the music tracks


def plant_options(c, sound: float = 1.0, music: float = 0.5, windowed: bool = True, difficulty: int = 1,
                  speed: int = 2, tracks: tuple = (True, False, False, False), fullscreen_row: bool = True) -> list:
    """The Options dialog as 0x42B710 and its widgets draw it. The Fullscreen row only when
    ldw.ini forces neither (0x42B0FB); the slider handles at L + 0xCC + trunc(volume x 236); a
    radio: radioselected.png for the setting, radioblank.png for the others; the music tracks'
    check boxes (0x40B1E0, CheckboxStrip.png at the dialog's top + 0xAE) ticked is frame 2, not ticked frame 1
    (0x40AC13: the frame is min(state, cols / 2 - 1), + cols / 2 when ticked); "Done" on
    widePTButton02.png centred across, 2 x (7 - h) above the bottom (0x42B252)."""
    import pictures_plant as pp
    w, h = _tile_size(*PLANT_OPTIONS_SIZE)
    left, top = cdiv(800 - w, 2), cdiv(600 - h, 2)
    L, T = left, top + cdiv(h - PLANT_OPTIONS_SIZE[1], 2)
    out = dialog_tiles("GreenDlgTileGrid.png", w, h, left, top)
    out.append(say(cdiv(w, 2) + left, T + 0x14, ident(9), align="centre"))
    if fullscreen_row:
        out += [say(L + x, T + y, part) for part, x, y in PLANT_OPTIONS_WORDS[7:10]]
        out += _radios(L, T + 0xEF, 2, 1 if windowed else 0)
    out += _radios(L, T + 0x171, 4, speed)
    out += [say(L + x, T + y, part) for part, x, y in PLANT_OPTIONS_WORDS[14:]]
    out += _radios(L, T + 0x130, 3, difficulty)
    out += [say(L + x, T + y, part) for part, x, y in PLANT_OPTIONS_WORDS[10:14]]
    for k, volume in enumerate((sound, music)):
        y = T + (0x3C, 0x78)[k]
        out += [Piece("WideSlider2.png", L + 0xC8, y),
                Piece("sliderhandle.png", L + 0xCC + int(pp.f32(volume) * 236.0), y)]
    out += [say(L + x, T + y, part) for part, x, y in PLANT_OPTIONS_WORDS[:7]]
    bw, bh = c.cell_size("widePTButton02.png", 3, 1)
    out += label("widePTButton02.png", left + cdiv(w, 2) - cdiv(bw, 2), top + h + 2 * (7 - bh), ident(0x192))
    for x, ticked in zip(PLANT_OPTIONS_CHECK_XS, tracks):
        out.append(Piece("CheckboxStrip.png", left + x, top + PLANT_OPTIONS_CHECK_Y, cols=2, rows=1, cell=1 if ticked else 0))
    return out


def _radios(L: int, y: int, n: int, chosen: int) -> list:
    return [Piece("radioselected.png" if k == chosen else "radioblank.png", L + PLANT_OPTIONS_RADIO_XS[k], y)
            for k in range(n)]


# The greenhouse's text button "Replay Tutorial Instruction" (0x424BB0: button 8, no picture, at
# (400, 0); its label white, mouse over and pressed 0xFF003333). The greenhouse takes it off the
# screen at once and shows it only while the tutorial has an instruction to replay (0x428AE1).
# A button without a picture is as big as its label plus 2 all round (0x401079), so the label is
# drawn at its own place, 2 right and down when pressed.
PLANT_REPLAY = (0x190, 0, 0x91)
PLANT_REPLAY_COLOURS = (0xFFFFFFFF, 0xFF003333, 0xFF003333)


def plant_replay(frame: int = 0) -> Piece:
    x, y, text = PLANT_REPLAY
    shift = 2 if frame == 2 else 0
    return say(x + shift, y + shift, ident(text), colour=PLANT_REPLAY_COLOURS[frame])


def plant_pot_words() -> list:
    """A picked pot's words (0x428250 / 0x4286E6 and the helpers 0x44CD80 / 0x44CB30, 0x4232F0):
    its name centred at (118, 254), "NA" seeds at (62, 302), "Age:" and the age, its state at
    (20, 466) and how long to the next stage at (50, 500), all black."""
    black = 0xFF000000
    return [say(0x76, 0xFE, ("id", 0x18E), colour=black, align="centre"),
            say(0x3E, 0x12E, ("id", 0x5F), colour=black),
            say(0x8C, 0x1D2, ("id", 0x40), colour=black), say(0xB7, 0x1D2, ("fmt", 0x4653BC, (3,)), colour=black),
            say(0x14, 0x1D2, ("id", 0x5E), colour=black),
            say(0x32, 0x1F4, ("fmt", 0x4691BC, (("id", 0x18A), 12)), colour=black)]


PLANT_BUTTONS = (
    ("play_button.png", "Main menu: Play"), ("startover_button.png", "Main menu: Start over"),
    ("options_button.png", "Main menu: Options"), ("help_button.png", "Main menu: Help"),
    ("quit_button.png", "Main menu: Quit"), ("change_button.png", "Main menu: Change player"),
    ("playername_button.png", "Main menu: player name"), ("purplePTButton.png", "Bottom tab bar"),
    ("snapshot_button.png", "Greenhouse: Snapshot"), ("sell_button.png", "Greenhouse: Sell"),
    ("widePTButton.png", "Wide button (message boxes, Price, Help)"),
    ("widePTButton02.png", "Wide button 2 (Options OK, Story Yes / No)"),
    ("empty_button.png", "Empty button"), ("leftarrow.png", "Help: back arrow"),
    ("rightarrow.png", "Help: next arrow"), ("arrowup_strip.png", "Up arrow"), ("arrowdown_strip.png", "Down arrow"),
)
PLANT_STATES = ((0, "normal"), (1, "mouse over"), (2, "pressed"), ("dim", "disabled"))
TAB_XS = (236, 349, 462, 575, 688)        # Menu / Main, Seeds, Supplies, Collect, Nursery
TAB_Y = 540


# Each screen's tab labels (its constructor's 0x401570 calls, run in Unicorn by the tests): a
# string-table line or the executable's own C string; the screen's own tab is lit_button.png,
# unlabelled.
PLANT_LILAC = 0xFFD7B9BA                  # the tabs' and menu buttons' normal label colour
PLANT_BLACK = 0xFF000000                  # [0x48C6A0], [0x490548]
GREENHOUSE_TABS = (("id", 0x17E), ("id", 0x17A), ("id", 0x181), ("id", 0x17D), ("id", 0x180))      # 0x424BB0
SEEDBOX_TABS = (("id", 0x191), None, ("at", 0x467B38), ("at", 0x4696F4), ("at", 0x467B30))          # 0x4332C0
STORE_TABS = (("id", 0x191), ("id", 0x17A), None, ("id", 0x17D), ("id", 0x180))                    # 0x446630
COLLECTIONS_TABS = (("id", 0x191), ("at", 0x467B44), ("at", 0x467B38), None, ("at", 0x467B30))      # 0x418E70


# A screen's own tab: lit_button.png and its name in white, left-aligned at (x, 560), drawn by the
# screen itself (Seed box 0x434330, Store 0x447D73, Collections 0x4184E9; colours [0x48EA2C],
# [0x48EB40], [0x482464] all 0xFFFFFFFF).
OWN_TABS = {1: (at(0x467B44), 0x17C), 2: (ident(0x181), 0x1E4), 3: (ident(0x17D), 0x25B)}


def _tabs(skip: int | None, labels: tuple | None = None) -> list:
    own, rest = _split_tabs(skip, labels)
    return own + rest


def _split_tabs(skip: int | None, labels: tuple | None = None) -> tuple:
    """(the screen's own lit tab and its name, the other tabs as buttons)."""
    own, rest = [], []
    for k, x in enumerate(TAB_XS):
        if k == skip:
            own.append(Piece("lit_button.png", x, TAB_Y))
            if k in OWN_TABS:
                part, tx = OWN_TABS[k]
                own.append(say(tx, 0x230, part, colour=0xFFFFFFFF))
    for k, x in enumerate(TAB_XS):
        if k != skip:
            if labels is not None and labels[k] is not None:
                rest += label("purplePTButton.png", x, TAB_Y, labels[k], PLANT_LILAC)
            else:
                rest.append(_button("purplePTButton.png", x, TAB_Y))
    return own, rest


# The trays' names (text widgets 0x40CBE0, centred, colour 0xFF010832, set by 0x40C6C0) on the
# greenhouse (0x424BB0) and the Seed box (0x4332C0), and the trash bin's (0xFF000662).
TRAY_WORDS = {"seeds": (ident(0x17A), 0x6B, 7), "tools": (ident(0x17C), 0x6B, 0x69),
              "seeds2": (ident(0x17A), 0x47, 0x159), "pollen": (ident(0x17B), 0x9F, 0x159)}
TRAY_COLOUR, TRASH_COLOUR = 0xFF010832, 0xFF000662
TRASH_WORD = (ident(0x190), 0xC9, 0x21F)
TOOL_TRAY = (Piece("soilbag_grid.png", 19, 136, cols=2, rows=3), Piece("waterbucket_grid.png", 64, 136, cols=2, rows=3))
POTS = tuple(Piece("pot.png", x, y, cols=1, rows=7) for y in (102, 246, 390) for x in (295, 388, 481, 574, 667))


# The Store's headings (text widgets, centred, white; 0x446630).
STORE_WORDS = ((0x194, 0x21C, 7), (0x195, 0x1D2, 0x25), (0x196, 0x2AB, 0x25), (0x180, 0x1D2, 0x111), (0x197, 0x2AB, 0x111))


def _cash() -> list:
    """CASH and the player's cash (a sample $1000) at the bottom left (0x44CDE0, 0x44CC20)."""
    return [say(0xD, 0x21F, ident(0x3F), colour=0xFFFFFFFF), say(0x4B, 0x221, fmt(0x470C44, 1000), colour=PLANT_BLACK)]


def _tray(*names) -> list:
    return [say(x, y, part, colour=TRAY_COLOUR, align="centre") for part, x, y in (TRAY_WORDS[n] for n in names)]


def _trash() -> list:
    part, x, y = TRASH_WORD
    return [Piece("trashbin.png", 143, 515, cols=2, rows=1), say(x, y, part, colour=TRASH_COLOUR, align="centre")]


def _plant_pictures() -> list:
    out = []
    meters, loading, dialogs, buttons, screens = ("Meters (health and water)", "Loading bar", "Dialog boxes",
                                                  "Buttons", "Screens")
    for h in (0, 1, 10, 25, 50, 75, 100):
        out.append(Picture(f"health{h}", meters, f"Health meter alone at {h}%" + (" (empty: nothing drawn)" if h == 0 else ""),
                           tuple(plant_meter(*PLANT_HEALTH[:3], PLANT_HEALTH[3], h * 10)) or (fill(0, 0, 1, 1, (0, 0, 0, 0)),)))
    for w in (0, 10, 100, 250, 500, 750, 1000):
        out.append(Picture(f"water{w}", meters, f"Water meter alone at {w} of 1000" + (" (nothing drawn)" if w < 8 else ""),
                           tuple(plant_meter(*PLANT_WATER[:3], PLANT_WATER[3], w)) or (fill(0, 0, 1, 1, (0, 0, 0, 0)),)))
    for h, w in ((100, 1000), (75, 600), (50, 500), (25, 200), (10, 50), (0, 0)):
        pieces = [Piece("main_bg.png", 0, 0), Piece("hose.png", 0, 0)]
        pieces += plant_meter(*PLANT_HEALTH[:3], PLANT_HEALTH[3], h * 10) + plant_meter(*PLANT_WATER[:3], PLANT_WATER[3], w)
        out.append(Picture(f"panel{h}_{w}", meters, f"On the greenhouse panel: health {h}%, water {w}",
                           tuple(pieces), crop=PLANT_PANEL_CROP))
    for pct in (1, 3, 10, 25, 50, 75, 99, 100):
        bar = loading_bar(pct)
        out.append(Picture(f"loading{pct}", loading, f"Loading bar at {pct}%" + ("" if bar else " (nothing drawn yet)"),
                           tuple(bar) or (fill(0, 0, 1, 1, (0, 0, 0, 0)),)))
    out.append(Picture("screen:loading", screens, "Loading (the bar at 50%)",
                       (Piece("loading.jpg", 0, 0), *loading_bar(50), Piece("logo1.png", 227, 40),
                        Piece("ldw_logo.png", 600, 400)), canvas=(800, 600)))
    for file, colour in DIALOG_FILES:
        for w, h, what in ((128, 128, "the smallest (2 x 2 tiles)"), (384, 256, "Create nickname (384 x 256)"),
                           (512, 384, "Statistics (512 x 384)"), (512, 448, "Change player (512 x 448)"),
                           (640, 512, "Options (640 x 512)")):
            out.append(Picture(f"dialog:{colour}:{w}x{h}", dialogs, f"{colour.capitalize()} dialog box, {what}",
                               tuple(dialog_tiles(file, w, h))))
    for text, cancel, green in ((0x10A, True, False), (0x77, False, False), (0x3E, True, True)):
        out.append(Picture(f"question:{text:x}", dialogs,
                           f"{'Green' if green else 'Orange'} question box with OK{' and Cancel' if cancel else ''} "
                           "(a real message)", (), make=lambda c, t=text, x=cancel, g=green: plant_question(c, t, x, g)))
    for text in (0x6E, 0x78, 0x8C, 0xAA, 0xCD):
        out.append(Picture(f"message:{text:x}", dialogs, "Message box (a real message)", (),
                           make=lambda c, t=text: plant_message(c, t)))
    for frame in (0, 1):
        out.append(Picture(f"checkbox{frame}", buttons, f"Options: music track check box - {('not ticked', 'ticked')[frame]}",
                           (Piece("CheckboxStrip.png", 0, 0, cols=2, rows=1, cell=frame),)))
    for file, where in PLANT_BUTTONS:
        for frame, state in PLANT_STATES:
            piece = _button(file, 0, 0, 0 if frame == "dim" else frame)
            if frame == "dim":
                piece = Piece(file, 0, 0, cols=3, rows=1, cell=0, dim=True)
            out.append(Picture(f"button:{file}:{frame}", buttons, f"{where} - {state}", (piece,),
                               unused=frame == "dim"))
    # a disabled button with its label: the game never disables a button in this version (nothing
    # clears the enabled byte +0x29 that the constructor 0x401A08 sets), so the look is unused
    for file, text, colour, where in (("widePTButton.png", ident(0x41), PLANT_LILAC, "Greenhouse: Price"),
                                      ("sell_button.png", ident(0x184), PLANT_LILAC, "Greenhouse: Sell"),
                                      ("sell_button.png", ident(0x185), PLANT_LILAC, "Greenhouse: Sell All"),
                                      ("purplePTButton.png", ident(0x17A), PLANT_LILAC, "Bottom tab bar: Seeds"),
                                      ("widePTButton.png", ident(0x12), 0xFFFFFFFF, "Message box: OK"),
                                      ("widePTButton02.png", ident(0x192), 0xFFFFFFFF, "Options: Done")):
        for frame, state in ((0, "normal"), ("dim", "disabled, its label dimmed")):
            out.append(Picture(f"labelled:{file}:{text[1]:x}:{frame}", buttons, f"{where} - {state}",
                               label(file, 0, 0, text, colour, dim=frame == "dim"), unused=frame == "dim"))
    for frame, state in ((0, "closed"), (1, "open (mouse over it)")):
        out.append(Picture(f"trashbin{frame}", buttons, f"Trash bin - {state}",
                           (Piece("trashbin.png", 0, 0, cols=2, rows=1, cell=frame),)))
    for file, state in (("radioblank.png", "not chosen"), ("radioselected.png", "chosen")):
        out.append(Picture(f"radio:{file}", buttons, f"Options: radio button - {state}", (Piece(file, 0, 0),)))
    for v in (0, 50, 100):
        out.append(Picture(f"slider{v}", buttons, f"Options: volume slider at {v}%",
                           (Piece("WideSlider2.png", 0, 0), Piece("sliderhandle.png", 4 + 236 * v // 100, 0))))
    # screens
    menu = [Piece("Menu_BG.jpg", 0, 0), Piece("logo1.png", 16, 17), _button("playername_button.png", 587, 430)]
    for file, x, y, text in (("play_button.png", 433, 337, 7), ("startover_button.png", 210, 259, 8),
                             ("quit_button.png", 513, 44, 9), ("help_button.png", 199, 414, 0xA),
                             ("options_button.png", 304, 521, 0xB), ("change_button.png", 614, 479, 5)):
        menu += label(file, x, y, ident(text), PLANT_LILAC)
    menu += [say(0x29E, 0x1B8, sample("Player"), align="centre"),                         # 0x42A39A
             say(5, 0x244, ident(0xF), colour=0xFFCCCCCC),                                  # 0x42A274
             say(0x316, 0x244, at(0x4692C4), colour=0xFFCCCCCC, align="right")]             # 0x42A2F6
    out.append(Picture("screen:menu", screens, "Main menu (a sample player name)", tuple(menu), canvas=(800, 600)))
    out.append(Picture("screen:options", screens, "Options (over the main menu; sample settings: sounds full, music "
                       "half, windowed, Normal difficulty and speed, music track 1)", (), canvas=(800, 600),
                       make=lambda c, m=tuple(menu): m + (shade(),) + tuple(plant_options(c))))
    out.append(Picture("screen:splash", screens, "Splash", (Piece("SPLASH_BG.jpg", 0, 0),), canvas=(800, 600)))
    # in the game's order (0x40B6B0: the background, the widgets, the overlay)
    green = [Piece("main_bg.png", 0, 0), *_trash(),
             *label("sell_button.png", 115, 407, ident(0x185), PLANT_LILAC),
             *label("sell_button.png", 31, 407, ident(0x184), PLANT_LILAC),
             *label("widePTButton.png", 31, 369, ident(0x41), PLANT_LILAC), _button("snapshot_button.png", 755, 4),
             *_tabs(None, GREENHOUSE_TABS), *_tray("tools", "seeds", "pollen", "seeds2"),
             Piece("hose.png", 0, 0), *TOOL_TRAY, *POTS]
    green += _cash()
    out.append(Picture("screen:greenhouse", screens, "Greenhouse (empty, no pot picked)",
                       tuple(green) + (say(0x76, 0xFE, ident(0x18D), colour=PLANT_BLACK, align="centre"),),
                       canvas=(800, 600)))
    out.append(Picture("screen:greenhouse:replay", screens, "Greenhouse with its hidden text button \"Replay "
                       "Tutorial Instruction\" (shown only while the tutorial has an instruction to replay)",
                       tuple(green) + (say(0x76, 0xFE, ident(0x18D), colour=PLANT_BLACK, align="centre"),
                                       plant_replay()), canvas=(800, 600)))
    for frame, state in ((0, "normal"), (1, "mouse over"), (2, "pressed")):
        out.append(Picture(f"replay{frame}", buttons, f"Greenhouse: Replay Tutorial Instruction (a text button) - {state}",
                           (Piece("main_bg.png", 0, 0), plant_replay(frame)), crop=(380, 0, 640, 30)))
    out.append(Picture("screen:greenhouse:pot", screens, "Greenhouse, a pot picked (its words; the plant is not drawn)",
                       tuple(green) + tuple(plant_pot_words()), canvas=(800, 600)))
    for n in (0, 1, 2):
        own, rest = _split_tabs(1, SEEDBOX_TABS)
        seeds = [Piece("SeedBox_BG.jpg", 0, 0)] + own + [say(0x21C, 7, ident(0x198), colour=0xFFFFFFFF, align="centre"),
                                                         *_tray("seeds", "tools"), *rest, *_trash(), *TOOL_TRAY]
        seeds += [Piece("addlSeedBox.png", 239, y) for y in (201, 354)[:n]]
        out.append(Picture(f"screen:seedbox{n}", screens, f"Seed box (empty; {n} extra seed box{'es' if n != 1 else ''})",
                           tuple(seeds), canvas=(800, 600)))
    store = [Piece("Store_BG.jpg", 0, 0), *_tabs(2, STORE_TABS), *_cash()]
    store += [say(x, y, ident(t), colour=0xFFFFFFFF, align="centre") for t, x, y in STORE_WORDS] + _tray("seeds", "tools")
    out.append(Picture("screen:store", screens, "Store (its words; the shelves are on the Items tab)", tuple(store),
                       canvas=(800, 600)))
    out.append(Picture("screen:nursery", screens, "Nursery (no ornaments)",
                       (Piece("Nursery_BG.jpg", 0, 0), Piece("nurseryUI.png", 0, 484),
                        *label("purplePTButton.png", 227, 540, ident(0x191), PLANT_LILAC)), canvas=(800, 600)))
    own, rest = _split_tabs(3, COLLECTIONS_TABS)
    tabs = own + rest
    out.append(Picture("screen:collections0", screens, "Collections (no bug caught)",
                       (Piece("collections_bg.jpg", 0, 0), *own, Piece("collection_jars.png", 0, 0),
                        *label("widePTButton.png", 59, 514, at(0x467B4C)), *rest), canvas=(800, 600)))
    out.append(Picture("screen:collections48", screens, "Collections (all 48 bugs caught, in their jars)",
                       tuple(collections_screen(range(48))), canvas=(800, 600)))
    for k in range(1, 7):     # 0x420F00: no back arrow on the first page, no next arrow on the last
        arrows = (() if k == 1 else (_button("leftarrow.png", 345, 541),)) +             (() if k == 6 else (_button("rightarrow.png", 428, 541),))
        out.append(Picture(f"screen:help{k}", screens, f"Help, page {k}",
                           (Piece(f"help{k}.jpg", 0, 0), *arrows, *label("widePTButton.png", 28, 553, ident(0x17E)),
                            *label("widePTButton.png", 610, 553, ident(0x19E))), canvas=(800, 600)))
    for key, name, bg in (("credits", "Credits", "credits.jpg"), ("story1", "Story, page 1", "story1_bg.jpg"),
                          ("gamewin", "Game won", "gamewin_bg.jpg")):
        out.append(Picture(f"screen:{key}", screens, name, (Piece(bg, 0, 0),), canvas=(800, 600)))
    out.append(Picture("screen:story2", screens, "Story, page 2",
                       (Piece("story2_bg.jpg", 0, 0), *label("widePTButton02.png", 228, 560, ident(0x10)),
                        *label("widePTButton02.png", 428, 560, ident(0x11))), canvas=(800, 600)))
    for k in (1, 2, 3):
        out.append(Picture(f"screen:arrangement{k}", screens, f"Snapshot scene {k} (no plants), with its message",
                           (Piece(f"arrangementBG0{k}.jpg", 0, 0), Piece("PhotoMsg.png", 120, 10, scale=60),
                            *label("widePTButton.png", 60, 550, ident(0x191)),              # 0x448630
                            *label("widePTButton.png", 310, 550, ident(0x1B2)),
                            *label("widePTButton.png", 560, 550, at(0x469850))), canvas=(800, 600)))
    built = {p.key: p for p in out}
    # question boxes where the game asks them (0x42A605 from the menu, 0x4247CC and 0x428202 in the
    # greenhouse), over the darkened screen
    for text, cancel, green, where, name in ((0x3E, True, True, "screen:menu", "the main menu: Start Over"),
                                              (0x10A, True, False, "screen:greenhouse", "the greenhouse: delete a plant"),
                                              (0x77, False, False, "screen:greenhouse", "the greenhouse: seed box full")):
        out.append(Picture(f"question:{text:x}:screen", dialogs, f"Question box over {name}", (), canvas=(800, 600),
                           make=lambda c, t=text, x=cancel, g=green, b=built[where].pieces: tuple(b) + (shade(),)
                           + tuple(plant_question(c, t, x, g, True))))
    # the tutorial's message boxes where the game shows them: over the screen it is on, darkened
    built = {p.key: p for p in out}
    names = {"screen:greenhouse": "the greenhouse", "screen:store": "the Store", "screen:seedbox0": "the Seed box",
             "screen:collections0": "Collections", "screen:nursery": "the Nursery"}
    for step in range(0xA4, 0xC5):
        where = {0xB3: "screen:store", 0xB9: "screen:seedbox0", 0xBF: "screen:collections0",
                 0xC3: "screen:nursery"}.get(step, "screen:greenhouse")
        arrow = PLANT_TUTORIAL.get(step)
        out.append(Picture(f"tutorial:{step:x}", "Tutorial messages",
                           f"Tutorial message {step - 0xA3} over {names[where]}"
                           + (f", its arrow pointing {('up', 'down', 'left', 'right')[arrow[0] - 1]}" if arrow else ""),
                           (), canvas=(800, 600),
                           make=lambda c, b=built[where].pieces, i=step: b + (shade(),) + tuple(plant_message(c, i, True))))
    return out


# The Collections screen (0x418460): leaf k at LEAVES[k] (table 0x482078), the jar record's place
# JARS[k] (table 0x482208); a bug resting in its jar at the record + (9, 43), frame 0 (0x4194B5);
# the spider of the day on spiderweb.png at the record, the spider at + (2, 10), frame 2.
LEAVES = ((2, 6), (54, 6), (107, 6), (2, 100), (54, 100), (106, 100), (110, 217), (6, 321), (63, 321), (123, 321),
          (96, 415), (191, 22), (191, 125), (191, 230), (191, 332), (191, 429), (270, 2), (270, 88), (270, 171),
          (270, 255), (270, 342), (270, 428), (358, 22), (358, 125), (358, 230), (358, 332), (358, 429), (615, 3),
          (673, 2), (732, 2), (416, 75), (475, 58), (535, 71), (598, 93), (718, 94), (448, 171), (505, 171),
          (561, 171), (615, 171), (692, 171), (744, 171), (427, 343), (481, 343), (535, 343), (592, 343),
          (683, 329), (635, 417), (735, 398))
JARS = ((0, 6), (53, 6), (106, 6), (0, 101), (53, 101), (106, 101), (109, 217), (5, 321), (62, 321), (122, 321),
        (95, 415), (190, 23), (190, 126), (190, 231), (190, 333), (190, 430), (269, 2), (269, 89), (269, 172),
        (269, 256), (269, 343), (269, 429), (357, 23), (357, 126), (357, 231), (357, 333), (357, 430), (614, 3),
        (672, 3), (731, 3), (415, 76), (474, 59), (534, 72), (597, 94), (717, 95), (447, 172), (504, 172),
        (559, 172), (614, 172), (691, 173), (743, 173), (426, 344), (480, 344), (534, 344), (591, 344),
        (682, 330), (634, 417), (734, 399))
JAR_REST, WEB_SPIDER, JAR_BOX = (9, 43), (2, 10), (53, 78)


def collection_bug(bug: int, on_web: bool = False) -> list:
    rx, ry = JARS[bug]
    if on_web:
        return [Piece("spiderweb.png", rx, ry), Piece("small_bugs.png", rx + WEB_SPIDER[0], ry + WEB_SPIDER[1],
                                                       cols=12, rows=24, cell=6 * bug + 2)]
    return [Piece("small_bugs.png", rx + JAR_REST[0], ry + JAR_REST[1], cols=12, rows=24, cell=6 * bug)]


def collections_screen(caught, web: int | None = None, tabs: bool = True) -> list:
    out = [Piece("collections_bg.jpg", 0, 0)]
    out += [Piece("collectionLeafGrid.png", *LEAVES[k], cols=8, rows=6, cell=k) for k in caught]
    if tabs:
        out += _split_tabs(3, COLLECTIONS_TABS)[0]
    for k in caught:
        out += collection_bug(k, on_web=k == web)
    out.append(Piece("collection_jars.png", 0, 0))
    if tabs:
        out += list(label("widePTButton.png", 59, 514, ("at", 0x467B4C))) + _split_tabs(3, COLLECTIONS_TABS)[1]
    return out


def collection_picture(bug: int, on_web: bool = False) -> Picture:
    """Bug k on the Collections screen: the background, its leaf, the bug, the jars over it, cut
    to its jar and leaf."""
    lx, ly = LEAVES[bug]
    rx, ry = JARS[bug]
    crop = (min(lx, rx) - 4, min(ly, ry) - 4, max(lx + 51, rx + JAR_BOX[0]) + 4, max(ly + 79, ry + JAR_BOX[1]) + 4)
    crop = (max(0, crop[0]), max(0, crop[1]), min(800, crop[2]), min(600, crop[3]))
    return Picture(f"collection{bug}{'web' if on_web else ''}", "Bugs", "On the Collections screen",
                   tuple(collections_screen([bug], web=bug if on_web else None, tabs=False)), crop=crop)


# ------------------------------------------------------------------ Plant Tycoon's bugs, drawn by the game
#
# The greenhouse (0x416810, layer 0 before the pots, layer 1 after): cell 6 x bug + frame of
# small_bugs.png at the bug's size, +0x44 = 70 + Random(30) percent, rolled once when it comes
# (0x417820, 0x4178C1, 0x417960, 0x417A18), at alpha 1.0. The walking beetles and spiders have
# shadowsmall.png under them at the same place and size (0x4169B2, 0x416AEB). Frames: butterflies
# fly on 0/1 (right) and 3/4 (left), bugs 4, 5 and 11 also rest on 2; beetles walk on 0/1 and 3/4
# and fly on 2 / 5; beetle 17 (Hiding Beetle) plays dead on 2 / 5 at alpha 0.5 (0x4169C3);
# dragonflies rest on 0 and fly on 2 (right) / 5 (left); spiders walk on 0/1 and 3/4 and drop on
# 2, fading to alpha 2 x (92 - t) / 100 once t > 50 (0x416A82), no shadow while they drop.

GREENHOUSE_SIZES = (70, 85, 99)
BUG_SHEET = ("small_bugs.png", 12, 24)
SHADOW_SMALL = "shadowsmall.png"
PLAYS_DEAD = 16
SPIDER_FADE = (51, 70, 90)


def greenhouse_frames(bug: int) -> tuple:
    family = bug // 12
    if family == 0:
        return (0, 1, 3, 4) + ((2,) if bug in (3, 4, 10) else ())
    if family == 1:
        return (0, 1, 3, 4, 2, 5)
    if family == 2:
        return (0, 2, 5)
    return (0, 1, 3, 4, 2)


def _shadowed(bug: int, frame: int) -> bool:
    return bug // 12 in (1, 3) and frame in (0, 1, 3, 4)


def bug_views(bug: int) -> tuple:
    """(key, label) of every composed picture the game draws of the bug."""
    out = []
    for frame in greenhouse_frames(bug):
        for size in GREENHOUSE_SIZES:
            out.append((f"g{size}_{frame}", f"In the greenhouse: frame {frame + 1}, {size}% size "
                                            "(its size is random, 70-99%)" + (", on its shadow" if _shadowed(bug, frame) else "")))
    if bug == PLAYS_DEAD:
        for frame in (2, 5):
            out.append((f"dead{frame}", f"In the greenhouse: playing dead, frame {frame + 1} (50% see-through, 85% size)"))
    if bug // 12 == 3:
        for t in SPIDER_FADE:
            out.append((f"drop{t}", f"In the greenhouse: dropping, fading ({_fade(t)}% strong, 85% size)"))
    out.append(("jar", "On the Collections screen, in its jar"))
    if bug // 12 == 3:
        out.append(("web", "On the Collections screen, on the web (the spider of the day)"))
    return tuple(out)


def _fade(t: int) -> int:
    from pictures_plant import f32
    return int(round(f32(f32(2.0 * (92 - t)) / 100.0) * 100))


def bug_picture(bug: int, view: str) -> Picture:
    name, cols, rows = BUG_SHEET
    if view == "jar":
        return collection_picture(bug)
    if view == "web" and bug // 12 == 3:
        return collection_picture(bug, on_web=True)
    if view.startswith("g") and "_" in view:
        size, frame = (int(v) for v in view[1:].split("_"))
        if size in GREENHOUSE_SIZES and frame in greenhouse_frames(bug):
            pieces = [Piece(SHADOW_SMALL, 0, 0, scale=size)] if _shadowed(bug, frame) else []
            pieces.append(Piece(name, 0, 0, cols, rows, 6 * bug + frame, scale=size))
            return Picture(view, "Bugs", view, tuple(pieces))
    if view.startswith("dead") and bug == PLAYS_DEAD and view[4:] in ("2", "5"):
        a = plant_alpha(0.5)
        return Picture(view, "Bugs", view, (Piece(SHADOW_SMALL, 0, 0, scale=85),
                                            Piece(name, 0, 0, cols, rows, 6 * bug + int(view[4:]), alpha=a, scale=85)))
    if view.startswith("drop") and bug // 12 == 3 and view[4:].isdigit() and int(view[4:]) in SPIDER_FADE:
        from pictures_plant import f32
        alpha = f32(f32(2.0 * (92 - int(view[4:]))) / 100.0)
        return Picture(view, "Bugs", view, (Piece(name, 0, 0, cols, rows, 6 * bug + 2, alpha=plant_alpha(alpha),
                                                  scale=85),))
    raise PictureError("The game does not draw this bug that way.")


# ------------------------------------------------------------------ rendering


class Composer:
    """Draws a Picture from a pictures_game_art.GameArt's images."""

    def __init__(self, art) -> None:
        self.art = art
        self._by_name = {}
        for sheet in art.sheets:
            if sheet.readable:
                self._by_name.setdefault(sheet.name.casefold(), sheet)

    @classmethod
    def of(cls, art) -> "Composer":
        composer = getattr(art, "_composer", None)
        if composer is None:
            composer = art._composer = cls(art)
        return composer

    def image(self, name: str) -> Image:
        sheet = self._by_name.get(name.casefold())
        if sheet is None:
            raise PictureError(f"{name} is not in the game copy found; click \"Find game...\".")
        return self.art.image(sheet)

    def piece(self, p: Piece) -> tuple:
        """(picture, x, y) of a piece as the game draws it."""
        import picture_image as pi
        if p.fill is not None:
            r, g, b, a, w, h = p.fill
            out = Image(w, h)
            out.data[:] = bytes((r, g, b, a)) * (w * h)
            return out, p.x, p.y
        image = self.image(p.file)
        left, top, right, bottom = pi.cell_rect(image.width, image.height, p.cols, p.rows, p.cell)
        if p.src is not None:
            sl, st, sr, sb = p.src
            left, top, right, bottom = left + sl, top + st, left + sr, top + sb
        piece = image.sub(left, top, right - left, bottom - top)
        x, y = p.x, p.y
        if p.scale != 100:
            import pictures_plant as pp
            scale = pp.f32(p.scale / 100.0)
            w, h = piece.width, piece.height
            sw, sh = pp.ftol(w * scale + 0.5), pp.ftol(h * scale + 0.5)
            x += -pp.half(sw - w)
            y += -pp.half(sh - h)
            piece = pp.resample(piece, p.scale)
        if p.dim:
            piece = piece.copy()
            d = piece.data
            for i in range(0, len(d), 4):
                if d[i + 3]:
                    d[i] = (d[i] * 127 >> 8) + 50
                    d[i + 1] = (d[i + 1] * 127 >> 8) + 50
                    d[i + 2] = (d[i + 2] * 127 >> 8) + 50
        return piece, x, y

    # ---- sizes the games' layouts are worked out from
    def cell_size(self, file: str, cols: int = 1, rows: int = 1) -> tuple:
        import picture_image as pi
        image = self.image(file)
        left, top, right, bottom = pi.cell_rect(image.width, image.height, cols, rows, 0)
        return right - left, bottom - top

    # ---- the game's words
    def _game(self) -> tuple:
        """(fonts by number, executable bytes, string table) of the game copy, read once."""
        cached = getattr(self, "_words", None)
        if cached is not None:
            return cached
        import text_maker as tm
        import translation_strings as ts
        from pathlib import Path
        copy = getattr(self.art.source, "copy", None) if self.art.source is not None else None
        if copy is None or not (Path(copy) / tm.EXE_NAMES[self.art.game]).is_file():
            raise PictureError("The game's words need a game copy: click \"Find game...\".")
        exe = (Path(copy) / tm.EXE_NAMES[self.art.game]).read_bytes()
        loaded = {f.spec.key: f for f in tm.load_fonts(self.art.game, Path(copy))}
        fonts = [loaded.get(spec.key) for spec in tm.FONTS[self.art.game] if spec.table is not None]
        strings = {s.id: s.english.encode("cp1252", "replace") for s in ts.read_table(self.art.game, exe)}
        self._words = (fonts, exe, strings)
        return self._words

    def font(self, number: int):
        fonts = self._game()[0]
        font = fonts[number] if number < len(fonts) else None
        if font is None:
            raise PictureError("The game's font picture is not in the game copy found.")
        return font

    def c_string(self, address: int) -> bytes:
        import translation_strings as ts
        exe = self._game()[1]
        at_ = ts._offset(exe, address)
        return exe[at_:exe.index(b"\0", at_)]

    def part(self, part) -> bytes:
        if isinstance(part, int):
            return b"%d" % part
        kind = part[0]
        if kind == "id":
            return self._game()[2].get(part[1], b"")
        if kind == "at":
            return self.c_string(part[1])
        if kind == "sample":
            return part[1].encode("cp1252")
        if kind == "fmt":
            import re
            args = list(part[2])

            def one(match):
                value = args.pop(0)
                if match.group(1) == b"s":
                    return self.part(value) if not isinstance(value, bytes) else value
                return b"%d" % (value if isinstance(value, int) else int(self.part(value)))
            return re.sub(rb"%([dsui])", one, self.c_string(part[1]))
        raise PictureError(f"unknown text part {part!r}")

    def text_bytes(self, text: Text) -> bytes:
        return b"".join(self.part(p) for p in text.parts)

    def text_size(self, font_number: int, data: bytes) -> tuple:
        """The game's text width (Fish 0x4023D0, Plant 0x402380: each line the sum of its
        letters' widths and the spacing, the widest line, less one spacing) and height (0x4024A0
        / 0x402450: one line height per line)."""
        font = self.font(font_number)
        widest = 0
        for line in data.split(b"\n"):
            widest = max(widest, sum(font.game_glyph(b).advance + font.spacing for b in line))
        if widest:
            widest -= font.spacing
        return widest, font.line_height * (data.count(b"\n") + 1)

    def text_place(self, p: Piece) -> tuple:
        """(bytes, x, y, width, height) of a text piece where the game draws it."""
        data = self.text_bytes(p.text)
        w, h = self.text_size(p.text.font, data)
        x = p.x
        if p.text.align == "centre":
            x -= cdiv(w, 2)
        elif p.text.align == "right":
            x -= w
        elif p.text.align == "between":
            x += cdiv(p.text.x2 - p.x - w, 2)
        elif p.text.align == "button":         # 0x401250 / 0x4011F0: centred in the frame
            cw, ch = self.cell_size(p.text.button, 3, 1)
            x += cdiv(cw - w, 2)
            return data, x, p.y + cdiv(ch - self.font(p.text.font).line_height, 2), w, h
        return data, x, p.y, w, h

    def draw_text(self, canvas: Image, p: Piece, data: bytes, x: int, y: int) -> None:
        """The game's draw loop (text_maker.render_game_bytes): each byte's letter in the colour
        (each channel ANDed, 0x402730), SDL's blend where the screen is opaque."""
        import text_maker as tm
        font = self.font(p.text.font)
        colour = p.text.colour & 0xFFFFFFFF
        if colour >> 24 == 0:
            colour = 0xFFFFFFFF                       # the default colour: white
        rgb = ((colour & 0xFF) << 16) | (colour & 0xFF00) | ((colour >> 16) & 0xFF)
        # Plant Tycoon: a colour less than opaque draws each letter with its alpha blit at A / 255
        # (0x408F21 -> 0x404610), the colour's alpha byte otherwise unused (0x402700 keeps the
        # letters' own alpha)
        see_through = self.art.game == "plant" and colour >> 24 != 0xFF
        if see_through:
            import pictures_plant as pp
            alpha = plant_alpha(pp.f32((colour >> 24) / 255.0))
        start = x
        for byte in data:
            if byte == 0x0A:
                x, y = start, y + font.line_height
                continue
            glyph = font.game_glyph(byte)
            if glyph.advance == 0:
                continue
            letter = tm.tint(glyph.pixels, rgb)
            if see_through:
                blend(canvas, letter, x, y, alpha)
            elif _opaque_under(canvas, x, y, letter.width, letter.height):
                tm.sdl_blend(canvas, letter, x, y)
            else:
                canvas.draw(letter, x, y)
            x += glyph.advance + font.spacing

    def pieces(self, picture: Picture) -> tuple:
        return tuple(picture.make(self)) if picture.make is not None else picture.pieces

    def render(self, picture: Picture) -> Image:
        drawn = []
        for p in self.pieces(picture):
            if p.text is not None:
                data, x, y, w, h = self.text_place(p)
                drawn.append(("text", p, data, x, y, w, h))
            else:
                image, x, y = self.piece(p)
                drawn.append(("image", p, image, x, y, image.width, image.height))
        if picture.canvas:
            left, top, right, bottom = 0, 0, *picture.canvas
        elif picture.crop:
            left, top, right, bottom = picture.crop
        else:
            left = min(d[3] for d in drawn)
            top = min(d[4] for d in drawn)
            right = max(d[3] + d[5] for d in drawn)
            bottom = max(d[4] + d[6] for d in drawn)
        canvas = Image(max(1, right - left), max(1, bottom - top))
        for kind, p, what, x, y, _w, _h in drawn:
            if p.shade:
                _shade(canvas, p.fill, x - left, y - top)
            elif kind == "text":
                self.draw_text(canvas, p, what, x - left, y - top)
            elif p.alpha >= 255:
                canvas.draw(what, x - left, y - top)
            else:
                blend(canvas, what, x - left, y - top, p.alpha)
        return canvas


def _shade(canvas: Image, rgbaw: tuple, x: int, y: int) -> None:
    """0x403870: the rectangle's colour at alpha A over the screen, channel by channel."""
    r, g, b, a, w, h = rgbaw
    add = ((r * a) >> 8, (g * a) >> 8, (b * a) >> 8)
    keep = 255 - a
    table = [bytes(((v * keep) >> 8) + add[c] & 0xFF for v in range(256)) for c in range(3)]
    d = canvas.data
    for yy in range(max(0, y), min(canvas.height, y + h)):
        for xx in range(max(0, x), min(canvas.width, x + w)):
            i = (yy * canvas.width + xx) * 4
            d[i], d[i + 1], d[i + 2] = table[0][d[i]], table[1][d[i + 1]], table[2][d[i + 2]]


def _opaque_under(canvas: Image, x: int, y: int, w: int, h: int) -> bool:
    a = canvas.data
    for yy in range(max(0, y), min(canvas.height, y + h)):
        row = yy * canvas.width
        for xx in range(max(0, x), min(canvas.width, x + w)):
            if a[(row + xx) * 4 + 3] != 255:
                return False
    return True


def blend(canvas: Image, src: Image, x: int, y: int, alpha: int) -> None:
    """Plant Tycoon's alpha blit (0x404610, 0x4051A0): a' = (a x A + 127) >> 8, then on an opaque
    pixel (src x a' + dst x (255 - a') + 127) >> 8; on a clear one the piece as it is, see-through."""
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(canvas.width, x + src.width), min(canvas.height, y + src.height)
    sd, dd = src.data, canvas.data
    for yy in range(y0, y1):
        s = ((yy - y) * src.width + (x0 - x)) * 4
        d = (yy * canvas.width + x0) * 4
        for _ in range(x1 - x0):
            a = (sd[s + 3] * alpha + 127) >> 8
            if a:
                if dd[d + 3] == 255:
                    for c in range(3):
                        dd[d + c] = (sd[s + c] * a + dd[d + c] * (255 - a) + 127) >> 8
                elif dd[d + 3] == 0:
                    dd[d:d + 3] = sd[s:s + 3]
                    dd[d + 3] = a
                else:                         # over a see-through pixel: straight-alpha "over"
                    da = dd[d + 3]
                    keep = da * (255 - a)
                    total = a * 255 + keep
                    for c in range(3):
                        dd[d + c] = (sd[s + c] * a * 255 + dd[d + c] * keep + total // 2) // total
                    dd[d + 3] = (total + 127) // 255
            s += 4
            d += 4


# ------------------------------------------------------------------ the tab

NOTE = {
    "fish": ("The game's pictures made of several pieces, put together exactly as Fish Tycoon draws them: whole "
             "screens (the background, the screen's pieces and its buttons in their normal look) with their "
             "words, the Options popup, message boxes, the Health and Fed meters and the research bar empty, "
             "filled at several levels and joined to their frames, every button in each state (normal, mouse "
             "over, pressed; a disabled button is not drawn at all in Fish Tycoon, so it has no picture), and the "
             "rope boxes of the hints and tooltips. The words are the game's own text from your copy of the game "
             "in its own fonts and colours; a player's cash ($1000), counts, prices, ages and names are sample "
             "values. Checked by running the game's code: the text widths and heights, the text draw and its "
             "left / centred / right / between placing, the Options popup's headers and radio buttons. Read "
             "from the code without running it: where each screen puts its words, the message box's and the "
             "Options popup's sizes and their OK / Cancel places, a radio button's label beside it. Not drawn: "
             "tooltip text, fish, customers and bubbles."),
    "plant": ("The game's pictures made of several pieces, put together exactly as Plant Tycoon draws them: whole "
              "screens (the background, the screen's pieces and its buttons in their normal look) with their "
              "words and button labels, message and question boxes sized for real messages, the health and water "
              "meters at several levels (alone and in their slots on the greenhouse panel), the loading bar, the "
              "dialog boxes at their sizes, and every button in each state (normal, mouse over, pressed, "
              "disabled). The words are the game's own text from your copy of the game in its own font and "
              "colours; cash, ages, times and the player's name are sample values. Checked by running the game's "
              "code: every screen's buttons and labels (the Sell All button, the snapshot scene's three buttons), "
              "the text widths and heights, the text draw and its placing. Read from the code without running "
              "it: the greenhouse panel's words, the main menu's version, copyright and player name, the message "
              "and question boxes' sizes and places (and which question box is orange or green), the check box "
              "picture's two frames (which one is ticked is not traced). Not drawn: a disabled button's label, the "
              "message box's pointing arrow, the Options dialog's words, plants, visitors and the lightbeam. The "
              "orange and green dialog pictures are the same picture in this version of the game."),
}


def pictures(game: str) -> tuple:
    cache = _CACHE.get(game)
    if cache is None:
        cache = _CACHE[game] = tuple(_fish_pictures() if game == "fish" else _plant_pictures())
    return cache


_CACHE: dict = {}


def categories(game: str) -> tuple:
    return tuple(dict.fromkeys(p.category for p in pictures(game)))


def by_key(game: str) -> dict:
    return {p.key: p for p in pictures(game)}


def fields(art, spec: dict) -> dict:
    from picture_image import Option
    cats = categories(art.game)
    category = spec.get("category") if spec.get("category") in cats else cats[0]
    options = tuple(Option(p.key, p.name, p.patcher, p.unused) for p in pictures(art.game) if p.category == category)
    return {"category": tuple(Option(c, c) for c in cats), "picture": options}


def subject(art):
    from picture_image import Field, Subject
    f = fields(art, {})
    note = NOTE[art.game]
    if art.problem:
        note = art.problem + " " + note
    return Subject("screens", "Screens, bars and buttons", (
        Field("category", "Category", f["category"], f["category"][0].key),
        Field("picture", "Picture", f["picture"], f["picture"][0].key)), note)


def batch(art) -> list:
    if art.source is None:
        return []
    return [((p.category,), p.name, {"subject": "screens", "category": p.category, "picture": p.key})
            for p in pictures(art.game)]


def render(art, spec: dict) -> Image:
    picture = by_key(art.game).get(str(spec.get("picture") or ""))
    if picture is None:
        raise PictureError("Pick a picture.")
    return Composer.of(art).render(picture)
