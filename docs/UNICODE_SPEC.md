# Shared Unicode text spec: Fish/Plant, VF1, VF2, VV (audit of 2026-11-02)

The owner's rules, word for word: "ALL GAMES' UNICODE IMPLEMENTATION MUST BE THE SAME." and "DO NOT REMOVE STUFF
TO MATCH THE OTHERS, BUILD STUFF TO MATCH THE OTHERS."

So this spec is the **union** of what the four patchers do today. For each row it takes the strongest behaviour
that exists in at least one repo and names the repo it comes from. It adds nothing that no repo has: there are
no UCD 18.0 tables, and nothing beyond what some repo already ships or has in an open PR. Where two repos made
choices that cannot both hold, the spec picks one, using these tests in order:

1. Saves stay loadable and readable in the stock game.
2. The choice keeps the most capability.

It then says why. The other repo moves toward that choice and keeps everything else it has.

Game-specific facts (addresses, file names, field sizes, DLL names) are in the per-repo difference files, not here.

Snapshots audited (read-only):
- Fish/Plant: origin/main c26b682, plus commit 463539a (feat/unicode-18).
- VF1: origin/main 6073731 (PR #71 merged).
- VF2: origin/main cfad729 (B207 config).
- VV: origin/main c62ad648 (#676 merged), plus open PR #677 `feat/copy-paste-in-game` at a95ce151 for Copy and Paste.

Repo short names: **FP** (Fish/Plant), **VF1**, **VF2**, **VV**.

---

## 1. Settings

| Item | Spec | From |
| --- | --- | --- |
| Names, exact | `Render Unicode with In-Game Fonts`, `Use Unicode Font (overrides in-game fonts)`, `Copy and Paste in Text Boxes` | all four already match |
| Defaults | Render ON; Use Unicode Font OFF; Copy and Paste ON | all four |
| Owner's Defaults | Render ON, Use Unicode Font OFF (**owner decided 2026-11-01**). Select All and Default Patches also keep Render. | all four |
| Exclusion | The two Unicode settings exclude each other everywhere. Ticking one unticks the other. Patch Selection Settings refuses Tick These when both are chosen. The command line refuses `--enable` of both, and `--enable` of one turns the other off. The manifest says `excludes` both ways. | VF1 (most complete: GUI, Patch Selection, CLI, manifest) |
| Font picker | Two parts: (a) a **Tools-tab "Unicode Font..." window**: any installed family (with a search) or a .ttf/.otf/.ttc file, previews of every game font drawn as the game will draw them, and Save. A re-patch keeps the choice. A font file is copied beside the DLL and loaded with `AddFontResourceExW(FR_PRIVATE)` for the game only. (b) a quick font box beside the setting (and `--unicode-font` on the command line) where a repo already has one. Both write the same stored choice. The default is **Segoe UI**, then the fallback chain (row 3). | (a) VF1, VF2. (b) FP, VV; kept, not removed |
| Use Unicode Font sizing | Each game font keeps its line height, baseline, weight and coverage curve. Its em is fitted so that "The quick brown fox jumps over the lazy dog 0123456789" is as wide as the game font draws it, within 60%..130% of the game font's own em. | VF1 (`FitChosenFont`), VF2 |
| "Modded Upgrades" copy | Where a patcher writes content settings to a separate "- Modded Upgrades" copy, the Unicode settings go to that copy too, because they write a sidecar beside the save. Patchers with only one output copy: not applicable. | FP |
| Copy and Paste setting | It is its own setting and works with either Unicode setting on, or with neither. | all four (VV in PR #677) |

## 2. Name limit and storage

**Limit (owner decided, 2026-11-03: "All games: up to 1,200").** Every name box takes up to
`NAME_BOX_BYTES = 1,200` bytes as stored, with **no separate character cap**. That is up to 1,200 plain-ASCII
letters, and fewer when letters need more bytes. The 1,200 is the LDW engine's own `SetEditable` / `SetCanEdit` cap,
and it is never patched past. The earlier 300-character cap (VF1, VF2, FP) is **raised**, not kept, so nothing gets
lower than VV has today.

The byte count is **the bytes the box stores**, under the write rule in this section: one byte per Windows-1252
character, and that character's UTF-8 bytes otherwise. `NAME_BOX_BYTES` is written **once**, in the patcher's Python
text module. A build script writes the C header from it, and a test fails if any other file spells the number. (From
VF1: `build_vf1_text_tables.py` writes `extenders.inc`, and `test_name_limit.py` checks.) Any `NAME_LETTERS` constant
is removed or set so that it never cuts before the byte cap.

- **Which boxes:** every box that names a player, family, tribe or person. That includes the slot menu and New
  Player, the first family or tribe, a new baby, adoption, dating, renaming a person, and the patcher's own
  windows that store a name. Boxes that are not names keep their stock limits. (Each repo lists its boxes in its
  difference file.)
- **Counting:** characters are **grapheme clusters**. A typed code point is taken only while the text stays
  within 1,200 bytes, and a cluster goes in whole or not at all. (VF1, VF2, with the limit as owner-decided)
- **Cluster rule (one table, shared by Python and C, generated from one source):** one character plus every
  following extender. Extenders are:
  - general category **Mn, Mc, Me**;
  - ZWNJ;
  - ZWJ *and the character after it* (unless that character is CR or LF);
  - variation selectors FE00..FE0F and E0100..E01EF;
  - emoji skin tones 1F3FB..1F3FF;
  - tag characters E0020..E007F.

  Two regional indicators make one flag, and CR LF is one character. (VF2 has the complete set, with CR LF and
  ZWJ-before-newline. VF1 is the same except CR LF. VV's Python drops Mc. FP's C uses a short hand-written range
  list.)

**Short form in the save.**
- A name that fits its fixed field is stored there exactly as it is.
- A name that does not fit becomes its **short form**: the longest start of whole characters that fits, with
  trailing spaces dropped, then `...`. If another name already has that short form, the number goes first:
  `2...`, `3...`, and so on, until the short form stands for no other name in any slot.
- A short form already made for this name is used again.
- The short form follows the person everywhere the game copies the name: the parents' names of children, the
  tree records, death, Copy Player Slot, Back Up and Restore, and rename.

Contradiction: `...` (VF1, VF2) against `…` U+2026 written as byte 0x85 (VV). The spec takes **`...`**, because
ASCII dots draw correctly in every stock game. The stock VF1 and VF2 fonts have no 0x85 glyph: VF1 draws it as
"!" and VF2 as a missing glyph. VV keeps *reading* its `…` short forms and records forever. Only new short forms
use `...` + number. (VF1, VF2)

**Save write rule (per character):**
- A character that Windows-1252 has is written as its one byte.
- Any other character is written as UTF-8. Both kinds can mix in one string.
- If the mixed bytes would read back as different text (for example a Windows-1252 "Ã" followed by "©" spells
  UTF-8 "é"), every non-ASCII character in that string is written as UTF-8.
- A UTF-8 encoding of a Windows-1252 character met on input is rewritten as its byte.

This is from **VV** (`encode_game_text`, `ut_append`).

Why this rule: it keeps the most text readable in the **stock** game. Every Windows-1252 letter that the stock
font has shows correctly even inside a name that also holds 日本. Old names keep their exact bytes. It is also the
shortest form. VF2 (Windows-1252 only when the *whole* string fits, else all UTF-8) and VF1 (always UTF-8) both
write more names that the stock game shows as mojibake. Every stock game loads either form; the coordinator's
check found no game whose stock code rejects high bytes.

**Read rule (one shared decoder):** each well-formed, shortest UTF-8 sequence (Unicode Table 3-7: no overlong
forms, no surrogates, nothing past U+10FFFF) is read as its character. Every other byte is read as its
Windows-1252 character, and the five bytes Windows-1252 leaves undefined (81, 8D, 8F, 90, 9D) are read as the
Latin-1 control with the same number. The decoder works **per sequence, not per string**, so mixed strings read
correctly. (VV)

Migration note: VF1 and VF2 decode the whole string. Switching to per-sequence decoding changes only strings that
are invalid UTF-8 as a whole but contain a valid sequence. For example, a VF2 single-byte "Ã©é" would become
"éé". That case only arises when someone typed "Ã©" deliberately. Each of those repos should scan its tests for it.

**The full-name sidecar (union of all four):**
- **Location:** one file per save (per save slot), in the patcher's own data folder beside the saves, in a
  `Names` (or `Long Names`) subfolder. **Format:** a header line with a version, then records
  `short<TAB>room<TAB>whole<TAB>CRC-32` (8 upper-case hex digits over everything before the last tab), ending in
  LF. The text is in the game's own bytes or in UTF-8; one rule per repo, stated in its file. (Records: VF1, VF2.
  CRC: VV)
- **When written:** at once, the moment a name leaves a box (the GetText of a name site). It is also written at
  the next draw and at exit, as a fallback. A record made while no slot is known stays **pending** and is retried
  (every 2 s at a draw) until it has been written whole. (Write at once: FP, VF1, VF2. Pending and retry: VV)
- **Crash safety:**
  - The whole file is written to `<file>.tmp` and moved over the old file with `MoveFileEx(REPLACE_EXISTING |
    WRITE_THROUGH)`. If the move is refused, the file is written in place (FP, VF1, VF2).
  - Each record carries its CRC-32. A record that is cut short or merged with another is skipped (VV).
  - A file that cannot be read is read as empty, and the save then shows its short forms (VF1, VF2).
- **Records are never removed.** The first record for a short form wins. A record that is not valid is skipped:
  no mark, too long for its room, a control character, or more than 1,200 bytes. Older
  autosave copies stay readable. (VF1, VF2, VV)
- **Re-keying:**
  - Rename Players / Family / Tribe writes a new record. A failed rename undoes the file.
  - Copy Player Slot copies the source's file with its slot renamed, plus the new name's record.
  - Back Up Saves and Restore Saves carry the file with the save.
  - A short form is unique, so it follows a person through death and the game's own copies. (VF1, VF2; VV for the
    copy)
- **Readers:** every patcher reader expands short forms to whole names: save readers, logs, family trees, the
  Family History reader and Picture Studio. The game's own log DLLs write whole names. (VF1, VF2, VV)
- **Old masked names:** a repo that once wrote `?` for characters a log exporter could not store offers a Repair
  that rewrites those records to the real name, but only when the mask matches exactly one person. A tool never
  writes `?` for a character it cannot store: it drops the character or uses UTF-8. (VV)

**Viewing never shortens a name.**
- A box the game opens with a stored name, and closes unchanged, gives the game back nothing, so the game skips
  its copy, or gives back exactly the same bytes. (VF1, VF2)
- A box given a short form opens with the whole name. (all four)
- A box's own draw never cuts its own text by pixels. It draws a fitted copy instead: the end of the text while
  the box is typed into, otherwise the start followed by "…". (FP, VF1, VF2, VV)
- In VV both Unicode settings require "Full Names on the Details Screen".

## 3. Drawing

- **Decoding:** the read rule of row 2, the same in the DLL and in Python.
- **Glyph source order:**
  1. the game font's own glyph, drawn by the game's own code pixel for pixel;
  2. a **patcher-made** glyph in the font's style (an accented letter built from the font's own base letter and
     accents; everything else drawn by GDI in the fitted face, em and coverage curve);
  3. a glyph drawn on the spot from the Windows fallback chain, in the game font's size, baseline and weight,
     and cached for the session;
  4. the **missing-glyph box**.

  (VF1, VF2, VV)

  Contradiction: FP draws `?` from the game font as the last resort. The spec takes the **box**, which three
  repos use and which can never be mistaken for a typed "?".
- **Fallback chain (one list, in this order; a face that is not installed is skipped):**
  1. Segoe UI (with Use Unicode Font: the chosen face first, then Segoe UI)
  2. Segoe UI Historic
  3. Segoe UI Symbol
  4. Segoe UI Emoji
  5. Yu Gothic (UI)
  6. Meiryo
  7. Microsoft YaHei (UI)
  8. Microsoft JhengHei (UI)
  9. Malgun Gothic
  10. SimSun-ExtB
  11. Nirmala UI
  12. Ebrima
  13. Gadugi
  14. Leelawadee UI
  15. Myanmar Text
  16. Javanese Text
  17. Mongolian Baiti
  18. Microsoft Himalaya
  19. Microsoft Yi Baiti
  20. Microsoft New Tai Lue
  21. Microsoft Tai Le
  22. Microsoft PhagsPa
  23. Sylfaen
  24. Cambria Math
  25. Noto Sans
  26. Noto Sans Symbols
  27. Noto Sans Symbols 2
  28. Noto Sans CJK JP
  29. Noto Sans CJK SC
  30. Noto Sans Math
  31. Noto Sans Cuneiform
  32. Noto Color Emoji

  This is the union of the VF1, VF2, VV and FP chains. Historic, Symbol and Emoji come before the CJK fonts, as in
  VF1, VF2 and VV. A face is used for a character only when its character map has every code point of the cluster
  (VF1).
- **Colour emoji:** a glyph from a colour font (COLR/CPAL, CBDT, sbix or SVG) is drawn in its own colours, never
  tinted, with the text's alpha. This uses Direct2D/DirectWrite (`D2D1_DRAW_TEXT_OPTIONS_ENABLE_COLOR_FONT`), and
  is the strongest form because it covers every colour format, including Noto Color Emoji's CBDT (FP). VV's own
  COLR/CPAL layer renderer is an accepted equal path for COLR fonts. Without Direct2D the glyph is drawn in one
  colour by GDI (FP).
- **Composition:** a base letter followed by combining marks is drawn as its precomposed letter when one exists
  (`NormalizeString` NFC). One that does not compose is drawn as a whole cluster. (VF1; VF2 uses a fixed table)
- **Shaping:** runs of scripts that need shaping are shaped and ordered by Windows (Uniscribe) as a whole run:
  Arabic, Hebrew, Syriac, Thaana, N'Ko, the Indic scripts, Thai, Lao, Tibetan, Myanmar, Khmer and Mongolian, with
  their marks, joiners and inner spaces. The run is drawn through the game's own draw. (VV only; the others draw
  one character at a time, unshaped.)
- **Fit-to-width with "…":** every fixed spot where the game draws a name has its **real room**, measured from the
  game's layout. A name wider than its room, whole names for short forms included, is drawn as its longest start of
  whole characters, trailing spaces dropped, then "…" (U+2026, or byte 0x85 in a one-byte string). It is measured
  with the glyphs actually drawn. A name that fits is drawn exactly as before. (VF1 `DrawSpots` / `LabelSpots`.
  FP and VF2 use an estimate: a placeholder width or as many "W" as the field holds.)
- **Wide characters in non-name boxes:** a typed text is never wider than the widest text the stock game allows in
  that box (its byte limit times the font's widest plain letter). A wider character is refused. Name boxes scroll
  instead. (VF2)
- **Line breaking (UAX #14):**
  - Text with a letter of a script written without spaces (ID, SA, H2, H3, JL, JT, JV, CJ, EB, EM, or the CJK
    punctuation blocks) or a ZWSP may break between whole clusters, where `ubrk_open(UBRK_LINE)` of Windows'
    `icu.dll` allows it. The DLL loads it with `LOAD_LIBRARY_SEARCH_SYSTEM32`; ICU also knows the
    Thai/Lao/Khmer/Myanmar dictionary words.
  - Without ICU, a built-in table is used: kinsoku closing marks never start a line (。、」）, small kana, ー, ゝ), and
    opening marks never end one.
  - Text with no such letter, where every word fits, runs the game's own wrapper untouched, so ASCII is
    pixel-identical.
  - A word wider than the whole line is cut after its longest start of whole characters (at least one) instead of
    hanging.
  - A justified CJK paragraph finishes its line instead of hanging.

  (VF1 `wrap.inc` / `linebreak.inc`; the last point is from VV)
- **The Windows-1252 / Latin-1 extended glyphs:** every Windows-1252 letter (80..9F included) and every Latin-1
  letter is a patcher-made glyph in each game font that lacks it. The fonts' broken boxes for ASCII symbols are
  made real (FP Fish's Paddington). With Render Unicode with In-Game Fonts on, they are added to *copies* of the
  font pictures; the game's own pictures are never changed. (FP, VF1, VF2, VV)

## 4. Typing

- **Every character the keyboard sends** reaches the box: an SDL 1.2 game reads `keysym.unicode`, an SDL 2 game
  reads the whole `SDL_TEXTINPUT` (UTF-8). Dead keys, Alt codes, AltGr letters and an input method's composed text
  all arrive. An SDL 1.2 game also subclasses the window for `WM_IME_COMPOSITION` (GCS_RESULTSTR as UTF-16),
  `WM_IME_CHAR` and `VK_PACKET` (TranslateMessage, then the `WM_CHAR` read as UTF-16). (FP for SDL 1.2; all four
  for SDL 2)
- **Surrogate pairs joined:** a high half waits for the low half (two `WM_CHAR`s, or two SDL text events of
  `ED A0..AF xx` / `ED B0..BF xx`). The pair is posted as one character. A lone half is never typed. (all four)
- A letter goes in **whole or not at all**, within the box's byte limit. (all four)
- **Backspace removes one whole grapheme cluster.** (VF1, VF2, VV)
- **A combining mark typed right after a refused character** belongs to that character and is refused too. It
  never lands on the box's last character. (VF2)
- Control characters, C1 controls and lone surrogates are never stored. Enter and Tab keep the box's stock "done".
  Number boxes keep their stock rules. (all four)

## 5. Copy and Paste in Text Boxes

- **Setting:** `Copy and Paste in Text Boxes`, ON by default, in Owner's Defaults and in Select All. (all four)
- **Keys:**
  - Ctrl+V and Shift+Insert paste at the caret, which is the end of the text in every game.
  - Ctrl+C and Ctrl+Insert copy the box's whole text (the whole name, never the short form).
  - Ctrl+X copies, and empties the box only if the copy succeeded.
  - No Alt (so AltGr letters are left alone), no Windows key, and Ctrl+Shift+V is not a paste. A held key's
    repeats are swallowed.

  (all four; "only if the copy succeeded" and "repeats swallowed" from VV)
- **Only while a box has typing focus:** the box is found the way the game itself would type into it, in the
  game's own listener order. With no box focused, every key goes on to the stock game exactly as before.
  (VF1, VF2, VV)
- **The text is cleaned before it goes in:**
  - CR, LF and Tab each become a space, with **CR LF as one space** (FP, VV).
  - Other C0, DEL and C1 controls are dropped, and so are lone surrogates.
  - The text is put in **NFC** first (VV; VF1 composes with FoldStringW).
  - A character the game cannot show is dropped, never turned into "?" (VV).
  - A number box keeps digits only, and "-" only as the first character. (all four)
- **The cut:** the paste goes in as if typed, through the box's own handler, at whole grapheme clusters. It stops
  at the box's byte limit, counted over the box's existing text plus the paste. A mark that would join the box's
  last character and no longer fits is not pasted. (VF1, VF2)
- **With both Unicode settings off (owner decided, 2026-11-03: "What the fonts draw"):** a paste keeps only the
  characters **that game's stock fonts can draw**, one byte each, so nothing turns into blanks. For example, VF1
  keeps ASCII plus A2..FF. Each repo derives its set from its own stock font tables and tests it. Where the stock
  fonts have only ASCII (FP, and VV with no Unicode companion), that means printable ASCII.
- **Clipboard read cap:** a bounded read of at most **8,192 UTF-16 units** (VF1), bounded by `GlobalSize` and the
  first NUL, never past either. OpenClipboard gets the game's window, is always closed, and is never waited on. A
  busy or empty clipboard does nothing. Copy allocates before `EmptyClipboard`, so a failed copy leaves the
  clipboard as it was. (FP, VF1 for the bounds; VV for no waiting)
- **The keys never type letters,** and no save, record or file is written by Copy and Paste except the box's text.
  (all four)

## 6. Allowed characters in the tools (Rename and Copy Player Slot)

- They decide by **code-point ranges, not by Python's `unicodedata`**. Allowed: any scalar except NUL, C0/DEL/C1
  controls, lone surrogates, U+2028/U+2029 and U+FEFF. **Letters newer than the running Python's Unicode data must
  be accepted**, because the games take and draw them. (FP commit 463539a for the range approach; VF1 `printable`
  for the set)

  Contradiction: FP 463539a also rejects private use and noncharacters, while VF1 and VF2 accept them (the game
  stores them and draws a box). The spec **accepts** them, because rejecting would remove something VF1 and VF2
  allow today.
- With no Unicode setting on, the tools allow the stock set (printable ASCII, or the game's stock Latin-1 /
  Windows-1252 set).
- Length is checked as 1,200 bytes, as stored, with cuts at whole clusters. The counter reads "N / 1200 bytes"
  (plus the character count for information) and says when the save will keep a short form. (VF1, VF2, with the
  limit as owner-decided)

## 7. The translation validator

- **Files:** UTF-8 with or without a BOM, or UTF-16 LE/BE with a BOM. Any Unicode scalar is accepted in a
  translation except C0 controls other than `\n` and `\t`. There is no check against `unicodedata` categories, so
  new letters pass. (FP, VF1, VF2, VV)
- **The "%" rule:** only the tokens in the line's **own English** are placeholders: its printf conversions, and
  `%%` when the English has it. Any other `%` is plain text, so "2 %", "2 %" and "50 % de réduction" are fine.
  A translation's conversion must match one the English has; a width or precision may change, but never by adding
  the space flag alone. When the program uses the line as a printf **format**, a plain `%` is written as `%%` in
  the text handed to it, and the extra bytes count toward the line's room. In any other line it is passed on
  unchanged. (VF1 `translation_format.py`, "PERCENT SIGNS")
- **Byte rooms:** counted in the bytes the game will get (UTF-8 when the Unicode contract is on, otherwise
  Windows-1252). Choices are counted at their longest. (FP, VV)

## 8. The Translations ↔ Unicode contract

- The Unicode text DLL exports one stdcall function, `int <Prefix>UnicodeTextActive(void)` (FP:
  `FtfpUnicodeTextActive`; VV's equivalent is `VvfpGlyphsUtf8`). It returns nonzero only once its hooks are
  **installed** and it draws UTF-8.
- The Translations DLL, loaded after it, finds it with `GetModuleHandleW` + `GetProcAddress` and passes the
  translation on as UTF-8 when the function returns nonzero. Otherwise it converts to Windows-1252, writing "?"
  only for characters with no byte; this is a fallback for display only. Windows popups get UTF-16.
- Translation text and long-name expansion are applied in a fixed order in the draw path: translation first, then
  short forms to whole names. (VV)
- Copy and Paste asks the same function, or the equivalent status export, to choose UTF-8 or bytes. (VV, VF2)

**From FP:** the function's answer reflects whether the hooks really installed, not only whether the DLL file is
present.

## 9. Docs wording shown to players

Every patcher uses the same release-note paragraph, with only its game's box list and folder name changed (from
VF1 / VF2 `UNICODE_TEXT.md`, "Release note"):

> **Long names, everywhere.** With Render Unicode with In-Game Fonts or Use Unicode Font on, every name box takes
> names up to 1,200 bytes (up to 1,200 plain letters; fewer when letters need more bytes): <the game's boxes>;
> <the rename and copy tools> take the same. It is one
> limit, shared with the other Fun Patchers. Characters are counted as you see them (a letter with its accents,
> an emoji with its skin tone or a flag is one), and Backspace removes one whole character. A long name scrolls in
> its box while you type it. The save itself is not changed: a name that fits its field is kept there exactly as
> before; a longer one is kept there as its short form (its start and "...", or "2...", "3..." when two would
> start alike) and the whole name is kept beside the save, in `<Game> Patcher Data\Names`. The game shows the
> whole name wherever it shows that name, fitted with an ellipsis (…) only where the game leaves room for a name's
> usual length. Back Up Saves, Restore Saves and Copy Player Slot carry the Names files with the saves. With both
> settings off the game still loads and plays such a save and shows the short form.

The setting descriptions say "characters" (not "letters" or "bytes"), name the fallback chain the same way
("Segoe UI, Segoe UI Historic, Segoe UI Symbol, Segoe UI Emoji (in colour), the CJK fonts, Nirmala UI, Ebrima ...,
Noto if installed"), and say that emoji are in colour. Copy and Paste's text matches row 5. Every Unicode setting
says "Not yet seen in a running game" until it has been live tested.

## 10. Tools and the Translations window (VF chat's rows 11 and 14)

- **Game Text tool** (Tools tab), from VF1 "Game Text...", VF2 "Game Font Text...", FP "Text Maker..." and VV's
  Picture Studio Text tab. It offers:
  - every game font, labelled;
  - colour and see-through;
  - a preview drawn exactly as the game draws, at 1x/2x/4x, or "As the stock game shows it";
  - a character picker that searches by name or code point and labels each character "(game)",
    "(patcher-made)", "(drawn by Windows: face)" or "(missing)";
  - "As Use Unicode Font draws it" (VF2);
  - Save PNG.

  The entry is labelled **"Game Text..."** (VF1). Existing tools keep their current features.
- **Translations window:**
  - multi-select (extended);
  - Select All;
  - Delete... (to the Recycle Bin, after one Yes/No that defaults to No);
  - **Download from GitHub...** (the repo's public `translations/` folder, through the read-only public API);
  - Add, Edit, Check, Export, Open folder;
  - Share on GitHub...;
  - a "(TEST)" translation is never shipped in a release;
  - releases are checked on VirusTotal.

  (VF1 PR #71; VirusTotal and the public folder also VF2)
