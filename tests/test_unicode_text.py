"""Render Unicode with In-Game Fonts, stage 1 (Latin-1): "Unicode Text.dll" for each game, its own
code run in Unicorn against the vanilla executables (tests/store_emulator.py, the DLL rebuilt from
its committed source with a map).

* It installs every site or none: each site's stock bytes are checked, the font pictures must be in
  Images, and a changed byte anywhere leaves the game exactly as it was.
* Typing: the game's own key path runs with the DLL's stub. A key whose character is U+00A0-U+00FF
  (Fish: keysym.unicode; Plant: SDL_TEXTINPUT's UTF-8) reaches the text box as that Latin-1 byte,
  AltGr included; every other key is posted exactly as the stock game posts it. The game's own text
  box (0x40BFC0 / 0x40CA90) then stores the name's bytes.
* Drawing: the game's own font loader and draw (tests/font_draw_emulator.py) with the name and table
  the DLL points the font set-up at and the shipped picture: the game's own letters are drawn exactly
  as before, and every Latin-1 letter is the patcher-made one (scripts/build_unicode_assets.py),
  pixel for pixel.
* Saves: a slot saved with such a name loads in the stock game byte for byte, and the stock game
  draws it without trouble (Fish Tycoon's paddington has no é: it draws its record 0, a space).
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

from picture_image import Image  # noqa: E402
import text_maker as tm  # noqa: E402

try:
    import store_emulator as E
    import font_draw_emulator as fde
except ImportError:          # no Unicorn
    E = fde = None

VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
EXES = {"fish": VANILLA / "Fish Tycoon" / "Fish Tycoon.exe", "plant": VANILLA / "Plant Tycoon" / "Plant Tycoon.exe"}
ASSETS = {"fish": ROOT / "assets" / "fish_tycoon_unicode", "plant": ROOT / "assets" / "plant_tycoon_unicode"}
PROJECTS = {"fish": "ftfp_fish_unicode", "plant": "ftfp_plant_unicode"}
GAME_DIR = {"fish": "C:\\Games\\Fish Tycoon - Modded Upgrades\\", "plant": "C:\\Games\\Plant Tycoon - Modded Upgrades\\"}
DLL_FOLDER = {"fish": "Fish Tycoon Fix Patcher DLLs\\", "plant": "Plant Tycoon Fix Patcher DLLs\\"}

# (push table, push name) sites and the font each makes
FONT_SITES = {
    "fish": ((0x42A45F, "paddington_tt_18"), (0x42A4CF, "paddington_tt_30"),
             (0x410A9F, "font_triplex_sanslightlin_bold_16pt")),
    "plant": ((0x412D9F, "PTfontsmall"),),
}
INPUT_SITES = {"fish": (0x403ED4, 8), "plant": (0x40439B, 9)}

FISH_EVENTS_GET, FISH_EVENTS_POST = 0x004021E0, 0x00402010
PLANT_EVENTS_GET, PLANT_EVENTS_POST = 0x00402190, 0x00402000
KMOD_SHIFT, KMOD_CTRL_ALT, KMOD_CAPS = 0x0001, 0x0240, 0x2000    # AltGr: left Ctrl + right Alt

NAMES = ("Renée", "Zoë Müller", "François", "Ångström", "Señor Niño", "¡Olé! ¿Qué?", "Æsir Øl ß",
         "Ýý ÿ þÞ ðÐ", "£5 ½ ¼ ¾ © ® ° ± µ ¶ § ¤ ¢ ¥ « » ¬ ¦ ª º ¹ ² ³ × ÷", "Paddington %*+<=>[\\]^{|}~")


def latin1() -> list[int]:
    return list(range(0xA0, 0x100))


# Every byte the extended fonts draw: Windows-1252 (Latin-1 from 0xA0), but for the five it
# leaves undefined. Translations.dll writes Windows-1252 while FtfpUnicodeTextActive answers 0.
CP1252_BYTES = [b for b in range(0x20, 0x100) if b != 0x7F and b not in (0x81, 0x8D, 0x8F, 0x90, 0x9D)]
CP1252_SAMPLE = "€5 „Grüße“ ‘quoted’ – — … • ™ Œuvre œ Šš Žž Ÿ ‹›"


def _ready(game: str) -> bool:
    return (E is not None and E.toolchain_ready() and EXES[game].is_file()
            and (ASSETS[game] / "Unicode Text.dll").is_file())


def needs(game: str):
    return unittest.skipUnless(_ready(game), "needs Unicorn, the pinned MSVC toolset, the vanilla game and the DLL")


_BUILT: dict[str, tuple[Path, dict]] = {}
_TEMPS: list[tempfile.TemporaryDirectory] = []


def built(game: str) -> tuple[Path, dict]:
    if game not in _BUILT:
        temp = tempfile.TemporaryDirectory()
        _TEMPS.append(temp)
        _BUILT[game] = E.build_with_map(PROJECTS[game], ASSETS[game] / "Unicode Text.dll", Path(temp.name))
    return _BUILT[game]


def tearDownModule() -> None:
    for temp in _TEMPS:
        temp.cleanup()


def hook_windows(emu, game: str, present: set[str] | None = None) -> dict:
    """The DLL's Windows calls: its module and the game's paths, the Images pictures that are
    there (all of them unless `present` says which), page protection, Documents, and the files it
    writes ({path: text}; "log" and "text" are its log's)."""
    files: dict = {"log": None, "written": {}, "folders": []}
    handles: dict = {}
    special = emu.thunk()

    def documents(e) -> int:
        e.uc.mem_write(e.arg(1), (DOCUMENTS + "\0").encode("utf-16-le"))
        return 1

    emu.hook(special, documents, 16)

    def module_name(e) -> int:
        path = GAME_DIR[game] + (DLL_FOLDER[game] + "Unicode Text.dll" if e.arg(0) else f"{tm.GAME_TITLES[game]}"
                                 " - Modded Upgrades.exe")
        e.uc.mem_write(e.arg(1), (path + "\0").encode("utf-16-le"))
        return len(path)

    def attributes(e) -> int:
        path = e.wstring(e.arg(0))
        name = path.rsplit("\\", 1)[-1]
        ok = path.startswith(GAME_DIR[game] + "Images\\") and (present is None or name in present)
        return 0x20 if ok else 0xFFFFFFFF

    def protect(e) -> int:
        e.write32(e.arg(3), 0x20)
        return 1

    def create(e) -> int:
        path = e.wstring(e.arg(0))
        if path.endswith(".log"):
            files["log"] = path
        handle = 0x44 + 4 * len(handles)
        handles[handle] = path
        return handle

    def write(e) -> int:
        text = bytes(e.uc.mem_read(e.arg(1), e.arg(2))).decode("ascii")
        path = handles[e.arg(0)]
        files["written"][path] = text
        if path.endswith(".log"):
            files["text"] = text
        e.write32(e.arg(3), e.arg(2))
        return 1

    def make_folder(e) -> int:
        files["folders"].append(e.wstring(e.arg(0)))
        return 1

    emu.hook_import("GetModuleFileNameW", module_name, 12)
    emu.hook_import("GetFileAttributesW", attributes, 4)
    emu.hook_import("VirtualProtect", protect, 16)
    emu.hook_import("FlushInstructionCache", lambda e: 1, 12)
    emu.hook_import("GetCurrentProcess", lambda e: 0xFFFFFFFF, 0)
    emu.hook_import("CreateFileW", create, 28)
    emu.hook_import("WriteFile", write, 20)
    emu.hook_import("CloseHandle", lambda e: 1, 4)
    emu.hook_import("LoadLibraryW", lambda e: 0x7000_0000, 4)
    emu.hook_import("GetProcAddress", lambda e: special if e.cstring(e.arg(1)) == b"SHGetSpecialFolderPathW" else 0, 8)
    emu.hook_import("CreateDirectoryW", make_folder, 8)
    return files


DOCUMENTS = "C:\\Users\\Player\\Documents"


def marker_path(game: str) -> str:
    title = tm.GAME_TITLES[game]
    return f"{DOCUMENTS}\\LDW\\{title} - Modded Upgrades\\{title} Fix Patcher Data\\Unicode Text.ini"


DLL_BASE = 0x10000000


def startup(emu, symbols: dict) -> int:
    """DllMain's part (the DLL's own module handle), then FtfpStartup as the loader calls it."""
    emu.write32(symbols["_self_module"], DLL_BASE)
    return emu.call(symbols["_FtfpStartup@0"])


def code_bytes(emu, ranges) -> bytes:
    return b"".join(bytes(emu.uc.mem_read(va, n)) for va, n in ranges)


def site_ranges(game: str) -> list[tuple[int, int]]:
    return [INPUT_SITES[game]] + [(va, 10) for va, _key in FONT_SITES[game]]


def picture_names(game: str) -> set[str]:
    return {p.name for p in (ASSETS[game] / "Images").glob("*_unicode.png")}


# ------------------------------------------------------------------ install


class InstallCase(unittest.TestCase):
    game = "fish"

    def emulator(self, present=None):
        dll, symbols = built(self.game)
        emu = E.Emulator(EXES[self.game], dll, symbols)
        emu.uc.mem_map(0, 0x1000)                                  # fs:[0] for __try
        files = hook_windows(emu, self.game, present)
        return emu, symbols, files

    def check_installs_all_or_none(self) -> None:
        emu, symbols, files = self.emulator()
        stock = code_bytes(emu, site_ranges(self.game))
        self.assertEqual(startup(emu, symbols), 1)
        self.assertIn("installed", files["text"])
        self.assertTrue(files["log"].endswith(DLL_FOLDER[self.game] + "Unicode Text.log"))
        # the save folder's marker for the patcher's tools, its folders made as needed
        self.assertIn("Render Unicode with In-Game Fonts", files["written"][marker_path(self.game)])
        self.assertEqual(files["folders"][-1], marker_path(self.game).rsplit("\\", 1)[0])
        after = code_bytes(emu, site_ranges(self.game))
        self.assertNotEqual(stock, after)
        # the input site is a jump into the DLL, the rest nops
        va, n = INPUT_SITES[self.game]
        site = bytes(emu.uc.mem_read(va, n))
        self.assertEqual(site[0], 0xE9)
        self.assertEqual(site[5:], b"\x90" * (n - 5))
        self.assertEqual(va + 5 + struct.unpack_from("<i", site, 1)[0], symbols["_stub_input"])
        # each font's pushes point at the DLL's name and table, its name the shipped picture's
        for va, _key in FONT_SITES[self.game]:
            push = bytes(emu.uc.mem_read(va, 10))
            self.assertEqual((push[0], push[5]), (0x68, 0x68))
            name = emu.cstring(struct.unpack_from("<I", push, 6)[0]).decode("ascii")
            self.assertIn(name + ".png", picture_names(self.game))
        self.assertEqual(startup(emu, symbols), 1)                 # once only
        self.assertEqual(code_bytes(emu, site_ranges(self.game)), after)
        # a changed byte at any site: nothing at all is written
        for va, n in site_ranges(self.game):
            for at in (va, va + n - 1):
                with self.subTest(changed=hex(at)):
                    emu, symbols, files = self.emulator()
                    emu.write8(at, emu.uc.mem_read(at, 1)[0] ^ 0x5A)
                    before = code_bytes(emu, site_ranges(self.game))
                    self.assertEqual(startup(emu, symbols), 0)
                    self.assertEqual(code_bytes(emu, site_ranges(self.game)), before)
                    self.assertIn("not the stock code", files["text"])
                    self.assertNotIn(marker_path(self.game), files["written"])
        # a picture missing from Images: nothing written either
        for missing in sorted(picture_names(self.game)):
            with self.subTest(missing=missing):
                emu, symbols, files = self.emulator(picture_names(self.game) - {missing})
                self.assertEqual(startup(emu, symbols), 0)
                self.assertEqual(code_bytes(emu, site_ranges(self.game)), stock)
                self.assertIn("missing", files["text"])


@needs("fish")
class FishInstallTests(InstallCase):
    game = "fish"

    def test_installs_every_site_or_none(self) -> None:
        self.check_installs_all_or_none()


@needs("plant")
class PlantInstallTests(InstallCase):
    game = "plant"

    def test_installs_every_site_or_none(self) -> None:
        self.check_installs_all_or_none()


# ------------------------------------------------------------------ typing


class FishKeys:
    """The game's key-down path (0x403EAA) to the next event (0x403EF7), its posts recorded."""

    def __init__(self, patched: bool) -> None:
        dll, symbols = built("fish") if patched else (None, {})
        emu = self.emu = E.Emulator(EXES["fish"], dll, symbols)
        emu.uc.mem_map(0, 0x1000)
        if patched:
            hook_windows(emu, "fish")
            assert startup(emu, symbols) == 1
        self.posts: list[tuple[int, int, int]] = []
        emu.hook(FISH_EVENTS_GET, lambda e: 0x0BAD0000, 0)
        emu.hook(FISH_EVENTS_POST, self._post, 0xC)
        self.ebp = emu.alloc(0x40)

    def _post(self, e) -> int:
        self.posts.append((e.arg(0), e.arg(1), e.arg(2)))
        return 0

    def key(self, sym: int, unicode: int, mod: int = 0) -> list[tuple[int, int, int]]:
        emu = self.emu
        self.posts = []
        esp = E.STACK + E.STACK_SIZE - 0x1000
        emu.uc.mem_write(esp, bytes(0x40))
        emu.write8(esp + 0x10, 2)                                   # SDL_KEYDOWN
        emu.write32(esp + 0x18, sym)
        emu.write32(esp + 0x1C, mod)
        emu.write32(esp + 0x20, unicode)
        emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(E.X.UC_X86_REG_EBP, self.ebp)
        emu.uc.reg_write(E.X.UC_X86_REG_ECX, 2)
        emu.uc.emu_start(0x00403EAA, 0x00403EF7, count=10_000)
        self.assertion = emu.uc.reg_read(E.X.UC_X86_REG_ESP) == esp
        assert self.assertion, "the key path left the stack unbalanced"
        return self.posts


class PlantText:
    """The game's SDL_TEXTINPUT path (0x404385) to the next event (0x404467), its posts recorded."""

    def __init__(self, patched: bool) -> None:
        dll, symbols = built("plant") if patched else (None, {})
        emu = self.emu = E.Emulator(EXES["plant"], dll, symbols)
        emu.uc.mem_map(0, 0x1000)
        if patched:
            hook_windows(emu, "plant")
            assert startup(emu, symbols) == 1
        self.posts: list[tuple[int, int, int]] = []
        emu.hook(PLANT_EVENTS_GET, lambda e: 0x0BAD0000, 0)
        emu.hook(PLANT_EVENTS_POST, self._post, 0xC)

    def _post(self, e) -> int:
        self.posts.append((e.arg(0), e.arg(1), e.arg(2)))
        return 0

    def text(self, utf8: bytes) -> list[tuple[int, int, int]]:
        emu = self.emu
        self.posts = []
        esp = E.STACK + E.STACK_SIZE - 0x1000
        emu.uc.mem_write(esp, bytes(0x60))
        emu.uc.mem_write(esp + 0x30, utf8[:31] + b"\0")
        emu.uc.reg_write(E.X.UC_X86_REG_ESP, esp)
        emu.uc.reg_write(E.X.UC_X86_REG_EBX, 0)
        emu.uc.emu_start(0x00404385, 0x00404467, count=10_000)
        assert emu.uc.reg_read(E.X.UC_X86_REG_ESP) == esp, "the text path left the stack unbalanced"
        return self.posts


def text_box(emu, handler: int, events_get: int, changed: int, chars: list[int], limit: int = 31) -> bytes:
    """The game's text box key handler, given the characters as posted: what it stores."""
    box = emu.alloc(0x60)
    emu.uc.mem_write(box, bytes(0x60))
    focus = emu.alloc(0x10)
    emu.write8(focus + 8, 1)
    buffer = emu.alloc(0x40)
    emu.uc.mem_write(buffer, bytes(0x40))
    emu.write8(box + 0x25, 1)                   # it has the focus
    emu.write32(box + 0x1C, focus)
    emu.write32(box + 0x28, limit)
    emu.write32(box + 0x30, buffer)
    emu.hook(events_get, lambda e: 0x0BAD0000, 0)
    emu.hook(changed, lambda e: 0, 8)           # the box's "text changed" event (0xC)
    for ch in chars:
        emu.call(handler, 5, 0, ch, ecx=box)
    return emu.cstring(buffer)


@needs("fish")
class FishTypingTests(unittest.TestCase):
    def test_every_latin1_letter_reaches_the_text_box_as_its_byte(self) -> None:
        keys = FishKeys(patched=True)
        for code in latin1():
            for mod in (0, KMOD_SHIFT, KMOD_CTRL_ALT, KMOD_CAPS):
                with self.subTest(code=hex(code), mod=hex(mod)):
                    self.assertEqual(keys.key(code, code, mod), [(5, code, code)])
        # the stock game drops them all
        stock = FishKeys(patched=False)
        for code in latin1():
            self.assertNotIn(code, [post[2] & 0xFF for post in stock.key(code, code)])

    def test_every_other_key_is_posted_as_the_stock_game_posts_it(self) -> None:
        patched, stock = FishKeys(patched=True), FishKeys(patched=False)
        cases = []
        for unicode in list(range(0x00, 0x80)) + [0x100, 0x142, 0x20AC, 0x3042]:
            for sym in {unicode if unicode < 0x100 else 0, 0x61, 0x111, 0x100 + 5, 0x13A}:
                for mod in (0, KMOD_SHIFT, KMOD_CTRL_ALT, KMOD_CAPS, 0x0400):
                    cases.append((sym, unicode, mod))
        for sym, unicode, mod in cases:
            with self.subTest(sym=hex(sym), unicode=hex(unicode), mod=hex(mod)):
                self.assertEqual(patched.key(sym, unicode, mod), stock.key(sym, unicode, mod))

    def test_the_text_box_stores_the_typed_name(self) -> None:
        keys = FishKeys(patched=True)
        for name in NAMES[:7]:
            raw = name.encode("latin-1")
            posted = []
            for byte in raw:
                posted += [post[2] for post in keys.key(byte, byte, KMOD_SHIFT if chr(byte).isupper() else 0)]
            with self.subTest(name=name):
                stored = text_box(keys.emu, 0x0040BFC0, FISH_EVENTS_GET, 0x00402030, posted)
                self.assertEqual(stored, raw)
        # the stock path's sign-extended byte (what 0x403F3A would post) is refused by the box
        self.assertEqual(text_box(keys.emu, 0x0040BFC0, FISH_EVENTS_GET, 0x00402030, [0xFFFFFFE9]), b"")


@needs("plant")
class PlantTypingTests(unittest.TestCase):
    def test_every_latin1_letter_reaches_the_text_box_as_its_byte(self) -> None:
        text = PlantText(patched=True)
        stock = PlantText(patched=False)
        for code in latin1():
            with self.subTest(code=hex(code)):
                self.assertEqual(text.text(chr(code).encode("utf-8")), [(5, 0, code)])
                self.assertEqual(stock.text(chr(code).encode("utf-8")), [])

    def test_everything_else_is_as_the_stock_game_has_it(self) -> None:
        patched, stock = PlantText(patched=True), PlantText(patched=False)
        samples = [bytes([b]) for b in range(1, 0x80)] + [
            "\u0080".encode(), "\u009f".encode(), "ł".encode(), "€".encode(), "あ".encode(), "😀".encode(),
            b"ab", b"\xc3", b"\xc3\x28", b"\xc2\xc2", b"\xe2\x82"]
        for raw in samples:
            with self.subTest(raw=raw):
                self.assertEqual(patched.text(raw), stock.text(raw))

    def test_the_text_box_stores_the_typed_name(self) -> None:
        text = PlantText(patched=True)
        for name in NAMES[:7]:
            posted = []
            for ch in name:
                posted += [post[2] for post in text.text(ch.encode("utf-8"))]
            with self.subTest(name=name):
                self.assertEqual(text_box(text.emu, 0x0040CA90, PLANT_EVENTS_GET, 0x00402020, posted), name.encode("latin-1"))


# ------------------------------------------------------------------ drawing


def extended_font(game: str, key: str, name: str, table_records: list[list[int]]) -> tm.GameFont:
    """The Text Maker's model of the font the patched game makes: the shipped picture and the
    DLL's table, laid out as the loader lays it."""
    spec = next(s for s in tm.FONTS[game] if s.key == key)
    sheet = Image.from_png((ASSETS[game] / "Images" / f"{name}.png").read_bytes())
    records, height = tm.relayout(table_records, sheet.width)
    font = tm.GameFont(game, spec, sheet, records, height)
    font.index = tm.byte_index(records)
    return font


def dll_table(emu, address: int) -> list[list[int]]:
    records = []
    while True:
        rec = list(struct.unpack("<5i", emu.uc.mem_read(address + 20 * len(records), 20)))
        if rec[0] == 0:
            return records
        records.append(rec)


class DrawCase(unittest.TestCase):
    game = "fish"
    BG = (24, 40, 72)

    def check_fonts(self) -> None:
        dll, symbols = built(self.game)
        vanilla_fonts = {f.key: f for f in tm.load_fonts(self.game, EXES[self.game].parent)}
        for va, key in FONT_SITES[self.game]:
            emu = fde.FontDrawEmulator(self.game, screen_w=3200, dll=dll, symbols=symbols)
            hook_windows(emu.emu, self.game)
            self.assertEqual(startup(emu.emu, symbols), 1)
            push = bytes(emu.emu.uc.mem_read(va, 10))
            table, name_at = struct.unpack_from("<I", push, 1)[0], struct.unpack_from("<I", push, 6)[0]
            name = emu.emu.cstring(name_at).decode("ascii")
            records = dll_table(emu.emu, table)
            font = extended_font(self.game, key, name, records)
            handle = emu.load_font_at(name_at, table, (ASSETS[self.game] / "Images" / f"{name}.png").read_bytes())
            stock = vanilla_fonts[key]
            # the game's own records are laid out where they were
            self.assertEqual([r[1:] for r in font.records[:len(stock.records)]], [r[1:] for r in stock.records])
            # every byte the stock font really has draws the same pixels; every other Latin-1
            # byte now has its own letter (not record 0)
            for byte in CP1252_BYTES:
                with self.subTest(font=key, byte=hex(byte)):
                    self.assertTrue(font.has_byte(byte))
                    glyph = font.game_glyph(byte)
                    if stock.has_byte(byte):
                        self.assertEqual(glyph.pixels.data, stock.game_glyph(byte).pixels.data)
                    else:
                        self.assertNotEqual(font.index[byte], 0)
            # the composed accents are the Text Maker's own (made from the font's own pixels)
            for ch in "éèàù":
                if not stock.has_byte(ord(ch)):
                    made = tm.make_glyph(stock, ch)
                    self.assertEqual(font.game_glyph(ord(ch)).pixels.data,
                                     fde_pad(made.pixels, made.advance, font.line_height).data)
            # the game's own draw, pixel for pixel, for names and every letter
            for text in NAMES + ("".join(chr(b) for b in latin1()), CP1252_SAMPLE):
                for colour in (0xFFFFFFFF, 0xFF40D0FF, 0):
                    with self.subTest(font=key, text=text, colour=hex(colour)):
                        raw = text.encode("cp1252")
                        emu.fill(self.BG)
                        emu.blits = []
                        emu.draw(handle, raw, 5, 7, colour)
                        screen = Image(emu.screen_image.width, emu.screen_image.height)
                        screen.data[:] = bytes((*self.BG, 255)) * (screen.width * screen.height)
                        tm.render_game_bytes(font, raw, _rgb(colour), screen, 5, 7)
                        self.assertEqual(screen.data, emu.screen_image.data)
                        self.assertEqual(len(emu.blits), sum(1 for b in raw if font.game_glyph(b).advance))


def _rgb(colour: int) -> int:
    if colour == 0:
        return 0xFFFFFF
    return ((colour & 0xFF) << 16) | (colour & 0xFF00) | ((colour >> 16) & 0xFF)


def fde_pad(px: Image, width: int, height: int) -> Image:
    """A letter's pixels as its record holds them: `width` wide (its advance), the line tall."""
    out = Image(width, height)
    for row in range(min(height, px.height)):
        n = min(px.width, width) * 4
        out.data[row * width * 4: row * width * 4 + n] = px.data[row * px.width * 4: row * px.width * 4 + n]
    return out


@needs("fish")
class FishDrawTests(DrawCase):
    game = "fish"

    def test_the_three_fonts_draw_every_latin1_letter(self) -> None:
        self.check_fonts()


@needs("plant")
class PlantDrawTests(DrawCase):
    game = "plant"

    def test_the_font_draws_every_latin1_letter(self) -> None:
        self.check_fonts()


# ------------------------------------------------------------------ saves

FISH_SAVE_BODY = 0x1E3C8                 # tests/test_vanilla_fixes.py: the state from +8
FISH_NAME_IN_BODY = 0x1E3B5 - 0x18       # save_tools: the name at 0x1E3B5 in the file


@needs("fish")
class FishSaveTests(unittest.TestCase):
    def load(self, dll=None, symbols=None) -> tuple[object, bytes]:
        body = bytearray((i * 7 + 3) & 0xFF for i in range(FISH_SAVE_BODY))
        name = "Renée Ørsted".encode("latin-1")
        body[FISH_NAME_IN_BODY: FISH_NAME_IN_BODY + 32] = name.ljust(32, b"\0")
        emu = E.Emulator(EXES["fish"], dll, symbols or {})
        emu.uc.mem_map(0, 0x1000)
        if dll is not None:
            hook_windows(emu, "fish")
            self.assertEqual(startup(emu, symbols), 1)
        emu.hook_fish_save_read(bytes(body))
        state = emu.alloc(FISH_SAVE_BODY + 0x1000)
        self.assertEqual(emu.call(0x0041AE70, 1, ecx=state) & 0xFF, 1)
        loaded = bytes(emu.uc.mem_read(state, FISH_SAVE_BODY + 8))
        self.assertEqual(loaded[8:], bytes(body))
        return emu, loaded[8 + FISH_NAME_IN_BODY: 8 + FISH_NAME_IN_BODY + len(name)]

    def test_a_latin1_name_loads_in_the_stock_and_the_patched_game(self) -> None:
        _emu, stock_name = self.load()
        dll, symbols = built("fish")
        _emu, patched_name = self.load(dll, symbols)
        self.assertEqual(stock_name, patched_name)
        self.assertEqual(stock_name.decode("latin-1"), "Renée Ørsted")

    def test_the_stock_game_draws_such_a_name_without_trouble(self) -> None:
        name = "Renée Ørsted".encode("latin-1")
        for font in tm.load_fonts("fish", EXES["fish"].parent):
            emu = fde.FontDrawEmulator("fish")
            key = {"font_triplex_sanslightlin_bold_16pt": "FONT_TRIPLEX_SANSLIGHTLIN_BOLD_16PT"}.get(font.key, font.key)
            handle = emu.load_font(key, font.spec.table)
            emu.fill((0, 0, 0))
            emu.draw(handle, name, 0, 0, 0xFFFFFFFF)
            # each letter it lacks is its record 0: paddington's and triplex's is a space
            self.assertEqual(font.records[0][0], 0x20)
            screen = Image(emu.screen_image.width, emu.screen_image.height)
            screen.data[:] = bytes((0, 0, 0, 255)) * (screen.width * screen.height)
            tm.render_game_bytes(font, name.replace(b"\xe9", b" ").replace(b"\xd8", b" "), 0xFFFFFF, screen, 0, 0)
            self.assertEqual(screen.data, emu.screen_image.data)



class TranslationsContractTests(unittest.TestCase):
    """The Translations helper's contract: "Translations.dll" writes UTF-8 only when a DLL loaded
    before it exports FtfpUnicodeTextActive (stdcall, no arguments) and it returns nonzero."""

    def check(self, game: str) -> None:
        dll, symbols = built(game)
        exports = E.pe_exports(dll.read_bytes()) if hasattr(E, "pe_exports") else None
        self.assertIn(b"FtfpUnicodeTextActive", dll.read_bytes())
        if exports is not None:
            self.assertIn("FtfpUnicodeTextActive", exports)
        emu = E.Emulator(EXES[game], dll, symbols)
        emu.uc.mem_map(0, 0x1000)
        hook_windows(emu, game)
        active = symbols["_FtfpUnicodeTextActive@0"]
        self.assertEqual(emu.call(active), 0)                       # not installed yet
        self.assertEqual(startup(emu, symbols), 1)
        # This stage draws the game's bytes (Windows-1252 letters included), not UTF-8: it answers 0
        self.assertEqual(emu.call(active), 0)
        emu.write32(symbols["_utf8_drawing"], 1)                    # once it draws UTF-8
        self.assertEqual(emu.call(active), 1)

    @needs("fish")
    def test_fish(self) -> None:
        self.check("fish")

    @needs("plant")
    def test_plant(self) -> None:
        self.check("plant")

    def test_def_files_export_it(self) -> None:
        for game in ("fish", "plant"):
            text = (ROOT / "native" / PROJECTS[game] / f"{PROJECTS[game]}.def").read_text(encoding="ascii")
            self.assertIn("FtfpUnicodeTextActive = _FtfpUnicodeTextActive@0", text)

    def test_unicode_text_loads_before_any_other_tail(self) -> None:
        import ds_fish_loader
        for game, base in (("fish", ds_fish_loader.fish_profile({"ds_fish"})),
                           ("plant", ds_fish_loader.plant_profile({"new_flowers"}))):
            for order in (["Translations.dll", "Unicode Text.dll"], ["Unicode Text.dll", "Translations.dll"]):
                for start in (base, None):
                    names = ds_fish_loader.with_tails(game, start, order).dll_names
                    self.assertLess(names.index("Unicode Text.dll"), names.index("Translations.dll"), (game, order))


# ------------------------------------------------------------------ the patcher

SETTING = "unicode_ingame_fonts"


class PatcherTests(unittest.TestCase):
    """The setting in the manifests, and the executable it gets: the other settings' pinned bytes with
    "Unicode Text.dll" added last to the startup loader (src/ds_fish_loader.py, with_tails)."""

    def setUp(self) -> None:
        import tycoon_fix_patcher as combined
        self.combined = combined

    def test_the_setting(self) -> None:
        import hashlib
        for game in ("fish", "plant"):
            setting = self.combined.patch_settings(game)[SETTING]
            self.assertEqual(setting["name"], "Render Unicode with In-Game Fonts")
            self.assertIs(setting["default"], True)               # new content: on by default
            self.assertIs(setting["separate_output"], True)
            companion = setting["companion"]
            self.assertEqual(companion["loader_tail"], "Unicode Text.dll")
            self.assertNotIn("startup_loader", companion)
            folder = ROOT / companion["source"]
            paths = {f["path"] for f in companion["files"]}
            self.assertEqual(paths, {"Unicode Text.dll"} | {f"Images/{n}" for n in picture_names(game)})
            for entry in companion["files"]:
                data = (folder / entry["path"]).read_bytes()
                self.assertEqual((entry["size"], entry["sha256"]),
                                 (len(data), hashlib.sha256(data).hexdigest().upper()), entry["path"])
                if entry["path"].endswith(".dll"):
                    self.assertEqual(entry["destination"], f"{tm.GAME_TITLES[game]} Fix Patcher DLLs/Unicode Text.dll")
                else:
                    self.assertEqual(entry["destination"], entry["path"])
            # no pins carry the setting: it is left out of the pin key
            manifest = self.combined.load_manifest(game)
            self.assertFalse([k for k in manifest["patched_sha256_by_settings"] if SETTING in k.split(",")])

    def test_loader_tail_profiles(self) -> None:
        import ds_fish_loader
        alone = ds_fish_loader.with_tails("fish", None, ["Unicode Text.dll"])
        self.assertEqual(alone.dll_names, ("Unicode Text.dll",))
        base = ds_fish_loader.fish_profile({"ds_fish", "extra_tanks"})
        both = ds_fish_loader.with_tails("fish", base, ["Unicode Text.dll", "Unicode Text.dll"])
        self.assertEqual(both.dll_names, base.dll_names + ("Unicode Text.dll",))
        self.assertIs(ds_fish_loader.with_tails("fish", base, []), base)
        plant = ds_fish_loader.with_tails("plant", ds_fish_loader.plant_profile({"new_flowers"}), ["Unicode Text.dll"])
        self.assertEqual(plant.dll_names, ("Unused Flowers.dll", "Unicode Text.dll"))
        details = self.combined.setting_companion_details("fish", SETTING)
        self.assertTrue(any("Unicode Text.dll" in d.note for d in details))

    @unittest.skipUnless(EXES["fish"].is_file() and EXES["plant"].is_file(), "needs the vanilla games")
    def test_the_executable_is_the_pinned_one_with_the_dll_added_to_the_loader(self) -> None:
        import hashlib
        import ds_fish_loader
        import fish_patcher
        import plant_patcher
        for game, patcher in (("fish", fish_patcher), ("plant", plant_patcher)):
            manifest = self.combined.load_manifest(game)
            settings = self.combined.patch_settings(game)
            defaults = {sid for sid, s in settings.items() if s.get("default")}
            original = EXES[game].read_bytes()
            key = patcher.settings_key if game == "fish" else (lambda core, m=manifest: plant_patcher.settings_key(core, m))
            for others in (defaults - {SETTING}, {"fix_vanilla_bugs"}, set()):
                with self.subTest(game=game, others=sorted(others)):
                    enabled = others | {SETTING}
                    self.assertEqual(fish_patcher.pin_settings(manifest, enabled), others)
                    built, _p, loader, pin = fish_patcher.build_executable(
                        manifest, original, enabled, game, patcher.active_patch_records, patcher.apply_patch_bytes,
                        patcher.expected_patched_hash, key)
                    plain, _p2, _l2, pin2 = fish_patcher.build_executable(
                        manifest, original, others, game, patcher.active_patch_records, patcher.apply_patch_bytes,
                        patcher.expected_patched_hash, key)
                    self.assertEqual(pin, pin2)
                    if others:
                        self.assertEqual(hashlib.sha256(plain).hexdigest().upper(), pin)    # the pinned build
                    tail = f"{tm.GAME_TITLES[game]} Fix Patcher DLLs\\Unicode Text.dll".encode("utf-16-le")
                    self.assertIn(tail, built)
                    self.assertNotIn(tail, plain)
                    profile = fish_patcher.loader_profile(manifest, enabled, game)
                    self.assertEqual(profile.dll_names[-1], "Unicode Text.dll")
                    pre, _ = patcher.apply_patch_bytes(original, patcher.active_patch_records(manifest, others))
                    self.assertEqual(built, ds_fish_loader.append_startup_loader(pre, profile)[0])
                    self.assertTrue(loader)
            # a damaged pin for the other settings refuses the build with the tail too
            broken = dict(manifest, patched_sha256_by_settings=dict(manifest["patched_sha256_by_settings"]))
            broken["patched_sha256_by_settings"][key(defaults - {SETTING})] = "0" * 64
            with self.assertRaises(Exception):
                fish_patcher.build_executable(broken, original, defaults, game, patcher.active_patch_records,
                                              patcher.apply_patch_bytes, patcher.expected_patched_hash, key)


if __name__ == "__main__":
    unittest.main()
