"""Run "Translations.dll" (native/ftfp_translations) in Unicorn against the real game.

The DLL is rebuilt from its source (tests/store_emulator.py: the rebuild must equal the
committed DLL), mapped beside the vanilla executable, and its Windows imports are Python hooks:
the files it reads (Translation.ini, the translation) come from a dict, the log it writes is
kept. Then FtfpStartup() runs and the game's own string lookup is called, so a test sees exactly
what the game would draw.
"""

from __future__ import annotations

from pathlib import Path
import struct
import tempfile

try:
    from keystone import KS_ARCH_X86, KS_MODE_32, Ks
    import store_emulator as se
except ImportError:           # Keystone or Unicorn is not installed (CI): ready() is False
    se = None

ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / "assets" / "translations" / "Translations.dll"
EXES = {} if se is None else {"fish": se.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe",
                              "plant": se.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"}
FOLDERS = {"fish": "C:\\Game\\Fish Tycoon Fix Patcher DLLs\\", "plant": "C:\\Game\\Plant Tycoon Fix Patcher DLLs\\"}
FISH_LOOKUP, PLANT_LOOKUP = 0x00426FD0, 0x0044CA70

_built: dict[str, object] = {}


def ready() -> bool:
    return se is not None and se.toolchain_ready() and all(p.is_file() for p in EXES.values()) and DLL.is_file()


def built() -> tuple[Path, dict[str, int]]:
    if "dll" not in _built:
        out = Path(tempfile.mkdtemp(prefix="ftfp_tr_"))
        _built["dll"], _built["symbols"] = se.build_with_map("ftfp_translations", DLL, out)
    return _built["dll"], _built["symbols"]  # type: ignore[return-value]


def relocate(data: bytes, new_base: int) -> bytes:
    """A DLL image's file bytes with every HIGHLOW fixup moved to new_base."""
    out = bytearray(data)
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    base = struct.unpack_from("<I", data, pe + 52)[0]
    struct.pack_into("<I", out, pe + 52, new_base)
    reloc_rva, reloc_size = struct.unpack_from("<II", data, pe + 24 + 96 + 5 * 8)
    _base, _size, sections, _imports = se.pe_image(data)

    def offset(rva: int) -> int:
        for s_rva, raw, raw_size in sections:
            if s_rva <= rva < s_rva + raw_size:
                return raw + rva - s_rva
        raise ValueError(hex(rva))
    at = 0
    while at < reloc_size:
        page, size = struct.unpack_from("<II", data, offset(reloc_rva + at))
        if size < 8:
            break
        for k in range((size - 8) // 2):
            entry = struct.unpack_from("<H", data, offset(reloc_rva + at + 8 + 2 * k))[0]
            if entry >> 12 == 3:
                o = offset(page + (entry & 0xFFF))
                struct.pack_into("<I", out, o, struct.unpack_from("<I", out, o)[0] - base + new_base)
        at += size
    return bytes(out)


class Runtime:
    """One game with Translations.dll, before FtfpStartup."""

    def __init__(self, game: str, files: dict[str, bytes], dlls: dict[str, tuple[bytes, int]] | None = None,
                 chain_plant: bool = False, unicode_active: int | None = None) -> None:
        dll, symbols = built()
        self.game = game
        self.emu = se.Emulator(EXES[game], dll, symbols)
        self.emu.uc.mem_map(0, 0x1000)                          # fs:[0] (the DLL's __try)
        self.files = {k.lower(): v for k, v in files.items()}
        self.written: dict[str, bytearray] = {}
        self.handles: dict[int, tuple[str, int]] = {}
        self.modules: dict[str, int] = {}
        self.protect_calls = 0
        for name, (data, base) in (dlls or {}).items():
            self.emu._map(relocate(data, base))
            self.modules[name.lower()] = base
        e = self.emu
        e.hook_import("GetModuleFileNameW", self._module_file_name, 12)
        e.hook_import("CreateFileW", self._create_file, 28)
        e.hook_import("GetFileSizeEx", self._file_size, 8)
        e.hook_import("ReadFile", self._read_file, 20)
        e.hook_import("WriteFile", self._write_file, 20)
        e.hook_import("CloseHandle", lambda emu: 1, 4)
        e.hook_import("GetProcessHeap", lambda emu: 0x1234, 0)
        e.hook_import("HeapAlloc", self._heap_alloc, 12)
        e.hook_import("VirtualProtect", self._virtual_protect, 16)
        e.hook_import("FlushInstructionCache", lambda emu: 1, 12)
        e.hook_import("GetCurrentProcess", lambda emu: 0xFFFFFFFF, 0)
        e.hook_import("GetModuleHandleW", self._module_handle, 4)
        e.hook_import("GetProcAddress", self._proc_address, 8)
        self.unicode_active = unicode_active
        if unicode_active is not None:                      # "Unicode Text.dll" loaded before this DLL
            self.modules["unicode text.dll"] = 0x0C000000
            self.active_thunk = e.thunk()
            e.hook(self.active_thunk, lambda emu: self.unicode_active, 0)
        e.hook_import("DisableThreadLibraryCalls", lambda emu: 1, 4)
        self.chained_text = 0
        if chain_plant:
            self._chain_plant()

    # ------------------------------------------------------------ imports
    def _module_file_name(self, emu) -> int:
        buffer, size = emu.arg(1), emu.arg(2)
        path = FOLDERS[self.game] + "Translations.dll"
        emu.uc.mem_write(buffer, path.encode("utf-16-le") + b"\0\0")
        return len(path) if len(path) < size else 0

    def _create_file(self, emu) -> int:
        path = emu.wstring(emu.arg(0))
        access = emu.arg(1)
        handle = 0x100 + len(self.handles)
        if access & 0x40000000:                                  # GENERIC_WRITE
            name = path.rsplit("\\", 1)[-1]
            self.written[name] = bytearray()
            self.handles[handle] = ("w:" + name, 0)
            return handle
        data = self.files.get(path.lower())
        if data is None:
            return 0xFFFFFFFF                                    # INVALID_HANDLE_VALUE
        self.handles[handle] = (path.lower(), 0)
        return handle

    def _file_size(self, emu) -> int:
        path, _ = self.handles[emu.arg(0)]
        emu.uc.mem_write(emu.arg(1), struct.pack("<Q", len(self.files[path])))
        return 1

    def _read_file(self, emu) -> int:
        handle, buffer, count, got = emu.arg(0), emu.arg(1), emu.arg(2), emu.arg(3)
        path, at = self.handles[handle]
        data = self.files[path][at:at + count]
        emu.uc.mem_write(buffer, data)
        self.handles[handle] = (path, at + len(data))
        if got:
            emu.write32(got, len(data))
        return 1

    def _write_file(self, emu) -> int:
        handle, buffer, count, done = emu.arg(0), emu.arg(1), emu.arg(2), emu.arg(3)
        name = self.handles[handle][0][2:]
        self.written[name] += bytes(emu.uc.mem_read(buffer, count))
        if done:
            emu.write32(done, count)
        return 1

    def _heap_alloc(self, emu) -> int:
        size = emu.arg(2)
        address = emu.alloc(size + 16)
        return address

    def _virtual_protect(self, emu) -> int:
        self.protect_calls += 1
        if emu.arg(3):
            emu.write32(emu.arg(3), 0x20)
        return 1

    def _proc_address(self, emu) -> int:
        name = emu.cstring(emu.arg(1)) if emu.arg(1) >= 0x10000 else b""
        if self.unicode_active is not None and emu.arg(0) == 0x0C000000 and name == b"FtfpUnicodeTextActive":
            return self.active_thunk
        return 0

    def _module_handle(self, emu) -> int:
        name = emu.wstring(emu.arg(0)).lower() if emu.arg(0) else ""
        return self.modules.get(name, 0)

    # ------------------------------------------------------------ Plant: Store Upgrades' jump
    def _chain_plant(self) -> None:
        """What "Store Upgrades and Items.dll" leaves at 0x44CA70: a jump to its own texts (id
        0x1F0: "Radioactive Plant Formula") that runs the stock head for every other id."""
        e = self.emu
        text = e.text("Radioactive Plant Formula")
        self.chained_text = text
        stub = e.alloc(64)
        code = (f"mov eax, dword ptr [esp + 4]; cmp eax, 0x1F0; jne stock; mov eax, {text}; ret 4; "
                f"stock: test eax, eax; push 0x44CA76; ret")
        encoding, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(code, stub)
        e.uc.mem_write(stub, bytes(encoding))
        rel = (stub - (PLANT_LOOKUP + 5)) & 0xFFFFFFFF
        e.uc.mem_write(PLANT_LOOKUP, b"\xE9" + struct.pack("<I", rel) + b"\x90")

    # ------------------------------------------------------------ running
    def start(self) -> int:
        return self.emu.call(self.emu.sym("_FtfpStartup@0"))

    @property
    def log(self) -> str:
        return bytes(self.written.get("Translations.log", b"")).decode("latin-1")

    def lookup(self, ident: int, german: bool = False) -> bytes:
        """What the game's own lookup returns for a string id (Fish: in English, or German)."""
        e = self.emu
        if self.game == "fish":
            language = e.alloc(4)
            e.write32(language, 1 if german else 0)
            return e.cstring(e.call(FISH_LOOKUP, ident, ecx=language))
        return e.cstring(e.call(PLANT_LOOKUP, ident, ecx=0x493CC0))

    def hook_plant_table(self) -> None:
        """Plant Tycoon fills [0x493CC0 + id * 4] at start (0x44CE40, from its stock table at
        0x48EC58 and the optional sm.xml): the same, from the stock table, here."""
        e = self.emu
        for k in range(0x18F):
            entry = 0x48EC58 + 16 * k
            ident = e.read32(entry)
            if 1 <= ident <= 0x1B2:
                e.write32(0x493CC0 + 4 * ident, entry)


def ini(path: str, language: str = "Test") -> bytes:
    return ("\ufeff; written by the patcher\r\nlanguage=" + language + "\r\nfile=" + path + "\r\n").encode("utf-8")
