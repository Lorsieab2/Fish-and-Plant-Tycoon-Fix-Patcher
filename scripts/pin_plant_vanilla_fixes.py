"""Pin Plant Tycoon's "Fix Vanilla Bugs" setting into the plant manifest.

    python scripts/pin_plant_vanilla_fixes.py "<vanilla Plant Tycoon folder>"

Stock bugs fixed by byte changes, each listed in records():

  * A new game can start at the Flower of Knowledge (Nox Orchid) prices. The
    new game 0x41EF30 calls the price setup 0x41DBD0 at 0x41EFB8, but clears
    the seven magic plant flags (state + 0x2180..0x2186: a dword, a word and
    a byte at 0x41F170..0x41F182) only later. The price setup gives every
    species V + 3 x (V/4) when the Flower of Knowledge flag (+0x2181) is set,
    so it reads the flag of the save loaded before the new game (the game
    loads the last save when it starts, 0x41FA10). The call at 0x41EFB8 now
    goes to a few bytes in the zero tail of .text (VA 0x464950, after the R
    key's code at 0x464930) that clear exactly those seven bytes, then jump
    to 0x41DBD0. Nothing between 0x41EFB8 and 0x41F170 reads the flags, and
    0x41F170 still clears them, so the only change is that the prices come
    from a clean state. Finding the Flower of Knowledge (0x41EB3F, then
    0x41DBD0 from 0x41EB46) is untouched. Unused Flowers.dll hooks 0x41DBD0's
    entry, so its species see the cleared flag too. Loading a save never runs
    0x41EF30.

  * Saves that already got those prices are re-priced as they load. The load
    0x41EE00 copies the save into the state, then calls 0x41ED70 at 0x41EEF9;
    that call now goes through VA 0x464970 (repair_bytes()). A save is repaired
    only when its Flower of Knowledge flag (+0x2181) is clear and every species
    it has NOT discovered (byte state + 0x64 + foliage*24 + flower) with V >= 4
    asks exactly V + 3 x (V/4), at least one of them. Without the flag the
    price setup gives P = V -+ Random(V/2) with Random(n) in 0..n-1, so
    |P - V| <= V/2 - 1, while 3 x (V/4) >= V/2 for every V >= 4: such a price
    cannot come from the stock rule (below 4 both rules give V). Discovered
    species are never read or written, since the player sets asking prices
    (the price dialog 0x42FFE0 writes the same cell); a save with any other
    undiscovered price is left alone. Repaired species get the price setup's
    own formula and Random calls in its order; nothing else is written (the
    price setup itself is not re-run, so the Unused Flowers hook does not
    fire here). After a repair no undiscovered price is the Knowledge price,
    so it never runs again; the game saves the new prices at its next save.
    Unused Flowers.dll applies the same rule to its 322 species after it
    reads their sidecar, when it sees this call in the executable.

The .text section's VirtualSize grows from 0x6392F to its raw size 0x64000
so the tail is mapped (0x464930..0x464A4C is used); "R refreshes the seed shop" makes the same change, so
this setting's copy of it applies only without that setting.

Then pin_seed_refresh.py's last step runs: every PE checksum record and every
executable pin is rebuilt for all setting combinations.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pin_seed_refresh as seed  # noqa: E402

MANIFEST = ROOT / "data" / "plant_manifest.json"
EXE = "Plant Tycoon.exe"
SETTING_ID = "fix_vanilla_bugs"

NEW_GAME_PRICE_CALL = 0x41EFB8     # call 0x41DBD0 inside the new game 0x41EF30
PRICE_SETUP = 0x41DBD0
CAVE_VA = 0x464950                 # after the R key's 32 bytes at 0x464930
FLAGS = 0x2180                     # seven magic plant flag bytes, 0x2180..0x2186

LOAD_FIXUP_CALL = 0x41EEF9         # call 0x41ED70 inside the load 0x41EE00, right after the save is copied in
LOAD_FIXUP = 0x41ED70
REPAIR_VA = 0x464970               # after the new game's 19 bytes at 0x464950
RANDOM = 0x4033B0                  # Random(bound): 0..bound-1 (cdecl)
KNOWLEDGE = 0x2181                 # the Flower of Knowledge's flag byte
DISCOVERED = 0x64                  # byte discovered[24][24] at state + 0x64 + foliage*24 + flower
PRICE_FROM_VALUE = 0xA90           # asking price P = value V's cell + 26*26*4

SETTING = {
    "id": SETTING_ID,
    "name": "Fix Vanilla Bugs",
    "summary": "Fixes stock bugs: a new game no longer starts at the Flower of Knowledge (Nox Orchid) prices, "
               "and saves that did are re-priced.",
    "description": (
        "Fixes bugs in the base game. A new game sets every plant's asking price before it forgets the "
        "magic plants of the save that was open (and the game opens your last save when it starts), so "
        "after a save that has found the Flower of Knowledge (Nox Orchid), a new game prices every plant "
        "at the Flower of Knowledge price, V + 3 x (V/4), though it has not found it. The magic plants are "
        "now forgotten first, so a new game gets the normal prices; finding the Flower of Knowledge still "
        "raises them. A save already priced this way is repaired the first time it loads: if it has not "
        "found the Flower of Knowledge and every species it has not discovered is at that price, those "
        "species get normal prices (V -+ Random(V/2), as a new game gives). Discovered species keep their "
        "prices, which you may have set, and a save with any other undiscovered price, or that has found "
        "the Flower of Knowledge, stays as it is."
    ),
    "category": "main",
    "default": True,
}


def offset(va: int) -> int:
    return va - 0x400000


def cave_bytes() -> bytes:
    code = bytearray()
    code += b"\x31\xC0"                                    # xor eax, eax
    code += b"\x89\x81" + struct.pack("<I", FLAGS)         # mov [ecx+0x2180], eax  (0x2180..0x2183)
    code += b"\x89\x81" + struct.pack("<I", FLAGS + 3)     # mov [ecx+0x2183], eax  (0x2183..0x2186)
    jump_at = CAVE_VA + len(code)
    code += b"\xE9" + struct.pack("<i", PRICE_SETUP - (jump_at + 5))   # jmp 0x41DBD0 (ecx = the state)
    assert len(code) == 19
    return bytes(code)


class _Code:
    """A few bytes of x86 at a fixed VA, with labels for its branches (all rel32)."""

    def __init__(self, va: int) -> None:
        self.va, self.code, self.labels, self.fixups = va, bytearray(), {}, []

    def emit(self, raw: bytes) -> None:
        self.code += raw

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def branch(self, opcode: bytes, target: str | int) -> None:
        self.code += opcode
        self.fixups.append((len(self.code), target))
        self.code += bytes(4)

    def done(self) -> bytes:
        for at, target in self.fixups:
            to = self.va + self.labels[target] if isinstance(target, str) else target
            self.code[at:at + 4] = struct.pack("<i", to - (self.va + at + 4))
        return bytes(self.code)


JNE, JE, JL, JLE, JG, JMP, CALL = b"\x0F\x85", b"\x0F\x84", b"\x0F\x8C", b"\x0F\x8E", b"\x0F\x8F", b"\xE9", b"\xE8"


def repair_bytes() -> bytes:
    """VA 0x464970, reached from the load's call at 0x41EEF9 (thiscall, ecx = the state, one
    argument for 0x41ED70 on the stack). It ends by jumping to 0x41ED70, so the load goes on
    exactly as before. Two passes over the stock species, foliage 1..23 outer, flower 1..23
    inner (0x41DBD0's order); only species not yet discovered (state + 0x64 + foliage*24 +
    flower is 0) with V >= 4 are looked at (below 4 the Knowledge price is V, a normal price).
      pass 0: leave unless the Flower of Knowledge flag is clear and every one of them is
              asking exactly V + 3*(V/4), and there is at least one;
      pass 1: give each of them P = V -+ Random(V/2), minus when Random(100) <= 50: the
              price setup's own formula and Random calls, in its order."""
    c = _Code(REPAIR_VA)
    c.emit(b"\x60")                                         # pushad
    c.emit(b"\x8B\xF1")                                     # mov esi, ecx              (the state)
    c.emit(b"\x80\xBE" + struct.pack("<I", KNOWLEDGE) + b"\x00")   # cmp byte [esi+0x2181], 0
    c.branch(JNE, "done")                                   # found it: prices are its own
    c.emit(b"\x31\xDB")                                     # xor ebx, ebx              (pass 0)
    c.emit(b"\x6A\x00")                                     # push 0                    ([esp] = species at the Knowledge price)
    c.label("pass")
    c.emit(b"\xBD\x01\x00\x00\x00")                         # mov ebp, 1                (foliage)
    c.label("foliage")
    c.emit(b"\xBF\x01\x00\x00\x00")                         # mov edi, 1                (flower)
    c.label("flower")
    c.emit(b"\x8D\x44\x6D\x00")                             # lea eax, [ebp+ebp*2]
    c.emit(b"\x8D\x04\xC7")                                 # lea eax, [edi+eax*8]      (foliage*24 + flower)
    c.emit(b"\x80\x7C\x06" + bytes([DISCOVERED]) + b"\x00")  # cmp byte [esi+eax+0x64], 0
    c.branch(JNE, "next")                                   # discovered: never touched
    c.emit(b"\x8D\x45\x1D")                                 # lea eax, [ebp+0x1D]
    c.emit(b"\x6B\xC0\x1A")                                 # imul eax, eax, 26
    c.emit(b"\x01\xF8")                                     # add eax, edi
    c.emit(b"\x8D\x04\x86")                                 # lea eax, [esi+eax*4]      (&V; P is at +0xA90)
    c.emit(b"\x8B\x08")                                     # mov ecx, [eax]            (V)
    c.emit(b"\x83\xF9\x04")                                 # cmp ecx, 4
    c.branch(JL, "next")
    c.emit(b"\x8B\xD1")                                     # mov edx, ecx
    c.emit(b"\xC1\xFA\x02")                                 # sar edx, 2
    c.emit(b"\x8D\x14\x52")                                 # lea edx, [edx+edx*2]
    c.emit(b"\x03\xD1")                                     # add edx, ecx              (V + 3*(V/4))
    c.emit(b"\x39\x90" + struct.pack("<I", PRICE_FROM_VALUE))   # cmp [eax+0xA90], edx
    c.branch(JE, "knowledge_price")
    c.emit(b"\x85\xDB")                                     # test ebx, ebx
    c.branch(JE, "leave")                                   # pass 0: a price that is not the Knowledge price: leave the save alone
    c.branch(JMP, "next")
    c.label("knowledge_price")
    c.emit(b"\x85\xDB")                                     # test ebx, ebx
    c.branch(JNE, "reprice")
    c.emit(b"\xFF\x04\x24")                                 # inc dword [esp]
    c.branch(JMP, "next")
    c.label("reprice")
    c.emit(b"\x50")                                         # push eax                  (&V)
    c.emit(b"\x8B\xC1")                                     # mov eax, ecx
    c.emit(b"\x99")                                         # cdq
    c.emit(b"\x2B\xC2")                                     # sub eax, edx
    c.emit(b"\xD1\xF8")                                     # sar eax, 1                (V/2)
    c.emit(b"\x50")                                         # push eax
    c.branch(CALL, RANDOM)                                  # call Random               (d)
    c.emit(b"\x83\xC4\x04")                                 # add esp, 4
    c.emit(b"\x50")                                         # push eax                  (d)
    c.emit(b"\x6A\x64")                                     # push 100
    c.branch(CALL, RANDOM)                                  # call Random
    c.emit(b"\x83\xC4\x04")                                 # add esp, 4
    c.emit(b"\x5A")                                         # pop edx                   (d)
    c.emit(b"\x59")                                         # pop ecx                   (&V)
    c.emit(b"\x83\xF8\x32")                                 # cmp eax, 50
    c.branch(JG, "plus")
    c.emit(b"\xF7\xDA")                                     # neg edx
    c.label("plus")
    c.emit(b"\x03\x11")                                     # add edx, [ecx]            (V + d)
    c.emit(b"\x89\x91" + struct.pack("<I", PRICE_FROM_VALUE))   # mov [ecx+0xA90], edx  (the asking price)
    c.label("next")
    c.emit(b"\x47")                                         # inc edi
    c.emit(b"\x83\xFF\x17")                                 # cmp edi, 23
    c.branch(JLE, "flower")
    c.emit(b"\x45")                                         # inc ebp
    c.emit(b"\x83\xFD\x17")                                 # cmp ebp, 23
    c.branch(JLE, "foliage")
    c.emit(b"\x85\xDB")                                     # test ebx, ebx
    c.branch(JNE, "leave")                                  # pass 1 done
    c.emit(b"\x83\x3C\x24\x00")                             # cmp dword [esp], 0
    c.branch(JE, "leave")                                   # nothing at the Knowledge price
    c.emit(b"\x43")                                         # inc ebx                   (pass 1)
    c.branch(JMP, "pass")
    c.label("leave")
    c.emit(b"\x58")                                         # pop eax
    c.label("done")
    c.emit(b"\x61")                                         # popad
    c.branch(JMP, LOAD_FIXUP)                               # jmp 0x41ED70, as the load called it
    return c.done()


def records(vanilla: bytes) -> list[dict]:
    hb = seed.hex_bytes
    cave = cave_bytes()
    stock_call = b"\xE8" + struct.pack("<i", PRICE_SETUP - (NEW_GAME_PRICE_CALL + 5))
    new_call = b"\xE8" + struct.pack("<i", CAVE_VA - (NEW_GAME_PRICE_CALL + 5))
    repair = repair_bytes()
    assert CAVE_VA + len(cave) <= REPAIR_VA and REPAIR_VA + len(repair) <= 0x465000
    stock_fixup = b"\xE8" + struct.pack("<i", LOAD_FIXUP - (LOAD_FIXUP_CALL + 5))
    new_fixup = b"\xE8" + struct.pack("<i", REPAIR_VA - (LOAD_FIXUP_CALL + 5))
    vso = seed.text_vsize_offset(vanilla)
    out = [
        {"id": "fix_new_game_knowledge_text_size", "file_path": EXE, "offset": hex(vso),
         "expected": hb(struct.pack("<I", seed.TEXT_VSIZE_OLD)),
         "replacement": hb(struct.pack("<I", seed.TEXT_VSIZE_NEW)),
         "requires": [SETTING_ID], "excludes": [seed.SETTING_ID],
         "note": "The .text section's VirtualSize, 0x6392F -> 0x64000 (its raw size), so the zero tail that "
                 "holds the new game's flag clear is mapped. R refreshes the seed shop makes the same change, "
                 "so this copy applies only without it."},
        {"id": "fix_new_game_knowledge_clear", "file_path": EXE, "offset": hex(offset(CAVE_VA)),
         "expected": hb(bytes(len(cave))), "replacement": hb(cave), "requires": [SETTING_ID],
         "note": "VA 0x464950 (the zero tail of .text): clear the seven magic plant flags, state + "
                 "0x2180..0x2186 (the bytes 0x41F170 clears later), then jump to the price setup 0x41DBD0."},
        {"id": "fix_new_game_knowledge_call", "file_path": EXE, "offset": hex(offset(NEW_GAME_PRICE_CALL)),
         "expected": hb(stock_call), "replacement": hb(new_call), "requires": [SETTING_ID],
         "note": "The new game's price setup call (0x41EFB8) goes through 0x464950, so the prices never "
                 "read the Flower of Knowledge flag of the save that was open before."},
        {"id": "fix_loaded_knowledge_prices_code", "file_path": EXE, "offset": hex(offset(REPAIR_VA)),
         "expected": hb(bytes(len(repair))), "replacement": hb(repair), "requires": [SETTING_ID],
         "note": "VA 0x464970 (the zero tail of .text): a loaded save that has not found the Flower of "
                 "Knowledge (state + 0x2181 is 0) but where every species it has not discovered (V >= 4) asks "
                 "exactly V + 3 x (V/4), the price an earlier save's flag gave its new game, gets those "
                 "undiscovered species re-priced by the price setup's own rule, V -+ Random(V/2). Discovered "
                 "species, whose prices the player may have set, and every other field are left alone. Then "
                 "it jumps to 0x41ED70, where the load was going."},
        {"id": "fix_loaded_knowledge_prices_call", "file_path": EXE, "offset": hex(offset(LOAD_FIXUP_CALL)),
         "expected": hb(stock_fixup), "replacement": hb(new_fixup), "requires": [SETTING_ID],
         "note": "The load's call at 0x41EEF9 (to 0x41ED70, just after the save is copied into the state) "
                 "goes through 0x464970 first."},
    ]
    for record in out:
        at, raw = int(record["offset"], 16), bytes.fromhex(record["expected"].replace(" ", ""))
        if vanilla[at:at + len(raw)] != raw:
            raise SystemExit(f"{record['id']} at 0x{at:X}: the vanilla bytes are not {record['expected']}")
    return out


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / EXE).read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    manifest["settings"].insert(0, dict(SETTING))        # first, as in Fish Tycoon
    manifest["patches"] = [p for p in manifest["patches"] if SETTING_ID not in p.get("requires", [])]
    manifest["patches"] += records(vanilla)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(records(vanilla))} vanilla fix patches; rebuilding checksums and pins")
    return seed.main()


if __name__ == "__main__":
    raise SystemExit(main())
