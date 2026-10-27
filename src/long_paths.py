"""Paths past Windows' 260-character limit (MAX_PATH).

A modded copy is staged beside the chosen location and a save backup nests
inside its save folder ("...\\Backups\\Backup <date> (before restore) (in
progress)\\<Game> Fix Patcher Data\\..."), so with a deep location or a long
user name a full path can pass 260 characters, where plain Windows file calls
fail with "path too long". The extended-length form ("\\\\?\\C:\\..." or
"\\\\?\\UNC\\server\\share\\...") lifts that limit to about 32,000 characters,
so every file operation of the patcher and its save tools goes through it.
Paths shown to the player or written to logs stay in the plain form.
"""

from __future__ import annotations

import os
from pathlib import Path

_PREFIX = "\\\\?\\"
_UNC_PREFIX = "\\\\?\\UNC\\"


def extended(path: str | os.PathLike) -> Path:
    """The extended-length form of ``path`` on Windows (absolute, normalised); unchanged elsewhere."""
    if os.name != "nt":
        return Path(path)
    text = os.fspath(path)
    if text.startswith(_PREFIX):
        return Path(text)
    text = os.path.abspath(text)
    if text.startswith("\\\\"):
        return Path(_UNC_PREFIX + text[2:])
    return Path(_PREFIX + text)


def plain(path: str | os.PathLike) -> Path:
    """``path`` without the extended-length prefix, as the player knows it."""
    text = os.fspath(path)
    if text.startswith(_UNC_PREFIX):
        return Path("\\\\" + text[len(_UNC_PREFIX):])
    if text.startswith(_PREFIX):
        return Path(text[len(_PREFIX):])
    return Path(text)
