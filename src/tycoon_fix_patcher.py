#!/usr/bin/env python3
"""Unified offline interface for the Fish and Plant Tycoon fix patchers."""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import io
import json
from pathlib import Path
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
    exe_name: str
    fixed_folder_name: str
    manifest_path: Path
    engine: ModuleType


GAMES = {
    "fish": GameSpec(
        "fish",
        "Fish Tycoon",
        "Fish Tycoon.exe",
        "Fish Tycoon - Fixed",
        ROOT / "data" / "fish_manifest.json",
        fish_patcher,
    ),
    "plant": GameSpec(
        "plant",
        "Plant Tycoon",
        "Plant Tycoon.exe",
        "Plant Tycoon - Fixed",
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
    return vanilla.parent / spec.fixed_folder_name


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
