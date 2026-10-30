"""The startup loader for the companion DLLs (DS Fish in Fish Tycoon, the
new flowers in Plant Tycoon).

Same design as the Virtual Villagers Fun Patcher's startup loader
(src/vv_fun_patcher.py, _apply_startup_loader): the patcher appends one small
read/execute section to the executable and routes the C runtime's
`call WinMain` through its stub. The stub

    pushad; sub esp, 0x410; mov esi, esp              ; WCHAR path[0x208]
    ebx = GetModuleHandleA("KERNEL32.dll")            ; 0 -> done
    GetProcAddress(ebx, "GetModuleFileNameW")(NULL, esi, 0x208)
                                                      ; 0 or >= 0x208 -> done
    edi = after the last backslash                    ; none -> done
    the tail does not fit -> done
    copy L"Fish Tycoon Fix Patcher DLLs\\DS Exclusive Fish.dll" there
    GetProcAddress(ebx, "LoadLibraryExW")(esi, NULL, LOAD_WITH_ALTERED_SEARCH_PATH)
      -> GetProcAddress(., "FtfpStartup") -> call it
  done:
    add esp, 0x410; popad; jmp WinMain

loads the DLL by its full path beside the executable (never the DLL search
order), and every failure goes to `done`, so the game always starts, with
the stack and registers exactly as the C runtime left them. A profile with
`then_dlls` (the Optimize Prices button) loads each of them after the first
the same way, its name copied to the same place (kept in ebp); one that is
missing or refuses goes on to the next. A one-DLL loader is byte for byte
what it was before that, so its pins never moved. In every case the game
starts with
the stack and registers exactly as the C runtime left them. The DLL itself
checks every site it writes and installs all of them or none.

Each game has a LoaderProfile (its WinMain call, its IAT, the DLL to load);
the module-level names are Fish Tycoon's, as they were before Plant Tycoon
had a companion.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import struct

SECTION_NAME = b".ftfpst"
PATCHER_FILES_FOLDER = "Fish Tycoon Fix Patcher DLLs"
DLL_NAME = "DS Exclusive Fish.dll"
EXPORT = b"FtfpStartup\0"

WINMAIN_CALL_VA = 0x0042D7DE        # e8 6d cb ff ff: call WinMain
WINMAIN_VA = 0x0042A350
GET_MODULE_HANDLE_A_IAT = 0x00440144
GET_PROC_ADDRESS_IAT = 0x00440150


@dataclass(frozen=True)
class LoaderProfile:
    game: str
    patcher_files_folder: str
    dll_name: str
    winmain_call_va: int
    winmain_va: int
    get_module_handle_a_iat: int
    get_proc_address_iat: int
    what_it_installs: str
    then_dlls: tuple[str, ...] = ()       # loaded after dll_name, each the same way

    @property
    def tail(self) -> bytes:
        return self.tail_of(self.dll_name)

    def tail_of(self, dll_name: str) -> bytes:
        return (self.patcher_files_folder + "\\" + dll_name + "\0").encode("utf-16-le")

    @property
    def dll_names(self) -> tuple[str, ...]:
        return (self.dll_name,) + self.then_dlls


FISH = LoaderProfile(
    game="fish", patcher_files_folder="Fish Tycoon Fix Patcher DLLs", dll_name="DS Exclusive Fish.dll",
    winmain_call_va=WINMAIN_CALL_VA, winmain_va=WINMAIN_VA,
    get_module_handle_a_iat=GET_MODULE_HANDLE_A_IAT, get_proc_address_iat=GET_PROC_ADDRESS_IAT,
    what_it_installs="That checks every one of the 69 places it changes in the running game and writes all of "
                     "them or none; docs/fish-tycoon-ds-fish-technical-map.md lists them.",
)
# With only the Maximizable window on, the loader loads that DLL itself; with
# DS Exclusive Fish on, "DS Exclusive Fish.dll" loads it.
FISH_WINDOW = replace(
    FISH, dll_name="Maximizable Window.dll",
    what_it_installs="That checks the two places it changes in the running game (the import slots of "
                     "SDL_SetVideoMode and SDL_Flip, behind their stock thunks) and writes both or neither; "
                     "native/ftfp_fish_window/ftfp_fish_window.c describes them.",
)


OPTIMIZE_PRICES_DLL = "Optimize Prices.dll"
OPTIMIZE_PRICES_SETTING = "optimize_prices"
OPTIMIZE_PRICES_INSTALLS = ("That wraps two slots of the {screen}'s table (its commands and its opening) after "
                            "checking they hold the stock functions, or writes nothing; {source} describes them.")
FISH_OPTIMIZE = replace(
    FISH, dll_name=OPTIMIZE_PRICES_DLL,
    what_it_installs=OPTIMIZE_PRICES_INSTALLS.format(screen="Species Chart",
                                                     source="native/ftfp_fish_prices/ftfp_fish_prices.c"),
)


# With the counts on, the loader loads "Tank Counts.dll", which first loads
# the DLL the loader would load without it (DS Exclusive Fish, else the
# Maximizable Window), so their pins are untouched.
COUNTS_SETTING = "tank_greenhouse_counts"
FISH_COUNTS = replace(
    FISH, dll_name="Tank Counts.dll",
    what_it_installs="That first loads DS Exclusive Fish.dll or Maximizable Window.dll when their settings are "
                     "on, then checks the two slots it changes in the running game (the tank screen's overlay, "
                     "0x443A70, and its mouse, 0x443A58) and writes both or nothing; native/ftfp_tank_counts/"
                     "ftfp_tank_counts.c describes it.",
)


# With Multiple ornaments on, the loader loads that DLL first; it loads
# "DS Exclusive Fish.dll" or else "Maximizable Window.dll" when they are there.
FISH_ORNAMENTS = replace(
    FISH, dll_name="Multiple Ornaments.dll",
    what_it_installs="That checks the ten places it changes in the running game (calls of the stock ornament "
                     "code, the save and load of a game slot, and the store's Buy click and panel) and writes "
                     "all of them or none, then loads DS Exclusive Fish or the Maximizable window when they are "
                     "on; native/ftfp_ornaments/ftfp_ornaments.c describes them.",
)


# With "3 extra tanks" on, the loader loads that DLL, which first loads the one
# the loader would have loaded otherwise (Multiple Ornaments, else DS Exclusive
# Fish, else the window's).
FISH_EXTRA_TANKS = replace(
    FISH, dll_name="Extra Tanks.dll",
    what_it_installs="That first loads Multiple Ornaments.dll, DS Exclusive Fish.dll or Maximizable Window.dll "
                     "when they are there, then checks the places it changes in the running game and writes all "
                     "of them or none; docs/fish-tycoon-extra-tanks-design.md lists them.",
)


def chain(profiles: list[LoaderProfile]) -> LoaderProfile:
    """One loader for several DLLs: the first is loaded as a one-DLL loader would load it, then each
    of the others the same way, in order. A single profile is returned as it is (its pins never move)."""
    first = profiles[0]
    if len(profiles) == 1:
        return first
    rest = profiles[1:]
    text = first.what_it_installs
    for p in rest:
        text += f" Then it loads '{p.dll_name}' the same way. " + p.what_it_installs
    return replace(first, then_dlls=first.then_dlls + tuple(p.dll_name for p in rest), what_it_installs=text)


def with_optimize_prices(base: LoaderProfile | None, alone: LoaderProfile) -> LoaderProfile:
    """The loader for a game whose Optimize Prices button is on: it loads "Optimize Prices.dll"
    after the companion it would load anyway (so that DLL has installed first), or on its own."""
    return alone if base is None else chain([base, alone])


def fish_profile(enabled: set[str]) -> LoaderProfile:
    """The DLLs Fish Tycoon's loader loads for these settings.

    Extra Tanks goes first: it loads Multiple Ornaments (which loads DS Exclusive Fish, which loads DS
    Store Items and the window) before it installs, so the sites they share chain in that order. Without
    it, Multiple Ornaments goes first the same way. The counts follow (Tank Counts.dll wraps the tank
    screen's overlay slot, after everything Extra Tanks draws) and the Optimize Prices button last; each loads its own
    companions only if they are not loaded yet (every FtfpStartup runs once)."""
    profiles: list[LoaderProfile] = []
    if "extra_tanks" in enabled:
        profiles.append(FISH_EXTRA_TANKS)
    elif "multiple_ornaments" in enabled:
        profiles.append(FISH_ORNAMENTS)
    if COUNTS_SETTING in enabled:
        profiles.append(FISH_COUNTS)
    if not profiles and ("ds_fish" in enabled or "maximizable_window" in enabled
                         or OPTIMIZE_PRICES_SETTING not in enabled):
        profiles.append(FISH if "ds_fish" in enabled else FISH_WINDOW)
    if OPTIMIZE_PRICES_SETTING in enabled:
        profiles.append(FISH_OPTIMIZE)
    return chain(profiles)


PLANT = LoaderProfile(
    game="plant", patcher_files_folder="Plant Tycoon Fix Patcher DLLs", dll_name="Unused Flowers.dll",
    winmain_call_va=0x00451AE0,        # e8 9b 11 fc ff: call WinMain (0x412C80)
    winmain_va=0x00412C80,
    get_module_handle_a_iat=0x004650F0, get_proc_address_iat=0x004650F4,
    what_it_installs="That checks every place it changes in the running game and writes all of them or none; "
                     "docs/plant-tycoon-new-flowers-technical-map.md lists them.",
)
# With only the Sort Seeds button on, the loader loads that DLL itself; with
# the new flowers on, "Unused Flowers.dll" loads it (after the seed boxes).
PLANT_SORT = replace(
    PLANT, dll_name="Sort Seeds.dll",
    what_it_installs="That wraps two slots of the Seed Storage screen's table (its commands and its "
                     "opening) after checking they hold the stock functions, or writes nothing; "
                     "native/ftfp_sort_seeds/ftfp_sort_seeds.c describes them.",
)


PLANT_OPTIMIZE = replace(
    PLANT, dll_name=OPTIMIZE_PRICES_DLL,
    what_it_installs=OPTIMIZE_PRICES_INSTALLS.format(screen="Nursery",
                                                     source="native/ftfp_plant_prices/ftfp_plant_prices.c"),
)
# With the counts on, "Greenhouse Counts.dll" is loaded first and loads
# Unused Flowers, else Sort Seeds, itself.
PLANT_COUNTS = replace(
    PLANT, dll_name="Greenhouse Counts.dll",
    what_it_installs="That first loads Unused Flowers.dll or Sort Seeds.dll when their settings are on, then "
                     "changes two places (the greenhouse overlay's held-item draw, 0x4291D2, and the screen's "
                     "mouse slot) after checking they hold the stock code, or writes nothing; native/ftfp_greenhouse_counts/"
                     "ftfp_greenhouse_counts.c describes it.",
)
# With the extra greenhouses or the extra nurseries on, the loader loads that
# DLL (both settings' DLL), which starts "Greenhouse Counts.dll", else "Unused
# Flowers.dll", else "Sort Seeds.dll" first and then wraps what they installed.
PLANT_GREENHOUSES = replace(
    PLANT, dll_name="Extra Greenhouses.dll",
    what_it_installs="That starts the other companion DLLs beside it, then checks the ten places in the game's "
                     "code and the 19 screen-table slots it changes and writes all of them or none; "
                     "docs/plant-tycoon-extra-greenhouses-design.md lists them.",
)


def plant_profile(enabled: set[str]) -> LoaderProfile:
    """The DLLs Plant Tycoon's loader loads for these settings.

    With the extra greenhouses or nurseries, Extra Greenhouses.dll is loaded last: it starts the counts,
    Unused Flowers or Sort Seeds itself, then wraps 19 screen-table slots, chaining the wrappers other
    companions put there first -- the counts' greenhouse slots and the Optimize Prices button's two
    Nursery slots, so the button's DLL goes before it (it only installs over the stock functions).
    Otherwise the counts go first (they load Unused Flowers, else Sort Seeds, themselves) and the
    Optimize Prices button last."""
    profiles: list[LoaderProfile] = []
    if "extra_greenhouses" in enabled or "extra_nurseries" in enabled:
        if OPTIMIZE_PRICES_SETTING in enabled:
            profiles.append(PLANT_OPTIMIZE)
        profiles.append(PLANT_GREENHOUSES)
        return chain(profiles)
    if COUNTS_SETTING in enabled:
        profiles.append(PLANT_COUNTS)
    elif ("new_flowers" in enabled or "sort_seeds" in enabled or OPTIMIZE_PRICES_SETTING not in enabled):
        profiles.append(PLANT if "new_flowers" in enabled else PLANT_SORT)
    if OPTIMIZE_PRICES_SETTING in enabled:
        profiles.append(PLANT_OPTIMIZE)
    return chain(profiles)


PATH_WCHARS = 0x208
PATH_BYTES = PATH_WCHARS * 2
LOAD_WITH_ALTERED_SEARCH_PATH = 0x8

KERNEL32 = b"KERNEL32.dll\0"
MODULE_FILE_NAME = b"GetModuleFileNameW\0"
LOAD_LIBRARY = b"LoadLibraryExW\0"
TAIL = (PATCHER_FILES_FOLDER + "\\" + DLL_NAME + "\0").encode("utf-16-le")


class LoaderError(ValueError):
    pass


def _layout(profile: LoaderProfile = FISH) -> tuple[dict[str, int], int]:
    offsets: dict[str, int] = {}
    at = 0
    for key, text in (("kernel32", KERNEL32), ("module_file_name", MODULE_FILE_NAME),
                      ("load_library", LOAD_LIBRARY), ("export", EXPORT)):
        offsets[key] = at
        at += len(text)
    at = (at + 1) & ~1
    for index, name in enumerate(profile.dll_names):
        offsets["tail" if index == 0 else f"tail{index}"] = at
        at += len(profile.tail_of(name))
    return offsets, (at + 15) & ~15


def _block(block_va: int, profile: LoaderProfile = FISH) -> bytes:
    offsets, code_offset = _layout(profile)
    tails = [profile.tail_of(name) for name in profile.dll_names]
    code = bytearray()
    fixups: list[tuple[int, str]] = []
    labels: dict[str, int] = {}

    def u32(value: int) -> bytes:
        return struct.pack("<I", value & 0xFFFFFFFF)

    def jump(opcode: bytes, label: str) -> None:
        code.extend(opcode)
        fixups.append((len(code), label))
        code.extend(b"\0\0\0\0")

    jz, jae, jb, jne, ja = b"\x0F\x84", b"\x0F\x83", b"\x0F\x82", b"\x0F\x85", b"\x0F\x87"
    code += b"\x60"                                       # pushad
    code += b"\x81\xEC" + u32(PATH_BYTES)                 # sub esp, 0x410
    code += b"\x8B\xF4"                                   # mov esi, esp
    code += b"\x68" + u32(block_va + offsets["kernel32"])
    code += b"\xFF\x15" + u32(profile.get_module_handle_a_iat)    # GetModuleHandleA
    code += b"\x85\xC0"
    jump(jz, "done")
    code += b"\x8B\xD8"                                   # mov ebx, eax
    code += b"\x68" + u32(block_va + offsets["module_file_name"])
    code += b"\x53"
    code += b"\xFF\x15" + u32(profile.get_proc_address_iat)
    code += b"\x85\xC0"
    jump(jz, "done")
    code += b"\x68" + u32(PATH_WCHARS)
    code += b"\x56"
    code += b"\x6A\x00"
    code += b"\xFF\xD0"                                   # GetModuleFileNameW(NULL, esi, 0x208)
    code += b"\x85\xC0"
    jump(jz, "done")
    code += b"\x3D" + u32(PATH_WCHARS)
    jump(jae, "done")
    code += b"\x8D\x3C\x46"                               # lea edi, [esi+eax*2]
    labels["scan"] = len(code)
    code += b"\x83\xEF\x02"                               # sub edi, 2
    code += b"\x3B\xFE"                                   # cmp edi, esi
    jump(jb, "done")
    code += b"\x66\x83\x3F\x5C"                           # cmp word [edi], '\\'
    jump(jne, "scan")
    code += b"\x83\xC7\x02"                               # add edi, 2
    several = len(tails) > 1
    if several:
        code += b"\x8B\xEF"                               # mov ebp, edi: where each DLL's name goes
    for index, tail in enumerate(tails):
        # one DLL after the other; a DLL that is missing or refuses goes on to the next
        after = "done" if index == len(tails) - 1 else f"next{index + 1}"
        if index:
            labels[f"next{index}"] = len(code)
        if several:
            code += b"\x8B\xFD"                           # mov edi, ebp
        code += b"\x8D\x87" + u32(len(tail))              # lea eax, [edi+tail]
        code += b"\x2B\xC6"                               # sub eax, esi
        code += b"\x3D" + u32(PATH_BYTES)
        jump(ja, after)
        code += b"\x56"                                   # push esi
        code += b"\xBE" + u32(block_va + offsets["tail" if index == 0 else f"tail{index}"])   # mov esi, tail
        code += b"\xB9" + u32(len(tail))                  # mov ecx, len
        code += b"\xF3\xA4"                               # rep movsb
        code += b"\x5E"                                   # pop esi
        code += b"\x68" + u32(block_va + offsets["load_library"])
        code += b"\x53"
        code += b"\xFF\x15" + u32(profile.get_proc_address_iat)
        code += b"\x85\xC0"
        jump(jz, after)
        code += b"\x6A" + bytes([LOAD_WITH_ALTERED_SEARCH_PATH])
        code += b"\x6A\x00"
        code += b"\x56"
        code += b"\xFF\xD0"                               # LoadLibraryExW
        code += b"\x85\xC0"
        jump(jz, after)
        code += b"\x68" + u32(block_va + offsets["export"])
        code += b"\x50"
        code += b"\xFF\x15" + u32(profile.get_proc_address_iat)
        code += b"\x85\xC0"
        jump(jz, after)
        code += b"\xFF\xD0"                               # FtfpStartup() (stdcall, no arguments)
    labels["done"] = len(code)
    code += b"\x81\xC4" + u32(PATH_BYTES)                 # add esp, 0x410
    code += b"\x61"                                       # popad
    code += b"\xE9" + u32(profile.winmain_va - (block_va + code_offset + len(code) + 5))
    for at, label in fixups:
        struct.pack_into("<i", code, at, labels[label] - (at + 4))
    head = bytearray(code_offset)
    for key, text in (("kernel32", KERNEL32), ("module_file_name", MODULE_FILE_NAME),
                      ("load_library", LOAD_LIBRARY), ("export", EXPORT)):
        head[offsets[key]: offsets[key] + len(text)] = text
    for index, tail in enumerate(tails):
        at = offsets["tail" if index == 0 else f"tail{index}"]
        head[at: at + len(tail)] = tail
    return bytes(head) + bytes(code)


def _where(profile: LoaderProfile) -> str:
    return "', then '".join(profile.patcher_files_folder + "\\" + name for name in profile.dll_names)


def described_changes(profile: LoaderProfile = FISH) -> list[tuple[int, int | None, int, str]]:
    """The executable changes, for the GUI's technical details:
    (file offset, virtual address or None, length, what it does)."""
    _, code_offset = _layout(profile)
    file_end, block_va = {"fish": (0x5E000, 0x00460000), "plant": (0xAB000, 0x004AE000)}[profile.game]
    block_length = code_offset + len(_block(block_va, profile))
    where = _where(profile)
    return [
        (0xFE, None, 2, "NumberOfSections: one more, the .ftfpst section."),
        (0x148, None, 4, "SizeOfImage: grows to take in the .ftfpst section."),
        (0x2B8, None, 40, "The .ftfpst section header: read and execute, never writable."),
        (profile.winmain_call_va - 0x400000, profile.winmain_call_va, 5,
         "The C runtime's call of WinMain now calls the startup loader, which then jumps to WinMain."),
        (file_end, block_va, block_length,
         f"The startup loader, appended: it loads '{where}' by its full path beside the executable and calls "
         f"FtfpStartup. {profile.what_it_installs} If the DLL is missing or refuses, the game starts as it "
         "would without this setting."),
        (0x150, None, 4, "The PE checksum, recomputed over the whole file."),
    ]


def pe_checksum(data: bytes | bytearray) -> int:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    checksum_offset = pe + 24 + 64
    total = 0
    padded = bytes(data) + (b"\0" if len(data) % 2 else b"")
    for i in range(0, len(padded), 2):
        if checksum_offset <= i < checksum_offset + 4:
            continue
        total += padded[i] | (padded[i + 1] << 8)
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + len(data)) & 0xFFFFFFFF


def append_startup_loader(data: bytes, profile: LoaderProfile = FISH) -> tuple[bytes, list[dict[str, str]]]:
    """The executable with the .ftfpst section and the WinMain call routed
    through it; refuses anything that is not the stock layout it expects."""
    out = bytearray(data)
    pe = struct.unpack_from("<I", out, 0x3C)[0]
    count = struct.unpack_from("<H", out, pe + 6)[0]
    optional = pe + 24
    optional_size = struct.unpack_from("<H", out, pe + 20)[0]
    image_base = struct.unpack_from("<I", out, optional + 28)[0]
    section_alignment, file_alignment = struct.unpack_from("<II", out, optional + 32)
    size_of_headers = struct.unpack_from("<I", out, optional + 60)[0]
    table = optional + optional_size
    sections = []
    for i in range(count):
        at = table + 40 * i
        name = bytes(out[at: at + 8]).rstrip(b"\0")
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", out, at + 8)
        sections.append({"name": name, "vsize": vsize, "vaddr": vaddr, "rsize": rsize, "raw": raw})
    if any(s["name"] == SECTION_NAME for s in sections):
        raise LoaderError("the executable already has a .ftfpst section")
    entry = table + 40 * count
    first_raw = min(s["raw"] for s in sections if s["rsize"])
    if entry + 40 > min(size_of_headers, first_raw) or any(out[entry: entry + 40]):
        raise LoaderError("no free section header slot")
    file_end = max(s["raw"] + s["rsize"] for s in sections)
    if len(out) != file_end:
        raise LoaderError("the executable has data after its last section")
    text = sections[0]
    call_va = profile.winmain_call_va
    call_off = call_va - image_base - text["vaddr"] + text["raw"]
    stock_call = b"\xE8" + struct.pack("<i", profile.winmain_va - (call_va + 5))
    if bytes(out[call_off: call_off + 5]) != stock_call:
        raise LoaderError(f"0x{call_va:X} is not the stock call of WinMain")

    def align(value: int, unit: int) -> int:
        return (value + unit - 1) // unit * unit

    section_rva = align(max(s["vaddr"] + max(s["vsize"], 1) for s in sections), section_alignment)
    raw_pointer = align(len(out), file_alignment)
    block = _block(image_base + section_rva, profile)
    raw_size = align(len(block), file_alignment)
    header = SECTION_NAME.ljust(8, b"\0") + struct.pack(
        "<IIIIIIHHI", len(block), section_rva, raw_size, raw_pointer, 0, 0, 0, 0,
        0x60000020)                                        # code, execute, read: never writable
    size_of_image = align(section_rva + len(block), section_alignment)
    hook = b"\xE8" + struct.pack("<i", image_base + section_rva + _layout(profile)[1] - (call_va + 5))
    records = []
    for offset, after, purpose in (
        (pe + 6, struct.pack("<H", count + 1), "NumberOfSections: add .ftfpst"),
        (optional + 56, struct.pack("<I", size_of_image), "SizeOfImage through .ftfpst"),
        (entry, header, "the .ftfpst section header (read/execute)"),
        (call_off, hook, "route the C runtime's call of WinMain through the startup loader"),
    ):
        records.append({"offset": f"0x{offset:X}", "before": bytes(out[offset: offset + len(after)]).hex().upper(),
                        "after": after.hex().upper(), "purpose": purpose})
        out[offset: offset + len(after)] = after
    records.append({"offset": f"0x{len(out):X}", "before": "", "after": f"{raw_size} bytes",
                    "purpose": f"the startup loader: load '{_where(profile)}' by its full path "
                               "and call FtfpStartup, then WinMain"})
    out.extend(bytes(raw_pointer - len(out)) + block + bytes(raw_size - len(block)))
    checksum_offset = optional + 64
    struct.pack_into("<I", out, checksum_offset, 0)
    struct.pack_into("<I", out, checksum_offset, pe_checksum(out))
    return bytes(out), records
