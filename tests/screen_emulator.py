"""A game's screen and dialog constructors run in Unicorn on the vanilla executable, with the
buttons they make and the labels they give them recorded. Picture Studio's "Screens, bars and
buttons" tests compare these records with pictures_screens's placements.

What runs is the game's machine code: the constructor and everything it calls, except
* the button constructor and its label setters, recorded and not run (their arguments are
  what the test wants: the button's id, sprite, place, label, colours and font);
* the string lookup, which hands back the English line from the string table;
* operator new, which hands out zeroed memory, and the game's sprite getter, which hands
  back a marker for the sprite id;
* the Windows and SDL imports, which do nothing and return 0 (each pops the arguments its
  caller pushed, so the stack stays as the caller expects).
Memory the game reads that was never set up is mapped on first touch, zeroed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import struct
import sys

try:
    import capstone
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_FETCH_UNMAPPED, UC_HOOK_MEM_READ_UNMAPPED, UC_HOOK_MEM_WRITE_UNMAPPED
    from unicorn import x86_const as X
except ImportError:              # CI installs neither: the tests that use this skip
    capstone = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import translation_strings as ts  # noqa: E402

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
if capstone is not None:
    from store_emulator import Emulator  # noqa: E402

SPRITE_MARK = 0x7F000000

EXES = {"fish": VANILLA / "Fish Tycoon" / "Fish Tycoon.exe", "plant": VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"}


@dataclass
class Button:
    obj: int
    id: int
    sprite: int | None
    x: int
    y: int
    label: str | None = None
    colours: tuple = ()
    font: int = 0


@dataclass(frozen=True)
class Game:
    new: int
    lookup: int            # thiscall string lookup (id) -> char*
    sprite: int            # thiscall sprite getter (id) -> sprite
    button: int            # thiscall button constructor (id, sprite, x, y, parent, extra)
    label: int             # thiscall label setter (text, normal, over, pressed, font)
    quiet: tuple = ()      # (address, pop): calls that do nothing here (free, image loading)


GAMES = {
    "fish": Game(0x42A793, 0x427050, 0x41BC90, 0x401BD0, 0, ((0x42A6B1, 0), (0x409540, 4), (0x409AB0, 4), (0x409F00, 0), (0x4251A0, 0))),
    "plant": Game(0x44E894, 0x44CA70, 0x420460, 0x401B60, 0x401570,
                  ((0x44E7B3, 0), (0x420550, 4), (0x40A4D0, 4))),
}


def available(game: str = "plant") -> bool:
    try:
        import pefile  # noqa: F401
    except ImportError:
        return False
    return capstone is not None and EXES[game].is_file()


class ScreenEmulator:
    def __init__(self, game: str = "plant") -> None:
        self.game = game
        g = self.g = GAMES[game]
        exe = EXES[game].read_bytes()
        emu = self.emu = Emulator(EXES[game], None, {})
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        emu.uc.mem_map(0, 0x400000)           # null objects' fields read as 0
        emu.uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED | UC_HOOK_MEM_WRITE_UNMAPPED | UC_HOOK_MEM_FETCH_UNMAPPED,
                        self._map_zero)
        self.buttons: dict[int, Button] = {}
        self.order: list[Button] = []
        self.strings = {s.id: s.english for s in ts.read_table(game, exe)}
        self._string_at: dict[int, int] = {}
        emu.hook(g.new, lambda e: self._zeroed(max(1, e.arg(0))), 0)
        emu.hook(g.lookup, self._lookup, 4)
        emu.hook(g.sprite, lambda e: SPRITE_MARK | e.arg(0), 4)
        emu.hook(g.button, self._button, 0x18)
        if g.label:
            emu.hook(g.label, self._label, 0x14)
        self.calls: list = []
        for address, pop in g.quiet:
            emu.hook(address, lambda e: 0, pop)
        self._stub_imports(exe)
        import pefile
        pe = pefile.PE(data=exe, fast_load=True)
        text = next(sec for sec in pe.sections if sec.Characteristics & 0x20000000)
        self.text = (0x400000 + text.VirtualAddress, 0x400000 + text.VirtualAddress + text.Misc_VirtualSize)
        self.globals = self.fill_singletons(text.get_data(), self.text[0])
        emu.uc.hook_add(UC_HOOK_CODE, self._outside)

    def _outside(self, uc, address, _size, _data) -> None:
        """A call into memory that holds no code (a zeroed object's method): return 0 at once."""
        lo, hi = self.text
        if lo <= address < hi or 0x30000000 <= address < 0x30010000:
            return
        esp = uc.reg_read(X.UC_X86_REG_ESP)
        back = self.emu.read32(esp)
        if not lo <= back < hi:
            raise RuntimeError(f"ran into {address:#x} not from a call")
        pop = self._pushed_before(back)
        uc.reg_write(X.UC_X86_REG_EAX, 0)
        uc.reg_write(X.UC_X86_REG_ESP, esp + 4 + pop)
        uc.reg_write(X.UC_X86_REG_EIP, back)

    # ---- memory
    def _zeroed(self, size: int) -> int:
        address = self.emu.alloc(size + 0x100)
        self.emu.uc.mem_write(address, bytes(size + 0x100))
        return address

    def _map_zero(self, uc, _access, address, _size, _value, _data) -> bool:
        page = address & ~0xFFF
        try:
            uc.mem_map(page, 0x1000)
        except Exception:              # noqa: BLE001  already mapped (a race of two hooks)
            return False
        return True

    # ---- imports: every IAT slot points at a thunk that pops what its caller pushed
    def _stub_imports(self, exe: bytes) -> None:
        import pefile
        pe = pefile.PE(data=exe, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        emu = self.emu
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            stdcall = not entry.dll.lower().startswith((b"sdl", b"msvcr", b"msvcp"))
            for imp in entry.imports:
                thunk = emu.thunk()
                emu.write32(imp.address, thunk)
                emu.hook(thunk, self._stdcall_stub if stdcall else (lambda e: 0), 0)

    def _stdcall_stub(self, emu: Emulator) -> int:
        """A Windows import: pop what the caller pushed (moving the return address up)."""
        esp = emu.uc.reg_read(X.UC_X86_REG_ESP)
        back = emu.read32(esp)
        pop = self._pushed_before(back)
        if pop:
            emu.write32(esp + pop, back)
            emu.uc.reg_write(X.UC_X86_REG_ESP, esp + pop)
        return 0

    def _pushed_before(self, back: int) -> int:
        """The bytes the caller pushed for the call that returns to `back` (its pushes since the
        last call or stack adjustment)."""
        code = bytes(self.emu.uc.mem_read(back - 0x60, 0x60))
        best = 0
        for start in range(0x60):
            ins = list(self.md.disasm(code[start:], back - 0x60 + start))
            if ins and ins[-1].address + ins[-1].size == back and ins[-1].mnemonic == "call":
                pushes = 0
                for i in reversed(ins[:-1]):
                    if i.mnemonic == "push":
                        pushes += 4
                    elif i.mnemonic in ("call", "ret") or (i.mnemonic in ("add", "sub") and i.op_str.startswith("esp")):
                        break
                best = pushes
                break
        return best

    # ---- hooks
    def _lookup(self, emu: Emulator) -> int:
        ident = emu.arg(0)
        if ident not in self._string_at:
            self._string_at[ident] = emu.text(self.strings.get(ident, f"<{ident:#x}>"))
        return self._string_at[ident]

    def _button(self, emu: Emulator) -> int:
        this = emu.uc.reg_read(X.UC_X86_REG_ECX)
        sprite = emu.arg(1)
        b = Button(this, emu.arg(0), sprite & 0xFFFF if sprite & 0xFF000000 == SPRITE_MARK else None,
                   struct.unpack("<i", struct.pack("<I", emu.arg(2)))[0],
                   struct.unpack("<i", struct.pack("<I", emu.arg(3)))[0])
        self.buttons[this] = b
        self.order.append(b)
        emu.write32(this + 0x10, this)
        return this

    def _label(self, emu: Emulator) -> int:
        this = emu.uc.reg_read(X.UC_X86_REG_ECX)
        b = self.buttons.get(this)
        text = emu.cstring(emu.arg(0)).decode("cp1252")
        if b is None:
            b = self.buttons[this] = Button(this, -1, None, 0, 0)
            self.order.append(b)
        b.label, b.colours, b.font = text, (emu.arg(1), emu.arg(2), emu.arg(3)), emu.arg(4)
        return 0

    def fill_singletons(self, exe_text: bytes, base: int, size: int = 0x10000) -> list:
        """Every lazily made global object (`mov eax, [G]; test eax, eax` and, a little later,
        `mov [G], eax`) is made up front, zeroed, so no getter runs its maker (which loads files)."""
        import re
        made = []
        for m in re.finditer(rb"\xA3(....)", exe_text, re.S):
            g = m.group(1)
            if exe_text.find(b"\xA1" + g + b"\x85\xC0", max(0, m.start() - 0x60), m.start()) < 0:
                continue
            g = struct.unpack("<I", g)[0]
            if g not in made and self.emu.read32(g) == 0:
                self.emu.write32(g, self._zeroed(size))
                made.append(g)
        return made

    def record(self, address: int, pop: int, args: int, result: int | None = None) -> None:
        """Calls of this function are recorded (address, this, args) and not run; it returns
        `this` (or `result`)."""
        def handler(emu):
            this = emu.uc.reg_read(X.UC_X86_REG_ECX)
            self.calls.append((address, this, tuple(struct.unpack("<i", struct.pack("<I", emu.arg(i)))[0]
                                                    for i in range(args))))
            return this if result is None else result
        self.emu.hook(address, handler, pop)

    # ---- running
    def construct(self, ctor: int, *args: int, size: int = 0x2000) -> int:
        this = self._zeroed(size)
        self.emu.call(ctor, *args, ecx=this)
        return this
