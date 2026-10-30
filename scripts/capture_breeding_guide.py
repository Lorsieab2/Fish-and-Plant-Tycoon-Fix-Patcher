"""Render the Breeding Guide's tabs to docs/images/breeding-guide-*.png.

Builds the window as tests/test_breeding_guide.py does, on the same small
synthetic Fish Tycoon save (no player's data), shows each tab on screen for a
moment and grabs it with Pillow. Run on Windows with a display:

    python scripts/capture_breeding_guide.py
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import struct
import sys
import tempfile
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402

import breeding_guide as bg  # noqa: E402
from test_breeding_guide import make_documents  # noqa: E402

OUT = ROOT / "docs" / "images"


def print_window(window) -> Image.Image:
    """The window's own pixels, by Windows' PrintWindow (works when the screen itself
    cannot be grabbed, such as a locked or remote session)."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = int(window.wm_frame(), 16)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(0)
    dc = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    gdi32.SelectObject(dc, bitmap)
    user32.PrintWindow(hwnd, dc, 2)                       # PW_RENDERFULLCONTENT
    header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(dc, bitmap, 0, height, buffer, ctypes.create_string_buffer(header), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(dc)
    user32.ReleaseDC(0, screen)
    return Image.frombuffer("RGB", (width, height), buffer.raw, "raw", "BGRX", 0, 1)


def grab(guide, name: str) -> Path:
    window = guide.window
    window.update()
    window.after(400)
    window.update()
    image = print_window(window)
    path = OUT / f"breeding-guide-{name}.png"
    image.save(path, optimize=True)
    print(path)
    return path


def select(guide, title: str) -> None:
    nb = guide.notebook
    titles = [nb.tab(t, "text") for t in nb.tabs()]
    nb.select(nb.tabs()[titles.index(title)])
    guide.window.update()


def pick_row(guide, sheet_id: str, name: str) -> None:
    tree = guide.trees[sheet_id]
    for item in tree.get_children():
        if tree.set(item, "c0") == name:
            tree.selection_set(item)
            tree.see(item)
            break
    guide.window.update()


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    with tempfile.TemporaryDirectory() as tmp:
        documents = make_documents(Path(tmp))
        settings = {"show_spoilers": False}
        guide = bg.open_window(root, "fish", settings=settings, documents=documents)
        guide.window.geometry("1180x800+20+20")
        guide.window.attributes("-topmost", True)
        select(guide, "Fins")
        pick_row(guide, "part:fin", "Greenfin")
        grab(guide, "fish-fins")
        select(guide, "Bodies")
        pick_row(guide, "part:body", "Spotanus")
        grab(guide, "fish-bodies")
        select(guide, "Discovered Species")
        pick_row(guide, "species", "Greenfin Spotanus")
        grab(guide, "fish-discovered-species")
        guide.spoilers_var.set(True)
        select(guide, "All Species")
        pick_row(guide, "species", "Canary Fire-Arrow")
        grab(guide, "fish-all-species")
        select(guide, "Breeding Calculator")
        names = [s.name for s in guide.calc_choices]
        guide.calc_boxes[0].current(names.index("Greenfin Spotanus"))
        guide.calc_boxes[1].current(names.index("Twin-Fin Spotanus"))
        guide.calc_effects_var.set("max")
        grab(guide, "fish-calculator")
        select(guide, "Have to Want")
        names = [s.name for s in guide.have_choices]
        guide.have_list.selection_clear(0, "end")
        for name in ("Silky Shark", "Pink Fatfish", "Greenfin Spotanus", "Twin-Fin Spotanus"):
            guide.have_list.selection_set(names.index(name))
        wants = [s.name for s in guide.want_choices]
        guide.want_box.current(wants.index("Speckled Leaffish"))
        guide.plan_effects_var.set("none")
        guide.plan()
        guide.wait_for_plan()
        grab(guide, "fish-have-to-want")
        guide.game_var.set("Plant Tycoon")
        select(guide, "Flowers")
        grab(guide, "plant-flowers")
        select(guide, "All Species")
        grab(guide, "plant-all-species")
        guide.close()
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
