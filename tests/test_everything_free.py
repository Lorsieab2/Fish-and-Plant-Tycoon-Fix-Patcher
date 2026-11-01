"""Everything is Free (both games): every price the player pays is $0.

Layers:
  * the manifests: the setting (a cheat, off by default, the owner's sentence, only an .ini beside the
    DLLs), its in-place patches, a checksum record and a pin for every combination;
  * the GUI: "Select All Patches", "Owner's Defaults" and "Default Patches" leave it off, ticking it by hand turns it on, CHEAT is shown
    beside its name;
  * the executables: every patched site is the stock instruction, overlaps no other setting's patch or
    companion DLL site, and every companion's hooks still find their stock bytes with all settings on;
  * Unicorn: the game's own store code, run patched and unpatched -- with the setting each kind of stock
    purchase takes $0 and still delivers, shows $0 and is never refused for money; without it every price
    is the stock one; the limits stay;
  * the companion DLLs (rebuilt from source): each reads "Everything Free.ini" at start-up and is then free.
"""

from __future__ import annotations

import itertools
import json
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import cheat  # noqa: E402
import ds_fish_loader  # noqa: E402
import experimental  # noqa: E402
import fish_patcher  # noqa: E402
import pin_everything_free as P  # noqa: E402
import plant_patcher  # noqa: E402

try:
    import store_emulator as E
except ImportError:                     # Unicorn is not installed
    E = None

SETTING = "everything_free"
TEXT = "Every store item and upgrade is free. Obviously a cheat mod, have fun!"
VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
EXES = {"fish": VANILLA / "Fish Tycoon" / "Fish Tycoon.exe", "plant": VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"}
PATCHERS = {"fish": fish_patcher, "plant": plant_patcher}


def manifest(game: str) -> dict:
    return json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))


def key(game: str, enabled: set[str], m: dict) -> str:
    return fish_patcher.settings_key(enabled) if game == "fish" else plant_patcher.settings_key(enabled, m)


def build(game: str, enabled: set[str], m: dict) -> bytes:
    patcher = PATCHERS[game]
    data, _ = patcher.apply_patch_bytes(EXES[game].read_bytes(), patcher.active_patch_records(m, enabled))
    if fish_patcher.needs_startup_loader(m, enabled):
        profile = (ds_fish_loader.fish_profile if game == "fish" else ds_fish_loader.plant_profile)(enabled)
        data, _ = ds_fish_loader.append_startup_loader(data, profile)
    return data


def everything_but_cheats(m: dict) -> set[str]:
    """Every setting but the cheats, and but the loader tails (Unicode Text), which have no pins of their own."""
    return fish_patcher.pin_settings(m, {s["id"] for s in m["settings"] if not cheat.is_cheat(s)})


# ------------------------------------------------------------------ manifests


class ManifestTests(unittest.TestCase):
    def test_the_setting_in_both_games(self) -> None:
        for game in ("fish", "plant"):
            m = manifest(game)
            s = next(x for x in m["settings"] if x["id"] == SETTING)
            self.assertEqual(s["name"], "Everything is Free")
            self.assertEqual(s["description"], TEXT)
            self.assertEqual(s["summary"], TEXT)
            self.assertIs(s["default"], False)
            self.assertTrue(cheat.is_cheat(s))
            self.assertFalse(experimental.is_experimental(s))
            self.assertNotIn("requires_settings", s)
            ids = [x["id"] for x in m["settings"]]
            self.assertEqual(ids.index(SETTING), ids.index("add_money") + 1, "listed after Add Money")
            folder = "Fish Tycoon Fix Patcher DLLs" if game == "fish" else "Plant Tycoon Fix Patcher DLLs"
            self.assertEqual([f["destination"] for f in s["companion"]["files"]], [f"{folder}/Everything Free.ini"])
            self.assertFalse(s["companion"].get("startup_loader", False), "no DLL of its own, no loader change")

    def test_only_this_setting_is_a_cheat(self) -> None:
        for game in ("fish", "plant"):
            self.assertEqual({s["id"] for s in manifest(game)["settings"] if cheat.is_cheat(s)}, {SETTING})

    def test_every_patch_is_this_settings_and_in_place(self) -> None:
        for game, count in (("fish", 20), ("plant", 28)):
            mine = [p for p in manifest(game)["patches"] if p["id"].startswith("everything_free_")]
            self.assertEqual(len(mine), count, game)
            for p in mine:
                self.assertEqual(p["requires"], [SETTING])
                self.assertEqual(len(p["expected"].split()), len(p["replacement"].split()))

    def test_off_no_patch_is_active(self) -> None:
        for game in ("fish", "plant"):
            m = manifest(game)
            active = PATCHERS[game].active_patch_records(m, everything_but_cheats(m))
            self.assertFalse([p["id"] for p in active if SETTING in p.get("requires", [])], game)

    def test_a_checksum_record_and_a_pin_for_every_combination(self) -> None:
        for game in ("fish", "plant"):
            m = manifest(game)
            settings = P.byte_settings(m)
            self.assertIn(SETTING, settings)
            records = {tuple(p["requires"]) for p in m["patches"] if p["id"].startswith("update_pe_checksum")}
            self.assertEqual(len(records), 2 ** len(settings) - 1)
            pins = m["patched_sha256_by_settings"]
            self.assertIn(SETTING, pins)
            without = [k for k in pins if SETTING not in k.split(",")]
            for k in without:
                self.assertIn(",".join(sorted(set(k.split(",")) | {SETTING})), pins, (game, k))
            self.assertEqual(len(pins), 2 * len(without) + 1, game)


# ------------------------------------------------------------------ the GUI


class GuiTests(unittest.TestCase):
    def test_enable_all_and_defaults_leave_it_off_ticking_turns_it_on(self) -> None:
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as error:      # no display (CI)
            self.skipTest(f"no Tk: {error}")
        root.withdraw()
        try:
            import tycoon_fix_patcher_gui as gui
            from tkinter import ttk
            app = gui.App.__new__(gui.App)
            app.root = root
            games = ("fish", "plant")
            app.patch_vars = {g: {sid: tk.BooleanVar(master=root, value=bool(s.get("default")))
                                  for sid, s in gui.patch_settings(g).items()} for g in games}
            app.busy_controls = []
            app.path_vars = {g: {k: tk.StringVar(master=root) for k in ("vanilla", "output", "backup")} for g in games}
            app.status_var = tk.StringVar(master=root)
            app._save_settings = lambda: None
            app._technical_details = lambda *a, **k: None
            for game in games:
                frame = ttk.Frame(root)
                app._build_game_panel(frame, game, compact=False)
                rows: dict[str, list[str]] = {}

                def walk(widget) -> None:
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Frame):
                            labels = [str(c.cget("text")) for c in child.winfo_children()
                                      if isinstance(c, (ttk.Checkbutton, ttk.Label))]
                            if labels:
                                rows[labels[0]] = labels
                        walk(child)
                walk(frame)
                for sid, s in gui.patch_settings(game).items():
                    self.assertEqual(cheat.LABEL in rows[str(s.get("name", sid))], sid == SETTING, (game, sid))
                var = app.patch_vars[game][SETTING]
                self.assertFalse(var.get())
                for preset in ("select_all", "owners_defaults"):
                    app._set_selection(game, gui.preset_selection(preset, game))
                    self.assertFalse(var.get(), f"{preset} leaves the cheat off")
                    # (Owner's Defaults leaves Render Unicode with In-Game Fonts off by the owner's choice;
                    # Select All keeps it and so leaves Use Unicode Font, which excludes it, off)
                    left_off = {SETTING} | (gui.OWNERS_DEFAULTS_OFF if preset == "owners_defaults"
                                            else {"unicode_system_font"})
                    others = [v.get() for sid, v in app.patch_vars[game].items() if sid not in left_off]
                    self.assertTrue(all(others), f"{preset} still turns every other setting on")
                app._set_selection(game, gui.preset_selection("default_patches", game))
                self.assertFalse(var.get(), "Default Patches leave it off")
                var.set(True)                                   # ticked by hand
                self.assertTrue(var.get())
                app._set_selection(game, gui.preset_selection("deselect_all", game))
                self.assertFalse(var.get(), "Deselect All Patches turns it off")
        finally:
            root.destroy()

    def test_cheat_helpers(self) -> None:
        s = cheat.mark({"id": "x", "name": "X", "default": True, "category": "main"})
        self.assertEqual(list(s), ["id", "name", "default", "cheat", "category"])
        self.assertIs(s["default"], False)
        self.assertFalse(cheat.in_enable_all(s))
        self.assertTrue(cheat.in_enable_all({"id": "y"}))
        self.assertEqual(cheat.mark(s), s)


# ------------------------------------------------------------------ the executables


def _have(game: str):
    return unittest.skipUnless(EXES[game].is_file(), f"the vanilla {game} executable is needed")


def _site_expectations(game: str) -> list[tuple[int, bytes, str]]:
    """Every companion DLL's code site and the stock bytes it checks before it installs."""
    projects = P.GAMES[game]["dlls"] + (["ftfp_supply_slots"] if game == "fish" else [])
    out = []
    for project in sorted(set(projects)):
        for header in (ROOT / "native" / project).glob("*sites.h"):
            text = header.read_text(encoding="utf-8")
            vas = dict(re.findall(r"#define SITE_(\w+)_VA (0x[0-9A-Fa-f]+)u", text))
            for name, raw in re.findall(r"static const unsigned char SITE_(\w+)_EXPECT\[\] = \{([^}]*)\}", text):
                if name in vas:
                    out.append((int(vas[name], 16), bytes(int(b, 16) for b in raw.split(",")), f"{project} {name}"))
    return out


class ExecutableTests(unittest.TestCase):
    @_have("fish")
    @_have("plant")
    def test_sites_are_stock_and_overlap_nothing(self) -> None:
        import importlib.util
        if importlib.util.find_spec("capstone") is None:
            self.skipTest("needs capstone")
        for game, g in P.GAMES.items():
            m = manifest(game)
            records = P.check_sites(EXES[game].read_bytes(), g, m)
            on_file = {p["id"]: p for p in m["patches"] if p["id"].startswith("everything_free_")}
            self.assertEqual({r["id"]: r for r in records}, on_file, game)

    @_have("fish")
    @_have("plant")
    def test_all_settings_and_this_one_alone_build_to_their_pins_and_every_hook_still_installs(self) -> None:
        for game in ("fish", "plant"):
            m = manifest(game)
            everything = everything_but_cheats(m) | {SETTING}
            for enabled in (everything, {SETTING}, everything - {SETTING}):
                fish_patcher.check_setting_requirements(m, enabled)
                data = build(game, enabled, m)
                import hashlib
                self.assertEqual(hashlib.sha256(data).hexdigest().upper(),
                                 m["patched_sha256_by_settings"][key(game, enabled, m)], (game, sorted(enabled)))
                for va, stock, name in _site_expectations(game):
                    off = va - 0x400000
                    self.assertEqual(data[off:off + len(stock)], stock, f"{game}: {name} would not install")

    @_have("fish")
    @_have("plant")
    def test_without_the_setting_every_site_is_stock(self) -> None:
        for game in ("fish", "plant"):
            m = manifest(game)
            data = build(game, everything_but_cheats(m), m)
            for p in m["patches"]:
                if p["id"].startswith("everything_free_"):
                    off = int(p["offset"], 16)
                    self.assertEqual(data[off:off + len(p["expected"].split())], bytes.fromhex(p["expected"].replace(" ", "")))


# ------------------------------------------------------------------ Unicorn: the game's own code


def _exe_file(game: str, free: bool, folder: Path) -> Path:
    if not free:
        return EXES[game]
    m = manifest(game)
    data, _ = PATCHERS[game].apply_patch_bytes(EXES[game].read_bytes(), PATCHERS[game].active_patch_records(m, {SETTING}))
    path = folder / f"{game}_free.exe"
    path.write_bytes(data)
    return path


def _needs_unicorn(game: str):
    return unittest.skipUnless(E is not None and EXES[game].is_file(), "Unicorn and the vanilla executable are needed")


S_MONEY, S_SPENT = 0x38C, 0x24


@_needs_unicorn("fish")
class FishStoreTests(unittest.TestCase):
    """Fish Tycoon's Supplies store: prices live in the state's item table (+0x74 + item x 20)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.free_exe = _exe_file("fish", True, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def world(self, free: bool, money: int = 0):
        emu = E.Emulator(self.free_exe if free else EXES["fish"], None, {})
        for address, pop in ((0x00425120, 0), (0x004251A0, 4), (0x0040AE20, 4), (0x00419E40, 4)):
            emu.hook(address, emu.record(hex(address), args=1), pop)
        emu.hook(0x004032C0, lambda e: 1000, 0)                              # the game clock
        state, store = emu.alloc(0x40000), emu.alloc(0x100)
        emu.write32(store + 0x10, state)
        emu.write32(state + S_MONEY, money)
        emu.state, emu.store = state, store
        return emu

    def price(self, emu, item: int, value: int) -> None:
        emu.write32(emu.state + 0x74 + item * 20, value)

    def money(self, emu) -> int:
        return emu.read32(emu.state + S_MONEY, signed=True)

    def test_supplies_cost_nothing_and_still_fill_the_slot(self) -> None:
        """The slot purchase 0x427540(slot, item, icon, cursor): food, medicine, chemicals, eggs."""
        for item, slot in ((0, 1), (1, 1), (4, 2), (6, 3)):
            for free, money, spent in ((True, 500, 0), (False, 500 - 40, 40)):
                emu = self.world(free, 500)
                self.price(emu, item, 40)
                emu.call(0x00427540, slot, item, 0xA7, 0xAD, ecx=emu.store)
                self.assertEqual(self.money(emu), money, (item, free))
                self.assertEqual(emu.read32(emu.state + S_SPENT), spent, (item, free))
                self.assertEqual(emu.read32(emu.state + slot * 28 + 0x2B8), item, "the slot holds it")
                self.assertEqual(emu.read32(emu.state + slot * 28 + 0x2C0), 3)

    def test_research_costs_nothing_and_still_starts(self) -> None:
        """The research purchase 0x427600(item): each line at levels 1 and 2."""
        for item, field in ((23, 0x240), (24, 0x254), (25, 0x268)):
            for level in (1, 2):
                for free in (True, False):
                    emu = self.world(free, 300)
                    emu.write32(emu.state + field, 250)
                    emu.write32(emu.state + field + 4, level)
                    emu.call(0x00427600, item, ecx=emu.store)
                    self.assertEqual(self.money(emu), 300 if free else 50, (item, level, free))
                    self.assertEqual(emu.read32(emu.state + S_SPENT), 0 if free else 250)
                    self.assertNotEqual(emu.read32(emu.state + field), 250, "the next level's price is set")

    def test_research_limit_stays(self) -> None:
        emu = self.world(True, 300)
        emu.write32(emu.state + 0x240 + 4, 3)              # level 3: done
        emu.write32(emu.state + 0x240, 650)
        emu.call(0x00427600, 23, ecx=emu.store)
        self.assertEqual(emu.read32(emu.state + 0x240), 650)
        self.assertFalse(emu.calls, "refused before anything happens")

    def test_permanent_items_cost_nothing_and_are_owned(self) -> None:
        """The purchase 0x427B30(item), Tank Two (item 9)."""
        for free, money in ((True, 900), (False, 0)):
            emu = self.world(free, 900)
            self.price(emu, 9, 900)
            emu.call(0x00427B30, 9, ecx=emu.store)
            self.assertEqual(self.money(emu), money)
            self.assertEqual(emu.read32(emu.state + 0x78 + 9 * 20), 1, "owned")

    def test_an_owned_permanent_item_is_still_refused(self) -> None:
        emu = self.world(True, 900)
        self.price(emu, 9, 900)
        emu.write32(emu.state + 0x78 + 9 * 20, 1)
        self.assertEqual(emu.call(0x00427B30, 9, ecx=emu.store) & 0xFF, 1)
        self.assertEqual(self.money(emu), 900)
        self.assertFalse(emu.calls)

    def test_the_seahorse_refund_is_zero_too(self) -> None:
        """No tank has room (0x427E9F): the stock refunds the price it took; free, it took $0 and gives $0."""
        from unicorn import x86_const as X
        for free, money in ((True, 0), (False, 1300)):
            emu = self.world(free, 0)
            self.price(emu, 11, 1300)
            emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
            emu.uc.reg_write(X.UC_X86_REG_ESI, emu.store)
            emu.uc.reg_write(X.UC_X86_REG_EDI, 11 * 20)
            emu.uc.reg_write(X.UC_X86_REG_EBP, (11 * 5 + 0x1E) * 4)
            emu.uc.emu_start(0x00427E9F, 0x00427EC0, count=50)
            self.assertEqual(self.money(emu), money)

    def run_to(self, emu, start: int, stops: tuple[int, ...], **regs) -> int:
        from unicorn import UC_HOOK_CODE
        from unicorn import x86_const as X
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        for name, value in regs.items():
            emu.uc.reg_write(getattr(X, f"UC_X86_REG_{name.upper()}"), value)
        hit = []

        def stop(uc, address, _size, _data) -> None:
            if address in stops:
                hit.append(address)
                uc.emu_stop()
        handle = emu.uc.hook_add(UC_HOOK_CODE, stop)
        emu.uc.emu_start(start, 0, count=60)
        emu.uc.hook_del(handle)
        return hit[0]

    def test_never_too_little_money(self) -> None:
        """The Buy click's test (0x42810F): price > money goes to the "can't afford" hint (0x428124)."""
        for free, expected in ((True, 0x00428133), (False, 0x00428124)):
            emu = self.world(free, 0)
            self.price(emu, 12, 200)
            self.assertEqual(self.run_to(emu, 0x0042810F, (0x00428124, 0x00428133),
                                         ecx=emu.state, edi=12, esi=emu.store), expected)

    def test_the_price_line_says_zero(self) -> None:
        """The store panel's price line (0x4274A4): '%s  $%d'."""
        for free, expected in ((True, 0), (False, 350)):
            emu = self.world(free, 0)
            self.price(emu, 14, 350)
            item = emu.alloc(0x20)
            emu.write32(item + 0x10, 14)
            shown = []
            emu.hook(0x00427050, lambda e: e.text("Price:"), 4)
            emu.hook(0x0042B20B, lambda e: (shown.append(e.arg(3)), 0)[1], 0)
            emu.hook(0x00408B80, lambda e: 0, 20)
            emu.write32(emu.store + 0x18, emu.alloc(0x10))
            from unicorn import x86_const as X
            emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
            emu.uc.reg_write(X.UC_X86_REG_EDI, item)
            emu.uc.reg_write(X.UC_X86_REG_ESI, emu.store)
            emu.uc.reg_write(X.UC_X86_REG_EBP, emu.alloc(0x10))
            emu.uc.emu_start(0x004274A4, 0x004274EE, count=40)
            self.assertEqual(shown, [expected])


@_needs_unicorn("plant")
class PlantStoreTests(unittest.TestCase):
    """Plant Tycoon's purchase dialog: the price at dialog + 0x84, the cash at state + 0x217C."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.free_exe = _exe_file("plant", True, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def world(self, free: bool, cash: int = 0, price: int = 200):
        emu = E.Emulator(self.free_exe if free else EXES["plant"], None, {})
        state, dialog = emu.alloc(0x60000), emu.alloc(0x200)
        emu.write32(state + 0x217C, cash)
        emu.write32(dialog + 0x74, state)
        emu.write32(dialog + 0x84, price)
        emu.state, emu.dialog = state, dialog
        return emu

    def run_to(self, emu, start: int, stops: tuple[int, ...], count: int = 30, **regs) -> int:
        from unicorn import UC_HOOK_CODE
        from unicorn import x86_const as X
        emu.uc.reg_write(X.UC_X86_REG_ESP, E.STACK + E.STACK_SIZE - 0x1000)
        for name, value in regs.items():
            emu.uc.reg_write(getattr(X, f"UC_X86_REG_{name.upper()}"), value)
        hit = []

        def stop(uc, address, _size, _data) -> None:
            if address in stops:
                hit.append(address)
                uc.emu_stop()
        handle = emu.uc.hook_add(UC_HOOK_CODE, stop)
        emu.uc.emu_start(start, 0, count=count)
        emu.uc.hook_del(handle)
        return hit[0] if hit else -1

    def test_never_too_poor(self) -> None:
        """Each of the dialog's cash tests, with $0 cash and a $200 price: stock goes to the
        "not enough cash" branch, free never does."""
        cases = [   # (start, poor branch, affordable fall-through, registers)
            (0x00430A96, 0x00430DF0, 0x00430AB0, {}),
            (0x00430BF1, 0x00430DF0, 0x00430C0B, {}),
            (0x00430D0A, 0x00430DF0, 0x00430D23, {}),
            (0x00430DF3, 0x00430E7E, 0x00430E03, {}),
        ]
        for start, poor, ok, _ in cases:
            for free in (True, False):
                emu = self.world(free)
                got = self.run_to(emu, start, (poor, ok), ecx=emu.state, esi=emu.dialog)
                self.assertEqual(got, ok if free else poor, (hex(start), free))
        # price and cash in registers: the tools (0x431570), nursery items (0x432170), chemicals (0x43273F)
        for free in (True, False):
            emu = self.world(free)
            self.assertEqual(self.run_to(emu, 0x00431570, (0x00431750, 0x00431578), edx=200, edi=0),
                             0x00431578 if free else 0x00431750)
            emu = self.world(free)
            self.assertEqual(self.run_to(emu, 0x00432170, (0x004322F2, 0x0043217C), edx=200, ecx=emu.state),
                             0x0043217C if free else 0x004322F2)
            emu = self.world(free)
            self.assertEqual(self.run_to(emu, 0x00432736, (0x004328C1, 0x0043274B), esi=emu.dialog),
                             0x0043274B if free else 0x004328C1)

    def test_every_price_line_says_zero(self) -> None:
        from unicorn import x86_const as X
        sites = [p for p in P.PLANT_SITES if "Price: $%d" in p[3]]
        self.assertEqual(len(sites), 17)
        for va, _expect, how, _why in sites:
            for free in (True, False):
                emu = self.world(free)
                self.run_to(emu, va, (va + 6,), esi=emu.dialog, eax=7, ecx=7, edx=7)
                reg = {"eax": X.UC_X86_REG_EAX, "ecx": X.UC_X86_REG_ECX, "edx": X.UC_X86_REG_EDX}[how.split()[1]]
                self.assertEqual(emu.uc.reg_read(reg), 0 if free else 200, (hex(va), free))

    def test_buy_charges_nothing_and_still_delivers(self) -> None:
        """The four Buy charges (AddCash 0x41ED70 with -price): a seed, a nursery item, a tool, a chemical.
        The tool is still marked owned after its charge (state + 0x9EC)."""
        for va, back in ((0x00432D96, 0x00432DA7), (0x00432DB3, 0x00432DC4),
                         (0x00432DE8, 0x00432DF9), (0x00432E1D, 0x00432E2E)):
            for free in (True, False):
                emu = self.world(free, 1000)
                charged = []
                emu.hook(0x0041ED70, lambda e: (charged.append(e.read32(
                    e.uc.reg_read(__import__("unicorn").x86_const.UC_X86_REG_ESP) + 4, signed=True)), 0)[1], 4)
                self.run_to(emu, va, (back,), count=10, ebp=emu.dialog)
                self.assertEqual(charged, [0 if free else -200], (hex(va), free))
        emu = self.world(True, 0)
        emu.hook(0x0041ED70, lambda e: 0, 4)
        emu.write32(emu.dialog + 0x94, 1)
        self.run_to(emu, 0x00432DE8, (0x00432E16,), count=20, ebp=emu.dialog)
        self.assertEqual(emu.uc.mem_read(emu.state + 1 * 0xA0 + 0x9EC, 1)[0], 1, "the tool is owned")

    def test_an_owned_tool_is_still_refused(self) -> None:
        """0x43155D: an owned tool (record + 0x6EC) goes to "already own" before any cash test."""
        emu = self.world(True)
        record = emu.alloc(0x800)
        emu.write8(record + 0x6EC, 1)
        self.assertEqual(self.run_to(emu, 0x0043155D, (0x00431F1D, 0x0043156A), ecx=record), 0x00431F1D)


# ------------------------------------------------------------------ the companion DLLs


def _dll_ready() -> bool:
    return E is not None and E.toolchain_ready() and EXES["fish"].is_file() and EXES["plant"].is_file()


@unittest.skipUnless(_dll_ready(), "Unicorn, the pinned MSVC toolset and the vanilla executables are needed")
class CompanionTests(unittest.TestCase):
    """Each store DLL, rebuilt from source (byte-identical to the shipped one), reads the setting's file at
    start-up (the function its start-up stores in its free flag: DS Store Items' free_on, Store Upgrades
    and Items' free_upgrades, Multiple Ornaments' everything_free) and is then free, as with Free upgrades."""

    DLLS = {
        "ftfp_ds_store": ("fish", "assets/fish_tycoon_ds_store/DS Store Items.dll", "_free_setting", "free_on"),
        "ftfp_ornaments": ("fish", "assets/fish_tycoon_ornaments/Multiple Ornaments.dll",
                           "_everything_free_setting", "everything_free"),
        "ftfp_plant_upgrades": ("plant", "assets/plant_tycoon_upgrades/Store Upgrades and Items.dll",
                                "_free_setting", "free_upgrades"),
    }

    def test_each_start_up_stores_the_setting_in_its_flag(self) -> None:
        for project, (_game, _path, function, flag) in self.DLLS.items():
            source = (ROOT / "native" / project / f"{project}.c").read_text(encoding="utf-8")
            self.assertRegex(source, rf"{flag} = (\(unsigned char\))?{function[1:]}\(\);", project)

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.built = {}
        for project, (_game, path, _start, _flag) in cls.DLLS.items():
            out = Path(cls.tmp.name) / project
            out.mkdir()
            cls.built[project] = E.build_with_map(project, ROOT / path, out)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def start(self, project: str, files: set[str]) -> tuple[int, list[str]]:
        game, _path, startup, flag = self.DLLS[project]
        dll, symbols = self.built[project]
        emu = E.Emulator(EXES[game], dll, symbols)
        asked: list[str] = []
        folder = "C:\\Game\\Patcher DLLs\\"

        def module_file(e) -> int:
            module, buffer = e.arg(0), e.arg(1)
            if module == 0:
                return 0                                   # the executable's path: no log is written
            text = folder + "x.dll"
            e.uc.mem_write(buffer, text.encode("utf-16-le") + b"\0\0")
            return len(text)

        def attributes(e) -> int:
            name = e.wstring(e.arg(0))
            asked.append(name)
            return 0x20 if name.rsplit("\\", 1)[-1] in files else 0xFFFFFFFF

        emu.hook_import("GetModuleFileNameW", module_file, 12)
        emu.hook_import("GetFileAttributesW", attributes, 4)
        for name, pop, result in (("GetModuleHandleW", 4, 0), ("GetModuleHandleExW", 12, 0), ("LoadLibraryW", 4, 0),
                                  ("GetProcAddress", 8, 0), ("VirtualProtect", 16, 0), ("CreateFileW", 28, 0xFFFFFFFF),
                                  ("GetPrivateProfileIntW", 16, 0), ("GetPrivateProfileStringW", 24, 0),
                                  ("FlushInstructionCache", 12, 1), ("GetCurrentProcess", 0, 0xFFFFFFFF),
                                  ("CloseHandle", 4, 1), ("WriteFile", 20, 1), ("GetLastError", 0, 0),
                                  ("SetLastError", 4, 0), ("GetTickCount", 0, 0)):
            emu.hook_import(name, lambda e, r=result: r, pop)
        return emu.call(symbols[startup]) & 0xFF, asked

    def test_each_store_dll_reads_the_file(self) -> None:
        for project in self.DLLS:
            on, asked = self.start(project, {"Everything Free.ini"})
            self.assertEqual(on, 1, project)
            self.assertIn("C:\\Game\\Patcher DLLs\\Everything Free.ini", asked, project)
            off, _ = self.start(project, set())
            self.assertEqual(off, 0, project)

    def test_free_upgrades_alone_still_works(self) -> None:
        for project in ("ftfp_ds_store", "ftfp_plant_upgrades"):
            on, _ = self.start(project, {"Free Upgrades.ini"})
            self.assertEqual(on, 1, project)

    def test_an_ornament_copy_is_free(self) -> None:
        """Multiple Ornaments' Buy on an owned ornament: $0 taken, the copy still made, the money test passed."""
        import test_multiple_ornaments as T
        case = T.EmulatedTests("test_buying_through_the_store_click")
        case.dll, case.symbols = self.built["ftfp_ornaments"]
        for free, money in ((1, 0), (0, 0)):
            emu = case.world()
            emu.write32(emu.state + S_MONEY, 0)
            emu.write32(emu.sym("_everything_free"), free)
            emu.write32(emu.state + 17 * 20 + 0x78, 1)
            emu.call(emu.sym("_store_click"), emu.store, 17)
            self.assertEqual(emu.read32(emu.sym("_copy_count")), 1 if free else 0, free)
            self.assertEqual(emu.read32(emu.state + S_MONEY), money)
            self.assertEqual(emu.read32(emu.state + S_SPENT), 0)


if __name__ == "__main__":
    unittest.main()
