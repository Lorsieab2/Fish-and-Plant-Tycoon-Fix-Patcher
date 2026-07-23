#!/usr/bin/env python3
"""Manifest-driven offline patcher for the supported Windows Fish Tycoon build."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
from typing import Any
from datetime import datetime, timezone


class PatchError(RuntimeError):
    pass


EXCLUDED_OUTPUT_NAMES = {"fish tycoon - copy.exe"}


def excluded_output_files(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name.casefold() in EXCLUDED_OUTPUT_NAMES}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PatchError(f"Could not read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PatchError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def parse_int(value: Any, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError as exc:
            raise PatchError(f"{field} is not a valid integer: {value}") from exc
    raise PatchError(f"{field} must be an integer or 0x-prefixed string.")


def parse_hex(value: Any, field: str) -> bytes:
    if not isinstance(value, str):
        raise PatchError(f"{field} must be a hexadecimal string.")
    text = "".join(value.split())
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise PatchError(f"{field} contains invalid hexadecimal bytes.") from exc


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def pe_identity(data: bytes) -> dict[str, int]:
    if len(data) < 0x100 or data[:2] != b"MZ":
        raise PatchError("Target is not a valid DOS/PE executable.")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 0x58 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise PatchError("Target does not contain a valid PE header.")
    machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
    timestamp = struct.unpack_from("<I", data, pe_offset + 8)[0]
    optional_magic = struct.unpack_from("<H", data, pe_offset + 24)[0]
    image_base = struct.unpack_from("<I", data, pe_offset + 24 + 28)[0]
    return {
        "pe_offset": pe_offset,
        "machine": machine,
        "timestamp": timestamp,
        "optional_magic": optional_magic,
        "image_base": image_base,
    }


def validate_original_executable(exe: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    target = manifest.get("target")
    if not isinstance(target, dict):
        raise PatchError("Manifest target section is missing.")
    if not exe.is_file():
        raise PatchError(f"Required executable was not found: {exe}")
    data = exe.read_bytes()
    expected_size = parse_int(target.get("size"), "target.size")
    if len(data) != expected_size:
        raise PatchError(f"Unsupported Fish Tycoon.exe size: {len(data)}; expected {expected_size}.")
    actual_hash = sha256_bytes(data)
    expected_hash = str(target.get("sha256", "")).upper()
    if actual_hash != expected_hash:
        raise PatchError(
            "Unsupported Fish Tycoon.exe SHA-256.\n"
            f"Actual:   {actual_hash}\nExpected: {expected_hash}"
        )
    identity = pe_identity(data)
    checks = {
        "machine": parse_int(target.get("machine"), "target.machine"),
        "timestamp": parse_int(target.get("pe_timestamp"), "target.pe_timestamp"),
        "optional_magic": parse_int(target.get("optional_magic"), "target.optional_magic"),
        "image_base": parse_int(target.get("image_base"), "target.image_base"),
    }
    for key, expected in checks.items():
        if identity[key] != expected:
            raise PatchError(
                f"Unsupported PE {key}: 0x{identity[key]:X}; expected 0x{expected:X}."
            )
    return {
        "path": str(exe.resolve()),
        "size": len(data),
        "sha256": actual_hash,
        **{key: f"0x{value:X}" for key, value in identity.items()},
    }


def manifest_settings(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = manifest.get("settings", [])
    if not isinstance(raw, list):
        raise PatchError("Manifest settings must be a list.")
    result: dict[str, dict[str, Any]] = {}
    for index, setting in enumerate(raw):
        if not isinstance(setting, dict) or not isinstance(setting.get("id"), str):
            raise PatchError(f"settings[{index}] is invalid.")
        result[setting["id"]] = setting
    return result


def enabled_settings(manifest: dict[str, Any], args: argparse.Namespace) -> set[str]:
    settings = manifest_settings(manifest)
    enabled = {key for key, value in settings.items() if bool(value.get("default", False))}
    if getattr(args, "disable_all", False):
        enabled.clear()
    for key in getattr(args, "enable", None) or []:
        if key not in settings:
            raise PatchError(f"Unknown setting: {key}")
        enabled.add(key)
    for key in getattr(args, "disable", None) or []:
        if key not in settings:
            raise PatchError(f"Unknown setting: {key}")
        enabled.discard(key)
    return enabled


def active_patch_records(manifest: dict[str, Any], enabled: set[str]) -> list[dict[str, Any]]:
    raw = manifest.get("patches")
    if not isinstance(raw, list):
        raise PatchError("Manifest patches must be a list.")
    result: list[dict[str, Any]] = []
    for index, patch in enumerate(raw):
        if not isinstance(patch, dict):
            raise PatchError(f"patches[{index}] is invalid.")
        requires = patch.get("requires", [])
        if not isinstance(requires, list) or not all(isinstance(item, str) for item in requires):
            raise PatchError(f"patches[{index}].requires must be a string list.")
        excludes = patch.get("excludes", [])
        if not isinstance(excludes, list) or not all(isinstance(item, str) for item in excludes):
            raise PatchError(f"patches[{index}].excludes must be a string list.")
        if all(item in enabled for item in requires) and not any(item in enabled for item in excludes):
            result.append(patch)
    return result


def settings_key(enabled: set[str]) -> str:
    return ",".join(sorted(enabled))


def expected_patched_hash(manifest: dict[str, Any], enabled: set[str]) -> str:
    variants = manifest.get("patched_sha256_by_settings")
    if variants is not None:
        if not isinstance(variants, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in variants.items()):
            raise PatchError("patched_sha256_by_settings must be a string-to-string object.")
        return str(variants.get(settings_key(enabled), "")).upper()
    return str(manifest.get("patched_sha256", "")).upper()


def apply_patch_bytes(data: bytes, patches: list[dict[str, Any]]) -> tuple[bytes, list[dict[str, Any]]]:
    output = bytearray(data)
    summary: list[dict[str, Any]] = []
    occupied: list[tuple[int, int, str]] = []
    for index, patch in enumerate(patches):
        patch_id = str(patch.get("id", f"patch_{index}"))
        offset = parse_int(patch.get("offset"), f"patches[{index}].offset")
        expected = parse_hex(patch.get("expected"), f"patches[{index}].expected")
        replacement = parse_hex(patch.get("replacement"), f"patches[{index}].replacement")
        if len(expected) != len(replacement):
            raise PatchError(f"{patch_id}: expected and replacement lengths differ.")
        end = offset + len(expected)
        if offset < 0 or end > len(output):
            raise PatchError(f"{patch_id}: patch range is outside the executable.")
        for prior_start, prior_end, prior_id in occupied:
            if offset < prior_end and end > prior_start:
                raise PatchError(f"{patch_id}: overlaps {prior_id}.")
        actual = bytes(output[offset:end])
        if actual != expected:
            raise PatchError(
                f"{patch_id}: target bytes do not match at file offset 0x{offset:X}.\n"
                f"Actual:   {actual.hex(' ').upper()}\nExpected: {expected.hex(' ').upper()}"
            )
        output[offset:end] = replacement
        occupied.append((offset, end, patch_id))
        summary.append(
            {
                "id": patch_id,
                "offset": f"0x{offset:X}",
                "length": len(expected),
                "expected": expected.hex(" ").upper(),
                "replacement": replacement.hex(" ").upper(),
            }
        )
    return bytes(output), summary


def resolve_paths(args: argparse.Namespace, manifest: dict[str, Any]) -> tuple[Path, Path, Path]:
    game_dir = Path(args.game_dir).expanduser().resolve()
    target = manifest["target"]
    exe_name = str(target.get("exe_name", "Fish Tycoon.exe"))
    exe = game_dir / exe_name
    output_cfg = manifest.get("output", {})
    default_folder = str(output_cfg.get("default_folder_name", "Fish Tycoon - Fixed"))
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if getattr(args, "output_dir", None)
        else game_dir.parent / default_folder
    )
    if not game_dir.is_dir():
        raise PatchError(f"Vanilla game folder does not exist: {game_dir}")
    if output_dir == game_dir or is_within(output_dir, game_dir):
        raise PatchError("The modded output folder must be separate from the vanilla game folder.")
    return game_dir, exe, output_dir


def recognized_output(path: Path, manifest: dict[str, Any]) -> bool:
    marker = path / ".fish_tycoon_bug_fix_output.json"
    if not marker.is_file():
        return False
    try:
        value = read_json(marker)
    except PatchError:
        return False
    return value.get("manifest_id") == manifest.get("id")


def notify_windows_shell_file_changed(path: Path) -> bool:
    """Ask Explorer to discard a stale cached icon for the replaced EXE path."""
    if os.name != "nt":
        return False
    try:
        shell32 = ctypes.windll.shell32
        # SHCNE_UPDATEITEM, SHCNF_PATHW | SHCNF_FLUSH
        shell32.SHChangeNotify(0x00002000, 0x00001005, str(path), None)
        return True
    except Exception:
        return False


def apply_manifest(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = read_json(manifest_path)
    game_dir, vanilla_exe, output_dir = resolve_paths(args, manifest)
    identity = validate_original_executable(vanilla_exe, manifest)
    enabled = enabled_settings(manifest, args)
    patches = active_patch_records(manifest, enabled)
    original = vanilla_exe.read_bytes()
    patched, patch_summary = apply_patch_bytes(original, patches)
    expected_hash = expected_patched_hash(manifest, enabled)
    patched_hash = sha256_bytes(patched)
    if patches and not expected_hash:
        raise PatchError(f"Manifest has no expected output hash for enabled settings: {settings_key(enabled)}")
    if patches and patched_hash != expected_hash:
        raise PatchError(
            f"Patched output hash mismatch: {patched_hash}; expected {expected_hash}."
        )

    report = {
        "operation": "dry-run" if args.dry_run else "apply",
        "timestamp_utc": utc_now(),
        "manifest": str(manifest_path),
        "manifest_id": manifest.get("id"),
        "manifest_version": manifest.get("version"),
        "vanilla_game_dir": str(game_dir),
        "output_dir": str(output_dir),
        "target": identity,
        "enabled_settings": sorted(enabled),
        "patches": patch_summary,
        "output_exe_sha256": patched_hash,
    }
    if args.dry_run:
        args.last_apply_summary = report
        print(json.dumps(report, indent=2))
        print("DRY RUN PASS: exact executable identity and all patch bytes validated; no files written.")
        return 0

    output_parent = output_dir.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = output_parent / ".fish_tycoon_patch_backups" / stamp
    suffix = 1
    while backup_dir.exists():
        backup_dir = output_parent / ".fish_tycoon_patch_backups" / f"{stamp}_{suffix:02d}"
        suffix += 1
    backup_dir.mkdir(parents=True)
    backup_exe = backup_dir / vanilla_exe.name
    shutil.copy2(vanilla_exe, backup_exe)
    backup_manifest = {
        "format": 1,
        "created_utc": utc_now(),
        "manifest_id": manifest.get("id"),
        "original_game_dir": str(game_dir),
        "output_dir": str(output_dir),
        "exe_name": vanilla_exe.name,
        "original_sha256": identity["sha256"],
        "backup_exe": backup_exe.name,
    }
    write_json(backup_dir / "fish_tycoon_patch_backup_manifest.json", backup_manifest)

    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_parent))
    try:
        shutil.rmtree(staging)
        shutil.copytree(game_dir, staging, ignore=excluded_output_files)
        staged_exe = staging / vanilla_exe.name
        staged_exe.write_bytes(patched)
        if sha256_file(staged_exe) != patched_hash:
            raise PatchError("Staged executable failed its post-write SHA-256 check.")
        report["backup_dir"] = str(backup_dir)
        report["output_exe"] = str(output_dir / vanilla_exe.name)
        write_json(staging / ".fish_tycoon_bug_fix_output.json", {
            "manifest_id": manifest.get("id"),
            "manifest_version": manifest.get("version"),
            "created_utc": utc_now(),
            "vanilla_game_dir": str(game_dir),
            "backup_dir": str(backup_dir),
        })
        write_json(staging / "FishTycoonBugFixPatchLog.json", report)

        if output_dir.exists():
            if not recognized_output(output_dir, manifest):
                raise PatchError(
                    f"Output folder already exists and is not recognized as this patcher's output: {output_dir}"
                )
            previous = backup_dir / "previous_output"
            shutil.move(str(output_dir), str(previous))
        os.replace(staging, output_dir)
        report["base_game_icon_resources_preserved"] = True
        report["windows_shell_icon_refresh_requested"] = notify_windows_shell_file_changed(
            output_dir / vanilla_exe.name
        )
        write_json(output_dir / "FishTycoonBugFixPatchLog.json", report)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    print(json.dumps(report, indent=2))
    print(f"PATCH PASS: created separate fixed game folder: {output_dir}")
    args.last_apply_summary = report
    return 0


def restore_backup(args: argparse.Namespace) -> int:
    backup_dir = Path(args.backup_dir).expanduser().resolve()
    manifest_path = backup_dir / "fish_tycoon_patch_backup_manifest.json"
    backup = read_json(manifest_path)
    exe_name = str(backup.get("exe_name", "Fish Tycoon.exe"))
    backup_exe = backup_dir / str(backup.get("backup_exe", exe_name))
    expected_hash = str(backup.get("original_sha256", "")).upper()
    if not backup_exe.is_file() or sha256_file(backup_exe) != expected_hash:
        raise PatchError("Backup executable is missing or failed its SHA-256 check.")
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else Path(str(backup.get("output_dir", ""))).resolve()
    )
    if not output_dir.is_dir():
        raise PatchError(f"Restore output folder does not exist: {output_dir}")
    target = output_dir / exe_name
    temp = output_dir / f".{exe_name}.restore.tmp"
    shutil.copy2(backup_exe, temp)
    os.replace(temp, target)
    if sha256_file(target) != expected_hash:
        raise PatchError("Restored executable failed its SHA-256 check.")
    report = {
        "operation": "restore",
        "timestamp_utc": utc_now(),
        "backup_dir": str(backup_dir),
        "restored_exe": str(target),
        "sha256": expected_hash,
    }
    write_json(output_dir / "FishTycoonBugFixRestoreLog.json", report)
    print(json.dumps(report, indent=2))
    print(f"RESTORE PASS: restored original executable in {output_dir}")
    return 0


def list_settings(args: argparse.Namespace) -> int:
    manifest = read_json(Path(args.manifest).expanduser().resolve())
    for setting_id, value in manifest_settings(manifest).items():
        print(f"{setting_id}\tdefault={bool(value.get('default', False))}\t{value.get('name', '')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Fish Tycoon PC bug-fix patcher")
    commands = parser.add_subparsers(dest="command", required=True)
    apply_cmd = commands.add_parser("apply", help="Validate and create a separate patched game folder")
    apply_cmd.add_argument("--game-dir", required=True)
    apply_cmd.add_argument("--manifest", required=True)
    apply_cmd.add_argument("--output-dir")
    apply_cmd.add_argument("--dry-run", action="store_true")
    apply_cmd.add_argument("--enable", action="append")
    apply_cmd.add_argument("--disable", action="append")
    apply_cmd.add_argument("--disable-all", action="store_true")
    apply_cmd.set_defaults(func=apply_manifest)
    restore_cmd = commands.add_parser("restore", help="Restore an output EXE from a patcher backup")
    restore_cmd.add_argument("--backup-dir", required=True)
    restore_cmd.add_argument("--output-dir")
    restore_cmd.set_defaults(func=restore_backup)
    settings_cmd = commands.add_parser("settings", help="List manifest settings")
    settings_cmd.add_argument("--manifest", required=True)
    settings_cmd.set_defaults(func=list_settings)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PatchError as exc:
        print(f"PATCH ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"UNEXPECTED ERROR: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
