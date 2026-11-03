> **Owner decisions, 2026-11-03 (these override anything below):**
> 1. **Name limit: "All games: up to 1,200".** Every name box takes up to 1,200 bytes as stored, with NO 300-character cap. Wherever this file says "300 characters", read "1,200 bytes", cut at whole clusters. Remove any NAME_LETTERS-style cap that would cut before the byte cap. The counter reads "N / 1200 bytes". Change manifest and docs wording to match.
> 2. **Paste with both Unicode settings off: "What the fonts draw".** Keep only the characters that game's stock fonts can draw, one byte each. Derive the set from the stock font tables and test it. (FP and VV: printable ASCII, since their stock fonts lack the rest.)
> 3. **VF2 Translations DLL and window: in B208.**

# VF1 (Lorsieab2/Virtual-Families-1-Fun-Patcher): what to build

Audited: origin/main 6073731 (PR #71 merged).

VF1 is the spec's source for most rows: the limit written once, real-spot fitting, UAX #14, the "%" rule, the font
picker and the Translations window. Every item below is something to **build**. Nothing is removed.

Game facts (kept out of the spec):
- Fields: family name 19 bytes, slot menu 20, a person's name 24, parents' names 25.
- Ten `SetEditable` name-box calls (`docs/UNICODE_TEXT.md`).
- Sidecar: `<saves>\Virtual Families 1 Patcher Data\Names\Virtual Families<N>.ldw.txt`, header `VF1 Names 1`.
- DLLs: `vf1text.dll` / `vf1font.dll`; Copy and Paste is in `vf1fun.dll` (`clipboard.inc`); Translations is
  `vf1tr`.
- Stock fonts hold 0x21..0x7F and 0xA2..0xFF. Bytes 0x80..0xA1 draw as "!".

## Bugs

1. **bug (low): the Translations DLL decides UTF-8 by DLL presence, not by install.**
   - `native/vf1tr/vf1tr.c:842` sets `text_mode = GetModuleHandleW(L"vf1text.dll") || GetModuleHandleW(L"vf1font.dll")`.
   - `vf1text.dll` installs its six hooks all-or-nothing, so on an exe whose bytes do not match, the DLL is loaded but
     draws bytes, and translations would arrive as UTF-8 mojibake.
   - Fix: export a `VF1Text_UnicodeTextActive()` (stdcall int, nonzero only once the hooks are installed), modelled
     on FP's `FtfpUnicodeTextActive`, and query it.
   - Do the same for `native/vf1fun/clipboard.inc:76` `UnicodeTextOn()`, which tests only that the
     `VF1Text_FullName` export exists.

## Name limit and storage (row 2)

2. **consistency: per-character write rule.**
   - Today every non-ASCII character is stored as UTF-8 (`patcher/vf1_text.py` `encode` / `encode_field`).
   - Build VV's rule: a Windows-1252 character is its one byte, anything else UTF-8, and all UTF-8 when the mix
     would read back differently.
   - The same rule in `native/vf1text/names.inc` (GetText / `ShortFor`), `native/vf1fun/text_names.inc`
     (`StoreTypedName`), `native/vf1fun/clipboard.inc` (`FitNameUtf8`), `patcher/vf1_names.py`,
     `vf1_rename_family.py` and `vf1_copy_slot.py`.
   - Why: "Zoë 日本" keeps a stock-readable ë, and old Latin-1 names keep their bytes.
3. **consistency: per-sequence read rule.**
   - `vf1_text.decode` and the DLL's decode treat a whole string as UTF-8 or as Windows-1252.
   - Build VV's per-sequence decoder (each well-formed sequence as its character, every other byte as
     Windows-1252), so mixed strings from item 2 read correctly.
   - Check `tests/test_vf1_text.py` for strings that change, such as a hand-typed "Ã©".
4. **consistency: the cluster rule gets CR LF as one character** (`vf1_text.clusters`, regenerated into
   `native/vf1text/extenders.inc` by `scripts/build_vf1_text_tables.py`; VF2 `vf2_game_text.clusters`).
5. **consistency: sidecar CRC-32 and pending writes.**
   - Add a CRC-32 column to each record (`short<TAB>room<TAB>whole<TAB>CRC`) under a new header `VF1 Names 2`, and
     keep reading `VF1 Names 1`.
   - Skip a record whose CRC fails.
   - Keep a record pending and retry it while no slot is known or the write failed (VV
     `native/vvfp_unicode_text/long_names.inc`).
   - Files: `patcher/vf1_names.py`, `native/vf1text/names.inc`, `native/vf1logs` (reader).

## Drawing (row 3)

6. **consistency: colour emoji.** `docs/UNICODE_TEXT.md` lists colour emoji as "Not in this part", and GDI draws
   emoji in one colour (`native/vf1text/glyph_gdi.inc`). Build FP's Direct2D/DirectWrite colour path (FP
   `native/common/unicode_glyphs.h` `raster_colour`) for COLR, CBDT, sbix and SVG faces, never tinted, keeping GDI
   as the fallback. Mirror it in `patcher/vf1_glyph_gdi.py` so the Game Text preview matches.
7. **consistency: shaping of complex scripts.** Today Arabic, Hebrew order and Indic shaping are drawn one
   character at a time (`docs/UNICODE_TEXT.md`, "Not in this part"). Build VV's Uniscribe runs
   (`native/vvfp_unicode_text/text_utf8.h` `ut_unit` UT_RUN, `runtime_glyphs.inc`) inside `vf1text.cpp`'s
   per-character loop.
8. **consistency: fallback chain.** Add Meiryo, SimSun-ExtB, Noto Sans CJK SC, Noto Sans Cuneiform and Noto Color
   Emoji to `FallbackFaces[]` (`native/vf1text/glyph_gdi.inc`) and to `patcher/vf1_glyph_gdi.py`, in the spec's
   order.
9. **consistency: wide characters in non-name boxes.** Refuse a typed character that would make a box's text
   wider than the widest stock text (byte limit × widest plain letter); name boxes keep scrolling. From VF2
   `b200unicode.cpp`.

## Typing (row 4)

10. **consistency: a mark typed after a refused character is refused too** (`native/vf1text/vf1text.cpp`, the
    0x40DA70 HandleMessage hook). VF1 does this for a paste (`clipboard.inc`) but not for typing. From VF2
    `b200unicode.cpp` ("A name box whose last typed character was refused").

## Copy and Paste (row 5)

11. **consistency: CR LF becomes one space.** `PasteInto` in `native/vf1fun/clipboard.inc` maps CR and LF each to a
    space, so CR LF becomes two.
12. **consistency: NFC with a Unicode setting on as well.** `Composed()` (FoldStringW MAP_PRECOMPOSED) is used only
    on the both-off path; apply NFC to every paste (VV PR #677).
13. **consistency: swallow a held key's repeats,** and empty on Ctrl+X only after the copy succeeded (check
    `clipboard.inc`; VV PR #677 has both).
14. **owner check: the set with both Unicode settings off.**
    - VF1 keeps U+0020..U+007E and U+00A2..U+00FF, the characters the stock **fonts** can draw.
    - The stock **box** (0x40DB0F) refuses every byte from 0x80.
    - The owner's rule is "each game's stock box set". Strictly read, that is printable ASCII. Confirm which one the
      owner means before changing anything.

## Allowed characters (row 6)

15. ✓ `patcher/vf1_rename_family.py` `printable` rejects only Cc, Cs, Zl, Zp and U+FEFF, so new letters pass. No
    change.

## Translation validator and contract (rows 7, 8)

16. ✓ The "%" rule is the spec's source (`patcher/translation_format.py`). See item 1 for the contract.

## Docs (row 9)

17. **consistency:** after items 2, 6 and 7, update `docs/UNICODE_TEXT.md` ("Storage: UTF-8 in the game's own
    fields", "Not in this part"), the `RenderUnicodeInGameFonts` and `UseUnicodeFont` descriptions in
    `patcher/manifest.json`, and `README.md`, so they say emoji are in colour and describe the per-character write
    rule.

## Tools and the Translations window (row 10)

18. ✓ "Game Text...", "Unicode Font...", and the Translations window (Delete..., multi-select, Download from
    GitHub..., the public folder, "(TEST)" never shipped, VirusTotal) are the spec's source. No change.
