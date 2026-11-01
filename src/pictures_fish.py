"""Picture Studio, Fish Tycoon: the fish, creatures and decorations of a save, and pictures
made from any body, fin, age and state, drawn by the game's own rules (see
docs/picture-studio-interface.md for the interface, and tests/test_pictures_fish.py for the
proof: every plan here is compared with the draw calls of the game's own code, run in
Unicorn on the vanilla executable).

The rules, from the vanilla Fish Tycoon.exe:

* Sprites (0x41BCA0, the sprite table 0x4552F0: file, columns, rows). A fish's sprite ids
  are set by 0x415DF0(sprite, body, fin): body 10001 + 100 x body, top fin 10061 + 100 x fin,
  bottom fin 10031 + 100 x fin, the fins' surface alpha by fin (0x411100) and the fins' anchor
  points by body (0x4111E0). 0x4122A0 turns an id into a table entry (38 + 3 x gene, + 1 the
  bottom fin sheet, + 2 the top) and a cell.
* Grid cells (0x4095F0): width // columns by height // rows, column and row clamped.
* The fish draw 0x4145F0(x, y, fish, mode, body frame, fin frame, stage): the body is drawn at
  y + (56 - h) / 2, h being the view's body height (0x415460: 32 a baby, 48 a teen, the body
  cell's height an adult). Mode 1 swims left (body cells 0-5, fins at x + 50 - anchor), mode
  0 right (cells 6-11, fins at x + anchor), modes 3 and 4 turn (cells 12-17, each fin at
  x + 44 + c - anchor, c = 0, -13, -13, 10, 10, 10 by frame, the bottom fin 4 higher). Both
  fins are drawn before the body, with the fin's surface alpha; an adult sick with ick (1)
  or fungus (2) gets three spots (ick1.png / ick2.png) after it, only while swimming left
  or right.
* Stages (0x415460): age 0 is not drawn; a living fish under 6 is a baby (FISH_baby_Grid,
  one sheet for every fish, cell = mode offset + frame), under 20 a teen (FISH_teen_Grid, row
  = body, drawn at (age x 3 + 82)% by the scaled draw 0x408190), else an adult. Dead babies
  and teens are FISH_teen_dead_Grid cell age % 4; a dead adult is FISH_adult_dead_Grid cell
  = body. Body 22 is the Golden Seahorse (stage 3: seahorse_body_Grid).
* The blitter 0x4041C0: a fin's pixel alpha a becomes (a x alpha + 127) >> 8 (alpha 200,
  210 or 240; 255 draws as it is); a teen is scaled nearest-neighbour (picture_image).
* Ornaments (0x41D600): six 0x2C-byte records per tank at state + 0x5208 + tank x 0x51EC;
  each resting one has TANK_OBJECT_SHADOW.png at (x - 25, y + h - 25) under it.
* The plants and equipment (0x41D340, 0x41EE60): game-wide flags at state + 0x118 +
  k x 0x14, drawn as their own pictures.

The patcher's own (from its DLL sources): DS Exclusive Fish (native/ftfp_ds_fish: genes 23-29
on their own sheets, the pair anchors and head-on rule of pictures_fish_ds, the DS teen and
dead sheets) and DS Store Items (native/ftfp_ds_store: the Puffer Fish, Sting Ray and Moray
Eel, fish records with body 22 and fin 30-32 drawn from their own sheets, and the eel's rock).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import struct

import picture_image as pi
from picture_image import Draw, Field, Option, PictureError, SavedItem, Subject

try:
    import pictures_fish_ds as ds_data
except ImportError:                                   # pragma: no cover - shipped together
    ds_data = None

GAME = "fish"
PATCHER_ROOT = Path(__file__).resolve().parents[1]

# ------------------------------------------------------------------ the sprite table

PC_LAST, SEAHORSE, DS_FIRST, DS_LAST = 20, 22, 23, 29
DS_SPRITE_BASE, DS_SPRITE_TEEN, DS_SPRITE_DEAD = 197, 218, 219       # ftfp_ds_fish.c
STORE_SPRITE_BASE = 220                                              # ftfp_ds_store.c
SPR_SHEET, SPR_ROCK, SPR_ROCK_HOME = STORE_SPRITE_BASE + 5, STORE_SPRITE_BASE + 8, STORE_SPRITE_BASE + 9
SPR_HOME_BACK, SPR_HOME_FRONT, SPR_PUFF = STORE_SPRITE_BASE + 10, STORE_SPRITE_BASE + 11, STORE_SPRITE_BASE + 12

# The stock entries the pictures use (0x4552F0): index -> (file, columns, rows). A plain
# image (columns 0) is drawn whole.
STOCK_SHEETS = {
    1: ("SUPPLYSHOP_ITEMFORSALE_AERATOR.png", 0, 0), 2: ("ITEM_heater.png", 0, 0),
    3: ("TANK_OBJECT_SHADOW.png", 0, 0),
    5: ("TANKOBJECT_PLANT17_BAYLEAF.png", 0, 0), 6: ("TANKOBJECT_PLANT05_ORANGEFLOWER.png", 0, 0),
    7: ("TANKOBJECT_PLANT06_PURPLE.png", 0, 0), 8: ("TANKOBJECT_PLANT07_REDGREEN.png", 0, 0),
    13: ("ick1.png", 0, 0), 14: ("ick2.png", 0, 0),
    15: ("ITEM_snail_vleft_up.png", 0, 0), 16: ("ITEM_snail_h_left.png", 0, 0),
    17: ("ITEM_snail_vright_down.png", 0, 0), 18: ("ITEM_snail_vright_up.png", 0, 0),
    19: ("ITEM_snail_h_right.png", 0, 0), 20: ("ITEM_snail_vleft_down.png", 0, 0),
    34: ("FISH_baby_Grid.png", 18, 1), 35: ("FISH_teen_dead_Grid.png", 4, 1),
    36: ("FISH_teen_Grid.png", 18, 21), 37: ("FISH_adult_dead_Grid.png", 7, 3),
    101: ("seahorse_body_Grid.png", 16, 2), 112: ("eggs_Grid.png", 16, 1),
    177: ("shell02.png", 0, 0), 178: ("pagoda1.png", 0, 0), 179: ("diverblue.png", 0, 0),
    180: ("column01.png", 0, 0), 181: ("beigecoral.png", 0, 0), 182: ("junk1.png", 0, 0),
}
PART_SHEETS = ("body", "bot", "top")                 # entry 38 + 3 g + 0, 1, 2
PART_GRID = {"body": (7, 3), "bot": (13, 2), "top": (13, 2)}
STORE_SHEETS = {                                      # ftfp_ds_store.c SPRITE_FILES, 220 + k
    SPR_SHEET: ("DS_PUFFER_Grid.png", 6, 3), SPR_SHEET + 1: ("DS_STINGRAY_Grid.png", 6, 3),
    SPR_SHEET + 2: ("DS_EEL_Grid.png", 6, 3), SPR_ROCK: ("DS_EEL_ROCK.png", 0, 0),
    SPR_ROCK_HOME: ("DS_EEL_ROCK.png", 0, 0), SPR_HOME_BACK: ("DS_EEL_HOME_BACK_Grid.png", 4, 8),
    SPR_HOME_FRONT: ("DS_EEL_HOME_FRONT_Grid.png", 4, 8), SPR_PUFF: ("DS_PUFFER_PUFF_Grid.png", 4, 2),
}


# Eggs dropped into a tank: the tank's effect 15 (set up at 0x410CE6: sprite 0x70, eggs_Grid.png,
# surface alpha 175), drawn by the effects pass 0x410F50 at cell = its frame (16 cells, wrapping).
# No fish is drawn before it hatches (age 0, 0x415460); a hatched fish is a baby (fry) to age 5.
SPR_EGGS, EGGS_ALPHA, EGG_FRAMES = 112, 175, 16


def plan_eggs(frame: int, x: int = 0, y: int = 0) -> list:
    """0x410F50 for the eggs effect: its grid cell at (x, y), alpha 175, unscaled."""
    return [draw_cell(SPR_EGGS, x, y, frame % EGG_FRAMES, alpha=EGGS_ALPHA)]


def is_ds(gene: int) -> bool:
    return DS_FIRST <= gene <= DS_LAST


def sheet(index: int) -> tuple[str, int, int]:
    """The sprite table entry: the stock table, then DS Exclusive Fish's and DS Store Items'."""
    if index in STOCK_SHEETS:
        return STOCK_SHEETS[index]
    if 38 <= index <= 100:
        gene, part = divmod(index - 38, 3)
        cols, rows = PART_GRID[PART_SHEETS[part]]
        return f"FISH_{gene:02d}_{PART_SHEETS[part]}_Grid.png", cols, rows
    if DS_SPRITE_BASE <= index < DS_SPRITE_TEEN:
        k, part = divmod(index - DS_SPRITE_BASE, 3)
        cols, rows = PART_GRID[PART_SHEETS[part]]
        return f"FISH_{DS_FIRST + k}_{PART_SHEETS[part]}_Grid.png", cols, rows
    if index == DS_SPRITE_TEEN:
        return "FISH_DS_teen_Grid.png", 18, DS_LAST - DS_FIRST + 1
    if index == DS_SPRITE_DEAD:
        return "FISH_DS_adult_dead_Grid.png", DS_LAST - DS_FIRST + 1, 1
    if index in STORE_SHEETS:
        return STORE_SHEETS[index]
    raise PictureError(f"No picture is known for sprite {index}.")


def draw_cell(index: int, x: int, y: int, frame: int = 0, alpha: int = 255, scale: int = 100) -> Draw:
    """A draw of sprite `index`: a grid's cell `frame` (0x407EF0), or a plain image whole (0x407D60)."""
    file, cols, rows = sheet(index)
    if cols == 0:
        return Draw(file, 1, 1, 0, x, y, alpha=alpha, scale=scale)
    return Draw(file, cols, max(1, rows), frame, x, y, alpha=alpha, scale=scale)


# ------------------------------------------------------------------ 0x415DF0: a fish's sprites

# 0x411100: the fins' surface alpha by fin (anything else: 210).
FIN_ALPHA = (255, 200, 200, 200, 210, 210, 210, 210, 210, 210, 210, 210, 210, 210, 210, 240, 210, 210, 210, 240, 210)
DEFAULT_ALPHA = 210
# 0x4111E0: the fin anchors by body, (top x, top y, bottom x, bottom y) (anything else: the last).
BODY_ANCHORS = (
    (20, -15, 12, 33), (18, -10, 21, 37), (13, -10, 12, 36), (13, -13, 12, 42), (15, -13, 24, 36),
    (17, -12, 22, 33), (14, -17, 23, 33), (10, -10, 17, 38), (15, -14, 11, 40), (12, -11, 18, 35),
    (15, -23, 21, 34), (15, -13, 21, 33), (15, -13, 21, 33), (4, -15, 5, 35), (20, -16, 23, 39),
    (20, -16, 16, 39), (13, -20, 21, 29), (15, -13, 18, 37), (14, -20, 16, 32), (10, -16, 15, 35),
    (17, -17, 21, 36),
)
DEFAULT_ANCHORS = (10, -16, 15, 37)


@dataclass(frozen=True)
class Sprites:
    """A fish record's sprite fields (+0x54..+0x74)."""
    body_id: int
    top_id: int
    bot_id: int
    alpha: int
    top: tuple
    bot: tuple


def fish_sprites(body: int, fin: int) -> Sprites:
    """0x415DF0, with DS Exclusive Fish's pair anchors for a pair with a DS gene (pair_anchors)."""
    alpha = FIN_ALPHA[fin] if 0 <= fin <= PC_LAST else DEFAULT_ALPHA
    anchors = BODY_ANCHORS[body] if 0 <= body <= PC_LAST else DEFAULT_ANCHORS
    if (is_ds(body) or is_ds(fin)) and _valid(body) and _valid(fin) and ds_data is not None:
        anchors = ds_data.PAIR_ANCHOR[(body, fin)]
    return Sprites(10001 + 100 * body, 10061 + 100 * fin, 10031 + 100 * fin, alpha,
                   tuple(anchors[0:2]), tuple(anchors[2:4]))


def _valid(gene: int) -> bool:
    return 0 <= gene <= PC_LAST or is_ds(gene)


def _cdiv(a: int, b: int) -> int:
    """C integer division (toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def _cmod(a: int, b: int) -> int:
    return a - _cdiv(a, b) * b


def decode(sprite_id: int) -> tuple[int, int]:
    """0x4122A0 (and DS Exclusive Fish's decode_sprite): an id -> (table entry, cell)."""
    v = sprite_id - 10000
    g = _cdiv(v, 100)
    f = v - g * 100
    base = DS_SPRITE_BASE + 3 * (g - DS_FIRST) if is_ds(g) else 38 + 3 * g
    for low, part, minus in ((81, 2, 69), (71, 2, 65), (61, 2, 61), (51, 1, 39), (41, 1, 35), (31, 1, 31),
                             (21, 0, 9), (11, 0, 5)):
        if f >= low:
            return base + part, f - minus
    return base, f - 1


def head_on_x(body: int, fin: int, part: int, frame: int, anchor: int, c: int) -> int:
    """The turning fin's x before `+ body x + 44` (0x41492A / 0x4149A6: c - anchor); for a pair
    with a DS gene, DS Exclusive Fish's head_on_x."""
    if not (is_ds(body) or is_ds(fin)) or not _valid(body) or not _valid(fin) or frame < 0 or frame > 5 \
            or ds_data is None:
        return c - anchor
    k = frame + 1
    b0, bk = ds_data.EXTENT[body]["body"][0], ds_data.EXTENT[body]["body"][k]
    key = "top" if part == 0 else "bot"
    f0, fk = ds_data.EXTENT[fin][key][0], ds_data.EXTENT[fin][key][k]
    w0, wk = b0[1] - b0[0], bk[1] - bk[0]
    if w0 <= 0 or f0[1] == 0 or fk[1] == 0:
        return c - anchor
    num = (50 - anchor + f0[0] - b0[0]) * wk
    if frame < 3:
        x = bk[1] - _cdiv(num + _cdiv(w0, 2), w0) - fk[1]
    else:
        x = bk[0] + _cdiv(num + _cdiv(w0, 2), w0) - fk[0]
    return x - 0x2C


# ------------------------------------------------------------------ 0x4145F0: the fish draw

STAGE_ADULT, STAGE_TEEN, STAGE_BABY, STAGE_SEAHORSE = 0, 1, 2, 3
MODE_RIGHT, MODE_LEFT, MODE_TURN = 0, 1, 3
MODE_OFFSETS = {0: (10, 6), 1: (0, 0), 3: (20, 12), 4: (20, 12)}     # (body/fin id offset, baby cell offset)
COMPANION_CELL = {30: (74, 71), 31: (145, 63), 32: (234, 45)}        # ftfp_ds_store store_data.h
FIN_PUFFER, FIN_RAY, FIN_EEL = 30, 31, 32


@dataclass(frozen=True)
class Fish:
    """What the fish draw reads from a fish record."""
    body: int
    fin: int
    age: int = 30
    health: int = 100
    disease: int = 0
    alive: int = 1
    sprites: Sprites | None = None

    def sprite_fields(self) -> Sprites:
        return self.sprites or fish_sprites(self.body, self.fin)


def stage_of(fish: Fish) -> int | None:
    """0x415460: the view's stage (None: not drawn, age 0)."""
    if fish.age < 1:
        return None
    if fish.age < 6 and fish.health != 0:
        stage = STAGE_BABY
    elif fish.age < 20:
        stage = STAGE_TEEN
    else:
        stage = STAGE_ADULT
    if fish.body == SEAHORSE:
        stage = STAGE_SEAHORSE
    return stage


def view_height(stage: int, body_cell_height: int) -> int:
    """0x415460: the view's body height (+0x64): 32 a baby, 48 a teen, else the body cell's."""
    return {STAGE_BABY: 32, STAGE_TEEN: 48}.get(stage, body_cell_height)


def plan_fish(fish: Fish, mode: int, body_frame: int, fin_frame: int, stage: int, *, height: int = 50,
              x: int = 0, y: int = 0, puff: int = 0) -> list[Draw]:
    """0x4145F0(x, y, fish, mode, body frame, fin frame, stage), as Draw calls. `height` is
    the view's body height (view_height); `puff` the DS Puffer Fish's puff stage (0 none)."""
    s = fish.sprite_fields()
    health = fish.health
    out: list[Draw] = []
    if stage == STAGE_BABY and health <= 0:
        y2 = y - 7                     # a dead baby (0x41460F) is kept where the tank floor is
        x = min(max(x, 0x1F8), 0x25C) if y2 > 0x1A4 else min(x, 0x2BC)
    else:
        y2 = y + _cdiv(0x38 - height, 2)
    if mode not in MODE_OFFSETS:
        raise PictureError("That way of swimming is not one the game draws.")
    d, c = MODE_OFFSETS[mode]
    if stage == STAGE_BABY:
        if health <= 0:
            return [draw_cell(0x23, x, y2, _cmod(fish.age, 4))]
        return [draw_cell(0x22, x, y2, c + body_frame)]
    if stage == STAGE_TEEN:
        if health <= 0:
            return [draw_cell(0x23, x, y2, _cmod(fish.age, 4))]
        gene = _cdiv(s.body_id - 10000, 100)
        index, row = (DS_SPRITE_TEEN, gene - DS_FIRST) if is_ds(gene) else (0x24, gene)
        file, cols, rows = sheet(index)            # 0x408190(sprite, x, y, row, column, scale)
        return [Draw(file, cols, rows, row * cols + min(c + body_frame, cols - 1), x, y2,
                     scale=fish.age * 3 + 82)]
    if stage == STAGE_SEAHORSE:
        if not fish.alive:
            return []
        f = d + body_frame
        if f >= 21:
            f -= 9
        elif f >= 11:
            f -= 5
        if f < 0 or f > 17:
            f = 0
        index, xx, yy = 0x65, x, y2
        k = fish.fin - FIN_PUFFER
        if 0 <= k <= 2:                # DS Store Items' companion_sheet (0x414C8A)
            w, h = COMPANION_CELL[fish.fin]
            xx = min(max(x + 57 - w // 2, 0), 800 - w)
            yy = y2 + 30 - _cdiv(h, 2)
            index = SPR_SHEET + k
            if fish.fin == FIN_PUFFER and 0 <= f < 12 and puff:
                f = (4 if f >= 6 else 0) + puff
                index = SPR_PUFF
        return [draw_cell(index, xx, yy, f)]
    # an adult
    if not fish.alive:
        return []
    if health <= 0:
        if is_ds(fish.body):
            return [draw_cell(DS_SPRITE_DEAD, x, y2, fish.body - DS_FIRST)]
        return [draw_cell(0x25, x, y2, fish.body)]
    body_code = s.body_id + d + body_frame
    (tax, tay), (bax, bay) = s.top, s.bot
    if mode == MODE_RIGHT:
        out.append(_fin(s.top_id + d + fin_frame, x + tax, y + tay, s.alpha))
        out.append(_fin(s.bot_id + d + fin_frame, x + bax, y + bay, s.alpha))
    elif mode == MODE_LEFT:
        out.append(_fin(s.top_id + d + fin_frame, x - tax + 50, y + tay, s.alpha))
        out.append(_fin(s.bot_id + d + fin_frame, x - bax + 50, y + bay, s.alpha))
    else:
        cc = -13 if 1 <= body_frame <= 2 else 10 if 3 <= body_frame <= 5 else 0
        out.append(_fin(s.top_id + body_frame + 20, head_on_x(fish.body, fish.fin, 0, body_frame, tax, cc) + x + 0x2C,
                        y + tay, s.alpha))
        out.append(_fin(s.bot_id + body_frame + 20, head_on_x(fish.body, fish.fin, 1, body_frame, bax, cc) + x + 0x2C,
                        y + bay - 4, s.alpha))
    index, frame = decode(body_code)
    out.append(draw_cell(index, x, y2, frame))
    if mode in (MODE_RIGHT, MODE_LEFT) and fish.disease:
        odd = _cmod(fish.body, 2) * 25
        if mode == MODE_LEFT:
            if fish.disease == 1:
                spots = ((13, x - tax + 0x41, y + bay - 10), (13, x - tax + 0x3C, y + bay - 15),
                         (13, x - tax + 0x37, y + bay - 10))
            else:
                spots = ((14, x - odd - tax + 0x3E, y + bay - 0x14), (14, x - tax + 0x41, y + bay - 0x19),
                         (14, x - odd - tax + 0x37, y + bay - 0x12))
        else:
            if fish.disease == 1:
                spots = ((13, x + odd + bax + 10, y + bay - 0xB), (13, x + bax + 0xF, y + bay - 0xF),
                         (13, x + bax + 0x19, y + bay - 0xB))
            else:
                spots = ((14, x + bax + 0xC, y + bay - 0x14), (14, x + odd + bax + 0x10, y + bay - 0x19),
                         (14, x + bax + 0x1E, y + bay - 0x16))
        out += [draw_cell(i, sx, sy) for i, sx, sy in spots]
    return out


def _fin(code: int, x: int, y: int, alpha: int) -> Draw:
    index, frame = decode(code)
    return draw_cell(index, x, y, frame, alpha=alpha)


# ------------------------------------------------------------------ ornaments and the tank's things

ORNAMENTS = (               # store item 16-21 -> sprite (0x427BAE; ftfp_ornaments.c ORNAMENT_SPRITE)
    (177, "Shell Ornament"), (178, "Pagoda Ornament"), (179, "Diver Ornament"),
    (181, "Fancy Coral Ornament"), (180, "Sunken Antique Column"), (182, "Sunken Ship Ornament"),
)
ROCK_NAME = "Moray Eel's rock"
SHADOW = 3
SHADOW_W = 135
ROCK_H, ROCK_SINK = 132, 14
HOME_IDLE, HOME_ACTION = 13, 19

# Game-wide items (state + 0x118 + k x 0x14, the store's order) and the pictures the tank
# screen draws for them (0x41EE60, 0x41D340); the snail is drawn by 0x42201B.
EQUIPMENT = ((0x118, "Aeration System", 1), (0x12C, "Temperature Regulator", 2),
             (0x168, "Plant of Incubation from Isola", 5), (0x17C, "Plant of Nutrition from Isola", 6),
             (0x190, "Plant of Curing from Isola", 7), (0x1A4, "Plant of Fertility from Isola", 8))
SNAIL_FLAG = 0x140
SNAIL_VIEWS = ((16, "crawling left"), (19, "crawling right"), (15, "up the left glass"),
               (20, "down the left glass"), (18, "up the right glass"), (17, "down the right glass"))


def plan_ornament(sprite: int, *, x: int = 0, y: int = 0, h: int | None = None, falling: bool = False,
                  shadow: bool = True, image_h: int = 0, home_frame: int = 0) -> list[Draw]:
    """0x41D600 for one record: its shadow when it rests, then the ornament. The eel's rock
    (DS Store Items): its own shadow centred under it (rock_shadows), the eel's back layer
    when it is home, the rock, then the front layer (draw_home)."""
    h = image_h if h is None else h
    out = []
    if sprite in (SPR_ROCK, SPR_ROCK_HOME):
        w = 160
        if shadow and not falling:
            out.append(draw_cell(SHADOW, x + _cdiv(w, 2) - _cdiv(SHADOW_W, 2), y + h - 25))
        if sprite == SPR_ROCK_HOME:
            out.append(draw_cell(SPR_HOME_BACK, x, y, home_frame))
        out.append(draw_cell(sprite, x, y))
        if sprite == SPR_ROCK_HOME:
            out.append(draw_cell(SPR_HOME_FRONT, x, y, home_frame))
        return out
    if shadow and not falling:
        out.append(draw_cell(SHADOW, x - 25, y + h - 25))
    out.append(draw_cell(sprite, x, y))
    return out


# The Creatures tab: the Golden Seahorse, DS Store Items' animals (the Moray Eel out of its home,
# in its home, and its home alone), then the snail's six pictures.
CREATURE_OPTIONS = (
    Option("seahorse", "Golden Seahorse"),
    Option("puffer", "Magic Pufferfish", True), Option("puffer_puffed", "Magic Pufferfish, puffed up", True),
    Option("ray", "Blue-Spotted Stingray", True),
    Option("eel", "Moray Eel, out of its home (swimming)", True),
    Option("eel_home", "Moray Eel in its home", True),
    Option("eel_rock", "Moray Eel's home (its rock, the eel out)", True),
) + tuple(Option(f"snail{index}", f"Cleaning Snail, {words}") for index, words in SNAIL_VIEWS)
# draw_home's frames (ftfp_ds_store.c home_frame): 13 idle frames in the cave mouth, played forward then
# back, and the 19-frame snap (it ducks, peeks, lunges, snaps out in front of the rock and bites).
HOME_FRAME_OPTIONS = tuple(Option(k, f"Frame {k + 1} (idle in the cave mouth)") for k in range(HOME_IDLE)) + \
    tuple(Option(HOME_IDLE + k, f"Frame {HOME_IDLE + k + 1} (the snap, {k + 1} of {HOME_ACTION})")
          for k in range(HOME_ACTION))


# ------------------------------------------------------------------ names

def _names():
    import breeding_fish as bf
    return bf


def part_name(kind: str, gene: int) -> str:
    bf = _names()
    if not _valid(gene):
        return f"{kind} {gene}"
    return (bf.BODY_NAMES if kind == "body" else bf.FIN_NAMES)[bf.ds_index(gene)]


def species_name(body: int, fin: int) -> str:
    if _valid(body) and _valid(fin):
        return _names().species_name(body, fin)
    return f"Fish {body}/{fin}"


CREATURE_NAMES = {22: "Golden Seahorse", FIN_PUFFER: "Magic Pufferfish", FIN_RAY: "Blue-Spotted Stingray",
                  FIN_EEL: "Moray Eel"}


# ------------------------------------------------------------------ the save

SAVE_HEADER = 0x18                    # "ldwg", then the state from +8: state offset X is at X + 0x10
STATE_SIZE = 0x1E3C8
FISH_BASE, TANK_STRIDE, SLOT_STRIDE, RECORDS = 0x390, 0x51EC, 0x288, 31
ORN_BASE, ORN_STRIDE, ORN_SLOTS = 0x5208, 0x2C, 6
SIDECAR_FOLDER = "Fish Tycoon Fix Patcher Data"
ANIMAL_MARK = 0x41435446              # "FTCA" at +0x14
TANK_NAMES = ("Tank 1", "Tank 2", "Tank 3 (Sale Tank)", "Isolation Tank", "Tank 4", "Tank 5", "Tank 6")
EXTRA_MAGIC, EXTRA_BLOCKS = 0x54585446, 3       # "FTXT" (ftfp_extra_tanks.c)
TA_MAGIC, TA_RECORDS = 0x41545446, 15           # "FTTA" (ftfp_ds_store.c)
ORN_MAGIC, ORN_TANKS, ORN_COPIES = 0x524F5446, 8, 10   # "FTOR" (ftfp_ornaments.c)


def _crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def _fnv(data: bytes) -> int:
    h = 2166136261
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


def _i32(data: bytes, at: int) -> int:
    return struct.unpack_from("<i", data, at)[0]


@dataclass
class TankRead:
    name: str
    fish: list                     # (slot, record bytes)
    animals: list                  # (k, record bytes)
    ornaments: list                # record bytes


@dataclass
class SaveRead:
    tanks: list
    owned: dict                    # state offset -> owned
    notes: list


def _record_fish(rec: bytes) -> Fish:
    body, fin = _i32(rec, 0x4C), _i32(rec, 0x50)
    stored = Sprites(_i32(rec, 0x54), _i32(rec, 0x58), _i32(rec, 0x5C), _i32(rec, 0x60),
                     (_i32(rec, 0x68), _i32(rec, 0x6C)), (_i32(rec, 0x70), _i32(rec, 0x74)))
    fresh = fish_sprites(body, fin) if _valid(body) or body == SEAHORSE else None
    # The game draws from the record's own fields; DS Exclusive Fish refreshes a DS pair's
    # anchors on every load (refresh_anchors), so those are the current ones.
    sprites = stored
    if fresh is not None and (is_ds(body) or is_ds(fin)):
        sprites = replace(stored, top=fresh.top, bot=fresh.bot)
    if fresh is not None and (stored.body_id, stored.top_id, stored.bot_id) != (fresh.body_id, fresh.top_id, fresh.bot_id):
        sprites = fresh                                  # never set up: the game would set them up
    return Fish(body, fin, _i32(rec, 0x0C), _i32(rec, 0x3C), _i32(rec, 0x40), _i32(rec, 0), sprites)


def _is_animal(rec: bytes) -> bool:
    return _i32(rec, 0) != 0 and _i32(rec, 0x4C) == SEAHORSE and struct.unpack_from("<I", rec, 0x14)[0] == ANIMAL_MARK


def read_save(save_folder, slot: int) -> SaveRead:
    """Everything drawable in "Fish Tycoon<slot>.ldw" and its patcher files, read only."""
    folder = Path(save_folder)
    path = folder / f"Fish Tycoon{int(slot)}.ldw"
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PictureError(f"{path.name} could not be read ({exc.strerror or exc}).") from None
    if len(data) < SAVE_HEADER + STATE_SIZE or data[:4] != b"ldwg":
        raise PictureError(f"{path.name} is not a Fish Tycoon save.")
    state = lambda off: SAVE_HEADER - 8 + off            # noqa: E731
    notes: list[str] = []
    tanks = []
    for t in range(4):
        block = data[state(FISH_BASE + t * TANK_STRIDE):state(FISH_BASE + (t + 1) * TANK_STRIDE)]
        tanks.append(_read_block(TANK_NAMES[t], block, []))
    owned = {off: _i32(data, state(off)) != 0 for off, _n, _s in EQUIPMENT}
    owned[SNAIL_FLAG] = _i32(data, state(SNAIL_FLAG)) != 0
    sidecars = folder / SIDECAR_FOLDER
    # DS Store Items' animals of Tanks 1-3 ("Tank Animals <slot>.dat", ta_load's rules).
    fingerprint = tuple(struct.unpack_from("<I", data, state(off))[0] for off in (0x38C, 0x24, 0x3C, 0x44))
    animals = _read_tank_animals(sidecars, slot, fingerprint, notes)
    if animals is not None:
        for t in range(3):
            tanks[t].animals = [(k, rec) for k, rec in enumerate(animals[t]) if _is_animal(rec)]
    # 3 extra tanks ("Extra Tanks <slot>.dat").
    for e, (block, extra_animals) in enumerate(_read_extra_tanks(sidecars, slot, notes)):
        tanks.append(_read_block(TANK_NAMES[4 + e], block, extra_animals))
    # Multiple Ornaments' copies ("Ornaments <slot>.dat"): logical tanks 0-2, then 3-5 = Tanks 4-6.
    copies = _read_ornament_copies(sidecars, slot, notes)
    for logical, records in copies.items():
        target = logical if logical < 3 else logical + 1
        if target < len(tanks):
            tanks[target].ornaments += records
    return SaveRead(tanks, owned, notes)


def _read_block(name: str, block: bytes, animals: list) -> TankRead:
    fish = []
    for s in range(RECORDS):
        rec = block[s * SLOT_STRIDE:(s + 1) * SLOT_STRIDE]
        if len(rec) == SLOT_STRIDE and _i32(rec, 0) != 0:
            fish.append((s, rec))
    ornaments = []
    for k in range(ORN_SLOTS):
        at = ORN_BASE - FISH_BASE + k * ORN_STRIDE
        rec = block[at:at + ORN_STRIDE]
        if len(rec) == ORN_STRIDE and rec[0] != 0:
            ornaments.append(rec)
    return TankRead(name, fish, [(k, r) for k, r in animals if _is_animal(r)], ornaments)


def _read_tank_animals(folder: Path, slot: int, fingerprint: tuple, notes: list):
    size = 40 + TA_RECORDS * SLOT_STRIDE

    def read(path: Path):
        try:
            raw = path.read_bytes()
        except OSError:
            return 0, None
        h = struct.unpack_from("<10I", raw, 0) if len(raw) >= 40 else None
        if len(raw) != size or h[0] != TA_MAGIC or h[1] != 1 or h[2] != TA_RECORDS or h[3] != SLOT_STRIDE \
                or h[9] != _fnv(raw[40:]):
            return -1, None
        if tuple(h[4:8]) == fingerprint:
            return 1, raw
        later = h[6] <= fingerprint[2] and h[7] <= fingerprint[3] and (h[6] < fingerprint[2] or h[7] < fingerprint[3])
        return (2 if later else -2), raw

    a, raw_a = read(folder / f"Tank Animals {int(slot)}.dat")
    chosen = raw_a if a == 1 else None
    if chosen is None:
        b, raw_b = read(folder / f"Tank Animals {int(slot)}.previous.dat")
        chosen = raw_b if b == 1 else (raw_a if a == 2 else None)
    if chosen is None:
        if a < 0:
            notes.append("Its Tank Animals file is not this save's, so the game does not load it.")
        return None
    return [[chosen[40 + (t * 5 + k) * SLOT_STRIDE:40 + (t * 5 + k + 1) * SLOT_STRIDE] for k in range(5)]
            for t in range(3)]


def _read_extra_tanks(folder: Path, slot: int, notes: list) -> list:
    path = folder / f"Extra Tanks {int(slot)}.dat"
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    held = TANK_STRIDE + 5 * SLOT_STRIDE
    if len(raw) < 28:
        notes.append("Its Extra Tanks file could not be read.")
        return []
    h = struct.unpack_from("<7I", raw, 0)
    v4 = len(raw) == 28 + EXTRA_BLOCKS * held and h[1] == 4
    v3 = len(raw) == 28 + EXTRA_BLOCKS * TANK_STRIDE and h[1] == 3
    data_size = EXTRA_BLOCKS * (held if v4 else TANK_STRIDE)
    if not (v4 or v3) or h[0] != EXTRA_MAGIC or h[2] != EXTRA_BLOCKS or h[3] != TANK_STRIDE \
            or _crc32(raw[28:28 + data_size]) != h[4] or h[5] > EXTRA_BLOCKS or h[6] > 7:
        notes.append("Its Extra Tanks file could not be read, so the game does not load it.")
        return []
    out = []
    for e in range(min(h[5], EXTRA_BLOCKS)):            # only the tanks bought
        if v4:
            start = 28 + e * held
            block = raw[start:start + TANK_STRIDE]
            animals = [(k, raw[start + TANK_STRIDE + k * SLOT_STRIDE:start + TANK_STRIDE + (k + 1) * SLOT_STRIDE])
                       for k in range(5)]
        else:                                           # version 3: animals in records 26-30 (settle_v3_animals)
            start = 28 + e * TANK_STRIDE
            block = bytearray(raw[start:start + TANK_STRIDE])
            animals = []
            for s in range(26, RECORDS):
                rec = bytes(block[s * SLOT_STRIDE:(s + 1) * SLOT_STRIDE])
                if _is_animal(rec):
                    animals.append((len(animals), rec))
                    block[s * SLOT_STRIDE:(s + 1) * SLOT_STRIDE] = bytes(SLOT_STRIDE)
            block = bytes(block)
        out.append((block, animals))
    return out


def _read_ornament_copies(folder: Path, slot: int, notes: list) -> dict:
    path = folder / f"Ornaments {int(slot)}.dat"
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    size = 20 + 4 * ORN_TANKS + ORN_TANKS * ORN_COPIES * ORN_STRIDE
    if len(raw) != size:
        notes.append("Its Ornaments file could not be read.")
        return {}
    h = struct.unpack_from("<5I", raw, 0)
    counts = struct.unpack_from(f"<{ORN_TANKS}I", raw, 20)
    if h != (ORN_MAGIC, 1, ORN_TANKS, ORN_COPIES, ORN_STRIDE) or any(c > ORN_COPIES for c in counts):
        notes.append("Its Ornaments file could not be read.")
        return {}
    sprites = {s for s, _n in ORNAMENTS}
    out = {}
    for t in range(ORN_TANKS):
        records = []
        for k in range(counts[t]):
            at = 20 + 4 * ORN_TANKS + (t * ORN_COPIES + k) * ORN_STRIDE
            rec = raw[at:at + ORN_STRIDE]
            if rec[0] != 1 or _i32(rec, 0x24) not in sprites:
                notes.append("Its Ornaments file could not be read.")
                return {}
            records.append(rec)
        if records:
            out[t] = records
    return out


# ------------------------------------------------------------------ the renderer

FACINGS = (("left", "Facing left", MODE_LEFT), ("right", "Facing right", MODE_RIGHT),
           ("turn", "Turning", MODE_TURN))
FRAMES = tuple(Option(k, f"Frame {k + 1}") for k in range(6))
STATES = (("healthy", "Healthy"), ("ick", "Sick: ick"), ("fungus", "Sick: fungus"), ("dead", "Dead"))
MODE_OF = {key: mode for key, _l, mode in FACINGS}


def _stage_options() -> tuple:
    out = [Option("baby", "Baby, just hatched (age 1-5)")]
    out += [Option(f"teen{a}", f"Teen, age {a} ({a * 3 + 82}%)") for a in range(6, 20)]
    out.append(Option("adult", "Adult (age 20 and up)"))
    return tuple(out)


def required_files() -> list[str]:
    import pictures_fish_items as items
    names = []
    for index in list(STOCK_SHEETS) + list(range(38, 101)):
        names.append(sheet(index)[0])
    names += items.stock_files()
    return list(dict.fromkeys(names))


def patcher_files() -> list[str]:
    """The patcher's own art the pictures may use (DS Exclusive Fish, DS Store Items)."""
    names = [sheet(i)[0] for i in range(DS_SPRITE_BASE, DS_SPRITE_DEAD + 1)]
    names += [f for f, _c, _r in STORE_SHEETS.values()]
    import pictures_fish_items as items
    names += items.patcher_files()
    return list(dict.fromkeys(names))


def patcher_art() -> dict[str, Path]:
    assets = PATCHER_ROOT / "assets"
    out = {}
    for name in patcher_files():
        for folder in ("fish_tycoon_ds", "fish_tycoon_ds_store", "fish_tycoon_supply_slots"):
            path = assets / folder / "Images" / name
            if path.is_file():
                out[name] = path
                break
    return out


class _FolderSource:
    """A game folder read straight (no cache): Images, then Assets\\ft.dat."""

    def __init__(self, folder) -> None:
        import breeding_pictures as bp
        self.art = bp.ArtSource(folder)
        self.patcher = bp.PatcherArt(GAME, patcher_art())
        self.problem = self.art.problem

    def read(self, name: str):
        data = self.patcher.read(name)
        return data if data is not None else self.art.read(name)


def load(source) -> "FishRenderer":
    if isinstance(source, (str, os.PathLike)):
        source = _FolderSource(source)
    return FishRenderer(source)


class FishRenderer:
    game = GAME

    def __init__(self, source) -> None:
        self.source = source
        self.sheets = pi.Sheets(source)
        self.problem = getattr(source, "problem", "") or ""
        self._save_key = None
        self._save = None
        self._items: dict[str, tuple] = {}

    # ---- art
    def cell_height(self, index: int) -> int:
        file, cols, rows = sheet(index)
        image = self.sheets.image(file)
        return image.height // max(1, rows) if cols else image.height

    def image_height(self, index: int) -> int:
        return self.sheets.image(sheet(index)[0]).height

    def render_plan(self, plan) -> pi.Image:
        if not plan:
            raise PictureError("The game draws nothing for this.")
        return pi.render_plan(self.sheets, plan)

    # ---- fish
    def plan_for(self, fish: Fish, mode: int = MODE_LEFT, frame: int = 0, stage: int | None = None,
                 puff: int = 0) -> list[Draw]:
        stage = stage_of(fish) if stage is None else stage
        if stage is None:
            raise PictureError("The game does not draw a fish of age 0.")
        height = 50
        if stage in (STAGE_ADULT, STAGE_SEAHORSE):
            try:
                index, _f = decode(fish.sprite_fields().body_id)
                height = self.cell_height(index) if stage == STAGE_ADULT else 50
            except PictureError:
                height = 50
        else:
            height = view_height(stage, 50)
        return plan_fish(fish, mode, frame, frame, stage, height=height, puff=puff)

    # ---- the save
    def _read(self, save_folder, slot: int) -> SaveRead:
        path = Path(save_folder) / f"Fish Tycoon{int(slot)}.ldw"
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = None
        key = (str(save_folder), int(slot), stamp)
        if key != self._save_key:
            self._save = read_save(save_folder, slot)
            self._save_key = key
        return self._save

    def saved_items(self, save_folder, slot: int, spoilers: bool = False) -> list[SavedItem]:
        """Everything in the save; a fish under 20 unnamed unless `spoilers` (see _fish_label)."""
        save = self._read(save_folder, slot)
        items: list[SavedItem] = []
        self._items = {}

        def add(item_id, label, location, kind, detail, what):
            self._items[item_id] = what
            items.append(SavedItem(item_id, label, location, kind, detail))

        for t, tank in enumerate(save.tanks):
            for s, rec in tank.fish:
                fish = _record_fish(rec)
                stage = stage_of(fish)
                if stage is None:
                    continue
                if fish.body == SEAHORSE:
                    name = CREATURE_NAMES.get(fish.fin, "Golden Seahorse")
                    add(f"t{t}f{s}", name, tank.name, "creature", f"{name} in {tank.name}, place {s + 1}.",
                        ("fish", fish))
                    continue
                label, detail = self._fish_label(fish, stage, spoilers)
                add(f"t{t}f{s}", label, tank.name, "fish", f"{detail} {tank.name}, place {s + 1}.", ("fish", fish))
            for k, rec in tank.animals:
                fish = _record_fish(rec)
                name = CREATURE_NAMES.get(fish.fin, "Golden Seahorse")
                add(f"t{t}a{k}", name, tank.name, "creature", f"{name} in {tank.name} (DS Store Items).",
                    ("fish", fish))
            for k, rec in enumerate(tank.ornaments):
                sprite = _i32(rec, 0x24)
                name = dict(ORNAMENTS).get(sprite)
                if name is None and sprite in (SPR_ROCK, SPR_ROCK_HOME):
                    name = ROCK_NAME + (" (the eel is home)" if sprite == SPR_ROCK_HOME else "")
                if name is None:
                    continue
                add(f"t{t}o{k}", name, tank.name, "decoration", f"{name} in {tank.name}.",
                    ("ornament", sprite, _i32(rec, 0x1C), _i32(rec, 0x10) != 0))
        everywhere = "Every tank"
        if save.owned.get(SNAIL_FLAG):
            add("snail", "Cleaning Snail", everywhere, "creature", "The Cleaning Snail, in every tank.", ("snail", 16))
        for off, name, sprite in EQUIPMENT:
            if save.owned.get(off):
                add(f"e{off:x}", name, everywhere, "decoration", f"{name}, in every tank.", ("image", sprite))
        return items

    @staticmethod
    def _fish_label(fish: Fish, stage: int, spoilers: bool = False) -> tuple[str, str]:
        """The fish's line. The game names a fish only from age 20 (its info panel, 0x41D9ED);
        a younger one is "Baby fish" / "Teen fish" unless Show Spoilers is on."""
        words = {STAGE_BABY: "baby", STAGE_TEEN: "teen", STAGE_ADULT: "adult"}[stage]
        state = ""
        if fish.health <= 0:
            state = ", dead"
        elif fish.disease == 1:
            state = ", sick (ick)"
        elif fish.disease:
            state = ", sick (fungus)"
        if fish.age < 20 and not spoilers:
            name = f"{words.capitalize()} fish"
            return f"{name} (age {fish.age}{state})", f"{name}: age {fish.age}, health {fish.health}{state}."
        name = species_name(fish.body, fish.fin)
        label = f"{name} ({words}, age {fish.age}{state})"
        return label, f"{name}: {words}, age {fish.age}, health {fish.health}{state}."

    def render_saved(self, save_folder, slot: int, item_id: str, facing: str = "left", frame: int = 0) -> pi.Image:
        return self.render_plan(self.plan_saved(save_folder, slot, item_id, facing, frame))

    def plan_saved(self, save_folder, slot: int, item_id: str, facing: str = "left", frame: int = 0) -> list[Draw]:
        if item_id not in self._items or self._save_key is None or self._save_key[:2] != (str(save_folder), int(slot)):
            self.saved_items(save_folder, slot)
        what = self._items.get(item_id)
        if what is None:
            raise PictureError("That is no longer in the save.")
        return self._plan_what(what, MODE_OF.get(facing, MODE_LEFT), frame)

    def _plan_what(self, what, mode: int, frame: int) -> list[Draw]:
        kind = what[0]
        if kind == "fish":
            return self.plan_for(what[1], mode, frame)
        if kind == "ornament":
            _k, sprite, h, falling = what
            return plan_ornament(sprite, h=h, falling=falling, image_h=self.image_height(sprite))
        if kind == "snail":
            return [draw_cell(what[1], 0, 0)]
        return [draw_cell(what[1], 0, 0)]

    # ---- make your own
    def custom_choices(self, extras, spoilers: bool, discovered) -> list[Subject]:
        """The patcher's own parts and creatures (DS Exclusive Fish's bodies and fins, DS Store
        Items' animals and the eel's rock) are always offered, marked "(patcher)": their art
        ships with the patcher (patcher_art), so they draw whatever the save's settings are.
        `extras` is kept for the window's call. With Show Spoilers off only the parts the
        save has discovered are offered; with no save (`discovered` None) nothing is hidden."""
        genes = list(range(0, PC_LAST + 1)) + list(range(DS_FIRST, DS_LAST + 1))
        hide = not spoilers and discovered is not None
        known_bodies = {b for b, _f in (discovered or ())}
        known_fins = {f for _b, f in (discovered or ())}
        bodies = tuple(Option(g, part_name("body", g), is_ds(g)) for g in genes if not hide or g in known_bodies)
        fins = tuple(Option(g, part_name("fin", g), is_ds(g)) for g in genes if not hide or g in known_fins)
        facing = Field("facing", "Facing", tuple(Option(k, label) for k, label, _m in FACINGS), "left")
        frame = Field("frame", "Frame", FRAMES, 0)
        fish = Subject("fish", "Fish", (
            Field("fin", "Fin", fins, fins[0].key if fins else None),
            Field("body", "Body", bodies, bodies[0].key if bodies else None),
            Field("stage", "Stage", _stage_options(), "adult"),
            Field("state", "State", tuple(Option(k, label) for k, label in STATES), "healthy"),
            facing, frame),
            note="Ages follow the game: under 6 a baby, under 20 a teen (it grows from 100% at age 6 to 139% "
                 "at 19), then an adult. Sick spots show on adults facing left or right, as in the game."
                 + ("" if spoilers else " Show Spoilers is off: only the bodies and fins you have discovered."))
        creature = Subject("creature", "Creatures", (
            Field("creature", "Creature", CREATURE_OPTIONS, "seahorse"), facing, frame,
            Field("home_frame", "Eel at home: frame", HOME_FRAME_OPTIONS, 0)),
            note="Facing and Frame are for the swimmers (the Moray Eel out of its home too); the snail has one "
                 "picture for each way it crawls. The Moray Eel in its home is its rock with the eel's back and "
                 "front layers, as DS Store Items draws it (Eel at home: frame); its home alone is the rock "
                 "with no eel, as the tank shows it while the eel is out.")
        decorations = [Option(f"orn{sprite}", name) for sprite, name in ORNAMENTS]
        decorations += [Option(f"img{sprite}", name) for _off, name, sprite in EQUIPMENT]
        decoration = Subject("decoration", "Decorations", (
            Field("decoration", "Decoration", tuple(decorations), decorations[0].key),
            Field("shadow", "Shadow", (Option(True, "With its shadow in the gravel"), Option(False, "No shadow")), True)),
            note="Ornaments rest on a shadow in the gravel, as in the tank; plants and equipment are drawn as the "
                 "tank shows them. The Moray Eel's rock is on the Creatures tab.")
        eggs = Subject("eggs", "Eggs", (
            Field("egg_frame", "Frame", tuple(Option(k, f"Frame {k + 1}") for k in range(EGG_FRAMES)), 0),),
            note="Eggs dropped into a tank, as the game's tank effect draws them (16 pictures as they fall "
                 "and spread, see-through as in the game). The game draws nothing else for an egg: a fish "
                 "is not drawn before it hatches (age 0), then it is a baby (the Fish tab's Baby stage).")
        import pictures_game_art as ga
        return [fish, creature, decoration, eggs, self._items_subject(), ga.subject(self.game_art())]


    # ---- All game art (pictures_game_art): read straight from the game copy the window found
    art_copy = None

    def game_art(self):
        import pictures_game_art as ga
        if getattr(self, "_art", None) is None or self._art_for != self.art_copy:
            self._art = ga.GameArt(self.game, self.art_copy)
            self._art_for = self.art_copy
        return self._art

    # ---- items (pictures_fish_items)
    def _items_subject(self) -> Subject:
        fields = self._item_fields({})
        return Subject("items", "Items", (
            Field("category", "Category", fields["category"], fields["category"][0].key),
            Field("item", "Item", fields["item"], fields["item"][0].key),
            Field("view", "Picture", fields["view"], fields["view"][0].key)),
            note="Every item of the game, owned or not, as the game draws it: in the supply store (at rest on its "
                 "shadow, pointed at, and picked, when the store makes it pulse), in its supply slot, on the mouse "
                 "and in the tank. (patcher): an item a patcher setting adds; (unused): art in the game's files "
                 "that the game never draws, shown whole.")

    @staticmethod
    def _item_fields(spec: dict) -> dict:
        import pictures_fish_items as fi
        categories = tuple(Option(c, c) for c in fi.CATEGORIES)
        category = spec.get("category") if spec.get("category") in fi.CATEGORIES else fi.CATEGORIES[0]
        in_category = [i for i in fi.ITEMS if i.category == category]
        items = tuple(Option(i.key, i.name, i.patcher, i.unused) for i in in_category)
        chosen = fi.BY_KEY.get(spec.get("item"))
        if chosen is None or chosen.category != category:
            chosen = in_category[0]
        views = tuple(Option(k, label) for k, label in fi.views(chosen))
        return {"category": categories, "item": items, "view": views}

    def refine_choices(self, subject: str, spec: dict) -> dict:
        """The options that follow the others' picks (Items: the category's items, the item's pictures;
        All game art: the category's files, the file's frames)."""
        if subject == "art":
            import pictures_game_art as ga
            fields = ga.fields(self.game_art(), spec)
            return {"sheet": fields["sheet"], "frame": fields["frame"]}
        if subject != "items":
            return {}
        fields = self._item_fields(spec)
        return {"item": fields["item"], "view": fields["view"]}

    def custom_name(self, spec: dict) -> str | None:
        """A picture's file name from only the choices that change it (a creature's), else None
        (the window joins every choice)."""
        if spec.get("subject") != "creature":
            return None
        option = next((o for o in CREATURE_OPTIONS if o.key == spec.get("creature")), None)
        if option is None:
            return None
        name = option.label + (" (patcher)" if option.patcher else "")
        key = str(option.key)
        if key.startswith("snail") or key == "eel_rock":
            return name
        if key == "eel_home":
            frame = next((o.label for o in HOME_FRAME_OPTIONS if o.key == spec.get("home_frame")), "")
            return f"{name} - {frame}"
        facing = next((label for k, label, _m in FACINGS if k == spec.get("facing")), "Facing left")
        return f"{name} - {facing} - Frame {int(spec.get('frame') or 0) + 1}"

    def custom_batch(self, subject: str):
        """Every picture of a "Make your own" tab, for its "Save all on this tab...": a list of
        (sub-folder names, file name, spec), or None for the Fish tab (every body, fin, stage, state,
        facing and frame would be over a hundred thousand pictures)."""
        out = []
        if subject == "art":
            import pictures_game_art as ga
            return ga.batch(self.game_art())
        if subject == "items":
            import pictures_fish_items as fi
            for item in fi.ITEMS:
                mark = " (patcher)" if item.patcher else " (unused)" if item.unused else ""
                for key, label in fi.views(item):
                    out.append(((item.category,), f"{item.name}{mark} - {label}",
                                {"subject": "items", "category": item.category, "item": item.key, "view": key}))
            return out
        if subject == "creature":
            for option in CREATURE_OPTIONS:
                key, name = option.key, option.label + (" (patcher)" if option.patcher else "")
                if str(key).startswith("snail") or key == "eel_rock":
                    out.append(((), name, {"subject": "creature", "creature": key}))
                elif key == "eel_home":
                    out += [((name,), f"{name} - {o.label}", {"subject": "creature", "creature": key, "home_frame": o.key})
                            for o in HOME_FRAME_OPTIONS]
                else:
                    out += [((name,), f"{name} - {label} - Frame {k + 1}",
                             {"subject": "creature", "creature": key, "facing": facing, "frame": k})
                            for facing, label, _m in FACINGS for k in range(6)]
            return out
        if subject == "decoration":
            for sprite, name in ORNAMENTS:
                out += [((), name, {"subject": "decoration", "decoration": f"orn{sprite}", "shadow": True}),
                        ((), f"{name} - no shadow", {"subject": "decoration", "decoration": f"orn{sprite}", "shadow": False})]
            out += [((), name, {"subject": "decoration", "decoration": f"img{sprite}"}) for _o, name, sprite in EQUIPMENT]
            return out
        if subject == "eggs":
            return [((), f"Eggs - Frame {k + 1}", {"subject": "eggs", "egg_frame": k}) for k in range(EGG_FRAMES)]
        return None

    def plan_custom(self, spec: dict) -> list[Draw]:
        subject = spec.get("subject")
        mode = MODE_OF.get(spec.get("facing", "left"), MODE_LEFT)
        frame = int(spec.get("frame", 0) or 0)
        if subject == "fish":
            body, fin = spec.get("body"), spec.get("fin")
            if body is None or fin is None:
                raise PictureError("Pick a body and a fin.")
            stage_key = spec.get("stage", "adult")
            state = spec.get("state", "healthy")
            if stage_key == "baby":
                age, stage = 3, STAGE_BABY
            elif str(stage_key).startswith("teen"):
                age, stage = int(str(stage_key)[4:]), STAGE_TEEN
            else:
                age, stage = 30, STAGE_ADULT
            fish = Fish(int(body), int(fin), age, 0 if state == "dead" else 100,
                        {"ick": 1, "fungus": 2}.get(state, 0))
            if stage == STAGE_BABY and state == "dead":
                stage = STAGE_TEEN                     # 0x4156EF: a dead fish under 6 is in the teen stage
            return self.plan_for(fish, mode, frame, stage)
        if subject == "creature":
            key = spec.get("creature", "seahorse")
            if str(key).startswith("snail"):
                return [draw_cell(int(str(key)[5:]), 0, 0)]
            if key in ("eel_home", "eel_rock"):
                home = int(spec.get("home_frame", 0) or 0)
                if not 0 <= home < HOME_IDLE + HOME_ACTION:
                    raise PictureError("The eel's home has no such frame.")
                return plan_ornament(SPR_ROCK_HOME if key == "eel_home" else SPR_ROCK, h=ROCK_H - ROCK_SINK,
                                     home_frame=home)
            fin = {"seahorse": 22, "puffer": FIN_PUFFER, "puffer_puffed": FIN_PUFFER, "ray": FIN_RAY,
                   "eel": FIN_EEL}.get(key)
            if fin is None:
                raise PictureError("Pick a creature.")
            fish = Fish(SEAHORSE, fin, 21)
            return self.plan_for(fish, mode, frame, STAGE_SEAHORSE, puff=3 if key == "puffer_puffed" else 0)
        if subject == "decoration":
            key = str(spec.get("decoration", ""))
            shadow = bool(spec.get("shadow", True))
            if key.startswith("orn"):
                sprite = int(key[3:])
                return plan_ornament(sprite, shadow=shadow, image_h=self.image_height(sprite))
            if key in ("rock", "rock_home"):
                sprite = SPR_ROCK_HOME if key == "rock_home" else SPR_ROCK
                return plan_ornament(sprite, h=ROCK_H - ROCK_SINK, shadow=shadow,
                                     home_frame=int(spec.get("home_frame", 0) or 0))
            if key.startswith("img"):
                return [draw_cell(int(key[3:]), 0, 0)]
            raise PictureError("Pick a decoration.")
        if subject == "items":
            import pictures_fish_items as fi
            item = fi.BY_KEY.get(spec.get("item"))
            if item is None:
                raise PictureError("Pick an item.")
            return fi.plan(item, spec.get("view", "store"), self.image_height)
        if subject == "eggs":
            return plan_eggs(int(spec.get("egg_frame", 0) or 0))
        raise PictureError("Pick what to draw.")

    def render_custom(self, spec: dict) -> pi.Image:
        if spec.get("subject") == "art":
            import pictures_game_art as ga
            return ga.render(self.game_art(), spec)
        return self.render_plan(self.plan_custom(spec))
