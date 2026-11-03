# Translations

Translation files for the Fish and Plant Tycoon Fix Patcher, one per game per language:
`fish/Fish Tycoon - <language>.txt` and `plant/Plant Tycoon - <language>.txt`. The format and how
to make, check and share a translation are in [docs/translations.md](../docs/translations.md).

These files live in the repository only: they are not packaged in the patcher's release ZIP. Get
one in the patcher with Tools tab, Translations..., "Download from GitHub...", or download the
`.txt` file from this folder and add it with "Add translation file...".

## (TEST) - French AI Translation

- `fish/Fish Tycoon - (TEST) - French AI Translation.txt`
- `plant/Plant Tycoon - (TEST) - French AI Translation.txt`

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
