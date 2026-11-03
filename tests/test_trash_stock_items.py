"""The trash takes chemicals, eggs, medicines and ornaments ("Fix Vanilla Bugs", both games).

The owner (v1.0.25): "I can't trash any chemicals, eggs or decorations in fish tycoon. trashing
chemicals and eggs brings up a message "This must be used directly in a tank"", and "Check plant
tycoon too (do not trash tools)".

Fish Tycoon, stock: a held supply let go goes through the release 0x421B20 to the use 0x420B70.
The use tests only the tank (impl + 0xA8..0xB4); outside it, 0x42165C tests only the isolation
tank (hint 0xC) and otherwise shows hint 0xD, "This must be used directly in a tank." (0x446444,
the hint table at 0x457A04), the trash can (impl + 0x88..0x94) included, and the slot keeps its
item. The ornament drop 0x41F660 tests only the three tank buttons, then settles the ornament
where it was let go (0x41F7BF, 0x41EA10): on the trash can it just rests there. So no medicine,
chemical, egg or ornament could ever be thrown away, in the stock game as in every patched build
(DS Store Items throws away only its own supplies before the use, 0x421B52; Multiple Ornaments
only its copies, at 0x421D43). Fix Vanilla Bugs: the use's outside branch (0x42165C) and the
ornament settle (0x41F7BF) jump to routines in .text's zero tail (0x43F900, 0x43F9A0).

Plant Tycoon, stock: the greenhouse trash 0x424680 sells seeds and deletes plants; a chemical
bottle (held 5-8, the tray's four records) let go on the bin is left in the hand, and a bottle
clicked on the bin with a plant selected asks to delete that plant. The tools (held 1-4) never
reach the trash (0x425FCC, 0x42730D). Fix Vanilla Bugs: the trash, once the bin is hit (0x4246EB),
and the press off the pots (0x4272E5) throw a held bottle away whole, with the bin's sound and no
question. The tools are refused as before.

Everything runs the vanilla executables' own code in Unicorn (tests/store_emulator.py), with the
manifest's bytes for each setting combination; the DLLs are rebuilt from source where they take
part (DS Store Items, Extra Supply Slots, Store Upgrades and Items).
"""

from __future__ import annotations

import struct
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

import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402

FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
STORE_DLL = ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll"
UPGRADES_DLL = ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll"
FIX = "fix_vanilla_bugs"

_BUILT: dict = {}


def _needs(exe):
    ready = E is not None and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn and the vanilla executable")


def _needs_dll(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


def built_exe(game: str, enabled: frozenset[str]) -> Path:
    """The executable the patcher writes for these settings (the manifest's own bytes)."""
    key = (game, enabled)
    if key not in _BUILT:
        vanilla = FISH_EXE if game == "fish" else PLANT_EXE
        if not enabled:
            _BUILT[key] = vanilla
        else:
            records = fish_patcher.active_patch_records(combined.load_manifest(game), set(enabled))
            data, _ = fish_patcher.apply_patch_bytes(vanilla.read_bytes(), records)
            path = Path(tempfile.mkdtemp(prefix="ftfp_trash_")) / f"{game}.exe"
            path.write_bytes(data)
            _BUILT[key] = path
    return _BUILT[key]


def dll(project: str, shipped: Path):
    if project not in _BUILT:
        out = Path(tempfile.mkdtemp(prefix=f"{project}_"))
        _BUILT[project] = E.build_with_map(project, shipped, out)
    return _BUILT[project]


# ================================================================== Fish Tycoon

STATE_SIZE = 0x1E600
FISH, TANK = 0x390, 0x51EC
ORN_BASE, ORN_STRIDE = 0x5208, 0x2C
S_TANK = 0x384
SLOT, REC = 0x2B8, 0x1C                   # supply slot k: item, present, count, icon, cursor, x
NOTHING = 0x63
FOOD = 0x17
TRASH = (650, 541, 689, 600)              # the tank screen's rectangles (0x41CE20-0x41CE88)
ISOLATION = (500, 489, 639, 600)
TANK_RECT = (2, 51, 798, 489)
HINT_TANK_ONLY, HINT_ISOLATION = 0xD, 0xC  # "This must be used directly in a tank.", the isolation tank's
SOUND_TRASH = 4
# Stock items: (item, shelf picture, cursor), as the store writes them (test_supply_slots.STOCK_ITEMS):
# medicines 0-1, chemicals 2-4 (the Unknown Chemical among them), eggs 5-7 and the starter eggs 26.
STOCK_ITEMS = {0: (0xA7, 0xAD), 1: (0xA8, 0xAE), 2: (0xA9, 0xAF), 3: (0x7A, 0x7B), 4: (0xAA, 0xB0),
               5: (0x79, 0x79), 6: (0xAB, 0xAB), 7: (0xAC, 0xAC), 26: (0x79, 0x79)}
NATIVE = {0: 1, 1: 1, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 3, 26: 3}
EXOTIC, RGH, REVIVAL, CLONA, MUTA_FIN, MUTA_BODY = 28, 29, 30, 31, 32, 33
DS_ITEMS = {EXOTIC: (224, 224), RGH: (236, 237), REVIVAL: (239, 240), CLONA: (242, 243), MUTA_FIN: (247, 248),
            MUTA_BODY: (250, 251)}
# Store ornaments: sprite -> its store item (ownership dword state + item * 20 + 0x78).
ORNAMENTS = {177: 16, 178: 17, 179: 18, 181: 19, 180: 20, 182: 21}
SPR_ROCK = 228                            # DS Store Items' eel rock (an ornament it trashes itself)
TRASH_POINTS = ((TRASH[0], TRASH[1]), (TRASH[2], TRASH[3]), (669, 570), (TRASH[0], TRASH[3]))
OFF_TRASH = ((TRASH[0] - 1, 570), (TRASH[2] + 1, 570), (669, TRASH[1] - 1), (300, 560))


def owned(item: int) -> int:
    return item * 20 + 0x78


def maximized_points() -> list[tuple[int, int]]:
    import test_trash_patcher_items as T
    return T.maximized_trash_points()


class FishTank:
    """The tank screen (impl) and the state, the game's own release and drop running on them."""

    def __init__(self, enabled: set[str], store: bool = False, answer_yes: bool = True, current: int = 0) -> None:
        exe = built_exe("fish", frozenset(enabled))
        if store:
            path, symbols = dll("ftfp_ds_store", STORE_DLL)
            self.emu = emu = E.Emulator(exe, path, symbols)
            site = 0x421B52                                                   # as its install writes it
            emu.uc.mem_write(site, b"\xE8" + struct.pack("<i", emu.sym("_stub_supply_drop") - (site + 5)))
            emu.hook_import("GetModuleHandleW", lambda e: 0, 4)
        else:
            self.emu = emu = E.Emulator(exe, None, {})
        emu.uc.mem_map(0, 0x1000)                                             # fs:[0]
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        emu.hook(0x00425120, lambda e: 0x5000, 0)
        emu.hook(0x004251A0, lambda e: emu.calls.append(("sound", (e.arg(0),))) or 0x6000, 4)
        emu.hook(0x0040AE20, emu.record("play"), 4)
        emu.hook(0x004221A0, emu.record("question", args=1), 8)
        emu.hook(0x00401D00, lambda e: 0 if answer_yes else 1, 8)
        emu.hook(0x00422440, lambda e: 0, 0)
        emu.hook(0x0041EA10, emu.record("settle", args=4), 16)               # the ornament's stock finish
        emu.hook(0x0041E9C0, emu.record("place", args=2), 8)
        emu.hook(0x0041E980, emu.record("unview", args=2), 8)
        emu.hook(0x00419C00, emu.record("add ornament", result=1, args=2), 8)
        emu.hook(0x00420BCA, self._used, 0)                                   # the use's four in-tank cases
        for case in (0x00420C4B, 0x00420E3A, 0x00421356):
            emu.hook(case, self._used, 0)
        self.state, self.impl = state, impl = emu.alloc(STATE_SIZE), emu.alloc(0x100)
        for at in range(0, STATE_SIZE, 4):                                   # every field: a pattern
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        emu.write32(state + 0x1E4E8, 0xFFFFFFFF)                              # no fish held
        emu.write32(state + S_TANK, current)
        for k in range(4):                                                    # every slot empty, the food in #1
            self.put(k, None)
        self.put(0, FOOD)
        emu.write32(impl + 0x1C, NOTHING)
        emu.write32(impl + 0x28, NOTHING)
        emu.write32(impl + 0x34, state)
        for offset in (0x3C, 0x44, 0x4C, 0x50):
            emu.write32(impl + offset, emu.alloc(0x40))
        for base, rect in ((0x58, (5000, 5000, 5001, 5001)), (0x68, (5000, 5000, 5001, 5001)),
                           (0x78, (5000, 5000, 5001, 5001)),                  # the tank buttons: out of the way
                           (0x88, TRASH), (0x98, ISOLATION), (0xA8, TANK_RECT)):
            for i, value in enumerate(rect):
                emu.write32(impl + base + 4 * i, value)

    def _used(self, emu) -> int:
        """The use's in-tank case for this slot: recorded, then the use returns as it would."""
        emu.calls.append(("used", (emu.read32(self.impl + 0x1C),)))
        esp = emu.uc.reg_read(X.UC_X86_REG_ESP)                              # "return" to the use's exit
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp - 4)
        emu.write32(esp - 4, 0x0042168A)
        return 0

    # -- the slots
    def put(self, k: int, item: int | None, count: int = 3) -> None:
        if item is None:
            record = struct.pack("<6i", 0, 0, 0, 0, 0, k * 0x30 + 0x1E)
        elif item == FOOD:
            record = struct.pack("<6i", FOOD, 1, 0, 0x78, 0x6E, k * 0x30 + 0x1E)
        else:
            icon, cursor = STOCK_ITEMS.get(item) or DS_ITEMS[item]
            record = struct.pack("<6i", item, 1, count, icon, cursor, k * 0x30 + 0x1E)
        self.emu.uc.mem_write(self.state + SLOT + k * REC, record)

    def slot(self, k: int) -> tuple[int, ...]:
        return struct.unpack("<6i", self.emu.uc.mem_read(self.state + SLOT + k * REC, 24))

    def everything(self) -> bytes:
        return bytes(self.emu.uc.mem_read(self.state, STATE_SIZE))

    def release(self, k: int, x: int, y: int) -> None:
        """A supply from slot k let go at (x, y): the tank screen's release 0x421B20."""
        self.emu.write32(self.impl + 0x1C, k)
        self._run(0x00421B20, x, y)

    # -- ornaments
    def ornament(self, tank: int, k: int) -> int:
        return self.state + ORN_BASE + tank * TANK + k * ORN_STRIDE

    def put_ornament(self, tank: int, k: int, sprite: int) -> bytes:
        r = bytearray(ORN_STRIDE)
        r[0] = 1
        struct.pack_into("<ii", r, 4, 300, 420)
        struct.pack_into("<iii", r, 0x1C, 40, 80, sprite)
        self.emu.uc.mem_write(self.ornament(tank, k), bytes(r))
        return bytes(r)

    def drop_ornament(self, k: int, x: int, y: int) -> None:
        """Ornament k of the tank on screen let go at (x, y): the release 0x421B20 to the drop 0x41F660."""
        self.emu.write32(self.impl + 0x28, k)
        self._run(0x00421B20, x, y)

    def _run(self, address: int, x: int, y: int) -> None:
        self.emu.call(address, x, y, ecx=self.impl)

    @property
    def calls(self) -> list:
        return self.emu.calls

    def labels(self) -> list[str]:
        return [c[0] for c in self.emu.calls]


ALL_STOCK = (0, 1, 2, 3, 4, 5, 6, 7, 26)
FISH_BUILDS = (set(), {"universal_supply_slots"})        # the stock game, and the patcher's slot layout


@_needs(FISH_EXE)
class FishStockSupplyRootCause(unittest.TestCase):
    """Without the fix (vanilla, and Universal supply slots): every stock supply let go on the trash can
    gets "This must be used directly in a tank." and stays."""

    def test_the_trash_shows_the_tank_hint_and_keeps_the_supply(self) -> None:
        for build in FISH_BUILDS:
            for item in ALL_STOCK:
                k = NATIVE[item]
                with self.subTest(build=sorted(build), item=item):
                    tank = FishTank(build)
                    tank.put(k, item)
                    before = tank.everything()
                    tank.release(k, 669, 570)
                    self.assertEqual(tank.everything(), before)
                    self.assertEqual(tank.calls, [("hint", (HINT_TANK_ONLY,))])


@_needs(FISH_EXE)
class FishStockSuppliesInTheTrash(unittest.TestCase):
    """With Fix Vanilla Bugs: the stock supplies go in the trash; nothing else about a release changes."""

    def test_every_stock_supply_on_the_trash_is_thrown_away_whole(self) -> None:
        points = list(TRASH_POINTS) + maximized_points()
        for build in FISH_BUILDS:
            for item in ALL_STOCK:
                for k in sorted({NATIVE[item], 1, 2, 3} if build else {NATIVE[item]}):
                    for count in (1, 3):
                        for x, y in points:
                            with self.subTest(build=sorted(build), item=item, k=k, count=count, at=(x, y)):
                                tank = FishTank(build | {FIX})
                                tank.put(k, item, count)
                                other = 1 + k % 3                             # another slot keeps its own
                                tank.put(other, 4, 2)
                                before = bytearray(tank.everything())
                                tank.release(k, x, y)
                                self.assertEqual(tank.slot(k), (0, 0, 0, 0, 0, k * 0x30 + 0x1E))
                                self.assertEqual(tank.calls, [("sound", (SOUND_TRASH,)), ("play", ())])
                                self.assertEqual(tank.emu.read32(tank.impl + 0x1C), NOTHING)
                                at = SLOT + k * REC
                                before[at:at + 20] = bytes(20)
                                self.assertEqual(tank.everything(), bytes(before))   # nothing else

    def test_off_the_trash_the_hints_are_as_before(self) -> None:
        for build in FISH_BUILDS:
            for item in ALL_STOCK:
                k = NATIVE[item]
                for (x, y), hint in [(p, HINT_TANK_ONLY) for p in OFF_TRASH] + [((560, 550), HINT_ISOLATION)]:
                    with self.subTest(build=sorted(build), item=item, at=(x, y)):
                        results = []
                        for fixed in (False, True):
                            tank = FishTank(build | ({FIX} if fixed else set()))
                            tank.put(k, item)
                            before = tank.everything()
                            tank.release(k, x, y)
                            self.assertEqual(tank.everything(), before)
                            self.assertEqual(tank.calls, [("hint", (hint,))])
                            results.append(tank.calls)
                        self.assertEqual(results[0], results[1])

    def test_used_on_the_tank_exactly_as_before(self) -> None:
        # In the tank the use reaches its in-tank case for the slot, with nothing changed on the way,
        # the same with the setting on and off.
        for build in FISH_BUILDS:
            for item in ALL_STOCK:
                k = NATIVE[item]
                for x, y in ((400, 300), (TANK_RECT[0], TANK_RECT[1]), (TANK_RECT[2], TANK_RECT[3])):
                    with self.subTest(build=sorted(build), item=item, at=(x, y)):
                        seen = []
                        for fixed in (False, True):
                            tank = FishTank(build | ({FIX} if fixed else set()))
                            tank.put(k, item)
                            before = tank.everything()
                            tank.release(k, x, y)
                            self.assertEqual(tank.calls, [("used", (k,))])
                            seen.append((tank.calls, tank.everything() == before))
                        self.assertEqual(seen[0], seen[1])

    def test_the_fish_food_is_never_thrown_away(self) -> None:
        for build in FISH_BUILDS:
            for x, y in TRASH_POINTS:
                tank = FishTank(build | {FIX})
                before = tank.everything()
                tank.release(0, x, y)
                self.assertEqual(tank.everything(), before)
                self.assertEqual(tank.calls, [("hint", (HINT_TANK_ONLY,))])         # as stock

    def test_the_tank_on_screen_does_not_matter(self) -> None:
        for current in (0, 1, 2):
            tank = FishTank({FIX}, current=current)
            tank.put(2, 3)
            before = tank.everything()
            tank.release(2, 669, 570)
            after = tank.everything()
            self.assertEqual(after[FISH:FISH + 4 * TANK], before[FISH:FISH + 4 * TANK])
            self.assertEqual(tank.slot(2)[:5], (0, 0, 0, 0, 0))


@_needs_dll(FISH_EXE)
class FishWithDsStoreItems(unittest.TestCase):
    """DS Store Items beside it (its trash at 0x421B52 runs first): its own supplies go as before,
    the stock ones now go too; before the fix the stock ones stayed with the hint."""

    def test_every_supply_in_the_trash(self) -> None:
        for build in FISH_BUILDS:
            for item in ALL_STOCK + tuple(DS_ITEMS):
                k = NATIVE.get(item, 3 if item == EXOTIC else 2)
                with self.subTest(build=sorted(build), item=item):
                    for fixed in (False, True):
                        tank = FishTank(build | ({FIX} if fixed else set()), store=True)
                        tank.put(k, item, 3)
                        before = tank.everything()
                        tank.release(k, 669, 570)
                        if fixed or item in DS_ITEMS:
                            self.assertEqual(tank.slot(k)[:5], (0, 0, 0, 0, 0), fixed)
                            self.assertIn(("sound", (SOUND_TRASH,)), tank.calls)
                            self.assertNotIn("hint", tank.labels())
                        else:
                            self.assertEqual(tank.everything(), before)
                            self.assertEqual(tank.calls, [("hint", (HINT_TANK_ONLY,))])


@_needs_dll(FISH_EXE)
class FishExtraSupplySlots(unittest.TestCase):
    """Extra Supply Slots (its release hook lends an extra slot to its stock slot; the game's code does
    the rest): a stock supply from page 2 or 3 in the trash, before and after the fix."""

    def rig(self, universal: bool, fixed: bool):
        import test_supply_slots as S
        enabled = ({"universal_supply_slots"} if universal else set()) | ({FIX} if fixed else set())
        return S, S.Rig(exe=built_exe("fish", frozenset(enabled)))

    def test_a_stock_supply_from_an_extra_slot(self) -> None:
        trash = ((TRASH[0] + TRASH[2]) // 2, (TRASH[1] + TRASH[3]) // 2)
        for universal in (False, True):
            for item in ALL_STOCK:
                for e in (0, 4, 6):
                    with self.subTest(universal=universal, item=item, extra=e):
                        for fixed in (False, True):
                            S, rig = self.rig(universal, fixed)
                            rig.put_extra(e, S.record(item, 3))
                            before = S.slots_view(rig)
                            rig.pick_extra(e)
                            rig.let_go(*trash)
                            after = S.slots_view(rig)
                            if fixed:
                                self.assertEqual(rig.extra(e), S.EMPTY, "thrown away whole")
                                self.assertEqual(after[:4], before[:4], "the stock slots keep their own")
                                self.assertIn(("sound", 4), rig.calls)
                                self.assertNotIn(("hint", 0xD), rig.calls)
                            else:
                                self.assertEqual(after, before)
                                self.assertIn(("hint", 0xD), rig.calls)
                            self.assertEqual(rig.held(), NOTHING)
                            self.assertEqual(rig.r("_lift_e"), -1)

    def test_used_on_the_tank_from_an_extra_slot_as_before(self) -> None:
        import test_supply_slots as S
        for universal in (False, True):
            for item in (0, 3, 5):
                with self.subTest(universal=universal, item=item):
                    states = []
                    for fixed in (False, True):
                        S_, rig = self.rig(universal, fixed)
                        S.UseRig.prepare(rig)
                        rig.put_extra(2, S.record(item, 3))
                        rig.pick_extra(2)
                        rig.let_go(*S.IN_TANK)
                        states.append((rig.everything(), rig.extra(2), [c for c in rig.calls if c[0] != "cell"]))
                    self.assertEqual(states[0], states[1])


@_needs(FISH_EXE)
class FishOrnamentsInTheTrash(unittest.TestCase):
    """The ornament drop 0x41F660: stock, an ornament on the trash can rests there; fixed, the store
    ornaments go after "Delete this fish?" and can be bought again."""

    def test_stock_the_ornament_just_rests_on_the_trash(self) -> None:
        for sprite in ORNAMENTS:
            tank = FishTank(set())
            record = tank.put_ornament(0, 2, sprite)
            tank.emu.write32(tank.state + owned(ORNAMENTS[sprite]), 1)
            tank.drop_ornament(2, 669, 570)
            self.assertEqual(tank.calls, [("settle", (669, 570, 0, 2))])
            self.assertEqual(bytes(tank.emu.uc.mem_read(tank.ornament(0, 2), ORN_STRIDE)), record)

    def test_every_store_ornament_goes_after_the_question(self) -> None:
        points = list(TRASH_POINTS) + maximized_points()[:3]
        for sprite, item in ORNAMENTS.items():
            for current in (0, 1, 2):
                for k in (0, 5):
                    for x, y in points:
                        with self.subTest(sprite=sprite, tank=current, k=k, at=(x, y)):
                            tank = FishTank({FIX}, current=current)
                            tank.put_ornament(current, k, sprite)
                            tank.put_ornament(current, 3 if k != 3 else 4, 182 if sprite != 182 else 177)
                            tank.emu.write32(tank.state + owned(item), 1)
                            before = bytearray(tank.everything())
                            tank.drop_ornament(k, x, y)
                            self.assertEqual(tank.calls, [("question", (0xAC,)), ("sound", (SOUND_TRASH,)),
                                                          ("play", ())])
                            self.assertEqual(tank.emu.read32(tank.impl + 0x28), NOTHING)
                            at = ORN_BASE + current * TANK + k * ORN_STRIDE
                            before[at:at + ORN_STRIDE] = bytes(ORN_STRIDE)
                            struct.pack_into("<i", before, owned(item), 0)        # buyable again
                            self.assertEqual(tank.everything(), bytes(before))     # nothing else

    def test_no_or_off_the_trash_it_settles_as_before(self) -> None:
        cases = [((669, 570), False)] + [(p, True) for p in OFF_TRASH + ((400, 300),)]
        for (x, y), yes in cases:
            with self.subTest(at=(x, y), yes=yes):
                tank = FishTank({FIX}, answer_yes=yes)
                record = tank.put_ornament(0, 1, 179)
                tank.emu.write32(tank.state + owned(18), 1)
                before = tank.everything()
                tank.drop_ornament(1, x, y)
                self.assertEqual(tank.labels()[-1], "settle")
                self.assertEqual(tank.calls[-1], ("settle", (x, y, 0, 1)))
                self.assertEqual(tank.everything(), before)
                self.assertEqual(bytes(tank.emu.uc.mem_read(tank.ornament(0, 1), ORN_STRIDE)), record)

    def test_the_eel_rock_is_left_to_ds_store_items(self) -> None:
        tank = FishTank({FIX})
        tank.put_ornament(0, 0, SPR_ROCK)
        before = tank.everything()
        tank.drop_ornament(0, 669, 570)
        self.assertEqual(tank.calls, [("settle", (669, 570, 0, 0))])
        self.assertEqual(tank.everything(), before)


# ================================================================== Plant Tycoon

PLANT_STATE = 0x64000
HELD, SELECTED = 0x56C, 0x63E58
CHEM_TRAY = 0x53F84                        # 4 bottles: present (byte), chemical id, doses; 0xC each
POT0, POT_SIZE = 0x2188, 0x5600
P_TRASH = (0xAE, 0x20D, 0xAE + 0x38, 0x20D + 0x4B)       # left, top, right, bottom (inclusive, 0x435FF0)
P_POINTS = ((P_TRASH[0], P_TRASH[1]), (P_TRASH[2], P_TRASH[3]), (0xC0, 0x230), (0xE0, 0x250))
P_OFF = ((P_TRASH[0] - 1, 0x230), (P_TRASH[2] + 1, 0x230), (0xC0, P_TRASH[1] - 1), (400, 300))
TRASH_BIN = 0x23                                          # close_trash_bin.ogg
STOCK_CHEMICALS = range(27, 36)                           # the store's nine chemicals (fertilizers among them)
NEW_CHEMICALS = (36, 37, 38, 39, 48, 49)                  # Store Upgrades and Items'
TOOLS = (1, 2, 3, 4)                                      # the watering can and the other rack tools


class Greenhouse:
    """The greenhouse's mouse-up (0x425FB8 on) and press off the pots (0x4272DC on), with the stock
    trash (0x424680) and put-back (0x4244C0); Store Upgrades and Items' stubs when asked."""

    def __init__(self, enabled: set[str], upgrades: bool = False, answer_yes: bool = False) -> None:
        exe = built_exe("plant", frozenset(enabled))
        if upgrades:
            path, symbols = dll("ftfp_plant_upgrades", UPGRADES_DLL)
            self.emu = emu = E.Emulator(exe, path, symbols)
            emu.uc.mem_write(0x425FF2, b"\xE8" + struct.pack("<i", emu.sym("_stub_trash_drop") - 0x425FF7))
            emu.uc.mem_write(0x4272DC, b"\xE9" + struct.pack("<i", emu.sym("_stub_trash_press") - 0x4272E1)
                             + b"\x90" * 4)
        else:
            self.emu = emu = E.Emulator(exe, None, {})
        emu.uc.mem_map(0, 0x1000)
        emu.hook(0x0044A580, emu.record("sound", args=1), 4)
        emu.hook(0x00421190, emu.record("fly back", args=8), 0x20)          # the put-back's animation
        emu.hook(0x0042F690, emu.record("pot emptied", args=1), 4)
        emu.hook(0x0042AB50, emu.record("question", args=5), 0x14)          # "Delete this plant?"
        emu.hook(0x00401C90, lambda e: 0, 8)
        emu.hook(0x0042AB10, lambda e: 0 if answer_yes else 1, 0)
        emu.hook(0x0042AAA0, lambda e: 0, 0)
        emu.hook(0x0041D420, emu.record("seed out of the tray", args=1), 4)
        emu.hook(0x0041ED70, emu.record("cash", args=1), 4)
        emu.hook(0x004033B0, lambda e: 0, 0)
        emu.hook(0x0041B190, emu.record("tip", args=2), 8)
        self.state, self.gh = state, gh = emu.alloc(PLANT_STATE), emu.alloc(0x200)
        for at in range(0, PLANT_STATE, 4):
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        for k in range(4):
            emu.uc.mem_write(state + CHEM_TRAY + k * 0xC, bytes(0xC))
        emu.write32(state + SELECTED, 0x63)
        emu.write32(gh + 0x68, state)
        for offset in (0x60, 0x6C, 0x70, 0x74, 0x80, 0x84, 0x8C):
            emu.write32(gh + offset, emu.alloc(0x40))
        emu.write8(gh + 0x105, 1)                                            # dragging
        emu.write32(gh + 0x144, 0)

    def bottle(self, k: int, chemical: int, doses: int) -> None:
        self.emu.uc.mem_write(self.state + CHEM_TRAY + k * 0xC, struct.pack("<B3xii", 1, chemical, doses))

    def tray(self) -> list[tuple[int, int, int]]:
        return [struct.unpack("<B3xii", self.emu.uc.mem_read(self.state + CHEM_TRAY + k * 0xC, 0xC))
                for k in range(4)]

    def select_plant(self, k: int = 7) -> None:
        pot = self.state + POT0 + k * POT_SIZE
        self.emu.write32(self.state + SELECTED, k)
        self.emu.write32(pot + 0x1C, 1)                    # planted
        self.emu.write32(pot + 0x24, 60)                   # alive
        self.emu.write32(pot + 0x4C, 3)

    def release(self, held: int, x: int, y: int) -> None:
        """Let go off the pots (0x425FB8 to its end, 0x426019)."""
        emu = self.emu
        emu.write32(self.state + HELD, held)
        esp = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.mem_write(esp, bytes(0x100))
        emu.write32(esp + 0xAC, x)
        emu.write32(esp + 0xB0, y)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_EBP, self.gh)
        emu.uc.emu_start(0x00425FB8, 0x00426019, count=200_000)

    def press(self, held: int, x: int, y: int) -> None:
        """A click off the pots (0x4272DC to the press handler's return)."""
        emu = self.emu
        emu.write32(self.state + HELD, held)
        esp = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.mem_write(esp, bytes(0x40))
        emu.write32(esp + 0x1C, E.RETURN)
        emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(X.UC_X86_REG_ESI, self.gh)
        emu.uc.reg_write(X.UC_X86_REG_EBX, x)
        emu.uc.reg_write(X.UC_X86_REG_EBP, y)
        emu.uc.emu_start(0x004272DC, E.RETURN, count=200_000)

    def everything(self) -> bytes:
        return bytes(self.emu.uc.mem_read(self.state, PLANT_STATE)) + bytes(self.emu.uc.mem_read(self.gh, 0x200))

    @property
    def calls(self) -> list:
        return self.emu.calls

    def labels(self) -> list[str]:
        return [c[0] for c in self.emu.calls]


def _thrown_away(test, gh: Greenhouse, before: bytes, slot: int) -> None:
    after = bytearray(before)
    after[CHEM_TRAY + slot * 0xC] = 0                                     # the bottle, every dose
    struct.pack_into("<i", after, HELD, 0)                                # nothing held
    after[PLANT_STATE + 0x105] = 0                                        # not dragging
    test.assertEqual(gh.everything(), bytes(after))
    test.assertIn(("sound", (TRASH_BIN,)), gh.calls)
    for label in ("question", "pot emptied", "fly back"):
        test.assertNotIn(label, gh.labels())


@_needs(PLANT_EXE)
class PlantRootCause(unittest.TestCase):
    """Without the fix: a stock bottle let go on the bin stays in the hand; clicked on the bin with a
    plant selected, the game asks to delete that plant instead."""

    def test_stock_keeps_the_bottle(self) -> None:
        for chemical in STOCK_CHEMICALS:
            gh = Greenhouse(set())
            gh.bottle(1, chemical, 2)
            gh.emu.write32(gh.state + HELD, 6)
            before = gh.everything()
            gh.release(6, 0xC0, 0x230)
            self.assertEqual(gh.everything()[:PLANT_STATE], before[:PLANT_STATE], chemical)
            self.assertNotIn(("sound", (TRASH_BIN,)), gh.calls)
        gh = Greenhouse(set())
        gh.select_plant()
        gh.bottle(1, 30, 2)
        gh.press(6, 0xE0, 0x230)
        self.assertEqual([c[1][0] for c in gh.calls if c[0] == "question"], [0x10A])     # "Delete this plant?"
        self.assertEqual(gh.tray()[1], (1, 30, 2))


@_needs(PLANT_EXE)
class PlantChemicalsInTheTrash(unittest.TestCase):
    def test_a_bottle_let_go_on_the_bin_is_thrown_away(self) -> None:
        for chemical in STOCK_CHEMICALS:
            for slot in range(4):
                for selected in (False, True):
                    for x, y in P_POINTS:
                        with self.subTest(chemical=chemical, slot=slot, selected=selected, at=(x, y)):
                            gh = Greenhouse({FIX}, answer_yes=True)
                            if selected:
                                gh.select_plant()
                            gh.bottle(slot, chemical, 3)
                            gh.bottle((slot + 1) % 4, chemical, 2)            # another bottle stays
                            gh.emu.write32(gh.state + HELD, 5 + slot)
                            before = gh.everything()
                            gh.release(5 + slot, x, y)
                            _thrown_away(self, gh, before, slot)
                            self.assertEqual(gh.tray()[(slot + 1) % 4], (1, chemical, 2))

    def test_a_bottle_clicked_on_the_bin_is_thrown_away_and_no_plant_is_touched(self) -> None:
        for chemical in STOCK_CHEMICALS:
            for selected in (False, True):
                for x, y in P_POINTS:
                    with self.subTest(chemical=chemical, selected=selected, at=(x, y)):
                        gh = Greenhouse({FIX}, answer_yes=True)
                        if selected:
                            gh.select_plant()
                        gh.bottle(2, chemical, 1)
                        gh.emu.write32(gh.state + HELD, 7)
                        before = gh.everything()
                        gh.press(7, x, y)
                        _thrown_away(self, gh, before, 2)

    def test_off_the_bin_as_before(self) -> None:
        for x, y in P_OFF:
            for selected in (False, True):
                results = []
                for enabled in (set(), {FIX}):
                    for action in ("release", "press"):
                        gh = Greenhouse(enabled)
                        if selected:
                            gh.select_plant()
                        gh.bottle(0, 30, 3)
                        getattr(gh, action)(5, x, y)
                        results.append((action, gh.everything(), gh.calls))
                self.assertEqual(results[:2], results[2:], (x, y, selected))

    def test_the_tools_are_refused(self) -> None:
        # Held 1-4 never reach the bin: let go there a tool stays in the hand, clicked there it goes
        # back to the rack (the stock put-back) or, with a plant selected, as stock; exactly as without
        # the setting, and never thrown away.
        for tool in TOOLS:
            for selected in (False, True):
                for x, y in P_POINTS:
                    for action in ("release", "press"):
                        with self.subTest(tool=tool, selected=selected, at=(x, y), action=action):
                            seen = []
                            for enabled in (set(), {FIX}):
                                gh = Greenhouse(enabled, answer_yes=True)
                                if selected:
                                    gh.select_plant()
                                gh.bottle(0, 30, 3)
                                gh.emu.write32(gh.state + HELD, tool)
                                getattr(gh, action)(tool, x, y)
                                self.assertEqual(gh.tray()[0], (1, 30, 3))
                                for label in ("question", "pot emptied", "sound"):
                                    self.assertNotIn(label, gh.labels())
                                if action == "release":
                                    self.assertEqual(gh.emu.read32(gh.state + HELD), tool)   # still in the hand
                                seen.append((gh.everything(), gh.calls))
                            self.assertEqual(seen[0], seen[1])

    def test_seeds_and_plants_as_before(self) -> None:
        for enabled in (set(), {FIX}):
            gh = Greenhouse(enabled)
            record = gh.state + 0x52A20 + 10 * 36
            gh.emu.write32(record + 0x20, 15)
            gh.release(10, 0xC0, 0x230)
            self.assertIn(("seed out of the tray", (record,)), gh.calls)
            self.assertIn(("cash", (15,)), gh.calls)
            self.assertEqual(gh.emu.read32(gh.state + HELD), 0)
            gh = Greenhouse(enabled, answer_yes=False)
            gh.select_plant()
            gh.press(0, 0xC0, 0x230)                                           # nothing held: the plant
            self.assertEqual([c[1][0] for c in gh.calls if c[0] == "question"], [0x10A], enabled)


@_needs_dll(PLANT_EXE)
class PlantWithStoreUpgrades(unittest.TestCase):
    """Store Upgrades and Items' stubs run first: its chemicals go as before, the stock ones now too."""

    def test_every_chemical(self) -> None:
        for chemical in tuple(STOCK_CHEMICALS) + NEW_CHEMICALS:
            for action in ("release", "press"):
                with self.subTest(chemical=chemical, action=action):
                    gh = Greenhouse({FIX}, upgrades=True)
                    gh.select_plant()
                    gh.bottle(3, chemical, 2)
                    getattr(gh, action)(8, 0xC0, 0x230)
                    self.assertEqual(gh.tray()[3][0], 0)
                    self.assertEqual(gh.emu.read32(gh.state + HELD), 0)
                    self.assertIn(("sound", (TRASH_BIN,)), gh.calls)
                    self.assertNotIn("question", gh.labels())


if __name__ == "__main__":
    unittest.main()
