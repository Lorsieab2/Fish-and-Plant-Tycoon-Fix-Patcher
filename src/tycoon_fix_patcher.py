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


# --- Per-patch technical detail ----------------------------------------------


@dataclass(frozen=True)
class PatchDetail:
    """One byte-level change, described for a reader rather than a machine."""

    id: str
    file_offset: int
    virtual_address: int | None
    length: int
    note: str

    @property
    def where(self) -> str:
        if self.virtual_address is None:
            return f"file 0x{self.file_offset:X}"
        return f"VA 0x{self.virtual_address:X} (file 0x{self.file_offset:X})"


def _image_base(manifest: dict) -> int | None:
    target = manifest.get("target")
    if not isinstance(target, dict):
        return None
    try:
        return int(str(target.get("image_base")), 0)
    except (TypeError, ValueError):
        return None


def file_offset_to_va(manifest: dict, offset: int) -> int | None:
    """Map a file offset to a virtual address using the recorded section layout.

    Falls back to image base + offset, which holds for these two builds because
    every section's raw offset equals its RVA. Returns None if neither the
    layout nor an image base is recorded, rather than inventing an address.
    """
    base = _image_base(manifest)
    if base is None:
        return None
    layout = (manifest.get("target") or {}).get("section_layout")
    if isinstance(layout, list):
        for section in layout:
            try:
                raw = int(str(section["raw_offset"]), 0)
                size = int(str(section["raw_size"]), 0)
                rva = int(str(section["virtual_address"]), 0)
            except (KeyError, TypeError, ValueError):
                continue
            if raw <= offset < raw + size:
                return base + rva + (offset - raw)
    return base + offset


def setting_patch_details(game_id: str, setting_id: str) -> list[PatchDetail]:
    """Every byte-level change a single setting is responsible for.

    A patch is attributed to a setting when that setting appears in its
    `requires`. Variants that differ only by which other settings are also on
    are collapsed, so the reader sees each distinct change once. The PE
    checksum records are excluded; they are bookkeeping, not behaviour, and
    there is one per setting combination.
    """
    manifest = load_manifest(game_id)
    patches = manifest.get("patches")
    if not isinstance(patches, list):
        return []
    details: list[PatchDetail] = []
    seen: set[tuple[int, str]] = set()
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        identifier = str(patch.get("id", ""))
        if identifier.startswith("update_pe_checksum"):
            continue
        requires = patch.get("requires") or []
        if setting_id not in requires:
            continue
        try:
            offset = int(str(patch.get("offset")), 0)
        except (TypeError, ValueError):
            continue
        expected = "".join(str(patch.get("expected", "")).split())
        length = len(expected) // 2
        key = (offset, identifier.rsplit("_for_", 1)[0])
        if key in seen:
            continue
        seen.add(key)
        details.append(
            PatchDetail(
                id=identifier,
                file_offset=offset,
                virtual_address=file_offset_to_va(manifest, offset),
                length=length,
                note=str(patch.get("note", "")).strip(),
            )
        )
    details.sort(key=lambda item: item.file_offset)
    return details


def setting_checksum_note(game_id: str) -> str:
    """One line covering the checksum records, which are otherwise noise."""
    manifest = load_manifest(game_id)
    count = sum(
        1
        for patch in manifest.get("patches", [])
        if isinstance(patch, dict) and str(patch.get("id", "")).startswith("update_pe_checksum")
    )
    if not count:
        return ""
    return (
        f"Plus one of {count} PE checksum records, chosen to match whichever "
        "combination of settings you enable, so the executable stays internally "
        "consistent."
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
