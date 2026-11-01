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
            "(emoji in one colour). The save keeps each name's first 31 letters as the game keeps names (one "
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


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    for game_id, game in GAMES.items():
        path = game["manifest"]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        entry = setting(game)
        old = next((s for s in manifest["settings"] if s["id"] == SETTING_ID), None)
        for key in ("conflicts_settings",):
            if old is not None and key in old:
                entry[key] = old[key]
        entry["companion"] = companion(game)
        if old is None:
            manifest["settings"].append(entry)
        else:
            manifest["settings"][manifest["settings"].index(old)] = entry
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{game_id}: {SETTING_ID} with {len(entry['companion']['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
