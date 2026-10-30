"""Multiple ornaments: decorative copies of the six store ornaments (Fish Tycoon).

Three layers:
  * the manifest and patcher: the setting, its pinned DLL, its startup loader,
    and every combination without it left exactly as it was;
  * native/ftfp_ornaments/orn_logic_harness.c, the DLL's own rules compiled
    without the game (buying, the limit, the swap of copies through the stock
    ornament records, the trash can, moving between tanks, the sidecar);
  * Unicorn: the DLL's own machine code (rebuilt from source, byte-identical to
    the committed DLL) run against the vanilla executable, so a copy goes
    through the game's real ornament code, and the game's real customer and
    thought code reads a state with 1 or 3 copies.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402

try:
    import store_emulator as E
except ImportError:                     # Unicorn is not installed
    E = None

MANIFEST = ROOT / "data" / "fish_manifest.json"
NATIVE = ROOT / "native" / "ftfp_ornaments"
DLL = ROOT / "assets" / "fish_tycoon_ornaments" / "Multiple Ornaments.dll"
SETTING = "multiple_ornaments"
MSVC = Path(r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231")
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10")
SDK_VERSION = "10.0.26100.0"
VANILLA_EXE = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
               / "Fish Tycoon" / "Fish Tycoon.exe")

ORN_BASE, ORN_STRIDE, TANK_STRIDE = 0x5208, 0x2C, 0x51EC
S_CURRENT_TANK, S_MONEY, S_SPENT, S_SECOND_TANK = 0x384, 0x38C, 0x24, 0x230
NO_ORNAMENT = 0x63


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def toolchain_ready() -> bool:
    return (MSVC / "bin" / "Hostx64" / "x86" / "cl.exe").is_file()


def record(x: int, y: int, sprite: int = 178, w: int = 52, h: int = 37, falling: int = 0) -> bytes:
    rec = bytearray(ORN_STRIDE)
    rec[0] = 1
    struct.pack_into("<ii", rec, 4, x, y)
    struct.pack_into("<i", rec, 0x10, falling)
    struct.pack_into("<iii", rec, 0x1C, h, w, sprite)
    return bytes(rec)


# ---------------------------------------------------------------- manifest and patcher

class ManifestTests(unittest.TestCase):
    def test_setting_is_off_by_default_in_the_upgrades_copy(self) -> None:
        setting = fish_patcher.manifest_settings(manifest())[SETTING]
        self.assertEqual(setting["name"], "Multiple ornaments")
        self.assertFalse(setting["default"])
        self.assertTrue(setting["separate_output"], "new content goes in the Modded Upgrades copy")
        self.assertIn("trash", setting["warning"])
        self.assertTrue(setting["companion"]["startup_loader"])

    def test_dll_is_pinned(self) -> None:
        files = fish_patcher.manifest_settings(manifest())[SETTING]["companion"]["files"]
        self.assertEqual(len(files), 1)
        data = DLL.read_bytes()
        self.assertEqual(files[0]["size"], len(data))
        self.assertEqual(files[0]["sha256"], hashlib.sha256(data).hexdigest().upper())
        self.assertEqual(files[0]["destination"], "Fish Tycoon Fix Patcher DLLs/Multiple Ornaments.dll")

    def test_loader_profile(self) -> None:
        for others in (set(), {"ds_fish"}, {"maximizable_window"}, {"ds_fish", "ds_store", "maximizable_window"}):
            self.assertEqual(ds_fish_loader.fish_profile(others | {SETTING}).dll_name, "Multiple Ornaments.dll")
        self.assertEqual(ds_fish_loader.fish_profile({"ds_fish"}).dll_name, "DS Exclusive Fish.dll")
        self.assertEqual(ds_fish_loader.fish_profile(set()).dll_name, "Maximizable Window.dll")

    def test_every_combination_is_pinned_both_ways(self) -> None:
        pins = manifest()["patched_sha256_by_settings"]
        without = [k for k in pins if SETTING not in k.split(",")]
        with_it = {k for k in pins if SETTING in k.split(",")}
        for key in without:
            enabled = {s for s in key.split(",") if s} | {SETTING}
            self.assertIn(fish_patcher.settings_key(enabled), with_it, key)
        self.assertIn(SETTING, with_it, "the setting on its own")
        self.assertEqual(len(with_it), len(without) + 1)

    def test_no_executable_patch_records(self) -> None:
        """The setting changes the game in memory only (its DLL): no byte-patch record names it."""
        for patch in manifest()["patches"]:
            self.assertNotIn(SETTING, patch.get("requires", []) + patch.get("excludes", []), patch["id"])


@unittest.skipUnless(VANILLA_EXE.is_file(), "the vanilla Fish Tycoon.exe is needed")
class PinTests(unittest.TestCase):
    def build(self, enabled: set[str]) -> bytes:
        data = manifest()
        patched, _ = fish_patcher.apply_patch_bytes(VANILLA_EXE.read_bytes(),
                                                    fish_patcher.active_patch_records(data, enabled))
        if fish_patcher.needs_startup_loader(data, enabled):
            patched, _ = ds_fish_loader.append_startup_loader(patched, ds_fish_loader.fish_profile(enabled))
        return patched

    def test_setting_off_leaves_the_game_byte_identical(self) -> None:
        """Every combination without the setting builds exactly what it built before (its pin from
        main is unchanged), and turning the setting on changes only the startup loader."""
        pins = manifest()["patched_sha256_by_settings"]
        defaults = {k for k, v in fish_patcher.manifest_settings(manifest()).items() if v.get("default")}
        for enabled in (defaults, defaults | {"ds_fish", "ds_store"}, {"fix_vanilla_bugs"}):
            off = self.build(enabled)
            self.assertEqual(hashlib.sha256(off).hexdigest().upper(), pins[fish_patcher.settings_key(enabled)])
            on = self.build(enabled | {SETTING})
            self.assertEqual(hashlib.sha256(on).hexdigest().upper(),
                             pins[fish_patcher.settings_key(enabled | {SETTING})])
            self.assertIn("Multiple Ornaments.dll".encode("utf-16-le"), on)
            self.assertNotIn("Multiple Ornaments.dll".encode("utf-16-le"), off)
        self.assertEqual(hashlib.sha256(VANILLA_EXE.read_bytes()).hexdigest().upper(),
                         manifest()["target"]["sha256"])

    def test_patcher_installs_the_dll_in_the_upgrades_copy(self) -> None:
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            game = root / "Fish Tycoon"
            game.mkdir()
            (game / "Fish Tycoon.exe").write_bytes(VANILLA_EXE.read_bytes())
            args = Namespace(game_dir=str(game), manifest=str(MANIFEST), output_dir=None, dry_run=False,
                             enable=[SETTING], disable=None, disable_all=False)
            self.assertEqual(fish_patcher.apply_manifest(args), 0)
            out = root / "Fish Tycoon - Modded Upgrades"
            self.assertEqual((out / "Fish Tycoon Fix Patcher DLLs" / "Multiple Ornaments.dll").read_bytes(),
                             DLL.read_bytes())
            self.assertTrue((out / "Fish Tycoon - Modded Upgrades.exe").is_file())


class SiteHeaderTests(unittest.TestCase):
    def test_sites_are_the_generated_ones(self) -> None:
        header = (NATIVE / "orn_sites.h").read_text(encoding="utf-8")
        self.assertIn("#define ORN_SITE_COUNT 10", header)
        for va in ("0x00422062u", "0x004220D8u", "0x0041EFD9u", "0x00421BA0u", "0x00421D43u", "0x0041AA98u",
                   "0x00419160u", "0x0041AF59u", "0x004282C6u", "0x00427351u"):
            self.assertIn(va, header)

    @unittest.skipUnless(VANILLA_EXE.is_file(), "the vanilla Fish Tycoon.exe is needed")
    def test_header_matches_the_executable_and_overlaps_nothing(self) -> None:
        """The generator refuses a site that is not the stock code, contains a branch target, or overlaps
        a Fix Patcher patch, a DS Fish site or a DS Store Items site; its output is the committed header."""
        before = (NATIVE / "orn_sites.h").read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ornaments_headers.py"),
                                 str(VANILLA_EXE.parent)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((NATIVE / "orn_sites.h").read_bytes(), before)

    def test_install_is_all_or_none(self) -> None:
        source = (NATIVE / "ftfp_ornaments.c").read_text(encoding="utf-8")
        self.assertIn("installed = prepare() && ftfp_install_sites(writes, ORN_SITE_COUNT);", source)
        self.assertEqual(source.count("(w++, "), 10, "one write per site")


# ---------------------------------------------------------------- the logic harness

@unittest.skipUnless(toolchain_ready(), "the pinned MSVC toolset is not installed")
class HarnessTests(unittest.TestCase):
    lines: dict[str, list[str]] = {}
    draws: list[list[int]] = []
    folder: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        build = Path(cls.tmp.name)
        exe = build / "orn_logic_harness.exe"
        command = [
            str(MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/O2", "/MT", "/W4", "/WX",
            f"/Fo{build}\\", f"/Fe{exe}",
            "/I", str(MSVC / "include"),
            "/I", str(SDK / "Include" / SDK_VERSION / "um"),
            "/I", str(SDK / "Include" / SDK_VERSION / "shared"),
            "/I", str(SDK / "Include" / SDK_VERSION / "ucrt"),
            str(NATIVE / "orn_logic_harness.c"),
            "/link", f"/LIBPATH:{MSVC / 'lib' / 'x86'}",
            f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'um' / 'x86'}",
            f"/LIBPATH:{SDK / 'Lib' / SDK_VERSION / 'ucrt' / 'x86'}", "kernel32.lib",
        ]
        result = subprocess.run(command, cwd=build, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        cls.folder = build / "out"
        cls.folder.mkdir()
        run = subprocess.run([str(exe), str(cls.folder)], capture_output=True, text=True, timeout=60)
        if run.returncode != 0:
            raise AssertionError(run.stdout + run.stderr)
        cls.lines, cls.draws = {}, []
        for line in run.stdout.splitlines():
            name, *rest = line.split()
            if name == "draw":
                cls.draws.append([int(v) for v in rest])
            else:
                cls.lines[name] = rest

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def values(self, name: str) -> dict[str, str]:
        rest = self.lines[name]
        out = {"result": rest[0]}
        for i in range(1, len(rest) - 1, 2):
            out[rest[i]] = rest[i + 1]
        return out

    def test_buying_a_second_copy(self) -> None:
        self.assertEqual(self.lines["buy_unowned"], ["0"], "the first one is the stock purchase")
        self.assertEqual(self.lines["buy_not_ornament"], ["0"])
        bought = self.values("buy_second")
        self.assertEqual(bought, {"result": "1", "money": "99980", "spent": "20", "owned": "1", "copies": "1",
                                  "sound": "14"})
        self.assertEqual(self.lines["buy_state_unchanged"], ["1"],
                         "past the money paid, buying a copy changes nothing in the save's state")
        self.assertEqual(self.values("buy_other_tank"), {"result": "1", "tank2": "1"})

    def test_bought_copy_is_the_record_the_store_makes(self) -> None:
        self.assertEqual(bytes.fromhex(self.lines["bought_record"][0]),
                         record(200, 250, sprite=177, w=52, h=37, falling=1))

    def test_refusals(self) -> None:
        self.assertEqual(self.values("buy_no_money"), {"result": "1", "hint": "2", "tank2": "1", "money": "10"})
        self.assertEqual(self.values("buy_declined"), {"result": "1", "tank2": "1", "money": "100000"})
        self.assertEqual(self.lines["buy_trial_locked"], ["0"], "the stock click refuses what the trial lacks")
        self.assertEqual(self.lines["buy_trial_open"], ["1"])
        self.assertEqual(self.values("buy_full"), {"result": "1", "hint": "6", "tank2": "10", "money": "100000"})
        self.assertEqual(self.lines["max_copies"], ["10"])

    def test_originals_are_put_back_byte_for_byte(self) -> None:
        self.assertEqual(self.values("draws"), {"result": "7", "held_after": "4"})
        self.assertEqual(self.lines["fallen_y"], ["440", "440", "speed", "0"])
        self.assertEqual(self.lines["fall_originals_intact"], ["1"])
        self.assertEqual(self.lines["drag_originals_intact"], ["1"])
        self.assertEqual(self.lines["move_originals_intact"], ["1", "tank1_records_clear", "1"])
        self.assertEqual(self.lines["trash_all"][-1], "1")

    def test_pick_drag_drop(self) -> None:
        self.assertEqual(self.lines["pick_miss"], ["0"])
        self.assertEqual(self.lines["pick"], ["1", "held", "0", "6", "scene_held", "99"],
                         "the top copy, and the game's held-ornament index is left alone")
        self.assertEqual(self.lines["drag"], ["1"])
        self.assertEqual(self.lines["dragged"], ["380", "285", "speed", "0"])
        held_draws = self.draws[7:14]
        self.assertEqual(len(held_draws), 7)
        self.assertEqual(held_draws[-1], [178, 380, 285, 0], "the held copy has no shadow")
        self.assertEqual(self.lines["drop_in_place"], ["1", "held", "-1", "speed", "100"])

    def test_moving_between_tanks(self) -> None:
        self.assertEqual(self.values("move_no_second_tank"), {"result": "1", "hint": "8", "tank0": "7", "tank1": "0"})
        self.assertEqual(self.values("move_to_tank1"),
                         {"result": "1", "sound": "12", "tank0": "6", "tank1": "1", "x": "380", "speed": "100"})

    def test_trashing_copies_keeps_the_original_and_its_effect(self) -> None:
        self.assertEqual(self.values("trash_declined"), {"result": "1", "tank0": "6"})
        self.assertEqual(self.values("trash"), {"result": "1", "sound": "4", "tank0": "5", "owned": "1"})
        self.assertEqual(self.lines["trash_all"], ["tank0", "0", "owned", "1", "originals_intact", "1"])

    def test_a_held_copy_is_let_go_with_its_tank(self) -> None:
        self.assertEqual(self.lines["stale_hold"], ["picked", "1", "drag", "0", "held", "-1"])

    def test_sidecar_round_trip(self) -> None:
        self.assertEqual(self.lines["sidecar_round_trip"], ["1", "counts", "1", "1", "1"])
        self.assertEqual(self.lines["sidecar_missing"], ["0"])
        self.assertEqual(self.lines["sidecar_settings_slot"], ["0"])
        self.assertEqual(self.lines["sidecar_bad"], ["0", "aside", "1"], "a bad file is set aside, never read")
        self.assertTrue(list(self.folder.glob("Ornaments 3.unreadable-1.dat")))
        self.assertEqual(self.lines["sidecar_no_settings_file"], ["1"])
        size = int(self.lines["sidecar_size"][0])
        self.assertEqual(size, 4 * 5 + 4 * 8 + 8 * 10 * ORN_STRIDE)
        self.assertFalse(list(self.folder.glob("*.tmp")), "the temporary file is always moved over or removed")

    def test_tank_map_default(self) -> None:
        self.assertEqual(self.lines["logical_default"], ["0", "2", "-1", "-1"])

    def test_states_differ_only_by_money(self) -> None:
        one = (self.folder / "state_1_copy.bin").read_bytes()
        three = (self.folder / "state_3_copies.bin").read_bytes()
        originals = (self.folder / "state_originals.bin").read_bytes()
        self.assertEqual(one, three, "copies are not in the save's bytes")
        self.assertEqual(one, originals)


# ---------------------------------------------------------------- the real code, emulated

def _emulation_ready() -> bool:
    return E is not None and VANILLA_EXE.is_file() and toolchain_ready()


@unittest.skipUnless(_emulation_ready(), "Unicorn, the vanilla Fish Tycoon.exe and MSVC are needed")
class EmulatedTests(unittest.TestCase):
    """The DLL's machine code and the game's, together."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_ornaments", DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def world(self):
        emu = E.Emulator(VANILLA_EXE, self.dll, self.symbols)
        emu.draws = []
        emu.hook(0x0041BE70, lambda e: e.arg(0), 4)                    # sprite get: the image is its id
        emu.hook(0x00408A40, lambda e: (e.draws.append((e.arg(0), e.arg(1), e.arg(2))), 0)[1], 12)
        emu.hook(0x004095C0, lambda e: 37, 0)                           # image height
        emu.hook(0x004095B0, lambda e: 52, 0)                           # image width
        emu.hook(0x00403240, lambda e: 0, 0)                            # Random(n) -> 0
        emu.hook(0x00416BA0, emu.record("sand", args=2), 8)
        emu.hook(0x00425120, lambda e: 0, 0)
        emu.hook(0x004251A0, emu.record("sound", args=1), 4)            # no sound object: none played
        emu.hook(0x0040AE20, lambda e: 0, 4)
        emu.hook(0x0041A940, emu.record("tip", args=1), 4)
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        emu.hook(0x00407AB0, lambda e: 800, 0)                          # the screen's width
        emu.hook(0x004221A0, emu.record("dialog", args=1), 8)
        emu.hook(0x00401D00, lambda e: 0, 8)                            # Yes
        emu.hook(0x00422440, lambda e: 0, 0)
        state, scene, store = emu.alloc(0x1E510), emu.alloc(0x100), emu.alloc(0x40)
        emu.write32(scene + 0x34, state)
        for offset in (0x38, 0x3C, 0x40, 0x44, 0x4C, 0x50, 0x54):
            emu.write32(scene + offset, emu.alloc(0x10))
        emu.write32(scene + 0x1C, NO_ORNAMENT)                          # no tool held
        emu.write32(scene + 0x28, NO_ORNAMENT)                          # no ornament held
        emu.write32(state + 0x1E4E8, 0xFFFFFFFF)                        # no fish held
        for i, value in enumerate((700, 500, 760, 590)):                # the trash can
            emu.write32(scene + 0x88 + 4 * i, value)
        for t in range(3):                                              # the tank buttons
            for i, value in enumerate((10 + 60 * t, 560, 60 + 60 * t, 590)):
                emu.write32(scene + 0x58 + 16 * t + 4 * i, value)
        emu.write32(store + 0x10, state)
        emu.write32(store + 0x0C, emu.alloc(0x10))
        emu.write32(store + 0x14, emu.alloc(0x10))
        emu.write32(store + 0x20, emu.alloc(0x10))
        emu.write8(state + 0x1E50C, 1)
        emu.write32(state + S_MONEY, 100000)
        for i, price in enumerate((20, 50, 350, 950, 1500, 3500)):
            emu.write32(state + (16 + i) * 20 + 0x74, price)
        emu.state, emu.scene, emu.store = state, scene, store
        return emu

    def original(self, emu, k: int, rec: bytes, item: int = 17) -> None:
        emu.uc.mem_write(emu.state + ORN_BASE + k * ORN_STRIDE, rec)
        emu.write32(emu.state + item * 20 + 0x78, 1)

    def orn(self, emu, k: int, tank: int = 0) -> bytes:
        return bytes(emu.uc.mem_read(emu.state + ORN_BASE + tank * TANK_STRIDE + k * ORN_STRIDE, ORN_STRIDE))

    def copy(self, emu, k: int, tank: int = 0) -> bytes:
        return bytes(emu.uc.mem_read(emu.sym("_copies") + (tank * 10 + k) * ORN_STRIDE, ORN_STRIDE))

    def count(self, emu, tank: int = 0) -> int:
        return emu.read32(emu.sym("_copy_count") + 4 * tank)

    def buy(self, emu, item: int) -> int:
        return emu.call(emu.sym("_store_click"), emu.store, item)

    def gesture(self, emu, press, moves, release) -> tuple[int, int]:
        """A press, drags and a release through the DLL's stubs at the game's call sites."""
        picked = emu.call(emu.sym("_stub_pick"), *press, ecx=emu.scene) & 0xFF
        held = emu.read32(emu.scene + 0x28)
        for x, y in moves:
            emu.call(emu.sym("_stub_drag"), x, y, ecx=emu.scene)
        emu.call(emu.sym("_stub_drop"), *release, ecx=emu.scene)
        return picked, held

    def settle(self, emu) -> None:
        for _ in range(200):
            emu.call(emu.sym("_stub_fall"), ecx=emu.scene)

    def test_copy_record_is_the_stock_purchase_record(self) -> None:
        """The stock purchase body (0x427BB5, the Shell) builds its record; the DLL's copy is the same bytes."""
        emu = self.world()
        captured = []

        def add(e) -> int:
            captured.append(bytes(e.uc.mem_read(e.arg(1), ORN_STRIDE)))
            return 0
        emu.hook(0x00419C00, add, 8)
        from unicorn import x86_const as X
        esp = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.mem_write(esp, bytes(0x100))
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ESI, emu.store)
        emu.uc.reg_write(X.UC_X86_REG_EBX, 1)
        emu.uc.emu_start(0x00427BB5, 0x00427C66, count=10_000)
        emu.write32(emu.state + 16 * 20 + 0x78, 1)
        self.assertEqual(self.buy(emu, 16), 1)
        self.assertEqual(captured, [self.copy(emu, 0)])

    def test_buying_through_the_store_click(self) -> None:
        """The Buy click (0x4282A0) with the DLL's jump at 0x4282C6: an owned ornament becomes a copy, an
        unowned one goes on to the stock purchase (0x428080)."""
        emu = self.world()
        stub = emu.sym("_stub_click")
        emu.uc.mem_write(0x004282C6, b"\xE9" + struct.pack("<i", stub - 0x004282CB) + b"\x90\x90")
        emu.hook(0x00428080, emu.record("stock purchase", args=1), 4)
        emu.write32(emu.store, 17)
        emu.call(0x004282A0, ecx=emu.store)
        self.assertIn(("stock purchase", (17,)), emu.calls)
        self.assertEqual(self.count(emu), 0)
        emu.calls.clear()
        emu.write32(emu.state + 17 * 20 + 0x78, 1)
        emu.call(0x004282A0, ecx=emu.store)
        self.assertNotIn(("stock purchase", (17,)), emu.calls)
        self.assertEqual(self.count(emu), 1)
        self.assertEqual(emu.read32(emu.state + S_MONEY), 100000 - 50)
        self.assertEqual(emu.read32(emu.state + 17 * 20 + 0x78), 1, "ownership stays 1")
        emu.write32(emu.store, 11)                                       # not an ornament: stock
        emu.call(0x004282A0, ecx=emu.store)
        self.assertEqual(self.count(emu), 1)

    def test_store_panel_shows_the_price_of_an_owned_ornament(self) -> None:
        emu = self.world()
        from unicorn import x86_const as X
        stub = emu.sym("_stub_panel")
        for item, owned, expected in ((17, 1, 0x00427478), (11, 1, 0x00427358), (17, 0, 0x00427478)):
            emu.write32(emu.state + item * 20 + 0x78, owned)
            emu.uc.reg_write(X.UC_X86_REG_EAX, item)
            emu.uc.reg_write(X.UC_X86_REG_ESI, emu.store)
            emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
            stops = []

            def stop(uc, address, _size, _data, stops=stops):
                if address in (0x00427478, 0x00427358):
                    stops.append(address)
                    uc.emu_stop()
            from unicorn import UC_HOOK_CODE
            handle = emu.uc.hook_add(UC_HOOK_CODE, stop)
            emu.uc.emu_start(stub, 0, count=50)
            emu.uc.hook_del(handle)
            self.assertEqual(stops, [expected], item)

    def test_copy_is_drawn_exactly_like_the_original(self) -> None:
        """The stock decor pass (0x41EE60, ornaments at 0x41D600) through the DLL's draw stub: a copy with
        a record's bytes is drawn with exactly the calls an original with those bytes gets."""
        rec = record(310, 433)
        emu = self.world()
        self.original(emu, 0, rec)
        emu.call(emu.sym("_stub_draw"), ecx=emu.scene)
        stock = list(emu.draws)
        self.assertEqual(stock, [(3, 310 - 25, 433 + 37 - 25), (178, 310, 433)], "shadow, then the pagoda")

        emu = self.world()
        emu.write32(emu.state + 17 * 20 + 0x78, 1)
        self.buy(emu, 17)
        emu.uc.mem_write(emu.sym("_copies"), rec)
        emu.call(emu.sym("_stub_draw"), ecx=emu.scene)
        self.assertEqual(emu.draws, stock)
        self.assertEqual(self.orn(emu, 0), bytes(ORN_STRIDE), "no original appears in the save's records")

        emu = self.world()                                              # original and two copies
        self.original(emu, 0, rec)
        for i in range(2):
            self.buy(emu, 17)
            emu.uc.mem_write(emu.sym("_copies") + i * ORN_STRIDE, record(100 + 200 * i, 433))
        emu.call(emu.sym("_stub_draw"), ecx=emu.scene)
        self.assertEqual(emu.draws[:2], stock, "the original first, unchanged")
        self.assertEqual(emu.draws[2:], [(3, 75, 445), (178, 100, 433), (3, 275, 445), (178, 300, 433)])

    def test_copy_falls_and_is_dragged_exactly_like_the_original(self) -> None:
        """One gesture (press, three drags, release in the tank) on an original, through the stock code,
        and on a copy, through the DLL's stubs and the same stock code: the same record comes out."""
        start = record(200, 250, falling=1)
        press, moves, release = (226, 451), [(300, 200), (640, 300), (520, 360)], (520, 360)

        emu = self.world()
        self.original(emu, 0, start)
        self.settle(emu)
        landed = self.orn(emu, 0)
        picked, held = self.gesture(emu, press, moves, release)
        self.assertEqual((picked, held), (1, 0))
        self.assertEqual(emu.read32(emu.scene + 0x28), NO_ORNAMENT)
        self.settle(emu)
        original_after = self.orn(emu, 0)
        self.assertNotEqual(original_after, landed, "the gesture moved it")

        emu = self.world()
        emu.write32(emu.state + 17 * 20 + 0x78, 1)
        self.buy(emu, 17)
        emu.uc.mem_write(emu.sym("_copies"), start)
        self.settle(emu)
        self.assertEqual(self.copy(emu, 0), landed)
        picked, held = self.gesture(emu, press, moves, release)
        self.assertEqual((picked, held), (1, NO_ORNAMENT), "a copy never takes the game's held index")
        self.settle(emu)
        self.assertEqual(self.copy(emu, 0), original_after)
        self.assertEqual(self.orn(emu, 0), bytes(ORN_STRIDE))

    def test_copy_moves_to_another_tank_like_the_original(self) -> None:
        emu = self.world()
        self.original(emu, 0, record(200, 433))
        emu.write32(emu.state + S_SECOND_TANK, 1)
        self.gesture(emu, (210, 440), [(85, 575)], (85, 575))
        moved = self.orn(emu, 0, tank=1)
        self.assertEqual(self.orn(emu, 0)[0], 0, "the stock move switches the old record off")
        self.assertEqual(moved[0], 1)

        emu = self.world()
        emu.write32(emu.state + 17 * 20 + 0x78, 1)
        emu.write32(emu.state + S_SECOND_TANK, 1)
        self.buy(emu, 17)
        emu.uc.mem_write(emu.sym("_copies"), record(200, 433))
        self.gesture(emu, (210, 440), [(85, 575)], (85, 575))
        self.assertEqual((self.count(emu, 0), self.count(emu, 1)), (0, 1))
        self.assertEqual(self.copy(emu, 0, tank=1), moved)
        self.assertEqual(self.orn(emu, 0, tank=1), bytes(ORN_STRIDE))

    def test_trash_takes_a_copy_never_an_original(self) -> None:
        emu = self.world()
        self.original(emu, 0, record(200, 433))
        for _ in range(3):
            self.buy(emu, 17)
        before = self.orn(emu, 0)
        self.gesture(emu, (210, 440), [(720, 550)], (720, 550))           # the original: the stock drop ignores the can
        self.assertEqual(self.count(emu), 3)
        self.assertEqual(self.orn(emu, 0)[0], 1)
        self.settle(emu)
        for k in range(3):
            emu.uc.mem_write(emu.sym("_copies") + k * ORN_STRIDE, record(500, 433))
        self.gesture(emu, (510, 440), [(720, 550)], (720, 550))
        self.assertEqual(self.count(emu), 2)
        self.assertEqual(emu.read32(emu.state + 17 * 20 + 0x78), 1)
        self.assertEqual(self.orn(emu, 0)[:4], before[:4])

    # ---------------------------------------------------------- the effect, counted once
    def customers(self, emu) -> int:
        """The selling scene's customer count (0x423E7D-0x423F4A), Random fixed at 0."""
        from unicorn import x86_const as X
        sell = emu.alloc(0x100)
        emu.write32(sell + 0x70, emu.state)
        emu.write32(sell + 0x6C, emu.alloc(0x10))
        emu.hook(0x00413B20, lambda e: 0, 0)
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        emu.uc.reg_write(X.UC_X86_REG_EDI, sell)
        emu.uc.reg_write(X.UC_X86_REG_EBX, 0)
        emu.uc.emu_start(0x00423E7D, 0x00423F4E, count=10_000)
        return emu.uc.reg_read(X.UC_X86_REG_EAX)

    def decor_thought(self, emu) -> int:
        """The customers' "?" thought (0x413651-0x4136A2): how many ornaments count."""
        from unicorn import x86_const as X
        holder = emu.alloc(0x6000)
        emu.write32(holder + 0x5DE4, emu.state)
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        emu.uc.reg_write(X.UC_X86_REG_ESI, holder)
        emu.uc.emu_start(0x00413651, 0x004136A2, count=1_000)
        return emu.uc.reg_read(X.UC_X86_REG_EDI)

    def selling_numbers(self, copies: int, fish_slots: tuple[int, ...]) -> tuple[int, int, int]:
        emu = self.world()
        self.original(emu, 0, record(200, 433), item=18)
        self.original(emu, 1, record(400, 433), item=16)
        emu.write32(emu.state + 0x26C, 3)                                # Advertising level 3
        for slot in fish_slots:                                          # adults in the selling tank
            rec = emu.state + 0x390 + 2 * TANK_STRIDE + slot * 0x288
            emu.write32(rec, 1)
            emu.write32(rec + 0x0C, 30)
            emu.write32(rec + 0x3C, 80)
        for i in range(copies):
            emu.write32(emu.state + S_CURRENT_TANK, i % 3)
            self.assertEqual(self.buy(emu, 18 if i % 2 else 16), 1)
        emu.write32(emu.state + S_CURRENT_TANK, 0)
        self.assertEqual(sum(self.count(emu, t) for t in range(3)), copies)
        return self.customers(emu), self.decor_thought(emu), emu.read32(emu.state + 18 * 20 + 0x78)

    def test_effect_is_counted_once(self) -> None:
        """1 copy or 3 copies (or none): the game's own customer count and decor thought give the same
        numbers, and the ornaments' ownership stays 1. Generic over which fish slots hold the adults
        (stock 21, "Bigger tanks" 26)."""
        for slots in ((0, 3, 7, 20), (0, 1, 2, 3, 4, 5, 18, 19, 20), tuple(range(21))):
            none = self.selling_numbers(0, slots)
            self.assertEqual(none[1], 2, "two ornaments owned")
            self.assertEqual(none[2], 1)
            self.assertEqual(self.selling_numbers(1, slots), none, slots)
            self.assertEqual(self.selling_numbers(3, slots), none, slots)


if __name__ == "__main__":
    unittest.main()
