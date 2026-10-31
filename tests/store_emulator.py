"""Run a store DLL's own code against the real game executable in Unicorn.

The DLL is rebuilt from its committed source with the flags of its build
script plus /MAP (the map file names its static functions and variables; the
DLL itself comes out byte-for-byte the same), the vanilla executable and the
DLL are mapped at their image bases, and chosen game functions and the DLL's
Windows imports are replaced by Python hooks. Everything else is the game's
and the DLL's own machine code.
"""

from __future__ import annotations

import re
import gc
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
from unicorn import x86_const as X

ROOT = Path(__file__).resolve().parents[1]
MSVC = Path(r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231")
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10")
SDK_VERSION = "10.0.26100.0"
VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"

STACK, STACK_SIZE = 0x0F000000, 0x00100000
HEAP, HEAP_SIZE = 0x20000000, 0x01000000
THUNKS, THUNK_SIZE = 0x30000000, 0x00010000
RETURN = THUNKS + THUNK_SIZE - 0x10


def toolchain_ready() -> bool:
    return (MSVC / "bin" / "Hostx64" / "x86" / "cl.exe").is_file()


def build_with_map(project: str, committed: Path, out: Path,
                   link: tuple[str, ...] = ()) -> tuple[Path, dict[str, int]]:
    """Rebuild native/<project>/<project>.c; return the DLL and its map's symbols. `link`: the
    build script's own extra linker flags (Extra Supply Slots' /BASE, so it maps beside another)."""
    native = ROOT / "native" / project
    command = [
        str(MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/LD", "/O2", "/MT", "/W4", "/WX",
        "/GS-", "/Brepro", f"/Fo{out}\\",
        "/I", str(MSVC / "include"),
        "/I", str(SDK / "Include" / SDK_VERSION / "um"),
        "/I", str(SDK / "Include" / SDK_VERSION / "shared"),
        "/I", str(SDK / "Include" / SDK_VERSION / "ucrt"),
        str(native / f"{project}.c"),
        "/link", "/Brepro", f"/DEF:{native / (project + '.def')}",
        f"/LIBPATH:{MSVC / 'lib' / 'x86'}",
        f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'um' / 'x86'}",
        f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'ucrt' / 'x86'}",
        f"/IMPLIB:{out / (project + '.lib')}", f"/OUT:{out / 'rebuilt.dll'}", f"/MAP:{out / 'rebuilt.map'}",
        *link, "/RELEASE", "/SAFESEH:NO", "kernel32.lib", "user32.lib",
    ]
    result = subprocess.run(command, cwd=out, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    dll = out / "rebuilt.dll"
    if dll.read_bytes() != committed.read_bytes():
        raise AssertionError(f"the committed {committed.name} is not what its source builds to; rebuild and re-pin")
    symbols = {}
    for line in (out / "rebuilt.map").read_text(encoding="latin-1").splitlines():
        match = re.match(r"\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+(\S+)\s+([0-9A-Fa-f]{8})\b", line)
        if match:
            symbols.setdefault(match.group(1), int(match.group(2), 16))
    return dll, symbols


def pe_image(data: bytes) -> tuple[int, int, list[tuple[int, int, int]], int]:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 52)[0]
    size = struct.unpack_from("<I", data, pe + 80)[0]
    imports = struct.unpack_from("<I", data, pe + 24 + 104)[0]
    sections = []
    for i in range(count):
        at = pe + 24 + optional + i * 40
        _vsize, rva, raw_size, raw = struct.unpack_from("<IIII", data, at + 8)
        sections.append((rva, raw, raw_size))
    return base, size, sections, imports


class Emulator:
    # An emulator's code hook refers back to it, so only the cycle collector frees one, and Unicorn's
    # memory is not what makes Python collect: the full suite builds thousands and once ran out of
    # memory (UC_ERR_NOMEM). Collect every so often.
    _built = 0

    def __init__(self, exe: Path, dll: Path | None, symbols: dict[str, int]) -> None:
        Emulator._built += 1
        if Emulator._built % 16 == 0:
            gc.collect()
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.symbols = symbols
        self.hooks: dict[int, tuple[Callable[["Emulator"], int], int]] = {}
        self.calls: list[tuple[str, tuple]] = []
        self.heap_top = HEAP
        self.next_thunk = THUNKS
        self.uc.mem_map(STACK, STACK_SIZE)
        self.uc.mem_map(HEAP, HEAP_SIZE)
        self.uc.mem_map(THUNKS, THUNK_SIZE)
        self.uc.mem_write(THUNKS, b"\xC3" * THUNK_SIZE)
        self._map(exe.read_bytes())
        self.imports = self._map(dll.read_bytes(), resolve=True) if dll is not None else {}
        self.uc.hook_add(UC_HOOK_CODE, self._on_code)
        self.hook_import("VirtualQuery", Emulator._virtual_query, 12)

    def _virtual_query(self) -> int:
        """Every page asked about is committed, readable code (the DLLs check the game's bytes)."""
        address, info = self.arg(0), self.arg(1)
        self.uc.mem_write(info, struct.pack("<7I", address & ~0xFFF, address & ~0xFFF, 0x20, 0x1000,
                                            0x1000, 0x20, 0x1000000))
        return 28

    # ---------------------------------------------------------- images
    def _map(self, data: bytes, resolve: bool = False) -> dict[str, int]:
        base, size, sections, imports = pe_image(data)
        self.uc.mem_map(base, (size + 0xFFF) & ~0xFFF)
        self.uc.mem_write(base, data[:0x1000])
        for rva, raw, raw_size in sections:
            self.uc.mem_write(base + rva, data[raw:raw + raw_size])
        names: dict[str, int] = {}
        if not resolve:
            return names
        at = imports
        while True:
            lookup, _t, _f, _name, iat = struct.unpack("<5I", self.uc.mem_read(base + at, 20))
            if lookup == 0 and iat == 0:
                return names
            slot = 0
            while True:
                entry = struct.unpack("<I", self.uc.mem_read(base + (lookup or iat) + slot * 4, 4))[0]
                if entry == 0:
                    break
                name = self.cstring(base + entry + 2).decode("ascii") if not entry & 0x80000000 else f"#{entry & 0xFFFF}"
                thunk = self.thunk()
                self.write32(base + iat + slot * 4, thunk)
                names[name] = thunk
                slot += 1
            at += 20

    def thunk(self) -> int:
        address = self.next_thunk
        self.next_thunk += 0x10
        return address

    # ---------------------------------------------------------- memory
    def alloc(self, size: int) -> int:
        address = self.heap_top
        self.heap_top += (size + 0xF) & ~0xF
        return address

    def read32(self, address: int, signed: bool = False) -> int:
        return struct.unpack("<i" if signed else "<I", self.uc.mem_read(address, 4))[0]

    def write32(self, address: int, value: int) -> None:
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def write8(self, address: int, value: int) -> None:
        self.uc.mem_write(address, bytes([value & 0xFF]))

    def cstring(self, address: int) -> bytes:
        out = bytearray()
        while True:
            b = self.uc.mem_read(address + len(out), 1)[0]
            if b == 0:
                return bytes(out)
            out.append(b)

    def wstring(self, address: int) -> str:
        out = []
        while True:
            c = struct.unpack("<H", self.uc.mem_read(address + 2 * len(out), 2))[0]
            if c == 0:
                return "".join(out)
            out.append(chr(c))

    def text(self, value: str) -> int:
        data = value.encode("latin-1") + b"\0"
        address = self.alloc(len(data))
        self.uc.mem_write(address, data)
        return address

    def sym(self, name: str) -> int:
        return self.symbols[name]

    # ---------------------------------------------------------- hooks
    def arg(self, n: int) -> int:
        """The n-th stack argument (0-based) of the hooked call."""
        return self.read32(self.uc.reg_read(X.UC_X86_REG_ESP) + 4 + 4 * n)

    def hook(self, address: int, handler: Callable[["Emulator"], int], pop: int = 0) -> None:
        """Replace the function at address: handler's result goes in eax, then `ret pop`."""
        self.hooks[address] = (handler, pop)

    def hook_import(self, name: str, handler: Callable[["Emulator"], int], pop: int) -> None:
        if name in self.imports:
            self.hook(self.imports[name], handler, pop)

    def record(self, label: str, result: int = 0, pop: int = 0, args: int = 0) -> Callable[["Emulator"], int]:
        def handler(emu: "Emulator") -> int:
            emu.calls.append((label, tuple(emu.arg(i) for i in range(args))))
            return result
        return handler

    def _on_code(self, uc: Uc, address: int, _size: int, _data: object) -> None:
        if address == RETURN:
            uc.emu_stop()
            return
        hooked = self.hooks.get(address)
        if hooked is None:
            if THUNKS <= address < THUNKS + THUNK_SIZE:
                names = [name for name, thunk in self.imports.items() if thunk == address]
                raise AssertionError(f"unhooked import {names or hex(address)}")
            return
        handler, pop = hooked
        result = handler(self)
        esp = uc.reg_read(X.UC_X86_REG_ESP)
        back = self.read32(esp)
        uc.reg_write(X.UC_X86_REG_EAX, result & 0xFFFFFFFF)
        uc.reg_write(X.UC_X86_REG_ESP, esp + 4 + pop)
        uc.reg_write(X.UC_X86_REG_EIP, back)

    def call(self, address: int, *args: int, ecx: int = 0, edx: int = 0, esi: int = 0) -> int:
        esp = STACK + STACK_SIZE - 0x1000
        for value in reversed(args):
            esp -= 4
            self.write32(esp, value)
        esp -= 4
        self.write32(esp, RETURN)
        self.uc.reg_write(X.UC_X86_REG_ESP, esp)
        self.uc.reg_write(X.UC_X86_REG_ECX, ecx)
        self.uc.reg_write(X.UC_X86_REG_EDX, edx)
        self.uc.reg_write(X.UC_X86_REG_ESI, esi)
        self.uc.reg_write(X.UC_X86_REG_FPCW, 0x027F)          # Windows' x87 default: 53-bit doubles
        self.uc.emu_start(address, RETURN, count=5_000_000)
        return self.uc.reg_read(X.UC_X86_REG_EAX)

    def run_until(self, start: int, stop: int, esi: int = 0) -> None:
        """Run a naked stub from start until it jumps to stop (its way back into the game)."""
        self.uc.reg_write(X.UC_X86_REG_ESP, STACK + STACK_SIZE - 0x1000)
        self.uc.reg_write(X.UC_X86_REG_ESI, esi)
        self.uc.emu_start(start, stop, count=100_000)

    # ---------------------------------------------------------- Fish Tycoon's save load
    def hook_fish_save_read(self, body: bytes) -> None:
        """Fish Tycoon's Load (0x41AE70) reads `body` (a save file without its 0x18-byte header):
        the file read 0x403350 (thiscall buffer, size, slot) and the CRT memcpy 0x42CB10."""
        def read(emu: "Emulator") -> int:
            buffer, size = emu.arg(0), emu.arg(1)
            emu.uc.mem_write(buffer, bytes(body[:size]))
            return 1

        def memcpy(emu: "Emulator") -> int:
            target, source, size = emu.arg(0), emu.arg(1), emu.arg(2)
            emu.uc.mem_write(target, bytes(emu.uc.mem_read(source, size)))
            return target
        self.hook(0x00403350, read, 12)
        self.hook(0x0042CB10, memcpy, 0)

    # ---------------------------------------------------------- the CRT's printf
    def hook_printf(self) -> None:
        """sprintf_s / swprintf_s end in the static UCRT's __stdio_common_v*printf_s,
        which needs the CRT's start-up; these format %d / %i / %s in Python."""
        for name, wide in (("___stdio_common_vsprintf_s", False), ("___stdio_common_vswprintf_s", True)):
            if name in self.symbols:
                self.hook(self.symbols[name], lambda emu, w=wide: emu._printf(w))

    def _printf(self, wide: bool) -> int:
        buffer, count, fmt, args = self.arg(2), self.arg(3), self.arg(4), self.arg(6)
        template = self.wstring(fmt) if wide else self.cstring(fmt).decode("latin-1")
        out, cursor = [], args

        def value(match: re.Match) -> str:
            nonlocal cursor
            kind = match.group(1)
            raw = self.read32(cursor, signed=True)
            cursor += 4
            if kind in "di":
                return str(raw)
            pointer = raw & 0xFFFFFFFF
            return self.wstring(pointer) if wide else self.cstring(pointer).decode("latin-1")

        text = re.sub(r"%([dis])", value, template.replace("%%", "\x00")).replace("\x00", "%")
        out.append(text)
        result = "".join(out)[: count - 1]
        if wide:
            self.uc.mem_write(buffer, result.encode("utf-16-le") + b"\0\0")
        else:
            self.uc.mem_write(buffer, result.encode("latin-1") + b"\0")
        return len(result)
