"""Supply slot tooltips (DS Store Items) and the extra supply slots' page number (Extra Supply Slots),
run in Unicorn against the vanilla and the Universal supply slots Fish Tycoon.exe with both DLLs
rebuilt from their sources (tests/test_supply_slots.py's rig).

* The page number: "1/3", "2/3", "3/3" under the slot arrows once the slots are bought, nothing before.
* A tooltip over every kind of slot: its name and what is left of it as the game will spend it
  (doses, the Unknown Chemical's uses, egg batches), the fish food by name only, the extra slots'
  items on pages 2-3, nothing over an empty slot, page 3's unused place, while a hint is up or
  while something is held; German names and counts; the hint's own box, clamped to the screen;
  the maximized window.
* The rope edge (v1.0.22): with the hint's real rope bars and the stock box code 0x423280 run as it
  is, every tooltip -- the one-line Fish Food too, every slot of every page -- gets its whole rope.
* One tooltip at a time (v1.0.22): at any mouse point on any page, at most one box, only the hovered
  slot's of the page shown, nothing from another page, nothing while the stock hint is up.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_supply_slots as T  # noqa: E402

E = T.E if T.HAVE_UNICORN else None

# The game's own strings for the stock supplies (string 0xAE + 2 x item), English and German.
NAMES = {0xAE: ("Ick Treatment", "Weissp\xfcnktchen-Medikament"), 0xB0: ("Fungal Treatment", "Pilzinfektions-Medikament"),
         0xB2: ("Fish Vitamins", "Fischvitamine"), 0xB4: ("Growth Hormone", "Wachstumshormone"),
         0xB6: ("Unknown Chemical", "Unbekannte Chemikalie"), 0xB8: ("Common Fish Eggs", "Gew\xf6hnliche Fischeier"),
         0xBA: ("Unusual Fish Eggs", "Ungew\xf6hnliche Fischeier"), 0xBC: ("Rare Fish Eggs", "Seltene Fischeier")}
FOOD = struct.pack("<7i", 0x17, 1, 0, 0x78, 0x6E, 0x19, 0xF)
CHAR_W = 9                                           # the stubbed hint font: 9 pixels a character
# 0x423280 draws its rope (bars 64 x 10 and 10 x 64, just outside the box) only around a box whose
# rope is at least 64 pixels each way (a box 44 wide), and its side bars (the left one down from the
# box's top, the right one up from its bottom) stay inside the rope's outline only for a box at least
# 64 - 10 = 54 tall.
ROPE_LONG, ROPE_SHORT = 64, 10
ROPE_MIN_W = ROPE_LONG - 2 * ROPE_SHORT
ROPE_MIN = ROPE_LONG - ROPE_SHORT


class TipRig(T.Rig):
    """The rig with DS Store Items as the main DLL and Extra Supply Slots beside it."""

    def __init__(self, universal: bool = False, owned: bool = True, german: bool = False,
                 slots_loaded: bool = True, exe: Path | None = None) -> None:
        super().__init__(universal, owned=owned, with_store=True, exe=exe)
        emu = self.emu
        ss = emu.symbols
        emu.write32(ss["_installed"], 1)
        self.w("_installed", 1)
        emu.write32(0x0045ABDC, self.state)
        lang = emu.alloc(4)
        emu.write32(lang, 1 if german else 0)
        emu.write32(0x0045B314, lang)
        # The text goes in the graphics' default font (0x408C30 with font 0: [[impl + 0x54]] + 0x34);
        # 0x45B26C is the hints' text colour, never written: 0, the default white.
        self.font = emu.alloc(16)
        graphics = emu.alloc(0x40)
        emu.write32(emu.read32(self.impl + 0x54), graphics)
        emu.write32(graphics + 0x34, self.font)
        emu.write32(0x0045B26C, 0)
        self.text_args: list[tuple[int, int]] = []
        emu.hook(0x00408C30, lambda e: self.calls.append(("text", e.cstring(e.arg(0)).decode("latin-1"),
                                                          e.arg(1), e.arg(2), e.arg(3)))
                 or self.text_args.append((e.arg(4), e.arg(5))) or 0, 24)
        exports = {"FtfpSupplySlotsShown": self.sym["_FtfpSupplySlotsShown@4"]}
        emu.hook_import("GetModuleHandleW", lambda e: 0x13000000 if slots_loaded and
                        e.wstring(e.arg(0)) == "Extra Supply Slots.dll" else 0, 4)
        emu.hook_import("GetProcAddress", lambda e: exports.get(e.cstring(e.arg(1)).decode(), 0), 8)
        table = emu.alloc(16)
        self.strings = {i: emu.text(NAMES[i][int(german)]) for i in NAMES}
        emu.hook(0x00427060, lambda e: table, 0)
        emu.hook(0x00427050, lambda e: self.strings.get(e.arg(0), emu.text("?")), 4)
        emu.hook(0x004023D0, lambda e: CHAR_W * len(e.cstring(e.arg(0)))
                 if e.uc.reg_read(T.X.UC_X86_REG_ECX) == self.font else 0, 8)
        # The hint object: its vtable[1] draws its box (0x423280) at a rectangle.
        self.boxes: list[tuple[int, ...]] = []
        hint, vtable = emu.alloc(0x40), emu.alloc(16)
        box = emu.thunk()
        emu.hook(box, lambda e: self.boxes.append(struct.unpack("<4i", e.uc.mem_read(e.arg(0), 16))) or 0, 4)
        emu.write32(vtable + 4, box)
        emu.write32(hint, vtable)
        emu.write32(emu.read32(self.impl + 0x44), hint)

    def tip(self, x: int, y: int, hint_shown: int = 0) -> list[str]:
        self.point = [x, y]
        self.calls.clear()
        self.boxes.clear()
        self.emu.call(self.emu.symbols["_slot_tooltip"], self.impl, hint_shown)
        return [c[1] for c in self.calls if c[0] == "text"]


def ready() -> bool:
    return T.ready() and T.STORE_DLL.is_file()


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and both DLLs")
class Tooltips(unittest.TestCase):
    def test_every_stock_supply(self) -> None:
        cases = (  # (universal, slot k, record, lines)
            (False, 1, T.record(0, 2, 1), ["Ick Treatment", "2 doses left"]),
            (False, 1, T.record(1, 1, 1), ["Fungal Treatment", "1 dose left"]),
            (False, 2, T.record(2, 3, 2), ["Fish Vitamins", "3 doses left"]),
            (False, 2, T.record(3, 3, 2), ["Growth Hormone", "3 doses left"]),
            (False, 2, T.record(4, 3, 2), ["Unknown Chemical", "1 use left"]),       # vanilla: one use
            (True, 2, T.record(4, 3, 2), ["Unknown Chemical", "3 uses left"]),
            (False, 3, T.record(5, 3, 3), ["Common Fish Eggs", "1 batch left"]),     # vanilla: one hatch
            (True, 3, T.record(6, 2, 3), ["Unusual Fish Eggs", "2 batches left"]),
            (True, 1, T.record(7, 1, 1), ["Rare Fish Eggs", "1 batch left"]),
            (False, 3, T.record(26, 1, 3), ["Common Fish Eggs", "1 batch left"]),    # the starter eggs
            (True, 3, T.record(26, 1, 3), ["Common Fish Eggs", "1 batch left"]),
        )
        for universal, k, rec, lines in cases:
            with self.subTest(universal=universal, k=k, item=rec[0]):
                rig = TipRig(universal)
                rig.put_stock(k, rec)
                self.assertEqual(rig.tip(*T.centre(k)), lines)
                width = max(len(s) for s in lines) * CHAR_W + 20
                self.assertEqual(len(rig.boxes), 1, "the hint's own box")
                left, top, right, bottom = rig.boxes[0]
                self.assertEqual((top, right - left, bottom - top), (60, width, max(ROPE_MIN, 12 + 20 * len(lines))))
                self.assertGreaterEqual(left, 12)
                self.assertLessEqual(right, 788)
                self.assertEqual(set(rig.text_args), {(0, 0)}, "the hints' colour, the default font")

    def test_the_fish_food_by_name_only(self) -> None:
        rig = TipRig()
        rig.put_stock(0, FOOD)
        self.assertEqual(rig.tip(*T.centre(0)), ["Fish Food"])
        self.assertEqual(rig.boxes[0][3] - rig.boxes[0][1], ROPE_MIN, "tall enough for the hint's rope")
        left, _, right, _ = rig.boxes[0]
        self.assertEqual((left, right - left), (12, len("Fish Food") * CHAR_W + 20), "on screen, the text inside")
        text = [c for c in rig.calls if c[0] == "text"][0]
        self.assertEqual(text[2:5], (left, right, 60 + (ROPE_MIN - 20) // 2), "the one line in the middle")

    def test_the_patcher_supplies(self) -> None:
        for universal in (False, True):
            for item, count, lines in ((T.RGH, 2, ["Radioactive Growth Hormone", "2 doses left"]),
                                       (T.REVIVAL, 1, ["Revival Potion", "1 dose left"]),
                                       (T.CLONA, 3, ["ClonaFish", "3 doses left"]),
                                       (T.MUTA_FIN, 3, ["Muta-Fin", "3 doses left"]),
                                       (T.MUTA_BODY, 1, ["Muta-Body", "1 dose left"]),
                                       (T.EXOTIC, 2, ["Exotic Fish Eggs", "2 batches left" if universal
                                                      else "1 batch left"])):
                with self.subTest(universal=universal, item=item):
                    rig = TipRig(universal)
                    rig.put_stock(T.NATIVE[item], T.record(item, count, T.NATIVE[item]))
                    self.assertEqual(rig.tip(*T.centre(T.NATIVE[item])), lines)

    def test_the_extra_slots_on_pages_2_and_3(self) -> None:
        rig = TipRig(True)
        rig.put_extra(1, T.record(T.RGH, 2))
        rig.put_extra(6, T.record(5, 3))
        rig.to_page(1)
        self.assertEqual(rig.tip(*T.centre(1)), ["Radioactive Growth Hormone", "2 doses left"])
        self.assertEqual(rig.tip(*T.centre(0)), [], "an empty extra slot")
        self.assertEqual(rig.boxes, [])
        rig.to_page(2)
        self.assertEqual(rig.tip(*T.centre(2)), ["Common Fish Eggs", "3 batches left"])
        self.assertEqual(rig.tip(*T.centre(3)), [], "page 3 has no fourth slot")
        rig.to_page(0)
        self.assertEqual(rig.tip(*T.centre(1)), ["Ick Treatment", "3 doses left"], "page 1: the stock slot")

    def test_nothing_over_an_empty_slot_or_off_the_slots(self) -> None:
        rig = TipRig()
        rig.put_stock(2, T.EMPTY)
        self.assertEqual(rig.tip(*T.centre(2)), [])
        for x, y in ((T.BOXES[0][0] - 1, 20), (55, 20), (T.BOXES[3][2] + 1, 20), (80, 49), (400, 300)):
            self.assertEqual(rig.tip(x, y), [], (x, y))
        self.assertEqual(rig.boxes, [])

    def test_nothing_while_a_hint_is_up_or_something_is_held(self) -> None:
        rig = TipRig()
        self.assertEqual(rig.tip(*T.centre(1), hint_shown=1), [])
        rig.pick_stock(2)
        self.assertEqual(rig.tip(*T.centre(1)), [], "a supply held")
        rig.let_go(*T.centre(2))
        rig.emu.write32(rig.state + 0x1E4E8, 3)
        self.assertEqual(rig.tip(*T.centre(1)), [], "a fish held")
        rig.emu.write32(rig.state + 0x1E4E8, 0xFFFFFFFF)
        rig.emu.write32(rig.impl + 0x28, 2)
        self.assertEqual(rig.tip(*T.centre(1)), [], "an ornament held")

    def test_german(self) -> None:
        rig = TipRig(True, german=True)
        rig.put_stock(1, T.record(0, 2, 1))
        rig.put_stock(2, T.record(4, 1, 2))
        rig.put_stock(3, T.record(7, 3, 3))
        rig.put_stock(0, FOOD)
        self.assertEqual(rig.tip(*T.centre(1)), ["Weissp\xfcnktchen-Medikament", "Noch 2 Dosen"])
        self.assertEqual(rig.tip(*T.centre(2)), ["Unbekannte Chemikalie", "Noch 1 Anwendung"])
        self.assertEqual(rig.tip(*T.centre(3)), ["Seltene Fischeier", "Noch 3 Gelege"])
        self.assertEqual(rig.tip(*T.centre(0)), ["Fischfutter"])
        rig.put_extra(0, T.record(T.REVIVAL, 1))
        rig.to_page(1)
        self.assertEqual(rig.tip(*T.centre(0)), ["Wiederbelebungstrank", "Noch 1 Dosis"])

    def test_without_extra_supply_slots(self) -> None:
        """DS Store Items alone: the stock four, from the game's own records."""
        rig = TipRig(slots_loaded=False)
        self.assertEqual(rig.tip(*T.centre(3)), ["Common Fish Eggs", "1 batch left"])

    def test_the_box_stays_on_screen(self) -> None:
        rig = TipRig()
        rig.put_stock(1, T.record(0, 3, 1))
        rig.tip(*T.centre(0 + 1))
        left = rig.boxes[0][0]
        self.assertEqual(left, max(4, 80 - (len("Ick Treatment") * CHAR_W + 20) // 2))
        rig.put_stock(0, FOOD)
        rig.tip(*T.centre(0))
        self.assertGreaterEqual(rig.boxes[0][0], 4)

    def test_maximized(self) -> None:
        import test_fish_window as W
        for cw, ch in ((1920, 1017), (1366, 705)):
            x, y, w, h = W.fit(cw, ch)
            gx, gy = T.centre(2)
            point = (W.to_picture(x + gx * w // 800 + 1, x, w, 800), W.to_picture(y + gy * h // 600 + 1, y, h, 600))
            rig = TipRig()
            self.assertEqual(rig.tip(*point), ["Growth Hormone", "3 doses left"], (cw, ch))


class RopeRig(TipRig):
    """TipRig with the game's own hint box: the hint object as 0x4231E0 builds it (its four rope bars,
    CUSTOMPOPUP_FTROPESTYLE_BAR_top/bottom/left/right, as images of their real sizes, and its fill
    colour) and its vtable[1] the stock 0x423280, run as it is. Only the drawing is Python: the
    fill (0x407940) and every picture drawn (0x408A40)."""

    BARS = {4: ("top", ROPE_LONG, ROPE_SHORT), 8: ("bottom", ROPE_LONG, ROPE_SHORT),
            0xC: ("left", ROPE_SHORT, ROPE_LONG), 0x10: ("right", ROPE_SHORT, ROPE_LONG)}

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        emu = self.emu
        hint, vtable = emu.alloc(0x40), emu.alloc(16)
        emu.write32(vtable + 4, 0x00423280)
        emu.write32(hint, vtable)
        self.bar_of: dict[int, str] = {}
        for offset, (name, w, h) in self.BARS.items():
            image, holder, surface = emu.alloc(8), emu.alloc(4), emu.alloc(0x10)
            emu.write32(surface + 8, w)
            emu.write32(surface + 0xC, h)
            emu.write32(holder, surface)
            emu.write32(image + 4, holder)
            emu.write32(hint + offset, image)
            self.bar_of[image] = name
        emu.write32(hint + 0x14, 0xFF404C50)
        emu.write32(emu.read32(self.impl + 0x44), hint)
        self.fills: list[tuple[int, ...]] = []
        emu.hook(0x00407900, lambda e: self.gfx, 0)
        self.gfx = emu.alloc(0x40)
        emu.hook(0x00407940, lambda e: self.fills.append(struct.unpack("<4i", e.uc.mem_read(e.arg(0), 16))) or 0, 8)

    def tip(self, x: int, y: int, hint_shown: int = 0) -> list[str]:
        self.fills.clear()
        return super().tip(x, y, hint_shown)

    def bars(self) -> dict[str, list[tuple[int, int]]]:
        out: dict[str, list[tuple[int, int]]] = {}
        for c in self.calls:
            if c[0] == "draw" and c[1] in self.bar_of:
                out.setdefault(self.bar_of[c[1]], []).append((c[2], c[3]))
        return out

    def box(self) -> tuple[int, int, int, int]:
        """The box the tooltip asked for: the fill is it, one pixel larger each way (0x423307)."""
        left, top, right, bottom = self.fills[0]
        return left + 1, top + 1, right - 1, bottom - 1


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and both DLLs")
class RopeEdge(unittest.TestCase):
    """The owner, v1.0.21: "the fish food is missing the rope border". The stock box drew only its fill
    around the one-line Fish Food box (32 pixels tall: its rope would be 52 < 64). Every tooltip now
    gets the whole rope, drawn by the game's own 0x423280."""

    def assert_roped(self, rig: RopeRig, what: str) -> None:
        """One box; its rope drawn by the stock code on all four sides, every pixel of the 10-pixel
        band around the box covered and no bar sticking out of it; the text inside."""
        self.assertEqual(len(rig.fills), 1, f"{what}: one box")
        left, top, right, bottom = rig.box()
        bars = rig.bars()
        self.assertEqual(set(bars), {"top", "bottom", "left", "right"}, f"{what}: the rope on every side")
        e = ROPE_SHORT
        ol, ot, orr, ob = left - e, top - e, right + e, bottom + e
        band = [bytearray(orr - ol) for _ in range(ob - ot)]
        for name, pieces in bars.items():
            w, h = (ROPE_LONG, e) if name in ("top", "bottom") else (e, ROPE_LONG)
            for x, y in pieces:
                self.assertTrue(ol <= x and x + w <= orr and ot <= y and y + h <= ob,
                                f"{what}: the {name} bar at {(x, y)} inside the rope's outline {(ol, ot, orr, ob)}")
                for row in range(y, y + h):
                    band[row - ot][x - ol:x - ol + w] = b"\1" * w
        holes = [(ol + c, ot + r) for r in range(ob - ot) for c in range(orr - ol)
                 if not band[r][c] and not (left <= ol + c < right and top <= ot + r < bottom)]
        self.assertEqual(holes[:5], [], f"{what}: the whole rope around the box")
        self.assertGreaterEqual(left - e, 0, f"{what}: the rope on screen")
        self.assertLessEqual(right + e, 800, f"{what}: the rope on screen")
        texts = [c for c in rig.calls if c[0] == "text"]
        for text in texts:
            self.assertEqual(text[2:4], (left, right), f"{what}: the text centred in the box")
            self.assertGreaterEqual(text[4], top, what)
            self.assertLessEqual(text[4] + 20, bottom, f"{what}: the text inside the box")

    def test_the_fish_food(self) -> None:
        for german in (False, True):
            rig = RopeRig(german=german)
            rig.put_stock(0, FOOD)
            self.assertEqual(rig.tip(*T.centre(0)), ["Fischfutter" if german else "Fish Food"])
            self.assert_roped(rig, "the fish food")
            left, top, right, bottom = rig.box()
            self.assertEqual(bottom - top, ROPE_MIN)

    def test_every_slot_on_every_page(self) -> None:
        rig = RopeRig(universal=True)
        rig.put_stock(0, FOOD)
        for e, it in enumerate((T.RGH, T.REVIVAL, T.CLONA, T.MUTA_FIN, T.MUTA_BODY, T.EXOTIC, 7)):
            rig.put_extra(e, T.record(it, 2))
        seen = 0
        for page in (0, 1, 2):
            rig.to_page(page)
            for p in range(4):
                lines = rig.tip(*T.centre(p))
                if not lines:
                    self.assertEqual((page, p), (2, 3), "only page 3's unused place has no tooltip")
                    continue
                self.assert_roped(rig, f"page {page + 1}, slot {p + 1}: {lines[0]}")
                seen += 1
        self.assertEqual(seen, 11)

    def test_a_narrow_name_still_has_its_rope(self) -> None:
        """A one-word name narrower than the rope's top bar: the box is as wide as the bar needs."""
        rig = RopeRig()
        rig.put_stock(0, FOOD)
        rig.emu.hook(0x004023D0, lambda e: 3, 8)                       # a tiny font
        rig.tip(*T.centre(0))
        self.assert_roped(rig, "a narrow box")
        left, top, right, bottom = rig.box()
        self.assertEqual((right - left, bottom - top), (ROPE_MIN_W, ROPE_MIN))

    def test_two_lines(self) -> None:
        rig = RopeRig()
        rig.put_stock(1, T.record(0, 2, 1))
        rig.tip(*T.centre(1))
        self.assert_roped(rig, "Ick Treatment")
        left, top, right, bottom = rig.box()
        self.assertEqual((top, bottom), (60, 60 + ROPE_MIN))
        self.assertEqual([c[4] for c in rig.calls if c[0] == "text"], [67, 87], "the two lines in the middle")

    def test_the_stock_box_left_only_the_fill_around_one_line(self) -> None:
        """The cause: the one-line box v1.0.19-21 drew (32 tall) got no rope from 0x423280 at all."""
        rig = RopeRig()
        rect = rig.emu.alloc(16)
        rig.emu.uc.mem_write(rect, struct.pack("<4i", 12, 60, 113, 92))
        rig.calls.clear()
        rig.emu.call(0x00423280, rect, ecx=rig.emu.read32(rig.emu.read32(rig.impl + 0x44)))
        self.assertEqual((len(rig.fills), rig.bars()), (1, {}))


@unittest.skipUnless(ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and both DLLs")
class OneTooltipAtATime(unittest.TestCase):
    """The owner, v1.0.21: "make sure the tooltips don't overlap each other from other pages". Over the
    whole top bar and the tank under it, on every page: at most one box at any mouse point, and only
    the hovered slot's of the page shown -- never a slot of another page, never the stock hint's too."""

    PAGES = {0: ("Fish Food", "Ick Treatment", "Growth Hormone", "Rare Fish Eggs"),
             1: ("Radioactive Growth Hormone", "Revival Potion", "ClonaFish", "Muta-Fin"),
             2: ("Muta-Body", "Exotic Fish Eggs", "Fungal Treatment", None)}

    def rig(self) -> RopeRig:
        rig = RopeRig(universal=True)
        rig.put_stock(0, FOOD)
        rig.put_stock(1, T.record(0, 2, 1))
        rig.put_stock(2, T.record(3, 2, 2))
        rig.put_stock(3, T.record(7, 2, 3))
        for e, it in enumerate((T.RGH, T.REVIVAL, T.CLONA, T.MUTA_FIN, T.MUTA_BODY, T.EXOTIC, 1)):
            rig.put_extra(e, T.record(it, 2))
        return rig

    def test_at_most_one_and_only_the_page_shown(self) -> None:
        rig = self.rig()
        for page, names in self.PAGES.items():
            rig.to_page(page)
            others = {n for pg, ns in self.PAGES.items() if pg != page for n in ns if n}
            for x in range(0, 260, 5):
                for y in range(0, 130, 6):
                    lines = rig.tip(x, y)
                    p = next((i for i, b in enumerate(T.BOXES) if b[0] <= x <= b[2] and b[1] <= y <= b[3]), None)
                    with self.subTest(page=page, x=x, y=y):
                        self.assertLessEqual(len(rig.fills), 1, "never two boxes")
                        self.assertEqual(sum(1 for c in rig.calls if c[0] == "hint"), 0, "no stock hint with it")
                        expect = names[p] if p is not None else None
                        if expect is None:
                            self.assertEqual((lines, rig.fills), ([], []), "nothing off a slot of this page")
                            continue
                        self.assertEqual(lines[0], expect, "the hovered slot of the page shown")
                        self.assertNotIn(lines[0], others, "nothing from another page")
                        left, _, right, _ = rig.box()
                        centre = (T.BOXES[p][0] + T.BOXES[p][2]) // 2
                        self.assertTrue(left <= centre <= right or left == 12, "under its own slot")

    def test_the_stock_hint_hides_it(self) -> None:
        """While the stock hint is up (0x417FD0 drew it) there is no tooltip at all, on any page."""
        rig = self.rig()
        for page in (0, 1, 2):
            rig.to_page(page)
            for p in range(4):
                self.assertEqual(rig.tip(*T.centre(p), hint_shown=1), [])
                self.assertEqual(rig.fills, [])

    def test_turning_the_page_under_the_mouse(self) -> None:
        """The mouse stays on a slot while the page turns: each frame shows that page's slot only."""
        rig = self.rig()
        for _ in range(2):
            for page in (0, 1, 2):
                rig.to_page(page)
                self.assertEqual(rig.tip(*T.centre(1))[0], self.PAGES[page][1])
                self.assertEqual(len(rig.fills), 1)


@unittest.skipUnless(T.ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and the built DLL")
class PageNumber(unittest.TestCase):
    def rig(self, owned: bool = True) -> T.Rig:
        rig = T.Rig(owned=owned)
        self.images: dict[int, str] = {}

        def image(e) -> int:
            this = e.uc.reg_read(T.X.UC_X86_REG_ECX)
            self.images[this] = e.cstring(e.arg(0)).decode()
            return this
        rig.emu.hook(0x00409540, image, 4)
        rig.emu.hook(0x004095B0, lambda e: 17, 0)
        return rig

    def drawn(self, rig: T.Rig) -> list[tuple[str, int, int]]:
        rig.calls.clear()
        rig.emu.call(rig.sym["@draw_hook@8"], ecx=rig.impl)
        return [(self.images[c[1]], c[2], c[3]) for c in rig.calls
                if c[0] == "draw" and self.images.get(c[1], "").startswith("SupplyPage")]

    def test_each_page(self) -> None:
        rig = self.rig()
        for page in (0, 1, 2, 0):
            rig.to_page(page)
            self.assertEqual(self.drawn(rig), [(f"SupplyPage{page + 1}.png", 213 - 17 // 2, 46)])

    def test_not_before_the_purchase(self) -> None:
        self.assertEqual(self.drawn(self.rig(owned=False)), [])

    def test_clear_of_the_arrows_slot_4_and_the_label(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("needs Pillow")
        for n in (1, 2, 3):
            img = Image.open(T.ROOT / "assets" / "fish_tycoon_supply_slots" / "Images" / f"SupplyPage{n}.png")
            left, top = 213 - img.width // 2, 46
            right, bottom = left + img.width - 1, top + img.height - 1
            self.assertGreater(top, T.ARROW_DOWN_Y + T.ARROW_H - 1, "under the lower arrow")
            self.assertLessEqual(bottom, 56, "inside the bar")
            self.assertGreater(left, T.BOXES[3][2], "right of slot 4")
            self.assertLess(right, 227, "left of the Magic Breeds row and its label")


class TooltipSite(unittest.TestCase):
    """DS Store Items' new site, the hints' draw call in the tank screen's overlay (0x41D127), is written
    by no other companion and by no Fix Patcher patch, and holds the stock call in every build."""

    def test_no_overlap(self) -> None:
        ranges = T.site_ranges()
        store = ranges.pop("ftfp_ds_store")
        self.assertIn((0x41D127, 0x41D12C), store)
        for name, sites in ranges.items():
            for a, b in sites:
                self.assertFalse(a < 0x41D12C and 0x41D127 < b, f"{name}'s site 0x{a:X}")
        try:
            import build_ds_fish_headers as H
        except ImportError:
            self.skipTest("needs capstone")
        for start, end in H.fix_patcher_ranges():
            self.assertFalse(start < 0x41D12C and 0x41D127 < end, f"a Fix Patcher patch at 0x{start:X}")

    @unittest.skipUnless(T.ready(), "needs the vanilla Fish Tycoon.exe")
    def test_stock_in_the_enable_all_build(self) -> None:
        import json
        manifest = json.loads(T.MANIFEST.read_text(encoding="utf-8"))
        data = T.built_exe({s["id"] for s in manifest["settings"]}).read_bytes()
        at = 0x41D127 - 0x401000 + 0x1000
        self.assertEqual(data[at:at + 5], bytes.fromhex("E8A4AEFFFF"), "call 0x417FD0")


if __name__ == "__main__":
    unittest.main()
