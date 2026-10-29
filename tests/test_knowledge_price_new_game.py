"""Fix Vanilla Bugs (Plant Tycoon): a new game never starts at the Flower of Knowledge price.

Stock: the new game (0x41EF30) runs the price setup (0x41DBD0, called at
0x41EFB8) before it clears the seven magic plant flags (state + 0x2180..0x2186,
at 0x41F170), and the price setup gives every species V + 3 x (V/4) when the
Flower of Knowledge flag (+0x2181) is set. So a new game started after a save
with that flag was loaded (the game loads the last save when it starts,
0x41FA10) is priced as if it had found the Nox Orchid.

Fix Vanilla Bugs sends the call at 0x41EFB8 through 0x464950, which clears
those seven bytes and jumps to 0x41DBD0. These tests run the vanilla and the
patched code in Unicorn: off, the stock behaviour; on, normal prices, while
finding the Flower of Knowledge still raises them, with Unused Flowers' 322
species too. Loading a save never runs the new game, and the patch changes no
other code.

Fish Tycoon has no such price: its new-game price setup (0x418B10) writes
fixed base prices and "undiscovered" for every species whatever the state held
before, with DS Exclusive Fish too.
"""

from __future__ import annotations

import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import game_mechanics as gm  # noqa: E402
import plant_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

VANILLA_ROOT = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
PLANT_EXE = VANILLA_ROOT / "Plant Tycoon" / "Plant Tycoon.exe"
FISH_EXE = VANILLA_ROOT / "Fish Tycoon" / "Fish Tycoon.exe"

SETTING = "fix_vanilla_bugs"
NEW_GAME, PRICE_SETUP = 0x41EF30, 0x41DBD0
PRICE_CALL, AFTER_PRICE_CALL, AFTER_FLAG_CLEAR = 0x41EFB8, 0x41EFBD, 0x41F17D
CAVE = 0x464950
FLAGS, KNOWLEDGE = 0x2180, 0x2181
STOCK_SPECIES = [(f, fl) for f in range(1, 24) for fl in range(1, 24)]


def nox(v: int) -> int:
    return v + 3 * (v // 4)


def file_at(va: int) -> int:
    return va - 0x400000


def patched_exe(enabled: set[str]) -> bytes:
    manifest = combined.load_manifest("plant")
    data, _ = plant_patcher.apply_patch_bytes(PLANT_EXE.read_bytes(),
                                              plant_patcher.active_patch_records(manifest, enabled))
    return data


class ManifestTests(unittest.TestCase):
    def test_on_by_default_first_and_in_the_plain_modded_copy(self) -> None:
        settings = combined.patch_settings("plant")
        self.assertEqual(list(settings)[0], SETTING)
        setting = settings[SETTING]
        self.assertEqual(setting["name"], "Fix Vanilla Bugs")
        self.assertTrue(setting["default"])
        self.assertFalse(setting.get("separate_output"))
        self.assertNotIn("companion", setting)
        self.assertIn("Flower of Knowledge", setting["summary"])
        self.assertIn("stay as they are", setting["description"])

    def test_its_patches(self) -> None:
        manifest = combined.load_manifest("plant")
        records = {p["id"]: p for p in manifest["patches"] if p["id"].startswith("fix_new_game_knowledge")}
        self.assertEqual(set(records), {"fix_new_game_knowledge_text_size", "fix_new_game_knowledge_clear",
                                        "fix_new_game_knowledge_call"})
        self.assertTrue(all(p["requires"] == [SETTING] for p in records.values()))
        self.assertEqual(records["fix_new_game_knowledge_text_size"]["excludes"], ["seed_refresh_key"])
        call = records["fix_new_game_knowledge_call"]
        self.assertEqual(int(call["offset"], 16), file_at(PRICE_CALL))
        self.assertEqual(call["expected"], "E8 13 EC FF FF")                       # call 0x41DBD0
        self.assertEqual(int(records["fix_new_game_knowledge_clear"]["offset"], 16), file_at(CAVE))
        for combo in ({SETTING}, {SETTING, "seed_refresh_key"},
                      {SETTING, "no_old_age_plant_deaths", "seed_refresh_key"}):
            self.assertRegex(plant_patcher.expected_patched_hash(manifest, combo), r"^[0-9A-F]{64}$")


@unittest.skipUnless(PLANT_EXE.is_file(), "the vanilla Plant Tycoon.exe is not here")
class PatchedBytesTests(unittest.TestCase):
    def test_the_cave_clears_the_seven_flags_then_jumps_to_the_price_setup(self) -> None:
        data = patched_exe({SETTING})
        call = data[file_at(PRICE_CALL):file_at(PRICE_CALL) + 5]
        self.assertEqual(call[0], 0xE8)
        self.assertEqual(PRICE_CALL + 5 + struct.unpack("<i", call[1:])[0], CAVE)
        cave = data[file_at(CAVE):file_at(CAVE) + 19]
        self.assertEqual(cave[:14], bytes.fromhex("31C0" "898180210000" "898183210000"))
        self.assertEqual(cave[14], 0xE9)
        self.assertEqual(CAVE + 19 + struct.unpack("<i", cave[15:19])[0], PRICE_SETUP)
        # the stock clear, still in place: dword 0x2180, word 0x2184, byte 0x2186
        self.assertEqual(data[0x1F170:0x1F17D], bytes.fromhex("898680210000" "66898684210000"))
        self.assertEqual(data[0x1F182:0x1F188], bytes.fromhex("888686210000"))

    def test_with_the_r_key_both_caves_fit(self) -> None:
        data = patched_exe({SETTING, "seed_refresh_key"})
        self.assertEqual(struct.unpack_from("<I", data, 0x1F8)[0], 0x64000)
        self.assertNotEqual(data[0x64930:0x64950], bytes(32))
        self.assertEqual(data[file_at(CAVE):file_at(CAVE) + 19], patched_exe({SETTING})[file_at(CAVE):file_at(CAVE) + 19])

    def test_no_other_code_changes_and_loading_never_runs_the_new_game(self) -> None:
        vanilla, data = PLANT_EXE.read_bytes(), patched_exe({SETTING})
        allowed = (set(range(0x150, 0x154)) | set(range(0x1F8, 0x1FC))
                   | set(range(file_at(PRICE_CALL), file_at(PRICE_CALL) + 5))
                   | set(range(file_at(CAVE), file_at(CAVE) + 19)))
        changed = [i for i in range(len(vanilla)) if vanilla[i] != data[i]]
        self.assertTrue(set(changed) <= allowed, [hex(i) for i in changed if i not in allowed])
        for at in range(0x1EE00, 0x1EF30):           # the load 0x41EE00..0x41EF2F never calls the new game
            if data[at] == 0xE8:
                self.assertNotEqual(0x400000 + at + 5 + struct.unpack_from("<i", data, at + 1)[0], NEW_GAME)


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


@_needs(PLANT_EXE)
class PlantNewGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_new_flowers", ROOT / "assets" / "plant_tycoon_flowers" / "Unused Flowers.dll", Path(cls.tmp.name))
        cls.fixed = Path(cls.tmp.name) / "Plant Tycoon fixed.exe"
        cls.fixed.write_bytes(patched_exe({SETTING}))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def emulator(self, fixed: bool, with_dll: bool = False):
        emu = E.Emulator(self.fixed if fixed else PLANT_EXE, self.dll, self.symbols)
        rng = random.Random(7)
        emu.hook(0x004033B0, lambda e: rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0)    # Random(bound)
        emu.hook(0x00403430, lambda e: 1000)                                              # the clock

        def memset(e):
            e.uc.mem_write(e.arg(0), bytes([e.arg(1) & 0xFF]) * e.arg(2))
            return e.arg(0)
        emu.hook(0x00451280, memset)
        if with_dll:      # the DLL's two hooks, as FtfpStartup writes them
            emu.call(emu.sym("_build_tables"))
            for va, stub in ((PRICE_SETUP, "_stub_price_setup"), (NEW_GAME, "_stub_new_game")):
                emu.uc.mem_write(va, b"\xE9" + struct.pack("<i", emu.sym(stub) - (va + 5)))
        return emu

    def run_to(self, emu, start: int, stop: int, state: int, *args: int) -> None:
        esp = E.STACK + E.STACK_SIZE - 0x1000
        for value in reversed(args):
            esp -= 4
            emu.write32(esp, value)
        esp -= 4
        emu.write32(esp, E.RETURN)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ECX, state)
        emu.uc.emu_start(start, stop, count=20_000_000)

    def new_game(self, fixed: bool, knowledge_before: int, with_dll: bool = False, stop: int = AFTER_FLAG_CLEAR):
        emu = self.emulator(fixed, with_dll)
        state = emu.alloc(0x63E64)
        emu.uc.mem_write(state + FLAGS - 4, b"\xAB" * 15)            # 0x217C..0x218A: a played save's bytes
        emu.write8(state + KNOWLEDGE, knowledge_before)
        self.run_to(emu, NEW_GAME, stop, state)
        return emu, state

    @staticmethod
    def stock_prices(emu, state):
        read = lambda o: emu.read32(state + o, signed=True)
        return {(f, fl): (read(((f + 0x1D) * 26 + fl) * 4), read(((f + 0x37) * 26 + fl) * 4))
                for f, fl in STOCK_SPECIES}

    @staticmethod
    def new_prices(emu):
        read = lambda name, f, k: emu.read32(emu.sym(name) + (f * 14 + k) * 4, signed=True)
        return {(f, 24 + k): (read("_value", f, k), read("_price", f, k)) for f in range(1, 24) for k in range(14)}

    def assert_normal(self, prices) -> None:
        for v, p in prices.values():
            self.assertLessEqual(abs(p - v), v // 2)
        self.assertLess(sum(p == nox(v) for v, p in prices.values()), len(prices) // 10)

    def test_off_a_new_game_after_a_knowledge_save_gets_the_knowledge_price(self) -> None:
        emu, state = self.new_game(False, 1)
        prices = self.stock_prices(emu, state)
        self.assertTrue(all(p == nox(v) for v, p in prices.values()))
        self.assertEqual(prices[(4, 4)], (95, 95 + 3 * 23))
        self.assertEqual(emu.uc.mem_read(state + KNOWLEDGE, 1)[0], 0)   # the save shows it not found

    def test_off_a_clean_new_game_gets_the_normal_prices(self) -> None:
        emu, state = self.new_game(False, 0)
        self.assert_normal(self.stock_prices(emu, state))

    def test_on_a_new_game_after_a_knowledge_save_gets_the_normal_prices(self) -> None:
        emu, state = self.new_game(True, 1)
        prices = self.stock_prices(emu, state)
        self.assertEqual(prices[(4, 4)][0], 95)
        self.assert_normal(prices)
        self.assertEqual(bytes(emu.uc.mem_read(state + FLAGS, 7)), bytes(7))

    def test_on_the_flags_are_cleared_before_the_price_setup_and_nothing_else(self) -> None:
        emu, state = self.new_game(True, 1, stop=AFTER_PRICE_CALL)
        self.assertEqual(bytes(emu.uc.mem_read(state + FLAGS, 7)), bytes(7))
        self.assertEqual(bytes(emu.uc.mem_read(state + FLAGS - 4, 4)), b"\xAB" * 4)   # 0x217C..0x217F
        self.assertEqual(bytes(emu.uc.mem_read(state + FLAGS + 7, 4)), b"\xAB" * 4)   # 0x2187..0x218A

    def test_on_and_off_a_clean_new_game_gets_the_same_prices(self) -> None:
        off, on = self.new_game(False, 0), self.new_game(True, 0)
        self.assertEqual(self.stock_prices(*off), self.stock_prices(*on))

    def test_on_finding_the_flower_of_knowledge_still_gives_the_knowledge_price(self) -> None:
        emu, state = self.new_game(True, 1)
        self.run_to(emu, 0x41EB00, 0x41EB4B, state, 4, 4)            # the magic plant check, flower (4, 4)
        self.assertEqual(emu.uc.mem_read(state + KNOWLEDGE, 1)[0], 1)
        self.assertTrue(all(p == nox(v) for v, p in self.stock_prices(emu, state).values()))

    def test_unused_flowers_follows_the_setting(self) -> None:
        for fixed in (False, True):
            emu, state = self.new_game(fixed, 1, with_dll=True)
            stock, new = self.stock_prices(emu, state), self.new_prices(emu)
            self.assertEqual(len(new), 322)
            if fixed:
                self.assert_normal(stock)
                self.assert_normal(new)
            else:
                self.assertTrue(all(p == nox(v) for v, p in stock.values()))
                self.assertTrue(all(p == nox(v) for v, p in new.values()))
        emu, state = self.new_game(True, 1, with_dll=True)
        self.run_to(emu, 0x41EB00, 0x41EB4B, state, 4, 4)
        self.assertTrue(all(p == nox(v) for v, p in self.new_prices(emu).values()))


@_needs(FISH_EXE)
class FishNewGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map(
            "ftfp_ds_fish", ROOT / "assets" / "fish_tycoon_ds" / "DS Exclusive Fish.dll", Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def new_game_prices(self, stale: bool, with_dll: bool):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        size = 0x30000
        state = emu.alloc(size)
        if stale:      # a played game's leftovers: raised base prices, asking prices, research, difficulty
            rng = random.Random(3)
            emu.uc.mem_write(state, bytes(rng.randrange(256) for _ in range(size)))
        emu.call(0x00418B10, ecx=state)
        if with_dll:
            emu.call(emu.sym("@init_ds_species@4"), ecx=state)
        rows = emu.read32(emu.sym("_ds_rows"))
        got = {}
        for b in range(30):
            for f in range(30):
                if b in (21, 22) or f in (21, 22):
                    continue
                if 23 <= b <= 29:
                    if not with_dll:
                        continue
                    at = rows + ((b - 23) * 31 + f) * 0x28
                elif f <= 20 or with_dll:
                    at = state + 0x14B40 + (b * 31 + f) * 0x28
                else:
                    continue
                got[(b, f)] = (emu.read32(at + 0x20, signed=True), emu.read32(at + 0x24, signed=True))
        return got

    def test_the_new_game_prices_ignore_what_came_before(self) -> None:
        for with_dll, count in ((False, 441), (True, 784)):
            clean, stale = self.new_game_prices(False, with_dll), self.new_game_prices(True, with_dll)
            self.assertEqual(len(clean), count)
            self.assertEqual(clean, stale)
            self.assertTrue(all(asking == -1 for asking, _ in stale.values()))
            self.assertEqual(stale[(7, 7)], (-1, 190))                  # the Golden Guppy


class GameMechanicsTextTests(unittest.TestCase):
    def test_the_plant_page_gives_the_stock_and_the_fixed_behaviour(self) -> None:
        page = gm.load_page("plant")
        prices = next(group for group in page.groups if group.title == "Prices")
        text = " ".join(fact.text for fact in prices.facts)
        for part in ("Flower of Knowledge price", "0x41EFB8", "0x41F170", "loads your last save"):
            self.assertIn(part, text)
        patched = {setting for fact in prices.facts for setting, _ in fact.patched}
        self.assertIn(SETTING, patched)
        magic = " ".join(" ".join(fact.subs) for group in page.groups for fact in group.facts)
        self.assertNotIn("not tried live", magic)


if __name__ == "__main__":
    unittest.main()
