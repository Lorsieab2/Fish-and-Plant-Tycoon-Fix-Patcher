#!/usr/bin/env python3
"""Unified offline interface for the Fish and Plant Tycoon fix patchers."""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import time
from types import ModuleType
from typing import Iterable

import fish_patcher
import plant_patcher


ROOT = Path(__file__).resolve().parents[1]


class CombinedPatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class GameSpec:
    id: str
    title: str
    vanilla_exe_name: str
    modded_exe_name: str
    modded_folder_name: str
    manifest_path: Path
    engine: ModuleType

    @property
    def exe_name(self) -> str:
        """Compatibility alias for the exact vanilla executable name."""
        return self.vanilla_exe_name


GAMES = {
    "fish": GameSpec(
        "fish",
        "Fish Tycoon",
        "Fish Tycoon.exe",
        "Fish Tycoon - Modded.exe",
        "Fish Tycoon - Modded",
        ROOT / "data" / "fish_manifest.json",
        fish_patcher,
    ),
    "plant": GameSpec(
        "plant",
        "Plant Tycoon",
        "Plant Tycoon.exe",
        "Plant Tycoon - Modded.exe",
        "Plant Tycoon - Modded",
        ROOT / "data" / "plant_manifest.json",
        plant_patcher,
    ),
}


def game_spec(game_id: str) -> GameSpec:
    try:
        return GAMES[game_id]
    except KeyError as exc:
        raise CombinedPatchError(f"Unknown game: {game_id}") from exc


def load_manifest(game_id: str) -> dict:
    spec = game_spec(game_id)
    return spec.engine.read_json(spec.manifest_path)


def patch_settings(game_id: str) -> dict[str, dict]:
    spec = game_spec(game_id)
    return spec.engine.manifest_settings(load_manifest(game_id))


def default_output_dir(game_id: str, vanilla_dir: str | Path) -> Path:
    spec = game_spec(game_id)
    vanilla = Path(vanilla_dir).expanduser()
    return vanilla.parent / spec.modded_folder_name


def output_dir_at(game_id: str, parent_dir: str | Path) -> Path:
    """Return the exact per-game modded folder beneath a chosen location."""
    spec = game_spec(game_id)
    return Path(parent_dir).expanduser() / spec.modded_folder_name


def find_game_in_parent(game_id: str, parent_dir: str | Path) -> list[Path]:
    """Find exact vanilla EXE matches in a parent or its immediate children."""
    spec = game_spec(game_id)
    root = Path(parent_dir).expanduser()
    if not root.is_dir():
        return []
    candidates = [root / spec.vanilla_exe_name]
    candidates.extend(
        child / spec.vanilla_exe_name
        for child in root.iterdir()
        if child.is_dir()
    )
    return [candidate for candidate in candidates if candidate.is_file()]


# --- Automatic game discovery -------------------------------------------------
#
# The scan only ever reads directory listings.  It never opens or writes a game
# file, so an interrupted scan cannot leave anything behind.

SKIPPED_DIR_NAMES = {
    "$recycle.bin",
    "appdata",
    "application data",
    "config.msi",
    "node_modules",
    "onedrivetemp",
    "perflogs",
    "programdata",
    "recovery",
    "system volume information",
    "temp",
    "tmp",
    "windows",
    "winsxs",
    ".git",
}

# Folders that hold a finished modded copy are skipped so a previous run of the
# patcher can never be offered back as a vanilla source.
MODDED_FOLDER_SUFFIX = "- modded"

@dataclass(frozen=True)
class ScanResult:
    """Outcome of one automatic search for installed games."""

    matches: dict[str, list[Path]]
    folders_scanned: int
    complete: bool

    def found(self, game_id: str) -> list[Path]:
        return self.matches.get(game_id, [])

    @property
    def any_found(self) -> bool:
        return any(self.matches.values())


DEFAULT_SCAN_DEPTH = 3
DEFAULT_SCAN_LIMIT = 12000
DEFAULT_SCAN_SECONDS = 45.0


def _drive_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name == "nt":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            candidate = Path(f"{letter}:/")
            try:
                if candidate.is_dir():
                    roots.append(candidate)
            except OSError:
                continue
    else:
        roots.append(Path("/"))
    return roots


def candidate_search_roots() -> list[Path]:
    """Return the likely install locations, most specific first.

    Only the places an LDW download or its installer normally lands are
    searched.  Storefront library folders are deliberately not listed: the
    supported builds are the free Windows downloads from LDW's own site, and no
    other distribution has been checked against the pinned identities.

    Whole drives are deliberately excluded.  The list stays small enough that a
    scan finishes in a couple of seconds on a normal machine.
    """
    home = Path.home()
    roots: list[Path] = [
        home / "Downloads",
        home / "Desktop",
        home / "Documents",
        home / "Games",
        home / "AppData" / "Local" / "Programs",
    ]
    for drive in _drive_roots():
        roots.extend(
            [
                drive / "Program Files (x86)",
                drive / "Program Files",
                drive / "Games",
            ]
        )
    # Cloud-synced folders answer slowly, so they are searched last.
    roots.extend(
        [
            home / "OneDrive" / "Desktop",
            home / "OneDrive" / "Documents",
            home / "OneDrive" / "Downloads",
        ]
    )
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root).casefold()
        if key in seen:
            continue
        seen.add(key)
        try:
            if root.is_dir():
                unique.append(root)
        except OSError:
            continue
    return unique


def _is_skipped_dir(directory: Path) -> bool:
    name = directory.name.casefold()
    if name in SKIPPED_DIR_NAMES or name.startswith("$"):
        return True
    return name.endswith(MODDED_FOLDER_SUFFIX)


def scan_for_games(
    roots: Iterable[str | Path] | None = None,
    *,
    max_depth: int = DEFAULT_SCAN_DEPTH,
    scan_limit: int = DEFAULT_SCAN_LIMIT,
    time_budget: float = DEFAULT_SCAN_SECONDS,
    on_progress=None,
) -> ScanResult:
    """Search likely locations for the exact vanilla executable of each game.

    Returns one deduplicated, sorted list of vanilla game folders per game id,
    plus whether the walk finished instead of hitting one of its budgets.
    ``on_progress`` is called with each folder about to be listed so a GUI can
    show what the scan is doing without the scan knowing anything about Tk.
    The folder budget and the time budget both stop the walk early, so a huge
    or slow (cloud-synced, network) location can never hang the patcher.
    """
    search_roots = (
        [Path(root).expanduser() for root in roots]
        if roots is not None
        else candidate_search_roots()
    )
    wanted = {
        spec.vanilla_exe_name.casefold(): game_id for game_id, spec in GAMES.items()
    }
    found: dict[str, list[Path]] = {game_id: [] for game_id in GAMES}
    # Depth each folder was last listed at.  A folder reached again from a
    # nearer root, which happens whenever one search root sits inside another,
    # is listed again so its remaining depth is not inherited from the longer
    # route.
    seen_dirs: dict[str, int] = {}
    visited = 0

    deadline = time.monotonic() + time_budget if time_budget > 0 else None
    complete = True
    stack: list[tuple[Path, int]] = [(root, 0) for root in reversed(search_roots)]
    while stack:
        if visited >= scan_limit or (
            deadline is not None and time.monotonic() > deadline
        ):
            complete = False
            break
        directory, depth = stack.pop()
        key = str(directory).casefold()
        if seen_dirs.get(key, max_depth + 1) <= depth:
            continue
        seen_dirs[key] = depth
        visited += 1
        if on_progress is not None:
            on_progress(directory)
        try:
            entries = list(directory.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            try:
                if entry.is_dir():
                    if depth + 1 <= max_depth and not _is_skipped_dir(entry):
                        stack.append((entry, depth + 1))
                    continue
                game_id = wanted.get(entry.name.casefold())
                if game_id and entry.name == GAMES[game_id].vanilla_exe_name:
                    found[game_id].append(entry.parent)
            except OSError:
                continue

    return ScanResult(
        matches={
            game_id: sorted(
                {str(path): path for path in matches}.values(),
                key=lambda path: str(path).casefold(),
            )
            for game_id, matches in found.items()
        },
        folders_scanned=visited,
        complete=complete,
    )


def _namespace(
    game_id: str,
    vanilla_dir: str | Path,
    output_dir: str | Path,
    enabled: Iterable[str],
    dry_run: bool,
) -> argparse.Namespace:
    spec = game_spec(game_id)
    return argparse.Namespace(
        game_dir=str(Path(vanilla_dir).expanduser()),
        manifest=str(spec.manifest_path),
        output_dir=str(Path(output_dir).expanduser()),
        dry_run=dry_run,
        enable=sorted(set(enabled)),
        disable=None,
        disable_all=True,
    )


def run_game(
    game_id: str,
    vanilla_dir: str | Path,
    output_dir: str | Path,
    enabled: Iterable[str],
    *,
    dry_run: bool,
) -> dict:
    spec = game_spec(game_id)
    args = _namespace(game_id, vanilla_dir, output_dir, enabled, dry_run)
    try:
        result = int(spec.engine.apply_manifest(args))
    except Exception as exc:
        raise CombinedPatchError(f"{spec.title}: {exc}") from exc
    if result != 0:
        raise CombinedPatchError(f"{spec.title}: patch engine returned {result}")
    summary = getattr(args, "last_apply_summary", None)
    if not isinstance(summary, dict):
        raise CombinedPatchError(f"{spec.title}: patch engine returned no summary")
    return summary


def run_games(
    configs: dict[str, dict],
    *,
    dry_run: bool,
) -> list[dict]:
    ordered = [game_id for game_id in GAMES if game_id in configs]
    if not ordered:
        raise CombinedPatchError("No games were selected.")

    # Validate and render every exact input before any output folder is written.
    preflight: list[dict] = []
    for game_id in ordered:
        config = configs[game_id]
        preflight.append(
            run_game(
                game_id,
                config["vanilla_dir"],
                config["output_dir"],
                config.get("enabled", ()),
                dry_run=True,
            )
        )
    if dry_run:
        return preflight

    results = []
    for game_id in ordered:
        config = configs[game_id]
        results.append(
            run_game(
                game_id,
                config["vanilla_dir"],
                config["output_dir"],
                config.get("enabled", ()),
                dry_run=False,
            )
        )
    return results


def capture_run(configs: dict[str, dict], *, dry_run: bool) -> tuple[list[dict], str]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        results = run_games(configs, dry_run=dry_run)
    return results, stream.getvalue()


def restore_game(
    game_id: str,
    backup_dir: str | Path,
    output_dir: str | Path,
) -> str:
    spec = game_spec(game_id)
    args = argparse.Namespace(
        backup_dir=str(Path(backup_dir).expanduser()),
        output_dir=str(Path(output_dir).expanduser()),
    )
    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            result = int(spec.engine.restore_backup(args))
    except Exception as exc:
        raise CombinedPatchError(f"{spec.title}: {exc}") from exc
    if result != 0:
        raise CombinedPatchError(f"{spec.title}: restore engine returned {result}")
    return stream.getvalue()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="Fish & Plant Tycoon Fix Patcher")
    parser.add_argument("--game", choices=tuple(GAMES), required=True)
    parser.add_argument("--vanilla-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--enable", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output_dir or default_output_dir(args.game, args.vanilla_dir)
    try:
        results = run_games(
            {
                args.game: {
                    "vanilla_dir": args.vanilla_dir,
                    "output_dir": output,
                    "enabled": args.enable,
                }
            },
            dry_run=not args.apply,
        )
    except CombinedPatchError as exc:
        print(f"PATCH ERROR: {exc}")
        return 2
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
