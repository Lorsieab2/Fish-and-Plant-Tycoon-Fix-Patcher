"""The tank and greenhouse counts are drawn on top: a whole frame of each game's
own paint, in Unicorn, with the expansion DLLs loaded beside the counts.

Each test maps the vanilla executable and the real companion DLLs (rebuilt
from their sources, each byte-for-byte its committed copy; every DLL after the
first relocated to a base of its own), starts them in the startup loader's
order with their own FtfpStartup (so every site and slot is written, and
chained, exactly as in the game), and then paints one frame with the game's
own screen paint:

  * Fish Tycoon: 0x40AC90 on the tank screen -- its draw (0x422010, with
    "3 extra tanks"' and "Multiple ornaments"' wrappers inside it), its
    controls, its overlay (0x41CF20, what the hand holds), the controls'
    overlays; with Extra Tanks.dll and Multiple Ornaments.dll;
  * Plant Tycoon: 0x40B6B0 on the greenhouse screen -- its background
    (0x4257A0), its controls (the buttons, Extra Greenhouses' arrows), its
    overlay (0x428E70: the tables, pots, plants, bugs, tools, then what the
    hand holds, then the bottom bar), the controls' overlays; with Extra
    Greenhouses.dll, which starts Greenhouse Counts.dll itself.

Every function the paint calls (the game's sprite, picture and text draws
among them) is a Python hook that records who called it, so the test sees
every draw of the frame in order, the DLLs' own included.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

try:
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs
    import store_emulator as E
except ImportError:          # Unicorn or Capstone is not installed
    E = None

FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


# ------------------------------------------------------------------ PE images

def _directory(data: bytes, index: int) -> tuple[int, int]:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    return struct.unpack_from("<II", data, pe + 24 + 96 + index * 8)


def _rva_to_raw(sections, rva: int) -> int:
    for start, raw, size in sections:
        if start <= rva < start + size:
            return raw + rva - start
    raise KeyError(hex(rva))


class Image:
    """A companion DLL: rebuilt from its source (as the committed copy), mapped at `base`."""

    def __init__(self, name: str, project: str, committed: Path, base: int, out: Path) -> None:
        self.name = name
        (out / project).mkdir(parents=True, exist_ok=True)
        dll, symbols = E.build_with_map(project, committed, out / project)
        self.data = dll.read_bytes()
        preferred, self.size, self.sections, self.imports_rva = E.pe_image(self.data)
        self.base = base
        delta = base - preferred
        self.symbols = {k: v + delta if preferred <= v < preferred + self.size else v for k, v in symbols.items()}
        self.delta = delta
        self.exports: dict[str, int] = {}
        rva, _size = _directory(self.data, 0)
        if rva:
            at = _rva_to_raw(self.sections, rva)
            names = struct.unpack_from("<I", self.data, at + 0x18)[0]
            functions, name_table, ordinals = struct.unpack_from("<III", self.data, at + 0x1C)
            for i in range(names):
                name_rva = struct.unpack_from("<I", self.data, _rva_to_raw(self.sections, name_table) + 4 * i)[0]
                raw = _rva_to_raw(self.sections, name_rva)
                export = self.data[raw:self.data.index(b"\0", raw)].decode()
                ordinal = struct.unpack_from("<H", self.data, _rva_to_raw(self.sections, ordinals) + 2 * i)[0]
                function = struct.unpack_from("<I", self.data, _rva_to_raw(self.sections, functions) + 4 * ordinal)[0]
                self.exports[export] = base + function

    def contains(self, address: int) -> bool:
        return self.base <= address < self.base + self.size

    def map(self, emu, imports: dict[str, tuple]) -> None:
        """Map the image at its base, apply its relocations and point its imports at hooked thunks."""
        uc = emu.uc
        uc.mem_map(self.base, (self.size + 0xFFF) & ~0xFFF)
        uc.mem_write(self.base, self.data[:0x1000])
        for rva, raw, raw_size in self.sections:
            uc.mem_write(self.base + rva, self.data[raw:raw + raw_size])
        rva, size = _directory(self.data, 5)
        at, end = rva, rva + size
        while at < end:
            page, block = struct.unpack("<II", uc.mem_read(self.base + at, 8))
            if block == 0:
                break
            for i in range((block - 8) // 2):
                entry = struct.unpack("<H", uc.mem_read(self.base + at + 8 + 2 * i, 2))[0]
                if entry >> 12 == 3:                                       # IMAGE_REL_BASED_HIGHLOW
                    where = self.base + page + (entry & 0xFFF)
                    emu.write32(where, emu.read32(where) + self.delta)
            at += block
        at = self.imports_rva
        while True:
            lookup, _t, _f, _name, iat = struct.unpack("<5I", uc.mem_read(self.base + at, 20))
            if lookup == 0 and iat == 0:
                return
            slot = 0
            while True:
                entry = emu.read32(self.base + (lookup or iat) + slot * 4)
                if entry == 0:
                    break
                name = emu.cstring(self.base + entry + 2).decode("ascii")
                thunk = emu.thunk()
                emu.write32(self.base + iat + slot * 4, thunk)
                if name in imports:
                    handler, pop = imports[name]
                    emu.hook(thunk, handler, pop)
                else:
                    emu.hook(thunk, lambda e, n=name, m=self.name: (_ for _ in ()).throw(
                        AssertionError(f"{m} called the unhooked import {n}")), 0)
                slot += 1
            at += 20


def _pops(exe_data: bytes, address: int) -> int:
    """What a game function pops on return (its `ret n`), following a tail jump."""
    base, _size, sections, _imports = E.pe_image(exe_data)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for _hop in range(4):
        raw = _rva_to_raw(sections, address - base)
        for ins in md.disasm(exe_data[raw:raw + 0x4000], address):
            if ins.mnemonic == "ret":
                return int(ins.op_str, 16) if ins.op_str else 0
            if ins.mnemonic == "jmp" and ins.op_str.startswith("0x"):
                address = int(ins.op_str, 16)
                break
        else:
            raise AssertionError(hex(address))
    raise AssertionError(hex(address))


def _callees(exe_data: bytes, start: int, end: int) -> set[int]:
    """Every direct call target in [start, end) of the game's code."""
    base, _size, sections, _imports = E.pe_image(exe_data)
    raw = _rva_to_raw(sections, start - base)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    out = set()
    for ins in md.disasm(exe_data[raw:raw + end - start], start):
        if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
            out.add(int(ins.op_str, 16))
    return out


# --------------------------------------------------------------------- world

class World:
    """The vanilla game and its companion DLLs in one emulator; every hooked call is recorded
    as (name, the function, the caller's return address)."""

    FOLDER = ""

    def __init__(self, exe: Path, images: list[Image]) -> None:
        self.exe_data = exe.read_bytes()
        emu = self.emu = E.Emulator(exe, None, {})
        emu.uc.mem_map(0, 0x1000)                         # fs:[0] for __try's SEH frame
        self.images = images
        self.loaded: set[str] = set()
        self.present: set[str] = {image.name for image in images}
        self.log: list[tuple[str, int, int]] = []
        imports = {
            "VirtualProtect": (self._virtual_protect, 16),
            "FlushInstructionCache": (lambda e: 1, 12),
            "GetCurrentProcess": (lambda e: 0xFFFFFFFF, 0),
            "GetModuleFileNameW": (self._module_file_name, 12),
            "GetFileAttributesW": (self._file_attributes, 4),
            "LoadLibraryW": (lambda e: self._load(e.wstring(e.arg(0))), 4),
            "LoadLibraryExW": (lambda e: self._load(e.wstring(e.arg(0))), 12),
            "GetProcAddress": (self._get_proc, 8),
            "GetModuleHandleW": (self._module_handle, 4),
            "GetModuleHandleExW": (self._module_handle_ex, 12),
            "VirtualQuery": (self._virtual_query, 12),
            "GetPrivateProfileIntW": (lambda e: e.arg(2), 16),
            "WritePrivateProfileStringW": (lambda e: 1, 16),
            "CreateFileW": (lambda e: 0xFFFFFFFF, 28),
            "WriteFile": (lambda e: 0, 20),
            "CloseHandle": (lambda e: 1, 4),
            "lstrcmpiW": (lambda e: 0 if e.wstring(e.arg(0)).lower() == e.wstring(e.arg(1)).lower() else 1, 8),
            "GetLastError": (lambda e: 0, 0),
            "SetLastError": (lambda e: 0, 4),
        }
        for image in images:
            image.map(emu, imports)

    # ---------------------------------------------------------- imports
    def image_of(self, address: int) -> Image | None:
        return next((image for image in self.images if image.contains(address)), None)

    def by_name(self, path: str) -> Image | None:
        name = path.rsplit("\\", 1)[-1]
        return next((image for image in self.images if image.name == name), None)

    def _virtual_protect(self, e) -> int:
        e.write32(e.arg(3), 0x20)
        return 1

    def _module_file_name(self, e) -> int:
        image = next((i for i in self.images if i.base == e.arg(0)), None)
        path = self.FOLDER + (image.name if image else "Game.exe")
        e.uc.mem_write(e.arg(1), path.encode("utf-16-le") + b"\0\0")
        return len(path)

    def _file_attributes(self, e) -> int:
        path = e.wstring(e.arg(0))
        return 0x20 if path.startswith(self.FOLDER) and path[len(self.FOLDER):] in self.present else 0xFFFFFFFF

    def _load(self, path: str) -> int:
        image = self.by_name(path)
        if image is None or not path.startswith(self.FOLDER):
            return 0
        self.loaded.add(image.name)
        return image.base

    def _get_proc(self, e) -> int:
        image = next((i for i in self.images if i.base == e.arg(0)), None)
        return image.exports.get(e.cstring(e.arg(1)).decode(), 0) if image else 0

    def _module_handle(self, e) -> int:
        if e.arg(0) == 0:
            return 0x400000
        image = self.by_name(e.wstring(e.arg(0)))
        return image.base if image is not None and image.name in self.loaded else 0

    def _module_handle_ex(self, e) -> int:
        address = e.arg(1)
        image = self.image_of(address)
        module = image.base if image else 0x400000 if 0x400000 <= address < 0x500000 else 0
        e.write32(e.arg(2), module)
        return 1 if module else 0

    def _virtual_query(self, e) -> int:
        address, info = e.arg(0), e.arg(1)
        image = self.image_of(address)
        base = image.base if image else 0x400000 if 0x400000 <= address < 0x500000 else address & ~0xFFF
        e.uc.mem_write(info, struct.pack("<7I", address & ~0xFFF, base, 0x20, 0x1000, 0x1000, 0x20, 0x1000000))
        return 28

    # ---------------------------------------------------------- the game
    def start(self, name: str) -> int:
        image = self.by_name(name)
        self.loaded.add(image.name)
        for other in self.images:                                  # what DllMain would have set
            if "_self_module" in other.symbols:
                self.emu.write32(other.symbols["_self_module"], other.base)
        return self.emu.call(image.exports["FtfpStartup"])

    def record(self, address: int, name: str, pop: int, result=0) -> None:
        def handler(e) -> int:
            back = e.read32(e.uc.reg_read(E.X.UC_X86_REG_ESP))
            self.log.append((name, address, back))
            return result(e) if callable(result) else result
        self.emu.hook(address, handler, pop)

    def record_callees(self, start: int, end: int, names: dict[int, str], results: dict | None = None,
                       keep: tuple[int, ...] = ()) -> None:
        """Every function the game's code in [start, end) calls becomes a recorded hook."""
        results = results or {}
        for target in sorted(_callees(self.exe_data, start, end)):
            if target in keep or target in self.emu.hooks:
                continue
            self.record(target, names.get(target, f"game {target:#x}"), _pops(self.exe_data, target),
                        results.get(target, 0))

    def control(self, label: str) -> int:
        """A screen control: its draw (+0x18) and its overlay (+0x1C) are recorded."""
        table = self.emu.alloc(0x40)
        for slot, what in ((0x18, "draw"), (0x1C, "overlay")):
            thunk = self.emu.thunk()
            self.record(thunk, f"{label} {what}", 0)
            self.emu.write32(table + slot, thunk)
        control = self.emu.alloc(0x40)
        self.emu.write32(control, table)
        return control

    def screen(self, table: int, size: int, controls: list[int]) -> int:
        """A screen object for the game's paint: its table, its node (visible, its controls)."""
        scene = self.emu.alloc(size)
        self.emu.uc.mem_write(scene, bytes(size))
        node = self.emu.alloc(0x40)
        self.emu.uc.mem_write(node, bytes(0x40))
        self.emu.write8(node, 1)
        head = 0
        for control in reversed(controls):
            link = self.emu.alloc(8)
            self.emu.write32(link, control)
            self.emu.write32(link + 4, head)
            head = link
        self.emu.write32(node + 0x18, head)
        self.emu.write32(scene, table)
        self.emu.write32(scene + 4, node)
        return scene

    # ---------------------------------------------------------- the frame
    def counts_draws(self, counts: Image) -> list[int]:
        return [i for i, (name, _f, back) in enumerate(self.log) if name == "text" and counts.contains(back)]


# --------------------------------------------------------------- Fish Tycoon

FISH_FOLDER = "C:\\Games\\Fish Tycoon\\Fish Tycoon Fix Patcher DLLs\\"
FISH_STATE_SIZE = 0x1E600
TANK_DRAW, TANK_DRAW_END = 0x422010, 0x422095
TANK_BUTTONS, TANK_BUTTONS_END = 0x4216E0, 0x4218C1
TANK_OVERLAY, TANK_OVERLAY_END = 0x41CF20, 0x41D13E
FISH_GRAPHICS, FISH_FONT = 0x00C0FFEE, 0x0F0F1000


@_needs(FISH_EXE)
class FishCountsOnTopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        cls.spec = [
            ("Extra Tanks.dll", "ftfp_extra_tanks", ROOT / "assets" / "fish_tycoon_extra_tanks" / "Extra Tanks.dll"),
            ("Multiple Ornaments.dll", "ftfp_ornaments",
             ROOT / "assets" / "fish_tycoon_ornaments" / "Multiple Ornaments.dll"),
            ("Tank Counts.dll", "ftfp_tank_counts", ROOT / "assets" / "fish_tycoon_counts" / "Tank Counts.dll"),
        ]
        cls.built = [Image(name, project, committed, 0x50000000 + 0x2000000 * i, out)
                     for i, (name, project, committed) in enumerate(cls.spec)]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def world(self) -> World:
        w = World(FISH_EXE, self.built)
        w.FOLDER = FISH_FOLDER
        emu = w.emu
        # The startup loader: Extra Tanks.dll (which loads Multiple Ornaments.dll), then Tank Counts.dll.
        self.assertEqual(w.start("Extra Tanks.dll"), 1)
        self.assertIn("Multiple Ornaments.dll", w.loaded)
        self.assertEqual(w.start("Tank Counts.dll"), 1)
        self.tanks, self.counts = w.by_name("Extra Tanks.dll"), w.by_name("Tank Counts.dll")

        # The game's own functions the paint reaches: every call in the tank screen's draw, its
        # buttons and its overlay is recorded (the drawing primitives by name).
        names = {0x41D140: "background", 0x41D1B0: "snail", 0x415E50: "fish", 0x41D340: "decorations",
                 0x41DE20: "creatures", 0x41EE60: "equipment and ornaments", 0x4162F0: "bubbles",
                 0x4216E0: "top bar, panels and tank buttons", 0x415E60: "held fish",
                 0x41D600: "Multiple Ornaments' copies"}
        w.record(0x408A40, "picture", 0xC)
        w.record(0x408AA0, "cell", 0x10)
        w.record(0x408B80, "text", 0x14)
        w.record(0x408C30, "text", 0x14)
        w.record(0x418210, "font manager", 0, 0x0F0F0000)
        w.record(0x4181F0, "font", 4, FISH_FONT)
        w.record(0x417FD0, "messages shown", 0, 1)                    # no queued message this frame
        for start, end in ((TANK_DRAW, TANK_DRAW_END), (TANK_OVERLAY, TANK_OVERLAY_END)):
            w.record_callees(start, end, names)
        w.record(0x41D600, names[0x41D600], 0)
        w.record(TANK_BUTTONS, names[TANK_BUTTONS], 0)                # reached by a jmp (0x42208E)
        # Extra Tanks' art (its images are game objects: new, then the picture or grid constructor).
        w.record(0x42A793, "new", 0, lambda e: e.alloc(max(e.arg(0), 4)))
        w.record(0x409540, "image", 4, lambda e: e.uc.reg_read(E.X.UC_X86_REG_ECX))
        w.record(0x4096C0, "grid", 0xC, lambda e: e.uc.reg_read(E.X.UC_X86_REG_ECX))
        w.record(0x402060, "mouse", 0, 0)
        w.record(0x402080, "mouse down", 0, 0)
        w.record(0x41BCA0, "sprite grid", 4, 0x5000)
        w.record(0x41BE70, "sprite", 4, 0x5000)

        state = self.state = emu.alloc(FISH_STATE_SIZE)
        emu.uc.mem_write(state, bytes(FISH_STATE_SIZE))
        emu.write32(state + 0x1E4E8, 7)                               # a fish in the hand (slot 7)
        emu.write32(state + 0x140, 1)                                 # the Cleaning Snail
        emu.write32(0x45ABDC, state)                                  # the game's state
        for slot, age in enumerate((25, 25, 8, 3)):                   # fish to count
            at = state + 0x390 + slot * 0x288
            emu.write32(at, 1000)
            emu.write32(at + 0x0C, age)
            emu.write32(at + 0x3C, 100)
            emu.write32(at + 0x4C, 3)
        impl = self.impl = emu.alloc(0x200)
        emu.uc.mem_write(impl, bytes(0x200))
        emu.write32(impl + 0x34, state)
        emu.write32(impl + 0x38, emu.alloc(0x40))                     # the sprites
        emu.write32(impl + 0x3C, emu.alloc(0x40))                     # the fish view
        emu.write32(impl + 0x40, emu.alloc(0x40))                     # the bubbles
        emu.write32(impl + 0x44, emu.alloc(0x40))                     # the messages
        emu.write32(impl + 0x54, FISH_GRAPHICS)
        emu.write32(impl + 0x1C, 99)                                  # no tool in the hand
        emu.write32(impl + 0x28, 99)                                  # no ornament in the hand
        for b, left in enumerate((513, 610, 707)):                   # the tank buttons (0x41CDD4)
            emu.uc.mem_write(impl + 0x58 + b * 0x10, struct.pack("<4i", left, 2, left + 85, 54))
        self.scene = w.screen(0x443A54, 0x40, [w.control("button")])
        emu.write32(self.scene + 8, impl)
        # The extra tanks: all three bought, Tank Five "For sale".
        sym = self.tanks.symbols
        emu.write32(sym["_owner"], state)
        emu.write32(sym["_owned"], 3)
        emu.write32(sym["_selling"], 4)
        return w

    def show(self, w: World, tank: int) -> None:
        """Tank 1-6 on screen: 1-3 the stock tanks, 4-6 the extra tanks (in Tank 1's place)."""
        sym = self.tanks.symbols
        stock, extra = (tank - 1, -1) if tank <= 3 else (0, tank - 4)
        w.emu.write32(self.state + 0x384, stock)
        w.emu.write32(sym["_shown"], extra & 0xFFFFFFFF)
        w.emu.write32(sym["_page"], 1 if extra >= 0 else 0)

    def frame(self, w: World) -> list[tuple[str, int, int]]:
        w.log.clear()
        w.emu.call(0x40AC90, ecx=self.scene)                          # the game's paint of a screen
        return list(w.log)

    def test_the_counts_are_drawn_over_everything_in_the_tank_on_every_tank(self) -> None:
        w = self.world()
        ornaments = w.by_name("Multiple Ornaments.dll")
        for tank in range(1, 7):
            with self.subTest(tank=tank):
                self.show(w, tank)
                log = self.frame(w)
                mine = w.counts_draws(self.counts)
                self.assertTrue(mine, "the counts are drawn")
                texts = [log[i] for i in mine]
                self.assertEqual(len(texts), 2 * 3, "the button and two lines, each with its shadow")
                first, last = mine[0], mine[-1]
                self.assertEqual(mine, list(range(first, last + 1)), "the counts are drawn in one go")
                before, after = log[:first], log[last + 1:]

                # Everything the tank screen's draw makes, stock and the expansions', comes first.
                def drawn_by(entry, *ranges) -> bool:
                    return any(lo <= entry[2] < hi for lo, hi in ranges)
                tank_screen = ((TANK_DRAW, TANK_DRAW_END), (TANK_BUTTONS, TANK_BUTTONS_END),
                               (self.tanks.base, self.tanks.base + self.tanks.size),
                               (ornaments.base, ornaments.base + ornaments.size))
                self.assertEqual([e for e in after if drawn_by(e, *tank_screen)], [])
                names = [e[0] for e in before]
                for name in ("background", "snail", "fish", "decorations", "creatures", "equipment and ornaments",
                             "bubbles", "top bar, panels and tank buttons", "button draw"):
                    self.assertIn(name, names, name)
                if tank >= 4:
                    # Extra Tanks' arrows, its buttons, the tank's name and For sale button.
                    extras = [e for e in before if e[0] in ("picture", "cell") and self.tanks.contains(e[2])]
                    self.assertGreaterEqual(len(extras), 4, extras)
                # After them: only the stock overlay (what the hand holds) and the controls' overlays.
                self.assertTrue(all(drawn_by(e, (TANK_OVERLAY, TANK_OVERLAY_END)) or e[0] == "button overlay"
                                    for e in after), after)
                self.assertIn("held fish", [e[0] for e in after], "the fish in the hand is drawn over the counts")

    def test_the_tank_screen_draws_before_its_controls_and_overlay(self) -> None:
        """The game's own order (0x40AC90): the screen's draw, its controls, its overlay, the
        controls' overlays; the overlay slot is where the counts are."""
        w = self.world()
        self.show(w, 5)
        log = self.frame(w)
        order = [e[0] for e in log if e[0] in ("background", "button draw", "held fish", "button overlay")]
        self.assertEqual(order, ["background", "button draw", "held fish", "button overlay"])
        self.assertEqual(w.emu.read32(0x443A70), self.counts.symbols["@on_overlay@8"])

    def test_the_screensaver_draws_no_counts(self) -> None:
        w = self.world()
        self.show(w, 5)
        w.emu.write8(self.state + 0x1E4F9, 1)
        self.frame(w)
        self.assertEqual(w.counts_draws(self.counts), [])


# -------------------------------------------------------------- Plant Tycoon

PLANT_FOLDER = "C:\\Games\\Plant Tycoon\\Plant Tycoon Fix Patcher DLLs\\"
PLANT_STATE_SIZE = 0x63E70
GH_OVERLAY, GH_HELD, GH_HELD_END, GH_OVERLAY_END = 0x428E70, 0x4291D2, 0x4295EE, 0x4296FB
PLANT_GRAPHICS = 0x00C0FFEE


@_needs(PLANT_EXE)
class PlantCountsOnTopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        cls.spec = [
            ("Extra Greenhouses.dll", "ftfp_extra_greenhouses",
             ROOT / "assets" / "plant_tycoon_greenhouses" / "Extra Greenhouses.dll"),
            ("Greenhouse Counts.dll", "ftfp_greenhouse_counts",
             ROOT / "assets" / "plant_tycoon_counts" / "Greenhouse Counts.dll"),
        ]
        cls.built = [Image(name, project, committed, 0x50000000 + 0x2000000 * i, out)
                     for i, (name, project, committed) in enumerate(cls.spec)]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def world(self, held: int = 3) -> World:
        w = World(PLANT_EXE, self.built)
        w.FOLDER = PLANT_FOLDER
        w.present.add("Extra Greenhouses.ini")                       # the setting is on
        emu = w.emu
        state = self.state = emu.alloc(PLANT_STATE_SIZE)
        emu.uc.mem_write(state, bytes(PLANT_STATE_SIZE))
        # The startup loader loads Extra Greenhouses.dll, which starts Greenhouse Counts.dll first.
        self.assertEqual(w.start("Extra Greenhouses.dll"), 1)
        self.assertIn("Greenhouse Counts.dll", w.loaded)
        self.greenhouses, self.counts = w.by_name("Extra Greenhouses.dll"), w.by_name("Greenhouse Counts.dll")
        names = {0x4257A0: "background", 0x4208F0: "sprite", 0x4092B0: "centred text", 0x4092A0: "text",
                 0x44CC20: "money", 0x44CDE0: "money box", 0x41B1C0: "timed message"}
        w.record(0x4257A0, "background", 0)
        w.record(0x407A90, "graphics", 0, PLANT_GRAPHICS)
        w.record(0x4092A0, "text", 0x14)
        w.record(0x4092B0, "centred text", 0x14)
        w.record(0x44CA70, "string", 4, lambda e: e.text("text"))
        w.record(0x44F30B, "sprintf", 0, 0)
        w.record_callees(GH_OVERLAY, GH_OVERLAY_END, names, keep=(0x44ECC5,))

        emu.write32(0x49333C, state)                                  # the game's state
        emu.write32(state + 0x56C, held)                              # what the hand holds (3: a tool)
        for k, age in enumerate((25.0, 22.0, 3.0)):                   # plants to count
            at = state + 0x2188 + k * 0x5600
            emu.uc.mem_write(at + 0x10, struct.pack("<f", age))
            emu.write32(at + 0x24, 90)
            emu.write32(at + 0x4C, 1)
        self.scene = w.screen(0x469220, 0x400, [w.control("button")])
        emu.write32(self.scene + 0x68, state)
        emu.write8(self.scene + 8, 1)                                 # the mouse is over the greenhouse
        emu.write32(self.scene + 0x0C, 0x150)                         # at y 336
        emu.write32(self.greenhouses.symbols["_owned"], 5)            # all five extra greenhouses bought
        return w

    def frame(self, w: World) -> list[tuple[str, int, int]]:
        w.log.clear()
        w.emu.call(0x40B6B0, ecx=self.scene)                          # the game's paint of a screen
        return list(w.log)

    def test_the_counts_are_drawn_over_everything_in_the_greenhouse_on_every_greenhouse(self) -> None:
        w = self.world()
        for shown in range(6):
            with self.subTest(greenhouse=shown + 1):
                w.emu.write32(self.greenhouses.symbols["_shown"], shown)
                log = self.frame(w)
                mine = w.counts_draws(self.counts)
                self.assertEqual(len(mine), 2 * 2, "the button and the line, each with its shadow")
                first, last = mine[0], mine[-1]
                self.assertEqual(mine, list(range(first, last + 1)), "the counts are drawn in one go")
                before, after = log[:first], log[last + 1:]
                names = [e[0] for e in before]
                self.assertIn("background", names)
                self.assertIn("button draw", names, "the buttons and Extra Greenhouses' arrows")
                # (a return address is the instruction after the call: 0x4291D2 ends the last scene call)
                scene = [e for e in log if GH_OVERLAY < e[2] <= GH_HELD]      # tables, pots, plants, bugs, tools
                self.assertGreaterEqual(len(scene), 18)
                self.assertTrue(all(e in before for e in scene), "everything in the greenhouse is under the counts")
                held = [e for e in log if GH_HELD < e[2] <= GH_HELD_END]
                self.assertIn("sprite", [e[0] for e in held])
                self.assertTrue(all(e in after for e in held), "what the hand holds is over the counts")
                # After the counts: what the hand holds, the bottom bar's money and news line and the
                # timed messages, the controls' overlays, and Extra Greenhouses' greenhouse name.
                label = [e for e in after if self.greenhouses.contains(e[2])]
                self.assertEqual([e[0] for e in label], ["graphics", "centred text"])
                for entry in after:
                    self.assertTrue(GH_HELD < entry[2] <= GH_OVERLAY_END or entry[0] == "button overlay"
                                    or entry in label, entry)

    def test_the_greenhouse_name_and_the_counts_never_overlap(self) -> None:
        """Extra Greenhouses draws the greenhouse's name after the whole overlay, centred at
        (510, 26); with its arrows shown the lines start at y 62 and the button is at (646, 4),
        clear of it."""
        w = self.world()
        w.emu.write32(self.greenhouses.symbols["_shown"], 5)
        self.frame(w)
        labels = []
        w.record(0x4092B0, "centred text", 0x14, lambda e: labels.append(
            (e.cstring(e.arg(0)).decode(), e.arg(1), e.arg(2))) or 0)
        texts = []
        w.record(0x4092A0, "text", 0x14, lambda e: texts.append((e.cstring(e.arg(0)).decode(), e.arg(1), e.arg(2))) or 0)
        self.frame(w)
        name = [label for label in labels if label[0].startswith("Greenhouse")]
        self.assertEqual(name, [("Greenhouse 6 of 6", 510, 26)])
        width = 9 * len(name[0][0])                                   # PTfontsmall is narrower than 9 px a glyph
        name_box = (510 - width // 2, 26, 510 + width // 2, 26 + 21)
        for text, x, y in texts:
            box = (x, y, x + 9 * len(text), y + 21)
            self.assertTrue(box[2] < name_box[0] or box[0] > name_box[2] or box[3] <= name_box[1]
                            or box[1] >= name_box[3], (text, x, y))


if __name__ == "__main__":
    unittest.main()
