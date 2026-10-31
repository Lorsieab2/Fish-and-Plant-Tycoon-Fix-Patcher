"""The Breeding Guide's picture tabs (src/breeding_pictures.py).

They are built headless from tiny synthetic sprite files laid out like the games' own
(no game art is in the repo): Fish Tycoon's sheets in an Assets\\ft.dat ZIP plus DS
sheets in Images (disk wins, as the game's loader 0x409B00), Plant Tycoon's in Images.
Checked: the grouping by rarity in the games' words, spoilers on and off, a missing art
folder, and, with the vanilla executables, that the art tables are the games' own.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_fish as bf  # noqa: E402
import breeding_guide as bg  # noqa: E402
import breeding_pictures as bpx  # noqa: E402
import breeding_plant as bp  # noqa: E402
from test_breeding_guide import make_documents, tk_root  # noqa: E402

VANILLA = Path(os.environ.get("TYCOON_VANILLA_GAMES", str(
    Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games")))


def png(width: int, height: int, rgba=(200, 40, 40, 255)) -> bytes:
    """A plain RGBA PNG, written with the standard library."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\0" + bytes(rgba) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def make_fish_copy(root: Path, skip=()) -> Path:
    copy = root / "Fish Tycoon"
    (copy / "Assets").mkdir(parents=True)
    (copy / "Images").mkdir()
    with zipfile.ZipFile(copy / "Assets" / "ft.dat", "w") as dat:
        for g in bf.PC_GENES:
            dat.writestr(f"fish_{g:02d}_body_grid.png", png(14, 6))
            dat.writestr(f"fish_{g:02d}_top_grid.png", png(26, 4))
            dat.writestr(f"fish_{g:02d}_bot_grid.png", png(26, 4))
        for _name, _tier, file in bpx.FISH_EGGS:
            if file not in skip:
                dat.writestr(file.lower(), png(3, 3))
    for g in bf.DS_GENES:                                      # the patcher's DS sheets, on disk
        for part, (w, h) in (("body", (14, 6)), ("top", (26, 4)), ("bot", (26, 4))):
            (copy / "Images" / f"FISH_{g}_{part}_Grid.png").write_bytes(png(w, h))
    (copy / "Images" / bpx.EXOTIC_EGGS[2]).write_bytes(png(3, 3))
    return copy


def make_plant_copy(root: Path) -> Path:
    copy = root / "Plant Tycoon"
    images = copy / "Images"
    images.mkdir(parents=True)
    for name, cols, rows in bpx.FLOWER_SHEETS.values():
        (images / name.replace("grid", "Grid")).write_bytes(png(2 * cols, 2 * rows))   # case as shipped varies
    for name in bpx.FOLIAGE_ART.values():
        (images / name).write_bytes(png(4, 4))
    for name, cols, rows in (bpx.SEED_SHEET, bpx.LEGENDARY_SHEET):
        (images / name).write_bytes(png(2 * cols, 2 * rows))
    return copy


class GroupTests(unittest.TestCase):
    def test_parts_are_grouped_by_rarity_in_the_games_words(self) -> None:
        for model, kind, order in ((bf.load(None, True), "fin", ["Common", "Unusual", "Rare"]),
                                   (bf.load(None, False), "body", ["Common", "Unusual", "Rare"]),
                                   (bp.load(None, True), "flower", ["Common", "Endangered", "Extinct", "Legendary"]),
                                   (bp.load(None, False), "foliage", ["Common", "Endangered", "Extinct"])):
            groups = bpx.part_items(bg.View(model, set(), spoilers=True), kind)
            self.assertEqual([g.tier for g in groups], order)
            names = []
            for group in groups:
                for item in group.items:
                    part = next(p for p in model.parts(kind) if p.name == item.name)
                    self.assertEqual(model.part_rarity(part), group.tier)
                    self.assertTrue(item.art)
                    names.append(item.name)
            self.assertEqual(sorted(names), sorted(p.name for p in model.parts(kind)))

    def test_eggs_and_seeds(self) -> None:
        eggs = bpx.egg_items(bg.View(bf.load(None, True), set(), spoilers=True))
        self.assertEqual([g.tier for g in eggs], ["Common", "Unusual", "Rare", "Exotic (DS Store Items)"])
        self.assertEqual(len(bpx.egg_items(bg.View(bf.load(None, False), set(), spoilers=True))), 3)
        seeds = bpx.seed_items(bg.View(bp.load(None, True), set(), spoilers=True))
        self.assertEqual([g.tier for g in seeds], ["Common", "Endangered", "Extinct", "Legendary"])
        self.assertEqual(len(seeds[0].items), len(bp.COMMON_GENES))
        self.assertEqual(len(seeds[2].items), 2 * len(bp.EXTINCT_GENES))
        self.assertEqual(seeds[0].items[0].art[0].index, bpx.seed_frame(1, 0))
        self.assertEqual(seeds[3].items[0].art[0].index, 95 + 1)
        self.assertEqual(bpx.seed_frame(7, 1), 25)                # Fern, an Endangered flower

    def test_spoilers_off_hides_undiscovered_parts(self) -> None:
        view = bg.View(bf.load(None, False), {(0, 0), (4, 4)}, spoilers=False)
        fins = [i for g in bpx.part_items(view, "fin") for i in g.items]
        self.assertEqual(sorted(i.name for i in fins), ["Pink", "Silky"])     # the others are left out, no "?"
        self.assertTrue(all(i.art and not i.hidden for i in fins))
        seeds = [i for g in bpx.seed_items(bg.View(bp.load(None, False), {(1, 1)}, spoilers=False)) for i in g.items]
        self.assertEqual([i.name for i in seeds], ["Reptans seed"])

    def test_the_rarest_packets_name_only_discovered_flowers(self) -> None:
        """An Extinct foliage's second packet is "the rarest flowers"; it names Arthurium and
        Tilia only when both are discovered (or with spoilers)."""
        model = bp.load(None, False)
        for found, spoilers, words in (({(2, 1)}, False, "(the rarest flowers)"),
                                       ({(2, 18), (2, 23)}, False, "(Arthurium to Tilia flower)"),
                                       ({(2, 18)}, False, "(the rarest flowers)"),
                                       (set(), True, "(Arthurium to Tilia flower)")):
            seeds = [i.name for g in bpx.seed_items(bg.View(model, found, spoilers)) for i in g.items]
            self.assertIn(f"Scandens seed {words}", seeds, found)
            if not spoilers:
                self.assertEqual({n.split(" seed")[0] for n in seeds}, {"Scandens"})


class ArtSourceTests(unittest.TestCase):
    def test_disk_wins_over_the_dat_and_names_ignore_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copy = make_fish_copy(Path(tmp))
            (copy / "Images" / "FISH_00_BODY_GRID.png").write_bytes(b"disk")
            source = bpx.ArtSource(copy)
            self.assertEqual(source.problem, "")
            self.assertEqual(source.read("fish_00_body_Grid.png"), b"disk")
            self.assertTrue(source.read("fish_01_body_grid.png").startswith(b"\x89PNG"))
            self.assertIsNone(source.read("nothing.png"))
            source.close()

    def test_missing_or_broken_art(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("No game copy", bpx.ArtSource(None).problem)
            self.assertIn("No game images", bpx.ArtSource(Path(tmp) / "gone").problem)
            broken = Path(tmp) / "broken"
            (broken / "Assets").mkdir(parents=True)
            (broken / "Assets" / "ft.dat").write_bytes(b"not a zip")
            self.assertIn("could not be read", bpx.ArtSource(broken).problem)

    @unittest.skipUnless((VANILLA / "Fish Tycoon" / "Assets" / "ft.dat").is_file(), "needs a local Fish Tycoon copy")
    def test_reads_a_real_copy(self) -> None:
        source = bpx.ArtSource(VANILLA / "Fish Tycoon")
        for g in bf.PC_GENES:
            for art in bpx.part_art(bf.load(None, False), "body", g) + bpx.part_art(bf.load(None, False), "fin", g):
                self.assertIsNotNone(source.read(art.file), art.file)
        for _n, _t, file in bpx.FISH_EGGS:
            self.assertIsNotNone(source.read(file))
        source.close()
        plant = bpx.ArtSource(VANILLA / "Plant Tycoon")
        model = bp.load(None, False)
        for kind in ("flower", "foliage"):
            for part in model.parts(kind):
                for art in bpx.part_art(model, kind, part.index):
                    self.assertIsNotNone(plant.read(art.file), art.file)
        self.assertIsNotNone(plant.read(bpx.SEED_SHEET[0]))


class WindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display for Tk")
        self.tmp = tempfile.TemporaryDirectory()
        self.documents = make_documents(Path(self.tmp.name))
        bg._open_window = None
        self.settings = {"show_spoilers": True}
        self.guide = bg.open_window(self.root, "fish", settings=self.settings, documents=self.documents)
        self.root.update()

    def tearDown(self) -> None:
        self.guide.close()
        self.root.destroy()
        self.tmp.cleanup()

    def use(self, copy) -> None:
        self.guide.art_source = lambda: bpx.ArtSource(copy)
        self.guide._refresh()
        self.root.update()

    def tabs(self) -> list[str]:
        nb = self.guide.notebook
        return [nb.tab(t, "text") for t in nb.tabs()]

    def test_fish_picture_tabs(self) -> None:
        self.use(make_fish_copy(Path(self.tmp.name)))
        for title in ("Fin Pictures", "Body Pictures", "Egg Pictures"):
            self.assertIn(title, self.tabs())
        for tab_id in ("pictures:fin", "pictures:body", "pictures:eggs"):
            built = self.guide.pictures[tab_id]
            self.assertEqual(built["message"].cget("text"), "")
            for item, image, label in built["cells"]:
                self.assertIsNotNone(image, item.name)
                self.assertIn(item.tier, label)
                self.assertIn(item.name, label)
        fin = self.guide.pictures["pictures:fin"]["cells"][0][1]
        self.assertEqual((fin.width(), fin.height()), (2, 4))           # top fin cell over bottom fin cell

    def test_spoilers_off_shows_only_the_discovered_parts(self) -> None:
        """No "?" cells: an undiscovered part is left out, as on the part sheets, and the count
        of discovered parts is at the top."""
        self.use(make_fish_copy(Path(self.tmp.name)))
        self.guide.spoilers_var.set(False)
        self.root.update()
        built = self.guide.pictures["pictures:body"]
        cells = built["cells"]
        self.assertFalse([c for c in cells if c[0].hidden])
        for item, image, label in cells:
            self.assertIsNotNone(image, item.name)
            self.assertNotIn("Undiscovered", label)
        self.assertEqual({c[0].name for c in cells}, {"Shark", "Fatfish", "Goldbulb", "Spotanus", "Idle", "Quicksilver"})
        self.assertEqual(built["header"].cget("text"),
                         "6 of 28 bodies discovered (7 of them DS Exclusive Fish, 1 discovered).")
        self.guide.spoilers_var.set(True)
        self.root.update()
        self.assertEqual(len(self.guide.pictures["pictures:body"]["cells"]), 28)

    def test_missing_art_folder_is_said_not_raised(self) -> None:
        self.use(Path(self.tmp.name) / "no such copy")
        self.assertEqual(self.guide.build_errors, [])
        built = self.guide.pictures["pictures:body"]
        self.assertIn("No game images", built["message"].cget("text"))
        self.assertTrue(all(image is None for _i, image, _l in built["cells"]))
        # a copy missing one file: that picture says so, the rest are drawn
        copy = make_fish_copy(Path(self.tmp.name) / "partial", skip=("ITEM_FISHEGGS_RARE.png",))
        self.use(copy)
        built = self.guide.pictures["pictures:eggs"]
        self.assertIn("1 picture(s) could not be read", built["message"].cget("text"))
        self.assertEqual(sum(image is None for _i, image, _l in built["cells"]), 1)

    def test_plant_picture_tabs(self) -> None:
        copy = make_plant_copy(Path(self.tmp.name))
        self.guide.game_var.set("Plant Tycoon")
        self.root.update()
        self.use(copy)
        for tab_id in ("pictures:flower", "pictures:foliage", "pictures:seeds"):
            built = self.guide.pictures[tab_id]
            self.assertEqual(built["message"].cget("text"), "", tab_id)
            self.assertTrue(built["cells"])
            self.assertTrue(all(image is not None for _i, image, _l in built["cells"]), tab_id)
        # Seed Pictures is a grid (tests/test_breeding_collectopedia.py: SeedGridTests)
        columns, rows = self.guide.pictures["pictures:seeds"]["grid"]
        self.assertEqual(columns, ["Common", "Endangered", "Extinct", "Extinct (Arthurium to Tilia flower)"])
        self.assertEqual(len(self.guide.pictures["pictures:seeds"]["cells"]), 4 * 23)

    def test_export_on_a_picture_tab_does_nothing(self) -> None:
        self.use(make_fish_copy(Path(self.tmp.name)))
        nb = self.guide.notebook
        nb.select(nb.tabs()[self.tabs().index("Egg Pictures")])
        self.root.update()
        self.assertIsNone(self.guide.export("csv", str(Path(self.tmp.name) / "eggs.csv")))


def _exe_reader(path: Path):
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    sections = [struct.unpack_from("<IIII", data, pe + 24 + opt + i * 40 + 8) for i in range(count)]

    def at(va: int) -> int:
        r = va - 0x400000
        for _vs, rva, rs, raw in sections:
            if rva <= r < rva + rs:
                return raw + r - rva
        raise KeyError(hex(va))
    return data, at


PLANT_EXE = VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"


@unittest.skipUnless(PLANT_EXE.is_file(), "needs the vanilla Plant Tycoon.exe")
class PlantArtTablesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data, self.at = _exe_reader(PLANT_EXE)

    def test_flower_art_records_are_the_games(self) -> None:
        for gene in range(1, 24):
            record = struct.unpack_from("<7i", self.data, self.at(0x48E6B8) + 28 * gene)
            self.assertEqual(record[0], gene)
            self.assertEqual((record[2], record[4]), bpx.FLOWER_ART[gene], gene)
        source = (ROOT / "native" / "ftfp_new_flowers" / "ftfp_new_flowers.c").read_text(encoding="utf-8")
        for gene, sheet, cell in re.findall(r"\{ (\d+), 5, (\d+), \d+, (\d+),", source):
            self.assertEqual(bpx.FLOWER_ART[int(gene)], (int(sheet), int(cell)))

    def test_sprite_table_names(self) -> None:
        names = {}
        # the sprite table at 0x485E80: {.., id at +0x10, name at +0x14}, 0x34 bytes an entry
        start = self.at(0x485E9C)
        for k in range(0, 60):
            sid, name_va = struct.unpack_from("<II", self.data, start + 0x34 * k + 0x10)
            try:
                o = self.at(name_va)
            except KeyError:
                continue
            names[sid] = self.data[o:self.data.index(b"\0", o)].decode("latin-1")
        for sheet, (file, _c, _r) in bpx.FLOWER_SHEETS.items():
            self.assertEqual(names[sheet].casefold(), file.casefold())
        self.assertEqual(names[0x2E].casefold(), bpx.SEED_SHEET[0].casefold())
        self.assertEqual(set(bpx.FOLIAGE_ART.values()), {names[i] for i in range(0x39, 0x50)})

    def test_foliage_classes_and_seed_frames_are_the_games(self) -> None:
        """The plant factory's switch (0x42EE61: case = (foliage - 1) % 23 + 1, table 0x42F3B0)
        and each case's class (its constructor's vtable, the RTTI name); the seed frame rule
        at 0x41DD54 ((foliage - 1) x 4, then + 3 / + 2 / + 1 by the flower)."""
        try:
            import capstone
        except ImportError:
            self.skipTest("needs capstone")
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        table = struct.unpack_from("<24I", self.data, self.at(0x42F3B0))
        for foliage in range(1, 24):
            case = table[foliage]
            code = self.data[self.at(case):self.at(case) + 80]
            ctor = next(int(i.op_str, 16) for i in md.disasm(code, case)
                        if i.mnemonic == "call" and i.op_str != "0x44e894")
            vt = next(int(i.op_str.rsplit(", ", 1)[1], 16) for i in md.disasm(self.data[self.at(ctor):self.at(ctor) + 0x1800], ctor)
                      if i.mnemonic == "mov" and i.op_str.startswith("dword ptr [e")
                      and re.search(r", (0x[0-9a-f]+)$", i.op_str)
                      and int(i.op_str.rsplit(", ", 1)[1], 16) > 0x460000)
            col = struct.unpack_from("<I", self.data, self.at(vt - 4))[0]
            td = struct.unpack_from("<I", self.data, self.at(col + 0xC))[0]
            o = self.at(td + 8)
            name = self.data[o:self.data.index(b"\0", o)].decode()
            self.assertEqual(name, f".?AV{bpx.FOLIAGE_CLASSES[foliage]}@@", foliage)
        code = self.data[self.at(0x41DD54):self.at(0x41DD54) + 0x60]
        text = " | ".join(f"{i.mnemonic} {i.op_str}" for i in md.disasm(code, 0x41DD54))
        self.assertIn("lea ecx, [eax*4 - 4]", text)
        for step in ("add ecx, 3", "add ecx, 2", "add ecx, 1"):
            self.assertIn(step, text)


if __name__ == "__main__":
    unittest.main()
