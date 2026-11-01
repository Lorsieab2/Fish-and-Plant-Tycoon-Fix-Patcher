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
mod/tank_counts.fish~1f0a2b3c	Fish: 	Poissons : 	Tank Counts.dll
```

- Columns are separated by tabs: **Key**, **English**, **Translation**, **Notes**. Never change the Key or
  the English: the key holds the English's fingerprint, and a line whose English no longer matches shows
  English.
- `\n` is a line break, `\t` a tab, `\\` a backslash. Spaces at the start or end count.
- `strings/<id>` lines are the game's own string table (Fish Tycoon 248 lines, Plant Tycoon about 400);
  `mod/<dll>.<name>` lines are the patcher's own texts (store items and their descriptions, the counts,
  Time Warp's popups...).
- `#` starts a comment.

### Placeholders

- **printf conversions** (`%d` a number, `%s` a text, `%i`...): keep the same ones in the same order.
  Write `%%` for a percent sign.
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
the translation first. Everywhere else a choice takes its `other` branch (the patcher's own formatted
texts too). **Persons:** `{%1: m=... | f=... | o=...}` is part of the format, but neither game has a line
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

The game draws bytes with its own fonts. Until the patcher's Unicode font settings draw more, a
translation is shown in Windows-1252: Latin-1 (French, German, Spanish, Portuguese, Italian, Dutch,
Nordic...) plus the usual quotes and dashes; any other letter shows as `?`. The editor warns about such
letters. With the Unicode setting on, Translations.dll passes the text on as UTF-8 (see below), so
Turkish, Polish, Russian, Japanese, Chinese... appear. Windows popups (Time Warp's) always get full
Unicode.

### Not translated

Fish species, fins and bodies, plant flowers and foliage, bug names and the like are names the games build
from their own data, not from the string table: they stay as they are. Fish Tycoon has a German mode: a
chosen translation replaces the game's lines in either mode, while a patcher text that has a German
version keeps it in German mode.

## Sharing

The Translations window says: "If you want to share your translation, consider going to the Patcher's
GitHub page and adding it!" -- How: press **Share on GitHub...**, drag the file in, press **Submit**.

Share on GitHub... first asks whether you want to continue (No changes nothing), then asks for the
**credit name** you want shown with the translation: you type it every time, it is public, and the patcher
never fills it in (not from git, Windows, GitHub or a save). **Email addresses are never saved and are
rejected from translation files.** Then the patcher writes a copy with that credit into
`translations\Shared`, shows it in its folder and opens GitHub's translation form with the game and
language filled in: drag the file into the form and press Submit.

You need a free GitHub account: https://github.com/signup

When the owner accepts it (the `accept-translation` label), a GitHub Action downloads the file, checks it
as data only with the patcher's own validator, and opens a pull request adding it to `translations/<game>/`
credited only to the typed credit name; if something is wrong it comments the problems instead. Accepted
translations ship in the next release and appear in every player's language list.

## For developers

- `src/translation_format.py`: the format (reading, writing, placeholders, choices, CLDR plural rules,
  email refusal, coverage).
- `src/translation_strings.py`: every line a translation can replace, with its limit; the game lines are
  read from the player's own executable (the patcher never ships the games' text).
- `native/ftfp_translations` builds `Translations.dll` (`scripts/build_ftfp_translations.ps1`, after
  `scripts/build_translations_headers.py`). The startup loader loads it last (`src/ds_fish_loader.py`).
  It replaces the head of the string lookup (Fish Tycoon 0x426FD0, Plant Tycoon 0x44CA70) with a jump to
  itself after checking it holds the stock code or another companion's jump (Plant Tycoon's Store Upgrades
  and Items already jumps from there; Translations.dll calls that jump), patches Fish Tycoon's five Goals
  sprintf calls (0x4247FF, 0x424820, 0x424841, 0x424883, 0x4248AF), and points every relocation of a
  patcher DLL that refers to a translated text at its translation. It writes all of it or nothing.
- **Unicode contract.** Translations.dll writes Windows-1252 unless a DLL loaded before it exports
  `int __stdcall FtfpUnicodeTextActive(void)` returning nonzero ("Unicode Text.dll"); then it passes the
  translation on as UTF-8.
- `scripts/pin_translations.py` pins the setting; `scripts/accept_translation.py` is the Action's check.
- Tests: `tests/test_translation_format.py`, `tests/test_translations_runtime.py` (the DLL in Unicorn
  against the real games), `tests/test_translations_window.py`, `tests/test_translation_sharing.py`.
