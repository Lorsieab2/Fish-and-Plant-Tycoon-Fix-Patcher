"""Render the Extra Chemical Slots mockups from the game's own art and the DLLs' own drawing.

    python scripts/render_chem_slots_preview.py "<vanilla Plant Tycoon folder>"

writes, in docs/images:

* extra-chemical-slots-page-1.png and extra-chemical-slots-page-2.png: the greenhouse (main_bg.png,
  a pot on every table spot as scripts/render_extra_greenhouses_preview.py draws them) with the
  Tools box as the game and "Extra Chemical Slots.dll" draw it once the slots are bought. The
  DLL's own tray draw (0x428EFC) and the game's own tools draw (0x44DD70) and tray draw (0x416650)
  run in Unicorn on the vanilla executable (the emulated greenhouse of tests/test_chem_slots.py),
  and every picture they draw is composited from the game's sheets (the chemicals sheet is this
  mod's taller copy, as Store Upgrades and Items points it). "1/2" / "2/2" is set from the game's
  font (PTfontsmall.png) where the DLL writes it, white on a black shadow. Page 2 also shows one
  of the slots' tooltips ("Revival Potion / 2 doses left") under the mouse, as a plain box (the
  game draws its tooltips at run time; the box here only shows where and what).
* extra-chemical-slots-store.png: the Supplies store's Upgrades view as Store Upgrades and Items
  draws it (scripts/render_seed_boxes_preview.py's store_draws: its own on_draw, every item
  shown), with the Extra Chemical Slots item on the chemicals shelf's third row.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

import render_extra_greenhouses_preview as R  # noqa: E402
import render_seed_boxes_preview as S  # noqa: E402

IMAGES_OUT = ROOT / "docs" / "images"


def greenhouse_draws(page: int) -> tuple[list[tuple], list[tuple]]:
    """The tools' and the tray's draws, and the texts, with the slots bought and a few bottles."""
    import tempfile
    import store_emulator as E
    import test_chem_slots as T
    with tempfile.TemporaryDirectory() as tmp:
        dll, symbols = E.build_with_map("ftfp_chem_slots", T.DLL, Path(tmp))
        g = T.Game(types.SimpleNamespace(dll=dll, symbols=symbols))
        for k, (chemical, doses) in enumerate(((27, 3), (30, 1), (32, 2), (36, 3))):
            g.put(k, chemical, doses)
        for e, (chemical, doses) in enumerate(((31, 2), (28, 4), (39, 1), (37, 2), (29, 5), (38, 3), (33, 1), (34, 2))):
            g.put2(e, chemical, doses)
        if page:
            g.press(T.ARROW[0] + 8, T.ARROW[1] + 8)
        g.emu.hook(0x0041DDE0, lambda e: 0, 0)                      # the tools' upgrade levels
        g.emu.hook(0x0041DE00, lambda e: 0, 0)
        g.emu.hook(0x0041DE20, lambda e: 0, 0)
        g.emu.hook(0x0041DE40, lambda e: 0, 0)
        g.emu.write32(g.state + 0x57C, 1)                           # the third tool (the seed tray) owned
        tools = g.emu.alloc(8)
        g.emu.write32(tools, g.state)
        g.calls.clear()
        del g.emu.hooks[0x0044DD70]                                 # the game's own tools draw
        g.emu.call(symbols["@tools_draw@12"], 0xFFFFFFFF, ecx=tools)
        draws = [("sprite",) + c[1] for c in g.calls if c[0] == "draw"]
        draws += [("sprite",) + d for d in g.draw()]
        texts = [c[1] for c in g.calls if c[0] == "text"]
        return draws, texts


def word(folder: Path, exe: bytes, text: str, colour: tuple[int, int, int]) -> Image.Image:
    w = R.words(folder, exe, text)
    a = w.getchannel("A")
    solid = Image.new("RGBA", w.size, colour + (255,))
    solid.putalpha(a)
    return solid


def compose_greenhouse(folder: Path, page: int) -> Image.Image:
    exe = (folder / "Plant Tycoon.exe").read_bytes()
    images = folder / "Images"
    sheets = S.Sheets(folder)
    screen = Image.open(images / "main_bg.png").convert("RGBA")
    pots = Image.open(images / "pot.png").convert("RGBA")
    frame_h = pots.height // 7
    for row in range(3):
        for column in range(5):
            style = (row * 5 + column) % 6
            pot = pots.crop((0, style * frame_h, pots.width, (style + 1) * frame_h))
            screen.alpha_composite(pot, (323 + 93 * column - 28, 117 + 144 * row - 15))
    draws, texts = greenhouse_draws(page)
    for _kind, sheet, frame, x, y in draws:
        layer = Image.new("RGBA", screen.size)
        layer.paste(sheets.frame(sheet, frame), (x, y))
        screen.alpha_composite(layer)
    for text, x, y, colour in texts:
        rgb = (0, 0, 0) if colour == 0xFF000000 else (255, 255, 255)
        screen.alpha_composite(word(folder, exe, text, rgb), (x, y))
    if page:
        lines = ["Revival Potion", "2 doses left"]
        rendered = [word(folder, exe, line, (0, 0, 0)) for line in lines]
        w = max(r.width for r in rendered) + 10
        h = sum(r.height for r in rendered) + 8
        x, y = 186, 166                                             # beside the mouse over page 2's slot 4
        d = ImageDraw.Draw(screen)
        d.rectangle((x, y, x + w, y + h), fill=(255, 255, 225, 255), outline=(0, 0, 0, 255))
        at = y + 4
        for r in rendered:
            screen.alpha_composite(r, (x + 5, at))
            at += r.height
        hand = Image.open(images / "hand_open.png").convert("RGBA")
        hand = hand.crop(hand.getbbox())
        screen.alpha_composite(hand, (163, 150))
    return screen


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1])
    exe = (folder / "Plant Tycoon.exe").read_bytes()
    for text in ("1/2", "2/2", "Revival Potion", "2 doses left", "1 dose left"):
        R.words(folder, exe, text)                                  # every label has its glyphs
    for page in (0, 1):
        S.save(compose_greenhouse(folder, page), f"extra-chemical-slots-page-{page + 1}.png")
    S.save(S.compose_store(folder, S.store_draws((1, 1, 1, 1, 1, 1), chem_slots=0)), "extra-chemical-slots-store.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
