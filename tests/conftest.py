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
import picture_image  # noqa: E402

_CACHE = Path(tempfile.mkdtemp(prefix="breeding-guide-pictures-"))
breeding_pictures.CACHE_ROOT = _CACHE
picture_image.CACHE_ROOT = _CACHE / "Picture Studio Pictures"
breeding_guide.INSTALL_ENV = {}
atexit.register(shutil.rmtree, _CACHE, True)


# Tk's startup can fail now and then ("tk wasn't installed properly") while many test workers
# start Tk at the same moment; a new root is retried a few times before the error stands.
import time as _time  # noqa: E402
import tkinter as _tkinter  # noqa: E402

_tk_init = _tkinter.Tk.__init__


def _tk_init_retrying(self, *args, **kwargs):
    for attempt in range(4):
        try:
            return _tk_init(self, *args, **kwargs)
        except _tkinter.TclError:
            if attempt == 3:
                raise
            _time.sleep(0.5 * (attempt + 1))


_tkinter.Tk.__init__ = _tk_init_retrying
