"""Extra Chemical Slots ("Extra chemical slots", Plant Tycoon): a second page of 8 chemical slots.

Everything runs in Unicorn on the vanilla Plant Tycoon.exe with "Extra Chemical Slots.dll" rebuilt
from its committed source (tests/store_emulator.py): the DLL installs itself (FtfpStartup), and
the game's own code runs the greenhouse press (0x426040), the put-back (0x4244C0), the tray's
add / room / dose functions (0x416410, 0x4164B0, 0x416540), the tray draw (0x416650) and the
chemical use's tail (0x42720B).  "Store Upgrades and Items.dll" (the store item, the save events,
the trash of its four chemicals and the setting-off fallback) runs in its own emulator, and once
beside this DLL (relocated) for the trash.  Only drawing, sounds, strings, tooltips and the file
system are Python hooks.
"""

from __future__ import annotations

import json
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

import ds_fish_loader  # noqa: E402

EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
DLL = ROOT / "assets" / "plant_tycoon_chem_slots" / "Extra Chemical Slots.dll"
UPGRADES_DLL = ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll"
SOURCE = ROOT / "native" / "ftfp_chem_slots" / "ftfp_chem_slots.c"
SITES_H = ROOT / "native" / "ftfp_chem_slots" / "chem_slots_sites.h"
MANIFEST = ROOT / "data" / "plant_manifest.json"
SHEET = ROOT / "assets" / "plant_tycoon_upgrades" / "Images" / "Chemicals_Grid_upgrades.png"

STATE_SIZE = 0x64000
TRAY, HELD, SELECTED = 0x53F84, 0x56C, 0x63E58
FORMULA, REVIVAL, REVITA, BOMB = 36, 37, 38, 39
MUTA_FLOWER, MUTA_FOLIAGE = 48, 49                      # Store Upgrades and Items' Muta chemicals
SHEET_CHEMICALS = 0xB3
SOUND_BUTTON, SOUND_DROP, TRASH_BIN = 0x0C, 0x0D, 0x23
DOCS = "C:\\Docs"
EXE_PATH = "C:\\Games\\Plant Tycoon\\Plant Tycoon.exe"
SIDECAR = DOCS + "\\LDW\\Plant Tycoon\\Plant Tycoon Fix Patcher Data\\Extra Chemical Slots {}.dat"

# Page 1: slot i drawn at (2 + 45 i, 173), hit x 20..47 + 45 i, y 173..253 (0x4165A0 / 0x416650).
# Page 2: the same columns, row 1 drawn at y 126 (hit 136..184), row 2 at 173 (hit 185..253).
COL_X = [2 + 45 * c for c in range(4)]
ROW_Y = (126, 173)
ARROW = (199, 178, 24, 24)               # the right arrow: x, y, w, h
ARROW_LEFT = (0, 178, 24, 24)            # the left arrow, drawn
ARROW_LEFT_HIT = (0, 178, 18, 24)        # and pressed: left of every tool and slot
PAGE_TEXT = (201, 204)                   # under the right arrow


def page1_point(i: int) -> tuple[int, int]:
    return 33 + 45 * i, 210


def page2_point(e: int) -> tuple[int, int]:
    return 33 + 45 * (e % 4), (160, 215)[e // 4]


def name(chemical: int) -> str:
    return f"Chemical {chemical}"


def _needs():
    ready = (E is not None and E.toolchain_ready() and EXE is not None and EXE.is_file() and DLL.is_file()
             and UPGRADES_DLL.is_file())
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset, the vanilla executable and the DLLs")


class FakeFiles:
    """CreateFileW / ReadFile / WriteFile / MoveFileExW / ... over a dict."""

    def __init__(self, emu, hook_import=None) -> None:
        self.emu, self.files, self.handles, self.next = emu, {}, {}, 0x100
        hook = hook_import or emu.hook_import
        hook("LoadLibraryW", lambda e: 0x7000_0000, 4)
        self.special = emu.thunk()
        emu.hook(self.special, self._special, 16)
        hook("GetModuleFileNameW", self._exe_name, 12)
        hook("CreateDirectoryW", lambda e: 1, 8)
        hook("CreateFileW", self._create, 28)
        hook("WriteFile", self._write, 20)
        hook("ReadFile", self._read, 20)
        hook("GetFileSizeEx", self._size, 8)
        hook("FlushFileBuffers", lambda e: 1, 4)
        hook("CloseHandle", lambda e: 1, 4)
        hook("MoveFileExW", self._move, 12)
        hook("DeleteFileW", lambda e: self.files.pop(e.wstring(e.arg(0)), None) is not None, 4)
        hook("GetLastError", lambda e: 183, 0)          # ERROR_ALREADY_EXISTS

    def _special(self, e) -> int:
        e.uc.mem_write(e.arg(1), (DOCS + "\0").encode("utf-16-le"))
        return 1

    def _exe_name(self, e) -> int:
        e.uc.mem_write(e.arg(1), (EXE_PATH + "\0").encode("utf-16-le"))
        return len(EXE_PATH)

    def _create(self, e) -> int:
        path, disposition = e.wstring(e.arg(0)), e.arg(4)
        if disposition == 3 and path not in self.files:      # OPEN_EXISTING
            return 0xFFFFFFFF
        if disposition == 2:                                 # CREATE_ALWAYS
            self.files[path] = b""
        self.next += 4
        self.handles[self.next] = [path, 0]
        return self.next

    def _write(self, e) -> int:
        h, buf, n, out = e.arg(0), e.arg(1), e.arg(2), e.arg(3)
        self.files[self.handles[h][0]] += bytes(e.uc.mem_read(buf, n))
        e.write32(out, n)
        return 1

    def _read(self, e) -> int:
        h, buf, n, out = e.arg(0), e.arg(1), e.arg(2), e.arg(3)
        path, pos = self.handles[h]
        chunk = self.files[path][pos: pos + n]
        e.uc.mem_write(buf, chunk)
        self.handles[h][1] = pos + len(chunk)
        e.write32(out, len(chunk))
        return 1

    def _size(self, e) -> int:
        size = len(self.files[self.handles[e.arg(0)][0]])
        e.uc.mem_write(e.arg(1), struct.pack("<q", size))
        return 1

    def _move(self, e) -> int:
        src, dst, flags = e.wstring(e.arg(0)), e.wstring(e.arg(1)), e.arg(2)
        if src not in self.files or (dst in self.files and not flags & 1):
            return 0
        self.files[dst] = self.files.pop(src)
        return 1


def sidecar(owned: int, page: list[tuple[int, int] | None]) -> bytes:
    body = b"".join(struct.pack("<B3xii", 1, c, d) if c else bytes(12) for c, d in
                    ((p or (0, 0)) for p in page))
    return struct.pack("<5I", 0x53435450, 1, owned, 8, 12) + body


class Game:
    """The greenhouse with the DLL installed: the state, the screen and the game's helpers."""

    def __init__(self, test: "ChemSlotsCase", owned: bool = True, slot: int | None = None,
                 files: dict | None = None, exe: Path | None = None) -> None:
        emu = self.emu = E.Emulator(exe or EXE, test.dll, test.symbols)
        emu.uc.mem_map(0, 0x1000)                                  # fs:[0]
        emu.hook_printf()
        self.files = FakeFiles(emu)
        if files:
            self.files.files.update(files)
        self.calls = emu.calls
        emu.hook_import("VirtualProtect", self._protect, 16)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)
        emu.hook_import("GetProcAddress", lambda e: self.files.special, 8)
        emu.hook_import("lstrcmpiW", lambda e: 1, 8)
        self.tips: dict[int, dict] = {}
        self.strings: dict[int, int] = {}
        emu.hook(0x004208F0, self._sprite, 0x1C)
        emu.hook(0x004092A0, self._text, 0x14)
        emu.hook(0x00407A90, lambda e: 0x0BAD0000, 0)
        emu.hook(0x0044A580, emu.record("sound", args=1), 4)
        emu.hook(0x0044CA70, self._string, 4)
        emu.hook(0x0044E894, lambda e: e.alloc(max(e.arg(0), 4)), 0)
        emu.hook(0x00409870, self._tip_new, 0x1C)
        emu.hook(0x00409AA0, self._tip_text, 0x10)
        emu.hook(0x0040B400, emu.record("control", args=1), 4)
        emu.hook(0x0044DD70, emu.record("tools", args=1), 4)
        emu.hook(0x00420670, lambda e: self.sprites, 0)
        emu.hook(0x00421190, self._fly, 0x20)                     # the put-back's flight
        emu.hook(0x004033B0, lambda e: 0, 0)
        emu.hook(0x0041B190, emu.record("hint", args=2), 8)
        emu.hook(0x00402050, lambda e: 0, 0)                      # the tooltips' "a button is down": none
        emu.hook(0x00402060, lambda e: 0, 0)                      # and their clock (the hover's delay)
        self.installed = emu.call(test.symbols["_FtfpStartup@0"])
        state = self.state = emu.alloc(STATE_SIZE)
        for k in range(4):
            emu.uc.mem_write(state + TRAY + 12 * k, bytes(12))
        emu.write32(state + HELD, 0)
        emu.write32(state + SELECTED, 0x63)
        scene = self.scene = emu.alloc(0x200)
        emu.write32(scene + 4, emu.alloc(0x20))                    # its rect (0x40B380): at 0, 0
        emu.write32(scene + 0x68, state)
        self.sprites = emu.alloc(0x40)
        emu.write32(scene + 0x6C, self.sprites)
        for offset in (0x60, 0x70, 0x74, 0x78, 0x84, 0x88, 0x90):
            emu.write32(scene + offset, emu.alloc(0x40))
        self.flight = emu.alloc(0x40)
        emu.write32(self.flight + 4, 0xFFFFFFFF)
        emu.write32(scene + 0x80, self.flight)
        self.tray_obj = emu.alloc(8)
        emu.write32(self.tray_obj, state)
        emu.write32(scene + 0x8C, self.tray_obj)
        emu.write32(0x00493BE8, self.tray_obj)                    # the tray's instance (0x416370)
        self.sym = test.symbols
        if slot is None:
            self.new_game()
        else:
            self.load(slot)
        if owned and slot is None:
            self.buy()

    # -------------------------------------------------------------- the hooks
    def _protect(self, e) -> int:
        e.write32(e.arg(3), 0x20)
        return 1

    def _sprite(self, e) -> int:
        e.calls.append(("draw", (e.arg(0), e.arg(1), e.arg(2), e.arg(3))))
        return 0

    def _text(self, e) -> int:
        e.calls.append(("text", (e.cstring(e.arg(0)).decode(), e.arg(1), e.arg(2), e.arg(3))))
        return 0

    def _string(self, e) -> int:
        sid = e.arg(0)
        if sid not in self.strings:
            names = {0x1F0: "Radioactive Plant Formula", 0x1F5: "Revival Potion", 0x1F6: "Revita-Seed",
                     0x1F7: "Radioactive Plant Formula Bomb", 0x1FB: "Muta-Flower", 0x1FC: "Muta-Foliage"}
            self.strings[sid] = e.text(names.get(sid, name(sid - 0x189)))
        return self.strings[sid]

    def _tip_new(self, e) -> int:
        """0x409870 as the game makes a tooltip: the shell (+8 1, +0xC its body) and the body
        (0x4094A0: +4 id, +0x10 rect, +0x30 parent, +0x39 1, +0x3A not hovered).  The body's own
        mouse move (0x409D70) is the game's, run by move(); hovered() is its draw's test (0x409B70)."""
        tip = e.uc.reg_read(X.UC_X86_REG_ECX)
        rect = struct.unpack("<4i", e.uc.mem_read(e.arg(1), 16))
        body = e.alloc(0x6C)
        e.write32(body + 4, e.arg(0))
        e.uc.mem_write(body + 0x10, struct.pack("<4i", *rect))
        e.write32(body + 0x30, e.arg(2))
        e.write8(body + 0x39, 1)
        e.write32(tip + 0xC, body)
        self.tips[tip] = {"id": e.arg(0), "rect": rect, "text": e.cstring(e.arg(3)).decode(), "body": body}
        e.write8(tip + 8, 1)
        return tip

    def _tip_text(self, e) -> int:
        self.tips[e.uc.reg_read(X.UC_X86_REG_ECX)]["text"] = e.cstring(e.arg(0)).decode()
        return 0

    def _fly(self, e) -> int:
        f = e.uc.reg_read(X.UC_X86_REG_ECX)
        e.write32(f + 4, e.arg(0))
        e.write32(f + 0x10, e.arg(1))
        e.write32(f + 0x14, e.arg(2))
        e.write8(f, 1)
        e.calls.append(("fly", (e.arg(0), e.arg(1), e.arg(2))))
        return 0

    # -------------------------------------------------------------- the game
    def call(self, name_: str, *args, **regs) -> int:
        return self.emu.call(self.sym[name_], *args, **regs)

    def new_game(self) -> None:
        self.call("_FtfpChemSlotsNewGame")

    def buy(self) -> None:
        self.call("_FtfpChemSlotsBuy")

    def save(self, slot: int) -> None:
        self.call("_FtfpChemSlotsSave", self.state, slot)

    def load(self, slot: int) -> None:
        self.call("_FtfpChemSlotsLoad", self.state, slot)

    def page(self) -> int:
        return self.call("_FtfpChemSlotsPage")

    def put(self, k: int, chemical: int, doses: int) -> None:
        self.emu.uc.mem_write(self.state + TRAY + 12 * k, struct.pack("<B3xii", 1, chemical, doses))

    def put2(self, e: int, chemical: int, doses: int) -> None:
        rec = self.call("_FtfpChemSlotsRecord", e)
        self.emu.uc.mem_write(rec, struct.pack("<B3xii", 1, chemical, doses))

    def tray(self) -> list[tuple[int, int] | None]:
        out = []
        for k in range(4):
            p, c, d = struct.unpack("<B3xii", self.emu.uc.mem_read(self.state + TRAY + 12 * k, 12))
            out.append((c, d) if p else None)
        return out

    def page2(self) -> list[tuple[int, int] | None]:
        out = []
        for e in range(8):
            rec = self.call("_FtfpChemSlotsRecord", e)
            p, c, d = struct.unpack("<B3xii", self.emu.uc.mem_read(rec, 12))
            out.append((c, d) if p else None)
        return out

    def held(self) -> int:
        return self.emu.read32(self.state + HELD, signed=True)

    def flying(self) -> int:
        return self.emu.read32(self.flight + 4, signed=True) if self.emu.uc.mem_read(self.flight, 1)[0] else -1

    def draw(self, skip: int = -1) -> list:
        """The greenhouse draw's tray call (0x428EFC): the stub, then the draws it made."""
        self.calls.clear()
        self.call("_stub_tray_draw", skip & 0xFFFFFFFF, ecx=self.tray_obj, esi=self.scene)
        return [c[1] for c in self.calls if c[0] == "draw"]

    def tools_drawn(self) -> bool:
        self.calls.clear()
        self.call("@tools_draw@12", 0xFFFFFFFF, ecx=self.emu.read32(self.scene + 0x90))
        return any(c[0] == "tools" for c in self.calls)

    def press(self, x: int, y: int) -> int:
        """The greenhouse press (0x426040, thiscall scene (x, y)) through the DLL's mouse wrapper's checks."""
        return self.mouse(2, x, y)

    def mouse(self, kind: int, x: int, y: int) -> int:
        return self.call("@gh_mouse@20", kind, x, y, ecx=self.scene)

    def activate(self, on: int) -> int:
        return self.call("@gh_activate@12", on, ecx=self.scene)

    def hover(self, x: int, y: int) -> int:
        """The mouse move's tray spot (0x427765): the stub, as the stock hover calls it."""
        return self.emu.call(self.sym["_stub_tray_spot"], x, y, esi=self.scene)

    def visible_tips(self) -> dict[tuple, str]:
        """The tooltips the mouse can bring up: those whose body keeps its rect.  A hidden one's rect
        is empty (no point is in it) and it is not hovered; the shell's +8 is read by nothing."""
        out = {}
        for t in self.tips.values():
            r = struct.unpack("<4i", self.emu.uc.mem_read(t["body"] + 0x10, 16))
            if r[0] <= r[2] and r[1] <= r[3]:
                assert r == t["rect"], (r, t["rect"])
                out[r] = t["text"]
            else:
                assert not self.emu.uc.mem_read(t["body"] + 0x3A, 1)[0], t
        return out

    def move(self, x: int, y: int) -> None:
        """The mouse moves to (x, y): the input hands it to every tooltip body (0x409D70, the game's)."""
        for t in self.tips.values():
            self.emu.call(0x00409D70, 1, x, y, ecx=t["body"])

    def hovered(self) -> list[str]:
        """The tooltips the screen's draw draws now (0x409B70: a hovered body, +0x3A)."""
        return [t["text"] for t in self.tips.values() if self.emu.uc.mem_read(t["body"] + 0x3A, 1)[0]]


class ChemSlotsCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_chem_slots", DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def game(self, **kw) -> Game:
        g = Game(self, **kw)
        self.assertEqual(g.installed, 1)
        # The mouse wrapper's next handler: a press goes on to the stock press (0x426040) only; the
        # rest of 0x4273D0 (the cursor, double clicks, dragging plants) is not about the tray.
        code = g.emu.alloc(0x20)
        g.emu.uc.mem_write(code, bytes.fromhex("837C240402750DFF74240CFF74240C")
                           + b"\xE8" + struct.pack("<i", 0x00426040 - (code + 20)) + bytes.fromhex("B801000000C20C00"))
        g.emu.write32(self.symbols["_next_mouse"], code)
        return g


def dose(g: Game, chemical: int) -> int:
    """The chemical use's dose (0x426699: 0x416540, thiscall tray (id)): 1 when one was spent."""
    return g.emu.call(0x00416540, chemical, ecx=g.tray_obj) & 0xFF


def use_tail(g: Game) -> None:
    """The chemical use's tail (0x42721F on: the bottle kept while it has doses, else the hand emptied)."""
    emu = g.emu
    esp = E.STACK + E.STACK_SIZE - 0x2000
    emu.uc.mem_write(esp, bytes(0x40))
    emu.write32(esp + 0x1C, E.RETURN)               # after edi, esi, ebp, ebx and 0xC of locals
    emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
    emu.uc.reg_write(X.UC_X86_REG_ESI, g.scene)
    emu.uc.emu_start(0x0042721F, E.RETURN, count=200_000)


def land(g: Game) -> None:
    """The put-back's flight arrives (0x4211D0), then a frame is drawn."""
    g.emu.call(0x004211D0, ecx=g.flight)
    g.draw()


def tray_add(g: Game, chemical: int, doses: int) -> int:
    return g.emu.call(0x00416410, chemical, doses, ecx=g.tray_obj) & 0xFF


def tray_room(g: Game, chemical: int) -> int:
    return g.emu.call(0x004164B0, chemical, ecx=g.tray_obj) & 0xFF


def in_rect(r: tuple[int, int, int, int], x: int, y: int) -> bool:
    return r[0] <= x <= r[2] and r[1] <= y <= r[3]


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


@_needs()
class InstallTests(ChemSlotsCase):
    def test_every_site_is_written_and_chains_what_was_there(self) -> None:
        g = self.game()
        calls = {0x42606E: "@tool_hit@16", 0x4260A9: "_stub_tray_hit", 0x427765: "_stub_tray_spot",
                 0x428EE2: "@tools_draw@12", 0x428EFC: "_stub_tray_draw"}
        for va, target in calls.items():
            raw = bytes(g.emu.uc.mem_read(va, 5))
            self.assertEqual(raw[0], 0xE8, hex(va))
            self.assertEqual(va + 5 + struct.unpack("<i", raw[1:])[0], self.symbols[target], hex(va))
        for va, target in ((0x416410, "@tray_add@16"), (0x4164B0, "@tray_room@12")):
            raw = bytes(g.emu.uc.mem_read(va, 5))
            self.assertEqual((raw[0], va + 5 + struct.unpack("<i", raw[1:])[0]), (0xE9, self.symbols[target]))
        self.assertEqual(g.emu.read32(0x469224), self.symbols["@gh_mouse@20"])
        self.assertEqual(g.emu.read32(0x469244), self.symbols["@gh_activate@12"])
        self.assertEqual(g.emu.read32(self.symbols["_next_activate"]), 0x4231E0)
        log = g.files.files["C:\\Games\\Plant Tycoon\\Extra Chemical Slots.log"]
        self.assertEqual(log, b"Extra Chemical Slots: installed (all sites)\r\n")

    def test_one_changed_site_writes_nothing(self) -> None:
        for va in (0x42606E, 0x4260A9, 0x427765, 0x428EE2, 0x428EFC, 0x416410, 0x4164B0, 0x469224, 0x469244):
            emu = E.Emulator(EXE, self.dll, self.symbols)
            emu.uc.mem_map(0, 0x1000)
            files = FakeFiles(emu)
            emu.hook_import("VirtualProtect", lambda e: (e.write32(e.arg(3), 0x20), 1)[1], 16)
            emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
            emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
            emu.hook_import("GetModuleHandleW", lambda e: 0, 4)
            emu.hook_import("GetProcAddress", lambda e: files.special, 8)
            emu.hook_import("lstrcmpiW", lambda e: 1, 8)                          # another folder's DLL
            before ={a: bytes(emu.uc.mem_read(a, 8)) for a in (0x42606E, 0x4260A9, 0x427765, 0x428EE2, 0x428EFC,
                                                                  0x416410, 0x4164B0, 0x469224, 0x469244)}
            emu.write8(va + 1, emu.uc.mem_read(va + 1, 1)[0] ^ 0x5A)             # someone else's change
            before[va] = bytes(emu.uc.mem_read(va, 8))
            self.assertEqual(emu.call(self.symbols["_FtfpStartup@0"]), 0, hex(va))
            for a, raw in before.items():
                self.assertEqual(bytes(emu.uc.mem_read(a, 8)), raw, (hex(va), hex(a)))
            log = files.files["C:\\Games\\Plant Tycoon\\Extra Chemical Slots.log"].decode()
            self.assertIn(f"NOT installed; the code at 0x{va:08X}", log)

    def test_the_header_is_what_the_generator_makes_and_overlaps_nothing(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("chem_headers", ROOT / "scripts" / "build_chem_slots_headers.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        with tempfile.TemporaryDirectory() as tmp:
            gen.OUT = Path(tmp)
            sys.argv = ["x", str(EXE.parent)]
            self.assertEqual(gen.main(), 0)                      # it refuses any overlap or branch target
            self.assertEqual((Path(tmp) / "chem_slots_sites.h").read_text(encoding="utf-8"),
                             SITES_H.read_text(encoding="utf-8"))
        data = EXE.read_bytes()
        mine = []
        for _n, va, expect in gen.SITES:
            mine.append((va, va + sum(len(i.bytes) for i in gen.disasm(data, va, len(expect)))))
        mine += [(va, va + 4) for _n, va, _f in gen.VTABLE]
        # The greenhouse table slots are shared on purpose (chained); nothing else may touch these bytes.
        others = [(s, e, n) for s, e, n in gen.used_ranges(data)] + [(s, e, "Fix Patcher") for s, e in
                                                                       gen.flower_headers.fix_patcher_ranges()]
        for start, stop in mine:
            for s, e, n in others:
                self.assertFalse(start < e and s < stop, (hex(start), n))

    def test_loaded_after_every_other_companion_with_enable_all(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        everything = {s["id"] for s in manifest["settings"]}
        everything |= {"extra_chemical_slots"}
        for enabled in (everything, {"new_flowers", "plant_upgrades", "extra_chemical_slots"},
                        {"new_flowers", "plant_upgrades", "extra_chemical_slots", "tank_greenhouse_counts",
                         "optimize_prices"}, everything - {"extra_greenhouses", "extra_nurseries"}):
            names = ds_fish_loader.plant_profile(enabled).dll_names
            self.assertEqual(names[-1], "Extra Chemical Slots.dll", enabled)
            self.assertEqual(names.count("Extra Chemical Slots.dll"), 1)
        self.assertNotIn("Extra Chemical Slots.dll",
                         ds_fish_loader.plant_profile(everything - {"extra_chemical_slots"}).dll_names)


@_needs()
class PageTests(ChemSlotsCase):
    ARROW_POINTS = ((ARROW[0], ARROW[1]), (ARROW[0] + ARROW[2] - 1, ARROW[1] + ARROW[3] - 1), (211, 190),
                    (0, ARROW_LEFT[1]), (ARROW_LEFT_HIT[2] - 1, ARROW_LEFT[1] + ARROW_LEFT[3] - 1), (8, 190))

    def test_the_arrow_turns_the_page_and_shows_the_page_number(self) -> None:
        g = self.game()
        drawn = g.draw()
        for frame, at in ((38, ARROW), (39, ARROW_LEFT)):                      # both arrows on page 1
            self.assertIn((SHEET_CHEMICALS, frame, at[0], at[1]), drawn)
        self.assertEqual([c[1][:3] for c in g.calls if c[0] == "text"],
                         [("1/2", PAGE_TEXT[0] + 1, PAGE_TEXT[1] + 1), ("1/2", *PAGE_TEXT)])
        for x, y in self.ARROW_POINTS:
            with self.subTest(at=(x, y)):
                g.calls.clear()
                before = g.page()
                self.assertEqual(g.press(x, y), 1)
                self.assertEqual(g.page(), 1 - before)
                self.assertIn(("sound", (SOUND_BUTTON,)), g.calls)
        g = self.game()
        g.press(*self.ARROW_POINTS[2])
        drawn = g.draw()
        for frame, at in ((38, ARROW), (39, ARROW_LEFT)):                      # and on page 2
            self.assertIn((SHEET_CHEMICALS, frame, at[0], at[1]), drawn)
        self.assertEqual([c[1][0] for c in g.calls if c[0] == "text"], ["2/2", "2/2"])
        for x, y in ((ARROW[0] - 1, 190), (ARROW[0] + ARROW[2], 190), (211, ARROW[1] - 1), (211, ARROW[1] + ARROW[3]),
                     (ARROW_LEFT_HIT[2], 190), (8, ARROW_LEFT[1] - 1), (8, ARROW_LEFT[1] + ARROW_LEFT[3])):
            g.press(x, y)
            self.assertEqual(g.page(), 1, (x, y))

    def test_not_bought_nothing_shows_and_the_page_never_turns(self) -> None:
        g = self.game(owned=False)
        drawn = g.draw()
        self.assertFalse([d for d in drawn if d[1] in (38, 39)])
        self.assertFalse([c for c in g.calls if c[0] == "text"])
        g.press(211, 190)
        self.assertEqual(g.page(), 0)
        self.assertTrue(g.tools_drawn())

    def test_page_two_has_no_tools_page_one_has(self) -> None:
        g = self.game()
        self.assertTrue(g.tools_drawn())
        self.assertNotEqual(g.call("@tool_hit@16", 40, 150, ecx=g.scene) & 0xFFFFFFFF, 0xFFFFFFFF)   # the soil
        g.press(211, 190)
        self.assertFalse(g.tools_drawn())
        for k in range(4):
            self.assertEqual(g.call("@tool_hit@16", 40 + 45 * k, 150, ecx=g.scene) & 0xFFFFFFFF, 0xFFFFFFFF)
        g.emu.write32(g.state + HELD, 2)                     # a tool in the hand stays there through the pages
        g.press(211, 190)
        self.assertEqual((g.page(), g.held()), (0, 2))

    def test_page_two_draws_its_eight_slots_in_both_rows(self) -> None:
        g = self.game()
        for e in range(8):
            g.put2(e, 27 + e, 1 + e)
        g.put(0, 36, 3)
        g.press(211, 190)
        drawn = g.draw()
        for e in range(8):
            self.assertIn((SHEET_CHEMICALS, 2 * (27 + e) - 54, COL_X[e % 4], ROW_Y[e // 4]), drawn)
        self.assertNotIn((SHEET_CHEMICALS, 2 * 36 - 54, COL_X[0], 173), drawn)    # page 1's bottle is not
        g.press(211, 190)
        drawn = g.draw()
        self.assertIn((SHEET_CHEMICALS, 2 * 36 - 54, COL_X[0], 173), drawn)
        self.assertFalse([d for d in drawn if d[1] == 2 * 27 - 54])

    def test_carrying_a_chemical_over_the_arrow_turns_the_page_once(self) -> None:
        g = self.game()
        g.put(1, 30, 2)
        g.press(*page1_point(1))
        self.assertEqual(g.held(), 6)
        g.mouse(1, 100, 100)
        g.mouse(1, 210, 185)                                 # onto the arrow
        self.assertEqual(g.page(), 1)
        g.mouse(1, 212, 188)                                 # still on it: no second turn
        self.assertEqual(g.page(), 1)
        g.mouse(1, 120, 100)
        g.mouse(1, 210, 185)                                 # off and on again: back
        self.assertEqual(g.page(), 0)
        self.assertEqual(g.held(), 6)
        g.emu.write32(g.state + HELD, 0)
        g.mouse(1, 120, 100)
        g.mouse(1, 210, 185)                                 # an empty hand only turns it by a click
        self.assertEqual(g.page(), 0)
        g.emu.write32(g.state + HELD, 3)
        g.mouse(1, 120, 100)
        g.mouse(1, 210, 185)                                 # nor does a tool
        self.assertEqual(g.page(), 0)


@_needs()
class TrayTests(ChemSlotsCase):
    def test_buying_fills_page_one_then_page_two_and_stacks_anywhere(self) -> None:
        g = self.game()
        for n in range(12):
            self.assertEqual(tray_add(g, 27 + n, 3), 1, n)
        self.assertEqual(g.tray(), [(27 + k, 3) for k in range(4)])
        self.assertEqual(g.page2(), [(31 + e, 3) for e in range(8)])
        self.assertEqual(tray_room(g, 38), 1)                # stacks on its own bottle
        self.assertEqual(tray_add(g, 36, 3), 1)
        self.assertEqual(g.page2()[5], (36, 6))
        self.assertEqual(tray_add(g, 28, 2), 1)
        self.assertEqual(g.tray()[1], (28, 5))
        g.emu.uc.mem_write(g.state + TRAY + 12 * 2, bytes(12))      # a free slot on page 1 (29 gone) ...
        g.emu.uc.mem_write(g.call("_FtfpChemSlotsRecord", 6), bytes(12))   # ... and on page 2 (37 gone)
        self.assertEqual(tray_add(g, 37, 1), 1)              # page 1 first
        self.assertEqual(g.tray()[2], (37, 1))
        self.assertEqual(tray_add(g, 29, 1), 1)              # then page 2
        self.assertEqual(g.page2()[6], (29, 1))

    def test_the_full_tray_refuses_only_when_all_twelve_are_full(self) -> None:
        g = self.game()
        for n in range(12):
            tray_add(g, 27 + n, 1)
        self.assertEqual(tray_room(g, 38), 1)                 # 38 is in the last slot: it stacks
        g.emu.uc.mem_write(g.call("_FtfpChemSlotsRecord", 7), struct.pack("<B3xii", 1, 39, 1))   # now 39 is
        self.assertEqual(tray_room(g, 38), 0)                 # "There is no room in your Chemical Tray."
        before = (g.tray(), g.page2())
        self.assertEqual(tray_add(g, 38, 3), 0)
        self.assertEqual((g.tray(), g.page2()), before)
        g.emu.uc.mem_write(g.call("_FtfpChemSlotsRecord", 4), bytes(12))
        self.assertEqual(tray_room(g, 38), 1)                 # one free slot on page 2 is room

    def test_not_bought_the_tray_is_the_stock_four(self) -> None:
        g = self.game(owned=False)
        for n in range(4):
            self.assertEqual(tray_add(g, 27 + n, 2), 1)
        self.assertEqual(tray_room(g, 35), 0)
        self.assertEqual(tray_add(g, 35, 2), 0)
        self.assertEqual(tray_room(g, 28), 1)
        self.assertEqual(g.page2(), [None] * 8)

    def test_every_chemical_is_used_from_page_two_with_its_doses(self) -> None:
        for chemical in range(27, 40):
            for full_page_one in (False, True):
                with self.subTest(chemical=chemical, full_page_one=full_page_one):
                    g = self.game()
                    if full_page_one:
                        for k in range(4):
                            g.put(k, 27 + (chemical - 27 + 1 + k) % 13, 5)
                    page_one = g.tray()
                    e = (chemical - 27) % 8
                    g.put2(e, chemical, 2)
                    g.press(211, 190)
                    self.assertEqual(g.press(*page2_point(e)), 1)
                    k = g.held() - 5
                    self.assertIn(k, range(4))
                    self.assertEqual(g.tray()[k], (chemical, 2))        # the stock record holds it while used
                    drawn = g.draw()
                    self.assertNotIn((SHEET_CHEMICALS, 2 * chemical - 54, COL_X[e % 4], ROW_Y[e // 4]), drawn)
                    self.assertEqual(dose(g, chemical), 1)
                    use_tail(g)
                    self.assertEqual((g.held(), g.tray()[k]), (5 + k, (chemical, 1)))   # still in the hand
                    self.assertEqual(dose(g, chemical), 1)
                    use_tail(g)
                    self.assertEqual(g.held(), 0)                              # used up
                    g.draw()
                    self.assertEqual(g.tray(), page_one)                       # page 1 as it was
                    self.assertEqual(g.page2(), [None] * 8)

    def test_a_page_two_bottle_put_back_flies_home(self) -> None:
        g = self.game()
        g.put(0, 27, 1)
        g.put2(5, 33, 4)
        g.press(211, 190)
        g.press(*page2_point(5))
        k = g.held() - 5
        self.assertEqual(g.tray()[k], (33, 4))
        g.press(*page2_point(5))                             # its own slot: the stock put-back
        self.assertEqual((g.held(), g.flying()), (0, 5 + k))
        self.assertEqual((g.emu.read32(g.flight + 0x10), g.emu.read32(g.flight + 0x14)), (COL_X[1] + 35, 173 + 35))
        self.assertEqual(g.tray()[k], (33, 4))               # in the stock record until it lands
        land(g)
        self.assertEqual(g.page2()[5], (33, 4))
        self.assertEqual(g.tray(), [(27, 1), None, None, None])

    def test_leaving_the_greenhouse_puts_a_held_page_two_bottle_home(self) -> None:
        for on in (0, 1):
            g = self.game()
            g.emu.hook(0x004231E0, g.emu.record("stock activate", args=1), 4)
            for k in range(4):
                g.put(k, 27 + k, 1)
            g.put2(2, 36, 3)
            g.press(211, 190)
            g.press(*page2_point(2))
            self.assertNotEqual(g.held(), 0)
            g.activate(on)
            self.assertEqual(g.held(), 0)
            self.assertEqual(g.tray(), [(27 + k, 1) for k in range(4)])
            self.assertEqual(g.page2()[2], (36, 3))


@_needs()
class MoveTests(ChemSlotsCase):
    def test_a_held_bottle_pressed_on_another_slot_moves_stacks_or_swaps(self) -> None:
        cases = (("empty", None, [None, (30, 2)], (30, 2)), ("same", (30, 5), [None, (30, 7)], None),
                 ("other", (31, 1), [(31, 1), (30, 2)], None))
        for label, there, _, _ in cases:
            for src_page2, dst_page2 in ((False, False), (False, True), (True, False), (True, True)):
                with self.subTest(label=label, src_page2=src_page2, dst_page2=dst_page2):
                    g = self.game()
                    src, dst = (4 + 6, 4 + 1) if src_page2 else (0, 2)
                    if dst_page2:
                        dst = 4 + 3 if src_page2 else 4 + 1
                    elif src_page2:
                        dst = 2
                    put = lambda s, c, d: g.put(s, c, d) if s < 4 else g.put2(s - 4, c, d)
                    put(src, 30, 2)
                    if there:
                        put(dst, *there)
                    if src_page2:
                        g.press(211, 190)
                        g.press(*page2_point(src - 4))
                    else:
                        g.press(*page1_point(src))
                    self.assertNotEqual(g.held(), 0)
                    if src_page2 != dst_page2:
                        g.press(211, 190)                             # the arrow, the bottle still in hand
                    g.calls.clear()
                    g.press(*(page2_point(dst - 4) if dst_page2 else page1_point(dst)))
                    self.assertEqual((g.held(), g.flying()), (0, -1))
                    self.assertIn(("sound", (SOUND_DROP,)), g.calls)
                    g.draw()
                    every = g.tray() + g.page2()
                    want_src = there if label == "other" else None
                    want_dst = (30, 2) if label in ("empty", "other") else (30, 7)
                    self.assertEqual((every[src], every[dst]), (want_src, want_dst))
                    self.assertEqual(sum(1 for r in every if r), 2 if label == "other" else 1)

    def test_let_go_over_another_slot_it_moves_there(self) -> None:
        g = self.game()
        g.put(3, 29, 4)
        g.press(*page1_point(3))                              # picked up
        g.press(211, 190)                                     # page 2, still held
        g.mouse(3, *page2_point(7))                           # released over page 2's last slot
        g.draw()
        self.assertEqual(g.held(), 0)
        self.assertEqual(g.tray(), [None] * 4)
        self.assertEqual(g.page2()[7], (29, 4))
        g.press(*page2_point(7))                              # pressed and let go on the same slot: kept in hand
        g.mouse(3, *page2_point(7))
        self.assertNotEqual(g.held(), 0)


@_needs()
class TooltipTests(ChemSlotsCase):
    def test_every_slot_shows_its_name_and_doses_left(self) -> None:
        g = self.game()
        g.put(0, 30, 2)
        g.put(2, REVIVAL, 1)
        g.put2(0, FORMULA, 3)
        g.put2(5, 27, 4)
        g.draw()
        tips = g.visible_tips()
        self.assertEqual(tips, {(20, 173, 47, 253): "Chemical 30\n2 doses left",
                                (110, 173, 137, 253): "Revival Potion\n1 dose left"})
        g.press(211, 190)
        g.draw()
        self.assertEqual(g.visible_tips(), {(20, 136, 47, 184): "Radioactive Plant Formula\n3 doses left",
                                            (65, 185, 92, 253): "Chemical 27\n4 doses left"})
        g.press(*page2_point(0))                              # in the hand: no tooltip over its empty slot
        g.draw()
        self.assertEqual(list(g.visible_tips().values()), ["Chemical 27\n4 doses left"])
        self.assertEqual(dose(g, FORMULA), 1)
        use_tail(g)
        g.press(*page2_point(0))
        land(g)
        self.assertEqual(g.visible_tips()[(20, 136, 47, 184)], "Radioactive Plant Formula\n2 doses left")
        self.assertEqual(g.hover(*page2_point(0)), 0xFFFFFFFF)  # the stock tray tooltips are never made

    def test_without_the_purchase_page_one_has_them_too(self) -> None:
        g = self.game(owned=False)
        for k, chemical in enumerate((BOMB, REVITA, 31)):
            g.put(k, chemical, k + 1)
        g.draw()
        self.assertEqual(g.visible_tips(), {(20, 173, 47, 253): "Radioactive Plant Formula Bomb\n1 dose left",
                                            (65, 173, 92, 253): "Revita-Seed\n2 doses left",
                                            (110, 173, 137, 253): "Chemical 31\n3 doses left"})
        self.assertEqual(len(g.tips), 12)


def slot_under(page: int, x: int, y: int) -> int | None:
    """The slot (0-3 page 1, 4-11 page 2) under (x, y) on the page shown, as its tooltip's rect."""
    for c in range(4):
        if not 20 + 45 * c <= x <= 47 + 45 * c:
            continue
        if page == 0:
            return c if 173 <= y <= 253 else None
        for r, (top, bottom) in enumerate(((136, 184), (185, 253))):
            if top <= y <= bottom:
                return 4 + 4 * r + c
    return None


def stock_tray_tips(g: Game) -> None:
    """The stock tray's four tooltips (0x427836) as if the game had made them, at scene + 0x110."""
    for k in range(4):
        tip, rect = g.emu.alloc(0x10), g.emu.alloc(16)
        g.emu.uc.mem_write(rect, struct.pack("<4i", 20 + 45 * k, 173, 47 + 45 * k, 253))
        g.emu.call(0x00409870, 0x200 + k, rect, g.scene, g.emu.text(f"Stock tray tip {k}"), 0, 0, 0, ecx=tip)
        g.emu.write32(g.scene + 0x110 + 4 * k, tip)


@_needs()
class OneTooltipTests(ChemSlotsCase):
    """The owner (2026-11-01): two tooltips drawn over each other on page 2 ("Mutation Liquid
    Vaporbomb\\n12 doses left" over another).  A tooltip's body takes every mouse move itself and is
    drawn whenever the mouse is over its rect (0x409D70, 0x409B70); nothing reads the shell's +8.
    Page 1's tooltips (y 173-253) lie under page 2's second row and the foot of its first, so they
    were hovered on page 2 too.  Now a hidden tooltip has no rect: only the slot under the mouse on
    the page shown, holding a bottle, has its tooltip, never one from the other page or the stock's."""

    XS = sorted(set(range(0, 232, 9)) | {19, 20, 47, 48, 64, 65, 92, 93, 109, 110, 137, 138, 154, 155, 182, 183})
    YS = sorted(set(range(120, 262, 8)) | {135, 136, 172, 173, 184, 185, 253, 254})

    def sweep(self, g: Game, texts: dict[int, str]) -> None:
        for page in (0, 1):
            if g.page() != page:
                g.press(*([a + 8 for a in ARROW[:2]]))
            for x in self.XS:
                for y in self.YS:
                    g.move(x, y)
                    g.draw()
                    want = slot_under(page, x, y)
                    with self.subTest(page=page + 1, x=x, y=y):
                        self.assertEqual(g.hovered(), [texts[want]] if want in texts else [])

    def test_at_most_one_tooltip_for_any_mouse_point_on_either_page(self) -> None:
        g = self.game()
        stock_tray_tips(g)
        texts = {}
        for s, chemical in enumerate(list(range(27, 36)) + [37, 48, 49]):
            (g.put if s < 4 else lambda k, c, d: g.put2(k - 4, c, d))(s, chemical, s + 2)
            label = {37: "Revival Potion", 48: "Muta-Flower", 49: "Muta-Foliage"}.get(chemical, name(chemical))
            texts[s] = f"{label}\n{s + 2} doses left"
        self.sweep(g, texts)

    def test_empty_slots_show_none_and_a_bottle_in_the_hand_loses_its_tooltip(self) -> None:
        g = self.game()
        stock_tray_tips(g)
        g.put(0, 30, 2)
        g.put2(4, 31, 3)                                       # page 2 under page 1's slot 0
        g.put2(1, 32, 1)
        self.sweep(g, {0: "Chemical 30\n2 doses left", 8: "Chemical 31\n3 doses left",
                       5: "Chemical 32\n1 dose left"})
        g.move(*page2_point(4))
        g.draw()
        self.assertEqual(g.hovered(), ["Chemical 31\n3 doses left"])
        g.press(*page2_point(4))                               # picked up: gone without another move
        g.draw()
        self.assertEqual(g.hovered(), [])
        g.mouse(1, ARROW[0] + 8, ARROW[1] + 8)                 # carried over the arrow: page 1
        self.assertEqual(g.page(), 0)
        g.move(*page1_point(0))
        g.draw()
        self.assertEqual(g.hovered(), ["Chemical 30\n2 doses left"])

    def test_the_greenhouse_has_no_other_tooltip(self) -> None:
        """Every tooltip the game makes (0x409870): in the greenhouse's code (0x423000-0x42A000) only
        the tray's (0x427836); the tools have none."""
        data = EXE.read_bytes()
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        count, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
        base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
        sites = []
        for i in range(count):
            sec = pe + 24 + opt_size + 40 * i
            vsize, rva, rsize, raw = struct.unpack_from("<4I", data, sec + 8)
            if not struct.unpack_from("<I", data, sec + 36)[0] & 0x20000000:
                continue
            for off in range(raw, raw + min(rsize, vsize) - 5):
                if data[off] == 0xE8:
                    va = base + rva + off - raw
                    if (va + 5 + struct.unpack_from("<i", data, off + 1)[0]) & 0xFFFFFFFF == 0x00409870:
                        sites.append(va)
        self.assertIn(0x00427836, sites)
        self.assertEqual([s for s in sites if 0x423000 <= s < 0x42A000], [0x00427836])


@_needs()
class SidecarTests(ChemSlotsCase):
    def test_round_trip_and_the_save_keeps_the_stock_layout(self) -> None:
        g = self.game()
        g.put(0, 27, 1)
        g.put2(1, 30, 2)
        g.put2(6, BOMB, 3)
        g.press(211, 190)
        g.press(*page2_point(6))                              # held while the game saves
        k = g.held() - 5
        g.save(0)                                             # the settings file: no sidecar
        g.save(3)
        self.assertEqual(g.tray(), [(27, 1), None, None, None])     # what the game writes now
        self.assertEqual(g.files.files[SIDECAR.format(3)],
                         sidecar(1, [None, (30, 2), None, None, None, None, (BOMB, 3), None]))
        self.assertNotIn(SIDECAR.format(0), g.files.files)
        g.draw()                                              # the next frame: in the hand again
        self.assertEqual((g.held(), g.tray()[k]), (5 + k, (BOMB, 3)))
        h = self.game(slot=3, files=g.files.files)
        h.put(0, 27, 1)
        self.assertEqual(h.page2(), [None, (30, 2), None, None, None, None, (BOMB, 3), None])
        self.assertEqual(h.call("_FtfpChemSlotsOwned"), 1)

    def test_a_new_game_empties_page_two_and_forgets_the_purchase(self) -> None:
        files = {SIDECAR.format(2): sidecar(1, [(30, 2)] + [None] * 7)}
        g = self.game(slot=2, files=files)
        self.assertEqual((g.call("_FtfpChemSlotsOwned"), g.page2()[0]), (1, (30, 2)))
        g.new_game()
        self.assertEqual((g.call("_FtfpChemSlotsOwned"), g.page2()), (0, [None] * 8))
        g.save(2)
        self.assertEqual(g.files.files[SIDECAR.format(2)], sidecar(0, [None] * 8))

    def test_no_file_or_an_unreadable_one(self) -> None:
        g = self.game(slot=4)
        self.assertEqual((g.call("_FtfpChemSlotsOwned"), g.page2()), (0, [None] * 8))
        for bad in (b"junk", sidecar(1, [(99, 1)] + [None] * 7), sidecar(1, [None] * 8)[:-1]):
            g = self.game(slot=4, files={SIDECAR.format(4): bad})
            self.assertEqual((g.call("_FtfpChemSlotsOwned"), g.page2()), (0, [None] * 8))
            self.assertEqual(g.files.files.get(SIDECAR.format(4) + ".unreadable-1"), bad)     # set aside, kept

    def test_the_muta_chemicals_load_and_show_their_names(self) -> None:
        # 48 and 49 are chemicals (their sheet rows 21 and 22); 40-47 are rows of other pictures.
        page = [(MUTA_FLOWER, 2), (MUTA_FOLIAGE, 3)] + [None] * 6
        g = self.game(slot=6, files={SIDECAR.format(6): sidecar(1, page)})
        self.assertEqual(g.page2(), page)
        self.assertNotIn(SIDECAR.format(6) + ".unreadable-1", g.files.files)
        bad = sidecar(1, [(44, 1)] + [None] * 7)
        g = self.game(slot=6, files={SIDECAR.format(6): bad})
        self.assertEqual(g.files.files.get(SIDECAR.format(6) + ".unreadable-1"), bad)
        g = self.game(owned=False)
        g.put(0, MUTA_FLOWER, 1)
        g.put(1, MUTA_FOLIAGE, 3)
        g.draw()
        self.assertEqual(g.visible_tips(), {(20, 173, 47, 253): "Muta-Flower\n1 dose left",
                                            (65, 173, 92, 253): "Muta-Foliage\n3 doses left"})

    def test_a_chemical_on_both_pages_is_stacked_on_load(self) -> None:
        g = self.game(slot=1, files={SIDECAR.format(1): sidecar(1, [(30, 2), None, (31, 1), (30, 1)] + [None] * 4)})
        self.assertEqual(g.page2(), [(30, 3), None, (31, 1)] + [None] * 5)

    def test_deleting_the_slot_deletes_its_file(self) -> None:
        g = self.game(slot=5, files={SIDECAR.format(5): sidecar(1, [None] * 8)})
        g.call("_FtfpChemSlotsDelete", 5)
        self.assertNotIn(SIDECAR.format(5), g.files.files)


# ------------------------------------------------------------------ Store Upgrades and Items' side

S_CASH = 0x217C
ITEM_AT = (598 + 30, 177 + 30)


@_needs()
class StoreItemTests(unittest.TestCase):
    """Store Upgrades and Items.dll: the Upgrades view's item, the events and the setting off."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", UPGRADES_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def store(self, cash: int = 10000, free: bool = False, answer_yes: bool = True, owned: int | None = 0,
              files: dict | None = None):
        emu = E.Emulator(EXE, self.dll, self.symbols)
        emu.uc.mem_map(0, 0x1000)
        emu.hook_printf()
        emu.answers = answer_yes
        self.owned = owned
        fake = FakeFiles(emu)
        if files:
            fake.files.update(files)
        emu.files = fake
        exports = {}
        for label, pop in (("FtfpChemSlotsOwned", 0), ("FtfpChemSlotsBuy", 0), ("FtfpChemSlotsSave", 0),
                           ("FtfpChemSlotsLoad", 0), ("FtfpChemSlotsDelete", 0), ("FtfpChemSlotsNewGame", 0)):
            thunk = emu.thunk()
            exports[label.encode()] = thunk
            emu.hook(thunk, self._export(label), pop)

        def message(e):
            e.calls.append(("MessageBoxW", e.wstring(e.arg(2)), e.wstring(e.arg(1))))
            return 6 if e.answers else 7
        emu.hook_import("MessageBoxW", message, 16)
        for name_, pop in (("GetActiveWindow", 0), ("GetForegroundWindow", 0)):
            emu.hook_import(name_, emu.record(name_), pop)
        present = owned is not None
        emu.hook_import("GetModuleHandleW", lambda e: 0x6D000000 if present and e.wstring(e.arg(0)) ==
                        "Extra Chemical Slots.dll" else 0, 4)
        emu.hook_import("GetProcAddress", lambda e: exports.get(e.cstring(e.arg(1)), fake.special), 8)
        emu.hook(0x0044A580, emu.record("sound", args=1), 4)
        emu.hook(0x0044E894, lambda e: e.alloc(max(e.arg(0), 4)), 0)
        emu.hook(0x00409870, lambda e: (e.calls.append(("tip", e.cstring(e.arg(3)).decode("latin-1"))), 0)[1], 0x1C)
        emu.hook(0x00409AA0, lambda e: (e.calls.append(("tip", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 0x10)
        emu.hook(0x0040B400, emu.record("control"), 4)
        emu.hook(0x004208F0, lambda e: (e.calls.append(("draw", (e.arg(0), e.arg(1), e.arg(2), e.arg(3)))), 0)[1], 0x1C)
        emu.hook(0x004207F0, lambda e: (e.calls.append(("shadow", (e.arg(0), e.arg(1), e.arg(2)))), 0)[1], 0x14)
        emu.hook(0x004033B0, lambda e: 0, 0)
        state = emu.alloc(STATE_SIZE)
        scene = emu.alloc(0x400)
        emu.write32(scene + 0x1BC, state)
        emu.write32(state + S_CASH, cash)
        emu.write8(emu.sym("_free_upgrades"), int(free))
        tray = emu.alloc(8)
        emu.write32(tray, state)
        emu.write32(0x00493BE8, tray)
        emu.state, emu.scene = state, scene
        emu.chem_calls = []
        self.emu = emu
        return emu

    def _export(self, label: str):
        def handler(e) -> int:
            if label == "FtfpChemSlotsOwned":
                return self.owned if self.owned is not None else -1
            if label == "FtfpChemSlotsBuy":
                self.owned = 1
            e.chem_calls.append((label, tuple(e.arg(i) for i in range(2))))
            return 1
        return handler

    def click(self, emu, at) -> None:
        emu.write32(emu.sym("_upgrades_view"), 1)
        emu.call(emu.sym("_on_click"), emu.scene, *at)

    def asked(self, emu):
        return [c[1:] for c in emu.calls if c[0] == "MessageBoxW"]

    def test_bought_once_for_10000(self) -> None:
        emu = self.store(10005)
        self.click(emu, ITEM_AT)
        self.assertEqual(self.asked(emu), [("Extra Chemical Slots", "Buy the extra chemical slots for $10000?\n\nA gold "
                                            "arrow in the greenhouse's Tools box turns to a second page of 8 chemical "
                                            "slots.")])
        self.assertEqual((emu.read32(emu.state + S_CASH), self.owned), (5, 1))
        self.assertIn(("sound", (0x0C,)), emu.calls)
        self.click(emu, ITEM_AT)
        self.assertEqual(self.asked(emu)[-1], ("Extra Chemical Slots", "You already have the extra chemical slots!"))
        self.assertEqual(emu.read32(emu.state + S_CASH), 5)

    def test_no_too_poor_and_free(self) -> None:
        emu = self.store(10005, answer_yes=False)
        self.click(emu, ITEM_AT)
        self.assertEqual((emu.read32(emu.state + S_CASH), self.owned), (10005, 0))
        emu = self.store(9999)
        self.click(emu, ITEM_AT)
        self.assertEqual(self.asked(emu), [("Extra Chemical Slots", "You can't afford to buy this yet! The extra "
                                            "chemical slots cost $10,000.")])
        self.assertEqual(self.owned, 0)
        emu = self.store(0, free=True)
        self.click(emu, ITEM_AT)
        self.assertEqual(self.asked(emu)[0][1].splitlines()[0], "Buy the extra chemical slots for $0?")
        self.assertEqual(self.owned, 1)

    def test_drawn_with_a_tick_once_bought_and_hidden_with_the_setting_off(self) -> None:
        for owned, tick in ((0, False), (1, True)):
            emu = self.store(owned=owned)
            emu.write32(emu.sym("_upgrades_view"), 1)
            emu.call(emu.sym("_on_draw"), emu.scene)
            self.assertIn(("draw", (SHEET_CHEMICALS, 36, 598, 177)), emu.calls)
            self.assertEqual(("shadow", (0x25, 598 + 19, 177 + 22)) in emu.calls, tick)
        emu = self.store(owned=None)
        emu.write32(emu.sym("_upgrades_view"), 1)
        emu.call(emu.sym("_on_draw"), emu.scene)
        self.assertNotIn(("draw", (SHEET_CHEMICALS, 36, 598, 177)), emu.calls)
        self.click(emu, ITEM_AT)
        self.assertEqual(self.asked(emu), [])

    def test_the_tooltip_says_the_price_or_sold_out(self) -> None:
        for owned, free, text in ((0, False, "Extra Chemical Slots\nPrice: $ 10000"),
                                  (0, True, "Extra Chemical Slots\nPrice: $ 0"), (1, False, "Extra Chemical Slots\nSold out")):
            emu = self.store(owned=owned, free=free)
            emu.call(emu.sym("_chem_make_tip"), emu.scene)
            self.assertIn(("tip", text), emu.calls)

    def test_the_item_overlaps_nothing_on_the_shelf(self) -> None:
        rect = (598 + 12, 177 + 8, 598 + 57, 177 + 60)
        source = (ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c").read_text(encoding="utf-8")
        auto = (ROOT / "native" / "ftfp_plant_upgrades" / "auto_upgrades.h").read_text(encoding="utf-8")
        others = [(610, 63, 655, 115), (655 + 12, 63, 655 + 57, 115), (712 + 12, 63, 712 + 57, 115),
                  (610, 124, 655, 176), (667, 124, 712, 176), (403, 114, 461, 174), (404, 52, 461, 113)]
        self.assertIn("BOMB_Y (55 + 61)", source)
        self.assertIn("{ 667, 124, 712, 176 }", auto)
        for other in others:
            self.assertFalse(overlaps(rect, other), other)
        # Every picture the Upgrades view draws (its own on_draw, every item shown and owned), against
        # this item's picture and click rectangle.
        import render_seed_boxes_preview as R
        sheets = R.Sheets(EXE.parent)
        mine = R.visible_rect(sheets, ("sprite", SHEET_CHEMICALS, 36, 598, 177))
        self.assertTrue(mine[0] >= rect[0] and mine[2] <= rect[2] + 1 and mine[1] >= rect[1] and mine[3] <= rect[3] + 1)
        drawn = R.store_draws((1, 1, 1, 1, 1, 1), chem_slots=1)
        self.assertIn(("sprite", SHEET_CHEMICALS, 36, 598, 177), drawn)
        for d in drawn:
            if d[0] != "sprite" or (d[1], d[2], d[3], d[4]) == (SHEET_CHEMICALS, 36, 598, 177):
                continue
            other = R.visible_rect(sheets, d)
            if other is None:
                continue
            other = (other[0], other[1], other[2] - 1, other[3] - 1)
            self.assertFalse(overlaps((mine[0], mine[1], mine[2] - 1, mine[3] - 1), other), d)
            self.assertFalse(overlaps(rect, other), d)

    def test_events_go_to_the_dll(self) -> None:
        emu = self.store(owned=0)
        emu.call(emu.sym("_on_save"), emu.state, 3)
        emu.call(emu.sym("_on_delete"), 4)
        emu.call(emu.sym("_on_new_game"))
        self.assertEqual([c[0] for c in emu.chem_calls], ["FtfpChemSlotsSave", "FtfpChemSlotsDelete",
                                                          "FtfpChemSlotsNewGame"])
        self.assertEqual(emu.chem_calls[0][1], (emu.state, 3))

    def test_setting_off_page_two_goes_into_free_stock_slots_and_the_rest_waits(self) -> None:
        path = SIDECAR.format(2)
        files = {path: sidecar(1, [(30, 2), (27, 1), None, (33, 4), (34, 1), (35, 2), None, (36, 3)])}
        emu = self.store(owned=None, files=files)
        emu.uc.mem_write(emu.state + TRAY, struct.pack("<B3xii", 1, 27, 5) + bytes(12) + bytes(12)
                         + struct.pack("<B3xii", 1, 31, 1))
        emu.call(emu.sym("_chem_off_load"), 2)
        tray = [struct.unpack("<B3xii", emu.uc.mem_read(emu.state + TRAY + 12 * k, 12)) for k in range(4)]
        self.assertEqual(tray, [(1, 27, 6), (1, 30, 2), (1, 33, 4), (1, 31, 1)])   # 27 stacked, two free slots filled
        self.assertEqual(emu.files.files[path], files[path])                # unchanged until the game saves
        emu.call(emu.sym("_chem_save"), emu.state, 1)                       # another slot: not this file
        self.assertEqual(emu.files.files[path], files[path])
        emu.call(emu.sym("_chem_save"), emu.state, 2)
        self.assertEqual(emu.files.files[path], sidecar(1, [None, None, None, None, (34, 1), (35, 2), None, (36, 3)]))

    def test_setting_off_everything_fits_and_nothing_bought_the_file_goes(self) -> None:
        path = SIDECAR.format(1)
        emu = self.store(owned=None, files={path: sidecar(0, [(30, 2)] + [None] * 7)})
        emu.call(emu.sym("_chem_off_load"), 1)
        emu.call(emu.sym("_chem_save"), emu.state, 1)
        self.assertNotIn(path, emu.files.files)

    def test_setting_off_a_new_game_drops_the_old_file_at_its_save(self) -> None:
        path = SIDECAR.format(3)
        emu = self.store(owned=None, files={path: sidecar(1, [(30, 2)] + [None] * 7)})
        emu.call(emu.sym("_chem_new_game"))
        emu.call(emu.sym("_chem_save"), emu.state, 3)
        self.assertNotIn(path, emu.files.files)


# ------------------------------------------------------------------ both DLLs: the trash

def map_relocated(emu, data: bytes, base: int) -> dict[str, int]:
    """Map a second DLL at `base`, applying its base relocations; its imports become new thunks."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    opt = pe + 24
    preferred, size = struct.unpack_from("<I", data, pe + 52)[0], struct.unpack_from("<I", data, pe + 80)[0]
    count, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    emu.uc.mem_map(base, (size + 0xFFF) & ~0xFFF)
    emu.uc.mem_write(base, data[:0x1000])
    for i in range(count):
        at = opt + opt_size + i * 40
        _vs, rva, raw_size, raw = struct.unpack_from("<IIII", data, at + 8)
        emu.uc.mem_write(base + rva, data[raw:raw + raw_size])
    reloc_rva, reloc_size = struct.unpack_from("<II", data, opt + 96 + 5 * 8)
    delta, at, end = base - preferred, base + reloc_rva, base + reloc_rva + reloc_size
    while at < end:
        page, block = struct.unpack("<II", emu.uc.mem_read(at, 8))
        if block == 0:
            break
        for n in range((block - 8) // 2):
            entry = struct.unpack("<H", emu.uc.mem_read(at + 8 + 2 * n, 2))[0]
            if entry >> 12 == 3:
                where = base + page + (entry & 0xFFF)
                emu.write32(where, emu.read32(where) + delta)
        at += block
    names = {}
    imports = struct.unpack_from("<I", data, opt + 96 + 8)[0]
    at = imports
    while True:
        lookup, _t, _f, _name, iat = struct.unpack("<5I", emu.uc.mem_read(base + at, 20))
        if lookup == 0 and iat == 0:
            return names
        slot = 0
        while True:
            entry = emu.read32(base + (lookup or iat) + slot * 4)
            if entry == 0:
                break
            label = emu.cstring(base + entry + 2).decode("ascii") if not entry & 0x80000000 else f"#{entry & 0xFFFF}"
            thunk = emu.thunk()
            emu.write32(base + iat + slot * 4, thunk)
            names[label] = thunk
            slot += 1
        at += 20


@_needs()
class TrashTests(ChemSlotsCase):
    """Store Upgrades and Items' trash (PR #76) with a page-2 bottle in the hand: both DLLs' own code."""

    UPGRADES_BASE = 0x18000000
    BIN = (0xAE + 20, 0x20D + 30)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.up_tmp = tempfile.TemporaryDirectory()
        cls.up_dll, cls.up_symbols = E.build_with_map("ftfp_plant_upgrades", UPGRADES_DLL, Path(cls.up_tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        cls.up_tmp.cleanup()

    def trash(self, g: Game) -> int:
        preferred = struct.unpack_from("<I", self.up_dll.read_bytes(), struct.unpack_from("<I", self.up_dll.read_bytes(),
                                                                                         0x3C)[0] + 52)[0]
        if not hasattr(g, "up"):
            map_relocated(g.emu, self.up_dll.read_bytes(), self.UPGRADES_BASE)
            g.up = True
        chem_trash = self.up_symbols["_chem_trash"] - preferred + self.UPGRADES_BASE
        return g.emu.call(chem_trash, g.scene, *self.BIN) & 0xFF

    def test_the_upgrades_chemicals_go_in_the_trash_from_page_two(self) -> None:
        for chemical in (FORMULA, REVIVAL, REVITA, BOMB, MUTA_FLOWER, MUTA_FOLIAGE):
            with self.subTest(chemical=chemical):
                g = self.game()
                for k in range(4):
                    g.put(k, 27 + k, 2)
                g.put2(4, chemical, 3)
                g.put2(5, 33, 1)
                g.press(211, 190)
                g.press(*page2_point(4))
                g.calls.clear()
                self.assertEqual(self.trash(g), 1)
                self.assertIn(("sound", (TRASH_BIN,)), g.calls)
                self.assertEqual(g.held(), 0)
                g.draw()
                self.assertEqual(g.tray(), [(27 + k, 2) for k in range(4)])     # page 1 untouched
                self.assertEqual(g.page2(), [None] * 4 + [None, (33, 1), None, None])

    def test_the_games_own_chemicals_stay_in_the_hand(self) -> None:
        g = self.game()
        g.put2(2, 30, 3)
        g.press(211, 190)
        g.press(*page2_point(2))
        held = g.held()
        self.assertEqual(self.trash(g), 0)
        self.assertEqual(g.held(), held)
        g.draw()
        self.assertEqual(g.tray()[held - 5], (30, 3))


def patched_exe(enabled: set[str]) -> Path:
    """The executable the patcher writes for these settings (manifest patches; no loader needed here)."""
    import plant_patcher
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data, _ = plant_patcher.apply_patch_bytes(EXE.read_bytes(), plant_patcher.active_patch_records(manifest, enabled))
    path = Path(tempfile.mkdtemp(prefix="ftfp_chem_exe_")) / "Plant Tycoon.exe"
    path.write_bytes(data)
    return path


def buy(g: Game, chemical: int, table_doses: int, price: int = 100, start: int = 0x00432E1D) -> list[int]:
    """The purchase dialog's chemical Buy (0x432E1D-0x432E5A, ebp = the dialog): the charge, then the
    doses from the store's item table (state + 0x8DC, shelf row 0, column 0), into the tray (0x416410).
    Returns the cash changes it made."""
    emu = g.emu
    dialog = emu.alloc(0x100)
    emu.write32(dialog + 0x74, g.state)
    emu.write32(dialog + 0x78, g.tray_obj)
    emu.write32(dialog + 0x84, price)
    emu.write32(dialog + 0x94, 0)
    emu.write32(dialog + 0x98, 0)
    emu.write32(dialog + 0xB8, chemical)
    emu.write32(g.state + 0x8DC, table_doses)
    paid = []
    emu.hook(0x0041ED70, lambda e: (paid.append(e.arg(0) - (1 << 32) if e.arg(0) >> 31 else e.arg(0)), 0)[1], 4)
    emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x2000)
    emu.uc.reg_write(X.UC_X86_REG_EBP, dialog)
    emu.uc.emu_start(start, 0x00432E5A, count=200_000)
    return paid


def tip_of(g: Game, g_slot: int) -> str | None:
    """The tooltip shown over slot g (0-3 page 1, 4-11 page 2) after a frame, on its page."""
    if (g_slot >= 4) != (g.page() == 1):
        g.press(*([a + 8 for a in ARROW[:2]]))
    g.draw()
    r = ((20 + 45 * g_slot, 173, 47 + 45 * g_slot, 253) if g_slot < 4 else
         (20 + 45 * ((g_slot - 4) % 4), (136, 185)[(g_slot - 4) // 4], 47 + 45 * ((g_slot - 4) % 4),
          (184, 253)[(g_slot - 4) // 4]))
    return g.visible_tips().get(r)


@_needs()
class TooltipDosesAreTheGamesTests(ChemSlotsCase):
    """The owner: the tooltips are patch-accurate. A bottle's doses live only in its tray record
    (present, id, doses): the Buy writes them there (the store's item table, state + 0x8DC, or Store
    Upgrades and Items' 3 for its four), each use takes one (0x416540, the use switch's 0x426699), and
    the tray drops the bottle at 0 (0x416500). The tooltips read that record, so they say what the game
    will give, whatever the settings. These tests run each Plant setting that touches a chemical's
    doses, uses or stacking, and check that no other one touches them."""

    def test_stock_doses_are_the_store_tables_and_each_use_takes_one(self) -> None:
        g = self.game()
        for doses in (1, 4, 7):
            with self.subTest(doses=doses):
                g.emu.uc.mem_write(g.state + TRAY, bytes(12))
                buy(g, 30, doses)
                self.assertEqual(g.tray()[0], (30, doses))
                self.assertEqual(tip_of(g, 0), f"Chemical 30\n{doses} {'dose' if doses == 1 else 'doses'} left")
                dose(g, 30)
                self.assertEqual(tip_of(g, 0), None if doses == 1 else
                                 f"Chemical 30\n{doses - 1} {'dose' if doses == 2 else 'doses'} left")

    def test_extra_chemical_slots_buying_stacks_onto_the_bottle_on_either_page(self) -> None:
        g = self.game()
        g.put2(5, 31, 2)
        buy(g, 31, 4)
        self.assertEqual(g.page2()[5], (31, 6))
        self.assertEqual(tip_of(g, 4 + 5), "Chemical 31\n6 doses left")
        g.press(*page2_point(5))                               # used from page 2: the same record
        dose(g, 31)
        use_tail(g)
        g.press(*page2_point(5))
        land(g)
        self.assertEqual(tip_of(g, 4 + 5), "Chemical 31\n5 doses left")
        g.put(2, 32, 1)
        buy(g, 32, 3)
        self.assertEqual(tip_of(g, 2), "Chemical 32\n4 doses left")

    def test_add_new_store_upgrades_and_items_gives_its_four_three_doses(self) -> None:
        preferred = struct.unpack_from("<I", UPGRADES_DLL.read_bytes(),
                                       struct.unpack_from("<I", UPGRADES_DLL.read_bytes(), 0x3C)[0] + 52)[0]
        with tempfile.TemporaryDirectory() as tmp:
            up_dll, up_symbols = E.build_with_map("ftfp_plant_upgrades", UPGRADES_DLL, Path(tmp))
            for chemical in (FORMULA, REVIVAL, REVITA, BOMB):
                with self.subTest(chemical=chemical):
                    g = self.game()
                    base = 0x18000000
                    map_relocated(g.emu, up_dll.read_bytes(), base)
                    at = lambda name_: up_symbols[name_] - preferred + base
                    g.emu.write8(at("_upgrade_dialog"), 1)                   # bought on the Upgrades view
                    g.emu.uc.mem_write(0x00432E43, b"\xE9" + struct.pack("<i", at("_stub_chem_doses") - 0x00432E48)
                                       + b"\x90\x90")
                    g.put2(0, 27, 1)
                    buy(g, chemical, 9)                                      # the stock table would say 9
                    self.assertEqual(g.tray()[0], (chemical, 3))
                    self.assertEqual(tip_of(g, 0).splitlines()[1], "3 doses left")
                    buy(g, chemical, 9)                                      # a second purchase stacks: 6
                    self.assertEqual(tip_of(g, 0).splitlines()[1], "6 doses left")

    def test_free_upgrades_and_everything_free_change_the_price_never_the_doses(self) -> None:
        exe = patched_exe({"everything_free", "free_upgrades", "plant_upgrades", "new_flowers"})
        g = self.game(exe=exe)
        paid = buy(g, 33, 5, price=750)
        self.assertEqual(paid, [0])                                          # Everything is Free: $0
        self.assertEqual(tip_of(g, 0), "Chemical 33\n5 doses left")
        g = self.game()
        self.assertEqual(buy(g, 33, 5, price=750), [-750])                   # the vanilla charge, same doses
        self.assertEqual(tip_of(g, 0), "Chemical 33\n5 doses left")

    def test_no_other_patch_or_companion_touches_a_dose(self) -> None:
        """Every Plant setting: its manifest patches and its DLLs' sites. Only these may touch the tray's
        functions, the Buy's dose read and add, the dose taken by a use and the use's tail."""
        dose_code = [(0x416340, 0x416730, "the tray's functions"), (0x432E2E, 0x432E5A, "the Buy's doses"),
                     (0x426690, 0x4266A6, "the use's dose"), (0x42720B, 0x427258, "the use's tail")]
        allowed = {("ftfp_plant_upgrades", 0x432E43), ("ftfp_chem_slots", 0x416410), ("ftfp_chem_slots", 0x4164B0)}
        touching = set()
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for patch in manifest["patches"]:
            start = int(patch["offset"], 16) + 0x400000
            end = start + len(bytes.fromhex(patch["replacement"].replace(" ", "")))
            for a, b, _what in dose_code:
                if start < b and a < end:
                    touching.add((patch["id"], start))
        plant_dlls = ("ftfp_new_flowers", "ftfp_plant_upgrades", "ftfp_seed_boxes", "ftfp_extra_greenhouses",
                      "ftfp_greenhouse_counts", "ftfp_sort_seeds", "ftfp_plant_prices", "ftfp_chem_slots")
        for header in sorted((ROOT / "native").glob("ftfp_*/*sites*.h")):
            if header.parent.name not in plant_dlls:
                continue
            text = header.read_text(encoding="utf-8")
            for m in re.finditer(r"#define SITE_(\w+)_VA 0x([0-9A-Fa-f]+)u", text):
                va = int(m.group(2), 16)
                n = re.search(rf"#define SITE_{m.group(1)}_LEN (\d+)", text)
                end = va + (int(n.group(1)) if n else 4)
                for a, b, _what in dose_code:
                    if va < b and a < end:
                        touching.add((header.parent.name, va))
        self.assertEqual(touching, allowed)
        counts = (ROOT / "native" / "ftfp_greenhouse_counts" / "ftfp_greenhouse_counts.c").read_text(encoding="utf-8")
        self.assertIn("HELD_SITE_VA 0x004291D2u", counts)                     # its one code site, elsewhere


@_needs()
class ArtAndManifestTests(unittest.TestCase):
    def test_the_sheet_has_the_item_and_the_arrows(self) -> None:
        from PIL import Image
        sheet = Image.open(SHEET).convert("RGBA")
        self.assertEqual(sheet.size, (140, 23 * 70))                    # rows 21-22: Muta-Flower, Muta-Foliage
        cell = lambda f: sheet.crop(((f % 2) * 70, (f // 2) * 70, (f % 2) * 70 + 70, (f // 2) * 70 + 70))
        box = cell(36).getbbox()
        self.assertTrue(box[0] >= 12 and box[2] <= 58 and box[1] >= 8 and box[3] <= 61, box)     # in its click rectangle
        for f in (38, 39):
            self.assertEqual(cell(f).getbbox(), (0, 0, ARROW[2], ARROW[3]))
        import build_plant_upgrades_assets as B
        rebuilt = B.formula_bottle(EXE.parent / "Images")
        self.assertEqual(rebuilt.tobytes(), sheet.tobytes())

    def test_the_arrows_and_page_number_are_clear_of_everything(self) -> None:
        arrow = (ARROW[0], ARROW[1], ARROW[0] + ARROW[2] - 1, ARROW[1] + ARROW[3] - 1)
        left = (ARROW_LEFT_HIT[0], ARROW_LEFT_HIT[1], ARROW_LEFT_HIT[0] + ARROW_LEFT_HIT[2] - 1,
                ARROW_LEFT_HIT[1] + ARROW_LEFT_HIT[3] - 1)
        import render_extra_greenhouses_preview as RG
        size = RG.words(EXE.parent, EXE.read_bytes(), "2/2").size                    # in PTfontsmall, + shadow
        text = (PAGE_TEXT[0], PAGE_TEXT[1], PAGE_TEXT[0] + size[0], PAGE_TEXT[1] + size[1])
        tools = [(18 + 45 * k, 136, 63 + 45 * k, 181) for k in range(4)]                  # 0x423AA0
        slots = [(20 + 45 * i, 136, 47 + 45 * i, 253) for i in range(4)]                  # both pages
        seeds = [(21 + 43 * c, 30 + 34 * r, 64 + 43 * c, 64 + 34 * r) for c in range(4) for r in range(2)]   # 0x423A10
        side_arrows = [(220, 236, 269, 285)]                                             # Extra Greenhouses
        buttons = [(47, 293, 94, 330), (130, 287, 187, 324)]                              # 0x42614A, 0x42629C
        for thing in (arrow, left, text):
            for other in tools + slots + seeds + side_arrows + buttons:
                self.assertFalse(overlaps(thing, other), (thing, other))
        self.assertFalse(overlaps(arrow, text))
        self.assertLess(ARROW_LEFT[0] + ARROW_LEFT[2], 25)                               # left of the soil's picture

    def test_the_setting(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        ids = [s["id"] for s in manifest["settings"]]
        setting = next(s for s in manifest["settings"] if s["id"] == "extra_chemical_slots")
        self.assertEqual((setting["name"], setting["default"], setting["experimental"], setting["requires_settings"]),
                         ("Extra chemical slots", True, True, ["plant_upgrades"]))
        self.assertTrue(setting["summary"].startswith("EXPERIMENTAL - USE AT OWN RISK."))
        self.assertEqual(ids, ["fix_vanilla_bugs", "no_old_age_plant_deaths", "seed_refresh_key", "add_missing_ldw_assets",
                               "tank_greenhouse_counts", "new_flowers", "plant_upgrades", "sort_seeds", "optimize_prices",
                               "time_warp", "free_upgrades", "add_money", "everything_free", "extra_greenhouses",
                               "extra_nurseries",
                               "extra_chemical_slots", "unicode_ingame_fonts", "translations"])
        files = setting["companion"]["files"]
        data = DLL.read_bytes()
        import hashlib
        self.assertEqual(files, [{"path": "Extra Chemical Slots.dll",
                                  "destination": "Plant Tycoon Fix Patcher DLLs/Extra Chemical Slots.dll",
                                  "size": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}])
        self.assertTrue(setting["companion"]["startup_loader"])

    def test_every_combination_with_the_upgrades_has_a_pin_with_and_without_it(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        pins = manifest["patched_sha256_by_settings"]
        without = [k for k in pins if "plant_upgrades" in k.split(",") and "extra_chemical_slots" not in k.split(",")]
        for key in without:
            self.assertIn(",".join(sorted(set(key.split(",")) | {"extra_chemical_slots"})), pins, key)
        self.assertFalse([k for k in pins if "extra_chemical_slots" in k.split(",") and "plant_upgrades" not in k.split(",")])
        import fish_patcher
        everything = ",".join(sorted(fish_patcher.pin_settings(manifest, {
            s["id"] for s in manifest["settings"] if s["id"] != "add_missing_ldw_assets"})))
        self.assertIn(everything, pins)

    def test_the_enable_all_executable_is_its_pin(self) -> None:
        import fish_patcher
        import plant_patcher
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        enabled = fish_patcher.pin_settings(manifest, {s["id"] for s in manifest["settings"]})
        patched, _ = plant_patcher.apply_patch_bytes(EXE.read_bytes(), plant_patcher.active_patch_records(manifest, enabled))
        patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.plant_profile(enabled))
        import hashlib
        self.assertEqual(hashlib.sha256(patched).hexdigest().upper(),
                         manifest["patched_sha256_by_settings"][plant_patcher.settings_key(enabled, manifest)])

    def test_backups_know_the_file(self) -> None:
        import save_backup
        for name_ in ("Extra Chemical Slots 3.dat", "Extra Chemical Slots 3.dat.tmp",
                      "Extra Chemical Slots 3.dat.unreadable-2"):
            self.assertEqual(save_backup._SIDE_FILE_SLOT.search(name_).group(1), "3", name_)
