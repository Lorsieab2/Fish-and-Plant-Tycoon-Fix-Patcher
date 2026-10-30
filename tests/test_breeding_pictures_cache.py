"""The Breeding Guide's own picture cache and how it finds a game copy (src/breeding_pictures.py,
src/breeding_guide.py).

Checked: the lookup finds the "- Modded" and "- Modded Upgrades" copies from the folders the
patcher knows (its output folder and copies, the Game tab's game folder, default installs);
the cache is built from a fake game copy, all or nothing, and from the read-only vanilla
copies when they are on this machine; the guide shows its pictures from the cache with no
game copy anywhere; a corrupt or partial cache is rebuilt, never used; and nothing is ever
written to the game copy or the saves.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import breeding_guide as bg  # noqa: E402
import breeding_pictures as bpx  # noqa: E402
import store_emulator as E  # noqa: E402
from test_breeding_guide import make_documents, tk_root  # noqa: E402
from test_breeding_pictures import make_fish_copy, make_plant_copy  # noqa: E402


def snapshot(folder: Path) -> dict[str, str]:
    """Every file under a folder with its SHA-256 and modification time."""
    out = {}
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file():
            out[str(path.relative_to(folder))] = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    return out


def add_exe(copy: Path, exe: str) -> Path:
    (copy / f"{exe}.exe").write_bytes(b"MZ")
    return copy


def fish_copy(parent: Path, name: str) -> Path:
    """A fake Fish Tycoon copy named `name` (its exe named after it, as the patcher makes them)."""
    copy = make_fish_copy(parent / f".{name}.tmp")
    target = parent / name
    copy.rename(target)
    (parent / f".{name}.tmp").rmdir()
    return add_exe(target, name)


def plant_copy(parent: Path, name: str) -> Path:
    copy = make_plant_copy(parent / f".{name}.tmp")
    target = parent / name
    copy.rename(target)
    (parent / f".{name}.tmp").rmdir()
    return add_exe(target, name)


class CacheTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.cache_root = self.base / "patcher" / bpx.CACHE_FOLDER
        self._old_root = bpx.CACHE_ROOT
        bpx.CACHE_ROOT = self.cache_root

    def tearDown(self) -> None:
        bpx.CACHE_ROOT = self._old_root
        self.tmp.cleanup()


class LookupTests(CacheTestCase):
    def layout(self):
        """The owner's layout: the "- Modded" copy is gone, "- Modded Upgrades" sits beside
        where it was, and the vanilla game is elsewhere; the settings still name "- Modded"."""
        modded = self.base / "Modded Games"
        modded.mkdir()
        upgrades = fish_copy(modded, "Fish Tycoon - Modded Upgrades")
        plant_upgrades = plant_copy(modded, "Plant Tycoon - Modded Upgrades")
        vanilla_parent = self.base / "Vanilla Games"
        vanilla_parent.mkdir()
        vanilla = fish_copy(vanilla_parent, "Fish Tycoon")
        return modded, upgrades, plant_upgrades, vanilla

    def tools_parents(self, modded: Path, vanilla: Path) -> list[str]:
        """What the Tools tab passes the guide for these settings (tools_tab.breeding)."""
        import tools_tab
        captured = {}

        def var(value):
            return SimpleNamespace(get=lambda: value)
        app = SimpleNamespace(
            output_parent=var(str(modded)), game_choice=var("fish"), breeding_settings={}, _save_settings=lambda: "",
            path_vars={"fish": {"output": var(str(modded / "Fish Tycoon - Modded")), "vanilla": var(str(vanilla))},
                       "plant": {"output": var(""), "vanilla": var("")}})
        old = bg.open_window
        bg.open_window = lambda *a, **k: captured.update(k)
        try:
            tools_tab.ToolsTab.breeding(SimpleNamespace(app=app), "fish")
        finally:
            bg.open_window = old
        return captured["game_parents"]

    def test_modded_save_finds_the_upgrades_copy_and_the_game_tab_folder(self) -> None:
        modded, upgrades, plant_upgrades, vanilla = self.layout()
        parents = self.tools_parents(modded, vanilla)
        self.assertIn(str(vanilla), parents)                        # the Game tab's folder is passed now
        save = self.base / "LDW" / "Fish Tycoon - Modded"
        self.assertIsNone(bg.find_game_copy(save, bg.lookup_parents(parents)))   # its own copy is gone
        copies = bg.art_copies("fish", save, parents)
        self.assertEqual(copies[0], upgrades)
        self.assertIn(vanilla, copies)
        self.assertNotIn(plant_upgrades, copies)
        self.assertEqual(bg.art_copies("plant", self.base / "LDW" / "Plant Tycoon - Modded", parents),
                         [plant_upgrades])

    def test_each_save_folder_maps_to_its_own_copy_first(self) -> None:
        modded, upgrades, _p, vanilla = self.layout()
        plain = fish_copy(modded, "Fish Tycoon - Modded")
        parents = [str(modded), str(vanilla)]
        for name, copy in (("Fish Tycoon - Modded", plain), ("Fish Tycoon - Modded Upgrades", upgrades),
                           ("Fish Tycoon", vanilla)):
            save = self.base / "LDW" / name
            self.assertEqual(bg.find_game_copy(save, bg.lookup_parents(parents)), copy, name)
            self.assertEqual(bg.art_copies("fish", save, parents)[0], copy, name)

    def test_default_installs(self) -> None:
        program_files = self.base / "Program Files (x86)"
        (program_files / "LDW").mkdir(parents=True)
        installed = fish_copy(program_files / "LDW", "Fish Tycoon")
        env = {"ProgramFiles(x86)": str(program_files)}
        self.assertIn(program_files / "LDW", bg.default_install_parents(env))
        old = bg.INSTALL_ENV
        bg.INSTALL_ENV = env
        try:
            self.assertEqual(bg.art_copies("fish", self.base / "LDW" / "Fish Tycoon - Modded", []), [installed])
        finally:
            bg.INSTALL_ENV = old

    def test_a_folder_without_the_games_exe_or_art_is_not_a_copy(self) -> None:
        empty = self.base / "Fish Tycoon - Modded"
        empty.mkdir()
        add_exe(empty, "Fish Tycoon - Modded")                    # no Images, no ft.dat
        self.assertFalse(bg.is_game_copy("fish", empty))
        art_only = make_fish_copy(self.base / "x")                  # art, no exe
        self.assertFalse(bg.is_game_copy("fish", art_only))
        self.assertFalse(bg.is_game_copy("plant", add_exe(art_only, "Fish Tycoon")))


class BuildTests(CacheTestCase):
    def test_builds_from_a_fake_copy_and_never_writes_to_it(self) -> None:
        for game, make in (("fish", make_fish_copy), ("plant", make_plant_copy)):
            copy = make(self.base / game)
            before = snapshot(copy)
            built, why = bpx.build_cache(game, copy)
            self.assertTrue(built, why)
            self.assertEqual(snapshot(copy), before)
            folder = self.cache_root / bpx.CACHE_GAME_FOLDERS[game]
            manifest = json.loads((folder / bpx.MANIFEST).read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["files"]), set(bpx.required_files(game)))
            for name, entry in manifest["files"].items():
                data = (folder / name).read_bytes()
                self.assertTrue(data.startswith(bpx.PNG_MAGIC), name)
                self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest().upper())
            cache = bpx.CacheSource(game)
            self.assertTrue(cache.ok, cache.problem)
            # the patcher's own art is the patcher's file, not the copy's
            for name, path in bpx.patcher_art(game).items():
                self.assertEqual(cache.read(name), path.read_bytes(), name)
                self.assertEqual(manifest["files"][name]["from"], "the patcher's own art")
            self.assertEqual([p.name for p in self.cache_root.iterdir() if p.name.startswith(".")], [])

    def test_a_copy_missing_a_sheet_builds_nothing_and_keeps_the_old_cache(self) -> None:
        good = make_fish_copy(self.base / "good")
        self.assertTrue(bpx.build_cache("fish", good)[0])
        manifest = (self.cache_root / "Fish" / bpx.MANIFEST).read_bytes()
        partial = make_fish_copy(self.base / "partial", skip=("ITEM_FISHEGGS_RARE.png",))
        built, why = bpx.build_cache("fish", partial)
        self.assertFalse(built)
        self.assertIn("ITEM_FISHEGGS_RARE.png", why)
        self.assertEqual((self.cache_root / "Fish" / bpx.MANIFEST).read_bytes(), manifest)
        self.assertTrue(bpx.CacheSource("fish").ok)
        fresh = self.base / "fresh"
        self.assertFalse(bpx.build_cache("fish", partial, fresh)[0])
        self.assertFalse((fresh / "Fish").exists())

    def test_leftovers_of_a_cut_short_build_are_cleared(self) -> None:
        (self.cache_root / ".Fish.building-dead").mkdir(parents=True)
        (self.cache_root / ".Fish.building-dead" / "half.png").write_bytes(b"x")
        self.assertTrue(bpx.build_cache("fish", make_fish_copy(self.base))[0])
        self.assertEqual(sorted(p.name for p in self.cache_root.iterdir()), ["Fish"])

    @unittest.skipUnless((E.VANILLA / "Fish Tycoon" / "Assets" / "ft.dat").is_file()
                         and (E.VANILLA / "Plant Tycoon" / "Images").is_dir(), "needs the read-only vanilla games")
    def test_builds_from_the_real_vanilla_copies_read_only(self) -> None:
        for game, folder in (("fish", "Fish Tycoon"), ("plant", "Plant Tycoon")):
            copy = E.VANILLA / folder
            stamps = {p: p.stat().st_mtime_ns for p in (copy / "Images", copy / "Assets") if p.exists()}
            old_fill = bpx.PLANT_FILL
            bpx.PLANT_FILL = self.base / "no fill"                  # the copy alone has every sheet
            try:
                built, why = bpx.build_cache(game, copy)
            finally:
                bpx.PLANT_FILL = old_fill
            self.assertTrue(built, why)
            self.assertTrue(bpx.CacheSource(game).ok)
            self.assertEqual({p: p.stat().st_mtime_ns for p in stamps}, stamps)


class CorruptCacheTests(CacheTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.copy = make_fish_copy(self.base / "copy")
        self.assertTrue(bpx.build_cache("fish", self.copy)[0])
        self.folder = self.cache_root / "Fish"

    def assert_rebuilt_not_used(self) -> None:
        self.assertFalse(bpx.CacheSource("fish").ok)
        alone = bpx.picture_source("fish", [])                 # no copy: the broken cache is not used
        self.assertIsNone(alone.base)
        self.assertEqual(alone.problem, bpx.no_pictures_message("fish"))
        self.assertIsNone(alone.read("FISH_00_body_Grid.png"))
        source = bpx.picture_source("fish", [self.copy])          # with a copy: made again
        self.assertIsInstance(source.base, bpx.CacheSource)
        self.assertEqual(source.problem, "")
        self.assertTrue(bpx.CacheSource("fish").ok)

    def test_changed_file(self) -> None:
        path = self.folder / "FISH_03_body_Grid.png"
        path.write_bytes(path.read_bytes()[:-1] + b"\0")
        self.assert_rebuilt_not_used()

    def test_missing_file(self) -> None:
        (self.folder / "ITEM_FISHEGGS_COMMON.png").unlink()
        self.assert_rebuilt_not_used()

    def test_partial_manifest(self) -> None:
        manifest = json.loads((self.folder / bpx.MANIFEST).read_text(encoding="utf-8"))
        del manifest["files"]["FISH_05_top_Grid.png"]
        (self.folder / bpx.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        self.assert_rebuilt_not_used()

    def test_unreadable_or_foreign_manifest(self) -> None:
        (self.folder / bpx.MANIFEST).write_text("{not json", encoding="utf-8")
        self.assert_rebuilt_not_used()
        manifest = json.loads((self.folder / bpx.MANIFEST).read_text(encoding="utf-8"))
        manifest["version"] = 0
        (self.folder / bpx.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        self.assert_rebuilt_not_used()

    def test_manifest_gone(self) -> None:
        (self.folder / bpx.MANIFEST).unlink()
        self.assert_rebuilt_not_used()


class GuideWindowTests(CacheTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = tk_root()
        if self.root is None:
            self.skipTest("no display for Tk")
        self.documents = make_documents(self.base / "docs")
        # the owner's save folder: "- Modded", whose copy is nowhere
        ldw = self.documents / "LDW"
        (ldw / "Fish Tycoon - Modded Upgrades").rename(ldw / "Fish Tycoon - Modded")
        bg._open_window = None
        self.guide = None

    def tearDown(self) -> None:
        if self.guide is not None:
            self.guide.close()
        self.root.destroy()
        super().tearDown()

    def open(self, game="fish", parents=()) -> None:
        self.guide = bg.open_window(self.root, game, settings={"show_spoilers": True}, documents=self.documents,
                                    game_parents=list(parents))
        self.root.update()

    def assert_all_pictures(self, tab_ids) -> None:
        for tab_id in tab_ids:
            built = self.guide.pictures[tab_id]
            self.assertEqual(built["message"].cget("text"), "", tab_id)
            self.assertIsNone(built["find"], tab_id)
            self.assertTrue(built["cells"], tab_id)
            self.assertTrue(all(image is not None for _i, image, _l in built["cells"]), tab_id)

    def test_pictures_show_from_the_cache_with_no_game_copy(self) -> None:
        copy = make_fish_copy(self.base / "gone")
        self.assertTrue(bpx.build_cache("fish", copy)[0])
        import shutil
        shutil.rmtree(copy)
        before = snapshot(self.documents)
        self.open()
        self.assertEqual(self.guide.folder_var.get(), "Fish Tycoon - Modded")
        self.assertEqual(self.guide.art_copies, [])
        self.assert_all_pictures(("pictures:fin", "pictures:body", "pictures:eggs"))
        for slot_index in range(len(self.guide.slots)):                  # every player
            self.guide.slot_box.current(slot_index)
            self.guide._reload()
            self.root.update()
            self.assert_all_pictures(("pictures:body",))
        self.assertEqual(snapshot(self.documents), before)

    def test_plant_pictures_from_the_cache(self) -> None:
        copy = make_plant_copy(self.base / "plant")
        self.assertTrue(bpx.build_cache("plant", copy)[0])
        import shutil
        shutil.rmtree(copy)
        self.open("plant")
        self.assert_all_pictures(("pictures:flower", "pictures:foliage", "pictures:seeds"))

    def test_first_open_builds_the_cache_from_the_upgrades_copy(self) -> None:
        modded = self.base / "Modded Games"
        modded.mkdir()
        upgrades = fish_copy(modded, "Fish Tycoon - Modded Upgrades")
        before_copy, before_docs = snapshot(upgrades), snapshot(self.documents)
        self.open(parents=[str(modded), str(modded / "Fish Tycoon - Modded")])
        self.assert_all_pictures(("pictures:fin", "pictures:body", "pictures:eggs"))
        self.assertTrue(bpx.CacheSource("fish").ok)
        self.assertEqual(json.loads((self.cache_root / "Fish" / bpx.MANIFEST).read_text(encoding="utf-8"))
                         ["built_from"], str(upgrades))
        self.assertEqual(snapshot(upgrades), before_copy)
        self.assertEqual(snapshot(self.documents), before_docs)

    def test_no_cache_no_copy_says_pick_the_game_then_find_game_fills_it(self) -> None:
        self.open()
        built = self.guide.pictures["pictures:body"]
        self.assertEqual(built["message"].cget("text"), bpx.no_pictures_message("fish"))
        self.assertIn("Game tab", bpx.no_pictures_message("fish"))
        self.assertIsNotNone(built["find"])
        self.assertTrue(all(image is None for _i, image, _l in built["cells"]))
        holder = self.base / "Games"
        holder.mkdir()
        copy = fish_copy(holder, "Fish Tycoon")
        before = snapshot(copy)
        self.assertEqual(self.guide.find_game(str(holder)), "")          # the folder the game is in
        self.root.update()
        self.assert_all_pictures(("pictures:fin", "pictures:body", "pictures:eggs"))
        self.assertEqual(snapshot(copy), before)


class ReleaseTests(unittest.TestCase):
    def test_the_cache_is_never_committed_or_shipped(self) -> None:
        self.assertIn("Breeding Guide Pictures/", (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_release
        self.assertFalse([f for f in build_release.FILES + build_release.bundled_asset_files()
                          if bpx.CACHE_FOLDER in f])
        self.assertEqual(bpx.PATCHER_ROOT, ROOT)                 # the cache's home is the patcher's folder


if __name__ == "__main__":
    unittest.main()
