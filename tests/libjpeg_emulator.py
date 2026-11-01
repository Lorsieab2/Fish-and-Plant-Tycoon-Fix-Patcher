"""Plant Tycoon's own JPEG decoder, libjpeg-9.dll (beside the game), run in Unicorn: the ground truth
for picture_formats.decode_jpeg (tests/test_picture_formats.py).

The DLL is mapped at its image base and its own machine code does the whole decode
(jpeg_std_error, jpeg_CreateDecompress, jpeg_mem_src, jpeg_read_header, jpeg_start_decompress,
jpeg_read_scanlines) with libjpeg's default settings and RGB out, as SDL2_image asks for it. Only
its C library imports (malloc, free, memcpy, memset ...) are Python. No per-instruction hook: the
imports are hooked on their thunks only, so a picture decodes in a second or two.
"""

from __future__ import annotations

from pathlib import Path
import struct

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon"
DLL = VANILLA / "libjpeg-9.dll"

STACK, STACK_SIZE = 0x0F000000, 0x00100000
HEAP, HEAP_SIZE = 0x20000000, 0x04000000
THUNKS, THUNK_SIZE = 0x30000000, 0x00010000
STOP = THUNKS + THUNK_SIZE - 0x10
JPEG_LIB_VERSION, STRUCT_SIZE = 90, 0x1C8          # jpeg_CreateDecompress's own checks
JCS_RGB = 2
OUT_COLOR_SPACE = 0x2C                              # cinfo->out_color_space


def available() -> bool:
    try:
        import unicorn  # noqa: F401
    except ImportError:
        return False
    return DLL.is_file()


class LibJpeg:
    def __init__(self) -> None:
        from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.heap = HEAP
        self.uc.mem_map(STACK, STACK_SIZE)
        self.uc.mem_map(HEAP, HEAP_SIZE)
        self.uc.mem_map(THUNKS, THUNK_SIZE)
        self.uc.mem_write(THUNKS, b"\xC3" * THUNK_SIZE)
        self.handlers: dict[int, object] = {}
        self.failed = None
        self.exports = self._map(DLL.read_bytes())
        self.uc.hook_add(UC_HOOK_CODE, self._thunk, begin=THUNKS, end=THUNKS + THUNK_SIZE - 1)
        self.mark = self.heap

    # ---------------------------------------------------------- the DLL
    def _map(self, data: bytes) -> dict:
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        count = struct.unpack_from("<H", data, pe + 6)[0]
        optional = struct.unpack_from("<H", data, pe + 20)[0]
        base = struct.unpack_from("<I", data, pe + 52)[0]
        size = struct.unpack_from("<I", data, pe + 80)[0]
        export_rva = struct.unpack_from("<I", data, pe + 24 + 96)[0]
        import_rva = struct.unpack_from("<I", data, pe + 24 + 104)[0]
        self.base = base
        self.uc.mem_map(base, (size + 0xFFF) & ~0xFFF)
        self.uc.mem_write(base, data[:0x1000])
        for i in range(count):
            at = pe + 24 + optional + i * 40
            vsize, rva, raw_size, raw = struct.unpack_from("<IIII", data, at + 8)
            self.uc.mem_write(base + rva, data[raw:raw + min(raw_size, max(vsize, raw_size))])
        # imports: every function a thunk; _iob a zeroed block
        next_thunk = THUNKS
        at = import_rva
        while True:
            lookup, _t, _f, _name, iat = struct.unpack("<5I", self.uc.mem_read(base + at, 20))
            if lookup == 0 and iat == 0:
                break
            slot = 0
            while True:
                entry = struct.unpack("<I", self.uc.mem_read(base + (lookup or iat) + slot * 4, 4))[0]
                if entry == 0:
                    break
                name = self.cstring(base + entry + 2).decode()
                if name == "_iob":
                    target = self.malloc(0x200)
                else:
                    target = next_thunk
                    self.handlers[target] = name
                    next_thunk += 4
                self.uc.mem_write(base + iat + slot * 4, struct.pack("<I", target))
                slot += 1
            at += 20
        exports = {}
        (_c, _t, _ma, _mi, _name, _base, nfuncs, nnames, funcs, names, ordinals) = struct.unpack(
            "<IIHHIIIIIII", self.uc.mem_read(base + export_rva, 40))
        for k in range(nnames):
            name_rva = struct.unpack("<I", self.uc.mem_read(base + names + 4 * k, 4))[0]
            ordinal = struct.unpack("<H", self.uc.mem_read(base + ordinals + 2 * k, 2))[0]
            func = struct.unpack("<I", self.uc.mem_read(base + funcs + 4 * ordinal, 4))[0]
            exports[self.cstring(base + name_rva).decode()] = base + func
        return exports

    # ---------------------------------------------------------- memory
    def cstring(self, address: int) -> bytes:
        out = bytearray()
        while True:
            chunk = bytes(self.uc.mem_read(address + len(out), 64))
            end = chunk.find(b"\0")
            if end >= 0:
                return bytes(out + chunk[:end])
            out += chunk

    def malloc(self, size: int) -> int:
        at = (self.heap + 15) & ~15
        self.heap = at + max(16, size)
        if self.heap > HEAP + HEAP_SIZE:
            raise MemoryError("the emulated heap is full")
        return at

    def read32(self, address: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def write32(self, address: int, value: int) -> None:
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    # ---------------------------------------------------------- the C library
    def _thunk(self, uc, address, _size, _data) -> None:
        from unicorn import x86_const as X
        if address == STOP:
            uc.emu_stop()
            return
        name = self.handlers.get(address)
        if name is None:
            return
        esp = uc.reg_read(X.UC_X86_REG_ESP)
        args = [self.read32(esp + 4 + 4 * k) for k in range(4)]
        result = 0
        if name == "malloc":
            result = self.malloc(args[0])
        elif name in ("memcpy", "memmove"):
            if args[2]:
                uc.mem_write(args[0], bytes(uc.mem_read(args[1], args[2])))
            result = args[0]
        elif name == "memset":
            if args[2]:
                uc.mem_write(args[0], bytes([args[1] & 0xFF]) * args[2])
            result = args[0]
        elif name == "strlen":
            result = len(self.cstring(args[0]))
        elif name in ("exit", "abort"):
            self.failed = name
            uc.emu_stop()
        uc.reg_write(X.UC_X86_REG_EAX, result & 0xFFFFFFFF)

    def call(self, name: str, *args: int) -> int:
        from unicorn import x86_const as X
        esp = STACK + STACK_SIZE - 0x1000
        for value in reversed((STOP,) + tuple(args)):
            esp -= 4
            self.write32(esp, value)
        self.uc.reg_write(X.UC_X86_REG_ESP, esp)
        self.uc.emu_start(self.exports[name], STOP)
        if self.failed:
            raise AssertionError(f"libjpeg stopped the decode ({self.failed})")
        return self.uc.reg_read(X.UC_X86_REG_EAX)

    # ---------------------------------------------------------- a whole picture
    def decode(self, data: bytes) -> tuple[int, int, bytes]:
        """(width, height, RGB bytes) of a JPEG, as libjpeg-9 hands it to SDL2_image."""
        self.heap = self.mark                        # one picture at a time: start the heap again
        self.failed = None
        err = self.malloc(0x200)
        cinfo = self.malloc(STRUCT_SIZE + 0x40)
        self.uc.mem_write(cinfo, bytes(STRUCT_SIZE))
        self.write32(cinfo, self.call("jpeg_std_error", err))
        self.call("jpeg_CreateDecompress", cinfo, JPEG_LIB_VERSION, STRUCT_SIZE)
        source = self.malloc(len(data))
        self.uc.mem_write(source, bytes(data))
        self.call("jpeg_mem_src", cinfo, source, len(data))
        self.call("jpeg_read_header", cinfo, 1)
        width, height = self.read32(cinfo + 0x1C), self.read32(cinfo + 0x20)
        self.write32(cinfo + OUT_COLOR_SPACE, JCS_RGB)
        self.call("jpeg_start_decompress", cinfo)
        row = self.malloc(width * 3 + 64)
        rows = self.malloc(8)
        self.write32(rows, row)
        out = bytearray()
        for _ in range(height):
            self.call("jpeg_read_scanlines", cinfo, rows, 1)
            out += self.uc.mem_read(row, width * 3)
        return width, height, bytes(out)


def decode_in_child(paths, out_folder) -> dict:
    """Decode the JPEGs in a child Python (a Unicorn instance in the test process itself makes the
    Python work after it very slow on Windows): {file name: (width, height, RGB bytes)}."""
    import subprocess
    import sys
    out_folder = Path(out_folder)
    subprocess.run([sys.executable, __file__, str(out_folder), *map(str, paths)], check=True,
                   capture_output=True)
    result = {}
    for path in paths:
        raw = (out_folder / (Path(path).name + ".rgb")).read_bytes()
        width, height = struct.unpack_from("<II", raw, 0)
        result[Path(path).name] = (width, height, raw[8:])
    return result


if __name__ == "__main__":
    import sys
    folder = Path(sys.argv[1])
    decoder = LibJpeg()
    for name in sys.argv[2:]:
        width, height, rgb = decoder.decode(Path(name).read_bytes())
        (folder / (Path(name).name + ".rgb")).write_bytes(struct.pack("<II", width, height) + rgb)
