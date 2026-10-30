"""Tank and greenhouse counts (both games): the setting, its pins, and the
counts DLLs' own code run in Unicorn against the vanilla executables.

The emulated tests rebuild "Tank Counts.dll" and "Greenhouse Counts.dll"
from their sources (each must come out byte-for-byte the committed one), map
each beside its game, build tank and greenhouse states in memory and call the
hooked draw exactly as the game does (the tank screen's call at 0x422013, the
greenhouse vtable's slot at 0x469238). The game's text, font and background
functions are Python hooks that record what is drawn.
"""

from __future__ import annotations

from argparse import Namespace
import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import plant_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

SETTING = "tank_greenhouse_counts"
FISH_DLL = ROOT / "assets" / "fish_tycoon_counts" / "Tank Counts.dll"
PLANT_DLL = ROOT / "assets" / "plant_tycoon_counts" / "Greenhouse Counts.dll"
FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
DEFAULTS = Namespace(enable=None, disable=None, disable_all=False)


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


def exe_bytes(exe: Path, va: int, length: int) -> bytes:
    data = exe.read_bytes()
    base, _size, sections, _imports = E.pe_image(data)
    rva = va - base
    raw = next(raw + rva - start for start, raw, size in sections if start <= rva < start + size)
    return data[raw:raw + length]


# ------------------------------------------------------------------ manifests

class ManifestTests(unittest.TestCase):
    GAMES = {"fish": ("Tank Counts.dll", "Fish Tycoon Fix Patcher DLLs", ds_fish_loader.FISH_COUNTS),
             "plant": ("Greenhouse Counts.dll", "Plant Tycoon Fix Patcher DLLs", ds_fish_loader.PLANT_COUNTS)}

    def test_on_by_default_in_the_plain_copy_of_both_games(self) -> None:
        for game, patcher in (("fish", fish_patcher), ("plant", plant_patcher)):
            manifest = combined.load_manifest(game)
            setting = combined.patch_settings(game)[SETTING]
            self.assertEqual(setting["name"], "Tank and greenhouse counts")
            self.assertTrue(setting["default"])
            self.assertFalse(setting.get("separate_output", False))
            self.assertFalse(setting.get("requires_settings"))
            defaults = patcher.enabled_settings(manifest, DEFAULTS)
            self.assertIn(SETTING, defaults)
            self.assertIn("Display only", setting["description"])
        folder, exe = fish_patcher.output_names(combined.load_manifest("fish"),
                                                fish_patcher.enabled_settings(combined.load_manifest("fish"), DEFAULTS),
                                                Path("Fish Tycoon - Modded"), "Fish Tycoon - Modded.exe")
        self.assertEqual((folder.name, exe), ("Fish Tycoon - Modded", "Fish Tycoon - Modded.exe"))

    def test_companion_dll_is_pinned_and_present(self) -> None:
        for game, (dll, folder, _profile) in self.GAMES.items():
            companion = combined.patch_settings(game)[SETTING]["companion"]
            self.assertTrue(companion["startup_loader"])
            [entry] = companion["files"]
            self.assertEqual(entry["destination"], f"{folder}/{dll}")
            data = (ROOT / companion["source"] / entry["path"]).read_bytes()
            self.assertEqual(len(data), entry["size"])
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"])
            self.assertIn(b"FtfpStartup", data)

    def test_the_loader_loads_the_counts_dll_first(self) -> None:
        self.assertIs(ds_fish_loader.fish_profile({SETTING}), ds_fish_loader.FISH_COUNTS)
        self.assertIs(ds_fish_loader.fish_profile({SETTING, "ds_fish", "maximizable_window"}), ds_fish_loader.FISH_COUNTS)
        self.assertIs(ds_fish_loader.fish_profile({"ds_fish"}), ds_fish_loader.FISH)
        self.assertIs(ds_fish_loader.fish_profile({"maximizable_window"}), ds_fish_loader.FISH_WINDOW)
        self.assertIs(ds_fish_loader.plant_profile({SETTING, "new_flowers"}), ds_fish_loader.PLANT_COUNTS)
        self.assertIs(ds_fish_loader.plant_profile({"new_flowers"}), ds_fish_loader.PLANT)
        self.assertIs(ds_fish_loader.plant_profile({"sort_seeds"}), ds_fish_loader.PLANT_SORT)
        for game, (dll, _folder, _profile) in self.GAMES.items():
            details = combined.setting_companion_details(game, SETTING)
            self.assertTrue(any(dll in d.note for d in details), game)
        # the counts DLLs load the DLL the loader would have loaded
        self.assertIn("DS Exclusive Fish.dll".encode("utf-16-le"), FISH_DLL.read_bytes())
        self.assertIn("Maximizable Window.dll".encode("utf-16-le"), FISH_DLL.read_bytes())
        self.assertIn("Unused Flowers.dll".encode("utf-16-le"), PLANT_DLL.read_bytes())
        self.assertIn("Sort Seeds.dll".encode("utf-16-le"), PLANT_DLL.read_bytes())

    def test_every_combination_is_pinned(self) -> None:
        for game in self.GAMES:
            pins = combined.load_manifest(game)["patched_sha256_by_settings"]
            without = [key for key in pins if SETTING not in key.split(",")]
            with_it = [key for key in pins if SETTING in key.split(",")]
            self.assertEqual(len(with_it), len(without) + ("" not in pins), game)
            for key in with_it:
                self.assertRegex(pins[key], r"^[0-9A-F]{64}$")
                if {"extra_greenhouses", "extra_nurseries"} & set(key.split(",")):
                    continue        # Extra Greenhouses.dll starts the counts' DLL itself: the same loader
                self.assertNotEqual(pins[key], pins.get(",".join(sorted(set(key.split(",")) - {SETTING}))), key)

    @unittest.skipUnless(FISH_EXE is not None and FISH_EXE.is_file() and PLANT_EXE.is_file(),
                         "needs the vanilla executables")
    def test_pins_match_the_vanilla_executables(self) -> None:
        cases = (("fish", fish_patcher, FISH_EXE, ds_fish_loader.fish_profile, ({"ds_fish"}, {"maximizable_window"}, set())),
                 ("plant", plant_patcher, PLANT_EXE, ds_fish_loader.plant_profile, ({"new_flowers"}, {"sort_seeds"}, set())))
        for game, patcher, exe, profile, extras in cases:
            manifest = combined.load_manifest(game)
            vanilla = exe.read_bytes()
            pins = manifest["patched_sha256_by_settings"]
            defaults = patcher.enabled_settings(manifest, DEFAULTS)
            for extra in extras:
                for enabled in (defaults | extra, {SETTING} | extra):
                    patched, _ = patcher.apply_patch_bytes(vanilla, patcher.active_patch_records(manifest, enabled))
                    patched, _ = ds_fish_loader.append_startup_loader(patched, profile(enabled))
                    self.assertIn(profile(enabled).tail, patched)
                    key = patcher.settings_key(enabled, manifest) if game == "plant" else patcher.settings_key(enabled)
                    self.assertEqual(hashlib.sha256(patched).hexdigest().upper(), pins[key], (game, key))


class ThresholdTests(unittest.TestCase):
    """The DLLs' constants are the vanilla executables' own."""

    @unittest.skipUnless(E is not None and FISH_EXE is not None and FISH_EXE.is_file(), "needs the vanilla Fish Tycoon.exe")
    def test_fish_stages_are_the_view_builders(self) -> None:
        self.assertEqual(exe_bytes(FISH_EXE, 0x413F0B, 5), b"\xBA\x01\x00\x00\x00")       # mov edx, 1 (shown from 1)
        self.assertEqual(exe_bytes(FISH_EXE, 0x413F1C, 3), b"\x83\xF8\x06")               # cmp eax, 6 (teen)
        self.assertEqual(exe_bytes(FISH_EXE, 0x413F65, 3), b"\x83\xF8\x14")               # cmp eax, 0x14 (adult)
        self.assertEqual(exe_bytes(FISH_EXE, 0x4206B1, 3), b"\x83\xF9\x15")               # the 21-slot bound
        self.assertEqual(exe_bytes(FISH_EXE, 0x422013, 5), b"\xE8\x28\xB1\xFF\xFF")       # call 0x41D140

    @unittest.skipUnless(E is not None and PLANT_EXE is not None and PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon.exe")
    def test_plant_stages_are_the_countdowns(self) -> None:
        self.assertEqual(struct.unpack("<f", exe_bytes(PLANT_EXE, 0x4691D8, 4))[0], 21.0)
        self.assertEqual(struct.unpack("<f", exe_bytes(PLANT_EXE, 0x4677E8, 4))[0], 24.0)
        self.assertEqual(exe_bytes(PLANT_EXE, 0x469238, 4), struct.pack("<I", 0x4257A0))


# ----------------------------------------------------------- shared fixture

class _DllFixture:
    PROJECT = ""
    COMMITTED: Path
    EXE: Path
    NEXT = ("", "")

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(cls.PROJECT, cls.COMMITTED, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def setUp(self) -> None:
        emu = self.emu = E.Emulator(self.EXE, self.dll, self.symbols)
        emu.uc.mem_map(0, 0x1000)             # fs:[0] for __try's SEH frame (FS base is 0 here)
        self.calls: list[tuple] = []
        self.present: set[str] = set()
        self.next_startup = emu.thunk()
        emu.hook(self.next_startup, self._log("next FtfpStartup", 0, 1))
        emu.hook_import("VirtualProtect", self._virtual_protect, 16)
        emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
        emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
        emu.hook_import("GetModuleFileNameW", self._module_file_name, 12)
        emu.hook_import("GetFileAttributesW", self._file_attributes, 4)
        emu.hook_import("LoadLibraryW", self._load_library, 4)
        emu.hook_import("GetProcAddress", self._get_proc, 8)
        emu.hook_import("GetModuleHandleW", self._module_handle, 4)
        emu.hook_import("VirtualQuery", self._virtual_query, 12)
        self.text_draws: list[tuple] = []
        # Other companions already loaded: {module name: handle} and {(handle, export): address}.
        self.modules: dict[str, int] = {}
        self.exports: dict[tuple[int, str], int] = {}

    OTHER_MODULE = 0x6B000000                 # a loaded companion DLL's image (VirtualQuery's AllocationBase)

    def _module_handle(self, e) -> int:
        if e.arg(0) == 0:
            return 0x400000
        return self.modules.get(e.wstring(e.arg(0)), 0)

    def _virtual_query(self, e) -> int:
        address, info = e.arg(0), e.arg(1)
        base = self.OTHER_MODULE if self.OTHER_MODULE <= address < self.OTHER_MODULE + 0x100000 else 0x400000
        e.uc.mem_write(info, struct.pack("<IIIIIII", address & ~0xFFF, base, 0x20, 0x1000, 0x1000, 0x20, 0x1000000))
        return 28

    def export(self, module: str, name: str, handler, stack: int) -> int:
        """A companion `module` loaded with the export `name` (a thunk running handler)."""
        handle = self.modules.setdefault(module, 0x6C000000 + 0x10000 * len(self.modules))
        address = self.emu.thunk()
        self.emu.hook(address, handler, stack)
        self.exports[(handle, name)] = address
        return address

    FOLDER = "C:\\Games\\Game\\Patcher DLLs\\"

    def _log(self, name: str, args: int, result: int):
        def handler(e) -> int:
            self.calls.append((name, *[e.arg(i) for i in range(args)]))
            return result
        return handler

    def _virtual_protect(self, e) -> int:
        self.calls.append(("VirtualProtect", e.arg(0), e.arg(1)))
        e.write32(e.arg(3), 0x02)
        return 1

    def _module_file_name(self, e) -> int:
        path = self.FOLDER + self.COMMITTED.name
        e.uc.mem_write(e.arg(1), path.encode("utf-16-le") + b"\0\0")
        return len(path)

    def _file_attributes(self, e) -> int:
        name = e.wstring(e.arg(0))
        return 0x20 if name.startswith(self.FOLDER) and name[len(self.FOLDER):] in self.present else 0xFFFFFFFF

    def _load_library(self, e) -> int:
        self.calls.append(("LoadLibraryW", e.wstring(e.arg(0))))
        return 0x6A000000

    def _get_proc(self, e) -> int:
        name = e.cstring(e.arg(1)).decode()
        self.calls.append(("GetProcAddress", e.arg(0), name))
        if (e.arg(0), name) in self.exports:
            return self.exports[(e.arg(0), name)]
        return self.next_startup if name == "FtfpStartup" else 0

    def named(self, name: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == name]

    def startup(self) -> int:
        return self.emu.call(self.symbols["_FtfpStartup@0"])

    def in_dll(self, address: int) -> bool:
        base, size = E.pe_image(self.dll.read_bytes())[:2]
        return base <= address < base + size

    # ------------------------------------------------------------ loading
    def test_loads_the_dll_the_loader_would_have(self) -> None:
        first, second = self.NEXT
        for present, loaded in (({first, second}, first), ({first}, first), ({second}, second), (set(), None)):
            self.setUp()
            self.present = present
            self.startup()
            libraries = [call[1] for call in self.named("LoadLibraryW")]
            if loaded is None:
                self.assertEqual(libraries, [])
                self.assertEqual(self.named("next FtfpStartup"), [])
            else:
                self.assertEqual(libraries, [self.FOLDER + loaded], present)
                self.assertEqual(len(self.named("next FtfpStartup")), 1)

    def test_text_fits_the_game_font(self) -> None:
        drawable = self.font_glyphs()
        texts = self.every_text()
        self.assertTrue(texts)
        for text in texts:
            self.assertLessEqual(set(text), drawable, text)


# --------------------------------------------------------------- Fish Tycoon

STATE_SIZE = 0x1E600
FISH_BASE, TANK_STRIDE, SLOT_STRIDE = 0x390, 0x51EC, 0x288
ORN_BASE, ORN_STRIDE = 0x5208, 0x2C
FONT_MANAGER, FONT_GET, DRAW_TEXT, BACKGROUND = 0x418210, 0x4181F0, 0x408B80, 0x41D140
GRAPHICS, MANAGER, FONT = 0x00C0FFEE, 0x0F0F0000, 0x0F0F1000


@_needs(FISH_EXE)
class FishCountsTests(_DllFixture, unittest.TestCase):
    PROJECT = "ftfp_tank_counts"
    COMMITTED = FISH_DLL
    EXE = FISH_EXE
    NEXT = ("DS Exclusive Fish.dll", "Maximizable Window.dll")

    def setUp(self) -> None:
        super().setUp()
        emu = self.emu
        self.state = emu.alloc(STATE_SIZE)
        emu.uc.mem_write(self.state, bytes(STATE_SIZE))
        self.impl = emu.alloc(0x100)
        emu.uc.mem_write(self.impl, bytes(0x100))
        emu.write32(self.impl + 0x34, self.state)
        emu.write32(self.impl + 0x54, GRAPHICS)
        emu.hook(BACKGROUND, self._log("background", 0, 0))
        emu.hook(FONT_MANAGER, lambda e: MANAGER)
        emu.hook(FONT_GET, self._font_get, 4)
        emu.hook(DRAW_TEXT, self._draw_text, 0x14)
        # DS Store Items keeps each tank's 5 animals in records of its own (FtfpStoreAnimals).
        self.animals = emu.alloc(3 * 5 * SLOT_STRIDE)
        emu.uc.mem_write(self.animals, bytes(3 * 5 * SLOT_STRIDE))
        self.export("DS Store Items.dll", "FtfpStoreAnimals", self._store_animals, 8)

    def _store_animals(self, e) -> int:
        tank = e.arg(1)
        return self.animals + tank * 5 * SLOT_STRIDE if e.arg(0) == self.state and 0 <= tank <= 2 else 0

    def animal(self, tank: int, k: int, fin: int, mark: int = 0x41435446) -> None:
        """DS Store Items' animal k (0-4) of a tank: a body-22 record marked "FTCA"."""
        at = self.animals + (tank * 5 + k) * SLOT_STRIDE
        self.emu.write32(at + 0x00, 1000)
        self.emu.write32(at + 0x0C, 21)
        self.emu.write32(at + 0x14, mark)
        self.emu.write32(at + 0x3C, 100)
        self.emu.write32(at + 0x4C, 22)
        self.emu.write32(at + 0x50, fin)

    def _font_get(self, e) -> int:
        self.calls.append(("font", e.uc.reg_read(E.X.UC_X86_REG_ECX), e.arg(0)))
        return FONT

    def _draw_text(self, e) -> int:
        draw = (e.cstring(e.arg(0)).decode("latin-1"), e.arg(1), e.arg(2), e.arg(3), e.arg(4),
                e.uc.reg_read(E.X.UC_X86_REG_ECX))
        self.text_draws.append(draw)
        self.calls.append(("text",) + draw)
        return 0

    # ------------------------------------------------------------ state
    def fish(self, tank: int, slot: int, age: int, health: int = 100, body: int = 3, fin: int = 5,
             clock: int = 1000, mark: int = 0) -> None:
        at = self.state + FISH_BASE + tank * TANK_STRIDE + slot * SLOT_STRIDE
        self.emu.write32(at + 0x00, clock)
        self.emu.write32(at + 0x0C, age)
        self.emu.write32(at + 0x14, mark)
        self.emu.write32(at + 0x3C, health)
        self.emu.write32(at + 0x4C, body)
        self.emu.write32(at + 0x50, fin)

    def rock(self, tank: int, k: int, sprite: int) -> None:
        at = self.state + ORN_BASE + tank * TANK_STRIDE + k * ORN_STRIDE
        self.emu.write8(at, 1)
        self.emu.write32(at + 0x24, sprite)

    def lines(self, tank: int = 0) -> list[str]:
        """Install, then make the tank screen's own background call; the white lines drawn."""
        self.emu.write32(self.state + 0x384, tank)
        if self.emu.read32(0x422014) == 0xFFFFB128:          # still the stock call 0x41D140
            self.assertEqual(self.startup(), 1)
        self.calls.clear()
        self.text_draws.clear()
        rel = self.emu.read32(0x422014, signed=True)
        self.emu.call(0x422018 + rel, ecx=self.impl)
        return [draw[0] for draw in self.text_draws if draw[3] == 0xFFFFFFFF]

    # ------------------------------------------------------------ install
    def test_install_routes_the_background_call_here(self) -> None:
        self.assertEqual(self.startup(), 1)
        site = bytes(self.emu.uc.mem_read(0x422013, 5))
        self.assertEqual(site[0], 0xE8)
        target = 0x422018 + struct.unpack("<i", site[1:])[0]
        self.assertEqual(target, self.symbols["@on_background@8"])
        self.assertTrue(self.in_dll(target))
        self.assertEqual(self.named("VirtualProtect")[0][1:], (0x422013, 5))

    def test_changed_code_installs_nothing(self) -> None:
        self.emu.uc.mem_write(0x422013, b"\xE8\x00\x00\x00\x00")
        self.assertEqual(self.startup(), 0)
        self.assertEqual(bytes(self.emu.uc.mem_read(0x422013, 5)), b"\xE8\x00\x00\x00\x00")
        self.assertEqual(self.named("VirtualProtect"), [])

    # ------------------------------------------------------------ counts
    def test_stages_dead_creatures_and_hidden_records(self) -> None:
        for slot, age in enumerate((1, 5, 6, 19, 20, 100)):
            self.fish(0, slot, age)
        self.fish(0, 6, 0)                                  # age 0: not shown, not counted
        self.fish(0, 7, 10, clock=0)                        # an empty slot
        self.fish(0, 8, 30, health=0)                       # dead adult
        self.fish(0, 9, 2, health=-3)                       # dead baby
        self.fish(0, 10, 21, body=22, fin=22)               # the stock Golden Seahorse in a fish slot
        self.animal(0, 0, fin=30)                           # DS Store Items' puffer
        self.fish(0, 26, 21, body=22, fin=30, mark=0x41435446)   # an earlier build's record: not shown, not counted
        self.fish(0, 27, 21, body=22, fin=31)               # not marked: a leftover, not an animal
        self.rock(0, 2, 229)                                # the eel at home in its rock
        self.rock(0, 3, 228)                                # an empty rock
        self.assertEqual(self.lines(), [
            "Fish: 6 of 21 (2 adults, 2 teens, 2 babies)  Dead: 2",
            "Creatures: Golden Seahorse, Magic Pufferfish, Moray Eel",
            "Isolation tank: 0 of 1",
        ])

    def test_singular_words_and_several_of_a_creature(self) -> None:
        self.fish(0, 0, 25)
        self.fish(0, 1, 7)
        self.fish(0, 2, 3)
        self.fish(0, 3, 21, body=22, fin=22)
        self.animal(0, 0, fin=22)
        self.animal(0, 3, fin=32)
        self.animal(1, 1, fin=31)                           # another tank's
        self.assertEqual(self.lines()[:2], ["Fish: 3 of 21 (1 adult, 1 teen, 1 baby)",
                                            "Creatures: Golden Seahorse x2, Moray Eel"])

    def test_an_empty_tank_has_no_creature_line(self) -> None:
        self.assertEqual(self.lines(), ["Fish: 0 of 21", "Isolation tank: 0 of 1"])

    def test_only_the_tank_on_screen_counts(self) -> None:
        self.fish(0, 0, 30)
        for slot in range(3):
            self.fish(1, slot, 2)
        self.fish(2, 0, 9)
        self.assertEqual(self.lines(0)[0], "Fish: 1 of 21 (1 adult)")
        self.assertEqual(self.lines(1)[0], "Fish: 3 of 21 (3 babies)")
        self.assertEqual(self.lines(2)[0], "Fish: 1 of 21 (1 teen)")

    def test_bigger_tanks_room_is_30(self) -> None:
        for slot in range(23):
            self.fish(0, slot, 40)
        self.assertEqual(self.lines()[0], "Fish: 21 of 21 (21 adults)")       # slots 21-22 are not the tank's
        self.emu.write8(0x4206B3, 0x1E)                                       # the Bigger tanks bound
        self.assertEqual(self.lines()[0], "Fish: 23 of 30 (23 adults)")
        for slot in range(23, 30):
            self.fish(0, slot, 40)
        self.fish(0, 30, 40)                                                   # record 30: never a fish
        self.assertEqual(self.lines()[0], "Fish: 30 of 30 (30 adults)")

    def test_without_ds_store_items_no_animals_are_asked_for(self) -> None:
        self.exports.clear()
        self.modules.clear()
        self.fish(0, 0, 25)
        self.assertEqual(self.lines(), ["Fish: 1 of 21 (1 adult)", "Isolation tank: 0 of 1"])

    def test_with_extra_tanks_the_lines_go_under_the_name_and_for_sale_button(self) -> None:
        self.export("Extra Tanks.dll", "FtfpExtraTanksInstalled", lambda e: 1, 0)
        self.fish(0, 0, 25)
        self.lines()
        self.assertEqual([t[3] for t in self.named("text") if t[4] == 0xFFFFFFFF], [136, 156])

    def test_chains_another_companions_background_call(self) -> None:
        """Extra Tanks.dll (loaded first) already wraps 0x422013: the counts call its wrapper."""
        wrapper = self.OTHER_MODULE + 0x1230
        self.emu.uc.mem_map(self.OTHER_MODULE, 0x10000)
        self.emu.hook(wrapper, self._log("extra tanks' background", 0, 0))
        self.emu.uc.mem_write(0x422013, b"\xE8" + struct.pack("<i", wrapper - 0x422018))
        self.assertEqual(self.startup(), 1)
        self.fish(0, 0, 25)
        lines = self.lines()
        self.assertEqual(self.calls[0], ("extra tanks' background",))
        self.assertEqual(self.named("background"), [])
        self.assertEqual(lines[0], "Fish: 1 of 21 (1 adult)")

    def test_the_isolation_tank(self) -> None:
        self.fish(3, 0, 33)
        self.fish(3, 1, 33)                                 # not the isolation tank's place
        self.assertEqual(self.lines()[-1], "Isolation tank: 1 of 1 (1 adult)")
        self.fish(3, 0, 4)
        self.assertEqual(self.lines()[-1], "Isolation tank: 1 of 1 (1 baby)")
        self.fish(3, 0, 33, health=0)
        self.assertEqual(self.lines()[-1], "Isolation tank: 0 of 1  Dead: 1")

    def test_german(self) -> None:
        language = self.emu.alloc(4)
        self.emu.write32(language, 1)
        self.emu.write32(0x45B314, language)
        self.fish(0, 0, 25)
        self.fish(0, 1, 30)
        self.fish(0, 2, 7)
        self.fish(0, 3, 1)
        self.fish(0, 4, 50, health=0)
        self.animal(0, 4, fin=32)
        self.fish(3, 0, 20)
        self.assertEqual(self.lines(), [
            "Fische: 4 von 21 (2 ausgewachsen, 1 halbw\xfcchsig, 1 jung)  Tot: 1",
            "Tiere: Mur\xe4ne",
            "Zuchtaquarium: 1 von 1 (1 ausgewachsen)",
        ])

    def test_drawn_over_the_background_in_the_game_font_with_a_shadow(self) -> None:
        self.fish(0, 0, 25)
        self.lines()
        self.assertEqual(self.calls[0], ("background",))
        self.assertEqual(self.named("font"), [("font", MANAGER, 0)])          # paddington_tt_18
        texts = self.named("text")
        self.assertEqual([(t[2], t[3], t[4], t[5], t[6]) for t in texts], [
            (13, 63, 0xFF000000, FONT, GRAPHICS), (12, 62, 0xFFFFFFFF, FONT, GRAPHICS),
            (13, 83, 0xFF000000, FONT, GRAPHICS), (12, 82, 0xFFFFFFFF, FONT, GRAPHICS),
        ])

    def test_the_screensaver_shows_no_counts(self) -> None:
        self.fish(0, 0, 25)
        self.emu.write8(self.state + 0x1E4F9, 1)
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.named("background"), [("background",)])

    def test_nothing_is_written_to_the_state(self) -> None:
        for slot, age in enumerate((1, 8, 30)):
            self.fish(0, slot, age)
        self.animal(0, 2, fin=30)
        self.fish(3, 0, 20)
        self.rock(0, 0, 229)
        self.emu.write32(self.state + 0x384, 0)
        before = bytes(self.emu.uc.mem_read(self.state, STATE_SIZE))
        self.lines()
        self.assertEqual(bytes(self.emu.uc.mem_read(self.state, STATE_SIZE)), before)

    # ------------------------------------------------------------ glyphs
    def font_glyphs(self) -> set[str]:
        from test_store_extras import fish_fonts
        return fish_fonts()["paddington_tt_18"]

    def every_text(self) -> list[str]:
        out = []
        for german in (False, True):
            self.setUp()
            if german:
                language = self.emu.alloc(4)
                self.emu.write32(language, 1)
                self.emu.write32(0x45B314, language)
            for slot, age in enumerate((1, 2, 6, 7, 20, 21)):
                self.fish(0, slot, age)
            self.fish(0, 6, 5, health=0)
            for k, fin in enumerate((22, 30, 31, 32, 22)):
                self.animal(0, k, fin=fin)
            self.fish(3, 0, 25)
            out += self.lines()
            self.fish(0, 0, 1, clock=0)
            self.fish(0, 2, 1, clock=0)
            self.fish(0, 4, 1, clock=0)
            out += self.lines()
        return out


# -------------------------------------------------------------- Plant Tycoon

PLANT_STATE = 0x2188 + 15 * 0x5600 + 0x100
GREENHOUSE_DRAW, PLANT_GRAPHICS, PLANT_TEXT = 0x4257A0, 0x407A90, 0x4092A0
DRAW_SLOT = 0x469238


@_needs(PLANT_EXE)
class PlantCountsTests(_DllFixture, unittest.TestCase):
    PROJECT = "ftfp_greenhouse_counts"
    COMMITTED = PLANT_DLL
    EXE = PLANT_EXE
    NEXT = ("Unused Flowers.dll", "Sort Seeds.dll")

    def setUp(self) -> None:
        super().setUp()
        emu = self.emu
        self.state = emu.alloc(PLANT_STATE)
        emu.uc.mem_write(self.state, bytes(PLANT_STATE))
        self.scene = emu.alloc(0x200)
        emu.uc.mem_write(self.scene, bytes(0x200))
        emu.write32(self.scene + 0x68, self.state)
        emu.hook(GREENHOUSE_DRAW, self._log("background", 0, 0))
        emu.hook(PLANT_GRAPHICS, lambda e: GRAPHICS)
        emu.hook(PLANT_TEXT, self._draw_text, 0x14)

    def _draw_text(self, e) -> int:
        draw = (e.cstring(e.arg(0)).decode("latin-1"), e.arg(1), e.arg(2), e.arg(3), e.arg(4),
                e.uc.reg_read(E.X.UC_X86_REG_ECX))
        self.text_draws.append(draw)
        self.calls.append(("text",) + draw)
        return 0

    def pot(self, k: int, age: float, health: int = 90, planted: int = 1) -> None:
        at = self.state + 0x2188 + k * 0x5600
        self.emu.uc.mem_write(at + 0x10, struct.pack("<f", age))
        self.emu.write32(at + 0x24, health)
        self.emu.write32(at + 0x4C, planted)

    def lines(self) -> list[str]:
        """Install, then call the greenhouse vtable's draw slot, as the game's paint does."""
        if self.emu.read32(DRAW_SLOT) == GREENHOUSE_DRAW:
            self.assertEqual(self.startup(), 1)
        self.calls.clear()
        self.text_draws.clear()
        self.emu.call(self.emu.read32(DRAW_SLOT), ecx=self.scene)
        return [draw[0] for draw in self.text_draws if draw[3] == 0xFFFFFFFF]

    def test_install_wraps_the_draw_slot(self) -> None:
        self.assertEqual(self.startup(), 1)
        self.assertEqual(self.emu.read32(DRAW_SLOT), self.symbols["@on_draw@8"])
        self.assertEqual(self.named("VirtualProtect")[0][1:], (DRAW_SLOT, 4))

    def test_a_changed_slot_installs_nothing(self) -> None:
        self.emu.write32(DRAW_SLOT, 0x12345678)
        self.assertEqual(self.startup(), 0)
        self.assertEqual(self.emu.read32(DRAW_SLOT), 0x12345678)
        self.assertEqual(self.named("VirtualProtect"), [])

    def test_stages_by_the_countdowns(self) -> None:
        for k, age in enumerate((0.0, 20.99, 21.0, 23.9, 24.0, 500.0)):
            self.pot(k, age)
        self.pot(6, 30.0, health=0)                          # dead: fills its pot until trashed
        self.pot(7, 30.0, health=-5)
        self.pot(8, 30.0, health=100, planted=0)             # no plant (a stale record)
        self.assertEqual(self.lines(), ["Plants: 6 of 15 (2 mature, 2 with buds, 2 seedlings)  Dead: 2"])

    def test_singular_and_empty(self) -> None:
        self.assertEqual(self.lines(), ["Plants: 0 of 15"])
        self.pot(0, 3.0)
        self.pot(14, 22.0)
        self.pot(7, 25.0)
        self.assertEqual(self.lines(), ["Plants: 3 of 15 (1 mature, 1 with buds, 1 seedling)"])

    def test_a_full_greenhouse(self) -> None:
        for k in range(15):
            self.pot(k, 30.0)
        self.assertEqual(self.lines(), ["Plants: 15 of 15 (15 mature)"])

    def test_drawn_over_the_background_in_the_game_font_with_a_shadow(self) -> None:
        self.pot(0, 25.0)
        self.lines()
        self.assertEqual(self.calls[0], ("background",))
        self.assertEqual([(t[2], t[3], t[4], t[5], t[6]) for t in self.named("text")], [
            (237, 5, 0xFF000000, 0, GRAPHICS), (236, 4, 0xFFFFFFFF, 0, GRAPHICS)])

    def test_under_the_extra_greenhouses_arrows_once_one_is_bought(self) -> None:
        """5 extra greenhouses draws gold arrows at the top (y 10-59) once one is bought: the line
        goes under them; with none bought (or the setting off: -1) it stays at the top."""
        owned = [0]
        self.export("Extra Greenhouses.dll", "FtfpExtraGreenhousesOwned", lambda e: owned[0], 0)
        self.pot(0, 25.0)
        for count, y in ((0, 4), (-1, 4), (1, 62), (5, 62)):
            owned[0] = count
            self.lines()
            self.assertEqual([t[3] for t in self.named("text")], [y + 1, y], count)

    def test_nothing_is_written_to_the_state(self) -> None:
        for k, age in enumerate((1.0, 22.0, 30.0)):
            self.pot(k, age)
        self.pot(3, 30.0, health=0)
        before = bytes(self.emu.uc.mem_read(self.state, PLANT_STATE))
        self.lines()
        self.assertEqual(bytes(self.emu.uc.mem_read(self.state, PLANT_STATE)), before)

    def font_glyphs(self) -> set[str]:
        from test_store_extras import plant_font
        return plant_font()

    def every_text(self) -> list[str]:
        out = []
        for ages in ((1.0, 2.0, 22.0, 23.0, 25.0, 26.0), (1.0, 22.0, 25.0)):
            self.setUp()
            for k, age in enumerate(ages):
                self.pot(k, age)
            self.pot(14, 30.0, health=0)
            out += self.lines()
        return out


if __name__ == "__main__":
    unittest.main()
