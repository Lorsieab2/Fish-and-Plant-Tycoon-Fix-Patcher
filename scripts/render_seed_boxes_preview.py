"""Render the extra seed boxes' mockups from the game's own art and the DLLs' own drawing.

    python scripts/render_seed_boxes_preview.py "<vanilla Plant Tycoon folder>"

writes, in docs/images:

* extra-seed-box-store.png: the Supplies store's Upgrades view exactly as
  "Store Upgrades and Items.dll" draws it. The DLL's own on_draw runs in
  Unicorn on the vanilla executable (tests/store_emulator.py) with every item
  shown (the three Legendary packets, Time Warp, Add Money, the Extra
  Greenhouse and Nursery, both automatic upgrades, Extra Chemical Slots, and
  the one Extra Seed Box item with the Fourth to Seventh owned, "5 of 6"
  next), and each draw call it makes is
  composited from the game's sheets (the sprite table at 0x4855F0; the seed
  and chemical sheets are this mod's taller copies, as the DLL points them).
  The plant store's draw (0x4208F0) ignores its scale argument, so every
  picture is drawn at its frame's size, top left at (x, y).
* seed-boxes-7-9-storage.png: the Seed Storage screen on "Boxes 7-9" with the
  Seventh and Eighth owned (two drawers open), a few seeds, the gold arrows
  (leftarrow.png / rightarrow.png at 338 and 716, y -9), the Sort Seeds button
  (396, 6) and the label at (660, 9), as "Extra Seed Boxes.dll" and the stock
  draw (0x4342F0: addlSeedBox.png at (239, 201) and (239, 354) by drawer
  level, seeds at x 242 + 53 column, y 46 + 152 (row / 4) + 34 (row % 4))
  lay them out. Words are set from the game's font (PTfontsmall.png).

`store_draws` and `visible_rect` are also used by tests/test_seed_boxes_7_9.py
for the overlap checks.
"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import render_extra_greenhouses_preview as R  # noqa: E402

IMAGES_OUT = ROOT / "docs" / "images"
UPGRADE_IMAGES = ROOT / "assets" / "plant_tycoon_upgrades" / "Images"
SPRITE_TABLE, SPRITE_RECORD, SPRITE_COUNT = 0x4855F0, 0x34, 222
OVERRIDES = {0x2E: (UPGRADE_IMAGES / "seed_grid_legendary.png", 16, 8),     # the DLL's taller sheets
             0xB3: (UPGRADE_IMAGES / "Chemicals_Grid_upgrades.png", 2, 23)}
SHEET_SHADOW, SHEET_TICK = 0xB0, 0x25


def sprite_table(exe: bytes) -> dict[int, tuple[str, int, int]]:
    table = {}
    for k in range(SPRITE_COUNT):
        rec = struct.unpack_from("<6I", exe, R.file_offset(exe, SPRITE_TABLE + k * SPRITE_RECORD))
        if rec[1] == 0:                                     # the spare record (the Upgrades link's)
            continue
        at = R.file_offset(exe, rec[1])
        name = exe[at:exe.index(b"\0", at)].decode("latin-1")
        table[rec[0]] = (name, max(1, rec[4]), max(1, rec[5]))
    return table


class Sheets:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.table = sprite_table((folder / "Plant Tycoon.exe").read_bytes())
        self.cache: dict[int, tuple[Image.Image, int, int]] = {}

    def frame(self, sheet: int, frame: int) -> Image.Image:
        if sheet not in self.cache:
            if sheet in OVERRIDES:
                path, cols, rows = OVERRIDES[sheet]
            else:
                name, cols, rows = self.table[sheet]
                path = self.folder / "Images" / name
            self.cache[sheet] = (Image.open(path).convert("RGBA"), cols, rows)
        image, cols, rows = self.cache[sheet]
        w, h = image.width // cols, image.height // rows
        frame = min(frame, cols * rows - 1)                 # 0x409EE0 clamps past the last frame
        c, r = frame % cols, frame // cols
        return image.crop((c * w, r * h, c * w + w, r * h + h))


def visible_rect(sheets: Sheets, draw: tuple) -> tuple[int, int, int, int] | None:
    """The screen rectangle of a draw call's non-transparent pixels (right and bottom exclusive)."""
    kind, sheet, frame, x, y = draw
    box = sheets.frame(sheet, frame).getchannel("A").getbbox()
    return None if box is None else (x + box[0], y + box[1], x + box[2], y + box[3])


def store_draws(owned: tuple[int, ...] = (1, 1, 1, 1, 0, 0), version: int = 2,
                chem_slots: int | None = None) -> list[tuple]:
    """Run the Upgrades DLL's on_draw with every item shown; return its draws in order:
    ("sprite" | "shadow", sheet, frame, x, y), frame 0 for a shadow.  chem_slots: None without
    "Extra Chemical Slots.dll" (its item hidden), else what its FtfpChemSlotsOwned says (0, 1)."""
    import store_emulator as E
    with tempfile.TemporaryDirectory() as tmp:
        dll, symbols = E.build_with_map("ftfp_plant_upgrades", UPGRADE_IMAGES.parent / "Store Upgrades and Items.dll",
                                        Path(tmp))
        exe = E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"
        emu = E.Emulator(exe, dll, symbols)
        draws: list[tuple] = []
        emu.hook(0x004208F0, lambda e: (draws.append(("sprite", e.arg(0), e.arg(1), e.arg(2), e.arg(3))), 0)[1], 0x1C)
        emu.hook(0x004207F0, lambda e: (draws.append(("shadow", e.arg(0), 0, e.arg(1), e.arg(2))), 0)[1], 0x14)
        chem_owned = emu.thunk()
        emu.hook(chem_owned, lambda e: chem_slots, 0)
        emu.hook_import("GetModuleHandleW", lambda e: 0x6D000000 if chem_slots is not None and e.wstring(e.arg(0))
                        == "Extra Chemical Slots.dll" else 0, 4)
        emu.hook_import("GetProcAddress", lambda e: chem_owned if e.cstring(e.arg(1)) == b"FtfpChemSlotsOwned" else 0, 8)
        events, owned_fn, one = emu.alloc(0x20), emu.thunk(), emu.thunk()
        emu.hook(owned_fn, lambda e: owned[e.arg(0)] if 0 <= e.arg(0) < len(owned) else 0, 0)
        emu.hook(one, lambda e: 0, 0)
        emu.write32(events, version)
        for k in range(1, 7):
            emu.write32(events + 4 * k, one)
        emu.write32(events + 4 * 5, owned_fn)
        emu.write32(emu.sym("_boxes"), events)
        for i in range(3):                                      # three Legendary packets on the shelf
            at = emu.sym("_legendary") + i * 0x24
            emu.write32(at + 0x18, 1)
            emu.write32(at + 0x1C, 95 + 3 * i + 1)
        emu.write32(emu.sym("_warp_on"), 1)
        emu.write32(emu.sym("_money_on"), 1)
        extra = emu.thunk()
        emu.hook(extra, lambda e: 2, 0)                         # 2 of 5 bought: shown, no tick
        for i in range(2):
            emu.write32(emu.sym("_extra_owned") + 4 * i, extra)
        emu.write32(emu.sym("_upgrades_view"), 1)
        scene = emu.alloc(0x400)
        emu.write32(scene + 0x1C0, emu.alloc(0x40))
        emu.call(emu.sym("_on_draw"), scene)
        return draws


def compose_store(folder: Path, draws: list[tuple]) -> Image.Image:
    sheets = Sheets(folder)
    screen = Image.open(folder / "Images" / "Store_BG.jpg").convert("RGBA")
    for draw in draws:
        _kind, sheet, frame, x, y = draw
        layer = Image.new("RGBA", screen.size)
        layer.paste(sheets.frame(sheet, frame), (x, y))
        screen.alpha_composite(layer)
    return screen


def compose_storage(folder: Path) -> Image.Image:
    exe = (folder / "Plant Tycoon.exe").read_bytes()
    images = folder / "Images"
    sheets = Sheets(folder)
    screen = Image.open(images / "SeedBox_BG.jpg").convert("RGBA")
    drawer = Image.open(images / "addlSeedBox.png").convert("RGBA")
    level = 1                                                    # the Seventh and Eighth owned: two drawers
    for k, y in enumerate((201, 354)):
        if level >= k + 1:
            screen.alpha_composite(drawer, (239, y))
    seeds = {(0, 0): 5, (0, 1): 21, (0, 2): 40, (1, 0): 63, (2, 4): 77, (3, 9): 12, (4, 0): 30, (5, 3): 55}
    for (row, col), frame in seeds.items():
        if row < (level + 1) * 4:
            screen.alpha_composite(sheets.frame(0x2E, frame), (242 + 53 * col, 46 + 152 * (row // 4) + 34 * (row % 4)))
    for name, x in (("leftarrow.png", 338), ("rightarrow.png", 716)):
        arrow = Image.open(images / name).convert("RGBA")
        frame = arrow.crop((0, 0, arrow.height, arrow.height))
        screen.paste(frame, (x, -9), frame)
    button = Image.open(ROOT / "assets" / "plant_tycoon_sort_seeds" / "Images" / "sort_seeds_button.png").convert("RGBA")
    screen.alpha_composite(button.crop((0, 0, button.width // 3, button.height)), (396, 6))
    R.centred(screen, R.words(folder, exe, "Boxes 7-9"), 660, 9)
    return screen


def save(screen: Image.Image, name: str) -> Path:
    out = IMAGES_OUT / name
    out.parent.mkdir(parents=True, exist_ok=True)
    screen.convert("RGB").save(out, optimize=True)
    print(f"wrote {out.relative_to(ROOT)}")
    return out


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1])
    exe = (folder / "Plant Tycoon.exe").read_bytes()
    for text in ("Boxes 1-3", "Boxes 4-6", "Boxes 7-9", "Extra Seed Box 4 of 6", "Sold out", "Price: $ 1000"):
        R.words(folder, exe, text)                               # every label has its glyphs
    save(compose_store(folder, store_draws(chem_slots=0)), "extra-seed-box-store.png")
    save(compose_storage(folder), "seed-boxes-7-9-storage.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
