"""Copy and Paste in Text Boxes (Unicode Text.dll, both games): the DLL's own code and the game's
text box run in Unicorn against the vanilla executables, the Windows clipboard stood in for.

* Paste posts the clipboard's letters as the game's own "character" events, and the game's box
  (with Unicode: box_char; without: the game's own path) takes them as if typed: CR, LF and Tab
  become spaces, other control characters and lone surrogates are left out, the box keeps its
  byte limit and a name box its 300 letters, a letter with its combining marks or joined emoji
  goes in whole or not at all, a number box (Plant's price box) takes digits only.
* Without either Unicode setting (Mode=none) only printable ASCII is pasted, the stock boxes' set;
  the DLL then changes only the box draw's site.
* Copy puts the box's whole text on the clipboard (a player's full name, not its short form); cut
  also empties the box. A busy clipboard does nothing; it is always closed.
* The keys: Ctrl+V / Shift+Insert, Ctrl+C / Ctrl+Insert, Ctrl+X, not with AltGr, only while a box
  has typing focus, and they never reach the game. A letter past U+FFFF sent as two WM_CHARs is
  posted as its one letter.
"""

from __future__ import annotations

import struct
import unittest

import test_unicode_text as T
from test_unicode_text import E, needs

try:
    import test_unicode_names as N
except ImportError:          # no Unicorn
    N = None

HANDLER = {"fish": (0x40BFC0, T.FISH_EVENTS_GET, T.FISH_EVENTS_POST, 0x402030),
           "plant": (0x40CA90, T.PLANT_EVENTS_GET, T.PLANT_EVENTS_POST, 0x402020)}
BOX_DRAW_SITE = {"fish": 0x40B829, "plant": 0x40C239}
INI = "Unicode Text.ini"
WM_KEYDOWN, WM_CHAR = 0x100, 0x102
VK_CONTROL, VK_SHIFT, VK_MENU, VK_INSERT = 0x11, 0x10, 0x12, 0x2D


class Clip:
    """The game with the DLL installed (Mode from the ini), a stand-in clipboard and event queue."""

    def __init__(self, game: str, mode: str = "ingame") -> None:
        ini = T.GAME_DIR[game] + T.DLL_FOLDER[game] + INI
        existing = {ini: f"[Unicode Text]\r\nMode={mode}\r\nFont=Segoe UI\r\nPaste=1\r\n".encode()}
        self.game = game
        self.g = N.Game(game, existing=existing)
        self.emu = emu = self.g.emu
        self.symbols = self.g.symbols
        handler, events, post, changed = HANDLER[game]
        self.handler = handler
        self.posted: list[int] = []
        self.changes = 0
        emu.hook(events, lambda e: 0x0BAD0000, 0)
        emu.hook(post, self._post, 12)
        emu.hook(changed, self._changed, 8)
        self.clipboard: str | None = ""
        self.busy = False
        self.opened = self.closed = 0
        self.size_override: int | None = None
        self.keys: set[int] = set()
        self.tick = 1000
        emu.hook_import("OpenClipboard", self._open, 4)
        emu.hook_import("CloseClipboard", self._close, 0)
        emu.hook_import("GetClipboardData", self._get, 4)
        emu.hook_import("EmptyClipboard", lambda e: 1, 0)
        emu.hook_import("SetClipboardData", self._set, 8)
        emu.hook_import("GlobalLock", lambda e: e.arg(0), 4)
        emu.hook_import("GlobalUnlock", lambda e: 1, 4)
        emu.hook_import("GlobalSize", self._size, 4)
        emu.hook_import("GlobalAlloc", lambda e: self._alloc(e.arg(1)), 8)
        emu.hook_import("GlobalFree", lambda e: 0, 4)
        emu.hook_import("GetKeyState", lambda e: 0xFF80 if e.arg(0) in self.keys else 0, 4)
        emu.hook_import("GetTickCount", lambda e: self.tick, 0)
        self.allocs: dict[int, int] = {}

    # ---- the stand-ins
    def _post(self, e) -> int:
        assert e.arg(0) == 5
        self.posted.append(e.arg(2))
        return 0

    def _changed(self, e) -> int:
        self.changes += 1
        return 0

    def _open(self, e) -> int:
        if self.busy:
            return 0
        self.opened += 1
        return 1

    def _close(self, e) -> int:
        self.closed += 1
        return 1

    def _get(self, e) -> int:
        if self.clipboard is None or e.arg(0) != 13:              # CF_UNICODETEXT
            return 0
        raw = self.clipboard.encode("utf-16-le", "surrogatepass") +b"\0\0"
        at = self.emu.alloc(len(raw) + 16)
        self.emu.uc.mem_write(at, raw)
        self.allocs[at] = len(raw) if self.size_override is None else self.size_override
        return at

    def _size(self, e) -> int:
        return self.allocs.get(e.arg(0), 0)

    def _alloc(self, size: int) -> int:
        at = self.emu.alloc(size + 16)
        self.allocs[at] = size
        return at

    def _set(self, e) -> int:
        at = e.arg(1)
        raw = bytes(self.emu.uc.mem_read(at, self.allocs[at]))
        self.clipboard = raw.decode("utf-16-le").rstrip("\0")
        return at

    # ---- boxes
    def box(self, text: bytes = b"", limit: int = 0x20, number: bool = False) -> tuple[int, int]:
        emu = self.emu
        box = emu.alloc(0x60)
        emu.uc.mem_write(box, bytes(0x60))
        window = emu.alloc(0x10)
        emu.write8(window + 8, 1)
        buffer = emu.alloc(limit + 8)
        emu.uc.mem_write(buffer, text + b"\0")
        emu.write8(box + 0x25, 1)
        emu.write8(box + 0x2D, 1 if number else 0)
        emu.write32(box + 0x1C, window)
        emu.write32(box + 0x28, limit)
        emu.write32(box + 0x30, buffer)
        return box, buffer

    def paste(self, box: int) -> int:
        """clip_paste, then each posted letter through the game's own box handler, as typed."""
        self.posted.clear()
        n = self.emu.call(self.symbols["_clip_paste"], box)
        for ch in list(self.posted):
            self.emu.call(self.handler, 5, 0, ch, ecx=box)
        return n

    def text(self, box: int) -> bytes:
        return self.emu.cstring(self.emu.read32(box + 0x30))


class ClipboardCase:
    game = "fish"

    def test_paste_goes_in_as_typed_with_line_breaks_as_spaces(self) -> None:
        c = Clip(self.game)
        box, _ = c.box(b"Hi ", limit=1200)
        c.clipboard = "Zoë\r\nline\ttab\x07\x1b\u0085 山田 \U0001F41F é \ud800x"
        c.paste(box)
        self.assertEqual(c.text(box), "Hi Zoë line tab 山田 \U0001F41F é x".encode("utf-8"))
        self.assertEqual((c.opened, c.closed), (1, 1))

    def test_a_name_box_stops_at_300_letters_and_letters_stay_whole(self) -> None:
        c = Clip(self.game)
        box, _ = c.box(("あ" * 298).encode("utf-8"), limit=1200)
        c.clipboard = "ab\U0001F41Fcd"
        c.paste(box)
        self.assertEqual(c.text(box), ("あ" * 298 + "ab").encode("utf-8"))
        # bytes: a 10-byte box with 8 used takes the two-byte é, not the e and its accent (3 bytes)
        box, _ = c.box(b"abcdefgh", limit=10)
        c.clipboard = "éé"
        c.paste(box)
        self.assertEqual(c.text(box), b"abcdefgh")
        c.clipboard = "éé"
        c.paste(box)
        self.assertEqual(c.text(box), "abcdefghé".encode("utf-8"))
        # a joined emoji (family: ZWJ) goes in whole or not at all
        box, _ = c.box(b"", limit=12)
        c.clipboard = "\U0001F468‍\U0001F469‍\U0001F467 x"
        c.paste(box)
        self.assertEqual(c.text(box), b"")
        c.clipboard = "\U0001F44D\U0001F3FD!"
        c.paste(box)
        self.assertEqual(c.text(box), "\U0001F44D\U0001F3FD!".encode("utf-8"))

    def test_a_number_box_takes_digits_only(self) -> None:
        c = Clip(self.game)
        box, _ = c.box(b"", limit=6, number=True)
        c.clipboard = "Price: $1,250.75\n"
        c.paste(box)
        self.assertEqual(c.text(box), b"125075")
        box, _ = c.box(b"", limit=6, number=True)
        c.clipboard = "-42"
        c.paste(box)
        self.assertEqual(c.text(box), b"-42")

    def test_without_unicode_only_printable_ascii(self) -> None:
        c = Clip(self.game, mode="none")
        self.assertEqual(c.emu.read32(self.symbols_of(c)["_utf8_drawing"]), 0)
        box, _ = c.box(b"", limit=0x20)
        c.clipboard = "Zoë 1-2 山 ok\t\U0001F41F!"
        c.paste(box)
        self.assertEqual(c.text(box), b"Zo 1-2  ok !")
        # the stock box's limit (+0x28) as the game keeps it
        box, _ = c.box(b"", limit=0x20)
        c.clipboard = "x" * 100
        c.paste(box)
        self.assertEqual(c.text(box), b"x" * 0x20)
        # copy of a stock box: its Latin-1 bytes
        box, _ = c.box(b"Ren\xe9", limit=0x20)
        c.emu.call(self.symbols_of(c)["_clip_copy"], box, 0)
        self.assertEqual(c.clipboard, "René")

    def symbols_of(self, c: Clip) -> dict:
        return c.symbols

    def test_paste_only_mode_changes_only_the_box_draw(self) -> None:
        c = Clip(self.game, mode="none")
        stock = E.Emulator(T.EXES[self.game], None, {})
        for va, n in N.GAMES[self.game]["sites"]:
            here = bytes(c.emu.uc.mem_read(va, n))
            if va == BOX_DRAW_SITE[self.game]:
                self.assertEqual(here[0], 0xE8)
                self.assertEqual(va + 5 + struct.unpack_from("<i", here, 1)[0], c.symbols["_stub_box_draw"])
            else:
                self.assertEqual(here, bytes(stock.uc.mem_read(va, n)), hex(va))
        self.assertEqual(T.code_bytes(c.emu, T.site_ranges(self.game)), T.code_bytes(stock, T.site_ranges(self.game)))

    def test_huge_and_empty_clipboards(self) -> None:
        c = Clip(self.game)
        box, _ = c.box(b"", limit=0x20)
        c.clipboard = "y" * 200000
        c.paste(box)
        self.assertEqual(c.text(box), b"y" * 0x20)
        self.assertLessEqual(len(c.posted), 0x20)
        c.clipboard = None                       # no text on the clipboard
        box, _ = c.box(b"keep", limit=0x20)
        self.assertEqual(c.paste(box), 0)
        self.assertEqual(c.text(box), b"keep")
        self.assertEqual(c.opened, c.closed)
        # a clipboard whose memory is smaller than its text claims: read no further
        c.clipboard = "abcdef"
        c.size_override = 6
        box, _ = c.box(b"", limit=0x20)
        c.paste(box)
        self.assertEqual(c.text(box), b"abc")

    def test_copy_and_cut_the_whole_text(self) -> None:
        c = Clip(self.game)
        box, _ = c.box("Zoë \U0001F41F".encode("utf-8"), limit=1200)
        self.assertEqual(c.emu.call(c.symbols["_clip_copy"], box, 0), 1)
        self.assertEqual(c.clipboard, "Zoë \U0001F41F")
        self.assertEqual(c.text(box), "Zoë \U0001F41F".encode("utf-8"))
        self.assertEqual(c.emu.call(c.symbols["_clip_copy"], box, 1), 1)          # cut
        self.assertEqual(c.text(box), b"")
        self.assertEqual(c.changes, 1)
        self.assertEqual(c.clipboard, "Zoë \U0001F41F")
        # a player's short form: the full name
        long_name = "Wilhelmina Charlotte Ångström-Lindqvist \U0001F33B of Malmö"
        c.g.type_name(long_name, slot=2)
        box, _ = c.box(N.short_form(long_name), limit=0x20)
        c.emu.call(c.symbols["_clip_copy"], box, 0)
        self.assertEqual(c.clipboard, long_name)
        # a busy clipboard: nothing happens, the box keeps its text
        c.busy = True
        box, _ = c.box(b"stay", limit=0x20)
        self.assertEqual(c.emu.call(c.symbols["_clip_copy"], box, 1), 0)
        self.assertEqual(c.text(box), b"stay")
        c.clipboard = "zzz"
        self.assertEqual(c.paste(box), 0)
        self.assertEqual(c.text(box), b"stay")
        self.assertEqual(c.opened, c.closed)

    def test_the_keys(self) -> None:
        c = Clip(self.game)
        action = c.symbols["_clip_action"]
        cases = {(ord("V"), 1, 0, 0): 1, (VK_INSERT, 0, 1, 0): 1, (ord("C"), 1, 0, 0): 2, (VK_INSERT, 1, 0, 0): 2,
                 (ord("X"), 1, 0, 0): 3, (ord("V"), 1, 0, 1): 0, (ord("V"), 0, 0, 0): 0, (ord("V"), 1, 1, 0): 0,
                 (VK_INSERT, 0, 0, 0): 0, (ord("A"), 1, 0, 0): 0}
        for args, want in cases.items():
            with self.subTest(args=args):
                self.assertEqual(c.emu.call(action, *args), want)

    def test_keys_act_only_with_typing_focus_and_never_reach_the_game(self) -> None:
        c = Clip(self.game)
        window_proc = c.symbols["_text_window@16"]
        reached = []
        old = c.emu.thunk()
        c.emu.hook(old, lambda e: reached.append(e.arg(1)) or 0, 16)
        call_proc = c.emu.thunk()
        c.emu.hook(call_proc, lambda e: reached.append(e.arg(2)) or 0, 20)
        win = c.symbols["_win"]
        c.emu.write32(win + 0x0C, call_proc)     # win.call_proc
        box, _ = c.box(b"", limit=1200)
        # the box drawn with focus: it has typing focus for a moment
        c.emu.call(c.symbols["_clip_seen"], box)
        c.clipboard = "pasted \U0001F600"
        c.keys = {VK_CONTROL}
        c.posted.clear()
        self.assertEqual(c.emu.call(window_proc, 0x1234, WM_KEYDOWN, ord("V"), 0), 0)
        self.assertEqual(c.posted, [ord(ch) for ch in "pasted \U0001F600"])
        self.assertEqual(reached, [])                                       # the game never saw it
        # focus gone (the box lost it, or no box drawn lately): the key goes on to the game
        c.emu.write8(box + 0x25, 0)
        c.posted.clear()
        c.emu.call(window_proc, 0x1234, WM_KEYDOWN, ord("V"), 0)
        self.assertEqual((c.posted, reached), ([], [WM_KEYDOWN]))
        c.emu.write8(box + 0x25, 1)
        c.tick += 5000
        reached.clear()
        c.emu.call(window_proc, 0x1234, WM_KEYDOWN, ord("V"), 0)
        self.assertEqual((c.posted, reached), ([], [WM_KEYDOWN]))

    def test_a_letter_past_ffff_as_two_wm_chars(self) -> None:
        c = Clip(self.game)
        window_proc = c.symbols["_text_window@16"]
        c.posted.clear()
        c.emu.call(window_proc, 0x1234, WM_CHAR, 0xD83D, 0)
        c.emu.call(window_proc, 0x1234, WM_CHAR, 0xDC1F, 0)
        self.assertEqual(c.posted, [0x1F41F])
        box, _ = c.box(b"", limit=1200)
        for ch in c.posted:
            c.emu.call(c.handler, 5, 0, ch, ecx=box)
        self.assertEqual(c.text(box), "\U0001F41F".encode("utf-8"))


@needs("fish")
class FishClipboardTests(ClipboardCase, unittest.TestCase):
    game = "fish"


@needs("plant")
class PlantClipboardTests(ClipboardCase, unittest.TestCase):
    game = "plant"
