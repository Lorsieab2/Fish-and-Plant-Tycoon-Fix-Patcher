"""Game Mechanics, Plant Tycoon, "How many seeds you can hold": every number is the code's.

The constants are read from the vanilla executable's own instructions (skipped when it is missing)
and from the companions' sources, and each number on the page is worked out from them.
"""

from __future__ import annotations

import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import game_mechanics_plant as GM  # noqa: E402

VANILLA = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Plant Tycoon"
           / "Plant Tycoon.exe")


def define(path: Path, name: str) -> int:
    return int(re.search(rf"#define {name} (\d+)", path.read_text(encoding="utf-8")).group(1))


def page_text() -> str:
    def walk(facts):
        for f in facts:
            yield f.text
            yield from (f.subs or ())
            for _sid, text in (f.patched or ()):
                yield text
    return "\n".join(walk(GM.SEED_CAPACITY))


BOXES_C = ROOT / "native" / "ftfp_seed_boxes" / "ftfp_seed_boxes.c"
UPGRADES_C = ROOT / "native" / "ftfp_plant_upgrades" / "ftfp_plant_upgrades.c"
GREENHOUSES_C = ROOT / "native" / "ftfp_extra_greenhouses" / "ftfp_extra_greenhouses.c"


class SeedCapacityTests(unittest.TestCase):
    def constants(self) -> dict[str, int]:
        c = {
            "records": define(BOXES_C, "BOX_RECORDS"),
            "chests": define(BOXES_C, "CHESTS"),
            "boxes_per_chest": define(BOXES_C, "BOXES_PER_CHEST"),
            "extra_boxes": define(BOXES_C, "EXTRA_BOXES"),
            "pots": define(UPGRADES_C, "POTS"),
            "extra_greenhouses": define(UPGRADES_C, "EXTRA_COUNT"),
            "rows_per_drawer": 4, "columns": 10, "tray": 8, "ripe": 5,
        }
        if VANILLA.is_file():
            exe = VANILLA.read_bytes()
            pe = struct.unpack_from("<I", exe, 0x3C)[0]
            table = pe + 24 + struct.unpack_from("<H", exe, pe + 20)[0]
            sections = [struct.unpack_from("<IIII", exe, table + 40 * i + 8)
                        for i in range(struct.unpack_from("<H", exe, pe + 6)[0])]

            def at(va: int, n: int) -> bytes:
                for _size, rva, raw_size, raw in sections:
                    if rva <= va - 0x400000 < rva + raw_size:
                        start = raw + va - 0x400000 - rva
                        return exe[start:start + n]
                raise ValueError(hex(va))
            self.assertEqual(at(0x4245FD, 7), bytes.fromhex("8D3C8504000000"))     # lea edi, [eax*4 + 4]: rows
            self.assertEqual(at(0x424622, 3), bytes.fromhex("83F80A"))             # cmp eax, 10: columns
            self.assertEqual(at(0x430910, 3), bytes.fromhex("83F808"))             # cmp eax, 8: tray slots
            self.assertEqual(at(0x42E0E0, 3) + at(0x42E0E5, 5), bytes.fromhex("83F805B805000000"))   # min(.., 5)
        return c

    def test_the_numbers_match_the_code(self) -> None:
        c = self.constants()
        drawer = c["rows_per_drawer"] * c["columns"]
        self.assertEqual(drawer * c["boxes_per_chest"], c["records"])          # a chest is three drawers
        self.assertEqual(c["chests"] * c["boxes_per_chest"], 3 + c["extra_boxes"])
        stock, six, nine = 3 * drawer, 6 * drawer, c["chests"] * c["records"]
        on_plants = c["ripe"] * c["pots"]
        greenhouses = 1 + c["extra_greenhouses"]
        text = page_text()
        for line in (f"4 rows x 10 slots = {drawer} seeds", f"12 rows x 10 = {c['records']} records",
                     f"3 x {drawer} = {stock} seeds", f"6 x {drawer} = {six} seeds", f"9 x {drawer} = {nine} seeds",
                     f"holds {c['tray']} more", f"{stock + c['tray']}, {six + c['tray']} or {nine + c['tray']}",
                     f"at most {c['ripe']} seeds", f"has {c['pots']} pots", f"{c['ripe']} x {c['pots']} = {on_plants}",
                     f"({greenhouses} greenhouses of {c['pots']} pots): {c['ripe']} x {c['pots']} x {greenhouses} = "
                     f"{on_plants * greenhouses}",
                     f"Stock: {stock} + {c['tray']} + {on_plants} = {stock + c['tray'] + on_plants}",
                     f"{six} + {c['tray']} + {on_plants} = {six + c['tray'] + on_plants}",
                     f"{nine} + {c['tray']} + {on_plants} = {nine + c['tray'] + on_plants}",
                     f"{nine} + {c['tray']} + {on_plants * greenhouses} = {nine + c['tray'] + on_plants * greenhouses}"):
            self.assertIn(line, text)

    def test_the_section_is_on_the_page(self) -> None:
        titles = [g.title for g in GM.page().groups]
        self.assertIn("How many seeds you can hold", titles)
        self.assertEqual(titles.index("How many seeds you can hold"), titles.index("Tools and shears") + 1)


if __name__ == "__main__":
    unittest.main()
