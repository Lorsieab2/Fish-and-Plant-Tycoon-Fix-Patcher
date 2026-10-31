"""Every patcher consumable's in-game description ends with "Contains N doses." (the owner, 2026-10-31).

The rule covers every chemical or other consumable the patcher adds to a store, in both games:
Fish Tycoon's Radioactive Growth Hormone, Revival Potion, ClonaFish, Muta-Fin and Muta-Body (DS
Store Items), and Plant Tycoon's Radioactive Plant Formula, Revival Potion, Revita-Seed, Radioactive
Plant Formula Bomb, Muta-Flower and Muta-Foliage (Store Upgrades and Items). N is the number of doses a purchase really gives. The wording is the
stock games' own: Plant Tycoon's chemicals end "Contains N doses." and a line break, Fish Tycoon's
end "Contains N doses." and, in German, "Reicht für N Behandlungen." (the stock Growth Hormone's).

The static tests read the descriptions from the C sources, check every one is in the committed DLL
byte for byte, and classify every item of each store, so an item added later must be named here
as a consumable (with its doses) or not. The emulated tests buy each consumable with the DLL's own
code on the vanilla executable (tests/store_emulator.py) and count the doses it really gives.
"""

from __future__ import annotations

import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

try:
    import store_emulator as E
except ImportError:          # Unicorn is not installed
    E = None

FISH_C = ROOT / "native" / "ftfp_ds_store" / "ftfp_ds_store.c"
PLANT_C = ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c"
PLANT_MUTA_H = ROOT / "native" / "ftfp_plant_upgrades" / "muta_chemicals.h"     # Muta-Flower, Muta-Foliage
FISH_DLL = ROOT / "assets" / "fish_tycoon_ds_store" / "DS Store Items.dll"
PLANT_DLL = ROOT / "assets" / "plant_tycoon_upgrades" / "Store Upgrades and Items.dll"

# Every DS Store Items item, by its English name: its doses if it is a consumable, else None.
FISH_ITEMS = {
    "Magic Pufferfish": None, "Blue-Spotted Stingray": None, "Moray Eel": None,   # tank animals
    "Exotic Fish Eggs": None,             # eggs: one hatch, not a dosed chemical
    "Time Warp": None, "Add $1,000": None,  # used up when bought
    "Radioactive Growth Hormone": 3, "Revival Potion": 3, "ClonaFish": 3,
    "Extra Tank": None, "Auto-Feeder": None, "Auto-Healer": None,                 # upgrades
    "Extra Supply Slots": None,
    "Muta-Fin": 3, "Muta-Body": 3,
}
# Every Store Upgrades and Items description, by its C name: its doses if it is a consumable, else None.
PLANT_ITEMS = {
    "LEGENDARY_DESC": None,               # a seed packet
    "FORMULA_DESC": 3, "REVIVAL_DESC": 3, "REVITA_DESC": 3, "BOMB_DESC": 3,
    "MUTA_FLOWER_DESC": 3, "MUTA_FOLIAGE_DESC": 3,
}
FISH_ITEM_IDS = {"Radioactive Growth Hormone": 29, "Revival Potion": 30, "ClonaFish": 31, "Muta-Fin": 32,
                 "Muta-Body": 33}
FISH_CELLS = {29: (630, 125), 30: (725, 125), 31: (86, 200), 32: (450, 200), 33: (542, 200)}
PLANT_CHEMICALS = {"FORMULA_DESC": 36, "REVIVAL_DESC": 37, "REVITA_DESC": 38, "BOMB_DESC": 39,
                   "MUTA_FLOWER_DESC": 48, "MUTA_FOLIAGE_DESC": 49}

LITERAL = r'"(?:[^"\\]|\\.)*"'
LITERALS = rf"(?:{LITERAL}\s*)+"


def c_string(literals: str) -> str:
    """The text of adjacent C string literals (\\n, \\", \\\\ and \\xHH escapes)."""
    out = []
    for body in re.findall(LITERAL, literals):
        body, i = body[1:-1], 0
        while i < len(body):
            if body[i] != "\\":
                out.append(body[i])
                i += 1
                continue
            nxt = body[i + 1]
            if nxt == "x":
                digits = re.match(r"[0-9A-Fa-f]{1,2}", body[i + 2:]).group(0)
                out.append(chr(int(digits, 16)))
                i += 2 + len(digits)
            else:
                out.append({"n": "\n", '"': '"', "\\": "\\"}[nxt])
                i += 2
    return "".join(out)


def fish_items() -> dict[str, tuple[str, str]]:
    """English name -> (English description, German description) of every DS Store Items item."""
    source = FISH_C.read_text(encoding="utf-8")
    table = source[source.index("static const store_item ITEM[ITEMS]"):]
    table = table[:table.index("\n};")]
    items = {}
    for name, desc_en, desc_de in re.findall(
            rf"\{{\s*({LITERALS}),\s*{LITERALS}\}},\s*(?:/\*.*?\*/\s*)?\{{\s*({LITERALS}),\s*({LITERALS})\}}\s*\}}",
            table):
        items[c_string(name)] = (c_string(desc_en), c_string(desc_de))
    return items


def plant_descriptions() -> dict[str, str]:
    source = PLANT_C.read_text(encoding="utf-8") + PLANT_MUTA_H.read_text(encoding="utf-8")
    return {name: c_string(body)
            for name, body in re.findall(rf"static const char (\w+_DESC)\[\] =\s*({LITERALS});", source)}


def fish_constant(name: str) -> int:
    return int(re.search(rf"#define {name} (\d+)", FISH_C.read_text(encoding="utf-8")).group(1))


class DescriptionTests(unittest.TestCase):
    def test_every_fish_store_item_is_classified(self) -> None:
        self.assertEqual(set(fish_items()), set(FISH_ITEMS))

    def test_every_plant_store_description_is_classified(self) -> None:
        self.assertEqual(set(plant_descriptions()), set(PLANT_ITEMS))

    def test_fish_consumables_end_with_their_doses(self) -> None:
        items = fish_items()
        for name, doses in FISH_ITEMS.items():
            if doses is None:
                continue
            english, german = items[name]
            self.assertTrue(english.endswith(f"Contains {doses} doses."), (name, english))
            self.assertTrue(german.endswith(f"Reicht für {doses} Behandlungen."), (name, german))
            self.assertEqual(fish_constant("RGH_DOSES"), doses, name)     # every new chemical's purchase

    def test_plant_consumables_end_with_their_doses(self) -> None:
        descriptions = plant_descriptions()
        for name, doses in PLANT_ITEMS.items():
            if doses is None:
                continue
            # The stock chemicals' texts end with a line break after the sentence; nothing else follows it.
            self.assertTrue(descriptions[name].endswith(f"Contains {doses} doses.\n"), (name, descriptions[name]))

    def test_no_item_that_is_not_a_consumable_claims_doses(self) -> None:
        for name, (english, _) in fish_items().items():
            if FISH_ITEMS[name] is None:
                self.assertNotIn("dose", english.lower(), name)
        for name, text in plant_descriptions().items():
            if PLANT_ITEMS[name] is None:
                self.assertNotIn("dose", text.lower(), name)

    def test_the_committed_dlls_carry_these_texts(self) -> None:
        fish = FISH_DLL.read_bytes()
        for name, doses in FISH_ITEMS.items():
            if doses is not None:
                for text in fish_items()[name]:
                    self.assertIn(text.encode("latin-1") + b"\0", fish, name)
        plant = PLANT_DLL.read_bytes()
        for name, text in plant_descriptions().items():
            if PLANT_ITEMS[name] is not None:
                self.assertIn(text.encode("latin-1") + b"\0", plant, name)


def _needs(game: str):
    exe = (E.VANILLA / game / f"{game}.exe") if E else None
    ready = E is not None and E.toolchain_ready() and exe is not None and exe.is_file()
    return unittest.skipUnless(ready, "needs Unicorn, the pinned MSVC toolset and the vanilla executable")


@_needs("Fish Tycoon")
class FishPurchaseTests(unittest.TestCase):
    """Each Fish consumable bought with DS Store Items' own code: the doses in the supply slot, and
    the description the store shows for it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = E.VANILLA / "Fish Tycoon" / "Fish Tycoon.exe"
        cls.dll, cls.symbols = E.build_with_map("ftfp_ds_store", FISH_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def store(self, universal: bool = False):
        emu = E.Emulator(self.exe, self.dll, self.symbols)
        emu.hook_import("GetTickCount", lambda e: 0, 0)
        emu.hook_import("GetModuleHandleW", lambda e: 0, 4)            # no Extra Tanks.dll loaded
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
        state, impl, scene = emu.alloc(0x40000), emu.alloc(0x100), emu.alloc(0x100)
        emu.write32(scene + 8, impl)
        emu.write32(impl + 0x10, state)
        emu.write32(impl + 0x0C, emu.alloc(0x40))
        emu.write32(state + 0x38C, 100000)
        for name, on in (("_free_on", 0), ("_page_upgrades", 1), ("_exotic_any_slot", universal)):
            emu.write32(emu.sym(name), int(on))
        emu.state, emu.scene = state, scene
        return emu

    def select(self, emu, item: int) -> None:
        emu.call(emu.sym("@on_mouse@20"), 3, *FISH_CELLS[item], ecx=emu.scene)

    def slot_count(self, emu, k: int) -> tuple[int, int]:
        item, _, count = struct.unpack("<3i", emu.uc.mem_read(emu.state + 0x2B8 + k * 0x1C, 12))
        return item, count

    def test_a_purchase_gives_the_doses_the_description_says(self) -> None:
        for name, item in FISH_ITEM_IDS.items():
            doses = FISH_ITEMS[name]
            emu = self.store()
            self.select(emu, item)
            emu.call(emu.sym("@on_overlay@8"), ecx=emu.scene)
            shown = [c[1] for c in emu.calls if c[0] == "text"]
            self.assertTrue(any(t.endswith(f"Contains {doses} doses.") for t in shown), (name, shown))
            emu.call(emu.sym("_buy"), emu.scene)
            self.assertEqual(self.slot_count(emu, 2), (item, doses), name)                 # slot #3
            emu = self.store(universal=True)
            self.select(emu, item)
            emu.call(emu.sym("_buy"), emu.scene)
            self.assertEqual(self.slot_count(emu, 1), (item, doses), name)                 # universal slots


@_needs("Plant Tycoon")
class PlantPurchaseTests(unittest.TestCase):
    """The chemical Buy (0x432E43) with Store Upgrades and Items' own code: the doses each new chemical
    is bought with."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = E.VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"
        cls.dll, cls.symbols = E.build_with_map("ftfp_plant_upgrades", PLANT_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_a_purchase_gives_the_doses_the_description_says(self) -> None:
        for name, chemical in PLANT_CHEMICALS.items():
            # The formula is sold on the stock view too; 37-39 only from the Upgrades view.
            emu = E.Emulator(self.exe, self.dll, self.symbols)
            dialog, table = emu.alloc(0x200), emu.alloc(0x2000)
            emu.write32(dialog + 0xB8, chemical)
            emu.write8(emu.sym("_upgrade_dialog"), 0 if chemical == 36 else 1)
            emu.write32(table + 0x8DC, 77)                                 # what the stock record says
            for reg, value in (("ebp", dialog), ("eax", 0), ("ecx", table)):
                emu.uc.reg_write(getattr(E.X, f"UC_X86_REG_{reg.upper()}"), value)
            emu.uc.reg_write(E.X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
            emu.uc.emu_start(emu.sym("_stub_chem_doses"), 0x00432E4A, count=1000)
            self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_EDX), PLANT_ITEMS[name], name)


if __name__ == "__main__":
    unittest.main()
