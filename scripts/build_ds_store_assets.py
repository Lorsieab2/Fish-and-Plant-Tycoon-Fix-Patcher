"""Build the DS store items' art from the DS session's renders.

    python scripts/build_ds_store_assets.py "<DS dump>/graphics/fish_sprites/ds_exclusive_animals" "<vanilla Fish Tycoon folder>"

Writes assets/fish_tycoon_ds_store/Images/:

  DS_PUFFER_Grid.png, DS_STINGRAY_Grid.png, DS_EEL_Grid.png
      tank companions, 6x3 cells, frames 0-17 in the Golden Seahorse's layout
      (and the fish's): 0-5 a swim loop facing left, 6-11 the same mirrored,
      12-17 the turn (narrowing, mirrored 12-14, back 15-17)
  DS_PUFFER_PUFF_Grid.png
      the puffer swimming puffed up, 4x2 cells of the puffer's cell size: the
      DS's 4 puff-up frames facing left, then the same mirrored. The DLL
      plays them every so often while it swims (the owner's call).
  DS_EEL_ROCK.png, DS_EEL_HOME_BACK_Grid.png, DS_EEL_HOME_FRONT_Grid.png
      the eel's rock and, for an eel at home, the parts of it behind and in
      front of the rock (back, rock, front at one top-left = the DS in-rock
      animation), 16 frames
  ITEM_DS_PUFFER.png, ITEM_DS_STINGRAY.png, ITEM_DS_EEL.png,
  ITEM_FISHEGGS_EXOTIC.png, TOOL_FISHEGGS_EXOTIC.png
      store icons (and the exotic eggs' cursor), the size of the stock icons
  SuppliesUpgradesButton.png
      the Upgrades button: a text button on the store's own bottom bar, a
      3-frame strip like the stock buttons

and data/ds_store_layout.json (cell sizes, button position) for the DLL's
headers.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
LAYOUT = ROOT / "data" / "ds_store_layout.json"

TURN_WIDTH = [0.81, 0.67, 0.53, 0.53, 0.67, 0.81]
BUTTON_POS = (440, 551)
BUTTON_SIZE = (100, 50)
ICON_BOX = (80, 60)          # the net cells are about 85 wide; stock icons are up to 69
# The DS in-rock cycle (moray_eel_back/front, 32 frames): the frames the eel idles on in the
# cave mouth, and its action burst (it ducks, peeks, lunges and snaps out with its mouth open,
# then is back in at 1). In the frames where the DS shows it behind the rock, it is drawn whole
# in front of it (decided, user).
HOME_IDLE = list(range(1, 14))
HOME_ACTION = list(range(14, 32)) + [0]
HOME_IN_FRONT = {15, 21, 26, 27, 31}
EGG_HUE = 0.36          # the user's green, distinct from the orange Common Eggs

COMPANIONS = {
    # name: (source folder, frame picks for the 6-frame swim loop, for the
    # 6-frame turn (None: the first swim frame), scale)
    # The puffer's 4 DS frames are its puff-up: it swims deflated and puffs
    # up while it turns.
    "PUFFER": ("puffer_fish", [0, 0, 0, 0, 0, 0], [1, 2, 3, 3, 2, 1], 1.10),
    "STINGRAY": ("stingray_side", [0, 1, 3, 4, 5, 7], None, 0.60),
    "EEL": ("moray_eel_swim", [0, 3, 5, 8, 11, 13], None, 0.37),
}


def frames_in(folder: Path) -> list[Image.Image]:
    files = sorted(p for p in folder.glob("*.png") if p.stem[-2:].isdigit())
    if not files:
        raise SystemExit(f"No frames in {folder}")
    return [Image.open(p).convert("RGBA") for p in files]


def scaled(image: Image.Image, scale: float) -> Image.Image:
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)


def sheet(cells: list[Image.Image], size: tuple[int, int], cols: int) -> Image.Image:
    rows = (len(cells) + cols - 1) // cols
    out = Image.new("RGBA", (size[0] * cols, size[1] * rows))
    for k, image in enumerate(cells):
        out.alpha_composite(image, ((k % cols) * size[0], (k // cols) * size[1]))
    return out


def companion(source: Path, picks: list[int], turn: list[int] | None, scale: float) -> tuple[Image.Image, tuple[int, int]]:
    frames = frames_in(source)
    # One crop box for every frame, so the loop does not jitter.
    union = None
    for f in frames:
        box = f.getbbox()
        union = box if union is None else (min(union[0], box[0]), min(union[1], box[1]),
                                           max(union[2], box[2]), max(union[3], box[3]))
    loop = [scaled(frames[i].crop(union), scale) for i in picks]
    turning = [scaled(frames[i].crop(union), scale) for i in turn] if turn else [loop[0]] * 6
    cell = (loop[0].width + 4, loop[0].height + 4)
    cells = []
    for k in range(18):
        art = loop[k % 6] if k < 12 else turning[k - 12]
        if k >= 12:
            art = art.resize((max(1, round(art.width * TURN_WIDTH[k - 12])), art.height), Image.LANCZOS)
        if 6 <= k <= 14:
            art = art.transpose(Image.FLIP_LEFT_RIGHT)
        image = Image.new("RGBA", cell)
        image.alpha_composite(art, ((cell[0] - art.width) // 2, (cell[1] - art.height) // 2))
        cells.append(image)
    return sheet(cells, cell, 6), cell


def puff_sheet(source: Path, scale: float, cell: tuple[int, int]) -> Image.Image:
    """The puffer's 4 puff-up frames, left then mirrored, cropped and scaled
    exactly as its swim sheet is (so the two line up)."""
    frames = frames_in(source)
    union = None
    for f in frames:
        box = f.getbbox()
        union = box if union is None else (min(union[0], box[0]), min(union[1], box[1]),
                                           max(union[2], box[2]), max(union[3], box[3]))
    cells = []
    for mirrored in (False, True):
        for f in frames:
            art = scaled(f.crop(union), scale)
            if mirrored:
                art = art.transpose(Image.FLIP_LEFT_RIGHT)
            image = Image.new("RGBA", cell)
            image.alpha_composite(art, ((cell[0] - art.width) // 2, (cell[1] - art.height) // 2))
            cells.append(image)
    return sheet(cells, cell, len(frames))


def icon(image: Image.Image) -> Image.Image:
    image = image.crop(image.getbbox())
    scale = min(ICON_BOX[0] / image.width, ICON_BOX[1] / image.height, 1.0)
    art = scaled(image, scale)
    out = Image.new("RGBA", ICON_BOX)
    out.alpha_composite(art, ((ICON_BOX[0] - art.width) // 2, ICON_BOX[1] - art.height))
    return out


def tint(image: Image.Image, hue: float) -> Image.Image:
    import colorsys
    a = np.asarray(image.convert("RGBA")).astype(float) / 255
    flat = a[..., :3].reshape(-1, 3)
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in flat])
    hsv[:, 0] = hue
    hsv[:, 1] = np.clip(hsv[:, 1] * 1.3 + 0.1 * (hsv[:, 1] > 0.08), 0, 1)
    rgb = np.array([colorsys.hsv_to_rgb(*p) for p in hsv]).reshape(a.shape[0], a.shape[1], 3)
    return Image.fromarray((np.dstack([rgb, a[..., 3]]) * 255).round().astype("uint8"), "RGBA")


def upgrades_button(background: Image.Image) -> Image.Image:
    """The Upgrades button: a text button, "Upgrades" lettered on the store's
    own bottom bar at BUTTON_POS in the stock lettering (white with a dark
    rim; gold on hover; pressed 1 px down), as a 3-frame strip like the stock
    buttons. (The user: "Or even a text button.")"""
    bg = background.convert("RGB")
    bg = bg.crop((0, 0, bg.width, bg.height + 1))            # the stock buttons run one row past the screen
    bar = bg.crop((BUTTON_POS[0], BUTTON_POS[1], BUTTON_POS[0] + BUTTON_SIZE[0], BUTTON_POS[1] + BUTTON_SIZE[1]))
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 17)
    strip = Image.new("RGB", (BUTTON_SIZE[0] * 3, BUTTON_SIZE[1]))
    for f, (colour, drop) in enumerate((((255, 255, 255), 0), ((255, 222, 110), 0), ((225, 205, 160), 1))):
        frame = bar.copy()
        draw = ImageDraw.Draw(frame)
        text = "Upgrades"
        box = draw.textbbox((0, 0), text, font=font)
        x = (BUTTON_SIZE[0] - (box[2] - box[0])) // 2 - box[0]
        y = (BUTTON_SIZE[1] - (box[3] - box[1])) // 2 - box[1] + drop
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                if abs(dx) + abs(dy) <= 3:
                    draw.text((x + dx, y + dy), text, font=font, fill=(60, 15, 15))
        draw.text((x, y), text, font=font, fill=colour)
        strip.paste(frame, (f * BUTTON_SIZE[0], 0))
    return strip


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, game = Path(sys.argv[1]), Path(sys.argv[2])
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        names = {n.lower(): n for n in archive.namelist()}

        def stock(name: str) -> Image.Image:
            return Image.open(io.BytesIO(archive.read(names[name.lower()])))

        background = stock("supplyshop_bg_out.bmp")
        rare_item, rare_tool = stock("item_fisheggs_rare.png"), stock("tool_fisheggs_rare.png")
    OUT.mkdir(parents=True, exist_ok=True)
    layout = {"button": list(BUTTON_POS), "button_size": list(BUTTON_SIZE), "companions": {}}

    first_frames = {}
    for name, (folder, picks, turn, scale) in COMPANIONS.items():
        image, cell = companion(src / folder, picks, turn, scale)
        image.save(OUT / f"DS_{name}_Grid.png")
        layout["companions"][name] = {"cell": list(cell), "cols": 6, "rows": 3}
        first_frames[name] = image.crop((0, 0, cell[0], cell[1]))
    puff_sheet(src / COMPANIONS["PUFFER"][0], COMPANIONS["PUFFER"][3],
               tuple(layout["companions"]["PUFFER"]["cell"])).save(OUT / "DS_PUFFER_PUFF_Grid.png")

    # The eel's rock and the eel at home: 16 of the 32 in-rock frames.
    scale = 0.9
    rock = scaled(Image.open(src / "moray_eel_rock.png").convert("RGBA"), scale)
    rock.save(OUT / "DS_EEL_ROCK.png")
    backs = [scaled(f, scale) for f in frames_in(src / "moray_eel_back")]
    fronts = [scaled(f, scale) for f in frames_in(src / "moray_eel_front")]
    cell = rock.size
    for i in HOME_IN_FRONT:                      # the whole eel on the front layer
        whole = backs[i].copy()
        whole.alpha_composite(fronts[i])
        backs[i], fronts[i] = Image.new("RGBA", whole.size), whole
    picks = HOME_IDLE + HOME_ACTION
    backs, fronts = [backs[i] for i in picks], [fronts[i] for i in picks]
    sheet(backs, cell, 4).save(OUT / "DS_EEL_HOME_BACK_Grid.png")
    sheet(fronts, cell, 4).save(OUT / "DS_EEL_HOME_FRONT_Grid.png")
    # The cave mouth, where the eel's head shows while it idles: a press there pulls it out.
    layout["eel_home"] = {"cell": list(cell), "cols": 4, "rows": -(-len(picks) // 4), "frames": len(picks),
                          "idle": len(HOME_IDLE), "action": len(HOME_ACTION), "head_box": [60, 55, 115, 115]}

    inrock = frames_in(src / "moray_eel")[0]
    icon(first_frames["PUFFER"]).save(OUT / "ITEM_DS_PUFFER.png")
    icon(frames_in(src / "stingray_top")[0]).save(OUT / "ITEM_DS_STINGRAY.png")   # the user: from above
    icon(inrock).save(OUT / "ITEM_DS_EEL.png")
    tint(rare_item, EGG_HUE).save(OUT / "ITEM_FISHEGGS_EXOTIC.png")
    tint(rare_tool, EGG_HUE).save(OUT / "TOOL_FISHEGGS_EXOTIC.png")
    upgrades_button(background).save(OUT / "SuppliesUpgradesButton.png")

    LAYOUT.write_text(json.dumps(layout, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {len(list(OUT.glob('*.png')))} images to {OUT.relative_to(ROOT).as_posix()}; layout {layout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
