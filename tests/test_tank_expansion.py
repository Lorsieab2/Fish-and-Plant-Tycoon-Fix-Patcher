"""Bigger tanks: 30 fish (Fish Tycoon) in the patcher: the setting, its byte
patches checked against the vanilla executable, all or none, and the checksum
record and pin of every byte-patch combination. The patches' effect on the
game is run in tests/test_fish_30.py."""

from __future__ import annotations

import itertools
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import fish_patcher  # noqa: E402
import tycoon_fix_patcher as combined  # noqa: E402
import pin_tank_expansion  # noqa: E402

SETTING = "bigger_tanks"
VANILLA = (Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games" / "Fish Tycoon"
           / "Fish Tycoon.exe")

# Every patched instruction, stock -> 30 fish (capstone text at the site's VA).
SITES = {
    "addfish_free_slot": ("cmp eax, 0x15", "cmp eax, 0x1e"),
    "view_build_slots": ("cmp eax, 0x15", "cmp eax, 0x1e"),
    "view_refresh_slots": ("cmp eax, 0x15", "cmp eax, 0x1e"),
    "update_loop1_slots": ("cmp ecx, 0x15", "cmp ecx, 0x1e"),
    "update_loop2_count": ("mov dword ptr [esp + 0x18], 0x15", "mov dword ptr [esp + 0x18], 0x1e"),
    "reset_remove_slots": ("cmp esi, 0x15", "cmp esi, 0x1e"),
    "reset_clear_count": ("mov esi, 0x15", "mov esi, 0x1e"),
    "magic_scan_slots": ("cmp edx, 0x15", "cmp edx, 0x1e"),
    "thoughts_random_slot": ("push 0x15", "push 0x1e"),
    "tutorial_sick_slots": ("cmp eax, 0x15", "cmp eax, 0x1e"),
    "medicine_a_end": ("cmp ebx, 0x3528", "cmp ebx, 0x4bf0"),
    "medicine_b_end": ("cmp ebx, 0x3528", "cmp ebx, 0x4bf0"),
    "medicine_c_end": ("cmp ebx, 0x3528", "cmp ebx, 0x4bf0"),
    "sparkle_entries_a": ("cmp edi, 0x15", "cmp edi, 0x1f"),
    "sparkle_entries_b": ("cmp edi, 0x15", "cmp edi, 0x1f"),
    "sparkle_entries_c": ("cmp edi, 0x15", "cmp edi, 0x1f"),
    "sparkle_entries_d": ("cmp edi, 0x15", "cmp edi, 0x1f"),
    "sick_crowd_count": ("mov ecx, 7", "mov ecx, 0xa"),
    "eggs_t0_count_code": ("mov ecx, ebp; lea ebx, [ebx]", "mov ecx, 0xa; nop; nop; nop"),
    "eggs_t1_count": ("mov ecx, 7", "mov ecx, 0xa"),
    "eggs_t2_count": ("mov ecx, 7", "mov ecx, 0xa"),
    "cheat_age_end": ("cmp eax, 0x3528", "cmp eax, 0x4bf0"),
    "sell_adults_count": ("lea edx, [edi + 7]", "lea edx, [edi + 0xa]"),
    "sellscene_adults_count": ("mov ecx, 7", "mov ecx, 0xa"),
    "sellscene_comp_count": ("mov edx, 7", "mov edx, 0xa"),
    "sellscene_comp_body22": ("lea ebx, [edx + 0xf]", "lea ebx, [edx + 0xc]"),
    "customers_end": ("cmp esi, 0x3528", "cmp esi, 0x4bf0"),
    "sale_crowd_cap": ("push 2; call 0x403240", "jmp 0x43fe00; nop; nop"),
}
CODE = ("sale_crowd_code",)


def disasm(raw: bytes, va: int) -> str:
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs
    return "; ".join(f"{i.mnemonic} {i.op_str}".strip() for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(raw, va))


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = combined.load_manifest("fish")
        self.setting = combined.patch_settings("fish")[SETTING]
        self.mine = [p for p in self.manifest["patches"] if p["id"].startswith("tank30_")]

    def test_setting_is_off_by_default_and_says_what_it_does(self) -> None:
        self.assertFalse(self.setting["default"])
        self.assertEqual(self.setting["name"], "Bigger tanks: 30 fish")
        self.assertIn("30 fish", self.setting["summary"])
        self.assertIn("selling tank too", self.setting["summary"])
        self.assertIn("down to 21", self.setting["warning"])
        self.assertIn("isolation tank still holds one fish", self.setting["description"])

    def test_every_patch_requires_the_setting_and_matches_the_list(self) -> None:
        self.assertEqual(len(self.mine), len(SITES) + len(CODE))
        self.assertEqual(len(pin_tank_expansion.TANK_PATCHES), len(SITES) + len(CODE))
        self.assertFalse([p for p in self.manifest["patches"] if p["id"].startswith("tank26_")])
        for patch in self.mine:
            self.assertEqual(patch["requires"], [SETTING])
            self.assertEqual(len(patch["expected"].split()), len(patch["replacement"].split()), patch["id"])
        vsize = next(p for p in self.manifest["patches"] if p["id"] == "extend_text_virtual_size_for_bigger_tanks")
        self.assertEqual((vsize["offset"], vsize["replacement"]), ("0x1F8", "00 F0 03 00"))

    def test_no_patch_overlaps_another_settings_patch(self) -> None:
        def span(p: dict) -> tuple[int, int]:
            start = int(p["offset"], 16)
            return start, start + len(p["replacement"].split())
        mine = [span(p) for p in self.mine]
        others = [span(p) for p in self.manifest["patches"]
                  if not p["id"].startswith("tank30_") and not p["id"].startswith("update_pe_checksum")
                  and not p["id"].startswith("extend_text_virtual_size")]
        for a, b in mine:
            for c, d in others:
                self.assertFalse(a < d and c < b, f"0x{a:X} overlaps 0x{c:X}")

    def test_exactly_one_text_size_record_for_every_combination(self) -> None:
        settings = pin_tank_expansion.byte_settings(self.manifest)
        for count in range(len(settings) + 1):
            for combo in itertools.combinations(sorted(settings), count):
                active = [p["id"] for p in fish_patcher.active_patch_records(self.manifest, set(combo))
                          if p["id"].startswith("extend_text_virtual_size")]
                needs = {"fix_vanilla_bugs", "golden_seahorse_repurchase", "universal_supply_slots", SETTING} & set(combo)
                self.assertEqual(len(active), 1 if needs else 0, combo)

    def test_every_byte_combination_has_a_checksum_record_and_a_pin(self) -> None:
        settings = pin_tank_expansion.byte_settings(self.manifest)
        self.assertIn(SETTING, settings)
        self.assertEqual(len(settings), 6)
        checksums = {tuple(p["requires"]) for p in self.manifest["patches"] if p["id"].startswith("update_pe_checksum")}
        pins = self.manifest["patched_sha256_by_settings"]
        for count in range(1, len(settings) + 1):
            for combo in itertools.combinations(sorted(settings), count):
                self.assertIn(combo, checksums)
                self.assertRegex(pins.get(fish_patcher.settings_key(set(combo)), ""), r"^[0-9A-F]{64}$", combo)
        self.assertEqual(len(checksums), 2 ** len(settings) - 1)

    def test_release_packages_the_doc(self) -> None:
        import build_release

        self.assertIn("docs/fish-tycoon-tank-expansion.md", build_release.FILES)
        self.assertTrue((ROOT / "docs" / "fish-tycoon-tank-expansion.md").is_file())


@unittest.skipUnless(VANILLA.is_file(), "needs the vanilla executable")
class VanillaBytesTests(unittest.TestCase):
    """Every site holds the stock instruction in the vanilla executable, and the setting writes all of them
    or none: off, every byte the setting could write is the stock byte in every combination."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.vanilla = VANILLA.read_bytes()
        cls.manifest = combined.load_manifest("fish")
        cls.mine = {p["id"][len("tank30_"):]: p for p in cls.manifest["patches"] if p["id"].startswith("tank30_")}

    def test_every_site_is_the_stock_instruction_and_becomes_the_30_fish_one(self) -> None:
        try:
            import capstone  # noqa: F401
        except ImportError:
            self.skipTest("needs capstone")
        self.assertEqual(set(self.mine), set(SITES) | set(CODE))
        for name, (old, new) in SITES.items():
            patch = self.mine[name]
            at = int(patch["offset"], 16)
            expected = bytes.fromhex(patch["expected"].replace(" ", ""))
            replacement = bytes.fromhex(patch["replacement"].replace(" ", ""))
            self.assertEqual(self.vanilla[at:at + len(expected)], expected, name)
            self.assertEqual(disasm(expected, at + 0x400000), old, name)
            self.assertEqual(disasm(replacement, at + 0x400000), new, name)

    def test_the_routines_sit_in_zero_slack_no_other_setting_writes(self) -> None:
        for name in CODE:
            at = int(self.mine[name]["offset"], 16)
            size = len(self.mine[name]["replacement"].split())
            self.assertTrue(0x3FE00 <= at and at + size <= 0x3FE20, name)
            self.assertEqual(self.vanilla[at:at + size], bytes(size), name)
        for patch in self.manifest["patches"]:
            if patch["id"].startswith("tank30_") or patch["id"].startswith(("update_pe_checksum", "extend_text")):
                continue
            start = int(patch["offset"], 16)
            self.assertFalse(start < 0x3FE20 and 0x3FE00 < start + len(patch["replacement"].split()), patch["id"])

    def test_off_the_stock_bytes_stay_in_every_combination(self) -> None:
        settings = [s for s in pin_tank_expansion.byte_settings(self.manifest) if s != SETTING]
        spans = [(int(p["offset"], 16), len(p["replacement"].split())) for p in self.mine.values()]
        for count in range(len(settings) + 1):
            for combo in itertools.combinations(settings, count):
                off, _ = fish_patcher.apply_patch_bytes(
                    self.vanilla, fish_patcher.active_patch_records(self.manifest, set(combo)))
                on, _ = fish_patcher.apply_patch_bytes(
                    self.vanilla, fish_patcher.active_patch_records(self.manifest, set(combo) | {SETTING}))
                for at, size in spans:
                    self.assertEqual(off[at:at + size], self.vanilla[at:at + size], (combo, hex(at)))
                for name, patch in self.mine.items():
                    at = int(patch["offset"], 16)
                    self.assertEqual(on[at:at + len(patch["replacement"].split())],
                                     bytes.fromhex(patch["replacement"].replace(" ", "")), (combo, name))
                if not combo:
                    self.assertEqual(off, self.vanilla)


if __name__ == "__main__":
    unittest.main()
