"""Pin every bundled Plant Tycoon asset into the plant manifest.

Run after adding or replacing files under assets/plant_tycoon_steam/. Each file
is recorded by its game-relative path, size and SHA-256, and the patcher
refuses to merge anything that no longer matches.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "plant_manifest.json"
SETTING_ID = "add_missing_ldw_assets"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    setting = next(s for s in manifest["settings"] if s["id"] == SETTING_ID)
    source = ROOT / setting["asset_merge"]["source"]
    files = []
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        data = path.read_bytes()
        files.append({
            "path": path.relative_to(source).as_posix(),
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest().upper(),
        })
    if not files:
        raise SystemExit(f"No files found under {source}")
    setting["asset_merge"]["files"] = files
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pinned {len(files)} files from {source.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
