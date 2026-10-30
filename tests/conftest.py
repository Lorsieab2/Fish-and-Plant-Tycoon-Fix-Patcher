"""Suite-wide: the Breeding Guide's picture cache goes to a temporary folder, never the
patcher's own folder, and the guide does not look in this machine's default installs."""

from __future__ import annotations

import atexit
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import breeding_guide  # noqa: E402
import breeding_pictures  # noqa: E402

_CACHE = Path(tempfile.mkdtemp(prefix="breeding-guide-pictures-"))
breeding_pictures.CACHE_ROOT = _CACHE
breeding_guide.INSTALL_ENV = {}
atexit.register(shutil.rmtree, _CACHE, True)
