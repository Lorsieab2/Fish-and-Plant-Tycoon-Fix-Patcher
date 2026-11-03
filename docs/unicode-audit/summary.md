# Unicode audit summary (2026-11-02)

Spec: `UNICODE_SPEC.md`. What each repo must build: `diff_fish_plant.md`, `diff_vf1.md`, `diff_vf2.md`,
`diff_vv.md`.

Marks:
- ✓ matches the spec;
- differs: has it, but not as the spec says;
- missing: does not have it;
- **bug**: a defect today;
- (src): the repo the spec row comes from.

Snapshots:
- FP origin/main c26b682 (+463539a);
- VF1 origin/main 6073731;
- VF2 origin/main cfad729;
- VV origin/main c62ad648 (+ open PR #677 for Copy and Paste).

| Row | Fish/Plant | VF1 | VF2 | VV |
| --- | --- | --- | --- | --- |
| 1a Setting names (exact) | ✓ | ✓ | ✓ | ✓ |
| 1b Defaults (Render ON, Font OFF, Paste ON) | ✓ | ✓ | ✓ | ✓ (Paste only in PR #677) |
| 1c Owner's Defaults (Render ON, Font OFF) | ✓ | ✓ | ✓ | ✓ |
| 1d The two settings exclude each other | differs (no CLI refusal) | ✓ (src) | ✓ | ✓ |
| 1e Font picker: Segoe UI default + chain | ✓ | ✓ | ✓ | ✓ |
| 1f Tools-tab "Unicode Font..." (installed or file, preview) | missing (combobox only) | ✓ (src) | ✓ | missing (patch-selection box) |
| 1g Use Unicode Font em fitting | differs (line height only) | ✓ (src) | ✓ | check |
| 1h "Modded Upgrades" copy | ✓ (src) | n/a | n/a | n/a |
| 2a 300 characters + 1,200 bytes | differs (code points) | ✓ (src) | ✓ | differs (1,200 bytes only; owner check) |
| 2b Limit written once | differs (Python + C) | ✓ (src: generated) | ✓ (test-checked) | differs (Python + C) |
| 2c Counting by grapheme clusters | differs (code points) | ✓ | ✓ (src: full table) | differs (Python lacks Mc) |
| 2d Short form: fits as-is, else start + "..." / "2..." | differs (Latin-1, "?", 31 letters) | ✓ (src) | ✓ | differs ("…" + number) |
| 2e Write rule: per-character cp1252 / UTF-8 | differs (Latin-1 + "?") | differs (always UTF-8) | differs (whole-string) | ✓ (src) |
| 2f Read rule: per-sequence UTF-8, else cp1252 | differs (stray byte as Latin-1) | differs (whole string) | differs (whole string) | ✓ (src) |
| 2g Sidecar: atomic temp + MoveFileEx | ✓ | ✓ | ✓ | differs (append) |
| 2h Sidecar: CRC-32 records, pending + retry | missing | missing | missing | ✓ (src) |
| 2i Sidecar re-keying (rename, copy, backup) | ✓ | ✓ (src) | ✓ | differs (Rename Tribe writes no record) |
| 2j Viewing never shortens a name | ✓ | ✓ (src) | ✓ | ✓ |
| 2k Repair of old "?"-masked names | n/a | n/a | n/a | ✓ (src) |
| 3a UTF-8 decode, invalid bytes as cp1252 | differs (Latin-1) | ✓ | ✓ | ✓ |
| 3b Glyph order: game, patcher-made, Windows, box | differs ("?" last) | ✓ | ✓ | ✓ |
| 3c Fallback chain (union list) | differs (order, fewer faces) | differs (5 faces short) | differs (6 short) | differs (18 short) |
| 3d Colour emoji, every colour format | ✓ (src: Direct2D) | missing (one colour) | missing (one colour) | differs (COLR only; Noto Color Emoji is CBDT) |
| 3e Precomposed drawing of base + marks | missing (per code point) | ✓ (src) | ✓ (fixed table) | check |
| 3f Shaping (RTL, Indic, Thai) | missing | missing | missing | ✓ (src) |
| 3g Fit-to-width "…" at each spot's real room | differs (placeholder width) | ✓ (src) | differs (W-count) | missing |
| 3h Wide characters refused in non-name boxes | missing | missing | ✓ (src) | missing |
| 3i Line breaking: UAX #14, kinsoku, long-word cut | missing | ✓ (src) | differs (CJK only) | differs (CJK + short kinsoku) |
| 3j Windows-1252 / Latin-1 extended glyphs | ✓ | ✓ | ✓ | ✓ |
| 4a keysym.unicode / SDL_TEXTINPUT, IME, emoji panel | ✓ (src: SDL 1.2) | ✓ | ✓ | ✓ |
| 4b Surrogate pairs joined | ✓ | ✓ | ✓ | ✓ |
| 4c Backspace removes a whole grapheme | differs (code point) | ✓ | ✓ | ✓ |
| 4d Mark after a refused character is refused | missing | missing (typing) | ✓ (src) | missing |
| 5a Setting, defaults, keys, focus only, no letters typed | ✓ | ✓ | ✓ | ✓ (PR #677, not on main) |
| 5b CR LF as one space | ✓ | differs (two spaces) | differs (two spaces) | ✓ |
| 5c Controls and lone surrogates dropped | ✓ | ✓ | ✓ | ✓ |
| 5d NFC before the cut | missing | differs (only with both off) | missing | ✓ (src) |
| 5e Cut at clusters + 300 over box + paste | differs (code points) | ✓ (src) | ✓ | differs (bytes only) |
| 5f Both settings off: the stock box set | ✓ (ASCII) | owner check (ASCII + A2..FF) | owner check (all cp1252) | ✓ (ASCII) |
| 5g Clipboard read cap and bounds (8,192) | differs (2,408) | ✓ (src) | **bug** (not bounded by GlobalSize) | differs (4,096) |
| 5h Failed copy leaves the clipboard unchanged | ✓ | check | **bug** (empties first) | ✓ |
| 5i Held-key repeats swallowed | missing | check | check | ✓ (src) |
| 6 Tools accept letters newer than unicodedata | **bug** on main (fixed in 463539a) | ✓ | ✓ | **bug** (`printable` rejects Cn) |
| 7a Validator accepts any Unicode | ✓ | ✓ | ✓ | ✓ |
| 7b "%" rule (English's tokens; %% in format lines) | differs | ✓ (src) | differs | differs (no "%" without English) |
| 8 Unicode-active contract reflects the install | ✓ (src) | **bug** (DLL presence only) | missing (no Translations DLL) | ✓ (check) |
| 9 Player-facing docs wording | differs ("letters", "?") | ✓ (src) | differs ("one colour") | differs ("bytes", "…") |
| 10a "Game Text..." tool | differs (named Text Maker) | ✓ (src) | differs (named Game Font Text) | differs (Picture Studio tab) |
| 10b Translations window: Delete, multi-select, Download, public folder, TEST, VirusTotal | missing | ✓ (src) | missing (no window; has folder + VirusTotal) | missing (planned for v1.35.90) |

Note: Fish/Plant's 10b and 7b items are already built on unmerged branches for v1.0.25.

## Bugs (fix first)

| Repo | Bug | Where |
| --- | --- | --- |
| FP | Rename Players / Copy Player Slot refuse Unicode 17/18 letters on main | `src/save_tools.py` `name_allowed`; fixed in 463539a, not merged |
| VV | Tools refuse letters newer than Python's data | `src/vv_game_text.py` `printable`, used by `vv_tribe_rename.py` and `vv_save_backup.py` |
| VF1 | Translations and Copy and Paste choose UTF-8 by DLL presence, not by install | `native/vf1tr/vf1tr.c:842`, `native/vf1fun/clipboard.inc:76` |
| VF2 (B207 candidate) | Clipboard read not bounded by the block size | `runtime/native/b200unicode/b200clip.inc` `ClipboardText` |
| VF2 (B207 candidate) | A failed copy empties the player's clipboard | `b200clip.inc` `SetClipboardText` (`EmptyClipboard` before `GlobalAlloc`) |

## Contradictions the spec decided

1. **Save write rule:** per character (VV), over whole-string (VF2) and always-UTF-8 (VF1). It keeps the most
   characters readable in the stock game and old bytes unchanged.
2. **Short-form mark:** `...` with the number first (VF1, VF2), over `…`+number (VV), because ASCII draws in every
   stock font. VV keeps reading `…` forever.
3. **Last-resort glyph:** the box (VF1, VF2, VV), over "?" (FP).
4. **Fallback order:** Historic, Symbol and Emoji before the CJK fonts (VF1, VF2, VV), over FP's order.
5. **Allowed characters:** private use and unassigned are allowed (VF1, VF2), over 463539a, which rejects private use.
6. **Name limit:** 300 characters AND 1,200 bytes (VF1, VF2, FP; the owner's shared limit), over VV's 1,200 bytes
   alone. **Owner decided: 1,200 bytes everywhere, no 300-character cap.**

## Owner decisions (2026-11-03)

- **Name limit:** "All games: up to 1,200". Every game takes up to 1,200 bytes as stored, with no 300-character cap. Rows 2a, 2b, 5e and 9 now mean 1,200 bytes.
- **Paste with both settings off:** "What the fonts draw". Each game keeps what its stock fonts can draw (VF1: ASCII + A2..FF; FP and VV: printable ASCII).
- **VF2 Translations DLL and window:** in B208.
