"""Fix Vanilla Bugs (Plant Tycoon): a save that got the Flower of Knowledge prices
without finding it is re-priced as it loads.

Before the new-game fix (tests/test_knowledge_price_new_game.py), a new game
started after a save that had found the Flower of Knowledge priced every species
at V + 3 x (V/4). Fix Vanilla Bugs sends the load's call at 0x41EEF9 (to 0x41ED70,
just after the save is copied into the state) through 0x464970, which re-prices
such a save once:

  * only when the Flower of Knowledge flag (+0x2181) is clear and every species the
    save has not discovered (V >= 4) asks exactly V + 3 x (V/4);
  * only those undiscovered species, with the price setup's own V -+ Random(V/2);
    discovered species keep their prices (the player sets them);
  * Unused Flowers.dll does the same for its 322 species after reading their sidecar.

These tests load small fixtures, built by emulating the game's own new game,
through the vanilla and the patched load in Unicorn and compare the whole state
byte for byte.
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
sys.path.insert(0, str(ROOT / "scripts"))

import pin_plant_vanilla_fixes as pin  # noqa: E402
import plant_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

PLANT_EXE = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon" / "Plant Tycoon.exe"
SETTING = "fix_vanilla_bugs"
STATE_SIZE = 0x63E64
SAVE_BODY = 0x53FB0                     # the save after its 0x18-byte header is state + 8 .. + 0x53FB8
LOAD, NEW_GAME, PRICE_SETUP, AFTER_FLAG_CLEAR = 0x41EE00, 0x41EF30, 0x41DBD0, 0x41F17D
KNOWLEDGE, DISCOVERED = 0x2181, 0x64
SLOT = 5
FOLIAGES, NEW_COUNT = 23, 14
SIDECAR_HEADER = struct.pack("<3I", 0x574C4650, 1, 24 * 14 * 4 + 24 * 14)


def nox(v: int) -> int:
    return v + 3 * (v // 4)


def normal(v: int, p: int) -> bool:
    return abs(p - v) <= max(v // 2 - 1, 0)


def value_at(f: int, fl: int) -> int:
    return ((f + 0x1D) * 26 + fl) * 4


def price_at(f: int, fl: int) -> int:
    return ((f + 0x37) * 26 + fl) * 4


def discovered_at(f: int, fl: int) -> int:
    return DISCOVERED + f * 24 + fl


SPECIES = [(f, fl) for f in range(1, 24) for fl in range(1, 24)]
PRICE_CELLS = {price_at(f, fl) + i: (f, fl) for f, fl in SPECIES for i in range(4)}


def read_i32(state: bytes, at: int) -> int:
    return struct.unpack_from("<i", state, at)[0]


def patched_exe(enabled: set[str]) -> bytes:
    manifest = combined.load_manifest("plant")
    data, _ = plant_patcher.apply_patch_bytes(PLANT_EXE.read_bytes(),
                                              plant_patcher.active_patch_records(manifest, enabled))
    return data


class PatchBytesTests(unittest.TestCase):
    def test_the_records(self) -> None:
        manifest = combined.load_manifest("plant")
        records = {p["id"]: p for p in manifest["patches"] if p["id"].startswith("fix_loaded_knowledge_prices")}
        self.assertEqual(set(records), {"fix_loaded_knowledge_prices_code", "fix_loaded_knowledge_prices_call"})
        self.assertTrue(all(p["requires"] == [SETTING] for p in records.values()))
        call = records["fix_loaded_knowledge_prices_call"]
        self.assertEqual(int(call["offset"], 16), 0x1EEF9)
        self.assertEqual(call["expected"], "E8 72 FE FF FF")                       # call 0x41ED70
        code = bytes.fromhex(records["fix_loaded_knowledge_prices_code"]["replacement"].replace(" ", ""))
        self.assertEqual(code, pin.repair_bytes())
        self.assertLessEqual(0x464970 + len(code), 0x465000)
        self.assertEqual(int(records["fix_loaded_knowledge_prices_code"]["offset"], 16), 0x64970)

    def test_the_code_writes_only_asking_prices(self) -> None:
        try:
            from capstone import CS_ARCH_X86, CS_MODE_32, Cs
            from capstone.x86 import X86_OP_MEM
        except ImportError:          # the disassembler is not installed (GitHub CI)
            self.skipTest("needs capstone")
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        writes = []
        for ins in md.disasm(pin.repair_bytes(), 0x464970):
            if ins.mnemonic in ("mov", "add", "sub", "inc", "dec", "neg") and ins.operands \
                    and ins.operands[0].type == X86_OP_MEM:
                writes.append(f"{ins.mnemonic} {ins.op_str}")
        # the only memory written: the asking price, and its own counter on the stack
        self.assertEqual(writes, ["inc dword ptr [esp]", "mov dword ptr [ecx + 0xa90], edx"])


def _needs():
    ready = E is not None and E.toolchain_ready() and PLANT_EXE.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


class Files:
    """The DLL's Windows file calls, on an in-memory folder."""

    def __init__(self, emu, files: dict[str, bytes]) -> None:
        self.emu, self.files, self.open, self.next = emu, files, {}, 0x100
        self.writes: list[str] = []
        special = emu.thunk()
        emu.hook(special, self.special_folder, 16)
        emu.hook_import("LoadLibraryW", lambda e: 0x7000, 4)
        emu.hook_import("GetProcAddress", lambda e: special, 8)
        emu.hook_import("GetModuleFileNameW", self.module_name, 12)
        emu.hook_import("CreateDirectoryW", lambda e: 1, 8)
        emu.hook_import("CreateFileW", self.create, 28)
        emu.hook_import("ReadFile", self.read, 20)
        emu.hook_import("WriteFile", self.write, 20)
        emu.hook_import("CloseHandle", lambda e: 1, 4)
        emu.hook_import("MoveFileExW", self.move, 12)
        emu.hook_import("DeleteFileW", self.delete, 4)

    def _put(self, address: int, text: str) -> int:
        self.emu.uc.mem_write(address, (text + "\0").encode("utf-16-le"))
        return len(text)

    def special_folder(self, emu) -> int:
        self._put(emu.arg(1), "C:\\Docs")
        return 1

    def module_name(self, emu) -> int:
        return self._put(emu.arg(1), "C:\\Game\\Plant Tycoon.exe")

    def create(self, emu) -> int:
        path, access = emu.wstring(emu.arg(0)), emu.arg(1)
        if access & 0x40000000:                       # GENERIC_WRITE
            self.writes.append(path)
            self.files[path] = b""
        elif path not in self.files:
            return 0xFFFFFFFF
        handle, self.next = self.next, self.next + 1
        self.open[handle] = [path, 0]
        return handle

    def read(self, emu) -> int:
        path, at = self.open[emu.arg(0)]
        data = self.files[path][at:at + emu.arg(2)]
        emu.uc.mem_write(emu.arg(1), data)
        emu.write32(emu.arg(3), len(data))
        self.open[emu.arg(0)][1] += len(data)
        return 1

    def write(self, emu) -> int:
        path = self.open[emu.arg(0)][0]
        self.files[path] += bytes(emu.uc.mem_read(emu.arg(1), emu.arg(2)))
        emu.write32(emu.arg(3), emu.arg(2))
        return 1

    def move(self, emu) -> int:
        self.files[emu.wstring(emu.arg(1))] = self.files.pop(emu.wstring(emu.arg(0)))
        return 1

    def delete(self, emu) -> int:
        self.files.pop(emu.wstring(emu.arg(0)), None)
        return 1


SIDECAR = f"C:\\Docs\\LDW\\Plant Tycoon\\Plant Tycoon Fix Patcher Data\\New Flowers {SLOT}.dat"


class Harness:
    """The game's load (0x41EE00) of one save body, vanilla or patched, with or without Unused Flowers."""

    def __init__(self, tmp: Path) -> None:
        self.dll, self.symbols = E.build_with_map(
            "ftfp_new_flowers", ROOT / "assets" / "plant_tycoon_flowers" / "Unused Flowers.dll", tmp)
        self.fixed = tmp / "Plant Tycoon fixed.exe"
        self.fixed.write_bytes(patched_exe({SETTING}))

    def emulator(self, fixed: bool, with_dll: bool, seed: int = 7, files: dict | None = None):
        emu = E.Emulator(self.fixed if fixed else PLANT_EXE, self.dll if with_dll else None,
                         self.symbols if with_dll else {})
        rng = random.Random(seed)
        emu.randoms = 0

        def game_random(e):
            e.randoms += 1
            return rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0
        emu.hook(0x004033B0, game_random)
        emu.hook(0x00403430, lambda e: 1000)                                   # the clock

        def memset(e):
            e.uc.mem_write(e.arg(0), bytes([e.arg(1) & 0xFF]) * e.arg(2))
            return e.arg(0)

        def memcpy(e):
            e.uc.mem_write(e.arg(0), bytes(e.uc.mem_read(e.arg(1), e.arg(2))))
            return e.arg(0)
        emu.hook(0x00451280, memset)
        emu.hook(0x00450C10, memcpy)
        emu.hook(0x0042FBC0, lambda e: 0)                                       # the pots' scene after a load
        emu.hook(0x0042FC40, lambda e: 0)
        if with_dll:
            emu.files = Files(emu, dict(files or {}))
            emu.call(emu.sym("_build_tables"))
            for va, stub in ((PRICE_SETUP, "_stub_price_setup"), (NEW_GAME, "_stub_new_game"),
                             (LOAD, "_stub_load")):
                emu.uc.mem_write(va, b"\xE9" + struct.pack("<i", emu.sym(stub) - (va + 5)))
        return emu

    def load(self, body: bytes, fixed: bool, with_dll: bool = False, sidecar: bytes | None = None,
             seed: int = 7, before: bytes | None = None):
        """Load `body` into a state that held `before`; return (emu, state address, state bytes)."""
        files = {SIDECAR: sidecar} if sidecar is not None else {}
        emu = self.emulator(fixed, with_dll, seed, files)
        state = emu.alloc(STATE_SIZE)
        emu.uc.mem_write(state, before if before is not None else bytes(range(256)) * (STATE_SIZE // 256 + 1))

        def read_save(e):
            e.uc.mem_write(e.arg(0), body[:e.arg(1)])
            return 1
        emu.hook(0x004034C0, read_save, 12)
        loaded = emu.call(LOAD, SLOT, ecx=state)
        assert loaded & 0xFF == 1
        return emu, state, bytes(emu.uc.mem_read(state, STATE_SIZE))

    def new_game_state(self, knowledge_before: int, seed: int) -> bytes:
        """A fresh game's state, by the vanilla new game after a save with this flag."""
        emu = self.emulator(False, False, seed)
        state = emu.alloc(STATE_SIZE)
        emu.write8(state + KNOWLEDGE, knowledge_before)
        esp = E.STACK + E.STACK_SIZE - 0x1000
        emu.write32(esp, E.RETURN)
        from unicorn import x86_const as X
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ECX, state)
        emu.uc.emu_start(NEW_GAME, AFTER_FLAG_CLEAR, count=20_000_000)
        return bytes(emu.uc.mem_read(state, STATE_SIZE))

    def new_prices(self, emu) -> dict:
        read = lambda name, f, k: emu.read32(emu.sym(name) + (f * NEW_COUNT + k) * 4, signed=True)
        disc = lambda f, k: emu.uc.mem_read(emu.sym("_discovered") + f * NEW_COUNT + k, 1)[0]
        return {(f, k): (read("_value", f, k), read("_price", f, k), disc(f, k))
                for f in range(1, FOLIAGES + 1) for k in range(NEW_COUNT)}


def body_of(state: bytes) -> bytes:
    return state[8:8 + SAVE_BODY]


def with_changes(state: bytes, knowledge: int | None = None, discovered: dict | None = None,
                 prices: dict | None = None) -> bytes:
    out = bytearray(state)
    if knowledge is not None:
        out[KNOWLEDGE] = knowledge
    for (f, fl), flag in (discovered or {}).items():
        out[discovered_at(f, fl)] = flag
    for (f, fl), p in (prices or {}).items():
        struct.pack_into("<i", out, price_at(f, fl), p)
    return bytes(out)


def sidecar_of(values: dict, prices: dict, discovered: dict) -> bytes:
    price = [[0] * NEW_COUNT for _ in range(24)]
    disc = [[0] * NEW_COUNT for _ in range(24)]
    for (f, k), p in prices.items():
        price[f][k] = p
    for (f, k), d in discovered.items():
        disc[f][k] = d
    return (SIDECAR_HEADER + b"".join(struct.pack("<14i", *row) for row in price)
            + b"".join(bytes(row) for row in disc))


@_needs()
class LoadRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.h = Harness(Path(cls.tmp.name))
        nox_game = cls.h.new_game_state(1, seed=11)          # the bug: Knowledge prices, flag clear
        cls.clean_game = cls.h.new_game_state(0, seed=12)
        # played a little: four species discovered, two prices the player lowered, one left at its price
        cls.player = {(4, 4): 70, (5, 4): 67, (1, 1): 8}    # (4,4) V=95: Knowledge 164; (5,4) V=44: 77
        cls.nox_save = with_changes(nox_game, discovered={(4, 4): 1, (5, 4): 1, (1, 1): 1, (9, 9): 1},
                                    prices=cls.player)
        assert read_i32(cls.nox_save, KNOWLEDGE) & 0xFF == 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def differences(self, a: bytes, b: bytes) -> list[int]:
        return [i for i in range(len(a)) if a[i] != b[i]]

    def test_a_nox_priced_save_without_knowledge_is_re_priced(self) -> None:
        h = self.h
        _, _, vanilla = h.load(body_of(self.nox_save), fixed=False)
        emu, _, fixed = h.load(body_of(self.nox_save), fixed=True)
        changed = self.differences(vanilla, fixed)
        self.assertTrue(changed)
        species = {PRICE_CELLS.get(i) for i in changed}
        self.assertNotIn(None, species)                      # every changed byte is an asking price ...
        for f, fl in species:                                # ... of a species not discovered
            self.assertEqual(fixed[discovered_at(f, fl)], 0)
        undiscovered = [(f, fl) for f, fl in SPECIES if not self.nox_save[discovered_at(f, fl)]]
        for f, fl in undiscovered:
            v, p = read_i32(fixed, value_at(f, fl)), read_i32(fixed, price_at(f, fl))
            self.assertTrue(normal(v, p), (f, fl, v, p))
            self.assertEqual(read_i32(vanilla, price_at(f, fl)), nox(v))
        self.assertEqual(emu.randoms, 2 * sum(read_i32(fixed, value_at(f, fl)) >= 4 for f, fl in undiscovered))

    def test_discovered_species_keep_their_prices_even_at_the_knowledge_price(self) -> None:
        _, _, fixed = self.h.load(body_of(self.nox_save), fixed=True)
        for (f, fl), p in self.player.items():               # lowered by the player
            self.assertEqual(read_i32(fixed, price_at(f, fl)), p)
        v = read_i32(fixed, value_at(9, 9))                  # discovered, still at the Knowledge price
        self.assertEqual(read_i32(fixed, price_at(9, 9)), nox(v))

    def test_the_rest_of_the_state_is_byte_for_byte_the_vanilla_load(self) -> None:
        before = bytes(random.Random(5).randrange(256) for _ in range(STATE_SIZE))
        _, _, vanilla = self.h.load(body_of(self.nox_save), fixed=False, before=before)
        _, _, fixed = self.h.load(body_of(self.nox_save), fixed=True, before=before)
        for i in self.differences(vanilla, fixed):
            self.assertIn(i, PRICE_CELLS)
        # the save's bytes outside the asking prices of undiscovered species are exactly the file's
        repaired = {price_at(f, fl) + i for f, fl in SPECIES if not self.nox_save[discovered_at(f, fl)]
                    for i in range(4)}
        self.assertTrue(all(fixed[8 + i] == self.nox_save[8 + i] for i in range(SAVE_BODY) if 8 + i not in repaired
                            and 8 + i not in range(0x217C, 0x2180)))      # 0x41ED70 rounds +0x217C in both

    def test_a_save_that_found_the_flower_of_knowledge_is_unchanged(self) -> None:
        save = with_changes(self.nox_save, knowledge=1)
        _, _, vanilla = self.h.load(body_of(save), fixed=False)
        emu, _, fixed = self.h.load(body_of(save), fixed=True)
        self.assertEqual(vanilla, fixed)
        self.assertEqual(emu.randoms, 0)

    def test_a_normal_save_is_unchanged_byte_for_byte(self) -> None:
        save = with_changes(self.clean_game, discovered={(4, 4): 1}, prices={(4, 4): 300})
        _, _, vanilla = self.h.load(body_of(save), fixed=False)
        emu, _, fixed = self.h.load(body_of(save), fixed=True)
        self.assertEqual(vanilla, fixed)
        self.assertEqual(emu.randoms, 0)

    def test_one_other_undiscovered_price_leaves_the_save_alone(self) -> None:
        v = read_i32(self.nox_save, value_at(7, 7))
        save = with_changes(self.nox_save, prices={(7, 7): v})   # set by the player on a seedling, say
        _, _, vanilla = self.h.load(body_of(save), fixed=False)
        emu, _, fixed = self.h.load(body_of(save), fixed=True)
        self.assertEqual(vanilla, fixed)
        self.assertEqual(emu.randoms, 0)

    def test_the_repair_does_not_repeat(self) -> None:
        _, _, first = self.h.load(body_of(self.nox_save), fixed=True)
        emu, _, second = self.h.load(body_of(first), fixed=True, seed=99)     # saved, then loaded again
        _, _, vanilla = self.h.load(body_of(first), fixed=False)
        self.assertEqual(second, vanilla)
        self.assertEqual(emu.randoms, 0)

    def test_off_the_load_is_stock(self) -> None:
        stock = patched_exe(set())
        self.assertEqual(stock[0x1EEF9:0x1EEFE], bytes.fromhex("E872FEFFFF"))
        self.assertEqual(stock[0x64970:0x64A4D], bytes(0xDD))

    # ------------------------------------------------------------ Unused Flowers
    def new_flower_fixture(self, all_nox: bool = True):
        emu = self.h.emulator(False, True)
        values = {key: v for key, (v, _p, _d) in self.h.new_prices(emu).items()}
        prices = {key: nox(v) for key, v in values.items()}
        discovered = {(4, 0): 1, (4, 1): 1, (12, 5): 1}
        prices[(4, 0)] = 50                                   # lowered by the player
        prices[(4, 1)] = 61
        if not all_nox:
            prices[(20, 13)] = values[(20, 13)]
        return values, prices, discovered

    def test_unused_flowers_re_prices_its_undiscovered_species_and_saves_them(self) -> None:
        values, prices, discovered = self.new_flower_fixture()
        sidecar = sidecar_of(values, prices, discovered)
        emu, state, _ = self.h.load(body_of(self.nox_save), fixed=True, with_dll=True, sidecar=sidecar)
        got = self.h.new_prices(emu)
        self.assertEqual(len(got), 322)
        self.assertEqual(emu.files.writes, [])               # the load writes no file
        for key, (v, p, d) in got.items():
            self.assertEqual(d, discovered.get(key, 0))
            self.assertEqual(v, values[key])
            if discovered.get(key):
                self.assertEqual(p, prices[key])
            else:
                self.assertTrue(normal(v, p), (key, v, p))
        emu.call(emu.sym("_on_save_all"), state, SLOT)       # the game's next save writes the sidecar
        saved = emu.files.files[SIDECAR]
        self.assertEqual(len(saved), len(sidecar))
        self.assertEqual(saved[:12], SIDECAR_HEADER)
        self.assertEqual(saved[12 + 24 * 14 * 4:], sidecar[12 + 24 * 14 * 4:])   # discoveries kept
        # and loading it again changes nothing
        emu2, _, _ = self.h.load(body_of(self.nox_save), fixed=True, with_dll=True, sidecar=saved, seed=3)
        self.assertEqual(self.h.new_prices(emu2), got)

    def test_unused_flowers_leaves_other_sidecars_alone(self) -> None:
        values, prices, discovered = self.new_flower_fixture()
        cases = (
            ("knowledge found", with_changes(self.nox_save, knowledge=1), sidecar_of(values, prices, discovered), True),
            ("one other price", self.nox_save, sidecar_of(*self.new_flower_fixture(all_nox=False)), True),
            ("vanilla executable", self.nox_save, sidecar_of(values, prices, discovered), False),
            ("normal prices", self.nox_save,
             sidecar_of(values, {k: v for k, v in values.items()}, discovered), True),
        )
        for label, save, sidecar, fixed in cases:
            with self.subTest(label):
                emu, _, _ = self.h.load(body_of(save), fixed=fixed, with_dll=True, sidecar=sidecar)
                got = self.h.new_prices(emu)
                raw = sidecar[12:12 + 24 * 14 * 4]
                for (f, k), (_v, p, _d) in got.items():
                    self.assertEqual(p, struct.unpack_from("<i", raw, (f * 14 + k) * 4)[0])


if __name__ == "__main__":
    unittest.main()
