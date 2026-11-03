> **Owner decisions, 2026-11-03 (these override anything below):**
> 1. **Name limit: "All games: up to 1,200".** Every name box takes up to 1,200 bytes as stored, with NO 300-character cap. Wherever this file says "300 characters", read "1,200 bytes", cut at whole clusters. Remove any NAME_LETTERS-style cap that would cut before the byte cap. The counter reads "N / 1200 bytes". Change manifest and docs wording to match.
> 2. **Paste with both Unicode settings off: "What the fonts draw".** Keep only the characters that game's stock fonts can draw, one byte each. Derive the set from the stock font tables and test it. (FP and VV: printable ASCII, since their stock fonts lack the rest.)
> 3. **VF2 Translations DLL and window: in B208.**

# VF2 (Lorsieab2/Virtual-Families-2-Restoration-Addition-Patcher): what to build

Audited: origin/main cfad729 (B207 config).

B207 is being built on the current Unicode code, so alignment goes into **B208**. Only the two items marked
**bug (B207 candidate)** are worth taking into B207. Every item is something to **build**. Nothing is removed.

Game facts (kept out of the spec):
- Fields: player/nickname 20 bytes; family member 25 (the stock box keeps 18); Family Tree note 80.
- Ten `SetCanEdit` name-box calls, found by function pins (`runtime/b200_unicode_sites.py`).
- Sidecar: `<saves>\Virtual Families 2 Patcher Data\Names\Virtual Families 2<N>.ldw.txt`, header `VF2 Names 1`.
- DLLs: `vf2unicode_b200.dll` / `vf2unicodefont_b200.dll`, `vf2clip_b200.dll` (the same source built with
  `B200UNICODE_CLIP`), `vf2history_b200.dll`.
- Stock fonts hold ASCII and Latin-1 0xA2..0xFF.
- The Unicode Font choice is in `Unicode Font\Unicode Font.ini`.

## Bugs (B207 candidates)

1. **bug (B207 candidate, low): the clipboard read is not bounded by the block size.**
   - `runtime/native/b200unicode/b200clip.inc` `ClipboardText` loops `for (i = 0; w[i] && n < cap; ++i)`. It stops
     only at a NUL or once `cap` characters are *kept*; dropped controls do not count toward `cap`.
   - A clipboard block that has no NUL (an app may set one) is read past its `GlobalSize`.
   - Fix: bound `i` by `GlobalSize(h) / sizeof(wchar_t)` and by a fixed maximum of 8,192 units, as FP
     `text_clipboard.h` `clip_read` and VF1 `clipboard.inc` do.
2. **bug (B207 candidate, low): a failed copy empties the clipboard.**
   - `SetClipboardText` calls `EmptyClipboard()` *before* `GlobalAlloc`. If the allocation or the lock fails, the
     player's clipboard has already been wiped. The comment above says "the clipboard is left as it was".
   - Fix: allocate and fill first, then `OpenClipboard` / `EmptyClipboard` / `SetClipboardData`, as FP `clip_write`
     does.

## Name limit and storage (row 2)

3. **consistency: per-character write rule.**
   - Today `src/vf2_game_text.py` `encode` writes single bytes only when the *whole* string is Windows-1252, and all
     UTF-8 otherwise.
   - Build VV's per-character rule: each Windows-1252 character as its byte, others as UTF-8 in the same string, and
     all UTF-8 only when the mix would read back differently. VF2's existing check becomes this guard.
   - The same in `runtime/native/b200unicode/b200unicode_text.h` and `b200names.inc`.
4. **consistency: per-sequence read rule.**
   - Today `vf2_game_text.decode` and `is_utf8` treat the whole string as UTF-8 or as Windows-1252.
   - Build VV's per-sequence decoder (`b200unicode_text.h` too).
   - Check old saves and tests for strings that are invalid UTF-8 as a whole but hold a valid sequence, which the
     old encode could write, such as "Ã©é".
5. **consistency: sidecar CRC-32 and pending writes.**
   - Add a CRC-32 column under a `VF2 Names 2` header, and keep reading `VF2 Names 1`.
   - Skip a record whose CRC fails.
   - Keep a record pending and retry it (VV `long_names.inc`).
   - Files: `src/vf2_names.py`, `runtime/native/b200unicode/b200names.inc`, `runtime/native/b200history`.
6. ✓ The limit is written once (`NAME_LETTERS` in `vf2_game_text.py`; `b200name_limit.h` checked by
   `tests/test_name_limit.py`). For full parity, generate `b200name_limit.h` from Python as VF1 does, instead of
   checking it.

## Drawing (row 3)

7. **consistency: colour emoji.** The README says "Emoji are drawn in one colour (the text's), not in full colour".
   Build FP's Direct2D/DirectWrite colour path (COLR, CBDT, sbix, SVG; never tinted; GDI fallback) in
   `b200unicode.cpp`'s GDI section, and in `src/vf2_glyph_render.py` for the Game Font Text preview.
8. **consistency: shaping of complex scripts** with VV's Uniscribe runs (Arabic, Hebrew, Indic, Thai ...). Today
   they are drawn one cluster at a time.
9. **consistency: fallback chain.** Add Meiryo, Microsoft PhagsPa, Cambria Math, Noto Sans CJK JP, Noto Sans Math
   and Noto Color Emoji to `kChain[]` (`b200unicode.cpp:301`) and to `src/vf2_glyph_render.py`, in the spec's order.
10. **consistency: fit names to the real width of each fixed spot.**
    - Today a short form's whole name is fitted into "as many W as the field holds bytes" (`docs/UNICODE_TEXT.md`).
      A name stored whole that is wide in pixels (Cuneiform, CJK, set by Rename Family or Copy Player Slot rather
      than typed) is never fitted.
    - Build VF1's `DrawSpots` / `LabelSpots`: measure each spot's real room (Family Tree frames, bottom bar, status
      line, title screen name).
    - VF2's typing cap ("wide scripts fit") stays.
11. **consistency: line breaking (UAX #14).**
    - Today `next_justified_line` breaks after or before a "wide" (CJK) character, with no kinsoku, no
      Thai/Lao/Khmer/Myanmar and no emoji.
    - Build VF1's `wrap.inc` / `linebreak.inc`: `ubrk_open(UBRK_LINE)` from System32 `icu.dll`; a built-in fallback
      table with kinsoku; ASCII pixel-identical; a word wider than the line cut between clusters.
    - Check whether the stock `GetNextJustifiedLine` can hang on a word wider than the line, as VF1's wrapper did.
    - Files: `src/vf2_game_text.py`, `b200unicode.cpp`.

## Typing (row 4)

12. ✓ Surrogate halves joined, Backspace removes a grapheme, a mark after a refused character is refused (VF2 is
    the source). No change.

## Copy and Paste (row 5)

13. **consistency: CR LF becomes one space.** `ClipboardText` maps CR and LF each to a space.
14. **consistency: NFC before the cut** (VV PR #677; VF1 FoldStringW).
15. **consistency: swallow a held key's repeats,** and empty on Ctrl+X only after the copy succeeded (check
    `b200clip.inc`).
16. **owner check: the set with both Unicode settings off.**
    - VF2 pastes every Windows-1252 character (`Cp1252Byte`: 0x20..0x7E, 0xA0..0xFF and 0x80..0x9F).
    - The stock VF2 fonts have none of 0x80..0xA1, so a pasted € or curly quote draws as a missing glyph in a stock
      font.
    - The owner's rule is "each game's stock box set". Confirm whether that is printable ASCII (the stock
      `CheckForEvents` passes only one-byte text) or what the stock fonts draw (ASCII + 0xA2..0xFF).
17. **consistency: read cap of 8,192 UTF-16 units** (see bug 1).

## Allowed characters (row 6)

18. ✓ `src/vf2_rename_family.py` `_unusable` rejects only Cc and Cs, so new letters pass. No change.

## Translation validator (row 7), contract (row 8), Translations window (row 10)

19. **consistency: the game-side Translations feature is missing.**
    - VF2 has `src/vf2_translation_format.py`, a public `translations/` folder and the VirusTotal / "(TEST)"
      checks, but no Translations DLL, no Translations window and no Unicode contract.
    - FP, VF1 and VV ship one. Building it (VF1's `native/vf1tr`, `patcher/vf1_translations*.py`) is a whole
      feature. Owner and coordinator: decide whether it belongs in B208.
20. **consistency: the "%" rule.** `src/vf2_translation_format.py` has FP's older rule: a lone "%" is an error when
    the English has none, so "50 % de" fails. Port VF1's `Source` / `token_at` / `runtime_text` rule.
21. **consistency: the contract.** When item 19 is built, the Unicode DLL exports a
    `B200Unicode_UnicodeTextActive()` (or answers through `B200Unicode_Status`, which `b200clip.inc` already reads)
    that is nonzero only once the hooks are installed.

## Docs (row 9)

22. **consistency:** after items 3 and 7 to 11, update the README section "Render Unicode with In-Game Fonts" (it
    says "Emoji are drawn in one colour" and "Text of ASCII and Latin-1 letters is stored one byte per letter ...
    anything else is UTF-8"), `docs/UNICODE_TEXT.md` and `src/vf2_how_to_use.json`.

## Tools (row 10)

23. **consistency: label "Game Font Text..." as "Game Text..."** (VF1). Add "As the stock game shows it" and the
    (drawn by Windows: face) / (missing) labels if `src/vf2_text_tool.py` lacks them.
