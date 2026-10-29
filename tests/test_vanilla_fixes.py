"""Fix Vanilla Bugs (Fish Tycoon): the store plants' swapped effects, and the
Golden Seahorse's full health and food (bought, and in a save as it loads).

The seahorse tests run the game's own purchase and load code, stock and
patched, in Unicorn (tests/store_emulator.py)."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402
import pin_vanilla_fixes  # noqa: E402

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

VANILLA = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Fish Tycoon"
           / "Fish Tycoon.exe")

SAVE_BODY = 0x1E3C8                     # the state from +8, as a save stores it after its 0x18-byte header
FISH, TANK, RECORD = 0x390, 0x51EC, 0x288
HEALTH, FOOD, BODY, FIN = 0x3C, 0x44, 0x4C, 0x50


def record_at(tank: int, slot: int) -> int:
    """A fish record's offset in the state."""
    return FISH + tank * TANK + slot * RECORD


def save_body(records: dict[tuple[int, int], tuple[int, int, int, int, int]]) -> bytearray:
    """A save's body: {(tank, slot): (live, body, fin, health, food)}; every other byte a pattern."""
    body = bytearray((i * 7 + 3) & 0xFF for i in range(SAVE_BODY))
    for (tank, slot), (live, kind, fin, health, food) in records.items():
        at = record_at(tank, slot) - 8
        struct.pack_into("<I", body, at, live)
        struct.pack_into("<ii", body, at + BODY, kind, fin)
        struct.pack_into("<i", body, at + HEALTH, health)
        struct.pack_into("<i", body, at + FOOD, food)
    return body


def meters(state: bytes, tank: int, slot: int) -> tuple[int, int]:
    at = record_at(tank, slot)
    return struct.unpack_from("<i", state, at + HEALTH)[0], struct.unpack_from("<i", state, at + FOOD)[0]


class VanillaFixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("fish")

    def test_setting_is_on_by_default_and_first(self) -> None:
        settings = combined.patch_settings("fish")
        self.assertEqual(list(settings)[0], "fix_vanilla_bugs")
        self.assertTrue(settings["fix_vanilla_bugs"]["default"])
        self.assertIn("Plant of Incubation", settings["fix_vanilla_bugs"]["summary"])

    def test_the_plant_effects_swap_their_dword(self) -> None:
        patches = {p["id"]: p for p in self.manifest["patches"] if p["id"].startswith("fix_plant_")}
        self.assertEqual(len(patches), 4)
        starving = patches["fix_plant_effect_starving"]
        self.assertEqual(int(starving["offset"], 16), 0x205A1)
        self.assertEqual((starving["expected"], starving["replacement"]), ("39 98 68 01 00 00", "39 98 7C 01 00 00"))
        for va in (0x4213DB, 0x4214AA, 0x42157D):
            patch = patches[f"fix_plant_effect_eggs_{va:X}"]
            self.assertEqual(int(patch["offset"], 16), va - 0x400000)
            self.assertEqual((patch["expected"], patch["replacement"]), ("8B 8F 7C 01 00 00", "8B 8F 68 01 00 00"))
        self.assertTrue(all(p["requires"] == ["fix_vanilla_bugs"] for p in patches.values()))

    @unittest.skipUnless(VANILLA.is_file(), "the vanilla Fish Tycoon.exe is not here")
    def test_on_the_vanilla_executable(self) -> None:
        data = VANILLA.read_bytes()
        records = fish_patcher.active_patch_records(self.manifest, {"fix_vanilla_bugs"})
        patched, _ = fish_patcher.apply_patch_bytes(data, records)
        self.assertEqual(struct.unpack_from("<I", patched, 0x205A3)[0], 0x17C)
        for va in (0x4213DB, 0x4214AA, 0x42157D):
            self.assertEqual(struct.unpack_from("<I", data, va + 2 - 0x400000)[0], 0x17C)
            self.assertEqual(struct.unpack_from("<I", patched, va + 2 - 0x400000)[0], 0x168)
        for index, ids in ((12, (198, 199)), (13, (200, 201))):      # the store itself is untouched
            at = 0x457EF0 + index * 0x34 + 0x2C - 0x400000
            self.assertEqual(struct.unpack_from("<2I", patched, at), ids)

    def test_the_seahorse_patches_are_this_settings(self) -> None:
        patches = {p["id"]: p for p in self.manifest["patches"]}
        ids = ("fix_golden_seahorse_spawn_health", "fix_golden_seahorse_spawn_food", "fix_golden_seahorse_load_jump",
               "install_golden_seahorse_load_full_meters", "extend_text_virtual_size_for_fix_vanilla_bugs")
        for name in ids:
            self.assertEqual(patches[name]["requires"], ["fix_vanilla_bugs"], name)
        self.assertEqual(patches["install_golden_seahorse_load_full_meters"]["replacement"],
                         pin_vanilla_fixes.spaced(pin_vanilla_fixes.seahorse_load_cave()))
        for name in pin_vanilla_fixes.OTHER_VIRTUAL_SIZE_RECORDS:     # one VirtualSize record per combination
            self.assertIn("fix_vanilla_bugs", patches[name]["excludes"], name)
        self.assertIn("Golden Seahorse", combined.patch_settings("fish")["fix_vanilla_bugs"]["summary"])

    @unittest.skipUnless(VANILLA.is_file(), "the vanilla Fish Tycoon.exe is not here")
    def test_every_combination_keeps_the_ds_fish_load_hook_site(self) -> None:
        # DS Exclusive Fish replaces the memcpy call at 0x41AF62; the seahorse jump sits before it.
        data = VANILLA.read_bytes()
        all_settings = combined.patch_settings("fish")
        settings = [s for s in all_settings if not all_settings[s].get("companion")]
        for mask in range(1 << len(settings)):
            enabled = {s for i, s in enumerate(settings) if mask >> i & 1} | {"fix_vanilla_bugs"}
            patched, _ = fish_patcher.apply_patch_bytes(data, fish_patcher.active_patch_records(self.manifest, enabled))
            self.assertEqual(patched[0x1AF62:0x1AF67], bytes.fromhex("E8 A9 1B 01 00"), enabled)
            self.assertEqual(struct.unpack_from("<I", patched, 0x1F8)[0], 0x3F000, enabled)


def _exe(enabled: set[str], folder: Path) -> Path:
    data = VANILLA.read_bytes()
    patched, _ = fish_patcher.apply_patch_bytes(data, fish_patcher.active_patch_records(
        combined.load_manifest("fish"), enabled))
    path = folder / f"Fish Tycoon {'+'.join(sorted(enabled)) or 'vanilla'}.exe"
    path.write_bytes(patched)
    return path


@unittest.skipUnless(E is not None and VANILLA.is_file(), "needs Unicorn and the vanilla executable")
class GoldenSeahorseMeterTests(unittest.TestCase):
    """The game's own code, stock (setting off) and patched (setting on)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name)
        cls.stock = _exe(set(), folder)
        cls.fixed = _exe({"fix_vanilla_bugs"}, folder)
        cls.together = _exe({"fix_vanilla_bugs", "golden_seahorse_repurchase", "universal_supply_slots",
                             "bigger_tanks"}, folder)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def buy(self, exe: Path) -> tuple[int, int, int, list]:
        """The stock purchase builds the seahorse's record (0x427DBA) up to its placement (0x427E43)."""
        emu = E.Emulator(exe, None, {})
        emu.hook(0x004160A0, lambda e: e.alloc(0x100), 0)                       # the sprite helper
        emu.hook(0x00415390, emu.record("sprites"), 12)
        emu.hook(0x00403240, lambda e: (e.calls.append(("random", e.arg(0))), 7)[1], 0)
        emu.hook(0x004032C0, lambda e: 1234, 0)                                 # the state's clock
        esi = emu.alloc(0x40)
        emu.write32(esi + 0x10, emu.alloc(0x40))
        emu.uc.reg_write(E.X.UC_X86_REG_ESI, esi)
        esp = E.STACK + E.STACK_SIZE - 0x1000
        emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
        emu.uc.emu_start(0x00427DBA, 0x00427E43, count=100_000)
        self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_ESP), esp)
        rec = esp + 0x3C
        return (emu.read32(rec + HEALTH, signed=True), emu.read32(rec + FOOD, signed=True),
                emu.read32(rec + 0x0C), [c for c in emu.calls if c[0] == "random"])

    def test_bought_stock_seahorse_is_80_to_94_health_and_50_food(self) -> None:
        health, food, age, rolls = self.buy(self.stock)
        self.assertEqual((health, food, age), (80 + 7, 50, 21))
        self.assertEqual(rolls, [("random", 15)])

    def test_bought_seahorse_is_full_with_the_setting(self) -> None:
        for exe in (self.fixed, self.together):
            health, food, age, rolls = self.buy(exe)
            self.assertEqual((health, food, age), (100, 100, 21))
            self.assertEqual(rolls, [])

    def load(self, exe: Path, body: bytes, slot: int = 1) -> bytes:
        emu = E.Emulator(exe, None, {})
        emu.hook_fish_save_read(body)
        state = emu.alloc(SAVE_BODY + 0x1000)
        self.assertEqual(emu.call(0x0041AE70, slot, ecx=state) & 0xFF, 1)
        return bytes(emu.uc.mem_read(state, SAVE_BODY + 8))

    RECORDS = {
        (0, 5): (99, 22, 22, 40, 10),           # a half-fed, half-health Golden Seahorse
        (2, 27): (99, 22, 22, 83, 50),          # one in DS Store Items' animal slots
        (1, 3): (0, 22, 22, 40, 10),            # a dead record: not a seahorse any more
        (0, 0): (99, 3, 4, 40, 20),             # a fish
        (1, 26): (99, 22, 30, 50, 20),          # DS Store Items' Puffer Fish: its own DLL's job
        (3, 30): (99, 22, 22, 1, 2),            # the last record the loop reaches
    }

    def test_loading_stock_keeps_every_byte(self) -> None:
        body = save_body(self.RECORDS)
        state = self.load(self.stock, body)
        self.assertEqual(state[8:], bytes(body))

    def test_loading_fills_only_the_seahorses_meters(self) -> None:
        body = save_body(self.RECORDS)
        for exe in (self.fixed, self.together):
            state = self.load(exe, body)
            expected = bytearray(body)
            for tank, slot in ((0, 5), (2, 27), (3, 30)):
                struct.pack_into("<i", expected, record_at(tank, slot) - 8 + HEALTH, 100)
                struct.pack_into("<i", expected, record_at(tank, slot) - 8 + FOOD, 100)
            self.assertEqual(state[8:], bytes(expected))
            self.assertEqual(meters(state, 0, 5), (100, 100))
            self.assertEqual(meters(state, 1, 3), (40, 10))
            self.assertEqual(meters(state, 1, 26), (50, 20))
            self.assertEqual(meters(state, 0, 0), (40, 20))

    def test_a_full_seahorse_loads_unchanged(self) -> None:
        body = save_body({(2, 3): (99, 22, 22, 100, 100)})
        self.assertEqual(self.load(self.fixed, body)[8:], bytes(body))


if __name__ == "__main__":
    unittest.main()
