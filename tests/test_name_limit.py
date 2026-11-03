"""The one name limit is written once (docs/UNICODE_SPEC.md section 2, from VF1's test_name_limit.py).

* NAME_BOX_BYTES is spelled only in src/unicode_data.py; the DLL's copy is the header
  scripts/build_unicode18_tables.py writes from it (native/common/unicode_grapheme_table.h), and it is
  up to date.
* No other source file (the patcher, the DLLs, the scripts) spells the number, in any form (1200, 1,200,
  0x4B0), except the few that are not about names, listed here; and no NAME_LETTERS / NAME_LIMIT cap
  (the old 300-character one) is left to cut a name before the byte cap.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import unicode_data  # noqa: E402

SPELLED = re.compile(r"(?<![\w.,])(1200|1,200|0x4[bB]0|0x0*4[bB]0)(?!\w|[.,]\d)")
# Where the number means something else (a price, a coordinate, a test range): file -> a piece of the line.
NOT_NAMES = {
    "src/breeding_fish.py": ('("Rare Fish Eggs", 1200',),
    "src/game_mechanics_fish.py": ("Rare Fish Eggs ($1200)",),
    "src/game_mechanics_plant.py": ("Golden $1200",),
    "src/translation_format.py": ("_PROBE = list(range(0, 1200))",),
    "native/ftfp_ornaments/ftfp_ornaments.c": ("> 1200) return 0;",),
}
HOME = "src/unicode_data.py"
HEADER = "native/common/unicode_grapheme_table.h"


def sources() -> list[Path]:
    out = []
    for folder, patterns in (("src", ("*.py",)), ("native", ("*.c", "*.h", "*.inc", "*.def")),
                             ("scripts", ("*.py", "*.ps1"))):
        for pattern in patterns:
            out += sorted((ROOT / folder).rglob(pattern))
    return out


class NameLimitTests(unittest.TestCase):
    def test_the_limit_is_the_owners(self) -> None:
        self.assertEqual(unicode_data.NAME_BOX_BYTES, 1200)

    def test_the_dlls_copy_is_made_from_it(self) -> None:
        import build_unicode18_tables as B
        header = (ROOT / HEADER).read_bytes().decode("utf-8").replace("\r\n", "\n")
        self.assertEqual(header, B.render())
        self.assertIn(f"#define NAME_BOX_BYTES {unicode_data.NAME_BOX_BYTES}\n", header)

    def test_no_other_file_spells_it(self) -> None:
        found = []
        for path in sources():
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                if not SPELLED.search(line):
                    continue
                if rel == HOME:                     # its home: the constant and its comment
                    continue
                if rel == HEADER and line.startswith("#define NAME_BOX_BYTES "):
                    continue
                if any(piece in line for piece in NOT_NAMES.get(rel, ())):
                    continue
                found.append(f"{rel}:{number}: {line.strip()}")
        self.assertEqual(found, [], "spell NAME_BOX_BYTES (src/unicode_data.py, or the DLL's generated header)")

    def test_no_character_cap_is_left(self) -> None:
        found = []
        for path in sources():
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                if re.search(r"\bNAME_(LETTERS|LIMIT)\b", line):
                    found.append(f"{rel}:{number}: {line.strip()}")
        self.assertEqual(found, [])

    def test_a_check_spelling_would_be_caught(self) -> None:
        for line in ("#define NAME_BOX_BYTES 1200", "limit = 1200", "up to 1,200 bytes", "cmp eax, 0x4B0",
                     "up to 1,200."):
            self.assertTrue(SPELLED.search(line), line)
        for line in ("12000", "x1200", "1200.5", "$12,000", "11,200"):
            self.assertFalse(SPELLED.search(line), line)


if __name__ == "__main__":
    unittest.main()
