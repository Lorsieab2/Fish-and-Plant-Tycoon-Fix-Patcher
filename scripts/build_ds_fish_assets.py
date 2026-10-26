"""Build the DS Fish sprite sheets from the Fish Tycoon DS sprite exports.

The DS draws each fish from one flat side view: a 64x32 body plus a 32x32
top and bottom fin, placed by a per-(body, fin) offset table. The PC draws an
18-frame turn from per-gene sheets, so this script generates PC-layout sheets
for the seven DS-only bodies and fins (exe genes 23-29, DS indices 21-27):

    FISH_<gene>_body_Grid.png   770x150, 7x3 cells of 110x50
    FISH_<gene>_bot_Grid.png    780x70, 13x2 cells of 60x35
    FISH_<gene>_top_Grid.png    780x70, 13x2 cells of 60x35
    FISH_DS_teen_Grid.png       792x140, one 18-frame row per DS body
    FISH_DS_adult_dead_Grid.png 770x50, one dead adult per DS body

and data/ds_fish_layout.json with each DS fin's alpha and a fin anchor for
every (body, fin) pair that has a DS gene. The companion DLL writes those
anchors in place of the game's per-body ones (0x4111E0), so a DS fin sits
where the DS game draws it on any body, PC or DS, and a PC fin sits where the
DS draws it on a DS body. PC x PC pairs keep the game's own anchors.

The turn is faked from the single DS side view. Frame widths follow the PC
sheets: frames 0-5 face left and narrow from the tail, 6-11 repeat mirrored
(head edge fixed, as on the PC, so fins stay attached), 12-14 turn mirrored
toward head-on and 15-17 come back unmirrored, centred where the PC centres
them. Fin cells follow the PC convention measured from all 21 PC fin sheets:
top fins sit on the cell's bottom edge and bottom fins hang from its top edge,
left-aligned when the body faces left and right-aligned and mirrored when it
faces right. Teen fish are the body frames shrunk, and dead fish one body
image, exactly as on the PC: the game draws neither with separate fins.

Usage: python scripts/build_ds_fish_assets.py "<DS dump>/graphics/fish_sprites" "<vanilla Fish Tycoon folder>"
"""

from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "fish_tycoon_ds" / "Images"
LAYOUT = ROOT / "data" / "ds_fish_layout.json"

DS_FIRST = 21          # first DS-only index
EXE_FIRST = 23         # its exe gene (21 is the seahorse sprite slot, 22 the seahorse body)
COUNT = 7
DS_GENES = 28
SCALE = 1.58           # mean PC/DS body width ratio over the 21 shared bodies

BODY_CELL = (110, 50)
FIN_CELL = (60, 35)
TEEN_CELL = (44, 20)

# Body width per frame as a fraction of frame 0, and the head-on frames'
# centres relative to frame 0's, both medians of the 21 PC body sheets.
BODY_WIDTH = [1.00, 0.97, 0.94, 0.92, 0.91, 0.90,
              1.00, 0.97, 0.94, 0.92, 0.91, 0.90,
              0.81, 0.67, 0.53, 0.53, 0.67, 0.81]
HEAD_ON_SHIFT = {12: 7.0, 13: 9.5, 14: 9.5, 15: -10.5, 16: -10.5, 17: -8.0}
FIN_WIDTH = [1.0] * 12 + [0.8, 0.5, 0.4, 0.4, 0.5, 0.8]
MIRRORED = [False] * 6 + [True] * 9 + [False] * 3
# 0x4145F0 draws the body at fish y + (0x38 - h) / 2, h = rec+0x64 = body cell
# height (50, set from the cell rect at 0x413EFD / 0x4156CB), but the fins at
# fish y + anchor y: the body sits 3 px below the anchors' origin.
BODY_DY = (0x38 - BODY_CELL[1]) // 2
# A left-facing fish (frames 0-5) has its fins at fish x + 50 - anchor x (0x414878).
FIN_MIRROR_X = 0x32
FIN_ALPHA = 210        # the PC's most common fin alpha; the DS has no fin alpha


def exe_gene(ds_index: int) -> int:
    return ds_index if ds_index < DS_FIRST else ds_index - DS_FIRST + EXE_FIRST


def load(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def one(folder: Path, pattern: str) -> Path:
    found = sorted(folder.glob(pattern))
    if len(found) != 1:
        raise SystemExit(f"Expected one {pattern} in {folder}, found {len(found)}")
    return found[0]


def scaled(image: Image.Image, scale: float) -> Image.Image:
    image = image.crop(image.getbbox())
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.LANCZOS)


def cell(image: Image.Image, k: int, size: tuple[int, int], cols: int) -> Image.Image:
    x, y = (k % cols) * size[0], (k // cols) * size[1]
    return image.crop((x, y, x + size[0], y + size[1]))


def body_frames(body: Image.Image) -> tuple[list[Image.Image], dict]:
    """The 18 body cells, and where the art sits in frame 0 (for the anchors)."""
    box = body.getbbox()
    scale = min(SCALE, BODY_CELL[0] / (box[2] - box[0]), BODY_CELL[1] / (box[3] - box[1]))
    art = scaled(body, scale)
    left0 = (BODY_CELL[0] - art.width) // 2
    top = (BODY_CELL[1] - art.height) // 2
    cells = []
    for k, (width, mirrored) in enumerate(zip(BODY_WIDTH, MIRRORED)):
        frame = art.resize((max(1, round(art.width * width)), art.height), Image.LANCZOS)
        if mirrored:
            frame = frame.transpose(Image.FLIP_LEFT_RIGHT)
        if k < 6:                       # facing left: the head edge stays put
            left = left0
        elif k < 12:                    # mirrored: the head edge is the right one
            left = BODY_CELL[0] - left0 - frame.width
        else:                           # head-on: centred where the PC centres it
            left = round(BODY_CELL[0] / 2 + HEAD_ON_SHIFT[k] - frame.width / 2)
        image = Image.new("RGBA", BODY_CELL)
        image.alpha_composite(frame, (left, top))
        cells.append(image)
    return cells, {"left": left0, "top": top, "scale": scale, "ds_left": box[0], "ds_top": box[1]}


def fin_frames(fin: Image.Image, top: bool) -> list[Image.Image]:
    art = scaled(fin, SCALE)
    art = art.crop((0, 0, min(art.width, FIN_CELL[0]), min(art.height, FIN_CELL[1])))
    cells = []
    for width, mirrored in zip(FIN_WIDTH, MIRRORED):
        frame = art.resize((max(1, round(art.width * width)), art.height), Image.LANCZOS)
        if mirrored:
            frame = frame.transpose(Image.FLIP_LEFT_RIGHT)
        x = FIN_CELL[0] - frame.width if mirrored else 0
        y = FIN_CELL[1] - frame.height if top else 0
        image = Image.new("RGBA", FIN_CELL)
        image.alpha_composite(frame, (x, y))
        cells.append(image)
    return cells


def sheet(cells: list[Image.Image], size: tuple[int, int], cols: int, rows: int) -> Image.Image:
    out = Image.new("RGBA", (size[0] * cols, size[1] * rows))
    for k, image in enumerate(cells):
        out.alpha_composite(image, ((k % cols) * size[0], (k // cols) * size[1]))
    return out


def pair_anchors(offsets: dict, bodies: dict, fins: dict) -> list[dict]:
    """A fin anchor for every pair with a DS gene, from the DS offset table.

    The DS places each fin sprite at (body + offset). That is mapped onto the
    body's frame-0 art in its PC-layout sheet (scaled by the body's own
    PC/DS width ratio), and the anchor is chosen so the fin's frame-0 art
    lands there by its attaching edge: a top fin's left and bottom, a bottom
    fin's left and top. Frames 0-5 (facing left) draw a fin at fish x + 50 -
    anchor x and frames 6-11 at fish x + anchor x (0x41484A, 0x4147B0); the
    mirrored cells make the two agree."""
    rows = []
    for b in range(DS_GENES):
        for f in range(DS_GENES):
            if b < DS_FIRST and f < DS_FIRST:
                continue
            o, body, fin = offsets[(b, f)], bodies[b], fins[f]
            anchor = []
            for part, dx, dy in (("top", "top_dx", "top_dy"), ("bottom", "bottom_dx", "bottom_dy")):
                ds_box, pc_box = fin[part]
                if ds_box is None or pc_box is None:      # finless: nothing is drawn
                    anchor += [0, 0]
                    continue
                x = body["left"] + body["scale"] * (int(o[dx]) + ds_box[0] - body["ds_left"])
                edge = 3 if part == "top" else 1
                y = BODY_DY + body["top"] + body.get("scale_y", body["scale"]) * (int(o[dy]) + ds_box[edge] - body["ds_top"])
                anchor += [round(FIN_MIRROR_X - (x - pc_box[0])), round(y - pc_box[edge])]
            rows.append({"body": exe_gene(b), "fin": exe_gene(f), "anchor": anchor})
    return rows


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    ds, game = Path(sys.argv[1]), Path(sys.argv[2])
    with open(ds / "fin_offsets.csv", newline="", encoding="utf-8") as handle:
        offsets = {(int(r["body_idx"]), int(r["fin_idx"])): r for r in csv.DictReader(handle)}
    with zipfile.ZipFile(game / "Assets" / "ft.dat") as archive:
        pc = {name.lower(): archive.read(name) for name in archive.namelist() if name.lower().startswith("fish_")}

    def pc_sheet(gene: int, part: str) -> Image.Image:
        return Image.open(io.BytesIO(pc[f"fish_{gene:02d}_{part}_grid.png"])).convert("RGBA")

    OUT.mkdir(parents=True, exist_ok=True)
    bodies, fins = {}, {}
    layout = {"exe_first": EXE_FIRST, "ds_first": DS_FIRST, "bodies": [], "fins": []}
    teen_rows, dead_cells = [], []
    for d in range(DS_GENES):
        gene = exe_gene(d)
        body_ds = load(one(ds / "bodies", f"{d:02d}_*.png"))
        fin_ds = {part: load(one(ds / "fins", f"{d:02d}_*_{part}.png")) for part in ("top", "bottom")}
        if d >= DS_FIRST:
            cells, placed = body_frames(body_ds)
            sheet(cells, BODY_CELL, 7, 3).save(OUT / f"FISH_{gene}_body_Grid.png")
            teen_rows.append([c.resize(TEEN_CELL, Image.LANCZOS) for c in cells])
            dead = scaled(load(one(ds / "dead_bodies", f"{d:02d}_*_dead.png")), placed["scale"])
            dead = dead.transpose(Image.FLIP_LEFT_RIGHT)      # PC dead fish face right
            dead = dead.crop((0, 0, min(dead.width, BODY_CELL[0]), min(dead.height, BODY_CELL[1])))
            dead_cell = Image.new("RGBA", BODY_CELL)
            dead_cell.alpha_composite(dead, ((BODY_CELL[0] - dead.width) // 2, (BODY_CELL[1] - dead.height) // 2))
            dead_cells.append(dead_cell)
            top_cells, bot_cells = fin_frames(fin_ds["top"], True), fin_frames(fin_ds["bottom"], False)
            sheet(top_cells, FIN_CELL, 13, 2).save(OUT / f"FISH_{gene}_top_Grid.png")
            sheet(bot_cells, FIN_CELL, 13, 2).save(OUT / f"FISH_{gene}_bot_Grid.png")
            fin_cell0 = {"top": top_cells[0], "bottom": bot_cells[0]}
            name = one(ds / "bodies", f"{d:02d}_*.png").stem.split("_", 1)[1].replace("_", " ")
            fin_name = one(ds / "fins", f"{d:02d}_*_top.png").stem.split("_", 1)[1].rsplit("_", 1)[0].replace("_", " ")
            layout["bodies"].append({"gene": gene, "ds_index": d, "name": name})
            layout["fins"].append({"gene": gene, "ds_index": d, "name": fin_name, "alpha": FIN_ALPHA})
        else:
            pc_box = cell(pc_sheet(gene, "body"), 0, BODY_CELL, 7).getbbox()
            ds_box = body_ds.getbbox()
            # PC bodies have their own proportions: map the DS offsets by width
            # across and by height up and down.
            placed = {"left": pc_box[0], "top": pc_box[1], "scale": (pc_box[2] - pc_box[0]) / (ds_box[2] - ds_box[0]),
                      "scale_y": (pc_box[3] - pc_box[1]) / (ds_box[3] - ds_box[1]),
                      "ds_left": ds_box[0], "ds_top": ds_box[1]}
            fin_cell0 = {"top": cell(pc_sheet(gene, "top"), 0, FIN_CELL, 13),
                         "bottom": cell(pc_sheet(gene, "bot"), 0, FIN_CELL, 13)}
        bodies[d] = placed
        fins[d] = {part: (fin_ds[part].getbbox(), fin_cell0[part].getbbox()) for part in ("top", "bottom")}

    layout["pair_anchors"] = pair_anchors(offsets, bodies, fins)

    # Head-on frames (12-17) place fins at body + 44 - anchor, which only suits
    # the PC's own anchors. For a pair with a DS gene the DLL instead keeps each
    # fin at the same fraction along the body as on frame 0; it needs every
    # sheet's art extent (left, right) on frame 0 and the head-on frames.
    frames = [0, 12, 13, 14, 15, 16, 17]

    def extents(image: Image.Image, size: tuple[int, int], cols: int) -> list[list[int]]:
        out = []
        for k in frames:
            box = cell(image, k, size, cols).getbbox()
            out.append([box[0], box[2]] if box else [0, 0])
        return out

    geometry = {}
    for d in range(DS_GENES):
        gene = exe_gene(d)
        get = (lambda part: load(OUT / f"FISH_{gene}_{part}_Grid.png")) if d >= DS_FIRST else (lambda part: pc_sheet(gene, part))
        geometry[str(gene)] = {"body": extents(get("body"), BODY_CELL, 7),
                               "top": extents(get("top"), FIN_CELL, 13),
                               "bot": extents(get("bot"), FIN_CELL, 13)}
    layout["head_on"] = {"frames": frames, "extents": geometry}
    sheet([c for row in teen_rows for c in row], TEEN_CELL, 18, COUNT).save(OUT / "FISH_DS_teen_Grid.png")
    sheet(dead_cells, BODY_CELL, COUNT, 1).save(OUT / "FISH_DS_adult_dead_Grid.png")
    LAYOUT.write_text(json.dumps(layout, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {len(list(OUT.glob('*.png')))} sheets to {OUT.relative_to(ROOT).as_posix()} and "
          f"{len(layout['pair_anchors'])} pair anchors to {LAYOUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
