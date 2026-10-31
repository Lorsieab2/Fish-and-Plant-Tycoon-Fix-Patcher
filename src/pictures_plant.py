"""Picture Studio's Plant Tycoon renderer (docs/picture-studio-interface.md).

Every plant is drawn by a port of the game's own draw code, from the pot record the game keeps
(0x5600 bytes: the save's pots, or Extra Greenhouses' sidecar):

* the pot (0x42F740): pot.png (sprite 0x38) frame = the pot's style (+0x18) at (x - 28, y - 15),
  soil.png (0x37) at (x - 25, y - 12), then the plant at (x, y);
* the plant (vtable slot 7, 0x42E4A0, the same for every class): scale 1.0, or 0.85 when dead
  (health +0x24 = 0); the class's root draw (slot 10) starts the branch draw (slot 13, 0x42E690)
  at branch 0 with the class's shape table and the plant's age (+0x10);
* a branch (0x42E690): drawn when its type is 1 (alive) or 4 (dead) and its age t = age - born
  (born relative to its parent) is at least 1; it grows to full size over 18 units
  (f = G + t / 18 x (1 - G), G the class's starting fraction, slot 19), the root never past the
  plant's size (+0x80 / 100); its part (0x42CFE0) is the part's box in its sheet, its pivot on
  (x, y), scaled about the box's centre (whole percent), the dead sheet for a dead branch or plant;
  children hang from the part's joints, flowers from its flower spots, each offset scaled the same
  way (trunc(offset x scale + 0.5));
* a flower (0x42D9C0): drawn from age 21 when the plant is alive: a bud (art record 0) growing
  from 50% at 21 to 100% at 24, then the flower (frame = its art's first cell + the flower's view
  0-2) from 50% at 24 to 100% at 28, capped by the plant's bloom (+0x8C) / 100, full size from 28.

Sprites are composited with the game's own scaler (0x404610): a box average when shrinking, the
nearest pixel when enlarging, as straight RGBA (the game blends each onto its opaque screen with
(c x a + d x (255 - a) + 127) >> 8; on a transparent canvas that is "over").

Plants of your own ("Make your own") start from a shape the class's constructor makes (the
STARTING_SHAPES of pictures_plant_data, "Shape 1" ... "Shape 12"), and grow by the game's rules:
the one-time age-7 roll that kills 10% of the leaf branches (0x42DEC0), the first flowering
(the update's flower counts, 0x42E375..0x42E45A, added by 0x42ED60 / 0x42EBC0), more flowers
(0x42ED60(360, 0): every spot), and the Radioactive Plant Formula (Store Upgrades and Items.dll's
apply_formula). Nothing here needs Unicorn, Pillow or game art: the pictures are cut from the
player's own game copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import random
import struct

import pictures_plant_data as D
from picture_image import (Draw, Field, Image, Option, PictureError, SavedItem, Sheets, Subject,
                           decode_png)

GAME = "plant"

# ------------------------------------------------------------------ the game's numbers

POT_SPRITE, SOIL_SPRITE, TAG_SPRITE = 0x38, 0x37, 0x36
POT_DX, POT_DY, SOIL_DX, SOIL_DY = -28, -15, -25, -12          # 0x42F795 / 0x42F7C2
DEAD_SCALE = 0.85                    # 0x4694F4, the dead plant's draw scale (0x42E4B8)
GROW_UNITS = 18.0                    # vtable slot 6, 0x42CD90: a branch grows over 18 units
AGE_BUDS, AGE_FLOWERS, AGE_FULL = 21.0, 24.0, 28.0      # 0x4691D8, 0x4677E8, 0x469598
FIRST_GROWTH = D.GROWTH_START        # foliage -> slot 19's starting fraction
RECORD_SIZE = 0x5600
BRANCHES_AT, BRANCH_SIZE, BRANCH_MAX = 0xA8, 0x16C, 60
FLOWER_SIZE = 0x1C
SIZE_DEFAULT, SIZE_MAX = 80, 110     # base constructor 0x42CA50; plant food cap 0x42D5FA
BLOOM_FULL = 100                     # +0x8C on the first flowering (0x42EDCD): 100, or 70

SAVE_HEADER, SAVE_BODY = 0x18, 0x53FB0
POTS_AT = 0x2188                     # state + 0x2188 + k x 0x5600 (k = row x 5 + column)
POTS = 15
SIDECAR_MAGIC, SIDECAR_VERSION, SIDECAR_WORDS = 0x47585450, 1, 7
EXTRA_GREENHOUSES = 5
SOIL_UPGRADES = ((0x82C, 2), (0x78C, 1))      # 0x41DDE0: the soil upgrade owned (state offsets)
GREENHOUSE_PLACES = [(323 + 93 * c, 117 + 144 * r) for r in range(3) for c in range(5)]   # 0x42FDE0


def f32(value: float) -> float:
    """A value stored to a 32-bit float, as the game's fstp dword does."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def ftol(value: float) -> int:
    """The CRT's _ftol2 (0x44F260): truncation toward zero."""
    return int(math.trunc(value))


def half(n: int) -> int:
    """C's n / 2 (cdq; sub; sar): toward zero."""
    return int(n / 2) if n < 0 else n // 2


# The shape tables: one part definition per row, 61 ints (0xF4 bytes).
@dataclass(frozen=True)
class Part:
    id: int
    kind: int                        # +0x04: 1 a leaf (the age-7 roll can kill it)
    sheet: int                       # +0x08
    mask: int                        # +0x0C
    dead: int                        # +0x10
    box: tuple                       # +0x14..+0x20: x, y, w, h in the sheet
    pivot: tuple                     # +0x24, +0x28
    joint_count: int                 # +0x2C
    joints: tuple                    # +0x30 + j x 12: (x, y, flags), room for 10
    spot_count: int                  # +0xA8
    spots: tuple                     # +0xAC + i x 12: (x, y, flags), room for 6

    @classmethod
    def from_ints(cls, v: tuple) -> "Part":
        joints = tuple(tuple(v[12 + 3 * j:15 + 3 * j]) for j in range(10))
        spots = tuple(tuple(v[43 + 3 * i:46 + 3 * i]) for i in range(6))
        return cls(v[0], v[1], v[2], v[3], v[4], tuple(v[5:9]), (v[9], v[10]), v[11], joints, v[42], spots)

    def with_spot(self, index: int, spot: tuple) -> "Part":
        spots = list(self.spots)
        spots[index] = spot
        return Part(self.id, self.kind, self.sheet, self.mask, self.dead, self.box, self.pivot, self.joint_count,
                    self.joints, self.spot_count, tuple(spots))

    @property
    def rect(self) -> tuple:
        x, y, w, h = self.box
        return (x, y, x + w, y + h)


SHAPES = {f: tuple(Part.from_ints(p) for p in parts) for f, parts in D.SHAPE_TABLES.items()}


def formula_shapes() -> dict:
    """The shape tables as Store Upgrades and Items.dll leaves them (prepare_shapes): every empty
    spot past a part's own gets its FORMULA_SPOTS place."""
    out = {f: list(parts) for f, parts in SHAPES.items()}
    for foliage, d, s, x, y in D.FORMULA_SPOTS:
        part = out[foliage][d]
        if part.spots[s] == (0, 0, 0):
            out[foliage][d] = part.with_spot(s, (x, y, 0))
    return {f: tuple(p) for f, p in out.items()}


FORMULA_SHAPES = formula_shapes()


def find_part(parts: tuple, part_id: int):
    """0x42CF60: the first definition with this id."""
    for part in parts:
        if part.id == part_id:
            return part
    return None


def sprite(sheet: int) -> tuple:
    try:
        return D.SPRITES[sheet]
    except KeyError:
        raise PictureError(f"The game has no picture number {sheet:#x}.") from None


# ------------------------------------------------------------------ a draw call

@dataclass(frozen=True)
class PlantDraw(Draw):
    """A Draw with the game's source rectangle and whole-percent scale: what 0x404610 gets (the
    rectangle (x0, y0, x1, y1) of the sheet, the top-left (x, y) after the game's centring, the
    scale in percent)."""
    rect: tuple | None = None
    scale: int = 100


# ------------------------------------------------------------------ the pot record

@dataclass
class Flower:
    spot: int
    view: int                        # +0x04: Random(3), added to the art's first cell
    growth: float = 1.0              # +0x08
    state: int = 1                   # +0x18: 1 on the plant (3 falling)


@dataclass
class Branch:
    part: int
    kind: int                        # 1 alive, 2 hidden, 3 cut, 4 dead
    born: float
    children: list = field(default_factory=list)      # (joint, child branch)
    flowers: list = field(default_factory=list)


@dataclass
class Plant:
    foliage: int
    flower: int
    age: float
    size: int = SIZE_DEFAULT
    health: int = 100
    bloom: int = 0
    pot: int = 0
    soil: int = 1
    water: int = 0
    for_sale: bool = False
    branches: list = field(default_factory=list)
    formula: bool = False            # the Radioactive Plant Formula's spots (patched games)

    @classmethod
    def from_record(cls, data: bytes) -> "Plant":
        if len(data) < RECORD_SIZE:
            raise PictureError("A plant record is cut short.")
        i = lambda at: struct.unpack_from("<i", data, at)[0]
        plant = cls(foliage=i(0x4C), flower=i(0x50), age=struct.unpack_from("<f", data, 0x10)[0], size=i(0x80),
                    health=i(0x24), bloom=i(0x8C), pot=i(0x18), soil=i(0x1C), water=i(0x20),
                    for_sale=bool(data[0x9D]))
        for k in range(BRANCH_MAX):
            at = BRANCHES_AT + k * BRANCH_SIZE
            kind = i(at + 4)
            if kind == 0:
                break
            children = [(i(at + 0x20 + j * 0x10), i(at + 0x24 + j * 0x10)) for j in range(max(0, min(i(at + 0x1C), 9)))]
            flowers = []
            for n in range(max(0, min(i(at + 0xC0), 6))):
                f = at + 0xC4 + n * FLOWER_SIZE
                flowers.append(Flower(i(f), i(f + 4), struct.unpack_from("<f", data, f + 8)[0], i(f + 0x18)))
            plant.branches.append(Branch(i(at), kind, struct.unpack_from("<f", data, at + 8)[0], children, flowers))
        plant.formula = plant.on_formula_spots()
        return plant

    def on_formula_spots(self) -> bool:
        """Whether a flower sits on a spot only the Radioactive Plant Formula's tables have (a
        spot that is empty in the stock table but filled by Store Upgrades and Items.dll's
        prepare_shapes). The stock game never puts a flower there (0x42DC60 picks from the
        part's own spots), so such a plant grew in a game with the DLL, which fills those spots
        at start-up for every plant it draws; drawn with the stock tables, those flowers would
        land at the sheet's (0, 0), far from the plant."""
        if self.foliage <= 0:
            return False
        foliage = (self.foliage - 1) % 23 + 1
        stock, formula = SHAPES.get(foliage, ()), FORMULA_SHAPES.get(foliage, ())
        for b in self.branches:
            part, patched = find_part(stock, b.part), find_part(formula, b.part)
            if part is None or patched is None:
                continue
            for fl in b.flowers:
                if 0 <= fl.spot < 6 and part.spots[fl.spot] == (0, 0, 0) and patched.spots[fl.spot] != (0, 0, 0):
                    return True
        return False

    def to_record(self, base: bytes | None = None) -> bytes:
        """The pot record (for the tests' emulated game): these fields over `base` (zeros)."""
        data = bytearray(base or bytes(RECORD_SIZE))
        for at, value in ((0x4C, self.foliage), (0x50, self.flower), (0x80, self.size), (0x24, self.health),
                          (0x8C, self.bloom), (0x18, self.pot), (0x1C, self.soil), (0x20, self.water)):
            struct.pack_into("<i", data, at, value)
        struct.pack_into("<f", data, 0x10, self.age)
        struct.pack_into("<f", data, 0x0C, self.age)
        data[0x38] = 1 if self.foliage else 0
        data[0x9D] = 1 if self.for_sale else 0
        data[BRANCHES_AT:BRANCHES_AT + BRANCH_MAX * BRANCH_SIZE] = bytes(BRANCH_MAX * BRANCH_SIZE)
        for k, b in enumerate(self.branches[:BRANCH_MAX]):
            at = BRANCHES_AT + k * BRANCH_SIZE
            struct.pack_into("<iif", data, at, b.part, b.kind, b.born)
            struct.pack_into("<i", data, at + 0x1C, len(b.children))
            for j, (joint, child) in enumerate(b.children):
                struct.pack_into("<ii", data, at + 0x20 + j * 0x10, joint, child)
            struct.pack_into("<i", data, at + 0xC0, len(b.flowers))
            for n, fl in enumerate(b.flowers):
                f = at + 0xC4 + n * FLOWER_SIZE
                struct.pack_into("<iif", data, f, fl.spot, fl.view, fl.growth)
                struct.pack_into("<i", data, f + 0x18, fl.state)
        return bytes(data)


# ------------------------------------------------------------------ the draw (a port)

class Planner:
    """Builds the game's draw calls for one plant; `cells` gives a sheet's cell size."""

    def __init__(self, cells) -> None:
        self.cells = cells                    # (file, cols, rows) -> (cell w, cell h)

    def plan(self, plant: Plant, x: int, y: int, *, pot: bool = True, soil_level: int = 0) -> list:
        out: list = []
        if pot:
            name, cols, rows = sprite(POT_SPRITE)
            out.append(self._cell(POT_SPRITE, plant.pot, x + POT_DX, y + POT_DY))
            if plant.soil:
                frame = soil_level * 4 + (2 if plant.water > 500 else 0) + (1 if plant.foliage else 0)
                out.append(self._cell(SOIL_SPRITE, frame, x + SOIL_DX, y + SOIL_DY))
        if plant.foliage > 0 and plant.branches:
            foliage = (plant.foliage - 1) % 23 + 1
            parts = (FORMULA_SHAPES if plant.formula else SHAPES)[foliage]
            scale = f32(1.0 if plant.health != 0 else DEAD_SCALE)
            self._branch(plant, parts, foliage, 0, x, y, scale, f32(plant.age), out)
        return out

    # 0x4208F0 / 0x409130: a whole cell of a sheet, unscaled
    def _cell(self, sheet: int, frame: int, x: int, y: int) -> PlantDraw:
        name, cols, rows = sprite(sheet)
        cw, ch = self.cells((name, cols, rows))
        col, row = frame % cols, frame // cols
        col, row = min(col, cols - 1), min(row, rows - 1)
        return PlantDraw(name, cols, rows, row * cols + col, x, y, rect=(col * cw, row * ch, col * cw + cw, row * ch + ch))

    # 0x42E690
    def _branch(self, plant, parts, foliage, idx, x, y, scale, age, out) -> None:
        if not 0 <= idx < len(plant.branches):
            return
        b = plant.branches[idx]
        if b.kind not in (1, 4):
            return
        part = find_part(parts, b.part)
        if part is None:
            return
        t = f32(age - b.born)
        if 1.0 > t:
            return
        g = FIRST_GROWTH.get(foliage, 0.0)
        if GROW_UNITS > t:
            one = f32(1.0 - g)
            factor = g + (t / GROW_UNITS) * one
        else:
            factor = 1.0
        factor = f32(factor)
        if idx == 0:
            limit = f32(plant.size / 100.0)
            if limit < factor:
                factor = limit
        scale = f32(factor * scale)
        dead = plant.health <= 0 or b.kind == 4
        self._part(part, x, y, scale, dead, out)
        for joint, child in b.children:
            jx, jy = part.joints[joint][:2] if 0 <= joint < 10 else (0, 0)
            dx, dy = self._offset(part, jx, jy, scale)
            self._branch(plant, parts, foliage, child, x + dx, y + dy, scale, t, out)
        if plant.health == 0:
            return
        s = scale
        for fl in b.flowers:
            if fl.growth != 0:
                s = f32(s * fl.growth)
            sx, sy = part.spots[fl.spot][:2] if 0 <= fl.spot < 6 else (0, 0)
            dx, dy = self._offset(part, sx, sy, s)
            if fl.state == 1:
                self._flower(plant, x + dx, y + dy, fl.view, s, out)

    @staticmethod
    def _offset(part: Part, px: int, py: int, scale: float) -> tuple:
        """A joint's or spot's offset from the pivot (0x42E897..0x42E941)."""
        x0, y0, w, h = part.box
        pivx, pivy = part.pivot
        if scale == 1.0:
            return px - pivx, py - pivy
        hh, hw = half(h), half(w)
        a = ftol((pivy - y0 - hh) * scale + 0.5) + hh
        b = ftol((pivx - x0 - hw) * scale + 0.5) + hw
        c = ftol((py - y0 - hh) * scale + 0.5) + hh
        d = ftol((px - x0 - hw) * scale + 0.5) + hw
        return d - b, c - a

    # 0x42CFE0
    def _part(self, part: Part, x: int, y: int, scale: float, dead: bool, out) -> None:
        if part.sheet == 0:
            return
        sheet = part.dead if dead and part.dead else part.sheet
        name, cols, rows = sprite(sheet)
        x0, y0, w, h = part.box
        rect = (x0, y0, x0 + w, y0 + h)
        pivx, pivy = part.pivot[0] - x0, part.pivot[1] - y0
        if scale == 1.0:
            out.append(PlantDraw(name, 1, 1, 0, x - pivx, y - pivy, rect=rect))
            return
        hh, hw = half(h), half(w)
        py = ftol((pivy - hh) * scale + 0.5) + hh
        px = ftol((pivx - hw) * scale + 0.5) + hw
        percent = ftol(scale * 100.0)
        self._scaled(name, 1, 1, 0, rect, x - px, y - py, percent, out)

    def _scaled(self, name, cols, rows, cell, rect, x, y, percent, out) -> None:
        """0x4078E0 with the centre flag: moved by half the growth (rounded size), then 0x404610."""
        if percent != 100:
            p = f32(percent / 100.0)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            sw, sh = ftol(w * p + 0.5), ftol(h * p + 0.5)
            x += -half(rect[0] - rect[2] + sw)
            y += -half(rect[1] - rect[3] + sh)
        out.append(PlantDraw(name, cols, rows, cell, x, y, rect=rect, scale=percent))

    # 0x42D9C0
    def _flower(self, plant: Plant, x: int, y: int, view: int, scale: float, out) -> None:
        gene = plant.flower
        if not (1 <= gene <= 23 or gene in D.FLOWER_ART) or gene <= 0:
            return
        age = f32(plant.age)
        if not AGE_BUDS <= age:
            return
        if not AGE_FLOWERS <= age:
            factor = f32((age - 21.0) * 0.5 / 3.0 + 0.5)
            scale = f32(factor * scale)
            gene = 0
        elif not age >= AGE_FULL:
            factor = f32((age - 24.0) * 0.5 * 0.25 + 0.5)
            scale = f32(factor * scale)
            cap = f32(plant.bloom / 100.0)
            if not cap >= scale:
                scale = cap
        art = D.FLOWER_ART.get(gene) or D.FLOWER_ART[0]
        name, cols, rows = sprite(art[2])
        cw, ch = self.cells((name, cols, rows))
        frame = art[4] + view
        col, row = min(frame % cols, cols - 1), min(frame // cols, rows - 1)
        rect = (col * cw, row * ch, col * cw + cw, row * ch + ch)
        oy = ftol(art[6] * scale - 0.5)
        ox = ftol(art[5] * scale - 0.5)
        left = x - (half(ch) - ox)
        top = y - (half(cw) - oy)
        percent = ftol(scale * 100.0)
        self._scaled(name, cols, rows, row * cols + col, rect, left, top, percent, out)


# ------------------------------------------------------------------ compositing (the game's scaler)

def resample(piece: Image, percent: int) -> Image:
    """0x404610's scaled copy of a w x h piece (alpha 1.0): the box average when shrinking
    (0x404978..0x404DE8), the nearest pixel when enlarging (0x404DED..). Straight RGBA."""
    if percent == 100:
        return piece
    scale = f32(percent / 100.0)
    sw, sh = piece.width, piece.height
    dw, dh = ftol(sw * scale), ftol(sh * scale)
    out = Image(max(0, dw), max(0, dh))
    if dw <= 0 or dh <= 0:
        return out
    step_x, step_y = sw / dw, sh / dh
    src, dst = piece.data, out.data
    if scale < 1.0:
        fy = 0 - step_y * 0.5
        row_end = -1
        last_row, last_col = sh - 1, sw - 1
        half_x = step_x * 0.5
        for j in range(dh):
            row_start = row_end + 1
            fy += step_y
            row_end = min(ftol(fy) + 1, last_row)
            fx = 0 - half_x
            col_end = -1
            for i in range(dw):
                col_start = col_end + 1
                fx += step_x
                col_end = min(ftol(fx) + 1, last_col)
                if row_start > row_end or col_start > col_end:
                    continue
                r = g = b = a = 0
                for yy in range(row_start, row_end + 1):
                    at = (yy * sw + col_start) * 4
                    for _ in range(col_end - col_start + 1):
                        r += src[at]; g += src[at + 1]; b += src[at + 2]; a += src[at + 3]
                        at += 4
                count = (row_end - row_start + 1) * (col_end - col_start + 1)
                alpha = a // count
                if alpha == 0:
                    continue
                o = (j * dw + i) * 4
                dst[o], dst[o + 1], dst[o + 2], dst[o + 3] = r // count, g // count, b // count, alpha
    else:
        fy = 0.0
        for j in range(dh):
            row = ftol(fy)
            fx = 0.0
            for i in range(dw):
                at = (row * sw + ftol(fx)) * 4
                o = (j * dw + i) * 4
                dst[o:o + 4] = src[at:at + 4]
                fx += step_x
            fy += step_y
    return out


def composite(sheets: Sheets, plan, origin=(0, 0), size=None) -> Image:
    """The plan drawn on a transparent canvas just big enough (or `size`), moved by -origin."""
    pieces = []
    left = top = 10 ** 9
    right = bottom = -10 ** 9
    cache: dict = {}
    for call in plan:
        key = (call.file.casefold(), getattr(call, "rect", None), call.cols, call.rows, call.cell, call.flip, getattr(call, "scale", 100))
        piece = cache.get(key)
        if piece is None:
            sheet = sheets.image(call.file)
            rect = getattr(call, "rect", None) or _cell_rect(sheet, call)
            piece = sheet.sub(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
            if call.flip:
                piece = piece.flipped()
            piece = resample(piece, getattr(call, "scale", 100))
            cache[key] = piece
        pieces.append((piece, call))
        left, top = min(left, call.x), min(top, call.y)
        right, bottom = max(right, call.x + piece.width), max(bottom, call.y + piece.height)
    if not pieces:
        return Image(1, 1)
    if size is None:
        origin, size = (left, top), (right - left, bottom - top)
    canvas = Image(*size)
    for piece, call in pieces:
        canvas.draw(piece, call.x - origin[0], call.y - origin[1], call.alpha, call.tint)
    return canvas


def _cell_rect(sheet: Image, call) -> tuple:
    w, h = sheet.width // call.cols, sheet.height // call.rows
    col, row = call.cell % call.cols, call.cell // call.cols
    return (col * w, row * h, col * w + w, row * h + h)


# ------------------------------------------------------------------ growing a plant of your own

class Rolls:
    """The game's Random(n) (0x4033B0, rand() % n) for a plant of your own: a fixed sequence per
    shape and stage, so the same choices always give the same picture."""

    def __init__(self, key: str) -> None:
        self.rng = random.Random(key)

    def __call__(self, n: int) -> int:
        return self.rng.randrange(n) if n > 0 else 0


def starting_plant(foliage: int, flower: int, shape: int) -> Plant:
    """The pot record the class's constructor makes (STARTING_SHAPES), with the base
    constructor's size 80 (0x42CA50)."""
    shapes = D.STARTING_SHAPES[foliage]
    branches = [Branch(p, k, f32(b), [tuple(c) for c in cs]) for p, k, b, cs in shapes[(shape - 1) % len(shapes)]]
    return Plant(foliage=foliage, flower=flower, age=0.0, branches=branches)


def _branches(plant: Plant) -> list:
    """The branch records the game walks: up to the first unused one (type 0), at most 60."""
    out = []
    for b in plant.branches[:BRANCH_MAX]:
        if b.kind == 0:
            break
        out.append(b)
    return out


def set_children(plant: Plant, branch: Branch, kind: int) -> None:
    """0x42D760: each child of the branch (its own children first, when it is alive) takes `kind`,
    and a dead one (4) loses its flowers."""
    for _joint, child in branch.children:
        if not 0 <= child < len(plant.branches):
            continue
        c = plant.branches[child]
        if c.kind == 1:
            set_children(plant, c, kind)
        c.kind = kind
        if kind == 4:
            c.flowers = []


def age_seven_roll(plant: Plant, parts: tuple, rand) -> None:
    """0x42DEC0 (once, when the plant reaches 7): each live branch whose part is a leaf (+0x04 = 1)
    dies on Random(100) < 10: type 4, no flowers, its children dead too (0x42D760)."""
    leaves = []
    for k, b in enumerate(_branches(plant)):
        if b.kind == 1:
            part = find_part(parts, b.part)
            if part is not None and part.kind == 1:
                leaves.append(k)
    for k in leaves:
        if rand(100) < 10:
            b = plant.branches[k]
            b.kind = 4
            b.flowers = []
            set_children(plant, b, 4)


def spot_count(part: Part, foliage: int, formula: bool) -> int:
    """+0xA8, or while the formula flowers (flower_everything): the spots in place from the first,
    for the tables Store Upgrades and Items.dll knows."""
    if not formula or foliage not in D.FORMULA_FOLIAGES:
        return part.spot_count
    filled = 0
    while filled < 6 and part.spots[filled] != (0, 0, 0):
        filled += 1
    return max(part.spot_count, filled)


def spot_free(plant: Plant, branch: Branch, part: Part, spot: int, formula: bool) -> bool:
    """0x42D330: a spot on a joint (flags 0x100) is taken while a live branch grows from that
    joint; the formula answers free for every spot (stub_joint_free)."""
    if formula:
        return True
    sx, sy, flags = part.spots[spot]
    if not flags & 0x100:
        return True
    joint = next((j for j in range(max(0, part.joint_count))
                  if j < 10 and part.joints[j][:2] == (sx, sy)), -1)
    if joint < 0:
        return True
    for j, child in branch.children:
        if j == joint:
            return not (0 <= child < len(plant.branches) and plant.branches[child].kind == 1)
    return True


def free_spot(plant: Plant, branch: Branch, parts: tuple, foliage: int, rand, formula: bool) -> int:
    """0x42DC60: a random free spot of the branch's part (-1: none)."""
    part = find_part(parts, branch.part)
    if part is None:
        return -1
    taken = {fl.spot for fl in branch.flowers}
    free = [s for s in range(spot_count(part, foliage, formula))
            if s not in taken and spot_free(plant, branch, part, s, formula)]
    if not free:
        return -1
    return free[rand(len(free))]


def add_flower(plant: Plant, parts: tuple, foliage: int, rand, formula: bool = False) -> bool:
    """0x42EBC0: one more flower. Each live branch with room ranks children + flowers + 1; the
    lowest rank goes first, a random branch of that rank, a random free spot on it; the flower's
    view is Random(3)."""
    branches = _branches(plant)
    rank = [0] * len(branches)
    top = 0
    for k, b in enumerate(branches):
        if b.kind != 1:
            continue
        part = find_part(parts, b.part)
        if part is None:
            return False
        if len(b.flowers) < spot_count(part, foliage, formula):
            rank[k] = len(b.children) + len(b.flowers) + 1
            top = max(top, rank[k])
    if top == 0:
        return False
    level, left = 0, 0
    while True:
        if left == 0:
            level += 1
            left = rank.count(level)
            if left == 0:
                if level <= top:
                    continue
                return False
        pick = rand(left)
        k = [i for i, r in enumerate(rank) if r == level][pick]
        left -= 1
        spot = free_spot(plant, branches[k], parts, foliage, rand, formula)
        if spot < 0:
            rank[k] = 0
            if level <= top:
                continue
            return False
        branches[k].flowers.append(Flower(spot, rand(3), 1.0, 1))
        return True


def add_flowers(plant: Plant, parts: tuple, foliage: int, rand, many: int, more: int, formula: bool = False) -> int:
    """0x42ED60(many, more): up to many + more flowers; the bloom (+0x8C) is set once: 70 when
    `more` is not 0, else 100 (0x42EDC3)."""
    added = 0
    while added < many + more and add_flower(plant, parts, foliage, rand, formula):
        added += 1
    if plant.bloom == 0:
        plant.bloom = 70 if more else 100
    return added


def first_flowering(plant: Plant, parts: tuple, foliage: int, rand) -> None:
    """The update's flowering (0x42E375..0x42E45A), once the plant is 21 and has no flowers: one
    and one, (2-3, 1-2) above size 90, more for the 56-pixel flowers, by health."""
    art = D.FLOWER_ART.get(plant.flower) or D.FLOWER_ART[0]
    small = art[2] == 0x51
    many, more = 1, 1
    if plant.size > 90:
        many = rand(2) + 2
        more = rand(2) + 1
    if small:
        many += rand(2) + 1
        more += rand(2)
    if plant.health < 50:
        many -= 2
        more = 0
    elif plant.health < 80:
        many -= 1
        more -= 1
    if many <= 0:
        many = 1 if rand(100) >= 10 else 0
    if more <= 0:
        more = 1 if rand(100) >= 50 else 0
    add_flowers(plant, parts, foliage, rand, many, more)


def apply_formula(plant: Plant, parts: tuple, foliage: int, rand) -> None:
    """Store Upgrades and Items.dll's apply_formula: health 100, every hidden or dead branch alive,
    size 110, no age-7 roll, a flower on every spot (the formula's spots too), bloom 100, age 28."""
    plant.health = 100
    for b in _branches(plant):
        if b.kind in (2, 4):
            b.kind = 1
    plant.size = SIZE_MAX
    plant.formula = True
    add_flowers(plant, parts, foliage, rand, 360, 0, formula=True)
    plant.bloom = 100
    plant.age = max(plant.age, AGE_FULL)


# The "Make your own" growth stages.
STAGES = (
    ("seedling", "Seedling"),
    ("budding", "Budding"),
    ("bloom", "Normal bloom"),
    ("max", "Max bloom"),
    ("formula", "Max bloom + all effects"),
    ("dead", "Dead"),
)
STAGE_AGES = {"seedling": 8.0, "budding": 22.5, "bloom": 28.0, "max": 28.0, "formula": 28.0, "dead": 28.0}
STAGE_NOTE = ("Seedling: age 8, as the game's starting seedlings. Budding: age 22.5 (buds come at 21, "
              "flowers at 24). Normal bloom: full grown, the game's first flowering. Max bloom: size 110 "
              "and a flower on every free spot (plant food and fertilizer as often as you like). "
              "Max bloom + all effects: the Radioactive Plant Formula: every branch grown, no dead leaves. "
              "Dead: the normal bloom after it died (health 0): the game draws it at 85% with its dead "
              "pictures and no flowers. The game's draw shows no other state: thirst, pests and poor "
              "health change nothing in a plant's picture.")


def grow_custom(foliage: int, flower: int, shape: int, stage: str) -> Plant:
    """A plant of your own, grown by the game's rules to `stage`."""
    if foliage not in D.STARTING_SHAPES:
        raise PictureError(f"There is no foliage {foliage}.")
    plant = starting_plant(foliage, flower, shape)
    parts = SHAPES[foliage]
    rand = Rolls(f"plant {foliage} {flower} shape {shape} {stage}")
    age = STAGE_AGES.get(stage)
    if age is None:
        raise PictureError(f"There is no stage {stage!r}.")
    if stage != "formula" and age >= 7.0:
        age_seven_roll(plant, parts, rand)
    if stage == "max":
        plant.size = SIZE_MAX
    if age >= AGE_BUDS and stage != "formula":
        first_flowering(plant, parts, foliage, rand)
    if stage == "max":
        add_flowers(plant, parts, foliage, rand, 360, 0)
    if stage == "formula":
        apply_formula(plant, FORMULA_SHAPES[foliage], foliage, rand)
    if stage == "dead":
        plant.health = 0                 # 0x42E27D: a plant that dies keeps its branches and flowers
    plant.age = f32(age)
    return plant


# ------------------------------------------------------------------ the save (read only)

def save_path(save_folder, slot: int) -> Path:
    return Path(save_folder) / f"Plant Tycoon{int(slot)}.ldw"


def sidecar_path(save_folder, slot: int) -> Path:
    return Path(save_folder) / "Plant Tycoon Fix Patcher Data" / f"Extra Greenhouses {int(slot)}.dat"


# ------------------------------------------------------------------ decorations, bugs and pots

ORNAMENTS_AT, ORNAMENT_SIZE = 0x9EC, 0x20       # state + 0x9EC + k x 0x20: the ornament is owned
# The store's names (Game Mechanics: Nursery ornaments), matched to each ornament's pictures.
ORNAMENT_NAMES = ("Stone Turtle", "Sundial", "Weather Vane", "Charming Lantern", "Owl Statuette",
                  "Country Wheelbarrow", "Bird House", "Cherub Statuette", "Bench", "Fountain", "Sign",
                  "Fence", "Gate", "Cash Register", "Refurbishment")
BUG_SPRITE = 0x9E                    # small_bugs.png: 12 x 24 cells, 6 per bug (0x41685A: 6 x bug + pose)
BUG_COUNT, BUG_FRAMES = 48, 6
SOIL_LOOKS = (("none", "No soil"), ("soil", "Soil"), ("planted", "Soil, planted"))
SOIL_LEVELS = (0, 1, 2)              # 0x41DDE0: no soil upgrade, the first, the second


class SceneryPlanner:
    """The nursery's whole-picture sprite draw (0x4207F0) and the sprite manager's cell draw
    (0x4208F0), for decorations, bugs and pots."""

    def __init__(self, cells, planner: Planner) -> None:
        self.cells = cells
        self.planner = planner

    def decoration(self, k: int) -> list:
        """Ornament k as the nursery's scenery draws it when owned (0x437070(2), then (1)), at its
        place on the nursery screen."""
        out = []
        for sprite_id, x, y, scale, alpha in D.DECORATIONS[k]:
            if alpha != 100:
                raise PictureError("The game draws no decoration see-through.")
            name, _cols, _rows = sprite(sprite_id)
            w, h = self.cells((name, 1, 1))
            # 0x4207F0 -> 0x409090 (whole, unscaled) or 0x4091B0 -> 0x4085D0 (scaled about its centre)
            self.planner._scaled(name, 1, 1, 0, (0, 0, w, h), x, y, scale, out)
        return out

    def bug(self, bug: int, frame: int) -> list:
        """Cell 6 x bug + frame of small_bugs.png, unscaled (0x4208F0 with scale 1, alpha 100)."""
        return [self.planner._cell(BUG_SPRITE, bug * BUG_FRAMES + frame, 0, 0)]

    def pot(self, style: int, soil: str, level: int, wet: bool) -> list:
        """The pot draw (0x42F740) of a pot with no plant (or a planted mound, soil frame + 1)."""
        plant = Plant(foliage=1 if soil == "planted" else 0, flower=0, age=0.0, pot=style,
                      soil=0 if soil == "none" else 1, water=900 if wet else 0)
        return self.planner.plan(plant, 0, 0, soil_level=level)


@dataclass
class SavedPlants:
    """The pot records of a save: Greenhouse 1 (the save) and 2-6 (Extra Greenhouses' sidecar)."""
    greenhouses: list                # [greenhouse][pot] -> record bytes
    soil_level: int = 0
    note: str = ""
    ornaments: tuple = ()            # the nursery ornaments owned (k of DECORATIONS)


def read_save(save_folder, slot: int) -> SavedPlants:
    """Read only: the save's 15 pots and, when there is one, the sidecar's 75."""
    path = save_path(save_folder, slot)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PictureError(f"The save {path} could not be read ({exc.strerror or exc}).") from None
    if len(data) != SAVE_HEADER + SAVE_BODY or data[:4] != b"ldwg":
        raise PictureError(f"{path} is not a Plant Tycoon save.")
    body = SAVE_HEADER - 8                        # file offset of state + n is body + n
    pots = [data[body + POTS_AT + k * RECORD_SIZE: body + POTS_AT + (k + 1) * RECORD_SIZE] for k in range(POTS)]
    level = 0
    for at, value in SOIL_UPGRADES:
        if data[body + at]:
            level = value
            break
    owned = tuple(k for k in sorted(D.DECORATIONS) if data[body + ORNAMENTS_AT + k * ORNAMENT_SIZE])
    saved = SavedPlants([pots], level, ornaments=owned)
    side = sidecar_path(save_folder, slot)
    if side.is_file():
        try:
            raw = side.read_bytes()
        except OSError:
            raw = b""
        size = SIDECAR_WORDS * 4 + EXTRA_GREENHOUSES * POTS * RECORD_SIZE
        header = struct.unpack_from(f"<{SIDECAR_WORDS}I", raw) if len(raw) >= SIDECAR_WORDS * 4 else ()
        if len(raw) == size and header[:5] == (SIDECAR_MAGIC, SIDECAR_VERSION, EXTRA_GREENHOUSES, POTS, RECORD_SIZE):
            at = SIDECAR_WORDS * 4
            for g in range(EXTRA_GREENHOUSES):
                saved.greenhouses.append([raw[at + (g * POTS + k) * RECORD_SIZE: at + (g * POTS + k + 1) * RECORD_SIZE]
                                          for k in range(POTS)])
        else:
            saved.note = f"{side.name} is not a file the Extra Greenhouses setting wrote, so Greenhouses 2-6 are left out."
    return saved


def plant_label(plant: Plant) -> str:
    import breeding_plant as bp
    try:
        name = bp.species_name((plant.foliage, plant.flower))
    except IndexError:
        name = f"Foliage {plant.foliage}, flower {plant.flower}"
    return " ".join(name.split())


def plant_state(plant: Plant) -> str:
    age = int(plant.age)
    if plant.health <= 0:
        return f"dead, age {age}"
    if plant.age < AGE_BUDS:
        stage = "seedling"
    elif plant.age < AGE_FLOWERS:
        stage = "with buds"
    else:
        stage = "mature"
    return f"{stage}, age {age}"


# ------------------------------------------------------------------ the renderer

def required_files() -> list:
    """Every image the renderer may read (stock and patcher): the pot and soil, every part, dead
    and flower sheet."""
    names = [D.SPRITES[POT_SPRITE][0], D.SPRITES[SOIL_SPRITE][0]]
    for parts in SHAPES.values():
        for part in parts:
            for sheet in (part.sheet, part.dead):
                if sheet and sheet in D.SPRITES:
                    names.append(D.SPRITES[sheet][0])
    for art in D.FLOWER_ART.values():
        names.append(D.SPRITES[art[2]][0])
    for calls in D.DECORATIONS.values():
        names += [D.SPRITES[c[0]][0] for c in calls]
    names.append(D.SPRITES[BUG_SPRITE][0])
    return list(dict.fromkeys(names))


def patcher_art() -> dict:
    """The patcher's own art: Unused Flowers' 64-pixel flower sheet (the stock cells unchanged,
    the new flowers in its empty ones)."""
    root = Path(__file__).resolve().parents[1] / "assets"
    return {"flowers64x64_grid.png": root / "plant_tycoon_flowers" / "Images" / "flowers64x64_grid.png"}


class _FolderSource:
    """A game folder read straight from disk (its Images, then the patcher's art first)."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        images = self.folder / "Images"
        try:
            self.files = {p.name.casefold(): p for p in images.iterdir() if p.is_file()}
        except OSError:
            self.files = {}
        self.patcher = {k.casefold(): v for k, v in patcher_art().items()}

    def read(self, name: str):
        for table in (self.patcher, self.files):
            path = table.get(name.casefold())
            if path is not None:
                try:
                    return path.read_bytes()
                except OSError:
                    pass
        return None


def load(source) -> "Renderer":
    if isinstance(source, (str, Path)):
        source = _FolderSource(Path(source))
    return Renderer(source)


class Renderer:
    game = GAME

    def __init__(self, source) -> None:
        self.source = source
        self.sheets = Sheets(source)
        missing = [n for n in required_files() if source is None or source.read(n) is None]
        problem = getattr(source, "problem", "") or ""
        if missing and not problem:
            shown = ", ".join(missing[:3]) + (" ..." if len(missing) > 3 else "")
            problem = f"{len(missing)} Plant Tycoon picture file(s) are missing ({shown})."
        self.problem = problem
        self.planner = Planner(self._cell_size)
        self.scenery = SceneryPlanner(self._cell_size, self.planner)
        self._saved: dict = {}

    def _cell_size(self, key) -> tuple:
        name, cols, rows = key
        image = self.sheets.image(name)
        return image.width // max(1, cols), image.height // max(1, rows)

    # -------------------------------------------------------------- saved plants
    def _read(self, save_folder, slot: int) -> SavedPlants:
        key = (str(save_folder), int(slot))
        saved = read_save(save_folder, slot)
        self._saved[key] = saved
        return saved

    def saved_items(self, save_folder, slot: int) -> list:
        saved = self._read(save_folder, slot)
        items, for_sale = [], []
        for g, pots in enumerate(saved.greenhouses):
            for k, record in enumerate(pots):
                plant = Plant.from_record(record)
                if plant.foliage <= 0 or not plant.branches:
                    continue
                label = f"{plant_label(plant)} ({plant_state(plant)})"
                detail = (f"Greenhouse {g + 1}, pot {k + 1} (row {k // 5 + 1}, column {k % 5 + 1}). "
                          f"Health {plant.health}, size {plant.size}.")
                items.append(SavedItem(f"g{g}p{k}", label, f"Greenhouse {g + 1}", "plant", detail))
                if plant.for_sale and plant.health > 0:
                    for_sale.append(SavedItem(f"n{g}p{k}", label, "Nursery", "plant", detail + " For sale."))
        decorations = [SavedItem(f"d{k}", ORNAMENT_NAMES[k], "Nursery decorations", "decoration",
                                 "Owned: the nursery shows it.") for k in saved.ornaments]
        return items + for_sale + decorations

    def _plant(self, save_folder, slot: int, item_id: str) -> tuple:
        key = (str(save_folder), int(slot))
        saved = self._saved.get(key) or self._read(save_folder, slot)
        try:
            g, k = (int(v) for v in item_id[1:].split("p"))
            record = saved.greenhouses[g][k]
        except (ValueError, IndexError):
            raise PictureError("That plant is no longer in the save.") from None
        plant = Plant.from_record(record)
        if plant.foliage <= 0:
            raise PictureError("That pot is empty now.")
        return plant, saved.soil_level

    def plan_saved(self, save_folder, slot: int, item_id: str) -> list:
        if item_id.startswith("d"):
            key = (str(save_folder), int(slot))
            saved = self._saved.get(key) or self._read(save_folder, slot)
            try:
                k = int(item_id[1:])
            except ValueError:
                raise PictureError("There is no such decoration.") from None
            if k not in saved.ornaments:
                raise PictureError("The save no longer owns that decoration.")
            return self.scenery.decoration(k)
        plant, level = self._plant(save_folder, slot, item_id)
        return self.planner.plan(plant, 0, 0, soil_level=level)

    def render_saved(self, save_folder, slot: int, item_id: str) -> Image:
        return composite(self.sheets, self.plan_saved(save_folder, slot, item_id))

    # -------------------------------------------------------------- plants of your own
    def custom_choices(self, extras: frozenset, spoilers: bool, discovered) -> list:
        import breeding_plant as bp
        new = "new_flowers" in extras
        known_foliage = {f for f, _fl in discovered} if (discovered is not None and not spoilers) else None
        known_flower = {fl for _f, fl in discovered} if (discovered is not None and not spoilers) else None
        foliages = [Option(f, bp.FOLIAGE_WORD[f]) for f in range(1, 24) if known_foliage is None or f in known_foliage]
        flowers = [Option(fl, bp.FLOWER_WORD[fl].strip()) for fl in range(1, 24)
                   if known_flower is None or fl in known_flower]
        if new:
            flowers += [Option(fl, bp.FLOWER_WORD[fl], patcher=True) for fl in range(24, 38)
                        if known_flower is None or fl in known_flower]
        stages = [Option(k, label, patcher=(k == "formula" and "plant_upgrades" in extras)) for k, label in STAGES]
        shapes = [Option(n, f"Shape {n}") for n in range(1, D.SHAPE_COUNT + 1)]
        pots = [Option(-1, "No pot")] + [Option(n, f"Pot {n + 1}") for n in range(D.SPRITES[POT_SPRITE][2])]
        fields = (
            Field("flower", "Flower", tuple(flowers), flowers[0].key if flowers else None),
            Field("foliage", "Foliage", tuple(foliages), foliages[0].key if foliages else None),
            Field("stage", "Stage", tuple(stages), "bloom"),
            Field("shape", "Shape", tuple(shapes), 1),
            Field("pot", "Pot", tuple(pots), 0),
        )
        note = STAGE_NOTE
        if not spoilers and discovered is not None:
            note += " Spoilers are off: only the foliage and flowers you have discovered are offered."
        styles = tuple(Option(n, f"Pot {n + 1}") for n in range(D.SPRITES[POT_SPRITE][2]))
        return [
            Subject("plant", "Plant", fields, note),
            Subject("decoration", "Decorations",
                    (Field("ornament", "Decoration", tuple(Option(k, ORNAMENT_NAMES[k]) for k in sorted(D.DECORATIONS)),
                           min(D.DECORATIONS)),),
                    "Each nursery ornament as the nursery draws it once bought (the Refurbishment is the "
                    "whole repainted nursery building)."),
            Subject("bug", "Bugs",
                    (Field("bug", "Bug", tuple(Option(b, f"Bug {b + 1}") for b in range(BUG_COUNT)), 0),
                     Field("frame", "Frame", tuple(Option(f, f"Frame {f + 1}") for f in range(BUG_FRAMES)), 0)),
                    "Every bug the greenhouse can show, in each of its 6 pictures (small_bugs.png), drawn "
                    "as the game draws a bug."),
            Subject("pot", "Pots",
                    (Field("style", "Pot", styles, 0),
                     Field("soil", "Soil", tuple(Option(k, label) for k, label in SOIL_LOOKS), "soil"),
                     Field("level", "Soil upgrade", (Option(0, "None"), Option(1, "First"), Option(2, "Second")), 0),
                     Field("wet", "Watered", (Option(False, "Dry"), Option(True, "Wet")), False)),
                    "A greenhouse pot as the game draws it: wet soil is a pot with more than 500 water; "
                    "planted soil has the mound a plant grows from."),
        ]

    def _custom_plant(self, spec: dict) -> tuple:
        if spec.get("subject", "plant") != "plant":
            raise PictureError(f"There is no {spec.get('subject')!r} to make in Plant Tycoon.")
        try:
            foliage, flower = int(spec.get("foliage", 1)), int(spec.get("flower", 1))
            shape, pot = int(spec.get("shape", 1)), int(spec.get("pot", 0))
        except (TypeError, ValueError):
            raise PictureError("Pick a foliage, a flower, a shape and a pot.") from None
        if not 1 <= foliage <= 23:
            raise PictureError("Pick a foliage.")
        if flower not in D.FLOWER_ART or flower == 0:
            raise PictureError("Pick a flower.")
        plant = grow_custom(foliage, flower, shape, str(spec.get("stage", "bloom")))
        plant.pot = max(0, pot)
        return plant, pot >= 0

    def plan_custom(self, spec: dict) -> list:
        subject = spec.get("subject", "plant")
        try:
            if subject == "decoration":
                k = int(spec.get("ornament", min(D.DECORATIONS)))
                if k not in D.DECORATIONS:
                    raise PictureError("Pick a decoration.")
                return self.scenery.decoration(k)
            if subject == "bug":
                bug, frame = int(spec.get("bug", 0)), int(spec.get("frame", 0))
                if not (0 <= bug < BUG_COUNT and 0 <= frame < BUG_FRAMES):
                    raise PictureError("Pick a bug and a frame.")
                return self.scenery.bug(bug, frame)
            if subject == "pot":
                style, level = int(spec.get("style", 0)), int(spec.get("level", 0))
                soil = str(spec.get("soil", "soil"))
                if not (0 <= style < D.SPRITES[POT_SPRITE][2] and level in SOIL_LEVELS
                        and soil in dict(SOIL_LOOKS)):
                    raise PictureError("Pick a pot, its soil and its upgrade.")
                return self.scenery.pot(style, soil, level, bool(spec.get("wet", False)))
        except (TypeError, ValueError):
            raise PictureError("Pick one of the choices offered.") from None
        plant, pot = self._custom_plant(spec)
        return self.planner.plan(plant, 0, 0, pot=pot)

    def render_custom(self, spec: dict) -> Image:
        return composite(self.sheets, self.plan_custom(spec))
