"""DS Store Items: the animals' own records and "Tank Animals <slot>.dat".

The DLL is rebuilt from its source (tests/store_emulator.py) and run with the
vanilla executable, stock and with Bigger tanks: 30 fish, in Unicorn. The
earlier build (origin/main before this change, which kept the animals in the
game's fish records 26-30) is rebuilt from git for the side-by-side checks:
the animals' effects must be the same, fish by fish, roll by roll.
"""

from __future__ import annotations

import random
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import store_emulator as E
    from unicorn import x86_const as X
except ImportError:          # Unicorn is not installed
    E = None

import test_fish_30 as F  # noqa: E402

VANILLA = F.VANILLA
DLL = ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll"
OLD_COMMIT = "8ff9741"                       # the last build with the animals in fish records 26-30
FISH, TANK, RECORD = 0x390, 0x51EC, 0x288
SAVE_BODY = 0x1E3C8
FTCA = struct.unpack("<I", b"FTCA")[0]
SLOT = 3
SIDECAR = f"C:\\Docs\\LDW\\Fish Tycoon\\Fish Tycoon Fix Patcher Data\\Tank Animals {SLOT}.dat"
PREVIOUS = SIDECAR.replace(".dat", ".previous.dat")


def _needs():
    ready = E is not None and E.toolchain_ready() and VANILLA.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


def old_build(out: Path) -> tuple[Path, dict[str, int]]:
    """The earlier DS Store Items, rebuilt from git with its own headers, and its map's symbols."""
    native = out / "native"
    for path in ("native/ftfp_ds_store/ftfp_ds_store.c", "native/ftfp_ds_store/ftfp_ds_store.def",
                 "native/ftfp_ds_store/store_sites.h", "native/ftfp_ds_store/store_data.h",
                 "native/ftfp_ds_fish/install_sites.h", "native/common/time_warp_popup.h",
                 "native/common/setting_file.h"):
        data = subprocess.run(["git", "show", f"{OLD_COMMIT}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    build = out / "build"
    build.mkdir(exist_ok=True)
    project = native / "ftfp_ds_store"
    command = [
        str(E.MSVC / "bin" / "Hostx64" / "x86" / "cl.exe"), "/nologo", "/LD", "/O2", "/MT", "/W4", "/WX",
        "/GS-", "/Brepro", f"/Fo{build}\\",
        "/I", str(E.MSVC / "include"),
        "/I", str(E.SDK / "Include" / E.SDK_VERSION / "um"),
        "/I", str(E.SDK / "Include" / E.SDK_VERSION / "shared"),
        "/I", str(E.SDK / "Include" / E.SDK_VERSION / "ucrt"),
        str(project / "ftfp_ds_store.c"),
        "/link", "/Brepro", f"/DEF:{project / 'ftfp_ds_store.def'}",
        f"/LIBPATH:{E.MSVC / 'lib' / 'x86'}",
        f"/LIBPATH:{E.SDK / 'Lib' / E.SDK_VERSION / 'um' / 'x86'}",
        f"/LIBPATH:{E.SDK / 'Lib' / E.SDK_VERSION / 'ucrt' / 'x86'}",
        f"/IMPLIB:{build / 'old.lib'}", f"/OUT:{build / 'old.dll'}", f"/MAP:{build / 'old.map'}",
        "/RELEASE", "/SAFESEH:NO", "kernel32.lib", "user32.lib",
    ]
    result = subprocess.run(command, cwd=build, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    import re
    symbols = {}
    for line in (build / "old.map").read_text(encoding="latin-1").splitlines():
        match = re.match(r"\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+(\S+)\s+([0-9A-Fa-f]{8})\b", line)
        if match:
            symbols.setdefault(match.group(1), int(match.group(2), 16))
    return build / "old.dll", symbols


class Files:
    """The DLL's Windows file calls, on an in-memory folder; `fail` names paths whose writes fail."""

    def __init__(self, emu, files: dict[str, bytes] | None = None) -> None:
        self.emu, self.files, self.open, self.next = emu, dict(files or {}), {}, 0x100
        self.fail: set[str] = set()
        self.deleted: list[str] = []
        special = emu.thunk()
        emu.hook(special, self.special_folder, 16)
        emu.hook_import("GetModuleHandleW", lambda e: 0x7000, 4)
        emu.hook_import("GetProcAddress", lambda e: special, 8)
        emu.hook_import("GetModuleFileNameW", self.module_name, 12)
        emu.hook_import("CreateDirectoryW", lambda e: 1, 8)
        emu.hook_import("CreateFileW", self.create, 28)
        emu.hook_import("ReadFile", self.read, 20)
        emu.hook_import("WriteFile", self.write, 20)
        emu.hook_import("FlushFileBuffers", lambda e: 1, 4)
        emu.hook_import("CloseHandle", lambda e: 1, 4)
        emu.hook_import("MoveFileExW", self.move, 12)
        emu.hook_import("DeleteFileW", self.delete, 4)
        emu.hook_import("GetFileAttributesW", self.attributes, 4)

    def _put(self, address: int, text: str) -> int:
        self.emu.uc.mem_write(address, (text + "\0").encode("utf-16-le"))
        return len(text)

    def special_folder(self, emu) -> int:
        self._put(emu.arg(1), "C:\\Docs")
        return 1

    def module_name(self, emu) -> int:
        return self._put(emu.arg(1), "C:\\Game\\Fish Tycoon.exe")

    def attributes(self, emu) -> int:
        return 0x80 if emu.wstring(emu.arg(0)) in self.files else 0xFFFFFFFF

    def create(self, emu) -> int:
        path, access, disposition = emu.wstring(emu.arg(0)), emu.arg(1), emu.arg(4)
        if access & 0x40000000:                       # GENERIC_WRITE: a new file
            if path in self.fail:
                return 0xFFFFFFFF
            self.files[path] = b""
            at = 0
        elif access & 0x4:                            # FILE_APPEND_DATA (the log)
            self.files.setdefault(path, b"")
            at = len(self.files[path])
        elif path not in self.files:
            return 0xFFFFFFFF
        else:
            at = 0
        handle, self.next = self.next, self.next + 1
        self.open[handle] = [path, at]
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
        source, target = emu.wstring(emu.arg(0)), emu.wstring(emu.arg(1))
        if target in self.fail:
            return 0
        if target in self.files and not emu.arg(2) & 1:          # MOVEFILE_REPLACE_EXISTING
            return 0
        self.files[target] = self.files.pop(source)
        return 1

    def delete(self, emu) -> int:
        path = emu.wstring(emu.arg(0))
        self.deleted.append(path)
        self.files.pop(path, None)
        return 1

    def log(self) -> str:
        return self.files.get("C:\\Game\\Fish Tycoon Fix Patcher DLLs\\DS Store Items.log", b"").decode("latin-1")


def animal_record(fin: int, health: int = 100, food: int = 100, live: int = 99) -> bytes:
    """A store animal as the DLL builds it (body 22, its fin, the FTCA mark)."""
    r = bytearray(F.fish_record(body=22, fin=fin, health=health, food=food, age=21, live=live))
    struct.pack_into("<II", r, 0x14, FTCA, fin)
    return bytes(r)


def save_body(records: dict[tuple[int, int], bytes], money: int = 5000) -> bytearray:
    body = bytearray(SAVE_BODY)
    struct.pack_into("<i", body, 0x38C - 8, money)
    struct.pack_into("<i", body, 0x24 - 8, 777)
    struct.pack_into("<i", body, 0x3C - 8, 12)                   # sessions played
    struct.pack_into("<i", body, 0x44 - 8, 3456)                 # minutes played
    struct.pack_into("<i", body, 0x1E168 - 8, 10)
    for (tank, slot), record in records.items():
        at = FISH + tank * TANK + slot * RECORD - 8
        body[at:at + RECORD] = record
    return body


@_needs()
class AnimalTests(unittest.TestCase):
    stack_probe = staticmethod(F.EmulatedTests.stack_probe)
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        (tmp / "new").mkdir()
        (tmp / "old").mkdir()
        cls.dll, cls.symbols = E.build_with_map("ftfp_ds_store", DLL, tmp / "new")
        cls.old_dll, cls.old_symbols = old_build(tmp / "old")
        cls.exe30 = tmp / "Fish Tycoon 30.exe"
        cls.exe30.write_bytes(F.patched_exe({"bigger_tanks"}))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ harness
    def emulator(self, patched: bool = True, old: bool = False, files: dict | None = None, seed: int = 9):
        emu = E.Emulator(self.exe30 if patched else VANILLA, self.old_dll if old else self.dll,
                         self.old_symbols if old else self.symbols)
        emu.files = Files(emu, files)
        rng = random.Random(seed)
        emu.randoms = []

        def game_random(e):
            value = rng.randrange(e.arg(0)) if e.arg(0) > 0 else 0
            e.randoms.append((e.arg(0), value))
            return value
        emu.hook(0x00403240, game_random)
        emu.hook(0x004032C0, lambda e: F.NOW, 0)
        emu.hook(0x004020D0, lambda e: 50_000)
        state = emu.alloc(F.STATE_SIZE)
        emu.write32(0x0045ABDC, state)                          # the game's state pointer
        emu.state = state
        return emu

    def animal(self, emu, tank: int, k: int) -> int:
        return emu.call(emu.sym("_animal"), emu.state, tank, k)

    def animal_slot(self, emu, tank: int, k: int) -> int:
        return emu.call(emu.sym("_animal_slot"), emu.state, tank, k)

    def store(self, emu) -> list[bytes]:
        return [bytes(emu.uc.mem_read(self.animal(emu, t, k), RECORD)) for t in range(3) for k in range(5)]

    def place(self, emu, tank: int, record: bytes) -> int:
        buffer = emu.alloc(RECORD)
        emu.uc.mem_write(buffer, record)
        return emu.call(emu.sym("_place_animal"), emu.state, tank, buffer)

    def load(self, body: bytes, patched: bool = True, files: dict | None = None, fail: set[str] = frozenset()):
        """The DLL's Load (the state's vtable slot 0x4424D0): the game's own load, then the animals."""
        emu = self.emulator(patched, files=files)
        emu.files.fail |= set(fail)
        emu.hook_fish_save_read(bytes(body))
        self.assertEqual(emu.call(emu.sym("@on_state_load@12"), SLOT, ecx=emu.state) & 0xFF, 1)
        return emu

    def record(self, emu, tank: int, slot: int) -> bytes:
        return bytes(emu.uc.mem_read(emu.state + FISH + tank * TANK + slot * RECORD, RECORD))

    # ------------------------------------------------------------ the slot number game code follows
    def test_each_animals_slot_number_lands_on_its_record_in_the_games_arithmetic(self) -> None:
        for offset in (0, 4, 8, 12):                            # the state on either 8-byte phase
            emu = self.emulator()
            emu.state += offset
            emu.write32(0x0045ABDC, emu.state)
            for tank in range(3):
                for k in range(5):
                    slot = self.animal_slot(emu, tank, k)
                    self.assertTrue(31 <= slot < 1 << 29, slot)
                    self.assertEqual((emu.state + FISH + tank * TANK + slot * RECORD) & 0xFFFFFFFF,
                                     self.animal(emu, tank, k))
            # the game's own REMOVE_FISH on that number clears the animal and nothing in the state
            self.place(emu, 1, animal_record(31))
            before = bytes(emu.uc.mem_read(emu.state, F.STATE_SIZE))
            emu.call(0x00418E20, 1, self.animal_slot(emu, 1, 0), ecx=emu.state)
            self.assertEqual(bytes(emu.uc.mem_read(emu.state, F.STATE_SIZE)), before)
            self.assertEqual(emu.read32(self.animal(emu, 1, 0)), 0)

    def test_the_view_lists_the_fish_then_the_animals(self) -> None:
        for patched, fish in ((False, 21), (True, 30)):
            for function, site, stub in ((0x00413D80, 0x004140D0, "_stub_build_next"),
                                         (0x00415460, 0x0041589E, "_stub_refresh_next")):
                emu = self.emulator(patched)
                emu.uc.mem_write(site, b"\xE9" + struct.pack("<i", emu.sym(stub) - (site + 5)) + b"\x90")
                for s in range(31):
                    emu.uc.mem_write(emu.state + FISH + s * RECORD, F.fish_record(seed=s))
                for fin in (30, 31, 32):
                    self.place(emu, 0, animal_record(fin))
                self.place(emu, 1, animal_record(22))           # another tank's: not here
                emu.view = emu.alloc(0x6000)
                got = F.EmulatedTests.build_view(self, emu, 0, function)
                animals = [(0, self.animal_slot(emu, 0, k)) for k in range(3)]
                self.assertEqual(got, [(0, s) for s in range(fish)] + animals, (patched, hex(function)))

    # ------------------------------------------------------------ the one-time move out of the fish records
    OLD_LAYOUT = {(0, 26): animal_record(30, 50, 20), (0, 27): animal_record(32), (1, 30): animal_record(31, 70, 40),
                  (2, 28): animal_record(22, 40, 10)}

    def old_save(self) -> bytearray:
        layout = dict(self.OLD_LAYOUT)
        layout.update({(0, s): F.fish_record(seed=s) for s in range(0, 26)})
        layout.update({(2, s): F.fish_record(seed=40 + s) for s in range(0, 5)})
        return save_body(layout)

    def test_a_save_from_the_earlier_build_moves_its_animals_into_their_own_records_and_file(self) -> None:
        for patched in (False, True):
            body = self.old_save()
            emu = self.load(body, patched)
            store = self.store(emu)
            expected_tank = {0: [30, 32], 1: [31], 2: [22]}
            for tank, fins in expected_tank.items():
                self.assertEqual([struct.unpack_from("<i", store[tank * 5 + k], 0x50)[0] for k in range(len(fins))],
                                 fins)
            puffer = store[0]
            self.assertEqual(struct.unpack_from("<ii", puffer, 0x3C), (100, 0))     # filled on load
            self.assertEqual(struct.unpack_from("<i", puffer, 0x44)[0], 100)
            seahorse = store[10]
            self.assertEqual(struct.unpack_from("<i", seahorse, 0x3C)[0], 40)        # Fix Vanilla Bugs' job
            for (tank, slot) in self.OLD_LAYOUT:
                self.assertEqual(struct.unpack_from("<I", self.record(emu, tank, slot), 0)[0], 0, (tank, slot))
                self.assertEqual(struct.unpack_from("<I", self.record(emu, tank, slot), 0x14)[0], 0, (tank, slot))
            for s in range(26):
                self.assertEqual(self.record(emu, 0, s), F.fish_record(seed=s), s)    # every fish untouched
            data = emu.files.files[SIDECAR]
            self.assertEqual(data[:4], b"FTTA")
            self.assertIn(f"Slot {SLOT}: 4 animal(s) moved", emu.files.log())
            self.assertFalse(emu.files.deleted)

    def test_the_move_is_idempotent(self) -> None:
        body = self.old_save()
        first = self.load(body)
        again = self.load(body, files=first.files.files)          # the same save loaded again (no save between)
        self.assertEqual(self.store(first), self.store(again))
        self.assertEqual(again.files.files[SIDECAR], first.files.files[SIDECAR])
        self.assertEqual(again.files.files[PREVIOUS], first.files.files[SIDECAR])
        state_a = bytes(first.uc.mem_read(first.state, F.STATE_SIZE))
        state_b = bytes(again.uc.mem_read(again.state, F.STATE_SIZE))
        self.assertEqual(state_a, state_b)

    def test_the_records_stay_until_the_file_is_written(self) -> None:
        body = self.old_save()
        emu = self.load(body, fail={SIDECAR.replace(".dat", ".tmp.dat")})
        self.assertNotIn(SIDECAR, emu.files.files)
        for (tank, slot), record in self.OLD_LAYOUT.items():
            self.assertEqual(struct.unpack_from("<I", self.record(emu, tank, slot), 0)[0], 99, (tank, slot))
            self.assertEqual(struct.unpack_from("<I", self.record(emu, tank, slot), 0x14)[0], FTCA)
        self.assertIn("could not be written", emu.files.log())
        # the view never shows a waiting record twice: the fish slots skip it
        self.assertEqual(emu.read32(emu.sym("_pending_any")), 1)
        # the next save writes the file, then clears the records before the game writes its own
        emu.files.fail.clear()
        emu.hook(0x00419100, emu.record("game save", args=1), 4)
        emu.call(emu.sym("_stub_state_save"), SLOT, ecx=emu.state)
        self.assertEqual(emu.calls[-1], ("game save", (SLOT,)))
        self.assertIn(SIDECAR, emu.files.files)
        for (tank, slot) in self.OLD_LAYOUT:
            self.assertEqual(struct.unpack_from("<I", self.record(emu, tank, slot), 0)[0], 0)

    # ------------------------------------------------------------ the file: round trip and the save it belongs to
    def test_round_trip(self) -> None:
        emu = self.emulator()
        for tank, fin in ((0, 30), (0, 31), (1, 32), (2, 22), (2, 30)):
            self.place(emu, tank, animal_record(fin, health=60 + fin, food=10 + fin))
        body = save_body({(0, 0): F.fish_record()})
        emu.uc.mem_write(emu.state + 8, bytes(body))
        emu.hook(0x00419100, emu.record("game save", args=1), 4)
        emu.call(emu.sym("_stub_state_save"), SLOT, ecx=emu.state)
        saved = self.store(emu)
        loaded = self.load(body, files=emu.files.files)
        restored = self.store(loaded)
        for a, b in zip(saved, restored):
            if struct.unpack_from("<i", a, 0x50)[0] in (30, 31, 32):        # filled to 100/100 on load
                a = bytearray(a)
                struct.pack_into("<i", a, 0x3C, 100)
                struct.pack_into("<i", a, 0x44, 100)
                a = bytes(a)
            self.assertEqual(a, b)

    def test_a_file_from_another_save_is_set_aside_not_used(self) -> None:
        emu = self.emulator()
        self.place(emu, 0, animal_record(30))
        body = save_body({(0, 0): F.fish_record()}, money=5000)
        emu.uc.mem_write(emu.state + 8, bytes(body))
        emu.hook(0x00419100, emu.record("game save", args=1), 4)
        emu.call(emu.sym("_stub_state_save"), SLOT, ecx=emu.state)
        restored = save_body({(0, 0): F.fish_record()}, money=4000)          # an older backup of the slot
        struct.pack_into("<i", restored, 0x44 - 8, 3000)                     # fewer minutes played
        loaded = self.load(restored, files=emu.files.files)
        self.assertFalse(any(struct.unpack_from("<I", r, 0)[0] for r in self.store(loaded)))
        names = sorted(loaded.files.files)
        self.assertNotIn(SIDECAR, names)
        self.assertTrue(any("other-save-1" in n for n in names), names)
        self.assertFalse(loaded.files.deleted)
        new_game = save_body({}, money=500)                                   # a new game in the slot
        struct.pack_into("<i", new_game, 0x3C - 8, 0)
        struct.pack_into("<i", new_game, 0x44 - 8, 0)
        self.place(emu, 0, animal_record(31))
        emu.call(emu.sym("_stub_state_save"), SLOT, ecx=emu.state)
        loaded = self.load(new_game, files=emu.files.files)
        self.assertFalse(any(struct.unpack_from("<I", r, 0)[0] for r in self.store(loaded)))

    def test_animals_come_back_after_play_without_ds_store_items(self) -> None:
        emu = self.emulator()
        self.place(emu, 1, animal_record(31))
        body = save_body({(0, 0): F.fish_record()}, money=5000)
        emu.uc.mem_write(emu.state + 8, bytes(body))
        emu.hook(0x00419100, emu.record("game save", args=1), 4)
        emu.call(emu.sym("_stub_state_save"), SLOT, ecx=emu.state)
        later = save_body({(0, 0): F.fish_record()}, money=9000)             # played and saved without it
        struct.pack_into("<i", later, 0x3C - 8, 14)
        struct.pack_into("<i", later, 0x44 - 8, 4000)
        loaded = self.load(later, files=emu.files.files)
        self.assertEqual(struct.unpack_from("<i", self.store(loaded)[5], 0x50)[0], 31)
        self.assertIn("its animals are back", loaded.files.log())

    def test_the_previous_file_serves_a_save_that_did_not_finish(self) -> None:
        emu = self.emulator()
        self.place(emu, 2, animal_record(32))
        body = save_body({(0, 0): F.fish_record()}, money=5000)
        emu.uc.mem_write(emu.state + 8, bytes(body))
        emu.hook(0x00419100, emu.record("game save", args=1), 4)
        emu.call(emu.sym("_stub_state_save"), SLOT, ecx=emu.state)
        emu.write32(emu.state + 0x38C, 6000)                               # played on; saved again,
        emu.call(emu.sym("_stub_state_save"), SLOT, ecx=emu.state)         # but the game's file stayed at 5000
        loaded = self.load(body, files=emu.files.files)
        self.assertEqual(struct.unpack_from("<i", self.store(loaded)[10], 0x50)[0], 32)

    # ------------------------------------------------------------ the effects, against the earlier build
    def effects(self, old: bool, fish_slot: int, animals: list[int], seed: int, eel_home: bool = False):
        emu = self.emulator(patched=not old, old=old, seed=seed)
        fish = F.fish_record(health=60, food=40)
        emu.uc.mem_write(emu.state + FISH + 1 * TANK + fish_slot * RECORD, fish)
        for i, fin in enumerate(animals):
            if old:
                emu.uc.mem_write(emu.state + FISH + 1 * TANK + (26 + i) * RECORD, animal_record(fin))
            else:
                self.place(emu, 1, animal_record(fin))
        address = emu.state + FISH + 1 * TANK + fish_slot * RECORD
        emu.call(emu.sym("_companion_effects"), address, 1)
        lives = emu.call(emu.sym("_eel_save"), address, 1)
        return bytes(emu.uc.mem_read(address, RECORD)), emu.randoms, lives

    def test_every_animals_effect_is_the_earlier_builds_on_every_fish_slot(self) -> None:
        combos = ([30], [31], [22], [32], [30, 31], [22, 31, 30, 32], [30, 30, 30, 31, 31])
        for animals in combos:
            for seed in range(1, 6):
                old = self.effects(True, 0, animals, seed)
                for slot in (0, 20, 21, 29):
                    with self.subTest(animals=animals, seed=seed, slot=slot):
                        self.assertEqual(self.effects(False, slot, animals, seed), old)

    def test_animals_count_only_in_their_own_tank(self) -> None:
        emu = self.emulator()
        self.place(emu, 0, animal_record(30))
        for tank, count in ((0, 1), (1, 0), (2, 0), (3, 0)):
            self.assertEqual(emu.call(emu.sym("_count_in_tank"), emu.state, tank, 30), count)


if __name__ == "__main__":
    unittest.main()
