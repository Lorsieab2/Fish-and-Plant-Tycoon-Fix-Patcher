"""The owner's rule for the supply slot tooltips: patch-accurate. For every Fish setting that changes how
many doses, uses or batches a supply gives, the tooltip says exactly what that patched game spends.

Each case is built on the real pinned executable of its setting combination: the manifest's patches
applied and the startup loader appended, checked against data/fish_manifest.json's pin. In it, with
DS Store Items mapped (and its use stubs written as its install writes them), every supply that can
be in a slot -- the two medicines, Fish Vitamins, Growth Hormone, the Unknown Chemical, the three
stock eggs, the starter eggs, and this store's Radioactive Growth Hormone, Revival Potion, ClonaFish
and Exotic Fish Eggs -- is put in its slot with a count of 1, 2 or 3, its tooltip read, and then it is
used on the tank by the game's own code until the slot is empty: the number of uses must be the
number the tooltip gave.

The settings, and what each changes:
* Unknown Chemical: 3 uses (unknown_chemical_remove_runtime_count_reset_chemical_only, 0x4210B7):
  the Unknown Chemical keeps its count instead of being set to 1 before each use;
* Universal supply slots: the same at 0x4210B7, the three stock eggs' stack patches (0x4213A7,
  0x421476, 0x421549: one batch a hatch), and DS Store Items' Exotic Fish Eggs stacking with it;
* both together;
* Fix vanilla bugs: the Plant of Incubation's extra egg (0x4213DB, 0x4214AA, 0x42157D) is one more
  baby in a batch, never another batch: the counts are the stock ones;
* Everything is Free and every other setting: no supply's count changes (the Enable All build, with
  all of them, is checked too).
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import test_supply_slot_tooltips as TT  # noqa: E402

T = TT.T
BASE = {"ds_fish", "ds_store"}
CASES = {
    "stock (DS Store Items only)": set(),
    "Unknown Chemical: 3 uses": {"unknown_chemical_three_uses"},
    "Universal supply slots": {"universal_supply_slots"},
    "both": {"unknown_chemical_three_uses", "universal_supply_slots"},
    "Fix vanilla bugs": {"fix_vanilla_bugs"},
    "Everything is Free": {"everything_free"},
}
ITEMS = (0, 1, 2, 3, 4, 5, 6, 7, 26, T.RGH, T.REVIVAL, T.CLONA, T.EXOTIC)
_EXES: dict[str, Path] = {}


def pinned_exe(enabled: set[str]) -> Path:
    """The executable the patcher writes for these settings, checked against its pin."""
    import ds_fish_loader
    import fish_patcher
    key = fish_patcher.settings_key(enabled)
    if key not in _EXES:
        manifest = json.loads(T.MANIFEST.read_text(encoding="utf-8"))
        data, _ = fish_patcher.apply_patch_bytes(T.EXE.read_bytes(), fish_patcher.active_patch_records(manifest, enabled))
        data, _ = ds_fish_loader.append_startup_loader(data, ds_fish_loader.fish_profile(enabled))
        pin = manifest["patched_sha256_by_settings"][key]
        if hashlib.sha256(data).hexdigest().upper() != pin:
            raise AssertionError(f"{key}: the built executable is not its pin")
        path = Path(tempfile.mkdtemp(prefix="ftfp_tips_")) / "Fish Tycoon - Modded.exe"
        path.write_bytes(data)
        _EXES[key] = path
    return _EXES[key]


def with_store_stubs(rig) -> None:
    """DS Store Items' use sites, as its install writes them (its chemical and egg switches, its trash,
    and with Universal supply slots its use gate)."""
    emu, ss = rig.emu, rig.emu.symbols
    for site, name in ((0x420E6F, "_stub_chem_use"), (0x421356, "_stub_egg_use")):
        emu.uc.mem_write(site, b"\xE9" + struct.pack("<i", ss[name] - (site + 5)))
    emu.uc.mem_write(0x421B52, b"\xE8" + struct.pack("<i", ss["_stub_supply_drop"] - (0x421B52 + 5)))
    if bytes(emu.uc.mem_read(0x420B70, 5)) == b"\xE9\xDB\xE9\x01\x00":
        emu.uc.mem_write(0x43F593, b"\xE9" + struct.pack("<i", ss["_stub_use_gate"] - (0x43F593 + 5)))
        emu.write32(ss["_exotic_any_slot"], 1)


def tooltip_count(rig, k: int) -> int:
    lines = rig.tip(*T.centre(k))
    return int(lines[1].split()[0])


def uses_until_empty(rig, k: int) -> int:
    T.UseRig.prepare(rig)
    used = 0
    while struct.unpack_from("<i", rig.stock(k), 0x0C)[0] != 0 and used < 10:
        rig.pick_stock(k)
        rig.let_go(*T.IN_TANK)
        used += 1
    return used


@unittest.skipUnless(TT.ready(), "needs Unicorn, MSVC, the vanilla Fish Tycoon.exe and both DLLs")
class PatchAccurate(unittest.TestCase):
    def check(self, enabled: set[str]) -> None:
        exe = pinned_exe(BASE | enabled)
        for item in ITEMS:
            k = T.NATIVE[item]
            for count in (1, 2, 3):
                with self.subTest(item=item, count=count):
                    rig = TT.TipRig(exe=exe)
                    with_store_stubs(rig)
                    rig.put_stock(k, T.record(item, count, k))
                    said = tooltip_count(rig, k)
                    self.assertEqual(said, uses_until_empty(rig, k), "the tooltip is what the game spends")

    def test_stock(self) -> None:
        self.check(CASES["stock (DS Store Items only)"])

    def test_unknown_chemical_three_uses(self) -> None:
        self.check(CASES["Unknown Chemical: 3 uses"])

    def test_universal_supply_slots(self) -> None:
        self.check(CASES["Universal supply slots"])

    def test_both(self) -> None:
        self.check(CASES["both"])

    def test_fix_vanilla_bugs(self) -> None:
        self.check(CASES["Fix vanilla bugs"])

    def test_everything_free(self) -> None:
        self.check(CASES["Everything is Free"])

    def test_enable_all(self) -> None:
        manifest = json.loads(T.MANIFEST.read_text(encoding="utf-8"))
        self.check({s["id"] for s in manifest["settings"]})

    def test_the_counts_the_settings_give(self) -> None:
        """Spot values, so a regression reads plainly: the Unknown Chemical bought three times as one
        stack, and Rare Fish Eggs with a count of 3."""
        expect = {"stock (DS Store Items only)": (1, 1), "Unknown Chemical: 3 uses": (3, 1),
                  "Universal supply slots": (3, 3), "both": (3, 3), "Fix vanilla bugs": (1, 1),
                  "Everything is Free": (1, 1)}
        for name, enabled in CASES.items():
            with self.subTest(setting=name):
                rig = TT.TipRig(exe=pinned_exe(BASE | enabled))
                rig.put_stock(2, T.record(4, 3, 2))
                rig.put_stock(3, T.record(7, 3, 3))
                self.assertEqual((tooltip_count(rig, 2), tooltip_count(rig, 3)), expect[name])


if __name__ == "__main__":
    unittest.main()
