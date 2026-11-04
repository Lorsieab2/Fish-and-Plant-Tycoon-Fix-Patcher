"""Long names (Unicode Text.dll, both games; docs/UNICODE_SPEC.md section 2): one name limit for every
name box, the short form in the save's fixed fields, the whole name in "Names <slot>.dat", and long
names fitted on screen. The DLL's own code and the game's run in Unicorn against the vanilla
executables (tests/test_unicode_text.py builds the DLL from its committed source).

* The name boxes' setLimit(1, 0x20) (the five player rows and the new player's box) gives the
  shared limit, NAME_BOX_BYTES bytes as stored with no character cap; every other box keeps the game's.
* getText into a player's name writes the name as it is when it fits the 31-byte field (the write
  rule: a Windows-1252 letter one byte, any other UTF-8), else its short form (whole characters and
  "...", "2..." when taken), exactly as src/save_tools.py makes it (the Python tools are the oracle
  here), and its record goes into "Names <slot>.dat" (the shared format: header, then
  short<TAB>room<TAB>whole<TAB>CRC-32) at once, through "Names <slot>.dat.tmp"; a failed write stays
  pending and is written at a later draw or the exit.
* setText of that row gives the box the whole name again, also after a restart; records are never
  removed, the first of a short form wins, invalid ones are skipped, v1.0.25's files are read.
* Guard bytes: no fixed buffer is written past at NAME_BOX_BYTES.
* The text draw and measure show a player's short form as the whole name, fitted to the width the
  game left for a name; the boxes fit their own text and no longer cut it.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

import test_unicode_text as T
from test_unicode_text import E, needs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import save_tools  # noqa: E402
import unicode_data  # noqa: E402

SLOTS_PATH = "{docs}\\LDW\\{title} - Modded Upgrades\\{title} Fix Patcher Data\\Names {slot}.dat"
NAME_BOX_BYTES = unicode_data.NAME_BOX_BYTES
SHORT_BYTES = 32
HEADER = b"FTFP Names 1\n"
GUARD = b"\xA5" * 16

GAMES = {
    "fish": dict(new_call=0x417D72, new_dst=0x1E3A5, limit_call=0x417124, other_limit_call=0x4290E7, other_limit=8, text_call=0x417833,
                 state_global=0x45ABDC, rows=0x1E3D8, stride=0x2A, set_text=0x40B970, new=0x42A793,
                 free=0x42A6B1, draw=0x4087E0, width=0x4023D0, box_cut=0x40B7ED,
                 sites=((0x40B970, 6), (0x40BC90, 6), (0x40BC30, 8), (0x40B7A3, 5), (0x40B7ED, 2),
                        (0x40B829, 5), (0x4087E0, 7), (0x4023D0, 7), (0x41916A, 5)), save=0x41916A, save_end=0x403520),
    "plant": dict(new_call=0x41B018, new_dst=8, limit_call=0x415B6C, other_limit_call=0x4304C9, other_limit=6, text_call=0x416198,
                  state_global=0x49333C, rows=0x53FC2, stride=0x21, set_text=0x40C380, new=0x44E894,
                  free=0x44E7B3, draw=0x408E20, width=0x402380, box_cut=0x40C1FD,
                  sites=((0x40C380, 6), (0x40C740, 6), (0x40C6E0, 8), (0x40C1B3, 5), (0x40C1FD, 2),
                         (0x40C239, 5), (0x408E20, 7), (0x402380, 7), (0x41D160, 5)), save=0x41D160, save_end=0x403690),
}
TITLE_OF = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}
# The text the games make their name rows with (Fish 0x442220, Plant 0x467790), and their box makers:
# the constructor (thiscall wrapper, 9 arguments), setLimit and setText of the wrapper, and the rows'
# x and text as the player list passes them.
PLACEHOLDER = {"fish": b"_" * 26, "plant": b" " * 26}
BOX_MAKER = {
    "fish": dict(make=0x40C1E0, limit=0x40BC30, set_text=0x40BC40, row_x=0xE3, row_text=0x442220),
    "plant": dict(make=0x40CCB0, limit=0x40C6E0, set_text=0x40C6F0, row_x=200, row_text=0x467790),
}


def names_path(game: str, slot: int) -> str:
    return SLOTS_PATH.format(docs=T.DOCUMENTS, title=T.tm.GAME_TITLES[game], slot=slot)


def record(short: bytes, whole: str) -> bytes:
    return save_tools.record_line(save_tools.NameRecord(unicode_data.decode_game_text(short), 31, whole))


def f32(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


class Game:
    """The game with the DLL installed, its state and a box at hand."""

    def __init__(self, game: str, existing: dict | None = None, emu=None) -> None:
        self.game, self.a = game, GAMES[game]
        dll, symbols = T.built(game)
        self.symbols = symbols
        if emu is None:
            emu = E.Emulator(T.EXES[game], dll, symbols)
            emu.uc.mem_map(0, 0x1000)
        self.emu = emu
        self.files = T.hook_windows(emu, game, existing=existing)
        emu.hook(self.a["new"], lambda e: e.alloc(max(1, e.arg(0)) + 16), 0)
        emu.hook(self.a["free"], lambda e: 0, 0)
        self.state = emu.alloc(self.a["rows"] + 5 * self.a["stride"] + 0x100)
        emu.uc.mem_write(self.state, bytes(self.a["rows"] + 5 * self.a["stride"] + 0x100))
        emu.write32(self.a["state_global"], self.state)
        assert T.startup(emu, symbols) == 1

    def row(self, slot: int) -> int:
        return self.state + self.a["rows"] + (slot - 1) * self.a["stride"]

    def row_bytes(self, slot: int) -> bytes:
        return bytes(self.emu.uc.mem_read(self.row(slot), 32)).split(b"\0", 1)[0]

    def set_row(self, slot: int, raw: bytes) -> None:
        self.emu.uc.mem_write(self.row(slot), raw.ljust(32, b"\0"))

    def box(self, text: bytes = b"", limit: int = 0x20) -> tuple[int, int]:
        """(wrapper, box): a box (vtable aside) holding `text`, its buffer limit + 1 bytes and guard bytes."""
        emu = self.emu
        box = emu.alloc(0x60)
        emu.uc.mem_write(box, bytes(0x60))
        size = max(limit, len(text)) + 1
        buffer = emu.alloc(size + len(GUARD))
        emu.uc.mem_write(buffer, text + b"\0")
        emu.uc.mem_write(buffer + size, GUARD)
        emu.write32(box + 0x30, buffer)
        emu.write32(box + 0x28, limit)
        wrapper = emu.alloc(0x20)
        emu.write32(wrapper + 0x10, box)
        self.guards = getattr(self, "guards", []) + [(buffer + size, GUARD)]
        return wrapper, box

    def guards_intact(self) -> bool:
        return all(bytes(self.emu.uc.mem_read(at, len(g))) == g for at, g in self.guards)

    def text(self, box: int) -> bytes:
        return self.emu.cstring(self.emu.read32(box + 0x30))

    def run_call(self, at: int, ecx: int, *stack: int) -> None:
        """The game's own `call` at `at`, its arguments on the stack, to the next instruction."""
        emu = self.emu
        esp = E.STACK + E.STACK_SIZE - 0x2000
        for i, value in enumerate(stack):
            emu.write32(esp + 4 * i, value)
        emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(E.X.UC_X86_REG_ECX, ecx)
        emu.uc.emu_start(at, at + 5, count=2_000_000)
        assert emu.uc.reg_read(E.X.UC_X86_REG_ESP) == esp + 4 * len(stack), "stack unbalanced"

    def type_name(self, name: str, slot: int = 1) -> bytes:
        """The name in a name box (as the box keeps it: the write rule), its getText into player row
        `slot` (the game's own call): the row's 32 bytes."""
        wrapper, _box = self.box(unicode_data.encode_game_text(name), limit=NAME_BOX_BYTES)
        dst = self.row(slot)
        self.run_call(self.a["text_call"], wrapper, dst, 0x20)
        return bytes(self.emu.uc.mem_read(dst, 0x20))

    def set_text(self, box: int, text_at: int) -> None:
        self.emu.call(self.a["set_text"], text_at, ecx=box)

    def names_file(self, slot: int) -> bytes | None:
        return self.files["raw"].get(names_path(self.game, slot))

    def python_field(self, name: str, slot: int) -> bytes:
        """What src/save_tools.py stores for `name` in `slot`, given the DLL's Names files and rows
        as they are now (the oracle the DLL must agree with)."""
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            data = folder / f"{TITLE_OF[self.game]} Fix Patcher Data"
            data.mkdir()
            for n in range(1, 6):
                body = self.names_file(n)
                if body is None:
                    body = self.files["existing"].get(names_path(self.game, n))
                if body is not None:
                    (data / f"Names {n}.dat").write_bytes(body)
            book = save_tools.NameBook(self.game, folder)
            fields = {n: self.row_bytes(n) for n in range(1, 6)}
            field, _record = book.store(slot, name, fields, exclude=slot)
            return field


class NamesCase:
    game = "fish"

    def test_installs_with_every_name_site(self) -> None:
        g = Game(self.game)
        for va, n in GAMES[self.game]["sites"]:
            site = bytes(g.emu.uc.mem_read(va, n))
            if va == GAMES[self.game]["box_cut"]:
                self.assertEqual(site, b"\xEB\x18")                    # the cut is skipped
            else:
                self.assertIn(site[0], (0xE8, 0xE9))
                target = va + 5 + struct.unpack_from("<i", site, 1)[0]
                self.assertTrue(T.DLL_BASE <= target < T.DLL_BASE + 0x100000, hex(va))
        # a changed byte at any of them: nothing is written at all
        stock = E.Emulator(T.EXES[self.game], None, {})
        for va, n in GAMES[self.game]["sites"]:
            with self.subTest(changed=hex(va)):
                emu = E.Emulator(T.EXES[self.game], T.built(self.game)[0], T.built(self.game)[1])
                emu.uc.mem_map(0, 0x1000)
                files = T.hook_windows(emu, self.game)
                emu.write8(va + n - 1, emu.uc.mem_read(va + n - 1, 1)[0] ^ 0x5A)
                before = T.code_bytes(emu, GAMES[self.game]["sites"])
                self.assertEqual(T.startup(emu, T.built(self.game)[1]), 0)
                self.assertEqual(T.code_bytes(emu, GAMES[self.game]["sites"]), before)
                self.assertIn("not the stock code", files["text"])
                self.assertEqual(T.code_bytes(emu, T.site_ranges(self.game)),
                                 T.code_bytes(stock, T.site_ranges(self.game)))

    def test_name_boxes_get_the_shared_limit(self) -> None:
        """NAME_BOX_BYTES (the generated header's, from src/unicode_data.py), no character cap."""
        g = Game(self.game)
        wrapper, box = g.box(b"Ann")
        g.run_call(GAMES[self.game]["limit_call"], wrapper, 1, 0x20)
        self.assertEqual(g.emu.read32(box + 0x28), NAME_BOX_BYTES)
        self.assertEqual(g.text(box), b"Ann")
        wrapper, box = g.box(b"")
        a = GAMES[self.game]
        g.run_call(a["other_limit_call"], wrapper, 1, a["other_limit"])
        self.assertEqual(g.emu.read32(box + 0x28), a["other_limit"])

    def test_the_row_and_the_names_file_agree_with_the_tools(self) -> None:
        """Each name's field is what src/save_tools.py stores (the same rule, run in Python), and a
        name that does not fit has its record in the shared format beside the save."""
        g = Game(self.game)
        cases = [("Renée", 1), ("A" * 31, 2), ("Bartholomew Montgomery Fitzgerald the Third of Ørsted", 3),
                 ("é" * NAME_BOX_BYTES, 4), ("山田 🐟 Ölçer", 5), ("山田 太郎 山田 太郎 🐟 Ölçer", 5),
                 ("x" * NAME_BOX_BYTES, 1), ("Abcdefghijklmnopqrstuvwxyz1 3456789", 2),
                 ("é" * 20 + " \U0001F468‍\U0001F469‍\U0001F467", 3), ("Ã©" * 20, 4),
                 ("€uro — „Grüße“ " * 3, 1)]
        for name, slot in cases:
            with self.subTest(name=name[:30]):
                want = g.python_field(name, slot)
                before = g.names_file(slot)
                row = g.type_name(name, slot=slot)
                self.assertEqual(row, want.ljust(32, b"\0"))
                self.assertLessEqual(len(want), 31)
                if want == unicode_data.encode_game_text(name):
                    self.assertEqual(g.names_file(slot), before, "a name that fits needs no record")
                else:
                    self.assertTrue(unicode_data.decode_game_text(want).endswith("..."))
                    self.assertEqual(g.names_file(slot), (before or HEADER) + record(want, name))
                    self.assertIn(save_tools.NameRecord(unicode_data.decode_game_text(want), 31, name),
                                  save_tools.parse_names(g.names_file(slot)))
        self.assertTrue(g.guards_intact())

    def test_short_forms_are_unique_across_the_slots(self) -> None:
        """Names starting alike: "...", "2...", "3..." (the tools' rule); typing a name again gives its own
        short form again, and no second record."""
        g = Game(self.game)
        a = "Wilhelmina Charlotte Augusta of Anhalt"
        b = "Wilhelmina Charlotte Augusta of Brandenburg"
        c = "Wilhelmina Charlotte Augusta of Coburg"
        for name, slot, short in ((a, 1, b"Wilhelmina Charlotte Augusta..."), (b, 2, b"Wilhelmina Charlotte August2..."),
                                  (c, 3, b"Wilhelmina Charlotte August3...")):
            self.assertEqual(g.python_field(name, slot), short)
            self.assertEqual(g.type_name(name, slot), short.ljust(32, b"\0"))
        file1 = g.names_file(1)
        self.assertEqual(g.type_name(a, 1), b"Wilhelmina Charlotte Augusta...".ljust(32, b"\0"))
        self.assertEqual(g.names_file(1), file1)
        # a plain name equal to a taken short form becomes a short form itself
        name = "Wilhelmina Charlotte Augusta..."
        self.assertEqual(g.python_field(name, 4), b"Wilhelmina Charlotte August4...")
        self.assertEqual(g.type_name(name, 4), b"Wilhelmina Charlotte August4...".ljust(32, b"\0"))

    def test_records_are_never_removed_and_the_first_wins(self) -> None:
        g = Game(self.game)
        a, b = "Bartholomew Montgomery Fitzgerald Alpha", "Bartholomew Montgomery Fitzgerald Beta"
        g.type_name(a, 1)
        self.assertEqual(g.type_name(b, 1), b"Bartholomew Montgomery Fitz2...".ljust(32, b"\0"))
        path = names_path(self.game, 1)
        self.assertEqual(g.files["raw"][path], HEADER + record(b"Bartholomew Montgomery Fitzg...", a)
                         + record(b"Bartholomew Montgomery Fitz2...", b))
        # a restart: the file is read; each short form shows its own whole name
        g2 = Game(self.game, existing={path: g.files["raw"][path]})
        for short, whole in ((b"Bartholomew Montgomery Fitz2...", b), (b"Bartholomew Montgomery Fitzg...", a)):
            g2.set_row(1, short)
            _wrapper, box = g2.box()
            g2.set_text(box, g2.row(1))
            self.assertEqual(g2.text(box), unicode_data.encode_game_text(whole))
        # the same short form twice in a file: the first record wins
        doubled = HEADER + record(b"Same...", "Same first whole name") + record(b"Same...", "Same second whole name")
        g3 = Game(self.game, existing={names_path(self.game, 2): doubled})
        g3.set_row(2, b"Same...")
        _wrapper, box = g3.box()
        g3.set_text(box, g3.row(2))
        self.assertEqual(g3.text(box), b"Same first whole name")

    def test_invalid_records_are_skipped(self) -> None:
        """Cut short, merged, a wrong CRC, no mark, too long for its room, a control character, more
        than NAME_BOX_BYTES bytes: skipped, as src/save_tools.py parse_names skips them."""
        good = record(b"Good...", "Good whole name here")
        bad_crc = good[:-3] + (b"0\n" if not good.endswith(b"0\n") else b"1\n")
        nomark = save_tools.record_line(save_tools.NameRecord("Nomark", 31, "Nomark and more"))
        control = save_tools.record_line(save_tools.NameRecord("Ctl...", 31, "Ctl\x07name"))
        huge = save_tools.record_line(save_tools.NameRecord("Big...", 31, "x" * (NAME_BOX_BYTES + 1)))
        toolong = save_tools.record_line(save_tools.NameRecord("L" * 40 + "...", 31, "L" * 60))
        cut = record(b"Cut...", "Cut whole name")[:-12] + b"\n"
        merged = record(b"Mer...", "Merged whole name")[:15] + record(b"Ged...", "Second merged")
        body = HEADER + bad_crc + nomark + control + huge + toolong + cut + merged + good
        self.assertEqual(save_tools.parse_names(body), [save_tools.NameRecord("Good...", 31, "Good whole name here")])
        g = Game(self.game, existing={names_path(self.game, 1): body})
        for short, expect in ((b"Good...", b"Good whole name here"), (b"Abc...", b"Abc..."), (b"Nomark", b"Nomark"),
                              (b"Ctl...", b"Ctl..."), (b"Big...", b"Big..."), (b"Cut...", b"Cut..."),
                              (b"Ged...", b"Ged...")):
            g.set_row(1, short)
            _wrapper, box = g.box()
            g.set_text(box, g.row(1))
            self.assertEqual(g.text(box), expect, short)

    def test_a_v1025_names_file_is_read_and_kept(self) -> None:
        """"short NUL full NUL" with v1.0.25's short form ("?" for letters Latin-1 has not): used while the
        row holds it; a new record turns the file into the shared format with the old record first."""
        legacy = "Maximilian Alexander 山田 von Hohenstein-Waldburg"
        old = save_tools.old_short_form(legacy).encode("latin-1")
        path = names_path(self.game, 3)
        raw = old + b"\0" + legacy.encode("utf-8") + b"\0"
        g = Game(self.game, existing={path: raw})
        g.set_row(3, old)
        _wrapper, box = g.box()
        g.set_text(box, g.row(3))
        self.assertEqual(g.text(box), unicode_data.encode_game_text(legacy))
        # the stock game renamed the player: the old record is not used
        g.set_row(3, b"Someone Else")
        _wrapper, box = g.box()
        g.set_text(box, g.row(3))
        self.assertEqual(g.text(box), b"Someone Else")
        copy = g.emu.text(old.decode("latin-1"))
        _wrapper, box = g.box()
        g.set_text(box, copy)
        self.assertEqual(g.text(box), old, "a v1.0.25 short form is no short form once its row is renamed")
        # a new name for slot 3
        name = "Konstantin Friedrich Wilhelm von Preussen"
        g.type_name(name, 3)
        want = save_tools.render_names(raw, [save_tools.NameRecord("Konstantin Friedrich Wilhelm...", 31, name)])
        self.assertEqual(g.files["raw"][path], want)

    def test_the_new_players_name_is_written_at_once(self) -> None:
        """The new player's box accepted: Names 1.dat is written before the game copies the name
        into row 1 (no draw, no exit needed), even while row 1 still holds an older typed name."""
        g = Game(self.game)
        g.type_name("Older Name ✓ one and some more letters", slot=1)
        path = names_path(self.game, 1)
        before = g.files["raw"][path]
        name = "Новый \U0001F41F Yeni oyuncu \U0001202D"
        want = g.python_field(name, 1)
        wrapper, _box = g.box(unicode_data.encode_game_text(name), limit=NAME_BOX_BYTES)
        dst = g.state + GAMES[self.game]["new_dst"]
        g.files["moves"].clear()
        g.run_call(GAMES[self.game]["new_call"], wrapper, dst, 0x20)
        self.assertEqual(bytes(g.emu.uc.mem_read(dst, 0x20)), want.ljust(32, b"\0"))
        self.assertEqual(g.files["raw"][path], before + record(want, name))
        # REPLACE_EXISTING | WRITE_THROUGH, from the temporary file
        self.assertEqual(g.files["moves"], [(path + ".tmp", path, 0x1 | 0x8)])
        self.assertNotIn(path + ".tmp", g.files["raw"])
        # the game copies it into row 1: the row shows the whole name
        g.set_row(1, want)
        _wrapper, box = g.box()
        g.set_text(box, g.row(1))
        self.assertEqual(g.text(box), unicode_data.encode_game_text(name))

    def test_a_rename_is_written_at_once_through_a_temporary_file(self) -> None:
        g = Game(self.game)
        name = "Çağrı Yılmaz 山田 \U0001F600 rename"
        path = names_path(self.game, 3)
        short = g.type_name(name, slot=3).rstrip(b"\0")
        self.assertEqual(g.files["raw"][path], HEADER + record(short, name))
        self.assertIn((path + ".tmp", path, 0x9), g.files["moves"])
        # a move Windows refuses: the file is written in place, as before, the temporary removed
        g.emu.hook_import("MoveFileExW", lambda e: 0, 12)
        other = "Second name, ünïcödé ✨ and more"
        short2 = g.type_name(other, slot=3).rstrip(b"\0")
        self.assertEqual(g.files["raw"][path], HEADER + record(short, name) + record(short2, other))
        self.assertNotIn(path + ".tmp", g.files["raw"])

    def test_a_record_whose_write_failed_is_pending_and_written_later(self) -> None:
        """No file can be made: the row still gets the short form, the record waits; at a draw two
        seconds later (names_sync) it is written; the exit writes what is still pending."""
        g = Game(self.game)
        path = names_path(self.game, 2)
        real_create = g.emu.hooks[g.emu.imports["CreateFileW"]][0]
        blocked = {"on": True}

        def create(e) -> int:
            if blocked["on"] and not e.arg(1) & 0x80000000 and "Names" in e.wstring(e.arg(0)):
                return 0xFFFFFFFF
            return real_create(e)

        g.emu.hook_import("CreateFileW", create, 28)
        name = "Pending Name That Is Longer Than Its Field"
        short = g.type_name(name, 2).rstrip(b"\0")
        self.assertEqual(short, b"Pending Name That Is Longer...")
        self.assertNotIn(path, g.files["raw"])
        # the whole name is still shown while it waits
        _wrapper, box = g.box()
        g.set_text(box, g.row(2))
        self.assertEqual(g.text(box), name.encode())
        blocked["on"] = False
        g.files["tick"] += 500
        g.emu.call(g.symbols["_names_sync"])
        self.assertNotIn(path, g.files["raw"], "retried at most every 2 s")
        g.files["tick"] += 2000
        g.emu.call(g.symbols["_names_sync"])
        self.assertEqual(g.files["raw"][path], HEADER + record(short, name))
        # the exit: what is pending is written at once
        blocked["on"] = True
        other = "Another Pending Name, Longer Than Its Field"
        short2 = g.type_name(other, 2).rstrip(b"\0")
        blocked["on"] = False
        g.emu.call(g.symbols["_names_sync_now"], 1)
        self.assertEqual(g.files["raw"][path], HEADER + record(short, name) + record(short2, other))

    def test_a_record_made_while_no_slot_is_known_waits_for_its_row(self) -> None:
        """getText of a name into no player row: its record stays pending; once a row holds that short
        form, the next sync records it for that row's slot."""
        g = Game(self.game)
        name = "Nobody's Row Yet, A Name Too Long For Its Field"
        dst = g.emu.alloc(0x20)
        wrapper, _box = g.box(unicode_data.encode_game_text(name), limit=NAME_BOX_BYTES)
        g.run_call(GAMES[self.game]["text_call"], wrapper, dst, 0x20)
        short = bytes(g.emu.uc.mem_read(dst, 0x20)).split(b"\0", 1)[0]
        self.assertTrue(short.endswith(b"..."))
        self.assertFalse(any(names_path(self.game, n) in g.files["raw"] for n in range(1, 6)))
        g.set_row(4, short)
        g.files["tick"] += 5000
        g.emu.call(g.symbols["_names_sync"])
        self.assertEqual(g.names_file(4), HEADER + record(short, name))

    def run_save(self, g: Game) -> None:
        """The game's own save path, from its patched site to the game's writer it calls (no draw)."""
        emu = g.emu
        esp = E.STACK + E.STACK_SIZE - 0x2000
        emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(E.X.UC_X86_REG_ECX, g.state)
        emu.uc.reg_write(E.X.UC_X86_REG_EAX, g.state + 8)
        emu.uc.emu_start(GAMES[self.game]["save"], GAMES[self.game]["save_end"], count=2_000_000)
        self.assertEqual(emu.uc.reg_read(E.X.UC_X86_REG_ECX), g.state)       # ecx survived the sync

    def test_pending_records_are_written_by_the_games_save_path(self) -> None:
        """A name whose slot is unknown, and one whose first write failed, are pending; the game's
        save writes both at once (no draw, no exit); a normal name was already written."""
        g = Game(self.game)
        normal = "Normal Committed Name With Extra Letters"
        short1 = g.type_name(normal, slot=3).rstrip(b"\0")
        self.assertEqual(g.names_file(3), HEADER + record(short1, normal))   # at once
        # unknown slot
        name = "Nobody's Row Yet, A Name Too Long For Its Field"
        dst = g.emu.alloc(0x20)
        wrapper, _box = g.box(unicode_data.encode_game_text(name), limit=NAME_BOX_BYTES)
        g.run_call(GAMES[self.game]["text_call"], wrapper, dst, 0x20)
        short = bytes(g.emu.uc.mem_read(dst, 0x20)).split(b"\0", 1)[0]
        g.set_row(4, short)
        # a failed first write
        real_create = g.emu.hooks[g.emu.imports["CreateFileW"]][0]
        blocked = {"on": True}

        def create(e) -> int:
            if blocked["on"] and not e.arg(1) & 0x80000000 and "Names" in e.wstring(e.arg(0)):
                return 0xFFFFFFFF
            return real_create(e)

        g.emu.hook_import("CreateFileW", create, 28)
        other = "Pending Name That Is Longer Than Its Field"
        short2 = g.type_name(other, 2).rstrip(b"\0")
        self.assertIsNone(g.names_file(2))
        self.assertIsNone(g.names_file(4))
        blocked["on"] = False
        self.run_save(g)
        self.assertEqual(g.names_file(2), HEADER + record(short2, other))
        self.assertEqual(g.names_file(4), HEADER + record(short, name))
        self.assertEqual(g.names_file(3), HEADER + record(short1, normal))

    def test_viewing_a_long_name_never_shortens_it(self) -> None:
        """A box set up with the game's 32-byte limit (no name site's setLimit) shown a name of
        NAME_BOX_BYTES bytes: setText keeps it whole (the game's setText grows the limit to the
        text), and the getText that follows writes the same short form back and no new record."""
        name = "Å山\U0001F41F" * (NAME_BOX_BYTES // 8)
        self.assertEqual(save_tools.name_bytes(name), NAME_BOX_BYTES)
        g = Game(self.game)
        g.type_name(name, slot=4)
        path = names_path(self.game, 4)
        before = g.files["raw"][path]
        short = g.row_bytes(4)
        wrapper, box = g.box(b"", limit=0x20)
        g.set_text(box, g.row(4))
        self.assertEqual(g.text(box), unicode_data.encode_game_text(name))
        dst = g.row(4)
        g.run_call(GAMES[self.game]["text_call"], wrapper, dst, 0x20)
        self.assertEqual(g.row_bytes(4), short)
        self.assertEqual(g.files["raw"][path], before)
        self.assertEqual(before, HEADER + record(short, name))

    def test_no_fixed_buffer_is_overrun_at_the_limit(self) -> None:
        """Guard bytes after the game's 32-byte field, the box's buffer and the getText destination: a
        name of NAME_BOX_BYTES bytes (and a box the game grew past them) writes none of them."""
        g = Game(self.game)
        for name in ("山" * (NAME_BOX_BYTES // 3), "x" * NAME_BOX_BYTES, "\U0001F41F" * (NAME_BOX_BYTES // 4),
                     "é" * (NAME_BOX_BYTES // 3)):
            with self.subTest(name=name[:4]):
                dst = g.emu.alloc(0x20 + len(GUARD))
                g.emu.uc.mem_write(dst, bytes(0x20) + GUARD)
                wrapper, _box = g.box(unicode_data.encode_game_text(name), limit=NAME_BOX_BYTES)
                g.run_call(GAMES[self.game]["text_call"], wrapper, dst, 0x20)
                self.assertEqual(bytes(g.emu.uc.mem_read(dst + 0x20, len(GUARD))), GUARD)
                self.assertEqual(bytes(g.emu.uc.mem_read(dst + 0x1F, 1)), b"\0")
                self.assertTrue(g.guards_intact())
        # a box the game's setText grew past the limit: the whole name is cut at whole characters
        long_text = ("é" * (NAME_BOX_BYTES + 40)).encode("cp1252")
        wrapper, _box = g.box(long_text, limit=NAME_BOX_BYTES)
        g.run_call(GAMES[self.game]["text_call"], wrapper, g.row(5), 0x20)
        records = save_tools.parse_names(g.names_file(5))
        self.assertEqual(records[-1].whole, "é" * NAME_BOX_BYTES)
        self.assertTrue(g.guards_intact())

    def test_set_text_of_a_row_gives_the_whole_name(self) -> None:
        g = Game(self.game)
        long_name = "Wilhelmina Charlotte Ångström-Lindqvist of Malmö"
        short = g.type_name(long_name, slot=1).rstrip(b"\0")
        _wrapper, box = g.box()
        g.set_text(box, g.row(1))
        self.assertEqual(g.text(box), long_name.encode("cp1252"))
        # the short form as text (not the row itself) too
        copy = g.emu.text(short.decode("cp1252"))
        _wrapper, box = g.box()
        g.set_text(box, copy)
        self.assertEqual(g.text(box), long_name.encode("cp1252"))
        # a short name is its own whole name: nothing changes
        g.set_row(2, b"Bob")
        _wrapper, box = g.box()
        g.set_text(box, g.row(2))
        self.assertEqual(g.text(box), b"Bob")

    def test_other_boxes_get_their_text_as_the_game_copies_it(self) -> None:
        g = Game(self.game)
        wrapper, _box = g.box(b"Registration Name 12345678901234567890")
        dst = g.emu.alloc(0x40)
        g.emu.uc.mem_write(dst, b"\xAA" * 0x40)
        getter = 0x40BC90 if self.game == "fish" else 0x40C740
        g.emu.call(getter, dst, 0x21, ecx=wrapper)
        self.assertEqual(bytes(g.emu.uc.mem_read(dst, 0x22)), b"Registration Name 12345678901234567890"[:0x20]
                         + b"\0" + b"\xAA")


class DrawNamesCase:
    game = "fish"

    def setUp(self) -> None:
        dll, symbols = T.built(self.game)
        self.fde = T.fde.FontDrawEmulator(self.game, screen_w=1600, dll=dll, symbols=symbols)
        self.g = Game(self.game, emu=self.fde.emu)
        self.symbols = symbols
        font = next(iter(T.FONT_SITES[self.game]))
        va = font[0]
        push = bytes(self.fde.emu.uc.mem_read(va, 10))
        table, name_at = struct.unpack_from("<I", push, 1)[0], struct.unpack_from("<I", push, 6)[0]
        name = self.fde.emu.cstring(name_at).decode("ascii")
        self.font = self.fde.load_font_at(name_at, table, (T.ASSETS[self.game] / "Images" / f"{name}.png").read_bytes())

    def game_width(self, raw: bytes) -> int:
        emu = self.fde.emu
        at = emu.alloc(len(raw) + 1)
        emu.uc.mem_write(at, raw + b"\0")
        return emu.call(self.symbols["_orig_width"], at, f32(1.0), ecx=self.font)

    def hooked_width(self, raw: bytes) -> int:
        emu = self.fde.emu
        at = emu.alloc(len(raw) + 1)
        emu.uc.mem_write(at, raw + b"\0")
        return emu.call(GAMES[self.game]["width"], at, f32(1.0), ecx=self.font)

    def screen(self, raw: bytes, own: bool) -> bytes:
        """The screen after drawing `raw`: through the game's hooked draw, or (own) the game's own
        draw as it was."""
        self.fde.fill((10, 20, 30))
        emu = self.fde.emu
        at = emu.alloc(len(raw) + 1)
        emu.uc.mem_write(at, raw + b"\0")
        target = self.symbols["_orig_draw"] if own else GAMES[self.game]["draw"]
        emu.call(target, at, 4, 6, 0xFFFFFFFF, self.font, ecx=self.fde.impl)
        return bytes(self.fde.screen_image.data)

    def expected_fit(self, full: bytes, budget: int, tail: bool) -> bytes:
        """The most whole letters that fit `budget` with the ellipsis (one byte a letter here)."""
        if self.game_width(full) <= budget:
            return full

        def piece(k: int) -> bytes:
            return b"\x85" + full[len(full) - k:] if tail else full[:k] + b"\x85"
        lo, hi = 0, len(full)
        while lo < hi:
            k = (lo + hi + 1) // 2
            if self.game_width(piece(k)) <= budget:
                lo = k
            else:
                hi = k - 1
        # the most: one letter more does not fit
        self.assertTrue(lo == len(full) or self.game_width(piece(lo + 1)) > budget)
        return piece(lo)

    def test_a_short_form_is_drawn_as_the_full_name_fitted(self) -> None:
        placeholder = self.game_width(PLACEHOLDER[self.game])
        for name in ("Wilhelmina Charlotte Ångström-Lindqvist", "Bartholomew Montgomery Fitzgerald the Third "
                     "of the Northern Reaches of Ørsted"):
            with self.subTest(name=name):
                short = self.g.type_name(name, slot=2).rstrip(b"\0")
                self.g.emu.uc.mem_write(self.g.row(1), short.ljust(32, b"\0"))
                budget = max(self.game_width(short), placeholder)
                shown = self.expected_fit(name.encode("cp1252"), budget, tail=False)
                self.assertEqual(self.screen(short, own=False), self.screen(shown, own=True))
                self.assertEqual(self.hooked_width(short), self.game_width(shown))
        # any other text is the game's own, pixel for pixel
        for text in (b"Hello, world", b"Renee", b"__________________________", b"x" * 31):
            self.assertEqual(self.screen(text, own=False), self.screen(text, own=True))
            self.assertEqual(self.hooked_width(text), self.game_width(text))

    def test_a_name_within_the_games_text_is_the_full_name(self) -> None:
        """Text drawn outside a box: the short form in it is the full name, the whole text fitted to
        the wider of itself and itself with the game's name placeholder for the name."""
        name = "Bartholomew Montgomery Fitzgerald the Third of the Northern Reaches"
        short = self.g.type_name(name, slot=1).rstrip(b"\0")
        text = b"Player: " + short
        budget = max(self.game_width(text), self.game_width(b"Player: " + PLACEHOLDER[self.game]))
        shown = self.expected_fit(b"Player: " + name.encode("cp1252"), budget, tail=False)
        self.assertEqual(self.screen(text, own=False), self.screen(shown, own=True))
        self.assertEqual(self.hooked_width(text), self.game_width(shown))

    def game_box(self, x: int, y: int, text_va: int, align: int) -> tuple[int, int]:
        """(wrapper, box): a box made by the game's own constructor, with the arguments its screens
        pass (Fish 0x40C1E0, Plant 0x40CCB0: parent, id, x, y, text, font, alignment, 0, scale)."""
        emu = self.fde.emu
        parent = emu.alloc(0x400)
        emu.uc.mem_write(parent, bytes(0x400))
        wrapper = emu.alloc(0x40)
        emu.uc.mem_write(wrapper, bytes(0x40))
        emu.call(BOX_MAKER[self.game]["make"], parent, 0x64, x, y, text_va, self.font, align, 0, f32(1.0), ecx=wrapper)
        return wrapper, emu.read32(wrapper + 0x10)

    def box_shows(self, wrapper: int, box: int) -> tuple[int, bytes]:
        """The box's measure and draw of its own text (the DLL's box_width and box_draw, where the
        game's box draw calls them)."""
        emu = self.fde.emu
        text_at = emu.read32(box + 0x30)
        width = emu.call(self.symbols["_box_width"], self.font, box, 0, text_at, f32(1.0))
        self.fde.fill((10, 20, 30))
        graphics = emu.alloc(4)
        emu.write32(graphics, self.fde.impl)
        emu.call(self.symbols["_box_draw"], graphics, box, 0, text_at, 4, 6, 0xFFFFFFFF, self.font)
        return width, bytes(self.fde.screen_image.data)

    def test_a_player_row_fits_the_name_to_its_real_room(self) -> None:
        """The player list's rows, made by the game's own code as its screen makes them (Fish
        0x4170E2: centred on x 0xE3 with 26 underscores; Plant 0x415B04: 26 spaces), then made
        fixed by the game's setLimit(1, 0x20): a long name is fitted to the row's own room."""
        emu = self.fde.emu
        maker = BOX_MAKER[self.game]
        wrapper, box = self.game_box(maker["row_x"], 0x42, maker["row_text"], 1)
        left, right, margin = emu.read32(box + 8), emu.read32(box + 0x10), emu.read32(box + 0x44)
        room = right - left - margin
        # the game made the row as wide as its own text: the placeholder, by the game's own measure
        self.assertEqual(room, self.game_width(PLACEHOLDER[self.game]))
        emu.call(maker["limit"], 1, 0x20, ecx=wrapper)
        self.assertEqual(emu.uc.mem_read(box + 0x24, 1), b"\x01")
        for name in ("Wilhelmina Charlotte Ångström-Lindqvist of Malmö and Stockholm", "Ann Lee"):
            with self.subTest(name=name):
                short = self.g.type_name(name, slot=2).rstrip(b"\0")
                at = emu.alloc(len(short) + 1)
                emu.uc.mem_write(at, short + b"\0")
                emu.call(maker["set_text"], at, ecx=wrapper)
                width, drawn = self.box_shows(wrapper, box)
                shown = self.expected_fit(name.encode("cp1252"), room, tail=False)
                self.assertEqual(width, self.game_width(shown))
                self.assertLessEqual(width, room)
                self.assertEqual(drawn, self.screen(shown, own=True))
                if len(name) > 10:
                    self.assertTrue(shown.endswith(b"\x85"))
                    # the old estimate (Plant: underscores, wider than its 26 spaces) would not fit
                    if self.game == "plant":
                        self.assertGreater(self.game_width(b"_" * 26), room)

    def test_the_main_menu_player_label_fits_to_its_side_of_the_screen(self) -> None:
        """Fish Tycoon's main menu label (0x41C6DC: x 0x280, y 0x23C, "xxxxxx", aligned right; the game
        sets "<Player:> <name>" in it at 0x41C9C2): a long name is fitted to the room from the screen's
        left edge to the label's right edge."""
        if self.game != "fish":
            self.skipTest("Plant Tycoon shows names only in its player rows")
        emu = self.fde.emu
        wrapper, box = self.game_box(0x280, 0x23C, 0x4438CC, 2)
        self.assertEqual(emu.read32(box + 0x40), 2)                 # right-aligned
        emu.write32(self.symbols["_screen_right"], 800)
        right, margin = emu.read32(box + 0x10), emu.read32(box + 0x44)
        room = right - margin
        name = ("Bartholomew Montgomery Fitzgerald the Third of the Northern Reaches of Ørsted and the "
                "Southern Isles, Keeper of the Great Aquarium")
        short = self.g.type_name(name, slot=1).rstrip(b"\0")
        at = emu.alloc(len(short) + 16)
        emu.uc.mem_write(at, b"Player: " + short + b"\0")
        emu.call(BOX_MAKER["fish"]["set_text"], at, ecx=wrapper)
        width, drawn = self.box_shows(wrapper, box)
        shown = self.expected_fit(b"Player: " + name.encode("cp1252"), room, tail=False)
        self.assertEqual(width, self.game_width(shown))
        self.assertLessEqual(width, room)
        self.assertEqual(drawn, self.screen(shown, own=True))
        # wider than the old estimate allowed
        self.assertGreater(width, self.game_width(b"Player: " + b"_" * 26))

    def test_boxes_fit_their_text(self) -> None:
        emu = self.fde.emu
        long_name = "Wilhelmina Charlotte Ångström-Lindqvist of Malmö and Stockholm".encode("cp1252")
        for focused in (0, 1):
            for name in (b"Ann", long_name):
                with self.subTest(focused=focused, name=name[:10]):
                    _wrapper, box = self.g.box(name, limit=NAME_BOX_BYTES)
                    for off, value in ((8, 100), (0xC, 50), (0x10, 340), (0x14, 80), (0x44, 6)):
                        emu.write32(box + off, value)
                    emu.write8(box + 0x25, focused)
                    emu.write8(box + 0x24, 1)                              # a fixed box: the game cut it
                    text_at = emu.read32(box + 0x30)
                    width = emu.call(self.symbols["_box_width"], self.font, box, 0, text_at, f32(1.0))
                    room = 340 - 100 - 6
                    shown = self.expected_fit(name, room, tail=bool(focused))
                    self.assertEqual(width, self.game_width(shown))
                    self.assertLessEqual(width, room)
                    self.fde.fill((10, 20, 30))
                    wrapper = emu.alloc(4)
                    emu.write32(wrapper, self.fde.impl)
                    emu.call(self.symbols["_box_draw"], wrapper, box, 0, text_at, 4, 6, 0xFFFFFFFF, self.font)
                    drawn = bytes(self.fde.screen_image.data)
                    self.assertEqual(drawn, self.screen(shown, own=True))
                    self.assertEqual(self.g.text(box), name)                # the box's text is whole


@needs("fish")
class FishNamesTests(NamesCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantNamesTests(NamesCase, unittest.TestCase):
    game = "plant"


@needs("fish")
class FishDrawNamesTests(DrawNamesCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantDrawNamesTests(DrawNamesCase, unittest.TestCase):
    game = "plant"


if __name__ == "__main__":
    unittest.main()
