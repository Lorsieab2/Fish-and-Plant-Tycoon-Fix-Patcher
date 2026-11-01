"""Optimize Prices (both games): the button's price maths, its DLLs and its setting.

* The maths: native/common/price_math.h is compiled (native/common/price_math_harness.c)
  and asked for the price of many species and shops; every answer must be the Python
  model's (src/breeding_fish.py and src/breeding_plant.py, shop_best_price).
* The DLLs run in Unicorn against the vanilla executables (tests/store_emulator.py):
  the two vtable slots go in together or not at all; a click answered Yes sets exactly
  the discovered species to the model's price and changes no other byte; No changes
  nothing.
* The setting: off by default in both games (the owner, 2026-11-01), in the plain "- Modded" copy, shipping the
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
    shops = [(o, s, a, t) for o in range(7) for s in (False, True) for a in (1, 2, 3) for t in (21, 26, 30)]
    rng = random.Random(1717)
    out = [(b, *shop) for b in sorted(bases) for shop in rng.sample(shops, 8)]
    out += [(b, *shop) for b in (4, 26, 70, 190, 239) for shop in shops]
    out += [(rng.randint(1, 400), rng.randint(0, 6), rng.random() < 0.5, rng.randint(0, 3), rng.choice((21, 26, 30)))
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

    def test_fish_max_prices_agree(self) -> None:
        """Max Prices: pm_fish_max is shop_max_price for every base a species can have (all below
        600), and 0-1000."""
        bases = sorted({b for b, *_ in fish_queries()} | set(range(0, 1001)))
        got = self.ask([f"f {b}" for b in bases])
        self.assertEqual(got, [BF.shop_max_price(b) for b in bases])
        self.assertEqual(got, [max(2 * b - 1, 0) for b in bases])
        self.assertEqual(len(bases), 1001)

    def test_plant_max_prices_agree(self) -> None:
        """Max Prices: pm_plant_max is shop_max_price for every species value and 1-1000, with and
        without the Golden Berries of Wealth."""
        values = sorted({v for v, *_ in plant_queries()} | set(range(1, 1001)))
        queries = [(v, gb) for v in values for gb in (False, True)]
        got = self.ask([f"p {v} {int(gb)}" for v, gb in queries])
        self.assertEqual(got, [BP.shop_max_price(v, gb) for v, gb in queries])
        self.assertGreaterEqual(len(queries), 2000)


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

    def test_fish_max_is_twice_base_less_one(self) -> None:
        """The ceiling is 2B - 1 whatever the shop: the guide's highest selling, the last price with a
        sale chance for every crowd, the first price without one 2B."""
        model = BF.FishModel(extras=False)
        for key in ((0, 0), (7, 7), (10, 9), (20, 16)):
            for effects, level in (("none", 1), ("max", 3)):
                base = BF.advertised(BF.base_price(*key), level)
                self.assertEqual(BF.shop_max_price(base), 2 * base - 1)
                self.assertEqual(model.prices(key, effects).highest_selling, BF.shop_max_price(base))
        for base in (1, 2, 15, 239):
            top = BF.shop_max_price(base)
            for crowd in (0, 4, 13, 72):
                self.assertGreater(BF.sale_chance(top, base, crowd), 0.0)
                self.assertEqual(BF.sale_chance(top + 1, base, crowd), 0.0)
            self.assertGreaterEqual(top, BF.shop_best_price(base, 6, True, 3))
        self.assertEqual(BF.shop_max_price(0), 0)

    def test_plant_max_follows_the_golden_berries(self) -> None:
        """The price seen stays below 2V: without the Golden Berries the ceiling is 2V - 1; with
        them, the highest P with P - P/4 below 2V, which is higher; it is the guide's highest
        selling with no effects, and no score or per-plant effect is in it."""
        model = BP.PlantModel(extras=False)
        for v in (1, 7, 44, 95, 130, 250, 2500):
            self.assertEqual(BP.shop_max_price(v, False), min(2 * v - 1, BP.MAX_TYPED_PRICE))
            with_berries = BP.shop_max_price(v, True)
            self.assertLess(with_berries - with_berries // 4, 2 * v)
            if with_berries < BP.MAX_TYPED_PRICE:
                after = with_berries + 1
                self.assertGreaterEqual(after - after // 4, 2 * v)
            if v > 1:
                self.assertGreater(with_berries, BP.shop_max_price(v, False))
            for gb in (False, True):
                top = BP.shop_max_price(v, gb)
                c = BP.Condition(golden_berries=gb)
                self.assertGreater(BP.sale_chance(top, v, 8, c), 0.0)
                self.assertEqual(BP.sale_chance(top + 1, v, 55, c), 0.0)
        for key in ((2, 14), (11, 10), (23, 23)):
            self.assertEqual(model.prices(key, "none").highest_selling, BP.shop_max_price(BP.value(key), False))

    @unittest.skipUnless(FISH_EXE.is_file(), "needs the vanilla Fish Tycoon.exe")
    def test_the_fish_ceiling_is_the_sale_rolls(self) -> None:
        """0x4243DC-0x4243EA: mov ecx, [eax + 0x14B64] (B); add ecx, ecx; cmp [eax + 0x14B60] (the
        asking price), ecx; jge (no sale). Only the entry's own two cells are read."""
        exe = FISH_EXE.read_bytes()
        at = 0x4243DC - 0x400000                       # .text is mapped 1:1 in this exe
        self.assertEqual(exe[at:at + 20], bytes.fromhex("8B88644B0100" "03C9" "3988604B0100" "0F8D9A000000"))

    @unittest.skipUnless(PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon.exe")
    def test_the_golden_berries_are_the_only_save_wide_step(self) -> None:
        """0x436E22: cmp byte [state + 0x2183], 0 then the price seen loses a quarter; every other
        step of 0x436D4B-0x436E3C reads the pot or the plant (0x42DDE0, 0x42DE50, 0x42DEA0,
        0x42D570, 0x42D650, pot + 0x21AC / + 0x21B0)."""
        exe = PLANT_EXE.read_bytes()
        at = 0x436E22 - 0x400000
        self.assertEqual(exe[at:at + 7], bytes.fromhex("80B88321000000"))

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

    def test_off_by_default_in_the_plain_copy(self) -> None:
        for game, manifest in self.manifests.items():
            setting = {s["id"]: s for s in manifest["settings"]}[SETTING]
            self.assertEqual(setting["name"], "Optimize Prices button", game)
            self.assertFalse(setting["default"], game)
            self.assertEqual(setting["category"], "main", game)
            self.assertFalse(setting.get("separate_output", False), game)
            self.assertFalse(setting.get("requires_settings"), game)
            engine = fish_patcher if game == "fish" else plant_patcher
            defaults = engine.enabled_settings(manifest, Namespace(enable=None, disable=None, disable_all=False))
            self.assertNotIn(SETTING, defaults, game)

    def test_it_ships_the_dll_and_the_button(self) -> None:
        expected = {"fish": ("Fish Tycoon Fix Patcher DLLs/Optimize Prices.dll", "Images/OptimizePricesButton.png",
                             "Images/OptimizePricesStoreButton.png", "Images/MaxPricesButton.png",
                             "Images/MaxPricesStoreButton.png"),
                    "plant": ("Plant Tycoon Fix Patcher DLLs/Optimize Prices.dll", "Images/optimize_prices_button.png",
                              "Images/max_prices_button.png")}
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
        # Optimize Prices.dll installs after every other companion (Extra Tanks, Tank Counts and the DS
        # DLLs change the sale scene's code and the tank screen, never the slots it wraps).
        for others in ({"ds_fish", "ds_store"}, {"ds_fish", "ds_store", "extra_tanks"},
                       {"ds_fish", "ds_store", "multiple_ornaments", "tank_greenhouse_counts"}):
            self.assertEqual(fish({SETTING} | others).dll_names[-1], "Optimize Prices.dll", others)
            self.assertEqual(fish({SETTING} | others).dll_names.count("Optimize Prices.dll"), 1, others)
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
        self.assertEqual(len(buttons), 2)
        self.assertEqual([(b[0], emu.cstring(b[1]), b[2], b[3], b[4], b[5]) for b in buttons],
                         [(7, b"OptimizePricesButton.png", 524, 546, scene, 0),
                          (8, b"MaxPricesButton.png", 400, 546, scene, 0)])
        self.assertEqual(sum(1 for c in emu.calls if c[0] == "sound"), 2)
        self.assertIn(("sound", (1,)), emu.calls)
        self.assertEqual(sum(1 for c in emu.calls if c[0] == "add"), 2)

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

    def test_max_prices_sets_exactly_twice_base_less_one(self) -> None:
        """Max Prices (id 8): every discovered species gets 2B - 1, whatever the shop; nothing else
        changes; its own question, then "N prices set."; No changes nothing."""
        for shop in (dict(), dict(ornaments=(0,) * 6, seahorse=0, advertising=1),
                     dict(ornaments=(1,) * 6, seahorse=1, advertising=3)):
            emu = self.game()
            self.install(emu)
            entries, found = self.entries()
            state, scene = self.shop(emu, entries, **shop)
            strings = bytes(emu.uc.mem_read(F_STRINGS, 12 * 0xF9))
            before = bytearray(emu.uc.mem_read(state, 0x20000))
            self.assertEqual(emu.call(emu.read32(SPECIES_VT_COMMAND), 8, 8, ecx=scene) & 0xFF, 1)
            expected = bytearray(before)
            for key in found:
                at = F_SPECIES + (key[0] * F_STRIDE + key[1]) * F_ENTRY + 0x20
                expected[at:at + 4] = BF.shop_max_price(entries[key][1]).to_bytes(4, "little")
                self.assertEqual(BF.shop_max_price(entries[key][1]), 2 * entries[key][1] - 1)
            self.assertEqual(bytes(emu.uc.mem_read(state, 0x20000)), bytes(expected), shop)
            self.assertEqual(bytes(emu.uc.mem_read(F_STRINGS, 12 * 0xF9)), strings)
            (q_id, q_yes_no, q_en, q_de), (m_id, m_yes_no, m_en, m_de) = emu.dialogs
            self.assertEqual((q_id, q_yes_no, m_yes_no), (0xAC, 1, 0))
            self.assertEqual(q_en, "Set every discovered species\nto its highest selling price?\n"
                                   "Fish at this price sell\nmuch more slowly.")
            self.assertEqual(q_de, "Alle entdeckten Arten auf ihren\nh\xf6chsten Verkaufspreis setzen?\n"
                                   "Zu diesem Preis verkaufen sich\nFische viel langsamer.")
            self.assertEqual((m_en, m_de), (f"{len(found)} prices set.", f"{len(found)} Preise gesetzt."))
        emu = self.game(answer=1)
        self.install(emu)
        state, scene = self.shop(emu, self.entries()[0])
        before = bytes(emu.uc.mem_read(state, 0x20000))
        emu.call(emu.read32(SPECIES_VT_COMMAND), 8, 8, ecx=scene)
        self.assertEqual(bytes(emu.uc.mem_read(state, 0x20000)), before)
        self.assertEqual(len(emu.dialogs), 1)

    def test_max_then_optimize(self) -> None:
        """Optimize Prices still sets the best per day after Max Prices, and Max after Optimize."""
        emu = self.game()
        self.install(emu)
        entries, found = self.entries()
        state, scene = self.shop(emu, entries)
        cell = lambda k: state + F_SPECIES + (k[0] * F_STRIDE + k[1]) * F_ENTRY + 0x20  # noqa: E731
        for bid, price in ((8, BF.shop_max_price), (7, lambda b: BF.shop_best_price(b, 3, True, 2, 21)),
                           (8, BF.shop_max_price)):
            emu.call(emu.read32(SPECIES_VT_COMMAND), 8, bid, ecx=scene)
            for key in found:
                self.assertEqual(emu.read32(cell(key)), price(entries[key][1]), (bid, key))

    def test_max_prices_with_ds_species(self) -> None:
        ds_rows = {}
        emu = self.game(ds=ds_rows)
        self.install(emu)
        state, scene = self.shop(emu, {(2, 2): (9, 15)})
        rows = emu.alloc(0x100)
        ds_rows[(26, 4)] = rows
        emu.uc.mem_write(rows, b"DS\0")
        emu.write32(rows + 0x20, 77)
        emu.write32(rows + 0x24, BF.base_price(26, 4))
        emu.call(emu.read32(SPECIES_VT_COMMAND), 8, 8, ecx=scene)
        self.assertEqual(emu.read32(state + F_SPECIES + (2 * F_STRIDE + 2) * F_ENTRY + 0x20), 29)
        self.assertEqual(emu.read32(rows + 0x20), 2 * BF.base_price(26, 4) - 1)
        self.assertEqual(emu.dialogs[-1][2], "2 prices set.")

    def test_bigger_tanks_and_ds_species(self) -> None:
        ds_rows = {}
        emu = self.game(ds=ds_rows)
        self.install(emu)
        emu.write8(0x00419C74, 0x1E)                                       # Bigger tanks' slot bound (30)
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
        price = lambda base: BF.shop_best_price(base, 0, False, 1, 30)       # noqa: E731
        cell = lambda b, f: state + F_SPECIES + (b * F_STRIDE + f) * F_ENTRY + 0x20  # noqa: E731
        self.assertEqual(emu.read32(cell(3, 25)), price(BF.base_price(3, 25)))
        self.assertEqual(emu.read32(cell(2, 2)), price(15))
        self.assertEqual(emu.read32(cell(5, 5), signed=True), -1)
        self.assertEqual(emu.read32(rows + 0x20), price(BF.base_price(26, 4)))
        self.assertEqual(emu.read32(rows + 0x60, signed=True), -1)
        self.assertEqual(emu.dialogs[-1][2], "3 prices set.")


# Fish Tycoon's Fish Store screen (the sale scene, opened with Sell Fish)
SALE_VTABLE = 0x00443B08
SALE_VT_COMMAND, SALE_VT_ACTIVATE = 0x00443B14, 0x00443B2C
SALE_COMMAND, SALE_ACTIVATE = 0x00425B00, 0x00424160
SALE_OPEN = 0x00423E00                 # the scene's opening (customers, pictures, the count): 0x424160 jumps here
SALE_CODE = (0x00423700, 0x00424F20)   # the sale scene's code, where Extra Tanks changes calls
SALE_BUTTON = ROOT / "assets" / "fish_tycoon_optimize_prices" / "Images" / "OptimizePricesStoreButton.png"
# Extra Tanks' call sites in the sale scene (native/ftfp_extra_tanks/tank_sites.h): roll, crowd, pictures,
# "Fish for sale" text.
EXTRA_TANKS_SALE_SITES = (0x004246FB, 0x00423F52, 0x00423FEE, 0x00423927)


@_emulated(FISH_EXE)
class FishSaleButtonTests(unittest.TestCase):
    """The same button on the Fish Store screen's bottom bar: its two slots go in with the
    chart's, all four or none; the sale scene itself runs as before."""

    setUpClass = FishButtonTests.__dict__["setUpClass"]
    tearDownClass = FishButtonTests.__dict__["tearDownClass"]
    install = FishButtonTests.install
    shop = FishButtonTests.shop
    entries = FishButtonTests.entries

    SLOTS = (SPECIES_VT_COMMAND, SPECIES_VT_ACTIVATE, SALE_VT_COMMAND, SALE_VT_ACTIVATE)
    STOCK = [SPECIES_COMMAND, SPECIES_ACTIVATE, SALE_COMMAND, SALE_ACTIVATE]

    def game(self, answer: int = 0, extra_tanks: bool = False):
        """The vanilla game; with extra_tanks, Extra Tanks' four sale-scene calls go elsewhere first
        (as its DLL leaves them: rel32 calls out of the exe)."""
        emu = FishButtonTests.game(self, answer=answer)
        if extra_tanks:
            for k, site in enumerate(EXTRA_TANKS_SALE_SITES):
                emu.uc.mem_write(site, b"\xE8" + ((0x60000000 + 0x10 * k - site - 5) & 0xFFFFFFFF).to_bytes(4, "little"))
        emu.buttons = []
        emu.hook(0x0042A793, lambda e: e.alloc(0x14), 0)                 # operator new
        emu.hook(0x00401B10, lambda e: (e.buttons.append([e.arg(i) for i in range(6)]),
                                        e.uc.reg_read(E.X.UC_X86_REG_ECX))[1], 24)
        emu.hook(0x00425120, lambda e: 0x5000, 0)                         # the sound manager
        emu.hook(0x004251A0, emu.record("sound", 0x6000, args=1), 4)
        emu.hook(0x004015E0, emu.record("button sound", args=2), 8)
        emu.hook(0x0040A9E0, emu.record("add", args=1), 4)
        emu.hook(SALE_OPEN, lambda e: (e.calls.append(("open", (e.uc.reg_read(E.X.UC_X86_REG_ECX), e.arg(0)))),
                                       0)[1], 4)
        return emu

    def sale(self, emu, state: int) -> tuple[int, int]:
        """A Fish Store scene on `state`: scene + 8 = its impl, impl + 0x70 = the game state."""
        scene, impl = emu.alloc(0x40), emu.alloc(0x100)
        emu.write32(scene + 8, impl)
        emu.write32(impl + 0x70, state)
        return scene, impl

    def slots(self, emu) -> list[int]:
        return [emu.read32(va) for va in self.SLOTS]

    def test_all_four_slots_go_in_together(self) -> None:
        for extra in (False, True):
            emu = self.game(extra_tanks=extra)
            self.assertEqual(self.install(emu), 1, extra)
            for va, was in zip(self.SLOTS, self.STOCK):
                self.assertNotEqual(emu.read32(va), was, (extra, hex(va)))
                self.assertGreaterEqual(emu.read32(va), 0x10000000, (extra, hex(va)))

    def test_a_changed_slot_means_none_goes_in(self) -> None:
        for changed in self.SLOTS:
            emu = self.game()
            emu.write32(changed, 0x00401234)
            before = self.slots(emu)
            self.assertEqual(self.install(emu), 0, hex(changed))
            self.assertEqual(self.slots(emu), before)
            self.assertEqual(emu.protects, [])

    def test_a_refused_sale_write_puts_the_others_back(self) -> None:
        for refused in (SALE_VT_COMMAND, SALE_VT_ACTIVATE):
            emu = self.game()

            def protect(e, refused=refused) -> int:
                if e.arg(0) == refused:
                    return 0
                e.write32(e.arg(3), 0x02)
                return 1
            emu.hook_import("VirtualProtect", protect, 16)
            self.assertEqual(self.install(emu), 0)
            self.assertEqual(self.slots(emu), self.STOCK)

    def test_the_sale_scene_is_otherwise_untouched(self) -> None:
        """Sales and customers are the scene's own: with and without Extra Tanks' calls in the sale
        code, installing writes only the two slots (every other slot of the table and every byte of
        the sale code stay as they were), and the scene's opening still runs, first, with its
        own arguments."""
        for extra in (False, True):
            emu = self.game(extra_tanks=extra)
            table = bytes(emu.uc.mem_read(SALE_VTABLE, 0x28))
            code = bytes(emu.uc.mem_read(SALE_CODE[0], SALE_CODE[1] - SALE_CODE[0]))
            self.install(emu)
            after = bytes(emu.uc.mem_read(SALE_VTABLE, 0x28))
            for k in range(0, 0x28, 4):
                if SALE_VTABLE + k not in (SALE_VT_COMMAND, SALE_VT_ACTIVATE):
                    self.assertEqual(after[k:k + 4], table[k:k + 4], (extra, hex(SALE_VTABLE + k)))
            self.assertEqual(bytes(emu.uc.mem_read(SALE_CODE[0], SALE_CODE[1] - SALE_CODE[0])), code, extra)
            self.assertEqual(sorted(set(emu.protects)), sorted(self.SLOTS))
            scene, impl = self.sale(emu, emu.alloc(0x20000))
            for on in (1, 0, 1):
                emu.call(emu.read32(SALE_VT_ACTIVATE), on, ecx=scene)
            self.assertEqual([c for c in emu.calls if c[0] == "open"], [("open", (impl, on)) for on in (1, 0, 1)])
            names = [c[0] for c in emu.calls]
            self.assertLess(names.index("open"), names.index("add"))         # the stock opening runs first

    def test_opening_the_fish_store_adds_the_button_once(self) -> None:
        for extra in (False, True):
            emu = self.game(extra_tanks=extra)
            self.install(emu)
            scene, _ = self.sale(emu, emu.alloc(0x20000))
            for on in (1, 0, 1, 1):
                emu.call(emu.read32(SALE_VT_ACTIVATE), on, ecx=scene)
            self.assertEqual(len(emu.buttons), 2, extra)
            self.assertEqual([(b[0], emu.cstring(b[1]), b[2], b[3], b[4], b[5]) for b in emu.buttons],
                             [(7, b"OptimizePricesStoreButton.png", 544, 547, scene, 0),
                              (8, b"MaxPricesStoreButton.png", 420, 547, scene, 0)])
            self.assertIn(("sound", (1,)), emu.calls)
            self.assertEqual(sum(1 for c in emu.calls if c[0] == "add"), 2)
            # the Species Chart keeps its own buttons, on its own screen
            chart = self.shop(emu, {})[1]
            emu.call(emu.read32(SPECIES_VT_ACTIVATE), 1, ecx=chart)
            self.assertEqual(len(emu.buttons), 4)
            self.assertEqual([(b[0], emu.cstring(b[1]), b[2], b[3], b[4]) for b in emu.buttons[2:]],
                             [(7, b"OptimizePricesButton.png", 524, 546, chart),
                              (8, b"MaxPricesButton.png", 400, 546, chart)])

    def test_done_and_other_messages_reach_the_scene(self) -> None:
        """Done (1) is the stock command's: back to the tank, 1 returned; other messages, 0."""
        emu = self.game()
        self.install(emu)
        scene, _ = self.sale(emu, emu.alloc(0x20000))
        emu.hook(0x0040AC30, emu.record("close", args=1), 4)
        emu.hook(0x0041B070, lambda e: 0x5100, 0)
        emu.hook(0x00418990, emu.record("goto", args=1), 4)
        self.assertEqual(emu.call(emu.read32(SALE_VT_COMMAND), 8, 1, ecx=scene) & 0xFF, 1)
        self.assertIn(("goto", (5,)), emu.calls)
        self.assertEqual(emu.call(emu.read32(SALE_VT_COMMAND), 6, 7, ecx=scene) & 0xFF, 0)
        self.assertEqual(emu.dialogs, [])

    def test_the_fish_store_click_is_the_charts(self) -> None:
        """The same shop and species: a Yes (or No) on each Fish Store button (Optimize Prices 7, Max
        Prices 8) leaves the game state, the string table and the dialogs exactly as the Species
        Chart's same button does."""
        for answer, bid in ((0, 7), (1, 7), (0, 8), (1, 8)):
            results = []
            for where in ("chart", "fish store"):
                emu = self.game(answer=answer)
                self.install(emu)
                entries, found = self.entries()
                state, chart = self.shop(emu, entries)
                strings = bytes(emu.uc.mem_read(F_STRINGS, 12 * 0xF9))
                if where == "chart":
                    handled = emu.call(emu.read32(SPECIES_VT_COMMAND), 8, bid, ecx=chart)
                else:
                    scene, _ = self.sale(emu, state)
                    handled = emu.call(emu.read32(SALE_VT_COMMAND), 8, bid, ecx=scene)
                self.assertEqual(bytes(emu.uc.mem_read(F_STRINGS, 12 * 0xF9)), strings)
                results.append((handled & 0xFF, bytes(emu.uc.mem_read(state, 0x20000)), emu.dialogs))
            (h1, s1, d1), (h2, s2, d2) = results
            self.assertEqual((h1, h2), (1, 1), answer)
            self.assertEqual(s2, s1, answer)
            self.assertEqual(d2, d1, answer)
            self.assertEqual(len(d1), 2 if answer == 0 else 1)
            if answer == 0:
                self.assertEqual(d1[1][2], f"{len(found)} prices set.")


@unittest.skipUnless(FISH_EXE.is_file() and SALE_BUTTON.is_file(), "needs the vanilla game and the button")
class FishSaleButtonPlaceTests(unittest.TestCase):
    """The Fish Store's button covers nothing: not Done, not the "Fish for sale" and price boxes, not
    the fish picture box, not the room where the customers walk (and the "You have sold" line), not
    "Your cash"."""

    BUTTON_X, BUTTON_Y = 544, 547
    IMAGE, MACRO, SIZE = SALE_BUTTON, "SALE_BUTTON", (150, 50)

    @classmethod
    def setUpClass(cls) -> None:
        import io
        import struct
        import zipfile
        try:
            from PIL import Image
        except ImportError:
            raise unittest.SkipTest("needs Pillow")
        if not cls.IMAGE.is_file():
            raise unittest.SkipTest("needs the button")
        cls.exe = FISH_EXE.read_bytes()
        with zipfile.ZipFile(FISH_EXE.parent / "Assets" / "ft.dat") as archive:
            names = {n.lower(): n for n in archive.namelist()}
            cls.art = {n: Image.open(io.BytesIO(archive.read(names[n]))).convert("RGB")
                       for n in ("sellfishshop_bg_png.png", "selldonebutton.png")}
        button = Image.open(cls.IMAGE)
        cls.button = (cls.BUTTON_X, cls.BUTTON_Y, cls.BUTTON_X + button.width // 3, cls.BUTTON_Y + button.height)
        cls.struct = struct

    def va(self, address: int) -> int:
        data, s = self.exe, self.struct
        pe = s.unpack_from("<I", data, 0x3C)[0]
        count, optional = s.unpack_from("<H", data, pe + 6)[0], s.unpack_from("<H", data, pe + 20)[0]
        for i in range(count):
            _v, rva, size, raw = s.unpack_from("<IIII", data, pe + 24 + optional + i * 40 + 8)
            if rva <= address - 0x400000 < rva + size:
                return raw + address - 0x400000 - rva
        raise KeyError(hex(address))

    def imm(self, address: int, at: int) -> int:
        return self.struct.unpack_from("<i", self.exe, self.va(address) + at)[0]

    def assertClear(self, box, what) -> None:
        bx0, by0, bx1, by1 = self.button
        x0, y0, x1, y1 = box
        self.assertTrue(bx1 <= x0 or x1 <= bx0 or by1 <= y0 or y1 <= by0, f"{what} {box} under {self.button}")

    def test_the_button_is_where_the_dll_puts_it(self) -> None:
        source = (ROOT / "native" / "ftfp_fish_prices" / "ftfp_fish_prices.c").read_text(encoding="utf-8")
        self.assertIn(f"#define {self.MACRO}_X {self.BUTTON_X} ", source)
        self.assertIn(f"#define {self.MACRO}_Y {self.BUTTON_Y}\n", source)
        self.assertEqual((self.button[2] - self.button[0], self.button[3] - self.button[1]), self.SIZE)
        self.assertLessEqual(self.button[3], 600)

    def test_not_done(self) -> None:
        """Done's place from the scene's constructor (0x424588: mov edx, y; mov ecx, x)."""
        y, x = self.imm(0x00424588, 1), self.imm(0x0042458E, 1)
        self.assertEqual((x, y), (701, 547))
        done = self.art["selldonebutton.png"]
        self.assertClear((x, y, x + done.width // 3, y + done.height), "Done")

    def test_not_the_texts_or_their_boxes(self) -> None:
        """The scene's texts, from its draw (0x4238D1 cash, 0x423917 "Fish for sale", 0x42398E /
        0x4239CC the price) and the fish picture (0x423A1D): all above the bar but the cash,
        which ends in its black box (read off the background) left of the button."""
        self.assertEqual((self.imm(0x004238D6, 1) & 0xFF, self.imm(0x004238D1, 1)), (0x29, 0x22F))   # cash at 41, 559
        bg = self.art["sellfishshop_bg_png.png"]
        right = 60
        while sum(bg.getpixel((right, 570))) < 60:
            right += 1
        self.assertGreater(self.BUTTON_X, right)
        self.assertClear((0, 551, right, 600), "Your cash")
        # the picture box, the "Fish for sale" and price boxes: the panel above the bar
        self.assertClear((20, 390, 440, 536), "the fish picture, Fish for sale and Price boxes")
        self.assertLess(0x1E0 + 30, self.BUTTON_Y)

    def test_not_the_customers_room(self) -> None:
        """The room (customers, the shop's tanks, "You have sold n fish!" at y 350) ends at the
        panel's top, y 390, read off the background: a white rule, then the panel."""
        self.assertClear((0, 0, 800, 390), "the customers' room")
        self.assertEqual(self.imm(0x004245F3, 1), 0x15E)                 # the sold line's y


SALE_MAX_BUTTON = SALE_BUTTON.parent / "MaxPricesStoreButton.png"


@unittest.skipUnless(FISH_EXE.is_file(), "needs the vanilla game")
class FishSaleMaxButtonPlaceTests(FishSaleButtonPlaceTests):
    """The Fish Store's Max Prices button covers nothing either, Optimize Prices included: every
    test above, for its place, and a gap to Optimize Prices."""

    BUTTON_X, BUTTON_Y = 420, 547
    IMAGE, MACRO, SIZE = SALE_MAX_BUTTON, "SALE_MAX_BUTTON", (120, 50)

    def test_not_optimize_prices(self) -> None:
        from PIL import Image
        width = Image.open(SALE_BUTTON).width // 3
        self.assertClear((544, 547, 544 + width, 597), "Optimize Prices")
        self.assertLessEqual(self.button[2] + 4, 544)


# Fish Tycoon's Species Chart
CHART_BUTTON = ROOT / "assets" / "fish_tycoon_optimize_prices" / "Images" / "OptimizePricesButton.png"
CHART_MAX_BUTTON = CHART_BUTTON.parent / "MaxPricesButton.png"


@unittest.skipUnless(FISH_EXE.is_file(), "needs the vanilla Fish Tycoon")
class FishChartButtonPlaceTests(unittest.TestCase):
    """The Species Chart's two buttons cover nothing: not Done, not each other, not the chart's
    shells, name and price box or keypad (all drawn above the bottom bar, whose top is read off
    species_bg.bmp)."""

    @classmethod
    def setUpClass(cls) -> None:
        import io
        import zipfile
        try:
            from PIL import Image
        except ImportError:
            raise unittest.SkipTest("needs Pillow")
        cls.exe = FISH_EXE.read_bytes()
        with zipfile.ZipFile(FISH_EXE.parent / "Assets" / "ft.dat") as archive:
            names = {n.lower(): n for n in archive.namelist()}
            cls.bg = Image.open(io.BytesIO(archive.read(names["species_bg.bmp"]))).convert("RGB")
            cls.done = Image.open(io.BytesIO(archive.read(names["speciesdonebutton.png"])))
        cls.boxes = {}
        for name, path, x, y in (("Optimize Prices", CHART_BUTTON, 524, 546), ("Max Prices", CHART_MAX_BUTTON, 400, 546)):
            image = Image.open(path)
            cls.boxes[name] = (x, y, x + image.width // 3, y + image.height)

    @staticmethod
    def clear(a, b) -> bool:
        return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]

    def test_the_buttons_are_where_the_dll_puts_them(self) -> None:
        source = (ROOT / "native" / "ftfp_fish_prices" / "ftfp_fish_prices.c").read_text(encoding="utf-8")
        for macro, value in (("BUTTON_X", 524), ("BUTTON_Y", 546), ("MAX_BUTTON_X", 400), ("MAX_BUTTON_Y", 546)):
            self.assertRegex(source, rf"#define {macro} {value}\b")
        self.assertEqual(self.boxes["Max Prices"][2:], (520, 599))
        self.assertEqual(self.boxes["Optimize Prices"][2:], (684, 599))

    def test_not_each_other_or_done(self) -> None:
        """Done from the chart's constructor (0x425A79: mov edx, 0x222; 0x425A7F: mov ecx, 0x2B2)."""
        y = int.from_bytes(self.exe[0x425A7A - 0x400000:0x425A7E - 0x400000], "little")
        x = int.from_bytes(self.exe[0x425A80 - 0x400000:0x425A84 - 0x400000], "little")
        self.assertEqual((x, y), (690, 546))
        done = (x, y, x + self.done.width // 3, y + self.done.height)
        a, b = self.boxes["Max Prices"], self.boxes["Optimize Prices"]
        for name, box in self.boxes.items():
            self.assertTrue(self.clear(box, done), name)
        self.assertTrue(self.clear(a, b))

    def test_on_the_bottom_bar(self) -> None:
        """The bar's top edge (a dark rule across the screen) is above both buttons; the chart's
        own drawing (shells to y 0x1D6 + their height, the keypad, the name and price box at the top
        right) ends above it."""
        top = next(y for y in range(500, 560)
                   if all(sum(self.bg.getpixel((x, y))) < 200 for x in range(380, 700, 20)))
        for name, box in self.boxes.items():
            self.assertGreaterEqual(box[1], top, name)
            self.assertGreaterEqual(box[0], 0)
        self.assertLessEqual(top, 546)
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
        self.assertEqual(len(buttons), 2)
        self.assertEqual([(b[0], emu.cstring(b[1]), b[2], b[3], b[4], b[5]) for b in buttons],
                         [(9, b"optimize_prices_button.png", 620, 561, scene, 0),
                          (10, b"max_prices_button.png", 449, 561, scene, 0)])
        self.assertEqual(sum(1 for c in emu.calls if c[0] == "add"), 2)

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

    def test_max_prices_with_and_without_the_golden_berries(self) -> None:
        """Max Prices (id 10): every discovered species gets the highest price a visitor still buys
        at, 2V - 1 without the Golden Berries of Wealth and higher with them; ornaments, magic plants
        and bugs change nothing; its own question, then "N prices set."."""
        ornaments = ((0, 0), (1, 4), (2, 4))
        for golden in (False, True):
            for extras in ({}, dict(ornaments=ornaments, magic=(0x2182, 0x2185), bugs=48)):
                emu = self.game()
                emu.call(emu.sym("_FtfpStartup@0"))
                species = self.species()
                state, scene = self.nursery(emu, species, golden=golden, **extras)
                before = bytearray(emu.uc.mem_read(state, P_STATE_SIZE))
                entries = {sid: bytes(emu.uc.mem_read(entry, 0x10)) for sid, entry in emu.entries.items()}
                self.assertEqual(emu.call(emu.read32(SELL_VT_COMMAND), 8, 10, ecx=scene) & 0xFF, 1)
                expected = bytearray(before)
                found = [key for key, (_v, _p, d) in species.items() if d]
                for key in found:
                    at = p_price_cell(*key)
                    top = BP.shop_max_price(BP.value(key), golden)
                    if not golden:
                        self.assertEqual(top, 2 * BP.value(key) - 1)
                    else:
                        self.assertGreater(top, 2 * BP.value(key) - 1)
                    expected[at:at + 4] = top.to_bytes(4, "little")
                self.assertEqual(bytes(emu.uc.mem_read(state, P_STATE_SIZE)), bytes(expected), (golden, extras))
                self.assertEqual({sid: bytes(emu.uc.mem_read(e, 0x10)) for sid, e in emu.entries.items()}, entries)
                (q_args, q_text, q_ok, q_cancel), (m_args, m_text, m_ok, _c) = emu.dialogs
                self.assertEqual(q_args, (0x3E, 1, 1, 0, 0))
                self.assertEqual((q_text, q_ok, q_cancel),
                                 ("Set every discovered species\nto its highest selling price?\n"
                                  "Plants at this price sell\nmuch more slowly.", "Yes", "No"))
                self.assertEqual((m_args, m_text, m_ok), ((0x3E, 0, 0, 0, 0), f"{len(found)} prices set.", "OK"))
                self.assertIn(("sound", (0xC,)), emu.calls)

    def test_max_prices_no_changes_nothing(self) -> None:
        emu = self.game(answer=1)
        emu.call(emu.sym("_FtfpStartup@0"))
        state, scene = self.nursery(emu, self.species(), golden=True)
        before = bytes(emu.uc.mem_read(state, P_STATE_SIZE))
        emu.call(emu.read32(SELL_VT_COMMAND), 8, 10, ecx=scene)
        self.assertEqual(bytes(emu.uc.mem_read(state, P_STATE_SIZE)), before)
        self.assertEqual(len(emu.dialogs), 1)

    def test_max_then_optimize(self) -> None:
        """Optimize Prices still sets the best per day after Max Prices, and Max after Optimize."""
        emu = self.game()
        emu.call(emu.sym("_FtfpStartup@0"))
        species = self.species()
        state, scene = self.nursery(emu, species, golden=True)
        score = BP.visitor_score((False,) * 15, False, 1, False)       # the Golden Berries count as a magic plant
        found = [key for key, (_v, _p, d) in species.items() if d]
        for bid, price in ((10, lambda v: BP.shop_max_price(v, True)), (9, lambda v: BP.shop_best_price(v, True, score)),
                           (10, lambda v: BP.shop_max_price(v, True))):
            emu.call(emu.read32(SELL_VT_COMMAND), 8, bid, ecx=scene)
            for key in found:
                self.assertEqual(emu.read32(state + p_price_cell(*key)), price(BP.value(key)), (bid, key))

    def test_max_prices_unused_flowers(self) -> None:
        table = {}
        emu = self.game(flowers=table)
        emu.call(emu.sym("_FtfpStartup@0"))
        cells = emu.alloc(0x20)
        for i in range(2):
            emu.write32(cells + 4 * i, 123)
        table[(5, 24)] = (BP.value((5, 24)), cells, 1)
        table[(9, 30)] = (BP.value((9, 30)), cells + 4, 0)                 # not discovered
        state, scene = self.nursery(emu, {}, golden=True)
        emu.call(emu.read32(SELL_VT_COMMAND), 8, 10, ecx=scene)
        self.assertEqual(emu.read32(cells), BP.shop_max_price(BP.value((5, 24)), True))
        self.assertEqual(emu.read32(cells + 4), 123)
        self.assertEqual(emu.dialogs[-1][1], "1 price set.")

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


PLANT_BUTTONS = {"Optimize Prices": (ROOT / "assets" / "plant_tycoon_optimize_prices" / "Images" / "optimize_prices_button.png",
                                     620, 561, "BUTTON"),
                 "Max Prices": (ROOT / "assets" / "plant_tycoon_optimize_prices" / "Images" / "max_prices_button.png",
                                449, 561, "MAX_BUTTON")}


@unittest.skipUnless(PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon")
class PlantButtonPlaceTests(unittest.TestCase):
    """The Nursery's two buttons cover nothing: each other, the stock button (4, at 0xE3, 0x21C from
    the scene's constructor) and its panel, and they sit on the bar's brick strip (read off
    nurseryUI.png), right of the bar's left frame."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from PIL import Image
        except ImportError:
            raise unittest.SkipTest("needs Pillow")
        cls.exe = PLANT_EXE.read_bytes()
        cls.ui = Image.open(PLANT_EXE.parent / "Images" / "nurseryUI.png").convert("RGBA")
        cls.boxes = {}
        for name, (path, x, y, _macro) in PLANT_BUTTONS.items():
            image = Image.open(path)
            cls.boxes[name] = (x, y, x + image.width // 3, y + image.height)

    @staticmethod
    def clear(a, b) -> bool:
        return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]

    def test_the_buttons_are_where_the_dll_puts_them(self) -> None:
        source = (ROOT / "native" / "ftfp_plant_prices" / "ftfp_plant_prices.c").read_text(encoding="utf-8")
        for name, (_path, x, y, macro) in PLANT_BUTTONS.items():
            self.assertRegex(source, rf"#define {macro}_X {x}\b")
            self.assertRegex(source, rf"#define {macro}_Y {y}\b")
        self.assertEqual(self.boxes["Max Prices"], (449, 561, 612, 600))
        self.assertEqual(self.boxes["Optimize Prices"], (620, 561, 783, 600))

    def test_not_each_other_or_the_stock_button(self) -> None:
        """0x434FC0: mov ecx, 0x21C (y); 0x434FCC: mov eax, 0xE3 (x): the stock button 4 and its panel
        end at the bar's left frame, which the buttons are right of."""
        y = int.from_bytes(self.exe[0x434FC1 - 0x400000:0x434FC5 - 0x400000], "little")
        x = int.from_bytes(self.exe[0x434FCD - 0x400000:0x434FD1 - 0x400000], "little")
        self.assertEqual((x, y), (0xE3, 0x21C))
        self.assertTrue(self.clear(self.boxes["Max Prices"], self.boxes["Optimize Prices"]))
        for name, box in self.boxes.items():
            self.assertTrue(self.clear(box, (0, 0, 360, 600)), name)      # the stock button, its panel, the frame

    def test_on_the_brick_strip(self) -> None:
        """The brick strip runs from the bar's left frame (the first brick column on row 580) to the
        right edge; the buttons start inside it and at most 4 px above the white rule over it, as
        Optimize Prices always has."""
        row = 580 - (600 - self.ui.height)
        left = next(x for x in range(300, 500) if sum(self.ui.getpixel((x, row))[:3]) < 250)
        self.assertLess(left, 449)
        rule = next(y for y in range(540, 600) if sum(self.ui.getpixel((500, y - (600 - self.ui.height)))[:3]) > 450)
        for name, box in self.boxes.items():
            self.assertGreater(box[0], left, name)
            self.assertLessEqual(box[2], 800, name)
            self.assertGreaterEqual(box[1], rule - 4, name)
            self.assertLessEqual(box[3], 600, name)


if __name__ == "__main__":
    unittest.main()
