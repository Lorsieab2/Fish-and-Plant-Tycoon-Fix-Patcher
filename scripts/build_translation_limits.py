"""data/translation_limits.json: how wide (in pixels) each translatable line may be where the game
or a patcher DLL draws it, worked out by running the games' own code in Unicorn.

    python scripts/build_translation_limits.py            # the census (needs the vanilla games,
                                                          # Unicorn and capstone) -> the JSON
    python scripts/build_translation_limits.py --header   # the JSON -> native/ftfp_translations/
                                                          # translation_limits.h (no game needed)

HOW A GAME LINE'S ROOM IS FOUND.  Every call of the game's string lookup with a fixed id (Fish
Tycoon 0x426FD0, Plant Tycoon 0x44CA70) is found in the executable, and the function that makes it
is run in Unicorn (tests/draw_emulator.py: the game's screens, widgets, sprites and printf on a new
game's state, an 800 x 600 screen), then whatever it built is shown as the game shows a screen.
Every text draw (Fish 0x4087E0, Plant 0x408E20) and every picture is recorded, TWICE: once with the
game's text width (pictures_screens.Composer.text_size, the games' own measure), once with every
text D pixels wider. A line that did not move is placed from its left edge, one that moved D / 2
is centred, one that moved D is placed from its right edge, one whose box moved with it sits in a
box the game sizes from the text (a message box). Its room is then, as the Unicode DLL's box_room
gives a name its room: the screen (left: from its left edge to the screen's right; centred: twice
the nearer screen edge's distance from its centre; right: from the screen's left to its right
edge); a button or panel behind it is no limit (the owner: text may run out of a box, never off the
screen). A text box widget (Fish 0x40C110, Plant 0x40CBE0) that is
built but not drawn gives its room from its own fields exactly as box_room reads them. A line handed to a message or question box
(Fish 0x4221A0; Plant 0x44D690, 0x42A700) or a tooltip (Plant 0x409870) has the widest text that
box can hold on the screen, found the same way (the box built and drawn by the game with ever
wider text until a piece of it leaves the screen).

Lines the game picks from its own tables are shown one by one with the game's own setter or table
(table_scenarios, hint_ids: Fish's tutorial pop-ups, hint line and Supplies items, Plant's store
items). Lines that no fixed-id call reaches (ids chosen by a register: species, goals, Help pages...)
and lines whose spot the run could not show get the SAFE rule: the English's widest line plus a
quarter (at least 16 pixels), never more than the screen. They are marked "proven": false.

The patcher DLLs' texts ("mod/..."): where the DLL draws them the room is its own layout's
(MOD_SPOTS and COUNT_LINES below, from the DLL sources); a Windows popup's text wraps itself (no
limit); the rest get the safe rule.

The JSON holds numbers only (no game text): per key base ("strings/<id>", "mod/<id>"), the font,
the pixel limit, whether the spot breaks lines ("multiline": the English has "\\n"), the kind of
spot and whether the limit was proven by a run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import translation_strings as ts  # noqa: E402
import translation_format as tfmt  # noqa: E402

DATA = ROOT / "data" / "translation_limits.json"
HEADER = ROOT / "native" / "ftfp_translations" / "translation_limits.h"
SCREEN_W, SCREEN_H = 800, 600
D = 64                                   # the extra width of the second run
VERSION = 1


def safe_limit(english_width: int) -> int:
    """The safe rule: the English's widest line plus a quarter (at least 16 pixels), never beyond the
    screen; 0 English (an empty line) gets the screen."""
    if english_width <= 0:
        return SCREEN_W
    return min(SCREEN_W, max(english_width + max(16, english_width // 4), english_width))


# ------------------------------------------------------------------ the games' code, statically

LOOKUPS = {"fish": (0x426FD0, 0x427050), "plant": (0x44CA70,)}
# Calls that take the line's id itself: (address, which argument)
ID_TAKERS = {"fish": {0x4221A0: (0, "message")},
             "plant": {0x44D690: (0, "message"), 0x42AB50: (0, "question"), 0x41F230: (0, "message")}}


def _code(game: str, exe: bytes):
    import capstone
    rva, _vs, raw, rs = ts._sections(exe)[0]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.skipdata = True
    return list(md.disasm(exe[raw:raw + rs], 0x400000 + rva))


def lookup_sites(game: str, exe: bytes) -> list[tuple[int, int]]:
    """(address of the call, id) of every call of the lookup (or an id taker) with a fixed id."""
    ins = _code(game, exe)
    out = []
    takers = ID_TAKERS[game]
    for k, i in enumerate(ins):
        if i.mnemonic != "call" or not i.op_str.startswith("0x"):
            continue
        target = int(i.op_str, 16)
        if target in LOOKUPS[game]:
            want = 0
        elif target in takers:
            want = takers[target][0]
        else:
            continue
        pushes = []
        for j in range(k - 1, max(0, k - 12), -1):
            if ins[j].mnemonic == "push":
                pushes.append(ins[j].op_str)
            elif ins[j].mnemonic in ("call", "ret"):
                break
            if len(pushes) > want:
                break
        if len(pushes) > want:
            try:
                out.append((i.address, int(pushes[want], 0)))
            except ValueError:
                pass
    return out


def dynamic_sites(game: str, exe: bytes) -> list[int]:
    """The addresses of the lookup calls whose id is not a fixed number (a register, a table...)."""
    fixed = {a for a, _i in lookup_sites(game, exe)}
    ins = _code(game, exe)
    return [i.address for i in ins if i.mnemonic == "call" and i.op_str.startswith("0x")
            and int(i.op_str, 16) in LOOKUPS[game] and i.address not in fixed]


def function_start(exe: bytes, va: int) -> int | None:
    """The start of the function holding `va`: the nearest 16-aligned address after int3 padding."""
    o = ts._offset(exe, va)
    p = o & ~0xF
    while p > o - 0x4000:
        if exe[p - 1] == 0xCC and exe[p] != 0xCC:
            break
        p -= 0x10
    else:
        return None
    # a function that follows another with no padding: a 16-aligned `ret` / `ret n`, then a constructor's
    # SEH prologue (push -1; push handler), nearer than the padded start
    start = p
    for q in range(o & ~0xF, p, -0x10):
        prev_ret = exe[q - 1] == 0xC3 or (exe[q - 3] == 0xC2 and exe[q - 1] == 0)
        if prev_ret and exe[q:q + 3] == bytes.fromhex("6aff68"):
            start = q
            break
    return va - (o - start)


# ------------------------------------------------------------------ the games' code, run

# Functions whose text argument is watched (entry only; the game's code still runs):
# address -> kind. "box": a text box widget (its own fields give its room when it is not drawn);
# "button": a Plant button's label; "message" / "question" / "tooltip": a box sized from the text.
WATCHED = {
    "fish": {0x40C110: "box", 0x4221A0: "message"},
    "plant": {0x40CBE0: "box", 0x401570: "button", 0x44D690: "message", 0x42AB50: "question", 0x409870: "tooltip"},
}
# The argument that holds the text (or the line's id, for the boxes that take it)
WATCHED_ARG = {"box": 3, "button": 0, "message": 0, "question": 0, "tooltip": 3}
BOX_IMPL = 0x10                          # the widget's box object (+8 left, +0x10 right, +0x24 fixed,
#                                          +0x40 alignment, +0x44 margin: native/common/unicode_text.h box_room)


def box_room(read32, read8, box: int) -> tuple[int, str]:
    """native/common/unicode_text.h box_room, the screen 800 wide."""
    s = lambda v: v - (1 << 32) if v & 0x80000000 else v  # noqa: E731
    left, right, margin = s(read32(box + 8)), s(read32(box + 0x10)), s(read32(box + 0x44))
    margin = max(0, margin)
    if read8(box + 0x24):
        return right - left - margin, "box"
    align = read32(box + 0x40)
    if align == 0:
        return SCREEN_W - left - margin, "left"
    if align == 1:
        centre = (left + right) // 2
        return 2 * min(centre, SCREEN_W - centre), "centre"
    if align == 2:
        return right - margin, "right"
    return 0, "?"


VANILLA = Path.home() / "Downloads" / "Current Modded LDW Games and Dumps" / "Vanilla Games"
FOLDERS = {"fish": VANILLA / "Fish Tycoon", "plant": VANILLA / "Plant Tycoon"}

_COMPOSERS: dict = {}


def composer(game: str):
    if game not in _COMPOSERS:
        import pictures_game_art as ga
        import pictures_screens as S
        _COMPOSERS[game] = S.Composer(ga.GameArt(game, FOLDERS[game]))
    return _COMPOSERS[game]


class Run:
    """One run of a function of the game: its text draws (bytes, x, y, font), its pictures
    (x, y, w, h) and the texts handed to the watched functions (kind, bytes, this)."""

    def __init__(self, game: str, extra: int = 0, extra_h: int = 0, only: bytes | None = None) -> None:
        import draw_emulator as de
        from unicorn import UC_HOOK_CODE
        self.game, self.extra, self.extra_h, self.only = game, extra, extra_h, only
        c = composer(game)

        def measure(font, data):
            w, h = c.text_size(font, data)
            if not data or (only is not None and data != only):
                return w, h
            return w + extra, h + extra_h
        if game == "plant":
            import pictures_plant_data as D
            self.sizes = de.picture_sizes("plant")
            self.d = de.DrawEmulator("plant", self.sizes, D.SPRITES)
            self.d.measure = measure
        else:
            self.sizes = de.picture_sizes("fish")
            self.d = de.FishScreens(self.sizes, measure)
        self.emu = self.d.emu
        if game == "fish":
            # 0x4190C0 asks the game's window manager (not built here) whether the screen may open: yes
            self.emu.hook(0x4190C0, lambda e: 1, 0)
        self.watched: list[tuple[str, bytes, int]] = []
        self.texts: list[tuple[bytes, int, int, int]] = []
        self.pictures: list[tuple[int, int, int, int]] = []
        for address, kind in WATCHED[game].items():
            self.emu.uc.hook_add(UC_HOOK_CODE, lambda uc, _a, _s, _d, k=kind: self._watch(k),
                                 begin=address, end=address)

    def _watch(self, kind: str) -> None:
        from unicorn import x86_const as X
        emu = self.emu
        this = emu.uc.reg_read(X.UC_X86_REG_ECX)
        p = emu.arg(WATCHED_ARG[kind])
        if kind in ("message", "question") and p < 0x200:
            text = self.d.strings.get(p)
            if text:
                self.watched.append((kind, text.encode("cp1252", "replace"), this))
            return
        if 0x10000 <= p < 0xF0000000:
            try:
                data = emu.cstring(p)
            except Exception:  # noqa: BLE001
                return
            if 0 < len(data) < 2000:
                self.watched.append((kind, data, this))

    def collect(self) -> None:
        d = self.d
        if self.game == "plant":
            for x in d.draws:
                if x.kind == "text":
                    if x.text:
                        self.texts.append((x.text, x.x, x.y, x.font))
                elif not x.file.startswith("<"):
                    w, h = self.sizes(x.file)
                    if w and h:
                        self.pictures.append((x.x, x.y, w // max(1, x.cols), h // max(1, x.rows)))
        else:
            for x in d.draws:
                if x[0] == "text":
                    self.texts.append((x[1], x[2], x[3], x[5]))
                elif x[0] == "pic":
                    left, top, right, bottom = x[2]
                    self.pictures.append((x[3], x[4], right - left, bottom - top))
                elif x[0] == "fill":
                    left, top, right, bottom = x[1]
                    self.pictures.append((left, top, right - left, bottom - top))
        d.draws.clear()

    def run(self, function: int, args: tuple = (0, 0, 0, 0, 0, 0), size: int = 0x2000, at: int = 0) -> int:
        """The function run on a zeroed object (thiscall); `at`: the object placed `at` pixels right
        and down (Plant Tycoon's dialogs keep their place at +0x14 / +0x18)."""
        this = self.d._zeroed(size)
        if at and self.game == "plant":
            for offset in PLACE[self.game]:
                self.emu.write32(this + offset, at)
        try:
            self.emu.call(function, *args, ecx=this)
        except Exception:  # noqa: BLE001  a run that stops part way still tells what it built
            pass
        self.collect()
        try:
            if self.game == "fish":
                self.emu.write8(self.emu.read32(this + 4), 1)
                for widget in self.d.children(this):
                    self.emu.call(self.emu.read32(self.emu.read32(widget) + 20), 1, ecx=widget)
                self.emu.call(0x40AC90, ecx=this)
            else:
                self.d.show(this)
        except Exception:  # noqa: BLE001
            pass
        self.collect()
        return this


# ------------------------------------------------------------------ rooms from the runs

def text_room(x: int, w: int, shift: int) -> tuple:
    """(room, kind) of a text drawn at x, w wide, that moved `shift` when every text grew by D: the room runs to
    the screen edge only (a button or panel behind it is no limit), by its alignment."""
    if shift == 0:
        kind = "left"
    elif shift == -D:
        kind = "right"
    elif abs(shift + D // 2) <= 1:
        kind = "centre"
    else:
        return 0, "grown"
    centre = x + w / 2
    room = {"left": SCREEN_W - x, "right": x + w, "centre": int(2 * min(centre, SCREEN_W - centre))}[kind]
    return room, kind


class Census:
    """Every spot found for each game line: id -> [(room, kind, font, where)]."""

    def __init__(self, game: str) -> None:
        self.game = game
        self.exe = FOLDERS[game].joinpath(ts.EXE_NAMES[game]).read_bytes()
        self.english = {s.id: s.english.encode("cp1252", "replace") for s in ts.read_table(game, self.exe)}
        self.spots: dict[int, list] = {}
        self.looked_up: set = set()
        self._formats = []
        for ident, data in self.english.items():
            if b"%" in data:
                pattern = re.escape(data)
                pattern = pattern.replace(b"%%", b"%")
                pattern = re.sub(rb"%[-0 +#]*\d*[diu]", rb"-?\\d+", pattern)
                pattern = re.sub(rb"%[-0 +#]*\d*s", rb"(?s:.*?)", pattern)
                try:
                    self._formats.append((ident, re.compile(pattern + rb"\Z", re.S)))
                except re.error:
                    pass

    def width(self, font: int, data: bytes) -> int:
        return composer(self.game).text_size(font, data)[0]

    def owners(self, data: bytes) -> list[tuple[int, bytes]]:
        """The game lines a drawn text is (or holds): (id, the English part)."""
        out = [(i, e) for i, e in self.english.items() if e == data and e.strip()]
        if out:
            return out
        out = [(i, data) for i, rx in self._formats if rx.match(data)]
        if out:
            return out
        for i, e in self.english.items():
            if len(e.strip()) >= 6 and e in data:
                out.append((i, e))
        return out

    def add(self, ident: int, room: int, kind: str, font: int, where: str) -> None:
        self.spots.setdefault(ident, []).append((room, kind, font, where))

    def run_function(self, function: int) -> None:
        a, b = Run(self.game), Run(self.game, D)
        a.run(function)
        b.run(function)
        moved = None
        if PLACE[self.game]:
            # a third run with the object placed elsewhere: words that move with it are placed on a
            # dialog whose place on the screen this run does not know
            c = Run(self.game)
            c.run(function, at=PLACE_SHIFT)
            moved = {(data, y) for data, x, y, _f in a.texts
                     if any(t[0] == data and t[1] == x + PLACE_SHIFT for t in c.texts)}
        self.collect(a, b, f"{function:#x}", moved)

    def collect(self, a: "Run", b: "Run", where: str, moved: set | None = None) -> None:
        texts_b = list(b.texts)
        drawn = set()
        for data, x, y, font in a.texts:
            match = next((t for t in texts_b if t[0] == data and t[2] == y), None)
            if match is None:
                continue
            texts_b.remove(match)
            w, h = composer(self.game).text_size(font, data)
            room, kind = text_room(x, w, match[1] - x)
            if kind == "grown":
                continue
            if moved and (data, y) in moved:
                continue                    # its room from the screen's edge is not known here
            for ident, part in self.owners(data):
                drawn.add(part)
                extra = w - self.width(font, part) if part != data else 0
                self.add(ident, room - extra, kind, font, where)
        # texts handed to a box, a button or a message: drawn already, or their own fields
        for kind, data, this in a.watched:
            if kind == "box" and data in drawn:
                continue
            owners = self.owners(data)
            if not owners:
                continue
            room, how = 0, kind
            try:
                if kind == "box":
                    impl = a.emu.read32(this + BOX_IMPL)
                    room, how = box_room(a.emu.read32, lambda p: a.emu.uc.mem_read(p, 1)[0], impl)
                    how = "text box, " + how
                elif kind == "button" and self.game == "plant":
                    # a button's label is centred on its button: twice the nearer screen edge's distance
                    # from the centre (the button's own width is no limit)
                    impl = a.emu.read32(this + 0x10)
                    file, cols, _rows = a.d.describe(a.emu.read32(impl + 0x3C))
                    frame = a.sizes(file)[0] // max(1, cols)
                    # the button's place is not in its fields: every picture of that frame's width on this screen
                    # is taken (the narrowest room wins); none drawn here: the frame's own width
                    rooms = [int(2 * min(px + pw / 2, SCREEN_W - px - pw / 2)) for px, _py, pw, _ph in a.pictures if pw == frame]
                    room, how = (min(rooms) if rooms else frame), "button label, centred"
                elif kind in BOX_MAX[self.game]:
                    room, how = BOX_MAX[self.game][kind][0], kind + " box"
            except Exception:  # noqa: BLE001
                room = 0
            if room > 0:
                for ident, _part in owners:
                    self.add(ident, room, how, 0, where)

    def run_scenario(self, name: str, scenario) -> None:
        a, b = Run(self.game), Run(self.game, D)
        for r in (a, b):
            try:
                scenario(r)
            except Exception:  # noqa: BLE001
                pass
            r.collect()
        self.collect(a, b, name)

    def run_all(self, verbose: bool = False) -> None:
        for name, scenario in SCENARIOS[self.game]:
            self.run_scenario(name, scenario)
            if verbose:
                print(f"  {self.game} {name}", file=sys.stderr)
        for ident in hint_ids(self.game, self.exe):
            self.run_scenario(f"hint {ident}", _plant_hint(ident) if self.game == "plant" else _fish_hint(ident))
        for name, scenario in table_scenarios(self.game, self.exe):
            self.run_scenario(name, scenario)
        sites = lookup_sites(self.game, self.exe)
        functions: dict[int, set] = {}
        for address, ident in sites:
            f = function_start(self.exe, address)
            if f is not None:
                functions.setdefault(f, set()).add(ident)
        for address in dynamic_sites(self.game, self.exe):      # ids chosen by a register: the draws still show
            f = function_start(self.exe, address)
            if f is not None:
                functions.setdefault(f, set())
        for n, f in enumerate(sorted(functions)):
            try:
                self.run_function(f)
            except Exception as exc:  # noqa: BLE001
                if verbose:
                    print(f"  {f:#x}: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            if verbose:
                print(f"  {self.game} {n + 1}/{len(functions)} {f:#x}", file=sys.stderr)
        self.looked_up = {ident for _a, ident in sites}


BOX_MAX: dict = {"fish": {}, "plant": {}}         # kind -> (width, height): filled by box_maxima()


# ------------------------------------------------------------------ the boxes sized from their text

def _s32(v: int) -> int:
    return v - (1 << 32) if v & 0x80000000 else v


def _box_run(game: str, kind: str, extra: int, extra_h: int, only: bytes | None = None) -> "Run":
    """A message, question or tooltip box built and drawn by the game, its text `extra` pixels wider
    and `extra_h` taller than the sample line."""
    r = Run(game, extra, extra_h, only)
    d = r.d
    if game == "plant" and kind == "message":
        box = d._zeroed(0x200)
        d.run(0x44D690, 0x6E, 0, 0, 0, this=box)
        d.vcall(d.emu.read32(box + 0x3C), 3, d.emu.read32(box + 0x14), d.emu.read32(box + 0x18), 0x3F800000)
        d.run(0x44DBB0, this=box)
        ok = d.emu.read32(box + 0x74)
        d.vcall(ok, 5, 1)
        d.vcall(ok, 6)
    elif game == "plant" and kind == "question":
        box = d._zeroed(0x200)
        d.run(0x42AB50, 0x77, 1, 1, 0, 0, this=box)
        d.show(box)
    elif game == "plant" and kind == "tooltip":
        rects = []
        d.emu.hook(0x407AF0, lambda e: rects.append(tuple(_s32(v) for v in struct.unpack(
            "<4I", e.uc.mem_read(e.arg(0), 16)))) or 0, 8)
        ticks = [0]
        d.emu.hook(0x402060, lambda e: ticks[0], 0)

        def point(e):
            e.write32(e.arg(0), 400)
            e.write32(e.arg(0) + 4, 300)
            return e.arg(0)
        d.emu.hook(0x407D20, point, 4)
        rect = d.emu.alloc(16)
        d.emu.uc.mem_write(rect, struct.pack("<4i", 380, 280, 420, 320))
        tip = d._zeroed(0x20)
        d.run(0x409870, 0x170, rect, 0, d.emu.text(TIP_SAMPLE.decode()), 0, 0, 0, this=tip)
        body = d.emu.read32(tip + 0xC)
        d.emu.write8(body + 0x39, 1)
        d.emu.write8(body + 0x3A, 1)
        d.emu.write32(body + 0x3C, 500)
        d.run(0x409B70, this=body)
        ticks[0] = 10 ** 6
        d.run(0x409B70, this=body)
        r.pictures += [(a, b, c - a, e - b) for a, b, c, e in rects]   # (left, top, right, bottom)
    elif game == "fish" and kind == "message":
        screen = d.make(0x4221A0, 0x1C, 1, size=0x200)
        d.show(screen)
    else:
        raise ValueError(kind)
    r.collect()
    return r


def on_screen(r: "Run") -> bool:
    c = composer(r.game)
    for x, y, w, h in r.pictures:
        if x < 0 or y < 0 or x + w > SCREEN_W or y + h > SCREEN_H:
            return False
    for data, x, y, font in r.texts:
        w, h = c.text_size(font, data)
        if r.only is None or data == r.only:
            w, h = w + r.extra, h + r.extra_h
        if x < 0 or y < 0 or x + w > SCREEN_W or y + h > SCREEN_H:
            return False
    return True


def _largest(fits, top: int = SCREEN_W) -> int:
    lo, hi = 0, top
    if not fits(lo):
        return -1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fits(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


TIP_SAMPLE = b"Tip"
BOX_KINDS = {"fish": ("message",), "plant": ("message", "question", "tooltip")}
BOX_SAMPLE = {("plant", "message"): 0x6E, ("plant", "question"): 0x77, ("plant", "tooltip"): None,
              ("fish", "message"): 0x1C}


def box_maxima(game: str) -> dict:
    """kind -> (the widest text, the tallest text) the game's box holds on the 800 x 600 screen."""
    out = {}
    c = composer(game)
    for kind in BOX_KINDS[game]:
        ident = BOX_SAMPLE[(game, kind)]
        sample = c._game()[2][ident] if ident is not None else TIP_SAMPLE
        w0, h0 = c.text_size(0, sample)
        extra_w = _largest(lambda e: on_screen(_box_run(game, kind, e, 0, sample)))
        extra_h = _largest(lambda e: on_screen(_box_run(game, kind, 0, e, sample)), SCREEN_H)
        out[kind] = (w0 + extra_w, h0 + extra_h)
    return out


# ------------------------------------------------------------------ screens shown with their own state

def _plant_help(page: int):
    def run(r: "Run") -> None:
        d = r.d
        screen = d._zeroed(0x800)
        d.run(0x420A00, this=screen)
        d.emu.write32(screen + 0x1C, page)
        d.run(0x420F00, this=screen)
        d.run(0x420F00, this=screen)
        r.collect()
        d.show(screen)
    return run


def _plant_tutorial(ident: int):
    """0x41F230(message): the tutorial's message box for it (a message box, watched)."""
    def run(r: "Run") -> None:
        d = r.d
        for address, pop in ((0x401C90, 8), (0x44DB70, 0), (0x44DAF0, 0), (0x41D830, 8)):
            d.emu.hook(address, lambda em: 0, pop)
        d.emu.call(0x41F230, ident, 0, ecx=d._zeroed(0x70000))
    return run


def _fish_screen(ctor: int, *args: int, size: int = 0x400, page: int | None = None):
    def run(r: "Run") -> None:
        f = r.d
        screen = f.make(ctor, *args, size=size)
        f.show(screen)
    return run


# Plant Tycoon's hint line (under the greenhouse): 0x41B190 sets the line's id and how long it shows,
# the line's draw 0x41B0A0 puts that text at the middle of the screen's foot.
HINT_SETTER, HINT_DRAW = 0x41B190, 0x41B0A0
# Fish Tycoon's hint line: 0x417FA0 (on the holder 0x417F20 makes) sets the line's number n and its end
# time; 0x417FD0 -> 0x417E90, the only reader of n, draws string 0x83 + n centred in its own fixed rectangle
# (0x408C30) while the clock (0x4020D0) is before the end.
FISH_HINT_SETTER, FISH_HINT_BASE, FISH_HINT_HOLDER = 0x417FA0, 0x83, 0x417FE0   # the holder's getter: no arguments


def hint_ids(game: str, exe: bytes) -> list[int]:
    """The ids the game hands to the hint line: each fixed number pushed for the setter (Fish: also
    both numbers of a `push a; jmp; push b` choice just before it), as string ids."""
    setter, base = (HINT_SETTER, 0) if game == "plant" else (FISH_HINT_SETTER, FISH_HINT_BASE)
    ins = _code(game, exe)
    out = set()
    for k, i in enumerate(ins):
        if i.mnemonic != "call" or i.op_str != hex(setter):
            continue
        for j in range(k - 1, max(0, k - 6), -1):
            p = ins[j]
            if p.mnemonic == "push":
                try:
                    out.add(base + int(p.op_str, 0))
                except ValueError:
                    break
                if game == "plant" or not (ins[j - 1].mnemonic == "jmp" and ins[j - 2].mnemonic == "push"):
                    break
            elif game == "plant" or not (p.mnemonic in ("mov", "jmp") or p.op_str == hex(FISH_HINT_HOLDER)):
                break
    return sorted(out)


def _fish_hint(ident: int):
    def run(r: "Run") -> None:
        f = r.d
        f.emu.hook(0x4020D0, lambda e: 1000, 0)          # the clock, still: the line shows
        holder = f._zeroed(0x10)
        f.emu.call(0x417F20, ecx=holder)
        f.emu.call(FISH_HINT_SETTER, ident - FISH_HINT_BASE, ecx=holder)
        f.emu.call(0x417FD0, ecx=holder)
    return run


# ------------------------------------------------------------------ lines the game picks from its tables
#
# Fish Tycoon's tutorial pop-up (0x41B100, the step): the step's row of the table at 0x454EF8 (step, id,
# arrow, x, y; 0x334 bytes) gives the id, put in a text box on a panel the constructor centres (0x401D90).
# Every step of the table is shown.
# Plant Tycoon's purchase dialog (0x432E90 -> 0x430950, the item): an item's name and description ids are
# in the store's item table on the game's state (+0x6F4 / +0x6F8 a row of 0xA0 bytes, set by the new game's
# 0x41DE80), each put in a text box at the dialog's centre; the dialog centres itself (0x40D160). Every item
# of the three tables (items 10-24, 27-35, 37-51) is shown. The seeds' dialog (items 0-8) is left out: the
# seeds' names are also drawn by other screens no run here shows. The store's own screen (0x446D40, its
# state at +0x1BC, its strings at +0x1C8) hands every item's name to a tooltip, shown too.
# Fish Tycoon's Supplies screen (0x427830; its part at +8, 0x427120): the item under the mouse (part +0) has its
# record in the table at 0x457EF0 (0x34 bytes each, ended by -1; +0x10 the item, +0x2C / +0x30 the name and
# description ids), drawn by 0x4271E0 at x 0x39 (0x408B80, from the left). Every record is shown.
FISH_TUTORIAL_TABLE, FISH_TUTORIAL_ROWS = 0x454EF8, 0x334 // 0x14
FISH_SUPPLY_RECORDS, FISH_SUPPLY_STRIDE = 0x457EF0, 0x34


def _fish_supply(item: int):
    def run(r: "Run") -> None:
        f = r.d
        screen = f.make(0x427830)
        part = f.emu.read32(screen + 8)
        f.emu.write32(part, item)
        f.emu.write32(part + 4, item)
        f.draws.clear()
        f.emu.call(0x4271E0, ecx=part)
    return run
PLANT_STORE_ITEMS = list(range(10, 25)) + list(range(27, 36)) + list(range(37, 52))


def _plant_store(item: int | None):
    def run(r: "Run") -> None:
        d = r.d
        d.run(0x41DE80, this=d.game_state)
        if item is None:
            screen = d._zeroed(0x2000)
            d.emu.write32(screen + 0x1BC, d.game_state)
            d.emu.write32(screen + 0x1C8, d.run(0x44D0B0))
            d.run(0x446D40, 1, 0, 0, 0, this=screen)
            return
        dialog = d._zeroed(0x400)
        d.run(0x432E90, item, this=dialog)
        r.collect()
        d.show(dialog)
    return run


def table_scenarios(game: str, exe: bytes) -> list:
    if game == "fish":
        steps = [struct.unpack_from("<I", exe, ts._offset(exe, FISH_TUTORIAL_TABLE) + 0x14 * k)[0]
                 for k in range(FISH_TUTORIAL_ROWS)]
        at, items = ts._offset(exe, FISH_SUPPLY_RECORDS), []
        while struct.unpack_from("<i", exe, at)[0] != -1:
            items.append(struct.unpack_from("<I", exe, at + 0x10)[0])
            at += FISH_SUPPLY_STRIDE
        return ([(f"tutorial step {s}", _fish_screen(0x41B100, s)) for s in steps]
                + [(f"supplies item {i}", _fish_supply(i)) for i in items])
    return ([(f"store item {i}", _plant_store(i)) for i in PLANT_STORE_ITEMS]
            + [("store tooltips", _plant_store(None))])


def _plant_hint(ident: int):
    def run(r: "Run") -> None:
        d = r.d
        hint = d._zeroed(0x40)
        d.emu.write32(hint, d._zeroed(0x100))
        d.emu.write32(hint + 0x14, ident)
        d.emu.write32(hint + 0x18, 3)
        d.emu.write32(hint + 0x1C, 0x7FFFFFFF)
        d.run(HINT_DRAW, this=hint)
    return run


PLACE = {"fish": (), "plant": (0x14, 0x18)}
PLACE_SHIFT = 100


def _plant_options(r: "Run") -> None:
    """The Options dialog as the main menu opens it, placed by the game (0x42AF10, 0x42B710)."""
    d = r.d
    dialog = d._zeroed(0x200)
    d.run(0x42AF10, d.emu.text(d.strings[0x192]), 1, this=dialog)
    d.vcall(d.emu.read32(dialog + 0x3C), 3, d.emu.read32(dialog + 0x14), d.emu.read32(dialog + 0x18), 0x3F800000)
    d.run(0x42B710, this=dialog)
    for widget, _id in d.widgets:
        d.vcall(widget, 5, 1)
        d.vcall(widget, 6)


SCENARIOS = {
    "plant": [("options", _plant_options)] + [(f"help page {k + 1}", _plant_help(k)) for k in range(6)]
    # the tutorial box's ids: 0xA0-0xC7, and the ids pushed for it as fixed numbers above (0xC9-0xCE)
    + [(f"tutorial {i:#x}", _plant_tutorial(i)) for i in list(range(0xA0, 0xC8)) + list(range(0xC9, 0xCF))],
    "fish": [("tank", _fish_screen(0x41EB00)), ("menu", _fish_screen(0x41C380)), ("trophy", _fish_screen(0x428340)),
             ("help", _fish_screen(0x41B810)), ("intro", _fish_screen(0x41BFD0)), ("supplies", _fish_screen(0x427830)),
             ("sell", _fish_screen(0x4244F0)), ("options", _fish_screen(0x422530))],
}


# Lines the game picks by a number at one call (a register id): they share the spot found for one.
# Fish 0x424690: the Sell screen's line, one of 0x45..0x73 (the counts with sprintf, the tips),
# handed to 0x427050 for the screen's text box.
# Plant 0x422E70: the greenhouse's tip, one of 0xD5..0xD5 + 0x31 (the rand(0x32) it adds to 0xD5), a text box.
SHARED = {"fish": {i: 0x45 for i in range(0x46, 0x74)}, "plant": {i: 251 for i in range(0xD5, 0xD5 + 0x32)}}


# ------------------------------------------------------------------ the data file

def english_variants(game: str, exe: bytes) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for e in ts.game_entries(game, ts.patched_variants(game, exe)):
        source, ident, _h = tfmt.split_key(e.key)
        out.setdefault(int(ident), []).append(e.english)
    return out


def _widest(c, font: int, english: str) -> int:
    text = tfmt.evaluate(english, longest=True) if "{" in english else english
    return max(c.text_size(font, line.encode("cp1252", "replace"))[0] for line in text.split("\n"))


def game_limits(game: str, verbose: bool = False) -> dict:
    """{"strings/<id>": {...}} for every line of the game's table."""
    BOX_MAX[game] = box_maxima(game)
    census = Census(game)
    census.run_all(verbose)
    c = composer(game)
    out = {}
    variants = english_variants(game, census.exe)
    for ident in sorted(variants):
        englishes = variants[ident]
        spots = census.spots.get(SHARED[game].get(ident, ident), [])
        multiline = any("\n" in e for e in englishes)
        fmt = any(tfmt.parse_template(e).conversions for e in englishes)
        if spots:
            room, kind, font, where = min(spots)
            english_w = max(_widest(c, font, e) for e in englishes)
            entry = {"font": font, "width": max(room, english_w), "multiline": multiline, "kind": kind,
                     "proven": True, "where": where}
            box = next((BOX_MAX[game][k.split()[0]] for _r, k, _f, _w in spots
                        if k.split()[0] in BOX_MAX[game]), None)
            if box is not None:
                entry["height"] = max([box[1]] + [c.text_size(font, e.encode("cp1252", "replace"))[1]
                                                  for e in englishes])
        elif ident in MESSAGE_IDS.get(game, ()) and "message" in BOX_MAX[game]:
            box = BOX_MAX[game]["message"]
            entry = {"font": 0, "width": box[0], "multiline": multiline, "kind": "message box", "proven": True,
                     "where": "0x4221A0", "height": box[1]}
        else:
            english_w = max(_widest(c, 0, e) for e in englishes)
            entry = {"font": 0, "width": safe_limit(english_w), "multiline": multiline, "kind": "safe rule",
                     "proven": False}
        entry["format"] = fmt
        out[f"strings/{ident}"] = entry
    return out


# Fish lines the game hands to its message box (0x4221A0) with the id chosen by a register, so the census cannot
# reach them: the store's "Buy this item?" and the "Replace ... in slot #n?" questions (seen cut in the live check).
MESSAGE_IDS = {"fish": {236, 237, 238, 239}}

# The Counts button ("Counts: On" / "Off", drawn by Tank Counts and Greenhouse Counts) moves left to end
# at x 796 when its translation is wide (native/common/count_toggle.h), so its room is the screen
# less the 4 pixels the DLL keeps for the shadow and the edge: 796 pixels (checked by
# tests/test_tank_greenhouse_counts.py, which runs the DLL's draw).
COUNTS_BUTTON_ROOM = 796
MOD_SPOTS = {
    "fish": ("tank_counts.counts_on", "tank_counts.counts_off"),
    "plant": ("greenhouse_counts.counts_on", "greenhouse_counts.counts_off"),
}


# The Counts DLLs' lines (native/ftfp_tank_counts, native/ftfp_greenhouse_counts: count_text.h builds them,
# draw_at puts them at LABEL_X with a 1-pixel shadow, the game's font 0): each line as its parts, a "mod/" id
# ("id=sample": a counted format, at its widest) or the text the DLL adds itself, the numbers at their widest
# (Fish: 30 slots a tank, 1 in the isolation tank; Plant: 15 pots). A part's room is the screen right of
# LABEL_X less the shadow and the rest of the line in English; its smallest over the lines that hold it.
COUNT_LINES = {
    "fish": (12, [
        ["fish", "30", "of", "30", " (", "n_adults=30 adults", ", ", "n_teens=30 teens", ", ", "n_babies=30 babies",
         ")", "  ", "dead", "30"],
        ["sick", "30", " ", "fungus", ", ", "30", " ", "ick", "  ", "low_health", "30"],
        ["creatures", "golden_seahorse", " x30", ", ", "magic_pufferfish", " x30", ", ", "blue_spotted_stingray",
         " x30", ", ", "moray_eel", " x30"],
        ["isolation_tank", "1", "of", "1", " (", "n_adults=1 adult", ")", "  ", "dead", "1", "  ", "sick", "1", " ",
         "fungus", ", ", "1", " ", "ick", "  ", "low_health", "1"],
    ]),
    "plant": (236, [
        ["plants", "15", "of", "15", " (", "n_mature=15 mature", ", ", "n_with_buds=15 with buds", ", ",
         "n_seedlings=15 seedlings", ")", "  ", "dead", "15"],
        ["infested", "15", "  ", "unhealthy", "15"],
    ]),
}
COUNT_SOURCE = {"fish": "tank_counts", "plant": "greenhouse_counts"}


def count_rooms(game: str) -> dict:
    """{"<source>.<id>": room} for the Counts DLL's line parts."""
    c = composer(game)
    english = {tfmt.split_key(e.key)[1]: e.english for e in ts.mod_entries(game)}
    x, lines = COUNT_LINES[game]
    out: dict = {}
    for line in lines:
        texts = []
        for part in line:
            name, _, sample = part.partition("=")
            key = f"{COUNT_SOURCE[game]}.{name}"
            texts.append((key if key in english else None, sample or english.get(key, part)))
        for k, (key, _t) in enumerate(texts):
            if key is None:
                continue
            rest = b"".join(t.encode("cp1252") for j, (_k, t) in enumerate(texts) if j != k)
            room = SCREEN_W - x - 1 - c.text_size(0, rest)[0]
            out[key] = min(out.get(key, room), room)
    return out


def mod_limits(game: str) -> dict:
    """{"mod/<id>": {...}}: a Windows popup's text wraps itself (no limit); the Counts button and the Counts
    lines' parts their DLL's layout (MOD_SPOTS, COUNT_LINES); the rest the safe rule."""
    c = composer(game)
    out = {}
    counts = count_rooms(game)
    for e in ts.mod_entries(game):
        _source, ident, _h = tfmt.split_key(e.key)
        if e.wide:
            out[f"mod/{ident}"] = {"font": 0, "width": None, "multiline": True, "kind": "windows popup",
                                   "proven": True, "format": e.is_format}
            continue
        w = _widest(c, 0, e.english)
        if ident in MOD_SPOTS[game]:
            out[f"mod/{ident}"] = {"font": 0, "width": max(COUNTS_BUTTON_ROOM, w), "multiline": False,
                                   "kind": "Counts button, moved left to the screen's edge", "proven": True,
                                   "where": "DLL source", "format": e.is_format}
            continue
        if ident in counts:
            out[f"mod/{ident}"] = {"font": 0, "width": max(counts[ident], w), "multiline": False,
                                   "kind": "Counts line part, left", "proven": True, "where": "DLL source",
                                   "format": e.is_format}
            continue
        out[f"mod/{ident}"] = {"font": 0, "width": safe_limit(w), "multiline": "\n" in e.english,
                               "kind": "safe rule", "proven": False, "format": e.is_format}
    return out


def build(verbose: bool = False) -> dict:
    data = {"version": VERSION, "screen": [SCREEN_W, SCREEN_H],
            "note": "Pixel widths each translated line may take where it is drawn: written by "
                    "scripts/build_translation_limits.py from runs of the games' own code; proven false: "
                    "the safe rule (the English's widest line plus a quarter, at least 16, at most the screen).",
            "games": {}}
    for game in ("fish", "plant"):
        limits = game_limits(game, verbose)
        limits.update(mod_limits(game))
        data["games"][game] = {"boxes": {k: list(v) for k, v in BOX_MAX[game].items()}, "lines": limits}
    return data


def dumps(data: dict) -> str:
    """One line per key, so a diff shows what changed."""
    lines = ["{", f'  "version": {data["version"]},', f'  "screen": {json.dumps(data["screen"])},',
             f'  "note": {json.dumps(data["note"])},', '  "games": {']
    games = list(data["games"].items())
    for g, (game, body) in enumerate(games):
        lines.append(f'    "{game}": {{')
        lines.append(f'      "boxes": {json.dumps(body["boxes"], sort_keys=True)},')
        lines.append('      "lines": {')
        items = list(body["lines"].items())
        for k, (key, entry) in enumerate(items):
            lines.append(f'        {json.dumps(key)}: {json.dumps(entry, sort_keys=True)}' + ("," if k + 1 < len(items) else ""))
        lines.append("      }")
        lines.append("    }" + ("," if g + 1 < len(games) else ""))
    lines += ["  }", "}", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ the C header

def render_header(data: dict) -> str:
    out = ["/* translation_limits.h -- written by scripts/build_translation_limits.py --header from",
           "   data/translation_limits.json; do not edit.  The pixel room of each line where it is drawn",
           "   (Translations.dll fits a wider translation: re-broken, cut with an ellipsis, or English). */",
           "#ifndef FTFP_TRANSLATION_LIMITS_H", "#define FTFP_TRANSLATION_LIMITS_H", "",
           "#define TL_MULTILINE 1    /* the English breaks lines: a translation may be re-broken */",
           "#define TL_PROVEN 2       /* the room was measured by running the game's code */",
           "#define TL_FORMAT 4       /* a printf format: never cut, only re-broken at spaces */",
           "",
           "typedef struct tl_line {",
           "    unsigned short id;            /* the game's string id */",
           "    unsigned short width;         /* pixels */",
           "    unsigned short height;        /* pixels; 0: not checked */",
           "    unsigned char font;           /* the game's font number */",
           "    unsigned char flags;",
           "} tl_line;", "",
           "typedef struct tl_mod {",
           "    unsigned char game;           /* 1 Fish, 2 Plant */",
           "    unsigned char flags;",
           "    unsigned short width;",
           "    const char *id;               /* the key's id, as TR_MOD_TEXTS[].id */",
           "} tl_mod;", ""]
    mods = []
    for game, gid in (("fish", 1), ("plant", 2)):
        rows = []
        for key, e in data["games"][game]["lines"].items():
            flags = (1 if e["multiline"] else 0) | (2 if e["proven"] else 0) | (4 if e.get("format") else 0)
            if key.startswith("strings/"):
                rows.append(f'    {{ 0x{int(key[8:]):03X}, {e["width"]}, {e.get("height", 0)}, {e["font"]}, {flags} }},')
            elif e["width"] is not None:
                mods.append(f'    {{ {gid}, {flags}, {e["width"]}, "{key[4:]}" }},')
        name = "TL_FISH" if game == "fish" else "TL_PLANT"
        out.append(f"static const tl_line {name}[] = {{")
        out += rows
        out += ["};", f"#define {name}_N {len(rows)}", ""]
    out.append("static const tl_mod TL_MODS[] = {")
    out += mods
    out += ["};", f"#define TL_MODS_N {len(mods)}", "", "#endif", ""]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--header", action="store_true", help="write the C header from the committed JSON")
    parser.add_argument("--check", action="store_true", help="exit 1 when the committed files differ")
    args = parser.parse_args()
    if args.header:
        data = json.loads(DATA.read_text(encoding="utf-8"))
        text = render_header(data)
        if args.check:
            ok = HEADER.is_file() and HEADER.read_text(encoding="utf-8") == text
            print("up to date" if ok else f"{HEADER} is out of date: run scripts/build_translation_limits.py --header")
            return 0 if ok else 1
        HEADER.write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {HEADER.relative_to(ROOT)}")
        return 0
    text = dumps(build(verbose=True))
    if args.check:
        ok = DATA.read_text(encoding="utf-8") == text
        print("up to date" if ok else f"{DATA} is out of date")
        return 0 if ok else 1
    DATA.write_text(text, encoding="utf-8", newline="\n")
    HEADER.write_text(render_header(json.loads(text)), encoding="utf-8", newline="\n")
    print(f"Wrote {DATA.relative_to(ROOT)} and {HEADER.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
