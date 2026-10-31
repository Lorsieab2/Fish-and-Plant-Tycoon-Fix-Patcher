# Picture Studio: the renderer interface

Picture Studio (Tools tab) shows the fish and plants in a save, and pictures you make yourself,
drawn exactly as the game draws them, and saves them as transparent PNGs. One window
(`src/picture_studio.py`) shows either game through a renderer module:

- `src/pictures_fish.py` (Fish Tycoon);
- `src/pictures_plant.py` (Plant Tycoon).

The shared image type, PNG reader/writer, export sizes and picture cache are in
`src/picture_image.py`. No Pillow, no Unicorn and no game art ship: everything is pure Python
(`zlib`, `struct`), and the pictures are cut from the player's own game copy, cached in
"Picture Studio Pictures\<Fish|Plant>" beside the patcher (the Breeding Guide's cache code,
with the renderer's own file list).

Every drawing rule must come from the game's own draw code, ported to Python and proven by
tests that run that draw code in Unicorn on the vanilla executable, record every sprite draw
call (sheet, cell, x, y, flip, alpha, colour), and compare them with the renderer's plan.

## The shared module (`src/picture_image.py`)

```python
class PictureError(Exception): ...            # a picture that cannot be drawn, in words

class Image:                                   # straight (not premultiplied) RGBA, 8 bits
    width: int
    height: int
    data: bytearray                            # width * height * 4, rows top to bottom
    @classmethod
    def new(cls, width, height) -> Image       # fully transparent
    @classmethod
    def from_png(cls, data: bytes) -> Image    # any PNG the games ship (palette, grey, RGB, RGBA, tRNS)
    def to_png(self) -> bytes                  # colour type 6 (RGBA), 8 bits
    def copy(self) -> Image
    def sub(self, x, y, w, h) -> Image         # a cell of a sheet (clipped to the image)
    def cell(self, cols, rows, index) -> Image # cell `index` of a cols x rows grid
    def flipped(self) -> Image                 # mirrored left-right
    def draw(self, src, x, y, alpha=255, tint=None) -> None
        # src over self at (x, y), clipped; `alpha` multiplies src's alpha (SDL's surface
        # alpha), `tint` (r, g, b) multiplies its colour (SDL's colour mod).
    def bbox(self) -> tuple[int, int, int, int] | None   # (left, top, right, bottom) of alpha > 0
    def cropped(self, margin=MARGIN) -> Image  # cut to bbox, plus `margin` transparent pixels
    def scaled(self, factor: int) -> Image     # nearest neighbour, crisp
    def resized(self, width, height) -> Image  # smooth (premultiplied, antialiased linear)
    def photo(self, tk_mod, master, max_side=None)   # a Tk PhotoImage for previews

MARGIN = 4                                     # pixels around a cropped picture ("small margin")
SIZES = (("1x", 1), ("2x", 2), ("4x", 4))      # crisp game-size multiples

def export(image, *, scale=1, size=None, margin=MARGIN) -> Image
    """Crop to the drawn pixels plus `margin` (0: none), then scale: `scale` (nearest) or
    `size=(w, h)` (smooth; one of them may be 0 to keep the aspect ratio)."""
def save_png(image, path, **export_options) -> Path    # writes via a temp file, then replaces
def safe_file_name(text) -> str                         # a label as a Windows file name

@dataclass(frozen=True)
class SavedItem:
    id: str            # opaque to the window, stable for one read of the save
    label: str         # e.g. "Silky Shark (adult, 23 days)"
    location: str      # the group it is listed under: "Tank 1", "Isolation Tank", "Greenhouse 4"
    kind: str          # "fish", "creature", "decoration" / "plant", ...
    detail: str = ""   # a line for the details pane (age, health, state...)

@dataclass(frozen=True)
class Option:
    key: object        # what goes into the spec
    label: str
    patcher: bool = False      # added by a patcher setting (shown in brown)

@dataclass(frozen=True)
class Field:
    key: str           # the spec key
    label: str
    options: tuple[Option, ...]
    default: object = None

@dataclass(frozen=True)
class Subject:         # one "Make your own" tab
    key: str           # "fish" / "creature" / "decoration" / "plant" ...
    title: str
    fields: tuple[Field, ...]
    note: str = ""     # one line under the fields (what the stage/state choices mean)

def picture_source(game, copies, required, patcher_files) -> breeding_pictures.Pictures
    """The Studio's own picture cache for a game, built the first time from any game copy
    (read only), as the Breeding Guide's is: `required` is the renderer's file list,
    `patcher_files` its patcher-art map."""
```

## A renderer module (`src/pictures_fish.py`, `src/pictures_plant.py`)

```python
GAME: str                       # "fish" / "plant"

def required_files() -> list[str]
    """Every image file name the renderer may read (stock and patcher), as the game names it."""
def patcher_art() -> dict[str, Path]
    """The patcher's own art (assets/...), by file name, read before the game copy's."""

def load(source) -> Renderer
    """`source`: an object with .read(name) -> bytes | None (a breeding_pictures.Pictures from
    picture_image.picture_source), or a game folder Path (read straight from it)."""

class Renderer:
    game: str
    problem: str                # "" when the art is there; else one line saying why not
    def saved_items(self, save_folder, slot: int) -> list[SavedItem]
        """Everything drawable in the save, in the game's order: tanks/greenhouses (stock,
        then the extra ones from their sidecars), then creatures and decorations. Read only:
        never writes the save or a sidecar."""
    def render_saved(self, save_folder, slot: int, item_id: str) -> Image
        """That item as the game draws it now (its age, growth, state). Raises PictureError."""
    def custom_choices(self, extras: frozenset[str], spoilers: bool,
                       discovered: set | None) -> list[Subject]
        """The "Make your own" tabs. `extras`: the patcher setting ids on for the game copy
        (e.g. "ds_fish", "ds_store", "new_flowers", "plant_upgrades"); `discovered`: the
        Breeding Guide model's discovered species keys (None: no save). With spoilers off only
        discovered parts are offered."""
    def render_custom(self, spec: dict) -> Image
        """spec = {"subject": Subject.key, <Field.key>: <Option.key>, ...}. Raises PictureError."""
```

Additions since the first version:

- `saved_items` may take `spoilers: bool` (the window passes it when the renderer accepts it). The
  owner's rule: a fish's species name shows only when the game would show it (Fish Tycoon names
  a fish from age 20, its info panel 0x41D9ED), so with spoilers off a younger one is listed, and
  its PNG named, "Baby fish (age n)" / "Teen fish (age n)". The window's file names are
  "<label>, <location>".

- `Draw` has `scale` (percent, default 100): Fish Tycoon's scaled draw (0x408190), see
  `picture_image.scaled_cell`. `cell_rect` is the game's cell cut (0x4095F0, clamped).
- `Image.draw(alpha=A)` follows the game's blitter (0x4041C0): with A below 255 a pixel's alpha
  a becomes `(a * A + 127) >> 8` (proven in tests/test_pictures_fish.py).
- `render_saved` may take extra keyword options; the window passes `facing` ("left" / "right" /
  "turn") and `frame` (0-5) to the Fish renderer only, from its "Facing:" (Facing left / Facing right /
  Turning) and "Frame:" boxes under the preview; the plant window hides both (the pot draw has neither).
- The patcher's own parts (DS Exclusive Fish genes 23-29, DS Store Items' animals and rock, the
  Unused Flowers 24-37) are always offered (`Option.patcher`), whatever `extras` holds: their art
  ships in `assets/` (`patcher_art`). The window reads discoveries with the extras on.
- Fish Tycoon's Eggs tab: the tank effect 15 (0x410CE6, eggs_Grid.png, alpha 175) drawn by the
  effects pass 0x410F50, 16 frames. Nothing is drawn for an unhatched fish (age 0).
- Make your own, by the owner's spec: Fish has Fin, Body, Stage (baby, teen at each age 6-19,
  adult), State (healthy, ick, fungus, dead), Facing and Frame; Plant has Flower, Foliage and a
  Stage of seed / sprout / seedling / growing / budding / normal bloom / max bloom / max bloom +
  all effects and a State of alive or dead (any stage). The game draws no wilting or infested
  look: the plant draw (0x42E4A0) checks only health 0, the pot draw (0x42F740) only water > 500. The window builds one combobox per
  `Field`, in order.

Rules for both renderers:

- An `Image` is the whole sprite composition on a transparent canvas, in game pixels, before
  cropping; the window crops and scales on export (`export`).
- Drawing is done with `Image.draw` in the game's own layer order, with the game's own cell,
  offset, mirroring, surface alpha and colour modulation; the tests compare the renderer's
  plan (a list of draw calls) with the emulated game's.
- A renderer exposes its plan for the tests: `renderer.plan_custom(spec)` and
  `renderer.plan_saved(...)` return the list of `Draw(file, cols, rows, cell, x, y, flip,
  alpha, tint)` calls it composites (`picture_image.Draw`).
- Saves are read only; synthetic saves in the tests, never the owner's.
