"""Every line a translation can replace: the games' string tables and the patcher DLLs' texts.

Game lines ("strings/<id>") are read from the player's own copy of the game when a template is
made (the patcher never ships the games' text): Fish Tycoon's table at 0x457340 (249 entries
{id, English, German}, looked up by 0x426FD0) and Plant Tycoon's at 0x48EC58 (399 entries
{id, name, English, override}, looked up by 0x44CA70 through [0x493CC0 + id * 4]). Where one of
the patcher's own settings changes a line's English (Unknown Chemical: 3 uses), the changed
English is a second line with the same id, so a translation covers both copies of the game.

Patcher DLL lines ("mod/<dll>.<name>") are this file's MOD_STRINGS: the visible texts of each
companion DLL, found at runtime by the translation DLL through the DLL's relocations (every
pointer to the text) -- no DLL needed changing. Each has a limit where the DLL copies it into a
fixed buffer, so a longer translation can never overflow it (the runtime refuses it and shows
English); docs/translations.md lists them.

Limits for game lines: the game copies some lines into fixed buffers (sprintf, inline copies);
for those ids (BUFFER_IDS, found by reading every call of the lookup, see
docs/translations.md) a translation may be at most half as long again as the English (8 bytes
more for short ones), well inside every such buffer. NEVER_TRANSLATED are texts the game
writes into saves ("NEW PLAYER" marks an empty player slot), so they keep their English.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct

import translation_format as tfmt

IMAGE_BASE = 0x400000
EXE_NAMES = {"fish": "Fish Tycoon.exe", "plant": "Plant Tycoon.exe"}
ABSOLUTE_MAX = 1000                # bytes: no translated line is ever longer (runtime and editor)


def buffer_limit(english_bytes: int) -> int:
    """The longest translation (bytes) of a line the game copies into a fixed buffer."""
    return english_bytes + max(8, english_bytes // 2)


@dataclass(frozen=True)
class GameTable:
    address: int
    count: int
    stride: int
    english_at: int
    name_at: int | None


TABLES = {
    "fish": GameTable(0x457340, 0xF9, 12, 4, None),
    "plant": GameTable(0x48EC58, 0x18F, 16, 8, 4),
}

NEVER_TRANSLATED = {
    "fish": frozenset({0x0B}),       # "NEW PLAYER": written into the player list, marks an empty slot
    "plant": frozenset({0x06}),      # "New Player": the same
}

# Ids whose text the game copies into a fixed buffer (inline copies, sprintf), from every call of
# the lookup (scripts/find_translation_limits.py lists them); register-chosen ids at such sites are
# covered by their ranges (Plant: chemical and item names 0x189-0x1B0, every store item title).
_FISH_BUFFER = {0x07, 0x08, 0xAD} | set(range(0x45, 0x74))
_PLANT_BUFFER = {0x05, 0x0F, 0x41, 0x119, 0x11B, 0x11D, 0x1A1} | set(range(0x189, 0x1B1))
BUFFER_IDS = {"fish": frozenset(_FISH_BUFFER), "plant": frozenset(_PLANT_BUFFER)}
PLANT_TITLE_PREFIX = "eShortDesc"   # store item titles: every one can reach the store's hint buffer

# Number subjects for choices ({%1: one=... | other=...}): every %d line says so in its notes.


def _read_c_string(image: bytes, offset: int) -> bytes:
    end = image.index(b"\0", offset)
    return image[offset:end]


def _sections(exe: bytes) -> list[tuple[int, int, int, int]]:
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    count = struct.unpack_from("<H", exe, pe + 6)[0]
    optional = struct.unpack_from("<H", exe, pe + 20)[0]
    out = []
    for i in range(count):
        at = pe + 24 + optional + i * 40
        vsize, rva, raw_size, raw = struct.unpack_from("<IIII", exe, at + 8)
        out.append((rva, vsize, raw, raw_size))
    return out


def _offset(exe: bytes, va: int, sections=None) -> int:
    rva = va - IMAGE_BASE
    for s_rva, vsize, raw, raw_size in sections or _sections(exe):
        if s_rva <= rva < s_rva + max(vsize, raw_size):
            return raw + rva - s_rva
    raise ValueError(f"address {va:#x} is not in the executable")


@dataclass(frozen=True)
class GameString:
    id: int
    english: str
    name: str = ""            # Plant Tycoon's own name for the line (eTIME_STOPPED...)


def read_table(game: str, exe: bytes) -> list[GameString]:
    """The game's string table as this executable has it (vanilla or patched)."""
    table = TABLES[game]
    sections = _sections(exe)
    base = _offset(exe, table.address, sections)
    out = []
    for i in range(table.count):
        entry = struct.unpack_from("<4I", exe + b"\0" * 16, base + i * table.stride)
        ident = entry[0]
        text_va = entry[table.english_at // 4]
        english = _read_c_string(exe, _offset(exe, text_va, sections)).decode("cp1252", "replace")
        name = ""
        if table.name_at is not None:
            name = _read_c_string(exe, _offset(exe, entry[table.name_at // 4], sections)).decode("ascii", "replace")
        out.append(GameString(ident, english, name))
    return out


def game_limit(game: str, string: GameString) -> int | None:
    if string.id in BUFFER_IDS[game] or (game == "plant" and string.name.startswith(PLANT_TITLE_PREFIX)):
        return buffer_limit(len(string.english.encode("utf-8")))
    return None


def _notes(game: str, string: GameString, limit: int | None, variant: str = "") -> str:
    parts = []
    if string.name:
        parts.append(string.name)
    template = tfmt.parse_template(string.english)
    for n, conv in enumerate(template.conversions, start=1):
        kind = "number" if conv.is_number else "text"
        parts.append(f"%{n} ({conv.text}) = {kind}")
    if limit is not None:
        parts.append(f"at most {limit} letters (accented letters count 2)")
    if variant:
        parts.append(variant)
    return "; ".join(parts)


def game_entries(game: str, exe_variants: list[tuple[bytes, str]]) -> list[tfmt.Entry]:
    """The game's lines: each id once per distinct English among the given executables
    (the first is the vanilla game; others are patched copies, with what changed them)."""
    seen: dict[tuple[int, str], int] = {}
    order: list[tuple[GameString, str]] = []
    for exe, label in exe_variants:
        for s in read_table(game, exe):
            if s.id in NEVER_TRANSLATED[game] or not s.english.strip():
                continue
            if (s.id, s.english) in seen:
                continue
            seen[(s.id, s.english)] = len(order)
            order.append((s, label))
    order.sort(key=lambda item: (item[0].id, seen[(item[0].id, item[0].english)]))
    entries = []
    for s, label in order:
        limit = game_limit(game, s)
        entries.append(tfmt.Entry(tfmt.make_key("strings", str(s.id), s.english), s.english,
                                  _notes(game, s, limit, label), limit or ABSOLUTE_MAX))
    return entries


# --------------------------------------------------------------------------- patcher DLLs


@dataclass(frozen=True)
class ModString:
    game: str
    dll: str                     # file name in "<Game> Fix Patcher DLLs"
    english: str
    limit: int | None = None     # bytes (ANSI) or UTF-16 units (wide); None: ABSOLUTE_MAX
    wide: bool = False           # a UTF-16 text (Windows popups)
    note: str = ""
    patch: str = ""              # the setting (manifest id) it belongs to; "": its DLL's (DLL_PATCH)
    counted: bool = False        # a text with numbers its DLL asks Translations.dll for (COUNTED_STRINGS)

    @property
    def slug(self) -> str:
        return dll_slug(self.dll)


def dll_slug(dll: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", dll.lower().removesuffix(".dll")).strip("_")


def _text_slug(english: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "_", english.lower()).strip("_")
    return (words[:40].rstrip("_") or "text")


GAME_RULE = -1   # a ModString limit of GAME_RULE: the game's buffer rule (buffer_limit of the English)

_F, _P = "fish", "plant"
_COUNTS_F, _COUNTS_P = "Tank Counts.dll", "Greenhouse Counts.dll"
_DS, _PRICES = "DS Store Items.dll", "Optimize Prices.dll"
_UP = "Store Upgrades and Items.dll"


def _m(game, dll, english, limit=None, wide=False, note="", patch=""):
    return ModString(game, dll, english, limit, wide, note, patch)


# The setting (manifest id) each DLL's texts belong to: the editor groups the lines by the
# setting's name. PATCH_OF names the texts of a DLL that belong to another setting.
DLL_PATCH = {
    ("fish", "Tank Counts.dll"): "tank_greenhouse_counts",
    ("fish", "DS Exclusive Fish.dll"): "ds_fish",
    ("fish", "DS Store Items.dll"): "ds_store",
    ("fish", "Extra Tanks.dll"): "extra_tanks",
    ("fish", "Extra Supply Slots.dll"): "extra_supply_slots",
    ("fish", "Optimize Prices.dll"): "optimize_prices",
    ("plant", "Greenhouse Counts.dll"): "tank_greenhouse_counts",
    ("plant", "Extra Chemical Slots.dll"): "extra_chemical_slots",
    ("plant", "Extra Greenhouses.dll"): "extra_greenhouses",
    ("plant", "Optimize Prices.dll"): "optimize_prices",
    ("plant", "Sort Seeds.dll"): "sort_seeds",
    ("plant", "Extra Seed Boxes.dll"): "plant_upgrades",
    ("plant", "Store Upgrades and Items.dll"): "plant_upgrades",
    ("plant", "Unused Flowers.dll"): "new_flowers",
}

PATCH_OF: dict[tuple[str, str, str], str] = {}


def _texts_of(setting: str, game: str, dll: str, *texts: str) -> None:
    for t in texts:
        PATCH_OF[(game, dll, t)] = setting


_texts_of("time_warp", "fish", "DS Store Items.dll", "Time Warp", "Skip ahead in time! Choose how many\nhours (1-72) "
          "pass, as if you had been\naway that long. Your fish age, eat and\nresearch goes on.",
          "Please type a whole number of hours from 1 to 72.", "How many hours should pass? (1-72)", "OK", "Cancel",
          "Time is stopped. Turn time back on in Options, then warp.",
          "Open a tank first, then come back to the store to warp.")
_texts_of("add_money", "fish", "DS Store Items.dll", "Add $1,000",
          "A pile of gold coins! Each one you buy\nadds $1,000 to your money.\nBuy as many as you like.")
_texts_of("extra_tanks", "fish", "DS Store Items.dll", "Extra Tank",
          "Another tank for breeding! Each one\nyou buy opens the next of Tank 4,\nTank 5 and Tank 6.")
_texts_of("extra_supply_slots", "fish", "DS Store Items.dll", "Extra Supply Slots",
          "Seven more supply slots for medicine,\nchemicals and eggs, on two more pages.\nThe arrows beside the slots "
          "turn the\npage. One purchase opens all seven.")
_texts_of("time_warp", "plant", "Store Upgrades and Items.dll", "Time Warp\nPrice: $ %i", "Time Warp",
          "Please type a whole number of hours from 1 to 72.", "How many hours should pass? (1-72)", "OK", "Cancel",
          "Time is stopped. Turn time back on in Options, then warp.",
          "You can't afford to buy this yet! A Time Warp costs $500.")
_texts_of("add_money", "plant", "Store Upgrades and Items.dll", "Add $1,000\nPrice: $ %i", "Add $1,000",
          "You can't afford to buy this yet! +$1,000 costs $950.", "Buy +$1,000 for $%d?")
_texts_of("extra_greenhouses", "plant", "Store Upgrades and Items.dll", "Extra Greenhouse",
          "You already have all five extra greenhouses!",
          "You can't afford to buy this yet! An extra greenhouse costs $10,000.",
          "Buy Greenhouse %d for $%d?\n\nIt has 15 empty pots. The arrows on the greenhouse screen lead to it.")
_texts_of("extra_nurseries", "plant", "Store Upgrades and Items.dll", "Extra Nursery",
          "You already have all five extra nurseries!", "You can't afford to buy this yet! An extra nursery costs "
          "$10,000.", "Buy Nursery %d for $%d?\n\nIt holds 15 more plants for sale. The arrows on the nursery "
          "screen lead to it.")
_texts_of("extra_chemical_slots", "plant", "Store Upgrades and Items.dll", "Extra Chemical Slots\nSold out",
          "Extra Chemical Slots\nPrice: $ %i", "You already have the extra chemical slots!",
          "You can't afford to buy this yet! The extra chemical slots cost $10,000.", "Extra Chemical Slots",
          "Buy the extra chemical slots for $%d?\n\nA gold arrow in the greenhouse's Tools box turns to a second "
          "page of 8 chemical slots.")
_texts_of("extra_nurseries", "plant", "Extra Greenhouses.dll", "Nursery")



# Texts with numbers whose words depend on the number ("2 doses left"): the DLL asks
# Translations.dll (FtfpTranslateCounted, native/common/translated_count.h) with the real numbers,
# so a translation's choices ({%1: one=... | few=... | other=...}) pick the right form. The
# English is the key's, choices and all; the limit leaves room for the numbers in the DLL's buffer
# (the runtime also refuses anything that does not fit). Without a translation the DLL writes its
# English exactly as before, from the pieces in COUNTED_FALLBACKS.
_TW_DONE = ("Time Warp done: %d {%1: one=hour | other=hours} played (%d {%2: one={unit} | other={units}}). "
            "$%d paid.")
_TW_ASK = ("Warp %d {%1: one=hour | other=hours} for $%d?\n\nYour {what} will age %d {%3: one=hour | "
           "other=hours}, as if you had been away that long. This cannot be undone.")
_NURSERY = ("This plant was for sale when it died, but your {which} full: only %d plants can be for sale at once, "
            "counting every greenhouse.\n\nIt is alive again, not for sale. Make room in the nursery, then put it "
            "on sale again.")
_EG_FULL = "Your {which} full!\n\nOnly %d plants can be for sale at once,\ncounting every greenhouse."


def _c(game, dll, english, limit, wide=False, note="", patch=""):
    return ModString(game, dll, english, limit, wide, note, patch, True)


COUNTED_STRINGS: tuple[ModString, ...] = (
    *(_c(_F, _COUNTS_F, t, 40, note="one part of the bracket, '(8 adults, 3 teens, 1 baby)'") for t in (
        "%d {%1: one=adult | other=adults}", "%d {%1: one=teen | other=teens}", "%d {%1: one=baby | other=babies}")),
    *(_c(_F, _DS, t, 48, note="under a supply's name in its slot's tooltip") for t in (
        "%d {%1: one=batch | other=batches} left", "%d {%1: one=use | other=uses} left",
        "%d {%1: one=dose | other=doses} left")),
    _c(_F, _DS, "Costs $%d. Your fish age, eat and breed, and research goes on, as if you had been away.", 220, True,
       "the question above the hours", "time_warp"),
    _c(_F, _DS, _TW_ASK.replace("{what}", "fish"), 220, True, "%1 and %3 = hours, %2 = the price", "time_warp"),
    _c(_F, _DS, _TW_DONE.replace("{unit}", "age step").replace("{units}", "age steps"), 125, True,
       "%1 = hours, %2 = the fish's age steps, %3 = the price", "time_warp"),
    _c(_F, _PRICES, "%d {%1: one=price | other=prices} set.", 36, note="after Optimize Prices or Max Prices"),
    # ---------------------------------------------------------------- Plant Tycoon
    *(_c(_P, _COUNTS_P, t, 40, note="one part of the bracket, '(3 mature, 2 with buds, 1 seedling)'") for t in (
        "%d mature", "%d with buds", "%d {%1: one=seedling | other=seedlings}")),
    _c(_P, "Extra Chemical Slots.dll", "%d {%1: one=dose | other=doses} left", 40,
       note="under the chemical's name in its slot's tooltip"),
    _c(_P, _PRICES, "%d {%1: one=price | other=prices} set.", 36, note="after Optimize Prices or Max Prices"),
    *(_c(_P, "Extra Greenhouses.dll", _EG_FULL.replace("{which}", w), 140, patch="extra_nurseries",
         note="%1 = how many plants can be for sale") for w in ("nursery is", "nurseries are")),
    _c(_P, _UP, "Costs $%d. Your plants grow, ripen seeds and need water, and the seed shop restocks if due, as if "
                "you had been away.", 220, True, "the question above the hours", "time_warp"),
    _c(_P, _UP, _TW_ASK.replace("{what}", "plants"), 220, True, "%1 and %3 = hours, %2 = the price", "time_warp"),
    _c(_P, _UP, _TW_DONE.replace("{unit}", "age unit").replace("{units}", "age units"), 125, True,
       "%1 = hours, %2 = the plants' age units, %3 = the price", "time_warp"),
    *(_c(_P, _UP, _NURSERY.replace("{which}", w), 240, True, "a Revival Potion's popup; %1 = how many plants can "
         "be for sale") for w in ("nursery is", "nurseries are")),
)

# The English pieces a DLL still holds to write a counted text when there is no translation:
# (game, DLL, piece) -> the counted text that translates it (tests/test_translation_coverage.py).
COUNTED_FALLBACKS: dict[tuple[str, str, str], str] = {}


def _fallback(game: str, dll: str, counted: str, *pieces: str) -> None:
    for piece in pieces:
        COUNTED_FALLBACKS[(game, dll, piece)] = counted


for _w in ("adult", "teen", "baby"):
    _fallback(_F, _COUNTS_F, next(c.english for c in COUNTED_STRINGS if c.dll == _COUNTS_F and f"={_w}" in c.english),
              _w, {"adult": "adults", "teen": "teens", "baby": "babies"}[_w])
_fallback(_F, _DS, "%d {%1: one=batch | other=batches} left", " batch left", " batches left")
_fallback(_F, _DS, "%d {%1: one=use | other=uses} left", " use left", " uses left")
_fallback(_F, _DS, "%d {%1: one=dose | other=doses} left", " dose left", " doses left")
_fallback(_F, _DS, _TW_ASK.replace("{what}", "fish"), "Warp %d hour%s for $%d?\n\nYour fish will age %d hour%s, "
          "as if you had been away that long. This cannot be undone.")
_fallback(_F, _DS, _TW_DONE.replace("{unit}", "age step").replace("{units}", "age steps"),
          "Time Warp done: %d hour%s played (%d %s%s). $%d paid.", "age step")
_fallback(_F, _PRICES, "%d {%1: one=price | other=prices} set.", " price set.", " prices set.")
_fallback(_P, _COUNTS_P, "%d mature", "mature")
_fallback(_P, _COUNTS_P, "%d with buds", "with buds")
_fallback(_P, _COUNTS_P, "%d {%1: one=seedling | other=seedlings}", "seedling", "seedlings")
_fallback(_P, "Extra Chemical Slots.dll", "%d {%1: one=dose | other=doses} left", "dose", "doses",
          "%s\n%d %s left")
_fallback(_P, _PRICES, "%d {%1: one=price | other=prices} set.", " price set.", " prices set.")
_fallback(_P, "Extra Greenhouses.dll", _EG_FULL.replace("{which}", "nursery is"), "Your nursery is full!\n\nOnly ",
          " plants can be for sale at once,\ncounting every greenhouse.")
_fallback(_P, "Extra Greenhouses.dll", _EG_FULL.replace("{which}", "nurseries are"),
          "Your nurseries are full!\n\nOnly ")
_fallback(_P, _UP, _TW_ASK.replace("{what}", "plants"), "Warp %d hour%s for $%d?\n\nYour plants will age %d "
          "hour%s, as if you had been away that long. This cannot be undone.")
_fallback(_P, _UP, _TW_DONE.replace("{unit}", "age unit").replace("{units}", "age units"),
          "Time Warp done: %d hour%s played (%d %s%s). $%d paid.", "age unit")
_fallback(_P, _UP, _NURSERY.replace("{which}", "nursery is"), "This plant was for sale when it died, but your %s "
          "full: only %d plants can be for sale at once, counting every greenhouse.\n\nIt is alive again, not for "
          "sale. Make room in the nursery, then put it on sale again.", "nursery is")
_fallback(_P, _UP, _NURSERY.replace("{which}", "nurseries are"), "nurseries are")


MOD_STRINGS: tuple[ModString, ...] = (
    # Tank Counts (built in a bounded 160-byte line, drawn)
    *(_m(_F, _COUNTS_F, t) for t in (
        "Fish: ", " of ", "Dead: ", "Sick: ", "fungus",
        "ick", "Low Health: ", "Creatures: ", "Isolation tank: ", "Counts: On", "Counts: Off",
        "Golden Seahorse", "Magic Pufferfish", "Blue-Spotted Stingray", "Moray Eel")),
    # DS Store Items: names and descriptions (drawn), the supply slots' tooltips (bounded)
    *(_m(_F, _DS, t) for t in (
        "Exotic Fish Eggs", "Radioactive Growth Hormone", "Revival Potion", "ClonaFish", "Muta-Fin", "Muta-Body",
        "Magic Pufferfish", "Blue-Spotted Stingray", "Moray Eel",
        "The puffer fish magically enhances your\nenvironment and the life of your fish.\nComes fully installed.",
        "The sting ray magically enhances your\nenvironment and the life of your fish.\nComes fully installed.",
        "The moray eel magically enhances your\nenvironment and the life of your fish.\nComes fully installed, "
        "with its rock.",
        "These special eggs were extremely hard\nto obtain. Research FISH ENVIRONMENT\nbefore you try to hatch "
        "these.",
        "Time Warp",
        "Skip ahead in time! Choose how many\nhours (1-72) pass, as if you had been\naway that long. Your fish "
        "age, eat and\nresearch goes on.",
        "Add $1,000",
        "A pile of gold coins! Each one you buy\nadds $1,000 to your money.\nBuy as many as you like.",
        "This magical potion instantly revives\ndead fish and restores them to full\nhealth. Contains 3 doses.",
        "A wonder drug that instantly clones all\nfish in the tank. Make sure there's\nenough space in the tank!\n"
        "Contains 3 doses.",
        "Extra Tank",
        "Another tank for breeding! Each one\nyou buy opens the next of Tank 4,\nTank 5 and Tank 6.",
        "Auto-Feeder", "Automatically feeds all your fish in\nevery tank. No more starvation, ever!",
        "Auto-Healer",
        "Magically cures all diseases from fish\nand restores them to full health.\nWorks in every tank.",
        "Extra Supply Slots",
        "Seven more supply slots for medicine,\nchemicals and eggs, on two more pages.\nThe arrows beside the "
        "slots turn the\npage. One purchase opens all seven.",
        "Mutates the fins of fish.\nContains 3 doses.", "Mutates the bodies of fish.\nContains 3 doses.",
        "Fish Food", "Golden Seahorse", "Owned. Click it again to unpurchase.")),
    _m(_F, _DS, "Treated: $", 36, note="'Treated: $475' under a price, in a 48-letter space"),
    *(_m(_F, _DS, t, wide=True) for t in (
        "Time Warp", "Please type a whole number of hours from 1 to 72.", "How many hours should pass? (1-72)",
        "OK", "Cancel", "Time is stopped. Turn time back on in Options, then warp.",
        "Open a tank first, then come back to the store to warp.")),
    _m(_F, _DS, "Unpurchase ", 60, True, "followed by the machine's name and the next line"),
    _m(_F, _DS, "? It switches off. There is no refund, and buying it again costs the full price.", 170, True),
    # Extra Tanks, Extra Supply Slots (hints, drawn)
    _m(_F, "Extra Tanks.dll", "You don't own this tank yet!"),
    _m(_F, "Extra Supply Slots.dll", "You don't own the extra supply slots yet!"),
    # Optimize Prices (the game's own message box; the count in a 48-letter space)
    _m(_F, _PRICES, "Set every discovered species\nto its best price per day?"),
    _m(_F, _PRICES, "Set every discovered species\nto its highest selling price?\nFish at this price sell\n"
                    "much more slowly."),

    # ---------------------------------------------------------------- Plant Tycoon
    *(_m(_P, _COUNTS_P, t) for t in (
        " of ", "Plants: ", "Dead: ", "Infested: ", "Unhealthy: ",
        "Counts: On", "Counts: Off")),
    _m(_P, "Extra Greenhouses.dll", "Greenhouse ", 40, note="then the greenhouse's number"),
    _m(_P, "Extra Greenhouses.dll", " is full!\n\nThere is no empty pot to move\nthis plant to.", 110),
    _m(_P, "Extra Greenhouses.dll", "Greenhouse", 24, note="the screen's name: 'Greenhouse 2 of 3'"),
    _m(_P, "Extra Greenhouses.dll", "Nursery", 24, note="the screen's name: 'Nursery 2 of 3'"),
    _m(_P, _PRICES, "Set every discovered species\nto its best price per day?"),
    _m(_P, _PRICES, "Set every discovered species\nto its highest selling price?\nPlants at this price sell\n"
                    "much more slowly."),
    _m(_P, "Sort Seeds.dll", "Sort Seeds in Seed Boxes?\n\nThis will rearrange all seeds throughout\nyour available "
                             "seed boxes. Some may move\nto other pages.\nClick YES to Confirm, NO to Cancel."),
    *(_m(_P, "Extra Seed Boxes.dll", t) for t in ("Boxes 1-3", "Boxes 4-6", "Boxes 7-9")),
    # Store Upgrades and Items: titles (into 64-letter tooltips), names (the game's chemical
    # names), descriptions (drawn), the tooltips' formats
    *(_m(_P, _UP, t, 40, note="the store's title line") for t in (
        "Legendary Seeds\n", "Radioactive Plant Formula\n", "Revival Potion\n", "Revita-Seed\n",
        "Radioactive Plant Formula Bomb\n", "Muta-Flower\n", "Muta-Foliage\n")),
    *(_m(_P, _UP, t, GAME_RULE, note="the chemical's name") for t in (
        "Radioactive Plant Formula", "Revival Potion", "Revita-Seed", "Radioactive Plant Formula Bomb",
        "Muta-Flower", "Muta-Foliage")),
    *(_m(_P, _UP, t) for t in (
        "These ultra-rare seeds were only recently\nrediscovered on Isola and require the\nbest of care to survive.",
        "This magical potion instantly revives\ndead plants and restores them to full\nhealth. Contains 3 doses.\n",
        "Revitalizes depleted plants so they\ncan produce more seeds.\nContains 3 doses.\n",
        "Mutates the flowering parts of plants.\nContains 3 doses.\n",
        "Mutates the leafy parts of plants.\nContains 3 doses.\n")),
    _m(_P, _UP, "%sPrice: $ %i", 16, note="%1 = the title, %2 = number"),
    _m(_P, _UP, "Extra Seed Box", 14), _m(_P, _UP, "Extra Greenhouse", 16), _m(_P, _UP, "Extra Nursery", 13),
    _m(_P, _UP, "%s\nSold out", 11), _m(_P, _UP, "%s %i of %i\nPrice: $ %i", 24),
    _m(_P, _UP, "Automatic Sprinklers", 40), _m(_P, _UP, "Auto-Healer", 40),
    _m(_P, _UP, "%s\nOwned, click to unpurchase", 40), _m(_P, _UP, "%s\nPrice: $ %i", 40),
    _m(_P, _UP, "Extra Chemical Slots\nSold out", 50), _m(_P, _UP, "Extra Chemical Slots\nPrice: $ %i", 50),
    _m(_P, _UP, "Time Warp\nPrice: $ %i", 50), _m(_P, _UP, "Add $1,000\nPrice: $ %i", 50),
    _m(_P, _UP, "Treated: $%d", 20),
    *(_m(_P, _UP, t, wide=True) for t in (
        "Time Warp", "Please type a whole number of hours from 1 to 72.", "How many hours should pass? (1-72)",
        "OK", "Cancel", "Time is stopped. Turn time back on in Options, then warp.",
        "You can't afford to buy this yet! A Time Warp costs $500.",
        "You already have all five extra greenhouses!",
        "You can't afford to buy this yet! An extra greenhouse costs $10,000.",
        "You already have all five extra nurseries!",
        "You can't afford to buy this yet! An extra nursery costs $10,000.",
        "You can't afford to buy this yet! +$1,000 costs $950.",
        "You already have the extra chemical slots!",
        "You can't afford to buy this yet! The extra chemical slots cost $10,000.",
        "You already have all six extra seed boxes!", "You already have all three extra seed boxes!",
        "You can't afford to buy this yet! An extra seed box costs $1,000.")),
    *(_m(_P, _UP, t, 60, True, "a popup's title") for t in (
        "Extra Greenhouse", "Extra Nursery", "Automatic Sprinklers", "Auto-Healer", "Revival Potion",
        "Add $1,000", "Extra Chemical Slots", "Extra Seed Box")),
    *(_m(_P, _UP, t, 20, True, "'the Fourth Seed Box'") for t in (
        "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth")),
    _m(_P, _UP, "Automatically waters all pots in the greenhouse. Optimizes water levels for minimal pest "
                "infestations and problems.", 200, True),
    _m(_P, _UP, "Magically cures all diseases from plants and restores them to full health. Works in every "
                "greenhouse.", 200, True),
    _m(_P, _UP, "Buy Greenhouse %d for $%d?\n\nIt has 15 empty pots. The arrows on the greenhouse screen lead to "
                "it.", 200, True, "%1 = number, %2 = number"),
    _m(_P, _UP, "Buy Nursery %d for $%d?\n\nIt holds 15 more plants for sale. The arrows on the nursery screen "
                "lead to it.", 200, True, "%1 = number, %2 = number"),
    _m(_P, _UP, "Buy +$1,000 for $%d?", 100, True),
    _m(_P, _UP, "Unpurchase %s? It switches off. There is no refund, and buying it again costs the full price.",
       300, True, "%1 = the machine's name"),
    _m(_P, _UP, "You can't afford to buy this yet! %s costs $10,000.", 300, True, "%1 = the machine's name"),
    _m(_P, _UP, "Buy %s for $%d?\n\n%s", 100, True, "%1 = the machine's name, %2 = number, %3 = its description"),
    _m(_P, _UP, "Buy the extra chemical slots for $%d?\n\nA gold arrow in the greenhouse's Tools box turns to a "
                "second page of 8 chemical slots.", 200, True),
    _m(_P, _UP, "Buy the %s Seed Box for $%d?\n\nEven more space for your seeds! It opens a 40-seed drawer in "
                "Seed Storage (Boxes %s).", 180, True, "%1 = Fourth...Ninth, %2 = number, %3 = 4-6 or 7-9"),

    # ---------------------------------------------------------------- added in v1.0.25 (every patch)
    # New entries go here, after the older ones: a text's id is numbered "_2"... in this order.
    # DS Exclusive Fish: the parts of a DS species' name, "<fin><body>" ("Tiger Shark"), copied into
    # the species' 32-letter name (bounded): fin at most 15, body at most 16, so both always fit.
    *(_m(_F, "DS Exclusive Fish.dll", t, 15, note="the first part of a DS species' name, e.g. 'Tiger ' in "
                                                    "'Tiger Shark' (keep the space at the end)") for t in (
        "Silky ", "Tiger ", "Hornet ", "Fanned ", "Pink ", "Snubbed ", "Wasp ", "Canary ", "Orange ", "Oriental ",
        "Golden ", "Crimson ", "Spined ", "Stubby ", "Speckled ", "Razorback ", "Greenfin ", "Great-Sail ",
        "Flagged ", "Finless ", "Twin-Fin ", "Small-Fin ", "Roundy ", "Angel ", "Clown ", "Yellow ", "Blue ",
        "Moorish ")),
    *(_m(_F, "DS Exclusive Fish.dll", t, 16, note="the last part of a DS species' name, e.g. 'Shark' in "
                                                    "'Tiger Shark'") for t in (
        "Shark", "Catfish", "Arrowfish", "Snout", "Fatfish", "Snooper", "Goldshark", "Fire-Arrow", "Fruitfish",
        "Flashfish", "Goldbulb", "Comet", "Stickfish", "Grouper", "Leaffish", "Carp", "Beta", "Pigmy", "Bananafish",
        "Quicksilver", "Spotanus", "Clownfish", "Discus", "Bicolor", "Trigger", "Surgeonfish", "Tang", "Idle")),
    _m(_F, _DS, "Every fish in your tank gets full health and\nno sickness, young ones grow up at once, and\n"
                "pregnant ones give birth to babies. Allows\ntreated fish to sell at max price, regardless\nof "
                "their set value. Contains 3 doses."),
    # Store Upgrades and Items: the formula's and the bomb's descriptions (drawn)
    _m(_P, _UP, "Causes maximum flower and plant growth\nand restores full health to plants.\nNo more dead leaves! "
                "Always 5 seeds! Allows\ntreated plants to sell at max price, regardless\nof their set value. "
                "Contains 3 doses.\n"),
    _m(_P, _UP, "The Radioactive Plant Formula for\nevery plant in the greenhouse.\nAllows treated plants to sell "
                "at max\nprice, regardless of their set value.\nContains 3 doses.\n"),
    # Unused Flowers: the new species' names, "<flower> <foliage>" ("Nightingale Fern"), built into a
    # 96-letter name (bounded) when the translation is applied
    *(_m(_P, "Unused Flowers.dll", t, 24, note="the first word of a new flower's species name, e.g. "
                                                 "'Nightingale' in 'Nightingale Fern'") for t in (
        "Nightingale", "Rosetta", "Lilac", "Veronica", "Violetta", "Stella", "Silvermist", "Anagallis", "Buttercup",
        "Cerulean", "Phalaena", "Mirabilis", "Indigoberry", "Prunus")),
    *(_m(_P, "Unused Flowers.dll", t, 24, note="the second word of a new flower's species name, e.g. 'Fern' in "
                                                 "'Nightingale Fern' (only the new flowers' names use it)") for t in (
        "Reptans", "Scandens", "Grass", "Orchid", "Astera", "Gladiatus", "Fern", "Ananas", "Maranta", "Fanleaf",
        "Lemonbush", "Bamboo", "Maple", "Rare Oak", "Pipe Cactus", "Pear Cactus", "Ball Cactus", "Glaber",
        "Tigerfern", "Pitcher", "Weeper", "Multiflora", "Ridgeball")),
    *COUNTED_STRINGS,
)


def mod_limit(m: ModString) -> int:
    if m.limit == GAME_RULE:
        return buffer_limit(len(m.english.encode("utf-8")))
    return ABSOLUTE_MAX if m.limit is None else m.limit


def _plain(english: str) -> str:
    """A counted text's words for its id: each choice as its "other" branch, each %d as "n"."""
    text = re.sub(r"\{%\d+:[^{}]*\bother=([^|{}]*)\}", lambda m: m.group(1).strip(), english)
    return re.sub(r"%[di]", "n", text)


def _mod_ids() -> dict[tuple[str, str, str, bool], str]:
    """Each DLL text's id: "<dll>.<words>" ("<dll>.w.<words>" for a popup's text), numbered
    "_2", "_3"... when two texts of one DLL start with the same words (in MOD_STRINGS order)."""
    ids: dict[tuple[str, str, str, bool], str] = {}
    taken: set[tuple[str, str]] = set()
    for m in MOD_STRINGS:
        ident = (m.game, m.dll, m.english, m.wide)
        if ident in ids:
            continue
        stem = f"{m.slug}.{'w.' if m.wide else ''}{_text_slug(_plain(m.english) if m.counted else m.english)}"
        name, n = stem, 1
        while (m.game, name) in taken:
            n += 1
            name = f"{stem}_{n}"
        taken.add((m.game, name))
        ids[ident] = name
    return ids


_MOD_IDS = _mod_ids()


def mod_key(m: ModString) -> str:
    return tfmt.make_key("mod", _MOD_IDS[(m.game, m.dll, m.english, m.wide)], m.english)


_SETTING_NAMES: dict[str, dict[str, str]] = {}


def setting_name(game: str, setting: str) -> str:
    """A setting's name as the patcher shows it (data/<game>_manifest.json)."""
    if game not in _SETTING_NAMES:
        import json
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
        _SETTING_NAMES[game] = {x["id"]: x.get("name", x["id"]) for x in manifest.get("settings", [])}
    return _SETTING_NAMES[game].get(setting, setting)


def patch_of(m: ModString) -> str:
    """The setting (manifest id) a DLL text belongs to."""
    return m.patch or PATCH_OF.get((m.game, m.dll, m.english)) or DLL_PATCH[(m.game, m.dll)]


PATCH_NOTE = "Patch: "        # notes start "Patch: <setting>"; the editor groups the lines by it


def group_of(notes: str) -> str:
    """The editor's group for a line, from its notes: the patch's name, or "" for the game's own."""
    for part in (notes or "").split("; "):
        if part.startswith(PATCH_NOTE):
            return part[len(PATCH_NOTE):].strip()
    return ""


def mod_entries(game: str) -> list[tfmt.Entry]:
    """The patcher DLLs' lines, grouped by patch (the settings' order in the manifest)."""
    entries = []
    seen = set()
    for m in MOD_STRINGS:
        if m.game != game:
            continue
        key = mod_key(m)
        if key in seen:
            continue
        seen.add(key)
        limit = mod_limit(m)
        note = [PATCH_NOTE + setting_name(game, patch_of(m)), f"{m.dll}" + (" (Windows popup)" if m.wide else "")]
        template = tfmt.parse_template(m.english)
        for n, conv in enumerate(template.conversions, start=1):
            note.append(f"%{n} ({conv.text}) = {'number' if conv.is_number else 'text'}")
        if m.note:
            note.append(m.note)
        if m.limit is not None:
            note.append(f"at most {limit} letters" + ("" if m.wide else " (accented letters count 2)"))
        if template.conversions:
            note.append("choices use the real numbers" if m.counted else "choices here always take o / other")
        entries.append(tfmt.Entry(key, m.english, "; ".join(note), limit, m.wide))
    order = list(_setting_order(game))
    rank = {name: k for k, name in enumerate(order)}
    entries.sort(key=lambda e: rank.get(group_of(e.notes), len(order)))
    return entries


def _setting_order(game: str):
    setting_name(game, "")
    return _SETTING_NAMES[game].values()


# --------------------------------------------------------------------------- everything


def patched_variants(game: str, vanilla: bytes) -> list[tuple[bytes, str]]:
    """The vanilla game, and the game with each setting's patches alone: every English the
    patcher can make. Only settings that change a string table text are kept."""
    import json
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "data" / f"{game}_manifest.json").read_text(encoding="utf-8"))
    if game == "fish":
        import fish_patcher as patcher
    else:
        import plant_patcher as patcher  # type: ignore[no-redef]
    variants = [(vanilla, "")]
    base = {s.id: s.english for s in read_table(game, vanilla)}
    for setting in manifest.get("settings", []):
        try:
            records = patcher.active_patch_records(manifest, {setting["id"]})
            patched, _ = patcher.apply_patch_bytes(vanilla, records)
            changed = [s for s in read_table(game, patched) if base.get(s.id) != s.english]
        except Exception:
            continue
        if changed:
            variants.append((patched, PATCH_NOTE + setting.get("name", setting["id"])))
    return variants


def entries_for(game: str, vanilla_exe: bytes) -> list[tfmt.Entry]:
    """Every line of a translation for this game, in order: the game's, then the DLLs'."""
    return game_entries(game, patched_variants(game, vanilla_exe)) + mod_entries(game)


def find_vanilla_exe(game: str, folders) -> Path | None:
    """The first folder with the game's own (unpatched) executable."""
    for folder in folders:
        if not folder or not str(folder).strip():
            continue
        path = Path(str(folder).strip().strip('"')) / EXE_NAMES[game]
        try:
            if path.is_file() and _is_vanilla(game, path.read_bytes()):
                return path
        except OSError:
            continue
    return None


VANILLA_SHA256 = {
    "fish": "9F15F13537AD0978D1E3AA2F94A64992FB7D968648BF265810087BDC88EDBDCD",
    "plant": "D1F83E3E3CAFE177452E2F8B6AF4B68CACED783B77A304370389375DB611D6F9",
}


def _is_vanilla(game: str, data: bytes) -> bool:
    import hashlib
    return hashlib.sha256(data).hexdigest().upper() == VANILLA_SHA256[game]
