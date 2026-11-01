"""The owner's rule: "make sure everything works with every patch."

For each game, every configuration below is built exactly as the patcher builds it, loaded the
way the game loads it, and run:

  * Select All Patches (every setting but the cheats, as the GUI's Select All Patches and Owner's Defaults set them), and that
    with Everything is Free ticked too;
  * the Defaults;
  * every setting that ships a companion DLL, alone with what it requires (requires_settings,
    followed to the end, as the GUI ticks them).

For each configuration:

  Build    the patcher's own apply (tycoon_fix_patcher.run_game) writes the modded folder from the
           vanilla game; its executable must be the manifest's pin for those settings.
  Load     the patched executable, the game's own DLLs it imports (SDL) and every companion DLL in
           the built folder are mapped in Unicorn, and the executable's own startup loader (the
           .ftfpst section, src/ds_fish_loader.py) runs from the C runtime's call of WinMain until
           it jumps to WinMain: it loads each DLL by its path in the built folder, each DLL's DllMain
           runs when it is loaded, and each FtfpStartup (and the startups the DLLs call in each
           other) runs as in the game. The game must reach WinMain with the stack and registers as
           the C runtime left them.
  Installed  every DLL the configuration ships is loaded and installs: its log line says installed
           (all sites), its own "installed" export returns 1, and a DLL without either (the counts,
           the Maximizable window) returned 1 from its startup. None refuses.
  No clashes  no two DLLs write the same byte of the game, and no DLL writes a byte a manifest patch
           of this configuration wrote -- except the deliberate chains listed in CHAINS, each with
           its reason. Two views are checked: the sites each DLL declares (its *_sites.h, written by
           scripts/build_*_headers.py, and the table slots its source names), and every byte each
           DLL actually wrote into the game while it started.
  Runs     a few game update ticks and frames of the main screen run in the emulator through the
           screen's own table (so every wrapper a DLL put there runs): Fish Tycoon's tank screen,
           Plant Tycoon's greenhouse and Nursery. Nothing may crash, touch unmapped memory or call
           an import the harness does not provide, and each call must return to its caller.

As in tests/test_counts_on_top.py, the screens' own functions (each screen's ROOTS: its update, its
draw, its overlay; for Fish Tycoon also the fish update) and every DLL run as their real machine
code, and every game function those ROOTS call is a stand-in that records the call (a DLL's hook
calls it in turn) -- except tiny accessors, which run for real. The game state is a zeroed one with
a few fish or plants in it. Windows is answered in Python (World._api); an import the harness does
not answer fails the test. Nothing is written outside a temporary folder: the DLLs' files (their
logs, sidecars) are kept in memory, and the built folder is only read.
"""

from __future__ import annotations

import atexit
import contextlib
import hashlib
import io
import json
import re
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import cheat  # noqa: E402
import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import plant_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

try:
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs
    from unicorn import UC_HOOK_MEM_WRITE, UcError
    from unicorn import x86_const as X
    import store_emulator as E
except ImportError:          # Unicorn or Capstone is not installed
    E = None

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
VANILLA_DIRS = {"fish": VANILLA / "Fish Tycoon", "plant": VANILLA / "Plant Tycoon"}
PATCHERS = {"fish": fish_patcher, "plant": plant_patcher}
PROFILES = {"fish": ds_fish_loader.fish_profile, "plant": ds_fish_loader.plant_profile}


def _ready(game: str) -> bool:
    return E is not None and (VANILLA_DIRS[game] / combined.GAMES[game].vanilla_exe_name).is_file()


def _needs(game: str):
    return unittest.skipUnless(_ready(game), f"needs Unicorn, Capstone and the vanilla {game} game")


# ------------------------------------------------------------------ the configurations

def manifest(game: str) -> dict:
    return json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))


def with_requirements(m: dict, enabled: set[str]) -> set[str]:
    """`enabled` and everything it requires, followed to the end (as the GUI ticks them)."""
    settings = {s["id"]: s for s in m["settings"]}
    out, todo = set(), list(enabled)
    while todo:
        setting = todo.pop()
        if setting not in out:
            out.add(setting)
            todo.extend(settings[setting].get("requires_settings", []))
    return out


def dll_settings(m: dict) -> list[str]:
    """Settings that ship a companion DLL, in the manifest's order."""
    return [s["id"] for s in m["settings"]
            if any(str(f.get("destination", "")).lower().endswith(".dll")
                   for f in (s.get("companion") or {}).get("files", []))]


def configurations(game: str) -> dict[str, set[str]]:
    m = manifest(game)
    every = {s["id"] for s in m["settings"]}
    ticked = {s["id"] for s in m["settings"] if cheat.in_enable_all(s)}
    # The two Unicode settings exclude each other: Select All keeps the default one (Render
    # Unicode with In-Game Fonts), Owner's Defaults the other (Use Unicode Font).
    enable_all = ticked - {"unicode_system_font"}
    configs = {
        "Select All Patches": enable_all,
        "Owner's Defaults": ticked - {"unicode_ingame_fonts"},
        "Select All Patches + Everything is Free": enable_all | {"everything_free"},
        "Default Patches": {s["id"] for s in m["settings"] if s.get("default")},
    }
    assert "everything_free" in every and "everything_free" not in enable_all
    for setting in dll_settings(m):
        configs[f"{setting} alone"] = with_requirements(m, {setting})
    return configs


def shipped_dlls(game: str, enabled: set[str]) -> list[str]:
    """The DLL files a configuration copies into the patcher's DLL folder."""
    out: list[str] = []
    for s in manifest(game)["settings"]:
        if s["id"] in enabled:
            for f in (s.get("companion") or {}).get("files", []):
                name = str(f.get("destination", "")).rsplit("/", 1)[-1]
                if name.lower().endswith(".dll") and name not in out:
                    out.append(name)
    return out


# ------------------------------------------------------------------ the builds

_TMP: list[Path] = []
_BUILDS: dict[tuple[str, frozenset], "Build"] = {}


def _tmp() -> Path:
    if not _TMP:
        _TMP.append(Path(tempfile.mkdtemp(prefix="ftfp_every_patch_")))
        atexit.register(shutil.rmtree, _TMP[0], True)
    return _TMP[0]


class Build:
    """One configuration, written by the patcher's own apply into a temporary folder."""

    def __init__(self, game: str, enabled: set[str]) -> None:
        self.game, self.enabled = game, set(enabled)
        spec = combined.GAMES[game]
        parent = _tmp() / f"{game}{len(_BUILDS)}"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            summary = combined.run_game(game, VANILLA_DIRS[game], parent / spec.modded_folder_name,
                                        sorted(enabled), dry_run=False)
        self.folder = Path(summary["output_dir"])
        self.exe = self.folder / summary["output_exe_name"]
        m = manifest(game)
        # A loader-tail setting (Unicode Text) is left out of the pins: the executable without it
        # must be the manifest's pin (build_executable checks that), and the executable with it is
        # those same bytes with the tail DLL added to the loader.
        self.pin = PATCHERS[game].expected_patched_hash(m, fish_patcher.pin_settings(m, self.enabled))
        self.tails = fish_patcher.loader_tail_dlls(m, self.enabled)
        if self.tails:
            patcher = PATCHERS[game]
            original = (VANILLA_DIRS[game] / spec.vanilla_exe_name).read_bytes()
            key = patcher.settings_key if game == "fish" else (lambda core: patcher.settings_key(core, m))
            tailed, _s, _l, core_pin = fish_patcher.build_executable(
                m, original, self.enabled, game, patcher.active_patch_records, patcher.apply_patch_bytes,
                patcher.expected_patched_hash, key)
            assert core_pin == self.pin
            self.pin = hashlib.sha256(tailed).hexdigest().upper()
        self.sha256 = hashlib.sha256(self.exe.read_bytes()).hexdigest().upper()
        self.profile = fish_patcher.loader_profile(m, self.enabled, game) or PROFILES[game](self.enabled)
        self.dll_folder = self.folder / self.profile.patcher_files_folder
        self.dlls = shipped_dlls(game, self.enabled)
        self.active_patches = PATCHERS[game].active_patch_records(manifest(game), self.enabled)
        if "translations" in self.enabled:
            choose_test_translation(game, self.folder)


_TRANSLATION_PIECE = re.compile(r"%[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlLIw0-9]*[a-zA-Z]|\{[^{}]*\}|\\.")


def choose_test_translation(game: str, folder: Path) -> None:
    """A translation of every patcher text and a few game lines (the letters' case swapped, the
    placeholders kept), chosen for this copy as the Translations window would: Translations.dll
    then installs, hooks the lookup and points every DLL's texts at their translations."""
    import translation_format as tfmt
    import translation_strings as tstr
    import translations
    vanilla = (VANILLA_DIRS[game] / combined.GAMES[game].vanilla_exe_name).read_bytes()
    entries = tstr.entries_for(game, vanilla)
    f = tfmt.new_file(game, entries, "Test", "en")
    for row, entry in zip(f.rows, entries):
        if row.key.startswith("mod/") or row.key.split("/", 1)[1].split("~")[0] in ("1", "2", "7", "8", "69"):
            parts, at = [], 0
            for m in _TRANSLATION_PIECE.finditer(row.english):
                parts.append(row.english[at:m.start()].swapcase())
                parts.append(m.group(0))
                at = m.end()
            parts.append(row.english[at:].swapcase())
            text = "".join(parts)
            if not tfmt.check_translation(row.english, text)[0] and not tfmt.too_long(text, entry.max_length or 1000,
                                                                                       entry.wide):
                row.translation = text
    path = folder / "Test translation.txt"
    path.write_bytes(tfmt.to_bytes(f))
    assert translations.write_choice(folder, game, path, "Test")


def build(game: str, enabled: set[str]) -> Build:
    key = (game, frozenset(enabled))
    if key not in _BUILDS:
        _BUILDS[key] = Build(game, enabled)
    return _BUILDS[key]


# ------------------------------------------------------------------ the sites

# Each companion DLL and its source folder (native/<project>).
PROJECTS = {
    "fish": {
        "DS Exclusive Fish.dll": "ftfp_ds_fish", "DS Store Items.dll": "ftfp_ds_store",
        "Extra Tanks.dll": "ftfp_extra_tanks", "Extra Supply Slots.dll": "ftfp_supply_slots",
        "Multiple Ornaments.dll": "ftfp_ornaments", "Optimize Prices.dll": "ftfp_fish_prices",
        "Tank Counts.dll": "ftfp_tank_counts", "Maximizable Window.dll": "ftfp_fish_window",
        "Unicode Text.dll": "ftfp_fish_unicode", "Translations.dll": "ftfp_translations",
    },
    "plant": {
        "Unused Flowers.dll": "ftfp_new_flowers", "Store Upgrades and Items.dll": "ftfp_plant_upgrades",
        "Extra Seed Boxes.dll": "ftfp_seed_boxes", "Sort Seeds.dll": "ftfp_sort_seeds",
        "Optimize Prices.dll": "ftfp_plant_prices", "Greenhouse Counts.dll": "ftfp_greenhouse_counts",
        "Extra Greenhouses.dll": "ftfp_extra_greenhouses", "Extra Chemical Slots.dll": "ftfp_chem_slots",
        "Unicode Text.dll": "ftfp_plant_unicode", "Translations.dll": "ftfp_translations",
    },
}

# DLLs whose sites are not in a generated *_sites.h: the table and import slots (4 bytes each) and
# the code sites (with their length) their source defines, by the define's name.
SOURCE_SITES = {
    "ftfp_tank_counts": (("OVERLAY_SLOT_VA", 4), ("MOUSE_SLOT_VA", 4)),
    "ftfp_greenhouse_counts": (("HELD_SITE_VA", 9), ("MOUSE_SLOT_VA", 4)),
    "ftfp_fish_window": (("SET_VIDEO_MODE_SLOT", 4), ("FLIP_SLOT", 4)),
    "ftfp_fish_prices": (("SPECIES_VT_COMMAND", 4), ("SPECIES_VT_ACTIVATE", 4),
                         ("SALE_VT_COMMAND", 4), ("SALE_VT_ACTIVATE", 4)),
    "ftfp_plant_prices": (("SELL_VT_COMMAND", 4), ("SELL_VT_ACTIVATE", 4)),
    "ftfp_sort_seeds": (("SCENE_COMMAND_VA", 4), ("SCENE_ACTIVATE_VA", 4)),
    # Translations.dll: the lookup's first 5 bytes and Fish Tycoon's five Goals sprintf calls; one
    # DLL for both games, so declared_bytes keeps only the running game's (TRANSLATIONS_SITES).
    "ftfp_translations": (("FISH_LOOKUP", 5), ("FISH_COUNT_CALL_1", 5), ("FISH_COUNT_CALL_2", 5),
                          ("FISH_COUNT_CALL_3", 5), ("FISH_COUNT_CALL_4", 5), ("FISH_COUNT_CALL_5", 5),
                          ("PLANT_LOOKUP", 5)),
}
TRANSLATIONS_SITES = {"fish": {0x426FD0, 0x4247FF, 0x424820, 0x424841, 0x424883, 0x4248AF}, "plant": {0x44CA70}}


def declared_sites(project: str) -> dict[int, tuple[int, str]]:
    """{va: (length, name)}: every place in the game a DLL declares it writes --
      * its generated headers (scripts/build_*_headers.py): the SITE_/SLOT_ entries (a slot
        without a length is 4 bytes), DS Fish's species-index sites (7 bytes), the new flowers'
        index stubs (their length), the store upgrades' formula spots (x and y: 8 bytes);
      * a site its source writes by a literal address (ftfp_site_branch / ftfp_site_imm32);
      * for a DLL without a sites header, the defines named in SOURCE_SITES."""
    native = ROOT / "native" / project
    out: dict[int, tuple[int, str]] = {}
    source = (native / f"{project}.c").read_text(encoding="latin-1")
    for name, length in SOURCE_SITES.get(project, ()):
        va = int(re.search(rf"#define {name}\s+(0x[0-9A-Fa-f]+)", source).group(1), 16)
        out[va] = (length, name)
    for va, length in re.findall(r"ftfp_site_(?:branch|imm32)\(\s*[^,]+,\s*(0x[0-9A-Fa-f]+)u?,\s*(\d+)", source):
        out[int(va, 16)] = (int(length), "a literal site in the source")
    for header in sorted(native.glob("*.h")):
        text = header.read_text(encoding="latin-1")
        defines = dict(re.findall(r"#define (\w+)\s+(0x[0-9A-Fa-f]+|\d+)u?\b", text))
        for name, value in defines.items():
            match = re.fullmatch(r"((?:SITE|SLOT)_\w+)_VA", name)
            if match:
                length = int(defines.get(match.group(1) + "_LEN", "4"), 0)
                out[int(value, 16)] = (length, match.group(1))
        for va in re.findall(r"\{\s*(0x[0-9A-Fa-f]+)u?,\s*-?\d+,\s*-?\d+,\s*\{", text):      # ds_index_site
            out[int(va, 16)] = (7, "a species-index site")
        for va, length in re.findall(r"\{\s*(0x[0-9A-Fa-f]+)u?,\s*(\d+),\s*\(const unsigned char \*\)", text):
            out[int(va, 16)] = (int(length), "a flower index stub")
        for va in re.findall(r"\{\s*(0x[0-9A-Fa-f]+)u?,\s*-?\d+,\s*-?\d+\s*\}", text):        # formula_spot
            out[int(va, 16)] = (8, "a formula spot")
    if not out:
        raise AssertionError(f"{project}: it declares no sites")
    return out


def manifest_ranges(game: str, patches: list[dict]) -> list[tuple[int, int, str]]:
    """(va, end, id) of every active manifest patch that changes the game's code or data (the
    PE header and its checksum records excluded: they are no place a DLL writes)."""
    m = manifest(game)
    out = []
    for patch in patches:
        if str(patch.get("id", "")).startswith("update_pe_checksum"):
            continue
        offset = int(str(patch["offset"]), 0)
        length = len(bytes.fromhex("".join(str(patch.get("replacement", "")).split())))
        if offset < 0x400 or not length:
            continue
        va = combined.file_offset_to_va(m, offset)
        out.append((va, va + length, str(patch["id"])))
    return out


# ------------------------------------------------------------------ PE images

def _u32(data: bytes, at: int) -> int:
    return struct.unpack_from("<I", data, at)[0]


def _directory(data: bytes, index: int) -> tuple[int, int]:
    pe = _u32(data, 0x3C)
    return struct.unpack_from("<II", data, pe + 24 + 96 + index * 8)


def _rva_to_raw(sections, rva: int) -> int:
    for start, raw, size in sections:
        if start <= rva < start + size:
            return raw + rva - start
    raise KeyError(hex(rva))


_DLL_MAINS: dict[str, int] = {}


class Module:
    """A DLL mapped in the world: a companion from the built folder, or one of the game's own."""

    def __init__(self, path: Path, base: int, companion: bool) -> None:
        self.name = path.name
        self.path = str(path)
        self.data = path.read_bytes()
        self.companion = companion
        preferred, self.size, self.sections, self.imports_rva = E.pe_image(self.data)
        self.base, self.delta = base, base - preferred
        self.slots: dict[str, int] = {}          # import name -> its IAT slot
        self.exports: dict[str, int] = {}
        rva, _size = _directory(self.data, 0)
        if rva:
            at = _rva_to_raw(self.sections, rva)
            names = _u32(self.data, at + 0x18)
            functions, name_table, ordinals = struct.unpack_from("<III", self.data, at + 0x1C)
            for i in range(names):
                raw = _rva_to_raw(self.sections, _u32(self.data, _rva_to_raw(self.sections, name_table) + 4 * i))
                export = self.data[raw:self.data.index(b"\0", raw)].decode()
                ordinal = struct.unpack_from("<H", self.data, _rva_to_raw(self.sections, ordinals) + 2 * i)[0]
                self.exports[export] = base + _u32(self.data, _rva_to_raw(self.sections, functions) + 4 * ordinal)

    def contains(self, address: int) -> bool:
        return self.base <= address < self.base + self.size

    def dll_main(self) -> int:
        """The DLL's own DllMain: the only function that calls DisableThreadLibraryCalls (every
        companion's DllMain does, and the C runtime never does); it starts at the nearest call
        target before that call."""
        key = hashlib.sha256(self.data).hexdigest()
        if key not in _DLL_MAINS:
            preferred = self.base - self.delta
            slot = self.slots["DisableThreadLibraryCalls"] - self.delta
            text_rva, text_raw, text_size = self.sections[0]
            code = self.data[text_raw:text_raw + text_size]
            needle = b"\xFF\x15" + struct.pack("<I", slot)
            hits = [m.start() for m in re.finditer(re.escape(needle), code)]
            if len(hits) != 1:
                raise AssertionError(f"{self.name}: DisableThreadLibraryCalls is called {len(hits)} times")
            call_at = preferred + text_rva + hits[0]
            md = Cs(CS_ARCH_X86, CS_MODE_32)
            targets = {int(ins.op_str, 16) for ins in md.disasm(code, preferred + text_rva)
                       if ins.mnemonic == "call" and ins.op_str.startswith("0x")}
            starts = [t for t in targets if call_at - 0x40 <= t <= call_at]
            if not starts:
                # The C runtime may reach DllMain by a jump, not a call: then it starts right after
                # the int3 padding that ends the function before it.
                at = hits[0]
                while at > max(0, hits[0] - 0x40) and code[at - 1] != 0xCC:
                    at -= 1
                if code[at - 1] == 0xCC:
                    starts = [preferred + text_rva + at]
            if not starts:
                raise AssertionError(f"{self.name}: no DllMain found before 0x{call_at:X}")
            _DLL_MAINS[key] = max(starts) - preferred
        return self.base + _DLL_MAINS[key]


# ------------------------------------------------------------------ the world

TEB, GDT = 0x7FFD0000, 0x7FFE0000
KERNEL32 = 0x77000000                    # the handle GetModuleHandleA("KERNEL32.dll") gives (never mapped)
COMPANION_BASE, GAME_MODULE_BASE = 0x50000000, 0x68000000
INVALID = 0xFFFFFFFF
GENERIC_WRITE = 0x40000000
STARTUPS = {"FtfpStartup": 0, "FtfpStoreStartup": 4, "FtfpUpgradesStartup": 0, "FtfpSeedBoxesStartup": 0}


class Crash(AssertionError):
    pass


class Machine(E.Emulator if E else object):
    """store_emulator's emulator, which also tells the world each instruction it runs."""

    def __init__(self, exe: Path, world: "World") -> None:
        self.world = world
        super().__init__(exe, None, {})

    def _on_code(self, uc, address: int, size: int, data: object) -> None:
        world = self.world
        world.recent[world.cursor & 15] = world.last = address
        world.cursor += 1
        if COMPANION_BASE <= address < COMPANION_BASE + 0x10000000:
            world.ran[(address - COMPANION_BASE) >> 24] += 1
        if address in world.entries:
            world.on_entry(address)
        frames = world.frames
        if frames and address == frames[-1][1] and uc.reg_read(X.UC_X86_REG_ESP) == frames[-1][2]:
            world.on_return()
        super()._on_code(uc, address, size, data)


class World:
    """The built game in Unicorn: its executable, the game's own DLLs it imports, and every
    companion DLL of the built folder, mapped (not loaded until something loads them)."""

    def __init__(self, b: Build) -> None:
        self.build = b
        self.emu = emu = Machine(b.exe, self)
        self.uc = uc = emu.uc
        self.last = 0
        self.recent, self.cursor = [0] * 16, 0             # the last 16 instructions run
        self.ran = [0] * 16                                 # instructions each companion ran (by its slot)
        self.top_level: list[str] = []                      # the startups the loader itself called
        self.entries: dict[int, tuple[str, str, int]] = {}
        self.frames: list[tuple[str, int, int, str]] = []
        self.startups: list[tuple[str, str, int]] = []      # (dll, export, result), in the order they returned
        self.load_order: list[str] = []
        self.dll_mains: dict[str, int] = {}                 # dll -> the module DisableThreadLibraryCalls got
        self.writes: dict[str, dict[str, set[int]]] = {"startup": {}, "run": {}}
        self.order: dict[int, list[str]] = {}               # each byte the DLLs wrote: who wrote it, in turn
        self.log_calls: list[tuple[str, int]] = []          # the stand-ins called while the game ran
        self.phase = "startup"
        self.files: dict[str, tuple[str, bytearray]] = {}   # what the DLLs wrote, by lower-case path
        self.ini: dict[tuple[str, str, str], str] = {}
        self.handles: dict[int, dict] = {}
        self.next_handle = 0x1000
        self.last_error = 0
        self.messages: list[str] = []
        self.thunks: dict[tuple[str, str], int] = {}
        self.system: dict[str, int] = {"kernel32.dll": KERNEL32}   # Windows' own DLLs: a handle each, never mapped
        self.tick = 1000
        self._teb()
        self.api = self._api()
        self.pending = emu.alloc(4)
        self.load_library = {"LoadLibraryW": self._trampoline(4), "LoadLibraryExW": self._trampoline(12)}

        exe = self.exe_data = b.exe.read_bytes()
        _base, self.exe_size, self.exe_sections, exe_imports = E.pe_image(exe)
        self.modules: list[Module] = []
        base = GAME_MODULE_BASE
        for lib in self._libraries(0x400000, exe_imports):
            path = b.folder / lib
            if path.is_file():
                module = Module(path, base, companion=False)
                self.modules.append(module)
                base += (module.size + 0xFFFFF) & ~0xFFFFF
        for module in list(self.modules):
            self._map(module)
        self._resolve(0x400000, exe_imports, "the game", None)
        for i, path in enumerate(sorted(b.dll_folder.glob("*.dll")) if b.dll_folder.is_dir() else []):
            module = Module(path, COMPANION_BASE + 0x1000000 * i, companion=True)
            self.modules.append(module)
            self._map(module)
        self.companions = {m.name: m for m in self.modules if m.companion}
        self.loaded: set[str] = {m.name for m in self.modules if not m.companion}
        uc.hook_add(UC_HOOK_MEM_WRITE, self._on_write, begin=0x400000, end=0x400000 + self.exe_size - 1)
        for module in self.modules:
            if not module.companion:
                uc.hook_add(UC_HOOK_MEM_WRITE, self._on_write, begin=module.base,
                            end=module.base + module.size - 1)

    # ---------------------------------------------------------- memory and images
    def _teb(self) -> None:
        uc = self.uc
        uc.mem_map(TEB, 0x2000)
        uc.mem_write(TEB, struct.pack("<7I", INVALID, E.STACK + E.STACK_SIZE, E.STACK, 0, 0, 0, TEB))
        uc.mem_map(GDT, 0x1000)

        def descriptor(base: int, limit: int, flags: int) -> bytes:       # a ring-0 read/write data segment
            return struct.pack("<Q", (limit & 0xFFFF) | (base & 0xFFFFFF) << 16 | 0x92 << 40
                               | (limit >> 16 & 0xF) << 48 | flags << 52 | (base >> 24) << 56)
        uc.mem_write(GDT + 8 * 2, descriptor(0, 0xFFFFF, 0xC))                # flat: ss, ds, es
        uc.mem_write(GDT + 8 * 3, descriptor(TEB, 0xFFF, 0x4))                # fs: the thread's TEB
        uc.reg_write(X.UC_X86_REG_GDTR, (0, GDT, 0xFFF, 0))
        for reg in (X.UC_X86_REG_SS, X.UC_X86_REG_DS, X.UC_X86_REG_ES):
            uc.reg_write(reg, 2 << 3)
        uc.reg_write(X.UC_X86_REG_FS, 3 << 3)

    def module_at(self, address: int) -> Module | None:
        return next((m for m in self.modules if m.contains(address)), None)

    def where(self, address: int) -> str:
        module = self.module_at(address)
        if module is not None:
            return f"{module.name}+0x{address - module.base:X}"
        if 0x400000 <= address < 0x400000 + self.exe_size:
            return f"the game at 0x{address:X}"
        return f"0x{address:X}"

    def _libraries(self, base: int, imports_rva: int) -> list[str]:
        out, at = [], imports_rva
        while True:
            lookup, _t, _f, name, iat = struct.unpack("<5I", self.uc.mem_read(base + at, 20))
            if lookup == 0 and iat == 0:
                return out
            out.append(self.emu.cstring(base + name).decode("ascii"))
            at += 20

    def _map(self, module: Module) -> None:
        uc, emu = self.uc, self.emu
        uc.mem_map(module.base, (module.size + 0xFFF) & ~0xFFF)
        uc.mem_write(module.base, module.data[:0x1000])
        for rva, raw, raw_size in module.sections:
            uc.mem_write(module.base + rva, module.data[raw:raw + raw_size])
        rva, size = _directory(module.data, 5)
        at, end = rva, rva + size
        while module.delta and at < end:
            page, block = struct.unpack("<II", uc.mem_read(module.base + at, 8))
            if block == 0:
                break
            for i in range((block - 8) // 2):
                entry = struct.unpack("<H", uc.mem_read(module.base + at + 8 + 2 * i, 2))[0]
                if entry >> 12 == 3:                                       # IMAGE_REL_BASED_HIGHLOW
                    where = module.base + page + (entry & 0xFFF)
                    emu.write32(where, emu.read32(where) + module.delta)
            at += block
        self._resolve(module.base, module.imports_rva, module.name, module)

    def _resolve(self, base: int, imports_rva: int, who: str, module: Module | None) -> None:
        """Point every import slot at what Windows would: a game DLL's own export, or a thunk the
        harness answers (an import it does not answer fails the test when it is called)."""
        emu, at = self.emu, imports_rva
        while True:
            lookup, _t, _f, name_rva, iat = struct.unpack("<5I", self.uc.mem_read(base + at, 20))
            if lookup == 0 and iat == 0:
                return
            lib = emu.cstring(base + name_rva).decode("ascii")
            slot = 0
            while True:
                entry = emu.read32(base + (lookup or iat) + 4 * slot)
                if entry == 0:
                    break
                name = f"#{entry & 0xFFFF}" if entry & 0x80000000 else emu.cstring(base + entry + 2).decode("ascii")
                emu.write32(base + iat + 4 * slot, self._import(lib, name, who))
                if module is not None:
                    module.slots[name] = base + iat + 4 * slot
                slot += 1
            at += 20

    def _import(self, lib: str, name: str, who: str) -> int:
        game_module = next((m for m in self.modules if not m.companion and m.name.lower() == lib.lower()), None)
        if game_module is not None:
            if name not in game_module.exports:
                raise AssertionError(f"{who} imports {lib}!{name}, which it does not export")
            return game_module.exports[name]
        self.system.setdefault(lib.lower(), KERNEL32 + 0x10000 * len(self.system))
        if name in ("LoadLibraryW", "LoadLibraryExW"):
            return self.load_library[name]
        return self.thunk(lib, name)

    def thunk(self, lib: str, name: str) -> int:
        key = (lib.lower(), name)
        if key not in self.thunks:
            thunk = self.thunks[key] = self.emu.thunk()
            if name in self.api:
                handler, pop = self.api[name]
                self.emu.hook(thunk, handler, pop)
            else:
                def missing(e, lib=lib, name=name) -> int:
                    raise Crash(f"{lib}!{name} was called from {self.where(e.read32(e.uc.reg_read(X.UC_X86_REG_ESP)))}"
                                ", and the harness does not provide it")
                self.emu.hook(thunk, missing, 0)
        return self.thunks[key]

    def _trampoline(self, pop: int) -> int:
        """LoadLibraryW / LoadLibraryExW: the DLL is found (a Python hook), and the first time it
        loads its DllMain(module, DLL_PROCESS_ATTACH, 0) runs, as Windows' loader runs it."""
        emu = self.emu
        resolve = emu.thunk()
        emu.hook(resolve, lambda e: self._load(e.wstring(e.arg(0))), 4)
        code = emu.alloc(0x40)
        body = (b"\xFF\x74\x24\x04"                                        # push [esp+4] (the path)
                + b"\xE8" + struct.pack("<i", resolve - (code + 9))         # call resolve
                + b"\x85\xC0\x74\x13"                                      # test eax, eax; jz done
                + b"\x8B\x0D" + struct.pack("<I", self.pending)            # mov ecx, [pending]: DllMain or 0
                + b"\x85\xC9\x74\x09"                                      # test ecx, ecx; jz done
                + b"\x50\x6A\x00\x6A\x01\x50\xFF\xD1\x58"                  # push eax; DllMain(eax, 1, 0); pop eax
                + b"\xC2" + struct.pack("<H", pop))                        # done: ret pop
        assert len(body) == 35
        self.uc.mem_write(code, body)
        return code

    def _load(self, path: str) -> int:
        module = next((m for m in self.modules if m.path.lower() == path.lower()), None)
        self.emu.write32(self.pending, 0)
        if module is None:
            self.last_error = 126                                          # ERROR_MOD_NOT_FOUND
            return 0
        if module.companion and module.name not in self.loaded:
            for export, pop in STARTUPS.items():
                if export in module.exports:
                    self.entries[module.exports[export]] = (module.name, export, pop)
            self.loaded.add(module.name)
            self.load_order.append(module.name)
            self.emu.write32(self.pending, module.dll_main())
        return module.base

    # ---------------------------------------------------------- Windows, as the DLLs see it
    def _api(self) -> dict:
        """The Windows functions the companions (and the game's code the frames run) call, each
        (handler, bytes its stdcall pops). Files resolve to the built folder, read only; whatever a
        DLL writes stays in memory."""
        def ok(pop: int, result: int = 1):
            return (lambda e: result, pop)

        def last_error(e) -> int:
            return self.last_error

        def set_last_error(e) -> int:
            self.last_error = e.arg(0)
            return 0

        def tick(e) -> int:
            self.tick += 16
            return self.tick

        def counter(e) -> int:
            self.tick += 16
            e.uc.mem_write(e.arg(0), struct.pack("<Q", self.tick * 1000))
            return 1

        def frequency(e) -> int:
            e.uc.mem_write(e.arg(0), struct.pack("<Q", 1_000_000))
            return 1

        def message_box(e) -> int:
            self.messages.append(e.wstring(e.arg(1)) if e.arg(1) else "")
            return 1

        def crash(name: str):
            def handler(e) -> int:
                raise Crash(f"{name} was called from {self.where(e.read32(e.uc.reg_read(X.UC_X86_REG_ESP)))}")
            return handler

        api = {
            "GetModuleHandleA": (lambda e: self._module_handle(e.cstring(e.arg(0)).decode("latin-1") if e.arg(0) else None), 4),
            "GetModuleHandleW": (lambda e: self._module_handle(e.wstring(e.arg(0)) if e.arg(0) else None), 4),
            "GetModuleHandleExW": (self._module_handle_ex, 12),
            "GetProcAddress": (self._get_proc, 8),
            "GetModuleFileNameW": (self._module_file_name, 12),
            "FreeLibrary": ok(4),
            "DisableThreadLibraryCalls": (self._disable_thread_calls, 4),
            "VirtualProtect": (self._virtual_protect, 16),
            "VirtualQuery": (self._virtual_query, 12),
            "FlushInstructionCache": ok(12),
            "GetCurrentProcess": ok(0, INVALID),
            "GetCurrentProcessId": ok(0, 0x1234),
            "GetCurrentThreadId": ok(0, 0x5678),
            "GetLastError": (last_error, 0),
            "SetLastError": (set_last_error, 4),
            "GetTickCount": (tick, 0),
            "QueryPerformanceCounter": (counter, 4),
            "QueryPerformanceFrequency": (frequency, 4),
            "GetFileAttributesW": (self._file_attributes, 4),
            "CreateFileW": (self._create_file, 28),
            "ReadFile": (self._read_file, 20),
            "WriteFile": (self._write_file, 20),
            "FlushFileBuffers": ok(4),
            "CloseHandle": (lambda e: 1 if self.handles.pop(e.arg(0), None) is not None else 0, 4),
            "GetFileSizeEx": (self._file_size, 8),
            "SetFilePointerEx": (self._file_pointer, 20),
            "CreateDirectoryW": ok(8),
            "MoveFileExW": (self._move_file, 12),
            "DeleteFileW": (lambda e: 1 if self.files.pop(e.wstring(e.arg(0)).lower(), None) else 0, 4),
            "FindFirstFileExW": ok(24, INVALID),
            "FindNextFileW": ok(8, 0),
            "FindClose": ok(4),
            "GetPrivateProfileIntW": (self._profile_int, 16),
            "WritePrivateProfileStringW": (self._write_profile, 16),
            "lstrcmpiW": (lambda e: self._compare(e.wstring(e.arg(0)).lower(), e.wstring(e.arg(1)).lower()), 8),
            "lstrcmpiA": (lambda e: self._compare(e.cstring(e.arg(0)).lower(), e.cstring(e.arg(1)).lower()), 8),
            "lstrcmpA": (lambda e: self._compare(e.cstring(e.arg(0)), e.cstring(e.arg(1))), 8),
            "MultiByteToWideChar": (self._to_wide, 24),
            "WideCharToMultiByte": (self._to_narrow, 32),
            "GetProcessHeap": ok(0, 0x00A00000),
            "HeapAlloc": (lambda e: self._alloc(e.arg(2)), 12),
            "HeapFree": ok(12),
            "HeapReAlloc": (self._realloc, 16),
            "EnterCriticalSection": ok(4, 0),
            "LeaveCriticalSection": ok(4, 0),
            "InitializeCriticalSectionEx": ok(12),
            "DeleteCriticalSection": ok(4, 0),
            "EncodePointer": (lambda e: e.arg(0), 4),
            "DecodePointer": (lambda e: e.arg(0), 4),
            "IsDebuggerPresent": ok(0, 0),
            "MessageBoxW": (message_box, 16),
        }
        for name in ("RaiseException", "RtlUnwind", "TerminateProcess", "ExitProcess", "UnhandledExceptionFilter"):
            api[name] = (crash(name), 0)
        return api

    @staticmethod
    def _compare(a, b) -> int:
        return 0 if a == b else (-1 if a < b else 1)

    def _alloc(self, size: int) -> int:
        address = self.emu.alloc(max(size, 4) + 16)
        self.emu.write32(address, size)
        self.uc.mem_write(address + 16, bytes(max(size, 4)))
        return address + 16

    def _realloc(self, e) -> int:
        old, size = e.arg(2), e.arg(3)
        new = self._alloc(size)
        if old:
            keep = min(e.read32(old - 16), size)
            e.uc.mem_write(new, bytes(e.uc.mem_read(old, keep)))
        return new

    def _module_handle(self, name: str | None) -> int:
        if name is None:
            return 0x400000
        base = name.replace("/", "\\").rsplit("\\", 1)[-1].lower()
        for lib in (base, base + ".dll"):
            if lib in self.system:
                return self.system[lib]
        for module in self.modules:
            if module.name.lower() in (base, base + ".dll") and module.name in self.loaded:
                return module.base
        return 0

    def _module_handle_ex(self, e) -> int:
        flags, address = e.arg(0), e.arg(1)
        if not flags & 4:                                                   # FROM_ADDRESS only
            raise Crash(f"GetModuleHandleExW(0x{flags:X}) by name is not provided")
        module = self.module_at(address)
        base = module.base if module else 0x400000 if 0x400000 <= address < 0x400000 + self.exe_size else 0
        e.write32(e.arg(2), base)
        return 1 if base else 0

    def _get_proc(self, e) -> int:
        handle, name_at = e.arg(0), e.arg(1)
        if name_at < 0x10000:
            return 0
        name = e.cstring(name_at).decode("latin-1")
        lib = next((lib for lib, h in self.system.items() if h == handle), None)
        if lib is not None:
            return self._import(lib, name, "GetProcAddress")
        module = next((m for m in self.modules if m.base == handle), None)
        return module.exports.get(name, 0) if module else 0

    def path_of(self, handle: int) -> str:
        if handle in (0, 0x400000):
            return str(self.build.exe)
        module = next((m for m in self.modules if m.base == handle), None)
        if module is None:
            raise Crash(f"GetModuleFileNameW(0x{handle:X}): no such module")
        return module.path

    def _module_file_name(self, e) -> int:
        path, size = self.path_of(e.arg(0)), e.arg(2)
        text = path[:size - 1] if len(path) >= size else path
        e.uc.mem_write(e.arg(1), text.encode("utf-16-le") + b"\0\0")
        return size if len(path) >= size else len(path)

    def _disable_thread_calls(self, e) -> int:
        module = self.module_at(e.read32(e.uc.reg_read(X.UC_X86_REG_ESP)))
        self.dll_mains[module.name if module else "?"] = e.arg(0)
        return 1

    def _virtual_protect(self, e) -> int:
        address, size = e.arg(0), e.arg(1)
        if not self._mapped(address) or not self._mapped(address + max(size, 1) - 1):
            self.last_error = 487
            return 0
        e.write32(e.arg(3), 0x20 if 0x400000 <= address < 0x400000 + self.exe_size else 0x04)
        return 1

    def _mapped(self, address: int) -> bool:
        return any(start <= address <= end for start, end, _perms in self.uc.mem_regions())

    def _virtual_query(self, e) -> int:
        address, info = e.arg(0), e.arg(1)
        page = address & ~0xFFF
        region = next(((start, end) for start, end, _p in self.uc.mem_regions() if start <= address <= end), None)
        if region is None:
            e.uc.mem_write(info, struct.pack("<7I", page, 0, 0, 0x1000, 0x10000, 0x01, 0))
            return 28
        module = self.module_at(address)
        allocation = module.base if module else 0x400000 if 0x400000 <= address < 0x400000 + self.exe_size \
            else region[0]
        e.uc.mem_write(info, struct.pack("<7I", page, allocation, 0x20, region[1] + 1 - page, 0x1000, 0x20, 0x1000000))
        return 28

    # files: the built folder, read only; everything written stays in memory
    def _real(self, path: str) -> Path | None:
        folder = str(self.build.folder)
        if path.lower().startswith(folder.lower() + "\\"):
            return Path(folder) / path[len(folder) + 1:]
        return None

    def _contents(self, path: str) -> bytes | None:
        if path.lower() in self.files:
            return bytes(self.files[path.lower()][1])
        real = self._real(path)
        return real.read_bytes() if real is not None and real.is_file() else None

    def _file_attributes(self, e) -> int:
        path = e.wstring(e.arg(0))
        if path.lower() in self.files:
            return 0x20
        real = self._real(path)
        if real is not None and real.exists():
            return 0x10 if real.is_dir() else 0x20
        self.last_error = 2
        return INVALID

    def _create_file(self, e) -> int:
        path, access, disposition = e.wstring(e.arg(0)), e.arg(1), e.arg(4)
        old = self._contents(path)
        if access & GENERIC_WRITE:
            if disposition == 1 and old is not None or disposition in (3, 5) and old is None:
                self.last_error = 80 if disposition == 1 else 2
                return INVALID
            data = bytearray(old or b"") if disposition in (3, 4) else bytearray()
            self.files[path.lower()] = (path, data)
        elif old is None:
            self.last_error = 2
            return INVALID
        else:
            data = bytearray(old)
        handle = self.next_handle
        self.next_handle += 4
        self.handles[handle] = {"path": path, "data": data, "at": 0}
        return handle

    def _handle(self, e) -> dict:
        handle = self.handles.get(e.arg(0))
        if handle is None:
            raise Crash(f"a file call on the unknown handle 0x{e.arg(0):X}")
        return handle

    def _read_file(self, e) -> int:
        h = self._handle(e)
        chunk = bytes(h["data"][h["at"]:h["at"] + e.arg(2)])
        e.uc.mem_write(e.arg(1), chunk)
        h["at"] += len(chunk)
        if e.arg(3):
            e.write32(e.arg(3), len(chunk))
        return 1

    def _write_file(self, e) -> int:
        h = self._handle(e)
        chunk = bytes(e.uc.mem_read(e.arg(1), e.arg(2)))
        h["data"][h["at"]:h["at"] + len(chunk)] = chunk
        h["at"] += len(chunk)
        self.files[h["path"].lower()] = (h["path"], h["data"])
        if e.arg(3):
            e.write32(e.arg(3), len(chunk))
        return 1

    def _file_size(self, e) -> int:
        e.uc.mem_write(e.arg(1), struct.pack("<Q", len(self._handle(e)["data"])))
        return 1

    def _file_pointer(self, e) -> int:
        h = self._handle(e)
        move = struct.unpack("<q", struct.pack("<II", e.arg(1), e.arg(2)))[0]
        h["at"] = {0: 0, 1: h["at"], 2: len(h["data"])}[e.arg(4)] + move
        if e.arg(3):
            e.uc.mem_write(e.arg(3), struct.pack("<q", h["at"]))
        return 1

    def _move_file(self, e) -> int:
        source, target = e.wstring(e.arg(0)), e.wstring(e.arg(1))
        entry = self.files.pop(source.lower(), None)
        if entry is None:
            self.last_error = 2
            return 0
        self.files[target.lower()] = (target, entry[1])
        return 1

    def _profile_int(self, e) -> int:
        section, key, default, path = e.wstring(e.arg(0)), e.wstring(e.arg(1)), e.arg(2), e.wstring(e.arg(3))
        value = self.ini.get((path.lower(), section.lower(), key.lower()))
        if value is None:
            text = (self._contents(path) or b"").decode("latin-1")
            current = None
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current = line[1:-1].strip().lower()
                elif "=" in line and current == section.lower():
                    name, _, found = line.partition("=")
                    if name.strip().lower() == key.lower():
                        value = found.strip()
        try:
            return int(value) & 0xFFFFFFFF if value is not None else default
        except ValueError:
            return 0

    def _write_profile(self, e) -> int:
        section, key, path = e.wstring(e.arg(0)), e.wstring(e.arg(1)), e.wstring(e.arg(3))
        self.ini[(path.lower(), section.lower(), key.lower())] = e.wstring(e.arg(2)) if e.arg(2) else ""
        return 1

    def _to_wide(self, e) -> int:
        source, count, target, room = e.arg(2), e.arg(3), e.arg(4), e.arg(5)
        text = e.cstring(source) + b"\0" if count == INVALID else bytes(e.uc.mem_read(source, count))
        out = text.decode("latin-1").encode("utf-16-le")
        if room:
            e.uc.mem_write(target, out[:2 * room])
        return len(out) // 2

    def _to_narrow(self, e) -> int:
        source, count, target, room = e.arg(2), e.arg(3), e.arg(4), e.arg(5)
        text = e.wstring(source) + "\0" if count == INVALID else bytes(e.uc.mem_read(source, 2 * count)).decode("utf-16-le")
        out = text.encode("latin-1", "replace")
        if room:
            e.uc.mem_write(target, out[:room])
        return len(out)

    def log(self, dll: str) -> str | None:
        """What a companion wrote to "<its name>.log" beside it."""
        path = str(self.build.dll_folder / (dll[:-4] + ".log")).lower()
        return bytes(self.files[path][1]).decode("latin-1") if path in self.files else None

    # ---------------------------------------------------------- startups and writes
    def on_entry(self, address: int) -> None:
        dll, export, pop = self.entries[address]
        esp = self.uc.reg_read(X.UC_X86_REG_ESP)
        self.frames.append((dll, self.emu.read32(esp), esp + 4 + pop, export))

    def on_return(self) -> None:
        dll, _back, _esp, export = self.frames.pop()
        self.startups.append((dll, export, self.uc.reg_read(X.UC_X86_REG_EAX)))
        if not self.frames:
            self.top_level.append(dll)

    def instructions_run(self, dll: str) -> int:
        """How many instructions of a companion ran since the counts were cleared."""
        return self.ran[(self.companions[dll].base - COMPANION_BASE) >> 24]

    def _on_write(self, uc, _access, address: int, size: int, _value: int, _data: object) -> None:
        module = self.module_at(uc.reg_read(X.UC_X86_REG_EIP))
        if module is not None and module.companion:
            self.writes[self.phase].setdefault(module.name, set()).update(range(address, address + size))
            if self.phase == "startup":
                for byte in range(address, address + size):
                    order = self.order.setdefault(byte, [])
                    if not order or order[-1] != module.name:
                        order.append(module.name)

    # ---------------------------------------------------------- the startup loader
    def run_loader(self) -> None:
        """From the C runtime's call of WinMain to WinMain: the .ftfpst stub and every DLL it starts."""
        uc, emu, profile = self.uc, self.emu, self.build.profile
        call = profile.winmain_call_va
        code = bytes(uc.mem_read(call, 5))
        if code[0] != 0xE8:
            raise AssertionError(f"0x{call:X} is not a call")
        stub = call + 5 + struct.unpack("<i", code[1:])[0]
        if self.module_at(stub) is not None or not 0x400000 <= stub < 0x400000 + self.exe_size:
            raise AssertionError(f"the call of WinMain goes to 0x{stub:X}, not into the executable")
        esp = E.STACK + E.STACK_SIZE - 0x2000
        emu.write32(esp, call + 5)                                     # the call's return address
        sentinels = {X.UC_X86_REG_EBX: 0x0B0B0B0B, X.UC_X86_REG_ESI: 0x05150515, X.UC_X86_REG_EDI: 0x0D1D0D1D,
                     X.UC_X86_REG_EBP: 0x0B9B0B9B, X.UC_X86_REG_ECX: 0x0C0C0C0C, X.UC_X86_REG_EDX: 0x0D0D0D0D,
                     X.UC_X86_REG_EAX: 0x0A0A0A0A}
        for reg, value in sentinels.items():
            uc.reg_write(reg, value)
        uc.reg_write(X.UC_X86_REG_ESP, esp)
        uc.reg_write(X.UC_X86_REG_FPCW, 0x027F)
        self.run(stub, profile.winmain_va, "the startup loader")
        if uc.reg_read(X.UC_X86_REG_ESP) != esp or emu.read32(esp) != call + 5:
            raise AssertionError("the startup loader reached WinMain with a different stack")
        changed = [hex(value) for reg, value in sentinels.items() if uc.reg_read(reg) != value]
        if changed:
            raise AssertionError(f"the startup loader reached WinMain with registers changed: {changed}")
        if self.frames:
            raise AssertionError(f"startups that never returned: {self.frames}")

    def run(self, start: int, stop: int, what: str, count: int = 100_000_000) -> None:
        try:
            self.uc.emu_start(start, stop, count=count)
        except UcError as exc:
            raise Crash(f"{what}: {exc} at {self.where(self.uc.reg_read(X.UC_X86_REG_EIP))} "
                        f"(the instructions before it: {self.history()}; on the stack: {self.trace()})") from None
        eip = self.uc.reg_read(X.UC_X86_REG_EIP)
        if eip != stop:
            raise Crash(f"{what}: did not finish (stopped at {self.where(eip)} after {count} instructions)")

    def history(self) -> str:
        last = [self.recent[(self.cursor + i) & 15] for i in range(16)]
        return ", ".join(self.where(a) for a in last[-6:] if a)

    def trace(self) -> str:
        """The return addresses on the stack, nearest first: where the crash was called from."""
        esp, out = self.uc.reg_read(X.UC_X86_REG_ESP), []
        for i in range(96):
            try:
                value = self.emu.read32(esp + 4 * i)
            except UcError:
                break
            in_code = 0x401000 <= value < 0x440000 if self.build.game == "fish" else 0x401000 <= value < 0x465000
            module = self.module_at(value)
            if in_code or module is not None and module.companion:
                out.append(self.where(value))
        return ", ".join(out[:12])

    def call(self, address: int, *args: int, ecx: int = 0, what: str = "") -> int:
        """A thiscall/stdcall of the game's or a DLL's code that must return to its caller."""
        emu, uc = self.emu, self.uc
        esp = E.STACK + E.STACK_SIZE - 0x1000
        for value in reversed(args):
            esp -= 4
            emu.write32(esp, value)
        esp -= 4
        emu.write32(esp, E.RETURN)
        uc.reg_write(X.UC_X86_REG_ESP, esp)
        uc.reg_write(X.UC_X86_REG_ECX, ecx)
        uc.reg_write(X.UC_X86_REG_FPCW, 0x027F)
        self.run(address, E.RETURN, what or self.where(address), count=20_000_000)
        return uc.reg_read(X.UC_X86_REG_EAX)

    # ---------------------------------------------------------- the game's code, running
    def stand_in(self, address: int, name: str, pop: int, result=0) -> None:
        """A game primitive (a draw, a sound, the clock) answered in Python: it records the call
        and returns `result` (or result(emulator))."""
        def handler(e) -> int:
            self.log_calls.append((name, e.read32(e.uc.reg_read(X.UC_X86_REG_ESP))))
            return result(e) if callable(result) else result
        self.emu.hook(address, handler, pop)

    def pops(self, address: int) -> int:
        """What a function of the game pops on return (its `ret n`), following tail jumps, in the
        executable as the patcher built it (a DLL's jump into its own stub is not the game's)."""
        for _hop in range(6):
            if self.built_code(address, address + 2) == b"\xFF\x25":       # jmp [import]
                module = self.module_at(self.emu.read32(_u32(self.built_code(address, address + 6), 2)))
                if module is not None and not module.companion:
                    return 0                                              # SDL's functions are cdecl
                raise AssertionError(f"0x{address:X} jumps to a Windows import")
            _calls, tails, pops = self.walk(address)
            if len(pops) == 1:
                return pops.pop()
            if pops or len(tails) != 1:
                raise AssertionError(f"0x{address:X} returns {sorted(pops)} and tail-jumps to {sorted(tails)}")
            address = tails.pop()
        raise AssertionError(f"no return found in 0x{address:X}")

    def built_code(self, start: int, end: int) -> bytes:
        """The executable's bytes as the patcher wrote them (before any DLL changed them)."""
        return self.exe_data[_rva_to_raw(self.exe_sections, start - 0x400000):][:end - start]

    def walk(self, start: int) -> tuple[set[int], set[int], set[int]]:
        """The game's function at `start`, followed from its entry along every branch, as the
        patcher built it (a site a DLL changed still names the game's function, which the DLL's hook
        calls in turn): (the functions it calls, the ones it tail-jumps to, what its `ret`s pop)."""
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        limit = self.extent(start)
        in_exe = range(0x401000, 0x400000 + self.exe_size)
        seen, todo, calls, tails, pops = set(), [start], set(), set(), set()
        while todo:
            at = todo.pop()
            while start <= at < limit and at not in seen:
                seen.add(at)
                ins = next(md.disasm(self.built_code(at, at + 16), at), None)
                if ins is None:
                    break
                op = ins.op_str
                target = int(op, 16) if op.startswith("0x") else None
                if ins.mnemonic == "call":
                    if target in in_exe:
                        calls.add(target)
                elif ins.mnemonic.startswith("ret"):
                    pops.add(int(op, 16) if op else 0)
                    break
                elif ins.mnemonic == "jmp":
                    if target is not None:
                        (todo.append if start <= target < limit else tails.add)(target)
                    table = re.search(r"\*\s*4\s*\+\s*(0x[0-9a-f]+)\]", op)        # a switch's jump table
                    if table:
                        entry = int(table.group(1), 16)
                        while start <= _u32(self.built_code(entry, entry + 4), 0) < limit:
                            todo.append(_u32(self.built_code(entry, entry + 4), 0))
                            entry += 4
                    break
                elif ins.mnemonic.startswith(("j", "loop")) and target is not None:
                    todo.append(target)
                at += ins.size
        return calls, tails, pops

    def callees(self, start: int) -> set[int]:
        """Every function the game's function at `start` calls or tail-jumps to."""
        calls, tails, _pops = self.walk(start)
        return calls | {t for t in tails if 0x401000 <= t < 0x400000 + self.exe_size}

    def extent(self, start: int) -> int:
        """Where the game's function at `start` ends: the int3 padding the compiler put after it
        (the first int3 at an instruction's place, read in order from its start)."""
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.skipdata = True
        for ins in md.disasm(self.built_code(start, start + 0x4000), start):
            if ins.mnemonic == "int3":
                return ins.address
        raise AssertionError(f"no end found for 0x{start:X}")

    def stand_in_callees(self, start: int, keep: set[int]) -> list[int]:
        """Every function the game's function at `start` calls becomes a recorded stand-in, except
        `keep` (run for real) and the primitives already answered."""
        done = []
        for target in sorted(self.callees(start)):
            if target in keep or target in self.emu.hooks:
                continue
            if self.built_code(target, target + 2) == b"\xFF\x25":         # jmp [import]: Windows' or SDL's
                continue
            calls, tails, _pops = self.walk(target)
            if not calls and not tails and self.extent(target) - target <= 0x20:
                continue                                                  # an accessor: it runs for real
            self.stand_in(target, f"game 0x{target:X}", self.pops(target))
            done.append(target)
        return done

    def screen(self, table: int, size: int) -> int:
        """A screen object for the game's own screen code: its table, its node (shown, one control
        whose draw and overlay are recorded)."""
        emu = self.emu
        control_table = emu.alloc(0x40)
        for slot, what in ((0x18, "control draw"), (0x1C, "control overlay")):
            thunk = emu.thunk()
            self.stand_in(thunk, what, 0)
            emu.write32(control_table + slot, thunk)
        control = emu.alloc(0x40)
        emu.write32(control, control_table)
        link = emu.alloc(8)
        emu.write32(link, control)
        emu.write32(link + 4, 0)
        node = emu.alloc(0x40)
        emu.uc.mem_write(node, bytes(0x40))
        emu.write8(node, 1)                                            # shown
        emu.write32(node + 0x18, link)
        scene = emu.alloc(size)
        emu.uc.mem_write(scene, bytes(size))
        emu.write32(scene, table)
        emu.write32(scene + 4, node)
        return scene


# ------------------------------------------------------------------ the screens, running

def alloc_zero(w: World, size: int) -> int:
    address = w.emu.alloc(size)
    w.uc.mem_write(address, bytes(size))
    return address


class FishTankScreen:
    """Fish Tycoon's tank screen (its table 0x443A54), with four fish in Tank One and the Cleaning
    Snail. Each tick is the screen's own update (0x40A990: table +0x20, 0x4220A0) with the clock
    moved on so the 5-minute fish update runs (0x4218D0 -> 0x41FE70, the game's own fish update, with
    every DLL hook on its path); each frame is the game's paint of a screen (0x40AC90: table +0x18,
    the tank's draw 0x422010; its controls; +0x1C, the overlay 0x41CF20)."""

    TABLE = 0x443A54
    STATE_GLOBAL = 0x45ABDC
    STATE_SIZE = 0x1E600
    UPDATE, PAINT = 0x40A990, 0x40AC90
    # The game's functions that run for real (with every DLL hook in them); what they call is a
    # recorded stand-in: the update (0x4220A0), its 5-minute fish update (0x4218D0) and the fish
    # update itself (0x41FE70), the tank's draw (0x422010) and its overlay (0x41CF20).
    ROOTS = (0x4220A0, 0x4218D0, 0x41FE70, 0x422010, 0x41CF20)
    # the game's primitives: drawing, text, sound, the clock and the dice
    PRIMITIVES = {
        0x408A40: ("picture", 0xC), 0x408AA0: ("cell", 0x10), 0x408B80: ("text", 0x14),
        0x408C30: ("text", 0x14), 0x41BCA0: ("sprite grid", 4), 0x41BE70: ("sprite", 4),
        0x4181F0: ("font", 4), 0x418210: ("font manager", 0), 0x417FD0: ("messages shown", 0),
        0x402060: ("mouse", 0), 0x402080: ("mouse down", 0), 0x409540: ("image", 4), 0x4096C0: ("grid", 0xC),
    }

    def __init__(self, w: World) -> None:
        self.w = w
        emu = w.emu
        for address, (name, pop) in self.PRIMITIVES.items():
            result = {0x418210: lambda e: alloc_zero(w, 0x100), 0x4181F0: lambda e: alloc_zero(w, 0x100),
                      0x409540: lambda e: e.uc.reg_read(X.UC_X86_REG_ECX),
                      0x4096C0: lambda e: e.uc.reg_read(X.UC_X86_REG_ECX),
                      0x41BCA0: 0x5000, 0x41BE70: 0x5000}.get(address, 0)
            w.stand_in(address, name, pop, result)
        w.stand_in(0x42A793, "new", 0, lambda e: alloc_zero(w, max(e.arg(0), 4)))
        w.stand_in(0x4020D0, "the clock", 0, lambda e: self.now())
        w.stand_in(0x403240, "dice", 0, 0)
        self.clock = 100_000
        for root in self.ROOTS:
            w.stand_in_callees(root, keep=set(self.ROOTS))

        state = self.state = alloc_zero(w, self.STATE_SIZE)
        emu.write32(self.STATE_GLOBAL, state)
        emu.write32(state + 0x1E4E8, 0xFFFFFFFF)                      # nothing in the hand
        emu.write32(state + 0x140, 1)                                 # the Cleaning Snail
        emu.write32(state + 0x1E168, 10)                              # as a new game sets it (0x418AFB)
        for slot, age in enumerate((25, 25, 8, 3)):                   # four fish in Tank One
            at = state + 0x390 + slot * 0x288
            emu.write32(at, 1000)
            emu.write32(at + 0x0C, age)
            emu.write32(at + 0x3C, 100)
            emu.write32(at + 0x4C, 3)
        impl = self.impl = alloc_zero(w, 0x200)
        emu.write32(impl + 0x34, state)
        for at in (0x38, 0x3C, 0x40, 0x44, 0x4C, 0x50):              # sprites, view, bubbles, hints, sounds, dialogs
            emu.write32(impl + at, alloc_zero(w, 0x400))
        emu.write32(impl + 0x54, 0x00C0FFEE)                          # the graphics
        emu.write32(impl + 0x1C, 99)                                  # no tool in the hand
        emu.write32(impl + 0x28, 99)                                  # no ornament in the hand
        for b, left in enumerate((513, 610, 707)):                   # the tank buttons
            emu.uc.mem_write(impl + 0x58 + b * 0x10, struct.pack("<4i", left, 2, left + 85, 54))
        self.scene = w.screen(self.TABLE, 0x40)
        emu.write32(self.scene + 8, impl)

    def now(self) -> int:
        self.clock += 400                                             # past the 300 ms of the fish update
        return self.clock

    def tick(self) -> None:
        self.w.call(self.UPDATE, ecx=self.scene, what="the tank screen's update")

    def frame(self) -> None:
        self.w.call(self.PAINT, ecx=self.scene, what="the tank screen's paint")


class PlantScreen:
    """A Plant Tycoon screen, run through its own table: each tick the game's screen update
    (0x40B3B0: table +0x20), each frame the game's paint of a screen (0x40B6B0: table +0x18, the
    controls, +0x1C). Three plants grow in the greenhouse; ROOTS run for real, what they call is a
    recorded stand-in."""

    STATE_GLOBAL = 0x49333C
    STATE_SIZE = 0x63E70
    UPDATE, PAINT = 0x40B3B0, 0x40B6B0
    PRIMITIVES = {                    # each pops what its own `ret` pops
        0x407A90: "graphics", 0x4092A0: "text", 0x4092B0: "centred text", 0x4208F0: "sprite",
        0x44CC20: "money", 0x44CDE0: "money box", 0x41B1C0: "timed message",
    }
    TABLE = 0
    SIZE = 0x1000
    STATE_AT = 0x68
    ROOTS: tuple[int, ...] = ()
    WHAT = ""

    def __init__(self, w: World) -> None:
        self.w = w
        emu = w.emu
        for address, name in self.PRIMITIVES.items():
            if address not in emu.hooks:
                w.stand_in(address, name, w.pops(address), 0x00C0FFEE if address == 0x407A90 else 0)
        if 0x44CA70 not in emu.hooks:
            w.stand_in(0x44CA70, "string", 4, lambda e: e.text("text"))
            w.stand_in(0x44F30B, "sprintf", 0, 0)
        for root in self.ROOTS:
            w.stand_in_callees(root, keep=set(self.ROOTS))
        state = emu.read32(self.STATE_GLOBAL)
        if state == 0:
            state = alloc_zero(w, self.STATE_SIZE)
            emu.write32(self.STATE_GLOBAL, state)
            for k, age in enumerate((25.0, 22.0, 3.0)):                # three plants in the greenhouse
                at = state + 0x2188 + k * 0x5600
                emu.uc.mem_write(at + 0x10, struct.pack("<f", age))
                emu.write32(at + 0x24, 90)
                emu.write32(at + 0x4C, 1)
        self.state = state
        self.scene = w.screen(self.TABLE, self.SIZE)
        emu.write32(self.scene + self.STATE_AT, state)

    def tick(self) -> None:
        self.w.call(self.UPDATE, ecx=self.scene, what=f"the {self.WHAT}'s update")

    def frame(self) -> None:
        self.w.call(self.PAINT, ecx=self.scene, what=f"the {self.WHAT}'s paint")


class PlantGreenhouseScreen(PlantScreen):
    """The greenhouse (table 0x469220): its update 0x428810, its draw 0x4257A0 and its overlay
    0x428E70 (the tables, pots, plants, bugs, tools, what the hand holds, the bottom bar)."""
    TABLE, WHAT = 0x469220, "greenhouse"
    ROOTS = (0x428810, 0x4257A0, 0x428E70)

    def __init__(self, w: World) -> None:
        super().__init__(w)
        emu, scene = w.emu, self.scene
        emu.write32(self.state + 0x56C, 3)                             # a tool in the hand
        emu.write32(self.state + 0x63E58, 0x63)                        # no chemical selected
        emu.write8(scene + 8, 1)                                       # the mouse over the greenhouse
        emu.write32(scene + 0x0C, 0x150)
        # the screen's parts, as its constructor makes them (tests/test_chem_slots.py): the sprites,
        # the put-back's flight (+0x80, nothing flying), the chemical tray (+0x8C, over the state)
        for offset in (0x60, 0x6C, 0x70, 0x74, 0x78, 0x7C, 0x84, 0x88, 0x90):
            emu.write32(scene + offset, alloc_zero(w, 0x100))
        flight = alloc_zero(w, 0x40)
        emu.write32(flight + 4, 0xFFFFFFFF)
        emu.write32(scene + 0x80, flight)
        tray = alloc_zero(w, 8)
        emu.write32(tray, self.state)
        emu.write32(scene + 0x8C, tray)
        emu.write32(0x493BE8, tray)                                    # the tray's instance (0x416370)


class PlantNurseryScreen(PlantScreen):
    """The Nursery (table 0x469730): its update 0x437950, its draw 0x437BF0 and its overlay
    0x416730."""
    TABLE, WHAT = 0x469730, "Nursery"
    ROOTS = (0x437950, 0x437BF0, 0x416730)
    STATE_AT = 0xA3C

    def __init__(self, w: World) -> None:
        super().__init__(w)
        # the screen's parts its update and draw use (+0xA38-0xA74), each holding nothing (+4: -1)
        for offset in (0xA38, 0xA40, 0xA44, 0xA48, 0xA4C, 0xA54, 0xA58, 0xA5C, 0xA6C, 0xA70, 0xA74):
            part = alloc_zero(w, 0x100)
            w.emu.write32(part + 4, 0xFFFFFFFF)
            w.emu.write32(self.scene + offset, part)


SCREENS = {"fish": (FishTankScreen,), "plant": (PlantGreenhouseScreen, PlantNurseryScreen)}
TICKS = FRAMES = 3
SCREEN_SLOTS = (0x18, 0x1C, 0x20)          # the table entries a tick and a frame call: draw, overlay, update


# ------------------------------------------------------------------ the deliberate chains

class Chain(tuple):
    """A place two or more writers share on purpose: each later DLL checks the place holds the stock
    code or another companion's branch/pointer, keeps what was there and calls it in turn."""

    def __new__(cls, va: int, length: int, order: tuple[str, ...], reason: str):
        return super().__new__(cls, (va, length, order, reason))

    va = property(lambda self: self[0])
    length = property(lambda self: self[1])
    order = property(lambda self: self[2])        # the writers in the order they install
    reason = property(lambda self: self[3])

    def covers(self, byte: int) -> bool:
        return self.va <= byte < self.va + self.length


UNIVERSAL_SLOTS_PAYLOAD = "manifest:install_universal_slots_payload"   # either Unknown Chemical variant
CHAINS = {
    "fish": (
        Chain(0x41A663, 5, ("DS Store Items.dll", "Extra Tanks.dll", "Extra Supply Slots.dll"),
              "the save on quitting (call 0x419100): DS Store saves its state there; Extra Tanks puts the "
              "stock tanks back and writes its sidecar, then Extra Supply Slots writes its own, each calling "
              "what was there before (tank_sites.h / slot_sites.h SAVE_QUIT, store_sites.h SAVE_CALL_GAME)"),
        Chain(0x4424D0, 4, ("DS Store Items.dll", "Extra Tanks.dll", "Extra Supply Slots.dll"),
              "the game state's Load slot (the shared save/load table): each wraps the slot after checking "
              "it holds the stock Load or another companion's wrapper (SITE_SLOT_LOAD, SITE_STATE_LOAD)"),
        Chain(0x4424D4, 4, ("DS Store Items.dll", "Extra Tanks.dll", "Extra Supply Slots.dll"),
              "the game state's Save slot, as the Load slot (SITE_SLOT_SAVE, SITE_STATE_SAVE)"),
        Chain(0x421AAA, 5, ("DS Store Items.dll", "Extra Tanks.dll"),
              "the tank screen's activation update (call 0x41FE70): DS Store remembers the tank screen, "
              "Extra Tanks' TICK_SHOW then runs the update for the extra tanks too"),
        Chain(0x41AAC3, 5, ("Extra Tanks.dll", "Extra Supply Slots.dll"),
              "a new game (call 0x41A8F0): both empty their extra tanks / slots, then the stock new game"),
        Chain(0x421D43, 5, ("Multiple Ornaments.dll", "Extra Tanks.dll", "Extra Supply Slots.dll"),
              "a held item let go on the tank screen (call 0x421B20): an ornament copy dropped, a fish or "
              "supply dropped on an extra tank's or extra slot's button, then the stock release"),
        Chain(0x421FFB, 5, ("Extra Tanks.dll", "Extra Supply Slots.dll"),
              "the tank screen's mouse handler (call 0x421B80): the extra tanks' arrows and buttons, then "
              "the extra supply slots' arrows, then the stock handler"),
        Chain(0x42208E, 5, ("Extra Tanks.dll", "Extra Supply Slots.dll"),
              "the tank screen draw's tail jump to the buttons and panels (jmp 0x4216E0): each draws its "
              "own buttons and pages after the stock ones"),
        Chain(0x422062, 5, ("Multiple Ornaments.dll", "Extra Tanks.dll"),
              "the tank draw's equipment and ornaments (call 0x41EE60): Multiple Ornaments draws the "
              "ornament copies, Extra Tanks lends the extra tank's number for the draw"),
        Chain(0x43F593, 5, (UNIVERSAL_SLOTS_PAYLOAD, "DS Store Items.dll"),
              "the Universal supply slots payload's use gate (jmp 0x43F5DE, written by the manifest): "
              "DS Store sends Exotic Eggs and its chemicals to their slots there and jumps on to it"),
    ),
    "plant": (
        Chain(0x469224, 4, ("Greenhouse Counts.dll", "Extra Greenhouses.dll", "Extra Chemical Slots.dll"),
              "the greenhouse screen's mouse slot: the counts' button, the extra greenhouses' arrows, the "
              "extra chemical slots' tray, each wrapping the one before"),
        Chain(0x469244, 4, ("Extra Greenhouses.dll", "Extra Chemical Slots.dll"),
              "the greenhouse screen's activation slot: Extra Greenhouses, then Extra Chemical Slots"),
        Chain(0x46973C, 4, ("Optimize Prices.dll", "Extra Greenhouses.dll"),
              "the Nursery's command slot: the Optimize Prices button, then the extra nurseries"),
        Chain(0x469754, 4, ("Optimize Prices.dll", "Extra Greenhouses.dll"),
              "the Nursery's activation slot: the Optimize Prices button, then the extra nurseries"),
        Chain(0x46970C, 4, ("Extra Seed Boxes.dll", "Sort Seeds.dll"),
              "the Seed Storage screen's command slot: the extra seed boxes, then the Sort Seeds button"),
        Chain(0x469724, 4, ("Extra Seed Boxes.dll", "Sort Seeds.dll"),
              "the Seed Storage screen's activation slot: the extra seed boxes, then the Sort Seeds button"),
        Chain(0x44CA70, 5, ("Store Upgrades and Items.dll", "Translations.dll"),
              "the string lookup's head (0x44CA70): Store Upgrades and Items jumps to its own texts, then "
              "Translations.dll jumps to itself and calls that jump"),
    ),
}

# How each companion shows it installed: the line its log starts with, its own "installed" export;
# a DLL with neither (the counts, the Maximizable window) returns 1 from its FtfpStartup.
EVIDENCE = {
    "fish": {
        "DS Exclusive Fish.dll": ("DS Fish: installed (all sites)", "FtfpDsFishInstalled"),
        "DS Store Items.dll": ("DS Store: installed (all sites)", "FtfpDsStoreInstalled"),
        "Extra Tanks.dll": ("Extra Tanks: installed (all sites)", "FtfpExtraTanksInstalled"),
        "Extra Supply Slots.dll": ("Extra Supply Slots: installed (all sites)", "FtfpSupplySlotsInstalled"),
        "Multiple Ornaments.dll": ("Multiple Ornaments: installed (all sites)", "FtfpOrnamentsInstalled"),
        "Optimize Prices.dll": ("Optimize Prices: installed (Species Chart and Fish Store)",
                                "FtfpOptimizePricesInstalled"),
        "Tank Counts.dll": (None, None),
        "Maximizable Window.dll": (None, None),
        "Unicode Text.dll": ("Unicode Text: installed", None),
        "Translations.dll": ("\xef\xbb\xbfTranslations: installed (", "FtfpTranslationsInstalled"),
    },
    "plant": {
        "Unused Flowers.dll": ("New Flowers: installed (all sites)", "FtfpNewFlowersInstalled"),
        "Store Upgrades and Items.dll": ("Plant Upgrades: installed (all sites)", "FtfpPlantUpgradesInstalled"),
        "Extra Seed Boxes.dll": ("Seed Boxes: installed (all sites)", "FtfpSeedBoxesInstalled"),
        "Sort Seeds.dll": ("Sort Seeds: installed\r\n", None),
        "Optimize Prices.dll": ("Optimize Prices: installed\r\n", "FtfpOptimizePricesInstalled"),
        "Greenhouse Counts.dll": (None, None),
        "Extra Greenhouses.dll": ("Extra Greenhouses: installed (all sites)", "FtfpExtraGreenhousesInstalled"),
        "Extra Chemical Slots.dll": ("Extra Chemical Slots: installed (all sites)", "FtfpChemSlotsInstalled"),
        "Unicode Text.dll": ("Unicode Text: installed", None),
        "Translations.dll": ("\xef\xbb\xbfTranslations: installed (", "FtfpTranslationsInstalled"),
    },
}


def chain_at(game: str, byte: int) -> Chain | None:
    return next((c for c in CHAINS[game] if c.covers(byte)), None)


def manifest_party(patch_id: str) -> str:
    return UNIVERSAL_SLOTS_PAYLOAD if patch_id.startswith(UNIVERSAL_SLOTS_PAYLOAD[9:]) else f"manifest:{patch_id}"


def clashes(game: str, writers: dict[str, set[int]], patches: list[dict]) -> list[str]:
    """Every byte two writers share that no chain explains: `writers` maps each DLL to the bytes it
    writes (declared or actually written); the configuration's manifest patches are writers too."""
    found: dict[tuple, list[int]] = {}
    everyone = dict(writers)
    for va, end, patch_id in manifest_ranges(game, patches):
        everyone.setdefault(manifest_party(patch_id), set()).update(range(va, end))
    names = sorted(everyone)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            if first.startswith("manifest:") and second.startswith("manifest:"):
                continue
            for byte in sorted(everyone[first] & everyone[second]):
                chain = chain_at(game, byte)
                if chain is None or first not in chain.order or second not in chain.order:
                    found.setdefault((first, second), []).append(byte)
    return [f"{a} and {b} both write 0x{v[0]:X} ({len(v)} bytes)" for (a, b), v in found.items()]


def declared_bytes(game: str, dlls: list[str]) -> dict[str, set[int]]:
    out = {}
    for dll in dlls:
        out[dll] = set()
        for va, (length, _name) in declared_sites(PROJECTS[game][dll]).items():
            if dll == "Translations.dll" and va not in TRANSLATIONS_SITES[game]:
                continue
            out[dll].update(range(va, va + length))
    return out


# ------------------------------------------------------------------ the tests

class DeclaredSitesTests(unittest.TestCase):
    """The sites every DLL declares (its generated headers and its source) never overlap another
    DLL's or a manifest patch of the same configuration, except the deliberate chains. Data only:
    this runs without Unicorn and without the games."""

    def test_every_configuration(self) -> None:
        for game in ("fish", "plant"):
            m = manifest(game)
            for name, enabled in configurations(game).items():
                with self.subTest(game=game, configuration=name):
                    patches = PATCHERS[game].active_patch_records(m, enabled)
                    self.assertEqual(clashes(game, declared_bytes(game, shipped_dlls(game, enabled)), patches), [])

    def test_every_dll_has_its_sites_and_evidence(self) -> None:
        for game in ("fish", "plant"):
            dlls = set(shipped_dlls(game, {s["id"] for s in manifest(game)["settings"]}))
            self.assertEqual(dlls, set(PROJECTS[game]), game)
            self.assertEqual(dlls, set(EVIDENCE[game]), game)
            for dll in dlls:
                self.assertTrue(declared_sites(PROJECTS[game][dll]), dll)

    def test_the_chains_are_real(self) -> None:
        """Each chain names DLLs that declare a site there (and the manifest patch, when one does)."""
        for game in ("fish", "plant"):
            every = {s["id"] for s in manifest(game)["settings"]}
            declared = declared_bytes(game, shipped_dlls(game, every))
            patches = manifest_ranges(game, manifest(game)["patches"])
            for chain in CHAINS[game]:
                with self.subTest(game=game, chain=hex(chain.va)):
                    self.assertGreaterEqual(len(chain.order), 2)
                    for party in chain.order:
                        if party.startswith("manifest:"):
                            self.assertTrue(any(manifest_party(pid) == party and va <= chain.va < end
                                                for va, end, pid in patches), party)
                        else:
                            self.assertTrue(set(range(chain.va, chain.va + chain.length)) <= declared[party], party)


RESULTS: dict[tuple[str, str], dict] = {}        # what each configuration did, for a reader of the run


class EveryPatch:
    """One test per configuration: build, load, installed, no clashes, it runs."""

    game = ""

    def check(self, name: str) -> None:
        game = self.game
        enabled = configurations(game)[name]
        b = build(game, enabled)
        result = RESULTS[(game, name)] = {"dlls": b.dlls}

        # Build: the patcher's executable is the manifest's pin.
        self.assertTrue(b.pin, "the manifest pins this configuration")
        self.assertEqual(b.sha256, b.pin, "the built executable is its pin")
        self.assertEqual(set(p.name for p in b.dll_folder.glob("*.dll")) if b.dll_folder.is_dir() else set(),
                         set(b.dlls), "the built folder holds exactly the configuration's DLLs")

        # Load: the startup loader, from the C runtime's call of WinMain to WinMain.
        w = World(b)
        if b.dlls:
            w.run_loader()
        else:
            self.assertFalse(fish_patcher.needs_startup_loader(manifest(game), enabled))
        self.assertEqual(w.messages, [], "no DLL showed a message")
        self.assertEqual(sorted(w.load_order), sorted(b.dlls), "every DLL the configuration ships is loaded")
        self.assertEqual(w.top_level, list(b.profile.dll_names) if b.dlls else [],
                         "the loader starts its DLLs in the profile's order")
        for dll in b.dlls:
            self.assertEqual(w.dll_mains.get(dll), w.companions[dll].base, f"{dll}: its DllMain ran")

        # Installed: every DLL says so; none refuses.
        installed = []
        for dll in b.dlls:
            line, export = EVIDENCE[game][dll]
            if line is not None:
                log = w.log(dll)
                self.assertIsNotNone(log, f"{dll} wrote its log")
                self.assertTrue(log.startswith(line), f"{dll}: {log!r}")
            if export is not None:
                self.assertEqual(w.call(w.companions[dll].exports[export], what=export), 1, f"{dll}: {export}")
            if line is None and export is None:
                firsts = [r for d, x, r in w.startups if d == dll and x == "FtfpStartup"]
                self.assertTrue(firsts, f"{dll}: its FtfpStartup ran")
                self.assertEqual(firsts[0], 1, f"{dll}: FtfpStartup returned {firsts[0]}")
            installed.append(dll)
        result["installed"] = installed

        # No clashes: what each DLL wrote while it started, and what it declares.
        writes = w.writes["startup"]
        exe = range(0x400000, 0x400000 + w.exe_size)
        in_exe = {dll: {a for a in bytes_ if a in exe} for dll, bytes_ in writes.items()}
        self.assertEqual(clashes(game, in_exe, b.active_patches), [], "bytes the DLLs wrote")
        self.assertEqual(clashes(game, declared_bytes(game, b.dlls), b.active_patches), [], "declared sites")
        declared = declared_bytes(game, b.dlls)
        for dll, bytes_ in in_exe.items():
            undeclared = sorted(bytes_ - declared[dll])
            self.assertEqual([hex(a) for a in undeclared[:8]], [], f"{dll} wrote outside its declared sites")
        for dll, bytes_ in writes.items():
            outside = {a for a in bytes_ if a not in exe}
            if dll == "Translations.dll":                 # pointers to texts, in the companions' own images
                images = [range(m.base, m.base + m.size) for m in w.modules if m.companion and m.name != dll]
                self.assertEqual([hex(a) for a in sorted(outside) if not any(a in r for r in images)][:8], [],
                                 "Translations.dll writes only into companion images outside the game")
                continue
            if outside:                                   # only the window's: SDL.dll's ScreenToClient slot
                sdl = next(m for m in w.modules if m.name.lower() == "sdl.dll")
                slot = sdl.slots["ScreenToClient"]
                self.assertEqual((dll, outside), ("Maximizable Window.dll", set(range(slot, slot + 4))))
        for byte, order in w.order.items():
            if len(order) > 1:
                chain = chain_at(game, byte)
                self.assertIsNotNone(chain, f"0x{byte:X}: {order}")
                self.assertEqual(order, [p for p in chain.order if p in order],
                                 f"0x{byte:X}: installed in the chain's order")
        result["chains"] = sorted({hex(chain_at(game, a).va) for a, o in w.order.items() if len(o) > 1})

        # Runs: ticks and frames of the main screens, every DLL hook on their path included.
        w.phase = "run"
        w.ran = [0] * 16
        ran = result["ran"] = {}
        for screen_class in SCREENS[game]:
            screen = screen_class(w)
            for tick in range(TICKS):
                with self.subTest(screen=screen_class.__name__, tick=tick):
                    screen.tick()
            for frame in range(FRAMES):
                with self.subTest(screen=screen_class.__name__, frame=frame):
                    screen.frame()
            wrappers = {dll for slot in SCREEN_SLOTS for dll, bytes_ in in_exe.items()
                        if screen.TABLE + slot in bytes_}
            for dll in sorted(wrappers):
                self.assertGreater(w.instructions_run(dll), 0,
                                   f"{dll} wraps the {screen_class.__name__}'s table and ran")
        for dll in b.dlls:
            ran[dll] = w.instructions_run(dll)
        result["run"] = f"{len(SCREENS[game])} screen(s) x ({TICKS} ticks + {FRAMES} frames): returned normally"


def _test_name(name: str) -> str:
    return "test_" + re.sub(r"\W+", "_", name.lower()).strip("_")


def _add_tests(cls, game: str) -> None:
    for name in configurations(game):
        def test(self, name=name) -> None:
            self.check(name)
        test.__name__ = _test_name(name)
        test.__doc__ = f"{game}: {name}"
        setattr(cls, test.__name__, test)


@_needs("fish")
class FishEveryPatchTests(EveryPatch, unittest.TestCase):
    game = "fish"


@_needs("plant")
class PlantEveryPatchTests(EveryPatch, unittest.TestCase):
    game = "plant"


_add_tests(FishEveryPatchTests, "fish")
_add_tests(PlantEveryPatchTests, "plant")


if __name__ == "__main__":
    unittest.main()
