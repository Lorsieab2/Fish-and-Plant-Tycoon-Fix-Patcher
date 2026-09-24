from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
VERSION = "v1.0.15"
NAME = f"Fish-and-Plant-Tycoon-Fix-Patcher-{VERSION}.zip"
FILES = [
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "How to Use.txt",
    "Launch Fish and Plant Tycoon Fix Patcher.bat",
    "assets/fish.png",
    "assets/plant.png",
    "data/fish_manifest.json",
    "data/plant_manifest.json",
    "docs/fish-tycoon-technical-details.md",
    "docs/plant-tycoon-technical-details.md",
    "docs/golden-seahorse-defects.md",
    "docs/QA.md",
    "src/fish_patcher.py",
    "src/plant_patcher.py",
    "src/tycoon_fix_patcher.py",
    "src/tycoon_fix_patcher_gui.py",
]


def pinned_assets() -> list[tuple[str, int, str]]:
    """Every pinned asset file as (repo-relative path, size, SHA-256)."""
    manifest = json.loads((ROOT / "data" / "plant_manifest.json").read_text(encoding="utf-8"))
    result = []
    for setting in manifest["settings"]:
        merge = setting.get("asset_merge")
        if isinstance(merge, dict):
            result.extend(
                (f"{merge['source']}/{entry['path']}", entry["size"], entry["sha256"].upper())
                for entry in merge["files"]
            )
    return result


def bundled_asset_files() -> list[str]:
    """Every pinned asset file, as a repo-relative path, for the release ZIP."""
    return [relative for relative, _size, _digest in pinned_assets()]


def main() -> int:
    global FILES
    FILES = FILES + bundled_asset_files()
    OUTPUTS.mkdir(exist_ok=True)
    target = OUTPUTS / NAME
    temp = OUTPUTS / (NAME + ".tmp")
    temp.unlink(missing_ok=True)
    with zipfile.ZipFile(
        temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for relative in FILES:
            archive.write(ROOT / relative, relative)
    temp.replace(target)
    with zipfile.ZipFile(target) as archive:
        if sorted(archive.namelist()) != sorted(FILES):
            raise RuntimeError("release archive manifest mismatch")
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"release archive CRC failure: {bad}")
        if any(name.lower().endswith(".exe") for name in archive.namelist()):
            raise RuntimeError("release must not contain game executables")
        # Check the bundled assets as packaged, not as they sit on disk.
        for relative, size, digest in pinned_assets():
            data = archive.read(relative)
            if len(data) != size or hashlib.sha256(data).hexdigest().upper() != digest:
                raise RuntimeError(f"release asset does not match its pin: {relative}")
    digest = hashlib.sha256(target.read_bytes()).hexdigest().upper()
    manifest = {
        "file": target.name,
        "size": target.stat().st_size,
        "sha256": digest,
        "entries": FILES,
    }
    (OUTPUTS / f"{target.stem}.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
