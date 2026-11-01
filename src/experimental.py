"""The owner's "experimental" label for settings that change how much the game
holds (more tanks, bigger tanks, more ornaments, more greenhouses and
nurseries): a setting definition with ``"experimental": true``.

Such a setting keeps the default its pin script gives it (the owner,
2026-11-01: new content stays on by default), "Select All Patches" and
"Owner's Defaults" turn it on, the patcher shows EXPERIMENTAL - USE AT OWN
RISK beside its name, and its summary and description start with that label. The pin scripts
build their setting definitions through ``mark`` so the manifests carry the
flag and the label; the GUI reads the flag through ``is_experimental``.
"""

from __future__ import annotations

from typing import Any, Mapping

FLAG = "experimental"
LABEL = "EXPERIMENTAL - USE AT OWN RISK"
PREFIX = LABEL + "."


def is_experimental(setting: Mapping[str, Any]) -> bool:
    return bool(setting.get(FLAG, False))


def labelled(text: str) -> str:
    """The text with the label in front (once)."""
    text = text.strip()
    if text.startswith(LABEL):
        return text
    return f"{PREFIX} {text}" if text else PREFIX


def mark(setting: dict[str, Any]) -> dict[str, Any]:
    """A setting definition made experimental: the flag, and its summary and description
    starting with the label. The default is kept (off when there is none). The flag sits right
    after "default"."""
    marked: dict[str, Any] = {}
    for key, value in setting.items():
        if key in ("summary", "description") and isinstance(value, str):
            value = labelled(value)
        if key == FLAG:
            continue
        marked[key] = value
        if key == "default":
            marked[key] = bool(value)
            marked[FLAG] = True
    if FLAG not in marked:
        marked["default"] = False
        marked[FLAG] = True
    return marked
