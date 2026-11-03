# Translations

This is the public translations folder of the Fish and Plant Tycoon Fix Patcher. Everyone can download
from it, and everyone can add to it.

- `fish/`: Fish Tycoon translations
- `plant/`: Plant Tycoon translations

Each file is one language, named after its language code: `fr.tsv`, `ja.tsv`, `pt-BR.tsv`. If that
language is already here, a new file is named `<code>-<your credit name>.tsv` (for example
`fr-ann-lee.tsv`), so nobody's file is overwritten. Older files named `<Game title> - <language>.txt`
still work.

Accepted translations come with the patcher, and you can also download them with **Download from
GitHub...** in the patcher's Translations window. Files marked "(TEST)" are never put in the patcher;
you can get them only from this folder.

## Before you share

The patcher's Share on GitHub... button shows this, and it applies here too:

> This button allows you to share your game translation to the patcher's Public Github. IF ACCEPTED, everyone who uses this patcher will be able to see your translation in the game and your username will be included in the credits. Please DO NOT put ANY PRIVATE DETAILS YOU DO NOT WANT TO MAKE PUBLIC!
>
> Email addresses are never saved and are rejected from translation files.
>
> This feature is meant to be a community collaboration tool for game modding only.
>
> You will need a Github account to proceed. Continue?

Every file you send in is also sent to VirusTotal to be checked for viruses, and VirusTotal's partners
can see it. That is one more reason never to put private details in a translation.

## The easy way in

1. **Download a file.** Open `fish/` or `plant/`, click a file, then click the download button ("Download
   raw file"). To start a new language, use the patcher instead: Tools tab, **Translations...**, **Make a
   translation**. It writes a file with every English line in it.
2. **Translate it.** Use the patcher's built-in editor (the Make window, or **Edit...**), or any text
   editor such as Notepad. A spreadsheet works too: open the file as tab-separated text, and save it as
   tab-separated text in UTF-8.
3. **Type your credit name** in the file's header (see below).
4. **Name the file** after its language code, such as `fr.tsv`.
5. **Upload it.** On GitHub, open `translations/fish/` or `translations/plant/` and choose **Add file**,
   then **Upload files**. Drag your file in, write a short note, and press **Propose changes**. If you
   do not have write access to this repository (most people don't), GitHub makes a copy of it for you
   and opens a pull request automatically.

Or skip all of that: the patcher's **Share on GitHub...** button opens a ready-made form for you.

## What happens next

Every pull request that changes this folder is checked automatically, and the result is posted as a
comment on it:

1. **VirusTotal.** Each file has to be a UTF-8 `.tsv` file of at most 2 MB in `fish/` or `plant/`.
   Anything else is refused. Then it is sent to VirusTotal, and the check fails if any engine flags it,
   or if it could not be scanned at all.
2. **The translation check.** The format, the keys, the placeholders (`%d`, `%s`, `{name}`), the
   person and number choices, and email addresses. Each problem names its line.

The owner accepts a translation by merging the pull request. The "accept-translation" label runs the
checks again first. Accepted files are scanned again once they are in the repository.

## Your credit name

Near the top of the file is a row that starts with `@translator`. Type the name you want in the credits
in its third column, after two tabs:

```
@translator		Ann Lee
```

The credit name is public. Do not use an email address. A file containing one is refused.

## The file format, briefly

```
# Fish Tycoon - Français translation (format 1).
Key	English	Translation	Notes
@format	1	1
@game	Fish Tycoon
@language	English	Français
@code	en	fr
@translator		Ann Lee
strings/1~4ece2634	Age: 	Âge : 
strings/69~17a77e24	You have sold %d fish!	Vous avez vendu %d {%1: one=poisson | other=poissons} !	%1 (%d) = number
```

- UTF-8 text with tab-separated columns: **Key**, **English**, **Translation**, **Notes**. Only fill in
  **Translation**. Do not change the Key or the English.
- `@language` is the language's own name, and `@code` is its code (it must match the file name).
- Keep every placeholder: `%d`, `%s` and `{name}`. `\n` is a line break.
- `{%1: one=... | other=...}` chooses words by number, and `{SUBJECT: m=... | f=... | o=...}` chooses
  them by person.
- A line left empty stays in English.

The full guide is [docs/translations.md](../docs/translations.md).

## (TEST) - French AI Translation

- `fish/fr.tsv` (Fish Tycoon)
- `plant/fr.tsv` (Plant Tycoon)

**AI-made, for testing only.** These two files were machine-translated by an AI to test the
translation feature; no French speaker has reviewed them, so expect mistakes. They are
downloadable like any other translation. Credit: "(TEST) AI translation".

Every line of both templates is translated (the games' own lines, read from the vanilla games, and
every patch's text), with French plurals (`one` covers 0 and 1, `many` large round numbers,
`other` the rest), the placeholders of the English, every length limit, and no-break spaces
before `:` `;` `!` `?`. Kept in English on purpose: species-name words (the DS fish fin and body
words and the new flowers' names, like the games' own species names, which are never translated)
and words that are the same in French (OK, Normal, Options, Menu, Pollen, Stats, the version
number). "NEW PLAYER" is never in a translation.
