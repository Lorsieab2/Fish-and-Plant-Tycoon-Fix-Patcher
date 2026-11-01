"""Pin the "Translations" setting into both manifests.

    python -X utf8 scripts/pin_translations.py

Run after rebuilding "Translations.dll" (scripts/build_ftfp_translations.ps1). It records
assets/translations/Translations.dll by size and SHA-256, copied to each game's
"<Game> Tycoon Fix Patcher DLLs" folder, as a loader tail ("loader_tail": src/ds_fish_loader.py,
with_tails; src/fish_patcher.py, build_executable): the startup loader loads it after every other
companion and after "Unicode Text.dll", and the setting is left out of the executable pins (the
executable without it must match its pin, then the loader gets Translations.dll added), so no
combination needs a new pin.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ds_fish_loader  # noqa: E402

SOURCE = "assets/translations"
SETTING_ID = ds_fish_loader.TRANSLATIONS_SETTING
DLL_NAME = ds_fish_loader.TRANSLATIONS_DLL
FOLDERS = {"fish": "Fish Tycoon Fix Patcher DLLs", "plant": "Plant Tycoon Fix Patcher DLLs"}
TITLES = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}

def setting(game: str) -> dict:
    title = TITLES[game]
    return {
        "id": SETTING_ID,
        "name": "Translations",
        "summary": "Plays the game in the language you choose on the Tools tab (Translations...): installed "
                   "translations and your own. English until you choose one.",
        "description": (
            f"Lets {title} show a translation: every text of the game's own string table and the patcher's "
            "own texts (store items, counts, popups). Choose the language on the Tools tab, Translations...: "
            "it applies from the next game start, with no patching again. \"English (original)\" leaves the "
            "game exactly as it is. A line the translation lacks, or one it got wrong, stays in English; the "
            "game never stops for a translation. Make your own there too (a built-in editor), add one you were "
            "sent, or share yours on the patcher's GitHub page. Text is shown in the game's fonts as Latin-1 "
            "(accents of French, German, Spanish...) unless a Unicode setting draws more. Runs as a companion "
            "DLL the game loads at start, after the others; saves are unchanged."
        ),
        "category": "main",
        "default": True,
        "separate_output": True,
    }


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def companion(game: str) -> dict:
    data = (ROOT / SOURCE / DLL_NAME).read_bytes()
    return {"source": SOURCE, "loader_tail": DLL_NAME, "files": [
        {"path": DLL_NAME, "destination": f"{FOLDERS[game]}/{DLL_NAME}", "size": len(data), "sha256": sha256(data)}]}


def pin(game: str) -> None:
    path = ROOT / "data" / f"{game}_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entry = setting(game)
    entry["companion"] = companion(game)
    ids = [s["id"] for s in manifest["settings"]]
    if SETTING_ID in ids:
        manifest["settings"][ids.index(SETTING_ID)] = entry
    else:
        manifest["settings"].append(entry)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    for game in ("fish", "plant"):
        pin(game)
        print(f"{game}: pinned {DLL_NAME} (a loader tail; no executable pins change)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())