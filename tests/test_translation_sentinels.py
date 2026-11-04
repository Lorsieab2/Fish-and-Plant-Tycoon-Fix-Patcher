"""Every patch text reaches the game through its OWN translation key: a sentinel test.

tests/translation_sentinels.py translates every line of each game's translation (the game's own
lines, the lines an executable patch changes, every patcher DLL text and every counted text) to
a unique sentinel ("§K012§" with the line's placeholders and choices; the file validates). The
file is installed the way the game finds it (Translation.ini beside Translations.dll),
Translations.dll starts in Unicorn with every patcher DLL of the game mapped beside the real
executable, and each sentinel is followed to the place the game draws it or a DLL fills it in:

* the game's lines and the lines an executable patch changes ("strings/<id>", "Patch: ..."): the
  game's own string lookup -- the function every draw, sprintf and dialog of the game gets its
  text from -- returns the line's sentinel (Fish Tycoon in English and German mode), with the
  patched executable mapped for a patch's line;
* a DLL text (pointer texts): every relocated pointer of the DLL to its English now points at the
  sentinel, and the instruction that holds each pointer is run in Unicorn: it pushes or loads the
  sentinel's address (the argument the DLL hands to the game's draw call, sprintf, MessageBoxW or
  its own buffer), or it is a pointer table the DLL indexes;
* a counted text: FtfpTranslateCounted, given the DLL's own copy of the English (the exact text
  the DLL passes), fills the caller's buffer with the sentinel, its choices made by the number;
* real code paths, run in Unicorn: DS Exclusive Fish fills every DS species name from the
  translated parts, Unused Flowers builds every new species name from its two words, and the
  boxes a patch builds in a stock line's place (Optimize Prices, Sort Seeds, Extra Greenhouses)
  come out of the game's lookup as the patch's OWN text (Sort Seeds' Yes / No as the Yes / No
  lines): before Translations.dll looked at a line's +0xC override they showed the stock
  line's translation (OK, Cancel, the restart question, "box full") instead.
"""

from __future__ import annotations

import gc
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import translation_coverage as tc  # noqa: E402
import translation_format as tf  # noqa: E402
import translation_sentinels as S  # noqa: E402
import translation_strings as ts  # noqa: E402
import translations_emulator as te  # noqa: E402

try:
    import capstone
    from unicorn import UC_HOOK_CODE
    from unicorn import x86_const as X
    from test_translations_runtime import INI, PATH, _pointer_slots
    READY = te.ready()
except ImportError:              # CI: no Unicorn, Capstone or Keystone
    READY = False

SKIP = "needs Unicorn, Capstone, MSVC, the vanilla games and assets/translations/Translations.dll"
FIRST_BASE, STEP = 0x50000000, 0x01000000
STARTUP_BUDGET = 400_000_000          # instructions: the whole sentinel file is read and checked

# Keys no run in the emulator can follow to the game, with the reason. (None at present: every
# DLL text has a pointer the DLL hands on, every counted text is asked for by its DLL's copy.)
UNREACHABLE: dict[str, str] = {}



# ---------------------------------------------------------------------------------- the runtime

def _fast(emu) -> None:
    """Python sees only the imports' thunks and the hooked addresses, not every instruction."""
    import store_emulator as se
    emu.uc.hook_del(emu.code_hook)
    emu.code_hook = emu.uc.hook_add(UC_HOOK_CODE, emu._on_code, begin=se.THUNKS, end=se.THUNKS + se.THUNK_SIZE - 1)
    emu.fast_hooks = set()
    for address in list(emu.hooks):
        _watch(emu, address)


def _watch(emu, address: int) -> None:
    import store_emulator as se
    if se.THUNKS <= address < se.THUNKS + se.THUNK_SIZE or address in emu.fast_hooks:
        return
    emu.uc.hook_add(UC_HOOK_CODE, emu._on_code, begin=address, end=address)
    emu.fast_hooks.add(address)


def hook(emu, address: int, handler, pop: int = 0) -> None:
    emu.hook(address, handler, pop)
    _watch(emu, address)


def dlls_of(game: str) -> list[str]:
    return sorted({m.dll for m in ts.MOD_STRINGS if m.game == game})


def dll_bytes(game: str, dll: str) -> bytes:
    return (ROOT / "assets" / tc.DLLS[(game, dll)][0] / dll).read_bytes()


def mapping(game: str, only: list[str] | None = None) -> dict[str, tuple[bytes, int]]:
    return {dll: (dll_bytes(game, dll), FIRST_BASE + k * STEP) for k, dll in enumerate(dlls_of(game))
            if only is None or dll in only}


def runtime(game: str, only: list[str] | None = None, exe: bytes | None = None,
            before=None) -> tuple["te.Runtime", dict[str, tuple[bytes, int]]]:
    """Translations.dll with the sentinel file, the game's patcher DLLs mapped (or `only` these),
    the executable's sections replaced by `exe` (a patched game), started."""
    mapped = mapping(game, only)
    rt = te.Runtime(game, {INI[game]: te.ini(PATH), PATH: S.file_bytes(game)}, dlls=mapped)
    if exe is not None:
        _base, _size, sections, _imports = te.se.pe_image(exe)
        for rva, raw, raw_size in sections:
            rt.emu.uc.mem_write(0x400000 + rva, exe[raw:raw + raw_size])
    if game == "plant":
        rt.hook_plant_table()
    _fast(rt.emu)
    if before is not None:
        before(rt, mapped)
    result = rt.emu.call(rt.emu.sym("_FtfpStartup@0"), count=STARTUP_BUDGET)
    assert result == 1, rt.log
    assert f"{len(S.lines(game))} lines used" in rt.log, rt.log
    return rt, mapped


_STARTED: dict[str, tuple] = {}


def started(game: str):
    if game not in _STARTED:
        _STARTED[game] = runtime(game)
    return _STARTED[game]


def read_text(emu, address: int, wide: bool) -> str:
    return emu.wstring(address) if wide else emu.cstring(address).decode("cp1252")


def in_game(line: S.Line, wide: bool = False) -> str:
    """What Translations.dll hands the game for a line (Windows-1252 text, or UTF-16)."""
    text = line.translation
    if line.entry.is_format:
        text = tf.escape_percents(text, line.entry.english)
    return text


# ---------------------------------------------------------------------------------- symbols

_SYMBOLS: dict[str, dict[str, int]] = {}


def symbols(project: str, committed: Path) -> dict[str, int]:
    """A patcher DLL's map (rebuilt from its source; the rebuild must equal the committed DLL)."""
    if project not in _SYMBOLS:
        out = Path(tempfile.mkdtemp(prefix="ftfp_sentinel_"))
        _dll, _SYMBOLS[project] = te.se.build_with_map(project, committed, out)
    return _SYMBOLS[project]


def at(symbols_: dict[str, int], name: str, base: int) -> int:
    """A symbol of a DLL built for 0x10000000, relocated to `base`."""
    return symbols_[name] - 0x10000000 + base


def resolve_imports(rt, data: bytes, base: int) -> dict[str, int]:
    """Give a mapped patcher DLL's imports thunks (what Windows' loader does); name -> thunk."""
    emu = rt.emu
    _b, _s, _sections, imports = te.se.pe_image(data)
    names: dict[str, int] = {}
    at_ = imports
    while True:
        lookup, _t, _f, _name, iat = struct.unpack("<5I", emu.uc.mem_read(base + at_, 20))
        if lookup == 0 and iat == 0:
            return names
        slot = 0
        while True:
            entry = struct.unpack("<I", emu.uc.mem_read(base + (lookup or iat) + slot * 4, 4))[0]
            if entry == 0:
                break
            name = emu.cstring(base + entry + 2).decode("ascii") if not entry & 0x80000000 else f"#{entry & 0xFFFF}"
            thunk = emu.thunk()
            emu.write32(base + iat + slot * 4, thunk)
            names[name] = thunk
            slot += 1
        at_ += 20


# ---------------------------------------------------------------------------------- the file

@unittest.skipUnless(READY, SKIP)
class TheFile(unittest.TestCase):
    def test_every_line_has_a_valid_unique_sentinel(self) -> None:
        for game in ("fish", "plant"):
            with self.subTest(game=game):
                report = S.validate(game)
                self.assertEqual([str(p) for p in report.errors], [])
                self.assertEqual(report.translated, report.total)
                tags = [line.tag for line in S.lines(game)]
                self.assertEqual(len(tags), len(set(tags)))
                for line in S.lines(game):
                    self.assertTrue(line.translation.strip(" \n").startswith(line.tag), line.key)
                    self.assertNotIn(line.entry.english.strip(), line.translation if len(line.entry.english.strip())
                                     > 2 else "", line.key)

    def test_every_patch_key_is_listed(self) -> None:
        """Every patcher DLL text and every executable patch's line is in the file."""
        for game in ("fish", "plant"):
            keys = {line.key for line in S.lines(game)}
            for m in ts.MOD_STRINGS:
                if m.game == game:
                    self.assertIn(ts.mod_key(m), keys)
            patched = [line for line in S.lines(game) if ts.PATCH_NOTE in line.entry.notes]
            if game == "fish":
                self.assertTrue(patched)


# ---------------------------------------------------------------------------------- game lines

def _patch_lines(game: str) -> dict[str, list[S.Line]]:
    out: dict[str, list[S.Line]] = {}
    for line in S.lines(game):
        if S.game_id(line.key) is not None:
            label = ts.group_of(line.entry.notes)
            if label:
                out.setdefault(label, []).append(line)
    return out


def _patched_exe(game: str, label: str) -> bytes:
    import json
    manifest = json.loads((ROOT / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
    setting = next(s for s in manifest["settings"] if s.get("name", s["id"]) == label)
    if game == "fish":
        import fish_patcher as patcher
    else:
        import plant_patcher as patcher  # type: ignore[no-redef]
    exe = (te.EXES[game]).read_bytes()
    records = patcher.active_patch_records(manifest, {setting["id"]})
    patched, _ = patcher.apply_patch_bytes(exe, records)
    return patched


@unittest.skipUnless(READY, SKIP)
class GameLines(unittest.TestCase):
    def test_every_game_line_comes_out_of_the_games_lookup(self) -> None:
        for game in ("fish", "plant"):
            rt, _m = started(game)
            for line in S.lines(game):
                ident = S.game_id(line.key)
                if ident is None or ts.group_of(line.entry.notes):
                    continue
                with self.subTest(game=game, key=line.key):
                    want = in_game(line).encode("cp1252")
                    self.assertEqual(rt.lookup(ident), want)
                    if game == "fish":
                        self.assertEqual(rt.lookup(ident, german=True), want)

    def test_every_executable_patch_line_comes_out_of_the_patched_games_lookup(self) -> None:
        for game in ("fish", "plant"):
            for label, patch_lines in _patch_lines(game).items():
                with self.subTest(game=game, patch=label):
                    exe = _patched_exe(game, label)
                    rt, _m = runtime(game, only=[], exe=exe)
                    for line in patch_lines:
                        ident = S.game_id(line.key)
                        table = {s.id: s.english for s in ts.read_table(game, exe)}
                        self.assertEqual(table[ident], line.entry.english)      # what the patch writes
                        want = in_game(line).encode("cp1252")
                        self.assertEqual(rt.lookup(ident), want, line.key)
                        if game == "fish":
                            self.assertEqual(rt.lookup(ident, german=True), want, line.key)
                    del rt, _m
                    gc.collect()               # each emulator maps tens of MB: free it before the next


# ---------------------------------------------------------------------------------- DLL texts

def _sections(data: bytes) -> list[tuple[int, int, int]]:
    """(rva, size, characteristics) of each section."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    out = []
    for i in range(count):
        o = pe + 24 + optional + i * 40
        vsize, rva, raw_size = struct.unpack_from("<III", data, o + 8)
        flags = struct.unpack_from("<I", data, o + 36)[0]
        out.append((rva, max(vsize, raw_size), flags))
    return out


def _is_code(data: bytes, rva: int) -> bool:
    return any(r <= rva < r + size and flags & 0x20000000 for r, size, flags in _sections(data))


_CS = None


def _instruction(rt, slot: int):
    """The instruction whose immediate or displacement is the 4 bytes at `slot`."""
    global _CS
    if _CS is None:
        _CS = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        _CS.detail = True
    found = []
    for back in range(1, 12):
        start = slot - back
        code = bytes(rt.emu.uc.mem_read(start, 16))
        for insn in _CS.disasm(code, start, count=1):
            if insn.size < back + 4:
                continue
            if (insn.imm_offset and start + insn.imm_offset == slot) or \
                    (insn.disp_offset and start + insn.disp_offset == slot):
                found.append(insn)
    # a slot's bytes also decode as the tail of other instructions: take the one that holds the
    # pointer itself as a push or a mov (what a text's address is handed on by)
    value = struct.unpack("<I", bytes(rt.emu.uc.mem_read(slot, 4)))[0]
    own = [i for i in found if i.mnemonic in ("push", "mov") and
           value in (i.operands[-1].imm & 0xFFFFFFFF if i.operands[-1].type == capstone.x86.X86_OP_IMM else -1,
                     i.operands[-1].mem.disp & 0xFFFFFFFF if i.operands[-1].type == capstone.x86.X86_OP_MEM else -1)]
    pool = own or found
    return max(pool, key=lambda i: i.size) if pool else None


def hand_over(rt, slot: int) -> tuple[str, int | None]:
    """Run the one instruction that holds the pointer at `slot`; (mnemonic, the pointer it pushed
    or loaded, or None)."""
    emu = rt.emu
    insn = _instruction(rt, slot)
    if insn is None:
        return "?", None
    import store_emulator as se
    scratch = emu.alloc(0x2000)
    emu.uc.mem_write(scratch, b"\0" * 0x2000)
    esp = se.STACK + se.STACK_SIZE - 0x2000
    regs = (X.UC_X86_REG_EAX, X.UC_X86_REG_EBX, X.UC_X86_REG_ECX, X.UC_X86_REG_EDX, X.UC_X86_REG_ESI,
            X.UC_X86_REG_EDI, X.UC_X86_REG_EBP)
    for r in regs:
        emu.uc.reg_write(r, scratch + 0x1000)
    emu.uc.reg_write(X.UC_X86_REG_ESP, esp)
    emu.uc.mem_write(esp - 0x100, b"\0" * 0x200)
    pointer = emu.read32(slot)
    for op in insn.operands:
        # "mov cl, [eax + text]": the DLL reads the text's letters in place, one by one
        if insn.mnemonic == "mov" and op.type == capstone.x86.X86_OP_MEM and                 op.mem.disp & 0xFFFFFFFF == pointer and (op.mem.base or op.mem.index):
            return insn.mnemonic, pointer
    try:
        emu.uc.emu_start(insn.address, insn.address + insn.size, count=1)
    except Exception:                                   # noqa: BLE001 (a load of memory not mapped)
        return insn.mnemonic, None
    seen = [emu.uc.reg_read(r) for r in regs] + [emu.read32(emu.uc.reg_read(X.UC_X86_REG_ESP))]
    block = bytes(emu.uc.mem_read(scratch, 0x2000))
    seen += [struct.unpack_from("<I", block, k)[0] for k in range(0, 0x2000, 4)]
    for op in insn.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
            try:
                seen.append(emu.read32(op.mem.disp & 0xFFFFFFFF))
            except Exception:                           # noqa: BLE001
                pass
    return insn.mnemonic, pointer if pointer in seen else None


@unittest.skipUnless(READY, SKIP)
class DllTexts(unittest.TestCase):
    """Every pointer text of every patcher DLL: what each of the DLL's pointers to it now shows,
    and what the instruction holding the pointer hands on."""

    def test_every_dll_text_reaches_its_pointers(self) -> None:
        for game in ("fish", "plant"):
            rt, mapped = started(game)
            lines = {line.key: line for line in S.lines(game)}
            for key, m in S.mod_of(game).items():
                if m.counted:
                    continue
                with self.subTest(game=game, dll=m.dll, english=m.english, wide=m.wide):
                    data, base = mapped[m.dll]
                    slots = _pointer_slots(te.relocate(data, base), base, S.encoded(m.english, m.wide))
                    if not slots:
                        self.assertIn(key, UNREACHABLE, f"{m.dll} has no pointer to {m.english!r}")
                        continue
                    want = in_game(lines[key], m.wide)
                    for slot in slots:
                        self.assertEqual(read_text(rt.emu, rt.emu.read32(slot), m.wide), want, hex(slot))

    def test_every_pointer_is_handed_on(self) -> None:
        """Each pointer in code is the operand of an instruction that pushes or loads it; run, it
        gives the sentinel's address. A pointer in data is an entry of a table of texts."""
        for game in ("fish", "plant"):
            rt, mapped = started(game)
            for key, m in S.mod_of(game).items():
                if m.counted:
                    continue
                data, base = mapped[m.dll]
                for slot in _pointer_slots(te.relocate(data, base), base, S.encoded(m.english, m.wide)):
                    with self.subTest(game=game, dll=m.dll, english=m.english, slot=hex(slot)):
                        if not _is_code(data, slot - base):
                            continue                         # a table of texts (DS fish names...)
                        mnemonic, pointer = hand_over(rt, slot)
                        self.assertIn(mnemonic, ("push", "mov"), f"{m.english!r} at {slot:#x}: {mnemonic}")
                        self.assertIsNotNone(pointer, f"{mnemonic} at {slot:#x} does not hand on the pointer")
                        self.assertEqual(read_text(rt.emu, pointer, m.wide),
                                         in_game(next(x for x in S.lines(game) if x.key == key), m.wide))

    def test_no_dll_holds_a_second_copy_no_pointer_reaches(self) -> None:
        """(c) A DLL's English with no pointer to it would be a copy the translation never
        changes; every copy of every key's English in its DLL, as a whole string, is pointed at."""
        for game in ("fish", "plant"):
            _rt, mapped = started(game)
            for key, m in S.mod_of(game).items():
                if m.counted:
                    continue
                data, base = mapped[m.dll]
                image = te.relocate(data, base)
                targets = {_value_at(image, base, slot)
                           for slot in _pointer_slots(image, base, S.encoded(m.english, m.wide))}
                for offset in S.string_starts(image, S.encoded(m.english, m.wide), m.wide):
                    va = base + _rva_of(image, offset)
                    with self.subTest(game=game, dll=m.dll, english=m.english, at=hex(va)):
                        if va in targets:
                            continue
                        self.fail(f"{m.dll} holds {m.english!r} at {va:#x} with no pointer to it")


def _rva_of(image: bytes, offset: int) -> int:
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    count = struct.unpack_from("<H", image, pe + 6)[0]
    optional = struct.unpack_from("<H", image, pe + 20)[0]
    for i in range(count):
        o = pe + 24 + optional + i * 40
        _vsize, rva, raw_size, raw = struct.unpack_from("<IIII", image, o + 8)
        if raw <= offset < raw + raw_size:
            return rva + offset - raw
    return offset


def _value_at(image: bytes, base: int, va: int) -> int:
    rva = va - base
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    count = struct.unpack_from("<H", image, pe + 6)[0]
    optional = struct.unpack_from("<H", image, pe + 20)[0]
    for i in range(count):
        o = pe + 24 + optional + i * 40
        _vsize, s_rva, raw_size, raw = struct.unpack_from("<IIII", image, o + 8)
        if s_rva <= rva < s_rva + raw_size:
            return struct.unpack_from("<I", image, raw + rva - s_rva)[0]
    raise ValueError(hex(va))


# ---------------------------------------------------------------------------------- counted texts

@unittest.skipUnless(READY, SKIP)
class CountedTexts(unittest.TestCase):
    def test_every_counted_text_from_its_dlls_own_copy(self) -> None:
        for game in ("fish", "plant"):
            rt, mapped = started(game)
            e = rt.emu
            lines = {line.key: line for line in S.lines(game)}
            for key, m in S.mod_of(game).items():
                if not m.counted:
                    continue
                with self.subTest(game=game, dll=m.dll, english=m.english):
                    data, base = mapped[m.dll]
                    image = te.relocate(data, base)
                    copies = S.string_starts(image, S.encoded(m.english, m.wide), m.wide)
                    if not copies:
                        self.assertIn(key, UNREACHABLE, f"{m.dll} does not hold {m.english!r}")
                        continue
                    count = len(tf.parse_template(m.english).conversions)
                    for numbers in ([1] * count, [2, 500, 3][:count]):
                        for offset in copies:
                            english_at = base + _rva_of(image, offset)
                            values = e.alloc(16)
                            for k, n in enumerate(numbers):
                                e.write32(values + 4 * k, n)
                            out = e.alloc(4096)
                            got = e.call(e.sym("_FtfpTranslateCounted@24"), english_at, int(m.wide), values, count,
                                         out, 1000)
                            self.assertLess(got, 0x80000000, f"-1: {m.english!r} not translated")
                            want = lines[key].shown(numbers)
                            self.assertEqual(read_text(e, out, m.wide), want)
                            self.assertIn(lines[key].tag, want)


# ---------------------------------------------------------------------------------- real paths

def _line_for(game: str, dll: str, english: str, wide: bool = False) -> S.Line:
    m = next(x for x in ts.MOD_STRINGS if (x.game, x.dll, x.english, x.wide) == (game, dll, english, wide))
    key = ts.mod_key(m)
    return next(line for line in S.lines(game) if line.key == key)


def _game_line(game: str, ident: int) -> S.Line:
    return next(line for line in S.lines(game) if S.game_id(line.key) == ident and not ts.group_of(line.entry.notes))


@unittest.skipUnless(READY, SKIP)
class DsFishNames(unittest.TestCase):
    """DS Exclusive Fish fills each DS species' 32-letter name from its fin and body words."""

    def test_every_ds_species_name_is_filled_with_the_translated_words(self) -> None:
        dll = "DS Exclusive Fish.dll"
        rt, mapped = started("fish")
        data, base = mapped[dll]
        syms = symbols("ftfp_ds_fish", ROOT / "assets" / tc.DLLS[("fish", dll)][0] / dll)
        set_name = at(syms, "_set_name", base)
        fins = [_line_for("fish", dll, m.english) for m in ts.MOD_STRINGS
                if m.dll == dll and m.limit == 15]
        bodies = [_line_for("fish", dll, m.english) for m in ts.MOD_STRINGS
                  if m.dll == dll and m.limit == 16]
        self.assertEqual((len(fins), len(bodies)), (28, 28))
        e = rt.emu
        seen_fin, seen_body = set(), set()
        names = set()
        for gene in range(0, 80):
            for other in (gene,):
                entry = e.alloc(0x40)
                e.uc.mem_write(entry, b"\xAA" * 0x40)
                try:
                    e.call(set_name, entry, gene, other)
                except Exception:                               # noqa: BLE001 (not a DS gene)
                    continue
                name = e.cstring(entry).decode("cp1252")
                names.add(name)
        for fin in fins:
            for name in names:
                if name.startswith(fin.translation):
                    seen_fin.add(fin.key)
                    rest = name[len(fin.translation):]
                    for body in bodies:
                        if rest == body.translation:
                            seen_body.add(body.key)
        self.assertEqual(len(seen_fin), 28, sorted(names)[:5])
        self.assertEqual(len(seen_body), 28, sorted(names)[:5])
        for name in names:
            self.assertNotRegex(name, r"[A-Za-z]{3}", name)          # no English word left in a name


@unittest.skipUnless(READY, SKIP)
class UnusedFlowerNames(unittest.TestCase):
    """Unused Flowers builds every new species' name "<flower> <foliage>" from its two translated words."""

    def test_every_new_species_name_is_its_two_sentinels(self) -> None:
        dll = "Unused Flowers.dll"
        rt, mapped = started("plant")
        data, base = mapped[dll]
        syms = symbols("ftfp_new_flowers", ROOT / "assets" / tc.DLLS[("plant", dll)][0] / dll)
        e = rt.emu
        e.call(at(syms, "_FtfpTranslationApplied@0", base))
        adjectives = [m for m in ts.MOD_STRINGS if m.dll == dll and "first word" in m.note]
        nouns = [m for m in ts.MOD_STRINGS if m.dll == dll and "second word" in m.note]
        self.assertEqual((len(adjectives), len(nouns)), (14, 23))
        seen = set()
        for foliage, noun in enumerate(nouns, start=1):
            for k, adjective in enumerate(adjectives):
                name = e.cstring(e.call(at(syms, "_species_name", base), foliage, 24 + k)).decode("cp1252")
                want = (_line_for("plant", dll, adjective.english).translation + " " +
                        _line_for("plant", dll, noun.english).translation)
                self.assertEqual(name, want)
                seen.add((adjective.english, noun.english))
        self.assertEqual(len(seen), 14 * 23)


# ---------------------------------------------------------------------------------- boxes

def _put(emu, text: bytes) -> int:
    at = emu.alloc(len(text) + 8)
    emu.uc.mem_write(at, text + b"\0")
    return at


@unittest.skipUnless(READY, SKIP)
class BoxTexts(unittest.TestCase):
    """A patcher DLL's box: it puts its own text in a stock line's place for the game's box builder
    (Fish: the line's English at +4; Plant: an override at +0xC). The game's lookup must give the
    patch's OWN key's translation there, not the stock line's, and a stock line's own text put in
    another line's place (Sort Seeds' Yes / No in OK / Cancel) must get that line's translation."""

    def test_fish_optimize_prices_questions_in_the_games_box(self) -> None:
        rt, _m = started("fish")
        e = rt.emu
        entry = 0x00457340 + 0xAC * 12
        self.assertEqual(e.read32(entry), 0xAC)
        saved = e.read32(entry + 4)
        try:
            for m in ts.MOD_STRINGS:
                if (m.game, m.dll) != ("fish", "Optimize Prices.dll") or m.counted:
                    continue
                with self.subTest(english=m.english):
                    e.write32(entry + 4, _put(e, S.encoded(m.english, False)[:-1]))
                    want = in_game(_line_for("fish", m.dll, m.english)).encode("cp1252")
                    self.assertEqual(rt.lookup(0xAC), want)
        finally:
            e.write32(entry + 4, saved)

    def _override(self, rt, ident: int, text: bytes) -> bytes:
        e = rt.emu
        entry = e.read32(0x493CC0 + 4 * ident)
        self.assertEqual(e.read32(entry), ident)
        try:
            e.write32(entry + 0xC, _put(e, text))
            return rt.lookup(ident)
        finally:
            e.write32(entry + 0xC, 0)

    def test_plant_sort_seeds_question_is_its_own_text(self) -> None:
        rt, _m = started("plant")
        m = next(x for x in ts.MOD_STRINGS if (x.game, x.dll) == ("plant", "Sort Seeds.dll"))
        want = in_game(_line_for("plant", m.dll, m.english)).encode("cp1252")
        self.assertEqual(self._override(rt, 0x3E, S.encoded(m.english, False)[:-1]), want)
        # the stock line's own translation still shows with no override
        self.assertEqual(rt.lookup(0x3E), in_game(_game_line("plant", 0x3E)).encode("cp1252"))

    def test_plant_sort_seeds_yes_and_no_take_their_own_translation(self) -> None:
        rt, _m = started("plant")
        for yes_no, in_place_of in ((0x10, 0x12), (0x11, 0x13)):
            english = _game_line("plant", yes_no).entry.english.encode("cp1252")
            self.assertEqual(self._override(rt, in_place_of, english),
                             in_game(_game_line("plant", yes_no)).encode("cp1252"), hex(in_place_of))

    def test_plant_extra_greenhouses_box_keeps_the_translated_text_it_was_given(self) -> None:
        """The DLL builds the text translated (counted path) and puts it at +0xC of "box full"."""
        rt, _m = started("plant")
        counted = _line_for("plant", "Extra Greenhouses.dll",
                            "Your nursery is full!\n\nOnly %d plants can be for sale at once,\ncounting every greenhouse.")
        text = counted.shown([15]).encode("cp1252")
        self.assertEqual(self._override(rt, 0x77, text), text)
        self.assertNotEqual(text, in_game(_game_line("plant", 0x77)).encode("cp1252"))


if __name__ == "__main__":
    unittest.main()
