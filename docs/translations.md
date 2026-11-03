# Translations

Play Fish Tycoon and Plant Tycoon in your own language, or make a translation for everyone. The file
format is the one every patcher of this family uses (the Virtual Villagers Fun Patcher's
`docs/translation-file-format.md`, version 1), so a translator learns it once.

## Playing in another language

1. Patch the game with the **Translations** setting on (it is on by default, and makes the
   "- Modded Upgrades" copy).
2. Tools tab, **Translations...**: choose the game, then the language in **Language in the game**.
3. Start the game. The choice applies from the next game start; there is no need to patch again.

**English (original)** leaves the game exactly as it is. A line the translation lacks, or a line it got
wrong, stays in English; the game never stops because of a translation. The patcher writes the choice
into every copy of the game it knows (the folders on the Game tabs):
`<copy>\<Game> Tycoon Fix Patcher DLLs\Translation.ini` and a copy of the file, `Translation.txt`,
beside it. `Translations.log` there says what the game used (line numbers of any line that shows
English, never the text).

Translations that came with the patcher (accepted on GitHub) are in its `translations\fish` and
`translations\plant` folders and are listed with their translator's credit name. Yours are in
`translations` itself.

### Download from GitHub...

Every shared translation is in the patcher's public folder on GitHub, `translations/fish/` and
`translations/plant/` ([translations/README.md](../translations/README.md)). Accepted translations come
with the patcher too; files marked "(TEST)" never do, and come only from the public folder.

**Download from GitHub...** (in the Share box) lists the folder for the chosen game: each file's language
and credit (read from the file once you have it, "(not downloaded yet)" before that; when one language
has several files, the credit in the file name tells them apart), the date it last changed on GitHub, and
its status: **Not installed**, **Installed**, or **Update available** when the GitHub copy's content
differs from yours (compared by the git blob SHA of the file). Choose one or more and press **Download**:
each file is checked as data (format, game, placeholders, choices, no email address) before it is saved
into `translations\<game>`. It uses GitHub's public, read-only API with no login and sends nothing about
you; it only ever contacts api.github.com and raw.githubusercontent.com, and lists only the default
branch. Without an account GitHub allows 60 requests an hour, and the window says when that runs out.

## Making a translation

Tools tab, **Translations...**, **Make a translation**: choose the language (or **Other language...**
with its own name and code) and press **Make a translation...**. The patcher reads the English lines from
your original game (it never changes it), writes `translations\<Game> - <Language>.txt` and opens the
built-in editor:

- the English on the left, your translation on the right; **Search**; **Show untranslated only**; how much
  is done, in lines and percent;
- the line's notes: its placeholders, and its limit when the game keeps it in a fixed space;
- placeholders (`%d`, `%s`, `{name}`) in colour in both texts, **Insert** buttons for them, and a
  message as soon as one is missing or wrong: such a line shows English in the game;
- a preview in the game's own font (the Text Maker's renderer), with a warning when the line is wider
  than the English or longer than its limit;
- it saves by itself; if the game uses this translation, its copy in the game folders follows.

The file is plain UTF-8 text, so Notepad works too, and so does a spreadsheet (open it as tab-separated
text, save it as tab-separated text or "Unicode Text").

**Add translation file...** (or drag a `.txt` file onto the window) checks a file you were sent and adds
it; **Check** shows coverage, errors and warnings with line numbers; **Export translation...** saves a copy.

Adding a file never loses one you already have. It replaces an installed translation only when it is
that translation's update: the same language, the same `@code` and the same `@translator` (a credit
name; two uncredited files are never one update). The older version then goes to the Recycle Bin.
Anything else is kept beside it under a name of its own (`Fish Tycoon - Français (by Zoe).txt`, then
`(2)`...), and a name used by a translation that came with the patcher or from GitHub is never reused.
**Edit...** on one of those keeps your copy as `<Game> - <its name> (own copy)`, one per game. The
language the game uses is remembered by folder and name together (`fish/fr.tsv` is never your own
`fr.tsv`). **Download from GitHub...** follows the same rule: a file already there under that name is
replaced only by the same translator's update (the old one to the Recycle Bin); otherwise the download
is saved as `<code>-<credit slug>.tsv` beside it.

## Managing the files

The list under **Translations in the patcher** is for managing the files; the language the game uses is
chosen in **Language in the game** above it. The list selects several at once: click selects one,
**Ctrl+click** adds or removes one, **Shift+click** selects a range, and **Ctrl+A** or **Select All**
selects them all. **Edit...**, **Check** and **Share on GitHub...** work on one translation.

- **Export translation...** with one selected asks for a file name; with several it asks for a folder and
  saves one file each under its own name (it asks before replacing a file already there; No, the default,
  exports only the others).
- **Delete...** (or the **Delete** key in the list) asks once, listing the files (**No** is the default and
  changes nothing), then moves them to the Windows **Recycle Bin**, from where you can restore them. It is
  never a plain delete: the patcher calls `SHFileOperationW` with `FOF_ALLOWUNDO | FOF_NOCONFIRMATION |
  FOF_SILENT` (and `FOF_WANTNUKEWARNING`, so on a drive without a Recycle Bin Windows asks instead of
  destroying the file). If that fails, the patcher shows the error and deletes nothing.
  - **English (original)** is built into the game and is never deleted; if it is selected, the question says
    it is skipped.
  - Translations that came with the patcher (`translations\fish`, `translations\plant`) can be deleted from
    your copy too; they come back with the next patcher update.
  - If the game uses a translation you delete, it goes back to **English (original)** exactly as choosing
    English does: `Translation.ini` and `Translation.txt` are removed from the game copies. An open editor of
    a deleted file closes without saving.

After a patcher update, open your file in the editor: new lines appear untranslated, a line whose English
changed comes back untranslated with your old translation kept beside it, and everything else keeps
working.

## The file

```
# Fish Tycoon - Français translation (format 1).
Key	English	Translation	Notes
@format	1	1
@game	Fish Tycoon
@language	English	Français
@code	en	fr
@translator		Your credit name
strings/1~4ece2634	Age: 	Âge : 
strings/69~17a77e24	You have sold %d fish!	Vous avez vendu %d {%1: one=poisson | other=poissons} !	%1 (%d) = number
mod/tank_counts.fish~1f0a2b3c	Fish: 	Poissons : 	Patch: Tank and greenhouse counts; Tank Counts.dll
mod/tank_counts.n_adults~f892ea16	%d {%1: one=adult | other=adults}	%d {%1: one=adulte | other=adultes}	Patch: Tank and greenhouse counts; ...
```

- Columns are separated by tabs: **Key**, **English**, **Translation**, **Notes**. Never change the Key or
  the English: the key holds the English's fingerprint, and a line whose English no longer matches shows
  English.
- `\n` is a line break, `\t` a tab, `\\` a backslash. Spaces at the start or end count.
- `strings/<id>` lines are the game's own string table (Fish Tycoon 248 lines, Plant Tycoon about 400);
  `mod/<dll>.<name>` lines are the patcher's own texts: every text a patch shows (store items and their
  descriptions, the counts, Time Warp's popups, the DS fish's and the unused flowers' species-name words...).
  Every line's notes start with `Patch: <setting>`, the patch it belongs to; the editor shows the lines in
  groups, the game's own lines first, then one group per patch. A game line whose English a patch changed
  (Unknown Chemical: 3 uses, Universal supply slots) is a second line noted with that patch.
- `#` starts a comment.

### Placeholders

- **printf conversions** (`%d` a number, `%s` a text, `%i`...): keep the same ones in the same order.
  Only the English's own conversions, exactly as written, are placeholders: any other `%` is plain text,
  so French typography works as it is (`2 %`, `2 %`, `2 %`, `50 % de réduction`), and so does `%%`.
  A line with conversions is a **format** (the game or a DLL hands it to sprintf: Fish Tycoon's Goals lines,
  the patcher's formatted texts, the counted texts): there each plain `%` reaches sprintf as `%%` and shows
  as one `%`, and that extra byte counts in the line's limit. A line without conversions is shown as written.
- **Variables** (`{name}`): keep each one; any order.
- `{{` and `}}` are literal braces.

### Choosing words by number

`{%1: one=poisson | other=poissons}` takes a branch by the value of the line's first placeholder
(`%1`; `%2` is the second...). The keys are your language's CLDR plural categories (`zero`, `one`, `two`,
`few`, `many`, `other`) and exact values (`=0`, `=1`...), which win. A missing category uses `other`, and
without `other` the first branch. Examples:

| Language | Categories (whole numbers) | Example |
|---|---|---|
| English, German, Dutch, Swedish, Turkish... | one (1), other | `{%1: one=fish | other=fish}` |
| French, Portuguese (Brazil) | one (0 and 1), many (millions), other | `{%1: one=poisson | other=poissons}` |
| Spanish, Italian, Catalan, Portuguese (Portugal) | one (1), many (millions), other | |
| Russian, Ukrainian | one (1, 21...), few (2-4, 22-24...), many | `{%1: one=рыба | few=рыбы | many=рыб}` |
| Polish | one (1), few (2-4, 22-24...), many | |
| Czech, Slovak | one, few (2-4), other | |
| Arabic | zero, one, two, few, many, other | |
| Japanese, Chinese, Korean, Vietnamese, Thai, Indonesian | other | |

Inside a branch, write `\|` for a `|`. A branch cannot hold a `%` placeholder or another choice: put the
number outside, as above.

**Where the real number is known.** Fish Tycoon's counted lines (strings 69 to 75 on the Goals page,
"You have sold %d fish!" and the rest) choose with the real number: the game's sprintf there goes through
the translation first. So do the patcher's **counted texts**, whose English already holds a choice:
the counts' parts (`%d {%1: one=adult | other=adults}`), "%d doses left", "%d prices set.", the nursery
limit, and the Time Warp's and Revival Potion's popups (`Warp %d {%1: one=hour | other=hours} for $%d?...`).
Their notes say "choices use the real numbers". Everywhere else a choice takes its `other` branch. **Persons:** `{%1: m=... | f=... | o=...}` is part of the format, but neither game has a line
about a person whose sex it knows (no player sex; fish have no shown sex), so no line declares a person,
and a choice on a `%s` is refused. Plant Tycoon has no counted line at all: its counts are built from
pieces ("Remaining uses" and a number).

### Limits

Some lines are copied by the game or the patcher into a fixed space. Their notes say "at most N letters"
(an accented letter counts 2, as the game holds it in UTF-8 at most); a longer translation shows English,
so it can never overflow:

- game lines the game copies into a buffer (Fish Tycoon's cash and price labels and the Goals page lines,
  Plant Tycoon's store item titles and chemical names...): half as long again as the English, at least 8
  more;
- patcher texts kept in small spaces (Plant Tycoon's store tooltips, "Treated: $", the Extra Greenhouses
  labels...): the number given;
- every line: at most 1000.

"NEW PLAYER" (Fish Tycoon) and "New Player" (Plant Tycoon) are never translated: the game writes them into
the player list, where they mark an empty slot.

### Letters

How "Unicode Text.dll" draws a translation's letters (the shared Unicode spec's row 3): the game
font's own letter; a patcher-made one; else a letter drawn from Windows' fonts in the game font's
style, from the first font of the shared fallback chain (Segoe UI, Segoe UI Historic, Segoe UI Symbol,
Segoe UI Emoji, the CJK fonts, Nirmala UI, Ebrima ... Cambria Math, Noto if installed, then the fonts the
patcher ships) that has every code point; else an empty box, never "?". Arabic, Hebrew, the Indic
scripts, Thai and the other scripts that join or reorder are shaped and ordered by Windows a whole run
at a time. Neither game has a word wrapper: a long line is broken only where the translation has
`\n`, so keep lines as short as the English. Not yet seen in a running game.

The game draws bytes with its own fonts. Until the patcher's Unicode font settings draw more, a
translation is shown in Windows-1252: Latin-1 (French, German, Spanish, Portuguese, Italian, Dutch,
Nordic...) plus the usual quotes and dashes; any other letter shows as `?`. The editor warns about such
letters. With the Unicode setting on, Translations.dll passes the text on as UTF-8 (see below), so
Turkish, Polish, Russian, Japanese, Chinese... appear. Windows popups (Time Warp's) always get full
Unicode. "Unicode Text.dll" reads every text by one rule (the same as the patcher's tools): each whole
UTF-8 sequence is its character, any other byte its Windows-1252 character, one sequence at a time, so
a translated line holding a player's name (which the game keeps one byte for a Windows-1252 character,
UTF-8 for any other) draws correctly too.

### Not translated

Fish species, fins and bodies, plant flowers and foliage, bug names and the like are names the games build
from their own data, not from the string table: they stay as they are. The patches' own names are
translated: a DS species' name is its fin word and body word ("Tiger " + "Shark"; at most 15 and 16 letters,
so the two always fit the game's 31), and a new flower's is its flower word and foliage word ("Nightingale" +
" " + "Fern"; at most 24 each). The foliage words are used only for the new flowers. Fish Tycoon has a German mode: a
chosen translation replaces the game's lines in either mode, while a patcher text that has a German
version keeps it in German mode.

## Sharing

### The public folder

Translations live in `translations/fish/` and `translations/plant/` on GitHub, one file per language,
named after its language code: `fr.tsv`, `ja.tsv`, `pt-BR.tsv` (the name all of the owner's patchers
use). When that language is already there, a new file is `<code>-<credit slug>.tsv` (`fr-ann-lee.tsv`,
then `fr-ann-lee-2.tsv`...): the slug is the credit name in lower-case ASCII letters, digits and hyphens,
at most 40 letters, so nobody's file is overwritten. Older `<Game title> - <language>.txt` files are still
read everywhere.

Anyone can add one with GitHub's **Add file**, **Upload files** (without write access GitHub opens a pull
request automatically); [translations/README.md](../translations/README.md) walks through it. Each pull
request touching the folder is checked in two steps, and both comment their result on it:

1. **VirusTotal** (`scripts/virustotal_scan.py`): each file must be a UTF-8 `.tsv` (or `.txt`) of at most
   2 MB in `fish/` or `plant/`; anything else is refused. Then its SHA-256 is looked up on VirusTotal, or
   the file is uploaded and the analysis awaited. Any engine reporting it malicious or suspicious fails
   the check and is named; no answer, a timeout or no key also fails ("not scanned").
2. **The translation check** (`scripts/check_translation_pr.py`): format, keys, placeholders, person
   and number choices, email addresses, and that the name matches the `@code` row, each problem with
   its line.

The owner accepts by merging (the `accept-translation` label runs both again). Files are scanned once
more after they reach main.

A check speaks only for the commit it checked, and its comment names that commit. A newer push
cancels the older run, and the scripts ask GitHub again which commit the pull request is at after
fetching, after scanning and just before commenting; when it moved, the older run comments nothing and
fails. For Share on GitHub... the file committed is exactly the file scanned: the written file (with
its credit row) is scanned again and committed only when its SHA-256 matches, and the issue is read
again just before the pull request is pushed (edited, unlabelled or closed: nothing is pushed).

Every file sent in (a pull request or Share on GitHub...) is also sent to VirusTotal, where VirusTotal's partners can see it: one more reason never to put private details in a translation.

### Share on GitHub...

The Translations window says: "If you want to share your translation, consider going to the Patcher's
GitHub page and adding it!" -- How: press **Share on GitHub...**, drag the file in, press **Submit**.

Share on GitHub... first asks whether you want to continue (No changes nothing), then asks for the
**credit name** you want shown with the translation: you type it every time, it is public, and the patcher
never fills it in (not from git, Windows, GitHub or a save). **Email addresses are never saved and are
rejected from translation files.** Then the patcher writes a copy with that credit into
`translations\Shared`, shows it in its folder and opens GitHub's translation form with the game and
language filled in: drag the file into the form and press Submit.

You need a free GitHub account: https://github.com/signup

When the owner accepts it (the `accept-translation` label), a GitHub Action first sends the file to
VirusTotal (a flagged or unscanned file is refused with a comment naming the engines, and no pull request
is opened), then downloads it again, checks it is the file that was scanned, checks it as data only with
the patcher's own validator, and opens a pull request adding it to the public folder as
`translations/<game>/<code>.tsv` (or `<code>-<credit slug>.tsv`), credited only to the typed credit name;
if something is wrong it comments the problems instead. Accepted translations ship in the next release
(except "(TEST)" files: a language or credit starting with "(TEST)", or "test" in the file name) and can
be downloaded at once with Download from GitHub... Every file sent in (a pull request or Share on GitHub...) is also sent to VirusTotal, where VirusTotal's partners can see it: one more reason never to put private details in a translation.

## For developers

- `src/translation_format.py`: the format (reading, writing, placeholders, choices, CLDR plural rules,
  email refusal, coverage).
- `src/translation_strings.py`: every line a translation can replace, with its limit; the game lines are
  read from the player's own executable (the patcher never ships the games' text).
- `native/ftfp_translations` builds `Translations.dll` (`scripts/build_ftfp_translations.ps1`, after
  `scripts/build_translations_headers.py`). It is a loader tail (`"loader_tail"`, `src/ds_fish_loader.py` `with_tails`): the startup loader loads it after every other companion and after "Unicode Text.dll", and the setting adds no executable pins.
  It replaces the head of the string lookup (Fish Tycoon 0x426FD0, Plant Tycoon 0x44CA70) with a jump to
  itself after checking it holds the stock code or another companion's jump (Plant Tycoon's Store Upgrades
  and Items already jumps from there; Translations.dll calls that jump), patches Fish Tycoon's five Goals
  sprintf calls (0x4247FF, 0x424820, 0x424841, 0x424883, 0x4248AF), and points every relocation of a
  patcher DLL that refers to a translated text at its translation. It writes all of it or nothing.
- **Unicode contract.** Translations.dll writes Windows-1252 unless a DLL loaded before it exports
  `int __stdcall FtfpUnicodeTextActive(void)` returning nonzero ("Unicode Text.dll"); then it passes the
  translation on as UTF-8.
- **Counted texts.** `Translations.dll` exports `int __stdcall FtfpTranslateCounted(const void *english,
  int wide, const int *numbers, int count, void *out, int cap)`; `native/common/translated_count.h` is the
  callers' side. The DLL passes the counted English exactly as its key has it and the numbers; the reply is
  the translation with its choices made and each `%d` written, never past `cap`, or -1 (the DLL then writes
  its English as before). Counted texts are never pointed at through relocations. After pointing a DLL's
  texts, `Translations.dll` calls the DLL's `FtfpTranslationApplied` export if it has one (Unused Flowers
  builds its species names again).
- **Coverage.** `tests/test_translation_coverage.py` reads every string literal of every shipped patcher DLL
  (its sources, kept when the DLL holds it) and every text an executable patch writes; each must be a key's
  English, an English piece of a counted text (`COUNTED_FALLBACKS`) or in its allow-list with a reason (log
  lines, file names, ini keys, function names, fonts, German-mode texts).
- `scripts/pin_translations.py` pins the setting; `scripts/accept_translation.py` is the issue Action's
  check; `src/translation_public.py` holds the public folder's rules (names, pre-check, the data-only
  check), shared by `scripts/check_translation_pr.py` (the pull-request validator),
  `scripts/virustotal_scan.py` (the scan; its key only from the `VT_API_KEY` secret) and
  `src/translations_github.py` (Download from GitHub...).
- Workflows: `.github/workflows/translation-pr.yml` (pull_request_target: base-branch code only, the pull
  request's files fetched through the API as data, never checked out; minimal permissions),
  `accept-translation.yml` (scan, then accept) and `scan-translations.yml` (push to main).
- Tests: `tests/test_translation_format.py`, `tests/test_translations_runtime.py` (the DLL in Unicorn
  against the real games), `tests/test_translations_every_patch.py` (every patcher DLL and every counted text
  in Unicorn), `tests/test_translation_coverage.py`, `tests/test_translations_window.py`, `tests/test_translation_sharing.py`.
