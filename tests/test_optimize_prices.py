"""Optimize Prices (both games): the button's price maths, its DLLs and its setting.

* The maths: native/common/price_math.h is compiled (native/common/price_math_harness.c)
  and asked for the price of many species and shops; every answer must be the Python
  model's (src/breeding_fish.py and src/breeding_plant.py, shop_best_price).
* The DLLs run in Unicorn against the vanilla executables (tests/store_emulator.py):
  the two vtable slots go in together or not at all; a click answered Yes sets exactly
  the discovered species to the model's price and changes no other byte; No changes
  nothing.
* The setting: on by default in both games, in the plain "- Modded" copy, shipping the
  DLL and its button, loaded by the startup loader after any other companion; the
  pinned executables are what the patcher builds.
"""

from __future__ import annotations

from argparse import Namespace
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_fish as BF  # noqa: E402
import breeding_plant as BP  # noqa: E402
import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import plant_patcher  # noqa: E402

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

SETTING = "optimize_prices"
FISH_MANIFEST = ROOT / "data" / "fish_manifest.json"
PLANT_MANIFEST = ROOT / "data" / "plant_manifest.json"
FISH_DLL = ROOT / "assets" / "fish_tycoon_optimize_prices" / "Optimize Prices.dll"
PLANT_DLL = ROOT / "assets" / "plant_tycoon_optimize_prices" / "Optimize Prices.dll"
VANILLA = E.VANILLA if E else Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
FISH_EXE = VANILLA / "Fish Tycoon" / "Fish Tycoon.exe"
PLANT_EXE = VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"


def _toolchain() -> bool:
    return E is not None and E.toolchain_ready()


def fish_queries() -> list[tuple[int, int, bool, int, int]]:
    """(base, ornaments, seahorse, advertising, tank): every base price a species can have
    (stock and DS, at Advertising levels 1-3) and 1-60, over every shop, plus random ones."""
    bases = set(range(1, 61))
    for b in BF.PC_GENES + BF.DS_GENES:
        for f in BF.PC_GENES + BF.DS_GENES:
            for level in (1, 2, 3):
                bases.add(BF.advertised(BF.base_price(b, f), level))
    shops = [(o, s, a, t) for o in range(7) for s in (False, True) for a in (1, 2, 3) for t in (21, 26)]
    rng = random.Random(1717)
    out = [(b, *shop) for b in sorted(bases) for shop in rng.sample(shops, 8)]
    out += [(b, *shop) for b in (4, 26, 70, 190, 239) for shop in shops]
    out += [(rng.randint(1, 400), rng.randint(0, 6), rng.random() < 0.5, rng.randint(0, 3), rng.choice((21, 26)))
            for _ in range(200)]
    return out


def plant_queries() -> list[tuple[int, bool, int]]:
    """(V, Golden Berries, S): every species value (with Unused Flowers) and 1-40, over scores
    from nothing to everything, plus random ones."""
    values = set(range(1, 41))
    for foliage in BP.STOCK_FOLIAGES:
        for flower in list(BP.STOCK_FLOWERS) + list(BP.NEW_FLOWERS):
            values.add(BP.value((foliage, flower)))
    rng = random.Random(2424)
    out = [(v, gb, s) for v in sorted(values) for gb in (False, True) for s in rng.sample(range(0, 79), 2)]
    out += [(v, gb, s) for v in (7, 44, 95, 130, 250) for gb in (False, True) for s in range(0, 79)]
    out += [(rng.randint(1, 320), rng.random() < 0.5, rng.randint(0, 90)) for _ in range(150)]
    return out


@unittest.skipUnless(_toolchain(), "needs the pinned MSVC toolset")
class PriceMathAgreesWithTheModel(unittest.TestCase):
    """The C port gives the Python model's price for every query."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        common = ROOT / "native" / "common"
        command = [
            str(E.MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/O2", "/MT", "/W4", "/WX", "/GS-",
            f"/Fo{out}\\", f"/Fe{out / 'harness.exe'}",
            "/I", str(E.MSVC / "include"),
            "/I", str(E.SDK / "Include" / E.SDK_VERSION / "ucrt"),
            "/I", str(E.SDK / "Include" / E.SDK_VERSION / "um"),
            "/I", str(E.SDK / "Include" / E.SDK_VERSION / "shared"),
            str(common / "price_math_harness.c"),
            "/link", f"/LIBPATH:{E.MSVC / 'lib' / 'x86'}",
            f"/LIBPATH:{E.SDK / 'Lib' / E.SDK_VERSION / 'um' / 'x86'}",
            f"/LIBPATH:{E.SDK / 'Lib' / E.SDK_VERSION / 'ucrt' / 'x86'}",
        ]
        result = subprocess.run(command, cwd=out, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        cls.harness = out / "harness.exe"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def ask(self, lines: list[str]) -> list[int]:
        result = subprocess.run([str(self.harness)], input="\n".join(lines) + "\n", capture_output=True,
                                text=True, check=True)
        return [int(x) for x in result.stdout.split()]

    def test_fish_prices_agree(self) -> None:
        queries = fish_queries()
        got = self.ask([f"F {b} {o} {int(s)} {a} {t}" for b, o, s, a, t in queries])
        self.assertEqual(len(got), len(queries))
        for (b, o, s, a, t), price in zip(queries, got):
            self.assertEqual(price, BF.shop_best_price(b, o, s, a, t), (b, o, s, a, t))
        self.assertGreater(len(queries), 1000)

    def test_plant_prices_agree(self) -> None:
        queries = plant_queries()
        got = self.ask([f"P {v} {int(gb)} {s}" for v, gb, s in queries])
        self.assertEqual(len(got), len(queries))
        for (v, gb, s), price in zip(queries, got):
            self.assertEqual(price, BP.shop_best_price(v, gb, s), (v, gb, s))
        self.assertGreater(len(queries), 1000)


class ModelTests(unittest.TestCase):
    """The shop functions are the Breeding Guide's own "max" columns."""

    def test_fish_max_column_is_the_full_shop(self) -> None:
        model = BF.FishModel(extras=False)
        for key in ((0, 0), (7, 7), (10, 9), (20, 16)):
            base = BF.advertised(BF.base_price(*key), 3)
            self.assertEqual(model.prices(key, "max").best_per_day, BF.shop_best_price(base, 6, True, 3))

    def test_plant_scores_are_the_guides(self) -> None:
        everything = BP.visitor_score((True,) * 15, True, 5, True)
        self.assertEqual(everything, BP.ORNAMENT_POINTS + 2 * BP.SALE_SPOTS + 4 + 2 * 5 + 4)
        self.assertEqual(BP.visitor_limit(everything), 55)
        self.assertEqual(BP.visitor_score((False,) * 15, False, 0, False), 2 * BP.SALE_SPOTS)
        # the Golden Berries let a higher price sell
        self.assertGreater(BP.shop_best_price(130, True, everything), BP.shop_best_price(130, False, everything))

    @unittest.skipUnless(PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon.exe")
    def test_ornament_points_are_the_jump_table(self) -> None:
        exe = PLANT_EXE.read_bytes()
        points = []
        for i in range(15):                               # 0x440020: 0x43FF31 adds 1, 0x43FF36 adds 4
            target = int.from_bytes(exe[0x40020 + 4 * i: 0x40024 + 4 * i], "little")
            points.append({0x0043FF31: 1, 0x0043FF36: 4}[target])
        self.assertEqual(tuple(points), BP.ORNAMENT_POINTS_BY_ID)
        self.assertEqual(sum(BP.ORNAMENT_POINTS_BY_ID), BP.ORNAMENT_POINTS)


# ------------------------------------------------------------------ the setting

class SettingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifests = {game: json.loads(path.read_text(encoding="utf-8"))
                          for game, path in (("fish", FISH_MANIFEST), ("plant", PLANT_MANIFEST))}

    def test_on_by_default_in_the_plain_copy(self) -> None:
        for game, manifest in self.manifests.items():
            setting = {s["id"]: s for s in manifest["settings"]}[SETTING]
            self.assertEqual(setting["name"], "Optimize Prices button", game)
            self.assertTrue(setting["default"], game)
            self.assertEqual(setting["category"], "main", game)
            self.assertFalse(setting.get("separate_output", False), game)
            self.assertFalse(setting.get("requires_settings"), game)
            engine = fish_patcher if game == "fish" else plant_patcher
            defaults = engine.enabled_settings(manifest, Namespace(enable=None, disable=None, disable_all=False))
            self.assertIn(SETTING, defaults, game)

    def test_it_ships_the_dll_and_the_button(self) -> None:
        expected = {"fish": ("Fish Tycoon Fix Patcher DLLs/Optimize Prices.dll", "Images/OptimizePricesButton.png"),
                    "plant": ("Plant Tycoon Fix Patcher DLLs/Optimize Prices.dll", "Images/optimize_prices_button.png")}
        for game, manifest in self.manifests.items():
            companion = {s["id"]: s for s in manifest["settings"]}[SETTING]["companion"]
            self.assertTrue(companion["startup_loader"])
            self.assertEqual({f["destination"] for f in companion["files"]}, set(expected[game]))
            for item in companion["files"]:
                data = (ROOT / companion["source"] / item["path"]).read_bytes()
                self.assertEqual(len(data), item["size"])
                self.assertEqual(hashlib.sha256(data).hexdigest().upper(), item["sha256"].upper())

    def test_the_patchers_species_dlls_are_pinned(self) -> None:
        for game, owner, dll in (("fish", "ds_fish", "DS Exclusive Fish.dll"), ("plant", "new_flowers", "Unused Flowers.dll")):
            companion = {s["id"]: s for s in self.manifests[game]["settings"]}[owner]["companion"]
            entry = next(f for f in companion["files"] if f["path"] == dll)
            data = (ROOT / companion["source"] / dll).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest().upper(), entry["sha256"].upper())
            export = b"FtfpDsFishEntry" if owner == "ds_fish" else b"FtfpNewFlowersSpecies"
            self.assertIn(export, data)

    def test_every_combination_with_it_is_pinned(self) -> None:
        for game, manifest in self.manifests.items():
            pins = manifest["patched_sha256_by_settings"]
            without = [k for k in pins if SETTING not in k.split(",")]
            for key in without:
                enabled = {s for s in key.split(",") if s} | {SETTING}
                engine = fish_patcher if game == "fish" else plant_patcher
                new_key = engine.settings_key(enabled, manifest) if game == "plant" else engine.settings_key(enabled)
                self.assertIn(new_key, pins, (game, key))
            self.assertIn(SETTING, pins, game)

    def test_the_loader_loads_it_last(self) -> None:
        fish = ds_fish_loader.fish_profile
        self.assertEqual(fish({SETTING}).dll_names, ("Optimize Prices.dll",))
        self.assertEqual(fish({SETTING, "maximizable_window"}).dll_names,
                         ("Maximizable Window.dll", "Optimize Prices.dll"))
        self.assertEqual(fish({SETTING, "maximizable_window", "ds_fish"}).dll_names,
                         ("DS Exclusive Fish.dll", "Optimize Prices.dll"))
        self.assertIs(fish({"maximizable_window"}), ds_fish_loader.FISH_WINDOW)
        plant = ds_fish_loader.plant_profile
        self.assertEqual(plant({SETTING}).dll_names, ("Optimize Prices.dll",))
        self.assertEqual(plant({SETTING, "sort_seeds"}).dll_names, ("Sort Seeds.dll", "Optimize Prices.dll"))
        self.assertEqual(plant({SETTING, "new_flowers", "sort_seeds"}).dll_names,
                         ("Unused Flowers.dll", "Optimize Prices.dll"))
        self.assertIs(plant({"sort_seeds"}), ds_fish_loader.PLANT_SORT)

    def test_one_dll_loaders_are_unchanged(self) -> None:
        """Adding a second DLL to the loader leaves every one-DLL loader byte for byte as it was:
        the pins without this setting did not move."""
        block = ds_fish_loader._block(0x00460000, ds_fish_loader.FISH)
        self.assertNotIn(b"\x8B\xEF", block[block.index(b"\x83\xC7\x02"):][:5])      # no `mov ebp, edi`
        two = ds_fish_loader._block(0x00460000, ds_fish_loader.fish_profile({SETTING, "ds_fish"}))
        self.assertIn("Optimize Prices.dll".encode("utf-16-le"), two)
        self.assertIn("DS Exclusive Fish.dll".encode("utf-16-le"), two)

    @unittest.skipUnless(FISH_EXE.is_file() and PLANT_EXE.is_file(), "needs the vanilla executables")
    def test_pins_are_what_the_patcher_builds(self) -> None:
        cases = (("fish", FISH_EXE, fish_patcher, ds_fish_loader.fish_profile),
                 ("plant", PLANT_EXE, plant_patcher, ds_fish_loader.plant_profile))
        for game, exe, engine, profile in cases:
            manifest = self.manifests[game]
            vanilla = exe.read_bytes()
            defaults = engine.enabled_settings(manifest, Namespace(enable=None, disable=None, disable_all=False))
            extra = {"fish": ("ds_fish", "bigger_tanks"), "plant": ("new_flowers", "sort_seeds")}[game]
            for enabled in ({SETTING}, defaults, defaults | {extra[0]}, defaults | set(extra)):
                patched, _ = engine.apply_patch_bytes(vanilla, engine.active_patch_records(manifest, enabled))
                patched, _ = ds_fish_loader.append_startup_loader(patched, profile(enabled))
                key = engine.settings_key(enabled, manifest) if game == "plant" else engine.settings_key(enabled)
                self.assertEqual(hashlib.sha256(patched).hexdigest().upper(),
                                 manifest["patched_sha256_by_settings"][key], (game, key))


@unittest.skipUnless(E is not None and FISH_EXE.is_file(), "needs Unicorn and the vanilla Fish Tycoon.exe")
class TwoDllLoaderTests(unittest.TestCase):
    """The startup loader's own code, run: it loads its DLLs in order, each by its full path,
    calls each one's FtfpStartup, goes on past a missing one, and reaches WinMain with every
    register as the C runtime left it."""

    def run_loader(self, profile, missing: set[str]) -> tuple[list[str], list[str], dict]:
        patched, _ = ds_fish_loader.append_startup_loader(FISH_EXE.read_bytes(), profile)
        with tempfile.TemporaryDirectory() as raw:
            exe = Path(raw) / "Fish Tycoon - Modded.exe"
            exe.write_bytes(patched)
            emu = E.Emulator(exe, None, {})
        call = profile.winmain_call_va
        stub = call + 5 + int.from_bytes(bytes(emu.uc.mem_read(call + 1, 4)), "little", signed=True)
        loaded, started, handles = [], [], {}
        folder = "C:\\Games\\Fish Tycoon - Modded\\"
        thunks = {name: emu.thunk() for name in ("GetModuleHandleA", "GetProcAddress", "GetModuleFileNameW",
                                                 "LoadLibraryExW")}
        emu.write32(profile.get_module_handle_a_iat, thunks["GetModuleHandleA"])
        emu.write32(profile.get_proc_address_iat, thunks["GetProcAddress"])

        def file_name(e) -> int:
            text = folder + "Fish Tycoon - Modded.exe"
            e.uc.mem_write(e.arg(1), text.encode("utf-16-le") + b"\0\0")
            return len(text)

        def load(e) -> int:
            path = e.wstring(e.arg(0))
            loaded.append(path)
            if path.rsplit("\\", 1)[-1] in missing:
                return 0
            handles[path] = 0x71000000 + 0x10000 * len(handles)
            return handles[path]

        def proc(e) -> int:
            name = e.cstring(e.arg(1)).decode("ascii")
            if name == "FtfpStartup":
                path = next(p for p, h in handles.items() if h == e.arg(0))
                start = e.thunk()
                e.hook(start, lambda _e, p=path: started.append(p) or 1, 0)
                return start
            return thunks[name]
        emu.hook(thunks["GetModuleHandleA"], lambda e: 0x76000000, 4)
        emu.hook(thunks["GetProcAddress"], proc, 8)
        emu.hook(thunks["GetModuleFileNameW"], file_name, 12)
        emu.hook(thunks["LoadLibraryExW"], load, 12)
        registers = {r: 0x1000 * (i + 1) for i, r in enumerate((E.X.UC_X86_REG_EBX, E.X.UC_X86_REG_EBP,
                                                                 E.X.UC_X86_REG_EDI, E.X.UC_X86_REG_EDX))}
        for reg, value in registers.items():
            emu.uc.reg_write(reg, value)
        emu.run_until(stub, profile.winmain_va, esi=0x5150)
        after = {reg: emu.uc.reg_read(reg) for reg in registers}
        self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_ESP), E.STACK + E.STACK_SIZE - 0x1000)
        self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_ESI), 0x5150)
        self.assertEqual(after, registers)
        return [p.removeprefix(folder) for p in loaded], [p.removeprefix(folder) for p in started], handles

    def test_both_dlls_load_in_order(self) -> None:
        loaded, started, _ = self.run_loader(ds_fish_loader.fish_profile({SETTING, "maximizable_window"}), set())
        expected = ["Fish Tycoon Fix Patcher DLLs\\Maximizable Window.dll", "Fish Tycoon Fix Patcher DLLs\\Optimize Prices.dll"]
        self.assertEqual(loaded, expected)
        self.assertEqual(started, expected)

    def test_a_missing_first_dll_still_loads_the_second(self) -> None:
        loaded, started, _ = self.run_loader(ds_fish_loader.fish_profile({SETTING, "ds_fish"}), {"DS Exclusive Fish.dll"})
        self.assertEqual(loaded, ["Fish Tycoon Fix Patcher DLLs\\DS Exclusive Fish.dll",
                                  "Fish Tycoon Fix Patcher DLLs\\Optimize Prices.dll"])
        self.assertEqual(started, ["Fish Tycoon Fix Patcher DLLs\\Optimize Prices.dll"])

    def test_one_dll_alone(self) -> None:
        loaded, started, _ = self.run_loader(ds_fish_loader.fish_profile({SETTING}), set())
        self.assertEqual(loaded, ["Fish Tycoon Fix Patcher DLLs\\Optimize Prices.dll"])
        self.assertEqual(started, loaded)


# ------------------------------------------------------------------ the DLLs in the game's code

def _emulated(exe: Path):
    ready = _toolchain() and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


def _hook_windows(emu, modules: dict[str, dict[str, int]]) -> list[int]:
    """VirtualProtect works (and is logged), no install log is written, and GetModuleHandleW /
    GetProcAddress find only `modules` ({DLL name: {export: address}})."""
    protects: list[int] = []
    handles = {name: 0x70000000 + 0x10000 * i for i, name in enumerate(modules)}

    def protect(e) -> int:
        protects.append(e.arg(0))
        e.write32(e.arg(3), 0x02)
        return 1

    def module(e) -> int:
        return handles.get(e.wstring(e.arg(0)), 0)

    def proc(e) -> int:
        name = e.cstring(e.arg(1)).decode("ascii")
        for dll, handle in handles.items():
            if handle == e.arg(0):
                return modules[dll].get(name, 0)
        return 0
    emu.hook_import("VirtualProtect", protect, 16)
    emu.hook_import("GetModuleFileNameW", lambda e: 0, 12)
    emu.hook_import("GetModuleHandleW", module, 4)
    emu.hook_import("GetProcAddress", proc, 8)
    emu.uc.mem_map(0, 0x1000)                 # fs:[0] for __try's SEH frame (FS base is 0 here)
    return protects


# Fish Tycoon
SPECIES_VT_COMMAND, SPECIES_VT_ACTIVATE = 0x00443C9C, 0x00443CB4
SPECIES_COMMAND, SPECIES_ACTIVATE = 0x00425B00, 0x00401C90
F_SPECIES, F_STRIDE, F_ENTRY = 0x14B40, 31, 40
F_STRINGS = 0x00457340


@_emulated(FISH_EXE)
class FishButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_fish_prices", FISH_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def game(self, ds: dict | None = None, answer: int = 0):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        modules = {}
        if ds is not None:
            installed, entry = emu.thunk(), emu.thunk()
            emu.hook(installed, lambda e: 1, 0)
            emu.hook(entry, lambda e: ds.get((e.arg(1), e.arg(2)), 0), 12)
            modules["DS Exclusive Fish.dll"] = {"FtfpDsFishInstalled": installed, "FtfpDsFishEntry": entry}
        emu.protects = _hook_windows(emu, modules)
        emu.dialogs = []

        def dialog(e) -> int:
            at = next(F_STRINGS + 12 * i for i in range(0xF9) if e.read32(F_STRINGS + 12 * i) == e.arg(0))
            e.dialogs.append((e.arg(0), e.arg(1), e.cstring(e.read32(at + 4)).decode("latin-1"),
                              e.cstring(e.read32(at + 8)).decode("latin-1")))
            return e.uc.reg_read(E.X.UC_X86_REG_ECX)
        emu.hook(0x004221A0, dialog, 8)                                  # DIALOG_INIT(string id, yes / no)
        emu.hook(0x00401D00, lambda e: answer, 8)                        # DIALOG_RUN: 0 = Yes
        emu.hook(0x00422440, emu.record("free"), 0)
        return emu

    def install(self, emu) -> int:
        return emu.call(emu.sym("_FtfpStartup@0"))

    def shop(self, emu, entries: dict, ornaments=(1, 0, 1, 0, 0, 1), seahorse=1, advertising=2):
        state, impl, scene = emu.alloc(0x20000), emu.alloc(0x40), emu.alloc(0x40)
        emu.write32(scene + 8, impl)
        emu.write32(impl + 4, state)
        for k, owned in enumerate(ornaments):
            emu.write32(state + 0x1B8 + 0x14 * k, owned)
        emu.write32(state + 0x154, seahorse)
        emu.write32(state + 0x26C, advertising)
        for (body, fin), (price, base) in entries.items():
            at = state + F_SPECIES + (body * F_STRIDE + fin) * F_ENTRY
            emu.uc.mem_write(at, b"Fish\0")
            emu.write32(at + 0x20, price)
            emu.write32(at + 0x24, base)
        return state, scene

    def click(self, emu, scene) -> int:
        return emu.call(emu.read32(SPECIES_VT_COMMAND), 8, 7, ecx=scene)

    def test_both_slots_go_in_together(self) -> None:
        emu = self.game()
        self.assertEqual(self.install(emu), 1)
        for va, stock in ((SPECIES_VT_COMMAND, SPECIES_COMMAND), (SPECIES_VT_ACTIVATE, SPECIES_ACTIVATE)):
            self.assertNotEqual(emu.read32(va), stock)
            self.assertGreaterEqual(emu.read32(va), 0x10000000)
        self.assertEqual(emu.call(emu.sym("_FtfpOptimizePricesInstalled@0")), 1)

    def test_a_changed_slot_means_neither_goes_in(self) -> None:
        for changed in (SPECIES_VT_COMMAND, SPECIES_VT_ACTIVATE):
            emu = self.game()
            emu.write32(changed, 0x00401234)
            before = bytes(emu.uc.mem_read(0x00443C90, 0x28))
            self.assertEqual(self.install(emu), 0)
            self.assertEqual(bytes(emu.uc.mem_read(0x00443C90, 0x28)), before)
            self.assertEqual(emu.protects, [])

    def test_a_refused_second_write_puts_the_first_back(self) -> None:
        emu = self.game()

        def protect(e) -> int:
            if e.arg(0) == SPECIES_VT_ACTIVATE:
                return 0
            e.write32(e.arg(3), 0x02)
            return 1
        emu.hook_import("VirtualProtect", protect, 16)
        self.assertEqual(self.install(emu), 0)
        self.assertEqual(emu.read32(SPECIES_VT_COMMAND), SPECIES_COMMAND)
        self.assertEqual(emu.read32(SPECIES_VT_ACTIVATE), SPECIES_ACTIVATE)

    def test_opening_the_chart_adds_the_button_once(self) -> None:
        emu = self.game()
        self.install(emu)
        emu.hook(0x0042A793, lambda e: e.alloc(0x14), 0)                 # operator new
        buttons = []
        emu.hook(0x00401B10, lambda e: (buttons.append([e.arg(i) for i in range(6)]),
                                        e.uc.reg_read(E.X.UC_X86_REG_ECX))[1], 24)
        emu.hook(0x00425120, lambda e: 0x5000, 0)                         # the sound manager
        emu.hook(0x004251A0, emu.record("sound", 0x6000, args=1), 4)
        emu.hook(0x004015E0, emu.record("button sound", args=2), 8)
        emu.hook(0x0040A9E0, emu.record("add", args=1), 4)
        _, scene = self.shop(emu, {})
        for on in (1, 0, 1):
            emu.call(emu.read32(SPECIES_VT_ACTIVATE), on, ecx=scene)
        self.assertEqual(len(buttons), 1)
        bid, image, x, y, handler, zero = buttons[0]
        self.assertEqual((bid, emu.cstring(image), x, y, handler, zero),
                         (7, b"OptimizePricesButton.png", 524, 546, scene, 0))
        self.assertIn(("sound", (1,)), emu.calls)
        self.assertEqual(sum(1 for c in emu.calls if c[0] == "add"), 1)

    def entries(self) -> tuple[dict, set]:
        rng = random.Random(55)
        entries, found = {}, set()
        for body in BF.PC_GENES:
            for fin in BF.PC_GENES:
                base = BF.advertised(BF.base_price(body, fin), 2)
                discovered = rng.random() < 0.3 or (body, fin) in ((0, 0), (7, 7), (20, 16))
                entries[(body, fin)] = (rng.randint(1, 300) if discovered else -1, base)
                if discovered:
                    found.add((body, fin))
        return entries, found

    def test_yes_sets_exactly_the_discovered_species(self) -> None:
        emu = self.game()
        self.install(emu)
        entries, found = self.entries()
        state, scene = self.shop(emu, entries)
        strings = bytes(emu.uc.mem_read(F_STRINGS, 12 * 0xF9))
        before = bytearray(emu.uc.mem_read(state, 0x20000))
        self.assertEqual(self.click(emu, scene) & 0xFF, 1)
        after = bytes(emu.uc.mem_read(state, 0x20000))
        expected = bytearray(before)
        for key in found:
            price = BF.shop_best_price(entries[key][1], 3, True, 2, 21)
            at = F_SPECIES + (key[0] * F_STRIDE + key[1]) * F_ENTRY + 0x20
            expected[at:at + 4] = price.to_bytes(4, "little")
        self.assertEqual(after, bytes(expected))
        self.assertEqual(bytes(emu.uc.mem_read(F_STRINGS, 12 * 0xF9)), strings)      # the texts are put back
        (q_id, q_yes_no, q_en, q_de), (m_id, m_yes_no, m_en, m_de) = emu.dialogs
        self.assertEqual((q_yes_no, m_yes_no), (1, 0))
        self.assertEqual(q_en, "Set every discovered species\nto its best price per day?")
        self.assertEqual(m_en, f"{len(found)} prices set.")
        self.assertEqual(m_de, f"{len(found)} Preise gesetzt.")

    def test_no_changes_nothing(self) -> None:
        emu = self.game(answer=1)
        self.install(emu)
        entries, _ = self.entries()
        state, scene = self.shop(emu, entries)
        before = bytes(emu.uc.mem_read(state, 0x20000))
        strings = bytes(emu.uc.mem_read(F_STRINGS, 12 * 0xF9))
        self.click(emu, scene)
        self.assertEqual(bytes(emu.uc.mem_read(state, 0x20000)), before)
        self.assertEqual(bytes(emu.uc.mem_read(F_STRINGS, 12 * 0xF9)), strings)
        self.assertEqual(len(emu.dialogs), 1)

    def test_bigger_tanks_and_ds_species(self) -> None:
        ds_rows = {}
        emu = self.game(ds=ds_rows)
        self.install(emu)
        emu.write8(0x00419C74, 0x1A)                                       # Bigger tanks' slot bound
        entries = {(3, 25): (40, BF.base_price(3, 25)), (5, 5): (-1, 24), (2, 2): (9, 15)}
        state, scene = self.shop(emu, entries, ornaments=(0,) * 6, seahorse=0, advertising=1)
        rows = emu.alloc(0x100)
        ds_rows[(26, 4)] = rows                                            # a DS body: its row is the DLL's
        ds_rows[(27, 9)] = rows + 0x40                                     # undiscovered
        emu.uc.mem_write(rows, b"DS\0")
        emu.write32(rows + 0x20, 77)
        emu.write32(rows + 0x24, BF.base_price(26, 4))
        emu.uc.mem_write(rows + 0x40, b"DS\0")
        emu.write32(rows + 0x60, -1)
        emu.write32(rows + 0x64, BF.base_price(27, 9))
        self.click(emu, scene)
        price = lambda base: BF.shop_best_price(base, 0, False, 1, 26)       # noqa: E731
        cell = lambda b, f: state + F_SPECIES + (b * F_STRIDE + f) * F_ENTRY + 0x20  # noqa: E731
        self.assertEqual(emu.read32(cell(3, 25)), price(BF.base_price(3, 25)))
        self.assertEqual(emu.read32(cell(2, 2)), price(15))
        self.assertEqual(emu.read32(cell(5, 5), signed=True), -1)
        self.assertEqual(emu.read32(rows + 0x20), price(BF.base_price(26, 4)))
        self.assertEqual(emu.read32(rows + 0x60, signed=True), -1)
        self.assertEqual(emu.dialogs[-1][2], "3 prices set.")


# Plant Tycoon
SELL_VT_COMMAND, SELL_VT_ACTIVATE = 0x0046973C, 0x00469754
SELL_COMMAND, SELL_ACTIVATE = 0x004351C0, 0x004360D0
P_STRING_ENTRIES = 0x00493CC0
P_STATE_SIZE = 0x60000


def p_price_cell(foliage: int, flower: int) -> int:
    return ((foliage + 0x37) * 26 + flower) * 4


def p_value_cell(foliage: int, flower: int) -> int:
    return ((foliage + 0x1D) * 26 + flower) * 4


@_emulated(PLANT_EXE)
class PlantButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_prices", PLANT_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def game(self, flowers: dict | None = None, answer: int = 0):
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        modules = {}
        if flowers is not None:
            installed, species = emu.thunk(), emu.thunk()
            emu.hook(installed, lambda e: 1, 0)

            def lookup(e) -> int:
                found = flowers.get((e.arg(0), e.arg(1)))
                if found is None:
                    return -1
                v, cell, discovered = found
                e.write32(e.arg(2), v)
                e.write32(e.arg(3), cell)
                return discovered
            emu.hook(species, lookup, 16)
            modules["Unused Flowers.dll"] = {"FtfpNewFlowersInstalled": installed, "FtfpNewFlowersSpecies": species}
        emu.protects = _hook_windows(emu, modules)
        emu.entries = {}
        for sid, text in ((0x10, "Yes"), (0x11, "No"), (0x12, "OK"), (0x13, "Cancel"),
                          (0x3E, "Are you sure you want to restart the current game?")):
            entry = emu.alloc(0x10)
            emu.write32(entry, sid)
            emu.write32(entry + 8, emu.text(text))
            emu.write32(P_STRING_ENTRIES + 4 * sid, entry)
            emu.entries[sid] = entry
        emu.dialogs = []

        def shown(e, sid) -> str:
            entry = e.entries[sid]
            return e.cstring(e.read32(entry + 0xC) or e.read32(entry + 8)).decode("latin-1")

        def build(e) -> int:
            e.dialogs.append(((e.arg(0), e.arg(1), e.arg(2), e.arg(3), e.arg(4)),
                              shown(e, 0x3E), shown(e, 0x12), shown(e, 0x13)))
            return e.uc.reg_read(E.X.UC_X86_REG_ECX)
        emu.hook(0x0042AB50, build, 20)
        emu.hook(0x00401C90, lambda e: answer, 8)                         # run: 0 = the first button
        emu.hook(0x0042AAA0, emu.record("done"), 0)
        emu.hook(0x0044A580, emu.record("sound", args=1), 4)
        return emu

    def nursery(self, emu, species: dict, ornaments=(), magic=(), bugs=0, golden=False):
        state, scene = emu.alloc(P_STATE_SIZE), emu.alloc(0x1000)
        emu.write32(scene + 0xA3C, state)
        emu.write32(scene + 0xA54, 0x7000)
        for r, k in ornaments:
            emu.write8(state + 0x9EC + 0xA0 * r + 0x20 * k, 1)
        for flag in magic:
            emu.write8(state + flag, 1)
        if golden:
            emu.write8(state + 0x2183, 1)
        for i in range(bugs):
            emu.write8(state + 0x53F4B + i, 1)
        for (foliage, flower), (v, price, discovered) in species.items():
            emu.write32(state + p_value_cell(foliage, flower), v)
            emu.write32(state + p_price_cell(foliage, flower), price)
            emu.write8(state + 0x64 + foliage * 24 + flower, int(discovered))
        return state, scene

    def click(self, emu, scene) -> int:
        return emu.call(emu.read32(SELL_VT_COMMAND), 8, 9, ecx=scene)

    def test_both_slots_go_in_together(self) -> None:
        emu = self.game()
        self.assertEqual(emu.call(emu.sym("_FtfpStartup@0")), 1)
        for va, stock in ((SELL_VT_COMMAND, SELL_COMMAND), (SELL_VT_ACTIVATE, SELL_ACTIVATE)):
            self.assertNotEqual(emu.read32(va), stock)
        for changed in (SELL_VT_COMMAND, SELL_VT_ACTIVATE):
            emu = self.game()
            emu.write32(changed, 0x00401234)
            before = bytes(emu.uc.mem_read(0x00469730, 0x28))
            self.assertEqual(emu.call(emu.sym("_FtfpStartup@0")), 0)
            self.assertEqual(bytes(emu.uc.mem_read(0x00469730, 0x28)), before)

    def test_opening_the_nursery_adds_the_button_once(self) -> None:
        emu = self.game()
        emu.call(emu.sym("_FtfpStartup@0"))
        emu.hook(0x004360D0, emu.record("stock activate", args=1), 4)
        emu.hook(0x0044E894, lambda e: e.alloc(0x14), 0)
        buttons = []
        emu.hook(0x00401AA0, lambda e: buttons.append([e.arg(i) for i in range(6)]) or 0, 24)
        emu.hook(0x0040B400, emu.record("add", args=1), 4)
        _, scene = self.nursery(emu, {})
        for on in (1, 0, 1):
            emu.call(emu.read32(SELL_VT_ACTIVATE), on, ecx=scene)
        self.assertEqual([c for c in emu.calls if c[0] == "stock activate"],
                         [("stock activate", (1,)), ("stock activate", (0,)), ("stock activate", (1,))])
        self.assertEqual(len(buttons), 1)
        bid, image, x, y, parent, zero = buttons[0]
        self.assertEqual((bid, emu.cstring(image), x, y, parent, zero),
                         (9, b"optimize_prices_button.png", 620, 561, scene, 0))

    def species(self) -> dict:
        rng = random.Random(77)
        out = {}
        for foliage in BP.STOCK_FOLIAGES:
            for flower in BP.STOCK_FLOWERS:
                discovered = rng.random() < 0.3 or (foliage, flower) in ((2, 14), (11, 10))
                out[(foliage, flower)] = (BP.value((foliage, flower)), rng.randint(1, 400), discovered)
        return out

    def test_yes_sets_exactly_the_discovered_species(self) -> None:
        emu = self.game()
        emu.call(emu.sym("_FtfpStartup@0"))
        species = self.species()
        ornaments = ((0, 0), (0, 3), (1, 4), (2, 3), (2, 4))              # ids 0x18, 0x1B, 0x21, 0x25, 0x26
        state, scene = self.nursery(emu, species, ornaments, magic=(0x2182, 0x2185), bugs=48, golden=True)
        score = BP.visitor_score(tuple(i in (0, 3, 9, 13, 14) for i in range(15)), True, 1, True)
        before = bytearray(emu.uc.mem_read(state, P_STATE_SIZE))
        entries = {sid: bytes(emu.uc.mem_read(entry, 0x10)) for sid, entry in emu.entries.items()}
        self.assertEqual(self.click(emu, scene) & 0xFF, 1)
        expected = bytearray(before)
        found = [key for key, (_v, _p, d) in species.items() if d]
        for key in found:
            at = p_price_cell(*key)
            expected[at:at + 4] = BP.shop_best_price(BP.value(key), True, score).to_bytes(4, "little")
        self.assertEqual(bytes(emu.uc.mem_read(state, P_STATE_SIZE)), bytes(expected))
        self.assertEqual({sid: bytes(emu.uc.mem_read(entry, 0x10)) for sid, entry in emu.entries.items()}, entries)
        (q_args, q_text, q_ok, q_cancel), (m_args, m_text, m_ok, _m_cancel) = emu.dialogs
        self.assertEqual(q_args, (0x3E, 1, 1, 0, 0))
        self.assertEqual((q_text, q_ok, q_cancel), ("Set every discovered species\nto its best price per day?", "Yes", "No"))
        self.assertEqual(m_args, (0x3E, 0, 0, 0, 0))
        self.assertEqual((m_text, m_ok), (f"{len(found)} prices set.", "OK"))
        self.assertIn(("sound", (0xC,)), emu.calls)

    def test_no_changes_nothing(self) -> None:
        emu = self.game(answer=1)
        emu.call(emu.sym("_FtfpStartup@0"))
        state, scene = self.nursery(emu, self.species())
        before = bytes(emu.uc.mem_read(state, P_STATE_SIZE))
        self.click(emu, scene)
        self.assertEqual(bytes(emu.uc.mem_read(state, P_STATE_SIZE)), before)
        self.assertEqual(len(emu.dialogs), 1)

    def test_unused_flowers_species(self) -> None:
        table = {}
        emu = self.game(flowers=table)
        emu.call(emu.sym("_FtfpStartup@0"))
        cells = emu.alloc(0x20)
        for i in range(3):
            emu.write32(cells + 4 * i, 123)
        table[(5, 24)] = (BP.value((5, 24)), cells, 1)
        table[(9, 30)] = (BP.value((9, 30)), cells + 4, 0)                 # not discovered
        table[(23, 37)] = (BP.value((23, 37)), cells + 8, 1)
        state, scene = self.nursery(emu, {(1, 1): (7, 5, True)})
        score = BP.visitor_score((False,) * 15, False, 0, False)
        self.click(emu, scene)
        self.assertEqual(emu.read32(cells), BP.shop_best_price(BP.value((5, 24)), False, score))
        self.assertEqual(emu.read32(cells + 4), 123)
        self.assertEqual(emu.read32(cells + 8), BP.shop_best_price(BP.value((23, 37)), False, score))
        self.assertEqual(emu.read32(state + p_price_cell(1, 1)), BP.shop_best_price(7, False, score))
        self.assertEqual(emu.dialogs[-1][1], "3 prices set.")


if __name__ == "__main__":
    unittest.main()
