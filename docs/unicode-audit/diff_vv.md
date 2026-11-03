> **Owner decisions, 2026-11-03 (these override anything below):**
> 1. **Name limit: "All games: up to 1,200".** Every name box takes up to 1,200 bytes as stored, with NO 300-character cap. Wherever this file says "300 characters", read "1,200 bytes", cut at whole clusters. Remove any NAME_LETTERS-style cap that would cut before the byte cap. The counter reads "N / 1200 bytes". Change manifest and docs wording to match.
> 2. **Paste with both Unicode settings off: "What the fonts draw".** Keep only the characters that game's stock fonts can draw, one byte each. Derive the set from the stock font tables and test it. (FP and VV: printable ASCII, since their stock fonts lack the rest.)
> 3. **VF2 Translations DLL and window: in B208.**

# VV (Lorsieab2/Virtual-Villagers-Fun-Patcher): what to build

Audited:
- origin/main c62ad648 (#676 merged, shipping in v1.35.89);
- open PR #677 `feat/copy-paste-in-game` at a95ce151 (Copy and Paste in Text Boxes; **not on main yet**).

VV is the spec's source for:
- the per-character write rule and the per-sequence read rule;
- CRC-checked sidecar records with pending writes;
- full-colour COLR emoji;
- Uniscribe shaping runs;
- NFC paste;
- the "?"-name repair.

Every item is something to **build**. Nothing is removed.

Game facts (kept out of the spec):
- Five games.
- Fields: villager name 27 bytes (A New Home) or 23 (the others); tribe name 31 / 19; epitaph 64 / 31.
- Sidecar: `<save folder>\Virtual Villagers Fun Patcher\Save <S>\Data\Long Names\Virtual Villagers <N> Long Names - Save <S>.dat`,
  header `VVFP Long Names v2`.
- DLLs: `VVFP Unicode Text.dll` / `VVFP Unicode Font.dll`, `VVFP Copy and Paste.dll`, `VVFP Translations.dll`.
- Both Unicode settings depend on "Full Names on the Details Screen".
- A New Home's fonts hold only A-Z, a-z, 0-9 and a few signs.

## Bugs

1. **bug: tools reject letters newer than Python's Unicode data.**
   - `src/vv_game_text.py` `printable` returns `unicodedata.category(ch) not in ("Cc","Cs","Co","Cn")`. It is used by
     `src/vv_tribe_rename.py` (lines 202, 311, 477) and `src/vv_save_backup.py:869`.
   - So a Unicode 17 or 18 letter that the game takes and draws is refused, or reported as not printable.
   - Fix: decide by ranges as FP 463539a does, rejecting only NUL, C0/DEL/C1, lone surrogates, U+2028/2029 and
     U+FEFF. Private use and unassigned code points stay allowed, as in VF1 and VF2.

## Settings (row 1)

2. **consistency: build a Tools-tab "Unicode Font..." window.**
   - It offers any installed family with a search, or a .ttf/.otf/.ttc file (copied beside the DLL and loaded with
     `AddFontResourceExW(FR_PRIVATE)`), a preview of each game font as the game will draw it, and Save.
   - Keep the patch-selection "Unicode Font" box and `--unicode-font`. Both write the same choice
     (`src/vv_fun_patcher_gui.py` `unicode_font_var`).
   - Model: VF1 `patcher/vf1_unicode_font.py`.
3. **consistency: Use Unicode Font em fitting.** Check whether `runtime_glyphs.inc` (`g_override_face`) fits the
   chosen face so that the "quick brown fox ..." sentence is as wide as the game font, within 60%..130% (VF1
   `FitChosenFont`). If it does not, build it.
4. **consistency: Copy and Paste in Text Boxes is not on main.** Merge PR #677 (`native/vvfp_copy_paste`,
   `data/vv*_copy_paste_feature.json`), with the items in row 5 below.

## Name limit and storage (row 2)

5. **owner check, then consistency: the 300-character limit.**
   - VV takes 1,200 bytes and has no character count (`VV_SHARED_NAME_BYTES` in
     `native/vvfp_unicode_text/long_names.inc`, `SHARED_NAME_BYTES` in `src/vv_long_names.py`).
   - The shared limit in VF1, VF2 and FP is 300 characters AND 1,200 bytes. VF1 and VF2 say "shared with the other
     Fun Patchers".
   - Building it means plain-ASCII names stop at 300 instead of 1,200. Confirm with the owner, since the rule is
     "don't remove".
   - If confirmed:
     - count grapheme clusters in typing (`text_hooks.inc` box insert), in paste (`VvfpBoxInsertUtf8`, PR #677)
       and in the tools;
     - write `NAME_LETTERS` / `NAME_BOX_BYTES` once in Python and generate the C header, instead of the two copies
       today (VF1 `scripts/build_vf1_text_tables.py`).
6. **consistency: the short-form mark.**
   - VV writes `\x85` (`…`) and then a number (`Alexandria Montg…2`).
   - The spec takes `...` with the number first (`2...`), because ASCII dots draw in every stock font. The stock
     VF1 and VF2 fonts lack 0x85, and A New Home's fonts have no "…".
   - New short forms use `...` / `2...` (`native/vvfp_unicode_text/long_names.inc` around line 275, and
     `src/vv_long_names.py`). Old `…` records and short forms stay readable forever (`ln_` lookup line 355 already
     accepts both 0x85 and E2 80 A6).
7. **consistency: the sidecar.**
   - Add the `room` column (the field's bytes): `short<TAB>room<TAB>whole<TAB>CRC` under a `v3` header, still
     reading `v2`.
   - The file write uses `.tmp` + `MoveFileEx(REPLACE|WRITE_THROUGH)` (FP, VF1, VF2), alongside VV's CRC and
     pending records. Today VV appends one line per write.
   - Skip records with no mark, too long for their room, or holding a control character.
8. **consistency: Rename Tribe writes the long name.**
   - `src/vv_tribe_rename.py` takes at most 63 characters (`len(new) > 63`, line 477) and never writes a Long Names
     record.
   - Build: 300 characters / 1,200 bytes, the short form in the field, the record in the sidecar, and an undo on
     failure (VF1 `vf1_rename_family.py`).
   - Check that Copy Player Slot renames the Long Names file with the slot. `src/vv_copy_slot.py` copies `Save <S>`
     and re-keys names, so it most likely does.
9. **consistency: the cluster rule.**
   - `src/vv_game_text.py` `_extends` lacks **Mc** (spacing marks such as Devanagari ा) and CR LF.
   - Use the shared table (Mn/Mc/Me, ZWNJ, ZWJ + next, VS, skin tones, tags, RI pairs, CR LF) in Python and in
     `native/vvfp_unicode_text/unicode_text_tables.h` / `text_utf8.h`.

## Drawing (row 3)

10. **consistency: fit names to each fixed spot's real width with "…".** VV has no width fitting. Build VF1's
    `DrawSpots` / `LabelSpots`: measure every fixed spot where a villager or tribe name is drawn (Details screen,
    labels, map names, log headers shown in the game) and fit to it.
11. **consistency: full UAX #14.**
    - VV breaks between CJK characters and has a short kinsoku list (`text_utf8.h` `ut_no_break_before` /
      `ut_no_break_after`).
    - Build VF1's `ubrk_open(UBRK_LINE)` via System32 `icu.dll`, with the built-in table as the fallback, for Thai,
      Lao, Khmer, Myanmar, Hangul and emoji.
    - Keep the long-word cut and ASCII pixel-identical.
    - Keep VV's "a justified CJK paragraph finishes its line", which the spec adopts.
12. **consistency: colour emoji in every colour format.**
    - VV renders COLR/CPAL layers only (`runtime_glyphs.inc` `rg_colr`), but its chain includes **Noto Color Emoji,
      which is CBDT**: its glyphs get no colour.
    - Add FP's Direct2D/DirectWrite path for CBDT, sbix and SVG, keeping VV's COLR renderer.
13. **consistency: fallback chain.** Add Meiryo, Microsoft JhengHei, SimSun-ExtB, Gadugi, Leelawadee UI, Myanmar
    Text, Javanese Text, Mongolian Baiti, Microsoft Himalaya, Yi Baiti, New Tai Lue, Tai Le, PhagsPa, Sylfaen,
    Cambria Math, Noto Sans Symbols, Noto Sans CJK SC and Noto Sans Math to `RG_CHAIN[]`
    (`runtime_glyphs.inc:106`), in the spec's order.
14. **consistency: wide characters in non-name boxes are refused** beyond the widest stock text (VF2).
15. **consistency: composed drawing.** Check that a base letter plus combining marks is drawn as its precomposed
    letter (`NormalizeString` C) where one exists (VF1); otherwise as a cluster.

## Typing (row 4)

16. **consistency: a mark typed after a refused character is refused too** (`text_hooks.inc`; VF2
    `b200unicode.cpp`).

## Copy and Paste (row 5, PR #677)

17. **consistency: read cap of 8,192 UTF-16 units.** `CP_MAX_UNITS` is 4096 (`native/vvfp_copy_paste/vvfp_copy_paste.c`).
    Check that the read is bounded by `GlobalSize` as well as by the first NUL.
18. **consistency: name boxes cut at 300 characters** over box text + paste (after item 5), and a joining mark that
    no longer fits is not pasted (VF1 `clipboard.inc`).
19. ✓ CR LF as one space, NFC, "dropped, never '?'", printable ASCII with no Unicode companion (the owner's "stock
    box set"), repeats swallowed, cut only after a successful copy. No change.

## Allowed characters (row 6)

20. See bug 1.

## Translation validator (row 7)

21. **consistency: VF1's "%" rule.**
    - `src/vv_translation_format.py` (lines 815-819) refuses any "%" in a line whose English has none ("write the
      word for percent instead"), so French "50 %" fails.
    - Port VF1 `patcher/translation_format.py` `Source` / `token_at` (a "%" is a placeholder only when the English
      has that token), `Entry.is_format`, and `runtime_text` writing `%%` in format lines. Mirror it in
      `native/vvfp_translations`.

## Contract (row 8)

22. ✓ `VvfpGlyphsUtf8` (asked by `vvfp_translations.c:2362` and by Copy and Paste) is the equivalent of
    `FtfpUnicodeTextActive`. Check that it returns 1 only once the hooks are installed, not merely when the DLL is
    loaded.

## Docs (row 9)

23. **consistency:** use the spec's release-note paragraph and "characters" wording in
    `data/vv*_unicode_text_feature.json`, `data/vv*_unicode_font_feature.json`, `README.md`, `How to Use.txt` and
    `data/how_to_use.json`. Today they speak of 1,200 bytes and "…".

## Tools and the Translations window (row 10)

24. **consistency: a Tools-tab "Game Text..." entry** opening Picture Studio's Text tab, or the same tool. It needs
    "As the stock game shows it", "As Use Unicode Font draws it" and the (game) / (patcher-made) / (drawn by
    Windows: face) / (missing) labels (`src/vv_pictures_text_tab.py`).
25. **consistency: Translations window.** Multi-select, Select All, Delete..., Download from GitHub..., a public
    `translations/` folder, "(TEST)" never shipped (open PR #682 is a "(TEST)" translation) and VirusTotal. The VV
    chat says this is coming in v1.35.90. Model: VF1 `patcher/vf1_translations_window.py`.
