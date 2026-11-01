"""Long names (Unicode Text.dll, both games): one name limit for every name box, the short Latin-1
form in the save's fixed fields, the full name in "Names <slot>.dat", and long names fitted on
screen. The DLL's own code and the game's run in Unicorn against the vanilla executables
(tests/test_unicode_text.py builds the DLL from its committed source).

* The name boxes' setLimit(1, 0x20) (the five player rows and the new player's box) gives the
  shared limit; every other box keeps the game's.
* getText into a player's name writes the short form (31 letters, Latin-1, '?' for any other
  letter) and the full name goes into the save folder's "Names <slot>.dat" at once (a rename, or
  the new player's box, which the game copies into row 1 next), written to "Names <slot>.dat.tmp"
  and moved over the old file; setText of that row gives the box the full name again, also after a restart (the file
  is read at start) but not once the stock game has renamed the player.
* The text draw and measure show a player's short form as the full name, fitted to the width the
  game left for a name; the boxes fit their own text and no longer cut it.
"""

from __future__ import annotations

import struct
import unittest

import test_unicode_text as T
from test_unicode_text import E, needs

SLOTS_PATH = "{docs}\\LDW\\{title} - Modded Upgrades\\{title} Fix Patcher Data\\Names {slot}.dat"
NAME_LETTERS = 300
SHORT_BYTES = 32

GAMES = {
    "fish": dict(new_call=0x417D72, new_dst=0x1E3A5, limit_call=0x417124, other_limit_call=0x4290E7, other_limit=8, text_call=0x417833,
                 state_global=0x45ABDC, rows=0x1E3D8, stride=0x2A, set_text=0x40B970, new=0x42A793,
                 free=0x42A6B1, draw=0x4087E0, width=0x4023D0, box_cut=0x40B7ED,
                 sites=((0x40B970, 6), (0x40BC90, 6), (0x40BC30, 8), (0x40B7A3, 5), (0x40B7ED, 2),
                        (0x40B829, 5), (0x4087E0, 7), (0x4023D0, 7))),
    "plant": dict(new_call=0x41B018, new_dst=8, limit_call=0x415B6C, other_limit_call=0x4304C9, other_limit=6, text_call=0x416198,
                  state_global=0x49333C, rows=0x53FC2, stride=0x21, set_text=0x40C380, new=0x44E894,
                  free=0x44E7B3, draw=0x408E20, width=0x402380, box_cut=0x40C1FD,
                  sites=((0x40C380, 6), (0x40C740, 6), (0x40C6E0, 8), (0x40C1B3, 5), (0x40C1FD, 2),
                         (0x40C239, 5), (0x408E20, 7), (0x402380, 7))),
}


def names_path(game: str, slot: int) -> str:
    return SLOTS_PATH.format(docs=T.DOCUMENTS, title=T.tm.GAME_TITLES[game], slot=slot)


def short_form(name: str) -> bytes:
    return bytes(ord(c) if 0x20 <= ord(c) <= 0xFF and not 0x7F <= ord(c) < 0xA0 else 0x3F for c in name)[:31]


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

    def set_row(self, slot: int, raw: bytes) -> None:
        self.emu.uc.mem_write(self.row(slot), raw.ljust(32, b"\0"))

    def box(self, text: bytes = b"", limit: int = 0x20) -> tuple[int, int]:
        """(wrapper, box): a box (vtable aside) holding `text`."""
        emu = self.emu
        box = emu.alloc(0x60)
        emu.uc.mem_write(box, bytes(0x60))
        buffer = emu.alloc(NAME_LETTERS * 4 + 8)
        emu.uc.mem_write(buffer, text + b"\0")
        emu.write32(box + 0x30, buffer)
        emu.write32(box + 0x28, limit)
        wrapper = emu.alloc(0x20)
        emu.write32(wrapper + 0x10, box)
        return wrapper, box

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
        """The name in a name box, its getText into player row 1 (the game's own call): the row."""
        if all(ord(c) < 0x100 for c in name):
            wrapper, _box = self.box(name.encode("latin-1"), limit=NAME_LETTERS)
        else:                                       # any script: the box holds it as UTF-8
            wrapper, _box = self.box(name.encode("utf-8"), limit=4 * NAME_LETTERS)
        dst = self.row(slot)
        self.run_call(self.a["text_call"], wrapper, dst, 0x20)
        return bytes(self.emu.uc.mem_read(dst, 0x20))

    def set_text(self, box: int, text_at: int) -> None:
        self.emu.call(self.a["set_text"], text_at, ecx=box)


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
        g = Game(self.game)
        wrapper, box = g.box(b"Ann")
        g.run_call(GAMES[self.game]["limit_call"], wrapper, 1, 0x20)
        self.assertEqual(g.emu.read32(box + 0x28), 4 * NAME_LETTERS)   # UTF-8: up to 4 bytes a letter
        self.assertEqual(g.text(box), b"Ann")
        wrapper, box = g.box(b"")
        a = GAMES[self.game]
        g.run_call(a["other_limit_call"], wrapper, 1, a["other_limit"])
        self.assertEqual(g.emu.read32(box + 0x28), a["other_limit"])

    def test_short_form_in_the_row_and_the_full_name_beside_the_save(self) -> None:
        g = Game(self.game)
        cases = ["Renée", "A" * 31, "Bartholomew Montgomery Fitzgerald the Third of Ørsted", "é" * NAME_LETTERS]
        for name in cases:
            with self.subTest(name=name[:40]):
                row = g.type_name(name)
                self.assertEqual(row, short_form(name).ljust(32, b"\0"))
                path = names_path(self.game, 1)
                self.assertEqual(g.files["raw"][path], short_form(name) + b"\0" + name.encode("utf-8") + b"\0")

    def test_the_new_players_name_is_written_at_once(self) -> None:
        """The new player's box accepted: Names 1.dat is written before the game copies the name
        into row 1 (no draw, no exit needed), even while row 1 still holds an older typed name."""
        g = Game(self.game)
        g.type_name("Older Name \u2713 one", slot=1)
        path = names_path(self.game, 1)
        name = "\u041d\u043e\u0432\u044b\u0439 \U0001F41F Yeni oyuncu \U0001202D"
        wrapper, _box = g.box(name.encode("utf-8"), limit=4 * NAME_LETTERS)
        dst = g.state + GAMES[self.game]["new_dst"]
        g.files["moves"].clear()
        g.run_call(GAMES[self.game]["new_call"], wrapper, dst, 0x20)
        self.assertEqual(bytes(g.emu.uc.mem_read(dst, 0x20)), short_form(name).ljust(32, b"\0"))
        self.assertEqual(g.files["raw"][path], short_form(name) + b"\0" + name.encode("utf-8") + b"\0")
        # REPLACE_EXISTING | WRITE_THROUGH, from the temporary file
        self.assertEqual(g.files["moves"], [(path + ".tmp", path, 0x1 | 0x8)])
        self.assertNotIn(path + ".tmp", g.files["raw"])
        # the game copies it into row 1: the row shows the full name
        g.set_row(1, short_form(name))
        _wrapper, box = g.box()
        g.set_text(box, g.row(1))
        self.assertEqual(g.text(box), name.encode("utf-8"))

    def test_a_rename_is_written_at_once_through_a_temporary_file(self) -> None:
        g = Game(self.game)
        name = "\u00c7a\u011fr\u0131 Y\u0131lmaz \u5c71\u7530 \U0001F600 rename"
        path = names_path(self.game, 3)
        g.type_name(name, slot=3)
        self.assertEqual(g.files["raw"][path], short_form(name) + b"\0" + name.encode("utf-8") + b"\0")
        self.assertIn((path + ".tmp", path, 0x9), g.files["moves"])
        # a move Windows refuses: the file is written in place, as before, the temporary removed
        g.emu.hook_import("MoveFileExW", lambda e: 0, 12)
        other = "Second name, \u00fcn\u00efc\u00f6d\u00e9 \u2728"
        g.type_name(other, slot=3)
        self.assertEqual(g.files["raw"][path], short_form(other) + b"\0" + other.encode("utf-8") + b"\0")
        self.assertNotIn(path + ".tmp", g.files["raw"])

    def test_viewing_a_long_name_never_shortens_it(self) -> None:
        """A box set up with the game's 32-byte limit (no name site's setLimit) shown a 300-letter
        name: setText keeps it whole (the game's setText grows the limit to the text), and the
        getText that follows writes the same full name back, in the row and in Names <slot>.dat."""
        name = ("Å山\U0001F41F" * 100)[:300]
        g = Game(self.game)
        g.type_name(name, slot=4)
        path = names_path(self.game, 4)
        before = g.files["raw"][path]
        wrapper, box = g.box(b"", limit=0x20)
        g.set_text(box, g.row(4))
        self.assertEqual(g.text(box), name.encode("utf-8"))
        dst = g.row(4)
        g.run_call(GAMES[self.game]["text_call"], wrapper, dst, 0x20)
        self.assertEqual(bytes(g.emu.uc.mem_read(dst, 0x20)), short_form(name).ljust(32, b"\0"))
        self.assertEqual(g.files["raw"][path], before)
        self.assertEqual(g.files["raw"][path], short_form(name) + b"\0" + name.encode("utf-8") + b"\0")

    def test_set_text_of_a_row_gives_the_full_name(self) -> None:
        g = Game(self.game)
        long_name = "Wilhelmina Charlotte Ångström-Lindqvist of Malmö"
        g.type_name(long_name, slot=1)
        _wrapper, box = g.box()
        g.set_text(box, g.row(1))
        self.assertEqual(g.text(box), long_name.encode("utf-8"))
        # the short form as text (not the row itself) too
        copy = g.emu.text(short_form(long_name).decode("latin-1"))
        _wrapper, box = g.box()
        g.set_text(box, copy)
        self.assertEqual(g.text(box), long_name.encode("utf-8"))
        # a short name is its own full name: nothing changes
        g.set_row(2, b"Bob")
        _wrapper, box = g.box()
        g.set_text(box, g.row(2))
        self.assertEqual(g.text(box), b"Bob")

    def test_the_file_is_read_at_start_and_checked_against_the_row(self) -> None:
        long_name = "Maximilian Alexander von Hohenstein-Waldburg"
        short = short_form(long_name)
        existing = {names_path(self.game, 3): short + b"\0" + long_name.encode("utf-8") + b"\0"}
        g = Game(self.game, existing=existing)
        g.set_row(3, short)
        _wrapper, box = g.box()
        g.set_text(box, g.row(3))
        self.assertEqual(g.text(box), long_name.encode("utf-8"))
        # the stock game renamed the player: the file is not used
        g.set_row(3, b"Someone Else")
        _wrapper, box = g.box()
        g.set_text(box, g.row(3))
        self.assertEqual(g.text(box), b"Someone Else")

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
        placeholder = self.game_width(b"_" * 26)
        for name in ("Wilhelmina Charlotte Ångström-Lindqvist", "Bartholomew Montgomery Fitzgerald the Third "
                     "of the Northern Reaches of Ørsted"):
            with self.subTest(name=name):
                self.g.type_name(name, slot=2)
                self.g.emu.uc.mem_write(self.g.row(1), short_form(name).ljust(32, b"\0"))
                short = short_form(name)
                budget = max(self.game_width(short), placeholder)
                shown = self.expected_fit(name.encode("latin-1"), budget, tail=False)
                self.assertEqual(self.screen(short, own=False), self.screen(shown, own=True))
                self.assertEqual(self.hooked_width(short), self.game_width(shown))
        # any other text is the game's own, pixel for pixel
        for text in (b"Hello, world", b"Renee", b"__________________________", short_form("x" * 40)):
            self.assertEqual(self.screen(text, own=False), self.screen(text, own=True))
            self.assertEqual(self.hooked_width(text), self.game_width(text))

    def test_a_name_within_the_games_text_is_the_full_name(self) -> None:
        """The main menu's "Player: <name>": the short form in it is the full name, the whole text
        fitted to the wider of itself and itself with the game's name placeholder for the name."""
        name = "Bartholomew Montgomery Fitzgerald the Third of the Northern Reaches"
        self.g.type_name(name, slot=1)
        short = short_form(name)
        text = b"Player: " + short
        budget = max(self.game_width(text), self.game_width(b"Player: " + b"_" * 26))
        shown = self.expected_fit(b"Player: " + name.encode("latin-1"), budget, tail=False)
        self.assertEqual(self.screen(text, own=False), self.screen(shown, own=True))
        self.assertEqual(self.hooked_width(text), self.game_width(shown))

    def test_boxes_fit_their_text(self) -> None:
        emu = self.fde.emu
        long_name = "Wilhelmina Charlotte Ångström-Lindqvist of Malmö and Stockholm".encode("latin-1")
        for focused in (0, 1):
            for name in (b"Ann", long_name):
                with self.subTest(focused=focused, name=name[:10]):
                    _wrapper, box = self.g.box(name, limit=NAME_LETTERS)
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
