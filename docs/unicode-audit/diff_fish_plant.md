> **Owner decisions, 2026-11-03 (these override anything below):**
> 1. **Name limit: "All games: up to 1,200".** Every name box takes up to 1,200 bytes as stored, with NO 300-character cap. Wherever this file says "300 characters", read "1,200 bytes", cut at whole clusters. Remove any NAME_LETTERS-style cap that would cut before the byte cap. The counter reads "N / 1200 bytes". Change manifest and docs wording to match.
> 2. **Paste with both Unicode settings off: "What the fonts draw".** Keep only the characters that game's stock fonts can draw, one byte each. Derive the set from the stock font tables and test it. (FP and VV: printable ASCII, since their stock fonts lack the rest.)
> 3. **VF2 Translations DLL and window: in B208.**

# Fish/Plant (Lorsieab2/Fish-and-Plant-Tycoon-Fix-Patcher): what to build

Audited: origin/main c26b682, plus commit 463539a (feat/unicode-18; not on origin/main).

Every item is something to **build**. Nothing is removed. "bug" means wrong behaviour today. "consistency" means
building toward UNICODE_SPEC.md.

Game facts (kept out of the spec):
- Save fields are 32 bytes: 31 bytes and a NUL.
  - Fish: player list at state+0x1E3D8 (42 bytes a row); the save's own name at state+0x1E3A5.
  - Plant: list at state+0x53FC2 (33 bytes a row); state+8.
- Sidecar: `<Game> Fix Patcher Data\Names <slot>.dat`.
- DLL: `Unicode Text.dll`, set by `Unicode Text.ini` (`Mode=ingame|system|none`, `Font=`, `Paste=1`).
- Contract export: `FtfpUnicodeTextActive`.
- Name boxes: the five player-list rows and the new-player box.

## Bugs

1. **bug: Rename Players and Copy Player Slot refuse letters newer than Python's Unicode data.**
   `src/save_tools.py` `name_allowed` uses `unicodedata.category(ch) not in ("Cc","Cs","Co","Cn")`, so a Unicode 17
   or 18 letter is rejected as "Cn". The range-based fix is commit 463539a (`feat/unicode-18`). Merge it to main.

## Settings (row 1)

2. **consistency: build a Tools-tab "Unicode Font..." window.** It should offer:
   - any installed family with a search, or a .ttf/.otf/.ttc file (copied beside the DLL and loaded with
     `AddFontResourceExW(FR_PRIVATE)`);
   - a preview of each game font as the game will draw it;
   - Save.

   It writes the same `Font=` that the existing combobox writes (`src/tycoon_fix_patcher_gui.py`
   `_unicode_font_row`, kept) and adds a `File=` key that `native/common/unicode_config.h` reads. Model:
   VF1 `patcher/vf1_unicode_font.py`.
3. **consistency: Use Unicode Font em fitting.** Today `native/common/unicode_glyphs.h` (system_font) draws at the
   game fonts' line heights. Add VF1's fit: the "quick brown fox ..." sentence is as wide as the game font draws
   it, within 60%..130%, keeping the game font's baseline and coverage curve (VF1 `vf1_game_fonts.fit_unicode_font`,
   `FitChosenFont`).
4. **consistency: exclusion.** Make the command line refuse `--enable` of both Unicode settings, and make
   `--enable` of one turn the other off (`src/fish_patcher.py`, `src/plant_patcher.py`, `src/tycoon_fix_patcher.py`).
   Check that Patch Selection Settings refuses Tick These with both chosen. The GUI and manifests
   (`conflicts_settings`) already match.

## Name limit and storage (row 2)

5. **consistency: count characters as grapheme clusters, not code points.**
   - `native/common/unicode_typing.h` `letters_in` / `box_char` and `text_clipboard.h` (`letters_room`) count code
     points.
   - `src/save_tools.py` `validate_name` uses `len(name)`.
   - Use the shared cluster table (Mn/Mc/Me, ZWNJ, ZWJ + next, VS, skin tones, tags, RI pairs, CR LF). Generate it
     into a C header from one Python source, as VF1 `scripts/build_vf1_text_tables.py` does.
   - `clip_joins` in `text_clipboard.h` and `text_maker.py`'s cluster code then use that table.
6. **consistency: write NAME_LETTERS once.** Today it is written twice: `src/save_tools.py` `NAME_LIMIT = 300` and
   `native/common/unicode_names.h` `#define NAME_LETTERS 300`. Generate the C copy from Python and add a test that no
   other file spells 300 or 1200 for names.
7. **consistency: short form.**
   - Today `short_form` (`unicode_names.h` and `save_tools.py`) writes each character as its Latin-1 byte, "?" for
     any other, and cuts after 31 characters with no mark.
   - Build the spec's rule: a name that fits the 31 bytes is stored as it is, under the per-character write rule
     (row 2: a Windows-1252 byte, otherwise UTF-8, falling back to all UTF-8 when the mix would misread).
     Otherwise the longest whole-cluster start + `...`, or `2...`, `3...` until it is unique across the 5 slots.
   - Keep reading old "?" short forms. A slot file whose short form is the old Latin-1 form still matches.
   - **Check first:** confirm in the stock exes that the 32-byte name fields (Fish state+0x1E3A5 especially) are
     never used as a file name or registration key, where UTF-8 bytes could matter.
8. **consistency: read rule.**
   - `native/common/unicode_utf8.h` `utf8_next` reads a stray byte as **Latin-1**; the spec says Windows-1252
     (the five undefined bytes as Latin-1).
   - Add a `CP1252_HIGH` map to the decoder (one already exists in `unicode_glyphs.h`) so that copying a box that
     holds 0x80 gives U+20AC, not U+0080.
   - `src/save_tools.py` `full_name` uses `latin-1`; use the shared decoder there too.
9. **consistency: the sidecar format.**
   - Today `Names <slot>.dat` is "short NUL full NUL", one name per slot.
   - Build the shared format: a versioned header and `short<TAB>room<TAB>whole<TAB>CRC-32` records, never
     removed, first record wins, invalid records skipped.
   - Keep the `.tmp` + `MoveFileExW(REPLACE|WRITE_THROUGH)` write, which is already there.
   - Add a "pending" state with a retry for a record whose write failed.
   - Keep reading the old `.dat` files.
   - Files: `native/common/unicode_names.h`, `src/save_tools.py` (`_names_bytes`, `full_name`, Rename, Copy),
     `src/save_backup.py`.
10. **consistency: the rename and copy tools' counter.** It should read "N / 300 characters" and say when the save
    will keep a short form (`src/tools_tab.py`), as VF1 `vf1_rename_family.room_text` does.

## Drawing (row 3)

11. **consistency: the last resort is the missing-glyph box, not "?".** `native/common/unicode_glyphs.h`
    (`unicode_width` / `unicode_draw` use `font_byte(inner, '?')`). Build a box glyph in each font's style, as
    VF1 / VF2 `missing_box` do.
12. **consistency: fallback chain order and members.**
    - `CHAIN[]` in `unicode_glyphs.h` puts the CJK fonts before Segoe UI Historic, Emoji and Symbol, and Emoji
      before Symbol.
    - Reorder it to the spec's list, and add Microsoft JhengHei, SimSun-ExtB, Microsoft Yi Baiti, New Tai Lue,
      Tai Le, PhagsPa, Cambria Math and the Noto faces.
    - Use a face only when its cmap has every code point of the cluster.
13. **consistency: draw per cluster, compose marks (NFC), and shape complex-script runs.**
    - `raster_glyph` draws one code point at a time, so e + U+0301 and ZWJ emoji sequences come out as separate
      pieces.
    - Build VF1's composition (`NormalizeString` C) and VV's Uniscribe runs for Arabic, Hebrew, Indic, Thai and
      the others (VV `native/vvfp_unicode_text/runtime_glyphs.inc`, `text_utf8.h` `ut_unit`).
    - Keep FP's Direct2D colour path, which the spec takes as the colour-emoji model.
14. **consistency: fit names to real spot widths.** `native/common/unicode_text.h` `name_shown` fits to
    max(short-form width, 26-underscore placeholder). Measure each fixed spot where a name is drawn (player list
    rows, main menu "Player: <name>", greenhouse/tank labels, etc.) and give each its real room, as VF1
    `native/vf1text/names.inc` `DrawSpots` / `LabelSpots` do.
15. **consistency: wide characters in non-name boxes are refused** when the text would be wider than the stock box
    allows (registration boxes, the price box). From VF2 `b200unicode.cpp` (see its "wide scripts fit").
16. **consistency: line breaking (UAX #14 through `icu.dll`, kinsoku fallback, long words cut).** First find out
    whether either game has a word wrapper that translations or names reach (`native/ftfp_translations` lines,
    the Time Warp popup, tips). If one exists, hook it as VF1 `native/vf1text/wrap.inc` / `linebreak.inc` do.

## Typing (row 4)

17. **consistency: Backspace removes a whole grapheme cluster.** `unicode_typing.h` `box_char` uses `letter_before`,
    which is one code point.
18. **consistency: a mark typed after a refused character is refused too** (VF2 `b200unicode.cpp`, "A name box whose
    last typed character was refused").

## Copy and Paste (row 5)

19. **consistency: paste in NFC** (VV PR #677 / VF1 FoldStringW) before cutting (`text_clipboard.h` `clip_paste`).
20. **consistency: count the 300 over box text + paste in clusters,** and do not paste a joining mark that no longer
    fits (VF1 `clipboard.inc`). FP already keeps a base and its joiners together.
21. **consistency: read cap of 8,192 UTF-16 units.** `CLIP_UNITS` is 2,408 today; the read is already bounded by
    `GlobalSize`.
22. **consistency: swallow a held key's repeats.** In `clip_key`, check bit 30 of lParam (previous key state) on
    WM_KEYDOWN so a held Ctrl+V pastes once.
23. **consistency: with both settings off, the set stays printable ASCII.** This matches the owner's "each game's
    stock box set" and needs no change. Check that the docs say so.

## Allowed characters (row 6)

24. See item 1 (bug). When merging 463539a, also accept private use and noncharacters: VF1 and VF2 allow them and
    the spec keeps them. Reject only NUL, C0/DEL/C1, lone surrogates, U+2028/2029 and U+FEFF. Also,
    `src/text_maker.py` and `src/translations_window.py` must not reject Cn.

## Translation validator (row 7)

25. **consistency: VF1's "%" rule.** `src/translation_format.py` `check_translation` flags any lone `%` the English
    lacks, and "50 % de" parses as `% d`. Port VF1 `patcher/translation_format.py`:
    - the `Source` / `token_at` logic (a "%" is a placeholder only when the English has that token);
    - `Entry.is_format`;
    - `runtime_text` writing `%%` for plain "%" in format lines;
    - counting the extra bytes in `measure`.

    Mirror it in `native/ftfp_translations` and keep `tests/test_translations_runtime.py` in agreement.

## Contract (row 8)

26. ✓ `FtfpUnicodeTextActive` returns `utf8_drawing`, so it reflects the install. This is the spec's model. No
    change.

## Docs (row 9)

27. **consistency: use the spec's release-note paragraph and wording.**
    - The manifests' `description`s (`data/fish_manifest.json`, `data/plant_manifest.json`) say "300 letters",
      "first 31 letters ... '?' for a letter Latin-1 has not" and "Fix Patcher Data\Names <slot>.dat". After
      items 5 to 9 they should say "characters", describe the short form and `...`, and name the shared fallback
      chain.
    - Update `README.md`, `How to Use.txt`, `CHANGELOG.md`, `docs/translations.md` and `src/game_mechanics_*.py`
      to match.

## Tools and the Translations window (row 10)

28. **consistency: label the Text Maker entry "Game Text..."** and add "As the stock game shows it", "As Use Unicode
    Font draws it" and the (game) / (patcher-made) / (drawn by Windows: face) / (missing) labels where they are
    missing (`src/tools_tab.py`, `src/text_maker_window.py`).
29. **consistency: Translations window.**
    - Today it is single-select (`selectmode="browse"`) with no Delete..., Select All or Download from GitHub....
    - Build these from VF1 `patcher/vf1_translations_window.py` and `vf1_translations_github.py`, with a public
      `translations/` folder in the repo.
    - Add the release checks: a "(TEST)" translation is never shipped (VF1 `tools/package_release.py`,
      `tests/test_release.py`), and VirusTotal.
    - Files: `src/translations_window.py`, `src/translations.py`.
