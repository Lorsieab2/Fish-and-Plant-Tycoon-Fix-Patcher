"""Pin the "Translations" setting into both manifests.

    python -X utf8 scripts/pin_translations.py "<vanilla Fish Tycoon folder>" "<vanilla Plant Tycoon folder>" [--files-only]

Run after rebuilding "Translations.dll" (scripts/build_ftfp_translations.ps1), and again after any
other script that adds or re-pins combinations (it re-pins every combination with the setting from
the ones without it). It

  * records assets/translations/Translations.dll by size and SHA-256, copied to each game's
    "<Game> Tycoon Fix Patcher DLLs" folder;
  * pins the output executable of every combination with the setting: its startup loader loads
    "Translations.dll" last (src/ds_fish_loader.py, FISH_TRANSLATIONS / PLANT_TRANSLATIONS), so
    every combination with it has its own pin.

--files-only re-records the DLL and leaves every pin as it is. Combinations without the setting
are left exactly as they are: with it off the patcher writes the same bytes as before.
"""

from __future__ import annotations

import gc
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ds_fish_loader  # noqa: E402
import fish_patcher  # noqa: E402
import plant_patcher  # noqa: E402

SOURCE = "assets/translations"
SETTING_ID = ds_fish_loader.TRANSLATIONS_SETTING
DLL_NAME = ds_fish_loader.TRANSLATIONS_DLL
GAMES = {"fish": ("Fish Tycoon", "Fish Tycoon.exe"), "plant": ("Plant Tycoon", "Plant Tycoon.exe")}


def setting(game: str) -> dict:
    title = GAMES[game][0]
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
    folder = ds_fish_loader.PATCHER_FILES_FOLDER if game == "fish" else ds_fish_loader.PLANT.patcher_files_folder
    # "loader_tail": the Unicode work's loader (ds_fish_loader.with_tails) loads tail DLLs after every other
    # companion, Unicode Text.dll first, so Translations.dll sees FtfpUnicodeTextActive. Without that
    # loader, fish_profile / plant_profile put Translations.dll last themselves.
    return {"source": SOURCE, "startup_loader": True, "loader_tail": DLL_NAME, "files": [
        {"path": DLL_NAME, "destination": f"{folder}/{DLL_NAME}", "size": len(data), "sha256": sha256(data)}]}


def pin(game: str, vanilla_folder: Path | None) -> int:
    path = ROOT / "data" / f"{game}_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entry = setting(game)
    entry["companion"] = companion(game)
    ids = [s["id"] for s in manifest["settings"]]
    if SETTING_ID in ids:
        manifest["settings"][ids.index(SETTING_ID)] = entry
    else:
        manifest["settings"].append(entry)
    added = 0
    if vanilla_folder is not None:
        vanilla = (vanilla_folder / GAMES[game][1]).read_bytes()
        profile = ds_fish_loader.fish_profile if game == "fish" else ds_fish_loader.plant_profile
        pins = {k: v for k, v in manifest["patched_sha256_by_settings"].items() if SETTING_ID not in k.split(",")}
        for key in list(pins) + [""]:
            enabled = (set(key.split(",")) if key else set()) | {SETTING_ID}
            if fish_patcher.settings_key(enabled) in pins:
                continue
            patcher = fish_patcher if game == "fish" else plant_patcher
            patched, _ = patcher.apply_patch_bytes(vanilla, patcher.active_patch_records(manifest, enabled))
            patched, _ = ds_fish_loader.append_startup_loader(patched, profile(enabled))
            pins[fish_patcher.settings_key(enabled)] = sha256(patched)
            added += 1
            del patched
            if added % 2000 == 0:
                gc.collect()
                print(f"{game}: {added} combinations...", flush=True)
        manifest["patched_sha256_by_settings"] = dict(sorted(pins.items(),
                                                             key=lambda kv: (len(kv[0].split(",")), kv[0])))
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return added


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--files-only"]
    files_only = len(args) != len(sys.argv) - 1
    if len(args) != 2:
        raise SystemExit(__doc__)
    for game, folder in zip(("fish", "plant"), args):
        added = pin(game, None if files_only else Path(folder))
        print(f"{game}: pinned {DLL_NAME} and {added} executable combinations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
