"""Add (or refresh) the "Render Unicode with In-Game Fonts" setting in the fish and plant manifests.

    python scripts/pin_unicode_text.py

Run after scripts/build_unicode_assets.py and scripts/build_ftfp_<game>_unicode.ps1. The setting
ships "Unicode Text.dll" and the fonts' pictures (assets/<game>_tycoon_unicode). Its DLL is a
loader tail (src/ds_fish_loader.py, with_tails): the executable without it is checked against the
other settings' pins, then the loader gets the DLL added last, so it adds no pins of its own and
this script changes only the setting's own entry (and each file's size and SHA-256).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from unicode_data import NAME_BOX_BYTES as LIMIT  # noqa: E402
CHAIN = ('Segoe UI, Segoe UI Historic, Segoe UI Symbol, Segoe UI Emoji (in colour), the CJK fonts (Yu Gothic, Meiryo, Microsoft YaHei, Microsoft JhengHei, Malgun Gothic, SimSun-ExtB), Nirmala UI, Ebrima, Gadugi, Leelawadee UI ... Cambria Math, Noto if installed, then the fonts the patcher ships')
SETTING_ID = "unicode_ingame_fonts"
SYSTEM_ID = "unicode_system_font"          # Use Unicode Font (overrides in-game fonts)
PASTE_ID = "copy_paste_text_boxes"          # Copy and Paste in Text Boxes
DLL = "Unicode Text.dll"
DRAW_TEXT = ("A letter the game's fonts lack is drawn from Windows' fonts in that font's own style (its "
             "capital height, baseline, stroke weight, side bearings and shading), from the first font of the "
             "shared fallback chain that has every code point of it: Segoe UI, Segoe UI Historic, Segoe UI Symbol, Segoe UI Emoji (in colour), the CJK fonts (Yu Gothic, Meiryo, Microsoft YaHei, Microsoft JhengHei, Malgun Gothic, SimSun-ExtB), Nirmala UI, Ebrima, Gadugi, Leelawadee UI ... Cambria Math, Noto if installed, then the fonts the patcher ships. A letter with a combining accent "
             "that has a precomposed form is that letter; Arabic, Hebrew, the Indic scripts, Thai and the other "
             "scripts that join or reorder are shaped and ordered by Windows a whole run at a time, and a line "
             "that mixes left-to-right and right-to-left text is put in visual order as a whole (the Unicode bidi "
             "algorithm, by Windows), numbers in right-to-left text reading left to right; a letter no "
             "font has is an empty box in the font's style, never \"?\". Each name is fitted to the room the "
             "game's layout gives it, with an ellipsis. In a box that is not a name (" + "{boxes}" + "), a "
             "letter is refused when the text would be wider than the stock game allows there. The games have "
             "no word wrapper: text breaks only where it has a line break. Not yet seen in a running game.")
FONTS_TEXT = ("Every letter of Unicode 18.0 draws: after Windows' fonts come the fonts the patcher ships beside the DLL (GNU Unifont and Unifont Upper, Noto Serif Tangut, Noto Sans Cuneiform, and Unicode's Last Resort font, whose block placeholder stands for a letter no font has yet; all under the SIL Open Font License, loaded for the game only, never installed in Windows), and a letter with its marks, an emoji sequence or a flag is drawn and cut as one. "
              "A flag (Japan, the United States, England...) is drawn as a flag in colour, not as its two letters, from Twemoji Mozilla, also shipped beside the DLL and loaded for the game only (Twemoji artwork by Twitter, Inc and other contributors, CC-BY 4.0), which also draws the emoji Windows' own emoji font lacks.")

GAMES = {
    "fish": {
        "manifest": ROOT / "data" / "fish_manifest.json",
        "source": "assets/fish_tycoon_unicode",
        "folder": "Fish Tycoon Fix Patcher DLLs",
        "typing": "Typing in the game (a player's name, any text box), any letter of any script goes in "
                  "(AltGr letters, the emoji panel and input methods too); the game took only plain ASCII. "
                  f"Names can be up to {LIMIT:,} bytes as the save stores them, with no character limit (up to {LIMIT:,} plain letters, fewer when letters need more bytes; the same limit as the other Fun Patchers), counted in characters as you see them (a letter with its accents, an emoji with its skin tone or a flag is one), and Backspace removes one whole character.",
        "fonts": "All three of the game's fonts (Paddington 18 and 30, Triplex Sans Bold 16) get every Latin-1 "
                 "letter and symbol they lack, and paddington's empty boxes for % * + < = > [ \\ ] ^ { | } ~ "
                 "become real letters: accented letters are made from each font's own letters and accents, "
                 "the rest drawn in the font's size, baseline and weight. They are added to copies of the "
                 "fonts' pictures in the game's Images folder; the game's own pictures are not changed.",
        "boxes": "the registration boxes",
        "older": "A copy of the game without this setting shows each such letter as a blank (its fonts have "
                 "no letter for it) but loads and plays the save as always.",
    },
    "plant": {
        "manifest": ROOT / "data" / "plant_manifest.json",
        "source": "assets/plant_tycoon_unicode",
        "folder": "Plant Tycoon Fix Patcher DLLs",
        "typing": "Typing in the game (a player's name, any text box), any letter of any script goes in "
                  "(an input method's text too); the game dropped everything but plain ASCII. "
                  f"Names can be up to {LIMIT:,} bytes as the save stores them, with no character limit (up to {LIMIT:,} plain letters, fewer when letters need more bytes; the same limit as the other Fun Patchers), counted in characters as you see them (a letter with its accents, an emoji with its skin tone or a flag is one), and Backspace removes one whole character.",
        "fonts": "The game's font already has most of Latin-1; the no-break space and the inverted "
                 "exclamation mark (¡) are made for it in its style, in a copy of its picture in the Images "
                 "folder (the game's own picture is not changed).",
        "boxes": "the price box",
        "older": "A copy of the game without this setting shows these letters as well (its font has them), "
                 "except ¡, and loads and plays the save as always.",
    },
}


def setting(game: dict) -> dict:
    return {
        "id": SETTING_ID,
        "name": "Render Unicode with In-Game Fonts",
        "summary": f"Type and show names in any script (é ñ ß, Ç ğ İ, 山田, emoji ...) up to {LIMIT:,} bytes, drawn in "
                   "the game's own fonts; letters a font lacks are made for it in its style or drawn from "
                   "Windows' fonts.",
        "description": (
            f"{game['typing']} {game['fonts']} Any other letter (Turkish, Japanese, Chinese, Korean, "
            "cuneiform, emoji ...) is drawn from Windows' fonts at the font's size and in the text's colour "
            "(colour emoji in their own colours). The save itself is not changed: a name that fits the game's "
            "31-byte field is kept there as it is (one byte for a Windows-1252 character, UTF-8 for any other); "
            "a longer one is kept there as its short form (its start of whole characters and \"...\", or "
            "\"2...\", \"3...\" when two would start alike), so a copy of the game without the setting still "
            "loads and plays the save and shows the short form; the whole name is kept beside the save, in Fix "
            "Patcher Data\\Names <slot>.dat (the Names format the Fun Patchers share: one checked record a "
            "name, never removed). The patcher's tools (Rename Players, Copy Player Slot, Back Up and Restore "
            "Saves, the Breeding Guide and Picture Studio) read, write and carry such names too. "
            f"{DRAW_TEXT.replace('{boxes}', game['boxes'])} {FONTS_TEXT} {game['older']}"
        ),
        "category": "main",
        "default": True,
        "separate_output": True,
    }


def font_files(game: dict) -> list[dict]:
    """The fallback fonts and their licenses (data/unicode/fonts.json), into "<Game> Fix Patcher
    DLLs/Fonts" beside the DLL, which loads them for the game only (native/common/unicode_glyphs.h)."""
    source = ROOT / game["source"]
    doc = json.loads((ROOT / "data" / "unicode" / "fonts.json").read_text(encoding="utf-8"))
    fonts = doc["fonts"] + doc.get("colour_fonts", [])          # the chain's, then Twemoji Mozilla (flags)
    names = [f["file"] for f in fonts] + sorted(dict.fromkeys(f["license_file"] for f in fonts))
    files = []
    for name in names:
        data = (source / "Fonts" / name).read_bytes()
        files.append({"path": f"Fonts/{name}", "destination": f"{game['folder']}/Fonts/{name}", "size": len(data),
                      "sha256": hashlib.sha256(data).hexdigest().upper()})
    return files


def companion(game: dict) -> dict:
    source = ROOT / game["source"]
    files = []
    for path in [source / DLL] + sorted((source / "Images").glob("*_unicode.png")):
        data = path.read_bytes()
        relative = path.relative_to(source).as_posix()
        destination = f"{game['folder']}/{DLL}" if path.name == DLL else relative
        files.append({"path": relative, "destination": destination, "size": len(data),
                      "sha256": hashlib.sha256(data).hexdigest().upper()})
    return {"source": game["source"], "loader_tail": DLL, "files": files + font_files(game)}


def system_setting(game: dict) -> dict:
    """Use Unicode Font: the same DLL, told by the "Unicode Text.ini" the patcher writes beside it
    (src/fish_patcher.py, unicode_ini) to draw all text with the chosen font."""
    return {
        "id": SYSTEM_ID,
        "name": "Use Unicode Font (overrides in-game fonts)",
        "summary": "Draws all of the game's text with one Windows font you choose (Segoe UI unless you pick "
                   "another), any script, at the game's sizes and colours, instead of the game's own fonts.",
        "description": (
            f"{game['typing']} Every letter the game draws (names, menus, prices, a translation) is drawn with "
            "the font chosen in the patcher (the Tools tab's Unicode Font... window, with previews, or the Font "
            "box beside this setting; any installed font or a .ttf/.otf/.ttc file, copied beside the DLL and "
            "loaded for the game only; Segoe UI unless you pick another), then, for a letter it lacks, the "
            f"shared fallback chain ({CHAIN}). Each game font keeps its line height, baseline, weight and "
            "shading; the size is fitted so \"The quick brown fox jumps over the lazy dog 0123456789\" is as "
            "wide as the game draws it (within 60%-130%), in the game's colours (colour emoji in their own "
            f"colours). {FONTS_TEXT} The game's own fonts and pictures are not changed. Not yet seen in a running game. "
            "Names are kept as with "
            "Render Unicode with In-Game Fonts (the name or its short form with \"...\" in the save, the whole "
            "name beside it in Names <slot>.dat), and "
            "the two settings cannot both be on. Runs as the same Unicode Text.dll, set by the "
            "\"Unicode Text.ini\" the patcher writes beside it."
        ),
        "category": "main",
        "default": False,
        "separate_output": True,
        "conflicts_settings": [SETTING_ID],
    }


def system_companion(game: dict, fonts: bool = True) -> dict:
    """The DLL alone (Copy and Paste in Text Boxes draws nothing), or with the fallback fonts."""
    data = (ROOT / game["source"] / DLL).read_bytes()
    return {"source": game["source"], "loader_tail": DLL, "files": [{
        "path": DLL, "destination": f"{game['folder']}/{DLL}", "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest().upper()}] + (font_files(game) if fonts else [])}


def paste_setting(game: dict) -> dict:
    """Copy and Paste in Text Boxes: the same DLL, told by "Unicode Text.ini" (Paste=1; Mode=none when
    neither Unicode setting is on, so it installs only what the clipboard keys need)."""
    return {
        "id": PASTE_ID,
        "name": "Copy and Paste in Text Boxes",
        "summary": "Ctrl+V (or Shift+Insert) pastes into the game's text boxes, Ctrl+C (or Ctrl+Insert) copies "
                   "a box's whole text and Ctrl+X cuts it.",
        "description": (
            "While one of the game's text boxes has the typing cursor (a player's name, the new player's box, "
            f"{game['boxes']}), Ctrl+V or Shift+Insert pastes the Windows clipboard's text at the cursor, "
            "Ctrl+C or Ctrl+Insert copies the box's whole text (a player's whole name) and Ctrl+X copies it "
            "and empties the box once the copy succeeded; a held key does it once. A paste goes in as if typed "
            "character by character: it is composed first (NFC: a letter and its accent become the one "
            "accented letter), line breaks and tabs become spaces, other control characters are left out, the "
            f"box keeps its own limit ({LIMIT:,} bytes for a name, counted over the box's text and the paste) and "
            "its own characters (digits only in a price box), and a character is never cut in half (an accent "
            "that would join the box's last character and no longer fits is left out). At most 8,192 UTF-16 "
            "units are read from the clipboard. With Render Unicode with In-Game Fonts or Use Unicode Font any "
            "script goes in; with both off only what the game's own fonts draw and its box takes from the "
            "keyboard: printable ASCII (plain letters, digits and symbols). "
            "Runs as Unicode Text.dll (alone it changes only the text box's draw, to know which box has the "
            "cursor); the keys do nothing else in the game."
        ),
        "category": "main",
        "default": True,
        "separate_output": True,
    }


def put(manifest: dict, entry: dict) -> None:
    old = next((s for s in manifest["settings"] if s["id"] == entry["id"]), None)
    if old is None:
        manifest["settings"].append(entry)
    else:
        manifest["settings"][manifest["settings"].index(old)] = entry


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    for game_id, game in GAMES.items():
        path = game["manifest"]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        entry = setting(game)
        entry["conflicts_settings"] = [SYSTEM_ID]
        entry["companion"] = companion(game)
        put(manifest, entry)
        system = system_setting(game)
        system["companion"] = system_companion(game)
        put(manifest, system)
        paste = paste_setting(game)
        paste["companion"] = system_companion(game, fonts=False)
        put(manifest, paste)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{game_id}: {SETTING_ID} with {len(entry['companion']['files'])} files, {SYSTEM_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
