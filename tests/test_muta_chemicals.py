"""Muta-Fin, Muta-Body (Fish Tycoon) and Muta-Flower, Muta-Foliage (Plant Tycoon).

Fish Tycoon (DS Store Items, the Upgrades page): Muta-Fin (item 32) and Muta-Body (item 33), $2,500
for 3 doses, chemicals for supply slot #3. A dose is the stock Unknown Chemical's (item 4,
0x420E93-0x4210ED) for one part only: the same fish (live, health not 0, not a seahorse-type record,
any age, the tank on screen, over the stock loop's records), the same 26.03% each, the same step,
always the fin or always the body.

Plant Tycoon (Store Upgrades and Items, the Upgrades view): Muta-Flower (chemical 48) and
Muta-Foliage (49), $2,500 for 3 doses. A dose is the stock Mutation Liquid's (chemical 34, the case
at 0x426EF0) with its first Random(2) left out: the flower branch (0x42FAB2) or the foliage branch
(0x42FAF5) of 0x42FA80 itself, then the rest of the Mutation Liquid's case from 0x426EFA (discovery,
the encyclopedia, the sparkles).

The emulation tests run the DLLs' own code and the vanilla executables' code in Unicorn
(tests/store_emulator.py): each Muta dose is compared, fish for fish and byte for byte, with the
stock chemical's run with its part roll forced, over many seeds of the game's own rand(); with DS
Exclusive Fish's own step (its DLL mapped beside the store's) for the DS genes; with Unused Flowers'
bound rewrite for the new flowers.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

import tycoon_fix_patcher as combined  # noqa: E402

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

FISH_EXE = (E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe") if E else None
PLANT_EXE = (E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe") if E else None
STORE_DLL = ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll"
DS_DLL = ROOT / "assets" / "fish_tycoon_ds" / "DS Exclusive Fish.dll"
PLANT_DLL = ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll"
FISH_IMAGES = ROOT / "assets" / "fish_tycoon_ds_store" / "Images"
PLANT_SHEET = ROOT / "assets" / "plant_tycoon_upgrades" / "Images" / "Chemicals_Grid_upgrades.png"

UNKNOWN, MUTA_FIN, MUTA_BODY = 4, 32, 33
MUTA_FLOWER, MUTA_FOLIAGE = 48, 49
SPR = {MUTA_FIN: (246, 247, 248), MUTA_BODY: (249, 250, 251)}        # store picture, shelf, cursor
CELLS = {MUTA_FIN: (450, 200), MUTA_BODY: (542, 200)}
S_TANK, S_MONEY, S_SPENT = 0x384, 0x38C, 0x24
SLOT3 = 0x2B8 + 2 * 0x1C
FISH, TANK, REC = 0x390, 0x51EC, 0x288
F_LIVE, F_AGE, F_HEALTH, F_BODY, F_FIN = 0x00, 0x0C, 0x3C, 0x4C, 0x50
PLANT_STATE = 0x60000
POT0, POT_SIZE = 0x2188, 0x5600
P_FOLIAGE, P_FLOWER = 0x4C, 0x50

# The Unknown Chemical's Random(100) calls, by their return addresses.
UC_SELECT, UC_PART, UC_BODY_STEP, UC_FIN_STEP = 0x420EE0, 0x420EF3, 0x420F0A, 0x420F36
MUTATION_GENE_ROLL = 0x42FAAB                     # 0x42FA80's first Random(2): flower or foliage


class Rand:
    """The game's Random(n): MSVC rand() % n (0x403240 Fish, 0x4033B0 Plant)."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF

    def rand(self) -> int:
        self.state = (self.state * 214013 + 2531011) & 0xFFFFFFFF
        return (self.state >> 16) & 0x7FFF

    def __call__(self, n: int) -> int:
        return self.rand() % n if n > 0 else 0


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return struct.unpack(">II", data[16:24])


def map_relocated(emu, dll: Path, delta: int) -> int:
    """Map a DLL at its preferred base + delta beside the one the emulator holds, its base
    relocations applied (DS Exclusive Fish and DS Store Items share a preferred base)."""
    data = dll.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    base, size, sections, _ = E.pe_image(data)
    reloc_rva, reloc_size = struct.unpack_from("<II", data, pe + 24 + 96 + 5 * 8)
    image = bytearray((size + 0xFFF) & ~0xFFF)
    image[:0x1000] = data[:0x1000]
    for rva, raw, raw_size in sections:
        image[rva:rva + raw_size] = data[raw:raw + raw_size]
    at = reloc_rva
    while at < reloc_rva + reloc_size:
        page, block = struct.unpack_from("<II", image, at)
        if block == 0:
            break
        for k in range((block - 8) // 2):
            entry = struct.unpack_from("<H", image, at + 8 + 2 * k)[0]
            if entry >> 12 == 3:                                         # IMAGE_REL_BASED_HIGHLOW
                spot = page + (entry & 0xFFF)
                struct.pack_into("<I", image, spot, (struct.unpack_from("<I", image, spot)[0] + delta) & 0xFFFFFFFF)
        at += block
    emu.uc.mem_map(base + delta, len(image))
    emu.uc.mem_write(base + delta, bytes(image))
    return base + delta


# ================================================================== the art and the pins

class ArtTests(unittest.TestCase):
    def test_the_fish_art_is_pinned_with_the_store(self) -> None:
        store = combined.patch_settings("fish")["ds_store"]
        destinations = {f["destination"] for f in store["companion"]["files"]}
        for name, size in (("ITEM_MUTA_FIN.png", (48, 65)), ("TOOL_MUTA_FIN.png", (24, 35)),
                           ("TOOL_dropper_MUTA_FIN.png", (21, 21)), ("ITEM_MUTA_BODY.png", (48, 65)),
                           ("TOOL_MUTA_BODY.png", (24, 35)), ("TOOL_dropper_MUTA_BODY.png", (21, 21))):
            self.assertIn(f"Images/{name}", destinations)
            self.assertEqual(png_size(FISH_IMAGES / name), size, name)
        for text in ("Muta-Fin ($2,500, 3 doses)", "Muta-Body ($2,500, 3 doses)"):
            self.assertIn(text, store["description"])
        free = combined.patch_settings("fish")["free_upgrades"]["description"]
        self.assertIn("Muta-Fin ($2,500), Muta-Body ($2,500)", free)

    def test_the_plant_art_and_texts_are_pinned(self) -> None:
        upgrades = combined.patch_settings("plant")["plant_upgrades"]
        self.assertIn("Images/Chemicals_Grid_upgrades.png", {f["destination"] for f in upgrades["companion"]["files"]})
        for text in ("Muta-Flower", "Muta-Foliage", "$2,500"):
            self.assertIn(text, upgrades["description"])
        self.assertEqual(png_size(PLANT_SHEET), (140, 23 * 70))       # rows 21 and 22: chemicals 48 and 49
        free = combined.patch_settings("plant")["free_upgrades"]["description"]
        self.assertIn("Muta-Flower ($2,500), Muta-Foliage ($2,500)", free)

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "needs Pillow")
    def test_the_icons_match_their_neighbours(self) -> None:
        from PIL import Image
        height = lambda path: (lambda b: b[3] - b[1])(Image.open(path).convert("RGBA").getchannel("A").getbbox())
        for name in ("ITEM_MUTA_FIN.png", "ITEM_MUTA_BODY.png"):
            self.assertEqual(height(FISH_IMAGES / name), 57, name)           # the stock Growth Hormone's 57
        for name in ("TOOL_MUTA_FIN.png", "TOOL_MUTA_BODY.png"):
            self.assertEqual(height(FISH_IMAGES / name), 31, name)
        sheet = Image.open(PLANT_SHEET).convert("RGBA")
        box = lambda row, column: sheet.crop((column * 70, row * 70, column * 70 + 70, row * 70 + 70)).getchannel("A").getbbox()
        for row in (21, 22):                                             # the stock Mutation Liquid's own boxes
            self.assertEqual(box(row, 0), box(7, 0), row)
            self.assertEqual(box(row, 1), box(7, 1), row)

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "needs Pillow")
    def test_four_distinct_colours(self) -> None:
        import colorsys
        import numpy as np
        from PIL import Image

        def hue(image) -> float:
            a = np.asarray(image.convert("RGBA")).astype(float) / 255
            hs = [colorsys.rgb_to_hsv(*p[:3]) for p in a.reshape(-1, 4) if p[3] > 0.5]
            return float(np.median([h for h, s, v in hs if s > 0.4]))
        sheet = Image.open(PLANT_SHEET).convert("RGBA")
        hues = [hue(Image.open(FISH_IMAGES / "ITEM_MUTA_FIN.png")), hue(Image.open(FISH_IMAGES / "ITEM_MUTA_BODY.png")),
                hue(sheet.crop((0, 21 * 70, 70, 22 * 70))), hue(sheet.crop((0, 22 * 70, 70, 23 * 70)))]
        for i in range(4):
            for j in range(i + 1, 4):
                d = abs(hues[i] - hues[j])
                self.assertGreater(min(d, 1 - d) * 360, 40, (i, j, hues))

    @unittest.skipUnless(E is not None and FISH_EXE is not None and FISH_EXE.is_file()
                         and PLANT_EXE is not None and PLANT_EXE.is_file(), "needs the vanilla games")
    def test_the_art_is_rebuilt_by_its_pinned_scripts(self) -> None:
        import numpy as np
        from PIL import Image
        import build_muta_assets
        import build_plant_upgrades_assets
        built = build_muta_assets.fish_pictures(FISH_EXE.parent)
        self.assertEqual(set(built), {f"{k}_{n}.png" for k in ("ITEM", "TOOL", "TOOL_dropper") for n in ("MUTA_FIN", "MUTA_BODY")})
        for name, image in built.items():
            committed = np.asarray(Image.open(FISH_IMAGES / name).convert("RGBA"))
            self.assertTrue((np.asarray(image) == committed).all(), name)
        sheet = build_plant_upgrades_assets.formula_bottle(PLANT_EXE.parent / "Images")
        self.assertTrue((np.asarray(sheet) == np.asarray(Image.open(PLANT_SHEET).convert("RGBA"))).all())
        stock = Image.open(PLANT_EXE.parent / "Images" / "Chemicals_Grid.png").convert("RGBA")
        for name, cells in build_muta_assets.plant_cells(stock).items():
            row = build_muta_assets.MUTA_ROWS[name]
            for column, cell in enumerate(cells):
                part = sheet.crop((column * 70, row * 70, column * 70 + 70, row * 70 + 70))
                self.assertTrue((np.asarray(cell) == np.asarray(part)).all(), (name, column))
        for preview in ("muta-chemicals-fish.png", "muta-chemicals-plant.png", "muta-chemicals-icons.png"):
            self.assertTrue((ROOT / "docs" / "images" / preview).is_file())


def _needs(exe):
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


# ================================================================== Fish Tycoon

@_needs(FISH_EXE)
class FishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        store, ds = Path(cls.tmp.name) / "store", Path(cls.tmp.name) / "ds"
        store.mkdir()
        ds.mkdir()
        cls.dll, cls.symbols = E.build_with_map("ftfp_ds_store", STORE_DLL, store)
        _, cls.ds_symbols = E.build_with_map("ftfp_ds_fish", DS_DLL, ds)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ the store
    def store(self, money: int, free: bool = False, universal: bool = False, german: bool = False):
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        emu.hook_import("GetTickCount", lambda e: 0, 0)
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        emu.hook(0x004221A0, emu.record("dialog", args=1), 8)
        emu.hook(0x00401D00, emu.record("run", 0), 8)                            # Yes
        emu.hook(0x00422440, emu.record("free"), 0)
        emu.hook(0x00425120, emu.record("sounds"), 0)
        emu.hook(0x004251A0, emu.record("sound"), 4)
        table, price = emu.alloc(16), emu.text("Price:")
        emu.hook(0x00427060, lambda e: table, 0)
        emu.hook(0x00427050, lambda e: price, 4)
        emu.hook(0x0041BE70, lambda e: 1, 4)
        emu.hook(0x00408A40, emu.record("draw"), 12)
        emu.hook(0x00408AE0, emu.record("draw"), 24)
        emu.hook(0x00408B80, lambda e: (e.calls.append(("text", e.cstring(e.arg(0)).decode("latin-1"))), 0)[1], 20)
        if german:
            language = emu.alloc(4)
            emu.write32(language, 1)
            emu.write32(0x0045B314, language)
        state, impl, scene = emu.alloc(0x40000), emu.alloc(0x100), emu.alloc(0x100)
        emu.write32(scene + 8, impl)
        emu.write32(impl + 0x10, state)
        emu.write32(impl + 0x0C, emu.alloc(0x40))
        emu.write32(state + S_MONEY, money)
        for name, on in (("_free_on", free), ("_page_upgrades", 1), ("_exotic_any_slot", universal)):
            emu.write32(emu.sym(name), int(on))
        emu.state, emu.scene = state, scene
        return emu

    def select(self, emu, item: int) -> None:
        emu.call(emu.sym("@on_mouse@20"), 3, *CELLS[item], ecx=emu.scene)

    def shown(self, emu, item: int) -> list[str]:
        self.select(emu, item)
        emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
        return [c[1] for c in emu.calls if c[0] == "text"]

    def slot(self, emu, k: int = 2) -> tuple[int, ...]:
        return struct.unpack("<6i", emu.uc.mem_read(emu.state + 0x2B8 + k * 0x1C, 24))

    def test_names_texts_and_prices(self) -> None:
        for item, name, english, german in (
                (MUTA_FIN, "Muta-Fin", "Mutates the fins of fish. Contains 3 doses.",
                 "Ver\xe4ndert die Flossen von Fischen. Reicht f\xfcr 3 Behandlungen."),
                (MUTA_BODY, "Muta-Body", "Mutates the bodies of fish. Contains 3 doses.",
                 "Ver\xe4ndert die K\xf6rper von Fischen. Reicht f\xfcr 3 Behandlungen.")):
            texts = self.shown(self.store(0), item)
            self.assertIn(name, texts)
            self.assertIn(english, [t.replace("\n", " ") for t in texts])          # the owner's exact words
            self.assertEqual([t for t in texts if t.startswith("Price:")][-1], "Price:  $2500")
            self.assertEqual([t for t in self.shown(self.store(0, free=True), item) if t.startswith("Price:")][-1],
                             "Price:  $0")                                       # Free upgrades / Everything is Free
            texts = self.shown(self.store(0, german=True), item)
            self.assertIn(german, [t.replace("\n", " ") for t in texts])

    def test_bought_into_slot_3_with_3_doses(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            emu = self.store(2507)
            self.select(emu, item)
            emu.call(emu.sym("_buy"), emu.scene)
            self.assertEqual(self.slot(emu), (item, 1, 3, SPR[item][1], SPR[item][2], 2 * 0x30 + 0x1E))
            self.assertEqual((emu.read32(emu.state + S_MONEY), emu.read32(emu.state + S_SPENT)), (7, 2500))
            emu = self.store(2499)
            self.select(emu, item)
            emu.call(emu.sym("_buy"), emu.scene)
            self.assertIn(("hint", (2,)), emu.calls)                             # can't afford
            emu = self.store(0, free=True)
            self.select(emu, item)
            emu.call(emu.sym("_buy"), emu.scene)
            self.assertEqual(self.slot(emu)[:3], (item, 1, 3))
            self.assertEqual(emu.read32(emu.state + S_SPENT), 0)
            emu = self.store(10000, universal=True)                              # a stack gains 3 doses a purchase
            for _ in range(2):
                self.select(emu, item)
                emu.call(emu.sym("_buy"), emu.scene)
            self.assertEqual(self.slot(emu, 1)[:3], (item, 1, 6))

    def run_stub(self, name: str, targets: tuple[int, ...], **regs) -> int:
        from unicorn import x86_const as X
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        reached = []

        def stop(e, at):
            reached.append(at)
            e.uc.emu_stop()
            return 0
        for at in targets:
            emu.hook(at, lambda e, at=at: stop(e, at))
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        for reg, value in regs.items():
            emu.uc.reg_write(getattr(X, f"UC_X86_REG_{reg.upper()}"), value)
        emu.uc.emu_start(emu.sym(name), 0, count=50)
        return reached[0]

    def test_buying_a_stock_chemical_over_them_asks_to_replace(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            self.assertEqual(self.run_stub("_stub_chem_confirm", (0x428191, 0x4281D6), ecx=SPR[item][1]), 0x428191)

    def test_universal_slots_send_them_to_the_chemicals(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            self.assertEqual(self.run_stub("_stub_use_gate", (0x43F5A2, 0x43F5AC, 0x43F5DE), edx=item), 0x43F5A2)
        self.assertEqual(self.run_stub("_stub_use_gate", (0x43F5A2, 0x43F5AC, 0x43F5DE), edx=34), 0x43F5DE)

    # ------------------------------------------------------------ a dose
    def tank(self, item: int, rng, slots: int = 21, ds: bool = False, count: int = 3, part=None,
             sparkles: bool = False):
        """The vanilla use handler (0x420B70) with the DLL's chemical switch at 0x420E6F, slot #3 picked.
        `part`: for the stock Unknown Chemical, its body-or-fin roll's answer ("body" / "fin")."""
        emu = E.Emulator(FISH_EXE, self.dll, self.symbols)
        stub = emu.sym("_stub_chem_use")
        emu.uc.mem_write(0x420E6F, b"\xE9" + struct.pack("<i", stub - 0x420E74) + b"\x90" * 7)
        if slots != 21:                                                      # Bigger tanks rewrites the loop ends
            emu.uc.mem_write(0x421045, struct.pack("<i", slots * REC))
            emu.uc.mem_write(0x4206B3, bytes([slots]))
        emu.ds_base = None
        if ds:                                                               # DS Exclusive Fish's steps, its DLL beside
            delta = 0x02000000
            emu.ds_base = map_relocated(emu, DS_DLL, delta)
            emu.write32(self.ds_symbols["_installed"] + delta, 1)
            for site, name in ((0x420EFB, "_stub_mutate_body"), (0x420F27, "_stub_mutate_fin")):
                target = self.ds_symbols[name] + delta
                emu.uc.mem_write(site, b"\xE9" + struct.pack("<i", target - (site + 5)) + b"\x90")
            step = self.ds_symbols["_FtfpDsFishStepGene@4"] + delta
            emu.hook_import("GetModuleHandleW", lambda e: emu.ds_base if e.wstring(e.arg(0)) == "DS Exclusive Fish.dll"
                            else 0, 4)
            emu.hook_import("GetProcAddress", lambda e: step if e.cstring(e.arg(1)) == b"FtfpDsFishStepGene" else 0, 8)
        else:
            emu.hook_import("GetModuleHandleW", lambda e: 0, 4)
        emu.hook(0x00413B00, emu.record("effect", args=3), 12)
        emu.hook(0x004251A0, lambda e: 0, 4)
        emu.hook(0x0040AE20, emu.record("play"), 4)
        if sparkles:                                                         # view entries 0-2 show tank 0's slots 0-2
            emu.hook(0x00413BD0, lambda e: 1 if e.arg(0) < 3 else 0, 4)
            emu.hook(0x00413B30, lambda e: 0, 4)
            emu.hook(0x00413B50, lambda e: e.arg(0), 4)
            pos = emu.alloc(8)

            def where(e):
                emu.uc.mem_write(pos, struct.pack("<ii", 100 + e.arg(1), 200 + e.arg(1)))
                return pos
            emu.hook(0x00413BA0, where, 8)
        else:
            emu.hook(0x00413BD0, lambda e: 0, 4)
        emu.hook(0x004020D0, lambda e: 5000, 0)

        def random(e):
            n, caller = e.arg(0), e.read32(e.uc.reg_read(E.X.UC_X86_REG_ESP))
            if caller == UC_PART and part is not None:
                value = 0 if part == "body" else 99
            else:
                value = rng(n)
            e.calls.append(("random", caller, n, value))
            return value
        emu.hook(0x00403240, random, 0)
        emu.hook(0x00415E70, emu.record("view sync", args=1), 4)
        emu.hook(0x00415DF0, emu.record("sprites", args=3), 12)
        emu.hook(0x00417FA0, emu.record("hint", args=1), 4)
        state, impl = emu.alloc(0x50000), emu.alloc(0x100)
        for at in range(0, 0x50000, 4):
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        emu.write32(state + S_TANK, 0)
        emu.uc.mem_write(state + SLOT3, struct.pack("<6i", item, 1, count, 0x7A, 0x7B, 0x7E))
        for tank in range(4):
            for slot in range(31):
                emu.write32(state + FISH + tank * TANK + slot * REC, 0)
        emu.write32(impl + 0x1C, 2)
        emu.write32(impl + 0x34, state)
        emu.write32(impl + 0x3C, emu.alloc(0x40))
        emu.write32(impl + 0x44, emu.alloc(0x40))
        emu.write32(impl + 0x4C, emu.alloc(0x40))
        for at, value in ((0xA8, 0), (0xAC, 0), (0xB0, 800), (0xB4, 600)):
            emu.write32(impl + at, value)
        emu.state, emu.impl = state, impl
        return emu

    def at(self, emu, slot: int, tank: int = 0) -> int:
        return emu.state + FISH + tank * TANK + slot * REC

    def fish(self, emu, slot: int, body: int, fin: int, health: int = 60, tank: int = 0, age: int = 30) -> int:
        at = self.at(emu, slot, tank)
        for field, value in ((F_LIVE, 1234), (F_AGE, age), (F_HEALTH, health), (F_BODY, body), (F_FIN, fin)):
            emu.write32(at + field, value)
        return at

    def dose(self, emu) -> None:
        emu.write32(emu.impl + 0x1C, 2)
        emu.call(0x00420B70, 400, 300, ecx=emu.impl)

    def genes(self, emu, slot: int, tank: int = 0) -> tuple[int, int]:
        at = self.at(emu, slot, tank)
        return emu.read32(at + F_BODY, signed=True), emu.read32(at + F_FIN, signed=True)

    # A tank of every kind of record the stock chemical meets.
    LAYOUT = (
        # slot, body, fin, health, tank, age
        (0, 3, 7, 60, 0, 30), (1, 0, 0, 60, 0, 30), (2, 20, 20, 60, 0, 30), (3, 13, 5, 60, 0, 1),     # a baby
        (4, 9, 11, 0, 0, 40),                                                # dead: not reached
        (5, 22, 22, 60, 0, 30),                                              # the Golden Seahorse: not reached
        (6, 22, 31, 60, 0, 30),                                              # a store animal's record: not reached
        (7, 10, 10, -5, 0, 30),                                              # health below 0: reached, as stock
        (8, 19, 1, 100, 0, 90), (12, 6, 14, 60, 0, 30), (20, 15, 18, 60, 0, 30),
        (0, 4, 4, 60, 1, 30), (0, 5, 5, 60, 3, 30),                          # another tank, the isolation tank
    )

    def lay_out(self, emu, layout=LAYOUT) -> None:
        for slot, body, fin, health, tank, age in layout:
            self.fish(emu, slot, body, fin, health, tank, age)

    def fish_area(self, emu) -> bytes:
        return bytes(emu.uc.mem_read(emu.state + FISH, 4 * TANK))

    def compare_with_stock(self, item: int, seed: int, slots: int = 21, ds: bool = False, layout=LAYOUT) -> None:
        muta = self.tank(item, Rand(seed), slots=slots, ds=ds)
        stock = self.tank(UNKNOWN, Rand(seed), slots=slots, ds=ds, count=1, part="fin" if item == MUTA_FIN else "body")
        for emu in (muta, stock):
            self.lay_out(emu, layout)
        self.dose(muta)
        self.dose(stock)
        self.assertEqual(self.fish_area(muta), self.fish_area(stock), seed)             # every record, every field
        pick = lambda emu, label: [c for c in emu.calls if c[0] == label]
        self.assertEqual(pick(muta, "sprites"), pick(stock, "sprites"), seed)            # the same fish redrawn
        self.assertEqual(pick(muta, "view sync"), pick(stock, "view sync"), seed)
        self.assertEqual(muta.read32(muta.impl + 0x30), stock.read32(stock.impl + 0x30))  # next update: now + 1
        # The rolls: the stock ones without its body-or-fin roll, in the same order.
        rolls = lambda emu: [c[3] for c in emu.calls if c[0] == "random" and c[1] != UC_PART]
        self.assertEqual(rolls(muta), rolls(stock), seed)

    def test_each_dose_is_the_unknown_chemicals_for_one_part(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            for seed in range(40):
                with self.subTest(item=item, seed=seed):
                    self.compare_with_stock(item, seed)

    def test_the_other_part_and_every_other_record_never_change(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            emu = self.tank(item, Rand(7))
            self.lay_out(emu)
            before = bytearray(emu.uc.mem_read(emu.state, 0x50000))
            for _ in range(3):
                self.dose(emu)
            after = bytes(emu.uc.mem_read(emu.state, 0x50000))
            changed = {(off - FISH) // REC for off in range(FISH, FISH + 4 * TANK, 4)
                       if before[off:off + 4] != after[off:off + 4] and (off - FISH) % REC in (F_BODY, F_FIN)}
            for slot, body, fin, health, tank, _ in self.LAYOUT:
                now = self.genes(emu, slot, tank)
                if item == MUTA_FIN:
                    self.assertEqual(now[0], body, (slot, tank))                 # the body never changes
                else:
                    self.assertEqual(now[1], fin, (slot, tank))
                if health == 0 or body == 22 or tank != 0:                       # never reached
                    self.assertEqual(now, (body, fin), (slot, tank))
            self.assertTrue(changed)
            # Outside the fish records only slot #3 changed: its three doses spent, so it is emptied.
            outside = [off for off in range(0, 0x50000, 4) if not FISH <= off < FISH + 4 * TANK
                       and before[off:off + 4] != after[off:off + 4]]
            self.assertLessEqual(set(outside), set(range(SLOT3, SLOT3 + 0x14, 4)))

    def test_doses_count_down_and_the_slot_empties(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            emu = self.tank(item, Rand(1))
            for left in (2, 1):
                self.dose(emu)
                self.assertEqual(struct.unpack("<3i", emu.uc.mem_read(emu.state + SLOT3, 12)), (item, 1, left))
            self.dose(emu)
            self.assertEqual(struct.unpack("<3i", emu.uc.mem_read(emu.state + SLOT3, 12)), (0, 0, 0))
            self.assertEqual(emu.read32(emu.impl + 0x1C), 0x63)

    def test_the_distribution_over_many_doses(self) -> None:
        """Each fish reached: its part steps on Random(100) <= 25; up on Random(100) <= 49 (or at 0),
        always down at 20. Counted over the game's own rand() from several seeds."""
        import breeding_fish
        from math import sqrt
        p_change, p_up = breeding_fish.P_CHEMICAL, breeding_fish.P_UP
        for item in (MUTA_FIN, MUTA_BODY):
            counts = {"up": 0, "down": 0, "same": 0}
            edge = {"0 up": 0, "20 down": 0, "edge n": 0}
            trials = 0
            for seed in range(6):
                emu = self.tank(item, Rand(1000 + seed), count=10 ** 6)
                for _ in range(40):
                    layout = [(s, 10, 10, 60, 0, 30) for s in range(19)] + [(19, 0, 0, 60, 0, 30), (20, 20, 20, 60, 0, 30)]
                    self.lay_out(emu, layout)
                    self.dose(emu)
                    for s in range(21):
                        body, fin = self.genes(emu, s)
                        part, other = (fin, body) if item == MUTA_FIN else (body, fin)
                        start = 10 if s < 19 else (0 if s == 19 else 20)
                        self.assertEqual(other, start)                          # the other part never changes
                        if s < 19:
                            trials += 1
                            counts["up" if part == 11 else "down" if part == 9 else "same"] += 1
                            self.assertIn(part, (9, 10, 11))
                        else:
                            self.assertIn(part, (start, 1 if start == 0 else 19))   # 0 only up, 20 only down
                            if part != start:
                                edge["0 up" if start == 0 else "20 down"] += 1
                            edge["edge n"] += 1
            for name, p in (("up", p_change * p_up), ("down", p_change * (1 - p_up)), ("same", 1 - p_change)):
                sd = sqrt(trials * p * (1 - p))
                self.assertLess(abs(counts[name] - trials * p), 4.5 * sd, (item, name, counts, trials))
            n = edge["edge n"] / 2
            self.assertLess(abs(edge["0 up"] - n * p_change), 4.5 * sqrt(n * p_change * (1 - p_change)) + 1, edge)

    def test_the_stock_steps_never_reach_the_ds_genes(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            seen = set()
            for seed in range(30):
                emu = self.tank(item, Rand(seed))
                self.lay_out(emu, [(s, 19, 19, 60, 0, 30) for s in range(21)])
                self.dose(emu)
                seen |= {self.genes(emu, s)[0 if item == MUTA_BODY else 1] for s in range(21)}
            self.assertEqual(seen, {18, 19, 20}, item)                          # never 23

    def test_with_ds_exclusive_fish_its_own_step_reaches_the_ds_genes(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            for seed in range(25):
                with self.subTest(item=item, seed=seed):
                    self.compare_with_stock(item, seed, ds=True,
                                            layout=[(s, 20 if s % 3 else 23, 29 if s % 2 else 20, 60, 0, 30)
                                                    for s in range(21)])
            seen = set()
            for seed in range(30):
                emu = self.tank(item, Rand(seed), ds=True)
                self.lay_out(emu, [(s, 20, 20, 60, 0, 30) for s in range(10)] + [(s, 29, 29, 60, 0, 30) for s in range(10, 21)])
                self.dose(emu)
                seen |= {self.genes(emu, s)[0 if item == MUTA_BODY else 1] for s in range(21)}
            self.assertEqual(seen, {19, 20, 23, 28, 29}, item)                  # 20 up into 23, 29 only down

    def test_bigger_tanks_reach_the_records_the_stock_loop_reaches(self) -> None:
        for slots in (26, 30):
            for item in (MUTA_FIN, MUTA_BODY):
                self.compare_with_stock(item, 3, slots=slots,
                                        layout=[(s, 10, 10, 60, 0, 30) for s in range(slots)])
                hit = set()
                for seed in range(20):
                    emu = self.tank(item, Rand(seed), slots=slots)
                    self.lay_out(emu, [(s, 10, 10, 60, 0, 30) for s in range(31)])
                    self.dose(emu)
                    hit |= {s for s in range(31) if self.genes(emu, s) != (10, 10)}
                self.assertIn(slots - 1, hit)
                self.assertFalse({s for s in hit if s >= slots}, (slots, item))

    def test_the_sparkles_are_the_unknown_chemicals(self) -> None:
        for item in (MUTA_FIN, MUTA_BODY):
            muta = self.tank(item, Rand(5), sparkles=True)
            stock = self.tank(UNKNOWN, Rand(5), count=1, sparkles=True, part="fin" if item == MUTA_FIN else "body")
            for emu in (muta, stock):
                self.lay_out(emu, [(0, 3, 3, 60, 0, 30), (1, 4, 4, 0, 0, 30), (2, 5, 5, 60, 0, 30)])
                self.dose(emu)
            effects = lambda emu: [c for c in emu.calls if c[0] == "effect"]
            self.assertEqual(effects(muta), effects(stock))
            sparkles = [c[1] for c in effects(muta) if c[1][0] == 0x15]
            self.assertEqual(sparkles, [(0x15, 100, 200), (0x15, 102, 202)])  # the live fish on screen only


# ================================================================== Plant Tycoon

@_needs(PLANT_EXE)
class PlantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", PLANT_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def greenhouse(self, rng, gene_roll=None, unused_flowers: bool = False, with_plants: bool = True):
        """`gene_roll`: for the stock step, its flower-or-foliage Random(2)'s answer."""
        emu = E.Emulator(PLANT_EXE, self.dll, self.symbols)
        emu.hook_printf()
        if unused_flowers:                                                   # its rewrite of the flower bounds
            emu.uc.mem_write(0x42FACE, bytes([37]))
            emu.uc.mem_write(0x42FAD5, struct.pack("<I", 36))
        state, greenhouse, plants = emu.alloc(PLANT_STATE), emu.alloc(0x200), emu.alloc(0x100)
        for at in range(0, PLANT_STATE, 4):
            emu.write32(state + at, (at * 2654435761) & 0x7FFFFFFF)
        emu.write32(greenhouse + 0x68, state)
        emu.write32(greenhouse + 0x70, plants)
        emu.write32(plants, state)

        def random(e):
            n, caller = e.arg(0), e.read32(e.uc.reg_read(E.X.UC_X86_REG_ESP))
            value = gene_roll if caller == MUTATION_GENE_ROLL and gene_roll is not None else rng(n)
            e.calls.append(("random", caller, n, value))
            return value
        emu.hook(0x004033B0, random, 0)
        # Plant objects: vtable +0 delete (recorded), +0x44 regrow (recorded); 0x42D570 flower count.
        vtable = emu.alloc(0x80)
        for slot, label, pop in ((0, "delete", 4), (0x44, "regrow", 8)):
            thunk = emu.thunk()
            emu.hook(thunk, lambda e, label=label: (e.calls.append((label, e.uc.reg_read(E.X.UC_X86_REG_ECX))), 0)[1], pop)
            emu.write32(vtable + slot, thunk)
        emu.objects = []

        def new_plant(k):
            obj = emu.alloc(0x40)
            emu.write32(obj, vtable)
            emu.write32(plants + 8 + 4 * k, obj)
            emu.objects.append(obj)
            return obj
        if with_plants:
            for k in range(15):
                new_plant(k)
        emu.hook(0x0042D570, lambda e: 4, 0)

        def grow(e):                                                         # 0x42F660(row, col, pot): a new object
            row, col, pot = e.arg(0), e.arg(1), e.arg(2)
            e.calls.append(("grow", row, col, pot))
            new_plant(row * 5 + col)
            return 0
        emu.hook(0x0042F660, grow, 12)
        emu.state, emu.gh, emu.plants = state, greenhouse, plants
        return emu

    def pot(self, emu, k: int) -> int:
        return emu.state + POT0 + k * POT_SIZE

    def set_genes(self, emu, k: int, foliage: int, flower: int) -> None:
        emu.write32(self.pot(emu, k) + P_FOLIAGE, foliage)
        emu.write32(self.pot(emu, k) + P_FLOWER, flower)

    def genes(self, emu, k: int) -> tuple[int, int]:
        return emu.read32(self.pot(emu, k) + P_FOLIAGE, signed=True), emu.read32(self.pot(emu, k) + P_FLOWER, signed=True)

    def muta(self, emu, chemical: int, k: int) -> None:
        emu.call(emu.sym("_apply_muta"), emu.gh, k % 5, k // 5, chemical)

    def stock_step(self, emu, k: int) -> None:
        emu.call(0x0042FA80, k // 5, k % 5, ecx=emu.plants)

    def snapshot(self, emu) -> bytes:
        return bytes(emu.uc.mem_read(emu.state, PLANT_STATE)) + bytes(emu.uc.mem_read(emu.plants, 0x100))

    def test_each_dose_is_the_mutation_liquids_step_for_one_gene(self) -> None:
        for chemical, roll in ((MUTA_FLOWER, 1), (MUTA_FOLIAGE, 0)):
            for unused in (False, True):
                for seed in range(12):
                    for k, (foliage, flower) in ((0, (12, 12)), (6, (1, 1)), (9, (23, 23)), (14, (22, 37 if unused else 23))):
                        with self.subTest(chemical=chemical, unused=unused, seed=seed, k=k):
                            muta, stock = self.greenhouse(Rand(seed), unused_flowers=unused), \
                                self.greenhouse(Rand(seed), gene_roll=roll, unused_flowers=unused)
                            for emu in (muta, stock):
                                self.set_genes(emu, k, foliage, flower)
                            self.muta(muta, chemical, k)
                            self.stock_step(stock, k)
                            self.assertEqual(self.snapshot(muta), self.snapshot(stock))
                            pick = lambda emu: [c for c in emu.calls if c[0] != "random" or c[1] != MUTATION_GENE_ROLL]
                            self.assertEqual(pick(muta), pick(stock))           # the same calls, rolls and regrowth
                            now = self.genes(muta, k)
                            if chemical == MUTA_FLOWER:
                                self.assertEqual(now[0], foliage)
                            else:
                                self.assertEqual(now[1], flower)

    def test_the_distribution_and_the_bounces(self) -> None:
        import breeding_plant
        from math import sqrt
        for chemical in (MUTA_FLOWER, MUTA_FOLIAGE):
            for unused in (False, True):
                for start in ((12, 12), (1, 1), (23, 23), (22, 37)):
                    if start == (22, 37) and not unused:
                        continue
                    results: dict[tuple[int, int], int] = {}
                    trials = 400
                    emu = self.greenhouse(Rand(start[0] * 100 + chemical + unused), unused_flowers=unused)
                    for _ in range(trials):
                        self.set_genes(emu, 3, *start)
                        self.muta(emu, chemical, 3)
                        got = self.genes(emu, 3)
                        results[got] = results.get(got, 0) + 1
                    # The stock step's own results for that gene (breeding_plant.mutation_steps), renormalised.
                    slot = 1 if chemical == MUTA_FLOWER else 0
                    expected: dict[tuple[int, int], float] = {}
                    for new, p in breeding_plant.mutation_steps(start, unused):
                        if new[1 - slot] == start[1 - slot] and (new != start or new[slot] != start[slot]):
                            if new[slot] != start[slot] or new == start:
                                expected[new] = expected.get(new, 0) + 2 * p
                    self.assertEqual(set(results), set(expected), (chemical, unused, start, results))
                    for new, p in expected.items():
                        sd = sqrt(trials * p * (1 - p)) or 1
                        self.assertLess(abs(results[new] - trials * p), 4.5 * sd, (chemical, start, new, results))

    def test_unused_flowers_only_with_its_setting(self) -> None:
        for unused, top in ((False, 23), (True, 37)):
            seen = set()
            for seed in range(30):
                emu = self.greenhouse(Rand(seed), unused_flowers=unused)
                self.set_genes(emu, 0, 5, 23)
                self.muta(emu, MUTA_FLOWER, 0)
                seen.add(self.genes(emu, 0)[1])
            self.assertEqual(seen, {22, 24} if unused else {22})                 # 23 + 1 is 24 only with the setting
            self.assertTrue(max(seen) <= top)

    def test_no_plant_object_keeps_the_foliage_as_stock(self) -> None:
        for seed in range(5):
            muta, stock = self.greenhouse(Rand(seed), with_plants=False), self.greenhouse(Rand(seed), 0, with_plants=False)
            for emu in (muta, stock):
                self.set_genes(emu, 2, 9, 9)
            self.muta(muta, MUTA_FOLIAGE, 2)
            self.stock_step(stock, 2)
            self.assertEqual(self.genes(muta, 2), (9, 9))
            self.assertEqual(self.snapshot(muta), self.snapshot(stock))

    # ------------------------------------------------------------ the switch, discovery and the store
    def use(self, emu, chemical: int, k: int, stop: int):
        """stub_apply as the use reaches it (0x4266A6): esi the greenhouse, ebx column, ebp row, edi the
        pot's offset, [esp + 0x20] the chemical, [esp + 0x14] the plant; runs to `stop`."""
        esp = E.STACK + E.STACK_SIZE - 0x1000
        emu.write32(esp + 0x20, chemical)
        emu.write32(esp + 0x14, emu.read32(emu.plants + 8 + 4 * k))
        regs = {"ESP": esp, "ESI": emu.gh, "EBX": k % 5, "EBP": k // 5, "EDI": k * POT_SIZE}
        for reg, value in regs.items():
            emu.uc.reg_write(getattr(E.X, f"UC_X86_REG_{reg}"), value)
        emu.uc.emu_start(emu.sym("_stub_apply"), stop, count=200000)
        return regs

    def test_the_switch_sends_48_and_49_into_the_mutation_liquids_case(self) -> None:
        for chemical in (MUTA_FLOWER, MUTA_FOLIAGE):
            emu = self.greenhouse(Rand(9))
            self.set_genes(emu, 7, 8, 8)
            regs = self.use(emu, chemical, 7, 0x00426EFA)
            self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EIP), 0x00426EFA)
            for reg, value in regs.items():                                      # every register as the case expects
                self.assertEqual(emu.uc.reg_read(getattr(E.X, f"UC_X86_REG_{reg}")), value, reg)
            self.assertNotEqual(self.genes(emu, 7), (8, 8))
        for chemical, back in ((35, 0x004266AD), (40, 0x004266AD), (47, 0x004266AD), (50, 0x004266AD)):
            emu = self.greenhouse(Rand(1))
            self.use(emu, chemical, 0, back)
            self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EIP), back, chemical)

    def test_the_new_species_is_discovered_as_the_mutation_liquid_does(self) -> None:
        for chemical in (MUTA_FLOWER, MUTA_FOLIAGE):
            emu = self.greenhouse(Rand(4))
            emu.hook(0x0041EB00, emu.record("encyclopedia", args=2), 8)
            emu.hook(0x0041C1F0, emu.record("sparkle", args=7), 0x1C)
            emu.write32(emu.gh + 0x64, emu.alloc(0x40))
            self.set_genes(emu, 4, 10, 10)
            emu.uc.mem_write(emu.state + 0x64, bytes(24 * 24))                    # nothing discovered yet
            self.use(emu, chemical, 4, 0x0042720B)
            foliage, flower = self.genes(emu, 4)
            table = bytes(emu.uc.mem_read(emu.state + 0x64, 24 * 24))
            self.assertEqual([i for i, b in enumerate(table) if b], [foliage * 24 + flower])
            self.assertIn(("encyclopedia", (foliage, flower)), emu.calls)
            self.assertTrue(any(c[0] == "sparkle" for c in emu.calls))

    def run_until(self, emu, stub: str, stop: int, **regs) -> None:
        for reg, value in regs.items():
            emu.uc.reg_write(getattr(E.X, f"UC_X86_REG_{reg.upper()}"), value)
        emu.uc.reg_write(E.X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        emu.uc.emu_start(emu.sym(stub), stop, count=1000)

    def test_bought_through_the_chemical_dialog_with_3_doses_at_2500(self) -> None:
        for chemical in (MUTA_FLOWER, MUTA_FOLIAGE):
            for upgrade_view, building in ((1, chemical), (0, 0)):               # only from the Upgrades view
                emu = self.greenhouse(Rand(0))
                emu.write8(emu.sym("_upgrade_dialog"), upgrade_view)
                esp = E.STACK + E.STACK_SIZE - 0x1000
                emu.write32(esp + 4, chemical)
                emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
                emu.uc.emu_start(emu.sym("_stub_dialog"), 0x00430957, count=1000)
                self.assertEqual(emu.read32(emu.sym("_building_chem")) & 0xFF, building)
            for free, price in ((0, 2500), (1, 0)):                              # Free upgrades / Everything is Free
                emu = self.greenhouse(Rand(0))
                emu.write8(emu.sym("_building_chem"), chemical)
                emu.write8(emu.sym("_free_upgrades"), free)
                scene = emu.alloc(0x100)
                self.run_until(emu, "_stub_chem_price", 0x00432721, esi=scene, eax=0, ecx=0)
                self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EDX), price, (chemical, free))
            emu = self.greenhouse(Rand(0))
            dialog, table = emu.alloc(0x200), emu.alloc(0x2000)
            emu.write32(dialog + 0xB8, chemical)
            emu.write8(emu.sym("_upgrade_dialog"), 1)
            emu.write32(table + 0x8DC, 77)
            self.run_until(emu, "_stub_chem_doses", 0x00432E4A, ebp=dialog, eax=0, ecx=table)
            self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EDX), 3)

    def test_names_texts_and_the_store_items(self) -> None:
        import test_store_extras
        font = test_store_extras.plant_font()
        emu = self.greenhouse(Rand(0))
        texts = {name: emu.cstring(emu.sym(f"_{name}")).decode("latin-1")
                 for name in ("MUTA_FLOWER_TITLE", "MUTA_FLOWER_DESC", "MUTA_FLOWER_NAME",
                              "MUTA_FOLIAGE_TITLE", "MUTA_FOLIAGE_DESC", "MUTA_FOLIAGE_NAME")}
        self.assertEqual(texts["MUTA_FLOWER_DESC"].replace("\n", " ").strip(),
                         "Mutates the flowering parts of plants. Contains 3 doses.")       # the owner's words
        self.assertEqual(texts["MUTA_FOLIAGE_DESC"].replace("\n", " ").strip(),
                         "Mutates the leafy parts of plants. Contains 3 doses.")
        self.assertEqual((texts["MUTA_FLOWER_NAME"], texts["MUTA_FOLIAGE_NAME"]), ("Muta-Flower", "Muta-Foliage"))
        for text in texts.values():
            self.assertLessEqual(set(text) - {"\n"}, font, text)
        # The tray's names (greenhouse and store) and the dialog's title and description.
        for chemical, name_id in ((MUTA_FLOWER, 0x1FB), (MUTA_FOLIAGE, 0x1FC)):
            emu = self.greenhouse(Rand(0))
            self.run_until(emu, "_stub_name_greenhouse", 0x004277B9, eax=chemical)
            self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EAX), name_id)
            emu = self.greenhouse(Rand(0))
            esp = E.STACK + E.STACK_SIZE - 0x1000
            emu.write32(esp, E.RETURN)
            emu.write32(esp + 4, name_id)
            emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
            emu.uc.emu_start(emu.sym("_stub_string"), E.RETURN, count=1000)
            self.assertEqual(emu.cstring(emu.uc.reg_read(E.X.UC_X86_REG_EAX)).decode(),
                             "Muta-Flower" if chemical == MUTA_FLOWER else "Muta-Foliage")
            for string_id, prefix in ((0x165, "Muta-F"), (0x166, "Mutates the")):
                emu = self.greenhouse(Rand(0))
                emu.write8(emu.sym("_building_chem"), chemical)
                emu.write32(esp, E.RETURN)
                emu.write32(esp + 4, string_id)
                emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
                emu.uc.emu_start(emu.sym("_stub_string"), E.RETURN, count=1000)
                self.assertTrue(emu.cstring(emu.uc.reg_read(E.X.UC_X86_REG_EAX)).decode().startswith(prefix))

    def store_scene(self, emu) -> int:
        scene = emu.alloc(0x400)
        emu.write32(scene + 0x1BC, emu.state)
        emu.write32(emu.sym("_upgrades_view"), 1)
        owned = emu.thunk()                                              # no extra greenhouse or nursery owned
        emu.hook(owned, lambda e: 0, 0)
        for i in range(2):
            emu.write32(emu.sym("_extra_owned") + 4 * i, owned)
            emu.write32(emu.sym("_extra_buy") + 4 * i, owned)
        for name, pop in (("GetModuleHandleW", 4), ("GetProcAddress", 8)):
            emu.hook_import(name, lambda e: 0, pop)
        return scene

    def test_the_store_draws_and_opens_them(self) -> None:
        # The Upgrades view's draw: both bottles, upright (frames 42 and 44: rows 21 and 22), on the
        # chemicals shelf's third row beside Extra Chemical Slots.
        emu = self.greenhouse(Rand(0))
        emu.hook(0x004208F0, emu.record("sprite", args=7), 0x1C)
        emu.hook(0x004207F0, emu.record("shadow", args=5), 0x14)
        emu.call(emu.sym("_on_draw"), self.store_scene(emu))
        frames = [(c[1][1], c[1][2], c[1][3]) for c in emu.calls if c[0] == "sprite"]
        self.assertIn((42, 655, 177), frames)
        self.assertIn((44, 712, 177), frames)
        # A click on each opens the stock chemical dialog with its own index.
        opened = []
        emu = self.greenhouse(Rand(0))
        emu.hook(0x00432E90, lambda e: (opened.append(e.arg(0)), 0)[1], 4)
        emu.hook(0x00401C90, lambda e: 0, 8)
        emu.hook(0x004307A0, lambda e: 0, 0)
        emu.hook(0x00409AA0, lambda e: 0, 0x10)
        scene = self.store_scene(emu)
        for x, y in ((690, 210), (747, 210)):
            emu.call(emu.sym("_on_click"), scene, x, y)
        self.assertEqual(opened, [MUTA_FLOWER, MUTA_FOLIAGE])


if __name__ == "__main__":
    unittest.main()
