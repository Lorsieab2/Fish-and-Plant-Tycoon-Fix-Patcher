"""The release ZIP carries every file the patcher needs to start."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContentsTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_release

        self.release = build_release

    def test_every_imported_module_is_packaged(self) -> None:
        # v1.0.18 shipped without src/cheat.py and the patcher would not start.
        self.assertEqual(self.release.missing_modules(self.release.FILES), [])

    def test_the_import_walk_reaches_the_whole_patcher(self) -> None:
        reached = self.release.imported_modules()
        for name in ("tycoon_fix_patcher_gui", "tycoon_fix_patcher", "cheat", "experimental",
                     "tools_tab", "picture_studio", "breeding_collectopedia", "game_mechanics_window"):
            self.assertIn(name, reached)

    def test_a_dropped_module_is_reported(self) -> None:
        files = [name for name in self.release.FILES if name != "src/cheat.py"]
        self.assertEqual(self.release.missing_modules(files), ["src/cheat.py"])

    def test_every_listed_file_exists(self) -> None:
        missing = [name for name in self.release.FILES if not (ROOT / name).is_file()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
