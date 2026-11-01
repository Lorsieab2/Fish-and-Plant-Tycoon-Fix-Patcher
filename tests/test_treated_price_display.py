"""The treated price beside the set price (DS Store Items; the owner, 2026-10-31: "put the 'treated'
price beside the normal 'set' price", shown "in the selling screen when fish are sold" and in the
window where prices are set, never in a tank).

Fish Tycoon shows a price the player sets in exactly two places, the two sprintf("$%d") texts of the
vanilla executable, each drawn by a `call 0x408B80` (left-aligned text):

* the Species Chart (its draw 0x4252C0, call 0x425356): the isolation tank's fish's species price,
  the window where the price is set;
* the Fish Store, the selling screen (its draw 0x423800, call 0x4239CC): the last sold fish's price.

DS Store Items turns both calls into its own (stub_chart_price, stub_sold_price). Here the stock
draws run in Unicorn on the vanilla executable with the hooks written as the install writes them
(tests/test_radioactive_max_price.py's rig: Extra Tanks.dll and DS Store Items.dll rebuilt from
source), and every text they draw is recorded:

* a treated fish: the stock "$40" exactly as before, and "Treated: $475" (the species' highest selling
  price, or the asking price when that is higher) in the game's default font and the price's colour --
  the very number the sale pays (checked against a real sale in the same rig);
* an untreated fish: exactly the vanilla executable's texts, nothing more;
* the site bytes: each is the stock `call 0x408B80`, inside its draw, with esi the screen, and no
  other companion or patch touches it.
"""

from __future__ import annotations

import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import test_radioactive_max_price as RMP  # noqa: E402

E, XT = RMP.E, RMP.XT
FISH_EXE = RMP.FISH_EXE
ASKING = RMP.ASKING                          # 40 for every stock species in the rig
GUPPY_MAX = 475                              # the Golden Guppy (7, 7): 2 x 238 - 1
ISOLATION = RMP.FISH_BASE + 3 * RMP.TANK     # tank 3, record 0
LEFT_TEXT, CENTRE_TEXT, SPRINTF = 0x00408B80, 0x00408C30, 0x0042B20B
PRICE_COLOUR, CHART_FONT, SALE_FONT = 0x0045709C, 0x77700001, 0x77700002
CHART_SITE, SOLD_SITE = 0x00425356, 0x004239CC
STORE_C = ROOT / "native" / "ftfp_ds_store" / "ftfp_ds_store.c"
SITES_H = ROOT / "native" / "ftfp_ds_store" / "store_sites.h"


def _text_section(exe: Path) -> tuple[int, bytes]:
    return RMP._text_section(exe)


@unittest.skipUnless(FISH_EXE.is_file(), "needs the vanilla Fish Tycoon.exe")
class Sites(unittest.TestCase):
    """The two sites: what the vanilla code is there, and that nothing else writes it."""

    def test_the_header_pins_the_stock_calls(self) -> None:
        header = SITES_H.read_text(encoding="utf-8")
        va0, code = _text_section(FISH_EXE)
        for name, va in (("CHART_PRICE", CHART_SITE), ("SOLD_PRICE", SOLD_SITE)):
            self.assertIn(f"#define SITE_{name}_VA 0x{va:08X}u", header)
            self.assertIn(f"#define SITE_{name}_LEN 5", header)
            raw = code[va - va0: va - va0 + 5]
            self.assertEqual(raw[0], 0xE8)
            self.assertEqual(va + 5 + struct.unpack("<i", raw[1:])[0], LEFT_TEXT, hex(va))
            expect = ", ".join(f"0x{b:02X}" for b in raw)
            self.assertIn(f"SITE_{name}_EXPECT[] = {{ {expect} }};", header)

    def test_they_are_the_only_two_dollar_prices(self) -> None:
        """The game's "$%d" (0x443B00) is pushed in exactly two places, each formatting the price the
        site then draws: the Species Chart (0x42532E) and the Fish Store (0x42399B)."""
        va0, code = _text_section(FISH_EXE)
        push = b"\x68" + struct.pack("<I", 0x00443B00)
        found = [va0 + m.start() for m in re.finditer(re.escape(push), code)]
        self.assertEqual(found, [0x0042399B, 0x0042532E])
        self.assertLess(0x0042532E, CHART_SITE)
        self.assertLess(0x0042399B, SOLD_SITE)
        self.assertLess(CHART_SITE - 0x0042532E, 0x30)
        self.assertLess(SOLD_SITE - 0x0042399B, 0x40)

    def test_esi_is_the_screen_at_each_site(self) -> None:
        """Each draw keeps its screen in esi (`mov esi, ecx` at its start) and never writes esi before
        the site, so the stub can hand it over."""
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        va0, code = _text_section(FISH_EXE)
        for start, site in ((0x004252C0, CHART_SITE), (0x00423800, SOLD_SITE)):
            texts = [f"{i.mnemonic} {i.op_str}" for i in md.disasm(code[start - va0: site - va0], start)]
            writes = [t for t in texts if re.match(r"(mov|lea|pop|xchg|add|sub|xor) esi,", t)]
            self.assertEqual(writes, ["mov esi, ecx"], hex(site))

    def test_no_other_companion_or_patch_writes_them(self) -> None:
        import json
        for source in sorted((ROOT / "native").rglob("*.[ch]")):
            if source.parent.name == "ftfp_ds_store":
                continue
            text = source.read_text(encoding="utf-8", errors="replace").upper()
            for va in (CHART_SITE, SOLD_SITE):
                self.assertNotIn(f"0X{va:08X}", text, source)
                self.assertNotIn(f"0X{va:X}", text, source)
        manifest = json.loads((ROOT / "data" / "fish_manifest.json").read_text(encoding="utf-8"))
        for patch in manifest["patches"]:
            if patch.get("file_path") != "Fish Tycoon.exe":
                continue
            start = int(patch["offset"], 16) + 0x400000
            end = start + len(patch["expected"].split())
            for va in (CHART_SITE, SOLD_SITE):
                self.assertFalse(start < va + 5 and va < end, (patch["id"], hex(va)))

    def test_the_install_writes_both(self) -> None:
        source = STORE_C.read_text(encoding="utf-8")
        self.assertIn("CALL(w++, CHART_PRICE, stub_chart_price);", source)
        self.assertIn("CALL(w++, SOLD_PRICE, stub_sold_price);", source)
        self.assertIn("#define TOTAL_SITES 35", source)
        self.assertEqual(len(re.findall(r"^\s+(?:JMP|CALL|SLOT)\(w\+\+|^\s+ftfp_site_branch\(w\+\+", source, re.M)), 35)


def _ready() -> bool:
    return RMP._toolchain() and FISH_EXE.is_file() and XT is not None


@unittest.skipUnless(_ready(), "needs Unicorn, the pinned MSVC toolset and the vanilla executable")
class Displays(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dll, cls.symbols = E.build_with_map("ftfp_ds_store", RMP.FISH_DLL, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # ------------------------------------------------------------ the rig
    def rig(self, hooked: bool = True, german: bool = False):
        rig, scene = RMP.FishSales.rig(self, rolls=lambda n: 0)        # its rig, with this class's DLL
        emu = rig.emu
        if not hooked:                                                 # the vanilla call back in place
            emu.uc.mem_write(0x004244D4, bytes([0xE8]) + struct.pack("<i", 0x00424010 - 0x004244D9))
        else:
            RMP.branch(emu, CHART_SITE, rig.store["_stub_chart_price"], 5, 0xE8)
            RMP.branch(emu, SOLD_SITE, rig.store["_stub_sold_price"], 5, 0xE8)
        lang = emu.alloc(4)
        emu.write32(lang, 1 if german else 0)
        emu.write32(0x0045B314, lang)
        rig.texts = []
        table = emu.alloc(16)
        label = emu.text("Price:")
        emu.hook(0x00427060, lambda e: table, 0)
        emu.hook(0x00427050, lambda e: label, 4)

        def sprintf(e) -> int:
            fmt = e.cstring(e.arg(1)).decode("latin-1")
            out = fmt.replace("%d", str(e.read32(e.uc.reg_read(RMP.X.UC_X86_REG_ESP) + 12, signed=True)), 1)
            e.uc.mem_write(e.arg(0), out.encode("latin-1") + b"\0")
            return len(out)
        emu.hook(SPRINTF, sprintf, 0)
        emu.hook(LEFT_TEXT, lambda e: rig.texts.append(
            ("left", e.cstring(e.arg(0)).decode("latin-1"), e.arg(1), e.arg(2), e.arg(3), e.arg(4))) or 0, 0x14)
        emu.hook(CENTRE_TEXT, lambda e: rig.texts.append(
            ("centre", e.cstring(e.arg(0)).decode("latin-1"), e.arg(1), e.arg(2), e.arg(3), e.arg(4), e.arg(5)))
            or 0, 0x18)
        emu.hook(0x00408B90, lambda e: 0, 0x14)                        # right-aligned ("Fish for sale" count)
        emu.hook(0x00408BE0, lambda e: 0, 0x14)                        # centred names
        emu.hook(0x00408D60, lambda e: 0, 4)                           # the background
        emu.hook(0x00419290, lambda e: emu.text("name"), 0xC)          # a species' name (3 arguments)
        emu.hook(0x00415350, lambda e: 0, 0xC)                         # a fish picture
        emu.hook(0x00419ED0, lambda e: 0, 4)
        emu.hook(0x0041BE70, lambda e: 0, 4)
        emu.hook(0x00408A40, lambda e: 0, 0xC)
        emu.write32(PRICE_COLOUR, 0x00FFCC33)
        return rig, scene

    def chart(self, rig) -> list[tuple]:
        emu = rig.emu
        chart = emu.alloc(0x40)
        emu.write32(chart + 0x04, rig.state)
        emu.write32(chart + 0x0C, emu.alloc(0x10))                     # the graphics
        emu.write32(chart + 0x18, CHART_FONT)
        emu.write32(0x004572A0, 0x00FFFFFF)                            # the chart's label colour
        emu.write32(0x004572B8, 0x00FFCC33)                            # and its price colour
        rig.texts.clear()
        emu.call(0x004252C0, ecx=chart)
        return [t for t in rig.texts]

    def store(self, rig, scene) -> list[tuple]:
        emu = rig.emu
        emu.write32(scene + 0x80, emu.alloc(0x10))                     # the graphics
        emu.write32(scene + 0x90, SALE_FONT)
        rig.texts.clear()
        emu.call(0x00423800, ecx=scene)
        return [t for t in rig.texts]

    def isolate(self, rig, record: bytes) -> None:
        rig.emu.uc.mem_write(rig.state + ISOLATION, record)

    def guppy(self, dosed: bool) -> bytes:
        f = XT.fish(XT.NOW, 7, 7, 25, 90, 60)
        return RMP.treated(f) if dosed else f

    def sell(self, rig, scene, record: bytes) -> int:
        before = rig.get(RMP.S_MONEY)
        rig.put_tank(2, XT.block_with({5: record}))
        rig.emu.write32(scene + 0x58, 0)
        rig.emu.call(rig.sym["@roll_hook@12"], 10, ecx=scene)
        return rig.get(RMP.S_MONEY) - before

    def set_asking(self, rig, price: int) -> None:
        """The asking price; the rig's base price B (+0x24) is raised with it so it still sells (the
        sale roll never sells at 2B or more)."""
        at = RMP.entry_at(rig.state, 7, 7)
        rig.emu.write32(at + 0x20, price)
        rig.emu.write32(at + 0x24, max(ASKING, price))

    # ------------------------------------------------------------ the Species Chart
    def test_the_chart_of_a_treated_fish_shows_the_treated_price_the_sale_pays(self) -> None:
        for asking in (ASKING, 300, 600):
            with self.subTest(asking=asking):
                rig, scene = self.rig()
                self.set_asking(rig, asking)
                self.isolate(rig, self.guppy(True))
                texts = self.chart(rig)
                paid = self.sell(rig, scene, self.guppy(True))
                self.assertEqual(paid, max(GUPPY_MAX, asking))
                self.assertEqual(texts, [
                    ("left", "Price:", 560, 95, 0x00FFFFFF, CHART_FONT),
                    ("left", f"${asking}", 640, 95, 0x00FFCC33, CHART_FONT),
                    ("left", f"Treated: ${paid}", 560, 121, 0x00FFCC33, 0),
                ])

    def test_the_chart_of_an_untreated_fish_is_the_vanilla_chart(self) -> None:
        for fish in (self.guppy(False), XT.fish(XT.NOW, 7, 7, 25, health=0)):
            vanilla, _ = self.rig(hooked=False)
            patched, _ = self.rig()
            for rig in (vanilla, patched):
                self.isolate(rig, fish)
            self.assertEqual(self.chart(patched), self.chart(vanilla))
            self.assertEqual(len(self.chart(patched)), 2)
        # An empty isolation tank, and a treated mark left in an empty record: nothing.
        rig, _ = self.rig()
        empty = bytearray(RMP.SLOT)
        struct.pack_into("<I", empty, RMP.F_MARK, RMP.MARK)
        self.isolate(rig, bytes(empty))
        self.assertEqual([t[1] for t in self.chart(rig)], ["Price:", "$40"])

    def test_a_treated_ds_fish_on_the_chart(self) -> None:
        """A DS body's price comes from DS Exclusive Fish's row (FtfpDsFishEntry), as the sale's does."""
        rig, scene = self.rig()
        body, fin = 29, 29
        at = RMP.entry_at(rig.state, body, fin)
        rig.emu.write32(at + 0x20, ASKING)
        rig.emu.write32(at + 0x24, ASKING)
        rig.ds_entries[(body, fin)] = at
        record = RMP.treated(XT.fish(XT.NOW, body, fin, 25, 90, 60))
        self.isolate(rig, record)
        texts = self.chart(rig)
        expected = RMP.BF.FishModel(extras=True).prices((body, fin), "max").highest_selling
        self.assertEqual(texts[-1][1], f"Treated: ${expected}")
        self.assertEqual(self.sell(rig, scene, record), expected)

    def test_german(self) -> None:
        rig, _ = self.rig(german=True)
        self.isolate(rig, self.guppy(True))
        self.assertEqual(self.chart(rig)[-1][1], f"Behandelt: ${GUPPY_MAX}")

    # ------------------------------------------------------------ the Fish Store
    def test_a_treated_sale_shows_the_set_price_and_the_treated_price_paid(self) -> None:
        rig, scene = self.rig()
        paid = self.sell(rig, scene, self.guppy(True))
        self.assertEqual(paid, GUPPY_MAX)
        texts = self.store(rig, scene)
        self.assertIn(("left", f"${ASKING}", 304, 480, 0x00FFCC33, SALE_FONT), texts, "the set price, as stock")
        self.assertEqual(texts[-1], ("centre", f"Treated: ${paid}", 25, 209, 507, 0x00FFCC33, 0))
        self.assertEqual(sum(t[0] == "centre" for t in texts), 1)

    def test_an_untreated_sale_is_the_vanilla_store(self) -> None:
        vanilla, vscene = self.rig(hooked=False)
        patched, pscene = self.rig()
        self.assertEqual(self.sell(vanilla, vscene, self.guppy(False)), ASKING)
        self.assertEqual(self.sell(patched, pscene, self.guppy(False)), ASKING)
        self.assertEqual(self.store(patched, pscene), self.store(vanilla, vscene))
        self.assertNotIn("centre", [t[0] for t in self.store(patched, pscene)])

    def test_the_next_untreated_sale_drops_the_treated_price(self) -> None:
        rig, scene = self.rig()
        self.sell(rig, scene, self.guppy(True))
        self.assertEqual(self.store(rig, scene)[-1][1], f"Treated: ${GUPPY_MAX}")
        self.sell(rig, scene, self.guppy(False))
        self.assertNotIn("centre", [t[0] for t in self.store(rig, scene)])
        # Before any sale there is no sold fish and nothing treated to show.
        fresh, fscene = self.rig()
        self.assertNotIn("centre", [t[0] for t in self.store(fresh, fscene)])

    def test_a_treated_fish_asking_more_than_the_max(self) -> None:
        """The sale pays the asking price then (never less), and that is the treated price shown."""
        rig, scene = self.rig()
        self.set_asking(rig, 600)
        self.assertEqual(self.sell(rig, scene, self.guppy(True)), 600)
        texts = self.store(rig, scene)
        self.assertIn("$600", [t[1] for t in texts])
        self.assertEqual(texts[-1][1], "Treated: $600")


class Texts(unittest.TestCase):
    def test_game_mechanics_names_the_two_screens_and_nowhere_else(self) -> None:
        import game_mechanics as GM
        rendered = GM.render_text(GM.load_page("fish"))
        for words in ("Allows treated fish to sell at max price, regardless of their set value.",
                      "the Fish Store (the selling screen Sell Fish opens", "\"Treated: $475\"",
                      "the Species Chart (the window where you set a price", "not in any tank (the Sale Tank included)"):
            self.assertIn(words, rendered)

    def test_the_patcher_description(self) -> None:
        import json
        manifest = json.loads((ROOT / "data" / "fish_manifest.json").read_text(encoding="utf-8"))
        text = next(s for s in manifest["settings"] if s["id"] == "ds_store")["description"]
        self.assertIn("\"Treated: $<price>\" in the Fish Store", text)
        self.assertIn("Species Chart", text)


if __name__ == "__main__":
    unittest.main()
