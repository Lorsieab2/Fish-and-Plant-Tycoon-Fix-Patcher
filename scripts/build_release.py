from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
VERSION = "v1.0.10"
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


def main() -> int:
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
