"""Pin the "Fix Vanilla Bugs" setting into the fish manifest.

    python scripts/pin_vanilla_fixes.py "<vanilla Fish Tycoon folder>"

Stock bugs fixed by data changes alone, each listed in VANILLA_FIXES:

  * The two store plants do each other's job. The $200 Plant of Incubation
    ("...increases the viability of purchased eggs") sets the dword at
    state + 0x168, but only the starvation code reads it (0x4205A1: a
    starving fish gets food +5 on Random(100) <= 20). The $350 Plant of
    Nutrition sets state + 0x17C, which the three egg-hatch paths read
    (0x4213DB, 0x4214AA, 0x42157D: +1 egg per batch). The four reads swap
    their offset, so each plant does what its name says. The store (names,
    pictures, prices) and the plant drawn in the tank stay as they are, and
    saves need no change: an owned plant keeps its dword.

  * The Golden Seahorse is bought with health Random(15) + 80 and food 50
    (0x427E0C, 0x427E23), below the game's full meters of 100. Owner's call
    (2026-10-29): it comes full. The roll's call becomes `mov eax, 20` (the
    stock `add eax, 80` that follows makes 100) and the food store's
    immediate 50 becomes 100.

  * Seahorses already in a save get full meters when it loads. The game
    never lowers a seahorse's health or food (its age step skips body 22 at
    0x42043F, overfeeding skips it at 0x4121F4; only feeding and one supply
    item raise them), so filling them on every load fills them once and needs
    no sidecar. The load routine 0x41AE70 reads the save into a stack buffer
    and copies it into the state (0x41AF54 push size, 0x41AF62 memcpy, which
    DS Exclusive Fish hooks). The push becomes a jump to SEAHORSE_LOAD_CAVE,
    which sets health and food to 100 in every live record of body 22 and fin
    22 in the read buffer (tanks 0-3, slots 0-30), then pushes the size and
    jumps back. Only those two dwords of those records change; the game
    writes them to the save on its next save. The cave sits in the zero tail
    of .text, so .text's VirtualSize grows to 0x3F000 as for the other
    payloads there.

  * A save whose game speed (state + 0x1E168) is 0 crashes the game. The age
    step divides each live fish's seconds by 60 x speed (0x41FFFF, 0x420953:
    div dword ptr [ecx + 0x1E168]), so speed 0 is an integer divide by zero,
    the crash Virtual Families 1's bank chart has. The game never writes 0
    (a new game sets 10; the options write 5, 10, 15 or 9999), but its load
    takes the speed as the save holds it, so a hand-edited, Cheat Engine
    edited or damaged save can hold 0. The only stock check, "over 100
    becomes 10" (0x41AAA4), runs when no save is found, not on a load. The
    load jump at 0x41AF54 now goes to SPEED_LOAD_CAVE first: a speed of 0 in
    the read buffer becomes 10 (the game's own fallback and a new game's
    speed), then it jumps on to SEAHORSE_LOAD_CAVE, unchanged. Every other
    speed, negative ones included (an unsigned divide by a huge divisor, no
    fault), loads as stock.

Then run scripts/pin_tank_expansion.py (it rebuilds the PE checksum record
and pin of every byte-patch combination, this setting's included),
scripts/pin_ds_fish.py and scripts/pin_ds_store.py, then the companions'
pin scripts that re-pin from those: pin_time_warp, pin_store_extras,
pin_extra_tanks, pin_supply_slots, pin_time_warp, pin_store_extras,
pin_multiple_ornaments, pin_fish_window, pin_counts, pin_optimize_prices,
pin_everything_free, pin_time_warp, pin_store_extras, pin_unicode_text and
pin_translations (the v1.0.24 run). pin_ds_fish.py and pin_ds_store.py also
pin combinations with the loader-tail settings (Render Unicode with In-Game
Fonts, Translations), which the patcher never looks up (fish_patcher.pin_settings
leaves them out) and the tests forbid; drop every key that
names one. Afterwards the key set must be the same as before and only the
combinations with this setting may change.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "fish_manifest.json"
EXE = "Fish Tycoon.exe"
SETTING_ID = "fix_vanilla_bugs"

SETTING = {
    "id": SETTING_ID,
    "name": "Fix Vanilla Bugs",
    "summary": (
        "Fixes stock bugs: the Plant of Incubation and Plant of Nutrition do what their names say, the "
        "Golden Seahorse has full health and food, a save with game speed 0 no longer crashes, and the trash "
        "can takes medicines, chemicals, eggs and ornaments."
    ),
    "description": (
        "Fixes bugs in the base game. The store's two plants do each other's job: the Plant of Incubation "
        "($200, \"increases the viability of purchased eggs\") actually rescues starving fish (on "
        "Random(100) <= 20 per step, food +5), and the Plant of Nutrition ($350) actually adds 1 egg to "
        "every egg batch. Their effects are swapped back: the Plant of Incubation adds the egg and the Plant "
        "of Nutrition rescues starving fish. Names, pictures and prices are unchanged, and plants already "
        "bought switch to their proper effect. The Golden Seahorse arrives with full health and a full food "
        "meter (the base game gives it health 80-94 and food 50), and a seahorse already in a save is filled "
        "up the first time the save is loaded with this setting. The game never lowers a seahorse's meters, so "
        "it stays full; nothing else about it changes. A save whose game speed is 0 (the game never saves that, "
        "but a hand-edited or damaged save can hold it) crashed the game with a divide by zero as its fish aged; "
        "it now loads at speed 10, the speed a new game starts at. The trash can took only fish: a medicine, "
        "chemical or egg let go on it said \"This must be used directly in a tank.\" and went back to its slot, and "
        "an ornament just rested on it. Now a supply picked up from any slot (the patcher's extra slots and items "
        "too) and let go on the trash can is thrown away, the whole slot with every dose or hatch left, with the "
        "trash sound and no question; an ornament goes after the game's \"Delete this fish?\" question and can then "
        "be bought again. The fish food is a tool and stays."
    ),
    "category": "main",
    "default": True,
}

STARVING_CHECK = 0x4205A1     # cmp dword ptr [eax + 0x168], ebx
EGG_READS = (0x4213DB, 0x4214AA, 0x42157D)      # mov ecx, dword ptr [edi + 0x17c]
SEAHORSE_HEALTH_ROLL = 0x427E0C                 # call 0x403240 (Random(15)), then add eax, 0x50
SEAHORSE_FOOD = 0x427E2A                        # the 50 of mov dword ptr [esp + 0x80], 0x32
LOAD_PUSH_SIZE = 0x41AF54                       # push 0x1E3C8, before the memcpy into the state
LOAD_BACK = 0x41AF59                            # lea ecx, [esp + 0x120]
SEAHORSE_LOAD_CAVE = 0x43F880                   # zero tail of .text, after the other payloads
SPEED_LOAD_CAVE = 0x43F8D0                      # right after the seahorse routine (0x43F880..0x43F8CE)
GAME_SPEED = 0x1E168                            # state + 0x1E168: the age step's divisor (0x41FFFF, 0x420953)
FALLBACK_SPEED = 10                             # a new game's speed, and the stock "over 100" reset's
TEXT_VIRTUAL_SIZE = 0x1F8                       # .text VirtualSize: 0x3E29F -> 0x3F000
FULL_METER = 100                                # the game's cap for health and food


def offset(va: int) -> int:
    return va - 0x400000      # file offset = VA - image base


def rel32(source_end: int, target: int) -> bytes:
    return ((target - source_end) & 0xFFFFFFFF).to_bytes(4, "little")


def seahorse_load_cave() -> bytes:
    """Full meters for every live Golden Seahorse (body 22, fin 22) in the read save buffer.

    At 0x41AF54 the buffer (the state from +8) is at [esp + 0x11C], so the first fish
    record (state + 0x390) is at [esp + 0x4A4]; tanks are 0x51EC apart, records 0x288,
    31 records a tank. eax (the memcpy destination) is kept; ecx and edx are free."""
    first = 0x11C + 0x390 - 8
    full = FULL_METER.to_bytes(4, "little")
    code = bytearray()
    code += b"\x8D\x94\x24" + first.to_bytes(4, "little")                      # lea edx, [esp + 0x4A4]
    tank = len(code)
    code += b"\xB9\x1F\x00\x00\x00"                                            # mov ecx, 31
    record = len(code)
    code += b"\x83\x3A\x00" + b"\x74\x1A"                                      # cmp [edx], 0 ; je next
    code += b"\x83\x7A\x4C\x16" + b"\x75\x14"                                  # body 22?     ; jne next
    code += b"\x83\x7A\x50\x16" + b"\x75\x0E"                                  # fin 22?      ; jne next
    code += b"\xC7\x42\x3C" + full                                             # health = 100
    code += b"\xC7\x42\x44" + full                                             # food = 100
    code += b"\x81\xC2" + (0x288).to_bytes(4, "little")                        # next: add edx, 0x288
    code += b"\x49"                                                            # dec ecx
    code += b"\x75" + bytes([(record - (len(code) + 2)) & 0xFF])               # jnz record
    code += b"\x81\xC2" + (0x51EC - 31 * 0x288).to_bytes(4, "little")          # add edx, to the next tank
    code += b"\x8D\x8C\x24" + (first + 4 * 0x51EC).to_bytes(4, "little")       # lea ecx, past tank 3
    code += b"\x3B\xD1"                                                        # cmp edx, ecx
    code += b"\x72" + bytes([(tank - (len(code) + 2)) & 0xFF])                 # jb tank
    code += b"\x68\xC8\xE3\x01\x00"                                            # push 0x1E3C8 (the stock push)
    code += b"\xE9" + rel32(SEAHORSE_LOAD_CAVE + len(code) + 5, LOAD_BACK)     # jmp 0x41AF59
    return bytes(code)


def speed_load_cave() -> bytes:
    """A save's game speed of 0 becomes 10, then on to the seahorse routine.

    At 0x41AF54 the read buffer (the state from +8) is at [esp + 0x11C], so the speed
    (state + 0x1E168) is at [esp + 0x1E27C]. The flags it changes are set again before the
    load reads any (the seahorse routine's first compare)."""
    at = (0x11C + GAME_SPEED - 8).to_bytes(4, "little")
    code = bytearray()
    code += b"\x83\xBC\x24" + at + b"\x00"                                        # cmp dword [esp + 0x1E27C], 0
    code += b"\x75\x0B"                                                            # jne past the store
    code += b"\xC7\x84\x24" + at + FALLBACK_SPEED.to_bytes(4, "little")           # mov dword [esp + 0x1E27C], 10
    code += b"\xE9" + rel32(SPEED_LOAD_CAVE + len(code) + 5, SEAHORSE_LOAD_CAVE)  # jmp 0x43F880
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
            self.code[at:at + 4] = (to - (self.va + at + 4)).to_bytes(4, "little", signed=True)
        return bytes(self.code)


JE, JNE, JL, JG, JA, JMP, CALL = b"\x0F\x84", b"\x0F\x85", b"\x0F\x8C", b"\x0F\x8F", b"\x0F\x87", b"\xE9", b"\xE8"

# The trash can takes supplies and ornaments (stock: only fish). The tank screen (impl) keeps the
# trash can's rectangle at +0x88..+0x94 (left, top, right, bottom, inclusive, as the fish trash and
# DS Store Items test it), the state at +0x34, the sound manager at +0x4C, the dialog parent at +0x50,
# the held supply slot at +0x1C and the held ornament at +0x28 (0x63 = none).
SUPPLY_OUTSIDE = 0x42165C          # cmp edi, [esi + 0x98]: the use 0x420B70, let go outside the tank
SUPPLY_OUTSIDE_NEXT = 0x421662     # jl 0x421680 (the isolation tank's test goes on)
SUPPLY_DONE = 0x42168A             # the use's exit: nothing held (impl + 0x1C = 0x63), ret 8
SUPPLY_TRASH_CAVE = 0x43F900       # zero tail of .text, after the speed check (0x43F8D0..0x43F8E9)
ORNAMENT_SETTLE = 0x41F7BF         # mov eax, [esp + 0x14]; push edi: the ornament drop's settle 0x41EA10
ORNAMENT_SETTLE_NEXT = 0x41F7C4    # push ebx
ORNAMENT_DONE = 0x41F7CE           # the drop's exit: nothing held (impl + 0x28 = 0x63), ret 8
ORNAMENT_TRASH_CAVE = 0x43F9A0       # after the supply routine (0x43F900..0x43F996)
SOUND_GET, SOUND_PLAY, SOUND_TRASH = 0x4251A0, 0x40AE20, 4          # the fish trash's sound (0x41E7F6)
DIALOG_INIT, DIALOG_RUN, DIALOG_FREE = 0x4221A0, 0x401D00, 0x422440
STRING_DELETE = 0xAC               # "Delete this fish?", the trash can's question (and Multiple Ornaments')
FOOD_ITEM = 0x17                   # the fish food, a tool (slot #1)
ORNAMENT_SPRITES = (177, 178, 179, 180, 181, 182)
# Sprite 177..182 -> its store item (the purchase switch at 0x427BAE): Shell 16, Pagoda 17, Diver 18,
# Sunken Antique Column 20, Fancy Coral 19, Sunken Ship 21.
ORNAMENT_ITEMS = bytes((16, 17, 18, 20, 19, 21))


def sound_call(code: _Code) -> None:
    """The trash's sound 4, as the fish trash plays it, skipped when the game has no such sound."""
    code.emit(b"\x8B\x4E\x4C")                                # mov ecx, [esi + 0x4C]  (the sound manager)
    code.emit(b"\x6A" + bytes([SOUND_TRASH]))                 # push 4
    code.branch(CALL, SOUND_GET)
    code.emit(b"\x85\xC0")                                    # test eax, eax
    code.branch(JE, "silent")
    code.emit(b"\x6A\x00")                                    # push 0
    code.emit(b"\x8B\xC8")                                    # mov ecx, eax
    code.branch(CALL, SOUND_PLAY)
    code.label("silent")


def trash_rect_tests(code: _Code, x_reg: bytes, y_reg: bytes) -> None:
    """Branch to "stock" unless (x, y) is on the trash can. x_reg / y_reg: the ModRM byte of
    `cmp reg, [esi + disp32]` for the registers holding x and y."""
    for modrm, disp, jump in ((x_reg, 0x88, JL), (x_reg, 0x90, JG), (y_reg, 0x8C, JL), (y_reg, 0x94, JG)):
        code.emit(b"\x3B" + modrm + disp.to_bytes(4, "little"))
        code.branch(jump, "stock")


def supply_trash_cave() -> bytes:
    """A supply let go on the trash can is thrown away: the whole slot, every dose or hatch left.

    Reached from the use 0x420B70 when the supply is let go outside the tank (0x42165C, edi = x,
    ebx = y, esi = the tank screen). On the trash can, with a held stock slot 2-4 (impl + 0x1C = 1..3)
    that holds an item other than the fish food, the slot is emptied as the use empties a used-up
    one (0x420D9B: item, present, count, icon and cursor 0; its x stays), the fish trash's sound
    plays and the use ends through its own exit (nothing held). No question: the game asks only
    before a live fish. Anywhere else the stock test of the isolation tank runs on, so the hints
    ("This must be used directly in a tank.", or the isolation tank's) are as before. Extra Supply
    Slots lends an extra slot to stock slot 2-4 and Universal supply slots moves the record to its
    item's native slot before this code runs, so every slot is covered; DS Store Items throws its
    own supplies away before the use is called (0x421B52)."""
    c = _Code(SUPPLY_TRASH_CAVE)
    trash_rect_tests(c, b"\xBE", b"\x9E")                     # cmp edi / ebx, [esi + disp32]
    c.emit(b"\x8B\x46\x1C")                                   # mov eax, [esi + 0x1C]   (the held slot)
    c.emit(b"\x48")                                           # dec eax
    c.emit(b"\x83\xF8\x02")                                   # cmp eax, 2              (slots 2-4 only)
    c.branch(JA, "stock")
    c.emit(b"\x40")                                           # inc eax
    c.emit(b"\x6B\xC0\x1C")                                   # imul eax, eax, 0x1C
    c.emit(b"\x03\x46\x34")                                   # add eax, [esi + 0x34]
    c.emit(b"\x05\xB8\x02\x00\x00")                           # add eax, 0x2B8          (the slot record)
    c.emit(b"\x83\x38" + bytes([FOOD_ITEM]))                  # cmp dword [eax], 0x17   (the food: a tool)
    c.branch(JE, "stock")
    c.emit(b"\x83\x78\x0C\x00")                               # cmp dword [eax + 0x0C], 0  (an empty slot)
    c.branch(JE, "stock")
    c.emit(b"\x33\xC9")                                       # xor ecx, ecx
    c.emit(b"\x89\x08\x89\x48\x04\x89\x48\x08\x89\x48\x0C\x89\x48\x10")   # item .. cursor = 0
    sound_call(c)
    c.branch(JMP, SUPPLY_DONE)
    c.label("stock")
    c.emit(b"\x3B\xBE\x98\x00\x00\x00")                       # cmp edi, [esi + 0x98]   (the stock compare)
    c.branch(JMP, SUPPLY_OUTSIDE_NEXT)
    return c.done()


def ornament_trash_cave() -> bytes:
    """An ornament let go on the trash can is thrown away after the game's own question.

    Reached from the ornament drop 0x41F660 at its settle (0x41F7BF: esi = the tank screen,
    ebx = the tank, edi = the ornament's record 0-5, ebp = y, [esp + 0x14] = x). On the trash can,
    for a live store ornament of a stock tank (sprites 177-182: Shell, Pagoda, Diver, Sunken
    Antique Column, Fancy Coral, Sunken Ship), the game asks "Delete this fish?" (string 0xAC,
    what it asks before the fish trash, and what Multiple Ornaments asks for a copy and DS Store
    Items for the eel's rock); Yes clears the record (as DS Store Items clears the rock) and the
    store's ownership dword (state + item * 20 + 0x78, which the selling scene's customer count
    reads and the store checks before selling it), so it can be bought again; the fish trash's
    sound plays and the drop ends through its own exit. No, or anywhere else: the stock settle,
    as before. Copies (Multiple Ornaments) and the eel's rock (DS Store Items) never get here."""
    c = _Code(ORNAMENT_TRASH_CAVE)
    c.emit(b"\x8B\x44\x24\x14")                               # mov eax, [esp + 0x14]   (x)
    trash_rect_tests(c, b"\x86", b"\xAE")                     # cmp eax / ebp, [esi + disp32]
    c.emit(b"\x83\xFF\x05")                                   # cmp edi, 5
    c.branch(JA, "stock")
    c.emit(b"\x83\xFB\x02")                                   # cmp ebx, 2              (a stock tank)
    c.branch(JA, "stock")
    c.emit(b"\x69\xC3\xEC\x51\x00\x00")                       # imul eax, ebx, 0x51EC
    c.emit(b"\x03\x46\x34")                                   # add eax, [esi + 0x34]
    c.emit(b"\x6B\xCF\x2C")                                   # imul ecx, edi, 0x2C
    c.emit(b"\x8D\x84\x08\x08\x52\x00\x00")                   # lea eax, [eax + ecx + 0x5208]  (the record)
    c.emit(b"\x80\x38\x00")                                   # cmp byte [eax], 0
    c.branch(JE, "stock")
    c.emit(b"\x8B\x48\x24")                                   # mov ecx, [eax + 0x24]   (its sprite)
    c.emit(b"\x81\xE9" + ORNAMENT_SPRITES[0].to_bytes(4, "little"))   # sub ecx, 177
    c.emit(b"\x83\xF9\x05")                                   # cmp ecx, 5
    c.branch(JA, "stock")
    c.emit(b"\x50\x51")                                       # push eax; push ecx      (record, index)
    c.emit(b"\x81\xEC\x04\x04\x00\x00")                       # sub esp, 0x404          (answer, dialog)
    c.emit(b"\x8D\x4C\x24\x04")                               # lea ecx, [esp + 4]
    c.emit(b"\x6A\x01\x68" + STRING_DELETE.to_bytes(4, "little"))     # push 1; push 0xAC
    c.branch(CALL, DIALOG_INIT)
    c.emit(b"\x8D\x4C\x24\x04")                               # lea ecx, [esp + 4]
    c.emit(b"\x6A\x00\xFF\x76\x50")                           # push 0; push [esi + 0x50]
    c.branch(CALL, DIALOG_RUN)
    c.emit(b"\x89\x04\x24")                                   # mov [esp], eax          (0 = Yes)
    c.emit(b"\x8D\x4C\x24\x04")                               # lea ecx, [esp + 4]
    c.branch(CALL, DIALOG_FREE)
    c.emit(b"\x58")                                           # pop eax
    c.emit(b"\x81\xC4\x00\x04\x00\x00")                       # add esp, 0x400
    c.emit(b"\x59\x5A")                                       # pop ecx; pop edx        (index, record)
    c.emit(b"\x85\xC0")                                       # test eax, eax
    c.branch(JNE, "stock")
    c.emit(b"\x57\x51")                                       # push edi; push ecx
    c.emit(b"\x8B\xFA\x33\xC0\xB9\x0B\x00\x00\x00\xF3\xAB")   # mov edi, edx; xor eax, eax; mov ecx, 11; rep stosd
    c.emit(b"\x59\x5F")                                       # pop ecx; pop edi
    c.emit(b"\x0F\xB6\x89")                                   # movzx ecx, byte [ecx + items]
    items_at = len(c.code)
    c.emit(bytes(4))
    c.emit(b"\x6B\xC9\x14")                                   # imul ecx, ecx, 20
    c.emit(b"\x03\x4E\x34")                                   # add ecx, [esi + 0x34]
    c.emit(b"\xC7\x41\x78\x00\x00\x00\x00")                   # mov dword [ecx + 0x78], 0  (not owned)
    sound_call(c)
    c.branch(JMP, ORNAMENT_DONE)
    c.label("stock")
    c.emit(b"\x8B\x44\x24\x14\x57")                           # mov eax, [esp + 0x14]; push edi (the stock bytes)
    c.branch(JMP, ORNAMENT_SETTLE_NEXT)
    c.label("items")
    c.emit(ORNAMENT_ITEMS)
    code = bytearray(c.done())
    code[items_at:items_at + 4] = (ORNAMENT_TRASH_CAVE + c.labels["items"]).to_bytes(4, "little")   # absolute
    return bytes(code)


def spaced(raw: bytes) -> str:
    return raw.hex(" ").upper()


# (patch id, file offset, expected, replacement, note)
VANILLA_FIXES = [
    ("fix_plant_effect_starving", offset(STARVING_CHECK), "39 98 68 01 00 00", "39 98 7C 01 00 00",
     "The starvation rescue checks the Plant of Nutrition (state + 0x17C), not the Plant of Incubation."),
] + [
    (f"fix_plant_effect_eggs_{va:X}", offset(va), "8B 8F 7C 01 00 00", "8B 8F 68 01 00 00",
     "The extra egg checks the Plant of Incubation (state + 0x168), not the Plant of Nutrition.")
    for va in EGG_READS
] + [
    ("fix_golden_seahorse_spawn_health", offset(SEAHORSE_HEALTH_ROLL), "E8 2F B4 FD FF", "B8 14 00 00 00",
     "A bought Golden Seahorse's health is 100 (mov eax, 20, then the stock add eax, 80), not Random(15) + 80."),
    ("fix_golden_seahorse_spawn_food", offset(SEAHORSE_FOOD), "32 00 00 00", "64 00 00 00",
     "A bought Golden Seahorse's food is 100, not 50."),
    ("fix_golden_seahorse_load_jump", offset(LOAD_PUSH_SIZE), "68 C8 E3 01 00",
     spaced(b"\xE9" + rel32(LOAD_PUSH_SIZE + 5, SPEED_LOAD_CAVE)),
     f"Loading a save jumps to the game speed check at 0x{SPEED_LOAD_CAVE:X}, then the full-meters routine at "
     f"0x{SEAHORSE_LOAD_CAVE:X}, before copying it into the state; that routine does the stock push 0x1E3C8 and "
     "jumps back."),
    ("fix_game_speed_zero_on_load", offset(SPEED_LOAD_CAVE), spaced(bytes(len(speed_load_cave()))),
     spaced(speed_load_cave()),
     "A save just read with game speed 0 (state + 0x1E168, the age step's divisor at 0x41FFFF and 0x420953) gets "
     "speed 10, the game's own fallback, instead of a divide-by-zero crash; then the full-meters routine."),
    ("install_golden_seahorse_load_full_meters", offset(SEAHORSE_LOAD_CAVE), spaced(bytes(len(seahorse_load_cave()))),
     spaced(seahorse_load_cave()),
     "Every live Golden Seahorse (body 22, fin 22) in the save just read gets health 100 and food 100."),
    ("fix_trash_supplies_jump", offset(SUPPLY_OUTSIDE), "3B BE 98 00 00 00",
     spaced(b"\xE9" + rel32(SUPPLY_OUTSIDE + 5, SUPPLY_TRASH_CAVE) + b"\x90"),
     f"A supply let go outside the tank goes to the trash test at 0x{SUPPLY_TRASH_CAVE:X} first; it does the stock "
     "compare and jumps back to 0x421662 when the supply is not thrown away."),
    ("install_trash_supplies", offset(SUPPLY_TRASH_CAVE), spaced(bytes(len(supply_trash_cave()))),
     spaced(supply_trash_cave()),
     "A medicine, chemical or egg (stock or the patcher's, from any slot but the fish food's) let go on the trash "
     "can is thrown away with everything left in its slot, with the fish trash's sound and no question; elsewhere "
     "the stock hint, as before."),
    ("fix_trash_ornaments_jump", offset(ORNAMENT_SETTLE), "8B 44 24 14 57",
     spaced(b"\xE9" + rel32(ORNAMENT_SETTLE + 5, ORNAMENT_TRASH_CAVE)),
     f"An ornament let go goes to the trash test at 0x{ORNAMENT_TRASH_CAVE:X} before the stock settle; it does the "
     "stock bytes and jumps back to 0x41F7C4 when the ornament is kept."),
    ("install_trash_ornaments", offset(ORNAMENT_TRASH_CAVE), spaced(bytes(len(ornament_trash_cave()))),
     spaced(ornament_trash_cave()),
     "A store ornament let go on the trash can is thrown away after \"Delete this fish?\" (the trash can's question): "
     "its record and its store ownership are cleared (it can be bought again), with the fish trash's sound."),
    ("extend_text_virtual_size_for_fix_vanilla_bugs", TEXT_VIRTUAL_SIZE, "9F E2 03 00", "00 F0 03 00",
     ".text VirtualSize 0x3E29F -> 0x3F000 (its raw size), so the full-meters routine in the zero tail is mapped "
     "as code."),
]

# The other settings' VirtualSize records write the same value; this setting's record replaces them.
OTHER_VIRTUAL_SIZE_RECORDS = (
    "extend_text_virtual_size_for_golden_seahorse_repurchase",
    "extend_text_virtual_size_for_golden_seahorse_repurchase_with_slots",
    "extend_text_virtual_size_for_slots_payload",
)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    vanilla = (Path(sys.argv[1]) / EXE).read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["settings"] = [s for s in manifest["settings"] if s["id"] != SETTING_ID]
    manifest["settings"].insert(0, dict(SETTING))
    manifest["patches"] = [p for p in manifest["patches"] if SETTING_ID not in p.get("requires", [])
                           or p["id"].startswith("update_pe_checksum")]
    for patch in manifest["patches"]:
        if patch["id"] in OTHER_VIRTUAL_SIZE_RECORDS and SETTING_ID not in patch.get("excludes", []):
            patch["excludes"] = sorted(patch.get("excludes", []) + [SETTING_ID])
    for name, offset, expected, replacement, note in VANILLA_FIXES:
        raw = bytes.fromhex(expected.replace(" ", ""))
        if vanilla[offset:offset + len(raw)] != raw:
            raise SystemExit(f"{name} at 0x{offset:X}: the vanilla bytes are not {expected}")
        manifest["patches"].append({"id": name, "file_path": EXE, "offset": hex(offset), "expected": expected,
                                    "replacement": replacement, "requires": [SETTING_ID], "note": note})
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(VANILLA_FIXES)} vanilla fixes; now run pin_tank_expansion.py, pin_ds_fish.py, pin_ds_store.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
