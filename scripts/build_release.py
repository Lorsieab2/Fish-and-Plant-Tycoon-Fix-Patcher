from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
VERSION = "v1.0.23"
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
    "docs/fish-tycoon-ds-fish-technical-map.md",
    "docs/fish-tycoon-ds-fish-testing-guide.md",
    "docs/fish-tycoon-pc-vs-ds-differences.md",
    "docs/fish-tycoon-ds-store-items-design.md",
    "docs/fish-tycoon-tank-expansion.md",
    "docs/fish-tycoon-extra-tanks-design.md",
    "docs/images/extra-tanks-extra-page.png",
    "docs/images/extra-tanks-stock-page.png",
    "docs/images/extra-tank-4-selling-off.png",
    "docs/images/extra-tank-4-selling-on.png",
    "docs/images/extra-tank-5-selling-off.png",
    "docs/images/extra-tank-5-selling-on.png",
    "docs/images/extra-tank-6-selling-off.png",
    "docs/images/extra-tank-6-selling-on.png",
    "docs/images/tank-3-sale-vs-tank-6-for-sale-on.png",
    "docs/images/extra-supply-slots-page-1.png",
    "docs/images/extra-supply-slots-page-2.png",
    "docs/images/extra-supply-slots-page-3.png",
    "docs/images/extra-supply-slots-locked.png",
    "docs/images/extra-supply-slots-store.png",
    "docs/images/supply-slot-tooltip-hormone.png",
    "docs/images/supply-slot-tooltip-food.png",
    "docs/images/supply-slot-tooltip-eggs.png",
    "docs/plant-tycoon-new-flowers-design.md",
    "docs/plant-tycoon-upgrades-design.md",
    "docs/plant-tycoon-extra-greenhouses-design.md",
    "docs/images/extra-greenhouses-switch.png",
    "docs/images/extra-nurseries-switch.png",
    "docs/images/extra-nurseries-nursery-1.png",
    "docs/images/extra-greenhouses-store.png",
    "docs/images/add-money-fish.png",
    "docs/images/add-money-plant.png",
    "docs/images/optimize-prices-fish.png",
    "docs/images/optimize-prices-fish-store.png",
    "docs/images/optimize-prices-plant.png",
    "docs/images/tank-counts-fish.png",
    "docs/images/greenhouse-counts-plant.png",
    "docs/images/radioactive-growth-hormone-fish.png",
    "docs/images/revival-potion-fish.png",
    "docs/images/revival-potion-plant.png",
    "docs/images/muta-chemicals-fish.png",
    "docs/images/muta-chemicals-plant.png",
    "docs/images/muta-chemicals-icons.png",
    "docs/images/auto-upgrades-fish.png",
    "docs/images/auto-upgrades-plant.png",
    "docs/images/extra-seed-box-store.png",
    "docs/images/seed-boxes-7-9-storage.png",
    "docs/images/extra-chemical-slots-page-1.png",
    "docs/images/extra-chemical-slots-page-2.png",
    "docs/images/extra-chemical-slots-store.png",
    "docs/images/tank-counts-fish-off.png",
    "docs/images/greenhouse-counts-plant-off.png",
    "docs/images/breeding-guide-fish-discovered-species.png",
    "docs/images/multiple-ornaments-tank.png",
    "docs/breeding-guide-interface.md",
    "docs/plant-tycoon-technical-details.md",
    "docs/golden-seahorse-defects.md",
    "docs/QA.md",
    "src/ds_fish_loader.py",
    "src/fish_patcher.py",
    "src/plant_patcher.py",
    "src/long_paths.py",
    "src/save_backup.py",
    "src/save_tools.py",
    "src/tools_tab.py",
    "src/breeding_guide.py",
    "src/breeding_fish.py",
    "src/breeding_plant.py",
    "src/breeding_pictures.py",
    "src/picture_image.py",
    "src/picture_formats.py",
    "src/picture_studio.py",
    "src/pictures_fish.py",
    "src/pictures_fish_ds.py",
    "src/pictures_fish_art_table.py",
    "src/pictures_fish_items.py",
    "src/pictures_game_art.py",
    "src/pictures_plant.py",
    "src/pictures_plant_data.py",
    "src/pictures_plant_items.py",
    "docs/picture-studio-interface.md",
    "src/breeding_collectopedia.py",
    "src/game_mechanics.py",
    "src/game_mechanics_fish.py",
    "src/game_mechanics_plant.py",
    "src/game_mechanics_window.py",
    "docs/game-mechanics-window.md",
    "src/experimental.py",
    "src/cheat.py",
    "src/tycoon_fix_patcher.py",
    "src/tycoon_fix_patcher_gui.py",
]


def pinned_assets() -> list[tuple[str, int, str]]:
    """Every pinned bundled file as (repo-relative path, size, SHA-256): the
    Plant Tycoon asset merge and every companion setting of both games."""
    result = []
    for name in ("plant_manifest.json", "fish_manifest.json"):
        manifest = json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
        for setting in manifest["settings"]:
            for key in ("asset_merge", "companion"):
                bundle = setting.get(key)
                if isinstance(bundle, dict):
                    result.extend(
                        (f"{bundle['source']}/{entry['path']}", entry["size"], entry["sha256"].upper())
                        for entry in bundle["files"]
                    )
    return result


def bundled_asset_files() -> list[str]:
    """Every pinned asset file, as a repo-relative path, for the release ZIP.
    A file two settings share (Time Warp.ini, in both games' manifests) is listed once."""
    return list(dict.fromkeys(relative for relative, _size, _digest in pinned_assets()))


def imported_modules(entry: str = "tycoon_fix_patcher_gui") -> set[str]:
    """Every src module the patcher can import, starting from the GUI and
    following each import (top level or inside a function) through src."""
    sources = {path.stem for path in (ROOT / "src").glob("*.py")}
    seen: set[str] = set()
    todo = [entry]
    while todo:
        name = todo.pop()
        if name in seen or name not in sources:
            continue
        seen.add(name)
        tree = ast.parse((ROOT / "src" / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                todo.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                todo.append(node.module.split(".")[0])
            elif (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "import_module"
                  and node.args and isinstance(node.args[0], ast.Constant)):
                todo.append(str(node.args[0].value).split(".")[0])
    return seen


def missing_modules(files: list[str]) -> list[str]:
    """The src files the patcher imports that the release list leaves out."""
    return sorted(f"src/{name}.py" for name in imported_modules() if f"src/{name}.py" not in files)


def main() -> int:
    global FILES
    missing = missing_modules(FILES)
    if missing:
        raise RuntimeError(f"release list is missing modules the patcher imports: {missing}")
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
        if len(set(archive.namelist())) != len(archive.namelist()):
            raise RuntimeError("release archive has a duplicate entry")
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
