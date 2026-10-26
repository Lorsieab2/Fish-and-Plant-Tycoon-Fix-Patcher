#!/usr/bin/env python3
"""Manifest-driven offline patcher for the supported Windows Fish Tycoon build."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
from typing import Any
from datetime import datetime, timezone

import ds_fish_loader


# Shown whenever an executable fails the exact identity check, so the
# player is told which copy of the game is supported instead of being
# left with a bare hash mismatch.
SUPPORTED_SOURCE_HINT = (
    "This patcher supports only the free Windows download from "
    "https://ldw.com. Copies from other sources are not supported."
)


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


def make_writable(path: Path) -> None:
    """Clear the read-only attribute on every file beneath path.

    copytree keeps each file's attributes, so a game installed read-only
    produced a read-only staging copy: the copied vanilla EXE could not be
    deleted, patching failed, and the staging folder could not be cleaned up.
    The modded copy is the player's to run and re-patch, so it is writable.
    """
    for item in [path, *path.rglob("*")]:
        mode = item.stat().st_mode
        if not mode & stat.S_IWRITE:
            os.chmod(item, mode | stat.S_IWRITE)


def remove_tree(path: Path) -> None:
    """Delete a folder even when some of its files are read-only."""

    def retry_writable(function, name, _error):
        os.chmod(name, stat.S_IWRITE)
        function(name)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry_writable)
    else:
        shutil.rmtree(path, onerror=retry_writable)


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


def pe_sections(data: bytes, identity: dict[str, int]) -> dict[str, dict[str, int]]:
    pe_offset = identity["pe_offset"]
    section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    table_offset = pe_offset + 24 + optional_size
    table_end = table_offset + section_count * 40
    if table_end > len(data):
        raise PatchError("PE section table extends beyond the executable.")

    sections: dict[str, dict[str, int]] = {}
    for index in range(section_count):
        offset = table_offset + index * 40
        name = data[offset:offset + 8].split(b"\0", 1)[0].decode("ascii", errors="replace")
        raw_size = struct.unpack_from("<I", data, offset + 16)[0]
        raw_offset = struct.unpack_from("<I", data, offset + 20)[0]
        if raw_offset + raw_size > len(data):
            raise PatchError(f"PE section {name!r} extends beyond the executable.")
        sections[name] = {"offset": raw_offset, "size": raw_size}
    return sections


def validate_original_executable(exe: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    target = manifest.get("target")
    if not isinstance(target, dict):
        raise PatchError("Manifest target section is missing.")
    if not exe.is_file():
        raise PatchError(f"Required executable was not found: {exe}")
    data = exe.read_bytes()
    expected_size = parse_int(target.get("size"), "target.size")
    if len(data) != expected_size:
        raise PatchError(
            f"Unsupported Fish Tycoon.exe size: {len(data)}; expected {expected_size}.\n"
            f"{SUPPORTED_SOURCE_HINT}"
        )
    actual_hash = sha256_bytes(data)
    expected_hash = str(target.get("sha256", "")).upper()
    if actual_hash != expected_hash:
        raise PatchError(
            "Unsupported Fish Tycoon.exe SHA-256.\n"
            f"Actual:   {actual_hash}\nExpected: {expected_hash}\n"
            f"{SUPPORTED_SOURCE_HINT}"
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

    expected_resource = target.get("resource_section")
    if not isinstance(expected_resource, dict):
        raise PatchError("Manifest target.resource_section is missing.")
    resource_name = str(expected_resource.get("name", ""))
    resource = pe_sections(data, identity).get(resource_name)
    if resource is None:
        raise PatchError(f"Required PE resource section was not found: {resource_name}")
    expected_resource_offset = parse_int(
        expected_resource.get("offset"), "target.resource_section.offset"
    )
    expected_resource_size = parse_int(
        expected_resource.get("size"), "target.resource_section.size"
    )
    if resource["offset"] != expected_resource_offset or resource["size"] != expected_resource_size:
        raise PatchError(
            "Unsupported PE resource section layout: "
            f"offset 0x{resource['offset']:X}, size {resource['size']}; expected "
            f"offset 0x{expected_resource_offset:X}, size {expected_resource_size}."
        )
    resource_hash = sha256_bytes(
        data[resource["offset"]:resource["offset"] + resource["size"]]
    )
    expected_resource_hash = str(expected_resource.get("sha256", "")).upper()
    if resource_hash != expected_resource_hash:
        raise PatchError(
            "Unsupported PE resource section SHA-256.\n"
            f"Actual:   {resource_hash}\nExpected: {expected_resource_hash}"
        )
    return {
        "path": str(exe.resolve()),
        "size": len(data),
        "sha256": actual_hash,
        "resource_section_sha256": resource_hash,
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


def check_setting_requirements(manifest: dict[str, Any], enabled: set[str]) -> None:
    """A setting that builds on another (`requires_settings`) needs it on too."""
    settings = manifest_settings(manifest)
    for key in sorted(enabled):
        needed = settings[key].get("requires_settings", [])
        if not isinstance(needed, list) or not all(isinstance(item, str) for item in needed):
            raise PatchError(f"{key}: requires_settings must be a string list.")
        missing = [item for item in needed if item not in enabled]
        if missing:
            names = ", ".join(str(settings.get(item, {}).get("name", item)) for item in missing)
            raise PatchError(f"{settings[key].get('name', key)} needs {names}; turn that on too.")


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


def companion_setting_ids(manifest: dict[str, Any]) -> set[str]:
    """Settings that ship a runtime companion (a DLL and its files) with the game."""
    return {
        key for key, value in manifest_settings(manifest).items()
        if isinstance(value.get("companion"), dict)
    }


def needs_startup_loader(manifest: dict[str, Any], enabled: set[str]) -> bool:
    settings = manifest_settings(manifest)
    return any(
        bool(settings[setting_id]["companion"].get("startup_loader"))
        for setting_id in enabled & companion_setting_ids(manifest)
    )


def companion_plan(
    manifest: dict[str, Any], manifest_path: Path, enabled: set[str]
) -> list[dict[str, Any]]:
    """Validate every file an enabled companion setting copies into the game.

    Each file is pinned by size and SHA-256 in the manifest and must resolve
    inside the patcher, so a damaged or swapped release file is refused
    before anything is written. A companion file goes to its own game-relative
    destination: the DLL into the patcher's folder beside the executable,
    images into the game's Images folder (which the game reads before ft.dat).
    """
    root = manifest_path.parent.parent
    plan: list[dict[str, Any]] = []
    settings = manifest_settings(manifest)
    for setting_id in sorted(enabled & companion_setting_ids(manifest)):
        companion = settings[setting_id]["companion"]
        declared = Path(str(companion.get("source", "")))
        source = (root / declared).resolve()
        if declared.is_absolute() or not declared.parts or not is_within(source, root):
            raise PatchError(f"{setting_id}: companion source must be a folder inside the patcher: {declared}")
        files = companion.get("files")
        if not isinstance(files, list) or not files:
            raise PatchError(f"{setting_id}: companion.files must be a non-empty list.")
        for index, entry in enumerate(files):
            relative = Path(str(entry.get("path", "")))
            destination = Path(str(entry.get("destination", "")))
            for label, value in (("path", relative), ("destination", destination)):
                if not value.parts or value.is_absolute() or ".." in value.parts:
                    raise PatchError(f"{setting_id}: files[{index}] has an unsafe {label}: {value}")
            bundled = source / relative
            if not bundled.is_file():
                raise PatchError(f"{setting_id}: companion file is missing: {bundled}")
            expected_size = parse_int(entry.get("size"), f"{setting_id}.files[{index}].size")
            expected_hash = str(entry.get("sha256", "")).upper()
            if bundled.stat().st_size != expected_size or sha256_file(bundled) != expected_hash:
                raise PatchError(f"{setting_id}: companion file failed its size/SHA-256 check: {bundled}")
            plan.append({
                "setting": setting_id,
                "source": bundled,
                "destination": destination.as_posix(),
                "sha256": expected_hash,
            })
    return plan


def install_companion_files(plan: list[dict[str, Any]], staging: Path) -> list[dict[str, Any]]:
    """Copy each planned companion file into the staged output, read back."""
    summary: list[dict[str, Any]] = []
    for item in plan:
        target = staging / Path(item["destination"])
        target.parent.mkdir(parents=True, exist_ok=True)
        replaced = target.exists()
        shutil.copy2(item["source"], target)
        if sha256_file(target) != item["sha256"]:
            raise PatchError(f"Companion file failed its post-write SHA-256 check: {target}")
        summary.append({
            "setting": item["setting"],
            "path": item["destination"],
            "action": "replaced" if replaced else "added",
        })
    return summary


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
                # Carried into the patch log so the record of a run explains
                # what each change actually does.
                "note": str(patch.get("note", "")),
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
    default_folder = str(output_cfg.get("default_folder_name", "Fish Tycoon - Modded"))
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


def output_names(
    manifest: dict[str, Any], enabled: set[str], output_dir: Path, default_exe: str
) -> tuple[Path, str]:
    """The modded folder and EXE for these settings.

    Settings that add new content (``"separate_output": true``) get their own
    copy, "<Game> - Modded Upgrades", beside the plain "<Game> - Modded", so the
    two never replace each other. A folder the user named themselves is kept;
    only the default name is swapped.
    """
    output_cfg = manifest.get("output", {})
    exe_name = str(output_cfg.get("exe_name", default_exe))
    settings = manifest_settings(manifest)
    if not any(settings.get(setting_id, {}).get("separate_output") for setting_id in enabled):
        return output_dir, exe_name
    folder = output_cfg.get("upgrades_folder_name")
    exe = output_cfg.get("upgrades_exe_name")
    if not folder or not exe:
        return output_dir, exe_name
    default_folder = str(output_cfg.get("default_folder_name", ""))
    if output_dir.name.casefold() == default_folder.casefold():
        output_dir = output_dir.parent / str(folder)
    return output_dir, str(exe)


def output_family(identifier: Any) -> str:
    """Drop the trailing -v<N> revision from a manifest id.

    Output folders are recognized by family, not by exact id. Every manifest
    revision bump would otherwise orphan the folders written by the previous
    release, and the patcher would refuse to replace them.
    """
    return re.sub(r"-v\d+$", "", str(identifier or ""))


def recognized_output(path: Path, manifest: dict[str, Any]) -> bool:
    marker = path / ".fish_tycoon_bug_fix_output.json"
    if not marker.is_file():
        return False
    try:
        value = read_json(marker)
    except PatchError:
        return False
    family = output_family(manifest.get("id"))
    return bool(family) and output_family(value.get("manifest_id")) == family


def refuse_unrecognized_output(output_dir: Path, manifest: dict[str, Any]) -> None:
    if output_dir.exists() and not recognized_output(output_dir, manifest):
        raise PatchError(
            f"Output folder already exists and is not recognized as this patcher's output: {output_dir}"
        )


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
    output_dir, output_exe_name = output_names(manifest, enabled, output_dir, "Fish Tycoon - Modded.exe")
    check_setting_requirements(manifest, enabled)
    patches = active_patch_records(manifest, enabled)
    original = vanilla_exe.read_bytes()
    patched, patch_summary = apply_patch_bytes(original, patches)
    loader_summary: list[dict[str, str]] = []
    if needs_startup_loader(manifest, enabled):
        # The DS Fish companion's loader goes on last, over the patched bytes:
        # one new read/execute section and the C runtime's call of WinMain
        # routed through it (src/ds_fish_loader.py).
        try:
            patched, loader_summary = ds_fish_loader.append_startup_loader(patched)
        except ds_fish_loader.LoaderError as exc:
            raise PatchError(f"Startup loader: {exc}.") from exc
    expected_hash = expected_patched_hash(manifest, enabled)
    patched_hash = sha256_bytes(patched)
    changed = bool(patches) or bool(loader_summary)
    if changed and not expected_hash:
        raise PatchError(f"Manifest has no expected output hash for enabled settings: {settings_key(enabled)}")
    if changed and patched_hash != expected_hash:
        raise PatchError(
            f"Patched output hash mismatch: {patched_hash}; expected {expected_hash}."
        )
    companions = companion_plan(manifest, manifest_path, enabled)
    # Checked before anything is written, and in a dry run too, so a Both
    # Games run cannot write one game's folder and then refuse the other's.
    refuse_unrecognized_output(output_dir, manifest)

    report = {
        "operation": "dry-run" if args.dry_run else "apply",
        "timestamp_utc": utc_now(),
        "manifest": str(manifest_path),
        "manifest_id": manifest.get("id"),
        "manifest_version": manifest.get("version"),
        "vanilla_game_dir": str(game_dir),
        "output_dir": str(output_dir),
        "output_exe_name": output_exe_name,
        "target": identity,
        "enabled_settings": sorted(enabled),
        "patches": patch_summary,
        "startup_loader": loader_summary,
        "companion_files": [
            {"setting": item["setting"], "path": item["destination"], "action": "would add"}
            for item in companions
        ],
        "output_exe_sha256": patched_hash,
    }
    if args.dry_run:
        args.last_apply_summary = report
        print(json.dumps(report, indent=2))
        print("DRY RUN PASS: exact executable identity, all patch bytes and all companion files validated; no files written.")
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
        "source_exe_name": vanilla_exe.name,
        "output_exe_name": output_exe_name,
        "original_sha256": identity["sha256"],
        "backup_exe": backup_exe.name,
    }
    write_json(backup_dir / "fish_tycoon_patch_backup_manifest.json", backup_manifest)

    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_parent))
    try:
        shutil.rmtree(staging)
        shutil.copytree(game_dir, staging, ignore=excluded_output_files)
        make_writable(staging)
        copied_vanilla_exe = staging / vanilla_exe.name
        if copied_vanilla_exe.is_file() and copied_vanilla_exe.name != output_exe_name:
            copied_vanilla_exe.unlink()
        staged_exe = staging / output_exe_name
        staged_exe.write_bytes(patched)
        if sha256_file(staged_exe) != patched_hash:
            raise PatchError("Staged executable failed its post-write SHA-256 check.")
        report["companion_files"] = install_companion_files(companions, staging)
        report["backup_dir"] = str(backup_dir)
        report["output_exe"] = str(output_dir / output_exe_name)
        write_json(staging / ".fish_tycoon_bug_fix_output.json", {
            "manifest_id": manifest.get("id"),
            "manifest_version": manifest.get("version"),
            "created_utc": utc_now(),
            "vanilla_game_dir": str(game_dir),
            "backup_dir": str(backup_dir),
        })
        write_json(staging / "FishTycoonBugFixPatchLog.json", report)

        refuse_unrecognized_output(output_dir, manifest)
        previous = backup_dir / "previous_output"
        if output_dir.exists():
            shutil.move(str(output_dir), str(previous))
        try:
            os.replace(staging, output_dir)
        except OSError:
            # Put the previous modded folder back rather than leave the player
            # with none; it would otherwise survive only inside the backup.
            if previous.exists() and not output_dir.exists():
                shutil.move(str(previous), str(output_dir))
            raise
        report["base_game_icon_resources_preserved"] = True
        report["windows_shell_icon_refresh_requested"] = notify_windows_shell_file_changed(
            output_dir / output_exe_name
        )
        write_json(output_dir / "FishTycoonBugFixPatchLog.json", report)
    except Exception:
        if staging.exists():
            try:
                remove_tree(staging)
            except OSError:
                pass
        raise

    print(json.dumps(report, indent=2))
    print(f"PATCH PASS: created separate modded game folder: {output_dir}")
    args.last_apply_summary = report
    return 0


def restore_backup(args: argparse.Namespace) -> int:
    backup_dir = Path(args.backup_dir).expanduser().resolve()
    manifest_path = backup_dir / "fish_tycoon_patch_backup_manifest.json"
    backup = read_json(manifest_path)
    source_exe_name = str(
        backup.get("source_exe_name", backup.get("exe_name", "Fish Tycoon.exe"))
    )
    output_exe_name = str(
        backup.get("output_exe_name", backup.get("exe_name", "Fish Tycoon - Modded.exe"))
    )
    backup_exe = backup_dir / str(backup.get("backup_exe", source_exe_name))
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
    target = output_dir / output_exe_name
    temp = output_dir / f".{output_exe_name}.restore.tmp"
    shutil.copy2(backup_exe, temp)
    make_writable(temp)
    if target.exists():
        # Replacing a read-only file fails on Windows.
        make_writable(target)
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
