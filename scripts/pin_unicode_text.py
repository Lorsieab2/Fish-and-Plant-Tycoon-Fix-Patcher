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
SETTING_ID = "unicode_ingame_fonts"
SYSTEM_ID = "unicode_system_font"          # Use Unicode Font (overrides in-game fonts)
PASTE_ID = "copy_paste_text_boxes"          # Copy and Paste in Text Boxes
DLL = "Unicode Text.dll"

GAMES = {
    "fish": {
        "manifest": ROOT / "data" / "fish_manifest.json",
        "source": "assets/fish_tycoon_unicode",
        "folder": "Fish Tycoon Fix Patcher DLLs",
        "typing": "Typing in the game (a player's name, any text box), any letter of any script goes in "
                  "(AltGr letters, the emoji panel and input methods too); the game took only plain ASCII. "
                  "Names can be up to 300 letters.",
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
                  "(an input method's text too); the game dropped everything but plain ASCII. Names can be up "
                  "to 300 letters.",
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
        "summary": "Type and show names in any script (é ñ ß, Ç ğ İ, 山田, emoji ...) up to 300 letters, drawn in "
                   "the game's own fonts; letters a font lacks are made for it in its style or drawn from "
                   "Windows' fonts.",
        "description": (
            f"{game['typing']} {game['fonts']} Any other letter (Turkish, Japanese, Chinese, Korean, "
            "cuneiform, emoji ...) is drawn from Windows' fonts at the font's size and in the text's colour "
            "(colour emoji in their own colours). The save keeps each name's first 31 letters as the game keeps names (one "
            "byte a letter, '?' for a letter Latin-1 has not), so its layout is unchanged, and the full name "
            "beside it (Fix Patcher Data\\Names <slot>.dat); the patcher's tools (Rename Players, Copy "
            "Player Slot, the Breeding Guide and Picture Studio) read and write such names too. "
            f"{game['older']}"
        ),
        "category": "main",
        "default": True,
        "separate_output": True,
    }


def companion(game: dict) -> dict:
    source = ROOT / game["source"]
    files = []
    for path in [source / DLL] + sorted((source / "Images").glob("*_unicode.png")):
        data = path.read_bytes()
        relative = path.relative_to(source).as_posix()
        destination = f"{game['folder']}/{DLL}" if path.name == DLL else relative
        files.append({"path": relative, "destination": destination, "size": len(data),
                      "sha256": hashlib.sha256(data).hexdigest().upper()})
    return {"source": game["source"], "loader_tail": DLL, "files": files}


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
            "the font chosen beside this setting in the patcher (Segoe UI unless you pick another), then, for a "
            "letter it lacks, the fonts for other scripts (Yu Gothic, Meiryo, Microsoft YaHei, Malgun Gothic, "
            "Segoe UI Historic, Segoe UI Emoji ...), at the game fonts' line heights and in the game's colours "
            "(colour emoji in their own colours). The game's own fonts and pictures are not changed. Names are kept as with "
            "Render Unicode with In-Game Fonts (the first 31 letters in the save, the full name beside it), and "
            "the two settings cannot both be on. Runs as the same Unicode Text.dll, set by the "
            "\"Unicode Text.ini\" the patcher writes beside it."
        ),
        "category": "main",
        "default": False,
        "separate_output": True,
        "conflicts_settings": [SETTING_ID],
    }


def system_companion(game: dict) -> dict:
    data = (ROOT / game["source"] / DLL).read_bytes()
    return {"source": game["source"], "loader_tail": DLL, "files": [{
        "path": DLL, "destination": f"{game['folder']}/{DLL}", "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest().upper()}]}


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
            "Ctrl+C or Ctrl+Insert copies the box's whole text (a player's full name) and Ctrl+X copies it "
            "and empties the box. A paste goes in as if typed letter by letter: line breaks and tabs become "
            "spaces, other control characters are left out, the box keeps its own limit (300 letters for a "
            "name) and its own letters (digits only in a price box), and a letter is never cut in half. With "
            "Render Unicode with In-Game Fonts or Use Unicode Font any script goes in; without them only "
            "what the game's own box takes from the keyboard (plain ASCII letters, digits and symbols). "
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
        paste["companion"] = system_companion(game)
        put(manifest, paste)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{game_id}: {SETTING_ID} with {len(entry['companion']['files'])} files, {SYSTEM_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
