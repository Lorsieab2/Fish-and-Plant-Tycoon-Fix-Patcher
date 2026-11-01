"""Picture Studio: "Screens, bars and buttons", the pictures the games put together from several
pieces: whole screens as assembled, meters and bars empty and filled and joined to their frames,
buttons in each state, rope boxes and dialog boxes, for the tab of that name in "Make your own".

Every number is the game's own (tests/test_picture_screens.py reads them back out of the
executables, and runs Fish Tycoon's meter in Unicorn). Text is not drawn: the words on the
screens and buttons are the game's font text, which the Studio does not draw, so a screen or a
button shows its art only (the tab's note says so).

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

from picture_image import Image, PictureError

# ------------------------------------------------------------------ pieces and pictures


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


def fill(x, y, w, h, rgba) -> Piece:
    return Piece("", x, y, fill=(*rgba, w, h))


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
        pieces += [_button(f, x, y) for f, x, y in FISH_TANK_SCREEN_BUTTONS]
        out.append(Picture(f"screen:tank{k + 1}", screens, f"Tank {k + 1} (empty, no fish held)", tuple(pieces),
                           canvas=(800, 600)))
    menu = [Piece("options_bg.png", 0, 0)] + [_button(f, x, y) for f, x, y in FISH_MENU_BUTTONS] + [Piece(*FISH_TITLE)]
    out.append(Picture("screen:menu", screens, "Main menu", tuple(menu), canvas=(800, 600)))
    shop = [Piece("supplyshop_bg_out.bmp", 0, 0)]
    for k in range(26):
        (ix, iy), shadow, file = fi.STORE[k]
        if shadow:
            shop.append(Piece(fi.SHADOW_FILE, *shadow))
        shop.append(Piece(file, ix, iy))
    shop += [_button("suppliesbuybutton.png", 578, 551), _button("suppliesdonebutton.png", 695, 551)]
    out.append(Picture("screen:supplies", screens, "Supplies store (every item for sale)", tuple(shop), canvas=(800, 600)))
    for key, name, bg, buttons_ in (
            ("sell", "Sell fish", "sellfishshop_bg_png.png", (("selldonebutton.png", 701, 547),)),
            ("species", "Species", "species_bg.bmp", (("speciesdonebutton.png", 690, 546),)),
            ("trophy", "Trophy case", "trophycase_bg.bmp", (("trophycasestatsbutton.png", 577, 547),
                                                             ("trophycasedonebutton.png", 694, 547))),
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


def _tabs(skip: int | None) -> list:
    out = []
    for k, x in enumerate(TAB_XS):
        if k == skip:
            out.append(Piece("lit_button.png", x, TAB_Y))
    for k, x in enumerate(TAB_XS):
        if k != skip:
            out.append(_button("purplePTButton.png", x, TAB_Y))
    return out


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
    bw, bh = 163, 39                                      # widePTButton's frame
    for count in (1, 2):
        span = bw + 60 if count == 1 else 5 * bw // 2 + 60
        width, height = max(2, -(-span // TILE)) * TILE, max(2, -(-(bh + 60) // TILE)) * TILE
        pieces = dialog_tiles("OrangeDlgTileGrid.png", span, bh + 60)
        if count == 1:
            pieces.append(_button("widePTButton.png", (width - bw) // 2, height - bh - 20))
        else:
            x1 = (width - 5 * bw // 2) // 2
            pieces += [_button("widePTButton.png", x1, height - bh - 20),
                       _button("widePTButton.png", x1 + 3 * bw // 2, height - bh - 20)]
        out.append(Picture(f"message{count}", dialogs,
                           f"Message box with {'an OK button' if count == 1 else 'OK and Cancel'} (an empty message)",
                           tuple(pieces)))
    for file, where in PLANT_BUTTONS:
        for frame, state in PLANT_STATES:
            piece = _button(file, 0, 0, 0 if frame == "dim" else frame)
            if frame == "dim":
                piece = Piece(file, 0, 0, cols=3, rows=1, cell=0, dim=True)
            out.append(Picture(f"button:{file}:{frame}", buttons, f"{where} - {state}", (piece,)))
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
    menu += [_button(f, x, y) for f, x, y in (("play_button.png", 433, 337), ("startover_button.png", 210, 259),
                                              ("quit_button.png", 513, 44), ("help_button.png", 199, 414),
                                              ("options_button.png", 304, 521), ("change_button.png", 614, 479))]
    out.append(Picture("screen:menu", screens, "Main menu", tuple(menu), canvas=(800, 600)))
    out.append(Picture("screen:splash", screens, "Splash", (Piece("SPLASH_BG.jpg", 0, 0),), canvas=(800, 600)))
    green = [Piece("main_bg.png", 0, 0), Piece("trashbin.png", 143, 515, cols=2, rows=1), Piece("hose.png", 0, 0),
             _button("snapshot_button.png", 755, 4), _button("widePTButton.png", 31, 369),
             _button("sell_button.png", 31, 407)] + _tabs(None)
    out.append(Picture("screen:greenhouse", screens, "Greenhouse (empty, no pot picked)", tuple(green), canvas=(800, 600)))
    for n in (0, 1, 2):
        seeds = [Piece("SeedBox_BG.jpg", 0, 0)] + _tabs(1)[:1] + [Piece("trashbin.png", 143, 515, cols=2, rows=1)]
        seeds += [Piece("addlSeedBox.png", 239, y) for y in (201, 354)[:n]] + _tabs(1)[1:]
        out.append(Picture(f"screen:seedbox{n}", screens, f"Seed box (empty; {n} extra seed box{'es' if n != 1 else ''})",
                           tuple(seeds), canvas=(800, 600)))
    out.append(Picture("screen:store", screens, "Store (the background and tabs; the shelves are on the Items tab)",
                       (Piece("Store_BG.jpg", 0, 0), *_tabs(2)), canvas=(800, 600)))
    out.append(Picture("screen:nursery", screens, "Nursery (no ornaments)",
                       (Piece("Nursery_BG.jpg", 0, 0), Piece("nurseryUI.png", 0, 484),
                        _button("purplePTButton.png", 227, 540)), canvas=(800, 600)))
    out.append(Picture("screen:collections0", screens, "Collections (no bug caught)",
                       (Piece("collections_bg.jpg", 0, 0), *_tabs(3)[:1], Piece("collection_jars.png", 0, 0),
                        _button("widePTButton.png", 59, 514), *_tabs(3)[1:]), canvas=(800, 600)))
    out.append(Picture("screen:collections48", screens, "Collections (all 48 bugs caught, in their jars)",
                       tuple(collections_screen(range(48))), canvas=(800, 600)))
    for k in range(1, 7):
        out.append(Picture(f"screen:help{k}", screens, f"Help, page {k}",
                           (Piece(f"help{k}.jpg", 0, 0), _button("leftarrow.png", 345, 541),
                            _button("rightarrow.png", 428, 541), _button("widePTButton.png", 28, 553),
                            _button("widePTButton.png", 610, 553)), canvas=(800, 600)))
    for key, name, bg in (("credits", "Credits", "credits.jpg"), ("story1", "Story, page 1", "story1_bg.jpg"),
                          ("gamewin", "Game won", "gamewin_bg.jpg")):
        out.append(Picture(f"screen:{key}", screens, name, (Piece(bg, 0, 0),), canvas=(800, 600)))
    out.append(Picture("screen:story2", screens, "Story, page 2",
                       (Piece("story2_bg.jpg", 0, 0), _button("widePTButton02.png", 228, 560),
                        _button("widePTButton02.png", 428, 560)), canvas=(800, 600)))
    for k in (1, 2, 3):
        out.append(Picture(f"screen:arrangement{k}", screens, f"Snapshot scene {k} (no plants), with its message",
                           (Piece(f"arrangementBG0{k}.jpg", 0, 0), Piece("PhotoMsg.png", 120, 10, scale=60)),
                           canvas=(800, 600)))
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
        out += _tabs(3)[:1]
    for k in caught:
        out += collection_bug(k, on_web=k == web)
    out.append(Piece("collection_jars.png", 0, 0))
    if tabs:
        out += [_button("widePTButton.png", 59, 514)] + _tabs(3)[1:]
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

    def render(self, picture: Picture) -> Image:
        drawn = [(self.piece(p), p.alpha) for p in picture.pieces]
        if picture.canvas:
            left, top, right, bottom = 0, 0, *picture.canvas
        elif picture.crop:
            left, top, right, bottom = picture.crop
        else:
            left = min(x for (im, x, y), _a in drawn)
            top = min(y for (im, x, y), _a in drawn)
            right = max(x + im.width for (im, x, y), _a in drawn)
            bottom = max(y + im.height for (im, x, y), _a in drawn)
        canvas = Image(max(1, right - left), max(1, bottom - top))
        for (image, x, y), alpha in drawn:
            if alpha >= 255:
                canvas.draw(image, x - left, y - top)
            else:
                blend(canvas, image, x - left, y - top, alpha)
        return canvas


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
             "screens (the background, the screen's pieces and its buttons in their normal look), the Health and "
             "Fed meters and the research bar empty, filled at several levels and joined to their frames, every "
             "button in each state (normal, mouse over, pressed; a disabled button is not drawn at all in Fish "
             "Tycoon, so it has no picture), and the rope boxes of the hints and tooltips. Not drawn: the words "
             "(font text), fish, customers and bubbles."),
    "plant": ("The game's pictures made of several pieces, put together exactly as Plant Tycoon draws them: whole "
              "screens (the background, the screen's pieces and its buttons in their normal look), the health and "
              "water meters at several levels (alone and in their slots on the greenhouse panel), the loading bar, "
              "the dialog boxes at their sizes, and every button in each state (normal, mouse over, pressed, "
              "disabled). Not drawn: the words (font text), plants, visitors and the lightbeam. The orange and "
              "green dialog pictures are the same picture in this version of the game."),
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
